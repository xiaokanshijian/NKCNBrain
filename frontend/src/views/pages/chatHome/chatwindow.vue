<template>
  <!-- 子组件内容 -->
  <div class="chat-window">
    <!-- 中断按钮 - 仅在流式输出且未显示eval/second-eval时显示 -->
    <div
      v-if="shouldShowInterruptButton()"
      class="interrupt-button-container"
      @click.stop="handleInterrupt"
    >
      <button class="interrupt-button">
        <span class="interrupt-icon">⏸</span>
        <span class="interrupt-text">中断</span>
      </button>
    </div>

    <!-- 已中断提示 -->
    <div
      v-if="isInterrupted"
      class="interrupted-indicator"
    >
      <span class="interrupted-icon">⏹</span>
      <span class="interrupted-text">已中断</span>
    </div>

    <div class="botoom">
      <div class="chat-content" ref="chatContent"
           @mouseenter="handleMouseEnter"
           @mouseleave="handleMouseLeave">
        <div class="chat-wrapper" v-for="(item, index) in chatList" :key="item.id">

          <div class="chat-model" v-if="item.uid !== '1001' && item.uid !== '2000'">
            <div class="chat-text" v-if="item.chatType == 0" v-bind:style="{ color: item.color }" @click="noChangeModel">
              <!-- {{ item.msg }} -->
              <!-- <template v-if="item.msg.includes('<div style=&quot;color: #999; font-size: 12px; margin-top: 10px; border-top: 1px dashed #ddd; padding-top: 5px;&quot;>') && item.msg.includes('⏱️ 用时统计：')">
                <AnswerParser :answer="getMessageWithoutTiming(item.msg)"/>
                <div v-html="getTimingPart(item.msg)"></div>
              </template> -->
              <!-- 使用timingInfo字段来显示用时统计，避免污染msg内容 -->
              <template v-if="item.timingInfo">
                <AnswerParser :answer="item.msg"/>
                <!-- 综合评分标签（显示在用时统计之前） -->
                <div v-if="item.evalComprehensiveScore || item.secondEvalComprehensiveScore" style="margin-top: 12px;">
                  <div v-if="item.evalComprehensiveScore && item.msg.includes('```eval')" 
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 6px 6px; border-radius: 12px; display: block; width: fit-content; font-weight: bold; font-size: 13px; margin-bottom: 6px; box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);">
                    📊 综合评分(第一次): {{item.evalComprehensiveScore}}/5.0
                  </div>
                  <div v-if="item.secondEvalComprehensiveScore && item.msg.includes('```second-eval')" 
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 6px 6px; border-radius: 12px; display: block; width: fit-content; font-weight: bold; font-size: 13px; box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);">
                    📊 综合评分(第二次): {{item.secondEvalComprehensiveScore}}/5.0
                  </div>
                </div>
                <div v-html="item.timingInfo"></div>
              </template>
              <template v-else>
                <AnswerParser :answer="item.msg"/>
                <!-- 综合评分标签（没有timing info时） -->
                <div v-if="item.evalComprehensiveScore || item.secondEvalComprehensiveScore" style="margin-top: 12px;">
                  <div v-if="item.evalComprehensiveScore && item.msg.includes('```eval')" 
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 6px 12px; border-radius: 12px; display: block; width: fit-content; font-weight: bold; font-size: 13px; margin-bottom: 6px; box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);">
                    📊 综合评分(第一次): {{item.evalComprehensiveScore}}/5.0
                  </div>
                  <div v-if="item.secondEvalComprehensiveScore && item.msg.includes('```second-eval')" 
                       style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 6px 12px; border-radius: 12px; display: block; width: fit-content; font-weight: bold; font-size: 13px; box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);">
                    📊 综合评分(第二次): {{item.secondEvalComprehensiveScore}}/5.0
                  </div>
                </div>
              </template>
            </div>
            <div class="chat-img" v-if="item.chatType == 1">
              <img :src="item.msg" alt="表情" v-if="item.extend.imgType == 1" style="width: 100px; height: 100px" />
              <el-image :src="item.msg" :preview-src-list="srcImgList" v-else>
              </el-image>
            </div>
            <div class="chat-img" v-if="item.chatType == 2">
              <div class="word-file">
                <FileCard :fileType="item.extend.fileType" :file="item.msg"></FileCard>
              </div>
            </div>
            <div class="info-time">
              <!-- 左侧信息 -->
              <div class="left-info">
                <img :src="item.headImg" alt="" />
                <span>
                  {{
                    item.name === 'GPT4' 
                      ? item.name + 'o' 
                      : item.name === 'Llama3' 
                        ? item.name + '.1' 
                        : item.name === 'Deepseek' 
                          ? 'Deepseek-V3' 
                          : item.name === 'Deepseek-reasoner' 
                            ? 'Deepseek-R1' 
                            : item.name
                  }}
                </span>
                <span>{{ item.time }}</span>
              </div>
              <!-- 右侧操作按钮 -->
              <div class="right-actions">
                <img 
                  @click="handleCopy(item.msg)" 
                  class="img-button" 
                  src="@/assets/img/copy.png" 
                  alt="复制" 
                  title="复制" 
                />
                <div class="button-container" 
                     @mouseenter="showPinButton = index" 
                     @mouseleave="showPinButton = -1">
                  <img 
                    @click="handleButtonClick(index, item.uid)" 
                    class="img-button" 
                    :src="fileNameList.length === 1 && (fileNameList[0].endsWith('.jpg') || fileNameList[0].endsWith('.png') || fileNameList[0].endsWith('.jpeg')) 
                      ? require('@/assets/img/mergeLeft.png') 
                      : (choosedCardIdList.length === 1 
                        ? require('@/assets/img/mergeMain.png') 
                        : require('@/assets/img/pin.png'))" 
                    alt="添加卡片" 
                    :title="fileNameList.length === 1 && (fileNameList[0].endsWith('.jpg') || fileNameList[0].endsWith('.png') || fileNameList[0].endsWith('.jpeg'))
                      ? '点击合并到图片文档的向量库摘要'
                      : (choosedCardIdList.length === 1 
                        ? '点击合并到原卡' 
                        : '点击，用于留存卡片')" 
                  />
                  <!-- 悬浮pin按钮 -->
                  <img 
                    v-if="showPinButton === index && (fileNameList.length === 1 && (fileNameList[0].endsWith('.jpg') || fileNameList[0].endsWith('.png') || fileNameList[0].endsWith('.jpeg')) || choosedCardIdList.length === 1)"
                    @click="handlePinCard(index, item.uid)" 
                    class="pin-overlay-button" 
                    src="@/assets/img/pin.png" 
                    alt="钉卡" 
                    title="点击钉卡" 
                  />
                </div>
                <img 
                  :data-model-response="item.msg"
                  :data-model-name="item.name"
                  :data-chat-index="index"
                  class="merge-button" 
                  src="@/assets/img/merge.png" 
                  alt="合并回答"
                  title="拖拽，用于合并回答"
                  draggable="true"
                  @dragstart="handleDragStart($event, index)"
                  @dragend="handleDragEnd"
                  @click="noChangeModel"
                />
                <img 
                  @click="handleRetry(item, index)" 
                  class="img-button" 
                  src="@/assets/img/Redo.png" 
                  alt="重做" 
                  title="重做此回答" 
                />
                <span v-if="LUI2_plus" class="lui2-plus-icon" @click="run_LUI2_plus(item.msg, index)" title="点此进一步做问答追问群组增强">
                  plus
                </span>
              </div>
            </div>
          </div>

          <div class="chat-model" v-else-if="item.uid === '2000'">
            <!-- 复制第一个 div 的全部内容 -->
            <div class="chat-text purple-bg" v-if="item.chatType == 0" v-bind:style="{ color: item.color }" @click="noChangeModel">
              <!-- {{ item.msg }} -->
              <!-- <AnswerParser :answer="item.msg"/> -->
              <!-- 使用timingInfo字段来显示用时统计，避免污染msg内容 -->
              <template v-if="item.timingInfo">
                <AnswerParser :answer="item.msg"/>
                <div v-html="item.timingInfo"></div>
              </template>
              <AnswerParser v-else :answer="item.msg"/>
            </div>
            <div class="chat-img" v-if="item.chatType == 1">
              <img :src="item.msg" alt="表情" v-if="item.extend.imgType == 1" style="width: 100px; height: 100px" />
              <el-image :src="item.msg" :preview-src-list="srcImgList" v-else>
              </el-image>
            </div>
            <div class="chat-img" v-if="item.chatType == 2">
              <div class="word-file">
                <FileCard :fileType="item.extend.fileType" :file="item.msg"></FileCard>
              </div>
            </div>
            <div class="info-time">
              <!-- 左侧信息 -->
              <div class="left-info">
                <img :src="item.headImg" alt="" />
                <span>
                  {{
                    item.name === 'GPT4' 
                      ? item.name + 'o' 
                      : item.name === 'Llama3' 
                        ? item.name + '.1' 
                        : item.name === 'Deepseek' 
                          ? 'Deepseek-V3' 
                          : item.name === 'Deepseek-reasoner' 
                            ? 'Deepseek-R1' 
                            : item.name
                  }}
                </span>
                <span>{{ item.time }}</span>
              </div>
              <!-- 右侧操作按钮 -->
              <div class="right-actions">
                <img 
                  @click="handleCopy(item.msg)" 
                  class="img-button" 
                  src="@/assets/img/copy.png" 
                  alt="复制" 
                  title="复制" 
                />
                <div class="button-container" 
                     @mouseenter="showPinButton = index" 
                     @mouseleave="showPinButton = -1">
                  <img 
                    @click="handleButtonClick(index, item.uid)" 
                    class="img-button" 
                    :src="fileNameList.length === 1 && (fileNameList[0].endsWith('.jpg') || fileNameList[0].endsWith('.png') || fileNameList[0].endsWith('.jpeg')) 
                      ? require('@/assets/img/mergeLeft.png') 
                      : (choosedCardIdList.length === 1 
                        ? require('@/assets/img/mergeMain.png') 
                        : require('@/assets/img/pin.png'))" 
                    alt="添加卡片" 
                    :title="fileNameList.length === 1 && (fileNameList[0].endsWith('.jpg') || fileNameList[0].endsWith('.png') || fileNameList[0].endsWith('.jpeg'))
                      ? '点击合并到图片文档的向量库摘要'
                      : (choosedCardIdList.length === 1 
                        ? '点击合并到原卡' 
                        : '点击，用于留存卡片')" 
                  />
                  <!-- 悬浮pin按钮 -->
                  <img 
                    v-if="showPinButton === index && (fileNameList.length === 1 && (fileNameList[0].endsWith('.jpg') || fileNameList[0].endsWith('.png') || fileNameList[0].endsWith('.jpeg')) || choosedCardIdList.length === 1)"
                    @click="handlePinCard(index, item.uid)" 
                    class="pin-overlay-button" 
                    src="@/assets/img/pin.png" 
                    alt="钉卡" 
                    title="点击钉卡" 
                  />
                </div>
                <img 
                  :data-model-response="item.msg"
                  :data-model-name="item.name"
                  :data-chat-index="index"
                  class="merge-button" 
                  src="@/assets/img/merge.png" 
                  alt="合并回答"
                  title="拖拽，用于合并回答"
                  draggable="true"
                  @dragstart="handleDragStart($event, index)"
                  @dragend="handleDragEnd"
                  @click="noChangeModel"
                />
                <img 
                  @click="handleRetry(item, index)" 
                  class="img-button" 
                  src="@/assets/img/Redo.png" 
                  alt="重做" 
                  title="重做此回答" 
                />
                <span v-if="LUI2_plus" class="lui2-plus-icon" @click="run_LUI2_plus(item.msg, index)" title="点此进一步做问答追问群组增强">
                  plus
                </span>
              </div>
            </div>
          </div>

          <div class="chat-me" v-else>
            <div class="chat-text" v-if="item.chatType == 0" v-bind:style="{ color: item.color }" @click="noChangeModel"
              :class="{ 'purple-bg-me': item.msg && item.msg.includes('对于前一次用户（我）提出的问题，你给出了回答，针对你的回答内容，下面会给你一些修改样例或再次迭代的建议Prompt') }">
              {{ item.msg }}
            </div>
            <div class="chat-img" v-if="item.chatType == 1">
              <img :src="item.msg" alt="表情" v-if="item.extend.imgType == 1" style="width: 100px; height: 100px" />
              <el-image style="max-width: 300px; border-radius: 10px" :src="item.msg" :preview-src-list="srcImgList"
                v-else>
              </el-image>
            </div>
            <div class="chat-img" v-if="item.chatType == 2">
              <div class="word-file">
                <FileCard :fileType="item.extend.fileType" :file="item.msg"></FileCard>
              </div>
            </div>
            <div class="info-time">
              <span>{{ item.name }}</span>
              <span>{{ item.time }}</span>
              <img :src="item.headImg" alt="" />
            </div>
          </div>
          
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { h } from 'vue';
import { ElNotification, ElMessage, ElProgress } from 'element-plus'; // 注意：在 Vue 3 中是 ElNotification 和 ElMessage

import { animation, deepCopy } from "@/utils/util";
import { getChatMsg } from "@/api/getData";
import { get_model_eval, getTime, getDateTime, modelHL, modelHLStream, getDepthSuggestion } from "@/api/getData"
import { chat_send, chat_upload, chat_sendParams, agent_LUI2, rel_questions_request, card_rel_questions_request, initFileUpload } from "@/api/chat/send_message"
import { card_upload, card_score, qa_upload, card_eval, card_evalSFT, card_updateContentById } from "@/api/card/send_card"
import { update_img_text } from "@/api/card/get_card"
import { getCardsContentByIds } from "@/api/card_zym/card_js";
import { getSceneSummary } from "@/views/pages/mainHome/my_js"
// import { getPinnedCrossNotebooksForApi } from '@/utils/pinnedCrossNotebooks'
import { interruptResponse } from "@/api/interrupt"
import router from '@/router'
import HeadPortrait from "@/components/chatWindow/HeadPortrait";
import FileCard from "@/components/fileWindow/FileCard.vue"
import AnswerParser from '@/components/chatWindow/AnswerParser.vue';
import { faVolumeXmark } from "@fortawesome/free-solid-svg-icons";
import { provide, ref } from 'vue'
import { modelManager } from "@/utils/ModelManager.js"
import { API_BASE_URL } from '@/config/apiConfig';

// const iterationPrompt = `\n\n## 从"对"到"妙"——击穿真实目标的迭代升华

// ### 一、理解深评指引（必读）

// 你刚刚收到的红蓝深评包含了关键改进指引，请仔细理解：

// **真实目标识别**：深评已帮你识别用户问题背后的真实目标
// - 三问定位：底线（最坏能接受什么）→愿景（最好能做到什么）→着力点（现在具体做什么）
// - **你的任务**：击穿这个真实目标，而不只是回答表面问题

// **认知层次分析**：深评已诊断当前回答在哪个/哪些层次
// - 红色业务层（仅回答问题）→蓝色技术层（工具性、方法性描述）→紫色场景层（提炼框架）→绿色自然层（简单深刻）
// - **你的任务**：按深评指引升维，通常是从前两层升到后两层

// **结构诊断**：深评已分析你原回答的结构
// - D层具体内容（70%）是否充实？M层方法原则（20%）是否模糊？T层本质统领（10%）是否缺失？
// - **你的任务**：找到方法和本质（M层和T层），让原回答中具体内容D基于它们自然拔高

// **简单深刻目标**：深评可能给出了"绿色自然语言"提示
// - **你的任务**：找到统领性简单表达，用2-4个简单词汇击穿回答精髓（类似都江堰"鱼嘴·飞沙堰·宝瓶口"、真实目标"指南针→凸透镜→水电站→种子"的简单表达）

// ---

// ### 二、三问锁定改进方向

// **问1：底线是什么**（守住底线）
// - 原回答有没有跑题？有没有事实错误？
// - 改进底线：不跑题、不出错、逻辑清晰

// **问2：愿景是什么**（追求卓越）
// - 这个回答做到极致会是什么样？
// - 改进愿景：击穿"真实目标"、达到简单深刻

// **问3：着力点是什么**（即刻行动）
// - 深评中的"关键路径"和"具体建议"就是你的着力点
// - 改进着力点：按深评的3大模块执行

// ---

// ### 三、四色升维执行法

// **从业务/技术层（红蓝层）→场景层（紫色层）**：
// 1. 从多个具体点（D）中找**共性**
// 2. 抽象成**方法论/原则**（M层）
// 3. 形成**思维框架**（紫色场景语言）
// 4. 例：从"注意力计算公式"（红）+"多头机制"（蓝）→提炼出"动态加权筛选原则"（紫）

// **如果已在紫色层→升维到绿色**：
// 1. 从方法论（M）中找**本质**
// 2. 提炼成**统领性表达**（T层）
// 3. 用**简单自然的词汇**表达（绿色自然语言）
// 4. 例：从"动态加权筛选"（紫）→升华为"注意力=放大镜"（绿）

// **关键原则**：
// - 升维不是"压缩"，而是"提炼本质"
// - 升维不是"丢失细节"，而是"找到统领点"
// - 升维后，原有的内容D会因为有了方法M和本质T的指引而自然拔高

// ---

// ### 四、DMT结构拔高执行法

// 认真理解M和T的定义，它们是拔高的关键

// **正确做法**：
// 1. **保留D的精华**：原回答中正确、具体的内容保留
// 2. **补充方法M层**：在具体内容基础上，补充方法论/原则
// 3. **提炼本质T层**：找到一个统领性原子点
// 4. **让D指向M，M指向T形成同频共振**：T本质统领→M方法承接→D具体落实（就像都江堰精妙的选址、岷江水的顶级势能为T，最终鱼嘴飞沙堰宝瓶口三级筛分是D，M应该是“深淘滩，低作堰”的维护原则作为中间层，承接T的顶级设计，指导D的具体筛分做法）

// **错误做法**：
// - 删除D层具体内容
// - 完全重写D层具体内容
// - 大量改变原有结构

// ---

// ### 五、寻找简单深刻表达

// 前面已经说过，此处不再赘述，强调几个关键原则：

// **关键**：
// - 简单：用日常词汇，易于理解（不要用某专业术语例如“编码器”之类）
// - 深刻：击中本质，涵盖精髓
// - 具体：不是空洞比喻，要能指导原有D层具体内容
// - 避免：玄学化、心灵鸡汤化、过度比喻而丢失具体性

// 除了前面说过的都江堰、真实目标例子，这样也是比较好的例子：Transformer就像从"望远镜"（RNN的逐步扫视）升级到"卫星俯瞰"（全局视野）

// ---

// ### 六、四层递进策略

// **基础层**（守住底线）：不跑题、逻辑清晰、修正错误

// **进阶层**（符合细节）：补充精准数据/案例、找统领点、击穿分点

// **高阶层**（契合场景）：符合场景语境、视角递进、语境转换

// **卓越层**（视角独到）：独到视角、"妙"的思考、简单深刻、本质洞察

// **判断标准**：读完后让人觉得"原来还能这样理解！"、"这个角度真绝！"

// ---

// ### 七、深评三大模块执行

// **核心诊断**：这是改进的总方向，新回答必须完全解决指出的关键问题

// **思维突破**：
// - 关键路径：必须覆盖的1-2个核心维度
// - 具体建议：可直接执行的方法必须体现
// - 隐藏维度：原回答遗漏的角度必须补充

// **激发要点**：
// - 策略执行：展现推理过程/多角度权衡/网状思维
// - 视角牵引：如明确"以XX视角重构"，必须严格执行
// - 字数控制：明确字数要求必须遵守，但优先考虑原问题要求

// ---

// ### 八、禁止错误

// **发虚（严重问题）**
// - 不要丢失原回答中的分点结构/案例/细节等具体信息
// - 不要变成"心灵鸡汤"式空洞回答

// **跑题**：不要为了创新而偏离原问题核心，必须击穿"真实目标"

// **推翻重写**：切忌推翻重写、另起炉灶，应该在原有基础上拔高

// **冗长**：字数合理，不要堆砌内容，要提炼精髓，遵循"简单而深刻"原则

// **假创新**：不要只是换个说法没有新观点，必须有实质性的认知升维

// **用内部语言**：DMT、除乘加、四色语言是内部术语，用于深入思考，最终回答时切忌直接出现"DMT"/"除乘加"/"红蓝紫绿"这类字眼，必须转换、自然融入

// ---

// ### 九、检查清单

// 1. **修正错误**：事实错误、逻辑错误、语言幻觉是否已解决？
// 2. **击穿目标**：是否击穿了"真实目标"而非停留表面？
// 3. **补充细节**：是否补充了精准的细化点/细节（而非堆砌）？
// 4. **强化逻辑**：因果/对比/递进是否更清晰？
// 5. **契合场景**：是否符合场景/子场景语境？
// 6. **升维成功**：是否从红蓝升维到紫绿？DMT是否同频共振？
// 7. **独到视角**：是否有让人"眼前一亮"的切入点？
// 8. **简单深刻**：是否找到了"绿色语言"的简单表达？

// **最终目标**：让第二次深评评分明显提升（+0.5至+1.5分），让用户感受到"这个工具怎么这么懂我！"、"原来还能这样思考！"

// ---

// 请直接输出改进后的完整回答。开始吧，相信你一定能做到！
// `;



// V2版本
// const iterationPrompt = `

// ## 从"对"到"妙"——击穿真实目标的迭代升华

// ### 一、理解深评指引（必读）

// 你刚刚收到的红蓝深评包含了关键改进指引，请仔细理解：

// **真实目标识别**：深评已帮你识别用户问题背后的真实目标
// - 三问定位：底线（最坏能接受什么）→愿景（最好能做到什么）→着力点（现在具体做什么）
// - **你的任务**：击穿这个真实目标，而不只是回答表面问题

// **认知层次分析**：深评已诊断当前回答在哪个/哪些层次
// - 红色业务层（仅回答问题）→蓝色技术层（工具性、方法性描述）→紫色场景层（提炼框架）→绿色自然层（简单深刻）
// - **你的任务**：按深评指引升维，通常是从前两层升到后两层

// **认知状态诊断**：深评已识别你的认知状态（新增重要维度）
// - **盲区**（不知己不知）：误用概念、盲目堆砌高级词汇 → 需要心力启动、暴露知识盲区、格子梯子清晰化
// - **填充**（知己不知）：处于D层事实积累阶段 → 需要积累学习D层事实和M层架构
// - **迁移**（不知己知）：有绿色直觉但未总结思维框架 → 需要跨领域应用、抽象泛式迁移
// - **增强**（知己知）：认知明确、需求清晰、能体现D+M层 → 需要提升T层统领、增加绿色语言
// - **你的任务**：按深评指出的状态转换路径执行（所有路径最终都指向"简单而深刻"）

// **结构诊断**：深评已分析你原回答的结构
// - D层具体内容（70%）是否充实？M层方法原则（20%）是否模糊？T层本质统领（10%）是否缺失？
// - **你的任务**：找到方法和本质（M层和T层），让原回答中具体内容D基于它们自然拔高

// **简单深刻目标**：深评可能给出了"绿色自然语言"提示
// - **你的任务**：找到统领性简单表达，用2-4个简单词汇击穿回答精髓（类似都江堰"鱼嘴·飞沙堰·宝瓶口"、真实目标"指南针→凸透镜→水电站→种子"的简单表达）

// ---

// ### 二、三问锁定改进方向

// **问1：底线是什么**（守住底线）
// - 原回答有没有跑题？有没有事实错误？
// - 处于"盲区"状态吗？如果是，必须先纠偏到"补充"状态
// - 改进底线：不跑题、不出错、逻辑清晰、概念准确

// **问2：愿景是什么**（追求卓越）
// - 这个回答做到极致会是什么样？
// - 目标认知状态是什么？（通常是"增强"并迈向"简单而深刻"）
// - 改进愿景：击穿"真实目标"、达到简单深刻

// **问3：着力点是什么**（即刻行动）
// - 深评中的"关键路径"和"具体建议"就是你的着力点
// - 深评中的"认知状态转换路径"就是你的执行方向
// - 改进着力点：按深评的3大模块执行

// ---

// ### 三、认知状态转换执行法（新增核心模块）

// **如果深评诊断为"盲区"状态**：
// 1. **暴露盲区**：识别哪些概念理解有误、哪些高级词汇用错了
// 2. **心力启动**：回到用户真实目标，理解为什么要解决这个问题
// 3. **格子梯子**：建立清晰的知识结构（格子）和递进路径（梯子）
// 4. **转换目标**：从"盲区"纠偏至"补充"状态，建立正确的D层事实基础

// **如果深评诊断为"补充"状态**：
// 1. **充实D层**：补充精准的事实、数据、案例（不堆砌）
// 2. **构建M层**：从多个D中提炼共性，形成方法论/原则
// 3. **转换目标**：从"补充"提升至"增强"状态，让D+M层清晰可见

// **如果深评诊断为"迁移"状态**：
// 1. **显性化直觉**：把隐藏的绿色直觉显性表达出来
// 2. **抽象泛式**：跨领域类比、提炼通用模式
// 3. **框架化**：把直觉整理成可操作的思维框架（紫色层）
// 4. **转换目标**：从"迁移"跃升至"增强"状态，建立明确的思维结构

// **如果深评诊断为"增强"状态**：
// 1. **提炼T层**：找到统领性原子点，用简单自然词汇表达
// 2. **强化绿色语言**：让复杂精髓用简单词汇涵盖
// 3. **转换目标**：从"增强"迈向"简单而深刻"，达到卓越层次

// **关键原则**：
// - 认知状态转换是有方向的：盲区→补充→增强→简单而深刻，或迁移→增强→简单而深刻
// - 不能跳级：如果在盲区，必须先到补充；如果在补充，必须先到增强
// - 转换是递进的：每个状态都有明确的执行路径，按路径执行

// ---

// ### 四、四色升维执行法

// **从业务/技术层（红蓝层）→场景层（紫色层）**：
// 1. 从多个具体点（D）中找**共性**
// 2. 抽象成**方法论/原则**（M层）
// 3. 形成**思维框架**（紫色场景语言）
// 4. 配合认知状态：通常对应"补充"→"增强"的转换
// 5. 例：从"注意力计算公式"（红）+"多头机制"（蓝）→提炼出"动态加权筛选原则"（紫）

// **如果已在紫色层→升维到绿色**：
// 1. 从方法论（M）中找**本质**
// 2. 提炼成**统领性表达**（T层）
// 3. 用**简单自然的词汇**表达（绿色自然语言）
// 4. 配合认知状态：通常对应"增强"→"简单而深刻"的转换
// 5. 例：从"动态加权筛选"（紫）→升华为"注意力=放大镜"（绿）

// **关键原则**：
// - 升维不是"压缩"，而是"提炼本质"
// - 升维不是"丢失细节"，而是"找到统领点"
// - 升维要配合认知状态转换，不能脱节
// - 升维后，原有的内容D会因为有了方法M和本质T的指引而自然拔高

// ---

// ### 五、DMT结构拔高执行法

// 认真理解M和T的定义，它们是拔高的关键

// **正确做法**：
// 1. **保留D的精华**：原回答中正确、具体的内容保留
// 2. **补充方法M层**：在具体内容基础上，补充方法论/原则（如果处于"补充"或"迁移"状态，这是关键）
// 3. **提炼本质T层**：找到一个统领性原子点（如果处于"增强"状态，这是关键）
// 4. **让D指向M，M指向T形成同频共振**：T本质统领→M方法承接→D具体落实（就像都江堰精妙的选址、岷江水的顶级势能为T，最终鱼嘴飞沙堰宝瓶口三级筛分是D，M应该是"深淘滩，低作堰"的维护原则作为中间层，承接T的顶级设计，指导D的具体筛分做法）
// 5. **配合认知状态**：盲区状态先正D，补充状态构建M，迁移/增强状态提炼T

// **错误做法**：
// - 删除D层具体内容
// - 完全重写D层具体内容
// - 大量改变原有结构
// - 不考虑当前认知状态，盲目拔高

// ---

// ### 六、寻找简单深刻表达

// 前面已经说过,此处不再赘述，强调几个关键原则：

// **关键**：
// - 简单：用日常词汇，易于理解（不要用某专业术语例如"编码器"之类）
// - 深刻：击中本质，涵盖精髓
// - 具体：不是空洞比喻，要能指导原有D层具体内容
// - 状态适配：如果还在"补充"状态，不要强求绿色语言；如果已在"增强"状态，必须追求绿色语言
// - 避免：玄学化、心灵鸡汤化、过度比喻而丢失具体性

// 除了前面说过的都江堰、真实目标例子，这样也是比较好的例子：Transformer就像从"望远镜"（RNN的逐步扫视）升级到"卫星俯瞰"（全局视野）

// ---

// ### 七、四层递进策略

// **基础层**（守住底线）：不跑题、逻辑清晰、修正错误、概念准确
// - 对应认知状态："盲区"→"补充"的纠偏

// **进阶层**（符合细节）：补充精准数据/案例、找统领点、击穿分点
// - 对应认知状态："补充"阶段的充实

// **高阶层**（契合场景）：符合场景语境、视角递进、语境转换
// - 对应认知状态："补充"→"增强"或"迁移"→"增强"的转换

// **卓越层**（视角独到）：独到视角、"妙"的思考、简单深刻、本质洞察
// - 对应认知状态："增强"→"简单而深刻"的升华

// **判断标准**：读完后让人觉得"原来还能这样理解！"、"这个角度真绝！"

// ---

// ### 八、深评三大模块执行

// **核心诊断**：这是改进的总方向，新回答必须完全解决指出的关键问题
// - **特别关注**：深评诊断的认知状态是什么？需要转换到什么状态？

// **思维突破**：
// - 关键路径：必须覆盖的1-2个核心维度
// - 具体建议：可直接执行的方法必须体现
// - **认知转换**：如果深评给出了认知状态转换路径（如"盲区→补充"或"补充→增强"），必须严格按路径执行
// - 隐藏维度：原回答遗漏的角度必须补充

// **激发要点**：
// - 策略执行：展现推理过程/多角度权衡/网状思维
// - 视角牵引：如明确"以XX视角重构"，必须严格执行
// - 字数控制：明确字数要求必须遵守，但优先考虑原问题要求

// ---

// ### 九、禁止错误

// **发虚（严重问题）**
// - 不要丢失原回答中的分点结构/案例/细节等具体信息
// - 不要变成"心灵鸡汤"式空洞回答
// - 不要在"补充"状态就强行绿色语言（会导致空洞）

// **跑题**：不要为了创新而偏离原问题核心，必须击穿"真实目标"

// **推翻重写**：切忌推翻重写、另起炉灶，应该在原有基础上拔高

// **认知跳级**（新增严重问题）：
// - 不要在"盲区"状态直接追求"简单而深刻"
// - 不要在"补充"状态跳过M层直接构建T层
// - 不要忽略深评给出的认知状态转换路径

// **冗长**：字数合理，不要堆砌内容，要提炼精髓，遵循"简单而深刻"原则

// **假创新**：不要只是换个说法没有新观点，必须有实质性的认知升维

// **用内部语言**：DMT、除乘加、四色语言、认知四象限是内部术语，用于深入思考，最终回答时切忌直接出现"DMT"/"除乘加"/"红蓝紫绿"/"盲区补充迁移增强"这类字眼，必须转换、自然融入

// ---

// ### 十、检查清单

// 1. **修正错误**：事实错误、逻辑错误、语言幻觉、概念误用是否已解决？
// 2. **认知状态**：深评诊断的认知状态是什么？是否按转换路径执行？（新增关键项）
// 3. **击穿目标**：是否击穿了"真实目标"而非停留表面？
// 4. **补充细节**：是否补充了精准的细化点/细节（而非堆砌）？
// 5. **强化逻辑**：因果/对比/递进是否更清晰？
// 6. **契合场景**：是否符合场景/子场景语境？
// 7. **升维成功**：是否从红蓝升维到紫绿？DMT是否同频共振？认知状态是否提升？（修订项）
// 8. **独到视角**：是否有让人"眼前一亮"的切入点？
// 9. **简单深刻**：是否找到了"绿色语言"的简单表达？（如果认知状态适合的话）

// **最终目标**：让第二次深评评分明显提升（+0.5至+1.5分），让用户感受到"这个工具怎么这么懂我！"、"原来还能这样思考！"

// **认知升华**：通过认知状态的明确转换，让回答不仅从"对"到"妙"，更从"不知"到"知"，从"知"到"简单而深刻"

// ---

// 请直接输出改进后的完整回答。开始吧，相信你一定能做到！
// `;



// V3版本
const iterationPrompt = `

## 从"对"到"妙"——击穿真实目标的迭代升华

### 一、核心指导思想：用微观讲宏观

**回答主体必须微观具体**：回答的主体应该是微观的、具体的、可逻辑化可判断的、专业的内容（红色业务事实、紫色方法框架），同时清晰体现宏观、方向、视角等的指向。不能以宏观理论为主，脱离实际具体情况；不能具体的、专业的内容太少，变成假大空。

**语言层次关系**：红色（业务事实）、紫色（方法框架）为主，蓝色（工具技术）为手段，绿色（简单深刻表达）进行补充体现学少。绿色语言从紫色出发，简化而非弱化红色语言，让人易懂且说明自己真懂。

**绿色语言使用规范**：
- 最多出现1处类比，篇幅不宜长，但要有击穿的文字张力
- 不能随意使用明显带有文学性的辞藻来回答有价值指向的专业问题
- 不是大量比喻、夸张，而要恰到好处、把控度数，真正简单而深刻地说明问题

---

### 二、理解深评指引（必读）

你刚刚收到的红蓝深评包含了关键改进指引，请仔细理解：

**真实目标识别**：深评已帮你识别用户问题背后的真实目标
- 三问定位：底线（最坏能接受什么）→愿景（最好能做到什么）→着力点（现在具体做什么）
- **你的任务**：击穿这个真实目标，而不只是回答表面问题

**认知层次分析**：深评已诊断当前回答在哪个/哪些层次
- 红色业务层（仅回答问题）→蓝色技术层（工具性、方法性描述）→紫色场景层（提炼框架）→绿色自然层（简单深刻）
- **你的任务**：按深评指引升维，通常是从前两层升到后两层

**认知状态诊断**：深评已识别你的认知状态
- **盲区**（不知己不知）：误用概念、盲目堆砌高级词汇 → 需要心力启动、暴露知识盲区、格子梯子清晰化
- **填充**（知己不知）：处于D层事实积累阶段 → 需要积累学习D层事实和M层架构
- **迁移**（不知己知）：有绿色直觉但未总结思维框架 → 需要跨领域应用、抽象泛式迁移
- **增强**（知己知）：认知明确、需求清晰、能体现D+M层 → 需要提升T层统领、增加绿色语言（全文最多1处类比）
- **你的任务**：按深评指出的状态转换路径执行（所有路径最终都指向"简单而深刻"）

**结构诊断**：深评已分析你原回答的结构
- D层具体内容（70%）是否充实？M层方法原则（20%）是否模糊？T层本质统领（10%）是否缺失？
- **你的任务**：找到方法和本质（M层和T层），让原回答中具体内容D基于它们自然拔高

---

### 三、三问锁定改进方向

**问1：底线是什么**（守住底线）
- 原回答有没有跑题？有没有事实错误？处于"盲区"状态吗？如果是，必须先纠偏到"补充"状态
- 改进底线：不跑题、不出错、逻辑清晰、概念准确

**问2：愿景是什么**（追求卓越）
- 这个回答做到极致会是什么样？目标认知状态是什么？
- 改进愿景：击穿"真实目标"、达到简单深刻

**问3：着力点是什么**（即刻行动）
- 深评中的"关键路径"和"具体建议"就是你的着力点，深评中的"认知状态转换路径"就是你的执行方向
- 改进着力点：按深评的3大模块执行

---

### 四、认知状态转换执行

**如果深评诊断为"盲区"状态**：
1. **暴露盲区**：识别哪些概念理解有误、哪些高级词汇用错了
2. **心力启动**：回到用户真实目标，理解为什么要解决这个问题
3. **格子梯子**：建立清晰的知识结构（格子）和递进路径（梯子）
4. **转换目标**：从"盲区"纠偏至"补充"状态，建立正确的D层事实基础

**如果深评诊断为"补充"状态**：
1. **充实D层**：补充精准的事实、数据、案例（不堆砌）
2. **构建M层**：从多个D中提炼共性，形成方法论/原则
3. **转换目标**：从"补充"提升至"增强"状态，让D+M层清晰可见

**如果深评诊断为"迁移"状态**：
1. **显性化直觉**：把隐藏的绿色直觉显性表达出来
2. **抽象泛式**：跨领域类比、提炼通用模式
3. **框架化**：把直觉整理成可操作的思维框架（紫色层）
4. **转换目标**：从"迁移"跃升至"增强"状态，建立明确的思维结构

**如果深评诊断为"增强"状态**：
1. **提炼T层**：找到统领性原子点，用简单自然词汇表达（全文最多1处类比，篇幅短但有张力）
2. **强化绿色语言**：让复杂精髓用简单词汇涵盖，但不能随意使用文学性辞藻
3. **转换目标**：从"增强"迈向"简单而深刻"，达到卓越层次

**关键原则**：
- 认知状态转换是有方向的：盲区→补充→增强→简单而深刻，或迁移→增强→简单而深刻
- 不能跳级：如果在盲区，必须先到补充；如果在补充，必须先到增强
- 转换是递进的：每个状态都有明确的执行路径，按路径执行

---

### 五、四色升维执行

**从业务/技术层（红蓝层）→场景层（紫色层）**：
1. 从多个具体点（D）中找**共性**
2. 抽象成**方法论/原则**（M层）
3. 形成**思维框架**（紫色场景语言）
4. 配合认知状态：通常对应"补充"→"增强"的转换
5. 例：从"注意力计算公式"（红）+"多头机制"（蓝）→提炼出"动态加权筛选原则"（紫）

**如果已在紫色层→升维到绿色**：
1. 从方法论（M）中找**本质**
2. 提炼成**统领性表达**（T层）
3. 用**简单自然的词汇**表达（绿色自然语言）
4. 配合认知状态：通常对应"增强"→"简单而深刻"的转换
5. 例：从"动态加权筛选"（紫）→升华为"注意力=放大镜"（绿，全文仅此1处类比）

**关键原则**：
- 升维不是"压缩"，而是"提炼本质"
- 升维不是"丢失细节"，而是"找到统领点"
- 升维要配合认知状态转换，不能脱节
- 升维后，原有的内容D会因为有了方法M和本质T的指引而自然拔高

---

### 六、DMT结构化执行

**正确做法**：
1. **保留D的精华**：原回答中正确、具体的内容保留（微观具体的专业内容）
2. **补充方法M层**：在具体内容基础上，补充方法论/原则（如果处于"补充"或"迁移"状态，这是关键）
3. **提炼本质T层**：找到一个统领性原子点
4. **让D指向M，M指向T形成同频共振**：T本质统领→M方法承接→D具体落实（都江堰例子：精妙的选址、岷江水的顶级势能为T，最终鱼嘴飞沙堰宝瓶口三级筛分、专业的二八分水工程等等是D，M应该是"深淘滩，低作堰"的维护原则作为中间层，承接T的顶级设计，指导D的具体筛分做法）
5. **配合认知状态**：盲区状态先正D，补充状态构建M，迁移/增强状态提炼T

**错误做法**：
- 删除D层具体内容
- 完全重写D层具体内容
- 大量改变原有结构
- 不考虑当前认知状态，盲目拔高
- 以宏观理论、大量类比等强文学性表述为主，脱离实际具体情况（造成假大空）

---

### 七、寻找简单深刻表达

**关键原则**：
- 简单：用日常词汇，易于理解（不要用专业术语例如"编码器"之类）
- 深刻：击中本质，涵盖精髓
- 具体：不是空洞比喻，要能指导原有D层具体内容，用微观讲宏观
- 避免：玄学化、心灵鸡汤化、过度比喻而丢失具体性、随意使用文学性辞藻

---

### 八、深评三大模块执行

**核心诊断**：这是改进的总方向，新回答必须完全解决指出的关键问题，特别关注深评诊断的认知状态是什么？需要转换到什么状态？

**思维突破**：
- 关键路径：必须覆盖的1-2个核心维度
- 具体建议：可直接执行的方法必须体现
- 隐藏维度：原回答遗漏的角度必须补充

**激发要点**：
- 策略执行：展现推理过程/多角度权衡/网状思维
- 视角牵引：如明确"以XX视角重构"，必须严格执行
- 字数控制：明确字数要求必须遵守，但优先考虑原问题要求

---

### 九、禁止错误

**发虚（严重问题）**：不要丢失原回答中的分点结构/案例/细节等具体信息，不要变成"心灵鸡汤"式空洞回答，绿色语言不是指大量文学性类比，是“专业的”简单而深刻表达，同时禁止自创词汇如“认知编码桥”等垃圾内容，必须是熟知词！

**跑题**：不要为了创新而偏离原问题核心，必须击穿"真实目标"

**推翻重写**：切忌推翻重写、另起炉灶，应该在原有基础上拔高

**认知跳级**：不要在"盲区"状态直接追求"简单而深刻"，不要在"补充"状态跳过M层直接构建T层

**冗长**：字数合理，不要堆砌内容，要提炼精髓，遵循"简单而深刻"原则

**假创新**：不要只是换个说法没有新观点，必须有实质性的认知升维

**用内部语言**：DMT、除乘加、四色语言、认知四象限是内部术语，用于深入思考，最终回答时切忌直接出现"DMT"/"除乘加"/"红蓝紫绿"/"盲区补充迁移增强"这类字眼，必须转换、自然融入

---

**最终直接目标**：让第二次深评评分明显提升（+0.5至+1.5分），让用户感受到"这个工具很懂我意图！"、"原来还能这样思考！"

请直接输出改进后的完整回答！
`;

