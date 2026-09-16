<template>
  <div class="card-text-reader">
    <header class="reader-header">
      <h1 class="reader-title">{{ title }}</h1>
      <div class="reader-toolbar">
        <button type="button" class="reader-btn" @click="speakTextBegin">从头开始朗读</button>
        <button type="button" class="reader-btn" @click="stopSpeech">停止朗读</button>
      </div>
      <p class="reader-hint">提示：双击正文可从该位置开始朗读</p>
    </header>
    <main class="reader-body">
      <div v-if="imageUrl" class="reader-image-wrap">
        <img
          class="reader-image"
          :src="imageUrl"
          alt="卡片配图"
          title="双击可全屏放大"
          @dblclick="openImageFullscreen"
        />
      </div>
      <AnswerParser
        v-if="content"
        :answer="content"
        @startReading="startFromIndex"
        @doubleClickOver="doubleClickOver"
      />
      <p v-else class="reader-empty">暂无内容</p>
    </main>
  </div>
</template>

<script>
import AnswerParser from '@/components/chatWindow/AnswerParser.vue';

export default {
  name: 'CardTextReader',
  components: { AnswerParser },
  data() {
    return {
      title: '卡片内容',
      content: '',
      imageUrl: '',
      storageKey: '',
      selectedIndex: 0,
      doubleClick: false,
      isSpeaking: false,
    };
  },
  mounted() {
    document.title = this.title;
    this.loadFromStorage();
  },
  beforeUnmount() {
    this.stopSpeech();
    if (this.storageKey) {
      try {
        sessionStorage.removeItem(this.storageKey);
      } catch (e) {
        /* ignore */
      }
    }
  },
  methods: {
    loadFromStorage() {
      const key = String(this.$route.query.key || '').trim();
      if (!key) {
        this.title = '卡片内容';
        this.content = '';
        this.imageUrl = '';
        return;
      }
      this.storageKey = key;
      try {
        const raw = sessionStorage.getItem(key);
        if (!raw) return;
        const data = JSON.parse(raw);
        this.title = data.title || '卡片内容';
        this.content = data.content || '';
        this.imageUrl = data.imageUrl || '';
        document.title = this.title;
      } catch (e) {
        console.error('[CardTextReader] load failed', e);
      }
    },
    openImageFullscreen() {
      if (!this.imageUrl) return;
      const w = window.open('', '_blank');
      if (!w) return;
      const srcEsc = String(this.imageUrl).replace(/"/g, '&quot;');
      const script = "(function(){var s=1,tx=0,ty=0,min=0.2,max=5,step=0.15,el=document.getElementById('fsImg'),wrap=document.getElementById('fsWrap'),down=null;" +
        "function apply(){el.style.transform='translate('+tx+'px,'+ty+'px) scale('+s+')';}" +
        "wrap.addEventListener('wheel',function(e){e.preventDefault();var px=e.clientX,py=e.clientY,r=el.getBoundingClientRect();" +
        "var sNew=e.deltaY>0?Math.max(min,s-step):Math.min(max,s+step);" +
        "tx=(px-r.left)*(1-sNew/s)+tx*sNew/s;ty=(py-r.top)*(1-sNew/s)+ty*sNew/s;s=sNew;apply();},{passive:false});" +
        "wrap.addEventListener('mousedown',function(e){if(e.button===0)down={startX:e.clientX,startY:e.clientY,startTx:tx,startTy:ty};});" +
        "wrap.addEventListener('mousemove',function(e){if(down!==null){tx=down.startTx+(e.clientX-down.startX);ty=down.startTy+(e.clientY-down.startY);apply();}});" +
        "wrap.addEventListener('mouseup',function(){down=null;});wrap.addEventListener('mouseleave',function(){down=null;});" +
        "apply();})();";
      const scriptCloseTag = '</scr' + 'ipt>';
      w.document.write(
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>卡片图片</title>' +
        '<style>body{margin:0;background:#1a1a1a;display:flex;align-items:center;justify-content:center;min-height:100vh;overflow:hidden;cursor:grab;}' +
        'body:active{cursor:grabbing;}#fsWrap{position:relative;display:flex;align-items:center;justify-content:center;width:100%;height:100%;overflow:hidden;}' +
        '#fsImg{max-width:100vw;max-height:100vh;width:auto;height:auto;object-fit:contain;transform-origin:0 0;transition:none;user-select:none;pointer-events:none;}</style></head>' +
        '<body><div id="fsWrap"><img id="fsImg" src="' + srcEsc + '"/></div><script>' + script + scriptCloseTag + '</body></html>'
      );
      w.document.close();
    },
    startFromIndex(index) {
      this.selectedIndex = index;
      this.doubleClick = true;
      this.speakText();
    },
    doubleClickOver() {
      this.doubleClick = false;
    },
    speakTextBegin() {
      this.stopSpeech();
      const utterance = new SpeechSynthesisUtterance(this.content);
      window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },
    speakText() {
      this.stopSpeech();
      const utterance = new SpeechSynthesisUtterance(this.content.slice(this.selectedIndex));
      window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },
    stopSpeech() {
      if (this.isSpeaking) {
        window.speechSynthesis.cancel();
        this.isSpeaking = false;
      }
    },
  },
};
</script>

<style scoped>
.card-text-reader {
  min-height: 100vh;
  background: #f5f7fa;
  color: #303133;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.reader-header {
  max-width: 960px;
  margin: 0 auto;
  padding: 28px 32px 12px;
}

.reader-title {
  margin: 0 0 16px;
  font-size: 28px;
  line-height: 1.35;
  font-weight: 600;
}

.reader-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}

.reader-btn {
  padding: 8px 16px;
  font-size: 15px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  cursor: pointer;
}

.reader-btn:hover {
  background: #ecf5ff;
  border-color: #b3d8ff;
  color: #409eff;
}

.reader-hint {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.reader-body {
  max-width: 960px;
  margin: 0 auto;
  padding: 12px 32px 48px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  min-height: calc(100vh - 180px);
}

.reader-image-wrap {
  margin: 0 0 24px;
  text-align: center;
}

.reader-image {
  max-width: 100%;
  width: auto;
  max-height: 72vh;
  height: auto;
  object-fit: contain;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  cursor: zoom-in;
  background: #fafafa;
}

.reader-empty {
  color: #909399;
  font-size: 18px;
}

/* 比卡片内默认字号更大，便于大窗口阅读 */
.card-text-reader :deep(.markdown-text) {
  font-size: 20px;
  line-height: 1.75;
}

.card-text-reader :deep(.original-code-block pre) {
  font-size: 16px;
  line-height: 1.6;
}

.card-text-reader :deep(.copy-button) {
  font-size: 14px;
}
</style>
