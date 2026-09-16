<template>
    <div class="selection-wrapper-up">
        <div class="up-header">
            <h2>话题管理(TOPIC)</h2>
            <select v-model="selectedTopicLevel">
                <option value="0">请选择层级</option>
                <option value="1">level1(10)</option>
                <option value="2">level2(100)</option>
                <option value="3">level3(1000)</option>
                <option value="4">level4(10000)</option>
                <option value="5">level5(10000+)</option>
            </select>
            <input class="search-text" v-model="topicSearch" placeholder="筛选话题" />
            <button @click="topicSearchClicked" title="模糊搜索">搜索</button>
            <div class="total-count">(共{{ totalTopicCount }}条topic)</div>
        </div>
        <div class="header-buttons">
            <button @click="topicIntegrate" title="聚合成为topic卡片">聚合</button>
            <button @click="setAllTopicLevel" title="全部设置为第一个种子的level">同层</button>
            <button @click="setAllTopicScoreH" title="全部设置为第一个种子的scoreH">同分</button>
            <button @click="selectAllTopicSeeds">{{ selectAllTopic[selectedTopicLevel] ? '全消' : '全选' }}</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th title="层级">Level</th>
                    <th title="话题">Topic</th>
                    <th title="评分">Score</th>
                    <th title="人工打分">ScoreH</th>
                    <th title="选中">Check</th>
                    <th title="管理">Manage</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in filteredTopicData" :key="item.question">

                    <td>
                        <input class="full-text" v-model="item.level" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.topic" />
                    </td>
                    <td>
                        <div class="score-wrapper">
                            {{ item.score }}
                        </div>
                    </td>
                    <td>
                        <input class="full-text" v-model="item.scoreH" />
                    </td>
                    <td>
                        <input type="checkbox" v-model="item.selected" />
                    </td>
                    <td>
                        <button @click="seedUpdate(item)" title="修改更新到数据库">更新</button>
                        <button @click="seedDelete(item)" title="删除该topic">删除</button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    <div class="selection-wrapper-down">
        <div class="up-header">
            <h2>问题管理(QUESTION)</h2>
            <select v-model="selectedQuestionLevel">
                <option value="0">请选择层级</option>
                <option value="1">level1(10)</option>
                <option value="2">level2(100)</option>
                <option value="3">level3(1000)</option>
                <option value="4">level4(10000)</option>
                <option value="5">level5(10000+)</option>
            </select>
            <input class="search-text" v-model="questionSearch" placeholder="筛选问题" />
            <button @click="questionSearchClicked" title="模糊搜索">搜索</button>
            <div class="total-count">(共 {{ totalQuestionCount }} 条question)</div>
        </div>
        <div class="header-buttons">
            <button @click="questionIntegrate" title="聚合成为question卡片">聚合</button>
            <button @click="setAllQuestionLevel" title="全部设置为第一个种子的level">同层</button>
            <button @click="setAllQuestionScoreH" title="全部设置为第一个种子的scoreH">同分</button>
            <button @click="selectAllQuestionSeeds">{{ selectAllQuestion[selectedQuestionLevel] ? '全消' : '全选' }}</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th title="层级">Level</th>
                    <th title="话题">Topic</th>
                    <th title="问题">Question</th>
                    <th title="回答">Answer</th>
                    <th title="评分">Score</th>
                    <th title="人工打分">ScoreH</th>
                    <th title="选中">Check</th>
                    <th title="管理">Manage</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in filteredQuestionData" :key="item.question">

                    <td>
                        <input class="full-text" v-model="item.level" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.topic" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.question" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.answer" />
                    </td>
                    <td>
                        <div class="score-wrapper">
                            {{ item.score }}
                        </div>
                    </td>
                    <td>
                        <input class="full-text" v-model="item.scoreH" />
                    </td>
                    <td><input type="checkbox" v-model="item.selected" /></td>
                    <td>
                        <button @click="seedUpdate(item)" title="修改更新到数据库">更新</button>
                        <button @click="seedDelete(item)" title="删除该question">删除</button>
                        <button @click="seedAnswer(item)" title="大模型回答question">回答</button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>

    <div class="topic-dialog" v-if="this.showTopicDialogChecked">
        <div class="topic-dialog-header">
            <h2>聚合卡片：已经选择话题(TOPIC)</h2>
            <div class="close" @click="hideTopicDialog">&times;</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th title="层级">Level</th>
                    <th title="话题">Topic</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in checkedTopicData" :key="item.question">

                    <td>
                        <input class="full-text" v-model="item.level" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.topic" />
                    </td>

                </tr>
            </tbody>
        </table>
        <div class="dialog-btn">
            <button @click="integrate(true)">聚合</button>
        </div>
    </div>

    <div class="question-dialog" v-if="this.showQuestionDialogChecked">
        <div class="question-dialog-header">
            <h2>聚合卡片：已经选择问题(Question)</h2>
            <div class="close" @click="hideQuestionDialog">&times;</div>
        </div>
        <table>
            <thead>
                <tr>
                    <th title="层级">Level</th>
                    <th title="话题">Topic</th>
                    <th title="问题">Question</th>
                    <th title="回答">Answer</th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in checkedQuestionData" :key="item.question">
                    <td>
                        <input class="full-text" v-model="item.level" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.topic" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.question" />
                    </td>
                    <td>
                        <input class="full-text" v-model="item.answer" />
                    </td>
                </tr>
            </tbody>
        </table>
        <div class="dialog-btn">
            <button @click="integrate(false)">聚合</button>
        </div>
    </div>
