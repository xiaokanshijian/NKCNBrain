<template>
  <div class="multi-card-func" v-if="choosedCardIdList.length >= 2">
    <button class="card-combine-btn" @click="cardCombine">多卡融合</button>
    <button class="card-summarize-btn" @click="cardSummarize">多卡内容总结</button>
    <button class="card-study-guide-btn" @click="cardStudyGuide">多卡学习指导</button>
    <button class="card-suggest-ideas-btn" @click="cardSuggestIdeas">多卡建议想法</button>
    <button class="card-user-define" @click="cardUserDefine">动态追问</button>
  </div>
  <div class="multi-card-func" v-if="choosedCardIdList.length == 1">
    <button class="card-combine-btn" @click="singleCardUnderstand">单卡辅助理解</button>
    <button class="card-summarize-btn" @click="singleCardCrtique">单卡批判</button>
    <button class="card-study-guide-btn" @click="singleCardCreateOutline">单卡大纲</button>
    <button v-if="isPlus" class="card-react-btn" @click="singleCardReact">React加强</button>
    <button class="card-user-define" @click="cardUserDefine">动态追问</button>
  </div>

  <!-- 悬浮显示的菜单，鼠标悬停时才可见 -->
  <div class="tags-container" v-if="menuVisible" @mouseover="showMenu" @mouseleave="hideMenu">
    <div class="tags-header">
      <span>标题-卡片筛选</span>
    </div>
    <div class="title-filter">
      <input type="text" v-model="titleFilter" placeholder="请输入标题，模糊匹配筛选卡片" class="filter-input"/>
    </div>

    <div class="tags-header">
      <span>标签(关键词)-卡片筛选</span>
      <button class="reset-btn" @click="clearSelectedTopics">恢复</button>
    </div>
    <button class="tag-btn" v-for="topic in keyTopics" :key="topic" @click="toggleTopicSelection(topic)"
          :class="{ 'selected': selectedTopics.includes(topic) }">
      {{ topic }}
    </button>
  </div>
  
  <!-- gutter:每列20间隔；span是一列占多少单位，一共24个单位，这里指定24就是占满了一行只有一个 -->
  <div class="grid-container">
    <el-row class="grid-row" :gutter="2">
      <!-- 空白内容表示等待生成完成 -->
      <el-col class="grid-col" :span="8" v-if="showBlankCard || cardMaking">
        <div class="notebook-card-waiting" shadow="hover">
          <img class="waiting-gif" src="@/assets/img/chatwindow/card_waiting.gif" alt="Loading...">
          <div class="waiting-text">正在生成卡片，请稍等...</div>
        </div>
      </el-col>
      <div class="notebook-card-waiting-single" shadow="hover" v-if="cardSingleMaking">
        <div class="waiting-text">请稍等...正在合并到原卡</div>
      </div>
      <!-- 已有卡片集合 -->
      <template v-for="(group, groupIndex) in groupedCardList" :key="groupIndex" >
        <el-col :span="8" :class="['grid-col', 'card-stack']" :ref="'cardStack' + groupIndex">
          <!-- 遮罩层 -->
          <div class="card-mask" @click="expandGroup(groupIndex)"></div>
          <CardFold v-for="(card, index) in group.slice().reverse()" :key="card.cid" :title="card.title" :content="card.content" 
            :score="card.score" :idx="index" :cid="card.cid" :cardcolor="card.color" :colorhlSFT="card.colorSFT" :scoreSFT="card.scoreSFT"
            :model_id="card.model_id" :status="card.status" :contentTitle="card.contentTitle" @change="addChoseCard2List"
            @checkParams="handleCheck" @update-history="handelUpdateHistory" @hint="handleHint" :needflashing="card.cid === flashingCid && groupIndex === flashingGroupIndex"
            :card="card" @MultiHint="handleMultiHint" :needMultiFlashing="flashingCids.includes(card.cid) && groupIndex === flashingGroupIndex" @updateOrder="updateOrder"
            :reAcquire="reAcquire" @reAcquireOver="reAcquireOver" @deleteCard="deleteCard" @cardClickLog="cardClickLog"
            :activeModel="activeModel" :updateCheckbox="updateCheckbox" :choosedCardIdList="choosedCardIdList" 
            @cardTextNum="cardTextNum" @cardTextNumOver="cardTextNumOver" :keyTopics="keyTopics" :groupIndex="groupIndex"
            :subSceneName="subSceneName" :sceneName="sceneName"/>
        </el-col>

        <!-- 在点击的 card-stack 下插入对应的 CardOpen -->
        <CardOpen v-if="expandedGroups[groupIndex]" v-for="(card, index) in group" :key="card.cid" :title="card.title" :content="card.content" 
          :score="card.score" :idx="index" :cid="card.cid" :cardcolor="card.color" :colorhlSFT="card.colorSFT" :scoreSFT="card.scoreSFT"
          :model_id="card.model_id" :status="card.status" :contentTitle="card.contentTitle" @change="addChoseCard2List"
          @checkParams="handleCheck" @update-history="handelUpdateHistory" @hint="handleHint" :needflashing="card.cid === flashingCid && groupIndex === flashingGroupIndex"
          :card="card" @MultiHint="handleMultiHint" :needMultiFlashing="flashingCids.includes(card.cid) && groupIndex === flashingGroupIndex" @updateOrder="updateOrder"
          :reAcquire="reAcquire" @reAcquireOver="reAcquireOver" @deleteCard="deleteCard" @cardClickLog="cardClickLog"
          :activeModel="activeModel" :updateCheckbox="updateCheckbox" :choosedCardIdList="choosedCardIdList" 
          @cardTextNum="cardTextNum" @cardTextNumOver="cardTextNumOver" :keyTopics="keyTopics" :groupIndex="groupIndex"
          :subSceneName="subSceneName" :sceneName="sceneName"/>
      </template>
    </el-row>
  </div>

  <el-dialog v-model="showDialog" width="60%" class="createCardQuestion" :close-on-click-modal="false"
    :close-on-press-escape="false">
    <h1 class="cardQuestion">卡片追问</h1>
    <!--    <div class="ButtonListContainer">-->
    <!--      <el-button v-for="text in this.cardQuestionList" class="ButtonList" @click="createRelCard(text)" >-->
    <!--        {{text}}-->
    <!--      </el-button>-->
    <!--    </div>-->

    <el-form :model="userDefineForm" label-width="80px" class="inline-form">
      <div class="form-container">
        <!-- 模板按钮组 -->
        <div class="template-buttons">
          <el-button v-for="(template, index) in promptTemplates" :key="index" @click="applyTemplate(template)">
            {{ template.label }}
          </el-button>
        </div>

        <!-- 使用div包裹输入框和按钮，应用flex布局 -->
        <div class="input-button-group">
          <el-input type="textarea" placeholder="提出您的自定义追问，建议在上方点选模板使用" v-model="userDefineForm.userText"></el-input>
          <el-button class="userDefineButton" @click="createRelCard(userDefineForm.userText)">追问</el-button>
        </div>
      </div>
    </el-form>
  </el-dialog>

  <div class="cardParams-dialog" v-if="this.showCardParams">
    <div class="dialog-header">
      <h2>Card生成时参数图</h2>
      <div class="close" @click="hideDialog">&times;</div>
    </div>
    <radarChartCard :params="params" :timeParams="timeParams" :timeModel="timeModel"></radarChartCard>
  </div>
