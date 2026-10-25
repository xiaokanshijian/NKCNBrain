import base from './index'
import { execute_commands, execute_commands_stream, execute_commands_stream_sessionId } from "@/api/chat/send_message"
import { getSceneSummary } from "@/views/pages/mainHome/my_js"
let axios = base.axios
let baseUrl = base.baseUrl

import { modelManager } from '@/utils/ModelManager'
import { ModelFormatter } from '@/utils/ModelFormatter';
import { API_BASE_URL, USE_BACKEND_DEPTH_SUGGESTION } from '@/config/apiConfig';

var currentDate = new Date();

var year = currentDate.getFullYear(); // 获取当前年份，如2022
var month = currentDate.getMonth() + 1; // 获取当前月份，注意月份从0开始计算，所以要+1，如2表示3月份
var day = currentDate.getDate(); // 获取当前日期，如15
var hours = currentDate.getHours(); // 获取当前小时（0-23），如18
var minutes = currentDate.getMinutes(); // 获取当前分钟（0-59），如30
var seconds = currentDate.getSeconds(); // 获取当前秒数（0-59），如45
var H_M_S = hours + ":" + minutes + ":" + seconds

let modelList =
  [
    {
      img: "",
      name: "GPT4",
      detail: "OpenAI",
      lastMsg: "to do",
      id: "1002",
      headImg: require("@/assets/img/head_portrait1.jpg"),

    },
    {
      img: "",
      name: "Mixtral8x7B",
      detail: "MistralAI",
      lastMsg: "大萨达萨达所大大萨达",
      id: "1003",
      headImg: require("@/assets/img/head_portrait2.jpg"),

    },
    {
      img: "",
      name: "Kimi",
      detail: "MoonShot",
      lastMsg: "dada dw ertgthy j uy",
      id: "1004",
      headImg: require("@/assets/img/head_portrait3.jpg"),

    },
    {
      img: "",
      name: "Llama3",
      detail: "Meta",
      lastMsg: "dada dw ertgthy j uy",
      id: "1005",
      headImg: require("@/assets/img/head_portrait4.jpg"),

    },
    {
      img: "",
      name: "Claude3.5",
      detail: "Anthropic",
      lastMsg: "dada dw ertgthy j uy",
      id: "1006",
      headImg: require("@/assets/img/head_portrait5.png"),

    },
    {
      img: "",
      name: "Deepseek",
      detail: "Deepseek",
      lastMsg: "dada dw ertgthy j uy",
      id: "1007",
      headImg: require("@/assets/img/head_portrait6.png"),

    },
    {
      img: "",
      name: "Deepseek-reasoner",
      detail: "Aliyun",
      lastMsg: "dada dw ertgthy j uy",
      id: "1008",
      headImg: require("@/assets/img/head_portrait6.png"),

    },
    {
      img: "",
      name: "Gemini",
      detail: "Google 2.5",
      lastMsg: "dada dw ertgthy j uy",
      id: "1009",
      headImg: require("@/assets/img/emoji/rocket.png"),

    },
    {
      img: "",
      name: "Qwq",
      detail: "plus",
      lastMsg: "dada dw ertgthy j uy",
      id: "1010",
      headImg: require("@/assets/img/emoji/shamrock.png"),

    },
  ]

let LittleModelList = 
  [
    {
      img: "",
      name: "Qwen3-30B-A3B MoE",
      detail: "0.3B×128专家微调小模型，均衡性能，为默认",
      lastMsg: "dada dw ertgthy j uy",
      id: "3003",
      headImg: require("@/assets/img/emoji/smiling-face-with-sunglasses.png"),
    },
    {
      img: "",
      name: "llama3.1 8B单模",
      detail: "快速稳定的8B微调小模型",
      lastMsg: "dada dw ertgthy j uy",
      id: "3002",
      headImg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    },
    // {
    //   img: "",
    //   name: "Qwen3 32B单模",
    //   detail: "保证推理质量的微调小模型",
    //   lastMsg: "dada dw ertgthy j uy",
    //   id: "3001",
    //   headImg: require("@/assets/img/emoji/smiling-face.png"),
    // },
    // {
    //   img: "",
    //   name: "DeepSeek-R1-Qwen3-8B",
    //   detail: "DS-R1蒸馏小模型",
    //   lastMsg: "dada dw ertgthy j uy",
    //   id: "3004",
    //   headImg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    // },
    // {
    //   img: "",
    //   name: "GPT-OSS-20B",
    //   detail: "开源GPT架构20B单模型",
    //   lastMsg: "dada dw ertgthy j uy",
    //   id: "3005",
    //   headImg: require("@/assets/img/emoji/thinking-face.png"),

    // },
    // {
    //   img: "",
    //   name: "Llama3.3 70B模型",
    //   detail: "70B微调中模型（待开发）",
    //   lastMsg: "dada dw ertgthy j uy",
    //   id: "3006",
    //   headImg: require("@/assets/img/emoji/face-without-mouth.png"),

    // },
    {
      img: "",
      name: "Qwen3-30B-A3B-HL-e3-3k-e2-1k",
      detail: "基于已有红蓝模型以新3k+旧1k数据训练",
      lastMsg: "dada dw ertgthy j uy",
      id: "3001",
      headImg: require("@/assets/img/emoji/smiling-face.png"),
    },
    {
      img: "",
      name: "Qwen3-30B-A3B-HL-e3-3k",
      detail: "基于已有红蓝模型以新3k数据训练",
      lastMsg: "dada dw ertgthy j uy",
      id: "3004",
      headImg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    },
    {
      img: "",
      name: "Qwen3-30B-A3B-e3-3k",
      detail: "基于30B moe基座以新3k数据训练",
      lastMsg: "dada dw ertgthy j uy",
      id: "3005",
      headImg: require("@/assets/img/emoji/thinking-face.png"),

    },
    {
      img: "",
      name: "Qwen3-30B-A3B-e3-3k-e2-1k",
      detail: "基于30B moe基座以新3k+旧1k数据训练",
      lastMsg: "dada dw ertgthy j uy",
      id: "3006",
      headImg: require("@/assets/img/emoji/face-without-mouth.png"),

    },
    // {
    //   img: "",
    //   name: "llama3.3 70B模型",
    //   detail: "初步雏形70B微调中模型",
    //   lastMsg: "dada dw ertgthy j uy",
    //   id: "3004",
    //   headImg: require("@/assets/img/emoji/thinking-face.png"),
    // },
    {
      img: "",
      name: "Qwen3-30B-A3B MoE NewServer",
      detail: "0.3B×128专家微调小模型，均衡性能，新算力服务器",
      lastMsg: "dada dw ertgthy j uy",
      id: "3007",
      headImg: require("@/assets/img/emoji/smiling-face-with-sunglasses.png"),
    },
  ]