</template>
<script>
import {
    seed_getTopicData, seed_getQuestionData, seed_integrate
    , seed_update, seed_delete
} from "@/api/seed/lookup"

export default {
    name: "Lookup",
    components: {
    },
    data() {
        return {
            selectAllTopic: {
                "0": false,
                "1": false,
                "2": false,
                "3": false,
                "4": false,
                "5": false,
            },
            selectAllQuestion: {
                "0": false,
                "1": false,
                "2": false,
                "3": false,
                "4": false,
                "5": false,
            },
            topicSearch: "",
            questionSearch: "",
            showTopicDialogChecked: false,
            showQuestionDialogChecked: false,
            selectedTopicLevel: "0",
            selectedQuestionLevel: "0",
            topic_data: [
                { sid: 1, level: 1, topic: "话题1", question: "问题1", answer: "回答1", score: "得分1", scoreH: "人工打分1", selected: false },
                { sid: 2, level: 2, topic: "话题2", question: "问题2", answer: "回答2", score: "得分2", scoreH: "人工打分2", selected: false },
                { sid: 3, level: 3, topic: "话题3", question: "问题3", answer: "回答3", score: "得分3", scoreH: "人工打分3", selected: false },
                { sid: 4, level: 4, topic: "话题4", question: "问题4", answer: "回答4", score: "得分4", scoreH: "人工打分4", selected: false },
                { sid: 5, level: 5, topic: "话题5", question: "问题5", answer: "回答5", score: "得分5", scoreH: "人工打分5", selected: false },
                { sid: 6, level: 6, topic: "话题6", question: "问题6", answer: "回答6", score: "得分6", scoreH: "人工打分6", selected: false },
                { sid: 7, level: 7, topic: "话题7", question: "问题7", answer: "回答7", score: "得分7", scoreH: "人工打分7", selected: false },
            ],

            question_data: [
                { sid: 8, level: 1, topic: "话题1", question: "问题1", answer: "回答1", score: "得分1", scoreH: "人工打分1", selected: false },
                { sid: 9, level: 2, topic: "话题2", question: "问题2", answer: "回答2", score: "得分2", scoreH: "人工打分2", selected: false },
                { sid: 10, level: 3, topic: "话题3", question: "问题3", answer: "回答3", score: "得分3", scoreH: "人工打分3", selected: false },
                { sid: 11, level: 4, topic: "话题4", question: "问题4", answer: "回答4", score: "得分4", scoreH: "人工打分4", selected: false },
                { sid: 12, level: 5, topic: "话题5", question: "问题5", answer: "回答5", score: "得分5", scoreH: "人工打分5", selected: false },
                { sid: 13, level: 6, topic: "话题6", question: "问题6", answer: "回答6", score: "得分6", scoreH: "人工打分6", selected: false },
                { sid: 14, level: 7, topic: "话题7", question: "问题7", answer: "回答7", score: "得分7", scoreH: "人工打分7", selected: false },
            ],
        };
    },
    computed: {
        filteredTopicData() {
            // 如果没有选择level或者选择的是"请选择层级"，则显示所有数据
            if (this.selectedTopicLevel === "0") return this.topic_data;
            // 否则，只显示与选中level匹配的数据
            return this.topic_data.filter(item => item.level.toString() === this.selectedTopicLevel);
        },
        filteredQuestionData() {
            if (this.selectedQuestionLevel === "0") return this.question_data;
            return this.question_data.filter(item => item.level.toString() === this.selectedQuestionLevel);
        },
        checkedTopicData() {
            return this.topic_data.filter(item => item.selected === true);
        },
        checkedQuestionData() {
            return this.question_data.filter(item => item.selected === true);
        },
        totalTopicCount() {
            return this.topic_data.length;
        },
        totalQuestionCount() {
            return this.question_data.length;
        }
    },
    mounted() {
        this.getTopicData(this.topicSearch);
        this.getQuestionData(this.questionSearch);
    },
    methods: {
        topicSearchClicked() {
            this.getTopicData();
        },
        questionSearchClicked() {
            this.getQuestionData();
        },
        getTopicData() {
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('likeSearch', this.topicSearch);
            seed_getTopicData(formData).then(data => {
                this.topic_data = data['data'];
                console.log(this.topic_data);
            }).catch(error => {
                console.log(error);
            });
        },
        getQuestionData() {
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('likeSearchTopic', this.topicSearch);
            formData.append('likeSearchQuestion', this.questionSearch);
            seed_getQuestionData(formData).then(data => {
                this.question_data = data['data'];
                console.log(this.question_data);
            }).catch(error => {
                console.log(error);
            });
        },
        seedUpdate(item) {
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('seedId', item.sid);
            formData.append('seed', JSON.stringify(item));
            seed_update(formData).then(data => {
                this.$message.success("更新成功！");
                this.getTopicData();
                this.getQuestionData();
            }).catch(error => {
                console.log(error);
            });
        },
        seedDelete(item) {
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('seedId', item.sid);
            formData.append('seed', JSON.stringify(item));
            seed_delete(formData).then(data => {
                this.$message.success("删除成功！");
                this.getTopicData();
                this.getQuestionData();
            }).catch(error => {
                console.log(error);
            });
        },
        seedAnswer(item) {
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('seedId', item.sid);
            formData.append('seed', JSON.stringify(item));
            // seed_answer(formData).then(data => {
            //     this.$message.success("回答成功！");
            //     this.getTopicData();
            //     this.getQuestionData();
            // }).catch(error => {
            //     console.log(error);
            // })
        },
        integrate(isTopic) {
            console.log(isTopic);
            let idList = [];
            if (isTopic) {
                this.checkedTopicData.forEach(item => {
                    idList.push(item.sid);
                })
            } else {
                this.checkedQuestionData.forEach(item => {
                    idList.push(item.sid);
                })
            }
            console.log(idList);
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('isTopic', isTopic);
            formData.append('idList', idList);
            // 使用以下方式遍历键值对
            formData.forEach((value, key) => {
                console.log(`${key}: ${value}`);
            });

            seed_integrate(formData).then(data => {
                console.log(data);
            }).catch(error => {
                console.log(error);
            });
        },
        selectAllTopicSeeds() {
            if (this.filteredTopicData[0]) {
                if (this.selectAllTopic[this.selectedTopicLevel] === false) {
                    let count = 0;
                    this.filteredTopicData.forEach(item => {
                        item.selected = true;
                        count++;
                    })
                    this.$message.success(`已全选level ${this.selectedTopicLevel} 下的 ${count} 个topic`);
                    this.selectAllTopic[this.selectedTopicLevel] = !this.selectAllTopic[this.selectedTopicLevel];
                }
                else {
                    this.filteredTopicData.forEach(item => {
                        item.selected = false;
                    })
                    this.$message.success(`已取消选择level ${this.selectedTopicLevel} 下所有topic`);
                    this.selectAllTopic[this.selectedTopicLevel] = !this.selectAllTopic[this.selectedTopicLevel];
                }
            }
            else {
                this.$message.error('当前没有数据!');
            }
        },
        setAllTopicScoreH() {
            if (this.filteredTopicData[0]) {
                let scoreH = this.filteredTopicData[0].scoreH
                this.filteredTopicData.forEach(item => {
                    item.scoreH = scoreH;
                })
                this.$message.success(`已将level ${this.selectedTopicLevel} 下的scoreH全部更新为 ${scoreH}`);
            }
            else {
                this.$message.error('当前没有数据!');
            }
        },
        setAllTopicLevel() {
            if (this.filteredTopicData[0]) {
                let level = this.filteredTopicData[0].level
                this.filteredTopicData.forEach(item => {
                    item.level = level;
                })
                this.$message.success(`已全部更新为level ${level}`);
            }
            else {
                this.$message.error('当前没有数据!');
            }
        },
        selectAllQuestionSeeds() {
            if (this.filteredQuestionData[0]) {
                if (this.selectAllQuestion[this.selectedQuestionLevel] === false) {
                    let count = 0;
                    this.filteredQuestionData.forEach(item => {
                        item.selected = true;
                        count++;
                    })
                    this.$message.success(`已全选level ${this.selectedQuestionLevel} 下的 ${count} 个question`);
                    this.selectAllQuestion[this.selectedQuestionLevel] = !this.selectAllQuestion[this.selectedQuestionLevel];
                }
                else {
                    this.filteredQuestionData.forEach(item => {
                        item.selected = false;
                    })
                    this.$message.success(`已取消选择level ${this.selectedQuestionLevel} 下所有topic`);
                    this.selectAllQuestion[this.selectedQuestionLevel] = !this.selectAllQuestion[this.selectedQuestionLevel];
                }
            }
            else {
                this.$message.error('当前没有数据!');
            }
        },
        setAllQuestionScoreH() {
            if (this.filteredQuestionData[0]) {
                let scoreH = this.filteredQuestionData[0].scoreH
                this.filteredQuestionData.forEach(item => {
                    item.scoreH = scoreH;
                })
                this.$message.success(`已将level ${this.selectedQuestionLevel} 下的scoreH全部更新为 ${scoreH}`);
            }
            else {
                this.$message.error('当前没有数据!');
            }
        },
        setAllQuestionLevel() {
            if (this.filteredQuestionData[0]) {
                let level = this.filteredQuestionData[0].level
                this.filteredQuestionData.forEach(item => {
                    item.level = level;
                })
                this.$message.success(`已全部更新为level ${level}`);
            }
            else {
                this.$message.error('当前没有数据!');
            }
        },
        topicIntegrate() {
            this.showTopicDialog();
        },
        questionIntegrate() {
            this.showQuestionDialog();
        },
        showTopicDialog() {
            this.showTopicDialogChecked = true;
        },
        showQuestionDialog() {
            this.showQuestionDialogChecked = true;
        },
        hideTopicDialog() {
            this.showTopicDialogChecked = false;
        },
        hideQuestionDialog() {
            this.showQuestionDialogChecked = false;
        },
        topicUpdate(item) {
            console.log(item);
        },
        topicDelete(item) {
            console.log(item);
        },
        questionUpdate(item) {
            console.log(item);
        },
        questionDelete(item) {
            console.log(item);
        },
    }
}
</script>
<style scoped>
.selection-wrapper-up {
    position: absolute;
    left: 0;
    top: 6vh;
    background-color: #f9f9f9;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 20px;
    max-height: 40vh;
    overflow-y: auto;
}

