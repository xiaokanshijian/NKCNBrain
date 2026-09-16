// import Vue from 'vue'
// import VueRouter from 'vue-router'

// Vue.use(VueRouter)

// import Home from '../views/homePage.vue'
// import Main from '../views/mainPage.vue'
import { createRouter, createWebHistory } from "vue-router";


const routes = [
    {
        path: '/',
        component: () => import('../views/login.vue'),
    },
    {
        path: '/adminhome',
        name: 'adminhome',
        component: () => import('../views/pages/mainHome/adminIndex.vue')
    },
    // NOTE: 25-05-27新增meta
    {
        path: '/home',
        name: 'home',
        component: () => import('../views/pages/mainHome/index.vue'),
        meta: { keepAlive: true }
    },
    {
        path: '/main',
        component: () => import('../views/mainPage.vue'),
        meta: { keepAlive: true }
    },
    {
        path: '/chat',
        name: 'chat',
        component: () => import('../views/pages/chatHome/index.vue')
    },
    {
        path: '/card',
        name: 'card',
        component: () => import('../views/pages/cardHome/index.vue')
    },
    {
        path: '/admin',
        name: 'admin',
        component: () => import('../views/pages/adminHome/index.vue')
    },
    {
        path: '/seed',
        name: 'seed',
        component: () => import('../views/pages/seedHome/index.vue')
    },
    {
        path: '/card-text-reader',
        name: 'cardTextReader',
        component: () => import('../views/CardTextReader.vue'),
    },
    {
        path: '/live',
        name: 'live',
        component: () => import('../views/livePage.vue')
    },
    {
        path: '/simple',
        name: 'simple',
        component: () => import('../views/simplePage.vue')
    },
    {
        path: '/minimal',
        name: 'minimal',
        component: () => import('../views/minimalPage.vue')
    },
    {
        path: '/unicast',
        name: 'unicast',
        component: () => import('../views/unicastPage.vue')
    },
]

// const router = new VueRouter({
//     mode: 'history',
//     routes
// })

const router = new createRouter({
    history: createWebHistory(),
    routes
})

export default router
