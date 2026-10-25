<template>
    <div>
        <div>
            <!-- 文本输入区域 -->
            <textarea id="textarea" style="height: 30vh; width: 80vw" placeholder="请输入您要合成的文本" :value="tts_text">
        </textarea>
        </div>
        <div>
            <!-- 控制面板 -->
            <div>语速([0-100])：<input id="speed" v-model="speed" value="50" /></div>
            <div>音量([0-100])：<input id="volume" v-model="volume" value="50" /></div>
            <div>音高([0-100])：<input id="pitch" v-model="pitch" value="50" /></div>
            <div>发音人：<input id="vcn" v-model="vcn" value="xiaoyan" /></div>
            <div>小语种(泰语)：<input id="tte" type="checkbox" v-model="tte" /></div>
            <div>注意：发音人与语种会关联，小语种需要开通指定发音人</div>
        </div>
        <div>
            <!-- 按钮控制区域 -->
            <button id="controll_tts" @click="synthesize">立即合成</button>
            <button id="download_pcm" @click="downloadPcm">下载pcm</button>
            <button id="download_wav" @click="downloadWav">下载wav</button>
        </div>

        <div id="result"></div>
    </div>
</template>
  
<script>
import { requestVoiceSession } from '@/api/voiceSession'

import AudioPlayer from '@/components/dist/index.umd.js';
import { Base64 } from 'js-base64';