</template>

<script>
import Card from './Card.vue';
import CardFold from './CardFold.vue';
import CardOpen from './CardOpen.vue';
import radarChartCard from '@/components/radar-chartCard.vue';

import { get_cards } from "@/api/card/get_card"
import { card_evalSFT } from "@/api/card/send_card"
import { mergeCardBackend, cardUserDefine, react } from "@/api/card_zym/card_js"
import { getDateTime, modelHL } from "@/api/getData";
import router from "@/router";
export default {
  components: {
    Card,
    CardFold,
    CardOpen,
    radarChartCard
  },
  props: {
    cards: Array,
    cardUpdate: Boolean,
    params: Object,
    activeModel: String,
    isPlus: Boolean,
    cardMaking: Boolean,
    cardSingleMaking: Boolean,
    menuVis: Boolean,
    sceneName: String,
    subSceneName: String,
  },
  data() {
    return {
      expandedGroups: {}, // 用于记录每组的展开状态

      // 定义模板数组，每个模板包含一个标签和内容
      promptTemplates: [
        { label: "单卡迭代通用模板", text: "您是根据一段文本进行改进（/创作）迭代的专家，后续将给你一段文本，请用中文完成指定要求：\n（请您在此处填充您的迭代要求）" },
        { label: "多卡迭代通用模板", text: "您是综合多段文本进行改进（/创作）迭代的专家，后续将给你多段文本，请用中文完成指定要求：\n（请您在此处填充您的迭代要求）" },
        { label: "改进型迭代模板", text: "您是根据一段文本（/综合多段文本）进行改进迭代的专家，下面将先指明改进要求，再给你一段（/多段）文本，请用中文完成以下要求：\n下面的这段（/这几段）文本是xxx（简要说明各文本<即各卡片内容>是什么、怎么得来的、有无关联等），其中xxx还不够完善（/xxx有误/xxx还需要修改/缺少xxx内容/没有体现xxx指向/其他），理由是xxx，请你做如下修改（/增加/删除/完善/其他）迭代：\n1.改进迭代任务一：一两句话简单描述目标及内容\n2.改进迭代任务二：一两句话简单描述目标及内容\n3....\n\n注意事项及细节：\n1.注意点一\n2...." },
        { label: "创作型迭代模板", text: "您是根据一段文本（/综合多段文本）进行创作迭代的专家，下面将先指明创作撰写要求，再给你一段（/多段）文本，请用中文完成以下要求：\n下面的这段（/这几段）文本是xxx（简要说明各文本<即各卡片内容>是什么、怎么得来的、有无关联等），请你以这些为素材，进行如下（文本创作/代码编写/其他）迭代：\n1.创作迭代任务一：一两句话简单描述目标及内容\n2.创作迭代任务二：一两句话简单描述目标及内容\n3....\n\n注意事项及细节：\n1.注意点一\n2...." },
        { label: "合并模板", text: "您是综合多段文本进行合并迭代的专家，下面将先指明合并要求，再给你xxx段文本，请用中文完成以下要求：\n下面的这xxx段文本（/问答/回答/其他）是xxx（简要说明各文本<即各卡片内容>是什么、怎么得来的、有什么关联、将要有什么作用等）\n（例如：\n下面这两段问答是对同一个提出的要求，两个不同模型给出的回答/下面这两段文本是针对论文的xxx章节xxx小节，撰写的2个不同版本，它们具有一些共识点，需要你找出；其他内容则分模块、分段落对比两个版本孰优孰劣，然后扩长化短）\n请你以这些为素材，进行迭代，对这xxx段文本进行综合合并\n\n其他注意事项及细节：\n1.注意点一\n2...." }
      ],

      menuVisible: false, // 控制菜单显示状态
      keyTopics: [],      // 将提取出的已有的卡片关键词放入此数组，作为此后的备选Tags
      selectedTopics: [], // 当前选中的多个关键词
      titleFilter: "",    // 标题筛选关键词

      showBlankCard: false, // 控制是否显示空白列
      isInitial: true,
      updateCheckbox: false,
      reAcquire: false,

      flashingGroupIndex: -1,
      flashingIndexes: [], // 需要闪烁的多卡卡片索引数组
      flashingIndex: -1, // 当前需要闪烁的单卡卡片索引, 默认没有卡片闪烁
      flashingCids: [], // 需要闪烁的多卡卡片cid数组
      flashingCid: -1, // 当前需要闪烁的单卡卡片cid, 默认没有卡片闪烁
      cardList: [
        // 按理说应该是getall获取完成才知道有多少个，vue才会去加载这些子Card
        // 但这里初始化的时候写了2个默认的，就默认先把前两个位置占用了，导致后来getall之后的前两个位置被占了挂载不上，但后面的不受影响
        // 所以这里不能有默认加载内容
        // {
        //   "title": "title1",
        //   "content": "content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1content1",
        //   "score": 1.7,
        // },
        // {
        //   "title": "title2",
        //   "content": "content2",
        // },
      ],
      choosedCardIdList: [],
      choosedFunc: -1,
      // cardUpdateTmp: false,
      showCardParams: false,
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
      timeModel: '',
      showDialog: false,
      cardQuestionList: ["test", "test2", "test3"],
      choosedText: '',
      userDefineForm: {
        userText: ''
      },
    }
  },
  async created() {
    // 使用 async/await 确保 get_all_cards 在子组件创建前执行完毕
    await this.get_all_cards();
    // 此时，子组件的 created 钩子将在 get_all_cards 完成后执行
  },
  mounted() {
    // this.get_all_cards();
  },
  watch: {
    cardUpdate: function (newVal, oldVal) {
      // 当 cardUpdate 从 false 变为 true 时，执行 get_all_cards 函数
      if (newVal === true) {
        this.isInitial = false
        this.get_all_cards();
      } else {

      }
    },
    menuVis: function (newVal, oldVal) {
      if (newVal === true) {
        this.menuVisible = true
      } else {
        this.menuVisible = false
      }
    },
  },
  computed: {
    // 根据 selectedTopic 过滤卡片
    filteredCards() {
      // 没有选中topic，则显示所有卡片
      // 根据 selectedTopics 和 titleFilter 过滤卡片列表
      let filteredList = this.cardList;

      // 先按关键词进行过滤，只显示 keyWords 包含 selectedTopics 中某些的卡片
      if (this.selectedTopics.length > 0) {
        filteredList = filteredList.filter(card =>
          this.selectedTopics.some(topic => card.keyWords.includes(topic))
        );
      }

      // 再按标题进行模糊过滤
      if (this.titleFilter) {
        const filterText = this.titleFilter.trim();
        const requiredMatchCount = Math.ceil(filterText.length * 0.7); // 计算70%匹配字符数

        filteredList = filteredList.filter(card => {
          const contentTitle = card.contentTitle;
          let matchCount = 0;

          // 统计 filterText 中的字符在 contentTitle 中出现的次数
          for (let char of filterText) {
            if (contentTitle.includes(char)) {
              matchCount++;
            }
            if (matchCount >= requiredMatchCount) {
              return true; // 达到80%匹配则认为匹配成功
            }
          }
          return false; // 未达到70%则不匹配
        });
      }

      return filteredList;
    },
    groupedCardList() {
      // const groups = {};
      const groups = new Map();
      let filteredList = this.cardList;

      // 先按关键词进行过滤，只显示 keyWords 包含 selectedTopics 中某些的卡片
      if (this.selectedTopics.length > 0) {
        filteredList = filteredList.filter(card =>
          this.selectedTopics.some(topic => card.keyWords.includes(topic))
        );
      }

      // 再按标题进行模糊过滤
      if (this.titleFilter) {
        const filterText = this.titleFilter.trim();
        const requiredMatchCount = Math.ceil(filterText.length * 0.7); // 计算70%匹配字符数

        filteredList = filteredList.filter(card => {
          const contentTitle = card.contentTitle;
          let matchCount = 0;

          // 统计 filterText 中的字符在 contentTitle 中出现的次数
          for (let char of filterText) {
            if (contentTitle.includes(char)) {
              matchCount++;
            }
            if (matchCount >= requiredMatchCount) {
              return true; // 达到70%匹配则认为匹配成功
            }
          }
          return false; // 未达到70%则不匹配
        });
      }

      // filteredList.forEach(card => {
      //   console.log(card.theme)
      //   if (!groups[card.theme]) {
      //     groups[card.theme] = [];
      //   }
      //   groups[card.theme].push(card);
      // });
      // return Object.values(groups);

      // 正则表达式匹配模式
      const regex1 = /(\d+)(理解|批判|大纲|扩写|缩写|自定义)/;
      const regex2 = /((\d+,)*\d+)(总结|合并|建议|指导|自定义)/;

      // 定义递归函数，查找并添加符合条件的卡片
      const findAndPushCards = (card, group) => {
        const title = card.title;
        // let match = title.match(regex1) || title.match(regex2);
        let match1 = title.match(regex1);
        let match2 = title.match(regex2);

        // 优先匹配逗号更多的 regex2
        let match = null;

        // 如果两者都匹配，优先选择逗号更多的匹配（match2 的逗号数目更多）
        if (match2 && match1) {
          const countCommaInMatch1 = match1[1].split(',').length;
          const countCommaInMatch2 = match2[1].split(',').length;
          match = countCommaInMatch2 >= countCommaInMatch1 ? match2 : match1;
        } else {
          match = match2 || match1;
        }

        if (match) {
          // 提取 card.cid 列表
          const ids = match[1].split(',').map(id => parseInt(id, 10));
          console.log("cardfold ids:" ,ids)
          
          // 将所有来源卡片按 cid 递归查找并分组
          ids.forEach(id => {
            const matchedCard = this.cardList.find(c => c.cid === id);
            if (matchedCard && !group.includes(matchedCard)) {
              group.push(matchedCard);
              findAndPushCards(matchedCard, group); // 递归查找来源卡片
            }
          });
        }
      };

      // 遍历所有符合条件的卡片，进行分组
      filteredList.forEach(card => {
        const title = card.title;
        // let match = title.match(regex1) || title.match(regex2);
        let match1 = title.match(regex1);
        let match2 = title.match(regex2);

        let match = null;

        // 优先匹配逗号更多的 regex2，比较逗号数量，优先选择逗号更多的
        if (match2 && match1) {
          const countCommaInMatch1 = match1[1].split(',').length;
          const countCommaInMatch2 = match2[1].split(',').length;
          match = countCommaInMatch2 >= countCommaInMatch1 ? match2 : match1;
        } else {
          match = match2 || match1;
        }

        if (match) {
          if (!groups.has(card.cid)) {
            groups.set(card.cid, []);
          }
          groups.get(card.cid).push(card);
          
          // 查找并添加迭代链条中的所有卡片
          findAndPushCards(card, groups.get(card.cid));
        } else {
          // 不符合条件的卡片作为独立分组，或者不显示（因为迭代过的会在别的迭代卡box显示，未迭代的单卡不重要）
          if (!groups.has(card.cid)) {
            groups.set(card.cid, []);
          }
          groups.get(card.cid).push(card);
        }
      });
      console.log("filteredList:", filteredList)

      // 过滤掉那些是其他 group 子集的 group
      // groups 对象使用 Map，是为保持其插入顺序，不像字典自动按cid升序排序，这里将其 values 转为数组参与后续处理和返回
      const groupArray = Array.from(groups.values());
      const filteredGroups = [];

      for (let i = 0; i < groupArray.length; i++) {
        const group = groupArray[i];
        let isSubset = false;

        // 遍历其它 group 检查是否当前 group 是其子集
        for (let j = 0; j < groupArray.length; j++) {
          if (i !== j) { // 跳过自身比较
            const otherGroup = groupArray[j];
            
            // 判断当前 group 是否是 otherGroup 的子集
            isSubset = group.every(card => otherGroup.some(otherCard => otherCard.cid === card.cid));
            
            if (isSubset) {
              break; // 如果是子集，跳出
            }
          }
        }

        // 如果不是子集，保留当前 group
        if (!isSubset) {
          filteredGroups.push(group);
        }
      }
      console.log("fileteredGroups:", groupArray, filteredGroups)

      // 初始化 expandedGroups
      this.expandedGroups = {}; // 重置 expandedGroups
      filteredGroups.forEach((_, index) => {
        this.expandedGroups[index] = false;
      });

      return filteredGroups;
    }
  },
  methods: {
    scrollAllToBottom() {
      // 遍历所有 card-stack 的 ref，并设置其滚动位置为底部
      this.groupedCardList.forEach((_, groupIndex) => {
        const cardStack = this.$refs['cardStack' + groupIndex];
        const element = Array.isArray(cardStack) ? cardStack[0] : cardStack;
        if (element) {
          const actualElement = element.$el || element; // 确保获取的是 DOM 元素
          actualElement.scrollTop = actualElement.scrollHeight - actualElement.clientHeight;
        } else {
          console.error(`Ref not found for groupIndex ${groupIndex}`);
        }
      });
    },

    expandGroup(groupIndex) {
      this.expandedGroups[groupIndex] = !this.expandedGroups[groupIndex]; // 切换展开状态
    },

    applyTemplate(template) {
      // 将模板内容插入到输入框中以供编辑
      this.userDefineForm.userText = template.text;
    },
    // 选择 topics 用于计算属性过滤
    toggleTopicSelection(topic) {
      // 切换选择状态
      if (this.selectedTopics.includes(topic)) {
        this.selectedTopics = this.selectedTopics.filter(t => t !== topic);
      } else {
        this.selectedTopics.push(topic);
      }
    },
    clearSelectedTopics() {
      this.selectedTopics = [];
    },
    showMenu() {
      this.menuVisible = true;
    },
    hideMenu() {
      this.menuVisible = false;
      this.$emit("menuVisNo")
    },

    cardTextNum() {
      this.showBlankCard = true
    },
    cardTextNumOver() {
      this.isInitial = false
      this.get_all_cards();
    },
    cardClickLog(content, score, reason, keyWords, contentTitle) {
      this.$emit('cardClickLog', content, score, reason, keyWords, contentTitle)
    },
    handleMultiHint(numbers, groupIndex) {
      this.flashingGroupIndex = groupIndex
      // 找到所有匹配的卡片索引
      const flashingCids = numbers.reduce((cids, number) => {
        const card = this.cardList.find(card => card.cid === number);
        if (card) {
          const cid = card.cid;
          if (cid !== -1) { // 确保索引有效
            cids.push(cid);
          }
        }
        return cids;
      }, []);

      if (flashingCids.length > 0) {
        this.flashingCids = flashingCids;
        setTimeout(() => {
          // 停止所有卡片的闪烁
          this.flashingCids = [];
        }, 2000); 
      } else {
        console.log("没有找到匹配的卡片");
      }
    },
    handleHint(number, groupIndex) {
      this.flashingGroupIndex = groupIndex
      const card = this.cardList.find(card => card.cid === parseInt(number, 10));
      if (card) {
        this.flashingCid = card.cid;
        setTimeout(() => {
          this.flashingCid = -1; // 停止闪烁
        }, 2000); // 2秒后停止闪烁
      }
    },
    handelUpdateHistory(history, title) {
      this.$emit('update-history', history, title);
    },
    handleCheck(timeParams, timeModel) {
      this.showCardParams = true;
      this.timeParams = timeParams;
      this.timeModel = timeModel;
    },
    hideDialog() {
      this.showCardParams = false;
    },
    cardUserDefine() {
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      this.showDialog = true;
      // this.mergeCard();
    },
    createRelCard(text) {
      this.choosedFunc = 10;
      this.choosedText = text;
      this.showDialog = false;
      this.mergeCard();
    },

    singleCardReact() {
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }
      
      this.$message.success('开始对本卡片的react加强, 请耐心等待一会!');
      let formData = new FormData();
      formData.append('cardIndexList', this.choosedCardIdList);
      react(formData).then(data => {
        if(data['error_num'] === 0) {
          this.isInitial = false
          this.get_all_cards();
          this.$message.success('卡片内容及红蓝评分更新完成');
        } else {
          this.$message.error('出错了，请退出重登再试，若再次出错，请联系管理员并暂勿使用此功能');
        }
      })
    },
    singleCardUnderstand() {
      // Help me understand the selected note
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      this.choosedFunc = 4;
      this.mergeCard();
    },
    singleCardCrtique() {
      // Critique the selected note
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      this.choosedFunc = 5;
      this.mergeCard();
    },
    singleCardCreateOutline() {
      // Create an outline for the selected note
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      this.choosedFunc = 6;
      this.mergeCard();
    },
    cardSummarize() {
      // Summarize the selected notes
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 0;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },
    cardSuggestIdeas() {
      // Suggest ideas from my sources related to the selected notes
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 1;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },

    cardStudyGuide() {
      // Create a study guide for the selected notes
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 2;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },
    cardCombine() {
      // Combine the selected notes into a single note
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限执行此操作');
        return
      }

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 3;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },
    updateC() {

      // this.$router.go(0);
      // this.$message.success('保存成功！');
    },
    mergeCard() {
      let formData = new FormData();
      formData.append('cardIndexList', this.choosedCardIdList);
      formData.append('username', localStorage.getItem('userId'));
      formData.append('datetime', getDateTime());
      //model_id 栏改为参与融合的卡片的数量
      //status 栏改为参与迭代的次数
      formData.append('model_id', 1003);//1003表示是迭代得到的卡片
      formData.append('status', 2);//status=2表示卡片由迭代得到
      formData.append('func', this.choosedFunc);
      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', this.subSceneName);
      formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递
      if (this.choosedFunc == 10) {
        formData.append('text', this.choosedText);
      }
      else {
        formData.append('text', '');
      }
      this.showBlankCard = true
      mergeCardBackend(formData).then(response => {
        if (response.error_num === 0) {
          let finalContent=response.finalContent;
          let cid = response.cardId
          this.isInitial = false
          this.get_all_cards();
          this.waitDecodedResult(cid, finalContent)
          // this.isInitial = false
          // this.get_all_cards();
          // this.$message.success('卡片添加成功');
          // this.$emit('cardMerge', finalContent)
        }
        else {
          this.isInitial = false
          this.get_all_cards();
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
        this.isInitial = false
        this.get_all_cards();
        this.$emit('cardMerge', finalContent, this.choosedText)
      } else {
        let formDataSFT = new FormData();
        formDataSFT.append('content', decodedResult);
        formDataSFT.append('cid', cid);
        card_evalSFT(formDataSFT).then(responseSFT => {
          if (responseSFT.error_num === 0) {
            this.$message.success('卡片保存成功！');
          } else {
            this.$message.error('卡片保存成功，但红蓝微调评测模型打分保存失败');
          }
          this.isInitial = false
          this.get_all_cards();
          this.$emit('cardMerge', finalContent, this.choosedText)
        });
      }
    },

    addChoseCard2List(para) {
      if (para['checked']) {
        this.choosedCardIdList.push(para['cid']);
        // alert(para['cid']);
      }
      else {
        const index = this.choosedCardIdList.indexOf(para['cid']);
        if (index > -1) {
          this.choosedCardIdList.splice(index, 1);
        }
      }
      this.$emit('chooseCardChange', this.choosedCardIdList)
      // alert(id);
    },
    deleteCard() {
      this.isInitial = false
      this.$message.success('删除成功！');
      this.get_all_cards();
    },
    updateOrder() {
      this.isInitial = false
      this.get_all_cards();
      this.$message.success('您刚刚打开的卡片以及相关卡片已被移动至最前！');
    },
    reAcquireOver() {
      this.reAcquire = false
    },
    generateKeyTopics() {
      // 获取所有 keyWords，分割后去重并存入 keyTopics
      const keywordsSet = new Set();

      this.cardList.forEach(card => {
        if (card.keyWords) {    // 检查 keyWords 是否为空
          const keywords = card.keyWords.split(/[,，]/);    // 支持中英文逗号分隔
          keywords.forEach(keyword => {
            const trimmedKeyword = keyword.trim();
            if (trimmedKeyword && !keywordsSet.has(trimmedKeyword)) { // 检查非空且未添加
              keywordsSet.add(trimmedKeyword);
            }
          });
        }
      });

      this.keyTopics = Array.from(keywordsSet); // 转换为数组并赋值
      this.$emit("sendKeyTopics", this.keyTopics)
    },

    async get_all_cards() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      get_cards(formData).then(data => {
        this.showBlankCard = false

        let content = data.content;
        this.cardList = content;
        this.generateKeyTopics();
        // 初始化时让所有 card-stack 滚动到底部
        // setTimeout(() => {
        //   this.scrollAllToBottom();
        // }, 100);

        // 测试样例数据，为每个卡片随机添加一个主题
        const themes = ['植物', '动物', '微生物', '病毒', '细菌', '蓝藻', '无机物'];
        // const themes = ['植物', '动物', '微生物'];
        this.cardList = this.cardList.map(card => ({
          ...card,
          theme: themes[Math.floor(Math.random() * themes.length)]
        }));
        
        // 更新完毕，传回mainpage避免watch重复更新卡片
        this.$emit('cardUpdateOver');
        // 除了初始化外，调用此函数的位置均需要reacquire
        // 到上面为止只更新了cardList，但是cardList传到Card的信息并没有都被正确地用上，Card中使用了很多CardInfo信息，而它之前只在mounted
        // 更新一次，更新cardList并不会重新执行mounted，所以只能通过reAcquire变量通知其执行与mounted内一样的代码段，正确更新CardInfo
        if(this.isInitial === false) {
          // this.reAcquire = true
          this.updateCheckbox = true
          setTimeout(() => {
            this.updateCheckbox = false
          }, 50);
        }
      }).catch(error => {
        this.showBlankCard = false
        console.error("An error occurred:", error); // 错误处理
        this.$message.error("发生了一个错误, 具体log: ", error);
      });
    }
  }
};
</script>

