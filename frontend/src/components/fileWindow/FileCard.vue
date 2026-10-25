<template>
  <div class="file-card" :class="getFileCardClasses()" :style="getFileCardStyle()" ref="filecard">
    <!-- 添加半自动进度指示器 -->
    <!-- <div v-if="automationStatus" class="automation-indicator" :class="automationStatus">
      <i v-if="automationStatus === 'running'" class="el-icon-loading"></i>
      <i v-else-if="automationStatus === 'success'" class="el-icon-check"></i>
      <i v-else-if="automationStatus === 'failed'" class="el-icon-close" @click="retryAutomation"></i>
    </div> -->
    
    <!-- 添加半自动化启动按钮 -->
    <!-- <el-button 
      v-if="isAutomationReady" 
      @click="startAutomation" 
      size="mini" 
      type="primary"
      class="auto-btn">
      自动后台
    </el-button> -->

    <!-- 半自动化进度指示器 -->
    <div 
      v-if="canAutomate"
      class="automation-progress"
      @click="handleAutomationClick"
      @dblclick="handleAutomationDoubleClick"
      :title="getAutomationTooltip">

      <!-- 人工记录状态 - 红色圆圈 -->
      <svg v-if="isCurFileRecording" width="20" height="20" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15" fill="none" stroke="#F56C6C" stroke-width="3"></circle>
        <circle cx="18" cy="18" r="6" fill="#F56C6C"></circle>
      </svg>
      
      <!-- 未开始状态 - 灰色圆圈 -->
      <svg v-if="!automationStatus && !isCurFileRecording" width="20" height="20" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15" fill="none" stroke="#4D4F53" stroke-width="3"></circle>
        <text x="18" y="23" text-anchor="middle" font-size="16" font-weight="bold" fill="#6B6E75">待</text>
      </svg>
      
      <!-- 运行中 - 绿色进度扇形 -->
      <svg v-else-if="automationStatus === 'running' && !isCurFileRecording" width="20" height="20" viewBox="0 0 36 36" class="rotating">
        <circle cx="18" cy="18" r="15" fill="none" stroke="#e6e6e6" stroke-width="3"></circle>
        <!-- 进度环 -->
        <circle 
          cx="18" 
          cy="18" 
          r="15" 
          fill="none" 
          stroke="#67C23A" 
          stroke-width="3"
          stroke-dasharray="94.2"
          :stroke-dashoffset="progressOffset"
          transform="rotate(-90 18 18)">
        </circle>
        <!-- 进度扇形 -->
        <path 
          :d="progressSectorPath" 
          fill="#67C23A" 
          fill-opacity="0.4">
        </path>
      </svg>
      
      <!-- 成功 - 绿色对勾 -->
      <svg v-else-if="automationStatus === 'success' && !isCurFileRecording" width="20" height="20" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15" fill="none" stroke="#67C23A" stroke-width="3"></circle>
        <path d="M10 18L16 24L26 12" fill="none" stroke="#67C23A" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
      </svg>
      
      <!-- 失败 - 红色叉号 -->
      <svg v-else-if="automationStatus === 'failed' && !isCurFileRecording" width="20" height="20" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r="15" fill="none" stroke="#F56C6C" stroke-width="3"></circle>
        <path d="M12 12L24 24M24 12L12 24" stroke="#F56C6C" stroke-width="3" stroke-linecap="round"></path>
      </svg>
    </div>

    <i class="file-manage" @click="filemanage" ref="selects"></i>
    <div class="manage-select" v-if="showSelectsChecked">
      <select v-model="leftSelect">
        <option value="0">获取全文</option>
        <option value="1">从头截取</option>
        <option value="2">均匀截取</option>
      </select>
      <select v-model="rightSelect">
        <option value="0">获取全文</option>
        <option value="1">从头截取</option>
        <option value="2">均匀截取</option>
        <option value="3">相关搜索</option>
      </select>
    </div>
    <img src="@/assets/img/fileImg/unknowfile.png" alt="" v-if="fileType == 0" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/word.png" alt="" v-else-if="fileType == 1" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/excel.png" alt="" v-else-if="fileType == 2" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/ppt.png" alt="" v-else-if="fileType == 3" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/pdf.png" alt="" v-else-if="fileType == 4" @click="showFileDialog" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/zpi.png" alt="" v-else-if="fileType == 5" @click="showFileDialog" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/txt.png" alt="" v-else-if="fileType == 6" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/png.png" alt="" v-else-if="fileType == 7" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/jpg.png" alt="" v-else-if="fileType == 8" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/excel.png" alt="" v-else-if="fileType == 9" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/excel.png" alt="" v-else-if="fileType == 10" @contextmenu="hideContextMenu"/>
    <img src="@/assets/img/fileImg/audio.png" alt="" v-else-if="fileType == 11" @contextmenu="hideContextMenu"/>
    <!-- <div class="word" @click="showFileDialog" @mouseenter="showConfidenceTooltip = true" @mouseleave="showConfidenceTooltip = false" style="position: relative;">
      <span :title="file.name">{{ file.name || '未知' }}</span>
      <span>{{ file.size }}</span>

      <div v-if="showConfidenceTooltip && documentConfidence > 0" class="confidence-tooltip">
        <div><strong>{{ file.name }}</strong></div>
        <div style="margin-top: 5px;">📊 文档置信度: {{ documentConfidence.toFixed(1) }}/5.0 {{ getDocConfidenceLevel(documentConfidence) }}</div>
      </div>
    </div> -->
    <div class="word" @click="showFileDialog">
      <span 
        @mouseenter="handleMouseEnter" 
        @mouseleave="handleMouseLeave"
        ref="fileNameSpan">
        {{ file.name || '未知' }}
      </span>
      <span>{{ file.size }}</span>
      <div
        v-if="skillStatusLabel"
        class="skill-status-badge"
        :class="skillStatusClass"
        :title="skillStatusTitle"
        @click.stop="onSkillStatusClick"
      >{{ skillStatusLabel }}</div>
    </div>
    
    <!-- 文档置信度悬浮框 - 移到外部 -->
    <div v-if="showConfidenceTooltip" class="confidence-tooltip" :style="tooltipStyle">
      <div><strong>{{ file.name }}</strong></div>
      <div v-if="documentConfidence > 0" style="margin-top: 5px;">
        📊 文档置信度: {{ documentConfidence.toFixed(1) }}/5.0 {{ getDocConfidenceLevel(documentConfidence) }}
      </div>
    </div>

    <div class="file-checkbox" :class="{ 'checked': checked }" @click="onCheckboxChange"></div>

    <!-- 🔥 文档类型颜色显示图标（右上角） -->
    <div v-if="split !== 0" class="file-type-indicator" :style="getFileTypeIndicatorStyle()" :title="isBaseFile ? '场景基础文档' : '本子增量文档'"></div>
    <div v-if="isHomeworkPdf" class="homework-badge" :title="homeworkBadgeTitle">{{ homeworkBadgeText }}</div>
  </div>
  <!-- <div class="file-dialog" 
    <div class="file-dialog-header">
      <h2>{{ file.name }}</h2>
      <div class="close" @click=
    </div>
    <div class="file-dialog-body">
      <p>文件大小: {{ file.size }} </p>
      <p>文件类型: {{ file.suffix }}</p>
    </div>
