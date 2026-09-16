<template>
  <!-- 使用计算属性来判断是否是移动设备 -->
  <div class="chat-container" :class="{ 'mobile-view': isMobile }">
    <!-- 桌面端布局 -->
    <template v-if="!isMobile">
      <!-- 原有的完整布局代码 -->
      <!-- 左侧边栏 -->
      <div class="sidebar">
        <!-- 新对话按钮 -->
        <div class="new-chat-btn" @click="startNewChat">
          <el-button type="primary" class="new-chat-button">
            <el-icon><Plus /></el-icon>
            新对话
          </el-button>
        </div>

        <!-- 历史对话列表 -->
        <div class="chat-history">
          <div v-for="chat in chatHistory" 
              :key="chat.id" 
              :class="['history-item', { active: currentChatId === chat.id }]"
              @click="selectChat(chat.id)">
            <el-icon><ChatDotRound /></el-icon>
            <span class="chat-title">{{ chat.title }}</span>
            <el-button class="delete-btn" 
                      type="text" 
                      @click.stop="deleteChat(chat.id)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </div>

        <!-- 底部用户信息 -->
        <div class="user-info">
          <el-dropdown trigger="click">
            <div class="user-dropdown">
              <el-avatar size="small">{{ userInitial }}</el-avatar>
              <span class="username">{{ username }}</span>
            </div>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </div>

      <!-- 主聊天区域 -->
      <div class="main-content">
        <!-- 聊天头部 -->
        <div class="chat-header">
          <h2>{{ currentChat?.title || '新对话' }}</h2>
        </div>

        <!-- 消息列表 -->
        <div class="messages-container" ref="messagesContainer">
          <div v-if="currentMessages.length === 0" class="welcome-screen">
            <div class="welcome-content">
              <h1>NKCN·Brain最小屏幕听说通道</h1>
              <p>有任何问题都可以问我</p>
            </div>
            <div class="suggestion-grid">
              <div class="suggestion-card" v-for="(suggestion, index) in suggestions" 
                  :key="index" 
                  @click="usesuggestion(suggestion)">
                <el-icon><ChatLineRound /></el-icon>
                <span>{{ suggestion }}</span>
              </div>
            </div>
          </div>
          
          <template v-else>
            <div v-for="(message, index) in currentMessages" 
                :key="index" 
                :class="['message', message.role]">
              <div class="message-avatar">
                <el-avatar :size="36">
                  {{ message.role === 'user' ? userInitial : 'AI' }}
                </el-avatar>
              </div>
              <!-- 消息内容部分简化, 不再需要模型切换器 -->
              <div class="message-content">
                <!-- 显示使用的模型 -->
                <div v-if="message.role === 'assistant'" class="model-indicator">
                  <el-tag size="mini" type="info">{{ message.model || 'GPT4o' }}</el-tag>
                </div>
                
                <!-- 消息内容 -->
                <div class="message-text" v-html="formatMessage(message.content)"></div>

                <!-- 消息操作 -->
                <div class="message-actions" v-if="message.role === 'assistant'">
                  <el-button type="text" size="small" 
                            @click="copyMessage(message.content)">
                    <el-icon><Document /></el-icon> 
                    <span style="margin-left: 4px;">复制</span>
                  </el-button>
                </div>

                <!-- AI回复的模型切换器 -->
                <!-- <div v-if="message.role === 'assistant' && message.allResponses" 
                    class="model-switcher">
                  <el-radio-group 
                    :value="message.selectedModel"
                    @change="(val) => updateMessageModel(index, val)"
                    size="small">
                    <el-radio-button 
                      v-for="model in modelOptions" 
                      :key="model.id" 
                      :label="model.id">
                      {{ model.label }}
                    </el-radio-button>
                  </el-radio-group>
                </div> -->
                
                <!-- 消息内容 -->
                <!-- <div class="message-text" v-html="formatMessage(
                  message.role === 'assistant' && message.allResponses 
                    ? getModelResponse(message.allResponses, message.selectedModel) 
                    : message.content
                )"></div> -->

                <!-- 消息操作 -->
                <!-- <div class="message-actions" v-if="message.role === 'assistant'">
                  <el-button type="text" size="small" 
                            @click="copyMessage(
                              message.allResponses 
                                ? getModelResponse(message.allResponses, message.selectedModel) 
                                : message.content
                            )">
                    <el-icon><Document /></el-icon> 
                    <span style="margin-left: 4px;">复制</span>
                  </el-button>
                </div> -->
              </div>
            </div>
          </template>
        </div>

        <!-- 输入区域 -->
        <div class="input-container">
          <!-- 新增：在输入区域上方添加模型选择器 -->
          <!-- <div class="model-selector">
            <el-radio-group v-model="currentModel" size="small">
              <el-radio-button 
                v-for="model in modelOptions" 
                :key="model.id" 
                :label="model.id">
                {{ model.label }}
              </el-radio-button>
            </el-radio-group>
          </div> -->
          <ResponsiveModelSelector 
            :value="currentModel" 
            :modelOptions="modelOptionsNormal" 
            @input="handleModelChange"
          />

          <div class="chat-boxup-button-voice" @click="showSpeakDialog">
          </div>
          <div class="input-wrapper">
            <el-input
              v-model="userInput"
              type="textarea"
              :rows="isExpanded ? 10 : 3"
              class="chat-textarea"
              placeholder="输入消息，按Enter发送..."
              @keydown.enter.exact.prevent="handleEnter"
              @keydown.enter.shift.prevent="handleShiftEnter"
            />
            <div class="button-group">
              <el-button
                type="text"
                class="expand-button"
                @click="toggleExpand"
              >
                <el-icon>
                  <component :is="isExpanded ? 'ArrowDown' : 'ArrowUp'" />
                </el-icon>
              </el-button>
              <el-button 
                type="primary" 
                class="send-button" 
                :disabled="!userInput.trim() || isLoading"
                @click="sendMessage"
              >
                <el-icon>
                  <component :is="isLoading ? 'Loading' : 'Position'" />
                </el-icon>
              </el-button>
            </div>
          </div>
          <div class="input-footer">
            <span class="tip">按Enter发送，Shift+Enter换行</span>
          </div>
        </div>

      </div>
    </template>


    <!-- 移动端布局 -->
    <template v-else>
      <!-- 移动端的简化布局 -->
      <div class="mobile-header">
        <div class="left-buttons">
          <el-button 
            class="menu-button" 
            type="text"
            @click="toggleMobileMenu"
          >
            <el-icon><Menu /></el-icon>
          </el-button>
          <el-button 
            class="back-button" 
            type="text"
            @click="logout"
          >
            <el-icon><ArrowLeft /></el-icon>
          </el-button>
        </div>

        <h2 class="header-title">{{ currentChat?.title || '新对话' }}</h2>

        <div class="right-buttons">
          <el-button 
            class="new-chat-mobile" 
            type="text"
            @click="startNewChat"
          >
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 移动端侧边菜单 -->
      <div 
        v-show="showMobileMenu" 
        class="mobile-sidebar"
        @click.self="toggleMobileMenu"
      >
        <div class="mobile-menu-content">
          <div class="chat-history">
            <div 
              v-for="chat in chatHistory" 
              :key="chat.id" 
              :class="['history-item', { active: currentChatId === chat.id }]"
              @click="selectMobileChat(chat.id)"
            >
              <el-icon><ChatDotRound /></el-icon>
              <span class="chat-title">{{ chat.title }}</span>
              <el-button 
                class="delete-btn" 
                type="text" 
                @click.stop="deleteChat(chat.id)"
              >
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <!-- 移动端主内容区域 -->
      <div class="mobile-content">
        <!-- 消息列表 -->
        <div class="messages-container" ref="messagesContainer">
          <div v-if="currentMessages.length === 0" class="welcome-screen">
            <div class="welcome-content">
              <h1>NKCN·Brain最小屏幕听说</h1>
              <p>有任何问题都可以问我</p>
            </div>
            <div class="suggestion-grid">
              <div 
                class="suggestion-card" 
                v-for="(suggestion, index) in suggestions" 
                :key="index" 
                @click="usesuggestion(suggestion)"
              >
                <el-icon><ChatLineRound /></el-icon>
                <span>{{ suggestion }}</span>
              </div>
            </div>
          </div>
          
          <template v-else>
            <div v-for="(message, index) in currentMessages" 
                :key="index" 
                :class="['message', message.role]">
              <div class="message-avatar">
                <el-avatar :size="32">
                  {{ message.role === 'user' ? userInitial : 'AI' }}
                </el-avatar>
              </div>
              <!-- 消息内容部分简化, 不再需要模型切换器 -->
              <div class="message-content">
                <!-- 显示使用的模型 -->
                <div v-if="message.role === 'assistant'" class="model-indicator">
                  <el-tag size="mini" type="info">{{ message.model || 'GPT4o' }}</el-tag>
                </div>
                
                <!-- 消息内容 -->
                <div class="message-text" v-html="formatMessage(message.content)"></div>

                <!-- 消息操作 -->
                <div class="message-actions" v-if="message.role === 'assistant'">
                  <el-button type="text" size="small" 
                            @click="copyMessage(message.content)">
                    <el-icon><Document /></el-icon> 
                    <span style="margin-left: 4px;">复制</span>
                  </el-button>
                </div>

                <!-- 移动端模型切换器 -->
                <!-- <div v-if="message.role === 'assistant' && message.allResponses" 
                    class="mobile-model-switcher">
                  <el-select 
                    :value="message.selectedModel"
                    @change="(val) => updateMessageModel(index, val)"
                    size="small" 
                    class="model-select">
                    <el-option
                      v-for="model in modelOptions"
                      :key="model.id"
                      :label="model.label"
                      :value="model.id">
                    </el-option>
                  </el-select>
                </div> -->
                
                <!-- 消息内容 -->
                <!-- <div class="message-text" v-html="formatMessage(
                  message.role === 'assistant' && message.allResponses 
                    ? getModelResponse(message.allResponses, message.selectedModel) 
                    : message.content
                )"></div> -->

                <!-- 消息操作 -->
                <!-- <div class="message-actions" v-if="message.role === 'assistant'">
                  <el-button type="text" size="small" 
                            @click="copyMessage(
                              message.allResponses 
                                ? getModelResponse(message.allResponses, message.selectedModel) 
                                : message.content
                            )">
                    <el-icon><Document /></el-icon>
                    <span style="margin-left: 4px;">复制</span>
                  </el-button>
                </div> -->
              </div>
            </div>
          </template>
        </div>

        <!-- 移动端输入区域 -->
        <div class="mobile-input">
          <!-- 新增：在输入区域上方添加模型选择器 -->
          <!-- <div class="model-selector">
            <el-radio-group v-model="currentModel" size="small">
              <el-radio-button 
                v-for="model in modelOptions" 
                :key="model.id" 
                :label="model.id">
                {{ model.label }}
              </el-radio-button>
            </el-radio-group>
          </div> -->
          <ResponsiveModelSelector 
            :value="currentModel" 
            :modelOptions="modelOptionsNormal" 
            @input="handleModelChange"
          />

          <div class="chat-boxup-button-voice" @click="showSpeakDialog">
          </div>
          <div class="input-wrapper">
            <el-input
              v-model="userInput"
              type="textarea"
              :rows="isExpanded ? 8 : 1"
              class="chat-textarea"
              placeholder="输入消息..."
              @keydown.enter.exact.prevent="handleEnter"
              @keydown.enter.shift.prevent="handleShiftEnter"
            />
            <div class="button-group">
              <el-button
                type="text"
                class="expand-button"
                @click="toggleExpand"
              >
                <el-icon>
                  <component :is="isExpanded ? 'ArrowDown' : 'ArrowUp'" />
                </el-icon>
              </el-button>
              <el-button 
                type="primary" 
                class="send-button" 
                :disabled="!userInput.trim() || isLoading"
                @click="sendMessage"
              >
                <el-icon>
                  <component :is="isLoading ? 'Loading' : 'Position'" />
                </el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <ASRVoice style="display: none;" ref="ASRVoice" :identifyStatus="true" :showIdentifyTextStatus="true"
      @voiceRecognitionTextChanged="updateVoiceRecognitionText"
      @voiceRecognitionBreaked="updateVoiceRecognitionStatus" />
    <audio ref="audioElement" controls style="display: none;"></audio>

    <!-- 类似chatgpt的语音对话界面 -->
    <!-- 根据设备类型显示不同的对话框 -->
    <!-- 桌面端对话框 -->
    <el-dialog v-if="!isMobile"
      v-model="dialogSpeakVisible" 
      width="30%" 
      class="myDialogSpeak"
      :close-on-press-escape="false" 
      :close-on-click-modal="false" 
      :before-close="handleSpeakClose"
      style="background-color: rgba(105, 160, 137, 0.2);"
    >
      <div class="chat-boxup-button-voice" 
          :class="{ 'chat-boxup-button-voice-ban': voiceStatus !== 1 }" 
          :ref="chatBoxUpButtonVoice"
          @click="showVoice">
      </div>
      <!-- 下拉框 -->
      <div class="dropdown-container" :class="{ 'mobile': isMobile }">
        <div class="custom-select-wrapper" @click="toggleDropdown">
          <div class="custom-select-display">
            <span>{{ selectedOptionLabel || '请选择' }}</span>
          </div>
          <div class="custom-select-options" v-if="isOpen">
            <div
              v-for="option in options"
              :key="option.value"
              :class="{ 'is-selected': option.value === selectedOption }"
              @click="selectOption(option)"
              class="custom-select-option"
            >
              {{ option.label }}
            </div>
          </div>
        </div>
        <div class="emotion-select-wrapper" @click="toggleEmotionDropdown">
          <div class="emotion-select-display">
            <span>{{ selectedEmotionOptionLabel || '请选择' }}</span>
          </div>
          <div class="emotion-select-options" v-if="isEmotionOpen">
            <div
              v-for="option in currentOptions"
              :key="option.value"
              :class="{ 'is-selected': option.value === selectedEmotionOption }"
              @click="selectEmotionOption(option)"
              class="emotion-select-option"
            >
              {{ option.label }}
            </div>
          </div>
        </div>
      </div>

      <!-- <transition name="fade">
        <video style="width: 700px; height: 394px; margin-top: 25px; border-radius: 200px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.4); position: absolute;" 
            autoplay muted loop
            v-if="voiceStatus===1"
            src="@/assets/img/chatwindow/listening.mp4" alt="Listening" />
      </transition> -->
      <!-- 视频显示区域 -->
      <div class="video-container" :class="{ 'mobile': isMobile }">
        <video :class="['status-video', { 'mobile': isMobile }]" 
            autoplay muted loop
            v-if="voiceStatus===1"
            src="@/assets/img/chatwindow/listening.mp4" 
            alt="Listening" />
        <video :class="['status-video', { 'mobile': isMobile }]" 
            autoplay muted loop
            v-if="voiceStatus===0 || voiceStatus===2"
            src="@/assets/img/chatwindow/thinking.mp4" 
            alt="Thinking" />
        <video :class="['status-video', { 'mobile': isMobile }]" 
            autoplay muted loop
            v-if="voiceStatus===3"
            src="@/assets/img/chatwindow/speaking.mp4" 
            alt="Speaking" />
      </div>

      <!-- 状态文本 -->
      <div :class="['status-text', { 'mobile': isMobile }]" 
          v-if="voiceStatus === 0">正在准备，请等几秒</div>
      <div :class="['status-text', { 'mobile': isMobile }]" 
          v-if="voiceStatus === 1">我正在听您说话</div>
      <div :class="['status-text', { 'mobile': isMobile }]" 
          v-if="voiceStatus === 2">我正在思考，请稍等</div>
      <div :class="['status-text', { 'mobile': isMobile }]" 
          v-if="voiceStatus === 3">请听我回答您</div>
    </el-dialog>


    <!-- 移动端对话框 -->
    <div v-else
      v-show="dialogSpeakVisible"
      class="mobile-dialog"
    >
      <div class="mobile-dialog-content">
        <!-- 关闭按钮 -->
        <button class="mobile-dialog-close" @click="handleSpeakClose">
          ×
        </button>
        
        <!-- 对话框内容 -->
        <div class="chat-boxup-button-voice" 
            :class="{ 'chat-boxup-button-voice-ban': voiceStatus !== 1 }" 
            :ref="chatBoxUpButtonVoice"
            @click="showVoice">
        </div>
        <!-- 下拉框 -->
        <div class="dropdown-container" :class="{ 'mobile': isMobile }">
          <div class="custom-select-wrapper" @click="toggleDropdown">
            <div class="custom-select-display">
              <span>{{ selectedOptionLabel || '请选择' }}</span>
            </div>
            <div class="custom-select-options" v-if="isOpen">
              <div
                v-for="option in options"
                :key="option.value"
                :class="{ 'is-selected': option.value === selectedOption }"
                @click="selectOption(option)"
                class="custom-select-option"
              >
                {{ option.label }}
              </div>
            </div>
          </div>
          <div class="emotion-select-wrapper" @click="toggleEmotionDropdown">
            <div class="emotion-select-display">
              <span>{{ selectedEmotionOptionLabel || '请选择' }}</span>
            </div>
            <div class="emotion-select-options" v-if="isEmotionOpen">
              <div
                v-for="option in currentOptions"
                :key="option.value"
                :class="{ 'is-selected': option.value === selectedEmotionOption }"
                @click="selectEmotionOption(option)"
                class="emotion-select-option"
              >
                {{ option.label }}
              </div>
            </div>
          </div>
        </div>

        <!-- <transition name="fade">
          <video style="width: 700px; height: 394px; margin-top: 25px; border-radius: 200px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.4); position: absolute;" 
              autoplay muted loop
              v-if="voiceStatus===1"
              src="@/assets/img/chatwindow/listening.mp4" alt="Listening" />
        </transition> -->
        <!-- 视频显示区域 -->
        <div class="video-container" :class="{ 'mobile': isMobile }">
          <video :class="['status-video', { 'mobile': isMobile }]" 
              autoplay muted loop
              v-if="voiceStatus===1"
              src="@/assets/img/chatwindow/listening.mp4" 
              alt="Listening" />
          <video :class="['status-video', { 'mobile': isMobile }]" 
              autoplay muted loop
              v-if="voiceStatus===0 || voiceStatus===2"
              src="@/assets/img/chatwindow/thinking.mp4" 
              alt="Thinking" />
          <video :class="['status-video', { 'mobile': isMobile }]" 
              autoplay muted loop
              v-if="voiceStatus===3"
              src="@/assets/img/chatwindow/speaking.mp4" 
              alt="Speaking" />
        </div>

        <!-- 状态文本 -->
        <div :class="['status-text', { 'mobile': isMobile }]" 
            v-if="voiceStatus === 0">正在准备，请等几秒</div>
        <div :class="['status-text', { 'mobile': isMobile }]" 
            v-if="voiceStatus === 1">我正在听您说话</div>
        <div :class="['status-text', { 'mobile': isMobile }]" 
            v-if="voiceStatus === 2">我正在思考，请稍等</div>
        <div :class="['status-text', { 'mobile': isMobile }]" 
            v-if="voiceStatus === 3">请听我回答您</div>
      </div>
    </div>

    <!-- 自定义遮罩层 -->
    <transition name="fade">
      <div v-if="dialogSpeakVisible" class="custom-backdrop"></div>
    </transition>
  </div>