let MultimodalLittleModelList =
  [
    {
      img: "",
      name: "RhyAQA",
      detail: "节律感知问答多模态小模型",
      lastMsg: "dada dw ertgthy j uy",
      id: "4002",
      headImg: require("@/assets/img/emoji/hibiscus.png"),
    },
    {
      img: "",
      name: "RespLLM",
      detail: "呼吸音频分类多模态小模型",
      lastMsg: "dada dw ertgthy j uy",
      id: "4001",
      headImg: require("@/assets/img/emoji/shamrock.png"),
    },
  ]

let chatMsg1002 =
  [
    {
      headImg: require("@/assets/img/head_portrait1.jpg"),
      name: "GPT4",
      time: H_M_S,
      msg: " 您好，我是您的AI助手GPT4o，我擅长中英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
      //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
      chatType: 0, //信息类型，0文字，1图片
      extend: {
        imgType: 1, //(1表情，2本地图片)
      },
      uid: "1002", //uid
      checked: false,
    },
  ]

let chatMsg1003 = [
  {
    headImg: require("@/assets/img/head_portrait2.jpg"),
    name: "Mixtral8x7B",
    time: H_M_S,
    msg: " 您好，我是您的AI助手Mixtral8x7B，我擅长中英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1003", //uid
  },
]

let chatMsg1004 = [
  {
    headImg: require("@/assets/img/head_portrait3.jpg"),
    name: "Kimi",
    time: H_M_S,
    msg: " 您好，我是您的AI助手Kimi，我擅长中英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1004", //uid
  },
]


let chatMsg1005 = [
  {
    headImg: require("@/assets/img/head_portrait4.jpg"),
    name: "Llama3",
    time: H_M_S,
    msg: " 您好，我是您的AI助手Llama3.1，我擅长英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1005", //uid
  },
]


let chatMsg1006 = [
  {
    headImg: require("@/assets/img/head_portrait5.png"),
    name: "Claude3.5",
    time: H_M_S,
    msg: " 您好，我是您的AI助手Claude3.5，我擅长英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1006", //uid
  },
]


let chatMsg1007 = [
  {
    headImg: require("@/assets/img/head_portrait6.png"),
    name: "Deepseek",
    time: H_M_S,
    msg: " 您好，我是您的AI助手DeepSeek V3，我擅长英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1007", //uid
  },
]


let chatMsg1008 = [
  {
    headImg: require("@/assets/img/head_portrait6.png"),
    name: "Deepseek-reasoner",
    time: H_M_S,
    msg: " 您好，我是您的AI助手DeepSeek R1，我擅长英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1008", //uid
  },
]


let chatMsg1009 = [
  {
    headImg: require("@/assets/img/emoji/rocket.png"),
    name: "Gemini",
    time: H_M_S,
    msg: " 您好，我是您的AI助手Gemini，我擅长英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1009", //uid
  },
]


let chatMsg1010 = [
  {
    headImg: require("@/assets/img/emoji/shamrock.png"),
    name: "Qwq",
    time: H_M_S,
    msg: " 您好，我是您的AI助手Qwq，我擅长英文问题回答、文本摘要、信息提取、头脑风暴；若使用双问号？？提问则不直接回答而是提供熵减式的建议和引导；若使用三问号？？？提问则进行脱场景文档对话；若使用叹号！则对话末端综合及小模型红蓝深评后，大模型自动对齐一次小模型完成初闭环，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "1010", //uid
  },
]


let chatMsg3001 = [
  {
    headImg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    name: "Qwen3 32B模型",
    time: H_M_S,
    msg: " 您好，我是您的AI助手Qwen3-32B微调模型，我擅长英文问题回答、文本摘要、信息提取、头脑风暴，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "3001", //uid
  },
]

let chatMsg3002 = [
  {
    headImg: require("@/assets/img/emoji/smiling-face.png"),
    name: "llama3.1 8B单模",
    time: H_M_S,
    msg: " 您好，我是您的AI助手llama3.1 8B微调模型，我擅长英文问题回答、文本摘要、信息提取、头脑风暴，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "3002", //uid
  },
]

let chatMsg3003 = [
  {
    headImg: require("@/assets/img/emoji/thinking-face.png"),
    name: "llama3.3 70B模型",
    time: H_M_S,
    msg: " 您好，我是您的AI助手llama3.3 70B微调模型，我擅长英文问题回答、文本摘要、信息提取、头脑风暴，请问有什么可以帮助您？",
    //      msg: require("@/assets/img/emoji/slightly-smiling-face.png"),
    chatType: 0, //信息类型，0文字，1图片
    extend: {
      imgType: 1, //(1表情，2本地图片)
    },
    uid: "3003", //uid
  },
]

// 保存到localStorage
function saveCachedModels(models) {
  try {
    localStorage.setItem('modelList', JSON.stringify(models));
  } catch (error) {
    console.error('保存模型列表失败:', error);
  }
}

// 从localStorage获取
function getCachedModels() {
  try {
    const cached = localStorage.getItem('modelList');
    return cached ? JSON.parse(cached) : null;
  } catch (error) {
    console.error('获取缓存模型列表失败:', error);
    return null;
  }
}

