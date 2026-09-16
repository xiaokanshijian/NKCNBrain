<template>
  <div class="login-container">
    <div class="login-background">
      <div class="background-image"
        :style="{ backgroundImage: 'url(' + backgroundImage + ')', filter: 'brightness(99%)' }"></div>
      <div class="background-overlay"></div>

      <div class="particle-container">
        <!-- <div class="particle" v-for="i in 100" :key="i"></div>
        <div class="particle-2" v-for="j in 100" :key="j"></div> -->
        <div class="particle-3" v-for="m in 100" :key="m"></div>
        <div class="particle-4" v-for="n in 100" :key="n"></div>
        <div class="particle-5" v-for="p in 100" :key="p"></div>
        <div class="particle-6" v-for="q in 100" :key="q"></div>
        <div class="particle-7" v-for="x in 100" :key="x"></div>
        <div class="particle-8" v-for="y in 100" :key="y"></div>
      </div>

      <div class="login-prompt">
        <div class="prompt-container">
          <div class="prompt-title">

            <!-- <h2>欢迎使用 NKCN·Brain V2.3</h2> -->
            <div class="login-centered-name">欢迎使用 NKCN·Brain V3.2</div>
            <div>
              <div class="login-centered-text">NKCN·Brain借助费曼学习法、卢曼卡片盒笔记及都江堰超级自然本体机制与升维语义，清晰化个体与群组思维，助力被AI放大，提高个人人机混合智商，成为超级个体，组织商数提高成为AI原生组织，并外推个人及组织全量知识盲区边界，助力低门槛使用工程本体。</div>
              <div class="login-centered-text">三脑叠加群组商数提升·群组人机熵减升维共生</div>
              <div class="login-centered-text">人机共生驾驭·红蓝卡标指向·升维迭代撰写</div>
              <div class="login-centered-text">涌创蛙鸣·牵引示范·微带赋能·共振群流</div>
              <div class="login-centered-text">人机共生撰写（备教引导·协同迭代·群组对齐）</div>
              <div class="login-centered-text"><卡标指向·比对迭代·原生AI·赋能共生></div>
              <div class="login-centered-text">打格子分节点·搭梯子分层级·创卡片留关键·用卡标多迭代</div>
              <div class="login-centered-text">透过OpenClaw支持多模态, 对接多源大模型, 包括开源Kimi K3/DeepSeek4.x/Qwen等、闭源GPT5.6/Claude Fable5/Gemini3.x 等，支持阅读、学习、创作、设计、研究、纸联&体联，与数据集制备等七大场景。</div>
            </div>
            <!-- <p>未来支持多模态, 对接多源大模型, 包括开源Llama、闭源GPT4等以及群组认知驱动的公能GPT</p> -->

          </div>

          <div class="login-form">
            <h1 class="login-title">登录</h1>
            <!-- 添加 UI 模式选择 -->
            <el-radio-group v-model="uiMode" size="small" class="ui-mode-selector">
              <el-radio-button label="unicast">内心独白</el-radio-button>
              <el-radio-button label="minimal">听说对话</el-radio-button>
              <el-radio-button label="simple">简构简用</el-radio-button>
              <el-radio-button label="full">深构深用</el-radio-button>
            </el-radio-group>
            
            <el-form :model="loginForm" label-width="80px">
              <el-form-item label="用户名" class="item">
                <el-input class="myinput" v-model="loginForm.username"></el-input>
              </el-form-item>
              <el-form-item label="密码" class="item">
                <el-input class="myinput" v-model="loginForm.password" type="password" @keyup.enter="login"></el-input>
              </el-form-item>
              <!-- <el-form-item>
                <el-button class="mybutton" type="primary" @click="dialogVisible = true">注册</el-button>
                <el-button class="mybutton" type="primary" @click="resetForm">重置</el-button>
              </el-form-item> -->
            </el-form>
          </div>


          <el-dialog v-model="dialogVisible" width="30%" :before-close="handleClose" class="myDialog"
            :close-on-click-modal="false" :close-on-press-escape="false">
            <h1 class="login-title">请注册新账户</h1>
            <el-form :model="registerForm" label-width="120px">
              <el-form-item label="用户名(英)">
                <el-input class="myinput" v-model="registerForm.username"></el-input>
              </el-form-item>
              <el-form-item label="密码">
                <el-input class="myinput" v-model="registerForm.password" type="password"></el-input>
              </el-form-item>
              <el-form-item label="组织层级">
                <el-select v-model="registerForm.level" placeholder="在此处选取您在组织中的层级" class="myinput">
                  <el-option label="超级组织电脑S级" value="S"></el-option>
                  <el-option label="T级" value="T"></el-option>
                  <el-option label="TA级" value="TA"></el-option>
                  <el-option label="组长GL级" value="GL"></el-option>
                  <el-option label="组员GM级" value="GM"></el-option>
                </el-select>
              </el-form-item>
              <el-form-item label="领航员用户名">
                <el-input class="myinput" v-model="registerForm.coacher"></el-input>
              </el-form-item>
            </el-form>
            <template #footer>
              <div class="dialog-footer">
                <el-button class="mybutton" @click="deleteRegister">取 消</el-button>
                <el-button class="mybutton" type="primary" @click="submitRegister">确 定</el-button>
              </div>
            </template>
          </el-dialog>


          <div class="prompt-button">
            <el-button class="mybutton" type="primary" @click="login">立即登录</el-button>
            <el-button class="mybutton" type="primary" @click="dialogVisible = true">注册</el-button>
          </div>
        </div>
      </div>
      <div class="login-footer">
        <p>© 2024 NanKai LLM</p>
      </div>
    </div>
  </div>

  <router-view />
