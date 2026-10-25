<template>
  <!-- <router-view /> -->

  <!-- <router-view v-slot="{ Component }">
    <keep-alive>
      <component :is="Component" v-if="$route.meta.keepAlive"/>
    </keep-alive>
    <component :is="Component" v-if="!$route.meta.keepAlive"/>
  </router-view> -->

  <router-view v-slot="{ Component }">
    <keep-alive>
      <component 
        :is="Component" 
        v-if="$route.meta.keepAlive &&
         ($route.query.from === 'live' ||
          ($route.query.from === 'main' && $route.query.to === 'home') ||
          ($route.query.from === 'login' && $route.query.to === 'home'))"
        :key="$route.query.bookId"
      />
    </keep-alive>
    <component 
      :is="Component" 
      v-if="!$route.meta.keepAlive ||
       ($route.query.from !== 'live' &&
        ($route.query.from !== 'main' || $route.query.to !== 'home') &&
        ($route.query.from !== 'login' || $route.query.to !== 'home'))"
    />
  </router-view>
</template>


<script>
import Main from '@/views/mainPage.vue';
import { user_exit } from '@/api/user';
import { logoutSession } from '@/api/authSession';
import { logoutBeforeNavigation } from '@/utils/authNavigation';

export default {
  name: 'App',
  components: {
    Main
  },
  created() {
    // 注册导航守卫
    this.$router.beforeEach(this.beforeRouteChange);
    this.$router.afterEach((to) => {
      setTimeout(() => {
        if (Object.keys(to.query).length > 0) {
          // 使用 window.history 直接修改 URL 而不触发新的导航
          const url = window.location.pathname;
          window.history.replaceState({}, '', url);
        }
      }, 10); // 延迟0.01秒执行 
    });
  },
  destroyed() {
    // 取消注册导航守卫，避免内存泄漏
    this.$router.beforeEach(null);
  },
  computed: {
    cachedPages() {
      return this.$router.options.routes
        .filter(route => route.meta && route.meta.keepAlive)
        .map(route => route.name);
    }
  },
  methods: {
    // 导航守卫：路由切换前
    async beforeRouteChange(to, from, next) {
      try {
        await logoutBeforeNavigation(to, from, logoutSession, localStorage);
      } catch (error) {
        this.$message.error('退出登录失败，请重试');
        next(false);
        return;
      }
      // 获取目标路由的路径
      const toPath = to.path;
      // 判断目标路由是否为指定路由
      if (toPath === '/main') {
        // 如果是指定路由，则应用样式和脚本
        this.applyStyleAndScript();
      } else {
        // 如果不是指定路由，则移除样式和脚本
        // this.removeStyleAndScript();
        this.removeAppliedStyle();
      }

      // 判断用户是否退出本子，可能是1.叉掉浏览器；2.关闭标签页；3.右上角按钮退出本子到个人页；4.浏览器后退按钮
      if ((from.path.includes('/main') && to.path !== '/live' && to.path !== '/seed') || ((from.path === '/live' || from.path === '/seed') && to.path === '/home')){
        console.log("退出到：", to.path)
        if (localStorage.getItem('intervalId')) {
          const intervalId = localStorage.getItem('intervalId');
          clearInterval(Number(intervalId));
          localStorage.removeItem('intervalId');
          // 获取一个足够大的数字，确保覆盖所有可能的定时器ID
          const interval_id = window.setInterval(()=>{}, 9999);
          for (let i = 1; i <= interval_id; i++) {
            window.clearInterval(i);
          }
          console.log("清理content上传2min计时器")
        }
        
        let formData = new FormData();
        if(localStorage.getItem('userId') === localStorage.getItem('realName'))
          formData.append('username', localStorage.getItem('exitJustNow'));
        else
          formData.append('username', localStorage.getItem('userId'));
        user_exit(formData).then(data => {
          if(data['error_num'] === 0) {
            console.log("用户退出本子已在后端记录")
          } else {
            console.log("用户退出本子未能在后端记录")
          }
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
      }
      // 继续路由导航
      next();
    },
    // 应用样式和脚本
    applyStyleAndScript() {
      // 添加样式
      const style = document.createElement('style');
      style.id = 'main-route-style'; // 添加id以便识别
      style.textContent = `
        /* style标签内容 */

        .iconfont {
          font-family: "iconfont" !important;
          font-style: normal;
          font-size: 25px;
          vertical-align: middle;
          color: rgb(117, 120, 137);
          transition: .3s;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;
        }

        * {
          padding: 0;
          margin: 0;
        }

        #app {
          width: 100vw;
          height: 100vh;
          background-color: rgb(151, 157, 167);
        }
      `;
      document.head.appendChild(style);
      // 添加脚本
      // const script = document.createElement('script');
      // script.textContent = `
      //   /* script标签内容 */
      //   import Main from '@/views/mainPage.vue'

      //   export default {
      //     name: 'App',
      //     components: {
      //       Main
      //     }
      //   }
      // `;
      // document.body.appendChild(script);
    },
    // 移除之前应用的样式
    removeAppliedStyle() {
      // 通过id找到并移除之前添加的style标签
      const styleElement = document.getElementById('main-route-style');
      if (styleElement) {
        styleElement.parentNode.removeChild(styleElement);
      }
    },
    // 移除样式和脚本
    removeStyleAndScript() {
      // 移除样式
      const style = document.querySelector('style');
      if (style) {
        style.remove();
      }
      // 移除脚本
      const script = document.querySelector('script');
      if (script) {
        script.remove();
      }
    },
  },
};
</script>

<style lang="scss">
@import url(./assets/font/iconfont.css);
/* 此处留空，样式将在 applyStyleAndScript 方法中动态添加，这样避免所有 <router-view/> 加载的页面都使用此处的样式，不和原本页面设计冲突 */
</style>



<!-- <script>
import Main from '@/views/mainPage.vue'

export default {
  name: 'App',
  components: {
    Main
  }
}
</script>


<style lang="scss">
@import url(./assets/font/iconfont.css);

.iconfont {
  font-family: "iconfont" !important;
  font-style: normal;
  font-size: 25px;
  vertical-align: middle;
  color: rgb(117, 120, 137);
  transition: .3s;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

* {
  padding: 0;
  margin: 0;
}

#app {
  width: 100vw;
  height: 100vh;
  background-color: rgb(151, 157, 167);
}
</style>  -->