</div>-->
  <div class="context-menu" v-show="showContextMenu" :style="contextMenuStyle">
    <div class="menu-item" v-if="isImageFileType" @click="openBatchSketchRDialog">批量图自动逐张：原草图作 R 层复现图</div>
    <div class="menu-item" @click="deleteFile">删除文件</div>
    <div class="menu-item" @click="editDocumentFourColor">修改主辅四色属性</div>
    <div class="menu-item" v-if="String(file.name || '').toLowerCase().endsWith('.pdf')" @click="openMaterialSettings">材料设置</div>
    <div class="menu-item" v-if="isSkillRelatedFile" :class="{ disabled: skillStatusPending }" @click="openSkillEnableDialog">
      {{ skillStatusPending ? 'Skill 生成中…' : '禁用/启用对应 Skill' }}
    </div>
    <div class="menu-item" v-if="isSkillRelatedFile" :class="{ disabled: skillStatusPending }" @click="openSkillEditDialog">
      {{ skillStatusPending ? 'Skill 生成中…' : '查看/编辑对应 Skill' }}
    </div>
    <div class="menu-item" v-if="canRetrySkill" @click="retrySkillGeneration">重试生成 Skill</div>
  </div>

  <!-- Skill 启用/禁用 -->
  <div v-if="showSkillEnableDialog" class="skill-dlg-overlay" @click.self="showSkillEnableDialog=false">
    <div class="skill-dlg skill-dlg--enable" @click.stop>
      <div class="skill-dlg-header">
        <div>
          <h3>禁用 / 启用 Skill</h3>
          <p class="skill-dlg-sub">来源：{{ file.name }}</p>
        </div>
        <button class="skill-dlg-close" type="button" @click="showSkillEnableDialog=false">×</button>
      </div>
      <div class="skill-dlg-body">
        <div v-if="!skillForFileList.length" class="skill-empty">暂无关联 Skill（可能仍在生成中）</div>
        <div v-else class="skill-enable-grid">
          <div
            v-for="s in skillForFileList"
            :key="s.name"
            class="skill-enable-card"
            :class="{ 'is-off': !s.enabled }"
          >
            <div class="skill-enable-card-top">
              <div class="skill-enable-card-title">
                <span>{{ s.title || s.name }}</span>
                <span v-if="s.is_hub" class="skill-hub-badge">Hub</span>
              </div>
              <el-switch v-model="s.enabled" @change="(v)=>toggleSkillEnabled(s, v)" />
            </div>
            <div class="skill-enable-card-name">{{ s.name }}</div>
            <div
              class="skill-md-snippet"
              v-html="renderSkillMarkdown(s.description || '（无描述）')"
            ></div>
          </div>
        </div>
      </div>
      <div class="skill-dlg-footer">
        <button class="skill-btn skill-btn--ghost" type="button" @click="showSkillEnableDialog=false">关闭</button>
      </div>
    </div>
  </div>

  <!-- Skill 编辑（Markdown 预览 / 源码编辑） -->
  <div v-if="showSkillEditDialog" class="skill-dlg-overlay" @click.self="showSkillEditDialog=false">
    <div class="skill-dlg skill-dlg--edit" @click.stop>
      <div class="skill-dlg-header">
        <div>
          <h3>查看 / 编辑 Skill</h3>
          <p class="skill-dlg-sub">{{ editingSkillName || '未选择' }}</p>
        </div>
        <button class="skill-dlg-close" type="button" @click="showSkillEditDialog=false">×</button>
      </div>
      <div class="skill-dlg-toolbar">
        <select
          v-if="skillEditCandidates.length > 1"
          v-model="editingSkillName"
          class="skill-select"
          @change="loadSkillRaw"
        >
          <option v-for="s in skillEditCandidates" :key="s.name" :value="s.name">
            {{ s.title || s.name }}
          </option>
        </select>
        <div class="skill-tabs">
          <button
            type="button"
            class="skill-tab"
            :class="{ active: skillEditMode === 'preview' }"
            @click="skillEditMode = 'preview'"
          >Markdown 预览</button>
          <button
            type="button"
            class="skill-tab"
            :class="{ active: skillEditMode === 'edit' }"
            @click="skillEditMode = 'edit'"
          >编辑源码</button>
        </div>
      </div>
      <div class="skill-dlg-body skill-dlg-body--edit">
        <div v-if="skillEditMode === 'preview'" class="skill-md-preview">
          <div v-if="skillEditFrontmatterMeta.length" class="skill-fm-box">
            <div class="skill-fm-title">Frontmatter</div>
            <div class="skill-fm-row" v-for="(row, i) in skillEditFrontmatterMeta" :key="i">
              <span class="skill-fm-key">{{ row.key }}</span>
              <span
                class="skill-fm-val"
                :class="{ 'is-description': row.key === 'description' }"
                v-html="formatSkillDescDisplay(row.value)"
              ></span>
            </div>
          </div>
          <div class="skill-md-body" v-html="skillEditPreviewHtml"></div>
        </div>
        <textarea
          v-else
          v-model="editingSkillRaw"
          class="skill-md-editor"
          spellcheck="false"
          placeholder="在此编辑完整 SKILL.md（含 YAML frontmatter）…"
          @input="onSkillEditRawInput"
        ></textarea>
      </div>
      <div class="skill-dlg-footer">
        <span class="skill-dlg-hint">{{ skillEditLineCount }} 行 · 保存写入完整 Markdown</span>
        <div class="skill-dlg-footer-actions">
          <button class="skill-btn skill-btn--ghost" type="button" @click="showSkillEditDialog=false">取消</button>
          <button class="skill-btn skill-btn--primary" type="button" @click="saveSkillRaw">保存</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Skill 包 ZIP 预览 -->
  <div v-if="showSkillPackDialog" class="skill-dlg-overlay" @click.self="showSkillPackDialog=false">
    <div class="skill-dlg skill-dlg--pack" @click.stop>
      <div class="skill-dlg-header">
        <div>
          <h3>Skill 包</h3>
          <p class="skill-dlg-sub">{{ file.name }} · {{ file.size || '' }}</p>
        </div>
        <button class="skill-dlg-close" type="button" @click="showSkillPackDialog=false">×</button>
      </div>
      <div class="skill-pack-stats" v-if="skillPackList.length">
        <span>共 {{ skillPackList.length }} 个 Skill</span>
        <span>已启用 {{ skillPackEnabledCount }}/{{ skillPackList.length }}</span>
        <span v-if="skillPackHubName">Hub：{{ skillPackHubName }}</span>
      </div>
      <div class="skill-dlg-body">
        <div v-if="skillPackLoading" class="skill-empty">正在加载 Skill 包内容…</div>
        <div v-else-if="!skillPackList.length" class="skill-empty">
          此 ZIP 尚未解析出 Skill（可能仍在导入，或不是有效 Skill 包）。可右键「查看/编辑对应 Skill」重试。
        </div>
        <div v-else class="skill-enable-grid">
          <div
            v-for="s in skillPackList"
            :key="s.name"
            class="skill-enable-card"
            :class="{ 'is-off': !s.enabled, 'is-hub': s.is_hub }"
          >
            <div class="skill-enable-card-top">
              <div class="skill-enable-card-title">
                <span>{{ s.title || s.name }}</span>
                <span v-if="s.is_hub" class="skill-hub-badge">Hub</span>
              </div>
              <el-switch v-model="s.enabled" @change="(v)=>toggleSkillEnabled(s, v)" />
            </div>
            <div class="skill-enable-card-name">{{ s.name }}</div>
            <div
              class="skill-md-snippet"
              v-html="renderSkillMarkdown(s.description || '（无描述）')"
            ></div>
            <div class="skill-pack-card-actions">
              <button class="skill-btn skill-btn--sm" type="button" @click="openEditFromPack(s)">查看 / 编辑 MD</button>
            </div>
          </div>
        </div>
      </div>
      <div class="skill-dlg-footer">
        <button class="skill-btn skill-btn--ghost" type="button" @click="showSkillPackDialog=false">关闭</button>
      </div>
    </div>
  </div>

  <!-- 🔥 文档四色属性编辑对话框 -->
  <div 
    v-if="showFourColorDialog"
    class="color-dmt-dialog-overlay"
    @click.self="closeFourColorDialog"
  >
    <div class="color-dmt-dialog" @click.stop>
      <div class="dialog-header">
        <h3>修改文档四色属性</h3>
        <button class="dialog-close" @click="closeFourColorDialog">×</button>
      </div>
      <div class="dialog-content">
        <!-- 主色选择 -->
        <div class="dialog-section">
          <div class="dialog-section-title">主色：</div>
          <div class="dialog-current">
            当前：<span :style="{ color: mainFourColor === 'R' ? '#dc143c' : mainFourColor === 'B' ? '#1e90ff' : mainFourColor === 'P' ? '#9370db' : mainFourColor === 'G' ? '#3cb371' : '#999', fontWeight: 'bold' }">
              {{ colorOptionNames[mainFourColor] || '未设置' }}
            </span>
          </div>
          <div class="dialog-options">
            <button
              v-for="option in colorOptions"
              :key="'main-' + option"
              class="dialog-option-btn"
              :class="{ 'selected': option === editingMainFourColor }"
              :style="{
                backgroundColor: option === 'R' ? '#dc143c' : option === 'B' ? '#1e90ff' : option === 'P' ? '#9370db' : option === 'G' ? '#3cb371' : '#ccc',
                color: 'white',
                border: option === editingMainFourColor ? '3px solid #333' : '1px solid #ddd'
              }"
              @click="editingMainFourColor = option"
            >
              {{ option }}: {{ colorOptionNames[option] }}
            </button>
            <button
              class="dialog-option-btn"
              :class="{ 'selected': editingMainFourColor === '' }"
              style="background-color: #ccc; color: white; border: 1px solid #ddd;"
              @click="editingMainFourColor = ''"
            >
              清除
            </button>
          </div>
        </div>
        
        <!-- 辅色选择 -->
        <div class="dialog-section" style="margin-top: 20px;">
          <div class="dialog-section-title">辅色：</div>
          <div class="dialog-current">
            当前：<span :style="{ color: secondaryFourColor === 'R' ? '#dc143c' : secondaryFourColor === 'B' ? '#1e90ff' : secondaryFourColor === 'P' ? '#9370db' : secondaryFourColor === 'G' ? '#3cb371' : '#999', fontWeight: 'bold' }">
              {{ colorOptionNames[secondaryFourColor] || '未设置' }}
            </span>
          </div>
          <div class="dialog-options">
            <button
              v-for="option in colorOptions"
              :key="'secondary-' + option"
              class="dialog-option-btn"
              :class="{ 'selected': option === editingSecondaryFourColor }"
              :style="{
                backgroundColor: option === 'R' ? '#dc143c' : option === 'B' ? '#1e90ff' : option === 'P' ? '#9370db' : option === 'G' ? '#3cb371' : '#ccc',
                color: 'white',
                border: option === editingSecondaryFourColor ? '3px solid #333' : '1px solid #ddd'
              }"
              @click="editingSecondaryFourColor = option"
            >
              {{ option }}: {{ colorOptionNames[option] }}
            </button>
            <button
              class="dialog-option-btn"
              :class="{ 'selected': editingSecondaryFourColor === '' }"
              style="background-color: #ccc; color: white; border: 1px solid #ddd;"
              @click="editingSecondaryFourColor = ''"
            >
              清除
            </button>
          </div>
        </div>
        
        <!-- 确认和取消按钮 -->
        <div class="dialog-actions">
          <button class="dialog-confirm-btn" @click="confirmFourColorEdit">确认</button>
          <button class="dialog-cancel-btn" @click="closeFourColorDialog">取消</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import base from "@/api";