</template>

<script>
// import { ref } from 'vue'
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElRadioGroup, ElRadioButton, ElSelect, ElOption } from 'element-plus'
import { addUser, verifyUser, get_userChosen } from '@/api/user'
// import router from "@/router/index.js";
import router from '@/router'
import { addScene } from "@/views/pages/mainHome/my_js"

export default {
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    ElRadioGroup,
    ElRadioButton,
    ElSelect,
    ElOption,
  },
  data() {
    return {
      // backgroundImage: 'https://ts1.cn.mm.bing.net/th/id/R-C.e68edefcc5e5946112ab1a8b414219d6?rik=EMYDzNglNH9C1A&riu=http%3a%2f%2f5b0988e595225.cdn.sohucs.com%2fimages%2f20170715%2fdf98a4c987e44b61b334fea09f9f8e8f.gif&ehk=lQt9UN1KPTHP%2b6jD30In4sfsU1DVrlopg11ot4kGJDc%3d&risl=&pid=ImgRaw&r=0',
      backgroundImage: require('@/assets/img/login.png'),
      loginForm: {
        username: '',
        password: ''
      },
      registerForm: {
        username: '',
        password: '',
        level: '',    // 新增字段
        coacher: ''
      },
      dialogVisible: false,    // 控制对话框显示/隐藏
      uiMode: 'full',           // 默认使用完整模式
    }
  },
  mounted() {
    // 去除默认边距
    document.body.style.margin = '0';
    console.log("浏览器内存记录用户名：", localStorage.getItem('originRealName'))
    if (localStorage.getItem('originRealName') !== null) {
      this.getChosen()
    } else {
      if (localStorage.getItem('home2login') === "true") {
        localStorage.setItem('home2login', 'false');
      }
    }
  },
  methods: {
    getChosen(){
      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      get_userChosen(formData).then(data => {
        if(data['error_num'] === 0) {
          let choose = data['choose']
          if(choose === 0) {
            this.uiMode = "full"
          } else if(choose === 1) {
            this.uiMode = "simple"
          } else if(choose === 2) {
            this.uiMode = "minimal"
          } else {
            this.uiMode = "unicast"
          }
          if (localStorage.getItem('home2login') !== "true") {
            this.quickLogin()
          } else {
            localStorage.setItem('home2login', 'false');
            this.loginForm.username = localStorage.getItem('originRealName')
            this.loginForm.password = localStorage.getItem('password')
          }
        } else {
          this.$message.error(data['message'])
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    register() {
      this.dialogVisible = true;
    },
    handleClose(done) {
      this.registerForm.username = ''
      this.registerForm.password = ''
      done();
    },
    deleteRegister() {
      // this.registerForm.username = ''
      // this.registerForm.password = ''
      // this.registerForm.coacher = ''
      this.dialogVisible = false;
    },
    submitRegister() {
      // 处理注册逻辑
      if (this.registerForm.username === '' || this.registerForm.password === '' || this.registerForm.level === '' || this.registerForm.coacher === '') {
        this.$message.error('注册失败，所有项均不能为空！')
      } else {
        let name = this.registerForm.username;
        addUser(this.registerForm.username, this.registerForm.password, this.registerForm.level, this.registerForm.coacher).then(response => {
          if (response.error_num === 0) {
            // addScene(name, '阅读');
            this.$message.success('注册成功！');
          } else if (response['msg'] === 'Username already exists') {
            this.$message.error('注册失败，用户名重复，请更换！')
          } else if (response['msg'] === 'coacher用户名不存在') {
            this.$message.error('注册失败，领航员用户名不存在，请检查！')
          } else if (response['msg'] === '您填写的组织关系或领航员有误') {
            this.$message.error('注册失败，您填写的组织关系或领航员有误，请检查！')
          } else {
            this.$message.error('注册失败，请重试！')
            console.log(response['msg'])
          }
        })
      }

      // this.registerForm.username = ''
      // this.registerForm.password = ''
      this.dialogVisible = false;
    },
    resetForm() {
      this.loginForm.username = ''
      this.loginForm.password = ''
    },
    quickLogin() {
      this.$message.success('浏览器已有登录记录，自动登录成功！');
      localStorage.setItem('userId', localStorage.getItem('originRealName'));
      localStorage.setItem('realName', localStorage.getItem('originRealName'));
      localStorage.setItem('byuplevel', 'false');
      console.log("用户领航员、用户层级：", localStorage.getItem('coacherName'), localStorage.getItem('level'))
      // 管理员用户admin
      if(localStorage.getItem('originRealName') === 'admin') {
        localStorage.setItem('byadmin', 'true');
        router.push('/adminhome');
      } else {
        localStorage.setItem('byadmin', 'false');
        // 根据UI模式选择不同的路由
        if(this.uiMode === 'full') {
          localStorage.setItem('fromPath', '/')
          router.push({
            path: '/home',
            query: { from: 'login', to: 'home', bookId: localStorage.getItem('userId') }
          });
        } else if(this.uiMode === 'simple') {
          router.push('/simple');
        } else if(this.uiMode === 'minimal') {
          router.push('/minimal');
        } else {
          router.push('/unicast');
        }
      }
    },
    login() {
      verifyUser(this.loginForm.username, this.loginForm.password, this.uiMode).then(response => {
        // alert(response.msg)
        if (response.error_num === 0) {
          if (response.msg === 'success') {
            this.$message.success('登录成功！');
            localStorage.setItem('userId', response.name);
            localStorage.setItem('realName', response.name);
            localStorage.setItem('originRealName', response.name);
            localStorage.setItem('coacherName', response.coacherName);
            localStorage.setItem('level', response.level);
            localStorage.setItem('byuplevel', 'false');
            localStorage.setItem('password', this.loginForm.password);
            // 管理员用户admin
            if(response.name === 'admin') {
              localStorage.setItem('byadmin', 'true');
              router.push('/adminhome');
            } else {
              localStorage.setItem('byadmin', 'false');
              // 根据UI模式选择不同的路由
              if(this.uiMode === 'full') {
                localStorage.setItem('fromPath', '/')
                router.push('/home');
              } else if(this.uiMode === 'simple') {
                router.push('/simple');
              } else if(this.uiMode === 'minimal') {
                router.push('/minimal');
              } else {
                router.push('/unicast');
              }
            }
          } else {
            if (response.msg === 'User does not exist') {
              this.$message.error('登录失败，用户不存在！')
            } else {
              this.$message.error('登录失败，密码错误或未通过审核！')
            }
          }
        } else {
          this.$message.error('登录失败，请检查网络！')
          console.log(response['msg'])
        }
      })
    }
  }
}
</script>

<!-- <style scoped> -->
<style>
/* element样式自定义 */
.login-centered-name {
  text-align: center; /* 水平居中 */
  font-size: 44px; /* 字体大小 */
  font-weight: bolder;
  margin-bottom: 20px;
}
.login-centered-text {
  text-align: center; /* 水平居中 */
  font-size: 15px; /* 字体大小 */
  line-height: 1.3; /* 行高 */
  margin: 1px 0; /* 段落间距 */
}


.mybutton {
  width: 80px;
  height: 32px;
  background-color: #5e5e62;
  border-color: #2b2a2a;
  color: rgb(227, 223, 223);

  &:hover {
    background-color: #7e7e82;
    border-color: #151414;
    color: #ffffff;
  }
}

.myinput {
  width: 270px;
  height: 26px;
}

.item .el-form-item__label {
  color: rgb(25, 24, 24);
}

.myDialog {
  position: relative;
  top: 100px;
  width: 500px;
  height: 380px;
  border-radius: 10px;
  background: transparent;
  background-image: url('https://img.tukuppt.com/bg_grid/00/09/14/b0GWKwDYKD.jpg!/fh/350');
  background-size: 100% 100%;
}

/* css自定义 */
.login-container {
  display: flex;
  height: 100vh;
}

.login-form {
  width: 400px;
  padding: 30px;
  margin: auto;
}

.login-title {
  font-size: 30px;
  margin-bottom: 10px;
  color: black;
  /* 将字体颜色设置为黑色 */
}

.login-background {
  flex: 1;
  position: relative;
  animation: fadeIn 1s ease-in-out;
}

.background-image {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-size: cover;
}

.background-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgb(0, 0, 0, 0.1);
}

.login-prompt {
  position: absolute;
  top: 46%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: white;
  text-align: center;
  width: 80%;
}

.login-prompt .prompt-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
}

.login-prompt .prompt-title {
  text-align: center;
}

.login-prompt .prompt-title h1 {
  font-size: 48px;
  margin-bottom: 20px;
}

.login-prompt .prompt-title p {
  font-size: 18px;
  line-height: 1.5em;
}

.login-prompt .prompt-button {
  display: flex;
  gap: 12px;
}

.login-footer {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  box-sizing: border-box;
  padding: 10px;
  text-align: center;
  color: white;
  font-size: 12px;
}

/* 新增样式 */
.login-container {
  background-color: #f5f5f5;
}

.login-form {
  background-color: #4e2c2c;
  border-radius: 10px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);

  background-image: url('https://bpic.588ku.com/back_our/bg/20201021/bg/d22a73a368c76_431735.jpg');
  background-size: cover;
  /* 让背景图片充满整个容器 */
  background-position: center;
  /* 居中对齐背景图片 */
  padding: 20px;
  /* 添加一些内边距以使内容不会太靠近边框 */
}

