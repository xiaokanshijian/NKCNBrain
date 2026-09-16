<template>
    <div class="card-top-right2">
        <div class="card-top-right2-button" :class="{ 'checked': checked }" @click="onCheckboxChange"></div>
    </div>
    <div style="width: 100%; height: 100%;" id="radar-chart"></div>
</template>

<script>
import * as echarts from 'echarts';
export default {
    name: 'radar-chart',
    data() {
        return {
            paramsIndex: 0,
            modelName: 'GPT-4',
            checked: false,
            paramClassTmp: '精确型',
        };
    },
    props: {
        paramsClass: String,
        activeModel: String,
        params: Object,
    },
    watch: {
        paramsClass(newVal, oldVal) {
            if (newVal !== oldVal) {
                this.paramClassTmp = newVal;
                this.handleModels(this.modelName);
                const selected = {
                    '精确型': false,
                    '平衡型': false,
                    '创造型': false
                };
                selected[this.paramsClass] = true;
                this.option.legend.selected = selected;
                this.$nextTick(() => { 
                    let vm = this;
                    vm.myChart && vm.myChart.setOption(vm.option);
                });
            }
        },
        activeModel(newVal, oldVal) {
            this.modelName = newVal
            this.handleModels(newVal)
        },
        params: {
            handler(newVal, oldVal) {
                // 这里的代码将在 params 对象内部的任何属性变化时被调用
                this.handlehandChangeParams(newVal)
            },
            deep: true,  // 设置 deep 为 true 来启用深度监听
            // immediate: true  // 如果你也想在挂载时立即触发
        },
    },
    mounted() {
        this.initOption();
        this.$nextTick(() => { // 这里的 $nextTick() 方法是为了在下次 DOM 更新循环结束之后执行延迟回调。也就是延迟渲染图表避免一些渲染问题
            this.ready();
        });
    },
    methods: {
        ready() {
            let vm = this;
            let dom = document.getElementById('radar-chart');
            console.log("dom加载完毕")

            vm.myChart = echarts.init(dom);
            vm.myChart && vm.myChart.setOption(vm.option);

            // 监听点击事件
            vm.myChart.on('click', (params) => {
                // 检查是否点击的是雷达图的指标名称
                // if (params.componentType === 'radar' && params.name) {
                //     this.handleIndicatorClick(params.name);
                // }
                // 检查点击的是否是标题
                if (params.componentType === 'title') {
                    console.log("点击了图表标题")
                    this.$emit('titleClicked', params);  // 发射一个自定义事件给父组件
                }
            });
        },
        // 初始化图表配置
        initOption() {
            let vm = this;
            vm.option = {
                title: {
                    text: '超参数蜘蛛图',
                    textStyle: {
                        color: '#556B2F' // 这里设置标题文字的颜色为银色
                    },
                    selectedMode: true
                },
                tooltip: {},
                legend: {
                    data: ['精确型', '平衡型', '创造型'],
                    textStyle: {
                        color: '#FFA500' // 这里设置选中图例文字的颜色为橙色
                    },
                    selected: {
                        '精确型': true,  // 默认精确型
                        '平衡型': false,
                        '创造型': false
                    },
                    // selectedMode: false // 禁止通过图例选择或切换系列
                },
                radar: {
                    // shape: 'circle',
                    name: {
                        textStyle: {
                            color: '#fff',
                            backgroundColor: '#999',
                            borderRadius: 3,
                            padding: [3, 5]
                        }
                    },
                    indicator: [
                        { name: '温度', max: 3, min: 0.05 }, 
                        { name: 'top_p采样', max: 0.95, min: 0.05 }, 
                    ],
                    //隐藏轴线
                    // axisLine: {
                    //     show: false
                    // },
                    // //隐藏分层
                    // splitArea: {
                    //     show: false,
                    // },
                    //线设置为透明
                    splitLine: {
                        lineStyle: {
                            color: "rgba(255, 255, 255, 0)"//不透明度为0
                        }
                    },
                },
                series: [{
                    // name: '预算 vs 开销',
                    type: 'radar',
                    // areaStyle: {normal: {}},
                    data: [
                        {value: [0.1, 0.95], name: '精确型'}, 
                        {value: [0.6, 0.95], name: '平衡型'},
                        {value: [1.8, 0.95], name: '创造型'}
                    ],
                }],
                // 添加 dataRange 组件，允许拖拽选择数值范围
                // dataRange: {
                //     show: true,
                //     orient: 'horizontal',
                //     // 自定义手柄（滑块）的样式
                //     handleIcon: 'path://M0,0 L12,0 M0,0 L6,6 M6,6 L12,0',
                //     handleSize: '120%',
                //     // 拖拽事件
                //     handleStyle: {
                //         color: '#fff',
                //         shadowBlur: 10,
                //         shadowColor: 'rgba(0, 0, 0, 0.6)',
                //     },
                // }
            };
        },
        handleIndicatorClick(indicatorName) {
            const indicatorIndex = {
                '温度': 1,
                'top_p采样': 2,
                'top_k采样': 3,
                '最大生成长度': 4,
                'beam搜索': 5,
                '随机采样': 6,
                'beam组数': 7,
                '返回条数': 8,
                '重复惩罚值': 9,
                '最大新词数': 10,
                '多样性惩罚': 11,
                '生成长度惩罚': 12
            };

            // 如果点击的是已知指标，更新 paramsIndex
            if (indicatorName in indicatorIndex) {
                this.paramsIndex = indicatorIndex[indicatorName];
                console.log(this.paramsIndex);
                this.$emit('showParam', this.paramsIndex);
            }
        },
        handleModels(newVal) {
            if(this.paramClassTmp === '手动调') {
                this.handlehandChangeParams(this.params)
            } else {
                if(newVal === 'GPT-4') {
                    this.initOption();
                    let vm = this;
                    // 可改指标仅温度和top_p
                    vm.option.radar.indicator = [
                            { name: '温度', max: 3, min: 0.05 }, 
                            { name: 'top_p采样', max: 0.95, min: 0.05 }, 
                        ];
                    // 得到图例数据
                    vm.option.series[0].data = [
                            {value: [0.1, 0.95], name: '精确型'}, 
                            {value: [0.6, 0.95], name: '平衡型'},
                            {value: [1.8, 0.95], name: '创造型'}
                        ];
                    const selected = {
                        '精确型': false,
                        '平衡型': false,
                        '创造型': false
                    };
                    selected[this.paramsClass] = true;
                    vm.option.legend.selected = selected;
                    this.$nextTick(() => { 
                        vm.myChart && vm.myChart.setOption(vm.option);
                    });
                } else {
                    this.initOption();
                    let vm = this;
                    // 可改指标仅温度和top_p
                    vm.option.radar.indicator = [
                            { name: '温度', max: 3, min: 0.05 }, 
                            { name: 'top_p采样', max: 0.95, min: 0.05 }, 
                            { name: 'top_k采样', max: 100, min: 10 }, 
                            { name: '最大生成长度', max: 1024, min: 20 }, 
                            { name: 'beam搜索', max: 20, min: 1 }, 
                            { name: '随机采样', max: 1, min: 0 },
                            { name: 'beam组数', max: 20, min: 1 }, 
                            { name: '返回条数', max: 3, min: 1 }, 
                            { name: '重复惩罚值', max: 5, min: 0 }, 
                            { name: '最大新词数', max: 1024, min: 128 }, 
                            { name: '多样性惩罚', max: 2, min: -2 }, 
                            { name: '生成长度惩罚', max: 2, min: -2 },
                        ];
                    // 得到图例数据
                    vm.option.series[0].data = [
                            {value: [0.1, 0.95, 15, 128, 1, 1, 1, 1, 0.5, 128, 1.1, 0], name: '精确型'}, 
                            {value: [0.6, 0.95, 25, 256, 1, 1, 1, 1, 1, 256, 1.1, 1], name: '平衡型'},
                            {value: [1.8, 0.95, 50, 512, 1, 1, 1, 1, 1.5, 512, 1.1, 2], name: '创造型'}
                        ];
                    const selected = {
                        '精确型': false,
                        '平衡型': false,
                        '创造型': false
                    };
                    selected[this.paramsClass] = true;
                    vm.option.legend.selected = selected;
                    this.$nextTick(() => { 
                        vm.myChart && vm.myChart.setOption(vm.option);
                    });
                }
            }
        },
        onCheckboxChange() {
            this.checked = !this.checked;
            console.log("改变就是好事");
            if (this.checked === true) {
                this.$emit('handChangeParams');
            }
            
        },
        areObjectsEqual(obj1, obj2) {
            const keys1 = Object.keys(obj1);
            const keys2 = Object.keys(obj2);

            if (keys1.length !== keys2.length) {
                console.log("个数不一致")
                return false;
            }

            // 检查所有键和值是否相同
            for (let key of keys1) {
                if (obj1[key] !== obj2[key]) {
                    console.log("值不一致: ",obj1[key],obj2[key])
                    return false; // 如果有不同，立即返回 false
                }
            }
            return true;
        },
        handlehandChangeParams(newVal) {
            console.log('Params改变了:', newVal);
            const classJingMix = { value1: 0.1,value2: 0.95,value3: 15,value4: 128,value5: 1,value6: 1,value7: 1,value8: 1,value9: 0.5,value10: 128,value11: 1.1,value12: 0 };
            const classPingMix = { value1: 0.6,value2: 0.95,value3: 25,value4: 256,value5: 1,value6: 1,value7: 1,value8: 1,value9: 1,value10: 256,value11: 1.1,value12: 1 };
            const classChuangMix = { value1: 1.8,value2: 0.95,value3: 50,value4: 512,value5: 1,value6: 1,value7: 1,value8: 1,value9: 1.5,value10: 512,value11: 1.1,value12: 2 };
            const classJingGPT = { value1: 0.1,value2: 0.95 };
            const classPingGPT = { value1: 0.6,value2: 0.95 };
            const classChuangGPT = { value1: 1.8,value2: 0.95 };
            const input = { value1: newVal.value1, value2: newVal.value2 };
            if(this.modelName === 'GPT-4' && !(this.areObjectsEqual(classJingGPT, input)) && !(this.areObjectsEqual(classPingGPT, input)) && !(this.areObjectsEqual(classChuangGPT, input))) {
                console.log('Params手动改变了');
                this.paramClassTmp = '手动调';
                this.initOption();
                let vm = this;
                // 可改指标仅温度和top_p
                vm.option.radar.indicator = [
                        { name: '温度', max: 3, min: 0.05 }, 
                        { name: 'top_p采样', max: 0.95, min: 0.05 }, 
                    ];
                // 得到图例数据
                vm.option.series[0].data = [
                        {value: [newVal.value1, newVal.value2], name: '手动调'}
                    ];
                const selected = {
                    '手动调': true
                };
                vm.option.legend.selected = selected;
                vm.option.legend.data = ['手动调'];
                this.$nextTick(() => { 
                    vm.myChart && vm.myChart.setOption(vm.option);
                });
            } 
            if(this.modelName === 'Mixtral' && !(this.areObjectsEqual(classJingMix, newVal)) && !(this.areObjectsEqual(classPingMix, newVal)) && !(this.areObjectsEqual(classChuangMix, newVal))) {
                console.log('Params手动改变了');
                this.paramClassTmp = '手动调';
                this.initOption();
                let vm = this;
                // 可改指标仅温度和top_p
                vm.option.radar.indicator = [
                        { name: '温度', max: 3, min: 0.05 }, 
                        { name: 'top_p采样', max: 0.95, min: 0.05 }, 
                        { name: 'top_k采样', max: 100, min: 10 }, 
                        { name: '最大生成长度', max: 1024, min: 20 }, 
                        { name: 'beam搜索', max: 20, min: 1 }, 
                        { name: '随机采样', max: 1, min: 0 },
                        { name: 'beam组数', max: 20, min: 1 }, 
                        { name: '返回条数', max: 3, min: 1 }, 
                        { name: '重复惩罚值', max: 5, min: 0 }, 
                        { name: '最大新词数', max: 1024, min: 128 }, 
                        { name: '多样性惩罚', max: 2, min: -2 }, 
                        { name: '生成长度惩罚', max: 2, min: -2 },
                    ];
                // 得到图例数据
                vm.option.series[0].data = [
                        {value: [newVal.value1, newVal.value2, newVal.value3, newVal.value4, newVal.value5, newVal.value6, newVal.value7, newVal.value8, newVal.value9, newVal.value10, newVal.value11, newVal.value12 ], name: '手动调'}, 
                    ];
                const selected = {
                    '手动调': true
                };
                vm.option.legend.selected = selected;
                vm.option.legend.data = ['手动调'];
                this.$nextTick(() => { 
                    vm.myChart && vm.myChart.setOption(vm.option);
                });
            }
        }
    }
};
</script>

<style scoped>
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
</style>