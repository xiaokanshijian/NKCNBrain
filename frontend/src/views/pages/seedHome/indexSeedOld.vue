<template>
    <el-container height="50vh">
        <el-header>
            <MainNav>
            </MainNav>
        </el-header>
        <div class="seed-menu">
            <button class="menu-btn" @click="lookupClicked">阅览</button>
            <button class="menu-btn" @click="amplifyClicked">放大</button>
        </div>
        <el-main>
            <div class="seed-main">
                <component :is="currentComponent"></component>
            </div>
        </el-main>
    </el-container>
</template>
<script>
import MainNav from "@/views/mainNav.vue"
import Lookup from "@/views/pages/seedHome/lookup.vue"
import Amplify from "@/views/pages/seedHome/amplify.vue"

export default {
    name: "SeedHome",
    components: {
        MainNav,
        Lookup,
        Amplify
    },
    data() {
        return {
            currentComponent: "lookup"
        };
    },
    methods: {
        lookupClicked() {
            this.currentComponent = "lookup";
        },
        amplifyClicked() {
            this.currentComponent = "amplify";
        }
    }
}
</script>
<style scoped lang="scss">
.el-header {
    padding: 0;
    height: 5vh;
}

.el-main {
    display: flex;
    flex-direction: row;
    padding: 0;
}

.el-main::-webkit-scrollbar {
    display: none;
}


.seed-menu {
    position: absolute;
    top: 0;
    left: 100px;
    height: 5vh;
    background-color: #fff;
}

.menu-btn {
    border: none;
    background: none;
    width: 6vw;
    height: 5vh;
    background-color: #fff;
    font-family: Arial, Helvetica, sans-serif;
    transition: 0.5s ease;
    cursor: pointer;
    font-size: 20px;
    user-select: none;
    padding: 4px;
    border-left: 1px solid #000;
    top: 0;

    &:hover {
        background-color: #e6e3e3;
        box-shadow: 0 1px 1px 0;
        transform: scale(1.1);
    }
}

.seed-main {
    width: 100vw;
    background-color: rgb(228, 241, 244);
}
</style>