.login-background {
  background-color: #000;
}

.background-image {
  opacity: 0.3;
}

.login-prompt {
  background-color: rgba(0, 0, 0, 0.5);
  padding: 30px;
  border-radius: 10px;
}

.login-prompt .prompt-title h1 {
  color: #fff;
}

.login-prompt .prompt-title p {
  color: #ccc;
}

.login-prompt .prompt-button {
  justify-content: center;
}

.login-footer {
  background-color: rgba(0, 0, 0, 0.5);
}

/* 新增动画 */
.login-container {
  animation: fadeIn 1s ease-in-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }

  to {
    opacity: 1;
  }
}

/* 新增粒子效果 */
.particle-container {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
}

.particle {
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background-color: #ffffff69;
  animation: move 8s infinite;
}

@keyframes move {
  0% {
    transform: translate(2vw, 2vh);
  }

  50% {
    transform: translate(98vw, 98vh);
  }

  100% {
    transform: translate(2vw, 2vh);
  }
}

/* 新增背景音乐 */
/* @media (prefers-reduced-motion: no-preference) {
  body {
    background-music: url('path/to/music.mp3') no-repeat;
    background-music-volume: 0.2;
  }
} */

/* 新增粒子效果 2 */
.particle-2 {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: #ffffff79;
  animation: move-2 10s infinite;
}

