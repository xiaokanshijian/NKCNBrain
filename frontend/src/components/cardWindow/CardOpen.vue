<template>
  <ChatWindow ref="ChatWindow" style="display: none;"></ChatWindow>
  <div class="notebook-card" :class="{ 'flashing': needflashing || needMultiFlashing }" shadow="hover">
    <div class="card-top">
      <div class="card-top-left">
        <div class="card-top-from">
          <span>
            <i class="card-top-from-img"></i>
          </span>
          <span class="card-top-from-text" @click="onCardClick">{{ replaceTopTip(title) }}</span>
          <div class="card-merge-info" v-if="model_id < 0">
            <span class="merge-info-text">融合数量: {{ -model_id }}</span>
            <span class="merge-info-text">迭代次数: {{ -status - 1 }}</span>
          </div>
        </div>
        <div class="card-top-title" @click="onCardClick">
          {{ (contentTitle !== "") ? contentTitle : replaceTitle(title) }}
        </div>
      </div>

      <div class="card-rate">
        <span class="card-rate-right" ref="tooltipTarget">
          配置
          <div v-if="showTooltip" class="tooltip">
            {{ getCustomTitle }}
            <div class="nav-button">
              <el-button @click="handleClick">点击查看参数</el-button>
            </div>
          </div>
        </span>

        <span class="card-rate-left-single" :style="{ backgroundColor: color }" @click="turnToCardHL" v-if="scoreSFT === -1">
          <template v-if="this.score !== -2">
            {{ this.score }}
          </template>
          <img v-else src="@/assets/img/chatwindow/card_waiting_bigger.gif" style="width: 100%; height: 100%; object-fit: contain;"/>
        </span>
        <div class="card-rate-middle" v-if="scoreSFT !== -1">
          <span class="card-rate-left" :style="{ backgroundColor: colorSFT }" @click="turnToCardHLSFT">
            {{ scoreSFT }}
          </span>
          <span class="card-rate-left" :style="{ backgroundColor: color }" @click="turnToCardHL">
            {{ this.score }}
          </span>
        </div>

        <span class="card-rate-history" ref="historyTipTarget" @click="showHistory">
          历史
          <div v-if="showHistoryTip" class="tooltip">
            对话历史
            <div class="nav-button">
              <el-button @click="backHistoryClicked">点击回溯历史</el-button>
            </div>
          </div>
        </span>
      </div>

      <div class="card-top-right">
        <div class="card-top-right-button" :class="{ 'checked': checked }" @click="onCheckboxChange"></div>
        <div class="model-info-text" @click="onCardClick" v-if="(contentTitle !== '')">
          {{ replaceTitle(title) }}
        </div>
      </div>
    </div>


    <!-- 正文内容 -->
    <div class="card-content" @click="onCardClick">
      <div class="card-content-text" v-if="!isContentExpanded">
        {{ content }}
      </div>
    </div>

    <div class="card-down">
      <button class="card-combine-btn" @click="textTo500">转500字</button>
      <button class="card-summarize-btn" @click="textTo1000">转1000字</button>
      <button class="card-study-guide-btn" @click="textTo1500">转1500字</button>
      <span style="font-size: 12px; float: right; line-height: 22px; vertical-align: middle; 
        color: #5C4033; text-shadow: 0.5px 0.5px 1px rgba(0, 0, 0, 0.5);">
        字数：{{ wordCount }}
      </span>
    </div>


  </div>
  <div v-if="showHistoryDialog" class="history-dialog">
    <div class="history-dialog-header">
      <h2>对话历史</h2>
      <div class="close" @click="hideHistory">&times;</div>
    </div>
    <div class="chat-container">
      <div v-for="(item, index) in this.cardInfo.history" :key="index" class="chat-item">
        <div class="file-list">
          <h4>文件列表：</h4>
          <ul>
            <li v-for="file in item.filelist" :key="file">{{ file }}</li>
          </ul>
        </div>
        <div class="message">
          <h4>消息：</h4>
          <p>{{ item.message }}</p>
        </div>
        <div class="ai-message">
          <h4>AI回答：</h4>
          <div v-if="Array.isArray(item.AImessage)">
            <ul>
              <li v-for="reply in item.AImessage" :key="reply">{{ reply }}</li>
            </ul>
          </div>
          <div v-else>
            <p>{{ item.AImessage }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="card-dialog" v-if="isCardDialogVisible" ref="cardDialog">
    <div class="card-dialog-header">
      <h2>{{ replaceTitle(cardInfo.title) }}</h2>
      <div class="close" @click="hideCardDialog">&times;</div>
    </div>
    <div class="card-dialog-body">
      <div style="background-color: #e6f2ff; padding: 15px; border-radius: 8px;">
        <p><b>创建日期:</b> {{ cardInfo.datetime }} </p>
        <p><b>所有者:</b> {{ cardInfo.username }}</p>
        <p><b>卡片内容标题:</b> {{ cardInfo.contentTitle }}</p>
        <p><b>关键词:</b> {{ cardInfo.keyWords }}</p>
      </div>
      <div style="padding: 15px; border-radius: 8px;">
        <h3>主体部分</h3>
      </div>
      <div style="background-color: #f0f0f0; padding: 15px; border-radius: 8px;">
        <p><b>卡片内容：&nbsp;&nbsp;
          <button @click="speakTextBegin">从头开始朗读</button>
          <button @click="stopSpeech">停止朗读</button>
          <br></b>
          <!-- {{ cardInfo.content }} -->
          <AnswerParser :answer="cardInfo.content" @startReading="startFromIndex" @doubleClickOver="doubleClickOver"/>
        </p>
      </div>
      <div style="padding: 15px; border-radius: 8px;">
        <h3>卡标部分</h3>
      </div>
      <div style="background-color: #9966cc; padding: 10px; border-radius: 8px;">
        <p ref="scoreSFT" :style="textStyleSFT"><b>红蓝卡标深评打分(微调Qwen3 32b):<br></b>{{ cardInfo.scoreSFT < 0 ? '?' : cardInfo.scoreSFT }}</p>
      </div>
      <div style="background-color: #e6f0ff; padding: 10px; border-radius: 8px;">
        <p v-if="splitReasonSFT.length > 0" :style="textStyleSFT"><b>红蓝深评理由:<br></b> {{ splitReasonSFT[0] || "正在打分，等待解析打分理由" }} </p>
      </div>
      <div style="background-color: #fff9d6; padding: 10px; border-radius: 8px;">
        <p v-if="splitReasonSFT.length > 1" :style="textStyleSFT"><b>红蓝深评改进建议:&nbsp;&nbsp;<button @click="speakTextBeginSFT">从头开始朗读</button><button @click="stopSpeech">停止朗读</button><br></b> 
          <!-- {{ splitReasonSFT[1] || "正在打分，等待解析改进建议" }}  -->
          <AnswerParser 
            :answer="splitReasonSFT[1] || '正在打分，等待解析改进建议'" 
            @startReading="startFromIndexSFT" 
            @doubleClickOver="doubleClickOver"
          />
        </p>
      </div>
      <br><br>
      <div style="background-color: #baa6e0; padding: 10px; border-radius: 8px;">
        <p :style="textStyle"><b>红蓝卡标浅评打分(GPT4o prompt):<br></b>{{ this.score }}</p>
      </div>
      <div style="background-color: #f5faff; padding: 10px; border-radius: 8px;">
        <p v-if="splitReason.length > 0" :style="textStyle"><b>红蓝浅评理由:<br></b> {{ splitReason[0] || "正在打分，等待解析打分理由" }} </p>
      </div>
      <div style="background-color: #fffdf0; padding: 10px; border-radius: 8px;">
        <p v-if="splitReason.length > 1" :style="textStyle"><b>红蓝浅评改进建议:<br></b> {{ splitReason[1] || "正在打分，等待解析改进建议" }} </p>
      </div>
    </div>
    <br><br>
    <div class="card-button">
      <button class="card-edit" @click="editContent">编辑内容</button>
      <button class="card-delete" @click="deleteCard">删除卡片</button>
      <button class="card-history" @click="backHistory(this.cardInfo.history, title)">回溯历史</button>
      <button class="card-paste" @click="copyContentWithEmptyLines">复制卡片</button>
    </div>
  </div>

  <el-dialog v-model="showEditDialog" class="editContentDialog" :close-on-click-modal="false"
    :close-on-press-escape="false">
    <h1 class="createNotebookTitle">修改卡片文本</h1>
    <el-form :model="editForm" label-width="80px">
      <el-form-item label="内容标题" style="margin-top: 10px;">
        <el-input :rows="8" v-model="editForm.contentTitle"></el-input>
      </el-form-item>
      <el-form-item label="关键词" style="margin-top: 10px;">
        <el-input :rows="8" v-model="editForm.keyWords"></el-input>
      </el-form-item>

      <el-form-item label="卡片内容">
        <el-input class="contentInput" type="textarea" :rows="8" v-model="editForm.content"></el-input>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="footer">
        <el-button class="cancelButton" @click="cancelDialog">取 消</el-button>
        <el-button class="editButton" type="primary" @click="saveContent">确 定</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script>
import { get_card, set_card } from "@/api/card/get_card"
import { card_evalSFT } from "@/api/card/send_card"
import { ElButton, ElDialog, ElForm, ElFormItem, ElInput } from 'element-plus'
import { chageContent, deleteChoosedCard, changeText } from "@/api/card_zym/card_js";
import { getSceneByName } from "@/views/pages/mainHome/my_js";
import { getDateTime, modelHL } from "@/api/getData";
import AnswerParser from '@/components/chatWindow/AnswerParser.vue';

export default {
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    AnswerParser
  },
  data() {
    return {
      chosenContent: '', // 用于存储选中的内容

      doubleClick: false,
      textStyle: { color: "black" }, // 默认颜色为黑色
      textStyleSFT: { color: "black" }, // 默认颜色为黑色
      needTurnToCardHL: false,
      needTurnToCardHLSFT: false,
      selectedIndex: 0, // 存储双击的开始位置
      speech: null, // 用于存储语音合成实例
      isSpeaking: false,

      checked: false,
      isContentExpanded: false,
      isContentTruncated: false,
      isCardDialogVisible: false,
      showTooltip: false,
      showEditDialog: false,
      showHistoryDialog: false,
      showHistoryTip: false,
      editForm: {
        contentTitle: '',
        content: '',
        keyWords: '',
      },
      splitReasonContent: [],
      // 卡片放大查看
      cardInfo: {
        title: "title",
        content: "content",
        username: "admin",
        datetime: "datetime",
        score: 1.0,
        color: "紫",
        reason: "",
        keyWords: "",
        contentTitle: "",
        type: "",
        preIndex: "",
        postIndex: "",
        lastContent: "",
        writer: "",
        interGrowthT2TA: "",
        interGrowthTA2GL: "",
        interGrowthGL2GM: "",
        subareaAndHLAndSugTA2GL: "",
        timeParams: {
          "value1": 0.7,
          "value2": 0.95,
          "value3": 25,
          "value4": 512,
          "value5": 1,
          "value6": 1,
          "value7": 1,
          "value8": 1,
          "value9": 1,
          "value10": 512,
          "value11": 1.1,
          "value12": 1
        },
      }
    };
  },
  created() {
  },
  mounted() {
    // 添加一个监听器，当语音状态改变时更新 isSpeaking
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      this.isSpeaking = window.speechSynthesis.speaking;
    });

    // 保证加载页面时就更新卡片内容、打分、颜色，否则不放大卡片颜色不正确显示
    // let formData = new FormData();
    // formData.append('username', localStorage.getItem('userId'));
    // formData.append('cid', this.cid);
    // console.log("卡片id: ", this.cid);
    // get_card(formData).then(data => {
    //   console.log(data.content);
    //   this.cardInfo = data.content;
    //   this.cardInfo.username = localStorage.getItem('realName');
    //   console.log("卡片内容：", this.cardInfo)
    // }).catch(error => {
    //   console.error("An error occurred:", error);
    // });

    setTimeout(() => {
      this.cardFromCardListToCardInfo()
    }, 1000); // 延迟0.1秒执行

    // 显示卡片模型、参数配置
    this.$refs.tooltipTarget.addEventListener('mouseenter', this.show);
    this.$refs.tooltipTarget.addEventListener('mouseleave', this.hide);
    this.$refs.historyTipTarget.addEventListener('mouseenter', this.showHisTip);
    this.$refs.historyTipTarget.addEventListener('mouseleave', this.hideHisTip);
  },
  beforeDestroy() {
    this.$refs.tooltipTarget.removeEventListener('mouseenter', this.show);
    this.$refs.tooltipTarget.removeEventListener('mouseleave', this.hide);
    this.$refs.historyTipTarget.removeEventListener('mouseenter', this.showHisTip);
    this.$refs.historyTipTarget.removeEventListener('mouseleave', this.hideHisTip);

  },
  computed: {
    wordCount() {
      if (!this.content) return 0;
      
      const text = this.content;
      
      // 统计中文字符
      const chineseCount = (text.match(/[\u4e00-\u9fa5]/g) || []).length;
      
      // 处理英文单词 - 先清理markdown符号
      const cleanedText = text
        .replace(/```/g, '') // 只移除代码块标记
        .replace(/`/g, '')  // 只移除行内代码标记
        .replace(/\*\*/g, '') // 只移除加粗标记
        .replace(/\*/g, '') // 只移除斜体标记
        .replace(/\[(.*?)\]\(.*?\)/g, '$1') // 保留链接文本，移除URL
        .replace(/#{1,6}\s/g, '') // 只移除标题标记
        .replace(/-\s+/g, ' ') // 移除列表符号
        .replace(/>\s+/g, ' ') // 移除引用符号
        .replace(/[^\w\s\u4e00-\u9fa5]|_/g, ' ') // 将标点符号替换为空格
        .replace(/\s+/g, ' ') // 合并多个空格
        .trim();
      
      // 统计英文单词（按空格分隔）
      const englishWords = cleanedText.split(/\s+/).filter(word => 
        // 只计算包含英文字母的单词
        /[a-zA-Z]/.test(word) && word.length > 0
      ).length;
      
      // 返回总字数
      return chineseCount + englishWords;
    },

    splitReasonSFT() {
      const [part1, part2] = this.splitTextAtFirstOccurrence(this.cardInfo.reasonSFT, "建议");
      return [part1, part2];
    },
    colorSFT() {
      // 假设饱和度为50%，亮度范围从90%到10%，根据score调整
      let baseHue = 270; // 紫色的基准色调
      const saturation = 50; // 饱和度固定为50%
      const minLightness = 50; // 最暗的亮度值
      const maxLightness = 90; // 最亮的亮度值
      const lightnessRange = maxLightness - minLightness;

      // 根据score计算亮度值，score越小亮度越高，颜色越浅
      let lightness;
      if (this.scoreSFT >= 1 && this.scoreSFT <= 5) {
        baseHue = 270; // 紫色的基准色调
        lightness = maxLightness - ((this.scoreSFT - 1) / 4) * lightnessRange;
      } else if (this.scoreSFT > 0 && this.scoreSFT < 1) {
        if (this.colorhlSFT === "红") {
          baseHue = 0; // 红色的基准色调
        } else if (this.colorhlSFT === "蓝") {
          baseHue = 240; // 蓝色的基准色调
        } else {
          baseHue = 100; // 默认
        }
        lightness = maxLightness - (this.scoreSFT / 1) * lightnessRange;
      } else {
        // 如果分数不在0-5之间，可以选择一个默认行为，比如返回透明
        lightness = 100; // 完全透明，相当于白色
      }

      // 返回HSL颜色字符串
      return `hsl(${baseHue}, ${saturation}%, ${lightness}%)`;
    },

    splitReason() {
      const [part1, part2] = this.splitTextAtFirstOccurrence(this.cardInfo.reason, "建议");
      return [part1, part2];
    },
    color() {
      // 假设饱和度为50%，亮度范围从90%到10%，根据score调整
      let baseHue = 270; // 紫色的基准色调
      const saturation = 50; // 饱和度固定为50%
      const minLightness = 50; // 最暗的亮度值
      const maxLightness = 90; // 最亮的亮度值
      const lightnessRange = maxLightness - minLightness;

      // 根据score计算亮度值，score越小亮度越高，颜色越浅
      // 根据分数计算亮度值，这里用this.score而不用cardInfo里的，应该是因为挂载时cardInfo要后端获取，而this.score是直接传过来的，无延迟
      let lightness;
      if (this.score >= 1 && this.score <= 5) {
        baseHue = 270; // 紫色的基准色调
        lightness = maxLightness - ((this.score - 1) / 4) * lightnessRange;
      } else if (this.score > 0 && this.score < 1) {
        if (this.cardcolor === "红") {
          baseHue = 0; // 红色的基准色调
        } else if (this.cardcolor === "蓝") {
          baseHue = 240; // 蓝色的基准色调
        } else {
          baseHue = 100; // 默认
        }
        lightness = maxLightness - (this.score / 1) * lightnessRange;
      } else {
        // 如果分数不在0-5之间，可以选择一个默认行为，比如返回透明
        lightness = 100; // 完全透明，相当于白色
      }

      // 返回HSL颜色字符串
      return `hsl(${baseHue}, ${saturation}%, ${lightness}%)`;
    },
    getCustomTitle() {
      if (this.title.includes("1002")) {
        return "来自GPT-4o";
      } else if (this.title.includes("1003")) {
        return "来自Mixtral";
      } else if (this.title.includes("1004")) {
        return "来自Kimi";
      } else if (this.title.includes("1005")) {
        return "来自llama3.1";
      } else if (this.title.includes("1006")) {
        return "来自Claude3.5";
      } else if (this.title.includes("1007")) {
        return "来自Deepseek";
      } else if (this.title.includes("1008")) {
        return "来自Deepseek";
      } else if (this.title.includes("1009")) {
        return "来自Gemini";
      } else if (this.title.includes("1010")) {
        return "来自Qwq";
      } else if (this.title.includes("2000")) {
        return "来自2模融合";
      } else {
        return "卡片迭代结果";
      }
    },
  },
  props: {
    cid: Number,
    idx: Number,
    title: String,
    content: String,
    cardcolor: String,
    score: Number,
    colorhlSFT: String,
    scoreSFT: Number,
    model_id: Number,
    status: Number,
    contentTitle: String,
    needflashing: Boolean,
    needMultiFlashing: Boolean,
    reAcquire: Boolean,
    updateCheckbox: Boolean,
    choosedCardIdList: Array,
    activeModel: String,
    card: Object,
    keyTopics: Array,
    groupIndex: Number,
    sceneName: String,
    subSceneName: String,
  },
  watch: {
    card(newVal){
      this.cardFromCardListToCardInfo()
    },
    content(newVal) {
      // 根据内容长度判断是否需要截断显示
      if (newVal.length > 100) {
        this.isContentTruncated = true;
      }
    },
    needflashing(newVal) {
      if(newVal === true){
        // let formData = new FormData();
        // formData.append('username', localStorage.getItem('userId'));
        // formData.append('cid', this.cid);
        // set_card(formData).then(data => {
        // }).catch(error => {
        //   console.error("An error occurred:", error); // 错误处理
        // });
      }
    },
    needMultiFlashing(newVal) {
      if(newVal === true){
        // let formData = new FormData();
        // formData.append('username', localStorage.getItem('userId'));
        // formData.append('cid', this.cid);
        // set_card(formData).then(data => {
        // }).catch(error => {
        //   console.error("An error occurred:", error); // 错误处理
        // });
      }
    },
    reAcquire(newVal) {
      if(newVal === true){
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', this.cid);
        console.log("卡片id: ", this.cid);
        get_card(formData).then(data => {
          console.log(data.content);
          this.cardInfo = data.content;
          this.cardInfo.username = localStorage.getItem('realName');
          this.$emit('reAcquireOver');
        }).catch(error => {
          console.error("An error occurred:", error);
        });

        // 显示卡片模型、参数配置
        this.$refs.tooltipTarget.addEventListener('mouseenter', this.show);
        this.$refs.tooltipTarget.addEventListener('mouseleave', this.hide);
        this.$refs.historyTipTarget.addEventListener('mouseenter', this.showHisTip);
        this.$refs.historyTipTarget.addEventListener('mouseleave', this.hideHisTip);
      }
    },
    updateCheckbox(newVal) {
      if(newVal === true){
        if(this.choosedCardIdList.includes(this.cid))
          this.checked = true
        else
          this.checked = false
      }
    }
  },
  methods: {
    cardFromCardListToCardInfo() {
      this.cardInfo.cid = this.card.cid
      this.cardInfo.title = this.card.title
      this.cardInfo.content = this.card.content
      this.cardInfo.status = this.card.status
      this.cardInfo.username = this.card.username
      this.cardInfo.datetime = this.card.datetime
      this.cardInfo.score = this.card.score
      this.cardInfo.color = this.card.color
      this.cardInfo.reason = this.card.reason
      this.cardInfo.scoreSFT = this.card.scoreSFT
      this.cardInfo.colorSFT = this.card.colorSFT
      this.cardInfo.reasonSFT = this.card.reasonSFT
      this.cardInfo.keyWords = this.card.keyWords
      this.cardInfo.contentTitle = this.card.contentTitle
      this.cardInfo.type = this.card.type
      this.cardInfo.preIndex = this.card.preIndex
      this.cardInfo.postIndex = this.card.postIndex
      this.cardInfo.lastContent = this.card.lastContent
      this.cardInfo.writer = this.card.writer
      this.cardInfo.interGrowthT2TA = this.card.interGrowthT2TA
      this.cardInfo.interGrowthTA2GL = this.card.interGrowthTA2GL
      this.cardInfo.interGrowthGL2GM = this.card.interGrowthGL2GM
      this.cardInfo.subareaAndHLAndSugTA2GL = this.card.subareaAndHLAndSugTA2GL

      this.cardInfo.timeParams = this.card.time_params
      if(this.card.history === null)
        this.cardInfo.history = null
      else
        this.cardInfo.history = this.card.history.data
    },
    turnToCardHL() {
      this.needTurnToCardHL = true
      this.onCardClick()
    },
    turnToCardHLSFT() {
      this.needTurnToCardHLSFT = true
      this.onCardClick()
    },

    startFromIndexSFT(index, answer) {
      this.selectedIndex = index;
      this.doubleClick = true;
      this.speakTextSFT();
    },
    speakTextBeginSFT() {
      this.stopSpeech()
      // 从头开始读
      let SFT = this.splitReasonSFT[1] || '正在打分，等待解析改进建议'
      const utterance = new SpeechSynthesisUtterance(SFT);
      this.speech = window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },
    speakTextSFT() {
      this.stopSpeech()
      // 截取从用户双击位置开始的内容
      let SFT = this.splitReasonSFT[1] || '正在打分，等待解析改进建议'
      const content = SFT.slice(this.selectedIndex);
      const utterance = new SpeechSynthesisUtterance(content);
      this.speech = window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },

    doubleClickOver() {
      this.doubleClick = false
    },
    startFromIndex(index, answer) {
      this.selectedIndex = index;
      this.doubleClick = true;
      this.speakText();
    },
    speakTextBegin() {
      this.stopSpeech()
      // 从头开始读
      const utterance = new SpeechSynthesisUtterance(this.cardInfo.content);
      this.speech = window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },
    speakText() {
      this.stopSpeech()
      // 截取从用户双击位置开始的内容
      const content = this.cardInfo.content.slice(this.selectedIndex);
      const utterance = new SpeechSynthesisUtterance(content);
      this.speech = window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },
    stopSpeech() {
      if (this.isSpeaking) {
        window.speechSynthesis.cancel();
        this.isSpeaking = false;
        this.speech = null;
      }
    },
    splitTextAtFirstOccurrence(text, keyword) {
      // 正则表达式匹配 keyword"建议" 前的标点符号、空格或换行符
      // const regex = new RegExp(`[.。,，?？!！;；:： \n]+(?=${keyword})`, 'g');
      const regex = new RegExp(`([.。,，*?？!！;；:： \\s]+|\\\\n)+(?=${keyword})`, 'g');

      // 执行匹配
      const match = regex.exec(text);
      
      if (match) {
        // 找到匹配的位置，分割字符串
        const index = match.index + match[0].length;
        const part1 = text.substring(0, index);
        const part2 = text.substring(index);
        
        return [part1, part2];
      } else {
        // 如果没有找到匹配，返回原始字符串和空字符串
        console.log("未匹配到建议")
        return [text, ''];
      }
    },
    copyContentWithEmptyLines() {
      // 使用Clipboard API复制文本，包括空行
      navigator.clipboard.writeText(this.cardInfo.content).then(() => {
        this.$message.success('内容已复制到剪贴板，包含空行');
      }).catch((err) => {
        this.$message.error("复制失败！");
      });
    },
    replaceTopTip(title) {
      if (title.includes("1002") || title.includes("1003") || title.includes("1004") || title.includes("1005") || title.includes("1006") || title.includes("1007") || title.includes("1008") || title.includes("1009") || title.includes("1010") || title.includes("2000")) {
        return "普通问答收藏"
      } else if (title.includes("理解")) {
        return "单卡理解结果"
      } else if (title.includes("批判")) {
        return "单卡批判结果"
      } else if (title.includes("大纲")) {
        return "单卡大纲结果"
      } else if (title.includes("扩写")) {
        return "单卡扩写结果"
      } else if (title.includes("缩写")) {
        return "单卡缩写结果"
      } else if (title.includes("总结")) {
        return "多卡总结结果"
      } else if (title.includes("合并")) {
        return "多卡融合结果"
      } else if (title.includes("建议")) {
        return "多卡建议想法"
      } else if (title.includes("指导")) {
        return "多卡学习指导"
      } else {
        return "自定义结果"
      }
    },
    replaceTitle(title) {
      let localTitle = title;
      return localTitle.replace(/(1002|1003|1004|1005|1006|1007|1008|1009|1010|2000)/g, match => {
        switch(match) {
          case '1002':
            return 'GPT4o';
          case '1003':
            return 'mixtral';
          case '1004':
            return 'kimi';
          case '1005':
            return 'llama3.1';
          case '1006':
            return 'Claude3.5';
          case '1007':
            return 'Deepseek';
          case '1008':
            return 'Deepseek';
          case '1009':
            return 'Gemini';
          case '1010':
            return 'Qwq';
          case '2000':
            return '×2融合';
          default:
            return match; // 如果匹配不到任何case，返回原字符串
        }
      });
    },
    backHistoryClicked() {
      // 在外面，还没有获取cardinfo就回溯历史了
      this.cardInfo.username = localStorage.getItem('realName');
      this.backHistory(this.cardInfo.history, this.title);
      this.hideHistory();
      this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle)
    },
    backHistory(history, title) {
      if (!history) {
        this.$message.error("该卡片非对话生成，无历史记录");
        return;
      }
      this.$emit('update-history', history, title);
      setTimeout(() => {
        this.isCardDialogVisible = false;
        this.showHistoryDialog = false;
      }, 5); // 延迟0.005秒执行
    },
    show() {
      this.showTooltip = true;
    },
    hide() {
      this.showTooltip = false;
    },
    showHistory() {
      this.cardInfo.username = localStorage.getItem('realName');
      this.showHistoryDialog = true;
      this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle)
    },
    hideHistory() {
      this.showHistoryDialog = false;
    },
    showHisTip() {
      this.showHistoryTip = true;
    },
    hideHisTip() {
      this.showHistoryTip = false;
    },
    handleClick() {
      let timeModel = '';
      // 要检查的键
      const keysToCheckGPT4 = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens', 'n'];  
      // const keysToCheckMixtral = ['temperature', 'top_p', 'top_k', 'max_tokens'];  
      const keysToCheckKimi = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens', 'n'];  
      const keysToCheckLlama3 = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];  
      const keysToCheckClaude = ['temperature', 'top_p', 'top_k', 'max_tokens'];  
      const keysToCheckDeepseek = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];
      const keysToCheckGemini = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];
      const keysToCheckQwq = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];

      if (this.title.includes("1002")) {
        timeModel = 'GPT4';
      } else if (this.title.includes("1003")) {
        timeModel = 'Mixtral';
      } else if (this.title.includes("1004")) {
        timeModel = 'Kimi';
      } else if (this.title.includes("1005")) {
        timeModel = 'llama3';
      } else if (this.title.includes("1006")) {
        timeModel = 'Claude';
      } else if (this.title.includes("1007")) {
        timeModel = 'Deepseek';
      } else if (this.title.includes("1008")) {
        timeModel = 'Deepseek';
      } else if (this.title.includes("1009")) {
        timeModel = 'Gemini';
      } else if (this.title.includes("1010")) {
        timeModel = 'Qwq';
      } else {
        // 此处还存在问题，因为kimi和gpt4的超参一致、llama3.1和Deepseek的超参一致，仅这样区分不开
        if (keysToCheckGPT4.every(key => key in this.cardInfo.timeParams))
          timeModel = 'GPT4';
        if (keysToCheckKimi.every(key => key in this.cardInfo.timeParams))
          timeModel = 'GPT4';
        if (keysToCheckLlama3.every(key => key in this.cardInfo.timeParams))
          timeModel = 'llama3';
        if (keysToCheckDeepseek.every(key => key in this.cardInfo.timeParams))
          timeModel = 'Deepseek';
        if (keysToCheckClaude.every(key => key in this.cardInfo.timeParams))
          timeModel = 'Claude';
        else
          timeModel = this.activeModel;
      }

      if(this.cardInfo.timeParams != null)
        this.$emit('checkParams', this.cardInfo.timeParams, timeModel);
      else
        this.$message.error('此卡片未保存配置');
      this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle)
    },
    onCheckboxChange() {
      this.checked = !this.checked;
      this.$emit('change', { 'cid': this.cid, 'checked': this.checked });

      // if(this.checked === true) {
      //   let formData = new FormData();
      //   formData.append('username', localStorage.getItem('userId'));
      //   formData.append('cid', this.cid);
      //   set_card(formData).then(data => {
      //     this.$emit('updateOrder');
      //   }).catch(error => {
      //     console.error("An error occurred:", error); // 错误处理
      //   });
      // }
    },
    expandContent() { this.isContentExpanded = true; this.isContentTruncated = false; }, collapseContent() { this.isContentExpanded = false; this.isContentTruncated = true; }, handleSetting(command) {
      this.$emit('setting', command);
    },

    // 平滑地在duration时间内完成拖动到底部
    smoothScrollToBottom(element, duration) {
      return new Promise((resolve) => {
        const start = element.scrollTop;
        const change = element.scrollHeight - element.clientHeight - start;
        const startTime = performance.now();

        function animateScroll(currentTime) {
          const timeElapsed = currentTime - startTime;
          const progress = Math.min(timeElapsed / duration, 1); // 计算进度，最大为1
          element.scrollTop = start + change * progress;

          if (timeElapsed < duration) {
            requestAnimationFrame(animateScroll);
          } else {
            resolve(); // 滚动完成后执行 resolve
          }
        }

        requestAnimationFrame(animateScroll);
      });
    },
    smoothScrollToPositionSFT(element, targetPosition, duration) {
      return new Promise((resolve) => {
        const start = element.scrollTop;
        const change = targetPosition - start;
        const startTime = performance.now();

        function animateScroll(currentTime) {
          const timeElapsed = currentTime - startTime;
          const progress = Math.min(timeElapsed / duration, 1); // 计算进度，最大为1
          element.scrollTop = start + change * progress;

          if (timeElapsed < duration) {
            requestAnimationFrame(animateScroll);
          } else {
            resolve(); // 滚动完成后执行 resolve
          }
        }

        requestAnimationFrame(animateScroll);
      });
    },
    changeTextColor() {
      if (this.needTurnToCardHL === true) {
        // 等待 0.8s 后变为红色
        // setTimeout(() => {
        this.textStyle = { color: "red", transition: "color 0.8s" };
        
        // 持续 2.5s 后再变回黑色
        setTimeout(() => {
          this.textStyle = { color: "black", transition: "color 0.8s" };
        }, 2500);
        this.needTurnToCardHL = false
      } else if (this.needTurnToCardHLSFT === true) {
        this.textStyleSFT = { color: "purple", transition: "color 0.8s" };
        
        setTimeout(() => {
          this.textStyleSFT = { color: "black", transition: "color 0.8s" };
        }, 2500);
        this.needTurnToCardHLSFT = false;
      }
    },
    judgeScrollToBottom() {
      if (this.needTurnToCardHL === true) {
        this.$nextTick(() => {
          // 获取 card-dialog 元素
          const cardDialog = this.$refs.cardDialog;

          // 检查是否存在垂直滚动条，如果有，将滚动条滚动到最底部
          if (cardDialog.scrollHeight > cardDialog.clientHeight) {
            // cardDialog.scrollTop = cardDialog.scrollHeight;
            // 0.5秒完成拖动
            this.smoothScrollToBottom(cardDialog, 500).then(() => {
              this.changeTextColor(); // 滚动到底部后更改颜色
            });
          } else {
            this.needTurnToCardHL = false;
          }
        });
      } else if (this.needTurnToCardHLSFT === true) {
        this.$nextTick(() => {
          const cardDialog = this.$refs.cardDialog;

          // 获取微调模型红蓝打分元素的 offsetTop
          const scoreElement = this.$refs.scoreSFT;
          const targetPosition = scoreElement.offsetTop;

          // 如果存在滚动条，平滑滚动到目标位置
          if (cardDialog.scrollHeight > cardDialog.clientHeight) {
            // 0.5秒内平滑滚动到微调模型红蓝打分的位置
            this.smoothScrollToPositionSFT(cardDialog, targetPosition, 500).then(() => {
              this.changeTextColor(); // 滚动到底部后更改颜色
            });
          } else {
            this.needTurnToCardHLSFT = false;
          }
        });
      }
    },

    catchCidIndex() {
      if(this.title.includes("1002") || this.title.includes("1003") || this.title.includes("1004") || this.title.includes("1005") || this.title.includes("1006") || this.title.includes("1007") || this.title.includes("1008") || this.title.includes("1009") || this.title.includes("1010") || this.title.includes("2000")){
        this.isCardDialogVisible = true;
        this.judgeScrollToBottom()
      } else if(this.title.includes("理解") || this.title.includes("批判") || this.title.includes("大纲") || this.title.includes("扩写") || this.title.includes("缩写") || (this.title.includes("自定义")&&!this.title.includes(","))){
        const regex = /(\d+)(理解|批判|大纲|扩写|缩写|自定义)/;
        const match = this.title.match(regex);
        let numberBefore;
        if (match) {
          numberBefore = match[1]; // 第一个捕获组是要找的数字
          console.log("捕获卡片cid" ,numberBefore);
        } else {
          console.log("没有找到匹配的数字");
        }
        this.$emit('hint', numberBefore, this.groupIndex);
        this.$message.success('闪烁的为单卡迭代来源卡片，它将和当前卡片一同被移动至最前！');
        setTimeout(() => {
          this.isCardDialogVisible = true;
          this.judgeScrollToBottom()
        }, 2000); // 2秒闪烁后，再展示卡片内容
      } else if(this.title.includes("总结") || this.title.includes("合并") || this.title.includes("建议") || this.title.includes("指导") || (this.title.includes("自定义")&&this.title.includes(","))){
        const regex = /((\d+,)*\d+)(总结|合并|建议|指导|自定义)/;
        const match = this.title.match(regex);
        let numbers;
        if (match) {
          const numberBefore = match[1];
          numbers = numberBefore.split(',').map(num => parseInt(num.trim(), 10));
          console.log("捕获的卡片cid数组:", numbers);
        } else {
          console.log("没有找到匹配的数字");
        }
        this.$emit('MultiHint', numbers, this.groupIndex);
        this.$message.success('闪烁的为多卡迭代来源卡片，它们将和当前卡片一同被移动至最前！');
        setTimeout(() => {
          this.isCardDialogVisible = true;
          this.judgeScrollToBottom()
        }, 2000); // 2秒闪烁后，再展示卡片内容
      } else {
        this.isCardDialogVisible = true;
        this.judgeScrollToBottom()
      }
    },
    onCardClick() {
      this.catchCidIndex()

      // this.isCardDialogVisible = true;
      this.getSingleCard()
    },
    getSingleCard() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      get_card(formData).then(data => {
        console.log(data.content);
        this.cardInfo = data.content;
        this.cardInfo.username = localStorage.getItem('realName');
        this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle)
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },

    hideCardDialog() {
      if(this.doubleClick === false) {
        this.stopSpeech()
        this.isCardDialogVisible = false;
        
        // let formData = new FormData();
        // formData.append('username', localStorage.getItem('userId'));
        // formData.append('cid', this.cid);
        // set_card(formData).then(data => {
        //   this.$emit('updateOrder');
        // }).catch(error => {
        //   console.error("An error occurred:", error); // 错误处理
        // });
      } else {
        this.$message.error('您操作过快，请您稍等2s，再关闭卡片');
      }
    },
    editContent() {
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限编辑卡片');
        return
      }

      this.showEditDialog = true;
      this.editForm.contentTitle = this.cardInfo.contentTitle
      this.editForm.content = this.cardInfo.content;
      this.editForm.keyWords = this.cardInfo.keyWords
    },
    deleteCard() {
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限删除卡片');
        return
      }

      deleteChoosedCard(this.cid).then(response => { 
        this.$emit('deleteCard');
      }).catch(error => {
        alert("error2");
        console.log('error', error.message);
      })

      this.showEditDialog = false;
      this.isCardDialogVisible = false;
    },
    cancelDialog() {
      this.showEditDialog = false;
      // this.isCardDialogVisible = false;
    },
    saveContent() {

      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('newContent', this.editForm.content);
      formData.append('newContentTitle', this.editForm.contentTitle);
      formData.append('newKeyWords', this.editForm.keyWords);
      chageContent(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('保存成功');
          this.$emit('updateOrDeleteCard');
        }
        else {
          alert("error!");
        }
      }).catch(error => {
        alert("error!2");
        console.log('error', error.message);
      })

      this.cardInfo.content = this.editForm.content;
      this.cardInfo.contentTitle = this.editForm.contentTitle
      this.cardInfo.keyWords = this.editForm.keyWords
      this.showEditDialog = false;
      // this.isCardDialogVisible = false;
      // this.$router.go(0);
    },

    changeTextLen(length) {
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }
      
      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('content', this.cardInfo.content);
      formData.append('tarLen', length);
      formData.append('username', localStorage.getItem('userId'));
      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', this.subSceneName);
      formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递
      this.$emit("cardTextNum")
      changeText(formData).then(response => {
        if (response.error_num === 0) {
          let finalContent=response.finalContent;
          let cid = response.cardId
          this.$emit("cardTextNumOver")
          this.waitDecodedResult(cid, finalContent)
        }
        else {
          this.$emit("cardTextNumOver")
          alert("error!");
        }
      }).catch(error => {
        alert("error!2");
        console.log('error', error.message);
      })
    },
    async waitDecodedResult(cid, finalContent) {
      // 等待 modelHL 异步函数执行完成，并将结果赋值给 decodedResult
      let decodedResult = await modelHL(finalContent); 
      console.log("红蓝微调评测模型打分：", decodedResult);

      if (decodedResult === "fail") {
        this.$message.error('卡片保存成功，但红蓝微调评测模型打分失败');
        this.$emit("cardTextNumOver")
      } else {
        let formDataSFT = new FormData();
        formDataSFT.append('content', decodedResult);
        formDataSFT.append('cid', cid);
        card_evalSFT(formDataSFT).then(responseSFT => {
          if (responseSFT.error_num === 0) {
            this.$message.success('字数改写卡片保存成功！');
          } else {
            this.$message.error('字数改写卡片保存成功，但红蓝微调评测模型打分保存失败');
          }
          this.$emit("cardTextNumOver")
        });
      }
    },

    textTo1500() {
      this.changeTextLen(1500);
    },
    textTo500() {
      this.changeTextLen(500);
    },
    textTo1000() {
      this.changeTextLen(1000);
    },
  }
};
</script>

