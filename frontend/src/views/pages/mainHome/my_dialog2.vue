<!-- CreateNotebookDialog.vue -->
<template>
  <div class="create-notebook-dialog" v-if="show">
    <div class="dialog-content">
      <h2>创建新的笔记本</h2>
      <form @submit.prevent="createNotebook">
        <label for="title">笔记名称</label>
        <input type="text" id="title" v-model="title" required>

        <label for="description">笔记描述</label>
        <input type="text" id="description" v-model="description" required>

        <button type="submit">创建笔记本</button>
      </form>
      <button class="close-btn" @click="closeDialog">&times;</button>
    </div>
  </div>
</template>

<script>
export default {
  name: 'my_dialog2',
  data() {
    return {
      show: false,
      title: '',
      description: ''
    };
  },
  methods: {
    createNotebook(event) {
      event.preventDefault();
      if (this.title.trim() === '' || this.description.trim() === '') {
        alert('笔记名称和描述不能为空');
        return;
      }
      // Emit an event to the parent component with the new notebook data
      this.$emit('notebook-created', { title: this.title, description: this.description }); this.closeDialog();
    }, closeDialog() { this.show = false; this.title = ''; this.description = ''; }
  }
};
</script>
<style scoped>
/* Add your CSS styles for the dialog here */


.create-notebook-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background-color: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
  width: 90%;
  max-width: 400px;
  z-index: 1000;
  padding: 20px;
  display: none;
  /* 初始状态不显示 */
}

.dialog-content {
  display: flex;
  flex-direction: column;
  gap: 15px;

}

.close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  background-color: transparent;
  border: none;
  font-size: 24px;
  font-weight: bold;
  color: #aaa;
  cursor: pointer;
  transition: color 0.3s;

}

.close-btn:hover {
  color: #333;

}

form {
  display: flex;
  flex-direction: column;
  gap: 10px;

}

input[type="text"] {
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  transition: border-color 0.3s;
}

input[type="text"]:focus {
  outline: none;
  border-color: #1a73e8;
}

button {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  background-color: #1a73e8;
  color: white;
  font-size: 14px;
  cursor: pointer;
  transition: background-color 0.3s;
}

button:hover {
  background-color: #0d47a1;
}
</style>