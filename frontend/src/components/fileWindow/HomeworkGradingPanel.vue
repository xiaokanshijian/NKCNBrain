<template>
  <div class="hg-panel-overlay" :class="{ 'is-page-only': pageViewOnly, 'is-verify-assist': verifyAssist }">
    <aside v-if="!pageViewOnly && !verifyAssist" class="hg-panel">
      <header class="hg-header">
        <div>
          <div class="hg-title">连续图片批改</div>
          <div class="hg-subtitle">{{ fileTitle }} · {{ subjectLabel }}</div>
        </div>
        <div class="hg-header-actions">
          <div v-if="homeworkVersions.length" class="hg-version-wrap">
            <label class="hg-version-label" for="hg-version-select">版本</label>
            <select
              id="hg-version-select"
              class="hg-version-select"
              :value="activeRunId"
              :disabled="!!(runningTask && !runningTask.completed) || versionsLoading"
              @change="onVersionChange"
            >
              <option v-for="ver in homeworkVersions" :key="ver.run_id" :value="ver.run_id">
                {{ versionOptionLabel(ver) }}
              </option>
            </select>
            <button
              v-if="showKeyVersionButton"
              :class="['hg-key-version-btn', { 'is-key': activeVersion?.is_key_version }]"
              type="button"
              :disabled="!canToggleKeyVersion"
              :title="keyVersionButtonTitle"
              @click="toggleKeyVersion"
            >{{ keyVersionButtonText }}</button>
          </div>
          <button
            class="hg-rerun-btn"
            type="button"
            :disabled="rerunLoading || !!(runningTask && !runningTask.completed) || !canOpenRerunDialog"
            :title="rerunButtonTitle"
            @click="confirmRerun"
          >迭代</button>
          <button
            class="hg-rerun-btn"
            type="button"
            :disabled="pinLoading || !!(runningTask && !runningTask.completed) || activeRunId !== 'current' || !activeResult"
            title="把当前批改终态覆盖写入本子结果卡，并仅对诊断卡重新出图/HTML"
            @click="pinResultCards"
          >{{ pinLoading ? '沉淀中…' : '重新沉淀' }}</button>
          <!-- 进度在 mainPage 右下角；关面板也不消失 -->
          <button
            v-if="canResumeSessionRerun"
            class="hg-rerun-btn hg-resume-rerun-btn"
            type="button"
            :disabled="rerunLoading || !!(runningTask && !runningTask.completed) || !canIncrementalRerun"
            title="继续原任务尚未完成的处理，保持原目标和规则"
            @click="resumeSessionRerun"
          >继续处理</button>
          <button class="hg-cross-btn" type="button" :disabled="pass3Loading" @click="openPass3Dialog">双科交叉诊断</button>
          <button class="hg-close" type="button" @click="$emit('close')">×</button>
        </div>
      </header>

      <details class="hg-skill-usage">
        <summary>本次使用 Skill：{{ activeResult?.notebook_skill_usage?.message || '未记录本子 Skill 使用情况' }}</summary>
        <p v-for="item in activeResult?.notebook_skill_usage?.members || []" :key="item.name">
          {{ item.title || item.name }}（{{ item.source }}）<span v-if="item.truncated"> · 已按长度节选</span>
        </p>
        <p v-for="stage in activeResult?.notebook_skill_usage?.stages || []" :key="stage.phase">
          {{ stage.label }}：已确认发送 {{ stage.sent }} 次，返回已接受 {{ stage.accepted }} 次，检查点复用 {{ stage.reused }} 次
        </p>
        <p v-if="activeResult?.notebook_skill_usage?.status === 'selected'">使用记录包含沿用的阶段记录；方法对内容的影响仍需对照核验。</p>
        <p v-if="activeResult?.notebook_skill_usage?.unreadable_audits">部分调用记录不可读，使用统计不完整。</p>
      </details>
      <div v-if="(runningTask && !runningTask.completed) || rerunLoading" class="hg-progress">
        <div class="hg-progress-title">{{ displayProgressSection }}</div>
        <div class="hg-progress-track">
          <div class="hg-progress-bar" :style="{ width: progressPercent + '%' }"></div>
        </div>
        <div v-if="rerunLoading" class="hg-progress-hint">正在准备迭代，界面可能停留数十秒到两分钟，并非卡死。</div>
      </div>

      <main class="hg-body">
        <div v-if="['complete', 'running'].includes(activeResult?.completion?.status)">{{ activeResult.completion.message }}</div>
        <div v-if="reviewCoverageText">{{ reviewCoverageText }}</div>
        <div v-if="checkWarning" class="hg-check-warning" role="alert">{{ checkWarning }}</div>
        <section v-if="userVerification && userVerification.items && userVerification.items.length" class="hg-verify-banner" role="region" aria-label="需加强核实">
          <div class="hg-verify-banner-head">
            <strong>{{ userVerification.title || '需加强核实的位置' }}</strong>
            <span class="hg-verify-counts">
              <em v-for="group in userVerificationGroups" :key="'c-' + group.level" :class="'is-' + group.level.toLowerCase()">{{ group.level }} {{ group.items.length }}</em>
            </span>
          </div>
          <p class="hg-verify-summary">{{ userVerification.summary }}</p>
          <div v-for="group in userVerificationGroups" :key="group.level" class="hg-verify-tier">
            <div class="hg-verify-tier-name">{{ group.title }} <em>{{ group.items.length }}</em></div>
            <div class="hg-verify-chips">
              <button
                v-for="item in group.items"
                :key="item.qid_global || item.label"
                type="button"
                :class="['hg-verify-chip', 'is-' + group.level.toLowerCase()]"
                @click="jumpToEvidence(item.qid_global)"
                :title="item.reason || ''"
              >{{ item.label || item.qid_global }}</button>
            </div>
          </div>
        </section>
        <section v-if="activeResult" class="hg-basis-strip">
          <FeedbackBasisStrip :result="activeResult" :task="runningTask" />
        </section>
        <section v-if="isFinalGradingResult" :class="['hg-red-blue-card', `is-${redBlueReview.color || 'pending'}`]">
          <template v-if="redBlueReady">
            <div class="hg-red-blue-head">
              <div>
                <div class="hg-red-blue-kicker">批改质量红蓝卡标</div>
                <div class="hg-red-blue-score">{{ Number(redBlueReview.score || 0).toFixed(1) }} <small>/ 5</small></div>
              </div>
              <div class="hg-red-blue-status">
                <span>{{ redBlueReview.color_label || redBlueColorLabel }}</span>
                <small>这是批改质量，不是学生成绩</small>
              </div>
            </div>
            <div class="hg-red-blue-rails">
              <div class="is-blue"><span>蓝侧 · 证据</span><strong>{{ Number(redBlueReview.blue_score || 0).toFixed(1) }}</strong></div>
              <div class="is-red"><span>红侧 · 教学</span><strong>{{ Number(redBlueReview.red_score || 0).toFixed(1) }}</strong></div>
            </div>
            <div class="hg-red-blue-dimensions">
              <div v-for="dimension in redBlueDimensions" :key="dimension.key" class="hg-red-blue-dimension">
                <div>
                  <strong>{{ dimension.label }} · {{ Math.round(Number(dimension.weight || 0) * 100) }}%</strong>
                  <span>{{ Number(dimension.score || 0).toFixed(1) }}</span>
                </div>
                <p>{{ displayText(dimension.reason) }}</p>
                <div v-if="dimension.evidence_refs && dimension.evidence_refs.length" class="hg-red-blue-evidence">
                  <button v-for="ev in dimension.evidence_refs" :key="ev" type="button" @click="jumpToEvidence(ev)">{{ evidenceLabel(ev) }}</button>
                </div>
              </div>
            </div>
            <div class="hg-red-blue-reason">
              <strong>评分理由</strong>
              <span>{{ displayText(redBlueReview.reason) || '已按证据与教学双轨完成审计。' }}</span>
            </div>
            <details v-if="redBlueSuggestions.length" class="hg-red-blue-suggestions">
              <summary>查看下一轮迭代建议（{{ redBlueSuggestions.length }}）</summary>
              <article v-for="suggestion in redBlueSuggestions" :key="suggestion.id">
                <div>
                  <span>{{ priorityLabel(suggestion.priority) }}</span>
                  <span>{{ suggestionStageLabel(suggestion.target_stage) }}</span>
                </div>
                <strong>{{ displayText(suggestion.action) }}</strong>
                <p v-if="suggestion.why">{{ displayText(suggestion.why) }}</p>
                <p>验收：{{ displayText(suggestion.acceptance_criteria) }}</p>
                <div v-if="suggestion.evidence_refs && suggestion.evidence_refs.length" class="hg-red-blue-evidence">
                  <button v-for="ev in suggestion.evidence_refs" :key="ev" type="button" @click="jumpToEvidence(ev)">{{ evidenceLabel(ev) }}</button>
                </div>
              </article>
            </details>
          </template>
          <div v-else class="hg-red-blue-empty">
            <div>
              <strong>批改质量红蓝卡标</strong>
              <span>{{ redBlueEmptyText }}</span>
            </div>
            <button
              v-if="canRetryRedBlue"
              type="button"
              :disabled="redBlueRetryLoading || !!(runningTask && !runningTask.completed)"
              @click="$emit('retry-red-blue')"
            >{{ redBlueRetryLoading ? '评分中…' : '重新评分' }}</button>
          </div>
        </section>

        <section v-if="isOpenMaterial && hasOpenMaterialOverview" class="hg-layer hg-layer-open-overview">
          <div class="hg-layer-header hg-open-overview-header">
            <span>开放材料反馈</span>
          </div>
          <div class="hg-layer-content hg-open-overview-content">
            <article class="hg-open-overview-card">
              <h4>主体与版面理解</h4>
              <div v-if="explanationLayers(openMaterialOverview.subject_and_layout).length" class="hg-three-q">
                <div v-for="layer in explanationLayers(openMaterialOverview.subject_and_layout)" :key="layer.key" class="hg-three-q-item">
                  <strong>{{ layer.key }}</strong>
                  <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                    <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                    <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
                  </div>
                  <p v-else>{{ layer.text }}</p>
                </div>
              </div>
              <p v-else>{{ displayText(openMaterialOverview.subject_and_layout) }}</p>
            </article>
            <article class="hg-open-overview-card">
              <h4>内容理解与评述</h4>
              <div v-if="explanationLayers(openMaterialOverview.content_review).length" class="hg-three-q">
                <div v-for="layer in explanationLayers(openMaterialOverview.content_review)" :key="layer.key" class="hg-three-q-item">
                  <strong>{{ layer.key }}</strong>
                  <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                    <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                    <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
                  </div>
                  <p v-else>{{ layer.text }}</p>
                </div>
              </div>
              <p v-else>{{ displayText(openMaterialOverview.content_review) }}</p>
            </article>
            <article class="hg-open-overview-card">
              <h4>下一步建议</h4>
              <ol>
                <li v-for="(step, index) in openMaterialNextSteps" :key="index">{{ displayText(step) }}</li>
              </ol>
            </article>
          </div>
        </section>

        <section class="hg-layer hg-layer-diagnosis">
          <button class="hg-layer-header" type="button" @click="expanded.diagnosis = !expanded.diagnosis">
            <span>整篇诊断</span>
            <span>{{ expanded.diagnosis ? '收起' : '展开' }}</span>
          </button>
          <div v-show="expanded.diagnosis" class="hg-layer-content hg-diagnosis-content">
            <div v-if="diagnosisMetaItems.length" class="hg-diagnosis-meta">
              <span v-for="item in diagnosisMetaItems" :key="item.text" :class="['hg-meta-badge', item.warn ? 'is-warn' : '']">{{ item.text }}</span>
            </div>
            <div v-if="diagnosis.summary" class="hg-summary-card">
              <div v-if="diagnosisSummaryLayers.length" class="hg-three-q">
                <div v-for="layer in diagnosisSummaryLayers" :key="layer.key" class="hg-three-q-item">
                  <strong>{{ layer.key }}</strong>
                  <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                    <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                    <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
                  </div>
                  <p v-else>{{ layer.text }}</p>
                </div>
              </div>
              <template v-else>{{ displayText(diagnosis.summary) }}</template>
            </div>
            <div v-if="unassignedPagesNote" class="hg-process-card" style="border-left: 3px solid #909399;">
              <div class="hg-process-title">布置范围</div>
              <div class="hg-process-text">{{ unassignedPagesNote }}</div>
            </div>
            <div v-if="showEvolutionNarrative" class="hg-process-card">
              <div class="hg-process-title">学习过程概览</div>
              <div v-if="evolutionLayers.length" class="hg-three-q">
                <div v-for="layer in evolutionLayers" :key="layer.key" class="hg-three-q-item">
                  <strong>{{ layer.key }}</strong>
                  <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                    <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                    <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
                  </div>
                  <p v-else>{{ layer.text }}</p>
                </div>
              </div>
              <div v-else class="hg-process-text">{{ evolutionNarrative }}</div>
            </div>
            <div v-for="block in diagnosisBlocks" :key="block.key" :class="['hg-diag-block', `hg-diag-${block.key}`]">
              <div class="hg-diag-label">{{ block.label }}</div>
              <ul class="hg-diag-list">
                <li v-for="(item, index) in block.items" :key="index">{{ item }}</li>
              </ul>
            </div>
            <div v-if="!hasDiagnosis" class="hg-empty">暂无整篇诊断</div>
          </div>
        </section>

        <section class="hg-layer hg-layer-zone">
          <button class="hg-layer-header" type="button" @click="expanded.zone = !expanded.zone">
            <span>认知区域</span>
            <span>{{ expanded.zone ? '收起' : '展开' }}</span>
          </button>
          <div v-show="expanded.zone" class="hg-layer-content hg-zone-grid">
            <div v-for="zone in zoneBlocks" :key="zone.key" :class="['hg-zone-item', `hg-zone-${zone.key}`]">
              <div class="hg-zone-label">{{ zone.label }}</div>
              <div v-if="zone.entries.length" class="hg-zone-entries">
                <div v-for="(entry, idx) in zone.entries" :key="idx" class="hg-zone-entry">
                  <div class="hg-zone-kp-row">
                    <span class="hg-zone-kp">{{ entry.knowledge_point || '相关知识点' }}</span>
                    <span v-if="entry.trend" :class="['hg-zone-tag', `hg-trend-${entry.trend}`]">{{ trendBadgeText(entry.trend) }}</span>
                    <span v-if="entry.stability" class="hg-zone-tag hg-zone-stability">{{ stabilityLabel(entry.stability) }}</span>
                  </div>
                  <div v-if="entry.confidence != null" class="hg-zone-conf">
                    <div class="hg-zone-conf-track"><div class="hg-zone-conf-bar" :style="{ width: Math.round((entry.confidence || 0) * 100) + '%' }"></div></div>
                    <span class="hg-zone-conf-val">置信 {{ Math.round((entry.confidence || 0) * 100) }}%</span>
                  </div>
                  <div v-if="explanationLayers(entry.comment).length" class="hg-zone-comment">
                    <div v-for="layer in explanationLayers(entry.comment)" :key="layer.key" class="hg-three-q-item">
                      <strong>{{ layer.key }}</strong>
                      <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                        <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                        <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
                      </div>
                      <p v-else>{{ layer.text }}</p>
                    </div>
                  </div>
                  <div v-else-if="entry.comment" class="hg-zone-comment">{{ entry.comment }}</div>
                  <div v-if="entry.error_clusters && entry.error_clusters.length" class="hg-zone-clusters">
                    <div v-for="(ec, ecIdx) in entry.error_clusters" :key="ecIdx" class="hg-zone-cluster">
                      <div v-if="ec.cause" class="hg-zone-cluster-cause">· {{ ec.cause }}</div>
                      <div v-if="ec.evidence && ec.evidence.length" class="hg-zone-evidence">
                        <span class="hg-zone-ev-chips">
                          <button v-for="ev in ec.evidence" :key="ev" type="button" class="hg-zone-ev-chip" @click="jumpToEvidence(ev)">{{ evidenceLabel(ev) }}</button>
                        </span>
                      </div>
                    </div>
                  </div>
                  <div v-if="entry.evidence.length" class="hg-zone-evidence">
                    <span class="hg-zone-ev-label">题号：</span>
                    <span class="hg-zone-ev-chips">
                      <button v-for="ev in evidenceSlice(zone.key, idx, entry.evidence)" :key="ev" type="button" class="hg-zone-ev-chip" @click="jumpToEvidence(ev)">{{ evidenceLabel(ev) }}</button>
                      <button v-if="entry.evidence.length > 4" type="button" class="hg-zone-ev-more" @click="toggleEvidenceExpanded(zone.key, idx)">{{ isEvidenceExpanded(zone.key, idx) ? '收起' : `+${entry.evidence.length - 4}` }}</button>
                    </span>
                  </div>
                  <div v-if="zone.key === 'zpd' && entry.suggested_next_step" class="hg-zone-next">
                    <span class="hg-zone-next-label">下一步</span>
                    <span class="hg-zone-next-text">{{ entry.suggested_next_step }}</span>
                  </div>
                </div>
              </div>
              <div v-else class="hg-zone-text">暂无</div>
            </div>
          </div>
        </section>

        <section v-if="!isOpenMaterial && sessionTrends.length >= 1" class="hg-layer hg-layer-trend">
          <button class="hg-layer-header" type="button" @click="toggleTrend">
            <span>学习趋势（按篇次）</span>
            <span>{{ expanded.trend ? '收起' : '展开' }}</span>
          </button>
          <div v-show="expanded.trend" class="hg-layer-content">
            <div ref="trendChartRef" class="hg-trend-chart"></div>
          </div>
        </section>

        <section v-if="!isOpenMaterial && hasCurriculum" class="hg-layer hg-layer-curriculum">
          <button class="hg-layer-header" type="button" @click="expanded.curriculum = !expanded.curriculum">
            <span>知识点 · 课标掌握度</span>
            <span>{{ expanded.curriculum ? '收起' : '展开' }}</span>
          </button>
          <div v-show="expanded.curriculum" class="hg-layer-content">
            <div v-for="dom in curriculumDomains" :key="dom.domain" class="hg-curr-row">
              <div class="hg-curr-head">
                <span class="hg-curr-domain">{{ dom.domain }}</span>
                <span class="hg-curr-rate">{{ Math.round((dom.correct_rate || 0) * 100) }}%（{{ dom.correct }}/{{ dom.total }}）</span>
              </div>
              <div class="hg-curr-track">
                <div class="hg-curr-bar" :class="rateClass(dom.correct_rate)" :style="{ width: Math.round((dom.correct_rate || 0) * 100) + '%' }"></div>
              </div>
            </div>
            <div v-if="!curriculumDomains.length" class="hg-empty">暂无课标掌握度数据</div>
          </div>
        </section>

        <section class="hg-layer hg-layer-page">
          <button class="hg-layer-header" type="button" @click="expanded.pages = !expanded.pages">
            <span>逐页批改</span>
            <span>{{ expanded.pages ? '收起' : '展开' }}</span>
          </button>
          <div v-show="expanded.pages" class="hg-layer-content">
            <div class="hg-page-entry">
              <div>
                <div class="hg-page-entry-title">共 {{ pages.length }} 页批改结果</div>
                <div class="hg-page-entry-meta">进入后可逐页查看原始页面、批改页面与题目反馈</div>
              </div>
              <button class="hg-primary-btn" type="button" :disabled="!pages.length" @click="openPageAt(0, 'grading')">进入逐页查看</button>
            </div>
            <div v-if="!pages.length" class="hg-empty">暂无逐页批改结果</div>
          </div>
        </section>
      </main>
    </aside>

    <div
      v-if="pageDialogVisible"
      class="hg-dialog-overlay"
      :class="{
        'is-verify-assist': verifyAssist,
        'is-va-collapsed': verifyAssist && verifyAssistCollapsed,
      }"
      @click.self="!verifyAssist && closePageDialog()"
    >
      <!-- 核验对照：左原始 / 右批改，中间留给提交弹窗；收起时左右分别收向两侧 -->
      <template v-if="verifyAssist">
        <button
          v-if="verifyAssistCollapsed"
          type="button"
          class="hg-va-rail-btn is-left"
          title="展开对照"
          @click.stop="verifyAssistCollapsed = false"
        >
          <svg class="hg-va-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M8.5 6.5 L13.5 12 L8.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M13.5 6.5 L18.5 12 L13.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
        <button
          v-if="verifyAssistCollapsed"
          type="button"
          class="hg-va-rail-btn is-right"
          title="展开对照"
          @click.stop="verifyAssistCollapsed = false"
        >
          <svg class="hg-va-icon" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M15.5 6.5 L10.5 12 L15.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M10.5 6.5 L5.5 12 L10.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>

        <aside
          v-show="!verifyAssistCollapsed"
          class="hg-va-side is-left"
          :style="{ width: `${verifyAssistLeftWidth}px` }"
        >
          <header class="hg-dialog-header hg-va-side-header">
            <div>
              <div>第 {{ activePage.page }} 页{{ pageViewModeLabel }}</div>
              <div class="hg-dialog-meta">{{ activePageIndex + 1 }} / {{ pages.length }}</div>
            </div>
            <div class="hg-dialog-actions">
              <button class="hg-va-toggle" type="button" title="收起（左收 / 右收）" @click="verifyAssistCollapsed = true">
                <svg class="hg-va-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M15.5 6.5 L10.5 12 L15.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M10.5 6.5 L5.5 12 L10.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
              <button class="hg-close" type="button" title="关闭对照" @click="closePageDialog">×</button>
            </div>
          </header>
          <section
            v-if="pageViewMode === 'grading' && activePage.feedback_context"
            class="hg-page-context is-va-compact"
          >
            <strong>{{ displayText(activePage.feedback_context.education_level_label) }} · {{ displayText(activePage.feedback_context.grade_label) }} · {{ displayText(activePage.feedback_context.subject_label) }}</strong>
            <div>{{ displayText(activePage.feedback_context.unit_label) }}</div>
            <p class="hg-va-context-summary">{{ displayText(activePage.feedback_context.understanding_summary) }}</p>
          </section>
          <div class="hg-va-side-body">
            <div class="hg-image-title">原始页面</div>
            <div
              ref="rawImageWrap"
              class="hg-img-wrap hg-va-raw-stage"
              :class="{ 'is-loading': pageImageLoading }"
            >
              <img
                v-if="activePage.raw_image_path"
                ref="rawImageRef"
                class="hg-page-img"
                :key="`va-raw-${pageImageLoadToken}-${activePage.raw_image_path}-${assetBustKey()}`"
                :src="assetUrl(activePage.raw_image_path, { preview: true })"
                alt="原始页面"
                decoding="async"
                @load="onRawImageLoad"
                @error="onPageImageLoad('raw')"
              />
              <div class="hg-box-layer" v-if="verifyFocusQuestion && rawImageMetrics.width">
                <div
                  v-show="verifyFocusTagVisible"
                  class="hg-verify-focus-tag"
                  :style="verifyFocusTagStyle"
                >{{ verifyFocusTagText }}</div>
                <div
                  class="hg-verify-focus-arrow"
                  :class="verifyFocusArrowClass"
                  :style="verifyFocusArrowStyle"
                  aria-hidden="true"
                />
                <div
                  class="hg-verify-focus-box"
                  :style="verifyFocusBoxStyle"
                  :title="questionTitle(verifyFocusQuestion)"
                  @mouseenter="verifyFocusTagVisible = true"
                  @mouseleave="verifyFocusTagVisible = false"
                />
              </div>
            </div>
          </div>
          <div
            class="hg-va-resize is-left-panel"
            title="拖拽调整宽度"
            @mousedown.prevent="startVerifyAssistResize($event, 'left')"
          />
        </aside>

        <aside
          v-show="!verifyAssistCollapsed"
          class="hg-va-side is-right"
          :style="{ width: `${verifyAssistRightWidth}px` }"
        >
          <header class="hg-dialog-header hg-va-side-header">
            <div>
              <div>{{ rightPaneTitle }}</div>
              <div class="hg-dialog-meta">第 {{ activePage.page }} 页</div>
            </div>
            <div class="hg-dialog-actions">
              <button class="hg-va-toggle" type="button" title="收起（左收 / 右收）" @click="verifyAssistCollapsed = true">
                <svg class="hg-va-icon" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M8.5 6.5 L13.5 12 L8.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M13.5 6.5 L18.5 12 L13.5 17.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
              </button>
              <button class="hg-close" type="button" title="关闭对照" @click="closePageDialog">×</button>
            </div>
          </header>
          <div class="hg-va-side-body">
            <div class="hg-image-title">{{ rightPaneTitle }}</div>
            <div class="hg-stage" ref="stageRef" :class="{ 'is-loading': pageImageLoading }">
              <img
                v-if="activeRightImagePath"
                ref="annotatedImageRef"
                class="hg-page-img"
                :key="`va-right-${pageImageLoadToken}-${activeRightImagePath}-${assetBustKey()}`"
                :src="assetUrl(activeRightImagePath, { preview: true })"
                alt="批改页面"
                decoding="async"
                @load="onAnnotatedImageLoad"
                @error="onAnnotatedImageLoad"
              />
              <div class="hg-box-layer" v-if="imageMetrics.width">
                <button
                  v-for="question in activePage.questions"
                  :key="`va-${question.id}`"
                  class="hg-question-box"
                  type="button"
                  :class="questionBoxClasses(question)"
                  :style="questionBoxStyle(question)"
                  @mouseenter="showQuestionTooltip(question, $event)"
                  @mousemove="moveQuestionTooltip"
                  @mouseleave="hideQuestionTooltip"
                >
                  <span
                    v-if="pageViewMode === 'grading' && !useBakedOverlay"
                    class="hg-confidence-dot"
                    :style="gradingConfidenceDotStyle(question)"
                  />
                  <template v-if="showVerdictMarks">
                    <span v-if="question.importance === 'HIGH'" class="hg-q-flag hg-q-flag-high">重</span>
                    <span v-else-if="question.uncertain_reason" class="hg-q-flag hg-q-flag-uncertain">?</span>
                    <span v-if="question.trend === 'worsening'" class="hg-q-trend hg-q-trend-down">↓</span>
                    <span v-else-if="question.trend === 'improving'" class="hg-q-trend hg-q-trend-up">↑</span>
                  </template>
                </button>
              </div>
              <div
                v-if="hoveredQuestion"
                class="hg-tooltip"
                :class="{ 'is-expanded': tooltipExpanded }"
                :style="tooltipStyle()"
                @mouseenter="onTooltipEnter"
                @mouseleave="onTooltipLeave"
              >
                <div class="hg-tooltip-title">
                  <span>{{ questionTitle(hoveredQuestion) }}</span>
                  <button
                    v-if="tooltipNeedsExpand(hoveredQuestion)"
                    type="button"
                    class="hg-tooltip-expand"
                    @click.stop="tooltipExpanded = !tooltipExpanded"
                  >{{ tooltipExpanded ? '收起' : '展开全文' }}</button>
                </div>
                <div class="hg-tooltip-body">
                  <div v-for="row in tooltipRows(hoveredQuestion)" :key="row.label" class="hg-tooltip-row" :class="{ 'is-block': row.layers && row.layers.length }">
                    <span>{{ row.label }}</span>
                    <div v-if="row.layers && row.layers.length" class="hg-three-q hg-three-q-compact">
                      <div v-for="layer in row.layers" :key="layer.key" class="hg-three-q-item">
                        <strong>{{ layer.key }}</strong>
                        <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                          <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                          <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
                        </div>
                        <p v-else>{{ layer.text }}</p>
                      </div>
                    </div>
                    <strong v-else>{{ row.value }}</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div
            class="hg-va-resize is-right-panel"
            title="拖拽调整宽度"
            @mousedown.prevent="startVerifyAssistResize($event, 'right')"
          />
        </aside>
      </template>

      <div v-else class="hg-dialog">
        <header class="hg-dialog-header">
          <div>
            <div>第 {{ activePage.page }} 页{{ pageViewModeLabel }}</div>
            <div class="hg-dialog-meta">{{ activePageIndex + 1 }} / {{ pages.length }}</div>
          </div>
          <div class="hg-dialog-actions">
            <button class="hg-nav-btn" type="button" :disabled="!canPrevPage" @click="goPrevPage">← 上一页</button>
            <button class="hg-nav-btn" type="button" :disabled="!canNextPage" @click="goNextPage">下一页 →</button>
            <button class="hg-close" type="button" @click="closePageDialog">×</button>
          </div>
        </header>
        <div v-if="pageViewMode === 'grading' && checkWarning" class="hg-check-warning" role="alert">{{ checkWarning }}</div>
        <section v-if="pageViewMode === 'grading' && activePage.feedback_context" class="hg-page-context">
          <strong>{{ displayText(activePage.feedback_context.education_level_label) }} · {{ displayText(activePage.feedback_context.grade_label) }} · {{ displayText(activePage.feedback_context.subject_label) }}</strong>
          <div>{{ displayText(activePage.feedback_context.unit_label) }}</div>
          <div v-if="explanationLayers(activePage.feedback_context.understanding_summary).length" class="hg-three-q">
            <div v-for="layer in explanationLayers(activePage.feedback_context.understanding_summary)" :key="layer.key" class="hg-three-q-item">
              <strong>{{ layer.key }}</strong>
              <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
              </div>
              <p v-else>{{ layer.text }}</p>
            </div>
          </div>
          <p v-else>{{ displayText(activePage.feedback_context.understanding_summary) }}</p>
        </section>
        <div class="hg-dialog-body">
          <div class="hg-image-pane">
            <div class="hg-image-title">原始页面</div>
            <div class="hg-img-wrap" :class="{ 'is-loading': pageImageLoading }">
              <img
                v-if="activePage.raw_image_path"
                class="hg-page-img"
                :src="assetUrl(activePage.raw_image_path, { preview: true })"
                alt="原始页面"
                decoding="async"
                @load="onPageImageLoad('raw')"
                @error="onPageImageLoad('raw')"
              />
            </div>
          </div>
          <div class="hg-image-pane">
            <div class="hg-image-title">{{ rightPaneTitle }}</div>
            <div class="hg-stage" ref="stageRef" :class="{ 'is-loading': pageImageLoading }">
              <img
                v-if="activeRightImagePath"
                ref="annotatedImageRef"
                class="hg-page-img"
                :key="`right-${pageImageLoadToken}-${activeRightImagePath}-${assetBustKey()}`"
                :src="assetUrl(activeRightImagePath, { preview: true })"
                alt="批改页面"
                decoding="async"
                @load="onAnnotatedImageLoad"
                @error="onAnnotatedImageLoad"
              />
              <div class="hg-box-layer" v-if="imageMetrics.width">
                <button
                  v-for="question in activePage.questions"
                  :key="question.id"
                  class="hg-question-box"
                  type="button"
                  :class="questionBoxClasses(question)"
                  :style="questionBoxStyle(question)"
                  @mouseenter="showQuestionTooltip(question, $event)"
                  @mousemove="moveQuestionTooltip"
                  @mouseleave="hideQuestionTooltip"
                >
                  <span
                    v-if="pageViewMode === 'grading' && !useBakedOverlay"
                    class="hg-confidence-dot"
                    :style="gradingConfidenceDotStyle(question)"
                  />
                  <template v-if="showVerdictMarks">
                    <span v-if="question.importance === 'HIGH'" class="hg-q-flag hg-q-flag-high">重</span>
                    <span v-else-if="question.uncertain_reason" class="hg-q-flag hg-q-flag-uncertain">?</span>
                    <span v-if="question.trend === 'worsening'" class="hg-q-trend hg-q-trend-down">↓</span>
                    <span v-else-if="question.trend === 'improving'" class="hg-q-trend hg-q-trend-up">↑</span>
                  </template>
                </button>
              </div>
              <div
                v-if="hoveredQuestion"
                class="hg-tooltip"
                :class="{ 'is-expanded': tooltipExpanded }"
                :style="tooltipStyle()"
                @mouseenter="onTooltipEnter"
                @mouseleave="onTooltipLeave"
              >
                <div class="hg-tooltip-title">
                  <span>{{ questionTitle(hoveredQuestion) }}</span>
                  <button
                    v-if="tooltipNeedsExpand(hoveredQuestion)"
                    type="button"
                    class="hg-tooltip-expand"
                    @click.stop="tooltipExpanded = !tooltipExpanded"
                  >{{ tooltipExpanded ? '收起' : '展开全文' }}</button>
                </div>
                <div class="hg-tooltip-body">
                  <div v-for="row in tooltipRows(hoveredQuestion)" :key="row.label" class="hg-tooltip-row" :class="{ 'is-block': row.layers && row.layers.length }">
                    <span>{{ row.label }}</span>
                    <div v-if="row.layers && row.layers.length" class="hg-three-q hg-three-q-compact">
                      <div v-for="layer in row.layers" :key="layer.key" class="hg-three-q-item">
                        <strong>{{ layer.key }}</strong>
                        <div v-if="layer.key === '这说明什么' && meanTagParts(layer.text).length" class="hg-mean-tags">
                          <div v-for="tag in meanTagParts(layer.text)" :key="tag.name"><em>{{ tag.name }}</em>{{ tag.value }}</div>
                          <p v-if="meanLeftover(layer.text)">{{ meanLeftover(layer.text) }}</p>
                        </div>
                        <p v-else>{{ layer.text }}</p>
                      </div>
                    </div>
                    <strong v-else>{{ row.value }}</strong>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="pass3DialogVisible" class="hg-dialog-overlay" @click.self="closePass3Dialog">
      <div class="hg-pass3-dialog">
        <header class="hg-dialog-header">
          <div>
            <div>双科交叉诊断</div>
            <div class="hg-dialog-meta">选择另一门已批改的学科作业进行交叉分析</div>
          </div>
          <button class="hg-close" type="button" @click="closePass3Dialog">×</button>
        </header>
        <div class="hg-pass3-body">
          <div v-if="pass3Loading" class="hg-empty">正在加载可配对作业…</div>
          <template v-else>
            <div v-if="!pass3Candidates.length" class="hg-empty">
              暂无可配对的其他学科作业。请先完成另一门学科的作业批改。
            </div>
            <ul v-else class="hg-pair-list">
              <li v-for="pair in pass3Candidates" :key="pair.cross_analysis_id" class="hg-pair-item">
                <div class="hg-pair-info">
                  <div class="hg-pair-subjects">{{ pair.subject_a_label }} × {{ pair.subject_b_label }}</div>
                  <div class="hg-pair-files">{{ (pair.files_a || []).join('、') }} ／ {{ (pair.files_b || []).join('、') }}</div>
                </div>
                <button
                  class="hg-primary-btn"
                  type="button"
                  @click="startPass3(pair)"
                >{{ pair.status === 'completed' ? '查看结果' : '开始交叉诊断' }}</button>
              </li>
            </ul>
          </template>
        </div>
      </div>
    </div>

    <div v-if="rerunConfirmVisible" class="hg-rerun-confirm-overlay" @click.self="closeRerunConfirm">
      <div class="hg-rerun-confirm-box" role="dialog" aria-modal="true" aria-labelledby="hg-rerun-confirm-title">
        <div class="hg-rerun-confirm-header">
          <div id="hg-rerun-confirm-title" class="hg-rerun-confirm-title">{{ needsFullRecompute ? '完整新跑' : '迭代批改' }}</div>
          <div class="hg-rerun-confirm-text">
            {{ needsFullRecompute
              ? '本版本依据不可恢复，只能完整新跑：原结果归档保留，将按当前材料设置从预处理重跑整份材料。'
              : '默认沿用本版本依据。原结果保留，所选阶段及下游在新版本重新执行。' }}
          </div>
        </div>
        <div class="hg-rerun-confirm-body">
          <section class="hg-skill-usage">
            <label><input v-model="replaceNotebookSkills" type="checkbox" @change="onNotebookSkillsChange"> 重新选择／采用当前 Skill 内容</label>
            <p v-if="!replaceNotebookSkills">沿用该运行冻结的 Skill 内容。</p>
            <template v-else>
              <p>本次将整份重新处理，保留原结果。</p>
              <NotebookSkillSelector v-model="notebookSkillSelection" :username="skillWorkspace" @valid="notebookSkillValid = $event" />
            </template>
          </section>
          <div class="hg-rerun-stage-list">
            <label
              v-for="option in rerunStageOptions"
                :key="option.value"
                :class="[
                  'hg-rerun-stage-option',
                  {
                    'is-active': selectedRerunStage === option.value,
                    'is-disabled': (preprocessModeChanged || needsFullRecompute || refreshConfiguration || replaceNotebookSkills) && option.value !== 'all',
                  },
                ]"
              >
              <input
                v-model="selectedRerunStage"
                type="radio"
                name="hg-rerun-stage"
                :value="option.value"
                :disabled="(preprocessModeChanged || needsFullRecompute || refreshConfiguration || replaceNotebookSkills) && option.value !== 'all'"
              >
              <span>
                <strong>{{ option.label }}</strong>
                <em>{{ option.description }}</em>
              </span>
            </label>
          </div>

          <section class="hg-rerun-fold is-expanded">
            <div class="hg-rerun-fold-body hg-current-rules-option">
              <label class="hg-red-blue-toggle">
                <input v-model="refreshConfiguration" type="checkbox" @change="onRefreshConfigurationChange">
                <span>
                  <strong>采用当前规则，整份重新处理</strong>
                  <em>读取管理页现行规则；原结果归档保留，不能与分阶段或篇目迭代混用。</em>
                </span>
              </label>
            </div>
          </section>

          <section :class="['hg-rerun-fold', 'is-preprocess', { 'is-expanded': rerunSectionsExpanded.preprocess }]">
            <button
              class="hg-rerun-fold-trigger"
              type="button"
              :aria-expanded="rerunSectionsExpanded.preprocess"
              aria-controls="hg-rerun-preprocess-content"
              @click="rerunSectionsExpanded.preprocess = !rerunSectionsExpanded.preprocess"
            >
              <span>
                <strong>PDF 预处理</strong>
                <em>{{ preprocessFoldSummary }}</em>
              </span>
              <span class="hg-rerun-fold-state">
                {{ rerunSectionsExpanded.preprocess ? '收起' : '展开' }}
                <i aria-hidden="true">⌄</i>
              </span>
            </button>
            <div v-show="rerunSectionsExpanded.preprocess" id="hg-rerun-preprocess-content" class="hg-rerun-fold-body">
              <div class="hg-preprocess-mode-list">
                <label
                  v-for="option in preprocessModeOptions"
                  :key="option.value"
                  :class="['hg-preprocess-mode-option', { 'is-active': selectedPreprocessMode === option.value }]"
                >
                  <input
                    v-model="selectedPreprocessMode"
                    type="radio"
                    name="hg-preprocess-mode"
                    :value="option.value"
                    @change="onPreprocessModeChange"
                  >
                  <span>
                    <strong>{{ option.label }}</strong>
                    <em>{{ option.description }}</em>
                  </span>
                </label>
              </div>
              <div v-if="preprocessModeChanged" class="hg-preprocess-mode-notice">
                预处理模式已改变，本次将自动选择“完整迭代”并重跑整份作业，不能只重跑部分篇目。
              </div>
              <div v-else-if="preprocessResultSummary" class="hg-preprocess-result-summary">
                {{ preprocessResultSummary }}
              </div>
            </div>
          </section>

          <section :class="['hg-rerun-fold', { 'is-expanded': rerunSectionsExpanded.sessions, 'is-disabled': preprocessModeChanged || needsFullRecompute || refreshConfiguration || replaceNotebookSkills }]">
            <button
              class="hg-rerun-fold-trigger"
              type="button"
              :aria-expanded="rerunSectionsExpanded.sessions"
              aria-controls="hg-rerun-session-content"
              @click="rerunSectionsExpanded.sessions = !rerunSectionsExpanded.sessions"
            >
              <span>
                <strong>迭代篇目</strong>
                <em>{{ needsFullRecompute ? '完整新跑将重跑整份材料' : (rerunSessions.length ? `已选 ${selectedRerunSessionIds.length} / ${rerunSessions.length} 篇` : '按整份作业迭代') }}</em>
              </span>
              <span class="hg-rerun-fold-state">
                {{ rerunSectionsExpanded.sessions ? '收起' : '展开' }}
                <i aria-hidden="true">⌄</i>
              </span>
            </button>
            <div v-show="rerunSectionsExpanded.sessions" id="hg-rerun-session-content" class="hg-rerun-fold-body">
              <div v-if="rerunSessions.length" class="hg-rerun-session-head">
                <span>选择本轮要处理的篇目</span>
                <span>
                  <button type="button" :disabled="preprocessModeChanged || needsFullRecompute || refreshConfiguration || replaceNotebookSkills" @click="selectAllRerunSessions">全选</button>
                  <button type="button" :disabled="preprocessModeChanged || needsFullRecompute || refreshConfiguration || replaceNotebookSkills" @click="clearRerunSessions">清空</button>
                </span>
              </div>
              <div v-if="rerunSessions.length" class="hg-rerun-session-list">
                <label v-for="item in rerunSessions" :key="item.session_id" class="hg-rerun-session-option">
                  <input v-model="selectedRerunSessionIds" type="checkbox" :value="item.session_id" :disabled="preprocessModeChanged || needsFullRecompute || refreshConfiguration || replaceNotebookSkills">
                  <span>{{ rerunSessionLabel(item) }}</span>
                </label>
              </div>
              <div v-else class="hg-rerun-session-empty">{{ needsFullRecompute ? '完整新跑将重跑整份材料。' : '当前结果暂未提供篇目列表，将按整份作业迭代。' }}</div>
            </div>
          </section>

          <section :class="['hg-rerun-fold', 'is-red-blue', { 'is-expanded': rerunSectionsExpanded.redBlue }]">
            <button
              class="hg-rerun-fold-trigger"
              type="button"
              :aria-expanded="rerunSectionsExpanded.redBlue"
              aria-controls="hg-rerun-red-blue-content"
              @click="rerunSectionsExpanded.redBlue = !rerunSectionsExpanded.redBlue"
            >
              <span>
                <strong>红蓝卡标反馈</strong>
                <em v-if="redBlueReady">{{ redBlueFeedbackFoldSummary }}</em>
                <em v-else>当前卡标不可用</em>
              </span>
              <span class="hg-rerun-fold-state">
                {{ rerunSectionsExpanded.redBlue ? '收起' : '展开' }}
                <i aria-hidden="true">⌄</i>
              </span>
            </button>
            <div v-show="rerunSectionsExpanded.redBlue" id="hg-rerun-red-blue-content" class="hg-rerun-fold-body">
              <label :class="['hg-red-blue-toggle', { 'is-disabled': !redBlueReady }]">
                <input v-model="useRedBlueFeedback" type="checkbox" :disabled="!redBlueReady">
                <span>
                  <strong>参考本版本红蓝卡标</strong>
                  <em>{{ redBlueReady ? '本次打开默认开启；原图、结构化证据与学科规则始终优先' : '卡标缺失或评分失败，可不参考卡标继续迭代' }}</em>
                </span>
              </label>
              <div v-if="useRedBlueFeedback && redBlueReady && !redBlueEarlyStagesEnabled" class="hg-rerun-feedback-policy">
                当前策略：卡标暂不作用于无损版面和无损理解，仅在三区批改阶段使用。
              </div>
              <div v-if="useRedBlueFeedback && redBlueReady" class="hg-rerun-feedback-preview">
                <div><strong>来源 {{ Number(redBlueReview.score || 0).toFixed(1) }} / 5</strong> · {{ displayText(redBlueReview.reason) }}</div>
                <ul v-if="applicableRedBlueSuggestions.length">
                  <li v-for="item in applicableRedBlueSuggestions" :key="item.id">{{ displayText(item.action) }}</li>
                </ul>
                <div v-else>本轮所选阶段与篇目没有对应建议，不会注入卡标反馈。</div>
              </div>
            </div>
          </section>
        </div>
        <div class="hg-rerun-confirm-actions">
          <button class="hg-rerun-cancel-btn" type="button" @click="closeRerunConfirm">取消</button>
          <button class="hg-rerun-confirm-btn" type="button" :disabled="rerunSubmitDisabled" @click="submitRerun">{{ needsFullRecompute ? '开始完整新跑' : '开始迭代' }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { API_BASE_URL } from '@/config/apiConfig'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import { resolveHomeworkEvidencePage } from '@/utils/homeworkEvidence'
import { listCIPass3Pairs, feedbackMaterialSettings } from '@/api/continuous_image'
import FeedbackBasisStrip from './FeedbackBasisCard.vue'
import NotebookSkillSelector from './NotebookSkillSelector.vue'

const HOMEWORK_INTERNAL_TERM_LABELS = Object.freeze({
  source_lock: '证据来源不足',
  no_audio_source: '缺少音频或听力原文',
  source_locked: '题目缺少必要来源',
  answer_sentence_required: '应用题缺少完整答话',
  missing_answer_statement: '缺少最终答话',
  missing_final_answer_statement: '缺少最终答话',
  math_application_missing_answer_statement: '应用题缺少最终答话',
  unit_required: '答案单位不完整或不匹配',
  final_form_required: '答案未满足化简或指定形式',
  term_required: '术语或运算律名称不完整',
  process_required: '缺少题目要求的过程或方法',
  missing_audio_context: '缺少听力材料',
  missing_context: '缺少必要上下文',
  missing_visual_evidence: '缺少可核对的图像证据',
  incorrect_option_selection: '选项选择错误',
  concept_error: '概念理解错误',
  operation_law_name_incomplete: '运算律名称不完整',
  context_mismatch: '语境不匹配',
  choice_mismatch: '选项选择错误',
  verb_form_incomplete: '动词形式不完整',
  cross_page_attempted: '跨页信息已尝试修补，仍建议复核',
  cross_page_unresolved: '跨页内容不足',
  single_page: '单页信息不足',
  verifier_override: '规则复核改为待确认',
  blind_spot: '盲区',
  friction_zone: '内耗区',
  zpd: '最近发展区',
  knowledge_point: '知识点',
  qid_global: '全局题号',
  recurrence_hint: '是否重复出现',
  ontology: '诊断结果',
  student_ontology: '学科诊断结果',
  mastery_trajectory: '掌握变化轨迹',
  fallback_used: '已使用兜底',
  built_by: '生成链路',
  confidence: '置信度',
  trend: '变化趋势',
  stability: '稳定性',
  no_observed: '本次未观察到显著问题',
  extension_recommendation: '拓展提升建议',
  generic_extension: '拓展提升建议',
  improving: '改善中',
  worsening: '需关注',
  stable: '基本稳定',
  transient: '阶段性',
  persistent: '持续性',
  acquired: '基本掌握',
  consolidating: '正在巩固',
  struggling: '困难较多',
  recurring: '反复出现',
  new: '新出现',
  na: '不适用',
})

export default {
  name: 'HomeworkGradingPanel',
  components: { FeedbackBasisStrip, NotebookSkillSelector },
  props: {
    activeResult: Object,
    activeAnalysisId: String,
    activeRunId: {
      type: String,
      default: 'current',
    },
    homeworkVersions: {
      type: Array,
      default: () => [],
    },
    versionsLoading: Boolean,
    keyVersionLoading: Boolean,
    rerunLoading: Boolean,
    pinLoading: {
      type: Boolean,
      default: false,
    },
    redBlueRetryLoading: Boolean,
    runningTask: Object,
    pageViewOnly: {
      type: Boolean,
      default: false,
    },
    /** 提交核验时：左侧停靠逐页对照，不挡卡片 HTML 提交弹窗 */
    verifyAssist: {
      type: Boolean,
      default: false,
    },
    /** 核验迭代等回写后刷新标注图，避免浏览器仍显示旧 PNG 上的对错/白灰黑图标 */
    assetCacheBust: {
      type: [Number, String],
      default: 0,
    },
  },
  emits: ['close', 'close-verify-assist', 'start-pass3', 'rerun', 'retry-red-blue', 'switch-version', 'toggle-key-version', 'start-pin-result-cards', 'result-cards-pinned'],
  data() {
    return {
      expanded: { diagnosis: true, zone: true, trend: true, curriculum: true, pages: true, verifyList: false },
      evidenceExpanded: {},
      pageDialogVisible: false,
      pageViewMode: 'grading',
      activePageIndex: 0,
      pageImageLoading: false,
      pageImageLoadToken: 0,
      pageImagePending: { raw: false, annotated: false },
      _prefetchCache: null,
      hoveredQuestion: null,
      tooltipPointer: null,
      tooltipExpanded: false,
      tooltipPinned: false,
      _tooltipHideTimer: null,
      imageMetrics: { left: 0, top: 0, width: 0, height: 0 },
      rawImageMetrics: { left: 0, top: 0, width: 0, height: 0 },
      verifyFocusQid: '',
      verifyFocusTagVisible: true,
      verifyAssistCollapsed: false,
      verifyAssistLeftWidth: 460,
      verifyAssistRightWidth: 520,
      _vaResize: null,
      // 逐页查看用缩放预览；300DPI 原图太大，直接拉会卡数秒
      pagePreviewWidth: 1600,
      trendChart: null,
      trendResizeObserver: null,
      pass3DialogVisible: false,
      pass3Loading: false,
      pass3Candidates: [],
      rerunConfirmVisible: false,
      refreshConfiguration: false,
      replaceNotebookSkills: false,
      notebookSkillSelection: { enabled: false, names: [] },
      notebookSkillValid: true,
      selectedRerunStage: 'grading',
      selectedRerunSessionIds: [],
      selectedPreprocessMode: 'scan',
      useRedBlueFeedback: true,
      rerunSectionsExpanded: {
        preprocess: false,
        sessions: false,
        redBlue: false,
      },
      preprocessModeOptions: [
        { value: 'auto', label: '自动识别（推荐）', description: '逐页区分扫描件和拍照页；增强不安全时自动使用原图' },
        { value: 'scan', label: '扫描件模式', description: '沿用原有红笔去除与白底处理，适合规整 PDF 扫描件' },
        { value: 'photo', label: '拍照增强', description: '校正光照和纸张底色；质量门禁不通过时自动使用原图' },
        { value: 'off', label: '关闭预处理（原图）', description: '只将 PDF 渲染为图片，不去红笔、不白底、不增强' },
      ],
      rerunStageOptions: [
        { value: 'layout', label: '迭代无损版面', description: '清空无损版面、无损理解和三区批改结果' },
        { value: 'understanding', label: '迭代无损理解', description: '保留版面检测，清空无损理解和三区批改结果' },
        { value: 'grading', label: '迭代三区批改', description: '保留无损版面和无损理解，刷新诊断与批改图' },
        { value: 'all', label: '完整迭代', description: '清空当前工作区，从 PDF 预处理重新跑完整流程' },
      ],
      // 与 confidence_zones.py GRAY_*_RGB_BY_SHADE 同步
      grayRgbByShade: {
        box: { gray_deep: 92, gray_mid: 128, gray_light: 168 },
        dot: { gray_deep: 108, gray_mid: 148, gray_light: 188 },
      },
      // 与 confidence_zones.py SUBJECT_THRESHOLDS 同步
      confidenceThresholdsBySubject: {
        chinese: {
          layout: { white: 89, black: 75 },
          understanding: { white: 90, black: 82 },
          grading: { white: 92, black: 83 },
        },
        math: {
          layout: { white: 86, black: 75 },
          understanding: { white: 89, black: 82 },
          grading: { white: 91, black: 83 },
        },
        english: {
          layout: { white: 91, black: 75 },
          understanding: { white: 92, black: 82 },
          grading: { white: 94, black: 83 },
        },
      },
    }
  },
  computed: {
    skillWorkspace() { return this.activeResult?.manifest?.username || localStorage.getItem('userId') || '' },
    reviewCoverageText() {
      const coverage = this.manifest.pass1_review?.coverage
      if (!coverage) return ''
      const skipped = (coverage.policy_skipped_pages || []).length
      const checked = Math.max(0, (coverage.completed_pages || []).length - skipped)
      return `逐页复核：${checked}页已核对，${skipped}页按当前策略免检，${(coverage.incomplete_pages || []).length}页未完成。`
    },
    checkWarning() {
      const completion = this.runningTask?.completion || this.activeResult?.completion
      if (completion && ['incomplete', 'unverified'].includes(completion.status)) {
        return [completion.message, ...(completion.issues || []).map(item => item.message)].join(' ')
      }
      if (this.manifest.content_validation?.status === 'needs_review') {
        return '部分反馈尚未通过核验；已保留有效内容，待复核项不作为确定结论。'
      }
      if (this.manifest.hallucination?.status === 'failed') {
        return '批改复核未完成，结果已保留，请结合原文人工核实。'
      }
      return this.manifest.rule_profile?.status === 'failed'
        ? '部分辅助检查未完成，请结合原文核实建议。' : ''
    },
    manifest() {
      return this.activeResult?.manifest || {}
    },
    currentPreprocessMode() {
      const mode = this.manifest?.preprocess?.requested_mode
      return ['auto', 'scan', 'photo', 'off'].includes(mode) ? mode : 'scan'
    },
    preprocessModeChanged() {
      return this.selectedPreprocessMode !== this.currentPreprocessMode
    },
    preprocessFoldSummary() {
      const labels = {
        auto: '自动识别',
        scan: '扫描件模式',
        photo: '拍照增强',
        off: '关闭预处理（原图）',
      }
      const selected = labels[this.selectedPreprocessMode] || labels.scan
      return this.preprocessModeChanged ? `${selected} · 将完整重跑` : selected
    },
    preprocessResultSummary() {
      const preprocess = this.manifest?.preprocess
      const summary = preprocess?.summary
      if (!summary || typeof summary !== 'object') return ''
      const parts = []
      if (Number(summary.scan_page_count) > 0) parts.push(`扫描处理 ${Number(summary.scan_page_count)} 页`)
      if (Number(summary.photo_page_count) > 0) parts.push(`拍照增强 ${Number(summary.photo_page_count)} 页`)
      if (Number(summary.off_page_count) > 0) parts.push(`原图 ${Number(summary.off_page_count)} 页`)
      if (Number(summary.fallback_page_count) > 0) parts.push(`安全回退 ${Number(summary.fallback_page_count)} 页`)
      return parts.length ? `当前结果：${parts.join('，')}` : ''
    },
    rerunSubmitDisabled() {
      if (this.replaceNotebookSkills && !this.notebookSkillValid) return true
      if (this.rerunLoading) return true
      if (this.needsFullRecompute || this.preprocessModeChanged || this.refreshConfiguration || this.replaceNotebookSkills) return this.selectedRerunStage !== 'all'
      return Boolean(this.rerunSessions.length && !this.selectedRerunSessionIds.length)
    },
    redBlueReview() {
      const value = this.activeResult?.red_blue_review
      return value && typeof value === 'object' ? value : { status: 'missing' }
    },
    redBlueReady() {
      return this.redBlueReview.status === 'ready'
    },
    redBlueDimensions() {
      return Array.isArray(this.redBlueReview.dimensions) ? this.redBlueReview.dimensions : []
    },
    redBlueSuggestions() {
      return Array.isArray(this.redBlueReview.suggestions) ? this.redBlueReview.suggestions : []
    },
    redBlueColorLabel() {
      const labels = { red: '红·教学偏重', blue: '蓝·证据偏重', purple: '紫·平衡' }
      return labels[this.redBlueReview.color] || '评分待补充'
    },
    redBlueFeedbackPolicy() {
      const value = this.activeResult?.red_blue_feedback_policy
      return value && typeof value === 'object'
        ? value
        : { early_stages_enabled: false, grading_enabled: true }
    },
    redBlueEarlyStagesEnabled() {
      return this.redBlueFeedbackPolicy.early_stages_enabled === true
    },
    redBlueApplicableStages() {
      const target = this.selectedRerunStage
      if (target === 'all') {
        return this.redBlueEarlyStagesEnabled
          ? ['layout', 'understanding', 'grading']
          : ['grading']
      }
      if (target === 'grading') return ['grading']
      return this.redBlueEarlyStagesEnabled && ['layout', 'understanding'].includes(target)
        ? [target]
        : []
    },
    redBlueFeedbackFoldSummary() {
      if (!this.useRedBlueFeedback) return '本轮不参考'
      const source = `来源 ${Number(this.redBlueReview.score || 0).toFixed(1)} / 5`
      if (!this.redBlueApplicableStages.length) return '已开启 · 当前所选阶段暂不注入'
      if (!this.redBlueEarlyStagesEnabled && this.selectedRerunStage === 'all') {
        return `已开启 · 仅用于三区批改 · ${source}`
      }
      return `已开启 · ${source}`
    },
    isFinalGradingResult() {
      return this.manifest?.stages?.grading === 'done' || this.manifest?.status === 'completed'
    },
    canRetryRedBlue() {
      const action = this.activeResult?.available_actions?.retry_quality
      return action ? action.enabled : false
    },
    redBlueEmptyText() {
      const action = this.activeResult?.available_actions?.retry_quality
      if (action?.reason) return action.reason
      if (this.redBlueReview.status === 'failed') {
        return '质量评分待补充。已保留报告，可单独重新评分。'
      }
      return this.canIncrementalRerun
        ? '当前版本尚无卡标，可单独生成；完整批改结果不受影响。'
        : '该历史版本生成时尚未包含卡标。'
    },
    /** 当前版本即可打开迭代面板；快照不可恢复时走完整新跑 */
    canOpenRerunDialog() {
      return (this.activeRunId || 'current') === 'current' && Boolean(this.activeResult?.analysis_id || this.activeAnalysisId)
    },
    needsFullRecompute() {
      return this.canOpenRerunDialog && this.activeResult?.snapshot_status !== 'complete'
    },
    /** 可沿用原快照做分阶段/篇目迭代 */
    canIncrementalRerun() {
      const action = this.activeResult?.available_actions?.rerun_grading
      return this.canOpenRerunDialog && (action ? action.enabled : this.activeResult?.snapshot_status === 'complete')
    },
    canRerunCurrentVersion() {
      return this.canOpenRerunDialog
    },
    activeVersion() {
      const runId = this.activeRunId || 'current'
      return (this.homeworkVersions || []).find(ver => ver?.run_id === runId) || null
    },
    keyVersionCount() {
      return (this.homeworkVersions || []).filter(ver => ver?.is_key_version && !ver?.is_current).length
    },
    showKeyVersionButton() {
      return Boolean(this.activeVersion && !this.activeVersion.is_current)
    },
    canToggleKeyVersion() {
      if (!this.showKeyVersionButton) return false
      if (this.versionsLoading || this.keyVersionLoading || (this.runningTask && !this.runningTask.completed)) return false
      return Boolean(this.activeVersion?.is_key_version) || this.keyVersionCount < 3
    },
    keyVersionButtonText() {
      return this.activeVersion?.is_key_version ? '取消关键' : '设为关键'
    },
    keyVersionButtonTitle() {
      if (!this.showKeyVersionButton) return '当前版本不能设为关键历史版本'
      if (this.activeVersion?.is_key_version) return '取消关键历史版本标记'
      if (this.keyVersionCount >= 3) return '关键历史版本最多只能设置 3 个；已有历史版本均保留'
      return '设为关键历史版本'
    },
    rerunButtonTitle() {
      if ((this.activeRunId || 'current') !== 'current') return '历史版本不可迭代，请切回当前版本'
      if (this.needsFullRecompute) return '本版本依据不可恢复，点击后仅可完整新跑'
      if (!this.canOpenRerunDialog) return '当前没有可迭代的批改结果'
      return '迭代当前版本；已有历史版本均保留'
    },
    rerunSessions() {
      return Array.isArray(this.activeResult?.rerun_sessions) ? this.activeResult.rerun_sessions : []
    },
    sessionRerunState() {
      const value = this.activeResult?.session_rerun
      return value && typeof value === 'object' ? value : {}
    },
    canResumeSessionRerun() {
      if (this.activeResult?.available_actions?.resume) return this.activeResult.available_actions.resume.enabled
      return this.canIncrementalRerun
        && Boolean(this.sessionRerunState.resume_available)
        && Array.isArray(this.sessionRerunState.remaining_session_ids)
        && this.sessionRerunState.remaining_session_ids.length > 0
    },
    kpNameMap() {
      return this.activeResult?.kp_name_map || {}
    },
    pages() {
      return Array.isArray(this.activeResult?.pages) ? this.activeResult.pages : []
    },
    activePage() {
      return this.pages[this.activePageIndex] || { page: 0, questions: [] }
    },
    verifyFocusQuestion() {
      if (!this.verifyAssist || !this.verifyFocusQid) return null
      const questions = this.activePage?.questions || []
      return questions.find(q => String(q.id) === String(this.verifyFocusQid)) || null
    },
    verifyFocusTone() {
      const question = this.verifyFocusQuestion
      const blue = { solid: '#2d6fae', fill: 'rgba(45, 111, 174, 0.16)' }
      if (!question) return blue
      if (this.pageViewMode === 'layout' || this.pageViewMode === 'understanding') {
        return blue
      }
      const verdict = String(question.verdict || '')
      if (verdict === 'correct') return { solid: '#1f8a3b', fill: 'rgba(31, 138, 59, 0.16)' }
      if (verdict === 'wrong') return { solid: '#d23b32', fill: 'rgba(210, 59, 50, 0.16)' }
      if (verdict === 'partial') return { solid: '#d67e23', fill: 'rgba(214, 126, 35, 0.16)' }
      return blue
    },
    verifyFocusBoxStyle() {
      const geom = this.verifyFocusGeom
      if (!geom) return { display: 'none' }
      const tone = this.verifyFocusTone
      const base = {
        left: `${geom.left}px`,
        top: `${geom.top}px`,
        width: `${geom.width}px`,
        height: `${geom.height}px`,
        borderColor: tone.solid,
        background: tone.fill,
        borderWidth: '2px',
      }
      if (this.pageViewMode === 'layout' || this.pageViewMode === 'understanding') {
        const question = this.verifyFocusQuestion
        const confidence = this.pageViewMode === 'layout'
          ? question.layout_confidence
          : this.combinedRecognitionUnderstandingConfidence(question)
        const colors = this.confidenceBoxColors(confidence, this.pageViewMode) || {}
        return {
          ...base,
          ...colors,
          borderWidth: '2px',
          borderStyle: 'solid',
        }
      }
      return base
    },
    verifyFocusArrowClass() {
      const geom = this.verifyFocusGeom
      if (!geom) return ''
      return geom.placeLeft ? 'is-from-left' : 'is-from-right'
    },
    verifyFocusGeom() {
      const question = this.verifyFocusQuestion
      const m = this.rawImageMetrics
      if (!question || !m.width) return null
      const bbox = question.bbox || this.positionToBbox(question.position)
      const w = Number(bbox.w || 0)
      const h = Number(bbox.h || 0)
      if (!(w > 0) || !(h > 0)) return null
      const rawW = Math.max(8, w * m.width)
      const rawH = Math.max(8, h * m.height)
      const scale = 1.08
      const width = rawW * scale
      const height = rawH * scale
      const left = (m.left + Number(bbox.x || 0) * m.width) - (width - rawW) / 2
      const top = (m.top + Number(bbox.y || 0) * m.height) - (height - rawH) / 2
      return {
        left,
        top,
        width,
        height,
        placeLeft: left >= 28,
      }
    },
    verifyFocusArrowStyle() {
      const geom = this.verifyFocusGeom
      if (!geom) return { display: 'none' }
      const tone = this.verifyFocusTone
      const mid = geom.top + geom.height / 2
      if (geom.placeLeft) {
        return {
          left: `${Math.max(2, geom.left - 22)}px`,
          top: `${mid - 9}px`,
          borderLeftColor: tone.solid,
        }
      }
      return {
        left: `${geom.left + geom.width + 6}px`,
        top: `${mid - 9}px`,
        borderRightColor: tone.solid,
      }
    },
    verifyFocusTagText() {
      const question = this.verifyFocusQuestion
      if (!question) return ''
      const id = question.id ? String(question.id) : ''
      return this.isOpenMaterial ? `内容 ${id}` : `题目 ${id}`
    },
    verifyFocusTagStyle() {
      const geom = this.verifyFocusGeom
      if (!geom) return { display: 'none' }
      const tagH = 26
      let top = geom.top - tagH - 4
      if (top < 2) top = geom.top + geom.height + 4
      return {
        left: `${Math.max(2, geom.left)}px`,
        top: `${top}px`,
      }
    },
    canPrevPage() {
      return this.activePageIndex > 0
    },
    canNextPage() {
      return this.activePageIndex < this.pages.length - 1
    },
    showVerdictMarks() {
      return this.pageViewMode === 'grading'
    },
    pageViewModeLabel() {
      const labels = { layout: ' · 无损版面', understanding: ' · 无损理解', grading: '批改' }
      return labels[this.pageViewMode] || '批改'
    },
    rightPaneTitle() {
      const labels = { layout: '无损版面', understanding: '无损理解', grading: '批改页面' }
      return labels[this.pageViewMode] || '批改页面'
    },
    activeRightImagePath() {
      const page = this.activePage || {}
      if (this.pageViewMode === 'layout') {
        return page.annotated_layout_image_path || page.clean_image_path || ''
      }
      if (this.pageViewMode === 'understanding') {
        return page.annotated_understanding_image_path || page.clean_image_path || ''
      }
      return page.annotated_image_path || page.clean_image_path || ''
    },
    useBakedOverlay() {
      const page = this.activePage || {}
      if (this.pageViewMode === 'layout') return Boolean(page.annotated_layout_image_path)
      if (this.pageViewMode === 'understanding') return Boolean(page.annotated_understanding_image_path)
      return Boolean(page.annotated_image_path)
    },
    confidenceMode() {
      if (this.pageViewMode === 'layout') return 'layout'
      if (this.pageViewMode === 'understanding') return 'understanding'
      return 'grading'
    },
    gradingMarkPx() {
      const h = Number(this.imageMetrics.height || 0)
      if (!h) return 20
      return Math.max(20, Math.round(h / 80))
    },
    report() {
      return this.activeResult?.report || {}
    },
    isOpenMaterial() {
      const materialType = this.manifest?.feedback_context?.material_type
        || this.activeResult?.feedback_context?.material_type
        || ''
      return materialType === 'notes' || materialType === 'composition'
    },
    openMaterialOverview() {
      const overview = this.report.open_material_overview
      return overview && typeof overview === 'object' ? overview : {}
    },
    openMaterialNextSteps() {
      return Array.isArray(this.openMaterialOverview.next_steps)
        ? this.openMaterialOverview.next_steps.filter(item => this.cleanText(item))
        : []
    },
    hasOpenMaterialOverview() {
      return Boolean(
        this.cleanText(this.openMaterialOverview.subject_and_layout)
        && this.cleanText(this.openMaterialOverview.content_review)
        && this.openMaterialNextSteps.length
      )
    },
    diagnosis() {
      return this.report.diagnosis || {}
    },
    userVerification() {
      const uv = this.report.user_verification
      if (uv && typeof uv === 'object' && Array.isArray(uv.items) && uv.items.length) return uv
      return null
    },
    userVerificationGroups() {
      const items = (this.userVerification && this.userVerification.items) || []
      const titles = {
        I: 'I · 最应该优先核验的',
        II: 'II · 其次应该先核验的',
        III: 'III · 再次可做核验的',
      }
      const groups = ['I', 'II', 'III'].map((level) => ({
        level,
        title: titles[level],
        items: items.filter((it) => String(it.level || '') === level),
      })).filter((group) => group.items.length)
      const rest = items.filter((it) => !['I', 'II', 'III'].includes(String(it.level || '')))
      if (rest.length) groups.push({ level: 'other', title: '需加强核实', items: rest })
      return groups
    },
    unassignedPagesNote() {
      const note = (this.report && this.report.unassigned_pages_note)
        || (this.report && this.report.grading_config && this.report.grading_config.note)
        || ''
      if (note) return note
      const pages = (this.report && this.report.unassigned_pages) || []
      if (Array.isArray(pages) && pages.length) {
        return '未布置页：' + pages.join(',') + '（本轮未批改）'
      }
      return ''
    },
    hasDiagnosis() {
      return Boolean(
        this.diagnosis.summary
        || this.unassignedPagesNote
        || this.evolutionNarrative
        || this.diagnosisBlocks.some(block => block.items.length)
      )
    },
    diagnosisBlocks() {
      return [
        { key: 'strengths', label: '优势', items: this.cleanList(this.diagnosis.strengths) },
        { key: 'main_problems', label: '主要问题', items: this.cleanList(this.diagnosis.main_problems) },
        { key: 'next_actions', label: '下一步', items: this.cleanList(this.diagnosis.next_actions) },
      ].filter(block => block.items.length)
    },
    zoneBlocks() {
      const data = this.report.zone_classification || {}
      const parse = (raw) => {
        if (!Array.isArray(raw)) {
          const text = this.kpName(this.cleanText(raw))
          return text ? [{ knowledge_point: text, comment: '', evidence: [], error_clusters: [] }] : []
        }
        return raw.map(item => {
          if (item && typeof item === 'object') {
            const evIds = Array.isArray(item.evidence_question_ids)
              ? item.evidence_question_ids.map(id => this.cleanEvidenceId(id)).filter(Boolean)
              : []
            const clusters = Array.isArray(item.error_clusters)
              ? item.error_clusters.map(ec => ({
                  cause: this.displayText(ec && ec.cause),
                  evidence: Array.isArray(ec && ec.evidence) ? ec.evidence.map(id => this.cleanEvidenceId(id)).filter(Boolean) : [],
                })).filter(ec => ec.cause || ec.evidence.length)
              : []
            return {
              knowledge_point: this.kpName(this.cleanText(item.knowledge_point)),
              comment: this.displayText(item.comment),
              evidence: evIds,
              error_clusters: clusters,
              stability: this.cleanText(item.stability),
              trend: this.cleanText(item.trend),
              confidence: typeof item.confidence === 'number' ? item.confidence : null,
              suggested_next_step: this.displayText(item.suggested_next_step),
            }
          }
          const text = this.kpName(this.cleanText(item))
          return { knowledge_point: text, comment: '', evidence: [], error_clusters: [] }
        }).filter(e => e.knowledge_point || e.comment || e.evidence.length || (e.error_clusters && e.error_clusters.length))
      }
      return [
        { key: 'blind_spot', label: '盲区', entries: parse(data.blind_spot) },
        { key: 'friction_zone', label: '内耗区', entries: parse(data.friction_zone) },
        { key: 'zpd', label: '最近发展区', entries: parse(data.zpd) },
      ]
    },
    ontology() {
      return this.activeResult?.ontology || {}
    },
    evolutionNarrative() {
      const reportMeta = this.report?._ontology_metadata || {}
      return this.displayPracticeText(this.ontology.evolution_narrative || reportMeta.evolution_narrative || '')
    },
    showEvolutionNarrative() {
      const evo = String(this.ontology.evolution_narrative || this.report?._ontology_metadata?.evolution_narrative || '').trim()
      const summary = String(this.diagnosis.summary || '').trim()
      return !!(evo && evo !== summary)
    },
    diagnosisSummaryLayers() {
      return this.explanationLayers(this.diagnosis.summary)
    },
    evolutionLayers() {
      return this.explanationLayers(this.ontology.evolution_narrative || this.report?._ontology_metadata?.evolution_narrative || '')
    },
    ontologyMeta() {
      const o = this.ontology || {}
      const meta = this.activeResult?.sample_meta || {}
      const sessionCount = this.activeResult?.session_count || 0
      return {
        fallbackUsed: !!o.fallback_used,
        nonEmpty: !!o.non_empty_guaranteed,
        grade: meta.grade || o.grade || '',
        stage: meta.stage || o.stage || '',
        sessionCount,
      }
    },
    diagnosisMetaItems() {
      const items = []
      if (this.ontologyMeta.grade) items.push({ text: `${this.ontologyMeta.grade}年级` })
      if (this.ontologyMeta.stage) items.push({ text: this.stageDisplayLabel(this.ontologyMeta.stage) })
      if (this.ontologyMeta.sessionCount) items.push({ text: `${this.ontologyMeta.sessionCount}次练习` })
      if (this.ontologyMeta.fallbackUsed) items.push({ text: '含规则兜底建议', warn: true })
      const effect = this.manifest?.result_cards?.skill_effect || {}
      if (effect.level) items.push({ text: `方法作用${effect.level}` })
      else if (effect.source) items.push({ text: '方法作用档未写出', warn: true })
      return items
    },
    masteryTrajectory() {
      const o = this.ontology || {}
      return Array.isArray(o.mastery_trajectory) ? o.mastery_trajectory : []
    },
    subjectLabel() {
      return this.activeResult?.homework_grading?.subject_label || this.manifest.subject_label || '作业'
    },
    homeworkSubject() {
      const code = (
        this.activeResult?.homework_grading?.subject
        || this.manifest?.subject
        || 'chinese'
      ).toString().toLowerCase()
      if (['math', 'chinese', 'english'].includes(code)) return code
      return 'chinese'
    },
    fileTitle() {
      return (this.manifest.selected_files || [])[0] || '作业PDF'
    },
    progressPercent() {
      if (this.rerunLoading && !(this.runningTask && !this.runningTask.completed)) return 12
      if (!this.runningTask || !this.runningTask.total) return 8
      return Math.max(8, Math.min(100, Math.round((this.runningTask.item / this.runningTask.total) * 100)))
    },
    displayProgressSection() {
      if (this.rerunLoading && !(this.runningTask && !this.runningTask.completed)) {
        return '正在精选并交叉理解本子 Skill（请稍候）…'
      }
      return this.formatProgressSection(this.runningTask?.section || '')
    },
    sessionTrends() {
      return Array.isArray(this.activeResult?.session_trends) ? this.activeResult.session_trends : []
    },
    curriculumDomains() {
      const cm = this.activeResult?.curriculum_mastery || {}
      return Array.isArray(cm.by_domain) ? cm.by_domain : []
    },
    hasCurriculum() {
      return this.curriculumDomains.length > 0
    },
  },
  mounted() {
    window.addEventListener('resize', this.syncImageMetrics)
    window.addEventListener('resize', this.resizeTrendChart)
    window.addEventListener('keydown', this.handlePageKeydown)
    if (!this.pageViewOnly && !this.verifyAssist) {
      this.$nextTick(() => this.renderTrendChart())
    }
  },
  beforeUnmount() {
    window.removeEventListener('resize', this.syncImageMetrics)
    window.removeEventListener('resize', this.resizeTrendChart)
    window.removeEventListener('keydown', this.handlePageKeydown)
    this.stopVerifyAssistResize()
    if (this._tooltipHideTimer) {
      clearTimeout(this._tooltipHideTimer)
      this._tooltipHideTimer = null
    }
    if (this.trendResizeObserver) {
      this.trendResizeObserver.disconnect()
      this.trendResizeObserver = null
    }
    if (this.trendChart) {
      this.trendChart.dispose()
      this.trendChart = null
    }
    this._prefetchCache = null
  },
  watch: {
    activeAnalysisId() { this.closeRerunConfirm() },
    activeRunId() { this.closeRerunConfirm() },
    skillWorkspace() { this.closeRerunConfirm() },
    verifyAssist(val) {
      if (val) {
        this.verifyAssistCollapsed = false
        // 左右尽量加宽，中间只预留提交弹窗；左边略窄一点更舒服
        const side = this.defaultVerifyAssistSideWidth()
        this.verifyAssistRightWidth = side
        this.verifyAssistLeftWidth = Math.max(320, Math.round(side * 0.88))
      } else {
        this.verifyAssistCollapsed = false
        this.stopVerifyAssistResize()
      }
    },
    sessionTrends() {
      if (this.pageViewOnly || this.verifyAssist || this.pageDialogVisible) return
      this.$nextTick(() => this.renderTrendChart())
    },
    pageViewOnly(val) {
      if (!val && !this.verifyAssist) this.$nextTick(() => this.renderTrendChart())
    },
    pages: {
      immediate: true,
      handler(list) {
        if (!Array.isArray(list) || !list.length) return
        // 结果就绪后预热首页三种视图预览，缩短点工具栏按钮的首开等待
        this.$nextTick(() => this.prefetchPageAssets(0, ['layout', 'understanding', 'grading']))
      },
    },
    assetCacheBust() {
      // 迭代回写后：清预取、换 img key/src（URL 带 &_=），强制浏览器拉新预览
      this._prefetchCache = new Set()
      this.pageImageLoadToken += 1
      this.$nextTick(() => {
        this.beginPageImageLoad()
        this.prefetchPageAssets(this.activePageIndex, ['layout', 'understanding', 'grading'])
      })
    },
  },
  methods: {
    evidenceSlice(zoneKey, entryIdx, evidence) {
      return this.isEvidenceExpanded(zoneKey, entryIdx) ? evidence : evidence.slice(0, 4)
    },
    isEvidenceExpanded(zoneKey, entryIdx) {
      return !!this.evidenceExpanded[`${zoneKey}-${entryIdx}`]
    },
    toggleEvidenceExpanded(zoneKey, entryIdx) {
      const key = `${zoneKey}-${entryIdx}`
      this.evidenceExpanded[key] = !this.evidenceExpanded[key]
    },
    jumpToEvidence(ev) {
      const idx = resolveHomeworkEvidencePage(ev, this.pages)
      if (idx < 0) {
        ElMessage.warning('该证据无法唯一定位，请从逐页批改中核对原题。')
        return
      }
      this.openPageAt(idx, this.pageViewMode || 'grading')
      const raw = String(ev || '').trim()
      const matched = raw.match(/^p(\d+):(.+)$/i)
      const qid = matched ? matched[2] : raw
      const page = this.pages[idx]
      const question = (page?.questions || []).find(q => String(q.id) === String(qid))
      this.verifyFocusQid = question ? String(question.id) : ''
      this.verifyFocusTagVisible = true
      if (question) {
        this.$nextTick(() => {
          this.hoveredQuestion = question
          this.tooltipPinned = true
          this.tooltipExpanded = true
          this.syncRawImageMetrics()
        })
      }
    },
    trendBadgeText(trend) {
      const map = { improving: '向好', worsening: '需关注', stable: '较稳定' }
      return map[trend] || this.safeInternalLabel(trend, '趋势待确认')
    },
    stabilityLabel(stability) {
      const map = { persistent: '持续性', transient: '阶段性' }
      return map[stability] || this.safeInternalLabel(stability, '')
    },
    stageDisplayLabel(stage) {
      const map = {
        1: '第一学段（1-2年级）',
        2: '第二学段（3-4年级）',
        3: '第三学段（5-6年级）',
      }
      const key = Number(stage)
      return map[key] || `第${stage}学段`
    },
    evidenceLabel(ev) {
      const raw = String(ev || '').trim()
      const matched = raw.match(/^p(\d+):(.+)$/i)
      if (matched) return `第${matched[1]}页 · ${matched[2]}题`
      return raw || '相关题目'
    },
    /** 预览图缓存戳：迭代戳 / 盘上标注图 mtime / 核验回写时间，避免 Ctrl+F5 后仍吃旧 jpg */
    assetBustKey(options = {}) {
      if (options.bust) return String(options.bust)
      if (this.assetCacheBust) return String(this.assetCacheBust)
      const assetsVersion = this.activeResult?.assets_version
        || this.activePage?.asset_mtime
      if (assetsVersion) return String(assetsVersion)
      const verifyAt = this.report?.verify_loop?.updated_at
        || this.activeResult?.report?.verify_loop?.updated_at
        || this.report?.user_verification?.updated_at
        || ''
      if (verifyAt) return String(verifyAt)
      const mtimeHint = this.activeResult?.manifest?.updated_at
        || this.manifest?.updated_at
        || ''
      return mtimeHint ? String(mtimeHint) : ''
    },
    assetUrl(path, options = {}) {
      if (!path) return ''
      const username = this.manifest.username || localStorage.getItem('userId') || ''
      const analysisId = this.activeAnalysisId || this.activeResult?.analysis_id || ''
      const runId = (this.activeRunId || this.activeResult?.run_id || 'current').trim()
      let url = `${API_BASE_URL}/api/ci/layout_visual?path=${encodeURIComponent(path.replace(/\\/g, '/'))}&username=${encodeURIComponent(username)}&analysis_id=${encodeURIComponent(analysisId)}`
      if (runId && runId !== 'current') {
        url += `&run_id=${encodeURIComponent(runId)}`
      }
      if (options.preview) {
        const w = Number(options.width || this.pagePreviewWidth) || 1600
        url += `&w=${encodeURIComponent(w)}`
      }
      const bust = this.assetBustKey(options)
      if (bust) {
        url += `&_=${encodeURIComponent(bust)}`
      }
      return url
    },
    rightImagePathForPage(page, mode = this.pageViewMode) {
      const p = page || {}
      if (mode === 'layout') return p.annotated_layout_image_path || p.clean_image_path || ''
      if (mode === 'understanding') return p.annotated_understanding_image_path || p.clean_image_path || ''
      return p.annotated_image_path || p.clean_image_path || ''
    },
    prefetchPageAssets(centerIndex = this.activePageIndex, modes = null) {
      if (!this.pages.length) return
      if (!this._prefetchCache) this._prefetchCache = new Set()
      const indices = [centerIndex - 1, centerIndex, centerIndex + 1]
        .filter((i, pos, arr) => i >= 0 && i < this.pages.length && arr.indexOf(i) === pos)
      const modeList = Array.isArray(modes) && modes.length
        ? modes
        : [this.pageViewMode]
      for (const i of indices) {
        const page = this.pages[i] || {}
        const paths = [page.raw_image_path]
        for (const mode of modeList) {
          paths.push(this.rightImagePathForPage(page, mode))
        }
        for (const path of [...new Set(paths.filter(Boolean))]) {
          const url = this.assetUrl(path, { preview: true })
          if (!url || this._prefetchCache.has(url)) continue
          this._prefetchCache.add(url)
          const img = new Image()
          img.decoding = 'async'
          img.src = url
        }
      }
    },
    beginPageImageLoad() {
      const token = ++this.pageImageLoadToken
      const pending = {
        raw: Boolean(this.activePage?.raw_image_path),
        annotated: Boolean(this.activeRightImagePath),
      }
      this.pageImagePending = pending
      this.pageImageLoading = pending.raw || pending.annotated
      // 已缓存时可能同步触发 load，下一帧再核对一次
      this.$nextTick(() => {
        if (token !== this.pageImageLoadToken) return
        this.syncImageMetrics()
        this.prefetchPageAssets(this.activePageIndex)
      })
    },
    defaultVerifyAssistSideWidth() {
      // 中间约留出提交弹窗 + 间距，其余左右平分
      const centerReserve = 460
      const gap = 28
      const avail = Math.max(640, window.innerWidth - centerReserve - gap)
      const side = Math.floor(avail / 2)
      return Math.max(360, Math.min(720, side))
    },
    verifyAssistSideMaxWidth() {
      const centerReserve = 420
      const gap = 24
      return Math.max(360, Math.min(760, Math.floor((window.innerWidth - centerReserve - gap) / 2)))
    },
    startVerifyAssistResize(event, side = 'left') {
      if (!this.verifyAssist || this.verifyAssistCollapsed) return
      this.stopVerifyAssistResize()
      const startX = event.clientX
      const startW = side === 'right' ? this.verifyAssistRightWidth : this.verifyAssistLeftWidth
      const max = this.verifyAssistSideMaxWidth()
      const onMove = (e) => {
        const delta = e.clientX - startX
        // 左边栏：向右拖变宽；右边栏：向左拖变宽
        const next = side === 'right'
          ? Math.round(startW - delta)
          : Math.round(startW + delta)
        const width = Math.max(280, Math.min(max, next))
        if (side === 'right') this.verifyAssistRightWidth = width
        else this.verifyAssistLeftWidth = width
        this.syncImageMetrics()
        this.syncRawImageMetrics()
      }
      const onUp = () => this.stopVerifyAssistResize()
      this._vaResize = { onMove, onUp }
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    },
    stopVerifyAssistResize() {
      if (!this._vaResize) return
      window.removeEventListener('mousemove', this._vaResize.onMove)
      window.removeEventListener('mouseup', this._vaResize.onUp)
      this._vaResize = null
    },
    onPageImageLoad(kind) {
      if (kind !== 'raw' && kind !== 'annotated') return
      // 忽略上一页迟到的 load，避免误清当前页 loading
      if (!this.pageImagePending[kind]) return
      this.pageImagePending = {
        ...this.pageImagePending,
        [kind]: false,
      }
      if (!this.pageImagePending.raw && !this.pageImagePending.annotated) {
        this.pageImageLoading = false
      }
    },
    onAnnotatedImageLoad() {
      this.onPageImageLoad('annotated')
      this.syncImageMetrics()
    },
    onRawImageLoad() {
      this.onPageImageLoad('raw')
      this.syncRawImageMetrics()
    },
    syncRawImageMetrics() {
      const wrap = this.$refs.rawImageWrap
      const img = this.$refs.rawImageRef
      if (!wrap || !img) return
      const wrapRect = wrap.getBoundingClientRect()
      const imgRect = img.getBoundingClientRect()
      if (!imgRect.width || !imgRect.height) return
      this.rawImageMetrics = {
        left: imgRect.left - wrapRect.left,
        top: imgRect.top - wrapRect.top,
        width: imgRect.width,
        height: imgRect.height,
      }
    },
    versionOptionLabel(ver) {
      const label = ver?.label || ver?.run_id || '版本'
      const context = ver?.feedback_context
      const material = context ? ` · ${context.grade_label || '未知年级'} ${context.subject_name || '未知课程'}` : ' · 未保存材料依据'
      const timeText = this.formatVersionTime(ver?.created_at)
      const keyMark = ver?.is_key_version ? '★ ' : ''
      const delivery = ver?.completion?.status
      const deliveryText = delivery === 'incomplete' ? ' · 尚有未完成项' : delivery === 'unverified' ? ' · 未记录完整性核验' : ''
      const scoreText = ver?.red_blue_status === 'ready' && Number.isFinite(Number(ver?.red_blue_score))
        ? ` · 卡标 ${Number(ver.red_blue_score).toFixed(1)}`
        : ''
      return timeText ? `${keyMark}${label} · ${timeText}${scoreText}${material}${deliveryText}` : `${keyMark}${label}${scoreText}${material}${deliveryText}`
    },
    formatVersionTime(value) {
      const text = String(value || '').trim()
      if (!text) return ''
      const date = new Date(text)
      if (Number.isNaN(date.getTime())) {
        const matched = text.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})/)
        if (matched) {
          return `${matched[1]}-${matched[2]}-${matched[3]} ${matched[4]}:${matched[5]}`
        }
        return text
      }
      const pad = n => String(n).padStart(2, '0')
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
    },
    onVersionChange(event) {
      const runId = event?.target?.value || 'current'
      if (runId === (this.activeRunId || 'current')) return
      this.$emit('switch-version', runId)
    },
    toggleKeyVersion() {
      if (!this.canToggleKeyVersion || !this.activeVersion) return
      this.$emit('toggle-key-version', {
        runId: this.activeVersion.run_id,
        isKey: !this.activeVersion.is_key_version,
      })
    },
    pinResultCards() {
      if (this.pinLoading || (this.runningTask && !this.runningTask.completed) || this.activeRunId !== 'current') return
      const analysisId = (this.activeAnalysisId || this.activeResult?.analysis_id || '').trim()
      const username = this.skillWorkspace
      if (!analysisId || !username) {
        this.$message.warning('无法确定当前批改，稍后再试')
        return
      }
      // 进度条由 mainPage 托管，关闭本面板后仍可见
      this.$emit('start-pin-result-cards', { username, analysisId })
    },
    confirmRerun() {
      if (this.rerunLoading || (this.runningTask && !this.runningTask.completed) || !this.canOpenRerunDialog) return
      this.selectedRerunStage = this.needsFullRecompute
        ? 'all'
        : (['layout', 'understanding', 'grading'].includes(this.pageViewMode) ? this.pageViewMode : 'grading')
      this.selectedRerunSessionIds = this.needsFullRecompute
        ? []
        : this.rerunSessions.map(item => item.session_id).filter(Boolean)
      this.selectedPreprocessMode = this.currentPreprocessMode
      this.refreshConfiguration = false
      this.replaceNotebookSkills = false
      this.notebookSkillSelection = { enabled: false, names: [] }
      this.notebookSkillValid = true
      this.useRedBlueFeedback = this.redBlueReady
      this.rerunSectionsExpanded = {
        preprocess: false,
        sessions: false,
        redBlue: false,
      }
      this.rerunConfirmVisible = true
    },
    closeRerunConfirm() {
      this.rerunConfirmVisible = false
    },
    async submitRerun() {
      const analysisId = (this.activeAnalysisId || this.activeResult?.analysis_id || '').trim()
      if (!analysisId) return
      const files = Array.isArray(this.activeResult?.manifest?.selected_files)
        ? [...this.activeResult.manifest.selected_files]
        : []
      if (this.replaceNotebookSkills && !this.notebookSkillValid) return
      const fullRecompute = this.needsFullRecompute || this.replaceNotebookSkills
      const rerunStage = fullRecompute
        ? 'all'
        : (['all', 'layout', 'understanding', 'grading'].includes(this.selectedRerunStage)
          ? this.selectedRerunStage
          : 'grading')
      const sessionIds = this.selectedRerunSessionIds.filter(Boolean)
      const modeChanged = this.preprocessModeChanged
      if (!fullRecompute && !modeChanged && !this.refreshConfiguration && this.rerunSessions.length && !sessionIds.length) return
      if ((fullRecompute || modeChanged) && rerunStage !== 'all') return

      // 只有显式采用当前配置或旧快照不可恢复时才读取当前材料设置；普通完整迭代继续沿用原快照。
      let material = null
      if (this.refreshConfiguration || this.needsFullRecompute) {
        const filename = String(files[0] || this.activeResult?.manifest?.selected_files?.[0] || '').trim()
        const username = this.skillWorkspace
        if (filename && username) {
          try {
            const settings = await feedbackMaterialSettings({ username, files: [filename] })
            if (settings?.error_num !== 0) throw new Error(settings?.msg || '材料设置读取失败')
            if (settings.material_saved && settings.material) {
              material = settings.material
            }
          } catch (error) {
            console.warn('[HomeworkGradingPanel] load material settings for rerun failed:', error)
            this.$message.error(error?.message || '材料设置读取失败，本次未启动')
            return
          }
        }
      }

      this.rerunConfirmVisible = false
      this.$emit('rerun', {
        analysisId,
        files,
        rerunStage,
        preprocessMode: this.selectedPreprocessMode,
        useRedBlueFeedback: Boolean(this.useRedBlueFeedback && this.redBlueReady),
        ...(fullRecompute ? { fullRecompute: true } : {}),
        ...(this.replaceNotebookSkills ? { notebookSkillSelection: {
          enabled: this.notebookSkillSelection.enabled, names: [...this.notebookSkillSelection.names],
        } } : {}),
        ...(this.refreshConfiguration ? { refreshConfiguration: true } : {}),
        ...(material ? { material } : {}),
        // 仅当本次带入材料设置（依据可能变化）时不传篇目；其余情况保持原样传篇目
        ...(!fullRecompute && !modeChanged && !material && sessionIds.length ? { sessionIds } : {}),
      })
    },
    onNotebookSkillsChange() {
      if (this.replaceNotebookSkills) {
        this.selectedRerunStage = 'all'
        this.selectedRerunSessionIds = []
      }
    },
    onPreprocessModeChange() {
      if (this.preprocessModeChanged) {
        this.selectedRerunStage = 'all'
        this.rerunSectionsExpanded.preprocess = true
      }
    },
    onRefreshConfigurationChange() {
      if (this.refreshConfiguration) {
        this.selectedRerunStage = 'all'
        this.selectedRerunSessionIds = []
        this.rerunSectionsExpanded.sessions = false
      }
    },
    selectAllRerunSessions() {
      this.selectedRerunSessionIds = this.rerunSessions.map(item => item.session_id).filter(Boolean)
    },
    clearRerunSessions() {
      this.selectedRerunSessionIds = []
    },
    rerunSessionLabel(item) {
      const title = this.cleanText(item?.session_title || '') || '篇目'
      const start = Number(item?.page_start)
      const end = Number(item?.page_end)
      if (Number.isFinite(start) && Number.isFinite(end) && start > 0 && end >= start) {
        return `${title}（${start === end ? `第${start}页` : `第${start}-${end}页`}）`
      }
      return title
    },
    resumeSessionRerun() {
      if (!this.canResumeSessionRerun || this.rerunLoading || (this.runningTask && !this.runningTask.completed)) return
      const analysisId = (this.activeAnalysisId || this.activeResult?.analysis_id || '').trim()
      if (!analysisId) return
      const files = Array.isArray(this.activeResult?.manifest?.selected_files)
        ? [...this.activeResult.manifest.selected_files]
        : []
      const rerunStage = this.activeResult?.available_actions?.resume?.rerun_stage || this.sessionRerunState.rerun_stage
      if (!['all', 'layout', 'understanding', 'grading'].includes(rerunStage)) return
      this.$emit('rerun', { analysisId, files, rerunStage, resume: true })
    },
    priorityLabel(priority) {
      const labels = { high: '高优先级', medium: '中优先级', low: '低优先级' }
      return labels[priority] || '中优先级'
    },
    suggestionStageLabel(stage) {
      const labels = {
        layout: '无损版面',
        understanding: '识别与理解',
        grading: '诊断与批语',
        all: '全流程',
      }
      return labels[stage] || '全流程'
    },
    cleanText(value) {
      const text = String(value || '').replace(/\s+/g, ' ').trim()
      const invalid = [
        '信息不足，建议人工确认',
        '信息不足，建议人工确认。',
        '信息不足，建议人工复核',
        '信息不足，建议人工复核。',
        '信息不足',
        '建议人工确认',
        '建议人工复核',
        'null',
        'None',
        '无',
      ]
      return invalid.includes(text) ? '' : text
    },
    cleanEvidenceId(value) {
      return String(value || '').replace(/\s+/g, '').trim()
    },
    localizeInternalTerms(value) {
      let text = this.cleanText(value)
      if (!text) return ''
      Object.entries(HOMEWORK_INTERNAL_TERM_LABELS)
        .sort(([left], [right]) => right.length - left.length)
        .forEach(([key, label]) => {
          const escaped = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
          const pattern = new RegExp(`(^|[^A-Za-z0-9_])${escaped}(?=$|[^A-Za-z0-9_])`, 'gi')
          text = text.replace(pattern, (_match, prefix) => `${prefix}${label}`)
        })
      return text.replace(/\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b/g, '内部信息')
    },
    explanationLayers(value) {
      const raw = this.displayText(value)
      if (!raw || (!raw.includes('【看到了什么】') && !raw.includes('【这说明什么】') && !raw.includes('【下一步做什么】'))) {
        return []
      }
      const re = /【(看到了什么|这说明什么|下一步做什么)】\s*/g
      const found = []
      let match
      while ((match = re.exec(raw))) {
        found.push({ key: match[1], start: match.index, end: match.index + match[0].length })
      }
      return found.map((item, index) => {
        const stop = index + 1 < found.length ? found[index + 1].start : raw.length
        return { key: item.key, text: raw.slice(item.end, stop).trim() }
      }).filter(item => item.text)
    },
    meanLeftover(text) {
      const raw = String(text || '')
      const re = /【(?!看到了什么|这说明什么|下一步做什么)([^】]{1,12})】\s*/g
      const found = []
      let match
      while ((match = re.exec(raw))) {
        found.push({ start: match.index, end: match.index + match[0].length })
      }
      if (!found.length) return ''
      let leftover = ''
      let last = 0
      found.slice(0, 5).forEach((item, index) => {
        leftover += raw.slice(last, item.start)
        last = index + 1 < found.length ? found[index + 1].start : raw.length
      })
      leftover += raw.slice(last)
      return leftover.replace(/\s+/g, ' ').replace(/^[ ；,，、。.\n]+|[ ；,，、。.\n]+$/g, '').trim()
    },
    meanTagParts(text) {
      const raw = String(text || '')
      const re = /【(?!看到了什么|这说明什么|下一步做什么)([^】]{1,12})】\s*/g
      const found = []
      let match
      while ((match = re.exec(raw))) {
        found.push({ name: match[1].trim(), start: match.index, end: match.index + match[0].length })
      }
      return found.slice(0, 5).map((item, index) => {
        const stop = index + 1 < found.length ? found[index + 1].start : raw.length
        return { name: item.name, value: raw.slice(item.end, stop).trim().slice(0, 24) }
      }).filter(item => item.name)
    },
    displayText(value) {
      let text = this.localizeInternalTerms(value)
      if (!text) return ''
      text = text.replace(/p(\d+):\\?\s*([0-9A-Za-z][0-9A-Za-z_.-]*(?:[（(][0-9A-Za-z_.-]+[）)])?)/gi, (_m, page, qid) => {
        let suffix = ''
        let questionId = qid
        if (/[)）]$/.test(questionId) && !/[（(]/.test(questionId)) {
          suffix = questionId.slice(-1)
          questionId = questionId.slice(0, -1)
        }
        return `第${Number(page)}页第${questionId}题${suffix}`
      })
      text = text.replace(/p(\d+):\\?(?=[、，,）)\s]|$)/gi, (_m, page) => `第${Number(page)}页相关题目`)
      text = text.replace(/\bsession\s*(\d+)\s*[-~—–至、,]\s*(\d+)/gi, '第$1至$2次练习')
      text = text.replace(/\bsession\s*(\d+)/gi, '第$1次练习')
      text = text.replace(/\bsessions?\b/gi, '练习阶段')
      text = text.replace(/\bL4\b/gi, '规则复核')
      text = text.replace(/\bL5\b/gi, '学科诊断')
      if (/第\d+页第[^，。；、\s]+题/.test(text)) {
        text = text.replace(/第\d+(?:至\d+)?次练习(?:中|里|时|的)?/g, '')
        text = text.replace(/第\d+(?:至\d+)?次(?:中|里|时|的)?/g, '')
        text = text.replace(/^[，、；\s]+/, '')
        text = text.replace(/([（(])\s*[，、；]\s*/g, '$1')
      }
      const replacements = [
        [/word_problem/gi, '应用题'],
        [/operation_law/gi, '运算律'],
        [/friction_zone/gi, '内耗区'],
        [/blind_spot/gi, '盲区'],
        [/\bZPD\b/gi, '最近发展区'],
        [/transient/gi, '阶段性'],
        [/persistent/gi, '持续性'],
        [/improving/gi, '有进步'],
        [/worsening/gi, '需关注'],
        [/\bstable\b/gi, '较稳定'],
        [/acquired/gi, '基本掌握'],
        [/consolidating/gi, '正在巩固'],
        [/struggling/gi, '困难较多'],
      ]
      replacements.forEach(([pattern, label]) => {
        text = text.replace(pattern, label)
      })
      text = text.replace(/([\u4e00-\u9fff0-9）)])\s+(?=[\u4e00-\u9fff])/g, '$1')
      text = text.replace(/\s+([。；，、）])/g, '$1')
      return text
    },
    displayPracticeText(value) {
      let text = this.displayText(value)
      if (!text) return ''
      text = text.replace(/第(\d+)\s*(?:至|到|[-~—–])\s*(\d+)次练习/g, '第$1-$2次练习')
      text = text.replace(/第(\d+)\s*(?:至|到|[-~—–])\s*(\d+)次(?!练习)/g, '第$1-$2次练习')
      text = text.replace(/第(\d+)次(?!练习)/g, '第$1次练习')
      return text
    },
    cleanList(value) {
      if (Array.isArray(value)) return value.map(item => this.displayText(item)).filter(Boolean)
      const text = this.displayText(value)
      return text ? [text] : []
    },
    formatProgressSection(value) {
      let text = this.cleanText(value) || '处理中'
      text = text.replace(/Session\s*(\d+)\/(\d+)[（(][^，),]*[，,]\s*(\d+)页[，,]\s*前序有[）)]/i, '正在批改第$1/$2篇（$3页，已参考前面错题）')
      text = text.replace(/Session\s*(\d+)\/(\d+)[（(][^，),]*[，,]\s*(\d+)页[，,]\s*前序无[）)]/i, '正在批改第$1/$2篇（$3页）')
      text = text.replace(/逐页批改\s*Session\s*(\d+)\/(\d+)[（(]刚完成第(\d+)页[）)]/i, '已完成第$3页，继续第$1/$2篇')
      text = text.replace(/Session\s*预切分（双通道）/i, '识别作业篇目结构')
      text = text.replace(/逐页批改准备中（\d+并行）/g, '准备逐页批改')
      text = text.replace(/未归\s*session\s*第(\d+)页/ig, '第$1页')
      text = text.replace(/\bsession\b/ig, '篇目')
      text = text.replace(/构建数字孪生体（?L5）?/g, '生成整篇学习诊断')
      text = text.replace(/生成三区诊断（消费 ontology）/ig, '整理问题与提升建议')
      text = text.replace(/幻觉过滤校验（三件套回写）/g, '复核批改结果')
      text = text.replace(/学科约束校验（L4验算）/g, '复核学科规则')
      text = text.replace(/汇总错题记忆与规则基线/g, '汇总错题线索')
      text = text.replace(/ontology/ig, '诊断结果')
      text = text.replace(/\bL[45]\b/g, '')
      text = text.replace(/\s+/g, ' ').trim()
      return text || '处理中'
    },
    openPageAt(index = 0, mode = 'grading') {
      if (!this.pages.length) return
      this.pageViewMode = mode || 'grading'
      this.activePageIndex = Math.max(0, Math.min(index, this.pages.length - 1))
      this.hoveredQuestion = null
      this.tooltipPointer = null
      this.tooltipExpanded = false
      this.tooltipPinned = false
      if (this._tooltipHideTimer) {
        clearTimeout(this._tooltipHideTimer)
        this._tooltipHideTimer = null
      }
      this.imageMetrics = { left: 0, top: 0, width: 0, height: 0 }
      this.pageDialogVisible = true
      this.beginPageImageLoad()
    },
    openPageViewAt(index = 0, mode = 'grading') {
      this.openPageAt(index, mode)
    },
    closePageDialog() {
      this.pageDialogVisible = false
      this.pageViewMode = 'grading'
      this.hoveredQuestion = null
      this.verifyFocusQid = ''
      this.rawImageMetrics = { left: 0, top: 0, width: 0, height: 0 }
      this.tooltipPointer = null
      this.tooltipExpanded = false
      this.tooltipPinned = false
      this.verifyAssistCollapsed = false
      this.stopVerifyAssistResize()
      if (this._tooltipHideTimer) {
        clearTimeout(this._tooltipHideTimer)
        this._tooltipHideTimer = null
      }
      this.imageMetrics = { left: 0, top: 0, width: 0, height: 0 }
      if (this.verifyAssist) {
        this.$emit('close-verify-assist')
        return
      }
      if (this.pageViewOnly) {
        this.$emit('close')
      }
    },
    goPrevPage() {
      if (!this.canPrevPage) return
      this.openPageAt(this.activePageIndex - 1, this.pageViewMode)
    },
    goNextPage() {
      if (!this.canNextPage) return
      this.openPageAt(this.activePageIndex + 1, this.pageViewMode)
    },
    handlePageKeydown(event) {
      if (!this.pageDialogVisible) return
      if (event.key === 'ArrowLeft') this.goPrevPage()
      if (event.key === 'ArrowRight') this.goNextPage()
    },
    syncImageMetrics() {
      const stage = this.$refs.stageRef
      const img = this.$refs.annotatedImageRef
      if (!stage || !img) return
      const stageRect = stage.getBoundingClientRect()
      const imgRect = img.getBoundingClientRect()
      this.imageMetrics = {
        left: imgRect.left - stageRect.left,
        top: imgRect.top - stageRect.top,
        width: imgRect.width,
        height: imgRect.height,
      }
    },
    questionBoxStyle(question) {
      const bbox = question.bbox || this.positionToBbox(question.position)
      const m = this.imageMetrics
      const base = {
        left: `${m.left + Number(bbox.x || 0) * m.width}px`,
        top: `${m.top + Number(bbox.y || 0) * m.height}px`,
        width: `${Math.max(8, Number(bbox.w || 0) * m.width)}px`,
        height: `${Math.max(8, Number(bbox.h || 0) * m.height)}px`,
      }
      // 有烘焙标注图时，对错/白灰黑都画在底图上，叠层只负责热区，不再另铺色
      if (this.useBakedOverlay) {
        return base
      }
      if (this.pageViewMode === 'layout' || this.pageViewMode === 'understanding') {
        const confidence = this.pageViewMode === 'layout'
          ? question.layout_confidence
          : this.combinedRecognitionUnderstandingConfidence(question)
        return { ...base, ...this.confidenceBoxColors(confidence, this.pageViewMode) }
      }
      return base
    },
    questionBoxClasses(question) {
      const classes = []
      if (this.useBakedOverlay) {
        classes.push('is-baked')
      } else if (this.pageViewMode === 'layout' || this.pageViewMode === 'understanding') {
        classes.push('is-confidence')
      } else {
        classes.push(`is-${question.verdict || 'uncertain'}`, question.importance === 'HIGH' ? 'is-high' : '')
      }
      return classes
    },
    combinedRecognitionUnderstandingConfidence(question) {
      const rec = Number(question.recognition_confidence)
      const und = Number(question.understanding_confidence)
      if (!Number.isFinite(rec) && !Number.isFinite(und)) return null
      if (!Number.isFinite(rec)) return und
      if (!Number.isFinite(und)) return rec
      return Math.round((rec + und) / 2)
    },
    confidenceThresholdsForMode(mode) {
      const bySubject = this.confidenceThresholdsBySubject[this.homeworkSubject]
        || this.confidenceThresholdsBySubject.chinese
      return bySubject[mode] || bySubject.grading
    },
    grayT(value, th) {
      const span = Math.max(th.white - th.black - 1, 1)
      return Math.max(0, Math.min(1, (value - th.black) / span))
    },
    grayShade(value, mode) {
      const th = this.confidenceThresholdsForMode(mode)
      const n = Number(value)
      if (!Number.isFinite(n)) return 'gray_mid'
      if (n >= th.white || n < th.black) return 'gray_mid'
      const t = this.grayT(n, th)
      if (t < 1 / 3) return 'gray_deep'
      if (t < 2 / 3) return 'gray_mid'
      return 'gray_light'
    },
    grayBoxRgb(value, mode) {
      const shade = this.grayShade(value, mode)
      return this.grayRgbByShade.box[shade] || 128
    },
    grayDotRgb(value) {
      const shade = this.grayShade(value, 'grading')
      return this.grayRgbByShade.dot[shade] || 148
    },
    confidenceZone(value, mode) {
      const m = mode || this.confidenceMode
      const th = this.confidenceThresholdsForMode(m)
      const n = Number(value)
      if (!Number.isFinite(n)) return 'gray'
      if (n >= th.white) return 'white'
      if (n < th.black) return 'black'
      return 'gray'
    },
    confidenceZoneLabel(zone) {
      const labels = { white: '白区', gray: '灰区', black: '黑区' }
      return labels[zone] || '灰区'
    },
    confidenceZoneRow(question) {
      let value = null
      if (this.pageViewMode === 'layout') {
        value = question.layout_confidence
      } else if (this.pageViewMode === 'understanding') {
        value = this.combinedRecognitionUnderstandingConfidence(question)
      } else {
        value = question.grading_confidence
      }
      const n = Number(value)
      if (!Number.isFinite(n)) {
        return { label: '置信度分区', value: '灰区（无置信度）' }
      }
      const zone = this.confidenceZone(n, this.confidenceMode)
      return { label: '置信度分区', value: `${this.confidenceZoneLabel(zone)}（${n}）` }
    },
    confidenceBoxColors(confidence, mode) {
      const m = mode || this.confidenceMode
      const value = Number(confidence)
      if (!Number.isFinite(value)) {
        return {
          borderColor: 'rgba(120, 120, 120, 0.65)',
          backgroundColor: 'rgba(120, 120, 120, 0.14)',
        }
      }
      const zone = this.confidenceZone(value, m)
      if (zone === 'white') {
        return {
          borderColor: 'rgba(52, 142, 76, 0.62)',
          backgroundColor: 'rgba(52, 142, 76, 0.14)',
        }
      }
      if (zone === 'black') {
        return {
          borderColor: 'rgba(45, 45, 55, 0.82)',
          backgroundColor: 'rgba(45, 45, 55, 0.28)',
        }
      }
      const gray = this.grayBoxRgb(value, m)
      return {
        borderColor: `rgba(${gray}, ${gray}, ${gray}, 0.82)`,
        backgroundColor: `rgba(${gray}, ${gray}, ${gray}, 0.20)`,
      }
    },
    gradingConfidenceDotStyle(question) {
      const mark = this.gradingMarkPx
      const gap = Math.max(6, Math.round(mark / 5))
      const size = mark * 2
      const base = {
        width: `${size}px`,
        height: `${size}px`,
        marginTop: `${-mark}px`,
        right: `${-(mark * 2 + gap + size)}px`,
      }
      const value = Number(question.grading_confidence)
      if (!Number.isFinite(value)) {
        return { ...base, backgroundColor: 'rgba(190, 190, 190, 0.92)' }
      }
      const zone = this.confidenceZone(value, 'grading')
      if (zone === 'white') {
        return {
          ...base,
          backgroundColor: 'rgba(245, 245, 245, 0.92)',
          border: '1px solid rgba(200, 200, 200, 0.7)',
        }
      }
      if (zone === 'black') {
        return { ...base, backgroundColor: 'rgba(45, 45, 55, 0.88)' }
      }
      const gray = this.grayDotRgb(value)
      return { ...base, backgroundColor: `rgba(${gray}, ${gray}, ${gray}, 0.92)` }
    },
    showQuestionTooltip(question, event) {
      if (this._tooltipHideTimer) {
        clearTimeout(this._tooltipHideTimer)
        this._tooltipHideTimer = null
      }
      if (this.hoveredQuestion !== question) {
        this.tooltipExpanded = false
      }
      this.tooltipPinned = false
      this.hoveredQuestion = question
      this.moveQuestionTooltip(event)
    },
    moveQuestionTooltip(event) {
      if (this.tooltipPinned || this.tooltipExpanded) return
      const stage = this.$refs.stageRef
      if (!stage || !event) return
      const stageRect = stage.getBoundingClientRect()
      this.tooltipPointer = {
        x: event.clientX - stageRect.left,
        y: event.clientY - stageRect.top,
      }
    },
    hideQuestionTooltip() {
      if (this.tooltipExpanded) return
      if (this._tooltipHideTimer) clearTimeout(this._tooltipHideTimer)
      this._tooltipHideTimer = setTimeout(() => {
        this._tooltipHideTimer = null
        if (this.tooltipPinned || this.tooltipExpanded) return
        this.hoveredQuestion = null
        this.tooltipPointer = null
        this.tooltipExpanded = false
      }, 120)
    },
    onTooltipEnter() {
      if (this._tooltipHideTimer) {
        clearTimeout(this._tooltipHideTimer)
        this._tooltipHideTimer = null
      }
      this.tooltipPinned = true
    },
    onTooltipLeave() {
      this.tooltipPinned = false
      if (this.tooltipExpanded) return
      if (this._tooltipHideTimer) clearTimeout(this._tooltipHideTimer)
      this._tooltipHideTimer = setTimeout(() => {
        this._tooltipHideTimer = null
        if (this.tooltipPinned || this.tooltipExpanded) return
        this.hoveredQuestion = null
        this.tooltipPointer = null
      }, 80)
    },
    tooltipNeedsExpand(question) {
      const rows = this.tooltipRows(question) || []
      let chars = 0
      for (const row of rows) {
        if (row.layers && row.layers.length) {
          for (const layer of row.layers) chars += String(layer.text || '').length
        } else {
          chars += String(row.value || '').length
        }
      }
      return chars > 180
    },
    tooltipStyle() {
      const stage = this.$refs.stageRef
      const stageW = stage ? stage.clientWidth : (this.imageMetrics.width || 800)
      const stageH = stage ? stage.clientHeight : (this.imageMetrics.height || 600)
      const pointer = this.tooltipPointer || {
        x: this.imageMetrics.left + this.imageMetrics.width / 2,
        y: this.imageMetrics.top + 24,
      }
      const tooltipWidth = this.tooltipExpanded ? Math.min(420, stageW - 16) : Math.min(360, Math.max(280, stageW * 0.42))
      const maxH = this.tooltipExpanded ? Math.min(stageH * 0.72, 480) : Math.min(stageH * 0.42, 280)
      let left = pointer.x - tooltipWidth - 12
      if (left < 8) left = Math.min(pointer.x + 16, stageW - tooltipWidth - 8)
      left = Math.max(8, Math.min(left, stageW - tooltipWidth - 8))
      let top = pointer.y - 28
      if (top + maxH > stageH - 8) top = Math.max(8, stageH - maxH - 8)
      if (top < 8) top = 8
      return {
        left: `${left}px`,
        top: `${top}px`,
        width: `${tooltipWidth}px`,
        maxHeight: `${maxH}px`,
      }
    },
    positionToBbox(position) {
      if (!Array.isArray(position) || position.length !== 4) return {}
      const [x1, y1, x2, y2] = position.map(value => Number(value || 0) / 1000)
      if (x2 <= x1 || y2 <= y1) return {}
      return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 }
    },
    questionTitle(question) {
      if (this.isOpenMaterial) {
        const contentId = question.id ? `内容 ${question.id}` : '内容'
        if (this.pageViewMode === 'layout') return `${contentId} · 版面`
        if (this.pageViewMode === 'understanding') return `${contentId} · 识别与理解`
        return `${contentId} · 内容反馈`
      }
      const id = question.id ? `题目 ${question.id}` : '题目'
      if (this.pageViewMode === 'layout') return `${id} · 版面`
      if (this.pageViewMode === 'understanding') return `${id} · 识别与理解`
      return `${id} · ${this.verdictLabel(question.verdict)}`
    },
    verdictLabel(verdict) {
      const labels = { correct: '正确', wrong: '错误', partial: '半对', unanswered: '未答', uncertain: '待确认' }
      return labels[verdict] || '待确认'
    },
    sourceLockReasonLabel(value) {
      const labels = {
        no_audio_source: '缺少音频或听力原文，系统不强判正误',
        source_locked: '题目缺少必要来源，复核不得强判正误',
      }
      return labels[value] || this.safeInternalLabel(this.localizeInternalTerms(value), '')
    },
    rubricCheckLabel(value) {
      const labels = {
        source_lock: '证据来源不足',
        answer_sentence_required: '应用题缺少完整答话',
        missing_answer_statement: '缺少最终答话',
        missing_final_answer_statement: '缺少最终答话',
        unit_required: '答案单位不完整或不匹配',
        final_form_required: '答案未满足化简或指定形式',
        term_required: '术语或运算律名称不完整',
        process_required: '缺少题目要求的过程或方法',
      }
      return labels[value] || this.safeInternalLabel(this.localizeInternalTerms(value), '')
    },
    errorTypeLabel(value) {
      const raw = this.cleanText(value)
      if (!raw) return ''
      const localized = this.localizeInternalTerms(raw)
      if (!/[\u4e00-\u9fff]/.test(raw) && /[A-Za-z]/.test(raw)) {
        const categories = [
          [/contextual mismatch/i, '语境不匹配'],
          [/grammar errors?/i, '语法错误'],
          [/pragmatic error/i, '语用错误'],
          [/spelling errors?/i, '拼写错误'],
          [/listening task dependent on audio/i, '听力题依赖音频'],
        ]
        const matched = categories.find(([pattern]) => pattern.test(raw))
        if (matched) return matched[1]
        return /[A-Za-z]{2,}/.test(localized) ? '其他错误' : localized
      }
      return this.safeInternalLabel(localized, '其他错误') || '其他错误'
    },
    selectedRerunPageNums() {
      const selected = new Set(this.selectedRerunSessionIds)
      const pages = new Set()
      this.rerunSessions.forEach(item => {
        if (!selected.has(item?.session_id)) return
        const start = Number(item?.page_start)
        const end = Number(item?.page_end)
        if (!Number.isFinite(start) || !Number.isFinite(end)) return
        for (let page = start; page <= end; page += 1) pages.add(page)
      })
      return pages
    },
    applicableRedBlueSuggestions() {
      const applicableStages = this.redBlueApplicableStages
      if (!applicableStages.length) return []
      return this.redBlueSuggestions.filter(item => {
        const stageMatched = item?.target_stage === 'all'
          || applicableStages.includes(item?.target_stage)
        if (!stageMatched) return false
        const refs = Array.isArray(item?.evidence_refs) ? item.evidence_refs : []
        if (item?.scope === 'global' || !refs.length || !this.selectedRerunPageNums.size) return true
        return refs.some(ref => {
          const matched = String(ref || '').match(/^p(\d+):/i)
          return matched && this.selectedRerunPageNums.has(Number(matched[1]))
        })
      })
    },
    spellingCorrectionComment(question) {
      const onlyCjk = value => this.cleanText(value).replace(/[^\u3400-\u9fff]/g, '')
      const studentChars = [...onlyCjk(question.student_answer)]
      const expectedChars = [...onlyCjk(question.correct_answer)]
      if (studentChars.length === expectedChars.length && studentChars.length > 0) {
        const differences = studentChars
          .map((char, index) => ({ student: char, expected: expectedChars[index] }))
          .filter(item => item.student !== item.expected)
        if (differences.length === 1) {
          const difference = differences[0]
          return `“${difference.student}”字应写作“${difference.expected}”，注意区分字形。`
        }
      }
      return '存在错别字，请对照参考答案检查字形。'
    },
    selfReviewComment(question) {
      const selfReview = question.self_review || {}
      const reason = this.cleanText(selfReview.reason)
      const internalAuditReason = /(?:真实字格|无先验|视觉仲裁|多路视觉证据|标准错字|glyph[_\s-]|single[_\s-]cell|ROI)/i
      if (reason && !internalAuditReason.test(reason)) {
        return this.displayText(reason)
      }
      if (this.cleanText(question.error_type) === '错别字') {
        return this.spellingCorrectionComment(question)
      }
      if (reason) {
        return '复核发现作答与参考答案不一致，请检查并订正。'
      }
      return ''
    },
    tooltipComment(question) {
      const feedback = question.feedback || {}
      const comment = this.displayText(feedback.comment)
      if (comment) return comment

      const sourceLock = question.source_lock || {}
      if (sourceLock.locked) {
        return this.displayText(sourceLock.reason) || this.sourceLockReasonLabel(sourceLock.reason_code)
      }

      const checks = Array.isArray(question.rubric_checks) ? question.rubric_checks : []
      const failedCheck = checks.find(check => check && check.result !== 'pass' && (check.result === 'fail' || check.evidence || check.name))
      if (failedCheck) {
        return this.displayText(failedCheck.evidence) || this.rubricCheckLabel(failedCheck.name)
      }

      const verification = question.verification_result || {}
      if (verification.detail) return this.displayText(verification.detail)

      const selfReview = question.self_review || {}
      if (selfReview.verdict_fix_blocked) {
        return this.displayText(selfReview.lock_reason) || '复核改判被规则锁阻止'
      }
      return this.selfReviewComment(question)
    },
    tooltipRows(question) {
      const markingRows = [
        { label: '印刷文字与标记', value: this.cleanText(question.printed_text_marked) },
        { label: '手写内容与笔色', value: this.cleanText(question.handwritten_text_marked) },
        { label: '标注关系', value: (Array.isArray(question.annotation_links) ? question.annotation_links : [])
          .map(link => [link.marked_text, link.annotation_text, link.relation].filter(Boolean).join('；')).join('\n') },
        { label: '标记提示', value: (Array.isArray(question.marking_warnings) ? question.marking_warnings : []).join('；') },
      ].filter(row => row.value)
      const zoneRow = this.confidenceZoneRow(question)
      if (this.pageViewMode === 'layout') {
        const crossPageText = question.cross_page
          ? [
              this.displayText(question.cross_page_note) || '跨页题目',
              question.cross_page_resolved ? '（跨页上下文已补齐）' : '',
            ].filter(Boolean).join(' ')
          : '否'
        return [
          { label: '题号', value: this.cleanText(question.id) },
          { label: '大题号', value: this.cleanText(question.parent_group_id) },
          { label: '大题', value: this.cleanText(question.parent_stem_excerpt) },
          { label: '本题', value: this.cleanText(question.stem_excerpt) },
          ...markingRows,
          { label: '跨页', value: crossPageText },
          zoneRow,
        ].filter(row => row.value)
      }
      if (this.pageViewMode === 'understanding') {
        return [
          { label: '题号', value: this.cleanText(question.id) },
          { label: '学生作答', value: this.cleanText(question.student_answer) },
          ...markingRows,
          { label: '理解', value: this.cleanText(question.understanding) },
          { label: '参考答案', value: this.cleanText(question.correct_answer) },
          zoneRow,
        ].filter(row => row.value)
      }
      const feedback = question.feedback || {}
      const comment = this.tooltipComment(question)
      const commentLayers = this.explanationLayers(comment)
      return [
        { label: '错误类型', value: this.errorTypeLabel(question.error_type) },
        { label: '知识点', value: this.kpName(this.cleanText(question.knowledge_point)) },
        { label: '重要度', value: this.importanceLabel(question.importance) },
        { label: '趋势', value: this.trendLabel(question.trend) },
        { label: '认知区域', value: this.displayText(feedback.zone_label) },
        { label: '待确认原因', value: this.uncertainReasonLabel(question.uncertain_reason) },
        { label: '批语', value: comment, layers: commentLayers },
        ...markingRows,
        { label: '理解', value: this.cleanText(question.understanding) },
        zoneRow,
      ].filter(row => row.value)
    },
    stripCurriculumCodes(value) {
      // 只去掉 EN_S2_040 这类课标码；保留 [tense_usage, 理解, 语音] 与中文说明
      const key = String(value || '').trim()
      if (!key) return ''
      const line = key.match(/^([A-Z]{2}_S\d+_\d+)(\s*\[[^\]]*\])?(?:\s+(.+))?$/)
      if (line) {
        const meta = (line[2] || '').trim()
        const desc = (line[3] || '').trim()
        const parts = [meta, desc].filter(Boolean)
        if (parts.length) return parts.join(' ')
        return ''
      }
      return key.replace(/\b[A-Z]{2}_S\d+_\d+\b/g, '').replace(/\s{2,}/g, ' ').trim()
    },
    kpName(label) {
      const key = String(label || '').trim()
      if (!key) return ''
      const localMap = {
        no_observed: '本次未观察到显著问题',
        extension_recommendation: '拓展提升建议',
        generic_extension: '拓展提升建议',
      }
      if (this.kpNameMap[key]) return this.kpNameMap[key]
      if (localMap[key]) return localMap[key]
      const stripped = this.stripCurriculumCodes(key)
      if (stripped && stripped !== key) {
        if (this.kpNameMap[stripped]) return this.kpNameMap[stripped]
        return stripped
      }
      if (/^[A-Z]{2}_S\d+_\d+$/.test(key)) {
        return this.kpNameMap[key] || '相关知识点'
      }
      return this.safeInternalLabel(key, '相关知识点')
    },
    safeInternalLabel(value, fallback) {
      const text = String(value || '').trim()
      if (!text) return ''
      if (/^[A-Z]{2}_S\d+_\d+$/.test(text)) return fallback
      if (/[A-Z]{2}_S\d+_\d+/.test(text)) {
        const stripped = this.stripCurriculumCodes(text)
        return stripped || fallback
      }
      if (/^[A-Za-z][A-Za-z0-9_/-]*$/.test(text)) return fallback
      return text
    },
    importanceLabel(value) {
      const labels = { HIGH: '高', MID: '中', LOW: '低' }
      return labels[value] || ''
    },
    trendLabel(value) {
      const labels = { improving: '进步中', worsening: '退步中', stable: '稳定', new: '新出现' }
      return labels[value] || ''
    },
    uncertainReasonLabel(value) {
      const labels = {
        cross_page_attempted: '跨页信息已尝试修补，仍建议复核',
        cross_page_unresolved: '跨页内容不足',
        single_page: '单页信息不足',
        no_audio_source: '缺少音频或听力原文',
        verifier_override: '规则复核改为待确认',
      }
      return labels[value] || this.safeInternalLabel(this.localizeInternalTerms(value), '')
    },
    sessionPageStart(trend) {
      if (trend && trend.page_start != null) return Number(trend.page_start)
      if (trend && Array.isArray(trend.page_range) && trend.page_range[0] != null) return Number(trend.page_range[0])
      return null
    },
    sessionPageEnd(trend) {
      if (trend && trend.page_end != null) return Number(trend.page_end)
      if (trend && Array.isArray(trend.page_range) && trend.page_range[1] != null) return Number(trend.page_range[1]) - 1
      return null
    },
    sessionDisplayLabel(trend) {
      return this.sessionPageLabel(trend) || (trend.session_index ? `第${trend.session_index}篇` : '篇目')
    },
    sessionTooltipLabel(trend) {
      const start = this.sessionPageStart(trend)
      const end = this.sessionPageEnd(trend)
      const title = this.cleanText(trend.session_title || trend.module_title || '')
      const index = trend.session_index || ''
      const prefix = index ? `第${index}篇` : '篇目'
      const pageText = start && end
        ? (start === end ? `第${start}页` : `第${start}-${end}页`)
        : ''
      return [prefix, title, pageText].filter(Boolean).join(' · ')
    },
    sessionPageLabel(trend) {
      const start = this.sessionPageStart(trend)
      const end = this.sessionPageEnd(trend)
      if (start && end) return start === end ? `第${start}页` : `第${start}-${end}页`
      return ''
    },
    rateClass(rate) {
      const r = Number(rate || 0)
      if (r >= 0.8) return 'is-good'
      if (r >= 0.5) return 'is-mid'
      return 'is-low'
    },
    toggleTrend() {
      this.expanded.trend = !this.expanded.trend
      if (this.expanded.trend) this.$nextTick(() => this.renderTrendChart())
    },
    resizeTrendChart() {
      if (this.trendChart) this.trendChart.resize()
    },
    renderTrendChart() {
      const el = this.$refs.trendChartRef
      const trends = this.sessionTrends
      if (!el || trends.length < 1) return
      // 容器尚未拥有真实尺寸（结果面板初次挂载/被 v-show 折叠时），
      // ECharts 无法构建 coordinateSystem，dataSample 处理器会在 coordSys.type 上崩溃。
      // 用 ResizeObserver 等待容器拿到非零尺寸后再 init。
      if (!el.offsetWidth || !el.offsetHeight) {
        if (!this.trendResizeObserver && typeof ResizeObserver !== 'undefined') {
          this.trendResizeObserver = new ResizeObserver(() => {
            if (el.offsetWidth && el.offsetHeight) {
              this.trendResizeObserver.disconnect()
              this.trendResizeObserver = null
              this.renderTrendChart()
            }
          })
          this.trendResizeObserver.observe(el)
        }
        return
      }
      // 每次都 dispose 再重建，避免 ECharts 内部 task scheduler 持有旧 series model 导致崩溃
      if (this.trendChart) {
        this.trendChart.dispose()
        this.trendChart = null
      }
      this.trendChart = echarts.init(el)
      const labels = trends.map(t => this.sessionDisplayLabel(t))
      const tooltipLabels = trends.map(t => this.sessionTooltipLabel(t))
      const accData = trends.map(t => Math.round((t.accuracy || 0) * 100))
      const single = accData.length < 2
      this.trendChart.setOption({
        grid: { left: 40, right: 16, top: 28, bottom: 38 },
        tooltip: {
          trigger: 'axis',
          formatter: params => {
            const idx = params[0].dataIndex
            const t = trends[idx]
            const submodules = Array.isArray(t.submodules) && t.submodules.length
              ? `<br/>子模块：${t.submodules.join('、')}`
              : ''
            return `${tooltipLabels[idx]}<br/>正确率：${accData[idx]}%<br/>题量：${t.question_count || 0}${submodules}`
          },
        },
        xAxis: {
          type: 'category', data: labels, boundaryGap: single,
          axisLabel: { fontSize: 11, color: '#617087', interval: 0, rotate: labels.length > 4 ? 30 : 0 },
        },
        yAxis: {
          type: 'value', min: 0, max: 100,
          axisLabel: { formatter: '{value}%', fontSize: 11, color: '#617087' },
          splitLine: { lineStyle: { color: '#eef2f8' } },
        },
        series: [single
          ? {
            type: 'bar', data: accData, barWidth: '38%',
            itemStyle: { color: '#2d6fae', borderRadius: [4, 4, 0, 0] },
            label: { show: true, position: 'top', formatter: '{c}%', fontSize: 11, color: '#34516e' },
          }
          : {
            type: 'line', data: accData, smooth: true, symbolSize: 7,
            lineStyle: { color: '#2d6fae', width: 2 },
            itemStyle: { color: '#2d6fae' },
            areaStyle: { color: 'rgba(45, 111, 174, 0.10)' },
            label: { show: true, formatter: '{c}%', fontSize: 11, color: '#34516e' },
          }],
      })
    },
    async openPass3Dialog() {
      this.pass3DialogVisible = true
      this.pass3Loading = true
      this.pass3Candidates = []
      try {
        const username = localStorage.getItem('userId') || ''
        const currentId = this.activeAnalysisId || this.activeResult?.analysis_id || ''
        const resp = await listCIPass3Pairs({ username })
        if (resp && resp.error_num === 0) {
          const pairs = Array.isArray(resp.pairs) ? resp.pairs : []
          this.pass3Candidates = currentId
            ? pairs.filter(p => p.analysis_id_a === currentId || p.analysis_id_b === currentId)
            : pairs
        }
      } catch (e) {
        console.error('[HG] listCIPass3Pairs error:', e)
      } finally {
        this.pass3Loading = false
      }
    },
    closePass3Dialog() {
      this.pass3DialogVisible = false
    },
    startPass3(pair) {
      this.$emit('start-pass3', {
        analysis_id_a: pair.analysis_id_a,
        analysis_id_b: pair.analysis_id_b,
        cross_analysis_id: pair.cross_analysis_id,
      })
      this.pass3DialogVisible = false
    },
  },
}
</script>

