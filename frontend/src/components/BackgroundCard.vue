<template>
  <div class="bgc-list" v-for="(bgcInfo, index) in this.bgcList">
    <div class="bgc">
      <div class="info">
        <div class="head-portrait">
          <img :src="imgUrl" alt="">
        </div>
        <div class="info-detail" @click="selectBgc(bgcInfo)">
          <div class="name">{{ bgcInfo.name }}</div>
          <div class="detail">{{ bgcInfo.detail }}</div>
        </div>
        <div class="modify" @click="modifyCard(bgcInfo, index)">
          <img :src="imgUrl2" alt="">
        </div>
      </div>
    </div>
  </div>
  <div class="bgc-card" @click="addBgc">
    <div class="bgc-info">
      <div class="bgc-info-name">添加卡片</div>
      <div class="bgc-info-detail">自定义模型背景知识</div>
    </div>
  </div>

  <div v-if="isDialogOpen" class="dialog-container">
    <div class="dialog-header">
      <h2>卡片(id:{{ curBgcInfo.cid }})</h2>
      <div class="close" @click="hideDialog">&times;</div>
    </div>
    <div class="dialog-body">
      <div>
        <label for="name">标题</label>
        <input type="text" id="name" v-model="curBgcInfo.name">
      </div>
      <div>
        <label for="detail">描述</label>
        <textarea id="detail" v-model="curBgcInfo.detail" rows="4" cols="50"></textarea>
      </div>
      <div>
        <label for="content">内容</label>
        <textarea id="content" v-model="curBgcInfo.content" rows="10" cols="50"></textarea>
      </div>
      <div>
        <label for="datetime">创建日期:</label>
        <span>{{ curBgcInfo.datetime }}</span>
      </div>
      <button type="submit" @click.prevent="handleSubmit">确定</button>
      <button type="button" @click="handleDelete" v-if="!isAddCard">删除</button>
      <button type="button" @click="generateBgc(1)" v-if="isAddCard">全部场景</button>
      <button type="button" @click="generateBgc(2)" v-if="isAddCard">当前场景</button>
      <button type="button" @click="generateBgc(3)" v-if="isAddCard">全部笔记</button>
      <button type="button" @click="generateBgc(4)" v-if="isAddCard">当前笔记</button>
      <button type="button" @click="uploadtxt" v-if="isAddCard">上传txt</button>
    </div>
  </div>
</template>

<script>
import HeadPortrait from "./chatWindow/HeadPortrait.vue";
import { getDateTime } from "@/api/getData";
import { test } from "@/api/test"
import { generate_bgc, send_bgc_card, get_bgc_card, update_bgc_card, delete_bgc_card } from "@/api/chat/backgroundcard"

