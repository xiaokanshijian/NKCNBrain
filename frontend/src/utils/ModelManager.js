// import { modelConfigLoader } from './ModelConfigLoader';
// import { modelPersistence } from '../utils/ModelPersistence';
import { request_model_list, update_model_list } from '@/api/chat/send_message';

export class ModelManager {
  constructor() {
    this.models = new Map();  // 存储格式3的完整数据 { id => model }
    this._initialized = false;
    this.loadFromCache(); // 改：构造时先加载缓存
  }

  /**
   * 初始化加载模型数据
   */
  async init() {
    console.log("有/无缓存初始化：", this.models)
    if (this._initialized && localStorage.getItem('modelManagerCache')) return;
    
    try {
      // const configs = await modelConfigLoader.load();
      // 改为从后端获取模型列表
      const configs = await request_model_list();

      console.log('模型-列表:', configs);
      this.models.clear();
      configs.forEach(model => this.models.set(model.id, model));
      this._initialized = true;

      // 改：保存到缓存
      this.saveToCache();
    } catch (error) {
      console.error('ModelManager初始化失败:', error);
      throw error;
    }
  }

  /**
   * 添加新模型
   * @param {Object} rawData 包含必需的模型字段（至少name/detail）
   * @returns {Promise<Object>} 添加后的完整模型数据（格式3）
   */
  async addModel(rawData) {
    await this._validateModelData(rawData);
    
    // const newModel = this._createModelObject(rawData);
    this.models.set(rawData.id, rawData);

    try {
      // await modelPersistence.save(this.getAllModels());
      // 向后端发送新增模型信息

      return { ...rawData };
    } catch (error) {
      this.models.delete(rawData.id); // 回滚
      throw error;
    }
  }


  createModelFromForm(formData) {
    const modelData = {
      name: formData.abbreviation,       // 映射 abbreviation -> name
      detail: formData.fullName,         // 映射 fullName -> detail
      id: this._generateId(),            // 生成唯一ID
      sequence: this._getNextSequence(), // 自动生成序号
      lastMsg: "to do",                  // 默认消息
      imgKey: "1",                       // 默认头像
      hyperParams: {                     // 默认超参数
        temperature: 0.7,
        top_p: 0.95,
        max_tokens: 2048,
        presence_penalty: 1.0,
        frequency_penalty: 1.0,
        stop: ["\n"]
      },

      responseSpeed: formData.responseSpeed || 'medium_fast',
      reasoningLevel: formData.reasoningLevel || 'low_nonnative',
      multimodalLevel: formData.multimodalLevel || 'none',
      description: formData.description || '',
      // 保留原始表单数据（可选）
      _raw: {
        url: formData.url,
        apiKey: formData.apiKey,
        promptTemplate: formData.promptTemplate
        // isInference: formData.isInference,
        // supportsImages: formData.supportsImages
      }
    };
  
    // 向后端发送formData
    const backendData = {
      name: formData.abbreviation,
      full_name: formData.fullName,
      id: modelData.id,
      // model_type: formData.modelType || 'openai',  // 默认为openai
      model_type: formData.type || 'openai',  // 默认为openai
      sequence: modelData.sequence,
      hyperParams: modelData.hyperParams,
      base_url: formData.url,
      model_api: formData.apiKey,  
      prompt_template: formData.promptTemplate,
      // reasoner: formData.isInference,
      // allow_img: formData.supportsImages
      response_speed: formData.responseSpeed || 'medium_fast',
      reasoning_level: formData.reasoningLevel || 'low_nonnative',
      multimodal_level: formData.multimodalLevel || 'none',
      description: formData.description || ''
    };
    
    // 调用后端API
    update_model_list(backendData)
      .then(response => {
        console.log('Model data sent to backend successfully:', response);
      })
      .catch(error => {
        console.error('Error sending model data to backend:', error);
      });
  
    return modelData;
  }

