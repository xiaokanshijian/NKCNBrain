import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/theme-chalk/index.css'
import App from './App.vue'
import router from './router'
import redirectManager from './config/redirectConfig'

// 全局跳转检查
// 检查是否需要跳转到配置的服务器
redirectManager.checkAndRedirect().then(needRedirect => {
    if (!needRedirect) {
        // 如果不需要跳转，则正常初始化 Vue 应用
        const app = createApp(App)
    
        // 使用 app.use() 方法注册 Element Plus
        app.use(ElementPlus)
    
        // 使用 app.use() 方法注册 Vue Router
        app.use(router)
    
        app.mount('#app')
    }
    // 如果需要跳转，checkAndRedirect 已经执行了跳转，不需要初始化应用
}).catch(error => {
    console.error('[Main] 跳转检查失败，正常初始化应用:', error);
    // 如果跳转检查失败，仍然正常初始化应用
    const app = createApp(App)
    app.use(ElementPlus)
    app.use(router)
    app.mount('#app')
})

const debounce = (fn, delay) => {
let timer
    return (...args) => {
    if (timer) {
        clearTimeout(timer)
    }
    timer = setTimeout(() => {
        fn(...args)
    }, delay)
    }
}
const _ResizeObserver = window.ResizeObserver;
window.ResizeObserver = class ResizeObserver extends _ResizeObserver{
    constructor(callback) {
    callback = debounce(callback, 200);
    super(callback);
    }
}