<style scoped>
.cardParams-dialog {
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
  width: 40vw;
  height: 60vh;
  max-width: 100%;
}

.cardParams-dialog .dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.cardParams-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}

.grid-container {
  max-height: 78vh;
  overflow-y: auto;

  padding: 30px;
  padding-left: 40px;

  .grid-row {
    padding: 0px;
  }

  .grid-col {
    padding: 0px;
  }

  .card-stack {
    position: relative;
    /* height: 250px;  */
    width: 280px;
    height: 300px; /* 设置每组卡片的最大高度 */
    overflow-x: hidden;
    overflow-y: scroll; /* 允许上下滚动 */
    margin-bottom: 10px;
    border-radius: 15px;
  }

  .card-stack::-webkit-scrollbar {
    display: none; /* 隐藏滚动条 */
  }
}



.card-combine-btn,
.card-summarize-btn,
.card-study-guide-btn,
.card-suggest-ideas-btn,
.card-react-btn,
.card-user-define {
  padding: 2px 4px; /* 保持原定的padding */
  border: none; /* 无边框 */
  border-radius: 4px; /* 保持原定的圆角 */
  cursor: pointer; /* 鼠标悬停时显示手形光标 */
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2); /* 轻微的阴影，增加了深度 */
  transition: 
    box-shadow 0.3s ease-in-out, 
    background-color 0.3s ease-in-out,
    transform 0.1s ease-out; /* 平滑的阴影和背景颜色过渡 */
  letter-spacing: 0.5px; /* 字母间距微调，提升视觉效果 */
  text-transform: uppercase; /* 所有字母大写，增加正式感 */
  overflow: hidden; /* 确保阴影不会溢出 */
  position: relative; /* 为添加元素做准备 */
}