import { get_file } from "@/api/card/get_card"
import { API_BASE_URL } from '@/config/apiConfig';
import { marked } from 'marked';

import { startAutomation, getAutomationStatus, stopAutomation, resetAutomation, getFileAutomationStatus, saveFileAutomationStatus } from "@/api/automation"

export default {
  // props: ["fileType", "file"],
  data() {
    return {
      // 半自动化新增
      clickTimer: null,  // 单击延时器
      clickDelay: 250,   // 延迟时间（毫秒）
      isCurFileRecording: false,
      automationStatus: null, // null, 'running', 'success', 'failed'
      taskId: null,
      currentStep: 0,
      totalSteps: 0,
      isAutomationReady: false, // 是否显示自动化按钮

      isBaseFile: this.checked,
      idx: 0,
      isChecked: this.checked, // 局部响应式数据，用于跟踪checked状态
      isFileDialogVisible: false,
      fileContent: "",
      showSelectsChecked: false,
      leftSelect: "2",  // 默认策略从"从头截取"改为"均匀截取"
      rightSelect: "3",

      showContextMenu: false,
      contextMenuStyle: {
        top: '0px',
        left: '0px'
      },

      showConfidenceTooltip: false,  // 是否显示置信度悬浮框
      documentConfidence: 0,  // 文档置信度评分
      
      // 🔥 四色属性编辑对话框
      showFourColorDialog: false,
      editingMainFourColor: '',
      editingSecondaryFourColor: '',
      colorOptions: ['R', 'B', 'P', 'G'],
      colorOptionNames: { 'R': '红色', 'B': '蓝色', 'P': '紫色', 'G': '绿色' },
      // Skill
      showSkillEnableDialog: false,
      showSkillEditDialog: false,
      showSkillPackDialog: false,
      skillForFileList: [],
      skillEditCandidates: [],
      skillPackList: [],
      skillPackLoading: false,
      editingSkillName: '',
      editingSkillRaw: '',
      skillEditMode: 'preview', // preview | edit
      editingSkillFrontmatter: null, // skill_get 解析后的 frontmatter（完整 description）
      skillEditRawDirty: false,
      skillEditRawBaseline: '',
      skillGenStatus: null, // null | 'pending' | true | false
      skillStatusPollTimer: null,
      skillNullPollCount: 0,
    }
  },
  props: {
    needWaitFile: Number,
    fileType: Number,
    file: Object,
    fileStatus: Number,
    index: Number,
    split: Number,
    isRecording: Boolean,
    updateFileCardState: Boolean,
    checked: {
      type: Boolean,
      required: false
    },
    mainFourColor: {
      type: String,
      default: ''
    },
    secondaryFourColor: {
      type: String,
      default: ''
    },
    dmtLevel: {
      type: String,
      default: ''
    },
    isHomeworkPdf: {
      type: Boolean,
      default: false
    },
    homeworkSubject: {
      type: String,
      default: 'unknown'
    },
    homeworkConfidence: {
      type: Number,
      default: 0
    },
    /** 由 FileList 传入，与勾选文档列表同步（NK2026 自动勾选「获取全文」依赖此项） */
    fileLeftSelect: {
      type: [String, Number],
      default: undefined,
    },
    fileRightSelect: {
      type: [String, Number],
      default: undefined,
    },
    default() {
      return {};
    },
  },
  watch: {
    fileLeftSelect: {
      immediate: true,
      handler(val) {
        if (val !== undefined && val !== null && val !== "") {
          this.leftSelect = String(val);
        }
      },
    },
    fileRightSelect: {
      immediate: true,
      handler(val) {
        if (val !== undefined && val !== null && val !== "") {
          this.rightSelect = String(val);
        }
      },
    },
    file() {
      // console.log(this.file);
    },
    checked(newValue) {
      this.isChecked = newValue;
    },
    leftSelect(newVal) {
      this.$emit('update:fileLeftSelection', this.index, newVal);
    },
    rightSelect(newVal) {
      this.$emit('update:fileRightSelection', this.index, newVal);
    },
    updateFileCardState(newVal) {
      console.log("新文件状态变化：", newVal, this.file.name)
      if (newVal === true) {
        if (this.canAutomate) {
          this.checkAutomationStatus();
        }
        setTimeout(() => {
          this.$emit("updateFileCardStateOver")
        }, 5000);  // 这个延迟要久一点好些，考虑到存在很多个文档的本子（例如群组批改半自动化的本子）
      }
    }
  },
  computed: {
    // 计算悬浮框位置
    tooltipStyle() {
      if (!this.$refs.fileNameSpan) return {};
      
      const rect = this.$refs.fileNameSpan.getBoundingClientRect();

      let topPosition = `${rect.top - 35}px`
      if(this.documentConfidence > 0) {
        topPosition = `${rect.top - 60}px`
      }

      return {
        position: 'fixed',
        top: topPosition,
        left: `${rect.left}px`,
        zIndex: 9999
      };
    },


    isImageFileType() {
      return this.fileType === 7 || this.fileType === 8;
    },
    isSkillRelatedFile() {
      const n = String(this.file?.name || '').toLowerCase();
      return n.endsWith('.pdf') || n.endsWith('.txt') || n.endsWith('.zip');
    },
    isDocSkillFile() {
      const n = String(this.file?.name || '').toLowerCase();
      return n.endsWith('.pdf') || n.endsWith('.txt');
    },
    skillStatusPending() {
      return this.isDocSkillFile && this.skillGenStatus === 'pending';
    },
    canRetrySkill() {
      return this.isDocSkillFile && this.skillGenStatus === false;
    },
    skillStatusLabel() {
      if (!this.isDocSkillFile) return '';
      if (this.skillGenStatus === 'pending') return 'Skill生成中';
      if (this.skillGenStatus === false) return 'Skill失败·点重试';
      return '';
    },
    skillStatusClass() {
      if (this.skillGenStatus === 'pending') return 'pending';
      if (this.skillGenStatus === false) return 'failed';
      return '';
    },
    skillStatusTitle() {
      if (this.skillGenStatus === 'pending') return '文档 Skill 正在后台生成';
      if (this.skillGenStatus === false) return 'Skill 生成失败，点击重试';
      return '';
    },
    skillEditLineCount() {
      const raw = this.editingSkillRaw || '';
      if (!raw) return 0;
      return raw.split('\n').length;
    },
    skillEditParsed() {
      const raw = this.editingSkillRaw || '';
      if (!raw.startsWith('---')) {
        return { frontmatterText: '', body: raw };
      }
      const end = raw.indexOf('\n---', 3);
      if (end < 0) {
        return { frontmatterText: '', body: raw };
      }
      return {
        frontmatterText: raw.slice(3, end).trim(),
        body: raw.slice(end + 4).replace(/^\r?\n/, ''),
      };
    },
    skillEditFrontmatterMeta() {
      // 优先用后端 yaml.safe_load 的结果（完整折叠 description）；源码被改过则本地重解析
      const apiFm = this.editingSkillFrontmatter;
      if (apiFm && typeof apiFm === 'object' && !this.skillEditRawDirty) {
        return this.formatFrontmatterRows(apiFm);
      }
      return this.parseFrontmatterRowsFromText(this.skillEditParsed.frontmatterText || '');
    },
    skillEditPreviewHtml() {
      return this.renderSkillMarkdown(this.skillEditParsed.body || '（正文为空）');
    },
    skillPackEnabledCount() {
      return (this.skillPackList || []).filter((s) => s.enabled).length;
    },
    skillPackHubName() {
      const hub = (this.skillPackList || []).find((s) => s.is_hub);
      return hub ? (hub.title || hub.name) : '';
    },

    // 计算进度百分比
    progressPercentage() {
      if (this.totalSteps === 0) return 0;
      return (this.currentStep / this.totalSteps) * 100;
    },
    
    // 计算进度环的偏移量
    progressOffset() {
      const circumference = 2 * Math.PI * 15; // 94.2
      return circumference - (circumference * this.progressPercentage / 100);
    },
    
    // 计算进度扇形路径
    progressSectorPath() {
      const angle = (this.progressPercentage / 100) * 2 * Math.PI;
      const x = 18 + 15 * Math.sin(angle);
      const y = 18 - 15 * Math.cos(angle);
      const largeArc = angle > Math.PI ? 1 : 0;
      
      if (this.progressPercentage === 0) return '';
      if (this.progressPercentage >= 100) {
        return 'M 18 18 L 18 3 A 15 15 0 1 1 17.99 3 Z';
      }
      
      return `M 18 18 L 18 3 A 15 15 0 ${largeArc} 1 ${x} ${y} Z`;
    },
    
    // 获取提示文本
    getAutomationTooltip() {
      if (!this.automationStatus) return '单击开始自动后台，双击进行涌现示范';
      if (this.automationStatus === 'running') {
        return `自动后台中，点击可终止: ${this.currentStep}/${this.totalSteps}`;
      }
      if (this.automationStatus === 'success') return '自动后台已完成，点击可重做';
      if (this.automationStatus === 'failed') return '自动后台失败/手动终止，点击选择：取消自动/继续自动/从头开始';
      return '';
    },

    canAutomate() {
      // 判断是否是学生报告文件
      // return this.file.name.includes('实验报告') || 
      //         this.file.name.includes('课设') ||
      //         this.file.name.includes('报告');
      return true;
    },

    homeworkSubjectLabel() {
      const labels = { math: '数学', chinese: '语文', english: '英语' };
      return labels[this.homeworkSubject] || '作业';
    },

    homeworkBadgeText() {
      return this.homeworkSubjectLabel === '作业' ? '作业' : `${this.homeworkSubjectLabel}作业`;
    },

    homeworkBadgeTitle() {
      const confidence = Number(this.homeworkConfidence || 0);
      const confidenceText = confidence > 0 ? `，置信度 ${(confidence * 100).toFixed(0)}%` : '';
      return `${this.homeworkBadgeText}${confidenceText}`;
    }
  },
  mounted() {
    // 半自动化：检查是否是学生报告文件
    // 检查是否显示自动化按钮
    if (this.canAutomate && localStorage.getItem('hasRecords') === 'true') {
        this.isAutomationReady = true;
    }

    // 检查自动化状态
    // if (this.canAutomate) {
    //   setTimeout(() => {
    //     this.checkAutomationStatus();
    //   }, 1000);
    // }

    // console.log(this.file);
    // console.log(this.fileType);
    this.isChecked = this.checked;
    // 挂载先于 props 传值开始执行，要获取到正确的值需要等一会
    setTimeout(() => {
      this.isBaseFile = this.checked;
    }, 1000);
    
    this.$emit('update:fileChecked', this.isChecked, this.index);

    this.$refs.selects.addEventListener('mouseenter', this.showSelects);
    this.$refs.filecard.addEventListener('mouseleave', this.hideSelects);

    this.$refs.filecard.addEventListener('contextmenu', this.handleContextMenu);
    // 点击其他地方时隐藏右键菜单
    document.addEventListener('click', this.hideContextMenu);

    setTimeout(() => {
      // 获取文档置信度
      this.fetchDocumentConfidence();
    }, 1000);

    if (this.isDocSkillFile) {
      this.skillNullPollCount = 0;
      this.refreshSkillStatus();
      this.skillStatusPollTimer = setInterval(() => {
        if (this.skillGenStatus === 'pending') {
          this.refreshSkillStatus();
        } else if (this.skillGenStatus == null && this.skillNullPollCount < 20) {
          // 等待旧本子后台补生成把状态写成 pending（约 80s 内）
          this.refreshSkillStatus();
        } else if (this.skillStatusPollTimer) {
          clearInterval(this.skillStatusPollTimer);
          this.skillStatusPollTimer = null;
        }
      }, 4000);
    }
  },
  beforeDestroy() {
    if (this.skillStatusPollTimer) {
      clearInterval(this.skillStatusPollTimer);
      this.skillStatusPollTimer = null;
    }
    this.$refs.selects.removeEventListener('mouseenter', this.showSelects);
    this.$refs.filecard.removeEventListener('mouseleave', this.hideSelects);

    document.removeEventListener('click', this.hideContextMenu);
    this.$refs.filecard.removeEventListener('contextmenu', this.handleContextMenu);
  },
  methods: {
    // 鼠标进入文件名
    handleMouseEnter() {
      this.showConfidenceTooltip = true;
    },
    
    // 鼠标离开文件名
    handleMouseLeave() {
      this.showConfidenceTooltip = false;
    },

    // 获取文档置信度等级文本
    getDocConfidenceLevel(score) {
      if (score >= 4.0) return '(高)';
      if (score >= 2.5) return '(中)';
      return '(低)';
    },
    
    // 从后端获取文档置信度
    async fetchDocumentConfidence() {
      try {
        const username = localStorage.getItem('userId');
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取

        const response = await fetch(`${BASE_URL}/api/get_document_confidence`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: username,
            filename: this.file.name
          })
        });
        
        if (response.ok) {
          const data = await response.json();
          console.log('[FileCard] ${this.file.name} 置信度:', data);
          if (data.confidence_score) {
            this.documentConfidence = data.confidence_score;
            // console.log(`[FileCard] ${this.file.name} 置信度: ${this.documentConfidence}`);
          }
        }
      } catch (error) {
        console.error('获取文档置信度失败:', error);
      }
    },


    // 半自动化新增
    checkAutomationStatus() {
      const formData = new FormData();
      formData.append('notebook_id', localStorage.getItem('userId'));
      formData.append('file_name', this.file.name);

      getFileAutomationStatus(formData).then(response => {
        if (response.status) {
          this.automationStatus = response.status;
          this.taskId = response.task_id;
          
          // 如果是运行中，继续轮询
          if (this.automationStatus === 'running') {
            this.pollStatus();
          }
        }
      });
    },

    saveAutomationStatus(status) {
      const formData = new FormData();
      formData.append('notebook_id', localStorage.getItem('userId'));
      formData.append('file_name', this.file.name);
      formData.append('status', status);
      formData.append('task_id', this.taskId || '');
      
      saveFileAutomationStatus(formData);
    },

    // retryAutomation() {
    //   if (this.automationStatus === 'failed' && this.taskId) {
    //     this.$confirm('是否从失败位置继续执行?', '提示', {
    //       confirmButtonText: '继续',
    //       cancelButtonText: '重新开始',
    //       type: 'warning'
    //     }).then(() => {
    //       // 从失败位置继续
    //       this.continueAutomation();
    //     }).catch(() => {
    //       // 重新开始
    //       this.startAutomation();
    //     });
    //   }
    // },
    
    // continueAutomation() {
    //   const formData = new FormData();
    //   formData.append('task_id', this.taskId);
    //   formData.append('action', 'continue');
      
    //   continueAutomation(formData).then(response => {
    //     this.automationStatus = 'running';
    //     this.pollStatus();
    //   });
    // },

    handleAutomationDoubleClick() {
      // 清除单击的延时器
      if (this.clickTimer) {
        clearTimeout(this.clickTimer);
        this.clickTimer = null;
      }

      if (this.isChecked === false) {
        this.onCheckboxChange()
      }

      // 获取父组件的recordMode状态
      let parentRecordMode = this.isRecording;
      if (parentRecordMode) {
        this.$emit('endRecordWithTarget')
        this.isCurFileRecording = false
      }

      if (!parentRecordMode && (!this.automationStatus || this.automationStatus === "failed")) {
        // 未在记录模式且未开始自动化，开始人工记录
        this.$emit('startRecordWithTarget', this.file.name);
        this.isCurFileRecording = true
        // this.isRecording = true;
      }
    },

    handleAutomationClick() {
      // 如果已有延时器，说明是双击的第二次点击，直接返回
      if (this.clickTimer) {
        return;
      }

      // 设置延时器，250ms后执行单击逻辑
      this.clickTimer = setTimeout(() => {
        this.clickTimer = null;
        
        // 以下是原有的单击逻辑，保持不变
        // 获取父组件的recordMode状态
        let parentRecordMode = this.isRecording;
        if (parentRecordMode) {
          this.$message.error('有文件正在涌现示范中！');
          return;
        }

        if (localStorage.getItem('hasRecords') === 'false') {
          this.$message.error('目前本子内暂无涌现示范记录！');
          return;
        }

        if (this.automationStatus === 'running') {
          // 运行中，点击终止
          this.$confirm('确定要终止自动化执行吗？', '提示', {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning'
          }).then(() => {
            this.stopAutomation();
          });
        } else if (!this.automationStatus || this.automationStatus === 'success') {
          // 未开始或已完成，点击开始
          this.startAutomation();
        } else if (this.automationStatus === 'failed') {
          // 失败状态，弹出选项对话框
          this.showAutomationOptionsDialog();
        } else {
          // this.$message.success('此文件自动成卡已完成过了');
          this.$message.error('未知状态！');
        }
      }, 250);
    },

    showAutomationOptionsDialog() {
      // 简化的三选项对话框
      const actions = [
        { text: '取消自动（回到"待"状态）', value: 'reset' },
        { text: '继续自动过程', value: 'continue' },
        { text: '从头开始自动', value: 'restart' }
      ];

      let message = '自动化任务失败/手动中止，请选择下一步操作：<br/><br/>';
      actions.forEach((action, index) => {
        message += `${index + 1}. ${action.text}<br/>`;
      });

      this.$confirm(message, '自动化任务失败/手动中止', {
        dangerouslyUseHTMLString: true,
        confirmButtonText: '继续自动过程',
        cancelButtonText: '其他选项',
        type: 'warning',
        customClass: 'automation-options-dialog'
      }).then(() => {
        // 继续自动过程
        this.continueAutomation();
      }).catch(() => {
        // 显示其他选项
        this.$confirm('请选择其他操作：', '选择操作', {
          confirmButtonText: '取消自动（回到"待"状态）',
          cancelButtonText: '从头开始自动',
          type: 'info'
        }).then(() => {
          // 取消自动（回到"待"状态）
          this.resetAutomationStatus();
        }).catch(() => {
          // 从头开始自动
          this.restartAutomation();
        });
      });
    },

    continueAutomation() {
      // 继续自动过程（从失败点恢复）
      this.startAutomation();
    },

    resetAutomationStatus() {
      // 重置自动化状态到"待"状态
      const formData = new FormData();
      formData.append('notebook_id', localStorage.getItem('userId'));
      formData.append('file_name', this.file.name);
      
      resetAutomation(formData).then(response => {
        if (response.error_num === 0) {
          this.automationStatus = null;  // 重置为待执行状态
          this.taskId = null;
          this.$message.success('已重置为待执行状态');
        } else {
          this.$message.error('重置失败: ' + response.msg);
        }
      }).catch(error => {
        this.$message.error('重置失败: ' + error.message);
      });
    },

    restartAutomation() {
      // 从头开始自动（强制重新开始）
      const formData = new FormData();
      formData.append('notebook_id', localStorage.getItem('userId'));
      formData.append('target_file', this.file.name);
      formData.append('restart_from_beginning', 'true');
      formData.append('current_user', localStorage.getItem('originRealName'));  // 🔥 传递当前登录用户
      formData.append('scene_name', localStorage.getItem('sceneName') || '');
      
      startAutomation(formData).then(response => {
        this.taskId = response.task_id;
        this.automationStatus = 'running';
        this.currentStep = 0;
        this.pollStatus();

        // 保存状态到数据库
        this.saveAutomationStatus('running');
        this.$message.success('已从头开始自动化');
      }).catch(error => {
        this.$message.error('启动失败: ' + error.message);
      });
    },

    stopAutomation() {
      const formData = new FormData();
      formData.append('task_id', this.taskId);
      
      stopAutomation(formData).then(response => {
        this.automationStatus = 'failed';
        this.$message.warning('自动化已终止');

        // 保存状态到数据库
        this.saveAutomationStatus('failed');
      });
    },

    startAutomation() {
      const formData = new FormData();
      formData.append('notebook_id', localStorage.getItem('userId'));
      formData.append('target_file', this.file.name);
      formData.append('current_user', localStorage.getItem('originRealName'));  // 🔥 传递当前登录用户
      formData.append('scene_name', localStorage.getItem('sceneName') || '');
      
      startAutomation(formData).then(response => {
        this.taskId = response.task_id;
        this.automationStatus = 'running';
        this.currentStep = 0;
        this.pollStatus();

        // 保存状态到数据库
        this.saveAutomationStatus('running');
      });
    },
    
    pollStatus() {
      const interval = setInterval(() => {
        getAutomationStatus(this.taskId).then(response => {
          this.automationStatus = response.status;
          this.currentStep = response.current_step;
          this.totalSteps = response.total_steps;
          
          if (response.status !== 'running') {
            clearInterval(interval);
            
            if (response.status === 'failed') {
              this.$message.error('自动化执行失败: ' + response.error_message);
              // 保存状态到数据库
              this.saveAutomationStatus('failed');
            } else {
              this.$message.success('自动化执行完成');
              this.$emit('reloadAutoCards')
              // 保存状态到数据库
              this.saveAutomationStatus('success');
            }
          }
        });
      }, 2000);
    },

    // 原有方法
    showSelects() {
      this.showSelectsChecked = true;
    },
    hideSelects() {
      this.showSelectsChecked = false;
    },
    filemanage() {
      this.showSelectsChecked = true;
    },
    onCheckboxChange() {
      this.isChecked = !this.isChecked; // 切换isChecked的值
      this.$emit('update:fileChecked', this.isChecked, this.index);
    },
    showFileDialog() {
      const name = String(this.file?.name || '').toLowerCase();
      if (name.endsWith('.zip')) {
        this.openSkillPackPreview();
        return;
      }
      this.isChecked = true; // 切换isChecked的值
      // 根据文件名获取文件内容
      this.$emit('update:fileChecked', this.isChecked, this.index);
      this.$emit('update:fileSummary', this.file.name);
      // if(this.needWaitFile === 0) {
      //   this.isChecked = true; // 切换isChecked的值
      //   // 根据文件名获取文件内容
      //   this.$emit('update:fileChecked', this.isChecked, this.index);
      //   this.$emit('update:fileSummary', this.file.name);
      // } else {
      //   this.$message.error("您还有文件在上传，请耐心等待，目前不可操作！");
      // }
    },

    handleContextMenu(event) {
      event.preventDefault();
      this.showContextMenu = true;
      this.contextMenuStyle = {
        top: `${event.clientY}px`,
        left: `${event.clientX}px`
      };
    },
    openBatchSketchRDialog() {
      this.showContextMenu = false;
      this.$emit('open-batch-sketch-r-dialog');
    },
    deleteFile() {
      this.showContextMenu = false;
      this.$emit('delete-file', this.index);
    },
    hideContextMenu() {
      this.showContextMenu = false;
    },
    openMaterialSettings() {
      this.hideContextMenu();
      this.$emit('material-settings', this.file.name);
    },

    renderSkillMarkdown(text) {
      const src = String(text || '').trim();
      if (!src) return '<p class="skill-md-empty">（无内容）</p>';
      try {
        marked.setOptions({ breaks: true, gfm: true });
        const html = typeof marked.parse === 'function' ? marked.parse(src) : marked(src);
        return html;
      } catch (e) {
        const escaped = src
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;');
        return `<pre>${escaped}</pre>`;
      }
    },

    async fetchSkillsForFile() {
      const username = localStorage.getItem('userId');
      const response = await fetch(`${API_BASE_URL}/api/skill_for_file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, filename: this.file.name }),
      });
      const data = await response.json();
      if (data.error_num !== 0) {
        this.$message.error(data.msg || '获取 Skill 失败');
        return [];
      }
      return data.skills || [];
    },

    async openSkillPackPreview() {
      this.isChecked = true;
      this.$emit('update:fileChecked', this.isChecked, this.index);
      this.skillPackLoading = true;
      this.skillPackList = [];
      this.showSkillPackDialog = true;
      try {
        this.skillPackList = await this.fetchSkillsForFile();
      } finally {
        this.skillPackLoading = false;
      }
    },

    async openEditFromPack(skill) {
      if (!skill || !skill.name) return;
      this.skillEditCandidates = this.skillPackList.length
        ? this.skillPackList.slice()
        : [{ name: skill.name, title: skill.title || skill.name }];
      this.editingSkillName = skill.name;
      this.skillEditMode = 'preview';
      this.showSkillEditDialog = true;
      await this.loadSkillRaw();
    },

    async openSkillEnableDialog() {
      this.showContextMenu = false;
      if (this.skillStatusPending) {
        this.$message.info('Skill 仍在生成中，请稍候');
        return;
      }
      this.skillForFileList = await this.fetchSkillsForFile();
      this.showSkillEnableDialog = true;
    },

    async openSkillEditDialog() {
      this.showContextMenu = false;
      if (this.skillStatusPending) {
        this.$message.info('Skill 仍在生成中，请稍候');
        return;
      }
      this.skillEditCandidates = await this.fetchSkillsForFile();
      if (!this.skillEditCandidates.length) {
        this.$message.info(this.skillGenStatus === false ? 'Skill 生成失败，可右键重试' : '暂无关联 Skill（可能仍在生成中）');
        return;
      }
      this.editingSkillName = this.skillEditCandidates[0].name;
      this.skillEditMode = 'preview';
      this.showSkillEditDialog = true;
      await this.loadSkillRaw();
    },

    async refreshSkillStatus() {
      if (!this.isDocSkillFile) return;
      try {
        const username = localStorage.getItem('userId');
        const response = await fetch(`${API_BASE_URL}/api/skill_status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username }),
        });
        const data = await response.json();
        const map = data.documentSkillStatus || {};
        const st = map[this.file.name];
        if (st === 'pending' || st === true || st === false) {
          this.skillGenStatus = st;
          this.skillNullPollCount = 0;
          if (st === true && this.skillStatusPollTimer) {
            clearInterval(this.skillStatusPollTimer);
            this.skillStatusPollTimer = null;
          }
          return;
        }
        // 无状态记录：偶尔查一次磁盘 Skill，避免每 4s 打 skill_for_file
        this.skillNullPollCount = (this.skillNullPollCount || 0) + 1;
        if (this.skillNullPollCount === 1 || this.skillNullPollCount % 5 === 0) {
          const skills = await this.fetchSkillsForFile();
          if (skills.length) {
            this.skillGenStatus = true;
            if (this.skillStatusPollTimer) {
              clearInterval(this.skillStatusPollTimer);
              this.skillStatusPollTimer = null;
            }
          }
        }
      } catch (e) {
        console.warn('[SkillStatus] 拉取失败', e);
      }
    },

    async onSkillStatusClick() {
      if (this.skillGenStatus === false) {
        await this.retrySkillGeneration();
      }
    },

    async retrySkillGeneration() {
      this.showContextMenu = false;
      if (!this.isDocSkillFile) return;
      try {
        const username = localStorage.getItem('userId');
        const response = await fetch(`${API_BASE_URL}/api/skill_regenerate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ username, filename: this.file.name }),
        });
        const data = await response.json();
        if (data.error_num === 0) {
          this.skillGenStatus = 'pending';
          this.$message.success('已重新开始生成 Skill');
          if (!this.skillStatusPollTimer) {
            this.skillStatusPollTimer = setInterval(() => {
              if (this.skillGenStatus === 'pending') {
                this.refreshSkillStatus();
              } else if (this.skillStatusPollTimer) {
                clearInterval(this.skillStatusPollTimer);
                this.skillStatusPollTimer = null;
              }
            }, 4000);
          }
        } else {
          this.$message.error(data.msg || '重试失败');
        }
      } catch (e) {
        this.$message.error('重试请求失败');
      }
    },

    async loadSkillRaw() {
      if (!this.editingSkillName) return;
      const username = localStorage.getItem('userId');
      const response = await fetch(`${API_BASE_URL}/api/skill_get`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, name: this.editingSkillName }),
      });
      const data = await response.json();
      if (data.error_num === 0) {
        const raw = data.raw || '';
        this.editingSkillRaw = raw;
        this.skillEditRawBaseline = raw;
        this.skillEditRawDirty = false;
        // 后端 yaml.safe_load 已正确合并折叠 description
        this.editingSkillFrontmatter = data.frontmatter || null;
      } else {
        this.$message.error(data.msg || '读取失败');
      }
    },

    onSkillEditRawInput() {
      this.skillEditRawDirty = this.editingSkillRaw !== this.skillEditRawBaseline;
    },

    formatFrontmatterRows(fm) {
      if (!fm || typeof fm !== 'object') return [];
      const prefer = ['name', 'description', 'title', 'version', 'license', 'agent_created'];
      const skip = new Set(['metadata', 'layers', 'compatibility', 'allowed-tools', 'allowed_tools']);
      const rows = [];
      const seen = new Set();
      const pushKey = (key) => {
        if (seen.has(key) || !(key in fm) || skip.has(key)) return;
        seen.add(key);
        const raw = fm[key];
        if (raw == null) return;
        if (typeof raw === 'object') return; // 嵌套对象不展示
        const value = String(raw).trim();
        if (!value) return;
        rows.push({ key, value });
      };
      prefer.forEach(pushKey);
      Object.keys(fm).forEach(pushKey);
      return rows;
    },

    formatSkillDescDisplay(text) {
      const src = String(text || '');
      if (!src) return '';
      const escaped = src
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      // Use when / NOT for 前换行并高亮（大小写不敏感）
      return escaped
        .replace(
          /\s*(Use\s+when)\b/gi,
          '<br><span class="skill-desc-mark">$1</span>'
        )
        .replace(
          /\s*(NOT\s+for)\b/gi,
          '<br><span class="skill-desc-mark">$1</span>'
        );
    },

    parseFrontmatterRowsFromText(text) {
      // 兼容 YAML 折叠纯量：description 首行后缩进续行（调试本子 fenquan-funeng / 文档 Skill 均为此格式）
      if (!text) return [];
      const skip = new Set(['metadata', 'layers', 'compatibility', 'allowed-tools', 'allowed_tools']);
      const lines = text.split(/\r?\n/);
      const rows = [];
      let i = 0;
      while (i < lines.length) {
        const line = lines[i];
        const m = line.match(/^([A-Za-z0-9_-]+)\s*:\s*(.*)$/);
        if (!m) {
          i++;
          continue;
        }
        const key = m[1];
        let value = (m[2] || '').trim();
        i++;

        if (skip.has(key)) {
          // 跳过嵌套块整段
          while (i < lines.length) {
            const next = lines[i];
            if (/^[A-Za-z0-9_-]+\s*:/.test(next)) break;
            i++;
          }
          continue;
        }

        if (value === '|' || value === '>') {
          const block = [];
          while (i < lines.length) {
            const next = lines[i];
            if (/^[A-Za-z0-9_-]+\s*:/.test(next)) break;
            if (/^\s*$/.test(next)) {
              block.push('');
              i++;
              continue;
            }
            if (!/^\s+/.test(next)) break;
            block.push(next.replace(/^\s+/, ''));
            i++;
          }
          value = block.join(value === '>' ? ' ' : '\n').replace(/[ \t]+\n/g, '\n').trim();
        } else if (
          (value.startsWith('"') && value.endsWith('"') && value.length >= 2) ||
          (value.startsWith("'") && value.endsWith("'") && value.length >= 2)
        ) {
          value = value.slice(1, -1);
        } else if (
          (value.startsWith('"') && !value.endsWith('"')) ||
          (value.startsWith("'") && !value.endsWith("'"))
        ) {
          const quote = value[0];
          const parts = [value.slice(1)];
          while (i < lines.length) {
            const next = lines[i];
            i++;
            const qi = next.indexOf(quote);
            if (qi >= 0) {
              parts.push(next.slice(0, qi));
              break;
            }
            parts.push(next.trim());
          }
          value = parts.join(' ').replace(/\s+/g, ' ').trim();
        } else if (value !== '') {
          // 折叠纯量续行：缩进行拼到 description
          const cont = [value];
          while (i < lines.length) {
            const next = lines[i];
            if (/^[A-Za-z0-9_-]+\s*:/.test(next)) break;
            if (/^\s*$/.test(next)) break;
            if (!/^\s+\S/.test(next)) break;
            cont.push(next.replace(/^\s+/, ''));
            i++;
          }
          value = cont.join(' ').replace(/\s+/g, ' ').trim();
        } else {
          // key: 后为空 → 嵌套块，跳过子行
          while (i < lines.length) {
            const next = lines[i];
            if (/^[A-Za-z0-9_-]+\s*:/.test(next)) break;
            if (/^\s*$/.test(next)) {
              i++;
              continue;
            }
            if (!/^\s+/.test(next) && !/^- /.test(next.trim())) break;
            i++;
          }
          continue;
        }

        if (!value) continue;
        rows.push({ key, value });
      }
      return rows;
    },

    async saveSkillRaw() {
      const username = localStorage.getItem('userId');
      const response = await fetch(`${API_BASE_URL}/api/skill_save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username,
          name: this.editingSkillName,
          raw: this.editingSkillRaw,
        }),
      });
      const data = await response.json();
      if (data.error_num === 0) {
        this.$message.success('Skill 已保存');
        this.skillEditRawBaseline = this.editingSkillRaw;
        this.skillEditRawDirty = false;
        this.showSkillEditDialog = false;
      } else {
        this.$message.error(data.msg || '保存失败');
      }
    },

    async toggleSkillEnabled(skill, enabled) {
      const username = localStorage.getItem('userId');
      const response = await fetch(`${API_BASE_URL}/api/skill_set_enabled`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username,
          names: [skill.name],
          enabled: !!enabled,
        }),
      });
      const data = await response.json();
      if (data.error_num === 0) {
        this.$message.success(enabled ? `已启用 ${skill.name}` : `已禁用 ${skill.name}`);
      } else {
        skill.enabled = !enabled;
        this.$message.error(data.msg || '更新失败');
      }
    },

    // 🔥 编辑文档四色属性
    editDocumentFourColor() {
      this.showContextMenu = false;
      // 初始化编辑值
      this.editingMainFourColor = this.mainFourColor || '';
      this.editingSecondaryFourColor = this.secondaryFourColor || '';
      this.showFourColorDialog = true;
    },
    
    // 🔥 关闭四色属性编辑对话框
    closeFourColorDialog() {
      this.showFourColorDialog = false;
      this.editingMainFourColor = '';
      this.editingSecondaryFourColor = '';
    },
    
    // 🔥 确认四色属性编辑
    async confirmFourColorEdit() {
      try {
        const username = localStorage.getItem('userId');
        // 尝试从父组件获取sceneName，如果没有则使用空字符串（后端会根据username自动查找）
        let sceneName = '';
        if (this.$parent && this.$parent.sceneName) {
          sceneName = this.$parent.sceneName;
        } else if (this.$parent && this.$parent.$parent && this.$parent.$parent.sceneName) {
          sceneName = this.$parent.$parent.sceneName;
        }
        
        const response = await fetch(`${API_BASE_URL}/api/update_document_four_color_dmt`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: username,
            filename: this.file.name,
            main_four_color: this.editingMainFourColor,
            secondary_four_color: this.editingSecondaryFourColor,
            scene_name: sceneName
          })
        });
        
        if (response.ok) {
          const data = await response.json();
          if (data.error_num === 0) {
            this.$message.success('文档四色属性更新成功');
            // 通知父组件更新
            this.$emit('document-four-color-updated', {
              filename: this.file.name,
              main_four_color: this.editingMainFourColor,
              secondary_four_color: this.editingSecondaryFourColor
            });
            this.closeFourColorDialog();
          } else {
            this.$message.error('更新失败: ' + data.msg);
          }
        } else {
          this.$message.error('更新失败: 网络错误');
        }
      } catch (error) {
        console.error('更新文档四色属性失败:', error);
        this.$message.error('更新失败: ' + error.message);
      }
    },

    // 判断是否有四色属性
    hasFourColor() {
      return !!(this.mainFourColor && this.mainFourColor.trim());
    },
    
    // 获取文件卡片样式类
    getFileCardClasses() {
      return {
        'file-card-notsplit': this.split === 0,
        'file-card-with-border': !this.hasFourColor() && this.split !== 0, // 无四色且split不为0时添加边框类
      };
    },
    
    // 获取文件卡片样式（动态背景色）
    getFileCardStyle() {
      // 如果split为0，不设置任何样式，让.file-card-notsplit样式生效
      if (this.split === 0) {
        return {};
      }

      // 如果有四色属性，使用四色作为背景
      if (this.hasFourColor()) {
        const colorMap = {
          'R': 'rgba(255, 160, 160, 0.6)',  // 红色：降低GB值(185→160)提高饱和度，稍微提高透明度
          'B': 'rgba(216, 233, 251, 1)',  // 蓝色：保持不变✓
          'P': 'rgba(180, 100, 200, 0.5)',  // 紫色：提高R(238→245)，降低B(238→230)，偏红紫
          'G': 'rgba(200, 235, 205, 0.9)'   // 绿色：保持不变✓
        };
        
        const mainColor = colorMap[this.mainFourColor] || 'rgba(204, 204, 204, 0.3)';
        const secondaryColor = this.secondaryFourColor ? (colorMap[this.secondaryFourColor] || mainColor) : mainColor;
        
        if (mainColor === secondaryColor) {
          return { background: mainColor };
        } else {
          // 主色大（约75%），辅色小（约25%）
          return {
            background: `linear-gradient(to right, ${mainColor} 0%, ${mainColor} 65%, ${secondaryColor} 35%, ${secondaryColor} 100%)`
          };
        }
      }
      
      // 如果没有四色属性，使用白色背景
      return { background: '#ffffff' };
    },
    
    // 获取右上角文档类型指示器样式
    getFileTypeIndicatorStyle() {
      // 基础文档用深蓝，增量文档用浅蓝
      const baseColor = '#6ea6e0';      // 原#8ebff7 → 加深约15%
      const incrementalColor = '#c5ddf4';  // 原#d8e9fb → 加深约10%
      const indicatorColor = this.isBaseFile ? baseColor : incrementalColor;
      
      return {
        background: indicatorColor
      };
    }
  }
};
</script>

