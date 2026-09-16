<template>
    <div class="navbar">
        <el-button @click="returnHome">
            <i class="el-icon-home"></i>
        </el-button>
        <div class="nav-container">
            <el-button @click="userFeedBack">
                <i class="el-icon-OIP"></i>
            </el-button>
            <el-button @click="seed">
                <i class="el-icon-seed"></i>
            </el-button>
            <el-button @click="toggleStyle">
                <i :class="sunOrMoon === 0 ? 'el-icon-sun' : 'el-icon-moon'"></i>
            </el-button>
            <el-button @click="uploadPrompt">
                <i class="el-icon-prompt"></i>
            </el-button>
            <input ref="fileInput" type="file" accept=".xls,.xlsx" style="display: none;" @change="handleFileChange">
            <el-button @click="settings">
                <i class="el-icon-setting"></i>
            </el-button>
            <el-button @click="admin">
                <i class="el-icon-admin"></i>
            </el-button>
            <el-button v-if="isLoggedIn" @click="logout">
                <i class="el-icon-user1"></i>
            </el-button>
            <el-button v-else @click="login">
                <i class="el-icon-user2"></i>
            </el-button>
        </div>
    </div>
</template>
  
<script>
import router from '@/router'
import { prompt_upload } from "@/api/chat/send_message"
import { saveSceneExcel, saveAndReloadSceneExcel } from "@/views/pages/mainHome/my_js";
import { get_context } from "@/api/chat/send_message"

import { modelManager } from '@/utils/ModelManager.js';


export default {
    data() {
        return {
            context_data: null,
            isLoggedIn: false, // 初始状态为未登录
            currentModule: 0,
            sunOrMoon: 0,
        };
    },
    props: {
        needWaitFile: Number,
        clickAdmin: Boolean,
    },
    watch: {
        clickAdmin(newVal) {
            if (newVal === true) {
                this.$emit('clickOver');
                this.admin();
            }
        }
    },
    methods: {
        userFeedBack() {
            this.$emit('userFeedBack');
        },
        returnHome() {
            console.log('Return home clicked');
            // router.push('/main');
            // 改：退出时清空接入的模型信息缓存
            localStorage.removeItem('modelManagerCache'); 
            console.log('已清空ModelManager缓存');
            localStorage.removeItem('modelList'); 
            console.log('已清空模型缓存');
            modelManager.init().catch(err => {
                console.error('模型管理器自动初始化失败:', err);
            });

            this.login()
        },
        toggleStyle() {
            this.sunOrMoon = (this.sunOrMoon + 1) % 2
            // this.currentModule = (this.currentModule + 1) % 2;
            this.$emit('updateStyle', this.sunOrMoon);
        },
        uploadPrompt() {
            console.log('Prompt clicked');
            // 这里可以添加上传提示词的逻辑
            this.$refs.fileInput.click();
        },
        settings() {
            console.log('Settings clicked');
            // 这里可以添加打开设置的逻辑
            this.$emit('update:params');
        },
        seed() {
            console.log('seed clicked');
            router.push('/seed')
        },
        admin() {
            console.log('admin clicked');
            if (localStorage.getItem('controlled') === 'true'){

            } else {
                localStorage.setItem('controlled', 'false');
            }

            this.$emit('updateContext')
            setTimeout(() => { 
                localStorage.setItem('firstBookUser', localStorage.getItem('realName'));
                localStorage.setItem('firstBookName', localStorage.getItem('userId').substring(localStorage.getItem('realName').length + 1));
                // 这里不对，取到的是用户刚在home加载本子时候的数据，进入本子后的操作没有更新过来，所以无法即使看见，需要在点进去前获取一次数据
                // localStorage.setItem('firstBookContext', localStorage.getItem('context_data'));
                let formData = new FormData();
                formData.append('username', localStorage.getItem('realName'));
                formData.append('bookname', localStorage.getItem('userId').substring(localStorage.getItem('realName').length + 1));
                get_context(formData).then(response => {
                    if (response.error_num === 0) {
                        this.$message.success('刷新成功');
                        localStorage.setItem('firstBookContext', response.contextData);
                        router.push('/live')
                    } else {
                        this.$message.error('刷新失败');
                    }
                });
            }, 50); 
        },
        login() {
            this.isLoggedIn = true;
            console.log('Login clicked');
            // 这里可以添加登录的逻辑
            if(this.needWaitFile === 0)
                this.backtohome();
            else
                this.$message.error("您还有文件在上传，请耐心等待，尽量不要退出！");
        },
        logout() {
            this.isLoggedIn = false;
            console.log('Logout clicked');
            // 这里可以添加退出登录的逻辑
            if(this.needWaitFile === 0)
                this.backtohome();
            else
                this.$message.error("您还有文件在上传，请耐心等待，尽量不要退出！");
        },
        backtohome() {
            localStorage.setItem('exitJustNow', localStorage.getItem('userId'));
            localStorage.setItem('userId', localStorage.getItem('originRealName'));
            localStorage.setItem('realName', localStorage.getItem('originRealName'));
            // router.push('/home');
            router.push({
                path: '/home',
                query: { from: 'main', to: 'home', bookId: localStorage.getItem('userId') }
            });
        },
        handleFileChange(e) {
            const file = e.target.files[0];

            if (file) {
                // 可以在这里进行文件的预处理，例如读取文件内容等
                const reader = new FileReader();

                reader.onload = (e) => {
                    const fileData = e.target.result.split(',')[1]; // 获取文件的数据，去除前缀
                    let formData = new FormData();
                    formData.append('username', localStorage.getItem('userId'));
                    formData.append('sname', localStorage.getItem('sceneName'));
                    formData.append('file', fileData); // 添加文件数据到 FormData
                    console.log(formData);
                    // prompt_upload(formData);
                    saveAndReloadSceneExcel(formData).then(response => {
                        if (response.error_num === 0) {
                            localStorage.setItem('subSceneList', response['subSceneList']);
                        }
                        else {
                        }
                    });
                };
                reader.readAsDataURL(file); // 读取文件内容，以Base64编码的形式
            } else {
                console.log('未选择文件');
            }


        }
    }
};
</script>
  
<style scoped>
.navbar {
    justify-content: space-between;
    align-items: center;
    background-color: #ffffff;
    width: 100%;
    height: 6vh;
}

.nav-container {
    float: right;
    width: 280px;
}

.nav-container::after {
  content: '';
  display: block;
  height: 3px;
  background-color: purple;
  margin-top: 10px;
}

button {
    border: none;
    background: none;
    cursor: pointer;
    margin-left: 10px;
    padding: 5px;
    outline: none;
    transition: background-color 0.3s;
}

button:hover {
    background-color: #ccc;
}


.el-icon-home {
    background-image: url('@/assets/img/nav/home.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 28px;
    height: 28px;
    left: 0px;
    top: 0px;
    display: flex;
}

.el-icon-OIP {
    background-image: url('@/assets/img/nav/OIP.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-seed {
    background-image: url('@/assets/img/nav/seed.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-sun {
    background-image: url('@/assets/img/nav/PhSunFill.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-moon {
    background-image: url('@/assets/img/nav/PhMoonStarsDuotone.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-prompt {
    background-image: url('@/assets/img/nav/prompt.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-admin {
    background-image: url('@/assets/img/nav/admin.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-setting {
    background-image: url('@/assets/img/nav/setting_grey.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-user1 {
    background-image: url('@/assets/img/nav/user_grey.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}

.el-icon-user2 {
    background-image: url('@/assets/img/nav/user_blue.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 18px;
    height: 18px;
    margin-top: 8px;
}
</style>