<style scoped>
.notebook-card {
  height: 200px;
  width: 280px;
  border-radius: 10px;
  overflow: hidden;

  padding: 20px;
  background-color: #deecf3;
  margin: 10px;

  position: relative;
  /* position: absolute; */

  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1), 0 6px 20px rgba(0, 0, 0, 0.2);
}

.card-top {
  display: flex;
  position: relative;
  width: 100%;
  height: 58%;
}

.card-top-left {
  width: 50%;
}

.card-top-right {
  width: 50%;
}

.card-top-from {
  width: 100%;
}

.card-top-from-img {
  background-image: url('@/assets/img/cardwindow/response.png');
  background-size: contain;
  background-repeat: no-repeat;
  vertical-align: middle;
  height: 20.8px;
  width: 20.8px;
  border-radius: 3px;
  float: left;
}

.card-top-from-text {
  font-size: 14px;
  margin-left: 10px;
  color: #6eb7ff
}

.card-top-title {
  font-size: 21px;
  font-weight: bold;
  color: #3b3b3b;
  margin-bottom: 10px;
  width: 100%;
  word-wrap: break-word;
  border-radius: 8px;
  background-color: #ffffffda;
  position: relative;
  z-index: 1;
  text-shadow: 1px 1px 1px rgba(75, 75, 75, 0.09); /* 添加文字阴影 */
  /* 可选，为内容提供一些内边距 */
  /* padding: 1px;  */
  /* 确保内边距和边框宽度包含在宽度内 */
  /* box-sizing: border-box;  */
}