export default {
  components: {
    HeadPortrait,
  },
  props: {
    bgcList: Array,
  },
  data() {
    return {
      imgUrl: require('@/assets/img/bgc.jpg'),
      imgUrl2: require('@/assets/img/modify.png'),

      isDialogOpen: false,
      isAddCard: false,
      modifiedIndex: 0,
      curBgcInfo: {
        cid: 0,
        name: '默认背景摘要',
        detail: '此时大模型不具备任何背景知识',
        content: '',
        datetime: '',
        status: 0,
      }
    }
  },
  methods: {
    selectBgc(bgcInfo) {
      this.$message.success('已选摘要：' + bgcInfo.name);
      this.$emit('update:selectBgc', bgcInfo);
      // TODO关闭父级窗口
    },
    modifyCard(bgcInfo, index) {
      this.modifiedIndex = index;
      this.curBgcInfo = bgcInfo;
      this.curBgcInfo.datetime = getDateTime();
      this.isDialogOpen = true;
    },
    hideDialog() {
      this.isDialogOpen = false;
    },
    handleSubmit() {
      this.bgcList[this.modifiedIndex] = this.curBgcInfo;
      if (this.isAddCard) {
        let formData = new FormData();
        if(this.curBgcInfo.status === 1) {
          formData.append('username', 'NKCNGBrain');
        } else if(this.curBgcInfo.status === 2) {
          formData.append('username', localStorage.getItem('realName'));
        } else if(this.curBgcInfo.status === 3) {
          formData.append('username', localStorage.getItem('realName'));
        } else if(this.curBgcInfo.status === 4) {
          formData.append('username', localStorage.getItem('userId'));
        } else {
          formData.append('username', localStorage.getItem('userId'));
        }
        formData.append('bgcard', JSON.stringify(this.curBgcInfo));
        send_bgc_card(formData).then(response => {
          this.$message.success('更新成功！');
          this.updateBgcList();
        }).catch(error => {
          this.$message.error(error);
        });
      }
      else {
        let cid = this.curBgcInfo.cid;
        console.log('即将更新的cid：', cid);
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('bgcard', JSON.stringify(this.curBgcInfo));
        update_bgc_card(formData).then(response => {
          this.$message.success('更新成功！');
          this.updateBgcList();
        }).catch(error => {
          this.$message.error(error);
        });
      }
      this.isAddCard = false;
      this.isDialogOpen = false;
      this.curBgcInfo = {
        cid: 0,
        name: '默认背景摘要',
        detail: '此时大模型不具备任何背景知识',
        content: '',
        datetime: '',
        status: 0,
      }
      this.updateBgcList();
      this.$message.success('完成卡片更新！');
    },
    handleDelete() {
      let cid = this.curBgcInfo.cid;
      console.log('即将删除的cid：', cid);
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('bgcard', JSON.stringify(this.curBgcInfo));
      delete_bgc_card(formData).then(response => {
        this.$message.success('删除成功！');
        this.updateBgcList();
      }).catch(error => {
        this.$message.error(error);
      });
    },
    addBgc() {
      this.curBgcInfo = {};
      this.isDialogOpen = true;
      this.isAddCard = true;
    },
    uploadtxt(event) {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.txt'; // 只允许选择txt文件
      input.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
          const reader = new FileReader();
          reader.onload = (e) => {
            this.curBgcInfo.content = e.target.result;
          };
          reader.readAsText(file);
        }
      });
      input.click();
      this.curBgcInfo.status = 5;
    },
    generateBgc(num) {
      this.curBgcInfo.content = '正在调用大模型总结，不要离开！！！！！！！！！！！！！！';
      this.curBgcInfo.status = num;
      if (num == 1) {
        this.curBgcInfo.name = "全部场景背景摘要";
      } else if (num == 2) {
        this.curBgcInfo.name = localStorage.getItem('sceneName') + "场景背景摘要";
      } else if (num == 3) {
        this.curBgcInfo.name = localStorage.getItem('realName') + "全部笔记本背景摘要";
      } else if (num == 4) {
        this.curBgcInfo.name = localStorage.getItem('userId') + "笔记本背景摘要";
      }
      this.curBgcInfo.detail = this.curBgcInfo.name;
      let formData = new FormData();
      let realName = localStorage.getItem('realName');
      let userbookName = localStorage.getItem('userId');
      let sceneName = localStorage.getItem('sceneName');
      formData.append('realName', realName);
      formData.append('userbookName', userbookName);
      formData.append('sceneName', sceneName);
      formData.append('num', num);
      generate_bgc(formData).then(response => {
        this.curBgcInfo.content = response.content;
      }).catch(e => {
        this.$message.error(e);
      })
    },
    updateBgcList() {
      this.$emit('update:bgcList');

      this.isDialogOpen = false;
      this.isAddCard = false;
    },
  },
  mounted() {
    this.updateBgcList();
  }
};
</script>

<style lang="scss" scoped>
.bgc {
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
        width: 180px;
        overflow-x: hidden;
      }

      .detail {
        color: #5c6675;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        font-size: 12px;
        width: 180px;
        overflow-x: hidden;
      }
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

.head-portrait {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  // border: 2px solid rgb(137,140,151);
  border: 2px solid rgb(255, 255, 255);
  position: relative;

  &::before {
    content: '';
    width: 15px;
    height: 15px;
    z-index: 1;
    display: block;
    border-radius: 50%;
    background-color: rgb(144, 225, 80);
    position: absolute;
    right: 0;
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



.modify {
  width: 50px;
  height: 50px;
  border-radius: 50%;
  // border: 2px solid rgb(137,140,151);
  border: 2px solid rgb(255, 255, 255);
  position: relative;
  transition: .5s ease;
  margin-left: 50px;

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

  &:hover {
    transform: scale(1.04);
  }
}


.bgc-card {
  width: 400px;
  height: 100px;
  border-radius: 20px;
  background-color: rgb(50, 54, 68);
  position: relative;
  margin: auto;
  margin-top: 20px;
  cursor: pointer;

  &:hover {
    background-color: #1d90f5;
    transition: 0.3s;
    box-shadow: 0px 0px 10px 0px rgb(0, 136, 255);
  }
}

.bgc-info {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 90%;
  transform: translate(-50%, -50%);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  // align-items: center;
  justify-content: center;
}

.bgc-info-name {
  color: #fff;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  margin-bottom: 5px;
}

.bgc-info-detail {
  color: #5c6675;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 12px;
}

.dialog-container {
  position: fixed;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -50%);
  background-color: white;
  padding: 20px;
  border: 1px solid #ccc;
  z-index: 1000;
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dialog-body {
  margin-top: 20px;
}

.close {
  cursor: pointer;
  font-size: 24px;
  color: #ccc;
}

.close:hover {
  color: #999;
}
</style>