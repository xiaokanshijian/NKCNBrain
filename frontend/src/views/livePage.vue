<template>
  
  <div class="textlive-backdrop">
    <div class="myDialogTextLive">

      <div class="share-actions">
        <h1>此本子可点评干预的操作流</h1>
        <div class="nav-close" @click="navClose">
          <i class="nav-close-icon"></i>
        </div>
      </div>

      <div class="button-container">
        <el-button style="background-color: mediumseagreen; color: #071a0e; border: 1px solid #071a0e;"
              @click="commentOlder">再前两次的操作流</el-button>
        <el-button style="background-color: darkolivegreen; color: #071a0e; border: 1px solid #071a0e;"
              @click="commentMiddle">再前一次的操作流</el-button>
        <el-button style="background-color: yellowgreen; color: #071a0e; border: 1px solid #071a0e;" 
              @click="commentNewest">最近一次的操作流</el-button>
        <!-- <el-button style="background-color: mediumspringgreen; color: #071a0e; border: 1px solid #071a0e;"
              @click="flashStatus">刷新当前监控状态</el-button> -->
        <el-select v-if="!isSelf" v-model="interventionLevel" placeholder="高级引控" style="width: 200px; margin-left: 20px;">
          <el-option
            value=""
            label="? 跟踪观察式干预"
          />
          <el-option
            value="questionGuidance"
            label="?? 问题引导式干预"
          />
          <el-option
            value="targetedGuidance"
            label="??? 目标导向式牵引"
          />
        </el-select>
      </div>

      <div class="text-boxes">
        <!-- 第二个 text-box，展示选中的消息详情 -->
        <div class="text-box">
          <div v-if="selectedMessage">
            <div class="message" v-for="(value, key) in selectedMessage.Specifics" :key="key" :class="getBubbleClass(key)">
              <div class="key">{{ key }}</div>
              <div class="value">{{ value }}</div>
            </div>
            <div v-if="selectedMessage.comments" class="message coacher">
              <div class="value">{{ selectedMessage.comments }}</div>
            </div>
            <div class="intervention-controls" v-if="interventionLevel">
              <div v-if="interventionLevel === 'targetedGuidance'" class="guidance-options">
                <!-- 添加判定选项 -->
                <div class="judgment-section" style="margin-bottom: 35px;">
                  <div style="margin-bottom: 10px; margin-top: 20px;">请您根据使用即回复情况，判定是否可继续使用NKCN：</div>
                  <div style="display: flex; justify-content: center;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                      <el-radio-group v-model="canContinue" style="margin-bottom: 15px;">
                        <el-radio :label="true">
                          <i class="el-icon-check" style="color: #67C23A; font-size: large;">√</i>
                        </el-radio>
                        <el-radio :label="false">
                          <i class="el-icon-close" style="color: #F56C6C; font-size: large;">×</i>
                        </el-radio>
                      </el-radio-group>
                      <el-button type="primary" size="small" @click="handleNKCNConfirm">确认</el-button>
                    </div>
                  </div>
                </div>
                <!-- 原有的下拉框 -->
                <el-select v-model="selectedGoal" placeholder="选择学习目标" style="width: 100%; margin-bottom: 10px;">
                  <el-option value="提升问题分析能力" label="提升问题分析能力" />
                  <el-option value="加强逻辑思维训练" label="加强逻辑思维训练" />
                  <el-option value="培养系统思考方式" label="培养系统思考方式" />
                </el-select>
                <el-select v-model="selectedSuggestion" placeholder="选择改进建议" style="width: 100%; margin-bottom: 10px;">
                  <el-option value="建议：尝试从多个角度分析问题" label="多角度分析" />
                  <el-option value="建议：注意总结经验和规律" label="经验总结" />
                  <el-option value="建议：思考问题的关联性" label="关联思考" />
                </el-select>
              </div>
              <div class="comment">
                <input v-model="commentInput" :placeholder="getPlaceholder()" />
                <button @click="sendComment">发送</button>
              </div>
            </div>
            <div v-else class="comment">
              <input v-model="commentInput" :placeholder="getPlaceholderUser()" />
              <button @click="sendComment">发送</button>
            </div>
          </div>
        </div>

        <!-- 第一个 text-box，展示消息列表 -->
        <div class="text-box">
          <div class="message" @click="selectMessage(item, index)" v-for="(item, index) in streamCommenting.stream" :key="index">
            <div class="time">{{ formatTime(item.time) }}</div>
            <div class="action">{{ item.action }}</div>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>
  
