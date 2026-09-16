// 格式1：模型列表
// {
//     "img": "",
//     "lastMsg": "to do",
//     "headImg": "/static/img/head_portrait1.84f92874.jpg",
//     "sequence": 0,
//     "name": "GPT4",
//     "detail": "OpenAI",
//     "id": "1002",
//     "imgKey": "1"
//     "responseSpeed": 'medium_fast',
//     "reasoningLevel": "none",
//     "multimodalLevel": "none",
//     "description": ""
// }
// 格式2：模型消息
// {
//     "headImg": "/static/img/head_portrait1.84f92874.jpg",
//     "name": "GPT4",
//     "time": "13:54:50",
//     "msg": "您好，我是您的AI助手GPT4，我擅长英文问题回答、文本摘要、信息提取、头脑风暴，请问有什么可以帮助您？",
//     "chatType": 0,
//     "extend": {
//         "imgType": 1
//     },
//     "uid": "1002"
// }
// 格式3：JSON配置
  // {
  //   "name": "GPT4",
  //   "detail": "OpenAI",
  //   "id": "1002",
  //   "sequence": 0,
  //   "lastMsg": "to do",
  //   "imgKey": "1",
  //   "hyperParams": {
  //     "temperature": 0.7,
  //     "top_p": 0.95,
  //     "max_tokens": 2048,
  //     "presence_penalty": 1.0,
  //     "frequency_penalty": 1.0,
  //     "stop": ["\n"]
  //   },
  //   "responseSpeed": 'medium_fast',
  //   "reasoningLevel": "none",
  //   "multimodalLevel": "none",
  //   "description": ""
  // },
// 格式4：模型配置表单
// this.modelForm = {
//   id: '',
//   abbreviation: '',
//   fullName: '',
//   url: '',
//   apiKey: '',
//   promptTemplate: '',
//   isInference: false,
//   supportsImages: false
// };



// 头像资源映射表
const HEAD_IMAGES = {
    '1': require('@/assets/img/head_portrait1.jpg'),
    '2': require('@/assets/img/head_portrait2.jpg'),
    '3': require('@/assets/img/head_portrait3.jpg'),
    '4': require('@/assets/img/head_portrait4.jpg'),
    '5': require('@/assets/img/head_portrait5.png'),
    '6': require('@/assets/img/head_portrait6.png')
  };

export class ModelFormatter {
  /**
   * 将格式3转换为格式1（模型列表项）
   * @param {Object} model 格式3的模型数据
   * @returns {Object} 格式1的输出
   */
  static toListFormat(model) {
    return {
      img: "",
      lastMsg: model.lastMsg || "to do",
      headImg: HEAD_IMAGES[model.imgKey] || HEAD_IMAGES.default,
      sequence: model.sequence || 0,
      name: model.name,
      detail: model.detail,
      id: model.id,
      imgKey: model.imgKey || "1",

      responseSpeed: model.responseSpeed || 'medium_fast',
      reasoningLevel: model.reasoningLevel || "low_nonnative",
      multimodalLevel: model.multimodalLevel || "none",
      description: model.description || "",
      // 保留原始数据（不对外暴露）
      _raw: {
        hyperParams: model.hyperParams,
        createdAt: model.createdAt,
        updatedAt: model.updatedAt
      }
    };
  }

  /**
   * 将格式3转换为格式2（聊天消息）
   * @param {Object} model 格式3的模型数据 
   * @param {string} timeStr 时间字符串 (HH:mm:ss)
   * @returns {Object} 格式2的输出
   */
  static toChatFormat(model, timeStr) {
    return {
      headImg: HEAD_IMAGES[model.imgKey] || HEAD_IMAGES.default,
      name: model.name,
      time: timeStr,
      msg: this._generateWelcomeMsg(model),
      chatType: 0,  // 0-文字 1-图片
      extend: {
        imgType: 1, // 表情类型
        capabilities: this._getCapabilities(model)
      },
      uid: model.id
    };
  }

  // -------------------- 私有方法 --------------------
  /**
   * 生成欢迎消息
   */
  static _generateWelcomeMsg(model) {
    const skills = [
      '问题回答',
      '文本摘要',
      '信息提取',
      ...(model.hyperParams?.temperature > 0.7 ? ['创意生成'] : ['精准回答']),
      ...(model.hyperParams?.max_tokens > 2048 ? ['长文本处理'] : [])
    ];
    return `您好，我是${model.name}（${model.detail}），擅长${skills.join('、')}，若用双问号？？提问则不直接回答而是提供建议引导；若用三问号？？？则进行脱场景对话；若使用叹号！则对话后自动迭代一次增强思维，+/++/+++代表以上的程度，有什么可以帮您吗？`;
  }

  /**
   * 获取模型能力标记
   */
  static _getCapabilities(model) {
    return {
      inference: model.hyperParams?.temperature < 0.3, // 低温=推理型
      creative: model.hyperParams?.temperature > 0.7,  // 高温=创意型
      longText: model.hyperParams?.max_tokens > 2048   // 长文本支持
    };
  }
}