</template>

<script>
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElRadioGroup, ElRadioButton, ElIcon } from 'element-plus'
import { Delete, Loading, Position, Plus, ChatDotRound, Document, ChatLineRound, ArrowUp, ArrowDown, ArrowLeft, Menu } from '@element-plus/icons-vue'
import { chat_send_onlytext, chat_send_onlytext_stream } from "@/api/chat/send_message"
import { loadUserSimplify } from "@/views/pages/mainHome/my_js";
import { marked } from 'marked'
import { test_get_speech_text } from '@/api/test'
import { getModel } from "@/api/getData"
import { modelManager } from '@/utils/ModelManager.js';
import { API_BASE_URL } from '@/config/apiConfig';
import router from '@/router'
import ASRVoice from '@/components/xftest.vue'
import ResponsiveModelSelector from '@/components/chatWindow/ResponsiveModelSelector.vue'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css'

export default {
  name: 'SimpleHome',
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    ElRadioGroup,
    ElRadioButton,
    ElIcon,
    Delete,
    Loading,
    Position,
    Plus,
    ChatDotRound,
    Document,
    ChatLineRound,
    ArrowUp,
    ArrowDown,
    ArrowLeft,
    Menu,
    ASRVoice,
    ResponsiveModelSelector
  },
  data() {
    return {
      // 新增：当前选中的模型
      currentModel: 'GPT4o', // 默认选中GPT4o

      chatHistory: [],
      currentChatId: null,
      currentMessages: [],
      userInput: '',
      isLoading: false,
      username: localStorage.getItem('realName') || '用户',
      suggestions: [
        "最近有什么值得我回顾？",
        "把这些完整地串起来吧",
        "从我的摘要中找找相关灵感",
        "整理下我近期的思考脉络"
      ],
      isExpanded: false, // 添加这个控制输入框展开状态
      // 是否移动设备
      isMobile: false,
      showMobileMenu: false,
      
      modelOptions: [
        { id: 'GPT4', label: 'GPT-4' },
        // { id: 'Mixtral8x7B', label: 'Mixtral 8x7B' },
        { id: 'Llama3', label: 'Llama 3' },
        { id: 'Kimi', label: 'Kimi' },
        { id: 'Claude3.5', label: 'Claude 3.5' },
        { id: 'Deepseek', label: 'Deepseek' },
        { id: 'Deepseek-reasoner', label: 'Deepseek-reasoner' },
        { id: 'Gemini', label: 'Gemini' },
        { id: 'Qwq', label: 'Qwq' },
      ],

      modelOptionsNormal: [
        { id: 'GPT4o', label: 'gpt-4o' },
        { id: 'claude-3.5', label: 'claude-3-5-sonnet-20241022' },
        { id: 'DeepSeekV3', label: 'deepseek-chat-0324' },
        { id: 'DeepseekR1', label: 'deepseek-r1-0528-Aliyun' },
        { id: 'claude-3.7', label: 'claude-3-7-sonnet-20250219' },
        { id: 'Gemini', label: 'gemini-2.5-pro-exp-03-25' },
        { id: 'kimi', label: 'moonshot-v1-8k' },
        { id: 'Llama3', label: 'meta/llama-3.1-405b-instruct' },
        { id: 'Llama4', label: 'meta/llama-4-maverick-17b-128e-instruct' },
        { id: 'Qwq', label: 'qwq-plus' },
        // { id: 'Grok', label: 'grok-beta' },
        // { id: 'GLM', label: 'glm-4-flash' },
        // { id: 'GLM-long', label: 'glm-4-long' },
        // { id: 'Grok-r', label: 'grok-3-reasoner' },
        { id: 'claude-4-opus', label: 'claude-opus-4-20250514' },
        { id: 'claude-4-sonnet', label: 'claude-sonnet-4-20250514' },
        { id: 'DeepseekR1-tencent', label: 'deepseek-r1-0528-Tencent' },
      ],

      voiceRecognizing: false,  // 正在语音识别
      voiceRecognitionText: '',
      isListening: false,
      isSpeaking: false,
      audioContext: null,
      analyser: null,
      microphone: null,
      justCutSpeak: false,
      justCloseSpeak: false,
      voiceStatus: 0,
      dialogSpeakVisible: false,
      isOpen: false,
      selectedOption: 'BV700_V2_streaming',
      selectedOptionLabel: '灿灿 2.0',
      options: [
        { value: 'BV700_V2_streaming', label: '灿灿 2.0' },
        { value: 'BV701_V2_streaming', label: '擎苍 2.0' },
        { value: 'BV705_streaming', label: '炀炀' },
        { value: 'BV405_streaming', label: '甜美小源' },
        { value: 'BV009_streaming', label: '知性女声' },
        { value: 'BV008_streaming', label: '亲切男声' },
        // 更多选项...
      ],
      isEmotionOpen: false,
      selectedEmotionOption: 'no',
      selectedEmotionOptionLabel: '通用',
      emotionCanCanOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },
        { value: 'annoyed', label: '嗔怪' },
        { value: 'happy', label: '开心' },
        { value: 'angry', label: '愤怒' },
        { value: 'hate', label: '厌恶' },
        { value: 'surprise', label: '惊讶' },
        { value: 'sad', label: '悲伤' },
        { value: 'scare', label: '害怕' },
        { value: 'tear', label: '哭腔' },
        { value: 'customer_service', label: '客服' },
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' },
        { value: 'tsundere', label: '傲娇' },
        { value: 'comfort', label: '安慰鼓励' },
        { value: 'conniving', label: '绿茶' },
        { value: 'charming', label: '娇媚' },
        { value: 'radio', label: '情感电台' },
        { value: 'lovey-dovey', label: '撒娇' },
        { value: 'yoga', label: '瑜伽' },
        { value: 'storytelling', label: '讲故事' }
      ],
      emotionQingCangOptions: [
        { value: 'narrator', label: '旁白-舒缓' },
        { value: 'narrator_immersive', label: '旁白-沉浸' },
        { value: 'novel_dialog', label: '平和' },
        { value: 'happy', label: '开心' },
        { value: 'angry', label: '愤怒' },
        { value: 'hate', label: '厌恶' },
        { value: 'surprise', label: '惊讶' },
        { value: 'sad', label: '悲伤' },
        { value: 'scare', label: '害怕' },
        { value: 'tear', label: '哭腔' }
      ],
      emotionYangYangOptions: [
        { value: 'no', label: '通用' },
        { value: 'chat', label: '自然对话' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },
        { value: 'annoyed', label: '嗔怪' },
        { value: 'comfort', label: '安慰鼓励' },
        { value: 'storytelling', label: '讲故事' }
      ],
      emotionTianMeiXiaoYuanOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },        
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' }
      ],
      emotionZhiXingGirlOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },        
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' }
      ],
      emotionQinQieBoyOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },        
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' }
      ],
    }
  },
  created() {
    if(localStorage.getItem('byadmin') === 'true' || localStorage.getItem('byuplevel') === 'true') {
      localStorage.setItem('fromPath', '/home')
      router.push('/home');
    } else {
      // 初始化时检测设备类型, 添加窗口大小变化监听
      localStorage.setItem('home2login', 'false');
      this.checkDevice()
      window.addEventListener('resize', this.checkDevice)
      this.loadUserSim()
      this.startNewChat()
      // 新增：动态加载模型列表
      this.loadModelOptions();
    }
  },
  mounted() {
    this.audioElement = this.$refs.audioElement; // 设置播放tts音频的变量
  },
  beforeDestroy() {
    // 移除监听器
    window.removeEventListener('resize', this.checkDevice)
  },
  computed: {
    userInitial() {
      return this.username.charAt(0).toUpperCase()
    },
    currentChat() {
      return this.chatHistory.find(chat => chat.id === this.currentChatId)
    },
    currentOptions() {
      switch (this.selectedOptionLabel) {
        case '灿灿 2.0':
          return this.emotionCanCanOptions;
        case '擎苍 2.0':
          return this.emotionQingCangOptions;
        case '炀炀':
          return this.emotionYangYangOptions;
        case '甜美小源':
          return this.emotionTianMeiXiaoYuanOptions;
        case '知性女声':
          return this.emotionZhiXingGirlOptions;
        case '亲切男声':
          return this.emotionQinQieBoyOptions;
        default:
          return this.emotionCanCanOptions;
      }
    },
  },
  methods: {
    loadModelOptions() {
      let models = getModel();

      if (models && models.length > 0) {
        // 转换数据格式：name -> id, detail -> label
        this.modelOptionsNormal = models.map(model => ({
          id: model.name,      // name 字段对应 id
          label: model.detail  // detail 字段对应 label
        }));
        
        console.log('成功获取模型列表:', this.modelOptionsNormal);
      } else {
        console.warn('获取到的模型列表为空，使用默认配置');
      }
    },
    // 更新：切换模型
    handleModelChange(newValue) {
      this.currentModel = newValue;
      console.log('父组件接收到新值:', newValue);
    },

    toggleDropdown() {
      this.isOpen = !this.isOpen;
    },
    selectOption(option) {
      this.selectedOption = option.value;
      this.selectedOptionLabel = option.label;
      this.isOpen = false;
      event.stopPropagation(); // 阻止事件冒泡到wrapper又变成true
    },
    toggleEmotionDropdown() {
      this.isEmotionOpen = !this.isEmotionOpen;
    },
    selectEmotionOption(option) {
      this.selectedEmotionOption = option.value;
      this.selectedEmotionOptionLabel = option.label;
      this.isEmotionOpen = false;
      event.stopPropagation(); // 阻止事件冒泡到wrapper又变成true
    },
    stopListening() {
      this.isSpeaking = false; // 重置状态
      this.isListening = false; // 重置标志位
      if (this.microphone) {
        const tracks = this.microphone.mediaStream.getTracks();
        tracks.forEach(track => track.stop()); // 停止音频轨道
        this.microphone = null; // 清理引用
      }
      if (this.audioContext) {
        this.audioContext.close(); // 关闭音频上下文
        this.audioContext = null;
      }
    },
    async startListening() {
      // if (this.audioContext) {
      //   this.stopListening(); // 如果正在检测，先停止
      // }
      // 检查浏览器是否支持 getUserMedia
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        try {
          // 创建音频上下文
          this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
          // 获取麦克风输入
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          this.microphone = this.audioContext.createMediaStreamSource(stream);
          this.analyser = this.audioContext.createAnalyser();
          this.microphone.connect(this.analyser);
          this.analyser.fftSize = 2048;

          // 创建低通和高通滤波器，只听取人声，过滤环境音和待打断的系统音
          const lowPassFilter = this.audioContext.createBiquadFilter();
          lowPassFilter.type = 'lowpass';
          lowPassFilter.frequency.setValueAtTime(3400, this.audioContext.currentTime); // 高通滤波器，去除3400Hz以上的频率

          const highPassFilter = this.audioContext.createBiquadFilter();
          highPassFilter.type = 'highpass';
          highPassFilter.frequency.setValueAtTime(300, this.audioContext.currentTime); // 低通滤波器，去除300Hz以下的频率

          // 将麦克风音频连接到滤波器
          this.microphone.connect(lowPassFilter);
          lowPassFilter.connect(highPassFilter);
          highPassFilter.connect(this.analyser);
          
          // 开启检测声音
          this.isListening = true; // 设置为正在监听
          this.detectSound();
        } catch (error) {
          console.error('获取麦克风失败:', error);
          this.$message.error('获取麦克风失败');
        }
      } else {
        this.$message.error('您的浏览器不支持音频输入');
      }
    },
    detectSound() {
      const bufferLength = this.analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      const checkSound = () => {
        if (!this.isListening) return; // 检查标志位

        this.analyser.getByteFrequencyData(dataArray);
        // 检测声音分贝
        const average = dataArray.reduce((sum, value) => sum + value) / bufferLength;
        if (average > 35) { // 根据需要调整这个阈值
          // 声音超过35分贝，就模拟点击一下打断TTS说话，停止打断检测，准备打断后重新进入听阶段
          // this.stopListening()
          this.showVoice()
          if (this.audioContext) {
            this.audioContext.close(); // 关闭音频上下文
            this.audioContext = null;
          }
          this.isListening = false; // 停止检测
          return; // 退出检测
        } else {
          this.isSpeaking = false;
        }

        requestAnimationFrame(checkSound);
      };

      checkSound();
    },
    handleSpeakClose() {
      if(this.voiceStatus !== 0) {
        if(this.voiceStatus === 2) {
          this.$message.error('我还在思考，请听我回答后再决定退出');
        } else {
          this.$message.success('语音听说对话即将结束');
          this.dialogSpeakVisible = false
          this.stopListening();
          this.$refs.ASRVoice.closeVoice();
          this.voiceRecognizing = false;
          this.audioElement.pause();
          this.justCloseSpeak = true
          setTimeout(() => { 
            this.justCloseSpeak = false
          }, 3000); 
        }
      } else {
        this.$message.error('请您等3秒后，初始化完成才可退出');
      }
    },
    showSpeakDialog() {
      if(this.justCloseSpeak === false) {
        this.dialogSpeakVisible = true
        this.voiceRecognizing = false
        this.voiceRecognitionText = ''
        this.voiceStatus = 0
        // 打开语音界面后 2000 毫秒执行，如果2s后用户还没自己点击左上角控制按钮 ，就帮用户自动模拟点击一次
        setTimeout(() => { 
          if(this.voiceStatus === 0) {
            this.showVoice()
          }
        }, 2000); 
      } else {
        this.$message.error('请您等3秒缓冲后，再重新进入听说通道');
      }
    },
    showVoice() {
      if(this.voiceStatus !== 2 && this.justCutSpeak !== true) {
        if(this.selectedEmotionOption === null || this.selectedEmotionOptionLabel === '' || this.selectedOption === null || this.selectedOptionLabel === '') {
          this.$message.error('您还未选音色及情感，请选好后再开始对话哦');
        } 
        else {
          if(this.voiceStatus === 0)
            this.voiceStatus = 1
          else
            this.voiceStatus = 0

          // 更改为开始录音的逻辑
          // this.showVoiceChecked = true;
          if (!this.voiceRecognizing) {
            //没有在识别，点击后开启识别
            this.$message.success('您可以开始说话了');
            this.$refs.ASRVoice.openVoice();
            this.voiceRecognizing = true;
          } else {
            // 已经在识别，点击后停止识别
            this.isListening = false; // 停止打断检测
            this.$refs.ASRVoice.closeVoice();
            this.voiceRecognizing = false;
            this.audioElement.pause();
            this.voiceRecognitionText = ''
            // 等close结束，模拟再点一下，重新open开始录音
            this.justCutSpeak = true
            setTimeout(() => { 
              this.justCutSpeak = false
              this.showVoice();
            }, 1000); 
          }
        }
      } else if(this.justCutSpeak === true) {
        this.$message.error('打断需等待1秒，然后您可以开始说话');
      } else {
        this.$message.error('我还在思考，请稍后先听我回答，再决定是否重新开始对话');
      }
    },

    updateVoiceRecognitionText(newText) {
      // this.voiceRecognitionText = newText;
      this.userInput = newText;
    },
    updateVoiceRecognitionStatus() {
      setTimeout(() => {
        if (this.userInput === "") {
          console.log('this.userInput is an empty string.');
          return; // 空的直接返回
        }
        if (this.voiceRecognizing === false) {
          console.log('ASR is closed');
          return; // 已经关闭了直接返回
        }
        let voiceinput = this.userInput;
        
        const userMessage = {
          role: 'user',
          content: this.userInput.trim()
        }

        // 将用户消息添加到当前对话
        this.currentMessages.push(userMessage)
        const currentChat = this.chatHistory.find(c => c.id === this.currentChatId)
        if (currentChat) {
          currentChat.messages = [...this.currentMessages]
          // 更新对话标题为第一条消息的前20个字符
          if (currentChat.messages.length === 1) {
            currentChat.title = userMessage.content.slice(0, 20) + (userMessage.content.length > 20 ? '...' : '')
          }
        }
        this.userInput = "";

        this.voiceStatus = 2
        let formData = new FormData()
        formData.append('username', localStorage.getItem('realName') + "_virtualBook4SimpleUI");
        formData.append('message', voiceinput);
        formData.append('background', '');
        formData.append('role', this.selectedOption);
        formData.append('emotion', this.selectedEmotionOption);
        formData.append('rounds', 3);
        // TODO语音：把这里的地址改了，再上传服务器
        fetch(`${API_BASE_URL}/api/asr_chat_send`,
          {
            method: 'POST',
            body: formData,
          })
          .then(response => {
            if (response.ok) {
              console.log('response ok，转换为blob');
              return response.blob();
            }
            throw new Error('Network response was not ok.');
          })
          .then(blob => {
            const audioURL = URL.createObjectURL(blob);
            this.audioElement.src = audioURL;
            let text_formData = new FormData();
            text_formData.append('username', localStorage.getItem('realName') + "_virtualBook4SimpleUI");
            test_get_speech_text(text_formData).then(response => {
              let response_text = response['response_text'];
              const all_content = [
                response_text,  // GPT4o's response at index 0
                "",            // Empty string at index 1
                "",            // Empty string at index 2
                ""             // Empty string at index 3
              ];
              const aiMessage = {
                role: 'assistant',
                content: all_content[0], // 默认显示GPT4的回复
                allResponses: all_content, // 存储所有模型的回复
                selectedModel: 'GPT4' // 每条消息独立的选中模型
              };

              this.currentMessages.push(aiMessage)
              
              // 同步更新历史记录
              if (currentChat) {
                currentChat.messages = [...this.currentMessages]
              }
            });
            this.audioElement.addEventListener('ended', () => {
              if(this.voiceRecognizing === true) {
                this.isListening = false; // 停止打断检测
                this.voiceStatus = 1
                this.$refs.ASRVoice.openVoice(); // 继续下一轮的识别
              }
            });
            this.voiceStatus = 3
            this.audioElement.play();           // 播放音频
            this.startListening();
            // this.audioElement.play().then(() => {
            //   this.$refs.ASRVoice.openVoice();//继续下一轮的识别
            // }).catch((error) => {
            //   // 播放过程中可能发生的错误处理
            //   console.error("Error playing audio:", error);
            // });;
          })
          .catch(error => {
            // 处理错误
            console.error('There has been a problem with your fetch operation:', error);
          });
      }, 2000);
    },

    // 检测设备类型
    checkDevice() {
      this.isMobile = window.innerWidth <= 768
    },
    // 移动端专用方法
    toggleMobileMenu() {
      this.showMobileMenu = !this.showMobileMenu
    },
    selectMobileChat(chatId) {
      this.selectChat(chatId)
      this.showMobileMenu = false
    },
    // 处理Enter键
    handleEnter(e) {
      if (!this.isLoading && this.userInput.trim()) {
        this.sendMessage()
      }
    },
    handleShiftEnter(e) {
      this.userInput += '\n'
    },
    // 切换输入框展开/收起状态
    toggleExpand() {
      this.isExpanded = !this.isExpanded
    },
    logout() {
      // 改：退出时清空接入的模型信息缓存
      localStorage.removeItem('modelManagerCache'); 
      console.log('已清空ModelManager缓存');
      localStorage.removeItem('modelList'); 
      console.log('已清空模型缓存');
      modelManager.init().catch(err => {
          console.error('模型管理器自动初始化失败:', err);
      });

      localStorage.setItem('home2login', 'true');
      router.push('/');
    },
    loadUserSim() {
      let uname = localStorage.getItem('realName') + "_virtualBook4SimpleUI";
      loadUserSimplify(uname).then(response => {
        if (response.error_num === 0) {
          this.$message.success('用户数据底座加载成功！');
        } else {
          this.$message.error('用户数据底座加载发生了一点错误，您可能需要重新登陆再试：' + response.msg);
        }
      }).catch(error => {
        console.log(error);
        this.$message.error('用户数据底座加载发生了一点错误，您可能需要重新登陆再试：' + error);
      });
    },
    startNewChat() {
      const newChat = {
        id: Date.now(), // 使用时间戳作为唯一ID
        title: '新对话',
        messages: []
      }
      this.chatHistory.unshift(newChat)
      this.selectChat(newChat.id)
      this.userInput = ''
    },
    selectChat(chatId) {
      if (this.currentChatId === chatId) return // 如果点击当前对话，不做任何操作
    
      this.currentChatId = chatId
      const selectedChat = this.chatHistory.find(chat => chat.id === chatId)
      if (selectedChat) {
        this.currentMessages = [...selectedChat.messages] // 使用浅拷贝来避免直接引用
        this.userInput = '' // 清空输入框
        
        this.$nextTick(() => {
          this.scrollToBottom()
        })
      }
    },
    deleteChat(chatId) {
      const index = this.chatHistory.findIndex(c => c.id === chatId)
      if (index > -1) {
        this.chatHistory.splice(index, 1)
        if (this.currentChatId === chatId) {
          if (this.chatHistory.length > 0) {
            this.selectChat(this.chatHistory[0].id)
          } else {
            this.startNewChat()
          }
        }
      }
    },
    // 获取指定模型的回复内容
    getModelResponse(allContent, modelName) {
      const modelIndex = {
        'GPT4': 0,
        // 'Mixtral8x7B': 3,
        'Llama3': 1,
        'Kimi': 2,
        'Claude3.5': 3,
        'Deepseek': 4,
        'Deepseek-reasoner': 5
      };
      return allContent[modelIndex[modelName]] || '';
    },
    // 更新特定消息的选中模型
    updateMessageModel(messageIndex, newModel) {
      if (this.currentMessages[messageIndex].role === 'assistant') {
        this.currentMessages[messageIndex].selectedModel = newModel;
        
        // 同步更新历史记录
        const currentChat = this.chatHistory.find(c => c.id === this.currentChatId);
        if (currentChat) {
          currentChat.messages = [...this.currentMessages];
        }
      }
    },
    async sendMessage() {
      if (!this.userInput.trim()) return

      const userMessage = {
        role: 'user',
        content: this.userInput.trim()
      }

      // 将用户消息添加到当前对话
      this.currentMessages.push(userMessage)
      const currentChat = this.chatHistory.find(c => c.id === this.currentChatId)
      if (currentChat) {
        currentChat.messages = [...this.currentMessages]
        // 更新对话标题为第一条消息的前20个字符
        if (currentChat.messages.length === 1) {
          currentChat.title = userMessage.content.slice(0, 20) + (userMessage.content.length > 20 ? '...' : '')
        }
      }

      // 后端AI响应
      // try {
      //   let formData = new FormData()
      //   formData.append('message', this.userInput);
      //   formData.append('realName', localStorage.getItem('realName'));
      //   formData.append('username', localStorage.getItem('realName') + "_virtualBook4SimpleUI");
      //   formData.append('model', this.currentModel); // 新增：传递选中的模型

      //   // 清空输入
      //   this.userInput = ''
      //   this.isLoading = true

      //   chat_send_onlytext(formData)
      //     .then(response => {
      //       if (response.error_num === 0) {
      //         this.$message.success('发送成功！');
      //       } else {
      //         this.$message.error('发送失败，请重试！');
      //         console.log(response['msg']);
      //       }
      //       // 创建包含所有模型回复的AI消息
      //       // let all_content = response['content'];
      //       // const aiMessage = {
      //       //   role: 'assistant',
      //       //   content: all_content[0], // 默认显示GPT4o的回复
      //       //   allResponses: all_content, // 存储所有模型的回复
      //       //   selectedModel: 'GPT4o' // 每条消息独立的选中模型
      //       // };

      //       // 修改：现在只返回单个模型的回复
      //       const aiMessage = {
      //         role: 'assistant',
      //         content: response['content'],
      //         model: this.currentModel // 记录使用的模型
      //       };

      //       this.currentMessages.push(aiMessage)
            
      //       // 同步更新历史记录
      //       if (currentChat) {
      //         currentChat.messages = [...this.currentMessages]
      //       }
            
      //       this.isLoading = false
      //       this.$nextTick(() => {
      //         this.scrollToBottom()
      //       })
      //     })
      // } catch (error) {
      //   console.error('Error:', error)
      //   this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + error);
      //   this.isLoading = false
      // }
      // 后端AI响应 - 改为流式处理
      try {
        let formData = new FormData()
        formData.append('message', this.userInput);
        formData.append('realName', localStorage.getItem('realName'));
        formData.append('username', localStorage.getItem('realName') + "_virtualBook4SimpleUI");
        formData.append('model', this.currentModel); // 传递选中的模型

        // 清空输入
        const currentMessage = this.userInput; // 保存当前消息用于错误处理
        this.userInput = ''
        this.isLoading = true

        // 创建AI消息对象，先添加到消息列表
        const aiMessage = {
          role: 'assistant',
          content: '',
          model: this.currentModel
        };
        this.currentMessages.push(aiMessage);

        chat_send_onlytext_stream(formData)
          .then(response => {
            const reader = response.body.getReader();
            const decoder = new TextDecoder('utf-8');
            
            const processStream = () => {
              reader.read().then(({done, value}) => {
                if (done) {
                  this.isLoading = false;
                  console.log('Stream reading complete');
                  console.log('最终AI消息内容:', aiMessage.content); // 添加这行
                  
                  // 同步更新历史记录
                  const currentChat = this.chatHistory.find(chat => chat.id === this.currentChatId);
                  if (currentChat) {
                    currentChat.messages = [...this.currentMessages]
                  }
                  
                  this.$nextTick(() => {
                    this.scrollToBottom()
                  });
                  return;
                }
                
                const resp = decoder.decode(value);
                console.log('收到原始数据:', resp);

                // 【恢复正则匹配】使用正则表达式匹配和提取每个独立的 JSON 对象
                const jsonObjects = resp.match(/{[\s\S]*?}(?=\s*{|$)/g);
                if (jsonObjects) {
                  jsonObjects.forEach(jsonObject => {
                    try {
                      console.log("单个JSON字符串:", jsonObject);
                      const responseData = JSON.parse(jsonObject);
                      console.log("解析后的数据:", responseData);
                      const content = responseData["content"];
                      console.log("提取的content:", content);
                      if (content) {
                        // 更新AI消息内容
                        aiMessage.content += content;
                        console.log("累积的AI内容:", aiMessage.content);
                        
                        // 强制Vue更新视图
                        this.$forceUpdate();
                      }
                    } catch (e) {
                      console.error('JSON parse error:', e, '原始JSON:', jsonObject);
                    }
                  });
                } else {
                  console.error('No JSON objects found in the stream:', resp);
                }
                
                // 继续读取下一块数据
                processStream();
              }).catch(error => {
                console.error('Stream reading error:', error);
                this.isLoading = false;
                this.$message.error('流式读取发生错误：' + error);
              });
            };
            
            processStream();
          })
          .catch(error => {
            console.error('Stream request error:', error);
            this.isLoading = false;
            this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + error);
            
            // 移除失败的AI消息
            const index = this.currentMessages.indexOf(aiMessage);
            if (index > -1) {
              this.currentMessages.splice(index, 1);
            }
          });
          
      } catch (error) {
        console.error('Error:', error)
        this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + error);
        this.isLoading = false
      }
    },
    scrollToBottom() {
      const container = this.$refs.messagesContainer
      if (container) {
        setTimeout(() => {
          container.scrollTo({
            top: container.scrollHeight,
            behavior: 'smooth'
          })
        }, 100)
      }
    },
    formatMessage(content) {
      // 配置 marked 使用 highlight.js
      marked.setOptions({
        highlight: function(code, language) {
          if (language && hljs.getLanguage(language)) {
            return hljs.highlight(code, { language }).value
          }
          return hljs.highlightAuto(code).value
        },
        breaks: true
      })
      return marked(content)
    },
    usesuggestion(suggestion) {
      this.userInput = suggestion
      this.sendMessage()
    },
    copyMessage(content) {
      navigator.clipboard.writeText(content)
      this.$message.success('已复制到剪贴板')
    },
    newline(e) {
      e.preventDefault()
      this.userInput += '\n'
    },
  }
}
</script>

