<template>
  <div class="model-card-list" v-for="(modelInfo, index) in this.displayList">
    <div class="model-card" @click="selectModel(modelInfo)">
      <div class="info">
        <HeadPortrait 
          :imgUrl="modelInfo.headImg" 
          :index="index"
          :isActive="littlePortraitStates[index]"
        ></HeadPortrait>
        <div class="info-detail">
          <div class="name">{{ modelInfo.name === 'GPT4' ? modelInfo.name + 'o' : (modelInfo.name === 'Llama3' ? modelInfo.name + '.1' : modelInfo.name) }}</div>
          <div class="detail">{{ modelInfo.detail }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import HeadPortrait from "./HeadPortrait.vue";

import { getLittleModel } from "@/api/getData"

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
    littlePortraitStates: {
      type: Object,
      required: true
    }
  },
  methods: {
    toggleState() {
      this.$emit('update:littlePortraitStates');
    },
    selectModel(modelInfo) {
      this.$message.success('已选模型：' + modelInfo.name);
      this.$emit('update:selectModel', modelInfo);
    }
  },
  mounted() {
    this.modelList = getLittleModel();
    const originalList = [...this.modelList]; // 保存原始数组

    // 定义排序的优先顺序，按照后端modelList顺序：
    // 3003(索引0) → 3002(索引1) → 3001(索引2) → 3004(索引3) → 3005(索引4) → 3006(索引5) → 3007(索引6)
    const order = ["3003", "3002", "3001", "3004", "3005", "3006", "3007"];

    // 自定义排序函数，按照 `order` 中的顺序进行排序
    // 创建新的排序数组而不影响原数组
    const sortedList = [...originalList].sort((a, b) => {
      return order.indexOf(a.id) - order.indexOf(b.id);
    });
    // this.modelList.sort((a, b) => {
    //   return order.indexOf(a.id) - order.indexOf(b.id);
    // });

    // 使用排序后的数组进行显示
    this.displayList = sortedList;
  }
};
</script>

<style lang="scss" scoped>
.model-card {
  width: 400px;
  height: 100px;
  border-radius: 20px;
  background-color: rgb(50, 54, 68);
  position: relative;
  margin: auto;
  margin-top: 20px;
  cursor: pointer;

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