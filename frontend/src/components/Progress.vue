<!-- Progress.vue -->
<template>
    <el-progress :percentage="percentage" :color="color"></el-progress>
</template>
  
<script>
import { ElProgress } from 'element-plus';

export default {
    components: {
        ElProgress
    },
    props: {
        percentage: {
            type: Number,
            default: 0
        },
        color: {
            type: String,
            default: '#409eff'
        }
    }
};
</script>