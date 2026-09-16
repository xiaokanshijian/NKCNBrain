<template>
  <div class="ci-panel-overlay">
    <div class="ci-panel">
      <!-- 面板顶部 -->
      <div class="ci-panel-header">
        <h2 class="ci-panel-title" @dblclick.stop="handleTitleDoubleClick" title="双击可触发重新生图">连续图片认知理解</h2>
        <div class="ci-panel-header-right">
          <!-- 视角切换（仅多图结果时显示） -->
          <div class="ci-view-switch" v-if="activeResult && mSections.length > 1">
            <button
              class="ci-switch-btn"
              :class="{ active: viewMode === 'single' }"
              @click="switchViewMode('single')"
            >单图视角</button>
            <button
              class="ci-switch-btn"
              :class="{ active: viewMode === 'group' }"
              @click="switchViewMode('group')"
            >连续组视角</button>
          </div>
          <!-- 迭代（仅展示结果时） -->
          <button
            class="ci-rebuild-btn"
            v-if="activeResult && activeAnalysisId"
            @click="$emit('redo', activeAnalysisId)"
            title="迭代 M/T 层理解（复用 OCR 缓存）"
          >迭代</button>
          <button
            class="ci-generate-btn"
            v-if="activeResult && activeAnalysisId && mSections.length <= 1"
            :disabled="reproductionBusy"
            @click="handleTopIterativeGenerate"
            :title="reproductionButtonTitle"
          >{{ reproductionButtonLabel }}</button>
          <button
            class="ci-rebuild-btn"
            v-if="activeResult && activeAnalysisId && mSections.length <= 1"
            :disabled="topRollbackDisabled"
            @click="handleTopRollback"
            :title="topRollbackTitle"
          >回滚上一版</button>
          <!-- 关闭 -->
          <div class="ci-close-btn" @click="$emit('close')">&times;</div>
        </div>
      </div>

      <!-- 分析标签栏：单图 + 多图 tabs -->
      <div class="ci-tabs-bar" v-if="allTabs.length > 1">
        <button
          v-for="tab in allTabs"
          :key="tab.analysis_id"
          class="ci-tab-btn"
          :class="{ active: tab.analysis_id === activeAnalysisId }"
          @click="$emit('switch-tab', tab.analysis_id)"
          :title="tab.files ? tab.files.join(', ') : ''"
        >{{ tab.label }}</button>
      </div>

      <!-- 结果区域 -->
      <div class="ci-result-body" v-if="activeResult">
        <div class="ci-layer ci-layer-r-top" v-if="rItems.length">
          <div class="ci-layer-header ci-r-top-header" @click="rContextPanelExpanded = !rContextPanelExpanded">
            <span class="ci-layer-icon">🧾</span>
            <span class="ci-layer-label">R层生成依据 / 单页迭代</span>
            <span class="ci-expand-arrow" :class="{ expanded: rContextPanelExpanded }">▼</span>
          </div>
          <div class="ci-layer-content" v-show="rContextPanelExpanded">
            <div class="ci-lite-batch-bar" v-if="activeResult">
              <button
                type="button"
                class="ci-action-btn ci-action-btn-primary"
                :disabled="liteBatchRunning || reproductionBusy"
                @click="openLiteBatchWorkflowDialog"
              >{{ liteBatchRunning ? '批量自动化进行中…' : '批量轻量识字+三层理解预览' }}</button>
              <span class="ci-single-inline-hint">弹窗内先选图并查询 CI 状态，再批量：轻量 Qwen 识字（全 D 区）→ Gemini 校正三层理解预览（写入当日缓存，不自动确认向量库）</span>
            </div>
            <div class="ci-r-context-body">
              <div
                class="ci-r-unit-editor"
                v-for="item in rItems"
                :key="item.unit_id"
              >
                <div class="ci-r-unit-header" @click="toggleRContextSection(item.unit_id)">
                  <div class="ci-r-unit-header-left">
                    <img
                      v-if="item.status === 'ready' && getReproductionSrc(item)"
                      :src="getReproductionSrc(item)"
                      class="ci-r-unit-thumb"
                      alt="R层复现图缩略图"
                    />
                    <div class="ci-r-unit-meta">
                      <div class="ci-r-unit-title">{{ getReproductionTitle(item) }}</div>
                      <div class="ci-r-unit-subtitle">
                        <span>状态：{{ formatRItemStatus(item.status) }}</span>
                        <span v-if="item.iter_context && item.iter_context.updated_at">更新时间：{{ formatCompactTime(item.iter_context.updated_at) }}</span>
                        <span v-if="item.iter_context">模式：{{ item.iter_context.use_sketch_input ? '输入草图' : '不输入草图' }}</span>
                        <span v-if="item.iter_context && item.iter_context.use_sketch_input && item.iter_context.use_original_sketch_as_r">｜原图直出 R</span>
                        <span v-if="item.rollback_count">可回滚：{{ item.rollback_count }} 个版本</span>
                      </div>
                    </div>
                  </div>
                  <div class="ci-r-unit-header-right">
                    <span v-if="isUnitIterating(item.unit_id)" class="ci-r-unit-busy">迭代中…</span>
                    <span class="ci-expand-arrow" :class="{ expanded: rContextExpandedSections[item.unit_id] }">▼</span>
                  </div>
                </div>
                <div v-show="rContextExpandedSections[item.unit_id]" class="ci-r-unit-body" v-if="rContextEdits[item.unit_id]">
                  <div class="ci-r-field-inline">
                    <label class="ci-r-field-label">生成模式</label>
                    <select v-model="rContextEdits[item.unit_id].use_sketch_input" class="ci-r-select">
                      <option :value="true">输入草图</option>
                      <option :value="false">不输入草图</option>
                    </select>
                  </div>
                  <div class="ci-r-field-inline" v-if="rContextEdits[item.unit_id].use_sketch_input">
                    <label class="ci-r-field-label">原图直出</label>
                    <label class="ci-r-inline-check">
                      <input type="checkbox" v-model="rContextEdits[item.unit_id].use_original_sketch_as_r" />
                      直接用原草图作为 R 层复现图（不调升维模型）
                    </label>
                  </div>
                  <div
                    class="ci-r-field"
                    v-for="field in rContextFieldDefs"
                    :key="field.key"
                  >
                    <div class="ci-r-field-top">
                      <label class="ci-r-field-label">{{ field.label }}</label>
                      <button type="button" class="ci-r-mini-btn" @click.stop="toggleRTextPreview(item.unit_id, field.key)">
                        {{ isRTextPreviewCollapsed(item.unit_id, field.key) ? '展开' : '收起' }}
                      </button>
                    </div>
                    <div
                      v-if="isRTextPreviewCollapsed(item.unit_id, field.key)"
                      class="ci-r-field-preview"
                    >{{ getRFieldPreview(item.unit_id, field.key) }}</div>
                    <textarea
                      v-else-if="field.editable"
                      v-model="rContextEdits[item.unit_id][field.key]"
                      class="ci-r-textarea"
                      :rows="field.rows"
                    ></textarea>
                    <pre
                      v-else
                      class="ci-r-readonly"
                    >{{ rContextEdits[item.unit_id][field.key] || '（空）' }}</pre>
                  </div>
                  <div class="ci-r-actions">
                    <button type="button" class="ci-action-btn" @click.stop="saveRContextItem(item)">保存字段</button>
                    <button
                      type="button"
                      class="ci-action-btn"
                      :disabled="isUnitIterating(item.unit_id) || !canRollbackRItem(item)"
                      @click.stop="rollbackRContextItem(item)"
                    >回滚上一版</button>
                    <button
                      type="button"
                      class="ci-action-btn ci-action-btn-primary"
                      :disabled="isUnitIterating(item.unit_id)"
                      @click.stop="handleRUnitPrimaryAction(item)"
                    >{{ item.status === 'ready' ? '迭代该页复现图' : '保存后生成该页复现图' }}</button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ====== T 层：整体纪要 ====== -->
        <div class="ci-layer ci-layer-t">
          <div class="ci-layer-header" @click="tLayerExpanded = !tLayerExpanded">
            <span class="ci-layer-icon">📋</span>
            <span class="ci-layer-label">整体纪要 (T 层)</span>
            <span class="ci-expand-arrow" :class="{ expanded: tLayerExpanded }">▼</span>
          </div>
          <div class="ci-layer-content" v-show="tLayerExpanded">
            <!-- 总体理解 -->
            <div class="ci-t-block" v-if="tLayer.overall_summary">
              <div class="ci-t-block-title">📝 总体理解</div>
              <div class="ci-t-block-content">{{ tLayer.overall_summary }}</div>
            </div>
            <!-- 核心主题 -->
            <div class="ci-t-block" v-if="tLayer.core_theme">
              <div class="ci-t-block-title">🎯 核心主题</div>
              <div class="ci-t-block-content">{{ tLayer.core_theme }}</div>
            </div>
            <!-- 多图关系 -->
            <div class="ci-t-block" v-if="hasMeaningful(tLayer.group_relations)">
              <div class="ci-t-block-title">🔗 多图关系</div>
              <div class="ci-t-block-content ci-pre-wrap">{{ formatRelations(tLayer.group_relations) }}</div>
            </div>
            <!-- 图文关联 -->
            <div class="ci-t-block" v-if="hasMeaningful(tLayer.doc_relations)">
              <div class="ci-t-block-title">📄 图文关联</div>
              <div class="ci-t-block-content ci-pre-wrap">{{ formatRelations(tLayer.doc_relations) }}</div>
            </div>
            <!-- 场景意义 -->
            <div class="ci-t-block" v-if="hasMeaningful(tLayer.scene_meaning)">
              <div class="ci-t-block-title">🌐 场景意义</div>
              <div class="ci-t-block-content ci-pre-wrap">{{ formatRelations(tLayer.scene_meaning) }}</div>
            </div>
            <div class="ci-t-block" v-if="readyRItems.length || failedRItems.length">
              <div class="ci-t-block-title">🎨 升维复现图</div>
              <div class="ci-t-repro-grid" v-if="readyRItems.length">
                <div
                  class="ci-t-repro-card"
                  v-for="item in readyRItems"
                  :key="item.unit_id"
                  @click="openReproductionImage(item)"
                  @contextmenu.prevent.stop="openSingleReproContextMenu($event, item)"
                  :title="isStrictSingleMode ? `点击查看 ${getReproductionTitle(item)}；右键可更新单图理解` : `点击查看 ${getReproductionTitle(item)}`"
                >
                  <img
                    :src="getReproductionSrc(item)"
                    class="ci-t-repro-thumb"
                    :alt="getReproductionTitle(item)"
                  />
                  <div class="ci-t-repro-caption">{{ getReproductionTitle(item) }}</div>
                </div>
              </div>
              <div class="ci-t-repro-failed" v-if="failedRItems.length">
                {{ failedRItems.length }} 张复现图生成失败，可点击顶部“迭代生图”，或双击标题“连续图片认知理解”触发重新生图。
              </div>
            </div>
            <!-- 认知建议 -->
            <div class="ci-t-advice">
              <div class="ci-t-advice-title">💡 认知建议</div>
              <div class="ci-t-advice-item" v-if="tLayer.blind_spots">
                <span class="ci-advice-label">盲区：</span>
                <span class="ci-pre-wrap">{{ formatRelations(tLayer.blind_spots) }}</span>
              </div>
              <div class="ci-t-advice-item" v-if="tLayer.internal_friction">
                <span class="ci-advice-label">内耗区：</span>
                <span class="ci-pre-wrap">{{ formatRelations(tLayer.internal_friction) }}</span>
              </div>
              <div class="ci-t-advice-item" v-if="tLayer.zpd_next_step">
                <span class="ci-advice-label">最近发展区：</span>
                <span>{{ tLayer.zpd_next_step }}</span>
              </div>
              <div class="ci-t-advice-item" v-if="tLayer.next_actions">
                <span class="ci-advice-label">下一步建议：</span>
                <span class="ci-pre-wrap">{{ formatRelations(tLayer.next_actions) }}</span>
              </div>
            </div>
            <!-- 本体萃取 -->
            <div class="ci-t-candidates" v-if="tLayer.semantic_layer_candidate || tLayer.tribal_candidate">
              <div class="ci-t-block-title">🧩 本体萃取</div>
              <div class="ci-t-advice-item" v-if="tLayer.semantic_layer_candidate">
                <span class="ci-advice-label">升维语义萃取：</span>
                <span class="ci-pre-wrap">{{ formatRelations(tLayer.semantic_layer_candidate) }}</span>
              </div>
              <div class="ci-t-advice-item" v-if="tLayer.tribal_candidate">
                <span class="ci-advice-label">部落知识萃取：</span>
                <span class="ci-pre-wrap">{{ formatRelations(tLayer.tribal_candidate) }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- ====== M 层：章节纪要 ====== -->
        <div class="ci-layer ci-layer-m">
          <div class="ci-layer-header" @click="mLayerExpanded = !mLayerExpanded">
            <span class="ci-layer-icon">📑</span>
            <span class="ci-layer-label">章节纪要 (M 层)</span>
            <span class="ci-page-info" v-if="mSections.length">共 {{ mSections.length }} 页</span>
            <span class="ci-expand-arrow" :class="{ expanded: mLayerExpanded }">▼</span>
          </div>
          <div class="ci-layer-content" v-show="mLayerExpanded">
            <!-- 连续组视角 -->
            <template v-if="viewMode === 'group'">
              <div
                class="ci-m-section"
                v-for="(section, idx) in mSections"
                :key="section.unit_id || idx"
              >
                <div class="ci-m-section-header" @click="toggleSection(idx)">
                  <span class="ci-m-seq">{{ idx + 1 }}</span>
                  <span class="ci-m-title">{{ section.title || `第${idx + 1}页` }}</span>
                  <span class="ci-m-source">{{ section.source_file || '' }}{{ section.page ? ` p${section.page}` : '' }}</span>
                  <span class="ci-m-layout-badge" v-if="section.layout_visual_status === 'ready'" title="有版面可视化">
                    📐
                  </span>
                  <span class="ci-expand-arrow" :class="{ expanded: expandedSections[idx] }">▼</span>
                </div>
                <div class="ci-m-section-body" v-show="expandedSections[idx]">
                  <!-- 结构说明 -->
                  <div class="ci-m-field" v-if="section.main_content">
                    <div class="ci-m-field-label">主要内容</div>
                    <div class="ci-m-field-value">{{ section.main_content }}</div>
                  </div>
                  <div class="ci-m-field" v-if="hasMeaningful(section.layout_regions)">
                    <div class="ci-m-field-label">版面区域</div>
                    <div class="ci-m-field-value ci-pre-wrap">{{ formatLayoutRegions(section.layout_regions) }}</div>
                  </div>
                  <div class="ci-m-field" v-if="section.reading_order">
                    <div class="ci-m-field-label">阅读顺序</div>
                    <div class="ci-m-field-value">{{ section.reading_order }}</div>
                  </div>
                  <div class="ci-m-field" v-if="section.annotation_relation">
                    <div class="ci-m-field-label">标注关系</div>
                    <div class="ci-m-field-value">{{ section.annotation_relation }}</div>
                  </div>
                  <!-- 与前一图关系 -->
                  <div class="ci-m-continuity" v-if="section.continuity_with_prev">
                    <span class="ci-continuity-label">↕ 与前一图关系：</span>
                    <span>{{ formatContinuity(section.continuity_with_prev) }}</span>
                  </div>
                  <div class="ci-m-d-input" v-if="shouldShowOcrInputPolicy(section)">
                    <div class="ci-m-d-input-topline">
                      <span class="ci-m-d-input-label">D层输入：</span>
                      <span
                        class="ci-m-d-input-badge"
                        :class="getOcrInputBadgeClass(getOcrInputPolicy(section))"
                      >{{ formatOcrInputUsage(getOcrInputPolicy(section)) }}</span>
                    </div>
                    <div class="ci-m-d-input-detail" v-if="getOcrInputReason(section)">
                      原因：{{ getOcrInputReason(section) }}
                    </div>
                    <div class="ci-m-d-input-detail" v-if="hasOcrInputDebugFlags(section)">
                      快速判定：
                      无意义={{ getOcrInputPolicy(section).meaningless_ocr ? '是' : '否' }}，
                      与上下文无关={{ getOcrInputPolicy(section).unrelated_to_context ? '是' : '否' }}
                    </div>
                    <div class="ci-m-d-input-detail" v-if="getOcrInputPolicy(section).judge_model">
                      判定模型：{{ getOcrInputPolicy(section).judge_model }}
                    </div>
                  </div>
                  <!-- 操作按钮 -->
                  <div class="ci-m-actions">
                    <button
                      class="ci-action-btn"
                      v-if="section.layout_visual_status === 'ready'"
                      @click="openLayoutVisual(section)"
                    >📐 查看版面</button>
                    <button
                      class="ci-action-btn"
                      @click="toggleOcr(idx)"
                    >{{ expandedOcrs[idx] ? '收起 OCR' : '展开 OCR' }}</button>
                  </div>
                  <!-- OCR 内联展开 -->
                  <div class="ci-m-ocr" v-show="expandedOcrs[idx]">
                    <div class="ci-ocr-title">
                      OCR 原文
                      <span class="ci-low-confidence" v-if="getUnitDLayer(section.unit_id)?.low_confidence_hint">⚠ 低置信</span>
                    </div>
                    <pre class="ci-ocr-text">{{ getUnitDLayer(section.unit_id)?.ocr_text || '无 OCR 数据' }}</pre>
                  </div>
                </div>
              </div>
            </template>
            <!-- 单图视角 -->
            <template v-else>
              <div class="ci-single-view">
                <div class="ci-single-nav">
                  <button class="ci-nav-btn" :disabled="singleIndex <= 0" @click="singleIndex--">‹ 上一图</button>
                  <span class="ci-nav-info">{{ singleIndex + 1 }} / {{ mSections.length }}</span>
                  <button class="ci-nav-btn" :disabled="singleIndex >= mSections.length - 1" @click="singleIndex++">下一图 ›</button>
                </div>
                <div class="ci-m-section active-single" v-if="currentSingleSection">
                  <div class="ci-m-section-header">
                    <span class="ci-m-seq">{{ singleIndex + 1 }}</span>
                    <span class="ci-m-title">{{ currentSingleSection.title || `第${singleIndex + 1}页` }}</span>
                    <span class="ci-m-source">{{ currentSingleSection.source_file || '' }}{{ currentSingleSection.page ? ` p${currentSingleSection.page}` : '' }}</span>
                    <span class="ci-m-layout-badge" v-if="currentSingleSection.layout_visual_status === 'ready'" title="有版面可视化">
                      📐
                    </span>
                  </div>
                  <div class="ci-m-section-body" style="display: block;">
                    <div class="ci-m-field" v-if="currentSingleSection.main_content">
                      <div class="ci-m-field-label">主要内容</div>
                      <div class="ci-m-field-value">{{ currentSingleSection.main_content }}</div>
                    </div>
                    <div class="ci-m-field" v-if="hasMeaningful(currentSingleSection.layout_regions)">
                      <div class="ci-m-field-label">版面区域</div>
                      <div class="ci-m-field-value ci-pre-wrap">{{ formatLayoutRegions(currentSingleSection.layout_regions) }}</div>
                    </div>
                    <div class="ci-m-field" v-if="currentSingleSection.reading_order">
                      <div class="ci-m-field-label">阅读顺序</div>
                      <div class="ci-m-field-value">{{ currentSingleSection.reading_order }}</div>
                    </div>
                    <div class="ci-m-field" v-if="currentSingleSection.annotation_relation">
                      <div class="ci-m-field-label">标注关系</div>
                      <div class="ci-m-field-value">{{ currentSingleSection.annotation_relation }}</div>
                    </div>
                    <div class="ci-m-continuity" v-if="currentSingleSection.continuity_with_prev">
                      <span class="ci-continuity-label">↕ 与前一图关系：</span>
                      <span>{{ formatContinuity(currentSingleSection.continuity_with_prev) }}</span>
                    </div>
                    <div class="ci-m-d-input" v-if="shouldShowOcrInputPolicy(currentSingleSection)">
                      <div class="ci-m-d-input-topline">
                        <span class="ci-m-d-input-label">D层输入：</span>
                        <span
                          class="ci-m-d-input-badge"
                          :class="getOcrInputBadgeClass(getOcrInputPolicy(currentSingleSection))"
                        >{{ formatOcrInputUsage(getOcrInputPolicy(currentSingleSection)) }}</span>
                      </div>
                      <div class="ci-m-d-input-detail" v-if="getOcrInputReason(currentSingleSection)">
                        原因：{{ getOcrInputReason(currentSingleSection) }}
                      </div>
                      <div class="ci-m-d-input-detail" v-if="hasOcrInputDebugFlags(currentSingleSection)">
                        快速判定：
                        无意义={{ getOcrInputPolicy(currentSingleSection).meaningless_ocr ? '是' : '否' }}，
                        与上下文无关={{ getOcrInputPolicy(currentSingleSection).unrelated_to_context ? '是' : '否' }}
                      </div>
                      <div class="ci-m-d-input-detail" v-if="getOcrInputPolicy(currentSingleSection).judge_model">
                        判定模型：{{ getOcrInputPolicy(currentSingleSection).judge_model }}
                      </div>
                    </div>
                    <div class="ci-m-actions">
                      <button
                        class="ci-action-btn"
                        v-if="currentSingleSection.layout_visual_status === 'ready'"
                        @click="openLayoutVisual(currentSingleSection)"
                      >📐 查看版面</button>
                      <button class="ci-action-btn" @click="showSingleOcr = !showSingleOcr">
                        {{ showSingleOcr ? '收起 OCR' : '展开 OCR' }}
                      </button>
                    </div>
                    <div class="ci-m-ocr" v-show="showSingleOcr">
                      <div class="ci-ocr-title">
                        OCR 原文
                        <span class="ci-low-confidence" v-if="getUnitDLayer(currentSingleSection.unit_id)?.low_confidence_hint">⚠ 低置信</span>
                      </div>
                      <pre class="ci-ocr-text">{{ getUnitDLayer(currentSingleSection.unit_id)?.ocr_text || '无 OCR 数据' }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- ====== D 层：原始记录 ====== -->
        <div class="ci-layer ci-layer-d">
          <div class="ci-layer-header" @click="dLayerExpanded = !dLayerExpanded">
            <span class="ci-layer-icon">📝</span>
            <span class="ci-layer-label">原始记录 (D 层)</span>
            <span class="ci-expand-arrow" :class="{ expanded: dLayerExpanded }">▼</span>
          </div>
          <div class="ci-layer-content" v-show="dLayerExpanded">
            <div
              class="ci-d-unit"
              v-for="(unit, idx) in dUnits"
              :key="unit.unit_id || idx"
            >
              <div class="ci-d-unit-header">
                <span class="ci-d-seq">{{ unit.seq || idx + 1 }}</span>
                <span class="ci-d-source">{{ unit.source_file }}{{ unit.page ? ` p${unit.page}` : '' }}</span>
                <span class="ci-low-confidence" v-if="unit.low_confidence_hint">⚠ 低置信</span>
              </div>
              <div class="ci-d-unit-body">
                <div class="ci-d-tabs">
                  <button
                    class="ci-d-tab"
                    :class="{ active: dViewMode[idx] !== 'markdown' }"
                    @click="setDViewMode(idx, 'text')"
                  >原文</button>
                  <button
                    class="ci-d-tab"
                    :class="{ active: dViewMode[idx] === 'markdown' }"
                    @click="setDViewMode(idx, 'markdown')"
                  >Markdown</button>
                </div>
                <pre
                  class="ci-d-text"
                  v-if="dViewMode[idx] !== 'markdown'"
                >{{ unit.ocr_text || '无内容' }}</pre>
                <pre
                  class="ci-d-text"
                  v-else
                >{{ unit.ocr_markdown || unit.ocr_text || '无内容' }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 文件信息 -->
        <div class="ci-manifest-info" v-if="manifest">
          <div class="ci-manifest-label">分析模式：{{ manifest.mode === 'single' ? '单图' : '连续组' }}</div>
          <div class="ci-manifest-label">涉及文件：{{ (manifest.selected_files || []).join(', ') }}</div>
          <div class="ci-manifest-label" v-if="manifest.scene_name">场景：{{ manifest.scene_name }} {{ manifest.sub_scene_name ? '/ ' + manifest.sub_scene_name : '' }}</div>
        </div>
      </div>

      <!-- 布局可视化弹窗 -->
      <div class="ci-layout-overlay" v-if="layoutVisualVisible" @click.self="layoutVisualVisible = false">
        <div class="ci-layout-dialog">
          <div class="ci-layout-header">
            <span>📐 版面可视化</span>
            <span class="ci-layout-view-tag">{{ layoutVisualIsOriginal ? '原始内容' : '布局可视化内容' }}</span>
            <div class="ci-close-btn" @click="layoutVisualVisible = false">&times;</div>
          </div>
          <div class="ci-layout-body">
            <!-- PDF 类型：iframe 内嵌预览 -->
            <iframe
              v-if="layoutVisualSrc && layoutVisualType === 'pdf'"
              :src="layoutVisualSrc"
              class="ci-layout-iframe"
              frameborder="0"
            ></iframe>
            <!-- 图片类型：img 直接渲染 -->
            <img
              v-else-if="layoutVisualSrc && layoutVisualType !== 'pdf'"
              :src="layoutVisualSrc"
              alt="版面可视化"
              class="ci-layout-img"
            />
            <div v-else class="ci-layout-empty">暂无版面可视化数据</div>
          </div>
        </div>
      </div>

      <div
        v-if="singleReproContextMenuVisible"
        class="ci-repro-context-menu"
        :style="{ left: `${singleReproContextMenuX}px`, top: `${singleReproContextMenuY}px` }"
      >
        <button type="button" class="ci-repro-context-menu-item" :disabled="singleReproRefineBusy" @click="runSingleRefineTLayer">
          {{ singleReproRefineBusy ? '处理中…' : '更新完善整体纪要（T层）' }}
        </button>
        <button type="button" class="ci-repro-context-menu-item" :disabled="singleReproRefineBusy" @click="runSingleRefineImageUnderstandingPreview">
          {{ singleReproRefineBusy ? '处理中…' : '更新完善原图片三层理解' }}
        </button>
        <button type="button" class="ci-repro-context-menu-item" :disabled="singleReproRefineBusy" @click="runSingleRollbackTLayer">
          回退整体纪要（T层）到上一版
        </button>
      </div>

      <div class="ci-layout-overlay" v-if="rIterateDialogVisible" @click.self="closeRIterateDialog">
        <div class="ci-layout-dialog ci-r-iterate-dialog" @paste="handleRIterateDialogPaste">
          <div class="ci-layout-header">
            <span>🛠 R层单页迭代</span>
            <div class="ci-close-btn" @click="closeRIterateDialog">&times;</div>
          </div>
          <div class="ci-layout-body ci-r-iterate-body">
            <div class="ci-r-iterate-hint">改图依据：当前R层生成字段、可选文字修改要求、可选参考图。若该页已有复现图，将尽量保持原图风格与布局稳定，仅做必要局部更新。</div>
            <div class="ci-r-field-inline">
              <label class="ci-r-field-label">清晰度</label>
              <select v-model="rIterateImageQuality" class="ci-r-select">
                <option value="normal">普通（现有逻辑）</option>
                <option value="high">高清（4K）</option>
              </select>
            </div>
            <div class="ci-r-field">
              <label class="ci-r-field-label">具体修改要求</label>
              <textarea
                v-model="rIterateRevisionInstruction"
                class="ci-r-textarea"
                rows="4"
                placeholder="例如：把顶部标题改得更具体；去掉右侧某块装饰；保持整体结构不变，仅更新第2块内容"
              ></textarea>
            </div>
            <div class="ci-r-field">
              <label class="ci-r-field-label">参考图（选填）</label>
              <input ref="rIterateFileInput" type="file" accept="image/*" class="ci-r-file-input" @change="onRIterateReferenceFileChange" />
              <div class="ci-r-actions ci-r-actions-left">
                <button type="button" class="ci-action-btn" @click="triggerRIterateReferenceUpload">选择图片</button>
                <button type="button" class="ci-action-btn" v-if="rIterateReferenceDataUrl" @click="clearRIterateReferenceImage">清除</button>
                <span class="ci-r-paste-tip">也可直接粘贴图片</span>
              </div>
              <img v-if="rIterateReferenceDataUrl" :src="rIterateReferenceDataUrl" class="ci-r-reference-preview" alt="参考图预览" />
            </div>
            <div class="ci-r-actions ci-r-dialog-actions">
              <button type="button" class="ci-action-btn" @click="closeRIterateDialog">取消</button>
              <button type="button" class="ci-action-btn ci-action-btn-primary" @click="submitRIterateDialog">确定并迭代</button>
            </div>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleWorkAreaVisible" @click.self="closeSingleWorkArea">
        <div class="ci-layout-dialog ci-single-workspace-dialog">
          <div class="ci-layout-header">
            <span>🛠 单图迭代工作区</span>
            <div class="ci-close-btn" @click="closeSingleWorkArea">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-workspace-body">
            <div class="ci-single-workspace-left">
              <div class="ci-single-preview-card">
                <div class="ci-single-preview-head">
                  <div class="ci-single-preview-title">当前复现图</div>
                  <div v-if="singleWorkAreaReproductionSrc" class="ci-single-preview-zoom-tools">
                    <button type="button" class="ci-preview-zoom-btn" @click="adjustSingleWorkAreaPreviewZoom(-0.2)">-</button>
                    <input v-model.number="singleWorkAreaPreviewZoom" class="ci-preview-zoom-range" type="range" min="1" max="3.5" step="0.1" />
                    <button type="button" class="ci-preview-zoom-btn" @click="adjustSingleWorkAreaPreviewZoom(0.2)">+</button>
                    <button type="button" class="ci-preview-zoom-reset" @click="resetSingleWorkAreaPreviewZoom">{{ Math.round(singleWorkAreaPreviewZoom * 100) }}%</button>
                  </div>
                </div>
                <div v-if="singleOverlayDataUrl" class="ci-single-preview-filter-panel">
                  <div class="ci-single-preview-filter-head">
                    <span class="ci-single-preview-filter-label">覆盖层显示</span>
                    <span class="ci-single-preview-filter-summary">{{ getSingleOverlayVisibleSummaryText() }}</span>
                  </div>
                  <div class="ci-single-preview-filter-row">
                    <button
                      v-for="level in ['d', 'm', 't']"
                      :key="`overlay-filter-${level}`"
                      type="button"
                      class="ci-single-preview-filter-toggle"
                      :class="[`is-${level}`, { 'is-active': isSingleOverlayLevelVisible(level) }]"
                      :aria-pressed="isSingleOverlayLevelVisible(level) ? 'true' : 'false'"
                      @click="toggleSingleOverlayVisibleLevel(level)"
                    >
                      <span class="ci-single-preview-filter-toggle-title">{{ getSingleOverlayLevelLabel(level) }}</span>
                      <span class="ci-single-preview-filter-toggle-state">{{ getSingleOverlayLevelVisibilityText(level) }}</span>
                    </button>
                  </div>
                </div>
                <div class="ci-single-preview-viewport">
                  <div
                    ref="singleWorkAreaPreviewStage"
                    class="ci-single-preview-stage"
                    :class="{ 'is-selectable': singleOverlayRegionBoxesVisible }"
                    :style="getSingleWorkAreaPreviewStageStyle()"
                    @click="handleSinglePreviewStageClick"
                  >
                    <img
                      v-if="singleWorkAreaReproductionSrc"
                      ref="singleWorkAreaPreviewImage"
                      :src="singleWorkAreaReproductionSrc"
                      class="ci-single-preview-image"
                      alt="当前复现图"
                      @load="syncSingleOverlayDisplayMetrics"
                    />
                    <div v-else class="ci-single-preview-empty">当前页尚无复现图</div>
                    <img
                      v-if="singleOverlayPreviewDataUrl"
                      :src="singleOverlayPreviewDataUrl"
                      class="ci-single-preview-overlay"
                      alt="DMT覆盖层预览"
                    />
                    <div v-if="singleOverlayRegionBoxesVisible" class="ci-single-layout-region-layer">
                      <div
                        v-for="region in singleOverlayVisibleRegions"
                        :key="`overlay-region-${region.region_id}`"
                        class="ci-single-layout-region-box"
                        :class="[
                          `is-${region.level || 'd'}`,
                          {
                            'is-selected': isSingleLayoutRegionSelected(region.region_id),
                            'is-auto-selected': Boolean(region.auto_selected),
                            'is-auto-iterated': region.auto_state === 'iterated',
                            'is-auto-skipped': region.auto_state === 'skipped',
                            'is-auto-failed': region.auto_state === 'failed',
                          },
                        ]"
                        :style="getSingleOverlayRegionDisplayStyle(region)"
                      >
                        <span v-if="isSingleLayoutRegionSelected(region.region_id) || region.auto_selected" class="ci-single-layout-region-tag">{{ getSingleOverlayRegionTagText(region) }}</span>
                      </div>
                    </div>
                  </div>
                </div>
                <div class="ci-single-preview-caption">
                  <span v-if="singleWorkAreaItem">{{ getReproductionTitle(singleWorkAreaItem) }}</span>
                  <span v-if="singleOverlayJobRunning" class="ci-r-unit-busy">覆盖层处理中…</span>
                </div>
                <div class="ci-single-history-row" v-if="singleOverlayHistory.length">
                  <button class="ci-action-btn" :disabled="singleOverlayHistoryIndex <= 0" @click="goSingleOverlayHistoryPrev">上一版</button>
                  <span class="ci-single-history-text">覆盖层历史 {{ singleOverlayHistoryIndex + 1 }}/{{ singleOverlayHistory.length }}</span>
                  <button class="ci-action-btn" :disabled="singleOverlayHistoryIndex >= singleOverlayHistory.length - 1" @click="goSingleOverlayHistoryNext">下一版</button>
                </div>
                <div v-if="singleAutoIterationLastRound" class="ci-single-auto-round-summary">
                  <div class="ci-single-auto-round-summary-head">
                    <span class="ci-single-layout-iterate-title">{{ singleAutoIterationLastRound.mode === 'full_lite' ? '最近一轮轻量识字（Qwen）' : '最近一轮自动迭代' }}</span>
                    <span v-if="singleAutoIterationLastRound.mode === 'full_lite'" class="ci-single-auto-round-summary-meta">
                      已选 {{ singleAutoIterationLastRound.selected_count || 0 }} · 失败 {{ singleAutoIterationLastRound.failed_count || 0 }}
                      <template v-if="singleWorkAreaOverlayStateItem?.lite_auto_iteration_last?.bundle_rel_path">
                        · 汇总 JSON <code>{{ singleWorkAreaOverlayStateItem.lite_auto_iteration_last.bundle_rel_path }}</code>
                      </template>
                    </span>
                    <span v-else class="ci-single-auto-round-summary-meta">已选 {{ singleAutoIterationLastRound.selected_count || 0 }} · 已迭代 {{ singleAutoIterationLastRound.iterated_count || 0 }} · 已跳过 {{ singleAutoIterationLastRound.skipped_count || 0 }}</span>
                  </div>
                  <div class="ci-single-auto-round-summary-list">
                    <div
                      v-for="item in (singleAutoIterationLastRound.selected_regions || [])"
                      :key="`auto-round-${item.region_id}`"
                      class="ci-single-auto-round-summary-item"
                      :class="`is-${item.decision || 'selected'}`"
                    >
                      <div class="ci-single-auto-round-summary-main">
                        <span>{{ item.title || item.region_id }}</span>
                        <span>{{ getSingleAutoRoundItemMeta(item) }}</span>
                      </div>
                      <div v-if="getSingleGrayQualityLabel(item)" class="ci-single-inline-hint">灰区质量：{{ getSingleGrayQualityLabel(item) }}</div>
                      <details v-if="hasSingleAutoIterationAdjudication(item)" class="ci-single-d-probe-details">
                        <summary>自检/裁判/仲裁明细</summary>
                        <div class="ci-single-d-probe-judge-card">
                          <div v-if="getSingleDRegionFinalSuggestedText(item)" class="ci-single-auto-preview-text">
                            最终建议结果：{{ getSingleDRegionFinalSuggestedText(item) }}
                          </div>
                          <details v-if="item.disagreement_adjudication?.self_checks?.length" class="ci-single-d-probe-details">
                            <summary>选手自检结果</summary>
                            <pre class="ci-single-d-probe-pre">{{ formatSingleDRegionSelfCheckDetails(item.disagreement_adjudication.self_checks) }}</pre>
                          </details>
                          <div class="ci-single-inline-hint">
                            裁判票数：1号={{ item.disagreement_adjudication?.votes?.option1 || 0 }}，
                            2号={{ item.disagreement_adjudication?.votes?.option2 || 0 }}，
                            都不对={{ item.disagreement_adjudication?.votes?.neither || 0 }}
                          </div>
                          <div class="ci-single-inline-hint">
                            最终裁判结论：{{ formatSingleDRegionJudgeFinalVote(item.disagreement_adjudication?.final_vote) }}
                          </div>
                          <div v-if="item.disagreement_adjudication?.corrected_text" class="ci-single-auto-preview-text">
                            裁判建议结果：{{ item.disagreement_adjudication.corrected_text }}
                          </div>
                          <div v-if="item.disagreement_adjudication?.arbitration?.success" class="ci-single-inline-hint">
                            仲裁结论：{{ formatSingleDRegionJudgeFinalVote(item.disagreement_adjudication.arbitration.vote) }}
                            <span v-if="item.disagreement_adjudication.arbitration.corrected_text">
                              ，建议：{{ item.disagreement_adjudication.arbitration.corrected_text }}
                            </span>
                          </div>
                          <details class="ci-single-d-probe-details">
                            <summary>查看每位裁判明细</summary>
                            <pre class="ci-single-d-probe-pre">{{ formatSingleDRegionJudgeDetails(item.disagreement_adjudication?.judges) }}</pre>
                          </details>
                        </div>
                      </details>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="ci-single-workspace-right">
              <div class="ci-single-workspace-section" v-if="singleWorkAreaItem && rContextEdits[singleWorkAreaUnitId]">
                <div class="ci-single-workspace-section-header" @click="toggleSingleWorkAreaSection('reproduction')">
                  <span class="ci-single-workspace-title">R层单图复现</span>
                  <span class="ci-expand-arrow" :class="{ expanded: isSingleWorkAreaSectionExpanded('reproduction') }">▼</span>
                </div>
                <div v-show="isSingleWorkAreaSectionExpanded('reproduction')" class="ci-single-workspace-section-body">
                <div class="ci-r-field-inline">
                  <label class="ci-r-field-label">生成模式</label>
                  <select v-model="rContextEdits[singleWorkAreaUnitId].use_sketch_input" class="ci-r-select">
                    <option :value="true">输入草图</option>
                    <option :value="false">不输入草图</option>
                  </select>
                </div>
                <div class="ci-r-field-inline" v-if="rContextEdits[singleWorkAreaUnitId].use_sketch_input">
                  <label class="ci-r-field-label">原图直出</label>
                  <label class="ci-r-inline-check">
                    <input type="checkbox" v-model="rContextEdits[singleWorkAreaUnitId].use_original_sketch_as_r" />
                    直接用原草图作为 R 层复现图（不调升维模型）
                  </label>
                </div>
                <div class="ci-r-field" v-for="field in rContextFieldDefs" :key="`workspace-${field.key}`">
                  <div class="ci-r-field-top">
                    <label class="ci-r-field-label">{{ field.label }}</label>
                  </div>
                  <textarea
                    v-if="field.editable"
                    v-model="rContextEdits[singleWorkAreaUnitId][field.key]"
                    class="ci-r-textarea"
                    :rows="field.rows"
                  ></textarea>
                  <pre v-else class="ci-r-readonly">{{ rContextEdits[singleWorkAreaUnitId][field.key] || '（空）' }}</pre>
                </div>
                <div class="ci-r-field">
                  <label class="ci-r-field-label">当前页具体修改要求</label>
                  <textarea
                    v-model="singleWorkAreaRevisionInstruction"
                    class="ci-r-textarea"
                    rows="4"
                    placeholder="已有复现图时可填写本次局部修改要求；首次生成可留空"
                  ></textarea>
                </div>
                <div class="ci-r-field">
                  <label class="ci-r-field-label">复现参考图（选填）</label>
                  <input ref="singleWorkAreaReferenceFileInput" type="file" accept="image/*" class="ci-r-file-input" @change="onSingleWorkAreaReferenceFileChange" />
                  <div class="ci-r-actions ci-r-actions-left">
                    <button type="button" class="ci-action-btn" @click="triggerSingleWorkAreaReferenceUpload">选择图片</button>
                    <button type="button" class="ci-action-btn" v-if="singleWorkAreaReferenceDataUrl" @click="clearSingleWorkAreaReferenceImage">清除</button>
                  </div>
                  <img v-if="singleWorkAreaReferenceDataUrl" :src="singleWorkAreaReferenceDataUrl" class="ci-r-reference-preview" alt="复现参考图" />
                </div>
                <div class="ci-r-field-inline">
                  <label class="ci-r-field-label">清晰度</label>
                  <select v-model="singleWorkAreaImageQuality" class="ci-r-select">
                    <option value="normal">普通</option>
                    <option value="high">高清（4K）</option>
                  </select>
                </div>
                <div class="ci-r-actions">
                  <button type="button" class="ci-action-btn" @click="saveRContextItem(singleWorkAreaItem)">保存R层字段</button>
                  <button
                    type="button"
                    class="ci-action-btn"
                    :disabled="!singleWorkAreaReproductionSrc || reproductionBusy || isUnitIterating(singleWorkAreaItem.unit_id)"
                    @click="openSingleReproductionManualDialog"
                  >编辑底图</button>
                  <button
                    type="button"
                    class="ci-action-btn ci-action-btn-primary"
                    :disabled="reproductionBusy"
                    @click="submitSingleWorkAreaReproduction"
                  >{{ singleWorkAreaItem.status === 'ready' ? '迭代当前页复现图' : '生成当前页复现图' }}</button>
                </div>
                <div class="ci-single-inline-hint">每次复现完成后，会自动进入当前页的单图迭代工作区，便于继续迭代。</div>
                </div>
              </div>

              <div class="ci-single-workspace-section">
                <div class="ci-single-workspace-section-header" @click="toggleSingleWorkAreaSection('overlay')">
                  <span class="ci-single-workspace-title">DMT覆盖层</span>
                  <span class="ci-expand-arrow" :class="{ expanded: isSingleWorkAreaSectionExpanded('overlay') }">▼</span>
                </div>
                <div v-show="isSingleWorkAreaSectionExpanded('overlay')" class="ci-single-workspace-section-body">
                <div class="ci-r-actions ci-r-actions-left">
                  <button
                    type="button"
                    class="ci-action-btn"
                    :disabled="singleOverlayHandwritingBusy || !singleWorkAreaReproductionSrc"
                    @click="runSingleOverlayHandwritingEstimate"
                  >{{ singleOverlayHandwritingBusy ? '估算中…' : '手写占比估算（Qwen）' }}</button>
                  <button type="button" class="ci-action-btn" :disabled="singleOverlayPromptStreaming || !singleWorkAreaReproductionSrc" @click="runSingleOverlayDmtPrompt">{{ singleOverlayPromptStreaming ? '生成中...' : 'DMT微版面化' }}</button>
                  <button type="button" class="ci-action-btn" :disabled="!singleWorkAreaReproductionSrc" @click="openSingleOverlayManualDialog">编辑覆盖层</button>
                </div>
                <div class="ci-single-inline-hint">建议先点「手写占比估算」：写入 overlay 后，「DMT微版面化」按占比选用粗/细 Prompt；未估算时默认细粒度（与手写≥60% 一致）。</div>
                <div class="ci-r-field-inline">
                  <label class="ci-r-field-label">生成时附带 T/M 理解文本</label>
                  <label class="ci-r-inline-check">
                    <input v-model="singleOverlayIncludeTmContext" type="checkbox" />
                    <span>{{ singleOverlayIncludeTmContext ? '开启' : '关闭' }}</span>
                  </label>
                </div>
                <div class="ci-r-field">
                  <label class="ci-r-field-label">生成覆盖层要求</label>
                  <textarea
                    v-model="singleOverlayInstructionText"
                    class="ci-r-textarea"
                    rows="8"
                    placeholder="点击 DMT微版面化 自动生成，也可手工修改后再生成覆盖层"
                  ></textarea>
                </div>
                <div class="ci-r-field">
                  <label class="ci-r-field-label">覆盖层参考图（选填）</label>
                  <input ref="singleOverlayReferenceFileInput" type="file" accept="image/*" class="ci-r-file-input" @change="onSingleOverlayReferenceFileChange" />
                  <div class="ci-r-actions ci-r-actions-left">
                    <button type="button" class="ci-action-btn" @click="triggerSingleOverlayReferenceUpload">选择图片</button>
                    <button type="button" class="ci-action-btn" v-if="singleOverlayReferenceDataUrl" @click="clearSingleOverlayReferenceImage">清除</button>
                  </div>
                  <img v-if="singleOverlayReferenceDataUrl" :src="singleOverlayReferenceDataUrl" class="ci-r-reference-preview" alt="覆盖层参考图" />
                </div>
                <div class="ci-r-field-inline">
                  <label class="ci-r-field-label">覆盖层清晰度</label>
                  <select v-model="singleOverlayImageQuality" class="ci-r-select">
                    <option value="normal">普通</option>
                    <option value="high">高清（4K）</option>
                  </select>
                </div>
                <div class="ci-r-actions">
                  <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="singleOverlayBusy || !singleWorkAreaReproductionSrc" @click="startSingleOverlayGenerate">{{ singleOverlayDataUrl ? '重新生成覆盖层' : '生成覆盖层' }}</button>
                  <button type="button" class="ci-action-btn" :disabled="singleOverlayBusy || !singleOverlayDataUrl" @click="startSingleOverlayIterate">按当前要求迭代覆盖层</button>
                </div>
                <div class="ci-single-inline-hint">覆盖层只会单独保存为 sidecar 文件，不会覆盖当前复现图。</div>
                <div class="ci-single-auto-iterate-panel">
                  <div class="ci-single-layout-iterate-title">D版面自动迭代</div>
                  <div class="ci-r-field-inline">
                    <label class="ci-r-field-label">自动迭代模式</label>
                    <select v-model="singleAutoIterationMode" class="ci-r-select">
                      <option v-for="option in singleAutoIterationModeOptions" :key="`auto-mode-${option.value}`" :value="option.value">{{ option.label }}</option>
                    </select>
                  </div>
                  <div class="ci-r-field-inline">
                    <label class="ci-r-field-label">识字前整图清晰化</label>
                    <label class="ci-r-inline-check">
                      <input v-model="singleSnippetSketchPreprocess" type="checkbox" />
                      <span>{{ singleSnippetSketchPreprocess ? '开启 handwriting_isolate 后再按 D 框裁切' : '关闭（直接用原草图裁切）' }}</span>
                    </label>
                  </div>
                  <div class="ci-r-field-inline">
                    <label class="ci-r-field-label">识字注入上下文</label>
                    <label class="ci-r-inline-check">
                      <input v-model="singleSnippetUseRecognitionContext" type="checkbox" />
                      <span>{{ singleSnippetUseRecognitionContext ? '开启（card/doc/候选词表）' : '关闭（两模型不输入任何上下文）' }}</span>
                    </label>
                  </div>
                  <div class="ci-single-inline-hint">{{ singleAutoIterationHint }}</div>
                  <div class="ci-single-layout-summary">{{ singleAutoIterationSelectionSummary }}</div>
                  <div v-if="singleAutoIterationStartOptions.length" class="ci-single-auto-chip-list">
                    <button
                      v-for="region in singleAutoIterationStartOptions"
                      :key="`auto-chip-${region.region_id}`"
                      type="button"
                      class="ci-single-layout-chip"
                      :class="[
                        'is-d',
                        { 'is-selected': isSingleAutoIterationRegionSelected(region.region_id) },
                      ]"
                      :disabled="!singleOverlayViewingCurrent || (!isSingleAutoIterationRegionSelected(region.region_id) && !canSelectSingleAutoIterationRegion(region))"
                      @click="toggleSingleAutoIterationRegion(region)"
                    >
                      <span>{{ region.title || region.region_id }}</span>
                      <span class="ci-single-layout-chip-meta">{{ formatSingleLayoutRegionPosition(region) }}</span>
                    </button>
                  </div>
                  <div v-else class="ci-single-layout-empty">当前覆盖层尚未解析出可用的 D 版面，请先生成或修正覆盖层。</div>
                  <div v-if="singleAutoIterationStartOptions.length" class="ci-r-field-inline ci-single-d-probe-row">
                    <label class="ci-r-field-label">单区识字核查</label>
                    <select v-model="singleDRegionProbeRegionId" class="ci-r-select">
                      <option value="">选择 D 版面…</option>
                      <option
                        v-for="region in singleAutoIterationStartOptions"
                        :key="`d-probe-${region.region_id}`"
                        :value="region.region_id"
                      >{{ region.title || region.region_id }} · {{ formatSingleLayoutRegionPosition(region) }}</option>
                    </select>
                    <button
                      type="button"
                      class="ci-action-btn"
                      :disabled="singleDRegionProbeBusy || !singleDRegionProbeRegionId || !singleOverlayViewingCurrent"
                      @click="runSingleDRegionRecognitionProbe"
                    >{{ singleDRegionProbeBusy ? '识别中…' : '双模型识别并预览' }}</button>
                    <select v-model="singleDRegionConfidenceModel" class="ci-r-select" :disabled="singleDRegionConfidenceBusy">
                      <option value="qwen">Qwen3.6-plus（逐区）</option>
                      <option value="gemini">Gemini-3.1-pro-preview（10区/批）</option>
                    </select>
                    <button
                      type="button"
                      class="ci-action-btn"
                      :disabled="singleDRegionConfidenceBusy || !singleOverlayViewingCurrent || !singleAutoIterationStartOptions.length"
                      @click="runSingleDRegionConfidenceBatch"
                    >{{ singleDRegionConfidenceBusy ? '评估中…' : `D区识别置信度评估(${singleDRegionConfidenceModel === 'gemini' ? 'Gemini' : 'Qwen'})` }}</button>
                  </div>
                  <div v-if="singleDRegionConfidenceResultPath" class="ci-single-inline-hint">
                    结果文件：<code>{{ singleDRegionConfidenceResultPath }}</code>
                  </div>
                  <div v-if="singleDRegionConfidenceResults.length" class="ci-r-field">
                    <label class="ci-r-field-label">D区字迹识别置信度结果</label>
                    <div class="ci-r-field-inline">
                      <label class="ci-r-field-label">排序方式</label>
                      <select v-model="singleDRegionConfidenceSortOrder" class="ci-r-select">
                        <option value="asc">按置信度升序</option>
                        <option value="desc">按置信度降序</option>
                      </select>
                    </div>
                    <textarea class="ci-r-textarea" rows="8" :value="singleDRegionConfidenceSummaryText" readonly></textarea>
                  </div>
                  <div v-if="singleAutoIterationStartOptions.length" class="ci-single-inline-hint">识别结果追加写入分析目录下 <code>ci_audit/d_region_recognition_audit.jsonl</code>（与自动预览/迭代共用同一审计文件）。</div>
                  <div v-if="singleDmtCoarseLayoutEligible" class="ci-single-inline-hint">整图手写面积估算占比：{{ formatSingleHandwritingRatio }}（&lt;60% 时一般为粗粒度红框，并可选用下方「轻量全自动」）。</div>
                  <div class="ci-single-inline-hint" v-if="singleAutoIterationMode === 'semi' && selectedSingleAutoIterationRegions.length">半自动模式会先识别本轮白/灰/黑区，再用一个总弹窗汇总灰区供你确认。</div>
                  <div class="ci-single-inline-hint" v-else-if="singleAutoIterationMode === 'full_lite'">轻量全自动须先在上方勾选 D 版面；仅对所选调区运行 Qwen 识字与自检并保存 JSON，不修改当前 R 层复现图。再次提交时只覆盖本轮勾选的 D 区，其余已保存区保留（可单独迭代不满意的版面）。</div>
                  <div class="ci-single-inline-hint" v-else-if="singleAutoIterationMode === 'full' && singleAutoIterationUsesManualSelection">已启用手动选择，全自动会直接处理所选 D 版面，不走游标。</div>
                  <div class="ci-r-field-inline" v-if="singleAutoIterationMode === 'full' && !singleAutoIterationUsesManualSelection">
                    <label class="ci-r-field-label">继续上一轮游标</label>
                    <label class="ci-r-inline-check">
                      <input v-model="singleAutoIterationContinueFromCursor" type="checkbox" />
                      <span>{{ singleAutoIterationContinueFromCursor ? '开启' : '关闭' }}</span>
                    </label>
                  </div>
                  <div v-if="singleAutoIterationMode === 'full' && !singleAutoIterationUsesManualSelection && !singleAutoIterationContinueFromCursor" class="ci-r-field-inline">
                    <label class="ci-r-field-label">起始D版面</label>
                    <select v-model="singleAutoIterationStartRegionId" class="ci-r-select">
                      <option v-for="region in singleAutoIterationStartOptions" :key="`auto-start-${region.region_id}`" :value="region.region_id">{{ region.title || region.region_id }} · {{ formatSingleLayoutRegionPosition(region) }}</option>
                    </select>
                  </div>
                  <div v-if="singleLiteFollowupReady" class="ci-r-field">
                    <label class="ci-r-field-label">轻量识字后续</label>
                    <div class="ci-r-actions ci-r-actions-wrap">
                      <button
                        type="button"
                        class="ci-action-btn ci-action-btn-primary"
                        :disabled="isApplyLiteBundleRunning || reproductionBusy || !singleOverlayViewingCurrent || !singleWorkAreaReproductionSrc"
                        @click="submitApplyLiteBundleToReproduction"
                      >{{ isApplyLiteBundleRunning ? '贴补中…' : '用轻量识字迭代当前 R 层复现图' }}</button>
                      <button type="button" class="ci-action-btn" :disabled="singleReproRefineBusy || !singleOverlayViewingCurrent" @click="openSingleDLiteRefineModelDialog('t_layer')">
                        {{ singleReproRefineBusy ? '处理中…' : '预览：按轻量 D 校正整体纪要(T)' }}
                      </button>
                      <button type="button" class="ci-action-btn" :disabled="singleReproRefineBusy || !singleOverlayViewingCurrent" @click="openSingleDLiteUnderstandingPreviewEntry">
                        {{ singleReproRefineBusy ? '处理中…' : singleDLiteUnderstandingPreviewButtonLabel }}
                      </button>
                    </div>
                    <div class="ci-single-inline-hint">依赖 <code>d_region_lite_recognition_*.json</code>（多次轻量提交按 D 区合并，非整文件覆盖）；三层确认写入仍走 diff 与原向量库路径。</div>
                  </div>
                  <div class="ci-r-actions">
                    <button type="button" class="ci-action-btn" v-if="selectedSingleAutoIterationRegions.length" @click="clearSingleAutoIterationSelections">清空所选 D 版面</button>
                    <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="!canSubmitSingleAutoIteration" @click="submitSingleAutoIterationRound">{{ singleAutoIterationButtonLabel }}</button>
                    <button
                      type="button"
                      class="ci-action-btn"
                      :disabled="singleDRegionConfidenceBusy || reproductionBusy || !singleOverlayViewingCurrent"
                      @click="runAutoIterateByLowestConfidence"
                    >按最低置信度自动选前9</button>
                    <button
                      type="button"
                      class="ci-action-btn ci-action-btn-primary"
                      :disabled="singleGlobalWorkflowRunning || reproductionBusy || !singleOverlayViewingCurrent || !singleWorkAreaReproductionSrc"
                      @click="runSingleGlobalAutoWorkflow"
                    >{{ singleGlobalWorkflowRunning ? '全流程执行中…' : '一键全流程自动执行' }}</button>
                  </div>
                  <div v-if="singleGlobalWorkflowRunning || singleGlobalWorkflowProgress > 0" class="ci-r-field">
                    <label class="ci-r-field-label">全流程进度：{{ singleGlobalWorkflowProgress }}%</label>
                    <div class="ci-progress-track"><div class="ci-progress-fill" :style="{ width: `${singleGlobalWorkflowProgress}%` }"></div></div>
                    <div class="ci-single-inline-hint">{{ singleGlobalWorkflowStatus }}</div>
                  </div>
                </div>
                <div class="ci-single-layout-iterate-panel">
                  <div class="ci-single-layout-iterate-title">按版面定向迭代当前复现图</div>
                  <div class="ci-r-field-inline">
                    <label class="ci-r-field-label">迭代模式</label>
                    <select v-model="singleLayoutIterationMode" class="ci-r-select">
                      <option v-for="option in singleLayoutIterationModeOptions" :key="`layout-mode-${option.value}`" :value="option.value">{{ option.label }}</option>
                    </select>
                  </div>
                  <div class="ci-single-inline-hint">{{ singleLayoutIterationMode === 'crop' ? '局部裁切模式只允许选择一个现有 D/M/T 版面；后端会裁切该局部、生成同尺寸局部图，再拼回当前复现图。' : '可在左侧图中点选版面，也可在下方列表中选择。D级最多3个，M级最多2个，T级最多1个；会沿用上方复现参考图与清晰度设置。' }}</div>
                  <div v-if="!singleOverlayRegions.length" class="ci-single-layout-empty">当前覆盖层尚未解析出可迭代版面，请先生成或手工修正覆盖层。</div>
                  <div v-else-if="!singleOverlayViewingCurrent" class="ci-single-layout-empty">当前正在查看历史覆盖层，请切回最新一版后再选择版面。</div>
                  <template v-else>
                    <div class="ci-single-layout-summary">{{ singleLayoutRegionSelectionSummary }}</div>
                    <div class="ci-single-layout-groups">
                      <div v-for="group in singleOverlayRegionGroups" :key="`layout-group-${group.level}`" class="ci-single-layout-group">
                        <div class="ci-single-layout-group-header ci-single-layout-group-toggle" @click="toggleSingleLayoutRegionGroup(group.level)">
                          <div class="ci-single-layout-group-info">
                            <span class="ci-single-layout-level-badge" :class="`is-${group.level}`">{{ group.label }}</span>
                            <span>{{ group.selectedCount }}/{{ group.limitLabel }}</span>
                          </div>
                          <span class="ci-expand-arrow" :class="{ expanded: isSingleLayoutRegionGroupExpanded(group.level) }">▼</span>
                        </div>
                        <div v-show="isSingleLayoutRegionGroupExpanded(group.level)" class="ci-single-layout-group-body">
                          <div class="ci-single-layout-chip-list">
                          <button
                            v-for="region in group.items"
                            :key="`layout-chip-${region.region_id}`"
                            type="button"
                            class="ci-single-layout-chip"
                            :class="[
                              `is-${region.level || 'd'}`,
                              { 'is-selected': region.draft?.selected },
                            ]"
                            :disabled="!region.draft?.selected && !canSelectSingleLayoutRegion(region)"
                            @click="toggleSingleLayoutRegion(region)"
                          >
                            <span>{{ region.title || region.region_id }}</span>
                            <span class="ci-single-layout-chip-meta">{{ getSingleLayoutRegionMetaText(region) }}</span>
                          </button>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div v-if="selectedSingleLayoutRegions.length" class="ci-single-layout-editors">
                      <div v-for="region in selectedSingleLayoutRegions" :key="`layout-editor-${region.region_id}`" class="ci-single-layout-editor-card">
                        <div class="ci-single-layout-editor-head">
                          <div class="ci-single-layout-editor-title-row">
                            <span class="ci-single-layout-level-badge" :class="`is-${region.level}`">{{ region.title || region.region_id }}</span>
                            <span class="ci-single-layout-editor-pos">{{ formatSingleLayoutRegionPosition(region) }}</span>
                          </div>
                          <button type="button" class="ci-link-btn" @click="toggleSingleLayoutRegion(region)">取消选择</button>
                        </div>
                        <div class="ci-r-field-inline">
                          <label class="ci-r-field-label">辨识度属性</label>
                          <select v-model="region.draft.recognition" class="ci-r-select">
                            <option v-for="option in singleLayoutRecognitionOptions" :key="`rec-${region.region_id}-${option.value}`" :value="option.value">{{ option.label }}</option>
                          </select>
                        </div>
                        <div v-if="getSingleLayoutRegionEditorHint(region)" class="ci-single-inline-hint">{{ getSingleLayoutRegionEditorHint(region) }}</div>
                        <div class="ci-r-field">
                          <label class="ci-r-field-label">版面级修改指令</label>
                          <textarea
                            v-model="region.draft.user_instruction"
                            class="ci-r-textarea"
                            rows="3"
                            placeholder="选填；留空时系统会结合当前页理解与本子上下文自动补全这一版面的迭代意图"
                          ></textarea>
                        </div>
                      </div>
                    </div>
                    <div v-else class="ci-single-layout-empty">尚未选择版面。可直接点击左侧图中的框区，或在上方列表中选择。</div>
                    <div class="ci-r-actions">
                      <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="!canSubmitSingleLayoutRegionIterate" @click="submitSingleLayoutRegionIterate">按所选版面迭代当前复现图</button>
                    </div>
                    <div class="ci-single-inline-hint">{{ singleLayoutRegionSubmitHint }}</div>
                  </template>
                </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 必须在「单图迭代工作区」之后渲染：同属 ci-layout-overlay z-index:3000 时，后出现的层叠在上，否则工作区会挡住预览弹窗的点击 -->
      <div class="ci-layout-overlay" v-if="singleImageUnderstandingPreviewDialogVisible" @click.self="cancelSingleRefineImageUnderstanding">
        <div class="ci-layout-dialog ci-single-auto-dialog">
          <div class="ci-layout-header">
            <span>{{ singleImageUnderstandingPreviewKind === 'd_lite' ? '三层理解（轻量 D 识字·预览确认）' : '更新完善原图片三层理解（预览确认）' }}</span>
            <div class="ci-close-btn" @click="cancelSingleRefineImageUnderstanding">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-auto-dialog-body">
            <div class="ci-single-inline-hint">{{ singleImageUnderstandingPreviewKind === 'd_lite' ? `依据轻量 D 区识字汇总与原草图生成预览；区分表单预置印刷信息与用户手写记录，细节尽量保留。确认后写入向量库（路径与原有「按 R 层预览」相同）。${singleDLiteRefineModelUsedName ? ` 预览模型：${singleDLiteRefineModelUsedName}` : ''}` : '先预览结果，确认后才会写入原图片三层理解并更新向量库。' }}</div>
            <div class="ci-single-inline-hint">前后 diff（仅变化段高亮）：</div>
            <div class="ci-single-diff-panel" v-html="renderSingleUnderstandingDiffHtml()"></div>
            <textarea
              v-model="singleImageUnderstandingPreviewText"
              class="ci-r-textarea"
              rows="16"
              placeholder="暂无预览内容"
            ></textarea>
          </div>
          <div class="ci-r-actions ci-single-auto-dialog-actions">
            <button type="button" class="ci-action-btn" :disabled="singleReproRefineBusy" @click="cancelSingleRefineImageUnderstanding">取消</button>
            <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="singleReproRefineBusy || !singleImageUnderstandingPreviewText.trim()" @click="confirmSingleRefineImageUnderstanding">
              {{ singleReproRefineBusy ? '确认中…' : '确认并更新向量库' }}
            </button>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleDLiteRefineModelDialogVisible" @click.self="cancelSingleDLiteRefineModelDialog">
        <div class="ci-layout-dialog ci-single-auto-dialog">
          <div class="ci-layout-header">
            <span>选择预览模型</span>
            <div class="ci-close-btn" @click="cancelSingleDLiteRefineModelDialog">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-auto-dialog-body">
            <div class="ci-single-inline-hint">
              {{ singleDLiteRefineModelPendingAction === 't_layer'
                ? '将依据轻量 D 区识字汇总与原草图，预览迭代整体纪要(T)。'
                : '将依据轻量 D 区识字汇总与原草图，预览迭代三层理解。' }}
            </div>
            <div class="ci-r-field-inline">
              <label class="ci-r-field-label">预览模型</label>
              <select v-model="singleDLiteRefineModelChoice" class="ci-r-select">
                <option value="gemini">Gemini · gemini-3.1-pro-preview</option>
                <option value="qwen">Qwen · qwen3.6-plus</option>
              </select>
            </div>
          </div>
          <div class="ci-r-actions ci-single-auto-dialog-actions">
            <button type="button" class="ci-action-btn" :disabled="singleReproRefineBusy" @click="cancelSingleDLiteRefineModelDialog">取消</button>
            <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="singleReproRefineBusy" @click="confirmSingleDLiteRefineModelAndPreview">
              {{ singleReproRefineBusy ? '生成预览中…' : '确认并开始预览' }}
            </button>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleTLayerFromDLiteDialogVisible" @click.self="cancelSingleTLayerFromDLiteDialog">
        <div class="ci-layout-dialog ci-single-auto-dialog">
          <div class="ci-layout-header">
            <span>整体纪要 T 层（轻量 D 识字·预览确认）</span>
            <div class="ci-close-btn" @click="cancelSingleTLayerFromDLiteDialog">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-auto-dialog-body">
            <div class="ci-single-inline-hint">依据轻量 D 区识字汇总与原草图生成；区分表单预置印刷信息与用户手写记录，具体措辞尽量完整保留。确认后写入「当前分析」的 T 层文件（与右键「按 R 层更新 T」为不同入口）。<span v-if="singleDLiteRefineModelUsedName"> 预览模型：{{ singleDLiteRefineModelUsedName }}</span></div>
            <div class="ci-single-inline-hint">前后 diff（仅变化段高亮）：</div>
            <div class="ci-single-diff-panel" v-html="renderSingleTLayerFromDLiteDiffHtml()"></div>
            <textarea
              v-model="singleTLayerFromDLitePreviewText"
              class="ci-r-textarea"
              rows="16"
              placeholder="暂无预览内容"
            ></textarea>
          </div>
          <div class="ci-r-actions ci-single-auto-dialog-actions">
            <button type="button" class="ci-action-btn" :disabled="singleReproRefineBusy" @click="cancelSingleTLayerFromDLiteDialog">取消</button>
            <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="singleReproRefineBusy || !singleTLayerFromDLitePreviewText.trim()" @click="confirmSingleTLayerFromDLiteApply">
              {{ singleReproRefineBusy ? '确认中…' : '确认写入 T 层' }}
            </button>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleAutoIterationGrayDialogVisible" @click.self="closeSingleAutoIterationGrayDialog">
        <div class="ci-layout-dialog ci-single-auto-dialog">
          <div class="ci-layout-header">
            <span>灰区汇总确认</span>
            <div class="ci-close-btn" @click="closeSingleAutoIterationGrayDialog">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-auto-dialog-body">
            <div class="ci-single-inline-hint">
              本轮共选 {{ singleAutoIterationPreviewData?.selected_count || 0 }} 个 D 版面，其中灰区 {{ singleAutoIterationPreviewData?.gray_count || 0 }} 个，识别失败 {{ singleAutoIterationPreviewData?.failed_count || 0 }} 个。
            </div>
            <div class="ci-single-auto-preview-list">
              <div
                v-for="item in singleAutoIterationPreviewSelectedRegions"
                :key="`auto-preview-${item.region_id}`"
                class="ci-single-auto-preview-card"
                :class="`is-${normalizeSingleRecognition(item.recognition) || 'unknown'}`"
              >
                <div class="ci-single-auto-preview-head">
                  <div class="ci-single-auto-preview-title-row">
                    <span class="ci-single-layout-level-badge is-d">{{ item.title || item.region_id }}</span>
                    <span class="ci-single-auto-preview-meta">{{ getSingleRecognitionLabel(item.recognition) || '待确认' }}</span>
                  </div>
                  <span class="ci-single-auto-preview-meta">{{ formatSingleLayoutRegionPosition(item) }}</span>
                </div>
                <div v-if="item.recognized_text" class="ci-single-auto-preview-text">识别结果：{{ item.recognized_text }}</div>
                <div v-if="item.recognition_reason" class="ci-single-inline-hint">判定说明：{{ item.recognition_reason }}</div>
                <div class="ci-single-auto-model-list" v-if="getSingleAutoIterationModelText(item, 'gemini') || getSingleAutoIterationModelText(item, 'qwen')">
                  <div v-if="getSingleAutoIterationModelText(item, 'gemini')" class="ci-single-auto-model-item">
                    <span class="ci-single-auto-model-label">Gemini</span>
                    <span>{{ getSingleAutoIterationModelText(item, 'gemini') }}</span>
                  </div>
                  <div v-if="getSingleAutoIterationModelText(item, 'qwen')" class="ci-single-auto-model-item">
                    <span class="ci-single-auto-model-label">Qwen</span>
                    <span>{{ getSingleAutoIterationModelText(item, 'qwen') }}</span>
                  </div>
                </div>
                <div v-if="getSingleGrayQualityLabel(item)" class="ci-single-inline-hint">灰区质量：{{ getSingleGrayQualityLabel(item) }}</div>
                <details v-if="hasSingleAutoIterationAdjudication(item)" class="ci-single-d-probe-details">
                  <summary>自检/裁判/仲裁明细</summary>
                  <div class="ci-single-d-probe-judge-card">
                    <div v-if="getSingleDRegionFinalSuggestedText(item)" class="ci-single-auto-preview-text">
                      最终建议结果：{{ getSingleDRegionFinalSuggestedText(item) }}
                    </div>
                    <details v-if="item.disagreement_adjudication?.self_checks?.length" class="ci-single-d-probe-details">
                      <summary>选手自检结果</summary>
                      <pre class="ci-single-d-probe-pre">{{ formatSingleDRegionSelfCheckDetails(item.disagreement_adjudication.self_checks) }}</pre>
                    </details>
                    <div class="ci-single-inline-hint">
                      裁判票数：1号={{ item.disagreement_adjudication?.votes?.option1 || 0 }}，
                      2号={{ item.disagreement_adjudication?.votes?.option2 || 0 }}，
                      都不对={{ item.disagreement_adjudication?.votes?.neither || 0 }}
                    </div>
                    <div class="ci-single-inline-hint">
                      最终裁判结论：{{ formatSingleDRegionJudgeFinalVote(item.disagreement_adjudication?.final_vote) }}
                    </div>
                    <div v-if="item.disagreement_adjudication?.corrected_text" class="ci-single-auto-preview-text">
                      裁判建议结果：{{ item.disagreement_adjudication.corrected_text }}
                    </div>
                    <div v-if="item.disagreement_adjudication?.arbitration?.success" class="ci-single-inline-hint">
                      仲裁结论：{{ formatSingleDRegionJudgeFinalVote(item.disagreement_adjudication.arbitration.vote) }}
                      <span v-if="item.disagreement_adjudication.arbitration.corrected_text">
                        ，建议：{{ item.disagreement_adjudication.arbitration.corrected_text }}
                      </span>
                    </div>
                    <details class="ci-single-d-probe-details">
                      <summary>查看每位裁判明细</summary>
                      <pre class="ci-single-d-probe-pre">{{ formatSingleDRegionJudgeDetails(item.disagreement_adjudication?.judges) }}</pre>
                    </details>
                  </div>
                </details>
                <template v-if="normalizeSingleRecognition(item.recognition) === 'gray' && singleAutoIterationGrayDrafts[item.region_id]">
                  <div class="ci-r-field-inline">
                    <label class="ci-r-field-label">灰区处理方式</label>
                    <select v-model="singleAutoIterationGrayDrafts[item.region_id].choice_type" class="ci-r-select">
                      <option v-for="option in singleAutoIterationGrayChoiceOptions" :key="`gray-choice-${item.region_id}-${option.value}`" :value="option.value">{{ option.label }}</option>
                    </select>
                  </div>
                  <div v-if="singleAutoIterationGrayDrafts[item.region_id].choice_type === 'manual'" class="ci-r-field">
                    <label class="ci-r-field-label">手动目标文字</label>
                    <textarea
                      v-model="singleAutoIterationGrayDrafts[item.region_id].target_text"
                      class="ci-r-textarea"
                      rows="3"
                      placeholder="请输入该灰区应改成的目标文字"
                    ></textarea>
                  </div>
                  <div v-else class="ci-single-inline-hint">本轮执行文字：{{ getSingleAutoIterationGrayResolvedText(item) || '（空）' }}</div>
                </template>
                <div v-else-if="normalizeSingleRecognition(item.recognition) === 'white'" class="ci-single-inline-hint">白区会直接改成清晰、规整的标准印刷体。</div>
                <div v-else-if="normalizeSingleRecognition(item.recognition) === 'black'" class="ci-single-inline-hint">黑区会以原始草图局部作为唯一笔迹来源，保留笔迹、线条和轮廓痕迹。</div>
                <div v-else-if="item.recognition_error" class="ci-single-inline-hint">识别失败：{{ item.recognition_error }}</div>
              </div>
            </div>
            <div v-if="singleAutoIterationPreviewFailedRegions.length" class="ci-single-auto-preview-failed">
              <div class="ci-single-auto-preview-failed-title">识别失败区域</div>
              <div class="ci-single-auto-preview-failed-list">
                <div v-for="item in singleAutoIterationPreviewFailedRegions" :key="`auto-preview-failed-${item.region_id}`" class="ci-single-auto-preview-failed-item">
                  <span>{{ item.title || item.region_id }}</span>
                  <span>{{ item.error || 'model_recognition_failed' }}</span>
                </div>
              </div>
            </div>
          </div>
          <div class="ci-r-actions ci-single-auto-dialog-actions">
            <button type="button" class="ci-action-btn" @click="closeSingleAutoIterationGrayDialog">取消</button>
            <button type="button" class="ci-action-btn ci-action-btn-primary" @click="confirmSingleAutoIterationGrayDialog">确认并加入队列</button>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleDRegionProbeDialogVisible" @click.self="closeSingleDRegionProbeDialog">
        <div class="ci-layout-dialog ci-single-auto-dialog">
          <div class="ci-layout-header">
            <span>D 版面双模型识字</span>
            <div class="ci-close-btn" @click="closeSingleDRegionProbeDialog">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-auto-dialog-body">
            <div v-if="singleDRegionProbeAuditPath" class="ci-single-inline-hint">审计日志（服务端路径）：{{ singleDRegionProbeAuditPath }}</div>
            <div
              v-if="singleDRegionProbeDialogPayload"
              class="ci-single-auto-preview-card"
              :class="`is-${normalizeSingleRecognition(singleDRegionProbeDialogPayload.recognition) || 'unknown'}`"
            >
              <div class="ci-single-auto-preview-head">
                <div class="ci-single-auto-preview-title-row">
                  <span class="ci-single-layout-level-badge is-d">{{ singleDRegionProbeRegionId }}</span>
                  <span class="ci-single-auto-preview-meta">{{ getSingleRecognitionLabel(singleDRegionProbeDialogPayload.recognition) || '—' }}</span>
                </div>
              </div>
              <div v-if="singleDRegionProbeDialogPayload.recognized_text" class="ci-single-auto-preview-text">采纳结果：{{ singleDRegionProbeDialogPayload.recognized_text }}</div>
              <div v-if="singleDRegionProbeDialogPayload.recognition_reason" class="ci-single-inline-hint">判定说明：{{ singleDRegionProbeDialogPayload.recognition_reason }}</div>
              <div v-if="singleDRegionProbeDialogPayload.recognition_error" class="ci-single-inline-hint">错误：{{ singleDRegionProbeDialogPayload.recognition_error }}</div>
              <div class="ci-single-auto-model-list" v-if="getSingleDRegionProbeModelLine('gemini') || getSingleDRegionProbeModelLine('qwen')">
                <div v-if="getSingleDRegionProbeModelLine('gemini')" class="ci-single-auto-model-item">
                  <span class="ci-single-auto-model-label">Gemini</span>
                  <span>{{ getSingleDRegionProbeModelLine('gemini') }}</span>
                </div>
                <div v-if="getSingleDRegionProbeModelLine('qwen')" class="ci-single-auto-model-item">
                  <span class="ci-single-auto-model-label">Qwen</span>
                  <span>{{ getSingleDRegionProbeModelLine('qwen') }}</span>
                </div>
              </div>
              <details v-if="singleDRegionProbeDialogPayload.disagreement_adjudication?.self_checks?.length" class="ci-single-d-probe-details">
                <summary>选手自检结果</summary>
                <pre class="ci-single-d-probe-pre">{{ formatSingleDRegionSelfCheckDetails(singleDRegionProbeDialogPayload.disagreement_adjudication.self_checks) }}</pre>
              </details>
              <details v-if="getSingleDRegionProbeReasoningPreview()" class="ci-single-d-probe-details">
                <summary>模型原始推理片段（节选）</summary>
                <pre class="ci-single-d-probe-pre">{{ getSingleDRegionProbeReasoningPreview() }}</pre>
              </details>
              <div v-if="singleDRegionProbeDialogPayload.disagreement_adjudication" class="ci-single-d-probe-judge-card">
                <div class="ci-single-d-probe-judge-title">分歧裁判（盲选）</div>
                <div class="ci-single-inline-hint">
                  裁判票数：1号={{ singleDRegionProbeDialogPayload.disagreement_adjudication.votes?.option1 || 0 }}，
                  2号={{ singleDRegionProbeDialogPayload.disagreement_adjudication.votes?.option2 || 0 }}，
                  都不对={{ singleDRegionProbeDialogPayload.disagreement_adjudication.votes?.neither || 0 }}
                </div>
                <div class="ci-single-inline-hint">最终裁判结论：{{ formatSingleDRegionJudgeFinalVote(singleDRegionProbeDialogPayload.disagreement_adjudication.final_vote) }}</div>
                <div v-if="singleDRegionProbeDialogPayload.disagreement_adjudication.corrected_text" class="ci-single-auto-preview-text">
                  裁判建议结果：{{ singleDRegionProbeDialogPayload.disagreement_adjudication.corrected_text }}
                </div>
                <div v-if="getSingleDRegionFinalSuggestedText(singleDRegionProbeDialogPayload)" class="ci-single-auto-preview-text">
                  最终建议结果：{{ getSingleDRegionFinalSuggestedText(singleDRegionProbeDialogPayload) }}
                </div>
                <div v-if="singleDRegionProbeDialogPayload.disagreement_adjudication.arbitration?.success" class="ci-single-inline-hint">
                  仲裁结论：{{ formatSingleDRegionJudgeFinalVote(singleDRegionProbeDialogPayload.disagreement_adjudication.arbitration.vote) }}
                  <span v-if="singleDRegionProbeDialogPayload.disagreement_adjudication.arbitration.corrected_text">
                    ，建议：{{ singleDRegionProbeDialogPayload.disagreement_adjudication.arbitration.corrected_text }}
                  </span>
                </div>
                <details class="ci-single-d-probe-details">
                  <summary>查看每位裁判明细</summary>
                  <pre class="ci-single-d-probe-pre">{{ formatSingleDRegionJudgeDetails(singleDRegionProbeDialogPayload.disagreement_adjudication.judges) }}</pre>
                </details>
              </div>
            </div>
          </div>
          <div class="ci-r-actions ci-single-auto-dialog-actions">
            <button type="button" class="ci-action-btn ci-action-btn-primary" @click="closeSingleDRegionProbeDialog">关闭</button>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleDRegionProbeConfirmVisible" @click.self="cancelSingleDRegionRecognitionProbe">
        <div class="ci-layout-dialog ci-single-auto-dialog">
          <div class="ci-layout-header">
            <span>D 版面识字前确认</span>
            <div class="ci-close-btn" @click="cancelSingleDRegionRecognitionProbe">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-auto-dialog-body">
            <div class="ci-single-inline-hint">请确认下图就是将要输入给 Gemini/Qwen 的识字裁切图，确认后才会调用双模型识别。</div>
            <div class="ci-single-inline-hint">上下文注入：{{ singleSnippetUseRecognitionContext ? '开启' : '关闭' }}</div>
            <img
              v-if="singleDRegionProbeCropPreviewDataUrl"
              :src="singleDRegionProbeCropPreviewDataUrl"
              class="ci-single-d-probe-crop-preview"
              alt="识字裁切图预览"
            />
          </div>
          <div class="ci-r-actions ci-single-auto-dialog-actions">
            <button type="button" class="ci-action-btn" @click="cancelSingleDRegionRecognitionProbe">取消</button>
            <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="singleDRegionProbeBusy" @click="confirmSingleDRegionRecognitionProbe">
              {{ singleDRegionProbeBusy ? '识别中…' : '确认并开始识别' }}
            </button>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleReproductionManualDialogVisible" @click.self="closeSingleReproductionManualDialog">
        <div class="ci-layout-dialog ci-single-overlay-editor-dialog">
          <div class="ci-layout-header">
            <span>🖍 编辑当前复现图底图</span>
            <div class="ci-close-btn" @click="closeSingleReproductionManualDialog">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-overlay-editor-body">
            <div class="ci-single-overlay-editor-toolbar">
              <button type="button" class="ci-tool-btn" :class="{ active: singleReproductionManualTool === 'line' }" @click="activateSingleReproductionManualTool('line')">直线</button>
              <button type="button" class="ci-tool-btn" :class="{ active: singleReproductionManualTool === 'arrow' }" @click="activateSingleReproductionManualTool('arrow')">箭头直线</button>
              <button type="button" class="ci-tool-btn" :class="{ active: singleReproductionManualTool === 'erase' }" @click="activateSingleReproductionManualTool('erase')">擦除</button>
              <div class="ci-single-editor-meta" v-if="singleReproductionManualTool !== 'erase'">
                <span>颜色</span>
                <input v-model="singleReproductionManualStrokeColor" class="ci-tool-color" type="color" />
              </div>
              <div class="ci-single-editor-meta">
                <span>{{ singleReproductionManualTool === 'erase' ? '擦除半径' : '线宽' }}</span>
                <input v-model.number="singleReproductionManualStrokeWidth" class="ci-tool-range-compact" type="range" min="2" max="48" step="1" />
                <span>{{ singleReproductionManualStrokeWidth }}px</span>
              </div>
              <div class="ci-single-editor-meta">
                <span>缩放</span>
                <input v-model.number="singleReproductionManualZoom" class="ci-tool-range-compact" type="range" min="1" max="4" step="0.1" />
                <span>{{ singleReproductionManualZoom.toFixed(1) }}x</span>
              </div>
              <div class="ci-single-editor-meta ci-single-editor-meta-note">
                <span>这里只改当前复现图，不会触碰 DMT 覆盖层 sidecar。</span>
              </div>
              <button type="button" class="ci-action-btn" :disabled="singleReproductionManualUndoStack.length === 0" @click="undoSingleReproductionManual">撤销</button>
            </div>
            <div ref="singleReproductionManualStageWrap" class="ci-single-overlay-editor-stage-wrap">
              <div
                class="ci-single-overlay-editor-stage"
                :style="{ width: (singleReproductionManualDisplayBaseWidth * singleReproductionManualZoom) + 'px', height: (singleReproductionManualDisplayBaseHeight * singleReproductionManualZoom) + 'px', cursor: getSingleReproductionManualStageCursor() }"
                @mousedown.prevent="onSingleReproductionManualMouseDown"
                @mousemove.prevent="onSingleReproductionManualMouseMove"
                @mouseup.prevent="onSingleReproductionManualMouseUp"
                @mouseleave.prevent="onSingleReproductionManualMouseUp"
              >
                <canvas
                  ref="singleReproductionManualCanvas"
                  class="ci-single-overlay-editor-canvas ci-single-reproduction-editor-canvas"
                  :style="{ width: '100%', height: '100%' }"
                ></canvas>
              </div>
            </div>
          </div>
          <div class="ci-r-actions ci-single-editor-actions">
            <button type="button" class="ci-action-btn" @click="closeSingleReproductionManualDialog">取消</button>
            <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="singleReproductionManualSaving" @click="confirmSingleReproductionManualEdit">保存到当前底图</button>
          </div>
        </div>
      </div>

      <div class="ci-layout-overlay" v-if="singleOverlayManualDialogVisible" @click.self="closeSingleOverlayManualDialog">
        <div class="ci-layout-dialog ci-single-overlay-editor-dialog">
          <div class="ci-layout-header">
            <span>✏️ 编辑 DMT 覆盖层</span>
            <div class="ci-close-btn" @click="closeSingleOverlayManualDialog">&times;</div>
          </div>
          <div class="ci-layout-body ci-single-overlay-editor-body">
            <div class="ci-single-overlay-editor-toolbar">
              <button type="button" class="ci-tool-btn" :class="{ active: singleOverlayManualTool === 'select' }" @click="activateSingleOverlayManualTool('select')">编辑已有框</button>
              <button type="button" class="ci-tool-btn" :class="{ active: singleOverlayManualTool === 'draw' }" @click="activateSingleOverlayManualTool('draw')">新增框</button>
              <button type="button" class="ci-tool-btn" :class="{ active: singleOverlayManualTool === 'erase' }" @click="activateSingleOverlayManualTool('erase')">删除已有框</button>
              <button type="button" class="ci-tool-btn" @click="selectSingleOverlayManualWhole">选中整层并拖拽/缩放</button>
              <div class="ci-single-editor-meta" v-if="singleOverlayManualTool === 'select'">
                <span>点击已有框后，拖动标签可平移，拖拽四角可伸缩；也可点“选中整层并拖拽/缩放”整体变换</span>
              </div>
              <div class="ci-single-editor-meta">
                <span>底图仅作参照，不可编辑；保存时覆盖整张覆盖层并同步更新全部DMT坐标</span>
              </div>
              <div class="ci-single-editor-meta" v-if="singleOverlayManualTool === 'erase'">
                <span>删除命中的已有框，不支持任意区域擦除</span>
              </div>
              <div class="ci-single-editor-meta" v-if="singleOverlayManualTool === 'draw'">
                <span>拖拽框选即可新增框（默认新增 D 框）</span>
              </div>
              <div class="ci-single-editor-meta">
                <span>缩放</span>
                <input v-model.number="singleOverlayManualZoom" type="range" min="1" max="4" step="0.1" />
                <span>{{ singleOverlayManualZoom.toFixed(1) }}x</span>
              </div>
              <button type="button" class="ci-action-btn" v-if="singleOverlayManualSelection" @click="clearSingleOverlayManualSelection">取消选中</button>
              <button type="button" class="ci-action-btn" v-if="singleOverlayManualSelection && singleOverlayManualSelection.region_id !== '__whole_overlay__'" @click="deleteSingleOverlayManualSelection">删除选中框</button>
              <button type="button" class="ci-action-btn" :disabled="singleOverlayManualUndoStack.length === 0" @click="undoSingleOverlayManual">撤销</button>
            </div>
            <div ref="singleOverlayManualStageWrap" class="ci-single-overlay-editor-stage-wrap">
              <div
                class="ci-single-overlay-editor-stage"
                :style="{ width: (singleOverlayManualDisplayBaseWidth * singleOverlayManualZoom) + 'px', height: (singleOverlayManualDisplayBaseHeight * singleOverlayManualZoom) + 'px', cursor: getSingleOverlayManualStageCursor() }"
                @mousedown.prevent="onSingleOverlayManualMouseDown"
                @mousemove.prevent="onSingleOverlayManualMouseMove"
                @mouseup.prevent="onSingleOverlayManualMouseUp"
                @mouseleave.prevent="onSingleOverlayManualMouseUp"
              >
                <img
                  v-if="singleWorkAreaReproductionSrc"
                  :src="singleWorkAreaReproductionSrc"
                  class="ci-single-overlay-editor-base-image"
                  alt="当前复现图底图"
                />
                <canvas
                  ref="singleOverlayManualCanvas"
                  class="ci-single-overlay-editor-canvas"
                  :style="{ width: '100%', height: '100%' }"
                ></canvas>
                <div
                  v-if="singleOverlayManualSelection"
                  class="ci-single-overlay-selection"
                  :class="{ 'is-active': singleOverlayManualTool === 'select' }"
                  :style="getSingleOverlayManualSelectionStyle()"
                >
                  <div class="ci-single-overlay-selection-label" @mousedown.stop.prevent="startSingleOverlayManualTransform('move', $event)">{{ singleOverlayManualSelection.title || singleOverlayManualSelection.region_id }} · {{ singleOverlayManualSelection.w }}×{{ singleOverlayManualSelection.h }}</div>
                  <span class="ci-single-overlay-selection-handle is-nw" @mousedown.stop.prevent="startSingleOverlayManualTransform('resize-nw', $event)"></span>
                  <span class="ci-single-overlay-selection-handle is-ne" @mousedown.stop.prevent="startSingleOverlayManualTransform('resize-ne', $event)"></span>
                  <span class="ci-single-overlay-selection-handle is-sw" @mousedown.stop.prevent="startSingleOverlayManualTransform('resize-sw', $event)"></span>
                  <span class="ci-single-overlay-selection-handle is-se" @mousedown.stop.prevent="startSingleOverlayManualTransform('resize-se', $event)"></span>
                </div>
              </div>
            </div>
          </div>
          <div class="ci-r-actions ci-single-editor-actions">
            <button type="button" class="ci-action-btn" @click="closeSingleOverlayManualDialog">取消</button>
            <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="singleOverlayManualSaving" @click="confirmSingleOverlayManualEdit">保存到当前覆盖层</button>
          </div>
        </div>
      </div>
      <!-- 批量轻量识字 + 三层理解预览 -->
      <div class="ci-layout-overlay" v-if="liteBatchDialogVisible" @click.self="!liteBatchRunning && closeLiteBatchWorkflowDialog()">
        <div class="ci-layout-dialog ci-lite-batch-dialog">
          <div class="ci-layout-dialog-header">
            <span>批量轻量识字 + 三层理解预览（Gemini）</span>
            <button type="button" class="ci-link-btn" :disabled="liteBatchRunning" @click="closeLiteBatchWorkflowDialog">关闭</button>
          </div>
          <div class="ci-layout-dialog-body">
            <div v-if="!liteBatchRunning && !liteBatchFinished" class="ci-lite-batch-pick">
              <template v-if="liteBatchPhase === 'pick_files'">
                <div class="ci-single-inline-hint">第 1 步：在下方勾选要纳入批量的<strong>文档导入区图片</strong>（共 {{ liteBatchPickPoolImages.length }} 张），确认后再查询各图的单图 CI 分析与 D 区状态。</div>
                <div v-if="!liteBatchPickPoolImages.length" class="ci-single-inline-hint">文档导入区暂无图片文件，请先在左侧导入区上传图片。</div>
                <div v-else-if="liteBatchCandidatesLoading" class="ci-single-inline-hint">正在查询各图片对应的单图 CI 分析…</div>
                <div class="ci-lite-batch-checklist">
                  <label
                    v-for="fileName in liteBatchPickPoolImages"
                    :key="`lite-batch-pool-${fileName}`"
                    class="ci-r-inline-check ci-lite-batch-check-item"
                  >
                    <input v-model="liteBatchPoolPickFileNames" type="checkbox" :value="fileName" :disabled="liteBatchCandidatesLoading" />
                    <span>{{ fileName }}</span>
                  </label>
                </div>
                <div class="ci-r-actions">
                  <button type="button" class="ci-action-btn" :disabled="liteBatchCandidatesLoading" @click="liteBatchSelectAllPool">全选</button>
                  <button type="button" class="ci-action-btn" :disabled="liteBatchCandidatesLoading" @click="liteBatchClearPoolPick">清空</button>
                  <button
                    type="button"
                    class="ci-action-btn ci-action-btn-primary"
                    :disabled="!liteBatchPoolPickFileNames.length || liteBatchCandidatesLoading"
                    @click="confirmLiteBatchPoolAndResolve"
                  >{{ liteBatchCandidatesLoading ? '解析中…' : '查询所选图片的 CI 状态' }}</button>
                </div>
              </template>
              <template v-else-if="liteBatchPhase === 'pick_batch'">
                <div class="ci-single-inline-hint">第 2 步：已解析 {{ liteBatchCandidatesResolved.length }} 张。请勾选<strong>可处理</strong>项（须有独立单图 CI 且覆盖层含 D 区），再开始批量；失败不阻断后续图片。</div>
                <div class="ci-lite-batch-checklist">
                  <label
                    v-for="row in liteBatchCandidatesResolved"
                    :key="`lite-batch-pick-${row.fileName}`"
                    class="ci-r-inline-check ci-lite-batch-check-item"
                    :class="{ 'is-disabled': !row.selectable }"
                  >
                    <input v-model="liteBatchSelectedFileNames" type="checkbox" :value="row.fileName" :disabled="!row.selectable" />
                    <span>
                      {{ row.fileName }}
                      <template v-if="row.note"> · {{ row.note }}</template>
                      <template v-if="row.rStatus && row.rStatus !== 'ready'"> · R层{{ formatRItemStatus(row.rStatus) }}</template>
                    </span>
                  </label>
                </div>
                <div class="ci-r-actions">
                  <button type="button" class="ci-action-btn" @click="liteBatchBackToPoolPick">返回重选图片</button>
                  <button type="button" class="ci-action-btn" @click="liteBatchSelectAllCandidates">全选可处理项</button>
                  <button type="button" class="ci-action-btn" @click="liteBatchClearSelection">清空</button>
                  <button type="button" class="ci-action-btn ci-action-btn-primary" :disabled="!liteBatchSelectedFileNames.length" @click="runLiteBatchWorkflow">开始批量处理</button>
                </div>
              </template>
            </div>
            <div v-else class="ci-lite-batch-progress">
              <label class="ci-r-field-label">进度 {{ liteBatchProgress }}%</label>
              <div class="ci-progress-track"><div class="ci-progress-fill" :style="{ width: `${liteBatchProgress}%` }"></div></div>
              <div class="ci-single-inline-hint">{{ liteBatchStatus }}</div>
              <div v-if="liteBatchResults.length" class="ci-lite-batch-results">
                <div
                  v-for="row in liteBatchResults"
                  :key="`lite-batch-result-${row.fileName || row.unitId}`"
                  class="ci-lite-batch-result-row"
                  :class="{ 'is-ok': row.liteOcrOk && row.previewOk, 'is-partial': row.liteOcrOk && !row.previewOk, 'is-fail': !row.liteOcrOk }"
                >
                  <div class="ci-lite-batch-result-title">
                    <strong>{{ row.fileName || row.title || row.unitId }}</strong>
                    <span v-if="row.liteOcrOk && row.previewOk"> · 全部成功</span>
                    <span v-else-if="row.liteOcrOk"> · 识字成功 / 预览失败</span>
                    <span v-else> · 失败</span>
                  </div>
                  <div v-if="row.cachePath" class="ci-single-inline-hint">缓存：<code>{{ row.cachePath }}</code></div>
                  <div v-if="row.error" class="ci-single-inline-hint">错误：{{ row.error }}</div>
                  <ul v-if="row.logs && row.logs.length" class="ci-lite-batch-log">
                    <li v-for="(line, li) in row.logs" :key="`${row.unitId}-log-${li}`">{{ line }}</li>
                  </ul>
                </div>
              </div>
              <div v-if="liteBatchFinished" class="ci-r-actions">
                <button type="button" class="ci-action-btn ci-action-btn-primary" @click="closeLiteBatchWorkflowDialog">完成</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { API_BASE_URL } from '@/config/apiConfig'
import {
  applyCILiteBundleToReproduction,
  applyRefineCISingleImageUnderstanding,
  applyRefineCISingleTLayerFromDLite,
  autoIterateCIReproductionRound,
  estimateCIOverlayHandwriting,
  evaluateCIDRegionConfidenceBatch,
  generateCIOverlay,
  getCIDLiteImageUnderstandingPreviewCache,
  getCIDRegionConfidenceResult,
  getCIOverlayHistory,
  getCIOverlayStatus,
  getCIProgress,
  getCIResult,
  queryCIAnalyses,
  iterateCIOverlay,
  markCIAutoIterateRegionsUsed,
  pickCIAutoIterateRegionsByConfidence,
  previewRefineCISingleImageUnderstanding,
  previewRefineCISingleImageUnderstandingFromDLite,
  previewRefineCISingleTLayerFromDLite,
  previewCIAutoIterateReproductionRound,
  recognizeCIDRegion,
  refineCISingleTLayer,
  rollbackCISingleTLayer,
  saveCIOverlay,
  saveCIReproduction,
} from '@/api/continuous_image'

// 英文字段名 → 中文标签映射
const KEY_LABELS = {
  seq: '序号',
  unit_id: '图片',
  relation_type: '关系',
  reason: '说明',
  scene_name: '场景',
  sub_scene_name: '子场景',
  scene_summary_binding: '场景绑定',
  meaning: '核心意义',
  type: '类型',
  position: '位置',
  content: '内容',
  description: '描述',
  label: '标签',
  category: '分类',
  summary: '摘要',
  title: '标题',
  action: '行动',
  priority: '优先级',
  topic: '主题',
  knowledge_type: '知识类型',
  // doc_relations 字段
  file_name: '文档',
  relation: '关联类型',
  key_point: '关联要点',
  // scene_meaning 字段
  file_key: '文档键',
}

const R_CONTEXT_FIELD_DEFS = [
  { key: 't_focus_text', label: 'T层高价值理解补充', rows: 5, editable: true },
  { key: 'main_content', label: '主要内容摘要', rows: 4, editable: true },
  { key: 'layout_regions_text', label: '版面区域划分', rows: 9, editable: true },
  { key: 'reading_order', label: '阅读顺序', rows: 3, editable: true },
  { key: 'handwriting_printing_relation', label: '手写/印刷层说明', rows: 3, editable: true },
  { key: 'annotation_section', label: '批注关系', rows: 3, editable: true },
  { key: 'continuity_text', label: '与前图关系', rows: 3, editable: true },
  { key: 'm_verification_text', label: 'M层复核结果', rows: 4, editable: true },
  { key: 'color_instruction', label: '底色指示', rows: 2, editable: false },
  { key: 'ratio_instruction', label: '信息比例', rows: 2, editable: false },
]

const SINGLE_LAYOUT_REGION_LIMITS = {
  d: 9,
  m: 2,
  t: 1,
}

/** 轻量全自动（full_lite）单轮可选手动 D 区上限；半自动/普通全自动仍为 SINGLE_LAYOUT_REGION_LIMITS.d */
const SINGLE_AUTO_ITERATION_D_LIMIT_LITE = 18

const SINGLE_LAYOUT_REGION_META = {
  d: { label: 'D级版面', color: '#E53935', rgb: [229, 57, 53] },
  m: { label: 'M级版面', color: '#1E88E5', rgb: [30, 136, 229] },
  t: { label: 'T级版面', color: '#8E24AA', rgb: [142, 36, 170] },
}

const SINGLE_LAYOUT_RECOGNITION_OPTIONS = [
  { value: 'white', label: '白区：文字清晰且能被上下文确认' },
  { value: 'gray', label: '灰区：能识别但仍需继续迭代' },
  { value: 'black', label: '黑区：OCR无效或难以辨认' },
]

const SINGLE_LAYOUT_ITERATION_MODE_OPTIONS = [
  { value: 'rewrite', label: '文本约束迭代' },
  { value: 'crop', label: '局部裁切迭代' },
]

const SINGLE_AUTO_ITERATION_MODE_OPTIONS = [
  { value: 'semi', label: '半自动：预览灰区后确认' },
  { value: 'full', label: '全自动：直接执行本轮' },
]

const SINGLE_AUTO_GRAY_CHOICE_OPTIONS = [
  { value: 'default', label: '默认合并结果' },
  { value: 'gemini', label: 'Gemini 结果' },
  { value: 'qwen', label: 'Qwen 结果' },
  { value: 'manual', label: '手动输入' },
]

const SINGLE_OVERLAY_LEVELS = ['d', 'm', 't']
const SINGLE_LAYOUT_REGION_ORDER = { t: 0, m: 1, d: 2 }
const DEFAULT_SINGLE_WORKAREA_SECTION_EXPANDED = { reproduction: false, overlay: true }
const DEFAULT_SINGLE_LAYOUT_GROUP_EXPANDED = { d: false, m: false, t: false }
const DEFAULT_SINGLE_OVERLAY_VISIBLE_LEVELS = { d: true, m: true, t: true }

export default {
  name: 'ContinuousImagePanel',
  props: {
    /** 可用分析列表 { singles: [], groups: [] } */
    availableAnalyses: { type: Object, default: () => ({ singles: [], groups: [] }) },
    /** 当前查看/运行中的 analysis_id */
    activeAnalysisId: { type: String, default: '' },
    /** 当前展示的完整结果（含 manifest/d/m/t_layer）*/
    activeResult: { type: Object, default: null },
    /** 当前运行中的任务 */
    runningTask: { type: Object, default: null },
    /** 父组件发来的单图工作区自动进入信号 */
    singleWorkAreaAutoOpenSignal: { type: Object, default: null },
    /** 当前勾选的文档文件名列表 */
    selectedContextDocs: { type: Array, default: () => [] },
    /** 当前勾选的卡片ID列表 */
    selectedContextCardIds: { type: Array, default: () => [] },
    /** 当前场景名（用于 queryCIAnalyses） */
    sceneName: { type: String, default: '' },
    /** 文档导入区全部图片文件名（非勾选子集） */
    docImportImageFileNames: { type: Array, default: () => [] },
  },
  emits: ['close', 'switch-tab', 'redo', 'generate-reproduction', 'save-reproduction-context', 'iterate-reproduction-unit', 'iterate-reproduction-layout-regions', 'auto-iterate-reproduction-round', 'apply-lite-bundle-reproduction', 'rollback-reproduction-unit'],
  data() {
    return {
      viewMode: 'group',
      tLayerExpanded: true,
      rContextPanelExpanded: false,
      mLayerExpanded: true,
      dLayerExpanded: false,
      expandedSections: {},
      expandedOcrs: {},
      rContextExpandedSections: {},
      rTextPreviewCollapsed: {},
      rContextEdits: {},
      rItemLocalOverrides: {},
      singleIndex: 0,
      showSingleOcr: false,
      dViewMode: {},
      layoutVisualVisible: false,
      layoutVisualSrc: '',
      layoutVisualIsOriginal: false,
      layoutVisualType: 'image',
      rIterateDialogVisible: false,
      rIterateActiveUnitId: '',
      rIterateRevisionInstruction: '',
      rIterateReferenceDataUrl: '',
      rIterateImageQuality: 'normal',
      singleWorkAreaVisible: false,
      singleWorkAreaUnitId: '',
      singleWorkAreaRevisionInstruction: '',
      singleWorkAreaReferenceDataUrl: '',
      singleWorkAreaImageQuality: 'normal',
      singleWorkAreaPreviewZoom: 1,
      singleWorkAreaSectionExpanded: { ...DEFAULT_SINGLE_WORKAREA_SECTION_EXPANDED },
      singleOverlayInstructionText: '',
      singleOverlayReferenceDataUrl: '',
      singleOverlayImageQuality: 'normal',
      singleOverlayHistory: [],
      singleOverlayHistoryIndex: -1,
      singleOverlayDataUrl: '',
      singleOverlayPreviewDataUrl: '',
      singleOverlayVisibleLevels: { ...DEFAULT_SINGLE_OVERLAY_VISIBLE_LEVELS },
      singleOverlayItemLocal: null,
      singleOverlayDisplayMetrics: { left: 0, top: 0, width: 0, height: 0 },
      singleLayoutIterationMode: 'rewrite',
      singleLayoutRegionGroupExpanded: { ...DEFAULT_SINGLE_LAYOUT_GROUP_EXPANDED },
      singleLayoutRegionDrafts: {},
      singleOverlayJobRunning: false,
      singleOverlayBusy: false,
      singleOverlayPollTimer: null,
      singleOverlayHandwritingBusy: false,
      singleOverlayPromptStreaming: false,
      singleOverlayIncludeTmContext: true,
      singleOverlayDmtGenerated: false,
      singleAutoIterationMode: 'semi',
      singleAutoIterationContinueFromCursor: true,
      singleAutoIterationStartRegionId: '',
      singleAutoIterationSelectedRegionIds: [],
      singleAutoIterationPreviewing: false,
      singleAutoIterationPreviewData: null,
      singleAutoIterationGrayDialogVisible: false,
      singleAutoIterationGrayDrafts: {},
      singleDRegionProbeRegionId: '',
      singleDRegionProbeBusy: false,
      singleDRegionProbeDialogVisible: false,
      singleDRegionProbeDialogPayload: null,
      singleDRegionProbeAuditPath: '',
      singleDRegionProbeConfirmVisible: false,
      singleDRegionProbeCropPreviewDataUrl: '',
      singleDRegionConfidenceBusy: false,
      singleDRegionConfidenceResultPath: '',
      singleDRegionConfidenceResults: [],
      singleDRegionConfidenceSortOrder: 'asc',
      singleDRegionConfidenceModel: 'qwen',
      singleAutoIterLowestPickPending: null,
      singleGlobalWorkflowRunning: false,
      singleGlobalWorkflowProgress: 0,
      singleGlobalWorkflowStatus: '',
      liteBatchDialogVisible: false,
      liteBatchPhase: 'pick_files',
      liteBatchPoolPickFileNames: [],
      liteBatchSelectedFileNames: [],
      liteBatchRunning: false,
      liteBatchFinished: false,
      liteBatchProgress: 0,
      liteBatchStatus: '',
      liteBatchResults: [],
      liteBatchUnitCacheMap: {},
      liteBatchCandidatesResolved: [],
      liteBatchCandidatesLoading: false,
      liteBatchScopedAnalysisId: '',
      singleSnippetSketchPreprocess: true,
      singleSnippetUseRecognitionContext: true,
      singleReproContextMenuVisible: false,
      singleReproContextMenuX: 0,
      singleReproContextMenuY: 0,
      singleReproContextMenuUnitId: '',
      singleReproRefineBusy: false,
      singleImageUnderstandingPreviewDialogVisible: false,
      singleImageUnderstandingPreviewKind: 'repro',
      singleImageUnderstandingPreviewText: '',
      singleImageUnderstandingExistingText: '',
      singleImageUnderstandingPreviewSourceFile: '',
      singleImageUnderstandingPreviewImgId: 0,
      singleTLayerFromDLiteDialogVisible: false,
      singleTLayerFromDLitePreviewText: '',
      singleTLayerFromDLiteExistingText: '',
      singleDLiteRefineModelDialogVisible: false,
      singleDLiteRefineModelChoice: 'gemini',
      singleDLiteRefineModelPendingAction: '',
      singleDLiteRefineModelUsedName: '',
      singleOverlayManualDialogVisible: false,
      singleOverlayManualTool: 'select',
      singleOverlayManualLevel: 'd',
      singleOverlayManualDirty: false,
      singleOverlayManualZoom: 1.6,
      singleOverlayManualCanvasWidth: 0,
      singleOverlayManualCanvasHeight: 0,
      singleOverlayManualDisplayBaseWidth: 0,
      singleOverlayManualDisplayBaseHeight: 0,
      singleOverlayManualRegions: [],
      singleOverlayManualUndoStack: [],
      singleOverlayManualEraseSize: 20,
      singleOverlayManualIsErasing: false,
      singleOverlayManualLastPoint: null,
      singleOverlayManualDrawingBox: false,
      singleOverlayManualBoxStart: null,
      singleOverlayManualBoxBackup: null,
      singleOverlayManualSelection: null,
      singleOverlayManualSelecting: false,
      singleOverlayManualSelectionStart: null,
      singleOverlayManualTransformMode: '',
      singleOverlayManualTransformStart: null,
      singleOverlayManualTransformBaseImage: null,
      singleOverlayManualTransformSourceCanvas: null,
      singleOverlayManualTransformSourceRect: null,
      singleOverlayManualSaving: false,
      singleReproductionManualDialogVisible: false,
      singleReproductionManualTool: 'line',
      singleReproductionManualZoom: 1.4,
      singleReproductionManualCanvasWidth: 0,
      singleReproductionManualCanvasHeight: 0,
      singleReproductionManualDisplayBaseWidth: 0,
      singleReproductionManualDisplayBaseHeight: 0,
      singleReproductionManualUndoStack: [],
      singleReproductionManualDrawing: false,
      singleReproductionManualStartPoint: null,
      singleReproductionManualPreviewBaseImage: null,
      singleReproductionManualLastPoint: null,
      singleReproductionManualStrokeColor: '#c62828',
      singleReproductionManualStrokeWidth: 12,
      singleReproductionManualSaving: false,
    }
  },
  computed: {
    manifest() {
      return this.activeResult?.manifest || null
    },
    tLayer() {
      return this.activeResult?.t_layer || {}
    },
    mSections() {
      const m = this.activeResult?.m_layer
      if (!m) return []
      return m.sections || []
    },
    dUnits() {
      const d = this.activeResult?.d_layer
      if (!d) return []
      return d.items || d.units || []
    },
    rItems() {
      const baseItems = Array.isArray(this.activeResult?.r_layer?.items) ? this.activeResult.r_layer.items : []
      return baseItems.map(item => {
        const unitId = item?.unit_id || ''
        const override = unitId ? this.rItemLocalOverrides?.[unitId] : null
        if (!override) return item
        const baseUpdatedAt = String(item?.updated_at || '')
        const overrideUpdatedAt = String(override?.updated_at || '')
        if (baseUpdatedAt && overrideUpdatedAt && overrideUpdatedAt < baseUpdatedAt) return item
        return {
          ...item,
          ...override,
          iter_context: override?.iter_context || item?.iter_context || {},
        }
      })
    },
    overlayItems() {
      return this.activeResult?.overlay_layer?.items || []
    },
    currentSingleSection() {
      return this.mSections[this.singleIndex] || null
    },
    currentSingleRItem() {
      const unitId = this.currentSingleSection?.unit_id || ''
      if (!unitId) return null
      return this.rItems.find(item => item?.unit_id === unitId) || null
    },
    readyRItems() {
      return this.rItems.filter(item => item && item.status === 'ready')
    },
    failedRItems() {
      return this.rItems.filter(item => item && item.status === 'failed')
    },
    currentSingleOverlayItem() {
      const unitId = this.currentSingleSection?.unit_id || ''
      if (!unitId) return null
      return this.overlayItems.find(item => item?.unit_id === unitId) || null
    },
    singleWorkAreaItem() {
      if (!this.singleWorkAreaUnitId) return null
      return this.rItems.find(item => item?.unit_id === this.singleWorkAreaUnitId) || null
    },
    singleWorkAreaOverlayItem() {
      if (!this.singleWorkAreaUnitId) return null
      return this.overlayItems.find(item => item?.unit_id === this.singleWorkAreaUnitId) || null
    },
    singleWorkAreaOverlayStateItem() {
      if (this.singleOverlayItemLocal?.unit_id === this.singleWorkAreaUnitId) return this.singleOverlayItemLocal
      return this.singleWorkAreaOverlayItem
    },
    singleWorkAreaReproductionSrc() {
      return this.getReproductionSrc(this.singleWorkAreaItem)
    },
    singleAutoIterationState() {
      const autoIteration = this.singleWorkAreaOverlayStateItem?.auto_iteration
      return autoIteration && typeof autoIteration === 'object' ? autoIteration : {}
    },
    singleAutoIterationLastRound() {
      const lastRound = this.singleAutoIterationState?.last_round
      return lastRound && typeof lastRound === 'object' ? lastRound : null
    },
    singleAutoIterationCursorRegionId() {
      return String(this.singleAutoIterationState?.next_region_id || '')
    },
    singleOverlayRegions() {
      const regions = this.singleWorkAreaOverlayStateItem?.regions
      return Array.isArray(regions) ? regions : []
    },
    singleAutoIterationStartOptions() {
      return this.singleOverlayRegions
        .filter(region => (region?.level || '').toLowerCase() === 'd')
        .sort((left, right) => {
          const leftRank = Number(left?.rank || 0)
          const rightRank = Number(right?.rank || 0)
          if (leftRank !== rightRank) return leftRank - rightRank
          const leftY = Number(left?.bbox?.y || 0)
          const rightY = Number(right?.bbox?.y || 0)
          if (leftY !== rightY) return leftY - rightY
          const leftX = Number(left?.bbox?.x || 0)
          const rightX = Number(right?.bbox?.x || 0)
          if (leftX !== rightX) return leftX - rightX
          return String(left?.region_id || '').localeCompare(String(right?.region_id || ''))
        })
    },
    singleAutoIterationModeOptions() {
      const base = [...SINGLE_AUTO_ITERATION_MODE_OPTIONS]
      if (this.singleDmtCoarseLayoutEligible) {
        base.push({ value: 'full_lite', label: '全自动-直接执行&平衡效率和质量（Qwen 轻量）' })
      }
      return base
    },
    singleDmtCoarseLayoutEligible() {
      const item = this.singleWorkAreaOverlayStateItem
      if (!item || typeof item !== 'object') return false
      if (item.ci_dmt_coarse_layout === true || item.ci_dmt_coarse_layout === 'true') return true
      const r = Number(item.ci_sketch_handwriting_area_ratio)
      return Number.isFinite(r) && r >= 0 && r < 0.6
    },
    formatSingleHandwritingRatio() {
      const r = Number(this.singleWorkAreaOverlayStateItem?.ci_sketch_handwriting_area_ratio)
      if (!Number.isFinite(r)) return '—'
      return `${(r * 100).toFixed(1)}%`
    },
    singleLiteFollowupReady() {
      const lite = this.singleWorkAreaOverlayStateItem?.lite_auto_iteration_last
      if (!lite || typeof lite !== 'object') return false
      return Boolean(lite.finished_at || lite.bundle_rel_path)
    },
    liteBatchPickPoolImages() {
      const docs = Array.isArray(this.docImportImageFileNames) ? this.docImportImageFileNames : []
      const seen = new Set()
      const out = []
      for (const name of docs) {
        if (!this.isDocImportImageFile(name)) continue
        const key = this.normalizeCiFileKey(name)
        if (!key || seen.has(key)) continue
        seen.add(key)
        out.push(name)
      }
      return out
    },
    liteBatchSelectableFileNames() {
      return this.liteBatchCandidatesResolved.filter(row => row.selectable).map(row => row.fileName)
    },
    singleDLiteUnderstandingHasTodayCache() {
      const uid = this.singleWorkAreaItem?.unit_id || ''
      const aid = this.activeAnalysisId || ''
      const key = aid && uid ? `${aid}::${uid}` : uid
      return Boolean(key && this.liteBatchUnitCacheMap[key] === true)
    },
    singleDLiteUnderstandingPreviewButtonLabel() {
      return this.singleDLiteUnderstandingHasTodayCache
        ? '查看结果：按轻量 D 校正三层理解'
        : '预览：按轻量 D 校正三层理解'
    },
    isApplyLiteBundleRunning() {
      const uid = this.singleWorkAreaItem?.unit_id || ''
      return Boolean(
        uid &&
        this.runningTask &&
        !this.runningTask.completed &&
        this.runningTask.task_kind === 'reproduction_apply_lite_bundle' &&
        this.runningTask.analysis_id === this.activeAnalysisId &&
        this.runningTask.unit_id === uid
      )
    },
    singleAutoIterationGrayChoiceOptions() {
      return SINGLE_AUTO_GRAY_CHOICE_OPTIONS
    },
    singleAutoIterationMaxDRegions() {
      return this.singleAutoIterationMode === 'full_lite'
        ? SINGLE_AUTO_ITERATION_D_LIMIT_LITE
        : SINGLE_LAYOUT_REGION_LIMITS.d
    },
    selectedSingleAutoIterationRegions() {
      const selectedSet = new Set(this.singleAutoIterationSelectedRegionIds || [])
      return this.singleAutoIterationStartOptions
        .filter(region => selectedSet.has(region?.region_id))
        .slice(0, this.singleAutoIterationMaxDRegions)
    },
    singleAutoIterationUsesManualSelection() {
      return this.selectedSingleAutoIterationRegions.length > 0
    },
    singleAutoIterationSelectionSummary() {
      if (!this.singleAutoIterationStartOptions.length) return '当前覆盖层没有可用的 D 版面。'
      if (this.singleAutoIterationMode === 'semi') {
        return `半自动模式：已手动选择 ${this.selectedSingleAutoIterationRegions.length}/${SINGLE_LAYOUT_REGION_LIMITS.d} 个 D 版面。`
      }
      if (this.singleAutoIterationMode === 'full_lite') {
        if (this.singleAutoIterationUsesManualSelection) {
          return `轻量全自动：已选择 ${this.selectedSingleAutoIterationRegions.length}/${this.singleAutoIterationMaxDRegions} 个 D 版面；提交后仅对这些区域运行 Qwen + 自检并保存（无裁判、不贴补 R）；JSON 按区合并，再次提交可只勾选需迭代的区。`
        }
        return `轻量全自动：请先在上方勾选 1-${this.singleAutoIterationMaxDRegions} 个 D 版面，再点击执行（后端最多 2 路并发）。`
      }
      if (this.singleAutoIterationUsesManualSelection) {
        return `全自动手动模式：已选择 ${this.selectedSingleAutoIterationRegions.length}/${SINGLE_LAYOUT_REGION_LIMITS.d} 个 D 版面，提交后会直接处理这些版面。`
      }
      if (this.singleAutoIterationContinueFromCursor) {
        const cursorRegion = this.singleAutoIterationStartOptions.find(region => region?.region_id === this.singleAutoIterationCursorRegionId)
        if (cursorRegion) return `全自动游标模式：下一轮将从 ${cursorRegion.title || cursorRegion.region_id} 开始。`
        return '全自动游标模式：尚未建立游标，系统会从第一个 D 版面开始。'
      }
      const startRegion = this.singleAutoIterationStartOptions.find(region => region?.region_id === this.singleAutoIterationStartRegionId)
      if (startRegion) return `全自动起始模式：将从 ${startRegion.title || startRegion.region_id} 开始。`
      return '全自动起始模式：请指定起始 D 版面。'
    },
    singleAutoIterationPreviewSelectedRegions() {
      const selected = this.singleAutoIterationPreviewData?.selected_regions
      return Array.isArray(selected) ? selected : []
    },
    singleAutoIterationPreviewGrayRegions() {
      const grayRegions = this.singleAutoIterationPreviewData?.gray_regions
      return Array.isArray(grayRegions) ? grayRegions : []
    },
    singleDRegionConfidenceSummaryText() {
      if (!this.singleDRegionConfidenceResults.length) return ''
      const sortOrder = String(this.singleDRegionConfidenceSortOrder || 'asc').toLowerCase() === 'desc' ? 'desc' : 'asc'
      const ordered = [...this.singleDRegionConfidenceResults].sort((left, right) => {
        const lv = Number(left?.confidence_percent || 0)
        const rv = Number(right?.confidence_percent || 0)
        return sortOrder === 'asc' ? (lv - rv) : (rv - lv)
      })
      return ordered.map((item, index) => {
        const regionId = String(item?.region_id || '').trim()
        const title = String(item?.title || regionId || `D${index + 1}`).trim()
        const confidence = Number(item?.confidence_percent || 0)
        const attempts = Number(item?.attempts || 0)
        const err = String(item?.error || '').trim()
        return `${index + 1}. ${title} (${regionId}) -> ${confidence.toFixed(2)}%${attempts ? `（尝试${attempts}次）` : ''}${err ? `；错误：${err}` : ''}`
      }).join('\n')
    },
    singleAutoIterationPreviewFailedRegions() {
      const failed = this.singleAutoIterationPreviewData?.failed_regions
      return Array.isArray(failed) ? failed : []
    },
    canSubmitSingleAutoIteration() {
      if (this.singleAutoIterationPreviewing) return false
      if (this.reproductionBusy) return false
      if (!this.singleWorkAreaItem?.unit_id || this.singleWorkAreaItem?.status !== 'ready') return false
      if (this.isUnitIterating(this.singleWorkAreaItem.unit_id)) return false
      if (!this.singleOverlayViewingCurrent) return false
      if (!this.singleAutoIterationStartOptions.length) return false
      if (this.singleAutoIterationMode === 'semi') return this.selectedSingleAutoIterationRegions.length > 0
      if (this.singleAutoIterationMode === 'full_lite') {
        if (!this.singleDmtCoarseLayoutEligible) return false
        return this.selectedSingleAutoIterationRegions.length > 0
      }
      if (this.singleAutoIterationUsesManualSelection) return true
      if (this.singleAutoIterationContinueFromCursor && this.singleAutoIterationLastRound && !this.singleAutoIterationCursorRegionId) return false
      if (!this.singleAutoIterationContinueFromCursor && !this.singleAutoIterationStartRegionId) return false
      return true
    },
    singleAutoIterationButtonLabel() {
      if (this.singleAutoIterationPreviewing) return '预览中...'
      if (this.reproductionBusy) return '处理中...'
      if (this.singleAutoIterationMode === 'semi') return '预览灰区并确认'
      if (this.singleAutoIterationMode === 'full_lite') {
        if (!this.singleAutoIterationUsesManualSelection) return '请先选择 D 版面'
        return '按所选 D 版面轻量识字（保存）'
      }
      if (this.singleAutoIterationUsesManualSelection) return '按所选 D 版面全自动迭代'
      if (this.singleAutoIterationContinueFromCursor) {
        if (this.singleAutoIterationLastRound && !this.singleAutoIterationCursorRegionId) return '当前已到末尾'
        return this.singleAutoIterationCursorRegionId ? '继续自动迭代一轮' : '开始自动迭代一轮'
      }
      return '从指定D版面开始自动迭代'
    },
    singleAutoIterationHint() {
      if (!this.singleWorkAreaItem?.unit_id || this.singleWorkAreaItem?.status !== 'ready') return '请先生成当前页复现图，再进行自动迭代。'
      if (!this.singleOverlayRegions.length) return '请先生成当前页覆盖层，系统才能按 D 版面顺序执行自动迭代。'
      if (!this.singleOverlayViewingCurrent) return '当前正在查看历史覆盖层，请切回最新一版后再执行自动迭代。'
      if (!this.singleAutoIterationStartOptions.length) return '当前覆盖层没有可用的 D 版面。'
      if (this.singleAutoIterationMode === 'semi') {
        if (!this.selectedSingleAutoIterationRegions.length) return `半自动模式需要先手动选择 1-${SINGLE_LAYOUT_REGION_LIMITS.d} 个 D 版面；系统会先识别白/灰/黑区，再用一个总弹窗汇总灰区供你确认。`
        return '半自动模式会先识别所选 D 版面的白/灰/黑区；灰区会汇总到一个总弹窗中，供你选择 Gemini、Qwen 或手动文字。'
      }
      if (this.singleAutoIterationMode === 'full_lite') {
        if (!this.singleDmtCoarseLayoutEligible) return '轻量全自动仅在手写面积占比偏低（粗粒度 DMT）时可用；当前不满足条件。'
        if (!this.selectedSingleAutoIterationRegions.length) {
          return `请先勾选至少 1 个 D 版面；轻量全自动仅对所选调区使用 Qwen3.6-plus 初识与自检并保存，不做裁判与 R 层贴补；每批最多 ${this.singleAutoIterationMaxDRegions} 区、后端最多 2 路并发，结果写入 ci_audit（按 D 区合并，可分批只迭代部分区）。完成后可在左侧「最近一轮轻量识字」查看各 D 区明细。`
        }
        return `轻量全自动：仅使用 Qwen3.6-plus 初识与自检，不做裁判与 R 层贴补；本轮处理已选的 ${this.selectedSingleAutoIterationRegions.length} 个 D 区，结果写入 ci_audit（与已有汇总按区合并）。完成后可用下方按钮贴补 R 层或校正 T 层 / 三层理解；若仅个别区不满意，可只勾选该区再跑一轮。`
      }
      if (this.singleAutoIterationUsesManualSelection) return `全自动模式下，已手动选择的 1-${SINGLE_LAYOUT_REGION_LIMITS.d} 个 D 版面会直接执行本轮迭代，不再经过灰区确认弹窗。`
      if (this.singleAutoIterationContinueFromCursor) {
        if (this.singleAutoIterationLastRound && !this.singleAutoIterationCursorRegionId) return `最近一轮已经跑到最后一个 D 版面。如需重跑，请关闭“继续上一轮游标”并指定起始 D 版面，或直接手动选择 1-${SINGLE_LAYOUT_REGION_LIMITS.d} 个 D 版面。`
        const cursorRegion = this.singleAutoIterationStartOptions.find(region => region?.region_id === this.singleAutoIterationCursorRegionId)
        if (cursorRegion) return `下一轮将从 ${cursorRegion.title || cursorRegion.region_id} 开始，按坐标顺序最多处理 ${SINGLE_LAYOUT_REGION_LIMITS.d} 个 D 版面。`
        return '尚未建立自动迭代游标，系统会从第一个 D 版面开始执行。'
      }
      return `将从你指定的 D 版面开始，按坐标顺序最多处理 ${SINGLE_LAYOUT_REGION_LIMITS.d} 个 D 版面；白区、灰区、黑区都会按各自规则执行。`
    },
    singleOverlayVisibleLevelList() {
      const visibleLevels = SINGLE_OVERLAY_LEVELS.filter(level => this.singleOverlayVisibleLevels?.[level] !== false)
      return visibleLevels.length ? visibleLevels : [...SINGLE_OVERLAY_LEVELS]
    },
    singleOverlayVisibleRegions() {
      const visibleSet = new Set(this.singleOverlayVisibleLevelList)
      return this.singleOverlayRegions.filter(region => visibleSet.has(String(region?.level || '').toLowerCase()))
    },
    singleOverlayViewingCurrent() {
      return this.singleOverlayHistoryIndex >= 0 && this.singleOverlayHistoryIndex === this.singleOverlayHistory.length - 1
    },
    singleOverlayRegionBoxesVisible() {
      return Boolean(
        this.singleOverlayViewingCurrent &&
        this.singleOverlayVisibleRegions.length &&
        this.singleOverlayDisplayMetrics.width > 0 &&
        this.singleOverlayDisplayMetrics.height > 0
      )
    },
    singleOverlayRegionGroups() {
      return ['d', 'm', 't']
        .map(level => {
          const items = this.singleOverlayRegions
            .filter(region => (region?.level || '').toLowerCase() === level)
            .sort((left, right) => {
              const leftRank = Number(left?.rank || 0)
              const rightRank = Number(right?.rank || 0)
              if (leftRank !== rightRank) return leftRank - rightRank
              return String(left?.region_id || '').localeCompare(String(right?.region_id || ''))
            })
            .map(region => ({
              ...region,
              draft: this.singleLayoutRegionDrafts[region.region_id] || { selected: false, recognition: 'gray', user_instruction: '' },
            }))
          return {
            level,
            label: SINGLE_LAYOUT_REGION_META[level]?.label || `${level.toUpperCase()}级版面`,
            limit: SINGLE_LAYOUT_REGION_LIMITS[level] || 0,
            limitLabel: this.singleLayoutIterationMode === 'crop' ? '单选' : String(SINGLE_LAYOUT_REGION_LIMITS[level] || 0),
            selectedCount: items.filter(region => region.draft?.selected).length,
            items,
          }
        })
        .filter(group => group.items.length)
    },
    selectedSingleLayoutRegions() {
      return this.singleOverlayRegionGroups
        .reduce((items, group) => items.concat(group.items || []), [])
        .filter(region => region.draft?.selected)
        .sort((left, right) => {
          const leftOrder = SINGLE_LAYOUT_REGION_ORDER[left.level] ?? 99
          const rightOrder = SINGLE_LAYOUT_REGION_ORDER[right.level] ?? 99
          if (leftOrder !== rightOrder) return leftOrder - rightOrder
          const leftRank = Number(left?.rank || 0)
          const rightRank = Number(right?.rank || 0)
          if (leftRank !== rightRank) return leftRank - rightRank
          return String(left?.region_id || '').localeCompare(String(right?.region_id || ''))
        })
    },
    singleLayoutRecognitionOptions() {
      return SINGLE_LAYOUT_RECOGNITION_OPTIONS
    },
    singleLayoutIterationModeOptions() {
      return SINGLE_LAYOUT_ITERATION_MODE_OPTIONS
    },
    singleLayoutRegionSelectionSummary() {
      if (this.singleLayoutIterationMode === 'crop') {
        return `局部裁切模式：已选 ${this.selectedSingleLayoutRegions.length}/1`
      }
      return ['d', 'm', 't']
        .map(level => `${SINGLE_LAYOUT_REGION_META[level]?.label || level.toUpperCase()} ${this.getSelectedSingleLayoutRegionCount(level)}/${SINGLE_LAYOUT_REGION_LIMITS[level] || 0}`)
        .join(' · ')
    },
    canSubmitSingleLayoutRegionIterate() {
      if (this.reproductionBusy) return false
      if (!this.singleWorkAreaItem?.unit_id || this.singleWorkAreaItem?.status !== 'ready') return false
      if (!this.singleOverlayViewingCurrent || !this.selectedSingleLayoutRegions.length) return false
      return true
    },
    singleLayoutRegionSubmitHint() {
      if (!this.singleOverlayRegions.length) return '先生成当前页覆盖层，系统才会自动解析 D/M/T 版面。'
      if (!this.singleOverlayViewingCurrent) return '当前正在查看历史覆盖层，请切回最新一版后再提交版面级迭代。'
      if (!this.selectedSingleLayoutRegions.length) return '至少选择一个版面后才可提交定向迭代。'
      if (this.singleLayoutIterationMode === 'crop') {
        if (this.selectedSingleLayoutRegions.length > 1) return '局部裁切模式下一次只能保留一个版面，请重新选择。'
        return '提交后会裁切所选版面、生成同尺寸局部图，再拼回当前复现图；选区外内容保持不变。'
      }
      if (this.selectedSingleLayoutRegions.some(region => !String(region.draft?.user_instruction || '').trim())) {
        return '未填写版面级修改指令的区域，会结合当前页图生文理解与本子上下文自动补全；已填写的区域只按用户要求执行。'
      }
      return '提交后会先自动重写为“只改这些地方，其他不要变”的强约束指令，再进入现有单页迭代链路。'
    },
    rContextFieldDefs() {
      return R_CONTEXT_FIELD_DEFS
    },
    /** 所有可用分析的扁平标签列表，用于顶部 tabs */
    allTabs() {
      const tabs = []
      for (const r of (this.availableAnalyses?.singles || [])) {
        const f = r.files && r.files.length ? r.files[0] : '单图'
        tabs.push({ analysis_id: r.analysis_id, label: `📷 ${f}`, files: r.files })
      }
      for (const r of (this.availableAnalyses?.groups || [])) {
        const n = r.files ? r.files.length : 0
        tabs.push({ analysis_id: r.analysis_id, label: `🔗 多图(${n}张)`, files: r.files })
      }
      return tabs
    },
    reproductionStatus() {
      return this.activeResult?.reproduction_status || ''
    },
    isStrictSingleMode() {
      return (this.manifest?.mode || '') === 'single'
    },
    reproductionBusy() {
      if (!this.runningTask || this.runningTask.completed) return false
      return this.runningTask.analysis_id === this.activeAnalysisId
    },
    topReproductionReady() {
      return this.hasReadyReproductionImage(this.getTopIterativeTargetItem())
    },
    reproductionButtonLabel() {
      if (this.reproductionBusy) return '生成中...'
      return this.topReproductionReady ? '迭代生图' : '生成复现图'
    },
    reproductionButtonTitle() {
      if (this.reproductionBusy) return '当前分析正在处理中'
      if (!this.topReproductionReady) return '当前分析尚无复现图，点击后选择升维复现生成方式'
      if (this.shouldUseSingleUnitIterateFromTop()) return '当前为单图模式，点击后进入当前页的R层单页迭代'
      return '基于当前理解结果执行整组迭代生图'
    },
    topRollbackTargetItem() {
      return this.getTopIterativeTargetItem()
    },
    topRollbackDisabled() {
      const item = this.topRollbackTargetItem
      if (!item?.unit_id) return true
      if (this.reproductionBusy) return true
      if (this.isUnitIterating(item.unit_id)) return true
      return !this.canRollbackRItem(item)
    },
    topRollbackTitle() {
      const item = this.topRollbackTargetItem
      if (!item?.unit_id) return '当前为连续组视角，暂不支持顶部一键回滚；请在R层单页中操作'
      if (this.reproductionBusy || this.isUnitIterating(item.unit_id)) return '当前页正在处理中，暂不可回滚'
      if (!this.canRollbackRItem(item)) return '当前页暂无可回滚版本'
      return '回滚当前页复现图到上一版本'
    },
  },
  watch: {
    activeAnalysisId() {
      // 切换分析时重置所有内部展示状态
      this.closeSingleWorkArea()
      this.expandedSections = {}
      this.expandedOcrs = {}
      this.rContextExpandedSections = {}
      this.rTextPreviewCollapsed = {}
      this.rContextEdits = {}
      this.rItemLocalOverrides = {}
      this.dViewMode = {}
      this.singleIndex = 0
      this.showSingleOcr = false
      this.viewMode = 'group'
      this.dLayerExpanded = false
    },
    activeResult(val) {
      if (val) {
        this.tLayerExpanded = true
        this.mLayerExpanded = true
        this.initRContextEdits()
        this.syncSingleWorkAreaAutoOpen()
      }
    },
    singleWorkAreaAutoOpenSignal: {
      immediate: true,
      handler() {
        this.syncSingleWorkAreaAutoOpen()
      },
    },
    mSections(newVal) {
      if (!Array.isArray(newVal) || !newVal.length) {
        this.singleIndex = 0
        return
      }
      if (this.singleIndex < 0 || this.singleIndex >= newVal.length) {
        this.singleIndex = 0
      }
    },
    singleOverlayDataUrl() {
      this.$nextTick(() => this.syncSingleOverlayDisplayMetrics())
    },
    singleOverlayHistoryIndex() {
      this.$nextTick(() => this.syncSingleOverlayDisplayMetrics())
    },
    singleWorkAreaVisible() {
      this.$nextTick(() => this.syncSingleOverlayDisplayMetrics())
    },
    singleWorkAreaPreviewZoom() {
      this.$nextTick(() => this.syncSingleOverlayDisplayMetrics())
    },
    singleOverlayVisibleLevels: {
      deep: true,
      handler() {
        this.rebuildSingleOverlayPreviewAlpha()
      },
    },
    singleLayoutIterationMode() {
      this.normalizeSingleLayoutSelectionsForMode(true)
    },
    singleAutoIterationMode() {
      this.closeSingleAutoIterationGrayDialog()
      const max = this.singleAutoIterationMaxDRegions
      const ids = this.singleAutoIterationSelectedRegionIds
      if (Array.isArray(ids) && ids.length > max) {
        const orderMap = new Map(this.singleAutoIterationStartOptions.map((item, index) => [item.region_id, index]))
        const sorted = [...ids].sort((left, right) => (orderMap.get(left) ?? 999) - (orderMap.get(right) ?? 999))
        this.singleAutoIterationSelectedRegionIds = sorted.slice(0, max)
      }
    },
    singleDmtCoarseLayoutEligible(val) {
      if (val === false && this.singleAutoIterationMode === 'full_lite') {
        this.singleAutoIterationMode = 'full'
      }
    },
    singleAutoIterationLastRound: {
      deep: true,
      handler() {
        this.tryMarkAutoIterLowestPickIfFinished()
      },
    },
  },
  mounted() {
    window.addEventListener('resize', this.syncSingleOverlayDisplayMetrics)
    window.addEventListener('click', this.closeSingleReproContextMenu)
  },
  beforeUnmount() {
    this.stopSingleOverlayPolling()
    window.removeEventListener('resize', this.syncSingleOverlayDisplayMetrics)
    window.removeEventListener('click', this.closeSingleReproContextMenu)
  },
  methods: {
    buildRContextEditState(item) {
      const ctx = item?.iter_context || {}
      const useSketch = ctx.use_sketch_input !== false
      return {
        use_sketch_input: useSketch,
        use_original_sketch_as_r: useSketch && ctx.use_original_sketch_as_r === true,
        t_focus_text: ctx.t_focus_text || '',
        main_content: ctx.main_content || '',
        layout_regions_text: ctx.layout_regions_text || '',
        reading_order: ctx.reading_order || '',
        handwriting_printing_relation: ctx.handwriting_printing_relation || '',
        annotation_section: ctx.annotation_section || '',
        continuity_text: ctx.continuity_text || '',
        m_verification_text: ctx.m_verification_text || '',
        color_instruction: ctx.color_instruction || '',
        ratio_instruction: ctx.ratio_instruction || '',
      }
    },
    applyRItemState(item, options = {}) {
      if (!item?.unit_id) return
      this.rItemLocalOverrides = {
        ...this.rItemLocalOverrides,
        [item.unit_id]: {
          ...item,
          iter_context: item?.iter_context ? { ...item.iter_context } : {},
        },
      }
      if (options.syncContext) {
        this.rContextEdits = {
          ...this.rContextEdits,
          [item.unit_id]: this.buildRContextEditState(item),
        }
      }
      this.$nextTick(() => this.syncSingleOverlayDisplayMetrics())
    },
    cloneSingleOverlayItem(item) {
      if (!item || typeof item !== 'object') return null
      return {
        ...item,
        auto_iteration: item?.auto_iteration ? JSON.parse(JSON.stringify(item.auto_iteration)) : null,
        regions: Array.isArray(item.regions)
          ? item.regions.map(region => ({
            ...region,
            bbox: region?.bbox ? { ...region.bbox } : null,
          }))
          : [],
      }
    },
    syncSingleLayoutRegionDrafts(regions) {
      const currentDrafts = this.singleLayoutRegionDrafts || {}
      const nextDrafts = {}
      for (const region of (Array.isArray(regions) ? regions : [])) {
        const regionId = region?.region_id || ''
        if (!regionId) continue
        const prev = currentDrafts[regionId] || {}
        const recognized = this.normalizeSingleRecognition(region?.recognition)
        nextDrafts[regionId] = {
          selected: Boolean(prev.selected),
          recognition: ['white', 'gray', 'black'].includes(prev.recognition) ? prev.recognition : (recognized || 'gray'),
          user_instruction: prev.user_instruction || '',
        }
      }
      this.singleLayoutRegionDrafts = nextDrafts
      this.normalizeSingleLayoutSelectionsForMode(false)
    },
    syncSingleAutoIterationSelections(regions) {
      const dRegionIds = (Array.isArray(regions) ? regions : [])
        .filter(region => (region?.level || '').toLowerCase() === 'd')
        .map(region => region?.region_id)
        .filter(Boolean)
      const validSet = new Set(dRegionIds)
      const orderedIds = []
      for (const regionId of dRegionIds) {
        if (this.singleAutoIterationSelectedRegionIds.includes(regionId) && !orderedIds.includes(regionId)) {
          orderedIds.push(regionId)
        }
        if (orderedIds.length >= this.singleAutoIterationMaxDRegions) break
      }
      const nextIds = orderedIds.filter(regionId => validSet.has(regionId))
      const prevIds = Array.isArray(this.singleAutoIterationSelectedRegionIds) ? this.singleAutoIterationSelectedRegionIds : []
      if (nextIds.length !== prevIds.length || nextIds.some((regionId, index) => regionId !== prevIds[index])) {
        this.singleAutoIterationSelectedRegionIds = nextIds
      }
    },
    normalizeSingleLayoutSelectionsForMode(notify = false) {
      if (this.singleLayoutIterationMode !== 'crop') return
      const selectedRegions = this.selectedSingleLayoutRegions || []
      if (selectedRegions.length <= 1) return
      const keepRegionId = selectedRegions[0]?.region_id || ''
      if (!keepRegionId) return
      const nextDrafts = { ...this.singleLayoutRegionDrafts }
      Object.keys(nextDrafts).forEach(regionId => {
        nextDrafts[regionId] = {
          ...nextDrafts[regionId],
          selected: regionId === keepRegionId,
        }
      })
      this.singleLayoutRegionDrafts = nextDrafts
      if (notify && this.$message?.warning) {
        this.$message.warning('局部裁切模式每次只允许一个版面，已自动保留排序后的第一个选区。')
      }
    },
    applySingleOverlayItemState(overlayItem, options = {}) {
      const cloned = this.cloneSingleOverlayItem(overlayItem)
      this.singleOverlayItemLocal = cloned
      this.syncSingleLayoutRegionDrafts(cloned?.regions || [])
      this.syncSingleAutoIterationSelections(cloned?.regions || [])
      this.syncSingleAutoIterationStartRegion(cloned?.regions || [])
      if (options.forceInstructionText) {
        this.singleOverlayInstructionText = cloned?.instruction_text || ''
      } else if (!this.singleOverlayInstructionText && cloned?.instruction_text) {
        this.singleOverlayInstructionText = cloned.instruction_text
      }
      this.$nextTick(() => this.syncSingleOverlayDisplayMetrics())
    },
    resetSingleOverlayVisibleLevels() {
      this.singleOverlayVisibleLevels = { ...DEFAULT_SINGLE_OVERLAY_VISIBLE_LEVELS }
    },
    normalizeSingleOverlayLevel(level) {
      const normalized = String(level || '').toLowerCase()
      return SINGLE_OVERLAY_LEVELS.includes(normalized) ? normalized : ''
    },
    getSingleOverlayLevelLabel(level) {
      const normalized = this.normalizeSingleOverlayLevel(level)
      return SINGLE_LAYOUT_REGION_META[normalized]?.label || `${String(level || '').toUpperCase()}级版面`
    },
    getSingleOverlayLevelVisibilityText(level) {
      return this.isSingleOverlayLevelVisible(level) ? '显示中' : '已隐藏'
    },
    normalizeSingleRecognition(value) {
      const normalized = String(value || '').toLowerCase()
      return ['white', 'gray', 'black'].includes(normalized) ? normalized : ''
    },
    getSingleRecognitionLabel(recognition) {
      const normalized = this.normalizeSingleRecognition(recognition)
      if (normalized === 'white') return '白区'
      if (normalized === 'gray') return '灰区'
      if (normalized === 'black') return '黑区'
      return ''
    },
    getSingleAutoDecisionLabel(decision) {
      const normalized = String(decision || '').toLowerCase()
      if (normalized === 'iterated') return '已迭代'
      if (normalized === 'skipped') return '已跳过'
      if (normalized === 'failed') return '失败'
      if (normalized === 'selected') return '已选中'
      return ''
    },
    getSingleRegionDisplayName(region) {
      return region?.title || region?.region_id || '未命名版面'
    },
    getSingleLayoutRegionMetaText(region) {
      const parts = [this.formatSingleLayoutRegionPosition(region)]
      const regionId = region?.region_id || ''
      const draftRecognition = this.singleLayoutRegionDrafts?.[regionId]?.recognition
      const recognitionLabel = this.getSingleRecognitionLabel(draftRecognition || region?.recognition)
      if (recognitionLabel) parts.push(recognitionLabel)
      const autoDecision = this.getSingleAutoDecisionLabel(region?.auto_state)
      if (region?.auto_selected && autoDecision) parts.push(autoDecision)
      return parts.join(' · ')
    },
    getSingleOverlayRegionTagText(region) {
      const parts = [this.getSingleRegionDisplayName(region)]
      const regionId = region?.region_id || ''
      const draftRecognition = this.singleLayoutRegionDrafts?.[regionId]?.recognition
      const recognitionLabel = this.getSingleRecognitionLabel(draftRecognition || region?.recognition)
      if (recognitionLabel) parts.push(recognitionLabel)
      const autoDecision = this.getSingleAutoDecisionLabel(region?.auto_state)
      if (region?.auto_selected && autoDecision) parts.push(autoDecision)
      return parts.join(' · ')
    },
    normalizeSingleReasonText(value, maxLength = 88) {
      const normalized = String(value || '').replace(/\s+/g, ' ').trim()
      if (!normalized) return ''
      return normalized.length > maxLength ? `${normalized.slice(0, maxLength)}...` : normalized
    },
    getSingleLayoutRegionEditorHint(region) {
      const parts = []
      const recognizedText = String(region?.recognized_text || '').trim()
      if (recognizedText) parts.push(`识别文字：${recognizedText}`)
      const recognitionReason = this.normalizeSingleReasonText(region?.recognition_error || region?.recognition_reason)
      if (!recognizedText && recognitionReason) parts.push(`识别说明：${recognitionReason}`)
      const contextLabel = String(region?.context_label || '').trim()
      if (contextLabel) parts.push(`命中上下文：${contextLabel}`)
      const autoDecision = this.getSingleAutoDecisionLabel(region?.auto_state)
      if (region?.auto_selected && autoDecision) parts.push(`最近一轮：${autoDecision}`)
      const autoReason = this.normalizeSingleReasonText(region?.auto_state_reason)
      if (region?.auto_selected && autoReason) parts.push(`原因：${autoReason}`)
      return parts.join(' · ')
    },
    getSingleAutoRoundItemMeta(item) {
      const parts = []
      const recognitionLabel = this.getSingleRecognitionLabel(item?.recognition)
      if (recognitionLabel) parts.push(recognitionLabel)
      const autoDecision = this.getSingleAutoDecisionLabel(item?.decision)
      if (autoDecision) parts.push(autoDecision)
      const targetText = this.normalizeSingleReasonText(item?.target_text, 36)
      if (targetText && String(item?.decision || '').toLowerCase() === 'iterated') parts.push(`目标：${targetText}`)
      const decisionReason = this.normalizeSingleReasonText(item?.decision_reason, 48)
      if (decisionReason && String(item?.decision || '').toLowerCase() === 'failed') parts.push(`原因：${decisionReason}`)
      return parts.join(' · ')
    },
    syncSingleAutoIterationStartRegion(regions) {
      const dRegions = (Array.isArray(regions) ? regions : [])
        .filter(region => (region?.level || '').toLowerCase() === 'd')
        .sort((left, right) => {
          const leftRank = Number(left?.rank || 0)
          const rightRank = Number(right?.rank || 0)
          if (leftRank !== rightRank) return leftRank - rightRank
          const leftY = Number(left?.bbox?.y || 0)
          const rightY = Number(right?.bbox?.y || 0)
          if (leftY !== rightY) return leftY - rightY
          const leftX = Number(left?.bbox?.x || 0)
          const rightX = Number(right?.bbox?.x || 0)
          if (leftX !== rightX) return leftX - rightX
          return String(left?.region_id || '').localeCompare(String(right?.region_id || ''))
        })
      const validIds = new Set(dRegions.map(region => region?.region_id).filter(Boolean))
      const cursorId = validIds.has(this.singleAutoIterationCursorRegionId) ? this.singleAutoIterationCursorRegionId : ''
      if (!validIds.has(this.singleAutoIterationStartRegionId)) {
        this.singleAutoIterationStartRegionId = cursorId || dRegions[0]?.region_id || ''
      }
      if (this.singleAutoIterationContinueFromCursor) {
        this.singleAutoIterationStartRegionId = cursorId || dRegions[0]?.region_id || ''
      }
    },
    isSingleAutoIterationRegionSelected(regionId) {
      return this.singleAutoIterationSelectedRegionIds.includes(regionId)
    },
    canSelectSingleAutoIterationRegion(region) {
      const regionId = region?.region_id || ''
      if (!regionId) return false
      if (this.isSingleAutoIterationRegionSelected(regionId)) return true
      return this.selectedSingleAutoIterationRegions.length < this.singleAutoIterationMaxDRegions
    },
    toggleSingleAutoIterationRegion(region) {
      const regionId = region?.region_id || ''
      if (!regionId || !this.singleOverlayViewingCurrent) return
      if (this.isSingleAutoIterationRegionSelected(regionId)) {
        this.singleAutoIterationSelectedRegionIds = this.singleAutoIterationSelectedRegionIds.filter(item => item !== regionId)
        return
      }
      if (!this.canSelectSingleAutoIterationRegion(region)) {
        const cap = this.singleAutoIterationMaxDRegions
        if (this.$message?.warning) {
          this.$message.warning(
            this.singleAutoIterationMode === 'full_lite'
              ? `轻量全自动每轮最多手动选择 ${cap} 个 D 版面`
              : `自动迭代每轮最多手动选择 ${cap} 个 D 版面`,
          )
        }
        return
      }
      const nextIds = [...this.singleAutoIterationSelectedRegionIds, regionId]
      const orderMap = new Map(this.singleAutoIterationStartOptions.map((item, index) => [item.region_id, index]))
      nextIds.sort((left, right) => (orderMap.get(left) ?? 999) - (orderMap.get(right) ?? 999))
      this.singleAutoIterationSelectedRegionIds = nextIds.slice(0, this.singleAutoIterationMaxDRegions)
    },
    clearSingleAutoIterationSelections() {
      this.singleAutoIterationSelectedRegionIds = []
    },
    buildSingleAutoIterationGrayDrafts(preview) {
      const drafts = {}
      const grayRegions = Array.isArray(preview?.gray_regions) ? preview.gray_regions : []
      grayRegions.forEach(region => {
        const regionId = String(region?.region_id || '').trim()
        if (!regionId) return
        drafts[regionId] = {
          choice_type: 'default',
          target_text: String(region?.default_target_text || region?.recognized_text || '').trim(),
        }
      })
      return drafts
    },
    getSingleAutoIterationModelText(region, modelName) {
      return String(region?.model_predictions?.[modelName]?.text || '').trim()
    },
    getSingleGrayQualityLabel(region) {
      if (this.normalizeSingleRecognition(region?.recognition) !== 'gray') return ''
      const quality = String(region?.gray_quality_hint || '').trim().toLowerCase()
      if (quality === 'preferred') return '优质'
      return '普通'
    },
    hasSingleAutoIterationAdjudication(region) {
      const adj = region?.disagreement_adjudication
      if (!adj || typeof adj !== 'object') return false
      const hasSelfChecks = Array.isArray(adj.self_checks) && adj.self_checks.length > 0
      const hasJudges = Array.isArray(adj.judges) && adj.judges.length > 0
      const hasVotes = Number(adj?.votes?.option1 || 0) > 0 || Number(adj?.votes?.option2 || 0) > 0 || Number(adj?.votes?.neither || 0) > 0
      const hasFinalVote = String(adj.final_vote || '').trim().length > 0
      const hasArbitration = Boolean(adj?.arbitration?.success) || String(adj?.arbitration?.vote || '').trim().length > 0
      const hasCorrected = String(adj.corrected_text || '').trim().length > 0 || String(adj?.arbitration?.corrected_text || '').trim().length > 0
      return hasSelfChecks || hasJudges || hasVotes || hasFinalVote || hasArbitration || hasCorrected
    },
    getSingleDRegionProbeModelLine(modelName) {
      const p = this.singleDRegionProbeDialogPayload
      const m = p?.model_predictions?.[modelName]
      if (!m) return ''
      const t = String(m.text || '').trim()
      const sim = m.vocab_similarity != null && m.vocab_similarity !== '' ? `（词表相似度 ${m.vocab_similarity}）` : ''
      if (!t && m.error) return `（失败）${m.error}`
      return t ? `${t} ${sim}`.trim() : ''
    },
    getSingleDRegionProbeReasoningPreview() {
      const v = this.singleDRegionProbeDialogPayload?.snippet_raw_voting
      const preds = v?.predictions
      if (!preds || typeof preds !== 'object') return ''
      const parts = []
      ;['gemini', 'qwen'].forEach((alias) => {
        const block = preds[alias]
        const r = String(block?.reasoning || '').trim()
        if (r) parts.push(`【${alias}】\n${r}`)
      })
      const text = parts.join('\n\n---\n\n')
      return text.length > 12000 ? `${text.slice(0, 12000)}…` : text
    },
    formatSingleDRegionJudgeFinalVote(vote) {
      const v = String(vote || '').trim().toLowerCase()
      if (v === 'option1') return '投 1 号答案'
      if (v === 'option2') return '投 2 号答案'
      if (v === 'neither') return '都不对'
      return '无明确结论'
    },
    formatSingleDRegionSelfCheckDetails(items) {
      const rows = Array.isArray(items) ? items : []
      if (!rows.length) return '（无自检明细）'
      return rows.map((item, index) => {
        const judge = item?.judge || `self_check_${index + 1}`
        const confirmed = String(item?.confirmed || '').trim().toLowerCase()
        const verdict = confirmed === 'true' ? '已确认原结果' : (confirmed === 'false' ? '已修正结果' : '无明确结论')
        const finalText = String(item?.final_text || '').trim()
        const reason = String(item?.reason || item?.error || '').trim()
        return [
          `【${judge}】`,
          `- 结论：${verdict}`,
          finalText ? `- 最终结果：${finalText}` : '',
          reason ? `- 说明：${reason}` : '',
        ].filter(Boolean).join('\n')
      }).join('\n\n')
    },
    getSingleDRegionFinalSuggestedText(payload) {
      const p = payload || {}
      const adj = p.disagreement_adjudication || {}
      const option1 = String(adj.option1_text || '').trim()
      const option2 = String(adj.option2_text || '').trim()
      const arbVote = String(adj?.arbitration?.vote || '').trim().toLowerCase()
      const arbText = String(adj?.arbitration?.corrected_text || '').trim()
      if (arbVote === 'neither' && arbText) return arbText
      if (arbVote === 'option1' && option1) return option1
      if (arbVote === 'option2' && option2) return option2
      const finalVote = String(adj.final_vote || '').trim().toLowerCase()
      const corrected = String(adj.corrected_text || '').trim()
      if (finalVote === 'neither' && corrected) return corrected
      if (finalVote === 'option1' && option1) return option1
      if (finalVote === 'option2' && option2) return option2
      if (corrected) return corrected
      return String(p.recognized_text || '').trim()
    },
    formatSingleDRegionJudgeDetails(judges) {
      const items = Array.isArray(judges) ? judges : []
      if (!items.length) return '（无裁判明细）'
      return items.map((item, index) => {
        const judge = item?.judge || `judge_${index + 1}`
        const vote = this.formatSingleDRegionJudgeFinalVote(item?.vote)
        const corrected = String(item?.corrected_text || '').trim()
        const reason = String(item?.reason || item?.error || '').trim()
        return [
          `【${judge}】`,
          `- 投票：${vote}`,
          corrected ? `- 建议结果：${corrected}` : '',
          reason ? `- 说明：${reason}` : '',
        ].filter(Boolean).join('\n')
      }).join('\n\n')
    },
    async runSingleDRegionRecognitionProbe() {
      const username = localStorage.getItem('userId')
      const analysisId = this.activeAnalysisId
      const unitId = this.singleWorkAreaItem?.unit_id || ''
      const regionId = this.singleDRegionProbeRegionId
      if (!username || !analysisId || !unitId || !regionId) {
        if (this.$message?.warning) this.$message.warning('请先选择当前分析页与 D 版面')
        return
      }
      try {
        this.singleDRegionProbeBusy = true
        const previewResp = await recognizeCIDRegion({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          region_id: regionId,
          sketch_preprocess: this.singleSnippetSketchPreprocess,
          use_recognition_context: this.singleSnippetUseRecognitionContext,
          preview_only: true,
        })
        if (previewResp.error_num !== 0) {
          if (this.$message?.error) this.$message.error(previewResp.msg || '获取识别裁切图失败')
          return
        }
        const cropB64 = String(previewResp.model_input_crop_b64 || '').trim()
        if (!cropB64) {
          if (this.$message?.error) this.$message.error('未获取到识别裁切图')
          return
        }
        this.singleDRegionProbeCropPreviewDataUrl = cropB64.startsWith('data:') ? cropB64 : `data:image/png;base64,${cropB64}`
        this.singleDRegionProbeConfirmVisible = true
      } catch (e) {
        console.error('[CI] runSingleDRegionRecognitionProbe preview', e)
        if (this.$message?.error) this.$message.error('获取识别裁切图失败：' + (e.message || e))
      } finally {
        this.singleDRegionProbeBusy = false
      }
    },
    async runSingleDRegionConfidenceBatch() {
      const username = localStorage.getItem('userId')
      const analysisId = this.activeAnalysisId
      const unitId = this.singleWorkAreaItem?.unit_id || ''
      if (!username || !analysisId || !unitId) {
        if (this.$message?.warning) this.$message.warning('请先进入当前页工作区')
        return
      }
      try {
        this.singleDRegionConfidenceBusy = true
        const resp = await evaluateCIDRegionConfidenceBatch({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          confidence_model: this.singleDRegionConfidenceModel,
        })
        if (resp.error_num === 1 && resp.generating) {
          if (this.$message?.warning) this.$message.warning('该页复现图正在处理中，请稍等')
          return
        }
        if (resp.error_num !== 0) {
          if (this.$message?.error) this.$message.error(resp.msg || 'D区置信度评估失败')
          return
        }
        this.singleDRegionConfidenceResultPath = String(resp.result_file_path || '').trim()
        this.singleDRegionConfidenceResults = Array.isArray(resp.results) ? resp.results : []
        if (resp.model) {
          const modelText = String(resp.model || '').toLowerCase()
          this.singleDRegionConfidenceModel = modelText.includes('gemini') ? 'gemini' : 'qwen'
        }
        if (this.$message?.success) this.$message.success('D区置信度评估完成')
      } catch (e) {
        console.error('[CI] runSingleDRegionConfidenceBatch', e)
        if (this.$message?.error) this.$message.error('D区置信度评估失败：' + (e.message || e))
      } finally {
        this.singleDRegionConfidenceBusy = false
      }
    },
    async loadSingleDRegionConfidenceResult() {
      const username = localStorage.getItem('userId')
      const analysisId = this.activeAnalysisId
      const unitId = this.singleWorkAreaItem?.unit_id || this.singleWorkAreaUnitId || ''
      if (!username || !analysisId || !unitId) return
      try {
        const resp = await getCIDRegionConfidenceResult({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
        })
        if (resp.error_num !== 0) return
        this.singleDRegionConfidenceResultPath = String(resp.result_file_path || '').trim()
        this.singleDRegionConfidenceResults = Array.isArray(resp.results) ? resp.results : []
        if (resp.model) {
          const modelText = String(resp.model || '').toLowerCase()
          this.singleDRegionConfidenceModel = modelText.includes('gemini') ? 'gemini' : 'qwen'
        }
      } catch (e) {
        // 文件不存在属于正常情况，静默即可
      }
    },
    async runAutoIterateByLowestConfidence(autoRun = false) {
      const username = localStorage.getItem('userId')
      const analysisId = this.activeAnalysisId
      const unitId = this.singleWorkAreaItem?.unit_id || this.singleWorkAreaUnitId || ''
      if (!username || !analysisId || !unitId) return
      try {
        const resp = await pickCIAutoIterateRegionsByConfidence({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          limit: 9,
        })
        if (resp.error_num !== 0) {
          if (this.$message?.warning) this.$message.warning(resp.msg || '未找到可用于自动挑选的D区')
          return
        }
        const ids = Array.isArray(resp.selected_region_ids) ? resp.selected_region_ids.filter(Boolean) : []
        if (!ids.length) {
          if (this.$message?.warning) this.$message.warning('没有可用的未取用D区（或置信度文件缺失）')
          return
        }
        this.singleAutoIterationMode = 'full'
        this.singleAutoIterationSelectedRegionIds = ids
        this.singleSnippetSketchPreprocess = false
        this.singleSnippetUseRecognitionContext = false
        if (autoRun) {
          const payload = this.buildSingleAutoIterationExecutionPayload()
          this.singleAutoIterLowestPickPending = {
            analysisId,
            unitId,
            selectedRegionIds: ids,
          }
          this.$emit('auto-iterate-reproduction-round', payload)
          return
        }
        if (this.$message?.success) this.$message.success(`已自动选中最低置信度前${ids.length}个D区，可手动调整后再点“按所选 D 版面全自动迭代”`)
      } catch (e) {
        if (this.$message?.error) this.$message.error('按最低置信度自动选取失败：' + (e.message || e))
      }
    },
    async tryMarkAutoIterLowestPickIfFinished() {
      const pending = this.singleAutoIterLowestPickPending
      if (!pending) return
      const lastRound = this.singleAutoIterationLastRound || {}
      if (!lastRound || typeof lastRound !== 'object') return
      const unitId = String(lastRound.unit_id || '')
      if (unitId && unitId !== String(pending.unitId || '')) return
      const selectedIds = Array.isArray(lastRound.selected_region_ids) ? lastRound.selected_region_ids.map(id => String(id || '').trim()).filter(Boolean) : []
      if (!selectedIds.length) return
      const pendingSorted = [...(pending.selectedRegionIds || [])].map(id => String(id || '').trim()).filter(Boolean).sort().join(',')
      const currentSorted = [...selectedIds].sort().join(',')
      if (!pendingSorted || pendingSorted !== currentSorted) return
      const failed = Array.isArray(lastRound.failed_region_ids) ? lastRound.failed_region_ids.filter(Boolean) : []
      const username = localStorage.getItem('userId')
      const status = failed.length ? 'failed' : 'success'
      try {
        await markCIAutoIterateRegionsUsed({
          username,
          analysis_id: pending.analysisId,
          unit_id: pending.unitId,
          region_ids: pending.selectedRegionIds,
          status,
          note: failed.length ? 'auto_iter_round_has_failed_regions' : 'auto_iter_round_success',
        })
      } catch (e) {
        // 标记失败不阻断主流程
      } finally {
        this.singleAutoIterLowestPickPending = null
      }
    },
    async waitSingleOverlayGenerateDone(timeoutMs = 240000) {
      const started = Date.now()
      while (Date.now() - started < timeoutMs) {
        const username = localStorage.getItem('userId') || ''
        const resp = await getCIOverlayStatus({
          username,
          analysis_id: this.activeAnalysisId,
          unit_id: this.singleWorkAreaUnitId,
        })
        const data = resp.data || resp
        const status = String(data?.status || 'idle')
        if (status === 'success') {
          await this.syncSingleOverlayHistoryFromServer()
          return
        }
        if (status === 'failed') {
          throw new Error(String(data?.error || data?.msg || 'overlay_generate_failed'))
        }
        await new Promise(resolve => setTimeout(resolve, 1500))
      }
      throw new Error('overlay_generate_timeout')
    },
    async waitAutoIterRoundDone(timeoutMs = 20 * 60 * 1000) {
      const started = Date.now()
      while (Date.now() - started < timeoutMs) {
        const lastRound = this.singleAutoIterationLastRound || {}
        const selected = Array.isArray(lastRound.selected_region_ids) ? lastRound.selected_region_ids : []
        const finishedAt = String(lastRound.finished_at || '').trim()
        if (selected.length && finishedAt) return lastRound
        await new Promise(resolve => setTimeout(resolve, 1800))
      }
      throw new Error('auto_iter_round_timeout')
    },
    async waitCITaskDone(taskId, { unitId = '', analysisId = '', timeoutMs = 25 * 60 * 1000 } = {}) {
      const started = Date.now()
      while (Date.now() - started < timeoutMs) {
        const resp = await getCIProgress(taskId)
        if (resp.error_num !== 0) throw new Error(resp.msg || '查询进度失败')
        if (resp.error) throw new Error(resp.error)
        if (resp.completed) {
          if (unitId && this.singleWorkAreaUnitId === unitId) {
            const aid = analysisId || this.liteBatchScopedAnalysisId || this.activeAnalysisId
            await this.syncSingleOverlayHistoryForAnalysis(aid, unitId)
          }
          return resp
        }
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
      throw new Error('task_timeout')
    },
    openLiteBatchWorkflowDialog() {
      if (this.liteBatchRunning) return
      this.liteBatchFinished = false
      this.liteBatchProgress = 0
      this.liteBatchStatus = ''
      this.liteBatchResults = []
      this.liteBatchPhase = 'pick_files'
      this.liteBatchPoolPickFileNames = []
      this.liteBatchSelectedFileNames = []
      this.liteBatchCandidatesResolved = []
      this.liteBatchCandidatesLoading = false
      this.liteBatchDialogVisible = true
    },
    closeLiteBatchWorkflowDialog() {
      if (this.liteBatchRunning) return
      this.liteBatchDialogVisible = false
      this.liteBatchFinished = false
      this.liteBatchPhase = 'pick_files'
    },
    liteBatchSelectAllPool() {
      this.liteBatchPoolPickFileNames = [...this.liteBatchPickPoolImages]
    },
    liteBatchClearPoolPick() {
      this.liteBatchPoolPickFileNames = []
    },
    liteBatchBackToPoolPick() {
      if (this.liteBatchCandidatesLoading || this.liteBatchRunning) return
      this.liteBatchPhase = 'pick_files'
      this.liteBatchSelectedFileNames = []
      this.liteBatchCandidatesResolved = []
    },
    async confirmLiteBatchPoolAndResolve() {
      const files = [...(this.liteBatchPoolPickFileNames || [])]
      if (!files.length) {
        if (this.$message?.warning) this.$message.warning('请先勾选要查询的图片')
        return
      }
      const ok = await this.refreshLiteBatchCandidates(files)
      if (!ok) return
      this.liteBatchPhase = 'pick_batch'
      this.liteBatchSelectedFileNames = []
      const n = this.liteBatchSelectableFileNames.length
      if (this.$message?.info) {
        this.$message.info(n ? `解析完成：${n} 张可批量处理` : '解析完成：当前所选图片均不可批量处理（见各行说明）')
      }
    },
    liteBatchSelectAllCandidates() {
      this.liteBatchSelectedFileNames = [...this.liteBatchSelectableFileNames]
    },
    liteBatchClearSelection() {
      this.liteBatchSelectedFileNames = []
    },
    async prepareLiteBatchFileContext(candidate) {
      const analysisId = candidate?.analysisId || ''
      const unitId = candidate?.unitId || ''
      if (!analysisId || !unitId) throw new Error('无效的分析或 unit_id')
      this.liteBatchScopedAnalysisId = analysisId
      this.singleWorkAreaUnitId = unitId
      this.singleWorkAreaVisible = true
      const result = await this.fetchCIResult(analysisId)
      const overlayItem = (result?.overlay_layer?.items || []).find(item => item?.unit_id === unitId) || null
      this.applySingleOverlayItemState(overlayItem, { forceInstructionText: true })
      this.singleAutoIterationMode = 'full_lite'
      this.singleSnippetSketchPreprocess = false
      this.singleSnippetUseRecognitionContext = false
      this.singleAutoIterationSelectedRegionIds = []
      await this.syncSingleOverlayHistoryForAnalysis(analysisId, unitId)
    },
    async runLiteBatchFullLiteOcr(candidate, allDIds, rec) {
      const chunkSize = SINGLE_AUTO_ITERATION_D_LIMIT_LITE
      const chunks = []
      for (let i = 0; i < allDIds.length; i += chunkSize) {
        chunks.push(allDIds.slice(i, i + chunkSize))
      }
      const username = localStorage.getItem('userId') || ''
      const analysisId = candidate.analysisId
      for (let ci = 0; ci < chunks.length; ci += 1) {
        const chunk = chunks[ci]
        this.singleAutoIterationSelectedRegionIds = [...chunk]
        rec.logs.push(`识字批次 ${ci + 1}/${chunks.length}：${chunk.length} 个 D 区`)
        const payload = this.buildSingleAutoIterationExecutionPayload()
        const resp = await autoIterateCIReproductionRound({
          username,
          analysis_id: analysisId,
          unit_id: candidate.unitId,
          mode: payload.mode,
          selected_region_ids: payload.selectedRegionIds,
          continue_from_cursor: false,
          image_quality: payload.imageQuality,
          iter_context: payload.iterContext,
          sketch_preprocess: false,
          use_recognition_context: false,
        })
        if (resp.error_num === 1 && resp.generating) throw new Error('该页复现图正在处理中')
        if (resp.error_num !== 0) throw new Error(resp.msg || '启动轻量识字失败')
        await this.waitCITaskDone(resp.task_id, { unitId: candidate.unitId, analysisId: candidate.analysisId })
      }
    },
    async runLiteBatchPreviewAndCache(candidate) {
      const username = localStorage.getItem('userId') || ''
      const { analysisId, unitId } = candidate
      const resp = await previewRefineCISingleImageUnderstandingFromDLite({
        username,
        analysis_id: analysisId,
        unit_id: unitId,
        refine_model: 'gemini',
        save_preview_cache: true,
        context_docs: [],
        context_card_ids: [],
      })
      if (resp?.error_num !== 0) throw new Error(resp?.msg || '预览三层理解失败')
      return String(resp.cache_rel_path || '').trim()
    },
    liteBatchCacheKey(analysisId, unitId) {
      const aid = String(analysisId || '').trim()
      const uid = String(unitId || '').trim()
      return aid && uid ? `${aid}::${uid}` : uid
    },
    async refreshLiteBatchCacheStatus(unitId, analysisId) {
      if (!unitId) return
      const username = localStorage.getItem('userId') || ''
      const aid = analysisId || this.liteBatchScopedAnalysisId || this.activeAnalysisId
      if (!username || !aid) return
      const cacheKey = this.liteBatchCacheKey(aid, unitId)
      try {
        const resp = await getCIDLiteImageUnderstandingPreviewCache({ username, analysis_id: aid, unit_id: unitId })
        this.liteBatchUnitCacheMap = {
          ...this.liteBatchUnitCacheMap,
          [cacheKey]: resp?.error_num === 0 && resp?.has_cache === true,
        }
      } catch (_) {
        this.liteBatchUnitCacheMap = { ...this.liteBatchUnitCacheMap, [cacheKey]: false }
      }
    },
    async runLiteBatchWorkflow() {
      if (this.liteBatchPhase !== 'pick_batch') {
        if (this.$message?.warning) this.$message.warning('请先查询所选图片的 CI 状态')
        return
      }
      const fileNames = [...(this.liteBatchSelectedFileNames || [])]
      if (!fileNames.length) {
        if (this.$message?.warning) this.$message.warning('请至少选择一张可处理的图片')
        return
      }
      this.liteBatchRunning = true
      this.liteBatchFinished = false
      this.liteBatchResults = []
      const total = fileNames.length
      let idx = 0
      try {
        for (const fileName of fileNames) {
          idx += 1
          const row = this.liteBatchCandidatesResolved.find(item => item.fileName === fileName)
          const unitId = row?.unitId || ''
          const analysisId = row?.analysisId || ''
          const rec = { fileName, unitId, analysisId, title: fileName, liteOcrOk: false, previewOk: false, error: '', cachePath: '', logs: [] }
          this.liteBatchResults.push(rec)
          this.liteBatchProgress = Math.round(((idx - 1) / total) * 100)
          this.liteBatchStatus = `[${idx}/${total}] ${fileName}：准备中…`
          try {
            if (!row?.selectable || !unitId || !analysisId) throw new Error(row?.note || '未找到该图的单图 CI 分析或覆盖层无 D 版面')
            rec.logs.push(`加载单图分析 ${analysisId}`)
            await this.prepareLiteBatchFileContext(row)
            const dIds = this.singleAutoIterationStartOptions.map(region => region.region_id).filter(Boolean)
            if (!dIds.length) throw new Error('覆盖层无可用 D 版面')
            rec.logs.push(`设置：full_lite · 清晰化关 · 上下文关 · 共 ${dIds.length} 个 D 区`)
            this.liteBatchStatus = `[${idx}/${total}] ${fileName}：轻量识字…`
            await this.runLiteBatchFullLiteOcr(row, dIds, rec)
            rec.liteOcrOk = true
            rec.logs.push('轻量识字完成')
            this.liteBatchStatus = `[${idx}/${total}] ${fileName}：Gemini 校正三层理解…`
            const cachePath = await this.runLiteBatchPreviewAndCache(row)
            rec.previewOk = true
            rec.cachePath = cachePath
            rec.logs.push(`预览已写入当日缓存${cachePath ? `（${cachePath}）` : ''}`)
            const cacheKey = this.liteBatchCacheKey(analysisId, unitId)
            this.liteBatchUnitCacheMap = { ...this.liteBatchUnitCacheMap, [cacheKey]: true }
          } catch (e) {
            rec.error = e?.message || String(e)
            rec.logs.push(`失败：${rec.error}`)
          }
          this.liteBatchProgress = Math.round((idx / total) * 100)
        }
        const okCount = this.liteBatchResults.filter(row => row.liteOcrOk && row.previewOk).length
        this.liteBatchStatus = `批量完成：${okCount}/${total} 张全部成功`
        this.liteBatchFinished = true
        if (this.$message?.success) this.$message.success(this.liteBatchStatus)
      } finally {
        this.liteBatchRunning = false
        this.liteBatchScopedAnalysisId = ''
      }
    },
    openSingleDLiteUnderstandingPreviewEntry() {
      if (this.singleReproRefineBusy) return
      if (this.singleDLiteUnderstandingHasTodayCache) {
        this.loadAndShowDLiteUnderstandingPreviewCache()
        return
      }
      this.openSingleDLiteRefineModelDialog('image_understanding')
    },
    async loadAndShowDLiteUnderstandingPreviewCache() {
      const username = localStorage.getItem('userId') || ''
      const analysisId = this.activeAnalysisId
      const unitId = this.singleWorkAreaItem?.unit_id || ''
      if (!username || !analysisId || !unitId) return
      this.singleReproRefineBusy = true
      try {
        const resp = await getCIDLiteImageUnderstandingPreviewCache({ username, analysis_id: analysisId, unit_id: unitId })
        if (resp?.error_num !== 0 || !resp?.has_cache) {
          const cacheKey = this.liteBatchCacheKey(analysisId, unitId)
          this.liteBatchUnitCacheMap = { ...this.liteBatchUnitCacheMap, [cacheKey]: false }
          throw new Error(resp?.msg || '无当日预览缓存')
        }
        this.singleImageUnderstandingPreviewKind = 'd_lite'
        this.singleDLiteRefineModelUsedName = String(resp.refine_model_name || resp.refine_model || 'gemini').trim()
        this.singleImageUnderstandingPreviewText = String(resp.preview_text || '').trim()
        this.singleImageUnderstandingExistingText = String(resp.existing_text || '').trim()
        this.singleImageUnderstandingPreviewSourceFile = String(resp.source_file || '').trim()
        this.singleImageUnderstandingPreviewImgId = Number(resp.imgid || 0)
        this.singleImageUnderstandingPreviewDialogVisible = true
      } catch (e) {
        if (this.$message?.error) this.$message.error(`读取预览缓存失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    async runSingleGlobalAutoWorkflow() {
      if (this.singleGlobalWorkflowRunning) return
      const item = this.singleWorkAreaItem
      if (!item?.unit_id) return
      this.singleGlobalWorkflowRunning = true
      this.singleGlobalWorkflowProgress = 2
      this.singleGlobalWorkflowStatus = '开始：DMT微版面化'
      try {
        this.singleOverlayIncludeTmContext = true
        await this.runSingleOverlayDmtPrompt()
        if (!String(this.singleOverlayInstructionText || '').trim()) throw new Error('dmt_prompt_empty')
        this.singleGlobalWorkflowProgress = 25
        this.singleGlobalWorkflowStatus = '进行中：生成覆盖层'
        await this.startSingleOverlayGenerate()
        await this.waitSingleOverlayGenerateDone()
        this.singleGlobalWorkflowProgress = 48
        this.singleGlobalWorkflowStatus = '进行中：D区识别置信度评估'
        await this.runSingleDRegionConfidenceBatch()
        if (!this.singleDRegionConfidenceResults.length) throw new Error('confidence_result_empty')
        this.singleGlobalWorkflowProgress = 68
        this.singleGlobalWorkflowStatus = '进行中：按最低置信度选D并全自动迭代'
        await this.runAutoIterateByLowestConfidence(true)
        const lastRound = await this.waitAutoIterRoundDone()
        const failed = Array.isArray(lastRound?.failed_region_ids) ? lastRound.failed_region_ids.filter(Boolean) : []
        if (failed.length) {
          this.singleGlobalWorkflowStatus = `完成但有失败区域：${failed.join('、')}`
          this.singleGlobalWorkflowProgress = 95
        } else {
          this.singleGlobalWorkflowStatus = '全流程完成'
          this.singleGlobalWorkflowProgress = 100
        }
      } catch (e) {
        this.singleGlobalWorkflowStatus = `全流程失败：${e.message || e}`
        if (this.$message?.error) this.$message.error(this.singleGlobalWorkflowStatus)
      } finally {
        this.singleGlobalWorkflowRunning = false
      }
    },
    async confirmSingleDRegionRecognitionProbe() {
      const username = localStorage.getItem('userId')
      const analysisId = this.activeAnalysisId
      const unitId = this.singleWorkAreaItem?.unit_id || ''
      const regionId = this.singleDRegionProbeRegionId
      if (!username || !analysisId || !unitId || !regionId) return
      try {
        this.singleDRegionProbeBusy = true
        const resp = await recognizeCIDRegion({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          region_id: regionId,
          sketch_preprocess: this.singleSnippetSketchPreprocess,
          use_recognition_context: this.singleSnippetUseRecognitionContext,
        })
        if (resp.error_num === 1 && resp.generating) {
          if (this.$message?.warning) this.$message.warning('该页复现图正在处理中，请稍等')
          return
        }
        if (resp.error_num !== 0) {
          if (this.$message?.error) this.$message.error(resp.msg || '识字失败')
          return
        }
        this.singleDRegionProbeAuditPath = resp.audit_log_path || ''
        this.singleDRegionProbeDialogPayload = resp.recognition_payload || null
        this.singleDRegionProbeDialogVisible = true
        this.singleDRegionProbeConfirmVisible = false
        if (this.$message?.success) this.$message.success('识字完成')
      } catch (e) {
        console.error('[CI] confirmSingleDRegionRecognitionProbe', e)
        if (this.$message?.error) this.$message.error('识字失败：' + (e.message || e))
      } finally {
        this.singleDRegionProbeBusy = false
      }
    },
    cancelSingleDRegionRecognitionProbe() {
      this.singleDRegionProbeConfirmVisible = false
      this.singleDRegionProbeCropPreviewDataUrl = ''
    },
    closeSingleDRegionProbeDialog() {
      this.singleDRegionProbeDialogVisible = false
      this.singleDRegionProbeDialogPayload = null
      this.singleDRegionProbeAuditPath = ''
      this.singleDRegionProbeConfirmVisible = false
      this.singleDRegionProbeCropPreviewDataUrl = ''
    },
    getSingleAutoIterationGrayResolvedText(region) {
      const draft = this.singleAutoIterationGrayDrafts?.[region?.region_id] || {}
      const choiceType = String(draft.choice_type || 'default').trim().toLowerCase()
      if (choiceType === 'manual') return String(draft.target_text || '').trim()
      if (choiceType === 'gemini' || choiceType === 'qwen') {
        return this.getSingleAutoIterationModelText(region, choiceType) || String(region?.default_target_text || region?.recognized_text || '').trim()
      }
      return String(region?.default_target_text || region?.recognized_text || '').trim()
    },
    closeSingleAutoIterationGrayDialog() {
      this.singleAutoIterationGrayDialogVisible = false
      this.singleAutoIterationPreviewData = null
      this.singleAutoIterationGrayDrafts = {}
    },
    buildSingleAutoIterationExecutionPayload(extra = {}) {
      const item = this.singleWorkAreaItem
      const manualRegionIds = this.selectedSingleAutoIterationRegions.map(region => region.region_id)
      const useManualSelection = manualRegionIds.length > 0
      const startRegionId = (!useManualSelection && !this.singleAutoIterationContinueFromCursor)
        ? (this.singleAutoIterationStartRegionId || this.singleAutoIterationStartOptions[0]?.region_id || '')
        : ''
      const payload = {
        analysisId: this.activeAnalysisId,
        unitId: item?.unit_id || '',
        iterContext: this.buildIterContextPayload(item?.unit_id || ''),
        imageQuality: this.singleWorkAreaImageQuality || 'normal',
        mode: this.singleAutoIterationMode,
        selectedRegionIds: useManualSelection ? manualRegionIds : [],
        continueFromCursor: useManualSelection ? false : this.singleAutoIterationContinueFromCursor,
        startRegionId,
        sketchPreprocess: this.singleSnippetSketchPreprocess,
        useRecognitionContext: this.singleSnippetUseRecognitionContext,
      }
      if (Array.isArray(extra.grayResolutions) && extra.grayResolutions.length) {
        payload.grayResolutions = extra.grayResolutions
      }
      return payload
    },
    buildSingleAutoIterationGrayResolutions() {
      return this.singleAutoIterationPreviewGrayRegions.map(region => {
        const draft = this.singleAutoIterationGrayDrafts?.[region.region_id] || {}
        return {
          region_id: region.region_id,
          choice_type: String(draft.choice_type || 'default').trim().toLowerCase() || 'default',
          target_text: String(draft.target_text || '').trim(),
        }
      })
    },
    async previewSingleAutoIterationRound(payload) {
      const username = localStorage.getItem('userId')
      const analysisId = payload?.analysisId || this.activeAnalysisId
      const unitId = payload?.unitId || this.singleWorkAreaItem?.unit_id || ''
      if (!username || !analysisId || !unitId) return
      try {
        this.singleAutoIterationPreviewing = true
        const resp = await previewCIAutoIterateReproductionRound({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          mode: payload?.mode || 'semi',
          selected_region_ids: Array.isArray(payload?.selectedRegionIds) ? payload.selectedRegionIds : [],
          sketch_preprocess: typeof payload?.sketchPreprocess === 'boolean' ? payload.sketchPreprocess : undefined,
          use_recognition_context: payload?.useRecognitionContext !== false,
        })
        if (resp.error_num === 1 && resp.generating) {
          this.$message.warning('该页复现图正在处理中，请稍等')
          return
        }
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '预览单图自动迭代失败')
          return
        }
        if (!Number(resp.gray_count || 0)) {
          this.$emit('auto-iterate-reproduction-round', payload)
          this.$message.success('本轮没有灰区，已直接加入自动迭代队列')
          return
        }
        this.singleAutoIterationPreviewData = resp
        this.singleAutoIterationGrayDrafts = this.buildSingleAutoIterationGrayDrafts(resp)
        this.singleAutoIterationGrayDialogVisible = true
      } catch (e) {
        console.error('[CI] previewSingleAutoIterationRound error:', e)
        this.$message.error('预览单图自动迭代失败：' + (e.message || e))
      } finally {
        this.singleAutoIterationPreviewing = false
      }
    },
    confirmSingleAutoIterationGrayDialog() {
      const missingManual = this.singleAutoIterationPreviewGrayRegions.find(region => {
        const draft = this.singleAutoIterationGrayDrafts?.[region.region_id] || {}
        return String(draft.choice_type || 'default').trim().toLowerCase() === 'manual' && !String(draft.target_text || '').trim()
      })
      if (missingManual) {
        if (this.$message?.warning) this.$message.warning(`请先填写 ${missingManual.title || missingManual.region_id} 的手动目标文字`)
        return
      }
      const payload = this.buildSingleAutoIterationExecutionPayload({
        grayResolutions: this.buildSingleAutoIterationGrayResolutions(),
      })
      this.closeSingleAutoIterationGrayDialog()
      this.$emit('auto-iterate-reproduction-round', payload)
    },
    getSingleOverlayVisibleSummaryText() {
      return `已显示 ${this.singleOverlayVisibleLevelList.length}/${SINGLE_OVERLAY_LEVELS.length} 层`
    },
    isSingleOverlayLevelVisible(level) {
      const normalized = this.normalizeSingleOverlayLevel(level)
      if (!normalized) return false
      return this.singleOverlayVisibleLevels?.[normalized] !== false
    },
    toggleSingleOverlayVisibleLevel(level) {
      const normalized = this.normalizeSingleOverlayLevel(level)
      if (!normalized) return
      const nextVisible = {
        ...this.singleOverlayVisibleLevels,
        [normalized]: !(this.singleOverlayVisibleLevels?.[normalized] !== false),
      }
      if (!SINGLE_OVERLAY_LEVELS.some(item => nextVisible[item] !== false)) {
        if (this.$message?.warning) this.$message.warning('至少保留一个覆盖层用于预览和点选')
        return
      }
      this.singleOverlayVisibleLevels = nextVisible
    },
    detectSingleOverlayPixelLevel(r, g, b, a) {
      if (a < 16) return ''
      if (r >= 242 && g >= 242 && b >= 242) return ''
      let bestLevel = ''
      let bestDistance = Infinity
      for (const level of SINGLE_OVERLAY_LEVELS) {
        const rgb = SINGLE_LAYOUT_REGION_META[level]?.rgb || []
        if (rgb.length !== 3) continue
        const distance = Math.abs(r - rgb[0]) + Math.abs(g - rgb[1]) + Math.abs(b - rgb[2])
        if (level === 'd') {
          if (r < 116 || r < g + 14 || r < b + 12 || distance > 300) continue
        } else if (level === 'm') {
          if (b < 116 || b < r + 14 || b < g + 8 || distance > 300) continue
        } else {
          if (Math.max(r, b) < 108 || r < g + 6 || b < g + 6 || distance > 320) continue
        }
        if (distance < bestDistance) {
          bestDistance = distance
          bestLevel = level
        }
      }
      return bestLevel
    },
    getSingleOverlayManualSourceRegions(level = this.singleOverlayManualLevel) {
      const normalized = this.normalizeSingleOverlayLevel(level)
      if (!normalized) return this.singleOverlayRegions
      return this.singleOverlayRegions.filter(region => String(region?.level || '').toLowerCase() === normalized)
    },
    getSingleOverlayManualWholeRect(regions = this.singleOverlayManualRegions) {
      const list = this.cloneSingleOverlayManualRegions(regions)
      if (!list.length) return null
      const left = Math.min(...list.map(region => Number(region.x || 0)))
      const top = Math.min(...list.map(region => Number(region.y || 0)))
      const right = Math.max(...list.map(region => Number(region.x || 0) + Number(region.w || 0)))
      const bottom = Math.max(...list.map(region => Number(region.y || 0) + Number(region.h || 0)))
      const w = Math.max(1, right - left)
      const h = Math.max(1, bottom - top)
      return {
        region_id: '__whole_overlay__',
        level: 'all',
        title: '整层覆盖层',
        rank: 0,
        x: left,
        y: top,
        w,
        h,
      }
    },
    selectSingleOverlayManualWhole() {
      const whole = this.getSingleOverlayManualWholeRect()
      if (!whole) return
      this.activateSingleOverlayManualTool('select')
      this.setSingleOverlayManualSelection(whole)
    },
    getSelectedSingleLayoutRegionCount(level) {
      const normalizedLevel = String(level || '').toLowerCase()
      return Object.entries(this.singleLayoutRegionDrafts || {}).reduce((count, [regionId, draft]) => {
        if (!draft?.selected) return count
        const region = this.singleOverlayRegions.find(item => item?.region_id === regionId)
        return (region?.level || '').toLowerCase() === normalizedLevel ? count + 1 : count
      }, 0)
    },
    canSelectSingleLayoutRegion(region) {
      const regionId = region?.region_id || ''
      const level = String(region?.level || '').toLowerCase()
      if (!regionId || !level) return false
      if (this.singleLayoutIterationMode === 'crop') return true
      if (this.singleLayoutRegionDrafts?.[regionId]?.selected) return true
      return this.getSelectedSingleLayoutRegionCount(level) < (SINGLE_LAYOUT_REGION_LIMITS[level] || 0)
    },
    isSingleLayoutRegionSelected(regionId) {
      return Boolean(this.singleLayoutRegionDrafts?.[regionId]?.selected)
    },
    toggleSingleLayoutRegion(region) {
      const regionId = region?.region_id || ''
      const level = String(region?.level || '').toLowerCase()
      if (!regionId || !level || !this.singleOverlayViewingCurrent) return
      const current = this.singleLayoutRegionDrafts?.[regionId] || { selected: false, recognition: 'gray', user_instruction: '' }
      if (this.singleLayoutIterationMode === 'crop') {
        if (current.selected) {
          this.singleLayoutRegionDrafts = {
            ...this.singleLayoutRegionDrafts,
            [regionId]: {
              selected: false,
              recognition: current.recognition || 'gray',
              user_instruction: current.user_instruction || '',
            },
          }
          return
        }
        const nextDrafts = { ...this.singleLayoutRegionDrafts }
        Object.keys(nextDrafts).forEach(draftRegionId => {
          nextDrafts[draftRegionId] = {
            ...nextDrafts[draftRegionId],
            selected: false,
          }
        })
        nextDrafts[regionId] = {
          selected: true,
          recognition: current.recognition || 'gray',
          user_instruction: current.user_instruction || '',
        }
        this.singleLayoutRegionDrafts = nextDrafts
        return
      }
      if (!current.selected && !this.canSelectSingleLayoutRegion(region)) {
        if (this.$message?.warning) {
          this.$message.warning(`${level.toUpperCase()}级版面最多选择 ${SINGLE_LAYOUT_REGION_LIMITS[level] || 0} 个`)
        }
        return
      }
      this.singleLayoutRegionDrafts = {
        ...this.singleLayoutRegionDrafts,
        [regionId]: {
          selected: !current.selected,
          recognition: current.recognition || 'gray',
          user_instruction: current.user_instruction || '',
        },
      }
    },
    handleSinglePreviewStageClick(event) {
      if (!this.singleOverlayRegionBoxesVisible) return
      const targetRegion = this.findSingleLayoutRegionByClick(event)
      if (!targetRegion) return
      this.toggleSingleLayoutRegion(targetRegion)
    },
    findSingleLayoutRegionByClick(event) {
      const stage = this.$refs.singleWorkAreaPreviewStage
      const baseImage = this.$refs.singleWorkAreaPreviewImage
      if (!stage || !baseImage) return null
      const imageRect = baseImage.getBoundingClientRect()
      if (!imageRect.width || !imageRect.height) return null
      const offsetX = event.clientX - imageRect.left
      const offsetY = event.clientY - imageRect.top
      if (offsetX < 0 || offsetY < 0 || offsetX > imageRect.width || offsetY > imageRect.height) return null
      const normX = offsetX / imageRect.width
      const normY = offsetY / imageRect.height
      return this.singleOverlayVisibleRegions
        .filter(region => {
          const bbox = region?.bbox || {}
          const x = Number(bbox.x || 0)
          const y = Number(bbox.y || 0)
          const w = Number(bbox.w || 0)
          const h = Number(bbox.h || 0)
          return normX >= x && normX <= x + w && normY >= y && normY <= y + h
        })
        .sort((left, right) => {
          const leftArea = Number(left?.bbox?.w || 0) * Number(left?.bbox?.h || 0)
          const rightArea = Number(right?.bbox?.w || 0) * Number(right?.bbox?.h || 0)
          if (leftArea !== rightArea) return leftArea - rightArea
          const leftOrder = SINGLE_LAYOUT_REGION_ORDER[left?.level] ?? 99
          const rightOrder = SINGLE_LAYOUT_REGION_ORDER[right?.level] ?? 99
          return leftOrder - rightOrder
        })[0] || null
    },
    clampSingleWorkAreaPreviewZoom(value) {
      const numeric = Number(value)
      if (!Number.isFinite(numeric)) return 1
      return Math.min(3.5, Math.max(1, numeric))
    },
    adjustSingleWorkAreaPreviewZoom(delta) {
      this.singleWorkAreaPreviewZoom = this.clampSingleWorkAreaPreviewZoom(Number(this.singleWorkAreaPreviewZoom || 1) + Number(delta || 0))
    },
    resetSingleWorkAreaPreviewZoom() {
      this.singleWorkAreaPreviewZoom = 1
    },
    getSingleWorkAreaPreviewStageStyle() {
      const zoom = this.clampSingleWorkAreaPreviewZoom(this.singleWorkAreaPreviewZoom)
      return {
        width: `${Math.max(100, zoom * 100)}%`,
      }
    },
    syncSingleOverlayDisplayMetrics() {
      const stage = this.$refs.singleWorkAreaPreviewStage
      const baseImage = this.$refs.singleWorkAreaPreviewImage
      if (!this.singleWorkAreaVisible || !stage || !baseImage) {
        this.singleOverlayDisplayMetrics = { left: 0, top: 0, width: 0, height: 0 }
        return
      }
      const stageRect = stage.getBoundingClientRect()
      const imageRect = baseImage.getBoundingClientRect()
      if (!imageRect.width || !imageRect.height) {
        this.singleOverlayDisplayMetrics = { left: 0, top: 0, width: 0, height: 0 }
        return
      }
      this.singleOverlayDisplayMetrics = {
        left: Math.max(0, imageRect.left - stageRect.left),
        top: Math.max(0, imageRect.top - stageRect.top),
        width: imageRect.width,
        height: imageRect.height,
      }
    },
    getSingleOverlayRegionDisplayStyle(region) {
      const bbox = region?.bbox || {}
      const metrics = this.singleOverlayDisplayMetrics || { left: 0, top: 0, width: 0, height: 0 }
      return {
        left: `${metrics.left + Number(bbox.x || 0) * metrics.width}px`,
        top: `${metrics.top + Number(bbox.y || 0) * metrics.height}px`,
        width: `${Math.max(0, Number(bbox.w || 0) * metrics.width)}px`,
        height: `${Math.max(0, Number(bbox.h || 0) * metrics.height)}px`,
      }
    },
    formatSingleLayoutRegionPosition(region) {
      const bbox = region?.bbox || {}
      const x = Number(bbox.x || 0)
      const y = Number(bbox.y || 0)
      const w = Number(bbox.w || 0)
      const h = Number(bbox.h || 0)
      const centerX = x + w / 2
      const centerY = y + h / 2
      const horizontal = centerX < 0.34 ? '左侧' : (centerX > 0.66 ? '右侧' : '中部')
      const vertical = centerY < 0.34 ? '上部' : (centerY > 0.66 ? '下部' : '中部')
      if (horizontal === '中部' && vertical === '中部') return '画面中部'
      if (horizontal === '中部') return `画面${vertical}`
      if (vertical === '中部') return `画面${horizontal}`
      return `画面${vertical}${horizontal}`
    },
    buildSelectedSingleLayoutRegionsPayload() {
      return this.selectedSingleLayoutRegions.map(region => ({
        region_id: region.region_id,
        recognition: region.draft?.recognition || 'gray',
        user_instruction: String(region.draft?.user_instruction || '').trim(),
      }))
    },
    submitSingleLayoutRegionIterate() {
      const item = this.singleWorkAreaItem
      if (!item?.unit_id || !this.singleOverlayViewingCurrent) return
      const selectedRegions = this.buildSelectedSingleLayoutRegionsPayload()
      if (!selectedRegions.length) {
        if (this.$message?.warning) this.$message.warning('请至少选择一个版面')
        return
      }
      if (this.singleLayoutIterationMode === 'crop' && selectedRegions.length !== 1) {
        if (this.$message?.warning) this.$message.warning('局部裁切模式每次只能选择一个版面')
        return
      }
      this.$emit('iterate-reproduction-layout-regions', {
        analysisId: this.activeAnalysisId,
        unitId: item.unit_id,
        iterContext: this.buildIterContextPayload(item.unit_id),
        iterationMode: this.singleLayoutIterationMode,
        referenceImage: this.singleWorkAreaReferenceDataUrl || undefined,
        imageQuality: this.singleWorkAreaImageQuality || 'normal',
        selectedRegions,
      })
    },
    submitSingleAutoIterationRound() {
      const item = this.singleWorkAreaItem
      if (!item?.unit_id) return
      if (!this.canSubmitSingleAutoIteration) {
        if (this.$message?.warning) this.$message.warning(this.singleAutoIterationHint)
        return
      }
      const payload = this.buildSingleAutoIterationExecutionPayload()
      if (this.singleAutoIterationMode === 'semi') {
        this.previewSingleAutoIterationRound(payload)
        return
      }
      this.$emit('auto-iterate-reproduction-round', payload)
    },
    handleTitleDoubleClick() {
      if (!this.activeAnalysisId || this.reproductionBusy) return
      this.$emit('generate-reproduction', {
        analysisId: this.activeAnalysisId,
        forceRebuild: true,
      })
    },
    handleTopIterativeGenerate() {
      if (!this.activeAnalysisId) return
      const singleTarget = this.getTopIterativeTargetItem()
      if (singleTarget && this.hasReadyReproductionImage(singleTarget)) {
        this.openSingleWorkArea(singleTarget)
        return
      }
      this.$emit('generate-reproduction', {
        analysisId: this.activeAnalysisId,
        forceRebuild: false,
      })
    },
    handleTopRollback() {
      const target = this.topRollbackTargetItem
      if (!target?.unit_id) return
      if (this.topRollbackDisabled) return
      this.$emit('rollback-reproduction-unit', {
        analysisId: this.activeAnalysisId,
        unitId: target.unit_id,
      })
    },
    shouldUseSingleUnitIterateFromTop() {
      return this.isStrictSingleMode
    },
    getTopIterativeTargetItem() {
      if (!this.shouldUseSingleUnitIterateFromTop()) return null
      if (this.currentSingleRItem) return this.currentSingleRItem
      if (this.rItems.length === 1) return this.rItems[0]
      return null
    },
    switchViewMode(mode) {
      if (mode !== 'single' && mode !== 'group') return
      this.viewMode = mode
      this.showSingleOcr = false
      if (mode === 'single') {
        if (this.singleIndex < 0 || this.singleIndex >= this.mSections.length) {
          this.singleIndex = 0
        }
      }
    },
    toggleSection(idx) {
      this.expandedSections = { ...this.expandedSections, [idx]: !this.expandedSections[idx] }
    },
    isSingleWorkAreaSectionExpanded(sectionKey) {
      return this.singleWorkAreaSectionExpanded?.[sectionKey] !== false
    },
    toggleSingleWorkAreaSection(sectionKey) {
      this.singleWorkAreaSectionExpanded = {
        ...this.singleWorkAreaSectionExpanded,
        [sectionKey]: !this.isSingleWorkAreaSectionExpanded(sectionKey),
      }
    },
    isSingleLayoutRegionGroupExpanded(level) {
      return this.singleLayoutRegionGroupExpanded?.[level] !== false
    },
    toggleSingleLayoutRegionGroup(level) {
      this.singleLayoutRegionGroupExpanded = {
        ...this.singleLayoutRegionGroupExpanded,
        [level]: !this.isSingleLayoutRegionGroupExpanded(level),
      }
    },
    toggleRContextSection(unitId) {
      this.rContextExpandedSections = { ...this.rContextExpandedSections, [unitId]: !this.rContextExpandedSections[unitId] }
    },
    toggleOcr(idx) {
      this.expandedOcrs = { ...this.expandedOcrs, [idx]: !this.expandedOcrs[idx] }
    },
    initRContextEdits() {
      const nextEdits = {}
      const nextCollapsed = {}
      for (const item of (this.rItems || [])) {
        if (!item || !item.unit_id) continue
        nextEdits[item.unit_id] = this.buildRContextEditState(item)
        nextCollapsed[item.unit_id] = {}
        for (const field of R_CONTEXT_FIELD_DEFS) nextCollapsed[item.unit_id][field.key] = true
      }
      this.rContextEdits = nextEdits
      this.rTextPreviewCollapsed = nextCollapsed
    },
    isUnitIterating(unitId) {
      return Boolean(
        this.runningTask &&
        !this.runningTask.completed &&
        ['reproduction_iterate_unit', 'reproduction_iterate_layout_regions', 'reproduction_auto_iterate_round', 'reproduction_apply_lite_bundle'].includes(this.runningTask.task_kind) &&
        this.runningTask.analysis_id === this.activeAnalysisId &&
        this.runningTask.unit_id === unitId
      )
    },
    formatRItemStatus(status) {
      const mapping = {
        ready: '已生成',
        failed: '失败',
        skipped: '跳过',
        not_started: '未生成',
      }
      return mapping[status] || (status || '未生成')
    },
    formatCompactTime(value) {
      if (!value) return ''
      const s = String(value)
      const m = s.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/)
      return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : s
    },
    getRFieldPreview(unitId, fieldKey) {
      const text = String(this.rContextEdits?.[unitId]?.[fieldKey] || '').trim()
      if (!text) return '（空）'
      return text.length > 120 ? text.slice(0, 120) + '…' : text
    },
    isRTextPreviewCollapsed(unitId, fieldKey) {
      return this.rTextPreviewCollapsed?.[unitId]?.[fieldKey] !== false
    },
    toggleRTextPreview(unitId, fieldKey) {
      const unitState = { ...(this.rTextPreviewCollapsed?.[unitId] || {}) }
      unitState[fieldKey] = !(unitState[fieldKey] !== false)
      this.rTextPreviewCollapsed = { ...this.rTextPreviewCollapsed, [unitId]: unitState }
    },
    buildIterContextPayload(unitId) {
      const ctx = this.rContextEdits?.[unitId] || {}
      const useSketch = ctx.use_sketch_input !== false
      return {
        use_sketch_input: useSketch,
        use_original_sketch_as_r: useSketch && ctx.use_original_sketch_as_r === true,
        t_focus_text: ctx.t_focus_text || '',
        main_content: ctx.main_content || '',
        layout_regions_text: ctx.layout_regions_text || '',
        reading_order: ctx.reading_order || '',
        handwriting_printing_relation: ctx.handwriting_printing_relation || '',
        annotation_section: ctx.annotation_section || '',
        continuity_text: ctx.continuity_text || '',
        m_verification_text: ctx.m_verification_text || '',
        color_instruction: ctx.color_instruction || '',
        ratio_instruction: ctx.ratio_instruction || '',
      }
    },
    saveRContextItem(item) {
      if (!item?.unit_id) return
      this.$emit('save-reproduction-context', {
        analysisId: this.activeAnalysisId,
        unitId: item.unit_id,
        iterContext: this.buildIterContextPayload(item.unit_id),
      })
    },
    canRollbackRItem(item) {
      return Boolean(item?.rollback_available || Number(item?.rollback_count || 0) > 0)
    },
    hasReadyReproductionImage(item) {
      return Boolean(item?.status === 'ready' && String(item?.reproduction_path || '').trim())
    },
    rollbackRContextItem(item) {
      if (!item?.unit_id || !this.canRollbackRItem(item)) return
      this.$emit('rollback-reproduction-unit', {
        analysisId: this.activeAnalysisId,
        unitId: item.unit_id,
      })
    },
    handleRUnitPrimaryAction(item) {
      if (!item?.unit_id) return
      if (this.mSections.length === 1) {
        this.openSingleWorkArea(item)
        return
      }
      this.openRIterateDialog(item)
    },
    syncSingleWorkAreaAutoOpen() {
      const signal = this.singleWorkAreaAutoOpenSignal
      if (!signal || signal.analysisId !== this.activeAnalysisId) return
      const fallbackUnitId = this.mSections?.[0]?.unit_id || this.rItems?.[0]?.unit_id || ''
      const targetUnitId = signal.unitId || fallbackUnitId
      if (!targetUnitId) return
      const target = this.rItems.find(item => item?.unit_id === targetUnitId)
        || this.currentSingleRItem
        || this.rItems[0]
      if (!target?.unit_id) return
      // 勿在「已打开同一单图工作区」时重复 openSingleWorkArea：会 force 用服务端 instruction_text
      // 覆盖本地「生成覆盖层要求」（常为空的初始值），导致 DMT 微版面化流式结束后文本框被清空。
      if (this.singleWorkAreaVisible && this.singleWorkAreaUnitId === target.unit_id) return
      this.openSingleWorkArea(target)
    },
    async openSingleWorkArea(item) {
      if (!item?.unit_id) return
      this.singleWorkAreaUnitId = item.unit_id
      this.singleWorkAreaRevisionInstruction = ''
      this.singleWorkAreaReferenceDataUrl = ''
      this.singleWorkAreaImageQuality = 'normal'
      this.singleWorkAreaPreviewZoom = 1
      this.singleWorkAreaSectionExpanded = { ...DEFAULT_SINGLE_WORKAREA_SECTION_EXPANDED }
      this.singleOverlayReferenceDataUrl = ''
      this.singleOverlayImageQuality = 'normal'
      this.resetSingleOverlayVisibleLevels()
      this.singleOverlayIncludeTmContext = true
      this.singleOverlayDmtGenerated = false
      this.closeSingleAutoIterationGrayDialog()
      this.singleAutoIterationMode = 'semi'
      this.singleAutoIterationContinueFromCursor = true
      this.singleAutoIterationStartRegionId = ''
      this.singleAutoIterationSelectedRegionIds = []
      this.singleLayoutIterationMode = 'rewrite'
      this.singleLayoutRegionGroupExpanded = { ...DEFAULT_SINGLE_LAYOUT_GROUP_EXPANDED }
      this.singleDRegionConfidenceResultPath = ''
      this.singleDRegionConfidenceResults = []
      this.singleDRegionConfidenceSortOrder = 'asc'
      this.singleDRegionConfidenceModel = 'qwen'
      this.singleGlobalWorkflowRunning = false
      this.singleGlobalWorkflowProgress = 0
      this.singleGlobalWorkflowStatus = ''
      this.applySingleOverlayItemState(this.singleWorkAreaOverlayItem, { forceInstructionText: true })
      this.singleWorkAreaVisible = true
      await this.syncSingleOverlayHistoryFromServer()
      await this.loadSingleDRegionConfidenceResult()
      await this.refreshLiteBatchCacheStatus(item.unit_id)
    },
    closeSingleWorkArea() {
      this.singleWorkAreaVisible = false
      this.singleWorkAreaUnitId = ''
      this.singleWorkAreaRevisionInstruction = ''
      this.singleWorkAreaReferenceDataUrl = ''
      this.singleWorkAreaPreviewZoom = 1
      this.singleWorkAreaSectionExpanded = { ...DEFAULT_SINGLE_WORKAREA_SECTION_EXPANDED }
      this.singleOverlayReferenceDataUrl = ''
      this.resetSingleOverlayVisibleLevels()
      this.singleOverlayItemLocal = null
      this.singleOverlayIncludeTmContext = true
      this.singleOverlayDmtGenerated = false
      this.closeSingleAutoIterationGrayDialog()
      this.singleAutoIterationMode = 'semi'
      this.singleAutoIterationContinueFromCursor = true
      this.singleAutoIterationStartRegionId = ''
      this.singleAutoIterationSelectedRegionIds = []
      this.singleLayoutIterationMode = 'rewrite'
      this.singleLayoutRegionDrafts = {}
      this.singleLayoutRegionGroupExpanded = { ...DEFAULT_SINGLE_LAYOUT_GROUP_EXPANDED }
      this.singleDRegionConfidenceResultPath = ''
      this.singleDRegionConfidenceResults = []
      this.singleDRegionConfidenceSortOrder = 'asc'
      this.singleDRegionConfidenceModel = 'qwen'
      this.singleGlobalWorkflowRunning = false
      this.singleGlobalWorkflowProgress = 0
      this.singleGlobalWorkflowStatus = ''
      this.singleOverlayDisplayMetrics = { left: 0, top: 0, width: 0, height: 0 }
      this.stopSingleOverlayPolling()
      this.closeSingleReproductionManualDialog()
      this.closeSingleOverlayManualDialog()
    },
    openRIterateDialog(item) {
      if (!item?.unit_id) return
      this.rIterateActiveUnitId = item.unit_id
      this.rIterateRevisionInstruction = ''
      this.rIterateReferenceDataUrl = ''
      this.rIterateImageQuality = 'normal'
      this.rIterateDialogVisible = true
    },
    closeRIterateDialog() {
      this.rIterateDialogVisible = false
      this.rIterateActiveUnitId = ''
      this.rIterateRevisionInstruction = ''
      this.rIterateReferenceDataUrl = ''
      if (this.$refs.rIterateFileInput) this.$refs.rIterateFileInput.value = ''
    },
    triggerRIterateReferenceUpload() {
      this.$refs.rIterateFileInput?.click()
    },
    onRIterateReferenceFileChange(e) {
      const file = e.target?.files?.[0]
      if (!file || !file.type.startsWith('image/')) return
      const reader = new FileReader()
      reader.onload = () => {
        this.rIterateReferenceDataUrl = reader.result || ''
      }
      reader.readAsDataURL(file)
      e.target.value = ''
    },
    clearRIterateReferenceImage() {
      this.rIterateReferenceDataUrl = ''
      if (this.$refs.rIterateFileInput) this.$refs.rIterateFileInput.value = ''
    },
    handleRIterateDialogPaste(e) {
      if (!this.rIterateDialogVisible) return
      const items = e.clipboardData?.items || []
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image/') === 0) {
          e.preventDefault()
          const file = items[i].getAsFile()
          if (!file) return
          const reader = new FileReader()
          reader.onload = () => {
            this.rIterateReferenceDataUrl = reader.result || ''
          }
          reader.readAsDataURL(file)
          return
        }
      }
    },
    submitRIterateDialog() {
      const unitId = this.rIterateActiveUnitId
      if (!unitId) return
      this.$emit('iterate-reproduction-unit', {
        analysisId: this.activeAnalysisId,
        unitId,
        iterContext: this.buildIterContextPayload(unitId),
        revisionInstruction: this.rIterateRevisionInstruction || '',
        referenceImage: this.rIterateReferenceDataUrl || undefined,
        imageQuality: this.rIterateImageQuality || 'normal',
      })
      this.closeRIterateDialog()
    },
    async submitSingleWorkAreaReproduction() {
      const item = this.singleWorkAreaItem
      if (!item?.unit_id) return
      if (item.status === 'ready') {
        this.$emit('iterate-reproduction-unit', {
          analysisId: this.activeAnalysisId,
          unitId: item.unit_id,
          iterContext: this.buildIterContextPayload(item.unit_id),
          revisionInstruction: this.singleWorkAreaRevisionInstruction || '',
          referenceImage: this.singleWorkAreaReferenceDataUrl || undefined,
          imageQuality: this.singleWorkAreaImageQuality || 'normal',
        })
        return
      }
      const useSketch = this.rContextEdits?.[item.unit_id]?.use_sketch_input !== false
      this.$emit('generate-reproduction', {
        analysisId: this.activeAnalysisId,
        forceRebuild: false,
        useSketchInput: useSketch,
        useOriginalSketchAsR: useSketch && this.rContextEdits?.[item.unit_id]?.use_original_sketch_as_r === true,
      })
    },
    triggerSingleWorkAreaReferenceUpload() {
      this.$refs.singleWorkAreaReferenceFileInput?.click()
    },
    onSingleWorkAreaReferenceFileChange(e) {
      const file = e.target?.files?.[0]
      if (!file || !file.type.startsWith('image/')) return
      const reader = new FileReader()
      reader.onload = () => {
        this.singleWorkAreaReferenceDataUrl = reader.result || ''
      }
      reader.readAsDataURL(file)
      e.target.value = ''
    },
    clearSingleWorkAreaReferenceImage() {
      this.singleWorkAreaReferenceDataUrl = ''
      if (this.$refs.singleWorkAreaReferenceFileInput) this.$refs.singleWorkAreaReferenceFileInput.value = ''
    },
    triggerSingleOverlayReferenceUpload() {
      this.$refs.singleOverlayReferenceFileInput?.click()
    },
    onSingleOverlayReferenceFileChange(e) {
      const file = e.target?.files?.[0]
      if (!file || !file.type.startsWith('image/')) return
      const reader = new FileReader()
      reader.onload = () => {
        this.singleOverlayReferenceDataUrl = reader.result || ''
      }
      reader.readAsDataURL(file)
      e.target.value = ''
    },
    clearSingleOverlayReferenceImage() {
      this.singleOverlayReferenceDataUrl = ''
      if (this.$refs.singleOverlayReferenceFileInput) this.$refs.singleOverlayReferenceFileInput.value = ''
    },
    async runSingleOverlayHandwritingEstimate() {
      if (!this.singleWorkAreaUnitId || !this.singleWorkAreaReproductionSrc) return
      if (this.singleOverlayHandwritingBusy) return
      const username = localStorage.getItem('userId') || ''
      const analysisId = this.activeAnalysisId || ''
      const unitId = this.singleWorkAreaUnitId || ''
      if (!username || !analysisId || !unitId) return
      this.singleOverlayHandwritingBusy = true
      try {
        const resp = await estimateCIOverlayHandwriting({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
        })
        if (resp.error_num !== 0) {
          if (this.$message?.error) this.$message.error(resp.msg || '手写占比估算失败')
          return
        }
        const ratio = Number(resp.handwriting_area_ratio)
        const pct = Number.isFinite(ratio) ? `${(ratio * 100).toFixed(1)}%` : '—'
        const modeTip = resp.coarse_layout ? '已按粗粒度（手写占比小于 60%）' : '已按细粒度（手写占比≥60%）'
        if (this.$message?.success) this.$message.success(`手写面积约 ${pct}，${modeTip}`)
        this.$emit('switch-tab', analysisId)
      } catch (e) {
        console.error('[CI] runSingleOverlayHandwritingEstimate', e)
        if (this.$message?.error) this.$message.error(`手写占比估算失败：${e?.message || e}`)
      } finally {
        this.singleOverlayHandwritingBusy = false
      }
    },
    async runSingleOverlayDmtPrompt() {
      if (!this.singleWorkAreaUnitId || !this.singleWorkAreaReproductionSrc) return
      if (this.singleOverlayPromptStreaming) return
      this.singleOverlayPromptStreaming = true
      this.singleOverlayDmtGenerated = false
      try {
        const username = localStorage.getItem('userId') || ''
        const res = await fetch(`${API_BASE_URL}/api/ci/overlay/prompt_stream`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username,
            analysis_id: this.activeAnalysisId,
            unit_id: this.singleWorkAreaUnitId,
            include_tm_context: this.singleOverlayIncludeTmContext,
          }),
        })
        if (!res.ok || !res.body || !res.body.getReader) {
          throw new Error('DMT微版面化请求失败')
        }
        const reader = res.body.getReader()
        const decoder = new TextDecoder('utf-8')
        let acc = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          acc += decoder.decode(value, { stream: true })
          this.singleOverlayInstructionText = acc
        }
        acc += decoder.decode()
        this.singleOverlayInstructionText = acc
        this.singleOverlayDmtGenerated = !!acc.trim()
        if (String(this.singleOverlayInstructionText || '').trim()) {
          this.$emit('switch-tab', this.activeAnalysisId)
        }
      } catch (e) {
        console.error('[CI] runSingleOverlayDmtPrompt error:', e)
      } finally {
        this.singleOverlayPromptStreaming = false
      }
    },
    stopSingleOverlayPolling() {
      if (this.singleOverlayPollTimer) {
        clearTimeout(this.singleOverlayPollTimer)
        this.singleOverlayPollTimer = null
      }
      this.singleOverlayJobRunning = false
      this.singleOverlayBusy = false
    },
    async syncSingleOverlayHistoryFromServer() {
      if (!this.singleWorkAreaUnitId) return
      const analysisId = this.liteBatchScopedAnalysisId || this.activeAnalysisId
      await this.syncSingleOverlayHistoryForAnalysis(analysisId, this.singleWorkAreaUnitId)
    },
    async syncSingleOverlayHistoryForAnalysis(analysisId, unitId) {
      if (!analysisId || !unitId) return
      const username = localStorage.getItem('userId') || ''
      try {
        const resp = await getCIOverlayHistory({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
        })
        const data = resp.data || resp
        this.applySingleOverlayItemState(data.overlay_item || this.singleWorkAreaOverlayItem)
        const items = Array.isArray(data.items) ? data.items : []
        this.singleOverlayHistory = items.slice(-2)
        this.singleOverlayHistoryIndex = this.singleOverlayHistory.length ? this.singleOverlayHistory.length - 1 : -1
        const cur = this.singleOverlayHistory[this.singleOverlayHistoryIndex] || null
        this.singleOverlayDataUrl = cur?.image || ''
        await this.rebuildSingleOverlayPreviewAlpha()
      } catch (e) {
        console.error('[CI] syncSingleOverlayHistoryForAnalysis error:', e)
      }
    },
    /** 手动保存成功后：用本地画布与 save 返回的 overlay_item 更新预览/历史，避免再拉两张全图 */
    async applySingleOverlayHistoryAfterLocalSave(overlayImage, overlayItem) {
      const image = (overlayImage || '').trim()
      if (!image) return
      const bbox = overlayItem?.overlay_bbox && typeof overlayItem.overlay_bbox === 'object'
        ? overlayItem.overlay_bbox
        : null
      const currentEntry = { image, bbox }
      const prior = Array.isArray(this.singleOverlayHistory) ? this.singleOverlayHistory : []
      let nextHistory = []
      if (prior.length >= 2) {
        nextHistory = [prior[0], currentEntry]
      } else if (prior.length === 1) {
        nextHistory = [prior[0], currentEntry]
      } else {
        nextHistory = [currentEntry]
      }
      this.singleOverlayHistory = nextHistory.slice(-2)
      this.singleOverlayHistoryIndex = this.singleOverlayHistory.length - 1
      this.singleOverlayDataUrl = image
      await this.rebuildSingleOverlayPreviewAlpha()
    },
    async goSingleOverlayHistoryPrev() {
      if (this.singleOverlayHistoryIndex <= 0) return
      this.singleOverlayHistoryIndex -= 1
      const cur = this.singleOverlayHistory[this.singleOverlayHistoryIndex] || null
      this.singleOverlayDataUrl = cur?.image || ''
      await this.rebuildSingleOverlayPreviewAlpha()
    },
    async goSingleOverlayHistoryNext() {
      if (this.singleOverlayHistoryIndex >= this.singleOverlayHistory.length - 1) return
      this.singleOverlayHistoryIndex += 1
      const cur = this.singleOverlayHistory[this.singleOverlayHistoryIndex] || null
      this.singleOverlayDataUrl = cur?.image || ''
      await this.rebuildSingleOverlayPreviewAlpha()
    },
    async rebuildSingleOverlayPreviewAlpha() {
      const src = this.singleOverlayDataUrl
      if (!src) {
        this.singleOverlayPreviewDataUrl = ''
        return
      }
      const allowedLevels = this.singleOverlayVisibleLevelList
      const img = new Image()
      await new Promise(resolve => {
        img.onload = resolve
        img.onerror = resolve
        img.src = src
      })
      if (!img.width || !img.height) {
        this.singleOverlayPreviewDataUrl = src
        return
      }
      const cvs = document.createElement('canvas')
      cvs.width = img.width
      cvs.height = img.height
      const ctx = cvs.getContext('2d')
      ctx.drawImage(img, 0, 0)
      this.makeSingleOverlayWhiteTransparent(ctx, cvs.width, cvs.height, allowedLevels)
      this.singleOverlayPreviewDataUrl = cvs.toDataURL('image/png')
    },
    async pollSingleOverlayStatus(immediate = false) {
      this.stopSingleOverlayPolling()
      if (!this.singleWorkAreaUnitId) return
      const username = localStorage.getItem('userId') || ''
      const run = async () => {
        try {
          const resp = await getCIOverlayStatus({
            username,
            analysis_id: this.activeAnalysisId,
            unit_id: this.singleWorkAreaUnitId,
          })
          const data = resp.data || resp
          this.applySingleOverlayItemState(data.overlay_item || this.singleWorkAreaOverlayStateItem)
          const status = data.status || 'idle'
          if (status === 'running') {
            this.singleOverlayJobRunning = true
            this.singleOverlayBusy = true
            this.singleOverlayPollTimer = setTimeout(run, 1800)
            return
          }
          this.singleOverlayJobRunning = false
          this.singleOverlayBusy = false
          if (status === 'success') {
            await this.syncSingleOverlayHistoryFromServer()
          }
        } catch (e) {
          console.error('[CI] pollSingleOverlayStatus error:', e)
          this.singleOverlayBusy = false
        }
      }
      if (immediate) run()
      else this.singleOverlayPollTimer = setTimeout(run, 500)
    },
    async startSingleOverlayGenerate() {
      if (!this.singleWorkAreaUnitId) return
      const username = localStorage.getItem('userId') || ''
      try {
        const resp = await generateCIOverlay({
          username,
          analysis_id: this.activeAnalysisId,
          unit_id: this.singleWorkAreaUnitId,
          instruction_text: this.singleOverlayInstructionText || '',
          include_tm_context: this.singleOverlayIncludeTmContext,
          dmt_generated: this.singleOverlayDmtGenerated,
          reference_image: this.singleOverlayReferenceDataUrl || undefined,
          image_quality: this.singleOverlayImageQuality || 'normal',
        })
        const data = resp.data || resp
        if (data.error_num !== 0) return
        this.singleOverlayDmtGenerated = false
        this.singleOverlayBusy = true
        this.pollSingleOverlayStatus(false)
      } catch (e) {
        console.error('[CI] startSingleOverlayGenerate error:', e)
      }
    },
    async startSingleOverlayIterate() {
      if (!this.singleWorkAreaUnitId || !this.singleOverlayDataUrl) return
      const username = localStorage.getItem('userId') || ''
      try {
        const resp = await iterateCIOverlay({
          username,
          analysis_id: this.activeAnalysisId,
          unit_id: this.singleWorkAreaUnitId,
          overlay_image: this.singleOverlayDataUrl,
          instruction_text: this.singleOverlayInstructionText || '',
          reference_image: this.singleOverlayReferenceDataUrl || undefined,
          image_quality: this.singleOverlayImageQuality || 'normal',
        })
        const data = resp.data || resp
        if (data.error_num !== 0) return
        this.singleOverlayBusy = true
        this.pollSingleOverlayStatus(false)
      } catch (e) {
        console.error('[CI] startSingleOverlayIterate error:', e)
      }
    },
    async openSingleReproductionManualDialog() {
      if (!this.singleWorkAreaReproductionSrc) return
      this.closeSingleOverlayManualDialog()
      this.singleReproductionManualDialogVisible = true
      this.singleReproductionManualTool = 'line'
      this.singleReproductionManualUndoStack = []
      this.singleReproductionManualDrawing = false
      this.singleReproductionManualStartPoint = null
      this.singleReproductionManualPreviewBaseImage = null
      this.singleReproductionManualLastPoint = null
      await this.$nextTick()
      await this.initSingleReproductionManualCanvas(this.singleWorkAreaReproductionSrc)
    },
    closeSingleReproductionManualDialog() {
      this.singleReproductionManualDialogVisible = false
      this.singleReproductionManualDrawing = false
      this.singleReproductionManualStartPoint = null
      this.singleReproductionManualPreviewBaseImage = null
      this.singleReproductionManualLastPoint = null
    },
    async initSingleReproductionManualCanvas(src) {
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs || !src) return
      const img = new Image()
      await new Promise(resolve => {
        img.onload = resolve
        img.onerror = resolve
        if (/^https?:/i.test(src)) img.crossOrigin = 'anonymous'
        img.src = src
      })
      if (!img.width || !img.height) return
      cvs.width = img.width
      cvs.height = img.height
      this.singleReproductionManualCanvasWidth = img.width
      this.singleReproductionManualCanvasHeight = img.height
      await this.$nextTick()
      const wrap = this.$refs.singleReproductionManualStageWrap
      const availW = Math.max(240, (wrap?.clientWidth || 900) - 24)
      const availH = Math.max(180, (wrap?.clientHeight || Math.floor(window.innerHeight * 0.62)) - 24)
      const fitScale = Math.min(availW / img.width, availH / img.height, 1)
      this.singleReproductionManualDisplayBaseWidth = Math.max(1, Math.floor(img.width * fitScale))
      this.singleReproductionManualDisplayBaseHeight = Math.max(1, Math.floor(img.height * fitScale))
      const ctx = cvs.getContext('2d')
      ctx.clearRect(0, 0, img.width, img.height)
      ctx.drawImage(img, 0, 0)
    },
    async restoreSingleReproductionManualCanvas(snapshotImage) {
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs || !snapshotImage) return
      const img = new Image()
      await new Promise(resolve => {
        img.onload = resolve
        img.onerror = resolve
        img.src = snapshotImage
      })
      if (!img.width || !img.height) return
      if (cvs.width !== img.width || cvs.height !== img.height) {
        cvs.width = img.width
        cvs.height = img.height
        this.singleReproductionManualCanvasWidth = img.width
        this.singleReproductionManualCanvasHeight = img.height
      }
      const ctx = cvs.getContext('2d')
      ctx.clearRect(0, 0, cvs.width, cvs.height)
      ctx.drawImage(img, 0, 0)
    },
    activateSingleReproductionManualTool(tool) {
      this.singleReproductionManualTool = tool
      this.singleReproductionManualDrawing = false
      this.singleReproductionManualStartPoint = null
      this.singleReproductionManualPreviewBaseImage = null
      this.singleReproductionManualLastPoint = null
    },
    getSingleReproductionManualStageCursor() {
      return 'crosshair'
    },
    getSingleReproductionManualPoint(e) {
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs) return null
      const rect = cvs.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) return null
      return {
        x: this.clampSingleOverlayManualValue((e.clientX - rect.left) * (cvs.width / rect.width), 0, cvs.width),
        y: this.clampSingleOverlayManualValue((e.clientY - rect.top) * (cvs.height / rect.height), 0, cvs.height),
      }
    },
    snapshotSingleReproductionManualUndo() {
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs) return
      this.singleReproductionManualUndoStack.push({
        image: cvs.toDataURL('image/png'),
      })
      if (this.singleReproductionManualUndoStack.length > 20) {
        this.singleReproductionManualUndoStack = this.singleReproductionManualUndoStack.slice(this.singleReproductionManualUndoStack.length - 20)
      }
    },
    drawSingleReproductionManualSegment(ctx, startPoint, endPoint, options = {}) {
      if (!ctx || !startPoint || !endPoint) return
      const strokeWidth = Math.max(2, Number(this.singleReproductionManualStrokeWidth || 12))
      const color = options.color || this.singleReproductionManualStrokeColor || '#c62828'
      const drawArrow = Boolean(options.arrow)
      const dx = endPoint.x - startPoint.x
      const dy = endPoint.y - startPoint.y
      const distance = Math.hypot(dx, dy)
      ctx.save()
      ctx.globalCompositeOperation = 'source-over'
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.strokeStyle = color
      ctx.fillStyle = color
      ctx.lineWidth = strokeWidth
      if (distance < 0.5) {
        ctx.beginPath()
        ctx.arc(startPoint.x, startPoint.y, strokeWidth / 2, 0, Math.PI * 2)
        ctx.fill()
        ctx.restore()
        return
      }
      ctx.beginPath()
      ctx.moveTo(startPoint.x, startPoint.y)
      ctx.lineTo(endPoint.x, endPoint.y)
      ctx.stroke()
      if (drawArrow) {
        const angle = Math.atan2(dy, dx)
        const headLength = Math.max(12, strokeWidth * 2.8)
        ctx.beginPath()
        ctx.moveTo(endPoint.x, endPoint.y)
        ctx.lineTo(
          endPoint.x - headLength * Math.cos(angle - Math.PI / 7),
          endPoint.y - headLength * Math.sin(angle - Math.PI / 7)
        )
        ctx.lineTo(
          endPoint.x - headLength * Math.cos(angle + Math.PI / 7),
          endPoint.y - headLength * Math.sin(angle + Math.PI / 7)
        )
        ctx.closePath()
        ctx.fill()
      }
      ctx.restore()
    },
    eraseSingleReproductionManualStroke(ctx, fromPoint, toPoint) {
      if (!ctx || !fromPoint) return
      const targetPoint = toPoint || fromPoint
      const strokeWidth = Math.max(2, Number(this.singleReproductionManualStrokeWidth || 12))
      ctx.save()
      ctx.globalCompositeOperation = 'destination-out'
      ctx.lineCap = 'round'
      ctx.lineJoin = 'round'
      ctx.strokeStyle = 'rgba(0,0,0,1)'
      ctx.fillStyle = 'rgba(0,0,0,1)'
      ctx.lineWidth = strokeWidth
      ctx.beginPath()
      ctx.moveTo(fromPoint.x, fromPoint.y)
      ctx.lineTo(targetPoint.x, targetPoint.y)
      ctx.stroke()
      ctx.beginPath()
      ctx.arc(targetPoint.x, targetPoint.y, strokeWidth / 2, 0, Math.PI * 2)
      ctx.fill()
      ctx.restore()
    },
    previewSingleReproductionManualSegment(point) {
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs || !this.singleReproductionManualPreviewBaseImage || !this.singleReproductionManualStartPoint || !point) return
      const ctx = cvs.getContext('2d')
      ctx.putImageData(this.singleReproductionManualPreviewBaseImage, 0, 0)
      this.drawSingleReproductionManualSegment(ctx, this.singleReproductionManualStartPoint, point, {
        arrow: this.singleReproductionManualTool === 'arrow',
      })
    },
    onSingleReproductionManualMouseDown(e) {
      const point = this.getSingleReproductionManualPoint(e)
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!point || !cvs) return
      const ctx = cvs.getContext('2d')
      this.snapshotSingleReproductionManualUndo()
      this.singleReproductionManualDrawing = true
      this.singleReproductionManualStartPoint = point
      this.singleReproductionManualLastPoint = point
      if (this.singleReproductionManualTool === 'erase') {
        this.singleReproductionManualPreviewBaseImage = null
        this.eraseSingleReproductionManualStroke(ctx, point, point)
        return
      }
      this.singleReproductionManualPreviewBaseImage = ctx.getImageData(0, 0, cvs.width, cvs.height)
    },
    onSingleReproductionManualMouseMove(e) {
      if (!this.singleReproductionManualDrawing) return
      const point = this.getSingleReproductionManualPoint(e)
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!point || !cvs) return
      const ctx = cvs.getContext('2d')
      if (this.singleReproductionManualTool === 'erase') {
        this.eraseSingleReproductionManualStroke(ctx, this.singleReproductionManualLastPoint || point, point)
        this.singleReproductionManualLastPoint = point
        return
      }
      this.previewSingleReproductionManualSegment(point)
    },
    onSingleReproductionManualMouseUp(e) {
      if (!this.singleReproductionManualDrawing) return
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs) return
      const ctx = cvs.getContext('2d')
      const point = this.getSingleReproductionManualPoint(e) || this.singleReproductionManualLastPoint || this.singleReproductionManualStartPoint
      if (this.singleReproductionManualTool !== 'erase' && point && this.singleReproductionManualStartPoint) {
        if (this.singleReproductionManualPreviewBaseImage) {
          ctx.putImageData(this.singleReproductionManualPreviewBaseImage, 0, 0)
        }
        this.drawSingleReproductionManualSegment(ctx, this.singleReproductionManualStartPoint, point, {
          arrow: this.singleReproductionManualTool === 'arrow',
        })
      }
      this.singleReproductionManualDrawing = false
      this.singleReproductionManualStartPoint = null
      this.singleReproductionManualPreviewBaseImage = null
      this.singleReproductionManualLastPoint = null
    },
    async undoSingleReproductionManual() {
      if (!this.singleReproductionManualUndoStack.length) return
      const remain = this.singleReproductionManualUndoStack.slice(0, -1)
      const last = this.singleReproductionManualUndoStack[this.singleReproductionManualUndoStack.length - 1]
      if (last?.image) await this.restoreSingleReproductionManualCanvas(last.image)
      this.singleReproductionManualUndoStack = remain
    },
    exportSingleReproductionManualCanvas() {
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs) return ''
      const out = document.createElement('canvas')
      out.width = cvs.width
      out.height = cvs.height
      const outCtx = out.getContext('2d')
      outCtx.fillStyle = '#FFFFFF'
      outCtx.fillRect(0, 0, out.width, out.height)
      outCtx.drawImage(cvs, 0, 0)
      return out.toDataURL('image/png')
    },
    async confirmSingleReproductionManualEdit() {
      const cvs = this.$refs.singleReproductionManualCanvas
      if (!cvs || !this.singleWorkAreaUnitId) return
      this.singleReproductionManualSaving = true
      const username = localStorage.getItem('userId') || ''
      try {
        const reproductionImage = this.exportSingleReproductionManualCanvas()
        const resp = await saveCIReproduction({
          username,
          analysis_id: this.activeAnalysisId,
          unit_id: this.singleWorkAreaUnitId,
          reproduction_image: reproductionImage,
        })
        const data = resp.data || resp
        if (data.error_num === 0) {
          this.applyRItemState(data.r_item || this.singleWorkAreaItem)
          this.closeSingleReproductionManualDialog()
        }
      } catch (e) {
        console.error('[CI] confirmSingleReproductionManualEdit error:', e)
      } finally {
        this.singleReproductionManualSaving = false
      }
    },
    /** 尚无覆盖层时，用与复现图同尺寸的纯白 PNG 作为手工框编辑底图（白底后续会抠透明）。 */
    async buildBlankOverlayBaseDataUrlFromReproduction() {
      const repro = this.singleWorkAreaReproductionSrc
      if (!repro) return ''
      const img = new Image()
      img.crossOrigin = 'anonymous'
      await new Promise((resolve) => {
        img.onload = resolve
        img.onerror = resolve
        img.src = repro
      })
      if (!img.width || !img.height) return ''
      const c = document.createElement('canvas')
      c.width = img.width
      c.height = img.height
      const ctx = c.getContext('2d')
      ctx.fillStyle = '#ffffff'
      ctx.fillRect(0, 0, c.width, c.height)
      return c.toDataURL('image/png')
    },
    async resolveSingleOverlayManualInitSrc() {
      if (this.singleOverlayDataUrl) return this.singleOverlayDataUrl
      return await this.buildBlankOverlayBaseDataUrlFromReproduction()
    },
    async openSingleOverlayManualDialog() {
      if (!this.singleWorkAreaReproductionSrc) return
      const initSrc = await this.resolveSingleOverlayManualInitSrc()
      if (!initSrc) return
      this.closeSingleReproductionManualDialog()
      this.singleOverlayManualDialogVisible = true
      this.singleOverlayManualTool = 'select'
      this.singleOverlayManualLevel = ''
      this.singleOverlayManualDirty = false
      this.singleOverlayManualUndoStack = []
      await this.$nextTick()
      await this.initSingleOverlayManualCanvas(initSrc, null)
    },
    closeSingleOverlayManualDialog() {
      this.singleOverlayManualDialogVisible = false
      this.singleOverlayManualDirty = false
      this.singleOverlayManualIsErasing = false
      this.singleOverlayManualDrawingBox = false
      this.singleOverlayManualBoxStart = null
      this.singleOverlayManualBoxBackup = null
      this.clearSingleOverlayManualSelection()
      this.resetSingleOverlayManualTransformState()
    },
    async initSingleOverlayManualCanvas(src, allowedLevels = null) {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs || !src) return
      const img = new Image()
      await new Promise(resolve => {
        img.onload = resolve
        img.onerror = resolve
        img.src = src
      })
      if (!img.width || !img.height) return
      cvs.width = img.width
      cvs.height = img.height
      this.singleOverlayManualCanvasWidth = img.width
      this.singleOverlayManualCanvasHeight = img.height
      await this.$nextTick()
      const wrap = this.$refs.singleOverlayManualStageWrap
      const availW = Math.max(240, (wrap?.clientWidth || 900) - 24)
      const availH = Math.max(180, (wrap?.clientHeight || Math.floor(window.innerHeight * 0.62)) - 24)
      const fitScale = Math.min(availW / img.width, availH / img.height, 1)
      this.singleOverlayManualDisplayBaseWidth = Math.max(1, Math.floor(img.width * fitScale))
      this.singleOverlayManualDisplayBaseHeight = Math.max(1, Math.floor(img.height * fitScale))
      const ctx = cvs.getContext('2d')
      ctx.clearRect(0, 0, img.width, img.height)
      ctx.drawImage(img, 0, 0)
      this.makeSingleOverlayWhiteTransparent(ctx, img.width, img.height, allowedLevels)
      this.singleOverlayManualRegions = this.buildSingleOverlayManualRegionsFromOverlay(this.getSingleOverlayManualSourceRegions(''))
      this.clearSingleOverlayManualSelection()
      this.resetSingleOverlayManualTransformState()
    },
    async restoreSingleOverlayManualCanvas(snapshotImage) {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs || !snapshotImage) return
      const img = new Image()
      await new Promise(resolve => {
        img.onload = resolve
        img.onerror = resolve
        img.src = snapshotImage
      })
      if (!img.width || !img.height) return
      if (cvs.width !== img.width || cvs.height !== img.height) {
        cvs.width = img.width
        cvs.height = img.height
        this.singleOverlayManualCanvasWidth = img.width
        this.singleOverlayManualCanvasHeight = img.height
      }
      const ctx = cvs.getContext('2d')
      ctx.clearRect(0, 0, cvs.width, cvs.height)
      ctx.drawImage(img, 0, 0)
      this.makeSingleOverlayWhiteTransparent(ctx, cvs.width, cvs.height, null)
    },
    async switchSingleOverlayManualLevel(level) {
      const normalized = this.normalizeSingleOverlayLevel(level)
      if (!normalized || normalized === this.singleOverlayManualLevel) return
      if (this.singleOverlayManualDirty && window && typeof window.confirm === 'function') {
        const confirmed = window.confirm('切换编辑层会丢失当前未保存修改，是否继续？')
        if (!confirmed) return
      }
      this.singleOverlayManualLevel = normalized
      this.singleOverlayManualDirty = false
      this.singleOverlayManualUndoStack = []
      const initSrc = await this.resolveSingleOverlayManualInitSrc()
      if (!initSrc) return
      await this.initSingleOverlayManualCanvas(initSrc, null)
    },
    makeSingleOverlayWhiteTransparent(ctx, width, height, allowedLevels = null) {
      if (!ctx || !width || !height) return
      const normalizedLevels = Array.isArray(allowedLevels)
        ? allowedLevels.map(level => this.normalizeSingleOverlayLevel(level)).filter(Boolean)
        : []
      const allowSet = normalizedLevels.length ? new Set(normalizedLevels) : null
      const im = ctx.getImageData(0, 0, width, height)
      const arr = im.data
      for (let i = 0; i < arr.length; i += 4) {
        if (arr[i + 3] === 0) continue
        const level = this.detectSingleOverlayPixelLevel(arr[i], arr[i + 1], arr[i + 2], arr[i + 3])
        if (!level) {
          arr[i + 3] = 0
          continue
        }
        if (allowSet && !allowSet.has(level)) arr[i + 3] = 0
      }
      ctx.putImageData(im, 0, 0)
    },
    cloneSingleOverlayManualRegion(region) {
      if (!region || typeof region !== 'object') return null
      return {
        region_id: region.region_id || `manual_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        level: String(region.level || 'd').toLowerCase(),
        title: region.title || '',
        rank: Number(region.rank || 0),
        bbox: region?.bbox ? { ...region.bbox } : null,
        x: Number(region.x || 0),
        y: Number(region.y || 0),
        w: Number(region.w || 0),
        h: Number(region.h || 0),
      }
    },
    cloneSingleOverlayManualRegions(regions) {
      return (Array.isArray(regions) ? regions : [])
        .map(region => this.cloneSingleOverlayManualRegion(region))
        .filter(Boolean)
    },
    buildSingleOverlayManualRegionsFromOverlay(regions) {
      const width = this.singleOverlayManualCanvasWidth
      const height = this.singleOverlayManualCanvasHeight
      if (!width || !height) return []
      return this.cloneSingleOverlayManualRegions(regions).map(region => {
        const bbox = region.bbox || {}
        const left = this.clampSingleOverlayManualValue(Math.round(Number(bbox.x || 0) * width), 0, width - 1)
        const top = this.clampSingleOverlayManualValue(Math.round(Number(bbox.y || 0) * height), 0, height - 1)
        const right = this.clampSingleOverlayManualValue(Math.round((Number(bbox.x || 0) + Number(bbox.w || 0)) * width), left + 1, width)
        const bottom = this.clampSingleOverlayManualValue(Math.round((Number(bbox.y || 0) + Number(bbox.h || 0)) * height), top + 1, height)
        return {
          region_id: region.region_id,
          level: String(region.level || 'd').toLowerCase(),
          title: region.title || region.region_id || '',
          rank: Number(region.rank || 0),
          x: left,
          y: top,
          w: Math.max(1, right - left),
          h: Math.max(1, bottom - top),
        }
      })
    },
    activateSingleOverlayManualTool(tool) {
      this.singleOverlayManualTool = tool
      this.singleOverlayManualIsErasing = false
      this.singleOverlayManualLastPoint = null
      this.singleOverlayManualDrawingBox = false
      this.singleOverlayManualBoxStart = null
      this.singleOverlayManualBoxBackup = null
      this.singleOverlayManualSelecting = false
      this.singleOverlayManualSelectionStart = null
      this.resetSingleOverlayManualTransformState()
    },
    getSingleOverlayToolStyle(tool) {
      const mapping = {
        d: { color: '#E53935', width: 1.5, label: 'D' },
        m: { color: '#1E88E5', width: 2, label: 'M' },
        t: { color: '#8E24AA', width: 3, label: 'T' },
      }
      return mapping[tool] || mapping.d
    },
    getSingleOverlayManualStageCursor() {
      if (this.singleOverlayManualTool === 'select') return 'pointer'
      if (this.singleOverlayManualTool === 'erase') return 'pointer'
      return 'crosshair'
    },
    getSingleOverlayManualLevelOrder(level) {
      return { t: 0, m: 1, d: 2 }[String(level || '').toLowerCase()] ?? 99
    },
    getSingleOverlayManualSortedRegions(regions = this.singleOverlayManualRegions) {
      return this.cloneSingleOverlayManualRegions(regions)
        .sort((left, right) => {
          const leftOrder = this.getSingleOverlayManualLevelOrder(left.level)
          const rightOrder = this.getSingleOverlayManualLevelOrder(right.level)
          if (leftOrder !== rightOrder) return leftOrder - rightOrder
          const leftRank = Number(left.rank || 0)
          const rightRank = Number(right.rank || 0)
          if (leftRank !== rightRank) return leftRank - rightRank
          return String(left.region_id || '').localeCompare(String(right.region_id || ''))
        })
    },
    drawSingleOverlayManualRegion(ctx, region) {
      if (!ctx || !region) return
      const style = this.getSingleOverlayToolStyle(region.level)
      const fontSize = this.clampSingleOverlayManualValue(Math.round(Math.min(region.w, region.h) * 0.18), 12, 24)
      ctx.save()
      ctx.strokeStyle = style.color
      ctx.lineWidth = style.width
      ctx.fillStyle = style.color
      ctx.font = `bold ${fontSize}px serif`
      ctx.textBaseline = 'top'
      ctx.globalCompositeOperation = 'source-over'
      ctx.strokeRect(region.x, region.y, region.w, region.h)
      ctx.fillText(region.title || style.label, region.x + 4, region.y + 4)
      ctx.restore()
    },
    redrawSingleOverlayManualCanvas(previewRegion = null) {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs) return
      const ctx = cvs.getContext('2d')
      ctx.clearRect(0, 0, cvs.width, cvs.height)
      this.getSingleOverlayManualSortedRegions().forEach(region => this.drawSingleOverlayManualRegion(ctx, region))
      if (previewRegion) this.drawSingleOverlayManualRegion(ctx, previewRegion)
    },
    getSingleOverlayManualScaleX() {
      if (!this.singleOverlayManualCanvasWidth) return 1
      return (this.singleOverlayManualDisplayBaseWidth * this.singleOverlayManualZoom) / this.singleOverlayManualCanvasWidth
    },
    getSingleOverlayManualScaleY() {
      if (!this.singleOverlayManualCanvasHeight) return 1
      return (this.singleOverlayManualDisplayBaseHeight * this.singleOverlayManualZoom) / this.singleOverlayManualCanvasHeight
    },
    getSingleOverlayManualSelectionStyle() {
      const rect = this.singleOverlayManualSelection
      if (!rect) return {}
      const scaleX = this.getSingleOverlayManualScaleX()
      const scaleY = this.getSingleOverlayManualScaleY()
      return {
        left: `${rect.x * scaleX}px`,
        top: `${rect.y * scaleY}px`,
        width: `${Math.max(1, rect.w * scaleX)}px`,
        height: `${Math.max(1, rect.h * scaleY)}px`,
      }
    },
    clearSingleOverlayManualSelection() {
      this.singleOverlayManualSelection = null
      this.singleOverlayManualSelecting = false
      this.singleOverlayManualSelectionStart = null
    },
    getSingleOverlayManualRegionById(regionId) {
      if (!regionId) return null
      if (regionId === '__whole_overlay__') return this.getSingleOverlayManualWholeRect()
      return this.singleOverlayManualRegions.find(region => region?.region_id === regionId) || null
    },
    setSingleOverlayManualSelection(region) {
      this.singleOverlayManualSelection = region ? this.cloneSingleOverlayManualRegion(region) : null
    },
    resetSingleOverlayManualTransformState() {
      this.singleOverlayManualTransformMode = ''
      this.singleOverlayManualTransformStart = null
      this.singleOverlayManualTransformBaseImage = null
      this.singleOverlayManualTransformSourceCanvas = null
      this.singleOverlayManualTransformSourceRect = null
    },
    updateSingleOverlayManualRegion(regionId, nextRegion, options = {}) {
      if (!regionId || !nextRegion) return
      const cloned = this.cloneSingleOverlayManualRegion(nextRegion)
      this.singleOverlayManualRegions = this.singleOverlayManualRegions.map(region => (region.region_id === regionId ? cloned : region))
      if (options.select !== false) this.setSingleOverlayManualSelection(cloned)
      if (options.redraw) this.redrawSingleOverlayManualCanvas()
    },
    deleteSingleOverlayManualRegion(regionId) {
      if (!regionId) return
      const target = this.getSingleOverlayManualRegionById(regionId)
      this.singleOverlayManualRegions = this.singleOverlayManualRegions.filter(region => region?.region_id !== regionId)
      if (this.singleOverlayManualSelection?.region_id === regionId) this.clearSingleOverlayManualSelection()
      const cvs = this.$refs.singleOverlayManualCanvas
      if (cvs && target) {
        const ctx = cvs.getContext('2d')
        ctx.clearRect(target.x, target.y, target.w, target.h)
      }
    },
    deleteSingleOverlayManualSelection() {
      if (!this.singleOverlayManualSelection?.region_id) return
      this.snapshotSingleOverlayManualUndo()
      this.deleteSingleOverlayManualRegion(this.singleOverlayManualSelection.region_id)
      this.resetSingleOverlayManualTransformState()
    },
    clampSingleOverlayManualValue(value, min, max) {
      return Math.min(max, Math.max(min, value))
    },
    normalizeSingleOverlayManualRect(start, end) {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs || !start || !end) return null
      const x1 = this.clampSingleOverlayManualValue(Math.round(start.x), 0, cvs.width)
      const y1 = this.clampSingleOverlayManualValue(Math.round(start.y), 0, cvs.height)
      const x2 = this.clampSingleOverlayManualValue(Math.round(end.x), 0, cvs.width)
      const y2 = this.clampSingleOverlayManualValue(Math.round(end.y), 0, cvs.height)
      const x = Math.min(x1, x2)
      const y = Math.min(y1, y2)
      return {
        x,
        y,
        w: Math.abs(x2 - x1),
        h: Math.abs(y2 - y1),
      }
    },
    createSingleOverlayManualRegion(level, rect) {
      const normalizedLevel = String(level || 'd').toLowerCase()
      const nextRank = this.singleOverlayManualRegions.reduce((maxRank, region) => {
        if (String(region?.level || '').toLowerCase() !== normalizedLevel) return maxRank
        return Math.max(maxRank, Number(region?.rank || 0))
      }, 0) + 1
      const label = this.getSingleOverlayToolStyle(normalizedLevel).label
      return {
        region_id: `manual_${normalizedLevel}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        level: normalizedLevel,
        rank: nextRank,
        title: `${label}-${nextRank}`,
        x: rect.x,
        y: rect.y,
        w: rect.w,
        h: rect.h,
      }
    },
    getSingleOverlayManualPoint(e) {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs) return null
      const rect = cvs.getBoundingClientRect()
      if (rect.width <= 0 || rect.height <= 0) return null
      return {
        x: this.clampSingleOverlayManualValue((e.clientX - rect.left) * (cvs.width / rect.width), 0, cvs.width),
        y: this.clampSingleOverlayManualValue((e.clientY - rect.top) * (cvs.height / rect.height), 0, cvs.height),
      }
    },
    snapshotSingleOverlayManualUndo() {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs) return
      this.singleOverlayManualDirty = true
      this.singleOverlayManualUndoStack.push({
        image: cvs.toDataURL('image/png'),
        regions: this.cloneSingleOverlayManualRegions(this.singleOverlayManualRegions),
      })
      if (this.singleOverlayManualUndoStack.length > 20) {
        this.singleOverlayManualUndoStack = this.singleOverlayManualUndoStack.slice(this.singleOverlayManualUndoStack.length - 20)
      }
    },
    getSingleOverlayManualHitRegion(point) {
      if (!point) return null
      const tolerance = 6
      const candidates = this.cloneSingleOverlayManualRegions(this.singleOverlayManualRegions)
        .filter(region => {
          const left = region.x - tolerance
          const top = region.y - tolerance
          const right = region.x + region.w + tolerance
          const bottom = region.y + region.h + tolerance
          return point.x >= left && point.x <= right && point.y >= top && point.y <= bottom
        })
        .sort((left, right) => {
          const leftArea = left.w * left.h
          const rightArea = right.w * right.h
          if (leftArea !== rightArea) return leftArea - rightArea
          const leftOrder = this.getSingleOverlayManualLevelOrder(left.level)
          const rightOrder = this.getSingleOverlayManualLevelOrder(right.level)
          if (leftOrder !== rightOrder) return rightOrder - leftOrder
          return Number(left.rank || 0) - Number(right.rank || 0)
        })
      return candidates[0] || null
    },
    startSingleOverlayManualTransform(mode, e) {
      if (this.singleOverlayManualTool !== 'select' || !this.singleOverlayManualSelection) return
      const point = this.getSingleOverlayManualPoint(e)
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!point) return
      const rect = this.getSingleOverlayManualRegionById(this.singleOverlayManualSelection.region_id)
      if (!rect || !cvs) return
      if (rect.w <= 0 || rect.h <= 0) return
      const ctx = cvs.getContext('2d')
      const sourceCanvas = document.createElement('canvas')
      sourceCanvas.width = rect.w
      sourceCanvas.height = rect.h
      sourceCanvas.getContext('2d').drawImage(cvs, rect.x, rect.y, rect.w, rect.h, 0, 0, rect.w, rect.h)
      this.snapshotSingleOverlayManualUndo()
      this.singleOverlayManualTransformMode = mode
      this.singleOverlayManualTransformStart = point
      this.singleOverlayManualTransformBaseImage = ctx.getImageData(0, 0, cvs.width, cvs.height)
      this.singleOverlayManualTransformSourceCanvas = sourceCanvas
      this.singleOverlayManualTransformSourceRect = this.cloneSingleOverlayManualRegion(rect)
      this.singleOverlayManualSelecting = false
      this.singleOverlayManualSelectionStart = null
    },
    getSingleOverlayManualTransformedRect(point) {
      const cvs = this.$refs.singleOverlayManualCanvas
      const sourceRect = this.singleOverlayManualTransformSourceRect
      const startPoint = this.singleOverlayManualTransformStart
      if (!cvs || !sourceRect || !startPoint || !point) return null
      const minSize = 12
      const dx = Math.round(point.x - startPoint.x)
      const dy = Math.round(point.y - startPoint.y)
      if (this.singleOverlayManualTransformMode === 'move') {
        return {
          x: this.clampSingleOverlayManualValue(sourceRect.x + dx, 0, Math.max(0, cvs.width - sourceRect.w)),
          y: this.clampSingleOverlayManualValue(sourceRect.y + dy, 0, Math.max(0, cvs.height - sourceRect.h)),
          w: sourceRect.w,
          h: sourceRect.h,
        }
      }
      if (this.singleOverlayManualTransformMode === 'resize-nw') {
        const left = this.clampSingleOverlayManualValue(Math.round(point.x), 0, sourceRect.x + sourceRect.w - minSize)
        const top = this.clampSingleOverlayManualValue(Math.round(point.y), 0, sourceRect.y + sourceRect.h - minSize)
        return { x: left, y: top, w: sourceRect.x + sourceRect.w - left, h: sourceRect.y + sourceRect.h - top }
      }
      if (this.singleOverlayManualTransformMode === 'resize-ne') {
        const right = this.clampSingleOverlayManualValue(Math.round(point.x), sourceRect.x + minSize, cvs.width)
        const top = this.clampSingleOverlayManualValue(Math.round(point.y), 0, sourceRect.y + sourceRect.h - minSize)
        return { x: sourceRect.x, y: top, w: right - sourceRect.x, h: sourceRect.y + sourceRect.h - top }
      }
      if (this.singleOverlayManualTransformMode === 'resize-sw') {
        const left = this.clampSingleOverlayManualValue(Math.round(point.x), 0, sourceRect.x + sourceRect.w - minSize)
        const bottom = this.clampSingleOverlayManualValue(Math.round(point.y), sourceRect.y + minSize, cvs.height)
        return { x: left, y: sourceRect.y, w: sourceRect.x + sourceRect.w - left, h: bottom - sourceRect.y }
      }
      if (this.singleOverlayManualTransformMode === 'resize-se') {
        const right = this.clampSingleOverlayManualValue(Math.round(point.x), sourceRect.x + minSize, cvs.width)
        const bottom = this.clampSingleOverlayManualValue(Math.round(point.y), sourceRect.y + minSize, cvs.height)
        return { x: sourceRect.x, y: sourceRect.y, w: right - sourceRect.x, h: bottom - sourceRect.y }
      }
      return null
    },
    applySingleOverlayManualTransform(point) {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs || !this.singleOverlayManualTransformBaseImage || !this.singleOverlayManualTransformSourceCanvas || !this.singleOverlayManualTransformSourceRect) return
      const nextRect = this.getSingleOverlayManualTransformedRect(point)
      if (!nextRect) return
      const ctx = cvs.getContext('2d')
      const sourceRect = this.singleOverlayManualTransformSourceRect
      const transformWhole = sourceRect.region_id === '__whole_overlay__'
      ctx.putImageData(this.singleOverlayManualTransformBaseImage, 0, 0)
      ctx.clearRect(sourceRect.x, sourceRect.y, sourceRect.w, sourceRect.h)
      ctx.save()
      ctx.imageSmoothingEnabled = false
      ctx.drawImage(this.singleOverlayManualTransformSourceCanvas, nextRect.x, nextRect.y, nextRect.w, nextRect.h)
      ctx.restore()
      if (transformWhole) {
        const scaleX = nextRect.w / Math.max(1, sourceRect.w)
        const scaleY = nextRect.h / Math.max(1, sourceRect.h)
        const nextRegions = this.singleOverlayManualRegions.map(region => ({
          ...region,
          x: Math.round(nextRect.x + (Number(region.x || 0) - sourceRect.x) * scaleX),
          y: Math.round(nextRect.y + (Number(region.y || 0) - sourceRect.y) * scaleY),
          w: Math.max(1, Math.round(Number(region.w || 0) * scaleX)),
          h: Math.max(1, Math.round(Number(region.h || 0) * scaleY)),
        }))
        this.singleOverlayManualRegions = this.cloneSingleOverlayManualRegions(nextRegions)
        this.setSingleOverlayManualSelection(this.getSingleOverlayManualWholeRect(nextRegions))
      } else {
        const nextRegion = {
          ...this.singleOverlayManualTransformSourceRect,
          x: nextRect.x,
          y: nextRect.y,
          w: nextRect.w,
          h: nextRect.h,
        }
        this.updateSingleOverlayManualRegion(nextRegion.region_id, nextRegion)
      }
    },
    paintSingleOverlayManualBox(rect, tool, baseImageData = null) {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs || !rect) return
      const ctx = cvs.getContext('2d')
      if (baseImageData) ctx.putImageData(baseImageData, 0, 0)
      const style = this.getSingleOverlayToolStyle(tool)
      ctx.save()
      ctx.strokeStyle = style.color
      ctx.lineWidth = style.width
      ctx.fillStyle = style.color
      ctx.font = 'bold 16px serif'
      ctx.textBaseline = 'top'
      ctx.globalCompositeOperation = 'source-over'
      ctx.strokeRect(rect.x, rect.y, rect.w, rect.h)
      ctx.fillText(style.label, rect.x + 4, rect.y + 4)
      ctx.restore()
    },
    onSingleOverlayManualMouseDown(e) {
      const point = this.getSingleOverlayManualPoint(e)
      if (!point) return
      if (this.singleOverlayManualTool === 'erase') {
        const hitRegion = this.getSingleOverlayManualHitRegion(point)
        if (!hitRegion) {
          this.clearSingleOverlayManualSelection()
          return
        }
        this.snapshotSingleOverlayManualUndo()
        this.deleteSingleOverlayManualRegion(hitRegion.region_id)
        return
      }
      if (this.singleOverlayManualTool === 'select') {
        const hitRegion = this.getSingleOverlayManualHitRegion(point)
        if (!hitRegion) {
          this.clearSingleOverlayManualSelection()
          return
        }
        this.setSingleOverlayManualSelection(hitRegion)
        return
      }
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs) return
      const ctx = cvs.getContext('2d')
      this.snapshotSingleOverlayManualUndo()
      this.singleOverlayManualBoxBackup = ctx.getImageData(0, 0, cvs.width, cvs.height)
      this.singleOverlayManualBoxStart = point
      this.singleOverlayManualDrawingBox = true
    },
    onSingleOverlayManualMouseMove(e) {
      const point = this.getSingleOverlayManualPoint(e)
      if (!point) return
      if (this.singleOverlayManualTool === 'select') {
        if (this.singleOverlayManualTransformMode) {
          this.applySingleOverlayManualTransform(point)
          return
        }
        return
      }
      if (!this.singleOverlayManualDrawingBox || !this.singleOverlayManualBoxStart || !this.singleOverlayManualBoxBackup) return
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs) return
      const ctx = cvs.getContext('2d')
      const rect = {
        x: Math.min(this.singleOverlayManualBoxStart.x, point.x),
        y: Math.min(this.singleOverlayManualBoxStart.y, point.y),
        w: Math.abs(point.x - this.singleOverlayManualBoxStart.x),
        h: Math.abs(point.y - this.singleOverlayManualBoxStart.y),
      }
      this.paintSingleOverlayManualBox(rect, this.singleOverlayManualLevel, this.singleOverlayManualBoxBackup)
    },
    onSingleOverlayManualMouseUp(e) {
      if (this.singleOverlayManualTool === 'erase') {
        this.singleOverlayManualIsErasing = false
        this.singleOverlayManualLastPoint = null
        return
      }
      if (this.singleOverlayManualTool === 'select') {
        const point = this.getSingleOverlayManualPoint(e) || this.singleOverlayManualTransformStart || this.singleOverlayManualSelectionStart
        if (this.singleOverlayManualTransformMode) {
          this.applySingleOverlayManualTransform(point)
          this.resetSingleOverlayManualTransformState()
          return
        }
        return
      }
      if (!this.singleOverlayManualDrawingBox) return
      const point = this.getSingleOverlayManualPoint(e) || this.singleOverlayManualBoxStart
      const rect = this.normalizeSingleOverlayManualRect(this.singleOverlayManualBoxStart, point)
      const cvs = this.$refs.singleOverlayManualCanvas
      this.singleOverlayManualDrawingBox = false
      if (!rect || rect.w < 6 || rect.h < 6) {
        if (cvs && this.singleOverlayManualBoxBackup) {
          cvs.getContext('2d').putImageData(this.singleOverlayManualBoxBackup, 0, 0)
        }
        this.singleOverlayManualBoxStart = null
        this.singleOverlayManualBoxBackup = null
        return
      }
      this.paintSingleOverlayManualBox(rect, this.singleOverlayManualLevel, this.singleOverlayManualBoxBackup)
      this.singleOverlayManualBoxStart = null
      this.singleOverlayManualBoxBackup = null
      const nextRegion = this.createSingleOverlayManualRegion(this.singleOverlayManualLevel, rect)
      this.singleOverlayManualRegions = [...this.singleOverlayManualRegions, nextRegion]
      this.setSingleOverlayManualSelection(nextRegion)
    },
    async undoSingleOverlayManual() {
      if (!this.singleOverlayManualUndoStack.length) return
      const remain = this.singleOverlayManualUndoStack.slice(0, -1)
      const last = this.singleOverlayManualUndoStack[this.singleOverlayManualUndoStack.length - 1]
      if (last?.image) await this.restoreSingleOverlayManualCanvas(last.image)
      this.singleOverlayManualRegions = this.cloneSingleOverlayManualRegions(last?.regions || [])
      this.clearSingleOverlayManualSelection()
      this.singleOverlayManualUndoStack = remain
    },
    exportSingleOverlayManualCanvas() {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs) return ''
      const out = document.createElement('canvas')
      out.width = cvs.width
      out.height = cvs.height
      const outCtx = out.getContext('2d')
      outCtx.fillStyle = '#FFFFFF'
      outCtx.fillRect(0, 0, out.width, out.height)
      outCtx.drawImage(cvs, 0, 0)
      return out.toDataURL('image/png')
    },
    buildSingleOverlayManualRegionsForSave() {
      const width = this.singleOverlayManualCanvasWidth
      const height = this.singleOverlayManualCanvasHeight
      if (!width || !height) return []
      return this.cloneSingleOverlayManualRegions(this.singleOverlayManualRegions).map(region => ({
        region_id: region.region_id,
        level: String(region.level || 'd').toLowerCase(),
        title: region.title || region.region_id || '',
        rank: Number(region.rank || 0),
        source: 'manual_edit',
        bbox: {
          x: region.x / width,
          y: region.y / height,
          w: region.w / width,
          h: region.h / height,
        },
      }))
    },
    async confirmSingleOverlayManualEdit() {
      const cvs = this.$refs.singleOverlayManualCanvas
      if (!cvs || !this.singleWorkAreaUnitId) return
      this.singleOverlayManualSaving = true
      const username = localStorage.getItem('userId') || ''
      try {
        const overlayImage = this.exportSingleOverlayManualCanvas()
        const resp = await saveCIOverlay({
          username,
          analysis_id: this.activeAnalysisId,
          unit_id: this.singleWorkAreaUnitId,
          overlay_image: overlayImage,
          overlay_level: '',
          target: 'current',
          preserve_exact: true,
          regions: this.buildSingleOverlayManualRegionsForSave(),
        })
        const data = resp.data || resp
        if (data.error_num === 0) {
          this.singleOverlayManualDirty = false
          this.applySingleOverlayItemState(data.overlay_item || this.singleWorkAreaOverlayStateItem)
          await this.applySingleOverlayHistoryAfterLocalSave(overlayImage, data.overlay_item)
          this.closeSingleOverlayManualDialog()
        }
      } catch (e) {
        console.error('[CI] confirmSingleOverlayManualEdit error:', e)
      } finally {
        this.singleOverlayManualSaving = false
      }
    },
    setDViewMode(idx, mode) {
      this.dViewMode = { ...this.dViewMode, [idx]: mode }
    },
    getUnitDLayer(unitId) {
      if (!unitId || !this.dUnits.length) return null
      return this.dUnits.find(u => u.unit_id === unitId) || null
    },
    hasMeaningful(data) {
      if (data === null || data === undefined) return false
      if (typeof data === 'string') return data.trim().length > 0
      if (Array.isArray(data)) return data.length > 0
      if (typeof data === 'object') return Object.keys(data).length > 0
      return Boolean(data)
    },
    formatObjectLine(obj) {
      if (!obj || typeof obj !== 'object') return String(obj || '')
      return Object.entries(obj)
        .filter(([k]) => k !== 'seq')  // seq 在 formatRelationItem 里已用作序号，此处跳过
        .map(([k, v]) => {
          const label = KEY_LABELS[k] || k
          const val = typeof v === 'object' ? JSON.stringify(v) : v
          return `${label}: ${val}`
        })
        .join('； ')
    },
    /** 专门处理各类关系条目 */
    formatRelationItem(item, index) {
      // group_relations 条目：含 relation_type
      if (item.relation_type !== undefined) {
        const seq = item.seq != null ? item.seq : index + 1
        const relType = item.relation_type || ''
        const unitId = item.unit_id || ''
        const reason = item.reason || ''
        return `${seq}. [${relType}] ${unitId}${reason ? `：${reason}` : ''}`
      }
      // doc_relations 条目：含 file_name
      if (item.file_name !== undefined) {
        const fname = item.file_name || ''
        const rel = item.relation || ''
        const kp = item.key_point || ''
        return `${index + 1}. 📄 ${fname}  [${rel}]${kp ? `：${kp}` : ''}`
      }
      return `${index + 1}. ${this.formatObjectLine(item)}`
    },
    formatRelations(data) {
      if (!data) return ''
      if (typeof data === 'string') return data
      if (Array.isArray(data)) {
        return data
          .map((item, index) => {
            if (item && typeof item === 'object') {
              return this.formatRelationItem(item, index)
            }
            return String(item)
          })
          .join('\n')
      }
      if (typeof data === 'object') {
        return Object.entries(data)
          .map(([k, v]) => {
            const label = KEY_LABELS[k] || k
            const val = typeof v === 'object' ? JSON.stringify(v) : v
            return `${label}：${val}`
          })
          .join('\n')
      }
      return String(data)
    },
    formatLayoutRegions(data) {
      if (!data) return ''
      if (Array.isArray(data)) {
        return data
          .map((item, index) => {
            if (item && typeof item === 'object') {
              const type = item.type || '区域'
              const position = item.position || '未知位置'
              const content = item.content || ''
              return `${index + 1}. [${type}] ${position}${content ? `：${content}` : ''}`
            }
            return `${index + 1}. ${item}`
          })
          .join('\n')
      }
      return this.formatRelations(data)
    },
    formatContinuity(data) {
      if (!data) return ''
      if (typeof data === 'string') return data
      if (typeof data === 'object') {
        const type = data.type || '未知'
        const reason = data.reason || ''
        return reason ? `${type}（${reason}）` : type
      }
      return String(data)
    },
    getOcrInputPolicy(section) {
      if (!section || typeof section !== 'object') return {}
      if (section.ocr_input_policy && typeof section.ocr_input_policy === 'object') {
        return section.ocr_input_policy
      }
      const legacyMode = section.context_used?.d_input_mode
      const legacyReason = section.context_used?.d_input_reason
      if (!legacyMode && !legacyReason) return {}
      return {
        used_d_text_in_m: legacyMode !== 'suppressed_meaningless',
        reason: legacyReason || '',
        legacy_mode: legacyMode || '',
      }
    },
    shouldShowOcrInputPolicy(section) {
      const policy = this.getOcrInputPolicy(section)
      return Boolean(
        policy && (
          typeof policy.used_d_text_in_m === 'boolean' ||
          policy.reason ||
          policy.judge_model ||
          policy.legacy_mode
        )
      )
    },
    getOcrInputBadgeClass(policy) {
      return policy && policy.used_d_text_in_m === false ? 'is-suppressed' : 'is-used'
    },
    formatOcrInputUsage(policy) {
      if (!policy || typeof policy.used_d_text_in_m !== 'boolean') {
        if (policy?.legacy_mode === 'suppressed_meaningless') return '未注入 D层OCR'
        return '已注入 D层OCR'
      }
      return policy.used_d_text_in_m ? '已注入 D层OCR' : '未注入 D层OCR'
    },
    formatDInputReason(reason) {
      const reasonMap = {
        ocr_meaningless: 'OCR无有效语义',
        ocr_no_semantic_terms: 'OCR缺少可用语义词',
        heuristic_semantic_too_short: 'OCR语义文本过短',
        heuristic_garbled_text: 'OCR乱码占比过高',
        heuristic_sparse_tokens: 'OCR有效词过少',
        heuristic_repetitive_tokens: 'OCR几乎在重复同一词汇',
        heuristic_extreme_low_diversity: 'OCR词汇极度单一',
        heuristic_low_diversity_text: 'OCR整体重复度过高',
        heuristic_repeated_phrase: 'OCR存在大量重复短语',
        heuristic_fragmented_babble: 'OCR呈现碎片化胡言乱语',
        heuristic_ocr_has_signal: 'OCR仍有可用信息',
        heuristic_context_overlap: 'OCR与上下文存在重合',
        heuristic_no_context_overlap: 'OCR与上下文无明显重合',
        heuristic_need_llm_for_relevance: '启发式无法确认相关性',
        llm_meaningless_true: 'LLM判定OCR整体无意义',
        llm_meaningless_false: 'LLM判定OCR仍有可用语义',
        llm_unrelated_true: 'LLM判定OCR与上下文无关',
        llm_unrelated_false: 'LLM判定OCR与上下文存在潜在关联',
        context_irrelevant: 'OCR与上下文无关',
        meaningless_and_context_irrelevant: 'OCR无有效语义且与上下文无关',
        context_related: 'OCR与上下文存在关联',
        ocr_meaningful: 'OCR可用',
        context_empty: '上下文为空，不执行屏蔽',
        no_context: '未注入上下文，不执行屏蔽',
      }
      if (!reason) return '无'
      return reason
        .split(';')
        .map(part => part.trim())
        .filter(Boolean)
        .map(part => reasonMap[part] || part)
        .join('； ')
    },
    getOcrInputReason(section) {
      const policy = this.getOcrInputPolicy(section)
      return this.formatDInputReason(policy?.reason || '')
    },
    hasOcrInputDebugFlags(section) {
      const policy = this.getOcrInputPolicy(section)
      return typeof policy.meaningless_ocr === 'boolean' || typeof policy.unrelated_to_context === 'boolean'
    },
    getUnitRItem(unitId) {
      if (!unitId || !this.rItems.length) return null
      return this.rItems.find(r => r.unit_id === unitId) || null
    },
    isDocImportImageFile(fileName) {
      const lower = String(fileName || '').trim().toLowerCase()
      if (!lower) return false
      const imgExts = ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.gif']
      return imgExts.some(ext => lower.endsWith(ext))
    },
    normalizeCiFileKey(fileName) {
      return String(fileName || '').trim().toLowerCase()
    },
    ciFileListContains(files, fileName) {
      const target = this.normalizeCiFileKey(fileName)
      return (files || []).some(file => this.normalizeCiFileKey(file) === target)
    },
    findSingleAnalysisRecordForFile(fileName, singles) {
      const matches = (singles || []).filter(record =>
        record?.analysis_id && this.ciFileListContains(record.files || [], fileName)
      )
      if (!matches.length) return null
      const completed = matches.filter(record => record.status === 'completed')
      const pool = completed.length ? completed : matches
      return pool[0] || null
    },
    async fetchCIResult(analysisId) {
      const username = localStorage.getItem('userId') || ''
      const resp = await getCIResult({ username, analysis_id: analysisId })
      if (resp?.error_num !== 0) throw new Error(resp?.msg || '读取分析结果失败')
      return resp
    },
    resolveUnitIdFromCIResult(result, fileName) {
      const key = this.normalizeCiFileKey(fileName)
      const section = (result?.m_layer?.sections || []).find(row => this.normalizeCiFileKey(row?.source_file) === key)
      if (section?.unit_id) return section.unit_id
      const inputUnits = Array.isArray(result?.manifest?.input_units) ? result.manifest.input_units : []
      const inputUnit = inputUnits.find(row => this.normalizeCiFileKey(row?.source_file) === key)
      if (inputUnit?.unit_id) return inputUnit.unit_id
      const rItem = (result?.r_layer?.items || []).find(row => this.normalizeCiFileKey(row?.source_file) === key)
      return rItem?.unit_id || result?.r_layer?.items?.[0]?.unit_id || result?.m_layer?.sections?.[0]?.unit_id || ''
    },
    countOverlayDRegionsInResult(result, unitId) {
      if (!unitId) return 0
      const overlay = (result?.overlay_layer?.items || []).find(row => row?.unit_id === unitId)
      const regions = Array.isArray(overlay?.regions) ? overlay.regions : []
      return regions.filter(row => String(row?.level || 'd').toLowerCase() === 'd').length
    },
    async refreshLiteBatchCandidates(files) {
      const fileList = Array.isArray(files) ? files.filter(Boolean) : []
      if (!fileList.length) {
        if (this.$message?.warning) this.$message.warning('请先勾选要查询的图片')
        return false
      }
      this.liteBatchCandidatesLoading = true
      this.liteBatchCandidatesResolved = []
      try {
        const username = localStorage.getItem('userId') || ''
        const resp = await queryCIAnalyses({
          username,
          files: fileList,
          scene_name: this.sceneName || '',
        })
        const singles = resp?.error_num === 0 ? (resp.singles || []) : []
        const candidates = await Promise.all(fileList.map(async fileName => {
          const record = this.findSingleAnalysisRecordForFile(fileName, singles)
          const row = {
            fileName,
            analysisId: record?.analysis_id || '',
            analysisStatus: record?.status || '',
            unitId: '',
            dRegionCount: 0,
            selectable: false,
            note: '',
            rStatus: '',
          }
          if (!record?.analysis_id) {
            row.note = '未找到单图 CI 分析'
            return row
          }
          if (record.status !== 'completed') {
            row.note = `CI 分析未完成（${record.status || '进行中'}）`
            return row
          }
          try {
            const result = await this.fetchCIResult(record.analysis_id)
            row.unitId = this.resolveUnitIdFromCIResult(result, fileName)
            row.dRegionCount = this.countOverlayDRegionsInResult(result, row.unitId)
            const rItem = (result?.r_layer?.items || []).find(item => item?.unit_id === row.unitId)
            row.rStatus = rItem?.status || ''
            row.selectable = Boolean(row.unitId && row.dRegionCount > 0)
            if (!row.unitId) row.note = '无法解析 unit_id'
            else if (row.dRegionCount <= 0) row.note = '覆盖层无 D 版面'
            else row.note = `${row.dRegionCount} 个 D 区`
          } catch (e) {
            row.note = '读取分析结果失败'
          }
          return row
        }))
        this.liteBatchCandidatesResolved = candidates
        await Promise.all(candidates.map(row => {
          if (row.analysisId && row.unitId) {
            return this.refreshLiteBatchCacheStatus(row.unitId, row.analysisId)
          }
          return Promise.resolve()
        }))
        return true
      } catch (e) {
        if (this.$message?.error) this.$message.error(`解析图片列表失败：${e?.message || e}`)
        return false
      } finally {
        this.liteBatchCandidatesLoading = false
      }
    },
    resolveUnitIdForDocFile(fileName) {
      const key = this.normalizeCiFileKey(fileName)
      if (!key) return ''
      const section = (this.mSections || []).find(row => this.normalizeCiFileKey(row?.source_file) === key)
      if (section?.unit_id) return section.unit_id
      const inputUnits = Array.isArray(this.manifest?.input_units) ? this.manifest.input_units : []
      const inputUnit = inputUnits.find(row => this.normalizeCiFileKey(row?.source_file) === key)
      if (inputUnit?.unit_id) return inputUnit.unit_id
      const rItem = (this.rItems || []).find(row => this.normalizeCiFileKey(row?.source_file) === key)
      return rItem?.unit_id || ''
    },
    countOverlayDRegions(unitId) {
      if (!unitId) return 0
      const overlay = (this.overlayItems || []).find(row => row?.unit_id === unitId)
      const regions = Array.isArray(overlay?.regions) ? overlay.regions : []
      return regions.filter(row => String(row?.level || 'd').toLowerCase() === 'd').length
    },
    buildLiteBatchWorkItem(row) {
      if (!row?.unitId) return null
      return { unit_id: row.unitId, source_file: row.fileName || '' }
    },
    getReproductionTitle(rItem) {
      if (!rItem) return '升维复现图'
      const section = this.mSections.find(item => item.unit_id === rItem.unit_id)
      if (section && section.title) return section.title
      if (rItem.source_file) {
        return rItem.page ? `${rItem.source_file} p${rItem.page}` : rItem.source_file
      }
      return '升维复现图'
    },
    getReproductionSrc(rItem) {
      if (!rItem || !rItem.reproduction_path) return ''
      const username = localStorage.getItem('userId') || ''
      const analysisId = this.activeAnalysisId || ''
      const path = rItem.reproduction_path.replace(/\\/g, '/')
      const version = this.activeResult?.r_layer_version || ''
      const versionPart = version ? `&v=${encodeURIComponent(version)}` : ''
      const updatedAt = rItem?.updated_at ? `&t=${encodeURIComponent(rItem.updated_at)}` : ''
      return `${API_BASE_URL}/api/ci/layout_visual?path=${encodeURIComponent(path)}&username=${encodeURIComponent(username)}&analysis_id=${encodeURIComponent(analysisId)}${versionPart}${updatedAt}`
    },
    getOverlaySrc(overlayItem) {
      if (!overlayItem || !overlayItem.overlay_path) return ''
      const username = localStorage.getItem('userId') || ''
      const analysisId = this.activeAnalysisId || ''
      const path = overlayItem.overlay_path.replace(/\\/g, '/')
      const version = this.activeResult?.overlay_layer_version || ''
      const versionPart = version ? `&v=${encodeURIComponent(version)}` : ''
      return `${API_BASE_URL}/api/ci/layout_visual?path=${encodeURIComponent(path)}&username=${encodeURIComponent(username)}&analysis_id=${encodeURIComponent(analysisId)}${versionPart}`
    },
    openReproductionImage(rItem) {
      if (!rItem || !rItem.reproduction_path) return
      this.layoutVisualSrc = this.getReproductionSrc(rItem)
      this.layoutVisualType = 'image'
      this.layoutVisualIsOriginal = false
      this.layoutVisualVisible = true
    },
    openSingleReproContextMenu(event, rItem) {
      if (!this.isStrictSingleMode) return
      const unitId = rItem?.unit_id || ''
      if (!unitId) return
      this.singleReproContextMenuVisible = true
      this.singleReproContextMenuX = Number(event?.clientX || 0)
      this.singleReproContextMenuY = Number(event?.clientY || 0)
      this.singleReproContextMenuUnitId = unitId
    },
    closeSingleReproContextMenu() {
      this.singleReproContextMenuVisible = false
    },
    escapeHtmlForDiff(value) {
      return String(value || '')
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
    },
    _splitDiffBlocks(text) {
      return String(text || '')
        .split(/\n{2,}/)
        .map(item => item.trim())
        .filter(Boolean)
    },
    renderSingleTLayerFromDLiteDiffHtml() {
      const oldBlocks = this._splitDiffBlocks(this.singleTLayerFromDLiteExistingText)
      const newBlocks = this._splitDiffBlocks(this.singleTLayerFromDLitePreviewText)
      const len = Math.max(oldBlocks.length, newBlocks.length)
      const rows = []
      for (let i = 0; i < len; i += 1) {
        const oldText = oldBlocks[i] || ''
        const newText = newBlocks[i] || ''
        const changed = oldText !== newText
        rows.push(
          `<div class="ci-single-diff-row ${changed ? 'is-changed' : ''}">`
            + `<div class="ci-single-diff-col"><div class="ci-single-diff-col-title">原文</div><pre>${this.escapeHtmlForDiff(oldText || '（空）')}</pre></div>`
            + `<div class="ci-single-diff-col"><div class="ci-single-diff-col-title">新版</div><pre>${this.escapeHtmlForDiff(newText || '（空）')}</pre></div>`
          + `</div>`
        )
      }
      if (!rows.length) return '<div class="ci-single-inline-hint">暂无可对比内容</div>'
      return rows.join('')
    },
    renderSingleUnderstandingDiffHtml() {
      const oldBlocks = this._splitDiffBlocks(this.singleImageUnderstandingExistingText)
      const newBlocks = this._splitDiffBlocks(this.singleImageUnderstandingPreviewText)
      const len = Math.max(oldBlocks.length, newBlocks.length)
      const rows = []
      for (let i = 0; i < len; i += 1) {
        const oldText = oldBlocks[i] || ''
        const newText = newBlocks[i] || ''
        const changed = oldText !== newText
        rows.push(
          `<div class="ci-single-diff-row ${changed ? 'is-changed' : ''}">`
            + `<div class="ci-single-diff-col"><div class="ci-single-diff-col-title">原文</div><pre>${this.escapeHtmlForDiff(oldText || '（空）')}</pre></div>`
            + `<div class="ci-single-diff-col"><div class="ci-single-diff-col-title">新版</div><pre>${this.escapeHtmlForDiff(newText || '（空）')}</pre></div>`
          + `</div>`
        )
      }
      if (!rows.length) return '<div class="ci-single-inline-hint">暂无可对比内容</div>'
      return rows.join('')
    },
    async runSingleRefineTLayer() {
      const analysisId = this.activeAnalysisId || ''
      const unitId = this.singleReproContextMenuUnitId || ''
      const username = localStorage.getItem('userId') || ''
      if (!analysisId || !unitId || !username) return
      this.singleReproRefineBusy = true
      this.closeSingleReproContextMenu()
      try {
        const resp = await refineCISingleTLayer({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          context_docs: Array.isArray(this.selectedContextDocs) ? this.selectedContextDocs : [],
          context_card_ids: Array.isArray(this.selectedContextCardIds) ? this.selectedContextCardIds : [],
        })
        if (resp?.error_num !== 0) throw new Error(resp?.msg || '更新失败')
        this.$message.success('T层整体纪要已更新')
        this.$emit('switch-tab', analysisId)
      } catch (e) {
        this.$message.error(`更新整体纪要失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    async runSingleRollbackTLayer() {
      const analysisId = this.activeAnalysisId || ''
      const unitId = this.singleReproContextMenuUnitId || ''
      const username = localStorage.getItem('userId') || ''
      if (!analysisId || !unitId || !username) return
      this.singleReproRefineBusy = true
      this.closeSingleReproContextMenu()
      try {
        const resp = await rollbackCISingleTLayer({ username, analysis_id: analysisId, unit_id: unitId })
        if (resp?.error_num !== 0) throw new Error(resp?.msg || '回退失败')
        this.$message.success('T层整体纪要已回退到上一版')
        this.$emit('switch-tab', analysisId)
      } catch (e) {
        this.$message.error(`回退整体纪要失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    async runSingleRefineImageUnderstandingPreview() {
      const analysisId = this.activeAnalysisId || ''
      const unitId = this.singleReproContextMenuUnitId || ''
      const username = localStorage.getItem('userId') || ''
      if (!analysisId || !unitId || !username) return
      this.singleReproRefineBusy = true
      this.closeSingleReproContextMenu()
      try {
        this.singleImageUnderstandingPreviewKind = 'repro'
        const resp = await previewRefineCISingleImageUnderstanding({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          context_docs: Array.isArray(this.selectedContextDocs) ? this.selectedContextDocs : [],
          context_card_ids: Array.isArray(this.selectedContextCardIds) ? this.selectedContextCardIds : [],
        })
        if (resp?.error_num !== 0) throw new Error(resp?.msg || '预览失败')
        this.singleImageUnderstandingPreviewText = String(resp.preview_text || '').trim()
        this.singleImageUnderstandingExistingText = String(resp.existing_text || '').trim()
        this.singleImageUnderstandingPreviewSourceFile = String(resp.source_file || '').trim()
        this.singleImageUnderstandingPreviewImgId = Number(resp.imgid || 0)
        this.singleImageUnderstandingPreviewDialogVisible = true
      } catch (e) {
        this.$message.error(`预览三层理解更新失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    async runPreviewImageUnderstandingFromDLite(refineModel = 'gemini') {
      const analysisId = this.activeAnalysisId || ''
      const unitId = this.singleWorkAreaItem?.unit_id || ''
      const username = localStorage.getItem('userId') || ''
      if (!analysisId || !unitId || !username) return
      this.singleReproRefineBusy = true
      try {
        this.singleImageUnderstandingPreviewKind = 'd_lite'
        const resp = await previewRefineCISingleImageUnderstandingFromDLite({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          context_docs: Array.isArray(this.selectedContextDocs) ? this.selectedContextDocs : [],
          context_card_ids: Array.isArray(this.selectedContextCardIds) ? this.selectedContextCardIds : [],
          refine_model: refineModel,
        })
        if (resp?.error_num !== 0) throw new Error(resp?.msg || '预览失败')
        this.singleDLiteRefineModelUsedName = String(resp.refine_model_name || resp.refine_model || refineModel || '').trim()
        this.singleImageUnderstandingPreviewText = String(resp.preview_text || '').trim()
        this.singleImageUnderstandingExistingText = String(resp.existing_text || '').trim()
        this.singleImageUnderstandingPreviewSourceFile = String(resp.source_file || '').trim()
        this.singleImageUnderstandingPreviewImgId = Number(resp.imgid || 0)
        this.singleImageUnderstandingPreviewDialogVisible = true
      } catch (e) {
        this.$message.error(`预览三层理解（轻量 D）失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    async runPreviewTLayerFromDLite(refineModel = 'gemini') {
      const analysisId = this.activeAnalysisId || ''
      const unitId = this.singleWorkAreaItem?.unit_id || ''
      const username = localStorage.getItem('userId') || ''
      if (!analysisId || !unitId || !username) return
      this.singleReproRefineBusy = true
      try {
        const resp = await previewRefineCISingleTLayerFromDLite({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          context_docs: Array.isArray(this.selectedContextDocs) ? this.selectedContextDocs : [],
          context_card_ids: Array.isArray(this.selectedContextCardIds) ? this.selectedContextCardIds : [],
          refine_model: refineModel,
        })
        if (resp?.error_num !== 0) throw new Error(resp?.msg || '预览失败')
        this.singleDLiteRefineModelUsedName = String(resp.refine_model_name || resp.refine_model || refineModel || '').trim()
        this.singleTLayerFromDLitePreviewText = String(resp.preview_text || '').trim()
        this.singleTLayerFromDLiteExistingText = String(resp.existing_text || '').trim()
        this.singleTLayerFromDLiteDialogVisible = true
      } catch (e) {
        this.$message.error(`预览整体纪要（轻量 D）失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    openSingleDLiteRefineModelDialog(action) {
      if (this.singleReproRefineBusy) return
      this.singleDLiteRefineModelPendingAction = action === 'image_understanding' ? 'image_understanding' : 't_layer'
      this.singleDLiteRefineModelChoice = 'gemini'
      this.singleDLiteRefineModelDialogVisible = true
    },
    cancelSingleDLiteRefineModelDialog() {
      if (this.singleReproRefineBusy) return
      this.singleDLiteRefineModelDialogVisible = false
      this.singleDLiteRefineModelPendingAction = ''
    },
    async confirmSingleDLiteRefineModelAndPreview() {
      const action = this.singleDLiteRefineModelPendingAction
      const refineModel = this.singleDLiteRefineModelChoice === 'qwen' ? 'qwen' : 'gemini'
      if (!action) return
      this.singleDLiteRefineModelDialogVisible = false
      if (action === 'image_understanding') {
        await this.runPreviewImageUnderstandingFromDLite(refineModel)
      } else {
        await this.runPreviewTLayerFromDLite(refineModel)
      }
      this.singleDLiteRefineModelPendingAction = ''
    },
    async confirmSingleTLayerFromDLiteApply() {
      const username = localStorage.getItem('userId') || ''
      const analysisId = this.activeAnalysisId || ''
      const unitId = this.singleWorkAreaItem?.unit_id || ''
      const refinedText = String(this.singleTLayerFromDLitePreviewText || '').trim()
      if (!username || !analysisId || !unitId || !refinedText) return
      this.singleReproRefineBusy = true
      try {
        const resp = await applyRefineCISingleTLayerFromDLite({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          refined_text: refinedText,
        })
        if (resp?.error_num !== 0) throw new Error(resp?.msg || '写入失败')
        this.$message.success('整体纪要（轻量 D 路径）已写入')
        this.cancelSingleTLayerFromDLiteDialog()
        this.$emit('switch-tab', analysisId)
      } catch (e) {
        this.$message.error(`写入 T 层失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    cancelSingleTLayerFromDLiteDialog() {
      if (this.singleReproRefineBusy) return
      this.singleTLayerFromDLiteDialogVisible = false
      this.singleTLayerFromDLitePreviewText = ''
      this.singleTLayerFromDLiteExistingText = ''
      this.singleDLiteRefineModelUsedName = ''
    },
    submitApplyLiteBundleToReproduction() {
      const item = this.singleWorkAreaItem
      if (!item?.unit_id) return
      this.$emit('apply-lite-bundle-reproduction', {
        analysisId: this.activeAnalysisId,
        unitId: item.unit_id,
        imageQuality: this.singleWorkAreaImageQuality || 'normal',
        iterContext: this.buildIterContextPayload(item.unit_id),
      })
    },
    cancelSingleRefineImageUnderstanding() {
      if (this.singleReproRefineBusy) return
      this.singleImageUnderstandingPreviewDialogVisible = false
      this.singleImageUnderstandingPreviewKind = 'repro'
      this.singleImageUnderstandingPreviewText = ''
      this.singleImageUnderstandingExistingText = ''
      this.singleImageUnderstandingPreviewSourceFile = ''
      this.singleImageUnderstandingPreviewImgId = 0
      this.singleDLiteRefineModelUsedName = ''
    },
    async confirmSingleRefineImageUnderstanding() {
      const username = localStorage.getItem('userId') || ''
      const sourceFile = this.singleImageUnderstandingPreviewSourceFile || ''
      const imgid = Number(this.singleImageUnderstandingPreviewImgId || 0)
      const refinedText = String(this.singleImageUnderstandingPreviewText || '').trim()
      if (!username || !sourceFile || !refinedText) return
      this.singleReproRefineBusy = true
      try {
        const resp = await applyRefineCISingleImageUnderstanding({
          username,
          source_file: sourceFile,
          imgid,
          refined_text: refinedText,
        })
        if (resp?.error_num !== 0) throw new Error(resp?.msg || '确认写入失败')
        this.$message.success('原图片三层理解已更新并写入向量库')
        this.cancelSingleRefineImageUnderstanding()
      } catch (e) {
        this.$message.error(`确认更新三层理解失败：${e?.message || e}`)
      } finally {
        this.singleReproRefineBusy = false
      }
    },
    openLayoutVisual(section) {
      if (!section.layout_visual_path) {
        this.layoutVisualSrc = ''
        this.layoutVisualType = 'image'
        this.layoutVisualVisible = true
        return
      }
      const username = localStorage.getItem('userId') || ''
      const analysisId = this.activeAnalysisId || ''
      const path = section.layout_visual_path.replace(/\\/g, '/')
      // 新架构：使用 /api/ci/layout_visual 端点，传 analysis_id
      this.layoutVisualSrc = `${API_BASE_URL}/api/ci/layout_visual?path=${encodeURIComponent(path)}&username=${encodeURIComponent(username)}&analysis_id=${encodeURIComponent(analysisId)}`
      this.layoutVisualType = section.layout_visual_type || 'image'
      this.layoutVisualIsOriginal = false
      this.layoutVisualVisible = true
    },
  },
}
</script>

<style scoped>
/* ====== 面板容器 ====== */
.ci-panel-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.08);
  z-index: 2000;
  display: flex;
  justify-content: flex-end;
  pointer-events: none;
}
.ci-panel {
  width: 44%;
  min-width: 420px;
  max-width: 780px;
  height: 100vh;
  background: #fff;
  box-shadow: -4px 0 24px rgba(0,0,0,0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  pointer-events: auto;
}

/* ====== 头部 ====== */
.ci-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid #e8e8e8;
  background: #fafbfc;
  flex-shrink: 0;
}
.ci-panel-title {
  font-size: 17px;
  font-weight: 600;
  color: #222;
  margin: 0;
}
.ci-panel-header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ci-close-btn {
  font-size: 22px;
  cursor: pointer;
  color: #999;
  line-height: 1;
  padding: 0 4px;
}
.ci-close-btn:hover {
  color: #333;
}

/* 视角切换 */
.ci-view-switch {
  display: flex;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  overflow: hidden;
}
.ci-switch-btn {
  padding: 4px 12px;
  font-size: 12px;
  border: none;
  background: #fff;
  cursor: pointer;
  color: #666;
  transition: all .2s;
}

.ci-r-context-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.ci-r-context-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ci-r-unit-editor {
  border: 1px solid #e8ecf3;
  border-radius: 10px;
  background: #fbfcfe;
}

.ci-r-unit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  cursor: pointer;
}

.ci-r-unit-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.ci-r-unit-thumb {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid #dbe3f0;
  background: #fff;
}

.ci-r-unit-meta {
  min-width: 0;
}

.ci-r-unit-title {
  font-size: 14px;
  font-weight: 600;
  color: #223;
}

.ci-r-unit-subtitle {
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #6a768a;
}

.ci-r-unit-header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ci-r-unit-busy {
  font-size: 12px;
  color: #c07b00;
}

.ci-r-unit-body {
  padding: 0 14px 14px;
  border-top: 1px solid #eef2f8;
}

.ci-r-field,
.ci-r-field-inline {
  margin-top: 12px;
}

.ci-r-field-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.ci-r-field-label {
  font-size: 12px;
  font-weight: 600;
  color: #465066;
}

.ci-r-inline-check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #2f3747;
  font-size: 12px;
}

.ci-r-inline-check input {
  margin: 0;
}

.ci-r-field-preview,
.ci-r-readonly {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f4f7fb;
  color: #2f3747;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.ci-r-textarea,
.ci-r-select {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d7deea;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 12px;
  color: #2f3747;
  background: #fff;
}

.ci-r-textarea {
  resize: vertical;
  min-height: 72px;
}

.ci-r-mini-btn {
  border: none;
  background: transparent;
  color: #4f78c7;
  font-size: 12px;
  cursor: pointer;
}

.ci-r-actions {
  display: flex;
  gap: 10px;
  margin-top: 12px;
}

.ci-r-actions-left {
  justify-content: flex-start;
}

.ci-action-btn-primary {
  background: #4f78c7;
  color: #fff;
  border-color: #4f78c7;
}

.ci-r-iterate-dialog {
  width: 640px;
  max-width: calc(100vw - 32px);
}

.ci-r-iterate-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ci-r-iterate-hint,
.ci-r-paste-tip {
  font-size: 12px;
  color: #697487;
  line-height: 1.6;
}

.ci-r-file-input {
  display: none;
}

.ci-r-reference-preview {
  width: 100%;
  max-height: 220px;
  object-fit: contain;
  border: 1px solid #dbe3f0;
  border-radius: 8px;
  background: #fff;
}

.ci-r-dialog-actions {
  justify-content: flex-end;
}

.ci-single-workspace-dialog {
  width: min(1240px, calc(100vw - 32px));
  max-width: calc(100vw - 32px);
}

.ci-single-workspace-body {
  display: grid;
  grid-template-columns: minmax(320px, 38%) minmax(420px, 1fr);
  gap: 18px;
}

.ci-single-workspace-left,
.ci-single-workspace-right {
  min-width: 0;
}

.ci-single-workspace-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ci-single-preview-card,
.ci-single-workspace-section {
  border: 1px solid #e4e9f2;
  border-radius: 12px;
  padding: 14px;
  background: linear-gradient(180deg, #fbfcfe 0%, #f6f8fc 100%);
}

.ci-single-preview-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.ci-single-preview-head .ci-single-preview-title {
  margin-bottom: 0;
}

.ci-single-preview-zoom-tools {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border: 1px solid #dce3ef;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
}

.ci-preview-zoom-btn,
.ci-preview-zoom-reset {
  border: 1px solid #d5ddeb;
  background: #fff;
  color: #33405a;
  border-radius: 999px;
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
}

.ci-preview-zoom-btn {
  width: 28px;
  height: 28px;
}

.ci-preview-zoom-reset {
  padding: 7px 10px;
  min-width: 62px;
}

.ci-preview-zoom-range {
  width: 110px;
}

.ci-single-preview-viewport {
  margin-top: 12px;
  overflow: auto;
  max-height: min(72vh, 860px);
  border-radius: 10px;
  background: linear-gradient(180deg, #eef2f8 0%, #e7edf6 100%);
}

.ci-single-workspace-section-header {
  display: flex;
  align-items: center;
  min-width: 100%;
  gap: 10px;
}

.ci-single-workspace-section-header:hover .ci-single-workspace-title {
  color: #1f4f88;
}

.ci-single-workspace-section-body {
  margin-top: 12px;
}

.ci-single-preview-title,
.ci-single-workspace-title {
  font-size: 13px;
  font-weight: 700;
  color: #24324a;
  margin-bottom: 12px;
}

.ci-single-workspace-section-header .ci-single-workspace-title {
  margin-bottom: 0;
}

.ci-single-preview-stage {
  position: relative;
  width: 100%;
  min-height: 280px;
  border-radius: 10px;
  overflow: hidden;
  background: #f0f3f8;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ci-single-preview-image,
.ci-single-preview-overlay {
  width: 100%;
  height: auto;
  display: block;
}

.ci-single-preview-overlay {
  position: absolute;
  inset: 0;
  object-fit: contain;
  pointer-events: none;
}

.ci-single-preview-empty {
  color: #71809b;
  font-size: 13px;
}

.ci-single-preview-caption,
.ci-single-history-row,
.ci-single-inline-hint {
  margin-top: 10px;
  font-size: 12px;
  color: #617087;
}

.ci-single-history-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ci-single-history-text {
  color: #4e5d74;
}

.ci-single-preview-stage.is-selectable {
  cursor: crosshair;
}

.ci-single-layout-region-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.ci-single-layout-region-box {
  position: absolute;
  border-radius: 10px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.08);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}

.ci-single-layout-region-box.is-d {
  border-color: rgba(229, 57, 53, 0.5);
}

.ci-single-layout-region-box.is-m {
  border-color: rgba(30, 136, 229, 0.5);
}

.ci-single-layout-region-box.is-t {
  border-color: rgba(142, 36, 170, 0.55);
}

.ci-single-layout-region-box.is-selected {
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.88), 0 14px 28px rgba(22, 31, 48, 0.18);
  background: rgba(255, 255, 255, 0.16);
}

.ci-single-layout-region-box.is-auto-selected {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.28), 0 0 0 1px rgba(34, 48, 74, 0.1);
}

.ci-single-layout-region-box.is-auto-iterated {
  background: rgba(56, 142, 60, 0.18);
}

.ci-single-layout-region-box.is-auto-skipped {
  background: rgba(90, 106, 133, 0.16);
}

.ci-single-layout-region-box.is-auto-failed {
  background: rgba(229, 57, 53, 0.16);
}

.ci-single-layout-region-tag {
  position: absolute;
  left: 6px;
  top: 6px;
  padding: 2px 8px;
  border-radius: 999px;
  background: rgba(21, 32, 51, 0.88);
  color: #fff;
  font-size: 10px;
  line-height: 1.4;
  letter-spacing: 0.02em;
}

.ci-single-auto-round-summary,
.ci-single-auto-iterate-panel,
.ci-single-layout-iterate-panel {
  margin-top: 14px;
  border-top: 1px solid #e3e8f2;
  padding-top: 14px;
}

.ci-single-auto-round-summary {
  display: grid;
  gap: 10px;
}

.ci-single-auto-round-summary-head,
.ci-single-auto-round-summary-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.ci-single-auto-round-summary-meta {
  font-size: 12px;
  color: #617087;
}

.ci-single-auto-round-summary-list {
  display: grid;
  gap: 8px;
}

.ci-single-auto-round-summary-item {
  display: grid;
  gap: 8px;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  padding: 9px 12px;
  background: rgba(255, 255, 255, 0.82);
  font-size: 12px;
  color: #34415a;
}

.ci-single-auto-round-summary-item.is-iterated {
  border-color: rgba(56, 142, 60, 0.24);
  background: rgba(56, 142, 60, 0.08);
}

.ci-single-auto-round-summary-item.is-skipped {
  border-color: rgba(93, 108, 133, 0.22);
  background: rgba(93, 108, 133, 0.07);
}

.ci-single-auto-round-summary-item.is-failed {
  border-color: rgba(229, 57, 53, 0.24);
  background: rgba(229, 57, 53, 0.08);
}

.ci-single-auto-chip-list {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}

.ci-single-auto-dialog {
  width: min(920px, calc(100vw - 48px));
}

.ci-single-auto-dialog-body {
  display: grid;
  gap: 14px;
  max-height: 72vh;
  overflow: auto;
}

.ci-single-auto-dialog-actions {
  padding-top: 12px;
}

.ci-single-auto-preview-list,
.ci-single-auto-preview-failed-list {
  display: grid;
  gap: 12px;
}

.ci-single-auto-preview-card,
.ci-single-auto-preview-failed {
  border: 1px solid #e4e9f2;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.9);
  padding: 12px;
}

.ci-single-auto-preview-card.is-white {
  border-color: rgba(56, 142, 60, 0.24);
  background: rgba(56, 142, 60, 0.06);
}

.ci-single-auto-preview-card.is-gray {
  border-color: rgba(245, 124, 0, 0.26);
  background: rgba(245, 124, 0, 0.06);
}

.ci-single-auto-preview-card.is-black,
.ci-single-auto-preview-card.is-unknown,
.ci-single-auto-preview-failed {
  border-color: rgba(93, 108, 133, 0.24);
  background: rgba(93, 108, 133, 0.06);
}

.ci-single-auto-preview-head,
.ci-single-auto-preview-title-row,
.ci-single-auto-preview-failed-item,
.ci-single-auto-model-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.ci-single-auto-preview-meta,
.ci-single-auto-model-label,
.ci-single-auto-preview-failed-title {
  font-size: 12px;
  color: #617087;
}

.ci-single-auto-preview-text {
  margin-top: 8px;
  font-size: 13px;
  color: #2f3c55;
}

.ci-single-auto-model-list {
  display: grid;
  gap: 8px;
  margin-top: 10px;
}

.ci-single-auto-model-item {
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(241, 245, 250, 0.92);
  font-size: 12px;
  color: #425067;
}

.ci-single-d-probe-row {
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 10px;
}

.ci-single-d-probe-row .ci-r-select {
  min-width: 200px;
  flex: 1;
}

.ci-single-d-probe-details {
  margin-top: 12px;
  font-size: 12px;
  color: #425067;
}

.ci-single-d-probe-pre {
  margin-top: 8px;
  max-height: 240px;
  overflow: auto;
  padding: 10px;
  background: #f6f8fc;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 11px;
  line-height: 1.45;
}

.ci-single-d-probe-crop-preview {
  width: 100%;
  max-height: 360px;
  object-fit: contain;
  border: 1px solid #d7e0ee;
  border-radius: 8px;
  background: #ffffff;
}

.ci-single-d-probe-judge-card {
  margin-top: 12px;
  padding: 10px;
  border: 1px solid #d7e0ee;
  border-radius: 8px;
  background: #f9fbff;
}

.ci-single-d-probe-judge-title {
  font-weight: 700;
  margin-bottom: 6px;
}

.ci-single-auto-preview-failed-title {
  margin-bottom: 10px;
  font-weight: 700;
}

.ci-single-layout-iterate-title {
  font-size: 13px;
  font-weight: 700;
  color: #24324a;
}

.ci-single-layout-summary {
  margin-top: 10px;
  font-size: 12px;
  color: #425067;
}

.ci-single-layout-groups {
  display: grid;
  gap: 12px;
  margin-top: 12px;
}

.ci-single-layout-group {
  border: 1px solid #e4e9f2;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  padding: 12px;
}

.ci-single-layout-group-header,
.ci-single-layout-editor-head,
.ci-single-layout-editor-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.ci-single-layout-group-toggle {
  cursor: pointer;
}

.ci-single-layout-group-info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.ci-single-layout-group-body {
  margin-top: 10px;
}

.ci-single-layout-chip-list,
.ci-single-layout-editors {
  display: grid;
  gap: 10px;
}

.ci-single-layout-editors {
  margin-top: 10px;
}

.ci-single-layout-chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  border-radius: 10px;
  border: 1px solid #dce4f0;
  background: #fff;
  color: #2b3750;
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
}

.ci-single-layout-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.ci-single-layout-chip.is-selected {
  border-color: #21385b;
  background: #eef4fb;
}

.ci-single-layout-chip-meta,
.ci-single-layout-editor-pos {
  font-size: 11px;
  color: #6b7891;
}

.ci-single-layout-editor-card {
  border: 1px solid #e4e9f2;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.84);
  padding: 12px;
}

.ci-single-layout-level-badge {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
}

.ci-single-layout-level-badge.is-d,
.ci-single-layout-chip.is-d.is-selected {
  background: rgba(229, 57, 53, 0.12);
  border-color: rgba(229, 57, 53, 0.26);
}

.ci-single-layout-level-badge.is-d {
  background: #e53935;
}

.ci-single-layout-level-badge.is-m,
.ci-single-layout-chip.is-m.is-selected {
  background: rgba(30, 136, 229, 0.12);
  border-color: rgba(30, 136, 229, 0.26);
}

.ci-single-layout-level-badge.is-m {
  background: #1e88e5;
}

.ci-single-layout-level-badge.is-t,
.ci-single-layout-chip.is-t.is-selected {
  background: rgba(142, 36, 170, 0.12);
  border-color: rgba(142, 36, 170, 0.28);
}

.ci-single-layout-level-badge.is-t {
  background: #8e24aa;
}

.ci-single-layout-empty {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(241, 245, 250, 0.9);
  color: #617087;
  font-size: 12px;
}

.ci-link-btn {
  border: none;
  background: transparent;
  color: #355d9a;
  cursor: pointer;
  font-size: 12px;
  padding: 0;
}

.ci-link-btn:hover {
  color: #1d4278;
}

.ci-single-overlay-editor-dialog {
  width: min(1100px, calc(100vw - 32px));
  max-width: calc(100vw - 32px);
}

.ci-single-overlay-editor-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.ci-single-overlay-editor-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.ci-tool-btn {
  border: 1px solid #d4dcec;
  background: #fff;
  color: #33405a;
  border-radius: 999px;
  padding: 6px 12px;
  cursor: pointer;
  font-size: 12px;
}

.ci-tool-btn.active {
  background: #203451;
  border-color: #203451;
  color: #fff;
}

.ci-single-editor-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #5d6a81;
}

.ci-single-editor-meta-note {
  flex: 1 1 240px;
  min-width: 220px;
}

.ci-tool-color {
  width: 34px;
  height: 34px;
  border: 1px solid #d4dcec;
  border-radius: 999px;
  background: #fff;
  padding: 3px;
  cursor: pointer;
}

.ci-tool-range-compact {
  width: 120px;
}

.ci-single-overlay-editor-stage-wrap {
  max-height: calc(100vh - 280px);
  overflow: auto;
  border-radius: 12px;
  background: linear-gradient(180deg, #eef2f8 0%, #e7edf6 100%);
  padding: 12px;
}

.ci-single-overlay-editor-stage {
  position: relative;
  margin: 0 auto;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
  box-shadow: 0 12px 30px rgba(33, 54, 89, 0.15);
}

.ci-single-overlay-editor-base-image,
.ci-single-overlay-editor-canvas {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
}

.ci-single-overlay-editor-base-image {
  object-fit: fill;
  pointer-events: none;
  user-select: none;
}

.ci-single-overlay-editor-canvas {
  background: transparent;
}

.ci-single-reproduction-editor-canvas {
  background: #fff;
}

.ci-single-overlay-selection {
  position: absolute;
  border: 2px dashed rgba(32, 52, 81, 0.92);
  border-radius: 10px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.85) inset;
  pointer-events: none;
}

.ci-single-overlay-selection.is-active {
  pointer-events: none;
}

.ci-single-overlay-selection-label {
  position: absolute;
  top: -28px;
  left: 0;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(32, 52, 81, 0.92);
  color: #fff;
  font-size: 11px;
  line-height: 1;
  white-space: nowrap;
  pointer-events: auto;
  cursor: move;
}

.ci-single-overlay-selection-handle {
  position: absolute;
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: #fff;
  border: 2px solid #203451;
  box-shadow: 0 2px 8px rgba(32, 52, 81, 0.18);
  pointer-events: auto;
}

.ci-single-preview-filter-panel {
  margin-top: 12px;
  padding: 10px 12px;
  border: 1px solid #dce4f0;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(246, 248, 252, 0.92) 100%);
}

.ci-single-preview-filter-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.ci-single-preview-filter-row {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.ci-single-preview-filter-label {
  font-size: 12px;
  font-weight: 600;
  color: #465066;
}

.ci-single-preview-filter-summary {
  font-size: 11px;
  color: #728098;
}

.ci-single-preview-filter-toggle {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  border: 1px solid #d8deea;
  background: rgba(255, 255, 255, 0.9);
  color: #45526a;
  border-radius: 10px;
  padding: 10px 12px;
  cursor: pointer;
  text-align: left;
  transition: border-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease, background 0.18s ease;
}

.ci-single-preview-filter-toggle:hover {
  transform: translateY(-1px);
  box-shadow: 0 8px 18px rgba(31, 53, 91, 0.08);
}

.ci-single-preview-filter-toggle-title {
  font-size: 12px;
  font-weight: 700;
  line-height: 1.4;
}

.ci-single-preview-filter-toggle-state {
  font-size: 11px;
  color: #7a879d;
  line-height: 1.3;
}

.ci-single-preview-filter-toggle.is-active {
  color: #fff;
  box-shadow: 0 10px 22px rgba(31, 53, 91, 0.16);
}

.ci-single-preview-filter-toggle.is-active .ci-single-preview-filter-toggle-state {
  color: rgba(255, 255, 255, 0.78);
}

.ci-single-preview-filter-toggle.is-active.is-d {
  background: linear-gradient(180deg, #ee615d 0%, #e53935 100%);
  border-color: #e53935;
}

.ci-single-preview-filter-toggle.is-active.is-m {
  background: linear-gradient(180deg, #48a0ee 0%, #1e88e5 100%);
  border-color: #1e88e5;
}

.ci-single-preview-filter-toggle.is-active.is-t {
  background: linear-gradient(180deg, #a44ac3 0%, #8e24aa 100%);
  border-color: #8e24aa;
}

.ci-single-overlay-selection-handle.is-nw {
  left: -7px;
  top: -7px;
  cursor: nwse-resize;
}

.ci-single-overlay-selection-handle.is-ne {
  right: -7px;
  top: -7px;
  cursor: nesw-resize;
}

.ci-single-overlay-selection-handle.is-sw {
  left: -7px;
  bottom: -7px;
  cursor: nesw-resize;
}

.ci-single-overlay-selection-handle.is-se {
  right: -7px;
  bottom: -7px;
  cursor: nwse-resize;
}

.ci-single-editor-actions {
  justify-content: flex-end;
  margin: 0 20px 20px;
}

@media (max-width: 980px) {
  .ci-single-workspace-body {
    grid-template-columns: 1fr;
  }

  .ci-single-preview-zoom-tools {
    width: 100%;
    justify-content: space-between;
  }

  .ci-preview-zoom-range {
    flex: 1;
    min-width: 88px;
  }
}
.ci-switch-btn.active {
  background: #1890ff;
  color: #fff;
}
.ci-switch-btn:hover:not(.active) {
  background: #f0f5ff;
}
.ci-rebuild-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #666;
}
.ci-rebuild-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}
.ci-generate-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid #91caff;
  border-radius: 4px;
  background: #e6f4ff;
  cursor: pointer;
  color: #0958d9;
}
.ci-generate-btn:hover:not(:disabled) {
  border-color: #4096ff;
  background: #d6e4ff;
}
.ci-generate-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* ====== 结果主体 ====== */
.ci-result-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

/* ====== 通用层块 ====== */
.ci-layer {
  margin-bottom: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  overflow: hidden;
}
.ci-layer-header {
  display: flex;
  align-items: center;
  padding: 10px 14px;
  background: #fafbfc;
  cursor: pointer;
  user-select: none;
  gap: 8px;
}
.ci-layer-header:hover {
  background: #f0f5ff;
}
.ci-layer-icon {
  font-size: 16px;
}
.ci-layer-label {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.ci-page-info {
  font-size: 12px;
  color: #999;
  margin-left: auto;
  margin-right: 4px;
}
.ci-expand-arrow {
  font-size: 10px;
  color: #999;
  transition: transform .2s;
  margin-left: auto;
}
.ci-expand-arrow.expanded {
  transform: rotate(0deg);
}
.ci-expand-arrow:not(.expanded) {
  transform: rotate(-90deg);
}
.ci-layer-content {
  padding: 12px 14px;
}

/* ====== T 层 ====== */
.ci-layer-t {
  border-color: #bae7ff;
}
.ci-layer-t .ci-layer-header {
  background: #e6f7ff;
}

.ci-layer-r-top {
  border-color: #dbe3f0;
  background: #fbfcfe;
}

.ci-r-top-header {
  background: #f4f7fb;
}
.ci-t-block {
  margin-bottom: 14px;
}
.ci-t-block-title {
  font-size: 13px;
  font-weight: 600;
  color: #1890ff;
  margin-bottom: 4px;
}
.ci-t-block-content {
  font-size: 13px;
  color: #444;
  line-height: 1.7;
}
.ci-t-repro-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.ci-t-repro-card {
  border: 1px solid #d9f7be;
  border-radius: 8px;
  background: #f6ffed;
  padding: 8px;
  cursor: pointer;
  transition: box-shadow .2s, transform .2s;
}
.ci-t-repro-card:hover {
  box-shadow: 0 4px 14px rgba(56, 158, 13, 0.18);
  transform: translateY(-1px);
}
.ci-t-repro-thumb {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  border-radius: 6px;
  border: 1px solid #b7eb8f;
  background: #fff;
}
.ci-t-repro-caption {
  margin-top: 8px;
  font-size: 12px;
  color: #389e0d;
  line-height: 1.5;
  word-break: break-word;
}
.ci-t-repro-failed {
  margin-top: 10px;
  font-size: 12px;
  color: #d46b08;
}
.ci-pre-wrap {
  white-space: pre-wrap;
}
.ci-t-advice {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fffbe6;
  border-radius: 4px;
  border: 1px solid #ffe58f;
}
.ci-t-advice-title {
  font-size: 13px;
  font-weight: 600;
  color: #d48806;
  margin-bottom: 6px;
}
.ci-t-advice-item {
  font-size: 13px;
  color: #444;
  line-height: 1.7;
  margin-bottom: 4px;
}
.ci-advice-label {
  font-weight: 600;
  color: #d48806;
}
.ci-t-candidates {
  margin-top: 10px;
  padding: 8px 12px;
  background: #f6ffed;
  border-radius: 4px;
  border: 1px solid #b7eb8f;
}

/* ====== M 层 ====== */
.ci-layer-m {
  border-color: #d9d9d9;
}
.ci-m-section {
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  margin-bottom: 8px;
  overflow: hidden;
}
.ci-m-section.active-single {
  border-color: #1890ff;
}
.ci-m-section-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: #fafafa;
  cursor: pointer;
  gap: 8px;
}
.ci-m-section-header:hover {
  background: #f5f5f5;
}
.ci-m-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px; height: 22px;
  border-radius: 50%;
  background: #1890ff;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}
.ci-m-title {
  font-size: 13px;
  font-weight: 600;
  color: #333;
}
.ci-m-source {
  font-size: 11px;
  color: #999;
  margin-left: auto;
}
.ci-m-layout-badge {
  font-size: 14px;
  cursor: help;
}
.ci-m-section-body {
  padding: 10px 12px;
}
.ci-m-field {
  margin-bottom: 8px;
}
.ci-m-field-label {
  font-size: 12px;
  color: #888;
  font-weight: 600;
  margin-bottom: 2px;
}
.ci-m-field-value {
  font-size: 13px;
  color: #444;
  line-height: 1.6;
}
.ci-m-continuity {
  padding: 6px 10px;
  margin: 6px 0;
  background: #f9f0ff;
  border-radius: 4px;
  font-size: 12px;
  color: #722ed1;
  border: 1px solid #efdbff;
}
.ci-continuity-label {
  font-weight: 600;
}
.ci-m-d-input {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 6px 10px;
  margin: 6px 0;
  background: #fafafa;
  border-radius: 4px;
  border: 1px solid #f0f0f0;
  font-size: 12px;
  color: #666;
}
.ci-m-d-input-topline {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ci-m-d-input-label {
.ci-single-editor-level-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding-right: 10px;
  margin-right: 4px;
  border-right: 1px solid #dde5f1;
  flex-wrap: wrap;
}
.ci-single-editor-level-switch-label {
  font-size: 12px;
  font-weight: 600;
  color: #465066;
}
  font-weight: 600;
  color: #555;
}
.ci-m-d-input-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
}
.ci-m-d-input-badge.is-used {
  background: #f6ffed;
  color: #389e0d;
  border: 1px solid #b7eb8f;
}
.ci-m-d-input-badge.is-suppressed {
  background: #fff7e6;
  color: #d46b08;
  border: 1px solid #ffd591;
}
.ci-m-d-input-reason {
  color: #8c8c8c;
}
.ci-m-d-input-detail {
  color: #8c8c8c;
  line-height: 1.5;
  word-break: break-word;
}
.ci-m-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.ci-action-btn {
  padding: 4px 10px;
  font-size: 12px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #555;
  transition: all .2s;
}
.ci-action-btn:hover {
  border-color: #1890ff;
  color: #1890ff;
}
.ci-m-ocr {
  margin-top: 8px;
  padding: 10px;
  background: #f7f7f7;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
}
.ci-ocr-title {
  font-size: 12px;
  font-weight: 600;
  color: #888;
  margin-bottom: 6px;
}
.ci-low-confidence {
  color: #fa8c16;
  font-weight: 600;
  margin-left: 6px;
}
.ci-ocr-text {
  font-size: 12px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

/* 单图导航 */
.ci-single-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  margin-bottom: 12px;
}
.ci-nav-btn {
  padding: 4px 14px;
  font-size: 13px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
  color: #555;
}
.ci-nav-btn:disabled {
  opacity: .4;
  cursor: not-allowed;
}
.ci-nav-btn:hover:not(:disabled) {
  border-color: #1890ff;
  color: #1890ff;
}
.ci-nav-info {
  font-size: 13px;
  color: #888;
}

/* ====== D 层 ====== */
.ci-layer-d {
  border-color: #d9d9d9;
}
.ci-d-unit {
  margin-bottom: 10px;
  border: 1px solid #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}
.ci-d-unit-header {
  display: flex;
  align-items: center;
  padding: 6px 12px;
  background: #fafafa;
  gap: 8px;
}
.ci-d-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px; height: 20px;
  border-radius: 50%;
  background: #666;
  color: #fff;
  font-size: 10px;
  flex-shrink: 0;
}
.ci-d-source {
  font-size: 12px;
  color: #888;
}
.ci-d-unit-body {
  padding: 8px 12px;
}
.ci-d-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 6px;
}
.ci-d-tab {
  padding: 2px 10px;
  font-size: 11px;
  border: 1px solid #d9d9d9;
  border-radius: 3px;
  background: #fff;
  cursor: pointer;
  color: #888;
}
.ci-d-tab.active {
  background: #1890ff;
  color: #fff;
  border-color: #1890ff;
}
.ci-d-text {
  font-size: 12px;
  line-height: 1.6;
  color: #555;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 250px;
  overflow-y: auto;
  margin: 0;
  background: #f7f7f7;
  padding: 8px;
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}

/* 文件信息 */
.ci-manifest-info {
  margin-top: 14px;
  padding: 10px 14px;
  background: #f9f9f9;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
}
.ci-manifest-label {
  font-size: 12px;
  color: #888;
  line-height: 1.8;
}

/* ====== 布局可视化弹窗 ====== */
.ci-layout-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.ci-layout-dialog {
  background: #fff;
  border-radius: 8px;
  max-width: 90vw;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.ci-layout-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #e8e8e8;
  background: #fafbfc;
  font-weight: 600;
}
.ci-layout-view-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 3px;
  background: #e6f7ff;
  color: #1890ff;
  font-weight: 400;
}
.ci-layout-body {
  padding: 16px;
  overflow: auto;
  flex: 1;
}
.ci-layout-img {
  max-width: 100%;
  height: auto;
}
.ci-layout-iframe {
  width: 80vw;
  height: 78vh;
  border: none;
  display: block;
}
.ci-layout-empty {
  color: #999;
  text-align: center;
  padding: 40px;
}

/* 分析标签栏 */
.ci-tabs-bar {
  display: flex;
  gap: 6px;
  padding: 6px 16px;
  border-bottom: 1px solid #eee;
  background: #fafafa;
  overflow-x: auto;
  flex-shrink: 0;
}
.ci-tab-btn {
  padding: 4px 12px;
  border-radius: 12px;
  border: 1px solid #d0d0d0;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.ci-tab-btn.active {
  background: #4f8ef7;
  color: #fff;
  border-color: #4f8ef7;
}
.ci-tab-btn:hover:not(.active) {
  background: #e8f0fe;
  border-color: #4f8ef7;
}

.ci-progress-track {
  width: 100%;
  height: 10px;
  border-radius: 6px;
  background: #f0f2f5;
  border: 1px solid #e1e4e8;
  overflow: hidden;
}

.ci-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #52c41a, #1890ff);
  transition: width 0.25s ease;
}

.ci-lite-batch-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px 14px;
  padding: 10px 12px 6px;
  border-bottom: 1px dashed #e6e8eb;
  margin-bottom: 8px;
}

.ci-lite-batch-dialog {
  width: min(720px, 92vw);
  max-height: 86vh;
  overflow: auto;
}

.ci-lite-batch-checklist {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 280px;
  overflow: auto;
  margin: 10px 0 12px;
  padding: 8px 10px;
  border: 1px solid #e8ebef;
  border-radius: 8px;
  background: #fafbfc;
}

.ci-lite-batch-check-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.ci-lite-batch-check-item.is-disabled {
  opacity: 0.55;
}

.ci-lite-batch-results {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
  max-height: 360px;
  overflow: auto;
}

.ci-lite-batch-result-row {
  border: 1px solid #e6e8eb;
  border-radius: 8px;
  padding: 8px 10px;
  background: #fff;
}

.ci-lite-batch-result-row.is-ok {
  border-color: #b7eb8f;
  background: #f6ffed;
}

.ci-lite-batch-result-row.is-partial {
  border-color: #ffe58f;
  background: #fffbe6;
}

.ci-lite-batch-result-row.is-fail {
  border-color: #ffa39e;
  background: #fff1f0;
}

.ci-lite-batch-log {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #555;
}

.ci-repro-context-menu {
  position: fixed;
  z-index: 2600;
  min-width: 240px;
  background: #fff;
  border: 1px solid #dfe4ea;
  border-radius: 8px;
  box-shadow: 0 8px 22px rgba(0, 0, 0, 0.16);
  padding: 6px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.ci-repro-context-menu-item {
  border: none;
  background: #fff;
  text-align: left;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: #2f3a4f;
  cursor: pointer;
}

.ci-repro-context-menu-item:hover:not(:disabled) {
  background: #f4f8ff;
}

.ci-repro-context-menu-item:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ci-single-diff-panel {
  border: 1px solid #e6eaf2;
  border-radius: 8px;
  background: #fbfcff;
  padding: 8px;
  max-height: 260px;
  overflow: auto;
  margin-bottom: 10px;
}

.ci-single-diff-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 6px;
  border-radius: 6px;
}

.ci-single-diff-row.is-changed {
  background: #fff8e8;
  border: 1px solid #ffe0a3;
}

.ci-single-diff-col {
  border: 1px solid #e6eaf2;
  border-radius: 6px;
  background: #fff;
}

.ci-single-diff-col-title {
  font-size: 12px;
  color: #5f6b7c;
  border-bottom: 1px solid #edf0f5;
  padding: 4px 8px;
}

.ci-single-diff-col pre {
  margin: 0;
  padding: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.45;
}


</style>
