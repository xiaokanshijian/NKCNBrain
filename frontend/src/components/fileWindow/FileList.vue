<template>
    <div class="file-list-container">
        <div class="file-list">
            <div class="file-last-card" tabindex="0" @click="addfileclicked" @keyup.enter="addfileclicked">
                <i class="file-last-card-img"></i>
                <input type="file" id="docFile" @change="addfile" accept="application/*,text/*,audio/*" style="display: none;" />
            </div>
            
            <!-- <div class="file-card-notsplit" v-if="needWaitFile">
                <i class="file-manage"></i>
                <img :src="getWaitFileIcon(waitFileName)" alt=""/>
                <div class="word">
                    <span>{{ waitFileName }}</span>
                    <span>{{ formatBytes(waitFileSize) }}</span>
                </div>
                <div class="file-checkbox"></div>
            </div> -->

            <!-- 显示所有等待处理的文件 -->
            <template v-if="waitFileNames && waitFileNames.length > 0">
                <div class="file-card-notsplit" v-for="(fileName, index) in waitFileNames" :key="'wait-'+index">
                <i class="file-manage"></i>
                <img :src="getWaitFileIcon(fileName)" alt="待处理文件图标" />
                <div class="word">
                    <span>{{ fileName }}</span>
                    <span>{{ waitFileSizes[index] }}</span>
                </div>
                <div class="file-checkbox"></div>
                </div>
            </template>

            <div class="file-card" v-for="(item, index) in sortedFileList" :key="item.originalIndex">
                <FileCard :fileType="item.fileType" :file="item.file" :fileStatus="item.fileStatus" :split=item.split
                    :fileLeftSelect="item.leftSelect" :fileRightSelect="item.rightSelect"
                    :index="item.originalIndex" :checked="item.checked" @update:fileChecked="handleFileCheckedUpdate"
                    @update:fileSummary="handleFileSummaryUpdate" @update:fileLeftSelection="handleFileLeftSelectUpdate"
                    @update:fileRightSelection="handleFileRightSelectUpdate" :needWaitFile="needWaitFile" @reloadAutoCards="reloadAutoCards"
                    @startRecordWithTarget="startRecordWithTarget" @endRecordWithTarget="endRecordWithTarget"
                    :isRecording="isRecording" @delete-file="handleDeleteFile" :updateFileCardState="updateFileCardState"
                    @updateFileCardStateOver="updateFileCardStateOver"
                    :mainFourColor="item.mainFourColor" :secondaryFourColor="item.secondaryFourColor" :dmtLevel="item.dmtLevel"
                    :isHomeworkPdf="item.isHomeworkPdf" :homeworkSubject="item.homeworkSubject" :homeworkConfidence="item.homeworkConfidence"
                    @document-four-color-updated="handleDocumentFourColorUpdated"
                    @material-settings="$emit('material-settings', $event)"
                    @open-batch-sketch-r-dialog="$emit('open-batch-sketch-r-dialog')"></FileCard>
            </div>
        </div>
    </div>
</template>
<script>
import FileCard from "@/components/fileWindow/FileCard.vue"
import ChatWindow from "@/views/pages/chatHome/chatwindow.vue";

/** NK2026 梯子图场景：与后端 automation_nk2026.NK2026_SCENE_NAME 一致 */
const NK2026_LADDER_SCENE = "NK2026梯子图·群组公能教学指向批改";
const NK2026_THEME_WORDS = ["车联", "纸联", "体联"];
const NK2026_SCENE_BASE_DOCS = [
    "A0监控表.pdf",
    "课程设计中课设实验精进（相关文件的）必要补充说明.pdf",
    "NK2026嵌入式课程目标分解与实施框架(助教专用)-20260309.pdf",
    "真实目标.pdf",
    "嵌入式系统课设各主题助教&教师教研激荡.pdf",
];

import { get_files } from "@/api/card/get_card"
import { saveDeletedFiles, getDeletedFiles } from "@/api/card/delete_card"