<style lang="scss" scoped>
.chat-container {
  display: flex;
  height: 100vh;
  background-color: #ffffff;
}

.sidebar {
  width: 260px;
  background-color: #202123;
  color: #ffffff;
  display: flex;
  flex-direction: column;
  padding: 10px;
}

.new-chat-button {
  width: 100%;
  background-color: #343541;
  border: 1px solid #565869;
  color: #ffffff;
  height: 44px;
  border-radius: 6px;
  transition: all 0.3s ease;
}

.new-chat-button:hover {
  background-color: #40414f;
}

.chat-history {
  flex: 1;
  overflow-y: auto;
  margin: 20px 0;
}

.history-item {
  display: flex;
  align-items: center;
  padding: 10px;
  margin: 2px 0;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.history-item:hover {
  background-color: #2a2b32;
}

.history-item.active {
  background-color: #343541;
}

.history-item i {
  margin-right: 10px;
  font-size: 16px;
}

.chat-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.user-info {
  padding: 10px;
  border-top: 1px solid #4d4d4f;
}

.user-dropdown {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 8px;
  border-radius: 6px;
}

.user-dropdown:hover {
  background-color: #2a2b32;
}

.username {
  margin-left: 10px;
  color: #ffffff;
}

.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background-color: #343541;
}