// export const getModel = params => {
//   return modelList
// }

// 三窗口默认模型配置API
export const saveDefaultModelsConfig = (configData) => {
  return axios.post(`${API_BASE_URL}/api/save_default_models_config`, configData)
    .then(response => response.data);
};

export const getDefaultModelsConfig = () => {
  return axios.get(`${API_BASE_URL}/api/get_default_models_config`)
    .then(response => response.data);
};

export const saveSceneModelsConfig = (configData) => {
  return axios.post(`${API_BASE_URL}/api/save_scene_models_config`, configData)
    .then(response => response.data);
};

export const getSceneModelsConfig = () => {
  return axios.get(`${API_BASE_URL}/api/get_scene_models_config`)
    .then(response => response.data);
};

/** 长短记忆：手动触发 AutoDream（Admin / 测试） */
export const notebookMemoryAutodream = (payload) => {
  return axios.post(`${API_BASE_URL}/api/notebook_memory_autodream`, payload || {})
    .then(response => response.data);
};

export const notebookMemoryStatus = (payload) => {
  return axios.post(`${API_BASE_URL}/api/notebook_memory_status`, payload || {})
    .then(response => response.data);
};

export const getModel = params => {
  // 从modelManager获取
  const models = modelManager.getAllModels();
  console.log("缓存modelList_new：", models);
  
  // 如果获取到数据，保存到localStorage
  if (models && models.length > 0) {
    saveCachedModels(models);
  }

  // 尝试从localStorage获取
  const cachedModels = getCachedModels();
  if (cachedModels && cachedModels.length > 0) {
    console.log("使用缓存的modelList_new：", cachedModels);
    return cachedModels.map(ModelFormatter.toListFormat);
  }
  
  return models.map(ModelFormatter.toListFormat);
}

export const getLittleModel = params => {
  return LittleModelList
}

export const getMultimodalLittleModel = params => {
  return MultimodalLittleModelList
}

// 获取聊天信息
// export const getChatMsg = params => {
//   let id = params.modelsId
//   if (id == '1002')
//     return chatMsg1002
//   else if (id == '1003')
//     return chatMsg1003
//   else if (id == '1004')
//     return chatMsg1004
//   else if (id == '1005')
//     return chatMsg1005
//   else if (id == '1006')
//     return chatMsg1006
//   else if (id == '1007')
//     return chatMsg1007
//   else if (id == '1008')
//     return chatMsg1008
//   else if (id == '1009')
//     return chatMsg1009
//   else if (id == '1010')
//     return chatMsg1010
//   else if (id == '3001')
//     return chatMsg3001
//   else if (id == '3002')
//     return chatMsg3002
//   else if (id == '3003')
//     return chatMsg3003
//   else
//     return chatMsg1002
// }

// 使用Map作为全局缓存
const chatMsgCache = new Map();

export const getChatMsg = ({ modelsId }) => {
  // 先检查缓存中是否存在
  if (chatMsgCache.has(modelsId)) {
    return chatMsgCache.get(modelsId);
  }

  // 缓存中没有，生成新的数据
  const model = modelManager.getModelById(modelsId)
  console.log("是或不是缓存来的单model2", model)
  const chatMsg = [ModelFormatter.toChatFormat(model, H_M_S)];

  // 存入缓存
  chatMsgCache.set(modelsId, chatMsg);

  return chatMsg;
}

export const getTime = params => {
  var currentDate = new Date();

  var hours = currentDate.getHours(); // 获取当前小时（0-23），如18
  var minutes = currentDate.getMinutes(); // 获取当前分钟（0-59），如30
  var seconds = currentDate.getSeconds(); // 获取当前秒数（0-59），如45
  let H_M_S = hours + ":" + minutes + ":" + seconds
  return H_M_S
}

export const getDateTime = params => {
  var currentDate = new Date();

  var year = currentDate.getFullYear(); // 获取当前年份，如2022
  var month = currentDate.getMonth() + 1; // 获取当前月份，注意月份从0开始计算，所以要+1，如2表示3月份
  var day = currentDate.getDate(); // 获取当前日期，如15
  var hours = currentDate.getHours(); // 获取当前小时（0-23），如18
  var minutes = currentDate.getMinutes(); // 获取当前分钟（0-59），如30
  var seconds = currentDate.getSeconds(); // 获取当前秒数（0-59），如45
  let Y_M_D_H_M_S = year + "/" + month + "/" + day + " " + hours + ":" + minutes + ":" + seconds
  return Y_M_D_H_M_S
}




// 清理文本中的代码块
// 修改后的 cleanCodeBlocks 函数
function cleanCodeBlocks(text) {
  let cleanedText = text;
  
  // 处理thinking和checking块（超过100字符的）
  ['thinking', 'checking'].forEach(blockType => {
    const regex = new RegExp('```' + blockType + '([\\s\\S]*?)```', 'g');
    cleanedText = cleanedText.replace(regex, (match, content) => {
      // 如果内容超过100字符，则删除整个块
      return content.length > 100 ? '' : match;
    });
  });
  
  // 处理不带语言标记的代码块（超过100字符的）
  const allCodeBlockRegex = /```([^\n]*)\n([\s\S]*?)```/g;
  cleanedText = cleanedText.replace(allCodeBlockRegex, (match, tag, content) => {
    // 如果标记为空且内容超过100字符，则删除
    if (tag.trim() === '' && content.length > 100) {
      return '';
    }
    return match;
  });
  
  // 清理多余的换行
  cleanedText = cleanedText.replace(/\n{3,}/g, '\n\n');
  
  return cleanedText;
}


// Unicode 转义序列转回测试函数
function transformTest() {
  let A = '"{\\"status\\": \\"success\\", \\"result\\": \\"0.2_\\\\u7ea2_\\\\u7406\\\\u7531\\\\u8bae\\\\uff0c\\", \\"error_num\\": 0}"';
  console.log("测试1：", A);
  // 去除外层的引号，得到有效的 JSON 字符串
  let str = A.slice(1, -1);
  console.log("测试2：", str);
  // 移除内部的转义字符
  str = str.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  console.log("测试3：", str);

  const resultObject = JSON.parse(str);
  const decodedResult = decodeResult(resultObject.result);
  console.log("红蓝测试结果2：", decodedResult);
}

