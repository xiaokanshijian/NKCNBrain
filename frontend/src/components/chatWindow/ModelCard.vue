<template>
  <div class="model-card-list" v-for="(modelInfo, index) in this.displayList">
    <div class="model-card" @click="selectModel(modelInfo)">
      <div class="info">
        <HeadPortrait 
          :imgUrl="modelInfo.headImg" 
          :index="index"
          :isActive="portraitStates[index]"
        ></HeadPortrait>
        <div class="info-detail">
          <div class="name">
            {{
              modelInfo.name === 'GPT4' 
                ? modelInfo.name + 'o' 
                : modelInfo.name === 'Llama3' 
                  ? modelInfo.name + '.1' 
                  : modelInfo.name === 'Deepseek' 
                    ? 'Deepseek-V3' 
                    : modelInfo.name === 'Deepseek-reasoner' 
                      ? 'Deepseek-R1' 
                      : modelInfo.name
            }}
          </div>
          <div class="detail">{{ modelInfo.detail }}</div>
          <div class="detail">{{'模型描述：' +  modelInfo.description || '暂无描述' }}</div>
          <div class="detail">{{'响应速度：' +   formatSpeed(modelInfo.responseSpeed) }}</div>
          <div class="detail">{{ '推理能力：' +  formatReasoning(modelInfo.reasoningLevel) }}</div>
          <div class="detail">{{'多模态能力：' +   formatMultimodal(modelInfo.multimodalLevel) }}</div>
        </div>
      </div>
    </div>
  </div>
  <div class="model-card" @click="toggleState">
    <div class="info">
      <div class="head-portrait">
        <img :src="imageUrl" alt="">
      </div>
      <div class="info-detail">
        <div class="name">{{ 'Empty(空)' }}</div>
        <div class="detail">{{ 'Clear This Window(关闭此窗口的模型)' }}</div>
      </div>
    </div>
  </div>
</template>

<script>
import HeadPortrait from "./HeadPortrait.vue";

import { getModel } from "@/api/getData"
import { request_base_info } from "@/api/chat/send_message"

export default {
  components: {
    HeadPortrait,
  },
  data() {
    return {
      modelList: [],
      displayList: [],
      imageUrl: require('@/assets/img/GrommetIconsClear.png')
    }
  },
  props: {
    activeModel: String,
    portraitStates: {
      type: Object,
      required: true
    }
  },
  methods: {
    toggleState() {
      this.$emit('update:portraitStates');
    },
    selectModel(modelInfo) {
      this.$message.success('已选模型：' + modelInfo.name);
      this.$emit('update:selectModel', modelInfo);
    },
    // 格式化响应速度
    formatSpeed(speed) {
      const speedMap = {
        fast: '快',
        medium_fast: '中快',
        medium_slow: '中慢',
        slow: '较慢'
      };
      return speedMap[speed] || '未知';
    },
    // 格式化推理能力
    formatReasoning(level) {
      const levelMap = {
        high_native: '高-原生',
        medium_native: '中-原生',
        low_native: '低-原生',
        high_nonnative: '高-非原生',
        medium_nonnative: '中-非原生',
        low_nonnative: '低-非原生',
      };
      return levelMap[level] || '未知';
    },
    // 格式化多模态能力
    formatMultimodal(level) {
      const levelMap = {
        high: '高',
        medium: '中',
        low: '低',
        none: '无'
      };
      return levelMap[level] || '未知';
    },
  },
  mounted() {
    this.modelList = getModel();
    const originalList = [...this.modelList]; // 保存原始数组

    // // 定义排序的优先顺序
    // const order = ["1002", "1006", "1007", "1008", "1005", "1004", "1003", "1009", "1010"];

    // // 自定义排序函数，按照 `order` 中的顺序进行排序
    // // 创建新的排序数组而不影响原数组
    // const sortedList = [...originalList].sort((a, b) => {
    //   return order.indexOf(a.id) - order.indexOf(b.id);
    // });
    // // this.modelList.sort((a, b) => {
    // //   return order.indexOf(a.id) - order.indexOf(b.id);
    // // });

    // // 使用排序后的数组进行显示
    // this.displayList = sortedList;
        // 根据modelList中每一项的sequence字段排序
    originalList.sort((a, b) => a.sequence - b.sequence);

    // console.log('originalList', originalList);
    this.formData = new FormData()
    this.formData.append('username', this.username);
    // this.fetchModelData();

    // console.log('当前的用户：', this.username)

    this.displayList = originalList;
  }
};
</script>

<style lang="scss" scoped>
.model-card {
  width: 400px;
  height: 110px;
  // height: auto; // 改为自适应高度
  border-radius: 20px;
  background-color: rgb(50, 54, 68);
  position: relative;
  margin: auto;
  margin-top: 20px;
  cursor: pointer;
  padding: 15px; // 添加内边距，防止文字贴边

  .info {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 90%;
    transform: translate(-50%, -50%);
    overflow: hidden;
    display: flex;

    .info-detail {
      margin-top: 5px;
      margin-left: 20px;

      .name {
        color: #fff;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        margin-bottom: 5px;
      }

      .detail {
        color: #5c6675;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        font-size: 12px;
      }
    }
  }

  .head-portrait {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    // border: 2px solid rgb(137,140,151);
    border: 2px solid rgb(255, 255, 255);
    position:relative;
    img {
        width: 45px;
        height: 45px;
        border-radius: 50%;
        // padding: 2px;
        box-sizing: border-box;
        position: absolute;
        left: 50%;
        top: 50%;
        transform: translate(-50%, -50%);
        vertical-align: middle;
    }
  }

  &:hover {
    background-color: #1d90f5;
    transition: 0.3s;
    box-shadow: 0px 0px 10px 0px rgb(0, 136, 255);

    // box-shadow:  0 5px 20px rgba(251, 152, 11, .5);
    .info {
      .info-detail {
        .detail {
          color: #fff;
        }
      }
    }
  }
}

.activeCard {
  background-color: #1d90f5;
  transition: 0.3s;
  box-shadow: 3px 2px 10px 0px rgb(0, 136, 255);

  .info {
    .info-detail {
      .detail {
        color: #fff;
      }
    }
  }
}
</style>