<style lang="scss" scoped>
.file-card {
  position: relative;
  width: 100%;
  height: 85px;
  border-radius: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 6px;
  box-sizing: border-box;
  cursor: pointer;
  margin-top: 20px;
  transition: background-color 0.5s;

  // 无四色时添加黑色粗边框
  &.file-card-with-border {
    border: 3px solid #000000;
  }

  &:hover {
    background-color: rgb(234, 234, 234);
  }

  img {
    width: 60px;
    height: 60px;
  }

  .word {
    width: 60%;
    margin-left: 10px;
    overflow: hidden;

    span {
      width: 90%;
      display: inline-block;
      color: #000000;
    }

    span:first-child {
      font-size: 14px;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    span:last-child {
      font-size: 12px;
      color: rgb(44, 44, 44);
    }

    .skill-status-badge {
      display: inline-block;
      margin-top: 2px;
      padding: 1px 6px;
      border-radius: 3px;
      font-size: 11px;
      line-height: 1.4;
      width: auto;
      max-width: 90%;
      white-space: nowrap;
      &.pending {
        color: #8a6d3b;
        background: #fcf8e3;
      }
      &.failed {
        color: #a94442;
        background: #f2dede;
        cursor: pointer;
      }
      &.ready {
        color: #3c763d;
        background: #dff0d8;
      }
    }
  }
}

// .file-card-base 样式已移除，统一使用 .file-card 的动态样式




.file-card-notsplit {
  width: 100%;
  height: 85px;
  background-color: rgb(234, 234, 234);
  border-radius: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 6px;
  box-sizing: border-box;
  cursor: pointer;

  margin-top: 20px;
  transition: background-color 0.5s;
  pointer-events: none;

  &:hover {
    background-color: red;
  }

  img {
    width: 60px;
    height: 60px;
  }

  .word {
    width: 60%;
    margin-left: 10px;
    overflow: hidden;

    span {
      width: 90%;
      display: inline-block;
      color: #000000;
    }

    span:first-child {
      font-size: 14px;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
    }

    span:last-child {
      font-size: 12px;
      color: rgb(44, 44, 44);
    }
  }
}


.file-card-notsplit::after {
  content: "文件正在上传，不要点击，后果自负";
  position: absolute;
  bottom: 10px;
  left: 5vw;
  color: white;
  background-color: rgba(0, 0, 0, 0.7);
  padding: 5px;
  border-radius: 5px;
  opacity: 0;
  transition: opacity 0.3s;
  z-index: 9999;
}

.file-card:hover::after {
  opacity: 1;
}

.checkbox {
  position: relative;
  top: 12px;
  right: 0px;
}

.file-checkbox {
  cursor: pointer;
  width: 40px;
  /* 设置图片的宽度 */
  height: 40px;
  /* 设置图片的高度 */
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;

}

.file-checkbox.checked {
  background-image: url('@/assets/img/pin_blue.png');
}

.file-checkbox:not(.checked) {
  background-image: url('@/assets/img/pin_grey.png');
}



.file-manage {
  position: relative;
  background-image: url('@/assets/img/filewindow/manage.png');
  background-size: contain;
  background-repeat: no-repeat;
  display: inline-block;
  width: 20px;
  height: 25px;

  left: 0px;
  top: 0px;
  display: flex;
}


.file-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 1000;
  width: 90vw;
  height: 90vh;
  max-width: 100%;
}