.chat-header {
  padding: 16px;
  background-color: rgba(255,255,255,0.1);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid #4d4d4f;
}

.chat-header h2 {
  color: #ffffff;
  margin: 0;
  font-size: 16px;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.welcome-screen {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #ffffff;
}

.welcome-content {
  text-align: center;
  margin-bottom: 40px;
}

.suggestion-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  width: 600px;
}

.suggestion-card {
  background-color: #444654;
  padding: 16px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
}

.suggestion-card:hover {
  background-color: #40414f;
  transform: translateY(-2px);
}

.suggestion-card i {
  margin-right: 10px;
}

.message {
  display: flex;
  padding: 20px;
  transition: all 0.3s ease;
}

.message.user {
  background-color: #343541;
}

.message.assistant {
  background-color: #444654;
}

.message-avatar {
  margin-right: 20px;
}

.message-content {
  flex: 1;
  color: #ffffff;
  font-size: 15px;
  line-height: 1.6;
}

.message-actions {
  margin-top: 10px;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.message:hover .message-actions {
  opacity: 1;
}

.input-container {
  padding: 20px;
  background-color: #343541;
  border-top: 1px solid #4d4d4f;
}

.input-wrapper {
  display: flex;
  gap: 10px;
  background-color: #40414f;
  border-radius: 8px;
  padding: 8px;
  transition: all 0.3s ease;
}

.input-wrapper :deep(.el-textarea__inner) {
  background-color: transparent;
  border: none;
  color: #ffffff;
  resize: none;
  box-shadow: none;
  height: auto;
  max-height: 200px;
}

.input-wrapper :deep(.el-textarea__inner:focus) {
  box-shadow: none;
}

.send-button {
  align-self: flex-end;
  height: 32px;
  padding: 0 12px;
}

.input-footer {
  margin-top: 8px;
  text-align: center;
  color: #8e8ea0;
  font-size: 12px;
}

:deep(.el-button--text) {
  color: #8e8ea0;
}

:deep(.el-button--text:hover) {
  color: #ffffff;
}

/* 代码高亮样式 */
:deep(.hljs) {
  background: #282c34;
  border-radius: 6px;
  padding: 16px;
  margin: 10px 0;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-thumb {
  background-color: #4d4d4f;
  border-radius: 3px;
}

::-webkit-scrollbar-track {
  background-color: transparent;
}



.chat-textarea {
  flex: 1;
  transition: all 0.3s ease;
}

.chat-textarea :deep(.el-textarea__inner) {
  background-color: transparent;
  border: none;
  color: #ffffff;
  resize: none;
  box-shadow: none !important;
  transition: all 0.3s ease;
  font-size: 14px;
  line-height: 1.5;
  padding: 8px 12px;
}

.button-group {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  gap: 8px;
}

.expand-button {
  color: #8e8ea0;
  padding: 4px 8px;
  height: 32px;
}

.expand-button:hover {
  color: #ffffff;
  background-color: #4b4c5c;
}

/* 添加高度过渡效果 */
.el-textarea__inner {
  transition: height 0.3s ease !important;
}

/* 模型切换器样式 */
.model-switcher {
  margin-bottom: 12px;
  padding: 8px 0;
}

.model-switcher :deep(.el-radio-button__inner) {
  background-color: #40414f;
  border-color: #565869;
  color: #ffffff;
  padding: 4px 12px;
}

.model-switcher :deep(.el-radio-button__orig-radio:checked + .el-radio-button__inner) {
  background-color: #2563eb;
  border-color: #2563eb;
  box-shadow: none;
}








/* 移动端样式 */
.mobile-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.mobile-header {
  height: 50px;
  background-color: #202123;
  color: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 15px;
  position: fixed;
  // position: relative;
  top: 0;
  left: 0;
  right: 0;
  z-index: 1000;
}

.left-buttons {
  display: flex;
  align-items: center;
  gap: 4px; /* 控制两个按钮之间的距离 */
}

.header-title {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 60%; /* 防止标题过长影响按钮 */
}

.right-buttons {
  display: flex;
  align-items: center;
}

.mobile-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  z-index: 999;
}

.mobile-menu-content {
  position: absolute;
  top: 0;
  left: 0;
  width: 80%;
  height: 100%;
  background-color: #202123;
  padding: 60px 15px 15px;
  overflow-y: auto;
}

.mobile-content {
  margin-top: 50px;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background-color: #343541; /* 添加这行，与桌面端保持一致 */
}

.mobile-input {
  padding: 10px;
  background-color: #343541;
  border-top: 1px solid #4d4d4f;
}

.mobile-view .suggestion-grid {
  grid-template-columns: 1fr;
  width: auto;
  padding: 0 15px;
}

.mobile-view .welcome-content {
  padding: 0 15px;
}

.mobile-view .welcome-content h1 {
  font-size: 24px;
}

/* 移动端特定的动画 */
.mobile-menu-content {
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    transform: translateX(-100%);
  }
  to {
    transform: translateX(0);
  }
}