@keyframes move-2 {
  0% {
    transform: translate(2vw, 2vh);
  }

  50% {
    transform: translate(98vw, 98vh);
  }

  100% {
    transform: translate(2vw, 2vh);
  }
}

/* 新增粒子效果 3 */
.particle-3 {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: rgba(124, 103, 179, 0.462);
  animation: move-3 8s infinite;
}

@keyframes move-3 {
  0% {
    transform: translate(2vw, 98vh);
  }

  50% {
    transform: translate(98vw, 2vh);
  }

  100% {
    transform: translate(2vw, 98vh);
  }
}

/* 新增粒子效果 4 */
.particle-4 {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background-color: #9f1f7f70;
  animation: move-4 12s infinite;
}

@keyframes move-4 {
  0% {
    transform: translate(2vw, 98vh);
  }

  50% {
    transform: translate(98vw, 2vh);
  }

  100% {
    transform: translate(2vw, 98vh);
  }
}

/* 新增粒子效果 5 */
.particle-5 {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #f7c53074;
  animation: move-5 7s infinite;
}

@keyframes move-5 {
  0% {
    transform: translate(2vw, 20vh);
  }

  50% {
    transform: translate(98vw, 80vh);
  }

  100% {
    transform: translate(2vw, 20vh);
  }
}

