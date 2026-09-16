<template>
  <div class="head-portrait">
    <img :src="imgUrl" alt="">
    <!-- 将伪元素改为真实的 div 元素 -->
    <div class="status-dot" :class="{ 'active': isActive }"></div>
  </div>
</template>

<script>
export default {
    props: {
        imgUrl:{ default:require('@/assets/img/head_portrait.jpg')},
        index: {
            type: Number,  // 类型为数字
            required: true // 必传参数
        },
        isActive: {
            type: Boolean,
            default: true  // 默认为 true,显示绿色
        }
    },
    methods: {
        // toggleState() {
        //     this.$emit('toggleState', this.index);
        //     setTimeout(() => {
        //         console.log("点击切换模型开关状态: ", this.index, this.isActive)
        //     }, 50); // 延迟50毫秒
        // }
    }
}
</script>

<style lang="scss" scoped>
.head-portrait {
    width: 50px;
    height: 50px;
    border-radius: 50%;
    // border: 2px solid rgb(137,140,151);
    border: 2px solid rgb(255, 255, 255);
    position:relative;
    // &::before {
    //     content: '';
    //     width: 15px;
    //     height: 15px;
    //     z-index: 1;
    //     display: block;
    //     border-radius: 50%;
    //     background-color: v-bind(isActive ? 'rgb(144,225,80)' : 'rgb(128,128,128)');
    //     position: absolute;
    //     right: 0;
    // }
    .status-dot {
        width: 15px;
        height: 15px;
        z-index: 1;
        display: block;
        border-radius: 50%;
        background-color: rgb(128,128,128); // 默认灰色
        position: absolute;
        right: 0;
        
        &.active {
            background-color: rgb(144,225,80); // 激活时为绿色
        }
    }

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
</style>