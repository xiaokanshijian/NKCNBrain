<template>
    <!-- 子组件内容 -->
    <div class="chat-window">
      <div class="botoom">
        <div class="chat-content" ref="chatContent">
          <div class="chat-wrapper" v-for="(item, index) in chatList" :key="item.id">
  
            <div class="chat-model" v-if="item.uid !== '1001'">
              <div class="chat-text" v-if="item.chatType == 0" v-bind:style="{ color: item.color }" @click="noChangeModel">
                {{ item.msg }}
              </div>
            </div>
            
          </div>
        </div>
      </div>
    </div>
  </template>
  
<script>
  import { animation } from "@/utils/util";
  import { getChatMsg } from "@/api/getData";
  import { getTime } from "@/api/getData"
  import { chat_send, chat_sendParams, agent_LUI2 } from "@/api/chat/send_message"
  export default {
    props: {        // 定义从父组件传递过来的变量
      chatModelInfo: Object,
      params: Object,
      isQuestionWindow: Boolean,
      isPlus: Boolean,
      isHistoryUsed: Boolean,
      isSummaryUsed: Boolean,
      rounds: Number,
      portraitStates: Object,
      default() {
        return {};
      },
    },
    data() {
      return {
        waitForChange: false,
        retQuestions: false,
        chatList: [],
        summary: false,
        questionContents: [
        ],
        shouldScroll: true
      };
    },
    methods: {
  
      noChangeModel() {
        // 阻止事件继续传播
        event.stopPropagation();
      },

      //发送信息
      sendMsg(msgList) {
        this.chatList.push(msgList);
        setTimeout(() => {
          this.scrollBottom();
        }, 100); // 延迟100毫秒
      },
      //获取窗口高度并滚动至最底层
      scrollBottom() {
        if (this.shouldScroll) {
          const scrollDom = this.$refs.chatContent;
          animation(scrollDom, scrollDom.scrollHeight - scrollDom.offsetHeight);
          this.shouldScroll = false; // 重置标志位
        }
      },
      //发送文字信息
      sendText(message, filenamelist, leftSelectList, rightSelectList) {
      this.shouldScroll = true;
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
      }

      // let username = "admin"
      let username = localStorage.getItem('userId')
      // 前端逻辑
      let chatMsg = {
        headImg: require("@/assets/img/head_portrait.jpg"),
        name: username,
        time: getTime(),
        msg: message,
        chatType: 0, //信息类型，0文字，1图片, 2文档
        uid: "1001", //uid
        checked: false
      };
      this.sendMsg(chatMsg);

      let formData = new FormData()
      formData.append('username', username);
      formData.append('model_id', this.chatModelInfo.id);
      formData.append('message', message);
      formData.append('filenamelist', filenamelist);
      formData.append('summary', this.summary);
      formData.append('leftSelectList', leftSelectList);
      formData.append('rightSelectList', rightSelectList);
      // 将 portraitStates 对象转换为 JSON 字符串再添加到 FormData
      formData.append('modelStates', JSON.stringify(this.portraitStates));

      formData.append('isHistoryUsed', this.isHistoryUsed);
      formData.append('isSummaryUsed', this.isSummaryUsed);
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
      let paramString = JSON.stringify(this.params);
      paramFormData.append('params', paramString);
      paramFormData.append('modelID', this.chatModelInfo.id)
      paramFormData.append('username', username);
      console.log(paramString);

      // 首先执行 chat_sendParams
      chat_sendParams(paramFormData)
        .then(response => {
          // 当 chat_sendParams 成功执行后，才执行 chat_send
          console.log(response['msg']);
          return chat_send(formData); // 返回 chat_send 的 Promise，以便在下一个 .then 中处理
        })
        .then(response => {
          // 处理 chat_send 的响应
          if (response.error_num === 0) {
            this.$message.success('发送成功！');
          } else {
            this.$message.error('发送失败，请重试！');
            console.log(response['msg']);
          }
          // 后端传回数据，显示
          let all_content = response['content'];
          let content = "";
          if (this.chatModelInfo.name == "GPT4") {
            content = all_content[0];
          }
          else if (this.chatModelInfo.name == "Mixtral8x7B") {
            content = all_content[1];
          }
          else if (this.chatModelInfo.name == "Llama3") {
            content = all_content[1];
          }
          else if (this.chatModelInfo.name == "Kimi") {
            content = all_content[2];
          }
          else if (this.chatModelInfo.name == "Claude3.5") {
            content = all_content[3];
          }
          else if (this.chatModelInfo.name == "Deepseek") {
            content = all_content[4];
          }
          else if (this.chatModelInfo.name == "Deepseek-reasoner") {
            content = all_content[5];
          }
          console.log(content);
          let timeParams = response['nowParams']
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
            seed: response["seed"],
          };
          this.shouldScroll = true;
          this.sendMsg(modelMsg);
          console.log(modelMsg);

        })
        .catch(error => {
          // 处理两个请求中的任何一个发生的错误
          console.error("An error occurred:", error);
          this.$message.error('问答发生了一点错误，您可能需要重新登陆再试：' + error);
        });
      },
    },
};
</script>