<template>
    <el-container class="brain-navigator-home">
        <el-header class="brain-header">
            <div class="brain-title">
                <h1>🧠 NKCN大脑思维导航器</h1>
                <p>智能思维状态感知与导航系统</p>
            </div>
        </el-header>
        
        <el-main class="brain-main">
            <!-- 左侧：聊天模拟区域 -->
            <div class="chat-simulation-panel">
                <div class="panel-header">
                    <h3>💬 实时聊天数据</h3>
                    <div class="control-buttons">
                        <el-button @click="addMockMessage" type="primary" size="small">
                            <i class="el-icon-plus"></i> 添加消息
                        </el-button>
                        <el-button @click="resetMockData" size="small">
                            <i class="el-icon-refresh"></i> 重置
                        </el-button>
                        <el-button @click="loadRealData" type="success" size="small">
                            <i class="el-icon-connection"></i> 加载真实数据
                        </el-button>
                    </div>
                </div>
                
                <div class="chat-list">
                    <div v-for="(msg, index) in chatList" :key="index" 
                         class="chat-item" :class="msg.uid === '2000' ? 'ai' : 'user'">
                        <div class="msg-header">
                            <span class="msg-type">{{ msg.uid === '2000' ? 'AI' : '用户' }}</span>
                            <span class="msg-time">{{ msg.time }}</span>
                        </div>
                        <div class="msg-content">{{ msg.msg }}</div>
                    </div>
                </div>
                
                <!-- 文件列表显示 -->
                <div class="file-list" v-if="fileNameList.length > 0">
                    <h4>📁 当前文件</h4>
                    <div class="file-tags">
                        <el-tag v-for="file in fileNameList" :key="file" class="file-tag">
                            {{ file }}
                        </el-tag>
                    </div>
                </div>
                
                <!-- 卡片列表显示 -->
                <div class="card-list" v-if="choosedCardIdList.length > 0">
                    <h4>📋 选中卡片</h4>
                    <div class="card-tags">
                        <el-tag v-for="cardId in choosedCardIdList" :key="cardId" type="success" class="card-tag">
                            Card {{ cardId }}
                        </el-tag>
                    </div>
                </div>
            </div>
            
            <!-- 右侧：大脑导航器 -->
            <div class="navigator-panel">
                <BrainNavigator 
                    :chatList="chatList"
                    :fileNameList="fileNameList"
                    :choosedCardIdList="choosedCardIdList"
                    :sceneName="sceneName"
                    :subSceneName="subSceneName"
                    @executeAction="handleBrainAction"
                />
            </div>
        </el-main>
    </el-container>
</template>

<script>
import MainNav from "@/views/mainNav.vue"
import BrainNavigator from '@/components/brainNavigator/BrainNavigator.vue'
import { getChatMsg } from "@/api/getData"
import { getRealChatHistory } from "@/api/brainNavigator/brain_api"

