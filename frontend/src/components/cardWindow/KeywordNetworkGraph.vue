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
        v-if="viewMode === 'network' && !isOntologyScopeMode"
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
        @click="exportFullNetworkPng"
        title="复制整张语义关键词空间图到剪贴板（高清 PNG）"
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
  <div v-if="viewMode === 'network'" class="network-view-wrapper">
    <div class="network-view-container" :style="{ height: computedContainerHeight }" ref="networkContainer">
      <div class="network-canvas-wrapper" ref="networkWrapper">
        <svg 
          ref="networkSvg" 
          class="network-svg"
          :viewBox="computedViewBox"
          preserveAspectRatio="xMidYMid meet">
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
          
          <!-- 连接线（透明热区便于右键细线） -->
          <g class="links">
            <line
              v-for="link in links"
              :key="`hit-${link.source.id}-${link.target.id}`"
              :x1="link.source.x"
              :y1="link.source.y"
              :x2="link.target.x"
              :y2="link.target.y"
              stroke="transparent"
              stroke-width="12"
              class="link-hit-area"
              @mouseenter="highlightLink(link, $event)"
              @mouseleave="resetHighlight"
              @contextmenu.prevent="handleLinkRightClick(link, $event)"
            />
            <line
              v-for="link in links"
              :key="`${link.source.id}-${link.target.id}`"
              :x1="link.source.x"
              :y1="link.source.y"
              :x2="link.target.x"
              :y2="link.target.y"
              :stroke-width="link.width"
              :stroke="link.color"
              :opacity="link.opacity"
              class="link-line"
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
                'new-keyword': !!node.isNew
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
              
              <circle
                :r="node.radius"
                :fill="node.color"
                :stroke="node.stroke"
                :stroke-width="node.strokeWidth"
                class="node-circle"
                @click="toggleKeywordSelection(node.label)"
                @mouseenter="showTooltip(node, $event)"
                @mouseleave="hideTooltip"
                @mouseover.stop
                @mousedown="startDrag(node, $event)"
                @contextmenu.prevent="handleRightClick(node, $event)"
              />
              
              <!-- 节点圆圈内的数字（卡片数量）；大本体模式无本子卡片，不显示 0 -->
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
                :font-size="node.fontSize || 10"
                :fill="node.textColor || '#333'"
                text-anchor="middle"
                dy=".35em"
                :y="(node.radius || 10) + 10"
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
          <div v-else>含此关键词的卡片: {{ tooltip.data?.cardCount }} 张</div>
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

