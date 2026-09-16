<template>
    <div style="text-align: center;">
        <div class="container">
            <h1>红蓝种子工程</h1>
            <div class="selection-wrapper">
                <select v-model="selectedDataValue" @change="handleDataSelect" class="custom-select">
                    <option v-for="option in optionsData" :key="option" :value="option">
                        {{ option }}
                    </option>
                </select>

                <select v-if="selectedDataValue" v-model="selectedModelValue" @change="handleModelSelect" class="custom-select">
                    <option v-for="option in optionsModel" :key="option" :value="option">
                        {{ option }}
                    </option>
                </select>
            </div>

            <div class="selection-wrapper-down">
                <h2>用户数据评估反馈</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Question</th>
                            <th>Answer</th>
                            <th>Score</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="item in data" :key="item.question">
                            <td>
                                <span class="full-text" v-text="item.question"></span>
                                {{ item.question }}
                            </td>
                            <td>
                                <span class="full-text" v-text="item.answer"></span>
                                {{ item.answer }}
                            </td>
                            <td>
                                <div class="score-wrapper">
                                    {{ item.score }}
                                    <div class="humanscore-button" :class="{ 'checked': checkStates[item.question] }" 
                                    @click="onHumanScore(item)" title="人工打分"></div>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <el-dialog v-model="dialogVisible" width="30%" :before-close="handleClose" class="myScoreDialog"
                :close-on-click-modal="false" :close-on-press-escape="false">
                <h1 class="score-login-title">请进行人工评分</h1>
                <el-form :model="score" label-width="80px">
                    <el-form-item label="人工评分">
                        <el-input class="myScoreinput" v-model="score.human"></el-input>
                    </el-form-item>
                    <el-form-item label="GPT4评分">
                        <el-input class="myScoreinput" v-model="score.GPT4" disabled></el-input>
                    </el-form-item>
                </el-form>
                <template #footer>
                    <div class="dialog-footer">
                        <el-button class="myScorebutton" type="primary" @click="submitScore">完 成</el-button>
                    </div>
                </template>
            </el-dialog>
        </div>
    </div>
</template>

<script>
import { get_backdata } from "@/api/getBackData"
import { good_data_upload } from "@/api/card/send_card"
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog } from 'element-plus'

