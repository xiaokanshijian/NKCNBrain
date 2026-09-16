<template>
    <div class="card-top-right2">
        <div class="card-top-right2-button" :class="{ 'checked': checked }" @click="onCheckboxChange"></div>
    </div>
    <div style="width: 100%; 
                height: 100%; 
                display: flex; /* 使用Flexbox布局 */
                justify-content: center; /* 水平居中子元素 */
                align-items: flex-end;" 
        id="spiderChart" v-show="!checked">
        <div class="bottom-nav-buttons">
            <el-button @click="handleClick('陈述型')" :class="{ 'is-active': paramsClass === '陈述型' }">陈述型</el-button>
            <el-button @click="handleClick('平衡型')" :class="{ 'is-active': paramsClass === '平衡型' }">平衡型</el-button>
            <el-button @click="handleClick('创造型')" :class="{ 'is-active': paramsClass === '创造型' }">创造型</el-button>
        </div>
    </div>
    <div style="width: 100%; 
                height: 100%; 
                display: flex; /* 使用Flexbox布局 */
                justify-content: center; /* 水平居中子元素 */
                align-items: flex-end;" 
        v-show="checked">
        <div class="think-mode">
            <div class="think-mode-title">思维模式选择</div>
            <div class="think-mode-item" v-for="(item, index) in this.modeList" :key="index"
                @click="thinkModeChange(index)">
                <span class="item-content"> 
                    {{ item }} 
                </span>
                <div class="spiderChartsModels">
                    <div :id="'spiderChartGPT4_' + index"></div>
                    <div :id="'spiderChartMixtral_' + index"></div>
                    <div :id="'spiderChartKimi_' + index"></div>
                    <div :id="'spiderChartLlama3_' + index"></div>
                    <div :id="'spiderChartClaude_' + index"></div>
                    <div :id="'spiderChartDeepseek_' + index"></div>
                </div>
            </div>
        </div>
    </div>
</template>

<script>
// import * as echarts from 'echarts';
//import * as d3 from 'd3';
import "./d3.min.js";
import { SpiderChart } from "@/api/navigator/spiderChart";
import { SpiderChartCard } from "@/api/navigator/spiderChartCard";
import { get_usp, set_usp } from "@/api/navigator/get_set_usp";
import { chat_sendParams } from "@/api/chat/send_message"
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog } from 'element-plus'

