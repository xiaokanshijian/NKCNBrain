<template>
  <div style="text-align: center;">
      <div class="import-button" :class="{ 'checked': checked }" @click="onImport"></div>
      <h1>深评视图窗口</h1>
  </div>
  <div class="container">
    <div class="selection-wrapper">
        <select v-model="selectedValue" @change="handleSelect" class="custom-select">
            <option disabled value="">微调模型相对于基座模型的得分变化（+变好/-变坏）</option>
            <option v-for="option in options" :key="option" :value="option">
                {{ option }}
            </option>
        </select>
        
        <input type="text" v-model="inputValue" class="custom-input" disabled placeholder="微调模型相对于基座模型的得分变化（+变好/-变坏）">
    </div>

    <!-- 上半部分 -->
    <div class="section model-1">
      <h1 class="section-title">基座模型</h1>
      <div v-if="changeFineTuneModel" class="image-container">
        <img src="@/assets/public-example.svg" alt="Model 1 Assessment">
      </div>
    </div>

    <!-- 下半部分 -->
    <div class="section model-2">
      <h1 class="section-title">微调模型</h1>
      <div v-if="changeFineTuneModel" class="image-container">
        <img src="@/assets/public-example.svg" alt="Model 2 Assessment">
      </div>
    </div>
  </div>
</template>

<script>
export default {
  props: {        // 定义从父组件传递过来的变量
    changeFineTuneModel: Boolean,
    default() {
      return {};
    },
  },
  watch: {
    changeFineTuneModel(newVal, oldVal) {
      if(newVal === true){
      }
    },
  },
  data() {
    return {
      options: ['基础能力', '红蓝融合能力'],
      selectedValue: null,
      inputValue: '',
      checked: false,
      baseScoreGap: 0.5,
      redBlueScoreGap: 26.09,
    };
  },
  methods: {
    handleSelect() {
      if(this.selectedValue === '基础能力') {
        this.inputValue = this.baseScoreGap
      } else {
        this.inputValue = this.redBlueScoreGap
      }
    },
    onImport() {
      // 创建一个input元素用于选择文件
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*'; // 限制只能选择图片文件

      // 为input元素添加change事件监听器
      input.addEventListener('change', (event) => {
        const file = event.target.files[0];
        if (file) {
          // 使用FileReader API读取图片文件
          const reader = new FileReader();
          reader.onload = (e) => {
            // 这里可以处理读取到的图片数据，例如将其设置为一个data URL
            const imageUrl = e.target.result;
            console.log('图片数据:', imageUrl);

            // 可以将图片URL用于img标签的src属性
            const img = new Image();
            img.src = imageUrl;

            // 或者可以将图片数据传递给其他组件或方法进行进一步处理
            // this.handleImage(imageUrl);

            // 选中状态
            this.checked = true;
          };
          reader.readAsDataURL(file);
        }
      });

      // 触发input元素的点击事件，打开文件选择对话框
      input.click();
    }
  }
};
</script>

<style scoped>
.container {
  display: flex;
  flex-direction: column;
  height: 84%; 
  padding: 20px;
  text-align: center;
  /* 使用视口高度 */

  overflow-y: auto;
}

.section {
  flex: 1; /* 让每个部分占据相等的空间 */
  display: flex;
  flex-direction: column;
  /* align-items: center;
  justify-content: center; */
  padding: 10px;
  box-sizing: border-box;
}

.section.model-1 {
  background-color: rgb(198, 92, 82); /* 上半部分的背景颜色 */
}

.section.model-2 {
  background-color: rgb(173, 94, 87); /* 下半部分的背景颜色 */
}

.section-title {
  margin-bottom: 20px; /* 标题和图片之间的间距 */
}


.image-container {
  width: 96%;
  height: 50%;
  height: auto; /* 高度自适应，保持图片的宽高比 */
  overflow: hidden; /* 如果图片超出容器，隐藏超出部分 */
  position: relative; /* 相对定位，用于绝对定位图片 */
}

.image-container img {
  width: 100%; /* 图片宽度为容器宽度 */
  height: auto; /* 高度自适应，保持图片的宽高比 */
  
  object-position: center; /* 图片在容器中水平和垂直居中 */
}


.custom-select {
  padding: 10px;
  border: 1px solid #ccc;
  border-radius: 5px;
  font-size: 16px;
  margin-bottom: 20px;
  width: 75%;
}

.custom-input {
  /* 文本框的样式，与下拉框相似 */
  padding: 10px;
  border: 1px solid #ccc;
  border-radius: 5px;
  font-size: 16px;
  margin-bottom: 20px;
  width: 75%;
  /* 禁用文本框的样式 */
  background-color: #eee;
  cursor: not-allowed;
}

.selection-wrapper {
  background-color: #f9f9f9;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}



.import-button {
  background-size: contain;
  background-repeat: no-repeat;
  vertical-align: middle;
  height: 22px;
  width: 22px;
  border-radius: 3px;
  position: fixed; /* 或者使用 absolute，取决于您的需求 */
  z-index: 10; /* 确保按钮在页面内容的上方 */
  cursor: pointer; /* 显示可点击的鼠标指针 */
  margin-left: 20px;
}

.import-button.checked {
  background-image: url('@/assets/img/pin_grey.png');
}

.import-button:not(.checked) {
  background-image: url('@/assets/img/pin_grey.png');
}
</style>