.card-top-right-button {
  background-size: contain;
  background-repeat: no-repeat;
  vertical-align: middle;
  height: 20.8px;
  width: 20.8px;
  border-radius: 3px;
  float: right;
  right: 0;
}


.card-top-right-button.checked {
  background-image: url('@/assets/img/pin_blue.png');
}

.card-top-right-button:not(.checked) {
  background-image: url('@/assets/img/pin_grey.png');
}

.card-content {
  font-size: 16px;
  color: #666;
  line-height: 1.6;
  overflow: hidden;
  width: 100%;
  word-wrap: break-word;
  height: 40%;
}

.card-content-text {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 7;
  margin-bottom: 10px;
  max-height: 9em;
  /* 根据行高计算最大高度，确保有5行文本的空间 */
  position: relative;
  overflow: hidden;
}

.card-content-text::before {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  z-index: 1;
}

.card-rate {
  width: 30%;
  display: flex;
  position: absolute;
  bottom: 75px;
  left: 160px;
  z-index: 3;
}

/* 新增的中间容器，用于垂直排列 card-rate-left 和 card-rate-left2 */
.card-rate-middle {
  display: flex;
  flex-direction: column; /* 垂直排列 */
  justify-content: center; /* 水平居中 */
}

.card-rate-left, .card-rate-left-single {
  display: flex;
  /* 启用 Flexbox */
  justify-content: center;
  /* 水平居中 */
  align-items: center;
  /* 垂直居中 */
  width: 30px;
  height: 20px;
  border-radius: 6px;
  background-color: #911787;
  font-size: 14px;
  font-weight: bold;
  color: #000000;
  transition: filter 0.3s ease;
  cursor: pointer;
}