  /**
   * 添加表单模型（完整流程）
   * @param {Object} formData 格式4的表单数据
   * @returns {Promise<Object>} 添加后的完整模型数据（格式3）
   */
  async addModelFromForm(formData) {
    const modelConfig = this.createModelFromForm(formData);
    return this.addModel(modelConfig);
  }

  /**
  * 更新现有模型
  * @param {Object} formData 包含模型更新信息的表单数据
  * @returns {Promise<Object>} 更新后的完整模型数据
  */
  async updateModel(formData) {
    if (!formData.id) {
      throw new Error('更新模型需要提供有效的ID');
    }
    
    // 检查模型是否存在
    if (!this.models.has(formData.id)) {
      throw new Error(`模型 ${formData.id} 不存在`);
    }
    
    // 获取原始模型数据
    const originalModel = this.models.get(formData.id);
    
    // 准备更新数据
    const updatedModel = {
      ...originalModel,
      name: formData.abbreviation,
      detail: formData.fullName,
      // 保留原始ID和sequence
      id: formData.id,
      sequence: originalModel.sequence,
      // 更新其他字段
      hyperParams: originalModel.hyperParams || {
        temperature: 0.7,
        top_p: 0.95,
        max_tokens: 2048,
        presence_penalty: 1.0,
        frequency_penalty: 1.0,
        stop: ["\n"]
      },
      responseSpeed: formData.responseSpeed || 'medium_fast',
      reasoningLevel: formData.reasoningLevel || 'low_nonnative',
      multimodalLevel: formData.multimodalLevel || 'none',
      description: formData.description || '',
      // 更新原始表单数据
      _raw: {
        url: formData.url,
        apiKey: formData.apiKey,
        promptTemplate: formData.promptTemplate,
      }
    };
    
    // 向后端发送更新请求
    const backendData = {
      name: formData.abbreviation,
      full_name: formData.fullName,
      id: formData.id,
      model_type: formData.type || 'openai',
      sequence: updatedModel.sequence,
      hyperParams: updatedModel.hyperParams,
      base_url: formData.url,
      model_api: formData.apiKey,
      prompt_template: formData.promptTemplate,

      response_speed: formData.responseSpeed,
      reasoning_level: formData.reasoningLevel,
      multimodal_level: formData.multimodalLevel,
      description: formData.description || ''
    };
    
    try {
      // 更新本地数据
      this.models.set(formData.id, updatedModel);
      
      // 保存到缓存
      this.saveToCache();
      
      // 发送到后端
      await update_model_list(backendData);
      
      return { ...updatedModel };
    } catch (error) {
      // 发生错误时恢复原始数据
      this.models.set(formData.id, originalModel);
      this.saveToCache();
      throw error;
    }
  }

  /**
   * 删除模型
   * @param {string} id 模型ID
   * @returns {Promise<boolean>} 是否删除成功
   */
  async deleteModel(id) {
    if (!this.models.has(id)) {
      throw new Error(`模型 ${id} 不存在`);
    }

    // const deletedModel = this.models.get(id);
    this.models.delete(id);
  }

  /**
   * 改：获取单个模型（格式3）
   */
  getModelById(id) {
    let model = this.models.get(id);

    // 如果没找到且还没初始化，尝试从缓存加载
    // if (!model && !this._initialized) {
    if (!model) {
      this.loadFromCache();
      model = this.models.get(id);
      
      // 后台异步初始化
      this.init().catch(err => console.error('后台初始化失败:', err));
    }

    if (!model) {
      console.log(`模型 ${id} 不存在缓存`);
      // window.location.reload();
      return;
    }
    console.log("是或不是缓存来的单model", model)
    return { ...model }; // 返回副本
  }

  /**
   * 改：获取所有模型（格式3数组，按sequence排序）
   */
  getAllModels() {
    // 如果没数据且还没初始化，先从缓存加载
    // if (this.models.size === 0 && !this._initialized) {
    if (this.models.size === 0) {
      this.loadFromCache();
      
      // 后台异步初始化
      this.init().catch(err => console.error('后台初始化失败:', err));
    }

    return Array.from(this.models.values())
      .sort((a, b) => a.sequence - b.sequence)
      .map(model => ({ ...model })); // 返回副本
  }

