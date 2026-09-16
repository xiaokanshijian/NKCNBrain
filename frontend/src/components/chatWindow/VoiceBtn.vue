<template>
    <div class="sound-sonic_wave">
        <div class="middle-btn">
            <div class="circle" @click="toggleWaveAnimation"></div>
            <div class="wave w1"></div>
            <div class="wave w2"></div>
        </div>
    </div>
</template>
<script>
export default {
    data() {
        return {
            buttontext: '',
        }
    },
    methods: {
        toggleWaveAnimation() {
            var wave1 = document.querySelector('.w1');
            wave1.classList.toggle('active');
            var wave2 = document.querySelector('.w2');
            wave2.classList.toggle('active');
        }
    }
}
</script>
<style scoped>
.sound-sonic_wave {
    width: 100%;
    height: 100%;
}

.middle-btn {
    position: relative;
    width: 100%;
    height: 100%;
}

.wave {
    position: absolute;
    top: calc((100% - 60px)/2);
    left: calc((100% - 60px)/2);
    width: 60px;
    height: 60px;
    border-radius: 50%;
    background-attachment: fixed;
    background-position: center center;
}

.circle {
    position: absolute;
    top: 50%;
    left: 50%;
    width: 100px;
    height: 100px;
    background-color: red;
    border-radius: 50%;
    transform: translate(-50%, -50%);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 2em;
    font-weight: 1000;
    z-index: 4;
}

.w1 {
    z-index: 2;
    border: 1px solid red;
    background-size: auto 106%;
    /* animation: wave 1s infinite; */
    animation: none;
}

.w2 {
    z-index: 3;
    border: 1px solid red;
    /* animation: wave 1s .2s infinite; */
    animation: none;
}

.w1.active {
    animation: wave 1s infinite;
}

.w2.active {
    animation: wave 1s .2s infinite;
}

@keyframes wave {
    0% {
        top: calc((100% - 60px)/2);
        left: calc((100% - 60px)/2);
        width: 60px;
        height: 60px;
    }

    100% {
        top: calc((100% - 200px)/2);
        left: calc((100% - 200px)/2);
        width: 200px;
        height: 200px;
        opacity: 0.4;
    }
}
</style>