// 辅助函数，将编码转为中文字符
function decodeResult(resultString) {
  const decodedString = resultString.replace(/\\u([\d\w]{4})/gi, (match, grp) => {
    return String.fromCharCode(parseInt(grp, 16));
  });
  return decodedString;
}

async function modelHL(text) {
  // 在处理之前先清理代码块
  text = cleanCodeBlocks(text);
  
  // 调试测试转码的函数
  // transformTest()
  let formDataScene = new FormData();
  formDataScene.append('scene', localStorage.getItem('sceneName'));
  formDataScene.append('subScene', localStorage.getItem('subSceneName'));

  // 使用await获取场景摘要
  const response = await getSceneSummary(formDataScene);

  if (response.error_num === 0) {
    let sceneName = localStorage.getItem('sceneName')
    let subSceneName = localStorage.getItem('subSceneName')
    console.log("场景子场景摘要获取成功：", sceneName, subSceneName, response.summary)
    text = "目前的场景是：" + sceneName + "，子场景阶段是：" + subSceneName + "\n其摘要为：" + response.summary + "\n\n待评文本如下：\n" + text

    // 此方式NKCN应用服务器可行
    try {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('text', text);

      // 使用 await 等待 execute_commands 执行完成
      const data = await execute_commands(formData);

      // 这个error_num代表execute_commands传至NKCN后端执行是否成功
      if(data['error_num'] === 0) {
        // 而这个resultObject.error_num代表在8卡服务器那边推理是否成功
        console.log("红蓝测试结果1: ", data['data'], data['data'].length)
        let str = data['data'].trim();   // 这一步很重要
        str = str.slice(1, -1);
        console.log("处理1：", str, str.length);
        str = str.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
        console.log("处理2：", str, str.length);
        const resultObject = JSON.parse(str);
        const decodedResult = decodeResult(resultObject.result);
        console.log("红蓝测试结果2：", decodedResult);
        return decodedResult
      } else {
        return "fail"
      }
    } catch (error) {
      console.error("An error occurred:", error);
      return "fail";
    }
    

    // 此方式本地调试可行
    // try {
    //   const response = await fetch((process.env.VUE_APP_SERVICE_8000_INVOKE_RATE_URL || "http://localhost:8000/invoke_rate"), {
    //     method: 'POST',
    //     headers: {
    //       'Content-Type': 'application/json; charset=utf-8',
    //     },
    //     body: JSON.stringify({
    //       username: localStorage.getItem('userId'),
    //       text: text,
    //     }),
    //   });

    //   if (response.ok) {
    //     const data = await response.json(); // 解析 JSON 响应体
    //     const resultObject = JSON.parse(data); // 解码返回的 JSON
    //     const decodedResult = decodeResult(resultObject.result); // 解码处理后的结果
    //     console.log("红蓝测试结果：", decodedResult);
    //     return decodedResult; // 返回最终结果
    //   } else {
    //     throw new Error('Network response was not ok');
    //   }
    // } catch (error) {
    //   console.error('There has been a problem with your fetch operation:', error);
    //   return "fail"; // 错误时返回 "fail"
    // }
    

  } else {
    console.log("场景子场景摘要获取失败")
  }




  // 废弃
  // fetch((process.env.VUE_APP_SERVICE_8000_INVOKE_RATE_URL || "http://localhost:8000/invoke_rate"), {
  //   method: 'POST',
  //   headers: {
  //     'Content-Type': 'application/json; charset=utf-8'
  //   },
  //   body: JSON.stringify({
  //     username: localStorage.getItem('userId'),
  //     // text: "该文本讨论了如何结合中医和时间来获取健康信息，并通过代码示例展示了实现方法。具体内容包括：\
  //     //       1. **简述中医与时间的关系**：一天24小时被分为12个时辰，每个时辰对应一个经络系统。\
  //     //       2. **代码示例一**：获取当前时辰、对应经络及其他信息。\
  //     //       3. **代码示例二**：显示包含五种联系因素的信息，如心率、血压等。\
  //     //       4. **代码示例三**：绘制图形化表示（如钟表）来直观显示这些信息。\
  //     //       总结，通过这些步骤提供了一套基础框架，指导学生将复杂问题逐步拆解成小问题，构建嵌入式应用系统。"
  //     text: text
  //   }),
  // })
  // .then(response => {
  //   // console.log(response)
  //   if (response.ok) {
  //     return response.json(); // 解析 JSON 响应体
  //   }
  // })
  // .then(data => {
  //   // 解码 Unicode 字符串
  //   const resultObject = JSON.parse(data);
  //   const decodedResult = decodeResult(resultObject.result);
  //   console.log("红蓝测试结果：", decodedResult);
  //   return decodedResult
  //   // if(resultObject.error_num === 0) {
  //   //   this.$message.success('红蓝评测模型调用测试成功');
  //   // } else {
  //   //   this.$message.error('红蓝评测模型调用测试失败');
  //   // }
  // })
  // .catch(error => {
  //   console.error('There has been a problem with your fetch operation:', error);
  //   return "fail"
  // });

  // 废弃
  // let formData = new FormData();
  // formData.append('username', localStorage.getItem('userId'));
  // formData.append('text', text);
  // execute_commands(formData).then(data => {
  //   // 这个error_num代表execute_commands传至NKCN后端执行是否成功
  //   if(data['error_num'] === 0) {
  //     // 而这个resultObject.error_num代表在8卡服务器那边推理是否成功
  //     console.log("红蓝测试结果1: ", data['data'], data['data'].length)
  //     let str = data['data'].trim();   // 这一步很重要
  //     str = str.slice(1, -1);
  //     console.log("处理1：", str, str.length);
  //     str = str.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
  //     console.log("处理2：", str, str.length);
  //     const resultObject = JSON.parse(str);
  //     const decodedResult = decodeResult(resultObject.result);
  //     console.log("红蓝测试结果2：", decodedResult);
  //     return decodedResult
  //   } else {
  //     return "fail"
  //   }
  // }).catch(error => {
  //   console.error("An error occurred:", error); // 错误处理
  //   return "fail"
  // });
}

