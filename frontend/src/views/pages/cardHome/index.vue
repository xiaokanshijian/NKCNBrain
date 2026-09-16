<template>
  <div class="cardHome">
    <div class="cardLeft">

      <div class="user-file">
        <span class="title-text">文档列表</span>
        <div class="file-list-wrapper">
          <FileList @FileNameListFromFileList="handleFileList"></FileList>
        </div>
      </div>
    </div>
    <div class="cardRight">
      <div class="content">
        <CardGrid></CardGrid>
      </div>
    </div>
  </div>
</template>

<script>
import FileList from "@/components/fileWindow/FileList.vue"
import CardGrid from "@/components/cardWindow/CardGrid.vue"

export default {
  name: "App",    // 组件名称，可选，调试用
  components: {    // 所依赖的子组件，于是可以在template里面使用它们
    FileList,
    CardGrid,
  },
  data() {        // 组件的数据对象，可以用this访问和修改
    return {
      pcCurrent: "",
      showChatWindow: false,
      chatWindowInfo: {},
    };
  },
  methods: {
    handleFileList(data) {
      this.$emit('FileNameListFromCardHome', data);  // 子组件emit
    }
  }
};
</script>

<style lang="scss" scoped>
.cardHome {

  display: flex;
  height: 629.88px;

  .cardLeft {
    width: 280px;

    .title {
      color: #fff;
      padding-left: 10px;
    }

    .user-file {
      margin-top: 20px;

      .title-text {
        padding-left: 10px;
        color: rgb(176, 178, 189);
      }

      .file-list-wrapper {
        padding-left: 10px;
        height: 65vh;
        margin-top: 10px;
        overflow: hidden;
        overflow-y: scroll;
        box-sizing: border-box;

        &::-webkit-scrollbar {
          width: 0;
          /* Safari,Chrome 隐藏滚动条 */
          height: 0;
          /* Safari,Chrome 隐藏滚动条 */
          display: none;
          /* 移动端、pad 上Safari，Chrome，隐藏滚动条 */
        }
      }
    }
  }

  .cardRight {
    height: 90vh;
    flex: 1;
    padding-right: 30px;
    margin: 20px;

    .showIcon {
      position: absolute;
      top: calc(50% - 150px);
      /*垂直居中 */
      left: calc(50% - 50px);

      /*水平居中 */
      .icon-snapchat {
        width: 300px;
        height: 300px;
        font-size: 300px;
        // color: rgb(28, 30, 44);
      }
    }
  }
}
</style>