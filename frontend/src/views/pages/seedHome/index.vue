<template>
    <div class="brain-navigator-home">
      <!-- 模式切换器 -->
      <div class="mode-switcher">
        <div class="switcher-container">
          <button 
            :class="['mode-btn', { active: currentMode === 'navigator' }]"
            @click="switchMode('navigator')"
          >
            <i class="el-icon-compass"></i>
            <span>思维导航</span>
          </button>
          <button 
            :class="['mode-btn', { active: currentMode === 'network' }]"
            @click="switchMode('network')"
          >
            <i class="el-icon-connection"></i>
            <span>神经网络</span>
          </button>
        </div>
      </div>
  
      <!-- 思维导航模式 -->
      <div v-if="currentMode === 'navigator'" class="navigator-mode">
        <el-container>
          <el-header class="brain-header">
            <!-- <MainNav /> -->
            <div class="brain-title">
              <h1>🧠 NKCN大脑思维导航器</h1>
              <p>智能思维状态感知与导航系统</p>
            </div>
          </el-header>
          
          <el-main class="brain-main">
            <BrainNavigator 
              :notebookData="notebookData"
              @brain-action="handleBrainAction"
            />
          </el-main>
      </el-container>
      </div>
  
      <!-- 神经网络模式 -->
      <div v-if="currentMode === 'network'" class="network-mode">
        <div class="network-header">
          <h1>🧠 NKCN思维神经网络</h1>
          <p>3D可视化思维网络，体验神经元信号传播</p>
          <div class="network-stats">
            <div class="stat-item">
              <span class="stat-label">思维节点</span>
              <span class="stat-value">{{ networkStats.nodes }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">信号强度</span>
              <span class="stat-value">{{ networkStats.signals }}%</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">连接密度</span>
              <span class="stat-value">{{ networkStats.density }}%</span>
            </div>
          </div>
        </div>
        
        <div class="network-content">
          <ThoughtNetwork3D
            :userId="userId"
            :notebookName="notebookName"
            @node-selected="handleNodeSelected"
            @suggestion-executed="handleSuggestionExecuted"
          />
        </div>
      </div>
  
    </div>
  </template>
  
  <script>
  // import MainNav from '@/components/MainNav.vue'
  // import BrainNavigator from '@/components/brainNavigator/BrainNavigator.vue'
  // import ThoughtNetwork3D from '@/components/thoughtNetwork/ThoughtNetwork3D.vue'
  import { ElMessage } from 'element-plus'
  
  export default {
    name: 'BrainNavigatorHome',
      components: {
      // MainNav,
      // BrainNavigator,
      // ThoughtNetwork3D
      },
      data() {
          return {
         currentMode: 'navigator', // 'navigator', 'network'
        notebookData: null,
        userId: localStorage.getItem('userId'),
        notebookName: (localStorage.getItem('userId') || '').replace((localStorage.getItem('realName') || '') + '_', ''),
        
        // 网络统计
        networkStats: {
          nodes: 0,
          signals: 0,
          density: 0
        },
        
      }
    },
    mounted() {
      this.initializeData()
    },
      methods: {
      switchMode(mode) {
        this.currentMode = mode
      },
      
      initializeData() {
        this.notebookData = {
          userId: this.userId,
          notebookName: this.notebookName
        }
      },
      
      handleBrainAction(action) {
        ElMessage.info(`执行思维动作: ${action}`)
      },
      
      handleNodeSelected(node) {
        ElMessage.success(`选中节点: ${node.title}`)
      },
      
      handleSuggestionExecuted(suggestion) {
        ElMessage.success(`执行建议: ${suggestion.title}`)
      },
      
      }
  }
  </script>
  
  <style scoped>
  .brain-navigator-home {
    width: 100%;
    height: 100vh;
    background: linear-gradient(135deg, #0f0f23 0%, #1a1a2e 50%, #16213e 100%);
    position: relative;
    overflow: hidden;
  }
  
  /* 模式切换器 */
  .mode-switcher {
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1000;
  }
  
  .switcher-container {
    display: flex;
    gap: 10px;
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
    border-radius: 25px;
    padding: 5px;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }
  
  .mode-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 12px 20px;
    border: none;
    background: transparent;
    color: rgba(255, 255, 255, 0.7);
    border-radius: 20px;
    cursor: pointer;
    transition: all 0.3s ease;
    font-size: 14px;
    font-weight: 500;
  }
  
  .mode-btn:hover {
    color: white;
    background: rgba(255, 255, 255, 0.1);
  }
  
  .mode-btn.active {
    color: white;
    background: linear-gradient(45deg, #00ff88, #00d4ff);
    box-shadow: 0 4px 15px rgba(0, 255, 136, 0.3);
  }
  
  /* 神经网络模式 */
  .network-mode {
    width: 100%;
    height: 100vh;
    position: relative;
  }
  
  .network-header {
    position: absolute;
    top: 80px;
    left: 20px;
    z-index: 100;
    color: white;
  }
  
  .network-header h1 {
    font-size: 32px;
    font-weight: 700;
    margin: 0 0 10px 0;
    background: linear-gradient(45deg, #00ff88, #00d4ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  
  .network-header p {
    font-size: 16px;
    color: rgba(255, 255, 255, 0.8);
    margin: 0 0 20px 0;
  }
  
  .network-stats {
    display: flex;
    gap: 20px;
  }
  
  .stat-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 15px;
    background: rgba(255, 255, 255, 0.1);
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.2);
  }
  
  .stat-label {
    font-size: 12px;
    color: #ccc;
    margin-bottom: 5px;
  }
  
  .stat-value {
    font-size: 24px;
    font-weight: 700;
    color: #00ff88;
  }
  
  .network-content {
    width: 100%;
    height: 100vh;
    position: relative;
  }
  
  
  /* 响应式设计 */
  @media (max-width: 768px) {
    .switcher-container {
      flex-direction: column;
      gap: 5px;
    }
    
    .mode-btn {
      padding: 10px 16px;
      font-size: 12px;
    }
    
  }
  </style>