export function get_model_eval(formData) {
  const controller = new AbortController();
  // 设置超时（原配置 300,000,000ms ≈ 3.5天）
  const timeoutId = setTimeout(() => {
    controller.abort();
    console.error('Request timed out');
  }, 300000000);

  console.log("查看内容", formData)

  return fetch(`${API_BASE_URL}/api/get_model_eval`, {
    method: 'POST',
    body: formData,
    signal: controller.signal,
    credentials: 'omit',
  }).finally(() => {
    clearTimeout(timeoutId);
  });
}

// 新增流式处理函数
// 本地调试环境下的流式处理函数
// async function modelHLStream(text, callback, addMode = '', includeDPart = true, gcsContentMode = 'simple_reason', dContentMode = 'inspire_framework', textForD = null, abortSignal = null) {
//   // 在处理之前先清理代码块
//   text = cleanCodeBlocks(text);
//   // 截断text，如果超过4400字符
//   if (text.length > 4400) {
//     text = text.substring(0, 4397) + '...';
//   }

//   // 如果提供了textForD，也清理
//   if (textForD) {
//     textForD = cleanCodeBlocks(textForD);
//     // 同样截断textForD，如果超过4400字符
//     if (textForD.length > 4400) {
//       textForD = textForD.substring(0, 4397) + '...';
//     }
//   }

//   console.log("xxxxxxxxx111:", text)
//   console.log("xxxxxxxxx222:", textForD)

//   try {
//     // 使用传入的 signal 或创建新的 AbortController
//     const controller = abortSignal ? null : new AbortController();
//     const signal = abortSignal || controller?.signal;
    
//     // 发起fetch请求
//     const response = await fetch((process.env.VUE_APP_SERVICE_8000_INVOKE_RATE_STREAM_URL || "http://localhost:8000/invoke_rate_stream"), {
//       method: 'POST',
//       headers: {
//         'Content-Type': 'application/json; charset=utf-8',
//         'Accept': 'text/event-stream',
//       },
//       body: JSON.stringify({
//         username: localStorage.getItem('userId'),
//         text: text,  // GCS输入
//         text_for_d: textForD || text,  // D输入（新增）
//         add_mode: addMode,
//         include_d_part: includeDPart,
//         gcs_content_mode: gcsContentMode,
//         d_content_mode: dContentMode
//       }),
//       signal: signal, // 使用传入的或内部创建的 signal
//     });

//     if (!response.ok) {
//       throw new Error('Network response was not ok');
//     }

//     // 处理流式响应
//     const reader = response.body.getReader();
//     const decoder = new TextDecoder('utf-8');
//     let buffer = '';
//     let fullResult = '';

//     // 处理数据块
//     while (true) {
//       const { done, value } = await reader.read();
//       if (done) break;
      
//       // 解码数据
//       const chunk = decoder.decode(value, { stream: true });
//       buffer += chunk;
      
//       // 处理SSE格式的数据，按行分割
//       const lines = buffer.split('\n');
//       buffer = lines.pop() || ''; // 最后一行可能不完整，保留到buffer
      
//       for (const line of lines) {
//         if (line.trim() === '') continue;
        
//         if (line.startsWith('data: ')) {
//           const data = line.substring(6).trim();
          
//           // 检查是否是结束信号
//           if (data === '[DONE]') {
//             console.log('[本地调试] 准备处理回调', fullResult);
//             // 解析评分信息（如果有）
//             if (addMode && fullResult.includes('置信度') && fullResult.includes('腐烂度')) {
//               // const match = fullResult.match(/(\d+\.?\d*)_[^_]+_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)_/);
//               // if (match) {
//               //   const scores = {
//               //     red_blue_score: parseFloat(match[1]),  // 红蓝评分
//               //     confidence_score: parseFloat(match[2]),
//               //     rot_score: parseFloat(match[3])
//               //   };
//               //   console.log('[本地调试] 解析到评分:', scores);
//               //   if (callback.onScores) {
//               //     callback.onScores(scores);
//               //   }
//               // }
//               // 尝试新格式：【打分结果】X.X_紫_置信度X.X_腐烂度X.X
//               console.log('[本地调试] 准备处理回调');
//               let newFormatMatch = fullResult.match(/【打分结果】(\d+\.?\d*)_([红蓝紫绿])_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)/);
//               if (newFormatMatch) {
//                 const scores = {
//                   red_blue_score: parseFloat(newFormatMatch[1]),
//                   confidence_score: parseFloat(newFormatMatch[3]),
//                   rot_score: parseFloat(newFormatMatch[4])
//                 };
//                 console.log('[本地调试] 使用新格式解析到评分:', scores);
//                 if (callback.onScores) {
//                   callback.onScores(scores);
//                 }
//               } else {
//                 // 尝试旧格式：X.X_紫_置信度X.X_腐烂度X.X（后面可能跟**或其他字符）
//                 let oldFormatMatch = fullResult.match(/(\d+\.?\d*)_([红蓝紫绿])_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)/);
//                 if (oldFormatMatch) {
//                   const scores = {
//                     red_blue_score: parseFloat(oldFormatMatch[1]),
//                     confidence_score: parseFloat(oldFormatMatch[3]),
//                     rot_score: parseFloat(oldFormatMatch[4])
//                   };
//                   console.log('[本地调试] 使用旧格式解析到评分:', scores);
//                   if (callback.onScores) {
//                     callback.onScores(scores);
//                   }
//                 } else {
//                   console.log('[本地调试] 旧格式匹配失败，fullResult中的评分部分:', fullResult.match(/(\d+\.?\d*_[红蓝紫绿]_置信度\d+\.?\d*_腐烂度\d+\.?\d*)/));
//                 }
//               }
//             }

