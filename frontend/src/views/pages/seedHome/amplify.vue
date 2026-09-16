<template>
    <div class="nav-buttons">
        <button @click="disintegrate" title="解析当前卡片">裂解</button>
        <button @click="getAllCards" title="获得用户所有卡片">{{ allCardsChecked ? '未裂卡片' : '所有卡片' }}</button>
    </div>
    <div class="swiper-container" ref="swiperContainer">
        <div class="swiper-wrapper">
            <div class="swiper-slide" v-for="(item, index) in this.cardContents" :key="index"
                @click="handleCardClick(item)">
                <div class="card-box">
                    <img src="@/assets/img/seedwindow/ai.png" class="box-img">
                    <div class="box-content">
                        <p>{{ item.content }}</p>
                        <div class="details">
                            <div class="imgBx" v-if="item.seed === 1">
                                <img src="@/assets/img/seedwindow/topic.png" alt="">
                            </div>
                            <div class="imgBx" v-else>
                                <img src="@/assets/img/seedwindow/question.png" alt="">
                            </div>
                            <h3>{{ item.username }}<br /> <span>{{ item.datetime }}</span></h3>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <div class="selection-wrapper-down">
        <div class="header">
            <h2>裂解种子筛选</h2>
            <div class="total-count">(共 {{ totalSeedCount }} 条seed)</div>
        </div>
        <div class="header-buttons">
            <button @click="setAllLevel" title="全部设置为第一个种子的level">同层</button>
            <button @click="setAllScoreH" title="全部设置为第一个种子的scoreH">同分</button>
            <button @click="selectAllSeeds">{{ selectAll ? '全消' : '全选' }}</button>
            <button @click="addSeeds">入库</button>
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
                </tr>
            </thead>
            <tbody>
                <tr v-for="item in seed_data" :key="item.question">

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
                </tr>
            </tbody>
        </table>
    </div>
    <div class="card-dialog" v-if="isCardDialogVisible">
        <div class="card-dialog-header">
            <h2>{{ singleCardInfo.title }}</h2>
            <div class="close" @click="hideCardDialog">&times;</div>
        </div>
        <div class="card-dialog-body">
            <p>创建日期: {{ singleCardInfo.datetime }} </p>
            <p>所有者: {{ singleCardInfo.username }}</p>
            <p>{{ singleCardInfo.content }}</p>
        </div>
    </div>
</template>
<script>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import Swiper, { Navigation, Pagination } from 'swiper';

import { get_cards } from "@/api/card/get_card"
import { messageConfig } from 'element-plus';

import {
    seed_disintegrate, seed_addSeeds,
    seed_getAllCards, seed_getAllUnprocessedCards
} from "@/api/seed/amplify"