/* 新增粒子效果 6 */
.particle-6 {
  position: absolute;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background-color: #37cd6b6b;
  animation: move-6 13s infinite;
}

@keyframes move-6 {
  0% {
    transform: translate(2vw, 80vh);
  }

  50% {
    transform: translate(98vw, 20vh);
  }

  100% {
    transform: translate(2vw, 80vh);
  }
}

/* 新增粒子效果 7 */
.particle-7 {
  position: absolute;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background-color: #e16c2d66;
  animation: move-7 6s infinite;
}

@keyframes move-7 {
  0% {
    transform: translate(30vw, 2vh);
  }

  50% {
    transform: translate(80vw, 98vh);
  }

  100% {
    transform: translate(30vw, 2vh);
  }
}

/* 新增粒子效果 8 */
.particle-8 {
  position: absolute;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background-color: #3dc0d167;
  animation: move-8 7s infinite;
}

@keyframes move-8 {
  0% {
    transform: translate(80vw, 2vh);
  }

  50% {
    transform: translate(30vw, 98vh);
  }

  100% {
    transform: translate(80vw, 2vh);
  }
}


.ui-mode-selector {
    margin-bottom: 20px;
}

.login-form .ui-mode-selector .el-radio-button__original-radio:checked + .el-radio-button__inner {
    background-color: #0b2049 !important;
    border-color: #c4cbd3ec !important;
    color: white !important;
    box-shadow: 0 0 0 0 #c4cbd3ec !important;
}

.login-form .ui-mode-selector .el-radio-button__inner {
    border-color: #c4cbd3ec !important;
}

.login-form .ui-mode-selector .el-radio-button__inner:hover {
    color: #238fc9 !important;
}


/* ========================= 移动端响应式样式 ========================= */

/* 平板设备 (768px 及以下) */
@media screen and (max-width: 768px) {
  .login-prompt {
    width: 95%;
    padding: 20px 15px;
    top: 50%;
  }

  .login-centered-name {
    font-size: 28px;
    margin-bottom: 15px;
    line-height: 1.2;
  }

  .login-centered-text {
    font-size: 13px;
    line-height: 1.4;
    margin: 2px 0;
  }

  .login-form {
    width: 100%;
    max-width: 350px;
    padding: 20px;
    margin: 10px auto;
  }

  .login-title {
    font-size: 24px;
    text-align: center;
  }

  .myinput {
    width: 100%;
    max-width: 250px;
  }

  .mybutton {
    width: 100px;
    height: 36px;
    font-size: 14px;
  }

  .prompt-button {
    flex-direction: column;
    gap: 10px;
    align-items: center;
  }

  .prompt-button .mybutton {
    width: 120px;
  }

  .ui-mode-selector {
    margin-bottom: 15px;
  }

  .ui-mode-selector .el-radio-button {
    margin-bottom: 8px;
  }

  .ui-mode-selector .el-radio-button__inner {
    font-size: 12px;
    padding: 8px 12px;
  }

  /* 注册弹窗适配 */
  .myDialog {
    width: 90% !important;
    max-width: 400px !important;
    top: 50px !important;
    margin: 0 auto;
  }

  /* 粒子效果在移动端适当减少 */
  .particle-3, .particle-4, .particle-5, .particle-6 {
    display: none;
  }
}

