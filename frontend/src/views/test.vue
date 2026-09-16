<template>
    <div class="test-container">
        <audio ref="audioPlayer2" controls></audio>
        <audio ref="audioPlayer" controls autoplay="true"></audio>
        <audio ref="ttsAudio" controls="controls" autobuffer="autobuffer">
            <source :src="audioSrc" />
        </audio>
        <div class="test-div">
            <button @click="playAudio">播放音频(科大讯飞)</button>
            <button @click="playVoice">播放语音(谷歌API)</button>
            <button @click="speak">语音播报(speak-tts)</button>
            <button @click="testBtn">语音播报(流式)</button>
            <p>当前播放的文本：{{ textToSpeak }}</p>
            <p v-if="isPlaying">正在播放...</p>
        </div>
        <div class="test-div">
            <button class="speech-btn" @click="startRecording" :disabled="isRecording">开始录制</button>
            <button class="speech-btn" @click="stopRecording" :disabled="!isRecording">结束录制</button>
            <p class="speech-text">这里显示文本：{{ response_text }}</p>
            <audio v-if="processedAudio" controls>
                <source :src="audioUrl" type="audio/mp3">
                您的浏览器不支持该音频格式。
            </audio>
            <audio ref="audioElement" controls style="display: none;"></audio>
        </div>
        <div class="test-div">
            <voice_tts @ttsBase64Changed="updateTtsBase64" />
        </div>
        <div class="test-div">
            <voice :identifyStatus="true" :showIdentifyTextStatus="true" />
        </div>
        <div class="test-div">
            <div ref="card">
                <el-row>
                    <el-col :span="24">
                        <el-card>
                            <div>
                                <h1>语音识别</h1>
                                <el-button @click="startRecognition">开始识别</el-button>
                                <el-button @click="stopRecognition">停止识别</el-button>
                                <p>识别过程：{{ asrresult }}
                                </p>
                                <p>识别结果：
                                    <textarea v-model="result" class="asrtext">等待结果</textarea>
                                </p>
                            </div>
                        </el-card>
                    </el-col>
                    <el-col :span="12">
                        <div class="grid-content bg-purple-light">

                        </div>
                    </el-col>
                </el-row>
            </div>
        </div>

    </div>
</template>
<script>
import voice from '@/components/xftest'
import voice_tts from '@/components/xftest2'
import { get, post } from '@/api';
import { test_upload_audio, test_get_speech_text } from '@/api/test'
import RecordRTC from 'recordrtc';
import Speech from 'speak-tts'
import { audio_stream } from "@/api/chat/send_message"

const synth = window.speechSynthesis;
const msg = new SpeechSynthesisUtterance();

