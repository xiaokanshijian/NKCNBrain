<template>
    <div class="container">
        <!-- <div v-if="showCtrlProcessWaveStatus"
            style="height:20vh;width:100%;box-sizing: border-box;display:inline-block;vertical-align:bottom"
            class="ctrlProcessWave"></div> -->
        <!-- 放一个 <audio ></audio> 播放器，标签名字大写，阻止uniapp里面乱编译 -->
        <AUDIO :class="isPlay ? 'visible' : 'hidden'" ref="LogAudioPlayer" style="width:100%"></AUDIO>
        <!-- <el-input :class="isShowBase64 ? 'visible' : 'hidden'" v-model="text" type="textarea" placeholder="语音Base64内容"
            rows="10" show-word-limit readonly /> -->
        <!-- <el-input:class="isShowIdentifyText ? 'asr-input-visible' : 'hidden'" v-model="identifyText"
            type="textarea" placeholder="语音识别内容" show-word-limit readonly /> -->
        <textarea :class="isShowIdentifyText ? 'asr-input-visible' : 'hidden'" v-model="identifyText" placeholder="语音识别内容">
    </textarea>
        <div class="buttonContainer">
            <!-- <el-button :class="isOpen ? 'hidden' : 'visible'" @click="openVoice" type="success" size="small">
                开始录制
            </el-button>
            <el-button :class="isOpen ? 'visible' : 'hidden'" @click="closeVoice" type="primary" size="small">
                关闭录制
            </el-button> -->
        </div>
    </div>
</template>

<script>
import 'recorder-core'
import 'recorder-core/src/engine/mp3.js'
import 'recorder-core/src/engine/mp3-engine.js'
// import 'recorder-core/recorder.mp3.min.js'
import 'recorder-core/src/extensions/waveview'
import CryptoJS from 'crypto-js'

const APPID = ''
const API_SECRET = ''
const API_KEY = ''

