
<template>
  <div class="container">
      <h1>模型权重脑图查看</h1>
      <div class="selection-wrapper">
        <div class="selection-wrapper" v-if="curModelName!=''">
        <select v-model="selectedValue" @change="handleSelect" class="custom-select">
          <option disabled value="">请选择...</option>
          <optgroup v-for="layer in MixtralProps.LayerCount" :key="String(layer-1)" :label="'layer'+String(layer-1)+' brain map'">
            <option v-for="name in MixtralProps.LayerNameSuffixList" :key="String(layer-1)+name" :value="String(layer-1)+name">
              {{"layer"+String(layer-1)+name}}
            </option>
          </optgroup>
        </select>
        <!-- 显示选中项对应的文本或图片 -->
        <div v-if="selectedValue" class="selected-item">
  <!--        <h2 class="selected-text">{{ selectedText }}</h2>-->
          <h4>原始模型权重脑图</h4>
          <img class="selected-image" :src="selectedImage" alt="图片待加载" />
          <h4>微调模型权重脑图</h4>
          <img class="selected-image2" :src="selectedImage2" alt="图片待加载" />
          <h4>微调前后差异脑图</h4>
          <img class="selected-image3" :src="selectedImage3" alt="图片待加载" />
        </div>
      </div>
    </div>
  </div>
</template>


<script>
export default {
  props : {
    curModelName: {
      type: String,
      default: '',
    },
  },
  watch: {
    curModelName(newVal,oldVal) {
      // alert(newVal);
    }
  },
  data() {
    return {
      selectedValue: null, // 当前选中的值
      selectedText: '',    // 显示的文本
      selectedImage: '', // 如果需要显示图片，可以添加这个属性
      selectedImage2: '',
      selectedImage3: '',
      MixtralProps : {
        LayerCount:32,
        LayerNameSuffixList:[".self_attn.q_proj.weight",
          ".self_attn.k_proj.weight",
          ".self_attn.v_proj.weight",
          ".self_attn.o_proj.weight",
          ".block_sparse_moe.experts.0.w1.weight",
          ".block_sparse_moe.experts.0.w2.weight",
          ".block_sparse_moe.experts.0.w3.weight",
          ".block_sparse_moe.experts.1.w1.weight",
          ".block_sparse_moe.experts.1.w2.weight",
          ".block_sparse_moe.experts.1.w3.weight",
          ".block_sparse_moe.experts.2.w1.weight",
          ".block_sparse_moe.experts.2.w2.weight",
          ".block_sparse_moe.experts.2.w3.weight",
          ".block_sparse_moe.experts.3.w1.weight",
          ".block_sparse_moe.experts.3.w2.weight",
          ".block_sparse_moe.experts.3.w3.weight",
          ".block_sparse_moe.experts.4.w1.weight",
          ".block_sparse_moe.experts.4.w2.weight",
          ".block_sparse_moe.experts.4.w3.weight",
          ".block_sparse_moe.experts.5.w1.weight",
          ".block_sparse_moe.experts.5.w2.weight",
          ".block_sparse_moe.experts.5.w3.weight",
          ".block_sparse_moe.experts.6.w1.weight",
          ".block_sparse_moe.experts.6.w2.weight",
          ".block_sparse_moe.experts.6.w3.weight",
          ".block_sparse_moe.experts.7.w1.weight",
          ".block_sparse_moe.experts.7.w2.weight",
          ".block_sparse_moe.experts.7.w3.weight",]
      },
    };
  },
  methods: {

    handleSelect() {
      // alert(this.selectedValue);
      if(this.selectedValue==="0.self_attn.k_proj.weight")
      {
        this.selectedImage="public-example.svg";
        this.selectedImage2="public-example.svg";
        this.selectedImage3="public-example.svg";
      }
      else
      {
        this.selectedImage="";
        this.selectedImage2="";
        this.selectedImage3="";
      }
      // const selectedOption = this.options.find(group => group.options.some(opt => opt.value === this.selectedValue));
      // if (selectedOption) {
      //   const option = selectedOption.options.find(opt => opt.value === this.selectedValue);
      //   this.selectedText = option ? option.text : ''; // 更新显示的文本
      //   // 如果选项中包含图片路径，也可以在这里设置
      //   this.selectedImage = option ? option.path : '';
      //   // alert(this.selectedImage);
      // }
    }
  }
};
</script>

<style scoped>
.container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  text-align: center;
}

.custom-select {
  padding: 10px;
  border: 1px solid #ccc;
  border-radius: 5px;
  font-size: 16px;
  margin-bottom: 20px;
  width: 75%;
}

.selection-wrapper {
  background-color: #f9f9f9;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

.selected-item {
  background-color: #f5f5f5;
  border-radius: 10px;
  padding: 20px;
  text-align: left;
}

.selected-text {
  color: #333;
  margin-bottom: 10px;
}

.selected-image {
  max-width: 100%;
  height: auto;
  border-radius: 5px;
}
.selected-image2{
  max-width: 100%;
  height: auto;
  border-radius: 5px;
}
.selected-image3 {
  max-width: 100%;
  height: auto;
  border-radius: 5px;
}
</style>
<!--path=../../../public/public-example.svg-->