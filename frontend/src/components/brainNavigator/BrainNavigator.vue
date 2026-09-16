<template>
  <div class="brain-navigator">
    <!-- 主控制面板 -->
    <div class="navigator-panel" :class="{ 'expanded': isExpanded }">
      <!-- 头部状态栏 -->
      <div class="status-header">
        <div class="brain-title">
          <img :src="iconImages.brain" class="icon-img" alt="brain">
          <span>NKCN大脑思维导航器</span>
          <div class="status-indicator" :class="brainStatus"></div>
        </div>
        <div class="control-buttons">
          <el-button size="mini" @click="toggleExpanded">
            <img :src="isExpanded ? iconImages.arrowUp : iconImages.arrowDown" class="icon-img" alt="arrow">
          </el-button>
          <el-button size="mini" @click="refreshAnalysis">
            <img :src="iconImages.refresh" class="icon-img" alt="refresh">
          </el-button>
        </div>
      </div>

      <!-- 思维状态仪表盘 -->
      <div class="thinking-dashboard" v-if="isExpanded">
        <!-- 象限感知器 -->
        <div class="quadrant-sensor">
          <h4>认知象限感知</h4>
          <div class="quadrant-display">
            <div class="quadrant-item" :class="{ 'active': thinkingState.quadrant === 'Q1' }">
              <span class="quadrant-label">Q1</span>
              <span class="quadrant-desc">知道自己知道</span>
            </div>
            <div class="quadrant-item" :class="{ 'active': thinkingState.quadrant === 'Q2' }">
              <span class="quadrant-label">Q2</span>
              <span class="quadrant-desc">不知道自己知道</span>
            </div>
            <div class="quadrant-item" :class="{ 'active': thinkingState.quadrant === 'Q3' }">
              <span class="quadrant-label">Q3</span>
              <span class="quadrant-desc">不知道自己不知道</span>
            </div>
            <div class="quadrant-item" :class="{ 'active': thinkingState.quadrant === 'Q4' }">
              <span class="quadrant-label">Q4</span>
              <span class="quadrant-desc">知道自己不知道</span>
            </div>
          </div>
        </div>

        <!-- 思维活跃度 -->
        <div class="mental-activity">
          <h4>思维活跃度</h4>
          <div class="activity-meter">
            <div class="activity-bar">
              <div class="activity-fill" :style="{ width: thinkingState.activity + '%' }"></div>
            </div>
            <span class="activity-value">{{ thinkingState.activity }}%</span>
          </div>
          <div class="activity-description">{{ getActivityDescription() }}</div>
        </div>

        <!-- 知识盲区热力图 -->
        <div class="knowledge-gaps">
          <h4>知识盲区热力图</h4>
          <div class="gaps-grid">
            <div v-for="gap in thinkingState.blindSpots" :key="gap.id" 
                 class="gap-item" :class="gap.intensity">
              <span class="gap-label">{{ gap.label }}</span>
              <span class="gap-score">{{ gap.score }}</span>
            </div>
          </div>
        </div>

        <!-- 跨本子思维连接 -->
        <div class="cross-notebook-connections">
          <h4>跨本子思维连接</h4>
          <div class="connections-list">
            <div v-for="connection in thinkingState.connections" :key="connection.id" 
                 class="connection-item">
              <img :src="iconImages.link" class="icon-img" alt="link">
              <span class="connection-label">{{ connection.notebook_name }}</span>
              <span class="connection-strength">{{ connection.strength }}%</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 动态思维路线图 -->
      <div class="thinking-pathway" v-if="isExpanded">
        <h4>动态思维路线图</h4>
        <div class="pathway-container">
          <div class="pathway-node" v-for="(node, index) in thinkingPathway" :key="index"
               :class="node.type" :style="{ left: node.x + '%', top: node.y + '%' }">
            <div class="node-content">
              <img :src="getNodeIcon(node.type)" class="icon-img" alt="node">
              <span class="node-label">{{ node.label }}</span>
            </div>
            <div class="node-connection" v-if="index < thinkingPathway.length - 1"></div>
          </div>
        </div>
      </div>

      <!-- 四色语境导航 -->
      <div class="context-navigation" v-if="isExpanded">
        <h4>四色语境导航</h4>
        <div class="context-layers">
          <div class="context-layer business" :class="{ 'active': currentContext === 'business' }">
            <span class="layer-label">业务语境</span>
            <div class="layer-content">{{ contextHints.businessContext }}</div>
          </div>
          <div class="context-layer neutral" :class="{ 'active': currentContext === 'neutral' }">
            <span class="layer-label">中性语境</span>
            <div class="layer-content">{{ contextHints.neutralContext }}</div>
          </div>
          <div class="context-layer scene" :class="{ 'active': currentContext === 'scene' }">
            <span class="layer-label">场景语境</span>
            <div class="layer-content">{{ contextHints.sceneContext }}</div>
          </div>
          <div class="context-layer natural" :class="{ 'active': currentContext === 'natural' }">
            <span class="layer-label">自然语境</span>
            <div class="layer-content">{{ contextHints.naturalContext }}</div>
          </div>
        </div>
      </div>

      <!-- 智能行动指引 -->
      <div class="action-guidance" v-if="isExpanded">
        <h4>智能行动指引</h4>
        <div class="action-suggestions">
          <div v-for="action in actionSuggestions" :key="action.id" 
               class="action-item" :class="action.priority">
            <img :src="getActionIcon(action.icon)" class="icon-img" alt="action">
            <div class="action-content">
              <span class="action-title">{{ action.title }}</span>
              <span class="action-description">{{ action.description }}</span>
            </div>
            <el-button size="mini" @click="executeAction(action)">执行</el-button>
          </div>
        </div>
      </div>
    </div>

    <!-- 脑波动画背景 -->
    <div class="brain-wave-bg" v-if="isExpanded">
      <div class="wave" v-for="i in 3" :key="i" :class="'wave-' + i"></div>
    </div>
  </div>