export default {
    name: "Amplify",
    mounted() {
        const swiperContainer = this.$refs.swiperContainer;
        this.swiper = new Swiper(swiperContainer, {
            effect: 'coverflow',
            grabCursor: true,
            centeredSlides: true,
            slidesPerView: 'auto',
            coverflowEffect: {
                rotate: 0,
                stretch: 0,
                depth: 100,
                modifier: 2,
                slideShadows: true,
            },
            loop: false,
        });

        this.getAllUnprocessedCards();
    },
    beforeDestroy() {
        if (this.swiper) {
            this.swiper.destroy();
        }
    },
    components: {
    },
    data() {
        return {
            allCardsChecked: false,
            seedMode: 0,          // 裂解之后更新，1是topic，2是topic-question
            cardContents: [
                {
                    'cid': '0',
                    'username': '提示',
                    'datetime': '2024-05-23 15:13',
                    'seed': 1,
                    'content': '您已经裂解了所有的卡片',
                    'score': '0'
                }, {
                    'cid': '2',
                    'username': '222',
                    'datetime': '222',
                    'seed': 2,
                    'content': '222',
                    'score': '222'
                }, {
                    'cid': '3',
                    'username': '333',
                    'datetime': '333',
                    'seed': 1,
                    'content': '333',
                    'score': '333'
                }, {
                    'cid': '4',
                    'username': '444',
                    'datetime': '444',
                    'seed': 2,
                    'content': '444',
                    'score': '444'
                }, {
                    'cid': '1',
                    'username': '111',
                    'datetime': '111',
                    'seed': 1,
                    'content': '111',
                    'score': '111'
                }, {
                    'cid': '2',
                    'username': '222',
                    'datetime': '222',
                    'seed': 2,
                    'content': '222',
                    'score': '222'
                }, {
                    'cid': '3',
                    'username': '333',
                    'datetime': '333',
                    'seed': 1,
                    'content': '333',
                    'score': '333'
                }, {
                    'cid': '4',
                    'username': '444',
                    'datetime': '444',
                    'seed': 2,
                    'content': '444',
                    'score': '444'
                }, {
                    'cid': '1',
                    'username': '111',
                    'datetime': '111',
                    'seed': 1,
                    'content': '111',
                    'score': '111'
                }, {
                    'cid': '2',
                    'username': '222',
                    'datetime': '222',
                    'seed': 2,
                    'content': '222',
                    'score': '222'
                }, {
                    'cid': '3',
                    'username': '333',
                    'datetime': '333',
                    'seed': 1,
                    'content': '333',
                    'score': '333'
                }, {
                    'cid': '4',
                    'username': '444',
                    'datetime': '444',
                    'seed': 2,
                    'content': '444',
                    'score': '444'
                }, {
                    'cid': '1',
                    'username': '111',
                    'datetime': '111',
                    'seed': 1,
                    'content': '111',
                    'score': '111'
                }, {
                    'cid': '2',
                    'username': '222',
                    'datetime': '222',
                    'seed': 2,
                    'content': '222',
                    'score': '222'
                }, {
                    'cid': '3',
                    'username': '333',
                    'datetime': '333',
                    'seed': 1,
                    'content': '333',
                    'score': '333'
                }, {
                    'cid': '4',
                    'username': '444',
                    'datetime': '444',
                    'seed': 2,
                    'content': '444',
                    'score': '444'
                }
            ],
            seed_data: [
                { level: 1, topic: "话题1", question: "问题1", answer: "回答1", score: "得分1", scoreH: "人工打分1", selected: false },
                { level: 2, topic: "话题2", question: "问题2", answer: "回答2", score: "得分2", scoreH: "人工打分2", selected: false },
                { level: 3, topic: "话题3", question: "问题3", answer: "回答3", score: "得分3", scoreH: "人工打分3", selected: false },
                { level: 4, topic: "话题4", question: "问题4", answer: "回答4", score: "得分4", scoreH: "人工打分4", selected: false },
                { level: 5, topic: "话题5", question: "问题5", answer: "回答5", score: "得分5", scoreH: "人工打分5", selected: false },
                { level: 6, topic: "话题6", question: "问题6", answer: "回答6", score: "得分6", scoreH: "人工打分6", selected: false },
                { level: 7, topic: "话题7", question: "问题7", answer: "回答7", score: "得分7", scoreH: "人工打分7", selected: false },
                // 更多数据...
            ],
            checkStates: {},  // 使用对象来存储每个 item 的 checked 状态
            selectAll: false,
            isCardDialogVisible: false,
            singleCardInfo: {
                'title': '标题',
                'username': 'admin',
                'datetime': '2024-05-23 15:13',
                'content': '您已经裂解了所有的卡片',
            },
        };
    },
    computed: {
        checkedData() {
            return this.seed_data.filter(item => item.selected === true);
        },
        totalSeedCount() {
            return this.seed_data.length;
        }
    },
    methods: {
        hideCardDialog() {
            this.isCardDialogVisible = false;
        },
        addSeeds() {
            if (this.seedMode === 1 || this.seedMode === 2) {
                let formData = new FormData();
                formData.append('username', localStorage.getItem('userId'));
                formData.append('seedMode', this.seedMode);
                formData.append('data', JSON.stringify(this.checkedData));
                seed_addSeeds(formData).then(data => {
                    console.log(data);
                }).catch(error => {
                    console.error("An error occurred:", error); // 错误处理
                })
            }
            else if (this.seedMode === 2) {

            }
            else {
                this.$message.error("请先裂解！");
            }
        },
        selectAllSeeds() {
            if (this.seed_data[0]) {
                if (!this.selectAll) {
                    this.seed_data.forEach(item => {
                        item.selected = true;
                    })
                    this.$message.success('已全部选中');
                    this.selectAll = !this.selectAll;
                }
                else {
                    this.seed_data.forEach(item => {
                        item.selected = false;
                    })
                    this.$message.success('已全部取消选中');
                    this.selectAll = !this.selectAll;
                }
            }
            else {
                this.$message.success('当前没有数据!');
            }
        },
        setAllScoreH() {
            if (this.seed_data[0]) {
                let scoreH = this.seed_data[0].scoreH
                this.seed_data.forEach(item => {
                    item.scoreH = scoreH;
                })
                this.$message.success('已全部更新为scoreH' + scoreH);
            }
            else {
                this.$message.success('当前没有数据!');
            }
        },
        setAllLevel() {
            if (this.seed_data[0]) {
                let level = this.seed_data[0].level
                this.seed_data.forEach(item => {
                    item.level = level;
                })
                this.$message.success('已全部更新为level' + level);
            }
            else {
                this.$message.success('当前没有数据!');
            }
        },
        disintegrate() {
            if (!this.$refs.swiperContainer.swiper) {
                this.$message.error('当前没有卡片!');
            }
            else {
                const activeIndex = this.$refs.swiperContainer.swiper.activeIndex;
                let item = this.cardContents[activeIndex];
                console.log(this.cardContents[activeIndex]);
                let cardString = JSON.stringify(item);
                let formData = new FormData();
                formData.append('username', localStorage.getItem('userId'));
                formData.append('card', cardString);

                // TODO：传item，更新seed_data
                seed_disintegrate(formData).then(data => {
                    let res_list = data['content'];
                    let seed = data['seed'];
                    if (seed === 1) {
                        // { level: 1, topic: "话题1", question: "问题1", answer: "回答1", score: "得分1", scoreH: "人工打分1", selected: false },
                        this.seed_data = res_list.map(item => ({
                            level: 1,
                            topic: item,
                            question: '',
                            answer: '',
                            score: 0,
                            scoreH: 0,
                            selected: false // 添加selected属性，并设置为false
                        }));
                        this.seedMode = 1;
                    }
                    else if (seed === 2) {
                        this.seed_data = res_list.map(item => ({
                            level: 1,
                            topic: item[0],
                            question: item[1],
                            answer: '',
                            score: 0,
                            scoreH: 0,
                            selected: false // 添加selected属性，并设置为false
                        }));
                        this.seedMode = 2
                    }
                    this.$message.success("裂解成功！")
                }).catch(error => {
                    console.error("An error occurred:", error); // 错误处理
                });
            }
        },
        handleCardClick(item) {
            this.isCardDialogVisible = true;
            this.singleCardInfo.title = item.username;
            this.singleCardInfo.username = localStorage.getItem('userId');
            this.singleCardInfo.content = item.content;
            this.singleCardInfo.datetime = new Date(item.datetime).toLocaleString();
        },
        getAllUnprocessedCards() {
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            seed_getAllUnprocessedCards(formData).then(data => {
                let content = data.content;
                // cid, content, datetime, history, model_id, score, seed, status, time_params, title, username
                this.cardContents = content;
                this.cardContents.forEach(item => {
                    item.username = item.seed === 1 ? '话题' : '问题';
                    item.datetime = new Date(item.datetime).toLocaleString();
                })
            }).catch(error => {
                console.error("An error occurred:", error); // 错误处理
            });
        },
        getAllCards() {
            if (this.allCardsChecked) {
                this.getAllUnprocessedCards();
            }
            else {
                let formData = new FormData();
                formData.append('username', localStorage.getItem('userId'));
                seed_getAllCards(formData).then(data => {
                    let content = data.content;
                    this.cardContents = content;
                    this.cardContents.forEach(item => {
                        item.username = item.seed === 1 ? '话题' : '问题';
                        item.datetime = new Date(item.datetime).toLocaleString();
                    })
                }).catch(error => {
                    console.error("An error occurred:", error); // 错误处理
                });
            }
            this.allCardsChecked = !this.allCardsChecked;
        }
    },
}
</script>
<style scoped>
/* 引入Swiper的样式文件 */
@import 'swiper/swiper-bundle.css';