export default {
    name: 'radar-chart2',
    components: {
        ElButton,
    },
    data() {
        return {
            checked: false,
            modeList: ['弹孔思维（适合需要逆向思维的场景）', '您的思维模式偏好'],
            // changeChartGPT4/XXX时，用于判定是模型更换导致需要执行此函数（保留显示上次通过 选思维模式/点按钮/拖拽 调好的超参），
            // 还是点击类型按钮需要执行此函数（显示对应类型超参）
            changeChartIsButton: false,
            // 仅陈述、平衡、创造三种类型
            params: {
                GPT4: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048,
                    n: 1
                },
                Mixtral: {
                    temperature: 0.1,
                    top_p: 0.95,
                    top_k: 15,
                    max_length: 2048,
                    do_sample: 1,
                    num_beams: 1,
                    num_beam_groups: 1,
                    num_return_sequences: 1,
                    repetition_penalty: 0.5,
                    max_new_tokens: 2048,
                    diversity_penalty: 1.1,
                    length_penalty: 0
                },
                Kimi: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048,
                    n: 1
                },
                llama3: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048
                },
                Claude: {
                    temperature: 0.7,
                    top_p: 0.95,
                    top_k: 30,
                    max_tokens: 2048
                },
                Deepseek: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048
                }
            },
            // 除以上三种类型外，拖动的参数也保存在这里（完整更新后的）
            paramsUpdate: {
                GPT4: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048,
                    n: 1
                },
                Mixtral: {
                    temperature: 0.7,
                    top_p: 0.95,
                    top_k: 30,
                    max_length: 2048,
                    do_sample: 1,
                    num_beams: 1,
                    num_beam_groups: 1,
                    num_return_sequences: 1,
                    repetition_penalty: 1.5,
                    max_new_tokens: 2048,
                    diversity_penalty: 1.1,
                    length_penalty: 0
                },
                Kimi: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048,
                    n: 1
                },
                llama3: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048
                },
                Claude: {
                    temperature: 0.7,
                    top_p: 0.95,
                    top_k: 30,
                    max_tokens: 2048
                },
                Deepseek: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048
                }
            },
            // 弹孔思维: 多样性（发散）、重复性（改变）、长短（居中）、大局观（全局.全面）
            danKongModeParams: {
                GPT4: {
                    temperature: 1.4,
                    top_p: 0.95,
                    frequency_penalty: 2.0,
                    presence_penalty: 2.0,
                    max_tokens: 2048,
                    n: 1
                },
                Mixtral: {
                    temperature: 1.4,
                    top_p: 0.95,
                    top_k: 50,
                    max_length: 2048,
                    do_sample: 1,
                    num_beams: 6,
                    num_beam_groups: 3,
                    num_return_sequences: 1,
                    repetition_penalty: 3,
                    max_new_tokens: 2048,
                    diversity_penalty: 1.5,
                    length_penalty: 1.0
                },
                Kimi: {
                    temperature: 0.8,
                    top_p: 0.95,
                    frequency_penalty: 2.0,
                    presence_penalty: 2.0,
                    max_tokens: 2048,
                    n: 1
                },
                llama3: {
                    temperature: 0.8,
                    top_p: 0.95,
                    frequency_penalty: 2.0,
                    presence_penalty: 2.0,
                    max_tokens: 2048
                },
                Claude: {
                    temperature: 0.8,
                    top_p: 0.95,
                    top_k: 50,
                    max_tokens: 2048
                },
                Deepseek: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048
                }
            },
            // 用户偏好思维
            userModeParams: {
                GPT4: {
                    temperature: 1.0,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 0.8,
                    max_tokens: 1024,
                    n: 1
                },
                Mixtral: {
                    temperature: 1.0,
                    top_p: 0.95,
                    top_k: 30,
                    max_length: 1024,
                    do_sample: 1,
                    num_beams: 2,
                    num_beam_groups: 2,
                    num_return_sequences: 1,
                    repetition_penalty: 1.5,
                    max_new_tokens: 1024,
                    diversity_penalty: 1.1,
                    length_penalty: 0.5
                },
                Kimi: {
                    temperature: 0.5,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 0.7,
                    max_tokens: 1024,
                    n: 1
                },
                llama3: {
                    temperature: 0.5,
                    top_p: 0.95,
                    frequency_penalty: 0.9,
                    presence_penalty: 0.8,
                    max_tokens: 1024
                },
                Claude: {
                    temperature: 0.5,
                    top_p: 0.95,
                    top_k: 30,
                    max_tokens: 1024
                },
                Deepseek: {
                    temperature: 0.7,
                    top_p: 0.95,
                    frequency_penalty: 1.0,
                    presence_penalty: 1.0,
                    max_tokens: 2048
                }
            },
            paramsClass: '陈述型',
        };
    },
    props: {
        configModel: String,
        clickClass: String,
        creativitySatisfaction: Number,
        repetitionSatisfaction: Number,
        comprehensivenessSatisfaction: Number,
        feedBack: Boolean
    },
    mounted() {
        // javaScript脚本函数，测试用，用于查看Mixtral多参数下的可能创造度score得分情况
        console.log("所有可能得分：", this.generateAllScores());

        // 思维模式预设4模型雷达图显示
        this.fixedChartGPT4(0);
        this.fixedChartMixtral(0);
        this.fixedChartKimi(0);
        this.fixedChartLlama3(0);
        this.fixedChartClaude(0);
        this.fixedChartDeepseek(0);

        // 读取用户在场景下的常用超参
        let getParamFormData = new FormData();
        getParamFormData.append('username', localStorage.getItem('realName'));
        getParamFormData.append('sname', localStorage.getItem('sceneName'));
        get_usp(getParamFormData).then(response => {
            if (response.error_num === 0) {
                let usparams = response.usparams
                console.log("您当前场景的常用超参是：", usparams);
                Object.keys(usparams).forEach(model => {
                    Object.keys(usparams[model]).forEach(key => {
                        this.userModeParams[model][key] = usparams[model][key];
                        this.paramsUpdate[model][key] = usparams[model][key];
                    });
                });
                // 用户在场景下的常用超参（思维模式）显示
                this.fixedChartGPT4(1);
                this.fixedChartMixtral(1);
                this.fixedChartKimi(1);
                this.fixedChartLlama3(1);
                this.fixedChartClaude(1);
                this.fixedChartDeepseek(1);

                if(this.configModel === 'GPT4')
                    this.initChartGPT4();
                else if(this.configModel === 'Mixtral')
                    this.initChartMixtral();
                else if(this.configModel === 'Kimi')
                    this.initChartKimi();
                else if(this.configModel === 'llama3')
                    this.initChartLlama3();
                else if(this.configModel === 'Deepseek')
                    this.initChartDeepseek();
                else
                    this.initChartClaude();

                // 加载时开始监听拖动事件，修改params
                this.$nextTick(() => {
                    document.querySelector("#spiderChart").addEventListener('updateValue', this.handleEvent);
                });

                this.$message.success('您在此场景的常用思维模式加载成功');
            } else {
                this.$message.error('您在此场景的常用思维模式加载失败')
            }
        });
    },
    watch: {
        params: {
            handler(newVal, oldVal) {
                // 这里的代码将在 params 对象内部的任何属性变化时被调用
                if(this.configModel === 'GPT4')
                    this.changeChartGPT4();
                else if(this.configModel === 'Mixtral')
                    this.changeChartMixtral();
                else if(this.configModel === 'Kimi')
                    this.changeChartKimi();
                else if(this.configModel === 'llama3')
                    this.changeChartLlama3();
                else if(this.configModel === 'Deepseek')
                    this.changeChartDeepseek();
                else
                    this.changeChartClaude();
            },
            deep: true,  // 设置 deep 为 true 来启用深度监听
            // immediate: true  // 如果想在挂载时立即触发
        },
        paramsUpdate: {
            handler(newVal, oldVal) {
                // 包括点击按钮更改参数、手动拖拽更改参数、点选思维模式，均将更新的参数值返回父组件
                this.$emit('paramsUpdate', newVal);
            },
            deep: true,  // Object设置深度监听
        },
        configModel(newVal, oldVal) {
            if(newVal === 'GPT4') {
                // 仅更新显示数据
                this.changeChartGPT4();
                // 真实更新前端params数据
                // this.handleClick(this.paramsClass);
            }
            if(newVal === 'Mixtral') {
                this.changeChartMixtral();
                // this.handleClick(this.paramsClass);
            }
            if(newVal === 'Kimi') {
                this.changeChartKimi();
                // this.handleClick(this.paramsClass);
            }
            if(newVal === 'llama3') {
                this.changeChartLlama3();
                // this.handleClick(this.paramsClass);
            }
            if(newVal === 'Claude') {
                this.changeChartClaude();
                // this.handleClick(this.paramsClass);
            }
            if(newVal === 'Deepseek') {
                this.changeChartDeepseek();
                // this.handleClick(this.paramsClass);
            }
        },
        clickClass(newVal, oldVal) {
            console.log("对话界面点击class改变: ", newVal);
            this.handleClick(newVal);
        },
        feedBack(newVal, oldVal) {
            if(newVal === true) {
                this.updateUserModeParams()
                this.$emit('feedBackOK')
            }
        },
    },
    methods: {
        updateUserModeParams() {
            let num_beams_tmp=this.userModeParams.Mixtral.num_beams
            let num_beam_groups_tmp=this.userModeParams.Mixtral.num_beam_groups
            // 遍历userModeParams中的每个模型
            for (const modelName in this.userModeParams) {
                if (this.userModeParams.hasOwnProperty(modelName)) {
                    // 确保paramsUpdate中也有这个模型
                    if (this.paramsUpdate.hasOwnProperty(modelName)) {
                        // 遍历模型中的每个参数
                        for (const paramName in this.userModeParams[modelName]) {
                            if (this.userModeParams[modelName].hasOwnProperty(paramName)) {
                                const updatedValue = 0.7 * this.paramsUpdate[modelName][paramName] +
                                                    0.3 * this.userModeParams[modelName][paramName];
                                if(paramName === 'max_tokens' || paramName === 'n' || paramName === 'top_k' || paramName === 'max_length' || paramName === 'num_beams' || paramName === 'num_beam_groups' || paramName === 'max_new_tokens') {
                                    this.userModeParams[modelName][paramName] = Number(updatedValue.toFixed(0));
                                } else {
                                    this.userModeParams[modelName][paramName] = Number(updatedValue.toFixed(2));
                                }
                            }
                        }
                    }
                }
            }
            if(this.creativitySatisfaction != null && this.creativitySatisfaction <= 3) {
                this.userModeParams.GPT4.temperature = Number((this.userModeParams.GPT4.temperature + (2-this.userModeParams.GPT4.temperature)*0.2*(4-this.creativitySatisfaction)/3).toFixed(2))
                this.userModeParams.Mixtral.temperature = Number((this.userModeParams.Mixtral.temperature + (2-this.userModeParams.Mixtral.temperature)*0.2*(4-this.creativitySatisfaction)/3).toFixed(2))
                this.userModeParams.Kimi.temperature = Number((this.userModeParams.Kimi.temperature + (1-this.userModeParams.Kimi.temperature)*0.2*(4-this.creativitySatisfaction)/3).toFixed(2))
                this.userModeParams.llama3.temperature = Number((this.userModeParams.llama3.temperature + (1-this.userModeParams.llama3.temperature)*0.2*(4-this.creativitySatisfaction)/3).toFixed(2))
                this.userModeParams.Claude.temperature = Number((this.userModeParams.Claude.temperature + (1-this.userModeParams.Claude.temperature)*0.2*(4-this.creativitySatisfaction)/3).toFixed(2))
                this.userModeParams.Deepseek.temperature = Number((this.userModeParams.Deepseek.temperature + (1-this.userModeParams.Deepseek.temperature)*0.2*(4-this.creativitySatisfaction)/3).toFixed(2))
            }
            if(this.repetitionSatisfaction != null && this.repetitionSatisfaction <= 3) {
                this.userModeParams.GPT4.frequency_penalty = Number((this.userModeParams.GPT4.frequency_penalty + (2-this.userModeParams.GPT4.frequency_penalty)*0.2*(4-this.repetitionSatisfaction)/3).toFixed(2))
                this.userModeParams.Mixtral.repetition_penalty = Number((this.userModeParams.Mixtral.repetition_penalty + (2-this.userModeParams.Mixtral.repetition_penalty)*0.2*(4-this.repetitionSatisfaction)/3).toFixed(2))
                this.userModeParams.Kimi.frequency_penalty = Number((this.userModeParams.Kimi.frequency_penalty + (2-this.userModeParams.Kimi.frequency_penalty)*0.2*(4-this.repetitionSatisfaction)/3).toFixed(2))
                this.userModeParams.llama3.frequency_penalty = Number((this.userModeParams.llama3.frequency_penalty + (2-this.userModeParams.llama3.frequency_penalty)*0.2*(4-this.repetitionSatisfaction)/3).toFixed(2))
                this.userModeParams.Claude.frequency_penalty = Number((this.userModeParams.Claude.frequency_penalty + (2-this.userModeParams.Claude.frequency_penalty)*0.2*(4-this.repetitionSatisfaction)/3).toFixed(2))
                this.userModeParams.Deepseek.frequency_penalty = Number((this.userModeParams.Deepseek.frequency_penalty + (2-this.userModeParams.Deepseek.frequency_penalty)*0.2*(4-this.repetitionSatisfaction)/3).toFixed(2))
            }
            if(this.comprehensivenessSatisfaction != null && this.comprehensivenessSatisfaction <= 3) {
                this.userModeParams.GPT4.presence_penalty = Number((this.userModeParams.GPT4.presence_penalty + (2-this.userModeParams.GPT4.presence_penalty)*0.2*(4-this.comprehensivenessSatisfaction)/3).toFixed(2))
                this.userModeParams.Mixtral.diversity_penalty = Number((this.userModeParams.Mixtral.diversity_penalty + (2-this.userModeParams.Mixtral.diversity_penalty)*0.2*(4-this.comprehensivenessSatisfaction)/3).toFixed(2))
                this.userModeParams.Kimi.presence_penalty = Number((this.userModeParams.Kimi.presence_penalty + (2-this.userModeParams.Kimi.presence_penalty)*0.2*(4-this.comprehensivenessSatisfaction)/3).toFixed(2))
                this.userModeParams.llama3.presence_penalty = Number((this.userModeParams.llama3.presence_penalty + (2-this.userModeParams.llama3.presence_penalty)*0.2*(4-this.comprehensivenessSatisfaction)/3).toFixed(2))
                this.userModeParams.Claude.presence_penalty = Number((this.userModeParams.Claude.presence_penalty + (2-this.userModeParams.Claude.presence_penalty)*0.2*(4-this.comprehensivenessSatisfaction)/3).toFixed(2))
                this.userModeParams.Deepseek.presence_penalty = Number((this.userModeParams.Deepseek.presence_penalty + (2-this.userModeParams.Deepseek.presence_penalty)*0.2*(4-this.comprehensivenessSatisfaction)/3).toFixed(2))

                this.userModeParams.GPT4.max_tokens = Number((this.userModeParams.GPT4.max_tokens + (8192-this.userModeParams.GPT4.max_tokens)*0.1*(4-this.comprehensivenessSatisfaction)/3).toFixed(0))
                this.userModeParams.Mixtral.max_new_tokens = Number((this.userModeParams.Mixtral.max_new_tokens + (8192-this.userModeParams.Mixtral.max_new_tokens)*0.1*(4-this.comprehensivenessSatisfaction)/3).toFixed(0))
                this.userModeParams.Kimi.max_tokens = Number((this.userModeParams.Kimi.max_tokens + (8192-this.userModeParams.Kimi.max_tokens)*0.1*(4-this.comprehensivenessSatisfaction)/3).toFixed(0))
                this.userModeParams.llama3.max_tokens = Number((this.userModeParams.llama3.max_tokens + (8192-this.userModeParams.llama3.max_tokens)*0.1*(4-this.comprehensivenessSatisfaction)/3).toFixed(0))
                this.userModeParams.Claude.max_tokens = Number((this.userModeParams.Claude.max_tokens + (8192-this.userModeParams.Claude.max_tokens)*0.1*(4-this.comprehensivenessSatisfaction)/3).toFixed(0))
                this.userModeParams.Deepseek.max_tokens = Number((this.userModeParams.Deepseek.max_tokens + (8192-this.userModeParams.Deepseek.max_tokens)*0.1*(4-this.comprehensivenessSatisfaction)/3).toFixed(0))
            }

            this.userModeParams.GPT4.n=1
            this.userModeParams.Kimi.n=1
            this.userModeParams.Mixtral.do_sample=1
            this.userModeParams.Mixtral.num_beams=num_beams_tmp
            this.userModeParams.Mixtral.num_beam_groups=num_beam_groups_tmp
            this.userModeParams.Mixtral.num_return_sequences=1
            this.fixedChartGPT4(1);
            this.fixedChartMixtral(1);
            this.fixedChartKimi(1);
            this.fixedChartLlama3(1);
            this.fixedChartClaude(1);
            this.fixedChartDeepseek(1);

            this.thinkModeChange(1);
            let paramFormData = new FormData();
            let paramCurrentString = JSON.stringify(this.paramsUpdate);
            paramFormData.append('params', paramCurrentString);
            paramFormData.append('modelID', '1000')
            paramFormData.append('username', localStorage.getItem('userId'));
            // 首先执行 chat_sendParams
            chat_sendParams(paramFormData).then(response => {
                console.log("超参传后端", response['msg']);
            })

            let setParamFormData = new FormData();
            let paramString = JSON.stringify(this.userModeParams);
            setParamFormData.append('params', paramString);
            setParamFormData.append('username', localStorage.getItem('realName'));
            setParamFormData.append('sname', localStorage.getItem('sceneName'));
            set_usp(setParamFormData).then(response => {
                if (response.error_num === 0) {
                    this.$message.success('已按照反馈自动更新您在此场景的常用思维模式');
                } else {
                    this.$message.error('您在此场景的常用思维模式更新失败')
                }
            });
        },
        onCheckboxChange() {
            this.checked = !this.checked;
            this.$emit('change');
        },
        thinkModeChange(index) {
            // params、paramsUpdate 都要改，本质上和点选风格按钮一样
            if(index === 0) {
                Object.keys(this.paramsUpdate.GPT4).forEach(key => {
                    this.params.GPT4[key] = this.danKongModeParams.GPT4[key];
                    this.paramsUpdate.GPT4[key] = this.danKongModeParams.GPT4[key];
                });
                Object.keys(this.paramsUpdate.Mixtral).forEach(key => {
                    this.params.Mixtral[key] = this.danKongModeParams.Mixtral[key];
                    this.paramsUpdate.Mixtral[key] = this.danKongModeParams.Mixtral[key];
                });
                Object.keys(this.paramsUpdate.Kimi).forEach(key => {
                    this.params.Kimi[key] = this.danKongModeParams.Kimi[key];
                    this.paramsUpdate.Kimi[key] = this.danKongModeParams.Kimi[key];
                });
                Object.keys(this.paramsUpdate.llama3).forEach(key => {
                    this.params.llama3[key] = this.danKongModeParams.llama3[key];
                    this.paramsUpdate.llama3[key] = this.danKongModeParams.llama3[key];
                });
                Object.keys(this.paramsUpdate.Claude).forEach(key => {
                    this.params.Claude[key] = this.danKongModeParams.Claude[key];
                    this.paramsUpdate.Claude[key] = this.danKongModeParams.Claude[key];
                });
                Object.keys(this.paramsUpdate.Deepseek).forEach(key => {
                    this.params.Deepseek[key] = this.danKongModeParams.Deepseek[key];
                    this.paramsUpdate.Deepseek[key] = this.danKongModeParams.Deepseek[key];
                });
            }
            if(index === 1) {
                Object.keys(this.paramsUpdate.GPT4).forEach(key => {
                    this.params.GPT4[key] = this.userModeParams.GPT4[key];
                    this.paramsUpdate.GPT4[key] = this.userModeParams.GPT4[key];
                });
                Object.keys(this.paramsUpdate.Mixtral).forEach(key => {
                    this.params.Mixtral[key] = this.userModeParams.Mixtral[key];
                    this.paramsUpdate.Mixtral[key] = this.userModeParams.Mixtral[key];
                });
                Object.keys(this.paramsUpdate.Kimi).forEach(key => {
                    this.params.Kimi[key] = this.userModeParams.Kimi[key];
                    this.paramsUpdate.Kimi[key] = this.userModeParams.Kimi[key];
                });
                Object.keys(this.paramsUpdate.llama3).forEach(key => {
                    this.params.llama3[key] = this.userModeParams.llama3[key];
                    this.paramsUpdate.llama3[key] = this.userModeParams.llama3[key];
                });
                Object.keys(this.paramsUpdate.Claude).forEach(key => {
                    this.params.Claude[key] = this.userModeParams.Claude[key];
                    this.paramsUpdate.Claude[key] = this.userModeParams.Claude[key];
                });
                Object.keys(this.paramsUpdate.Deepseek).forEach(key => {
                    this.params.Deepseek[key] = this.userModeParams.Deepseek[key];
                    this.paramsUpdate.Deepseek[key] = this.userModeParams.Deepseek[key];
                });
            }
            this.$message.success('您切换了思维模式');
        },
        handleClick(type) {
            this.changeChartIsButton = true;
            // params、paramsUpdate 都要改
            if(this.configModel === 'GPT4') {
                if(type === '陈述型') {
                    this.params.GPT4.temperature = 0.1;
                    this.params.GPT4.top_p = 0.95;
                    this.params.GPT4.frequency_penalty = -1.0;
                    this.params.GPT4.presence_penalty = -1.0;
                    this.params.GPT4.max_tokens = 1024;
                    Object.keys(this.params.GPT4).forEach(key => {
                        this.paramsUpdate.GPT4[key] = this.params.GPT4[key];
                    });
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } if(type === '平衡型') {
                    this.params.GPT4.temperature = 0.8;
                    this.params.GPT4.top_p = 0.95;
                    this.params.GPT4.frequency_penalty = 0.0;
                    this.params.GPT4.presence_penalty = 0.0;
                    this.params.GPT4.max_tokens = 4096;
                    Object.keys(this.params.GPT4).forEach(key => {
                        this.paramsUpdate.GPT4[key] = this.params.GPT4[key];
                    });
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } if(type === '创造型') {
                    this.params.GPT4.temperature = 1.6;
                    this.params.GPT4.top_p = 0.95;
                    this.params.GPT4.frequency_penalty = 1.0;
                    this.params.GPT4.presence_penalty = 1.0;
                    this.params.GPT4.max_tokens = 7168;
                    Object.keys(this.params.GPT4).forEach(key => {
                        this.paramsUpdate.GPT4[key] = this.params.GPT4[key];
                    });
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            }
            else if(this.configModel === 'Mixtral') {
                if(type === '陈述型') {
                    this.params.Mixtral.temperature = 0.1;
                    this.params.Mixtral.top_p = 0.95;
                    this.params.Mixtral.top_k = 15;
                    this.params.Mixtral.max_length = 1024;
                    this.params.Mixtral.repetition_penalty = 0.5;
                    this.params.Mixtral.max_new_tokens = 1024;
                    this.params.Mixtral.length_penalty = 0;
                    // 获取所有可枚举属性的键
                    // 不能直接简单地赋值，会用同一个地址，导致watch：params等同于watch：paramsUpdate
                    // this.paramsUpdate = this.params;
                    Object.keys(this.params.Mixtral).forEach(key => {
                        this.paramsUpdate.Mixtral[key] = this.params.Mixtral[key];
                    });
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } if(type === '平衡型') {
                    this.params.Mixtral.temperature = 0.8;
                    this.params.Mixtral.top_p = 0.95;
                    this.params.Mixtral.top_k = 45;
                    this.params.Mixtral.max_length = 4096;
                    this.params.Mixtral.repetition_penalty = 2.0;
                    this.params.Mixtral.max_new_tokens = 4096;
                    this.params.Mixtral.length_penalty = 1;
                    Object.keys(this.params.Mixtral).forEach(key => {
                        this.paramsUpdate.Mixtral[key] = this.params.Mixtral[key];
                    });
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } if(type === '创造型') {
                    this.params.Mixtral.temperature = 1.6;
                    this.params.Mixtral.top_p = 0.95;
                    this.params.Mixtral.top_k = 80;
                    this.params.Mixtral.max_length = 7168;
                    this.params.Mixtral.repetition_penalty = 4.5;
                    this.params.Mixtral.max_new_tokens = 7168;
                    this.params.Mixtral.length_penalty = 2;
                    Object.keys(this.params.Mixtral).forEach(key => {
                        this.paramsUpdate.Mixtral[key] = this.params.Mixtral[key];
                    });
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            }
            else if(this.configModel === 'Kimi') {
                if(type === '陈述型') {
                    this.params.Kimi.temperature = 0.1;
                    this.params.Kimi.top_p = 0.95;
                    this.params.Kimi.frequency_penalty = -1.0;
                    this.params.Kimi.presence_penalty = -1.0;
                    this.params.Kimi.max_tokens = 1024;
                    Object.keys(this.params.Kimi).forEach(key => {
                        this.paramsUpdate.Kimi[key] = this.params.Kimi[key];
                    });
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } if(type === '平衡型') {
                    this.params.Kimi.temperature = 0.5;
                    this.params.Kimi.top_p = 0.95;
                    this.params.Kimi.frequency_penalty = 0.0;
                    this.params.Kimi.presence_penalty = 0.0;
                    this.params.Kimi.max_tokens = 4096;
                    Object.keys(this.params.Kimi).forEach(key => {
                        this.paramsUpdate.Kimi[key] = this.params.Kimi[key];
                    });
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } if(type === '创造型') {
                    this.params.Kimi.temperature = 0.9;
                    this.params.Kimi.top_p = 0.95;
                    this.params.Kimi.frequency_penalty = 1.0;
                    this.params.Kimi.presence_penalty = 1.0;
                    this.params.Kimi.max_tokens = 7168;
                    Object.keys(this.params.Kimi).forEach(key => {
                        this.paramsUpdate.Kimi[key] = this.params.Kimi[key];
                    });
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            }
            else if(this.configModel === 'llama3') {
                if(type === '陈述型') {
                    this.params.llama3.temperature = 0.1;
                    this.params.llama3.top_p = 0.95;
                    this.params.llama3.frequency_penalty = -1.0;
                    this.params.llama3.presence_penalty = -1.0;
                    this.params.llama3.max_tokens = 1024;
                    Object.keys(this.params.llama3).forEach(key => {
                        this.paramsUpdate.llama3[key] = this.params.llama3[key];
                    });
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } if(type === '平衡型') {
                    this.params.llama3.temperature = 0.5;
                    this.params.llama3.top_p = 0.95;
                    this.params.llama3.frequency_penalty = 0.0;
                    this.params.llama3.presence_penalty = 0.0;
                    this.params.llama3.max_tokens = 4096;
                    Object.keys(this.params.llama3).forEach(key => {
                        this.paramsUpdate.llama3[key] = this.params.llama3[key];
                    });
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } if(type === '创造型') {
                    this.params.llama3.temperature = 0.9;
                    this.params.llama3.top_p = 0.95;
                    this.params.llama3.frequency_penalty = 1.0;
                    this.params.llama3.presence_penalty = 1.0;
                    this.params.llama3.max_tokens = 7168;
                    Object.keys(this.params.llama3).forEach(key => {
                        this.paramsUpdate.llama3[key] = this.params.llama3[key];
                    });
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            }
            else if(this.configModel === 'Deepseek') {
                if(type === '陈述型') {
                    this.params.Deepseek.temperature = 0.1;
                    this.params.Deepseek.top_p = 0.95;
                    this.params.Deepseek.frequency_penalty = -1.0;
                    this.params.Deepseek.presence_penalty = -1.0;
                    this.params.Deepseek.max_tokens = 1024;
                    Object.keys(this.params.Deepseek).forEach(key => {
                        this.paramsUpdate.Deepseek[key] = this.params.Deepseek[key];
                    });
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } if(type === '平衡型') {
                    this.params.Deepseek.temperature = 0.8;
                    this.params.Deepseek.top_p = 0.95;
                    this.params.Deepseek.frequency_penalty = 0.0;
                    this.params.Deepseek.presence_penalty = 0.0;
                    this.params.Deepseek.max_tokens = 4096;
                    Object.keys(this.params.Deepseek).forEach(key => {
                        this.paramsUpdate.Deepseek[key] = this.params.Deepseek[key];
                    });
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } if(type === '创造型') {
                    this.params.Deepseek.temperature = 1.5;
                    this.params.Deepseek.top_p = 0.95;
                    this.params.Deepseek.frequency_penalty = 1.0;
                    this.params.Deepseek.presence_penalty = 1.0;
                    this.params.Deepseek.max_tokens = 7168;
                    Object.keys(this.params.Deepseek).forEach(key => {
                        this.paramsUpdate.Deepseek[key] = this.params.Deepseek[key];
                    });
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            }
            else {
                if(type === '陈述型') {
                    this.params.Claude.temperature = 0.1;
                    this.params.Claude.top_p = 0.95;
                    this.params.Claude.top_k = 20;
                    this.params.Claude.max_tokens = 1024;
                    Object.keys(this.params.Claude).forEach(key => {
                        this.paramsUpdate.Claude[key] = this.params.Claude[key];
                    });
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } if(type === '平衡型') {
                    this.params.Claude.temperature = 0.5;
                    this.params.Claude.top_p = 0.95;
                    this.params.Claude.top_k = 35;
                    this.params.Claude.max_tokens = 4096;
                    Object.keys(this.params.Claude).forEach(key => {
                        this.paramsUpdate.Claude[key] = this.params.Claude[key];
                    });
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } if(type === '创造型') {
                    this.params.Claude.temperature = 0.9;
                    this.params.Claude.top_p = 0.95;
                    this.params.Claude.top_k = 45;
                    this.params.Claude.max_tokens = 7168;
                    Object.keys(this.params.Claude).forEach(key => {
                        this.paramsUpdate.Claude[key] = this.params.Claude[key];
                    });
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            }
        },
        handleEvent(event) {
            // 1. 拖动雷达图后真正更新参数的地方
            const axisMinAndMaxGPT4 = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            const axisMinAndMaxMixtral = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: 10, max: 100 },
                { min: 512, max: 8192 },
                { min: 0, max: 1 },
                { min: 1, max: 20 },
                { min: 1, max: 20 },
                { min: 1, max: 3 },
                { min: 0, max: 5 },
                { min: 512, max: 8192 },
                { min: -2, max: 2 },
                { min: -2, max: 2 }
            ];

            const axisMinAndMaxKimi = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            const axisMinAndMaxLlama = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            const axisMinAndMaxClaude = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: 15, max: 50 },
                { min: 512, max: 8192 }
            ];

            const axisMinAndMaxDeepseek = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            if(this.configModel === 'GPT4') {
                let keys = Object.keys(this.paramsUpdate.GPT4);
                this.paramsUpdate.GPT4[keys[event.detail.axisIndex]] = this.mapValueToAxisInterval(event.detail.axisIndex, event.detail.value, axisMinAndMaxGPT4, this.configModel);
            } else if(this.configModel === 'Mixtral') {
                let keys = Object.keys(this.paramsUpdate.Mixtral);
                this.paramsUpdate.Mixtral[keys[event.detail.axisIndex]] = this.mapValueToAxisInterval(event.detail.axisIndex, event.detail.value, axisMinAndMaxMixtral, this.configModel);
            } else if(this.configModel === 'Kimi') {
                let keys = Object.keys(this.paramsUpdate.Kimi);
                this.paramsUpdate.Kimi[keys[event.detail.axisIndex]] = this.mapValueToAxisInterval(event.detail.axisIndex, event.detail.value, axisMinAndMaxKimi, this.configModel);
            } else if(this.configModel === 'llama3') {
                let keys = Object.keys(this.paramsUpdate.llama3);
                this.paramsUpdate.llama3[keys[event.detail.axisIndex]] = this.mapValueToAxisInterval(event.detail.axisIndex, event.detail.value, axisMinAndMaxLlama, this.configModel);
            } else if(this.configModel === 'Deepseek') {
                let keys = Object.keys(this.paramsUpdate.Deepseek);
                this.paramsUpdate.Deepseek[keys[event.detail.axisIndex]] = this.mapValueToAxisInterval(event.detail.axisIndex, event.detail.value, axisMinAndMaxDeepseek, this.configModel);
            } else {
                let keys = Object.keys(this.paramsUpdate.Claude);
                this.paramsUpdate.Claude[keys[event.detail.axisIndex]] = this.mapValueToAxisInterval(event.detail.axisIndex, event.detail.value, axisMinAndMaxClaude, this.configModel);
            }

            console.log("params", this.params);
            console.log("paramsUpdate", this.paramsUpdate);

            // 2. 计算创造度得分，用于拖动后判别属于哪一类
            let score = 0;
            if(this.configModel === 'GPT4') {
                Object.keys(this.paramsUpdate.GPT4).forEach((key) => {
                    const value = this.paramsUpdate.GPT4[key];
                    // const index = parseInt(key.replace('value', ''));
                    const index = Object.keys(this.paramsUpdate.GPT4).indexOf(key);
                    const { min, max } = axisMinAndMaxGPT4[index];

                    // 计算分段的阈值
                    const firstThird = min + (max - min) / 3;
                    const secondThird = min + 2 * (max - min) / 3;

                    if( index === 0 || index === 1 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 3;
                        } else {
                            score += 5;
                        }
                    }
                    if( index === 2 || index === 3 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 0;
                        } else {
                            score += 2;
                        }
                    }
                    if( index === 4 ){
                        if (value <= firstThird) {
                            score += 1;
                        } else if (value <= secondThird) {
                            score += 2;
                        } else {
                            score += 3;
                        }
                    }
                });
            }
            else if(this.configModel === 'Mixtral') {
                Object.keys(this.paramsUpdate.Mixtral).forEach((key) => {
                    const value = this.paramsUpdate.Mixtral[key];
                    // const index = parseInt(key.replace('value', ''));
                    const index = Object.keys(this.paramsUpdate.Mixtral).indexOf(key);
                    const { min, max } = axisMinAndMaxMixtral[index];

                    // 计算分段的阈值
                    const firstThird = min + (max - min) / 3;
                    const secondThird = min + 2 * (max - min) / 3;

                    if( index !== 4 && index !== 5 && index !== 6 && index !== 7 && index !== 10 && index !== 11 ) {
                        // 判断 value 所在的区间，并更新 score
                        // 温度、top_p、top_k，分数设计特别一些，因为有互相影响
                        if( index === 0 || index === 1 || index === 2){
                            if( index === 2){
                                if(this.paramsUpdate.Mixtral.do_sample > 0) {
                                    if (value <= firstThird) {
                                        score -= 2;
                                    } else if (value <= secondThird) {
                                        score += 1;
                                    } else {
                                        score += 3;
                                    }
                                }
                            }
                            if( index === 0 || index === 1 ){
                                if(this.paramsUpdate.Mixtral.do_sample > 0) {
                                    if (value <= firstThird) {
                                        score -= 2;
                                    } else if (value <= secondThird) {
                                        score += 3;
                                    } else {
                                        score += 5;
                                    }
                                }
                            }
                        }
                        // 生成长度以及重复惩罚
                        else {
                            if (value <= firstThird) {
                            } else if (value <= secondThird) {
                                score += 1;
                            } else {
                                score += 2;
                            }
                        }
                    }
                    // >1开启束搜索，更陈述、精确，缺少多样性
                    if( index === 5) {    
                        if(value === 1) {
                        } else {
                            if (value <= firstThird) {
                                score -= 3;
                            } else if (value <= secondThird) {
                                score -= 2;
                            } else {
                                score -= 1;
                            }
                        } 
                    }
                    // 开启束搜索，以下参数才生效
                    if(this.paramsUpdate.Mixtral.num_beams > 1) {
                        // 分组，组内可相似，组间不相似，增加多样性
                        if( index === 6) {
                            if (value <= firstThird) {
                                score += 1;
                            } else if (value <= secondThird) {
                                score += 2;
                            } else {
                                score += 3;
                            }
                        }
                        // 扩大组间不相似度，增加多样性
                        if(this.paramsUpdate.Mixtral.num_beam_groups > 1) {
                            if( index === 10) {
                                if (value <= firstThird) {
                                    score += 1;
                                } else if (value <= secondThird) {
                                    score += 2;
                                } else {
                                    score += 3;
                                }
                            }
                        }
                        // 鼓励长句子，增加多样性
                        if( index === 11) {
                            if (value <= firstThird) {
                                score -= 1;
                            } else if (value <= secondThird) {
                            } else {
                                score += 1;
                            }
                        }
                    }
                    if( index === 4) {     // 不采样，贪心策略
                        if(value === 0){
                            score -= 5;
                        }
                    }
                    // else if(this.configModel === 'GPT4') {
                    //     if( key === 'value1' ){
                    //         if (value <= firstThird) {
                    //             score = 1;
                    //         } else if (value <= secondThird) {
                    //             score = 2;
                    //         } else {
                    //             score = 3;
                    //         }
                    //     }
                    //     // 最终得分为二者中低的那个
                    //     if( key === 'value2' ){
                    //         if (value <= firstThird) {
                    //             score = 1;
                    //         } else if (value <= secondThird) {
                    //             if(score === 1){
                    //             } else {
                    //                 score = 2;
                    //             }
                    //         } else {
                    //             if(score === 1){
                    //             } else {
                    //                 if(score === 2){
                    //                 } else {
                    //                     score = 3;
                    //                 }
                    //             }
                    //         }
                    //     }
                    // }
                });
            }
            else if(this.configModel === 'Kimi') {
                Object.keys(this.paramsUpdate.Kimi).forEach((key) => {
                    const value = this.paramsUpdate.Kimi[key];
                    // const index = parseInt(key.replace('value', ''));
                    const index = Object.keys(this.paramsUpdate.Kimi).indexOf(key);
                    const { min, max } = axisMinAndMaxKimi[index];

                    // 计算分段的阈值
                    const firstThird = min + (max - min) / 3;
                    const secondThird = min + 2 * (max - min) / 3;

                    if( index === 0 || index === 1 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 3;
                        } else {
                            score += 5;
                        }
                    }
                    if( index === 2 || index === 3 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 0;
                        } else {
                            score += 2;
                        }
                    }
                    if( index === 4 ){
                        if (value <= firstThird) {
                            score += 1;
                        } else if (value <= secondThird) {
                            score += 2;
                        } else {
                            score += 3;
                        }
                    }
                });
            }
            else if(this.configModel === 'llama3') {
                Object.keys(this.paramsUpdate.llama3).forEach((key) => {
                    const value = this.paramsUpdate.llama3[key];
                    // const index = parseInt(key.replace('value', ''));
                    const index = Object.keys(this.paramsUpdate.llama3).indexOf(key);
                    const { min, max } = axisMinAndMaxLlama[index];

                    // 计算分段的阈值
                    const firstThird = min + (max - min) / 3;
                    const secondThird = min + 2 * (max - min) / 3;

                    // -7~17，0|8
                    if( index === 0 || index === 1 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 3;
                        } else {
                            score += 5;
                        }
                    }
                    if( index === 2 || index === 3 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 0;
                        } else {
                            score += 2;
                        }
                    }
                    if( index === 4 ){
                        if (value <= firstThird) {
                            score += 1;
                        } else if (value <= secondThird) {
                            score += 2;
                        } else {
                            score += 3;
                        }
                    }
                });
            }
            else if(this.configModel === 'Deepseek') {
                Object.keys(this.paramsUpdate.Deepseek).forEach((key) => {
                    const value = this.paramsUpdate.Deepseek[key];
                    // const index = parseInt(key.replace('value', ''));
                    const index = Object.keys(this.paramsUpdate.Deepseek).indexOf(key);
                    const { min, max } = axisMinAndMaxDeepseek[index];

                    // 计算分段的阈值
                    const firstThird = min + (max - min) / 3;
                    const secondThird = min + 2 * (max - min) / 3;

                    // -7~17，0|8
                    if( index === 0 || index === 1 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 3;
                        } else {
                            score += 5;
                        }
                    }
                    if( index === 2 || index === 3 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 0;
                        } else {
                            score += 2;
                        }
                    }
                    if( index === 4 ){
                        if (value <= firstThird) {
                            score += 1;
                        } else if (value <= secondThird) {
                            score += 2;
                        } else {
                            score += 3;
                        }
                    }
                });
            }
            else {
                Object.keys(this.paramsUpdate.Claude).forEach((key) => {
                    const value = this.paramsUpdate.Claude[key];
                    // const index = parseInt(key.replace('value', ''));
                    const index = Object.keys(this.paramsUpdate.Claude).indexOf(key);
                    const { min, max } = axisMinAndMaxClaude[index];

                    // 计算分段的阈值
                    const firstThird = min + (max - min) / 3;
                    const secondThird = min + 2 * (max - min) / 3;

                    // -7~17，0|8
                    if( index === 0 || index === 1 || index === 2 ){
                        if (value <= firstThird) {
                            score -= 2;
                        } else if (value <= secondThird) {
                            score += 3;
                        } else {
                            score += 5;
                        }
                    }
                    if( index === 3 ){
                        if (value <= firstThird) {
                            score += 1;
                        } else if (value <= secondThird) {
                            score += 2;
                        } else {
                            score += 3;
                        }
                    }
                });
            }

            console.log("得分：", score);

            // 3. 判断 score 所在的区间，并更新按钮高亮划类
            if(this.configModel === 'Mixtral') {
                if (score <= 1) {
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } else if (score <= 12) {
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } else {
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            } else {
                if (score <= 0) {
                    this.paramsClass = '陈述型';
                    this.$message.success('当前模式：简短聊天，有助于事实调查');
                } else if (score <= 8) {
                    this.paramsClass = '平衡型';
                    this.$message.success('当前模式：均衡问答，用于日常的有料对话');
                } else {
                    this.paramsClass = '创造型';
                    this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
                }
            }
        },
        mapValueToAxisInterval(axisIndex, value, axisMinAndMax, configModel) {
            // 雷达图各属性value均默认0~1未处理, 此处将0~1映射到正确范围
            const { min, max } = axisMinAndMax[axisIndex];
            const scaledValue = min + (value * (max - min));  
            // 更新参数时按整数或小数分类
            if(configModel === 'GPT4') {
                if(axisIndex === 0||axisIndex === 1||axisIndex === 2||axisIndex === 3)
                    return Number(scaledValue.toFixed(2));
                else
                    return Number(scaledValue.toFixed(0));
            } else if(configModel === 'Mixtral') {
                if(axisIndex === 2||axisIndex === 3||axisIndex === 4||axisIndex === 5||axisIndex === 6||axisIndex === 7||axisIndex === 9)
                    return Number(scaledValue.toFixed(0));
                else
                    return Number(scaledValue.toFixed(2));
            } else if(configModel === 'Kimi') {
                if(axisIndex === 0||axisIndex === 1||axisIndex === 2||axisIndex === 3)
                    return Number(scaledValue.toFixed(2));
                else
                    return Number(scaledValue.toFixed(0));
            } else if(configModel === 'llama3') {
                if(axisIndex === 0||axisIndex === 1||axisIndex === 2||axisIndex === 3)
                    return Number(scaledValue.toFixed(2));
                else
                    return Number(scaledValue.toFixed(0));
            } else {
                if(axisIndex === 0||axisIndex === 1)
                    return Number(scaledValue.toFixed(2));
                else
                    return Number(scaledValue.toFixed(0));
            }
        },
        // 一次迭代可能得分：[-15,-13,-10,-9,-8,-7,-6,-5,-4,-2,-1,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,17,18,21]
        calculateScore(values) {
            let score = 0;

            // 随机采样开启时，处理第1、2、3个值
            if (values[4] > 0) {
                let max = 100;
                let third = max / 3;
                [0, 1, 2].forEach(index => {
                    if(index === 0){
                        let value = values[index];
                        if (value < third) score -= 2;
                        else if (value < 2 * third) score += 3;
                        else score += 5;
                    }
                    if(index === 1||index === 2){
                        let value = values[11];
                        if (value < third) score -= 2;
                        else if (value < 2 * third) score += 1;
                        else score += 3;
                    }
                }); 
            }

            // 处理第4、9、10个值
            [3, 8, 9].forEach(index => {
                let value = values[index];
                let max = 100;
                let third = max / 3;
                if (value < third) score += 0;
                else if (value < 2 * third) score += 1;
                else score += 2;
            });

            // 第5个值
            if (values[4] === 0) score -= 5;

            // 第6个值
            if (values[5] > 0) {
                let max = 100;
                let third = max / 3;
                if (values[5] < third) score -= 3;
                else if (values[5] < 2 * third) score -= 2;
                else score -= 1;
            }

            // 当第6个值不为其范围闭区间内最小值时处理第7、11、12个值
            if (values[5] > 0) {
                let max = 100;
                let third = max / 3;
                [6, 10, 11].forEach(index => {
                    if(index === 6){
                        let value = values[index];
                        if (value < third) score += 1;
                        else if (value < 2 * third) score += 2;
                        else score += 3;
                    }
                    if(index === 10 && values[6] > 0){
                        let value = values[index];
                        if (value < third) score += 1;
                        else if (value < 2 * third) score += 2;
                        else score += 3;
                    }
                    if(index === 11){
                        let value = values[11];
                        if (value < third) score -= 1;
                        else if (value < 2 * third) score += 0;
                        else score += 1;
                    }
                });            
            }
            
            return score;
        },
        generateAllScores() {
            const maxValue = 100;
            let possibleScores = new Set();
            // 简单化处理，仅为示例，这里不迭代所有值
            // for (let i = 0; i <= maxValue; i += 5) {  // 以步长5迭代以减少计算量
            //     for (let j = 0; j <= maxValue; j += 5) {
            //         for (let k = 0; k <= maxValue; k += 5) {
            //             // 此处添加更多迭代，或使用随机方法生成值
            //             let values = [i, i, i, j, j, k, k, i, j, j, k, k]; // 示例值
            //             possibleScores.add(this.calculateScore(values));
            //         }
            //     }
            // }
            for (let a = 0; a <= maxValue; a += 5) {
                for (let b = 0; b <= maxValue; b += 5) {
                    for (let c = 0; c <= maxValue; c += 5) {
                        for (let d = 0; d <= maxValue; d += 5) {
                            for (let e = 0; e <= maxValue; e += 5) {
                                let values = [a, b, c, d, e, a, b, c, d, e, a, b];
                                possibleScores.add(this.calculateScore(values));
                            }
                        }
                    }
                }
            }
            return Array.from(possibleScores).sort((a, b) => a - b);
        },
        initChartMixtral() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#00A0B0"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大长度", "随机采样", "beam搜索", "beam组数", "返回条数", "重复惩罚值", "最大新词数", "多样性惩罚", "生成长度惩罚"];
            let a_model = [0.6, 0.95, 25, 4096, 1, 1, 1, 1, 2.0, 4096, 1.1, 1.0];
            let axname = ["temperature", "top_p", "top_k", "max_length", "do_sample", "num_beams", "num_beam_groups", "num_return_sequences", "repetition_penalty", "max_new_tokens", "diversity_penalty", "length_penalty"];
            let i = 0;
            Object.keys(this.userModeParams.Mixtral).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.userModeParams.Mixtral[key];
            });
            // let a_model = [0.6, 0.95, 25, 256, 1, 1, 1, 1, 1, 256, 1.1, 1];
            // let a_model = [1.8, 0.95, 50, 512, 1, 1, 1, 1, 1.5, 512, 1.1, 2];
            // let a_model = [0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3];
            // let b_model = [0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8];

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: 10, max: 100 },
                { min: 512, max: 8192 },
                { min: 0, max: 1 },
                { min: 1, max: 20 },
                { min: 1, max: 20 },
                { min: 1, max: 3 },
                { min: 0, max: 5 },
                { min: 512, max: 8192 },
                { min: -2, max: 2 },
                { min: -2, max: 2 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },
        changeChartMixtral() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#00A0B0"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大长度", "随机采样", "beam搜索", "beam组数", "返回条数", "重复惩罚值", "最大新词数", "多样性惩罚", "生成长度惩罚"];
            let a_model = [0.1, 0.95, 15, 1024, 1, 1, 1, 1, 0.5, 1024, 1.1, 0.0];
            if (this.changeChartIsButton === true) {
                if (this.paramsClass === '平衡型') {
                    a_model = [0.8, 0.95, 45, 4096, 1, 1, 1, 1, 2.0, 4096, 1.1, 1.0];
                }
                if (this.paramsClass === '创造型') {
                    a_model = [1.6, 0.95, 80, 7168, 1, 1, 1, 1, 4.5, 7168, 1.1, 2.0];
                }
                this.changeChartIsButton = false;
            } else {
                Object.keys(this.paramsUpdate.Mixtral).forEach((key, index) => {
                    if (index < a_model.length) {   // 确保不超出数组界限
                        a_model[index] = this.paramsUpdate.Mixtral[key];
                    }
                });
            }
            // let a_model = [0.6, 0.95, 25, 256, 1, 1, 1, 1, 1, 256, 1.1, 1];
            // let a_model = [1.8, 0.95, 50, 512, 1, 1, 1, 1, 1.5, 512, 1.1, 2];
            // let a_model = [0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3];
            // let b_model = [0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8];

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: 10, max: 100 },
                { min: 512, max: 8192 },
                { min: 0, max: 1 },
                { min: 1, max: 20 },
                { min: 1, max: 20 },
                { min: 1, max: 3 },
                { min: 0, max: 5 },
                { min: 512, max: 8192 },
                { min: -2, max: 2 },
                { min: -2, max: 2 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
                // 不能在这里更新，spiderChart.js 里调这个回调时，找不到vue组件里的 “this”
                // this.paramsUpdate['value' + (axisIndex+1)] = this.mapValueToAxisInterval(axisIndex, value, axisMinAndMax);
                // console.log("params", this.params);
                // console.log("paramsUpdate", this.paramsUpdate);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },
        initChartGPT4() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#EDC951"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "n"];
            let a_model = [0.7, 0.95, 1.0, 1.0, 2048, 1];
            let i = 0;
            Object.keys(this.userModeParams.GPT4).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.userModeParams.GPT4[key];
            });
            // let a_model = [0.6, 0.95, 25, 256, 1, 1, 1, 1, 1, 256, 1.1, 1];
            // let a_model = [1.8, 0.95, 50, 512, 1, 1, 1, 1, 1.5, 512, 1.1, 2];
            // let a_model = [0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3];
            // let b_model = [0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8];

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },
        changeChartGPT4() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#EDC951"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let a_model = [0.1, 0.95, -1.0, -1.0, 1024, 1];
            if (this.changeChartIsButton === true) {
                if (this.paramsClass === '平衡型'){
                    a_model = [0.8, 0.95, 0.0, 0.0, 4096, 1];
                }
                if (this.paramsClass === '创造型'){
                    a_model = [1.6, 0.95, 1.0, 1.0, 7168, 1];
                }
                this.changeChartIsButton = false;
            } else {
                Object.keys(this.paramsUpdate.GPT4).forEach((key, index) => {
                    if (index < a_model.length) {   // 确保不超出数组界限
                        a_model[index] = this.paramsUpdate.GPT4[key];
                    }
                });
            }
            // let a_model = [0.6, 0.95, 25, 256, 1, 1, 1, 1, 1, 256, 1.1, 1];
            // let a_model = [1.8, 0.95, 50, 512, 1, 1, 1, 1, 1.5, 512, 1.1, 2];
            // let a_model = [0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3, 0.4, 0.6, 0.59, 0.5, 0.3];
            // let b_model = [0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8, 0.99, 0.9, 0.7, 0.9, 0.8];

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },

        initChartKimi() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#E4007F"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "n"];
            let a_model = [0.7, 0.95, 1.0, 1.0, 2048, 1];
            let i = 0;
            Object.keys(this.userModeParams.Kimi).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.userModeParams.Kimi[key];
            });

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },
        changeChartKimi() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#E4007F"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let a_model = [0.1, 0.95, -1.0, -1.0, 1024, 1];
            if (this.changeChartIsButton === true) {
                if (this.paramsClass === '平衡型'){
                    a_model = [0.5, 0.95, 0.0, 0.0, 4096, 1];
                }
                if (this.paramsClass === '创造型'){
                    a_model = [0.9, 0.95, 1.0, 1.0, 7168, 1];
                }
                this.changeChartIsButton = false;
            } else {
                Object.keys(this.paramsUpdate.Kimi).forEach((key, index) => {
                    if (index < a_model.length) {   // 确保不超出数组界限
                        a_model[index] = this.paramsUpdate.Kimi[key];
                    }
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },

        initChartLlama3() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens"];
            let a_model = [0.7, 0.95, 1.0, 1.0, 2048];
            let i = 0;
            Object.keys(this.userModeParams.llama3).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.userModeParams.llama3[key];
            });

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },
        changeChartLlama3() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let a_model = [0.1, 0.95, -1.0, -1.0, 1024];
            if (this.changeChartIsButton === true) {
                if (this.paramsClass === '平衡型'){
                    a_model = [0.5, 0.95, 0.0, 0.0, 4096];
                }
                if (this.paramsClass === '创造型'){
                    a_model = [0.9, 0.95, 1.0, 1.0, 7168];
                }
                this.changeChartIsButton = false;
            } else {
                Object.keys(this.paramsUpdate.llama3).forEach((key, index) => {
                    if (index < a_model.length) {   // 确保不超出数组界限
                        a_model[index] = this.paramsUpdate.llama3[key];
                    }
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },

        initChartClaude() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#20D5E2"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大词数"];
            let axname = ["temperature", "top_p", "top_k", "max_tokens"];
            let a_model = [0.7, 0.95, 30, 2048];
            let i = 0;
            Object.keys(this.userModeParams.Claude).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.userModeParams.Claude[key];
            });

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: 15, max: 50 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },
        changeChartClaude() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#20D5E2"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大词数"];
            let a_model = [0.1, 0.95, 20, 1024];
            if (this.changeChartIsButton === true) {
                if (this.paramsClass === '平衡型'){
                    a_model = [0.5, 0.95, 35, 4096];
                }
                if (this.paramsClass === '创造型'){
                    a_model = [0.9, 0.95, 45, 7168];
                }
                this.changeChartIsButton = false;
            } else {
                Object.keys(this.paramsUpdate.Claude).forEach((key, index) => {
                    if (index < a_model.length) {   // 确保不超出数组界限
                        a_model[index] = this.paramsUpdate.Claude[key];
                    }
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: 15, max: 50 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },

        initChartDeepseek() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens"];
            let a_model = [0.7, 0.95, 1.0, 1.0, 2048];
            let i = 0;
            Object.keys(this.userModeParams.Deepseek).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.userModeParams.Deepseek[key];
            });

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },
        changeChartDeepseek() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                // color: d3.scale.ordinal().range(["#00A0B0", "#EDC951"])
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let a_model = [0.1, 0.95, -1.0, -1.0, 1024];
            if (this.changeChartIsButton === true) {
                if (this.paramsClass === '平衡型'){
                    a_model = [0.8, 0.95, 0.0, 0.0, 4096];
                }
                if (this.paramsClass === '创造型'){
                    a_model = [1.5, 0.95, 1.0, 1.0, 7168];
                }
                this.changeChartIsButton = false;
            } else {
                Object.keys(this.paramsUpdate.Deepseek).forEach((key, index) => {
                    if (index < a_model.length) {   // 确保不超出数组界限
                        a_model[index] = this.paramsUpdate.Deepseek[key];
                    }
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            function handleEdit(axisIndex, value) {
                // 拖动的轴名，和数据值
                console.log("change:" + axisIndex + " to " + value);
            }

            SpiderChart("#spiderChart", axes, [a_model_convert], chartOptions, handleEdit, this.configModel);
        },

        fixedChartMixtral(index) {
            let chartOptions = {
                w: 160,
                h: 160,
                labelPositionRatio: 1.33,
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#00A0B0"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大长度", "随机采样", "beam搜索", "beam组数", "返回条数", "重复惩罚值", "最大新词数", "多样性惩罚", "生成长度惩罚"];
            let axname = ["temperature", "top_p", "top_k", "max_length", "do_sample", "num_beams", "num_beam_groups", "num_return_sequences", "repetition_penalty", "max_new_tokens", "diversity_penalty", "length_penalty"];
            let a_model = [0.1, 0.95, 15, 512, 1, 1, 1, 1, 1.5, 256, 1.1, 0];
            let i = 0;
            if (index === 0) {
                Object.keys(this.danKongModeParams.Mixtral).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.danKongModeParams.Mixtral[key];
                });
            }
            if (index === 1) {
                Object.keys(this.userModeParams.Mixtral).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.userModeParams.Mixtral[key];
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: 10, max: 100 },
                { min: 512, max: 8192 },
                { min: 0, max: 1 },
                { min: 1, max: 20 },
                { min: 1, max: 20 },
                { min: 1, max: 3 },
                { min: 0, max: 5 },
                { min: 512, max: 8192 },
                { min: -2, max: 2 },
                { min: -2, max: 2 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            SpiderChartCard(`#spiderChartMixtral_${index}`, axes, [a_model_convert], chartOptions, 'Mixtral');
        },
        fixedChartGPT4(index) {
            let chartOptions = {
                w: 160,
                h: 160,
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#EDC951"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "n"];
            let a_model = [0.1, 0.95, 0.0, 0.0, 1024, 1];
            let i = 0;
            if (index === 0) {
                Object.keys(this.danKongModeParams.GPT4).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.danKongModeParams.GPT4[key];
                });
            }
            if (index === 1) {
                Object.keys(this.userModeParams.GPT4).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.userModeParams.GPT4[key];
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            SpiderChartCard(`#spiderChartGPT4_${index}`, axes, [a_model_convert], chartOptions, 'GPT4');
        },
        fixedChartKimi(index) {
            let chartOptions = {
                w: 160,
                h: 160,
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#E4007F"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "n"];
            let a_model = [0.1, 0.95, 1.0, 1.0, 1024, 1];
            let i = 0;
            if (index === 0) {
                Object.keys(this.danKongModeParams.Kimi).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.danKongModeParams.Kimi[key];
                });
            }
            if (index === 1) {
                Object.keys(this.userModeParams.Kimi).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.userModeParams.Kimi[key];
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 },
                { min: 1, max: 3}
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            SpiderChartCard(`#spiderChartKimi_${index}`, axes, [a_model_convert], chartOptions, 'Kimi');
        },
        fixedChartLlama3(index) {
            let chartOptions = {
                w: 160,
                h: 160,
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens"];
            let a_model = [0.1, 0.95, 1.0, 1.0, 1024];
            let i = 0;
            if (index === 0) {
                Object.keys(this.danKongModeParams.llama3).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.danKongModeParams.llama3[key];
                });
            }
            if (index === 1) {
                Object.keys(this.userModeParams.llama3).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.userModeParams.llama3[key];
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            SpiderChartCard(`#spiderChartLlama3_${index}`, axes, [a_model_convert], chartOptions, 'llama3');
        },
        fixedChartClaude(index) {
            let chartOptions = {
                w: 160,
                h: 160,
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#20D5E2"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大词数"];
            let axname = ["temperature", "top_p", "top_k", "max_tokens"];
            let a_model = [0.1, 0.95, 20, 1024];
            let i = 0;
            if (index === 0) {
                Object.keys(this.danKongModeParams.Claude).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.danKongModeParams.Claude[key];
                });
            }
            if (index === 1) {
                Object.keys(this.userModeParams.Claude).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.userModeParams.Claude[key];
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 1.0 },
                { min: 0.05, max: 0.95 },
                { min: 15, max: 50 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            SpiderChartCard(`#spiderChartClaude_${index}`, axes, [a_model_convert], chartOptions, 'Claude');
        },
        fixedChartDeepseek(index) {
            let chartOptions = {
                w: 160,
                h: 160,
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens"];
            let a_model = [0.1, 0.95, 1.0, 1.0, 1024];
            let i = 0;
            if (index === 0) {
                Object.keys(this.danKongModeParams.Deepseek).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.danKongModeParams.Deepseek[key];
                });
            }
            if (index === 1) {
                Object.keys(this.userModeParams.Deepseek).forEach(key => {
                    i = axname.indexOf(key);
                    a_model[i] = this.userModeParams.Deepseek[key];
                });
            }

            // 定义每个指标的最小和最大值
            const axisMinAndMax = [
                { min: 0.05, max: 2.0 },
                { min: 0.05, max: 0.95 },
                { min: -2.0, max: 2.0 },
                { min: -2.0, max: 2.0 },
                { min: 512, max: 8192 }
            ];

            function convertModel(a_model, axisMinAndMax) {
                let a_model_convert = a_model.map((value, index) => {
                    let range = axisMinAndMax[index];
                    return (value - range.min) / (range.max - range.min);
                });
                return a_model_convert;
            }

            let a_model_convert = convertModel(a_model, axisMinAndMax);
            console.log("转换后的参数值", a_model_convert);

            SpiderChartCard(`#spiderChartDeepseek_${index}`, axes, [a_model_convert], chartOptions, 'Deepseek');
        },
    }
};
</script>

