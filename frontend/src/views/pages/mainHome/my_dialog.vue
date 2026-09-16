<!-- DialogComponent.vue -->
<template>
  <div class="dialog" v-if="visible">
    <div class="dialog-content">
      <span class="close" @click="closeDialog">&times;</span>
      <h2>创建新的笔记本</h2>
      <form @submit.prevent="createNotebook">
        <label for="title">笔记名称:</label>
        <input type="text" id="title" v-model="title" required>

        <label for="description">笔记描述:</label>
        <input type="text" id="description" v-model="description" required>

        <button type="submit">创建</button>
      </form>
    </div>
  </div>
</template>

<script>
export default {

  name:'my_dialog',

  props:{
    visible:{type:'boolean',default:false}
  },
  data() {
    return {
      showDialog: false,
      title: '',
      description: ''
    };
  },
  methods: {

    closeDialog() {
      this.showDialog = false;
      this.title = '';
      this.description = '';
    },

    createNotebook() {
      if (this.title.trim() === '' || this.description.trim() === '') {
        alert('笔记名称和描述不能为空');
        return;
      }
      // 发送创建笔记本的事件到父组件
      this.$emit('create',
          { title: this.title, description: this.description });
      this.closeDialog();
    }
  }
};
</script><style scoped>/* 样式略... */</style>

<style scoped lang="scss">

</style>