.card-combine-btn::before,
.card-summarize-btn::before,
.card-study-guide-btn::before,
.card-suggest-ideas-btn::before,
.card-react-btn::before,
.card-user-define::before {
  content: ''; /* 创建一个伪元素 */
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(45deg, rgba(255, 255, 255, 0.1), rgba(0, 0, 0, 0.1));
  transform: scale(0);
  transition: transform 0.3s ease-in-out; /* 伪元素过渡动画 */
}

.card-combine-btn:hover,
.card-summarize-btn:hover,
.card-study-guide-btn:hover,
.card-suggest-ideas-btn:hover,
.card-react-btn:hover,
.card-user-define:hover {
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3); /* 鼠标悬停时更大的阴影 */
  transform: translateY(-2px); /* 轻微提升，制造按下效果 */
}

.card-combine-btn:hover::before,
.card-summarize-btn:hover::before,
.card-study-guide-btn:hover::before,
.card-suggest-ideas-btn:hover::before,
.card-react-btn:hover::before,
.card-user-define:hover::before {
  transform: scale(1); /* 鼠标悬停时伪元素放大，增加光泽感 */
}

/* 卡片融合按钮 */
.card-combine-btn {
  background-color: #5e3380; /* 深蓝色背景，保持神秘感 */
  color: rgb(255, 255, 255); /* 白色文字 */
}