export default {
    components: {
        ElForm,
        ElFormItem,
        ElInput,
        ElButton,
        ElDialog,
    },
    mounted() {
        this.fetchBackData();
    },
    data() {
        return {
            optionsData: ['微调数据集a', '微调数据集b', '微调数据集c'],
            optionsModel: ['微调大模型1', '微调大模型2', '微调大模型3'],
            selectedDataValue: '',
            selectedModelValue: '',
            data: [
                { question: "问题1", answer: "回答1", score: "得分1" },
                { question: "问题2", answer: "回答2", score: "得分2" },
                { question: "问题3", answer: "回答3", score: "得分3" }
                // 更多数据...
            ],
            dialogVisible: false,
            score: {
                human: '',
                GPT4: ''
            },
            Question: '',
            Answer: '',
            checkStates: {},  // 使用对象来存储每个 item 的 checked 状态
        };
    },
    methods: {
        handleDataSelect() {
            
        },
        handleModelSelect() {
            if(this.selectedModelValue === '微调大模型1')
                this.$emit('changeFineTune')
            // zymgai
            this.$emit('chageModel',this.selectedModelValue);
            // zymgai
        },
        fetchBackData() {
            let formData = new FormData();
            formData.append('username', 'admin');

            get_backdata(formData).then(response => {
                if (response.error_num === 0) {
                    this.$message.success('用户数据反馈加载成功！');
                    this.data = response.data;
                    console.log("后端传来的反馈数据：", response.data);

                    // 根据data条数初始化check状态列表
                    this.data.forEach((item) => {
                        this.checkStates[item.question] = false;
                    });
                } else {
                    this.$message.error('用户数据反馈加载失败')
                }
            });
        },
        onHumanScore(item) {
            this.dialogVisible = true;
            this.Question = item.question;
            this.Answer = item.answer;
            this.score.GPT4 = item.score;
            // 获取当前状态的副本
            const currentCheckStates = { ...this.checkStates };
            if(currentCheckStates[item.question] === false) {
                currentCheckStates[item.question] = !currentCheckStates[item.question];
            }
            this.checkStates = currentCheckStates;
        },
        handleClose(done) {
            this.score.human = ''
            this.score.GPT4 = ''
            done();
        },
        submitScore() {
            // this.dialogVisible = false;
            this.checkScore();
            this.score.human = ''
            this.score.GPT4 = ''
            this.dialogVisible = false
        },
        checkScore() {
            const a = 1.0;  // 分差阈值a，超过此值认为置信度较低
            const maxDifference = 5;
            const b = 0.9;  // 相似度阈值b = 90%
            const c = 0.95; // 相似度阈值c = 95%
            // 将字符串类型的评分转换为浮点数
            const humanScore = parseFloat(this.score.human);
            const modelScore = parseFloat(this.score.GPT4);
            
            const difference = Math.abs(humanScore - modelScore);
            let similarity = ((maxDifference - difference) / maxDifference);

            let formData = new FormData();
            formData.append('question', this.Question);
            formData.append('answer', this.Answer);
            formData.append('score', this.score.GPT4);

            // 检查分差是否超过阈值a
            if (difference > a) {
                this.$message.error('评分置信度较低，人工和大模型评分存在明显差异!');
            } else if (similarity >= c) {
                good_data_upload(formData).then(response => {
                    if (response.error_num === 0) {
                    this.$message.success('高质量问答数据反馈成功！');
                    } else {
                    this.$message.error('高质量问答数据反馈失败')
                    }
                });
                this.$message.success('评分可置信度非常高！'+`评分差距为 ${difference.toFixed(1)}，相似度为 ${(similarity * 100).toFixed(2)}%。`);
            } else if (similarity >= b) {
                good_data_upload(formData).then(response => {
                    if (response.error_num === 0) {
                    this.$message.success('高质量问答数据反馈成功！');
                    } else {
                    this.$message.error('高质量问答数据反馈失败')
                    }
                });
                this.$message.success('评分可置信度较高！'+`评分差距为 ${difference.toFixed(1)}，相似度为 ${(similarity * 100).toFixed(2)}%。`);
            } else {
                this.$message.success('评分可置信度中等，'+`评分差距为 ${difference.toFixed(1)}，相似度为 ${(similarity * 100).toFixed(2)}%。`);
            }
        },
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

.selection-wrapper-down {
  background-color: #f9f9f9;
  border: 1px solid #ddd;
  border-radius: 8px;
  padding: 20px;
  margin-top: 60px;
  max-height: 250px; /* 根据需要设置表格的最大高度 */
  overflow-y: auto; /* 添加垂直滚动条 */

  /* 这里将.full-text做到最佳的定位方式 */
  position: relative;
}

table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed; /* 这有助于防止行之间的内容溢出 */
}

th, td {
  padding: 8px;
  border: 1px solid #ccc;
  text-align: left;
  overflow: hidden; /* 隐藏溢出的内容 */
  text-overflow: ellipsis; /* 如果内容太长，则显示省略号 */
  white-space: nowrap; /* 防止文本换行 */
}

th {
  background-color: #f2f2f2;
}

tbody tr:nth-child(odd) {
  background-color: #f9f9f9;
}



td:hover .full-text {
  visibility: visible; /* 显示工具提示 */
  opacity: 1;
}

td .full-text {
  visibility: hidden; /* 默认隐藏工具提示 */
  opacity: 0;
  transition: opacity 0.4s ease; /* 定义渐变效果 */
  position: absolute;
  z-index: 100;
  background: #fff;
  border: 2px solid #989797;
  border-radius: 10px;
  padding: 12px;
  box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);

  max-width: 1000px; /* 为工具提示设置一个最大宽度 */
  word-break: break-all; /* 允许在任意字符间断行 */
  white-space: normal; /* 允许换行 */

  overflow: auto; /* 如果内容超出，显示滚动条 */
}



.score-wrapper {
  display: flex; /* 使用Flexbox布局 */
  align-items: center; /* 垂直居中 */
}

.humanscore-button {
  background-size: contain;
  background-repeat: no-repeat;
  vertical-align: middle;
  height: 22px;
  width: 22px;
  border-radius: 3px;
  z-index: 10; /* 确保按钮在页面内容的上方 */
  cursor: pointer; /* 显示可点击的鼠标指针 */
  margin-left: 120px;
}

.humanscore-button.checked {
  background-image: url('@/assets/img/pin_blue.png');
}

.humanscore-button:not(.checked) {
  background-image: url('@/assets/img/pin_grey.png');
}




.myScoreDialog {
  position: relative;
  top: 92px;
  width: 450px;
  height: 280px;
  border-radius: 10px;
  background: transparent;
  background-image: url('https://img.tukuppt.com/ad_preview/00/05/71/5c98de77dc9e8.jpg!/fw/980');
  background-size: 100% 100%;
}
.score-login-title {
  font-size: 30px;
  margin-bottom: 20px;
  color: black;
  /* 将字体颜色设置为黑色 */
}
.myScoreinput {
  width: 270px;
  height: 26px;
}
.myScorebutton {
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
</style>