<script>
// import { ref } from 'vue'
import router from '@/router'
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElSelect, ElOption, ElRadio, ElRadioGroup } from 'element-plus'
import { get_context, coacher_comment, nkcn_continue, check_continue } from "@/api/chat/send_message"
import { stream } from 'xlsx';

export default {
  name: 'Live',
  components: {
      ElForm,
      ElFormItem,
      ElInput,
      ElButton,
      ElDialog,
      ElSelect,
      ElOption,
      ElRadio, 
      ElRadioGroup
  },
  data() {
    return {
      canContinue: null,  // 用于存储判定结果
      isControlled: false,
      isSelf: false,
      interventionLevel: '',
      selectedGoal: '',
      selectedSuggestion: '',

      isflashed: true,
      indexNodeCommented: 0,
      order: 0,
      contextAll: [],
      firstBookUser: '',
      firstBookName: '',
      firstBookContext: '',
      streamCommenting: {
        "beginTime": 0,
        "stream": [],
      },
      streamNewest: {
        "beginTime": 0,
        "stream": [],
      },
      streamMiddle: {
        "beginTime": 0,
        "stream": [],
      },
      streamOlder: {
        "beginTime": 0,
        "stream": [],
      },
      selectedMessage: null,
      commentInput: '',
      autoRefreshInterval: null
    }
  },
  mounted() {
    this.getTimeStreamPairs()
    this.autoRefreshInterval = setInterval(() => {
      this.flashStatus()
    }, 180000)

    if (localStorage.getItem('controlled') === 'true'){
      this.isControlled = true
    } else {
      this.isControlled = false
    }
    console.log("是否应该被控制：", this.isControlled)
  },
  beforeUnmount() {
    // 清理定时器
    if (this.autoRefreshInterval) {
      clearInterval(this.autoRefreshInterval)
    }
  },
  methods: {
    handleNKCNConfirm() {
      if(this.canContinue === null) {
        this.$message.error('请您先视情况选择√或×');
      } else {
        let formData = new FormData();
        formData.append('username', this.firstBookUser);
        formData.append('canContinue', this.canContinue);
        console.log(this.firstBookUser, this.canContinue, typeof this.canContinue)
        nkcn_continue(formData).then(response => {
          if (response.error_num === 0) {
            this.$message.success('提交成功！');
          } else {
            this.$message.error('提交失败');
          }
        });
      }
    },
    flashStatus() {
      let formData = new FormData();
      formData.append('username', this.firstBookUser);
      formData.append('bookname', this.firstBookName);
      get_context(formData).then(response => {
        if (response.error_num === 0) {
          this.firstBookContext = response.contextData
          if(this.firstBookContext !== "") {
            this.contextAll = JSON.parse(this.firstBookContext)
          }
          if(this.contextAll.length === 1) {
            this.streamNewest = this.contextAll[0]
          } else if(this.contextAll.length === 2) {
            this.streamMiddle = this.contextAll[0]
            this.streamNewest = this.contextAll[1]
          } else if(this.contextAll.length === 3) {
            this.streamOlder = this.contextAll[0]
            this.streamMiddle = this.contextAll[1]
            this.streamNewest = this.contextAll[2]
          } else {
          }
          this.streamCommenting = this.streamNewest
          this.isflashed = true
          setTimeout(() => { 
            this.isflashed = false
          }, 180000); 
          this.$message.success('刷新成功！');
        } else {
          this.$message.error('刷新失败');
        }
      });
    },
    selectMessage(item, index) {
      this.selectedMessage = item;
      this.indexNodeCommented = index; 
    },
    getBubbleClass(key) {
      return key.startsWith('human') ? 'bubble-right' : 'bubble-left';
    },
    sendComment() {
      if (this.isflashed === false) {
        alert("请您等待3分钟内自动刷新后再发送点评");
      } else {
        if (this.selectedMessage && this.commentInput.trim()) {
          let finalComment = this.commentInput;

          // 根据不同的干预级别添加额外的信息
          if (this.interventionLevel === 'questionGuidance') {
            finalComment = "————" + localStorage.getItem('realName') + ":\n" + `[等待回复] ${this.commentInput}\n请立即思考并回复上面的问题/要求！`;
          } else if (this.interventionLevel === 'targetedGuidance') {
            const goalPrefix = this.selectedGoal ? `[学习目标]\n${this.selectedGoal}` : '';
            finalComment = "————" + localStorage.getItem('realName') + ":\n" + `${goalPrefix}\n[高级引导]\n${this.selectedSuggestion || ''}\n[具体牵引指令]\n${this.commentInput}`;
          } else {
            finalComment = "————" + localStorage.getItem('realName') + ":\n" + this.commentInput
          }
          this.commentInput = finalComment

          // 更新 Specifics 字典、comments 字段
          // this.selectedMessage.Specifics['coacher'] += finalComment;
          // this.selectedMessage.comments += finalComment;
          
          let formData = new FormData();
          formData.append('username', this.firstBookUser);
          formData.append('bookname', this.firstBookName);

          if(this.contextAll.length === 1) {
            this.contextAll[0].stream[this.indexNodeCommented].Specifics['coacher'] += "\n\n" + this.commentInput;
            this.contextAll[0].stream[this.indexNodeCommented].comments += "\n\n" + this.commentInput;
          } else if(this.contextAll.length === 2) {
            if(this.order === 0) {
              this.contextAll[1].stream[this.indexNodeCommented].Specifics['coacher'] += "\n\n" + this.commentInput;
              this.contextAll[1].stream[this.indexNodeCommented].comments += "\n\n" + this.commentInput;
            } else {
              this.contextAll[0].stream[this.indexNodeCommented].Specifics['coacher'] += "\n\n" + this.commentInput;
              this.contextAll[0].stream[this.indexNodeCommented].comments += "\n\n" + this.commentInput;
            }
          } else if(this.contextAll.length === 3) {
            if(this.order === 0) {
              this.contextAll[2].stream[this.indexNodeCommented].Specifics['coacher'] += "\n\n" + this.commentInput;
              this.contextAll[2].stream[this.indexNodeCommented].comments += "\n\n" + this.commentInput;
            } else if(this.order === 1) {
              this.contextAll[1].stream[this.indexNodeCommented].Specifics['coacher'] += "\n\n" + this.commentInput;
              this.contextAll[1].stream[this.indexNodeCommented].comments += "\n\n" + this.commentInput;
            } else {
              this.contextAll[0].stream[this.indexNodeCommented].Specifics['coacher'] += "\n\n" + this.commentInput;
              this.contextAll[0].stream[this.indexNodeCommented].comments += "\n\n" + this.commentInput;
            }
          } else {
          }

          // 清空输入框
          this.commentInput = '';
          let contextString = JSON.stringify(this.contextAll);
          formData.append('context', contextString);
          formData.append('interventionLevel', this.interventionLevel);
          formData.append('who', localStorage.getItem('realName'));
          coacher_comment(formData).then(response => {
            if (response.error_num === 0) {
              this.$message.success('刷新成功！');
              if(localStorage.getItem('realName') === this.firstBookUser) {
                this.isControlled = response.controlled !== 0;
              }
            } else {
              this.$message.error('刷新失败');
            }
          });
        }
      }
    },
    formatTime(timestamp) {
      const date = new Date(timestamp);
      return date.toLocaleString();
    },
    commentNewest() {
      this.streamCommenting = this.streamNewest
      this.order = 0
    },
    commentMiddle() {
      this.streamCommenting = this.streamMiddle
      this.order = 1
    },
    commentOlder() {
      this.streamCommenting = this.streamOlder
      this.order = 2
    },
    getTimeStreamPairs() {
      this.firstBookUser = localStorage.getItem('firstBookUser')
      this.firstBookName = localStorage.getItem('firstBookName')
      this.firstBookContext = localStorage.getItem('firstBookContext')
      console.log(this.firstBookUser, this.firstBookName, this.firstBookContext, typeof(this.firstBookContext))

      if(this.firstBookUser === localStorage.getItem('realName')) {
        this.isSelf = true
      } else {
        this.isSelf = false
      }

      if(this.firstBookContext !== "") {
        this.contextAll = JSON.parse(this.firstBookContext)
      }
      if(this.contextAll.length === 1) {
        this.streamNewest = this.contextAll[0]
      } else if(this.contextAll.length === 2) {
        this.streamMiddle = this.contextAll[0]
        this.streamNewest = this.contextAll[1]
      } else if(this.contextAll.length === 3) {
        this.streamOlder = this.contextAll[0]
        this.streamMiddle = this.contextAll[1]
        this.streamNewest = this.contextAll[2]
      } else {
      }
      this.streamCommenting = this.streamNewest
    },
    getPlaceholder() {
      if (this.interventionLevel === 'questionGuidance') {
        return '输入问题或指令（此用户将暂停并回复，请您等待）';
      } else if (this.interventionLevel === 'targetedGuidance') {
        return '输入牵引性指令';
      }
      return '输入评论';
    },
    getPlaceholderUser() {
      if (this.isSelf === true) {
        return '回复您的领航员';
      } else {
        return '输入评论';
      }
    },
    navClose() {
      if(this.isControlled === true) {
        let formData = new FormData();
        formData.append('username', this.firstBookUser);
        check_continue(formData).then(response => {
          if (response.error_num === 0) {
            if (response.controlled === 0) {
              if(this.firstBookUser === localStorage.getItem('realName')) {
                // router.push('/main');
                // 在返回 main 之前设置标记
                localStorage.setItem('fromPath', '/main')
                router.push({
                  path: '/main',
                  query: { from: 'live', bookId: this.firstBookUser + "_" + this.firstBookName }
                });
              } else {
                localStorage.setItem('fromPath', '/live')
                router.push('/home');
              }
            } else {
              alert("领航员正在引控您，请查看你的操作流，找到领航员的提问/要求并认真回复后，才可退出继续使用");
            }
          } else {
            this.$message.error('请求失败');
          }
        });
      } else {
        if(this.firstBookUser === localStorage.getItem('realName')) {
          // router.push('/main');
          localStorage.setItem('fromPath', '/main')
          router.push({
            path: '/main',
            query: { from: 'live', bookId: this.firstBookUser + "_" + this.firstBookName }
          });
        } else {
          localStorage.setItem('fromPath', '/live')
          router.push('/home');
        }
      }
    },
  }
}
</script>
  