export default {
    components: {
        FileCard,
        ChatWindow,
    },
    data() {
        return {
            fileNameList: [],
            leftSelectList: [],
            rightSelectList: [],
            fileList: [
                {
                    index: 0,
                    fileType: 1,
                    file: {
                        name: "1个word",
                        size: "12kb",
                    },
                    fileStatus: 0,
                    checked: false,
                    leftSelect: "1",
                    rightSelect: "3",
                    split: 0,
                }, {
                    index: 1,
                    fileType: 2,
                    file: {
                        name: "1个excel",
                        size: "15kb",
                    },
                    fileStatus: 0,
                    checked: false,
                    leftSelect: "1",
                    rightSelect: "3",
                    split: 1,
                }, {
                    index: 2,
                    fileType: 3,
                    file: {
                        name: "1个ppt",
                        size: "17kb",
                    },
                    fileStatus: 0,
                    checked: false,
                    leftSelect: "1",
                    rightSelect: "3",
                    split: 1,
                }, {
                    index: 3,
                    fileType: 4,
                    file: {
                        name: "1个pdf",
                        size: "122kb",
                    },
                    fileStatus: 0,
                    checked: false,
                    leftSelect: "1",
                    rightSelect: "3",
                    split: 1,
                }, {
                    index: 4,
                    fileType: 5,
                    file: {
                        name: "1个zip",
                        size: "3.5mb",
                    },
                    fileStatus: 0,
                    checked: false,
                    leftSelect: "1",
                    rightSelect: "3",
                    split: 1,
                }, {
                    index: 5,
                    fileType: 6,
                    file: {
                        name: "1个txt",
                        size: "3kb",
                    },
                    fileStatus: 0,
                    checked: false,
                    leftSelect: "1",
                    rightSelect: "3",
                    split: 1,
                }, {
                    index: 6,
                    fileType: 0,
                    file: {
                        name: "未知文件",
                    },
                    fileStatus: 0,
                    checked: false,
                    leftSelect: "1",
                    rightSelect: "3",
                    split: 1,
                },
            ],
            fileSummaryName: "",
            deletedFiles: [],
            updateFileCardState: false,
            /** NK2026：自动勾选 A/B 类文档的索引，取消梯子图触发文档时撤销 */
            nk2026AutoAbIndices: [],
        };
    },
    props: {
        needWaitFile: Number,
        waitFileNames: Array,
        waitFileSizes: Array,
        isRecording: Boolean,
        sceneName: { type: String, default: "" },
    },
    watch: {
        // async needWaitFile(newVal) {
        //     console.log("needWaitFile changed:", newVal);
        //     if (newVal < 1 || newVal > this.waitFileNames.length) {
        //         return;
        //     }
        //     let waitFileName = this.waitFileNames[newVal-1];
        //     console.log("waitFileName:", waitFileName);
        //     // 在处理文件列表之前先获取删除记录
        //     await this.getDeletedFilesFromServer();
        //     if(newVal) {
        //         // 检查是否在已删除列表中
        //         if (this.deletedFiles.includes(waitFileName)) {
        //             console.log("已删除文件列表:", this.deletedFiles);
        //             // 从删除列表中移除
        //             const index = this.deletedFiles.indexOf(waitFileName);
        //             if (index > -1) {
        //                 this.deletedFiles.splice(index, 1);       
        //                 // 更新后端的删除记录
        //                 this.saveDeletedFilesToServer();
        //             }
        //         }
        //     }
        // }
    },
    mounted() {
        this.getAllUserFiles();
        this.sendFileNameList();
    },
    computed: {
        reversedFileList() {
            return this.fileList; // 使用reverse()来反转
        },
        sortedFileList() {
            // 将文件分为普通文件和基础文件两类
            const normalFiles = [];
            const baseFiles = [];
            
            this.fileList.forEach((item, originalIndex) => {
                // 为每个项目添加原始索引
                const itemWithIndex = { ...item, originalIndex };
                
                if (item.isBaseFile) {
                    // 基础文件（isBaseFile为true的文件）
                    baseFiles.push(itemWithIndex);
                } else {
                    // 普通文件（isBaseFile为false的文件）
                    normalFiles.push(itemWithIndex);
                }
            });
            
            // 按上传时间倒序排序（最新的在上面）
            const sortByTime = (a, b) => {
                const timeA = a.fileTime || 0;
                const timeB = b.fileTime || 0;
                return timeB - timeA; // 倒序
            };
            
            // 各自内部按时间倒序排序
            normalFiles.sort(sortByTime);
            baseFiles.sort(sortByTime);

            console.log("[FileList]:", normalFiles, baseFiles)
            
            // 普通文件在上，基础文件在下
            return [...normalFiles, ...baseFiles];
        }
    },
    methods: {
        // 半自动化新增
        updateFileCardStateOver() {
            this.updateFileCardState = false
        },

        endRecordWithTarget() {
            this.$emit('endRecordWithTarget');
        },
        startRecordWithTarget(fileName) {
            this.$emit('startRecordWithTarget', fileName);
        },

        reloadAutoCards() {
            this.$emit('reloadAutoCards')
        },

        // 更新图片文档矢量库摘要文本时对应FileCard灰色禁用样式显示切换
        updateFileCardBanStyle(fileName, isProcessing) {
            // 查找对应的文件
            const fileIndex = this.fileList.findIndex(item => item.file.name === fileName);
            if (fileIndex !== -1) {
                // 更新文件的split状态（split决定了文件卡片的样式）
                // 创建一个新对象 updatedFile，它包含原对象的所有属性，但 split 属性被更新
                const updatedFile = { ...this.fileList[fileIndex], split: isProcessing ? 0 : 1 };
                this.fileList.splice(fileIndex, 1, updatedFile);
            }
        },

        addfileclicked(event) {
            // 阻止事件的默认行为和冒泡
            event.preventDefault();
            event.stopPropagation();

            // 通过id获取文件输入框，并触发点击事件
            document.getElementById('docFile').click();
        },
        addfile(event) {
            // 当文件选择框发生变化时，获取文件对象
            const file = event.target.files[0];
            if (file) {
                // 可以在这里进行文件的预处理，例如读取文件内容等
                const reader = new FileReader();

                reader.onload = (e) => {
                    // FileReader.onload 事件在文件读取完成后触发
                    const fileData = e.target.result.split(',')[1];; // 获取文件的数据，去除前缀
                    // 这里可以将文件数据发送到后端服务器
                    // 创建 FormData 对象用于上传文件
                    // form就是表单的形式，可以添加字段-值
                    let formData = new FormData();
                    formData.append('username', localStorage.getItem('userId'));
                    formData.append('model_id', '1001');
                    formData.append('filename', file.name);
                    formData.append('file', fileData); // 添加文件数据到 FormData
                    // 配置axios的baseURL
                    //axios.defaults.baseURL = 'http://127.0.0.1:8000'
                    // axios.defaults.withCredentials = false
                    chat_upload(formData).then(data => {
                        // router.push('/main')// 刷新当前页面
                        this.$emit('fileUploadLog', file.name)
                    });
                };
                reader.readAsDataURL(file); // 读取文件内容，以Base64编码的形式
            } else {
                console.log('未选择文件');
            }
        },
        sendFileNameList() {
            console.log(this.fileList);
            // 使用map函数遍历列表并取出file.name属性
            // this.fileNameList = this.fileList
            //     .filter(obj => obj.checked) // 首先过滤出checked为true的对象
            //     .map(obj => obj.file.name); // 然后映射出这些对象的name属性
            let fileNameList = [];
            let leftSelectList = [];
            let rightSelectList = [];
            this.fileList.forEach(fileObj => {
                if (fileObj.checked) {
                    fileNameList.push(fileObj.file.name);
                    leftSelectList.push(fileObj.leftSelect);
                    rightSelectList.push(fileObj.rightSelect);
                } else {

                }
            });
            this.$emit('FileNameListFromFileList', fileNameList, leftSelectList, rightSelectList);
            const imgExts = ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.gif']
            const seen = new Set()
            const importImagePool = []
            this.fileList.forEach(fileObj => {
                const name = fileObj?.file?.name
                if (!name) return
                const lower = name.toLowerCase()
                if (!imgExts.some(ext => lower.endsWith(ext))) return
                const key = lower.trim()
                if (seen.has(key)) return
                seen.add(key)
                importImagePool.push(name)
            })
            this.$emit('ImportImagePoolFromFileList', importImagePool)
        },
        formatBytes(bytes) {
            if (typeof bytes !== 'number' || bytes < 0) {
                return 'Invalid input';
            }

            const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
            let unitIndex = 0;

            // 计算单位索引和缩放因子
            const scale = Math.pow(1024, unitIndex + 1);
            if (bytes < scale) {
                unitIndex = 0; // 如果字节数小于1KB，则使用字节为单位
            } else {
                while (bytes >= scale) {
                    bytes /= 1024;
                    unitIndex++;
                    if (unitIndex === units.length) break; // 防止溢出
                }
            }

            // 格式化数字，保留整数部分
            const formattedNumber = Math.round(bytes * 100) / 100;
            console.log("文件大小：", formattedNumber)

            // 返回格式化的字符串
            return `${formattedNumber} ${units[unitIndex]}`;
        },
        getAllUserFiles(filename=null) {
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('sceneName', localStorage.getItem('sceneName'));
            // res是一个promise，需要进一步处理:let res = get_files(formData);
            // 使用.then()方法处理Promise
            get_files(formData).then(async data => {
                // 在处理文件列表之前先获取删除记录
                await this.getDeletedFilesFromServer();
                
                // 检查是否在已删除列表中
                if (filename && this.deletedFiles.includes(filename)) {
                    console.log("已删除文件列表:", this.deletedFiles);
                    // 从删除列表中移除
                    const index = this.deletedFiles.indexOf(filename);
                    if (index > -1) {
                        this.deletedFiles.splice(index, 1);       
                        // 更新后端的删除记录
                        this.saveDeletedFilesToServer();
                    }
                }

                let content = data.content;
                console.log('getAllUserFiles:', content);
                this.fileList = content.map(fileInfo => {
                    // 定义文件类型映射
                    const fileTypeMapping = {
                        'doc': 1,
                        'xls': 2,
                        'ppt': 3,
                        'pdf': 4,
                        'zip': 5,
                        'txt': 6,
                        'png': 7,
                        'jpg': 8,
                        'xlsx': 9,
                        'xls': 10,
                        'mp3': 11,
                        'wav': 11,
                        'ogg': 11,
                        'm4a': 11,
                        'aac': 11,
                        'flac': 11,
                        'webm': 11
                    };
                    // 确定文件类型
                    let extension = fileInfo[0].split('.').pop();
                    let fileType = fileTypeMapping[extension] || 0; // 默认为未知类型
                    // 创建file对象
                    const file = {
                        name: fileInfo[0],
                        size: this.formatBytes(fileInfo[1]),
                        suffix: extension,
                    };
                    
                    let theSplit = 1
                    if(extension == "xlsx" || extension == "xls")
                        theSplit = 1
                    else
                        theSplit = fileInfo[3]
                    // 创建最终对象并返回
                    return {
                        fileType: fileType,
                        file: file,
                        checked: fileInfo[2],
                        isBaseFile: fileInfo[2], // 初始化时根据checked状态确定isBaseFile，之后不再改变
                        leftSelect: "1",
                        rightSelect: "3",
                        split: theSplit,
                        fileTime: fileInfo[4] || 0, // 添加文件时间信息
                        fileStatus: 'normal',
                        mainFourColor: fileInfo[5] || '', // 🔥 四色主色
                        secondaryFourColor: fileInfo[6] || '', // 🔥 四色辅色
                        dmtLevel: fileInfo[7] || '', // 🔥 DMT层次
                        isHomeworkPdf: Boolean(fileInfo[8] || fileInfo[9]),
                        homeworkSubject: fileInfo[10] || 'unknown',
                        homeworkStage: fileInfo[11] || 'unknown',
                        homeworkConfidence: Number(fileInfo[12] || 0),
                        homeworkReason: fileInfo[13] || '',
                        homeworkCheckedAt: fileInfo[14] || ''
                    };
                })
                // 过滤掉已删除的文件
                .filter(file => !this.deletedFiles.includes(file.file.name));

                // // Test: getAllUserFiles文件加载后将写死等一秒钟检测状态，改为真正的同步
                // setTimeout(() => {
                //     this.updateFileCardState = true
                // }, 800);

                this.sendFileNameList();
            }).catch(error => {
                console.error("An error occurred:", error); // 错误处理
            });
        },
        handleFileCheckedUpdate(checked, index) {
            console.log(`id 为 ${index} 的子组件的checked已更新为 ${checked}`);
            // 根据ID更新对应的子组件状态
            this.fileList[index].checked = checked;
            const sn = this.sceneName || localStorage.getItem("sceneName") || "";
            if (this.nk2026SceneActive(sn)) {
                const item = this.fileList[index];
                if (checked && this.isNk2026LadderImageTrigger(item)) {
                    this.applyNk2026AutoSelection(index);
                } else if (!checked && this.isNk2026LadderImageTriggerName(item.file.name)) {
                    this.clearNk2026AutoAbSelection();
                }
            }
            this.sendFileNameList();
        },

        nk2026SceneActive(sn) {
            return sn && sn.includes(NK2026_LADDER_SCENE);
        },

        weekNumFromFileName(name) {
            const m = name.match(/W(\d+)/i);
            return m ? parseInt(m[1], 10) : null;
        },

        parseNk2026LadderMeta(filename) {
            const wm = filename.match(/W(\d+)/i);
            if (!wm) return null;
            const week = parseInt(wm[1], 10);
            let theme = null;
            for (const t of NK2026_THEME_WORDS) {
                if (filename.includes(t)) {
                    theme = t;
                    break;
                }
            }
            if (!theme || !filename.includes("梯子图填写")) return null;
            let groupNum = null;
            const tm = filename.match(
                new RegExp(`${theme}[IVⅠⅡⅢ二三四五六七八九十]*\\s*(\\d+)\\s*组`)
            );
            if (tm) groupNum = parseInt(tm[1], 10);
            else {
                const gm = filename.match(/G(\d+)/i);
                if (gm) groupNum = parseInt(gm[1], 10);
                else {
                    const gm2 = filename.match(/(\d+)\s*组/);
                    if (gm2) groupNum = parseInt(gm2[1], 10);
                }
            }
            if (groupNum == null) return null;
            return { week, theme, groupNum };
        },

        nk2026MatchesGroup(name, g) {
            const gs = String(g);
            const pad = gs.padStart(2, "0");
            const reG = new RegExp(`G(?:${gs}|${pad})(?!\\d)`, "i");
            if (reG.test(name)) return true;
            const reZh = new RegExp(`(?<!\\d)(?:${gs}|${pad})\\s*组`);
            return reZh.test(name);
        },

        /** B7：Wn 与梯子周次 ladderWeek 一致；主题、组号与梯子一致 */
        matchesNk2026BPlanningXmlLog(name, theme, groupNum, ladderWeek) {
            if (ladderWeek == null || ladderWeek === undefined) return false;
            if (!theme || !name.includes(theme)) return false;
            if (!this.nk2026MatchesGroup(name, groupNum)) return false;
            if (!name.includes("规划表") || !name.includes("代码修改") || !name.includes("8XML")) return false;
            if (!name.includes("日志记录") && !name.includes("日志")) return false;
            const ww = String(ladderWeek);
            const wpad = ww.padStart(2, "0");
            const reW = new RegExp(`W(?:${ww}|${wpad})(?!\\d)`, "i");
            return reW.test(name);
        },

        /** 文件名中所有 Wn 的 n 取最大值（B7 多份时去重；无 V 版本号） */
        maxWeekDigitsInFilename(name) {
            const ms = [...name.matchAll(/W(\d+)/gi)].map((m) => parseInt(m[1], 10));
            return ms.length ? Math.max(...ms) : -1;
        },

        isNk2026LadderImageTriggerName(filename) {
            if (!this.nk2026SceneActive(this.sceneName || localStorage.getItem("sceneName") || ""))
                return false;
            const ext = (filename.split(".").pop() || "").toLowerCase();
            if (!["png", "jpg", "jpeg"].includes(ext)) return false;
            return this.parseNk2026LadderMeta(filename) != null;
        },

        isNk2026LadderImageTrigger(item) {
            return this.isNk2026LadderImageTriggerName(item.file.name);
        },

        parseVxVersion(name) {
            const m = name.match(/V(\d+)\.(\d+)/i);
            if (!m) return null;
            return parseInt(m[1], 10) * 1000 + parseInt(m[2], 10);
        },

        clearNk2026AutoAbSelection() {
            for (const idx of this.nk2026AutoAbIndices) {
                if (this.fileList[idx]) this.fileList[idx].checked = false;
            }
            this.nk2026AutoAbIndices = [];
        },

        _nkCheckAb(index, left, right) {
            const item = this.fileList[index];
            if (!item) return;
            item.checked = true;
            item.leftSelect = String(left);
            item.rightSelect = String(right);
            if (!this.nk2026AutoAbIndices.includes(index))
                this.nk2026AutoAbIndices.push(index);
        },

        _nkCheckC(index) {
            const item = this.fileList[index];
            if (!item) return;
            item.checked = true;
            item.leftSelect = "1";
            item.rightSelect = "3";
        },

        ladderHalfMatchesMeta(name, meta, halfKeyword) {
            if (!name.includes(`W${meta.week}`) || !name.includes(meta.theme)) return false;
            if (!this.nk2026MatchesGroup(name, meta.groupNum)) return false;
            if (!name.includes("梯子图填写")) return false;
            return (
                name.includes("（" + halfKeyword + "）") || name.includes("(" + halfKeyword + ")")
            );
        },

        applyNk2026AutoSelection(triggerIndex) {
            this.clearNk2026AutoAbSelection();
            const meta = this.parseNk2026LadderMeta(this.fileList[triggerIndex].file.name);
            if (!meta) return;

            const triggerName = this.fileList[triggerIndex].file.name;
            let otherHalfKey = null;
            if (triggerName.includes("上半部分")) otherHalfKey = "下半部分";
            else if (triggerName.includes("下半部分")) otherHalfKey = "上半部分";

            if (otherHalfKey) {
                for (let i = 0; i < this.fileList.length; i++) {
                    if (i === triggerIndex) continue;
                    const n = this.fileList[i].file.name;
                    if (this.ladderHalfMatchesMeta(n, meta, otherHalfKey)) {
                        this._nkCheckAb(i, 0, 0);
                        break;
                    }
                }
            }
            this._nkCheckAb(triggerIndex, 0, 0);

            const w = meta.week;
            const th = meta.theme;
            const g = meta.groupNum;
            const weekIncentiveOk = (wn) =>
                wn !== null &&
                (wn === w || wn === w - 1 || wn === w - 2 || wn === w - 3);

            // B3 激励谈话实录：多份命中时只勾选「|Wn−w|」最小的一份（与后端 pick_best_incentive_file 一致：距离相同则取更大周次），获取全文
            const b3Candidates = [];
            for (let i = 0; i < this.fileList.length; i++) {
                const name = this.fileList[i].file.name;
                const wn = this.weekNumFromFileName(name);
                if (!weekIncentiveOk(wn)) continue;
                if (!name.includes(th) || !name.includes("激励小组谈话实录")) continue;
                if (!this.nk2026MatchesGroup(name, g)) continue;
                const dist = Math.abs(wn - w);
                b3Candidates.push({ i, wn, dist });
            }
            b3Candidates.sort((a, b) => (a.dist - b.dist) || (b.wn - a.wn));
            if (b3Candidates.length > 0) {
                this._nkCheckAb(b3Candidates[0].i, 0, 0);
            }

            for (let i = 0; i < this.fileList.length; i++) {
                const name = this.fileList[i].file.name;
                const wn = this.weekNumFromFileName(name);

                // B1 智能纪要：周教研
                if (name.includes("智能纪要") && name.includes("周教研") && wn === w) {
                    this._nkCheckAb(i, 1, 3);
                }
                // B2 精进种子…定版
                if (wn === w && name.includes(th) && name.includes("精进种子三线放空设计定版")) {
                    this._nkCheckAb(i, 0, 0);
                }
                // // B3 激励谈话实录：Wn 与梯子图周次一致或 n-1～n-3，且主题、组号一致 → 获取全文
                // if (
                //     weekIncentiveOk(wn) &&
                //     name.includes(th) &&
                //     name.includes("激励小组谈话实录") &&
                //     this.nk2026MatchesGroup(name, g)
                // ) {
                //     this._nkCheckAb(i, 0, 0);
                // }
                // B4 当周 TA 小结
                if (wn === w && name.includes("课设实验课后TA助教小结")) {
                    this._nkCheckAb(i, 0, 0);
                }
                // B5 梯子图周次减 1 的 TA 小结（如 W10→W9）
                if (wn === w - 1 && name.includes("课设实验课后TA助教小结")) {
                    this._nkCheckAb(i, 0, 0);
                }
            }

            // B7：Wn 与梯子周次 w 一致；多份时取文件名中周次数字最大（无 V），再比名字序
            const b7Candidates = [];
            for (let i = 0; i < this.fileList.length; i++) {
                const name = this.fileList[i].file.name;
                if (!this.matchesNk2026BPlanningXmlLog(name, th, g, w)) continue;
                b7Candidates.push({
                    i,
                    wmax: this.maxWeekDigitsInFilename(name),
                });
            }
            b7Candidates.sort(
                (a, b) =>
                    (b.wmax - a.wmax) ||
                    (this.fileList[a.i].file.name || "").localeCompare(this.fileList[b.i].file.name || "")
            );
            if (b7Candidates.length > 0) {
                this._nkCheckAb(b7Candidates[0].i, 1, 3);
            }

            // B6 除乘加：同主题，取版本最高的两个
            const sanfa = [];
            for (let i = 0; i < this.fileList.length; i++) {
                const name = this.fileList[i].file.name;
                if (!name.includes(th) || !name.includes("各组除乘加三法则分析填写")) continue;
                const vr = this.parseVxVersion(name);
                if (vr != null) sanfa.push({ i, vr });
            }
            sanfa.sort((a, b) => a.vr - b.vr);
            const top2 = sanfa.slice(-2);
            for (const { i } of top2) this._nkCheckAb(i, 1, 3);

            // C 预置基础文档
            for (let i = 0; i < this.fileList.length; i++) {
                const baseName = this.fileList[i].file.name;
                if (NK2026_SCENE_BASE_DOCS.includes(baseName)) this._nkCheckC(i);
            }
        },

        handleFileSummaryUpdate(filename) {
            // 根据lqc的想法，点其中一个卡片，应该把所有选中的卡片以及select信息全部传给后端
            let fileNameList = [];
            let leftSelectList = [];
            let rightSelectList = [];
            this.fileList.forEach(fileObj => {
                if (fileObj.checked) {
                    fileNameList.push(fileObj.file.name);
                    leftSelectList.push(fileObj.leftSelect);
                    rightSelectList.push(fileObj.rightSelect);
                } else {

                }
            });
            this.$emit('update:fileSummary', filename, fileNameList, leftSelectList, rightSelectList);
        },
        handleFileLeftSelectUpdate(index, leftSelect) {
            this.fileList[index].leftSelect = leftSelect;
            this.sendFileNameList();
            // this.$emit('update:fileLeftSelection', index, leftSelect);
        },
        handleFileRightSelectUpdate(index, rightSelect) {
            this.fileList[index].rightSelect = rightSelect;
            this.sendFileNameList();
            // this.$emit('update:fileRightSelection', index, rightSelect);
        },
        getWaitFileIcon(fileName) {
            if (!fileName) {
                return require('@/assets/img/fileImg/unknowfile.png'); // Default icon if no filename
            }
            const extension = fileName.split('.').pop().toLowerCase();
            switch (extension) {
                case 'pdf':
                    return require('@/assets/img/fileImg/pdf.png');
                case 'doc':
                case 'docx':
                    return require('@/assets/img/fileImg/word.png');
                case 'xls':
                case 'xlsx':
                    return require('@/assets/img/fileImg/excel.png');
                case 'ppt':
                case 'pptx':
                    return require('@/assets/img/fileImg/ppt.png');
                case 'zip':
                    return require('@/assets/img/fileImg/zpi.png');
                case 'txt':
                    return require('@/assets/img/fileImg/txt.png');
                case 'png':
                    return require('@/assets/img/fileImg/png.png');
                case 'jpg':
                case 'jpeg':
                    return require('@/assets/img/fileImg/jpg.png');
                case 'mp3':
                case 'wav':
                case 'ogg':
                case 'm4a':
                case 'aac':
                case 'flac':
                case 'webm':
                    return require('@/assets/img/fileImg/audio.png');
                // Add more cases for other file types as needed
                default:
                    return require('@/assets/img/fileImg/unknowfile.png'); // Icon for unknown types
            }
        },

        // 处理文件删除
        handleDeleteFile(index) {
            const fileName = this.fileList[index].file.name;
            // 从文件列表中移除文件
            this.fileList.splice(index, 1);
            // 添加到删除列表
            this.deletedFiles.push(fileName);
            
            // 保存到后端
            this.saveDeletedFilesToServer();
            
            this.$message.success('文件已删除');
            // 更新文件列表显示
            this.sendFileNameList();

            setTimeout(() => {
                this.$emit('delete-file');
            }, 300);
        },

        // 🔥 处理文档四色属性更新
        handleDocumentFourColorUpdated(updateData) {
            const { filename, main_four_color, secondary_four_color } = updateData;
            // 找到对应的文件项并更新四色属性
            const fileIndex = this.fileList.findIndex(item => item.file.name === filename);
            if (fileIndex !== -1) {
                // 直接修改对象属性（Vue会自动检测变化，因为fileList是响应式的）
                this.fileList[fileIndex].mainFourColor = main_four_color;
                this.fileList[fileIndex].secondaryFourColor = secondary_four_color;
            }
        },

        // 保存删除记录到服务器
        saveDeletedFilesToServer() {
            const data = {
                username: localStorage.getItem('userId'),
                sceneName: localStorage.getItem('sceneName'),
                deletedFiles: this.deletedFiles
            };
            
            saveDeletedFiles(data).catch(error => {
                console.error('保存删除记录失败:', error);
                this.$message.error('保存删除记录失败');
            });
        },

        // 从服务器获取删除记录
        async getDeletedFilesFromServer() {
            try {
                const params = {
                    username: localStorage.getItem('userId'),
                    sceneName: localStorage.getItem('sceneName')
                };
                
                const response = await getDeletedFiles(params);
                if (response.error_num === 0) {
                    this.deletedFiles = response.content;
                }
            } catch (error) {
                console.error('获取删除记录失败:', error);
                this.$message.error('获取删除记录失败');
            }
        },

        // 在组件创建时获取删除记录
        async created() {
            await this.getDeletedFilesFromServer();
        },
    },
};
</script>
<style scoped>
.file-list {
    width: 82%;
    height: 70vh;
    padding: 30px;
    overflow-y: auto;
}