.file-dialog .file-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.file-dialog h2 {
  margin: 0;
  font-size: 1.2em;
}

.file-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}

.file-dialog .close:hover {
  color: #333;
}

.file-dialog .file-dialog-body {
  margin-top: 10px;
}

.file-dialog p {
  margin: 5px 0;
}

::-webkit-scrollbar {
  width: 20px;
  height: 15px;
  background: rgb(255, 255, 255);
  border-radius: 10px;
}

::-webkit-scrollbar-thumb {
  background: #bec5ca;
  min-height: 50px;
  min-width: 50px;
  border-radius: 10px;
}

.manage-select {
  position: absolute;
  top: 4vh;
  left: 2vw;
}





.context-menu {
  position: fixed;
  background: white;
  border: 1px solid #ccc;
  border-radius: 4px;
  padding: 5px 0;
  min-width: 120px;
  z-index: 1000;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.menu-item {
  padding: 8px 16px;
  cursor: pointer;
  
  &:hover {
    background-color: #f5f5f5;
  }

  &.disabled {
    color: #aaa;
    cursor: not-allowed;
    &:hover {
      background-color: transparent;
    }
  }
}




/* 🔥 四色属性编辑对话框样式 */
.color-dmt-dialog-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10001;
}

.color-dmt-dialog {
  background: white;
  border-radius: 8px;
  padding: 20px;
  min-width: 400px;
  max-width: 500px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
}

.dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  border-bottom: 1px solid #eee;
  padding-bottom: 10px;
}

.dialog-header h3 {
  margin: 0;
  font-size: 18px;
}

.dialog-close {
  background: none;
  border: none;
  font-size: 24px;
  cursor: pointer;
  color: #999;
  padding: 0;
  width: 30px;
  height: 30px;
  line-height: 30px;
}

.dialog-close:hover {
  color: #333;
}

.dialog-content {
  margin-bottom: 20px;
}

.dialog-section {
  margin-bottom: 20px;
}

.dialog-section-title {
  font-weight: bold;
  margin-bottom: 10px;
  font-size: 14px;
}

.dialog-current {
  margin-bottom: 15px;
  font-size: 14px;
}

.dialog-options {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.dialog-option-btn {
  padding: 8px 16px;
  border: 1px solid #ddd;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
  min-width: 80px;
}

.dialog-option-btn:hover {
  transform: scale(1.05);
}

.dialog-option-btn.selected {
  border-width: 3px;
}

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.dialog-confirm-btn {
  padding: 8px 20px;
  background-color: #409EFF;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.dialog-confirm-btn:hover {
  background-color: #66b1ff;
}

.dialog-cancel-btn {
  padding: 8px 20px;
  background-color: #909399;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.dialog-cancel-btn:hover {
  background-color: #a6a9ad;
}




// 半自动化: 废弃
.automation-indicator {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
}

.automation-indicator.running {
  background-color: #409EFF;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.automation-indicator.failed {
  background-color: #F56C6C;
  cursor: pointer;
}

.automation-indicator.failed:hover::after {
  content: "点击重试";
  position: absolute;
  top: 25px;
  right: 0;
  background: #303133;
  color: white;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
}

.automation-indicator.success {
  background-color: #67C23A;
}

.auto-btn {
  position: absolute;
  bottom: 5px;
  right: 5px;
}


// 半自动化
.automation-progress {
  position: absolute;
  top: 5px;
  left: 5px; /* 避免遮挡pin图标 */
  cursor: pointer;
  z-index: 2;
  // z-index: 10;
}

.automation-progress:hover {
  transform: scale(1.1);
  transition: transform 0.2s;
}

/* 旋转动画 - 可选 */
@keyframes rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.rotating {
  animation: rotate 2s linear infinite;
}



/* 文档置信度悬浮框 */
.confidence-tooltip {
  position: fixed;
  background: #303133;
  color: white;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0,0,0,0.15);
  pointer-events: none;
  min-width: 180px;
}