.card-combine-btn:hover {
  background-color: #4b2355; /* 鼠标悬停时更深的蓝色 */
}

/* 多卡片内容总结按钮 */
.card-summarize-btn {
  background-color: #8B3626;
  color: white;
}

.card-summarize-btn:hover {
  background-color: #5C2121;
}

/* 多卡片学习指导按钮 */
.card-study-guide-btn {
  background-color: #1E4D3C;
  color: white;
}

.card-study-guide-btn:hover {
  background-color: #0F3B2B;
}

/* 总结想法按钮 */
.card-suggest-ideas-btn {
  background-color: #00796B;
  color: white;
}

.card-suggest-ideas-btn:hover {
  background-color: #005662;
}

/* 自定义追问按钮 */
.card-user-define {
  background-color: #4A2C2A;
  color: white;
}

.card-user-define:hover {
  background-color: #2E1B1B;
}

/* react加强按钮 */
.card-react-btn {
  background-color: #275176; /* 深蓝色背景，保持神秘感 */
  color: rgb(255, 255, 255); /* 白色文字 */
}

.card-react-btn:hover {
  background-color: #2a2e91; /* 鼠标悬停时更深的蓝色 */
}



.createCardQuestion .el-dialog {
  width: 60%;
  /* 根据需要调整宽度 */
  border-radius: 8px;
  /* 轻微圆角 */
  overflow: hidden;
  /* 隐藏溢出内容 */
  background-color: #ffffff;
  /* 背景色 */
  box-shadow: 0 4px 12px 0 rgba(0, 0, 0, 0.1);
  /* 添加阴影 */
}