export default {
    name: "BrainNavigatorHome",
    components: {
        MainNav,
        BrainNavigator
    },
    data() {
        return {
            chatList: [],
            fileNameList: [],
            choosedCardIdList: [],
            sceneName: 'AI技术研究',
            subSceneName: '基础概念学习',
            isLoading: false
        }
    },
    async mounted() {
        await this.loadRealData()
    },
    methods: {
        // 加载真实数据
        async loadRealData() {
            this.isLoading = true
            try {
                // 获取当前用户信息
                const userId = localStorage.getItem('userId')
                const notebookData = (localStorage.getItem('userId') || '').split('_').slice(1).join('_');
                
                if (!userId) {
                    this.$message.warning('请先登录')
                    return
                }
                
                // 使用新的真实聊天历史API
                const chatData = {
                    user_id: userId,
                    notebook_name: notebookData || '默认本子',
                    scene_name: localStorage.getItem('sceneName') || '默认场景'
                }
                
                console.log('请求真实聊天历史:', chatData)
                
                const chatResponse = await getRealChatHistory(chatData)
                if (chatResponse && chatResponse.error_num === 0 && chatResponse.data) {
                    this.chatList = chatResponse.data
                    console.log('获取到真实聊天历史:', this.chatList)
                } else {
                    console.log('真实聊天历史为空，使用模拟数据')
                    this.loadMockData()
                    return
                }
                
                // 获取文件列表（从localStorage或其他地方）
                const files = localStorage.getItem('fileNameList')
                if (files) {
                    try {
                        this.fileNameList = JSON.parse(files)
                    } catch (e) {
                        this.fileNameList = []
                    }
                }
                
                // 获取场景信息
                this.sceneName = localStorage.getItem('sceneName') || 'AI技术研究'
                this.subSceneName = localStorage.getItem('subSceneName') || '基础概念学习'
                
                this.$message.success('真实数据加载成功')
            } catch (error) {
                console.error('加载真实数据失败:', error)
                this.$message.error('加载真实数据失败，使用模拟数据')
                this.loadMockData()
            } finally {
                this.isLoading = false
            }
        },
        
        // 加载模拟数据
        loadMockData() {
            this.chatList = [
                {
                    id: 1,
                    uid: '1001',
                    msg: '什么是人工智能？',
                    name: '用户',
                    time: '10:30',
                    chatType: 0
                },
                {
                    id: 2,
                    uid: '2000',
                    msg: '人工智能（AI）是计算机科学的一个分支，旨在创建能够执行通常需要人类智能的任务的系统。',
                    name: 'GPT-4',
                    time: '10:31',
                    chatType: 0
                },
                {
                    id: 3,
                    uid: '1001',
                    msg: '机器学习和深度学习有什么区别？',
                    name: '用户',
                    time: '10:32',
                    chatType: 0
                },
                {
                    id: 4,
                    uid: '2000',
                    msg: '机器学习是人工智能的一个子集，而深度学习是机器学习的一个子集。机器学习使用算法来学习数据中的模式，而深度学习使用多层神经网络来模拟人脑的工作方式。',
                    name: 'GPT-4',
                    time: '10:33',
                    chatType: 0
                }
            ]
            this.fileNameList = ['AI研究文档.pdf', '机器学习教程.docx']
            this.choosedCardIdList = []
        },
        
        // 添加模拟消息
        addMockMessage() {
            const messages = [
                { user: '神经网络是如何工作的？', ai: '神经网络通过模拟人脑神经元的工作方式来处理信息。它由多个层组成，每层包含多个神经元，通过权重和偏置来学习数据中的模式。' },
                { user: '什么是卷积神经网络？', ai: '卷积神经网络（CNN）是一种专门用于处理图像数据的深度学习架构，它使用卷积层来提取图像特征。' },
                { user: '如何训练一个深度学习模型？', ai: '训练深度学习模型通常包括：1）准备数据集，2）设计网络架构，3）选择损失函数，4）使用反向传播算法优化参数，5）验证和测试模型性能。' },
                { user: '什么是过拟合？', ai: '过拟合是指模型在训练数据上表现很好，但在新数据上表现较差的现象。这通常是因为模型过于复杂，记住了训练数据的细节而不是学习到一般规律。' },
                { user: '如何防止过拟合？', ai: '防止过拟合的方法包括：1）增加训练数据，2）使用正则化技术，3）减少模型复杂度，4）使用dropout，5）早停法等。' }
            ]
            
            const randomMsg = messages[Math.floor(Math.random() * messages.length)]
            const newId = this.chatList.length + 1
            
            this.chatList.push({
                id: newId,
                uid: '1001',
                msg: randomMsg.user,
                name: '用户',
                time: '10:3' + newId,
                chatType: 0
            })
            
            this.chatList.push({
                id: newId + 1,
                uid: '2000',
                msg: randomMsg.ai,
                name: 'GPT-4',
                time: '10:3' + (newId + 1),
                chatType: 0
            })
        },
        
        // 重置数据
        resetMockData() {
            this.loadMockData()
        },
        
        // 处理大脑行动
        handleBrainAction(action) {
            console.log('执行大脑行动:', action)
            
            switch (action.action_type) {
                case 'clarify':
                    this.$message.info('正在澄清问题，生成更具体的问题...')
                    this.addMockMessage()
                    break
                case 'explore':
                    this.$message.info('正在探索相关知识领域...')
                    // 可以在这里添加探索逻辑
                    break
                case 'activate':
                    this.$message.info('正在激活思维，生成新的问题...')
                    this.addMockMessage()
                    break
                case 'explore_gap':
                    this.$message.info('正在探索知识盲区...')
                    // 可以在这里添加盲区探索逻辑
                    break
                case 'organize':
                    this.$message.info('正在整理思路，生成卡片...')
                    // 可以在这里添加整理逻辑
                    break
                default:
                    this.$message.info(`执行行动: ${action.title}`)
            }
        }
    }
}
</script>
<style scoped lang="scss">
.brain-navigator-home {
    height: 100vh;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    
    .brain-header {
        padding: 0;
        height: 8vh;
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        display: flex;
        align-items: center;
        justify-content: space-between;
        
        .brain-title {
            color: white;
            text-align: center;
            flex: 1;
            
            h1 {
                font-size: 2rem;
                margin: 0;
                text-shadow: 0px 2px 4px rgba(0, 0, 0, 0.3);
            }
            
            p {
                font-size: 1rem;
                margin: 5px 0 0 0;
                opacity: 0.9;
            }
        }
    }
    
    .brain-main {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 20px;
        padding: 20px;
        height: 92vh;
        overflow: hidden;
        
        .chat-simulation-panel {
            background: white;
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0px 8px 32px rgba(0, 0, 0, 0.1);
            display: flex;
            flex-direction: column;
            
            .panel-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 20px;
                padding-bottom: 15px;
                border-bottom: 2px solid #f0f0f0;
                
                h3 {
                    margin: 0;
                    color: #333;
                    font-size: 1.2rem;
                }
                
                .control-buttons {
                    display: flex;
                    gap: 8px;
                }
            }
            
            .chat-list {
                flex: 1;
                overflow-y: auto;
                margin-bottom: 20px;
                max-height: 400px;
                
                .chat-item {
                    margin-bottom: 15px;
                    padding: 12px;
                    border-radius: 8px;
                    border-left: 4px solid;
                    
                    &.user {
                        background: #e3f2fd;
                        border-left-color: #2196f3;
                        margin-right: 20px;
                    }
                    
                    &.ai {
                        background: #f3e5f5;
                        border-left-color: #9c27b0;
                        margin-left: 20px;
                    }
                    
                    .msg-header {
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        margin-bottom: 8px;
                        
                        .msg-type {
                            font-weight: bold;
                            font-size: 0.9rem;
                        }
                        
                        .msg-time {
                            font-size: 0.8rem;
                            opacity: 0.7;
                        }
                    }
                    
                    .msg-content {
                        font-size: 0.95rem;
                        line-height: 1.4;
                    }
                }
            }
            
            .file-list, .card-list {
                margin-bottom: 15px;
                
                h4 {
                    margin: 0 0 10px 0;
                    color: #666;
                    font-size: 1rem;
                }
                
                .file-tags, .card-tags {
                    display: flex;
                    flex-wrap: wrap;
                    gap: 8px;
                    
                    .file-tag, .card-tag {
                        font-size: 0.8rem;
                    }
                }
            }
        }
        
        .navigator-panel {
            background: white;
            border-radius: 12px;
            box-shadow: 0px 8px 32px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }
    }
}

// 响应式设计
@media (max-width: 1200px) {
    .brain-navigator-home .brain-main {
        grid-template-columns: 1fr;
        grid-template-rows: 1fr 1fr;
    }
}

@media (max-width: 768px) {
    .brain-navigator-home {
        .brain-header .brain-title h1 {
            font-size: 1.5rem;
        }
        
        .brain-main {
            padding: 10px;
            gap: 10px;
        }
    }
}

// 滚动条样式
.chat-list::-webkit-scrollbar {
    width: 6px;
}

.chat-list::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 3px;
}

.chat-list::-webkit-scrollbar-thumb {
    background: #c1c1c1;
    border-radius: 3px;
}

.chat-list::-webkit-scrollbar-thumb:hover {
    background: #a8a8a8;
}
</style>