<style scoped>
.myDialogTextLive {
  position: relative;
  width: 1200px;
  height: 650px;
  border-radius: 10px;
  background-size: 100% 100%;
  background-color: rgba(105, 160, 137);
  border: 1px solid #5a7c66c2;
}
/* 遮罩层的样式 */
.textlive-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(22, 106, 54, 0.592);
  display: flex;
  justify-content: center;
  align-items: center;
}

.button-container {
  display: flex;
  justify-content: space-around;
  margin-bottom: 20px;
  max-width: 650px;
  margin-left: auto;
  margin-right: auto;
}

.text-boxes {
  display: flex;
  justify-content: space-between;
}

.text-box {
  flex: 1;
  background-color: rgba(255, 255, 255, 0.8);
  border: 1px solid #092212c4;
  border-radius: 10px;
  margin: 0 20px;
  padding: 20px;
  color: #071a0e;
  text-shadow: 0px 1px 1px rgba(155, 165, 135, 0.5);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3);
  text-align: center;
  height: 425px;
  font-weight: bold;
  overflow-y: auto;
}
.message {
  display: flex;
  flex-direction: column;
  background-color: #e1ffc7;
  padding: 10px;
  margin: 5px 4px;
  border-radius: 10px;
  max-width: 80%;
  word-wrap: break-word;
}
.time {
  font-size: 12px;
  color: #888;
  margin-bottom: 5px;
}
.action {
  font-size: 14px;
}