.card-rate-left-single {
  height: 40px;
}

.card-rate-right {
  display: flex;
  /* 启用 Flexbox */
  justify-content: center;
  /* 水平居中 */
  align-items: center;
  /* 垂直居中 */
  width: 30px;
  height: 40px;
  border-radius: 6px;
  background-color: #c81b1bac;
  font-size: 12px;
  /* font-weight: bold; */
  color: #000000;
  transition: filter 0.3s ease;
  /* 添加过渡效果 */
}

.card-rate-history {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 30px;
  height: 40px;
  border-radius: 6px;
  background-color: #0b0be79f;
  font-size: 12px;
  color: #000000;
  transition: filter 0.3s ease;
  cursor: pointer;
}

.card-rate-right:hover {
  filter: brightness(130%);
  /* 增加亮度 */
}


.card-rate-history:hover {
  filter: brightness(130%);
  /* 增加亮度 */
}

.tooltip {
  position: absolute;
  z-index: 10;
  background-color: #a2b1c1;
  border: 2px solid #72677b;
  padding: 5px;
  border-radius: 9px;
  width: 120px;
  height: 60px;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  /* 启用 Flexbox */
  flex-direction: column;
  /* 设置主轴方向为垂直 */
  align-items: center;
  /* 水平居中子元素 */
}