//             // 处理最终结果
//             try {
//               // 如果结果是JSON字符串，需要解析
//               let resultObject = JSON.parse(fullResult);
//               const decodedResult = decodeResult(resultObject.result);
//               console.log("调用正确性测试A", decodedResult)
//               callback(decodedResult, true);
//             } catch (e) {
//               // 不是有效的JSON，直接使用原始结果
//               console.log("调用正确性测试B", fullResult)
//               callback(fullResult, true);
//             }
            
//             controller.abort(); // 中止请求
//             return fullResult;
//           }
          
//           try {
//             const parsedData = JSON.parse(data);
//             if (parsedData.content) {
//               fullResult += parsedData.content;
//               callback(parsedData.content, false);
//             }
//           } catch (e) {
//             console.error('解析数据出错:', e, 'data:', data);
//           }
//         }
//       }
//     }
    
//     // 如果正常结束但没有收到[DONE]信号
//     if (fullResult) {
//       try {
//         // 尝试解析和处理最终结果
//         console.log("正常结束但没有收到[DONE]信号")
//         let resultStr = fullResult;
//         if (resultStr.startsWith('"') && resultStr.endsWith('"')) {
//           resultStr = resultStr.slice(1, -1);
//         }
//         resultStr = resultStr.replace(/\\"/g, '"').replace(/\\\\/g, '\\');
        
//         const resultObject = JSON.parse(resultStr);
//         const decodedResult = decodeResult(resultObject.result);
//         console.log("调用正确性测试C", decodedResult)
//         callback(decodedResult, true);
//         return decodedResult;
//       } catch (e) {
//         console.error('最终处理结果出错:', e);
//         callback(fullResult, true);
//         return fullResult;
//       }
//     }
    
//     return "fail";
//   } catch (error) {
//     console.error('流式处理请求出错:', error);
//     callback("fail", true);
//     return "fail";
//   }
// }




// 应用服务器环境在处理之下的流式处理函数
async function modelHLStream(text, callback, addMode = '', includeDPart = true, gcsContentMode = 'simple_reason', dContentMode = 'inspire_framework', textForD = null, abortSignal = null) {
  // 前先清理代码块
  text = cleanCodeBlocks(text);
  // 截断text，如果超过4000字符
  if (text.length > 4000) {
    text = text.substring(0, 4000) + '...';
  }

  // 如果提供了textForD，也清理
  if (textForD) {
    textForD = cleanCodeBlocks(textForD);
    // 同样截断textForD，如果超过4000字符
    if (textForD.length > 4000) {
      textForD = textForD.substring(0, 4000) + '...';
    }
  }

  return new Promise((resolve, reject) => {
    let eventSource = null; // 在外层声明，以便在 abort 事件中访问

    // 监听外部中断信号
    const abortHandler = () => {
      console.log('[SSE流式] 收到外部中断信号');
      if (eventSource) {
        eventSource.close();
        reject(new DOMException('SSE流式请求被用户中断', 'AbortError'));
      }
    };

    if (abortSignal) {
      if (abortSignal.aborted) {
        // 信号已经被中止
        return reject(new DOMException('SSE流式请求被用户中断', 'AbortError'));
      }
      abortSignal.addEventListener('abort', abortHandler);
    }

    try {
      // 创建一个能够生成唯一ID的函数
      const generateUniqueId = () => {
        return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
      };
      // 生成唯一的会话ID
      const sessionId = generateUniqueId();
      console.log("小模型末端流式会话ID: ", sessionId)

      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('text', text);  // GCS输入
      formData.append('text_for_d', textForD || text);  // D输入（如果未提供则与GCS相同）
      formData.append('sessionId', sessionId);
      formData.append('add_mode', addMode);  // 添加评估模式参数
      formData.append('include_d_part', includeDPart);  // 添加D部分参数
      formData.append('gcs_content_mode', gcsContentMode);  // 添加GCS内容模式参数
      formData.append('d_content_mode', dContentMode);  // 添加D内容模式参数

      // 使用 await 等待 execute_commands 执行完成
      execute_commands_stream_sessionId(formData).then(response => {
        if (response.error_num === 0) {
          // this.$message.success('对话窗口模型协同末端，进行红蓝卡标引控');
          // 构建查询参数
          // const params = new URLSearchParams();
          // params.append('username', localStorage.getItem('userId'));
          // params.append('text', text);
          
          const baseUrl = window.location.origin;
          const url = `${baseUrl}/api/execute_commands_stream?sessionId=${sessionId}`;
          // const url = `${baseUrl}/api/execute_commands_stream?${params.toString()}`;
          
          console.log('连接到SSE端点:', url);
          
          // 创建EventSource连接
          eventSource = new EventSource(url); // 使用外层声明的变量
          let fullResult = '';
          let isCompleted = false; // 添加完成标志，防止重复调用

          // 累积缓冲区和计数器
          let buffer = '';
          const updateInterval = 5; // 每接收到5个消息更新一次
          let messageCount = 0;
          let lastUpdateTime = Date.now();
          const minUpdateInterval = 200; // 最小更新间隔(ms)

          // 清理函数
          const cleanup = () => {
            if (abortSignal) {
              abortSignal.removeEventListener('abort', abortHandler);
            }
            if (eventSource) {
              eventSource.close();
            }
          };

          // 超时处理（先定义，后面需要在收到[DONE]时清除）
          const timeout = setTimeout(() => {
            if (isCompleted) return; // 如果已完成，忽略超时
            isCompleted = true;
            console.log('SSE连接超时');
            // 处理剩余缓冲区
            if (buffer.length > 0) {
              console.log("剩余缓冲区内容：", buffer)
              callback(buffer, false);
            }

            // eventSource.close();
            cleanup();
            if (fullResult) {
              callback(fullResult, true);
              resolve(fullResult);
            } else {
              callback("fail", true);
              reject("fail");
            }
          }, 60000); // 60秒超时
          
          // 批量更新函数
          const processBatch = () => {
            if (buffer.length > 0) {
              callback(buffer, false);
              buffer = '';
              messageCount = 0;
              lastUpdateTime = Date.now();
            }
          };
          
          // 处理消息
          eventSource.onmessage = (event) => {
            try {
              if (isCompleted) return; // 如果已完成，忽略后续消息
              
              const data = event.data;
              console.log('收到SSE消息:', data.substring(0, 50) + (data.length > 50 ? '...' : ''));
              
              // 检查结束信号
              if (data === '[DONE]') {
                console.log('收到结束信号');
                isCompleted = true;
                clearTimeout(timeout); // 清除超时计时器
                
                // 处理最后的缓冲区
                if (buffer.length > 0) {
                  callback(buffer, false);
                }
                cleanup();
                callback(fullResult, true);
                resolve(fullResult);
                return;
              }
              
              // 处理正常数据
              try {
                const parsedData = JSON.parse(data);
                if (parsedData.content !== undefined) {
                  fullResult += parsedData.content;
                  // callback(parsedData.content, false);
                  buffer += parsedData.content;
                  messageCount++;
                  
                  // 检查是否应该更新
                  const now = Date.now();
                  const shouldUpdate = 
                    messageCount >= updateInterval || // 累积足够的消息
                    now - lastUpdateTime >= minUpdateInterval; // 或者达到最小时间间隔
                  
                  if (shouldUpdate) {
                    processBatch();
                  }
                } else if (parsedData.scores !== undefined) {
                  // 处理评分信息（置信度和腐烂度）
                  console.log('收到评分信息:', parsedData.scores);
                  console.log('callback.onScores存在吗:', typeof callback.onScores);
                  // 将评分信息附加到回调中，用于后续显示
                  if (callback.onScores) {
                    console.log('调用callback.onScores');
                    callback.onScores(parsedData.scores);
                  } else {
                    console.log('callback.onScores不存在，无法调用');
                  }
                } else if (parsedData.error) {
                  console.error('收到错误:', parsedData.error);
                  cleanup();
                  callback("fail", true);
                  reject("fail");
                }
              } catch (e) {
                console.log('无法解析为JSON，作为普通文本处理:', data);
                fullResult += data;
                // callback(data, false);
                buffer += data;
                messageCount++;
                
                const now = Date.now();
                if (messageCount >= updateInterval || now - lastUpdateTime >= minUpdateInterval) {
                  processBatch();
                }
              }
            } catch (e) {
              console.error('处理消息出错:', e);
            }
          };
          
          // 错误处理
          eventSource.onerror = (error) => {
            if (isCompleted) return; // 如果已完成，忽略错误
            isCompleted = true;
            clearTimeout(timeout); // 清除超时计时器
            
            console.error('SSE连接错误:', error);
            // 处理剩余缓冲区
            if (buffer.length > 0) {
              callback(buffer, false);
            }

            cleanup();
            if (fullResult) {
              callback(fullResult, true);
              resolve(fullResult);
            } else {
              callback("fail", true);
              reject("fail");
            }
          };

        } else {
          // this.$message.error('对话窗口模型协同末端，红蓝卡标引控不成功');
          cleanup();
          reject("execute_commands_stream_sessionId failed");
        }
      });
      
    } catch (error) {
      console.error('初始化流式处理错误:', error);
      if (abortSignal) {
        abortSignal.removeEventListener('abort', abortHandler);
      }
      callback("fail", true);
      reject("fail");
    }
  });
}