* {
    padding: 0;
}

.swiper-container {
    width: 100%;
    height: 100%;
    overflow: hidden;
}

.swiper-wrapper {
    width: 100%;
    height: 100%;
    padding: 5vh 0;
}

.swiper-slide {
    background-position: center;
    background-size: cover;
    height: 50vh;
    width: 22vw;
    box-shadow: 0 15px 50px rgba(0, 0, 0, 0.2);
    filter: blur(1px);
    background: #c1c3c4;
    border-radius: 10px;
    transition: 0.5s ease;
}

/* 当前选中的图 */
.swiper-slide-active {
    filter: blur(0px);
    background: #fff;
    transform: scale(1.2);
    margin-left: 2.1vw;
    margin-right: 2.1vw;
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
}

.card-box {
    position: relative;
    width: 100%;
    height: 100%;
    color: #999;
}

.card-box .box-content {
    padding-top: 5vh;
    padding-left: 2vw;
    padding-right: 2vw;
}

.box-content p {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 10;
    /* 设置最大行数 */
    overflow: hidden;
}

.card-box .box-img {
    height: 24px;
    width: 24px;
    position: absolute;
    top: 16px;
    right: 16px;
    opacity: 0.5;
}

.card-box .details {
    display: flex;
    align-items: center;
    margin-top: 20px;

    position: absolute;
    bottom: 20px;
}