.confidence-tooltip::before {
  content: '';
  position: absolute;
  bottom: -5px;
  left: 10px;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-top: 5px solid #303133;
}

/* 🔥 文档类型颜色显示图标（右上角） */
.file-type-indicator {
  position: absolute;
  top: 4px;
  right: 6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.8);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.12);
  z-index: 2;
  opacity: 0.85;
  transition: all 0.2s ease;
}

.file-type-indicator:hover {
  opacity: 1;
  transform: scale(1.1);
}

.homework-badge {
  position: absolute;
  right: 4px;
  bottom: 4px;
  max-width: 62px;
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(40, 82, 128, 0.88);
  color: #fff;
  font-size: 10px;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  box-shadow: 0 1px 4px rgba(24, 38, 56, 0.18);
  z-index: 3;
}

/* ========== Skill 对话框 ========== */
.skill-dlg-overlay {
  position: fixed;
  inset: 0;
  background: rgba(22, 28, 36, 0.48);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10050;
  padding: 24px;
}

.skill-dlg {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(20, 30, 50, 0.22);
  display: flex;
  flex-direction: column;
  width: 920px;
  max-width: 96vw;
  max-height: 88vh;
  overflow: hidden;
}

.skill-dlg--enable,
.skill-dlg--pack {
  width: 860px;
  max-width: 96vw;
}