export default {
    components: {
        voice,
        voice_tts,
    },
    data() {
        return {
            audioSrc: null,
            isPlaying: false,

            isRecording: false,
            mediaRecorder: null,
            audioChunks: [],
            processedAudio: null,
            audioUrl: '',
            chunks: [],
            response_text: '',

            asrresult: '',
            result: '',
            recognizer: '',
            lastResultTime: null, // 记录上一个结果的时间戳
            shortPauseThreshold: 1000, // 短停顿阈值，例如1秒
            longPauseThreshold: 2020,

            textToSpeak: '大语言模型，指使用大量文本数据训练的深度学习模型，可以生成自然语言文本或理解语言文本的含义',

            speech: null,

            isPlaying: false, // 标记音频是否正在播放
            audioQueue: [], // 存储待播放的音频数据
            audioContext: null,
            source: null,

            mediaSource: null,
            sourceBuffer: null,
            audioPlayer: null,

        }
    },
    mounted() {
        this.audioElement = this.$refs.audioElement;
        // this.initAudioMedia();

        if ('webkitSpeechRecognition' in window) {
            this.recognizer = new webkitSpeechRecognition();
            this.recognizer.continuous = true;
            this.recognizer.interimResults = true;
            this.recognizer.lang = 'zh-CN';

            this.recognizer.onresult = (event) => {
                // 中间有个小停顿1-2s,就会增加length,多发一个音就重新调用一次onresult
                // 如果说了一段，那么length是1，如果停顿了，下一次调用length会加1，但是i不会从0开始而是从1开始
                // 就是说，它的result会及时覆盖
                let result = '';
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    const transcript = event.results[i][0].transcript;
                    console.log(i, event.results.length, transcript);
                    result = transcript;
                    if (event.results[i].isFinal) {
                        this.result = this.result ? this.result + '。' + this.asrresult : this.asrresult; // 将最终结果添加到finalResult
                    }
                }
                this.asrresult = result;
            };
            this.recognizer.onend = () => {
            };
            this.recognizer.onerror = (event) => {
                console.log(event);
            };
        }
        else {
            alert('浏览器不支持语音识别！');
        }

        this.speechInit();
    },
    methods: {
        testBtn() {
            var base64str = 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQABAP///v8AAAIAAAABAAQAAgAAAP////8AAP//AAAAAAEAAAD9////AAD//wEA/////wAAAwAAAAAAAQACAAAAAAABAAAA/v/+////AAAAAP//AgAAAP//AAAAAP//AQD8//3////+//7///////7////8/wAA//8AAAEAAAABAAEAAAACAAEA//8DAAEAAgACAP//AAD+//v//v/8//7///8AAAAA//8AAP///v/9//z//P/9//7/AAAAAAAA/f/+//3/+P/7//z/+v/7//z///8EAAEAAAD9//3//v/7//3/AAD//wAAAwABAAAAAgABAAAABAACAP//AQACAAEAAQAEAAAAAAAAAAAA/v/7//r/+//+/wEAAQAAAAAA/f8AAAAAAQADAAAAAQADAAcAAwABAAAA/f8AAAAAAAABAAAAAQABAAAAAgADAAIAAAAAAPn//f8BAAEAAAD9//z//v8BAAIACQAEAAQABQADAAAAAAABAAIABAADAAAAAQACAAIAAwABAAAAAgABAAEAAQAAAAIA/////wEAAQD9//7/AQAAAAIABAABAAEAAAACAAMAAgACAP3//f/+////AAACAAAA/f/+////AAAAAP////8BAAAAAAACAAMAAQAAAAEA/v/+//7///8AAAEA/f/+/wEAAQABAAAA/v/9//z//f8EAAIA/v/+/wAA/////wMAAAD9//3/AQADAAEAAwAHAP7///8AAAIABgABAP//AQABAAAAAQAAAP7//P///wAA/v8BAAEA///+//3//v/+/wEA//8AAP//+//6/wMAAQAEAAUA//8BAP3/AgAEAAIAAAD9//7///8AAP////8BAP///v///wAAAAAAAAAAAgAAAAAAAAACAAIAAAAAAAAAAQACAAMAAgACAAAABAABAAAAAgD//wEA//8AAAAA/////wEAAQACAAAAAAAAAAMABAABAAMAAgABAAMAAQABAAAAAAACAAAAAAD//wEAAQAAAAIAAQABAAIAAgABAAEAAgABAAEAAwACAAEAAwABAAAA/////////f8BAP7///8AAAAA/f/+/wAA///+/////v/8//v//v////3////9//z//P/+//v//P//////+/////7/+P/8//v/+v////z/AAD+//7//v//////AAAAAAAAAgAAAAMAAgADAAEAAAACAAIAAAADAAIAAAABAAEAAwAEAAEAAQD//wAA/f8AAP//AAADAAAAAgD//wIAAwABAAMAAQD+/wEAAgAEAAIAAwABAAAAAAACAAEAAQACAAEAAgACAAMAAAACAAEA/////wAAAAAAAAAAAAAAAAEAAgAAAAAAAAAAAP//AQAAAAEAAAABAAEAAAAAAAEAAQAAAAIAAgADAAEAAQABAP//AAABAP7/AAD+//z////9//////8AAP7//v//////AAABAAEAAwAAAAAAAQAAAP///P8AAP///////wEA/v/+////AgAAAAEAAgAAAAEAAQACAAIAAwAAAAMAAwADAAMAAQABAAIAAQAAAAAAAQABAAAA//8AAP7//v8AAAAA/P8DAP7/+v///wAA/P8DAAAA+P8CAPz/AwD9/wAA/v/+/wAA/v8AAAMAAAD//wEA/f8FAP7/AAD///z/AAAAAAIA/////////v8BAAEAAgAGAP//AAABAAAAAgACAAMAAwD//wAAAQABAAIAAQAAAP7/AQABAAMAAQD9/////f/+//7//f/9//7//v/8/////v////3//P/9//3/AgD9//7////9//z/+v////7//v8AAP//AAD//wAAAAD///3//v/+/wAA/f///////P8AAPv/AgAAAP/////7//7///8AAAAAAwD//////f8AAP//AgD8//7////8/wQA+v8GAPn////4//7/AAD9/wAA/P8BAAAAAgABAAcAAQABAAAAAQD//wIAAQABAAMAAAD//wEA//8CAP3/AQD//wEA//8BAP3/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';
            this.playBase64Audio(base64str);
        },
        playBase64Audio(base64String) {
            // 移除base64字符串中可能存在的数据URI方案（如果有的话）
            const audioBase64 = base64String.replace(/^data:.*?;base64,/, "");
            const binaryString = atob(audioBase64);
            const len = binaryString.length;
            const bytes = new Uint8Array(len);
            for (let i = 0; i < len; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            const audioBlob = new Blob([bytes], { type: 'audio/pcm' }); // 根据音频格式设置正确的MIME类
            const audioUrl = URL.createObjectURL(audioBlob);

            this.audioElement.src = audioUrl;
            this.audioElement.play()
                .catch(error => {
                    console.error('Error playing audio:', error);
                    // 音频播放失败时的处理
                });

            // 可选：播放完成后释放内存
            this.audioElement.onended = () => {
                URL.revokeObjectURL(audioUrl);
            };
        },
        onSourceOpen() {
            this.sourceBuffer = this.mediaSource.addSourceBuffer('audio/webm; codecs="vorbis"');
            this.sourceBuffer.addEventListener('updateend', this.onUpdateEnd);

            const postData = {
                username: this.username
            };
            audio_stream(postData).then(response => {
                this.appendAudioData(response);
            }).catch(error => {
                console.error('Error fetching audio:', error);
            });
        },
        onMediaSourceError(e) {
            console.error('MediaSource error:', e);
        },
        onUpdateEnd() {
            if (this.sourceBuffer.updating) return;
            this.audioPlayer.play();
        },
        appendAudioData(audioData) {
            if (this.sourceBuffer.updating) {
                setTimeout(() => this.appendAudioData(audioData), 50);
                return;
            }

            const audioChunk = new Uint8Array(audioData);
            this.sourceBuffer.appendBuffer(audioChunk);
        },
        initAudioMedia() {
            this.mediaSource = new MediaSource();
            this.audioPlayer = this.$refs.audioPlayer;
            this.audioPlayer.src = URL.createObjectURL(this.mediaSource);

            this.mediaSource.addEventListener('sourceopen', this.onSourceOpen);
            this.mediaSource.addEventListener('error', this.onMediaSourceError);
        },
        createMediaSource(audioData) {
            const mediaSource = new MediaSource();
            const audioPlayer = this.$refs.audioPlayer;
            audioPlayer.src = URL.createObjectURL(mediaSource);

            mediaSource.addEventListener('sourceopen', () => {
                const sourceBuffer = mediaSource.addSourceBuffer('audio/wav');
                sourceBuffer.addEventListener('updateend', () => {
                    audioPlayer.play();
                });

                // 将音频数据添加到SourceBuffer
                sourceBuffer.appendBuffer(audioData);
            });

            mediaSource.addEventListener('error', (e) => {
                console.error('MediaSource error:', e);
            });
        },
        speechInit() {
            this.speech = new Speech();
            this.speech.setLanguage('zh-CN');
            this.speech.init({
                volume: 0.6, // 音量0-1
                lang: 'zh-CN', // 语言
                rate: 1, // 语速1正常语速，2倍语速就写2
                pitch: 1, // 音调
                voice: 'Microsoft Kangkang - Chinese (Simplified, PRC)',//支持Microsoft Huihui - Chinese (Simplified, PRC),Microsoft Kangkang - Chinese (Simplified, PRC),Microsoft Yaoyao - Chinese (Simplified, PRC)
                listeners: {
                    // 事件
                    onvoiceschanged: voices => {
                        // console.log('事件声音已更改', voices);
                    },
                },
            }).then(data => {
                console.log('语音已准备好，声音可用', data);
            }).catch(e => {
                console.error('初始化时发生错误 : ', e);
            });

        },

        speak() {
            this.speech.speak({
                text: "大语言模型，指使用大量文本数据训练的深度学习模型，可以生成自然语言文本或理解语言文本的含义",
                queue: false,

            }).then(() => {
                console.log("播报完成")
            })
        },
        startRecording() {
            navigator.mediaDevices.getUserMedia({ audio: true })
                .then(stream => {
                    // 创建 MediaRecorder 实例
                    this.mediaRecorder = new MediaRecorder(stream);
                    // 监听数据可用事件来收集音频块
                    this.mediaRecorder.ondataavailable = event => {
                        if (event.data.size > 0) {
                            this.chunks.push(event.data);
                        }
                    };
                    // 开始录音
                    this.mediaRecorder.start();
                });
            this.isRecording = true;
        },
        // 停止录音的方法
        stopRecording() {
            if (this.mediaRecorder) {
                this.mediaRecorder.stop(); // 停止录音
                // 等待录音停止后处理音频块
                this.mediaRecorder.onstop = () => {
                    // 将音频块合并为一个 Blob
                    const audioBlob = new Blob(this.chunks, { type: 'audio/mpeg' });
                    this.uploadAudio(audioBlob);
                    this.chunks = []; // 重置 chunks
                };
            }
            this.isRecording = false;
        },
        // 上传音频的方法
        uploadAudio(audioBlob) {
            const formData = new FormData();
            formData.append('username', 'admin');
            formData.append('audio_file', audioBlob, 'recording.mp3'); // 确保 Blob 被正确添加

            // test_upload_audio(formData).then(response => {

            // }).catch(error => {
            //     console.error('Error uploading audio.', error);
            // });
            fetch('http://192.0.2.1:80/api/upload_audio',
                {
                    method: 'POST',
                    body: formData,
                })
                .then(response => {
                    // 确保请求成功
                    if (response.ok) {
                        console.log('response ok，转换为blob');
                        // 将响应转换为blob
                        return response.blob();
                    }
                    throw new Error('Network response was not ok.');
                })
                .then(blob => {
                    // 处理blob，例如创建一个URL
                    const audioURL = URL.createObjectURL(blob);
                    // 假设你有一个audio元素在模板中
                    this.audioElement.src = audioURL;
                    // 显示文本
                    let text_formData = new FormData();
                    text_formData.append('username', 'admin');
                    test_get_speech_text(text_formData).then(response => {
                        this.response_text = response['response_text'];
                    });
                    // 播放音频
                    this.audioElement.play();
                })
                .catch(error => {
                    // 处理错误
                    console.error('There has been a problem with your fetch operation:', error);
                });
        },
        // 启动语音识别
        startRecognition() {
            if (this.recognizer) {
                // this.asrresult = '';
                this.recognizer.start();
                console.log('语音识别已启动');
            } else {
                alert('语音识别功能未初始化！');
            }
        },

        // 停止语音识别
        stopRecognition() {
            if (this.recognizer) {
                console.log(this.asrresult);
                this.result = '';
                this.asrresult = '';
                this.recognizer.stop();
                console.log('语音识别已停止');
            } else {
                alert('语音识别功能未初始化！');
            }
        },

        playAudio() {
            // 检查 audioSrc 是否已设置
            if (this.audioSrc) {
                this.$refs.ttsAudio.play()
                    .then(() => {
                        this.isPlaying = true;
                    })
                    .catch(error => {
                        console.error('播放音频时出错:', error);
                    });
            }
        },
        updateTtsBase64(base64Data) {
            this.setAudioSource(base64Data);
            this.playAudio();
        },
        // 这个方法用于设置 audio 源，假设 base64AudioData 是从后端获取的 base64 编码音频数据
        setAudioSource(base64AudioData) {
            const audioType = base64AudioData.startsWith('data:audio/mpeg;base64,') ? 'audio/mpeg' : 'audio/wav';
            const base64Data = base64AudioData.replace(/^data:.*?;base64,/, '');
            const binaryString = atob(base64Data);
            const arrayBuffer = new Uint8Array(binaryString.length).map((char, index) => binaryString.charCodeAt(index));

            const blob = new Blob([arrayBuffer], { type: audioType });
            this.audioSrc = URL.createObjectURL(blob);
        },
        async playVoice() {
            if ('speechSynthesis' in window) {
                const utterance = new SpeechSynthesisUtterance(this.textToSpeak);

                // 可选：设置语音参数，如音量、语速、音调等
                utterance.volume = 1;
                utterance.rate = 1.5;
                utterance.pitch = 0.5;

                try {
                    // 获取可用的语音列表
                    const voices = await speechSynthesis.getVoices();
                    // 可选：选择一个特定的语音
                    utterance.voice = voices.find((voice) => voice.name === 'Google 粤语（香港）') || voices[0];

                    // 开始语音合成
                    speechSynthesis.speak(utterance);
                } catch (error) {
                    console.error('语音合成失败:', error);
                }
            } else {
                console.log('当前浏览器不支持语音合成');
            }
        },
        fetchAudio() {
            const postData = {
                username: this.username
            };
            const audioElement = this.$refs.audioPlayer2;
            // audio_stream(postData)
            // .then(response => {
            //     // 气死了，这个东西调了3天，django返回streamresponse，此时的response就是array数组，是二进制的东西，这时候response.data是未定义的，所以转blob肯定失败播放不了，提示Failed to load because no supported source was found.根据网上的说明，这个提示就是说你的url不对，是空的，没有获取资源
            //     // 第二个问题是，必须传wav文件，pcm还是同样的提示，应该也是格式不对啥的，但我不管了，wav能跑
            //     // console.log('response', response);
            //     const audioBlob = new Blob([response], { type: 'audio/wav' });
            //     // console.log('audioBlob', audioBlob);
            //     const audioUrl = URL.createObjectURL(audioBlob);
            //     // console.log('audioUrl', audioUrl);
            //     this.$refs.audioPlayer.src = audioUrl;
            //     this.$refs.audioPlayer.play();
            // })
            // .catch(error => {
            //     console.error('Error fetching audio:', error);
            // });
            fetch('http://localhost:8000/api/audio_stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(postData)
            })
                .then(response => {
                    if (!response.body) {
                        throw new Error('Stream has no body');
                    }

                    const reader = response.body.getReader();
                    const streamToBlob = async (stream) => {
                        const chunks = [];

                        while (true) {
                            const { done, value } = await stream.read();
                            if (done) {
                                break;
                            }
                            chunks.push(value);
                        }

                        const blob = new Blob(chunks, { type: 'audio/wav' });
                        return blob;
                    };

                    // 转换ReadableStream为Blob
                    streamToBlob(reader)
                        .then(blob => {
                            // 创建ObjectURL
                            const audioUrl = URL.createObjectURL(blob);
                            // 设置audio元素的src属性并播放
                            audioElement.src = audioUrl;
                            audioElement.play().catch(error => {
                                console.error('Error playing audio:', error);
                            });
                        })
                        .catch(error => {
                            console.error('Error converting stream to blob:', error);
                        });
                })
                .catch(error => {
                    console.error('Error fetching audio stream:', error);
                });
        },
    },
    beforeDestroy() {
        if (this.mediaSource) {
            this.mediaSource.endOfStream();
        }
    }
};

</script>

<style scoped>
.test-container {
    padding: 0;
    margin: 0;
}

.test-div {
    width: 100%;
}

.speech-btn {
    font-size: 1em;
}

.speech-text {
    font-size: 1em;
}

.asrtext {
    width: 100%;
    min-height: 4em;
    font-size: 2em;
}
</style>