<style scoped>
.hg-skill-usage { padding: 12px 18px; font-size: 13px; overflow-wrap: anywhere; }
.hg-skill-usage p { margin: 8px 0; line-height: 1.5; }
.hg-page-context {
  padding: 12px 20px;
  background: #f3f7fc;
  border-bottom: 1px solid #dce5ee;
  line-height: 1.65;
  overflow-wrap: anywhere;
  max-height: 25vh;
  overflow-y: auto;
  flex-shrink: 0;
}
.hg-page-context p { margin: 4px 0 0; }
.hg-panel-overlay {
  position: fixed;
  inset: 0;
  z-index: 2200;
  background: rgba(10, 18, 30, 0.12);
  display: flex;
  justify-content: flex-end;
}

.hg-panel-overlay.is-page-only,
.hg-panel-overlay.is-verify-assist {
  background: transparent;
  pointer-events: none;
}

.hg-panel-overlay.is-page-only .hg-dialog-overlay,
.hg-panel-overlay.is-verify-assist .hg-dialog-overlay {
  pointer-events: none;
}

.hg-panel-overlay.is-verify-assist .hg-va-side,
.hg-panel-overlay.is-verify-assist .hg-va-rail-btn {
  pointer-events: auto;
}

.hg-panel-overlay.is-page-only:not(.is-verify-assist) .hg-dialog-overlay {
  pointer-events: auto;
}