.selection-wrapper-down {
    position: absolute;
    left: 0;
    top: 50vh;
    background-color: #f9f9f9;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 20px;
    max-height: 40vh;
    overflow-y: auto;
}

.total-count {
    margin-left: 2vw;
}

table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}

th,
td {
    border: 1px solid #ccc;
    text-align: center;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    height: 4vh;

    align-items: center;
    justify-content: center;
}

th {
    background-color: #f2f2f2;
    text-align: center;
}

tbody tr:nth-child(odd) {
    background-color: #f9f9f9;
}

.full-text {
    border: none;
    height: 100%;
    width: 100%;
    transition: opacity 0.4s ease;
    background: #fff;
    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
    word-break: break-all;
    white-space: normal;
    overflow: auto;
}

.search-text {
    border: none;
    height: 4vh;
    width: 10vw;
    margin-left: 3vw;
    transition: opacity 0.4s ease;
    background: #fff;
    box-shadow: 2px 2px 5px rgba(0, 0, 0, 0.2);
    word-break: break-all;
    white-space: normal;
    overflow: auto;
}


.score-wrapper {
    display: flex;
    /* 使用Flexbox布局 */
    align-items: center;
    /* 垂直居中 */
}


.up-header {
    display: flex;
    align-items: center;
    justify-content: center;
}

.up-header select {
    height: 5vh;
    margin-left: 4vw;
}

.header-buttons {
    display: flex;
    justify-content: center;
    margin-bottom: 2vh;
}


.header-buttons button {
    width: 4vw;
    cursor: pointer;
    margin-left: 1vw;

    &:hover {
        background-color: #cbcaca;
    }
}


td button {
    width: 3.5vw;
    cursor: pointer;

    &:hover {
        background-color: #cbcaca;
    }
}

.topic-dialog {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border: 1px solid #ccc;
    background-color: #fff;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    z-index: 9;
    width: 40vw;
    height: 60vh;
    max-width: 100%;
    overflow: auto;
}

.topic-dialog .topic-dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
}

.topic-dialog .close {
    cursor: pointer;
    font-size: 1.2em;
    color: #888;
}



.question-dialog {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border: 1px solid #ccc;
    background-color: #fff;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    z-index: 9;
    width: 40vw;
    height: 60vh;
    max-width: 100%;
    overflow: auto;
}

.question-dialog .question-dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
}

.question-dialog .close {
    cursor: pointer;
    font-size: 1.2em;
    color: #888;
}

.dialog-btn {
    margin-top: 2vh;
    float: right;
}
</style>