</template>

<script>
import { analyzeThinkingState, generateContextNavigation, getActionSuggestions } from '@/api/brainNavigator/brain_api'

export default {
  name: 'BrainNavigator',
  props: {
    chatList: Array,
    fileNameList: Array,
    choosedCardIdList: Array,
    sceneName: String,
    subSceneName: String
  },
  data() {
    return {
      isExpanded: false,
      brainStatus: 'normal', // normal, active, confused, breakthrough
      thinkingState: {
        quadrant: 'Q1',
        activity: 75,
        blindSpots: [],
        connections: []
      },
      thinkingPathway: [],
      contextHints: {
        businessContext: '',
        neutralContext: '',
        sceneContext: '',
        naturalContext: ''
      },
      currentContext: 'business',
      actionSuggestions: [],

      // 添加图标映射
      iconImages: {
        brain: require('@/assets/img/brainwindow/brain.png'),
        arrowUp: require('@/assets/img/brainwindow/arrowup.png'),
        arrowDown: require('@/assets/img/brainwindow/arrowdown.png'),
        refresh: require('@/assets/img/brainwindow/refresh.png'),
        link: require('@/assets/img/brainwindow/link.png'),
        robot: require('@/assets/img/brainwindow/robot.png'),
        user: require('@/assets/img/brainwindow/user.png'),
        question: require('@/assets/img/brainwindow/question.png'),
        lightbulb: require('@/assets/img/brainwindow/lightbulb.png'),
        search: require('@/assets/img/brainwindow/search.png')
      }
    }
  },
  mounted() {
    this.initializeAnalysis();
    this.startRealTimeAnalysis();
  },
  methods: {
    // 获取节点图标
    getNodeIcon(type) {
      const iconMap = {
        'ai-response': this.iconImages.robot,
        'user-question': this.iconImages.user
      };
      return iconMap[type] || this.iconImages.user;
    },
    
    // 获取行动图标
    getActionIcon(iconClass) {
      const iconMap = {
        'el-icon-question': this.iconImages.question,
        'el-icon-lightbulb': this.iconImages.lightbulb,
        'el-icon-search': this.iconImages.search
      };
      return iconMap[iconClass] || this.iconImages.question;
    },
    
    // 修改生成思维路径方法
    generateThinkingPathway() {
      const pathway = [];
      const recentChats = this.chatList.slice(-5);
      
      recentChats.forEach((chat, index) => {
        const x = (index / (recentChats.length - 1)) * 80 + 10;
        const y = Math.random() * 60 + 20;
        
        pathway.push({
          x: x,
          y: y,
          type: chat.uid === '2000' ? 'ai-response' : 'user-question',
          icon: chat.uid === '2000' ? 'el-icon-robot' : 'el-icon-user',  // 保持这个，用于getNodeIcon映射
          label: chat.uid === '2000' ? 'AI回答' : '用户提问'
        });
      });
      
      this.thinkingPathway = pathway;
    },

    // 初始化分析
    async initializeAnalysis() {
      await this.analyzeThinkingState();
      this.generateThinkingPathway();
      await this.generateContextHints();
      await this.generateActionSuggestions();
    },

    // 分析思维状态
    async analyzeThinkingState() {
      try {
        // 获取更多真实数据
        const currentNotebook = localStorage.getItem('currentNotebook');
        const notebookData = (localStorage.getItem('userId') || '').split('_').slice(1).join('_');
        
        const data = {
          user_id: localStorage.getItem('userId'),
          notebook_name: notebookData || '默认本子',
          chat_history: this.chatList,
          file_list: this.fileNameList,
          scene_name: this.sceneName || localStorage.getItem('sceneName') || '默认场景',
          sub_scene_name: this.subSceneName || localStorage.getItem('subSceneName') || '默认子场景'
        };
        
        console.log('发送思维状态分析请求:', data);
        
        const response = await analyzeThinkingState(data);
        if (response.error_num === 0) {
          this.thinkingState = response.data;
          this.updateBrainStatus();
          console.log('思维状态分析结果:', this.thinkingState);
        } else {
          console.error('思维状态分析失败:', response.message);
          this.fallbackToLocalAnalysis();
        }
      } catch (error) {
        console.error('思维状态分析请求失败:', error);
        this.fallbackToLocalAnalysis();
      }
    },

    // 备选本地分析
    fallbackToLocalAnalysis() {
      console.log('使用本地分析作为备选');
      this.thinkingState.quadrant = this.detectCognitiveQuadrant();
      this.thinkingState.activity = this.calculateMentalActivity();
      this.thinkingState.blindSpots = this.identifyKnowledgeGaps();
      this.thinkingState.connections = this.findCrossNotebookLinks();
      this.updateBrainStatus();
    },

    // 检测认知象限
    detectCognitiveQuadrant() {
      const recentQuestions = this.getRecentQuestions();
      const failedSearches = this.getFailedSearches();
      const conceptJumps = this.getConceptJumps();
      
      // 基于问题模式、检索失败率、概念跳跃度判断象限
      if (failedSearches > 0.3 && conceptJumps < 0.2) {
        return 'Q3'; // 不知道自己不知道
      } else if (conceptJumps > 0.5 && recentQuestions.length > 3) {
        return 'Q2'; // 不知道自己知道
      } else if (recentQuestions.length > 0 && failedSearches < 0.1) {
        return 'Q1'; // 知道自己知道
      } else {
        return 'Q4'; // 知道自己不知道
      }
    },

    // 计算思维活跃度
    calculateMentalActivity() {
      const questionCount = this.getRecentQuestions().length;
      const interactionCount = this.chatList.length;
      const fileCount = this.fileNameList.length;
      
      // 基于交互频率、问题数量、文件使用情况计算活跃度
      const activity = Math.min(100, (questionCount * 10 + interactionCount * 2 + fileCount * 5));
      return Math.max(20, activity);
    },

    // 识别知识盲区
    identifyKnowledgeGaps() {
      const gaps = [];
      const recentTopics = this.extractRecentTopics();
      const allTopics = this.getAllTopics();
      
      // 找出未充分探索的主题
      allTopics.forEach(topic => {
        if (!recentTopics.includes(topic)) {
          gaps.push({
            id: topic.id,
            label: topic.name,
            score: topic.relevance,
            intensity: topic.relevance > 0.7 ? 'high' : topic.relevance > 0.4 ? 'medium' : 'low'
          });
        }
      });
      
      return gaps.slice(0, 6); // 最多显示6个盲区
    },

    // 查找跨本子连接
    findCrossNotebookLinks() {
      // 模拟跨本子连接数据
      return [
        { id: 1, notebookName: 'AI研究本', strength: 85 },
        { id: 2, notebookName: '产品设计本', strength: 72 },
        { id: 3, notebookName: '技术文档本', strength: 68 }
      ];
    },

    // 生成思维路径
    generateThinkingPathway() {
      const pathway = [];
      const recentChats = this.chatList.slice(-5);
      
      recentChats.forEach((chat, index) => {
        const x = (index / (recentChats.length - 1)) * 80 + 10;
        const y = Math.random() * 60 + 20;
        
        pathway.push({
          x: x,
          y: y,
          type: chat.uid === '2000' ? 'ai-response' : 'user-question',
          icon: chat.uid === '2000' ? 'el-icon-robot' : 'el-icon-user',
          label: chat.uid === '2000' ? 'AI回答' : '用户提问'
        });
      });
      
      this.thinkingPathway = pathway;
    },

    // 生成四色语境提示
    async generateContextHints() {
      try {
        const currentContent = this.getCurrentContent();
        const data = {
          content: currentContent,
          scene_name: this.sceneName || localStorage.getItem('sceneName') || '默认场景',
          sub_scene_name: this.subSceneName || localStorage.getItem('subSceneName') || '默认子场景'
        };
        
        console.log('发送语境导航生成请求:', data);
        
        const response = await generateContextNavigation(data);
        if (response.error_num === 0) {
          this.contextHints = response.data;
          console.log('语境导航生成结果:', this.contextHints);
        } else {
          console.error('语境导航生成失败:', response.message);
          this.fallbackToLocalContext();
        }
      } catch (error) {
        console.error('语境导航生成请求失败:', error);
        this.fallbackToLocalContext();
      }
    },

    // 备选本地语境生成
    fallbackToLocalContext() {
      console.log('使用本地语境生成作为备选');
      const currentContent = this.getCurrentContent();
      this.contextHints = {
        businessContext: this.extractBusinessContext(currentContent),
        neutralContext: this.deriveNeutralContext(currentContent),
        sceneContext: this.suggestSceneContext(currentContent),
        naturalContext: this.elevateToNaturalContext(currentContent)
      };
    },

    // 生成行动建议
    async generateActionSuggestions() {
      try {
        const currentNotebook = localStorage.getItem('currentNotebook');
        const notebookData = (localStorage.getItem('userId') || '').split('_').slice(1).join('_');
        
        const data = {
          thinking_state: this.thinkingState,
          current_context: this.contextHints.businessContext,
          user_id: localStorage.getItem('userId'),
          notebook_name: notebookData || '默认本子'
        };
        
        console.log('发送行动建议生成请求:', data);
        
        const response = await getActionSuggestions(data);
        if (response.error_num === 0) {
          this.actionSuggestions = response.data;
          console.log('行动建议生成结果:', this.actionSuggestions);
        } else {
          console.error('行动建议生成失败:', response.message);
          this.generateLocalActionSuggestions();
        }
      } catch (error) {
        console.error('行动建议生成请求失败:', error);
        this.generateLocalActionSuggestions();
      }
    },

    // 本地生成行动建议（备选方案）
    generateLocalActionSuggestions() {
      const suggestions = [];
      
      // 基于当前状态生成建议
      if (this.thinkingState.quadrant === 'Q3') {
        suggestions.push({
          id: 1,
          title: '澄清问题',
          description: '尝试将问题分解为更具体的子问题',
          icon: 'el-icon-question',
          priority: 'high'
        });
      }
      
      if (this.thinkingState.activity < 50) {
        suggestions.push({
          id: 2,
          title: '激活思维',
          description: '尝试从不同角度思考问题',
          icon: 'el-icon-lightbulb',
          priority: 'medium'
        });
      }
      
      if (this.thinkingState.blindSpots.length > 0) {
        suggestions.push({
          id: 3,
          title: '探索盲区',
          description: '深入探索未充分了解的知识领域',
          icon: 'el-icon-search',
          priority: 'high'
        });
      }
      
      this.actionSuggestions = suggestions;
    },

    // 更新大脑状态
    updateBrainStatus() {
      if (this.thinkingState.quadrant === 'Q3') {
        this.brainStatus = 'confused';
      } else if (this.thinkingState.activity > 80) {
        this.brainStatus = 'active';
      } else if (this.thinkingState.activity < 30) {
        this.brainStatus = 'normal';
      } else {
        this.brainStatus = 'breakthrough';
      }
    },

    // 获取活动描述
    getActivityDescription() {
      if (this.thinkingState.activity > 80) return '思维非常活跃，创造力旺盛';
      if (this.thinkingState.activity > 60) return '思维活跃，思路清晰';
      if (this.thinkingState.activity > 40) return '思维平稳，需要更多刺激';
      return '思维较为平静，建议激活思考';
    },

    // 执行行动
    executeAction(action) {
      this.$emit('executeAction', action);
      this.$message.success(`正在执行：${action.title}`);
    },

    // 切换展开状态
    toggleExpanded() {
      this.isExpanded = !this.isExpanded;
    },

    // 刷新分析
    async refreshAnalysis() {
      await this.initializeAnalysis();
      this.$message.success('思维状态已刷新');
    },

    // 开始实时分析
    startRealTimeAnalysis() {
      setInterval(async () => {
        if (this.isExpanded) {
          await this.analyzeThinkingState();
        }
      }, 600000); // 每10min更新一次
    },

    // 辅助方法
    getRecentQuestions() {
      return this.chatList.filter(chat => chat.uid !== '2000').slice(-5);
    },

    getFailedSearches() {
      // 模拟检索失败率
      return Math.random() * 0.5;
    },

    getConceptJumps() {
      // 模拟概念跳跃度
      return Math.random() * 0.8;
    },

    extractRecentTopics() {
      // 从最近对话中提取主题
      return ['AI', '机器学习', '深度学习'];
    },

    getAllTopics() {
      // 获取所有相关主题
      return [
        { id: 1, name: '神经网络', relevance: 0.8 },
        { id: 2, name: '自然语言处理', relevance: 0.6 },
        { id: 3, name: '计算机视觉', relevance: 0.4 }
      ];
    },

    getCurrentContent() {
      return this.chatList[this.chatList.length - 1]?.msg || '';
    },

    extractBusinessContext(content) {
      return '从业务需求出发，关注实际应用场景和用户价值';
    },

    deriveNeutralContext(content) {
      return '抽象出中性的技术概念和通用原则';
    },

    suggestSceneContext(content) {
      return '构建具体的应用场景和上下文环境';
    },

    elevateToNaturalContext(content) {
      return '升华到自然语言表达，形成直观的理解';
    }
  }
}
</script>