/* 根据设备类型隐藏/显示相应元素 */
.mobile-view .desktop-only {
  display: none;
}

.desktop-view .mobile-only {
  display: none;
}

/* 移动端模型切换器样式 */
.mobile-model-switcher {
  margin-bottom: 8px;
}

.mobile-model-switcher .model-select {
  width: 100%;
}

.mobile-model-switcher :deep(.el-select .el-input__inner) {
  background-color: #40414f;
  border-color: #565869;
  color: #ffffff;
}

/* 消息过渡动画 */
.message-content {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 响应式调整 */
@media (max-width: 768px) {
  .model-switcher {
    flex-wrap: wrap;
    gap: 4px;
  }
  
  .model-switcher :deep(.el-radio-button__inner) {
    padding: 2px 8px;
    font-size: 12px;
  }
  
  .message-actions {
    opacity: 1;
  }
  
  .mobile-model-switcher {
    padding: 0 8px;
  }
}








/* 视频容器样式 */
.video-container {
  width: 700px;

  @media screen and (max-width: 768px) {
    width: 350px;
    margin: 4px auto;
  }
}
.status-video {
  width: 700px;
  height: 394px;
  margin-top: 32px;
  border-radius: 200px;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.4);
  
  &.mobile {
    width: 100%;
    height: auto;
    aspect-ratio: 16/9;
    border-radius: 16px;
  }
}

