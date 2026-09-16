<template>
  <div class="thought-network-container">
    <!-- 控制面板 -->
    <div class="network-controls" :class="{ 'collapsed': isCollapsed }">
      <div class="control-header" @click="toggleCollapse">
        <h3>思维神经网络</h3>
        <i class="collapse-icon" :class="{ 'collapsed': isCollapsed }">▼</i>
      </div>
      
      <div class="control-content" v-show="!isCollapsed">
        <div class="control-group">
          <div class="metrics">
            <div class="metric">
              <span class="label">节点数:</span>
              <span class="value">{{ networkData.total_nodes || 0 }}</span>
            </div>
            <div class="metric">
              <span class="label">信号强度:</span>
              <span class="value">{{ (networkData.avg_signal_strength * 100).toFixed(1) }}%</span>
            </div>
            <div class="metric">
              <span class="label">连接密度:</span>
              <span class="value">{{ (networkData.connection_density * 100).toFixed(1) }}%</span>
            </div>
          </div>
        </div>
        
        <div class="control-buttons">
          <button @click="startSignalPropagation" :disabled="!selectedNode" class="signal-btn">
            <i class="el-icon-connection"></i>
            传播信号
          </button>
          <button @click="generateInsights" class="insight-btn">
            <i class="el-icon-lightbulb"></i>
            生成洞察
          </button>
          <button @click="resetView" class="reset-btn">
            <i class="el-icon-refresh"></i>
            重置视图
          </button>
        </div>
      </div>
    </div>

    <!-- 3D网络可视化区域 -->
    <div class="network-visualization" ref="networkContainer">
      <div class="hexagonal-grid">
        <div 
          v-for="node in networkData.nodes" 
          :key="node.id"
          :class="['neuron-node', node.type, { 'selected': selectedNode === node.id, 'active': activeNodes.includes(node.id) }]"
          :style="{
            left: `${650 + (node.position?.x || 0) * 80}px`,
            top: `${400 + (node.position?.y || 0) * 80}px`,
            transform: `scale(${getNodeSize(node) * 1.2})`,
            '--signal-strength': getSignalStrength(node.id),
            '--node-color': node.color
          }"
          @click="selectNode(node)"
          @mouseenter="hoverNode(node)"
          @mouseleave="unhoverNode(node)"
        >
          <!-- 神经元核心 -->
          <div class="neuron-core">
            <div class="neuron-membrane"></div>
            <div class="neuron-nucleus"></div>
          </div>
          
          <!-- 信号脉冲 -->
          <div class="signal-pulse" v-if="activeNodes.includes(node.id)"></div>
          
          <!-- 节点标签 -->
          <div class="node-label">
            <div class="node-title">{{ node.title }}</div>
            <div class="node-type">{{ getNodeTypeLabel(node.type) }}</div>
          </div>
          
          <!-- 信号强度指示器 -->
          <div class="signal-indicator">
            <div class="signal-bar" :style="{ height: `${getSignalStrength(node.id) * 100}%` }"></div>
          </div>
        </div>
        
        <!-- 调试信息 -->
        <div class="debug-info" v-if="networkData.nodes.length > 0">
          <div>节点数量: {{ networkData.nodes.length }}</div>
          <div>中心节点: {{ networkData.center_id }}</div>
        </div>
        
        <!-- 连接线图例 -->
        <div class="connection-legend" v-if="networkData.nodes && networkData.nodes.length > 0">
          <h4>连接线说明</h4>
          <div class="legend-item">
            <div class="legend-line center"></div>
            <span>中心节点连接</span>
          </div>
          <div class="legend-item">
            <div class="legend-line active"></div>
            <span>激活连接</span>
          </div>
          <div class="legend-item">
            <div class="legend-line normal"></div>
            <span>普通连接</span>
          </div>
        </div>
        
        <!-- 神经元节点 -->
        <div class="neuron-nodes" v-if="networkData.nodes.length > 0">
          <div 
            v-for="node in networkData.nodes" 
            :key="`neuron-${node.id}`"
            class="neuron-cell"
            :class="[node.type, { 'selected': selectedNode === node.id, 'active': activeNodes.includes(node.id) }]"
            :style="{
              left: `${650 + (node.position?.x || 0) * 80}px`,
              top: `${400 + (node.position?.y || 0) * 80}px`,
              transform: `scale(${getNodeSize(node) * 1.2})`,
              '--neuron-color': node.color,
              '--signal-strength': getSignalStrength(node.id)
            }"
            @click="selectNode(node)"
          >
            <!-- 细胞体 -->
            <div class="cell-body">
              <div class="nucleus"></div>
              <div class="membrane"></div>
            </div>
            
            <!-- 轴突 - 暂时禁用 -->
            <!-- <div class="axon" v-for="(connection, index) in node.connections" :key="`axon-${node.id}-${connection}`">
              <div class="axon-body" :style="getAxonStyle(node, connection, index)"></div>
              <div class="axon-terminal"></div>
            </div> -->
            
            <!-- 树突 - 暂时禁用 -->
            <!-- <div class="dendrites">
              <div 
                v-for="(dendrite, index) in getDendrites(node)" 
                :key="`dendrite-${node.id}-${index}`"
                class="dendrite"
                :style="getDendriteStyle(dendrite, index)"
              ></div>
            </div> -->
            
            <!-- 信号传递动画 - 暂时禁用 -->
            <!-- <div class="signal-flows">
              <div 
                v-for="(signal, index) in getNodeSignals(node.id)" 
                :key="`signal-${node.id}-${index}`"
                class="signal-particle"
                :class="signal.type"
                :style="getSignalStyle(signal)"
              ></div>
            </div> -->
            
            <!-- 节点标签 -->
            <div class="neuron-label">
              <div class="node-title">{{ node.title }}</div>
              <div class="signal-type">{{ getSignalType(node) }}</div>
            </div>
          </div>
        </div>
        
        <!-- 连接线 -->
        <svg class="connections-svg" v-if="networkData.nodes.length > 0">
          <defs>
            <linearGradient v-for="(flow, index) in signalFlows" :key="`gradient-${index}`" :id="`gradient-${index}`">
              <stop offset="0%" :stop-color="getFlowColor(flow.strength)" stop-opacity="0.8"/>
              <stop offset="100%" :stop-color="getFlowColor(flow.strength)" stop-opacity="0.2"/>
            </linearGradient>
          </defs>
          
          <g v-for="node in networkData.nodes" :key="`connections-${node.id}`">
            <path
              v-for="(connectedId, index) in getFilteredConnections(node)"
              :key="`${node.id}-${connectedId}`"
              :d="getCurvedPath(node, connectedId, index)"
              :class="['connection-line', { 'active': activeConnections.includes(`${node.id}-${connectedId}`) }]"
              :stroke="getConnectionColor(node, connectedId)"
              :stroke-width="getConnectionWidth(node, connectedId)"
              :opacity="getConnectionOpacity(node, connectedId)"
              stroke-linecap="round"
              fill="none"
            />
          </g>
          
          <!-- 信号流动画 - 暂时禁用 -->
          <!-- <g v-for="(flow, index) in signalFlows" :key="`flow-${index}`">
            <circle
              :cx="getFlowPosition(flow, 'x')"
              :cy="getFlowPosition(flow, 'y')"
              r="2"
              :fill="getFlowColor(flow.strength)"
              :opacity="flow.opacity || 0.8"
              class="signal-particle"
            />
          </g> -->
        </svg>
      </div>
    </div>

    <!-- 洞察面板 -->
    <div class="insights-panel" v-if="insights.length > 0">
      <h3>思维洞察</h3>
      <div class="insights-list">
        <div 
          v-for="(insight, index) in insights" 
          :key="index"
          :class="['insight-item', insight.priority]"
        >
          <div class="insight-icon">
            <i :class="insight.icon"></i>
          </div>
          <div class="insight-content">
            <div class="insight-title">{{ insight.title }}</div>
            <div class="insight-description">{{ insight.description }}</div>
            <div class="insight-action">{{ insight.action }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 建议面板 -->
    <div class="suggestions-panel" v-if="suggestions.length > 0">
      <h3>智能建议</h3>
      <div class="suggestions-list">
        <div 
          v-for="(suggestion, index) in suggestions" 
          :key="index"
          :class="['suggestion-item', suggestion.priority]"
          @click="executeSuggestion(suggestion)"
        >
          <div class="suggestion-icon">
            <i :class="getSuggestionIcon(suggestion.type)"></i>
          </div>
          <div class="suggestion-content">
            <div class="suggestion-title">{{ suggestion.title }}</div>
            <div class="suggestion-description">{{ suggestion.description }}</div>
          </div>
          <div class="suggestion-arrow">
            <i class="el-icon-arrow-right"></i>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { analyzeThoughtNetwork, propagateThoughtSignals, generateThoughtInsights } from '@/api/thoughtNetwork/thought_network_api.js'

export default {
  name: 'ThoughtNetwork3D',
  props: {
    userId: {
      type: String,
      required: true
    },
    notebookName: {
      type: String,
      required: true
    }
  },
  data() {
    return {
      networkData: {
        nodes: [],
        signals: [],
        total_nodes: 0,
        avg_signal_strength: 0,
        connection_density: 0
      },
      selectedNode: null,
      activeNodes: [],
      activeConnections: [],
      signalFlows: [],
      insights: [],
      suggestions: [],
      animationId: null,
      time: 0,
      isCollapsed: false
    }
  },
  mounted() {
    this.loadNetworkData()
    this.startAnimation()
  },
  beforeDestroy() {
    if (this.animationId) {
      cancelAnimationFrame(this.animationId)
    }
  },
  methods: {
    toggleCollapse() {
      this.isCollapsed = !this.isCollapsed
    },

    async loadNetworkData() {
      try {
        const response = await analyzeThoughtNetwork(this.userId, this.notebookName)
        console.log('网络数据响应:', response.data)
        if (response.data.success) {
          this.networkData = response.data.network
          console.log('网络数据:', this.networkData)
          console.log('节点数量:', this.networkData.nodes?.length)
          console.log('节点详情:', this.networkData.nodes?.map(n => ({
            id: n.id,
            title: n.title,
            position: n.position,
            color: n.color
          })))
          this.generateInsights()
        }
      } catch (error) {
        console.error('加载思维网络数据失败:', error)
        this.$message.error('加载思维网络数据失败')
      }
    },

    async generateInsights() {
      try {
        const response = await generateThoughtInsights(this.userId, this.notebookName, this.networkData)
        console.log('洞察生成响应:', response.data)
        if (response.data.success) {
          this.insights = response.data.insights || []
          this.suggestions = response.data.suggestions || []
          this.networkData = { ...this.networkData, ...response.data.metrics }
          this.$message.success(`生成了${this.insights.length}个洞察和${this.suggestions.length}个建议`)
        }
      } catch (error) {
        console.error('生成思维洞察失败:', error)
        this.$message.error('生成思维洞察失败')
      }
    },

    async startSignalPropagation() {
      if (!this.selectedNode && this.networkData.nodes.length > 0) {
        // 如果没有选中节点，默认从中心节点开始
        this.selectedNode = this.networkData.center_id || 0
      }
      
      if (!this.selectedNode) {
        this.$message.warning('请先选择一个节点')
        return
      }

      try {
        const response = await propagateThoughtSignals(this.networkData, this.selectedNode)
        console.log('信号传播响应:', response.data)
        if (response.data.success) {
          this.animateSignalPropagation(response.data.propagation)
          this.$message.success('信号传播已启动')
        }
      } catch (error) {
        console.error('信号传播失败:', error)
        this.$message.error('信号传播失败')
      }
    },

    animateSignalPropagation(propagation) {
      this.activeNodes = []
      this.activeConnections = []
      this.signalFlows = []

      // 按时间顺序播放信号传播
      propagation.paths.forEach((path, index) => {
        setTimeout(() => {
          this.activeNodes.push(path.node_id)
          this.updateConnections(path.node_id)
        }, index * 200)
      })

      // 创建信号流动画
      propagation.flows.forEach((flow, index) => {
        setTimeout(() => {
          this.signalFlows.push({
            ...flow,
            opacity: 1,
            progress: 0
          })
        }, index * 100)
      })
    },

    updateConnections(nodeId) {
      const node = this.networkData.nodes.find(n => n.id === nodeId)
      if (node) {
        node.connections.forEach(connectedId => {
          this.activeConnections.push(`${nodeId}-${connectedId}`)
        })
      }
    },

    selectNode(node) {
      this.selectedNode = node.id
      this.$emit('node-selected', node)
    },

    hoverNode(node) {
      // 悬停效果
    },

    unhoverNode(node) {
      // 取消悬停效果
    },

    resetView() {
      this.selectedNode = null
      this.activeNodes = []
      this.activeConnections = []
      this.signalFlows = []
    },

    executeSuggestion(suggestion) {
      this.$emit('suggestion-executed', suggestion)
    },

    getSignalStrength(nodeId) {
      const signal = this.networkData.signals.find(s => s.node_id === nodeId)
      return signal ? signal.strength : 0
    },

    getNodeTypeLabel(type) {
      const labels = {
        'center': '中心节点',
        'card': '卡片节点',
        'similar': '相似节点'
      }
      return labels[type] || '未知'
    },

    getNodePosition(nodeId) {
      const node = this.networkData.nodes.find(n => n.id === nodeId)
      if (!node) {
        return { x: 0, y: 0, z: 0 }
      }
      return node.position || { x: 0, y: 0, z: 0 }
    },

    // 生成曲线路径，避免连接线重叠
    getCurvedPath(fromNode, toNodeId, connectionIndex) {
      const toNode = this.networkData.nodes.find(n => n.id === toNodeId)
      if (!toNode) return ''

      const fromPos = fromNode.position || { x: 0, y: 0 }
      const toPos = toNode.position || { x: 0, y: 0 }
      
      const x1 = 650 + fromPos.x * 80 + 25
      const y1 = 400 + fromPos.y * 80 + 25
      const x2 = 650 + toPos.x * 80 + 25
      const y2 = 400 + toPos.y * 80 + 25
      
      // 计算距离和角度
      const dx = x2 - x1
      const dy = y2 - y1
      const distance = Math.sqrt(dx * dx + dy * dy)
      const angle = Math.atan2(dy, dx)
      
      // 检查连接线是否穿过其他节点，如果穿过则绕行
      const obstacleNodes = this.findObstacleNodes(x1, y1, x2, y2, fromNode.id, toNode.id)
      
      // 计算控制点，使用更智能的偏移策略
      let midX = (x1 + x2) / 2
      let midY = (y1 + y2) / 2
      
      // 如果有障碍节点，调整控制点位置绕行
      if (obstacleNodes.length > 0) {
        const obstacle = obstacleNodes[0] // 取第一个障碍节点
        const obstaclePos = obstacle.position || { x: 0, y: 0 }
        const obstacleX = 650 + obstaclePos.x * 80 + 25
        const obstacleY = 400 + obstaclePos.y * 80 + 25
        
        // 计算绕行方向（垂直于连接线方向）
        const perpX = -dy / distance
        const perpY = dx / distance
        
        // 根据障碍节点位置调整控制点
        const obstacleDistance = Math.sqrt((obstacleX - midX) ** 2 + (obstacleY - midY) ** 2)
        const avoidDistance = 80 + obstacleDistance * 0.5 // 动态调整绕行距离
        
        // 选择绕行方向（远离障碍节点）
        const direction = (obstacleX - midX) * perpX + (obstacleY - midY) * perpY > 0 ? 1 : -1
        
        midX += perpX * avoidDistance * direction
        midY += perpY * avoidDistance * direction
      }
      
      // 根据连接类型和索引计算偏移
      let offsetX = 0
      let offsetY = 0
      
      if (fromNode.type === 'center' || toNode.type === 'center') {
        // 中心节点连接：使用较大的垂直偏移
        const similarity = toNode.similarity || fromNode.similarity || 0.5
        const baseOffset = 60 + similarity * 30 // 60-90px偏移
        offsetY = (connectionIndex % 2 === 0 ? 1 : -1) * baseOffset
      } else {
        // 其他连接：使用较小的偏移，避免与中心连接重叠
        const similarity = toNode.similarity || fromNode.similarity || 0.5
        const baseOffset = 30 + similarity * 20 // 30-50px偏移
        const direction = (connectionIndex % 2 === 0 ? 1 : -1)
        offsetX = direction * baseOffset * Math.cos(angle + Math.PI/2)
        offsetY = direction * baseOffset * Math.sin(angle + Math.PI/2)
      }
      
      const controlX = midX + offsetX
      const controlY = midY + offsetY
      
      // 生成二次贝塞尔曲线
      return `M ${x1} ${y1} Q ${controlX} ${controlY} ${x2} ${y2}`
    },

    // 获取轴突样式
    getAxonStyle(node, connection, index) {
      const connectedNode = this.networkData.nodes.find(n => n.id === connection)
      if (!connectedNode) return {}
      
      const dx = connectedNode.position.x - node.position.x
      const dy = connectedNode.position.y - node.position.y
      const length = Math.sqrt(dx * dx + dy * dy) * 120
      const angle = Math.atan2(dy, dx) * 180 / Math.PI
      
      return {
        width: `${length}px`,
        transform: `rotate(${angle}deg)`,
        '--axon-length': `${length}px`
      }
    },

    // 获取树突
    getDendrites(node) {
      const dendrites = []
      const count = 3 + Math.floor(Math.random() * 4) // 3-6个树突
      
      for (let i = 0; i < count; i++) {
        const angle = (360 / count) * i + Math.random() * 30 - 15
        const length = 20 + Math.random() * 30
        dendrites.push({ angle, length })
      }
      
      return dendrites
    },

    // 获取树突样式
    getDendriteStyle(dendrite, index) {
      return {
        transform: `rotate(${dendrite.angle}deg)`,
        width: `${dendrite.length}px`
      }
    },

    // 获取节点信号
    getNodeSignals(nodeId) {
      const signals = []
      const node = this.networkData.nodes.find(n => n.id === nodeId)
      
      if (!node) return signals
      
      // 为每个连接生成信号
      node.connections.forEach((connection, index) => {
        const type = Math.random() > 0.5 ? 'electrical' : 'chemical'
        signals.push({
          type,
          target: connection,
          progress: Math.random(),
          strength: Math.random()
        })
      })
      
      return signals
    },

    // 获取信号样式
    getSignalStyle(signal) {
      return {
        '--signal-progress': signal.progress,
        '--signal-strength': signal.strength
      }
    },

    // 检测连接线是否穿过其他节点
    findObstacleNodes(x1, y1, x2, y2, fromNodeId, toNodeId) {
      const obstacles = []
      const nodeRadius = 30 // 节点半径
      
      for (const node of this.networkData.nodes) {
        // 跳过连接的两个节点
        if (node.id === fromNodeId || node.id === toNodeId) continue
        
        const pos = node.position || { x: 0, y: 0 }
        const nodeX = 650 + pos.x * 80 + 25
        const nodeY = 400 + pos.y * 80 + 25
        
        // 计算点到线段的距离
        const distance = this.pointToLineDistance(x1, y1, x2, y2, nodeX, nodeY)
        
        // 如果距离小于节点半径，说明连接线会穿过这个节点
        if (distance < nodeRadius + 10) { // 额外10px缓冲
          obstacles.push(node)
        }
      }
      
      return obstacles
    },

    // 计算点到线段的距离
    pointToLineDistance(x1, y1, x2, y2, px, py) {
      const A = px - x1
      const B = py - y1
      const C = x2 - x1
      const D = y2 - y1

      const dot = A * C + B * D
      const lenSq = C * C + D * D
      
      if (lenSq === 0) {
        // 线段退化为点
        return Math.sqrt(A * A + B * B)
      }
      
      let param = dot / lenSq
      
      let xx, yy
      
      if (param < 0) {
        xx = x1
        yy = y1
      } else if (param > 1) {
        xx = x2
        yy = y2
      } else {
        xx = x1 + param * C
        yy = y1 + param * D
      }
      
      const dx = px - xx
      const dy = py - yy
      return Math.sqrt(dx * dx + dy * dy)
    },

    // 获取信号类型标签
    getSignalType(node) {
      // 基于节点类型和连接度判定信号类型
      const connectionCount = node.connections ? node.connections.length : 0
      const similarity = node.similarity || 0
      
      if (node.type === 'center') {
        return '电信号' // 中心节点使用电信号
      } else if (node.type === 'card') {
        return connectionCount > 2 ? '混合信号' : '化学信号' // 卡片节点根据连接度判定
      } else if (node.type === 'similar') {
        return similarity > 0.6 ? '电信号' : '化学信号' // 相似本子根据相似度判定
      }
      
      return '化学信号' // 默认化学信号
    },

    // 计算节点大小
    getNodeSize(node) {
      let baseSize = 0.4 // 基础大小，整体调小
      
      if (node.type === 'center') {
        baseSize = 0.8 // 中心节点最大
      } else if (node.type === 'card') {
        baseSize = 0.5 // 卡片节点中等
      } else if (node.type === 'similar') {
        // 相似本子节点根据相似度和层级调整大小
        const similarity = node.similarity || 0
        const level = node.level || 1
        baseSize = level === 1 ? 0.4 + similarity * 0.2 : 0.25 + similarity * 0.15
      }
      
      // 根据连接度微调大小
      const connectionCount = node.connections ? node.connections.length : 0
      const connectionFactor = Math.min(1.3, 1.0 + connectionCount * 0.08)
      
      return Math.max(0.2, baseSize * connectionFactor)
    },

    // 过滤连接线，只显示有效的连接
    getFilteredConnections(node) {
      if (!node.connections || !Array.isArray(node.connections)) {
        return []
      }
      
      // 严格验证连接，确保两端都有节点
      const validConnections = node.connections.filter(connectedId => {
        const connectedNode = this.networkData.nodes.find(n => n.id === connectedId)
        if (!connectedNode) {
          return false
        }
        // 确保目标节点有有效位置
        if (!connectedNode.position || typeof connectedNode.position.x !== 'number' || typeof connectedNode.position.y !== 'number') {
          console.warn(`节点 ${connectedId} 位置无效，跳过连接`)
          return false
        }
        return true
      })
      
      // 如果是中心节点，只显示与第一层相似本子的连接
      if (node.type === 'center') {
        return validConnections.filter(id => {
          const connectedNode = this.networkData.nodes.find(n => n.id === id)
          return connectedNode && connectedNode.type === 'similar' && connectedNode.level === 1
        })
      }
      
      // 如果是卡片节点，不显示任何连接线
      if (node.type === 'card') {
        return []
      }
      
      // // 如果是相似本子节点，只显示与父节点的连接
      // if (node.type === 'similar') {
      //   const level = node.level || 1
      //   if (level === 1) {
      //     // 第一层相似本子只连接中心节点
      //     return validConnections.filter(id => id === 0)
      //   } else {
      //     // 第二层相似本子只连接其父节点
      //     return validConnections.filter(id => {
      //       const connectedNode = this.networkData.nodes.find(n => n.id === id)
      //       return connectedNode && connectedNode.level === 1
      //     })
      //   }
      // }

      // 如果是相似本子节点，只显示与子节点的连接（不显示与父节点的连接，避免双向重复）
      if (node.type === 'similar') {
        const level = node.level || 1
        if (level === 1) {
          // 第一层相似本子不显示与中心节点的连接（由中心节点负责渲染）
          return validConnections.filter(id => {
            const connectedNode = this.networkData.nodes.find(n => n.id === id)
            return connectedNode && connectedNode.level === 2
          })
        } else {
          // 第二层相似本子不显示任何连接（由父节点负责渲染）
          return []
        }
      }
      
      return []
    },

    getConnectionColor(fromNode, toNodeId) {
      const toNode = this.networkData.nodes.find(n => n.id === toNodeId)
      if (!toNode) return '#666'
      
      // 激活的连接使用亮绿色
      if (this.activeConnections.includes(`${fromNode.id}-${toNodeId}`)) {
        return '#00ff88'
      }
      
      // 使用真实的相似度数据作为颜色强度
      let similarity = 0
      
      // 如果是相似本子节点，使用其相似度
      if (toNode.type === 'similar' && toNode.similarity) {
        similarity = toNode.similarity
      } else if (fromNode.type === 'similar' && fromNode.similarity) {
        similarity = fromNode.similarity
      } else {
        // 对于其他连接，使用信号强度
        const fromStrength = this.getSignalStrength(fromNode.id)
        const toStrength = this.getSignalStrength(toNodeId)
        similarity = (fromStrength + toStrength) / 2
      }
      
      const typeColors = {
        'center': '#ff6b6b',
        'card': '#4ecdc4',
        'similar': '#45b7d1'
      }
      
      const baseColor = typeColors[toNode.type] || '#666'
      
      // 简化颜色，减少视觉混乱
      if (fromNode.type === 'center' || toNode.type === 'center') {
        return '#00ff88' // 中心节点连接用绿色
      }
      
      if (this.activeConnections.includes(`${fromNode.id}-${toNodeId}`)) {
        return '#00d4ff' // 激活连接用蓝色
      }
      
      return '#666' // 其他连接统一用灰色
    },

    getConnectionWidth(fromNode, toNodeId) {
      const toNode = this.networkData.nodes.find(n => n.id === toNodeId)
      if (!toNode) return 1
      
      // 使用真实的相似度数据作为连接宽度
      let similarity = 0
      
      // 如果是相似本子节点，使用其相似度
      if (toNode.type === 'similar' && toNode.similarity) {
        similarity = toNode.similarity
      } else if (fromNode.type === 'similar' && fromNode.similarity) {
        similarity = fromNode.similarity
      } else {
        // 对于其他连接，使用信号强度
        const fromStrength = this.getSignalStrength(fromNode.id)
        const toStrength = this.getSignalStrength(toNodeId)
        similarity = (fromStrength + toStrength) / 2
      }
      
      // 简化线条粗细，减少视觉混乱
      if (fromNode.type === 'center' || toNode.type === 'center') {
        return 4 // 中心节点连接稍粗
      }
      
      if (this.activeConnections.includes(`${fromNode.id}-${toNodeId}`)) {
        return 5 // 激活连接更粗
      }
      
      return 3 // 其他连接统一较细
    },

    getConnectionOpacity(fromNode, toNodeId) {
      const toNode = this.networkData.nodes.find(n => n.id === toNodeId)
      if (!toNode) return 0.3
      
      // 使用真实的相似度数据作为透明度
      let similarity = 0
      
      // 如果是相似本子节点，使用其相似度
      if (toNode.type === 'similar' && toNode.similarity) {
        similarity = toNode.similarity
      } else if (fromNode.type === 'similar' && fromNode.similarity) {
        similarity = fromNode.similarity
      } else {
        // 对于其他连接，使用信号强度
        const fromStrength = this.getSignalStrength(fromNode.id)
        const toStrength = this.getSignalStrength(toNodeId)
        similarity = (fromStrength + toStrength) / 2
      }
      
      // 简化透明度，减少视觉混乱
      if (fromNode.type === 'center' || toNode.type === 'center') {
        return 0.8 // 中心节点连接较明显
      }
      
      if (this.activeConnections.includes(`${fromNode.id}-${toNodeId}`)) {
        return 1 // 激活连接完全不透明
      }
      
      return 0.6 // 其他连接统一透明度
    },

    getFlowColor(strength) {
      const intensity = Math.floor(strength * 255)
      return `rgb(${intensity}, 255, ${intensity})`
    },

    getFlowPosition(flow, axis) {
      const fromNode = this.networkData.nodes.find(n => n.id === flow.from_node)
      const toNode = this.networkData.nodes.find(n => n.id === flow.to_node)
      
      if (!fromNode || !toNode) return 0
      
      const progress = flow.progress || 0
      const fromPos = fromNode.position?.[axis] || 0
      const toPos = toNode.position?.[axis] || 0
      
      return 500 + ((fromPos || 0) + ((toPos || 0) - (fromPos || 0)) * progress) * 60 + 25
    },

    getSuggestionIcon(type) {
      const icons = {
        'explore_similar': 'el-icon-folder-opened',
        'organize_cards': 'el-icon-s-grid',
        'strengthen_connections': 'el-icon-connection'
      }
      return icons[type] || 'el-icon-lightbulb'
    },

    startAnimation() {
      const animate = () => {
        this.time += 0.016
        
        // 更新信号流位置
        this.signalFlows.forEach(flow => {
          flow.progress = (flow.progress || 0) + 0.02
          if (flow.progress >= 1) {
            flow.opacity = 0
          }
        })
        
        // 移除完成的信号流
        this.signalFlows = this.signalFlows.filter(flow => flow.progress < 1)
        
        this.animationId = requestAnimationFrame(animate)
      }
      
      animate()
    }
  }
}
</script>

<style scoped>
.thought-network-container {
  width: 100%;
  height: 100vh;
  background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
  position: relative;
  overflow: hidden;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.network-controls {
  position: absolute;
  top: 20px;
  left: 20px;
  z-index: 100;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  padding: 20px;
  color: white;
  min-width: 300px;
}

.control-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding: 5px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  margin-bottom: 15px;
}

.control-header h3 {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  background: linear-gradient(45deg, #00ff88, #00d4ff);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.collapse-icon {
  font-size: 14px;
  color: #ccc;
  transition: transform 0.3s ease;
  user-select: none;
}

.collapse-icon.collapsed {
  transform: rotate(-90deg);
}

.control-content {
  transition: all 0.3s ease;
}

.network-controls.collapsed {
  padding: 15px 20px;
}

.metrics {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}

.metric {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.metric .label {
  font-size: 14px;
  color: #ccc;
}

.metric .value {
  font-size: 16px;
  font-weight: 600;
  color: #00ff88;
}

.control-buttons {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.control-buttons button {
  padding: 12px 20px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.signal-btn {
  background: linear-gradient(45deg, #00ff88, #00d4ff);
  color: white;
}

.signal-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 5px 15px rgba(0, 255, 136, 0.3);
}

.insight-btn {
  background: linear-gradient(45deg, #ff6b6b, #ffa726);
  color: white;
}

.insight-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 5px 15px rgba(255, 107, 107, 0.3);
}

.reset-btn {
  background: linear-gradient(45deg, #9c27b0, #673ab7);
  color: white;
}

.reset-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 5px 15px rgba(156, 39, 176, 0.3);
}

.network-visualization {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: visible;
  min-height: 800px;
}

.hexagonal-grid {
  width: 100%;
  height: 100%;
  position: relative;
  min-height: 800px;
  background: 
    radial-gradient(circle at 20% 20%, rgba(0, 255, 136, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 80% 80%, rgba(0, 212, 255, 0.1) 0%, transparent 50%),
    radial-gradient(circle at 40% 60%, rgba(255, 107, 107, 0.1) 0%, transparent 50%);
}

.neuron-node {
  position: absolute;
  width: 60px;
  height: 60px;
  cursor: pointer;
  transition: all 0.3s ease;
  transform-origin: center;
  z-index: 10;
  display: none; /* 暂时隐藏复杂节点，使用简单节点 */
}

.neuron-node:hover {
  transform: scale(1.2) !important;
  z-index: 10;
}

.neuron-node.selected {
  transform: scale(1.3) !important;
  z-index: 15;
}

.neuron-node.active {
  animation: neuronPulse 0.5s ease-in-out;
}

.neuron-core {
  width: 100%;
  height: 100%;
  position: relative;
  border-radius: 50%;
  background: var(--node-color);
  box-shadow: 
    0 0 20px var(--node-color),
    inset 0 0 20px rgba(255, 255, 255, 0.2),
    0 0 0 2px rgba(255, 255, 255, 0.3);
}

.neuron-membrane {
  position: absolute;
  top: -5px;
  left: -5px;
  right: -5px;
  bottom: -5px;
  border-radius: 50%;
  border: 2px solid var(--node-color);
  opacity: 0.6;
  animation: membranePulse 2s infinite;
}

.neuron-nucleus {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 20px;
  height: 20px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.5);
}

.signal-pulse {
  position: absolute;
  top: -10px;
  left: -10px;
  right: -10px;
  bottom: -10px;
  border-radius: 50%;
  border: 3px solid #00ff88;
  animation: signalPulse 1s ease-out;
}

.node-label {
  position: absolute;
  top: 80px;
  left: 50%;
  transform: translateX(-50%);
  text-align: center;
  color: white;
  font-size: 14px;
  white-space: nowrap;
  background: rgba(0, 0, 0, 0.7);
  padding: 4px 8px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.neuron-node:hover .node-label {
  opacity: 1;
}

.node-title {
  font-weight: 600;
  margin-bottom: 2px;
}

.node-type {
  font-size: 10px;
  color: #ccc;
}

.signal-indicator {
  position: absolute;
  top: -15px;
  left: 50%;
  transform: translateX(-50%);
  width: 4px;
  height: 30px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
  overflow: hidden;
}

.signal-bar {
  width: 100%;
  background: linear-gradient(to top, #00ff88, #00d4ff);
  border-radius: 2px;
  transition: height 0.3s ease;
}

.connections-svg {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.connection-line {
  stroke-linecap: round;
  transition: all 0.3s ease;
}

.connection-line.active {
  stroke-dasharray: none;
  animation: activeConnection 0.5s ease-in-out;
}

.signal-particle {
  animation: particleMove 1s linear;
}

.insights-panel {
  position: absolute;
  top: 20px;
  right: 20px;
  width: 350px;
  max-height: 400px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  padding: 20px;
  color: white;
  overflow-y: auto;
  z-index: 100;
}

/* 响应式设计：在小屏幕上调整面板位置 */
@media (max-width: 1200px) {
  .insights-panel {
    right: 20px;
    top: 20px; /* 保持在右上角 */
  }
  
  .connection-legend {
    right: 20px;
    top: 200px; /* 向下移动，避免与洞察面板重叠 */
  }
}

.insights-panel h3 {
  margin: 0 0 15px 0;
  font-size: 18px;
  color: #00ff88;
}

.insights-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.insight-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 15px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 10px;
  border-left: 4px solid;
  transition: all 0.3s ease;
}

.insight-item.high {
  border-left-color: #ff6b6b;
}

.insight-item.medium {
  border-left-color: #ffa726;
}

.insight-item.low {
  border-left-color: #66bb6a;
}

.insight-item:hover {
  background: rgba(255, 255, 255, 0.1);
  transform: translateX(5px);
}

.insight-icon {
  font-size: 20px;
  color: #00ff88;
  margin-top: 2px;
}

.insight-content {
  flex: 1;
}

.insight-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 5px;
  color: white;
}

.insight-description {
  font-size: 12px;
  color: #ccc;
  margin-bottom: 5px;
  line-height: 1.4;
}

.insight-action {
  font-size: 11px;
  color: #00ff88;
  font-style: italic;
}

.suggestions-panel {
  position: absolute;
  bottom: 20px;
  right: 20px;
  width: 350px;
  max-height: 300px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  border-radius: 15px;
  padding: 20px;
  color: white;
  overflow-y: auto;
  z-index: 100;
}

.suggestions-panel h3 {
  margin: 0 0 15px 0;
  font-size: 18px;
  color: #00d4ff;
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestion-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
}

.suggestion-item:hover {
  background: rgba(255, 255, 255, 0.1);
  transform: translateX(5px);
}

.suggestion-icon {
  font-size: 16px;
  color: #00d4ff;
}

.suggestion-content {
  flex: 1;
}

.suggestion-title {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 3px;
  color: white;
}

.suggestion-description {
  font-size: 11px;
  color: #ccc;
  line-height: 1.3;
}

.suggestion-arrow {
  font-size: 12px;
  color: #666;
}

@keyframes neuronPulse {
  0% { transform: scale(1); }
  50% { transform: scale(1.2); }
  100% { transform: scale(1); }
}

@keyframes membranePulse {
  0%, 100% { opacity: 0.6; transform: scale(1); }
  50% { opacity: 0.3; transform: scale(1.1); }
}

@keyframes signalPulse {
  0% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(2); }
}

@keyframes connectionFlow {
  0% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: 20; }
}

@keyframes activeConnection {
  0% { stroke-width: 1; }
  50% { stroke-width: 3; }
  100% { stroke-width: 1; }
}

@keyframes particleMove {
  0% { opacity: 1; }
  100% { opacity: 0; }
}

.debug-info {
  position: absolute;
  top: 10px;
  left: 10px;
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 10px;
  border-radius: 5px;
  font-size: 12px;
  z-index: 100;
}

.debug-info div {
  margin-bottom: 5px;
}

.neuron-nodes {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.neuron-cell {
  position: absolute;
  width: 50px;
  height: 50px;
  cursor: pointer;
  pointer-events: all;
  z-index: 20;
  transition: all 0.3s ease;
  transform-origin: center;
}

.neuron-cell:hover {
  transform: scale(1.1) !important;
}

.neuron-cell.selected {
  transform: scale(1.2) !important;
  z-index: 30;
}

.neuron-cell.active {
  animation: neuronPulse 1s ease-in-out infinite;
}

/* 细胞体 */
.cell-body {
  position: relative;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: var(--neuron-color);
  box-shadow: 
    0 0 20px var(--neuron-color),
    inset 0 0 20px rgba(255, 255, 255, 0.2);
  margin: 10px;
}

.membrane {
  position: absolute;
  top: -5px;
  left: -5px;
  right: -5px;
  bottom: -5px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.3);
  animation: membranePulse 2s ease-in-out infinite;
}

.nucleus {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 20px;
  height: 20px;
  background: rgba(255, 255, 255, 0.8);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.3);
}

/* 轴突 - 暂时禁用 */
/* .axon {
  position: absolute;
  top: 50%;
  left: 50%;
  height: 3px;
  background: linear-gradient(90deg, var(--neuron-color), rgba(255, 255, 255, 0.3));
  transform-origin: left center;
  z-index: 5;
}

.axon-body {
  height: 100%;
  background: linear-gradient(90deg, var(--neuron-color), rgba(255, 255, 255, 0.3));
  animation: axonPulse 1.5s ease-in-out infinite;
}

.axon-terminal {
  position: absolute;
  right: -8px;
  top: -5px;
  width: 8px;
  height: 13px;
  background: var(--neuron-color);
  border-radius: 50%;
  box-shadow: 0 0 10px var(--neuron-color);
} */

/* 树突 - 暂时禁用 */
/* .dendrites {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 1px;
  height: 1px;
}

.dendrite {
  position: absolute;
  height: 2px;
  background: linear-gradient(180deg, var(--neuron-color), rgba(255, 255, 255, 0.3));
  transform-origin: left center;
  border-radius: 1px;
} */

/* .dendrite::after {
  content: '';
  position: absolute;
  right: -3px;
  top: -2px;
  width: 6px;
  height: 6px;
  background: var(--neuron-color);
  border-radius: 50%;
  opacity: 0.7;
} */

/* 信号传递动画 - 暂时禁用 */
/* .signal-flows {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.signal-particle {
  position: absolute;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  animation: signalMove 2s linear infinite;
}

.signal-particle.electrical {
  background: #00ff88;
  box-shadow: 0 0 10px #00ff88;
}

.signal-particle.chemical {
  background: #ff6b6b;
  box-shadow: 0 0 10px #ff6b6b;
} */

/* 节点标签 */
.neuron-label {
  position: absolute;
  top: -30px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 4px 8px;
  border-radius: 12px;
  font-size: 10px;
  white-space: nowrap;
  z-index: 40;
}

.node-title {
  font-weight: bold;
  margin-bottom: 2px;
}

.signal-type {
  font-size: 8px;
  opacity: 0.8;
}

/* 调试信息和图例 */
.debug-info {
  position: absolute;
  top: 20px;
  left: 10px;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 10px;
  border-radius: 5px;
  font-size: 12px;
  z-index: 100;
}

.connection-legend {
  position: absolute;
  top: 20px;
  right: 420px; /* 进一步左移，避免遮住思维洞察面板 */
  background: rgba(0, 0, 0, 0.9);
  color: white;
  padding: 12px;
  border-radius: 8px;
  font-size: 11px;
  z-index: 1000;
  min-width: 160px;
  max-width: 180px;
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
}

.connection-legend h4 {
  margin: 0 0 8px 0;
  color: #00ff88;
  font-size: 13px;
}

.legend-item {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
  gap: 8px;
}

.legend-line {
  width: 25px;
  height: 2px;
  border-radius: 1px;
}

.legend-line.center {
  background: #00ff88;
  opacity: 0.8;
  height: 3px;
}

.legend-line.active {
  background: #00d4ff;
  opacity: 1;
  height: 4px;
}

.legend-line.normal {
  background: #666;
  opacity: 0.6;
  height: 2px;
}

/* 动画 */
@keyframes neuronPulse {
  0%, 100% { 
    transform: scale(1);
    box-shadow: 0 0 20px var(--neuron-color);
  }
  50% { 
    transform: scale(1.1);
    box-shadow: 0 0 30px var(--neuron-color);
  }
}

@keyframes membranePulse {
  0%, 100% { 
    border-color: rgba(255, 255, 255, 0.3);
  }
  50% { 
    border-color: rgba(255, 255, 255, 0.7);
  }
}

@keyframes axonPulse {
  0%, 100% { 
    opacity: 0.7;
  }
  50% { 
    opacity: 1;
  }
}

@keyframes signalMove {
  0% { 
    opacity: 1;
    transform: scale(1);
  }
  100% { 
    opacity: 0;
    transform: scale(0.5);
  }
}
</style>
