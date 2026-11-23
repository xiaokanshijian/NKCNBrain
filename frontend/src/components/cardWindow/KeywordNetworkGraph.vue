<template>
  <div class="keyword-network-container">
    <!-- 合并的按钮和图例说明 -->
    <div class="network-controls">
      <button 
        class="view-toggle-btn" 
        @click="toggleView"
        :title="viewMode === 'network' ? '切换到扁平视图' : '切换到网络图视图'">
        {{ viewMode === 'network' ? '📋' : '🕸️' }}
      </button>
      <button 
        v-if="viewMode === 'network'"
        class="reset-layout-btn" 
        @click="resetLayout"
        title="重置布局">
        🔄
      </button>
      <button 
        v-if="viewMode === 'network'"
        class="filter-strategy-btn"
        :class="{ 'active': currentFilterStrategy === 'union' }"
        @click="setFilterStrategy('union')"
        title="并集策略（默认）：筛选包含任一选中关键词的卡片，例如选择'关键词A'和'关键词B'，会显示包含A或B的所有卡片">
        ∪
      </button>
      <button 
        v-if="viewMode === 'network'"
        class="filter-strategy-btn"
        :class="{ 'active': currentFilterStrategy === 'intersection' }"
        @click="setFilterStrategy('intersection')"
        title="交集策略：筛选包含所有选中关键词的卡片，例如选择'关键词A'和'关键词B'，只会显示同时包含A和B的卡片">
        ∩
      </button>
      <button
        v-if="viewMode === 'network'"
        class="node-count-btn"
        @click="showNodeCountDialog = true"
        :title="`当前显示 ${nodeDisplayLimitLabel} 个关键词节点，点击调整`">
        #{{ nodeDisplayLimitShortLabel }}
      </button>
      <button
        v-if="viewMode === 'network' && showAuxLinkToggles"
        class="node-count-btn aux-link-btn"
        :class="{ active: showContourLinks }"
        @click="toggleAuxLinks('contour')"
        title="等高线：围着同一上级子节点的闭合圈。点击打开或关闭"
      >等高</button>
      <button
        v-if="viewMode === 'network' && showAuxLinkToggles"
        class="node-count-btn aux-link-btn"
        :class="{ active: showLongitudeLinks }"
        @click="toggleAuxLinks('longitude')"
        title="经度线：同色跨层虚线。点击打开或关闭"
      >经度</button>
      <button
        v-if="viewMode === 'network' && isV3Pipeline"
        class="node-count-btn aux-link-btn"
        :class="{ active: quadrantPlaceMode }"
        @click="toggleQuadrantPlaceMode"
        title="四个象限各自重新排布，中间留空。跨象限的线沿轴线走。再点一次回到原来的力导向。"
      >放入象限</button>
      <button
        v-if="viewMode === 'network' && !isOntologyScopeMode && !isV3Pipeline"
        class="node-count-btn keyword-pick-strategy-btn"
        @click="showKeywordPickStrategyDialog = true"
        :title="keywordPickStrategyTitle"
      >
        {{ keywordPickStrategyShortLabel }}
      </button>
      <button
        v-if="viewMode === 'network'"
        class="export-full-graph-btn"
        :disabled="exportingNetworkPng"
        @click="showExportGraphDialog = true"
        title="截取完整大图。可选择只截网络图，或连同上下左右的说明一起截"
      >
        {{ exportingNetworkPng ? '…' : '⤓' }}
      </button>
      
      <!-- 图例说明（仅网络视图） -->
      <div class="legend-container-inline" v-if="viewMode === 'network'">
      <div class="legend-main">
      <span class="legend-item">
        <span class="legend-label">四色：</span>
        <span class="legend-color" style="background: #dc143c;" title="专业业务">红</span>
        <span class="legend-color-text">专业业务</span>
        <span class="legend-color" style="background: #1e90ff;" title="工具手段">蓝</span>
        <span class="legend-color-text">工具手段</span>
        <span class="legend-color" style="background: #9370db;" title="思维框架">紫</span>
        <span class="legend-color-text">思维框架</span>
        <span class="legend-color" style="background: #3cb371;" title="简单深刻">绿</span>
        <span class="legend-color-text">简单深刻</span>
      </span>
      <span class="legend-item">
        <span class="legend-label">三类知识：</span>
        <svg class="legend-dmt-svg" width="22" height="22" viewBox="0 0 22 22">
          <circle cx="11" cy="11" r="6" fill="#9370db" stroke="#666" stroke-width="1.2"/>
          <text x="11" y="14.5" font-size="7" font-weight="bold" fill="#333" text-anchor="middle">传</text>
        </svg>
        <span class="legend-color-text">传统</span>
        <svg class="legend-dmt-svg" width="26" height="26" viewBox="0 0 26 26">
          <circle cx="13" cy="13" r="9.5" fill="none" stroke="#666" stroke-width="1.2"/>
          <circle cx="13" cy="13" r="6" fill="#9370db"/>
          <text x="13" y="16.5" font-size="7" font-weight="bold" fill="#333" text-anchor="middle">组</text>
        </svg>
        <span class="legend-color-text">组织</span>
        <svg class="legend-dmt-svg" width="30" height="30" viewBox="0 0 30 30">
          <circle cx="15" cy="15" r="13" fill="none" stroke="#666" stroke-width="1.2"/>
          <circle cx="15" cy="15" r="9.5" fill="none" stroke="#666" stroke-width="1.2"/>
          <circle cx="15" cy="15" r="6" fill="#9370db"/>
          <text x="15" y="18.5" font-size="7" font-weight="bold" fill="#333" text-anchor="middle">落</text>
        </svg>
        <span class="legend-color-text">部落</span>
      </span>
      <span class="legend-item">
        <span class="legend-label">D(小)M(中)T(大)：</span>
        <span class="legend-color-text">节点大小</span>
      </span>
      <!-- <span class="legend-item legend-item-axis-hint">
        <span class="legend-label">协作象限：</span>
        <span class="legend-color-text">背景为乔哈里视窗示意，节点位置仍为语义网络布局</span>
      </span> -->
      </div>
      <span class="legend-item legend-item-today-new">
        <span class="legend-today-new-circle"></span>
        <span class="legend-color-text">当日新增</span>
      </span>
      <span v-if="isV3Pipeline" class="legend-item">
        <span class="legend-label">经线：</span>
        <span class="legend-longitude-dash"></span>
        <span class="legend-color-text">同色跨层</span>
      </span>
      </div>
    </div>
    
    <!-- 关键词节点数量选择 -->
    <div
      v-if="showNodeCountDialog"
      class="color-dmt-dialog-overlay"
      @click.self="showNodeCountDialog = false"
    >
      <div class="color-dmt-dialog node-count-dialog" @click.stop>
        <div class="dialog-header">
          <h3>显示关键词节点数量</h3>
          <button class="dialog-close" @click="showNodeCountDialog = false">×</button>
        </div>
        <div class="dialog-content">
          <div class="dialog-current">
            本子共 <span style="font-weight: bold;">{{ totalKeywordCount }}</span> 个关键词；当前显示
            <span style="font-weight: bold;">{{ nodeDisplayLimitLabel }}</span> 个节点
          </div>
          <div class="dialog-options">
            <button
              v-for="option in nodeCountLimitOptions"
              :key="option.value"
              class="dialog-option-btn"
              :class="{ 'selected': option.value === nodeDisplayLimit }"
              @click="applyNodeDisplayLimit(option.value)"
            >
              {{ option.label }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showExportGraphDialog"
      class="color-dmt-dialog-overlay"
      @click.self="showExportGraphDialog = false"
    >
      <div class="color-dmt-dialog node-count-dialog" @click.stop>
        <div class="dialog-header">
          <h3>截取完整大图</h3>
          <button class="dialog-close" @click="showExportGraphDialog = false">×</button>
        </div>
        <div class="dialog-content">
          <div class="dialog-current">优先复制到剪贴板。若浏览器不让写入，会直接下载这张图。</div>
          <div class="dialog-options keyword-pick-strategy-options">
            <button
              class="dialog-option-btn keyword-pick-option-btn"
              :disabled="exportingNetworkPng"
              @click="exportFullNetworkPng(false)"
            >
              <div class="keyword-pick-option-title">只截网络图</div>
              <div class="keyword-pick-option-desc">节点、连线，以及图画布里的象限和轴端名称。</div>
            </button>
            <button
              class="dialog-option-btn keyword-pick-option-btn"
              :disabled="exportingNetworkPng"
              @click="exportFullNetworkPng(true)"
            >
              <div class="keyword-pick-option-title">带上上下左右信息</div>
              <div class="keyword-pick-option-desc">按页面上现在的样子，把图和上下左右的说明整张截下来。</div>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 节点取用策略（默认 / 取前三词 / 取前五词） -->
    <div
      v-if="showKeywordPickStrategyDialog"
      class="color-dmt-dialog-overlay"
      @click.self="showKeywordPickStrategyDialog = false"
    >
      <div class="color-dmt-dialog node-count-dialog" @click.stop>
        <div class="dialog-header">
          <h3>节点取用策略</h3>
          <button class="dialog-close" @click="showKeywordPickStrategyDialog = false">×</button>
        </div>
        <div class="dialog-content">
          <div class="dialog-current">
            在当前节点数量（{{ nodeDisplayLimitLabel }}）下，如何从参与分析的卡片中取词。
          </div>
          <div class="dialog-options keyword-pick-strategy-options">
            <button
              v-for="option in keywordPickStrategyOptions"
              :key="option.value"
              class="dialog-option-btn keyword-pick-option-btn"
              :class="{ 'selected': option.value === keywordPickStrategy }"
              @click="applyKeywordPickStrategy(option.value)"
            >
              <div class="keyword-pick-option-title">{{ option.label }}</div>
              <div class="keyword-pick-option-desc">{{ option.desc }}</div>
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 扁平视图（原有按钮列表） -->
    <div v-if="viewMode === 'flat'" class="tags-scroll-container">
      <button 
        class="tag-btn" 
        v-for="topic in keywords" 
        :key="topic" 
        @click="toggleKeywordSelection(topic)" 
        :class="{ 'selected': selectedKeywords.includes(topic) }">
        {{ topic }}
      </button>
    </div>
    
  <!-- 网络图视图 -->
  <div v-if="viewMode === 'network'" class="network-view-wrapper" ref="networkViewWrapper">
    <div v-if="isV3Pipeline && v3SpiralText" class="v3-spiral-banner">{{ v3SpiralText }}</div>
    <div class="network-svg-container" :class="{ 'is-v3': isV3Pipeline }">
      <div
        v-if="isV3Pipeline && v3Thermometer"
        class="v3-thermo v3-thermo-left"
        :title="v3Thermometer.subject_reason || ''"
      >
        <div class="v3-thermo-label">主体</div>
        <div class="v3-thermo-track">
          <div
            class="v3-thermo-fill"
            :style="{ height: Math.min(100, Math.max(0, Number(v3Thermometer.subject_score) || 0)) + '%' }"
          />
        </div>
        <div class="v3-thermo-score">{{ v3Thermometer.subject_score }}</div>
        <div v-if="v3Thermometer.subject_reason" class="v3-thermo-reason">{{ v3ThermometerSubjectReasonShort }}</div>
      </div>
    <div class="network-view-container" :style="{ height: computedContainerHeight }" ref="networkContainer">
      <div class="network-canvas-wrapper" ref="networkWrapper">
        <svg 
          ref="networkSvg" 
          class="network-svg"
          :viewBox="computedViewBox"
          preserveAspectRatio="xMidYMid meet"
          @mousemove="onNetworkMouseMove"
          @mouseleave="clearGraphHover">
          <!-- SVG滤镜定义（橙色阴影） -->
          <defs>
            <filter id="orangeGlow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur in="SourceAlpha" stdDeviation="5"/>
              <feOffset dx="0" dy="0" result="offsetblur"/>
              <feFlood flood-color="#ff8c00" flood-opacity="1.0"/>
              <feComposite in2="offsetblur" operator="in"/>
              <feMerge>
                <feMergeNode/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          
          <!-- 🔥 人与AI协作象限底纹 + 坐标轴（铺满当前 viewBox；节点位置仍为语义网络布局） -->
          <g class="axes" :style="{ pointerEvents: 'none' }">
            <!-- ② 盲区（左上：我不知道 × AI知道） -->
            <rect
              :x="axisCanvas.q2.x"
              :y="axisCanvas.q2.y"
              :width="axisCanvas.q2.w"
              :height="axisCanvas.q2.h"
              fill="#f0e8fc"
              opacity="0.42"
            />
            <!-- ① 共识区（右上：我知道 × AI知道） -->
            <rect
              :x="axisCanvas.q1.x"
              :y="axisCanvas.q1.y"
              :width="axisCanvas.q1.w"
              :height="axisCanvas.q1.h"
              fill="#e8f4fc"
              opacity="0.42"
            />
            <!-- ③ 未知区（左下：我不知道 × AI不知道） -->
            <rect
              :x="axisCanvas.q3.x"
              :y="axisCanvas.q3.y"
              :width="axisCanvas.q3.w"
              :height="axisCanvas.q3.h"
              fill="#e8f8f0"
              opacity="0.42"
            />
            <!-- ④ 隐藏区（右下：我知道 × AI不知道） -->
            <rect
              :x="axisCanvas.q4.x"
              :y="axisCanvas.q4.y"
              :width="axisCanvas.q4.w"
              :height="axisCanvas.q4.h"
              fill="#fff4e8"
              opacity="0.42"
            />

            <!-- 象限名 / 轴端名改画在节点之上，见下方 axis-edge-labels -->

            <!-- X轴（横轴铺满画布）：左=我/组不知道，右=我/组知道 -->
            <line
              :x1="axisCanvas.minX"
              :y1="axisCanvas.originY"
              :x2="axisCanvas.maxX"
              :y2="axisCanvas.originY"
              stroke="#999"
              stroke-width="1.5"
              opacity="0.8"
            />
            <!-- Y轴（纵轴铺满画布）：下=AI不知道，上=AI知道 -->
            <line
              :x1="axisCanvas.originX"
              :y1="axisCanvas.maxY"
              :x2="axisCanvas.originX"
              :y2="axisCanvas.minY"
              stroke="#999"
              stroke-width="1.5"
              opacity="0.8"
            />

            <!-- X轴正向箭头（画布右缘） -->
            <polygon
              :points="`${axisCanvas.maxX},${axisCanvas.originY} ${axisCanvas.maxX - 10},${axisCanvas.originY - 5} ${axisCanvas.maxX - 10},${axisCanvas.originY + 5}`"
              fill="#999"
              opacity="0.8"
            />
            <!-- Y轴正向箭头（画布上缘） -->
            <polygon
              :points="`${axisCanvas.originX},${axisCanvas.minY} ${axisCanvas.originX - 5},${axisCanvas.minY + 10} ${axisCanvas.originX + 5},${axisCanvas.minY + 10}`"
              fill="#999"
              opacity="0.8"
            />

          </g>

          <!-- 等高圈：围着同一上级的子节点，按角度收成闭合虚线，不连成额外边 -->
          <g v-if="visibleContourRings.length" class="contour-rings" pointer-events="none">
            <path
              v-for="ring in visibleContourRings"
              :key="ring.id"
              class="contour-ring"
              :class="{ 'is-hot': contourRingHot(ring), 'is-dim': contourRingDim(ring) }"
              :data-contour-id="ring.id"
              :d="ring.d"
              stroke-dasharray="9 6"
              stroke-linejoin="round"
            />
          </g>
          
          <!-- 连接线（透明热区便于右键细线） -->
          <g class="links">
            <path
              v-for="link in visibleLinks"
              :key="`hit-${link.source.id}-${link.target.id}`"
              :d="linkCurve(link)"
              stroke="transparent"
              stroke-width="12"
              fill="none"
              class="link-hit-area"
              :class="{ 'contour-dim': graphLinkDimmed(link) }"
              @mouseenter="highlightLink(link, $event)"
              @mouseleave="resetHighlight"
              @contextmenu.prevent="handleLinkRightClick(link, $event)"
            />
            <path
              v-for="link in visibleLinks"
              :key="`${link.source.id}-${link.target.id}`"
              :d="linkCurve(link)"
              fill="none"
              :stroke-width="link.width"
              :stroke="link.color"
              :opacity="quadrantLinkOpacity(link)"
              :stroke-dasharray="link.dasharray || null"
              class="link-line"
              :class="{ 'contour-dim': graphLinkDimmed(link) }"
              pointer-events="none"
            />
          </g>
          
          <!-- 连接线数量标记 -->
          <g class="link-labels" v-if="highlightedLink">
            <!-- 融合关系的简洁标记 -->
            <template v-if="highlightedLink.linkType === 'fusion'">
              <circle 
                :cx="(highlightedLink.source.x + highlightedLink.target.x) / 2" 
                :cy="(highlightedLink.source.y + highlightedLink.target.y) / 2"
                r="8"
                fill="#ff6b6b"
                stroke="#fff"
                stroke-width="1.5"
                class="fusion-link-marker"
              />
            </template>
            <!-- 普通连线使用原有样式；层次连边悬停显示强/中/普，共现连边仍显示共现次数 -->
            <template v-else>
              <circle 
                :cx="(highlightedLink.source.x + highlightedLink.target.x) / 2" 
                :cy="(highlightedLink.source.y + highlightedLink.target.y) / 2"
                r="12"
                fill="rgba(255, 255, 255, 0.9)"
                stroke="#493d8b"
                stroke-width="1.5"
                class="link-label-bg"
              />
              <text 
                :x="(highlightedLink.source.x + highlightedLink.target.x) / 2" 
                :y="(highlightedLink.source.y + highlightedLink.target.y) / 2 + 4"
                font-size="10"
                font-weight="bold"
                fill="#493d8b"
                text-anchor="middle"
                class="link-label-text"
              >
                {{ linkHoverLabel(highlightedLink) }}
              </text>
            </template>
          </g>
          
          <!-- 节点 -->
          <g class="nodes">
            <!-- 🔥 新节点箭头（放在节点组外面，使用绝对坐标，D/M/T类型新节点不显示箭头） -->
            <g
              v-for="node in nodes.filter(n => n.isNew && n.dmtLevel !== 'D' && n.dmtLevel !== 'M' && n.dmtLevel !== 'T')"
              :key="`arrow-${node.id}`"
              class="new-node-arrow"
            >
              <!-- 箭头线段（从左上角指向节点边缘） -->
              <line
                :x1="getArrowStart(node).x"
                :y1="getArrowStart(node).y"
                :x2="getArrowEnd(node).x"
                :y2="getArrowEnd(node).y"
                :stroke="getNodeFourColor(node)"
                stroke-width="2.5"
                stroke-linecap="round"
                pointer-events="none"
              />
              <!-- 箭头头部（V形） -->
              <polygon
                :points="`${getArrowEnd(node).x},${getArrowEnd(node).y} ${getArrowTipPoints(node).left.x},${getArrowTipPoints(node).left.y} ${getArrowTipPoints(node).right.x},${getArrowTipPoints(node).right.y}`"
                :fill="getNodeFourColor(node)"
                stroke="none"
                pointer-events="none"
              />
            </g>
            
            <g
              v-for="node in nodes"
              :key="node.id"
              :transform="`translate(${node.x},${node.y})`"
              class="node-group"
              :class="{ 
                'selected': selectedKeywords.includes(node.label),
                'highlighted': highlightedNode === node.id,
                'new-keyword': !!node.isNew,
                'contour-dim': graphNodeDimmed(node),
                'longitude-breath': longitudeNodeBreathing(node)
              }"
            >
              <!-- 三类知识外圈：部落两层 / 组织一层 / 传统无圈 -->
              <circle
                v-if="node.knowledgeType === 'trib'"
                :r="(node.radius || 10) + 8"
                fill="none"
                :stroke="node.isNew ? '#333333' : '#666'"
                :stroke-width="node.isNew ? node.strokeWidth : 2"
                :stroke-dasharray="node.isNew ? '4,4' : '0'"
                :filter="node.isNew ? 'url(#orangeGlow)' : 'none'"
                class="knowledge-ring knowledge-ring-outer"
                pointer-events="none"
              />
              <circle
                v-if="node.knowledgeType === 'trib'"
                :r="(node.radius || 10) + 4"
                fill="none"
                :stroke="node.isNew ? '#333333' : '#666'"
                :stroke-width="node.isNew ? node.strokeWidth : 2"
                :stroke-dasharray="node.isNew ? '4,4' : '0'"
                :filter="node.isNew ? 'url(#orangeGlow)' : 'none'"
                class="knowledge-ring knowledge-ring-inner"
                pointer-events="none"
              />
              <circle
                v-if="node.knowledgeType === 'org'"
                :r="(node.radius || 10) + 4"
                fill="none"
                :stroke="node.isNew ? '#333333' : '#666'"
                :stroke-width="node.isNew ? node.strokeWidth : 2"
                :stroke-dasharray="node.isNew ? '4,4' : '0'"
                :filter="node.isNew ? 'url(#orangeGlow)' : 'none'"
                class="knowledge-ring"
                pointer-events="none"
              />
              
              <rect
                v-if="node.pending || node.pendingFaded"
                :x="-((node.radius || 10) + 10)"
                :y="-((node.radius || 10) + 10)"
                :width="((node.radius || 10) + 10) * 2"
                :height="((node.radius || 10) + 10) * 2"
                fill="none"
                :stroke="node.pendingFaded ? '#b0b0b0' : '#888'"
                stroke-dasharray="4,3"
                :stroke-width="node.pendingFaded ? 1 : 1.5"
                :opacity="node.pendingFaded ? 0.42 : 0.95"
                pointer-events="none"
              />
              <circle
                v-if="longitudeNodeBreathing(node)"
                class="longitude-breath-halo"
                :r="(node.radius || 10) + 7"
                fill="none"
                :stroke="longitudeBreathColor()"
                stroke-width="2.4"
                pointer-events="none"
              />
              <circle
                :r="node.radius"
                :fill="node.color"
                :stroke="node.stroke"
                :stroke-width="node.strokeWidth"
                class="node-circle"
                @click="handleNodeClick(node, $event)"
                @mouseenter="showTooltip(node, $event)"
                @mouseleave="hideTooltip"
                @mouseover.stop
                @mousedown="startDrag(node, $event)"
                @contextmenu.prevent="handleRightClick(node, $event)"
              />
              
              <!-- 节点圆圈内的数字：v2=卡频；v3=文档命中+卡片模糊命中；大本体不显示 -->
              <text
                v-if="!isOntologyScopeMode"
                class="node-count-text"
                :font-size="node.countFontSize"
                :fill="node.countTextColor"
                text-anchor="middle"
                dy=".35em"
                :x="0"
                :y="0"
              >
                {{ node.cardCount }}
              </text>
              
              <!-- 节点标签（可编辑）- 使用绝对定位显示在节点上方 -->
              <foreignObject
                v-if="editingNode && editingNode.id === node.id"
                :x="getForeignObjectX(node)"
                :y="getForeignObjectY(node)"
                :width="Math.max(getForeignObjectWidth(node), 120)"
                :height="Math.max(getForeignObjectHeight(node), 30)"
              >
                <div class="keyword-edit-wrapper">
                  <input
                    v-model="editingText"
                    @blur="finishEdit(node)"
                    @keyup.enter="finishEdit(node)"
                    @keyup.esc="cancelEdit"
                    class="keyword-edit-input"
                    :style="{ fontSize: Math.max((node.fontSize || 10), 12) + 'px' }"
                    maxlength="8"
                    autofocus
                  />
                </div>
              </foreignObject>
              <text
                v-else
                class="node-label"
                :font-size="node.labelFontSize || node.fontSize || 10"
                :font-weight="node.labelWeight || 400"
                :fill="node.textColor || '#333'"
                text-anchor="middle"
                dy=".35em"
                :y="(node.radius || 10) + (node.labelFontSize || 10)"
                @contextmenu.prevent="handleRightClick(node, $event)"
              >
                {{ node.label }}
              </text>
            </g>
          </g>

          <!-- 象限名、轴端名：贴画布四边，叠在节点之上避免被挡住 -->
          <g class="axis-edge-labels" :style="{ pointerEvents: 'none' }">
            <text
              class="axis-edge-text"
              :x="axisCanvas.midX"
              :y="axisCanvas.minY + 26"
              font-size="15"
              fill="#555"
              text-anchor="middle"
              font-weight="600"
            >人机共生的协作象限</text>

            <text class="axis-edge-text" :x="axisCanvas.labels.q2.x" :y="axisCanvas.labels.q2.y" font-size="15" fill="#6b5b95" text-anchor="start" font-weight="700">② 盲区</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.q2.x" :y="axisCanvas.labels.q2.y + 16" font-size="11" fill="#7a6a9a" text-anchor="start">→ 让AI教你</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.q1.x" :y="axisCanvas.labels.q1.y" font-size="15" fill="#3d6f9c" text-anchor="end" font-weight="700">① 共识区</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.q1.x" :y="axisCanvas.labels.q1.y + 16" font-size="11" fill="#4a7fad" text-anchor="end">→ 让AI执行</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.q3.x" :y="axisCanvas.labels.q3.y - 16" font-size="15" fill="#3d7a5c" text-anchor="start" font-weight="700">③ 未知区</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.q3.x" :y="axisCanvas.labels.q3.y" font-size="11" fill="#4a8a6a" text-anchor="start">→ 跟AI共创</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.q4.x" :y="axisCanvas.labels.q4.y - 16" font-size="15" fill="#b07a3a" text-anchor="end" font-weight="700">④ 隐藏区</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.q4.x" :y="axisCanvas.labels.q4.y" font-size="11" fill="#c08a4a" text-anchor="end">→ 你告诉AI</text>

            <text class="axis-edge-text" :x="axisCanvas.labels.xNeg.x" :y="axisCanvas.labels.xNeg.y" font-size="13" fill="#555" text-anchor="start" font-weight="600">{{ axisXUnknownLabel }}</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.xPos.x" :y="axisCanvas.labels.xPos.y" font-size="13" fill="#555" text-anchor="end" font-weight="600">{{ axisXKnowLabel }}</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.yPos.x" :y="axisCanvas.labels.yPos.y" font-size="13" fill="#555" text-anchor="start" font-weight="600">AI 知道</text>
            <text class="axis-edge-text" :x="axisCanvas.labels.yNeg.x" :y="axisCanvas.labels.yNeg.y" font-size="13" fill="#555" text-anchor="start" font-weight="600">AI 不知道</text>
          </g>
        </svg>
      </div>
      
      <!-- 融合关系工具提示 -->
      <div 
        v-if="fusionLinkTooltip.visible" 
        class="fusion-link-tooltip"
        :style="fusionLinkTooltip.style">
        <div class="fusion-link-tooltip-title">融合关系</div>
        <div class="fusion-link-tooltip-content" v-if="fusionLinkTooltip.data">
          <div><strong>融合关键词：</strong>{{ fusionLinkTooltip.data.fusedKeyword }}</div>
          <div><strong>来源：</strong>{{ fusionLinkTooltip.data.sourceKeyword }} + {{ fusionLinkTooltip.data.otherSourceKeyword }}</div>
        </div>
      </div>
      
      <!-- 节点工具提示 -->
      <div 
        v-if="tooltip.visible" 
        class="network-tooltip"
        :style="tooltip.style">
        <div class="tooltip-title">{{ tooltip.data?.label }}</div>
        <div class="tooltip-content">
          <template v-if="isOntologyScopeMode">
            <div v-if="tooltipOntologyAttrs(tooltip.data?.label).dmt">
              DMT: {{ tooltipOntologyAttrs(tooltip.data?.label).dmt }}
            </div>
            <div v-if="tooltipOntologyAttrs(tooltip.data?.label).color">
              四色: {{ tooltipOntologyAttrs(tooltip.data?.label).color }}
            </div>
            <div v-if="tooltipOntologyAttrs(tooltip.data?.label).kt">
              三类知识: {{ tooltipOntologyAttrs(tooltip.data?.label).kt }}
            </div>
          </template>
          <template v-else-if="isV3Pipeline">
            <div>统计合计: {{ tooltip.data?.cardCount || 0 }}（文档 {{ tooltip.data?.docHitCount || 0 }} + 卡片 {{ tooltip.data?.cardHitCount || 0 }}）</div>
            <div class="tooltip-hint">文档/卡片按语义词匹配度累计（非卡频出图）</div>
          </template>
          <div v-else>含此关键词的卡片: {{ tooltip.data?.cardCount }} 张</div>
          <div v-if="tooltip.data?.level != null && tooltip.data?.level !== ''">层级: {{ tooltip.data.level }}</div>
          <div v-if="tooltip.data?.quadrant">象限: {{ tooltip.data.quadrant }}</div>
          <div v-if="tooltip.data?.pending">状态: 待确认</div>
          <div v-if="!isOntologyScopeMode && tooltip.data?.contributors && tooltip.data.contributors.length > 0">
            <span v-if="tooltip.data.isMultiWriter">贡献作者:</span>
            <span v-else>贡献阶段:</span>
            <div class="contributor-list">
              <div 
                v-for="contributor in tooltip.data.contributors" 
                :key="contributor.name"
                class="contributor-item">
                <div class="contributor-name">{{ contributor.name }}({{ contributor.count }})</div>
                <div class="contributor-stats">
                  <span 
                    class="stat-item" 
                    title="有四色DMT：带有四色或DMT属性的卡片数占该贡献者总卡片数的比例。数值越高，说明该贡献者的卡片被标注的比例越高。">
                    有四色DMT: {{ (contributor.dmtRatio * 100).toFixed(0) }}%
                  </span>
                  <span 
                    class="stat-item" 
                    title="四色DMT高质：综合考虑高价值卡片（绿/紫/T类型）占比、颜色覆盖度（四种颜色覆盖种类）和DMT类型覆盖度（三种类型覆盖种类）的综合指标。数值越高，说明该贡献者的卡片质量越高、类型越丰富。">
                    四色DMT高质: {{ (contributor.highQualityRatio * 100).toFixed(0) }}%
                  </span>
                  <span 
                    class="stat-item" 
                    title="红蓝高分：加权平均分（基础分×0.3 + 深度分×0.7）超过3.5的卡片数占该贡献者总卡片数的比例。数值越高，说明该贡献者的卡片得分越高。">
                    红蓝高分: {{ (contributor.highScoreRatio * 100).toFixed(0) }}%
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div v-if="!isOntologyScopeMode && tooltip.data?.coOccurrences && tooltip.data.coOccurrences.length > 0">
            关联关键词:
            <div class="co-occurrence-list">
              <span 
                v-for="co in tooltip.data.coOccurrences.slice(0, 5)" 
                :key="co.keyword"
                class="co-occurrence-item">
                {{ co.keyword }}({{ co.count }})
              </span>
            </div>
          </div>
        </div>
      </div>
      </div>
      <div
        v-if="isV3Pipeline && v3Thermometer"
        class="v3-thermo v3-thermo-right"
        :title="v3Thermometer.ontology_reason || ''"
      >
        <div class="v3-thermo-label">本体</div>
        <div class="v3-thermo-track">
          <div
            class="v3-thermo-fill v3-thermo-fill-ontology"
            :style="{ height: Math.min(100, Math.max(0, Number(v3Thermometer.ontology_score) || 0)) + '%' }"
          />
        </div>
        <div class="v3-thermo-score">{{ v3Thermometer.ontology_score }}</div>
        <div v-if="v3Thermometer.ontology_reason" class="v3-thermo-reason">{{ v3ThermometerOntologyReasonShort }}</div>
      </div>
    </div>
    <div v-if="isV3Pipeline" class="v3-bottom-panel">
      <div v-if="v3CoreIssue" class="v3-issue">
        <div class="v3-bottom-label">核心问题</div>
        <div class="v3-bottom-text">{{ v3CoreIssue }}</div>
        <div v-if="v3CoreIssueAlternatives.length" class="v3-chip-row">
          <span class="v3-chip-hint">备选</span>
          <button
            v-for="(alt, idx) in v3CoreIssueAlternatives"
            :key="'ci-' + idx"
            type="button"
            class="v3-chip"
            @click="saveV3IntentPreference({ preferred_core_issue: alt })"
          >{{ alt }}</button>
        </div>
      </div>
      <div v-if="isV3Pipeline" class="v3-issue">
        <div class="v3-bottom-label">子问题</div>
        <ol v-if="v3SubIssues.length" class="v3-sub-list">
          <li v-for="(q, idx) in v3SubIssues" :key="'sub-' + idx">
            <span class="v3-sub-text">{{ q }}</span>
            <span class="v3-row-actions">
              <button type="button" class="v3-mini-btn" @click="openPanelEdit({ kind: 'sub_edit', index: idx, current: q })">改</button>
              <button type="button" class="v3-mini-btn" @click="deleteV3SubIssue(idx)">删</button>
            </span>
          </li>
        </ol>
        <button type="button" class="v3-mini-btn v3-mini-add" @click="openPanelEdit({ kind: 'sub_add' })">添加子问题</button>
      </div>
      <div v-if="v3ScaleSummaryLines.length" class="v3-bottom-scales">
        <div
          v-for="line in v3ScaleSummaryLines"
          :key="line.key"
          class="v3-scale-block"
          :class="'v3-scale-' + line.key"
        >
          <div class="v3-scale-title">{{ line.title }}</div>
          <div v-for="item in line.items" :key="line.key + '-' + item.key" class="v3-scale-item">
            <div class="v3-scale-item-head">
              <span class="v3-scale-badge" :class="'badge-' + item.key">{{ item.name }}</span>
              <button
                type="button"
                class="v3-mini-btn"
                @click="openPanelEdit({ kind: 'scale_edit', scaleKey: line.key, itemKey: item.key, itemName: item.name, current: item.text })"
              >改</button>
            </div>
            <span class="v3-scale-desc">{{ item.text }}</span>
          </div>
          <div v-if="line.alternatives.length" class="v3-chip-row">
            <span class="v3-chip-hint">刻度备选</span>
            <button
              v-for="chip in line.alternatives"
              :key="line.key + '-' + chip.id"
              type="button"
              class="v3-chip"
              :title="chip.label"
              @click="chip.onClick()"
            >{{ chip.label }}</button>
          </div>
        </div>
      </div>
      <div v-if="v3QuadrantMeaningLines.length" class="v3-quadrant-panel">
        <div class="v3-bottom-label">本子四象限</div>
        <div class="v3-bottom-scales v3-quadrant-scales">
          <div
            v-for="line in v3QuadrantMeaningLines"
            :key="'qmean-' + line.key"
            class="v3-scale-block"
          >
            <div class="v3-scale-item-head">
              <div class="v3-scale-title">{{ line.title }}</div>
              <button
                type="button"
                class="v3-mini-btn"
                @click="openPanelEdit({ kind: 'quadrant_edit', itemKey: line.key, itemName: line.title, current: line.text })"
              >改</button>
            </div>
            <div class="v3-quadrant-rule">{{ line.rule }}</div>
            <div v-if="line.text" class="v3-scale-desc">{{ line.text }}</div>
          </div>
        </div>
      </div>
      <div v-if="v3TopAlternativeTiers.length" class="v3-top-block">
        <div
          v-for="tier in v3TopAlternativeTiers"
          :key="'top-tier-' + tier.key"
          class="v3-top-row"
        >
          <span class="v3-bottom-label">{{ tier.label }}</span>
          <div v-if="tier.current.length" class="v3-chip-row">
            <span class="v3-chip-hint">现有</span>
            <span
              v-for="(word, idx) in tier.current"
              :key="'top-cur-' + tier.key + '-' + idx"
              class="v3-chip v3-chip-current"
            >{{ word }}</span>
          </div>
          <div v-if="tier.words.length" class="v3-chip-row">
            <span class="v3-chip-hint">备选</span>
            <button
              v-for="(word, idx) in tier.words"
              :key="'top-' + tier.key + '-' + idx"
              type="button"
              class="v3-chip"
              @click="applyV3TopAlternative(tier.key, word)"
            >{{ word }}</button>
          </div>
        </div>
      </div>
    </div>
    </div>
    
    <!-- 🔥 右键菜单 -->
    <div 
      v-if="contextMenuVisible"
      class="context-menu"
      :style="{
        position: 'fixed',
        left: contextMenuPosition.x + 'px',
        top: contextMenuPosition.y + 'px',
        zIndex: 10000
      }"
      @click.stop
    >
      <div class="context-menu-item" @click="handleEditKeyword">
        <span>✏️ 修改关键词</span>
      </div>
      <div class="context-menu-item" @click="handleEditFourColor">
        <span>🎨 修改四色属性</span>
      </div>
      <div class="context-menu-item" @click="handleEditDMT">
        <span>📊 修改DMT属性</span>
      </div>
      <div class="context-menu-item" @click="handleEditKnowledgeType">
        <span>📚 修改三类知识属性</span>
      </div>
      <template v-if="!isOntologyScopeMode">
        <div class="context-menu-item" @click="handleGenerateOrUpdatePermanentCard">
          <span>🔄 {{ hasPermanentCard() ? '更新' : '生成' }}关键词神经元永久卡</span>
        </div>
        <div class="context-menu-item" v-if="hasPermanentCard()" @click="handleDeletePermanentCard" style="color: #f56c6c;">
          <span>🗑️ 删除关键词神经元永久卡</span>
        </div>
      </template>
    </div>

    <!-- 层次连边右键：调整关联程度 -->
    <div
      v-if="linkContextMenuVisible"
      class="context-menu link-strength-menu"
      :style="{
        position: 'fixed',
        left: linkContextMenuPosition.x + 'px',
        top: linkContextMenuPosition.y + 'px',
        zIndex: 10000
      }"
      @click.stop
    >
      <div class="context-menu-title">关联程度</div>
      <div
        v-for="opt in linkStrengthOptions"
        :key="opt.value"
        class="context-menu-item"
        :class="{ active: (linkContextMenuLink && linkContextMenuLink.linkStrength) === opt.value }"
        @click="setLinkStrength(opt.value)"
      >
        <span>{{ opt.label }}</span>
        <span v-if="(linkContextMenuLink && linkContextMenuLink.linkStrength) === opt.value" class="context-menu-check">✓</span>
      </div>
    </div>

    <!-- v3 Top 备选：用户指定替换该档中的哪个现有词 -->
    <div
      v-if="showTopReplaceDialog"
      class="color-dmt-dialog-overlay"
      @click.self="closeTopReplaceDialog"
    >
      <div class="color-dmt-dialog v3-pending-dialog" @click.stop>
        <div class="dialog-header">
          <h3>用备选「{{ topReplaceAltWord }}」替换哪个{{ topReplaceTierLabel }}词？</h3>
          <button class="dialog-close" @click="closeTopReplaceDialog">×</button>
        </div>
        <div class="dialog-content">
          <p class="v3-top-replace-hint">
            请从当前{{ topReplaceTierLabel }}里选一个意思最接近、你想换成更好表述的词；点取消则不做替换。
          </p>
          <div class="dialog-options v3-pending-options">
            <button
              v-for="(w, idx) in topReplaceCandidates"
              :key="'top-repl-' + idx"
              type="button"
              class="dialog-option-btn v3-pending-option-btn"
              :class="{ selected: topReplaceSelected === w }"
              @click="topReplaceSelected = w"
            >
              <span class="v3-pending-option-label">{{ w }}</span>
            </button>
          </div>
          <div class="v3-pending-actions">
            <button type="button" class="dialog-option-btn" @click="closeTopReplaceDialog">取消</button>
            <button
              type="button"
              class="dialog-option-btn"
              :disabled="topReplaceSaving || !topReplaceSelected"
              @click="confirmV3TopAlternativeReplace"
            >{{ topReplaceSaving ? '替换中…' : '确认替换' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 子问题 / 刻度说明：点选或手写 -->
    <div
      v-if="showPanelEditDialog"
      class="color-dmt-dialog-overlay"
      @click.self="closePanelEditDialog"
    >
      <div class="color-dmt-dialog v3-pending-dialog" @click.stop>
        <div class="dialog-header">
          <h3>{{ panelEditTitle }}</h3>
          <button class="dialog-close" @click="closePanelEditDialog">×</button>
        </div>
        <div class="dialog-content">
          <p class="v3-pending-lead">{{ panelEditLead }}</p>
          <p v-if="panelEditKind !== 'sub_add' && panelEditCurrent" class="v3-pending-lead">原文：{{ panelEditCurrent }}</p>
          <p v-if="panelEditLoading" class="v3-pending-lead">{{ panelEditKind === 'sub_add' ? '正在按本子现有内容准备可点的说法…' : '正在按原文做精修…' }}</p>
          <div v-else-if="panelEditOptions.length" class="dialog-options v3-pending-options">
            <button
              v-for="(opt, idx) in panelEditOptions"
              :key="'panel-opt-' + idx"
              type="button"
              class="dialog-option-btn v3-pending-option-btn"
              :class="{ selected: panelEditPicked === opt }"
              @click="pickPanelEditOption(opt)"
            >
              <span class="v3-pending-option-index">{{ idx + 1 }}</span>
              <span class="v3-pending-option-label">{{ opt }}</span>
            </button>
          </div>
          <p v-else class="v3-pending-lead">这次没有生成可点的说法，可以直接在下面写。</p>
          <div class="v3-pending-custom">
            <label>{{ panelEditKind === 'sub_add' ? '采用的说法（点上面一条会填到这里，也可以自己改）' : '修改稿（点上面一条会把精修后的全文填到这里，也可以再改）' }}</label>
            <textarea v-model="panelEditDraft" class="keyword-edit-input v3-panel-draft" rows="4" @input="panelEditPicked = ''" />
          </div>
          <div class="v3-pending-actions">
            <button type="button" class="dialog-option-btn" @click="closePanelEditDialog">取消</button>
            <button
              type="button"
              class="dialog-option-btn v3-pending-confirm"
              :disabled="panelEditSaving || !panelEditDraft.trim()"
              @click="confirmPanelEdit"
            >{{ panelEditSaving ? '保存中…' : '确认' }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- v3 存疑节点确认 -->
    <div
      v-if="showPendingDialog"
      class="color-dmt-dialog-overlay"
      @click.self="closePendingDialog"
    >
      <div class="color-dmt-dialog v3-pending-dialog" @click.stop>
        <div class="dialog-header">
          <h3>「{{ pendingDialogNode?.label }}」还没定</h3>
          <button class="dialog-close" @click="closePendingDialog">×</button>
        </div>
        <div class="dialog-content">
          <p class="v3-pending-lead">虚线框表示这个词还有几件不同的事没定。下面按事情分开，不是同一道题的很多答案。一次只拍板一条。</p>
          <div
            v-for="group in pendingDialogGroups"
            :key="group.key"
            class="v3-pending-group"
          >
            <div class="v3-pending-group-title">{{ group.title }}</div>
            <p class="v3-pending-group-note">{{ group.note }}</p>
            <div class="dialog-options v3-pending-options">
              <button
                v-for="(opt, idx) in group.items"
                :key="group.key + '-' + idx"
                type="button"
                class="dialog-option-btn v3-pending-option-btn"
                :class="{ selected: pendingSelectedChoice && pendingSelectedChoice.id === opt.id }"
                @click="pendingSelectedChoice = opt; pendingCustomText = ''"
              >
                <span class="v3-pending-option-index">{{ idx + 1 }}</span>
                <span class="v3-pending-option-body">
                  <span class="v3-pending-option-label">{{ opt.label }}</span>
                  <span v-if="opt.effect" class="v3-pending-option-preview">{{ opt.effect }}</span>
                </span>
              </button>
            </div>
          </div>
          <p v-if="!pendingDialogOptionsList.length" class="v3-pending-lead">暂时没有备选说法，可以直接在下面写你的判断。</p>
          <div class="v3-pending-custom">
            <label>都不对，我自己写一句</label>
            <input v-model="pendingCustomText" type="text" class="keyword-edit-input" placeholder="用你自己的话说明这个词" @input="pendingSelectedChoice = null" />
          </div>
        </div>
        <div class="v3-pending-actions">
          <button type="button" class="dialog-option-btn" @click="closePendingDialog">取消</button>
          <button
            type="button"
            class="dialog-option-btn v3-pending-confirm"
            :disabled="pendingConfirmSaving || (!pendingSelectedChoice?.id && !pendingCustomText.trim())"
            @click="confirmPendingChoice"
          >{{ pendingConfirmSaving ? '提交中…' : '确认' }}</button>
        </div>
      </div>
    </div>
    
    <!-- 🔥 自定义四色属性选择对话框 -->
    <div 
      v-if="showColorDialog"
      class="color-dmt-dialog-overlay"
      @click.self="closeDialogs"
    >
      <div class="color-dmt-dialog" @click.stop>
        <div class="dialog-header">
          <h3>修改四色属性</h3>
          <button class="dialog-close" @click="closeDialogs">×</button>
        </div>
        <div class="dialog-content">
          <div class="dialog-current">
            当前：<span :style="{ color: dialogCurrentValue === 'R' ? '#dc143c' : dialogCurrentValue === 'B' ? '#1e90ff' : dialogCurrentValue === 'P' ? '#9370db' : dialogCurrentValue === 'G' ? '#3cb371' : '#999', fontWeight: 'bold' }">
              {{ dialogOptionNames[dialogCurrentValue] || '未设置' }}
            </span>
          </div>
          <div class="dialog-options">
            <button
              v-for="option in dialogOptions"
              :key="option"
              class="dialog-option-btn"
              :class="{ 'selected': option === dialogCurrentValue }"
              :style="{
                backgroundColor: option === 'R' ? '#dc143c' : option === 'B' ? '#1e90ff' : option === 'P' ? '#9370db' : option === 'G' ? '#3cb371' : '#ccc',
                color: 'white',
                border: option === dialogCurrentValue ? '3px solid #333' : '1px solid #ddd'
              }"
              @click="confirmDialogChoice(option)"
            >
              {{ option }}: {{ dialogOptionNames[option] }}
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 🔥 自定义DMT属性选择对话框 -->
    <div 
      v-if="showDMTDialog"
      class="color-dmt-dialog-overlay"
      @click.self="closeDialogs"
    >
      <div class="color-dmt-dialog" @click.stop>
        <div class="dialog-header">
          <h3>修改DMT属性</h3>
          <button class="dialog-close" @click="closeDialogs">×</button>
        </div>
        <div class="dialog-content">
          <div class="dialog-current">
            当前：<span style="font-weight: bold;">{{ dialogOptionNames[dialogCurrentValue] || '未设置' }}</span>
          </div>
          <div class="dialog-options">
            <button
              v-for="option in dialogOptions"
              :key="option"
              class="dialog-option-btn"
              :class="{ 'selected': option === dialogCurrentValue }"
              :style="{
                border: option === dialogCurrentValue ? '3px solid #333' : '1px solid #ddd'
              }"
              @click="confirmDialogChoice(option)"
            >
              {{ option }}: {{ dialogOptionNames[option] }}
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 🔥 三类知识属性选择对话框 -->
    <div 
      v-if="showKnowledgeDialog"
      class="color-dmt-dialog-overlay"
      @click.self="closeDialogs"
    >
      <div class="color-dmt-dialog" @click.stop>
        <div class="dialog-header">
          <h3>修改三类知识属性</h3>
          <button class="dialog-close" @click="closeDialogs">×</button>
        </div>
        <div class="dialog-content">
          <div class="dialog-current">
            当前：<span style="font-weight: bold;">{{ dialogOptionNames[dialogCurrentValue] || '未设置' }}</span>
          </div>
          <div class="dialog-options">
            <button
              v-for="option in dialogOptions"
              :key="option"
              class="dialog-option-btn"
              :class="{ 'selected': option === dialogCurrentValue }"
              :style="{
                border: option === dialogCurrentValue ? '3px solid #333' : '1px solid #ddd'
              }"
              @click="confirmDialogChoice(option)"
            >
              {{ option }}: {{ dialogOptionNames[option] }}
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 🔥 关键词融合对话框 -->
    <div 
      v-if="showFusionDialog"
      class="color-dmt-dialog-overlay"
      @click.self.prevent="cancelFusion"
      @mouseleave.stop
      @mouseout.stop
    >
      <div class="color-dmt-dialog fusion-dialog" @click.stop style="max-width: 1100px; width: 90%; max-height: 85vh; overflow: hidden; display: flex; flex-direction: column;">
        <div class="dialog-header">
          <h3>融合关键词节点</h3>
          <button class="dialog-close" @click="cancelFusion">×</button>
        </div>
        <div class="dialog-content" style="padding: 20px; flex: 1; display: flex; flex-direction: column; overflow: hidden;">
          <!-- 顶部提示和原关键词（紧凑显示） -->
          <div style="margin-bottom: 18px; padding-bottom: 12px; border-bottom: 1px solid #e0e0e0; flex-shrink: 0;">
            <p style="margin-bottom: 10px; color: #555; font-size: 13px; line-height: 1.5;">请从以下3个不同视角的融合关键词中选择一个，点击关键词名称、四色或DMT可直接编辑：</p>
            <div style="display: inline-flex; gap: 20px; padding: 6px 12px; background: #f0f4ff; border-radius: 6px;">
              <span style="font-weight: 500; color: #493d8b; font-size: 13px;">原关键词1: <strong>{{ fusionSourceKeyword1 }}</strong></span>
              <span style="font-weight: 500; color: #493d8b; font-size: 13px;">原关键词2: <strong>{{ fusionSourceKeyword2 }}</strong></span>
            </div>
          </div>
          
          <!-- 加载状态 -->
          <div v-if="isFusing && fusionKeywordOptions.length === 0" style="text-align: center; padding: 60px 20px; flex: 1; display: flex; align-items: center; justify-content: center; flex-direction: column;">
            <div style="color: #666; margin-bottom: 10px; font-size: 16px;">正在生成融合关键词选项...</div>
            <div style="color: #999; font-size: 13px;">请稍候</div>
          </div>
          
          <!-- 3个关键词选项（横向排列） -->
          <div v-if="!isFusing && fusionKeywordOptions.length > 0" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 20px; flex: 1; overflow-y: auto; min-height: 0;">
            <div 
              v-for="(option, index) in fusionKeywordOptions" 
              :key="index"
              class="keyword-option-card"
              :class="{ 'keyword-option-selected': selectedKeywordIndex === index, 'keyword-option-editing': editingKeywordIndex === index && editingField }"
              style="position: relative;"
            >
              <!-- 单独重做图标（如果该选项被编辑过） -->
              <div 
                v-if="option.hasBeenEdited && !isRegeneratingOption[index]" 
                @click.stop="regenerateSingleOption(index)"
                style="position: absolute; top: 12px; right: 12px; width: 24px; height: 24px; cursor: pointer; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: #f0f0f0; transition: all 0.2s; z-index: 10;"
                @mouseenter="$event.target.style.background = '#e0e0e0'; $event.target.style.transform = 'scale(1.1)'"
                @mouseleave="$event.target.style.background = '#f0f0f0'; $event.target.style.transform = 'scale(1)'"
                title="根据当前的四色/DMT/视角设置，重新生成此选项的关键词名"
              >
                <span style="font-size: 16px; color: #493d8b;">↻</span>
              </div>
              
              <!-- 单独重做加载状态 -->
              <div 
                v-if="isRegeneratingOption[index]"
                style="position: absolute; top: 12px; right: 12px; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; z-index: 10;"
              >
                <div style="width: 16px; height: 16px; border: 2px solid #493d8b; border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
              </div>
              
              <!-- 单选框 -->
              <div style="display: flex; align-items: center; margin-bottom: 12px; position: relative;">
                <input 
                  type="radio" 
                  :checked="selectedKeywordIndex === index"
                  @click.stop="selectKeywordOption(index)"
                  @change="selectKeywordOption(index)"
                  style="margin-right: 8px; cursor: pointer; width: 16px; height: 16px;"
                />
                <span style="font-weight: 600; color: #493d8b; font-size: 14px;">选项 {{ index + 1 }}</span>
                <span v-if="selectedKeywordIndex === index" style="position: absolute; right: 50px; color: #493d8b; font-size: 18px; font-weight: bold;">✓</span>
              </div>
              
              <!-- 关键词名称：编辑模式 -->
              <div v-if="editingKeywordIndex === index && editingField === 'keyword'" style="margin-bottom: 12px; width: 100%; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 14px; font-weight: 600; color: #666; white-space: nowrap;">新节点：</span>
                <input 
                  type="text"
                  :ref="`keywordInput_${index}`"
                  v-model="editingKeywordData.keyword"
                  @blur="saveEditField(index, 'keyword')"
                  @keyup.enter="saveEditField(index, 'keyword')"
                  @keyup.esc="cancelEditField(index)"
                  style="flex: 1; max-width: 100%; box-sizing: border-box; padding: 8px; border: 2px solid #493d8b; border-radius: 4px; font-size: 15px; font-weight: 600; outline: none;"
                  placeholder="请输入关键词"
                />
              </div>
              
              <!-- 关键词名称：显示模式（可点击编辑） -->
              <div v-else style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 14px; font-weight: 600; color: #666;">新节点：</span>
                <span 
                  @click.stop="startEditField(index, 'keyword')"
                  style="font-size: 16px; font-weight: 600; color: #333; cursor: pointer; padding: 4px 6px; border-radius: 4px; display: inline-block; transition: background 0.2s; word-break: break-word;"
                  @mouseenter="$event.target.style.background = '#f0f0f0'"
                  @mouseleave="$event.target.style.background = 'transparent'"
                >
                  {{ option.keyword }}
                </span>
              </div>
              
              <!-- 视角说明：编辑模式 -->
              <div v-if="editingKeywordIndex === index && editingField === 'perspective'" style="margin-bottom: 12px; width: 100%;">
                <div style="display: flex; align-items: flex-start; gap: 8px;">
                  <span style="font-size: 14px; font-weight: 600; color: #666; white-space: nowrap; padding-top: 8px;">视角：</span>
                  <textarea
                    :ref="`perspectiveInput_${index}`"
                    v-model="editingKeywordData.perspective"
                    @blur="saveEditField(index, 'perspective')"
                    @keyup.ctrl.enter="saveEditField(index, 'perspective')"
                    @keyup.esc="cancelEditField(index)"
                    style="flex: 1; max-width: 100%; box-sizing: border-box; padding: 8px; border: 2px solid #493d8b; border-radius: 4px; font-size: 12px; outline: none; resize: vertical; min-height: 60px; line-height: 1.4;"
                    placeholder="请输入视角说明"
                  />
                </div>
              </div>
              
              <!-- 视角说明：显示模式（可点击编辑） -->
              <div v-else-if="option.perspective && !(editingKeywordIndex === index && editingField === 'keyword')" style="margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 14px; font-weight: 600; color: #666; white-space: nowrap;">视角：</span>
                <div 
                  @click.stop="startEditField(index, 'perspective')"
                  style="flex: 1; color: #666; font-size: 12px; line-height: 1.4; min-height: 32px; cursor: pointer; padding: 4px 6px; border-radius: 4px; transition: background 0.2s;"
                  @mouseenter="$event.target.style.background = '#f0f0f0'"
                  @mouseleave="$event.target.style.background = 'transparent'"
                >
                  {{ option.perspective }}
                </div>
              </div>
              
              <!-- 属性区域 -->
              <div style="display: flex; flex-direction: column; gap: 8px;">
                <!-- 四色类型 -->
                <div>
                  <span style="font-size: 12px; color: #888; margin-right: 6px;">四色语境：</span>
                  <!-- 编辑模式 -->
                  <select 
                    v-if="editingKeywordIndex === index && editingField === 'four_color_type'"
                    :ref="`colorSelect_${index}`"
                    v-model="editingKeywordData.four_color_type"
                    @change="saveEditField(index, 'four_color_type')"
                    @blur="saveEditField(index, 'four_color_type')"
                    style="width: auto; min-width: 60px; max-width: 100%; box-sizing: border-box; padding: 4px 6px; border: 2px solid #493d8b; border-radius: 4px; font-size: 12px; font-weight: 500; cursor: pointer; outline: none;"
                  >
                    <option value="R">红</option>
                    <option value="B">蓝</option>
                    <option value="P">紫</option>
                    <option value="G">绿</option>
                  </select>
                  <!-- 显示模式（可点击编辑） -->
                  <span 
                    v-else
                    @click.stop="startEditField(index, 'four_color_type')"
                    class="color-badge"
                    :class="`color-badge-${option.four_color_type}`"
                    style="padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 500; cursor: pointer; display: inline-block; transition: transform 0.2s, box-shadow 0.2s;"
                    @mouseenter="$event.target.style.transform = 'scale(1.05)'; $event.target.style.boxShadow = '0 2px 6px rgba(0,0,0,0.2)'"
                    @mouseleave="$event.target.style.transform = 'scale(1)'; $event.target.style.boxShadow = 'none'"
                  >
                    {{ option.four_color_type === 'R' ? '红' : option.four_color_type === 'B' ? '蓝' : option.four_color_type === 'G' ? '绿' : '紫' }}
                  </span>
                </div>
                
                <!-- DMT层次 -->
                <div>
                  <span style="font-size: 12px; color: #888; margin-right: 6px;">DMT粒度：</span>
                  <!-- 编辑模式 -->
                  <select 
                    v-if="editingKeywordIndex === index && editingField === 'dmt_level'"
                    :ref="`dmtSelect_${index}`"
                    v-model="editingKeywordData.dmt_level"
                    @change="saveEditField(index, 'dmt_level')"
                    @blur="saveEditField(index, 'dmt_level')"
                    style="width: auto; min-width: 50px; max-width: 100%; box-sizing: border-box; padding: 4px 6px; background: #e8e8e8; border: 2px solid #493d8b; border-radius: 4px; font-size: 12px; font-weight: 500; cursor: pointer; outline: none;"
                  >
                    <option value="D">D</option>
                    <option value="M">M</option>
                    <option value="T">T</option>
                  </select>
                  <!-- 显示模式（可点击编辑） -->
                  <span 
                    v-else
                    @click.stop="startEditField(index, 'dmt_level')"
                    style="padding: 4px 10px; background: #e8e8e8; border-radius: 4px; font-size: 12px; font-weight: 500; cursor: pointer; display: inline-block; transition: transform 0.2s, box-shadow 0.2s, background 0.2s;"
                    @mouseenter="$event.target.style.transform = 'scale(1.05)'; $event.target.style.background = '#d0d0d0'; $event.target.style.boxShadow = '0 2px 6px rgba(0,0,0,0.2)'"
                    @mouseleave="$event.target.style.transform = 'scale(1)'; $event.target.style.background = '#e8e8e8'; $event.target.style.boxShadow = 'none'"
                  >
                    {{ option.dmt_level }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          
          <div v-if="!isFusing && fusionKeywordOptions.length > 0" style="display: flex; flex-direction: row; justify-content: flex-end; gap: 12px; margin-top: 15px; padding-top: 15px; border-top: 1px solid #e0e0e0; flex-shrink: 0;">
            <button 
              class="dialog-option-btn"
              @click="cancelFusion"
              :disabled="isFusing || isRegeneratingAll"
              style="padding: 8px 20px; background: #ccc; color: #333; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background 0.2s; white-space: nowrap;"
              :style="{ opacity: (isFusing || isRegeneratingAll) ? 0.6 : 1, cursor: (isFusing || isRegeneratingAll) ? 'not-allowed' : 'pointer' }"
              @mouseenter="handleCancelButtonMouseEnter"
              @mouseleave="handleCancelButtonMouseLeave"
            >
              取消
            </button>
            <button 
              class="dialog-option-btn"
              @click="regenerateAllOptions"
              :disabled="isFusing || isRegeneratingAll"
              style="padding: 8px 20px; background: #7a6ba8; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background 0.2s; white-space: nowrap;"
              :style="{ opacity: (isFusing || isRegeneratingAll) ? 0.6 : 1, cursor: (isFusing || isRegeneratingAll) ? 'not-allowed' : 'pointer' }"
              @mouseenter="handleRegenerateButtonMouseEnter"
              @mouseleave="handleRegenerateButtonMouseLeave"
            >
              {{ isRegeneratingAll ? '重新生成中...' : '整体重来一遍' }}
            </button>
            <button 
              class="dialog-option-btn"
              @click="confirmSelectedKeyword"
              :disabled="isFusing || selectedKeywordIndex === -1 || isRegeneratingAll"
              style="padding: 8px 20px; background: #493d8b; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 500; transition: background 0.2s; white-space: nowrap;"
              :style="{ opacity: (isFusing || selectedKeywordIndex === -1 || isRegeneratingAll) ? 0.6 : 1, cursor: (isFusing || selectedKeywordIndex === -1 || isRegeneratingAll) ? 'not-allowed' : 'pointer' }"
              @mouseenter="handleConfirmButtonMouseEnter"
              @mouseleave="handleConfirmButtonMouseLeave"
            >
              {{ isFusing ? '生成中...' : '确认并生成永久卡片' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import "../d3.min.js";
import html2canvas from 'html2canvas';
import { semantic_intent_preference, semantic_confirm_pending, semantic_top_alternative_replace, semantic_panel_suggest } from '@/api/card/get_card';

const DEFAULT_NODE_DISPLAY_LIMIT = 30;
const QUADRANT_VIEW_KEY = 'keywordNetworkQuadrantView';

function readQuadrantPicture() {
  try {
    if (typeof window !== 'undefined' && window.__NKCN_QUADRANT_PICTURE
      && window.__NKCN_QUADRANT_PICTURE.positions
      && window.__NKCN_QUADRANT_PICTURE.frame) {
      return window.__NKCN_QUADRANT_PICTURE;
    }
  } catch (e) { /* 忽略 */ }
  try {
    const direct = localStorage.getItem(QUADRANT_VIEW_KEY);
    if (direct) {
      const data = JSON.parse(direct);
      if (data && data.positions && data.frame) return data;
    }
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (!key || key.indexOf('keywordNetworkQuadrantView') !== 0 || key === QUADRANT_VIEW_KEY) continue;
      const data = JSON.parse(localStorage.getItem(key) || 'null');
      if (data && data.positions && data.frame) return data;
    }
  } catch (e) { /* 读不到就当没有 */ }
  return null;
}

function writeQuadrantPicture(picture) {
  try {
    if (typeof window !== 'undefined') window.__NKCN_QUADRANT_PICTURE = picture;
  } catch (e) { /* 忽略 */ }
  try {
    localStorage.setItem(QUADRANT_VIEW_KEY, JSON.stringify(picture));
    localStorage.setItem('keywordNetworkQuadrantMode', '1');
  } catch (e) { /* 存不下时，这次页面里仍用内存里的那份 */ }
}

function clearQuadrantPicture() {
  try {
    if (typeof window !== 'undefined') window.__NKCN_QUADRANT_PICTURE = null;
  } catch (e) { /* 忽略 */ }
  try {
    const doomed = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key && (key.indexOf('keywordNetworkQuadrantView') === 0 || key.indexOf('keywordNetworkQuadrantMode') === 0)) {
        doomed.push(key);
      }
    }
    doomed.forEach((key) => localStorage.removeItem(key));
  } catch (e) { /* 清不掉就留着 */ }
}
const MIN_NODE_DISPLAY_OPTION = 1;
const MAX_NODE_DISPLAY_OPTION_DEFAULT = 100;
const MAX_NODE_DISPLAY_OPTION_V2 = 200;
const RECOMMENDED_NODE_LIMIT = 100;
const ANALYSIS_CARD_POOL_CAP = 60;
const KEYWORD_PICK_STRATEGIES = {
  default: 'default',
  top3: 'top3',
  top5: 'top5',
};

export default {
  name: 'KeywordNetworkGraph',
  props: {
    keywords: {
      type: Array,
      default: () => []
    },
    cards: {
      type: Array,
      default: () => []
    },
    selectedKeywords: {
      type: Array,
      default: () => []
    },
    filterStrategy: {
      type: String,
      default: 'union', // 默认策略是并集
      validator: (value) => ['union', 'intersection'].includes(value)
    },
    keywordFourColorDMT: {
      type: Object,
      default: () => ({})
    },
    initialKeywords: {
      type: Array,
      default: () => []
    },
    sceneName: {
      type: String,
      default: ''
    },
    authorFilter: {
      type: String,
      default: ''
    },
    keywordFusionRelations: {
      type: Object,
      default: () => ({})
    },
    tribalKeywords: {
      type: Array,
      default: () => []
    },
    semanticReorganizeMeta: {
      type: Object,
      default: () => ({})
    },
    /** 大本体作用域：scene / task_cluster；空则走本子内 API */
    ontologyScopeType: {
      type: String,
      default: ''
    },
    ontologyScopeId: {
      type: [String, Number],
      default: ''
    }
  },
  data() {
    const cachedQuad = readQuadrantPicture();
    return {
      viewMode: 'network', // 'flat' 或 'network'
      svgWidth: 800,
      svgHeight: 500,
      nodes: [],
      links: [],
      simulation: null,
      tooltip: {
        visible: false,
        data: null,
        style: {}
      },
      highlightedNode: null,
      highlightedLink: null,
      fusionLinkTooltip: {
        visible: false,
        style: {},
        data: null
      },
      draggedNode: null,
      dragOffset: { x: 0, y: 0 },
      // 布局稳定性相关
      layoutSeed: 42, // 固定随机种子
      savedPositions: {}, // 保存的节点位置
      quadrantPlaceMode: !!(cachedQuad && cachedQuad.frame),
      quadrantFrame: (cachedQuad && cachedQuad.frame) || null,
      forceLayoutSnapshot: (cachedQuad && cachedQuad.force) || null,
      // 工具提示防抖
      tooltipTimer: null,
      lastTooltipPosition: { x: 0, y: 0 },
      // 容器尺寸
      containerWidth: 800, // 默认宽度
      // 基准viewBox范围（保存初始稳定布局后的viewBox范围，用于重置时保持一致的显示大小）
      baseViewBoxBounds: null,
      // 本地筛选策略状态（用于按钮显示，与 prop 同步）
      localFilterStrategy: 'union',
      // 🔥 存储关键词四色DMT数据的纯对象版本
      keywordFourColorDMTData: {},
      // 🔥 记录本地已更新的关键词（通过API更新过的），避免被覆盖（暴露给父组件检查）
      locallyUpdatedKeywords: new Set(),
      // 🔥 首次加载重置定时器
      firstLoadResetTimer: null,
      // 🔥 关键词编辑相关
      editingNode: null,
      editingText: '',
      // 🔥 拖拽状态控制
      isDragging: false,
      dragStartTime: 0,
      dragSaveTimer: null, // 拖拽保存防抖定时器
      dragAnimationFrame: null, // 拖拽动画帧
      justEndedDrag: false, // 🔥 标记刚刚结束拖拽，用于防止触发点击事件
      dragStartPos: null, // 🔥 拖拽开始时的位置
      // 🔥 右键菜单相关
      contextMenuVisible: false,
      contextMenuNode: null,
      contextMenuPosition: { x: 0, y: 0 },
      // 层次连边右键：调整关联程度
      linkContextMenuVisible: false,
      linkContextMenuLink: null,
      linkContextMenuPosition: { x: 0, y: 0 },
      linkStrengthOptions: [
        { value: '强', label: '强' },
        { value: '强中', label: '强中' },
        { value: '普通', label: '普通' }
      ],
      linkStrengthSaving: false,
      _skipSemanticMetaReinit: false,
      // 🔥 自定义选择对话框
      showColorDialog: false,
      // 🔥 关键词重命名加载状态
      isRenamingKeyword: false,
      renamingKeyword: '',
      showDMTDialog: false,
      showKnowledgeDialog: false,
      dialogKeyword: null,
      dialogCurrentValue: '',
      dialogOptions: [],
      dialogOptionNames: {},
      dialogType: '', // 'color' | 'dmt' | 'knowledge'
      // 🔥 关键词融合相关
      showFusionDialog: false,
      fusionSourceKeyword1: '',
      fusionSourceKeyword2: '',
      isFusing: false,
      // 🔥 融合关键词选项
      fusionKeywordOptions: [], // [{keyword, four_color_type, dmt_level, perspective, hasBeenEdited}]
      editingKeywordIndex: -1, // 正在编辑的关键词索引
      editingKeywordData: { keyword: '', four_color_type: 'P', dmt_level: 'M', perspective: '' }, // 编辑中的数据
      selectedKeywordIndex: -1, // 用户选择的关键词索引
      isRegeneratingAll: false, // 是否正在整体重新生成
      isRegeneratingOption: {}, // {index: bool} 是否正在单独重新生成某个选项
      nodeDisplayLimit: DEFAULT_NODE_DISPLAY_LIMIT,
      showNodeCountDialog: false,
      showContourLinks: false,
      hoveredContourId: null,
      showLongitudeLinks: false,
      hoveredLongitudeId: null,
      exportingNetworkPng: false,
      showExportGraphDialog: false,
      keywordPickStrategy: KEYWORD_PICK_STRATEGIES.default,
      showKeywordPickStrategyDialog: false,
      showPendingDialog: false,
      pendingDialogNode: null,
      pendingSelectedChoice: null,
      pendingCustomText: '',
      pendingConfirmSaving: false,
      showTopReplaceDialog: false,
      topReplaceTierKey: '',
      topReplaceAltWord: '',
      topReplaceCandidates: [],
      topReplaceSelected: '',
      topReplaceSaving: false,
      showPanelEditDialog: false,
      panelEditKind: '',
      panelEditIndex: -1,
      panelEditScaleKey: '',
      panelEditItemKey: '',
      panelEditItemName: '',
      panelEditCurrent: '',
      panelEditDraft: '',
      panelEditPicked: '',
      panelEditOptions: [],
      panelEditLoading: false,
      panelEditSaving: false,
    }
  },
  watch: {
    keywords: {
      handler(newKeywords, oldKeywords) {
        if (this.viewMode === 'network') {
          // 🔥 增量更新：只添加新节点，删除消失的节点，不改变已有节点位置
          this.incrementalUpdateNodes(newKeywords, oldKeywords);
        }
      },
      immediate: false
    },
    cards: {
      handler() {
        if (this.viewMode === 'network') {
          this.$nextTick(() => {
            this.initializeNetwork();
          });
        }
      },
      immediate: false
    },
    authorFilter: {
      handler() {
        // 🔥 作者筛选变化时，重新初始化网络图
        if (this.viewMode === 'network') {
          this.$nextTick(() => {
            this.initializeNetwork();
          });
        }
      },
      immediate: false
    },
    selectedKeywords: {
      handler(newVal, oldVal) {
        // 当selectedKeywords改变时，更新节点的颜色状态
        if (this.nodes && this.nodes.length > 0) {
          // 计算最小和最大卡片数（用于颜色计算）
          const counts = this.nodes.map(node => node.cardCount || 0);
          const minCount = Math.min(...counts, 1);
          const maxCount = Math.max(...counts, 1);
          
          this.nodes.forEach(node => {
            const isSelected = newVal.includes(node.label);
            // 使用新的颜色计算方法，根据重要性更新颜色
            const colors = this.getNodeColors(
              node.label, // 🔥 传入关键词
              node.cardCount || 0, 
              minCount, 
              maxCount, 
              isSelected
            );
            // 直接修改节点属性，触发响应式更新
            node.color = colors.color;
            node.stroke = colors.stroke;
            node.strokeWidth = colors.strokeWidth;
          });
          // 强制更新视图，确保颜色变化立即显示
          this.$nextTick(() => {
            this.$forceUpdate();
          });
        }
      },
      immediate: false,
      deep: true
    },
    // 监听 prop 变化，同步到本地状态
    filterStrategy: {
      handler(newVal) {
        if (newVal) {
          this.localFilterStrategy = newVal;
        }
      },
      immediate: true
    },
    semanticReorganizeMeta: {
      handler() {
        // 手动改连边强度时只更新局部，避免整图重初始化导致节点跳动
        if (this._skipSemanticMetaReinit) return;
        // 大本体：meta 可能带属性；本子级勿因 meta 变化整表冲掉已加载的四色DMT
        if (this.isOntologyScopeMode) {
          this.syncKeywordFourColorDMTFromProp();
        }
        if (this.viewMode === 'network') {
          this.$nextTick(() => this.initializeNetwork());
        }
      },
      deep: true,
    },
    keywordFourColorDMT: {
      handler(newVal) {
        console.log('[KeywordNetworkGraph] watch 触发，newVal:', newVal);
        console.log('[KeywordNetworkGraph] newVal类型:', typeof newVal);
        
        const keyCount = this.syncKeywordFourColorDMTFromProp();
        console.log('[KeywordNetworkGraph] ✅ 数据更新成功，键数量:', keyCount);
        if (keyCount <= 0) {
          console.log('[KeywordNetworkGraph] ⚠️ 四色DMT 仍为空');
          return;
        }
              
              // 🔥 重新计算节点（包括大小和颜色），因为四色/DMT数据已更新
              if (this.viewMode === 'network' && this.graphKeywordPool.length > 0) {
                const keywordsToShow = this.getDisplayKeywords(this.graphKeywordPool, this.getActiveNodeLimit());
                
                // 🔥 保存已有节点的固定位置（fx/fy），以便重新计算后恢复
                const fixedPositions = new Map();
                this.nodes.forEach(node => {
                  if (node.fx !== undefined && node.fy !== undefined) {
                    fixedPositions.set(node.label, { fx: node.fx, fy: node.fy });
                  }
                });
                
                // 重新计算节点（会应用新的四色/DMT属性，包括半径和颜色）
                this.nodes = this.calculateNodes(keywordsToShow);
                this.links = this.calculateLinks(keywordsToShow);
                
                // 🔥 恢复已有节点的固定位置
                this.nodes.forEach(node => {
                  const fixedPos = fixedPositions.get(node.label);
                  if (fixedPos) {
                    node.x = fixedPos.fx;
                    node.y = fixedPos.fy;
                    node.fx = fixedPos.fx;
                    node.fy = fixedPos.fy;
                  }
                });
                
                if (this.quadrantPlaceMode || readQuadrantPicture()) {
                  this.quadrantPlaceMode = true;
                  this.restoreSavedQuadrantView();
                } else {
                  this.loadSavedPositions();
                  this.restorePositions();
                }
                this.updateLinkPositions();
                this.updateNodePositions();
              }
      },
      immediate: true,
      deep: true
    },
    
    // 🔥 监听selectedKeywords变化，更新节点颜色
    selectedKeywords: {
      handler(newVal, oldVal) {
        if (this.nodes && this.nodes.length > 0) {
          const counts = this.nodes.map(node => node.cardCount || 0);
          const minCount = Math.min(...counts, 1);
          const maxCount = Math.max(...counts, 1);
          
          this.nodes.forEach(node => {
            const isSelected = newVal.includes(node.label);
            const colors = this.getNodeColors(
              node.label,
              node.cardCount || 0,
              minCount,
              maxCount,
              isSelected
            );
            node.color = colors.color;
            node.stroke = colors.stroke;
            node.strokeWidth = colors.strokeWidth;
          });
          
          // 🔥 立即强制更新视图，确保颜色变化立即显示
          this.$nextTick(() => {
            this.updateNodePositions();
            this.$forceUpdate();
          });
        }
      },
      immediate: false
    },
    // 🔥 监听viewMode变化，当显示网络图时，如果是首次加载则延迟重置布局
    viewMode: {
      handler(newVal, oldVal) {
        if (newVal === 'network' && oldVal !== 'network') {
          // 网络图刚显示时，检查是否是首次加载
          console.log('[KeywordNetworkGraph] viewMode变为network，检查首次加载');
          this.$nextTick(() => {
            // 等待一下，确保组件已经完全渲染
            setTimeout(() => {
              this.loadSavedPositions();
              const isFirstLoad = !this.savedPositions || Object.keys(this.savedPositions).length === 0;
              
              if (this.quadrantModeEnabled() || readQuadrantPicture()) {
                return;
              }
              if (isFirstLoad && this.nodes && this.nodes.length > 0) {
                console.log('[KeywordNetworkGraph] 🔥 网络图显示且首次加载，将在2秒后自动执行重置布局');
                
                // 清除之前的延迟定时器（如果存在）
                if (this.firstLoadResetTimer) {
                  clearTimeout(this.firstLoadResetTimer);
                }
                
                // 延迟2秒后执行重置布局（确保tags-container已经完全显示）
                this.firstLoadResetTimer = setTimeout(() => {
                  console.log('[KeywordNetworkGraph] 🔥 执行首次加载自动重置布局');
                  
                  // 再次确认是首次加载（防止在延迟期间用户已经保存了位置）
                  this.loadSavedPositions();
                  const stillFirstLoad = !this.savedPositions || Object.keys(this.savedPositions).length === 0;
                  if (!stillFirstLoad) {
                    console.log('[KeywordNetworkGraph] ⚠️ 延迟期间已有保存位置，取消重置');
                    this.firstLoadResetTimer = null;
                    return;
                  }
                  
                  // 停止当前的模拟（如果还在运行）
                  if (this.simulation) {
                    this.simulation.stop();
                  }
                  
                  // 清除保存的位置（确保是真正的首次加载）
                  this.savedPositions = {};
                  localStorage.removeItem(this.getPositionsStorageKeyForLimit(this.getActiveNodeLimit()));
                  localStorage.removeItem(`keywordNetworkPositions_${this.getStorageKey()}`);
                  
                  // 清除所有节点的固定位置，让力导向布局重新计算
                  this.nodes.forEach(node => {
                    node.fx = undefined;
                    node.fy = undefined;
                  });
                  
                  // 清除基准viewBox范围，让布局重新计算
                  this.baseViewBoxBounds = null;
                  
                  // 重新运行布局（完全重新计算）
                  this.initializeForceLayout();
                  
                  // 清除定时器引用
                  this.firstLoadResetTimer = null;
                }, 2000); // 延迟2秒
              }
            }, 100); // 等待100ms确保组件完全渲染
          });
        }
      },
      immediate: false
    }
  },
  computed: {
    isOntologyScopeMode() {
      return !!(String(this.ontologyScopeType || '').trim() && String(this.ontologyScopeId || '').trim());
    },
    isV3Pipeline() {
      return String(this.semanticReorganizeMeta?.pipeline || '').startsWith('v3');
    },
    showAuxLinkToggles() {
      const meta = this.semanticReorganizeMeta || {};
      return this.isV3Pipeline
        || (Array.isArray(meta.hierarchy_links) && meta.hierarchy_links.length > 0)
        || (Array.isArray(meta.longitude_chains) && meta.longitude_chains.length > 0);
    },
    visibleLinks() {
      return (this.links || []).filter((link) => {
        if (link.linkType === 'contour') return false;
        if (link.linkType === 'longitude' && !this.showLongitudeLinks) return false;
        return true;
      });
    },
    contourRings() {
      const byLabel = {};
      (this.nodes || []).forEach((node) => {
        if (node && node.label && node.x != null && node.y != null) byLabel[node.label] = node;
      });
      const childrenByParent = {};
      (this.links || []).forEach((link) => {
        if (link.linkType !== 'hierarchy') return;
        const parent = link.parentKeyword;
        const child = link.childKeyword;
        if (!parent || !child || !byLabel[parent] || !byLabel[child]) return;
        if (!childrenByParent[parent]) childrenByParent[parent] = [];
        if (!childrenByParent[parent].includes(child)) childrenByParent[parent].push(child);
      });
      const rings = [];
      Object.keys(childrenByParent).forEach((parent) => {
        const pts = childrenByParent[parent]
          .map((label) => byLabel[label])
          .filter((node) => node && node.x != null && node.y != null)
          .map((node) => ({
            label: node.label,
            x: node.x,
            y: node.y,
            r: node.radius || 10,
          }));
        if (pts.length < 3) return;
        const cx = pts.reduce((s, p) => s + p.x, 0) / pts.length;
        const cy = pts.reduce((s, p) => s + p.y, 0) / pts.length;
        const dist = pts.map((p) => Math.hypot(p.x - cx, p.y - cy));
        const sortedDist = [...dist].sort((a, b) => a - b);
        const median = sortedDist[Math.floor(sortedDist.length / 2)] || 1;
        const local = pts.filter((p, i) => dist[i] <= Math.max(90, median * 1.8));
        if (local.length < 3) return;
        const lcx = local.reduce((s, p) => s + p.x, 0) / local.length;
        const lcy = local.reduce((s, p) => s + p.y, 0) / local.length;
        const ordered = [...local].sort((a, b) => Math.atan2(a.y - lcy, a.x - lcx) - Math.atan2(b.y - lcy, b.x - lcx));
        const expanded = ordered.map((p) => {
          const dx = p.x - lcx;
          const dy = p.y - lcy;
          const len = Math.hypot(dx, dy) || 1;
          const pad = (p.r || 10) + 18;
          return { x: p.x + (dx / len) * pad, y: p.y + (dy / len) * pad };
        });
        const d = this.closedContourPath(expanded);
        if (d) {
          rings.push({
            id: parent,
            d,
            members: [parent, ...local.map((p) => p.label)],
          });
        }
      });
      return rings;
    },
    hoveredContourFocus() {
      if (!this.hoveredContourId) return null;
      const ring = (this.contourRings || []).find((item) => item.id === this.hoveredContourId);
      if (!ring || !Array.isArray(ring.members)) return null;
      const set = {};
      ring.members.forEach((label) => {
        if (label) set[label] = true;
      });
      return set;
    },
    longitudeChainMap() {
      const map = {};
      (this.links || []).forEach((link) => {
        if (link.linkType !== 'longitude' || !link.longitudeId) return;
        if (!map[link.longitudeId]) map[link.longitudeId] = {};
        const a = link.source && link.source.label;
        const b = link.target && link.target.label;
        if (a) map[link.longitudeId][a] = true;
        if (b) map[link.longitudeId][b] = true;
      });
      return map;
    },
    visibleContourRings() {
      const rings = this.contourRings || [];
      if (this.showContourLinks && !(this.showLongitudeLinks && this.hoveredLongitudeId)) return rings;
      if (this.showLongitudeLinks && this.hoveredLongitudeId) {
        const chain = this.longitudeChainMap[this.hoveredLongitudeId] || {};
        const related = rings.filter((ring) => (ring.members || []).some((label) => chain[label]));
        if (this.showContourLinks) return rings;
        return related;
      }
      if (this.showContourLinks) return rings;
      return [];
    },
    activeFocus() {
      if (this.showLongitudeLinks && this.hoveredLongitudeId) {
        const chain = this.longitudeChainMap[this.hoveredLongitudeId] || {};
        const nodes = { ...chain };
        (this.contourRings || []).forEach((ring) => {
          if ((ring.members || []).some((label) => chain[label])) {
            (ring.members || []).forEach((label) => {
              if (label) nodes[label] = true;
            });
          }
        });
        return { mode: 'longitude-hover', nodes };
      }
      if (this.hoveredContourFocus) return { mode: 'contour', nodes: this.hoveredContourFocus };
      if (this.showLongitudeLinks) {
        const nodes = {};
        Object.keys(this.longitudeChainMap).forEach((id) => {
          Object.keys(this.longitudeChainMap[id]).forEach((label) => {
            nodes[label] = true;
          });
        });
        if (Object.keys(nodes).length) return { mode: 'longitude', nodes };
      }
      return null;
    },
    v3Thermometer() {
      const t = this.semanticReorganizeMeta?.thermometer;
      return t && typeof t === 'object' ? t : null;
    },
    v3SpiralText() {
      return String(this.v3Thermometer?.spiral || '').trim();
    },
    v3ThermometerSubjectReasonShort() {
      const s = String(this.v3Thermometer?.subject_reason || '').trim();
      return s.length > 48 ? `${s.slice(0, 48)}…` : s;
    },
    v3ThermometerOntologyReasonShort() {
      const s = String(this.v3Thermometer?.ontology_reason || '').trim();
      return s.length > 48 ? `${s.slice(0, 48)}…` : s;
    },
    v3CoreIssue() {
      const meta = this.semanticReorganizeMeta || {};
      const fromTop = meta.book_top_keywords?.core_issue;
      return String(meta.core_issue || fromTop || '').trim();
    },
    v3SubIssues() {
      const meta = this.semanticReorganizeMeta || {};
      const list = meta.sub_issues || meta.book_top_keywords?.sub_issues;
      return Array.isArray(list) ? list.map((x) => String(x).trim()).filter(Boolean) : [];
    },
    panelEditTitle() {
      if (this.panelEditKind === 'sub_add') return '添加子问题';
      if (this.panelEditKind === 'sub_edit') return '修改子问题';
      if (this.panelEditKind === 'scale_edit') return `修改${this.panelEditItemName || '刻度'}说明`;
      if (this.panelEditKind === 'quadrant_edit') return `修改${this.panelEditItemName || '象限'}内涵`;
      return '修改';
    },
    panelEditLead() {
      if (this.panelEditKind === 'quadrant_edit') {
        return '下面是在这段原文上精修的修改稿，不是另写一条换掉它。点一条就填进下方，也可以再改。这一象限收哪些语义要留住。';
      }
      if (this.panelEditKind === 'scale_edit') {
        return '下面是在这段原文上精修的修改稿，不是另写一条换掉它。点一条就填进下方，也可以再改。条目本身不能增删。';
      }
      if (this.panelEditKind === 'sub_edit') {
        return '下面是在这句原文上精修的修改稿，不是另起一个问题替换它。点一条就填进下方，也可以再改。';
      }
      return '下面几条按本子现有内容来补。点一条就填进下方，也可以自己改。子问题请保持一句问话。';
    },
    v3CoreIssueAlternatives() {
      const meta = this.semanticReorganizeMeta || {};
      const list = meta.core_issue_alternatives || meta.book_top_keywords?.core_issue_alternatives;
      return Array.isArray(list) ? list.map((x) => String(x).trim()).filter(Boolean) : [];
    },
    v3TopAlternativeTiers() {
      const meta = this.semanticReorganizeMeta || {};
      const tops = meta.book_top_keywords && typeof meta.book_top_keywords === 'object'
        ? meta.book_top_keywords
        : {};
      const alts = tops.top_alternatives && typeof tops.top_alternatives === 'object'
        ? tops.top_alternatives
        : {};
      const labels = { top1: 'Top1', top3: 'Top3', top5: 'Top5', top10: 'Top10' };
      const asWords = (raw) => {
        if (Array.isArray(raw)) return raw.map((x) => String(x).trim()).filter(Boolean);
        if (raw != null && String(raw).trim()) return [String(raw).trim()];
        return [];
      };
      return ['top1', 'top3', 'top5', 'top10'].map((key) => ({
        key,
        label: labels[key] || key,
        current: asWords(tops[key]),
        words: asWords(alts[key]),
      })).filter((tier) => tier.current.length > 0 || tier.words.length > 0);
    },
    pendingDialogGroups() {
      const buckets = {
        know: [],
        meaning: [],
        conflict: [],
        color: [],
        dmt: [],
        knowledge: [],
      };
      (this.pendingDialogOptionsList || []).forEach((opt) => {
        const key = buckets[opt.bucket] ? opt.bucket : 'meaning';
        buckets[key].push(opt);
      });
      const meta = [
        { key: 'know', title: '你知不知道', note: '只回答你本人清不清楚，不改颜色和层级。' },
        { key: 'meaning', title: '它在这里是什么意思', note: '选一句你认可的解释。' },
        { key: 'conflict', title: '材料里对不上的地方', note: '这不是归类。材料自己打架，或没写清它在文里的作用。' },
        { key: 'color', title: '四色', note: '只改颜色。红是事实，蓝是方法，紫是迁移，绿是规律。' },
        { key: 'dmt', title: 'DMT 层级', note: '只改层级。D 是立足点，M 是方法，T 是迁移。' },
        { key: 'knowledge', title: '知识类型', note: '只改它算传统、组织、部落，或更具体的哪一类实体。' },
      ];
      return meta
        .filter((item) => buckets[item.key].length)
        .map((item) => ({ ...item, items: buckets[item.key] }));
    },
    topReplaceTierLabel() {
      const map = { top1: 'Top1', top3: 'Top3', top5: 'Top5', top10: 'Top10' };
      return map[this.topReplaceTierKey] || this.topReplaceTierKey || 'Top';
    },
    v3ScaleSummaryLines() {
      const scale = this.semanticReorganizeMeta?.scale_definitions;
      if (!scale || typeof scale !== 'object') return [];
      const altsRoot = scale.alternatives && typeof scale.alternatives === 'object' ? scale.alternatives : {};
      const fmtItems = (obj, labels) => {
        if (!obj || typeof obj !== 'object') return [];
        return Object.keys(labels)
          .map((k) => {
            const v = obj[k];
            if (!v) return null;
            return { key: k, name: labels[k], text: String(v) };
          })
          .filter(Boolean);
      };
      const buildAltChips = (scaleKey, labelMap) => {
        const block = altsRoot[scaleKey];
        if (!block || typeof block !== 'object') return [];
        return Object.entries(block).flatMap(([variantId, variantVal]) => {
          if (!variantVal || typeof variantVal !== 'object') return [];
          const label = Object.keys(labelMap)
            .map((k) => (variantVal[k] ? `${labelMap[k]}:${variantVal[k]}` : ''))
            .filter(Boolean)
            .join(' ')
            .slice(0, 72);
          if (!label) return [];
          return [{
            id: String(variantId),
            label: label || String(variantId),
            onClick: () => this.saveV3IntentPreference({
              preferred_scale_definitions: { [scaleKey]: variantVal },
            }),
          }];
        });
      };
      return [
        {
          key: 'four_color',
          title: '四色刻度',
          items: fmtItems(scale.four_color, { R: '红', B: '蓝', P: '紫', G: '绿' }),
          alternatives: buildAltChips('four_color', { R: '红', B: '蓝', P: '紫', G: '绿' }),
        },
        {
          key: 'dmt',
          title: 'DMT 刻度',
          items: fmtItems(scale.dmt, { D: 'D', M: 'M', T: 'T' }),
          alternatives: buildAltChips('dmt', { D: 'D', M: 'M', T: 'T' }),
        },
        {
          key: 'knowledge',
          title: '三类知识刻度',
          items: fmtItems(scale.knowledge, { trad: '传统', org: '组织', trib: '部落' }),
          alternatives: buildAltChips('knowledge', { trad: '传统', org: '组织', trib: '部落' }),
        },
      ].filter((line) => (line.items && line.items.length) || line.alternatives.length);
    },
    v3QuadrantMeaningLines() {
      const pack = this.semanticReorganizeMeta?.quadrant_meaning;
      const defs = pack && typeof pack.definitions === 'object' ? pack.definitions : null;
      if (!defs) return [];
      const names = { Q1: '共识区', Q2: '盲区', Q3: '未知区', Q4: '隐藏区' };
      const rules = {
        Q1: '规则：机知且人知。材料里站得住，人这边也清楚。',
        Q2: '规则：机知且人不知。材料里站得住，人这边没掌握或说不清。',
        Q3: '规则：机不知且人不知。材料里也没把握，人这边也没掌握。',
        Q4: '规则：机不知且人知。人这边清楚，材料里还没立住。',
      };
      return ['Q1', 'Q2', 'Q3', 'Q4']
        .map((key) => {
          const raw = defs[key];
          const text = raw && typeof raw === 'object'
            ? String(raw.meaning || raw.text || '').trim()
            : String(raw || '').trim();
          if (!text) return null;
          return { key, title: names[key], rule: rules[key], text };
        })
        .filter(Boolean);
    },
    pendingDialogOptionsList() {
      const word = this.pendingDialogNode?.label;
      if (!word) return [];
      const quads = this.semanticReorganizeMeta?.quadrants || {};
      const entry = quads[word] || {};
      const fromMeta = Array.isArray(entry.pending_options) ? entry.pending_options : [];
      const seen = new Set();
      return fromMeta.map((opt) => {
        if (opt && typeof opt === 'object') {
          const id = String(opt.id || opt.label || '').trim();
          const label = String(opt.label || opt.id || '').trim();
          const item = {
            id: id || label,
            label: label || id,
            preview: String(opt.preview || '').trim(),
            human_know: opt.human_know,
            kind: String(opt.kind || '').trim(),
            attr_patch: (opt.attr_patch && typeof opt.attr_patch === 'object') ? opt.attr_patch : {},
          };
          item.bucket = this.pendingOptionBucket(item);
          item.effect = this.pendingOptionEffect(item);
          return item;
        }
        const s = String(opt).trim();
        return { id: s, label: s, preview: '', human_know: undefined, kind: '', attr_patch: {}, bucket: 'meaning', effect: '' };
      }).filter((o) => {
        const k = o.id || o.label;
        if (!k || seen.has(k)) return false;
        seen.add(k);
        return true;
      });
    },
    /** 组本横轴：组知道/组不知道；个人本：我知道/我不知道 */
    isGroupNotebookAxis() {
      try {
        const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
        if (currentNotebook.syncUsers && currentNotebook.syncUsers !== '') {
          return true;
        }
      } catch (e) { /* ignore */ }
      return this.isMultiWriterNotebook();
    },
    axisXKnowLabel() {
      return this.isGroupNotebookAxis ? '组知道' : '我知道';
    },
    axisXUnknownLabel() {
      return this.isGroupNotebookAxis ? '组不知道' : '我不知道';
    },
    // 当前筛选策略（优先使用本地状态，确保按钮立即响应）
    currentFilterStrategy() {
      return this.localFilterStrategy || this.filterStrategy || 'union';
    },

    /** v2 精进梳理后：只用新处理过的卡片构建节点/词池；旧卡旧词不再进图 */
    effectiveCards() {
      const meta = this.semanticReorganizeMeta || {};
      if (this.isV3Pipeline) {
        return this.cards || [];
      }
      const selected = meta.reorganize_selected_cids;
      if (
        meta.pipeline === 'v2_condense_hierarchy'
        && Array.isArray(selected)
        && selected.length > 0
      ) {
        const pid = new Set(selected.map((c) => Number(c)));
        return (this.cards || []).filter((c) => pid.has(Number(c.cid)));
      }
      // 旧版兼容：抽样时按 processed_cids
      if (!meta.sampled) {
        return this.cards || [];
      }
      const processed = meta.processed_cids;
      if (!Array.isArray(processed) || processed.length === 0) {
        return this.cards || [];
      }
      const pid = new Set(processed.map((c) => Number(c)));
      return (this.cards || []).filter((c) => pid.has(Number(c.cid)));
    },

    graphKeywordPool() {
      const kws = this.keywords || [];
      const meta = this.semanticReorganizeMeta || {};
      if (this.isV3Pipeline) {
        const bookKw = meta.book_keywords;
        if (Array.isArray(bookKw) && bookKw.length > 0) {
          const list = bookKw.map((k) => String(k).trim()).filter(Boolean);
          const allowed = new Set(kws);
          const intersected = list.filter((k) => allowed.has(k));
          return intersected.length > 0 ? intersected : list;
        }
      }
      const useSelectedOnly = (
        meta.pipeline === 'v2_condense_hierarchy'
        && Array.isArray(meta.reorganize_selected_cids)
        && meta.reorganize_selected_cids.length > 0
      ) || !!meta.sampled;
      if (!useSelectedOnly) {
        return kws;
      }
      const allowed = new Set();
      this.effectiveCards.forEach((card) => {
        if (!card.keyWords) return;
        card.keyWords.split(/[,，]/).map((k) => k.trim()).forEach((k) => {
          if (k) allowed.add(k);
        });
      });
      return kws.filter((k) => allowed.has(k));
    },

    totalKeywordCount() {
      return this.graphKeywordPool.length;
    },

    /** 做过 v2/v3 本体语义梳理的本子：节点显示上限提到 200 */
    maxNodeDisplayOption() {
      const meta = this.semanticReorganizeMeta || {};
      const isV2 = this.isV3Pipeline
        || meta.pipeline === 'v2_condense_hierarchy'
        || (Array.isArray(meta.reorganize_selected_cids) && meta.reorganize_selected_cids.length > 0)
        || (Array.isArray(meta.hierarchy_links) && meta.hierarchy_links.length > 0);
      return isV2 ? MAX_NODE_DISPLAY_OPTION_V2 : MAX_NODE_DISPLAY_OPTION_DEFAULT;
    },

    nodeCountLimitOptions() {
      const total = this.totalKeywordCount;
      const DEFAULT = DEFAULT_NODE_DISPLAY_LIMIT;
      const MAX_OPT = this.maxNodeDisplayOption;
      if (total <= 0) return [];

      const cap = Math.min(total, MAX_OPT);
      if (cap <= DEFAULT) {
        const recommended = total <= RECOMMENDED_NODE_LIMIT;
        return [{
          label: recommended ? `全部 (${total})（推荐）` : `全部 (${total})`,
          value: total,
          recommended,
        }];
      }

      const candidates = [1, 3, 5, 10, DEFAULT, 50, 100, 150, 200, MAX_OPT]
        .filter((n, i, arr) => arr.indexOf(n) === i);
      const values = [...new Set(
        candidates.filter(n => n >= MIN_NODE_DISPLAY_OPTION && n <= cap),
      )].sort((a, b) => a - b);

      if (total <= MAX_OPT && !values.includes(total)) {
        values.push(total);
        values.sort((a, b) => a - b);
      }

      const recommendedValue = [...values].filter(v => v <= RECOMMENDED_NODE_LIMIT).pop();

      return values.map(v => {
        const isAll = total <= MAX_OPT && v === total;
        const isRec = v === recommendedValue;
        let label = isAll ? `全部 (${total})` : `${v} 个`;
        if (isRec) label += '（推荐）';
        return { label, value: v, recommended: isRec };
      });
    },

    nodeDisplayLimitShortLabel() {
      const limit = this.getActiveNodeLimit();
      const total = this.totalKeywordCount;
      const MAX_OPT = this.maxNodeDisplayOption;
      if (total > 0 && limit >= Math.min(total, MAX_OPT)) {
        return limit >= MAX_OPT && total > MAX_OPT ? String(MAX_OPT) : '全';
      }
      return String(limit);
    },

    nodeDisplayLimitLabel() {
      const limit = this.getActiveNodeLimit();
      const total = this.totalKeywordCount;
      const MAX_OPT = this.maxNodeDisplayOption;
      if (total > 0 && limit >= Math.min(total, MAX_OPT)) {
        if (total <= MAX_OPT) return `全部 ${total}`;
        return String(MAX_OPT);
      }
      return String(limit);
    },

    keywordPickStrategyOptions() {
      const n = this.getActiveNodeLimit();
      const c3 = Math.max(1, Math.floor(n / 3));
      const c5 = Math.max(1, Math.floor(n / 5));
      return [
        {
          value: KEYWORD_PICK_STRATEGIES.default,
          label: '默认（四色/DMT均衡·高频·新词优先）',
          desc: '沿用现有智能筛选：尽量覆盖四色与 DMT，兼顾卡片共现频率与当日新词，不按单卡前几词截取。',
        },
        {
          value: KEYWORD_PICK_STRATEGIES.top3,
          label: '取前三词',
          desc: `从参与分析的最多 ${ANALYSIS_CARD_POOL_CAP} 张卡中精选约 ${c3} 张，每张取语义关键词前 3 个（3×${c3}≈${n}）。`,
        },
        {
          value: KEYWORD_PICK_STRATEGIES.top5,
          label: '取前五词',
          desc: `从参与分析的最多 ${ANALYSIS_CARD_POOL_CAP} 张卡中精选约 ${c5} 张，每张取语义关键词前 5 个（5×${c5}≈${n}）。`,
        },
      ];
    },

    keywordPickStrategyShortLabel() {
      if (this.keywordPickStrategy === KEYWORD_PICK_STRATEGIES.top3) return '前3';
      if (this.keywordPickStrategy === KEYWORD_PICK_STRATEGIES.top5) return '前5';
      return '默';
    },

    keywordPickStrategyTitle() {
      const map = {
        [KEYWORD_PICK_STRATEGIES.default]: '取用策略：默认（四色/DMT均衡·高频·新词优先）',
        [KEYWORD_PICK_STRATEGIES.top3]: '取用策略：取前三词',
        [KEYWORD_PICK_STRATEGIES.top5]: '取用策略：取前五词',
      };
      return map[this.keywordPickStrategy] || '节点取用策略';
    },

    ontologyViewerUsername() {
      return (
        localStorage.getItem('originRealName')
        || localStorage.getItem('realName')
        || ''
      ).trim();
    },
    
    computedViewBox() {
      if (this.quadrantPlaceMode && this.quadrantFrame) {
        const frame = this.quadrantFrame;
        const pad = 6;
        const minX = frame.minX - pad;
        const minY = frame.minY - pad;
        const width = Math.max(120, frame.maxX - frame.minX + pad * 2);
        const height = Math.max(120, frame.maxY - frame.minY + pad * 2);
        return `${minX} ${minY} ${width} ${height}`;
      }
      // 平时坐标轴固定：X轴 y=610，Y轴 x=60，原点 (60,610)
      const axisOriginX = 60;
      const axisOriginY = 610;
      const negativeSpace = 50;
      const axisLabelPadX = 60; // 「我不知道」等较长标签
      const axisLabelPadY = 60; // 顶部标题与「AI 知道」
      
      if (this.nodes && this.nodes.length > 0) {
        const bounds = this.getNodeBounds();
        const padding = 80;
        
        const nodeMinX = bounds.minX;
        const nodeMinY = bounds.minY;
        const nodeMaxX = bounds.maxX;
        const nodeMaxY = bounds.maxY;
        
        const minX = Math.min(axisOriginX - negativeSpace, nodeMinX - padding, -28 - axisLabelPadX);
        const maxX = Math.max(axisOriginX + negativeSpace, nodeMaxX + padding, 148 + axisLabelPadX);
        const minY = Math.min(nodeMinY - padding, axisOriginY - negativeSpace, 40 - axisLabelPadY);
        const maxY = Math.max(axisOriginY + negativeSpace, nodeMaxY + padding, 688 + 40);
        
        const width = maxX - minX;
        const height = maxY - minY;
        
        // 如果有基准viewBox范围，使用更大的范围来确保完整显示
        if (this.baseViewBoxBounds) {
          const baseBounds = this.baseViewBoxBounds;
          const baseMinX = baseBounds.minX;
          const baseMaxX = baseBounds.maxX;
          const baseMinY = baseBounds.minY;
          const baseMaxY = baseBounds.maxY;
          
          // 使用更大的范围，但确保包含坐标轴原点(axisOriginX, axisOriginY)和标签
          const finalMinX = Math.min(minX, baseMinX, axisOriginX - negativeSpace, -28 - axisLabelPadX);
          const finalMaxX = Math.max(maxX, baseMaxX, axisOriginX + negativeSpace, 148 + axisLabelPadX);
          const finalMinY = Math.min(minY, baseMinY, axisOriginY - negativeSpace, 40 - axisLabelPadY);
          const finalMaxY = Math.max(maxY, baseMaxY, axisOriginY + negativeSpace, 688 + 40);
          
          const finalWidth = finalMaxX - finalMinX;
          const finalHeight = finalMaxY - finalMinY;
          
          // viewBox格式：minX minY width height
          return `${finalMinX} ${finalMinY} ${finalWidth} ${finalHeight}`;
        }
        
        // 确保有最小值，避免viewBox为0
        const finalWidth = Math.max(width, 100);
        const finalHeight = Math.max(height, 100);
        
        // viewBox格式：minX minY width height
        return `${minX} ${minY} ${finalWidth} ${finalHeight}`;
      }
      // 如果没有节点，使用默认viewBox（包含坐标轴原点(axisOriginX, axisOriginY)和标签）
      return `${Math.min(axisOriginX - negativeSpace, -28 - axisLabelPadX)} ${Math.min(axisOriginY - negativeSpace, 40 - axisLabelPadY)} ${this.svgWidth} ${this.svgHeight}`;
    },
    axisCanvas() {
      if (this.quadrantPlaceMode && this.quadrantFrame) {
        const frame = this.quadrantFrame;
        const originX = frame.originX;
        const originY = frame.originY;
        const left = frame.minX;
        const top = frame.minY;
        const right = frame.maxX;
        const bottom = frame.maxY;
        const makeQuad = (x, y, w, h) => ({
          x,
          y,
          w: Math.max(w, 0),
          h: Math.max(h, 0),
          cx: x + Math.max(w, 0) / 2,
          cy: y + Math.max(h, 0) / 2,
        });
        const edge = 28;
        return {
          originX,
          originY,
          minX: left,
          minY: top,
          maxX: right,
          maxY: bottom,
          midX: (left + right) / 2,
          q2: makeQuad(left, top, originX - left, originY - top),
          q1: makeQuad(originX, top, right - originX, originY - top),
          q3: makeQuad(left, originY, originX - left, bottom - originY),
          q4: makeQuad(originX, originY, right - originX, bottom - originY),
          labels: {
            q2: { x: left + edge, y: top + 48 },
            q1: { x: right - edge, y: top + 48 },
            q3: { x: left + edge, y: bottom - 18 },
            q4: { x: right - edge, y: bottom - 18 },
            xNeg: { x: left + edge, y: originY - 10 },
            xPos: { x: right - 18, y: originY - 10 },
            yPos: { x: originX + 10, y: top + 46 },
            yNeg: { x: originX + 10, y: bottom - 14 },
          },
        };
      }
      const originX = 60;
      const originY = 610;
      const bleed = 4;
      const parts = String(this.computedViewBox || '').trim().split(/\s+/).map(Number);
      let minX = -200;
      let minY = -100;
      let width = 1000;
      let height = 1200;
      if (parts.length >= 4 && parts.every((n) => Number.isFinite(n))) {
        minX = parts[0];
        minY = parts[1];
        width = Math.max(parts[2], 1);
        height = Math.max(parts[3], 1);
      }
      const maxX = minX + width;
      const maxY = minY + height;
      const left = minX - bleed;
      const top = minY - bleed;
      const right = maxX + bleed;
      const bottom = maxY + bleed;
      const makeQuad = (x, y, w, h) => ({
        x,
        y,
        w: Math.max(w, 0),
        h: Math.max(h, 0),
        cx: x + Math.max(w, 0) / 2,
        cy: y + Math.max(h, 0) / 2,
      });
      const edge = 28;
      const q2x = left + edge;
      const q2y = top + 48;
      const q1x = right - edge;
      const q1y = top + 48;
      const q3x = left + edge;
      const q3y = bottom - 18;
      const q4x = right - edge;
      const q4y = bottom - 18;
      return {
        originX,
        originY,
        minX: left,
        minY: top,
        maxX: right,
        maxY: bottom,
        midX: (left + right) / 2,
        q2: makeQuad(left, top, originX - left, originY - top),
        q1: makeQuad(originX, top, right - originX, originY - top),
        q3: makeQuad(left, originY, originX - left, bottom - originY),
        q4: makeQuad(originX, originY, right - originX, bottom - originY),
        labels: {
          q2: { x: q2x, y: q2y },
          q1: { x: q1x, y: q1y },
          q3: { x: q3x, y: q3y },
          q4: { x: q4x, y: q4y },
          xNeg: { x: left + edge, y: originY - 10 },
          xPos: { x: right - 18, y: originY - 10 },
          yPos: { x: originX + 10, y: top + 46 },
          yNeg: { x: originX + 10, y: bottom - 14 },
        },
      };
    },
    computedContainerHeight() {
      // 动态计算容器高度，使其刚好适配网络图的宽高比（使用与viewBox相同的对称计算方式）
      if (this.nodes && this.nodes.length > 0) {
        const bounds = this.getNodeBounds();
        const padding = 80; // 与viewBox的padding保持一致
        
        // 计算节点分布的最大宽度和高度
        const contentWidth = bounds.maxX - bounds.minX;
        const contentHeight = bounds.maxY - bounds.minY;
        
        // 计算viewBox尺寸（内容 + 对称的padding）
        let finalWidth = contentWidth + padding * 2;
        let finalHeight = contentHeight + padding * 2;
        
        // 如果有基准viewBox范围，使用更大的范围
        if (this.baseViewBoxBounds) {
          const baseBounds = this.baseViewBoxBounds;
          const baseWidth = baseBounds.maxX - baseBounds.minX;
          const baseHeight = baseBounds.maxY - baseBounds.minY;
          finalWidth = Math.max(finalWidth, baseWidth);
          finalHeight = Math.max(finalHeight, baseHeight);
        }
        
        // 确保有最小值
        finalWidth = Math.max(finalWidth, 100);
        finalHeight = Math.max(finalHeight, 100);
        
        if (finalWidth > 0 && finalHeight > 0) {
          // 使用存储的容器宽度（在mounted和resize时更新）
          const containerWidth = this.containerWidth;
          
          // 计算宽高比，设置容器高度
          const aspectRatio = finalHeight / finalWidth;
          const calculatedHeight = containerWidth * aspectRatio;
          
          // 根据内容动态计算高度，移除高度限制以确保完整显示
          // 只设置最小高度，不限制最大高度，让容器完全适配内容
          const minHeight = 400;
          
          return Math.max(minHeight, calculatedHeight) + 'px';
        }
      }
      // 默认高度
      return '550px';
    }
  },
  created() {
    console.log('[KeywordNetworkGraph] ========== 组件已创建 ==========');
  },
  mounted() {
    console.log('[KeywordNetworkGraph] ========== 组件已挂载 ==========');
    console.log('[KeywordNetworkGraph] viewMode:', this.viewMode);
    console.log('[KeywordNetworkGraph] keywords:', this.keywords);
    
    // 🔥 从localStorage加载本地更新的关键词数据（避免依赖prop）
    this.loadLocalUpdatedKeywordsFromStorage();
    this.nodeDisplayLimit = this.loadNodeDisplayLimitPreference();
    this.keywordPickStrategy = this.loadKeywordPickStrategyPreference();
    
    // 🔥 添加点击外部关闭右键菜单的事件监听
    document.addEventListener('click', this.handleDocumentClick);
    document.addEventListener('contextmenu', this.handleDocumentClick);
    console.log('[KeywordNetworkGraph] keywords类型:', typeof this.keywords);
    console.log('[KeywordNetworkGraph] keywords是否为数组:', Array.isArray(this.keywords));
    console.log('[KeywordNetworkGraph] keywords.length:', this.keywords ? this.keywords.length : 'null/undefined');
    console.log('[KeywordNetworkGraph] initialKeywords:', this.initialKeywords);
    console.log('[KeywordNetworkGraph] cards:', this.effectiveCards);
    console.log('[KeywordNetworkGraph] cards.length:', this.effectiveCards ? this.effectiveCards.length : 'null/undefined');
    
    try {
      // 加载保存的节点位置
      this.loadSavedPositions();
      this.quadrantPlaceMode = this.quadrantModeEnabled();
      
      // 先获取容器宽度
      this.updateContainerWidth();
      
      // 初始化网络图
      if (this.viewMode === 'network') {
        if (this.keywords && this.keywords.length > 0) {
          console.log('[KeywordNetworkGraph] ✅ 准备初始化网络图');
          this.$nextTick(() => {
            this.initializeNetwork();
            
            // 🔥 组件挂载后，如果是首次加载，延迟2秒执行重置布局
            // 这样可以确保tags-container已经完全显示
            setTimeout(() => {
              this.loadSavedPositions();
              const isFirstLoad = !this.savedPositions || Object.keys(this.savedPositions).length === 0;
              
              if (this.quadrantModeEnabled() || readQuadrantPicture()) {
                return;
              }
              if (isFirstLoad && this.nodes && this.nodes.length > 0) {
                console.log('[KeywordNetworkGraph] 🔥 组件挂载且首次加载，将在2秒后自动执行重置布局');
                
                // 清除之前的延迟定时器（如果存在）
                if (this.firstLoadResetTimer) {
                  clearTimeout(this.firstLoadResetTimer);
                }
                
                // 延迟2秒后执行重置布局（确保tags-container已经完全显示）
                this.firstLoadResetTimer = setTimeout(() => {
                  console.log('[KeywordNetworkGraph] 🔥 执行首次加载自动重置布局');
                  
                  // 再次确认是首次加载（防止在延迟期间用户已经保存了位置）
                  this.loadSavedPositions();
                  const stillFirstLoad = !this.savedPositions || Object.keys(this.savedPositions).length === 0;
                  if (!stillFirstLoad) {
                    console.log('[KeywordNetworkGraph] ⚠️ 延迟期间已有保存位置，取消重置');
                    this.firstLoadResetTimer = null;
                    return;
                  }
                  
                  // 停止当前的模拟（如果还在运行）
                  if (this.simulation) {
                    this.simulation.stop();
                  }
                  
                  // 清除保存的位置（确保是真正的首次加载）
                  this.savedPositions = {};
                  localStorage.removeItem(this.getPositionsStorageKeyForLimit(this.getActiveNodeLimit()));
                  localStorage.removeItem(`keywordNetworkPositions_${this.getStorageKey()}`);
                  
                  // 清除所有节点的固定位置，让力导向布局重新计算
                  this.nodes.forEach(node => {
                    node.fx = undefined;
                    node.fy = undefined;
                  });
                  
                  // 清除基准viewBox范围，让布局重新计算
                  this.baseViewBoxBounds = null;
                  
                  // 重新运行布局（完全重新计算）
                  this.initializeForceLayout();
                  
                  // 清除定时器引用
                  this.firstLoadResetTimer = null;
                }, 2000); // 延迟2秒
              }
            }, 100); // 先等待100ms确保组件完全挂载
            
            // 布局稳定后再次更新容器宽度
            setTimeout(() => {
              this.updateContainerWidth();
            }, 2500); // 等待布局稳定
          });
        } else {
          console.log('[KeywordNetworkGraph] ⚠️ 关键词为空，等待关键词数据');
        }
      } else {
        console.log('[KeywordNetworkGraph] ⚠️ viewMode不是network，当前模式:', this.viewMode);
      }
      
      // 监听窗口大小变化
      window.addEventListener('resize', this.handleResize);
    } catch (error) {
      console.error('[KeywordNetworkGraph] ❌ mounted 时发生错误:', error);
      console.error('[KeywordNetworkGraph] 错误堆栈:', error.stack);
    }
  },
    beforeUnmount() {
      if (this.quadrantPlaceMode) {
        this.saveQuadrantView();
        this.persistQuadrantMode(true);
      }
      this.forceLayoutToken = (this.forceLayoutToken || 0) + 1;
      // 保存节点位置
    this.savePositions();
    
    // 🔥 清除首次加载重置定时器
    if (this.firstLoadResetTimer) {
      clearTimeout(this.firstLoadResetTimer);
      this.firstLoadResetTimer = null;
    }
    
    // 🔥 移除文档点击事件监听
    document.removeEventListener('click', this.handleDocumentClick);
    document.removeEventListener('contextmenu', this.handleDocumentClick);
    
    // 清理
    if (this.simulation) {
      this.simulation.stop();
    }
    
    window.removeEventListener('resize', this.handleResize);
  },
  methods: {
    /** 大本体悬停：从四色/DMT 映射取展示文案 */
    tooltipOntologyAttrs(label) {
      const kw = String(label || '').trim();
      const data = (this.keywordFourColorDMTData || {})[kw]
        || (this.keywordFourColorDMTData || {})[label]
        || {};
      const colorMap = { R: '红', B: '蓝', P: '紫', G: '绿' };
      const ktMap = { trad: '传统', org: '组织', trib: '部落' };
      const fc = String(data.four_color_type || '').trim().toUpperCase();
      const dmt = String(data.dmt_level || '').trim().toUpperCase();
      const kt = String(data.knowledge_type || '').trim().toLowerCase();
      return {
        color: colorMap[fc] || fc || '',
        dmt: dmt || '',
        kt: ktMap[kt] || kt || '',
      };
    },

    /** 从 prop / semanticMeta 同步四色DMT到本地。
     * 大本体：以 prop/meta 为准（属性常晚到）。
     * 本子级：禁止用空对象整表覆盖；已有本地数据优先，避免切换节点数/取用策略时被冲掉变「全淡紫」。
     */
    syncKeywordFourColorDMTFromProp() {
      const fromProp = this.keywordFourColorDMT && typeof this.keywordFourColorDMT === 'object'
        ? this.keywordFourColorDMT
        : {};
      const fromMeta = (this.semanticReorganizeMeta
        && this.semanticReorganizeMeta.keywordFourColorDMT
        && typeof this.semanticReorganizeMeta.keywordFourColorDMT === 'object')
        ? this.semanticReorganizeMeta.keywordFourColorDMT
        : {};
      const incoming = { ...fromMeta, ...fromProp };
      let incomingCopy = {};
      try {
        incomingCopy = JSON.parse(JSON.stringify(incoming));
      } catch (e) {
        incomingCopy = { ...incoming };
      }
      const incomingCount = Object.keys(incomingCopy).length;
      const local = this.keywordFourColorDMTData && typeof this.keywordFourColorDMTData === 'object'
        ? this.keywordFourColorDMTData
        : {};
      const localCount = Object.keys(local).length;

      if (this.isOntologyScopeMode) {
        // 大本体：有入参才覆盖；入参为空时保留本地（防晚到前被清空）
        if (incomingCount > 0) {
          this.keywordFourColorDMTData = incomingCopy;
        }
      } else if (incomingCount === 0) {
        // 本子级：prop 空则绝不覆盖本地（CardGrid 常靠 updateKeywordFourColorDMT 推送）
      } else {
        // 本子级：入参打底，本地已有有效属性的词优先保留
        const merged = { ...incomingCopy };
        Object.keys(local).forEach((kw) => {
          const L = local[kw];
          if (L && (L.four_color_type || L.dmt_level || L.knowledge_type)) {
            merged[kw] = { ...(merged[kw] || {}), ...L };
          }
        });
        this.keywordFourColorDMTData = merged;
        this.loadLocalUpdatedKeywordsFromStorage();
      }
      return Object.keys(this.keywordFourColorDMTData || {}).length || localCount;
    },

    /** 按当前 keywordFourColorDMTData 重刷节点颜色/描边/知识圈字段（不重建布局） */
    refreshNodeVisualFromAttrs() {
      if (!this.nodes || this.nodes.length === 0) return;
      const counts = this.nodes.map((n) => n.cardCount || 0);
      const minCount = Math.min(...counts, 1);
      const maxCount = Math.max(...counts, 1);
      this.nodes.forEach((node) => {
        const kw = node.label;
        const keywordData = (this.keywordFourColorDMTData || {})[kw] || {};
        const isSelected = (this.selectedKeywords || []).includes(kw);
        const colors = this.getNodeColors(kw, node.cardCount || 0, minCount, maxCount, isSelected);
        node.color = colors.color;
        node.stroke = colors.stroke;
        node.strokeWidth = colors.strokeWidth;
        node.dmtLevel = keywordData.dmt_level || node.dmtLevel || '';
        node.knowledgeType = keywordData.knowledge_type || node.knowledgeType || '';
        const isTribalKw = (this.tribalKeywords || []).includes(kw)
          || String(node.knowledgeType || '').toLowerCase() === 'trib';
        node.isTribal = !!isTribalKw;
      });
    },
    

    // 🔥 从localStorage加载本地更新的关键词数据
    loadLocalUpdatedKeywordsFromStorage() {
      // 大本体不读本子级 localStorage，避免污染/覆盖场景属性
      if (this.isOntologyScopeMode) return;
      try {
        const sceneName = this.sceneName || '';
        const username = localStorage.getItem('userId') || '';
        const storageKey = `keyword_dmt_local_updates_${username}_${sceneName}`;
        const savedData = localStorage.getItem(storageKey);
        
        if (savedData) {
          const localUpdates = JSON.parse(savedData);
          // 合并到keywordFourColorDMTData
          Object.keys(localUpdates).forEach(keyword => {
            if (!this.keywordFourColorDMTData[keyword]) {
              this.keywordFourColorDMTData[keyword] = {};
            }
            this.keywordFourColorDMTData[keyword].four_color_type = localUpdates[keyword].four_color_type || this.keywordFourColorDMTData[keyword].four_color_type || '';
            this.keywordFourColorDMTData[keyword].dmt_level = localUpdates[keyword].dmt_level || this.keywordFourColorDMTData[keyword].dmt_level || '';
            this.keywordFourColorDMTData[keyword].knowledge_type = localUpdates[keyword].knowledge_type || this.keywordFourColorDMTData[keyword].knowledge_type || '';
            // 标记为本地更新
            this.locallyUpdatedKeywords.add(keyword);
          });
          console.log('[KeywordNetworkGraph] 从localStorage加载本地更新，关键词数:', Object.keys(localUpdates).length);
        }
      } catch (e) {
        console.warn('[KeywordNetworkGraph] 加载本地更新失败:', e);
      }
    },
    
    // 🔥 保存本地更新的关键词数据到localStorage
    saveLocalUpdatedKeywordsToStorage(keyword, fourColorType, dmtLevel, knowledgeType) {
      try {
        // 大本体结果已落盘，不写入本子级 localStorage，避免污染
        if (this.isOntologyScopeMode) return;
        const sceneName = this.sceneName || '';
        const username = localStorage.getItem('userId') || '';
        const storageKey = `keyword_dmt_local_updates_${username}_${sceneName}`;
        const savedData = localStorage.getItem(storageKey);
        const localUpdates = savedData ? JSON.parse(savedData) : {};
        
        if (!localUpdates[keyword]) {
          localUpdates[keyword] = {};
        }
        localUpdates[keyword].four_color_type = fourColorType || '';
        localUpdates[keyword].dmt_level = dmtLevel || '';
        localUpdates[keyword].knowledge_type = knowledgeType || '';
        
        localStorage.setItem(storageKey, JSON.stringify(localUpdates));
        console.log('[KeywordNetworkGraph] 保存本地更新到localStorage，关键词:', keyword);
      } catch (e) {
        console.warn('[KeywordNetworkGraph] 保存本地更新失败:', e);
      }
    },
    
    // 🔥 直接从父组件调用更新数据的方法
    updateKeywordFourColorDMT(data) {
      console.log('[KeywordNetworkGraph] updateKeywordFourColorDMT 被调用，数据键数量:', Object.keys(data || {}).length);
      if (data && typeof data === 'object' && Object.keys(data).length > 0) {
        const newData = JSON.parse(JSON.stringify(data));
        
        // 🔥 先加载localStorage中的本地更新数据
        this.loadLocalUpdatedKeywordsFromStorage();
        
        // 🔥 合并数据：保留本地已通过API更新的关键词数据，避免被覆盖
        const mergedData = { ...newData };
        
        // 对于本地已更新的关键词，保留本地的数据
        this.locallyUpdatedKeywords.forEach(keyword => {
          const localData = this.keywordFourColorDMTData[keyword];
          if (localData && (localData.four_color_type || localData.dmt_level || localData.knowledge_type)) {
            mergedData[keyword] = {
              four_color_type: localData.four_color_type || (newData[keyword] && newData[keyword].four_color_type) || '',
              dmt_level: localData.dmt_level || (newData[keyword] && newData[keyword].dmt_level) || '',
              knowledge_type: localData.knowledge_type || (newData[keyword] && newData[keyword].knowledge_type) || ''
            };
          }
        });
        
        this.keywordFourColorDMTData = mergedData;
        console.log('[KeywordNetworkGraph] 数据合并更新成功，键数量:', Object.keys(this.keywordFourColorDMTData).length, '保留本地更新数:', this.locallyUpdatedKeywords.size);
        
        // 🔥 重新计算节点（包括大小和颜色），因为四色/DMT数据已更新
        if (this.viewMode === 'network' && this.graphKeywordPool.length > 0) {
          const keywordsToShow = this.getDisplayKeywords(this.graphKeywordPool, this.getActiveNodeLimit());
          
          // 🔥 保存已有节点的固定位置（fx/fy），以便重新计算后恢复
          const fixedPositions = new Map();
          this.nodes.forEach(node => {
            if (node.fx !== undefined && node.fy !== undefined) {
              fixedPositions.set(node.label, { fx: node.fx, fy: node.fy });
            }
          });
          
          // 重新计算节点（会应用新的四色/DMT属性，包括半径和颜色）
          this.nodes = this.calculateNodes(keywordsToShow);
          this.links = this.calculateLinks(keywordsToShow);
          
          // 🔥 恢复已有节点的固定位置
          this.nodes.forEach(node => {
            const fixedPos = fixedPositions.get(node.label);
            if (fixedPos) {
              node.x = fixedPos.fx;
              node.y = fixedPos.fy;
              node.fx = fixedPos.fx;
              node.fy = fixedPos.fy;
            }
          });
          
          this.loadSavedPositions();
          this.restorePositions();
          this.updateLinkPositions();
          this.updateNodePositions();
        }
      }
    },
    
    toggleView() {
      this.viewMode = this.viewMode === 'network' ? 'flat' : 'network';
      if (this.viewMode === 'network') {
        this.$nextTick(() => {
          this.initializeNetwork();
        });
      }
    },
    
    toggleKeywordSelection(keyword) {
      // 🔥 如果刚刚结束拖拽，不触发点击事件
      if (this.justEndedDrag) {
        return;
      }
      
      // 🔥 先预测下一个选中状态（用于立即更新颜色）
      const willBeSelected = !this.selectedKeywords.includes(keyword);
      
      this.$emit('toggle-keyword', keyword);
      
      // 🔥 立即基于预测状态更新节点颜色，不等待watch触发
      if (this.nodes && this.nodes.length > 0) {
        const counts = this.nodes.map(node => node.cardCount || 0);
        const minCount = Math.min(...counts, 1);
        const maxCount = Math.max(...counts, 1);
        
        const targetNode = this.nodes.find(node => node.label === keyword);
        if (targetNode) {
          const colors = this.getNodeColors(
            keyword,
            targetNode.cardCount || 0,
            minCount,
            maxCount,
            willBeSelected
          );
          targetNode.color = colors.color;
          targetNode.stroke = colors.stroke;
          targetNode.strokeWidth = colors.strokeWidth;
        }
        
        // 立即强制更新视图
        this.$forceUpdate();
        this.updateNodePositions();
      }
    },
    
    // 设置筛选策略
    setFilterStrategy(strategy) {
      if (strategy === 'union' || strategy === 'intersection') {
        // 立即更新本地状态（用于按钮显示）
        this.localFilterStrategy = strategy;
        // 将策略传递给父组件
        this.$emit('filter-strategy-change', strategy);
      }
    },
    
    initializeNetwork() {
      console.log('[initializeNetwork] ========== 方法被调用 ==========');
      console.log('[initializeNetwork] keywords:', this.keywords);
      console.log('[initializeNetwork] keywords类型:', typeof this.keywords);
      console.log('[initializeNetwork] keywords长度:', this.keywords ? this.keywords.length : 'null/undefined');

      // 大本体：初始化前从 prop 同步属性（属性常晚到）
      // 本子级：仅在本地尚无属性时补同步；绝不用空 prop 覆盖 CardGrid 已推送的数据
      if (this.isOntologyScopeMode) {
        const syncedKeys = this.syncKeywordFourColorDMTFromProp();
        console.log('[initializeNetwork] 大本体同步后 keywordFourColorDMT 键数:', syncedKeys);
      } else {
        const localKeys = Object.keys(this.keywordFourColorDMTData || {}).length;
        if (localKeys <= 0) {
          const syncedKeys = this.syncKeywordFourColorDMTFromProp();
          this.loadLocalUpdatedKeywordsFromStorage();
          console.log('[initializeNetwork] 本子级补同步 keywordFourColorDMT 键数:', syncedKeys);
        } else {
          console.log('[initializeNetwork] 本子级保留本地 keywordFourColorDMT 键数:', localKeys);
        }
      }
      
      if (!this.graphKeywordPool.length) {
        console.log('[initializeNetwork] ❌ 关键词为空，跳过初始化');
        return;
      }
      
      console.log('[initializeNetwork] ✅ 开始初始化网络图，关键词数量:', this.keywords.length);
      console.log('[initializeNetwork] initialKeywords:', this.initialKeywords);
      
      // 🔥 智能筛选30个关键词：确保四种颜色、DMT类型都有，且尽可能包含新生成的关键词
      const keywordsToShow = this.getDisplayKeywords(this.graphKeywordPool, this.getActiveNodeLimit());
      
      console.log('[initializeNetwork] keywordsToShow数量:', keywordsToShow.length);
      
      // 🔥 检查keywordFourColorDMTData是否已有数据
      const hasDMTData = this.keywordFourColorDMTData && Object.keys(this.keywordFourColorDMTData).length > 0;
      console.log('[initializeNetwork] keywordFourColorDMTData键数量:', hasDMTData ? Object.keys(this.keywordFourColorDMTData).length : 0);
      
      try {
        // 计算节点数据（会应用四色/DMT属性，包括半径和颜色）
        this.nodes = this.calculateNodes(keywordsToShow);
        // 再刷一次视觉属性，防止偶发未带上四色/知识圈
        this.refreshNodeVisualFromAttrs();
        console.log('[initializeNetwork] ✅ 计算完成，节点数量:', this.nodes.length);
        
        // 🔥 调试：检查节点大小是否应用了调整
        if (hasDMTData) {
          const adjustedNodes = this.nodes.filter(node => {
            const keywordData = this.keywordFourColorDMTData[node.label] || {};
            const fourColorType = keywordData.four_color_type || '';
            const dmtLevel = keywordData.dmt_level || '';
            const cardCount = node.cardCount || 0;
            const maxCount = Math.max(...this.nodes.map(n => n.cardCount || 0), 1);
            const minCount = Math.min(...this.nodes.map(n => n.cardCount || 0), 1);
            const frequencyRatio = maxCount > minCount ? (cardCount - minCount) / (maxCount - minCount) : 1;
            const isLowFrequency = frequencyRatio <= (1/3);
            return isLowFrequency && ((fourColorType === 'P' || fourColorType === 'G') || dmtLevel === 'T');
          });
          console.log('[initializeNetwork] 应该应用大小调整的节点数量:', adjustedNodes.length);
          if (adjustedNodes.length > 0) {
            console.log('[initializeNetwork] 调整后的节点半径示例:', adjustedNodes[0].radius);
          }
        }
      } catch (error) {
        console.error('[initializeNetwork] ❌ 计算节点时出错:', error);
        throw error;
      }
      
      // 计算连接数据
      this.links = this.calculateLinks(keywordsToShow);
      
      // 🔥 恢复保存的位置（确保每次初始化都加载保存的位置）
      this.loadSavedPositions();

      if (this.quadrantModeEnabled()) {
        this.quadrantPlaceMode = true;
        if (!this.restoreSavedQuadrantView()) {
          if (!this.forceLayoutSnapshot || !Object.keys(this.forceLayoutSnapshot).length) {
            const snap = {};
            (this.nodes || []).forEach((node) => {
              if (!node || node.label == null) return;
              const saved = this.savedPositions && this.savedPositions[node.label];
              const x = saved && saved.x != null ? saved.x : node.x;
              const y = saved && saved.y != null ? saved.y : node.y;
              if (x == null || y == null) return;
              snap[node.label] = { x, y };
            });
            if (Object.keys(snap).length) this.forceLayoutSnapshot = snap;
          }
          this.applyQuadrantPlacement();
        }
        if (this.simulation) this.simulation.stop();
        this.forceLayoutToken = (this.forceLayoutToken || 0) + 1;
        this.updateContainerWidth();
        this.$forceUpdate();
        return;
      }
      
      // 🔥 检测是否是首次加载（本子内纯首次加载，没有任何保存的位置）
      const isFirstLoad = !this.savedPositions || Object.keys(this.savedPositions).length === 0;
      
      // 初始化D3力导向布局（在恢复位置之前先初始化，确保布局能正确运行）
      this.$nextTick(() => {
        this.quadrantPlaceMode = this.quadrantModeEnabled();
        if (isFirstLoad) {
          // 🔥 首次加载时，先执行一次布局（让节点先显示出来）
          this.restorePositions(false);
          if (this.quadrantPlaceMode) this.showQuadrantNow();
          this.initializeForceLayout();
          
          // 🔥 注意：首次加载的自动重置布局现在由viewMode的watch来处理
          // 这样可以确保在tags-container显示后才开始计时
          console.log('[initializeNetwork] 🔥 检测到首次加载，viewMode watch会处理延迟重置');
        } else {
          // 非首次加载：先恢复位置（但不固定，让布局先运行）
          this.restorePositions(false);
          if (this.quadrantPlaceMode) this.showQuadrantNow();
          // 然后初始化力导向布局
          this.initializeForceLayout();
        }
      });
    },
    
    // 🔥 智能筛选关键词：确保四种颜色、DMT类型都有，且尽可能包含新生成的关键词
    // 🔥 获取节点的四色属性颜色
    getNodeFourColor(node) {
      const keywordDMTData = this.keywordFourColorDMTData || {};
      const keywordData = keywordDMTData[node.label] || {};
      const fourColorType = keywordData.four_color_type || '';
      
      const colorMap = {
        'R': '#dc143c',  // Crimson
        'B': '#1e90ff',  // DodgerBlue
        'P': '#9370db',  // MediumPurple
        'G': '#3cb371'   // MediumSeaGreen
      };
      
      return colorMap[fourColorType] || '#999'; // 默认灰色
    },
    
    // 🔥 计算箭头起点（在节点左上角外侧，使用绝对坐标）
    getArrowStart(node) {
      const radius = node.radius || 10;
      const offset = radius + 20; // 距离节点边缘的距离
      
      // 箭头起点在节点左上角外侧
      // SVG坐标系：x向右为正，y向下为正
      // 左上角：x向左（减小），y向上（减小）
      return {
        x: node.x - offset,
        y: node.y - offset
      };
    },
    
    // 🔥 计算箭头终点（箭头头部指向节点边缘，使用绝对坐标）
    getArrowEnd(node) {
      const radius = node.radius || 10;
      const start = this.getArrowStart(node);
      
      // 箭头从起点指向节点中心
      const dx = node.x - start.x;
      const dy = node.y - start.y;
      const distance = Math.sqrt(dx * dx + dy * dy);
      
      // 归一化方向向量
      const normDx = dx / distance;
      const normDy = dy / distance;
      
      // 终点在节点边缘（从节点中心向起点方向回退radius距离）
      return {
        x: node.x - normDx * radius,
        y: node.y - normDy * radius
      };
    },
    
    // 🔥 计算箭头头部两个点的位置（V形，使用绝对坐标）
    getArrowTipPoints(node) {
      const end = this.getArrowEnd(node);
      const start = this.getArrowStart(node);
      
      // 计算箭头方向（从起点指向终点）
      const dx = end.x - start.x;
      const dy = end.y - start.y;
      const angle = Math.atan2(dy, dx);
      
      const tipLength = 7; // 箭头头部长度
      const tipWidth = 5; // 箭头头部宽度的一半
      
      // 箭头头部在终点位置，向后延伸tipLength形成V形
      const tipBaseX = end.x - Math.cos(angle) * tipLength;
      const tipBaseY = end.y - Math.sin(angle) * tipLength;
      
      // 计算箭头头部的两个点（与箭头方向垂直）
      const perpAngle = angle + Math.PI / 2; // 垂直方向
      
      return {
        left: {
          x: tipBaseX + Math.cos(perpAngle) * tipWidth,
          y: tipBaseY + Math.sin(perpAngle) * tipWidth
        },
        right: {
          x: tipBaseX - Math.cos(perpAngle) * tipWidth,
          y: tipBaseY - Math.sin(perpAngle) * tipWidth
        }
      };
    },
    
    // getSmartFilteredKeywords(keywords, maxCount = 25) {
    //   if (!keywords || keywords.length === 0) {
    //     return [];
    //   }
      
    //   if (keywords.length <= maxCount) {
    //     return keywords;
    //   }
      
    //   // 准备数据
    //   const keywordFourColorDMTData = this.keywordFourColorDMTData || {};
      
    //   // 🔥 计算每个关键词的首次出现时间（包含该关键词的卡片中datetime最早的）
    //   const keywordFirstAppearance = {};
    //   keywords.forEach(keyword => {
    //     let earliestDate = null;
    //     this.effectiveCards.forEach(card => {
    //       if (!card.keyWords) return;
    //       const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
    //       if (cardKeywords.includes(keyword) && card.datetime) {
    //         const cardDate = new Date(card.datetime);
    //         if (!earliestDate || cardDate < earliestDate) {
    //           earliestDate = cardDate;
    //         }
    //       }
    //     });
    //     keywordFirstAppearance[keyword] = earliestDate;
    //   });
      
    //   // 🔥 按首次出现时间排序（最近的在前，null值排在最后）
    //   const sortedByTime = [...keywords].sort((a, b) => {
    //     const dateA = keywordFirstAppearance[a];
    //     const dateB = keywordFirstAppearance[b];
    //     if (!dateA && !dateB) return 0;
    //     if (!dateA) return 1; // A没有日期，排后面
    //     if (!dateB) return -1; // B没有日期，排后面
    //     return dateB - dateA; // 降序：最近的在前
    //   });
      
    //   // 分类关键词
    //   const colorGroups = { 'R': [], 'B': [], 'P': [], 'G': [], 'none': [] };
    //   const dmtGroups = { 'D': [], 'M': [], 'T': [], 'none': [] };
      
    //   keywords.forEach(keyword => {
    //     const keywordData = keywordFourColorDMTData[keyword] || {};
    //     const fourColorType = keywordData.four_color_type || '';
    //     const dmtLevel = keywordData.dmt_level || '';
        
    //     // 按颜色分类
    //     if (fourColorType && colorGroups[fourColorType]) {
    //       colorGroups[fourColorType].push(keyword);
    //     } else {
    //       colorGroups['none'].push(keyword);
    //     }
        
    //     // 按DMT分类
    //     if (dmtLevel && dmtGroups[dmtLevel]) {
    //       dmtGroups[dmtLevel].push(keyword);
    //     } else {
    //       dmtGroups['none'].push(keyword);
    //     }
    //   });
      
    //   // 🔥 智能选择关键词
    //   const selected = new Set();
      
    //   // 🔥 0. 最高优先级：保留当前显示的节点（特别是用户手动修改过的）
    //   // 这样可以确保用户手动修改四色/DMT后，节点不会突然消失
    //   const currentDisplayedKeywords = new Set(
    //     (this.nodes || []).map(node => node.label)
    //   );
    //   const userModifiedKeywords = this.locallyUpdatedKeywords || new Set();
      
    //   // 优先保留当前显示的节点（特别是用户修改过的）
    //   keywords.forEach(keyword => {
    //     if (currentDisplayedKeywords.has(keyword)) {
    //       // 如果是用户修改过的关键词，必须保留
    //       if (userModifiedKeywords.has(keyword)) {
    //         selected.add(keyword);
    //       }
    //       // 其他当前显示的节点也优先保留（但可能被后续逻辑调整）
    //     }
    //   });
      
    //   // 1. 优先选择生成时间最近的3个关键词（但不替换已保留的）
    //   sortedByTime.slice(0, 3).forEach(k => {
    //     if (keywords.includes(k)) {
    //       selected.add(k);
    //     }
    //   });
      
    //   // 2. 确保每种颜色至少有一个代表（优先从生成时间最近的中选择）
    //   ['R', 'B', 'P', 'G'].forEach(color => {
    //     if (colorGroups[color].length > 0) {
    //       // 优先从生成时间最近的未选中关键词中选择
    //       const keywordToAdd = sortedByTime.find(k => colorGroups[color].includes(k) && !selected.has(k));
    //       if (keywordToAdd) {
    //         selected.add(keywordToAdd);
    //       }
    //     }
    //   });
      
    //   // 3. 确保每种DMT类型至少有一个代表
    //   ['D', 'M', 'T'].forEach(dmt => {
    //     if (dmtGroups[dmt].length > 0) {
    //       const keywordToAdd = sortedByTime.find(k => dmtGroups[dmt].includes(k) && !selected.has(k));
    //       if (keywordToAdd) {
    //         selected.add(keywordToAdd);
    //       }
    //     }
    //   });
      
    //   // 4. 🔥 绿色节点可以稍多些（因为绿色节点总共都会很少）
    //   // 如果有绿色节点且还没有达到maxCount，可以多选一些绿色节点
    //   if (colorGroups['G'].length > 0) {
    //     const greenNotSelected = colorGroups['G'].filter(k => !selected.has(k));
    //     const currentGreenCount = Array.from(selected).filter(k => {
    //       const keywordData = keywordFourColorDMTData[k] || {};
    //       return keywordData.four_color_type === 'G';
    //     }).length;
        
    //     // 如果绿色节点数量较少（<=5个），可以多选一些（最多再选3个）
    //     if (greenNotSelected.length > 0 && currentGreenCount < 5 && selected.size < maxCount) {
    //       const additionalGreen = greenNotSelected.slice(0, Math.min(3, maxCount - selected.size));
    //       additionalGreen.forEach(k => selected.add(k));
    //     }
    //   }
      
    //   // 5. 如果用户修改过的关键词还未被选中，必须添加（即使超过maxCount也要保留）
    //   userModifiedKeywords.forEach(keyword => {
    //     if (keywords.includes(keyword) && !selected.has(keyword)) {
    //       selected.add(keyword);
    //     }
    //   });
      
    //   // 6. 从剩余关键词中补充到maxCount个（如果未达到maxCount）
    //   if (selected.size < maxCount) {
    //     const remaining = sortedByTime.filter(k => !selected.has(k) && keywords.includes(k));
    //     const needed = maxCount - selected.size;
    //     remaining.slice(0, needed).forEach(k => selected.add(k));
    //   }
      
    //   // 🔥 如果用户修改过的关键词导致超过maxCount，也保留它们（最多允许到maxCount+5）
    //   const finalSelected = Array.from(selected);
    //   const userModifiedNotIncluded = Array.from(userModifiedKeywords).filter(
    //     k => keywords.includes(k) && !finalSelected.includes(k)
    //   );
    //   if (userModifiedNotIncluded.length > 0 && finalSelected.length < maxCount + 5) {
    //     userModifiedNotIncluded.slice(0, maxCount + 5 - finalSelected.length).forEach(k => {
    //       finalSelected.push(k);
    //     });
    //   }
      
    //   return finalSelected;
    // },

    getActiveNodeLimit() {
      const total = this.totalKeywordCount;
      if (total <= 0) return DEFAULT_NODE_DISPLAY_LIMIT;
      // 大本体：默认展示全部关键词（无本子卡片频率可筛）
      if (this.isOntologyScopeMode) {
        return Math.min(total, this.maxNodeDisplayOption);
      }
      const capped = Math.min(this.nodeDisplayLimit, this.maxNodeDisplayOption);
      return Math.min(capped, total);
    },

    getNodeLimitPreferenceKey() {
      return `keywordNetworkNodeLimit_${this.getStorageKey()}`;
    },

    getPositionsStorageKeyForLimit(limit) {
      const n = limit != null ? limit : this.getActiveNodeLimit();
      return `keywordNetworkPositions_${this.getStorageKey()}_n${n}`;
    },

    loadNodeDisplayLimitPreference() {
      try {
        const raw = localStorage.getItem(this.getNodeLimitPreferenceKey());
        if (!raw) return DEFAULT_NODE_DISPLAY_LIMIT;
        const n = parseInt(raw, 10);
        if (Number.isNaN(n)) return DEFAULT_NODE_DISPLAY_LIMIT;
        return Math.min(Math.max(n, MIN_NODE_DISPLAY_OPTION), this.maxNodeDisplayOption);
      } catch (e) {
        return DEFAULT_NODE_DISPLAY_LIMIT;
      }
    },

    saveNodeDisplayLimitPreference(limit) {
      try {
        localStorage.setItem(this.getNodeLimitPreferenceKey(), String(limit));
      } catch (e) {
        console.warn('[KeywordNetworkGraph] 保存节点数量偏好失败:', e);
      }
    },

    applyNodeDisplayLimit(limit) {
      const nextLimit = Math.min(Math.max(limit, MIN_NODE_DISPLAY_OPTION), this.maxNodeDisplayOption);
      if (nextLimit === this.nodeDisplayLimit) {
        this.showNodeCountDialog = false;
        return;
      }
      if (this.nodes && this.nodes.length > 0) {
        this.savePositions(this.nodeDisplayLimit);
      }
      this.nodeDisplayLimit = nextLimit;
      this.saveNodeDisplayLimitPreference(nextLimit);
      this.showNodeCountDialog = false;
      this.loadSavedPositions(nextLimit);
      this.initializeNetwork();
    },

    getKeywordPickStrategyPreferenceKey() {
      return `keywordNetworkPickStrategy_${this.getStorageKey()}`;
    },

    loadKeywordPickStrategyPreference() {
      if (String(this.semanticReorganizeMeta?.pipeline || '').startsWith('v3')) {
        return KEYWORD_PICK_STRATEGIES.default;
      }
      try {
        const raw = localStorage.getItem(this.getKeywordPickStrategyPreferenceKey());
        if (raw === KEYWORD_PICK_STRATEGIES.top3 || raw === KEYWORD_PICK_STRATEGIES.top5) {
          return raw;
        }
      } catch (e) { /* ignore */ }
      return KEYWORD_PICK_STRATEGIES.default;
    },

    saveKeywordPickStrategyPreference(strategy) {
      try {
        localStorage.setItem(this.getKeywordPickStrategyPreferenceKey(), strategy);
      } catch (e) {
        console.warn('[KeywordNetworkGraph] 保存取用策略失败:', e);
      }
    },

    applyKeywordPickStrategy(strategy) {
      if (this.isV3Pipeline) {
        strategy = KEYWORD_PICK_STRATEGIES.default;
      }
      const next = (
        strategy === KEYWORD_PICK_STRATEGIES.top3
        || strategy === KEYWORD_PICK_STRATEGIES.top5
      ) ? strategy : KEYWORD_PICK_STRATEGIES.default;
      this.showKeywordPickStrategyDialog = false;
      if (next === this.keywordPickStrategy) return;
      if (this.nodes && this.nodes.length > 0) {
        this.savePositions();
      }
      this.keywordPickStrategy = next;
      this.saveKeywordPickStrategyPreference(next);
      this.initializeNetwork();
    },

    /** 统一入口：按当前取用策略决定展示哪些关键词 */
    getDisplayKeywords(keywords, maxCount = DEFAULT_NODE_DISPLAY_LIMIT) {
      if (this.isV3Pipeline) {
        return this.getV3DisplayKeywords(keywords, maxCount);
      }
      if (
        this.isOntologyScopeMode
        || this.keywordPickStrategy === KEYWORD_PICK_STRATEGIES.default
      ) {
        return this.getSmartFilteredKeywords(keywords, maxCount);
      }
      const topN = this.keywordPickStrategy === KEYWORD_PICK_STRATEGIES.top5 ? 5 : 3;
      return this.getTopNKeywordsByCardStrategy(keywords, maxCount, topN);
    },

    parseCardKeywordList(card) {
      if (!card || !card.keyWords) return [];
      return String(card.keyWords)
        .split(/[,，]/)
        .map((k) => k.trim())
        .filter(Boolean);
    },

    cardAnalysisPickScore(card) {
      let s = 0;
      if ((card.four_color_type || '').trim()) s += 100;
      if ((card.dmt_level || '').trim()) s += 50;
      const shallow = Number(card.score) || 0;
      const deep = Number(card.deep_score != null ? card.deep_score : card.score2) || 0;
      s += shallow * 8 + deep * 12;
      const kws = this.parseCardKeywordList(card);
      s += Math.min(kws.length, 12) * 3;
      if (card.datetime) {
        const t = new Date(card.datetime).getTime();
        if (!Number.isNaN(t)) s += t / 1e13;
      }
      return s;
    },

    /** 参与分析的卡片池：优先 reorganize 选中集，最多 60 */
    getAnalysisCardsPool() {
      let cards = (this.effectiveCards || []).filter((c) => this.parseCardKeywordList(c).length > 0);
      if (!cards.length) {
        cards = (this.cards || []).filter((c) => this.parseCardKeywordList(c).length > 0);
      }
      if (cards.length <= ANALYSIS_CARD_POOL_CAP) return cards;
      return [...cards]
        .sort((a, b) => this.cardAnalysisPickScore(b) - this.cardAnalysisPickScore(a))
        .slice(0, ANALYSIS_CARD_POOL_CAP);
    },

    /**
     * 取前 N 词策略：精选 xx 张卡（N×xx≈节点数），每张取前 N 个语义关键词。
     * 精选：优先高质卡，并尽量让前 N 词带来新词（多样性）。
     */
    getTopNKeywordsByCardStrategy(keywordsPool, maxCount, topN) {
      if (this.isV3Pipeline) {
        return this.getV3DisplayKeywords(keywordsPool, maxCount);
      }
      const poolAllowed = new Set((keywordsPool || []).filter(Boolean));
      const cards = this.getAnalysisCardsPool();
      if (!cards.length || maxCount <= 0) {
        return this.getSmartFilteredKeywords(keywordsPool, maxCount);
      }

      const cardTarget = Math.max(1, Math.floor(maxCount / topN));
      const ranked = [...cards].sort(
        (a, b) => this.cardAnalysisPickScore(b) - this.cardAnalysisPickScore(a)
      );

      const selectedCards = [];
      const selectedIds = new Set();
      const collected = [];
      const seen = new Set();

      const tryAddCard = (card) => {
        const cid = Number(card.cid);
        if (selectedIds.has(cid)) return 0;
        const tops = this.parseCardKeywordList(card)
          .slice(0, topN)
          .filter((k) => !poolAllowed.size || poolAllowed.has(k));
        let added = 0;
        tops.forEach((k) => {
          if (!seen.has(k)) {
            seen.add(k);
            collected.push(k);
            added += 1;
          }
        });
        selectedIds.add(cid);
        selectedCards.push(card);
        return added;
      };

      // 第一轮：贪心挑出约 cardTarget 张（优先带来新词的高分卡）
      while (selectedCards.length < cardTarget && selectedIds.size < ranked.length) {
        let best = null;
        let bestNew = -1;
        let bestScore = -Infinity;
        for (const card of ranked) {
          const cid = Number(card.cid);
          if (selectedIds.has(cid)) continue;
          const tops = this.parseCardKeywordList(card)
            .slice(0, topN)
            .filter((k) => !poolAllowed.size || poolAllowed.has(k));
          const newCount = tops.filter((k) => !seen.has(k)).length;
          const score = this.cardAnalysisPickScore(card);
          if (
            newCount > bestNew
            || (newCount === bestNew && score > bestScore)
          ) {
            best = card;
            bestNew = newCount;
            bestScore = score;
          }
        }
        if (!best) break;
        // 若已无新词可贡献，仍按排名补满 cardTarget（保证 3×卡数 口径）
        tryAddCard(best);
      }

      // 第二轮：去重后不足 maxCount 时，继续从剩余卡取前 N 词补齐
      if (collected.length < maxCount) {
        for (const card of ranked) {
          if (collected.length >= maxCount) break;
          if (selectedIds.has(Number(card.cid))) continue;
          tryAddCard(card);
        }
      }

      const result = collected.slice(0, maxCount);
      // 若卡词过少仍不足，回退用默认策略补足（不改变已取前缀顺序）
      if (result.length < maxCount) {
        const fallback = this.getSmartFilteredKeywords(keywordsPool, maxCount);
        fallback.forEach((k) => {
          if (result.length >= maxCount) return;
          if (!seen.has(k)) {
            seen.add(k);
            result.push(k);
          }
        });
      }
      console.log(
        `[KeywordNetworkGraph] 取前${topN}词: 池=${cards.length} 精选卡=${selectedCards.length}`
        + ` 目标卡≈${cardTarget} 词=${result.length}/${maxCount}`
      );
      return result;
    },

    flattenBookTopKeywords(meta) {
      const tops = (meta && meta.book_top_keywords) || {};
      const keys = ['top1', 'top3', 'top5', 'top10'];
      const seen = new Set();
      const out = [];
      keys.forEach((key) => {
        const raw = tops[key];
        const arr = Array.isArray(raw)
          ? raw
          : (raw != null && String(raw).trim() !== '' ? [raw] : []);
        arr.forEach((w) => {
          const s = String(w).trim();
          if (s && !seen.has(s)) {
            seen.add(s);
            out.push(s);
          }
        });
      });
      return out;
    },

    parseV3KeywordLevel(keyword, levels) {
      const lvMap = levels || {};
      let lv = lvMap[keyword];
      if (lv == null || lv === '') {
        const kwData = (this.keywordFourColorDMTData || {})[keyword] || {};
        lv = kwData.level;
      }
      const s = String(lv ?? '').trim().toUpperCase();
      const m = s.match(/^L?(\d+)$/);
      if (m) return Number(m[1]);
      return 99;
    },

    /** 解析 hierarchy_links → 邻接表（含强度分） */
    buildV3HierarchyAdjacency(meta) {
      const adj = {};
      const strengthScore = { '强': 3, '强中': 2, '普通': 1 };
      const links = Array.isArray(meta && meta.hierarchy_links) ? meta.hierarchy_links : [];
      links.forEach((pair) => {
        if (!pair || pair.length < 2) return;
        const a = String(pair[0] || '').trim();
        const b = String(pair[1] || '').trim();
        if (!a || !b || a === b) return;
        const s = String(pair[2] || '普通').trim() || '普通';
        const sc = strengthScore[s] || 1;
        if (!adj[a]) adj[a] = [];
        if (!adj[b]) adj[b] = [];
        adj[a].push({ other: b, score: sc });
        adj[b].push({ other: a, score: sc });
      });
      Object.keys(adj).forEach((k) => {
        adj[k].sort((x, y) => y.score - x.score || String(x.other).localeCompare(String(y.other), 'zh'));
      });
      return adj;
    },

    /**
     * 个数档位允许的少量溢出。1–10 档不溢出；更大档位约为所选题数的一成，最多 18 个。
     * 30→4，50→5，100→10，150→15，200→18。
     * 只用来补「第二层上、度高、强关系成团，但被枢纽邻居名额挤掉」的局部枢纽及其强链。
     */
    v3DisplayOverflowBudget(maxCount) {
      const n = Number(maxCount) || 0;
      if (n <= 10) return 0;
      const byCount = { 30: 4, 50: 5, 100: 10, 150: 15, 200: 18 };
      return byCount[n] || 0;
    },

    /**
     * 在已选集合之外追加局部枢纽。不替换已选词。
     * 先补：和已入选的第零层或第一层节点有强/强中边、自身在第二层或更深、度≥8、还有至少 3 条未入选强或强中关系的词。
     * 再补：没有挂上高层的同类枢纽。未入选强或强中邻居至少 5 条；若只有 4 条，则其中至少 1 条要是强。
     * 每个枢纽最多再带 6 个强/强中邻居。已在集合里、强链却大多没进来的第二层枢纽，用剩余名额补齐。
     */
    appendV3LocalHubOverflow(selected, pool, poolSet, adj, levelOf, maxCount) {
      const overflow = [];
      const budget = this.v3DisplayOverflowBudget(maxCount);
      if (!budget || !selected) return overflow;
      const selectedSet = new Set(selected);
      let added = 0;
      const addWord = (w) => {
        selected.push(w);
        selectedSet.add(w);
        overflow.push(w);
        added += 1;
      };
      const degreeOf = (w) => (adj[w] ? adj[w].length : 0);
      const strongHidden = (w) => (adj[w] || []).filter(
        (x) => x.score >= 2 && poolSet.has(x.other) && !selectedSet.has(x.other)
      );
      const attachScore = (w) => {
        let best = 0;
        (adj[w] || []).forEach((x) => {
          if (x.score >= 2 && selectedSet.has(x.other) && levelOf(x.other) <= 1) {
            best = Math.max(best, x.score);
          }
        });
        return best;
      };
      const chainScore = (w) => {
        const names = strongHidden(w).map((x) => x.other);
        const nameSet = new Set(names);
        let n = 0;
        names.forEach((other) => {
          (adj[other] || []).forEach((x) => {
            if (x.score >= 2 && nameSet.has(x.other) && String(x.other) > String(other)) n += 1;
          });
        });
        return n;
      };
      const qualifies = (w) => {
        if (!w || selectedSet.has(w) || !poolSet.has(w) || levelOf(w) < 2) return false;
        if (degreeOf(w) < 8) return false;
        const hiddenList = strongHidden(w);
        const hidden = hiddenList.length;
        if (attachScore(w) > 0) return hidden >= 3;
        const strongN = hiddenList.filter((x) => x.score >= 3).length;
        return hidden >= 5 || (hidden >= 4 && strongN >= 1);
      };
      const takeKids = (w) => {
        const hidden = strongHidden(w);
        const hiddenSet = new Set(hidden.map((x) => x.other));
        const ranked = hidden.slice().sort((a, b) => {
          if (b.score !== a.score) return b.score - a.score;
          const aChain = (adj[a.other] || []).some((x) => x.score >= 2 && hiddenSet.has(x.other)) ? 1 : 0;
          const bChain = (adj[b.other] || []).some((x) => x.score >= 2 && hiddenSet.has(x.other)) ? 1 : 0;
          if (bChain !== aChain) return bChain - aChain;
          return String(a.other).localeCompare(String(b.other), 'zh');
        });
        let kids = 0;
        ranked.forEach((x) => {
          if (added >= budget || kids >= 6 || selectedSet.has(x.other)) return;
          addWord(x.other);
          kids += 1;
        });
      };
      const pullHubs = (onlyAttached, sortFn) => {
        let guard = 0;
        while (added < budget && guard < 12) {
          guard += 1;
          const rows = pool.filter((w) => qualifies(w) && (!onlyAttached || attachScore(w) > 0));
          if (!rows.length) break;
          rows.sort(sortFn);
          const hub = rows[0];
          addWord(hub);
          takeKids(hub);
        }
      };
      pullHubs(true, (a, b) => (
        attachScore(b) - attachScore(a)
        || chainScore(b) - chainScore(a)
        || strongHidden(b).length - strongHidden(a).length
        || degreeOf(b) - degreeOf(a)
        || String(a).localeCompare(String(b), 'zh')
      ));
      pullHubs(false, (a, b) => (
        chainScore(b) - chainScore(a)
        || strongHidden(b).length - strongHidden(a).length
        || degreeOf(b) - degreeOf(a)
        || String(a).localeCompare(String(b), 'zh')
      ));
      if (added >= budget) return;
      const hanging = selected.filter(
        (w) => levelOf(w) >= 2 && degreeOf(w) >= 8 && strongHidden(w).length >= 3
      );
      hanging.sort((a, b) => (
        attachScore(b) - attachScore(a)
        || chainScore(b) - chainScore(a)
        || strongHidden(b).length - strongHidden(a).length
        || degreeOf(b) - degreeOf(a)
      ));
      hanging.forEach((w) => {
        if (added < budget) takeKids(w);
      });
      return overflow;
    },

    /**
     * 候选词对一整团词的字面匹配。
     * 个数：候选词里出现了这团的多少个不同字。
     * 词数：某个字在这团的几个词里出现过；出现的词越多，候选词只要带上这个字，加分越大（按词数平方）。
     * 次数：这些字在这团里一共出现了几次。
     * 最长连续字仍计入，但不再单独决定名次。
     */
    v3CharMatchScore(candidate, words) {
      const cand = String(candidate || '');
      const list = (words || []).map((w) => String(w || '')).filter(Boolean);
      if (!cand || !list.length) return { score: 0, maxRun: 0, distinct: 0, wordSum: 0 };
      const wordHits = {};
      const freq = {};
      list.forEach((w) => {
        const seen = new Set();
        String(w).split('').forEach((ch) => {
          if (!ch.trim()) return;
          freq[ch] = (freq[ch] || 0) + 1;
          if (seen.has(ch)) return;
          seen.add(ch);
          wordHits[ch] = (wordHits[ch] || 0) + 1;
        });
      });
      const candChars = new Set(cand.split('').filter((ch) => ch.trim() && wordHits[ch]));
      let distinct = 0;
      let wordSum = 0;
      let freqSum = 0;
      let hot = 0;
      candChars.forEach((ch) => {
        const hits = wordHits[ch] || 0;
        distinct += 1;
        wordSum += hits;
        freqSum += freq[ch] || 0;
        hot += hits * hits;
      });
      const longestRun = (a, b) => {
        let best = 0;
        for (let i = 0; i < a.length; i += 1) {
          for (let j = 0; j < b.length; j += 1) {
            let k = 0;
            while (i + k < a.length && j + k < b.length && a[i + k] === b[j + k]) k += 1;
            if (k > best) best = k;
          }
        }
        return best;
      };
      let maxRun = 0;
      let runSum = 0;
      list.forEach((w) => {
        const run = longestRun(cand, w);
        if (run > maxRun) maxRun = run;
        runSum += run;
      });
      const score = hot + freqSum + distinct * 2 + maxRun * maxRun * 4 + runSum;
      return { score, maxRun, distinct, wordSum };
    },

    /**
     * 主网 = 图上节点最多的那一团。
     * 主网外不少于 3 个词的小团，从小团里边最多的词连到主图里综合最像的词。
     */
    buildV3OverflowBridgeLinks(displayed) {
      const shown = (displayed || []).filter(Boolean);
      const shownSet = new Set(shown);
      const adj = this.buildV3HierarchyAdjacency(this.semanticReorganizeMeta || {});
      const neighbors = (w) => (adj[w] || [])
        .map((x) => x.other)
        .filter((other) => shownSet.has(other));
      const visited = new Set();
      const components = [];
      shown.forEach((start) => {
        if (visited.has(start)) return;
        const comp = [];
        const pending = [start];
        visited.add(start);
        while (pending.length) {
          const w = pending.pop();
          comp.push(w);
          neighbors(w).forEach((other) => {
            if (visited.has(other)) return;
            visited.add(other);
            pending.push(other);
          });
        }
        components.push(comp);
      });
      if (components.length < 2) return [];
      let main = components[0];
      components.forEach((comp) => {
        if (comp.length > main.length) main = comp;
      });
      const mainSet = new Set(main);
      const bridges = [];
      components.forEach((comp) => {
        if (comp === main || comp.length < 3) return;
        const compSet = new Set(comp);
        let best = null;
        main.forEach((cand) => {
          const scored = this.v3CharMatchScore(cand, comp);
          if (!scored || scored.distinct < 1) return;
          const tighter = best && scored.score === best.score && (
            scored.wordSum > best.wordSum
            || (scored.wordSum === best.wordSum && scored.maxRun > best.maxRun)
            || (scored.wordSum === best.wordSum && scored.maxRun === best.maxRun && cand.length < best.word.length)
          );
          if (!best || scored.score > best.score || tighter) {
            best = { word: cand, score: scored.score, maxRun: scored.maxRun, wordSum: scored.wordSum };
          }
        });
        if (!best) return;
        let hub = comp[0];
        let hubDeg = -1;
        comp.forEach((w) => {
          const deg = neighbors(w).filter((other) => compSet.has(other)).length;
          if (deg > hubDeg) {
            hubDeg = deg;
            hub = w;
          }
        });
        if (!mainSet.has(best.word) || compSet.has(best.word) || hub === best.word) return;
        bridges.push({ a: hub, b: best.word });
      });
      return bridges;
    },

    /**
     * v3：连通优先选显（非卡片频率）。
     * 必显 Top/部落 → 高层枢纽+强边 1 跳邻居 → 救孤立 → 层级/象限补齐。
     * 名额用完后，按溢出额度补第二层局部枢纽及其强链，不替换已选词。
     */
    getV3DisplayKeywords(keywordsPool, maxCount = DEFAULT_NODE_DISPLAY_LIMIT) {
      const pool = (keywordsPool || []).filter(Boolean);
      if (!pool.length || maxCount <= 0) return [];
      const poolSet = new Set(pool);
      const meta = this.semanticReorganizeMeta || {};
      const levels = meta.keyword_levels || {};
      const tribalList = (this.tribalKeywords || []).filter((w) => poolSet.has(w));
      const effectiveMax = maxCount + tribalList.length;
      const forced = this.flattenBookTopKeywords(meta).filter((w) => poolSet.has(w));
      const adj = this.buildV3HierarchyAdjacency(meta);

      const coreIssue = String(meta.core_issue || '').trim();
      const coreRelated = [];
      if (coreIssue) {
        pool.forEach((w) => {
          if (w && (coreIssue.includes(w) || w.includes(coreIssue.slice(0, Math.min(6, coreIssue.length))))) {
            coreRelated.push(w);
          }
        });
      }

      const mergeOrder = () => {
        const selected = [];
        const seen = new Set();
        const push = (k) => {
          if (!k || seen.has(k) || !poolSet.has(k)) return;
          seen.add(k);
          selected.push(k);
        };
        forced.forEach(push);
        tribalList.forEach(push);
        coreRelated.forEach(push);
        pool.forEach(push);
        return selected;
      };

      if (pool.length <= effectiveMax) {
        this.v3OverflowWords = [];
        this.v3DisplayBridgeLinks = [];
        return mergeOrder().slice(0, effectiveMax);
      }

      const selected = [];
      const selectedSet = new Set();
      const take = (k) => {
        if (!k || selectedSet.has(k) || !poolSet.has(k)) return false;
        if (selected.length >= effectiveMax) return false;
        selectedSet.add(k);
        selected.push(k);
        return true;
      };

      // 1) 必显
      forced.forEach(take);
      tribalList.forEach(take);
      coreRelated.forEach(take);

      const degreeOf = (w) => (adj[w] ? adj[w].length : 0);
      const levelOf = (w) => this.parseV3KeywordLevel(w, levels);
      const quadOf = (w) => {
        const q = String(((this.keywordFourColorDMTData || {})[w] || {}).quadrant || '').toUpperCase();
        return ['Q1', 'Q2', 'Q3', 'Q4'].includes(q) ? q : 'Q3';
      };

      // 2) 高层枢纽（L0/L1 且度高）先入，并带上最强 1 跳邻居
      const hubs = pool
        .filter((w) => !selectedSet.has(w) && levelOf(w) <= 1)
        .sort((a, b) => {
          const da = degreeOf(a);
          const db = degreeOf(b);
          if (db !== da) return db - da;
          return levelOf(a) - levelOf(b) || pool.indexOf(a) - pool.indexOf(b);
        });
      hubs.forEach((hub) => {
        if (selected.length >= effectiveMax) return;
        take(hub);
        const neigh = (adj[hub] || []).filter((x) => poolSet.has(x.other) && !selectedSet.has(x.other));
        // 预算：枢纽邻居约占剩余名额的一半，避免星型占满
        const budget = Math.max(2, Math.min(6, Math.floor((effectiveMax - selected.length) / 4)));
        neigh.slice(0, budget).forEach((x) => take(x.other));
      });

      // 3) 继续按「层级低 + 度高」补骨架，并顺手拉 1 个最强邻居
      const remainingSkeleton = pool
        .filter((w) => !selectedSet.has(w))
        .sort((a, b) => {
          const la = levelOf(a);
          const lb = levelOf(b);
          if (la !== lb) return la - lb;
          const da = degreeOf(a);
          const db = degreeOf(b);
          if (db !== da) return db - da;
          return pool.indexOf(a) - pool.indexOf(b);
        });
      for (const w of remainingSkeleton) {
        if (selected.length >= effectiveMax) break;
        take(w);
        const topNeigh = (adj[w] || []).find((x) => poolSet.has(x.other) && !selectedSet.has(x.other));
        if (topNeigh && selected.length < effectiveMax) take(topNeigh.other);
      }

      // 4) 救孤立：当前子集内无边、但全局有边 → 拉最强未入选邻居
      const hasEdgeInSelected = (w) =>
        (adj[w] || []).some((x) => selectedSet.has(x.other));
      let guard = 0;
      while (selected.length < effectiveMax && guard < effectiveMax * 2) {
        guard += 1;
        const isolates = selected.filter((w) => degreeOf(w) > 0 && !hasEdgeInSelected(w));
        if (!isolates.length) break;
        let pulled = false;
        for (const w of isolates) {
          if (selected.length >= effectiveMax) break;
          const cand = (adj[w] || []).find((x) => poolSet.has(x.other) && !selectedSet.has(x.other));
          if (cand && take(cand.other)) {
            pulled = true;
            break;
          }
        }
        if (!pulled) break;
      }

      // 5) 象限均衡补齐（仍优先有边的词）
      if (selected.length < effectiveMax) {
        const quadCount = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 };
        selected.forEach((w) => { quadCount[quadOf(w)] = (quadCount[quadOf(w)] || 0) + 1; });
        const rest = pool
          .filter((w) => !selectedSet.has(w))
          .sort((a, b) => {
            const qa = quadOf(a);
            const qb = quadOf(b);
            const ca = quadCount[qa] || 0;
            const cb = quadCount[qb] || 0;
            if (ca !== cb) return ca - cb;
            const da = degreeOf(a) > 0 ? 0 : 1;
            const db = degreeOf(b) > 0 ? 0 : 1;
            if (da !== db) return da - db;
            return levelOf(a) - levelOf(b) || pool.indexOf(a) - pool.indexOf(b);
          });
        rest.forEach((w) => {
          if (selected.length >= effectiveMax) return;
          if (take(w)) quadCount[quadOf(w)] = (quadCount[quadOf(w)] || 0) + 1;
        });
      }

      const base = selected.slice(0, effectiveMax);
      const overflowWords = this.appendV3LocalHubOverflow(base, pool, poolSet, adj, levelOf, maxCount) || [];
      this.v3OverflowWords = overflowWords;
      this.v3DisplayBridgeLinks = this.buildV3OverflowBridgeLinks(base);
      return base;
    },

    getSmartFilteredKeywords(keywords, maxCount = DEFAULT_NODE_DISPLAY_LIMIT) {
      if (!keywords || keywords.length === 0) {
        return [];
      }

      // 大本体：无卡片频率，优先保证属性数据已同步，并在上限内尽量全显
      if (this.isOntologyScopeMode) {
        if (!this.keywordFourColorDMTData || Object.keys(this.keywordFourColorDMTData).length === 0) {
          this.syncKeywordFourColorDMTFromProp();
        }
        const tribalList = this.tribalKeywords || [];
        const effectiveMax = maxCount + tribalList.length;
        if (keywords.length <= effectiveMax) {
          return keywords;
        }
        // 超出上限时仍走下方智能筛选（按四色/DMT 均衡），但不要依赖卡片频率
      }

      // 🔥 节点上限 = 原上限 + 部落知识关键词数，部落关键词必显
      const tribalList = this.tribalKeywords || [];
      const effectiveMax = maxCount + tribalList.length;

      if (keywords.length <= effectiveMax) {
        return keywords;
      }

      // 🔥 如果设置了作者筛选，只考虑该作者有贡献的关键词
      const authorFilterText = (this.authorFilter || '').trim().toLowerCase();
      const hasAuthorFilter = authorFilterText.length > 0;

      // 准备数据
      const keywordFourColorDMTData = this.keywordFourColorDMTData || {};
      const initialKeywordsSet = new Set();
      try {
        if (this.initialKeywords) {
          if (Array.isArray(this.initialKeywords)) {
            this.initialKeywords.forEach(k => initialKeywordsSet.add(k));
          } else if (this.initialKeywords.size !== undefined) {
            Array.from(this.initialKeywords).forEach(k => initialKeywordsSet.add(k));
          }
        }
      } catch (e) {
        console.warn('[getSmartFilteredKeywords] 处理initialKeywords时出错:', e);
      }
      
      // 🔥 计算每个关键词的频率（关联的卡片数量）和首次出现时间
      const keywordFrequency = {}; // 关键词频率（卡片数量）
      const keywordFirstAppearance = {}; // 关键词首次出现时间
      keywords.forEach(keyword => {
        let earliestDate = null;
        let cardCount = 0;
        this.effectiveCards.forEach(card => {
          if (!card.keyWords) return;
          const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
          if (cardKeywords.includes(keyword)) {
            cardCount++;
            if (card.datetime) {
              const cardDate = new Date(card.datetime);
              if (!earliestDate || cardDate < earliestDate) {
                earliestDate = cardDate;
              }
            }
          }
        });
        keywordFrequency[keyword] = cardCount;
        keywordFirstAppearance[keyword] = earliestDate;
      });
      
      // 🔥 按频率排序（频率高的在前），获取频率前三的关键词
      const sortedByFrequency = [...keywords].sort((a, b) => {
        return keywordFrequency[b] - keywordFrequency[a]; // 降序：频率高的在前
      });
      const top3FrequencyKeywords = sortedByFrequency.slice(0, 3);
      
      // 🔥 按首次出现时间排序（最近的在前，null值排在最后）
      const sortedByTime = [...keywords].sort((a, b) => {
        const dateA = keywordFirstAppearance[a];
        const dateB = keywordFirstAppearance[b];
        if (!dateA && !dateB) return 0;
        if (!dateA) return 1; // A没有日期，排后面
        if (!dateB) return -1; // B没有日期，排后面
        return dateB - dateA; // 降序：最近的在前
      });
      
      // 分类关键词
      const colorGroups = { 'R': [], 'B': [], 'P': [], 'G': [], 'none': [] };
      const dmtGroups = { 'D': [], 'M': [], 'T': [], 'none': [] };
      const newKeywords = [];
      const otherKeywords = [];
      
      // 🔥 获取当日（北京时间）的开始时间
      const now = new Date();
      const beijingTime = new Date(now.getTime() + (8 * 60 * 60 * 1000));
      const todayStart = new Date(beijingTime.getFullYear(), beijingTime.getMonth(), beijingTime.getDate());
      const todayStartUTC = new Date(todayStart.getTime() - (8 * 60 * 60 * 1000));
      
      keywords.forEach(keyword => {
        const keywordData = keywordFourColorDMTData[keyword] || {};
        const fourColorType = keywordData.four_color_type || '';
        const dmtLevel = keywordData.dmt_level || '';
        
        // 🔥 检查是否为新关键词（当日（北京时间）新产生的）
        let keywordCards = this.effectiveCards.filter(card => {
          if (!card.keyWords) return false;
          const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
          return cardKeywords.includes(keyword);
        });
        
        // 🔥 如果设置了作者筛选，只考虑该作者的卡片
        if (hasAuthorFilter) {
          keywordCards = keywordCards.filter(card => {
            const cardWriter = (card.writer || '').toLowerCase();
            return cardWriter.includes(authorFilterText);
          });
        }
        
        // 🔥 如果设置了作者筛选且该关键词没有该作者的卡片，跳过
        if (hasAuthorFilter && keywordCards.length === 0) {
          return; // 跳过此关键词
        }
        
        let isNew = false;
        if (keywordCards.length > 0) {
          isNew = keywordCards.some(card => {
            if (!card.datetime) return false;
            const cardDate = new Date(card.datetime);
            return cardDate >= todayStartUTC;
          });
        }
        
        // 按颜色分类
        if (fourColorType && colorGroups[fourColorType]) {
          colorGroups[fourColorType].push(keyword);
        } else {
          colorGroups['none'].push(keyword);
        }
        
        // 按DMT分类
        if (dmtLevel && dmtGroups[dmtLevel]) {
          dmtGroups[dmtLevel].push(keyword);
        } else {
          dmtGroups['none'].push(keyword);
        }
        
        // 新关键词优先
        if (isNew) {
          newKeywords.push(keyword);
        } else {
          otherKeywords.push(keyword);
        }
      });
      
      // 🔥 智能选择关键词
      const selected = new Set();
      
      // 🔥 0.0 最高优先级：频率前三的关键词必须包含
      top3FrequencyKeywords.forEach(k => {
        if (keywords.includes(k)) {
          selected.add(k);
        }
      });
      
      // 🔥 0.1 最高优先级：保留当前显示的节点（特别是用户手动修改过的）
      // 这样可以确保用户手动修改四色/DMT后，节点不会突然消失
      const currentDisplayedKeywords = new Set(
        (this.nodes || []).map(node => node.label)
      );
      const userModifiedKeywords = this.locallyUpdatedKeywords || new Set();
      
      // 优先保留当前显示的节点（特别是用户修改过的）
      keywords.forEach(keyword => {
        if (currentDisplayedKeywords.has(keyword)) {
          // 如果是用户修改过的关键词，必须保留
          if (userModifiedKeywords.has(keyword)) {
            selected.add(keyword);
          }
        }
      });

      // 0.2 优先选择生成时间最近的4个关键词（但不替换已保留的）
      sortedByTime.slice(0, 4).forEach(k => {
        if (keywords.includes(k)) {
          selected.add(k);
        }
      });
      
      // 1. 优先选择新关键词（最多10个）
      newKeywords.slice(0, 10).forEach(k => selected.add(k));
      
      // // 2. 确保每种颜色至少有一个代表（优先从新关键词中选择）
      // ['R', 'B', 'P', 'G'].forEach(color => {
      //   if (colorGroups[color].length > 0) {
      //     // 优先从新关键词中选择
      //     const newKeywordInColor = colorGroups[color].find(k => newKeywords.includes(k) && !selected.has(k));
      //     if (newKeywordInColor) {
      //       selected.add(newKeywordInColor);
      //     } else {
      //       // 如果没有新关键词，选择第一个未选中的
      //       const keywordToAdd = colorGroups[color].find(k => !selected.has(k));
      //       if (keywordToAdd) {
      //         selected.add(keywordToAdd);
      //       }
      //     }
      //   }
      // });
      
      // // 3. 确保每种DMT类型至少有一个代表
      // ['D', 'M', 'T'].forEach(dmt => {
      //   if (dmtGroups[dmt].length > 0) {
      //     const keywordToAdd = dmtGroups[dmt].find(k => !selected.has(k));
      //     if (keywordToAdd) {
      //       selected.add(keywordToAdd);
      //     }
      //   }
      // });

      // 2. 确保每种颜色至少有一个代表（优先从新关键词中选择）
      ['R', 'B', 'P', 'G'].forEach(color => {
        if (colorGroups[color].length > 0) {
          // 优先从新关键词中选择
          const newKeywordInColor = colorGroups[color].find(k => newKeywords.includes(k) && !selected.has(k));
          if (newKeywordInColor) {
            selected.add(newKeywordInColor);
          } else {
            // 如果没有新关键词，从时间排序的列表中选择未选中的
            const keywordToAdd = sortedByTime.find(k => colorGroups[color].includes(k) && !selected.has(k));
            if (keywordToAdd) {
              selected.add(keywordToAdd);
            }
          }
        }
      });
      
      // 3. 确保每种DMT类型至少有一个代表
      ['D', 'M', 'T'].forEach(dmt => {
        if (dmtGroups[dmt].length > 0) {
          // 优先从新关键词中选择
          const newKeywordInDmt = dmtGroups[dmt].find(k => newKeywords.includes(k) && !selected.has(k));
          if (newKeywordInDmt) {
            selected.add(newKeywordInDmt);
          } else {
            // 如果没有新关键词，从时间排序的列表中选择未选中的
            const keywordToAdd = sortedByTime.find(k => dmtGroups[dmt].includes(k) && !selected.has(k));
            if (keywordToAdd) {
              selected.add(keywordToAdd);
            }
          }
        }
      });
      
      // 4.1 🔥 绿色节点可以稍多些（因为绿色节点总共都会很少）
      // 如果有绿色节点且还没有达到maxCount，可以多选一些绿色节点
      if (colorGroups['G'].length > 0) {
        const greenNotSelected = colorGroups['G'].filter(k => !selected.has(k));
        const currentGreenCount = Array.from(selected).filter(k => {
          const keywordData = keywordFourColorDMTData[k] || {};
          return keywordData.four_color_type === 'G';
        }).length;
        
        // 如果绿色节点数量较少（<=5个），可以多选一些（最多再选3个）
        if (greenNotSelected.length > 0 && currentGreenCount < 5 && selected.size < maxCount) {
          const additionalGreen = greenNotSelected.slice(0, Math.min(3, maxCount - selected.size));
          additionalGreen.forEach(k => selected.add(k));
        }
      }

      // 4.2 🔥 T节点可以稍多些（因为T节点总共也会很少）
      // 如果有T节点且还没有达到maxCount，可以多选一些T节点
      if (dmtGroups['T'].length > 0) {
        const tNotSelected = dmtGroups['T'].filter(k => !selected.has(k));
        const currentTCount = Array.from(selected).filter(k => {
        const keywordData = keywordFourColorDMTData[k] || {};
        return keywordData.dmt_level === 'T';
        }).length;
        
        // 如果T节点数量较少（<3个），可以多选一些（最多再选2个）
        if (tNotSelected.length > 0 && currentTCount < 3 && selected.size < maxCount) {
        const additionalT = tNotSelected.slice(0, Math.min(2, maxCount - selected.size));
        additionalT.forEach(k => selected.add(k));
        }
      }
      
      // 5. 从剩余关键词中补充到maxCount个
      const remaining = keywords.filter(k => !selected.has(k));
      const needed = maxCount - selected.size;
      remaining.slice(0, needed).forEach(k => selected.add(k));

      // 🔥 确保所有部落关键词被包含
      tribalList.forEach(k => {
        if (keywords.includes(k)) selected.add(k);
      });
      
      return Array.from(selected);
    },
    
    /** 规范化短词，便于匹配 */
    normalizeKeywordToken(text) {
      return String(text || '')
        .trim()
        .toLowerCase()
        .replace(/[\s_\-·•、，,。.!！？?（）()【】\[\]「」""'']/g, '');
    },

    /** 最长连续公共子串长度（短词够用） */
    longestCommonSubstringLen(a, b) {
      if (!a || !b) return 0;
      let best = 0;
      for (let i = 0; i < a.length; i += 1) {
        for (let j = 0; j < b.length; j += 1) {
          let k = 0;
          while (
            i + k < a.length
            && j + k < b.length
            && a[i + k] === b[j + k]
          ) {
            k += 1;
          }
          if (k > best) best = k;
        }
      }
      return best;
    },

    /**
     * 节点词 ↔ 候选词（文档抽出词 / 卡片语义词）匹配度。
     * 综合：完全相等、包含、最长连续公共子串占比、字符覆盖（出现与否）。
     * 思路对齐卡片侧「重叠 + 部分匹配」的相似度，但面向短词。
     */
    computeKeywordMatchScore(nodeWord, candidateWord) {
      const a = this.normalizeKeywordToken(nodeWord);
      const b = this.normalizeKeywordToken(candidateWord);
      if (!a || !b) return 0;
      if (a === b) return 1;

      const shorter = a.length <= b.length ? a : b;
      const longer = a.length <= b.length ? b : a;
      if (longer.includes(shorter)) {
        return Math.max(0.72, shorter.length / longer.length);
      }

      const contig = this.longestCommonSubstringLen(a, b);
      const contigRatio = contig / Math.max(a.length, 1);

      // 节点词各字符是否在候选词中出现（覆盖率）
      let hitChars = 0;
      for (let i = 0; i < a.length; i += 1) {
        if (b.includes(a[i])) hitChars += 1;
      }
      const charCoverage = hitChars / Math.max(a.length, 1);

      // 2-gram 重叠（中文短词更稳）
      let gramHit = 0;
      let gramTotal = 0;
      if (a.length >= 2 && b.length >= 2) {
        const bGrams = new Set();
        for (let i = 0; i < b.length - 1; i += 1) bGrams.add(b.slice(i, i + 2));
        for (let i = 0; i < a.length - 1; i += 1) {
          gramTotal += 1;
          if (bGrams.has(a.slice(i, i + 2))) gramHit += 1;
        }
      }
      const gramRatio = gramTotal > 0 ? gramHit / gramTotal : 0;

      return Math.min(1, contigRatio * 0.5 + charCoverage * 0.2 + gramRatio * 0.3);
    },

    /** 节点词是否与候选词列表中任一词达到匹配阈值 */
    keywordMatchesAny(nodeWord, candidates, threshold = 0.58) {
      const list = Array.isArray(candidates) ? candidates : [];
      for (let i = 0; i < list.length; i += 1) {
        if (this.computeKeywordMatchScore(nodeWord, list[i]) >= threshold) return true;
      }
      return false;
    },

    isV3TopTierKeyword(keyword) {
      const forced = this.flattenBookTopKeywords(this.semanticReorganizeMeta || {});
      const target = String(keyword || '').trim();
      return forced.some((w) => String(w).trim() === target);
    },

    hasExactPermanentKeywordCard(keyword) {
      if (this.isOntologyScopeMode || !this.effectiveCards || !Array.isArray(this.effectiveCards)) {
        return false;
      }
      const keywordTrimmed = String(keyword || '').trim();
      if (!keywordTrimmed) return false;
      return this.effectiveCards.some((card) => {
        const cardKeyWords = (card.keyWords || '').trim();
        return card.title === '关键词神经元永久卡'
          && cardKeyWords === keywordTrimmed
          && card.four_color_type;
      });
    },

    /** v3：文档命中数（直接 sources + 各文档词表模糊匹配） */
    countV3DocHits(keyword) {
      const meta = this.semanticReorganizeMeta || {};
      const perDoc = (meta.per_doc_keywords && typeof meta.per_doc_keywords === 'object')
        ? meta.per_doc_keywords
        : {};
      const kwData = (this.keywordFourColorDMTData || {})[keyword] || {};
      const exactSources = Array.isArray(kwData.sources)
        ? kwData.sources.map((s) => String(s).trim()).filter(Boolean)
        : [];
      const exactSet = new Set(exactSources);

      const fileNames = Object.keys(perDoc).length > 0
        ? Object.keys(perDoc)
        : (Array.isArray(meta.source_files)
          ? meta.source_files.map((s) => String(s).trim()).filter(Boolean)
          : exactSources);

      if (!fileNames.length) {
        // 旧本子尚未写入 per_doc_keywords：至少用 sources 长度兜底
        return exactSources.length;
      }

      let hits = 0;
      fileNames.forEach((fn) => {
        if (exactSet.has(fn)) {
          hits += 1;
          return;
        }
        const words = perDoc[fn] || [];
        if (this.keywordMatchesAny(keyword, words)) {
          hits += 1;
        }
      });
      return hits;
    },

    /** v3：卡片命中数（卡片语义词与节点词达匹配阈值则 +1） */
    countV3CardHits(keyword, authorFilterText = '') {
      const hasAuthorFilter = !!(authorFilterText || '').trim();
      const filter = (authorFilterText || '').trim().toLowerCase();
      return (this.effectiveCards || []).filter((card) => {
        if (!card || !card.keyWords) return false;
        if (card.title === '关键词神经元永久卡') return false;
        if (hasAuthorFilter) {
          const cardWriter = (card.writer || '').toLowerCase();
          if (!cardWriter.includes(filter)) return false;
        }
        const cardKeywords = String(card.keyWords)
          .split(/[,，]/)
          .map((k) => k.trim())
          .filter(Boolean);
        return this.keywordMatchesAny(keyword, cardKeywords);
      }).length;
    },

    // 根据卡片数量和选中状态计算节点颜色
    getNodeColors(keyword, cardCount, minCount, maxCount, isSelected) {
      
      // 🔥 优先使用关键词的四色类型
      // 直接使用 data 中存储的纯对象数据
      const keywordDMTData = this.keywordFourColorDMTData || {};
      
      // 先尝试精确匹配
      let keywordData = keywordDMTData[keyword];
      
      // 如果精确匹配失败，尝试规范化匹配（去除首尾空格）
      if (!keywordData && keyword) {
        const normalizedKeyword = keyword.trim();
        keywordData = keywordDMTData[normalizedKeyword];
      }
      
      // 如果还是找不到，尝试遍历所有键进行匹配（去除空格后比较）
      if (!keywordData && keywordDMTData) {
        const keywordKeys = Object.keys(keywordDMTData);
        if (keywordKeys.length > 0) {
          const keywordTrimmed = keyword ? keyword.trim() : '';
          // 尝试精确匹配（去除空格后）
          const matchedKey = keywordKeys.find(k => k.trim() === keywordTrimmed);
          if (matchedKey) {
            keywordData = keywordDMTData[matchedKey];
          }
        }
      }
      
      if (keywordData && keywordData.four_color_type) {
        // 如果有明确的四色类型，使用预定义的颜色
        const colorMap = {
          'R': { r: 220, g: 20, b: 60 },  // Crimson (更红的红色)
          'B': { r: 30, g: 144, b: 255 }, // DodgerBlue (Blue)
          'P': { r: 147, g: 112, b: 219 },// MediumPurple (Purple)
          'G': { r: 60, g: 179, b: 113 }  // MediumSeaGreen (Green)
        };
        
        const baseColor = colorMap[keywordData.four_color_type] || { r: 150, g: 150, b: 150 }; // Default grey
        
        // 🔥 检查是否有对应的深色永久卡（title="关键词神经元永久卡"且keyWords=keyword）
        // 大本体无本子永久卡：仍用浅色四色（与「无永久卡」一致），避免过深
        const hasPermanentCard = this.hasExactPermanentKeywordCard(keyword);
        // v3：Top1/3/5/10 或永久卡完全匹配 → 偏深；其余偏浅
        const useDeep = this.isV3Pipeline
          ? (this.isV3TopTierKeyword(keyword) || hasPermanentCard)
          : hasPermanentCard;
        
        // 🔥 根据是否深色档调整颜色深浅（加大对比度）
        let r, g, b;
        if (useDeep) {
          // 偏深：baseColor * 0.65
          r = Math.round(baseColor.r * 0.65);
          g = Math.round(baseColor.g * 0.65);
          b = Math.round(baseColor.b * 0.65);
        } else {
          // 偏浅：baseColor * 0.45 + white * 0.55
          r = Math.round(baseColor.r * 0.45 + 255 * 0.55);
          g = Math.round(baseColor.g * 0.45 + 255 * 0.55);
          b = Math.round(baseColor.b * 0.45 + 255 * 0.55);
        }
        
        // 🔥 选中时使用节点本身的颜色加深（保持颜色特征）
        if (isSelected) {
          r = Math.max(0, Math.round(r * 0.6));
          g = Math.max(0, Math.round(g * 0.6));
          b = Math.max(0, Math.round(b * 0.6));
        }
        
        const toHex = (num) => {
          const hex = Math.max(0, Math.min(255, num)).toString(16);
          return hex.length === 1 ? '0' + hex : hex;
        };
        
        const color = `#${toHex(r)}${toHex(g)}${toHex(b)}`;
        const strokeColor = isSelected 
          ? `#${toHex(Math.max(0, r - 30))}${toHex(Math.max(0, g - 30))}${toHex(Math.max(0, b - 20))}`
          : color;
        
        return {
          color: color,
          stroke: strokeColor,
          strokeWidth: isSelected ? 3.5 : 2
        };
      }
      
      // 否则使用原有的基于重要性的紫色渐变逻辑
      // 计算重要性比例（0-1）
      const importance = maxCount > minCount 
        ? (cardCount - minCount) / (maxCount - minCount)
        : 1;
      
      // 定义颜色范围：从浅紫色到深紫色
      // 未选中状态：从很浅的紫色到中等深度的紫色
      const unselectedColors = {
        light: { r: 200, g: 180, b: 230 }, // 很浅的紫色
        dark: { r: 111, g: 85, b: 159 }    // #6f559f 中等深度的紫色
      };
      
      // 选中状态：从深紫色到很深的紫色（增强对比度）
      const selectedColors = {
        light: { r: 111, g: 85, b: 159 },  // #6f559f 中等深度的紫色
        dark: { r: 31, g: 22, b: 82 }      // #1f1652 很深的紫色
      };
      
      // 根据选中状态选择颜色范围
      const colorRange = isSelected ? selectedColors : unselectedColors;
      
      // 根据重要性插值颜色
      const r = Math.round(colorRange.light.r + (colorRange.dark.r - colorRange.light.r) * importance);
      const g = Math.round(colorRange.light.g + (colorRange.dark.g - colorRange.light.g) * importance);
      const b = Math.round(colorRange.light.b + (colorRange.dark.b - colorRange.light.b) * importance);
      
      // 转换为十六进制颜色的辅助函数
      const toHex = (num) => {
        const hex = Math.max(0, Math.min(255, num)).toString(16);
        return hex.length === 1 ? '0' + hex : hex;
      };
      
      // 节点填充颜色
      const color = `#${toHex(r)}${toHex(g)}${toHex(b)}`;
      
      // 边框颜色：选中时使用更深的边框，未选中时使用稍浅的边框
      let strokeR, strokeG, strokeB;
      if (isSelected) {
        // 选中时：边框比填充色更深，形成明显对比
        strokeR = Math.max(0, r - 40);
        strokeG = Math.max(0, g - 40);
        strokeB = Math.max(0, b - 30);
      } else {
        // 未选中时：边框稍浅，形成柔和效果
        strokeR = Math.min(255, r + 10);
        strokeG = Math.min(255, g + 10);
        strokeB = Math.min(255, b + 10);
      }
      const strokeColor = `#${toHex(strokeR)}${toHex(strokeG)}${toHex(strokeB)}`;
      
      return {
        color: color,
        stroke: strokeColor,
        strokeWidth: isSelected ? 3.5 : 2
      };
    },
    
    getV3KeywordAttrs(keyword) {
      const meta = this.semanticReorganizeMeta || {};
      const levels = meta.keyword_levels || {};
      const quads = meta.quadrants || {};
      const kwData = (this.keywordFourColorDMTData || {})[keyword] || {};
      let level = levels[keyword];
      if (level == null || level === '') level = kwData.level;
      const qEntry = quads[keyword] || {};
      const quadrant = String(qEntry.quadrant || kwData.quadrant || '').trim();
      const pendingList = qEntry.pending;
      const pendingFaded = !!(qEntry.pending_faded || kwData.pending_faded || kwData.status === 'soft_pending');
      const pendingRaw = (Array.isArray(pendingList) && pendingList.length > 0) || kwData.status === 'pending';
      // 淡化虚线不再当可点 pending（仍显示淡框）
      const pending = !!pendingRaw && !pendingFaded;
      return { level, quadrant, pending, pendingFaded };
    },

    hashStringToUnit(str) {
      let h = 0;
      const s = String(str || '');
      for (let i = 0; i < s.length; i += 1) {
        h = ((h << 5) - h) + s.charCodeAt(i);
        h |= 0;
      }
      return (Math.abs(h) % 1000) / 1000;
    },

    /** 连线轻微弯曲，减少直线完全重合 */
    linkCurve(link) {
      const s = link && link.source;
      const t = link && link.target;
      if (!s || !t || s.x == null || t.x == null) return '';
      if (this.quadrantPlaceMode && this.quadrantFrame && this.quadrantFrame.exits) {
        const qs = this.quadrantOfNode(s);
        const qt = this.quadrantOfNode(t);
        if (qs !== qt && link.linkType !== 'contour' && link.linkType !== 'longitude') {
          const routed = this.quadrantGutterPath(s, t, qs, qt);
          if (routed) return routed;
        }
      }
      const x1 = s.x;
      const y1 = s.y;
      const x2 = t.x;
      const y2 = t.y;
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const bend = (this.hashStringToUnit(`${s.label}|${t.label}`) - 0.5) * Math.min(36, len * 0.18);
      const mx = (x1 + x2) / 2 + (-dy / len) * bend;
      const my = (y1 + y2) / 2 + (dx / len) * bend;
      return `M ${x1} ${y1} Q ${mx} ${my} ${x2} ${y2}`;
    },

    quadrantLinkOpacity(link) {
      const base = link && link.opacity != null ? link.opacity : 0.7;
      if (!this.quadrantPlaceMode || !link || !link.source || !link.target) return base;
      if (link.linkType === 'contour' || link.linkType === 'longitude') return base;
      if (this.quadrantOfNode(link.source) === this.quadrantOfNode(link.target)) return base;
      return Math.min(base, 0.22);
    },

    quadrantGutterPath(s, t, qs, qt) {
      const frame = this.quadrantFrame;
      const exits = frame && frame.exits;
      const es = exits && exits[qs];
      const et = exits && exits[qt];
      if (!es || !et) return '';
      const port = (node, exit, qKey) => {
        const box = exit.bbox;
        const innerLeft = qKey === 'Q1' || qKey === 'Q4';
        const innerTop = qKey === 'Q3' || qKey === 'Q4';
        const vx = innerLeft ? box.minX : box.maxX;
        const hy = innerTop ? box.minY : box.maxY;
        const portV = { x: vx, y: Math.min(box.maxY, Math.max(box.minY, node.y)) };
        const portH = { x: Math.min(box.maxX, Math.max(box.minX, node.x)), y: hy };
        return Math.abs(node.x - vx) <= Math.abs(node.y - hy) ? portV : portH;
      };
      const ps = port(s, es, qs);
      const pt = port(t, et, qt);
      const diagonal = (qs === 'Q1' && qt === 'Q3') || (qs === 'Q3' && qt === 'Q1')
        || (qs === 'Q2' && qt === 'Q4') || (qs === 'Q4' && qt === 'Q2');
      const raw = [{ x: s.x, y: s.y }, ps, es.corner];
      if (diagonal) raw.push({ x: frame.originX, y: frame.originY });
      raw.push(et.corner, pt, { x: t.x, y: t.y });
      const pts = [];
      raw.forEach((p) => {
        const prev = pts[pts.length - 1];
        if (prev && Math.abs(prev.x - p.x) < 1.5 && Math.abs(prev.y - p.y) < 1.5) return;
        pts.push(p);
      });
      if (pts.length < 2) return '';
      let d = `M ${pts[0].x} ${pts[0].y}`;
      for (let i = 1; i < pts.length; i += 1) d += ` L ${pts[i].x} ${pts[i].y}`;
      return d;
    },

    /** 象限内安全矩形（内缩边距，保证节点落在象限内且不太贴边） */
    getV3PaddedQuadRect(quadrant) {
      const ac = this.axisCanvas;
      const qKey = String(quadrant || '').toUpperCase();
      const raw = { Q1: ac.q1, Q2: ac.q2, Q3: ac.q3, Q4: ac.q4 }[qKey];
      if (!raw || !raw.w || !raw.h) return null;
      const padX = Math.min(28, raw.w * 0.08);
      const padY = Math.min(28, raw.h * 0.08);
      return {
        x: raw.x + padX,
        y: raw.y + padY,
        w: Math.max(24, raw.w - padX * 2),
        h: Math.max(24, raw.h - padY * 2),
        cx: raw.x + raw.w / 2,
        cy: raw.y + raw.h / 2,
        // 朝向整图中心（轴附近）的「内角」——同象限内 L0/Top 优先靠这里，层次往外散开
        innerX: qKey === 'Q1' || qKey === 'Q4' ? raw.x + padX + raw.w * 0.22 : raw.x + raw.w - padX - raw.w * 0.22,
        innerY: qKey === 'Q1' || qKey === 'Q2' ? raw.y + raw.h - padY - raw.h * 0.22 : raw.y + padY + raw.h * 0.22,
      };
    },

    clampPointToV3Quad(x, y, quadrant) {
      const rect = this.getV3PaddedQuadRect(quadrant);
      const ac = this.axisCanvas;
      if (!rect) {
        return { x: ac.midX, y: (ac.minY + ac.maxY) / 2 };
      }
      return {
        x: Math.min(rect.x + rect.w, Math.max(rect.x, x)),
        y: Math.min(rect.y + rect.h, Math.max(rect.y, y)),
      };
    },

    getV3QuadBiasPosition(keyword, quadrant, quadCounter) {
      const rect = this.getV3PaddedQuadRect(quadrant);
      const ac = this.axisCanvas;
      if (!rect) {
        return { x: ac.midX, y: (ac.minY + ac.maxY) / 2 };
      }
      const qKey = String(quadrant || 'Q3').toUpperCase() || 'Q3';
      if (!quadCounter[qKey]) quadCounter[qKey] = 0;
      const idx = quadCounter[qKey];
      quadCounter[qKey] += 1;
      const cols = Math.max(1, Math.ceil(Math.sqrt(idx + 2)));
      const rows = Math.max(1, Math.ceil((idx + 1) / cols));
      const row = Math.floor(idx / cols);
      const col = idx % cols;
      const jx = (this.hashStringToUnit(`${keyword}:x`) - 0.5) * Math.min(rect.w * 0.08, 20);
      const jy = (this.hashStringToUnit(`${keyword}:y2`) - 0.5) * Math.min(rect.h * 0.08, 20);
      return this.clampPointToV3Quad(
        rect.x + ((col + 0.5) / cols) * rect.w + jx,
        rect.y + ((row + 0.5) / rows) * rect.h + jy,
        qKey
      );
    },

    /**
     * v3 布局：节点必须落在所属象限内；象限内按 L 层次相对父节点散开并尽量均匀可读。
     * 等高线不要求标准圆/椭圆——围着同一上级、不挤压即可。
     */
    computeV3LayoutPositions(keywords) {
      const meta = this.semanticReorganizeMeta || {};
      const levels = meta.keyword_levels || {};
      const hierarchyLinks = Array.isArray(meta.hierarchy_links) ? meta.hierarchy_links : [];
      const keywordSet = new Set((keywords || []).filter(Boolean));
      const childrenByParent = {};
      const parentByChild = {};
      hierarchyLinks.forEach((pair) => {
        if (!pair || pair.length < 2) return;
        const parent = String(pair[0] || '').trim();
        const child = String(pair[1] || '').trim();
        if (!parent || !child || parent === child) return;
        if (!keywordSet.has(parent) || !keywordSet.has(child)) return;
        parentByChild[child] = parent;
        if (!childrenByParent[parent]) childrenByParent[parent] = [];
        if (!childrenByParent[parent].includes(child)) {
          childrenByParent[parent].push(child);
        }
      });

      const tops = meta.book_top_keywords || {};
      const top1Raw = tops.top1;
      const top1Word = Array.isArray(top1Raw) ? top1Raw[0] : top1Raw;
      const top1 = top1Word ? String(top1Word).trim() : '';

      const quadOf = (kw) => {
        const q = String(this.getV3KeywordAttrs(kw).quadrant || '').toUpperCase();
        return ['Q1', 'Q2', 'Q3', 'Q4'].includes(q) ? q : 'Q3';
      };

      const positions = {};
      const placed = new Set();

      // 按象限分组，象限内再按层级铺开
      const byQuad = { Q1: [], Q2: [], Q3: [], Q4: [] };
      [...keywordSet].forEach((k) => {
        byQuad[quadOf(k)].push(k);
      });

      Object.keys(byQuad).forEach((qKey) => {
        const list = byQuad[qKey];
        if (!list.length) return;
        const rect = this.getV3PaddedQuadRect(qKey);
        if (!rect) return;

        // 同象限内：Top1 / L0 靠内角；其余相对父节点或网格散开
        const sorted = [...list].sort((a, b) => {
          const la = this.parseV3KeywordLevel(a, levels);
          const lb = this.parseV3KeywordLevel(b, levels);
          if (a === top1) return -1;
          if (b === top1) return 1;
          if (la !== lb) return la - lb;
          return a.localeCompare(b, 'zh');
        });

        sorted.forEach((kw) => {
          const lv = this.parseV3KeywordLevel(kw, levels);
          const parent = parentByChild[kw];
          const parentSameQuad = parent && quadOf(parent) === qKey && positions[parent];

          let x;
          let y;
          if (kw === top1 || lv === 0) {
            const n0 = sorted.filter((k) => k === top1 || this.parseV3KeywordLevel(k, levels) === 0).length || 1;
            const i0 = sorted
              .filter((k) => k === top1 || this.parseV3KeywordLevel(k, levels) === 0)
              .indexOf(kw);
            const ang = (2 * Math.PI * Math.max(0, i0)) / n0 - Math.PI / 2;
            const r0 = 18 + Math.min(36, n0 * 4);
            x = rect.innerX + Math.cos(ang) * r0;
            y = rect.innerY + Math.sin(ang) * r0;
          } else if (parentSameQuad) {
            const siblings = (childrenByParent[parent] || []).filter(
              (s) => keywordSet.has(s) && quadOf(s) === qKey
                && this.parseV3KeywordLevel(s, levels) === lv
            );
            const idx = Math.max(0, siblings.indexOf(kw));
            const n = Math.max(1, siblings.length);
            const outwardX = rect.cx - rect.innerX;
            const outwardY = rect.cy - rect.innerY;
            const baseAng = Math.atan2(outwardY || 0.01, outwardX || 0.01);
            const spread = Math.min(Math.PI * 0.85, 0.35 + n * 0.22);
            const ang = baseAng - spread / 2 + (n <= 1 ? 0 : (spread * idx) / (n - 1));
            const dist = 36 + lv * 28 + (n > 4 ? 8 : 0);
            x = positions[parent].x + Math.cos(ang) * dist;
            y = positions[parent].y + Math.sin(ang) * dist;
          } else {
            const rest = sorted.filter((k) => !(k === top1 || this.parseV3KeywordLevel(k, levels) === 0));
            const ri = Math.max(0, rest.indexOf(kw));
            const cols = Math.max(2, Math.ceil(Math.sqrt(Math.max(rest.length, 1))));
            const rows = Math.max(1, Math.ceil(rest.length / cols));
            const col = ri % cols;
            const row = Math.floor(ri / cols);
            const tCol = (col + 0.5) / cols;
            const tRow = (row + 0.55) / rows;
            x = rect.x + rect.w * (0.28 + 0.64 * tCol);
            y = rect.y + rect.h * (0.22 + 0.68 * tRow);
            if (parent && positions[parent]) {
              x = 0.72 * x + 0.28 * positions[parent].x;
              y = 0.72 * y + 0.28 * positions[parent].y;
            }
          }

          const jx = (this.hashStringToUnit(`${kw}:jx`) - 0.5) * 10;
          const jy = (this.hashStringToUnit(`${kw}:jy`) - 0.5) * 10;
          positions[kw] = this.clampPointToV3Quad(x + jx, y + jy, qKey);
          placed.add(kw);
        });

        for (let pass = 0; pass < 3; pass += 1) {
          for (let i = 0; i < list.length; i += 1) {
            for (let j = i + 1; j < list.length; j += 1) {
              const a = list[i];
              const b = list[j];
              const pa = positions[a];
              const pb = positions[b];
              if (!pa || !pb) continue;
              const dx = pb.x - pa.x;
              const dy = pb.y - pa.y;
              const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
              const minDist = 34;
              if (dist >= minDist) continue;
              const push = (minDist - dist) / 2;
              const ux = dx / dist;
              const uy = dy / dist;
              positions[a] = this.clampPointToV3Quad(pa.x - ux * push, pa.y - uy * push, qKey);
              positions[b] = this.clampPointToV3Quad(pb.x + ux * push, pb.y + uy * push, qKey);
            }
          }
        }
      });

      return positions;
    },

    getV3InitialPosition(keyword, quadrant, quadCounter, layoutPositions) {
      const k = String(keyword || '').trim();
      if (layoutPositions && layoutPositions[k]) {
        return layoutPositions[k];
      }
      return this.getV3QuadBiasPosition(keyword, quadrant, quadCounter);
    },

    calculateNodes(keywords) {
      const quadView = readQuadrantPicture();
      this._quadrantPosForCalc = quadView && quadView.positions ? quadView.positions : null;
      if (quadView && quadView.frame) {
        this.quadrantPlaceMode = true;
        this.quadrantFrame = quadView.frame;
        if (quadView.force && (!this.forceLayoutSnapshot || !Object.keys(this.forceLayoutSnapshot).length)) {
          this.forceLayoutSnapshot = quadView.force;
        }
      }
      // 🔥 如果设置了作者筛选，只统计该作者有贡献的关键词
      const authorFilterText = (this.authorFilter || '').trim().toLowerCase();
      const hasAuthorFilter = authorFilterText.length > 0;
      const useV3Layout = this.isV3Pipeline;
      
      // 统计每个关键词关联数量：
      // v2 = 卡片精确命中；v3 = 文档匹配命中 + 卡片模糊命中
      const cardCounts = {};
      const docHitCounts = {};
      const cardHitCounts = {};
      keywords.forEach(keyword => {
        if (useV3Layout) {
          const docHits = this.countV3DocHits(keyword);
          const cardHits = this.countV3CardHits(keyword, hasAuthorFilter ? authorFilterText : '');
          docHitCounts[keyword] = docHits;
          cardHitCounts[keyword] = cardHits;
          cardCounts[keyword] = docHits + cardHits;
          return;
        }
        const matchingCards = this.effectiveCards.filter(card => {
          if (!card.keyWords) return false;
          const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
          const hasKeyword = cardKeywords.includes(keyword);
          
          // 🔥 如果设置了作者筛选，只统计该作者的卡片
          if (hasAuthorFilter && hasKeyword) {
            const cardWriter = (card.writer || '').toLowerCase();
            return cardWriter.includes(authorFilterText);
          }
          
          return hasKeyword;
        });
        
        cardCounts[keyword] = matchingCards.length;
        docHitCounts[keyword] = 0;
        cardHitCounts[keyword] = matchingCards.length;
      });
      
      // 计算最小和最大卡片数（用于缩放和颜色计算）
      const counts = Object.values(cardCounts);
      const minCount = Math.min(...counts, 1);
      const maxCount = Math.max(...counts, 1);
      
      // 🔥 临时禁用新关键词检查，先恢复基本功能
      // 检查新关键词（不在初始关键词集合中）
      let initialKeywordsSet = new Set();
      try {
        if (this.initialKeywords) {
          if (Array.isArray(this.initialKeywords)) {
            initialKeywordsSet = new Set(this.initialKeywords);
          } else if (this.initialKeywords.size !== undefined) {
            initialKeywordsSet = new Set(Array.from(this.initialKeywords));
          }
        }
      } catch (e) {
        console.warn('[calculateNodes] 处理initialKeywords时出错:', e);
        initialKeywordsSet = new Set();
      }
      
      // 创建节点
      return keywords.map((keyword, index) => {
        const cardCount = cardCounts[keyword] || 0;
        const docHitCount = docHitCounts[keyword] || 0;
        const cardHitCount = cardHitCounts[keyword] || 0;
        
        // 🔥 获取关键词的四色/DMT属性
        const keywordDMTData = this.keywordFourColorDMTData || {};
        const keywordData = keywordDMTData[keyword] || {};
        const fourColorType = keywordData.four_color_type || '';
        const dmtLevel = keywordData.dmt_level || '';
        let knowledgeType = keywordData.knowledge_type || '';
        if (!knowledgeType && (this.tribalKeywords || []).includes(keyword)) {
          knowledgeType = 'trib';
        }
        if (!knowledgeType) knowledgeType = 'trad';

        const dmtRadiusMap = { D: 7, M: 11, T: 15 };
        const radius = dmtRadiusMap[dmtLevel] || 9;
        
        // 检查是否有保存的位置
        const savedPos = this.savedPositions[keyword];
        
        // 如果没有保存的位置，设置初始位置在SVG中心附近（使用基于index的确定性偏移）
        const centerX = this.svgWidth / 2;
        const centerY = this.svgHeight / 2;
        const initialOffset = 30; // 减小初始偏移范围，让节点更集中
        
        // 使用基于index的确定性偏移，确保布局一致性
        const angle = (index * 137.508) % 360; // 黄金角度，确保均匀分布
        const distance = (index % 3) * initialOffset / 3; // 分层，避免重叠
        const offsetX = Math.cos(angle * Math.PI / 180) * distance;
        const offsetY = Math.sin(angle * Math.PI / 180) * distance;
        
        // 检查是否选中
        const isSelected = this.selectedKeywords.includes(keyword);
        
        // 🔥 检查是否为新关键词（当日（北京时间）新产生的）
        // 获取该关键词关联的所有卡片，检查是否有当日生成的
        let keywordCards = this.effectiveCards.filter(card => {
          if (!card.keyWords) return false;
          const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
          if (useV3Layout) {
            return this.keywordMatchesAny(keyword, cardKeywords);
          }
          return cardKeywords.includes(keyword);
        });
        
        // 🔥 如果设置了作者筛选，只考虑该作者的卡片
        if (hasAuthorFilter) {
          keywordCards = keywordCards.filter(card => {
            const cardWriter = (card.writer || '').toLowerCase();
            return cardWriter.includes(authorFilterText);
          });
        }
        
        let isNew = false;
        if (keywordCards.length > 0) {
          // 获取当日（北京时间）的开始时间
          const now = new Date();
          // 北京时间 = UTC+8
          const beijingTime = new Date(now.getTime() + (8 * 60 * 60 * 1000));
          const todayStart = new Date(beijingTime.getFullYear(), beijingTime.getMonth(), beijingTime.getDate());
          // 转换回UTC时间用于比较
          const todayStartUTC = new Date(todayStart.getTime() - (8 * 60 * 60 * 1000));
          
          // 检查是否有卡片是当日生成的
          isNew = keywordCards.some(card => {
            if (!card.datetime) return false;
            const cardDate = new Date(card.datetime);
            return cardDate >= todayStartUTC;
          });
        }
        
        // 🔥 调试：确认 getNodeColors 被调用
        if (this._calculateNodesDebugCount === undefined) {
          this._calculateNodesDebugCount = 0;
          console.log('[calculateNodes] 开始计算节点，关键词数量:', keywords.length);
          console.log('[calculateNodes] keywordFourColorDMTData键数量:', Object.keys(this.keywordFourColorDMTData || {}).length);
        }
        
        // 根据重要性计算颜色（优先使用关键词四色类型）
        const colors = this.getNodeColors(keyword, cardCount, minCount, maxCount, isSelected);
        const v3Attrs = useV3Layout
          ? this.getV3KeywordAttrs(keyword)
          : { level: null, quadrant: '', pending: false, pendingFaded: false };
        
        // 计算节点内数字的字体大小（根据节点半径自适应）
        const finalRadius = Math.max(radius, 5);
        const countFontSize = Math.max(8, Math.min(finalRadius * 0.6, 12));

        let nodeX = savedPos ? savedPos.x : (centerX + offsetX);
        let nodeY = savedPos ? savedPos.y : (centerY + offsetY);
        const quadPos = this._quadrantPosForCalc && this._quadrantPosForCalc[keyword];
        if (quadPos && quadPos.x != null && quadPos.y != null) {
          nodeX = quadPos.x;
          nodeY = quadPos.y;
        }
        
        // 🔥 如果设置了作者筛选且该关键词没有该作者的卡片，跳过此节点（部落关键词必显不跳过）
        // v3：词来自文档，作者筛只影响数字，不因无卡隐藏节点
        const isTribalKw = (this.tribalKeywords || []).includes(keyword) || knowledgeType === 'trib';
        if (hasAuthorFilter && !isTribalKw && !useV3Layout) {
          const keywordCardsForAuthor = this.effectiveCards.filter(card => {
            if (!card.keyWords) return false;
            const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
            if (!cardKeywords.includes(keyword)) return false;
            const cardWriter = (card.writer || '').toLowerCase();
            return cardWriter.includes(authorFilterText);
          });
          if (keywordCardsForAuthor.length === 0) {
            return null; // 跳过此节点
          }
        }
        
        const v3Lv = useV3Layout ? this.parseV3KeywordLevel(keyword, (this.semanticReorganizeMeta || {}).keyword_levels || {}) : null;
        const labelFontSize = !useV3Layout ? 10 : (v3Lv != null && v3Lv <= 0 ? 13 : (v3Lv === 1 ? 11 : 9));
        const labelWeight = useV3Layout && v3Lv != null && v3Lv <= 1 ? 650 : 400;

        return {
          id: index,
          label: keyword,
          cardCount: cardCount,
          docHitCount,
          cardHitCount,
          radius: finalRadius,
          fontSize: labelFontSize,
          labelFontSize,
          labelWeight,
          v3Level: v3Lv,
          v3ChildCount: 0,
          countFontSize: countFontSize,
          countTextColor: '#ffffff',
          x: nodeX,
          y: nodeY,
          fx: quadPos ? quadPos.x : (savedPos ? savedPos.x : undefined),
          fy: quadPos ? quadPos.y : (savedPos ? savedPos.y : undefined),
          color: colors.color,
          dmtLevel: dmtLevel,
          knowledgeType: knowledgeType,
          stroke: colors.stroke,
          strokeWidth: colors.strokeWidth,
          textColor: '#333',
          level: v3Attrs.level,
          quadrant: v3Attrs.quadrant,
          pending: v3Attrs.pending,
          pendingFaded: !!v3Attrs.pendingFaded,
          // 保存用于颜色更新的数据
          minCount: minCount,
          maxCount: maxCount,
          // 🔥 标记是否为新关键词（确保是布尔值）
          isNew: !!isNew,
          // 🔥 是否为部落知识关键词（菱形显示）；大本体以 knowledge_type=trib 为准
          isTribal: isTribalKw
        };
      }).filter(node => node !== null); // 🔥 过滤掉null节点（作者筛选时跳过的节点）
    },
    
    // 🔥 计算foreignObject位置和尺寸的辅助方法（显示在节点上方，更清晰）
    getForeignObjectX(node) {
      // 居中显示，确保宽度至少120px
      return -60; // 固定宽度的一半
    },
    getForeignObjectY(node) {
      const radius = node.radius || 10;
      // 显示在节点上方，留出足够空间
      return -(radius + 35);
    },
    getForeignObjectWidth(node) {
      // 固定最小宽度，确保能完整显示8个字
      return 120;
    },
    getForeignObjectHeight(node) {
      // 固定高度，确保输入框清晰可见
      return 30;
    },
    
    handleNodeClick(node, event) {
      if (this.isV3Pipeline && node && node.pending) {
        if (event) {
          event.preventDefault();
          event.stopPropagation();
        }
        this.openPendingDialog(node);
        return;
      }
      this.toggleKeywordSelection(node.label);
    },

    openPendingDialog(node) {
      this.closeContextMenu();
      this.pendingDialogNode = node;
      this.pendingSelectedChoice = null;
      this.pendingCustomText = '';
      this.showPendingDialog = true;
    },

    pendingOptionBucket(opt) {
      const label = String((opt && opt.label) || '');
      const id = String((opt && opt.id) || '');
      const patch = (opt && opt.attr_patch && typeof opt.attr_patch === 'object') ? opt.attr_patch : {};
      if ((opt && opt.kind === 'quadrant') || /^(verify_|direct_)/.test(id)) return 'know';
      if (/不一致|矛盾|对不上|纪要/.test(label)) return 'conflict';
      if (patch.four_color_type || /四色/.test(label)) return 'color';
      if (/^DMT|DMT归为|DMT改为/.test(label) || (patch.dmt_level && !/^(知道|认可|我知道)/.test(label))) return 'dmt';
      if (patch.knowledge_type || /知识类型|属性改为/.test(label)) return 'knowledge';
      if (/^(知道|认可)[：:]|^我知道|^我能准确/.test(label)) return 'meaning';
      if (/不了解|我不清楚|不清楚|不知道|不确定|说不清|需要补充/.test(label)) return 'know';
      if (patch.dmt_level) return 'dmt';
      return 'meaning';
    },

    pendingOptionEffect(opt) {
      const id = String((opt && opt.id) || '');
      if (id === 'verify_true_know' || id === 'direct_know') return '确认后按「你知道」归位，虚线去掉。';
      if (id === 'verify_false_know' || id === 'direct_unknow') return '确认后按「你还不确定」归位，虚线去掉。';
      if (id === 'verify_partial') return '确认后先按「还没完全知道」归位，以后还能改属性。';
      if (opt && opt.kind === 'quadrant' && opt.human_know === true) return '确认后按「你知道」归位，虚线去掉。';
      if (opt && opt.kind === 'quadrant' && opt.human_know === false) return '确认后按「你还不确定」归位，虚线去掉。';
      return '';
    },

    closePendingDialog() {
      this.showPendingDialog = false;
      this.pendingDialogNode = null;
      this.pendingSelectedChoice = null;
      this.pendingCustomText = '';
    },

    openPanelEdit(payload) {
      const p = payload || {};
      this.panelEditKind = p.kind || '';
      this.panelEditIndex = Number.isInteger(p.index) ? p.index : -1;
      this.panelEditScaleKey = p.scaleKey || '';
      this.panelEditItemKey = p.itemKey || '';
      this.panelEditItemName = p.itemName || '';
      this.panelEditCurrent = String(p.current || '');
      this.panelEditDraft = this.panelEditCurrent;
      this.panelEditPicked = '';
      this.panelEditOptions = [];
      this.showPanelEditDialog = true;
      this.fetchPanelEditOptions();
    },

    closePanelEditDialog() {
      if (this.panelEditSaving) return;
      this.showPanelEditDialog = false;
      this.panelEditLoading = false;
    },

    pickPanelEditOption(text) {
      const value = String(text || '').trim();
      this.panelEditPicked = value;
      this.panelEditDraft = value;
    },

    async fetchPanelEditOptions() {
      const username = (localStorage.getItem('userId') || '').trim();
      if (!username) return;
      this.panelEditLoading = true;
      try {
        const data = await semantic_panel_suggest({
          username,
          scene_name: this.getSceneName() || this.sceneName || '',
          kind: this.panelEditKind,
          current: this.panelEditCurrent,
          scale_key: this.panelEditScaleKey,
          item_key: this.panelEditItemKey,
          item_name: this.panelEditItemName,
        });
        if (data.error_num !== 0) throw new Error(data.msg || '生成失败');
        const opts = Array.isArray(data.options) ? data.options.map((x) => String(x).trim()).filter(Boolean) : [];
        if (this.showPanelEditDialog) this.panelEditOptions = opts;
      } catch (e) {
        console.error('[KeywordNetworkGraph] fetchPanelEditOptions', e);
        if (this.showPanelEditDialog) this.panelEditOptions = [];
      } finally {
        this.panelEditLoading = false;
      }
    },

    async deleteV3SubIssue(index) {
      const list = this.v3SubIssues.slice();
      if (index < 0 || index >= list.length) return;
      const removed = list[index];
      if (!window.confirm('删掉这条子问题？')) return;
      list.splice(index, 1);
      await this.saveV3IntentPreference({
        preferred_sub_issues: list,
        panel_edit: { action: '删除子问题', target: removed },
      });
    },

    async confirmPanelEdit() {
      const draft = String(this.panelEditDraft || '').trim();
      if (!draft) return;
      this.panelEditSaving = true;
      try {
        let ok = false;
        if (this.panelEditKind === 'scale_edit') {
          ok = await this.saveV3IntentPreference({
            preferred_scale_definitions: {
              [this.panelEditScaleKey]: { [this.panelEditItemKey]: draft },
            },
            panel_edit: {
              action: '修改刻度说明',
              target: `${this.panelEditItemName || this.panelEditItemKey}`,
            },
          });
        } else if (this.panelEditKind === 'quadrant_edit') {
          ok = await this.saveV3IntentPreference({
            preferred_quadrant_definitions: {
              [this.panelEditItemKey]: draft,
            },
            panel_edit: {
              action: '修改象限内涵',
              target: `${this.panelEditItemName || this.panelEditItemKey}`,
            },
          });
        } else {
          const list = this.v3SubIssues.slice();
          const action = this.panelEditKind === 'sub_add' ? '添加子问题' : '修改子问题';
          if (this.panelEditKind === 'sub_add') list.push(draft);
          else if (this.panelEditIndex >= 0 && this.panelEditIndex < list.length) list.splice(this.panelEditIndex, 1, draft);
          else {
            this.panelEditSaving = false;
            return;
          }
          ok = await this.saveV3IntentPreference({
            preferred_sub_issues: list,
            panel_edit: { action, target: draft.slice(0, 40) },
          });
        }
        this.panelEditSaving = false;
        if (ok) this.closePanelEditDialog();
      } catch (e) {
        this.panelEditSaving = false;
      }
    },

    async saveV3IntentPreference(patch) {
      const username = (localStorage.getItem('userId') || '').trim();
      if (!username) {
        this.$message.error('未登录，无法保存偏好');
        return;
      }
      try {
        const data = await semantic_intent_preference({
          username,
          scene_name: this.getSceneName() || this.sceneName || '',
          patch: patch || {},
        });
        if (data.error_num !== 0) {
          throw new Error(data.msg || '保存失败');
        }
        this.applyV3IntentPatchToMeta(patch);
        this.$message.success('已保存偏好');
        this.$emit('intent-preference-saved', patch);
        return true;
      } catch (e) {
        console.error('[KeywordNetworkGraph] saveV3IntentPreference', e);
        this.$message.error(`保存失败：${e.message || '未知错误'}`);
        return false;
      }
    },

    applyV3IntentPatchToMeta(patch) {
      if (!patch || !this.semanticReorganizeMeta) return;
      const meta = this.semanticReorganizeMeta;
      if (patch.preferred_core_issue) {
        meta.core_issue = patch.preferred_core_issue;
      }
      if (Array.isArray(patch.preferred_sub_issues)) {
        const subs = patch.preferred_sub_issues.map((x) => String(x).trim()).filter(Boolean);
        this.$set(meta, 'sub_issues', subs);
        if (meta.book_top_keywords && typeof meta.book_top_keywords === 'object') {
          this.$set(meta.book_top_keywords, 'sub_issues', subs.slice());
        }
      }
      if (patch.preferred_top && patch.preferred_top.top1) {
        const tops = meta.book_top_keywords && typeof meta.book_top_keywords === 'object'
          ? { ...meta.book_top_keywords }
          : {};
        tops.top1 = [patch.preferred_top.top1];
        meta.book_top_keywords = tops;
      }
      if (patch.preferred_scale_definitions && typeof patch.preferred_scale_definitions === 'object') {
        const scale = meta.scale_definitions && typeof meta.scale_definitions === 'object'
          ? JSON.parse(JSON.stringify(meta.scale_definitions))
          : {};
        Object.keys(patch.preferred_scale_definitions).forEach((key) => {
          const val = patch.preferred_scale_definitions[key];
          if (val && typeof val === 'object') {
            scale[key] = { ...(scale[key] || {}), ...val };
          }
        });
        meta.scale_definitions = scale;
      }
      if (patch.preferred_quadrant_definitions && typeof patch.preferred_quadrant_definitions === 'object') {
        const pack = meta.quadrant_meaning && typeof meta.quadrant_meaning === 'object'
          ? JSON.parse(JSON.stringify(meta.quadrant_meaning))
          : { definitions: {} };
        const defs = pack.definitions && typeof pack.definitions === 'object' ? { ...pack.definitions } : {};
        Object.keys(patch.preferred_quadrant_definitions).forEach((key) => {
          const val = String(patch.preferred_quadrant_definitions[key] || '').trim();
          if (val) defs[key] = val;
        });
        pack.definitions = defs;
        this.$set(meta, 'quadrant_meaning', pack);
      }
    },

    /** 打开 Top 备选替换对话框：由用户点选该档中要被替换的词，可取消 */
    applyV3TopAlternative(tierKey, altWord) {
      const tier = String(tierKey || '').trim();
      const word = String(altWord || '').trim();
      if (!tier || !word) return;
      const meta = this.semanticReorganizeMeta || {};
      const tops = meta.book_top_keywords || {};
      const raw = tops[tier];
      let current = Array.isArray(raw)
        ? raw.map((x) => String(x).trim()).filter(Boolean)
        : (raw ? [String(raw).trim()] : []);
      if (!current.length) {
        const n = { top1: 1, top3: 3, top5: 5, top10: 10 }[tier] || 3;
        current = (meta.book_keywords || []).map((x) => String(x).trim()).filter(Boolean).slice(0, n);
      }
      if (!current.length) {
        this.$message.warning(`当前没有可替换的 ${tier} 词`);
        return;
      }
      this.topReplaceTierKey = tier;
      this.topReplaceAltWord = word;
      this.topReplaceCandidates = current;
      this.topReplaceSelected = current.length === 1 ? current[0] : '';
      this.topReplaceSaving = false;
      this.showTopReplaceDialog = true;
    },

    closeTopReplaceDialog() {
      this.showTopReplaceDialog = false;
      this.topReplaceTierKey = '';
      this.topReplaceAltWord = '';
      this.topReplaceCandidates = [];
      this.topReplaceSelected = '';
      this.topReplaceSaving = false;
    },

    /** 用户确认后：用备选替换其点选的该档现有词，并同步属性/层次/展示 */
    async confirmV3TopAlternativeReplace() {
      const username = (localStorage.getItem('userId') || '').trim();
      if (!username) {
        this.$message.error('未登录');
        return;
      }
      const tier = String(this.topReplaceTierKey || '').trim();
      const word = String(this.topReplaceAltWord || '').trim();
      const replaceWord = String(this.topReplaceSelected || '').trim();
      if (!tier || !word || !replaceWord) {
        this.$message.warning('请先选择要替换的词');
        return;
      }
      this.topReplaceSaving = true;
      try {
        const data = await semantic_top_alternative_replace({
          username,
          scene_name: this.getSceneName() || this.sceneName || '',
          tier,
          alt_word: word,
          replace_word: replaceWord,
        });
        if (data.error_num !== 0) {
          throw new Error(data.msg || '替换失败');
        }
        const oldWord = String(data.old || replaceWord).trim();
        const newWord = String(data.new || word).trim();
        if (this.semanticReorganizeMeta) {
          const meta = this.semanticReorganizeMeta;
          if (data.book_top_keywords) meta.book_top_keywords = data.book_top_keywords;
          if (data.hierarchy_links) meta.hierarchy_links = data.hierarchy_links;
          if (data.keyword_levels) meta.keyword_levels = data.keyword_levels;
          if (data.quadrants) meta.quadrants = data.quadrants;
          if (data.book_keywords) meta.book_keywords = data.book_keywords;
        }
        if (data.keyword_map && typeof data.keyword_map === 'object') {
          this.keywordFourColorDMTData = { ...data.keyword_map };
        } else if (oldWord && newWord && oldWord !== newWord) {
          const local = { ...(this.keywordFourColorDMTData || {}) };
          if (local[oldWord] && !local[newWord]) {
            local[newWord] = { ...local[oldWord] };
            delete local[oldWord];
          }
          this.keywordFourColorDMTData = local;
        }
        if (oldWord && newWord && oldWord !== newWord) {
          (this.nodes || []).forEach((n) => {
            if (n && n.label === oldWord) n.label = newWord;
          });
        }
        this.$message.success(
          oldWord && oldWord !== newWord
            ? `已用「${newWord}」替换「${oldWord}」（${tier}）`
            : `已更新 ${tier}`,
        );
        this.$emit('top-alternative-replaced', {
          tier, old: oldWord, new: newWord,
          book_top_keywords: data.book_top_keywords,
          book_keywords: data.book_keywords,
          keyword_map: data.keyword_map,
        });
        this.closeTopReplaceDialog();
        this.$nextTick(() => {
          try {
            this.refreshNodeVisualFromAttrs();
            if (typeof this.calculateLinks === 'function' && this.nodes) {
              const labels = this.nodes.map((n) => n.label).filter(Boolean);
              this.links = this.calculateLinks(labels);
            }
          } catch (e) {
            console.warn('[KeywordNetworkGraph] refresh after top replace', e);
          }
        });
      } catch (e) {
        console.error('[KeywordNetworkGraph] confirmV3TopAlternativeReplace', e);
        this.$message.error(`替换失败：${e.message || '未知错误'}`);
      } finally {
        this.topReplaceSaving = false;
      }
    },

    async confirmPendingChoice() {
      const node = this.pendingDialogNode;
      if (!node || this.pendingConfirmSaving) return;
      const word = String(node.label || '').trim();
      const custom = String(this.pendingCustomText || '').trim();
      const opt = this.pendingSelectedChoice;
      const choice = opt && opt.id ? String(opt.id).trim() : '';
      if (!choice && !custom) {
        this.$message.warning('请选择或填写一项');
        return;
      }
      const username = (localStorage.getItem('userId') || '').trim();
      if (!username) {
        this.$message.error('未登录');
        return;
      }
      this.pendingConfirmSaving = true;
      try {
        const previewApplied = (opt && opt.id)
          ? { option_id: opt.id, human_know: opt.human_know }
          : undefined;
        const data = await semantic_confirm_pending({
          username,
          scene_name: this.getSceneName() || this.sceneName || '',
          word,
          choice: choice || 'custom',
          custom_text: custom,
          preview_applied: previewApplied,
        });
        if (data.error_num !== 0) {
          throw new Error(data.msg || '确认失败');
        }
        this.applyPendingConfirmLocally(word, data);
        this.$message.success('已确认');
        this.closePendingDialog();
        this.initializeNetwork();
      } catch (e) {
        console.error('[KeywordNetworkGraph] confirmPendingChoice', e);
        this.$message.error(`确认失败：${e.message || '未知错误'}`);
      } finally {
        this.pendingConfirmSaving = false;
      }
    },

    applyPendingConfirmLocally(word, data) {
      const kwEntry = data.keyword && typeof data.keyword === 'object' ? data.keyword : {};
      const quadEntry = data.quadrant && typeof data.quadrant === 'object' ? data.quadrant : {};
      if (!this.keywordFourColorDMTData) this.keywordFourColorDMTData = {};
      this.keywordFourColorDMTData[word] = {
        ...(this.keywordFourColorDMTData[word] || {}),
        ...kwEntry,
      };
      if (this.semanticReorganizeMeta) {
        const quads = this.semanticReorganizeMeta.quadrants && typeof this.semanticReorganizeMeta.quadrants === 'object'
          ? { ...this.semanticReorganizeMeta.quadrants }
          : {};
        quads[word] = { ...(quads[word] || {}), ...quadEntry };
        this.semanticReorganizeMeta.quadrants = quads;
      }
    },

    // 🔥 处理右键点击（显示菜单）
    handleRightClick(node, event) {
      event.preventDefault();
      event.stopPropagation();

      this.closeLinkContextMenu();
      if (this.isV3Pipeline && node && node.pending) {
        this.openPendingDialog(node);
        return;
      }
      // 🔥 显示右键菜单
      this.contextMenuNode = node;
      this.contextMenuPosition = {
        x: event.clientX,
        y: event.clientY
      };
      this.contextMenuVisible = true;
    },

    // 🔥 关闭右键菜单
    closeContextMenu() {
      this.contextMenuVisible = false;
      this.contextMenuNode = null;
    },

    closeLinkContextMenu() {
      this.linkContextMenuVisible = false;
      this.linkContextMenuLink = null;
      this.highlightedLink = null;
      this.fusionLinkTooltip.visible = false;
    },

    // 层次连边右键菜单
    handleLinkRightClick(link, event) {
      event.preventDefault();
      event.stopPropagation();
      if (!link || link.linkType !== 'hierarchy') {
        return;
      }
      this.closeContextMenu();
      this.linkContextMenuLink = link;
      this.linkContextMenuPosition = {
        x: event.clientX,
        y: event.clientY
      };
      this.linkContextMenuVisible = true;
      this.highlightedLink = link;
    },

    async setLinkStrength(strength) {
      const link = this.linkContextMenuLink;
      if (!link || link.linkType !== 'hierarchy') {
        this.closeLinkContextMenu();
        return;
      }
      if (this.linkStrengthSaving) return;
      if (link.linkStrength === strength) {
        this.closeLinkContextMenu();
        return;
      }
      const parent = link.parentKeyword || (link.source && link.source.label) || '';
      const child = link.childKeyword || (link.target && link.target.label) || '';
      if (!parent || !child) {
        this.$message.error('无法识别连边端点');
        this.closeLinkContextMenu();
        return;
      }

      this.linkStrengthSaving = true;
      try {
        const apiBaseUrl = this.getApiBaseUrl();
        const scopeType = (this.ontologyScopeType || '').trim();
        const scopeId = String(this.ontologyScopeId || '').trim();
        const useSceneClusterApi = !!(scopeType && scopeId);
        const url = useSceneClusterApi
          ? `${apiBaseUrl}/api/scene_cluster_update_link_strength`
          : `${apiBaseUrl}/api/update_hierarchy_link_strength`;
        const body = useSceneClusterApi
          ? {
              scope_type: scopeType,
              scope_id: scopeId,
              viewer: this.ontologyViewerUsername,
              parent,
              child,
              strength
            }
          : {
              username: localStorage.getItem('userId'),
              scene_name: this.getSceneName(),
              parent,
              child,
              strength
            };
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        const data = await response.json();
        if (data.error_num !== 0) {
          throw new Error(data.msg || '保存失败');
        }

        const strengthStyle = {
          '强': { width: 3.6, opacity: 0.92, color: '#35286e' },
          '强中': { width: 2.6, opacity: 0.78, color: '#5a4a92' },
          '普通': { width: 1.7, opacity: 0.62, color: '#6d628c' },
        };
        const style = strengthStyle[strength] || strengthStyle['普通'];
        link.linkStrength = strength;
        link.width = style.width;
        link.opacity = style.opacity;
        link.color = style.color;

        // 同步 meta.hierarchy_links（跳过 deep watch 的整图重初始化）
        this._skipSemanticMetaReinit = true;
        try {
          const meta = this.semanticReorganizeMeta || {};
          if (Array.isArray(data.hierarchy_links) && data.hierarchy_links.length) {
            if (this.semanticReorganizeMeta) {
              this.semanticReorganizeMeta.hierarchy_links = data.hierarchy_links;
            }
            if (this.$parent && this.$parent.semanticReorganizeMeta) {
              this.$parent.semanticReorganizeMeta.hierarchy_links = data.hierarchy_links;
            }
          } else if (Array.isArray(meta.hierarchy_links)) {
            const linksMeta = meta.hierarchy_links;
            for (let i = 0; i < linksMeta.length; i++) {
              const item = linksMeta[i];
              if (!item || item.length < 2) continue;
              const a = String(item[0] || '').trim();
              const b = String(item[1] || '').trim();
              if ((a === parent && b === child) || (a === child && b === parent)) {
                if (item.length >= 3) {
                  item[2] = strength;
                } else {
                  linksMeta[i] = [a, b, strength];
                }
                break;
              }
            }
          }
          this.$emit('hierarchy-links-updated', data.hierarchy_links || meta.hierarchy_links || []);
        } finally {
          this.$nextTick(() => {
            this._skipSemanticMetaReinit = false;
          });
        }

        this.$message.success(`已设为「${strength}」`);
      } catch (error) {
        console.error('[KeywordNetworkGraph] 更新连边强度失败:', error);
        this.$message.error('保存失败：' + (error.message || '未知错误'));
      } finally {
        this.linkStrengthSaving = false;
        this.closeLinkContextMenu();
      }
    },
    
    // 🔥 处理文档点击事件（关闭右键菜单和对话框）
    handleDocumentClick(event) {
      // 🔥 如果点击的不是对话框内部和菜单，关闭对话框和菜单
      if (!event.target.closest('.color-dmt-dialog') && !event.target.closest('.context-menu')) {
        if (this.contextMenuVisible) {
          this.closeContextMenu();
        }
        if (this.linkContextMenuVisible) {
          this.closeLinkContextMenu();
        }
        if (this.showColorDialog || this.showDMTDialog || this.showKnowledgeDialog) {
          this.closeDialogs();
        }
      }
    },
    
    // 🔥 右键菜单：修改关键词
    handleEditKeyword() {
      if (this.contextMenuNode) {
        this.startEdit(this.contextMenuNode);
        this.closeContextMenu();
      }
    },
    
    // 🔥 右键菜单：修改关键词四色属性
    handleEditFourColor() {
      if (!this.contextMenuNode) return;
      
      const keyword = this.contextMenuNode.label;
      const currentData = this.keywordFourColorDMTData[keyword] || {};
      const currentColor = currentData.four_color_type || '';
      
      // 🔥 关闭菜单，显示自定义对话框
      this.closeContextMenu();
      
      const colors = ['R', 'B', 'P', 'G'];
      const colorNames = { 'R': '红色', 'B': '蓝色', 'P': '紫色', 'G': '绿色' };
      
      this.dialogKeyword = keyword;
      this.dialogCurrentValue = currentColor;
      this.dialogOptions = colors;
      this.dialogOptionNames = colorNames;
      this.dialogType = 'color';
      this.showColorDialog = true;
    },
    
    // 🔥 右键菜单：修改关键词DMT属性
    handleEditDMT() {
      if (!this.contextMenuNode) return;
      
      const keyword = this.contextMenuNode.label;
      const currentData = this.keywordFourColorDMTData[keyword] || {};
      const currentDMT = currentData.dmt_level || '';
      
      this.closeContextMenu();
      
      const dmtLevels = ['D', 'M', 'T'];
      const dmtNames = { 'D': '底层', 'M': '中层', 'T': '顶层' };
      
      this.dialogKeyword = keyword;
      this.dialogCurrentValue = currentDMT;
      this.dialogOptions = dmtLevels;
      this.dialogOptionNames = dmtNames;
      this.dialogType = 'dmt';
      this.showDMTDialog = true;
    },

    handleEditKnowledgeType() {
      if (!this.contextMenuNode) return;

      const keyword = this.contextMenuNode.label;
      const currentData = this.keywordFourColorDMTData[keyword] || {};
      const currentKt = currentData.knowledge_type || '';

      this.closeContextMenu();

      const ktOptions = ['trad', 'org', 'trib'];
      const ktNames = { trad: '传统知识', org: '组织知识', trib: '部落知识' };

      this.dialogKeyword = keyword;
      this.dialogCurrentValue = currentKt;
      this.dialogOptions = ktOptions;
      this.dialogOptionNames = ktNames;
      this.dialogType = 'knowledge';
      this.showKnowledgeDialog = true;
    },

    // 🔥 检查是否存在永久卡（用于右键菜单显示）
    hasPermanentCard() {
      if (!this.contextMenuNode) return false;
      const keyword = this.contextMenuNode.label;
      return this.checkPermanentCardExists(keyword);
    },
    
    // 🔥 检查指定关键词是否存在永久卡（辅助方法）
    checkPermanentCardExists(keyword) {
      // 通过父组件获取卡片列表，检查是否存在该关键词的永久卡
      if (this.$parent && this.$parent.cardList) {
        return this.$parent.cardList.some(card => 
          card.title === '关键词神经元永久卡' && 
          card.keyWords && 
          card.keyWords === keyword
        );
      }
      return false;
    },
    
    // 🔥 右键菜单：生成/更新关键词神经元永久卡
    async handleGenerateOrUpdatePermanentCard() {
      if (!this.contextMenuNode) return;
      
      const keyword = this.contextMenuNode.label;
      this.closeContextMenu();

      // 🔥 在操作前判断是生成还是更新（用于显示正确的成功消息）
      const hasCardBefore = this.checkPermanentCardExists(keyword);
      const actionText = hasCardBefore ? '更新' : '生成';

      // 🔥 如果是更新操作，找到对应的永久卡并设置loading状态
      let existingCardCid = null;
      if (hasCardBefore && this.$parent && this.$parent.cardList) {
        const permanentCard = this.$parent.cardList.find(card => {
          if (card.title !== '关键词神经元永久卡' || !card.keyWords) return false;
          const keywords = card.keyWords.split(/[,，]/).map(k => k.trim());
          return keywords.includes(keyword);
        });
        if (permanentCard) {
          existingCardCid = permanentCard.cid;
          // 调用父组件方法设置loading状态
          if (this.$parent.handlePermanentCardUpdateStart) {
            this.$parent.handlePermanentCardUpdateStart(existingCardCid);
          }
        }
      } else {
        // 🔥 如果是生成操作，显示等待卡片
        if (this.$parent && this.$parent.handlePermanentCardGenerateStart) {
          this.$parent.handlePermanentCardGenerateStart();
        }
      }
      
      try {
        // 1. 获取相关卡片（通过父组件）
        if (!this.$parent || !this.$parent.cardList) {
          this.$message.error('无法获取卡片列表');
          // 清除loading状态
          if (hasCardBefore && existingCardCid && this.$parent.handlePermanentCardUpdateComplete) {
            this.$parent.handlePermanentCardUpdateComplete(existingCardCid);
          } else if (!hasCardBefore && this.$parent.handlePermanentCardGenerateComplete) {
            this.$parent.handlePermanentCardGenerateComplete(null);
          }
          return;
        }
        
        const allCards = this.$parent.cardList;
        
        // 2. 筛选包含该关键词的卡片
        const keywordCards = allCards.filter(card => {
          if (!card.keyWords) return false;
          const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
          return cardKeywords.includes(keyword);
        });
        
        // 3. 筛选QA卡片
        const qaCards = keywordCards.filter(card => {
          // 判断是否为QA卡：有history字段或content中包含"提问"
          return card.history || (card.content && card.content.includes('提问'));
        });
        
        // 4. 筛选参考卡片（非QA卡片，且有four_color_type和dmt_level）
        const referenceCards = keywordCards.filter(card => {
          // 判断是否为QA卡：有history字段或content中包含"提问"
          const isQA = card.history || (card.content && card.content.includes('提问'));
          const hasAttributes = card.four_color_type && card.dmt_level;
          return !isQA && hasAttributes;
        });
        
        // 按综合得分排序
        referenceCards.sort((a, b) => {
          const scoreA = (a.score || 0) * 0.3 + (a.scoreSFT || 0) * 0.7;
          const scoreB = (b.score || 0) * 0.3 + (b.scoreSFT || 0) * 0.7;
          return scoreB - scoreA;
        });
        
        // 选择前5张作为参考卡片
        const selectedCards = referenceCards.slice(0, 5);
        
        if (selectedCards.length === 0 && qaCards.length === 0) {
          this.$message.warning(`关键词"${keyword}"没有找到相关卡片，无法生成永久卡`);
          // 清除loading状态
          if (hasCardBefore && existingCardCid && this.$parent.handlePermanentCardUpdateComplete) {
            this.$parent.handlePermanentCardUpdateComplete(existingCardCid);
          } else if (!hasCardBefore && this.$parent.handlePermanentCardGenerateComplete) {
            this.$parent.handlePermanentCardGenerateComplete(null);
          }
          return;
        }
        
        // 5. 调用后端API生成/更新永久卡片
        const apiBaseUrl = this.getApiBaseUrl();
        const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
        const isGroupNotebook = currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
        const originRealName = localStorage.getItem('originRealName') || '';
        
        const response = await fetch(`${apiBaseUrl}/api/generate_permanent_card`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            keyword: keyword,
            cards: selectedCards,
            qa_cards: qaCards,
            username: localStorage.getItem('userId'),
            scene_name: this.$parent.sceneName || '',
            sub_scene_name: this.$parent.subSceneName || '',
            is_group_notebook: isGroupNotebook,
            origin_real_name: originRealName
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        if (data.error_num !== 0) {
          throw new Error(data.msg || '生成失败');
        }
        
        // // 6. 刷新卡片列表
        // let newCardId = null;
        // if (this.$parent && typeof this.$parent.get_all_cards === 'function') {
        //   await this.$parent.get_all_cards();

        //   // 🔥 查找新生成的卡片（用于跳转）
        //   if (!hasCardBefore && this.$parent.cardList) {
        //     const newCard = this.$parent.cardList.find(card => {
        //       if (card.title !== '关键词神经元永久卡' || !card.keyWords) return false;
        //       const keywords = card.keyWords.split(/[,，]/).map(k => k.trim());
        //       return keywords.includes(keyword);
        //     });
        //     if (newCard) {
        //       newCardId = newCard.cid;
        //     }
        //   } else if (hasCardBefore) {
        //     // 更新操作，使用原有的cid
        //     newCardId = existingCardCid;
        //   }
        // }

        // 6. 刷新卡片列表
        let newCardId = null;
        if (hasCardBefore) {
          // 更新操作，使用原有的cid
          newCardId = existingCardCid;
        } else {
          // 生成操作，从API响应中获取card_id
          newCardId = data.card_id || null;
          console.log('[handleGenerateOrUpdatePermanentCard] 从API响应获取的新卡片ID:', newCardId);
        }
        
        if (this.$parent && typeof this.$parent.get_all_cards === 'function') {
          await this.$parent.get_all_cards();
        }

        // 🔥 清除loading状态并处理完成逻辑
        if (hasCardBefore && existingCardCid) {
          // 更新操作：清除cardTidying overlay
          if (this.$parent.handlePermanentCardUpdateComplete) {
            this.$parent.handlePermanentCardUpdateComplete(existingCardCid);
          }
        } else {
          // 生成操作：隐藏等待卡片，跳转到新卡片
          if (this.$parent.handlePermanentCardGenerateComplete) {
            this.$parent.handlePermanentCardGenerateComplete(newCardId);
          }
        }
        
        // 显示成功消息（使用操作前的判断结果）
        this.$message.success(`关键词"${keyword}"的神经元永久卡${actionText}成功！`);
      } catch (error) {
        console.error('[handleGenerateOrUpdatePermanentCard] 生成/更新永久卡失败:', error);
        this.$message.error('生成/更新永久卡失败：' + error.message);

        // 🔥 错误时也要清除loading状态
        if (hasCardBefore && existingCardCid && this.$parent.handlePermanentCardUpdateComplete) {
          this.$parent.handlePermanentCardUpdateComplete(existingCardCid);
        } else if (!hasCardBefore && this.$parent.handlePermanentCardGenerateComplete) {
          this.$parent.handlePermanentCardGenerateComplete(null);
        }
      }
    },
    
    // 🔥 右键菜单：删除关键词神经元永久卡
    async handleDeletePermanentCard() {
      if (!this.contextMenuNode) return;
      
      const keyword = this.contextMenuNode.label;
      this.closeContextMenu();
      
      // 确认删除
      if (!confirm(`确定要删除关键词"${keyword}"的神经元永久卡吗？`)) {
        return;
      }
      
      try {
        // 调用后端API删除永久卡
        const apiBaseUrl = this.getApiBaseUrl();
        const response = await fetch(`${apiBaseUrl}/api/delete_permanent_card`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            keyword: keyword,
            username: localStorage.getItem('userId')
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        if (data.error_num !== 0) {
          throw new Error(data.msg || '删除失败');
        }
        
        // 刷新卡片列表
        if (this.$parent && typeof this.$parent.get_all_cards === 'function') {
          await this.$parent.get_all_cards();
        }
        
        this.$message.success(`关键词"${keyword}"的神经元永久卡已删除`);
      } catch (error) {
        console.error('[handleDeletePermanentCard] 删除永久卡失败:', error);
        this.$message.error('删除永久卡失败：' + error.message);
      }
    },
    
    // 🔥 确认选择对话框
    confirmDialogChoice(selectedValue) {
      if (!this.dialogKeyword || !selectedValue) return;
      
      const keyword = this.dialogKeyword;
      const currentData = this.keywordFourColorDMTData[keyword] || {};
      
      if (this.dialogType === 'color') {
        this.updateKeywordFourColorDMTViaAPI(
          keyword, selectedValue, currentData.dmt_level || '', currentData.knowledge_type || ''
        );
      } else if (this.dialogType === 'dmt') {
        this.updateKeywordFourColorDMTViaAPI(
          keyword, currentData.four_color_type || '', selectedValue, currentData.knowledge_type || ''
        );
      } else if (this.dialogType === 'knowledge') {
        this.updateKeywordFourColorDMTViaAPI(
          keyword, currentData.four_color_type || '', currentData.dmt_level || '', selectedValue
        );
      }
      
      this.closeDialogs();
    },
    
    // 🔥 关闭所有对话框
    closeDialogs() {
      this.showColorDialog = false;
      this.showDMTDialog = false;
      this.showKnowledgeDialog = false;
      this.dialogKeyword = null;
      this.dialogCurrentValue = '';
      this.dialogOptions = [];
      this.dialogOptionNames = {};
      this.dialogType = '';
    },
    
    // 🔥 取消融合
    cancelFusion() {
      this.showFusionDialog = false;
      this.fusionSourceKeyword1 = '';
      this.fusionSourceKeyword2 = '';
      this.isFusing = false;
      this.fusionKeywordOptions = [];
      this.selectedKeywordIndex = -1;
      this.editingKeywordIndex = -1;
      this.editingField = '';
      this.editingKeywordData = { keyword: '', four_color_type: 'P', dmt_level: 'M' };
      // 恢复被拖拽节点的位置
      if (this.draggedNode && this.dragStartPos) {
        this.draggedNode.x = this.dragStartPos.x;
        this.draggedNode.y = this.dragStartPos.y;
        this.draggedNode.fx = this.dragStartPos.x;
        this.draggedNode.fy = this.dragStartPos.y;
      }
    },
    
    // 🔥 确认融合（第一步：获取3个关键词选项）
    async confirmFusion() {
      if (this.isFusing) return;
      
      this.isFusing = true;
      const keyword1 = this.fusionSourceKeyword1;
      const keyword2 = this.fusionSourceKeyword2;
      
      try {
        const apiBaseUrl = this.getApiBaseUrl();
        const apiUrl = `${apiBaseUrl}/api/fuse_keywords`;
        
        const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
        const isGroupNotebook = currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
        const originRealName = localStorage.getItem('originRealName') || '';
        
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            keyword1: keyword1,
            keyword2: keyword2,
            username: localStorage.getItem('userId'),
            scene_name: this.getSceneName(),
            sub_scene_name: this.getSubSceneName(),
            is_group_notebook: isGroupNotebook,
            origin_real_name: originRealName,
            useRelay: true  // 🔥 false使用Claude，true则使用8卡服务器小模型
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error_num === 0 && data.keyword_options && data.keyword_options.length >= 3) {
          // 为每个选项添加hasBeenEdited标记和初始值（用于后续对比用户的修改）
          this.fusionKeywordOptions = data.keyword_options.map(opt => ({
            ...opt,
            hasBeenEdited: false,
            originalFourColorType: opt.four_color_type,  // 🔥 保存初始四色类型
            originalDmtLevel: opt.dmt_level,              // 🔥 保存初始DMT层次
            originalPerspective: opt.perspective || ''    // 🔥 保存初始视角说明
          }));
          this.selectedKeywordIndex = -1;
          this.editingKeywordIndex = -1;
          this.editingField = '';
          this.isFusing = false;
          this.isRegeneratingAll = false;
          this.isRegeneratingOption = {};
          // 对话框已显示，等待用户选择和编辑
        } else {
          throw new Error(data.msg || '生成关键词选项失败');
        }
      } catch (error) {
        console.error('[KeywordNetworkGraph] 获取融合关键词选项失败:', error);
        this.$message.error('获取关键词选项失败：' + error.message);
        this.isFusing = false;
        this.showFusionDialog = false;
      }
    },
    
    // 🔥 选择关键词选项
    selectKeywordOption(index) {
      // 如果点击时正在编辑，先保存
      if (this.editingKeywordIndex === index && this.editingField) {
        this.saveEditField(index, this.editingField);
        return;
      }
      
      this.selectedKeywordIndex = index;
      // 如果正在编辑其他选项，取消编辑
      if (this.editingKeywordIndex !== -1 && this.editingKeywordIndex !== index) {
        this.cancelEditField(this.editingKeywordIndex);
      }
    },
    
    // 🔥 开始编辑字段
    startEditField(index, field) {
      const option = this.fusionKeywordOptions[index];
      // 保存当前选项数据到编辑数据
      this.editingKeywordData = {
        keyword: option.keyword,
        four_color_type: option.four_color_type,
        dmt_level: option.dmt_level,
        perspective: option.perspective || ''
      };
      this.editingKeywordIndex = index;
      this.editingField = field;
      
      // 聚焦到输入框或下拉框
      this.$nextTick(() => {
        const refName = field === 'keyword' ? `keywordInput_${index}` : 
                       field === 'four_color_type' ? `colorSelect_${index}` : 
                       field === 'dmt_level' ? `dmtSelect_${index}` :
                       `perspectiveInput_${index}`;
        const element = this.$refs[refName];
        if (element) {
          const el = Array.isArray(element) ? element[0] : element;
          if (el) {
            el.focus();
            // 对于keyword和perspective，光标聚焦到末尾而不是全选
            if (field === 'keyword' || field === 'perspective') {
              if (el.setSelectionRange) {
                const length = el.value ? el.value.length : 0;
                el.setSelectionRange(length, length);
              } else if (el.createTextRange) {
                // IE兼容
                const range = el.createTextRange();
                range.collapse(false);
                range.select();
              }
            }
          }
        }
      });
    },
    
    // 🔥 保存编辑的字段
    saveEditField(index, field) {
      if (field === 'keyword') {
        if (!this.editingKeywordData.keyword || !this.editingKeywordData.keyword.trim()) {
          this.$message.warning('关键词名称不能为空');
          this.cancelEditField(index);
          return;
        }
        this.fusionKeywordOptions[index].keyword = this.editingKeywordData.keyword.trim();
        // 标记为已编辑
        if (!this.fusionKeywordOptions[index].hasBeenEdited) {
          this.fusionKeywordOptions[index].hasBeenEdited = true;
        }
      } else if (field === 'four_color_type') {
        const oldValue = this.fusionKeywordOptions[index].four_color_type;
        this.fusionKeywordOptions[index].four_color_type = this.editingKeywordData.four_color_type;
        // 如果值发生变化，标记为已编辑
        if (oldValue !== this.editingKeywordData.four_color_type) {
          this.fusionKeywordOptions[index].hasBeenEdited = true;
        }
      } else if (field === 'dmt_level') {
        const oldValue = this.fusionKeywordOptions[index].dmt_level;
        this.fusionKeywordOptions[index].dmt_level = this.editingKeywordData.dmt_level;
        // 如果值发生变化，标记为已编辑
        if (oldValue !== this.editingKeywordData.dmt_level) {
          this.fusionKeywordOptions[index].hasBeenEdited = true;
        }
      } else if (field === 'perspective') {
        this.fusionKeywordOptions[index].perspective = this.editingKeywordData.perspective.trim();
        // 标记为已编辑
        if (!this.fusionKeywordOptions[index].hasBeenEdited) {
          this.fusionKeywordOptions[index].hasBeenEdited = true;
        }
      }
      
      // 结束编辑
      this.editingKeywordIndex = -1;
      this.editingField = '';
    },
    
    // 🔥 取消编辑字段
    cancelEditField(index) {
      this.editingKeywordIndex = -1;
      this.editingField = '';
    },
    
    // 🔥 确认按钮鼠标悬停事件
    handleConfirmButtonMouseEnter(event) {
      if (!this.isFusing && this.selectedKeywordIndex !== -1) {
        event.target.style.background = '#5a4a9c';
      }
    },
    
    // 🔥 确认按钮鼠标离开事件
    handleConfirmButtonMouseLeave(event) {
      if (!this.isFusing && this.selectedKeywordIndex !== -1) {
        event.target.style.background = '#493d8b';
      }
    },
    
    // 🔥 取消按钮鼠标进入事件
    handleCancelButtonMouseEnter(event) {
      if (!this.isFusing && !this.isRegeneratingAll) {
        event.target.style.background = '#bbb';
      }
    },
    
    // 🔥 取消按钮鼠标离开事件
    handleCancelButtonMouseLeave(event) {
      if (!this.isFusing && !this.isRegeneratingAll) {
        event.target.style.background = '#ccc';
      }
    },
    
    // 🔥 整体重来按钮鼠标进入事件
    handleRegenerateButtonMouseEnter(event) {
      if (!this.isFusing && !this.isRegeneratingAll) {
        event.target.style.background = '#6b5c97';
      }
    },
    
    // 🔥 整体重来按钮鼠标离开事件
    handleRegenerateButtonMouseLeave(event) {
      if (!this.isFusing && !this.isRegeneratingAll) {
        event.target.style.background = '#7a6ba8';
      }
    },
    
    // 🔥 整体重来一遍（重新生成3个关键词选项）
    async regenerateAllOptions() {
      if (this.isFusing || this.isRegeneratingAll) return;
      
      this.isRegeneratingAll = true;
      const keyword1 = this.fusionSourceKeyword1;
      const keyword2 = this.fusionSourceKeyword2;
      
      try {
        const apiBaseUrl = this.getApiBaseUrl();
        const apiUrl = `${apiBaseUrl}/api/regenerate_fuse_keywords`;
        
        const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
        const isGroupNotebook = currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
        const originRealName = localStorage.getItem('originRealName') || '';
        
        // 传递当前3个选项，让后端理解用户为什么觉得不够好
        const currentOptions = this.fusionKeywordOptions.map(opt => ({
          keyword: opt.keyword,
          four_color_type: opt.four_color_type,
          dmt_level: opt.dmt_level,
          perspective: opt.perspective
        }));
        
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            keyword1: keyword1,
            keyword2: keyword2,
            username: localStorage.getItem('userId'),
            scene_name: this.getSceneName(),
            sub_scene_name: this.getSubSceneName(),
            is_group_notebook: isGroupNotebook,
            origin_real_name: originRealName,
            useRelay: true,  // 使用8卡服务器小模型
            current_options: currentOptions  // 传递当前选项，帮助理解用户需求
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error_num === 0 && data.keyword_options && data.keyword_options.length >= 3) {
          // 为每个选项添加hasBeenEdited标记和初始值（用于后续对比用户的修改）
          this.fusionKeywordOptions = data.keyword_options.map(opt => ({
            ...opt,
            hasBeenEdited: false,
            originalFourColorType: opt.four_color_type,  // 🔥 保存初始四色类型
            originalDmtLevel: opt.dmt_level,              // 🔥 保存初始DMT层次
            originalPerspective: opt.perspective || ''    // 🔥 保存初始视角说明
          }));
          this.selectedKeywordIndex = -1;
          this.editingKeywordIndex = -1;
          this.editingField = '';
          this.isRegeneratingAll = false;
        } else {
          throw new Error(data.msg || '重新生成关键词选项失败');
        }
      } catch (error) {
        console.error('[KeywordNetworkGraph] 重新生成融合关键词选项失败:', error);
        this.$message.error('重新生成关键词选项失败：' + error.message);
        this.isRegeneratingAll = false;
      }
    },
    
    // 🔥 单独重做某个选项（根据编辑后的四色/DMT/视角重新生成关键词名）
    async regenerateSingleOption(index) {
      if (this.isFusing || this.isRegeneratingOption[index]) return;
      
      const option = this.fusionKeywordOptions[index];
      if (!option.hasBeenEdited) return; // 如果没有编辑过，不执行重做
      
      this.isRegeneratingOption[index] = true;
      
      const keyword1 = this.fusionSourceKeyword1;
      const keyword2 = this.fusionSourceKeyword2;
      
      try {
        const apiBaseUrl = this.getApiBaseUrl();
        const apiUrl = `${apiBaseUrl}/api/regenerate_single_fuse_keyword`;
        
        const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
        const isGroupNotebook = currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
        const originRealName = localStorage.getItem('originRealName') || '';
        
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            keyword1: keyword1,
            keyword2: keyword2,
            username: localStorage.getItem('userId'),
            scene_name: this.getSceneName(),
            sub_scene_name: this.getSubSceneName(),
            is_group_notebook: isGroupNotebook,
            origin_real_name: originRealName,
            useRelay: true,  // 使用8卡服务器小模型
            original_keyword: option.keyword,  // 🔥 传递原有的融合关键词名作为参照
            original_four_color_type: option.originalFourColorType || option.four_color_type,  // 🔥 传递原始四色类型
            original_dmt_level: option.originalDmtLevel || option.dmt_level,                    // 🔥 传递原始DMT层次
            original_perspective: option.originalPerspective || option.perspective || '',       // 🔥 传递原始视角说明
            four_color_type: option.four_color_type,      // 用户修改后的四色类型
            dmt_level: option.dmt_level,                  // 用户修改后的DMT层次
            perspective: option.perspective || ''         // 用户修改后的视角说明
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error_num === 0 && data.keyword) {
          // 更新关键词名，保留编辑标记
          this.fusionKeywordOptions[index].keyword = data.keyword;
          this.isRegeneratingOption[index] = false;
        } else {
          throw new Error(data.msg || '重新生成关键词失败');
        }
      } catch (error) {
        console.error('[KeywordNetworkGraph] 重新生成单个关键词失败:', error);
        this.$message.error('重新生成关键词失败：' + error.message);
        this.isRegeneratingOption[index] = false;
      }
    },
    
    // 🔥 确认选择的关键词并生成永久卡片
    async confirmSelectedKeyword() {
      if (this.selectedKeywordIndex === -1 || this.isFusing) return;
      
      this.isFusing = true;
      const selectedOption = this.fusionKeywordOptions[this.selectedKeywordIndex];
      const keyword1 = this.fusionSourceKeyword1;
      const keyword2 = this.fusionSourceKeyword2;
      
      // 关闭对话框
      this.showFusionDialog = false;
      
      // 通知父组件开始融合（显示等待卡、跳转顶部）
      if (this.$parent && typeof this.$parent.handleFusionKeywordStart === 'function') {
        this.$parent.handleFusionKeywordStart(null);
      }
      
      try {
        const apiBaseUrl = this.getApiBaseUrl();
        const apiUrl = `${apiBaseUrl}/api/confirm_fuse_keyword`;
        
        const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
        const isGroupNotebook = currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
        const originRealName = localStorage.getItem('originRealName') || '';
        
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            keyword: selectedOption.keyword,
            four_color_type: selectedOption.four_color_type,
            dmt_level: selectedOption.dmt_level,
            keyword1: keyword1,
            keyword2: keyword2,
            username: localStorage.getItem('userId'),
            scene_name: this.getSceneName(),
            sub_scene_name: this.getSubSceneName(),
            is_group_notebook: isGroupNotebook,
            origin_real_name: originRealName
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error_num === 0) {
          this.$message.success(`融合成功！新关键词: ${selectedOption.keyword}`);
          
          this.isFusing = false;
          const newCardId = data.card_id;
          this.fusionSourceKeyword1 = '';
          this.fusionSourceKeyword2 = '';
          this.fusionKeywordOptions = [];
          this.selectedKeywordIndex = -1;
          this.editingKeywordIndex = -1;
          this.editingField = '';
          
          // 通知父组件刷新数据
          if (this.$parent && typeof this.$parent.get_all_cards === 'function') {
            await this.$parent.get_all_cards();
          }
          
          // 通知父组件融合完成（隐藏等待卡、跳转到新卡片）
          if (this.$parent && typeof this.$parent.handleFusionKeywordComplete === 'function') {
            this.$parent.handleFusionKeywordComplete(newCardId);
          }
        } else {
          throw new Error(data.msg || '生成永久卡片失败');
        }
      } catch (error) {
        console.error('[KeywordNetworkGraph] 确认融合关键词失败:', error);
        this.$message.error('生成永久卡片失败：' + error.message);
        this.isFusing = false;
        // 融合失败时也要清除等待卡
        if (this.$parent && typeof this.$parent.handleFusionKeywordComplete === 'function') {
          this.$parent.handleFusionKeywordComplete(null);
        }
      }
    },
    
    // 🔥 更新关键词四色DMT属性（调用后端API）
    async updateKeywordFourColorDMTViaAPI(keyword, fourColorType, dmtLevel, knowledgeType) {
      try {
        // 🔥 参数验证
        if (!keyword || typeof keyword !== 'string') {
          console.error('[KeywordNetworkGraph] updateKeywordFourColorDMTViaAPI: keyword参数无效', keyword);
          return;
        }
        // 先记下改前属性，供意图跟随（须在本地数据被覆盖前）
        const prevAttrsSnapshot = {
          four_color_type: ((this.keywordFourColorDMTData || {})[keyword] || {}).four_color_type || '',
          dmt_level: ((this.keywordFourColorDMTData || {})[keyword] || {}).dmt_level || '',
          knowledge_type: ((this.keywordFourColorDMTData || {})[keyword] || {}).knowledge_type || '',
        };
        
        const apiBaseUrl = this.getApiBaseUrl();
        const useOntologyApi = this.isOntologyScopeMode;
        const apiUrl = useOntologyApi
          ? `${apiBaseUrl}/api/scene_cluster_update_keyword_attrs`
          : `${apiBaseUrl}/api/update_keyword_four_color_dmt`;
        const body = useOntologyApi
          ? {
              scope_type: String(this.ontologyScopeType || '').trim(),
              scope_id: String(this.ontologyScopeId || '').trim(),
              viewer: this.ontologyViewerUsername,
              keyword: String(keyword).trim(),
              four_color_type: fourColorType ? String(fourColorType).trim() : '',
              dmt_level: dmtLevel ? String(dmtLevel).trim() : '',
              knowledge_type: knowledgeType ? String(knowledgeType).trim() : '',
            }
          : {
              keyword: String(keyword).trim(),
              four_color_type: fourColorType ? String(fourColorType).trim() : '',
              dmt_level: dmtLevel ? String(dmtLevel).trim() : '',
              knowledge_type: knowledgeType ? String(knowledgeType).trim() : '',
              username: localStorage.getItem('userId'),
              scene_name: this.getSceneName()
            };
        
        const response = await fetch(apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body)
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        if (data.error_num === 0) {
          if (this.isV3Pipeline && !useOntologyApi) {
            try {
              await semantic_intent_preference({
                username: localStorage.getItem('userId'),
                scene_name: this.getSceneName(),
                patch: {
                  locked_attr_words: [String(keyword).trim()],
                  attr_edits: [{
                    word: String(keyword).trim(),
                    before: prevAttrsSnapshot,
                    after: {
                      four_color_type: fourColorType ? String(fourColorType).trim() : '',
                      dmt_level: dmtLevel ? String(dmtLevel).trim() : '',
                      knowledge_type: knowledgeType ? String(knowledgeType).trim() : '',
                    },
                  }],
                },
              });
            } catch (lockErr) {
              console.warn('[KeywordNetworkGraph] locked_attr_words', lockErr);
            }
          }
          // 大本体：同步父级 attrs 对象
          if (useOntologyApi && data.keywordFourColorDMT) {
            Object.keys(data.keywordFourColorDMT).forEach((k) => {
              this.keywordFourColorDMTData[k] = { ...(data.keywordFourColorDMT[k] || {}) };
            });
          }
          // 🔥 更新本地数据
          if (!this.keywordFourColorDMTData[keyword]) {
            this.keywordFourColorDMTData[keyword] = {};
          }
          this.keywordFourColorDMTData[keyword].four_color_type = fourColorType;
          this.keywordFourColorDMTData[keyword].dmt_level = dmtLevel;
          this.keywordFourColorDMTData[keyword].knowledge_type = knowledgeType || '';
          
          this.locallyUpdatedKeywords.add(keyword);
          
          this.saveLocalUpdatedKeywordsToStorage(keyword, fourColorType, dmtLevel, knowledgeType);
          
          // 🔥 更新节点属性（不重新筛选，避免节点消失）
          this.$nextTick(() => {
            if (this.viewMode === 'network' && this.graphKeywordPool.length > 0) {
              // 🔥 先确保当前节点列表包含刚修改的关键词（如果它在当前nodes中）
              const currentKeywordLabel = keyword;
              const existingNode = this.nodes.find(n => n.label === currentKeywordLabel);
              
              if (existingNode) {
                // 如果节点已存在，只更新其属性，不重新筛选
                const counts = this.nodes.map(n => n.cardCount || 0);
                const minCount = Math.min(...counts, 1);
                const maxCount = Math.max(...counts, 1);
                
                const colors = this.getNodeColors(
                  keyword,
                  existingNode.cardCount || 0,
                  minCount,
                  maxCount,
                  this.selectedKeywords.includes(keyword)
                );
                existingNode.color = colors.color;
                existingNode.stroke = colors.stroke;
                existingNode.strokeWidth = colors.strokeWidth;
                
                // 更新节点的四色/DMT数据
                existingNode.dmtLevel = dmtLevel || '';
                existingNode.knowledgeType = knowledgeType || '';
                const dmtRadiusMap = { D: 7, M: 11, T: 15 };
                existingNode.radius = Math.max(dmtRadiusMap[dmtLevel] || 9, 5);
                
                // 更新连接（因为节点属性可能变了）
                const allKeywordsToShow = this.nodes.map(n => n.label);
                this.links = this.calculateLinks(allKeywordsToShow);
                
                // 更新视图
                this.updateLinkPositions();
                this.updateNodePositions();
                this.$forceUpdate();
              } else {
                // 如果节点不存在，使用智能筛选（会优先保留用户修改过的关键词）
                const keywordsToShow = this.getDisplayKeywords(this.graphKeywordPool, this.getActiveNodeLimit());
                
                // 🔥 保存已有节点的固定位置（fx/fy），以便重新计算后恢复
                const fixedPositions = new Map();
                this.nodes.forEach(node => {
                  if (node.fx !== undefined && node.fy !== undefined) {
                    fixedPositions.set(node.label, { fx: node.fx, fy: node.fy });
                  }
                });
                
                this.nodes = this.calculateNodes(keywordsToShow);
                this.links = this.calculateLinks(keywordsToShow);
                
                // 🔥 恢复已有节点的固定位置
                this.nodes.forEach(node => {
                  const fixedPos = fixedPositions.get(node.label);
                  if (fixedPos) {
                    node.x = fixedPos.fx;
                    node.y = fixedPos.fy;
                    node.fx = fixedPos.fx;
                    node.fy = fixedPos.fy;
                  }
                });
                
                this.loadSavedPositions();
                this.restorePositions();
                this.updateLinkPositions();
                this.updateNodePositions();
              }
            }
          });
          
          // 🔥 通知父组件记录本地更新（避免被覆盖）
          this.$emit('keyword-dmt-local-updated', {
            keyword: keyword,
            four_color_type: fourColorType,
            dmt_level: dmtLevel,
            knowledge_type: knowledgeType || ''
          });
          
          this.$nextTick(() => {
            this.$emit('keyword-dmt-updated', {
              keyword: keyword,
              four_color_type: fourColorType,
              dmt_level: dmtLevel,
              knowledge_type: knowledgeType || ''
            });
          });
        } else {
          alert('更新失败：' + (data.msg || '未知错误'));
        }
      } catch (error) {
        console.error('[KeywordNetworkGraph] 更新关键词四色DMT失败:', error);
        alert('更新失败，请重试：' + error.message);
      }
    },
    
    // 🔥 开始编辑关键词
    startEdit(node) {
      this.editingNode = node;
      this.editingText = node.label;
    },
    
    // 🔥 完成编辑
    async finishEdit(node) {
      const newKeyword = this.editingText.trim();
      const oldKeyword = node.label;
      
      if (!newKeyword || newKeyword === oldKeyword) {
        this.cancelEdit();
        return;
      }
      
      // 🔥 验证：不能超过8个字
      if (newKeyword.length > 8) {
        alert('关键词不能超过8个字，请重新输入');
        this.editingText = oldKeyword; // 恢复原值
        return;
      }
      
      // // 🔥 验证：检查新关键词是否已存在（排除自己）
      // const existingKeywords = this.keywords.filter(kw => kw !== oldKeyword);
      // if (existingKeywords.includes(newKeyword)) {
      //   alert('该关键词已存在，请使用其他名称');
      //   this.editingText = oldKeyword; // 恢复原值
      //   return;
      // }

      // 🔥 允许改成和已有关键词一样的（合并关键词），不进行验证

      // 🔥 立即更新节点名称和取消编辑状态（在API调用之前）
      const nodeIndex = this.nodes.findIndex(n => n.id === node.id);
      if (nodeIndex !== -1) {
        // 保存节点位置（优先使用fx/fy固定位置）
        const nodeX = this.nodes[nodeIndex].fx !== undefined ? this.nodes[nodeIndex].fx : (this.nodes[nodeIndex].x !== undefined ? this.nodes[nodeIndex].x : null);
        const nodeY = this.nodes[nodeIndex].fy !== undefined ? this.nodes[nodeIndex].fy : (this.nodes[nodeIndex].y !== undefined ? this.nodes[nodeIndex].y : null);
        
        // 更新节点标签
        this.nodes[nodeIndex].label = newKeyword;
        
        // 保持位置不变并固定（防止被力导向布局移动）
        if (nodeX !== null && nodeY !== null) {
          this.nodes[nodeIndex].x = nodeX;
          this.nodes[nodeIndex].y = nodeY;
          this.nodes[nodeIndex].fx = nodeX; // 固定位置
          this.nodes[nodeIndex].fy = nodeY;
          
          // 🔥 保存位置到localStorage（用新关键词保存，确保后续能恢复）
          this.loadSavedPositions();
          if (!this.savedPositions) {
            this.savedPositions = {};
          }
          this.savedPositions[newKeyword] = { x: nodeX, y: nodeY };
          // 删除旧关键词的位置（如果存在）
          if (this.savedPositions[oldKeyword]) {
            delete this.savedPositions[oldKeyword];
          }
          this.savePositions();
        }
        
        // 强制更新视图
        this.$forceUpdate();
      }
      
      // 🔥 立即取消编辑状态
      this.editingNode = null;
      this.editingText = '';

      // 🔥 设置加载状态
      this.isRenamingKeyword = true;
      this.renamingKeyword = newKeyword;
      
      // 🔥 在API调用之前，先通知父组件设置loading状态（本子内）；大本体跳过 CardGrid 逻辑
      if (!this.isOntologyScopeMode) {
        if (this.$parent && typeof this.$parent.handleKeywordRenameStart === 'function') {
          this.$parent.handleKeywordRenameStart({
            oldKeyword: oldKeyword,
            newKeyword: newKeyword
          });
        } else {
          this.$emit('keyword-rename-start', {
            oldKeyword: oldKeyword,
            newKeyword: newKeyword
          });
        }
      }
      
      // 调用后端API更新关键词
      try {
        // 🔥 使用正确的API基础URL
        const apiBaseUrl = this.getApiBaseUrl();
        const apiUrl = `${apiBaseUrl}/api/rename_keyword`;
        
        console.log('[KeywordNetworkGraph] 调用重命名API:', apiUrl);
        
        const useOntologyApi = this.isOntologyScopeMode;
        const response = await fetch(
          useOntologyApi
            ? `${apiBaseUrl}/api/scene_cluster_rename_keyword`
            : apiUrl,
          {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(
            useOntologyApi
              ? {
                  scope_type: String(this.ontologyScopeType || '').trim(),
                  scope_id: String(this.ontologyScopeId || '').trim(),
                  viewer: this.ontologyViewerUsername,
                  old_keyword: oldKeyword,
                  new_keyword: newKeyword,
                }
              : {
                  old_keyword: oldKeyword,
                  new_keyword: newKeyword,
                  username: localStorage.getItem('userId'),
                  scene_name: this.getSceneName()
                }
          )
        });
        
        // 🔥 检查响应状态
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('[KeywordNetworkGraph] 重命名API响应:', data);
        
        if (data.error_num === 0) {
          console.log('[KeywordNetworkGraph] 重命名成功，后端返回need_reanalyze:', data.need_reanalyze);

          if (useOntologyApi) {
            // 大本体：本地同步词表/属性/连边，不依赖本子 CardGrid 刷新
            if (Array.isArray(data.keywords) && data.keywords.length) {
              // keywords 是 prop，通过 emit 让父组件更新
              this.$emit('ontology-keywords-renamed', {
                oldKeyword,
                newKeyword,
                keywords: data.keywords,
                keywordFourColorDMT: data.keywordFourColorDMT || {},
                hierarchy_links: data.hierarchy_links || [],
              });
            }
            if (data.keywordFourColorDMT) {
              Object.keys(data.keywordFourColorDMT).forEach((k) => {
                this.keywordFourColorDMTData[k] = { ...(data.keywordFourColorDMT[k] || {}) };
              });
              if (this.keywordFourColorDMTData[oldKeyword]) {
                delete this.keywordFourColorDMTData[oldKeyword];
              }
            }
            this._skipSemanticMetaReinit = true;
            try {
              if (this.semanticReorganizeMeta && Array.isArray(data.hierarchy_links)) {
                this.semanticReorganizeMeta.hierarchy_links = data.hierarchy_links;
              }
              this.$emit('hierarchy-links-updated', data.hierarchy_links || []);
            } finally {
              this.$nextTick(() => {
                this._skipSemanticMetaReinit = false;
              });
            }
            // 刷新连线（节点标签已在前面改过）
            const labels = this.nodes.map((n) => n.label);
            this.links = this.calculateLinks(labels);
            this.updateLinkPositions();
            this.updateNodePositions();
            this.$message.success('关键词已更新');
            setTimeout(() => {
              this.isRenamingKeyword = false;
              this.renamingKeyword = '';
            }, 300);
            return;
          }

          // 🔥 重命名成功后，触发父组件更新，并重新分析新关键词的四色DMT
          const needReAnalyze = data.need_reanalyze === true || data.need_reanalyze === undefined;
          console.log('[KeywordNetworkGraph] 准备调用父组件handleKeywordRename:', { oldKeyword, newKeyword, needReAnalyze });
          
          // 🔥 直接通过$parent调用父组件方法，避免事件传递问题
          if (this.$parent && typeof this.$parent.handleKeywordRename === 'function') {
            this.$parent.handleKeywordRename({
              oldKeyword: oldKeyword,
              newKeyword: newKeyword,
              needReAnalyze: needReAnalyze
            });
            console.log('[KeywordNetworkGraph] 已直接调用父组件handleKeywordRename');
          } else {
            // 降级方案：使用emit
            console.warn('[KeywordNetworkGraph] 无法直接调用父组件方法，降级使用emit');
            this.$emit('keyword-renamed', {
              oldKeyword: oldKeyword,
              newKeyword: newKeyword,
              needReAnalyze: needReAnalyze
            });
          }
          
          // 取消编辑状态，等待父组件刷新数据
          // this.editingNode = null;
          // this.editingText = '';
          
          // 🔥 清除加载状态（延迟清除，等待父组件刷新完成）
          setTimeout(() => {
            this.isRenamingKeyword = false;
            this.renamingKeyword = '';
          }, 500);
        } else {
          // alert('更新失败：' + (data.msg || '未知错误'));
          this.$message.error('更新失败：' + (data.msg || '未知错误'));
          this.cancelEdit();
          // 立即清除加载状态
          this.isRenamingKeyword = false;
          this.renamingKeyword = '';
        }
      } catch (error) {
        console.error('[KeywordNetworkGraph] 更新关键词失败:', error);
        console.error('[KeywordNetworkGraph] 错误详情:', error.message);
        this.$message.error('更新失败，请重试：' + error.message);
        this.cancelEdit();
        // 立即清除加载状态
        this.isRenamingKeyword = false;
        this.renamingKeyword = '';
      }
    },
    
    // 🔥 取消编辑
    cancelEdit() {
      this.editingNode = null;
      this.editingText = '';
    },
    
    // 🔥 获取API基础URL
    getApiBaseUrl() {
      // 从配置文件获取
      try {
        // 使用动态import或者直接使用window对象
        if (typeof window !== 'undefined' && window.API_BASE_URL) {
          return window.API_BASE_URL;
        }
        // 尝试从模块导入（在Vue组件中可能需要动态导入）
        const config = require('@/config/apiConfig');
        return config.API_BASE_URL || 'http://localhost:8000'; // 默认值
      } catch (e) {
        console.warn('[KeywordNetworkGraph] 获取API_BASE_URL失败，使用默认值:', e);
        // 如果都失败，返回默认值
        return 'http://localhost:8000';
      }
    },
    
    // 🔥 获取场景名（从props获取）
    getSceneName() {
      return this.sceneName || null;
    },
    
    // 🔥 获取子场景名（从父组件获取）
    getSubSceneName() {
      if (this.$parent && this.$parent.subSceneName) {
        return this.$parent.subSceneName;
      }
      return null;
    },
    
    calculateLinks(keywords) {
      const links = [];
      const nodeMap = {};
      this.nodes.forEach(node => {
        nodeMap[node.label] = node;
      });

      // 精进梳理成功后：连线按 bookKWConnect / hierarchy_links 的直接层次关系展示
      const meta = this.semanticReorganizeMeta || {};
      const hierarchyLinks = Array.isArray(meta.hierarchy_links) ? meta.hierarchy_links : [];
      const useHierarchy = hierarchyLinks.length > 0;

        if (useHierarchy) {
        const strengthStyle = {
          '强': { width: 3.6, opacity: 0.92, color: '#35286e' },
          '强中': { width: 2.6, opacity: 0.78, color: '#5a4a92' },
          '普通': { width: 1.7, opacity: 0.62, color: '#6d628c' },
        };
        const seen = {};
        hierarchyLinks.forEach((pair) => {
          if (!pair || pair.length < 2) return;
          const kw1 = String(pair[0] || '').trim();
          const kw2 = String(pair[1] || '').trim();
          if (!kw1 || !kw2 || kw1 === kw2) return;
          if (!keywords.includes(kw1) || !keywords.includes(kw2)) return;
          const key = [kw1, kw2].sort().join('|');
          if (seen[key]) return;
          seen[key] = true;
          const source = nodeMap[kw1];
          const target = nodeMap[kw2];
          if (source && target) {
            const strengthRaw = String(pair[2] || '').trim();
            const strength = (strengthRaw === '强' || strengthRaw === '强中' || strengthRaw === '普通')
              ? strengthRaw
              : '普通';
            const style = strengthStyle[strength];
            links.push({
              source: source,
              target: target,
              value: 1,
              width: style.width,
              opacity: style.opacity,
              color: style.color,
              linkType: 'hierarchy',
              linkStrength: strength,
              parentKeyword: kw1,
              childKeyword: kw2
            });
          }
        });

        this.buildV3OverflowBridgeLinks(keywords).forEach((pair) => {
          const kw1 = pair && pair.a;
          const kw2 = pair && pair.b;
          if (!kw1 || !kw2 || !keywords.includes(kw1) || !keywords.includes(kw2)) return;
          const key = [kw1, kw2].sort().join('|');
          if (seen[key]) return;
          seen[key] = true;
          const source = nodeMap[kw1];
          const target = nodeMap[kw2];
          if (!source || !target) return;
          const style = strengthStyle['强中'];
          links.push({
            source,
            target,
            value: 1,
            width: style.width,
            opacity: style.opacity,
            color: style.color,
            linkType: 'hierarchy',
            linkStrength: '强中',
            bridge: true,
            parentKeyword: kw2,
            childKeyword: kw1,
          });
        });

        const lonColorMap = { R: '#dc143c', B: '#1e90ff', P: '#9370db', G: '#3cb371' };
        const chains = Array.isArray(meta.longitude_chains) ? meta.longitude_chains : [];
        chains.forEach((chain, chainIndex) => {
          if (!chain || !Array.isArray(chain.nodes)) return;
          const colorKey = String(chain.color || '').trim().toUpperCase().slice(0, 1);
          const stroke = lonColorMap[colorKey] || '#c45c26';
          const nodes = chain.nodes.map((n) => String(n || '').trim()).filter(Boolean);
          for (let i = 0; i < nodes.length - 1; i += 1) {
            const kw1 = nodes[i];
            const kw2 = nodes[i + 1];
            if (!keywords.includes(kw1) || !keywords.includes(kw2)) continue;
            const lonKey = `lon|${kw1}|${kw2}`;
            if (seen[lonKey]) continue;
            seen[lonKey] = true;
            const source = nodeMap[kw1];
            const target = nodeMap[kw2];
            if (source && target) {
              links.push({
                source,
                target,
                value: 1,
                width: 3.2,
                opacity: 0.95,
                color: stroke,
                dasharray: '8,4',
                linkType: 'longitude',
                longitudeId: `lon-${chainIndex}`,
              });
            }
          }
        });

      } else if (this.isV3Pipeline) {
        // v3 无层次数据时不绘制共现边
      } else {
        // 兼容旧逻辑：共现连线（同卡出现且频次>=2）
        const cooccurrenceMatrix = {};
        keywords.forEach(kw1 => {
          keywords.forEach(kw2 => {
            if (kw1 !== kw2) {
              const key = [kw1, kw2].sort().join('|');
              cooccurrenceMatrix[key] = 0;
            }
          });
        });
        this.effectiveCards.forEach(card => {
          if (!card.keyWords) return;
          const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
          cardKeywords.forEach(kw1 => {
            cardKeywords.forEach(kw2 => {
              if (kw1 !== kw2 && keywords.includes(kw1) && keywords.includes(kw2)) {
                const key = [kw1, kw2].sort().join('|');
                cooccurrenceMatrix[key] = (cooccurrenceMatrix[key] || 0) + 1;
              }
            });
          });
        });
        Object.entries(cooccurrenceMatrix).forEach(([key, count]) => {
          if (count >= 2) {
            const [kw1, kw2] = key.split('|');
            const source = nodeMap[kw1];
            const target = nodeMap[kw2];
            if (source && target) {
              links.push({
                source: source,
                target: target,
                value: count,
                width: Math.max(1, Math.min(count / 2, 5)),
                opacity: Math.min(0.3 + count * 0.1, 0.8),
                color: '#493d8b',
                linkType: 'cooccurrence'
              });
            }
          }
        });
      }
      
      // 🔥 添加融合关系/部落语义关联的连接
      if (this.keywordFusionRelations && typeof this.keywordFusionRelations === 'object') {
        Object.entries(this.keywordFusionRelations).forEach(([fusedKeyword, relation]) => {
          if (!relation || !relation.source_keywords || !Array.isArray(relation.source_keywords)) {
            return;
          }
          const sourceKeywords = relation.source_keywords;
          if (sourceKeywords.length < 2) return;
          const fusedNode = nodeMap[fusedKeyword];
          if (!fusedNode || !keywords.includes(fusedKeyword)) return;
          const isTribal = (this.tribalKeywords || []).includes(fusedKeyword);
          const linkColor = isTribal ? '#2e7d32' : '#ff6b6b';  // 部落关键词用绿色连线
          sourceKeywords.forEach((srcKw) => {
            const srcNode = nodeMap[srcKw];
            if (srcNode && keywords.includes(srcKw)) {
              links.push({
                source: fusedNode,
                target: srcNode,
                value: isTribal ? 'tribal_semantic' : 'fusion',
                width: 2.5,
                opacity: 0.7,
                color: linkColor,
                linkType: isTribal ? 'tribal_semantic' : 'fusion',
                fusionInfo: { fusedKeyword, sourceKeyword: srcKw, otherSourceKeyword: sourceKeywords.find(k => k !== srcKw) }
              });
            }
          });
        });
      }
      
      return links.sort((a, b) => {
        const rank = { longitude: 1, hierarchy: 2, cooccurrence: 2, fusion: 3, tribal_semantic: 3, contour: 4 };
        const sa = a.linkStrength === '普通' ? 0 : (a.linkStrength === '强中' ? 1 : (a.linkStrength === '强' ? 2 : 1));
        const sb = b.linkStrength === '普通' ? 0 : (b.linkStrength === '强中' ? 1 : (b.linkStrength === '强' ? 2 : 1));
        return (rank[a.linkType] || 2) - (rank[b.linkType] || 2) || (sa - sb);
      });
    },
    
    initializeForceLayout() {
      this.forceLayoutToken = (this.forceLayoutToken || 0) + 1;
      const token = this.forceLayoutToken;
      if (this.quadrantModeEnabled()) {
        this.quadrantPlaceMode = true;
        if (this.simulation) this.simulation.stop();
        this.showQuadrantNow();
        return;
      }
      if (this.isV3Pipeline) {
        const childCount = {};
        (this.links || []).forEach((link) => {
          if (link.linkType !== 'hierarchy') return;
          const parent = link.parentKeyword;
          if (!parent) return;
          childCount[parent] = (childCount[parent] || 0) + 1;
        });
        this.nodes.forEach((node) => {
          node.v3ChildCount = childCount[node.label] || 0;
        });
      }
      if (!this.$refs.networkSvg) return;
      
      // 停止之前的模拟
      if (this.simulation) {
        this.simulation.stop();
      }
      
      // 设置固定随机种子（确保布局稳定）- D3 v3 使用 Math.random
      const originalRandom = Math.random;
      let seed = this.layoutSeed;
      Math.random = () => {
        seed = (seed * 9301 + 49297) % 233280;
        return seed / 233280;
      };
      
      // 等高、经度只是叠层，不参与力导向
      const simLinks = (this.links || []).filter((link) => (
        link.linkType !== 'longitude' && link.linkType !== 'contour'
      ));
      // 使用 D3 v3 API 创建力导向布局（平衡紧凑性和间距）
      this.simulation = d3.layout.force()
        .nodes(this.nodes)
        .links(simLinks)
        .size([this.svgWidth, this.svgHeight])
        .linkDistance(120)
        .linkStrength(0.7)
        .charge(-400)
        .gravity(0.08)
        .friction(0.9)
        .on('tick', () => {
          // 只在模拟运行时更新位置
          if (this.simulation && this.simulation.alpha() > 0.001) {
            // 🔥 对于有固定位置的节点，强制保持固定（防止力导向布局移动它们）
            this.nodes.forEach(node => {
              if (node.fx !== undefined && node.fy !== undefined) {
                node.x = node.fx;
                node.y = node.fy;
              }
            });
            this.updateLinkPositions();
            this.updateNodePositions();
          }
        });
      
      // 开始模拟
      this.simulation.start();
      
      // 运行模拟直到稳定（或设置最大迭代次数）
      let iterations = 0;
      const maxIterations = 300;
      const self = this;
      
      const tick = () => {
        if (token !== self.forceLayoutToken) return;
        if (self.quadrantModeEnabled()) {
          self.quadrantPlaceMode = true;
          if (self.simulation) self.simulation.stop();
          self.showQuadrantNow();
          return;
        }
        if (iterations < maxIterations && self.simulation && self.simulation.alpha() > 0.001) {
          self.simulation.tick();
          iterations++;
          requestAnimationFrame(tick);
        } else {
          if (token !== self.forceLayoutToken) return;
          // 恢复原始随机函数
          Math.random = originalRandom;
          
          if (self.quadrantModeEnabled()) {
            self.quadrantPlaceMode = true;
            self.showQuadrantNow();
            if (self.simulation) {
              self.simulation.stop();
              self.simulation.on('tick', null);
            }
            return;
          }

          // 模拟结束，固定所有节点位置（如果用户没有拖拽过）
          self.nodes.forEach(node => {
            // 🔥 如果节点已经有保存的位置但之前没有固定，现在固定它
            const savedPos = self.savedPositions[node.label];
            if (savedPos && savedPos.x !== undefined && savedPos.y !== undefined) {
              // 如果有保存的位置，使用保存的位置并固定
              if (node.fx === undefined || node.fy === undefined) {
                node.fx = savedPos.x;
                node.fy = savedPos.y;
                node.x = savedPos.x;
                node.y = savedPos.y;
              }
            } else if (node.fx === undefined && node.fy === undefined && node.x !== undefined && node.y !== undefined) {
              // 如果没有保存的位置，固定当前计算的位置
              node.fx = node.x;
              node.fy = node.y;
            }
          });
          
          // 🔥 更新视图并保存位置
          self.updateLinkPositions();
          self.updateNodePositions();
          self.savePositions(undefined, { keepForceLayout: true });
          if (self.quadrantPlaceMode) {
            if (!self.forceLayoutSnapshot) self.captureForceSnapshot();
            self.applyQuadrantPlacement();
          }
          
          // 更新容器宽度，用于计算容器高度
          self.updateContainerWidth();
          
          // 保存基准viewBox范围（第一次布局稳定后），用于重置时保持一致的显示大小（使用对称计算方式）
          if (!self.baseViewBoxBounds) {
            const bounds = self.getNodeBounds();
            const padding = 80; // 与viewBox的padding保持一致
            
            // 计算节点分布的中心点
            const centerX = (bounds.minX + bounds.maxX) / 2;
            const centerY = (bounds.minY + bounds.maxY) / 2;
            
            // 计算节点分布的最大宽度和高度
            const contentWidth = bounds.maxX - bounds.minX;
            const contentHeight = bounds.maxY - bounds.minY;
            
            // 计算viewBox尺寸（内容 + 对称的padding）
            let finalWidth = contentWidth + padding * 2;
            let finalHeight = contentHeight + padding * 2;
            
            // 确保有最小值
            finalWidth = Math.max(finalWidth, 100);
            finalHeight = Math.max(finalHeight, 100);
            
            // 以节点中心为基准，确保上下左右padding对称
            self.baseViewBoxBounds = {
              minX: centerX - finalWidth / 2,
              minY: centerY - finalHeight / 2,
              maxX: centerX + finalWidth / 2,
              maxY: centerY + finalHeight / 2
            };
          }
          
          // 停止模拟并移除tick事件监听，避免持续更新导致抖动
          if (self.simulation) {
            self.simulation.stop();
            self.simulation.on('tick', null); // 移除tick事件监听
          }
        }
      };
      
      tick();
    },
    
    updateLinkPositions() {
      // 更新连接线位置（Vue会自动响应）
      this.links.forEach(link => {
        if (typeof link.source === 'object') {
          // 已经是对象，直接使用
          return;
        } else {
          // 如果是ID，需要转换为节点对象
          const sourceNode = this.nodes.find(n => n.id === link.source);
          const targetNode = this.nodes.find(n => n.id === link.target);
          if (sourceNode) link.source = sourceNode;
          if (targetNode) link.target = targetNode;
        }
      });
    },
    
    updateNodePositions() {
      // 如果模拟已经稳定或停止，就不再强制更新（避免抖动）
      if (!this.simulation || this.simulation.alpha() < 0.01) {
        return;
      }
      // 节点位置会自动更新（通过Vue的响应式）
      this.$forceUpdate();
    },
    
    showTooltip(node, event) {
      // 如果已经显示的是同一个节点，直接返回（避免抖动）
      if (this.tooltip.visible && this.tooltip.data && this.tooltip.data.label === node.label) {
        return;
      }
      
      // 清除之前的定时器
      if (this.tooltipTimer) {
        clearTimeout(this.tooltipTimer);
      }
      
      // 使用防抖延迟，避免频繁更新
      this.tooltipTimer = setTimeout(() => {
        // 立即固定节点位置（避免悬停时抖动）
        if (node.fx === undefined && node.fy === undefined && node.x !== undefined && node.y !== undefined) {
          node.fx = node.x;
          node.fy = node.y;
        }
        
        // 计算主要共现关键词
        const coOccurrences = this.getCoOccurrences(node.label);
        
        // 计算贡献者信息（作者或子场景）
        const contributors = this.getContributors(node.label);
        const isMultiWriter = this.isMultiWriterNotebook();
        
        // 基于节点实际位置计算工具提示位置（通过事件目标元素获取准确位置）
        this.$nextTick(() => {
          let nodeScreenX, nodeScreenY;
          
          // 方法1：优先使用事件目标元素（circle元素）的实际位置
          if (event && event.target && event.target.tagName === 'circle') {
            const circleRect = event.target.getBoundingClientRect();
            nodeScreenX = circleRect.left + circleRect.width / 2; // 圆心X
            nodeScreenY = circleRect.top + circleRect.height / 2; // 圆心Y
          } else if (this.$refs.networkSvg) {
            // 方法2：如果无法获取事件目标，使用SVG坐标转换
            const nodeX = node.fx !== undefined ? node.fx : (node.x !== undefined ? node.x : this.svgWidth / 2);
            const nodeY = node.fy !== undefined ? node.fy : (node.y !== undefined ? node.y : this.svgHeight / 2);
            
            const svg = this.$refs.networkSvg;
            const svgRect = svg.getBoundingClientRect();
            
            // 计算缩放比例
            const scaleX = svgRect.width / this.computedSvgWidth;
            const scaleY = svgRect.height / this.computedSvgHeight;
            
            // 转换为屏幕坐标
            nodeScreenX = svgRect.left + (nodeX * scaleX);
            nodeScreenY = svgRect.top + (nodeY * scaleY);
          } else {
            // 方法3：如果都不可用，使用鼠标位置
            nodeScreenX = event ? (event.clientX || 0) : 0;
            nodeScreenY = event ? (event.clientY || 0) : 0;
          }
          
          // 计算工具提示位置（相对于节点中心，较小偏移）
          const tooltipOffset = 15; // 偏移量，让工具提示更靠近节点
          let tooltipX = nodeScreenX + tooltipOffset;
          let tooltipY = nodeScreenY - 100; // 上移，避免遮挡节点
          
          // 确保工具提示不会超出屏幕（移除固定高度限制，自适应内容）
          const tooltipWidth = 420;
          if (tooltipX + tooltipWidth > window.innerWidth - 20) {
            tooltipX = nodeScreenX - tooltipWidth - tooltipOffset;
          }
          if (tooltipY < 20) {
            tooltipY = nodeScreenY + tooltipOffset;
          }
          // 不设置固定高度，让工具提示自适应内容，但确保不会超出屏幕底部
          // 由于内容会自适应，只需确保顶部不会超出屏幕顶部即可
          
          // 更新工具提示（位置固定，不会抖动）
          this.tooltip = {
            visible: true,
            data: {
              label: node.label,
              cardCount: node.cardCount,
              docHitCount: node.docHitCount || 0,
              cardHitCount: node.cardHitCount || 0,
              contributors: contributors,
              isMultiWriter: isMultiWriter,
              coOccurrences: coOccurrences,
              level: node.level,
              quadrant: node.quadrant,
              pending: node.pending,
            },
            style: {
              left: tooltipX + 'px',
              top: tooltipY + 'px',
              position: 'fixed',
              overflow: 'visible',
              maxHeight: 'none',
              height: 'auto'
            }
          };
          
          // 🔥 如果显示了融合对话框，不要设置highlightedNode
          if (!this.showFusionDialog) {
            this.highlightedNode = node.id;
          }
        });
      }, 100); // 100ms防抖延迟
    },
    
    hideTooltip() {
      // 清除定时器
      if (this.tooltipTimer) {
        clearTimeout(this.tooltipTimer);
        this.tooltipTimer = null;
      }
      
      this.tooltip.visible = false;
      this.highlightedNode = null;
    },
    
    getCoOccurrences(keyword) {
      const coOccurrences = [];
      const keywordsSet = new Set(this.graphKeywordPool);
      
      this.effectiveCards.forEach(card => {
        if (!card.keyWords) return;
        const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
        
        if (cardKeywords.includes(keyword)) {
          cardKeywords.forEach(kw => {
            if (kw !== keyword && keywordsSet.has(kw)) {
              const existing = coOccurrences.find(co => co.keyword === kw);
              if (existing) {
                existing.count++;
              } else {
                coOccurrences.push({ keyword: kw, count: 1 });
              }
            }
          });
        }
      });
      
      return coOccurrences.sort((a, b) => b.count - a.count);
    },
    
    // 判断是否为多作者本子（组本）
    isMultiWriterNotebook() {
      if (!this.effectiveCards || this.effectiveCards.length === 0) return false;
      
      const writers = new Set();
      this.effectiveCards.forEach(card => {
        if (card.writer) {
          writers.add(card.writer);
        }
      });
      
      // 如果writer字段不唯一，则是组本
      return writers.size > 1;
    },
    
    // 提取子场景编号（从contentTitle中提取，如 "S1: xxx" -> "S1"）
    extractSubScene(contentTitle) {
      if (!contentTitle) return null;
      const match = contentTitle.match(/^(S\d+)[:：]/);
      return match ? match[1] : null;
    },
    
    // 获取关键词的贡献者信息（作者或子场景），按卡片质量排序
    getContributors(keyword) {
      const contributorMap = new Map(); // 使用Map存储，key为贡献者名称，value为卡片数组
      const isMultiWriter = this.isMultiWriterNotebook();
      
      // 收集每个贡献者的卡片
      this.effectiveCards.forEach(card => {
        if (!card.keyWords) return;
        const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
        
        if (cardKeywords.includes(keyword)) {
          let contributorName = null;
          
          if (isMultiWriter) {
            // 组本：使用作者信息（只有当writer存在且非空，且不是"未知作者"时才使用）
            if (card.writer && card.writer.trim() && card.writer.trim() !== '未知作者') {
              contributorName = card.writer.trim();
            }
          } else {
            // 个人本子：使用子场景信息
            const subScene = this.extractSubScene(card.contentTitle);
            if (subScene) {
              contributorName = subScene;
            }
          }
          
          // 只有当有有效的贡献者名称时才添加到列表
          if (contributorName) {
            if (!contributorMap.has(contributorName)) {
              contributorMap.set(contributorName, []);
            }
            contributorMap.get(contributorName).push(card);
          }
        }
      });
      
      // 计算每个贡献者的质量指标
      const contributors = [];
      contributorMap.forEach((cards, name) => {
        const totalCount = cards.length;
        
        // 1. 计算四色DMT属性卡片比例
        const dmtCards = cards.filter(card => {
          const fourColor = card.four_color_type ? String(card.four_color_type).trim() : '';
          const dmtLevel = card.dmt_level ? String(card.dmt_level).trim() : '';
          return fourColor !== '' || dmtLevel !== '';
        });
        const dmtRatio = totalCount > 0 ? (dmtCards.length / totalCount) : 0;
        
        // 2. 计算高质量卡片比例（绿/紫/T占四色DMT卡片的比例）
        const highQualityCards = dmtCards.filter(card => {
          const fourColor = (card.four_color_type || '').trim();
          const dmtLevel = (card.dmt_level || '').trim();
          return fourColor === 'G' || fourColor === 'P' || dmtLevel === 'T';
        });
        const highQualityBaseRatio = dmtCards.length > 0 ? (highQualityCards.length / dmtCards.length) : 0;
        
        // 2.1 计算四种颜色覆盖度（R、B、P、G中覆盖了几种）
        const colorSet = new Set();
        dmtCards.forEach(card => {
          const fourColor = (card.four_color_type || '').trim();
          if (fourColor && ['R', 'B', 'P', 'G'].includes(fourColor)) {
            colorSet.add(fourColor);
          }
        });
        const colorCoverage = colorSet.size / 4; // 0-1之间
        
        // 2.2 计算DMT类型覆盖度（D、M、T中覆盖了几种）
        const dmtSet = new Set();
        dmtCards.forEach(card => {
          const dmtLevel = (card.dmt_level || '').trim();
          if (dmtLevel && ['D', 'M', 'T'].includes(dmtLevel)) {
            dmtSet.add(dmtLevel);
          }
        });
        const dmtCoverage = dmtSet.size / 3; // 0-1之间
        
        // 2.3 综合高质量比例：基础比例*0.6 + 颜色覆盖度*0.2 + DMT覆盖度*0.2
        const highQualityRatio = highQualityBaseRatio * 0.6 + colorCoverage * 0.2 + dmtCoverage * 0.2;
        
        // 3. 计算高分卡片比例（score*0.3 + scoreSFT*0.7 > 3.5的比例）
        const highScoreCards = cards.filter(card => {
          const score = card.score || 0;
          const scoreSFT = card.scoreSFT || 0;
          const weightedScore = score * 0.3 + scoreSFT * 0.7;
          return weightedScore > 3.5;
        });
        const highScoreRatio = totalCount > 0 ? highScoreCards.length / totalCount : 0;
        
        // 计算综合质量分数（可以加权平均，这里简单平均）
        const qualityScore = (dmtRatio * 0.4 + highQualityRatio * 0.3 + highScoreRatio * 0.3);
        
        contributors.push({
          name: name,
          count: totalCount,
          dmtRatio: dmtRatio,
          highQualityRatio: highQualityRatio,
          highScoreRatio: highScoreRatio,
          qualityScore: qualityScore
        });
      });
      
      // 按质量分数降序排序（质量高的在前）
      return contributors.sort((a, b) => b.qualityScore - a.qualityScore);
    },
    
    linkHoverLabel(link) {
      if (!link) return '';
      // 最新层次连边：显示连接强度简称；旧共现连边：仍显示共现卡片数
      if (link.linkType === 'hierarchy') {
        const map = { '强': '强', '强中': '中', '普通': '普' };
        return map[link.linkStrength] || '普';
      }
      if (link.linkType === 'longitude') return '经';
      if (link.linkType === 'contour') return '廓';
      return link.value;
    },

    highlightLink(link, event) {
      this.highlightedLink = link;
      
      // 🔥 如果是融合关系，计算tooltip位置
      if (link.linkType === 'fusion' && link.fusionInfo) {
        this.$nextTick(() => {
          // 使用事件坐标作为基准点（鼠标位置在连线上）
          let tooltipX, tooltipY;
          
          if (event && event.clientX !== undefined) {
            // 使用鼠标位置
            tooltipX = event.clientX + 15;
            tooltipY = event.clientY - 40;
          } else if (this.$refs.networkSvg) {
            // 备用方案：使用SVG坐标转换计算连线中点
            const svg = this.$refs.networkSvg;
            const svgRect = svg.getBoundingClientRect();
            
            // 计算连线中点的SVG坐标
            const midX = (link.source.x + link.target.x) / 2;
            const midY = (link.source.y + link.target.y) / 2;
            
            // 使用viewBox计算缩放
            const viewBox = svg.viewBox.baseVal;
            const svgWidth = viewBox.width || this.svgWidth || 800;
            const svgHeight = viewBox.height || this.svgHeight || 500;
            
            // 计算缩放比例
            const scaleX = svgRect.width / svgWidth;
            const scaleY = svgRect.height / svgHeight;
            
            // 转换为屏幕坐标
            tooltipX = svgRect.left + (midX * scaleX) + 15;
            tooltipY = svgRect.top + (midY * scaleY) - 40;
          } else {
            return; // 无法计算位置，不显示tooltip
          }
          
          // 设置tooltip位置
          this.fusionLinkTooltip = {
            visible: true,
            style: {
              left: tooltipX + 'px',
              top: tooltipY + 'px',
              position: 'fixed',
              zIndex: 10000
            },
            data: link.fusionInfo
          };
        });
      } else {
        this.fusionLinkTooltip.visible = false;
      }
    },
    
    resetHighlight() {
      // 连边右键菜单打开时保持高亮，方便对照当前强度
      if (this.linkContextMenuVisible) return;
      this.highlightedLink = null;
      this.fusionLinkTooltip.visible = false;
    },
    
    startDrag(node, event) {
      // 🔥 如果正在编辑，不触发拖拽
      if (this.editingNode) {
        return;
      }
      
      event.preventDefault();
      event.stopPropagation();
      
      // 🔥 记录拖拽开始时间和状态
      this.isDragging = true;
      this.dragStartTime = Date.now();
      this.dragStartPos = {
        x: node.fx !== undefined ? node.fx : (node.x !== undefined ? node.x : 0),
        y: node.fy !== undefined ? node.fy : (node.y !== undefined ? node.y : 0)
      };
      
      // 🔥 只拖拽单个节点，固定其他所有节点位置
      this.nodes.forEach(n => {
        if (n.id !== node.id) {
          // 固定其他节点的位置，防止它们移动
          if (n.fx === undefined && n.x !== undefined && n.y !== undefined) {
            n.fx = n.x;
            n.fy = n.y;
          }
        }
      });
      
      this.draggedNode = node;
      
      // 🔥 获取SVG容器的边界和当前节点在SVG坐标系中的位置
      const svg = this.$refs.networkSvg;
      if (!svg) return;
      
      // 🔥 使用SVG的getScreenCTM获取更精确的坐标转换矩阵
      const svgPoint = svg.createSVGPoint();
      svgPoint.x = event.clientX;
      svgPoint.y = event.clientY;
      
      // 🔥 获取SVG的transform矩阵（考虑viewBox和preserveAspectRatio）
      const ctm = svg.getScreenCTM();
      if (ctm) {
        const inverseCTM = ctm.inverse();
        const svgCoord = svgPoint.matrixTransform(inverseCTM);
        const nodeX = node.fx !== undefined ? node.fx : (node.x !== undefined ? node.x : 0);
        const nodeY = node.fy !== undefined ? node.fy : (node.y !== undefined ? node.y : 0);
        
        // 🔥 计算偏移量（鼠标位置相对于节点中心）
        this.dragOffset = {
          x: svgCoord.x - nodeX,
          y: svgCoord.y - nodeY
        };
      } else {
        // 降级方案：使用viewBox计算
        const svgRect = svg.getBoundingClientRect();
        const viewBox = svg.getAttribute('viewBox') || `0 0 ${svgRect.width} ${svgRect.height}`;
        const vb = viewBox.split(/\s+/).map(Number);
        const viewBoxX = vb[0] || 0;
        const viewBoxY = vb[1] || 0;
        const viewBoxWidth = vb[2] || svgRect.width;
        const viewBoxHeight = vb[3] || svgRect.height;
        
        const scaleX = viewBoxWidth / svgRect.width;
        const scaleY = viewBoxHeight / svgRect.height;
        const mouseX = (event.clientX - svgRect.left) * scaleX + viewBoxX;
        const mouseY = (event.clientY - svgRect.top) * scaleY + viewBoxY;
        
        const nodeX = node.fx !== undefined ? node.fx : (node.x !== undefined ? node.x : 0);
        const nodeY = node.fy !== undefined ? node.fy : (node.y !== undefined ? node.y : 0);
        
        this.dragOffset = {
          x: mouseX - nodeX,
          y: mouseY - nodeY
        };
      }
      
      // 🔥 停止模拟，防止力导向布局干扰拖拽
      if (this.simulation) {
        this.simulation.stop();
      }
      
      window.addEventListener('mousemove', this.onDrag);
      window.addEventListener('mouseup', this.endDrag);
    },
    
    onDrag(event) {
      if (!this.draggedNode || !this.isDragging) return;
      
      event.preventDefault();
      event.stopPropagation();
      
      // 🔥 使用requestAnimationFrame确保流畅更新
      if (this.dragAnimationFrame) {
        cancelAnimationFrame(this.dragAnimationFrame);
      }
      
      this.dragAnimationFrame = requestAnimationFrame(() => {
        // 🔥 获取SVG容器的边界和viewBox信息
        const svg = this.$refs.networkSvg;
        if (!svg) return;
        
        // 🔥 使用SVG的getScreenCTM获取更精确的坐标转换矩阵
        const svgPoint = svg.createSVGPoint();
        svgPoint.x = event.clientX;
        svgPoint.y = event.clientY;
        
        const ctm = svg.getScreenCTM();
        let mouseX, mouseY;
        
        if (ctm) {
          const inverseCTM = ctm.inverse();
          const svgCoord = svgPoint.matrixTransform(inverseCTM);
          mouseX = svgCoord.x;
          mouseY = svgCoord.y;
        } else {
          // 降级方案：使用viewBox计算
          const svgRect = svg.getBoundingClientRect();
          const viewBox = svg.getAttribute('viewBox') || `0 0 ${svgRect.width} ${svgRect.height}`;
          const vb = viewBox.split(/\s+/).map(Number);
          const viewBoxX = vb[0] || 0;
          const viewBoxY = vb[1] || 0;
          const viewBoxWidth = vb[2] || svgRect.width;
          const viewBoxHeight = vb[3] || svgRect.height;
          
          const scaleX = viewBoxWidth / svgRect.width;
          const scaleY = viewBoxHeight / svgRect.height;
          mouseX = (event.clientX - svgRect.left) * scaleX + viewBoxX;
          mouseY = (event.clientY - svgRect.top) * scaleY + viewBoxY;
        }
        
        // 🔥 计算新位置（考虑偏移量，使用四舍五入确保位置精确）
        const newX = Math.round((mouseX - this.dragOffset.x) * 100) / 100;
        const newY = Math.round((mouseY - this.dragOffset.y) * 100) / 100;
        
        // 🔥 直接更新被拖拽节点的位置，并固定它
        this.draggedNode.x = newX;
        this.draggedNode.y = newY;
        this.draggedNode.fx = newX;
        this.draggedNode.fy = newY;
        
        // 🔥 只更新连接线位置，不启动模拟（避免干扰）
        this.updateLinkPositions();
        this.$forceUpdate();
      });
    },
    
    endDrag(event) {
      if (!this.isDragging) return;
      
      event?.preventDefault();
      event?.stopPropagation();
      
      // 🔥 取消动画帧
      if (this.dragAnimationFrame) {
        cancelAnimationFrame(this.dragAnimationFrame);
        this.dragAnimationFrame = null;
      }
      
      // 🔥 清除防抖定时器
      if (this.dragSaveTimer) {
        clearTimeout(this.dragSaveTimer);
        this.dragSaveTimer = null;
      }
      
      if (this.draggedNode) {
        // 🔥 检测是否拖拽到另一个节点上（判断重合）
        const draggedNodeX = this.draggedNode.fx !== undefined ? this.draggedNode.fx : (this.draggedNode.x !== undefined ? this.draggedNode.x : 0);
        const draggedNodeY = this.draggedNode.fy !== undefined ? this.draggedNode.fy : (this.draggedNode.y !== undefined ? this.draggedNode.y : 0);
        const draggedNodeRadius = this.draggedNode.radius || 10;
        
        // 查找是否与其他节点重合（判断不要太敏感，也不要太迟钝）
        // 重合判断：两个节点中心距离 < (半径1 + 半径2) * 0.75 时认为重合（75%重叠触发，不要太敏感也不要太迟钝）
        let targetNode = null;
        for (const node of this.nodes) {
          if (node.id === this.draggedNode.id) continue; // 跳过自己
          
          const nodeX = node.fx !== undefined ? node.fx : (node.x !== undefined ? node.x : 0);
          const nodeY = node.fy !== undefined ? node.fy : (node.y !== undefined ? node.y : 0);
          const nodeRadius = node.radius || 10;
          
          const distance = Math.sqrt(
            Math.pow(draggedNodeX - nodeX, 2) + 
            Math.pow(draggedNodeY - nodeY, 2)
          );
          // 计算重叠阈值：当两个节点中心距离小于两个半径之和的75%时，认为重合
          const overlapThreshold = (draggedNodeRadius + nodeRadius) * 0.75;
          
          if (distance < overlapThreshold) {
            targetNode = node;
            console.log(`[KeywordNetworkGraph] 检测到节点重合: ${this.draggedNode.label} 与 ${node.label}, 距离: ${distance.toFixed(2)}, 阈值: ${overlapThreshold.toFixed(2)}, 半径1: ${draggedNodeRadius}, 半径2: ${nodeRadius}`);
            break;
          }
        }
        
        // 如果检测到重合，弹出融合对话框
        if (targetNode) {
          // 🔥 立即清除节点高亮，避免节点被选中（在设置对话框之前）
          this.highlightedNode = null;
          // 🔥 标记刚刚结束拖拽，防止触发点击事件选中节点
          this.justEndedDrag = true;
          setTimeout(() => {
            this.justEndedDrag = false;
          }, 200); // 200ms后清除标志
          
          this.fusionSourceKeyword1 = this.draggedNode.label;
          this.fusionSourceKeyword2 = targetNode.label;
          this.fusionKeywordOptions = []; // 清空之前的选项
          this.selectedKeywordIndex = -1;
          this.editingKeywordIndex = -1;
          this.editingField = '';
          this.showFusionDialog = true;
          // 恢复被拖拽节点的位置（在用户确认融合前）
          if (this.dragStartPos) {
            this.draggedNode.x = this.dragStartPos.x;
            this.draggedNode.y = this.dragStartPos.y;
            this.draggedNode.fx = this.dragStartPos.x;
            this.draggedNode.fy = this.dragStartPos.y;
          }
          // 🔥 自动调用confirmFusion获取3个关键词选项
          this.$nextTick(() => {
            this.confirmFusion();
          });
          } else if (!this.quadrantPlaceMode) {
          // 没有重合，正常保存位置。象限模式里的坐标不能写进力导向存档。
          if (this.draggedNode.fx !== undefined && this.draggedNode.fy !== undefined) {
            // 🔥 确保位置精确（保留2位小数）
            const savedX = Math.round(this.draggedNode.fx * 100) / 100;
            const savedY = Math.round(this.draggedNode.fy * 100) / 100;
            
            this.savedPositions[this.draggedNode.label] = {
              x: savedX,
              y: savedY
            };
            
            // 🔥 立即保存到localStorage（长期保存）
            this.savePositions();
            console.log(`[KeywordNetworkGraph] 拖拽结束，保存节点'${this.draggedNode.label}'位置: (${savedX}, ${savedY})`);
          }
        }
      }
      
      // 🔥 只有真正拖拽了（移动距离超过3px）才标记，防止触发点击事件
      if (this.dragStartPos && this.draggedNode) {
        const currentX = this.draggedNode.fx !== undefined ? this.draggedNode.fx : (this.draggedNode.x !== undefined ? this.draggedNode.x : 0);
        const currentY = this.draggedNode.fy !== undefined ? this.draggedNode.fy : (this.draggedNode.y !== undefined ? this.draggedNode.y : 0);
        const dragDistance = Math.sqrt(
          Math.pow(currentX - this.dragStartPos.x, 2) + 
          Math.pow(currentY - this.dragStartPos.y, 2)
        );
        
        if (dragDistance > 3) {
          // 🔥 只有真正拖拽了才标记，防止触发点击事件
          this.justEndedDrag = true;
          setTimeout(() => {
            this.justEndedDrag = false;
          }, 100); // 100ms后清除标志
        }
      }
      
      // 🔥 清除拖拽开始位置
      this.dragStartPos = null;
      
      // 🔥 重置状态
      this.draggedNode = null;
      this.isDragging = false;
      this.dragStartTime = 0;
      
      // 🔥 移除事件监听
      window.removeEventListener('mousemove', this.onDrag);
      window.removeEventListener('mouseup', this.endDrag);
      
      // 🔥 不重新启动模拟，保持所有节点固定位置
    },
    
    graphNodeDimmed(node) {
      const focus = this.activeFocus;
      if (!focus || !node) return false;
      return !focus.nodes[node.label];
    },

    longitudeNodeBreathing(node) {
      if (!this.showLongitudeLinks || !this.hoveredLongitudeId || !node || !node.label) return false;
      const chain = this.longitudeChainMap[this.hoveredLongitudeId] || {};
      return !!chain[node.label];
    },

    longitudeBreathColor() {
      const id = this.hoveredLongitudeId;
      const link = (this.links || []).find((item) => item.linkType === 'longitude' && item.longitudeId === id);
      return (link && link.color) || '#c45c26';
    },

    graphLinkDimmed(link) {
      const focus = this.activeFocus;
      if (!focus || !link) return false;
      if (link.linkType === 'longitude') {
        if (focus.mode === 'longitude') return false;
        if (focus.mode === 'longitude-hover') return link.longitudeId !== this.hoveredLongitudeId;
      }
      if (focus.mode === 'longitude') return true;
      const a = link.source && link.source.label;
      const b = link.target && link.target.label;
      return !(focus.nodes[a] && focus.nodes[b]);
    },

    contourRingHot(ring) {
      if (!ring) return false;
      if (this.hoveredContourId && this.hoveredContourId === ring.id) return true;
      if (this.showLongitudeLinks && this.hoveredLongitudeId) {
        const chain = this.longitudeChainMap[this.hoveredLongitudeId] || {};
        return (ring.members || []).some((label) => chain[label]);
      }
      return false;
    },

    contourRingDim(ring) {
      if (!ring) return false;
      if (this.contourRingHot(ring)) return false;
      if (this.hoveredContourId) return true;
      if (this.showLongitudeLinks && this.hoveredLongitudeId) return true;
      if (this.showLongitudeLinks && this.showContourLinks) return true;
      return false;
    },

    clearGraphHover() {
      this.hoveredContourId = null;
      this.hoveredLongitudeId = null;
    },

    onNetworkMouseMove(event) {
      if (!this.showContourLinks && !this.showLongitudeLinks) {
        this.clearGraphHover();
        return;
      }
      const svg = this.$refs.networkSvg;
      if (!svg || !svg.createSVGPoint) return;
      const pt = svg.createSVGPoint();
      pt.x = event.clientX;
      pt.y = event.clientY;
      const ctm = svg.getScreenCTM();
      if (!ctm) return;
      const loc = pt.matrixTransform(ctm.inverse());
      let lonHit = null;
      if (this.showLongitudeLinks) {
        (this.links || []).some((link) => {
          if (link.linkType !== 'longitude' || !link.source || !link.target) return false;
          const dist = this.pointToLinkCurveDistance(loc.x, loc.y, link);
          if (dist < 16) {
            lonHit = link.longitudeId;
            return true;
          }
          return false;
        });
      }
      if (lonHit !== this.hoveredLongitudeId) this.hoveredLongitudeId = lonHit;
      if (lonHit) {
        if (this.hoveredContourId) this.hoveredContourId = null;
        return;
      }
      if (!this.showContourLinks) {
        if (this.hoveredContourId) this.hoveredContourId = null;
        return;
      }
      const paths = svg.querySelectorAll('path.contour-ring');
      let best = null;
      let bestArea = Infinity;
      paths.forEach((el) => {
        if (typeof el.isPointInFill !== 'function' || !el.isPointInFill(loc)) return;
        const box = el.getBBox();
        const area = (box.width || 0) * (box.height || 0);
        if (area < bestArea) {
          bestArea = area;
          best = el.getAttribute('data-contour-id');
        }
      });
      if (best !== this.hoveredContourId) this.hoveredContourId = best;
    },

    pointToLinkCurveDistance(px, py, link) {
      const s = link && link.source;
      const t = link && link.target;
      if (!s || !t || s.x == null || t.x == null) return Infinity;
      const x1 = s.x;
      const y1 = s.y;
      const x2 = t.x;
      const y2 = t.y;
      const dx = x2 - x1;
      const dy = y2 - y1;
      const len = Math.sqrt(dx * dx + dy * dy) || 1;
      const bend = (this.hashStringToUnit(`${s.label}|${t.label}`) - 0.5) * Math.min(36, len * 0.18);
      const mx = (x1 + x2) / 2 + (-dy / len) * bend;
      const my = (y1 + y2) / 2 + (dx / len) * bend;
      let best = Infinity;
      for (let i = 0; i <= 12; i += 1) {
        const u = i / 12;
        const o = 1 - u;
        const x = o * o * x1 + 2 * o * u * mx + u * u * x2;
        const y = o * o * y1 + 2 * o * u * my + u * u * y2;
        const d = Math.hypot(px - x, py - y);
        if (d < best) best = d;
      }
      return best;
    },

    closedContourPath(points) {
      const n = points.length;
      if (n < 3) return '';
      let d = `M ${points[0].x} ${points[0].y}`;
      for (let i = 0; i < n; i += 1) {
        const p0 = points[(i - 1 + n) % n];
        const p1 = points[i];
        const p2 = points[(i + 1) % n];
        const p3 = points[(i + 2) % n];
        const c1x = p1.x + (p2.x - p0.x) / 6;
        const c1y = p1.y + (p2.y - p0.y) / 6;
        const c2x = p2.x - (p3.x - p1.x) / 6;
        const c2y = p2.y - (p3.y - p1.y) / 6;
        d += ` C ${c1x} ${c1y}, ${c2x} ${c2y}, ${p2.x} ${p2.y}`;
      }
      return `${d} Z`;
    },

    toggleQuadrantPlaceMode() {
      if (!this.isV3Pipeline || !this.nodes || !this.nodes.length) return;
      if (this.quadrantPlaceMode) {
        const saved = this.loadQuadrantView();
        if (saved && saved.force && (!this.forceLayoutSnapshot || !Object.keys(this.forceLayoutSnapshot).length)) {
          this.forceLayoutSnapshot = saved.force;
        }
        this.clearQuadrantView();
        this.quadrantPlaceMode = false;
        this.persistQuadrantMode(false);
        this.quadrantFrame = null;
        this.restoreForceSnapshot();
        this.$forceUpdate();
        return;
      }
      this.captureForceSnapshot();
      this.quadrantPlaceMode = true;
      this.persistQuadrantMode(true);
      this.applyQuadrantPlacement();
    },

    captureForceSnapshot() {
      const snap = {};
      (this.nodes || []).forEach((node) => {
        if (!node || node.label == null || node.x == null || node.y == null) return;
        snap[node.label] = { x: node.x, y: node.y };
      });
      this.forceLayoutSnapshot = snap;
    },

    restoreForceSnapshot() {
      const snap = this.forceLayoutSnapshot || {};
      (this.nodes || []).forEach((node) => {
        const pos = snap[node.label];
        if (!pos) return;
        node.x = pos.x;
        node.y = pos.y;
        node.fx = pos.x;
        node.fy = pos.y;
      });
    },

    quadrantOfNode(node) {
      const q = String((node && node.quadrant) || this.getV3KeywordAttrs(node && node.label).quadrant || '').toUpperCase();
      return ['Q1', 'Q2', 'Q3', 'Q4'].includes(q) ? q : 'Q3';
    },

    /**
     * 四个象限各自做一次力导向，团落在靠外的一侧，靠轴线留出空档。
     * 跨象限的线不穿团，改沿轴线走。
     */
    applyQuadrantPlacement() {
      const snap = this.forceLayoutSnapshot || {};
      const nodes = (this.nodes || []).filter((node) => node && snap[node.label]);
      if (!nodes.length) return;
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      nodes.forEach((node) => {
        const pos = snap[node.label];
        minX = Math.min(minX, pos.x);
        minY = Math.min(minY, pos.y);
        maxX = Math.max(maxX, pos.x);
        maxY = Math.max(maxY, pos.y);
      });
      const pad = 86;
      const frameMinX = minX - pad;
      const frameMinY = minY - pad;
      const frameMaxX = Math.max(maxX + pad, frameMinX + 460);
      const frameMaxY = Math.max(maxY + pad, frameMinY + 380);
      const width = frameMaxX - frameMinX;
      const height = frameMaxY - frameMinY;
      const counts = { Q1: 0, Q2: 0, Q3: 0, Q4: 0 };
      nodes.forEach((node) => {
        counts[this.quadrantOfNode(node)] += 1;
      });
      const total = nodes.length || 1;
      const clampShare = (part) => Math.min(0.78, Math.max(0.22, part / total));
      const leftShare = clampShare(counts.Q2 + counts.Q3);
      const topShare = clampShare(counts.Q1 + counts.Q2);
      const originX = frameMinX + width * leftShare;
      const originY = frameMinY + height * topShare;
      this.quadrantFrame = {
        minX: frameMinX,
        minY: frameMinY,
        maxX: frameMaxX,
        maxY: frameMaxY,
        originX,
        originY,
      };
      const rectOf = {
        Q2: { x: frameMinX, y: frameMinY, w: originX - frameMinX, h: originY - frameMinY },
        Q1: { x: originX, y: frameMinY, w: frameMaxX - originX, h: originY - frameMinY },
        Q3: { x: frameMinX, y: originY, w: originX - frameMinX, h: frameMaxY - originY },
        Q4: { x: originX, y: originY, w: frameMaxX - originX, h: frameMaxY - originY },
      };
      const endNode = (end) => (end && typeof end === 'object' && end.label != null ? end : null);
      const contentOf = (qKey, rect) => {
        const gutter = Math.max(36, Math.min(78, Math.min(rect.w, rect.h) * 0.2));
        const outer = 18;
        let x = rect.x;
        let y = rect.y;
        let w = rect.w;
        let h = rect.h;
        if (qKey === 'Q1') {
          x += gutter; w -= gutter + outer; y += outer; h -= gutter + outer;
        } else if (qKey === 'Q2') {
          x += outer; w -= gutter + outer; y += outer; h -= gutter + outer;
        } else if (qKey === 'Q3') {
          x += outer; w -= gutter + outer; y += gutter; h -= gutter + outer;
        } else {
          x += gutter; w -= gutter + outer; y += gutter; h -= gutter + outer;
        }
        if (w < 64) { x = rect.x + 10; w = Math.max(64, rect.w - 20); }
        if (h < 64) { y = rect.y + 10; h = Math.max(64, rect.h - 20); }
        return { x, y, w, h };
      };
      const clampTo = (x, y, box) => ({
        x: Math.min(box.x + box.w, Math.max(box.x, x)),
        y: Math.min(box.y + box.h, Math.max(box.y, y)),
      });
      const byQuad = { Q1: [], Q2: [], Q3: [], Q4: [] };
      nodes.forEach((node) => {
        byQuad[this.quadrantOfNode(node)].push(node);
      });
      const indexByLabel = {};
      nodes.forEach((node) => {
        indexByLabel[node.label] = node;
      });
      const exits = {};
      Object.keys(byQuad).forEach((qKey) => {
        const list = byQuad[qKey];
        const territory = rectOf[qKey];
        const box = contentOf(qKey, territory);
        if (!list.length) return;
        const n = list.length;
        const cols = Math.max(1, Math.ceil(Math.sqrt(n * (box.w / Math.max(box.h, 1)))));
        const rows = Math.max(1, Math.ceil(n / cols));
        const ordered = list.slice().sort((a, b) => String(a.label).localeCompare(String(b.label), 'zh'));
        const state = ordered.map((node, index) => {
          const col = index % cols;
          const row = Math.floor(index / cols);
          return {
            node,
            x: box.x + ((col + 0.5) / cols) * box.w,
            y: box.y + ((row + 0.5) / rows) * box.h,
          };
        });
        const at = {};
        state.forEach((item, index) => {
          at[item.node.label] = index;
        });
        const pairs = [];
        (this.links || []).forEach((link) => {
          if (!link || link.linkType === 'contour' || link.linkType === 'longitude') return;
          const a = endNode(link.source);
          const b = endNode(link.target);
          if (!a || !b || a.label === b.label) return;
          if (!indexByLabel[a.label] || !indexByLabel[b.label]) return;
          if (this.quadrantOfNode(a) !== qKey || this.quadrantOfNode(b) !== qKey) return;
          const i = at[a.label];
          const j = at[b.label];
          if (i == null || j == null || i === j) return;
          pairs.push([i, j]);
        });
        const ideal = Math.max(58, Math.min(112, Math.sqrt((box.w * box.h) / n) * 0.78));
        const anchorX = box.x + box.w * (qKey === 'Q1' || qKey === 'Q4' ? 0.64 : 0.36);
        const anchorY = box.y + box.h * (qKey === 'Q1' || qKey === 'Q2' ? 0.36 : 0.64);
        const iterations = 170;
        for (let step = 0; step < iterations; step += 1) {
          const cool = 0.35 + 0.65 * (1 - step / iterations);
          const move = state.map(() => ({ x: 0, y: 0 }));
          for (let i = 0; i < state.length; i += 1) {
            for (let j = i + 1; j < state.length; j += 1) {
              let dx = state[j].x - state[i].x;
              let dy = state[j].y - state[i].y;
              let dist = Math.sqrt(dx * dx + dy * dy);
              if (dist < 0.8) {
                dx = (i + j) % 2 === 0 ? 1 : -1;
                dy = (i + j) % 2 === 0 ? 0.4 : -0.4;
                dist = Math.sqrt(dx * dx + dy * dy);
              }
              const reach = ideal * 1.55;
              if (dist >= reach) continue;
              const push = ((reach - dist) / reach) * 16 * cool;
              const ux = dx / dist;
              const uy = dy / dist;
              move[i].x -= ux * push;
              move[i].y -= uy * push;
              move[j].x += ux * push;
              move[j].y += uy * push;
            }
          }
          pairs.forEach(([i, j]) => {
            const dx = state[j].x - state[i].x;
            const dy = state[j].y - state[i].y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const pull = (dist - ideal) * 0.09 * cool;
            const ux = dx / dist;
            const uy = dy / dist;
            move[i].x += ux * pull;
            move[i].y += uy * pull;
            move[j].x -= ux * pull;
            move[j].y -= uy * pull;
          });
          state.forEach((item, index) => {
            move[index].x += (anchorX - item.x) * 0.045 * cool;
            move[index].y += (anchorY - item.y) * 0.045 * cool;
            const mx = move[index].x;
            const my = move[index].y;
            const mlen = Math.sqrt(mx * mx + my * my);
            const cap = 14;
            const scale = mlen > cap ? cap / mlen : 1;
            const next = clampTo(item.x + mx * scale, item.y + my * scale, box);
            item.x = next.x;
            item.y = next.y;
          });
        }
        const halfW = (node) => Math.min(40, Math.max((node.radius || 9) + 8, String(node.label || '').length * 4.4));
        const needYOf = (node) => (node.radius || 9) + (node.labelFontSize || 10) + 8;
        for (let pass = 0; pass < 10; pass += 1) {
          for (let i = 0; i < state.length; i += 1) {
            for (let j = i + 1; j < state.length; j += 1) {
              const a = state[i];
              const b = state[j];
              const dx = b.x - a.x;
              const dy = b.y - a.y;
              const needX = halfW(a.node) + halfW(b.node);
              const needY = needYOf(a.node) + (b.node.radius || 9);
              if (Math.abs(dx) >= needX || Math.abs(dy) >= needY) continue;
              const ux = Math.abs(dx) < 0.5 ? ((i + j) % 2 === 0 ? 1 : -1) : dx / Math.abs(dx);
              const uy = Math.abs(dy) < 0.5 ? 1 : dy / Math.abs(dy);
              const pushX = (needX - Math.abs(dx)) / 2;
              const pushY = (needY - Math.abs(dy)) / 2;
              const nextA = clampTo(a.x - ux * pushX, a.y - uy * pushY, box);
              const nextB = clampTo(b.x + ux * pushX, b.y + uy * pushY, box);
              a.x = nextA.x;
              a.y = nextA.y;
              b.x = nextB.x;
              b.y = nextB.y;
            }
          }
        }
        let bMinX = Infinity;
        let bMinY = Infinity;
        let bMaxX = -Infinity;
        let bMaxY = -Infinity;
        state.forEach((item) => {
          item.node.x = item.x;
          item.node.y = item.y;
          const pad = (item.node.radius || 9) + 4;
          bMinX = Math.min(bMinX, item.x - pad);
          bMinY = Math.min(bMinY, item.y - pad);
          bMaxX = Math.max(bMaxX, item.x + pad);
          bMaxY = Math.max(bMaxY, item.y + pad);
        });
        const corner = qKey === 'Q1'
          ? { x: originX + 12, y: originY - 12 }
          : qKey === 'Q2'
            ? { x: originX - 12, y: originY - 12 }
            : qKey === 'Q3'
              ? { x: originX - 12, y: originY + 12 }
              : { x: originX + 12, y: originY + 12 };
        exits[qKey] = {
          bbox: { minX: bMinX, minY: bMinY, maxX: bMaxX, maxY: bMaxY },
          corner,
        };
      });
      this.quadrantFrame = {
        minX: frameMinX,
        minY: frameMinY,
        maxX: frameMaxX,
        maxY: frameMaxY,
        originX,
        originY,
        exits,
      };
      nodes.forEach((node) => {
        node.fx = node.x;
        node.fy = node.y;
      });
      this.saveQuadrantView();
      this.$forceUpdate();
    },

    toggleAuxLinks(kind) {
      if (kind === 'contour') {
        this.showContourLinks = !this.showContourLinks;
        if (!this.showContourLinks) this.hoveredContourId = null;
      } else {
        this.showLongitudeLinks = !this.showLongitudeLinks;
        if (!this.showLongitudeLinks) this.hoveredLongitudeId = null;
      }
      const h = this.highlightedLink;
      if (!h) return;
      if (h.linkType === 'contour' && !this.showContourLinks) this.highlightedLink = null;
      if (h.linkType === 'longitude' && !this.showLongitudeLinks) this.highlightedLink = null;
    },

    resetLayout() {
      this.quadrantPlaceMode = false;
      this.persistQuadrantMode(false);
      this.clearQuadrantView();
      this.quadrantFrame = null;
      this.forceLayoutSnapshot = null;
      // 清除当前档位保存的位置
      this.savedPositions = {};
      localStorage.removeItem(this.getPositionsStorageKeyForLimit(this.getActiveNodeLimit()));
      
      // 象限排法留下的画布范围会把力导向结果缩得很小，重置时清掉
      this.baseViewBoxBounds = null;
      
      // 重置所有节点的固定位置
      this.nodes.forEach(node => {
        node.fx = undefined;
        node.fy = undefined;
      });
      
      // 重新初始化布局
      this.initializeNetwork();
    },
    
    quadrantModeStorageKey() {
      return `keywordNetworkQuadrantMode_${this.getStorageKey()}`;
    },

    persistQuadrantMode(on) {
      const keys = [this.quadrantModeStorageKey(), 'keywordNetworkQuadrantMode'];
      try {
        keys.forEach((key) => {
          if (on) localStorage.setItem(key, '1');
          else localStorage.removeItem(key);
        });
      } catch (e) { /* 记不住开关时，重新打开就回到力导向 */ }
    },

    quadrantModeEnabled() {
      if (this.quadrantPlaceMode) return true;
      if (readQuadrantPicture()) return true;
      try {
        if (localStorage.getItem(this.quadrantModeStorageKey()) === '1') return true;
        if (localStorage.getItem('keywordNetworkQuadrantMode') === '1') return true;
        if (localStorage.getItem(this.quadrantViewStorageKey())) return true;
      } catch (e) {
        return false;
      }
      return false;
    },

    quadrantViewStorageKey() {
      return `keywordNetworkQuadrantView_${this.getStorageKey()}_n${this.getActiveNodeLimit()}`;
    },

    loadQuadrantView() {
      return readQuadrantPicture();
    },

    saveQuadrantView() {
      if (!this.quadrantFrame) return;
      const positions = {};
      (this.nodes || []).forEach((node) => {
        if (!node || node.label == null || node.x == null || node.y == null) return;
        positions[node.label] = {
          x: Math.round(node.x * 100) / 100,
          y: Math.round(node.y * 100) / 100,
        };
      });
      if (!Object.keys(positions).length) return;
      const picture = {
        positions,
        frame: this.quadrantFrame,
        force: this.forceLayoutSnapshot || null,
      };
      writeQuadrantPicture(picture);
      try {
        localStorage.setItem(this.quadrantViewStorageKey(), JSON.stringify(picture));
      } catch (e) { /* 分档那份写不进去不影响，固定键已经写过 */ }
      this.persistQuadrantMode(true);
    },

    clearQuadrantView() {
      clearQuadrantPicture();
      this._quadrantPosForCalc = null;
    },

    restoreSavedQuadrantView() {
      const data = this.loadQuadrantView();
      if (!data) return false;
      let hit = 0;
      (this.nodes || []).forEach((node) => {
        const pos = data.positions[node.label];
        if (!pos || pos.x == null || pos.y == null) return;
        node.x = pos.x;
        node.y = pos.y;
        node.fx = pos.x;
        node.fy = pos.y;
        hit += 1;
      });
      if (!hit) return false;
      this.quadrantFrame = data.frame;
      if (data.force) this.forceLayoutSnapshot = data.force;
      this.quadrantPlaceMode = true;
      this.$forceUpdate();
      return true;
    },

    showQuadrantNow() {
      this.quadrantPlaceMode = true;
      if (this.restoreSavedQuadrantView()) {
        this.updateContainerWidth();
        return;
      }
      if (!this.forceLayoutSnapshot || !Object.keys(this.forceLayoutSnapshot).length) {
        const snap = {};
        (this.nodes || []).forEach((node) => {
          if (!node || node.label == null) return;
          const saved = this.savedPositions && this.savedPositions[node.label];
          const x = saved && saved.x != null ? saved.x : node.x;
          const y = saved && saved.y != null ? saved.y : node.y;
          if (x == null || y == null) return;
          snap[node.label] = { x, y };
        });
        if (Object.keys(snap).length) this.forceLayoutSnapshot = snap;
      }
      this.applyQuadrantPlacement();
      this.updateContainerWidth();
    },

    savePositions(limitOverride, opts) {
      const keepForce = !!(opts && opts.keepForceLayout);
      if (this.quadrantPlaceMode && !keepForce) return;
      const snap = keepForce && this.quadrantPlaceMode ? this.forceLayoutSnapshot : null;
      if (this.quadrantPlaceMode && keepForce && (!snap || !Object.keys(snap).length)) return;
      // 象限模式里只允许写入力导向快照，避免把象限坐标覆盖成平时布局
      const positions = {};
      if (snap) {
        Object.keys(snap).forEach((label) => {
          const pos = snap[label];
          if (!pos || pos.x == null || pos.y == null) return;
          positions[label] = {
            x: Math.round(pos.x * 100) / 100,
            y: Math.round(pos.y * 100) / 100
          };
        });
      } else {
        this.nodes.forEach(node => {
          const posX = node.fx !== undefined ? node.fx : (node.x !== undefined ? node.x : null);
          const posY = node.fy !== undefined ? node.fy : (node.y !== undefined ? node.y : null);
          if (posX !== null && posY !== null) {
            positions[node.label] = {
              x: Math.round(posX * 100) / 100,
              y: Math.round(posY * 100) / 100
            };
          }
        });
      }

      const limit = limitOverride != null ? limitOverride : this.getActiveNodeLimit();
      const storageKey = this.getPositionsStorageKeyForLimit(limit);
      if (Object.keys(positions).length > 0) {
        localStorage.setItem(storageKey, JSON.stringify(positions));
        console.log(`[KeywordNetworkGraph] 已保存${Object.keys(positions).length}个节点位置到: ${storageKey}`);
      } else {
        localStorage.removeItem(storageKey);
      }
    },
    
    loadSavedPositions(limitOverride) {
      // 🔥 从 localStorage 加载指定档位的节点位置
      const limit = limitOverride != null ? limitOverride : this.getActiveNodeLimit();
      try {
        const storageKey = this.getPositionsStorageKeyForLimit(limit);
        let saved = localStorage.getItem(storageKey);
        if (!saved) {
          const legacyKey = `keywordNetworkPositions_${this.getStorageKey()}`;
          const legacy = localStorage.getItem(legacyKey);
          if (legacy && limit === DEFAULT_NODE_DISPLAY_LIMIT) {
            saved = legacy;
            localStorage.setItem(storageKey, legacy);
          }
        }
        if (saved) {
          this.savedPositions = JSON.parse(saved);
          console.log(`[KeywordNetworkGraph] 已加载${Object.keys(this.savedPositions).length}个节点位置从: ${storageKey}`);
        } else {
          this.savedPositions = {};
        }
      } catch (e) {
        console.warn('[KeywordNetworkGraph] 加载保存的节点位置失败:', e);
        this.savedPositions = {};
      }
    },
    
    restorePositions(shouldFix = true) {
      if (this.quadrantPlaceMode || readQuadrantPicture()) {
        this.quadrantPlaceMode = true;
        this.restoreSavedQuadrantView();
        return;
      }
      // 🔥 恢复保存的位置到节点（在初始化网络图后调用）
      // shouldFix: 是否立即固定节点位置，false表示只恢复初始位置，让布局先运行
      let restoredCount = 0;
      this.nodes.forEach(node => {
        const savedPos = this.savedPositions[node.label];
        if (savedPos && savedPos.x !== undefined && savedPos.y !== undefined) {
          // 🔥 确保位置有效，使用精确的数值
          const restoredX = Math.round(savedPos.x * 100) / 100;
          const restoredY = Math.round(savedPos.y * 100) / 100;
          
          node.x = restoredX;
          node.y = restoredY;
          if (shouldFix) {
            node.fx = restoredX; // 🔥 固定位置，防止力导向布局移动
            node.fy = restoredY;
          }
          restoredCount++;
        }
      });
      
      console.log(`[KeywordNetworkGraph] 已恢复${restoredCount}个节点的位置${shouldFix ? '并固定' : ''}`);
      
      // 🔥 恢复位置后立即保存一次，确保数据同步
      if (shouldFix) {
        this.$nextTick(() => {
          this.savePositions();
        });
      }
    },
    
    // 🔥 增量更新节点：只添加新节点，删除消失的节点，保持已有节点位置不变
    incrementalUpdateNodes(newKeywords, oldKeywords) {
      // 如果是首次加载或旧关键词为空，执行完整初始化
      if (!oldKeywords || oldKeywords.length === 0 || !this.nodes || this.nodes.length === 0) {
        this.loadSavedPositions();
        this.$nextTick(() => {
          this.initializeNetwork();
        });
        return;
      }
      
      // 加载保存的位置
      this.loadSavedPositions();
      
      // 获取要显示的关键词（智能筛选）
      const newKeywordsToShow = this.getDisplayKeywords(newKeywords || [], this.getActiveNodeLimit());
      const oldKeywordsToShow = this.getDisplayKeywords(oldKeywords || [], this.getActiveNodeLimit());
      
      // 找出新增和删除的关键词
      const newKeywordsSet = new Set(newKeywordsToShow);
      const oldKeywordsSet = new Set(oldKeywordsToShow);
      const addedKeywords = newKeywordsToShow.filter(k => !oldKeywordsSet.has(k));
      const removedKeywords = oldKeywordsToShow.filter(k => !newKeywordsSet.has(k));
      
      // 如果没有变化，直接返回
      if (addedKeywords.length === 0 && removedKeywords.length === 0) {
        return;
      }
      
      // 删除消失的节点（不影响其他节点）
      if (removedKeywords.length > 0) {
        this.nodes = this.nodes.filter(node => !removedKeywords.includes(node.label));
        // 删除对应的保存位置
        removedKeywords.forEach(keyword => {
          delete this.savedPositions[keyword];
        });
        this.savePositions();
      }
      
      // 添加新节点（找到空闲位置）
      if (addedKeywords.length > 0) {
        // 为新关键词创建节点
        const existingNodeLabels = new Set(this.nodes.map(n => n.label));
        const newNodes = addedKeywords
          .filter(k => !existingNodeLabels.has(k))
          .map((keyword, index) => {
            // 使用calculateNodes的逻辑创建单个节点
            const cardCount = this.effectiveCards.filter(card => {
              if (!card.keyWords) return false;
              const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
              return cardKeywords.includes(keyword);
            }).length;
            
            const keywordDMTData = this.keywordFourColorDMTData || {};
            const keywordData = keywordDMTData[keyword] || {};
            const fourColorType = keywordData.four_color_type || '';
            const dmtLevel = keywordData.dmt_level || '';
            let knowledgeType = keywordData.knowledge_type || '';
            if (!knowledgeType && (this.tribalKeywords || []).includes(keyword)) {
              knowledgeType = 'trib';
            }
            if (!knowledgeType) knowledgeType = 'trad';

            const dmtRadiusMap = { D: 7, M: 11, T: 15 };
            const finalRadius = Math.max(dmtRadiusMap[dmtLevel] || 9, 5);
            const isSelected = this.selectedKeywords.includes(keyword);
            const colors = this.getNodeColors(keyword, cardCount, 1, Math.max(cardCount, 1), isSelected);
            
            // 查找空闲位置
            const emptyPosition = this.findEmptyPosition(finalRadius);
            
            // 检查是否为新关键词（本次使用中新生成的）
            let initialKeywordsSet = new Set();
            try {
              if (this.initialKeywords) {
                if (Array.isArray(this.initialKeywords)) {
                  initialKeywordsSet = new Set(this.initialKeywords);
                } else if (this.initialKeywords.size !== undefined) {
                  initialKeywordsSet = new Set(Array.from(this.initialKeywords));
                }
              }
            } catch (e) {
              initialKeywordsSet = new Set();
            }
            const isNew = initialKeywordsSet.size > 0 ? !initialKeywordsSet.has(keyword) : false;
            
            return {
              id: this.nodes.length + index,
              label: keyword,
              cardCount: cardCount,
              radius: finalRadius,
              fontSize: 10,
              countFontSize: Math.max(8, Math.min(finalRadius * 0.6, 12)),
              countTextColor: '#ffffff',
              x: emptyPosition.x,
              y: emptyPosition.y,
              fx: emptyPosition.x, // 立即固定位置
              fy: emptyPosition.y,
              color: colors.color,
              dmtLevel: dmtLevel,
              knowledgeType: knowledgeType,
              stroke: colors.stroke,
              strokeWidth: colors.strokeWidth,
              textColor: '#333',
              minCount: 1,
              maxCount: Math.max(cardCount, 1),
              isNew: !!isNew,
              isTribal: !!(this.tribalKeywords || []).includes(keyword)
            };
          });
        
        // 添加新节点到现有节点列表
        this.nodes = this.nodes.concat(newNodes);
        
        // 保存新节点的位置
        newNodes.forEach(node => {
          this.savedPositions[node.label] = { x: node.x, y: node.y };
        });
        this.savePositions();
      }
      
      // 重新计算连接（因为节点变化了）
      const allKeywordsToShow = this.nodes.map(n => n.label);
      this.links = this.calculateLinks(allKeywordsToShow);
      
      // 更新视图
      this.$nextTick(() => {
        this.updateLinkPositions();
        this.updateNodePositions();
      });
    },
    
    // 🔥 查找空闲位置（不与其他节点重叠）
    findEmptyPosition(radius, maxAttempts = 100) {
      const padding = radius * 2 + 20; // 节点之间的最小间距
      const margin = radius + 20; // 距离SVG边缘的最小距离
      
      // 获取已有节点的位置和半径
      const occupiedAreas = this.nodes.map(node => ({
        x: node.x || node.fx || this.svgWidth / 2,
        y: node.y || node.fy || this.svgHeight / 2,
        radius: node.radius || 10
      }));
      
      // 尝试找到不重叠的位置
      for (let attempt = 0; attempt < maxAttempts; attempt++) {
        // 使用螺旋搜索模式：从中心向外螺旋搜索
        const angle = attempt * 0.5; // 螺旋角度
        const distance = Math.min(50 + attempt * 3, Math.min(this.svgWidth, this.svgHeight) / 2 - margin);
        const x = this.svgWidth / 2 + Math.cos(angle) * distance;
        const y = this.svgHeight / 2 + Math.sin(angle) * distance;
        
        // 检查是否在SVG范围内
        if (x < margin || x > this.svgWidth - margin || 
            y < margin || y > this.svgHeight - margin) {
          continue;
        }
        
        // 检查是否与其他节点重叠
        const overlaps = occupiedAreas.some(area => {
          const dx = x - area.x;
          const dy = y - area.y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          return distance < (radius + area.radius + padding);
        });
        
        if (!overlaps) {
          return { x, y };
        }
      }
      
      // 如果找不到空闲位置，返回一个随机位置（至少不重叠）
      const fallbackX = margin + Math.random() * (this.svgWidth - 2 * margin);
      const fallbackY = margin + Math.random() * (this.svgHeight - 2 * margin);
      return { x: fallbackX, y: fallbackY };
    },
    
    getStorageKey() {
      // 🔥 生成存储键（基于本子名称，确保每个本子的位置独立保存）
      const userId = localStorage.getItem('userId') || 'anonymous';
      const realName = localStorage.getItem('realName') || '';
      
      // 从userId中提取bookName（本子名称）
      let bookName = 'default';
      if (userId && userId.includes('_') && realName) {
        bookName = userId.substring(realName.length + 1) || 'default';
      }
      
      return `keywordPositions_${bookName}`;
    },
    
    handleResize() {
      // 更新容器宽度
      this.updateContainerWidth();
      
      // 调整SVG大小
      if (this.$refs.networkWrapper) {
        const rect = this.$refs.networkWrapper.getBoundingClientRect();
        this.svgWidth = Math.max(600, rect.width - 20);
        this.svgHeight = Math.max(400, rect.height - 20);
        
        // 重新启动模拟 (D3 v3 使用 size 和 start)
        if (this.simulation) {
          this.simulation.size([this.svgWidth, this.svgHeight]);
          this.simulation.resume();
        }
      }
    },
    
    updateContainerWidth() {
      // 更新容器宽度，用于计算容器高度
      this.$nextTick(() => {
        if (this.$refs.networkContainer) {
          const rect = this.$refs.networkContainer.getBoundingClientRect();
          if (rect.width > 0) {
            this.containerWidth = rect.width;
          }
        }
      });
    },
    
    getNodeBounds() {
      // 获取所有节点的边界范围
      if (!this.nodes || this.nodes.length === 0) {
        return { minX: 0, minY: 0, maxX: 0, maxY: 0 };
      }
      
      let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
      
      this.nodes.forEach(node => {
        const x = node.fx !== undefined ? node.fx : (node.x || 0);
        const y = node.fy !== undefined ? node.fy : (node.y || 0);
        const radius = node.radius || 5; // 使用新的最小半径
        const fontSize = node.fontSize || 10; // 获取字体大小
        
        // 节点边界（包括半径）
        minX = Math.min(minX, x - radius);
        minY = Math.min(minY, y - radius);
        maxX = Math.max(maxX, x + radius);
        maxY = Math.max(maxY, y + radius);
        
        // 考虑标签高度（标签在节点下方，位置为 radius + 10）
        // 标签的y位置是 y + radius + 10（标签基线），文本高度约为 fontSize，再加上一些间距
        const labelY = y + radius + 10; // 标签基线位置
        const labelHeight = fontSize * 1.8; // 标签高度（保守估计，包括行高和间距）
        maxY = Math.max(maxY, labelY + labelHeight); // 标签底部位置
      });
      
      return { minX, minY, maxX, maxY };
    },

    /** 把当前网络图画成高清画布（完整 viewBox，3×） */
    async _rasterizeNetworkSvg() {
      const svg = this.$refs.networkSvg;
      if (!svg) throw new Error('找不到网络图');
      const vbRaw = (svg.getAttribute('viewBox') || this.computedViewBox || '0 0 800 600').trim();
      const parts = vbRaw.split(/\s+/).map(Number);
      const minX = Number.isFinite(parts[0]) ? parts[0] : 0;
      const minY = Number.isFinite(parts[1]) ? parts[1] : 0;
      const vbW = Math.max(1, Number.isFinite(parts[2]) ? parts[2] : 800);
      const vbH = Math.max(1, Number.isFinite(parts[3]) ? parts[3] : 600);
      const scale = Math.min(3, 8192 / vbW, 8192 / vbH);
      const clone = svg.cloneNode(true);
      clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
      clone.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
      clone.setAttribute('width', String(vbW));
      clone.setAttribute('height', String(vbH));
      clone.setAttribute('viewBox', `${minX} ${minY} ${vbW} ${vbH}`);
      const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      bg.setAttribute('x', String(minX));
      bg.setAttribute('y', String(minY));
      bg.setAttribute('width', String(vbW));
      bg.setAttribute('height', String(vbH));
      bg.setAttribute('fill', '#fafafa');
      clone.insertBefore(bg, clone.firstChild);
      let svgStr = new XMLSerializer().serializeToString(clone);
      if (!svgStr.includes('xmlns=')) {
        svgStr = svgStr.replace(/<svg\b/, '<svg xmlns="http://www.w3.org/2000/svg"');
      }
      const blob = new Blob([svgStr], { type: 'image/svg+xml;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      try {
        const img = await new Promise((resolve, reject) => {
          const image = new Image();
          image.onload = () => resolve(image);
          image.onerror = (e) => reject(e || new Error('SVG 转图片失败'));
          image.src = url;
        });
        const canvas = document.createElement('canvas');
        canvas.width = Math.ceil(vbW * scale);
        canvas.height = Math.ceil(vbH * scale);
        const ctx = canvas.getContext('2d');
        if (!ctx) throw new Error('无法创建画布');
        ctx.fillStyle = '#fafafa';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        return canvas;
      } finally {
        URL.revokeObjectURL(url);
      }
    },

    _unlockBottomPanel(panel) {
      if (!panel) return;
      panel.style.maxHeight = 'none';
      panel.style.overflow = 'visible';
      panel.style.height = 'auto';
    },

    async _captureVisibleSheet() {
      const el = this.$refs.networkViewWrapper;
      if (!el) throw new Error('找不到要截的区域');
      const panel = el.querySelector('.v3-bottom-panel');
      const prevPanel = panel
        ? {
            maxHeight: panel.style.maxHeight,
            overflow: panel.style.overflow,
            height: panel.style.height,
          }
        : null;
      this._unlockBottomPanel(panel);
      await this.$nextTick();
      await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
      const liveSvg = el.querySelector('.network-svg');
      const box = liveSvg ? liveSvg.getBoundingClientRect() : null;
      const rect = el.getBoundingClientRect();
      const fullHeight = Math.ceil(Math.max(el.scrollHeight, rect.height));
      const windowHeight = Math.ceil(rect.top + window.pageYOffset + fullHeight + 48);
      try {
        return await html2canvas(el, {
          scale: 2,
          backgroundColor: '#ffffff',
          useCORS: true,
          logging: false,
          foreignObjectRendering: false,
          height: fullHeight,
          windowHeight,
          onclone(doc, cloned) {
            const root = cloned || doc.querySelector('.network-view-wrapper');
            const clonedPanel = root && root.querySelector
              ? root.querySelector('.v3-bottom-panel')
              : doc.querySelector('.v3-bottom-panel');
            if (clonedPanel) {
              clonedPanel.style.maxHeight = 'none';
              clonedPanel.style.overflow = 'visible';
              clonedPanel.style.height = 'auto';
            }
            const svg = root && root.querySelector
              ? root.querySelector('.network-svg')
              : doc.querySelector('.network-svg');
            if (!svg || !box || box.width < 2 || box.height < 2) return;
            const w = String(Math.round(box.width));
            const h = String(Math.round(box.height));
            svg.setAttribute('width', w);
            svg.setAttribute('height', h);
            svg.style.width = `${w}px`;
            svg.style.height = `${h}px`;
          },
        });
      } finally {
        if (panel && prevPanel) {
          panel.style.maxHeight = prevPanel.maxHeight;
          panel.style.overflow = prevPanel.overflow;
          panel.style.height = prevPanel.height;
        }
      }
    },

    _downloadCanvas(canvas) {
      const a = document.createElement('a');
      a.href = canvas.toDataURL('image/png');
      a.download = '语义关键词空间.png';
      document.body.appendChild(a);
      a.click();
      a.remove();
    },

    async _deliverCanvas(canvas, label) {
      const pngBlob = await new Promise((resolve, reject) => {
        canvas.toBlob((b) => {
          if (b) resolve(b);
          else reject(new Error('PNG 生成失败'));
        }, 'image/png');
      });
      try {
        if (!navigator.clipboard || typeof ClipboardItem === 'undefined') {
          throw new Error('clipboard-unavailable');
        }
        await navigator.clipboard.write([
          new ClipboardItem({ 'image/png': pngBlob }),
        ]);
        this.$message?.success?.(`已复制${label}到剪贴板（${canvas.width}×${canvas.height}），可直接粘贴`);
      } catch (err) {
        console.warn('[KeywordNetworkGraph] 剪贴板未写入，改为下载', err);
        this._downloadCanvas(canvas);
        this.$message?.success?.(`图已生成。剪贴板没有接住，已下载到本地（${canvas.width}×${canvas.height}）`);
      }
    },

    /** 复制整图高清 PNG。withSurroundings 为真时带上上下左右说明。 */
    async exportFullNetworkPng(withSurroundings = false) {
      if (this.exportingNetworkPng) return;
      const svg = this.$refs.networkSvg;
      if (!svg || this.viewMode !== 'network') {
        this.$message?.warning?.('请先切换到网络图视图再复制');
        return;
      }
      this.showExportGraphDialog = false;
      this.exportingNetworkPng = true;
      try {
        await this.$nextTick();
        if (withSurroundings) {
          const sheet = await this._captureVisibleSheet();
          await this._deliverCanvas(sheet, '带上下左右信息的完整大图');
          return;
        }
        const graphCanvas = await this._rasterizeNetworkSvg();
        await this._deliverCanvas(graphCanvas, '网络图');
      } catch (e) {
        console.error('[KeywordNetworkGraph] 截图失败:', e);
        this.$message?.error?.(`截图没有完成：${(e && e.message) || '请再试一次'}`);
      } finally {
        this.exportingNetworkPng = false;
      }
    },
  }
}
</script>

<style scoped>
.keyword-network-container {
  width: 100%;
  position: relative;
}

.network-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: nowrap;
}

.legend-container-inline {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 8px;
  font-size: 11px;
  color: #666;
  flex: 1;
  min-width: 0;
}

.legend-main {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  min-width: 0;
}

.legend-item-today-new {
  margin-left: auto;
  flex-shrink: 0;
}

.legend-today-new-circle {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px dashed #333;
  border-radius: 50%;
  box-shadow: 0 0 6px 2px rgba(255, 140, 0, 0.55);
  vertical-align: middle;
}

.node-count-btn {
  padding: 3px 7px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  min-width: 34px;
  text-align: center;
  transition: all 0.2s;
}

.node-count-btn:hover {
  background: #f0f0f0;
  border-color: #999;
}

.node-count-btn.active {
  background: #efe8f8;
  border-color: #6f559f;
  color: #3f3478;
}

.keyword-pick-strategy-btn {
  margin-left: 3px;
  min-width: 36px;
}

.export-full-graph-btn {
  padding: 3px 7px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  min-width: 34px;
  text-align: center;
  transition: all 0.2s;
  margin-left: 3px;
  line-height: 1;
}

.export-full-graph-btn:hover:not(:disabled) {
  background: #eef6ff;
  border-color: #409eff;
  color: #409eff;
}

.export-full-graph-btn:disabled {
  opacity: 0.55;
  cursor: wait;
}

.keyword-pick-strategy-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.keyword-pick-option-btn {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 12px !important;
  white-space: normal !important;
  line-height: 1.4;
}

.keyword-pick-option-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.keyword-pick-option-desc {
  font-size: 12px;
  color: #666;
  font-weight: 400;
}

.node-count-dialog {
  max-width: 420px;
}

.view-toggle-btn,
.reset-layout-btn {
  padding: 3px 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.view-toggle-btn:hover,
.reset-layout-btn:hover {
  background: #f0f0f0;
  border-color: #999;
}

.filter-strategy-btn {
  padding: 3px 6px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: white;
  cursor: pointer;
  font-size: 14px;
  font-weight: bold;
  transition: all 0.2s;
  margin-left: 3px;
  min-width: 24px;
  text-align: center;
}

.filter-strategy-btn:hover {
  background: #f0f0f0;
  border-color: #999;
}

.filter-strategy-btn.active {
  background: #6f559f;
  color: white;
  border-color: #6f559f;
}

.filter-strategy-btn.active:hover {
  background: #493d8b;
  border-color: #493d8b;
}

/* 连接线标记样式 */
.link-label-bg {
  pointer-events: none;
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.2));
}

.link-label-text {
  pointer-events: none;
}

/* 图例说明样式（保留用于其他地方） */
.legend-container {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0 6px 0;
  font-size: 11px;
  color: #666;
  flex-wrap: wrap;
  border-top: 1px solid #eee;
  margin-top: 4px;
  padding-top: 6px;
}

.axis-edge-text {
  paint-order: stroke fill;
  stroke: #ffffff;
  stroke-width: 4px;
  stroke-linejoin: round;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 3px;
  white-space: nowrap;
}

.legend-color-text {
  font-size: 10px;
  color: #555;
  margin-right: 4px;
}

.legend-label {
  font-weight: 500;
  color: #333;
  margin-right: 2px;
}

.legend-color {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  color: white;
  font-size: 8px;
  font-weight: bold;
  text-align: center;
  line-height: 14px;
  border: 1px solid rgba(0, 0, 0, 0.15);
}

.legend-dmt-svg {
  vertical-align: middle;
  margin: 0 2px;
}

.legend-new-node {
  vertical-align: middle;
  margin: 0 2px;
}

.tags-scroll-container {
  max-height: 200px;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 5px 0;
}

.tag-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px;
  background-color: #6f559f;
  color: white;
  font-size: 14px;
  cursor: pointer;
  outline: none;
  transition: background-color 0.3s ease;
  margin: 2px;
}

.tag-btn:hover {
  background-color: #493d8b;
}

.tag-btn.selected {
  background-color: #1f1652;
}

.network-view-container {
  position: relative;
  width: 100%;
  height: 550px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  overflow: hidden; /* 保持hidden，防止内容溢出 */
  background: #fafafa;
  cursor: default;
}

.network-canvas-wrapper {
  width: 100%;
  height: 100%;
  overflow: hidden; /* 保持hidden，viewBox会自动适应 */
}

.network-svg {
  display: block;
  width: 100%;
  height: 100%;
  /* 使用viewBox自动适应容器大小，确保所有节点都在可见区域内 */
}

.link-hit-area {
  cursor: pointer;
  pointer-events: stroke;
}

.link-line {
  cursor: pointer;
  transition: opacity 0.2s;
}

.link-line:hover {
  opacity: 1 !important;
  /* 不再强制统一线宽，保留强/强中/普通的粗中细区分 */
}

.node-group {
  cursor: pointer;
  /* 移除所有transition，避免抖动 */
}

.node-circle {
  transition: fill 0.2s, stroke-width 0.2s;
  /* 只保留颜色过渡，不改变位置 */
}

/* 🔥 移除选中节点的固定颜色，使用节点本身的颜色（通过:fill和:stroke属性动态设置） */
.node-group.selected .node-circle {
  /* 不再强制设置fill和stroke，使用节点动态计算的color和stroke */
  stroke-width: 3.5 !important;
}

.node-group.highlighted .node-circle {
  stroke-width: 4;
  filter: drop-shadow(0 0 4px rgba(111, 85, 159, 0.6));
}

.node-group.longitude-breath .node-circle {
  transform-box: fill-box;
  transform-origin: center;
  animation: longitude-node-breath 1.5s ease-in-out infinite;
}

.longitude-breath-halo {
  transform-box: fill-box;
  transform-origin: center;
  animation: longitude-halo-breath 1.5s ease-in-out infinite;
}

@keyframes longitude-node-breath {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.14); }
}

@keyframes longitude-halo-breath {
  0%, 100% { opacity: 0.15; transform: scale(0.82); }
  50% { opacity: 0.95; transform: scale(1.42); }
}

.node-count-text {
  pointer-events: none;
  user-select: none;
  font-weight: bold;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.node-label {
  pointer-events: none;
  user-select: none;
  font-weight: 500;
}

/* 🔥 新关键词套圈样式 */
.new-keyword-ring {
  animation: pulse-ring 2s ease-in-out infinite;
}

@keyframes pulse-ring {
  0%, 100% {
    opacity: 0.8;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.05);
  }
}

/* 🔥 融合关系tooltip样式 */
.fusion-link-marker {
  cursor: pointer;
}

.fusion-link-tooltip {
  position: fixed;
  background: rgba(255, 255, 255, 0.98);
  border: 2px solid #ff6b6b;
  border-radius: 6px;
  padding: 8px 12px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-size: 12px;
  line-height: 1.5;
  pointer-events: none;
  z-index: 10000;
}

.fusion-link-tooltip-title {
  font-weight: bold;
  color: #ff6b6b;
  margin-bottom: 6px;
  font-size: 13px;
}

.fusion-link-tooltip-content {
  color: #333;
}

.fusion-link-tooltip-content div {
  margin-bottom: 4px;
}

.fusion-link-tooltip-content strong {
  color: #666;
  font-weight: 600;
}

/* 🔥 新节点小箭头样式 */
.new-node-arrow {
  /* animation: arrow-pulse 2s ease-in-out infinite; */
  display: inline-block;
}

@keyframes arrow-pulse {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.05);
  }
}

/* 🔥 关键词编辑输入框包装器样式 */
.keyword-edit-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.95);
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  z-index: 1000;
}

.keyword-edit-input {
  border: 2px solid #6f559f;
  border-radius: 4px;
  padding: 4px 8px;
  background: white;
  color: #333;
  font-weight: 500;
  text-align: center;
  outline: none;
  width: calc(100% - 4px);
  height: calc(100% - 4px);
  box-shadow: 0 2px 8px rgba(111, 85, 159, 0.3);
  box-sizing: border-box;
}

.keyword-edit-input:focus {
  border-color: #493d8b;
  box-shadow: 0 2px 12px rgba(111, 85, 159, 0.5);
}

/* 🔥 右键菜单样式 */
.context-menu {
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 180px;
  padding: 4px 0;
  z-index: 10000;
}

.context-menu-title {
  padding: 6px 16px 4px;
  font-size: 12px;
  color: #888;
  border-bottom: 1px solid #eee;
  margin-bottom: 2px;
}

.context-menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 14px;
  color: #333;
  transition: background-color 0.2s;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.context-menu-item:hover {
  background-color: #f0f0f0;
}

.context-menu-item.active {
  background-color: #f3effa;
  color: #493d8b;
  font-weight: 600;
}

.context-menu-item span {
  display: inline-block;
}

.context-menu-check {
  color: #493d8b;
  font-weight: 700;
  margin-left: 12px;
}

.link-strength-menu {
  min-width: 140px;
}

/* 🔥 自定义选择对话框样式 */
.color-dmt-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20000;
}

.color-dmt-dialog {
  background: white;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  min-width: 320px;
  max-width: 500px;
  padding: 0;
  overflow: hidden;
}

.dialog-header {
  background: linear-gradient(135deg, #6f559f 0%, #493d8b 100%);
  color: white;
  padding: 16px 20px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dialog-header h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.dialog-close {
  background: none;
  border: none;
  color: white;
  font-size: 24px;
  cursor: pointer;
  padding: 0;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: background-color 0.2s;
}

.dialog-close:hover {
  background: rgba(255, 255, 255, 0.2);
}

.dialog-content {
  padding: 20px;
}

/* 🔥 融合关键词对话框特殊样式 */
.fusion-dialog {
  min-width: 900px;
  display: flex;
  flex-direction: column;
}

.fusion-dialog .dialog-content {
  overflow: hidden !important;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 🔥 关键词选项卡片样式 */
.keyword-option-card {
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
  transition: all 0.3s ease;
  display: flex;
  flex-direction: column;
  min-height: 200px;
  max-width: 100%;
  box-sizing: border-box;
  overflow: hidden;
}

.keyword-option-card:hover {
  border-color: #9d8cc7;
  background: #f5f2fa;
  box-shadow: 0 2px 8px rgba(73, 61, 139, 0.1);
}

.keyword-option-selected {
  border-color: #493d8b;
  background: #f0f4ff;
  box-shadow: 0 4px 16px rgba(73, 61, 139, 0.25);
}

.keyword-option-editing {
  border-color: #493d8b;
  background: #fff;
  box-shadow: 0 4px 20px rgba(73, 61, 139, 0.3);
}

.color-badge {
  display: inline-block;
  min-width: 30px;
  text-align: center;
}

.color-badge-R {
  background: #ff6b6b;
  color: white;
}

.color-badge-B {
  background: #4dabf7;
  color: white;
}

.color-badge-P {
  background: #9775fa;
  color: white;
}

.color-badge-G {
  background: #51cf66;
  color: white;
}

.dialog-current {
  margin-bottom: 16px;
  font-size: 14px;
  color: #666;
}

.dialog-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.dialog-option-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
  white-space: nowrap;
}

.dialog-option-btn:hover {
  /* 悬停效果由内联样式处理 */
  opacity: 0.9;
}

.dialog-option-btn.selected {
  font-weight: bold;
  box-shadow: 0 2px 8px rgba(111, 85, 159, 0.3);
}

.network-tooltip {
  position: fixed;
  background: #ffffff;
  color: #333;
  padding: 14px 18px;
  border-radius: 8px;
  font-size: 13px;
  pointer-events: none;
  z-index: 10000;
  max-width: 420px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3);
  border: 2px solid #6f559f;
  line-height: 1.5;
  word-wrap: break-word;
  overflow: visible !important; /* 强制不显示滚动条，完全显示内容 */
  max-height: none !important; /* 移除任何最大高度限制 */
  /* 移除transition，避免抖动 */
}

.tooltip-title {
  font-weight: bold;
  margin-bottom: 10px;
  font-size: 15px;
  color: #1f1652;
  border-bottom: 2px solid #6f559f;
  padding-bottom: 8px;
}

.tooltip-content {
  font-size: 13px;
  line-height: 1.8;
  color: #222;
  overflow: visible !important;
  max-height: none !important;
  overflow-y: visible !important;
}

.tooltip-content > div {
  margin-bottom: 8px;
  font-weight: 500;
}

.co-occurrence-list {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.co-occurrence-item {
  background: linear-gradient(135deg, #6f559f 0%, #493d8b 100%);
  color: white;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 500;
  box-shadow: 0 2px 4px rgba(111, 85, 159, 0.3);
}

.contributor-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.contributor-item {
  background: linear-gradient(135deg, #f8f8f8 0%, #e8e8e8 100%);
  border: 1px solid #ddd;
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
}

.contributor-name {
  font-weight: 600;
  color: #1f1652;
  margin-bottom: 4px;
}

.contributor-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
}

.stat-item {
  color: #555;
  background: #fff;
  padding: 2px 6px;
  border-radius: 3px;
  border: 1px solid #ccc;
}

/* 包装器样式 */
.network-view-wrapper {
  position: relative;
  width: 100%;
}

.network-svg-container {
  display: flex;
  align-items: stretch;
  width: 100%;
  gap: 8px;
}

.network-svg-container.is-v3 .network-view-container {
  flex: 1;
  min-width: 0;
}

.v3-spiral-banner {
  font-size: 13px;
  line-height: 1.5;
  color: #4a3d7a;
  background: linear-gradient(90deg, #f5f0ff 0%, #eef6ff 100%);
  border: 1px solid #ddd5f0;
  border-radius: 6px;
  padding: 8px 12px;
  margin-bottom: 8px;
}

.v3-thermo {
  width: 52px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 4px;
  font-size: 11px;
  color: #555;
}

.v3-thermo-track {
  position: relative;
  width: 10px;
  height: 120px;
  background: #ececec;
  border-radius: 4px;
  margin: 6px 0;
  overflow: hidden;
  display: flex;
  align-items: flex-end;
}

.v3-thermo-fill {
  width: 100%;
  background: linear-gradient(180deg, #6f559f 0%, #493d8b 100%);
  border-radius: 3px 3px 0 0;
  transition: height 0.25s ease;
}

.v3-thermo-fill-ontology {
  background: linear-gradient(180deg, #3d8b6f 0%, #2e6b52 100%);
}

.v3-thermo-score {
  font-weight: 700;
  color: #333;
}

.v3-thermo-reason {
  margin-top: 4px;
  font-size: 10px;
  line-height: 1.3;
  color: #777;
  text-align: center;
  max-width: 48px;
  word-break: break-all;
}

.v3-bottom-panel {
  margin-top: 10px;
  padding: 14px 16px 8px;
  border: 1px solid #e6e0f2;
  border-radius: 10px;
  background: linear-gradient(180deg, #fcfbfe 0%, #f7f4fb 100%);
  font-size: 12.5px;
  line-height: 1.55;
  max-height: 420px;
  overflow: auto;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}

.v3-issue {
  margin-bottom: 14px;
}

.v3-bottom-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
}

.v3-bottom-label {
  display: block;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #3f3478;
  margin-bottom: 6px;
}

.v3-bottom-text {
  color: #333;
  white-space: normal;
  word-break: break-word;
}

.v3-sub-list {
  list-style: none;
  margin: 0;
  padding: 0;
  counter-reset: v3sub;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.v3-sub-list li {
  counter-increment: v3sub;
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
  background: #fff;
  border: 1px solid #efeaf6;
  border-radius: 8px;
  padding: 7px 10px;
  color: #333;
  word-break: break-word;
}

.v3-sub-list li::before {
  content: counter(v3sub);
  flex: 0 0 18px;
  height: 18px;
  margin-top: 1px;
  border-radius: 50%;
  background: #efe8f8;
  color: #5a4d8a;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
}

.v3-bottom-scales {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
  align-items: stretch;
}

.v3-quadrant-panel {
  margin-bottom: 12px;
}

.v3-quadrant-scales {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 8px;
}

.v3-quadrant-rule {
  margin: 6px 0 8px;
  color: #5a4d8a;
  font-size: 12px;
  line-height: 1.5;
}

.v3-scale-block {
  background: #fff;
  border: 1px solid #ece8f2;
  border-radius: 10px;
  padding: 10px 12px 8px;
  box-shadow: 0 1px 2px rgba(73, 61, 139, 0.04);
  min-width: 0;
}

.v3-scale-title {
  font-weight: 700;
  color: #3f3478;
  margin: -10px -12px 10px;
  padding: 8px 12px;
  border-radius: 10px 10px 0 0;
  background: #f4f0fa;
  border-bottom: 1px solid #ece8f2;
}

.v3-scale-four_color .v3-scale-title { background: #f8f1f4; }
.v3-scale-dmt .v3-scale-title { background: #f1f5fb; }
.v3-scale-knowledge .v3-scale-title { background: #f2f7f3; }

.v3-scale-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: stretch;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #efeaf6;
}

.v3-scale-item:last-of-type {
  border-bottom: none;
  margin-bottom: 4px;
  padding-bottom: 0;
}

.v3-sub-text {
  flex: 1;
  min-width: 0;
}

.v3-row-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}

.v3-scale-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.v3-mini-btn {
  border: 1px solid #d9d0ea;
  background: #fff;
  color: #5c4d86;
  border-radius: 999px;
  font-size: 12px;
  line-height: 1;
  padding: 4px 8px;
  cursor: pointer;
}

.v3-mini-btn:hover {
  background: #f6f2fb;
}

.v3-mini-add {
  margin-top: 8px;
}

.v3-panel-draft {
  width: 100%;
  resize: vertical;
  min-height: 72px;
}

.v3-scale-badge {
  align-self: flex-start;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  padding: 3px 8px;
  border-radius: 999px;
  color: #fff;
  background: #7a6aad;
}

.badge-R { background: #dc143c; }
.badge-B { background: #1e90ff; }
.badge-P { background: #9370db; }
.badge-G { background: #3cb371; }
.badge-D { background: #5b7cfa; }
.badge-M { background: #7a5af5; }
.badge-T { background: #2f9e8f; }
.badge-trad { background: #6b7280; }
.badge-org { background: #3d6f9c; }
.badge-trib { background: #3d7a5c; }

.v3-scale-desc {
  color: #3a3a3a;
  white-space: normal;
  word-break: break-word;
  line-height: 1.6;
}

.v3-top-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 6px;
}

.v3-top-row {
  padding-bottom: 8px;
  border-bottom: 1px dashed #efeaf6;
}

.v3-top-row:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.v3-top-row .v3-bottom-label {
  margin-bottom: 2px;
}

.v3-top-row .v3-chip-row {
  margin-top: 4px;
}

.v3-chip-row {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  gap: 6px;
  margin-top: 8px;
}

.v3-chip-hint {
  flex: 0 0 auto;
  align-self: center;
  font-size: 11px;
  color: #8a7eaa;
}

.v3-chip {
  border: 1px solid #d9d0e8;
  background: #fff;
  color: #493d8b;
  border-radius: 8px;
  padding: 3px 10px;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
  max-width: 100%;
  white-space: normal;
  text-align: left;
  word-break: break-word;
}

.v3-chip:hover {
  background: #f3eefb;
  border-color: #c3b6dc;
}

.v3-chip.v3-chip-current {
  cursor: default;
  background: #efe8f8;
  border-color: #c9bddf;
  font-weight: 600;
}

.v3-chip.v3-chip-current:hover {
  background: #efe8f8;
  border-color: #c9bddf;
}

.contour-ring {
  fill: rgba(217, 119, 6, 0.035);
  stroke: #e8c9a4;
  stroke-width: 1.4;
  opacity: 0.55;
  pointer-events: none;
}

.contour-ring.is-hot {
  fill: rgba(217, 119, 6, 0.14);
  stroke: #d97706;
  stroke-width: 2;
  opacity: 1;
}

.contour-ring.is-dim {
  opacity: 0.12;
}

.node-group.contour-dim,
.link-line.contour-dim,
.link-hit-area.contour-dim {
  opacity: 0.12;
}

.legend-longitude-dash {
  display: inline-block;
  width: 28px;
  height: 0;
  border-top: 2px dashed #c45c26;
  vertical-align: middle;
  margin: 0 4px;
}

.v3-pending-dialog {
  width: min(640px, calc(100vw - 48px));
  max-width: 640px;
  max-height: min(82vh, 760px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.v3-pending-dialog .dialog-header h3 {
  line-height: 1.4;
  word-break: break-word;
  padding-right: 8px;
}

.v3-pending-dialog .dialog-content {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-start;
  gap: 14px;
  overflow: auto;
  padding: 16px 18px 8px;
}

.v3-pending-lead {
  margin: 0;
  width: 100%;
  font-size: 13px;
  line-height: 1.55;
  color: #555;
}

.v3-pending-group {
  width: 100%;
  min-width: 0;
}

.v3-pending-group + .v3-pending-group {
  padding-top: 4px;
  border-top: 1px solid #efeaf6;
}

.v3-pending-group-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 700;
  color: #493d8b;
}

.v3-pending-group-note {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #7a738c;
}

.v3-pending-options {
  flex-direction: column;
  align-items: stretch;
}

.v3-pending-dialog .v3-pending-option-btn {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  text-align: left;
  gap: 10px;
  width: 100%;
  box-sizing: border-box;
  white-space: normal;
  word-break: break-word;
  height: auto;
  padding: 10px 12px;
  background: #fff;
  color: #2c2c2c;
  border: 1px solid #e4dff0;
  font-weight: 500;
  line-height: 1.5;
}

.v3-pending-dialog .v3-pending-option-btn:hover {
  background: #f7f4fb;
  border-color: #c9bddf;
  opacity: 1;
}

.v3-pending-dialog .v3-pending-option-btn.selected {
  background: #f3eefb;
  border-color: #493d8b;
  box-shadow: none;
}

.v3-pending-option-index {
  flex: none;
  width: 22px;
  height: 22px;
  margin-top: 1px;
  border-radius: 50%;
  background: #efeaf8;
  color: #493d8b;
  font-size: 12px;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.v3-pending-option-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.v3-pending-option-label {
  font-weight: 600;
  white-space: normal;
  word-break: break-word;
}

.v3-pending-option-preview {
  font-size: 12px;
  color: #6b6280;
  font-weight: 400;
  line-height: 1.45;
  white-space: normal;
  word-break: break-word;
}

.v3-pending-preview-highlight {
  margin-top: 12px;
  padding: 10px 12px;
  background: #f3f0fa;
  border-radius: 6px;
  font-size: 13px;
  color: #493d8b;
  line-height: 1.45;
}

.v3-top-replace-hint {
  margin: 0 0 10px;
  font-size: 13px;
  line-height: 1.45;
  color: #666;
}

.v3-pending-dialog .v3-pending-custom {
  margin-top: 0;
  width: 100%;
}

.v3-pending-dialog .v3-pending-custom label {
  display: block;
  font-size: 12px;
  color: #666;
  margin-bottom: 6px;
}

.v3-pending-dialog .v3-pending-custom .keyword-edit-input {
  width: 100%;
  height: auto;
  min-height: 36px;
  text-align: left;
}

.v3-pending-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin: 0;
  padding: 12px 18px 16px;
  border-top: 1px solid #eee;
  background: #fff;
}

.v3-pending-actions .dialog-option-btn {
  width: auto;
  white-space: nowrap;
  background: #f4f1f8;
  color: #3d3558;
  border: 1px solid #e4dff0;
}

.v3-pending-actions .v3-pending-confirm {
  background: #493d8b;
  color: #fff;
  border-color: #493d8b;
}

.v3-pending-actions .v3-pending-confirm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>


