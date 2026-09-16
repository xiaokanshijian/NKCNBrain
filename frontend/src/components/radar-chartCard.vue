<template>
    <div style="width: 100%; 
                height: 100%; 
                display: flex; /* 使用Flexbox布局 */
                justify-content: center; /* 水平居中子元素 */"
        id="spiderChartCard">
    </div>
</template>

<script>
// import * as echarts from 'echarts';
//import * as d3 from 'd3';
import "./d3.min.js";
import { SpiderChartCard } from "@/api/navigator/spiderChartCard";
import { ElButton } from 'element-plus'

export default {
    name: 'radar-chartCard',
    components: {
        ElButton,
    },
    props: {
        params: Object,
        timeParams: Object,
        timeModel: String,
    },
    data() {
        return {

        };
    },
    mounted() {
        if(this.timeModel === 'GPT4')
            this.initChartGPT4();
        else if(this.timeModel === 'Mixtral')
            this.initChartMixtral();
        else if(this.timeModel === 'Kimi')
            this.initChartKimi();
        else if(this.timeModel === 'llama3')
            this.initChartLlama3();
        else if(this.timeModel === 'Deepseek')
            this.initChartDeepseek();
        else
            this.initChartClaude();
    },
    methods: {
        initChartMixtral() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#00A0B0"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大长度", "随机采样", "beam搜索", "beam组数", "返回条数", "重复惩罚值", "最大新词数", "多样性惩罚", "生成长度惩罚"];
            let axname = ["temperature", "top_p", "top_k", "max_length", "do_sample", "num_beams", "num_beam_groups", "num_return_sequences", "repetition_penalty", "max_new_tokens", "diversity_penalty", "length_penalty"];
            let a_model = [0.1, 0.95, 15, 512, 1, 1, 1, 1, 1.5, 256, 1.1, 0];
            let i = 0;
            Object.keys(this.timeParams).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.timeParams[key];
            });

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

            SpiderChartCard("#spiderChartCard", axes, [a_model_convert], chartOptions, this.timeModel);
        },
        initChartGPT4() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#EDC951"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "n"];
            let a_model = [0.1, 0.95, 0.0, 0.0, 1024, 1];
            let i = 0;
            Object.keys(this.timeParams).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.timeParams[key];
            });

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

            SpiderChartCard("#spiderChartCard", axes, [a_model_convert], chartOptions, this.timeModel);
        },
        initChartKimi() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#E4007F"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数", "返回条数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens", "n"];
            let a_model = [0.1, 0.95, 1.0, 1.0, 1024, 1];
            let i = 0;
            Object.keys(this.timeParams).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.timeParams[key];
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

            SpiderChartCard("#spiderChartCard", axes, [a_model_convert], chartOptions, this.timeModel);
        },
        initChartLlama3() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens"];
            let a_model = [0.1, 0.95, 1.0, 1.0, 1024];
            let i = 0;
            Object.keys(this.timeParams).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.timeParams[key];
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

            SpiderChartCard("#spiderChartCard", axes, [a_model_convert], chartOptions, this.timeModel);
        },
        initChartClaude() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#20D5E2"])
            };

            let axes = ["温度", "top_p采样", "top_k采样", "最大词数"];
            let axname = ["temperature", "top_p", "top_k", "max_tokens"];
            let a_model = [0.1, 0.95, 30, 1024];
            let i = 0;
            Object.keys(this.timeParams).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.timeParams[key];
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

            SpiderChartCard("#spiderChartCard", axes, [a_model_convert], chartOptions, this.timeModel);
        },
        initChartDeepseek() {
            let chartOptions = {
                maxValue: 1.0,
                levels: 5,
                color: d3.scale.ordinal().range(["#40A46D"])
            };

            let axes = ["温度", "top_p采样", "频率惩罚", "存在惩罚", "最大词数"];
            let axname = ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens"];
            let a_model = [0.1, 0.95, 1.0, 1.0, 1024];
            let i = 0;
            Object.keys(this.timeParams).forEach(key => {
                i = axname.indexOf(key);
                a_model[i] = this.timeParams[key];
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

            SpiderChartCard("#spiderChartCard", axes, [a_model_convert], chartOptions, this.timeModel);
        },
    }
};
</script>

<!-- 这里需要SCSS 而不是普通的 CSS，增加了变量、嵌套、混合、函数等功能 -->
<style lang="scss" scoped>

</style>