.historyTip {
  position: absolute;
  z-index: 10;
  background-color: #a2b1c1;
  border: 2px solid #72677b;
  padding: 5px;
  border-radius: 9px;
  width: 50vw;
  height: 60vh;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  /* 启用 Flexbox */
  flex-direction: column;
  /* 设置主轴方向为垂直 */
  align-items: center;
  /* 水平居中子元素 */
}

.nav-button {
  width: 60px;
  margin-top: 7px;
  display: flex;
  justify-content: center;

  .el-button {
    font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    font-weight: 550;
    color: #6a45c2;
    cursor: pointer;
    transition: background-color 0.5s;
    background-color: #bccfe3;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

    &:hover {
      background-color: #ced8d8;
      box-shadow: 0 4px 8px rgba(106, 106, 106, 0.3);
    }
  }
}

.card-rate-text {
  font-size: 15px;
}

.more-text,
.less-text {
  color: #409eff;
  cursor: pointer;
}

.card-settings {
  position: relative;
  padding-top: 10px;
  bottom: 0px;
  right: 0px;
}

.el-dropdown-link {
  cursor: pointer;
  color: #409eff;
  font-size: 14px;
}

.custom-checkbox {
  cursor: pointer;
  width: 20px;
  /* 设置图片的宽度 */
  height: 20px;
  /* 设置图片的高度 */
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;

}