// 应用服务器环境下的流式处理函数（原先回答后直接综述没问题，改为问答后都获取深评并都迭代再综述后，有bug）
// async function modelHLStream(text, callback) {
//   // 在处理之前先清理代码块
//   text = cleanCodeBlocks(text);

//   return new Promise((resolve, reject) => {
//     try {
//       // 创建一个能够生成唯一ID的函数
//       const generateUniqueId = () => {
//         return Date.now().toString(36) + Math.random().toString(36).substr(2, 5);
//       };
//       // 生成唯一的会话ID
//       const sessionId = generateUniqueId();
//       console.log("小模型末端流式会话ID: ", sessionId)

//       let formData = new FormData();
//       formData.append('username', localStorage.getItem('userId'));
//       formData.append('text', text);
//       formData.append('sessionId', sessionId);

//       // 使用 await 等待 execute_commands 执行完成
//       execute_commands_stream_sessionId(formData).then(response => {
//         if (response.error_num === 0) {
//           // this.$message.success('对话窗口模型协同末端，进行红蓝卡标引控');
//           // 构建查询参数
//           // const params = new URLSearchParams();
//           // params.append('username', localStorage.getItem('userId'));
//           // params.append('text', text);
          
//           const baseUrl = window.location.origin;
//           const url = `${baseUrl}/api/execute_commands_stream?sessionId=${sessionId}`;
//           // const url = `${baseUrl}/api/execute_commands_stream?${params.toString()}`;
          
//           console.log('连接到SSE端点:', url);
          
//           // 创建EventSource连接
//           const eventSource = new EventSource(url);
//           let fullResult = '';

//           // 累积缓冲区和计数器
//           let buffer = '';
//           const updateInterval = 5; // 每接收到5个消息更新一次
//           let messageCount = 0;
//           let lastUpdateTime = Date.now();
//           const minUpdateInterval = 200; // 最小更新间隔(ms)
//           // 批量更新函数
//           const processBatch = () => {
//             if (buffer.length > 0) {
//               callback(buffer, false);
//               buffer = '';
//               messageCount = 0;
//               lastUpdateTime = Date.now();
//             }
//           };
          
//           // 处理消息
//           eventSource.onmessage = (event) => {
//             try {
//               const data = event.data;
//               console.log('收到SSE消息:', data.substring(0, 50) + (data.length > 50 ? '...' : ''));
              