export default {
    props: {
        openStatus: {
            type: Boolean,
            default: false
        },
        playStatus: {
            type: Boolean,
            default: false
        },
        showCtrlProcessWaveStatus: {
            type: Boolean,
            default: false
        },
        showBase64Status: {
            type: Boolean,
            default: false
        },
        downStatus: {
            type: Boolean,
            default: false
        },
        identifyStatus: {
            type: Boolean,
            default: false
        },
        showIdentifyTextStatus: {
            type: Boolean,
            default: false
        },
    },
    mounted() {
        // if (this.$props.openStatus) {
        //     this.openVoice()
        // }
    },
    watch: {
        identifyText(newVal, oldVal) {
            // 当identifyText变化时，执行更新操作
            console.log(newVal);
            this.$emit('voiceRecognitionTextChanged', newVal);
        },
    },
    data() {
        return {
            isOpen: this.openStatus,
            isPlay: this.playStatus,
            isShowCtrlProcessWave: this.showCtrlProcessWaveStatus,
            isShowBase64: this.showBase64Status,
            isDown: this.downStatus,
            isIdentify: this.identifyStatus,
            isShowIdentifyText: this.showIdentifyTextStatus,

            audio: null, // 音频
            text: null, // 存放转换后的文本内容
            identifyText: "", // 存放转换后的文本内容

            audios: [],
            base64s: [],
            type: "mp3",
            bitRate: 16,
            sampleRate: 16000,

            duration: 0,
            durationTxt: "0",
            powerLevel: 0,

            logs: [],

            sendInterval: 300,//发送间隔时长(毫秒)，mp3 chunk数据会缓冲，当pcm的累积时长达到这个时长，就会传输发送。这个值在takeoffEncodeChunk实现下，使用0也不会有性能上的影响。
            realTimeSendTryTime: 0,
            realTimeSendTryNumber: null,
            realTimeSendTryBytesChunks: null,
            realTimeSendTryClearPrevBufferIdx: null,
            realTimeSendTryBuffers: null,
            transferUploadNumberMax: null

        }
    },
    methods: {
        openVoice: function () {
            var This = this;
            var rec = this.rec = Recorder({
                type: This.type
                , bitRate: +This.bitRate
                , sampleRate: +This.sampleRate
                , onProcess: function (buffers, powerLevel, duration, sampleRate, newBufferIdx, asyncEnd) {
                    This.realTimeOnProcessClear(buffers, powerLevel, duration, sampleRate, newBufferIdx, asyncEnd);//实时数据处理，清理内存

                    This.duration = duration;
                    This.durationTxt = This.formatMs(duration, 1);
                    This.powerLevel = powerLevel;

                    if (This.isShowCtrlProcessWave) This.wave.input(buffers[buffers.length - 1], powerLevel, sampleRate);
                }
                , takeoffEncodeChunk: function (chunkBytes) {
                    //大于等于120秒自动关闭(2分)
                    if (This.duration >= 1200000) {
                        This.closeVoice();
                    } else {
                        //接管实时转码，推入实时处理
                        This.realTimeSendTry(chunkBytes, false);
                    }
                }
            });
            rec.open(function () {
                This.reclog("已打开:" + This.type + " " + This.sampleRate + "hz " + This.bitRate + "kbps", 2);
                This.recStart()
                This.isOpen = true;

                if (This.isShowCtrlProcessWave) This.wave = Recorder.WaveView({ elem: ".ctrlProcessWave" });

                if (This.$refs && This.$refs.LogAudioPlayer) {
                    var audio = This.$refs.LogAudioPlayer;
                    audio.pause();
                    audio = null;
                    This.audio = audio;
                }
                This.text = null;
                This.identifyText = "";
                This.base64s = [];

            }, function (msg, isUserNotAllow) {
                This.reclog((isUserNotAllow ? "UserNotAllow，" : "") + "打开失败：" + msg, 1);
            });
        },
        recStart: function () {
            if (!this.rec || !Recorder.IsOpen()) {
                this.reclog("未打开录音", 1);
                this.isOpen = false;
                return;
            }
            this.rec.start();
            this.realTimeSendTryReset();

            var set = this.rec.set;
            // this.reclog("录制中：" + set.type + " " + set.sampleRate + "hz " + set.bitRate + "kbps");
        },
        closeVoice: function () {
            this.realTimeSendTry(null, true);
            this.rec.close();
            this.isOpen = false;
            this.$emit('voiceRecognitionTextChanged', this.identifyText);
            this.$emit('voiceRecognitionBreaked');
        },
        recLast: function () {
            if (!this.recLogLast) {
                this.reclog("请先录音，然后停止后再播放", 1);
                return;
            }
            if (this.isPlay) this.recplay(this.recLogLast.idx);
            if (this.isShowBase64) this.recdown64(this.recLogLast.idx);
            if (this.isDown) this.recdown(this.recLogLast.idx);
        },
        recplay: function (idx) {
            var This = this;
            var o = this.logs[this.logs.length - idx - 1];
            o.play = (o.play || 0) + 1;
            var logmsg = function (msg) {
                o.playMsg = '<span style="color:green">' + o.play + '</span> ' + This.getTime() + " " + msg;
            };
            logmsg("");

            var audio = this.$refs.LogAudioPlayer;
            audio.controls = true;
            if (!(audio.ended || audio.paused)) {
                audio.pause();
            }
            audio.onerror = function (e) {
                logmsg('<span style="color:red">播放失败[' + audio.error.code + ']' + audio.error.message + '</span>');
            };
            audio.src = (window.URL || webkitURL).createObjectURL(o.res.blob);
            audio.play();
            This.audio = audio;
        },
        recdown64: function (idx) {
            var This = this;
            var o = this.logs[this.logs.length - idx - 1];
            var reader = new FileReader();
            reader.readAsDataURL(o.res.blob);
            reader.onloadend = function () {
                var base64 = (/.+;\s*base64\s*,\s*(.+)$/i.exec(reader.result) || [])[1];
                This.text = base64;
            };
        },
        recdown: function (idx) {
            var This = this;
            var o = this.logs[this.logs.length - idx - 1];
            o.down = (o.down || 0) + 1;

            o = o.res;
            var name = "rec-" + o.duration + "ms-" + (o.rec.set.bitRate || "-") + "kbps-" + (o.rec.set.sampleRate || "-") + "hz." + (o.rec.set.type || (/\w+$/.exec(o.blob.type) || [])[0] || "unknown");
            var downA = document.createElement("A");
            downA.href = (window.URL || webkitURL).createObjectURL(o.blob);
            downA.download = name;
            downA.click();
        },
        formatMs: function (ms, all) {
            var ss = ms % 1000;
            ms = (ms - ss) / 1000;
            var s = ms % 60;
            ms = (ms - s) / 60;
            var m = ms % 60;
            ms = (ms - m) / 60;
            var h = ms;
            var t = (h ? h + ":" : "")
                + (all || h + m ? ("0" + m).substr(-2) + ":" : "")
                + (all || h + m + s ? ("0" + s).substr(-2) + "″" : "")
                + ("00" + ss).substr(-3);
            return t;
        },
        getTime: function () {
            var now = new Date();
            var t = ("0" + now.getHours()).substr(-2)
                + ":" + ("0" + now.getMinutes()).substr(-2)
                + ":" + ("0" + now.getSeconds()).substr(-2);
            return t;
        },
        reclog: function (msg, color, res) {
            var obj = {
                idx: this.logs.length
                , msg: msg
                , color: color
                , res: res

                , playMsg: ""
                , down: 0
                , down64Val: ""
            };
            if (res && res.blob) {
                this.recLogLast = obj;
            }
            this.logs.splice(0, 0, obj);
        },
        realTimeSendTryReset() {
            this.realTimeSendTryTime = 0;
        },
        realTimeOnProcessClear(buffers, powerLevel, duration, sampleRate, newBufferIdx, asyncEnd) {
            if (this.realTimeSendTryTime == 0) {
                this.realTimeSendTryTime = Date.now();
                this.realTimeSendTryNumber = 0;
                this.transferUploadNumberMax = 0;
                this.realTimeSendTryBytesChunks = [];
                this.realTimeSendTryClearPrevBufferIdx = 0;
                this.realTimeSendTryBuffers = [];
            }

            //清理PCM缓冲数据，最后完成录音时不能调用stop，因为数据已经被清掉了
            //这里进行了延迟操作（必须要的操作），只清理上次到现在的buffer
            for (var i = this.realTimeSendTryClearPrevBufferIdx; i < newBufferIdx; i++) {
                buffers[i] = null;
            }
            this.realTimeSendTryClearPrevBufferIdx = newBufferIdx;

            //备份一下方便后面生成wav
            for (var i = newBufferIdx; i < buffers.length; i++) {
                this.realTimeSendTryBuffers.push(buffers[i]);
            }
        },
        realTimeSendTry(chunkBytes, isClose) {
            if (chunkBytes) {//推入缓冲再说
                this.realTimeSendTryBytesChunks.push(chunkBytes);
            }

            var t1 = Date.now();
            if (!isClose && t1 - this.realTimeSendTryTime < this.sendInterval) {
                return;//控制缓冲达到指定间隔才进行传输
            }
            this.realTimeSendTryTime = t1;
            var number = ++this.realTimeSendTryNumber;


            //缓冲的chunk拼接成一个更长点的
            var len = 0;
            for (var i = 0; i < this.realTimeSendTryBytesChunks.length; i++) {
                len += this.realTimeSendTryBytesChunks[i].length;
            }
            var chunkData = new Uint8Array(len);
            for (var i = 0, idx = 0; i < this.realTimeSendTryBytesChunks.length; i++) {
                var chunk = this.realTimeSendTryBytesChunks[i];
                chunkData.set(chunk, idx);
                idx += chunk.length;
            }
            this.realTimeSendTryBytesChunks = [];

            //推入传输
            var blob = null, meta = {};
            if (chunkData.length > 0) {//不是空的
                blob = new Blob([chunkData], { type: "audio/" + this.type });
                meta = Recorder.mp3ReadMeta([chunkData.buffer], chunkData.length) || {};//读取出这个片段信息
            }
            this.transferUpload(number
                , blob
                , meta.duration || 0
                , {
                    set: {
                        type: this.type
                        , sampleRate: meta.sampleRate
                        , bitRate: meta.bitRate
                    }
                }
                , isClose
            );
            var recMock = Recorder({
                type: this.type
                , sampleRate: this.sampleRate
                , bitRate: this.bitRate
            });
            if (this.realTimeSendTryBuffers.length > 0) {
                var chunk = Recorder.SampleData(this.realTimeSendTryBuffers, this.sampleRate, this.sampleRate);
                recMock.mock(chunk.data, this.sampleRate);
                var This = this;
                recMock.stop(function (blob, duration) {
                    var item = {
                        blob: blob
                        , duration: duration
                        , durationTxt: This.formatMs(duration)
                        , rec: recMock
                    }
                    This.audios.push(item)
                });
            }
            this.realTimeSendTryBuffers = [];
        },
        transferUpload(number, blobOrNull, c, blobRec, isClose) {
            this.transferUploadNumberMax = Math.max(this.transferUploadNumberMax, number);
            if (blobOrNull) {
                var blob = blobOrNull;

                //*********发送：Base64文本发送***************
                var This = this;
                var reader = new FileReader();
                reader.readAsDataURL(blob);
                reader.onloadend = function () {
                    var base64 = (/.+;\s*base64\s*,\s*(.+)$/i.exec(reader.result) || [])[1];
                    This.base64s.push(base64)
                    This.connectWebSocket()
                };
            }
            if (isClose) {
                this.mergeAll();
            }
        },
        mergeAll() {
            var bitRate = this.bitRate
            var idx = -1 + 1, files = [];
            var This = this;
            var read = function () {
                var audios = This.audios;
                var audiosItem = audios[idx++];
                if (idx >= audios.length) {
                    if (!files.length) {
                        return;
                    };

                    var rec = audiosItem.rec;
                    This.mp3Merge(files, bitRate, function (fileBytes, duration) {
                        var blob = new Blob([fileBytes.buffer], { type: "audio/" + This.type })
                        This.reclog("已录制:", "", {
                            blob: blob
                            , duration: duration
                            , durationTxt: This.formatMs(duration)
                            , rec: rec
                        });
                        This.recLast();
                    });
                    This.audios = [];
                    return;
                };
                var reader = new FileReader();
                reader.onloadend = function () {
                    files.push(new Uint8Array(reader.result));
                    read();
                };
                // console.log("audiosItem.blob:", audiosItem.blob)
                reader.readAsArrayBuffer(audiosItem.blob);
            };
            read();
        },
        mp3Merge(fileBytesList, bitRate, True) {
            //计算所有文件总长度
            var size = 0;
            for (var i = 0; i < fileBytesList.length; i++) {
                size += fileBytesList[i].byteLength;
            };
            //全部直接拼接到一起
            var fileBytes = new Uint8Array(size);
            var pos = 0;
            for (var i = 0; i < fileBytesList.length; i++) {
                var bytes = fileBytesList[i];
                fileBytes.set(bytes, pos);
                pos += bytes.byteLength;
            };
            //计算合并后的总时长
            var duration = Math.round(size * 8 / bitRate);
            True(fileBytes, duration);
        },

        // 连接websocket
        connectWebSocket() {
            if (!this.isIdentify) return;
            // console.log("连接websocket")
            return this.getWebSocketUrl().then(url => {
                if (this.webSocket && this.webSocket.readyState === this.webSocket.OPEN) {
                    return
                } else {
                    if ('WebSocket' in window) {
                        // console.log("创建WebSocket")
                        this.webSocket = new WebSocket(url)
                    } else if ('MozWebSocket' in window) {
                        // console.log("MozWebSocket")
                        this.webSocket = new MozWebSocket(url)
                    } else {
                        return
                    }

                    this.webSocket.onopen = e => {
                        this.webSocketSend()
                    }
                    this.webSocket.onmessage = e => {
                        this.result(e.data)
                    }
                    this.webSocket.onerror = e => {
                    }
                    this.webSocket.onclose = e => {
                    }
                }
            })
        },
        getWebSocketUrl() {
            return new Promise((resolve) => {
                // 请求地址根据语种不同变化
                var url = 'wss://iat-api.xfyun.cn/v2/iat'
                var host = 'iat-api.xfyun.cn'
                var apiKey = API_KEY
                var apiSecret = API_SECRET
                var date = new Date().toGMTString()
                var algorithm = 'hmac-sha256'
                var headers = 'host date request-line'
                var signatureOrigin = `host: ${host}\ndate: ${date}\nGET /v2/iat HTTP/1.1`
                var signatureSha = CryptoJS.HmacSHA256(signatureOrigin, apiSecret)
                var signature = CryptoJS.enc.Base64.stringify(signatureSha)
                var authorizationOrigin = `api_key="${apiKey}", algorithm="${algorithm}", headers="${headers}", signature="${signature}"`
                var authorization = btoa(authorizationOrigin)
                url = `${url}?authorization=${authorization}&date=${date}&host=${host}`
                resolve(url)
            })
        },
        // 向webSocket发送数据
        webSocketSend() {
            // console.log("webSocketSend:", JSON.stringify(this.webSocket))
            if (this.webSocket.readyState !== this.webSocket.OPEN) {
                return
            }
            if (this.base64s.length == 0) return;
            this.identifyText = "";
            // MODIFIED: 注释了上一行
            var index = 0;
            var params
            params =
            {
                common: {
                    app_id: APPID,
                },
                business: {
                    language: 'zh_cn', //小语种可在控制台--语音听写（流式）--方言/语种处添加试用
                    domain: 'iat',
                    accent: 'mandarin', //中文方言可在控制台--语音听写（流式）--方言/语种处添加试用
                },
                data: {
                    status: 0,
                    format: 'audio/L16;rate=16000',
                    encoding: 'lame',
                    audio: this.base64s[index],
                },
            }
            // console.log("首帧", this.base64s.length, index);
            //xx console.log("首帧", JSON.stringify(params));
            this.webSocket.send(JSON.stringify(params))
            this.handlerInterval = setInterval(() => {
                // websocket未连接
                if (this.webSocket.readyState !== this.webSocket.OPEN) {
                    // console.log("websocket未连接:", this.base64s.length, index)
                    // MODIFIED下面两行
                    // this.closeVoice();
                    console.log('websocket中断时候的文本：', this.identifyText);
                    this.closeVoice();
                    clearInterval(this.handlerInterval);
                    return
                }
                if (this.base64s.length === index) {
                    params =
                    {
                        data: {
                            status: 2,
                            format: 'audio/L16;rate=16000',
                            encoding: 'lame',
                            audio: '',
                        },
                    }
                    // console.log("尾帧", this.base64s.length, index);
                    //xx console.log("尾帧", JSON.stringify(params));
                    this.webSocket.send(JSON.stringify(params));
                    clearInterval(this.handlerInterval);
                    return false;
                }
                // 中间帧
                index++
                params =
                {
                    data: {
                        status: 1,
                        format: 'audio/L16;rate=16000',
                        encoding: 'lame',
                        audio: this.base64s[index],
                    },
                }
                // console.log("中间帧", this.base64s.length, index);
                //xx console.log("中间帧",this.base64s.length,index, JSON.stringify(params));
                this.webSocket.send(JSON.stringify(params))
            }, 40)
        },
        result(resultData) {
            // console.log("resultData：", resultData)
            // 识别结束
            let jsonData = JSON.parse(resultData)
            if (jsonData.data && jsonData.data.result) {
                let data = jsonData.data.result
                let status = jsonData.data.status
                let str = ''
                let ws = data.ws
                for (let i = 0; i < ws.length; i++) {
                    str = str + ws[i].cw[0].w
                }
                // console.log("识别的结果为" + this.isOpen + "===>" + status + "：", str)
                if (status === 0) {
                    this.identifyText = str
                }// MODIFIED: 下面两个是+=，但是这样就重复了因为返回的是包含历史的
                if (status === 1) {
                    this.identifyText += str
                }
                if (status === 2) {
                    this.identifyText += str
                }
            }
            if (jsonData.code === 0 && jsonData.data.status === 2) {
                this.webSocket.close()
            }
            if (jsonData.code !== 0) {
                this.webSocket.close()

            }
        },
    }
}
</script>
<style lang="scss" scoped>
.container {
    width: 100%;
    height: 30vh;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;

    .buttonContainer {
        margin-top: 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
    }
}

/* 隐藏 */
.hidden {
    display: none;
}

/* 显示 */
.visible {
    display: block;
}

.asr-input-visible {
    white-space: pre-wrap;
    line-height: 1em;
    width: 80%;
    min-height: 15vh;
    max-height: 30vh;
    background-color: white;
    text-align: left;
    overflow-y: auto;
    resize: none;
    font-size: 2em;
    word-wrap: break-word;
    overflow-wrap: break-word;
    vertical-align: top;
    padding: 0.5em;
    box-shadow: 10px 10px 50px rgba(255, 255, 255, 0.3);
    transition: box-shadow 0.3s ease;

    &:hover {
        box-shadow: 15px 15px 50px rgba(255, 255, 255, 0.5);
    }
}
</style>