.createCardQuestion .el-dialog__header {
  padding: 15px 20px;
  /* 头部内边距 */
  background-color: #eef1f6;
  /* 淡蓝色背景 */
  border-bottom: 1px solid #d3dce6;
  /* 下边框 */
}

.createCardQuestion .el-dialog__title {
  font-size: 18px;
  /* 标题字体大小 */
  color: #333;
  /* 标题颜色 */
}

.createCardQuestion .el-dialog__body {
  padding: 20px;
  /* 内容区域内边距 */
}

/* 追问标题样式 */
.createCardQuestion .cardQuestion {
  margin: 0 0 20px;
  /* 重置外边距和下边距 */
  font-size: 16px;
  /* 字体大小 */
  color: #333;
  /* 字体颜色 */
  text-align: center;
  /* 文本居中 */
}

/* 按钮容器样式 */
.ButtonListContainer {
  display: flex;
  flex-wrap: wrap;
  /* 允许换行 */
  justify-content: center;
  /* 水平居中对齐 */
  gap: 10px;
  /* 按钮之间间距 */
}

/* 按钮样式 */
.ButtonList {
  flex: 0 1 150px;
  /* 允许按钮宽度至少为150px，但可以更宽 */
  margin: 5px;
  /* 按钮外边距 */
  padding: 10px;
  /* 内边距 */
  font-size: 14px;
  /* 字体大小 */
  border-radius: 4px;
  /* 圆角 */
  background-color: #409eff;
  /* 背景色 */
  color: white;
  /* 字体颜色 */
  transition: background-color 0.3s;
  /* 渐变效果 */
  text-align: center;
  /* 文本居中 */
  word-break: break-word;
  /* 单词断行 */
  box-sizing: border-box;
  /* 边框计算在宽度内 */
}

