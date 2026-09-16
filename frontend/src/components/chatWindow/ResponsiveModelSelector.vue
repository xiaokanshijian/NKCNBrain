<template>
    <div class="model-selector">
      <el-radio-group v-model="currentModel" size="small" @change="handleModelChange">
        <!-- 显示的模型按钮 -->
        <el-radio-button 
          v-for="model in displayedModels" 
          :key="model.id" 
          :label="model.id">
          {{ model.label }}
        </el-radio-button>
        
        <!-- 更多按钮 -->
        <el-button 
          v-if="hasHiddenModels"
          size="small" 
          class="more-button"
          @click="openDialog">
          <span>...</span>
        </el-button>
      </el-radio-group>
      
      <!-- 自定义弹窗 -->
      <div v-if="showMoreDialog" class="custom-dialog-overlay" @click="closeDialog">
        <div class="custom-dialog" @click.stop>
          <!-- 弹窗头部 -->
          <div class="dialog-header">
            <h3 class="dialog-title">选择模型</h3>
            <button class="close-btn" @click="closeDialog">
              <i class="el-icon-close"></i>
            </button>
          </div>
          
          <!-- 弹窗内容 -->
          <div class="dialog-body">
            <div class="model-grid">
              <div 
                v-for="model in modelOptions" 
                :key="model.id"
                class="model-item"
                :class="{ 'active': currentModel === model.id }"
                @click="selectModel(model.id)">
                <!-- 这个id其实是模型自定义命名（后端json文件名），后端通过此名字get_model_id_by_name获取真正的ID号1xxx -->
                <div class="model-name">{{ model.id }}</div>
                <!-- 这个model_id样式类的label其实是实际API调用传入的modelname -->
                <div class="model-id">{{ model.label }}</div>
              </div>
            </div>
          </div>
          
          <!-- 弹窗底部 -->
          <div class="dialog-footer">
            <el-button @click="closeDialog">取消</el-button>
            <el-button type="primary" @click="closeDialog">确定</el-button>
          </div>
        </div>
      </div>
    </div>
  </template>
  
  <script>
  import { ElButton } from 'element-plus'
  
  export default {
    components: {
      ElButton,
    },
    props: {
      value: {
        type: String,
        default: ''
      },
      modelOptions: {
        type: Array,
        default: () => []
      }
    },
    emits: ['input'],
    data() {
      return {
        isMobile: false,
        showMoreDialog: false // 控制弹窗显示
      }
    },
    computed: {
      currentModel: {
        get() {
          return this.value;
        },
        set(val) {
          this.$emit('input', val);
          console.log('选中的模型:', val);
        }
      },
      // 计算显示数量
      maxDisplayCount() {
        return this.isMobile ? 4 : 6;
      },
      // 计算显示的模型
      displayedModels() {
        return this.modelOptions.slice(0, this.maxDisplayCount);
      },
      // 是否有隐藏的模型
      hasHiddenModels() {
        return this.modelOptions.length > this.maxDisplayCount;
      }
    },
    methods: {
      // 检测设备类型
      checkDevice() {
        this.isMobile = window.innerWidth <= 768;
      },
      // 打开弹窗
      openDialog() {
        console.log('打开弹窗');
        this.showMoreDialog = true;
        // 防止页面滚动
        document.body.style.overflow = 'hidden';
        // 监听 ESC 键
        document.addEventListener('keydown', this.handleEscape);
      },
      // 关闭弹窗
      closeDialog() {
        console.log('关闭弹窗');
        this.showMoreDialog = false;
        // 恢复页面滚动
        document.body.style.overflow = '';
        // 移除 ESC 键监听
        document.removeEventListener('keydown', this.handleEscape);
      },
      // ESC 键关闭弹窗
      handleEscape(e) {
        if (e.key === 'Escape') {
          this.closeDialog();
        }
      },
      // 选择模型（弹窗中使用）
      selectModel(modelId) {
        console.log('弹窗中选择模型:', modelId);
        this.currentModel = modelId;
        // 选择后关闭弹窗
        this.closeDialog();
      },
      // 处理模型变化
      handleModelChange(val) {
        console.log('模型变化事件:', val);
      }
    },
    mounted() {
      this.checkDevice();
      window.addEventListener('resize', this.checkDevice);
    },
    beforeUnmount() {
      window.removeEventListener('resize', this.checkDevice);
      // 确保移除事件监听
      document.removeEventListener('keydown', this.handleEscape);
      document.body.style.overflow = '';
    }
  };
  </script>
  
  <style lang="scss" scoped>
  .model-selector {
    margin-bottom: 10px;
    padding: 10px;
    background: #6a717e;
    border-radius: 8px;
  }
  
  /* 更多按钮样式 */
  .more-button {
    background: linear-gradient(135deg, #374151 0%, #4b5563 100%) !important;
    border-color: #6b7280 !important;
    color: #e5e7eb !important;
    margin-left: 4px;
    padding: 5px 8px !important;
    border-radius: 4px;
    min-width: 32px;
  }
  
  .more-button:hover {
    background: linear-gradient(135deg, #4b5563 0%, #6b7280 100%) !important;
    border-color: #9ca3af !important;
    color: #f3f4f6 !important;
  }
  
  /* 确保按钮组能够换行 */
  .model-selector .el-radio-group {
    display: flex;
    flex-wrap: wrap;
    gap: 2px;
    align-items: center;
  }
  
  /* 自定义弹窗样式 */
  .custom-dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 2000;
    backdrop-filter: blur(4px);
  }
  
  .custom-dialog {
    background: #434a54;
    border-radius: 12px;
    width: 700px;
    max-width: 95vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    animation: dialogFadeIn 0.3s ease-out;
  }
  
  @keyframes dialogFadeIn {
    from {
      opacity: 0;
      transform: scale(0.9) translateY(-20px);
    }
    to {
      opacity: 1;
      transform: scale(1) translateY(0);
    }
  }
  
  /* 弹窗头部 */
  .dialog-header {
    padding: 20px 24px 16px;
    border-bottom: 1px solid #6b7280;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  
  .dialog-title {
    color: #f3f4f6;
    font-size: 18px;
    font-weight: 600;
    margin: 0;
  }
  
  .close-btn {
    background: none;
    border: none;
    color: #9ca3af;
    font-size: 20px;
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    transition: all 0.2s;
  }
  
  .close-btn:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #f3f4f6;
  }
  
  /* 弹窗内容 */
  .dialog-body {
    padding: 20px 24px;
    flex: 1;
    overflow-y: auto;
    min-height: 300px;
    max-height: 60vh;
  }
  
  .model-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px;
  }
  
  .model-item {
    background: linear-gradient(135deg, #374151 0%, #4b5563 100%);
    border: 1px solid #6b7280;
    border-radius: 8px;
    padding: 16px;
    cursor: pointer;
    transition: all 0.3s ease;
    text-align: center;
  }
  
  .model-item:hover {
    background: linear-gradient(135deg, #4b5563 0%, #6b7280 100%);
    border-color: #9ca3af;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  }
  
  .model-item.active {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
    border-color: #3b82f6;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.3);
  }
  
  .model-name {
    color: #f3f4f6;
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 4px;
  }
  
  .model-item.active .model-name {
    color: #ffffff;
  }
  
  .model-id {
    color: #9ca3af;
    font-size: 12px;
    opacity: 0.8;
  }
  
  .model-item.active .model-id {
    color: rgba(255, 255, 255, 0.8);
  }
  
  /* 弹窗底部 */
  .dialog-footer {
    padding: 16px 24px 20px;
    border-top: 1px solid #6b7280;
    display: flex;
    justify-content: flex-end;
    gap: 12px;
  }
  
  /* Radio Button 样式 */
  .model-selector :deep(.el-radio-button__inner) {
    background: linear-gradient(135deg, #374151 0%, #4b5563 100%) !important;
    border-color: #6b7280 !important;
    color: #e5e7eb !important;
    box-shadow: none !important;
  }
  
  .model-selector :deep(.el-radio-button__inner:hover) {
    background: linear-gradient(135deg, #4b5563 0%, #6b7280 100%) !important;
    border-color: #9ca3af !important;
    color: #f3f4f6 !important;
  }
  
  .model-selector :deep(.el-radio-button.is-active .el-radio-button__inner) {
    background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%) !important;
    border-color: #3b82f6 !important;
    color: #ffffff !important;
  }
  
  /* 移动端优化 */
  @media (max-width: 768px) {
    .model-selector {
      padding: 8px;
    }
    
    .model-selector :deep(.el-radio-button__inner) {
      font-size: 12px;
      padding: 6px 10px;
    }
    
    .more-button {
      padding: 6px !important;
      min-width: 28px;
    }
    
    .custom-dialog {
      width: 95vw;
      max-height: 85vh;
      margin: 10px;
    }
    
    .dialog-header {
      padding: 16px 20px 12px;
    }
    
    .dialog-title {
      font-size: 16px;
    }
    
    .dialog-body {
      padding: 16px 20px;
      max-height: 50vh;
    }
    
    .model-grid {
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 8px;
    }
    
    .model-item {
      padding: 12px;
    }
    
    .dialog-footer {
      padding: 12px 20px 16px;
    }
  }
  </style>