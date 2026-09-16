<template>
  <div class="notebook-homepage">
    <div class="header">
      <h1>NKCN·Brain 欢迎你 {{ this.curUserName }}</h1>
      <button @click="backtologin" class="action-button">返回登录</button>
      <button @click="gotoUse" class="action-button">继续使用</button>
    </div>

    <div class="content">
      <div class="actions">
        <h1>用户列表</h1>
      </div>
      <div class="actions">
        <el-table :data="userList" style="width: min-content;">
          <el-table-column prop="username" label="用户名" width="180"></el-table-column>
          <el-table-column label="操作" width="300">
            <template #default="{ row }">
              <el-button type="primary"  style="width: 80px;" @click="editUser(row)">查看</el-button>
              <el-button type="danger"  style="width: 80px;" @click="banUser(row)">禁止</el-button>
              <el-button style="width: 80px; background-color: #0f9d58; color: white;" @click="openUser(row)">解除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <footer class="footer">
      <p>© 2024 NK-CN-Brain. All rights reserved.</p>
    </footer>
  </div>
</template>

<script>
import router from '@/router'
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElTable, ElTableColumn } from 'element-plus'
import { getList, ban_user, open_user } from '@/api/user'
import { response } from 'express';
export default {
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    ElTable, 
    ElTableColumn
  },
  data() {
    return {
      curUserName: '',
      userList: [] // 用于保存用户列表
    };
  },
  mounted() {
    this.fetchUserList();
  },
  created() {
    this.curUserName = 'admin';
  },
  methods: {
    backtologin() {
      router.push('/');
    },
    editUser(row) {
      localStorage.setItem('userId', row.username);
      localStorage.setItem('realName', row.username);
      localStorage.setItem('byadmin', 'true');
      router.push('/home');
    },
    banUser(row) {
      let formData = new FormData();
      formData.append('username', row.username);
      ban_user(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.error('操作成功');
        } else {
          this.$message.error('操作失败');
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
        this.$message.error('操作失败');
      });
    },
    openUser(row) {
      let formData = new FormData();
      formData.append('username', row.username);
      open_user(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.error('操作成功');
        } else {
          this.$message.error('操作失败');
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
        this.$message.error('操作失败');
      });
    },
    fetchUserList() {
      getList().then(response => {
        if (response.error_num === 0) {
          this.userList = response.list.map(user => {
            return {
              id: user.pk,
              username: user.fields.username
            };
          }).filter(user => user.username !== 'admin');   // 过滤掉 username 为 'admin'
        } else {
          this.$message.error('获取用户列表失败');
        }
      })
    },
    gotoUse() {
      // 通过他人用户名查看信息后，返回时改回admin自身信息
      localStorage.setItem('userId', 'admin');
      localStorage.setItem('realName', 'admin');
      router.push('/home');
    }
  },

};
</script>

<style scoped>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: 'Arial', sans-serif;
}

/* 全局背景动画 */
/* 全局背景动画 */
.notebook-homepage {
  /* 深色调和冷色调的线性渐变背景 */
  background: linear-gradient(-45deg, #1a3a91, #3b82f6, #0e5a6c, #0d47a1);
  background-size: 400% 400%;
  animation: gradientBG 10s ease infinite;
}

/* 动画效果 */
@keyframes gradientBG {
  0% {
    background-position: 0% 50%;
  }

  50% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0% 50%;
  }
}

/* 调整内容区域的背景和阴影 */
.content {
  background: rgba(255, 255, 255, 0.8);
  /* 半透明白色背景 */
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
  backdrop-filter: blur(5px);
  /* 轻微模糊效果 */
}

/* 其他样式保持不变 */
/* 容器样式 */
.notebook-homepage {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  min-height: 100vh;
  background-color: #f5f5f5;
  padding: 20px;
}

/* 头部样式 */
.header {
  margin-bottom: 30px;
  color: #333;
  display: flex;
}

.header h1 {
  font-size: 2.5em;
  margin-right: 50px;
}

.header button {
  background-color: #fff;
  color: black;
  font-size: medium;

  width: 150px;
  height: 50px;

  margin-top: 8px;

  &:hover {
    background-color: #1896da;
  }
}

/* 内容样式 */
.content {
  width: 100%;
  max-width: 800px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  padding: 30px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 操作按钮样式 */
.actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}


.action-button {
  margin-left: 10px;
  border: none;
  transform: scale(0.95);
  border-radius: 4px;
  background-color: #1a73e8;
  color: white;
  font-size: 1em;
  cursor: pointer;
  transition: background-color 0.3s;
}

.action-button:hover {
  background-color: #0d47a1;
}


/* 页脚样式 */
.footer {
  margin-top: 30px;
  color: #666;
  text-align: center;
  font-size: 0.8em;
  padding: 10px;
  border-top: 1px solid #eaeaea;
}

.footer {
  display: flex;
  justify-content: flex-end;
  /* 按钮组靠右对齐 */
  gap: 10px;
  /* 按钮之间的间距 */
}

.footer .el-button {
  padding: 10px 20px;
  /* 按钮的内边距 */
  border-radius: 4px;
  /* 按钮的边框圆角 */
  font-size: 1em;
  /* 按钮的字体大小 */
}


</style>
  