.ButtonList:hover {
  background-color: #50bfff;
  /* 鼠标悬停效果 */
}

/* 输入框样式 */
.createCardQuestion .myinput .el-input__inner {
  border-radius: 4px;
  /* 圆角 */
  padding: 8px 10px;
  /* 内边距 */
  font-size: 14px;
  /* 字体大小 */
}

/* 自定义追问按钮样式 */
.createCardQuestion .userDefineButton {
  margin-left: 10px;
  /* 与输入框的间距 */
  padding: 8px 15px;
  /* 内边距 */
  font-size: 14px;
  /* 字体大小 */
  border: none;
  /* 无边框 */
  border-radius: 4px;
  /* 圆角 */
  background-color: #67c23a;
  /* 背景色 */
  color: white;
  /* 字体颜色 */
  transition: background-color 0.3s;
  /* 渐变效果 */
}

.createCardQuestion .userDefineButton:hover {
  background-color: #85ce61;
  /* 鼠标悬停效果 */
}

.inline-form {
  display: flex;
  align-items: center;
  /* 垂直居中对齐 */
}

.input-button-group {
  flex: 1;
  /* 让这个容器占据剩余空间 */
  display: flex;
  /* 使用flex布局 */
  align-items: center;
  /* 垂直居中对齐 */
  justify-content: flex-start;
  /* 水平开始对齐 */
}