.status-text {
  font-size: 15px;
  font-weight: bold;
  color: #063214E5;
  margin-top: 17px;
  text-align: center;
  
  &.mobile {
    font-size: 14px;
    margin-top: 12px;
  }
}

.chat-boxup-button-voice {
  background-image: url('@/assets/img/chatwindow/voice.png');
  cursor: pointer;
  width: 30px;
  height: 30px;
  background-color: #70dfab;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;
  border-radius: 20px;
  margin: auto;
  transition: background-color 0.5s;

  &:hover {
    background-color: #58f3ab;
  }
}

.chat-boxup-button-voice-ban {
  background-image: url('@/assets/img/chatwindow/EpMute.png');
  cursor: pointer;
  width: 30px;
  height: 30px;
  background-color: #651a0d;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;
  border-radius: 20px;
  margin: auto;
  transition: background-color 0.5s;

  &:hover {
    background-color: #581710;
  }
}

.myDialogSpeak {
  position: relative;
  top: -40px;
  width: 750px;
  height: 570px;
  border-radius: 10px;
  background-size: 100% 100%;

  @media screen and (max-width: 768px) {
    width: 100%;
    height: auto;
    top: 0;
    padding: 16px;
    
    :deep(.el-dialog) {
      width: 90% !important;
      margin: 0 auto;
      border-radius: 16px;
      overflow: hidden;
    }
  }
}