/* 手机设备 (480px 及以下) */
@media screen and (max-width: 480px) {
  .login-prompt {
    width: 98%;
    padding: 15px 10px;
    gap: 15px;
  }

  .login-centered-name {
    font-size: 22px;
    margin-bottom: 10px;
    padding: 0 5px;
  }

  .login-centered-text {
    font-size: 11px;
    line-height: 1.3;
    margin: 1px 0;
    padding: 0 5px;
  }

  .login-form {
    width: 100%;
    max-width: 280px;
    padding: 15px;
    margin: 8px auto;
  }

  .login-title {
    font-size: 20px;
    margin-bottom: 15px;
  }

  .myinput {
    width: 100%;
    max-width: 220px;
    height: 32px;
  }

  .mybutton {
    width: 90px;
    height: 38px;
    font-size: 13px;
  }

  .prompt-button .mybutton {
    width: 110px;
  }

  /* UI模式选择器手机端优化 */
  .ui-mode-selector {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 5px;
    margin-bottom: 12px;
  }

  .ui-mode-selector .el-radio-button {
    flex: 0 0 48%;
    margin-bottom: 5px;
  }

  .ui-mode-selector .el-radio-button__inner {
    font-size: 11px;
    padding: 6px 8px;
    width: 100%;
    text-align: center;
  }

  /* 表单项标签优化 */
  .el-form {
    width: 100%;
  }

  .el-form-item {
    margin-bottom: 15px;
  }

  .item .el-form-item__label {
    font-size: 14px;
    width: 60px !important;
  }

  /* 注册弹窗手机端优化 */
  .myDialog {
    width: 95% !important;
    max-width: 320px !important;
    top: 20px !important;
    height: auto !important;
    max-height: 90vh;
    overflow-y: auto;
  }

  .myDialog .login-title {
    font-size: 18px;
  }

  .myDialog .el-form-item__label {
    font-size: 13px;
    width: 80px !important;
  }

  .myDialog .myinput {
    width: 100%;
    max-width: 180px;
  }

  /* 底部版权信息 */
  .login-footer {
    padding: 8px;
    font-size: 10px;
  }

  /* 移动端完全隐藏粒子效果以提升性能 */
  .particle-container {
    display: none;
  }
}

/* 超小屏幕设备 (360px 及以下) */
@media screen and (max-width: 360px) {
  .login-centered-name {
    font-size: 18px;
    line-height: 1.1;
  }

  .login-centered-text {
    font-size: 10px;
    line-height: 1.2;
  }

  .login-form {
    max-width: 260px;
    padding: 12px;
  }

  .login-title {
    font-size: 18px;
  }

  .myinput {
    max-width: 200px;
    height: 30px;
  }

  .mybutton {
    width: 80px;
    height: 36px;
    font-size: 12px;
  }

  .prompt-button .mybutton {
    width: 100px;
  }

  .ui-mode-selector .el-radio-button__inner {
    font-size: 10px;
    padding: 5px 6px;
  }

  .item .el-form-item__label {
    font-size: 13px;
    width: 55px !important;
  }
}

/* 横屏模式优化 */
@media screen and (max-height: 600px) and (orientation: landscape) {
  .login-prompt {
    top: 50%;
    gap: 10px;
  }

  .login-centered-name {
    font-size: 20px;
    margin-bottom: 8px;
  }

  .login-centered-text {
    font-size: 10px;
    margin: 0;
  }

  .login-form {
    padding: 15px;
    margin: 5px auto;
  }

  .login-title {
    font-size: 18px;
    margin-bottom: 10px;
  }

  .ui-mode-selector {
    margin-bottom: 10px;
  }

  .el-form-item {
    margin-bottom: 10px;
  }

  .prompt-button {
    gap: 8px;
  }

  /* 隐藏部分描述文字以节省空间 */
  .login-centered-text:nth-child(n+6) {
    display: none;
  }
}
</style>