<!-- 这里需要SCSS 而不是普通的 CSS，增加了变量、嵌套、混合、函数等功能 -->
<style lang="scss" scoped>
.card-top-right2 {
    width: 104%;
    z-index: 1000;
}
.card-top-right2-button {
    background-size: contain;
    background-repeat: no-repeat;
    vertical-align: middle;
    height: 20.8px;
    width: 20.8px;
    border-radius: 3px;
    float: right;
    right: 0;
    z-index: 10000;
}


.card-top-right2-button.checked {
    background-image: url('@/assets/img/pin_blue.png');
}

.card-top-right2-button:not(.checked) {
    background-image: url('@/assets/img/pin_grey.png');
}




.bottom-nav-buttons {
  position: absolute;
  right: 188px;
  top: 13px;
  width: 300px;

  .el-button {
    margin: 0 10px;
    font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
    font-size: 16px;
    font-weight: 550;
    color: #6a45c2;
    cursor: pointer;
    transition: background-color 0.5s;
    background-color: #bccfe3;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

    &:hover {
      background-color: #ced8d8;
      box-shadow: 0 4px 8px rgba(106, 106, 106, 0.3);
    }
  }
}

.el-button.is-active {
  /* 激活状态的样式 */
  color: #fff;
  background-color: #669fd7;
  border-color: #409eff;
}



.think-mode {
  width: 90%;
  height: 100%;
  margin-left: 30px;
  font-size: 15px;
  padding: 5px;
  overflow-y: auto;
}

.think-mode-title {
  width: 90%;
  font-size: 22px;
  font-weight: 900;
}

.item-content {
  margin-left: 10px;
  margin-top: 5px;
  font-weight: 500;
}

.spiderChartsModels {
  display: flex;
  justify-content: space-between; /* 水平排列，并且元素之间有间隔 */
  width: 100%; /* 根据需要调整宽度 */
}

.think-mode-item {
  width: 90%;
  overflow-x: auto;
  margin: 10px;
  background-color: #efdada;
  border-radius: 20px;
  padding: 5px;
  margin-bottom: 30px; /* items之间10像素的垂直间距 */
  cursor: pointer;

  &:hover {
    background-color: #e4c4c4;
  }
}
</style>