const DEFAULT_NODE_DISPLAY_LIMIT = 30;
const MAX_NODE_DISPLAY_OPTION_DEFAULT = 100;
const MAX_NODE_DISPLAY_OPTION_V2 = 150;
const RECOMMENDED_NODE_LIMIT = 70;
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
      exportingNetworkPng: false,
      keywordPickStrategy: KEYWORD_PICK_STRATEGIES.default,
      showKeywordPickStrategyDialog: false,
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
                
                this.loadSavedPositions();
                this.restorePositions();
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

    /** 做过 v2 本体语义梳理的本子：节点显示上限提到 150 */
    maxNodeDisplayOption() {
      const meta = this.semanticReorganizeMeta || {};
      const isV2 = meta.pipeline === 'v2_condense_hierarchy'
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

      const candidates = [DEFAULT, 50, 70, 80, 100, MAX_OPT].filter((n, i, arr) => arr.indexOf(n) === i);
      const values = [...new Set(
        candidates.filter(n => n >= DEFAULT && n <= cap),
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
      // 🔥 协作象限坐标轴：X轴 y=610，Y轴 x=60，原点 (60,610)
      // viewBox 需包含象限底纹、轴标签与所有节点（节点位置仍为语义网络布局）
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
      
      // 🔥 检测是否是首次加载（本子内纯首次加载，没有任何保存的位置）
      const isFirstLoad = !this.savedPositions || Object.keys(this.savedPositions).length === 0;
      
      // 初始化D3力导向布局（在恢复位置之前先初始化，确保布局能正确运行）
      this.$nextTick(() => {
        if (isFirstLoad) {
          // 🔥 首次加载时，先执行一次布局（让节点先显示出来）
          this.restorePositions(false);
          this.initializeForceLayout();
          
          // 🔥 注意：首次加载的自动重置布局现在由viewMode的watch来处理
          // 这样可以确保在tags-container显示后才开始计时
          console.log('[initializeNetwork] 🔥 检测到首次加载，viewMode watch会处理延迟重置');
        } else {
          // 非首次加载：先恢复位置（但不固定，让布局先运行）
          this.restorePositions(false);
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
        return Math.min(Math.max(n, DEFAULT_NODE_DISPLAY_LIMIT), this.maxNodeDisplayOption);
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
      const nextLimit = Math.min(Math.max(limit, DEFAULT_NODE_DISPLAY_LIMIT), this.maxNodeDisplayOption);
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
      if (this.isOntologyScopeMode || this.keywordPickStrategy === KEYWORD_PICK_STRATEGIES.default) {
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
        let hasPermanentCard = false;
        if (!this.isOntologyScopeMode && this.effectiveCards && Array.isArray(this.effectiveCards)) {
          const keywordTrimmed = (keyword || '').trim();
          hasPermanentCard = this.effectiveCards.some(card => {
            const cardKeyWords = (card.keyWords || '').trim();
            return card.title === '关键词神经元永久卡' && 
                   cardKeyWords === keywordTrimmed && 
                   card.four_color_type; // 必须有四色属性（深色卡）
          });
        }
        
        // 🔥 根据是否有永久卡调整颜色深浅（加大对比度）
        let r, g, b;
        if (hasPermanentCard) {
          // 有永久卡：使用较深的颜色（baseColor * 0.65）
          r = Math.round(baseColor.r * 0.65);
          g = Math.round(baseColor.g * 0.65);
          b = Math.round(baseColor.b * 0.65);
        } else {
          // 无永久卡 / 大本体：使用很浅的颜色（baseColor * 0.45 + white * 0.55）
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
    
    calculateNodes(keywords) {
      // 🔥 如果设置了作者筛选，只统计该作者有贡献的关键词
      const authorFilterText = (this.authorFilter || '').trim().toLowerCase();
      const hasAuthorFilter = authorFilterText.length > 0;
      
      // 统计每个关键词关联的卡片数量
      const cardCounts = {};
      keywords.forEach(keyword => {
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
        
        // 计算节点内数字的字体大小（根据节点半径自适应）
        const finalRadius = Math.max(radius, 5);
        const countFontSize = Math.max(8, Math.min(finalRadius * 0.6, 12));
        
        // 🔥 如果设置了作者筛选且该关键词没有该作者的卡片，跳过此节点（部落关键词必显不跳过）
        const isTribalKw = (this.tribalKeywords || []).includes(keyword) || knowledgeType === 'trib';
        if (hasAuthorFilter && !isTribalKw) {
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
        
        return {
          id: index,
          label: keyword,
          cardCount: cardCount,
          radius: finalRadius,
          fontSize: 10,
          countFontSize: countFontSize,
          countTextColor: '#ffffff',
          x: savedPos ? savedPos.x : (centerX + offsetX),
          y: savedPos ? savedPos.y : (centerY + offsetY),
          fx: savedPos ? savedPos.x : undefined,
          fy: savedPos ? savedPos.y : undefined,
          color: colors.color,
          dmtLevel: dmtLevel,
          knowledgeType: knowledgeType,
          stroke: colors.stroke,
          strokeWidth: colors.strokeWidth,
          textColor: '#333',
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
    
    // 🔥 处理右键点击（显示菜单）
    handleRightClick(node, event) {
      event.preventDefault();
      event.stopPropagation();
      
      this.closeLinkContextMenu();
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

        const strengthWidth = { '强': 5.5, '强中': 3.3, '普通': 1.0 };
        // Vue3 无 $set，直接赋值即可触发响应式
        link.linkStrength = strength;
        link.width = strengthWidth[strength] || 1.0;

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
        const strengthWidth = { '强': 5.5, '强中': 3.3, '普通': 1.0 };
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
            links.push({
              source: source,
              target: target,
              value: 1,
              width: strengthWidth[strength],
              opacity: 0.75,
              color: '#493d8b',
              linkType: 'hierarchy',
              linkStrength: strength,
              parentKeyword: kw1,
              childKeyword: kw2
            });
          }
        });
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
      
      return links;
    },
    
    initializeForceLayout() {
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
      
      // 使用 D3 v3 API 创建力导向布局（平衡紧凑性和间距）
      this.simulation = d3.layout.force()
        .nodes(this.nodes)
        .links(this.links)
        .size([this.svgWidth, this.svgHeight])
        .linkDistance(120) // 适中的连接距离，避免拥挤
        .linkStrength(0.7) // 适中的连接强度
        .charge(-400) // 适中的排斥力，保持节点间距
        .gravity(0.08) // 适中的重力，保持中心集中但不过度
        .friction(0.9) // 增加摩擦力，让布局更稳定
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
        if (iterations < maxIterations && self.simulation && self.simulation.alpha() > 0.001) {
          self.simulation.tick();
          iterations++;
          requestAnimationFrame(tick);
        } else {
          // 恢复原始随机函数
          Math.random = originalRandom;
          
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
          self.savePositions();
          
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
              contributors: contributors,
              isMultiWriter: isMultiWriter,
              coOccurrences: coOccurrences
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
        } else {
          // 没有重合，正常保存位置
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
    
    resetLayout() {
      // 清除当前档位保存的位置
      this.savedPositions = {};
      localStorage.removeItem(this.getPositionsStorageKeyForLimit(this.getActiveNodeLimit()));
      
      // 保留基准viewBox范围，确保重置后显示大小一致
      // this.baseViewBoxBounds 保持不变
      
      // 重置所有节点的固定位置
      this.nodes.forEach(node => {
        node.fx = undefined;
        node.fy = undefined;
      });
      
      // 重新初始化布局
      this.initializeNetwork();
    },
    
    savePositions(limitOverride) {
      // 🔥 保存节点位置到 localStorage（按本子 + 显示数量档位独立保存）
      const positions = {};
      this.nodes.forEach(node => {
        // 🔥 优先使用fx/fy（固定位置），如果没有则使用x/y
        const posX = node.fx !== undefined ? node.fx : (node.x !== undefined ? node.x : null);
        const posY = node.fy !== undefined ? node.fy : (node.y !== undefined ? node.y : null);
        
        if (posX !== null && posY !== null) {
          positions[node.label] = {
            x: Math.round(posX * 100) / 100, // 保留2位小数
            y: Math.round(posY * 100) / 100
          };
        }
      });
      
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

    /** 复制整图高清 PNG 到剪贴板（按完整 viewBox，3× 像素） */
    async exportFullNetworkPng() {
      if (this.exportingNetworkPng) return;
      const svg = this.$refs.networkSvg;
      if (!svg || this.viewMode !== 'network') {
        this.$message?.warning?.('请先切换到网络图视图再复制');
        return;
      }
      this.exportingNetworkPng = true;
      try {
        await this.$nextTick();
        const vbRaw = (svg.getAttribute('viewBox') || this.computedViewBox || '0 0 800 600').trim();
        const parts = vbRaw.split(/\s+/).map(Number);
        const minX = Number.isFinite(parts[0]) ? parts[0] : 0;
        const minY = Number.isFinite(parts[1]) ? parts[1] : 0;
        const vbW = Math.max(1, Number.isFinite(parts[2]) ? parts[2] : 800);
        const vbH = Math.max(1, Number.isFinite(parts[3]) ? parts[3] : 600);
        const scale = 3;

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
          const img = new Image();
          await new Promise((resolve, reject) => {
            img.onload = () => resolve();
            img.onerror = (e) => reject(e || new Error('SVG 转图片失败'));
            img.src = url;
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

          const pngBlob = await new Promise((resolve, reject) => {
            canvas.toBlob((b) => {
              if (b) resolve(b);
              else reject(new Error('PNG 生成失败'));
            }, 'image/png');
          });

          if (!navigator.clipboard || typeof ClipboardItem === 'undefined') {
            throw new Error('当前浏览器不支持图片剪贴板');
          }
          await navigator.clipboard.write([
            new ClipboardItem({ 'image/png': pngBlob }),
          ]);
          this.$message?.success?.(`已复制高清整图到剪贴板（${scale}×，${canvas.width}×${canvas.height}），可直接粘贴`);
        } finally {
          URL.revokeObjectURL(url);
        }
      } catch (e) {
        console.error('[KeywordNetworkGraph] 复制整图失败:', e);
        this.$message?.error?.('复制整图失败：请用 Chrome/Edge，并允许剪贴板权限后重试');
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
</style>