/* 遮罩层的样式 */
.custom-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgb(48, 212, 111);
  z-index: 999; /* 确保遮罩层在其他元素之上 */
  display: flex;
  justify-content: center;
  align-items: center;

  @media screen and (max-width: 768px) {
    background-color: rgba(48, 212, 111, 0.8);
  }
}
/* 定义过渡的样式 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.6s ease-in-out;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}


/* 下拉框容器 */
.dropdown-container {
  position: relative;
  display: inline-block;

  @media screen and (max-width: 768px) {
    position: relative;
    display: inline-block;
    flex-direction: column;
  }
}
.custom-select-wrapper {
  position: relative;
  display: inline-block;
  left: 26px;
  width: 200px; /* 根据需要调整宽度 */

  @media screen and (max-width: 768px) {
    width: 100%;
    left: 26px;
    margin: 0 auto;
  }
}
.emotion-select-wrapper {
  position: relative;
  display: inline-block;
  left: 52px;
  width: 200px; /* 根据需要调整宽度 */

  @media screen and (max-width: 768px) {
    width: 100%;
    left: 26px;
    margin: 0 auto;
  }
}

.custom-select-wrapper:after,
.emotion-select-wrapper:after {
  content: '\25BC'; /* 下拉箭头字符 */
  position: absolute;
  right: 17px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none; /* 防止箭头捕获点击事件 */
  color: #2e6805; /* 根据需要调整箭头颜色 */
}