.skill-dlg--edit {
  width: 980px;
  max-width: 96vw;
}

.skill-dlg-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px 12px;
  border-bottom: 1px solid #eef1f4;
  flex-shrink: 0;
}

.skill-dlg-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  color: #1f2a37;
  letter-spacing: 0.01em;
}

.skill-dlg-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: #7a8694;
  word-break: break-all;
}

.skill-dlg-close {
  border: none;
  background: transparent;
  color: #9aa5b1;
  font-size: 26px;
  line-height: 1;
  width: 32px;
  height: 32px;
  cursor: pointer;
  border-radius: 6px;
  flex-shrink: 0;
}

.skill-dlg-close:hover {
  background: #f2f4f7;
  color: #334155;
}

.skill-dlg-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 12px 22px 0;
  flex-shrink: 0;
}

.skill-select {
  flex: 1 1 220px;
  min-width: 180px;
  max-width: 420px;
  padding: 8px 10px;
  border: 1px solid #d7dee7;
  border-radius: 8px;
  font-size: 13px;
  background: #fff;
  color: #243447;
}

.skill-tabs {
  display: inline-flex;
  background: #f1f4f8;
  border-radius: 8px;
  padding: 3px;
  gap: 2px;
}

.skill-tab {
  border: none;
  background: transparent;
  color: #5b6b7c;
  font-size: 13px;
  padding: 7px 14px;
  border-radius: 6px;
  cursor: pointer;
}

.skill-tab.active {
  background: #fff;
  color: #1f2a37;
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(20, 30, 50, 0.08);
}

.skill-dlg-body {
  padding: 14px 22px;
  overflow: auto;
  flex: 1 1 auto;
  min-height: 0;
}

.skill-dlg-body--edit {
  display: flex;
  flex-direction: column;
}

.skill-empty {
  color: #8a96a3;
  text-align: center;
  padding: 36px 12px;
  font-size: 14px;
  line-height: 1.6;
}

.skill-enable-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}

.skill-enable-card {
  border: 1px solid #e5ebf1;
  border-radius: 10px;
  background: #fbfcfe;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 140px;
  height: auto;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.skill-enable-card.is-hub {
  border-color: #c9b896;
  background: linear-gradient(180deg, #fffdf8 0%, #fbfcfe 100%);
}

.skill-enable-card.is-off {
  opacity: 0.72;
  background: #f7f8fa;
}

.skill-enable-card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.skill-enable-card-title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 650;
  color: #1f2a37;
  line-height: 1.35;
}

.skill-enable-card-name {
  font-size: 11px;
  color: #8a96a3;
  font-family: Consolas, 'SF Mono', monospace;
  word-break: break-all;
}

.skill-hub-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  color: #7a5c2e;
  background: #f3e7cf;
  border-radius: 999px;
  padding: 1px 8px;
}

.skill-md-snippet {
  font-size: 12px;
  color: #4b5968;
  line-height: 1.55;
  max-height: none;
  overflow: visible;
  white-space: pre-wrap;
  word-break: break-word;
}

.skill-md-snippet :deep(p),
.skill-md-snippet :deep(ul),
.skill-md-snippet :deep(ol),
.skill-md-snippet :deep(h1),
.skill-md-snippet :deep(h2),
.skill-md-snippet :deep(h3) {
  margin: 0 0 4px;
  font-size: inherit;
  font-weight: 500;
}

.skill-md-snippet :deep(h1),
.skill-md-snippet :deep(h2),
.skill-md-snippet :deep(h3) {
  font-weight: 650;
  color: #243447;
}

.skill-pack-card-actions {
  margin-top: auto;
  padding-top: 4px;
}

.skill-pack-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  padding: 10px 22px 0;
  font-size: 12px;
  color: #5b6b7c;
  flex-shrink: 0;
}

.skill-pack-stats span {
  background: #f1f4f8;
  border-radius: 999px;
  padding: 4px 10px;
}

.skill-md-preview {
  flex: 1;
  min-height: 360px;
  overflow: auto;
  border: 1px solid #e5ebf1;
  border-radius: 10px;
  background: #fff;
  padding: 16px 18px;
}

.skill-fm-box {
  border: 1px solid #ebe4d6;
  background: #faf7f1;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 14px;
}

.skill-fm-title {
  font-size: 11px;
  font-weight: 650;
  color: #8a6a3b;
  margin-bottom: 6px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.skill-fm-row {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 8px;
  font-size: 12px;
  padding: 4px 0;
  align-items: start;
}

.skill-fm-key {
  color: #8a6a3b;
  font-family: Consolas, 'SF Mono', monospace;
  padding-top: 1px;
}

.skill-fm-val {
  color: #3d4a58;
  word-break: break-word;
  white-space: pre-wrap;
  line-height: 1.55;
}

.skill-fm-val.is-description {
  line-height: 1.65;
}

.skill-fm-val :deep(.skill-desc-mark) {
  display: inline-block;
  margin-top: 6px;
  font-weight: 700;
  color: #8a6a3b;
  letter-spacing: 0.02em;
}

.skill-md-body {
  color: #243447;
  font-size: 14px;
  line-height: 1.7;
}

.skill-md-body :deep(h1) {
  font-size: 22px;
  margin: 0 0 12px;
  border-bottom: 1px solid #eef1f4;
  padding-bottom: 8px;
}

.skill-md-body :deep(h2) {
  font-size: 18px;
  margin: 18px 0 8px;
}

.skill-md-body :deep(h3) {
  font-size: 15px;
  margin: 14px 0 6px;
}

.skill-md-body :deep(p),
.skill-md-body :deep(ul),
.skill-md-body :deep(ol) {
  margin: 0 0 10px;
}

.skill-md-body :deep(code) {
  background: #f1f4f8;
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 12px;
}

.skill-md-body :deep(pre) {
  background: #f6f8fb;
  border-radius: 8px;
  padding: 12px;
  overflow: auto;
}

.skill-md-editor {
  flex: 1;
  min-height: 420px;
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #d7dee7;
  border-radius: 10px;
  padding: 14px 16px;
  font-family: Consolas, 'SF Mono', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.55;
  color: #1f2a37;
  background: #fbfcfe;
  resize: vertical;
}

.skill-md-editor:focus {
  outline: none;
  border-color: #6ea8fe;
  box-shadow: 0 0 0 3px rgba(64, 158, 255, 0.15);
}

.skill-dlg-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 22px 16px;
  border-top: 1px solid #eef1f4;
  flex-shrink: 0;
  background: #fff;
}

.skill-dlg-hint {
  font-size: 12px;
  color: #8a96a3;
}

.skill-dlg-footer-actions {
  display: flex;
  gap: 10px;
  margin-left: auto;
}

.skill-btn {
  border: none;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 13px;
  cursor: pointer;
  line-height: 1.2;
}

.skill-btn--primary {
  background: #3b82f6;
  color: #fff;
}

.skill-btn--primary:hover {
  background: #2563eb;
}

.skill-btn--ghost {
  background: #eef1f5;
  color: #445566;
}

.skill-btn--ghost:hover {
  background: #e2e7ee;
}

.skill-btn--sm {
  background: #edf4ff;
  color: #2b6cb0;
  padding: 6px 10px;
  font-size: 12px;
  width: 100%;
}

.skill-btn--sm:hover {
  background: #dbeafe;
}
</style>