.card-box .details .imgBx {
    position: relative;
    width: 60px;
    height: 60px;
    border-radius: 50%;
    overflow: hidden;
    margin-left: 10px;
}

.card-box .details .imgBx img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.card-box .details h3 {
    font-size: 16px;
    font-weight: 400;
    letter-spacing: 1px;
    color: #2b2d2f;
    line-height: 1.1em;
}

.card-box .details h3 span {
    font-size: 12px;
    color: rgb(82, 79, 79);
}

.swiper-container-3d .swiper-slide-shadow-left,
.swiper-container-3d .swiper-slide-shadow-right {
    background-image: none;
}

.nav-buttons {
    position: absolute;
    top: 0;
    left: 22vw;
    width: 50vw;
    height: 6vh;
}

.nav-buttons button {
    border: none;
    background: none;
    width: 6vw;
    height: 5vh;
    background-color: #fff;
    font-family: Arial, Helvetica, sans-serif;
    transition: 0.5s ease;
    cursor: pointer;
    font-size: 20px;
    user-select: none;
    padding: 4px;
    border-left: 1px solid #000;

    &:hover {
        background-color: #e6e3e3;
        box-shadow: 0 1px 1px 0;
        transform: scale(1.1);
    }
}

.selection-wrapper-down {
    position: absolute;
    left: 0;
    top: 63vh;
    background-color: #f9f9f9;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 20px;
    max-height: 30vh;
    overflow-y: auto;
    z-index: 2000;

    transition: 0.5s ease;

    &:hover {
        top: 23vh;
        max-height: 70vh;
    }
}

.total-count {
    margin-left: 2vw;
}

.header {
    display: flex;
    align-items: center;
    justify-content: center;
}

table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
}

th,
td {
    border: 1px solid #ccc;
    text-align: left;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    height: 4vh;
}

th {
    background-color: #f2f2f2;
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



.score-wrapper {
    display: flex;
    /* 使用Flexbox布局 */
    align-items: center;
    /* 垂直居中 */
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



.card-dialog {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border: 1px solid #ccc;
    background-color: #fff;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
    z-index: 2000;
    width: 45vw;
    height: 60vh;
    max-width: 100%;

    overflow: scroll;
}


.card-dialog .card-dialog-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 15px;
}


.card-dialog h2 {
    margin: 0;
    font-size: 1.2em;
}

.card-dialog .close {
    cursor: pointer;
    font-size: 1.2em;
    color: #888;
}

.card-dialog .close:hover {
    color: #333;
}

.card-dialog .card-dialog-body {
    margin-top: 10px;
}

.card-dialog p {
    margin: 5px 0;
    white-space: pre-wrap;
}

.card-dialog pre {
    white-space: pre-wrap;
}

.card-merge-info {
    display: flex;
    align-items: center;
    margin-top: 10px;
    color: #333;
    font-size: 12px;
}

.card-merge-info .merge-info-text {
    margin-right: 5px;
    white-space: nowrap;
}

.card-down {
    width: 100%;
    height: 10%;
    float: bottom;
}

.editContentDialog {
    height: 100%;
    width: 100%;
}

.myinput textarea {
    resize: vertical;
    /* 允许垂直调整大小 */
    overflow: auto;
    /* 添加滚动条 */
    width: 100%;
    /* 设置宽度以适应其父元素 */
}
</style>