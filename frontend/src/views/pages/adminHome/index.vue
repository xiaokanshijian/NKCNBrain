<template>
    <el-container height="50vh">
        <el-header>
            <MainNav>
            </MainNav>
        </el-header>
        <el-main>
            <div class="admin-left">
                <AdminLeft @changeFineTune="handleChangeFineTune" @chageModel="getCurModelName"></AdminLeft>
            </div>
            <div class="admin-middle">
                <AdminMiddle :changeFineTuneModel="changeFineTuneModel"></AdminMiddle>
            </div>
            <div class="admin-right">
                <AdminRight :curModelName="curModelName"></AdminRight>
            </div>
        </el-main>
    </el-container>
</template>
<script>
import MainNav from "@/views/mainNav.vue"
import AdminLeft from "@/views/pages/adminHome/adminLeft.vue"
import AdminMiddle from "@/views/pages/adminHome/adminMiddle.vue"
import AdminRight from "@/views/pages/adminHome/adminRight.vue"

export default {
    name: "Admin",
    components: {
        MainNav,
        AdminLeft,
        AdminRight,
        AdminMiddle,
    },
    data() {
        return {
            changeFineTuneModel: false,
            curModelName: '',
        };
    },
    methods: {
        handleChangeFineTune() {
            this.changeFineTuneModel = true
        },
        getCurModelName(name) {
            this.curModelName=name;
        },
    }
}
</script>
<style scoped>
.el-header {
    padding: 0;
    height: 5vh;
}

.el-main {
    display: flex;
    flex-direction: row;
    padding: 0;
    height: 95vh;
}

.admin-left {
    width: 30%;
    height: 100%;
    background-color: #517bb1;
    transition: 0.4s ease;

    &:hover {
        width: 60%;
    }

    &:hover .admin-middle {
        width: 20%;
        filter: blur(10px);
    }

    &:hover .admin-right {
        width: 20%;
        filter: blur(10px);
    }

}

.admin-middle {
    width: 40%;
    height: 100%;
    background-color: rgb(182, 76, 66);
    transition: 0.4s ease;

    &:hover {
        width: 60%;
    }

    &:hover .admin-left {
        width: 20%;
        filter: blur(10px);
    }

    &:hover .admin-right {
        width: 20%;
        filter: blur(10px);
    }
}

.admin-right {
    width: 30%;
    height: 100%;
    background-color: #517bb1;
    transition: 0.4s ease;

    &:hover {
        width: 60%;
    }

    &:hover .admin-left {
        width: 20%;
        filter: blur(10px);
    }

    &:hover .admin-middle {
        width: 20%;
        filter: blur(10px);
    }
}
</style>