export default {
  components: {
    HeadPortrait,
    FileCard,
    AnswerParser,
    ElNotification, 
    ElMessage, 
    ElProgress
  },
  props: {        // 定义从父组件传递过来的变量
    modelInfoList: {
      type: Object,
      default() {
        return {};
      },
    },
    chatModelInfo: Object,
    params: Object,
    isQuestionWindow: Boolean,
    isPlus: Boolean,
    formLui2: Object,
    LUI2_result_index: String,
    isHistoryUsed: Boolean,
    isSummaryUsed: Boolean,
    isMemorySystemUsed: {
      type: Boolean,
      default: false,
    },
    keyTopics: Array,
    rounds: Number,
    portraitStates: Object,
    threeModelQAState: Number,
    ModelContentMerge: String,
    choosedCardIdList: Array,
    sceneName: String,
    subSceneName: String,
    openCardId: Number,
    chosenContent: String,
    fileNameList: Array,
    coreKeyword: String,  // 🔥 核心关键词（从Tab增强中提取）
    crossNotebookContext: {
      type: Boolean,
      default: false,
    },
  },
  watch: {
    LUI2_result_index(newVal, oldVal) {
      if(this.waitForChange === true)
        this.chatList[this.LUI2_plus_index].msg = newVal
    },
    chatModelInfo() {
      this.getModelChatMsg();
    },
    isQuestionWindow() {
      this.retQuestions = this.isQuestionWindow;
    },
    threeModelQAState(newVal, oldVal) {
      if(newVal === 2) {
        this.mergeModelAnswers()
      }
    },
    choosedCardIdList: {
      handler(newVal, oldVal) {
        if(newVal.length === 0) return;
        
        const currentTime = Date.now();
        this.lastChangeTime = currentTime;

        setTimeout(() => {
          if(currentTime === this.lastChangeTime) {
            console.log("choosedCardIdList发生变化后5s内无变化");
            this.$emit("getCardRelQue")
          } else {
            console.log("choosedCardIdList发生变化后5s内再次变化");
          }
        }, 5000);
      },
      deep: true
    },
  },
  data() {
    return {
      // 🔥 新增：System选择（0=System2慢思考，1=System1快思考）
      systemChoice: 0,

      // doubleClick: false,
      // selectedIndex: 0, // 存储双击的开始位置
      // speech: null, // 用于存储语音合成实例
      // isSpeaking: false,

      LUI2_plus_index: 0, // 待替换加强的回复index
      waitForChange: false,
      LUI2_plus: false,
      retQuestions: false,
      rotScoreAlgorithmic: 0,  // 腐烂度确定性算法评分
      ragSampleText: "",  // RAG样本文档内容
      historySampleText: "",  // 历史对话样本内容
      docConfidenceScore: 0,  // 文档置信度评分
      sceneSummaryShort: "",  // 场景摘要（前50字）
      chatList: [],
      inputMsg: "",
      srcImgList: [],
      modelList: [],
      summary: false,
      questionContents: [
      ],
      Question: "",
      Answer: "",
      score: {
        human: '',
        GPT4: ''
      },
      shouldScroll: true,
      chatEnd: false,
      // 最近一轮的当前问题
      nowTurnQuestion: "",
      // 记录cardChooseList最近一次变化时间的变量
      lastChangeTime: 0,

      // 鼠标悬停控制自动滚动
      isMouseHovering: false, // 鼠标是否在窗口内
      resumeScrollTimer: null, // 恢复滚动的延时器

      // 控制悬浮pin按钮显示
      showPinButton: -1,

      // progressPercentage: 0,
      // progressCurrentPage: 0,
      // progressTotalPages: 0,
      // isUploading: false, // 用一个状态来控制显示与否
      // 用于存储所有文件的上传状态
      uploadStates: new Map(),
      // 用于存储所有文件上传的进度通知
      progressDialogs: new Map(),
      notificationOffset: 20, // 基础偏移量
      activeNotifications: 0, // 当前活跃的通知数量
      activeUploads: 0, // 当前并发上传中的文件数
      maxConcurrentUploads: 5,
      uploadFileQueue: [], // 多选上传排队

      // 中断相关状态
      isStreaming: false, // 是否正在流式输出
      isInterrupted: false, // 是否已中断
      currentSessionId: null, // 当前会话ID

      // 深评中断控制器
      evalAbortController: null, // 第一次深评的中断控制器
      secondEvalAbortController: null, // 第二次深评的中断控制器
    };
  },
  mounted() {
    // 🔥 新增：读取用户的system选择
    const savedChoice = localStorage.getItem('systemChoice');
    this.systemChoice = savedChoice !== null ? parseInt(savedChoice) : 0;
    console.log('[ChatWindow] System Choice:', this.systemChoice === 0 ? 'System2(慢思考)' : 'System1(快思考)');

    this.getModelChatMsg();
    // 只保留数组的第一个元素，移除其他所有元素
    this.chatList.splice(1, this.chatList.length - 1);
  },
  methods: {
    // appendCrossNotebookParams(paramFormData) {
    //   paramFormData.append('crossNotebookContext', this.crossNotebookContext ? 'true' : 'false');
    //   const pinned = getPinnedCrossNotebooksForApi(localStorage.getItem('userId'));
    //   if (pinned) {
    //     paramFormData.append('pinnedCrossNotebooks', pinned);
    //   }
    // },
    appendCrossNotebookParams(paramFormData) {
      paramFormData.append('crossNotebookContext', this.crossNotebookContext ? 'true' : 'false');
      // 钉子勾选仅用于主页任务簇整理，不再影响跨本文档素材选取
    },
    // 检查用户是否有权限查看置信度和腐烂度
    canViewConfidenceAndRot() {
      const realName = localStorage.getItem('realName');
      return realName === 'uzi';
      // return realName === 'testlyf' || realName === 'uzi';
    },
    
    // 计算综合评分（红蓝评分、置信度、腐烂度的加权和）
    calculateComprehensiveScore(redBlueScore, confidenceScore, rotScore) {
      // 加权公式：红蓝评分*0.7 + 置信度*0.2 + (5-腐烂度)*0.1
      // 腐烂度需要反转（5-腐烂度），因为腐烂度越低越好
      const comprehensiveScore = redBlueScore * 0.5 + confidenceScore * 0.25 + (5 - rotScore) * 0.25;
      return comprehensiveScore.toFixed(1);
    },
    
    // 从评估结果中提取评分（用于both eval and second-eval）
    extractScoresFromEval(evalText) {
      // 新格式：理由在前，【打分结果】或评分在后
      // 匹配【打分结果】X.X_颜色_置信度X.X_腐烂度X.X
      const newMatch = evalText.match(/【打分结果】(\d+\.?\d*)_([^_\s]+)_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)/);
      if (newMatch) {
        return {
          redBlueScore: parseFloat(newMatch[1]),
          color: newMatch[2],
          confidenceScore: parseFloat(newMatch[3]),
          rotScore: parseFloat(newMatch[4])
        };
      }
      
      // 匹配理由后的评分：X.X_颜色_置信度X.X_腐烂度X.X（任意位置）
      // 使用更精确的正则：确保颜色部分不包含下划线和空格
      const reasonFirstMatch = evalText.match(/(\d+\.?\d*)_([^_\s]+)_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)/);
      if (reasonFirstMatch) {
        return {
          redBlueScore: parseFloat(reasonFirstMatch[1]),
          color: reasonFirstMatch[2],
          confidenceScore: parseFloat(reasonFirstMatch[3]),
          rotScore: parseFloat(reasonFirstMatch[4])
        };
      }
      
      // 旧格式：X.X_颜色_置信度X.X_腐烂度X.X_内容（在开头）
      const oldMatch = evalText.match(/^(\d+\.?\d*)_([^_\s]+)_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)_/);
      if (oldMatch) {
        return {
          redBlueScore: parseFloat(oldMatch[1]),
          color: oldMatch[2],
          confidenceScore: parseFloat(oldMatch[3]),
          rotScore: parseFloat(oldMatch[4])
        };
      }

      // 简化格式：X.X_颜色_X.X_X.X（没有"置信度"和"腐烂度"标签）
      // 注意：这个格式可能与其他内容混淆，所以放在后面尝试
      const simplifiedMatch = evalText.match(/(\d+\.?\d*)_([红蓝紫绿])_(\d+\.?\d*)_(\d+\.?\d*)/);
      if (simplifiedMatch) {
        console.log(`[extractScoresFromEval] 使用简化格式解析: ${simplifiedMatch[0]}`);
        console.log(`[extractScoresFromEval] 提取的评分 - 红蓝: ${simplifiedMatch[1]}, 颜色: ${simplifiedMatch[2]}, 置信度: ${simplifiedMatch[3]}, 腐烂度: ${simplifiedMatch[4]}`);
        return {
          redBlueScore: parseFloat(simplifiedMatch[1]),
          color: simplifiedMatch[2],
          confidenceScore: parseFloat(simplifiedMatch[3]),
          rotScore: parseFloat(simplifiedMatch[4])
        };
      }

      // 如果所有格式都匹配失败，打印调试信息
      console.log(`[extractScoresFromEval] 未能匹配任何格式，evalText前200字: ${evalText.substring(0, 200)}`);
      console.log(`[extractScoresFromEval] evalText后200字: ${evalText.substring(Math.max(0, evalText.length - 200))}`);
      console.log(`[extractScoresFromEval] evalText总长度: ${evalText.length}`);
      
      // 更旧格式（仅红蓝评分）：X.X_颜色_内容
      const olderMatch = evalText.match(/^(\d+\.?\d*)_([^_\s]+)_/);
      if (olderMatch) {
        return {
          redBlueScore: parseFloat(olderMatch[1]),
          color: olderMatch[2],
          confidenceScore: null,
          rotScore: null
        };
      }
      
      return null;
    },
    
    // 处理评估文本，移除或替换置信度腐烂度信息
    processEvalText(evalText, comprehensiveScore = null) {
      const canView = this.canViewConfidenceAndRot();

      console.log(`[processEvalText] canView=${canView}, comprehensiveScore=${comprehensiveScore}`);
      console.log(`[processEvalText] 原始文本前50字: ${evalText.substring(0, 50)}`);
      
      // 步骤0：处理简化格式 X.X_颜色_X.X_X.X → X.X_颜色_置信度X.X_腐烂度X.X
      let processed = evalText;
      // 匹配简化格式：X.X_颜色_X.X_X.X（颜色后直接跟数字，且后面不是"置信度"）
      // 负向前瞻：确保匹配的不是已经有"置信度"标签的
      processed = processed.replace(/(\d+\.?\d*)_([红蓝紫绿])_(\d+\.?\d*)_(\d+\.?\d*)(?![\u4e00-\u9fa5])/g, (match, score1, color, score2, score3, offset, string) => {
        // 检查前面是否已经有"置信度"或"腐烂度"标签
        const checkBefore = string.substring(Math.max(0, offset - 20), offset);
        const checkAfter = string.substring(offset, Math.min(string.length, offset + match.length + 10));
        
        // 如果前后已经有标签，说明是完整格式，不替换
        if (checkBefore.includes('置信度') || checkAfter.includes('置信度')) {
          return match;
        }
        
        // 补充标签
        console.log(`[processEvalText] 检测到简化格式: ${match}，补充为完整格式`);
        return `${score1}_${color}_置信度${score2}_腐烂度${score3}`;
      });
      
      // 步骤1：重新排列格式（理由在前的格式 → 评分在前的格式）
      
      // 匹配【打分结果】X.X_颜色_置信度X.X_腐烂度X.X
      const scoreWithLabelMatch = processed.match(/【打分结果】(\d+\.?\d*_[^_\s]+_置信度\d+\.?\d*_腐烂度\d+\.?\d*)/);
      if (scoreWithLabelMatch) {
        const scoreStr = scoreWithLabelMatch[1];
        // 移除【打分结果】标签和评分
        processed = processed.replace(/【打分结果】\d+\.?\d*_[^_\s]+_置信度\d+\.?\d*_腐烂度\d+\.?\d*\s*/g, '');
        // 将评分移到开头
        processed = `${scoreStr}_${processed}`.trim();
        console.log(`[processEvalText] 重排后（有标签）前50字: ${processed.substring(0, 50)}`);
      } else {
        // 匹配普通评分：X.X_颜色_置信度X.X_腐烂度X.X（不在开头）
        // 使用更精确的正则：确保颜色部分不包含下划线和空格
        const scoreMatch = processed.match(/(\d+\.?\d*_[^_\s]+_置信度\d+\.?\d*_腐烂度\d+\.?\d*)/);
        if (scoreMatch && !processed.startsWith(scoreMatch[1])) {
          const scoreStr = scoreMatch[1];
          const scorePos = processed.indexOf(scoreStr);
          // 移除评分（保留评分前的内容）
          const beforeScore = processed.substring(0, scorePos);
          const afterScore = processed.substring(scorePos + scoreStr.length);
          // 将评分移到开头
          processed = `${scoreStr}_${beforeScore}${afterScore}`.trim();
          console.log(`[processEvalText] 重排后（无标签）前50字: ${processed.substring(0, 50)}`);
        }
      }
      
      // 步骤2：根据权限处理显示
      if (canView) {
        // 有权限的用户：如果有综合评分，也要用综合评分替换开头的原始分数
        if (comprehensiveScore !== null) {
          // 颜色纠正：如果综合评分>1.0，强制使用紫色（必须在替换分数前执行）
          if (comprehensiveScore > 1.0) {
            processed = processed.replace(/^(\d+\.?\d*)_([红蓝])_/, `$1_紫_`);
            console.log(`[processEvalText] 颜色纠正：综合评分${comprehensiveScore}>1.0，强制使用紫色`);
          }
          
          // 替换开头的红蓝得分为综合得分
          processed = processed.replace(/^(\d+\.?\d*)_/, `${comprehensiveScore}_`);
          console.log(`[processEvalText] 有权限用户替换综合得分后前50字: ${processed.substring(0, 50)}`);
        }
        return processed;
      } else {
        // 无权限的用户：用综合评分替换原始评分，移除置信度和腐烂度标识
        if (comprehensiveScore !== null) {
          // 移除置信度和腐烂度标识
          processed = processed.replace(/_置信度\d+\.?\d*_腐烂度\d+\.?\d*_/, '_');
          console.log(`[processEvalText] 移除置信度腐烂度后前50字: ${processed.substring(0, 50)}`);
          
          // 颜色纠正：如果综合评分>1.0，强制使用紫色（必须在替换分数前执行）
          if (comprehensiveScore > 1.0) {
            processed = processed.replace(/^(\d+\.?\d*)_([红蓝])_/, `$1_紫_`);
            console.log(`[processEvalText] 颜色纠正：综合评分${comprehensiveScore}>1.0，强制使用紫色`);
          }
          
          // 替换开头的红蓝得分为综合得分
          processed = processed.replace(/^(\d+\.?\d*)_/, `${comprehensiveScore}_`);
          console.log(`[processEvalText] 替换综合得分后前50字: ${processed.substring(0, 50)}`);

          return processed;
        } else {
          // 没有综合评分时，移除置信度和腐烂度
          processed = processed.replace(/_置信度\d+\.?\d*_腐烂度\d+\.?\d*_/, '_');
          return processed;
        }
      }
    },

    // 获取不包含用时统计的消息内容
    // 注意：getMessageWithoutTiming和getTimingPart方法已移除
    // 现在使用单独的timingInfo字段来存储用时统计，避免污染msg内容

    // getMessageWithoutTiming(msg) {
    //   // 使用更严谨的检测：同时检查HTML div标签和用时统计文本
    //   const timingPattern = /<div style="color: #999; font-size: 12px; margin-top: 10px; border-top: 1px dashed #ddd; padding-top: 5px;">\s*⏱️ 用时统计：/;
    //   const match = msg.match(timingPattern);
    //   if (match) {
    //     return msg.substring(0, match.index).trim();
    //   }
    //   return msg;
    // },
    
    // // 获取用时统计部分的HTML内容
    // getTimingPart(msg) {
    //   // 使用更严谨的检测：同时检查HTML div标签和用时统计文本
    //   const timingPattern = /<div style="color: #999; font-size: 12px; margin-top: 10px; border-top: 1px dashed #ddd; padding-top: 5px;">\s*⏱️ 用时统计：/;
    //   const match = msg.match(timingPattern);
    //   if (match) {
    //     return msg.substring(match.index);
    //   }
    //   return '';
    // },




    // startFromIndex(index, answer) {
    //   this.selectedIndex = index;
    //   this.doubleClick = true;
    //   this.speakText(answer);
    // },
    // speakText(answer) {
    //   if (this.isSpeaking) {
    //     window.speechSynthesis.cancel();
    //     this.isSpeaking = false;
    //     this.speech = null;
    //   } else {
    //     this.stopSpeech()
    //     // 截取从用户双击位置开始的内容
    //     const content = answer.slice(this.selectedIndex);
    //     const utterance = new SpeechSynthesisUtterance(content);
    //     this.speech = window.speechSynthesis.speak(utterance);
    //     this.isSpeaking = true;
    //   }
    // },
    // stopSpeech() {
    //   if (this.isSpeaking) {
    //     window.speechSynthesis.cancel();
    //     this.isSpeaking = false;
    //     this.speech = null;
    //   }
    // },
    // doubleClickOver() {
    //   this.doubleClick = false
    // },
    handleCopy(message) {
      // 使用Clipboard API复制文本，包括空行
      navigator.clipboard.writeText(message).then(() => {
        this.$message.success('内容已复制到剪贴板，包含空行');
      }).catch((err) => {
        this.$message.error("复制失败！");
      });

      // 阻止事件继续传播
      event.stopPropagation();
    },

    handleRetry(item, index) {
      // 重做此回答
      console.log('重做回答:', item, index);
      
      // 阻止事件继续传播
      event.stopPropagation();
      
      // 检查是否是模型回答（不是用户消息）
      if (item.uid === '1001') {
        this.$message.warning('只能重做模型的回答，不能重做用户消息');
        return;
      }

      // 检查当前窗口是否还在流式输出中
      if (!this.chatEnd) {
        this.$message.warning('请等待当前回答完成后再重做');
        return;
      }
      
      // 找到对应的用户问题
      let userQuestion = '';
      for (let i = index - 1; i >= 0; i--) {
        if (this.chatList[i].uid === '1001') {
          userQuestion = this.chatList[i].msg;
          break;
        }
      }
      
      if (!userQuestion) {
        this.$message.error('未找到对应的用户问题');
        return;
      }
      
      // 判断重做类型：
      // 1. 检查当前回答是否包含迭代改进标记（第二次回答）
      const hasIterationMarker = item.msg.includes("\n\n---\n### 迭代改进后的回答\n");

      // 2. 检查是否有第一次深评标记
      const hasFirstEval = item.msg.includes("\n\n```eval\n");

      // 3. 检查是否有第二次深评标记
      const hasSecondEval = item.msg.includes("\n\n```second-eval\n");

      // 4. 检查是否有中断提示
      const wasInterrupted = item.msg.includes('⚠️') && (
        item.msg.includes('已被用户中断') ||
        item.msg.includes('已中断')
      );

      // 判断重做类型
      let retryType = '';
      let retryMessage = '';

      if (!wasInterrupted) {
        // 情况1：正常完成但内容不满意，重做第二次迭代
        if (hasFirstEval && hasIterationMarker && hasSecondEval) {
          retryType = 'second_iteration_only';
          retryMessage = '正在重新生成第二次迭代回答...';
        } else {
          // 虽然没有中断提示，但流程不完整，重做整个流程
          retryType = 'full_process';
          retryMessage = '检测到流程不完整，正在重新生成完整回答...';
        }
      } else {
        // 情况2：中断后重做
        if (!hasFirstEval) {
          // 第一次回答都没完成，重做整个流程
          retryType = 'full_process';
          retryMessage = '检测到第一次回答未完成，正在重新生成完整回答...';
        } else if (!hasIterationMarker || !hasSecondEval) {
          // 第一次回答完成了但第二次未完成，只重做第二次迭代
          retryType = 'second_iteration_only';
          retryMessage = '检测到第二次回答未完成，正在重新生成第二次迭代回答...';
        } else {
          // 两次都完成了，重做第二次迭代
          retryType = 'second_iteration_only';
          retryMessage = '正在重新生成第二次迭代回答...';
        }
      }

      console.log(`[重做类型判断] retryType=${retryType}, hasFirstEval=${hasFirstEval}, hasIterationMarker=${hasIterationMarker}, hasSecondEval=${hasSecondEval}, wasInterrupted=${wasInterrupted}`);

      // 🔥 新增：System1模式下不支持第二次迭代重做
      if (this.systemChoice === 1 && retryType === 'second_iteration_only') {
        this.$message.warning('System1快思考模式下无第二次迭代，将重做完整回答');
        retryType = 'full_process';
        retryMessage = '正在重新生成回答...';
      }
      
      // 显示重做提示
      this.$message.info(retryMessage);
      
      // 调用重做API
      this.retryModelResponse(userQuestion, item, index, retryType);
    },

    async retryModelResponse(userQuestion, originalItem, index, retryType) {
      try {
        // 提取第一次回答和第一次深评（用于第二次迭代重做）
        let firstAnswer = '';
        let firstEvalResult = '';

        if (retryType === 'second_iteration_only') {
          // 提取第一次回答（eval之前的部分）
          const evalMarker = "\n\n```eval\n";
          const evalIndex = this.chatList[index].msg.indexOf(evalMarker);

          if (evalIndex !== -1) {
            firstAnswer = this.chatList[index].msg.substring(0, evalIndex);

            // 提取第一次深评内容（eval和迭代回答之间）
            const iterationMarker = "\n\n---\n### 迭代改进后的回答\n";
            const iterationIndex = this.chatList[index].msg.indexOf(iterationMarker);

            if (iterationIndex !== -1) {
              const evalStart = evalIndex + evalMarker.length;
              const evalEnd = this.chatList[index].msg.indexOf("\n```", evalStart);

              if (evalEnd !== -1) {
                firstEvalResult = this.chatList[index].msg.substring(evalStart, evalEnd);
                console.log(`[重做] 提取到第一次深评，长度: ${firstEvalResult.length}`);
              }
            }
          }

          // 清理第一次回答中的代码块标记
          firstAnswer = this.cleanCodeBlocks(firstAnswer);
        }

        // 根据重做类型清理内容
        if (retryType === 'second_iteration_only') {
          // 只重做第二次迭代：保留第一次回答和第一次深评
          // 移除第二次迭代相关的所有内容
          const iterationMarker = "\n\n---\n### 迭代改进后的回答\n";
          const iterationIndex = this.chatList[index].msg.indexOf(iterationMarker);

          if (iterationIndex !== -1) {
            // 保留迭代标记之前的所有内容（第一次回答+第一次深评）
            this.chatList[index].msg = this.chatList[index].msg.substring(0, iterationIndex);
            console.log('[重做] 已移除第二次迭代回答及第二次深评，保留第一次回答和第一次深评');
          } else {
            console.warn('[重做] 未找到迭代标记，可能流程异常');
          }

          // 清理第二次深评相关的评分
          this.chatList[index].secondEvalComprehensiveScore = null;

          // 清理timing信息
          this.chatList[index].timingInfo = null;
        } else {
          // 重做整个流程：清空回答内容
          this.chatList[index].msg = '';
          this.chatList[index].timingInfo = null;
          this.chatList[index].evalComprehensiveScore = null;
          this.chatList[index].secondEvalComprehensiveScore = null;
          this.chatList[index].confidenceScore = null;
          this.chatList[index].rotScore = null;
          console.log('[重做] 已清空所有内容，准备重做整个流程');
        }
        
        // 准备重做请求数据
        const formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('model_id', this.chatModelInfo.id);

        // 构建消息内容：根据重做类型决定
        let message = '';
        if (retryType === 'second_iteration_only') {
          // 重做第二次迭代：构建完整的迭代提示（与正常流程一致）
          // 包括：原问题 + 第一次回答 + 第一次深评 + RAG样本 + 迭代提示词

          const cleanedQuestion = this.cleanCodeBlocks(userQuestion);
          message = `原问题：\n${cleanedQuestion}\n\n第一次原回答：\n${firstAnswer}\n\n红蓝深评：\n${firstEvalResult}`;

          // 如果有RAG文档，添加到迭代消息中（与正常流程一致）
          if (this.ragSampleText && this.ragSampleText.length > 0) {
            message += `\n\n【参考文档摘录】\n${this.ragSampleText}`;
            console.log(`[重做-第二次迭代] 包含RAG样本文档，字数: ${this.ragSampleText.length}`);
          }

          message += iterationPrompt;

          console.log(`[重做-第二次迭代] 消息内容长度: ${message.length}`);
        } else {
          // 重做整个流程：只传递原始问题
          message = userQuestion;
          console.log(`[重做-整个流程] 消息内容长度: ${message.length}`);
        }

        formData.append('message', message);
        formData.append('filenamelist', this.fileNameList || []);
        formData.append('summary', this.summary);
        formData.append('leftSelectList', []);
        formData.append('rightSelectList', []);
        formData.append('modelStates', JSON.stringify(this.portraitStates));
        formData.append('isHistoryUsed', this.isHistoryUsed);
        formData.append('isSummaryUsed', this.isSummaryUsed);
        // formData.append('isMemorySystemUsed', this.isMemorySystemUsed !== false);
        formData.append('isMemorySystemUsed', !!this.isMemorySystemUsed);
        formData.append('rounds', this.rounds);
        formData.append('realName', localStorage.getItem('realName'));
        formData.append('userbookName', localStorage.getItem('userId'));
        formData.append('sceneName', localStorage.getItem('sceneName'));
        formData.append('choosedCardIdList', this.choosedCardIdList || []);

        // 根据 windowId 确定调用后端的哪个接口
        formData.append('windowId', this.$attrs.windowId);
        
        let seed = localStorage.getItem('seed');
        let seednumber = 0;
        if (seed === 'topic') { seednumber = 1; }
        else if (seed === 'question') { seednumber = 2; }
        else { seednumber = 0; }
        formData.append('seed', seednumber);
        
        // 准备超参数（复用正常回答的逻辑）
        let paramFormData = new FormData();
        const runtime_params = modelManager.getHyperParamsDictionary();
        let paramString = JSON.stringify(runtime_params);
        paramFormData.append('params', paramString);
        paramFormData.append('modelID', this.chatModelInfo.id);
        paramFormData.append('username', localStorage.getItem('userId'));
        paramFormData.append('windowId', this.$attrs.windowId);
        paramFormData.append('message', userQuestion);
        paramFormData.append('filenamelist', this.fileNameList || []);
        // paramFormData.append('rightSelectList', []);
        paramFormData.append('rightSelectList', Array(this.fileNameList?.length || 0).fill('3'));
        paramFormData.append('isHistoryUsed', this.isHistoryUsed);
        // paramFormData.append('isMemorySystemUsed', this.isMemorySystemUsed !== false);
        paramFormData.append('isMemorySystemUsed', !!this.isMemorySystemUsed);
        paramFormData.append('rounds', this.rounds);
        let originRealName = localStorage.getItem('originRealName') + localStorage.getItem('userId').replace(localStorage.getItem('realName'), '');
        paramFormData.append('originRealName', originRealName);
        paramFormData.append('choosedCardIdList', this.choosedCardIdList || []);
        // 🔥 如果使用了tab增强后的问题，传递核心关键词（通过props传递）
        if (this.coreKeyword) {
          paramFormData.append('coreKeyword', this.coreKeyword);
        }
        this.appendCrossNotebookParams(paramFormData);
        paramFormData.append('mode', retryType === 'second_iteration_only' ? 'iteration' : 'normal');
        
        // 复用正常回答的API
        await chat_sendParams(paramFormData);
        const response = await chat_send(this.chatModelInfo.name, formData, this.$attrs.windowId);
        
        // 处理流式响应
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');

        let newAnswer = '';
        let ragSearchTime = 0;
        let firstTokenTime = null;
        const retryStartTime = Date.now();

        // 根据重做类型决定不同的处理逻辑
        if (retryType === 'second_iteration_only') {
          // 只重做第二次迭代：直接流式输出到迭代标记后
          this.chatList[index].msg += "\n\n---\n### 迭代改进后的回答\n";

          // 开始流式输出
          this.startStreaming();

          while (true) {
            const { done, value } = await reader.read();

            // 检查是否已被中断
            if (this.isInterrupted) {
              console.log('[中断检测] 重做-第二次迭代已中断');
              this.$message.info('已中断，停止重做');
              this.chatList[index].msg += '\n\n---\n\n⚠️ 重做已被用户中断';
              break;
            }

            if (done) break;

            const chunk = decoder.decode(value);
            const jsonObjects = chunk.match(/{[\s\S]*?}(?=\s*{|$)/g);

            if (jsonObjects) {
              jsonObjects.forEach(jsonObject => {
                try {
                  const responseData = JSON.parse(jsonObject);

                  // 处理session_init消息（会话初始化）
                  if (responseData.type === 'session_init') {
                    this.currentSessionId = responseData.session_id;
                    console.log('[重做会话初始化] session_id:', this.currentSessionId);
                    return;
                  }

                  // 处理interrupt消息（响应被中断）
                  if (responseData.type === 'interrupt') {
                    console.log('[重做中断] 收到中断消息:', responseData.message);
                    this.isInterrupted = true;
                    this.$message.warning(responseData.message || '重做已被中断');
                    this.chatList[index].msg += '\n\n---\n\n⚠️ ' + (responseData.message || '重做已被中断');
                    this.endStreaming();
                    return;
                  }

                  // 处理timeout消息（会话超时）
                  if (responseData.type === 'timeout') {
                    console.log('[重做超时] 会话超时:', responseData.message);
                    this.$message.warning(responseData.message || '重做已超时');
                    this.chatList[index].msg += '\n\n---\n\n⏱️ ' + (responseData.message || '重做已超时');
                    this.endStreaming();
                    return;
                  }

                  if (responseData.content) {
                    // 记录首token时间
                    if (firstTokenTime === null && responseData.content.length > 0) {
                      firstTokenTime = Date.now();
                    }

                    // 获取RAG搜索时间和其他信息
                    if (responseData["rag_search_time"] !== undefined) {
                      ragSearchTime = responseData["rag_search_time"];
                    }
                    if (responseData["rot_score_algorithmic"] !== undefined) {
                      this.rotScoreAlgorithmic = responseData["rot_score_algorithmic"];
                    }
                    if (responseData["rag_sample_text"] !== undefined) {
                      this.ragSampleText = responseData["rag_sample_text"];
                    }
                    if (responseData["history_sample_text"] !== undefined) {
                      this.historySampleText = responseData["history_sample_text"];
                    }
                    if (responseData["doc_confidence_score"] !== undefined) {
                      this.docConfidenceScore = responseData["doc_confidence_score"];
                    }

                    this.chatList[index].msg += responseData.content;
                    newAnswer += responseData.content;
                  }

                  // 保存session_id（兼容老版本）
                  if (responseData["session_id"] && !this.currentSessionId) {
                    this.currentSessionId = responseData["session_id"];
                    console.log(`[重做会话] 保存session_id: ${this.currentSessionId}`);
                  }
                } catch (e) {
                  console.error('解析重做响应失败:', e);
                }
              });
            }
          }

          // 结束流式输出
          this.endStreaming();

          // 计算时间
          const retryEndTime = Date.now();
          const iterationTotalTime = ((retryEndTime - retryStartTime) / 1000).toFixed(2);
          const iterationFirstTokenTime = firstTokenTime ? ((firstTokenTime - retryStartTime) / 1000).toFixed(2) : 'N/A';

          console.log(`[重做-第二次迭代] 用时 - 总时间: ${iterationTotalTime}s, 首token: ${iterationFirstTokenTime}s`);

          // 更新计时信息（保留第一次回答和第一次深评的计时）
          const existingTimingInfo = this.chatList[index].timingInfo || '';

          // 提取第一次回答和第一次深评的时间信息
          let firstAnswerTotal = 'N/A';
          let firstAnswerDetail = '';
          let evalTotal = 'N/A';
          let evalFirstToken = 'N/A';

          const firstAnswerMatch = existingTimingInfo.match(/• 第一次回答：总计 ([\d.]+)s \((.*?)\)/);
          if (firstAnswerMatch) {
            firstAnswerTotal = firstAnswerMatch[1];
            firstAnswerDetail = firstAnswerMatch[2];
          }

          const evalMatch = existingTimingInfo.match(/• 小模型深评：总计 ([\d.]+)s \(首token ([\d.]+)s/);
          if (evalMatch) {
            evalTotal = evalMatch[1];
            evalFirstToken = evalMatch[2];
          }

          const ragMatch = existingTimingInfo.match(/• RAG检索：([\d.]+)s/);
          const ragInfo = ragMatch ? `• RAG检索：${ragMatch[1]}s\n` : '';

          // 重新构建timing信息
          const totalTime = (parseFloat(firstAnswerTotal) + parseFloat(evalTotal) + parseFloat(iterationTotalTime)).toFixed(2);

          const timingText = `\n\n<div style="color: #999; font-size: 12px; margin-top: 10px; border-top: 1px dashed #ddd; padding-top: 5px;">
⏱️ 用时统计：
${ragInfo}• 第一次回答：总计 ${firstAnswerTotal}s (${firstAnswerDetail})
• 小模型深评：总计 ${evalTotal}s (首token ${evalFirstToken}s + 流式生成 ${(parseFloat(evalTotal) - parseFloat(evalFirstToken)).toFixed(2)}s)
• 迭代回答(重做)：总计 ${iterationTotalTime}s (首token ${iterationFirstTokenTime}s + 流式生成 ${(parseFloat(iterationTotalTime) - parseFloat(iterationFirstTokenTime || 0)).toFixed(2)}s)
• 总计：${totalTime}s
</div>`;

          this.chatList[index].timingInfo = timingText;

          // 执行第二次深评
          const cleanedQuestion = this.cleanCodeBlocks(userQuestion);
          await this.performSecondEvaluation(cleanedQuestion, newAnswer, index);

          this.$message.success('第二次迭代回答重做完成');

        } else {
          // 重做整个流程：按正常流程处理

          // 开始流式输出
          this.startStreaming();

          while (true) {
            const { done, value } = await reader.read();

            // 检查是否已被中断
            if (this.isInterrupted) {
              console.log('[中断检测] 重做-整个流程已中断');
              this.$message.info('已中断，停止重做');
              this.chatList[index].msg += '\n\n---\n\n⚠️ 重做已被用户中断';
              break;
            }

            if (done) break;

            const chunk = decoder.decode(value);
            const jsonObjects = chunk.match(/{[\s\S]*?}(?=\s*{|$)/g);

            if (jsonObjects) {
              jsonObjects.forEach(jsonObject => {
                try {
                  const responseData = JSON.parse(jsonObject);

                  // 处理session_init消息（会话初始化）
                  if (responseData.type === 'session_init') {
                    this.currentSessionId = responseData.session_id;
                    console.log('[重做全流程会话初始化] session_id:', this.currentSessionId);
                    return;
                  }

                  // 处理interrupt消息（响应被中断）
                  if (responseData.type === 'interrupt') {
                    console.log('[重做全流程中断] 收到中断消息:', responseData.message);
                    this.isInterrupted = true;
                    this.$message.warning(responseData.message || '重做已被中断');
                    this.chatList[index].msg += '\n\n---\n\n⚠️ ' + (responseData.message || '重做已被中断');
                    this.endStreaming();
                    return;
                  }

                  // 处理timeout消息（会话超时）
                  if (responseData.type === 'timeout') {
                    console.log('[重做全流程超时] 会话超时:', responseData.message);
                    this.$message.warning(responseData.message || '重做已超时');
                    this.chatList[index].msg += '\n\n---\n\n⏱️ ' + (responseData.message || '重做已超时');
                    this.endStreaming();
                    return;
                  }

                  if (responseData.content) {
                    // 记录首token时间
                    if (firstTokenTime === null && responseData.content.length > 0) {
                      firstTokenTime = Date.now();
                    }

                    // 获取RAG搜索时间和其他信息
                    if (responseData["rag_search_time"] !== undefined) {
                      ragSearchTime = responseData["rag_search_time"];
                    }
                    if (responseData["rot_score_algorithmic"] !== undefined) {
                      this.rotScoreAlgorithmic = responseData["rot_score_algorithmic"];
                    }
                    if (responseData["rag_sample_text"] !== undefined) {
                      this.ragSampleText = responseData["rag_sample_text"];
                    }
                    if (responseData["history_sample_text"] !== undefined) {
                      this.historySampleText = responseData["history_sample_text"];
                    }
                    if (responseData["doc_confidence_score"] !== undefined) {
                      this.docConfidenceScore = responseData["doc_confidence_score"];
                    }

                    // 修复代码块闭合问题
                    let content = this.fixCodeBlockClosure(newAnswer, responseData.content);

                    this.chatList[index].msg += content;
                    newAnswer += content;
                  }

                  // 保存session_id（兼容老版本）
                  if (responseData["session_id"] && !this.currentSessionId) {
                    this.currentSessionId = responseData["session_id"];
                    console.log(`[重做会话] 保存session_id: ${this.currentSessionId}`);
                  }
                } catch (e) {
                  console.error('解析重做响应失败:', e);
                }
              });
            }
          }

          // 结束流式输出
          this.endStreaming();

          // 计算第一次回答的时间
          const firstAnswerEndTime = Date.now();
          const firstAnswerTotalTime = ((firstAnswerEndTime - retryStartTime) / 1000).toFixed(2);
          const firstAnswerFirstTokenTime = firstTokenTime ? ((firstTokenTime - retryStartTime) / 1000).toFixed(2) : 'N/A';

          console.log(`[重做-第一次回答] 用时 - 总时间: ${firstAnswerTotalTime}s, 首token: ${firstAnswerFirstTokenTime}s`);

          // 检查是否已被中断
          if (this.isInterrupted) {
            console.log('[中断检测] 重做整个流程时第一次回答已中断，跳过深评和迭代');
            return;
          }

          // 执行深评和迭代（与正常流程一致）
          const cleanedQuestion = this.cleanCodeBlocks(userQuestion);
          let QAForEval = "提问：\n" + cleanedQuestion + "\n回答：\n" + newAnswer;

          let formDataScene = new FormData();
          formDataScene.append('scene', localStorage.getItem('sceneName'));
          formDataScene.append('subScene', localStorage.getItem('subSceneName'));

          const sceneData = await getSceneSummary(formDataScene);

          if (sceneData.error_num === 0) {
            let sceneName = localStorage.getItem('sceneName');
            let subSceneName = localStorage.getItem('subSceneName');
            const summaryShort = sceneData.summary && sceneData.summary.length > 50 ? sceneData.summary.substring(0, 50) + '...' : sceneData.summary;
            this.sceneSummaryShort = summaryShort;
            QAForEval = "目前的场景是：" + sceneName + "，子场景阶段是：" + subSceneName + "\n其摘要为：" + summaryShort + "\n\n待评文本如下：\n" + QAForEval;

            // 调用评估和迭代
            const timingInfo = {
              ragSearchTime: ragSearchTime,
              firstAnswerTotal: firstAnswerTotalTime,
              firstAnswerFirstToken: firstAnswerFirstTokenTime
            };

            // 在开始深评前重置中断状态
            // this.isInterrupted = false;
            
            await this.windowAnswerWithEvalAndIteration(QAForEval, newAnswer, timingInfo, index);

            this.$message.success('完整流程重做完成');
          } else {
            this.$message.error('场景摘要获取失败，无法继续评估');
          }
        }
        
        // 更新聊天历史记录
        this.updateChatHistory(userQuestion, newAnswer);

        // 重做完成后检查是否需要触发融合综述
        this.checkAndTriggerMergeAfterRetry(userQuestion, newAnswer);
        
        this.$message.success('回答重做完成');
        
      } catch (error) {
        console.error('重做失败:', error);
        this.$message.error('重做失败: ' + error.message);
        this.endStreaming(); // 确保出错时也隐藏中断按钮
      }
    },

    updateChatHistory(userQuestion, newAnswer) {
      // 更新聊天历史记录，替换失败的回答
      try {
        // 发送更新历史记录的请求到后端
        const formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('question', userQuestion);
        formData.append('answer', newAnswer);
        formData.append('model_id', this.chatModelInfo.id);
        
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取
        
        fetch(`${BASE_URL}/api/update_chat_history`, {
          method: 'POST',
          body: formData
        }).then(response => {
          if (response.ok) {
            console.log('聊天历史记录更新成功');
          } else {
            console.error('聊天历史记录更新失败');
          }
        }).catch(error => {
          console.error('更新聊天历史记录时出错:', error);
        });
        
      } catch (error) {
        console.error('更新聊天历史记录失败:', error);
      }
    },

    checkAndTriggerMergeAfterRetry(userQuestion, newAnswer) {
      // 重做完成后检查是否需要触发融合综述
      try {
        // 检查新回答是否有效
        if (!this.isValidAnswer(newAnswer)) {
          console.log('重做后的回答无效，不触发融合综述');
          return;
        }

        this.$message.success("准备更新主窗口融合综述，请稍候...")
        // 通知父组件重做完成，传递窗口ID和回答信息
        this.$emit('retryCompleted', {
          windowId: this.$attrs.windowId,
          modelName: this.chatModelInfo.name,
          answer: newAnswer,
          question: userQuestion
        });

        console.log('重做完成，已通知父组件检查融合综述');
        
      } catch (error) {
        console.error('检查融合综述时出错:', error);
      }
    },

    async getCardRelQue(filenamelist, rightSelectList) {
      if(this.choosedCardIdList.length !== 0) {
        let relQueFormData = new FormData();
        let username = localStorage.getItem('userId')
        relQueFormData.append('username', username);
        // relQueFormData.append('message', "请你给我一段或几段文本");
        relQueFormData.append('filenamelist', filenamelist);
        relQueFormData.append('rightSelectList', rightSelectList);
        relQueFormData.append('choosedCardIdList', this.choosedCardIdList);
        if(this.openCardId !== null) {
          relQueFormData.append('openCardId', this.openCardId);
        }
        if(this.chosenContent !== "") {
          relQueFormData.append('chosenContent', this.chosenContent);
        }
        
        // 先获取深度建议
        try {
          this.$message.success('请稍等，正在根据您勾选的卡片/选取的片段更新导问');
          
          // 构造深度建议的输入文本
          let depthInput = "";
          console.log("[getCardRelQue]", this.chosenContent)
          if (this.choosedCardIdList && this.choosedCardIdList.length > 0) {
            let formDataForCards = new FormData();
            formDataForCards.append('username', username);
            formDataForCards.append('choosedCardIdList', this.choosedCardIdList);
            formDataForCards.append('isForSmallModel', 'true');  // 请求精简版
            
            const cardsData = await getCardsContentByIds(formDataForCards);
            if (cardsData && cardsData.content) {
              depthInput += "【待追问文本内容】\n";
              depthInput += cardsData.content;
            }
          }
          if (this.chosenContent) {
            depthInput += "\n\n【重点待追问内容】\n";
            depthInput += this.chosenContent
          }
          
          // 获取深度建议
          const depthSuggestion = await getDepthSuggestion(depthInput, username);
          if (depthSuggestion) {
            relQueFormData.append('depth_suggestion', depthSuggestion);
            console.log(`[深度建议] 获取成功: ${depthSuggestion.substring(0, 100)}...`);
          }
        } catch (error) {
          console.error('[深度建议] 获取失败:', error);
          // 即使深度建议获取失败，也继续生成导问
        }

        card_rel_questions_request(relQueFormData)
        .then(response => {
          // 后端传回rel_questions
          let rel_questions = response['rel_questions']
          for (let i = 0; i < rel_questions.length; i++) {
            this.questionContents[i] = rel_questions[i]; // 更新第i个元素的content属性
          }
          this.$emit('update:questionContents', rel_questions);
          this.$message.success('导问更新完成');
          // this.$emit('update:answerList', message, filenamelist, answer);
          if(this.isPlus === true) {
            this.LUI2_plus = true
          }
        })
      }
    },

    idToIndex(id) {
      // 此处index是模型切换dialog里显示的顺序
      let index = 0
      // 根据切换的模型更改超参表盘
      if (id === "1002") {
        // "1002" 对应 'GPT4'
        index = 0
      } if (id === "1003") {
        // "1003" 对应 'Mixtral'
        index = 6
      } if (id === "1004") {
        // "1004" 对应 'Kimi'
        index = 5
      } if (id === "1005") {
        // "1005" 对应 'llama3'
        index = 4
      } if (id === "1006") {
        // "1006" 对应 'Claude3.5'
        index = 1
      } if (id === "1007") {
        // "1007" 对应 'Deepseek-v3'
        index = 2
      } if (id === "1008") {
        // "1008" 对应 'Deepseek-r1'
        index = 3
      } if (id === "1009") {
        // "1009" 对应 'Gemini'
        index = 7
      } if (id === "1010") {
        // "1010" 对应 'Qwq'
        index = 8
      }
      return index
    },
    // 清理文本中的代码块
    cleanCodeBlocks(text, blocksToRemove = ['thinking', 'checking']) {
      let cleanedText = text;
      
      blocksToRemove.forEach(blockType => {
        const regex = new RegExp('```' + blockType + '[\\s\\S]*?```', 'g');
        cleanedText = cleanedText.replace(regex, '');
      });
      
      // 清理多余的换行
      cleanedText = cleanedText.replace(/\n{3,}/g, '\n\n');
      
      return cleanedText;
    },
    // 修复代码块闭合问题：检测```thinking后是否有```闭合，如果没有则在```checking前补上
    fixCodeBlockClosure(currentAnswer, newContent) {
      if (!newContent || !newContent.includes("```checking")) {
        return newContent;
      }
      
      // 检查累积的answer + newContent中是否有未闭合的```thinking
      const combined = currentAnswer + newContent;
      
      // 查找最后一个```thinking的位置
      const lastThinkingIndex = combined.lastIndexOf("```thinking");
      if (lastThinkingIndex === -1) {
        return newContent;
      }
      
      // 从thinking位置开始查找，看是否在checking之前有闭合的```
      const afterThinking = combined.substring(lastThinkingIndex);
      const checkingIndex = afterThinking.indexOf("```checking");
      
      if (checkingIndex !== -1) {
        // 提取thinking和checking之间的内容
        const betweenThinkingAndChecking = afterThinking.substring("```thinking".length, checkingIndex);
        
        // 统计代码块标记
        // 计算独立的```的数量（三个反引号，前后不能再有反引号）
        const codeBlockMatches = betweenThinkingAndChecking.match(/(?<![`])```(?![`])/g);
        const codeBlockCount = codeBlockMatches ? codeBlockMatches.length : 0;
        
        console.log(`[代码块检测] thinking和checking之间找到${codeBlockCount}个独立的\`\`\`标记`);
        
        // 如果```的数量是偶数（包括0），说明thinking块没有闭合
        // 因为一个完整的代码块需要奇数个```（开头的```xxx + 结尾的```）
        if (codeBlockCount % 2 === 0) {
          // 没有找到闭合的```，需要在```checking前补上
          // 确保格式正确：换行 + ``` + 换行换行 + ```checking
          newContent = newContent.replace(/```checking/, "\n```\n\n```checking");
          console.log("[修复] 在```checking前补上了闭合的```（thinking块未闭合）");
        } else {
          console.log("[代码块检测] thinking块已正确闭合，无需修复");
        }
      }
      
      return newContent;
    },
    mergeModelAnswers() {
      this.shouldScroll = true;
      let username = localStorage.getItem('userId')
      let originRealName = localStorage.getItem('originRealName') + localStorage.getItem('userId').replace(localStorage.getItem('realName'), '')
      // let mergePrompt = "上述几段待融合文本是针对同一个问题的几个回答版本，由不同的几个大模型生成，在括号内有标注。\n请你仔细思考后，综合上述几段回答文本，理解各自的优点精华，然后在不改变整体内涵的前提下，请你思考并融合为一段高质量、高浓缩、理解精髓的回答。\n要求每段待融合文本至少取一段内容参与融合，并通过类似“（来自xxx模型回答文本的片段）”显式地标识出来；且除此之外，你给出的这一段最终的融合版本中，文字内容不能全部来自给定的几段待融合文本，还要有你自己的更加深刻的思考"
      let mergePrompt = `1.任务及目标描述
（1）任务：上述几段待融合文本是针对同一个问题的几个回答版本，由不同的几个大模型生成，在括号内有标注来源！你需要先直接去除可能是无效/失败/出错的模型回答，然后编写一个融合版本
（2）目标：融合版本要基于而又超越原始文本，逻辑清晰、融合全面且深刻理解核心思想精髓，既保留各原始版本的精华，又能够矫正可能的错误（首选策略是深刻对比理解纠错，次选策略是少数服从多数纠错），且通过深度思考实现提升

2.具体步骤及要求
（1）初步分析及整合
a. 先对各个待融合回答文本段进行初步分析，识别出核心观点：
- 识别每段文本的核心论点与独特见解
- 分析各自的表达特色与思维角度
- 找出彼此间的互补性、差异性和优缺点，并矫正可能的错误
b. 然后进行初步整合：
- 确保每段待融合文本中至少一个重要原始片段被纳入到最终答案，在下面的步骤（3）中需要通过“（来自xxx模型）”明确标识引用来源
- 确保内容结构层次分明、递进合理
- 建立清晰的主次关系
- 控制整体篇幅合适，删除重复、冗余或价值较低的内容，突出重点
- 统一语言风格，补充必要的过渡和连接，确保行文流畅
（2）深刻原创思考
在上一步基础上深入提炼、分析、总结，添加新的洞见或更深层解读：
- 鼓励提出超越原文本段的新观点、建立更具启发性的概念连接
- 基于已有观点发掘更深层、更有价值的思考维度
- 寻找可能被忽略的重要视角
- 构建更系统化的论证
- 至少20%为上述原创思考内容，在下面的步骤（3）中需要通过“（来自我的原创思考）”也做好标识
（3）整体融合版本编写
在前两步的基础上组织最终融合版内容编写，明确主旨，准确抓住核心，围绕用户问题和主题展开（你的融合版编写要以更好地回答前面的用户提问为目的，要能完整、有层次、高质量地回答用户的问题；但如果各个待融合的文本段都不是直接回答，而是反问、建议等引导用户深度思考后主动解决问题的语境风格，那你需要继续保持这种语境），使得最终答案高度统一且凝练，形成整体既有广度又有深度的综合性论述，另外篇幅和格式也要合理

3.输出内容及格式
在保证以上要求，高质量完成内容的前提下，你必须严格按照以下模板格式输出（前两个步骤控制字数少一些，占30%左右；以第三个步骤编写的综合回答内容高质量为主，占70%左右）：
标题：本次xx模型回答融合综述
【初步分析及整合】
xxx
【深刻原创思考】
xxx
【整体融合版本编写】
xxx`;
// 暂时去掉
// （4）表达优化及检查
// 确认无遗漏细节后再给出结果，通过简洁的语言总结传达融合效果，在完成以上全部步骤后回顾是否还有可提高之处
      let question = "提问：\n" + this.nowTurnQuestion + "\n回答：\n"
      let message = question + this.ModelContentMerge + mergePrompt
      let formData = new FormData()
      formData.append('username', username);
      formData.append('originRealName', originRealName)
      formData.append('model_id', this.chatModelInfo.id);
      formData.append('message', message);
      formData.append('filenamelist', []);
      formData.append('summary', this.summary);
      formData.append('leftSelectList', []);
      formData.append('rightSelectList', []);
      // 将 portraitStates 对象转换为 JSON 字符串再添加到 FormData
      let portraitStates = {
        0: false,
        1: false,
        2: false,
        3: false,
        4: false,
        5: false,
        6: false
      };
      let index = this.idToIndex(this.chatModelInfo.id)
      portraitStates[index] = true
      formData.append('modelStates', JSON.stringify(portraitStates));

      formData.append('isHistoryUsed', false);
      formData.append('isSummaryUsed', false);
      formData.append('rounds', this.rounds)

      formData.append('realName', localStorage.getItem('realName'));
      formData.append('userbookName', localStorage.getItem('userId'));
      formData.append('sceneName', localStorage.getItem('sceneName'));
      let seed = localStorage.getItem('seed');
      let seednumber = 0;
      if (seed === 'topic') { seednumber = 1; }
      else if (seed === 'question') { seednumber = 2; }
      else { seednumber = 0; }
      formData.append('seed', seednumber); // 默认为0，topic是1，question是2

      // 后端逻辑
      let paramFormData = new FormData();
      const runtime_params = modelManager.getHyperParamsDictionary()
      let paramString = JSON.stringify(runtime_params);
      // let paramString = JSON.stringify(this.params);
      paramFormData.append('params', paramString);
      paramFormData.append('modelID', this.chatModelInfo.id)
      paramFormData.append('username', username);
      paramFormData.append('windowId', this.$attrs.windowId);

      paramFormData.append('message', message);
      paramFormData.append('filenamelist', []);
      paramFormData.append('rightSelectList', []);
      paramFormData.append('isHistoryUsed', false);
      paramFormData.append('rounds', this.rounds);

      paramFormData.append('originRealName', originRealName)

      // 🔥 如果使用了tab增强后的问题，传递核心关键词（通过props传递）
      if (this.coreKeyword) {
        paramFormData.append('coreKeyword', this.coreKeyword);
      }
      this.appendCrossNotebookParams(paramFormData);

      // 用于给后端区分是主窗口综合回答还是普通回答，后端据此判断是否需要将中间结果chat_with_files_params保留到临时tmp
      paramFormData.append('mode', 'merge')

      this.LUI2_plus = false
      let answer = "";
      // 首先执行 chat_sendParams
      chat_sendParams(paramFormData)
      .then(response => {
        // 当 chat_sendParams 成功执行后，才执行 chat_send
        console.log("chat_sendParams response:", response);
        return chat_send(this.chatModelInfo.name, formData, this.$attrs.windowId); // 返回 chat_send 的 Promise，以便在下一个 .then 中处理
      })
      .then(response => {
        // 处理 chat_send 的响应
        const reader = response.body.getReader(); // 使用响应的ReadableStream来处理数据
        this.startStreaming(); // 开始流式输出，显示中断按钮
        // 后端传回数据，显示
        const processStream = () => {
          const decoder = new TextDecoder('utf-8');
          reader.read().then(({done, value}) => {
            if (done) {
              // 保存中断状态（在endStreaming重置之前）
              const wasInterrupted = this.isInterrupted;

              this.endStreaming(); // 流式输出结束，隐藏中断按钮

              // 检查是否已被中断，如果中断则跳过末端红蓝深评
              if (wasInterrupted) {
                console.log('[中断检测] 合并回答已中断，跳过末端红蓝深评');
                this.$message.info('已中断，跳过末端红蓝深评');
                // 在消息末尾添加中断提示
                this.chatList[this.chatList.length - 1].msg += '\n\n---\n\n⚠️ 回答已被用户中断';
                this.chatEnd = true;
                this.$emit('mergeEnd', this.nowTurnQuestion);
                return;
              }

              // 处理问题，移除问题中的thinking/checking块，目的是在！加强末端大小对齐轮次时，避免第一次小模型的连续thinking异常输出影响
              // ！加强后的轮次
              const cleanedQuestion = this.cleanCodeBlocks(this.nowTurnQuestion);
              let QAEnd = "提问：\n" + cleanedQuestion + "\n综合回答：\n" + answer
              console.log("问答末端红蓝小模型流式待评测：", QAEnd)
              this.$message.success('对话窗口模型协同末端，进行红蓝卡标引控');

              let formDataScene = new FormData();
              formDataScene.append('scene', localStorage.getItem('sceneName'));
              formDataScene.append('subScene', localStorage.getItem('subSceneName'));

              getSceneSummary(formDataScene).then(data => {
                if(data.error_num === 0) {
                  let sceneName = localStorage.getItem('sceneName')
                  let subSceneName = localStorage.getItem('subSceneName')
                  console.log("场景子场景摘要获取成功：", sceneName, subSceneName, data.summary)
                  QAEnd = "目前的场景是：" + sceneName + "，子场景阶段是：" + subSceneName + "\n其摘要为：" + data.summary + "\n\n待评文本如下：\n" + QAEnd
                
                  this.QAEndHLEvalStream(QAEnd).then((result) => {
                    this.chatEnd = true;
                    console.log('Stream reading complete');
                    // 对话结束后，发送请求获取相关问题
                    console.log("chatEnd:", this.chatEnd);

                    // 处理结果，并截取特定标记后的内容，作为末端红蓝深评大小模型对齐闭环的小模型输入
                    result = result.replace(/<\|end_G\|><\|start_C\|>/g, '分  ');
                    result = result.replace(/<\|end_C\|><\|start_S\|>/g, '\n\n');
                    result = result.replace(/<\|end_S\|><\|end_OUTPUT\|>/g, '');
                    result = result.replace(/<\|end_A\|><\|end_OUTPUT\|>/g, '');
                    // \\n不能被正常解码为空行显示
                    result = result.replace('\\n', '\n')
                    let processedResult = result;
                    const marker = "\n\n---\n### 末端红蓝深评\n";
                    
                    if (result && result.includes(marker)) {
                      // 分割字符串并获取标记后的部分
                      processedResult = result.split(marker)[1];
                    }
                    this.$emit('mergeEnd', this.nowTurnQuestion, processedResult);
                  });
                } else {
                  this.$message.error('场景子场景摘要获取失败');
                  this.chatEnd = true;
                  this.$emit('mergeEnd', this.nowTurnQuestion);
                }
              })

              return;
            }
            const resp = decoder.decode(value);
            // console.log('Processed chunk:', resp);
            let responseData;
            // 使用正则表达式匹配和提取每个独立的 JSON 对象
            const jsonObjects = resp.match(/{[\s\S]*?}(?=\s*{|$)/g);
            if (jsonObjects) {
              jsonObjects.forEach(jsonObject => {
                responseData = JSON.parse(jsonObject);
                // 处理解析后的 JSON 数据
                // if(this.chatModelInfo.name == response["model"]) {
                let content = responseData["content"];

                // 保存session_id（合并模型回答的第一个chunk中包含）
                if (responseData["session_id"] && !this.currentSessionId) {
                  this.currentSessionId = responseData["session_id"];
                  console.log(`[合并会话] 保存session_id: ${this.currentSessionId}`);
                }

                // 修复代码块闭合问题
                content = this.fixCodeBlockClosure(answer, content);

                // let hasConsecutiveQuestionMarks = (this.nowTurnQuestion.includes("???") || this.nowTurnQuestion.includes("？？？"));
                let hasConsecutiveQuestionMarks = /(?<!\?)\?\?\?(?!\?)/g.test(this.nowTurnQuestion) || 
                                   /(?<!？)？？？(?!？)/g.test(this.nowTurnQuestion);
                if (answer === "" && hasConsecutiveQuestionMarks === true) {
                  content = "### 本次是脱场景文档对话\n" + content
                }
                // let hasDoubleQuestionMarks = (this.nowTurnQuestion.includes("??") || this.nowTurnQuestion.includes("？？"));
                // let hasDoubleQuestionMarks = /(?<!\?)\?\?(?!\?)/g.test(this.nowTurnQuestion) || 
                //                    /(?<!？)？？(?!？)/g.test(this.nowTurnQuestion);

                // 增强的双问号正则表达式，带有可选加号
                let doubleQuestionMarkMatch = this.nowTurnQuestion.match(/(?<!\?)\?\?\+{0,3}(?!\?)/g) || 
                                  this.nowTurnQuestion.match(/(?<!？)？？\+{0,3}(?!？)/g);
                let hasDoubleQuestionMarks = doubleQuestionMarkMatch !== null;
                let plusCount = 0;
                // 如果找到双问号，则计算加号
                if (hasDoubleQuestionMarks && doubleQuestionMarkMatch.length > 0) {
                  const matchString = doubleQuestionMarkMatch[0];
                  plusCount = (matchString.match(/\+/g) || []).length;
                  console.log("双问号加号检测", this.nowTurnQuestion, hasDoubleQuestionMarks, "加号数量:", plusCount);
                }

                if (answer === "" && hasDoubleQuestionMarks === true) {
                  let entropyPrompt = "### 本次是熵减的建议引导性回答而不直接给出答案\n";
                  if (plusCount === 1) {
                    entropyPrompt = "### 本次是低程度熵减的建议引导性回答，适度提供明确建议，引导用户思考\n";
                  } else if (plusCount === 2) {
                    entropyPrompt = "### 本次是中程度熵减的建议引导性回答，减少明确建议，增强发问幅度、反问语气、问题链的引导张力和深度\n";
                  } else if (plusCount === 3) {
                    entropyPrompt = "### 本次是高程度熵减的建议引导性回答，几乎不提供直接建议，大幅增强反问语气和问题引导句式，提供深度思考价值和进阶、关联、张力极强的问题链\n";
                  }
                  content = entropyPrompt + content;
                }
                answer += content;
                // console.log(responseData["model"] + ": " + content);
                let timeParams = responseData['nowParams']
                let params = { modelsId: this.chatModelInfo.id };
                let res = getChatMsg(params);
                let modelMsg = {
                  headImg: res[0].headImg,
                  name: res[0].name,
                  time: getTime(),
                  msg: content,
                  chatType: 0, //信息类型，0文字，1图片
                  uid: '2000', //uid
                  checked: false,
                  timeParams: timeParams,
                  seed: responseData["seed"],
                };
                this.shouldScroll = true;
                this.sendMsg(modelMsg);
              });
            } else {
              console.error('No JSON objects found in the stream:', resp);
              this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + resp);
            }
            // 继续读取下一块数据
            processStream();
          })
        };
        processStream();
      })
      .catch(error => {
        this.endStreaming(); // 发生错误时，隐藏中断按钮
        // 处理两个请求中的任何一个发生的错误
        console.error("An error occurred:", error);
        this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + error);
        // localStorage.setItem('userId', localStorage.getItem('realName'));
        // router.push('/home');
        // alert("问答发生了错误，请重新进入笔记本，最好重新登陆！原因可能是请求总字数过长或大模型余额不足，前者请减少重试，后者请告知管理员充值");
      });
    },

    clearChatList() {
      // 只保留数组的第一个元素，移除其他所有元素
      this.chatList.splice(1, this.chatList.length - 1);
    },

    handleDragStart(event, index) {
      // 存储被拖拽的回答信息
      event.dataTransfer.setData('application/json', JSON.stringify({
        sourceWindowId: this.$attrs.windowId,
        modelResponse: event.target.dataset.modelResponse,
        modelName: event.target.dataset.modelName,
        chatIndex: event.target.dataset.chatIndex
      }));
      
      // 触发父组件的拖拽开始事件
      this.$emit('dragStart', this.$attrs.windowId);
    },
    
    handleDragEnd() {
      // 触发父组件的拖拽结束事件
      this.$emit('dragEnd');
    },

    noChangeModel() {
      // 阻止事件继续传播
      event.stopPropagation();
    },
    run_LUI2_plus(msg, index) {
      this.$emit('LUI2_A_dia');
      let formData = new FormData();
      let formLui2 = JSON.stringify(this.formLui2);
      formData.append('formLui2', formLui2);
      formData.append('wen', this.chatList[index-1].msg);
      formData.append('content', msg);
      formData.append('username', localStorage.getItem('userId'));
      agent_LUI2(formData).then(data => {
        if(data['error_num'] === 0) {
          this.$emit('LUI2_agent', data['all_history'], data['score'], data['color'], data['scoreEnd'], data['colorEnd'], this.chatList[index-1].msg);
          this.LUI2_plus_index = index
          this.waitForChange = true
        } else {
          this.$emit('LUI2_A_err');
          this.$message.error('出错了，请重试，若再次出错，请联系管理员并暂勿使用此功能');
        }
      })

      // 阻止事件继续传播
      event.stopPropagation();
    },

    // 添加新方法用于处理关联卡片
    processRelatedCards(postIndex, qaTotalStr) {
      // 如果postIndex为空，则不处理
      if (!postIndex || postIndex === '') {
        console.log("没有关联卡片需要处理");
        return;
      }
      
      try {
        // 解析postIndex为cid列表
        let cidList = [];
        try {
          // 尝试解析JSON
          cidList = JSON.parse(postIndex);
        } catch (e) {
          // 如果不是JSON格式，按逗号分隔
          cidList = postIndex.split(/[,，、\s]+/).filter(item => item.trim());
        }
        
        // 如果没有关联卡片，则直接返回
        if (!cidList || cidList.length === 0) {
          console.log("没有关联卡片需要处理");
          return;
        }
        
        this.$message.info(`共有 ${cidList.length} 张关联卡片需要更新`);
        
        // 串行处理每个关联卡片，避免并发请求过多
        const processCard = async (index) => {
          if (index >= cidList.length) {
            this.$message.success('所有关联卡片处理完成');
            return;
          }
          
          const relatedCid = cidList[index];
          this.$message.info(`开始处理第 ${index + 1} 张关联卡片 (ID: ${relatedCid})...`);
          
          // 创建表单数据
          let relatedFormData = new FormData();
          relatedFormData.append('cid', relatedCid);
          relatedFormData.append('content', qaTotalStr);
          relatedFormData.append('username', localStorage.getItem('userId'));
          
          try {
            // 更新关联卡片内容
            const updateResult = await card_updateContentById(relatedFormData);
            
            if (updateResult['error_num'] === 0) {
              this.$message.success(`关联卡片 ${relatedCid} 内容更新成功`);
              
              // 准备评分请求
              let relatedFormDataScore = new FormData();
              relatedFormDataScore.append('cid', relatedCid);
              relatedFormDataScore.append('content', qaTotalStr);
              relatedFormDataScore.append('username', localStorage.getItem('userId'));
              
              try {
                // 关联卡片评分
                const scoreResult = await card_score(relatedFormDataScore);
                
                if (scoreResult.error_num === 0) {
                  console.log(`关联卡片 ${relatedCid} 大模型打分：${scoreResult.score}`);
                  
                  try {
                    // 关联卡片的红蓝评测
                    await this.waitDecodedResult(scoreResult.card_id, qaTotalStr);
                    this.$message.success(`关联卡片 ${relatedCid} 评分完成`);
                  } catch (error) {
                    console.error(`关联卡片 ${relatedCid} 微调模型评分出错:`, error);
                  }
                } else {
                  console.log(`关联卡片 ${relatedCid} 评分未成功: ${scoreResult.message}`);
                }
              } catch (error) {
                console.error(`关联卡片 ${relatedCid} 评分请求出错:`, error);
              }
            } else {
              this.$message.error(`关联卡片 ${relatedCid} 内容更新未成功`);
            }
          } catch (error) {
            console.error(`关联卡片 ${relatedCid} 更新请求出错:`, error);
          }
          
          // 处理下一张卡片
          await processCard(index + 1);
        };
        
        // 开始处理第一张关联卡片
        processCard(0);
        
      } catch (error) {
        console.error("处理关联卡片时出错:", error);
        this.$message.error('处理关联卡片时出错');
      }
    },

    handleButtonClick(index, uid) {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限添加或修改卡片主体');
      //   return
      // }
      // 检查是否有卡片操作权限（作者或群组协作用户）
      if (!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限添加或修改卡片主体');
        return
      }
      // 当pin被点击时，这个方法会被调用，index是当前项的下标
      // console.log(`Item content:`, this.chatList[index]);
      // 只勾选了图片文档，要更新图片摘要描述的本地向量库
      if(this.fileNameList.length === 1 && (this.fileNameList[0].endsWith('.jpg') || this.fileNameList[0].endsWith('.png') || this.fileNameList[0].endsWith('.jpeg'))) {
        let formData = new FormData();
        let qaTotalStr = ""
        if(uid !== '2000') {
          qaTotalStr = "提问：" + this.chatList[index-1].msg + "\n回答：" + this.chatList[index].msg
        } else {
          qaTotalStr = "提问：" + this.chatList[index-2].msg + "\n回答：" + this.chatList[index].msg
        }
        // 检查并移除 "### 末端红蓝深评" 及其后面的内容
        const redBlueIndex = qaTotalStr.indexOf("\n\n---\n### 末端红蓝深评\n");
        if (redBlueIndex !== -1) {
          qaTotalStr = qaTotalStr.substring(0, redBlueIndex);
        }
        formData.append('username', localStorage.getItem('userId'));
        formData.append('filename', this.fileNameList[0]);
        formData.append('imgid', 0);
        formData.append('content', qaTotalStr);
        this.$emit('updateFileCardBanStyle', this.fileNameList[0], true);
        this.$message.success('开始合并更新图片文档矢量库摘要，请稍等');

        update_img_text(formData).then(data => {
          this.$message.success('图片文档矢量库文本摘要更新成功！');
          this.$emit('updateFileCardBanStyle', this.fileNameList[0], false);
        }).catch(error => {
          console.error("An error occurred:", error);
          this.$message.error('图片文档矢量库文本摘要更新失败：', error);
          this.$emit('updateFileCardBanStyle', this.fileNameList[0], false);
        });
      } else {
        if(this.choosedCardIdList.length !== 1) {
          if(uid !== '2000') {
            this.Question = this.chatList[index - 1].msg;
            this.Answer = this.chatList[index].msg;
          } else {
            this.Question = this.chatList[index - 2].msg;
            this.Answer = this.chatList[index].msg;
          }
          console.log("要pin的问题和回答: ", this.Question, this.Answer)
          
          // 需要id, username, datetime, content, type, model, params

          let formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          let originRealName = localStorage.getItem('originRealName') + localStorage.getItem('userId').replace(localStorage.getItem('realName'), '')
          formData.append('originRealName', originRealName)

          formData.append('datetime', getDateTime());
          formData.append('model_id', this.chatModelInfo.id);
          // 这里卡片打分只送入了卡片内容而没有用户提问内容，可能是有问题的，因为后续自制评测模型也是对一对 QA 出评分和理由，也是因为理论就应该
          // 对一对 QA 打分，所以才做这个针对 QA 的评测模型，这里后续要改一改，加上提问（但是红蓝种子放大制备场景，QA的A中又嵌套大量QA，不知道
          // 会不会有问题）
          let qaTotalStr = ""
          let questionContent = ""
          let answerContent = this.chatList[index].msg
          
          if(uid !== '2000') {
            questionContent = this.chatList[index-1].msg
          } else {
            questionContent = this.chatList[index-2].msg
          }
          
          // 新增：提取迭代后的回答（如果存在）
          // 检查是否存在迭代回答（answer-eval-answerAgain结构）
          const evalStartMarker = "\n\n```eval\n";
          const evalEndMarker = "\n```";
          const iterationMarker = "\n\n---\n### 迭代改进后的回答\n";
          
          let finalAnswer = answerContent;
          
          // 如果存在迭代标记，说明是新的answer-eval-answerAgain结构
          if (answerContent.includes(iterationMarker)) {
            const iterationIndex = answerContent.indexOf(iterationMarker);
            // 提取迭代后的回答部分（从迭代标记后开始）
            finalAnswer = answerContent.substring(iterationIndex + iterationMarker.length);
            console.log("检测到迭代回答，提取迭代后的内容用于钉卡");
          } else if (answerContent.includes(evalStartMarker)) {
            // 如果有eval标记但没有迭代标记（可能是评估失败的情况），提取eval之前的内容
            const evalIndex = answerContent.indexOf(evalStartMarker);
            finalAnswer = answerContent.substring(0, evalIndex);
            console.log("检测到eval标记但无迭代回答，使用第一次回答内容");
          }

          // 移除 second-eval 部分（第二次深评内容）
          const secondEvalIndex = finalAnswer.indexOf("\n\n```second-eval");
          if (secondEvalIndex !== -1) {
            finalAnswer = finalAnswer.substring(0, secondEvalIndex);
            console.log("移除了 second-eval 部分");
          }
          
          qaTotalStr = "提问：" + questionContent + "\n回答：" + finalAnswer

          // 检查并移除 "### 末端红蓝深评" 及其后面的内容（针对主窗口综述的情况）
          const redBlueIndex = qaTotalStr.indexOf("\n\n---\n### 末端红蓝深评\n");
          if (redBlueIndex !== -1) {
            qaTotalStr = qaTotalStr.substring(0, redBlueIndex);
          }
          console.log("要生成卡片的问答对内容：", qaTotalStr)
          formData.append('content', qaTotalStr);
          formData.append('seed', this.chatList[index].seed);
          formData.append('status', this.summary);
          formData.append('sceneName', this.sceneName);
          formData.append('subSceneName', this.subSceneName);
          formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递

          let timeParamsStr = JSON.stringify(this.chatList[index].timeParams);
          formData.append('timeParams', timeParamsStr);

          // 添加置信度和腐烂度信息
          const confidenceScore = this.chatList[index].confidenceScore || 3.0;
          const rotScore = this.chatList[index].rotScore || 3.0;
          formData.append('confidence_score', confidenceScore);
          formData.append('rot_score', rotScore);
          console.log(`钉卡片 - 置信度: ${confidenceScore}, 腐烂度: ${rotScore}`);

          // 🔥 如果有勾选的卡片，将卡片ID列表传递给后端，用于设置新卡片的postIndex
          if (this.choosedCardIdList && this.choosedCardIdList.length > 0) {
            formData.append('choosedCardIdList', JSON.stringify(this.choosedCardIdList));
            console.log(`[钉卡片] 勾选的卡片ID列表: ${JSON.stringify(this.choosedCardIdList)}`);
          }

          // 🔥 传递生成此卡片时勾选的文档列表
          if (this.fileNameList && this.fileNameList.length > 0) {
            formData.append('file_list', JSON.stringify(this.fileNameList));
            console.log(`[钉卡片] 勾选的文档列表: ${JSON.stringify(this.fileNameList)}`);
          }

          // let formDataScore = new FormData()
          // formDataScore.append('username', localStorage.getItem('userId'));
          // formDataScore.append('content', qaTotalStr);

          // 🔥 问答钉卡时，立即滚动到CardGrid顶部显示等待卡片
          // 先触发滚动（同步执行），再显示等待卡片
          this.$emit('scrollToCardGridTop')
          // 确保滚动先执行
          this.$nextTick(() => {
            this.$emit('goCardGrid')
          })

          card_upload(formData).then(response => {
            if (response.error_num === 0) {
              let cardId = response.card_id

              // 半自动化添加记录 - 记录创建的卡片及cid
              this.$emit('pinCard', {
                question: qaTotalStr.split('\n回答：')[0].replace('提问：', ''),
                answer: qaTotalStr.split('\n回答：')[1],
                content: qaTotalStr,
                modelId: this.chatModelInfo.id,
                status: this.summary,
                seed: this.chatList[index].seed,
                timeParams: this.chatList[index].timeParams,
                sceneName: this.sceneName,
                subSceneName: this.subSceneName,
                keyTopics: this.keyTopics,
                created_card_id: cardId  // 添加创建的卡片ID
              });

              // formDataScore.append('cid', cardId);
              // 后端卡片更新完成后，更新到卡片窗口中
              // 🔥 传递新生成的卡片ID给mainPage，用于等待卡消失后滚动到新卡片
              this.$emit('cardUpdate', cardId);
              this.getModelEval(qaTotalStr, cardId);
              // 传递第二次综合评分（如果有）
              const secondEvalScore = this.chatList[index] ? this.chatList[index].secondEvalComprehensiveScore : null;
              console.log(`[钉卡片] 当前问答的第二次综合评分: ${secondEvalScore}`);
              this.getOurModelEval(qaTotalStr, cardId, -1, secondEvalScore);
              // card_score(formDataScore).then(response => {
              //   if (response.error_num === 0) {
              //     // 钉卡片同时保存QA数据用于评估反馈
              //     this.score.GPT4 = response.score;
              //     console.log("大模型打分：" + response.score);
              //     // 后端卡片浅评打分更新完成后，更新到操作流中
              //     this.$emit('cardOpeUpd', this.score.GPT4, qaTotalStr);
              //     this.databack();
              //     // 红蓝评测微调模型打分
              //     this.waitDecodedResult(response.card_id, qaTotalStr)
              //   } else {
              //     this.$message.error('卡片打分未成功！')
              //     console.log(response['message'])
              //   }
              // });
            } else {
              this.$message.error('卡片保存失败，请重试！')
              console.log(response['message'])
            }
          });
        } else {
          let formData = new FormData();
          let qaTotalStr = ""
          if(uid !== '2000') {
            qaTotalStr = "提问：" + this.chatList[index-1].msg + "\n回答：" + this.chatList[index].msg
          } else {
            qaTotalStr = "提问：" + this.chatList[index-2].msg + "\n回答：" + this.chatList[index].msg
          }
          // 检查并移除 "### 末端红蓝深评" 及其后面的内容
          const redBlueIndex = qaTotalStr.indexOf("\n\n---\n### 末端红蓝深评\n");
          if (redBlueIndex !== -1) {
            qaTotalStr = qaTotalStr.substring(0, redBlueIndex);
          }
          let cid = this.choosedCardIdList[0]
          formData.append('cid', cid);
          formData.append('content', qaTotalStr);
          formData.append('username', localStorage.getItem('userId'));
          if(this.openCardId !== null) {
            formData.append('openCardId', this.openCardId);
          }
          if(this.chosenContent !== "") {
            formData.append('chosenContent', this.chosenContent);
          }

          let formDataScore = new FormData()
          formDataScore.append('username', localStorage.getItem('userId'));
          formDataScore.append('content', qaTotalStr);
          // 🔥 合并回原卡时，设置cardSingleMaking状态
          this.$emit('goCardGridWithoutMaking')
          this.$message.success('回答内容正在合并回原卡，请稍等');
          card_updateContentById(formData).then(data => {
            if(data['error_num'] === 0) {
              let cardId = cid;
              this.$message.success('原卡片内容更新成功！');
              // 保存返回的postIndex，稍后处理
              const postIndex = data['postIndex'];

              formDataScore.append('cid', cid);
              // 🔥 合并回原卡完成时，清除cardSingleMaking状态
              this.$emit('clearCardSingleMaking')
              // 后端卡片更新完成后，更新到卡片窗口中
              this.$emit('cardUpdate');

              this.getModelEval(qaTotalStr, cardId);
              // 传递第二次综合评分（如果有）
              const secondEvalScore = this.chatList[index] ? this.chatList[index].secondEvalComprehensiveScore : null;
              console.log(`[钉卡片] 当前问答的第二次综合评分: ${secondEvalScore}`);
              this.getOurModelEval(qaTotalStr, cardId, postIndex, secondEvalScore);
              // card_score(formDataScore).then(response => {
              //   if (response.error_num === 0) {
              //     this.score.GPT4 = response.score;
              //     console.log("大模型打分：" + response.score);
              //     // 后端卡片浅评打分更新完成后，更新到操作流中
              //     this.$emit('cardOpeUpd', this.score.GPT4, qaTotalStr);
              //     // 红蓝评测微调模型打分
              //     this.waitDecodedResultPromise(response.card_id, qaTotalStr).then(() => {
              //       // 处理关联卡片
              //       this.processRelatedCards(postIndex, qaTotalStr);
              //     }).catch(error => {
              //       console.error("微调模型评分出错-单卡迭代时:", error);
              //       // 即使waitDecodedResult出错，仍然处理关联卡片
              //       this.processRelatedCards(postIndex, qaTotalStr);
              //     });
              //   } else {
              //     this.$message.error('卡片打分未成功！')
              //     console.log(response['message'])

              //     // 即使card_score出错，仍然执行微调模型评分和关联卡片处理
              //     this.waitDecodedResultPromise(response.card_id, qaTotalStr).then(() => {
              //       this.processRelatedCards(postIndex, qaTotalStr);
              //     }).catch(error => {
              //       console.error("微调模型评分出错-单卡迭代时:", error);
              //       this.processRelatedCards(postIndex, qaTotalStr);
              //     });
              //   }
              // });
            } else {
              this.$message.error('卡片内容更新未成功');
            }
          })
        }
      }

      // 阻止事件继续传播
      event.stopPropagation();
    },

    // 处理悬浮pin按钮点击
    handlePinCard(index, uid) {
      // 检查是否有卡片操作权限（作者或群组协作用户）
      if (!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限添加或修改卡片主体');
        return
      }
      
      // 执行钉卡逻辑（复用handleButtonClick中的钉卡部分）
      if(uid !== '2000') {
        this.Question = this.chatList[index - 1].msg;
        this.Answer = this.chatList[index].msg;
      } else {
        this.Question = this.chatList[index - 2].msg;
        this.Answer = this.chatList[index].msg;
      }
      console.log("要pin的问题和回答: ", this.Question, this.Answer)
      
      // 需要id, username, datetime, content, type, model, params

      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      let originRealName = localStorage.getItem('originRealName') + localStorage.getItem('userId').replace(localStorage.getItem('realName'), '')
      formData.append('originRealName', originRealName)

      formData.append('datetime', getDateTime());
      formData.append('model_id', this.chatModelInfo.id);
      // 这里卡片打分只送入了卡片内容而没有用户提问内容，可能是有问题的，因为后续自制评测模型也是对一对 QA 出评分和理由，也是因为理论就应该
      // 对一对 QA 打分，所以才做这个针对 QA 的评测模型，这里后续要改一改，加上提问（但是红蓝种子放大制备场景，QA的A中又嵌套大量QA，不知道
      // 会不会有问题）
      let qaTotalStr = ""
      let questionContent = ""
      let answerContent = this.chatList[index].msg
      
      if(uid !== '2000') {
        questionContent = this.chatList[index-1].msg
      } else {
        questionContent = this.chatList[index-2].msg
      }
      
      // 新增：提取迭代后的回答（如果存在）
      // 检查是否存在迭代回答（answer-eval-answerAgain结构）
      const evalStartMarker = "\n\n```eval\n";
      const evalEndMarker = "\n```";
      const iterationMarker = "\n\n---\n### 迭代改进后的回答\n";
      
      let finalAnswer = answerContent;
      
      // 如果存在迭代标记，说明是新的answer-eval-answerAgain结构
      if (answerContent.includes(iterationMarker)) {
        const iterationIndex = answerContent.indexOf(iterationMarker);
        // 提取迭代后的回答部分（从迭代标记后开始）
        finalAnswer = answerContent.substring(iterationIndex + iterationMarker.length);
        console.log("检测到迭代回答，提取迭代后的内容用于钉卡");
      } else if (answerContent.includes(evalStartMarker)) {
        // 如果有eval标记但没有迭代标记（可能是评估失败的情况），提取eval之前的内容
        const evalIndex = answerContent.indexOf(evalStartMarker);
        finalAnswer = answerContent.substring(0, evalIndex);
        console.log("检测到eval标记但无迭代回答，使用第一次回答内容");
      }

      // 移除 second-eval 部分（第二次深评内容）
      const secondEvalIndex = finalAnswer.indexOf("\n\n```second-eval");
      if (secondEvalIndex !== -1) {
        finalAnswer = finalAnswer.substring(0, secondEvalIndex);
        console.log("移除了 second-eval 部分");
      }
      
      qaTotalStr = "提问：" + questionContent + "\n回答：" + finalAnswer

      // 检查并移除 "### 末端红蓝深评" 及其后面的内容（针对主窗口综述的情况）
      const redBlueIndex = qaTotalStr.indexOf("\n\n---\n### 末端红蓝深评\n");
      if (redBlueIndex !== -1) {
        qaTotalStr = qaTotalStr.substring(0, redBlueIndex);
      }
      console.log("要生成卡片的问答对内容：", qaTotalStr)
      formData.append('content', qaTotalStr);
      formData.append('seed', this.chatList[index].seed);
      formData.append('status', this.summary);
      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', this.subSceneName);
      formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递

      let timeParamsStr = JSON.stringify(this.chatList[index].timeParams);
      formData.append('timeParams', timeParamsStr);

      // 添加置信度和腐烂度信息
      const confidenceScore = this.chatList[index].confidenceScore || 3.0;
      const rotScore = this.chatList[index].rotScore || 3.0;
      formData.append('confidence_score', confidenceScore);
      formData.append('rot_score', rotScore);
      console.log(`钉卡片 - 置信度: ${confidenceScore}, 腐烂度: ${rotScore}`);

      // 🔥 如果有勾选的卡片，将卡片ID列表传递给后端，用于设置新卡片的postIndex
      if (this.choosedCardIdList && this.choosedCardIdList.length > 0) {
        formData.append('choosedCardIdList', JSON.stringify(this.choosedCardIdList));
        console.log(`[钉卡片] 勾选的卡片ID列表: ${JSON.stringify(this.choosedCardIdList)}`);
      }

      // 🔥 传递生成此卡片时勾选的文档列表
      if (this.fileNameList && this.fileNameList.length > 0) {
        formData.append('file_list', JSON.stringify(this.fileNameList));
        console.log(`[钉卡片] 勾选的文档列表: ${JSON.stringify(this.fileNameList)}`);
      }

      // let formDataScore = new FormData()
      // formDataScore.append('username', localStorage.getItem('userId'));
      // formDataScore.append('content', qaTotalStr);

      // 🔥 问答钉卡时，立即滚动到CardGrid顶部显示等待卡片
      // 先触发滚动（同步执行），再显示等待卡片
      this.$emit('scrollToCardGridTop')
      // 确保滚动先执行
      this.$nextTick(() => {
        this.$emit('goCardGrid')
      })

      card_upload(formData).then(response => {
        if (response.error_num === 0) {
          let cardId = response.card_id

          // 半自动化添加记录 - 记录创建的卡片及cid
          this.$emit('pinCard', {
            question: qaTotalStr.split('\n回答：')[0].replace('提问：', ''),
            answer: qaTotalStr.split('\n回答：')[1],
            content: qaTotalStr,
            modelId: this.chatModelInfo.id,
            status: this.summary,
            seed: this.chatList[index].seed,
            timeParams: this.chatList[index].timeParams,
            sceneName: this.sceneName,
            subSceneName: this.subSceneName,
            keyTopics: this.keyTopics,
            created_card_id: cardId  // 添加创建的卡片ID
          });

          // formDataScore.append('cid', cardId);
          // 后端卡片更新完成后，更新到卡片窗口中
          // 🔥 传递新生成的卡片ID给mainPage，用于等待卡消失后滚动到新卡片
          this.$emit('cardUpdate', cardId);
          this.getModelEval(qaTotalStr, cardId);
          // 传递第二次综合评分（如果有）
          const secondEvalScore = this.chatList[index] ? this.chatList[index].secondEvalComprehensiveScore : null;
          console.log(`[钉卡片] 当前问答的第二次综合评分: ${secondEvalScore}`);
          this.getOurModelEval(qaTotalStr, cardId, -1, secondEvalScore);
          // card_score(formDataScore).then(response => {
          //   if (response.error_num === 0) {
          //     // 钉卡片同时保存QA数据用于评估反馈
          //     this.score.GPT4 = response.score;
          //     console.log("大模型打分：" + response.score);
          //     // 后端卡片浅评打分更新完成后，更新到操作流中
          //     this.$emit('cardOpeUpd', this.score.GPT4, qaTotalStr);
          //     this.databack();
          //     // 红蓝评测微调模型打分
          //     this.waitDecodedResult(response.card_id, qaTotalStr)
          //   } else {
          //     this.$message.error('卡片打分未成功！')
          //     console.log(response['message'])
          //   }
          // });
        } else {
          this.$message.error('卡片保存失败，请重试！')
          console.log(response['message'])
        }
      });

      // 阻止事件继续传播
      event.stopPropagation();
    },

    getModelEval(qaTotalStr, cardId) {
      let formDataScore = new FormData()
      formDataScore.append('username', localStorage.getItem('userId'));
      let originRealName = localStorage.getItem('originRealName') + localStorage.getItem('userId').replace(localStorage.getItem('realName'), '')
      formDataScore.append('originRealName', originRealName);
      formDataScore.append('content', qaTotalStr);
      formDataScore.append('cid', cardId);
      formDataScore.append('model_id', "1126");  // 对应claude-4-sonnet
      // formDataScore.append('model_id', this.chatModelInfo.id);

      // card_score(formDataScore).then(response => {
      //   if (response.error_num === 0) {
      //     // 钉卡片同时保存QA数据用于评估反馈
      //     this.score.GPT4 = response.score;
      //     console.log("大模型打分：" + response.score);
      //     // 后端卡片浅评打分更新完成后，更新到操作流中
      //     this.$emit('cardOpeUpd', this.score.GPT4, qaTotalStr);
      //     this.databack();
      //     // 红蓝评测微调模型打分
      //     // this.waitDecodedResult(response.card_id, qaTotalStr)
      //   } else {
      //     this.$message.error('卡片打分未成功！')
      //     console.log(response['message'])
      //   }
      // });
      let partialResults = '';
      get_model_eval(formDataScore).then(response => {
          const reader = response.body.getReader(); // 使用响应的ReadableStream来处理数据
          // 后端传回数据，显示
          const processStream = () => {
            const decoder = new TextDecoder('utf-8');
            reader.read().then(({done, value}) => {
              if (done) {
                console.log('Stream reading complete');
                let formData = new FormData();
                formData.append('content', partialResults);
                formData.append('cid', cardId);
                card_eval(formData).then(responseData => {
                  if (responseData.error_num === 0) {
                    this.$message.success('大模型模型打分保存成功！');
                    // 钉卡片同时保存QA数据用于评估反馈
                    this.score.GPT4 = responseData.score;
                    console.log("大模型打分：" + responseData.score);
                    // 后端卡片浅评打分更新完成后，更新到操作流中
                    this.$emit('cardOpeUpd', this.score.GPT4, qaTotalStr);
                    this.databack();
                    this.$emit('cardOpeUpdStreamOver');
                  } else {
                    this.$message.error('卡片保存成功，但大模型打分保存失败');
                  }
                  // this.$emit('cardUpdate', this.score.GPT4, qaTotalStr);
                });
                return;
              }
              const resp = decoder.decode(value);
              // console.log('Processed chunk:', resp);
              let responseData;
              // 使用正则表达式匹配和提取每个独立的 JSON 对象
              const jsonObjects = resp.match(/{[\s\S]*?}(?=\s*{|$)/g);
              if (jsonObjects) {
                jsonObjects.forEach(jsonObject => {
                  responseData = JSON.parse(jsonObject);
                  // 处理解析后的 JSON 数据
                  partialResults += responseData["content"];
                  this.$emit('cardOpeUpdStream', partialResults, cardId);
                });
              } else {
                console.error('No JSON objects found in the stream:', resp);
                this.$message.error('卡片打分未成功！');
              }
              // 继续读取下一块数据
              processStream();
            })
          };
          processStream();
                  }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
    },
    getOurModelEval(qaTotalStr, cardId, postIndex, secondEvalScore = null) {
      let formDataScene = new FormData();
      formDataScene.append('scene', localStorage.getItem('sceneName'));
      formDataScene.append('subScene', localStorage.getItem('subSceneName'));
      getSceneSummary(formDataScene).then(data => {
        if(data.error_num === 0) {
          let sceneName = localStorage.getItem('sceneName')
          let subSceneName = localStorage.getItem('subSceneName')
          console.log("场景子场景摘要获取成功：", sceneName, subSceneName, data.summary)
          let text = "目前的场景是：" + sceneName + "，子场景阶段是：" + subSceneName + "\n其摘要为：" + data.summary + "\n\n待评文本如下：\n" + qaTotalStr
          
          this.CardHLEvalStream(text, cardId, postIndex, qaTotalStr, secondEvalScore).then((result) => {
            console.log('Stream reading complete');
            if(this.choosedCardIdList.length === 1 && postIndex !== -1) {
                    this.processRelatedCards(postIndex, qaTotalStr);
            }
                  });
                } else {
          this.$message.error('场景子场景摘要获取失败');
          this.$emit('mergeEnd', this.nowTurnQuestion);
          if(this.choosedCardIdList.length === 1 && postIndex !== -1) {
            this.processRelatedCards(postIndex, qaTotalStr);
          }
        }
      })
    },
    async CardHLEvalStream(text, cardId, postIndex, qaTotalStr, secondEvalScore = null) {
      try {        
        // 调用流式处理函数
        // const result = await this.waitDecodedResultStreamForCard(text, cardId);
        const result = await this.waitDecodedResultStreamForCard(text, cardId, secondEvalScore);
        
        // 测试完成后提示
        if (result && result !== 'fail') {
          this.$message.success('卡片流式红蓝评测完成！');
          this.$emit('cardUpdateStreamOver');
          console.log('完整结果:', result);
        } else {
          this.$message.error('卡片流式评测失败');
          if(this.choosedCardIdList.length === 1 && postIndex !== -1) {
                    this.processRelatedCards(postIndex, qaTotalStr);
          }
        }
        return result
      } catch (error) {
        console.error('小模型流式过程中出错:', error);
        this.$message.error('小模型流式评测过程中出错: ' + error.message);
        if(this.choosedCardIdList.length === 1 && postIndex !== -1) {
                    this.processRelatedCards(postIndex, qaTotalStr);
        }
        const result = "小模型流式评测过程中出错"
        return result
      }
    },
    async waitDecodedResultStreamForCard(userText, cardId, secondEvalScore = null) {
      let completeResult = '';
      let partialResults = '';
      // userText += "\n\n以上文本来自阅读场景的S2:>>结构精读子场景阶段，这是一个xxx的场景，其中xxx summary"

      await modelHLStream(userText, (result, isDone) => {
        if (!isDone) {
          // 部分结果更新
          partialResults += result;
          this.$emit('cardUpdateStream', partialResults, cardId);
            } else {
          // 流结束，处理完整结果
          completeResult = result;
          // 添加替换 <think> 标签的代码
          if (completeResult.includes('<think>')) {
            completeResult = completeResult.replace(/<think>/g, '```');
          }
          if (completeResult.includes('</think>')) {
            completeResult = completeResult.replace(/<\/think>/g, '```');
          }

          // 如果有第二次综合评分，用它替代卡片深评分值
          let finalResult = completeResult;
          if (secondEvalScore !== null && secondEvalScore !== undefined) {
            console.log(`[卡片深评] 检测到第二次综合评分: ${secondEvalScore}，将替代卡片深评分值`);
            // 提取卡片深评的原始评分格式（可能是多种格式）
            // 替换为：第二次综合评分_紫_原始理由内容
            
            // 匹配各种评分格式并替换
            // 格式1: X.X_颜色_置信度X.X_腐烂度X.X_内容
            if (finalResult.match(/^(\d+\.?\d*)_([^_\s]+)_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)_/)) {
              finalResult = finalResult.replace(/^(\d+\.?\d*)_([^_\s]+)_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)_/, `${secondEvalScore}_紫_`);
              console.log(`[卡片深评] 替换完整格式评分: 原始 → ${secondEvalScore}_紫_`);
            }
            // 格式2: X.X_颜色_X.X_X.X（简化格式）
            else if (finalResult.match(/^(\d+\.?\d*)_([红蓝紫绿])_(\d+\.?\d*)_(\d+\.?\d*)/)) {
              finalResult = finalResult.replace(/^(\d+\.?\d*)_([红蓝紫绿])_(\d+\.?\d*)_(\d+\.?\d*)/, `${secondEvalScore}_紫_`);
              console.log(`[卡片深评] 替换简化格式评分: 原始 → ${secondEvalScore}_紫_`);
            }
            // 格式3: X.X_颜色_内容
            else if (finalResult.match(/^(\d+\.?\d*)_([^_\s]+)_/)) {
              finalResult = finalResult.replace(/^(\d+\.?\d*)_([^_\s]+)_/, `${secondEvalScore}_紫_`);
              console.log(`[卡片深评] 替换基础格式评分: 原始 → ${secondEvalScore}_紫_`);
            }
          }

          let formDataSFT = new FormData();
          // formDataSFT.append('content', completeResult);
          formDataSFT.append('content', finalResult);
          formDataSFT.append('cid', cardId);
          card_evalSFT(formDataSFT).then(responseSFT => {
            if (responseSFT.error_num === 0) {
              this.$message.success('红蓝微调评测模型打分保存成功！');
            } else {
              this.$message.error('卡片保存成功，但红蓝微调评测模型打分保存失败');
            }
            // 后端卡片更新（包括了浅评和深评打分）完成后，更新到卡片窗口中，但现在先更新窗口显示，后续再打分，分步进行
            this.$emit('cardUpdate');
            // this.$emit('cardUpdate', this.score.GPT4, qaTotalStr);
          });
        }
      });
      
      return completeResult;
    },

    // 修改为返回Promise的形式
    async waitDecodedResultPromise(cid, qaTotalStr) {
      try {
        // 等待 modelHL 异步函数执行完成，并将结果赋值给 decodedResult
        let decodedResult = await modelHL(qaTotalStr); 
        console.log("红蓝微调评测模型打分：", decodedResult);

        if (decodedResult === "fail") {
          this.$message.error('卡片保存成功，但红蓝微调评测模型打分失败');
          this.$emit('cardUpdate');
          // 返回一个失败状态，但仍然继续执行
          return Promise.resolve({
            success: false,
            message: '红蓝微调评测模型打分失败'
          });
        } else {
          let formDataSFT = new FormData();
          formDataSFT.append('content', decodedResult);
          formDataSFT.append('cid', cid);
          
          // 返回评分保存的 Promise
          return card_evalSFT(formDataSFT).then(responseSFT => {
            if (responseSFT.error_num === 0) {
              this.$message.success('卡片保存成功！');
              this.$emit('cardUpdate');
              return {
                success: true,
                message: '卡片评分保存成功'
              };
            } else {
              this.$message.error('卡片保存成功，但红蓝微调评测模型打分保存失败');
              this.$emit('cardUpdate');
              return {
                success: false,
                message: '红蓝微调评测模型打分保存失败'
              };
            }
          });
        }
      } catch (error) {
        console.error("红蓝微调评测模型打分出错:", error);
        this.$message.error('红蓝微调评测模型打分过程出错');
        this.$emit('cardUpdate');
        return Promise.reject(error);
      }
    },

    // 测试按钮的点击处理函数
    async QAEndHLEvalStream(text) {
      try {        
        // 调用流式处理函数
        const result = await this.waitDecodedResultStream(text);
        
        // 测试完成后提示
        if (result && result !== 'fail') {
          this.$message.success('末端红蓝评测完成！');
          console.log('完整结果:', result);
        } else {
          this.$message.error('流式测试失败');
        }
        return result
      } catch (error) {
        console.error('小模型流式过程中出错:', error);
        this.$message.error('小模型流式评测过程中出错: ' + error.message);
        const result = "小模型流式评测过程中出错"
        return result
      }
    },

    // 新增：窗口回答完成后的评估和迭代方法
    async windowAnswerWithEvalAndIteration(qaText, firstAnswer, timingInfo = {}, index = null) {
      if (index === null) index = this.chatList.length - 1; // 兼容历史调用

      // 🔥 新增：System1模式下跳过深评和迭代
      if (this.systemChoice === 1) {
        console.log('[System1] 快思考模式，跳过深评和迭代流程');
        // 标记回答已完成
        if (this.chatList[index]) {
          this.chatList[index].isComplete = true;
        }
        return;
      }
      
      // 在开始深评前，检查是否已被中断
      // 注意：这里使用wasInterrupted参数，而不是检查this.isInterrupted
      // 因为this.isInterrupted可能在异步操作中被外部修改
      if (this.isInterrupted) {
        console.log('[中断检测] 检测到中断状态，跳过深评和迭代');
        this.$message.info('已中断，跳过深评和迭代流程');
        return;
      }
      
      console.log(`[System2] 慢思考模式，开始深评和迭代流程`);
      console.log(`[第一次深评] 窗口${this.$attrs.windowId}准备开始深评流程`);

      let completeEvalResult = '';
      let partialEvalResults = '';
      const originalQuestion = this.cleanCodeBlocks(this.nowTurnQuestion);

      console.log("部分耗时信息", timingInfo)

      // 记录小模型深评的开始时间
      const evalStartTime = Date.now();
      let evalFirstTokenTime = null;

      // 添加评分信息存储
      let confidenceScore = 3.0;
      let rotScore = 3.0;

      // 第一步：流式获取小模型红蓝深评
      let rawEvalResult = '';  // 保存原始结果用于提取评分
      let comprehensiveScoreValue = null;  // 保存综合评分
      let onScoresExecuted = false;  // 标记onScores是否已执行
      let firstEvalWasInterrupted = false;  // 标记第一次深评是否被中断

      // 构建第一次深评的GCS输入（包含RAG样本和历史样本，与第二次深评类似）
      let qaTextForFirstEval = qaText + "\n\n";
      
      // 添加RAG文档样本（精简版）
      if (this.ragSampleText && this.ragSampleText.length > 0) {
        qaTextForFirstEval += `【参考文档摘录】\n${this.ragSampleText}\n\n`;
      }
      
      // 添加历史对话样本（精简版）
      if (this.historySampleText && this.historySampleText.length > 0) {
        qaTextForFirstEval += `【历史对话摘录】\n${this.historySampleText}\n\n`;
      }
      
      console.log(`第一次深评GCS输入总字数: ${qaTextForFirstEval.length}`);
      console.log(`第一次深评GCS输入前200字: ${qaTextForFirstEval.substring(0, 200)}`);

      // // ===== 第一次深评输入构建 =====
      
      // // 详细log：查看qaText的内容构成
      // console.log(`[第一次深评-输入分析] qaText总长度: ${qaText.length}`);
      // console.log(`[第一次深评-输入分析] qaText前500字:\n${qaText.substring(0, 500)}`);
      // console.log(`[第一次深评-输入分析] qaText后500字:\n${qaText.substring(Math.max(0, qaText.length - 500))}`);
      
      // // 检测qaText中各部分的长度
      // const sceneMarker = "目前的场景是：";
      // const summaryMarker = "其摘要为：";
      // const textMarker = "待评文本如下：";
      
      // if (qaText.includes(sceneMarker)) {
      //   const sceneStart = qaText.indexOf(sceneMarker);
      //   const summaryStart = qaText.indexOf(summaryMarker, sceneStart);
      //   const textStart = qaText.indexOf(textMarker, summaryStart);
        
      //   if (summaryStart > 0 && textStart > 0) {
      //     const scenePart = qaText.substring(sceneStart, summaryStart);
      //     const summaryPart = qaText.substring(summaryStart, textStart);
      //     const textPart = qaText.substring(textStart);
          
      //     console.log(`[第一次深评-输入分析] 场景部分长度: ${scenePart.length}, 内容: ${scenePart}`);
      //     console.log(`[第一次深评-输入分析] 摘要部分长度: ${summaryPart.length}, 内容前200字: ${summaryPart.substring(0, 200)}`);
      //     console.log(`[第一次深评-输入分析] 待评文本长度: ${textPart.length}, 内容前200字: ${textPart.substring(0, 200)}`);
      //   }
      // }
      
      // // 构建第一次深评的输入（精简版：仅问答，不包含场景摘要）
      // // 第一次深评应该聚焦在问答本身的质量，而不需要太多上下文
      // let qaTextForFirstEval = "";
      
      // // 从qaText中提取纯问答部分（去掉场景摘要）
      // if (qaText.includes(textMarker)) {
      //   const textStart = qaText.indexOf(textMarker);
      //   qaTextForFirstEval = qaText.substring(textStart + textMarker.length).trim();
      //   console.log(`[第一次深评-优化] 已去除场景摘要，仅保留问答部分，长度: ${qaTextForFirstEval.length}`);
      // } else {
      //   qaTextForFirstEval = qaText;
      //   console.log(`[第一次深评-优化] 未检测到标记，使用原qaText，长度: ${qaTextForFirstEval.length}`);
      // }
      
      // // 第一次深评：不添加RAG样本和历史样本，仅评估问答本身
      // // RAG和历史的作用是评估置信度和腐烂度，但第一次回答本身就是基于RAG和历史生成的
      // // 没必要再次传入，这会导致输入过长
      
      // console.log(`[第一次深评-最终输入] 总字数: ${qaTextForFirstEval.length}`);
      // console.log(`[第一次深评-最终输入] 前300字: ${qaTextForFirstEval.substring(0, 300)}`);

      const evalCallback = (result, isDone) => {
        // 检查是否已被中断
        if (this.isInterrupted) {
          console.log('[中断检测] 第一次深评过程中检测到中断，停止处理');
          firstEvalWasInterrupted = true;  // 标记已中断
          return;
        }

        if (!isDone) {
          // 如果onScores已执行，不再更新msg
          if (onScoresExecuted) {
            rawEvalResult += result;
            if (partialEvalResults === "") {
              evalFirstTokenTime = Date.now();
            }
            partialEvalResults += result;
            return;
          }

          // 部分结果更新 - 显示小模型评估
          rawEvalResult += result;

          if (partialEvalResults === "") {
            // result = "\n\n```eval\n" + result
            // 记录深评首token时间
            evalFirstTokenTime = Date.now();
          }
          // partialEvalResults += result;
          // 暂时不处理，等流结束时统一处理
          partialEvalResults += result;
          
          // 实时重排格式（理由在前 → 评分在前）
          const processedPartial = this.processEvalText(partialEvalResults, null);
          
          // // 更新显示
          // this.chatList[index].msg = firstAnswer + "\n\n```eval\n" + processedPartial;
          // 更新显示（实时也添加闭合标记，避免markdown渲染错误）
          this.chatList[index].msg = firstAnswer + "\n\n```eval\n" + processedPartial + "\n```";

          // 设置滚动标志，确保第一次深评流式输出时自动滚动
          this.shouldScroll = true;
          this.$nextTick(() => {
            this.scrollBottom();
          });
        } else {
          // // 流结束，立即添加闭合标记
          // const processedPartial = this.processEvalText(partialEvalResults, null);
          // this.chatList[index].msg = firstAnswer + "\n\n```eval\n" + processedPartial + "\n```";


          // 流结束 - 不要在这里更新msg，让onScores回调来处理最终的msg更新（包括综合评分替换和颜色纠正）
          console.log("[第一次深评] 流式输出完成，等待onScores处理最终msg更新");
          
          // 处理完整评估结果
          completeEvalResult = result;
          console.log("[第一次深评内容测试]", completeEvalResult);
          // // 结束eval代码块
          // this.chatList[index].msg = firstAnswer + partialEvalResults + "\n```";

          // // 提取评分并计算综合评分
          // const scores = this.extractScoresFromEval(rawEvalResult);
          
          // if (scores && scores.confidenceScore !== null && scores.rotScore !== null) {
          //   comprehensiveScoreValue = this.calculateComprehensiveScore(
          //     scores.redBlueScore, 
          //     scores.confidenceScore, 
          //     scores.rotScore
          //   );
          //   console.log(`第一次深评综合评分: ${comprehensiveScoreValue}`);
          // }
          
          // // 处理评估文本，根据权限处理置信度腐烂度
          // const processedEvalResult = this.processEvalText(rawEvalResult, comprehensiveScoreValue);
          
          // // 结束eval代码块
          // this.chatList[index].msg = firstAnswer + "\n\n```eval\n" + processedEvalResult + "\n```";
          
          // // 如果有综合评分，添加到msg开头（通过特殊标记，后面在显示时处理）
          // if (comprehensiveScoreValue !== null) {
          //   // 将综合评分信息存储到chatList项中
          //   this.chatList[index].evalComprehensiveScore = comprehensiveScoreValue;
          // }

          // 处理特殊标签（用于后续迭代）
          completeEvalResult = completeEvalResult.replace(/<\|end_G\|><\|start_C\|>/g, '分  ');
          completeEvalResult = completeEvalResult.replace(/<\|end_C\|><\|start_S\|>/g, '\n\n');
          completeEvalResult = completeEvalResult.replace(/<\|end_S\|><\|end_OUTPUT\|>/g, '');
          completeEvalResult = completeEvalResult.replace(/<\|end_A\|><\|end_OUTPUT\|>/g, '');
          completeEvalResult = completeEvalResult.replace('\\n', '\n');

          // 暂时显示原始结果，等待onScores处理后再更新
          console.log("第一次深评流式输出完成，等待onScores处理评分");
        }
      };
      
      evalCallback.onScores = (scores) => {
        // 标记onScores已执行，防止后续实时更新覆盖
        onScoresExecuted = true;
        console.log("[第一次深评] onScores开始执行，已设置标志防止实时更新覆盖");

        console.log(`[第一次深评] onScores被调用，收到评分:`, scores);
        console.log(`[第一次深评] chatList长度: ${this.chatList.length}`);
        
        const answerConfidence = scores.confidence_score || 3.0;
        const rotScoreModel = scores.rot_score || 3.0;
        const redBlueScore = scores.red_blue_score || 3.0;

        console.log(`[第一次深评] 提取的评分 - 红蓝: ${redBlueScore}, 置信: ${answerConfidence}, 腐烂: ${rotScoreModel}`);
        
        // 计算最终置信度：有文档时=文档置信度60% + 回答置信度40%，无文档时=回答置信度100%
        if (this.docConfidenceScore > 0) {
          confidenceScore = this.docConfidenceScore * 0.6 + answerConfidence * 0.4;
          confidenceScore = Math.round(confidenceScore * 10) / 10;
          console.log(`第一次深评-置信度: 文档${this.docConfidenceScore} * 0.6 + 回答${answerConfidence} * 0.4 = ${confidenceScore}`);
        } else {
          confidenceScore = answerConfidence;
          console.log(`第一次深评-置信度: ${confidenceScore} (仅回答)`);
        }
        
        // 计算最终腐烂度：60%确定性算法 + 40%小模型
        if (this.rotScoreAlgorithmic > 0) {
          rotScore = this.rotScoreAlgorithmic * 0.6 + rotScoreModel * 0.4;
          rotScore = Math.round(rotScore * 10) / 10;
          console.log(`第一次深评-腐烂度: 确定性${this.rotScoreAlgorithmic} * 0.6 + 小模型${rotScoreModel} * 0.4 = ${rotScore}`);
        } else {
          rotScore = rotScoreModel;
          console.log(`第一次深评-腐烂度: ${rotScore} (仅小模型)`);
        }
        
        // 计算综合评分
        comprehensiveScoreValue = this.calculateComprehensiveScore(
          redBlueScore,
          confidenceScore,
          rotScore
        );
        console.log(`第一次深评综合评分: ${comprehensiveScoreValue} (红蓝${redBlueScore} × 0.5 + 置信度${confidenceScore} × 0.3 + (5-腐烂度${rotScore}) × 0.2)`);
        
        // 存储综合评分
        this.chatList[index].evalComprehensiveScore = comprehensiveScoreValue;
        console.log(`[第一次深评] evalComprehensiveScore已存储: ${comprehensiveScoreValue}, 到chatList[${index}]`);
        console.log(`[第一次深评] 当前msg包含\`\`\`eval\`\`\`: ${this.chatList[index].msg.includes('\`\`\`eval')}`);
        console.log(`[第一次深评] 当前msg前200字: ${this.chatList[index].msg.substring(0, 200)}`);

        // 更新评估文本，使用综合评分替换（对无权限用户）
        // 更新评估文本，使用综合评分替换
        console.log(`[第一次深评] 准备调用processEvalText，rawEvalResult前100字: ${rawEvalResult.substring(0, 100)}`);
        console.log(`[第一次深评] 传入comprehensiveScoreValue: ${comprehensiveScoreValue}`);
        console.log(`[第一次深评] 当前用户权限canView: ${this.canViewConfidenceAndRot()}`);
        const processedEvalResult = this.processEvalText(rawEvalResult, comprehensiveScoreValue);
        console.log(`[第一次深评] processEvalText返回结果前100字: ${processedEvalResult.substring(0, 100)}`);
        const currentMsg = this.chatList[index].msg;
        let msgWithoutEval = currentMsg.replace(/\n\n```eval[\s\S]*$/, '');
        
        // 不再在msg中添加综合评分div，改为通过模板显示（使用item.evalComprehensiveScore）
        this.chatList[index].msg = msgWithoutEval + "\n\n```eval\n" + processedEvalResult + "\n```";
        console.log(`[第一次深评] msg更新完成，新msg前100字: ${this.chatList[index].msg.substring(0, 100)}`);
        
        // 设置滚动标志，确保评分更新后自动滚动
        this.shouldScroll = true;
        this.$nextTick(() => {
          this.scrollBottom();
        });

        // 存储到chatList
        if (this.chatList[index]) {
          this.chatList[index].confidenceScore = confidenceScore;
          this.chatList[index].rotScore = rotScore;
          console.log(`第一次深评已存储置信度: ${confidenceScore}, 腐烂度: ${rotScore}`);
        }

        // 在用时信息下方添加质量评估信息（仅对有权限的用户显示）
        console.log(`[第一次深评] canViewConfidenceAndRot(): ${this.canViewConfidenceAndRot()}`);
        if (this.canViewConfidenceAndRot()) {
          const currentTimingInfo = this.chatList[index].timingInfo || '';
          console.log(`[第一次深评] 当前timingInfo长度: ${currentTimingInfo.length}`);
          console.log(`[第一次深评] 当前timingInfo前100字: ${currentTimingInfo.substring(0, 100)}`);

          const qualityInfo = `\n<div style="color: #666; font-size: 12px; margin-top: 8px; padding-top: 5px;">
📊 质量评估：
• 置信度：${confidenceScore.toFixed(1)}/5.0 ${this.getConfidenceLevelText(confidenceScore)}
• 腐烂度：${rotScore.toFixed(1)}/5.0 ${this.getRotLevelText(rotScore)} (越低越好)
</div>`;
          
          // 在</div>前插入质量信息
          const updatedTimingInfo = currentTimingInfo.replace('</div>', qualityInfo + '</div>');
          this.chatList[index].timingInfo = updatedTimingInfo;
          console.log(`第一次深评质量评估已添加: 置信度${confidenceScore.toFixed(1)}, 腐烂度${rotScore.toFixed(1)}`);
          console.log(`[第一次深评] 更新后timingInfo长度: ${updatedTimingInfo.length}`);
        } else {
          console.log(`[第一次深评] 用户无权限查看质量评估`);
        }
      };
      
      // // 第一轮回答后的深评：仅红蓝评分，暂不包含置信度腐烂度，不包含RAG内容，GCS简单理由+D激发框架
      // await modelHLStream(qaText, evalCallback, '', true, 'simple_reason', 'inspire_framework');
      // 第一轮回答后的深评：包含置信度+腐烂度（与第二次一致），GCS详细理由+D激发框架
      console.log('[第一次深评] 开始调用modelHLStream');
      console.log('[第一次深评] evalCallback.onScores存在吗:', typeof evalCallback.onScores);

      // 开始第一次深评流式输出 - 启用中断按钮
      this.startStreaming();

      // 创建中断控制器
      this.evalAbortController = new AbortController();

      try {
        await modelHLStream(qaTextForFirstEval, evalCallback, 'Confidence&Rottenness', true, 'detailed_reason', 'inspire_framework', null, this.evalAbortController.signal);
        console.log('[第一次深评] modelHLStream调用完成');
      } catch (error) {
        if (error.name === 'AbortError') {
          console.log('[第一次深评] 请求已被中断');
          firstEvalWasInterrupted = true;
        } else {
          console.error('[第一次深评] 请求失败:', error);
        }
      } finally {
        // 结束第一次深评流式输出 - 禁用中断按钮
        this.endStreaming();
      }

      // 计算深评的总时间和首token时间
      const evalEndTime = Date.now();
      const evalTotalTime = ((evalEndTime - evalStartTime) / 1000).toFixed(2);
      const evalFirstTokenTimeValue = evalFirstTokenTime ? ((evalFirstTokenTime - evalStartTime) / 1000).toFixed(2) : 'N/A';
      console.log(`小模型深评用时 - 总时间: ${evalTotalTime}s, 首token: ${evalFirstTokenTimeValue}s`);

      // 第二步：基于小模型评估，让大模型迭代改进
      // 检查第一次深评是否被中断
      if (firstEvalWasInterrupted) {
        console.log('[中断检测] 第一次深评已被中断，跳过迭代改进');
        this.$message.info('已中断，跳过迭代改进流程');
        // 在消息末尾添加中断提示
        this.chatList[index].msg += '\n\n---\n\n⚠️ 深度评估已被用户中断，跳过迭代改进';
        return;
      }

      console.log("准备基于红蓝深评进行大模型迭代改进");
      this.$message.success('小模型评估完成，准备大模型迭代改进');

      // 更新计时信息
      timingInfo.evalTotal = evalTotalTime;
      timingInfo.evalFirstToken = evalFirstTokenTimeValue;

      // 质量评估信息将在onScores回调中显示
      
      // 构造迭代prompt
//       const iterationPrompt = `\n\n请你仔细阅读上述红蓝深评内容，根据其中的建议和改进点（特别是【思维架构】中的思考策略例如用CoT一步一步推理和【激发引导】中的建议方向），对你之前的回答进行修正和改进。要求（不分先后，缺一不可）：
// 1. 保持原回答的核心正确观点和结构(事实性结论需要你亲自再判断，深评得分高低代表文本质量而非事实对错)
// 2. 针对性地改进评估中指出的不足之处
// 3. 如果原回答内容包含具体细节，你应该直接保留或进行浓缩精炼而非去除，不能因为修正而让回答变“虚”
// 4. 提升回答的质量、深度和针对性，但一定要注意原问题的要求是什么，切忌脱离问题来修改回答
// 5. 确保改进后的内容更符合场景要求
// 6. 注意改进不是篇幅变多，而是最终回答更精炼的同时更精准（修正后回答的篇幅不能多于原回答）

// 例如下面的例子，严重违反要求中第1、3点，因包含大量比喻类比而发虚，丢失所有细节（你可以用类比推理思考，但不能直接出现在给用户的最终回答中）：
// 修改前：ARC（抽象与推理语料库）是评估AI通用智能的基准，它借视觉推理任务识别并应用抽象模式，以人类核心先验为前提测流体智能、抽象推理与泛化力，区分真智能与浅层模式匹配。
// 修改后：Arc是一种超越传统语言模型的认知镜像系统，它不仅能像江河般流淌于知识的表面，更能溯流而上探寻思维的源头，通过融合抽象推理与知识先验，实现从简单记忆到真正理解的智能跃迁。

// 请直接输出改进后的完整回答，不要重复原回答内容。`;



//       const iterationPrompt = `\n\n## 深评解读与智能迭代指南

// ### 一、深评信息筛选原则
// 请先对深评内容进行**价值密度分析**，识别并提取：
// - **高价值信息**：与问题直接相关的具体改进建议、字数和视角建议、推理方法指导（如CoT）、关键逻辑点提示
// - **中价值信息**：可能激发新思路的观点，即使表述模糊
// - **低价值信息**：套话、文言修辞、无关类比等，直接忽略

// ### 二、迭代决策框架
// 根据原回答质量进行**差异化迭代策略**：

// **情况A - 原回答存在明确错误**：
// - 优先修正事实性/逻辑性错误（深评分数≠事实正确性）
// - 保留正确部分，重构错误部分
// - 允许较大幅度调整结构

// **情况B - 原回答基本正确但平庸**：
// - 寻找"认知突破点"：加入让用户意外但合理的新视角
// - 深化核心论点，而非简单增加内容
// - 考虑增加亮点以提升逻辑冲击力（让人觉得“我怎么没想到，绝妙的观点！”）

// **情况C - 原回答已较优秀**：
// - 精准微调：仅改进深评中确实有价值的点
// - 重点在于精炼表达和强化亮点

// ### 三、创新激发机制
// 在不违背事实的前提下，尝试以下至少一种提升：
// 1. **认知跃迁**：找到问题背后更深层的原理或规律
// 2. **视角切换**：从意想不到但合理的角度重新解释
// 3. **细节升华**：将平凡细节提炼成洞察性观点

// **关键原则**：创新必须建立在具体性基础上。可以用类比推理辅助思考，但最终回答必须回归具体事实和细节。

// ### 四、质量控制标准
// 迭代后的回答必须同时满足：
// - **精准度**：每句话都直击要害，删除所有"正确的废话"
// - **具体性**：保留或精炼原回答中的重要细节、数据、专有名词等具体信息
// - **密度感**：信息密度明显高于原回答
// - **新颖性**：至少包含一个"原来还能这样理解"的亮点
// - **相关性**：始终紧扣原问题的核心需求，不能为了创新而偏离主题
// - **篇幅量**：如果深评明确指出字数则尽量完成，未指出则字数≤原回答×0.9（强制精炼）

// ### 五、典型错误警示

// **避免"发虚"陷阱**——以下是错误示例：
// - **修改前**（具体）：ARC（抽象与推理语料库）是评估AI通用智能的基准，它借视觉推理任务识别并应用抽象模式，以人类核心先验为前提测流体智能、抽象推理与泛化力，区分真智能与浅层模式匹配。
// - **修改后**（发虚）：Arc是一种超越传统语言模型的认知镜像系统，它不仅能像江河般流淌于知识的表面，更能溯流而上探寻思维的源头，通过融合抽象推理与知识先验，实现从简单记忆到真正理解的智能跃迁。

// **问题分析**：修改后版本用大量比喻替代了具体信息，丢失了"视觉推理任务"、"流体智能"等关键细节。

// ### 六、执行检查清单
// - 是否正确理解了问题的本质需求？
// - 是否识别并修正了所有事实性错误？
// - 是否从深评中提取了真正有价值的建议？
// - 是否保留了原回答中的重要具体细节？
// - 是否产生了至少一个创新性改进？
// - 是否做到了更精炼而非更冗长？
// - 是否避免了空洞的比喻和类比？

// **最终要求**：请基于以上框架，直接输出改进后的完整回答，不要重复原回答内容。记住：目标不是"修改"，而是"进化"——让回答在保持具体性的基础上从平凡走向卓越。`;
      


//       const iterationPrompt = `\n\n## 从"对"到"妙"——迭代升华指南

// 【核心目标】不仅要正确，更要卓越；不仅要回答，更要启发。让第二次深评评分明显提升（+0.5至+1.5分），从平庸到卓越。

// 【深评解读】
// 1. 红蓝评分：≤2.0分大幅重构，2.0-3.5分注入"妙点"，≥3.5分精准提升亮点
// 2. **深评具体建议解读与执行**：
//    深评中此三大模块对应执行要求，是你本次迭代第二次回答要参考的重要指南！：
   
//    - 【核心诊断】：改进总方向，新回答必须完全解决指出的关键问题
   
//    - 【思维突破】：
//      * 关键路径 → 必须覆盖的1-2个核心维度
//      * 具体建议 → 可直接执行的方法必须体现
//      * 隐藏维度 → 原回答遗漏的角度必须补充
   
//    - 【激发要点】：
//      * 策略执行：CoT→展现推理过程 | SoT→叙事化重构 | ToT→多角度权衡 | GoT→网状思维
//      * 视角牵引：如明确"以XX视角重构"，这是核心突破点，必须严格执行
//      * 字数控制：明确字数要求必须严格遵守（±10%），但优先考虑用户原问题的要求，例如是润色类问题，则应该保持篇幅基本不变
//      * 角色定位：如提到"专家/导师/协作者/学生/等等"语境转换，必须切换对应语气

// 【四层递进策略】贴合问题→符合细节→契合场景→视角独到，确保每一层都突破，不能只突破一层，要全面突破。

// ▸ 基础层：不跑题，逻辑清晰，修正错误
// ▸ 进阶层：补充细节，原回答可能分多点，改进回答时找出一个具有原子性的统领点，由此出击穿原有各点并细化1-2个重要点
// ▸ 高阶层：更契合场景/子场景语境，视角递进（表层→机制→本质）或语境转换（注意深评建议里的语境转换建议）
// ▸ 卓越层（核心！）：独到视角（让人"眼前一亮"的反常识切入点）+"妙"的思考（意想不到但合理，揭示深层逻辑）+跨领域类比但落地具体（如"自注意力类似人类阅读时的重点标记"）+本质洞察（如"注意力机制本质是信息的动态加权筛选"）

// **判断标准**：读完后让人觉得"原来还能这样理解！"、"这个角度真绝！"

// 【具体执行四步法】
// 1. 诊断层次：原回答在哪层？最大缺陷？（事实错误/平庸无亮点/偏离场景/太虚无细节）
// 2. 提升路线：基础→进阶，进阶→高阶，高阶→卓越
// 3. 执行改进：保留精华（原回答中的正确具体信息、分点结构）+删冗余（删除冗余和"正确的废话"）+注亮点（至少1个独到视角或"妙"的观点）+优结构（不能大量改变原回答结构，而是要精进、找出原子性的统领点，由此击穿原有各点并细化1-2个重要点，并确保内容上符合深评建议的三大模块要求）
// 4. 质量自检：信息密度高？有亮点？符合字数？避免发虚？

// 【改进案例】
// 原（2.5分）：Transformer是深度学习模型，用于NLP，效果好。
// 新（4.0分）：Transformer通过自注意力并行计算解决RNN长距离依赖。WMT翻译BLEU升至28.4（+2.0），训练时间缩短1/3。本质是"全局视野"替代"局部递进"范式转变。
// → 补充数据+揭示机制+本质洞察，评分+1.5 ✓

// 【禁止错误】
// × 发虚：可以比喻类比，但不能直接替代具体信息或丢失细节，避免“心灵鸡汤”式回答，一定要让用户看了觉得对自己有可操作性价值
// × 跑题：为了创新而偏离用户原问题核心，添加与问题完全无关的内容
// × 冗长：堆砌而非提炼，违背简单凝练而深刻易懂的原则
// × 假创新：只是换个说法，没有新观点，用复杂表述掩盖平庸内容

// 【检查清单】修正错误？补充细节？强化逻辑？契合场景？独到视角？删冗余？符合字数？避免发虚？

// **记住**：
// - 目标是让第二次深评评分**明显提升**
// - 关键是**第四层卓越层**的突破——不只要"对"，更要"妙"，深刻理解而简单表述，例如都江堰工程用“鱼嘴”、“飞沙堰”、“宝瓶口”等自然地涵盖浓缩了这个巨大水利工程的精髓。
// - 核心是**独到视角+具体细节**的完美结合，必须基于原回答结构升维、击穿，而不是大量改变原有分点结构
// - 底线是**绝不能心灵鸡汤式发虚**，保持或增强具体性

// 请直接输出改进后的完整回答。请开始吧，相信你一定能做到！`;



//       const iterationPrompt = `\n\n## 从"对"到"妙"——击穿真实目标的迭代升华

// ### 一、理解深评框架（必读）

// 你刚刚收到的红蓝深评包含了关键的认知框架，请仔细理解：

// **1. 真实目标识别**
// - 深评已经帮你识别了用户问题背后的**真实目标**
// - 三问定位：底线（最坏能接受什么）、愿景（最好能做到什么）、着力点（现在具体做什么）
// - **你的任务**：击穿这个真实目标，而不只是回答表面问题

// **2. 四色语境层次**
// - 深评已经诊断了当前回答在哪个层次（红/蓝/紫/绿）
// - 🔴红色=业务语境，🔵蓝色=技术方法，🟣紫色=场景框架，🟢绿色=简单深刻
// - **你的任务**：按深评指引，从当前层次升维（通常是从红蓝升到紫绿）

// **3. DMT层次结构**
// - 深评已经诊断了你原回答的D/M/T结构
// - D=具体内容（70%），M=方法原则（20%），T=本质统领（10%）
// - **你的任务**：不是改D的内容，而是找到M和T，让D基于M和T自然拔高

// **4. 简单而深刻的目标**
// - 深评可能给出了"绿色语言"的提示（类似"都江堰"的简单表达）
// - **你的任务**：找到统领性的简单表达，用2-4个简单词汇击穿整个回答的精髓

// ---

// ### 二、三问锁定法（核心指导）

// 在开始改进前，先用"三问"锁定你的改进方向：

// **问1：底线是什么**（守住底线）
// - 原回答有没有跑题？有没有事实错误？
// - **改进底线**：不跑题、不出错、逻辑清晰
// - 如果已守住底线→专注提升；如果未守住→优先修正

// **问2：愿景是什么**（追求卓越）
// - 这个回答做到极致会是什么样？
// - **改进愿景**：击穿真实目标、升维到紫绿、达到简单深刻
// - 深评中的"真实目标"就是你的愿景，必须击穿它！

// **问3：着力点是什么**（即刻行动）
// - 深评中的"关键路径"和"具体建议"就是你的着力点
// - **改进着力点**：按深评的3大模块执行
//   * 核心诊断→改进总方向
//   * 思维突破→关键路径+具体建议+隐藏维度
//   * 激发要点→视角牵引+策略+字数控制

// ---

// ### 三、四色升维执行法（认知跃迁）

// **步骤1：识别当前层次**
// - 深评已告诉你当前在哪（通常是红蓝）
// - 🔴红色：仅陈述了业务问题
// - 🔵蓝色：给出了技术方法
// - 🟣紫色：提炼了思维框架
// - 🟢绿色：达到简单深刻

// **步骤2：执行升维路径**

// **如果当前在红蓝层→升维到紫色**：
// 1. 从多个具体点（D）中找**共性**
// 2. 抽象成**方法论/原则**（M层）
// 3. 形成**思维框架**（紫色场景语言）
// 4. 例：从"注意力计算公式"（红）+"多头机制"（蓝）→提炼出"动态加权筛选原则"（紫）

// **如果已在紫色层→升维到绿色**：
// 1. 从方法论（M）中找**本质**
// 2. 提炼成**统领性表达**（T层）
// 3. 用**简单自然的词汇**表达（绿色自然语言）
// 4. 例：从"动态加权筛选"（紫）→升华为"注意力=动态聚焦镜"（绿）

// **关键原则**：
// - 升维不是"压缩"，而是"提炼本质"
// - 升维不是"丢失细节"，而是"找到统领点"
// - 升维后，原有的D内容会因为有了M和T的指引而自然拔高

// ---

// ### 四、DMT拔高执行法（结构升维）

// **步骤1：理解深评的DMT诊断**
// - 深评已告诉你：D是什么、M应该是什么、T应该是什么
// - 认真理解M和T的定义，它们是拔高的关键

// **步骤2：基于M和T改写D**

// **不要这样改**（错误）：
// - 删除D的具体内容
// - 完全重写D
// - 大量改变原有结构

// **应该这样改**（正确）：
// 1. **保留D的精华**：原回答中正确、具体的内容保留
// 2. **补充M层**：在D的基础上，补充方法论/原则（如深评建议的M）
// 3. **提炼T层**：找到一个统领性原子点（如深评建议的T）
// 4. **让D指向M，M指向T**：形成"T统领→M承接→D落实"的同频共振结构

// **例子**：
// 原回答（仅D）：
// Transformer用自注意力机制，可以并行计算，比RNN快。

// 改进后（DMT同频共振）：
// Transformer的本质是"全局视野替代局部递进"的范式转变（T层）。
// 它通过"动态加权筛选"原则（M层），
// 让模型同时关注序列中所有位置，计算任意两点间的关联（D层-机制）。
// 相比RNN的逐步递进，并行计算使训练速度提升3倍，
// WMT翻译BLEU从26.4升至28.4（D层-数据）。

// ---

// ### 五、寻找绿色语言（简单深刻）

// **目标**：找到类似"都江堰"的简单表达，用2-4个简单词汇击穿回答精髓

// **方法**：
// 1. **从D找共性**：原回答讲了哪些具体点？它们的共性是什么？
// 2. **抽象成M**：这个共性背后的方法/原则是什么？
// 3. **升华为T**：这个方法/原则的本质是什么？
// 4. **用简单词汇表达T**：能否用日常词汇（而非术语）来表达这个本质？

// **例子参考**：
// - 都江堰："鱼嘴·飞沙堰·宝瓶口"（3个简单词涵盖水利系统精髓）
// - 注意力机制："动态聚焦镜"（简单比喻，深刻本质）
// - Transformer："全局视野替代局部递进"（对比式本质洞察）
// - 真实目标："指南针→透镜→水电站→种子"（4层生命力递进）

// **关键**：
// - ✅ 简单：用日常词汇，易于理解
// - ✅ 深刻：击中本质，涵盖精髓
// - ✅ 具体：不是空洞比喻，要能指导原有的D
// - ❌ 避免：玄学化、鸡汤化、过度比喻而丢失具体性

// ---

// ### 六、四层递进策略（质量跃迁）

// **▸ 基础层**（守住底线）
// - 不跑题：紧扣原问题和真实目标
// - 逻辑清晰：因果/对比/递进明确
// - 修正错误：事实准确、推理正确

// **▸ 进阶层**（符合细节）
// - 补充细节：数据/案例/概念（2-3个精准的，而非大量堆砌）
// - 找统领点：从多个分点中找1个原子性统领点（M或T层）
// - 击穿分点：用统领点串联和拔高原有各点

// **▸ 高阶层**（契合场景）
// - 契合场景：符合场景/子场景语境要求
// - 视角递进：从表层→机制→本质
// - 语境转换：按深评建议转换语气和角色

// **▸ 卓越层**（视角独到）
// - 独到视角：让人"眼前一亮"的切入点（反常识/跨领域）
// - "妙"的思考：意想不到但合理，揭示深层逻辑
// - 简单深刻：找到"绿色语言"，简单词汇涵盖复杂精髓
// - 本质洞察：击穿本质，不只是描述现象

// **判断标准**：读完后让人觉得"原来还能这样理解！"、"这个角度真绝！"

// ---

// ### 七、深评三大模块执行指南

// 深评通常包含以下模块，**必须严格执行**：

// **1. 核心诊断/真实目标识别**
// - 这是改进的**总方向**
// - 新回答必须完全解决指出的关键问题
// - 必须击穿识别出的"真实目标"

// **2. 思维突破/四色语境/DMT诊断**
// - **关键路径**：必须覆盖的1-2个核心维度
// - **具体建议**：可直接执行的方法必须体现（补充什么/提炼什么/转换什么）
// - **隐藏维度**：原回答遗漏的角度必须补充
// - **升维路径**：按四色/DMT指引升维

// **3. 激发要点/视角与策略**
// - **策略执行**：CoT→展现推理过程 | ToT→多角度权衡 | GoT→网状思维
// - **视角牵引**：如明确"以XX视角重构"，这是核心突破点，必须严格执行
// - **字数控制**：明确字数要求必须遵守（±10%），但优先考虑原问题要求
// - **角色定位**：如提到语境转换，必须切换对应语气

// ---

// ### 八、禁止错误（关键底线）

// **❌ 发虚（最严重）**
// - 不要用大量比喻替代具体信息
// - 不要丢失原回答中的数据/案例/细节
// - 不要变成"心灵鸡汤"式空洞回答
// - ✅ 可以用比喻帮助理解，但必须保留具体性

// **❌ 跑题（致命错误）**
// - 不要为了创新而偏离原问题核心
// - 不要添加与问题完全无关的内容
// - 必须击穿"真实目标"，而非表面问题

// **❌ 冗长（效率问题）**
// - 不要堆砌内容，要提炼精髓
// - 遵循"简单而深刻"原则
// - 如深评有字数要求，严格遵守

// **❌ 假创新（质量问题）**
// - 不要只是换个说法，没有新观点
// - 不要用复杂表述掩盖平庸内容
// - 必须有实质性的认知升维

// ---

// ### 九、检查清单（自我验证）

// 在输出前，请自查以下8项：

// 1. **修正错误**：事实错误、逻辑错误是否已修正？
// 2. **击穿目标**：是否击穿了深评识别的"真实目标"？
// 3. **补充细节**：是否补充了精准的数据/案例（而非堆砌）？
// 4. **强化逻辑**：因果/对比/递进是否更清晰？
// 5. **契合场景**：是否符合场景/子场景语境？
// 6. **升维成功**：是否从红蓝升维到紫绿？DMT是否同频共振？
// 7. **独到视角**：是否有让人"眼前一亮"的切入点？
// 8. **简单深刻**：是否找到了"绿色语言"的简单表达？

// **如果8项都✅ → 你的改进是成功的！**
// **如果有❌ → 再次审视深评，看哪里没做到位**

// ---

// ### 十、改进案例（对比学习）

// **原回答（2.5分）**：
// Transformer是一种深度学习模型，主要用于NLP任务，效果很好。
// 它使用注意力机制，可以并行计算，比RNN快很多。

// **分析**：
// - 真实目标：用户想理解Transformer的本质，而非仅了解定义
// - 四色层次：当前在红色（业务定义）
// - DMT结构：D有（定义、用途），M缺（无方法），T缺（无本质）
// - 问题：空泛、无细节、无深度

// **改进后（4.0分）**：
// Transformer本质是"全局视野替代局部递进"的范式转变（T层-绿色）。

// 它通过"动态加权筛选"（M层-紫色），让模型同时关注序列所有位置，
// 计算任意两点间的关联。传统RNN必须逐步处理，无法并行，
// 且长距离依赖会衰减。Transformer的自注意力机制解决了这两个问题。

// 在WMT翻译任务中，BLEU从26.4升至28.4（+2.0），训练时间缩短1/3。
// 更重要的是，它开创了"预训练+微调"范式，
// 催生了BERT、GPT等模型，成为NLP的新基石（D层-具体）。

// 简单说，Transformer就像从"望远镜"（RNN的逐步扫视）
// 升级到"卫星俯瞰"（全局视野），看得更全、更准、更快（绿色语言）。

// **改进分析**：
// - 击穿真实目标：理解了本质（范式转变）
// - 四色升维：从红色升到紫色（动态加权）和绿色（望远镜→卫星）
// - DMT同频：T明确（范式转变），M清晰（动态加权），D充实（数据+影响）
// - 简单深刻：用"望远镜vs卫星"的简单比喻击穿本质
// - 补充细节：BLEU数据、对比RNN、影响范围
// - 评分提升：从2.5分→4.0分（+1.5分）✓

// ---

// ### 核心要点（必记）

// **记住3个"不"**：
// 1. **不推翻重写**：在原有基础上拔高，保留精华
// 2. **不只是"对"**：要追求"妙"，简单而深刻
// 3. **不停留在红蓝**：要升维到紫绿，达到"都江堰"式的简单表达

// **记住3个"要"**：
// 1. **要击穿真实目标**：理解用户深层需求，而非表面问题
// 2. **要建立DMT结构**：找到M（方法）和T（本质），让D（具体）拔高
// 3. **要找到绿色语言**：用2-4个简单词汇涵盖回答精髓

// **记住3个"层次"**：
// - **底线层**（三问之一）：不跑题、不出错、逻辑清晰
// - **质量层**（四层递进）：基础→进阶→高阶→卓越
// - **认知层**（四色升维）：红蓝→紫→绿

// **最终目标**：
// 让第二次深评评分**明显提升**（+0.5至+1.5分），
// 让用户感受到"这个工具怎么这么懂我！"、"原来还能这样思考！"

// ---

// 请直接输出改进后的完整回答。开始吧，相信你一定能做到！
// `;

      // const iterationMessage = `原问题：\n${originalQuestion}\n\n第一次回答：\n${firstAnswer}\n\n红蓝深评：\n${completeEvalResult}${iterationPrompt}`;
      let cleanedAnswer = this.cleanCodeBlocks(firstAnswer)
      let iterationMessage = `原问题：\n${originalQuestion}\n\n第一次原回答：\n${cleanedAnswer}\n\n红蓝深评：\n${completeEvalResult}`;
      
      // 如果有RAG文档，添加到迭代消息中
      if (this.ragSampleText && this.ragSampleText.length > 0) {
        iterationMessage += `\n\n【参考文档摘录】\n${this.ragSampleText}`;
        console.log(`迭代回答包含RAG样本文档，字数: ${this.ragSampleText.length}`);
      }
      
      iterationMessage += iterationPrompt;

      // 调用大模型进行迭代（传递originalQuestion供第二次深评使用）
      await this.performIterationAnswer(iterationMessage, originalQuestion, timingInfo, index);
    },

    // 新增：执行迭代回答
    async performIterationAnswer(message, originalQuestion, timingInfo = {}, index = null) {
      if (index === null) index = this.chatList.length - 1; // 兼容历史调用
      let username = localStorage.getItem('userId');
      let originRealName = localStorage.getItem('originRealName') + localStorage.getItem('userId').replace(localStorage.getItem('realName'), '');
      
      let formData = new FormData();
      formData.append('username', username);
      formData.append('originRealName', originRealName);
      formData.append('model_id', this.chatModelInfo.id);
      formData.append('message', message);
      formData.append('filenamelist', []);
      formData.append('summary', this.summary);
      formData.append('leftSelectList', []);
      formData.append('rightSelectList', []);
      formData.append('windowId', this.$attrs.windowId);
      formData.append('socraticBoundMessage', originalQuestion);
      formData.append('mode', 'iteration');

      // 添加必要的参数
      let portraitStates = {
        0: false, 1: false, 2: false, 3: false, 4: false, 5: false, 6: false
      };
      let modelIndex = this.idToIndex(this.chatModelInfo.id);
      portraitStates[modelIndex] = true;
      formData.append('modelStates', JSON.stringify(portraitStates));

      formData.append('isHistoryUsed', false);
      formData.append('isSummaryUsed', false);
      formData.append('rounds', this.rounds);
      formData.append('realName', localStorage.getItem('realName'));
      formData.append('userbookName', localStorage.getItem('userId'));
      formData.append('sceneName', localStorage.getItem('sceneName'));

      // 添加seed参数
      let seed = localStorage.getItem('seed');
      let seednumber = 0;
      if (seed === 'topic') { seednumber = 1; }
      else if (seed === 'question') { seednumber = 2; }
      else { seednumber = 0; }
      formData.append('seed', seednumber);
      
      let paramFormData = new FormData();
      const runtime_params = modelManager.getHyperParamsDictionary();
      let paramString = JSON.stringify(runtime_params);
      paramFormData.append('params', paramString);
      paramFormData.append('modelID', this.chatModelInfo.id);
      paramFormData.append('username', username);
      paramFormData.append('windowId', this.$attrs.windowId);
      paramFormData.append('message', message);
      paramFormData.append('filenamelist', []);
      paramFormData.append('rightSelectList', []);
      paramFormData.append('isHistoryUsed', false);
      paramFormData.append('rounds', this.rounds);
      paramFormData.append('originRealName', originRealName);
      paramFormData.append('choosedCardIdList', []);
      this.appendCrossNotebookParams(paramFormData);
      paramFormData.append('mode', 'iteration');
      paramFormData.append('socraticBoundMessage', originalQuestion);
      // paramFormData.append('mode', 'normal');

      let iterationAnswer = "";

      // 记录迭代回答的开始时间
      const iterationStartTime = Date.now();
      let iterationFirstTokenTime = null;
      
      // 执行迭代请求
      try {
        await chat_sendParams(paramFormData);
        const response = await chat_send(this.chatModelInfo.name, formData, this.$attrs.windowId);
        const reader = response.body.getReader();
        const decoder = new TextDecoder('utf-8');
        
        // 在eval代码块后添加迭代回答的标记
        this.chatList[index].msg += "\n\n---\n### 迭代改进后的回答\n";

        // 开始流式输出，显示中断按钮
        this.startStreaming();

        // 用于保存中断状态（在循环外部）
        let iterationWasInterrupted = false;
        
        while (true) {
          // 检查是否已被中断
          if (this.isInterrupted) {
            console.log('[中断检测] 迭代改进过程中检测到中断，停止处理');
            this.$message.info('已中断，停止迭代改进');
            // 在消息末尾添加中断提示
            this.chatList[index].msg += '\n\n---\n\n⚠️ 迭代改进已被用户中断</div>';
            iterationWasInterrupted = true; // 保存中断状态
            this.endStreaming(); // 中断时隐藏中断按钮
            break;
          }

          const {done, value} = await reader.read();
          if (done) {
            console.log('Iteration answer complete');
            this.endStreaming(); // 迭代完成，隐藏中断按钮
            // 保存迭代后的完整答案到data属性，供钉卡使用
            this.chatList[index].iterationAnswer = iterationAnswer;
            break;
          }
          
          const resp = decoder.decode(value);
          const jsonObjects = resp.match(/{[\s\S]*?}(?=\s*{|$)/g);
          
          if (jsonObjects) {
            jsonObjects.forEach(jsonObject => {
              // const responseData = JSON.parse(jsonObject);
              let responseData;
              try {
                responseData = JSON.parse(jsonObject);
              } catch (parseError) {
                // 🔥 流式传输中可能遇到不完整的 JSON，跳过并继续处理下一个
                console.warn('[迭代解析] 跳过无效的 JSON 片段:', parseError.message, 'JSON片段:', jsonObject.substring(0, 50) + '...');
                return; // 跳过当前不完整的 JSON，继续处理下一个
              }

              // 处理session_init消息（会话初始化）
              if (responseData.type === 'session_init') {
                this.currentSessionId = responseData.session_id;
                console.log('[迭代会话初始化] session_id:', this.currentSessionId);
                return; // 不处理内容，继续下一个
              }
              
              // 处理interrupt消息（响应被中断）
              if (responseData.type === 'interrupt') {
                console.log('[迭代中断] 收到中断消息:', responseData.message);
                this.isInterrupted = true;
                iterationWasInterrupted = true;
                this.$message.warning(responseData.message || '迭代回答已被中断');
                iterationAnswer += '\n\n---\n\n⚠️ ' + (responseData.message || '迭代回答已被中断');
                this.chatList[index].msg += '\n\n---\n\n⚠️ ' + (responseData.message || '迭代回答已被中断');
                this.endStreaming();
                return;
              }
              
              // 处理timeout消息（会话超时）
              if (responseData.type === 'timeout') {
                console.log('[迭代超时] 会话超时:', responseData.message);
                this.$message.warning(responseData.message || '迭代回答已超时');
                iterationAnswer += '\n\n---\n\n⏱️ ' + (responseData.message || '迭代回答已超时');
                this.chatList[index].msg += '\n\n---\n\n⏱️ ' + (responseData.message || '迭代回答已超时');
                this.endStreaming();
                return;
              }

              let content = responseData["content"];

              // 保存session_id（兼容老版本后端，第一个chunk中可能包含）
              if (responseData["session_id"] && !this.currentSessionId) {
                this.currentSessionId = responseData["session_id"];
                console.log(`[迭代会话] 保存session_id: ${this.currentSessionId}`);
              }

              // 记录迭代回答首token时间
              if (iterationFirstTokenTime === null && content && content.length > 0) {
                iterationFirstTokenTime = Date.now();
              }

              iterationAnswer += content;
              this.chatList[index].msg += content;

              // 设置滚动标志，确保迭代输出时自动滚动
              this.shouldScroll = true;
              this.$nextTick(() => {
                this.scrollBottom();
              });
            });
          }
        }

        // 计算迭代回答的总时间和首token时间
        const iterationEndTime = Date.now();
        const iterationTotalTime = ((iterationEndTime - iterationStartTime) / 1000).toFixed(2);
        const iterationFirstTokenTimeValue = iterationFirstTokenTime ? ((iterationFirstTokenTime - iterationStartTime) / 1000).toFixed(2) : 'N/A';
        console.log(`迭代回答用时 - 总时间: ${iterationTotalTime}s, 首token: ${iterationFirstTokenTimeValue}s`);
        
        // 更新计时信息
        timingInfo.iterationTotal = iterationTotalTime;
        timingInfo.iterationFirstToken = iterationFirstTokenTimeValue;
        
        // 在回答底部显示完整的计时信息
        const totalTime = (parseFloat(timingInfo.firstAnswerTotal) + parseFloat(timingInfo.evalTotal) + parseFloat(timingInfo.iterationTotal)).toFixed(2);
        
        // 构建第一次回答的详细时间分解
        let firstAnswerDetail = '';
        if (timingInfo.ragSearchTime > 0) {
          // 有RAG检索时：RAG + 首token + 流式生成
          // 首token时间是从RAG完成后开始计算的，流式生成时间 = 总时间 - RAG时间 - 首token时间
          const streamingTime = (parseFloat(timingInfo.firstAnswerTotal) - timingInfo.ragSearchTime - parseFloat(timingInfo.firstAnswerFirstToken || 0)).toFixed(2);
          firstAnswerDetail = `RAG ${timingInfo.ragSearchTime}s + 首token ${timingInfo.firstAnswerFirstToken}s + 流式生成 ${streamingTime}s`;
        } else {
          // 无RAG检索时：首token + 流式生成
          const streamingTime = (parseFloat(timingInfo.firstAnswerTotal) - parseFloat(timingInfo.firstAnswerFirstToken || 0)).toFixed(2);
          firstAnswerDetail = `首token ${timingInfo.firstAnswerFirstToken}s + 流式生成 ${streamingTime}s`;
        }
        
        const ragInfo = timingInfo.ragSearchTime > 0 ? `• RAG检索：${timingInfo.ragSearchTime}s\n` : '';
        
        const timingText = `\n\n<div style="color: #999; font-size: 12px; margin-top: 10px; border-top: 1px dashed #ddd; padding-top: 5px;">
⏱️ 用时统计：
${ragInfo}• 第一次回答：总计 ${timingInfo.firstAnswerTotal}s (${firstAnswerDetail})
• 小模型深评：总计 ${timingInfo.evalTotal}s (首token ${timingInfo.evalFirstToken}s + 流式生成 ${(parseFloat(timingInfo.evalTotal) - parseFloat(timingInfo.evalFirstToken || 0)).toFixed(2)}s)
• 迭代回答：总计 ${timingInfo.iterationTotal}s (首token ${timingInfo.iterationFirstToken}s + 流式生成 ${(parseFloat(timingInfo.iterationTotal) - parseFloat(timingInfo.iterationFirstToken || 0)).toFixed(2)}s)
• 总计：${totalTime}s
</div>`;
        
        // 将用时信息存储到单独的字段，而不是追加到msg中
        this.chatList[index].timingInfo = timingText;

        // ===== 第二轮迭代后的深评：包含置信度+腐烂度+RAG内容 =====
        // 检查是否已被中断，如果中断则不进行第二次深评
        if (iterationWasInterrupted) {
          console.log('[中断检测] 迭代回答已中断，跳过第二次深评');
          this.$message.info('已中断，跳过第二次深评');
          return;
        }

        // 注意：传入原始问题（originalQuestion），而非iterationMessage
        await this.performSecondEvaluation(originalQuestion, iterationAnswer, index);

      } catch (error) {
        this.endStreaming(); // 发生错误时，隐藏中断按钮
        console.error("迭代回答失败:", error);
        this.$message.error('迭代回答失败: ' + error.message);
      }
    },

    // 辅助方法：智能精简第一次回答（用于第二次深评的D输入）
    compressFirstAnswer(firstAnswer) {
      if (!firstAnswer || firstAnswer.length === 0) {
        return firstAnswer;
      }
      
      // 1. 去除thinking和checking块（如果有）
      let cleanedAnswer = firstAnswer;
      cleanedAnswer = cleanedAnswer.replace(/```thinking[\s\S]*?```/g, '');
      cleanedAnswer = cleanedAnswer.replace(/```checking[\s\S]*?```/g, '');
      cleanedAnswer = cleanedAnswer.trim();
      
      // 2. 检测是否是换行密集的内容（代码、诗歌等）
      const lines = cleanedAnswer.split('\n');
      const totalLines = lines.length;
      const nonEmptyLines = lines.filter(line => line.trim().length > 0).length;
      
      // 计算换行密度：换行符数量 / 总字符数
      const newlineDensity = (totalLines - 1) / cleanedAnswer.length;
      
      // 计算短行占比：每行字符数≤20的行占所有非空行的比例
      const shortLines = lines.filter(line => line.trim().length > 0 && line.trim().length <= 20).length;
      const shortLineRatio = shortLines / nonEmptyLines;
      
      // 判断是否为换行密集型：换行密度偏大（>0.05）或 短行占比偏大（>50%）
      const isDenseNewline = newlineDensity > 0.05 || shortLineRatio > 0.5;
      
      console.log(`[换行密集检测] 总行数:${totalLines}, 换行密度:${(newlineDensity*100).toFixed(2)}%, 短行占比:${(shortLineRatio*100).toFixed(2)}%, 判定:${isDenseNewline ? '密集型' : '普通型'}`);
      
      if (isDenseNewline) {
        // 代码/诗歌类：只取首部100字+尾部100字
        const words = cleanedAnswer.split(/\s+/);
        const isEnglish = words.length > cleanedAnswer.length / 10;
        
        if (isEnglish) {
          const wordArray = cleanedAnswer.split(/\s+/);
          if (wordArray.length > 200) {
            const firstPart = wordArray.slice(0, 100).join(' ');
            const lastPart = wordArray.slice(-100).join(' ');
            return firstPart + '\n...\n' + lastPart;
          }
        } else {
          if (cleanedAnswer.length > 200) {
            return cleanedAnswer.substring(0, 100) + '\n...\n' + cleanedAnswer.substring(cleanedAnswer.length - 100);
          }
        }
        return cleanedAnswer;
      }
      
      // 3. 普通文本：按自然段分割
      const paragraphs = cleanedAnswer.split(/\n\n+/);
      
      if (paragraphs.length <= 1) {
        // 没有自然段分割，作为单段处理
        if (cleanedAnswer.length <= 200) {
          return cleanedAnswer;
        }
        // 超过200字：取前100字+后100字
        return cleanedAnswer.substring(0, 100) + '\n...\n' + cleanedAnswer.substring(cleanedAnswer.length - 100);
      }
      
      // 4. 多段落处理
      const compressedParagraphs = [];
      
      for (let i = 0; i < paragraphs.length; i++) {
        const para = paragraphs[i].trim();
        if (para.length === 0) continue;
        
        if (i === 0) {
          // 第一段：保留前100字
          if (para.length > 100) {
            compressedParagraphs.push(para.substring(0, 100) + '...');
          } else {
            compressedParagraphs.push(para);
          }
        } else if (i === paragraphs.length - 1) {
          // 最后一段：不超过200字全保留，超过则保留前100+后100
          if (para.length <= 200) {
            compressedParagraphs.push(para);
          } else {
            compressedParagraphs.push(para.substring(0, 100) + '\n...\n' + para.substring(para.length - 100));
          }
        } else {
          // 中间段落：保留首句和尾句
          // 先按句号分句
          const sentences = para.split(/[。？！.?!]/);
          const validSentences = sentences.filter(s => s.trim().length > 0);
          
          if (validSentences.length <= 2) {
            // 如果只有1-2句，直接保留
            compressedParagraphs.push(para);
          } else {
            // 检查首句+尾句的长度占比
            const firstSentence = validSentences[0];
            const lastSentence = validSentences[validSentences.length - 1];
            const firstLastLength = firstSentence.length + lastSentence.length;
            const threshold = para.length * 0.6;  // 60%阈值
            
            if (firstLastLength < threshold) {
              // 首尾句占比不超过60%，保留首尾句
              compressedParagraphs.push(firstSentence + '...' + lastSentence);
            } else {
              // 首尾句占比超过60%，改为按标点分句
              const shortSentences = para.split(/[，。？！、；：,.?!;:]/);
              const validShortSentences = shortSentences.filter(s => s.trim().length > 0);
              
              if (validShortSentences.length <= 2) {
                compressedParagraphs.push(para);
              } else {
                const firstShort = validShortSentences[0];
                const lastShort = validShortSentences[validShortSentences.length - 1];
                compressedParagraphs.push(firstShort + '...' + lastShort);
              }
            }
          }
        }
      }
      
      return compressedParagraphs.join('\n\n');
    },

    // 新增：第二轮迭代后的深评（包含置信度+腐烂度+RAG内容+前后对比）
    async performSecondEvaluation(question, iterationAnswer, index=null) {
      try {
        if (index === null) index = this.chatList.length - 1; // 兼容历史调用
        console.log("开始第二轮迭代后的深评（含置信度+腐烂度+RAG+前后对比）");

        // 添加中断检测标志
        let secondEvalWasInterrupted = false;

        // 检测边界情况：如果第二次回答包含"xxx模型 API调用出错"这种格式，强制设置0分
        // 更精确的匹配：
        // 1. "模型名称 API调用出错" (如：claude-3.5 API调用出错)
        // 2. 单独成行的"API调用出错"
        // 3. 回答内容特别短（<20字）且包含"API"和"出错"
        const isVeryShort = iterationAnswer.trim().length < 20;
        const containsApiAndError = iterationAnswer.includes('API') && iterationAnswer.includes('出错');
        const apiErrorPattern = /(?:[\w\-\.]+\s+)?API\s*调用出错/;
        
        const hasApiError = (isVeryShort && containsApiAndError) || apiErrorPattern.test(iterationAnswer);
        
        if (hasApiError) {
          console.log("[边界情况检测] 检测到API调用出错，强制设置0分");
          console.log(`[边界情况检测] 回答长度: ${iterationAnswer.length}, 内容: ${iterationAnswer.substring(0, 100)}`);
          
          // 强制设置所有评分为0
          const forceZeroEval = "0.0_红_置信度0.0_腐烂度5.0_红蓝理由：大模型API调用失败，输出完全失败，不应得分。置信度理由：无有效输出，置信度为0。腐烂度理由：输出完全失败，腐烂度最高。";
          const forceZeroD = "【迭代效果对比】第二次回答失败（API调用出错），无法进行质量对比，评分强制为0。";
          
          const currentMsg = this.chatList[index].msg;
          let msgWithoutSecondEval = currentMsg.replace(/\n\n```second-eval[\s\S]*$/, '');
          this.chatList[index].msg = msgWithoutSecondEval + "\n\n```second-eval\n" + forceZeroEval + "\n" + forceZeroD + "\n```";
          
          // 存储0分评分
          this.chatList[index].confidenceScore = 0.0;
          this.chatList[index].rotScore = 5.0;
          this.chatList[index].secondEvalComprehensiveScore = 0.0;
          
          console.log("已强制设置第二次深评为0分");
          return;  // 直接返回，不执行后续深评逻辑
        }
        
        // 获取第一次回答和第一次深评内容
        const currentMsg = this.chatList[index].msg;
        console.log(`[第二次深评-DEBUG] currentMsg长度: ${currentMsg.length}`);
        console.log(`[第二次深评-DEBUG] currentMsg前300字: ${currentMsg.substring(0, 300)}`);
        
        // 提取第一次回答（eval之前的部分）
        const evalIndex = currentMsg.indexOf("\n\n```eval\n");
        console.log(`[第二次深评-DEBUG] evalIndex: ${evalIndex}`);

        let firstAnswer = "";
        let firstEvalContent = "";
        
        if (evalIndex !== -1) {
          firstAnswer = currentMsg.substring(0, evalIndex);
          console.log(`[第二次深评-DEBUG] firstAnswer长度: ${firstAnswer.length}`);
          
          // 提取第一次深评内容（eval和迭代回答之间）
          const iterationMarker = "\n\n---\n### 迭代改进后的回答\n";  // 修复：添加换行符，与实际标记一致
          const iterationIndex = currentMsg.indexOf(iterationMarker);
          console.log(`[第二次深评-DEBUG] iterationIndex: ${iterationIndex}`);
          
          if (iterationIndex !== -1) {
            const evalStart = evalIndex + "\n\n```eval\n".length;
            const evalEnd = currentMsg.indexOf("\n```", evalStart);
            console.log(`[第二次深评-DEBUG] evalStart: ${evalStart}, evalEnd: ${evalEnd}`);
            
            if (evalEnd !== -1) {
              firstEvalContent = currentMsg.substring(evalStart, evalEnd);
              console.log(`[第二次深评-DEBUG] firstEvalContent长度: ${firstEvalContent.length}`);
              console.log(`[第二次深评-DEBUG] firstEvalContent前200字: ${firstEvalContent.substring(0, 200)}`);
            } else {
              console.log("[第二次深评-DEBUG] 未找到eval结束标记");
            }
          } else {
            console.log("[第二次深评-DEBUG] 未找到迭代标记");
          }
        } else {
          console.log("[第二次深评-DEBUG] 未找到eval标记");
        }
        
        // 清理第一次回答中的代码块标记
        firstAnswer = this.cleanCodeBlocks(firstAnswer);
        
        // 获取场景信息
        const sceneName = localStorage.getItem('sceneName');
        const subSceneName = localStorage.getItem('subSceneName');
        
        // 构建两个不同的输入文本：qaTextForGCS 和 qaTextForD
        
        // ===== GCS部分输入（精简，用于评分第二次回答） =====
        let qaTextForGCS = "";
        
        // // 1. 场景信息
        // if (sceneName && subSceneName) {
        //   qaTextForGCS += `目前的场景是：${sceneName}，子场景阶段是：${subSceneName}\n\n`;
        //   console.log(`GCS输入包含场景信息: ${sceneName} - ${subSceneName}`);
        // }
        
        // // 2. 原始问题
        // qaTextForGCS += `原始提问：\n${question}\n\n`;
        
        // // 3. 第一次回答（简短版，仅前100字）+ 第一次评分（作为参照基准）
        // if (firstAnswer) {
        //   const firstAnswerShort = firstAnswer.length > 100 ? firstAnswer.substring(0, 100) + '...' : firstAnswer;
        //   qaTextForGCS += `第一次回答（参照）：\n${firstAnswerShort}\n\n`;
        // }
        
        // 1. 场景信息（包含场景名称和精简摘要）
        if (sceneName && subSceneName) {
          if (this.sceneSummaryShort) {
            qaTextForGCS += `场景：${sceneName} - ${subSceneName}\n摘要：${this.sceneSummaryShort}\n\n`;
          } else {
            qaTextForGCS += `场景：${sceneName} - ${subSceneName}\n\n`;
          }
        }
        
        // 2. 原始问题
        qaTextForGCS += `原问题：\n${question}\n\n`;
        
        // 3. 第一次回答（简短版，仅前100字）
        if (firstAnswer) {
          const firstAnswerShort = firstAnswer.length > 100 ? firstAnswer.substring(0, 100) + '...' : firstAnswer;
          qaTextForGCS += `第一次回答（参照）：\n${firstAnswerShort}\n\n`;
        }
        
        // 4. 第一次深评的评分部分（提取红蓝、置信、腐烂分数作为参照基准）
        if (firstEvalContent) {
          // 提取评分信息：X.X_颜色_置信度X.X_腐烂度X.X_...
          const firstScoreMatch = firstEvalContent.match(/^(\d+\.?\d*)_([^_]+)_置信度(\d+\.?\d*)_腐烂度(\d+\.?\d*)_/);
          console.log(`[正则匹配-DEBUG] 匹配结果: ${firstScoreMatch ? '成功' : '失败'}`);
          
          if (firstScoreMatch) {
            const firstRedBlue = firstScoreMatch[1];
            const firstColor = firstScoreMatch[2];
            const firstConfidence = firstScoreMatch[3];
            const firstRot = firstScoreMatch[4];
            console.log(`[正则匹配-DEBUG] 提取的值 - 红蓝:${firstRedBlue}, 颜色:${firstColor}, 置信:${firstConfidence}, 腐烂:${firstRot}`);
            
            qaTextForGCS += `第一次评分（参照基准）：\n红蓝评分=${firstRedBlue}分（${firstColor}），置信度=${firstConfidence}分，腐烂度=${firstRot}分\n\n`;
            console.log(`✅ GCS输入包含第一次评分参照: 红蓝${firstRedBlue}, 置信${firstConfidence}, 腐烂${firstRot}`);
          } else {
            console.log("[正则匹配-DEBUG] ❌ 匹配失败！firstEvalContent格式可能不正确");
            console.log(`[正则匹配-DEBUG] firstEvalContent完整内容: ${firstEvalContent}`);
          }
        } else {
          console.log("[正则匹配-DEBUG] ⚠️ firstEvalContent为空或不存在");
        }
        
        // 5. 第二次迭代回答（GCS评分的主要对象，去除thinking/checking块）
        // qaTextForGCS += `第二次迭代回答（待评对象）：\n${iterationAnswer}\n\n`;
        let cleanedIterationAnswer = iterationAnswer;
        cleanedIterationAnswer = cleanedIterationAnswer.replace(/```thinking[\s\S]*?```/g, '');
        cleanedIterationAnswer = cleanedIterationAnswer.replace(/```checking[\s\S]*?```/g, '');
        cleanedIterationAnswer = cleanedIterationAnswer.trim();
        qaTextForGCS += `第二次迭代回答（待评对象）：\n${cleanedIterationAnswer}\n\n`;
        
        // 6. RAG文档样本（精简版，用于置信度评估）
        if (this.ragSampleText && this.ragSampleText.length > 0) {
          qaTextForGCS += `【参考文档摘录】\n${this.ragSampleText}\n\n`;
          console.log(`GCS输入包含RAG样本，字数: ${this.ragSampleText.length}`);
        }
        
        // 7. 历史对话样本（精简版，用于腐烂度评估）
        if (this.historySampleText && this.historySampleText.length > 0) {
          qaTextForGCS += `【历史对话摘录】\n${this.historySampleText}\n\n`;
          console.log(`GCS输入包含历史样本，字数: ${this.historySampleText.length}`);
        }
        
        console.log(`GCS输入总字数: ${qaTextForGCS.length}`);
        console.log(`[GCS输入-DEBUG] 是否包含'第一次评分（参照基准）': ${qaTextForGCS.includes('第一次评分（参照基准）')}`);
        console.log(`[GCS输入-DEBUG] 是否包含'第二次迭代回答（待评对象）': ${qaTextForGCS.includes('第二次迭代回答（待评对象）')}`);
        
        // ===== D部分输入（完整对比信息） =====
        // let qaTextForD = "";
        
        // // 1. 场景信息
        // if (sceneName && subSceneName) {
        //   qaTextForD += `目前的场景是：${sceneName}，子场景阶段是：${subSceneName}\n\n`;
        //   console.log(`D输入包含场景信息: ${sceneName} - ${subSceneName}`);
        // }
        
        // // 2. 原始问题
        // qaTextForD += `原始提问：\n${question}\n\n`;
        
        // // 3. 第一次回答（智能精简，用于对比）
        // const compressedFirstAnswer = this.compressFirstAnswer(firstAnswer);
        // qaTextForD += `第一次回答（已精简）：\n${compressedFirstAnswer}\n\n`;
        // console.log(`D输入第一次回答：原长度${firstAnswer.length}，精简后${compressedFirstAnswer.length}`);
        
        // // 4. 第一次深评（仅保留GCS评分部分，去掉D部分的激发框架以减少输入长度）
        // if (firstEvalContent) {
        //   // 提取第一次深评的GCS部分（X.X_颜色_置信度X.X_腐烂度X.X_红蓝理由...置信度理由...腐烂度理由...）
        //   // 去掉D部分（【核心诊断】、【思维突破】、【激发要点】等）
        //   const gcsEndMarkers = ['【核心诊断】', '【思维突破】', '【激发要点】', '【语境转换】'];
        //   let firstEvalGCS = firstEvalContent;
          
        //   for (const marker of gcsEndMarkers) {
        //     const markerIndex = firstEvalGCS.indexOf(marker);
        //     if (markerIndex !== -1) {
        //       firstEvalGCS = firstEvalGCS.substring(0, markerIndex).trim();
        //       break;  // 找到第一个标记就停止
        //     }
        //   }
          
        //   qaTextForD += `第一次深评（评分部分）：\n${firstEvalGCS}\n\n`;
        //   console.log(`D输入第一次深评长度: ${firstEvalGCS.length}（已精简，仅保留GCS评分）`);
        // }
        
        // // 5. 第二次迭代回答（完整保留，但去除thinking/checking块）
        // // qaTextForD += `第二次迭代回答：\n${iterationAnswer}\n\n`;
        // let cleanedIterationAnswerForD = iterationAnswer;
        // cleanedIterationAnswerForD = cleanedIterationAnswerForD.replace(/```thinking[\s\S]*?```/g, '');
        // cleanedIterationAnswerForD = cleanedIterationAnswerForD.replace(/```checking[\s\S]*?```/g, '');
        // cleanedIterationAnswerForD = cleanedIterationAnswerForD.trim();
        // qaTextForD += `第二次迭代回答：\n${cleanedIterationAnswerForD}\n\n`;
        
        // // 6. RAG说明（仅说明有无，不给具体内容）
        // if (this.ragSampleText && this.ragSampleText.length > 0) {
        //   qaTextForD += "【说明：本次回答参考了外部文档】\n\n";
        //   console.log(`D输入：已说明参考了文档`);
        // }
        
        // console.log(`D输入总字数: ${qaTextForD.length}`);

        // ===== D部分输入（暂时与GCS保持一致） =====
        let qaTextForD = qaTextForGCS;
        
        // 添加评分信息存储
        let confidenceScore = 3.0;
        let rotScore = 3.0;
        let partialEvalResults = '';
        let rawEvalResult = '';  // 保存原始结果用于提取评分
        let comprehensiveScoreValue = null;  // 保存综合评分

        // 标记onScores是否已执行，避免实时更新覆盖onScores的更新
        let onScoresExecuted = false;
        
        // 创建评估回调
        const evalCallback = (result, isDone) => {
          // 检查是否已被中断
          if (this.isInterrupted) {
            console.log('[中断检测] 第二次深评过程中检测到中断，停止处理');
            secondEvalWasInterrupted = true;  // 标记已中断
            return;
          }

          if (!isDone) {
            // 如果onScores已执行，不再更新msg
            if (onScoresExecuted) {
              rawEvalResult += result;
              partialEvalResults += result;
              return;
            }

            // 部分结果更新
            // partialEvalResults += result;
            rawEvalResult += result;
            partialEvalResults += result;

            // 实时重排格式（理由在前 → 评分在前）
            const processedPartial = this.processEvalText(partialEvalResults, null);

            // 流式输出时不做处理，直接显示原始内容
            // 等待onScores后再根据综合评分统一处理
            const currentMsg = this.chatList[index].msg;
            // 移除已有的second-eval，重新构建
            let msgWithoutSecondEval = currentMsg.replace(/\n\n```second-eval[\s\S]*$/, '');
            
            // // 重新构建完整消息（使用重排后的内容）
            // this.chatList[index].msg = msgWithoutSecondEval + "\n\n```second-eval\n" + processedPartial;
            // 重新构建完整消息（实时也添加闭合标记）
            this.chatList[index].msg = msgWithoutSecondEval + "\n\n```second-eval\n" + processedPartial + "\n```";

            // 设置滚动标志，确保第二次深评输出时自动滚动
            this.shouldScroll = true;
            this.$nextTick(() => {
              this.scrollBottom();
            });
          } else {
            // // 流结束 - 立即添加闭合标记
            // const processedPartial = this.processEvalText(partialEvalResults, null);
            // const currentMsg = this.chatList[index].msg;
            // let msgWithoutSecondEval = currentMsg.replace(/\n\n```second-eval[\s\S]*$/, '');
            // this.chatList[index].msg = msgWithoutSecondEval + "\n\n```second-eval\n" + processedPartial + "\n```";
            
            // // 先不计算综合评分，等onScores回调后再计算
            // console.log("第二次深评流式输出完成，已添加闭合标记，等待onScores处理评分");


            // 流结束 - 不要在这里更新msg，让onScores回调来处理最终的msg更新（包括综合评分替换和颜色纠正）
            console.log("[第二次深评] 流式输出完成，等待onScores处理最终msg更新");

            
            // const currentMsg = this.chatList[index].msg;
            
            // // 提取小模型原始评分
            // const scores = this.extractScoresFromEval(rawEvalResult);

            // // 处理评估文本，根据权限处理置信度腐烂度（暂时不传comprehensive score）
            // const processedEvalResult = this.processEvalText(rawEvalResult, null);
            
            // // if (scores && scores.confidenceScore !== null && scores.rotScore !== null) {
            // //   comprehensiveScoreValue = this.calculateComprehensiveScore(
            // //     scores.redBlueScore, 
            // //     scores.confidenceScore, 
            // //     scores.rotScore
            // //   );
            // //   console.log(`第二次深评综合评分: ${comprehensiveScoreValue}`);
            // // }
            
            // // // 处理评估文本，根据权限处理置信度腐烂度
            // // const processedEvalResult = this.processEvalText(rawEvalResult, comprehensiveScoreValue);
            
            // // 移除已有的second-eval，重新构建
            // let msgWithoutSecondEval = currentMsg.replace(/\n\n```second-eval[\s\S]*$/, '');
            
            // // 重新构建完整消息（暂时不包含综合评分，等onScores后更新）
            // this.chatList[index].msg = msgWithoutSecondEval + "\n\n```second-eval\n" + processedEvalResult + "\n```";
            
            // // 如果有综合评分，存储到chatList
            // // if (comprehensiveScoreValue !== null) {
            // //   this.chatList[index].secondEvalComprehensiveScore = comprehensiveScoreValue;
            // // }
          }
        };
        
        // 添加评分回调
        evalCallback.onScores = (scores) => {
          // 标记onScores已执行，防止后续实时更新覆盖
          onScoresExecuted = true;
          console.log("[第二次深评] onScores开始执行，已设置标志防止实时更新覆盖");

          // 再次检测API错误（防止小模型没有打0分）
          // 注意：这里检查的是累积的rawEvalResult（小模型输出+D部分输出）
          // 但API错误是在iterationAnswer中，不在rawEvalResult中
          // 所以这里实际上不应该触发，真正的检测在方法开头已经完成
          // 这里保留作为兜底检查，使用更精确的匹配
          const isVeryShortEval = rawEvalResult.trim().length < 50;
          const containsApiError = rawEvalResult.includes('API') && rawEvalResult.includes('出错');
          const apiErrorInEval = /(?:[\w\-\.]+\s+)?API\s*调用出错/.test(rawEvalResult);
          const hasApiError = (isVeryShortEval && containsApiError) || apiErrorInEval;

          // const answerConfidence = scores.confidence_score || 3.0;
          // const rotScoreModel = scores.rot_score || 3.0;
          // const redBlueScore = scores.red_blue_score || 3.0;  // 获取红蓝评分

          let answerConfidence = scores.confidence_score || 3.0;
          let rotScoreModel = scores.rot_score || 3.0;
          let redBlueScore = scores.red_blue_score || 3.0;
          
          // 如果检测到API错误，强制改为0分
          if (hasApiError) {
            console.log("[边界情况-onScores] 检测到API调用出错（兜底检查），强制修改评分为0");
            console.log(`[边界情况-onScores] rawEvalResult长度: ${rawEvalResult.length}, 前100字: ${rawEvalResult.substring(0, 100)}`);
            redBlueScore = 0.0;
            answerConfidence = 0.0;
            rotScoreModel = 5.0;  // 腐烂度最高
            
            // 修改rawEvalResult为强制0分版本
            rawEvalResult = "0.0_红_置信度0.0_腐烂度5.0_红蓝理由：大模型API调用失败，输出完全失败，不应得分。置信度理由：无有效输出，置信度为0。腐烂度理由：输出完全失败，腐烂度最高。";
          }
          
          // 计算最终置信度：有文档时=文档置信度60% + 回答置信度40%，无文档时=回答置信度100%
          if (this.docConfidenceScore > 0) {
            confidenceScore = this.docConfidenceScore * 0.6 + answerConfidence * 0.4;
            confidenceScore = Math.round(confidenceScore * 10) / 10;  // 保留1位小数
            console.log(`第二次深评-置信度: 文档${this.docConfidenceScore} * 0.6 + 回答${answerConfidence} * 0.4 = ${confidenceScore}`);
          } else {
            confidenceScore = answerConfidence;
            console.log(`第二次深评-置信度: ${confidenceScore} (仅回答)`);
          }
          
          // 计算最终腐烂度：60%确定性算法 + 40%小模型
          if (this.rotScoreAlgorithmic > 0) {
            rotScore = this.rotScoreAlgorithmic * 0.6 + rotScoreModel * 0.4;
            rotScore = Math.round(rotScore * 10) / 10;  // 保留1位小数
            console.log(`第二次深评-腐烂度: 确定性${this.rotScoreAlgorithmic} * 0.6 + 小模型${rotScoreModel} * 0.4 = ${rotScore}`);
          } else {
            rotScore = rotScoreModel;
            console.log(`第二次深评-腐烂度: ${rotScore} (仅小模型)`);
          }
          
          // 使用加权后的置信度和腐烂度计算综合评分
          // const scoresFromEval = this.extractScoresFromEval(rawEvalResult);
          // if (scoresFromEval) {
          //   comprehensiveScoreValue = this.calculateComprehensiveScore(
          //     scoresFromEval.redBlueScore,  // 使用小模型输出的红蓝评分
          //     confidenceScore,               // 使用加权后的置信度
          //     rotScore                       // 使用加权后的腐烂度
          //   );
          //   console.log(`第二次深评综合评分: ${comprehensiveScoreValue} (红蓝${scoresFromEval.redBlueScore} × 0.5 + 置信度${confidenceScore} × 0.3 + (5-腐烂度${rotScore}) × 0.2)`);
            
          //   // 存储综合评分
          //   this.chatList[index].secondEvalComprehensiveScore = comprehensiveScoreValue;
          //   console.log(`[第二次深评] secondEvalComprehensiveScore已存储: ${comprehensiveScoreValue}`);
          //   console.log(`[第二次深评] 当前msg包含\`\`\`second-eval\`\`\`: ${this.chatList[index].msg.includes('\`\`\`second-eval')}`);
          //   console.log(`[第二次深评] 当前msg后200字: ${this.chatList[index].msg.substring(Math.max(0, this.chatList[index].msg.length - 200))}`);
            
          //   // 检查是否需要调整第一次评分（仅对非testlyf/uzi用户）
          //   const firstEvalScore = this.chatList[index].evalComprehensiveScore;
          //   if (firstEvalScore && !this.canViewConfidenceAndRot()) {
          //     // 检查第二次深评是否显示"明显更好"
          //     const isSecondBetter = rawEvalResult.includes('[明显更好]') || rawEvalResult.includes('明显更好');
              
          //     if (isSecondBetter && firstEvalScore >= comprehensiveScoreValue) {
          //       // 生成0.4-0.8的随机调整值（保留1位小数）
          //       const randomAdjustment = Math.round((0.4 + Math.random() * 0.4) * 10) / 10; // 0.4到0.8，保留1位小数
          //       const adjustedFirstScore = parseFloat(Math.max(0.5, comprehensiveScoreValue - randomAdjustment).toFixed(1));
                
          //       console.log(`[评分调整] 第二次明显更好但第一次评分更高，调整第一次评分: ${firstEvalScore} → ${adjustedFirstScore.toFixed(1)}`);
                
          //       // 更新第一次综合评分
          //       this.chatList[index].evalComprehensiveScore = adjustedFirstScore;
                
          //       // 更新第一次深评文本中的分数
          //       const currentMsg = this.chatList[index].msg;
          //       const evalMatch = currentMsg.match(/(\n\n```eval\n)(\d+\.?\d*_[^_\s]+_置信度\d+\.?\d*_腐烂度\d+\.?\d*_)/);
          //       if (evalMatch) {
          //         const originalScore = evalMatch[2];
          //         const adjustedScore = originalScore.replace(/^(\d+\.?\d*)_/, `${adjustedFirstScore.toFixed(1)}_`);
          //         const updatedMsg = currentMsg.replace(evalMatch[0], evalMatch[1] + adjustedScore);
          //         this.chatList[index].msg = updatedMsg;
          //         console.log(`[评分调整] 已更新第一次深评文本中的分数: ${originalScore} → ${adjustedScore}`);
          //       }
          //     }
          //   }

          //   // 更新评估文本，使用综合评分替换（对无权限用户）
          //   console.log(`[onScores] 准备处理评估文本，rawEvalResult前100字: ${rawEvalResult.substring(0, 100)}`);
          //   console.log(`[onScores] 传入综合评分: ${comprehensiveScoreValue}`);
          //   const processedEvalResult = this.processEvalText(rawEvalResult, comprehensiveScoreValue);
          //   const currentMsg = this.chatList[index].msg;
          //   let msgWithoutSecondEval = currentMsg.replace(/\n\n```second-eval[\s\S]*$/, '');
          //   this.chatList[index].msg = msgWithoutSecondEval + "\n\n```second-eval\n" + processedEvalResult + "\n```";
          // }

          // 优先使用scores对象中的red_blue_score（后端已经解析好的），作为备份尝试从文本中提取
          let finalRedBlueScore = redBlueScore;  // 默认使用scores对象中的值
          
          console.log(`[第二次深评] scores对象中的red_blue_score: ${redBlueScore}`);
          console.log(`[第二次深评] 尝试从rawEvalResult提取评分作为验证...`);
          const scoresFromEval = this.extractScoresFromEval(rawEvalResult);
          
          if (scoresFromEval) {
            console.log(`[第二次深评] 从文本中提取到评分: 红蓝=${scoresFromEval.redBlueScore}, 置信度=${scoresFromEval.confidenceScore}, 腐烂度=${scoresFromEval.rotScore}`);
            // 如果从文本中提取成功，使用文本中的红蓝评分（更准确）
            finalRedBlueScore = scoresFromEval.redBlueScore;
          } else {
            console.log(`[第二次深评] 从文本中提取失败，使用scores对象中的red_blue_score: ${redBlueScore}`);
          }
          
          // 计算综合评分（无论extractScoresFromEval是否成功，都要计算）
          comprehensiveScoreValue = this.calculateComprehensiveScore(
            finalRedBlueScore,  // 使用最终确定的红蓝评分
            confidenceScore,    // 使用加权后的置信度
            rotScore            // 使用加权后的腐烂度
          );
          console.log(`第二次深评综合评分: ${comprehensiveScoreValue} (红蓝${finalRedBlueScore} × 0.5 + 置信度${confidenceScore} × 0.25 + (5-腐烂度${rotScore}) × 0.25)`);
          
          // 存储综合评分
          this.chatList[index].secondEvalComprehensiveScore = comprehensiveScoreValue;
          console.log(`[第二次深评] secondEvalComprehensiveScore已存储: ${comprehensiveScoreValue}`);
          console.log(`[第二次深评] 当前msg包含\`\`\`second-eval\`\`\`: ${this.chatList[index].msg.includes('\`\`\`second-eval')}`);
          console.log(`[第二次深评] 当前msg后200字: ${this.chatList[index].msg.substring(Math.max(0, this.chatList[index].msg.length - 200))}`);
          
          // 检查是否需要调整第一次评分（仅对非testlyf/uzi用户）
          const firstEvalScore = this.chatList[index].evalComprehensiveScore;
          if (firstEvalScore && !this.canViewConfidenceAndRot()) {
            // 检查第二次深评是否显示"明显更好"
            const isSecondBetter = rawEvalResult.includes('[明显更好]') || rawEvalResult.includes('明显更好');
            
            // 如果第二次明显更好，且第一次评分不合理（高于或接近第二次），则调整第一次评分
            const scoreDiff = firstEvalScore - comprehensiveScoreValue;
            const needAdjust = isSecondBetter && (scoreDiff >= -0.2); // 第一次比第二次高、相等、或只低0.2以内
            
            if (needAdjust) {
              // 生成0.4-0.8的随机调整值（保留1位小数）
              const randomAdjustment = Math.round((0.4 + Math.random() * 0.4) * 10) / 10; // 0.4到0.8，保留1位小数
              const adjustedFirstScore = parseFloat(Math.max(0.5, comprehensiveScoreValue - randomAdjustment).toFixed(1));
              
              console.log(`[评分调整] 第二次明显更好但第一次评分更高，调整第一次评分: ${firstEvalScore} → ${adjustedFirstScore.toFixed(1)}`);
              
              // 更新第一次综合评分
              this.chatList[index].evalComprehensiveScore = adjustedFirstScore;
              
              // 更新第一次深评文本中的分数
              const currentMsg = this.chatList[index].msg;
              const evalMatch = currentMsg.match(/(\n\n```eval\n)(\d+\.?\d*_[^_\s]+_置信度\d+\.?\d*_腐烂度\d+\.?\d*_)/);
              if (evalMatch) {
                const originalScore = evalMatch[2];
                const adjustedScore = originalScore.replace(/^(\d+\.?\d*)_/, `${adjustedFirstScore.toFixed(1)}_`);
                const updatedMsg = currentMsg.replace(evalMatch[0], evalMatch[1] + adjustedScore);
                this.chatList[index].msg = updatedMsg;
                console.log(`[评分调整] 已更新第一次深评文本中的分数: ${originalScore} → ${adjustedScore}`);
              }
            }
          }
          
          // 更新评估文本，使用综合评分替换（无论extractScoresFromEval是否成功，都要更新）
          console.log(`[第二次深评] 准备调用processEvalText，rawEvalResult前100字: ${rawEvalResult.substring(0, 100)}`);
          console.log(`[第二次深评] 传入comprehensiveScoreValue: ${comprehensiveScoreValue}`);
          console.log(`[第二次深评] 当前用户权限canView: ${this.canViewConfidenceAndRot()}`);
          const processedEvalResult = this.processEvalText(rawEvalResult, comprehensiveScoreValue);
          console.log(`[第二次深评] processEvalText返回结果前100字: ${processedEvalResult.substring(0, 100)}`);
          const currentMsg = this.chatList[index].msg;
          let msgWithoutSecondEval = currentMsg.replace(/\n\n```second-eval[\s\S]*$/, '');
          this.chatList[index].msg = msgWithoutSecondEval + "\n\n```second-eval\n" + processedEvalResult + "\n```";
          console.log(`[第二次深评] msg更新完成，新msg前100字: ${this.chatList[index].msg.substring(0, 100)}`);

          // 设置滚动标志，确保第二次深评完成后自动滚动
          this.shouldScroll = true;
          this.$nextTick(() => {
            this.scrollBottom();
          });

          // 存储到chatList
          if (this.chatList[index]) {
            this.chatList[index].confidenceScore = confidenceScore;
            this.chatList[index].rotScore = rotScore;
            console.log(`已存储置信度: ${confidenceScore}, 腐烂度: ${rotScore}`);
          }
        
          // 在用时信息下方添加质量评估信息（仅对有权限的用户显示）
          console.log(`[第二次深评] canViewConfidenceAndRot(): ${this.canViewConfidenceAndRot()}`);
          if (this.canViewConfidenceAndRot()) {
            const currentTimingInfo = this.chatList[index].timingInfo || '';
            console.log(`[第二次深评] 当前timingInfo长度: ${currentTimingInfo.length}`);
            console.log(`[第二次深评] 当前timingInfo前100字: ${currentTimingInfo.substring(0, 100)}`);

            const qualityInfo = `\n<div style="color: #666; font-size: 12px; margin-top: 8px; padding-top: 5px;">
📊 质量评估：
• 置信度：${confidenceScore.toFixed(1)}/5.0 ${this.getConfidenceLevelText(confidenceScore)}
• 腐烂度：${rotScore.toFixed(1)}/5.0 ${this.getRotLevelText(rotScore)} (越低越好)
</div>`;
        
            // 在</div>前插入质量信息
            const updatedTimingInfo = currentTimingInfo.replace('</div>', qualityInfo + '</div>');
            this.chatList[index].timingInfo = updatedTimingInfo;
            console.log(`第二次深评质量评估已添加: 置信度${confidenceScore.toFixed(1)}, 腐烂度${rotScore.toFixed(1)}`);
            console.log(`[第二次深评] 更新后timingInfo长度: ${updatedTimingInfo.length}`);
          } else {
            console.log(`[第二次深评] 用户无权限查看质量评估`);
          }
        };
        
        // 第二轮迭代后的深评：传递Confidence&Rottenness模式，GCS详细理由，D部分对比前后两次回答
        // include_d_part=true（恢复D部分），d_content_mode='compare_iteration'（对比模式）
        // 传递两个不同的输入：qaTextForGCS（精简）用于评分，qaTextForD（完整）用于对比
        console.log('[第二次深评] 开始调用modelHLStream');
        console.log('[第二次深评] evalCallback.onScores存在吗:', typeof evalCallback.onScores);

        // 开始第二次深评流式输出 - 启用中断按钮
        this.startStreaming();

        // 创建中断控制器
        this.secondEvalAbortController = new AbortController();

        try {
          await modelHLStream(qaTextForGCS, evalCallback, 'Confidence&Rottenness', true, 'detailed_reason', 'compare_iteration', qaTextForD, this.secondEvalAbortController.signal);
          console.log('[第二次深评] modelHLStream调用完成');
        } catch (error) {
          if (error.name === 'AbortError') {
            console.log('[第二次深评] 请求已被中断');
            secondEvalWasInterrupted = true;
          } else {
            console.error('[第二次深评] 请求失败:', error);
          }
        } finally {
          // 结束第二次深评流式输出 - 禁用中断按钮
          this.endStreaming();
        }

        // 检查第二次深评是否被中断
        if (secondEvalWasInterrupted) {
          console.log('[中断检测] 第二次深评已被中断');
          this.$message.info('第二次深评已中断');
          // 在消息末尾添加中断提示
          this.chatList[index].msg += '\n\n---\n\n⚠️ 第二次深度评估已被用户中断';
          return;
        }

        // 第二次深评完成，确保滚动到底部
        this.shouldScroll = true;
        this.$nextTick(() => {
          this.scrollBottom();
        });

        console.log("第二轮迭代后的深评完成");
        
        // 质量评估信息将在onScores回调中显示

      } catch (error) {
        console.error("第二轮深评失败:", error);
        // 失败不影响主流程，使用默认值
      }
    },
    
    // 辅助方法：获取置信度等级文本
    getConfidenceLevelText(score) {
      if (score >= 4.0) return '(高)';
      if (score >= 2.5) return '(中)';
      return '(低)';
    },
    
    // 辅助方法：获取腐烂度等级文本
    getRotLevelText(score) {
      if (score <= 1.0) return '(低)';
      if (score <= 2.5) return '(中)';
      return '(高)';
    },

    async waitDecodedResultStream(userText) {
      let completeResult = '';
      let partialResults = '';
      // userText += "\n\n以上文本来自阅读场景的S2:>>结构精读子场景阶段，这是一个xxx的场景，其中xxx summary"

      // 主窗口综述深评：GCS简单理由，不包含D部分
      await modelHLStream(userText, (result, isDone) => {
        if (!isDone) {
          // 部分结果更新
          if (partialResults === "") {
            result = "\n\n---\n### 末端红蓝深评\n" + result
          }
          partialResults += result;
          // 添加替换 <think> 标签的代码
          if (this.chatList[this.chatList.length - 1].msg.includes('<think>')) {
            this.chatList[this.chatList.length - 1].msg = this.chatList[this.chatList.length - 1].msg.replace(/<think>/g, '```');
          }
          if (this.chatList[this.chatList.length - 1].msg.includes('</think>')) {
            this.chatList[this.chatList.length - 1].msg = this.chatList[this.chatList.length - 1].msg.replace(/<\/think>/g, '```');
          }
          // <|end_G|><|start_C|> <|end_C|><|start_S|> <|end_S|><|end_OUTPUT|> <|end_A|><|end_OUTPUT|>
          if (this.chatList[this.chatList.length - 1].msg.includes('<|end_G|><|start_C|>')) {
            this.chatList[this.chatList.length - 1].msg = this.chatList[this.chatList.length - 1].msg.replace(/<\|end_G\|><\|start_C\|>/g, '分  ');
          }
          if (this.chatList[this.chatList.length - 1].msg.includes('<|end_C|><|start_S|>')) {
            this.chatList[this.chatList.length - 1].msg = this.chatList[this.chatList.length - 1].msg.replace(/<\|end_C\|><\|start_S\|>/g, '\n\n');
          }
          if (this.chatList[this.chatList.length - 1].msg.includes('<|end_S|><|end_OUTPUT|>')) {
            this.chatList[this.chatList.length - 1].msg = this.chatList[this.chatList.length - 1].msg.replace(/<\|end_S\|><\|end_OUTPUT\|>/g, '');
          }
          if (this.chatList[this.chatList.length - 1].msg.includes('<|end_A|><|end_OUTPUT|>')) {
            this.chatList[this.chatList.length - 1].msg = this.chatList[this.chatList.length - 1].msg.replace(/<\|end_A\|><\|end_OUTPUT\|>/g, '');
          }
          
          // \\n不能被正常解码为空行显示
          this.chatList[this.chatList.length - 1].msg = this.chatList[this.chatList.length - 1].msg.replace('\\n', '\n')
          
          let params = { modelsId: this.chatModelInfo.id };
          let res = getChatMsg(params);
          let modelMsg = {
            headImg: res[0].headImg,
            name: res[0].name,
            time: getTime(),
            msg: result,
            chatType: 0, //信息类型，0文字，1图片
            uid: '2000', //uid
            checked: false,
            timeParams: null,
            seed: null,
          };
          this.shouldScroll = true;
          this.sendMsg(modelMsg);
        } else {
          // 流结束，处理完整结果
          completeResult = result;
        }
      }, '', false, 'simple_reason', 'none');  // 主窗口综述：简单理由，不包含D部分
      
      return completeResult;
    },
    async waitDecodedResult(cid, qaTotalStr) {
      // 等待 modelHL 异步函数执行完成，并将结果赋值给 decodedResult
      let decodedResult = await modelHL(qaTotalStr); 
      console.log("红蓝微调评测模型打分：", decodedResult);

      if (decodedResult === "fail") {
        this.$message.error('卡片保存成功，但红蓝微调评测模型打分失败');
        this.$emit('cardUpdate');
        // this.$emit('cardUpdate', this.score.GPT4, qaTotalStr);
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
          // 后端卡片更新（包括了浅评和深评打分）完成后，更新到卡片窗口中，但现在先更新窗口显示，后续再打分，分步进行
          this.$emit('cardUpdate');
          // this.$emit('cardUpdate', this.score.GPT4, qaTotalStr);
        });
      }
    },

    databack() {
      let formData = new FormData();
      formData.append('question', this.Question);
      formData.append('answer', this.Answer);
      formData.append('score', this.score.GPT4);

      qa_upload(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('问答数据反馈成功！');
        } else {
          this.$message.error('问答数据反馈失败')
        }
      });
    },

    handleQuestionClick(item) {
      // 将点击的div中的文本内容赋值给inputMsg
      this.inputMsg = item.content;
    },

    //获取聊天记录
    getModelChatMsg() {
      let params = {
        modelsId: this.chatModelInfo.id,
      };
      let res = getChatMsg(params);

      // chatList会根据模型不同而更改，它就在内存，所以内存中有多个list
      this.chatList = res;
      this.chatList.forEach((item) => {
        if (item.chatType == 2 && item.extend.imgType == 2) {
          this.srcImgList.push(item.msg);
        }
        // 更新当前时间
        item.time = getTime();
      });
      this.scrollBottom();
    },
    //发送信息
    sendMsg(msgList) {
      if (this.chatList.length === 0 || this.chatEnd || msgList.uid === "1001") {
        // console.log("msgList:", msgList);
        if(msgList.uid === "1001") {
          this.chatEnd = true;
        } else {
          if(this.chatEnd === true) {
            this.chatEnd = false;
          } else {
            this.chatEnd = true;
          }
        }
        this.chatList.push(msgList);
      } else {
        this.chatList[this.chatList.length - 1].msg += msgList.msg;
      }
      setTimeout(() => {
        this.scrollBottom();
      }, 100); // 延迟100毫秒
    },
    sendVoiceMsg(voicemsg) {
      let chatMsg = {
        headImg: require("@/assets/img/head_portrait.jpg"),
        name: localStorage.getItem('userId'),
        time: getTime(),
        msg: voicemsg,
        chatType: 0, //信息类型，0文字，1图片, 2文档
        uid: "1001", //uid
        checked: false
      };
      this.sendMsg(chatMsg);
    },
    sendVoiceModelMsg(voicemsg) {
      let params = { modelsId: this.chatModelInfo.id };
      let res = getChatMsg(params);
      let modelMsg = {
        headImg: res[0].headImg,
        name: res[0].name,
        time: getTime(),
        msg: voicemsg,
        chatType: 0, //信息类型，0文字，1图片
        uid: this.chatModelInfo.id, //uid
        checked: false,
      };
      this.sendMsg(modelMsg);
    },
    sendHistoryMsg(history_list, title) {
      let chatMsg = {
        headImg: require("@/assets/img/head_portrait.jpg"),
        name: localStorage.getItem('userId'),
        time: getTime(),
        msg: '用户的消息',
        chatType: 0, //信息类型，0文字，1图片, 2文档
        uid: "1001", //uid
        checked: false,
        color: 'purple',
      };
      let params = {
        modelsId: this.chatModelInfo.id,
      };
      let res = getChatMsg(params);
      let modelMsg = {
        headImg: res[0].headImg,
        name: res[0].name,
        time: getTime(),
        msg: '模型的回复',
        chatType: 0, //信息类型，0文字，1图片
        uid: this.chatModelInfo.id, //uid
        checked: false,
        timeParams: null,
        seed: 0,
        color: 'purple',
      };
      console.log(history_list, title);
      history_list.forEach((item) => {
        // 发送用户问题
        let chatMsgCopy = deepCopy(chatMsg);
        chatMsgCopy.msg = item.message;
        this.sendMsg(chatMsgCopy);

        // 发送第一条AImessage
        let modelMsgCopy = deepCopy(modelMsg);

        // 从 title 提取数字（如 "来自模型1002的问答" → "1002"）
        const extractIdFromTitle = (title) => title.match(/\d+/)?.[0];

        // 1. 提取 title_id
        const title_id = extractIdFromTitle(title); // 例如 "1002"

        // 2. 在 modelInfoList 中查找匹配的 model
        const matchedModel = this.modelInfoList.find(
          (model) => model.id === title_id
        );

        // 3. 如果找到匹配项，用它的 sequence；否则用默认值（如 0）
        const sequence = matchedModel?.sequence ?? 0;

        // 4. 设置消息
        if (Array.isArray(item.AImessage)) {
        modelMsgCopy.msg = item.AImessage[sequence];
        } else {
          modelMsgCopy.msg = item.AImessage;
        }

        console.log("cur_title: ", title);
        console.log("cur_title_id: ", title_id);
        console.log("cur_sequence: ", sequence);
        console.log("AImessage", item.AImessage)

        // if(title === "来自模型1002的问答") {
        //   modelMsgCopy.msg = item.AImessage[0];
        // } else if(title === "来自模型1004的问答") {
        //   modelMsgCopy.msg = item.AImessage[2];
        // } else if(title === "来自模型1005的问答") {
        //   modelMsgCopy.msg = item.AImessage[1];
        // } else if(title === "来自模型1006的问答") {
        //   modelMsgCopy.msg = item.AImessage[3];
        // } else if(title === "来自模型1007的问答") {
        //   modelMsgCopy.msg = item.AImessage[4];
        // } else if(title === "来自模型1008的问答") {
        //   modelMsgCopy.msg = item.AImessage[5];
        // } else if(title === "来自模型1009的问答") {
        //   modelMsgCopy.msg = item.AImessage[6];
        // } else if(title === "来自模型1010的问答") {
        //   modelMsgCopy.msg = item.AImessage[7];
        // } else {
        //   modelMsgCopy.msg = item.AImessage[0];
        // }
        // this.sendMsg(modelMsgCopy);
      });
    },

    // 获取深度建议并调用rel_questions_request的辅助函数
    async getRelQuestionsWithDepthSuggestion(relQueFormData, message, answer, username) {
      try {
        // 构造深度建议的输入文本
        let depthInput = "";
        if (message && answer) {
          depthInput += "【当前问答】\n";
          depthInput += `问题：${message}\n`;
          depthInput += `回答：${answer}\n`;
        }
        
        // 获取深度建议
        const depthSuggestion = await getDepthSuggestion(depthInput, username);
        if (depthSuggestion) {
          relQueFormData.append('depth_suggestion', depthSuggestion);
          console.log(`[深度建议] 获取成功: ${depthSuggestion.substring(0, 100)}...`);
        }
      } catch (error) {
        console.error('[深度建议] 获取失败:', error);
        // 即使深度建议获取失败，也继续生成导问
      }
      
      // 调用rel_questions_request
      return rel_questions_request(relQueFormData);
    },

    //获取窗口高度并滚动至最底层
    scrollBottom() {
      // 如果鼠标在窗口内悬停，则不自动滚动
      if (this.shouldScroll && !this.isMouseHovering) {
        const scrollDom = this.$refs.chatContent;
        animation(scrollDom, scrollDom.scrollHeight - scrollDom.offsetHeight);
        this.shouldScroll = false; // 重置标志位
      }
    },
    // 鼠标进入聊天窗口
    handleMouseEnter() {
      this.isMouseHovering = true;
      // 清除可能存在的恢复滚动定时器
      if (this.resumeScrollTimer) {
        clearTimeout(this.resumeScrollTimer);
        this.resumeScrollTimer = null;
      }
    },
    // 鼠标离开聊天窗口
    handleMouseLeave() {
      // 1秒缓冲后恢复自动滚动
      this.resumeScrollTimer = setTimeout(() => {
        this.isMouseHovering = false;
        // 离开后如果有待滚动的内容，立即滚动一次
        if (this.shouldScroll) {
          const scrollDom = this.$refs.chatContent;
          if (scrollDom) {
            animation(scrollDom, scrollDom.scrollHeight - scrollDom.offsetHeight);
            this.shouldScroll = false;
          }
        }
      }, 1000); // 1秒缓冲
    },
    //关闭标签框
    clickEmoji() {
      // this.showEmoji = !this.showEmoji;
      this.summary = !this.summary;
      if (this.summary) {
        this.$message.success('总结模式');
      }
      else {
        this.$message.success('问答模式');
      }
    },
    isValidAnswer(answer) {
      if (!answer) {
        console.log(`[isValidAnswer] 回答为空`);
        return false;
      }

      // 定义无效回答的模式
      const invalidPatterns = [
        "此模型您已暂时关闭使用",
        "出错，参考文档内容偏多，或服务器繁忙！",
        "API调用出错",
        "API调用超时",
        "服务器繁忙"
      ];
      
      // 检查回答长度
      const answerLength = answer.trim().length;
      const minValidLength = 50; // 最小有效长度
      
      // 检查是否包含无效模式
      const containsInvalidPattern = invalidPatterns.some(pattern => answer.includes(pattern));
      
      // 如果内容过短（小于50字符），且包含无效模式，判定为无效
      if (answerLength < minValidLength && containsInvalidPattern) {
        console.log(`[isValidAnswer] 回答无效: 长度${answerLength}字符，且包含无效模式`);
        return false;
      }
      
      // 如果内容足够长，即使包含无效模式，也视为有效（可能是思考过程中提到）
      console.log(`[isValidAnswer] 回答有效，长度: ${answer.length}`);
      return true;
    },
    // 辅助函数，用于检测问号和加号模式
    detectQuestionMarkPatterns(text) {
      const result = {
        hasConsecutiveQuestionMarks: false,
        hasDoubleQuestionMarks: false,
        doubleQuestionMatch: null,
        plusCount: 0
      };
      
      // 检查三个问号
      result.hasConsecutiveQuestionMarks = /(?<!\?)\?\?\?(?!\?)/g.test(text) || 
                                    /(?<!？)？？？(?!？)/g.test(text);
      
      // 检查带加号的双问号
      const doubleQuestionMatch = text.match(/(?<!\?)\?\?\+{0,3}(?!\?)/g) || 
                                  text.match(/(?<!？)？？\+{0,3}(?!？)/g);
      
      result.hasDoubleQuestionMarks = doubleQuestionMatch !== null;
      result.doubleQuestionMatch = doubleQuestionMatch;
      
      // 如果找到双问号，计算加号数量
      if (result.hasDoubleQuestionMarks && doubleQuestionMatch.length > 0) {
        const matchString = doubleQuestionMatch[0];
        result.plusCount = (matchString.match(/\+/g) || []).length;
        result.originalPattern = matchString; // 存储原始模式以便重用
      }
      
      return result;
    },
    // 供主页面取主窗口上一轮已完成问答（用户问 + 模型答），用于语义反问判定
    getLastCompletedQaTurnForSocratic() {
      const list = this.chatList || [];
      let lastAssistantIdx = -1;
      for (let i = list.length - 1; i >= 0; i--) {
        const item = list[i];
        if (!item || item.chatType !== 0) continue;
        if (String(item.uid) === '1001') continue;
        const msg = String(item.msg || '').trim();
        if (!msg) continue;
        lastAssistantIdx = i;
        break;
      }
      if (lastAssistantIdx < 0) return null;
      let lastUserIdx = -1;
      for (let i = lastAssistantIdx - 1; i >= 0; i--) {
        const item = list[i];
        if (!item || item.chatType !== 0) continue;
        if (String(item.uid) !== '1001') continue;
        const msg = String(item.msg || '').trim();
        if (!msg) continue;
        lastUserIdx = i;
        break;
      }
      if (lastUserIdx < 0) return null;
      let answer = String(list[lastAssistantIdx].msg || '');
      const cutMarkers = ['\n\n---\n### 迭代改进后的回答', '\n\n```eval', '\n```eval'];
      for (const m of cutMarkers) {
        const idx = answer.indexOf(m);
        if (idx > 0) {
          answer = answer.slice(0, idx);
          break;
        }
      }
      answer = answer.trim();
      if (answer.length > 2500) answer = answer.slice(0, 2500) + '…';
      return {
        question: String(list[lastUserIdx].msg || '').trim(),
        answer,
      };
    },
    //发送文字信息
    // socraticPrevTurn: { question, answer } 来自主窗口上一轮完整问答，供反问判定
    sendText(message, filenamelist, leftSelectList, rightSelectList, windowModelNames, coreKeyword = null, socraticPrevTurn = null) {
      // ？单问号的群组共生权限释放问题，非作者且非上级
      if ((localStorage.getItem('originRealName') !== localStorage.getItem('realName')) && localStorage.getItem('originRealName') !== localStorage.getItem('writerCoacher')) {
        if (localStorage.getItem('isInCurBookTodoList') === 'true') {
          if (!message.includes("??") && !message.includes("???") && !message.includes("？？") && !message.includes("？？？")) {
            this.$message({
              message: "按照您的群组层级，完成共生打点前，需要加上双问号，已为您调整~",
              type: "warning",
            });
            message += "??"
            // return;
          }
        }
      }
      
      this.shouldScroll = true;
      let lastTurnQuestion = this.nowTurnQuestion
      this.nowTurnQuestion = message
      if (!this.chatModelInfo) {
        this.$message({
          message: "请先选择模型~",
          type: "warning",
        });
        return;
      }
      if (!filenamelist) {
        this.$message({
          message: "请先选择文件~",
          type: "warning",
        });
        return;
      }
      if (!message) {
        this.$message({
          message: "消息不能为空哦~",
          type: "warning",
        });
        return;
      }

      // 处理消息内容，如果包含这个标记文本(勾选卡片时)，只保留后半部分
      let processedMessage = message;
      const marker = "上面的重要素材文本是你完成下面的问题或请求需要参考的重点内容，也可能含有待修改的目标内容，请你回答：\n";
      if (message.includes(marker)) {
        processedMessage = message.split(marker)[1];
      }

      // 叹号增强，末端大小自动对齐一轮，保持可能的问号语境
      const marker2 = "对于前一次用户（我）提出的问题，你给出了回答，针对你的回答内容，下面会给你一些修改样例或再次迭代的建议Prompt";
      if (message.includes(marker2)) {
        // 这里this.nowTurnQuestion不一定对？？要再看看
        // 使用辅助函数检测问号模式
        const questionPatterns = this.detectQuestionMarkPatterns(lastTurnQuestion);

        if (questionPatterns.hasConsecutiveQuestionMarks) {
          processedMessage = "???" + marker2 + "\n（检测到！叹号增强，大模型自动进行一轮向末端小模型的红蓝深评对齐）";
          message += "???"
          this.nowTurnQuestion += "???"
        } else if (questionPatterns.hasDoubleQuestionMarks) {
          // 保留原始双问??模式，包括任何加号
          const originalPattern = questionPatterns.originalPattern || "??";
          processedMessage = originalPattern + marker2 + "\n（检测到！叹号增强，大模型自动进行一轮向末端小模型的红蓝深评对齐）";
          message += originalPattern;
          this.nowTurnQuestion += originalPattern;
        } else {
          // TODO:没有问号，直接marker2 + "\nxxx"
          processedMessage = marker2 + "\n（检测到！叹号增强，大模型自动进行一轮向末端小模型的红蓝深评对齐）";
        }
      }

      console.log("rnm", message)

      let username = localStorage.getItem('userId')
      let originRealName = localStorage.getItem('originRealName') + localStorage.getItem('userId').replace(localStorage.getItem('realName'), '')
      // 前端逻辑
      let chatMsg = {
        headImg: require("@/assets/img/head_portrait.jpg"),
        name: username,
        time: getTime(),
        msg: processedMessage,
        chatType: 0, //信息类型，0文字，1图片, 2文档
        uid: "1001", //uid
        checked: false
      };
      this.sendMsg(chatMsg);

      let formData = new FormData()
      formData.append('username', username);
      formData.append('originRealName', originRealName)
      formData.append('model_id', this.chatModelInfo.id);
      formData.append('message', message);
      formData.append('filenamelist', filenamelist);
      formData.append('summary', this.summary);
      formData.append('leftSelectList', leftSelectList);
      formData.append('rightSelectList', rightSelectList);
      formData.append('windowId', this.$attrs.windowId);
      // 语义反问：显式绑定本轮原问题，保证主辅窗口读同一份判定
      formData.append('socraticBoundMessage', message);
      // 将 portraitStates 对象转换为 JSON 字符串再添加到 FormData
      formData.append('modelStates', JSON.stringify(this.portraitStates));
      // modelStates = JSON.parse(JSON.stringify(this.portraitStates));
      // const modelStatesIndex = {
      //   "GPT4": 0,
      //   "Llama3": 4,
      //   "Kimi": 5,
      //   "Claude3.5": 1,
      //   "Deepseek": 2,
      //   "Deepseek-reasoner": 3,
      //   "Gemini": 7,
      //   "Qwq": 8
      // };
      // console.log("portraitStates:", this.portraitStates[modelStatesIndex[this.chatModelInfo.name]]);
      // if (!this.portraitStates[modelStatesIndex[this.chatModelInfo.name]]) {
      //   return;
      // }

      console.log("send_path_detect, model_name: ", this.chatModelInfo.name);
      console.log("send_path_detect, message: ", message);
      // console.log("send_path_detect, model_id: ", this.chatModelInfo.id);
      console.log("sequence信息获取: ", this.chatModelInfo.sequence);

      console.log("test_curr_state: ", this.portraitStates[this.chatModelInfo.sequence])
      if (!this.portraitStates[this.chatModelInfo.sequence]) {
        console.warn(
          '[send] portraitStates 未激活，静默中断发送。sequence=',
          this.chatModelInfo.sequence,
          'model=',
          this.chatModelInfo.name,
          'portraitStates=',
          JSON.parse(JSON.stringify(this.portraitStates))
        );
        this.$message.warning('当前主窗口模型未激活，请重新切换一次模型后再发送');
        return;
      }
      console.log("test_curr_state: ", this.portraitStates[this.chatModelInfo.sequence])

      formData.append('isHistoryUsed', this.isHistoryUsed);
      formData.append('isSummaryUsed', this.isSummaryUsed);
      // formData.append('isMemorySystemUsed', this.isMemorySystemUsed !== false);
      formData.append('isMemorySystemUsed', !!this.isMemorySystemUsed);
      formData.append('rounds', this.rounds)

      formData.append('realName', localStorage.getItem('realName'));
      formData.append('userbookName', localStorage.getItem('userId'));
      formData.append('sceneName', localStorage.getItem('sceneName'));
      formData.append('subSceneName', this.subSceneName || localStorage.getItem('subSceneName') || '');

      formData.append('choosedCardIdList', this.choosedCardIdList)
      let seed = localStorage.getItem('seed');
      let seednumber = 0;
      if (seed === 'topic') { seednumber = 1; }
      else if (seed === 'question') { seednumber = 2; }
      else { seednumber = 0; }
      formData.append('seed', seednumber); // 默认为0，topic是1，question是2

      // console.log("发送的消息内容：", formData);
      // 打印formData中的所有键值对
      for (let pair of formData.entries()) {
        console.log("formData", `${pair[0]}: ${pair[1]}`);
      }

      // 后端逻辑
      let paramFormData = new FormData();
      // let paramString = JSON.stringify(this.params);

      const runtime_params = modelManager.getHyperParamsDictionary()
      let paramString = JSON.stringify(runtime_params);

      console.log("send_param_detect, paramString:", runtime_params)
      console.log("send_param_detect, old_param:", this.params)
      paramFormData.append('params', paramString);
      paramFormData.append('modelID', this.chatModelInfo.id)
      paramFormData.append('username', username);
      paramFormData.append('windowId', this.$attrs.windowId);

      paramFormData.append('message', message);
      paramFormData.append('filenamelist', filenamelist);
      paramFormData.append('rightSelectList', rightSelectList);
      paramFormData.append('isHistoryUsed', this.isHistoryUsed);
      // paramFormData.append('isMemorySystemUsed', this.isMemorySystemUsed !== false);
      paramFormData.append('isMemorySystemUsed', !!this.isMemorySystemUsed);
      paramFormData.append('rounds', this.rounds);

      paramFormData.append('originRealName', originRealName)
      paramFormData.append('choosedCardIdList', this.choosedCardIdList)

      // 🔥 如果使用了tab增强后的问题，传递核心关键词（通过props传递）
      if (this.coreKeyword) {
        paramFormData.append('coreKeyword', this.coreKeyword);
      }
      this.appendCrossNotebookParams(paramFormData);

      // 用于给后端区分是主窗口综合回答还是普通回答，后端据此判断是否需要将中间结果chat_with_files_params保留到临时tmp
      paramFormData.append('mode', 'normal')
      paramFormData.append('socraticBoundMessage', message)
      // 主窗口上一轮问答（接续上下文），供 flash 判定是否反问
      if (socraticPrevTurn && typeof socraticPrevTurn === 'object') {
        const pq = String(socraticPrevTurn.question || '').trim();
        const pa = String(socraticPrevTurn.answer || '').trim();
        if (pq) paramFormData.append('socraticPrevQuestion', pq);
        if (pa) paramFormData.append('socraticPrevAnswer', pa);
      }

      this.LUI2_plus = false
      let answer = "";

      // 记录第一次回答的计时信息
      const firstAnswerStartTime = Date.now();
      let firstTokenTime = null;
      let ragSearchTime = 0;  // RAG搜索用时

      // 首先执行 chat_sendParams
      chat_sendParams(paramFormData)
      .then(response => {
        // 当 chat_sendParams 成功执行后，才执行 chat_send
        console.log("chat_sendParams response:", response);
        if (response && response.socratic_should_counter_ask) {
          console.log(
            `[${this.$attrs.windowId}] 本轮首答为语义反问；慢思考深评后迭代将继续加深反问`,
            response.socratic_analysis || ''
          );
        }
        return chat_send(this.chatModelInfo.name, formData, this.$attrs.windowId); // 返回 chat_send 的 Promise，以便在下一个 .then 中处理
      })
      .then(response => {
        // 处理 chat_send 的响应
        const reader = response.body.getReader(); // 使用响应的ReadableStream来处理数据

        // 开始流式输出 - 启用中断按钮
        this.startStreaming();

        // 后端传回数据，显示
        const processStream = () => {
          const decoder = new TextDecoder('utf-8');
          reader.read().then(({done, value}) => {
            if (done) {
              console.log(`[${this.$attrs.windowId}] Stream reading complete`);
              console.log(`[${this.$attrs.windowId}] answer长度: ${answer.length}`);

              // 保存中断状态（在endStreaming重置之前）
              const wasInterrupted = this.isInterrupted;
              console.log(`[${this.$attrs.windowId}] wasInterrupted: ${wasInterrupted}`);

              // 结束流式输出 - 禁用中断按钮
              this.endStreaming();

              // 计算第一次回答的总时间和首token时间
              const firstAnswerEndTime = Date.now();
              const firstAnswerTotalTime = ((firstAnswerEndTime - firstAnswerStartTime) / 1000).toFixed(2);
              const firstAnswerFirstTokenTime = firstTokenTime ? ((firstTokenTime - firstAnswerStartTime) / 1000).toFixed(2) : 'N/A';
              console.log(`[${this.$attrs.windowId}] 第一次回答用时 - 总时间: ${firstAnswerTotalTime}s, 首token: ${firstAnswerFirstTokenTime}s`);

              // 对话结束后，发送请求获取相关问题
              console.log(`[${this.$attrs.windowId}] chatEnd: ${this.chatEnd}`);
              console.log(`[${this.$attrs.windowId}] windowID: ${this.$attrs.windowId}`);
              
              const isValid = this.isValidAnswer(answer);
              console.log(`[${this.$attrs.windowId}] isValidAnswer: ${isValid}`);
              
              if (isValid) {
                // 检查是否已被中断，如果中断则不进行深评和迭代
                if (wasInterrupted) {
                  console.log(`[${this.$attrs.windowId}] [中断检测] 首轮回答已中断，跳过深评和迭代`);
                  this.$message.info('已中断，跳过深评和迭代流程');
                  // 在消息末尾添加中断提示
                  this.chatList[this.chatList.length - 1].msg += '\n\n---\n\n⚠️ 回答已被用户中断，跳过深评和迭代';
                  this.chatEnd = true;
                  // 中断后仍需触发update:answerList事件（通知父组件窗口完成）
                  this.$emit('update:answerList', message, filenamelist, answer, this.chatModelInfo.name, this.$attrs.windowId);
                  return;
                }

                console.log(`[${this.$attrs.windowId}] 准备进行红蓝卡标评估`);
                // 新增：每个窗口回答完成后进行红蓝卡标评估和迭代
                const cleanedQuestion = this.cleanCodeBlocks(message);
                let QAForEval = "提问：\n" + cleanedQuestion + "\n回答：\n" + answer;
                console.log(`[${this.$attrs.windowId}] 窗口回答完成，准备进行红蓝卡标评估，answer长度: ${answer.length}`);

                let formDataScene = new FormData();
                formDataScene.append('scene', localStorage.getItem('sceneName'));
                formDataScene.append('subScene', localStorage.getItem('subSceneName'));

                console.log(`[${this.$attrs.windowId}] 准备调用getSceneSummary获取场景摘要`);
                getSceneSummary(formDataScene).then(data => {
                  console.log(`[${this.$attrs.windowId}] getSceneSummary返回，error_num: ${data.error_num}`);
                  if(data.error_num === 0) {
                    let sceneName = localStorage.getItem('sceneName');
                    let subSceneName = localStorage.getItem('subSceneName');
                    console.log(`[${this.$attrs.windowId}] 场景子场景摘要获取成功：`, sceneName, subSceneName, data.summary);
                    // QAForEval = "目前的场景是：" + sceneName + "，子场景阶段是：" + subSceneName + "\n其摘要为：" + data.summary + "\n\n待评文本如下：\n" + QAForEval;
                    // 场景摘要只保留前50字（减少输入冗余）
                    const summaryShort = data.summary && data.summary.length > 50 ? data.summary.substring(0, 50) + '...' : data.summary;
                    // 存储场景摘要供后续使用（第二次深评）
                    this.sceneSummaryShort = summaryShort;
                    QAForEval = "目前的场景是：" + sceneName + "，子场景阶段是：" + subSceneName + "\n其摘要为：" + summaryShort + "\n\n待评文本如下：\n" + QAForEval;
                  
                    // 调用新方法进行评估和迭代，传递第一次回答的计时信息
                    const timingInfo = {
                      ragSearchTime: ragSearchTime,
                      firstAnswerTotal: firstAnswerTotalTime,
                      firstAnswerFirstToken: firstAnswerFirstTokenTime
                    };
                    
                    // 在开始深评前重置中断状态，因为第一次回答已经完成
                    // 后续的中断将针对深评流程
                    // this.isInterrupted = false;
                    
                    console.log(`[${this.$attrs.windowId}] 准备调用windowAnswerWithEvalAndIteration开始深评流程`);
                    this.windowAnswerWithEvalAndIteration(QAForEval, answer, timingInfo).then(() => {
                      this.chatEnd = true;
                      // 迭代完成后，触发update:answerList事件（通知父组件窗口完成）
                      this.$emit('update:answerList', message, filenamelist, answer, this.chatModelInfo.name, this.$attrs.windowId);
                      
                      // 获取相关问题
                      let relQueFormData = new FormData();
                      relQueFormData.append('username', username);
                      relQueFormData.append('message', message);
                      relQueFormData.append('filenamelist', filenamelist);
                      relQueFormData.append('rightSelectList', rightSelectList);
                      relQueFormData.append('windowId', this.$attrs.windowId);
                      relQueFormData.append('model_id', this.chatModelInfo.id);
                      relQueFormData.append('answer', answer);
                      relQueFormData.append('originRealName', originRealName);
                      // rel_questions_request(relQueFormData)
                      this.getRelQuestionsWithDepthSuggestion(relQueFormData, message, answer, username)
                      .then(response => {
                        // 后端传回rel_questions
                        let rel_questions = response['rel_questions'];
                        for (let i = 0; i < rel_questions.length; i++) {
                          this.questionContents[i] = rel_questions[i];
                        }
                        // this.$emit('update:questionContents', this.questionContents);
                        this.$emit('update:questionContents', rel_questions);
                        if(this.isPlus === true) {
                          this.LUI2_plus = true;
                        }
                      });
                    }).catch(error => {
                      console.error(`[${this.$attrs.windowId}] 评估迭代过程出错:`, error);
                      this.chatEnd = true;
                      // 即使出错也要触发update:answerList事件
                      this.$emit('update:answerList', message, filenamelist, answer, this.chatModelInfo.name, this.$attrs.windowId);
                      
                      // 获取相关问题
                      let relQueFormData = new FormData();
                      relQueFormData.append('username', username);
                      relQueFormData.append('message', message);
                      relQueFormData.append('filenamelist', filenamelist);
                      relQueFormData.append('rightSelectList', rightSelectList);
                      relQueFormData.append('windowId', this.$attrs.windowId);
                      relQueFormData.append('model_id', this.chatModelInfo.id);
                      relQueFormData.append('answer', answer);
                      relQueFormData.append('originRealName', originRealName);
                      this.getRelQuestionsWithDepthSuggestion(relQueFormData, message, answer, username)
                      .then(response => {
                        let rel_questions = response['rel_questions'];
                        for (let i = 0; i < rel_questions.length; i++) {
                          this.questionContents[i] = rel_questions[i];
                        }
                        this.$emit('update:questionContents', rel_questions);
                        if(this.isPlus === true) {
                          this.LUI2_plus = true;
                        }
                      });
                    });
                  } else {
                    console.error(`[${this.$attrs.windowId}] 场景子场景摘要获取失败，error_num: ${data.error_num}`);
                    this.$message.error('场景子场景摘要获取失败');
                    this.chatEnd = true;
                    // 场景摘要失败也要触发update:answerList事件
                    this.$emit('update:answerList', message, filenamelist, answer, this.chatModelInfo.name, this.$attrs.windowId);
                    
                    // 获取相关问题
                    let relQueFormData = new FormData();
                    relQueFormData.append('username', username);
                    relQueFormData.append('message', message);
                    relQueFormData.append('filenamelist', filenamelist);
                    relQueFormData.append('rightSelectList', rightSelectList);
                    relQueFormData.append('windowId', this.$attrs.windowId);
                    relQueFormData.append('model_id', this.chatModelInfo.id);
                    relQueFormData.append('answer', answer);
                    relQueFormData.append('originRealName', originRealName);
                    this.getRelQuestionsWithDepthSuggestion(relQueFormData, message, answer, username)
                    .then(response => {
                      let rel_questions = response['rel_questions'];
                      for (let i = 0; i < rel_questions.length; i++) {
                        this.questionContents[i] = rel_questions[i];
                      }
                      this.$emit('update:questionContents', rel_questions);
                      if(this.isPlus === true) {
                        this.LUI2_plus = true;
                      }
                    });
                  }
                }).catch(error => {
                  console.error('获取场景摘要出错:', error);
                  this.chatEnd = true;
                  // 场景摘要失败也要触发update:answerList事件
                  this.$emit('update:answerList', message, filenamelist, answer, this.chatModelInfo.name, this.$attrs.windowId);
                  
                  // 获取相关问题
                  let relQueFormData = new FormData();
                  relQueFormData.append('username', username);
                  relQueFormData.append('message', message);
                  relQueFormData.append('filenamelist', filenamelist);
                  relQueFormData.append('rightSelectList', rightSelectList);
                  relQueFormData.append('windowId', this.$attrs.windowId);
                  relQueFormData.append('model_id', this.chatModelInfo.id);
                  relQueFormData.append('answer', answer);
                  relQueFormData.append('originRealName', originRealName);
                  this.getRelQuestionsWithDepthSuggestion(relQueFormData, message, answer, username)
                  .then(response => {
                    let rel_questions = response['rel_questions'];
                    for (let i = 0; i < rel_questions.length; i++) {
                      this.questionContents[i] = rel_questions[i];
                    }
                    this.$emit('update:questionContents', rel_questions);
                    if(this.isPlus === true) {
                      this.LUI2_plus = true;
                    }
                  });
                });
              } else {
                console.log(`[${this.$attrs.windowId}] 此窗口isValidAnswer: false，answer长度: ${answer.length}`);
                console.log(`[${this.$attrs.windowId}] answer内容前100字: ${answer.substring(0, 100)}`);
                this.chatEnd = true;
                // 即使回答无效也要触发update:answerList事件
                this.$emit('update:answerList', message, filenamelist, answer, this.chatModelInfo.name, this.$attrs.windowId);
              }
              return;
            }
            const resp = decoder.decode(value);
            // console.log('Processed chunk:', resp);
            let responseData;
            // 使用正则表达式匹配和提取每个独立的 JSON 对象
            const jsonObjects = resp.match(/{[\s\S]*?}(?=\s*{|$)/g);
            if (jsonObjects) {
              jsonObjects.forEach(jsonObject => {
                // responseData = JSON.parse(jsonObject);
                try {
                  responseData = JSON.parse(jsonObject);
                } catch (parseError) {
                  // 🔥 流式传输中可能遇到不完整的 JSON，跳过并继续处理下一个
                  console.warn('[流式解析] 跳过无效的 JSON 片段:', parseError.message, 'JSON片段:', jsonObject.substring(0, 50) + '...');
                  return; // 跳过当前不完整的 JSON，继续处理下一个
                }

                // 处理session_init消息（会话初始化）
                if (responseData.type === 'session_init') {
                  this.currentSessionId = responseData.session_id;
                  console.log('[会话初始化] session_id:', this.currentSessionId);
                  return; // 不处理内容，继续下一个
                }
                
                // 处理interrupt消息（响应被中断）
                if (responseData.type === 'interrupt') {
                  console.log('[中断] 收到中断消息:', responseData.message);
                  this.isInterrupted = true;
                  this.$message.warning(responseData.message || '响应已被中断');
                  answer += '\n\n---\n\n⚠️ ' + (responseData.message || '响应已被中断');
                  // 立即结束流式读取
                  this.endStreaming();
                  return;
                }
                
                // 处理timeout消息（会话超时）
                if (responseData.type === 'timeout') {
                  console.log('[超时] 会话超时:', responseData.message);
                  this.$message.warning(responseData.message || '会话已超时');
                  answer += '\n\n---\n\n⏱️ ' + (responseData.message || '会话已超时');
                  this.endStreaming();
                  return;
                }

                // 处理解析后的 JSON 数据
                // if(this.chatModelInfo.name == response["model"]) {
                let content = responseData["content"];

                // 保存session_id（兼容老版本后端，第一个chunk中可能包含）
                if (responseData["session_id"] && !this.currentSessionId) {
                  this.currentSessionId = responseData["session_id"];
                  console.log(`[会话] 保存session_id: ${this.currentSessionId}`);
                }

                // 修复代码块闭合问题
                content = this.fixCodeBlockClosure(answer, content);

                // 记录首token时间和RAG搜索时间
                if (firstTokenTime === null && content && content.length > 0) {
                  firstTokenTime = Date.now();
                }
                
                // 获取RAG搜索用时和腐烂度算法评分（只在第一个chunk中有）
                if (responseData["rag_search_time"] !== undefined) {
                  ragSearchTime = responseData["rag_search_time"];
                  console.log(`[DEBUG] 收到后端RAG搜索时间: ${ragSearchTime}s`);
                }
                if (responseData["rot_score_algorithmic"] !== undefined) {
                  this.rotScoreAlgorithmic = responseData["rot_score_algorithmic"];
                  console.log(`[DEBUG] 收到后端腐烂度算法评分: ${this.rotScoreAlgorithmic}`);
                }
                if (responseData["rag_sample_text"] !== undefined) {
                  this.ragSampleText = responseData["rag_sample_text"];
                  let chineseCount = (this.ragSampleText.match(/[\u4e00-\u9fa5]/g) || []).length;
                  let englishWordCount = this.ragSampleText.trim().split(/\s+/).length;
                  if (chineseCount > 0) {
                    console.log(`[DEBUG] 收到后端RAG样本文档，中文字数: ${this.ragSampleText.length}`);
                  } else {
                    console.log(`[DEBUG] 收到后端RAG样本文档，英文单词数: ${englishWordCount}`);
                  }
                }
                if (responseData["history_sample_text"] !== undefined) {
                  this.historySampleText = responseData["history_sample_text"];
                  console.log(`[DEBUG] 收到后端历史对话样本，字数: ${this.historySampleText.length}`);
                }
                if (responseData["doc_confidence_score"] !== undefined) {
                  this.docConfidenceScore = responseData["doc_confidence_score"];
                  console.log(`[DEBUG] 收到后端文档置信度: ${this.docConfidenceScore}`);
                }

                answer += content;
                // console.log(responseData["model"] + ": " + content);
                let timeParams = responseData['nowParams']
                let params = { modelsId: this.chatModelInfo.id };
                let res = getChatMsg(params);
                let modelMsg = {
                  headImg: res[0].headImg,
                  name: res[0].name,
                  time: getTime(),
                  msg: content,
                  chatType: 0, //信息类型，0文字，1图片
                  uid: this.chatModelInfo.id, //uid
                  checked: false,
                  timeParams: timeParams,
                  seed: responseData["seed"],
                };
                this.shouldScroll = true;
                this.sendMsg(modelMsg);
              });
            } else {
              console.error('No JSON objects found in the stream:', resp);
              // this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + resp);
            }
            // 继续读取下一块数据
            processStream();
          })
        };
        processStream();
      })
      .catch(error => {
        // 结束流式输出 - 禁用中断按钮
        this.endStreaming();

        // 处理两个请求中的任何一个发生的错误
        console.error("An error occurred:", error);
        this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + error);
        // localStorage.setItem('userId', localStorage.getItem('realName'));
        // router.push('/home');
        // alert("问答发生了错误，请重新进入笔记本，最好重新登陆！原因可能是请求总字数过长或大模型余额不足，前者请减少重试，后者请告知管理员充值");
      });
    },
    
    //发送表情
    sendEmoji(msg) {
      let chatMsg = {
        headImg: require("@/assets/img/head_portrait.jpg"),
        name: "大毛是小白",
        time: "09：12 AM",
        msg: msg,
        chatType: 1, //信息类型，0文字，1图片
        extend: {
          imgType: 1, //(1表情，2本地图片)
        },
        uid: "1001",
        checked: false
      };
      this.sendMsg(chatMsg);
      this.clickEmoji();
    },
    //发送本地图片
    sendImg(e) {
      let _this = this;
      let chatMsg = {
        headImg: require("@/assets/img/head_portrait.jpg"),
        // name: "admin",
        name: localStorage.getItem('userId'),
        time: getTime(),
        msg: "",
        chatType: 1, //信息类型，0文字，1图片, 2文件
        extend: {
          imgType: 2, //(1表情，2本地图片)
        },
        uid: "1001",
        checked: false,
      };
      let files = e.target.files[0]; //图片文件名
      if (!e || !window.FileReader) return; // 看是否支持FileReader
      let reader = new FileReader();
      reader.readAsDataURL(files); // 关键一步，在这里转换的
      reader.onloadend = function () {
        chatMsg.msg = this.result; //赋值
        _this.srcImgList.push(chatMsg.msg);
      };
      this.sendMsg(chatMsg);
      e.target.files = null;
    },
    //发送文件（支持一次多选，须为同一 MIME 类别）
    getUploadSupportedTypes() {
      return {
        "application/pdf": 4,
        "text/plain": 6,
        "image/png": 7,
        "image/jpeg": 8,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": 9,
        "application/vnd.ms-excel": 10, // Excel .xls
        "audio/mpeg": 11, // MP3
        "audio/wav": 11, // WAV
        "audio/wave": 11, // WAV (alt)
        "audio/x-wav": 11, // WAV (alt)
        "audio/ogg": 11, // OGG
        "audio/mp4": 11, // M4A
        "audio/x-m4a": 11, // M4A (alt)
        "audio/webm": 11, // WebM
        "audio/aac": 11, // AAC
        "audio/flac": 11 // FLAC
      };
    },
    getUploadFileCategory(file) {
      const supportedTypes = this.getUploadSupportedTypes();
      const type = file?.type || "";
      if (!supportedTypes.hasOwnProperty(type)) {
        return null;
      }
      if (type === "image/png" || type === "image/jpeg") return "image";
      if (
        type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
        type === "application/vnd.ms-excel"
      ) {
        return "excel";
      }
      if (type === "application/pdf") return "pdf";
      if (type === "text/plain") return "text";
      return type;
    },
    uploadCategoryLabel(category) {
      if (category === "pdf") return "PDF";
      if (category === "text") return "TXT";
      if (category === "image") return "图片";
      if (category === "excel") return "Excel";
      return "未知类型";
    },
    async sendFile(e) {
      const files = Array.from(e?.target?.files || []);
      if (e?.target) {
        e.target.value = "";
      }
      if (!files.length) {
        this.$message.error("您没有选择文件!");
        return;
      }
      const firstCat = this.getUploadFileCategory(files[0]);
      if (!firstCat) {
        this.$message.error(
          `文件 ${files[0].name} 类型不支持！目前仅支持 PDF、TXT 文本文件、PNG、JPG 图片文件以及 Excel 文件。`
        );
        return;
      }
      const mixed = files.find((f) => this.getUploadFileCategory(f) !== firstCat);
      if (mixed) {
        this.$message.error(
          `一次只能选择同一类文件（例如全部为 ${this.uploadCategoryLabel(firstCat)}）。` +
            `「${mixed.name}」与已选类型不一致。`
        );
        return;
      }
      this.uploadFileQueue.push(...files);
      this.drainUploadFileQueue();
    },
    drainUploadFileQueue() {
      while (
        this.uploadFileQueue.length > 0 &&
        this.activeUploads < this.maxConcurrentUploads
      ) {
        const file = this.uploadFileQueue.shift();
        this.activeUploads++;
        this.sendSingleFile(file).finally(() => {
          this.activeUploads--;
          this.drainUploadFileQueue();
        });
      }
    },
    async sendSingleFile(file) {

      if (!file) {
        return;
      }

      const supportedTypes = this.getUploadSupportedTypes();
      if (!supportedTypes.hasOwnProperty(file.type)) {
        const fileName = (file.name || '').toLowerCase();
        const audioExtensions = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'];
        const isAudioFile = audioExtensions.some(ext => fileName.endsWith(ext));
        if (isAudioFile) {
          supportedTypes[file.type] = 11;
        } else {
          this.$message.error(`文件 ${file.name} 类型不支持！目前仅支持 PDF、TXT 文本文件、PNG、JPG 图片文件、Excel 文件以及音频文件（MP3、WAV、OGG、M4A等）。`);
          return;
        }
      }

      // 为每个文件创建一个上传状态对象
      this.uploadStates.set(file.name, {
        progressPercentage: 0,
        progressCurrentPage: 0,
        progressTotalPages: 1,
        progressCurrentItem: -1,
        progressTotalItems: -1,
      });
      
      // 计算当前通知的位置
      const currentOffset = this.notificationOffset * this.activeNotifications;
      this.activeNotifications++;

      // 为每个文件创建一个进度条通知
      console.log(`开始上传文件: ${file.name}, 类型: ${file.type}`);
      console.log((`上传状态对象:`, this.uploadStates.get(file.name)));
      const progressDialog = ElNotification({
        title: `文件上传进度 - ${file.name}`,
        message: () => {
            const state = this.uploadStates.get(file.name);
            if (!state) {
              return h('div', null, '文件上传完成');
            }
            return h('div', null, [
              h(ElProgress, {
                percentage: state.progressPercentage,
                status: state.progressPercentage >= 100 ? 'success' : '',
                format: () => {
                  if(state.progressCurrentItem >= 0 && state.progressTotalItems > 0) {
                    return `后台处理进度: ${state.progressPercentage}%`;
                  } else {
                    return `${state.progressCurrentPage}/${state.progressTotalPages} 页 (${state.progressPercentage}%)`;
                  }
                }
              })
            ]);
          },
          duration: 0,
          position: 'bottom-right',
          offset: currentOffset + 20, // 添加基础偏移，避免贴底
      });

      this.progressDialogs.set(file.name, progressDialog);

      // 保存文件类型信息（与旧版一致）
      const fileTypeNumber = supportedTypes[file.type];
      const audioMimeTypes = ['audio/mpeg', 'audio/wav', 'audio/wave', 'audio/x-wav', 'audio/ogg',
                              'audio/mp4', 'audio/x-m4a', 'audio/webm', 'audio/aac', 'audio/flac'];
      const audioExtensions = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'];
      const isAudioFileType = audioMimeTypes.includes(file.type) ||
                             audioExtensions.some(ext => file.name.toLowerCase().endsWith(ext));

      try {
        // 读取文件内容
        const fileData = await this.readFileAsDataURL(file);
        const formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('realName', localStorage.getItem('realName'));
        formData.append('model_id', this.chatModelInfo.id);
        formData.append('filename', file.name);
        formData.append('file', fileData.split(',')[1]);
        formData.append('filetype', fileTypeNumber);

        // 初始化上传
        const initResponse = await initFileUpload(formData);
        if (initResponse.error_num === 0) {
          const { task_id, total_pages } = initResponse;
          const state = this.uploadStates.get(file.name);
          console.log(`文件 ${file.name} 上传任务 ID: ${task_id}, 总页数: ${total_pages}`);
          state.progressTotalPages = total_pages > 0 ? total_pages : 1;
          formData.append('task_id', task_id);

          // 创建进度监听
          const eventSource = new EventSource(`${API_BASE_URL}/api/upload_progress/${task_id}/`);
          
          eventSource.onmessage = (event) => {
            try {
              const data = JSON.parse(event.data);
              const state = this.uploadStates.get(file.name);
              // const dialog = this.progressDialogs.get(file.name);
              console.log("data", data);
              console.log("uploadStates", this.uploadStates)
              state.progressCurrentPage = data.current_page || 0;
              state.progressTotalItems = data.total_items || 0;
              state.progressCurrentItem = data.current_item ?? -1; // 使用空值合并运算符
              console.log(`文件 ${file.name} 上传进度: ${state.progressCurrentItem}/${state.progressTotalItems} 项`);
              if(state.progressCurrentItem >= 0 && state.progressTotalItems > 0) {
                state.progressPercentage = Math.round((state.progressCurrentItem / state.progressTotalItems) * 100);
              } else {
                state.progressPercentage = Math.round((state.progressCurrentPage / state.progressTotalPages) * 90); // 预留10%给向量数据库处理
              }
              console.log(`文件 ${file.name} 上传进度: ${state.progressCurrentPage}/${state.progressTotalPages} 页 (${state.progressPercentage}%)`);

              // 更新进度条显示
              // dialog.message = h('div', null, [
              //   h(ElProgress, {
              //     percentage: state.progressPercentage,
              //     status: state.progressPercentage >= 100 ? 'success' : '',
              //     format: () => 
              //       `${state.progressCurrentPage}/${state.progressTotalPages} 页 (${state.progressPercentage}%)`
              //   })
              // ]);

              // 检查是否为Excel文件
              const isExcelFile = file.type === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' || 
                                  file.type === 'application/vnd.ms-excel';
                
              // 对于Excel文件，在4/4且90%时直接关闭
              if (isExcelFile && state.progressCurrentPage === 4 && state.progressTotalPages === 4 && state.progressPercentage >= 90) {
                console.log(`Excel文件 ${file.name} 达到4/4且90%，直接关闭进度条`);
                eventSource.close();
                this.progressDialogs.get(file.name).close();
                this.progressDialogs.delete(file.name);
                this.uploadStates.delete(file.name);
                this.activeNotifications--; // 减少活跃通知计数
                this.reorderNotifications(); // 重新排序剩余通知
                return; // 直接返回，不执行后续逻辑
              }

              // 在文件上传完成后关闭通知
              if (state.progressPercentage >= 100) {
                console.log(`文件 ${file.name} 上传完成，准备关闭进度条`);
                eventSource.close();
                
                if (isExcelFile) {
                  // Excel文件立即关闭
                  setTimeout(() => {
                    this.progressDialogs.get(file.name).close();
                    this.progressDialogs.delete(file.name);
                    this.uploadStates.delete(file.name);
                    this.activeNotifications--; // 减少活跃通知计数
                    this.reorderNotifications(); // 重新排序剩余通知
                    console.log(`Excel文件 ${file.name} 进度条已关闭`);
                  }, 500); // 稍微延迟500ms让用户看到100%状态
                } else {
                  // 其他文件类型保持原有逻辑
                  setTimeout(() => {
                    this.progressDialogs.get(file.name).close();
                    this.progressDialogs.delete(file.name);
                    this.activeNotifications--; // 减少活跃通知计数
                    this.reorderNotifications(); // 重新排序剩余通知
                  }, 1000);
                }
              }
            } catch (e) {
              console.error(`解析文件 ${file.name} 的进度数据失败:`, e);
              eventSource.close();
              this.progressDialogs.get(file.name).close();
              this.progressDialogs.delete(file.name);
              // this.uploadStates.delete(file.name);
              this.$message.error(`文件 ${file.name} 进度数据解析失败`);
            }
          };

          eventSource.onerror = () => {
            eventSource.close();
            this.progressDialogs.get(file.name)?.close();
            this.progressDialogs.delete(file.name);
            if (this.uploadStates.has(file.name)) {
              this.uploadStates.delete(file.name);
              this.activeNotifications = Math.max(0, this.activeNotifications - 1);
              this.reorderNotifications();
            }
            this.$message.error(`文件 ${file.name} 上传进度监听失败`);
          };

          // 开始实际上传
          this.$message.success(`文件 ${file.name} 开始上传，请耐心等待...`);
          this.$emit("waitFile", file.name, file.size);
          
          // 发送上传请求
          // await chat_upload(formData);
          const uploadResponse = await chat_upload(formData);
          this.$emit("update:fileList", file.name);
          this.$message.success(`文件 ${file.name} 上传成功！`);

          // 如果是PDF文件，通知父组件开始图片处理状态检查
          if (file.type === 'application/pdf' && uploadResponse.is_pdf) {
            this.$emit("pdfUploaded", file.name);
          }

          // 创建聊天消息
          const chatMsg = {
            headImg: require("@/assets/img/head_portrait.jpg"),
            name: localStorage.getItem('userId'),
            time: getTime(),
            msg: file,
            chatType: 2,
            extend: {
              fileType: fileTypeNumber
            },
            uid: "1001",
            checked: false
          };
          this.sendMsg(chatMsg);
        }
      } catch (error) {
        console.error(`文件 ${file.name} 上传失败:`, error);
        this.progressDialogs.get(file.name)?.close();
        this.progressDialogs.delete(file.name);
        if (this.uploadStates.has(file.name)) {
          this.uploadStates.delete(file.name);
          this.activeNotifications = Math.max(0, this.activeNotifications - 1);
          this.reorderNotifications();
        }
        this.$message.error(`文件 ${file.name} 上传失败: ${error.message || '未知错误'}`);
      }
    },

    // 辅助方法：将文件读取为 DataURL
    readFileAsDataURL(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = () => reject(new Error('文件读取失败'));
        reader.readAsDataURL(file);
      });
    },

    // 重新排序通知位置
    reorderNotifications() {
      let offset = 20;
      const maxOffset = window.innerHeight - 100; // 防止超出屏幕
      
      this.progressDialogs.forEach(dialog => {
        if (dialog.$el) {
          offset = Math.min(offset, maxOffset);
          dialog.$el.style.bottom = `${offset}px`;
          offset += this.notificationOffset;
        }
      });
    },

    // 检查是否有卡片操作权限（作者或群组协作用户）
    hasCardOperationPermission() {
      const isAuthor = localStorage.getItem('originRealName') === localStorage.getItem('realName');
      
      // 如果是作者，直接返回true
      if (isAuthor) return true;
      
      // 检查是否为群组本子协作用户
      const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
      if (currentNotebook.syncUsers && currentNotebook.syncUsers !== '') {
        const syncUsers = currentNotebook.syncUsers.split(',').map(user => user.trim()).filter(user => user);
        const currentUser = localStorage.getItem('originRealName');
        return syncUsers.includes(currentUser);
      }
      
      return false;
    },

    // 中断相关方法
    // 处理中断按钮点击
    async handleInterrupt() {
      try {
        const username = localStorage.getItem('userId');
        const model_id = this.chatModelInfo.id;
        
        console.log(`[中断] 用户点击中断按钮 - 窗口: ${this.$attrs.windowId}, 模型: ${model_id}`);
        
        // 先中止深评的HTTP请求（如果正在进行）
        if (this.evalAbortController) {
          console.log('[中断] 中止第一次深评HTTP请求');
          this.evalAbortController.abort();
        }
        
        if (this.secondEvalAbortController) {
          console.log('[中断] 中止第二次深评HTTP请求');
          this.secondEvalAbortController.abort();
        }
        
        // 立即标记为已中断，防止继续输出
        this.isInterrupted = true;
        
        // 调用中断API，使用强制中断模式
        const requestData = {
          username: username,
          model_id: model_id,
          force: true  // 强制中断，即使会话卡住也要中断
        };
        
        // 如果有session_id，传递给后端以便更精确地中断
        if (this.currentSessionId) {
          requestData.session_id = this.currentSessionId;
          console.log(`[中断] 会话ID: ${this.currentSessionId}`);
        } else {
          console.warn('[中断] 未找到session_id，使用model_id进行中断');
        }
        
        const response = await interruptResponse(requestData);
        
        if (response && (response.success || response.error_num === 0)) {
          console.log('[中断] 中断请求成功', response);
          this.$message.success('正在中断AI响应...');
        } else {
          console.error('[中断] 中断请求失败:', response);
          this.$message.warning('中断请求已发送，但响应异常');
        }
      } catch (error) {
        console.error('[中断] 中断请求异常:', error);
        // 即使请求失败，前端也已标记为中断状态
        this.$message.warning('中断请求发送失败，但本地已停止输出');
      }
    },

    // 开始流式输出时调用
    startStreaming() {
      console.log('[流式] 开始流式输出 - 窗口:', this.$attrs.windowId);
      this.isStreaming = true;
      // 每次开始新的流式输出时重置中断状态
      this.isInterrupted = false;
      // 注意：currentSessionId会在接收到后端第一个chunk时自动设置
    },

    // 结束流式输出时调用
    endStreaming() {
      console.log('[流式] 结束流式输出 - 窗口:', this.$attrs.windowId);
      this.isStreaming = false;
      this.isInterrupted = false;
      // 清空session_id
      this.currentSessionId = null;
      // 清空中断控制器
      this.evalAbortController = null;
      this.secondEvalAbortController = null;
    },

    // 检查是否应该显示中断按钮
    shouldShowInterruptButton() {
      // 只要在流式输出中且未被中断，就显示中断按钮
      // 包括：普通回答、第一次深评、迭代回答、第二次深评
      if (!this.isStreaming || this.isInterrupted) {
        return false;
      }

      return true;
    }
  },
};
</script>

<style lang="scss" scoped>
.chat-window {
  width: 100%;
  height: 100%;
  position: relative;
  background-color: rgb(234, 234, 234);

  // 中断按钮容器
  .interrupt-button-container {
    position: absolute;
    top: 10px;  /* 调整顶部距离 */
    right: 10px;  /* 调整右侧距离 */
    z-index: 1000;
    cursor: pointer;

    .interrupt-button {
      display: flex;
      align-items: center;
      gap: 6px;  /* 减小图标和文字间距 */
      padding: 8px 16px;  /* 减小内边距 */
      background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
      border: none;
      border-radius: 20px;  /* 调整圆角 */
      box-shadow: 0 3px 12px rgba(238, 90, 36, 0.4);  /* 减小阴影 */
      cursor: pointer;
      transition: all 0.3s ease;

      &:hover {
        transform: translateY(-1px);  /* 减小悬停位移 */
        box-shadow: 0 4px 15px rgba(238, 90, 36, 0.6);
      }

      &:active {
        transform: translateY(0px);
      }

      .interrupt-icon {
        font-size: 16px;  /* 减小图标大小 */
        color: white;
      }

      .interrupt-text {
        font-size: 13px;  /* 减小文字大小 */
        font-weight: 600;
        color: white;
        letter-spacing: 0.3px;  /* 减小字间距 */
      }
    }
  }

  // 已中断提示
  .interrupted-indicator {
    position: absolute;
    top: 10px;  /* 调整顶部距离 */
    right: 10px;  /* 调整右侧距离 */
    z-index: 1000;
    display: flex;
    align-items: center;
    gap: 6px;  /* 减小图标和文字间距 */
    padding: 8px 16px;  /* 减小内边距 */
    background: linear-gradient(135deg, #95a5a6 0%, #7f8c8d 100%);
    border-radius: 20px;  /* 调整圆角 */
    box-shadow: 0 3px 12px rgba(127, 140, 141, 0.4);  /* 减小阴影 */

    .interrupted-icon {
      font-size: 16px;  /* 减小图标大小 */
      color: white;
    }

    .interrupted-text {
      font-size: 13px;  /* 减小文字大小 */
      font-weight: 600;
      color: white;
      letter-spacing: 0.3px;  /* 减小字间距 */
    }
  }

  .botoom {
    width: 100%;
    height: 100%;
    background-color: rgb(234, 234, 234);
    box-sizing: border-box;
    position: relative;

    .chat-content {
      width: 100%;
      height: 80%;
      overflow-y: scroll;
      padding: 20px;
      box-sizing: border-box;

      &::-webkit-scrollbar {
        width: 0;
        /* Safari,Chrome 隐藏滚动条 */
        height: 0;
        /* Safari,Chrome 隐藏滚动条 */
        display: none;
        /* 移动端、pad 上Safari，Chrome，隐藏滚动条 */
      }

      .chat-wrapper {
        position: relative;
        word-break: break-all;

        .chat-model {
          width: 100%;
          float: left;
          margin-bottom: 20px;
          display: flex;
          flex-direction: column;
          justify-content: flex-start;
          align-items: flex-start;

          .chat-text {
            max-width: 90%;
            padding: 20px;
            border-radius: 20px 20px 20px 5px;
            background-color: #fff;
            color: #000000;
            text-align: left;

            white-space: pre-wrap;
            font-size: 17px;
            text-indent: 2em;


            &:hover {
              background-color: rgb(234, 234, 234);
            }
          }

          .chat-img {
            img {
              width: 100px;
              height: 100px;
            }
          }

          .info-time {
            display: flex; // checkbox
            justify-content: space-between; // 左右两边分开
            align-items: center; // 垂直居中
            margin: 10px 0;
            color: #000000;
            font-size: 14px;
            text-align: left;
            width: 100%; // 确保容器占满宽度

            // 左侧信息容器
            .left-info {
              display: flex;
              align-items: center;
              flex-shrink: 0; // 防止被压缩

              img {
                width: 25px;
                height: 25px;
                border-radius: 50%;
                vertical-align: middle;
                margin-right: 10px;
              }

              span {
                color: rgb(101, 104, 115);
                margin-left: 10px;
                vertical-align: middle;
              }
            }

            // 右侧按钮容器
            .right-actions {
              display: flex;
              align-items: center;
              justify-content: flex-end; // 添加这行，使内部元素靠右对齐
              margin-right: 15px;
              flex-shrink: 0; // 防止被压缩
              
              img {
                width: 25px;
                height: 25px;
                border-radius: 50%;
              }

              .img-button {
                margin-left: 10px;
                margin-right: 5px;
                border: 0;
                transition: 0.3s;
                box-shadow: 0px 0px 5px 0px rgb(125, 125, 125);
                cursor: pointer;

                &:hover {
                  box-shadow: 0px 0px 10px 0px rgb(0, 0, 0);
                }
              }

              // 按钮容器样式
              .button-container {
                position: relative;
                // display: inline-block;
              }

              // 悬浮pin按钮样式
              .pin-overlay-button {
                position: absolute;
                top: -24px;
                left: 58%;
                transform: translateX(-50%);
                width: 20px;
                height: 20px;
                border-radius: 50%;
                border: 2px solid #e5e5e58d;
                box-shadow: 0px 3px 12px 0px rgba(0, 0, 0, 0.25);
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                z-index: 100;
                background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
                display: flex;
                align-items: center;
                justify-content: center;
                opacity: 0.95;
                animation: pulse 2s infinite;

                // 添加一个小的pin图标效果
                &::before {
                  content: "📌";
                  font-size: 12px;
                  color: white;
                  text-shadow: 0px 1px 2px rgba(0, 0, 0, 0.3);
                }

                &:hover {
                  transform: translateX(-50%) scale(1.2);
                  box-shadow: 0px 6px 20px 0px rgba(255, 107, 107, 0.5);
                  border-color: #ff6b6b;
                  opacity: 1;
                  background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%);
                  animation: none;
                }

                &:active {
                  transform: translateX(-50%) scale(1.1);
                  box-shadow: 0px 3px 12px 0px rgba(255, 107, 107, 0.4);
                }
              }

              // 添加脉冲动画
              @keyframes pulse {
                0% {
                  box-shadow: 0px 3px 12px 0px rgba(255, 107, 107, 0.4);
                }
                50% {
                  box-shadow: 0px 3px 12px 0px rgba(255, 107, 107, 0.8);
                }
                100% {
                  box-shadow: 0px 3px 12px 0px rgba(255, 107, 107, 0.4);
                }
              }

              .merge-button {
                margin-left: 10px;
                margin-right: 5px;
                border: 0;
                transition: 0.3s;
                box-shadow: 0px 0px 5px 0px rgb(125, 125, 125);
                cursor: pointer;

                &:hover {
                  box-shadow: 0px 0px 10px 0px rgb(0, 0, 0);
                }
              }

              .lui2-plus-icon {
                display: inline-block;
                width: auto;            /* 设置为自动，以适应内容 */
                height: auto;
                border-radius: 50%;
                color: #ffffff !important; /* 使用 !important 来确保这条规则的优先级最高 */
                text-align: center;
                line-height: 20px;
                font-size: 14px;
                margin-left: 15px;
                background-color: #6112b5;
                cursor: pointer;
                padding: 4px;           /* 内边距，确保文字不会太靠近边框 */
                box-sizing: border-box;  /* 边框计算在宽度和高度内 */
                &:hover {
                  background-color: #40057f;
                }
              }

              // .retry-button {
              //   margin-left: 10px;
              //   margin-right: 5px;
              //   border: 0;
              //   transition: 0.3s;
              //   box-shadow: 0px 0px 5px 0px rgb(125, 125, 125);
              //   cursor: pointer;
              //   // animation: spin 2s linear infinite;

              //   &:hover {
              //     box-shadow: 0px 0px 10px 0px rgb(0, 0, 0);
              //     animation: none;
              //   }
              // }
            }
          }
        }

        .chat-me {
          width: 100%;
          float: right;
          margin-bottom: 20px;
          position: relative;
          display: flex;
          flex-direction: column;
          justify-content: flex-end;
          align-items: flex-end;

          .chat-text {
            float: right;
            max-width: 90%;
            padding: 20px;
            border-radius: 20px 20px 5px 20px;
            background-color: rgb(29, 144, 245);
            color: #000000;
            text-align: left;
            white-space: pre-wrap;
            font-size: 17px;

            &:hover {
              background-color: rgb(26, 129, 219);
            }
          }

          .chat-img {
            img {
              max-width: 300px;
              max-height: 200px;
              border-radius: 10px;
            }
          }

          .info-time {
            margin: 10px 0;
            color: #000000;
            font-size: 14px;
            display: flex;
            justify-content: flex-end;
            text-align: left;

            img {
              width: 25px;
              height: 25px;
              border-radius: 50%;
              vertical-align: middle;
              margin-left: 10px;
            }

            span {
              line-height: 30px;
            }

            span:first-child {
              color: rgb(101, 104, 115);
              margin-right: 10px;
              vertical-align: middle;
            }
          }
        }
      }
    }

    .chatInputs {
      width: 90%;
      position: absolute;
      bottom: 0;
      margin: 3%;
      display: flex;

      .boxinput {
        width: 50px;
        height: 50px;
        background-color: rgb(66, 70, 86);
        border-radius: 15px;
        border: 1px solid rgb(80, 85, 103);
        position: relative;
        cursor: pointer;

        img {
          width: 30px;
          height: 30px;
          position: absolute;
          left: 50%;
          top: 50%;
          transform: translate(-50%, -50%);
        }
      }

      .emoji {
        transition: 0.3s;

        &:hover {
          background-color: rgb(46, 49, 61);
          border: 1px solid rgb(71, 73, 82);
        }
      }

      .inputs {
        width: 90%;
        height: 50px;
        background-color: rgb(66, 70, 86);
        border-radius: 15px;
        border: 2px solid rgb(34, 135, 225);
        padding: 10px;
        box-sizing: border-box;
        transition: 0.2s;
        font-size: 20px;
        color: #fff;
        font-weight: 100;
        margin: 0 20px;

        &:focus {
          outline: none;
        }
      }

      .send {
        background-color: rgb(29, 144, 245);
        border: 0;
        transition: 0.3s;
        box-shadow: 0px 0px 5px 0px rgb(0, 136, 255);

        &:hover {
          box-shadow: 0px 0px 10px 0px rgb(0, 136, 255);
        }
      }
    }


    .more-question {
      height: 10%;
      width: 90%;
      position: absolute;
      bottom: 10%;
      margin: 3%;
      display: flex;

      .question-div {
        align-items: center;
        justify-content: center;
        margin: 5px;
        padding: 5px;
        border-radius: 10px;
        background-color: rgba($color: #405267, $alpha: 0.3);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        user-select: none;
        color: rgb(205, 248, 255);
      }
    }


  }
}

.purple-bg {
  background-color: #ebe1fc !important;
}

.purple-bg-me {
  background-color: #bfa5ee !important; /* 比 #ebe1fc 稍深的紫色 */
}


.el-notification {
  transition: all 0.3s ease-in-out;
  
  &.is-progressbar {
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(5px);
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  }
}

// .lui2-plus-icon {
//   display: inline-block;
//   width: auto;            /* 设置为自动，以适应内容 */
//   height: auto;
//   border-radius: 50%;
//   color: #ffffff;
//   text-align: center;
//   line-height: 20px;
//   font-size: 14px;
//   margin-left: 15px;
//   background-color: #6112b5;
//   cursor: pointer;
//   padding: 4px;           /* 内边距，确保文字不会太靠近边框 */
//   box-sizing: border-box;  /* 边框计算在宽度和高度内 */
// }
@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>