.custom-select-wrapper:before,
.emotion-select-wrapper:before {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 1em;
  pointer-events: none; /* 防止捕获点击事件 */
  background: #094331; /* 根据需要调整背景颜色 */
}

.custom-select-display,
.emotion-select-display {
  padding: 10px;
  border: 1px solid #094e17;
  border-radius: 5px;
  background-color: #063214;
  color: #17e593da;
  font-size: 16px;
  cursor: pointer;

  @media screen and (max-width: 768px) {
    padding: 8px;
    font-size: 14px;
  }
}

.custom-select-options,
.emotion-select-options {
  margin-top: 5px;
  position: absolute;
  width: 100%;
  background-color: #043122;
  border: 1px solid #094e17;
  border-radius: 5px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
  z-index: 100;

  @media screen and (max-width: 768px) {
    margin-top: 4px;
    max-height: 200px;
    overflow-y: auto;
  }
}

.custom-select-option,
.emotion-select-option {
  padding: 10px;
  color: #22c99d;
  border-bottom: 1px solid #083a12;
  cursor: pointer;

  @media screen and (max-width: 768px) {
    padding: 8px;
    font-size: 14px;
  }
}

.custom-select-option:last-child,
.emotion-select-option:last-child {
  border-bottom: none;
}

.custom-select-option:hover,
.emotion-select-option:hover {
  background-color: #084723;
  border: 1px solid #073a12; /* 根据需要调整边框 */
}

.custom-select-option.is-selected,
.emotion-select-option.is-selected {
  background-color: #074029;
  border: 1px solid #052b0d; /* 根据需要调整边框 */
}


// 添加模型选择样式
/* 方案一：深色主题风格 */
.model-selector {
  margin-bottom: 10px;
  padding: 10px;
  background: #6a717e;
  border-radius: 8px;
}

.model-indicator {
  margin-bottom: 8px;
}



/* 移动端对话框样式 */
.mobile-dialog {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(105, 160, 137, 0.2);
  z-index: 2000;
  display: flex;
  align-items: center;
  justify-content: center;
  
  .mobile-dialog-content {
    position: relative;
    width: 90%;
    max-height: 90vh;
    background: white;
    border-radius: 16px;
    padding: 20px;
    overflow-y: auto;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  }
  
  .mobile-dialog-close {
    position: absolute;
    top: 16px;
    right: 16px;
    width: 24px;
    height: 24px;
    border: none;
    background: transparent;
    color: #666;
    font-size: 24px;
    line-height: 24px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    
    &:hover {
      color: #333;
    }
  }
}

/* 自定义滚动条样式 */
.mobile-dialog-content {
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-track {
    background: #f1f1f1;
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: #888;
    border-radius: 3px;
  }
  
  &::-webkit-scrollbar-thumb:hover {
    background: #555;
  }
}
</style>