.bubble-right {
  align-self: flex-end;
  background-color: #83e054;
}

.bubble-left {
  align-self: flex-start;
  background-color: #1fb5ad;
}

.comment {
  display: flex;
  margin-top: 10px;
}

.comment input {
  flex: 1;
  padding: 5px;
  border: 1px solid #ccc;
  border-radius: 5px;
}

.comment button {
  margin-left: 10px;
  padding: 5px 10px;
  border: none;
  background-color: #4caf50;
  color: white;
  border-radius: 5px;
  cursor: pointer;
}

.coacher {
  background-color: #e0be58;
  align-self: flex-start;
}

.share-actions {
  color: rgb(37, 37, 37); 
  text-shadow: 0px 1px 1px #0d2d18df;
  text-align: center;
  margin-bottom: 10px;
  margin-top: 10px;
}

.nav-close {
  width: 4%;
  cursor: pointer;
  vertical-align: top;
  background-color: #50fbbfb4;
  justify-content: center;
  align-items: center;
  display: flex;
  margin-left: auto;
  border-radius: 20px;
  transition: 0.5s;

  &:hover {
    background-color: #b8b5b5;
    box-shadow: 0 4px 8px rgba(106, 106, 106, 0.3);
  }

  .nav-close-icon {
    background-image: url('@/assets/img/filewindow/close.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 20px;
    height: 20px;
  }
}



.value {
    white-space: pre-wrap;
    word-wrap: break-word;
    line-height: 1.5;
    padding: 8px;
    font-size: 14px;
    color: #2c3e50;
    background-color: rgba(255, 255, 255, 0.7);
    border-radius: 6px;
    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    text-align: left;
}
</style>