  // 保存到localStorage
  saveToCache() {
    try {
      const modelsArray = Array.from(this.models.values());
      localStorage.setItem('modelManagerCache', JSON.stringify(modelsArray));
      console.log('保存模型缓存modelManagerCache');
    } catch (error) {
      console.error('保存模型缓存失败:', error);
    }
  }

  // 从localStorage加载
  loadFromCache() {
    try {
      const cached = localStorage.getItem('modelManagerCache');
      if (cached) {
        const modelsArray = JSON.parse(cached);
        this.models.clear();
        modelsArray.forEach(model => this.models.set(model.id, model));
        console.log('从缓存加载了', modelsArray.length, '个模型');
      } else {
        console.log('缓存内暂无模型');
      }
    } catch (error) {
      console.error('加载模型缓存失败:', error);
    }
  }

  /**
   * Get a dictionary of model hyperparameters keyed by model name
   * @returns {Object} Dictionary of { modelName: hyperParams }
   */
  getHyperParamsDictionary() {
    const hyperParamsDict = {};
    
    this.models.forEach((model) => {
      if (model.name && model.hyperParams) {
        hyperParamsDict[model.name] = { ...model.hyperParams };
      }
    });
    
    return hyperParamsDict;
  }

  // -------------------- 私有方法 --------------------
  /**
   * 创建新模型对象
   */
  _createModelObject(rawData) {
    return {
      ...rawData,
      id: this._generateId(),
      sequence: this._getNextSequence(),
      imgKey: rawData.imgKey || '1',
      lastMsg: rawData.lastMsg || 'to do',
      createdAt: new Date().toISOString(),
      hyperParams: this._normalizeHyperParams(rawData.hyperParams),

      responseSpeed: rawData.responseSpeed || 'medium_fast',
      reasoningLevel: rawData.reasoningLevel || 'low_nonnative',
      multimodalLevel: rawData.multimodalLevel || 'none',
      description: rawData.description || '',
      _raw: rawData._raw || {}
    };
  }

  /**
   * 验证模型数据有效性
   */
  async _validateModelData(data) {
    const errors = [];
    
    // 必填字段检查
    if (!data.name || data.name.trim().length < 2) {
      errors.push('模型名称至少需要2个字符');
    }
    
    if (!data.detail || data.detail.trim().length < 2) {
      errors.push('模型描述至少需要2个字符');
    }

    // 名称唯一性检查
    const nameExists = Array.from(this.models.values()).some(
      model => model.name === data.name && model.id !== data.id
    );
    if (nameExists) {
      errors.push(`模型名称 "${data.name}" 已存在`);
    }

    if (errors.length > 0) {
      throw new Error(errors.join('; '));
    }
  }

  /**
   * 生成唯一ID (1开头 + 3位随机数)
   */
  _generateId() {
    let id;
    do {
      id = '1' + Math.floor(100 + Math.random() * 900);
    } while (this.models.has(id));

    console.log('生成的唯一ID:', id);

    return id;
  }

  /**
   * 获取下一个sequence值
   */
  _getNextSequence() {
    const sequences = Array.from(this.models.values()).map(m => m.sequence);
    return sequences.length > 0 ? Math.max(...sequences) + 1 : 0;
  }

  /**
   * 标准化超参数
   */
  _normalizeHyperParams(params = {}) {
    return {
      temperature: this._clamp(params.temperature, 0, 2, 0.7),
      max_tokens: params.max_tokens || 2048,
      top_p: this._clamp(params.top_p, 0, 1, 0.95),
      ...params
    };
  }

  /**
   * 数值范围限制
   */
  _clamp(value, min, max, defaultValue) {
    if (value === undefined) return defaultValue;
    return Math.min(max, Math.max(min, value));
  }
}

// 导出单例实例（带自动初始化）
export const modelManager = new ModelManager();

// 自动初始化（可选）
modelManager.init().catch(err => {
  console.error('模型管理器自动初始化失败:', err);
});