<style lang="scss" scoped>
.brain-navigator {
  position: relative;
  width: 100%;
  height: 100%;
  
  .navigator-panel {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px;
    padding: 16px;
    color: white;
    transition: all 0.3s ease;
    box-shadow: 0px 8px 32px rgba(102, 126, 234, 0.3);
    
    &.expanded {
      height: 600px;
      overflow-y: auto;
    }
    
    .status-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      
      .brain-title {
        display: flex;
        align-items: center;
        font-size: 18px;
        font-weight: bold;
        
        i {
          margin-right: 8px;
          font-size: 20px;
        }
        
        .status-indicator {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          margin-left: 12px;
          
          &.normal { background: #4CAF50; }
          &.active { background: #FF9800; }
          &.confused { background: #F44336; }
          &.breakthrough { background: #9C27B0; }
        }
      }
      
      .control-buttons {
        display: flex;
        gap: 8px;
      }
    }
    
    .thinking-dashboard {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 20px;
      
      .quadrant-sensor {
        .quadrant-display {
          display: grid;
          grid-template-columns: 1fr 1fr;
          gap: 8px;
          
          .quadrant-item {
            padding: 8px;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.1);
            text-align: center;
            transition: all 0.3s ease;
            
            &.active {
              background: rgba(255, 255, 255, 0.3);
              transform: scale(1.05);
            }
            
            .quadrant-label {
              display: block;
              font-weight: bold;
              font-size: 16px;
            }
            
            .quadrant-desc {
              display: block;
              font-size: 12px;
              opacity: 0.8;
            }
          }
        }
      }
      
      .mental-activity {
        .activity-meter {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 8px;
          
          .activity-bar {
            flex: 1;
            height: 8px;
            background: rgba(255, 255, 255, 0.2);
            border-radius: 4px;
            overflow: hidden;
            
            .activity-fill {
              height: 100%;
              background: linear-gradient(90deg, #4CAF50, #FF9800, #F44336);
              transition: width 0.3s ease;
            }
          }
          
          .activity-value {
            font-weight: bold;
            min-width: 40px;
          }
        }
        
        .activity-description {
          font-size: 12px;
          opacity: 0.8;
        }
      }
      
      .knowledge-gaps {
        .gaps-grid {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 8px;
          
          .gap-item {
            padding: 6px;
            border-radius: 4px;
            text-align: center;
            font-size: 12px;
            
            &.high { background: rgba(244, 67, 54, 0.3); }
            &.medium { background: rgba(255, 152, 0, 0.3); }
            &.low { background: rgba(76, 175, 80, 0.3); }
            
            .gap-label {
              display: block;
              font-weight: bold;
            }
            
            .gap-score {
              display: block;
              opacity: 0.8;
            }
          }
        }
      }
      
      .cross-notebook-connections {
        .connections-list {
          .connection-item {
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 6px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 4px;
            margin-bottom: 4px;
            
            .connection-strength {
              margin-left: auto;
              font-weight: bold;
            }
          }
        }
      }
    }
    
    .thinking-pathway {
      margin-bottom: 20px;
      
      .pathway-container {
        position: relative;
        height: 120px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 8px;
        overflow: hidden;
        
        .pathway-node {
          position: absolute;
          width: 60px;
          height: 60px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.2);
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.3s ease;
          
          &.user-question {
            background: rgba(33, 150, 243, 0.3);
          }
          
          &.ai-response {
            background: rgba(76, 175, 80, 0.3);
          }
          
          .node-content {
            text-align: center;
            
            i {
              display: block;
              font-size: 20px;
              margin-bottom: 4px;
            }
            
            .node-label {
              font-size: 10px;
              display: block;
            }
          }
          
          .node-connection {
            position: absolute;
            right: -30px;
            top: 50%;
            width: 30px;
            height: 2px;
            background: rgba(255, 255, 255, 0.5);
            transform: translateY(-50%);
          }
        }
      }
    }
    
    .context-navigation {
      margin-bottom: 20px;
      
      .context-layers {
        .context-layer {
          padding: 12px;
          margin-bottom: 8px;
          border-radius: 6px;
          background: rgba(255, 255, 255, 0.1);
          transition: all 0.3s ease;
          
          &.active {
            background: rgba(255, 255, 255, 0.3);
            transform: translateX(8px);
          }
          
          .layer-label {
            display: block;
            font-weight: bold;
            margin-bottom: 4px;
          }
          
          .layer-content {
            font-size: 12px;
            opacity: 0.8;
          }
        }
      }
    }
    
    .action-guidance {
      .action-suggestions {
        .action-item {
          display: flex;
          align-items: center;
          gap: 12px;
          padding: 12px;
          background: rgba(255, 255, 255, 0.1);
          border-radius: 6px;
          margin-bottom: 8px;
          transition: all 0.3s ease;
          
          &.high {
            border-left: 4px solid #F44336;
          }
          
          &.medium {
            border-left: 4px solid #FF9800;
          }
          
          &.low {
            border-left: 4px solid #4CAF50;
          }
          
          i {
            font-size: 20px;
          }
          
          .action-content {
            flex: 1;
            
            .action-title {
              display: block;
              font-weight: bold;
              margin-bottom: 4px;
            }
            
            .action-description {
              display: block;
              font-size: 12px;
              opacity: 0.8;
            }
          }
        }
      }
    }
  }
  
  .brain-wave-bg {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    pointer-events: none;
    overflow: hidden;
    
    .wave {
      position: absolute;
      width: 200%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
      animation: wave 3s infinite linear;
      
      &.wave-1 {
        top: 20%;
        animation-delay: 0s;
      }
      
      &.wave-2 {
        top: 50%;
        animation-delay: 1s;
      }
      
      &.wave-3 {
        top: 80%;
        animation-delay: 2s;
      }
    }
  }
}

@keyframes wave {
  0% {
    transform: translateX(-100%);
  }
  100% {
    transform: translateX(100%);
  }
}




.icon-img {
  width: 20px;
  height: 20px;
  vertical-align: middle;
  object-fit: contain;
  
  // 不同位置的图标大小调整
  .brain-title & {
    width: 20px;
    height: 20px;
    margin-right: 8px;
  }
  
  .control-buttons & {
    width: 14px;
    height: 14px;
  }
  
  .connection-item & {
    width: 16px;
    height: 16px;
  }
  
  .pathway-node & {
    width: 24px;
    height: 24px;
    margin-bottom: 4px;
  }
  
  .action-item & {
    width: 20px;
    height: 20px;
  }
}
</style>