/* 移除el-input的margin，因为我们不需要Element UI默认的间距 */
.myinput .el-input__inner {
  margin: 0;
  /* 移除输入框的外边距 */
}

/* 调整按钮的margin，使其与输入框对齐 */
.userDefineButton {
  margin-left: 10px;
  /* 按钮与输入框之间的间距 */
}


@keyframes flash {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.1); }
}

.flashing {
  animation: flash 1s infinite; /* 可以设置为无限循环以便更容易观察 */
}


.notebook-card-waiting-single {
  position: absolute;
  top: 0;
  left: 0;

  height: 200px;
  width: 290px;
  border-radius: 10px;
  overflow: hidden;

  padding: 20px;
  background-color: #ffffffdd;
  margin: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: #1d1d1d;
  font-family: 'Arial', sans-serif;
  z-index: 10; /* This ensures it stays on top */
  /* position: relative; */
}


.notebook-card-waiting {
  height: 200px;
  width: 290px;
  border-radius: 10px;
  overflow: hidden;

  padding: 20px;
  background: linear-gradient(to right, #d7def2 0%, #ffffff 30%, #ffffff 70%);
  margin: 10px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1), 0 6px 20px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: #1d1d1d;
  font-family: 'Arial', sans-serif;
  position: relative;
}

.notebook-card-waiting::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 10px;
  z-index: 1;
}

.waiting-text {
  position: relative;
  z-index: 2;
  font-size: 1.2em;
  font-weight: bold;
  text-align: center;
}

.waiting-gif {
  position: relative;
  z-index: 2;
  width: 150px;
  height: 150px;
}




.tags-container {
  position: absolute;
  top: 0px; /* 菜单出现在按钮旁 */
  right: 300px;
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-start;
  gap: 10px; /* Adjust the gap between tags */
  background-color: rgba(255, 255, 255, 0.9); /* Semi-transparent background */
  border-radius: 8px; /* Rounded corners */
  padding: 10px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); /* Optional: Adds a subtle shadow */
  margin-top: 5px;
  z-index: 1000; /* 保证菜单显示在前面 */
}

/* 标题筛选部分 */
.title-filter {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.filter-input {
  padding: 4px 8px;
  border: 2px solid #2f2f2f;
  border-radius: 4px;
  width: 200px; /* 调整宽度 */
}

/* 标签标题和恢复按钮 */
.tags-header {
  display: flex;
  align-items: center;
  width: 100%;
  justify-content: space-between;
  font-weight: bold;
  margin-bottom: 8px;
}

.reset-btn {
  background-color: #ff5555;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
}

.tag-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px; /* Rounded corners for buttons */
  background-color: #6f559f; /* GitLab-like background color */
  color: white;
  font-size: 14px;
  cursor: pointer;
  outline: none;
  transition: background-color 0.3s ease;
  margin: 2px; /* Optional: Adds margin around each button */
}

.tag-btn:hover {
  background-color: #493d8b; /* Darker color on hover */
}

/* 已选中状态的按钮 */
.tag-btn.selected {
  background-color: #1f1652;
}



.form-container {
  display: flex;
  flex-direction: column; /* 垂直堆叠子元素 */
  gap: 10px;
  width: 100%; /* 占据父容器的全部宽度 */
}

.template-buttons {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}


.card-mask {
  position: sticky;
  top: 0;
  left: 0;
  right: 0;
  height: 100%;
  background-color: rgba(255, 255, 255, 0);
  z-index: 20; /* 确保在其他内容上方 */
}
</style>