.custom-checkbox.checked {
  background-image: url('@/assets/img/pin_blue.png');
}

.custom-checkbox:not(.checked) {
  background-image: url('@/assets/img/pin_grey.png');
}



.card-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 25;
  width: 45vw;
  height: 60vh;
  max-width: 100%;

  overflow: scroll;
}

.history-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 23;
  width: 45vw;
  height: 60vh;
  max-width: 100%;

  overflow: scroll;
}

.card-dialog .card-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.history-dialog .history-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.card-dialog h2 {
  margin: 0;
  font-size: 1.2em;
}

.card-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}

.card-dialog .close:hover {
  color: #333;
}

.card-dialog .card-dialog-body {
  margin-top: 10px;
}

.card-dialog p {
  margin: 5px 0;
  white-space: pre-wrap;
}

.card-dialog pre {
  white-space: pre-wrap;
}

.card-merge-info {
  display: flex;
  /* 使用Flexbox布局 */
  align-items: center;
  /* 垂直居中对齐 */
  margin-top: 10px;
  /* 根据需要调整 */
  color: #333;
  /* 文字颜色 */
  font-size: 12px;
  /* 减小字体大小 */
}

.card-merge-info .merge-info-text {
  margin-right: 5px;
  /* 为数字和文字之间添加一些间距 */
  white-space: nowrap;
  /* 防止文本换行 */
}

