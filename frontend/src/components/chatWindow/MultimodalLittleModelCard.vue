<template>
  <div class="model-card-list" v-for="(modelInfo, index) in this.displayList">
    <div class="model-card" @click="selectModel(modelInfo)">
      <div class="info">
        <HeadPortrait 
          :imgUrl="modelInfo.headImg" 
          :index="index"
          :isActive="multimodalLittlePortraitStates[index]"
        ></HeadPortrait>
        <div class="info-detail">
          <div class="name">{{ modelInfo.name }}</div>
          <div class="detail">{{ modelInfo.detail }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import HeadPortrait from "./HeadPortrait.vue";
import { getMultimodalLittleModel } from "@/api/getData"

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
    multimodalLittlePortraitStates: {
      type: Object,
      required: true
    }
  },
  methods: {
    selectModel(modelInfo) {
      this.$message.success('已选多模态小模型：' + modelInfo.name);
      this.$emit('update:selectModel', modelInfo);
    }
  },
  mounted() {
    this.modelList = getMultimodalLittleModel();
    const order = ["4002", "4001"];
    const sortedList = [...this.modelList].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
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
    border: 2px solid rgb(255, 255, 255);
    position:relative;
    img {
      width: 45px;
      height: 45px;
      border-radius: 50%;
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

    .info {
      .info-detail {
        .detail {
          color: #fff;
        }
      }
    }
  }
}
</style>