//               // 检查结束信号
//               if (data === '[DONE]') {
//                 console.log('收到结束信号');
//                 // 处理最后的缓冲区
//                 if (buffer.length > 0) {
//                   callback(buffer, false);
//                 }
//                 eventSource.close();
//                 callback(fullResult, true);
//                 resolve(fullResult);
//                 return;
//               }
              
//               // 处理正常数据
//               try {
//                 const parsedData = JSON.parse(data);
//                 if (parsedData.content !== undefined) {
//                   fullResult += parsedData.content;
//                   // callback(parsedData.content, false);
//                   buffer += parsedData.content;
//                   messageCount++;
                  
//                   // 检查是否应该更新
//                   const now = Date.now();
//                   const shouldUpdate = 
//                     messageCount >= updateInterval || // 累积足够的消息
//                     now - lastUpdateTime >= minUpdateInterval; // 或者达到最小时间间隔
                  
//                   if (shouldUpdate) {
//                     processBatch();
//                   }
//                 } else if (parsedData.error) {
//                   console.error('收到错误:', parsedData.error);
//                   eventSource.close();
//                   callback("fail", true);
//                   reject("fail");
//                 }
//               } catch (e) {
//                 console.log('无法解析为JSON，作为普通文本处理:', data);
//                 fullResult += data;
//                 // callback(data, false);
//                 buffer += data;
//                 messageCount++;
                
//                 const now = Date.now();
//                 if (messageCount >= updateInterval || now - lastUpdateTime >= minUpdateInterval) {
//                   processBatch();
//                 }
//               }
//             } catch (e) {
//               console.error('处理消息出错:', e);
//             }
//           };
          
//           // 错误处理
//           eventSource.onerror = (error) => {
//             console.error('SSE连接错误:', error);
//             // 处理剩余缓冲区
//             if (buffer.length > 0) {
//               callback(buffer, false);
//             }

//             eventSource.close();
//             if (fullResult) {
//               callback(fullResult, true);
//               resolve(fullResult);
//             } else {
//               callback("fail", true);
//               reject("fail");
//             }
//           };
          
//           // 超时处理
//           const timeout = setTimeout(() => {
//             console.log('SSE连接超时');
//             // 处理剩余缓冲区
//             if (buffer.length > 0) {
//               console.log("剩余缓冲区内容：", buffer)
//               // callback(buffer, false);
//             }

//             eventSource.close();
//             if (fullResult) {
//               callback(fullResult, true);
//               resolve(fullResult);
//             } else {
//               callback("fail", true);
//               reject("fail");
//             }
//           }, 60000); // 60秒超时
          
//           // 连接关闭时清除超时
//           eventSource.addEventListener('close', () => {
//             clearTimeout(timeout);
//           });

//         } else {
//           // this.$message.error('对话窗口模型协同末端，红蓝卡标引控不成功');
//         }
//       });
      
//     } catch (error) {
//       console.error('初始化流式处理错误:', error);
//       callback("fail", true);
//       reject("fail");
//     }
//   });
// }

// 根据小模型ID获取服务器URL
function getSmallModelServerUrl(model_id) {
  if (model_id && String(model_id) === "3007") {
    return (process.env.VUE_APP_SERVICE_8000_URL || "http://localhost:8000");
  } else {
    return (process.env.VUE_APP_SERVICE_8000_URL || "http://localhost:8000");
  }
}

// 深度建议生成函数
async function getDepthSuggestion(input_text, user_name, task_type = "qa") {
  try {
    // console.log(`[深度建议] 开始生成，用户: ${user_name}, 任务类型: ${task_type}, 输入长度: ${input_text.length}`);
    // 从localStorage获取当前选择的小模型ID
    const model_id = localStorage.getItem('currentLittleModelId') || "3003";
    console.log(`[深度建议] 开始生成，用户: ${user_name}, 任务类型: ${task_type}, 输入长度: ${input_text.length}, 模型ID: ${model_id}`);
    
    if (USE_BACKEND_DEPTH_SUGGESTION) {
      // 应用服务器方式：调用NKCN后端API
      const response = await fetch(`${API_BASE_URL}/api/get_depth_suggestion`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
        },
        body: JSON.stringify({
          input_text: input_text,
          user_name: user_name,
          task_type: task_type
        }),
      });

      if (response.ok) {
        const result = await response.json();
        if (result.error_num === 0) {
          const suggestion = result.suggestion || '';
          console.log(`[深度建议] 应用服务器方式生成成功`);
          return suggestion;
        } else {
          console.log(`[深度建议] 应用服务器方式生成失败: ${result.message || '未知错误'}`);
          return '';
        }
      } else {
        console.log(`[深度建议] 应用服务器方式API调用失败: HTTP ${response.status}`);
        return '';
      }
    } else {
      // 本地调试方式：直接fetch访问中转服务器
      // const response = await fetch((process.env.VUE_APP_SERVICE_8000_GET_DEPTH_SUGGESTION_URL || "http://localhost:8000/get_depth_suggestion"), {
      const serverUrl = getSmallModelServerUrl(model_id);
      const response = await fetch(`${serverUrl}/get_depth_suggestion`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
        },
        body: JSON.stringify({
          input_text: input_text,
          user_name: user_name,
          task_type: task_type
        }),
      });

      if (response.ok) {
        const result = await response.json();
        if (result.error_num === 0) {
          const suggestion = result.suggestion || '';
          console.log(`[深度建议] 本地调试方式生成成功`);
          return suggestion;
        } else {
          console.log(`[深度建议] 本地调试方式生成失败: ${result.message || '未知错误'}`);
          return '';
        }
      } else {
        console.log(`[深度建议] 本地调试方式API调用失败: HTTP ${response.status}`);
        return '';
      }
    }
  } catch (error) {
    console.error(`[深度建议] 生成异常: ${error}`);
    return '';
  }
}

// 导出函数
export { modelHL, modelHLStream, getDepthSuggestion };