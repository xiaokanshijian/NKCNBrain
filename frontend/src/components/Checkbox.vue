<template>
    <div class="checkbox">
        <input type="checkbox" :id="id" :value="value" v-model="checked" @change="$emit('input', $event.target.checked)" />
        <label :for="id">{{ label }}</label>
    </div>
</template>
  
<script>
export default {
    name: 'Checkbox',
    props: {
        value: {
            type: Boolean,
            default: false,
        },
        id: {
            type: String,
            default: () => `checkbox-${Math.random().toString(36).substr(2, 9)}`,
        }, label: { type: String, default: '', },
    }, computed: {
        checked: {
            get() { return this.value; }, set(newValue) {
                this.$emit('change', newValue);
            },
        },
    },
};
</script>
  
<style scoped>
.checkbox input[type="checkbox"] {
    /* 样式设置 */
}

.checkbox label {
    /* 样式设置 */
}
</style>