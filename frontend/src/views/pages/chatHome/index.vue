<template>
  <div class="chatHome">
    <div class="chatLeft">

      <div class="online-model">
        <span class="onlin-text">模型列表</span>
        <div class="model-cards-wrapper">
          <div class="modelList" v-for="modelInfo in modelList" :key="modelInfo.id" @click="clickModel(modelInfo)">
            <ModelCard :modelInfo="modelInfo" :pcCurrent="pcCurrent"></ModelCard>
          </div>
        </div>
      </div>
    </div>
    <div class="chatRight">
      <!-- <router-view></router-view> -->
      <div v-if="showChatWindow">
        <!-- 传参到子组件的形式：冒号+子组件用的名字+等号+引号+当前组件中的变量名 ；传递方法用@-->
        <ChatWindow :chatModelInfo="chatWindowInfo" @modelCardSort="modelCardSort" :fileNameList="fileNameList"
          :params="params">
        </ChatWindow>
      </div>
      <div class="showIcon" v-else>
        <span class="iconfont icon-snapchat"></span>
        <!-- <img src="@/assets/img/snapchat.png" alt="" /> -->
      </div>
    </div>
    <!-- <el-col :span="4"><div class="grid-content bg-purple"></div></el-col> -->
  </div>
</template>

<script>
import ModelCard from "@/components/chatWindow/ModelCard.vue";
import ChatWindow from "@/views/pages/chatHome/chatwindow.vue";

import { getModel } from "@/api/getData";
import { chat_switch } from "@/api/chat/send_message"
export default {
  name: "App",    // 组件名称，可选，调试用
  components: {    // 所依赖的子组件，于是可以在template里面使用它们
    ModelCard,
    ChatWindow,
  },
  data() {        // 组件的数据对象，可以用this访问和修改
    return {
      pcCurrent: "",
      modelList: [],
      showChatWindow: false,
      chatWindowInfo: {},
    };
  },
  props: {
    fileNameList: {
      type: Array,
    },
    params: {
      type: Object,
    }
  },
  mounted() {     // 挂载项，即页面加载执行以下动作，用于从后台获取数据
    let res = getModel();
    this.modelList = res;
  },
  methods: {
    clickModel(info) {
      this.showChatWindow = true;
      this.chatWindowInfo = info;
      this.modelInfo = info;
      this.pcCurrent = info.id;

      // 切换模型：1002、1003、1004
      let formData = new FormData();
      formData.append('model_id', this.pcCurrent);
      formData.append('username', localStorage.getItem('userId'));
      chat_switch(formData).then(data => {
        this.$message({
          message: "切换成功",
          type: "success",
        });
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });

      console.log(this.pcCurrent);
    },
    modelCardSort(id) {
      if (id !== this.modelList[0].id) {
        let nowModelInfo;
        for (let i = 0; i < this.modelList.length; i++) {
          if (this.modelList[i].id == id) {
            nowModelInfo = this.modelList[i];
            this.modelList.splice(i, 1);
            break;
          }
        }
        this.modelList.unshift(nowModelInfo);
      }
    },
  },
};
</script>

<style lang="scss" scoped>
.chatHome {
  // margin-top: 20px;
  display: flex;

  .chatLeft {
    width: 280px;

    .title {
      color: #fff;
      padding-left: 10px;
    }

    .online-model {
      margin-top: 100px;

      .onlin-text {
        padding-left: 10px;
        color: rgb(176, 178, 189);
      }

      .model-cards-wrapper {
        padding-left: 10px;
        height: 65vh;
        margin-top: 20px;
        overflow: hidden;
        overflow-y: scroll;
        box-sizing: border-box;

        &::-webkit-scrollbar {
          width: 0;
          /* Safari,Chrome 隐藏滚动条 */
          height: 0;
          /* Safari,Chrome 隐藏滚动条 */
          display: none;
          /* 移动端、pad 上Safari，Chrome，隐藏滚动条 */
        }
      }
    }
  }

  .chatRight {
    flex: 1;
    padding-right: 30px;

    .showIcon {
      position: absolute;
      top: calc(50% - 150px);
      /*垂直居中 */
      left: calc(50% - 50px);

      /*水平居中 */
      .icon-snapchat {
        width: 300px;
        height: 300px;
        font-size: 300px;
        // color: rgb(28, 30, 44);
      }
    }
  }
}
</style>