.hg-panel {
  width: min(720px, 92vw);
  height: 100vh;
  background: #ffffff;
  box-shadow: -10px 0 28px rgba(20, 32, 50, 0.18);
  display: flex;
  flex-direction: column;
}

.hg-header,
.hg-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid #e5eaf2;
  background: #f8fafc;
}

.hg-title {
  font-size: 17px;
  font-weight: 700;
  color: #23324a;
}

.hg-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #617087;
}

.hg-close {
  width: 30px;
  height: 30px;
  border: 1px solid #d7e0ee;
  border-radius: 6px;
  background: #fff;
  color: #52627a;
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.hg-body {
  flex: 1;
  overflow: auto;
  padding: 16px 18px;
}

.hg-check-warning {
  flex-shrink: 0;
  margin: 10px 18px;
  padding: 10px 12px;
  border: 1px solid #e7c887;
  border-radius: 6px;
  background: #fff8e8;
  color: #785419;
  font-size: 13px;
  overflow-wrap: anywhere;
}

.hg-verify-banner {
  flex-shrink: 0;
  margin: 10px 18px;
  padding: 12px 14px;
  border: 1px solid #e8b4b0;
  border-left: 4px solid #c45c54;
  border-radius: 8px;
  background: linear-gradient(180deg, #fff6f5 0%, #fffaf8 100%);
  color: #5a2e2a;
}
.hg-verify-banner-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.hg-verify-banner-head strong { font-size: 14px; }
.hg-verify-counts { display: flex; gap: 8px; font-size: 12px; }
.hg-verify-counts em {
  font-style: normal;
  padding: 1px 8px;
  border-radius: 999px;
  background: #f8e4e2;
  color: #a33d36;
}
.hg-verify-summary {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.55;
  color: #6b3f3a;
}
.hg-verify-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.hg-verify-chip {
  appearance: none;
  border: 1px solid #d0dbe8;
  background: #e8eef5;
  color: #3b6ea5;
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
  line-height: 1.4;
}
.hg-verify-chip.is-critical {
  background: #fdecea;
  border-color: #ecc0bc;
  color: #a5342c;
}
.hg-verify-chip.is-careful {
  background: #fff4e5;
  border-color: #edd2a8;
  color: #8a5a14;
}
.hg-verify-tier { margin: 0 0 8px; }
.hg-verify-tier-name {
  font-size: 12px;
  font-weight: 700;
  margin: 2px 0 4px;
  color: #5a2e2a;
}
.hg-verify-tier-name em { font-style: normal; font-weight: 600; margin-left: 4px; }
.hg-verify-chip.is-i { background: #fdecea; border-color: #ecc0bc; color: #a5342c; }
.hg-verify-chip.is-ii { background: #fff4e5; border-color: #edd2a8; color: #8a5a14; }
.hg-verify-chip.is-iii { background: #f4f1ea; border-color: #ddd4c4; color: #5c5346; }
.hg-verify-counts em.is-i { background: #f8e4e2; color: #a33d36; }
.hg-verify-counts em.is-ii { background: #fff4e5; color: #8a5a14; }
.hg-verify-counts em.is-iii { background: #f4f1ea; color: #5c5346; }
.hg-verify-chip:hover { filter: brightness(0.97); }
.hg-verify-more {
  appearance: none;
  border: 1px dashed #c4a8a4;
  background: #fff;
  color: #7a4a44;
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
}
.hg-verify-chips.is-full { margin-top: 6px; }

.hg-layer {
  border: 1px solid #e1e8f3;
  border-radius: 6px;
  margin-bottom: 12px;
  overflow: hidden;
}

.hg-layer-header {
  width: 100%;
  border: 0;
  background: #f5f8fc;
  padding: 11px 14px;
  display: flex;
  justify-content: space-between;
  color: #27364f;
  font-weight: 700;
  cursor: pointer;
}

.hg-layer-content {
  padding: 13px 14px;
}

.hg-zone-text {
  color: #2f3c55;
  font-size: 13px;
  line-height: 1.65;
}

.hg-zone-entries {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hg-zone-entry {
  padding: 7px 9px;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 6px;
}

.hg-zone-kp {
  font-size: 13px;
  font-weight: 600;
  color: #2f3c55;
  line-height: 1.5;
}

.hg-zone-comment {
  margin-top: 3px;
  font-size: 12px;
  color: #56627a;
  line-height: 1.6;
}

.hg-zone-evidence {
  margin-top: 4px;
  font-size: 11px;
  color: #8a93a6;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 2px;
}

.hg-zone-ev-label {
  flex-shrink: 0;
}

.hg-zone-ev-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  align-items: center;
}

.hg-zone-ev-chip {
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(45, 111, 174, 0.08);
  color: #2d6fae;
  cursor: pointer;
  border: none;
  font-size: 11px;
  line-height: 1.6;
  transition: background 0.15s;
}
.hg-zone-ev-chip:hover {
  background: rgba(45, 111, 174, 0.2);
}

.hg-zone-ev-more {
  padding: 1px 5px;
  border-radius: 3px;
  background: rgba(138, 147, 166, 0.12);
  color: #8a93a6;
  cursor: pointer;
  border: none;
  font-size: 11px;
  line-height: 1.6;
  transition: background 0.15s;
}
.hg-zone-ev-more:hover {
  background: rgba(138, 147, 166, 0.25);
  color: #56627a;
}

.hg-zone-label {
  font-size: 12px;
  font-weight: 700;
  color: #40516d;
  margin-bottom: 6px;
}

.hg-zone-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.hg-zone-item {
  border: 1px solid #e4eaf3;
  border-radius: 6px;
  padding: 10px;
  background: #fbfcfe;
}

.hg-page-entry {
  border: 1px solid #dfe7f2;
  border-radius: 6px;
  background: #fff;
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hg-page-entry-title {
  font-size: 13px;
  font-weight: 700;
  color: #2d3c55;
}

.hg-page-entry-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #75849b;
}

.hg-primary-btn,
.hg-nav-btn {
  height: 30px;
  border: 1px solid #d6e0ee;
  border-radius: 6px;
  background: #fff;
  color: #34445e;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
}

.hg-primary-btn {
  padding: 0 14px;
  background: #2d6fae;
  border-color: #2d6fae;
  color: #fff;
}

.hg-primary-btn:disabled,
.hg-nav-btn:disabled {
  cursor: not-allowed;
  opacity: 0.48;
}

.hg-nav-btn {
  min-width: 78px;
  padding: 0 10px;
}

.hg-empty {
  color: #8694aa;
  font-size: 13px;
  padding: 12px 0;
}

.hg-red-blue-card {
  margin-bottom: 12px;
  padding: 14px;
  border: 1px solid #d8ddec;
  border-top: 4px solid #7651a8;
  border-radius: 8px;
  background: linear-gradient(135deg, #f7faff 0%, #fff7f7 100%);
}

.hg-red-blue-card.is-red { border-top-color: #d65252; }
.hg-red-blue-card.is-blue { border-top-color: #3978bb; }
.hg-red-blue-card.is-purple { border-top-color: #7651a8; }
.hg-red-blue-card.is-pending { border-top-color: #a3adbd; }

.hg-red-blue-head,
.hg-red-blue-rails,
.hg-red-blue-dimension > div,
.hg-red-blue-empty {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.hg-red-blue-kicker {
  color: #56627a;
  font-size: 12px;
  font-weight: 700;
}

.hg-red-blue-score {
  margin-top: 2px;
  color: #253750;
  font-size: 28px;
  font-weight: 800;
}

.hg-red-blue-score small {
  font-size: 13px;
  font-weight: 600;
  color: #738199;
}

.hg-red-blue-status {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}

.hg-red-blue-status span {
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(118, 81, 168, 0.11);
  color: #684398;
  font-size: 12px;
  font-weight: 700;
}

.hg-red-blue-status small {
  color: #7b8799;
  font-size: 11px;
}

.hg-red-blue-rails {
  margin-top: 12px;
}

.hg-red-blue-rails > div {
  flex: 1;
  display: flex;
  justify-content: space-between;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
}

.hg-red-blue-rails .is-blue { color: #225c96; background: #edf5fd; }
.hg-red-blue-rails .is-red { color: #a73535; background: #fff0f0; }
.hg-red-blue-rails strong { font-size: 15px; }

.hg-red-blue-dimensions {
  margin-top: 10px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 7px;
}

.hg-red-blue-dimension {
  padding: 8px 9px;
  border: 1px solid rgba(216, 225, 239, 0.9);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.76);
}

.hg-red-blue-dimension strong,
.hg-red-blue-dimension span {
  color: #33445e;
  font-size: 12px;
}

.hg-red-blue-dimension p,
.hg-red-blue-suggestions p {
  margin: 5px 0 0;
  color: #657188;
  font-size: 11px;
  line-height: 1.5;
}

.hg-red-blue-reason {
  margin-top: 10px;
  display: grid;
  gap: 4px;
  color: #44536b;
  font-size: 12px;
  line-height: 1.6;
}

.hg-red-blue-suggestions {
  margin-top: 10px;
  color: #384860;
  font-size: 12px;
}

.hg-red-blue-suggestions summary {
  cursor: pointer;
  font-weight: 700;
}

.hg-red-blue-suggestions article {
  margin-top: 8px;
  padding: 9px 10px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.8);
}

.hg-red-blue-suggestions article > div:first-child {
  display: flex;
  gap: 6px;
  margin-bottom: 5px;
}

.hg-red-blue-suggestions article > div:first-child span {
  padding: 1px 6px;
  border-radius: 999px;
  color: #6a4b22;
  background: #fff0d9;
  font-size: 10px;
}

.hg-red-blue-evidence {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 6px;
}

.hg-red-blue-evidence button {
  border: 0;
  border-radius: 999px;
  padding: 2px 7px;
  color: #2d6fae;
  background: #edf5fd;
  cursor: pointer;
  font-size: 10px;
}

.hg-red-blue-empty > div {
  display: grid;
  gap: 4px;
}

.hg-red-blue-empty strong { color: #33445e; font-size: 13px; }
.hg-red-blue-empty span { color: #748198; font-size: 12px; }
.hg-red-blue-empty button {
  flex: 0 0 auto;
  height: 30px;
  border: 1px solid #7651a8;
  border-radius: 6px;
  padding: 0 11px;
  color: #684398;
  background: #fff;
  cursor: pointer;
}
.hg-red-blue-empty button:disabled { cursor: not-allowed; opacity: 0.55; }

.hg-progress {
  padding: 10px 18px;
  border-bottom: 1px solid #e5eaf2;
  background: #fff;
}

.hg-progress-hint {
  margin-top: 6px;
  font-size: 11px;
  color: #8a97ab;
  line-height: 1.4;
}

.hg-progress-title {
  font-size: 12px;
  color: #53647d;
  margin-bottom: 8px;
}

.hg-progress-track {
  height: 7px;
  border-radius: 999px;
  background: #e8eef6;
  overflow: hidden;
}

.hg-progress-bar {
  height: 100%;
  background: #2d6fae;
}

.hg-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 3300;
  background: rgba(0, 0, 0, 0.48);
  display: flex;
  align-items: center;
  justify-content: center;
}

.hg-dialog-overlay.is-verify-assist {
  z-index: 2400;
  background: transparent;
  justify-content: space-between;
  align-items: stretch;
  padding: 10px;
  gap: 0;
}

.hg-dialog-overlay.is-verify-assist.is-va-collapsed {
  justify-content: space-between;
  align-items: flex-start;
  padding: 10px 8px;
}

.hg-dialog {
  width: min(1180px, 94vw);
  max-height: 92vh;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.hg-va-side {
  position: relative;
  height: calc(100vh - 20px);
  max-width: min(46vw, 720px);
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow: 0 10px 36px rgba(20, 32, 50, 0.22);
  border: 1px solid #d9e2ef;
  transition: transform 0.22s ease, opacity 0.18s ease;
}

.hg-va-side.is-left {
  margin-right: auto;
}

.hg-va-side.is-right {
  margin-left: auto;
}

.hg-va-side-header {
  flex-shrink: 0;
  padding: 10px 12px;
}

.hg-va-side-header .hg-dialog-meta {
  font-size: 11px;
}

.hg-page-context.is-va-compact {
  flex-shrink: 0;
  max-height: 72px;
  overflow: hidden;
  padding: 6px 10px;
  font-size: 11px;
  line-height: 1.35;
  color: #5a6b82;
  border-bottom: 1px solid #e8eef6;
}

.hg-page-context.is-va-compact strong {
  font-size: 11px;
  font-weight: 650;
  color: #3a4a63;
}

.hg-page-context.is-va-compact .hg-va-context-summary {
  margin: 2px 0 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #718096;
}

.hg-va-side-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 8px 10px 12px;
}

.hg-va-side-body .hg-image-title {
  margin-bottom: 6px;
  font-size: 11px;
}

.hg-va-resize {
  position: absolute;
  top: 0;
  width: 8px;
  height: 100%;
  cursor: ew-resize;
  z-index: 3;
}

.hg-va-resize.is-left-panel {
  right: -3px;
}

.hg-va-resize.is-right-panel {
  left: -3px;
}

.hg-va-resize::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 2px;
  width: 3px;
  height: 36px;
  margin-top: -18px;
  border-radius: 2px;
  background: #c5d0e0;
}

.hg-va-toggle,
.hg-va-rail-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid #d5deea;
  border-radius: 6px;
  background: #f4f7fb;
  color: #5a6b82;
  cursor: pointer;
  padding: 0;
}

.hg-va-toggle:hover,
.hg-va-rail-btn:hover {
  background: #eaf0f8;
  color: #2d6fae;
}

.hg-va-rail-btn {
  margin-top: 8px;
  box-shadow: 0 4px 14px rgba(20, 32, 50, 0.16);
}

.hg-va-rail-btn.is-right {
  margin-left: auto;
}

.hg-va-icon {
  width: 18px;
  height: 18px;
  display: block;
}

.hg-dialog-meta {
  margin-top: 3px;
  font-size: 12px;
  color: #718096;
}

.hg-dialog-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.hg-dialog-body {
  flex: 1;
  overflow: auto;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  padding: 14px;
}

.hg-image-pane {
  min-width: 0;
}

.hg-image-title {
  font-size: 12px;
  color: #617087;
  margin-bottom: 8px;
  font-weight: 700;
}

.hg-stage {
  position: relative;
  width: 100%;
}

.hg-img-wrap,
.hg-stage {
  min-height: 120px;
}

.hg-img-wrap.is-loading,
.hg-stage.is-loading {
  opacity: 0.72;
  transition: opacity 0.15s ease;
}

.hg-page-img {
  width: 100%;
  height: auto;
  display: block;
  border: 1px solid #dfe6f0;
  border-radius: 6px;
  background: #f8fafc;
}

.hg-box-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.hg-va-raw-stage {
  position: relative;
}

.hg-verify-focus-box {
  position: absolute;
  box-sizing: border-box;
  pointer-events: auto;
  border: 2px solid #2d6fae;
  border-radius: 3px;
  background: rgba(45, 111, 174, 0.16);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.92);
  z-index: 2;
}

.hg-verify-focus-tag {
  position: absolute;
  z-index: 4;
  pointer-events: none;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(24, 34, 52, 0.94);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  line-height: 1.3;
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.22);
  white-space: nowrap;
}

.hg-verify-focus-arrow {
  position: absolute;
  width: 0;
  height: 0;
  z-index: 3;
  pointer-events: none;
  filter: drop-shadow(0 0 1px rgba(255, 255, 255, 0.95));
}

.hg-verify-focus-arrow.is-from-left {
  border-top: 9px solid transparent;
  border-bottom: 9px solid transparent;
  border-left: 16px solid #2d6fae;
}

.hg-verify-focus-arrow.is-from-right {
  border-top: 9px solid transparent;
  border-bottom: 9px solid transparent;
  border-right: 16px solid #2d6fae;
}

.hg-question-box {
  position: absolute;
  pointer-events: auto;
  border: 1px solid rgba(45, 111, 174, 0.45);
  background: rgba(45, 111, 174, 0.04);
  cursor: help;
}

.hg-question-box.is-confidence {
  cursor: help;
}

.hg-question-box.is-baked {
  border-color: transparent;
  background: transparent;
}

.hg-question-box.is-baked:hover {
  border-color: rgba(45, 111, 174, 0.35);
  background: rgba(45, 111, 174, 0.06);
}

.hg-confidence-dot {
  position: absolute;
  top: 50%;
  border-radius: 50%;
  pointer-events: none;
}

.hg-question-box.is-wrong {
  border-color: rgba(208, 64, 64, 0.62);
}

.hg-question-box.is-partial {
  border-color: rgba(214, 126, 35, 0.7);
}

.hg-question-box.is-correct {
  border-color: rgba(52, 142, 76, 0.5);
}

.hg-tooltip {
  position: absolute;
  z-index: 5;
  display: flex;
  flex-direction: column;
  width: min(360px, 48vw);
  padding: 10px;
  border-radius: 6px;
  background: rgba(24, 34, 52, 0.94);
  color: #fff;
  box-shadow: 0 12px 24px rgba(0, 0, 0, 0.24);
  pointer-events: auto;
  overflow: hidden;
}

.hg-tooltip-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-weight: 700;
  font-size: 12px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.hg-tooltip-expand {
  flex-shrink: 0;
  border: 1px solid rgba(255, 255, 255, 0.28);
  background: rgba(255, 255, 255, 0.08);
  color: #d7e6f8;
  border-radius: 4px;
  font-size: 11px;
  line-height: 1.2;
  padding: 2px 6px;
  cursor: pointer;
}

.hg-tooltip-expand:hover {
  background: rgba(255, 255, 255, 0.16);
}

.hg-tooltip-body {
  overflow-x: hidden;
  overflow-y: auto;
  min-height: 0;
  flex: 1 1 auto;
  padding-right: 2px;
  overscroll-behavior: contain;
}

.hg-tooltip-row {
  display: grid;
  grid-template-columns: 68px 1fr;
  gap: 8px;
  font-size: 12px;
  line-height: 1.45;
  margin-top: 5px;
}

.hg-tooltip-row span {
  color: #b8c5d8;
}

.hg-tooltip-row strong {
  color: #fff;
  font-weight: 500;
  word-break: break-word;
  white-space: pre-wrap;
}
.hg-tooltip-row.is-block {
  grid-template-columns: 1fr;
}
.hg-three-q-compact {
  gap: 6px;
}
.hg-tooltip .hg-three-q-item strong {
  color: #d7e6f8;
}
.hg-tooltip .hg-three-q-item p {
  color: #fff;
}

/* open material overview */
.hg-open-overview-header {
  cursor: default;
}

.hg-open-overview-content {
  display: grid;
  gap: 10px;
}

.hg-open-overview-card {
  border: 1px solid #d8e5f4;
  border-radius: 6px;
  background: #f8fbff;
  padding: 10px 12px;
}

.hg-open-overview-card h4 {
  margin: 0 0 6px;
  color: #245f98;
  font-size: 13px;
}

.hg-open-overview-card p,
.hg-open-overview-card ol {
  margin: 0;
  color: #2f3c55;
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
}

.hg-open-overview-card ol {
  padding-left: 20px;
}

/* diagnosis section */
.hg-diagnosis-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.hg-diagnosis-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.hg-meta-badge {
  font-size: 11px;
  line-height: 1.7;
  padding: 1px 7px;
  border-radius: 999px;
  background: rgba(45, 111, 174, 0.10);
  color: #2d6fae;
}

.hg-meta-badge.is-warn {
  background: rgba(214, 126, 35, 0.14);
  color: #a05a14;
}

.hg-summary-card {
  background: #f0f5fb;
  border-left: 3px solid #2d6fae;
  border-radius: 0 4px 4px 0;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.7;
  color: #2a3b55;
}
.hg-three-q {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.hg-three-q-item strong {
  display: block;
  margin-bottom: 4px;
  color: #1f4e79;
}
.hg-three-q-item p {
  margin: 0;
  white-space: pre-wrap;
}
.hg-mean-tags {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hg-mean-tags em {
  font-style: normal;
  margin-right: 6px;
  color: #1f4e79;
}
.hg-basis-strip {
  margin-bottom: 10px;
}

.hg-process-card {
  border: 1px solid #d8e5f4;
  border-left: 3px solid #3a9e6a;
  border-radius: 0 4px 4px 0;
  background: #f6fbf8;
  padding: 9px 12px;
}

.hg-process-title {
  font-size: 12px;
  font-weight: 700;
  color: #236b45;
  margin-bottom: 4px;
}

.hg-process-text {
  font-size: 12.5px;
  color: #2f3c55;
  line-height: 1.65;
}

.hg-diag-block {
  border: 1px solid #e8eef6;
  border-radius: 6px;
  overflow: hidden;
}

.hg-diag-label {
  font-size: 11px;
  font-weight: 700;
  padding: 4px 10px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.hg-diag-list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
}

.hg-diag-list li {
  position: relative;
  padding: 4px 10px 4px 28px;
  font-size: 13px;
  line-height: 1.55;
  color: #2f3c55;
}

.hg-diag-list li::before {
  position: absolute;
  left: 11px;
  font-size: 11px;
  top: 5px;
}

.hg-diag-strengths { border-color: #cde8d8; background: #f7fbf8; }
.hg-diag-strengths .hg-diag-label { background: #edf7f0; color: #2e7d4f; }
.hg-diag-strengths .hg-diag-list li::before { content: '✓'; color: #48a86a; }

.hg-diag-main_problems { border-color: #f1cece; background: #fffafa; }
.hg-diag-main_problems .hg-diag-label { background: #fff0f0; color: #b5342a; }
.hg-diag-main_problems .hg-diag-list li::before { content: '!'; color: #d04040; font-weight: 700; }

.hg-diag-next_actions { border-color: #c5d8f0; background: #f6f9fe; }
.hg-diag-next_actions .hg-diag-label { background: #eef3fb; color: #245f98; }
.hg-diag-next_actions .hg-diag-list li::before { content: '→'; color: #2d6fae; }

/* zone cards */
.hg-zone-blind_spot { border-top: 3px solid #e05252; background: #fff6f6; }
.hg-zone-blind_spot .hg-zone-label { color: #b5342a; }

.hg-zone-friction_zone { border-top: 3px solid #e07c28; background: #fff8f2; }
.hg-zone-friction_zone .hg-zone-label { color: #a05a14; }

.hg-zone-zpd { border-top: 3px solid #3a9e6a; background: #f4fbf7; }
.hg-zone-zpd .hg-zone-label { color: #236b45; }

/* header actions */
.hg-header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.hg-cross-btn {
  height: 30px;
  padding: 0 14px;
  border: 1px solid #2d6fae;
  border-radius: 6px;
  background: #fff;
  color: #2d6fae;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.hg-cross-btn:hover { background: #f0f6fc; }
.hg-cross-btn:disabled { cursor: not-allowed; opacity: 0.5; }

.hg-version-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}

.hg-version-label {
  font-size: 12px;
  color: #617087;
  white-space: nowrap;
}

.hg-version-select {
  min-width: 168px;
  max-width: 220px;
  height: 30px;
  border: 1px solid #d6e0ee;
  border-radius: 6px;
  background: #fff;
  color: #34445e;
  font-size: 12px;
  padding: 0 8px;
}

.hg-key-version-btn {
  height: 30px;
  padding: 0 10px;
  border: 1px solid #d6e0ee;
  border-radius: 6px;
  background: #fff;
  color: #52627a;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.hg-key-version-btn.is-key {
  border-color: #d8a21f;
  background: #fff8df;
  color: #9a6a00;
}

.hg-key-version-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.hg-rerun-btn {
  height: 30px;
  padding: 0 12px;
  border: 1px solid #d67e23;
  border-radius: 6px;
  background: #fff7ef;
  color: #a05a14;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

.hg-rerun-btn:hover { background: #ffeede; }
.hg-rerun-btn:disabled { cursor: not-allowed; opacity: 0.5; }

.hg-rerun-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 4000;
  background: rgba(10, 18, 30, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}

.hg-rerun-confirm-box {
  width: min(420px, 92vw);
  max-height: calc(100vh - 32px);
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 18px 40px rgba(20, 32, 50, 0.24);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.hg-rerun-confirm-header {
  flex: 0 0 auto;
  padding: 18px 22px 0;
}

.hg-rerun-confirm-body {
  min-height: 0;
  padding: 14px 22px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.hg-rerun-confirm-title {
  font-size: 16px;
  font-weight: 700;
  color: #23324a;
}

.hg-rerun-confirm-text {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: #53647d;
}

.hg-rerun-stage-list {
  display: grid;
  gap: 8px;
}

.hg-rerun-stage-option {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 8px;
  align-items: flex-start;
  padding: 10px 12px;
  border: 1px solid #d8e2f0;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

.hg-rerun-stage-option.is-active {
  border-color: #d67e23;
  background: #fff8f1;
}

.hg-rerun-stage-option.is-disabled,
.hg-rerun-fold.is-disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.hg-rerun-stage-option input {
  margin-top: 2px;
}

.hg-rerun-stage-option strong {
  display: block;
  color: #26374f;
  font-size: 13px;
}

.hg-rerun-stage-option em {
  display: block;
  margin-top: 3px;
  color: #6b7890;
  font-size: 12px;
  font-style: normal;
  line-height: 1.45;
}

.hg-rerun-fold {
  margin-top: 10px;
  border: 1px solid #e3e8f0;
  border-radius: 8px;
  background: #fbfcfe;
  overflow: hidden;
}

.hg-rerun-fold.is-red-blue {
  border-color: #ded6ea;
  background: #fbf9fd;
}

.hg-rerun-fold.is-preprocess {
  border-color: #cfdced;
  background: #f8fbff;
}

.hg-rerun-fold.is-expanded {
  background: #fff;
}

.hg-rerun-fold-trigger {
  width: 100%;
  min-height: 48px;
  padding: 9px 12px;
  border: 0;
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  color: #33445c;
  cursor: pointer;
  text-align: left;
}

.hg-rerun-fold-trigger > span:first-child {
  min-width: 0;
}

.hg-rerun-fold-trigger strong,
.hg-rerun-fold-trigger em {
  display: block;
}

.hg-rerun-fold-trigger strong {
  font-size: 13px;
}

.hg-rerun-fold-trigger em {
  margin-top: 2px;
  color: #738198;
  font-size: 11px;
  font-style: normal;
  line-height: 1.4;
}

.hg-rerun-fold.is-red-blue .hg-rerun-fold-trigger strong {
  color: #554168;
}

.hg-rerun-fold-state {
  flex: 0 0 auto;
  color: #7c8799;
  font-size: 11px;
  white-space: nowrap;
}

.hg-rerun-fold-state i {
  display: inline-block;
  margin-left: 3px;
  font-size: 13px;
  font-style: normal;
  transform: translateY(-1px);
  transition: transform 0.18s ease;
}

.hg-rerun-fold.is-expanded .hg-rerun-fold-state i {
  transform: translateY(2px) rotate(180deg);
}

.hg-rerun-fold-body {
  padding: 0 10px 10px;
  border-top: 1px solid #edf0f5;
}

.hg-rerun-session-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 0 0 6px;
  padding-top: 9px;
  font-size: 13px;
  color: #554b43;
}
.hg-rerun-session-head button {
  border: 0;
  background: transparent;
  color: #c36a27;
  cursor: pointer;
  padding: 0 0 0 10px;
}
.hg-rerun-session-list {
  max-height: 180px;
  overflow-y: auto;
  border: 1px solid #f0dfd1;
  border-radius: 8px;
}
.hg-rerun-session-option {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 9px 10px;
  border-bottom: 1px solid #f7eee8;
  cursor: pointer;
  font-size: 13px;
  color: #554b43;
}
.hg-rerun-session-option:last-child { border-bottom: 0; }
.hg-rerun-session-empty { padding-top: 9px; color: #8f8176; font-size: 13px; }

.hg-preprocess-mode-list {
  display: grid;
  gap: 7px;
  padding-top: 9px;
}

.hg-preprocess-mode-option {
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 8px;
  align-items: flex-start;
  padding: 9px 10px;
  border: 1px solid #dce5f1;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
}

.hg-preprocess-mode-option.is-active {
  border-color: #4c82bd;
  background: #f1f7ff;
}

.hg-preprocess-mode-option input {
  margin-top: 2px;
}

.hg-preprocess-mode-option strong {
  display: block;
  color: #2d425e;
  font-size: 13px;
}

.hg-preprocess-mode-option em {
  display: block;
  margin-top: 3px;
  color: #6d7b90;
  font-size: 11px;
  font-style: normal;
  line-height: 1.45;
}

.hg-preprocess-mode-notice,
.hg-preprocess-result-summary {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 7px;
  font-size: 12px;
  line-height: 1.55;
}

.hg-preprocess-mode-notice {
  background: #fff5e8;
  color: #92541a;
}

.hg-preprocess-result-summary {
  background: #f2f6fb;
  color: #54677f;
}

.hg-red-blue-toggle {
  margin-top: 9px;
  display: grid;
  grid-template-columns: 18px 1fr;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #d9d2e8;
  border-radius: 8px;
  background: #faf8fd;
  cursor: pointer;
}

.hg-red-blue-toggle.is-disabled {
  cursor: not-allowed;
  opacity: 0.62;
}

.hg-red-blue-toggle input { margin-top: 2px; }
.hg-red-blue-toggle strong {
  display: block;
  color: #4d3d63;
  font-size: 13px;
}
.hg-red-blue-toggle em {
  display: block;
  margin-top: 3px;
  color: #7c718c;
  font-size: 11px;
  font-style: normal;
  line-height: 1.5;
}

.hg-rerun-feedback-preview {
  margin-top: 8px;
  padding: 9px 11px;
  border-radius: 7px;
  background: #f5f1fa;
  color: #645574;
  font-size: 11px;
  line-height: 1.55;
}

.hg-rerun-feedback-policy {
  margin-top: 8px;
  padding: 8px 10px;
  border-left: 3px solid #8b6ca8;
  border-radius: 5px;
  background: #f7f3fb;
  color: #695878;
  font-size: 11px;
  line-height: 1.55;
}

.hg-rerun-feedback-preview ul {
  margin: 6px 0 0;
  padding-left: 18px;
}

.hg-rerun-confirm-actions {
  flex: 0 0 auto;
  padding: 12px 22px 16px;
  border-top: 1px solid #e8edf4;
  background: #fff;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.hg-rerun-cancel-btn,
.hg-rerun-confirm-btn {
  height: 32px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.hg-rerun-cancel-btn {
  border: 1px solid #d6e0ee;
  background: #fff;
  color: #52627a;
}

.hg-rerun-confirm-btn {
  border: 1px solid #d67e23;
  background: #d67e23;
  color: #fff;
  font-weight: 700;
}

.hg-rerun-confirm-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

/* trend chart */
.hg-trend-chart {
  width: 100%;
  height: 240px;
}

/* curriculum mastery */
.hg-curr-row { margin-bottom: 11px; }

.hg-curr-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 5px;
}

.hg-curr-domain {
  font-size: 12.5px;
  font-weight: 600;
  color: #34445e;
}

.hg-curr-rate {
  font-size: 11.5px;
  color: #6a7a92;
}

.hg-curr-track {
  height: 8px;
  border-radius: 999px;
  background: #eef2f8;
  overflow: hidden;
}

.hg-curr-bar {
  height: 100%;
  border-radius: 999px;
  background: #348e4c;
  transition: width 0.3s ease;
}

.hg-curr-bar.is-good { background: #348e4c; }
.hg-curr-bar.is-mid { background: #d67e23; }
.hg-curr-bar.is-low { background: #d04040; }

/* question markers */
.hg-question-box.is-high {
  border-width: 2px;
  box-shadow: 0 0 0 1px rgba(208, 64, 64, 0.18);
}

.hg-q-flag,
.hg-q-trend {
  position: absolute;
  top: -9px;
  font-size: 10px;
  line-height: 16px;
  width: 16px;
  height: 16px;
  text-align: center;
  border-radius: 50%;
  color: #fff;
  font-weight: 700;
  pointer-events: none;
}

.hg-q-flag { left: -8px; }
.hg-q-flag-high { background: #d04040; }
.hg-q-flag-uncertain { background: #d67e23; }
.hg-q-trend { right: -8px; }
.hg-q-trend-down { background: #d04040; }
.hg-q-trend-up { background: #348e4c; }

/* pass3 dialog */
.hg-pass3-dialog {
  width: min(640px, 92vw);
  max-height: 80vh;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.hg-pass3-body {
  flex: 1;
  overflow: auto;
  padding: 14px 18px;
}

.hg-pair-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.hg-pair-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #e1e8f3;
  border-radius: 6px;
  padding: 12px;
}

.hg-pair-subjects {
  font-size: 13.5px;
  font-weight: 700;
  color: #2d3c55;
}

.hg-pair-files {
  margin-top: 4px;
  font-size: 11.5px;
  color: #75849b;
  word-break: break-all;
}

@media (max-width: 820px) {
  .hg-zone-grid,
  .hg-dialog-body {
    grid-template-columns: 1fr;
  }

  .hg-page-entry,
  .hg-pair-item,
  .hg-dialog-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .hg-primary-btn,
  .hg-nav-btn {
    width: 100%;
  }
}

/* zone v2.5 chips & layout */
.hg-zone-kp-row { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; }
.hg-zone-tag { font-size: 11px; padding: 0 6px; border-radius: 3px; background: rgba(138, 147, 166, 0.14); color: #56627a; line-height: 1.6; }
.hg-zone-tag.hg-trend-improving { background: rgba(52, 142, 76, 0.14); color: #236b45; }
.hg-zone-tag.hg-trend-worsening { background: rgba(208, 64, 64, 0.14); color: #b5342a; }
.hg-zone-tag.hg-trend-stable { background: rgba(45, 111, 174, 0.10); color: #2d6fae; }
.hg-zone-stability { background: rgba(214, 126, 35, 0.12); color: #a05a14; }

.hg-zone-conf { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.hg-zone-conf-track { flex: 1; height: 4px; border-radius: 999px; background: #eaeff6; overflow: hidden; }
.hg-zone-conf-bar { height: 100%; background: #2d6fae; }
.hg-zone-conf-val { font-size: 11px; color: #6a7a92; min-width: 60px; text-align: right; }

.hg-zone-clusters { margin-top: 5px; display: flex; flex-direction: column; gap: 4px; }
.hg-zone-cluster { padding: 4px 6px; background: rgba(255, 255, 255, 0.55); border-left: 2px solid rgba(45, 111, 174, 0.25); border-radius: 3px; }
.hg-zone-cluster-cause { font-size: 12px; color: #2f3c55; line-height: 1.5; }

.hg-zone-next { margin-top: 6px; padding: 6px 8px; background: rgba(58, 158, 106, 0.10); border-radius: 4px; border-left: 2px solid #3a9e6a; }
.hg-zone-next-label { font-size: 11px; font-weight: 700; color: #236b45; margin-right: 6px; }
.hg-zone-next-text { font-size: 12px; color: #2f3c55; line-height: 1.55; }
</style>