.file-last-card {
    height: 85px;
    width: 100%;
    margin-top: 20px;
    border-radius: 10px;
    background-color: #d8e9fb;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    transition: background-color 0.5s;
    cursor: pointer;

    &:hover {
        background-color: rgb(234, 234, 234);
    }
}

.file-last-card-img {
    background-image: url("@/assets/img/filewindow/add.png");
    background-size: cover;
    background-position: center;
    height: 58%;
    width: 21%;
}

.file-last-card-text {
    position: absolute;
    top: 90%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: white;
    font-size: 16px;
    z-index: 2;

    font-weight: bold;
    line-height: normal;
    font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
    font-size: 16px;
    color: #010101;
}


::-webkit-scrollbar {
    width: 20px;
    height: 15px;
    background: rgb(255, 255, 255);
    border-radius: 10px;
}

::-webkit-scrollbar-thumb {
    background: #bec5ca;
    min-height: 50px;
    min-width: 50px;
    border-radius: 10px;
}



.file-card-notsplit {
  width: 100%;
  height: 85px;
  background-color: rgb(234, 234, 234);
  border-radius: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 6px;
  box-sizing: border-box;
  cursor: pointer;

  margin-top: 20px;
  transition: background-color 0.5s;
  pointer-events: none;

  &:hover {
    background-color: red;
  }

  img {
    width: 60px;
    height: 60px;
  }

  .word {
    width: 60%;
    margin-left: 10px;
    overflow: hidden;

    span {
      width: 90%;
      display: inline-block;
      color: #000000;
    }

    span:first-child {
      font-size: 14px;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    span:last-child {
      font-size: 12px;
      color: rgb(44, 44, 44);
    }
  }
}

.file-manage {
  position: relative;
  background-image: url('@/assets/img/filewindow/manage.png');
  background-size: contain;
  background-repeat: no-repeat;
  display: inline-block;
  width: 20px;
  height: 25px;

  left: 0px;
  top: 0px;
  display: flex;
}

.file-checkbox {
  cursor: pointer;
  width: 40px;
  /* 设置图片的宽度 */
  height: 40px;
  /* 设置图片的高度 */
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;
  background-image: url('@/assets/img/pin_grey.png');
}

</style>