.model-info-text {
  position: absolute;
  right: 0;        /* 靠右 */
  bottom: 0;      /* 靠下 */
  margin-bottom: 8px;  /* 如果需要在底部留出空间，可以移除或调整这个值 */
  margin-right: 1px; /* 靠右时，可能需要右边距来保持距离容器边缘 */
  font-size: 12px;
  font-weight: bold;
  color: #8b8b8b;
  padding: 4px;     /* 内边距 */
  background: #e0e0e0; /* 背景颜色 */
  border-radius: 8px; /* 圆角 */
  box-shadow: 0px 0px 10px rgba(113, 113, 113, 0.15); /* 边缘阴影 */
  word-wrap: break-word;  /* 允许在单词内换行 */
  white-space: normal;     /* 正常处理空白和换行 */
  width: auto;
  max-width: 45%; /* 限制最大宽度 */
  box-sizing: border-box; /* 确保padding和border不会使元素宽度超出 */
}

.card-down {
  width: 100%;
  height: 10%;
  float: bottom;
}

.editContentDialog {
  height: 100%;
  width: 100%;

  display: flex;
  align-items: center;
  /* 这两行可以让textarea输入框下拉时整个dialog也跟随 */
}

.contentInput textarea {
  resize: vertical;
  /* 允许垂直调整大小 */
  overflow: auto;
  /* 添加滚动条 */
  width: 100%;
  /* 设置宽度以适应其父元素 */

  height: 700px;
}


@keyframes flash {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.1); }
}

.flashing {
  animation: flash 1s infinite; /* 可以设置为无限循环以便更容易观察 */
}
</style>