export default {
    name: 'TextToSpeech',
    data() {
        return {
            voiceAppId: '',
            tts_text: '《春江花月夜》是唐代诗人张若虚创作的七言歌行。',
            tts_base64: '',
            speed: 50,
            volume: 50,
            pitch: 50,
            vcn: 'xiaoyan',
            tte: false,
            ttsWS: null,   // tts WebSocket
            audioPlayer: null,
            audioBuf: null,

            isPlaying: false, // 标记音频是否正在播放
            audioQueue: [], // 存储待播放的音频数据
            audioContext: null,
            source: null,
        };
    },
    mounted() {
        this.audioPlayer = new AudioPlayer();
        this.audioPlayer.onStop = (audioDatas) => {
            console.log(audioDatas);
        };
    },
    methods: {
        async getWebSocketUrl() {
            const session = await requestVoiceSession('tts')
            this.voiceAppId = session.app_id
            return session.url
        },
        encodeText(text, type) {
            if (type === "unicode") {
                let buf = new ArrayBuffer(text.length * 4);
                let bufView = new Uint16Array(buf);
                for (let i = 0, strlen = text.length; i < strlen; i++) {
                    bufView[i] = text.charCodeAt(i);
                }
                let binary = "";
                let bytes = new Uint8Array(buf);
                let len = bytes.byteLength;
                for (let i = 0; i < len; i++) {
                    binary += String.fromCharCode(bytes[i]);
                }
                return window.btoa(binary);
            } else {
                return Base64.encode(text);
            }
        },
        async connectWebSocket() {
            this.tts_base64 = '';
            let url;
            try { url = await this.getWebSocketUrl(); }
            catch (error) { this.$message.error(error.message || '语音连接失败'); return; }
            if ("WebSocket" in window) {
                this.ttsWS = new WebSocket(url);
            } else if ("MozWebSocket" in window) {
                this.ttsWS = new MozWebSocket(url);
            } else {
                alert("浏览器不支持WebSocket");
                return;
            }

            this.ttsWS.onopen = (e) => {
                this.audioPlayer.start({
                    autoPlay: true,
                    sampleRate: 16000,
                    resumePlayDuration: 1000
                });
                var text =
                    document.getElementById("textarea").value.trim() ||
                    "请输入您要合成的文本";
                var tte = this.tte ? "unicode" : "UTF8";
                var params = {
                    common: {
                        app_id: this.voiceAppId,
                    },
                    business: {
                        aue: "raw",
                        auf: "audio/L16;rate=16000",
                        vcn: this.vcn,
                        speed: this.speed,
                        volume: this.volume,
                        pitch: this.pitch,
                        bgs: 1,
                        tte,
                    },
                    data: {
                        status: 2,
                        text: this.encodeText(text, tte),
                    },
                };
                console.log(params);
                this.ttsWS.send(JSON.stringify(params));
            };
            this.ttsWS.onmessage = (e) => {
                let jsonData = JSON.parse(e.data);
                if (jsonData.code === 0 && jsonData.data.audio) {
                    // console.log('onmessage, jsonData.data:', jsonData.data);
                    this.handleAudioData(jsonData.data.audio);
                }
                else {
                    console.error(jsonData);
                    alert('error：合成失败')
                    return;
                }

                // this.tts_base64 += jsonData.data.audio;
                // this.audioPlayer.postMessage({
                //     type: "base64",
                //     data: jsonData.data.audio,
                //     isLastData: jsonData.data.status === 2,
                // });
                // if (jsonData.code === 0 && jsonData.data.status === 2) {
                //     this.ttsWS.close();
                // }
                // console.log(jsonData.data);

                // let audioBuf = []; // 存储音频数据片段的数组
                // let filePath = 'thisisawavfileok.wav'; // 音频文件的存储路径
                // audioBuf.push(jsonData.data.audio);
                // let audio = Buffer.from(jsonData.data.audio, 'base64');
                // fs.appendFile(filePath, audio, 'binary', err => {
                //     if (err) {
                //         console.error('Error appending audio to file:', err);
                //     } else {
                //         console.log('Audio appended successfully.');
                //     }
                // });

                // // 检查状态码，如果状态为2，则表示合成结束，关闭WebSocket连接
                // if (jsonData.code == 0 && jsonData.data.status == 2) {
                //     console.log('TTS synthesis completed. Closing WebSocket.');
                //     this.ttsWS.close(); // 确保this.ttsWS是一个有效的WebSock
                // }


            };
            this.ttsWS.onerror = (e) => {
                console.error(e);
            };
            this.ttsWS.onclose = (e) => {
                console.log(e);
                console.log('关闭tts WebSocket，下面是base64编码');
                console.log(this.tts_base64);
                // this.$emit('ttsBase64Changed', this.tts_base64);
            }
        },
        // 处理服务器返回的音频数据
        handleAudioData(audio_data) {
            console.log('handelAudioData, audio:', audio_data);
            // const audioData = atob(audio_data);
            // const buffer = new Uint8Array(audioData.length);
            // for (let i = 0; i < audioData.length; i++) {
            //     buffer[i] = audioData.charCodeAt(i);
            // }
            // this.audioBlob = new Blob([buffer], { type: 'audio/wav' });
            // this.audioUrl = URL.createObjectURL(this.audioBlob);


            const audioData = atob(audio_data);
            const buffer = new Uint8Array(audioData.length);
            for (let i = 0; i < audioData.length; i++) {
                buffer[i] = audioData.charCodeAt(i);
            }
            var audioBlob = new Blob([buffer], { type: 'audio/wav' });

            // 创建FileReader读取音频数据
            const reader = new FileReader();
            reader.onload = async () => {
                const arrayBuffer = reader.result;  // 读取的音频数据，作为arraybuffer
                console.log(arrayBuffer);
                const audioBuffer = await this.audioContext.decodeAudioData(arrayBuffer);
                this.audioQueue.push(audioBuffer);
                if (!this.isPlaying) {
                    this.playNextInQueue();
                }
            };
            reader.readAsArrayBuffer(audioBlob);
        },
        initAudioContext() {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
        },

        // 播放队列中的下一个音频
        playNextInQueue() {
            this.initAudioContext();
            if (this.audioQueue.length > 0) {
                this.isPlaying = true;
                const nextAudio = this.audioQueue.shift();
                const source = this.audioContext.createBufferSource();
                source.buffer = nextAudio;
                source.connect(this.audioContext.destination);
                source.onended = () => {
                    this.isPlaying = false;
                    this.playNextInQueue();
                };
                source.start();
            }
        },
        synthesize() {
            // this.initAudioContext();
            this.connectWebSocket();
        },
        downloadPcm() {
            const blob = this.audioPlayer.getAudioDataBlob("pcm")
            if (!blob) {
                return
            }
            let defaultName = new Date().getTime();
            let node = document.createElement("a");
            node.href = window.URL.createObjectURL(blob);
            node.download = `${defaultName}.pcm`;
            node.click();
            node.remove();
        },
        downloadWav() {
            const blob = this.audioPlayer.getAudioDataBlob("wav")
            console.log(blob);
            if (!blob) {
                return
            }
            console.log(blob);
            let defaultName = new Date().getTime();
            let node = document.createElement("a");
            node.href = window.URL.createObjectURL(blob);
            node.download = `${defaultName}.wav`;
            node.click();
            node.remove();
        },
        // 其他方法
    }
};
</script>
  
<style scoped>
/* 你的CSS样式 */
</style>