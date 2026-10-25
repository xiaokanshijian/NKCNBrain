<template>
  <ChatWindow ref="ChatWindow" style="display: none;"></ChatWindow>
  <div class="notebook-card" 
    :class="{ 
      'flashing': needflashing || needMultiFlashing,
      'deep-permanent-card': isDeepPermanentCard(),
      // 'card-raised': isRelatedToSelected || isRelatedDocSelected()
    }" 
    :style="{ backgroundColor: getBackgroundColor(), position: 'relative' }"
    :data-cid="cid" 
    shadow="hover">
    <!-- 🔥 卡片进化等待提示覆盖层 -->
    <div v-if="cardTidying" class="card-tidying-overlay" @click.stop>
      <div class="card-tidying-content">
        <div class="waiting-text">请稍等...正在更新到原卡</div>
      </div>
    </div>
    <div
      v-show="cardHtmlMenuVisible"
      class="card-html-ctx-menu"
      :style="{ top: cardHtmlMenuY + 'px', left: cardHtmlMenuX + 'px' }"
      @mousedown.stop
    >
      <div
        v-if="imgClicked && imgClicked !== ''"
        class="card-html-ctx-item"
        @click.stop="onMenuCopyCardImage"
      >复制图片</div>
      <div class="card-html-ctx-item" @click.stop="onMenuGenerateHtml">
        {{ isCardHtmlBusy ? '生成中…' : (cardHasHtmlFile ? '重新生成html版' : '生成html版') }}
      </div>
      <div v-if="cardHasHtmlFile" class="card-html-ctx-item" @click.stop="onMenuIterateHtml">迭代现有html版</div>
      <div v-if="cardHasHtmlLastVersion" class="card-html-ctx-item" @click.stop="onMenuRevertHtml">回退上一版</div>
      <div v-if="cardHasHtmlFile" class="card-html-ctx-item" @click.stop="onMenuShowHtml">显示html版内容</div>
    </div>
    <div class="card-top">
      <div class="card-top-left">
        <div class="card-top-from">
          <span :title="cardTopLeftBusyTitle">
            <!-- 卡片生图/迭代：圆形箭头（刷新）转圈；HTML 生成：三角形转圈；完成后恢复原图标 -->
            <span v-if="isAnyImageBusy" class="card-image-spinner-wrap">
              <svg
                v-if="isOverlayImageGenerating && overlayBusyProgressTotal > 0"
                class="card-image-spinner-svg"
                :class="{ 'card-image-spinner-svg-overlay': isOverlayImageGenerating }"
                viewBox="0 0 24 24"
                width="20.8"
                height="20.8"
              >
                <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-opacity="0.25" stroke-width="1.8"></circle>
                <path :d="overlayBusySectorPath" fill="currentColor" fill-opacity="0.95"></path>
              </svg>
              <svg v-else class="card-image-spinner-svg" :class="{ 'card-image-spinner-svg-overlay': isOverlayImageGenerating }" viewBox="0 0 24 24" width="20.8" height="20.8">
                <!-- 圆弧 + 箭头（顺时针），类似刷新图标 -->
                <path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
                  d="M21 12a9 9 0 01-9 9 9 9 0 01-9-9 9 9 0 019-9c2.5 0 4.9.8 6.8 2.2L15 8.5h4V4"/>
              </svg>
            </span>
            <span v-else-if="isCardHtmlBusy" class="card-html-spinner-wrap">
              <svg class="card-html-spinner-svg" viewBox="0 0 24 24" width="20.8" height="20.8" aria-hidden="true">
                <polygon points="8,5 8,19 19,12" fill="currentColor" fill-opacity="0.92" />
              </svg>
            </span>
            <i v-else class="card-top-from-img" :class="{'purple-icon': cardInfo.interGrowthTA2GL, 'card-has-image-icon': hasCardImage}"></i>
          </span>
          <!-- 当前用户为作者或作者上级时显示进度环 -->
          <span 
            v-if="(isAuthor || isMarkLee) && cardInfo.interGrowthTA2GL" 
            class="progress-indicator"
            :title="`完成进度: ${completedSections}/${totalSections}`">
            
            <!-- 全部完成时显示勾号 -->
            <svg v-if="isFullyCompleted" width="20" height="20" viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15" fill="none" stroke="#1ac18e" stroke-width="3"></circle>
              <path d="M10 18L16 24L26 12" fill="none" stroke="#1ac18e" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"></path>
            </svg>
            
            <!-- 部分完成时显示进度环 -->
            <svg v-else width="20" height="20" viewBox="0 0 36 36">
              <circle cx="18" cy="18" r="15" fill="none" stroke="#e6e6e6" stroke-width="3"></circle>
              <!-- 进度环 -->
              <circle 
                cx="18" 
                cy="18" 
                r="15" 
                fill="none" 
                stroke="#1ac18e" 
                stroke-width="3"
                stroke-dasharray="94.2"
                :stroke-dashoffset="progressOffset"
                transform="rotate(-90 18 18)">
              </circle>
              <!-- 进度扇形 - 使用path元素绘制扇形 -->
              <path 
                :d="progressSectorPath" 
                fill="#1ac18e" 
                fill-opacity="0.4">
              </path>
            </svg>
          </span>
          <!-- 当前用户非作者且为作者下级时可能显示红色感叹号 -->
          <span 
            v-if="hasIncompleteResponses" 
            class="alert-icon" 
            title="您有未完成的回复">
            <i class="exclamation-icon">!</i>
          </span>
          <span 
            class="card-top-from-text" 
            @click="onCardClick"
            @mouseenter="showQualityTooltip = true"
            @mouseleave="showQualityTooltip = false"
            :class="{'intergrowth-card': cardInfo.interGrowthTA2GL}"
            style="position: relative;">
            {{ cardInfo.interGrowthTA2GL ? '共生打点卡片' : replaceTopTip(title) }}

            <!-- 质量评估悬浮框 -->
            <div v-if="showQualityTooltip && hasQualityScores && canViewQualityAssessment" class="quality-assessment-tooltip">
              <div style="font-weight: bold; margin-bottom: 5px;">📊 质量评估</div>
              <div v-if="validConfidenceScore">置信度：{{ validConfidenceScore.toFixed(1) }}/5.0 {{ confidenceLevel }}</div>
              <div v-if="validRotScore">腐烂度：{{ validRotScore.toFixed(1) }}/5.0 {{ rotLevel }} (越低越好)</div>
            </div>
          </span>
          <div class="card-merge-info" v-if="model_id < 0">
            <span class="merge-info-text">融合数量: {{ -model_id }}</span>
            <span class="merge-info-text">迭代次数: {{ -status - 1 }}</span>
          </div>
        </div>
        <div class="card-top-title" @click="onCardClick">
          <!-- {{ (contentTitle !== "") ? contentTitle : replaceTitle(title) }} -->
          <!-- {{ cardInfo.contentTitle || contentTitle || replaceTitle(title) }} -->
          <div class="card-title-content">
            <span class="card-author-badge" v-if="cardInfo.username && isGroupNotebook" title="卡片作者">
              {{
                ((s) => {
                  s = s.split('_')[0];
                  return s.length > 10 ? s.slice(0,8)+'...' : s;
                })(cardInfo.writer || cardInfo.username)
              }}
            </span>
            {{ cardInfo.contentTitle || contentTitle || replaceTitle(title) }}
          </div>
        </div>
      </div>

      <div class="card-rate">
        <span class="card-rate-right" ref="tooltipTarget">
          配置
          <div v-if="showTooltip" class="tooltip">
            {{ getCustomTitle }}
            <div class="nav-button">
              <el-button @click="handleClick">点击查看参数</el-button>
            </div>
          </div>
        </span>

        <span class="card-rate-left-single" :style="{ backgroundColor: color }" @click="turnToCardHL" v-if="scoreSFT === -1">
          <template v-if="this.score !== -2">
            {{ this.score }}
          </template>
          <img v-else src="@/assets/img/chatwindow/card_waiting_bigger.gif" style="width: 100%; height: 100%; object-fit: contain;"/>
        </span>
        <div class="card-rate-middle" v-if="scoreSFT !== -1">
          <span class="card-rate-left" :style="{ backgroundColor: colorSFT }" @click="turnToCardHLSFT">
            {{ scoreSFT }}
          </span>
          <span class="card-rate-left" :style="{ backgroundColor: color }" @click="turnToCardHL">
            <template v-if="this.score !== -2">
              {{ this.score }}
            </template>
            <img v-else src="@/assets/img/chatwindow/card_waiting_bigger.gif" style="width: 100%; height: 100%; object-fit: contain;"/>
          </span>
        </div>

        <span class="card-rate-history" ref="historyTipTarget" @click="showHistory">
          历史
          <div v-if="showHistoryTip" class="tooltip">
            对话历史
            <div class="nav-button">
              <el-button @click="backHistoryClicked">点击回溯历史</el-button>
            </div>
          </div>
        </span>
      </div>

      <div class="card-top-right">
        <div class="card-top-right-button" 
            :class="{ 'checked': checked }" 
            @click="onCheckboxChange"
            @contextmenu.prevent="onCheckboxChangeNoFront"
            :title="'点击勾选前移，右键仅勾选'">
        </div>
        <div class="model-info-text" @click="onCardClick" v-if="(contentTitle !== '')">
          {{ replaceTitle(title) }}
        </div>
      </div>
    </div>


    <!-- 正文内容 -->
    <div class="card-content" @click="onCardClick">
      <div class="card-content-text" v-if="!isContentExpanded">
        <!-- {{ content }} -->
        <div class="preview-content" v-html="formattedPreviewContent"></div>
      </div>
    </div>

    <div class="card-down">
      <button class="card-combine-btn" @click="textTo500">转500字</button>
      <button class="card-summarize-btn" @click="textTo1000">转1000字</button>
      <button class="card-study-guide-btn" @click="textTo1500">转1500字</button>

      <span style="float: right; line-height: 22px; vertical-align: middle;">
        <span class="word-count" style="font-size: 12px; color: #5C4033; text-shadow: 0.5px 0.5px 1px rgba(0, 0, 0, 0.5);">字数：{{ wordCount }}</span>
        <span v-if="isCiFeedbackLoading" class="card-ci-feedback-wordcount-loading" title="图理解反馈迭代进行中"><span class="card-ci-feedback-spinner"></span></span>
      </span>
    </div>

    <!-- 🔥 类型编辑对话框（移到这里，两个对话框样式都能使用） -->
    <el-dialog
      v-model="showTypeEditDialog"
      title="修改卡片类型"
      width="500px"
      :close-on-click-modal="false"
      @close="resetTypeEdit"
    >
      <div class="type-edit-content">
        <div class="type-explain">
          <h4>四色类型说明：</h4>
          <ul>
            <li><span style="color: #ff6b6b;">红色</span>：行业专业性语言（专业、严谨、权威，目标指向品质提高）</li>
            <li><span style="color: #4dabf7;">蓝色</span>：技术工具语言（通用工具和方法，目标指向效率提高）</li>
            <li><span style="color: #ae3ec9;">紫色</span>：场景思维语言（逻辑框架性，思维结构化）</li>
            <li><span style="color: #51cf66;">绿色</span>：自然语言（简单深刻，不虚伪、不浮华、不僵化）</li>
          </ul>
          <h4>DMT层次说明：</h4>
          <ul>
            <li><span style="color: #868e96;">枝(D)</span>：具体、细节、执行层面</li>
            <li><span style="color: #495057;">干(M)</span>：中等抽象程度</li>
            <li><span style="color: #212529;">根(T)</span>：抽象、框架、概念层面</li>
          </ul>
        </div>
        
        <div class="type-selector">
          <div class="type-group">
            <label>四色类型：</label>
            <select v-model="editingFourColorType" class="type-select">
              <option value="">未设置</option>
              <option value="R">红色 - 行业专业性</option>
              <option value="B">蓝色 - 技术工具</option>
              <option value="P">紫色 - 场景思维</option>
              <option value="G">绿色 - 自然语言</option>
            </select>
          </div>
          
          <div class="type-group">
            <label>DMT层次：</label>
            <select v-model="editingDmtLevel" class="type-select">
              <option value="">未设置</option>
              <option value="D">枝(D) - 具体执行</option>
              <option value="M">干(M) - 中等抽象</option>
              <option value="T">根(T) - 抽象框架</option>
            </select>
          </div>
        </div>
      </div>
      
      <div slot="footer" class="dialog-footer">
        <el-button @click="resetTypeEdit">取消</el-button>
        <el-button type="primary" @click="saveTypeEdit" :loading="savingType">保存</el-button>
      </div>
    </el-dialog>


  </div>
  <div v-if="showHistoryDialog" class="history-dialog">
    <div class="history-dialog-header">
      <h2>对话历史</h2>
      <div class="close" @click="hideHistory">&times;</div>
    </div>
    <div class="chat-container">
      <div v-for="(item, index) in this.cardInfo.history" :key="index" class="chat-item">
        <div class="file-list">
          <h4>文件列表：</h4>
          <ul>
            <li v-for="file in item.filelist" :key="file">{{ file }}</li>
          </ul>
        </div>
        <div class="message">
          <h4>消息：</h4>
          <p>{{ item.message }}</p>
        </div>
        <div class="ai-message">
          <h4>AI回答：</h4>
          <div v-if="Array.isArray(item.AImessage)">
            <ul>
              <li v-for="reply in item.AImessage" :key="reply">{{ reply }}</li>
            </ul>
          </div>
          <div v-else>
            <p>{{ item.AImessage }}</p>
          </div>
        </div>
      </div>
    </div>
  </div>


  <!-- 综合建议区域 -->
  <div class="comprehensive-area" v-if="isCardDialogVisible && hasComprehensiveAdvice">
    <h3 style="margin-bottom: 16px;">
      共生方案落地区（建议）
      <!-- 作者或上级可以查看不同用户的建议 -->
      <div v-if="isAuthor || isMarkLee" class="user-selector">
        <span>当前查看: </span>
        <el-select v-model="selectedAdviceUser" size="small" style="width: 120px; margin-left: 8px;">
          <el-option
            v-for="user in adviceUsersList"
            :key="user"
            :label="user"
            :value="user">
          </el-option>
        </el-select>
      </div>
    </h3>
    <div class="advice-content" v-html="formattedComprehensiveAdvice"></div>
  </div>

  <div
    class="card-dialog"
    :class="{ 'card-dialog--grading-excerpt': isGradingExcerptHtmlPreview }"
    v-if="isCardDialogVisible"
    ref="cardDialog"
    :style="{ zIndex: cardDialogZIndex }"
  >
    <!-- 关键词神经元永久卡片样式 -->
    <div v-if="isKeywordPermanentCard()" class="permanent-card-layout">
      <!-- 卡片标题和关闭按钮 -->
      <div class="card-dialog-header">
        <h2>
          {{ cardInfo.contentTitle || replaceTitle(cardInfo.title) }}
          <span style="font-size: 0.7em; font-weight: normal; color: #666;">（关键词神经元永久卡）</span>
        </h2>
        <div class="close" @click="hideCardDialog">&times;</div>
      </div>
      
      <!-- 上方一横条：日期、作者、标题、关键词 -->
      <div class="permanent-card-header-bar">
        <span class="permanent-card-meta-item"><b>创建日期:</b> {{ cardInfo.datetime }}</span>
        <span class="permanent-card-meta-separator">|</span>
        <span class="permanent-card-meta-item"><b>卡片作者:</b> {{ cardInfo.writer || cardInfo.username }}</span>
        <span class="permanent-card-meta-separator">|</span>
        <span class="permanent-card-meta-item">
          <b>卡片内容标题:</b> 
          <span v-if="!isEditingTitle" 
            @click="editTitle" 
            class="editable-field"
            style="cursor: pointer; padding: 2px; border-radius: 3px;">
            {{ cardInfo.contentTitle }}
          </span>
          <el-input
            v-else
            id="edit-title-input-permanent"
            v-model="tempTitle"
            size="small"
            style="width: 200px; display: inline-block;"
            @keyup.enter.native="saveInlineEdit"
            @keyup.esc.native="cancelInlineEdit"
          ></el-input>
        </span>
        <span class="permanent-card-meta-separator">|</span>
        <span class="permanent-card-meta-item">
          <b>语义关键词:</b>
          <span v-if="isKeywordsGenerating" class="keywords-generating-tip">
            <i class="el-icon-loading"></i> 还在理解和生成中…
          </span>
          <span v-else-if="!isEditingKeywords" 
            @click="editKeywords" 
            class="editable-field"
            style="cursor: pointer; padding: 2px; border-radius: 3px;">
            {{ cardInfo.keyWords }}
          </span>
          <el-input
            v-else
            id="edit-keywords-input-permanent"
            v-model="tempKeywords"
            size="small"
            style="width: 150px; display: inline-block;"
            @keyup.enter.native="saveInlineEdit"
            @keyup.esc.native="cancelInlineEdit"
          ></el-input>
          <span style="margin-left: 8px; color: #666; font-size: 12px;">字数：{{ wordCount }}</span>
          <span v-if="isCiFeedbackLoading" class="card-ci-feedback-wordcount-loading" title="图理解反馈迭代进行中"><span class="card-ci-feedback-spinner"></span></span>
        </span>
      </div>
      
      <!-- 中间区域：卡片内容（主体内容区域，有竖直滑动条） -->
      <div class="permanent-card-content-area">
          <div class="permanent-card-content-section">
          <div class="permanent-card-content-body" :style="{ backgroundColor: getKeywordPermanentCardContentBackground() }">
            <div class="card-toolbar-row">
              <div class="card-toolbar-left">
                <button type="button" class="card-toolbar-btn" @click="speakTextBegin">从头开始朗读</button>
                <button type="button" class="card-toolbar-btn" @click="stopSpeech">停止朗读</button>
                <button type="button" class="card-toolbar-btn" @click="openCardTextInNewTab" title="在新窗口中打开卡片内容（可朗读；有图时一并展示）">新窗口打开</button>
                <button type="button" class="card-toolbar-btn" v-if="isEditingContent" @click="saveInlineEdit">保存</button>
                <button type="button" class="card-toolbar-btn" v-if="isEditingContent" @click="cancelInlineEdit">取消</button>
                <span v-if="isCardImageGenerating" class="card-image-generating-tip" title="正在依卡片内容生图，请稍等"><i class="el-icon-loading"></i> 正在生图…</span>
                <template v-else>
                  <template v-if="!imgClicked || imgClicked === ''">
                    <button type="button" class="card-toolbar-btn card-toolbar-btn-gen-single" @click="openCardImageGenDialog">卡片生图</button>
                    <el-select v-model="cardImageQuality" size="small" style="width: 150px; margin-left: 10px;">
                      <el-option label="普通（现有逻辑）" value="normal"></el-option>
                      <el-option label="高清（4K）" value="high"></el-option>
                    </el-select>
                  </template>
                  <template v-else>
                    <span class="card-image-gen-group">
                      <button type="button" class="card-toolbar-btn card-toolbar-btn-gen" @click="openCardImageGenDialog">新生图</button>
                      <button type="button" class="card-toolbar-btn card-toolbar-btn-gen" @click="requestIterateCardImage">迭代图</button>
                      <button type="button" class="card-toolbar-btn" title="恢复为上一次「迭代图」前的图片（仅一步）" :disabled="isCardImageGenerating" @click="requestRevertIterateCardImage">图回退</button>
                      <el-select v-model="cardImageQuality" size="small" style="width: 150px; margin-left: 10px;">
                        <el-option label="普通（现有逻辑）" value="normal"></el-option>
                        <el-option label="高清（4K）" value="high"></el-option>
                      </el-select>
                    </span>
                    <button type="button" class="card-toolbar-btn card-toolbar-btn-ci" @click="openCiFeedbackDialog" :disabled="isCiFeedbackLoading" title="图无损理解反馈迭代文本">图理解反馈文本</button>
                    <span v-if="ciFeedbackStatus === 'loading'" class="card-ci-feedback-status card-ci-feedback-loading"><i class="el-icon-loading"></i> {{ ciFeedbackStatusMsg }}</span>
                    <span v-else-if="ciFeedbackStatus === 'success'" class="card-ci-feedback-status card-ci-feedback-success">{{ ciFeedbackStatusMsg }}</span>
                    <span v-else-if="ciFeedbackStatus === 'error'" class="card-ci-feedback-status card-ci-feedback-error" :title="ciFeedbackStatusMsg">{{ ciFeedbackStatusMsg.length > 20 ? ciFeedbackStatusMsg.slice(0, 18) + '…' : ciFeedbackStatusMsg }}</span>
                  </template>
                </template>
              </div>
              <div>
                <span v-if="!showLastContent && cardInfo.lastContent && cardInfo.lastContent !== ''" @click="toggleLastContent" style="cursor: pointer; margin-right: 10px;">
                  <i class="el-icon-arrow-left"></i> ←回退
                </span>
                <span v-if="showLastContent && cardInfo.lastContent && cardInfo.lastContent !== ''" style="display: flex; align-items: center;">
                  <span @click="toggleLastContent" style="cursor: pointer; margin-right: 10px;">
                    <i class="el-icon-arrow-right"></i> →最新
                  </span>
                  <span @click="confirmLastContent" style="cursor: pointer; color: #67c23a;">
                    <i class="el-icon-check"></i> 确认
                  </span>
                </span>
              </div>
            </div>
            <div class="card-image-stack" @contextmenu.prevent="openCardHtmlMenu($event)">
              <div v-if="cardMediaViewMode !== 'image'" class="card-html-chrome">
                <div class="card-html-chrome-left">
                  <button type="button" class="card-html-seg" :class="{ on: cardMediaViewMode === 'html' }" @click="setCardMediaViewMode('html')" title="预览">◉</button>
                  <button type="button" class="card-html-seg" :class="{ on: cardMediaViewMode === 'html_source' }" @click="setCardMediaViewMode('html_source')" title="HTML 源码">&lt;/&gt;</button>
                  <span class="card-html-chrome-title">{{ cardHtmlChromeTitle }}</span>
                </div>
                <div class="card-html-chrome-right">
                  <button type="button" class="card-html-seg" @click="copyCardHtml">Copy</button>
                  <button type="button" class="card-html-seg" @click="downloadCardHtml">Download</button>
                  <button type="button" class="card-html-seg" title="在浏览器新标签页打开（与预览同一地址）" @click="openCardHtmlInNewTab">新窗口</button>
                  <button type="button" class="card-html-seg primary" @click="setCardMediaViewMode('image')">图片</button>
                </div>
              </div>
              <img
                v-if="cardMediaViewMode === 'image' && imgClicked !== ''"
                :src="'data:' + (this.imgType || 'image/png') + ';base64,' + this.imgClicked"
                alt="Image"
                style="max-width: 100%; width: auto; height: auto; margin-bottom: 10px; cursor: pointer;"
                @dblclick="openCardImageFullscreen"
              />
              <iframe
                v-else-if="cardMediaViewMode === 'html'"
                :key="'htmlp' + cardHtmlIframeKey"
                class="card-html-iframe"
                :class="{ 'card-html-iframe--grading-excerpt': isGradingExcerptCard }"
                :src="cardHtmlViewUrl"
                title="card html"
                sandbox="allow-scripts allow-same-origin allow-forms"
              ></iframe>
              <pre v-else-if="cardMediaViewMode === 'html_source'" class="card-html-source-pre">{{ cardHtmlSourceText }}</pre>
            </div>
            <div v-if="!isEditingContent" 
                @click="editContentInline" 
                @mousedown="handleMouseDown"
                @mouseup="handleMouseUp"
                class="content-hover-area-tidy"
                :style="{ 
                  cursor: 'pointer', 
                  padding: '5px', 
                  borderRadius: '4px',
                  backgroundColor: getKeywordPermanentCardContentBackground(),
                  transition: 'background-color 0.2s ease'
                }"
                @mouseenter="$event.target.style.backgroundColor = getKeywordPermanentCardContentBackgroundHover()"
                @mouseleave="$event.target.style.backgroundColor = getKeywordPermanentCardContentBackground()">
              <AnswerParser
                :key="(showLastContent ? 'last' : 'current') + '-perm-p' + contentPageIndex"
                :answer="pagedDisplayContent"
                @startReading="startFromIndex"
                @doubleClickOver="doubleClickOver"
              />
              <div v-if="hasContentPages" class="nkcn-card-page-nav" @click.stop>
                <button type="button" :disabled="contentPageIndex <= 0" @click="contentPageIndex = Math.max(0, contentPageIndex - 1)">上一页</button>
                <span>{{ contentPageIndex + 1 }} / {{ contentPages.length }}</span>
                <button type="button" :disabled="contentPageIndex >= contentPages.length - 1" @click="contentPageIndex = Math.min(contentPages.length - 1, contentPageIndex + 1)">下一页</button>
              </div>
            </div>
            <el-input
              v-else
              id="edit-content-input-permanent"
              type="textarea"
              :rows="15"
              v-model="tempContent"
              style="width: 100%;"
              class="contentInput"
            ></el-input>
          </div>
        </div>
      </div>
      
      <!-- 下方一横条：后置索引和四色DMT属性 -->
      <div class="permanent-card-footer-bar">
        <div class="permanent-card-footer-item permanent-card-postindex-container">
          <span style="font-weight: bold; color: #0055cc; font-size: 1.1em; cursor: pointer; white-space: nowrap;" @click="openPostIndexDialog">∞后置索引：</span>
          <span class="permanent-card-postindex-list" v-if="postIndices && postIndices.length > 0">
            <span 
              v-for="cid in postIndices" 
              :key="cid"
              class="permanent-card-postindex-item"
              title="点击可查看"
              @click.stop="openCardByCid(cid)"
            >
              {{ cidToTitleMap[cid] || `未知卡片(${cid})` }}
            </span>
          </span>
          <span v-else style="font-size: 1.0em;">无</span>
        </div>
        <span class="permanent-card-footer-separator">|</span>
        <span class="permanent-card-footer-item" v-if="isAuthor || isMarkLee">
          <span class="type-edit-label" @click="showTypeEditDialog = true" title="点击修改卡片类型" style="cursor: pointer;">
            <span class="type-label-text">类型：</span>
            <span class="type-value" :style="{ color: getFourColorTypeColor(fourColorType) }">
              {{ getFourColorTypeDisplay(fourColorType) }}
            </span>
            <span class="type-separator">/</span>
            <span class="type-value" :style="{ color: getDmtLevelColor(dmtLevel) }">
              {{ getDmtLevelDisplay(dmtLevel) }}
            </span>
          </span>
        </span>
        <span class="permanent-card-footer-item" v-else>
          <span class="type-label-text">类型：</span>
          <span class="type-value" :style="{ color: getFourColorTypeColor(fourColorType) }">
            {{ getFourColorTypeDisplay(fourColorType) }}
          </span>
          <span class="type-separator">/</span>
          <span class="type-value" :style="{ color: getDmtLevelColor(dmtLevel) }">
            {{ getDmtLevelDisplay(dmtLevel) }}
          </span>
        </span>
      </div>
      
      <!-- 最下面（可溢出，滚动外部滑动条可见）：深评、浅评、四个button -->
      <div class="permanent-card-auxiliary-section">
        <!-- 深评 -->
        <div class="permanent-card-review-section">
          <div class="permanent-card-score-box" style="background-color: #9966cc;">
            <p ref="scoreSFT" :style="textStyleSFT">
              <b>【红蓝卡标深评打分】</b> 
              <span class="permanent-card-score-value" @click.stop="turnToCardHLSFT" style="cursor: pointer; text-decoration: underline;">{{ cardInfo.scoreSFT < 0 ? '?' : cardInfo.scoreSFT }}</span>
              <span class="permanent-card-expand-icon" :class="{ 'expanded': isDeepReviewExpanded }" @click.stop="toggleDeepReview" style="cursor: pointer; margin-left: 8px;">▼</span>
            </p>
          </div>
          <div v-if="isDeepReviewExpanded" class="permanent-card-review-details">
            <div class="permanent-card-reason-box" style="background-color: #e6f0ff;">
              <div class="expand-button" @click="expandContent('sftReason')">
                <span class="expand-icon">⤢</span>
              </div>
              <p v-if="splitReasonSFT.length > 0" :style="textStyleSFT"><b>【深评理由】</b> {{ splitReasonSFT[0] || "正在打分，等待解析打分理由" }}</p>
            </div>
            <div class="permanent-card-suggestion-box" style="background-color: #fff9d6;">
              <div class="expand-button" @click="expandContent('sftSuggestion')">
                <span class="expand-icon">⤢</span>
              </div>
              <p v-if="splitReasonSFT.length > 1" :style="textStyleSFT">
                <b>【深评建议】</b>&nbsp;&nbsp;
                <button @click="speakTextBeginSFT" style="padding: 2px 6px; font-size: 12px;">从头开始朗读</button>
                <button @click="stopSpeech" style="padding: 2px 6px; font-size: 12px;">停止朗读</button><br>
                <AnswerParser 
                  :answer="splitReasonSFT[1] || '正在打分，等待解析改进建议'" 
                  @startReading="startFromIndexSFT" 
                  @doubleClickOver="doubleClickOver"
                />
              </p>
            </div>
          </div>
        </div>
        
        <!-- 浅评 -->
        <div class="permanent-card-review-section">
          <div class="permanent-card-score-box" style="background-color: #baa6e0;">
            <p :style="textStyle">
              <b>红蓝卡标浅评打分(GPT4o prompt):</b> 
              <span class="permanent-card-score-value" @click.stop="turnToCardHL" style="cursor: pointer; text-decoration: underline;">{{ this.score }}</span>
              <span class="permanent-card-expand-icon" :class="{ 'expanded': isShallowReviewExpanded }" @click.stop="toggleShallowReview" style="cursor: pointer; margin-left: 8px;">▼</span>
            </p>
          </div>
          <div v-if="isShallowReviewExpanded" class="permanent-card-review-details">
            <div class="permanent-card-reason-box" style="background-color: #f5faff;">
              <div class="expand-button" @click="expandContent('reason')">
                <span class="expand-icon">⤢</span>
              </div>
              <p v-if="splitReason.length > 0" :style="textStyle"><b>红蓝浅评理由:</b> {{ splitReason[0] || "正在打分，等待解析打分理由" }}</p>
            </div>
            <div class="permanent-card-suggestion-box" style="background-color: #fffdf0;">
              <div class="expand-button" @click="expandContent('suggestion')">
                <span class="expand-icon">⤢</span>
              </div>
              <p v-if="splitReason.length > 1" :style="textStyle"><b>红蓝浅评改进建议:</b> {{ splitReason[1] || "正在打分，等待解析改进建议" }}</p>
            </div>
          </div>
        </div>
        
        <!-- 三个button -->
        <div class="permanent-card-button-group">
          <button class="card-delete" @click="deleteCard">删除卡片</button>
          <button class="card-history" @click="backHistory(this.cardInfo.history, title)">回溯历史</button>
          <button class="card-paste" @click="copyContentWithEmptyLines">复制卡片</button>
        </div>
      </div>
    </div>
    
    <!-- 普通卡片样式 -->
    <div v-else-if="this.card.type" class="card-layout">
      <!-- 卡片标题和关闭按钮 -->
      <div class="card-dialog-header">
        <h2>{{ replaceTitle(cardInfo.title) }}</h2>
        <div class="close" @click="hideCardDialog">&times;</div>
      </div>
      
      <!-- 左侧区域 -->
      <div class="card-content-layout">
        <div class="card-left-section">
          <!-- 卡片类型和前置索引区域 -->
          <div class="card-type-section" style="background-color: #c8d9f2; padding: 10px; border-radius: 8px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
            <div class="card-type" style="font-size: 1.2em; font-weight: bold;">
              <span>{{ cardInfo.type }}</span>
            </div>
            <div v-if="cardInfo.preIndex && cardInfo.preIndex !== ''" class="card-preindex" style="display: flex; align-items: center;">
              <span style="color: #0055cc; font-size: 1.1em;">∞前置索引：</span>
              <span style="font-weight: bold; font-size: 1.1em;">{{ cardInfo.preIndex }}</span>
            </div>
          </div>

          <!-- 卡片头部信息区 -->
          <div class="info-section" style="background-color: #e6f2ff; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
            <p><b>创建日期:</b> {{ cardInfo.datetime }}</p>
            <p><b>卡片作者:</b> {{ cardInfo.writer || cardInfo.username }}</p>
            <p><b>卡片内容标题:</b> 
              <span v-if="!isEditingTitle" 
                @click="editTitle" 
                class="editable-field"
                style="cursor: pointer; padding: 2px; border-radius: 3px;">
                {{ cardInfo.contentTitle }}
              </span>
              <el-input
                v-else
                id="edit-title-input"
                v-model="tempTitle"
                size="medium"
                style="width: 80%; background-color: #d0e5ff;"
                @keyup.enter.native="saveInlineEdit"
                @keyup.esc.native="cancelInlineEdit"
              ></el-input>
            </p>
            <p><b>语义关键词:</b>
              <span v-if="isKeywordsGenerating" class="keywords-generating-tip">
                <i class="el-icon-loading"></i> 还在理解和生成中…
              </span>
              <span v-else-if="!isEditingKeywords" 
                @click="editKeywords" 
                class="editable-field"
                style="cursor: pointer; padding: 2px; border-radius: 3px;">
                {{ cardInfo.keyWords }}
              </span>
              <el-input
                v-else
                id="edit-keywords-input"
                v-model="tempKeywords"
                size="medium"
                style="width: 80%; background-color: #d0e5ff;"
                @keyup.enter.native="saveInlineEdit"
                @keyup.esc.native="cancelInlineEdit"
              ></el-input>
            </p>
          </div>
          
          <!-- 主体部分 -->
          <div class="section-title" style="display: flex; align-items: center; justify-content: space-between;">
            <!-- <h3>主体部分</h3> -->
            <div>
              <!-- <span v-if="!showLastContent" @click="toggleLastContent" style="cursor: pointer; margin-right: 10px;"> -->
              <span v-if="!showLastContent && cardInfo.lastContent && cardInfo.lastContent !== ''" @click="toggleLastContent" style="cursor: pointer; margin-right: 10px;">
                <i class="el-icon-arrow-left"></i> ←回退
              </span>
              <span v-if="showLastContent && cardInfo.lastContent && cardInfo.lastContent !== ''" style="display: flex; align-items: center;">
                <span @click="toggleLastContent" style="cursor: pointer; margin-right: 10px;">
                  <i class="el-icon-arrow-right"></i> →最新
                </span>
                <span @click="confirmLastContent" style="cursor: pointer; color: #67c23a;">
                  <i class="el-icon-check"></i> 确认
                </span>
              </span>
            </div>
          </div>
          
          <!-- 主体部分内容 -->
          <div class="content-section card-content-zone" style="background-color: #e8f5e9; border-radius: 8px; position: relative; max-height: 350px; overflow-y: auto; margin-bottom: 15px;">
            <div class="expand-button" @click="expandContent('main')">
              <span class="expand-icon">⤢</span>
            </div>
            <div class="card-content-block">
              <div class="card-toolbar-row card-toolbar-row-inline">
                <button type="button" class="card-toolbar-btn" @click="speakTextBegin">从头开始朗读</button>
                <button type="button" class="card-toolbar-btn" @click="stopSpeech">停止朗读</button>
                <button type="button" class="card-toolbar-btn" @click="openCardTextInNewTab" title="在新窗口中打开卡片内容（可朗读；有图时一并展示）">新窗口打开</button>
                <button type="button" class="card-toolbar-btn" v-if="isEditingContent" @click="saveInlineEdit">保存</button>
                <button type="button" class="card-toolbar-btn" v-if="isEditingContent" @click="cancelInlineEdit">取消</button>
                <span v-if="isCardImageGenerating" class="card-image-generating-tip" title="正在依卡片内容生图，请稍等"><i class="el-icon-loading"></i> 正在生图…</span>
                <template v-else>
                  <button v-if="!imgClicked || imgClicked === ''" type="button" class="card-toolbar-btn card-toolbar-btn-gen-single" @click="openCardImageGenDialog">卡片生图</button>
                  <template v-else>
                    <span class="card-image-gen-group">
                      <button type="button" class="card-toolbar-btn card-toolbar-btn-gen" @click="openCardImageGenDialog">新生图</button>
                      <button type="button" class="card-toolbar-btn card-toolbar-btn-gen" @click="requestIterateCardImage">迭代图</button>
                      <button type="button" class="card-toolbar-btn" title="恢复为上一次「迭代图」前的图片（仅一步）" :disabled="isCardImageGenerating" @click="requestRevertIterateCardImage">图回退</button>
                    </span>
                    <button type="button" class="card-toolbar-btn card-toolbar-btn-ci" @click="openCiFeedbackDialog" :disabled="isCiFeedbackLoading" title="图无损理解反馈迭代文本">图理解反馈文本</button>
                    <span v-if="ciFeedbackStatus === 'loading'" class="card-ci-feedback-status card-ci-feedback-loading"><i class="el-icon-loading"></i> {{ ciFeedbackStatusMsg }}</span>
                    <span v-else-if="ciFeedbackStatus === 'success'" class="card-ci-feedback-status card-ci-feedback-success">{{ ciFeedbackStatusMsg }}</span>
                    <span v-else-if="ciFeedbackStatus === 'error'" class="card-ci-feedback-status card-ci-feedback-error" :title="ciFeedbackStatusMsg">{{ ciFeedbackStatusMsg.length > 20 ? ciFeedbackStatusMsg.slice(0, 18) + '…' : ciFeedbackStatusMsg }}</span>
                  </template>
                </template>
              </div>
              <div class="card-toolbar-content-gap"></div>
              <!-- 如果服务器提供了img_type，使用它；否则默认为png；双击图片新窗口铺满放大 -->
              <div class="card-image-stack" @contextmenu.prevent="openCardHtmlMenu($event)">
                <div v-if="cardMediaViewMode !== 'image'" class="card-html-chrome">
                  <div class="card-html-chrome-left">
                    <button type="button" class="card-html-seg" :class="{ on: cardMediaViewMode === 'html' }" @click="setCardMediaViewMode('html')" title="预览">◉</button>
                    <button type="button" class="card-html-seg" :class="{ on: cardMediaViewMode === 'html_source' }" @click="setCardMediaViewMode('html_source')" title="HTML 源码">&lt;/&gt;</button>
                    <span class="card-html-chrome-title">{{ cardHtmlChromeTitle }}</span>
                  </div>
                  <div class="card-html-chrome-right">
                    <button type="button" class="card-html-seg" @click="copyCardHtml">Copy</button>
                    <button type="button" class="card-html-seg" @click="downloadCardHtml">Download</button>
                    <button type="button" class="card-html-seg" title="在浏览器新标签页打开（与预览同一地址）" @click="openCardHtmlInNewTab">新窗口</button>
                    <button type="button" class="card-html-seg primary" @click="setCardMediaViewMode('image')">图片</button>
                  </div>
                </div>
                <img
                  v-if="cardMediaViewMode === 'image' && imgClicked !== ''"
                  :src="'data:' + (this.imgType || 'image/png') + ';base64,' + this.imgClicked"
                  alt="Image"
                  style="max-width: 100%; width: auto; height: auto; cursor: pointer;"
                  @dblclick="openCardImageFullscreen"
                />
                <iframe
                  v-else-if="cardMediaViewMode === 'html'"
                  :key="'htmld1' + cardHtmlIframeKey"
                  class="card-html-iframe"
                  :class="{ 'card-html-iframe--grading-excerpt': isGradingExcerptCard }"
                  :src="cardHtmlViewUrl"
                  title="card html"
                  sandbox="allow-scripts allow-same-origin allow-forms"
                ></iframe>
                <pre v-else-if="cardMediaViewMode === 'html_source'" class="card-html-source-pre">{{ cardHtmlSourceText }}</pre>
              </div>
              <!-- 非编辑状态显示解析后的内容，点击进入编辑状态 -->
              <div v-if="!isEditingContent" 
                  @click="editContentInline" 
                  @mousedown="handleMouseDown"
                  @mouseup="handleMouseUp"
                  class="content-hover-area-tidy"
                  style="cursor: pointer; padding: 5px; border-radius: 4px;">
                <AnswerParser
                  :key="(showLastContent ? 'last' : 'current') + '-p' + contentPageIndex"
                  :answer="pagedDisplayContent"
                  @startReading="startFromIndex"
                  @doubleClickOver="doubleClickOver"
                />
                <div v-if="hasContentPages" class="nkcn-card-page-nav" @click.stop>
                  <button type="button" :disabled="contentPageIndex <= 0" @click="contentPageIndex = Math.max(0, contentPageIndex - 1)">上一页</button>
                  <span>{{ contentPageIndex + 1 }} / {{ contentPages.length }}</span>
                  <button type="button" :disabled="contentPageIndex >= contentPages.length - 1" @click="contentPageIndex = Math.min(contentPages.length - 1, contentPageIndex + 1)">下一页</button>
                </div>
              </div>
              <!-- 编辑状态显示文本框 -->
              <el-input
                v-else
                id="edit-content-input"
                type="textarea"
                :rows="18"
                v-model="tempContent"
                style="width: 100%; background-color: #e8f4e8;"
                class="contentInput"
              ></el-input>
            </div>
          </div>
        </div>
        
        <!-- 右侧区域 -->
        <div class="card-right-section">
          <!-- 卡标部分标题 -->
          <div class="section-title">
            <h3>卡标部分</h3>
          </div>
          
          <!-- 深评打分 -->
          <div class="score-section" style="background-color: #9966cc; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
            <p ref="scoreSFT" :style="textStyleSFT"><b>【红蓝卡标深评打分】</b> {{ cardInfo.scoreSFT < 0 ? '?' : cardInfo.scoreSFT }}</p>
          </div>
          
          <!-- 深评理由 -->
          <div class="reason-section" style="background-color: #e6f0ff; padding: 10px; border-radius: 8px; position: relative; max-height: 120px; overflow-y: auto; margin-bottom: 10px;">
            <div class="expand-button" @click="expandContent('sftReason')">
              <span class="expand-icon">⤢</span>
            </div>
            <p v-if="splitReasonSFT.length > 0" :style="textStyleSFT"><b>【深评理由】</b> {{ splitReasonSFT[0] || "正在打分，等待解析打分理由" }}</p>
          </div>
          
          <!-- 深评改进建议 -->
          <div class="suggestion-section" style="background-color: #fff9d6; padding: 10px; border-radius: 8px; position: relative; max-height: 200px; overflow-y: auto; margin-bottom: 15px;">
            <div class="expand-button" @click="expandContent('sftSuggestion')">
              <span class="expand-icon">⤢</span>
            </div>
            <p v-if="splitReasonSFT.length > 1" :style="textStyleSFT">
              <b>【深评建议】</b>&nbsp;&nbsp;
              <button @click="speakTextBeginSFT">从头开始朗读</button>
              <button @click="stopSpeech">停止朗读</button><br>
              <AnswerParser 
                :answer="splitReasonSFT[1] || '正在打分，等待解析改进建议'" 
                @startReading="startFromIndexSFT" 
                @doubleClickOver="doubleClickOver"
              />
            </p>
          </div>
          
          <!-- 浅评打分 -->
          <div style="background-color: #baa6e0; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
            <p :style="textStyle"><b>红蓝卡标浅评打分(GPT4o prompt):</b> {{ this.score }}</p>
          </div>
          
          <!-- 浅评理由和建议 -->
          <div class="reason-suggestion-container">
            <!-- 浅评理由 -->
            <div class="reason-section-compact" style="background-color: #f5faff; padding: 10px; border-radius: 8px; position: relative; max-height: 100px; overflow-y: auto; flex: 1; margin-right: 5px;">
              <div class="expand-button" @click="expandContent('reason')">
                <span class="expand-icon">⤢</span>
              </div>
              <p v-if="splitReason.length > 0" :style="textStyle"><b>红蓝浅评理由:</b> {{ splitReason[0] || "正在打分，等待解析打分理由" }}</p>
            </div>
            
            <!-- 浅评改进建议 -->
            <div class="suggestion-section-compact" style="background-color: #fffdf0; padding: 10px; border-radius: 8px; position: relative; max-height: 100px; overflow-y: auto; flex: 1; margin-left: 5px;">
              <div class="expand-button" @click="expandContent('suggestion')">
                <span class="expand-icon">⤢</span>
              </div>
              <p v-if="splitReason.length > 1" :style="textStyle"><b>红蓝浅评改进建议:</b> {{ splitReason[1] || "正在打分，等待解析改进建议" }}</p>
            </div>
          </div>

          <!-- 后置索引区域 -->
          <div class="card-type-section" 
              style="background-color: #c8d9f2; padding: 10px; border-radius: 8px; margin-top: 12px; display: flex; justify-content: space-between; align-items: center;">
            <div class="card-postindex" style="display: flex; align-items: center;">
              <span style="font-weight: bold; color: #0055cc; font-size: 1.1em;" @click="openPostIndexDialog">∞后置索引：</span>
              <span style="font-size: 1.0em;">{{ postIndexTitle }}</span>
            </div>
          </div>

          <!-- 🔥 四色/DMT类型手动修改 -->
          <div class="card-type-edit-dialog" v-if="isAuthor || isMarkLee" style="margin-top: 12px;">
            <div class="card-type-section" 
                style="background-color: #f0f0f0; padding: 10px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
              <span class="type-edit-label" @click="showTypeEditDialog = true" title="点击修改卡片类型" style="cursor: pointer;">
                <span class="type-label-text">类型：</span>
                <span class="type-value" :style="{ color: getFourColorTypeColor(fourColorType) }">
                  {{ getFourColorTypeDisplay(fourColorType) }}
                </span>
                <span class="type-separator">/</span>
                <span class="type-value" :style="{ color: getDmtLevelColor(dmtLevel) }">
                  {{ getDmtLevelDisplay(dmtLevel) }}
                </span>
              </span>
            </div>
          </div>
        </div>
      </div>
      
      <!-- 按钮组 -->
      <div class="card-button">
        <button class="card-delete" @click="deleteCard">删除卡片</button>
        <button class="card-history" @click="backHistory(this.cardInfo.history, title)">回溯历史</button>
        <button class="card-paste" @click="copyContentWithEmptyLines">复制卡片</button>
      </div>
    </div>
    
    <!-- 原始样式 -->
    <div v-else>
      <div class="card-dialog-header">
        <h2>{{ replaceTitle(cardInfo.title) }}</h2>
        <div class="close" @click="hideCardDialog">&times;</div>
      </div>
      <div class="card-dialog-body">
        <div style="background-color: #e6f2ff; padding: 15px; border-radius: 8px;">
          <p><b>创建日期:</b> {{ cardInfo.datetime }}</p>
          <p><b>卡片作者:</b> {{ cardInfo.writer || cardInfo.username }}</p>
          <p><b>卡片内容标题:</b> 
            <span v-if="!isEditingTitle" 
              @click="editTitle" 
              class="editable-field"
              style="cursor: pointer; padding: 2px; border-radius: 3px;">
              {{ cardInfo.contentTitle }}
            </span>
            <el-input
              v-else
              id="edit-title-input"
              v-model="tempTitle"
              size="medium"
              style="width: 80%; background-color: #d0e5ff;"
              @keyup.enter.native="saveInlineEdit"
              @keyup.esc.native="cancelInlineEdit"
            ></el-input>
          </p>
          <p><b>语义关键词:</b>
            <span v-if="isKeywordsGenerating" class="keywords-generating-tip">
              <i class="el-icon-loading"></i> 还在理解和生成中…
            </span>
            <span v-else-if="!isEditingKeywords" 
              @click="editKeywords" 
              class="editable-field"
              style="cursor: pointer; padding: 2px; border-radius: 3px;">
              {{ cardInfo.keyWords }}
            </span>
            <el-input
              v-else
              id="edit-keywords-input"
              v-model="tempKeywords"
              size="medium"
              style="width: 80%; background-color: #d0e5ff;"
              @keyup.enter.native="saveInlineEdit"
              @keyup.esc.native="cancelInlineEdit"
            ></el-input>
          </p>
        </div>
        <div style="padding: 15px; border-radius: 8px;">
          <!-- <h3>主体部分</h3> -->
          <div>
            <span v-if="!showLastContentNormal && cardInfo.lastContent && cardInfo.lastContent !== ''" @click="toggleLastContentNormal" style="cursor: pointer; margin-right: 10px;">
              <i class="el-icon-arrow-left"></i> ←回退
            </span>
            <span v-if="showLastContentNormal && cardInfo.lastContent && cardInfo.lastContent !== ''" style="display: flex; align-items: center;">
              <span @click="toggleLastContentNormal" style="cursor: pointer; margin-right: 10px;">
                <i class="el-icon-arrow-right"></i> →最新
              </span>
              <span @click="confirmLastContentNormal" style="cursor: pointer; color: #67c23a;">
                <i class="el-icon-check"></i> 确认
              </span>
            </span>
          </div>
        </div>
        <div class="card-content-zone" style="background-color: #f0f0f0; border-radius: 8px;">
          <div class="card-content-block">
            <div class="card-toolbar-row card-toolbar-row-inline">
              <button type="button" class="card-toolbar-btn" @click="speakTextBegin">从头开始朗读</button>
              <button type="button" class="card-toolbar-btn" @click="stopSpeech">停止朗读</button>
              <button type="button" class="card-toolbar-btn" @click="openCardTextInNewTab" title="在新窗口中打开卡片内容（可朗读；有图时一并展示）">新窗口打开</button>
              <button type="button" class="card-toolbar-btn" v-if="isEditingContent" @click="saveInlineEdit">保存</button>
              <button type="button" class="card-toolbar-btn" v-if="isEditingContent" @click="cancelInlineEdit">取消</button>
              <span v-if="isCardImageGenerating" class="card-image-generating-tip" title="正在依卡片内容生图，请稍等"><i class="el-icon-loading"></i> 正在生图…</span>
              <template v-else>
                <button v-if="!imgClicked || imgClicked === ''" type="button" class="card-toolbar-btn card-toolbar-btn-gen-single" @click="openCardImageGenDialog">卡片生图</button>
                <template v-else>
                  <span class="card-image-gen-group">
                    <button type="button" class="card-toolbar-btn card-toolbar-btn-gen" @click="openCardImageGenDialog">新生图</button>
                    <button type="button" class="card-toolbar-btn card-toolbar-btn-gen" @click="requestIterateCardImage">迭代图</button>
                    <button type="button" class="card-toolbar-btn" title="恢复为上一次「迭代图」前的图片（仅一步）" :disabled="isCardImageGenerating" @click="requestRevertIterateCardImage">图回退</button>
                  </span>
                  <button type="button" class="card-toolbar-btn card-toolbar-btn-ci" @click="openCiFeedbackDialog" :disabled="isCiFeedbackLoading" title="图无损理解反馈迭代文本">图理解反馈文本</button>
                  <span v-if="ciFeedbackStatus === 'loading'" class="card-ci-feedback-status card-ci-feedback-loading"><i class="el-icon-loading"></i> {{ ciFeedbackStatusMsg }}</span>
                  <span v-else-if="ciFeedbackStatus === 'success'" class="card-ci-feedback-status card-ci-feedback-success">{{ ciFeedbackStatusMsg }}</span>
                  <span v-else-if="ciFeedbackStatus === 'error'" class="card-ci-feedback-status card-ci-feedback-error" :title="ciFeedbackStatusMsg">{{ ciFeedbackStatusMsg.length > 20 ? ciFeedbackStatusMsg.slice(0, 18) + '…' : ciFeedbackStatusMsg }}</span>
                </template>
              </template>
            </div>
            <div class="card-toolbar-content-gap"></div>
            <!-- 如果服务器提供了img_type，使用它；否则默认为png；双击图片新窗口铺满放大 -->
            <div class="card-image-stack" @contextmenu.prevent="openCardHtmlMenu($event)">
              <div v-if="cardMediaViewMode !== 'image'" class="card-html-chrome">
                <div class="card-html-chrome-left">
                  <button type="button" class="card-html-seg" :class="{ on: cardMediaViewMode === 'html' }" @click="setCardMediaViewMode('html')" title="预览">◉</button>
                  <button type="button" class="card-html-seg" :class="{ on: cardMediaViewMode === 'html_source' }" @click="setCardMediaViewMode('html_source')" title="HTML 源码">&lt;/&gt;</button>
                  <span class="card-html-chrome-title">{{ cardHtmlChromeTitle }}</span>
                </div>
                <div class="card-html-chrome-right">
                  <button type="button" class="card-html-seg" @click="copyCardHtml">Copy</button>
                  <button type="button" class="card-html-seg" @click="downloadCardHtml">Download</button>
                  <button type="button" class="card-html-seg" title="在浏览器新标签页打开（与预览同一地址）" @click="openCardHtmlInNewTab">新窗口</button>
                  <button type="button" class="card-html-seg primary" @click="setCardMediaViewMode('image')">图片</button>
                </div>
              </div>
              <img
                v-if="cardMediaViewMode === 'image' && imgClicked !== ''"
                :src="'data:' + (this.imgType || 'image/png') + ';base64,' + this.imgClicked"
                alt="Image"
                style="max-width: 100%; width: auto; height: auto; cursor: pointer;"
                @dblclick="openCardImageFullscreen"
              />
              <iframe
                v-else-if="cardMediaViewMode === 'html'"
                :key="'htmld2' + cardHtmlIframeKey"
                class="card-html-iframe"
                :class="{ 'card-html-iframe--grading-excerpt': isGradingExcerptCard }"
                :src="cardHtmlViewUrl"
                title="card html"
                sandbox="allow-scripts allow-same-origin allow-forms"
              ></iframe>
              <pre v-else-if="cardMediaViewMode === 'html_source'" class="card-html-source-pre">{{ cardHtmlSourceText }}</pre>
            </div>
            <!-- 交叉梳理卡：摘要 / 知识冲突 / Skill 簇 -->
            <div v-if="isCrossDocumentSuggestionCard" class="cross-reorg-tabs">
              <button type="button" class="cross-reorg-tab" :class="{ active: crossReorgTab==='suggest' }" @click="crossReorgTab='suggest'">交叉建议摘要</button>
              <button type="button" class="cross-reorg-tab" :class="{ active: crossReorgTab==='conflicts' }" @click="switchKnowledgeConflictTab">可能的知识冲突</button>
              <button type="button" class="cross-reorg-tab" :class="{ active: crossReorgTab==='skills' }" @click="switchCrossReorgSkillsTab">本子交叉 Skill 簇</button>
            </div>
            <div v-if="isCrossDocumentSuggestionCard && crossReorgTab==='conflicts'" class="kc-panel">
              <div v-if="kcLoading" class="cross-reorg-empty">知识冲突挖掘加载中…</div>
              <div v-else-if="!kcData" class="cross-reorg-empty">挖掘中或尚未生成…（生成交叉梳理后会后台产出）</div>
              <template v-else>
                <div class="kc-head">
                  <div class="kc-head-main">
                    <span class="kc-badge">冲突挖掘</span>
                    <span class="kc-meta">文档 Skill {{ (kcData.stats && kcData.stats.doc_skills) || 0 }} · 包成员 {{ (kcData.stats && kcData.stats.pack_skills) || 0 }} · 条目 {{ (kcData.items || []).length }}</span>
                  </div>
                  <span class="cross-reorg-status" :class="'st-' + (kcData.status || '')">{{ kcData.status || '—' }}</span>
                </div>
                <p v-if="kcData.note" class="kc-note">{{ kcData.note }}</p>
                <div v-if="kcData.status==='failed'" class="cross-reorg-empty">
                  挖掘失败{{ kcData.error ? ('：' + kcData.error) : '' }}；可稍后重新生成交叉梳理以重试。
                </div>
                <div v-else-if="kcData.status==='running'" class="cross-reorg-empty">挖掘进行中…</div>
                <div v-else-if="!(kcData.items || []).length" class="cross-reorg-empty">本轮未挖到足够站得住的知识冲突（宁可少报）。</div>
                <div
                  v-for="item in (kcData.items || [])"
                  :key="item.id"
                  class="kc-card"
                  :class="['kc-st-' + (item.user_status || 'pending'), { 'is-open': isKcItemOpen(item.id) }]"
                >
                  <div class="kc-card-top">
                    <span class="kc-cat">{{ item.category || '张力' }}</span>
                    <span class="kc-id">{{ item.id }}</span>
                  </div>
                  <h4 class="kc-title">{{ item.title }}</h4>
                  <p class="kc-summary" :class="{ 'is-clamped': !isKcItemOpen(item.id) }">{{ item.summary || item.insight }}</p>
                  <div v-if="(item.parties || []).length" class="kc-parties">
                    <span v-for="(p, pi) in item.parties" :key="pi" class="kc-party" :class="'kind-' + (p.kind || '')">{{ p.title || p.name }}</span>
                  </div>
                  <button
                    v-if="kcItemHasDetail(item)"
                    type="button"
                    class="kc-toggle"
                    @click="toggleKcItem(item.id)"
                  >{{ isKcItemOpen(item.id) ? '收起细节' : '展开张力 / 洞察' }}</button>
                  <div v-show="isKcItemOpen(item.id)" class="kc-detail">
                    <p v-if="item.tension" class="kc-tension"><b>张力</b>{{ item.tension }}</p>
                    <p v-if="item.insight && item.insight !== item.summary" class="kc-insight"><b>洞察</b>{{ item.insight }}</p>
                    <p v-if="item.why_not_forced" class="kc-why"><b>为何不牵强</b>{{ item.why_not_forced }}</p>
                    <div class="kc-note-box">
                      <label>补充说明</label>
                      <textarea
                        :value="item.user_note || ''"
                        rows="2"
                        placeholder="可改写或补充你的判断…"
                        @change="onKcNoteChange(item, $event)"
                      ></textarea>
                    </div>
                  </div>
                  <div class="kc-actions">
                    <button type="button" class="kc-act confirm" :class="{ on: item.user_status==='confirm' }" @click="setKcFeedback(item, 'confirm')">确认</button>
                    <button type="button" class="kc-act unsure" :class="{ on: item.user_status==='unsure' }" @click="setKcFeedback(item, 'unsure')">模糊不确认</button>
                    <button type="button" class="kc-act deny" :class="{ on: item.user_status==='deny' }" @click="setKcFeedback(item, 'deny')">否认</button>
                  </div>
                </div>
              </template>
            </div>
            <div v-if="isCrossDocumentSuggestionCard && crossReorgTab==='skills'" class="cross-reorg-skills-panel">
              <div v-if="crossReorgLoading" class="cross-reorg-empty">交叉 Skill 加载中…</div>
              <div v-else-if="!crossReorgIndex" class="cross-reorg-empty">交叉 Skill 生成中或尚未生成…（双击导入区生成交叉梳理后会后台产出）</div>
              <template v-else>
                <div class="cross-reorg-aim">
                  <div class="cross-reorg-aim-main">
                    <span class="cross-reorg-aim-label">本子目标</span>
                    <span class="cross-reorg-aim-text">{{ crossReorgIndex.notebook_aim_one_liner || '—' }}</span>
                  </div>
                  <span class="cross-reorg-status" :class="'st-' + (crossReorgIndex.status || '')">{{ crossReorgIndex.status || '—' }}</span>
                </div>

                <div class="cross-reorg-hub-card">
                  <div class="cross-reorg-hub-badge">入口 · 1</div>
                  <div class="cross-reorg-card-title">notebook-hub</div>
                  <div class="cross-reorg-card-desc">{{ (crossReorgIndex.hub && crossReorgIndex.hub.description) || '本子 Skill 总入口' }}</div>
                  <button type="button" class="cross-reorg-btn" @click="openCrossSkillViewer('notebook-hub', '本子 Skill 总入口')">查看入口全文</button>
                </div>

                <div
                  v-for="t in (crossReorgIndex.themes || [])"
                  :key="t.name"
                  class="cross-reorg-theme-card"
                  :class="{ 'is-failed': t.status==='failed', 'is-running': t.status==='running' }"
                >
                  <div class="cross-reorg-theme-head">
                    <div class="cross-reorg-card-title">{{ t.title || t.name }}</div>
                    <span class="cross-reorg-status" :class="'st-' + (t.status || '')">{{ t.status || '—' }}</span>
                  </div>
                  <div class="cross-reorg-card-desc">{{ (t.description || '').slice(0, 200) }}{{ (t.description||'').length>200?'…':'' }}</div>
                  <div v-if="t.how_to_use" class="cross-reorg-meta-row">
                    <span class="cross-reorg-meta-k">用好</span>
                    <span class="cross-reorg-meta-v">{{ t.how_to_use }}</span>
                  </div>
                  <div v-if="t.reuse_goal" class="cross-reorg-meta-row">
                    <span class="cross-reorg-meta-k">复用目标</span>
                    <span class="cross-reorg-meta-v">{{ t.reuse_goal }}</span>
                  </div>
                  <div v-if="(t.semantic_keywords || []).length" class="cross-reorg-kw-wrap">
                    <span
                      v-for="(kw, ki) in (t.semantic_keywords || []).slice(0, 10)"
                      :key="ki"
                      class="cross-reorg-kw"
                      :title="(kw && kw.gloss) || ''"
                    >{{ (kw && kw.term) || kw }}</span>
                    <span v-if="(t.semantic_keywords || []).length > 10" class="cross-reorg-kw more">+{{ (t.semantic_keywords || []).length - 10 }}</span>
                  </div>
                  <div class="cross-reorg-rel">
                    <div><b>关联文档</b> {{ (t.related_docs || []).join('、') || '—' }}</div>
                    <div><b>关联 Skill</b> {{ (t.related_existing_skills || []).join('、') || '—' }}</div>
                  </div>
                  <button
                    v-if="t.status==='ok'"
                    type="button"
                    class="cross-reorg-btn"
                    @click="openCrossSkillViewer(t.name, t.title || t.name)"
                  >查看主题全文</button>
                  <div v-else-if="t.error" class="cross-reorg-err">{{ t.error }}</div>
                </div>
              </template>
            </div>
            <!-- 非编辑状态显示解析后的内容，点击进入编辑状态 -->
            <div v-if="(!isCrossDocumentSuggestionCard || crossReorgTab==='suggest') && !isEditingContent" 
                @click="editContentInline" 
                @mousedown="handleMouseDown"
                @mouseup="handleMouseUp"
                class="content-hover-area"
                style="cursor: pointer; padding: 5px; border-radius: 4px;">
              <!-- <AnswerParser :answer="cardInfo.content" @startReading="startFromIndex" @doubleClickOver="doubleClickOver"/> -->
              <AnswerParser
                :key="'normal-p' + contentPageIndex"
                :answer="normalPagedDisplayContent"
                @startReading="startFromIndex"
                @doubleClickOver="doubleClickOver"
              />
              <div v-if="normalContentPages.length > 1" class="nkcn-card-page-nav" @click.stop>
                <button type="button" :disabled="contentPageIndex <= 0" @click="contentPageIndex = Math.max(0, contentPageIndex - 1)">上一页</button>
                <span>{{ contentPageIndex + 1 }} / {{ normalContentPages.length }}</span>
                <button type="button" :disabled="contentPageIndex >= normalContentPages.length - 1" @click="contentPageIndex = Math.min(normalContentPages.length - 1, contentPageIndex + 1)">下一页</button>
              </div>
            </div>
            <!-- 编辑状态显示文本框 -->
            <el-input
              v-else-if="(!isCrossDocumentSuggestionCard || crossReorgTab==='suggest') && isEditingContent"
              id="edit-content-input"
              type="textarea"
              :rows="18"
              v-model="tempContent"
              style="width: 100%; background-color: #e8f4e8;"
              class="contentInput"
            ></el-input>
          </div>
        </div>

        <!-- 交叉 Skill 全文查看：挂到 body，避免嵌在卡片弹窗层内 -->
        <Teleport to="body">
          <div v-if="crossSkillViewerVisible" class="skill-dlg-overlay" @click.self="closeCrossSkillViewer">
            <div class="skill-dlg skill-dlg--edit" @click.stop>
              <div class="skill-dlg-header">
                <div>
                  <h3>查看交叉 Skill</h3>
                  <p class="skill-dlg-sub">{{ crossSkillViewerTitle || crossSkillViewerName || '未选择' }}</p>
                </div>
                <button class="skill-dlg-close" type="button" @click="closeCrossSkillViewer">×</button>
              </div>
              <div class="skill-dlg-toolbar">
                <div class="skill-tabs">
                  <button
                    type="button"
                    class="skill-tab"
                    :class="{ active: crossSkillViewMode === 'preview' }"
                    @click="crossSkillViewMode = 'preview'"
                  >Markdown 预览</button>
                  <button
                    type="button"
                    class="skill-tab"
                    :class="{ active: crossSkillViewMode === 'source' }"
                    @click="crossSkillViewMode = 'source'"
                  >查看源码</button>
                </div>
              </div>
              <div class="skill-dlg-body skill-dlg-body--edit">
                <div v-if="crossSkillViewMode === 'preview'" class="skill-md-preview">
                  <div v-if="crossSkillFrontmatterRows.length" class="skill-fm-box">
                    <div class="skill-fm-title">Frontmatter</div>
                    <div class="skill-fm-row" v-for="(row, i) in crossSkillFrontmatterRows" :key="i">
                      <span class="skill-fm-key">{{ row.key }}</span>
                      <span
                        class="skill-fm-val"
                        :class="{ 'is-description': row.key === 'description' }"
                        v-html="formatSkillDescDisplay(row.value)"
                      ></span>
                    </div>
                  </div>
                  <div class="skill-md-body" v-html="crossSkillPreviewHtml"></div>
                </div>
                <pre v-else class="skill-md-source">{{ crossSkillViewerRaw }}</pre>
              </div>
              <div class="skill-dlg-footer">
                <span class="skill-dlg-hint">{{ crossSkillLineCount }} 行 · 交叉 Skill 只读</span>
                <div class="skill-dlg-footer-actions">
                  <button class="skill-btn skill-btn--ghost" type="button" @click="closeCrossSkillViewer">关闭</button>
                </div>
              </div>
            </div>
          </div>
        </Teleport>

        <!-- 后置索引区域 -->
        <!-- <div v-if="cardInfo.postIndex && cardInfo.postIndex !== ''"  -->
        <div class="card-type-section" 
            style="background-color: #c8d9f2; padding: 10px; border-radius: 8px; margin-bottom: 15px; display: flex; justify-content: space-between; align-items: center;">
          <div class="card-postindex" style="display: flex; align-items: center;">
            <span style="font-weight: bold; color: #0055cc; font-size: 1.1em;" @click="openPostIndexDialog">∞后置索引：</span>
            <span style="font-size: 1.0em;">{{ postIndexTitle }}</span>
          </div>
        </div>

        <!-- 🔥 四色/DMT类型手动修改 -->
        <div class="card-type-edit-dialog" v-if="isAuthor || isMarkLee" style="margin-bottom: 15px;">
          <div class="card-type-section" 
              style="background-color: #f0f0f0; padding: 10px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
            <span class="type-edit-label" @click="showTypeEditDialog = true" title="点击修改卡片类型" style="cursor: pointer;">
              <span class="type-label-text">类型：</span>
              <span class="type-value" :style="{ color: getFourColorTypeColor(fourColorType) }">
                {{ getFourColorTypeDisplay(fourColorType) }}
              </span>
              <span class="type-separator">/</span>
              <span class="type-value" :style="{ color: getDmtLevelColor(dmtLevel) }">
                {{ getDmtLevelDisplay(dmtLevel) }}
              </span>
            </span>
          </div>
        </div>

        <div style="padding: 15px; border-radius: 8px;">
          <h3>卡标部分</h3>
        </div>
        <div style="background-color: #9966cc; padding: 10px; border-radius: 8px;">
          <p ref="scoreSFT" :style="textStyleSFT"><b>红蓝卡标深评打分(微调Qwen3 32b):<br></b>{{ cardInfo.scoreSFT < 0 ? '?' : cardInfo.scoreSFT }}</p>
        </div>
        <div style="background-color: #e6f0ff; padding: 10px; border-radius: 8px;">
          <p v-if="splitReasonSFT.length > 0" :style="textStyleSFT"><b>红蓝深评理由:<br></b> {{ splitReasonSFT[0] || "正在打分，等待解析打分理由" }} </p>
        </div>
        <div style="background-color: #fff9d6; padding: 10px; border-radius: 8px;">
          <p v-if="splitReasonSFT.length > 1" :style="textStyleSFT"><b>红蓝深评改进建议:&nbsp;&nbsp;<button @click="speakTextBeginSFT">从头开始朗读</button><button @click="stopSpeech">停止朗读</button><br></b> 
            <!-- {{ splitReasonSFT[1] || "正在打分，等待解析改进建议" }}  -->
            <AnswerParser 
              :answer="splitReasonSFT[1] || '正在打分，等待解析改进建议'" 
              @startReading="startFromIndexSFT" 
              @doubleClickOver="doubleClickOver"
            />
          </p>
        </div>
        <br><br>
        <div style="background-color: #baa6e0; padding: 10px; border-radius: 8px;">
          <p :style="textStyle"><b>红蓝卡标浅评打分(GPT4o prompt):<br></b>{{ this.score }}</p>
        </div>
        <div style="background-color: #f5faff; padding: 10px; border-radius: 8px;">
          <p v-if="splitReason.length > 0" :style="textStyle"><b>红蓝浅评理由:<br></b> {{ splitReason[0] || "正在打分，等待解析打分理由" }} </p>
        </div>
        <div style="background-color: #fffdf0; padding: 10px; border-radius: 8px;">
          <p v-if="splitReason.length > 1" :style="textStyle"><b>红蓝浅评改进建议:<br></b> {{ splitReason[1] || "正在打分，等待解析改进建议" }} </p>
        </div>
      </div>
      <br><br>
      <div class="card-button">
        <button class="card-delete" @click="deleteCard">删除卡片</button>
        <button class="card-history" @click="backHistory(this.cardInfo.history, title)">回溯历史</button>
        <button class="card-paste" @click="copyContentWithEmptyLines">复制卡片</button>
      </div>
    </div>

  </div>

  <!-- 共生区 -->
  <div class="intergrowth-area" v-if="isCardDialogVisible && isInterGrowthAreaNeed">
    <h3 style="margin-bottom: 16px;">共生理解打点区</h3>

    <!-- 目标区 -->
    <div class="area-section goal-area">
      <h4 class="area-title">目标部分</h4>
      <div v-for="section in getAreaSections('目标区')" :key="section.number" 
          :class="['intergrowth-section', section.isCompleted ? 'completed' : 'incomplete']">
        <div class="section-content" @click="editSection(getInterGrowthSectionIndex(section))">
          <div v-html="formatSectionContent(section.content)"></div>
          <!-- 添加分割线 -->
          <hr v-if="section.isCompleted && getUserRatings(section.number) && Object.keys(getUserRatings(section.number)).length > 0" 
              class="rating-divider">
          <!-- 添加评分指示器显示 -->
          <div v-if="section.isCompleted" class="user-ratings">
            <div v-for="(rating, user) in getUserRatings(section.number)" :key="user" class="user-rating">
              <div class="user-rating-row">
                <div style="margin-right: 5px;"><strong>{{user}}得分:</strong></div>
                <div class="user-rating-score" :style="getRatingStyle(rating.score)" :title="`${user}评分: ${rating.score}`">
                  {{ rating.score }}
                </div>
                <button class="suggestions-button" @click.stop="showSuggestions(user, section.number)" title="查看改进建议">...</button>
              </div>
            </div>
          </div>
        </div>
        
        <div v-if="isEditing && currentEditingIndex === getInterGrowthSectionIndex(section) && !isAuthor && !isMarkLee" class="edit-area">
          <textarea v-model="editContentInterGrowth" placeholder="请在此输入内容"></textarea>
          <div class="edit-buttons">
            <button class="ai-feedback-btn" @click="getAIFeedback(getInterGrowthSectionIndex(section))" :disabled="isLoadingAI">
              <span v-if="!isLoadingAI">获取AI评分与建议</span>
              <span v-else>评分中...</span>
            </button>
            <button class="confirm-btn" @click="confirmEdit(getInterGrowthSectionIndex(section))">确认</button>
          </div>
          
          <!-- AI评分与建议区域 -->
          <div v-if="currentAIFeedback" class="ai-feedback-area">
            <div class="feedback-header">
              <div class="score-display" :style="getRatingStyle(currentAIFeedback.score)">
                {{ currentAIFeedback.score }}
              </div>
              <div class="feedback-title">评分: {{ currentAIFeedback.score }}/5.0 - {{ currentAIFeedback.title }}</div>
            </div>
            <div class="feedback-content">
              <div v-for="(point, idx) in currentAIFeedback.points" :key="idx" class="suggestion-item">
                <span class="suggestion-icon">⚠</span>
                <span class="suggestion-text">{{ point }}</span>
              </div>
            </div>
            <div class="feedback-actions">
              <button class="modify-btn" @click="modifyWithAI" :disabled="isModifying">
                {{ isModifying ? '修改中...' : 'AI辅助修改' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 任务区 -->
    <div class="area-section task-area">
      <h4 class="area-title">任务部分</h4>
      <div v-for="section in getAreaSections('任务区')" :key="section.number" 
          :class="['intergrowth-section', section.isCompleted ? 'completed' : 'incomplete']">
        <div class="section-content" @click="editSection(getInterGrowthSectionIndex(section))">
          <div v-html="formatSectionContent(section.content)"></div>
          <!-- 添加分割线 -->
          <hr v-if="section.isCompleted && getUserRatings(section.number) && Object.keys(getUserRatings(section.number)).length > 0" 
              class="rating-divider">
          <!-- 添加评分指示器显示 -->
          <div v-if="section.isCompleted" class="user-ratings">
            <div v-for="(rating, user) in getUserRatings(section.number)" :key="user" class="user-rating">
              <div class="user-rating-row">
                <div style="margin-right: 5px;"><strong>{{user}}得分:</strong></div>
                <div class="user-rating-score" :style="getRatingStyle(rating.score)" :title="`${user}评分: ${rating.score}`">
                  {{ rating.score }}
                </div>
                <button class="suggestions-button" @click.stop="showSuggestions(user, section.number)" title="查看改进建议">...</button>
              </div>
            </div>
          </div>
        </div>
        
        <div v-if="isEditing && currentEditingIndex === getInterGrowthSectionIndex(section) && !isAuthor && !isMarkLee" class="edit-area">
          <textarea v-model="editContentInterGrowth" placeholder="请在此输入内容"></textarea>
          <div class="edit-buttons">
            <button class="ai-feedback-btn" @click="getAIFeedback(getInterGrowthSectionIndex(section))" :disabled="isLoadingAI">
              <span v-if="!isLoadingAI">获取AI评分与建议</span>
              <span v-else>评分中...</span>
            </button>
            <button class="confirm-btn" @click="confirmEdit(getInterGrowthSectionIndex(section))">确认</button>
          </div>
          
          <!-- AI评分与建议区域 -->
          <div v-if="currentAIFeedback" class="ai-feedback-area">
            <div class="feedback-header">
              <div class="score-display" :style="getRatingStyle(currentAIFeedback.score)">
                {{ currentAIFeedback.score }}
              </div>
              <div class="feedback-title">评分: {{ currentAIFeedback.score }}/5.0 - {{ currentAIFeedback.title }}</div>
            </div>
            <div class="feedback-content">
              <div v-for="(point, idx) in currentAIFeedback.points" :key="idx" class="suggestion-item">
                <span class="suggestion-icon">⚠</span>
                <span class="suggestion-text">{{ point }}</span>
              </div>
            </div>
            <div class="feedback-actions">
              <button class="modify-btn" @click="modifyWithAI" :disabled="isModifying">
                {{ isModifying ? '修改中...' : 'AI辅助修改' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 分工区 -->
    <div class="area-section division-area">
      <h4 class="area-title">分工部分</h4>
      <div v-for="section in getAreaSections('分工区')" :key="section.number" 
          :class="['intergrowth-section', section.isCompleted ? 'completed' : 'incomplete']">
        <div class="section-content" @click="editSection(getInterGrowthSectionIndex(section))">
          <div v-html="formatSectionContent(section.content)"></div>
          <!-- 添加分割线 -->
          <hr v-if="section.isCompleted && getUserRatings(section.number) && Object.keys(getUserRatings(section.number)).length > 0" 
              class="rating-divider">
          <!-- 添加评分指示器显示 -->
          <div v-if="section.isCompleted" class="user-ratings">
            <div v-for="(rating, user) in getUserRatings(section.number)" :key="user" class="user-rating">
              <div class="user-rating-row">
                <div style="margin-right: 5px;"><strong>{{user}}得分:</strong></div>
                <div class="user-rating-score" :style="getRatingStyle(rating.score)" :title="`${user}评分: ${rating.score}`">
                  {{ rating.score }}
                </div>
                <button class="suggestions-button" @click.stop="showSuggestions(user, section.number)" title="查看改进建议">...</button>
              </div>
            </div>
          </div>
        </div>
        
        <div v-if="isEditing && currentEditingIndex === getInterGrowthSectionIndex(section) && !isAuthor && !isMarkLee" class="edit-area">
          <textarea v-model="editContentInterGrowth" placeholder="请在此输入内容"></textarea>
          <div class="edit-buttons">
            <button class="ai-feedback-btn" @click="getAIFeedback(getInterGrowthSectionIndex(section))" :disabled="isLoadingAI">
              <span v-if="!isLoadingAI">获取AI评分与建议</span>
              <span v-else>评分中...</span>
            </button>
            <button class="confirm-btn" @click="confirmEdit(getInterGrowthSectionIndex(section))">确认</button>
          </div>
          
          <!-- AI评分与建议区域 -->
          <div v-if="currentAIFeedback" class="ai-feedback-area">
            <div class="feedback-header">
              <div class="score-display" :style="getRatingStyle(currentAIFeedback.score)">
                {{ currentAIFeedback.score }}
              </div>
              <div class="feedback-title">评分: {{ currentAIFeedback.score }}/5.0 - {{ currentAIFeedback.title }}</div>
            </div>
            <div class="feedback-content">
              <div v-for="(point, idx) in currentAIFeedback.points" :key="idx" class="suggestion-item">
                <span class="suggestion-icon">⚠</span>
                <span class="suggestion-text">{{ point }}</span>
              </div>
            </div>
            <div class="feedback-actions">
              <button class="modify-btn" @click="modifyWithAI" :disabled="isModifying">
                {{ isModifying ? '修改中...' : 'AI辅助修改' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <div v-if="isAuthor || isMarkLee" class="author-edit-area">
      <div class="format-tip">必须按照如下格式：<br>1.xx<br>2.xx<br>3.xx<br>4.xx<br>（即必须以序号开头，用换行隔开）</div>
      <textarea v-model="tempInterGrowthTA2GL" placeholder="请输入内容" :disabled="!isAuthor"></textarea>
      <!-- 区域分配部分 -->
      <div class="area-assignment" v-if="isAuthor">
        <h4>问题区域分配：</h4>
        <div class="question-area-selector" v-for="num in extractQuestionNumbers(tempInterGrowthTA2GL)" :key="num">
          <span class="question-number">问题 {{ num }}:</span>
          <select v-model="questionAreaMapping[num]">
            <option value="目标区">目标区</option>
            <option value="任务区">任务区</option>
            <option value="分工区">分工区</option>
          </select>
        </div>
      </div>

      <button @click="isAuthor ? saveAuthorEdit() : null" :disabled="!isAuthor">确认</button>
    </div>
  </div>

  <!-- 生成中的加载提示 -->
  <div v-if="isCardDialogVisible && isInterGrowthAreaNeed && isGeneratingAdvice" class="loading-advice">
    <div class="loading-container">
      <div class="loading-spinner"></div>
      <p>正在生成综合建议，请耐心等待一会...</p>
    </div>
  </div>

  <!-- 卡片右栏红蓝建议详情弹窗 -->
  <div v-if="isCardDialogVisible && isInterGrowthAreaNeed && showingSuggestions" class="suggestions-modal">
    <div class="suggestions-content">
      <div class="modal-header">
        <h4>评分: {{ activeSuggestions.score }}/5.0 - {{ getRatingDescription(activeSuggestions.score) }}</h4>
        <button class="close-btn" @click="showingSuggestions = false">×</button>
      </div>
      <div class="suggestion-body" v-html="formattedSuggestion"></div>
      <div class="modal-footer">
        <button class="close-btn-bottom" @click="showingSuggestions = false">关闭</button>
      </div>
    </div>
  </div>

  <!-- 卡片右栏AI修改加载遮罩 -->
  <div v-if="isCardDialogVisible && isInterGrowthAreaNeed && (isModifying || isLoadingAI)" class="ai-modifying-overlay">
    <div class="loading-container">
      <div class="loading-spinner"></div>
      <p v-if="isModifying">AI辅助修改中，请稍等...</p>
      <p v-if="isLoadingAI">AI评分更新中，请稍等...</p>
    </div>
  </div>

  <!-- 卡片中栏主体内容展开弹窗 -->
  <div v-if="expandedView.visible" class="expanded-view-overlay" @click="closeExpandedView">
    <div class="expanded-view-content" @click.stop>
      <div class="expanded-view-header">
        <h3>{{ expandedView.title }}</h3>
        <div class="close" @click="closeExpandedView">&times;</div>
      </div>
      <div class="expanded-view-body">
        <div v-if="expandedView.type === 'main'">
          <p><b>卡片内容：</b></p>
          <AnswerParser :key="showLastContent ? 'last' : 'current'" :answer="showLastContent ? cardInfo.lastContent : cardInfo.content" />
        </div>
        <div v-else-if="expandedView.type === 'sftReason'">
          <p><b>红蓝深评理由：</b></p>
          <p>{{ splitReasonSFT[0] || "正在打分，等待解析打分理由" }}</p>
        </div>
        <div v-else-if="expandedView.type === 'sftSuggestion'">
          <p><b>红蓝深评改进建议：</b></p>
          <AnswerParser :answer="splitReasonSFT[1] || '正在打分，等待解析改进建议'" />
        </div>
        <div v-else-if="expandedView.type === 'reason'">
          <p><b>红蓝浅评理由：</b></p>
          <p>{{ splitReason[0] || "正在打分，等待解析打分理由" }}</p>
        </div>
        <div v-else-if="expandedView.type === 'suggestion'">
          <p><b>红蓝浅评改进建议：</b></p>
          <p>{{ splitReason[1] || "正在打分，等待解析改进建议" }}</p>
        </div>
      </div>
    </div>
  </div>

  <el-dialog v-model="showEditDialog" class="editContentDialog" :close-on-click-modal="false"
    :close-on-press-escape="false">
    <h1 class="createNotebookTitle">修改卡片文本</h1>
    <el-form :model="editForm" label-width="80px">
      <el-form-item label="内容标题" style="margin-top: 10px;">
        <el-input :rows="8" v-model="editForm.contentTitle"></el-input>
      </el-form-item>
      <el-form-item label="关键词" style="margin-top: 10px;">
        <el-input :rows="8" v-model="editForm.keyWords"></el-input>
      </el-form-item>

      <el-form-item label="卡片内容">
        <el-input class="contentInput" type="textarea" :rows="8" v-model="editForm.content"></el-input>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="footer">
        <el-button class="cancelButton" @click="cancelDialog">取 消</el-button>
        <el-button class="editButton" type="primary" @click="saveContent">确 定</el-button>
      </div>
    </template>
  </el-dialog>

  <!-- 图无损理解反馈：选择要使用的 CI 分析 -->
  <el-dialog v-model="ciFeedbackDialogVisible" title="选择图片理解分析" width="560px" append-to-body class="ci-feedback-dialog">
    <p v-if="ciAnalysesList.length === 0" class="ci-feedback-empty">暂无已完成的图片理解分析，请先在「连续多图理解」中完成分析。</p>
    <div v-else class="ci-feedback-list-wrap">
      <p class="ci-feedback-list-title">选择一条分析结果用于迭代卡片正文：</p>
      <div class="ci-feedback-list">
        <div v-for="a in ciAnalysesList" :key="a.analysis_id" class="ci-analysis-item">
          <el-radio v-model="selectedCiAnalysisId" :label="a.analysis_id">
            <span class="ci-analysis-label" :title="ciAnalysisItemTitle(a)">{{ a.mode === 'group' ? '多图' : '单图' }} · {{ ciAnalysisItemShort(a) }}</span>
            <span v-if="a.created_at" class="ci-analysis-time">{{ formatCiTime(a.created_at) }}</span>
          </el-radio>
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="ciFeedbackDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="isCiFeedbackLoading" :disabled="!selectedCiAnalysisId" @click="doCiFeedbackIterate">确定并迭代</el-button>
    </template>
  </el-dialog>

  <!-- 卡片生图 / 新生图：选择模型与长宽比 -->
  <el-dialog
    v-model="cardImageGenDialogVisible"
    :title="cardImageGenDialogTitle"
    width="440px"
    append-to-body
    class="card-image-gen-dialog"
  >
    <el-form label-width="88px" label-position="left">
      <el-form-item label="生图模型">
        <el-radio-group v-model="cardImageProvider">
          <el-radio label="gpt">GPT</el-radio>
          <el-radio label="gemini">Gemini</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="长宽比">
        <el-radio-group v-model="cardImageAspectRatio">
          <el-radio label="1:1">1:1</el-radio>
          <el-radio label="16:9">16:9</el-radio>
          <el-radio label="9:16">9:16</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="cardImageGenDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="confirmCardImageGen">确定生图</el-button>
    </template>
  </el-dialog>

  <!-- 迭代图：可选填写具体修改要求 + 可选参考图（如手绘草图） -->
  <el-dialog v-model="iterateImageDialogVisible" title="迭代图" :width="iterateOverlayTestMode ? '1120px' : '620px'" append-to-body>
    <p class="iterate-image-dialog-hint">改图依据：① 卡片内容文字变化；② 下方具体修改要求（选填）；③ 参考图（选填）；④ 在图上框选区域（选填）：有框选时仅对<strong>框内裁切图</strong>迭代，生成后<strong>自动拼回原图</strong>；可选是否同时输入<strong>整张原图</strong>作邻接参考。</p>
    <div style="margin-top: 8px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
      <span style="font-size: 13px; color: #666; white-space: nowrap;">迭代模型：</span>
      <el-radio-group v-model="iterateImageProvider" size="small">
        <el-radio label="gpt">GPT</el-radio>
        <el-radio label="gemini">Gemini</el-radio>
      </el-radio-group>
      <span style="font-size: 13px; color: #666; white-space: nowrap;">清晰度：</span>
      <el-select v-model="iterateImageQuality" size="small" style="width: 140px;">
        <el-option label="普通（现有逻辑）" value="normal"></el-option>
        <el-option label="高清（4K）" value="high"></el-option>
      </el-select>
      <label class="overlay-test-mode-switch">
        <input type="checkbox" v-model="iterateOverlayTestMode" />
        <span>覆盖层模式</span>
      </label>
    </div>
    <div v-if="iterateOverlayTestMode" class="overlay-test-panel">
      <div class="overlay-test-layout">
        <div class="overlay-test-left">
          <p class="overlay-test-desc">先点「生成覆盖层」，再在下图中直接拖动框体（平移）或拖动边缘点（单方向拉伸），最后点「应用覆盖层」。</p>
          <div class="overlay-test-base-row">
            <span class="overlay-test-label">底图来源：</span>
            <el-select v-model="overlayTestBaseSource" size="small" style="width: 180px;">
              <el-option label="当前卡片图" value="current"></el-option>
              <el-option label="迭代前备份图（若有）" value="backup"></el-option>
              <el-option label="自定义上传/粘贴" value="custom"></el-option>
            </el-select>
            <input ref="overlayBaseFileInput" type="file" accept="image/*" class="iterate-image-file-input" @change="onOverlayBaseFileChange" />
            <el-button size="small" plain @click="triggerOverlayBaseUpload">上传底图</el-button>
            <el-button size="small" plain @click="markPasteOverlayBase">粘贴底图</el-button>
          </div>
          <div class="overlay-test-opacity-row">
            <span class="overlay-test-label">覆盖层透明度：</span>
            <el-slider v-model="overlayTestContentOpacity" :min="0" :max="100" :step="1" style="width: 220px;" />
            <span class="overlay-test-opacity-text">{{ overlayTestContentOpacity }}%</span>
          </div>
          <div class="overlay-test-actions">
            <el-button size="small" type="primary" :loading="overlayTestGenerating" @click="generateOverlayTestLayer">生成覆盖层</el-button>
            <el-button size="small" :disabled="!overlayTestLayerDataUrl || overlayTestApplying" :loading="overlayTestApplying" @click="applyOverlayTestLayer">应用覆盖层</el-button>
            <el-button size="small" :disabled="!overlayTestLayerDataUrl" @click="resetOverlayTestTransform">重置位置</el-button>
            <el-button size="small" plain :disabled="!overlayTestLayerDataUrl || !overlayTestBaseDisplaySrc" @click="openOverlayQaDialogForDebug">调试对齐弹窗</el-button>
          </div>
          <div v-if="overlayTestLayerDataUrl && overlayTestBaseDisplaySrc" class="overlay-test-stage" @mousedown.prevent="onOverlayTestMouseDown">
            <img
              ref="overlayTestBaseImg"
              class="overlay-test-base-img"
              :src="overlayTestBaseDisplaySrc"
              alt="原图"
              draggable="false"
            />
            <img
              class="overlay-test-layer"
              :src="overlayTestLayerPreviewDataUrl || overlayTestLayerDataUrl"
              :style="overlayTestLayerImageStyle"
              alt="覆盖层预览"
              draggable="false"
            />
            <div class="overlay-test-box" :style="overlayTestBoxStyle">
              <span class="overlay-test-handle overlay-test-handle-left" data-handle="left"></span>
              <span class="overlay-test-handle overlay-test-handle-right" data-handle="right"></span>
              <span class="overlay-test-handle overlay-test-handle-top" data-handle="top"></span>
              <span class="overlay-test-handle overlay-test-handle-bottom" data-handle="bottom"></span>
            </div>
          </div>
        </div>
        <div class="overlay-test-right" v-if="overlayTestLayerDataUrl">
          <div class="overlay-iterate-panel">
        <p class="overlay-iterate-title">覆盖层二次迭代（先改覆盖层，再合回底图）</p>
        <p class="overlay-iterate-desc">可像卡片迭代一样：先框选覆盖层中的局部，再写修改要求并加参考图，点击「迭代覆盖层」后替换当前覆盖层预览。</p>
        <div class="overlay-iterate-stage" @mousedown.prevent="onOverlayIterateRegionMouseDown">
          <img ref="overlayIterateImg" :src="overlayTestLayerPreviewDataUrl || overlayTestLayerDataUrl" alt="覆盖层编辑区" draggable="false" />
          <div v-if="overlayIterateRegionCommittedStyle" class="iterate-region-rect" :style="overlayIterateRegionCommittedStyle"></div>
          <div v-if="overlayIterateRegionDrawingStyle" class="iterate-region-rect iterate-region-rect-drawing" :style="overlayIterateRegionDrawingStyle"></div>
        </div>
        <div class="overlay-iterate-toolbar">
          <el-button size="small" @click="overlayIterateEditRegionNorm = null">清除选区</el-button>
          <el-button size="small" type="warning" plain :disabled="!overlayTestLayerDataUrl" @click="openOverlayManualEraseDialog">手动修改</el-button>
          <span v-if="overlayIterateEditRegionNorm" class="iterate-region-coords">已选：{{ overlayIterateRegionSummary }}</span>
        </div>
        <el-input
          ref="overlayRightInstructionInput"
          v-model="overlayIterateInstruction"
          type="textarea"
          :rows="3"
          placeholder="例如：仅把右上角标签改成更醒目、字体更统一；其余标注保持不变"
          maxlength="1200"
          show-word-limit
        />
        <div class="overlay-iterate-ref-row">
          <el-button size="small" plain @click="triggerOverlayIterateReferenceUpload">选择参考图</el-button>
          <span class="iterate-image-paste-hint">粘贴默认会到“上方参考图”；如需粘贴底图请先点“粘贴底图”</span>
          <el-button v-if="overlayIterateReferenceDataUrl" size="small" @click="overlayIterateReferenceDataUrl = ''">清除参考图</el-button>
        </div>
        <div v-if="overlayIterateReferenceDataUrl" class="iterate-image-reference-preview">
          <img :src="overlayIterateReferenceDataUrl" alt="覆盖层迭代参考图" />
        </div>
        <input ref="overlayIterateRefFileInput" type="file" accept="image/*" class="iterate-image-file-input" @change="onOverlayIterateReferenceFileChange" />
        <div class="overlay-iterate-actions">
          <el-button size="small" :disabled="!canOverlayHistoryPrev" @click="goOverlayHistoryPrev">上一步</el-button>
          <el-button size="small" :disabled="!canOverlayHistoryNext" @click="goOverlayHistoryNext">下一步</el-button>
          <span class="overlay-iterate-history-text" v-if="overlayTestHistory.length > 0">历史 {{ overlayTestHistoryIndex + 1 }}/{{ overlayTestHistory.length }}</span>
          <el-button size="small" type="primary" :loading="overlayIterateSubmitting" @click="submitOverlayIterate">迭代覆盖层</el-button>
        </div>
          </div>
        </div>
      </div>
    </div>
    <div v-if="imgClicked && imgClicked !== '' && !iterateOverlayTestMode" class="iterate-region-panel">
      <p class="iterate-region-title">可编辑区域（选填）</p>
      <p class="iterate-region-desc">在下方<strong>当前卡片图</strong>上按住左键拖拽框选矩形：服务端以<strong>框内裁切图</strong>为主输入迭代，结果<strong>自动贴回</strong>该矩形（框外不变）。可勾选是否同时把<strong>整张原图</strong>交给模型作位置/邻接参考。</p>
      <div class="iterate-region-toolbar">
        <el-button size="small" @click="clearIterateEditRegion">清除选区</el-button>
        <label v-if="iterateEditRegionNorm" class="iterate-crop-full-switch">
          <input type="checkbox" v-model="iterateCropIncludeFullImage" />
          <span>同时输入整张原图（邻接参考）</span>
        </label>
        <span v-if="iterateEditRegionNorm" class="iterate-region-coords">已选（相对整图 0~1）：{{ iterateRegionSummary }}</span>
      </div>
      <div class="iterate-region-stage" @mousedown.prevent="onIterateRegionMouseDown">
        <img
          ref="iterateRegionImg"
          :src="'data:' + (imgType || 'image/png') + ';base64,' + imgClicked"
          alt="当前卡片图"
          draggable="false"
        />
        <div v-if="iterateRegionCommittedStyle" class="iterate-region-rect" :style="iterateRegionCommittedStyle"></div>
        <div v-if="iterateRegionDrawingStyle" class="iterate-region-rect iterate-region-rect-drawing" :style="iterateRegionDrawingStyle"></div>
      </div>
    </div>
    <div v-if="iterateOverlayTestMode" class="iterate-dmt-preset-row">
      <el-button
        size="small"
        type="primary"
        plain
        :loading="dmtOverlayPromptStreaming && !dmtOverlayRefinePassActive"
        :disabled="!imgClicked || imgClicked === '' || dmtOverlayPromptStreaming"
        @click="runDmtMicroLayoutOverlayPrompt"
      >DMT微版面化</el-button>
      <el-button
        size="small"
        type="primary"
        plain
        :loading="dmtOverlayPromptStreaming && dmtOverlayRefinePassActive"
        :disabled="!imgClicked || imgClicked === '' || dmtOverlayPromptStreaming || !canRunDmtOverlayRefine"
        @click="runDmtOverlayRefinePrompt"
      >检验优化一遍</el-button>
      <span class="iterate-dmt-preset-hint">先点「DMT微版面化」流式生成初稿（Gemini 3.1）；完成后如需对照原图润色，再点「检验优化一遍」二次流式。下方文本框会显示当前流式内容；生成两版后可用「选用版本」在初稿与检验优化稿之间切换，再点「生成覆盖层」。</span>
    </div>
    <div v-if="iterateOverlayTestMode && dmtOverlayRefinedText" class="iterate-dmt-version-row">
      <span class="iterate-dmt-version-label">选用版本：</span>
      <el-radio-group v-model="dmtOverlayActiveVersion" size="small" @change="onDmtOverlayVersionChange">
        <el-radio-button label="draft">初稿（微版面化）</el-radio-button>
        <el-radio-button label="refined">检验优化后</el-radio-button>
      </el-radio-group>
      <span class="iterate-dmt-version-hint">切换会覆盖下方文本框内容；若需手改请先选好版本再编辑。</span>
    </div>
    <el-input
      ref="iterateLeftInstructionInput"
      v-model="iterateImageRevisionInstruction"
      type="textarea"
      :rows="4"
      placeholder="例如：去掉图中右下角的章节页码信息；修改图上方大标题变得更实际具体（其余保持不变）；将某板块的小标题改为……"
      maxlength="6000"
      show-word-limit
    />
    <div class="iterate-image-reference-zone">
      <span class="iterate-image-reference-label">参考图（选填）</span>
      <input
        ref="iterateImageFileInput"
        type="file"
        accept="image/*"
        class="iterate-image-file-input"
        @change="onIterateReferenceFileChange"
      />
      <div class="iterate-image-reference-actions">
        <el-button size="small" type="primary" plain @click="triggerIterateReferenceUpload">选择图片</el-button>
        <span class="iterate-image-paste-hint">或直接粘贴（Ctrl+V）</span>
        <el-button v-if="iterateImageReferenceDataUrl" size="small" @click="clearIterateReferenceImage">清除</el-button>
      </div>
      <div v-if="iterateImageReferenceDataUrl" class="iterate-image-reference-preview">
        <img :src="iterateImageReferenceDataUrl" alt="参考图预览" />
        <p class="iterate-image-reference-hint">表示图中某区域希望的大致效果或感觉，将与上方文字一起传给模型</p>
      </div>
    </div>
    <template #footer>
      <el-button @click="iterateImageDialogVisible = false">取消</el-button>
      <el-button type="primary" :disabled="iterateImageSubmitting || iterateOverlayTestMode" @click="submitIterateCardImage">{{ iterateOverlayTestMode ? '覆盖层模式请用上方按钮' : '确定并迭代' }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="overlayQaDialogVisible" title="质检前先对齐覆盖层" width="980px" append-to-body :close-on-click-modal="false">
    <p class="overlay-test-desc" style="margin-bottom: 8px;">
      请先拖拽平移/单向拉伸覆盖层，让其与底图对齐。确认后将把「合成后的整卡图 + 初步覆盖层图」发给模型做 5+1 质检与后续修正。
    </p>
    <div v-if="overlayTestLayerDataUrl && overlayTestBaseDisplaySrc" class="overlay-test-stage" @mousedown.prevent="onOverlayTestMouseDown">
      <img
        ref="overlayQaBaseImg"
        class="overlay-test-base-img"
        :src="overlayTestBaseDisplaySrc"
        alt="卡片底图"
        draggable="false"
      />
      <img
        class="overlay-test-layer"
        :src="overlayTestLayerPreviewDataUrl || overlayTestLayerDataUrl"
        :style="overlayTestLayerImageStyle"
        alt="覆盖层预览"
        draggable="false"
      />
      <div class="overlay-test-box" :style="overlayTestBoxStyle">
        <span class="overlay-test-handle overlay-test-handle-left" data-handle="left"></span>
        <span class="overlay-test-handle overlay-test-handle-right" data-handle="right"></span>
        <span class="overlay-test-handle overlay-test-handle-top" data-handle="top"></span>
        <span class="overlay-test-handle overlay-test-handle-bottom" data-handle="bottom"></span>
      </div>
    </div>
    <template #footer>
      <el-button :disabled="overlayQaSubmitting" @click="skipOverlayQaComposite">取消</el-button>
      <el-button type="primary" :loading="overlayQaSubmitting" @click="submitOverlayQaComposite">确认并继续质检</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="overlayManualDialogVisible" title="手动修改覆盖层" width="980px" append-to-body @close="onOverlayManualDialogClose">
    <div class="overlay-manual-toolbar">
      <span class="overlay-test-label">编辑模式：</span>
      <el-radio-group v-model="overlayManualEditMode" size="small" style="margin-right: 16px;">
        <el-radio-button label="eraser">橡皮擦</el-radio-button>
        <el-radio-button label="select">选区编辑</el-radio-button>
        <el-radio-button label="line">直线</el-radio-button>
        <el-radio-button label="rect">方框</el-radio-button>
      </el-radio-group>
      <template v-if="overlayManualEditMode === 'eraser'">
        <span class="overlay-test-label">橡皮擦形状：</span>
        <el-radio-group v-model="overlayManualEraserShape" size="small" style="margin-right: 16px;">
          <el-radio-button label="circle">圆形</el-radio-button>
          <el-radio-button label="square">方形</el-radio-button>
        </el-radio-group>
        <span class="overlay-test-label">橡皮擦大小：</span>
        <el-slider v-model="overlayManualEraserSize" :min="6" :max="120" :step="1" style="width: 140px;" />
        <span class="overlay-manual-mini">{{ overlayManualEraserSize }}px</span>
      </template>
      <template v-if="overlayManualEditMode === 'select'">
        <span class="overlay-test-label">选区操作：</span>
        <el-radio-group v-model="overlayManualSelectMode" size="small" style="margin-right: 16px;" @change="onOverlayManualSelectModeChange">
          <el-radio-button label="move">平移</el-radio-button>
          <el-radio-button label="stretch">伸缩</el-radio-button>
          <el-radio-button label="copyplace">复制并放置</el-radio-button>
          <el-radio-button label="color">变色</el-radio-button>
          <el-radio-button label="thin">变细</el-radio-button>
        </el-radio-group>
        <template v-if="overlayManualSelectMode === 'copyplace' && overlayManualSelectedRegion && overlayManualSelectedRegion.w > 5 && overlayManualSelectedRegion.h > 5">
          <el-button
            v-if="!overlayManualCopyFloating"
            size="small"
            type="primary"
            plain
            style="margin-left: 8px;"
            @click="overlayManualCopySelectionToClipboard"
          >复制选区</el-button>
          <el-button
            v-if="overlayManualCopyFloating"
            size="small"
            plain
            style="margin-left: 8px;"
            @click="overlayManualCancelCopyFloating"
          >取消复制</el-button>
          <span v-if="overlayManualCopyFloating" class="overlay-manual-mini" style="margin-left: 8px;">拖动虚线框到目标位置后松开即可放置，可多次放置同一拷贝</span>
        </template>
        <el-button v-if="overlayManualSelectedRegion" size="small" type="danger" plain @click="clearManualSelection">清除选区</el-button>
        <el-button
          v-if="overlayManualSelectedRegion"
          size="small"
          type="primary"
          plain
          @click="addManualSelectionToOverlayKeepWhite"
        >选区加入白色保留区</el-button>
        <el-button
          size="small"
          plain
          :disabled="!overlayKeepWhiteRegions.length"
          @click="clearOverlayKeepWhiteRegions"
        >清空白色保留区</el-button>
        <span v-if="overlayKeepWhiteRegions.length" class="overlay-manual-mini" style="margin-left: 8px;">白色保留区：{{ overlayKeepWhiteRegions.length }} 个</span>
        <template v-if="overlayManualSelectMode === 'color'">
          <span class="overlay-test-label" style="margin-left: 12px;">颜色：</span>
          <span class="overlay-manual-color-presets">
            <button
              v-for="c in overlayManualSelectColorPresetColors"
              :key="c"
              type="button"
              class="overlay-manual-color-dot"
              :class="{ active: overlayManualSelectColor === c }"
              :style="{ background: c }"
              :title="c"
              @click="overlayManualSelectColor = c"
            />
          </span>
          <input v-model="overlayManualSelectColor" type="color" class="overlay-manual-color-input" title="取色器" />
          <span class="overlay-test-label" style="margin-left: 12px;">阈值：</span>
          <el-slider
            v-model="overlayManualSelectColorThreshold"
            :min="100"
            :max="245"
            :step="1"
            style="width: 140px;"
          />
          <span class="overlay-manual-mini">{{ overlayManualSelectColorThreshold }}</span>
          <el-button
            size="small"
            type="warning"
            plain
            :disabled="!overlayManualSelectedRegion || overlayManualSelectColorRunning"
            @click="applyOverlayManualSelectColor"
          >应用变色</el-button>
        </template>
        <template v-if="overlayManualSelectMode === 'thin'">
          <span class="overlay-test-label" style="margin-left: 12px;">阈值：</span>
          <el-slider
            v-model="overlayManualSelectThinThreshold"
            :min="100"
            :max="245"
            :step="1"
            style="width: 140px;"
          />
          <span class="overlay-manual-mini">{{ overlayManualSelectThinThreshold }}</span>
          <el-button
            size="small"
            type="warning"
            plain
            :disabled="!overlayManualSelectedRegion || overlayManualSelectThinRunning"
            @click="applyOverlayManualSelectThinLines"
          >选区变细</el-button>
        </template>
      </template>
      <template v-if="overlayManualEditMode === 'line'">
        <span class="overlay-test-label">线段粗细：</span>
        <el-slider v-model="overlayManualLineWidth" :min="1" :max="24" :step="1" style="width: 120px;" />
        <span class="overlay-manual-mini">{{ overlayManualLineWidth }}px</span>
        <span class="overlay-test-label">颜色：</span>
        <span class="overlay-manual-color-presets">
          <button
            v-for="c in overlayManualLinePresetColors"
            :key="c"
            type="button"
            class="overlay-manual-color-dot"
            :class="{ active: overlayManualLineColor === c }"
            :style="{ background: c }"
            :title="c"
            @click="overlayManualLineColor = c"
          />
        </span>
        <input v-model="overlayManualLineColor" type="color" class="overlay-manual-color-input" title="取色器" />
      </template>
      <template v-if="overlayManualEditMode === 'rect'">
        <el-checkbox v-model="overlayManualRectFilled" size="small" style="margin-right: 12px;">填充</el-checkbox>
        <template v-if="!overlayManualRectFilled">
          <span class="overlay-test-label">边框粗细：</span>
          <el-slider v-model="overlayManualRectStrokeWidth" :min="1" :max="24" :step="1" style="width: 120px;" />
          <span class="overlay-manual-mini">{{ overlayManualRectStrokeWidth }}px</span>
        </template>
        <span class="overlay-test-label">颜色：</span>
        <span class="overlay-manual-color-presets">
          <button
            v-for="c in overlayManualLinePresetColors"
            :key="'r-' + c"
            type="button"
            class="overlay-manual-color-dot"
            :class="{ active: overlayManualLineColor === c }"
            :style="{ background: c }"
            :title="c"
            @click="overlayManualLineColor = c"
          />
        </span>
        <input v-model="overlayManualLineColor" type="color" class="overlay-manual-color-input" title="取色器" />
      </template>
      <span class="overlay-test-label">放大倍数：</span>
      <el-slider v-model="overlayManualZoom" :min="1" :max="15" :step="0.1" style="width: 140px;" />
      <span class="overlay-manual-mini">{{ overlayManualZoom.toFixed(1) }}x</span>
      <el-button size="small" :disabled="overlayManualUndoStack.length === 0" @click="overlayManualUndo">撤销</el-button>
      <el-button
        size="small"
        type="warning"
        plain
        :loading="overlayManualBleachRunning"
        :disabled="overlayManualBleachRunning"
        @click="applyOverlayManualClearDarkToTransparent"
      >全图黑灰转透明</el-button>
      <!--
      旧功能：已由“识别红框并编号”替代，暂时保留代码但在界面注释隐藏
      <span class="overlay-test-label" style="margin-left: 12px;">红标修复起始号：</span>
      <el-input-number v-model="overlayManualDLabelStart" :min="1" :max="9999" :step="1" size="small" style="width: 110px;" />
      <el-button
        size="small"
        type="danger"
        plain
        :disabled="overlayManualDLabelRunning || overlayManualGeminiBoxesRunning"
        @click="applyOverlayManualNormalizeDLabels"
      >红标矩形顺序编号</el-button>
      -->
      <span class="overlay-manual-red-detect-inline" style="display: inline-flex; align-items: center; flex-wrap: wrap; gap: 8px;">
        <el-button
          size="small"
          type="primary"
          plain
          :loading="overlayManualGeminiBoxesRunning"
          :disabled="overlayManualDLabelRunning || overlayManualGeminiBoxesRunning"
          @click="applyOverlayManualGeminiDetectRedBoxes"
        >识别红框并编号</el-button>
        <el-checkbox v-model="overlayManualShowRedDetectParams" size="small">识别参数</el-checkbox>
      </span>
      <template v-if="overlayManualShowRedDetectParams">
        <span class="overlay-test-label" style="margin-left: 12px;">竖阈值：</span>
        <el-slider v-model="overlayManualDetectMinRunVert" :min="0" :max="24" :step="1" style="width: 96px;" />
        <span class="overlay-manual-mini">
          {{ overlayManualDetectMinRunVert === 0 ? (`自动(${overlayManualDetectAutoVert}px)`) : (overlayManualDetectMinRunVert + 'px') }}
        </span>
        <span class="overlay-test-label">横阈值：</span>
        <el-slider v-model="overlayManualDetectMinRunHoriz" :min="0" :max="24" :step="1" style="width: 96px;" />
        <span class="overlay-manual-mini">
          {{ overlayManualDetectMinRunHoriz === 0 ? (`自动(${overlayManualDetectAutoHoriz}px)`) : (overlayManualDetectMinRunHoriz + 'px') }}
        </span>
        <span class="overlay-test-label">斜阈值：</span>
        <el-slider v-model="overlayManualDetectMinRunDiag" :min="0" :max="24" :step="1" style="width: 96px;" />
        <span class="overlay-manual-mini">
          {{ overlayManualDetectMinRunDiag === 0 ? (`自动(${overlayManualDetectAutoDiag}px)`) : (overlayManualDetectMinRunDiag + 'px') }}
        </span>
        <span class="overlay-test-label">最小面积：</span>
        <el-slider v-model="overlayManualDetectMinAreaPx" :min="0" :max="220" :step="1" style="width: 100px;" />
        <span class="overlay-manual-mini">
          {{ overlayManualDetectMinAreaPx === 0 ? (`自动(${overlayManualDetectAutoArea}px²)`) : (overlayManualDetectMinAreaPx + 'px²') }}
        </span>
      </template>
      <span v-if="overlayTestHistory.length >= 2 && overlayTestHistoryIndex === 0" class="overlay-manual-save-hint">保存目标：上一版（overlay_prev）</span>
      <span v-else-if="overlayTestHistory.length" class="overlay-manual-save-hint">保存目标：当前（overlay_current）</span>
    </div>
    <div ref="overlayManualStageWrap" class="overlay-manual-stage-wrap">
      <div class="overlay-manual-stage">
        <canvas
          ref="overlayManualCanvas"
          class="overlay-manual-canvas"
          :style="{ width: (overlayManualDisplayBaseWidth * overlayManualZoom) + 'px', height: (overlayManualDisplayBaseHeight * overlayManualZoom) + 'px' }"
          @mousedown.prevent="onOverlayManualMouseDown"
          @mousemove.prevent="onOverlayManualMouseMove"
          @mouseup.prevent="onOverlayManualMouseUp"
          @mouseleave.prevent="onOverlayManualMouseUp"
        ></canvas>
        <!-- 选区框和控制点 -->
        <div v-if="overlayManualSelectedRegion && overlayManualEditMode === 'select'" 
             class="overlay-manual-selection-box"
             :style="getSelectionBoxStyle()">
          <!-- 拖拽整个选区进行平移 -->
          <div
            v-if="(overlayManualSelectMode === 'move' || (overlayManualSelectMode === 'copyplace' && overlayManualCopyFloating)) && !overlayManualIsDragging"
            class="selection-move-area"
            @mousedown.prevent.stop="onSelectionBoxMouseDown"
          ></div>
          <!-- 四条边的拖拽手柄用于伸缩 -->
          <template v-if="overlayManualSelectMode === 'stretch' && !overlayManualIsDragging">
            <div class="selection-edge selection-edge-top" @mousedown.prevent.stop="onEdgeDragStart('top', $event)"></div>
            <div class="selection-edge selection-edge-right" @mousedown.prevent.stop="onEdgeDragStart('right', $event)"></div>
            <div class="selection-edge selection-edge-bottom" @mousedown.prevent.stop="onEdgeDragStart('bottom', $event)"></div>
            <div class="selection-edge selection-edge-left" @mousedown.prevent.stop="onEdgeDragStart('left', $event)"></div>
          </template>
        </div>
        <!-- 拖动时显示选区内容 -->
        <canvas v-if="overlayManualIsDragging && overlayManualSelectionImageData"
                ref="overlayManualDragPreview"
                class="overlay-manual-drag-preview"
                :style="getDragPreviewStyle()">
        </canvas>
      </div>
    </div>
    <template #footer>
      <el-button @click="overlayManualDialogVisible = false">取消</el-button>
      <el-button type="primary" :loading="overlayManualConfirming" @click="confirmOverlayManualEdit">确认并保存到覆盖层文件</el-button>
    </template>
  </el-dialog>
</template>

<script>
import { API_BASE_URL } from '@/config/apiConfig'
import { get_card, set_card, card_generate_single_card_image, card_iterate_card_image, card_revert_iterate_card_image, card_generate_overlay_test_layer, card_get_overlay_test_layer_status, card_overlay_submit_qa_composite, card_overlay_skip_qa_composite, card_get_overlay_test_base_image, card_save_overlay_custom_base_image, card_save_overlay_custom_base_image_file, card_get_overlay_test_history, card_save_overlay_layer_file, card_overlay_detect_red_boxes_json, card_iterate_overlay_test_layer, card_apply_overlay_test_layer, card_list_ci_analyses_for_feedback, card_ci_feedback_iterate_content, card_html_exists, card_html_generate, card_html_iterate, card_html_revert, card_html_raw } from "@/api/card/get_card"

/** 与 backend views_card_image.DMT_OVERLAY_USER_PREFIX 第 99–106 行（至「……」段末空行）一致，【M级·蓝框】须紧随其后 */
const DMT_OVERLAY_STREAM_HEAD = `原图是一张手稿图，图中应该标注多个红、蓝、紫色框，具体如下：

【颜色规则】D=红框(#E53935,1.5px) M=蓝框(#1E88E5,1.5px) T=紫框(#8E24AA,1.5px)；红框/蓝框/紫框左上角分别加**红色底纯白字「D+序号」**标签、蓝色底白字「M+序号」标签、紫色底白字「T+序号」标签。嵌套关系：T⊃M⊃D。

【D级·红框】最小颗粒，每个独立格子各一框，每个词/短语/对象作为一个D框（宁可偏细勿粗）：
- D1：......
- D2：......
......

`

/** 与 backend 第 117–120 行一致：接在【T级·紫框】块末尾「......」换行之后，「---」之前 */
const DMT_OVERLAY_STREAM_SUFFIX_AFTER_T = `

我需要将上述所有的红蓝紫色框（含红/蓝/紫框左上角红底白字「D+序号」、蓝底白字「M+序号」、紫底白字「T+序号」标签，规格一致、用于定位）生成出来，底图内容（所有文字、线条、颜色等）全部清除不要，你生成出的图里应该只有红蓝紫框与标签上的白字序号，不要保留原图黑字正文或底色

风格严格按照参考图，红框+红底白字「D+序号」/蓝框+蓝色底白字「M+序号」/紫框+紫色底白字「T+序号」，仅参考样式风格
`
import { card_evalSFT } from "@/api/card/send_card"
import { ElButton, ElDialog, ElForm, ElFormItem, ElInput, ElMessageBox } from 'element-plus'
import { chageContent, deleteChoosedCard, changeText, backCardVersion, changeInterGrowth, changeInterGrowthForUser, getAIModification, getAIFeedback, generateComprehensiveAdvice, getCardHistory, getLastContent } from "@/api/card_zym/card_js";
import { getSceneByName } from "@/views/pages/mainHome/my_js";
import { getDateTime, modelHL } from "@/api/getData";
import AnswerParser from '@/components/chatWindow/AnswerParser.vue';
import { cross_reorganize_index, cross_reorganize_skill_get, cross_reorganize_skills_status, knowledge_conflict_get, knowledge_conflict_status, knowledge_conflict_feedback } from '@/api/chat/send_message';
import { marked } from 'marked';
// 🔥 使用npm安装的专业diff库
import { diffChars } from 'diff';

export default {
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElMessageBox,
    ElButton,
    ElDialog,
    AnswerParser
  },
  data() {
    return {
      crossReorgTab: 'suggest', // suggest | conflicts | skills
      crossReorgIndex: null,
      crossReorgLoading: false,
      crossReorgPollTimer: null,
      kcData: null,
      kcLoading: false,
      kcPollTimer: null,
      kcSaving: false,
      kcOpenIds: {},
      cardHtmlCacheBust: 0,
      crossSkillViewerVisible: false,
      crossSkillViewerTitle: '',
      crossSkillViewerName: '',
      crossSkillViewerRaw: '',
      crossSkillViewerFrontmatter: null,
      crossSkillViewMode: 'preview', // preview | source
      postIndexTitle: "",   // 后置索引title连结的字符串
      postIndices: [],  // 存储后置索引的cid

      // 每次CardGrid预加载content调整为前100字符后，点开卡片完整加载时，不可以让用户在加载完成前点击卡片编辑或确认，会造成不可逆的截断
      isContentLoading: true,

      isGeneratingAdvice: false,
      selectedAdviceUser: null,

      currentAIFeedback: null,
      isLoadingAI: false,
      isModifying: false,
      modifyingTimer: null,
      showingSuggestions: false,
      activeSuggestions: {
        score: 0,
        title: '',
        suggestion: ''
      },

      questionAreaMapping: {}, // 存储问题号与区域的映射
      // 共生区编辑状态标记
      isInterGrowthAreaNeed: false,
      isEditing: false,
      currentEditingIndex: -1,
      editContentInterGrowth: '',
      interGrowthSections: [],
      num: 0, // 需要num个用户回复才能变绿色
      isAuthor: false,
      isGroupCollaborator: false, // 是否为群组本子协作用户
      isGroupNotebook: false, // 是否为群组本子
      tempInterGrowthTA2GL: '',

      imgClicked: '',
      imgType: '',
      cardHtmlMenuVisible: false,
      cardHtmlMenuX: 0,
      cardHtmlMenuY: 0,
      cardHtmlBusy: false,
      cardHasHtmlFile: false,
      cardHasHtmlLastVersion: false,
      cardMediaViewMode: 'image',
      cardHtmlIframeKey: 0,
      cardHtmlSourceText: '',

      showLastContent: false,   // 卡片整理处
      showLastContentNormal: false,   // 一般的单卡迭代处

      _cardScrollTopBeforeEdit: undefined, // 进入编辑前卡片外层滚动位置
      _prevCardImageGeneratingCids: [], // 用于检测生图完成并刷新卡片图片

      // 添加三个编辑状态标记
      isEditingTitle: false,
      isEditingKeywords: false,
      isEditingContent: false,
      _keywordsPollTimer: null,
      _keywordsPollTries: 0,
      
      // 🔥 永久卡片：深评和浅评部分的展开/折叠状态
      isDeepReviewExpanded: false,
      isShallowReviewExpanded: false,
      
      // 🔥 卡片对话框的z-index（动态管理，后打开的在上层）
      cardDialogZIndex: 25,

      // 图无损理解反馈迭代：CI 分析列表与选择
      ciAnalysesList: [],
      ciFeedbackDialogVisible: false,
      selectedCiAnalysisId: '',
      isCiFeedbackLoading: false,
      ciFeedbackStatus: '',      // '' | 'loading' | 'success' | 'error'
      ciFeedbackStatusMsg: '',
      ciFeedbackStatusClearTimer: null,

      // 迭代图：弹窗与用户填写的具体修改要求、可选参考图
      iterateImageDialogVisible: false,
      iterateImageRevisionInstruction: '',
      iterateImageReferenceFile: null,
      iterateImageReferenceDataUrl: '',
      iterateImageQuality: 'normal',
      iterateImageProvider: 'gpt',
      iterateImageSubmitting: false,
      iterateOverlayTestMode: false,
      dmtOverlayPromptStreaming: false,
      /** 当前流式是否为「检验优化」Pass（用于两个按钮分别显示 loading） */
      dmtOverlayRefinePassActive: false,
      overlayDmtPromptReady: false,
      dmtOverlayDraftText: '',
      dmtOverlayRefinedText: '',
      dmtOverlayActiveVersion: 'draft',
      overlayTestGenerating: false,
      overlayTestApplying: false,
      overlayTestJobRunning: false,
      overlayTopBusy: false,
      overlayBusyProgressStep: 0,
      overlayBusyProgressTotal: 0,
      overlayBusyProgressMsg: '',
      overlayQaDialogVisible: false,
      overlayQaSubmitting: false,
      overlayQaAwaitingSince: 0,
      overlayQaSkipRequested: false,
      overlayTestPollTimer: null,
      overlayTestLayerDataUrl: '',
      overlayTestLayerPreviewDataUrl: '',
      overlayTestHistory: [],
      overlayTestHistoryIndex: -1,
      overlayCurrentOp: '', // '' | 'generate' | 'iterate'
      overlayPendingSnapshot: null,
      overlayTestSourceBoxNorm: null,
      overlayTestTargetBoxNorm: null,
      overlayTestContentOpacity: 100,
      overlayTestBaseSource: 'current', // current | backup | custom
      overlayTestBaseImageDataUrl: '',
      overlayTestCustomBaseDataUrl: '',
      overlayTestCustomBaseSaved: false,
      overlayTestPasteTarget: 'reference', // reference | base
      overlayTestDrag: {
        active: false,
        handle: 'move',
        start: null,
        startBox: null,
        baseImgEl: null,
      },
      overlayManualDialogVisible: false,
      overlayManualZoom: 1.8,
      overlayManualEraserSize: 24,
      overlayManualEraserShape: 'circle', // circle | square
      overlayManualEditMode: 'eraser', // eraser | select | line | rect
      overlayManualSelectMode: 'move', // move | stretch | copyplace | color | thin
      overlayManualCopyClipboard: null,
      overlayManualCopyFloating: false,
      overlayManualCanvasWidth: 0,
      overlayManualCanvasHeight: 0,
      overlayManualDisplayBaseWidth: 0,
      overlayManualDisplayBaseHeight: 0,
      overlayManualIsErasing: false,
      overlayManualLastPoint: null,
      overlayManualUndoStack: [],
      overlayManualThinThreshold: 220,
      overlayManualThinRunning: false,
      overlayManualBleachRunning: false,
      overlayManualSelectColorPresetColors: ['#D33431', '#1C7DD3', '#8E24AA'],
      overlayManualSelectColor: '#D33431',
      overlayManualSelectColorRunning: false,
      overlayManualSelectColorThreshold: 240,
      overlayManualSelectThinThreshold: 220,
      overlayManualSelectThinRunning: false,
      overlayManualDLabelStart: 1,
      overlayManualDLabelRunning: false,
      overlayManualGeminiBoxesRunning: false,
      overlayManualDetectMinRunVert: 0,
      overlayManualDetectMinRunHoriz: 0,
      overlayManualDetectMinRunDiag: 0,
      overlayManualDetectMinAreaPx: 0,
      overlayManualShowRedDetectParams: false,
      overlayManualSelectedRegion: null, // { x, y, w, h } 画布坐标
      overlayManualSelectionImageData: null, // 选中区域的像素数据
      overlayManualIsDragging: false,
      overlayManualDragStart: null,
      overlayManualDragEdge: null, // top | right | bottom | left
      overlayManualDragStartRegion: null,
      overlayManualDragSourceImageData: null,
      overlayManualTransforming: false,
      overlayManualLineColor: '#d33431',
      overlayManualLineWidth: 4,
      overlayManualLineDrawing: false,
      overlayManualLineStart: null,
      overlayManualLineBackup: null,
      overlayManualLinePresetColors: ['#d33431', '#1c7dd3', '#43a047', '#000000', '#fb8c00', '#8e24aa'],
      overlayManualRectFilled: false,
      overlayManualRectStrokeWidth: 4,
      overlayManualRectDrawing: false,
      overlayManualRectStart: null,
      overlayManualRectBackup: null,
      overlayManualConfirming: false,
      overlayIterateInstruction: '',
      overlayIterateReferenceDataUrl: '',
      overlayIterateSubmitting: false,
      overlayIterateEditRegionNorm: null,
      overlayKeepWhiteRegions: [],
      overlayIterateRegionDragging: false,
      overlayIterateRegionStart: null,
      overlayIterateRegionCurrent: null,
      // 迭代图：在原图上框选可编辑区域（归一化 0~1，相对整图宽高）
      iterateEditRegionNorm: null,
      iterateCropIncludeFullImage: true,
      iterateRegionDragging: false,
      iterateRegionDragStart: null,
      iterateRegionDragCurrent: null,
      
      // 图生成清晰度（普通/高清），用于「卡片生图/新生图」默认选择
      cardImageQuality: 'normal',
      cardImageProvider: 'gpt',
      cardImageAspectRatio: '1:1',
      cardImageGenDialogVisible: false,
      
      // 临时保存编辑内容
      tempTitle: '',
      tempKeywords: '',
      tempContent: '',
      // 🔥 保存编辑前的原始内容（用于diff对比）
      _originalContentBeforeEdit: null,
      // 单击双击区分
      clickTimer: null,
      // 鼠标位置跟踪（用于区分单击和拖拽<可能为局部文本复制>）
      mouseDownPos: null,
      mouseUpPos: null,
      // 跟踪是否刚刚进行了拖拽操作
      justDragged: false,
      // 是否拖拽后首次点击取消高亮
      firstClickAftDrag: false,

      chosenContent: '', // 用于存储选中的内容
      // 添加一个变量来标记是否注册了快捷键
      keydownHandlerRegistered: false,
      // 添加控制确认框显示的变量
      showConfirmBar: false,
      // 选中文本的位置信息
      selectionPosition: {
        left: 0,
        top: 0
      },
      // 当前选中的文本范围
      currentSelection: {
        start: 0,
        end: 0,
        text: ''
      },

      // 添加展开视图的状态
      expandedView: {
        visible: false,
        type: '', // 'main', 'sftReason', 'sftSuggestion', 'reason', 'suggestion'
        title: ''
      },

      shouldBeFront: false,   // 是否需要前置

      doubleClick: false,
      textStyle: { color: "black" }, // 默认颜色为黑色
      textStyleSFT: { color: "black" }, // 默认颜色为黑色
      needTurnToCardHL: false,
      needTurnToCardHLSFT: false,
      selectedIndex: 0, // 存储双击的开始位置
      speech: null, // 用于存储语音合成实例
      isSpeaking: false,
      clickedCharPosition: 0, // 🔥 记录单击时的字符位置

      checked: false,
      isContentExpanded: false,
      isContentTruncated: false,
      contentPageIndex: 0,
      isCardDialogVisible: false,
      showTooltip: false,
      showEditDialog: false,
      showHistoryDialog: false,
      showHistoryTip: false,
      showQualityTooltip: false,  // 质量评估悬浮框
      editForm: {
        contentTitle: '',
        content: '',
        keyWords: '',
      },
      splitReasonContent: [],
      // 🔥 类型编辑相关
      showTypeEditDialog: false,
      editingFourColorType: '',
      editingDmtLevel: '',
      savingType: false,
      // 卡片放大查看
      cardInfo: {
        title: "title",
        content: "content",
        username: "admin",
        datetime: "datetime",
        score: 1.0,
        color: "紫",
        reason: "",
        scoreSFT: 1.0,
        colorSFT: "紫",
        reasonSFT: "",
        keyWords: "",
        contentTitle: "",
        type: "",
        preIndex: "",
        postIndex: "",
        lastContent: "",
        writer: "",
        interGrowthT2TA: "",
        interGrowthTA2GL: "",
        interGrowthGL2GM: "",
        subareaAndHLAndSugTA2GL: "",
        timeParams: {
          "value1": 0.7,
          "value2": 0.95,
          "value3": 25,
          "value4": 512,
          "value5": 1,
          "value6": 1,
          "value7": 1,
          "value8": 1,
          "value9": 1,
          "value10": 512,
          "value11": 1.1,
          "value12": 1
        },
      }
    };
  },
  created() {
    // 🔥 初始化编辑变量
    this.editingFourColorType = this.fourColorType || '';
    this.editingDmtLevel = this.dmtLevel || '';
    // 创建一个绑定到当前组件实例的处理函数
    this.boundKeyHandler = this.handleGlobalKeyDown.bind(this);
    this._iterateDialogPasteHandler = this.onIterateDialogPaste.bind(this);
    this._boundIterateRegionMove = this.onIterateRegionMouseMove.bind(this);
    this._boundIterateRegionUp = this.onIterateRegionMouseUp.bind(this);
    this._boundOverlayTestMove = this.onOverlayTestMouseMove.bind(this);
    this._boundOverlayTestUp = this.onOverlayTestMouseUp.bind(this);
    this._boundOverlayIterateMove = this.onOverlayIterateRegionMouseMove.bind(this);
    this._boundOverlayIterateUp = this.onOverlayIterateRegionMouseUp.bind(this);
    // 检查当前用户是否为作者
    // 判断是否为作者或群组本子协作用户
    this.isAuthor = localStorage.getItem('originRealName') === localStorage.getItem('realName');

    // 检查是否为群组本子协作用户
    this.isGroupCollaborator = this.checkGroupCollaboratorPermission();

    // 检查是否为群组本子
    this.isGroupNotebook = this.checkGroupNotebook();

    this.num = localStorage.getItem('downLevelNum')
    console.log("[Card.vue]组本协作者中比作者低一级的人数：", this.num)
  },
  mounted() {
    // 添加一个监听器，当语音状态改变时更新 isSpeaking
    window.speechSynthesis.addEventListener('voiceschanged', () => {
      this.isSpeaking = window.speechSynthesis.speaking;
    });

    this.$nextTick(() => {
      // 全局注册键盘事件 - 这是最早的事件捕获
      if (!this.keydownHandlerRegistered) {
        window.addEventListener('keydown', this.boundKeyHandler, {
          capture: true,  // 使用捕获模式
          passive: false  // 明确表示处理函数可能会调用preventDefault()
        });
        
        this.keydownHandlerRegistered = true;
      }
      
      // 添加点击事件监听，用于处理点击外部保存编辑
      document.addEventListener('click', this.handleClickOutside);
      
      // 添加鼠标位置跟踪
      window.addEventListener('mousemove', this.trackMousePosition);

      // 解释精要 HTML iframe：题号跳转 / 核验迭代
      this._onCardHtmlMessage = (event) => {
        const data = event && event.data
        if (!data || !data.type) return
        if (!this._isMessageFromOwnCardHtml(event)) return
        const meta = this.parseGradingCardMarker()
        if (data.type === 'nkcn-homework-jump') {
          const evidence = String(data.evidence || '').trim()
          if (!evidence) return
          window.dispatchEvent(new CustomEvent('nkcn-homework-jump', {
            detail: {
              evidence,
              analysisId: meta.analysisId || data.analysisId || '',
              runId: meta.runId || data.runId || '',
              cid: this.cid,
            },
          }))
          return
        }
        if (data.type === 'nkcn-homework-verify-assist') {
          const evidence = String(data.evidence || '').trim()
          if (!evidence) return
          window.dispatchEvent(new CustomEvent('nkcn-homework-verify-assist', {
            detail: {
              evidence,
              analysisId: meta.analysisId || data.analysisId || data.analysis_id || '',
              runId: meta.runId || data.runId || data.run_id || 'current',
              cid: this.cid,
            },
          }))
          return
        }
        if (data.type === 'nkcn-homework-verify-assist-close') {
          window.dispatchEvent(new CustomEvent('nkcn-homework-verify-assist-close', {
            detail: { cid: this.cid },
          }))
          return
        }
        if (data.type === 'nkcn-homework-verify-iterate') {
          window.dispatchEvent(new CustomEvent('nkcn-homework-verify-iterate', {
            detail: {
              username: data.username || localStorage.getItem('userId') || '',
              analysisId: meta.analysisId || data.analysisId || data.analysis_id || '',
              runId: meta.runId || data.runId || data.run_id || 'current',
              cid: this.cid,
            },
          }))
        }
      }
      window.addEventListener('message', this._onCardHtmlMessage)
      this._onVerifyIterateDone = (event) => {
        const d = (event && event.detail) || {}
        const cid = d.cid
        if (cid != null && String(cid) !== String(this.cid)) return
        this.cardHtmlCacheBust = Date.now()
        // 触发卡片内容刷新（若有）
        try {
          if (typeof this.refreshCardInfo === 'function') this.refreshCardInfo()
          else if (typeof this.loadCardInfo === 'function') this.loadCardInfo()
        } catch (e) { /* ignore */ }
      }
      window.addEventListener('nkcn-homework-verify-iterate-done', this._onVerifyIterateDone)
    });

    // 保证加载页面时就更新卡片内容、打分、颜色，否则不放大卡片颜色不正确显示
    // let formData = new FormData();
    // formData.append('username', localStorage.getItem('userId'));
    // formData.append('cid', this.cid);
    // console.log("卡片id: ", this.cid);
    // get_card(formData).then(data => {
    //   console.log(data.content);
    //   this.cardInfo = data.content;
    //   this.cardInfo.username = localStorage.getItem('realName');
    //   console.log("卡片内容：", this.cardInfo)
    // }).catch(error => {
    //   console.error("An error occurred:", error);
    // });

    setTimeout(() => {
      this.cardFromCardListToCardInfo()
      this.showInterGrowthArea()

      // 初始化的时候要这两行加载一下后置索引（卡片内显示的后置title拼接字符串）
      this.postIndices = this.parsePostIndex(this.cardInfo.postIndex)
      this.postIndexTitle = this.getPostTitles().join(', ')
      this.refreshCardHtmlFlag()
    }, 1000); // 延迟0.1秒执行

    // 显示卡片模型、参数配置
    this.$refs.tooltipTarget.addEventListener('mouseenter', this.show);
    this.$refs.tooltipTarget.addEventListener('mouseleave', this.hide);
    this.$refs.historyTipTarget.addEventListener('mouseenter', this.showHisTip);
    this.$refs.historyTipTarget.addEventListener('mouseleave', this.hideHisTip);
  },
  beforeDestroy() {
    this.$refs.tooltipTarget.removeEventListener('mouseenter', this.show);
    this.$refs.tooltipTarget.removeEventListener('mouseleave', this.hide);
    this.$refs.historyTipTarget.removeEventListener('mouseenter', this.showHisTip);
    this.$refs.historyTipTarget.removeEventListener('mouseleave', this.hideHisTip);

    // 移除鼠标位置跟踪
    window.removeEventListener('mousemove', this.trackMousePosition);

    // 移除全局事件监听器
    if (this.keydownHandlerRegistered) {
      window.removeEventListener('keydown', this.boundKeyHandler, {
        capture: true
      });
      this.keydownHandlerRegistered = false;
    }
    // 移除点击事件监听
    document.removeEventListener('click', this.handleClickOutside);
    if (this._onCardHtmlMessage) {
      window.removeEventListener('message', this._onCardHtmlMessage)
      if (this._onVerifyIterateDone) {
        window.removeEventListener('nkcn-homework-verify-iterate-done', this._onVerifyIterateDone)
        this._onVerifyIterateDone = null
      }
      this._onCardHtmlMessage = null
    }
    // 移除确认框
    this.removeConfirmBar();
    // 清除可能存在的点击计时器
    if (this.clickTimer) {
      clearTimeout(this.clickTimer);
      this.clickTimer = null;
    }
    this._teardownIterateRegionDrag();
    this._teardownOverlayTestDrag();
    this._teardownOverlayIterateRegionDrag();
    this.stopOverlayTestPolling();
    this.stopKeywordsGeneratingPoll();
  },
  computed: {
    isCrossDocumentSuggestionCard() {
      const c = (this.cardInfo && this.cardInfo.content) || '';
      return c.includes('【文档全面交叉梳理建议卡片】');
    },
    crossSkillLineCount() {
      const raw = this.crossSkillViewerRaw || '';
      if (!raw) return 0;
      return raw.split('\n').length;
    },
    crossSkillParsed() {
      const raw = this.crossSkillViewerRaw || '';
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
    crossSkillFrontmatterRows() {
      const apiFm = this.crossSkillViewerFrontmatter;
      if (apiFm && typeof apiFm === 'object') {
        return this.formatFrontmatterRows(apiFm);
      }
      return this.parseFrontmatterRowsFromText(this.crossSkillParsed.frontmatterText || '');
    },
    crossSkillPreviewHtml() {
      return this.renderSkillMarkdown(this.crossSkillParsed.body || '（正文为空）');
    },
    overlayManualDetectAutoVert() {
      const h = Math.max(1, Number(this.overlayManualCanvasHeight) || 1);
      return Math.max(4, Math.min(18, Math.max(1, Math.floor(h / 120))));
    },
    overlayManualDetectAutoHoriz() {
      const w = Math.max(1, Number(this.overlayManualCanvasWidth) || 1);
      return Math.max(4, Math.min(18, Math.max(1, Math.floor(w / 120))));
    },
    overlayManualDetectAutoDiag() {
      return Math.max(this.overlayManualDetectAutoVert, this.overlayManualDetectAutoHoriz);
    },
    overlayManualDetectAutoArea() {
      const h = Math.max(1, Number(this.overlayManualCanvasHeight) || 1);
      const w = Math.max(1, Number(this.overlayManualCanvasWidth) || 1);
      return Math.max(12, Math.floor(h * w * 0.000015));
    },
    overlayBusyProgressRatio() {
      const t = Math.max(0, Number(this.overlayBusyProgressTotal) || 0);
      const s = Math.max(0, Number(this.overlayBusyProgressStep) || 0);
      if (t <= 0) return 0;
      return Math.max(0, Math.min(1, s / t));
    },
    overlayBusySectorPath() {
      const r = 9;
      const cx = 12;
      const cy = 12;
      const ratio = this.overlayBusyProgressRatio;
      if (ratio <= 0) return '';
      if (ratio >= 0.9999) return `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r} Z`;
      const a = -Math.PI / 2 + ratio * Math.PI * 2;
      const x = cx + r * Math.cos(a);
      const y = cy + r * Math.sin(a);
      const largeArc = ratio > 0.5 ? 1 : 0;
      return `M ${cx} ${cy} L ${cx} ${cy - r} A ${r} ${r} 0 ${largeArc} 1 ${x} ${y} Z`;
    },
    overlayBusyHoverTitle() {
      const step = Math.max(0, Number(this.overlayBusyProgressStep) || 0);
      const total = Math.max(0, Number(this.overlayBusyProgressTotal) || 0);
      const msg = (this.overlayBusyProgressMsg || '').trim();
      if (total > 0) {
        return msg ? `正在处理图片：${msg}（${step}/${total}）` : `正在处理图片（${step}/${total}）`;
      }
      return '正在处理图片，请稍等';
    },
    /** 左上角图标 hover：生图优先，其次 HTML 生成 */
    cardTopLeftBusyTitle() {
      if (this.isAnyImageBusy) return this.overlayBusyHoverTitle || '';
      if (this.isCardHtmlBusy) return '正在生成 HTML 版，请稍候';
      return '';
    },
    cardHtmlViewUrl() {
      const u = encodeURIComponent(localStorage.getItem('userId') || '');
      const bust = this.cardHtmlCacheBust ? `&_=${this.cardHtmlCacheBust}` : '';
      return `${API_BASE_URL}/api/card_html_view?username=${u}&cid=${this.cid}${bust}`;
    },
    cardHtmlChromeTitle() {
      const t = (this.cardInfo && this.cardInfo.contentTitle) ? String(this.cardInfo.contentTitle) : (this.contentTitle || '');
      const s = (t || '').trim();
      const x = s ? (s.length > 26 ? s.slice(0, 24) + '…' : s) : `卡片${this.cid}`;
      return x + ' · HTML';
    },
    /** 批改·解释精要卡（标题/正文标记） */
    isGradingExcerptCard() {
      const title = String(
        (this.cardInfo && this.cardInfo.contentTitle) || this.contentTitle || (this.cardInfo && this.cardInfo.title) || ''
      );
      if (title.includes('解释精要')) return true;
      const content = String((this.cardInfo && this.cardInfo.content) || this.content || '');
      return content.includes('nkcn_grading_card:批改·解释精要') || content.includes('批改·解释精要|');
    },
    /** 仅解释精要 + HTML 预览时加宽；切回图片/源码等仍用常规尺寸 */
    isGradingExcerptHtmlPreview() {
      return this.isGradingExcerptCard && this.cardMediaViewMode === 'html';
    },
    // 检查用户是否有权限查看质量评估
    canViewQualityAssessment() {
      const realName = localStorage.getItem('realName');
      return realName === 'testlyf' || realName === 'uzi';
    },
    // 有效的置信度评分（仅当不为null时）
    validConfidenceScore() {
      const score = this.confidenceScore !== null && this.confidenceScore !== undefined 
        ? this.confidenceScore 
        : this.cardInfo?.confidence_score;
      return (score !== null && score !== undefined) ? score : null;
    },
    // 有效的腐烂度评分（仅当不为null时）
    validRotScore() {
      const score = this.rotScore !== null && this.rotScore !== undefined 
        ? this.rotScore 
        : this.cardInfo?.rot_score;
      return (score !== null && score !== undefined) ? score : null;
    },
    // 是否有质量评分（至少有一个不为null）
    hasQualityScores() {
      return this.validConfidenceScore !== null || this.validRotScore !== null;
    },
    // 置信度等级
    confidenceLevel() {
      const score = this.validConfidenceScore;
      if (score === null) return '';
      if (score >= 4.0) return '(高)';
      if (score >= 2.5) return '(中)';
      return '(低)';
    },
    // 腐烂度等级（注意：腐烂度评分越低越好！）
    rotLevel() {
      const score = this.validRotScore;
      if (score === null) return '';
      if (score <= 1.5) return '(低)';  // 0-1.5分：腐烂度低（好）
      if (score <= 2.5) return '(中)';  // 1.5-2.5分：腐烂度中
      return '(高)';  // >2.5分：腐烂度高（不好）
    },
    isCardImageGenerating() {
      const list = this.cardImageGeneratingCids || [];
      const me = Number(this.cid);
      return list.some((c) => Number(c) === me);
    },
    isCardHtmlBusy() {
      const me = Number(this.cid);
      const inQueue = (this.cardHtmlGeneratingCids || []).some((c) => Number(c) === me);
      return this.cardHtmlBusy || inQueue;
    },
    cardImageGenDialogTitle() {
      return (this.imgClicked && this.imgClicked !== '') ? '新生图' : '卡片生图';
    },
    isAnyImageBusy() {
      return this.isCardImageGenerating || !!this.overlayTopBusy;
    },
    isOverlayImageGenerating() {
      return !!this.overlayTopBusy;
    },
    iterateRegionSummary() {
      const r = this.iterateEditRegionNorm;
      if (!r) return '';
      const x = Number(r.x);
      const y = Number(r.y);
      const w = Number(r.w);
      const h = Number(r.h);
      if ([x, y, w, h].some((n) => Number.isNaN(n))) return '';
      return `(${x.toFixed(3)}, ${y.toFixed(3)}) 宽 ${w.toFixed(3)} × 高 ${h.toFixed(3)}`;
    },
    /** 须先完成一次「DMT微版面化」（本地存了初稿），且当前用于检验的文本足够长 */
    canRunDmtOverlayRefine() {
      if (!this.iterateOverlayTestMode) return false;
      const d0 = (this.dmtOverlayDraftText || '').trim();
      if (d0.length < 40) return false;
      const t = ((this.iterateImageRevisionInstruction || '').trim() || d0);
      return t.length >= 40;
    },
    iterateRegionCommittedStyle() {
      const r = this.iterateEditRegionNorm;
      if (!r || r.w < 0.005 || r.h < 0.005) return null;
      return {
        left: `${r.x * 100}%`,
        top: `${r.y * 100}%`,
        width: `${r.w * 100}%`,
        height: `${r.h * 100}%`,
      };
    },
    iterateRegionDrawingStyle() {
      if (!this.iterateRegionDragging || !this.iterateRegionDragStart || !this.iterateRegionDragCurrent) return null;
      const x0 = this.iterateRegionDragStart.x;
      const y0 = this.iterateRegionDragStart.y;
      const x1 = this.iterateRegionDragCurrent.x;
      const y1 = this.iterateRegionDragCurrent.y;
      const x = Math.min(x0, x1);
      const y = Math.min(y0, y1);
      const w = Math.abs(x1 - x0);
      const h = Math.abs(y1 - y0);
      if (w < 0.001 || h < 0.001) return null;
      return {
        left: `${x * 100}%`,
        top: `${y * 100}%`,
        width: `${w * 100}%`,
        height: `${h * 100}%`,
      };
    },
    overlayTestBoxStyle() {
      const b = this.overlayTestTargetBoxNorm;
      if (!b) return null;
      return {
        left: `${b.x * 100}%`,
        top: `${b.y * 100}%`,
        width: `${b.w * 100}%`,
        height: `${b.h * 100}%`,
      };
    },
    overlayTestLayerImageStyle() {
      const src = this.overlayTestSourceBoxNorm;
      const dst = this.overlayTestTargetBoxNorm;
      if (!src || !dst || src.w <= 0 || src.h <= 0) return null;
      const sx = dst.w / src.w;
      const sy = dst.h / src.h;
      return {
        left: `${(dst.x - src.x * sx) * 100}%`,
        top: `${(dst.y - src.y * sy) * 100}%`,
        width: `${sx * 100}%`,
        height: `${sy * 100}%`,
      };
    },
    overlayTestBaseDisplaySrc() {
      if (this.overlayTestBaseSource === 'custom' && this.overlayTestCustomBaseDataUrl) return this.overlayTestCustomBaseDataUrl;
      if (this.overlayTestBaseImageDataUrl) return this.overlayTestBaseImageDataUrl;
      if (this.imgClicked) return 'data:' + (this.imgType || 'image/png') + ';base64,' + this.imgClicked;
      return '';
    },
    overlayIterateRegionSummary() {
      const r = this.overlayIterateEditRegionNorm;
      if (!r) return '';
      return `(${Number(r.x).toFixed(3)}, ${Number(r.y).toFixed(3)}) 宽 ${Number(r.w).toFixed(3)} × 高 ${Number(r.h).toFixed(3)}`;
    },
    overlayIterateRegionCommittedStyle() {
      const r = this.overlayIterateEditRegionNorm;
      if (!r || r.w < 0.005 || r.h < 0.005) return null;
      return { left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%` };
    },
    overlayIterateRegionDrawingStyle() {
      if (!this.overlayIterateRegionDragging || !this.overlayIterateRegionStart || !this.overlayIterateRegionCurrent) return null;
      const x0 = this.overlayIterateRegionStart.x;
      const y0 = this.overlayIterateRegionStart.y;
      const x1 = this.overlayIterateRegionCurrent.x;
      const y1 = this.overlayIterateRegionCurrent.y;
      const x = Math.min(x0, x1);
      const y = Math.min(y0, y1);
      const w = Math.abs(x1 - x0);
      const h = Math.abs(y1 - y0);
      if (w < 0.001 || h < 0.001) return null;
      return { left: `${x * 100}%`, top: `${y * 100}%`, width: `${w * 100}%`, height: `${h * 100}%` };
    },
    canOverlayHistoryPrev() {
      return this.overlayTestHistoryIndex > 0;
    },
    canOverlayHistoryNext() {
      return this.overlayTestHistoryIndex >= 0 && this.overlayTestHistoryIndex < this.overlayTestHistory.length - 1;
    },

    // 获取所有有综合建议的用户列表（作者和上级可见）
    adviceUsersList() {
      if (!this.subareaDataParsed || !this.subareaDataParsed.comprehensive) return [];
      return Object.keys(this.subareaDataParsed.comprehensive);
    },
    // 获取当前选中用户，如果没有选中且为作者或上级，则默认第一个
    currentAdviceUser() {
      if (this.selectedAdviceUser) {
        return this.selectedAdviceUser;
      }
      
      if (this.isAuthor || this.isMarkLee) {
        if (this.adviceUsersList.length > 0) {
          // 注意：这里不会修改 selectedAdviceUser，只是返回一个默认值
          return this.adviceUsersList[0];
        }
      }
      return null;
    },

    // 格式化建议文本
    // 🔥 格式化预览内容，区分不同类型（关键词、标题、加粗、句子）
    formattedPreviewContent() {
      if (!this.content) return '';
      const cleaned = String(this.content)
        .replace(/<!--\s*nkcn_grading_card:[^>]*-->\s*/gi, '')
        .replace(/<!--[\s\S]*?-->/g, '')
        .split(/\n*---NKCN_CARD_PAGE---\n*/)[0] || '';
      
      const lines = cleaned.split('\n').filter(line => line.trim() && !line.includes('(加载中)'));
      const formattedLines = [];
      
      // 🔥 遍历所有行，检测标题后面是否紧跟加粗，以及多个连续的加粗
      for (let i = 0; i < lines.length; i++) {
        const trimmed = lines[i].trim();
        
        // 标题：📄 开头
        if (trimmed.startsWith('📄 ')) {
          const text = trimmed.substring(2);
          
          // 🔥 收集所有连续的加粗行（标题后面）
          const boldParts = [];
          let j = i + 1;
          while (j < lines.length && lines[j].trim().startsWith('▸ ')) {
            const boldText = lines[j].trim().substring(2);
            boldParts.push(boldText);
            j++;
          }
          
          if (boldParts.length > 0) {
            // 🔥 合并标题和所有加粗到同一行
            const headingPart = `<span class="preview-heading-part"><span class="preview-icon">📄</span><span class="preview-text">${text}</span></span>`;
            const boldPartsHtml = boldParts.map(boldText => 
              `<span class="preview-bold-part"><span class="preview-icon">▸</span><span class="preview-text">${boldText}</span></span>`
            ).join('');
            formattedLines.push(`<div class="preview-heading-bold-row">${headingPart}${boldPartsHtml}</div>`);
            i = j - 1; // 跳过所有加粗行
          } else {
            formattedLines.push(`<div class="preview-heading"><span class="preview-icon">📄</span><span class="preview-text">${text}</span></div>`);
          }
        }
        // 关键词：🔑 开头
        else if (trimmed.startsWith('🔑 ')) {
          const text = trimmed.substring(2);
          formattedLines.push(`<div class="preview-keyword"><span class="preview-icon">🔑</span><span class="preview-text">${text}</span></div>`);
        }
        // 加粗：▸ 开头（检查是否有连续的加粗）
        else if (trimmed.startsWith('▸ ')) {
          // 🔥 收集所有连续的加粗行
          const boldParts = [];
          let j = i;
          while (j < lines.length && lines[j].trim().startsWith('▸ ')) {
            const boldText = lines[j].trim().substring(2);
            boldParts.push(boldText);
            j++;
          }
          
          if (boldParts.length > 1) {
            // 多个连续的加粗，合并到同一行
            const boldPartsHtml = boldParts.map(boldText => 
              `<span class="preview-bold-part"><span class="preview-icon">▸</span><span class="preview-text">${boldText}</span></span>`
            ).join('');
            formattedLines.push(`<div class="preview-bold-row">${boldPartsHtml}</div>`);
            i = j - 1; // 跳过所有加粗行
          } else {
            // 单个加粗
            const text = boldParts[0];
            formattedLines.push(`<div class="preview-bold"><span class="preview-icon">▸</span><span class="preview-text">${text}</span></div>`);
          }
        }
        // 句子：• 开头
        else if (trimmed.startsWith('• ')) {
          const text = trimmed.substring(2);
          formattedLines.push(`<div class="preview-sentence"><span class="preview-icon">•</span><span class="preview-text">${text}</span></div>`);
        }
        // 其他格式兼容（旧格式）
        else {
          formattedLines.push(`<div class="preview-line">${trimmed}</div>`);
        }
      }
      
      return formattedLines.join('');
    },


    formattedSuggestion() {
      if (!this.activeSuggestions.suggestion) return '';
      
      // 将"改进点1："等转换为带样式的HTML
      return this.activeSuggestions.suggestion
        .replace(/改进点(\d+)：/g, '<strong class="improvement-point">改进点$1：</strong>')
        .replace(/\n/g, '<br>');
    },
    
    // 检查综合建议区是否有内容
    hasComprehensiveAdvice() {
      if (this.isMarkLee || localStorage.getItem('originRealName') === localStorage.getItem('realName')) {
        console.log("综合信息：", (this.subareaDataParsed && this.subareaDataParsed.comprehensive))
        return this.subareaDataParsed && 
            this.subareaDataParsed.comprehensive
      } else {
        const currentUser = localStorage.getItem('originRealName');
        return this.subareaDataParsed && 
              this.subareaDataParsed.comprehensive && 
              this.subareaDataParsed.comprehensive[currentUser];
      }
    },
    // 获取当前用户的综合建议
    formattedComprehensiveAdvice() {
      const currentUser = localStorage.getItem('originRealName');
      const selectedUser = this.currentAdviceUser || currentUser;
      // const selectedUser = this.selectedAdviceUser || currentUser;

      if (!this.subareaDataParsed?.comprehensive?.[selectedUser]) return '';
      
      // 将<理解提升>等标签转换为HTML格式
      return this.subareaDataParsed.comprehensive[selectedUser]
        .replace(/<([^>]+)>/g, '<h4>$1</h4>')
        .replace(/\n/g, '<br>');
    },
    // 解析subareaAndHLAndSugTA2GL数据
    subareaDataParsed() {
      try {
        if (!this.cardInfo.subareaAndHLAndSugTA2GL) return null;
        let parseSubareaData = JSON.parse(this.cardInfo.subareaAndHLAndSugTA2GL);
        return parseSubareaData;
      } catch (e) {
        console.error("解析共生区打分及综合建议失败", e);
        return null;
      }
    },

    // 分析共生区的完成情况（作者视角）
    sectionCompletionStats() {
      if (!this.cardInfo.interGrowthTA2GL) return { completed: 0, total: 0 };
      
      const content = this.cardInfo.interGrowthTA2GL;
      const sections = this.parseInterGrowthPureContent(content);
      
      // 跟踪每个用户回答了哪些题目
      const userAnswers = {};
      const totalQuestions = sections.length; // 总题目数
      
      // 遍历所有题目，记录每个用户回答了哪些题目
      for (const section of sections) {
        // 找出该区域内所有的用户回复
        const userPattern = /<([^>]+)>/g;
        const matches = [...section.content.matchAll(userPattern)];
        
        // 记录每个用户回答的题目
        matches.forEach(match => {
          const userName = match[1];

          // 如果是作者或上级/同级，跳过
          let isUpOrSameLevel = false;
          // 是作者的上级
          if (userName === localStorage.getItem('writerCoacher'))
            isUpOrSameLevel = true;
          // 是作者的同级
          const sameLevelUsers = JSON.parse(localStorage.getItem('sameLevelUsers') || '[]');
          for (let sameLevelUser of sameLevelUsers) {
            if (userName === sameLevelUser) {
              isUpOrSameLevel = true;
              break;
            }
          }

          if (userName === this.cardInfo.writer || isUpOrSameLevel) {
            return;
          }
          
          if (!userAnswers[userName]) {
            userAnswers[userName] = new Set();
          }
          
          userAnswers[userName].add(section.number);
        });
      }
      
      // 计算有多少用户完成了所有题目
      let completedCount = 0;
      for (const userName in userAnswers) {
        if (userAnswers[userName].size === totalQuestions) {
          completedCount++;
        }
      }
      
      // 如果没有下级用户或下级用户数为0，不显示进度
      const totalUsers = Object.keys(userAnswers).length;
      if (totalUsers === 0) {
        return { completed: 0, total: parseInt(this.num, 10) };
      }
      
      return {
        completed: completedCount,
        total: parseInt(this.num, 10) // 使用下级用户总数
      };
      // let completedCount = 0;
      // for (const section of sections) {
      //   // 找出该区域内所有的用户回复
      //   const userPattern = /<([^>]+)>/g;
      //   const matches = [...section.content.matchAll(userPattern)];
      //   const uniqueUsers = new Set(matches.map(match => match[1]));
        
      //   // 如果回复用户数达到下级用户总数，认为该区域已完成
      //   if (uniqueUsers.size >= this.num) {
      //     completedCount++;
      //   }
      // }
      
      // return {
      //   completed: completedCount,
      //   total: sections.length
      // };
    },
    // 完成的区域数
    completedSections() {
      return this.sectionCompletionStats.completed;
    },
    // 总区域数
    totalSections() {
      return this.sectionCompletionStats.total;
    },
    // 进度环的偏移量
    progressOffset() {
      if (this.totalSections === 0) return 94.2; // 圆周长
      
      const progress = this.completedSections / this.totalSections;
      // 圆周长 = 2πr = 2 * 3.14 * 15 ≈ 94.2
      return 94.2 * (1 - progress);
    },
    // 添加一个新的计算属性判断是否全部完成
    isFullyCompleted() {
      return this.completedSections > 0 && this.completedSections === this.totalSections;
    },
    // 计算扇形路径
    progressSectorPath() {
      if (this.totalSections === 0) return '';
      
      const progress = this.completedSections / this.totalSections;
      const centerX = 18;
      const centerY = 18;
      const radius = 13; // 稍小于圆环半径，避免边缘重叠问题
      
      // 计算扇形的结束角度（弧度）
      const endAngle = 2 * Math.PI * progress;
      
      // 计算结束点的坐标
      const endX = centerX + radius * Math.cos(endAngle - Math.PI/2);
      const endY = centerY + radius * Math.sin(endAngle - Math.PI/2);
      
      // 构建SVG路径
      // M:移动到中心点, L:画线到起始点, A:画弧到结束点, Z:闭合路径
      const largeArcFlag = endAngle > Math.PI ? 1 : 0;
      return `M ${centerX} ${centerY} 
              L ${centerX} ${centerY - radius} 
              A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY} 
              Z`;
    },

    hasIncompleteResponses() {
      // 如果卡片没有共生内容，不显示感叹号
      if (!this.cardInfo.interGrowthTA2GL) 
        return false;

      if (this.isMarkLee || localStorage.getItem('originRealName') === localStorage.getItem('realName')) 
        return false;
      
      const currentUser = localStorage.getItem('originRealName');
      
      // 解析区域 - 找出所有问题序号的位置
      const content = this.cardInfo.interGrowthTA2GL;
      const sections = this.parseInterGrowthPureContent(content);
      
      // 检查当前用户是否在每个区域都有回复
      for (const section of sections) {
        // 找出该区域内所有的用户回复
        const userPattern = /<([^>]+)>/g;
        const matches = [...section.content.matchAll(userPattern)];
        const repliedUsers = matches.map(match => match[1]);
        
        // 如果当前用户没有在此区域回复，返回true显示感叹号
        if (!repliedUsers.includes(currentUser)) {
          return true;
        }
      }
      
      // 所有区域都已回复，不显示感叹号
      return false;
    },
    isMarkLee() {
      try {
        let isUpOrSameLevel = false;

        // 是作者的上级
        if (localStorage.getItem('originRealName') === localStorage.getItem('writerCoacher'))
          isUpOrSameLevel = true;

        // 是作者的同级
        const sameLevelUsers = JSON.parse(localStorage.getItem('sameLevelUsers') || '[]');
        for (let sameLevelUser of sameLevelUsers) {
          if (localStorage.getItem('originRealName') === sameLevelUser) {
            isUpOrSameLevel = true;
            break;
          }
        }

        return isUpOrSameLevel;
      } catch (e) {
        return false;
      }
    },

    wordCount() {
      return this.cardInfo.word_count || 0;
    },
    rawDisplayContent() {
      const raw = this.showLastContent
        ? (this.cardInfo.lastContent || '')
        : (this.cardInfo.content || '');
      return String(raw)
        .replace(/<!--\s*nkcn_grading_card:[^>]*-->\s*/gi, '')
        .replace(/<!--[\s\S]*?-->/g, '');
    },
    contentPages() {
      const text = this.rawDisplayContent;
      if (!text) return [''];
      if (!text.includes('---NKCN_CARD_PAGE---')) return [text];
      return text.split(/\n*---NKCN_CARD_PAGE---\n*/).filter((p) => String(p || '').trim());
    },
    hasContentPages() {
      return this.contentPages.length > 1;
    },
    pagedDisplayContent() {
      const pages = this.contentPages;
      if (!pages.length) return '';
      const idx = Math.min(Math.max(0, this.contentPageIndex), pages.length - 1);
      return pages[idx] || '';
    },
    normalRawDisplayContent() {
      const raw = this.showLastContentNormal
        ? (this.cardInfo.lastContent || '')
        : (this.cardInfo.content || '');
      return String(raw)
        .replace(/<!--\s*nkcn_grading_card:[^>]*-->\s*/gi, '')
        .replace(/<!--[\s\S]*?-->/g, '');
    },
    normalContentPages() {
      const text = this.normalRawDisplayContent;
      if (!text) return [''];
      if (!text.includes('---NKCN_CARD_PAGE---')) return [text];
      return text.split(/\n*---NKCN_CARD_PAGE---\n*/).filter((p) => String(p || '').trim());
    },
    hasNormalContentPages() {
      return this.normalContentPages.length > 1;
    },
    normalPagedDisplayContent() {
      const pages = this.normalContentPages;
      if (!pages.length) return '';
      const idx = Math.min(Math.max(0, this.contentPageIndex), pages.length - 1);
      return pages[idx] || '';
    },
    isKeywordsGenerating() {
      const kw = (this.cardInfo && this.cardInfo.keyWords != null)
        ? String(this.cardInfo.keyWords).trim()
        : '';
      return kw === '（理解生成中）';
    },

    splitReasonSFT() {
      this.cardInfo.reasonSFT = this.cardInfo.reasonSFT.replace(/\\n/g, '\n') // 将文本中的"\n"转换为实际的换行符
      const [part1, part2] = this.splitTextAtFirstOccurrence(this.cardInfo.reasonSFT, "建议");
      return [part1, part2];
    },
    colorSFT() {
      // 假设饱和度为50%，亮度范围从90%到10%，根据score调整
      let baseHue = 270; // 紫色的基准色调
      const saturation = 50; // 饱和度固定为50%
      const minLightness = 50; // 最暗的亮度值
      const maxLightness = 90; // 最亮的亮度值
      const lightnessRange = maxLightness - minLightness;

      // 根据score计算亮度值，score越小亮度越高，颜色越浅
      let lightness;
      if (this.scoreSFT >= 1 && this.scoreSFT <= 5) {
        baseHue = 270; // 紫色的基准色调
        lightness = maxLightness - ((this.scoreSFT - 1) / 4) * lightnessRange;
      } else if (this.scoreSFT > 0 && this.scoreSFT < 1) {
        if (this.colorhlSFT === "红") {
          baseHue = 0; // 红色的基准色调
        } else if (this.colorhlSFT === "蓝") {
          baseHue = 240; // 蓝色的基准色调
        } else {
          // 当分数<1但颜色标识不是红蓝时，根据分数范围显示默认颜色，程序稳健性处理
          if (this.scoreSFT < 0.5) {
            baseHue = 0; // 红色 (0-0.5分)
          } else {
            baseHue = 240; // 蓝色 (0.5-1分)
          }
        }
        lightness = maxLightness - (this.scoreSFT / 1) * lightnessRange;
      } else {
        // 如果分数不在0-5之间，可以选择一个默认行为，比如返回透明
        lightness = 100; // 完全透明，相当于白色
      }

      // 返回HSL颜色字符串
      return `hsl(${baseHue}, ${saturation}%, ${lightness}%)`;
    },

    splitReason() {
      this.cardInfo.reason = this.cardInfo.reason.replace(/\\n/g, '\n') // 将文本中的"\n"转换为实际的换行符
      const [part1, part2] = this.splitTextAtFirstOccurrence(this.cardInfo.reason, "建议");
      return [part1, part2];
    },
    color() {
      // 假设饱和度为50%，亮度范围从90%到10%，根据score调整
      let baseHue = 270; // 紫色的基准色调
      const saturation = 50; // 饱和度固定为50%
      const minLightness = 50; // 最暗的亮度值
      const maxLightness = 90; // 最亮的亮度值
      const lightnessRange = maxLightness - minLightness;

      // 根据score计算亮度值，score越小亮度越高，颜色越浅
      // 根据分数计算亮度值，这里用this.score而不用cardInfo里的，应该是因为挂载时cardInfo要后端获取，而this.score是直接传过来的，无延迟
      let lightness;
      if (this.score >= 1 && this.score <= 5) {
        baseHue = 270; // 紫色的基准色调
        lightness = maxLightness - ((this.score - 1) / 4) * lightnessRange;
      } else if (this.score > 0 && this.score < 1) {
        if (this.cardcolor === "红") {
          baseHue = 0; // 红色的基准色调
        } else if (this.cardcolor === "蓝") {
          baseHue = 240; // 蓝色的基准色调
        } else {
          // 当分数<1但颜色标识不是红蓝时，根据分数范围显示默认颜色，程序稳健性处理
          if (this.score < 0.5) {
            baseHue = 0; // 红色 (0-0.5分)
          } else {
            baseHue = 240; // 蓝色 (0.5-1分)
          }
        }
        lightness = maxLightness - (this.score / 1) * lightnessRange;
      } else {
        // 如果分数不在0-5之间，可以选择一个默认行为，比如返回透明
        lightness = 100; // 完全透明，相当于白色
      }

      // 返回HSL颜色字符串
      return `hsl(${baseHue}, ${saturation}%, ${lightness}%)`;
    },
    getCustomTitle() {
      if (this.title.includes("1002")) {
        return "来自GPT-4o";
      } else if (this.title.includes("1003")) {
        return "来自Mixtral";
      } else if (this.title.includes("1004")) {
        return "来自Kimi";
      } else if (this.title.includes("1005")) {
        return "来自llama3.1";
      } else if (this.title.includes("1006")) {
        return "来自Claude3.5";
      } else if (this.title.includes("1007")) {
        return "来自Deepseek";
      } else if (this.title.includes("1008")) {
        return "来自Deepseek";
      } else if (this.title.includes("1009")) {
        return "来自Gemini";
      } else if (this.title.includes("1010")) {
        return "来自Qwq";
      } else if (this.title.includes("2000")) {
        return "来自2模融合";
      } else {
        return "卡片迭代结果";
      }
    },
  },
  props: {
    cid: Number,
    idx: Number,
    title: String,
    content: String,
    cardcolor: String,
    score: Number,
    reason: String,
    colorhlSFT: String,
    scoreSFT: Number,
    reasonSFT: String,
    model_id: Number,
    status: Number,
    contentTitle: String,
    needflashing: Boolean,
    needMultiFlashing: Boolean,
    reAcquire: Boolean,
    updateCheckbox: Boolean,
    choosedCardIdList: Array,
    activeModel: String,
    card: Object,
    keyTopics: Array,
    sceneName: String,
    subSceneName: String,
    cidToTitleMap: Object,
    postIndex: String,

    HLOpeContent: Map,
    HLContent: Map,
    groupIndex: {
      type: Number,
      default: -1 // 设置默认值
    },
    confidenceScore: {
      type: Number,
      default: null
    },
    rotScore: {
      type: Number,
      default: null
    },
    // 🔥 新增：四色类型、DMT层次、高价值标记、相关卡片标记、选中文档列表
    fourColorType: {
      type: String,
      default: ''
    },
    dmtLevel: {
      type: String,
      default: ''
    },
    isHighValue: {
      type: Boolean,
      default: false
    },
    isRelatedToSelected: {
      type: Boolean,
      default: false
    },
    selectedDocs: {
      type: String,
      default: ''
    },
    selectedCardId: {
      type: Number,
      default: null
    },
    // 🔥 卡片进化整理等待状态
    cardTidying: {
      type: Boolean,
      default: false
    },
    cardImageGeneratingCids: {
      type: Array,
      default: () => []
    },
    cardHtmlGeneratingCids: {
      type: Array,
      default: () => []
    },
    /** 当前卡片是否已有附图（用于左上角图标高亮） */
    hasCardImage: {
      type: Boolean,
      default: false
    },
    cardList: {
      type: Array,
      default: () => []
    },
    /** 与主界面勾选文档一致，供「生成html版」拉 PDF 文本 / 图片三层理解 */
    fileNameList: {
      type: Array,
      default: () => []
    },
    leftSelectList: {
      type: Array,
      default: () => []
    },
    rightSelectList: {
      type: Array,
      default: () => []
    }
  },
  watch: {
    isKeywordsGenerating(v) {
      if (v) this.ensureKeywordsGeneratingPoll();
      else this.stopKeywordsGeneratingPoll();
    },
    isCardDialogVisible(v) {
      if (v && this.isKeywordsGenerating) this.ensureKeywordsGeneratingPoll();
    },
    overlayManualEditMode() {
      // 切换编辑模式时清除选区
      this.clearManualSelection();
    },
    iterateOverlayTestMode(v) {
      if (v) {
        this.fetchOverlayBasePreset();
        this.syncOverlayHistoryFromServer();
        this.pollOverlayTestStatus(true);
      } else {
        this._teardownOverlayTestDrag();
        this._teardownOverlayIterateRegionDrag();
        this.stopOverlayTestPolling();
        this.overlayTestPasteTarget = 'reference';
      }
    },
    overlayTestBaseSource(v) {
      if (!this.iterateOverlayTestMode) return;
      if (v === 'custom') return;
      this.fetchOverlayBasePreset();
    },
    overlayTestContentOpacity() {
      this.rebuildOverlayPreviewAlpha();
    },
    iterateImageDialogVisible(visible) {
      if (visible) {
        document.addEventListener('paste', this._iterateDialogPasteHandler);
        if (this.iterateOverlayTestMode) {
          this.pollOverlayTestStatus(true);
        }
      } else {
        document.removeEventListener('paste', this._iterateDialogPasteHandler);
        this._teardownIterateRegionDrag();
        this._teardownOverlayTestDrag();
        this._teardownOverlayIterateRegionDrag();
      }
    },
    // 监听adviceUsersList变化，设置默认用户，但修改了this.selectedAdviceUser会导致下级用户也只看到第一个人的
    // adviceUsersList: {
    //   immediate: true, // 确保组件创建时就执行
    //   handler(newList) {
    //     if (newList && newList.length > 0 && !this.selectedAdviceUser) {
    //       this.selectedAdviceUser = newList[0];
    //     }
    //   }
    // },
    'cardInfo.interGrowthTA2GL': {
      handler(newVal) {
        // 这里非空也要检测，因为有可能卡片前移的时候改变了，从有到无，如果不检测刷新变量this.interGrowthSections，
        // 现在的卡片没有共生区也会显示之前卡片的共生内容
        // if (newVal)
          this.parseInterGrowthSections();
      },
      immediate: true
    },
    chosenContent(newVal){
      if(newVal !== "") {
        // this.cancelDialog()
        // this.hideCardDialog()
        // this.onCheckboxChange()
        console.log("卡片内选中内容变化！", newVal)
      }
    },
    card(newVal){
      this.contentPageIndex = 0
      this.cardFromCardListToCardInfo()
      this.showInterGrowthArea()
      // 这里没有deep检测，只能检测到结构变化，单单内容变化检测不到，例如更新了card.postIndex，所以要单独提出来检测 ↓
    },
    showLastContent() {
      this.contentPageIndex = 0
    },
    showLastContentNormal() {
      this.contentPageIndex = 0
    },
    contentPages(pages) {
      if (!pages || !pages.length) {
        this.contentPageIndex = 0
        return
      }
      if (this.contentPageIndex >= pages.length) {
        this.contentPageIndex = pages.length - 1
      }
    },
    reason(newVal) {
      // 只有在没有流式更新内容时才更新content，避免覆盖流式更新的内容
      if (!(this.HLOpeContent && this.HLOpeContent.has(this.cid))) {
        this.cardFromCardListToCardInfo()
      } else {
        // 有流式内容时，只更新reason相关字段，不更新content
        // 但最后流式结束会更新一次cardlist，card变，其字段变为预加载的空串（因为去除了大字段），使得这里会更新掉，需要避免更新空值
        if (this.card.reason !== "")
          this.cardInfo.reason = this.card.reason
      }
      this.showInterGrowthArea()
    },
    reasonSFT(newVal) {
      // 只有在没有流式更新内容时才更新content，避免覆盖流式更新的内容
      if (!(this.HLContent && this.HLContent.has(this.cid))) {
        this.cardFromCardListToCardInfo()
      } else {
        // 有流式内容时，只更新reasonSFT相关字段，不更新content
        // 但最后流式结束会更新一次cardlist，card变，其字段变为预加载的空串（因为去除了大字段），使得这里会更新掉，需要避免更新空值
        if (this.card.reasonSFT !== "")
          this.cardInfo.reasonSFT = this.card.reasonSFT
      }
      this.showInterGrowthArea()
    },
    postIndex(newVal) {
      this.postIndices = this.parsePostIndex(newVal)
      this.postIndexTitle = this.getPostTitles().join(', ')
    },
    cardImageGeneratingCids(newVal) {
      const list = newVal && newVal.slice ? newVal.slice() : [];
      const me = Number(this.cid);
      const wasGenerating = (this._prevCardImageGeneratingCids || []).some((c) => Number(c) === me);
      this._prevCardImageGeneratingCids = list;
      const nowGenerating = list.some((c) => Number(c) === me);
      if (wasGenerating && !nowGenerating && this.isCardDialogVisible) {
        this.refetchCardImage();
      }
    },
    cardHtmlGeneratingCids(newVal) {
      const list = newVal && newVal.slice ? newVal.slice() : [];
      const me = Number(this.cid);
      const wasGenerating = (this._prevCardHtmlGeneratingCids || []).some((c) => Number(c) === me);
      this._prevCardHtmlGeneratingCids = list;
      const nowGenerating = list.some((c) => Number(c) === me);
      if (wasGenerating && !nowGenerating) {
        this.cardHasHtmlFile = true;
        this.cardHtmlIframeKey += 1;
      }
    },
    content(newVal) {
      // 根据内容长度判断是否需要截断显示
      if (newVal.length > 100) {
        this.isContentTruncated = true;
      }
    },
    needflashing(newVal) {
      if(newVal === true){
        // let formData = new FormData();
        // formData.append('username', localStorage.getItem('userId'));
        // formData.append('cid', this.cid);
        // set_card(formData).then(data => {
        // }).catch(error => {
        //   console.error("An error occurred:", error); // 错误处理
        // });
      }
    },
    needMultiFlashing(newVal) {
      if(newVal === true){
        // let formData = new FormData();
        // formData.append('username', localStorage.getItem('userId'));
        // formData.append('cid', this.cid);
        // set_card(formData).then(data => {
        // }).catch(error => {
        //   console.error("An error occurred:", error); // 错误处理
        // });
      }
    },
    reAcquire(newVal) {
      if(newVal === true){
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', this.cid);
        console.log("卡片id: ", this.cid);
        this.isContentLoading = true;
        get_card(formData).then(data => {
          console.log(data.content);
          this.isContentLoading = false;
          this.cardInfo = data.content;
          this.imgClicked = data.img;
          this.imgType = data.img_type;
          if (data.img && data.img !== '') this.$emit('card-has-image', this.cid);
          this.cardInfo.username = localStorage.getItem('realName');
          this.$emit('reAcquireOver');
        }).catch(error => {
          console.error("An error occurred:", error);
        });

        // 显示卡片模型、参数配置
        this.$refs.tooltipTarget.addEventListener('mouseenter', this.show);
        this.$refs.tooltipTarget.addEventListener('mouseleave', this.hide);
        this.$refs.historyTipTarget.addEventListener('mouseenter', this.showHisTip);
        this.$refs.historyTipTarget.addEventListener('mouseleave', this.hideHisTip);
      }
    },
    updateCheckbox(newVal) {
      if(newVal === true){
        if(this.choosedCardIdList.includes(this.cid))
          this.checked = true
        else
          this.checked = false
      }
    },
    // 🔥 监听四色类型和DMT层次变化，同步到编辑变量
    fourColorType(newVal) {
      this.editingFourColorType = newVal || '';
    },
    dmtLevel(newVal) {
      this.editingDmtLevel = newVal || '';
    },
  },
  methods: {
    openPostIndexDialog() {
      this.$emit("openPostIndexDialog", this.card)
    },

    // 获取当前选中的后置索引对应的标题
    getPostTitles() {
      return this.postIndices.map(cid => 
        this.cidToTitleMap[cid] || `未知卡片(${cid})`
      );
    },
    // 解析后置索引字符串为数组
    parsePostIndex(postIndexStr) {
      if (!postIndexStr || typeof postIndexStr !== 'string') return [];
      
      // 尝试解析JSON
      try {
        const parsed = JSON.parse(postIndexStr);
        if (Array.isArray(parsed)) {
          return parsed.map(item => item.toString());
        }
      } catch (e) {
        // 不是JSON格式，继续按字符串处理
      }
      
      // 按逗号或空格分隔
      return postIndexStr.split(/[,，、\s]+/).filter(item => item.trim());
    },

    // 获取AI评分与建议
    getAIFeedback(index) {
      if (!this.editContentInterGrowth.trim()) {
        this.$message.warning('请先输入内容');
        return;
      }
      
      this.isLoadingAI = true;
      
      // 准备请求数据
      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('cardContent', this.cardInfo.content);
      formData.append('sectionNumber', this.interGrowthSections[index].number);
      formData.append('sectionQuestion', this.interGrowthSections[index].content); // 添加问题内容
      formData.append('content', this.editContentInterGrowth.trim());
      formData.append('userName', localStorage.getItem('originRealName'));
      
      // 调用API获取AI评分与建议
      getAIFeedback(formData).then(response => {
        if (response.error_num === 0) {
          // 解析AI反馈
          this.currentAIFeedback = {
            score: response.score,
            title: response.title || '回答需要改进',
            points: this.parseImprovement(response.suggestion)
          };

          // 更新卡片的subareaAndHLAndSugTA2GL数据
          if (response.updated_subareaData) {
            this.cardInfo.subareaAndHLAndSugTA2GL = response.updated_subareaData;
          }
        } else {
          this.$message.error('获取AI评分失败: ' + response.msg);
        }
      }).catch(error => {
        this.$message.error('获取AI评分出错');
        console.error(error);
      }).finally(() => {
        this.isLoadingAI = false;
      });
    },

    // AI辅助修改
    modifyWithAI() {
      if (!this.currentAIFeedback) return;
      
      this.isModifying = true;
      
      // 设置超时计时器
      this.modifyingTimer = setTimeout(() => {
        this.isModifying = false;
        this.$message.warning('AI修改超时，请稍后再试');
      }, 60000); // 1分钟超时
      
      // 准备请求数据
      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('cardContent', this.cardInfo.content);
      formData.append('sectionQuestion', this.interGrowthSections[this.currentEditingIndex].content); // 添加问题内容
      formData.append('sectionNumber', this.interGrowthSections[this.currentEditingIndex].number);
      formData.append('originalContent', this.editContentInterGrowth);
      formData.append('suggestion', this.currentAIFeedback.points.join('\n'));
      formData.append('userName', localStorage.getItem('originRealName'));
      
      // 调用API获取AI修改建议
      getAIModification(formData).then(response => {
        if (response.error_num === 0) {
          clearTimeout(this.modifyingTimer);
          // 更新编辑内容
          this.editContentInterGrowth = response.modified_content;
          this.$message.success('AI修改完成');
        } else {
          this.$message.error('AI修改失败: ' + response.msg);
        }
      }).catch(error => {
        this.$message.error('AI修改出错');
        console.error(error);
      }).finally(() => {
        this.isModifying = false;
        clearTimeout(this.modifyingTimer);
      });
    },
    
    // 解析改进点
    parseImprovement(suggestion) {
      if (!suggestion) return [];
      // 将"改进点1：xxx\n改进点2：xxx"格式拆分为数组
      const points = suggestion.split(/改进点\d+：/).filter(item => item.trim());
      return points.map(p => p.trim());
    },
    
    // 获取用户评分
    getUserRatings(sectionNumber) {
      if (!this.subareaDataParsed || !this.subareaDataParsed.ratings) return {};
      
      const ratings = {};
      
      // 遍历所有用户的评分
      Object.entries(this.subareaDataParsed.ratings).forEach(([user, userRatings]) => {
        if (userRatings[sectionNumber]) {
          ratings[user] = userRatings[sectionNumber];
        }
      });
      // console.log("[card.vue]所有用户回答评分：", ratings)
      
      return ratings;
    },
    
    // 获取评分样式
    getRatingStyle(score) {
      // 小于1分区间
      if (score < 0.5) {
        return { backgroundColor: '#FF4D4F' };  // 红色 (0-0.5分)
      } else if (score < 1) {
        return { backgroundColor: '#1890FF' };  // 蓝色 (0.5-1分)
      } 
      // 1-4分区间，紫色渐变
      else if (score < 1.5) {
        return { backgroundColor: '#F3E5F5' };  // 紫色1级 (1-1.5分)
      } else if (score < 2) {
        return { backgroundColor: '#E1BEE7' };  // 紫色2级 (1.5-2分)
      } else if (score < 2.5) {
        return { backgroundColor: '#CE93D8' };  // 紫色3级 (2-2.5分)
      } else if (score < 3) {
        return { backgroundColor: '#BA68C8' };  // 紫色4级 (2.5-3分)
      } else if (score < 3.5) {
        return { backgroundColor: '#AB47BC' };  // 紫色5级 (3-3.5分)
      } else if (score < 4) {
        return { backgroundColor: '#9C27B0' };  // 紫色6级 (3.5-4分)
      } 
      // 4分以上区间
      else if (score < 4.5) {
        return { backgroundColor: '#8E24AA' };  // 深紫色1级 (4-4.5分)
      } else if (score < 5) {
        return { backgroundColor: '#7B1FA2' };  // 深紫色2级 (4.5-5分)
      } else {
        return { backgroundColor: '#6A1B9A' };  // 最深紫色 (5分及以上)
      }
    },
    
    // 获取评分描述
    getRatingDescription(score) {
      if (score < 1) {
        return '回答内容需要大幅改进';
      } else if (score < 2) {
        return '回答基本清晰但缺乏深度';
      } else if (score < 3) {
        return '回答内容较好但有提升空间';
      } else if (score < 4) {
        return '回答质量良好';
      } else if (score < 4.5) {
        return '回答非常优秀';
      } else {
        return '回答卓越，极具深度';
      }
    },
    
    // 显示建议
    showSuggestions(user, sectionNumber) {
      if (!this.subareaDataParsed || 
          !this.subareaDataParsed.ratings || 
          !this.subareaDataParsed.ratings[user] || 
          !this.subareaDataParsed.ratings[user][sectionNumber]) {
        return;
      }
      
      const rating = this.subareaDataParsed.ratings[user][sectionNumber];
      
      this.activeSuggestions = {
        score: rating.score,
        title: this.getRatingDescription(rating.score),
        suggestion: rating.suggestion || ''
      };
      
      this.showingSuggestions = true;
    },

    // 获取特定区域的问题
    getAreaSections(areaName) {
      if (!this.subareaDataParsed || !this.subareaDataParsed.areas) {
        // 如果没有分区数据，临时根据问题序号进行分类
        // 这只是一个默认实现，实际应该根据subareaData来分类
        const defaultMapping = {
          '目标区': [1, 2],
          '任务区': [3, 4],
          '分工区': [5]
        };
        
        const sectionNumbers = defaultMapping[areaName] || [];
        return this.interGrowthSections.filter(section => 
          sectionNumbers.includes(parseInt(section.number))
        );
      }
      
      // 根据subareaData获取当前区域的问题序号
      const sectionNumbers = this.subareaDataParsed.areas[areaName] || [];
      
      // 过滤出属于当前区域的问题
      return this.interGrowthSections.filter(section => 
        sectionNumbers.includes(parseInt(section.number))
      );
    },
    
    // 获取问题在interGrowthSections中的索引
    getInterGrowthSectionIndex(section) {
      return this.interGrowthSections.findIndex(s => s.number === section.number);
    },

    // 检查是否为群组本子协作用户
    checkGroupCollaboratorPermission() {
      // 获取当前本子信息
      const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
      
      // 如果是群组本子且当前用户是协作用户
      if (currentNotebook.syncUsers && currentNotebook.syncUsers !== '') {
        const syncUsers = currentNotebook.syncUsers.split(',').map(user => user.trim()).filter(user => user);
        const currentUser = localStorage.getItem('originRealName');
        
        // 检查当前用户是否在协作用户列表中
        return syncUsers.includes(currentUser);
      }
      
      return false;
    },

    // 检查是否为群组本子
    checkGroupNotebook() {
      // 获取当前本子信息
      const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
      
      // 如果是群组本子（有协作用户）
      return currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
    },

    // 检查是否有卡片操作权限（作者或群组协作用户）
    hasCardOperationPermission() {
      return this.isAuthor || this.isGroupCollaborator;
    },

    // 检查是否有卡片编辑权限（作者或群组协作用户且是卡片创建者）
    hasCardEditPermission() {
      if (this.isAuthor) return true;
      if (localStorage.getItem('originRealName') === "marklee" || localStorage.getItem('originRealName') === "testlyf") return true;
      if (this.isGroupCollaborator) {
        // 群组协作用户只能编辑自己创建的卡片
        return this.cardInfo.writer === localStorage.getItem('originRealName');
      }
      return false;
    },

    // 共生部分的实现
    showInterGrowthArea() {
      // console.log("信息信息：", this.isAuthor, this.num, this.cardInfo.interGrowthTA2GL)
      console.log("信息信息：", this.isAuthor, this.num)
      if(this.isAuthor === false) {
        // 不是作者，说明一定是组本，那么卡片共生区有内容就显示，没有就不显示即可
        if(this.cardInfo.interGrowthTA2GL === "")
          this.isInterGrowthAreaNeed = false
        else
          this.isInterGrowthAreaNeed = true
      } else {
        // 是作者，可能是自己的普通个人本，也可能是自己为作者的组本，有num就显示，没有就没必要显示（没人来回答）
        if(this.num > 0)
          this.isInterGrowthAreaNeed = true
        else
          this.isInterGrowthAreaNeed = false
      }
    },

    // 仅解析共生区内容纯文本，用于判断当前用户（下级）是否完成了此卡片的全部问题（是否红色感叹号）/ 作者或上级用户显示进度环
    parseInterGrowthPureContent(content) {
      if (!content) return [];
      
      const sections = [];
      const sectionRegex = /(\d+\..*?)(?=\d+\.|$)/gs;
      let match;
      
      while ((match = sectionRegex.exec(content + "\n")) !== null) {
        const sectionContent = match[1].trim();
        const sectionNumber = sectionContent.split('.')[0];
        
        sections.push({
          number: sectionNumber,
          content: sectionContent
        });
      }
      
      return sections;
    },
    // 解析共生区内容为不同的区域
    parseInterGrowthSections() {
      const content = this.cardInfo.interGrowthTA2GL;
      if (!content) {
        this.interGrowthSections = []
        return;
      }
      
      // 使用正则表达式匹配所有的序号段落
      const sections = [];
      const regex = /(\d+\..*?)(?=\d+\.|$)/gs;
      let match;
      
      while ((match = regex.exec(content + "\n")) !== null) {
        const sectionContent = match[1].trim();
        const sectionNumber = sectionContent.split('.')[0];
        
        // 确定该区域是否已完成
        let isCompleted = false;
        
        if (this.isAuthor || this.isMarkLee) {
          // 作者视角：统计用户回复数量
          const userCount = (sectionContent.match(/<[^>]+>/g) || []).length;
          isCompleted = userCount >= this.num;
        } else {
          // 非作者视角：检查当前用户是否已回复
          const currentUser = localStorage.getItem('originRealName');
          const userPattern = new RegExp(`<${currentUser}>`, 'i');
          isCompleted = userPattern.test(sectionContent);
        }
        
        sections.push({
          number: sectionNumber,
          content: sectionContent,
          isCompleted: isCompleted
        });
      }
      
      this.interGrowthSections = sections;
    },
    
    // 从文本中提取问题序号
    extractQuestionNumbers(text) {
      if (!text) return [];
      const matches = text.match(/(\d+)\./g) || [];
      return matches.map(match => parseInt(match.replace('.', '')));
    },
    // 格式化区域内容，突出显示用户回复
    // formatSectionContent(content) {
    //   // 替换用户标签为突出显示的样式
    //   return content.replace(/<([^>]+)>(.*?)(?=<|$)/g, 
    //     '<div class="user-reply"><strong>$1 回复:</strong> $2</div>');
    // },
    formatSectionContent(content) {
      // 获取问题内容（第一行）
      const questionPart = content.split('<')[0].trim();

      // 如果是作者或该区域已完成，显示所有回复
      const section = this.interGrowthSections.find(s => s.content === content);
      const currentUser = localStorage.getItem('originRealName');
      
      if (this.isAuthor || section.isCompleted || this.isMarkLee) {
        // 提取所有用户回复
        const userMatches = content.match(/<([^>]+)>([^<]*)/g) || [];
        
        let formattedContent = questionPart;
        
        // 逐个添加用户回复
        userMatches.forEach(match => {
          const parts = match.match(/<([^>]+)>(.*)/s);
          if (parts) {
            const userName = parts[1];
            const userContent = parts[2].trim();
            formattedContent += `<div class="user-reply"><strong>${userName} 回复:</strong> ${userContent}</div>`;
          }
        });
        
        return formattedContent;
      } else {
        // 非作者且未完成回答，只显示问题内容
        return questionPart;
      }
    },

    // 检测是否包含序号格式
    containsBannedFormat(text) {
      // 匹配任何以数字+点开头的行
      // return /\n\d+\.|\r\d+\.|\r\n\d+\.|^\d+\./.test(text);

      // 匹配任何包含"数字+点"的文本（无论位置）或包含尖括号的文本
      const numberFormatRegex = /\d+\./;  // 匹配任何位置的数字+点
      const bracketRegex = /[<>]/;  // 匹配任何尖括号
      
      return numberFormatRegex.test(text) || bracketRegex.test(text);
    },
    
    // 编辑区域
    editSection(index) {
      if (this.isAuthor) {
        // 作者编辑整个内容
        this.tempInterGrowthTA2GL = this.cardInfo.interGrowthTA2GL;
        return;
      }
      
      // 非作者只能编辑单个区域
      if (this.interGrowthSections[index].isCompleted) {
        this.$message.warning('您已经回复过此问题');
        return;
      }
      
      this.isEditing = true;
      this.currentEditingIndex = index;
      this.editContentInterGrowth = '';
      this.currentAIFeedback = null
    },
    
    // 确认编辑（非作者）
    confirmEdit(index) {
      const content = this.editContentInterGrowth.trim();
      if (!content) {
        this.$message.warning('内容不能为空');
        return;
      }

      // 检查是否包含序号格式
      if (this.containsBannedFormat(content)) {
        this.$message.warning('内容不能包含任何序号+小数点格式（如1.、2.等）或尖括号（<、>）');
        return;
      }
      
      const section = this.interGrowthSections[index];
      const currentUser = localStorage.getItem('originRealName');
      
      // 构建要插入的内容
      // const insertContent = `<${currentUser}>${this.editContentInterGrowth.trim()}\n`;
      const insertContent = `\n<${currentUser}>${this.editContentInterGrowth.trim()}`;
      
      // 更新cardInfo.interGrowthTA2GL
      let updatedContent = this.cardInfo.interGrowthTA2GL;
      
      // 找到当前区域在原文中的位置并插入内容
      let regex;
      if (index === this.interGrowthSections.length - 1) {
        // 最后一个区域，匹配到结尾
        regex = new RegExp(`(${section.number}\\..*?)$`, 's');
      } else {
        // 非最后一个区域，匹配到下一个序号
        regex = new RegExp(`(${section.number}\\..*?)(?=\\n\\d+\\.|$)`, 's');
      }
      updatedContent = updatedContent.replace(regex, `$1${insertContent}`);
      
      // 准备提交数据
      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('newInterGrowth', updatedContent);
      formData.append('sectionNumber', section.number);
      formData.append('userContent', this.editContentInterGrowth.trim());
      formData.append('userName', currentUser);

      formData.append('writerName', localStorage.getItem('realName'));
      formData.append('bookName', localStorage.getItem('userId').substring(localStorage.getItem('realName').length + 1));
      
      // 发送请求
      this.updateInterGrowth(formData);

      // 获取红蓝卡标打分
      setTimeout(() => {
        this.isLoadingAI = true;      
        // 准备请求数据
        let formData = new FormData();
        formData.append('cid', this.cid);
        formData.append('cardContent', this.cardInfo.content);
        formData.append('sectionNumber', this.interGrowthSections[index].number);
        formData.append('sectionQuestion', this.interGrowthSections[index].content); // 添加问题内容
        formData.append('content', this.editContentInterGrowth.trim());
        formData.append('userName', localStorage.getItem('originRealName'));
        // 调用API获取AI评分与建议
        getAIFeedback(formData).then(response => {
          if (response.error_num === 0) {
            // 解析AI反馈
            this.currentAIFeedback = {
              score: response.score,
              title: response.title || '回答需要改进',
              points: this.parseImprovement(response.suggestion)
            };
            // 更新卡片的subareaAndHLAndSugTA2GL数据
            if (response.updated_subareaData) {
              this.cardInfo.subareaAndHLAndSugTA2GL = response.updated_subareaData;
            }
          } else {
            this.$message.error('获取AI评分失败: ' + response.msg);
          }
        }).catch(error => {
          this.$message.error('获取AI评分出错');
          console.error(error);
        }).finally(() => {
          this.isLoadingAI = false;
          // 重置编辑状态
          this.isEditing = false;
          this.currentEditingIndex = -1;
          this.editContentInterGrowth = '';
          this.currentAIFeedback = null

          // 检查是否所有问题都已回答，如果是则生成综合建议
          this.$nextTick(() => {
            if (!this.hasIncompleteResponses) {
              this.generateComprehensiveAdvice();
            }
          });
        });
      }, 500); // 延迟0.5秒执行
    },
    
    // 作者保存整个共生区内容
    saveAuthorEdit() {
      // 验证格式
      const formatRegex = /^\d+\..+(\n\d+\..+)*$/s;
      if (!formatRegex.test(this.tempInterGrowthTA2GL.trim())) {
        this.$message.error('格式不正确，请按照要求填写');
        return;
      }

      // 提取所有问题序号
      const questionNumbers = this.extractQuestionNumbers(this.tempInterGrowthTA2GL);
      // 检查是否所有问题都已分配区域
      const unassignedQuestions = questionNumbers.filter(num => 
        !this.questionAreaMapping[num] || 
        !['目标区', '任务区', '分工区'].includes(this.questionAreaMapping[num])
      );
      if (unassignedQuestions.length > 0) {
        this.$message.error(`请为所有问题分配区域。未分配区域的问题: ${unassignedQuestions.join(', ')}`);
        return;
      }
      
      // 更新内容
      this.cardInfo.interGrowthTA2GL = this.tempInterGrowthTA2GL;
      this.shouldBeFront = true;

      // 准备区域分配数据
      const areas = {
        "目标区": [],
        "任务区": [],
        "分工区": []
      };

      // 将问题分配到对应区域
      for (const [numStr, area] of Object.entries(this.questionAreaMapping)) {
        const num = parseInt(numStr);
        if (area && areas[area]) {
          areas[area].push(num);
        }
      }
      // 准备或更新 subareaAndHLAndSugTA2GL 数据
      let subareaData = {};
      try {
        if (this.cardInfo.subareaAndHLAndSugTA2GL) {
          subareaData = JSON.parse(this.cardInfo.subareaAndHLAndSugTA2GL);
        }
      } catch (e) {
        subareaData = {};
      }
      // 更新区域分配数据
      subareaData.areas = areas;
      if (!subareaData.ratings) subareaData.ratings = {};
      if (!subareaData.comprehensive) subareaData.comprehensive = {};
      // 将更新后的数据转换为JSON字符串
      this.cardInfo.subareaAndHLAndSugTA2GL = JSON.stringify(subareaData);
      
      // 准备提交数据
      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('newInterGrowth', this.cardInfo.interGrowthTA2GL);
      formData.append('username', localStorage.getItem('realName'));
      formData.append('bookName', localStorage.getItem('userId').substring(localStorage.getItem('realName').length + 1));
      formData.append('subareaAndHLAndSugTA2GL', this.cardInfo.subareaAndHLAndSugTA2GL);  // 新增共生问题分区情况
      
      // 发送请求
      changeInterGrowth(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('保存成功');
          this.$emit('updateOrDeleteCard');
          this.parseInterGrowthSections(); // 重新解析区域
        } else {
          alert("error!");
        }
      }).catch(error => {
        alert("error!2");
        console.log('error', error.message);
      });
    },
    
    // 更新共生区内容（非作者）
    updateInterGrowth(formData) {
      // this.shouldBeFront = true;

      // 调用后端API
      changeInterGrowthForUser(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('回复成功');
          // 更新本地数据
          this.cardInfo.interGrowthTA2GL = response.updated_content || formData.get('newInterGrowth');
          this.parseInterGrowthSections(); // 重新解析区域
          this.$emit('updateOrDeleteCard');
        } else {
          alert("保存失败: " + response.msg);
        }
      }).catch(error => {
        alert("保存出错!");
        console.log('error', error.message);
      });
    },

    // 生成综合建议
    generateComprehensiveAdvice() {
      // 如果已经有当前用户的综合建议，就不再生成
      if (this.subareaDataParsed && 
          this.subareaDataParsed.comprehensive && 
          this.subareaDataParsed.comprehensive[localStorage.getItem('originRealName')]) {
        return;
      }
      
      // 准备数据，包括卡片内容和用户回复
      const currentUser = localStorage.getItem('originRealName');
      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('content', this.cardInfo.content);
      formData.append('interGrowthTA2GL', this.cardInfo.interGrowthTA2GL);
      formData.append('username', currentUser);
      formData.append('subareaAndHLAndSugTA2GL', this.cardInfo.subareaAndHLAndSugTA2GL);
      
      // 设置加载状态
      this.isGeneratingAdvice = true;
      
      // 发送请求
      generateComprehensiveAdvice(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('综合建议生成成功');
          // 更新本地数据
          this.cardInfo.subareaAndHLAndSugTA2GL = response.updated_data;
          // 通知父组件更新
          // this.$emit('updateOrDeleteCard');
        } else {
          this.$message.error("生成综合建议失败: " + response.msg);
          console.log("卡片左栏综合建议失败！", response.msg)
        }
      }).catch(error => {
        this.$message.error("系统错误，请稍后再试");
        console.error('生成综合建议出错', error.message);
      }).finally(() => {
        this.isGeneratingAdvice = false;
      });
    },

    // // 处理双击事件，阻止默认的doubleClickOver行为以便我们可以响应单击编辑
    // handleDoubleClick(event) {
    //   event.stopPropagation();
    //   return false;
    // },
    // toggleAndConfirmLastContent() {
    //   if (this.showLastContentNormal === false) {
    //     this.showLastContentNormal = true;

    //     let formData = new FormData();
    //     formData.append('username', localStorage.getItem('userId'));
    //     formData.append('cid', this.cid);
    //     formData.append('mode', 'normal')
    //     backCardVersion(formData).then(data => {
    //       this.$message.success('回退成功！')
    //       this.shouldBeFront = true;
    //     }).catch(error => {
    //       console.error("An error occurred:", error); // 错误处理
    //     });
    //   } else {
    //     this.$message.warning('您已经回退过了')
    //   }
    // },

    toggleLastContentNormal() {
      this.showLastContentNormal = !this.showLastContentNormal;

      if(this.showLastContentNormal === true && this.cardInfo.lastContent === "") {
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', this.cid);
        getLastContent(formData).then(data => {
          this.cardInfo.lastContent = data['lastContent']
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
      }
    },
    confirmLastContentNormal() {
      this.showLastContentNormal = false;

      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      formData.append('mode', 'normal')
      backCardVersion(formData).then(data => {
        this.$message.success('回退成功！')
        this.shouldBeFront = true;
        this.hideCardDialog()
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },

    toggleLastContent() {
      this.showLastContent = !this.showLastContent;

      if(this.showLastContent === true && this.cardInfo.lastContent === "") {
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', this.cid);
        getLastContent(formData).then(data => {
          this.cardInfo.lastContent = data['lastContent']
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
      }
    },
    confirmLastContent() {
      this.showLastContent = false;

      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      backCardVersion(formData).then(data => {
        this.$message.success('回退成功！')
        this.shouldBeFront = true;
        this.hideCardDialog()
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },

    getBackgroundColor() {
      // 🔥 如果是永久卡片且有四色属性，使用深色背景（按四色属性颜色加深）
      // 优先使用props中的fourColorType，如果没有则从card中获取
      const fourColorTypeValue = this.fourColorType || (this.card && this.card.four_color_type) || '';
      if (this.card && this.card.type && this.card.type.includes('永久') && fourColorTypeValue) {
        // 🔥 调整深色卡颜色，进一步降低饱和度和不透明度，调浅一些
        const deepColorMap = {
          'R': '#C07070',  // 深红色（稍微深一点）
          'B': '#5B8BC1',  // 深蓝色（稍微深一点）
          'P': '#947DBF',  // 深紫色（稍微深一点）
          'G': '#7CB57C'   // 深绿色（保持不变）
        };
        return deepColorMap[fourColorTypeValue] || '#6a6a6a'; // 默认深灰色（调浅）
      }

      // 🔥 如果为高价值卡片，按四色属性显示底色（覆盖原先进化卡片的底色规则）
      if (this.isHighValue && this.fourColorType) {
        const colorMap = {
          'R': 'rgba(255, 160, 160, 0.30)',  // 红色：降低GB值(185→160)提高饱和度，稍微提高透明度
          'B': 'rgba(205, 233, 241, 0.28)',  // 蓝色：保持不变✓
          'P': 'rgba(245, 195, 230, 0.32)',  // 紫色：提高R(238→245)，降低B(238→230)，偏红紫
          'G': 'rgba(200, 235, 205, 0.65)'   // 绿色：保持不变✓
        };
        return colorMap[this.fourColorType] || '#ffffff';
      }

      // 默认背景色
      let defaultColor = '#ffffff';
      
      // 如果是永久类型但没有四色属性，使用原来的逻辑
      if (this.card && this.card.type && this.card.type.includes('永久')) {
        // 检查scoreSFT是否有效 (正数)
        if (this.card.scoreSFT && this.card.scoreSFT > 0) {
          // 1-4分使用绿色渐变，保持原色调
          if (this.card.scoreSFT >= 1 && this.card.scoreSFT < 4) {
            // 从最浅绿色到深绿色的映射
            if (this.card.scoreSFT <= 2) {
              // 1-2分，浅绿色范围
              const ratio = (this.card.scoreSFT - 1) / 1; // 0-1的比例
              return this.blendColors('#e8f5e9', '#c8e6c9', ratio); // 保持原色调，浅绿到原始绿
            } else {
              // 2-4分，中绿色到深绿色范围
              const ratio = (this.card.scoreSFT - 2) / 2; // 0-1的比例
              return this.blendColors('#c8e6c9', '#a5d6a7', ratio); // 调整深色，不要太深
            }
          } 
          // 4-5分使用更淡的紫色渐变
          else if (this.card.scoreSFT >= 4 && this.card.scoreSFT <= 5) {
            // 从浅紫色到中等紫色，整体调淡
            const ratio = (this.card.scoreSFT - 4) / 1; // 0-1的比例
            return this.blendColors('#e6e0ee', '#cdc1e0', ratio); // 更淡的紫色，确保与深灰色字体有对比度
          }
          // 其他分数区间使用默认永久卡颜色
          else {
            return '#c8e6c9';
          }
        }
        // 无有效分数时使用默认永久卡颜色
        return '#c8e6c9';
      }
      
      // 不是永久类型，返回默认背景色
      return defaultColor;
    },

    // 🔥 判断是否为深色永久卡片（用于文字颜色）
    isDeepPermanentCard() {
      const fourColorTypeValue = this.fourColorType || (this.card && this.card.four_color_type) || '';
      return this.card && this.card.type && this.card.type.includes('永久') && fourColorTypeValue;
    },
    
    // 🔥 判断是否为关键词神经元永久卡片（用于特殊布局）
    isKeywordPermanentCard() {
      return (this.cardInfo && this.cardInfo.title && this.cardInfo.title.includes('关键词神经元永久卡')) &&
             (this.card && this.card.type && this.card.type.includes('永久'));
    },
    
    // 🔥 获取关键词神经元永久卡主体内容的背景颜色（根据四色属性）
    getKeywordPermanentCardContentBackground() {
      const fourColorTypeValue = this.fourColorType || (this.card && this.card.four_color_type) || '';
      
      if (fourColorTypeValue) {
        // 根据四色类型返回对应的背景色（与卡片四色属性保持一致）
        const colorMap = {
          'R': 'rgba(255, 160, 160, 0.30)',  // 红色
          'B': 'rgba(173, 216, 230, 0.40)',  // 蓝色（调深一些，从0.28改为0.40，从205,233,241改为173,216,230）
          'P': 'rgba(138, 43, 226, 0.20)',   // 紫色（降低透明度，从0.25改为0.20）
          'G': 'rgba(200, 235, 205, 0.65)'   // 绿色
        };
        return colorMap[fourColorTypeValue] || '#e8f5e9'; // 默认浅绿色
      }
      
      // 如果没有四色属性，使用默认浅绿色
      return '#e8f5e9';
    },
    
    // 🔥 获取关键词神经元永久卡主体内容悬停时的背景颜色（根据四色属性，颜色稍微加深）
    getKeywordPermanentCardContentBackgroundHover() {
      const fourColorTypeValue = this.fourColorType || (this.card && this.card.four_color_type) || '';
      
      if (fourColorTypeValue) {
        // 根据四色类型返回对应的悬停背景色（稍微加深，但不要太深）
        const colorMap = {
          'R': 'rgba(255, 155, 155, 0.35)',  // 红色稍微加深（从0.38降到0.35）
          'B': 'rgba(173, 216, 230, 0.47)',  // 蓝色稍微加深（从0.50降到0.47）
          'P': 'rgba(138, 43, 226, 0.28)',   // 紫色稍微加深（从0.32降到0.28）
          'G': 'rgba(200, 235, 205, 0.70)'   // 绿色稍微加深（从0.75降到0.70）
        };
        return colorMap[fourColorTypeValue] || '#d4edda'; // 默认浅绿色稍微加深
      }
      
      // 如果没有四色属性，使用默认浅绿色稍微加深
      return '#d4edda';
    },

    // 🔥 判断卡片是否与当前勾选的文档相关
    isRelatedDocSelected() {
      if (!this.selectedCardId || !this.selectedDocs) return false;
      
      try {
        // 通过$parent.$parent访问CardGrid的cardList
        const cardList = this.$parent.$parent?.cardList || this.$parent?.cardList;
        if (!cardList || !Array.isArray(cardList) || cardList.length === 0) return false;
        
        // 查找当前勾选的卡片
        const currentCard = cardList.find(c => c.cid === this.selectedCardId);
        if (!currentCard || !currentCard.selected_docs) return false;
        
        const currentCardDocs = typeof currentCard.selected_docs === 'string' 
          ? JSON.parse(currentCard.selected_docs) 
          : currentCard.selected_docs;
        
        if (!Array.isArray(currentCardDocs)) return false;
        
        // 判断此卡片的selected_docs是否与勾选卡片的selected_docs有交集
        const thisCardDocs = typeof this.selectedDocs === 'string' 
          ? JSON.parse(this.selectedDocs) 
          : this.selectedDocs;
        
        if (!Array.isArray(thisCardDocs)) return false;
        
        return currentCardDocs.some(doc => thisCardDocs.includes(doc));
      } catch (e) {
        console.error('解析selected_docs失败:', e);
        return false;
      }
    },

    // 🔥 获取四色类型显示文本
    getFourColorTypeDisplay(type) {
      const typeMap = {
        'R': '红色',
        'B': '蓝色',
        'P': '紫色',
        'G': '绿色'
      };
      return typeMap[type] || '未设置';
    },
    
    // 🔥 获取DMT层次显示文本
    getDmtLevelDisplay(level) {
      const levelMap = {
        'D': '枝(D)',
        'M': '干(M)',
        'T': '根(T)'
      };
      return levelMap[level] || '未设置';
    },
    
    // 🔥 获取四色类型颜色
    getFourColorTypeColor(type) {
      const colorMap = {
        'R': '#ff6b6b',
        'B': '#4dabf7',
        'P': '#ae3ec9',
        'G': '#51cf66'
      };
      return colorMap[type] || '#666';
    },
    
    // 🔥 获取DMT层次颜色
    getDmtLevelColor(level) {
      const colorMap = {
        'D': '#868e96',
        'M': '#495057',
        'T': '#212529'
      };
      return colorMap[level] || '#666';
    },
    
    // 🔥 重置类型编辑
    resetTypeEdit() {
      this.editingFourColorType = this.fourColorType || '';
      this.editingDmtLevel = this.dmtLevel || '';
      this.showTypeEditDialog = false;
    },
    
    // 🔥 保存类型编辑
    saveTypeEdit() {
      if (!this.hasCardEditPermission()) {
        this.$message.error('您没有权限修改此卡片');
        return;
      }
      
      this.savingType = true;
      const formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      formData.append('four_color_type', this.editingFourColorType || '');
      formData.append('dmt_level', this.editingDmtLevel || '');
      
      import('@/api/card_zym/card_js').then(({ card_updateType }) => {
        card_updateType(formData).then(response => {
          if (response.error_num === 0) {
            this.$message.success('卡片类型更新成功');
            
            // 🔥 立即更新当前卡片对象的数据（前端显示立即更新）
            if (this.card) {
              this.card.four_color_type = this.editingFourColorType || '';
              this.card.dmt_level = this.editingDmtLevel || '';
            }
            
            // 同时更新cardList中对应的卡片数据（确保列表视图也更新）
            const cardListParent = this.$parent.$parent || this.$parent;
            if (cardListParent && cardListParent.cardList) {
              const cardInList = cardListParent.cardList.find(c => c.cid === this.cid);
              if (cardInList) {
                cardInList.four_color_type = this.editingFourColorType || '';
                cardInList.dmt_level = this.editingDmtLevel || '';
              }
            }
            
            // 更新本地数据（通知父组件刷新整个列表，确保其他地方的显示也更新）
            this.$parent.$parent?.get_all_cards?.() || this.$parent?.get_all_cards?.();
            this.showTypeEditDialog = false;
          } else {
            this.$message.error('更新失败：' + response.msg);
          }
        }).catch(error => {
          this.$message.error('更新失败，请重试');
          console.error('更新卡片类型失败:', error);
        }).finally(() => {
          this.savingType = false;
        });
      });
    },

    // 颜色混合函数
    blendColors(color1, color2, ratio) {
      // 解析两个颜色的RGB值
      const r1 = parseInt(color1.substring(1, 3), 16);
      const g1 = parseInt(color1.substring(3, 5), 16);
      const b1 = parseInt(color1.substring(5, 7), 16);
      
      const r2 = parseInt(color2.substring(1, 3), 16);
      const g2 = parseInt(color2.substring(3, 5), 16);
      const b2 = parseInt(color2.substring(5, 7), 16);
      
      // 混合两个颜色
      const r = Math.round(r1 + (r2 - r1) * ratio);
      const g = Math.round(g1 + (g2 - g1) * ratio);
      const b = Math.round(b1 + (b2 - b1) * ratio);
      
      // 转换回十六进制颜色格式
      return '#' + 
        ((1 << 24) + (r << 16) + (g << 8) + b)
          .toString(16)
          .slice(1);
    },

    // 编辑标题
    editTitle(event) {
      // 阻止事件冒泡
      if (event) {
        event.stopPropagation();
      }

      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限编辑卡片');
      //   return
      // }
      if(!this.hasCardEditPermission()) {
        this.$message.error('您没有权限编辑此卡片');
        return
      }

      if(this.isContentLoading === true) {
        this.$message.warning('正在加载完整卡片内容，请您稍等几秒钟');
        return;
      }
      
      // 设置编辑状态
      this.isEditingTitle = true;
      this.tempTitle = this.cardInfo.contentTitle;
      
      // 下一个 DOM 更新循环后聚焦到输入框
      this.$nextTick(() => {
        // 聚焦到编辑框（优先检查永久卡片的input ID）
        const titleInput = document.getElementById('edit-title-input-permanent') || document.getElementById('edit-title-input');
        if (titleInput) {
          // 如果是 el-input，需要获取内部的 input 元素
          const inputEl = titleInput.querySelector('input') || titleInput;
          inputEl.focus();
        }
      });
    },

    // 编辑关键词
    editKeywords(event) {
      // 阻止事件冒泡
      if (event) {
        event.stopPropagation();
      }

      if (this.isKeywordsGenerating) {
        this.$message.info('语义关键词还在理解和生成中，请稍后再编辑');
        return;
      }

      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限编辑卡片');
      //   return
      // }
      if(!this.hasCardEditPermission()) {
        this.$message.error('您没有权限编辑此卡片');
        return
      }

      if(this.isContentLoading === true) {
        this.$message.warning('正在加载完整卡片内容，请您稍等几秒钟');
        return;
      }
      
      // 设置编辑状态
      this.isEditingKeywords = true;
      this.tempKeywords = this.cardInfo.keyWords;
      
      // 下一个 DOM 更新循环后聚焦到输入框
      this.$nextTick(() => {
        // 聚焦到编辑框（优先检查永久卡片的input ID）
        const keywordsInput = document.getElementById('edit-keywords-input-permanent') || document.getElementById('edit-keywords-input');
        if (keywordsInput) {
          // 如果是 el-input，需要获取内部的 input 元素
          const inputEl = keywordsInput.querySelector('input') || keywordsInput;
          inputEl.focus();
        }
      });
    },

    // 处理鼠标按下事件
    handleMouseDown(event) {
      this.mouseDownPos = {
        x: event.clientX,
        y: event.clientY
      };
    },

    // 处理鼠标抬起事件
    handleMouseUp(event) {
      this.mouseUpPos = {
        x: event.clientX,
        y: event.clientY
      };

      // 检查是否进行了拖拽操作
      if (this.mouseDownPos && this.mouseUpPos) {
        const deltaX = Math.abs(this.mouseUpPos.x - this.mouseDownPos.x);
        const deltaY = Math.abs(this.mouseUpPos.y - this.mouseDownPos.y);
        const dragThreshold = 5; // 5像素的拖拽阈值
        
        if (deltaX > dragThreshold || deltaY > dragThreshold) {
          // 检测到拖拽操作，标记为刚刚拖拽过
          this.justDragged = true;
          console.log('检测到拖拽操作，标记justDragged为true');
        }
      }
    },

    // 编辑内容 - 区分单击、双击和拖拽操作
    editContentInline(event) {
      // 阻止事件冒泡
      if (event) {
        event.stopPropagation();
      }

      // 拖拽操作后第一次点击去除高亮不进入编辑状态
      if (this.firstClickAftDrag) {
        this.firstClickAftDrag = false; // 重置拖拽后的第一次点击(取消高亮)标记
        return;
      }

      // 如果刚刚进行了拖拽操作，鼠标抬起时不进入编辑状态
      if (this.justDragged) {
        console.log('拖拽局部文本复制，不进入编辑状态');
        this.justDragged = false; // 重置拖拽标记
        this.firstClickAftDrag = true; // 拖拽后的第一次点击应该不进入编辑
        return;
      }
      
      // 使用单击计时器区分单击和双击
      if (this.clickTimer) {
        // 如果有定时器存在，说明这是双击的第二次点击，清除定时器不执行编辑
        clearTimeout(this.clickTimer);
        this.clickTimer = null;
        // 不进入编辑状态，让双击事件正常处理
        console.log('检测到双击，不进入编辑状态');
        return;
      }

      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限编辑卡片');
      //   return;
      // }
      if(!this.hasCardEditPermission()) {
        this.$message.error('您没有权限编辑此卡片');
        return
      }

      if(this.isContentLoading === true) {
        this.$message.warning('正在加载完整卡片内容，请您稍等几秒钟');
        return;
      }
      
      // 设置单击计时器，延迟执行编辑操作
      this.clickTimer = setTimeout(() => {
        // 检查是否有拖拽操作（鼠标按下和抬起位置不同）
        if (this.mouseDownPos && this.mouseUpPos) {
          const deltaX = Math.abs(this.mouseUpPos.x - this.mouseDownPos.x);
          const deltaY = Math.abs(this.mouseUpPos.y - this.mouseDownPos.y);
          const dragThreshold = 5; // 5像素的拖拽阈值
          
          if (deltaX > dragThreshold || deltaY > dragThreshold) {
            console.log('检测到拖拽操作，不进入编辑状态');
            this.clickTimer = null;
            return;
          }
        }

        // 这是单击操作，进入编辑状态
        if (this.showLastContent === false) {
          console.log('检测到单击，进入编辑状态');
          
          // 🔥 记录点击的字符位置（优先使用AnswerParser计算的位置和上下文）
          let clickedCharPosition = 0;
          let charContext = null;
          
          // 🔥 优先使用AnswerParser计算的位置和上下文（通过event._calculatedCharPosition和event._calculatedCharContext传递）
          if (event && event._calculatedCharPosition !== undefined) {
            clickedCharPosition = event._calculatedCharPosition;
            charContext = event._calculatedCharContext || null;
            console.log(`[editContentInline] 使用AnswerParser计算的字符位置: ${clickedCharPosition}`);
            if (charContext) {
              console.log(`[editContentInline] AnswerParser提供的上下文: 字符="${charContext.char}", 前="${charContext.before.substring(Math.max(0, charContext.before.length - 30))}", 后="${charContext.after.substring(0, Math.min(30, charContext.after.length))}"`);
            }
          } else if (event && event.target) {
            // 如果AnswerParser没有提供位置，使用原来的TreeWalker方法（向后兼容）
            console.log(`[editContentInline] AnswerParser未提供位置，使用TreeWalker方法计算`);
            
            // 找到内容容器（支持多种卡片类型）
            const contentElement = event.target.closest('.content-hover-area-tidy') || 
                                  event.target.closest('.content-hover-area') || 
                                  event.target;
            if (contentElement) {
              console.log(`[editContentInline] 点击的元素:`, event.target);
              console.log(`[editContentInline] 内容容器:`, contentElement);
              
              // 方法：使用 caretRangeFromPoint 获取精确位置
              let range = null;
              if (document.caretRangeFromPoint) {
                // 标准方法
                range = document.caretRangeFromPoint(event.clientX, event.clientY);
              } else if (document.caretPositionFromPoint) {
                // Firefox
                const caretPos = document.caretPositionFromPoint(event.clientX, event.clientY);
                if (caretPos) {
                  range = document.createRange();
                  range.setStart(caretPos.offsetNode, caretPos.offset);
                  range.setEnd(caretPos.offsetNode, caretPos.offset);
                }
              }
              
              if (range && range.startContainer) {
                console.log(`[editContentInline] 找到Range, startContainer:`, range.startContainer, `startOffset: ${range.startOffset}`);
                
                // 创建一个TreeWalker来遍历contentElement中的所有文本节点
                const walker = document.createTreeWalker(
                  contentElement,
                  NodeFilter.SHOW_TEXT,
                  null
                );
                
                let charCount = 0;
                let found = false;
                let node;
                
                // 遍历所有文本节点
                while (node = walker.nextNode()) {
                  if (node === range.startContainer) {
                    // 找到了点击的文本节点
                    charCount += range.startOffset;
                    found = true;
                    console.log(`[editContentInline] 找到点击的文本节点, startOffset: ${range.startOffset}, 当前累计字符位置: ${charCount}`);
                    break;
                  } else {
                    // 累加前面的文本长度
                    charCount += node.textContent.length;
                  }
                }
                
                if (found) {
                  clickedCharPosition = charCount;
                  console.log(`[editContentInline] 通过Range计算得到字符位置: ${clickedCharPosition}`);
                } else {
                  // 如果startContainer不在文本节点中（可能在span等元素中），尝试其他方法
                  console.log(`[editContentInline] startContainer不在文本节点中，尝试从元素中计算`);
                  
                  // 如果startContainer是元素节点，尝试获取其文本内容
                  let targetNode = range.startContainer;
                  if (targetNode.nodeType !== Node.TEXT_NODE) {
                    // 如果是元素节点，可能需要找到包含它的文本节点
                    targetNode = targetNode.firstChild;
                  }
                  
                  // 重新遍历，这次也考虑元素节点
                  const allWalker = document.createTreeWalker(
                    contentElement,
                    NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT,
                    null
                  );
                  
                  charCount = 0;
                  found = false;
                  let elementNode;
                  
                  while (elementNode = allWalker.nextNode()) {
                    if (elementNode.nodeType === Node.TEXT_NODE) {
                      if (elementNode === targetNode || elementNode.parentNode === targetNode) {
                        charCount += range.startOffset;
                        found = true;
                        console.log(`[editContentInline] 在元素节点中找到位置, startOffset: ${range.startOffset}, 累计: ${charCount}`);
                        break;
                      } else {
                        charCount += elementNode.textContent.length;
                      }
                    }
                  }
                  
                  if (found) {
                    clickedCharPosition = charCount;
                  } else {
                    // 最后备用方法：直接使用textContent的长度
                    const textContent = contentElement.textContent || '';
                    clickedCharPosition = Math.min(range.startOffset, textContent.length);
                    console.log(`[editContentInline] 使用备用方法，字符位置: ${clickedCharPosition}`);
                  }
                }
              } else {
                console.log(`[editContentInline] 无法获取Range，尝试使用textContent计算`);
                // 备用方法：直接使用textContent
                const textContent = contentElement.textContent || '';
                clickedCharPosition = textContent.length;
                console.log(`[editContentInline] 使用textContent长度作为位置: ${clickedCharPosition}`);
              }
              
              clickedCharPosition = Math.min(clickedCharPosition, this.cardInfo.content.length);
              console.log(`[editContentInline] 最终字符位置: ${clickedCharPosition}, 内容总长度: ${this.cardInfo.content.length}`);
              console.log(`[editContentInline] 字符位置对应的内容预览: "${this.cardInfo.content.substring(Math.max(0, clickedCharPosition - 20), clickedCharPosition + 20).replace(/\n/g, '\\n')}"`);
            } else {
              console.log(`[editContentInline] 未找到内容容器元素`);
            }
          } else {
            console.log(`[editContentInline] event或event.target为空`);
          }
          
          // 保存点击的字符位置到组件实例
          this.clickedCharPosition = clickedCharPosition;
          console.log(`[editContentInline] 保存的字符位置: ${this.clickedCharPosition}`);

          // 🔥 保存进入编辑前的卡片外层滚动位置
          if (this.$refs.cardDialog) {
            this._cardScrollTopBeforeEdit = this.$refs.cardDialog.scrollTop;
            console.log(`[editContentInline] 保存卡片滚动位置: ${this._cardScrollTopBeforeEdit}`);
          }
          
          // 🔥 使用传给AnswerParser的原始内容（与AnswerParser计算的position一致）
          const answerContent = this.showLastContent ? this.cardInfo.lastContent : this.cardInfo.content;
          this.isEditingContent = true;
          this.tempContent = answerContent;
          // 🔥 保存原始内容，用于保存时diff对比
          this._originalContentBeforeEdit = answerContent;
          
          console.log(`[editContentInline] 使用的内容长度: ${answerContent.length}, cardInfo.content长度: ${this.cardInfo.content.length}`);
          if (answerContent !== this.cardInfo.content) {
            console.log(`[editContentInline] ⚠️ answerContent和cardInfo.content不同，使用answerContent以保证位置一致性`);
            // 分析差异：计算字符差异
            const diff = Math.abs(answerContent.length - this.cardInfo.content.length);
            console.log(`[editContentInline] 📊 长度差异: ${diff} 字符 (${((diff / Math.max(answerContent.length, this.cardInfo.content.length)) * 100).toFixed(2)}%)`);
          }
          
          // 保存上下文信息（用于后续精确定位）
          this._clickedCharContext = charContext;
          
          // 下一个 DOM 更新循环后聚焦到输入框
          this.$nextTick(() => {
            // 聚焦到编辑框（优先检查永久卡片的input ID）
            const contentInput = document.getElementById('edit-content-input-permanent') || document.getElementById('edit-content-input');
            if (contentInput) {
              // 如果是 el-input 的 textarea，需要找到内部的 textarea 元素
              const textareaEl = contentInput.querySelector('textarea') || contentInput;
              
              if (textareaEl && textareaEl.tagName === 'TEXTAREA') {
                // 设置焦点
                textareaEl.focus();
              
              // 添加键盘事件监听
                textareaEl.addEventListener('keydown', this.handleGlobalKeyDown, {
                capture: true,
                passive: false
              });
                
                // 🔥 等待0.5s后再设置滚动位置和光标位置
                setTimeout(() => {
                  if (this.clickedCharPosition > 0) {
                    let position = Math.min(this.clickedCharPosition, textareaEl.value.length);
                    const lengthDiff = this.tempContent.length - textareaEl.value.length;
                    console.log(`[editContentInline] 初始位置: ${position}, textarea总长度: ${textareaEl.value.length}`);
                    if (lengthDiff !== 0) {
                      console.log(`[editContentInline] 📊 tempContent长度(${this.tempContent.length})与textarea长度(${textareaEl.value.length})差异: ${lengthDiff}字符`);
                      console.log(`[editContentInline] 💡 这可能是因为AnswerParser的answer包含代码块标记而cardInfo.content不包含，或存在其他格式差异`);
                    }
                    
                    // 🔥 如果有上下文信息，使用上下文来精确定位
                    if (this._clickedCharContext && this._clickedCharContext.char) {
                      const targetChar = this._clickedCharContext.char;
                      const targetBefore = this._clickedCharContext.before;
                      const targetAfter = this._clickedCharContext.after;
                      
                      const textareaValue = textareaEl.value;
                      
                      // 🔥 规范化文本：统一换行符（用于匹配，但不改变长度映射）
                      const normalizeLineBreaks = (text) => {
                        return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
                      };
                      
                      // 🔥 移除markdown标记（用于匹配）
                      const removeMarkdown = (text) => {
                        return text.replace(/\*\*/g, '').replace(/\*/g, '').replace(/^#{1,6}\s+/gm, '').replace(/`/g, '');
                      };
                      
                      // 🔥 移除标点符号和空白（仅用于匹配判断，不影响位置计算）
                      const removePunctuation = (text) => {
                        return text.replace(/[，。！？；：、""''（）【】\s]/g, '');
                      };
                      
                      // 🔥 核心匹配：目标字符 + 前5字 + 后5字（必须精确匹配）
                      const coreBefore = targetBefore.substring(Math.max(0, targetBefore.length - 5));
                      const coreAfter = targetAfter.substring(0, Math.min(5, targetAfter.length));
                      const corePattern = coreBefore + targetChar + coreAfter;
                      
                      console.log(`[editContentInline] 🔍 核心匹配模式（必须匹配）: "${corePattern}"`);
                      
                      // 🔥 在textarea中搜索所有可能的核心匹配位置（先尝试原始匹配）
                      const normalizedTextarea = normalizeLineBreaks(textareaValue);
                      const normalizedCorePattern = normalizeLineBreaks(corePattern);
                      
                      let coreMatches = [];
                      let searchIndex = 0;
                      while ((searchIndex = normalizedTextarea.indexOf(normalizedCorePattern, searchIndex)) !== -1) {
                        coreMatches.push({
                          index: searchIndex,
                          type: 'normal'
                        });
                        searchIndex += 1;
                      }
                      
                      // 如果没找到，尝试移除markdown标记后再搜索
                      if (coreMatches.length === 0) {
                        const cleanedTextarea = normalizeLineBreaks(removeMarkdown(textareaValue));
                        const cleanedCorePattern = normalizeLineBreaks(removeMarkdown(corePattern));
                        searchIndex = 0;
                        while ((searchIndex = cleanedTextarea.indexOf(cleanedCorePattern, searchIndex)) !== -1) {
                          // 需要映射回原始位置：在原始文本中找到对应位置
                          // 简化：使用相同索引（因为markdown标记通常不会影响核心匹配的位置偏移太多）
                          const originalIndex = textareaValue.substring(0, searchIndex + 100).length - 100;
                          coreMatches.push({
                            index: searchIndex, // 使用清理后的索引，后续会用上下文校正
                            type: 'cleaned'
                          });
                          searchIndex += 1;
                        }
                      }
                      
                      // 如果还是没找到，尝试移除标点符号后搜索
                      if (coreMatches.length === 0) {
                        const noPunctTextarea = removePunctuation(normalizeLineBreaks(textareaValue));
                        const noPunctPattern = removePunctuation(normalizeLineBreaks(corePattern));
                        searchIndex = 0;
                        while ((searchIndex = noPunctTextarea.indexOf(noPunctPattern, searchIndex)) !== -1) {
                          // 需要映射回原始位置（这个比较复杂，先记录，后续用上下文校正）
                          coreMatches.push({
                            index: searchIndex,
                            type: 'noPunct'
                          });
                          searchIndex += 1;
                        }
                      }
                      
                      console.log(`[editContentInline] 🔍 找到${coreMatches.length}个核心匹配位置`);
                      
                      if (coreMatches.length > 0) {
                        // 🔥 使用更长的上下文来筛选最匹配的位置（从长到短）
                        let bestMatch = null;
                        let bestPosition = -1;
                        let usedStrategy = '';
                        
                        const contextLengths = [50, 40, 30, 20, 10];
                        
                        for (const contextLen of contextLengths) {
                          const contextBefore = targetBefore.substring(Math.max(0, targetBefore.length - contextLen));
                          const contextAfter = targetAfter.substring(0, Math.min(contextLen, targetAfter.length));
                          const fullContextPattern = contextBefore + targetChar + contextAfter;
                          
                          // 对每个核心匹配位置，检查是否符合上下文
                          for (const coreMatch of coreMatches) {
                            const coreMatchIndex = coreMatch.index;
                            
                            // 计算在这个位置周围应该出现的上下文范围
                            const contextStart = Math.max(0, coreMatchIndex - contextBefore.length);
                            const contextEnd = Math.min(textareaValue.length, coreMatchIndex + corePattern.length + contextAfter.length);
                            const contextText = textareaValue.substring(contextStart, contextEnd);
                            
                            // 策略1：直接匹配（规范化换行符）
                            const normalizedContextText = normalizeLineBreaks(contextText);
                            const normalizedFullPattern = normalizeLineBreaks(fullContextPattern);
                            if (normalizedContextText.includes(normalizedFullPattern)) {
                              bestMatch = coreMatchIndex;
                              bestPosition = coreMatchIndex + coreBefore.length + 1; // +1 表示在目标字符之后
                              usedStrategy = `规范化${contextLen}字符上下文`;
                              break;
                            }
                            
                            // 策略2：移除markdown后匹配
                            const cleanedContextText = normalizeLineBreaks(removeMarkdown(contextText));
                            const cleanedFullPattern = normalizeLineBreaks(removeMarkdown(fullContextPattern));
                            if (cleanedContextText.includes(cleanedFullPattern)) {
                              bestMatch = coreMatchIndex;
                              bestPosition = coreMatchIndex + coreBefore.length + 1;
                              usedStrategy = `清理markdown+规范化${contextLen}字符上下文`;
                              break;
                            }
                            
                            // 策略3：移除标点符号后匹配（宽松匹配）
                            const noPunctContextText = removePunctuation(normalizeLineBreaks(contextText));
                            const noPunctFullPattern = removePunctuation(normalizeLineBreaks(fullContextPattern));
                            if (noPunctContextText.includes(noPunctFullPattern)) {
                              bestMatch = coreMatchIndex;
                              bestPosition = coreMatchIndex + coreBefore.length + 1;
                              usedStrategy = `移除标点+规范化${contextLen}字符上下文`;
                              break;
                            }
                          }
                          
                          if (bestMatch !== null) {
                            break; // 找到最佳匹配，停止搜索
                          }
                        }
                        
                        // 如果找到了最佳匹配
                        if (bestMatch !== null && bestPosition !== -1) {
                          console.log(`[editContentInline] 🔍 ${usedStrategy}找到最佳匹配，核心位置: ${bestMatch}, 精确位置: ${bestPosition}`);
                          position = bestPosition;
                        } else if (coreMatches.length === 1) {
                          // 只有一个核心匹配，直接使用
                          const newPosition = coreMatches[0].index + coreBefore.length + 1;
                          console.log(`[editContentInline] 🔍 仅有一个核心匹配，使用该位置: ${newPosition}`);
                          position = newPosition;
                        } else {
                          console.log(`[editContentInline] ⚠️ 找到多个核心匹配但无法确定最佳位置，使用第一个`);
                          position = coreMatches[0].index + coreBefore.length + 1;
                        }
                      } else {
                        console.log(`[editContentInline] ⚠️ 未找到核心匹配，使用原始位置: ${position}`);
                        console.log(`[editContentInline] ⚠️ 核心模式: "${corePattern}"`);
                      }
                    }
                    
                    console.log(`[editContentInline] 最终设置光标位置: ${position}, 总长度: ${textareaEl.value.length}`);
                    
                    // 🔥 验证位置对应的字符
                    const charAtPos = textareaEl.value[position];
                    const contextStart = Math.max(0, position - 30);
                    const contextEnd = Math.min(textareaEl.value.length, position + 30);
                    const context = textareaEl.value.substring(contextStart, contextEnd);
                    console.log(`[editContentInline] textarea中位置${position}的字符: "${charAtPos}"`);
                    console.log(`[editContentInline] textarea位置上下文: "${context.replace(/\n/g, '\\n')}"`);
                    console.log(`[editContentInline] textarea位置标记: "${context.substring(0, position - contextStart)}[${charAtPos}]${context.substring(position - contextStart + 1)}"`);
                    
                    // 先设置光标位置并聚焦
                    textareaEl.setSelectionRange(position, position);
                    textareaEl.focus();
                    
                    // 等待浏览器渲染完成，然后滚动到光标位置
                    requestAnimationFrame(() => {
                      requestAnimationFrame(() => {
                        // 再次确保光标位置正确
                        textareaEl.setSelectionRange(position, position);
                        
                        // 再等待一些时间，确保textarea的value已经完全更新和渲染
                        setTimeout(() => {
                          // 确保光标位置正确
                          textareaEl.setSelectionRange(position, position);
                          
                          // 获取样式信息
                          const textareaStyle = window.getComputedStyle(textareaEl);
                          const lineHeight = parseFloat(textareaStyle.lineHeight) || 20;
                          const textareaHeight = textareaEl.clientHeight;
                          const textareaScrollHeight = textareaEl.scrollHeight; // 内容总高度
                          
                          // 计算可见行数
                          const visibleLines = Math.floor(textareaHeight / lineHeight);
                          console.log(`[editContentInline] 行高: ${lineHeight}, textarea高度: ${textareaHeight}, 内容总高度: ${textareaScrollHeight}, 可见行数: ${visibleLines}`);
                          
                          // 使用隐藏div测量实际渲染的行号（考虑自动换行）
                          const fullText = textareaEl.value;
                          const textBeforeCursor = fullText.substring(0, position);
                          
                          // 创建一个隐藏的div来测量文本的实际渲染高度
                          const measureDiv = document.createElement('div');
                          measureDiv.style.position = 'absolute';
                          measureDiv.style.visibility = 'hidden';
                          measureDiv.style.whiteSpace = 'pre-wrap'; // 保持换行和空格
                          measureDiv.style.wordWrap = 'break-word'; // 自动换行
                          measureDiv.style.width = `${textareaEl.clientWidth}px`; // 与textarea相同的宽度
                          measureDiv.style.padding = textareaStyle.padding;
                          measureDiv.style.border = textareaStyle.border;
                          measureDiv.style.font = textareaStyle.font;
                          measureDiv.style.fontSize = textareaStyle.fontSize;
                          measureDiv.style.fontFamily = textareaStyle.fontFamily;
                          measureDiv.style.lineHeight = textareaStyle.lineHeight;
                          measureDiv.style.boxSizing = textareaStyle.boxSizing;
                          measureDiv.textContent = textBeforeCursor;
                          
                          document.body.appendChild(measureDiv);
                          const textBeforeCursorHeight = measureDiv.offsetHeight;
                          
                          // 计算光标所在的实际行号（考虑自动换行）
                          const linesBeforeCursor = Math.max(0, Math.floor(textBeforeCursorHeight / lineHeight));
                          
                          // 测量全文高度以计算总行数
                          measureDiv.textContent = fullText;
                          const fullTextHeight = measureDiv.offsetHeight;
                          const totalLines = Math.max(1, Math.ceil(fullTextHeight / lineHeight));
                          
                          // 清理临时元素
                          document.body.removeChild(measureDiv);
                          
                          console.log(`[editContentInline] 字符位置: ${position}, 总长度: ${fullText.length}`);
                          console.log(`[editContentInline] 光标所在行号（考虑自动换行）: ${linesBeforeCursor}, 总行数: ${totalLines}`);
                          console.log(`[editContentInline] 光标前文本高度: ${textBeforeCursorHeight}px, 全文高度: ${fullTextHeight}px`);
                          
                          // 计算光标所在行的像素位置（从文本顶部开始）
                          const cursorLinePixelPos = linesBeforeCursor * lineHeight;
                          
                          // 计算目标滚动位置：让光标所在行在视口中间
                          const centerOffset = Math.floor(visibleLines / 2) * lineHeight; // 视口中间位置的像素偏移
                          let targetScrollTop = cursorLinePixelPos - centerOffset;
                          
                          // 限制滚动范围：不能小于0，不能超过最大滚动位置
                          // 使用scrollHeight，因为它是实际渲染高度
                          const maxScrollTop = Math.max(0, textareaScrollHeight - textareaHeight);
                          targetScrollTop = Math.max(0, Math.min(targetScrollTop, maxScrollTop));
                          
                          console.log(`[editContentInline] 光标行像素位置: ${cursorLinePixelPos}, 中心偏移: ${centerOffset}`);
                          console.log(`[editContentInline] 最大scrollTop: ${maxScrollTop}, 目标scrollTop: ${targetScrollTop}`);
                          
                          // 设置滚动位置
                          textareaEl.scrollTop = targetScrollTop;
                          
                          // 再次确保光标位置正确
                          textareaEl.setSelectionRange(position, position);
                          
                          console.log(`[editContentInline] 滚动完成，当前scrollTop: ${textareaEl.scrollTop}, selectionStart: ${textareaEl.selectionStart}, selectionEnd: ${textareaEl.selectionEnd}`);
                          console.log(`[editContentInline] 滚动后的可见行范围: ${Math.floor(textareaEl.scrollTop / lineHeight)} - ${Math.floor(textareaEl.scrollTop / lineHeight) + visibleLines}`);
                        }, 300); // 额外延迟300ms，确保textarea完全渲染
                      });
                    });
                  } else {
                    console.log(`[editContentInline] clickedCharPosition为0，跳过光标位置设置`);
                  }
                  
                  // 清除记录的字符位置（延迟清除，确保设置完成）
                  setTimeout(() => {
                    this.clickedCharPosition = 0;
                  }, 100);
                }, 500);
              }
            }
          });
        }
        
        // 重置计时器和鼠标位置
        this.clickTimer = null;
        this.mouseDownPos = null;
        this.mouseUpPos = null;
      }, 250); // 250毫秒的延迟，这是区分单击和双击的时间窗口
    },

    // 保存内联编辑内容
    saveInlineEdit() {
      let needToSave = false;
      
      // 检查是否有内容变更
      if (this.isEditingTitle && this.tempTitle !== this.cardInfo.contentTitle) {
        this.cardInfo.contentTitle = this.tempTitle;
        needToSave = true;
      }
      
      if (this.isEditingKeywords && this.tempKeywords !== this.cardInfo.keyWords) {
        this.cardInfo.keyWords = this.tempKeywords;
        needToSave = true;
      }
      
      if (this.isEditingContent && this.tempContent !== this.cardInfo.content) {
        // 🔥 使用diff库对比原始内容和新内容，找出新增部分并添加***标记
        const originalContent = this._originalContentBeforeEdit || this.cardInfo.content;
        let newContent = this.tempContent;
        
        // 使用diff算法找出新增的内容
        const markedContent = this._markUserEditsWithDiff(originalContent, newContent);
        this.cardInfo.content = markedContent;
        needToSave = true;
        
        // 清除临时引用
        this._originalContentBeforeEdit = null;
      }
      
      // 重置编辑状态
      this.isEditingTitle = false;
      this.isEditingKeywords = false;
      this.isEditingContent = false;

      // 🔥 恢复进入编辑前的卡片外层滚动位置
      this.$nextTick(() => {
        if (this.$refs.cardDialog && this._cardScrollTopBeforeEdit !== undefined) {
          this.$refs.cardDialog.scrollTop = this._cardScrollTopBeforeEdit;
          console.log(`[saveInlineEdit] 恢复卡片滚动位置: ${this._cardScrollTopBeforeEdit}`);
          this._cardScrollTopBeforeEdit = undefined;
        }
      });
      
      // 如果有内容变更，执行保存
      if (needToSave) {
        // this.shouldBeFront = true;   // 修改卡片内容暂时调整为不前移
        
        let formData = new FormData();
        formData.append('cid', this.cid);
        formData.append('newContent', this.cardInfo.content);
        formData.append('newContentTitle', this.cardInfo.contentTitle);
        formData.append('newKeyWords', this.cardInfo.keyWords);
        
        chageContent(formData).then(response => {
          if (response.error_num === 0) {
            this.$message.success('保存成功');
            this.$emit('updateOrDeleteCard');
          } else {
            alert("error!");
          }
        }).catch(error => {
          alert("error!2");
          console.log('error', error.message);
        });
      }
    },

    // 取消内联编辑
    cancelInlineEdit() {
      this.isEditingTitle = false;
      this.isEditingKeywords = false;
      this.isEditingContent = false;
      
      // 🔥 恢复进入编辑前的卡片外层滚动位置
      this.$nextTick(() => {
        if (this.$refs.cardDialog && this._cardScrollTopBeforeEdit !== undefined) {
          this.$refs.cardDialog.scrollTop = this._cardScrollTopBeforeEdit;
          console.log(`[cancelInlineEdit] 恢复卡片滚动位置: ${this._cardScrollTopBeforeEdit}`);
          this._cardScrollTopBeforeEdit = undefined;
        }
      });

      // 🔥 清除临时引用
      this._originalContentBeforeEdit = null;
    },

    // 🔥 使用diff算法标记用户编辑的新增内容（添加***标记）
    // 本子输出目录卡，或 NK2026 梯子图批改场景下 contentTitle 含 S5 的卡片
    _isNk2026S5ContentTitleCard() {
      const scene = (this.sceneName || '').trim();
      const isNk2026 = scene.includes('NK2026梯子图') || scene.includes('梯子图·群组公能');
      const title = (this.cardInfo.contentTitle || '').trim();
      const isS5 = /\bS5\b/i.test(title) || /S\s*5(?:\s*[:：]|(?!\d))/i.test(title);
      return isNk2026 && isS5;
    },

    _markUserEditsWithDiff(originalContent, newContent) {
      if (!originalContent || originalContent === newContent) {
        return newContent;
      }

      const isDirectoryCard = this.cardInfo.title && this.cardInfo.title.includes('本子输出目录');
      const isNk2026S5Card = this._isNk2026S5ContentTitleCard();

      if (!isDirectoryCard && !isNk2026S5Card) {
        console.log(`[保存编辑] 非目录卡且非 NK2026 S5 卡，跳过***标记`);
        return newContent;
      }

      const cardKind = isDirectoryCard ? '本子输出目录卡' : 'NK2026 S5 卡片';
      console.log(`[保存编辑] ${cardKind}，开始diff对比，原始长度: ${originalContent.length}, 新长度: ${newContent.length}`);
      
      let excludeRanges = [];
      if (isDirectoryCard) {
        excludeRanges = this._getExcludeRangesForDirectoryCard(newContent);
        console.log(`[保存编辑] 本子输出目录卡，识别到${excludeRanges.length}个排除区域（目录/标题行）`);
      }

      // 🔥 使用diff库进行专业的diff对比
      // diffChars返回的格式: [{added: boolean, removed: boolean, value: string}, ...]
      const changes = diffChars(originalContent, newContent);
      
      console.log(`[保存编辑] 使用diff库进行对比，找到${changes.length}个差异片段`);
      
      // 处理diff结果：找出新增的部分（added === true），并添加***标记
      let result = '';
      let newContentPos = 0; // 跟踪在新内容中的当前位置
      
      for (let i = 0; i < changes.length; i++) {
        const part = changes[i];
        
        if (part.added) {
          // 新增的内容
          if (this._isInExcludeRange(newContentPos, part.value.length, excludeRanges)) {
            // 在排除区域内（目录或标题行），不添加***标记
            result += part.value;
            console.log(`[保存编辑] 新增内容在排除区域，跳过标记: "${part.value.substring(0, Math.min(30, part.value.length))}..."`);
          } else {
            // 不在排除区域，添加***标记
            result += `***${part.value}***`;
          }
          newContentPos += part.value.length;
        } else if (!part.removed) {
          // 未修改的部分，直接添加（忽略删除的部分）
          result += part.value;
          newContentPos += part.value.length;
        }
        // 删除的部分（part.removed === true）不添加到结果中，也不更新newContentPos
      }

      console.log(`[保存编辑] diff完成，标记后的长度: ${result.length}`);
      return result;
    },
    
    // 🔥 获取"本子输出目录卡"中需要排除标记的区域（目录区域和标题行）
    _getExcludeRangesForDirectoryCard(content) {
      const ranges = [];
      const lines = content.split('\n');
      let currentPos = 0;
      let inDirectory = false;
      let directoryStartPos = 0;
      let directoryEndPos = -1;
      
      // 检测目录区域（从开头到第一个#/##/###/####标题之前）
      if (lines.length > 0) {
        const firstLine = lines[0].trim();
        // 检查是否以"目录"开头，或者开头包含目录关键词
        if (firstLine.includes('目录') || firstLine.startsWith('目录')) {
          inDirectory = true;
          directoryStartPos = 0;
        }
      }
      
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        const lineStartPos = currentPos;
        const lineEndPos = currentPos + line.length;
        
        // 检测标题行（#/##/###/#### 开头的行）
        const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
        if (headingMatch) {
          // 记录标题行的位置范围
          ranges.push({
            start: lineStartPos,
            end: lineEndPos
          });
          
          // 如果之前是目录区域，目录在这里结束
          if (inDirectory && directoryEndPos === -1) {
            directoryEndPos = lineStartPos;
            ranges.push({
              start: directoryStartPos,
              end: directoryEndPos
            });
            inDirectory = false;
          }
        } else if (inDirectory && directoryEndPos === -1) {
          // 如果还在目录区域，继续记录（目录区域会在遇到第一个标题时结束）
          // 这里不单独记录每一行，而是等遇到标题时一次性记录整个目录区域
        }
        
        currentPos = lineEndPos + 1; // +1 是换行符
      }
      
      // 如果整个内容都是目录（没有标题），记录整个目录区域
      if (inDirectory && directoryEndPos === -1) {
        ranges.push({
          start: directoryStartPos,
          end: content.length
        });
      }
      
      return ranges;
    },
    
    // 🔥 检查位置范围是否在排除区域内
    _isInExcludeRange(startPos, length, excludeRanges) {
      const endPos = startPos + length;
      
      for (const range of excludeRanges) {
        // 检查是否有重叠：新增内容的范围与排除区域有交集
        if (startPos < range.end && endPos > range.start) {
          return true;
        }
      }
      
      return false;
    },

    // 点击非编辑区域时保存
    handleClickOutside(event) {
      if (this.cardHtmlMenuVisible) {
        const m = event.target && event.target.closest && event.target.closest('.card-html-ctx-menu');
        if (!m) this.cardHtmlMenuVisible = false;
      }
      if (this.isEditingTitle || this.isEditingKeywords || this.isEditingContent) {
        // 检查点击目标是否为编辑区域
        const editTitleInput = document.getElementById('edit-title-input');
        const editKeywordsInput = document.getElementById('edit-keywords-input');
        const editContentInput = document.getElementById('edit-content-input');
        
        // 检查是否点击了保存或取消按钮
        const isSaveButton = event.target.textContent === '保存';
        const isCancelButton = event.target.textContent === '取消';
        
        // 如果点击了保存或取消按钮，不做处理（让对应的事件处理程序执行）
        if (isSaveButton || isCancelButton) {
          return;
        }
        
        // 如果点击的不是编辑区域，则保存
        if (!(event.target === editTitleInput || 
              event.target === editKeywordsInput || 
              event.target === editContentInput ||
              event.target.closest('.el-textarea') ||  // 处理textarea内部元素
              event.target.closest('.el-input'))) {    // 处理input内部元素
          this.saveInlineEdit();
        }
      }
    },

    // 全局键盘事件处理
    handleGlobalKeyDown(event) {
      // 确认是Ctrl+K
      if (event.ctrlKey && (event.key === 'k' || event.key === 'K')) {
        console.log('检测到 Ctrl+K 按下');
        // 首先阻止默认行为
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        // 如果确认框已显示，先移除它
        if (this.showConfirmBar) {
          this.removeConfirmBar();
        }
        
        // 查找当前是否在编辑textarea(但这个textareaEl好像无法改变，切换Card进行选取操作，却还是上一个Card的信息，故换了一种方式)
        // let textareaEl = document.querySelector('.contentInput textarea');
        // if (!textareaEl) return;
        // 关键改动：直接使用当前活跃元素，而不是查询
        const activeElement = document.activeElement;

        console.log('检测点1 Ctrl+K 按下', document.activeElement);
        
        // 如果当前文本框有焦点，保存选中的文本
        // if (document.activeElement === textareaEl) {
        //   this.saveSelectedText(textareaEl);
        // }
        if (activeElement && 
            activeElement.tagName === 'TEXTAREA' && 
            (activeElement.className.includes('el-textarea__inner') || 
            activeElement.id === 'edit-content-input')) {
          this.saveSelectedText(activeElement); // 直接传入活跃元素
        }

        console.log('检测点2 Ctrl+K 按下');
        
        return false;  // 返回false以确保事件被完全停止
      } else if (event.key === 'Escape') {
        // 按下ESC键时取消编辑
        if (this.isEditingTitle || this.isEditingKeywords || this.isEditingContent) {
          this.cancelInlineEdit();
          event.preventDefault();
        }
        // 按下ESC键时移除确认框
        if (this.showConfirmBar) {
          this.removeConfirmBar();
          event.preventDefault();
        }
      }
    },
    
    // 提取保存选中文本的逻辑到单独的方法
    saveSelectedText(textarea) {
      console.log('开始saveSelectedText');
      if (!textarea) {
        // textarea = document.querySelector('.contentInput textarea');
        // if (!textarea) return;
        // 如果没有传入textarea，尝试获取当前活跃的textarea
        textarea = document.activeElement;
        if (!textarea || textarea.tagName !== 'TEXTAREA') return;
      }
      
      // 获取选中的文本
      const selectedText = textarea.value.substring(
        textarea.selectionStart, 
        textarea.selectionEnd
      );
      
      // 如果有选中的文本，则保存到chosenContent中
      if (selectedText) {
        // 保存选中的文本和位置信息
        this.currentSelection = {
          start: textarea.selectionStart,
          end: textarea.selectionEnd,
          text: selectedText
        };
        
        // 计算选中文本的位置
        this.calculateSelectionPosition(textarea);
        
        // 显示确认框
        this.showConfirmBar = true;
        this.createConfirmBar();
        
        // 可选：显示提示信息
        if (this.$message) {
          this.$message({
            message: '已选中文本，请您确认',
            type: 'success',
            duration: 2000
          });
        } else {
          // 如果没有$message方法，使用alert
          alert('已保存选中文本');
        }
      } else {
        console.log('没有选中任何文本');
        if (this.$message) {
          this.$message({
            message: '请先选中文本',
            type: 'warning',
            duration: 2000
          });
        }
      }
    },
    // 计算选中文本的位置
    // calculateSelectionPosition(textarea) {
    //   const selectionRange = textarea.value.substring(0, textarea.selectionStart);
    //   const lines = selectionRange.split('\n');
    //   const lineCount = lines.length;
    //   const charPos = lines[lines.length - 1].length;
      
    //   // 计算大致位置（这是一个近似值，可能需要根据实际情况调整）
    //   const lineHeight = parseInt(window.getComputedStyle(textarea).lineHeight) || 20;
    //   const charWidth = 8; // 假设每个字符宽度为8px
      
    //   // 获取textarea的位置
    //   const textareaRect = textarea.getBoundingClientRect();
      
    //   // 计算选中文本的位置
    //   this.selectionPosition = {
    //     left: textareaRect.left + charPos * charWidth,
    //     top: textareaRect.top + (lineCount - 1) * lineHeight + 5 // 向下偏移5px
    //   };
    // },
    // 计算选中文本的位置，确保确认框显示在选中文本附近
    calculateSelectionPosition(textarea) {
      // 直接使用鼠标位置 - 这是最简单可靠的方法
      // 保存当前鼠标位置作为确认框位置
      this.selectionPosition = {
        left: window.lastMouseX || window.event.clientX || 100,
        top: window.lastMouseY || window.event.clientY || 100
      };
      
      // 添加一些偏移，避免遮挡选中的文本
      this.selectionPosition.left += 10;
      this.selectionPosition.top += 10;
      
      // 确保不超出视窗边界
      const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
      
      const confirmBarWidth = 70;  // 根据你的截图估计
      const confirmBarHeight = 40; // 根据你的截图估计
      
      // 边界检查
      if (this.selectionPosition.left + confirmBarWidth > viewportWidth) {
        this.selectionPosition.left = viewportWidth - confirmBarWidth - 10;
      }
      
      if (this.selectionPosition.top + confirmBarHeight > viewportHeight) {
        this.selectionPosition.top = viewportHeight - confirmBarHeight - 10;
      }
    },

    // 跟踪鼠标位置
    trackMousePosition(event) {
      window.lastMouseX = event.clientX;
      window.lastMouseY = event.clientY;
    },
    
    // 创建确认框
    createConfirmBar() {
      // 移除可能存在的旧确认框
      this.removeConfirmBar();
      
      // 创建确认框
      const confirmBar = document.createElement('div');
      confirmBar.id = 'text-selection-confirm-bar';
      confirmBar.style.cssText = `
        position: fixed;
        z-index: 9999;
        left: ${this.selectionPosition.left}px;
        top: ${this.selectionPosition.top + 20}px;
        background-color: #fff;
        border: 1px solid #dcdfe6;
        border-radius: 4px;
        box-shadow: 0 2px 12px 0 rgba(0,0,0,.1);
        display: flex;
        align-items: center;
        padding: 5px 10px;
      `;
      
      // 创建确认按钮（绿色对钩）
      const confirmBtn = document.createElement('button');
      confirmBtn.style.cssText = `
        background-color: #67C23A;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 5px 10px;
        margin-right: 10px;
        cursor: pointer;
      `;
      confirmBtn.innerHTML = '✓';
      // confirmBtn.onclick = this.confirmSelection;
      confirmBtn.onclick = () => {
        this.confirmSelection();  // 箭头函数保持正确的this上下文
      };
      
      // 创建取消按钮（红色叉）
      const cancelBtn = document.createElement('button');
      cancelBtn.style.cssText = `
        background-color: #F56C6C;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 5px 10px;
        cursor: pointer;
      `;
      cancelBtn.innerHTML = '✕';
      // cancelBtn.onclick = this.cancelSelection;
      cancelBtn.onclick = () => {
        this.cancelSelection();  // 同样使用箭头函数
      };
      
      // 添加按钮到确认框
      confirmBar.appendChild(confirmBtn);
      confirmBar.appendChild(cancelBtn);
      
      // 添加确认框到文档
      document.body.appendChild(confirmBar);
    },
    
    // 移除确认框
    removeConfirmBar() {
      const oldConfirmBar = document.getElementById('text-selection-confirm-bar');
      if (oldConfirmBar) {
        oldConfirmBar.remove();
      }
      this.showConfirmBar = false;
    },
    
    // 确认选择
    confirmSelection() {
      // 保存选中的文本到chosenContent
      let selectedText = this.currentSelection.text;
      console.log('%c 文本已保存到chosenContent! ', 'background: #4CAF50; color: white; padding: 4px; border-radius: 3px;');

      // 显示提示
      if (this.$message) {
        this.$message({
          message: '已保存选中文本',
          type: 'success',
          duration: 2000
        });
      }
      
      // 移除确认框
      this.removeConfirmBar();

      // 直接调用原生DOM方法，模拟点击或提交表单
      setTimeout(() => {
        // 第一次操作时没问题；第二次换了一张Card，console显示取消按钮数量:2，没有生效；第三次操作又换回第一次的Card，
        // 生效了，console显示依然为2；第四次再换第三张card操作，console显示数量变成3，没有生效
        // 可能是因为Vue组件被卸载后，DOM元素仍然在页面上存在但已经与Vue实例断开连接
        // const cancelButtons = document.querySelectorAll('.cancelButton');
        // console.log('找到的取消按钮数量:', cancelButtons.length);
        // if (cancelButtons.length > 0) {
        //   cancelButtons[0].click();
        //   console.log('模拟点击了取消按钮');
        // } else {
        //   console.log('未找到取消按钮');
        // }

        // 找到所有取消按钮
        const cancelButtons = document.querySelectorAll('.cancelButton');
        console.log('找到的取消按钮数量:', cancelButtons.length);
        // 尝试找到最近添加的或可见的取消按钮
        let activeButton = null;
        
        // 遍历所有取消按钮找出最可能是活跃的那个
        cancelButtons.forEach((btn, index) => {
          console.log(`取消按钮 ${index} 可见性:`, btn.offsetParent !== null);
          
          // 检查按钮是否可见（有offsetParent）
          if (btn.offsetParent !== null) {
            // 检查按钮是否在视窗内
            const rect = btn.getBoundingClientRect();
            const isInViewport = (
              rect.top >= 0 &&
              rect.left >= 0 &&
              rect.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
              rect.right <= (window.innerWidth || document.documentElement.clientWidth)
            );
            
            console.log(`取消按钮 ${index} 在视窗内:`, isInViewport);
            if (isInViewport) {
              activeButton = btn;
            }
          }
        });
        
        // 如果找到了活跃按钮，点击它
        if (activeButton) {
          console.log('点击找到的活跃取消按钮');
          activeButton.click();
        } else if (cancelButtons.length > 0) {
          // 如果没找到活跃按钮，尝试点击最后一个（假设最后添加的最可能是活跃的）
          console.log('尝试点击最后一个取消按钮');
          cancelButtons[cancelButtons.length - 1].click();
        }
        
        // 找到所有绑定了hideCardDialog的按钮
        const closeButtons = document.querySelectorAll('div.close');
        console.log('找到的关闭按钮数量:', closeButtons.length);
        closeButtons.forEach((btn, index) => {
          console.log(`按钮 ${index}:`, btn.outerHTML);
        });
        if (closeButtons.length > 0) {
          closeButtons[0].click();
          console.log('模拟点击了hideCardDialog按钮');
        } else {
          console.log('未找到hideCardDialog按钮');
        }
        
        // 在延迟后设置选中的文本
        this.chosenContent = selectedText;
        console.log('已选中文本并保存:', this.chosenContent);

        this.$emit('chosenOver', this.chosenContent)
      }, 100);
    },
    
    // 取消选择
    cancelSelection() {
      console.log('已取消选择文本');
      
      // 移除确认框
      this.removeConfirmBar();
    },

    // 展开内容到大窗口
    expandContent(type) {
      let title = '';
      switch(type) {
        case 'main':
          title = '卡片内容';
          break;
        case 'sftReason':
          title = '红蓝深评理由';
          break;
        case 'sftSuggestion':
          title = '红蓝深评改进建议';
          break;
        case 'reason':
          title = '红蓝浅评理由';
          break;
        case 'suggestion':
          title = '红蓝浅评改进建议';
          break;
      }
      
      this.expandedView = {
        visible: true,
        type: type,
        title: title
      };
      
      // 防止背景滚动
      document.body.style.overflow = 'hidden';
    }, 
    // 关闭展开视图
    closeExpandedView() {
      this.expandedView.visible = false;
      document.body.style.overflow = '';
    },

    cardFromCardListToCardInfo() {
      // 一般情况下卡片区域需要整个被刷新时，例如钉卡，删卡，卡片迭代，是不会处于钉卡状态的，目前唯一使用中可能会在打开时触发这里的
      // 就是钉卡后流式出红蓝卡标时，不可全部更新，仅需更新打分、颜色等字段，其他不要变，不然显示会乱掉
      if (this.isCardDialogVisible === false) {
        this.cardInfo.cid = this.card.cid
        this.cardInfo.title = this.card.title
        this.cardInfo.content = this.card.content
        this.cardInfo.status = this.card.status
        this.cardInfo.username = this.card.username
        this.cardInfo.datetime = this.card.datetime
        this.cardInfo.score = this.card.score
        this.cardInfo.color = this.card.color
        this.cardInfo.reason = this.card.reason
        this.cardInfo.scoreSFT = this.card.scoreSFT
        this.cardInfo.colorSFT = this.card.colorSFT
        this.cardInfo.reasonSFT = this.card.reasonSFT
        this.cardInfo.keyWords = this.card.keyWords
        this.cardInfo.contentTitle = this.card.contentTitle
        this.cardInfo.type = this.card.type
        this.cardInfo.preIndex = this.card.preIndex
        this.cardInfo.postIndex = this.card.postIndex
        this.cardInfo.lastContent = this.card.lastContent
        this.cardInfo.writer = this.card.writer
        this.cardInfo.interGrowthT2TA = this.card.interGrowthT2TA
        this.cardInfo.interGrowthTA2GL = this.card.interGrowthTA2GL
        this.cardInfo.interGrowthGL2GM = this.card.interGrowthGL2GM
        this.cardInfo.subareaAndHLAndSugTA2GL = this.card.subareaAndHLAndSugTA2GL

        this.cardInfo.word_count = this.card.word_count

        this.cardInfo.timeParams = this.card.time_params
        if(this.card.history === null)
          this.cardInfo.history = null
        else
          this.cardInfo.history = this.card.history.data
      } else {
        // 钉卡后流式出红蓝卡标时，不可全部更新，仅需更新打分、颜色字段，其他不要变，不然显示会乱掉，因为更过来的card来自cardlist
        // cardlist来自getAllUserCards，这里为了提高性能，先只加载了小字段，大字段都没预加载，是空的
        this.cardInfo.score = this.card.score
        this.cardInfo.color = this.card.color
        // this.cardInfo.reason = this.card.reason
        this.cardInfo.scoreSFT = this.card.scoreSFT
        this.cardInfo.colorSFT = this.card.colorSFT
        // this.cardInfo.reasonSFT = this.card.reasonSFT
        // 关键词后台补全完成后，即使对话框打开也要刷新关键词
        if (this.card.keyWords && String(this.card.keyWords).trim() !== '（理解生成中）') {
          this.cardInfo.keyWords = this.card.keyWords
        }
      }
    },
    ensureKeywordsGeneratingPoll() {
      if (!this.isKeywordsGenerating) {
        this.stopKeywordsGeneratingPoll();
        return;
      }
      if (this._keywordsPollTimer) return;
      this._keywordsPollTries = 0;
      this.pollKeywordsOnce();
      this._keywordsPollTimer = setInterval(() => {
        this.pollKeywordsOnce();
      }, 3000);
    },
    stopKeywordsGeneratingPoll() {
      if (this._keywordsPollTimer) {
        clearInterval(this._keywordsPollTimer);
        this._keywordsPollTimer = null;
      }
      this._keywordsPollTries = 0;
    },
    pollKeywordsOnce() {
      const cid = (this.cardInfo && this.cardInfo.cid) || this.cid;
      if (!cid) return;
      this._keywordsPollTries = (this._keywordsPollTries || 0) + 1;
      if (this._keywordsPollTries > 80) {
        this.stopKeywordsGeneratingPoll();
        return;
      }
      const formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', cid);
      get_card(formData).then(data => {
        if (!data || data.error_num !== 0 || !data.content) return;
        const kw = (data.content.keyWords || '').trim();
        if (kw && kw !== '（理解生成中）') {
          this.cardInfo.keyWords = data.content.keyWords;
          this.stopKeywordsGeneratingPoll();
          this.$emit('keywordsReady', cid);
        }
      }).catch(() => {});
    },
    turnToCardHL() {
      // 🔥 如果是永久卡片，先展开浅评部分
      if (this.isKeywordPermanentCard()) {
        this.isShallowReviewExpanded = true;
        this.$nextTick(() => {
          this.needTurnToCardHL = true;
          this.onCardClick();
        });
      } else {
        this.needTurnToCardHL = true;
        this.onCardClick();
      }
    },
    turnToCardHLSFT() {
      // 🔥 如果是永久卡片，先展开深评部分
      if (this.isKeywordPermanentCard()) {
        this.isDeepReviewExpanded = true;
        this.$nextTick(() => {
          this.needTurnToCardHLSFT = true;
          this.onCardClick();
        });
      } else {
        this.needTurnToCardHLSFT = true;
        this.onCardClick();
      }
    },
    
    // 🔥 切换深评展开/折叠
    toggleDeepReview() {
      this.isDeepReviewExpanded = !this.isDeepReviewExpanded;
    },
    
    // 🔥 切换浅评展开/折叠
    toggleShallowReview() {
      this.isShallowReviewExpanded = !this.isShallowReviewExpanded;
    },

    startFromIndexSFT(index, answer) {
      this.selectedIndex = index;
      this.doubleClick = true;
      this.speakTextSFT();
    },
    speakTextBeginSFT() {
      this.stopSpeech()
      // 从头开始读
      let SFT = this.splitReasonSFT[1] || '正在打分，等待解析改进建议'
      const utterance = new SpeechSynthesisUtterance(SFT);
      this.speech = window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },
    speakTextSFT() {
      this.stopSpeech()
      // 截取从用户双击位置开始的内容
      let SFT = this.splitReasonSFT[1] || '正在打分，等待解析改进建议'
      const content = SFT.slice(this.selectedIndex);
      const utterance = new SpeechSynthesisUtterance(content);
      this.speech = window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },

    doubleClickOver() {
      this.doubleClick = false
    },
    startFromIndex(index, answer) {
      this.selectedIndex = index;
      this.doubleClick = true;
      this.speakText();
    },
    speakTextBegin() {
      this.stopSpeech()
      // 从头开始读
      if (this.showLastContent === false) {
        const utterance = new SpeechSynthesisUtterance(this.cardInfo.content);
        this.speech = window.speechSynthesis.speak(utterance);
        this.isSpeaking = true;
      } else {
        const utterance = new SpeechSynthesisUtterance(this.cardInfo.lastContent);
        this.speech = window.speechSynthesis.speak(utterance);
        this.isSpeaking = true;
      }
    },
    speakText() {
      this.stopSpeech()
      // 截取从用户双击位置开始的内容
      if (this.showLastContent === false) {
        const content = this.cardInfo.content.slice(this.selectedIndex);
        const utterance = new SpeechSynthesisUtterance(content);
        this.speech = window.speechSynthesis.speak(utterance);
        this.isSpeaking = true;
      } else {
        const content = this.cardInfo.lastContent.slice(this.selectedIndex);
        const utterance = new SpeechSynthesisUtterance(content);
        this.speech = window.speechSynthesis.speak(utterance);
        this.isSpeaking = true;
      }
    },
    stopSpeech() {
      if (this.isSpeaking) {
        window.speechSynthesis.cancel();
        this.isSpeaking = false;
        this.speech = null;
      }
    },
    splitTextAtFirstOccurrence(text, keyword) {
      // 正则表达式匹配 keyword"建议" 前的标点符号、空格或换行符
      // const regex = new RegExp(`[.。,，?？!！;；:： \n]+(?=${keyword})`, 'g');
      const regex = new RegExp(`([.。,，*?？!！;；:： \\s]+|\\\\n)+(?=${keyword})`, 'g');

      // 执行匹配
      const match = regex.exec(text);
      
      if (match) {
        // 找到匹配的位置，分割字符串
        const index = match.index + match[0].length;
        const part1 = text.substring(0, index);
        const part2 = text.substring(index);
        
        return [part1, part2];
      } else {
        // 如果没有找到匹配，返回原始字符串和空字符串
        console.log("未匹配到建议")
        return [text, ''];
      }
    },
    copyContentWithEmptyLines() {
      // 使用Clipboard API复制文本，包括空行
      navigator.clipboard.writeText(this.cardInfo.content).then(() => {
        this.$message.success('内容已复制到剪贴板，包含空行');
      }).catch((err) => {
        this.$message.error("复制失败！");
      });
    },
    replaceTopTip(title) {
      let baseText = "";
      
      // 🔥 首先检查卡片内容是否为文档摘要（单文档【文件摘要】/多增量【综合摘要】/含章节摘要）
      if (this.content && (
        this.content.trim().includes("【文件摘要】")
        || this.content.trim().includes("【综合摘要】")
        || this.content.trim().includes("【章节摘要】")
      )) {
        baseText = "文档摘要"
      } else if (this.content && this.content.trim().includes("A. 权威置信度要求")) {
        baseText = "梳理建议"
      } else if (title.includes("关键词节点图主体性认知推进分析卡")) {
        baseText = "主体分析"
      } else if (title.includes("关键词神经元永久卡")) {
        baseText = "神经元卡"
      } else if (title.includes("本子输出目录卡")) {
        baseText = "输出目录"
      } else if (title.includes("理解")) {
        // 首先检查关键词（优先级最高）
        baseText = "单卡理解"
      } else if (title.includes("批判")) {
        baseText = "单卡批判"
      } else if (title.includes("大纲")) {
        baseText = "单卡大纲"
      } else if (title.includes("扩写")) {
        baseText = "单卡扩写"
      } else if (title.includes("缩写")) {
        baseText = "单卡缩写"
      } else if (title.includes("总结")) {
        baseText = "多卡总结"
      } else if (title.includes("合并")) {
        baseText = "多卡融合"
      } else if (title.includes("建议")) {
        baseText = "多卡建议"
      } else if (title.includes("指导")) {
        baseText = "多卡学习"
      } else {
        // 如果没有匹配到关键词，检查是否是普通问答收藏（通过模型ID判断）
        // 参考replaceTitle的逻辑：使用正则表达式匹配所有数字
        let isNormalQAModel = false;
        
        // 尝试从title中提取模型ID（格式：来自模型XXX）
        const modelIdMatch = title.match(/来自模型(\d+)/);
        if (modelIdMatch) {
          const modelId = modelIdMatch[1];
          
          // 首先检查是否是已知的普通问答模型ID（硬编码的后备列表）
          const knownNormalQAModels = ['1002', '1003', '1004', '1005', '1006', '1007', '1008', '1009', '1010', '2000'];
          isNormalQAModel = knownNormalQAModels.includes(modelId);
          
          // 如果不在硬编码列表中，尝试从缓存中查找模型
          if (!isNormalQAModel) {
            try {
              const cached = localStorage.getItem('modelManagerCache');
              if (cached) {
                const modelsArray = JSON.parse(cached);
                const model = modelsArray.find(m => m.id === modelId || m.id === parseInt(modelId));
                // 如果找到模型，认为它是普通问答收藏（因为只有普通问答模型才会在缓存中）
                if (model && model.name) {
                  isNormalQAModel = true;
                }
              }
            } catch (error) {
              console.warn('从缓存获取模型名称失败:', error);
            }
          }
        } else {
          // 如果没有匹配到"来自模型XXX"格式，使用正则表达式匹配所有数字
          // 参考replaceTitle的逻辑，提取所有数字并检查
          const numberMatches = title.match(/(\d+)/g);
          if (numberMatches && numberMatches.length > 0) {
            for (const match of numberMatches) {
              // 检查是否是已知的普通问答模型ID
              const knownNormalQAModels = ['1002', '1003', '1004', '1005', '1006', '1007', '1008', '1009', '1010', '2000'];
              if (knownNormalQAModels.includes(match)) {
                isNormalQAModel = true;
                break;
              }
              
              // 尝试从缓存中查找
              try {
                const cached = localStorage.getItem('modelManagerCache');
                if (cached) {
                  const modelsArray = JSON.parse(cached);
                  const model = modelsArray.find(m => m.id === match || m.id === parseInt(match));
                  if (model && model.name) {
                    isNormalQAModel = true;
                    break;
                  }
                }
              } catch (error) {
                // 忽略错误，继续检查下一个数字
              }
            }
          }
        }
        
        if (isNormalQAModel) {
          baseText = "问答卡"
        } else {
          baseText = "自定义"
        }
      }
      
      // 🔥 如果有DMT属性，显示D/M/T信息
      if (this.dmtLevel && this.dmtLevel.trim() !== '') {
        const dmtDisplay = this.getDmtLevelDisplay(this.dmtLevel);
        return `${baseText} | ${dmtDisplay}`;
      }
      
      return baseText;
    },
    replaceTitle(title) {
      if (title === "直接生成卡片") {
        if (this.content && (
          this.content.trim().includes("【文件摘要】")
          || this.content.trim().includes("【综合摘要】")
          || this.content.trim().includes("【章节摘要】")
        )) {
          return '文档摘要卡片'
        } else if (this.content && this.content.trim().includes("A. 权威置信度要求")) {
          return '文档梳理卡片'
        } else {
          return title; // 如果匹配不到任何case，返回原字符串
        }
      }

      let localTitle = title;
      return localTitle.replace(/(\d+)/g, match => {
        // 首先尝试从localStorage的modelManagerCache中查找模型名称
        try {
          const cached = localStorage.getItem('modelManagerCache');
          if (cached) {
            const modelsArray = JSON.parse(cached);
            const model = modelsArray.find(m => m.id === match);
            if (model && model.name) {
              return model.name;
            }
          }
        } catch (error) {
          console.warn('从缓存获取模型名称失败:', error);
        }
        
        // 如果缓存中没有找到，使用硬编码的映射作为后备
        switch(match) {
          case '1002':
            return 'GPT4o';
          case '1003':
            return 'mixtral';
          case '1004':
            return 'kimi';
          case '1005':
            return 'llama3.1';
          case '1006':
            return 'Claude3.5';
          case '1007':
            return 'Deepseek';
          case '1008':
            return 'Deepseek';
          case '1009':
            return 'Gemini';
          case '1010':
            return 'Qwq';
          case '2000':
            return '×2融合';
          default:
            return match; // 如果匹配不到任何case，返回原字符串
        }
      });
    },
    backHistoryClicked() {
      // 在外面，还没有获取cardinfo就回溯历史了
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      getCardHistory(formData).then(data => {
        this.cardInfo.history = data["history"]

        this.cardInfo.username = localStorage.getItem('realName');
        this.backHistory(this.cardInfo.history, this.title);
        this.hideHistory();
        this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle)
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    backHistory(history, title) {
      if (!history) {
        this.$message.error("该卡片非对话生成，无历史记录");
        return;
      }
      this.$emit('update-history', history, title);
      setTimeout(() => {
        this.isCardDialogVisible = false;
        this.showHistoryDialog = false;
      }, 5); // 延迟0.005秒执行
    },
    show() {
      this.showTooltip = true;
    },
    hide() {
      this.showTooltip = false;
    },
    showHistory() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      getCardHistory(formData).then(data => {
        this.cardInfo.history = data["history"]

        this.cardInfo.username = localStorage.getItem('realName');
        this.showHistoryDialog = true;
        this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle)
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    hideHistory() {
      this.showHistoryDialog = false;
    },
    showHisTip() {
      this.showHistoryTip = true;
    },
    hideHisTip() {
      this.showHistoryTip = false;
    },
    handleClick() {
      let timeModel = '';
      // 要检查的键
      const keysToCheckGPT4 = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens', 'n'];  
      // const keysToCheckMixtral = ['temperature', 'top_p', 'top_k', 'max_tokens'];  
      const keysToCheckKimi = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens', 'n'];  
      const keysToCheckLlama3 = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];  
      const keysToCheckClaude = ['temperature', 'top_p', 'top_k', 'max_tokens'];  
      const keysToCheckDeepseek = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];
      const keysToCheckGemini = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];
      const keysToCheckQwq = ['temperature', 'top_p', 'frequency_penalty', 'presence_penalty', 'max_tokens'];

      if (this.title.includes("1002")) {
        timeModel = 'GPT4';
      } else if (this.title.includes("1003")) {
        timeModel = 'Mixtral';
      } else if (this.title.includes("1004")) {
        timeModel = 'Kimi';
      } else if (this.title.includes("1005")) {
        timeModel = 'llama3';
      } else if (this.title.includes("1006")) {
        timeModel = 'Claude';
      } else if (this.title.includes("1007")) {
        timeModel = 'Deepseek';
      } else if (this.title.includes("1008")) {
        timeModel = 'Deepseek';
      } else if (this.title.includes("1009")) {
        timeModel = 'Gemini';
      } else if (this.title.includes("1010")) {
        timeModel = 'Qwq';
      } else {
        // 此处还存在问题，因为kimi和gpt4的超参一致、llama3.1和Deepseek的超参一致，仅这样区分不开
        if (keysToCheckGPT4.every(key => key in this.cardInfo.timeParams))
          timeModel = 'GPT4';
        if (keysToCheckKimi.every(key => key in this.cardInfo.timeParams))
          timeModel = 'GPT4';
        if (keysToCheckLlama3.every(key => key in this.cardInfo.timeParams))
          timeModel = 'llama3';
        if (keysToCheckDeepseek.every(key => key in this.cardInfo.timeParams))
          timeModel = 'Deepseek';
        if (keysToCheckClaude.every(key => key in this.cardInfo.timeParams))
          timeModel = 'Claude';
        else
          timeModel = this.activeModel;
      }

      if(this.cardInfo.timeParams != null)
        this.$emit('checkParams', this.cardInfo.timeParams, timeModel);
      else
        this.$message.error('此卡片未保存配置');
      this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle)
    },
    onCheckboxChange() {
      this.checked = !this.checked;
      this.$emit('change', { 'cid': this.cid, 'checked': this.checked });

      if(this.checked === true) {
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', this.cid);
        set_card(formData).then(data => {
          this.$emit('updateOrder');
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
      }
    },
    onCheckboxChangeNoFront() {
      this.checked = !this.checked;
      this.$emit('change', { 'cid': this.cid, 'checked': this.checked });
    },
    // expandContent() { this.isContentExpanded = true; this.isContentTruncated = false; }, collapseContent() { this.isContentExpanded = false; this.isContentTruncated = true; }, handleSetting(command) {
    //   this.$emit('setting', command);
    // },

    // 平滑地在duration时间内完成拖动到底部
    smoothScrollToBottom(element, duration) {
      return new Promise((resolve) => {
        const start = element.scrollTop;
        const change = element.scrollHeight - element.clientHeight - start;
        const startTime = performance.now();

        function animateScroll(currentTime) {
          const timeElapsed = currentTime - startTime;
          const progress = Math.min(timeElapsed / duration, 1); // 计算进度，最大为1
          element.scrollTop = start + change * progress;

          if (timeElapsed < duration) {
            requestAnimationFrame(animateScroll);
          } else {
            resolve(); // 滚动完成后执行 resolve
          }
        }

        requestAnimationFrame(animateScroll);
      });
    },
    smoothScrollToPositionSFT(element, targetPosition, duration) {
      return new Promise((resolve) => {
        const start = element.scrollTop;
        const change = targetPosition - start;
        const startTime = performance.now();

        function animateScroll(currentTime) {
          const timeElapsed = currentTime - startTime;
          const progress = Math.min(timeElapsed / duration, 1); // 计算进度，最大为1
          element.scrollTop = start + change * progress;

          if (timeElapsed < duration) {
            requestAnimationFrame(animateScroll);
          } else {
            resolve(); // 滚动完成后执行 resolve
          }
        }

        requestAnimationFrame(animateScroll);
      });
    },
    changeTextColor() {
      if (this.needTurnToCardHL === true) {
        // 等待 0.8s 后变为红色
        // setTimeout(() => {
        this.textStyle = { color: "red", transition: "color 0.8s" };
        
        // 持续 2.5s 后再变回黑色
        setTimeout(() => {
          this.textStyle = { color: "black", transition: "color 0.8s" };
        }, 2500);
        this.needTurnToCardHL = false
      } else if (this.needTurnToCardHLSFT === true) {
        this.textStyleSFT = { color: "purple", transition: "color 0.8s" };
        
        setTimeout(() => {
          this.textStyleSFT = { color: "black", transition: "color 0.8s" };
        }, 2500);
        this.needTurnToCardHLSFT = false;
      }
    },
    judgeScrollToBottom() {
      setTimeout(() => {
        if (this.needTurnToCardHL === true) {
          this.$nextTick(() => {
            // 获取 card-dialog 元素
            const cardDialog = this.$refs.cardDialog;

            // 检查是否存在垂直滚动条，如果有，将滚动条滚动到最底部
            if (cardDialog.scrollHeight > cardDialog.clientHeight) {
              // cardDialog.scrollTop = cardDialog.scrollHeight;
              // 0.5秒完成拖动
              this.smoothScrollToBottom(cardDialog, 500).then(() => {
                this.changeTextColor(); // 滚动到底部后更改颜色
              });
            } else {
              this.needTurnToCardHL = false;
            }
          });
        } else if (this.needTurnToCardHLSFT === true) {
          this.$nextTick(() => {
            const cardDialog = this.$refs.cardDialog;

            // 获取微调模型红蓝打分元素的 offsetTop
            const scoreElement = this.$refs.scoreSFT;
            const targetPosition = scoreElement.offsetTop;

            // 如果存在滚动条，平滑滚动到目标位置
            if (cardDialog.scrollHeight > cardDialog.clientHeight) {
              // 0.5秒内平滑滚动到微调模型红蓝打分的位置
              this.smoothScrollToPositionSFT(cardDialog, targetPosition, 500).then(() => {
                this.changeTextColor(); // 滚动到底部后更改颜色
              });
            } else {
              this.needTurnToCardHLSFT = false;
            }
          });
        }
      }, 200);
    },

    catchCidIndex() {
      if(this.title.includes("1002") || this.title.includes("1003") || this.title.includes("1004") || this.title.includes("1005") || this.title.includes("1006") || this.title.includes("1007") || this.title.includes("1008") || this.title.includes("1009") || this.title.includes("1010") || this.title.includes("2000")){
        this.isCardDialogVisible = true;
        // this.judgeScrollToBottom()
      } else if(this.title.includes("理解") || this.title.includes("批判") || this.title.includes("大纲") || this.title.includes("扩写") || this.title.includes("缩写") || (this.title.includes("自定义")&&!this.title.includes(","))){
        const regex = /(\d+)(理解|批判|大纲|扩写|缩写|自定义)/;
        const match = this.title.match(regex);
        let numberBefore;
        if (match) {
          numberBefore = match[1]; // 第一个捕获组是要找的数字
          console.log("捕获卡片cid" ,numberBefore);
        } else {
          console.log("没有找到匹配的数字");
        }
        this.$emit('hint', numberBefore, this.groupIndex);
        this.$message.success('闪烁的为单卡迭代来源卡片，它将和当前卡片一同被移动至最前！');
        setTimeout(() => {
          this.isCardDialogVisible = true;
          // this.judgeScrollToBottom()
        }, 2000); // 2秒闪烁后，再展示卡片内容
      } else if(this.title.includes("总结") || this.title.includes("合并") || this.title.includes("建议") || this.title.includes("指导") || (this.title.includes("自定义")&&this.title.includes(","))){
        const regex = /((\d+,)*\d+)(总结|合并|建议|指导|自定义)/;
        const match = this.title.match(regex);
        let numbers;
        if (match) {
          const numberBefore = match[1];
          numbers = numberBefore.split(',').map(num => parseInt(num.trim(), 10));
          console.log("捕获的卡片cid数组:", numbers);
        } else {
          console.log("没有找到匹配的数字");
        }
        this.$emit('MultiHint', numbers, this.groupIndex);
        this.$message.success('闪烁的为多卡迭代来源卡片，它们将和当前卡片一同被移动至最前！');
        setTimeout(() => {
          this.isCardDialogVisible = true;
          // this.judgeScrollToBottom()
        }, 2000); // 2秒闪烁后，再展示卡片内容
      } else {
        this.isCardDialogVisible = true;
        // this.judgeScrollToBottom()
      }
    },
    onCardClick() {
      this.catchCidIndex()

      // this.isCardDialogVisible = true;
      this.getSingleCard()
    },
    
    // 通过CID打开卡片
    openCardByCid(cid) {
      this.$emit('openCardByCid', cid);
    },
    openCardHtmlMenu(e) {
      if (!e || typeof e.preventDefault === 'function') e.preventDefault();
      this.cardHtmlMenuX = (e && e.clientX) || 0;
      this.cardHtmlMenuY = (e && e.clientY) || 0;
      this.cardHtmlMenuVisible = true;
    },
    refreshCardHtmlFlag() {
      const username = localStorage.getItem('userId');
      if (!username) return;
      card_html_exists({ username, cid: this.cid })
        .then((res) => {
          const d = res.data || res;
          this.cardHasHtmlFile = !!(d && d.error_num === 0 && d.has_html);
          this.cardHasHtmlLastVersion = !!(d && d.error_num === 0 && d.has_last_version);
        })
        .catch(() => {
          this.cardHasHtmlFile = false;
          this.cardHasHtmlLastVersion = false;
        });
    },
    _buildCardHtmlRequestBody() {
      return {
        username: localStorage.getItem('userId'),
        cid: this.cid,
        filenamelist: Array.isArray(this.fileNameList) ? this.fileNameList : [],
        leftSelectList: Array.isArray(this.leftSelectList) ? this.leftSelectList : [],
        rightSelectList: Array.isArray(this.rightSelectList) ? this.rightSelectList : [],
        choosedCardIdList: Array.isArray(this.choosedCardIdList) ? this.choosedCardIdList : [],
      };
    },
    async onMenuCopyCardImage() {
      this.cardHtmlMenuVisible = false;
      if (!this.imgClicked || this.imgClicked === '') {
        this.$message.warning('当前无卡片图片可复制');
        return;
      }
      const mime = this.imgType || 'image/png';
      const dataUrl = `data:${mime};base64,${this.imgClicked}`;
      try {
        const res = await fetch(dataUrl);
        const blob = await res.blob();
        if (navigator.clipboard && window.ClipboardItem) {
          await navigator.clipboard.write([new ClipboardItem({ [blob.type || mime]: blob })]);
          this.$message.success('已复制卡片图片');
        } else {
          this.$message.warning('当前浏览器不支持复制图片到剪贴板');
        }
      } catch (e) {
        this.$message.error('复制图片失败：' + (e.message || e));
      }
    },
    async onMenuGenerateHtml() {
      this.cardHtmlMenuVisible = false;
      if (this.isCardHtmlBusy) return;
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.cardHtmlBusy = true;
      try {
        const res = await card_html_generate(this._buildCardHtmlRequestBody());
        const d = res.data || res;
        if (d.error_num !== 0) {
          this.$message.error(d.msg || '生成 HTML 失败');
          return;
        }
        this.$message.success(this.cardHasHtmlFile ? 'HTML 已重新生成并保存' : 'HTML 已生成并保存');
        this.cardHasHtmlFile = true;
        if (d.backed_up) this.cardHasHtmlLastVersion = true;
        this.cardMediaViewMode = 'html';
        this.cardHtmlIframeKey += 1;
      } catch (err) {
        this.$message.error('请求失败：' + (err.message || err));
      } finally {
        this.cardHtmlBusy = false;
      }
    },
    async onMenuIterateHtml() {
      this.cardHtmlMenuVisible = false;
      if (this.isCardHtmlBusy) return;
      if (!this.cardHasHtmlFile) {
        this.$message.warning('请先生成 HTML 版');
        return;
      }
      try {
        await this.$confirm(
          '迭代会覆盖现有的 HTML 内容（覆盖前会自动留存上一版，可通过「回退上一版」恢复）。是否继续？',
          '迭代现有html版',
          { confirmButtonText: '继续迭代', cancelButtonText: '取消', type: 'warning' }
        );
      } catch {
        return;
      }
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.cardHtmlBusy = true;
      try {
        const res = await card_html_iterate(this._buildCardHtmlRequestBody());
        const d = res.data || res;
        if (d.error_num !== 0) {
          this.$message.error(d.msg || '迭代 HTML 失败');
          return;
        }
        this.$message.success('HTML 已迭代并保存');
        this.cardHasHtmlFile = true;
        this.cardHasHtmlLastVersion = true;
        this.cardMediaViewMode = 'html';
        this.cardHtmlIframeKey += 1;
      } catch (err) {
        this.$message.error('请求失败：' + (err.message || err));
      } finally {
        this.cardHtmlBusy = false;
      }
    },
    async onMenuRevertHtml() {
      this.cardHtmlMenuVisible = false;
      if (!this.cardHasHtmlLastVersion) {
        this.$message.warning('无可回退的上一版');
        return;
      }
      try {
        await this.$confirm(
          '将用 lastVersion 中留存的上一版 HTML 覆盖当前内容，是否继续？',
          '回退上一版',
          { confirmButtonText: '确认回退', cancelButtonText: '取消', type: 'warning' }
        );
      } catch {
        return;
      }
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.cardHtmlBusy = true;
      try {
        const res = await card_html_revert({ username, cid: this.cid });
        const d = res.data || res;
        if (d.error_num !== 0) {
          this.$message.error(d.msg || '回退失败');
          return;
        }
        this.$message.success('已回退到上一版 HTML');
        this.cardHasHtmlFile = true;
        this.cardMediaViewMode = 'html';
        this.cardHtmlIframeKey += 1;
      } catch (err) {
        this.$message.error('请求失败：' + (err.message || err));
      } finally {
        this.cardHtmlBusy = false;
      }
    },
    async onMenuShowHtml() {
      this.cardHtmlMenuVisible = false;
      if (!this.cardHasHtmlFile) {
        this.$message.warning('请先生成 HTML 版');
        return;
      }
      this.cardMediaViewMode = 'html';
      this.cardHtmlIframeKey += 1;
    },
    async setCardMediaViewMode(mode) {
      this.cardMediaViewMode = mode;
      if (mode === 'html_source') {
        await this._loadCardHtmlSource();
      }
      if (mode === 'html') {
        this.cardHtmlIframeKey += 1;
      }
    },
    async _loadCardHtmlSource() {
      const username = localStorage.getItem('userId');
      if (!username) return;
      try {
        const res = await card_html_raw({ username, cid: this.cid });
        const d = res.data || res;
        if (d.error_num === 0 && d.html) {
          this.cardHtmlSourceText = d.html;
        } else {
          this.cardHtmlSourceText = '<!-- ' + (d.msg || '读取失败') + ' -->';
        }
      } catch (e) {
        this.cardHtmlSourceText = '<!-- ' + (e.message || e) + ' -->';
      }
    },
    async copyCardHtml() {
      try {
        await this._loadCardHtmlSource();
        const t = this.cardHtmlSourceText || '';
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(t);
          this.$message.success('已复制 HTML 到剪贴板');
        } else {
          this.$message.warning('浏览器不支持剪贴板 API');
        }
      } catch (e) {
        this.$message.error('复制失败');
      }
    },
    async downloadCardHtml() {
      try {
        await this._loadCardHtmlSource();
        const blob = new Blob([this.cardHtmlSourceText || ''], { type: 'text/html;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `card_${this.cid}.html`;
        a.click();
        URL.revokeObjectURL(a.href);
        this.$message.success('已开始下载');
      } catch (e) {
        this.$message.error('下载失败');
      }
    },
    getActiveCardContent() {
      const useLast = this.showLastContent || this.showLastContentNormal;
      if (useLast) {
        return this.cardInfo.lastContent || this.cardInfo.content || '';
      }
      return this.cardInfo.content || '';
    },
    openCardTextInNewTab() {
      const title = (this.cardInfo.contentTitle || this.cardInfo.title || '卡片内容').trim();
      const content = this.getActiveCardContent();
      if (!content || !String(content).trim()) {
        this.$message.warning('当前卡片暂无文字内容可打开');
        return;
      }
      const key = `card_text_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
      let imageUrl = '';
      if (this.imgClicked && this.imgClicked !== '') {
        try {
          const mime = this.imgType || 'image/png';
          const binary = atob(this.imgClicked);
          const bytes = new Uint8Array(binary.length);
          for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          imageUrl = URL.createObjectURL(new Blob([bytes], { type: mime }));
        } catch (e) {
          console.warn('[openCardTextInNewTab] build image blob failed', e);
        }
      }
      try {
        sessionStorage.setItem(key, JSON.stringify({ title, content, imageUrl }));
      } catch (e) {
        this.$message.error('内容过大，无法在新窗口打开');
        console.error('[openCardTextInNewTab] sessionStorage failed', e);
        if (imageUrl) {
          try { URL.revokeObjectURL(imageUrl); } catch (_) { /* ignore */ }
        }
        return;
      }
      const readerUrl = `${window.location.origin}/card-text-reader?key=${encodeURIComponent(key)}`;
      const opened = window.open(readerUrl, '_blank');
      if (!opened) {
        sessionStorage.removeItem(key);
        if (imageUrl) {
          try { URL.revokeObjectURL(imageUrl); } catch (_) { /* ignore */ }
        }
        this.$message.warning('无法打开新窗口，请检查浏览器是否拦截了弹出窗口');
      }
    },
    /** 从批改结果卡 marker 解析 analysis_id / run_id */
    parseGradingCardMarker() {
      const raw = String(
        (this.cardInfo && this.cardInfo.content) || this.content || ''
      )
      const m = raw.match(/<!--\s*nkcn_grading_card:批改·[^|]*\|([^|>]+)\|([^>]+)-->/i)
      if (!m) return { analysisId: '', runId: '' }
      return { analysisId: String(m[1] || '').trim(), runId: String(m[2] || '').trim() }
    },
    /** 收集本卡 HTML iframe（含打开弹层；兼容多根节点 $el 只指向首节点） */
    _collectCardHtmlFrames() {
      const frames = []
      const seen = new Set()
      const pushAll = (root) => {
        if (!root || !root.querySelectorAll) return
        root.querySelectorAll('iframe.card-html-iframe').forEach((frame) => {
          if (seen.has(frame)) return
          seen.add(frame)
          frames.push(frame)
        })
      }
      pushAll(this.$refs.cardDialog)
      pushAll(this.$el)
      try {
        const cid = String(this.cid || '')
        if (cid) {
          document.querySelectorAll('iframe.card-html-iframe').forEach((frame) => {
            const src = String(frame.getAttribute('src') || '')
            if (src.includes(`cid=${cid}`) || src.includes(`cid=${encodeURIComponent(cid)}`)) {
              if (!seen.has(frame)) {
                seen.add(frame)
                frames.push(frame)
              }
            }
          })
        }
      } catch (e) { /* ignore */ }
      return frames
    },
    _isMessageFromOwnCardHtml(event) {
      const frames = this._collectCardHtmlFrames()
      if (frames.some((frame) => frame.contentWindow === event.source)) return true
      // 兜底：解释精要卡按 analysisId 认领（避免多根节点漏检 iframe）
      const data = event && event.data
      if (!data || !this.isGradingExcerptCard) return false
      const meta = this.parseGradingCardMarker()
      const aid = String(data.analysisId || data.analysis_id || '').trim()
      return !!(meta.analysisId && aid && aid === meta.analysisId)
    },
    /** 与 iframe 预览同一接口，在系统浏览器新标签页全页打开（含脚本交互） */
    openCardHtmlInNewTab() {
      const url = this.cardHtmlViewUrl;
      const w = window.open(url, '_blank', 'noopener,noreferrer');
      if (!w) {
        this.$message.warning('无法打开新窗口，请检查浏览器是否拦截了弹出窗口');
      }
    },
    /** 双击卡片图片：新窗口打开，支持滚轮以鼠标为焦点缩放 + 拖动平移 */
    openCardImageFullscreen() {
      if (!this.imgClicked || this.imgClicked === '') return;
      const dataUrl = 'data:' + (this.imgType || 'image/png') + ';base64,' + this.imgClicked;
      const w = window.open('', '_blank');
      if (!w) return;
      var script = "(function(){var s=1,tx=0,ty=0,min=0.2,max=5,step=0.15,el=document.getElementById('fsImg'),wrap=document.getElementById('fsWrap'),down=null;" +
        "function apply(){el.style.transform='translate('+tx+'px,'+ty+'px) scale('+s+')';}" +
        "wrap.addEventListener('wheel',function(e){e.preventDefault();var px=e.clientX,py=e.clientY,r=el.getBoundingClientRect();" +
        "var sNew=e.deltaY>0?Math.max(min,s-step):Math.min(max,s+step);" +
        "tx=(px-r.left)*(1-sNew/s)+tx*sNew/s;ty=(py-r.top)*(1-sNew/s)+ty*sNew/s;s=sNew;apply();},{passive:false});" +
        "wrap.addEventListener('mousedown',function(e){if(e.button===0)down={startX:e.clientX,startY:e.clientY,startTx:tx,startTy:ty};});" +
        "wrap.addEventListener('mousemove',function(e){if(down!==null){tx=down.startTx+(e.clientX-down.startX);ty=down.startTy+(e.clientY-down.startY);apply();}});" +
        "wrap.addEventListener('mouseup',function(){down=null;});wrap.addEventListener('mouseleave',function(){down=null;});" +
        "apply();})();";
      w.document.write(
        '<!DOCTYPE html><html><head><meta charset="utf-8"><title>卡片图片</title>' +
        '<style>body{margin:0;background:#1a1a1a;display:flex;align-items:center;justify-content:center;min-height:100vh;overflow:hidden;cursor:grab;}' +
        'body:active{cursor:grabbing;}#fsWrap{position:relative;display:flex;align-items:center;justify-content:center;width:100%;height:100%;overflow:hidden;}' +
        '#fsImg{max-width:100vw;max-height:100vh;width:auto;height:auto;object-fit:contain;transform-origin:0 0;transition:none;user-select:none;pointer-events:none;}</style></head>' +
        '<body><div id="fsWrap"><img id="fsImg" src="' + dataUrl.replace(/"/g, '&quot;') + '"/></div><script>' + script + '<\/script></body></html>'
      );
      w.document.close();
    },

    // 单张卡片生图：先弹窗选模型与长宽比，再请求后端
    openCardImageGenDialog() {
      if (this.isCardImageGenerating) return;
      this.cardImageGenDialogVisible = true;
    },
    async confirmCardImageGen() {
      this.cardImageGenDialogVisible = false;
      await this.submitSingleCardImage();
    },
    async submitSingleCardImage() {
      if (this.isCardImageGenerating) return;
      const username = localStorage.getItem('userId');
      if (!username) return;
      try {
        const res = await card_generate_single_card_image({
          username,
          cid: this.cid,
          regenerate: !!(this.imgClicked && this.imgClicked !== ''),
          image_quality: this.cardImageQuality || 'normal',
          image_provider: this.cardImageProvider || 'gpt',
          image_aspect_ratio: this.cardImageAspectRatio || '1:1',
        });
        const data = res.data || res;
        if (data.error_num === 1 && data.generating) {
          this.$message.warning('该卡片正在生图中，请稍等');
          return;
        }
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '发起生图失败');
          return;
        }
        if ((data.generating_cids || []).includes(this.cid)) {
          this.$emit('single-card-image-requested', this.cid);
        }
        if (!data.skipped) this.$message.success('已加入生图队列');
      } catch (e) {
        this.$message.error('卡片生图请求失败：' + (e.message || e));
      }
    },
    // 迭代图：先弹窗让用户可选填具体修改要求与参考图，再发起迭代
    requestIterateCardImage() {
      if (this.isCardImageGenerating) return;
      this.iterateImageRevisionInstruction = '';
      this.overlayDmtPromptReady = false;
      this.dmtOverlayRefinePassActive = false;
      this.dmtOverlayDraftText = '';
      this.dmtOverlayRefinedText = '';
      this.dmtOverlayActiveVersion = 'draft';
      this.iterateImageReferenceFile = null;
      this.iterateImageReferenceDataUrl = '';
      this.iterateImageQuality = this.cardImageQuality || 'normal';
      this.iterateImageProvider = this.cardImageProvider || 'gpt';
      this.overlayIterateInstruction = '';
      this.overlayIterateReferenceDataUrl = '';
      this.overlayIterateEditRegionNorm = null;
      this.restoreOverlaySession();
      this._teardownOverlayTestDrag();
      this._teardownOverlayIterateRegionDrag();
      this.clearIterateEditRegion();
      this.iterateCropIncludeFullImage = true;
      this._teardownIterateRegionDrag();
      this.iterateImageDialogVisible = true;
      if (this.iterateOverlayTestMode) {
        this.syncOverlayHistoryFromServer();
      }
    },
    _iterateNormFromEvent(e, imgEl) {
      const r = imgEl.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) return { x: 0, y: 0 };
      let x = (e.clientX - r.left) / r.width;
      let y = (e.clientY - r.top) / r.height;
      x = Math.max(0, Math.min(1, x));
      y = Math.max(0, Math.min(1, y));
      return { x, y };
    },
    _teardownIterateRegionDrag() {
      document.removeEventListener('mousemove', this._boundIterateRegionMove);
      document.removeEventListener('mouseup', this._boundIterateRegionUp);
      this.iterateRegionDragging = false;
      this.iterateRegionDragStart = null;
      this.iterateRegionDragCurrent = null;
    },
    onIterateRegionMouseDown(e) {
      if (e.button !== 0) return;
      const img = this.$refs.iterateRegionImg;
      if (!img || !this.iterateImageDialogVisible) return;
      const p = this._iterateNormFromEvent(e, img);
      this.iterateRegionDragging = true;
      this.iterateRegionDragStart = p;
      this.iterateRegionDragCurrent = p;
      document.addEventListener('mousemove', this._boundIterateRegionMove);
      document.addEventListener('mouseup', this._boundIterateRegionUp);
    },
    onIterateRegionMouseMove(e) {
      const img = this.$refs.iterateRegionImg;
      if (!img || !this.iterateRegionDragging) return;
      this.iterateRegionDragCurrent = this._iterateNormFromEvent(e, img);
    },
    onIterateRegionMouseUp(e) {
      document.removeEventListener('mousemove', this._boundIterateRegionMove);
      document.removeEventListener('mouseup', this._boundIterateRegionUp);
      const img = this.$refs.iterateRegionImg;
      const start = this.iterateRegionDragStart;
      this.iterateRegionDragging = false;
      this.iterateRegionDragStart = null;
      this.iterateRegionDragCurrent = null;
      if (!img || !start) return;
      const end = this._iterateNormFromEvent(e, img);
      const x = Math.min(start.x, end.x);
      const y = Math.min(start.y, end.y);
      const w = Math.abs(end.x - start.x);
      const h = Math.abs(end.y - start.y);
      const MIN = 0.015;
      if (w < MIN || h < MIN) {
        this.iterateEditRegionNorm = null;
        return;
      }
      this.iterateEditRegionNorm = { x, y, w, h };
    },
    clearIterateEditRegion() {
      this.iterateEditRegionNorm = null;
    },
    triggerIterateReferenceUpload() {
      this.$refs.iterateImageFileInput?.click();
    },
    onIterateReferenceFileChange(e) {
      const file = e.target?.files?.[0];
      if (!file || !file.type.startsWith('image/')) return;
      this.iterateImageReferenceFile = file;
      const reader = new FileReader();
      reader.onload = () => {
        this.iterateImageReferenceDataUrl = reader.result || '';
      };
      reader.readAsDataURL(file);
      e.target.value = '';
    },
    clearIterateReferenceImage() {
      this.iterateImageReferenceFile = null;
      this.iterateImageReferenceDataUrl = '';
      this.$refs.iterateImageFileInput && (this.$refs.iterateImageFileInput.value = '');
    },
    _teardownOverlayTestDrag() {
      document.removeEventListener('mousemove', this._boundOverlayTestMove);
      document.removeEventListener('mouseup', this._boundOverlayTestUp);
      this.overlayTestDrag.active = false;
      this.overlayTestDrag.baseImgEl = null;
    },
    _teardownOverlayIterateRegionDrag() {
      document.removeEventListener('mousemove', this._boundOverlayIterateMove);
      document.removeEventListener('mouseup', this._boundOverlayIterateUp);
      this.overlayIterateRegionDragging = false;
      this.overlayIterateRegionStart = null;
      this.overlayIterateRegionCurrent = null;
    },
    _errText30(msg, fallback = '操作失败') {
      let s = '';
      if (msg === undefined || msg === null || msg === '') s = fallback;
      else s = String(msg);
      return s.length > 30 ? (s.slice(0, 29) + '…') : s;
    },
    _showErr30(msg, fallback = '操作失败') {
      this.$message.error(this._errText30(msg, fallback));
    },
    _isFocusedInInputRef(refName) {
      try {
        const comp = this.$refs[refName];
        const root = comp?.$el || comp;
        if (!root) return false;
        const active = document.activeElement;
        return !!(active && root.contains(active));
      } catch (e) {
        return false;
      }
    },
    async openOverlayManualEraseDialog() {
      if (!this.overlayTestLayerDataUrl) return;
      this._teardownOverlayManualLineDrag();
      this.overlayManualDialogVisible = true;
      // 重置选区状态
      this.overlayManualSelectedRegion = null;
      this.overlayManualSelectionImageData = null;
      this.overlayManualEditMode = 'eraser';
      this.overlayManualEraserShape = 'circle';
      this.overlayManualSelectMode = 'move';
      this.overlayManualCopyClipboard = null;
      this.overlayManualCopyFloating = false;
      await this.$nextTick();
      await this._initOverlayManualCanvas(this.overlayTestLayerDataUrl);
    },
    async _initOverlayManualCanvas(src) {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs || !src) return;
      const img = new Image();
      await new Promise((resolve) => {
        img.onload = resolve;
        img.onerror = resolve;
        img.src = src;
      });
      if (!img.width || !img.height) return;
      cvs.width = img.width;
      cvs.height = img.height;
      this.overlayManualCanvasWidth = img.width;
      this.overlayManualCanvasHeight = img.height;
      // 1.0 倍时按可视区域“完整看见整图”适配
      await this.$nextTick();
      const wrap = this.$refs.overlayManualStageWrap;
      const availW = Math.max(240, (wrap?.clientWidth || 900) - 24);
      const availH = Math.max(180, (wrap?.clientHeight || Math.floor(window.innerHeight * 0.62)) - 24);
      const fitScale = Math.min(availW / img.width, availH / img.height, 1);
      this.overlayManualDisplayBaseWidth = Math.max(1, Math.floor(img.width * fitScale));
      this.overlayManualDisplayBaseHeight = Math.max(1, Math.floor(img.height * fitScale));
      const ctx = cvs.getContext('2d');
      ctx.clearRect(0, 0, img.width, img.height);
      ctx.drawImage(img, 0, 0);
      this.overlayManualUndoStack = [];
      this.overlayManualIsErasing = false;
      this.overlayManualLastPoint = null;
      this._teardownOverlayManualLineDrag();
    },
    _getOverlayManualPoint(e) {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return null;
      const r = cvs.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) return null;
      const x = (e.clientX - r.left) * (cvs.width / r.width);
      const y = (e.clientY - r.top) * (cvs.height / r.height);
      return { x, y };
    },
    _snapshotOverlayManualUndo() {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      const data = cvs.toDataURL('image/png');
      this.overlayManualUndoStack.push(data);
      if (this.overlayManualUndoStack.length > 20) {
        this.overlayManualUndoStack = this.overlayManualUndoStack.slice(this.overlayManualUndoStack.length - 20);
      }
    },
    /** 覆盖层/Gemini 接口用：props.cid 与 card.cid 任一可用即可（避免未透传 props 时缺失） */
    _resolveOverlayManualCid() {
      const tryNum = (v) => {
        if (v === undefined || v === null || v === '') return null;
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      };
      return tryNum(this.cid) ?? tryNum(this.card && this.card.cid);
    },
    _eraseLine(from, to) {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs || !from || !to) return;
      const ctx = cvs.getContext('2d');
      ctx.save();
      ctx.globalCompositeOperation = 'destination-out';
      
      if (this.overlayManualEraserShape === 'circle') {
        // 圆形橡皮擦：笔触连续且边缘平滑
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.lineWidth = this.overlayManualEraserSize;
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        ctx.lineTo(to.x, to.y);
        ctx.stroke();
      } else {
        // 方形橡皮擦：采用“盖章”路径，避免线段擦除导致的缝隙
        const size = Math.max(1, Math.round(this.overlayManualEraserSize));
        const half = size / 2;
        const dx = to.x - from.x;
        const dy = to.y - from.y;
        const dist = Math.hypot(dx, dy);
        const step = Math.max(1, Math.floor(size * 0.28));
        const steps = Math.max(1, Math.ceil(dist / step));
        for (let i = 0; i <= steps; i++) {
          const t = i / steps;
          const x = from.x + dx * t;
          const y = from.y + dy * t;
          ctx.fillRect(Math.round(x - half), Math.round(y - half), size, size);
        }
      }
      
      ctx.restore();
    },
    onOverlayManualMouseDown(e) {
      if (this.overlayManualEditMode === 'eraser') {
        // 橡皮擦模式
        const p = this._getOverlayManualPoint(e);
        if (!p) return;
        this._snapshotOverlayManualUndo();
        this.overlayManualIsErasing = true;
        this.overlayManualLastPoint = p;
        this._eraseLine(p, p);
      } else if (this.overlayManualEditMode === 'select') {
        // 选区编辑模式：在画布上框选区域（仅选择，不立即挖空）
        const p = this._getOverlayManualPoint(e);
        if (!p) return;
        this.clearManualSelection();
        this.overlayManualDragStart = p;
        this.overlayManualIsDragging = true;
        this.overlayManualSelectedRegion = { x: p.x, y: p.y, w: 0, h: 0 };
      } else if (this.overlayManualEditMode === 'line') {
        this._teardownOverlayManualLineDrag();
        const p = this._getOverlayManualPoint(e);
        if (!p) return;
        const cvs = this.$refs.overlayManualCanvas;
        if (!cvs) return;
        this._snapshotOverlayManualUndo();
        const ctx = cvs.getContext('2d');
        this.overlayManualLineBackup = ctx.getImageData(0, 0, cvs.width, cvs.height);
        this.overlayManualLineStart = p;
        this.overlayManualLineDrawing = true;
        document.addEventListener('mousemove', this.onOverlayManualLineMove);
        document.addEventListener('mouseup', this.onOverlayManualLineUp, true);
      } else if (this.overlayManualEditMode === 'rect') {
        this._teardownOverlayManualLineDrag();
        const p = this._getOverlayManualPoint(e);
        if (!p) return;
        const cvs = this.$refs.overlayManualCanvas;
        if (!cvs) return;
        this._snapshotOverlayManualUndo();
        const ctx = cvs.getContext('2d');
        this.overlayManualRectBackup = ctx.getImageData(0, 0, cvs.width, cvs.height);
        this.overlayManualRectStart = p;
        this.overlayManualRectDrawing = true;
        document.addEventListener('mousemove', this.onOverlayManualRectMove);
        document.addEventListener('mouseup', this.onOverlayManualRectUp, true);
      }
    },
    onOverlayManualMouseMove(e) {
      if (this.overlayManualEditMode === 'eraser' && this.overlayManualIsErasing) {
        const p = this._getOverlayManualPoint(e);
        if (!p) return;
        this._eraseLine(this.overlayManualLastPoint, p);
        this.overlayManualLastPoint = p;
      } else if (this.overlayManualEditMode === 'select' && this.overlayManualIsDragging && this.overlayManualDragStart) {
        // 绘制选区框
        const p = this._getOverlayManualPoint(e);
        if (!p) return;
        const x1 = Math.min(this.overlayManualDragStart.x, p.x);
        const y1 = Math.min(this.overlayManualDragStart.y, p.y);
        const x2 = Math.max(this.overlayManualDragStart.x, p.x);
        const y2 = Math.max(this.overlayManualDragStart.y, p.y);
        this.overlayManualSelectedRegion = {
          x: x1,
          y: y1,
          w: x2 - x1,
          h: y2 - y1
        };
      }
    },
    onOverlayManualMouseUp() {
      // 平移/伸缩由 document 级 mouseup 收口，避免与画布 mouseup 竞态导致丢像素
      if (this.overlayManualTransforming) return;
      if (this.overlayManualLineDrawing || this.overlayManualRectDrawing) return;
      if (this.overlayManualEditMode === 'eraser') {
        this.overlayManualIsErasing = false;
        this.overlayManualLastPoint = null;
      } else if (this.overlayManualEditMode === 'select' && this.overlayManualIsDragging) {
        this.overlayManualIsDragging = false;
        this.overlayManualDragStart = null;
        // 只确认选区，不做像素抽取/清空；抽取在平移/伸缩开始时执行
        if (this.overlayManualSelectedRegion && this.overlayManualSelectedRegion.w > 5 && this.overlayManualSelectedRegion.h > 5) {
          this.overlayManualSelectedRegion = {
            x: Math.max(0, Math.floor(this.overlayManualSelectedRegion.x)),
            y: Math.max(0, Math.floor(this.overlayManualSelectedRegion.y)),
            w: Math.max(1, Math.ceil(this.overlayManualSelectedRegion.w)),
            h: Math.max(1, Math.ceil(this.overlayManualSelectedRegion.h)),
          };
        } else {
          this.overlayManualSelectedRegion = null;
        }
      }
    },
    async overlayManualUndo() {
      if (!this.overlayManualUndoStack.length) return;
      const remain = this.overlayManualUndoStack.slice(0, -1);
      const last = this.overlayManualUndoStack.pop();
      await this._initOverlayManualCanvas(last);
      this.overlayManualUndoStack = remain;
    },
    applyOverlayManualClearDarkToTransparent() {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      if (this.overlayManualBleachRunning) return;
      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      this._snapshotOverlayManualUndo();
      this.overlayManualBleachRunning = true;
      try {
        const img = ctx.getImageData(0, 0, cvs.width, cvs.height);
        const d = img.data;
        const w = cvs.width;
        const h = cvs.height;
        const n = w * h;
        const mask = new Uint8Array(n);
        let seed = 0;

        // 与后端一致：纯黑 + 低饱和黑灰，且不透明度较高
        for (let p = 0, i = 0; i < n; i++, p += 4) {
          const r = d[p];
          const g = d[p + 1];
          const b = d[p + 2];
          const a = d[p + 3];
          if (a < 200) continue;
          const mx = Math.max(r, g, b);
          const mn = Math.min(r, g, b);
          const span = mx - mn;
          const pure = r <= 64 && g <= 64 && b <= 64;
          const neutral = mx <= 188 && span <= 24;
          if (pure || neutral) {
            mask[i] = 1;
            seed++;
          }
        }

        if (seed <= 0) {
          this.$message.info('未检测到可清理的黑/灰像素');
          return;
        }

        // 膨胀 1 圈，去掉文字外沿浅灰抗锯齿
        const dilated = mask.slice();
        for (let y = 0; y < h; y++) {
          const row = y * w;
          for (let x = 0; x < w; x++) {
            const idx = row + x;
            if (!mask[idx]) continue;
            for (let dy = -1; dy <= 1; dy++) {
              const ny = y + dy;
              if (ny < 0 || ny >= h) continue;
              const nrow = ny * w;
              for (let dx = -1; dx <= 1; dx++) {
                const nx = x + dx;
                if (nx < 0 || nx >= w) continue;
                dilated[nrow + nx] = 1;
              }
            }
          }
        }

        let changed = 0;
        for (let i = 0, p = 0; i < n; i++, p += 4) {
          if (!dilated[i]) continue;
          if (d[p + 3] !== 0) changed++;
          d[p] = 255;
          d[p + 1] = 255;
          d[p + 2] = 255;
          d[p + 3] = 0;
        }
        ctx.putImageData(img, 0, 0);
        const pct = ((changed / Math.max(1, n)) * 100).toFixed(2);
        this.$message.success(`已将 ${changed}/${n}（${pct}%）黑灰像素转为透明`);
      } finally {
        this.overlayManualBleachRunning = false;
      }
    },
    applyOverlayManualThinLines() {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      if (this.overlayManualThinRunning) return;

      this._snapshotOverlayManualUndo();
      this.overlayManualThinRunning = true;
      try {
        const ctx = cvs.getContext('2d');
        const img = ctx.getImageData(0, 0, cvs.width, cvs.height);
        const d = img.data;
        const t = Math.max(0, Math.min(255, Number(this.overlayManualThinThreshold) || 240));

        // 把“偏浅”的像素抹掉（RGB 置白 + alpha 置 0）
        // 后续合成/预览会把白色当作背景，alpha=0 也能确保这些像素彻底不参与，观感会更明显。
        let changed = 0;
        const total = Math.floor(d.length / 4);
        for (let i = 0; i < d.length; i += 4) {
          const r = d[i];
          const g = d[i + 1];
          const b = d[i + 2];
          const a = d[i + 3];
          const lum = 0.299 * r + 0.587 * g + 0.114 * b;
          if (a !== 0 && lum >= t) {
            d[i] = 255;
            d[i + 1] = 255;
            d[i + 2] = 255;
            d[i + 3] = 0;
            changed++;
          }
        }
        ctx.putImageData(img, 0, 0);
        if (changed > 0) {
          const pct = ((changed / Math.max(1, total)) * 100).toFixed(2);
          this.$message.success(`已抹除 ${changed}/${total}（${pct}%）偏浅像素`);
        } else {
          this.$message.info('本次未找到满足条件的偏浅像素，尝试调低阈值再试');
        }
      } finally {
        this.overlayManualThinRunning = false;
      }
    },
    applyOverlayManualSelectColor() {
      const cvs = this.$refs.overlayManualCanvas;
      const region = this.overlayManualSelectedRegion;
      if (!cvs || !region) return;
      if (this.overlayManualSelectColorRunning) return;

      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      const x = Math.max(0, Math.floor(region.x));
      const y = Math.max(0, Math.floor(region.y));
      const w = Math.max(1, Math.ceil(region.w));
      const h = Math.max(1, Math.ceil(region.h));

      // 防御：裁到画布内部
      const ww = Math.min(w, Math.max(1, cvs.width - x));
      const hh = Math.min(h, Math.max(1, cvs.height - y));
      if (ww < 1 || hh < 1) return;

      const m = String(this.overlayManualSelectColor || '').trim();
      const hex = m.startsWith('#') ? m.slice(1) : m;
      if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
        this.$message.warning('颜色值不合法');
        return;
      }
      const tr = parseInt(hex.slice(0, 2), 16);
      const tg = parseInt(hex.slice(2, 4), 16);
      const tb = parseInt(hex.slice(4, 6), 16);

      // 覆盖层里白色背景（以及“被擦掉后 alpha=0”的情况）不参与；其余“非白”像素改成目标颜色
      const threshold = Math.max(0, Math.min(255, Number(this.overlayManualSelectColorThreshold) || 240));

      this._snapshotOverlayManualUndo();
      this.overlayManualSelectColorRunning = true;
      try {
        const img = ctx.getImageData(x, y, ww, hh);
        const d = img.data;
        const total = Math.floor(d.length / 4);
        let changed = 0;

        for (let i = 0; i < d.length; i += 4) {
          const r = d[i];
          const g = d[i + 1];
          const b = d[i + 2];
          const a = d[i + 3];
          if (a === 0) continue;
          const lum = 0.299 * r + 0.587 * g + 0.114 * b;
          // 非白：亮度低于阈值
          if (lum < threshold) {
            d[i] = tr;
            d[i + 1] = tg;
            d[i + 2] = tb;
            // alpha 保持不变
            changed++;
          }
        }

        ctx.putImageData(img, x, y);
        if (changed > 0) {
          const pct = ((changed / Math.max(1, total)) * 100).toFixed(2);
          this.$message.success(`已变色 ${changed}/${total}（${pct}%）非白像素`);
        } else {
          this.$message.info('未找到满足条件的“非白”像素，尝试换颜色/确认选区');
        }
      } finally {
        this.overlayManualSelectColorRunning = false;
      }
    },
    applyOverlayManualSelectThinLines() {
      const cvs = this.$refs.overlayManualCanvas;
      const region = this.overlayManualSelectedRegion;
      if (!cvs || !region) return;
      if (this.overlayManualSelectThinRunning) return;

      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      const x = Math.max(0, Math.floor(region.x));
      const y = Math.max(0, Math.floor(region.y));
      const w = Math.max(1, Math.ceil(region.w));
      const h = Math.max(1, Math.ceil(region.h));

      // 防御：裁到画布内部
      const ww = Math.min(w, Math.max(1, cvs.width - x));
      const hh = Math.min(h, Math.max(1, cvs.height - y));
      if (ww < 1 || hh < 1) return;

      const t = Math.max(0, Math.min(255, Number(this.overlayManualSelectThinThreshold) || 240));

      this._snapshotOverlayManualUndo();
      this.overlayManualSelectThinRunning = true;
      try {
        const img = ctx.getImageData(x, y, ww, hh);
        const d = img.data;
        const total = Math.floor(d.length / 4);
        let changed = 0;

        for (let i = 0; i < d.length; i += 4) {
          const r = d[i];
          const g = d[i + 1];
          const b = d[i + 2];
          const a = d[i + 3];
          if (a === 0) continue;

          const lum = 0.299 * r + 0.587 * g + 0.114 * b;
          // “偏浅”=更接近白色：将其抹掉（alpha=0），让线条边缘更利落
          if (lum >= t) {
            d[i] = 255;
            d[i + 1] = 255;
            d[i + 2] = 255;
            d[i + 3] = 0;
            changed++;
          }
        }

        ctx.putImageData(img, x, y);
        if (changed > 0) {
          const pct = ((changed / Math.max(1, total)) * 100).toFixed(2);
          this.$message.success(`已变细 ${changed}/${total}（${pct}%）偏浅像素`);
        } else {
          this.$message.info('未找到满足条件的偏浅像素，尝试调低阈值再试');
        }
      } finally {
        this.overlayManualSelectThinRunning = false;
      }
    },
    applyOverlayManualNormalizeDLabels() {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      if (this.overlayManualDLabelRunning) return;
      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      const region = this.overlayManualSelectedRegion
        ? {
            x: Math.max(0, Math.floor(this.overlayManualSelectedRegion.x)),
            y: Math.max(0, Math.floor(this.overlayManualSelectedRegion.y)),
            w: Math.max(1, Math.ceil(this.overlayManualSelectedRegion.w)),
            h: Math.max(1, Math.ceil(this.overlayManualSelectedRegion.h)),
          }
        : { x: 0, y: 0, w: cvs.width, h: cvs.height };

      const rw = Math.min(region.w, Math.max(1, cvs.width - region.x));
      const rh = Math.min(region.h, Math.max(1, cvs.height - region.y));
      if (rw < 1 || rh < 1) return;

      const startNum = Math.max(1, Math.floor(Number(this.overlayManualDLabelStart) || 1));
      this._snapshotOverlayManualUndo();
      this.overlayManualDLabelRunning = true;
      try {
        const img = ctx.getImageData(region.x, region.y, rw, rh);
        const d = img.data;
        const n = rw * rh;
        const mask = new Uint8Array(n);

        const isRedFill = (p) => {
          const r = d[p];
          const g = d[p + 1];
          const b = d[p + 2];
          const a = d[p + 3];
          if (a < 22) return false;
          return r >= 82 && g <= 138 && b <= 138 && r - g >= 14 && r - b >= 14;
        };

        for (let i = 0, p = 0; i < n; i++, p += 4) {
          if (isRedFill(p)) mask[i] = 1;
        }

        // 积分图：任意轴对齐矩形内红像素个数 O(1) 查询
        const iiW = rw + 1;
        const II = new Uint32Array(iiW * (rh + 1));
        const iiAt = (x, y) => y * iiW + x;
        for (let y = 1; y <= rh; y++) {
          for (let x = 1; x <= rw; x++) {
            const v = mask[(y - 1) * rw + (x - 1)];
            II[iiAt(x, y)] =
              v +
              II[iiAt(x - 1, y)] +
              II[iiAt(x, y - 1)] -
              II[iiAt(x - 1, y - 1)];
          }
        }

        const rectRedSum = (ox, oy, ww, hh) => {
          if (ox < 0 || oy < 0 || ox + ww > rw || oy + hh > rh) return -1;
          const x0 = ox;
          const y0 = oy;
          const x1 = ox + ww;
          const y1 = oy + hh;
          return II[iiAt(x1, y1)] - II[iiAt(x0, y1)] - II[iiAt(x1, y0)] + II[iiAt(x0, y0)];
        };

        const passesRedRatio = (ox, oy, ww, hh) => {
          if (ox < 0 || oy < 0 || ox + ww > rw || oy + hh > rh) return false;
          const area = ww * hh;
          const s = rectRedSum(ox, oy, ww, hh);
          return s * 100 >= 98 * area;
        };

        const expandSeedsForTemplate = (w0, h0) => {
          if (w0 > rw || h0 > rh || w0 < 1 || h0 < 1) return [];
          const seeds = [];
          for (let sy = 0; sy <= rh - h0; sy++) {
            for (let sx = 0; sx <= rw - w0; sx++) {
              if (passesRedRatio(sx, sy, w0, h0)) seeds.push({ sx, sy });
            }
          }
          if (!seeds.length) return [];

          let S = seeds;
          let kmax = 0;
          const maxK = Math.max(rw, rh);
          for (let k = 1; k < maxK; k++) {
            const ww = w0 + 2 * k;
            const hh = h0 + 2 * k;
            const Snext = [];
            for (let i = 0; i < S.length; i++) {
              const { sx, sy } = S[i];
              const ox = sx - k;
              const oy = sy - k;
              if (passesRedRatio(ox, oy, ww, hh)) Snext.push({ sx, sy });
            }
            if (!Snext.length) break;
            S = Snext;
            kmax = k;
          }

          const ww = w0 + 2 * kmax;
          const hh = h0 + 2 * kmax;
          const seen = new Set();
          const boxes = [];
          for (let i = 0; i < S.length; i++) {
            const { sx, sy } = S[i];
            const ox = sx - kmax;
            const oy = sy - kmax;
            const key = `${ox},${oy},${ww},${hh}`;
            if (seen.has(key)) continue;
            seen.add(key);
            boxes.push({ x: ox, y: oy, w: ww, h: hh });
          }
          return boxes;
        };

        const tw = Math.max(4, Math.min(32, Math.floor(rw * 0.02)));
        const th = Math.max(4, Math.min(32, Math.floor(rh * 0.02)));
        const templates = [
          [4, 4],
          [3, 3],
          [6, 2],
          [2, 6],
          [10, 2],
          [2, 10],
          [14, 3],
          [3, 14],
          [tw, 2],
          [2, th],
          [Math.min(tw * 2, rw), 2],
          [2, Math.min(th * 2, rh)],
        ];

        const boxKeySet = new Set();
        let comps = [];
        for (let ti = 0; ti < templates.length; ti++) {
          const w0 = templates[ti][0];
          const h0 = templates[ti][1];
          if (w0 > rw || h0 > rh) continue;
          const bs = expandSeedsForTemplate(w0, h0);
          for (let bi = 0; bi < bs.length; bi++) {
            const b = bs[bi];
            const key = `${b.x},${b.y},${b.w},${b.h}`;
            if (boxKeySet.has(key)) continue;
            boxKeySet.add(key);
            comps.push(b);
          }
        }

        const areaBox = (b) => b.w * b.h;
        const iouBox = (a, b) => {
          const x1 = Math.max(a.x, b.x);
          const y1 = Math.max(a.y, b.y);
          const x2 = Math.min(a.x + a.w, b.x + b.w);
          const y2 = Math.min(a.y + a.h, b.y + b.h);
          const iw = Math.max(0, x2 - x1);
          const ih = Math.max(0, y2 - y1);
          const inter = iw * ih;
          const u = areaBox(a) + areaBox(b) - inter;
          return u <= 0 ? 0 : inter / u;
        };
        const containsBox = (outer, inner) =>
          inner.x >= outer.x &&
          inner.y >= outer.y &&
          inner.x + inner.w <= outer.x + outer.w &&
          inner.y + inner.h <= outer.y + outer.h;

        comps = comps.filter((b) => areaBox(b) >= 9);
        comps.sort((a, b) => areaBox(b) - areaBox(a));
        const kept = [];
        for (let bi = 0; bi < comps.length; bi++) {
          const b = comps[bi];
          let skip = false;
          for (let ki = 0; ki < kept.length; ki++) {
            const k = kept[ki];
            if (containsBox(k, b) || iouBox(k, b) > 0.42) {
              skip = true;
              break;
            }
          }
          if (skip) continue;
          for (let ki = kept.length - 1; ki >= 0; ki--) {
            if (containsBox(b, kept[ki])) kept.splice(ki, 1);
          }
          kept.push(b);
        }
        comps = kept;

        if (!comps.length) {
          this.$message.info('未识别到 98% 红填充矩形（可框选更小区域或检查红底）');
          return;
        }

        comps.sort((a, b) => (a.y - b.y) || (a.x - b.x));
        const avgH = comps.reduce((s, c) => s + c.h, 0) / Math.max(1, comps.length);
        const rowTol = Math.max(8, avgH * 0.55);
        const lineRows = [];
        for (const c of comps) {
          let lineRow = lineRows.find((rr) => Math.abs(rr.y - c.y) <= rowTol);
          if (!lineRow) {
            lineRow = { y: c.y, items: [] };
            lineRows.push(lineRow);
          }
          lineRow.items.push(c);
          lineRow.y = (lineRow.y * (lineRow.items.length - 1) + c.y) / lineRow.items.length;
        }
        lineRows.sort((a, b) => a.y - b.y);
        const ordered = [];
        for (const lr of lineRows) {
          lr.items.sort((a, b) => a.x - b.x);
          ordered.push(...lr.items);
        }

        const bgHex = '#d33431';
        const fillRoundRect = (cc, gx, gy, gw, gh, rad) => {
          const r = Math.min(Math.max(0, rad), gw / 2, gh / 2);
          if (r <= 0.5) {
            cc.fillRect(gx, gy, gw, gh);
            return;
          }
          cc.beginPath();
          cc.moveTo(gx + r, gy);
          cc.lineTo(gx + gw - r, gy);
          cc.quadraticCurveTo(gx + gw, gy, gx + gw, gy + r);
          cc.lineTo(gx + gw, gy + gh - r);
          cc.quadraticCurveTo(gx + gw, gy + gh, gx + gw - r, gy + gh);
          cc.lineTo(gx + r, gy + gh);
          cc.quadraticCurveTo(gx, gy + gh, gx, gy + gh - r);
          cc.lineTo(gx, gy + r);
          cc.quadraticCurveTo(gx, gy, gx + r, gy);
          cc.closePath();
          cc.fill();
        };

        const drawOneLabel = (box, labelText) => {
          const gx = Math.floor(region.x + box.x);
          const gy = Math.floor(region.y + box.y);
          const gw = Math.max(10, Math.floor(box.w));
          const gh = Math.max(10, Math.floor(box.h));
          const cornerR = Math.max(
            2,
            Math.min(10, Math.floor(Math.min(gw, gh) * 0.16)),
          );
          ctx.fillStyle = bgHex;
          fillRoundRect(ctx, gx, gy, gw, gh, cornerR);
          const fontPx = Math.max(11, Math.floor(gh * 0.5));
          ctx.font = `800 ${fontPx}px "Segoe UI", Arial, "Microsoft YaHei UI", "PingFang SC", sans-serif`;
          const tx = gx + gw / 2;
          const ty = gy + gh / 2 + Math.max(0, fontPx * 0.04);
          ctx.lineJoin = 'round';
          ctx.lineWidth = Math.max(2.2, fontPx * 0.11);
          ctx.strokeStyle = 'rgba(0,0,0,0.42)';
          ctx.strokeText(labelText, tx, ty);
          ctx.fillStyle = '#ffffff';
          ctx.fillText(labelText, tx, ty);
        };

        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.imageSmoothingEnabled = true;

        for (let i = 0; i < ordered.length; i++) {
          drawOneLabel(ordered[i], `D${startNum + i}`);
        }

        ctx.restore();

        const scopeText = this.overlayManualSelectedRegion ? '选区' : '全图';
        this.$message.success(
          `${scopeText}已重绘 ${ordered.length} 个红色矩形标，白字编号 D${startNum}~D${startNum + ordered.length - 1}`,
        );
      } finally {
        this.overlayManualDLabelRunning = false;
      }
    },
    async applyOverlayManualGeminiDetectRedBoxes() {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      if (this.overlayManualGeminiBoxesRunning || this.overlayManualDLabelRunning) return;
      const username = localStorage.getItem('userId');
      if (!username) {
        this.$message.warning('未登录，无法调用识别接口');
        return;
      }
      const cid = this._resolveOverlayManualCid();
      if (cid == null) {
        this.$message.warning('无法解析卡片 cid，请从卡片网格打开覆盖层后再试');
        return;
      }
      const ctx = cvs.getContext('2d');
      if (!ctx) return;

      this.overlayManualGeminiBoxesRunning = true;
      try {
        const res = await card_overlay_detect_red_boxes_json({
          username,
          cid,
          overlay_image: cvs.toDataURL('image/png'),
          scan_min_run_vert: Math.max(0, Math.floor(Number(this.overlayManualDetectMinRunVert) || 0)),
          scan_min_run_horiz: Math.max(0, Math.floor(Number(this.overlayManualDetectMinRunHoriz) || 0)),
          scan_min_run_diag: Math.max(0, Math.floor(Number(this.overlayManualDetectMinRunDiag) || 0)),
          scan_min_area_px: Math.max(0, Math.floor(Number(this.overlayManualDetectMinAreaPx) || 0)),
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg || '识别失败', '红框检测');
          return;
        }
        const raw = data.boxes || [];
        const maskFn = data.mask_filename || '';
        if (!raw.length) {
          this.$message.info(
            maskFn
              ? `掩膜已保存到 cardImage：${maskFn}，但未提取到白区矩形`
              : '未提取到红框区域，可换图或稍后再试',
          );
          return;
        }
        const cw = cvs.width;
        const ch = cvs.height;
        const ordered = [];
        for (let i = 0; i < raw.length; i++) {
          const b = raw[i];
          let x = Math.max(0, Math.floor(Number(b.x) || 0));
          let y = Math.max(0, Math.floor(Number(b.y) || 0));
          let w = Math.max(1, Math.floor(Number(b.w) || 1));
          let h = Math.max(1, Math.floor(Number(b.h) || 1));
          x = Math.min(x, Math.max(0, cw - 1));
          y = Math.min(y, Math.max(0, ch - 1));
          w = Math.min(w, cw - x);
          h = Math.min(h, ch - y);
          ordered.push({ x, y, w, h });
        }
        ordered.sort((a, b) => a.y + a.h * 0.5 - (b.y + b.h * 0.5) || a.x - b.x);

        const startNum = Math.max(1, Math.floor(Number(this.overlayManualDLabelStart) || 1));
        this._snapshotOverlayManualUndo();

        const bgHex = '#d33431';
        const fillRoundRect = (cc, gx, gy, gw, gh, rad) => {
          const r = Math.min(Math.max(0, rad), gw / 2, gh / 2);
          if (r <= 0.5) {
            cc.fillRect(gx, gy, gw, gh);
            return;
          }
          cc.beginPath();
          cc.moveTo(gx + r, gy);
          cc.lineTo(gx + gw - r, gy);
          cc.quadraticCurveTo(gx + gw, gy, gx + gw, gy + r);
          cc.lineTo(gx + gw, gy + gh - r);
          cc.quadraticCurveTo(gx + gw, gy + gh, gx + gw - r, gy + gh);
          cc.lineTo(gx + r, gy + gh);
          cc.quadraticCurveTo(gx, gy + gh, gx, gy + gh - r);
          cc.lineTo(gx, gy + r);
          cc.quadraticCurveTo(gx, gy, gx + r, gy);
          cc.closePath();
          cc.fill();
        };

        const drawOneLabel = (box, labelText) => {
          const gx = Math.floor(box.x);
          const gy = Math.floor(box.y);
          const gw = Math.max(10, Math.floor(box.w));
          const gh = Math.max(10, Math.floor(box.h));
          const cornerR = Math.max(
            2,
            Math.min(10, Math.floor(Math.min(gw, gh) * 0.16)),
          );
          ctx.fillStyle = bgHex;
          fillRoundRect(ctx, gx, gy, gw, gh, cornerR);
          const fontPx = Math.max(11, Math.floor(gh * 0.5));
          ctx.font = `800 ${fontPx}px "Segoe UI", Arial, "Microsoft YaHei UI", "PingFang SC", sans-serif`;
          const tx = gx + gw / 2;
          const ty = gy + gh / 2 + Math.max(0, fontPx * 0.04);
          ctx.lineJoin = 'round';
          ctx.lineWidth = Math.max(2.2, fontPx * 0.11);
          ctx.strokeStyle = 'rgba(0,0,0,0.42)';
          ctx.strokeText(labelText, tx, ty);
          ctx.fillStyle = '#ffffff';
          ctx.fillText(labelText, tx, ty);
        };

        ctx.save();
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.imageSmoothingEnabled = true;
        for (let i = 0; i < ordered.length; i++) {
          drawOneLabel(ordered[i], `D${startNum + i}`);
        }
        ctx.restore();

        const maskHint = data.mask_filename ? `掩膜已存 ${data.mask_filename}；` : '';
        this.$message.success(
          `${maskHint}已据掩膜识别 ${ordered.length} 区并编号 D${startNum}~D${startNum + ordered.length - 1}`,
        );
      } catch (err) {
        this._showErr30(err?.message || String(err), '红框检测');
      } finally {
        this.overlayManualGeminiBoxesRunning = false;
      }
    },
    overlayManualSaveTargetForFile() {
      const len = (this.overlayTestHistory || []).length;
      const idx = Number(this.overlayTestHistoryIndex ?? -1);
      if (len >= 2 && idx === 0) return 'prev';
      return 'current';
    },
    onOverlayManualDialogClose() {
      this._teardownOverlayManualLineDrag();
    },
    _teardownOverlayManualLineDrag() {
      document.removeEventListener('mousemove', this.onOverlayManualLineMove);
      document.removeEventListener('mouseup', this.onOverlayManualLineUp, true);
      this.overlayManualLineDrawing = false;
      this.overlayManualLineStart = null;
      this.overlayManualLineBackup = null;
      document.removeEventListener('mousemove', this.onOverlayManualRectMove);
      document.removeEventListener('mouseup', this.onOverlayManualRectUp, true);
      this.overlayManualRectDrawing = false;
      this.overlayManualRectStart = null;
      this.overlayManualRectBackup = null;
    },
    _paintOverlayManualRect(ctx, sx, sy, ex, ey) {
      const x0 = Math.min(sx, ex);
      const y0 = Math.min(sy, ey);
      const rw = Math.max(1, Math.abs(ex - sx));
      const rh = Math.max(1, Math.abs(ey - sy));
      const c = this.overlayManualLineColor || '#000000';
      ctx.save();
      ctx.globalCompositeOperation = 'source-over';
      if (this.overlayManualRectFilled) {
        ctx.fillStyle = c;
        ctx.fillRect(x0, y0, rw, rh);
      } else {
        ctx.strokeStyle = c;
        ctx.lineWidth = Math.max(1, Number(this.overlayManualRectStrokeWidth) || 2);
        ctx.lineJoin = 'miter';
        ctx.beginPath();
        ctx.rect(x0, y0, rw, rh);
        ctx.stroke();
      }
      ctx.restore();
    },
    onOverlayManualLineMove(e) {
      if (!this.overlayManualLineDrawing || !this.overlayManualLineStart || !this.overlayManualLineBackup) return;
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      const p = this._getOverlayManualPoint(e);
      if (!p) return;
      const ctx = cvs.getContext('2d');
      ctx.putImageData(this.overlayManualLineBackup, 0, 0);
      ctx.save();
      ctx.strokeStyle = this.overlayManualLineColor || '#000000';
      ctx.lineWidth = Math.max(1, Number(this.overlayManualLineWidth) || 2);
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.globalCompositeOperation = 'source-over';
      ctx.beginPath();
      ctx.moveTo(this.overlayManualLineStart.x, this.overlayManualLineStart.y);
      ctx.lineTo(p.x, p.y);
      ctx.stroke();
      ctx.restore();
    },
    onOverlayManualLineUp(e) {
      if (!this.overlayManualLineDrawing) return;
      document.removeEventListener('mousemove', this.onOverlayManualLineMove);
      document.removeEventListener('mouseup', this.onOverlayManualLineUp, true);
      const cvs = this.$refs.overlayManualCanvas;
      if (cvs && this.overlayManualLineBackup && this.overlayManualLineStart) {
        const p = this._getOverlayManualPoint(e);
        if (p) {
          const ctx = cvs.getContext('2d');
          ctx.putImageData(this.overlayManualLineBackup, 0, 0);
          ctx.save();
          ctx.strokeStyle = this.overlayManualLineColor || '#000000';
          ctx.lineWidth = Math.max(1, Number(this.overlayManualLineWidth) || 2);
          ctx.lineCap = 'round';
          ctx.lineJoin = 'round';
          ctx.globalCompositeOperation = 'source-over';
          ctx.beginPath();
          ctx.moveTo(this.overlayManualLineStart.x, this.overlayManualLineStart.y);
          ctx.lineTo(p.x, p.y);
          ctx.stroke();
          ctx.restore();
        }
      }
      this.overlayManualLineDrawing = false;
      this.overlayManualLineStart = null;
      this.overlayManualLineBackup = null;
    },
    onOverlayManualRectMove(e) {
      if (!this.overlayManualRectDrawing || !this.overlayManualRectStart || !this.overlayManualRectBackup) return;
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      const p = this._getOverlayManualPoint(e);
      if (!p) return;
      const ctx = cvs.getContext('2d');
      ctx.putImageData(this.overlayManualRectBackup, 0, 0);
      this._paintOverlayManualRect(
        ctx,
        this.overlayManualRectStart.x,
        this.overlayManualRectStart.y,
        p.x,
        p.y,
      );
    },
    onOverlayManualRectUp(e) {
      if (!this.overlayManualRectDrawing) return;
      document.removeEventListener('mousemove', this.onOverlayManualRectMove);
      document.removeEventListener('mouseup', this.onOverlayManualRectUp, true);
      const cvs = this.$refs.overlayManualCanvas;
      if (cvs && this.overlayManualRectBackup && this.overlayManualRectStart) {
        const p = this._getOverlayManualPoint(e);
        if (p) {
          const ctx = cvs.getContext('2d');
          ctx.putImageData(this.overlayManualRectBackup, 0, 0);
          this._paintOverlayManualRect(
            ctx,
            this.overlayManualRectStart.x,
            this.overlayManualRectStart.y,
            p.x,
            p.y,
          );
        }
      }
      this.overlayManualRectDrawing = false;
      this.overlayManualRectStart = null;
      this.overlayManualRectBackup = null;
    },
    async confirmOverlayManualEdit() {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      this._teardownOverlayManualLineDrag();
      const username = localStorage.getItem('userId');
      if (!username) {
        this.$message.warning('未登录，无法保存到服务器');
        return;
      }
      const target = this.overlayManualSaveTargetForFile();
      const dataUrl = cvs.toDataURL('image/png');
      this.overlayManualConfirming = true;
      try {
        const res = await card_save_overlay_layer_file({
          username,
          cid: this.cid,
          overlay_image: dataUrl,
          target,
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg, '保存覆盖层失败');
          return;
        }
        const saved = data.overlay_image || dataUrl;
        this.overlayTestLayerDataUrl = saved;
        const idx = Number(this.overlayTestHistoryIndex ?? -1);
        if (idx >= 0 && this.overlayTestHistory[idx]) {
          const next = [...this.overlayTestHistory];
          const item = { ...next[idx], image: saved };
          if (data.overlay_bbox && data.overlay_bbox.w > 0 && data.overlay_bbox.h > 0) {
            item.bbox = { ...data.overlay_bbox };
            this.overlayTestSourceBoxNorm = { ...data.overlay_bbox };
            this.overlayTestTargetBoxNorm = { ...data.overlay_bbox };
          }
          next[idx] = item;
          this.overlayTestHistory = next;
        }
        await this.rebuildOverlayPreviewAlpha();
        this.persistOverlaySession();
        this.overlayManualDialogVisible = false;
        this.$message.success(target === 'prev' ? '已保存到 overlay_prev' : '已保存到 overlay_current');
      } catch (err) {
        this._showErr30(err?.message || err, '保存覆盖层失败');
      } finally {
        this.overlayManualConfirming = false;
      }
    },
    // 选区相关方法
    _extractSelectionImageData(shouldClear = true) {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs || !this.overlayManualSelectedRegion) return;
      const ctx = cvs.getContext('2d');
      const { x, y, w, h } = this.overlayManualSelectedRegion;
      const ix = Math.max(0, Math.floor(x));
      const iy = Math.max(0, Math.floor(y));
      const iw = Math.max(1, Math.min(cvs.width - ix, Math.ceil(w)));
      const ih = Math.max(1, Math.min(cvs.height - iy, Math.ceil(h)));

      this.overlayManualSelectedRegion = { x: ix, y: iy, w: iw, h: ih };
      this.overlayManualSelectionImageData = ctx.getImageData(ix, iy, iw, ih);

      if (shouldClear) {
        ctx.clearRect(ix, iy, iw, ih);
      }
    },
    clearManualSelection() {
      this._teardownOverlayManualLineDrag();
      this.overlayManualSelectedRegion = null;
      this.overlayManualSelectionImageData = null;
      this.overlayManualDragEdge = null;
      this.overlayManualDragStart = null;
      this.overlayManualIsDragging = false;
      this.overlayManualDragStartRegion = null;
      this.overlayManualDragSourceImageData = null;
      this.overlayManualTransforming = false;
      document.removeEventListener('mousemove', this.onSelectionDrag);
      document.removeEventListener('mouseup', this.onSelectionDragEnd);
      document.removeEventListener('mousemove', this.onEdgeDrag);
      document.removeEventListener('mouseup', this.onEdgeDragEnd);
    },
    getSelectionBoxStyle() {
      if (!this.overlayManualSelectedRegion) return {};
      const { x, y, w, h } = this.overlayManualSelectedRegion;
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs || !cvs.width || !cvs.height) return {};
      const displayW = cvs.clientWidth || 1;
      const displayH = cvs.clientHeight || 1;
      const scaleX = displayW / cvs.width;
      const scaleY = displayH / cvs.height;
      return {
        left: Math.max(0, x * scaleX) + 'px',
        top: Math.max(0, y * scaleY) + 'px',
        width: Math.max(1, w * scaleX) + 'px',
        height: Math.max(1, h * scaleY) + 'px'
      };
    },
    getDragPreviewStyle() {
      if (!this.overlayManualSelectedRegion || !this.overlayManualSelectionImageData) return {};
      const { x, y, w, h } = this.overlayManualSelectedRegion;
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs || !cvs.width || !cvs.height) return {};
      const displayW = cvs.clientWidth || 1;
      const displayH = cvs.clientHeight || 1;
      const scaleX = displayW / cvs.width;
      const scaleY = displayH / cvs.height;
      return {
        left: Math.max(0, x * scaleX) + 'px',
        top: Math.max(0, y * scaleY) + 'px',
        width: Math.max(1, w * scaleX) + 'px',
        height: Math.max(1, h * scaleY) + 'px'
      };
    },
    _renderOverlayManualDragPreview() {
      this.$nextTick(() => {
        const previewCanvas = this.$refs.overlayManualDragPreview;
        const srcData = this.overlayManualDragSourceImageData || this.overlayManualSelectionImageData;
        if (!previewCanvas || !srcData || !this.overlayManualSelectedRegion) return;
        const { w, h } = this.overlayManualSelectedRegion;
        const dw = Math.max(1, Math.ceil(w));
        const dh = Math.max(1, Math.ceil(h));
        previewCanvas.width = dw;
        previewCanvas.height = dh;
        const pctx = previewCanvas.getContext('2d');
        pctx.clearRect(0, 0, dw, dh);
        const tmp = document.createElement('canvas');
        tmp.width = srcData.width;
        tmp.height = srcData.height;
        const tctx = tmp.getContext('2d');
        tctx.putImageData(srcData, 0, 0);
        pctx.drawImage(tmp, 0, 0, tmp.width, tmp.height, 0, 0, dw, dh);
      });
    },
    _isOverlayManualSolidPixel(r, g, b, a) {
      // 白色/透明像素视为“空”，移动/复制放置时不应覆盖目标区域
      if (a <= 8) return false;
      return !(r >= 245 && g >= 245 && b >= 245);
    },
    _blendOverlayManualImageDataSkipWhite(dstData, srcData) {
      const dd = dstData.data;
      const sd = srcData.data;
      const n = Math.min(dd.length, sd.length);
      for (let i = 0; i < n; i += 4) {
        const sr = sd[i];
        const sg = sd[i + 1];
        const sb = sd[i + 2];
        const sa = sd[i + 3];
        if (!this._isOverlayManualSolidPixel(sr, sg, sb, sa)) continue;
        dd[i] = sr;
        dd[i + 1] = sg;
        dd[i + 2] = sb;
        dd[i + 3] = sa;
      }
    },
    _commitSelectionPixelsToCanvas() {
      const cvs = this.$refs.overlayManualCanvas;
      const srcData = this.overlayManualDragSourceImageData || this.overlayManualSelectionImageData;
      if (!cvs || !srcData || !this.overlayManualSelectedRegion) return;
      const ctx = cvs.getContext('2d');
      const { x, y, w, h } = this.overlayManualSelectedRegion;
      const dx = Math.max(0, Math.floor(x));
      const dy = Math.max(0, Math.floor(y));
      const dw = Math.max(1, Math.ceil(w));
      const dh = Math.max(1, Math.ceil(h));
      const srcW = Math.max(1, srcData.width || 1);
      const srcH = Math.max(1, srcData.height || 1);
      // 平移/复制放置：白色与透明像素不覆盖目标区域
      if (dw === srcW && dh === srcH) {
        const dst = ctx.getImageData(dx, dy, dw, dh);
        this._blendOverlayManualImageDataSkipWhite(dst, srcData);
        ctx.putImageData(dst, dx, dy);
      } else {
        // 伸缩：仅在尺寸变化时做缩放
        const tmp = document.createElement('canvas');
        tmp.width = srcW;
        tmp.height = srcH;
        const tctx = tmp.getContext('2d');
        tctx.putImageData(srcData, 0, 0);
        const tmpScaled = document.createElement('canvas');
        tmpScaled.width = dw;
        tmpScaled.height = dh;
        const sctx = tmpScaled.getContext('2d');
        sctx.drawImage(tmp, 0, 0, srcW, srcH, 0, 0, dw, dh);
        const scaled = sctx.getImageData(0, 0, dw, dh);
        const dst = ctx.getImageData(dx, dy, dw, dh);
        this._blendOverlayManualImageDataSkipWhite(dst, scaled);
        ctx.putImageData(dst, dx, dy);
      }
      // 提交后保留当前选区；像素数据在下次拖拽开始时重新抽取
      this.overlayManualSelectedRegion = { x: dx, y: dy, w: dw, h: dh };
      this.overlayManualSelectionImageData = null;
      this.overlayManualDragSourceImageData = null;
      this.overlayManualDragStartRegion = null;
    },
    onSelectionBoxMouseDown(e) {
      if (this.overlayManualSelectMode === 'copyplace') {
        if (
          !this.overlayManualCopyFloating ||
          !this.overlayManualCopyClipboard ||
          !this.overlayManualSelectedRegion
        ) {
          return;
        }
        this._snapshotOverlayManualUndo();
        this.overlayManualDragSourceImageData = this.overlayManualCopyClipboard;
        this.overlayManualSelectionImageData = this.overlayManualCopyClipboard;
        this.overlayManualDragStartRegion = { ...this.overlayManualSelectedRegion };
        this.overlayManualTransforming = true;
        this.overlayManualIsDragging = true;
        this.overlayManualDragStart = { x: e.clientX, y: e.clientY };
        this._renderOverlayManualDragPreview();
        document.addEventListener('mousemove', this.onSelectionDrag);
        document.addEventListener('mouseup', this.onSelectionDragEnd);
        return;
      }
      if (this.overlayManualSelectMode === 'move') {
        // 平移模式：开始时抽取像素并清空原位置，拖拽结束再落图
        if (!this.overlayManualSelectedRegion) return;
        this._snapshotOverlayManualUndo();
        this._extractSelectionImageData(true);
        this.overlayManualDragSourceImageData = this.overlayManualSelectionImageData;
        this.overlayManualDragStartRegion = { ...this.overlayManualSelectedRegion };
        this.overlayManualTransforming = true;
        this.overlayManualIsDragging = true;
        this.overlayManualDragStart = { x: e.clientX, y: e.clientY };
        this._renderOverlayManualDragPreview();
        document.addEventListener('mousemove', this.onSelectionDrag);
        document.addEventListener('mouseup', this.onSelectionDragEnd);
      }
    },
    onSelectionDrag(e) {
      if (!this.overlayManualIsDragging || !this.overlayManualDragStart || !this.overlayManualSelectedRegion || !this.overlayManualDragStartRegion) return;
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      const r = cvs.getBoundingClientRect();
      const scale = cvs.width / r.width;
      const dx = (e.clientX - this.overlayManualDragStart.x) * scale;
      const dy = (e.clientY - this.overlayManualDragStart.y) * scale;
      const base = this.overlayManualDragStartRegion;
      const newX = Math.max(0, Math.min(cvs.width - base.w, base.x + dx));
      const newY = Math.max(0, Math.min(cvs.height - base.h, base.y + dy));
      this.overlayManualSelectedRegion = { x: newX, y: newY, w: base.w, h: base.h };
      this._renderOverlayManualDragPreview();
    },
    onSelectionDragEnd() {
      const wasCopyPlace =
        this.overlayManualSelectMode === 'copyplace' && this.overlayManualCopyFloating;
      if (this.overlayManualSelectionImageData) {
        this._commitSelectionPixelsToCanvas();
      }
      if (wasCopyPlace && this.overlayManualCopyClipboard) {
        // 保留剪贴板与待放置状态，选区位置已由 _commit 更新为刚放置处，便于连续拖到下一处
        this.overlayManualCopyFloating = true;
        this.overlayManualSelectionImageData = this.overlayManualCopyClipboard;
      }
      this.overlayManualIsDragging = false;
      this.overlayManualDragStart = null;
      this.overlayManualDragStartRegion = null;
      this.overlayManualDragSourceImageData = null;
      this.overlayManualTransforming = false;
      document.removeEventListener('mousemove', this.onSelectionDrag);
      document.removeEventListener('mouseup', this.onSelectionDragEnd);
    },
    onOverlayManualSelectModeChange() {
      if (this.overlayManualSelectMode !== 'copyplace') {
        this.overlayManualCopyClipboard = null;
        this.overlayManualCopyFloating = false;
      }
    },
    overlayManualCopySelectionToClipboard() {
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs || !this.overlayManualSelectedRegion) return;
      let { x, y, w, h } = this.overlayManualSelectedRegion;
      if (w <= 5 || h <= 5) {
        this.$message.warning('请先拖出足够大的选区');
        return;
      }
      const ix = Math.max(0, Math.floor(x));
      const iy = Math.max(0, Math.floor(y));
      const iw = Math.max(1, Math.min(cvs.width - ix, Math.ceil(w)));
      const ih = Math.max(1, Math.min(cvs.height - iy, Math.ceil(h)));
      const ctx = cvs.getContext('2d');
      const data = ctx.getImageData(ix, iy, iw, ih);
      const buf = new Uint8ClampedArray(data.data);
      this.overlayManualCopyClipboard = new ImageData(buf, data.width, data.height);
      this.overlayManualCopyFloating = true;
      this.overlayManualSelectionImageData = this.overlayManualCopyClipboard;
      this.overlayManualDragSourceImageData = null;
      this.overlayManualSelectedRegion = { x: ix, y: iy, w: iw, h: ih };
      this.$message.success('已复制，可反复拖动虚线框到多处松开放置');
    },
    overlayManualCancelCopyFloating() {
      this.overlayManualCopyFloating = false;
      this.overlayManualCopyClipboard = null;
      this.overlayManualSelectionImageData = null;
      this.overlayManualDragSourceImageData = null;
    },
    onEdgeDragStart(edge, e) {
      if (this.overlayManualSelectMode !== 'stretch') return;
      if (!this.overlayManualSelectedRegion) return;
      this._snapshotOverlayManualUndo();
      this._extractSelectionImageData(true);
      this.overlayManualDragSourceImageData = this.overlayManualSelectionImageData;
      this.overlayManualDragStartRegion = { ...this.overlayManualSelectedRegion };
      this.overlayManualDragEdge = edge;
      this.overlayManualTransforming = true;
      this.overlayManualIsDragging = true;
      this.overlayManualDragStart = { x: e.clientX, y: e.clientY };
      this._renderOverlayManualDragPreview();
      document.addEventListener('mousemove', this.onEdgeDrag);
      document.addEventListener('mouseup', this.onEdgeDragEnd);
    },
    onEdgeDrag(e) {
      if (!this.overlayManualIsDragging || !this.overlayManualDragStart || !this.overlayManualSelectedRegion || !this.overlayManualDragEdge || !this.overlayManualDragStartRegion) return;
      const cvs = this.$refs.overlayManualCanvas;
      if (!cvs) return;
      const r = cvs.getBoundingClientRect();
      const scale = cvs.width / r.width;
      const dx = (e.clientX - this.overlayManualDragStart.x) * scale;
      const dy = (e.clientY - this.overlayManualDragStart.y) * scale;
      const base = this.overlayManualDragStartRegion;
      const region = { ...base };
      
      // 根据拖动的边更新选区 - 伸缩ImageData
      switch (this.overlayManualDragEdge) {
        case 'top':
          region.y = base.y + dy;
          region.h = base.h - dy;
          break;
        case 'right':
          region.w = base.w + dx;
          break;
        case 'bottom':
          region.h = base.h + dy;
          break;
        case 'left':
          region.x = base.x + dx;
          region.w = base.w - dx;
          break;
      }
      
      // 限制最小尺寸
      if (region.w >= 10 && region.h >= 10) {
        // 限制在画布范围内
        region.x = Math.max(0, region.x);
        region.y = Math.max(0, region.y);
        region.w = Math.max(10, Math.min(cvs.width - region.x, region.w));
        region.h = Math.max(10, Math.min(cvs.height - region.y, region.h));
        
        this.overlayManualSelectedRegion = region;
        this._renderOverlayManualDragPreview();
      }
    },
    onEdgeDragEnd() {
      if (this.overlayManualSelectionImageData) {
        this._commitSelectionPixelsToCanvas();
      }
      this.overlayManualIsDragging = false;
      this.overlayManualDragStart = null;
      this.overlayManualDragEdge = null;
      this.overlayManualDragStartRegion = null;
      this.overlayManualDragSourceImageData = null;
      this.overlayManualTransforming = false;
      document.removeEventListener('mousemove', this.onEdgeDrag);
      document.removeEventListener('mouseup', this.onEdgeDragEnd);
    },
    overlaySessionStorageKey() {
      const username = localStorage.getItem('userId') || 'anon';
      return `card_overlay_session:${username}:${this.cid}`;
    },
    persistOverlaySession() {
      try {
        const his = this.overlayTestHistory || [];
        const idx = Number(this.overlayTestHistoryIndex ?? -1);
        const hisItem = (idx >= 0 && idx < his.length) ? his[idx] : null;
        const safeLayer = this.overlayTestLayerDataUrl || hisItem?.image || '';
        const safeSource = this.overlayTestSourceBoxNorm || hisItem?.bbox || null;
        const payload = {
          history: this.overlayTestHistory || [],
          historyIndex: Number(this.overlayTestHistoryIndex ?? -1),
          layer: safeLayer,
          sourceBox: safeSource,
          targetBox: this.overlayTestTargetBoxNorm || null,
          baseSource: this.overlayTestBaseSource || 'current',
          customBase: this.overlayTestCustomBaseDataUrl || '',
          customBaseSaved: !!this.overlayTestCustomBaseSaved,
          keepWhiteRegions: Array.isArray(this.overlayKeepWhiteRegions) ? this.overlayKeepWhiteRegions : [],
          opacity: Number(this.overlayTestContentOpacity ?? 100),
          topBusy: !!this.overlayTopBusy,
        };
        sessionStorage.setItem(this.overlaySessionStorageKey(), JSON.stringify(payload));
      } catch (e) {}
    },
    restoreOverlaySession() {
      try {
        const raw = sessionStorage.getItem(this.overlaySessionStorageKey());
        if (!raw) return;
        const s = JSON.parse(raw);
        this.overlayTestHistory = Array.isArray(s.history) ? s.history.slice(-2) : [];
        this.overlayTestHistoryIndex = Number.isInteger(s.historyIndex) ? s.historyIndex : (this.overlayTestHistory.length - 1);
        if (this.overlayTestHistoryIndex < 0 && this.overlayTestHistory.length > 0) this.overlayTestHistoryIndex = this.overlayTestHistory.length - 1;
        if (this.overlayTestHistoryIndex >= this.overlayTestHistory.length) this.overlayTestHistoryIndex = this.overlayTestHistory.length - 1;
        const hisItem = (this.overlayTestHistoryIndex >= 0 && this.overlayTestHistoryIndex < this.overlayTestHistory.length)
          ? this.overlayTestHistory[this.overlayTestHistoryIndex]
          : null;
        this.overlayTestLayerDataUrl = s.layer || hisItem?.image || this.overlayTestLayerDataUrl || '';
        this.overlayTestSourceBoxNorm = s.sourceBox || hisItem?.bbox || this.overlayTestSourceBoxNorm || null;
        this.overlayTestTargetBoxNorm = s.targetBox || null;
        if (['current', 'backup', 'custom'].includes(s.baseSource)) this.overlayTestBaseSource = s.baseSource;
        this.overlayTestCustomBaseDataUrl = s.customBase || '';
        this.overlayTestCustomBaseSaved = !!s.customBaseSaved;
        this.overlayKeepWhiteRegions = Array.isArray(s.keepWhiteRegions) ? s.keepWhiteRegions : [];
        // 兼容旧会话：只要已有 customBase，默认认为服务端已暂存过，避免应用阶段重复上传触发失败
        if (!s.customBaseSaved && this.overlayTestCustomBaseDataUrl) this.overlayTestCustomBaseSaved = true;
        if (typeof s.opacity === 'number') this.overlayTestContentOpacity = Math.max(0, Math.min(100, s.opacity));
        this.overlayTopBusy = !!s.topBusy;
        this.rebuildOverlayPreviewAlpha();
      } catch (e) {}
    },
    _pushOverlayHistory(imageDataUrl, bbox) {
      if (!imageDataUrl) return;
      const current = this.overlayTestHistory[this.overlayTestHistoryIndex];
      if (current && current.image === imageDataUrl) return;
      if (this.overlayTestHistoryIndex < this.overlayTestHistory.length - 1) {
        this.overlayTestHistory = this.overlayTestHistory.slice(0, this.overlayTestHistoryIndex + 1);
      }
      this.overlayTestHistory.push({
        image: imageDataUrl,
        bbox: bbox ? { ...bbox } : null,
      });
      const MAX_HISTORY = 2;
      if (this.overlayTestHistory.length > MAX_HISTORY) {
        this.overlayTestHistory = this.overlayTestHistory.slice(this.overlayTestHistory.length - MAX_HISTORY);
      }
      this.overlayTestHistoryIndex = this.overlayTestHistory.length - 1;
      this.persistOverlaySession();
    },
    async _applyOverlayHistoryItem(item) {
      if (!item || !item.image) return;
      this.overlayTestLayerDataUrl = item.image;
      if (item.bbox && item.bbox.w > 0 && item.bbox.h > 0) {
        this.overlayTestSourceBoxNorm = { ...item.bbox };
        this.overlayTestTargetBoxNorm = { ...item.bbox };
      }
      await this.rebuildOverlayPreviewAlpha();
      this.persistOverlaySession();
    },
    addCurrentRegionToOverlayKeepWhite() {
      const r = this.overlayIterateEditRegionNorm;
      if (!r || r.w <= 0 || r.h <= 0) {
        this.$message.warning('请先在右侧图上框选一个区域');
        return;
      }
      const box = {
        x: Math.max(0, Math.min(1, Number(r.x) || 0)),
        y: Math.max(0, Math.min(1, Number(r.y) || 0)),
        w: Math.max(0.001, Math.min(1, Number(r.w) || 0)),
        h: Math.max(0.001, Math.min(1, Number(r.h) || 0)),
      };
      const list = Array.isArray(this.overlayKeepWhiteRegions) ? [...this.overlayKeepWhiteRegions] : [];
      const key = `${box.x.toFixed(4)}_${box.y.toFixed(4)}_${box.w.toFixed(4)}_${box.h.toFixed(4)}`;
      const exists = list.some((it) => {
        const k = `${Number(it?.x || 0).toFixed(4)}_${Number(it?.y || 0).toFixed(4)}_${Number(it?.w || 0).toFixed(4)}_${Number(it?.h || 0).toFixed(4)}`;
        return k === key;
      });
      if (!exists) list.push(box);
      this.overlayKeepWhiteRegions = list.slice(0, 30);
      this.persistOverlaySession();
      this.$message.success(exists ? '该区域已在白色保留区中' : '已加入白色保留区');
    },
    addManualSelectionToOverlayKeepWhite() {
      const r = this.overlayManualSelectedRegion;
      const cvs = this.$refs.overlayManualCanvas;
      if (!r || !cvs || !cvs.width || !cvs.height || r.w <= 0 || r.h <= 0) {
        this.$message.warning('请先在手动修改画布中框选一个区域');
        return;
      }
      const box = {
        x: Math.max(0, Math.min(1, Number(r.x || 0) / Number(cvs.width || 1))),
        y: Math.max(0, Math.min(1, Number(r.y || 0) / Number(cvs.height || 1))),
        w: Math.max(0.001, Math.min(1, Number(r.w || 0) / Number(cvs.width || 1))),
        h: Math.max(0.001, Math.min(1, Number(r.h || 0) / Number(cvs.height || 1))),
      };
      const list = Array.isArray(this.overlayKeepWhiteRegions) ? [...this.overlayKeepWhiteRegions] : [];
      const key = `${box.x.toFixed(4)}_${box.y.toFixed(4)}_${box.w.toFixed(4)}_${box.h.toFixed(4)}`;
      const exists = list.some((it) => {
        const k = `${Number(it?.x || 0).toFixed(4)}_${Number(it?.y || 0).toFixed(4)}_${Number(it?.w || 0).toFixed(4)}_${Number(it?.h || 0).toFixed(4)}`;
        return k === key;
      });
      if (!exists) list.push(box);
      this.overlayKeepWhiteRegions = list.slice(0, 30);
      this.persistOverlaySession();
      this.$message.success(exists ? '该区域已在白色保留区中' : '已加入白色保留区');
    },
    clearOverlayKeepWhiteRegions() {
      this.overlayKeepWhiteRegions = [];
      this.persistOverlaySession();
    },
    async goOverlayHistoryPrev() {
      if (!this.canOverlayHistoryPrev) return;
      this.overlayTestHistoryIndex -= 1;
      await this._applyOverlayHistoryItem(this.overlayTestHistory[this.overlayTestHistoryIndex]);
    },
    async goOverlayHistoryNext() {
      if (!this.canOverlayHistoryNext) return;
      this.overlayTestHistoryIndex += 1;
      await this._applyOverlayHistoryItem(this.overlayTestHistory[this.overlayTestHistoryIndex]);
    },
    async syncOverlayHistoryFromServer() {
      const username = localStorage.getItem('userId');
      if (!username) return;
      try {
        const res = await card_get_overlay_test_history({ username, cid: this.cid });
        const data = res.data || res;
        if (data.error_num !== 0) return;
        const items = Array.isArray(data.items) ? data.items : [];
        if (!items.length) return;
        this.overlayTestHistory = items.slice(-2);
        this.overlayTestHistoryIndex = this.overlayTestHistory.length - 1;
        const cur = this.overlayTestHistory[this.overlayTestHistoryIndex];
        this.overlayTestLayerDataUrl = cur?.image || this.overlayTestLayerDataUrl;
        if (cur?.bbox) {
          this.overlayTestSourceBoxNorm = { ...cur.bbox };
          this.overlayTestTargetBoxNorm = { ...cur.bbox };
        }
        await this.rebuildOverlayPreviewAlpha();
      } catch (e) {}
    },
    stopOverlayTestPolling() {
      if (this.overlayTestPollTimer) {
        clearTimeout(this.overlayTestPollTimer);
        this.overlayTestPollTimer = null;
      }
      this.overlayTestJobRunning = false;
    },
    async pollOverlayTestStatus(immediate = false) {
      this.stopOverlayTestPolling();
      const username = localStorage.getItem('userId');
      if (!username) return;
      const run = async () => {
        try {
          const res = await card_get_overlay_test_layer_status({ username, cid: this.cid });
          const data = res.data || res;
          if (data.error_num !== 0) return;
          const status = data.status || 'idle';
          if (status === 'awaiting_qa_composite') {
            this.overlayTestJobRunning = true;
            this.overlayTopBusy = false;
            this.overlayTestGenerating = false;
            this.overlayBusyProgressStep = Math.max(0, Number(data.progress_step) || 0);
            this.overlayBusyProgressTotal = Math.max(0, Number(data.progress_total) || 0);
            this.overlayBusyProgressMsg = data.progress_msg || '';
            if (data.overlay_image) {
              this.overlayTestLayerDataUrl = data.overlay_image;
              this.overlayTestLayerPreviewDataUrl = '';
            }
            const box = data.overlay_bbox || null;
            if (box && box.w > 0 && box.h > 0) {
              this.overlayTestSourceBoxNorm = { x: box.x, y: box.y, w: box.w, h: box.h };
              this.overlayTestTargetBoxNorm = { ...this.overlayTestSourceBoxNorm };
            }
            await this.rebuildOverlayPreviewAlpha();
            if (!this.overlayQaDialogVisible && !this.overlayQaSkipRequested) {
              this.overlayQaDialogVisible = true;
              this.overlayQaAwaitingSince = Date.now();
              this.$message.info('请先对齐覆盖层并确认，再继续后台质检');
            }
            this.persistOverlaySession();
            this.overlayTestPollTimer = setTimeout(run, 1600);
            return;
          }
          if (status === 'running') {
            this.overlayTestJobRunning = true;
            this.overlayTopBusy = true;
            this.overlayTestGenerating = true;
            this.overlayBusyProgressStep = Math.max(0, Number(data.progress_step) || 0);
            this.overlayBusyProgressTotal = Math.max(0, Number(data.progress_total) || 0);
            this.overlayBusyProgressMsg = data.progress_msg || '';
            this.persistOverlaySession();
            this.overlayTestPollTimer = setTimeout(run, 1800);
            return;
          }
          this.overlayTestJobRunning = false;
          this.overlayTestGenerating = false;
          this.overlayTopBusy = false;
          this.overlayQaDialogVisible = false;
          this.overlayQaSkipRequested = false;
          this.overlayBusyProgressStep = 0;
          this.overlayBusyProgressTotal = 0;
          this.overlayBusyProgressMsg = '';
          if (status === 'success' && data.overlay_image) {
            this.overlayTestLayerDataUrl = data.overlay_image;
            const box = data.overlay_bbox || null;
            if (box && box.w > 0 && box.h > 0) {
              this.overlayTestSourceBoxNorm = { x: box.x, y: box.y, w: box.w, h: box.h };
              if (!this.overlayTestTargetBoxNorm) this.overlayTestTargetBoxNorm = { ...this.overlayTestSourceBoxNorm };
            }
            await this.syncOverlayHistoryFromServer();
            this.overlayPendingSnapshot = null;
            this.overlayCurrentOp = '';
            this.persistOverlaySession();
            if (data.msg === 'overlay_iterate_success') {
              this.$message.success('覆盖层迭代已完成');
            } else if (typeof data.msg === 'string' && data.msg.startsWith('overlay_generate_success_with_autodetect:')) {
              const n = Number(String(data.msg).split(':')[1] || 0);
              this.$message.success(`覆盖层已生成完成；后台红框识别已完成（${Number.isFinite(n) ? n : 0} 个）`);
            } else if (data.msg === 'overlay_generate_success_autodetect_failed') {
              this.$message.warning('覆盖层已生成完成；后台红框识别失败（不影响覆盖层生成）');
            } else {
              this.$message.success('覆盖层已生成完成');
            }
          } else if (status === 'error') {
            if (this.overlayCurrentOp === 'iterate' && this.overlayPendingSnapshot) {
              const s = this.overlayPendingSnapshot;
              this.overlayTestLayerDataUrl = s.layer || this.overlayTestLayerDataUrl;
              this.overlayTestLayerPreviewDataUrl = s.preview || this.overlayTestLayerPreviewDataUrl;
              this.overlayTestHistory = Array.isArray(s.history) ? s.history : this.overlayTestHistory;
              this.overlayTestHistoryIndex = Number.isInteger(s.historyIndex) ? s.historyIndex : this.overlayTestHistoryIndex;
              this.overlayTestSourceBoxNorm = s.source || this.overlayTestSourceBoxNorm;
              this.overlayTestTargetBoxNorm = s.target || this.overlayTestTargetBoxNorm;
              await this.rebuildOverlayPreviewAlpha();
            }
            await this.syncOverlayHistoryFromServer();
            this.overlayPendingSnapshot = null;
            this.overlayCurrentOp = '';
            this.persistOverlaySession();
            this._showErr30(data.msg, '生成覆盖层失败');
          }
        } catch (e) {
          this.overlayTestGenerating = false;
        }
      };
      if (immediate) run();
      else this.overlayTestPollTimer = setTimeout(run, 500);
    },
    async fetchOverlayBasePreset() {
      const username = localStorage.getItem('userId');
      if (!username || this.overlayTestBaseSource === 'custom') return;
      try {
        const res = await card_get_overlay_test_base_image({
          username,
          cid: this.cid,
          base_source: this.overlayTestBaseSource || 'current',
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg, '读取底图失败');
          return;
        }
        this.overlayTestBaseImageDataUrl = data.base_image || '';
        this.persistOverlaySession();
      } catch (e) {
        this._showErr30(e?.message || e, '读取底图失败');
      }
    },
    triggerOverlayBaseUpload() {
      this.$refs.overlayBaseFileInput?.click();
    },
    async normalizeOverlayBaseDataUrl(dataUrl) {
      const src = String(dataUrl || '').trim();
      if (!src) return '';
      // 保真优先：不做有损压缩/缩放，直接使用原始 dataURL。
      // 避免高清底图在前端重编码后出现细节损失。
      return src;
    },
    async uploadOverlayCustomBaseIfNeeded(force = false) {
      if (this.overlayTestBaseSource !== 'custom') return true;
      const d = String(this.overlayTestCustomBaseDataUrl || '').trim();
      if (!d) return false;
      if (!force && this.overlayTestCustomBaseSaved) return true;
      const username = localStorage.getItem('userId');
      if (!username) return false;
      const res = await card_save_overlay_custom_base_image({
        username,
        cid: this.cid,
        base_image: d,
      });
      const data = res.data || res;
      if (data.error_num !== 0) {
        throw new Error(data.msg || '保存自定义底图失败');
      }
      this.overlayTestCustomBaseSaved = true;
      return true;
    },
    async uploadOverlayCustomBaseFile(file, dataUrl = '') {
      if (!file) return false;
      const username = localStorage.getItem('userId');
      if (!username) return false;
      const fd = new FormData();
      fd.append('username', username);
      fd.append('cid', String(this.cid));
      fd.append('base_file', file);
      if (dataUrl && String(dataUrl).trim()) {
        fd.append('base_image', String(dataUrl).trim());
      }
      const res = await card_save_overlay_custom_base_image_file(fd);
      const data = res.data || res;
      if (data.error_num !== 0) {
        throw new Error(data.msg || '保存自定义底图失败');
      }
      this.overlayTestCustomBaseSaved = true;
      return true;
    },
    onOverlayBaseFileChange(e) {
      const file = e.target?.files?.[0];
      if (!file || !file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const normalized = await this.normalizeOverlayBaseDataUrl(reader.result || '');
          this.overlayTestCustomBaseDataUrl = normalized || '';
          this.overlayTestBaseSource = 'custom';
          this.overlayTestCustomBaseSaved = false;
          try {
            await this.uploadOverlayCustomBaseFile(file, this.overlayTestCustomBaseDataUrl || '');
          } catch (saveErr) {
            this.$message.warning(`底图已加载，但服务器暂存失败：${saveErr?.message || saveErr}`);
          }
          this.persistOverlaySession();
        } catch (err) {
          this.overlayTestCustomBaseDataUrl = reader.result || '';
          this.overlayTestBaseSource = 'custom';
          this.overlayTestCustomBaseSaved = false;
          this.persistOverlaySession();
        }
      };
      reader.readAsDataURL(file);
      e.target.value = '';
    },
    markPasteOverlayBase() {
      this.overlayTestPasteTarget = 'base';
      this.$message.info('请按 Ctrl+V 粘贴底图');
    },
    async rebuildOverlayPreviewAlpha() {
      const src = this.overlayTestLayerDataUrl;
      if (!src) {
        this.overlayTestLayerPreviewDataUrl = '';
        return;
      }
      const alpha = Math.max(0, Math.min(100, Number(this.overlayTestContentOpacity || 0))) / 100;
      const img = new Image();
      img.crossOrigin = 'anonymous';
      await new Promise((resolve) => {
        img.onload = resolve;
        img.onerror = resolve;
        img.src = src;
      });
      if (!img.width || !img.height) {
        this.overlayTestLayerPreviewDataUrl = src;
        return;
      }
      const cvs = document.createElement('canvas');
      cvs.width = img.width;
      cvs.height = img.height;
      const ctx = cvs.getContext('2d');
      ctx.drawImage(img, 0, 0);
      const im = ctx.getImageData(0, 0, cvs.width, cvs.height);
      const d = im.data;
      const threshold = 240;
      for (let i = 0; i < d.length; i += 4) {
        const r = d[i], g = d[i + 1], b = d[i + 2], a = d[i + 3];
        const isWhite = (r >= threshold && g >= threshold && b >= threshold);
        if (isWhite) {
          d[i + 3] = 0;
        } else {
          d[i + 3] = Math.round(a * alpha);
        }
      }
      ctx.putImageData(im, 0, 0);
      this.overlayTestLayerPreviewDataUrl = cvs.toDataURL('image/png');
      this.persistOverlaySession();
    },
    triggerOverlayIterateReferenceUpload() {
      this.$refs.overlayIterateRefFileInput?.click();
    },
    onOverlayIterateReferenceFileChange(e) {
      const file = e.target?.files?.[0];
      if (!file || !file.type.startsWith('image/')) return;
      const reader = new FileReader();
      reader.onload = () => {
        this.overlayIterateReferenceDataUrl = reader.result || '';
      };
      reader.readAsDataURL(file);
      e.target.value = '';
    },
    onOverlayIterateRegionMouseDown(e) {
      if (e.button !== 0) return;
      const img = this.$refs.overlayIterateImg;
      if (!img) return;
      const p = this._iterateNormFromEvent(e, img);
      this.overlayIterateRegionDragging = true;
      this.overlayIterateRegionStart = p;
      this.overlayIterateRegionCurrent = p;
      document.addEventListener('mousemove', this._boundOverlayIterateMove);
      document.addEventListener('mouseup', this._boundOverlayIterateUp);
    },
    onOverlayIterateRegionMouseMove(e) {
      const img = this.$refs.overlayIterateImg;
      if (!img || !this.overlayIterateRegionDragging) return;
      this.overlayIterateRegionCurrent = this._iterateNormFromEvent(e, img);
    },
    onOverlayIterateRegionMouseUp(e) {
      document.removeEventListener('mousemove', this._boundOverlayIterateMove);
      document.removeEventListener('mouseup', this._boundOverlayIterateUp);
      const img = this.$refs.overlayIterateImg;
      const start = this.overlayIterateRegionStart;
      this.overlayIterateRegionDragging = false;
      this.overlayIterateRegionStart = null;
      this.overlayIterateRegionCurrent = null;
      if (!img || !start) return;
      const end = this._iterateNormFromEvent(e, img);
      const x = Math.min(start.x, end.x);
      const y = Math.min(start.y, end.y);
      const w = Math.abs(end.x - start.x);
      const h = Math.abs(end.y - start.y);
      if (w < 0.015 || h < 0.015) {
        this.overlayIterateEditRegionNorm = null;
        return;
      }
      this.overlayIterateEditRegionNorm = { x, y, w, h };
    },
    async submitOverlayIterate() {
      if (!this.overlayTestLayerDataUrl) return;
      this._pushOverlayHistory(this.overlayTestLayerDataUrl, this.overlayTestSourceBoxNorm);
      this.overlayIterateSubmitting = true;
      try {
        const username = localStorage.getItem('userId');
        if (!username) return;
        // 先快照一次当前覆盖层，避免提交后二次状态切换导致历史丢失观感
        this._pushOverlayHistory(this.overlayTestLayerDataUrl, this.overlayTestSourceBoxNorm);
        const res = await card_iterate_overlay_test_layer({
          username,
          cid: this.cid,
          overlay_image: this.overlayTestLayerDataUrl,
          revision_instruction: (this.overlayIterateInstruction || '').trim() || undefined,
          reference_image: this.overlayIterateReferenceDataUrl || undefined,
          image_quality: this.iterateImageQuality || 'normal',
          edit_region: this.overlayIterateEditRegionNorm || undefined,
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg, '覆盖层迭代失败');
          return;
        }
        this.overlayCurrentOp = 'iterate';
        this.overlayPendingSnapshot = {
          layer: this.overlayTestLayerDataUrl,
          preview: this.overlayTestLayerPreviewDataUrl,
          history: [...(this.overlayTestHistory || [])],
          historyIndex: this.overlayTestHistoryIndex,
          source: this.overlayTestSourceBoxNorm ? { ...this.overlayTestSourceBoxNorm } : null,
          target: this.overlayTestTargetBoxNorm ? { ...this.overlayTestTargetBoxNorm } : null,
        };
        this.overlayTopBusy = true;
        this.persistOverlaySession();
        this.overlayTestGenerating = true;
        this.$message.success('已提交后台覆盖层迭代，你可以先去做别的');
        this.pollOverlayTestStatus(false);
      } catch (e) {
        this._showErr30(e?.message || e, '覆盖层迭代失败');
      } finally {
        this.overlayIterateSubmitting = false;
      }
    },
    resetOverlayTestTransform() {
      if (!this.overlayTestSourceBoxNorm) return;
      this.overlayTestTargetBoxNorm = { ...this.overlayTestSourceBoxNorm };
    },
    onDmtOverlayVersionChange() {
      const v = this.dmtOverlayActiveVersion;
      if (v === 'refined' && (this.dmtOverlayRefinedText || '').trim()) {
        this.iterateImageRevisionInstruction = this.dmtOverlayRefinedText;
      } else if ((this.dmtOverlayDraftText || '').trim()) {
        this.iterateImageRevisionInstruction = this.dmtOverlayDraftText;
      }
    },
    /**
     * 流式结束后校正 DMT 输出：【M级·蓝框】前须与模板 99–106 行一致；【T级·紫框】末段「......」后须接 117–120 行再接「---」。
     */
    _normalizeDmtOverlayStreamText(s) {
      let text = String(s || '').replace(/\r\n/g, '\n');
      const markM = '【M级·蓝框】';
      const iM = text.indexOf(markM);
      if (iM < 0) return text;
      if (text.slice(0, iM) !== DMT_OVERLAY_STREAM_HEAD) {
        text = DMT_OVERLAY_STREAM_HEAD + text.slice(iM);
      }
      const dashM = text.match(/\n---(?:\n|$)/);
      const dashIdx = dashM ? dashM.index : -1;
      const body = dashIdx >= 0 ? text.slice(0, dashIdx) : text;
      const tail = dashIdx >= 0 ? text.slice(dashIdx) : '';
      const iT = body.indexOf('【T级·紫框】');
      if (iT < 0) return body + tail;
      const afterT = body.slice(iT);
      let lastDot = -1;
      for (let p = 0; ; ) {
        const f = afterT.indexOf('......\n', p);
        if (f < 0) break;
        lastDot = f;
        p = f + 1;
      }
      if (lastDot < 0) return body + tail;
      const absCut = iT + lastDot + '......\n'.length;
      const rest = body.slice(absCut);
      if (rest === DMT_OVERLAY_STREAM_SUFFIX_AFTER_T) {
        return body + tail;
      }
      return body.slice(0, absCut) + DMT_OVERLAY_STREAM_SUFFIX_AFTER_T + tail;
    },
    /**
     * DMT / 检验优化：流式读 card_dmt_overlay_prompt_stream（Gemini 3.1；流式结束后在前端做结构校正）。
     * @param {{ refine?: boolean, draftInstruction?: string, minLen?: number }}} opts
     * @returns {Promise<string|null>} 成功返回全文，失败 null
     */
    async _streamDmtOverlayPromptRequest(opts = {}) {
      const refine = !!opts.refine;
      const draftInstruction = (opts.draftInstruction || '').trim();
      const minLen = typeof opts.minLen === 'number' ? opts.minLen : (refine ? 40 : 80);
      const username = localStorage.getItem('userId');
      if (!username) {
        this.$message.warning('未登录');
        return null;
      }
      const cardContent = (this.cardInfo && this.cardInfo.content) ? String(this.cardInfo.content) : '';
      const cardTitle = (this.cardInfo && (this.cardInfo.contentTitle || this.cardInfo.title))
        ? String(this.cardInfo.contentTitle || this.cardInfo.title)
        : '';
      const imageDataUrl = 'data:' + (this.imgType || 'image/png') + ';base64,' + this.imgClicked;
      const maxAttempts = 4;
      let lastErr = '';
      for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        this.iterateImageRevisionInstruction = '';
        try {
          const body = {
            username,
            cid: this.cid,
            card_content: cardContent,
            card_title: cardTitle,
            image_data_url: imageDataUrl,
          };
          if (refine) {
            body.refine = true;
            body.draft_instruction = draftInstruction;
          }
          const res = await fetch(`${API_BASE_URL}/api/card_dmt_overlay_prompt_stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          });
          const ct = (res.headers.get('content-type') || '').toLowerCase();
          if (!res.ok) {
            let msg = `HTTP ${res.status}`;
            try {
              if (ct.includes('application/json')) {
                const j = await res.json();
                msg = j.msg || j.detail || msg;
              } else {
                const t = await res.text();
                if (t) msg = t.slice(0, 200);
              }
            } catch (e) {}
            lastErr = msg;
            if (attempt < maxAttempts) {
              await new Promise((r) => setTimeout(r, 900));
              continue;
            }
            this._showErr30(lastErr, refine ? 'DMT 检验优化失败' : 'DMT微版面化失败');
            return null;
          }
          if (!res.body || !res.body.getReader) {
            lastErr = '浏览器不支持流式读取';
            if (attempt < maxAttempts) {
              await new Promise((r) => setTimeout(r, 900));
              continue;
            }
            this._showErr30(lastErr, refine ? 'DMT 检验优化失败' : 'DMT微版面化失败');
            return null;
          }
          const reader = res.body.getReader();
          const decoder = new TextDecoder('utf-8');
          let acc = '';
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            acc += decoder.decode(value, { stream: true });
            this.iterateImageRevisionInstruction = acc;
          }
          acc += decoder.decode();
          let normalized = acc.replace(/\r\n/g, '\n');
          normalized = this._normalizeDmtOverlayStreamText(normalized);
          this.iterateImageRevisionInstruction = normalized;
          const trimmed = normalized.trim();
          if (trimmed.length >= minLen) {
            return trimmed;
          }
          lastErr = refine ? '检验优化内容过短，可能模型未正常返回' : '生成内容过短，可能模型未正常返回';
          if (attempt < maxAttempts) {
            await new Promise((r) => setTimeout(r, 900));
            continue;
          }
          this._showErr30(lastErr, refine ? 'DMT 检验优化失败' : 'DMT微版面化失败');
          return null;
        } catch (e) {
          lastErr = e?.message || String(e);
          if (attempt < maxAttempts) {
            await new Promise((r) => setTimeout(r, 900));
            continue;
          }
          this._showErr30(lastErr, refine ? 'DMT 检验优化失败' : 'DMT微版面化失败');
          return null;
        }
      }
      return null;
    },
    async runDmtMicroLayoutOverlayPrompt() {
      if (!this.iterateOverlayTestMode) return;
      if (!this.imgClicked || this.imgClicked === '') {
        this.$message.warning('当前卡片无附图，无法分析原图');
        return;
      }
      if (this.dmtOverlayPromptStreaming) return;
      this.dmtOverlayPromptStreaming = true;
      this.dmtOverlayRefinePassActive = false;
      this.overlayDmtPromptReady = false;
      this.dmtOverlayDraftText = '';
      this.dmtOverlayRefinedText = '';
      this.dmtOverlayActiveVersion = 'draft';
      try {
        const draft = await this._streamDmtOverlayPromptRequest({ refine: false, minLen: 80 });
        if (!draft) {
          return;
        }
        this.dmtOverlayDraftText = draft;
        this.iterateImageRevisionInstruction = draft;
        this.dmtOverlayActiveVersion = 'draft';
        this.$message.success('初稿已生成（Gemini 3.1）。如需润色可点「检验优化一遍」，或直接编辑后点「生成覆盖层」');
        this.overlayDmtPromptReady = true;
      } finally {
        this.dmtOverlayPromptStreaming = false;
        this.dmtOverlayRefinePassActive = false;
      }
    },
    async runDmtOverlayRefinePrompt() {
      if (!this.iterateOverlayTestMode) return;
      if (!this.imgClicked || this.imgClicked === '') {
        this.$message.warning('当前卡片无附图，无法分析原图');
        return;
      }
      if (this.dmtOverlayPromptStreaming) return;
      const draftInstruction = (
        (this.iterateImageRevisionInstruction || '').trim()
        || (this.dmtOverlayDraftText || '').trim()
      );
      if (draftInstruction.length < 40) {
        this.$message.warning('请先完成「DMT微版面化」或保证下方说明文字至少约 40 字，再检验优化');
        return;
      }
      this.dmtOverlayPromptStreaming = true;
      this.dmtOverlayRefinePassActive = true;
      try {
        const refined = await this._streamDmtOverlayPromptRequest({
          refine: true,
          draftInstruction,
          minLen: 40,
        });
        if (refined) {
          this.dmtOverlayRefinedText = refined;
          this.iterateImageRevisionInstruction = refined;
          this.dmtOverlayActiveVersion = 'refined';
          this.$message.success('检验优化版已生成，可用「选用版本」在初稿与优化稿之间切换');
        } else {
          this.$message.warning('检验优化未成功，可重试；当前仍保留文本框中的内容');
        }
      } finally {
        this.dmtOverlayPromptStreaming = false;
        this.dmtOverlayRefinePassActive = false;
      }
    },
    async generateOverlayTestLayer() {
      const username = localStorage.getItem('userId');
      if (!username) return;
      const dmtGenerated = !!this.overlayDmtPromptReady;
      this.overlayTestGenerating = true;
      this.overlayQaDialogVisible = false;
      this.overlayQaAwaitingSince = 0;
      this.overlayTestLayerPreviewDataUrl = '';
      this.overlayTestSourceBoxNorm = null;
      this.overlayTestTargetBoxNorm = null;
      try {
        const res = await card_generate_overlay_test_layer({
          username,
          cid: this.cid,
          revision_instruction: (this.iterateImageRevisionInstruction || '').trim() || undefined,
          reference_image: this.iterateImageReferenceDataUrl || undefined,
          image_quality: this.iterateImageQuality || 'normal',
          dmt_generated: dmtGenerated,
          d_label_start: this.overlayManualDLabelStart || 1,
          // 生成阶段固定用「当前卡片图」作为底图，避免影响覆盖层自身的坐标/外观。
          base_source: 'current',
        });
        // DMT 触发只消费一次，避免后续手填生成误走该分支
        this.overlayDmtPromptReady = false;
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg, '生成覆盖层失败');
          return;
        }
        this.overlayCurrentOp = 'generate';
        this.overlayPendingSnapshot = null;
        this.overlayTopBusy = true;
        this.persistOverlaySession();
        this.$message.success('已提交后台生成，你可以先去做别的操作');
        this.pollOverlayTestStatus(false);
      } catch (e) {
        this._showErr30(e?.message || e, '生成覆盖层失败');
      } finally {
        if (!this.overlayTestJobRunning) this.overlayTestGenerating = false;
      }
    },
    _currentOverlayBaseImgEl() {
      if (this.overlayQaDialogVisible && this.$refs.overlayQaBaseImg) return this.$refs.overlayQaBaseImg;
      if (this.$refs.overlayTestBaseImg) return this.$refs.overlayTestBaseImg;
      if (this.$refs.overlayQaBaseImg) return this.$refs.overlayQaBaseImg;
      return null;
    },
    _normPointFromOverlayEvent(e, imgEl = null) {
      const img = imgEl || this._currentOverlayBaseImgEl();
      if (!img) return { x: 0, y: 0 };
      const r = img.getBoundingClientRect();
      if (r.width <= 0 || r.height <= 0) return { x: 0, y: 0 };
      return {
        x: (e.clientX - r.left) / r.width,
        y: (e.clientY - r.top) / r.height,
      };
    },
    onOverlayTestMouseDown(e) {
      if (!this.overlayTestTargetBoxNorm) return;
      const baseImgEl = this._currentOverlayBaseImgEl();
      if (!baseImgEl) return;
      const t = e.target;
      let handle = 'move';
      if (t && t.dataset && t.dataset.handle) {
        handle = t.dataset.handle;
      }
      const p = this._normPointFromOverlayEvent(e, baseImgEl);
      this.overlayTestDrag.active = true;
      this.overlayTestDrag.handle = handle;
      this.overlayTestDrag.start = p;
      this.overlayTestDrag.startBox = { ...this.overlayTestTargetBoxNorm };
      this.overlayTestDrag.baseImgEl = baseImgEl;
      document.addEventListener('mousemove', this._boundOverlayTestMove);
      document.addEventListener('mouseup', this._boundOverlayTestUp);
    },
    onOverlayTestMouseMove(e) {
      if (!this.overlayTestDrag.active || !this.overlayTestDrag.startBox) return;
      const p = this._normPointFromOverlayEvent(e, this.overlayTestDrag.baseImgEl);
      const dx = p.x - this.overlayTestDrag.start.x;
      const dy = p.y - this.overlayTestDrag.start.y;
      const b0 = this.overlayTestDrag.startBox;
      let x = b0.x;
      let y = b0.y;
      let w = b0.w;
      let h = b0.h;
      const handle = this.overlayTestDrag.handle;
      if (handle === 'move') {
        x = b0.x + dx;
        y = b0.y + dy;
      } else if (handle === 'left') {
        x = b0.x + dx;
        w = b0.w - dx;
      } else if (handle === 'right') {
        w = b0.w + dx;
      } else if (handle === 'top') {
        y = b0.y + dy;
        h = b0.h - dy;
      } else if (handle === 'bottom') {
        h = b0.h + dy;
      }
      // 允许覆盖层在底图四周额外可拖拽/拉伸约 5%（便于微调对齐）
      const PAD = 0.05;
      const MIN = 0.01;
      const MAX = 1 + PAD * 2;
      w = Math.max(MIN, Math.min(MAX, w));
      h = Math.max(MIN, Math.min(MAX, h));
      x = Math.max(-PAD, Math.min(1 - w + PAD, x));
      y = Math.max(-PAD, Math.min(1 - h + PAD, y));
      this.overlayTestTargetBoxNorm = { x, y, w, h };
    },
    onOverlayTestMouseUp() {
      this._teardownOverlayTestDrag();
    },
    openOverlayQaDialogForDebug() {
      if (!this.overlayTestLayerDataUrl || !this.overlayTestBaseDisplaySrc) {
        this.$message.warning('请先准备底图与覆盖层');
        return;
      }
      if (!this.overlayTestSourceBoxNorm || this.overlayTestSourceBoxNorm.w <= 0 || this.overlayTestSourceBoxNorm.h <= 0) {
        this.overlayTestSourceBoxNorm = { x: 0, y: 0, w: 1, h: 1 };
      }
      if (!this.overlayTestTargetBoxNorm || this.overlayTestTargetBoxNorm.w <= 0 || this.overlayTestTargetBoxNorm.h <= 0) {
        this.overlayTestTargetBoxNorm = { ...this.overlayTestSourceBoxNorm };
      }
      this.overlayQaDialogVisible = true;
    },
    async _loadImageElement(src) {
      const s = String(src || '').trim();
      if (!s) return null;
      const img = new Image();
      img.crossOrigin = 'anonymous';
      await new Promise((resolve) => {
        img.onload = resolve;
        img.onerror = resolve;
        img.src = s;
      });
      if (!img.width || !img.height) return null;
      return img;
    },
    async buildOverlayQaCompositeDataUrl() {
      const baseSrc = this.overlayTestBaseDisplaySrc;
      const overlaySrc = this.overlayTestLayerPreviewDataUrl || this.overlayTestLayerDataUrl;
      const baseImg = await this._loadImageElement(baseSrc);
      const overlayImg = await this._loadImageElement(overlaySrc);
      if (!baseImg || !overlayImg) return '';
      const src = this.overlayTestSourceBoxNorm;
      const dst = this.overlayTestTargetBoxNorm;
      if (!src || !dst || src.w <= 0 || src.h <= 0) return '';
      const cvs = document.createElement('canvas');
      cvs.width = baseImg.width;
      cvs.height = baseImg.height;
      const ctx = cvs.getContext('2d');
      ctx.drawImage(baseImg, 0, 0, cvs.width, cvs.height);
      const sx = dst.w / src.w;
      const sy = dst.h / src.h;
      const drawX = (dst.x - src.x * sx) * cvs.width;
      const drawY = (dst.y - src.y * sy) * cvs.height;
      const drawW = sx * cvs.width;
      const drawH = sy * cvs.height;
      ctx.drawImage(overlayImg, drawX, drawY, drawW, drawH);
      return cvs.toDataURL('image/png');
    },
    async submitOverlayQaComposite() {
      if (this.overlayQaSubmitting) return;
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.overlayQaSubmitting = true;
      try {
        this.overlayQaSkipRequested = false;
        const merged = await this.buildOverlayQaCompositeDataUrl();
        if (!merged) {
          this.$message.warning('叠图生成失败，请重试');
          return;
        }
        const res = await card_overlay_submit_qa_composite({
          username,
          cid: this.cid,
          image: merged,
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg, '提交对齐图失败');
          return;
        }
        this.overlayQaDialogVisible = false;
        this.$message.success('已提交对齐图，后台继续执行质检');
      } catch (e) {
        this._showErr30(e?.message || e, '提交对齐图失败');
      } finally {
        this.overlayQaSubmitting = false;
      }
    },
    async skipOverlayQaComposite() {
      if (this.overlayQaSubmitting) return;
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.overlayQaSubmitting = true;
      this.overlayQaSkipRequested = true;
      try {
        const res = await card_overlay_skip_qa_composite({
          username,
          cid: this.cid,
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg, '取消对齐失败');
          this.overlayQaSkipRequested = false;
          return;
        }
        this.overlayQaDialogVisible = false;
        this.$message.info('已取消对齐，回退原图继续质检');
      } catch (e) {
        this.overlayQaSkipRequested = false;
        this._showErr30(e?.message || e, '取消对齐失败');
      } finally {
        this.overlayQaSubmitting = false;
      }
    },
    async applyOverlayTestLayer() {
      const username = localStorage.getItem('userId');
      if (!username || !this.overlayTestLayerDataUrl || !this.overlayTestSourceBoxNorm || !this.overlayTestTargetBoxNorm) return;
      if (this.overlayTestBaseSource === 'custom' && !this.overlayTestCustomBaseDataUrl) {
        this.$message.warning('请先上传或粘贴自定义底图');
        return;
      }
      this.overlayTestApplying = true;
      try {
        let applyBaseSource = this.overlayTestBaseSource || 'current';
        if (applyBaseSource === 'custom') {
          // 应用阶段不再重复暂存，直接使用已保存的 custom base 文件
          applyBaseSource = 'custom_saved';
        }
        const payload = {
          username,
          cid: this.cid,
          overlay_image: this.overlayTestLayerDataUrl,
          base_source: applyBaseSource,
          source_bbox: this.overlayTestSourceBoxNorm,
          target_bbox: this.overlayTestTargetBoxNorm,
          keep_white_regions: (this.overlayKeepWhiteRegions || []).length ? this.overlayKeepWhiteRegions : undefined,
          white_threshold: 240,
          overlay_alpha: Math.max(0, Math.min(100, Number(this.overlayTestContentOpacity || 0))) / 100,
        };
        const res = await card_apply_overlay_test_layer(payload);
        const data = res.data || res;
        if (data.error_num !== 0) {
          this._showErr30(data.msg, '应用覆盖层失败');
          return;
        }
        this.$message.success('覆盖层已应用到卡片图');
        this.iterateImageDialogVisible = false;
        this.refetchCardImage();
      } catch (e) {
        this._showErr30(e?.message || e, '应用覆盖层失败');
      } finally {
        this.overlayTestApplying = false;
      }
    },
    onIterateDialogPaste(e) {
      if (!this.iterateImageDialogVisible) return;
      const items = e.clipboardData?.items;
      if (!items) return;
      for (let i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image/') === 0) {
          e.preventDefault();
          e.stopPropagation();
          const file = items[i].getAsFile();
          if (!file) return;
          const reader = new FileReader();
          reader.onload = async () => {
            const d = reader.result || '';
            if (this.iterateOverlayTestMode) {
              const focusLeft = this._isFocusedInInputRef('iterateLeftInstructionInput');
              const focusRight = this._isFocusedInInputRef('overlayRightInstructionInput');
              if (this.overlayTestPasteTarget === 'base') {
                try {
                  this.overlayTestCustomBaseDataUrl = await this.normalizeOverlayBaseDataUrl(d);
                } catch (err) {
                  this.overlayTestCustomBaseDataUrl = d;
                }
                this.overlayTestBaseSource = 'custom';
                this.overlayTestCustomBaseSaved = false;
                try {
                  if (file && file.type.indexOf('image/') === 0) {
                    await this.uploadOverlayCustomBaseFile(file, this.overlayTestCustomBaseDataUrl || '');
                  } else {
                    await this.uploadOverlayCustomBaseIfNeeded(true);
                  }
                } catch (saveErr) {
                  this.$message.warning(`底图已粘贴，但服务器暂存失败：${saveErr?.message || saveErr}`);
                }
                this.overlayTestPasteTarget = 'reference';
                this.$message.success('底图已粘贴');
              } else if (focusLeft) {
                this.iterateImageReferenceFile = null;
                this.iterateImageReferenceDataUrl = d;
                this.$message.success('已粘贴到左侧生成覆盖层参考图');
              } else if (focusRight) {
                this.overlayIterateReferenceDataUrl = d;
                this.$message.success('已粘贴到右侧迭代覆盖层参考图');
              } else {
                this.iterateImageReferenceFile = null;
                this.iterateImageReferenceDataUrl = d;
              }
            } else {
              this.iterateImageReferenceFile = null;
              this.iterateImageReferenceDataUrl = d;
            }
          };
          reader.readAsDataURL(file);
          return;
        }
      }
    },
    async requestRevertIterateCardImage() {
      if (this.isCardImageGenerating || !this.imgClicked || this.imgClicked === '') return;
      const username = localStorage.getItem('userId');
      if (!username) return;
      try {
        await ElMessageBox.confirm(
          '将当前卡片图片恢复为上一次「迭代图」之前的版本？（仅保留一步回退；未做过迭代则无备份）',
          '图回退',
          { type: 'warning', confirmButtonText: '确定回退', cancelButtonText: '取消' }
        );
      } catch {
        return;
      }
      try {
        const res = await card_revert_iterate_card_image({ username, cid: this.cid });
        const data = res.data || res;
        if (data.error_num === 1 && data.generating) {
          this.$message.warning('该卡片正在生图中，请稍后再试');
          return;
        }
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '图回退失败');
          return;
        }
        this.$message.success('已恢复为迭代前图片');
        this.refetchCardImage();
      } catch (e) {
        this.$message.error('图回退请求失败：' + (e.message || e));
      }
    },
    async submitIterateCardImage() {
      const username = localStorage.getItem('userId');
      if (!username) return;
      if (this.iterateOverlayTestMode) {
        this.$message.warning('覆盖层模式请使用「应用覆盖层」按钮，不走常规迭代提交。');
        return;
      }
      this.iterateImageSubmitting = true;
      const instruction = (this.iterateImageRevisionInstruction || '').trim();
      const referenceImage = this.iterateImageReferenceDataUrl || undefined;
      try {
        const payload = {
          username,
          cid: this.cid,
          revision_instruction: instruction || undefined,
          reference_image: referenceImage,
          image_quality: this.iterateImageQuality || 'normal',
          image_provider: this.iterateImageProvider || 'gpt',
          edit_region: this.iterateEditRegionNorm || undefined,
        };
        if (this.iterateEditRegionNorm) {
          payload.crop_iterate_include_full_image = this.iterateCropIncludeFullImage;
        }
        const res = await card_iterate_card_image(payload);
        const data = res.data || res;
        if (data.error_num === 1 && data.generating) {
          this.$message.warning('该卡片正在生图中，请稍等');
          return;
        }
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '发起迭代生图失败');
          return;
        }
        this.iterateImageDialogVisible = false;
        this.iterateImageRevisionInstruction = '';
        this.overlayDmtPromptReady = false;
        this.clearIterateReferenceImage();
        if ((data.generating_cids || []).includes(this.cid)) {
          this.$emit('single-card-image-requested', this.cid);
        }
        this.$message.success(instruction || referenceImage ? '已按您的要求加入迭代生图队列' : '已加入迭代生图队列');
      } catch (e) {
        this.$message.error('迭代生图请求失败：' + (e.message || e));
      } finally {
        this.iterateImageSubmitting = false;
      }
    },
    // 图无损理解反馈迭代：拉取 CI 分析列表，无则提示，一条则直接迭代，多条则弹窗选择
    async openCiFeedbackDialog() {
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.isCiFeedbackLoading = true;
      this.ciAnalysesList = [];
      this.selectedCiAnalysisId = '';
      this.ciFeedbackDialogVisible = false;
      try {
        const res = await card_list_ci_analyses_for_feedback({ username });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '获取图片理解分析列表失败');
          return;
        }
        const list = data.analyses || [];
        if (list.length === 0) {
          this.$message.warning('暂无已完成的图片理解分析，请先在「连续多图理解」中完成分析');
          return;
        }
        this.ciAnalysesList = list;
        if (list.length === 1) {
          this.selectedCiAnalysisId = list[0].analysis_id;
          await this.doCiFeedbackIterate();
          return;
        }
        this.selectedCiAnalysisId = list[0].analysis_id;
        this.ciFeedbackDialogVisible = true;
      } catch (e) {
        this.$message.error('请求失败：' + (e.message || e));
      } finally {
        this.isCiFeedbackLoading = false;
      }
    },
    async doCiFeedbackIterate() {
      const username = localStorage.getItem('userId');
      if (!username || !this.selectedCiAnalysisId) return;
      if (this.ciFeedbackStatusClearTimer) {
        clearTimeout(this.ciFeedbackStatusClearTimer);
        this.ciFeedbackStatusClearTimer = null;
      }
      this.ciFeedbackDialogVisible = false;
      this.ciFeedbackStatus = 'loading';
      this.ciFeedbackStatusMsg = '正在根据图片理解迭代正文…';
      this.isCiFeedbackLoading = true;
      try {
        const res = await card_ci_feedback_iterate_content({
          username,
          cid: this.cid,
          analysis_id: this.selectedCiAnalysisId
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this.ciFeedbackStatus = 'error';
          this.ciFeedbackStatusMsg = data.msg || '图无损理解反馈迭代失败';
          this.ciFeedbackStatusClearTimer = setTimeout(() => {
            this.ciFeedbackStatus = '';
            this.ciFeedbackStatusMsg = '';
            this.ciFeedbackStatusClearTimer = null;
          }, 5000);
          return;
        }
        if (data.content !== undefined) this.cardInfo.content = data.content;
        if (data.lastContent !== undefined) this.cardInfo.lastContent = data.lastContent;
        this.ciFeedbackStatus = 'success';
        this.ciFeedbackStatusMsg = '迭代完成';
        this.ciFeedbackStatusClearTimer = setTimeout(() => {
          this.ciFeedbackStatus = '';
          this.ciFeedbackStatusMsg = '';
          this.ciFeedbackStatusClearTimer = null;
        }, 4000);
      } catch (e) {
        this.ciFeedbackStatus = 'error';
        this.ciFeedbackStatusMsg = (e.message || e) + '';
      } finally {
        this.isCiFeedbackLoading = false;
      }
    },
    ciAnalysisItemShort(a) {
      const files = (a.files || []).join(', ') || a.analysis_id || '';
      const maxLen = 42;
      if (files.length <= maxLen) return files;
      return files.slice(0, maxLen - 2) + '…';
    },
    ciAnalysisItemTitle(a) {
      const files = (a.files || []).join(', ') || a.analysis_id || '';
      const time = a.created_at ? ' · ' + a.created_at : '';
      return (a.mode === 'group' ? '多图' : '单图') + ' · ' + files + time;
    },
    formatCiTime(created_at) {
      if (!created_at) return '';
      const s = String(created_at);
      const m = s.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
      return m ? `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}` : s;
    },
    refetchCardImage() {
      const formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      get_card(formData).then(data => {
        const d = data.data || data;
        if (d.img !== undefined) this.imgClicked = d.img || '';
        if (d.img_type !== undefined) this.imgType = d.img_type || '';
        if (this.imgClicked && this.imgClicked !== '') this.$emit('card-has-image', this.cid);
      }).catch(() => {});
    },
    getSingleCard() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('cid', this.cid);
      this.isContentLoading = true;
      get_card(formData).then(data => {
        console.log("getSingleCard", data.content);
        this.isContentLoading = false;
        this.cardInfo = data.content;
        this.imgClicked = data.img;
        this.imgType = data.img_type;
        if (data.img && data.img !== '') this.$emit('card-has-image', this.cid);
        this.cardInfo.username = localStorage.getItem('realName');
        // 新增，重置编辑状态
        this.isEditing = false
        this.currentEditingIndex = -1
        this.currentAIFeedback = null
        
        // 🔥 每次打开卡片时，递增全局z-index并设置当前卡片的z-index
        if (!window.cardDialogZIndexCounter) {
          window.cardDialogZIndexCounter = 25;
        }
        window.cardDialogZIndexCounter += 1;
        this.cardDialogZIndex = window.cardDialogZIndexCounter;
        
        this.judgeScrollToBottom()
        this.$emit('cardClickLog', this.cardInfo.content, this.cardInfo.score, this.cardInfo.reason, this.cardInfo.keyWords, this.cardInfo.contentTitle, this.cardInfo.cid)
        this.refreshCardHtmlFlag()
        this.crossReorgTab = 'suggest';
        if ((this.cardInfo.content || '').includes('【文档全面交叉梳理建议卡片】')) {
          this.loadCrossReorgIndex({ pollIfRunning: true });
          this.loadKnowledgeConflicts({ pollIfRunning: true });
        } else {
          this.stopCrossReorgPoll();
          this.crossReorgIndex = null;
          this.stopKcPoll();
          this.kcData = null;
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },

    switchCrossReorgSkillsTab() {
      this.crossReorgTab = 'skills';
      this.loadCrossReorgIndex({ pollIfRunning: true });
    },
    switchKnowledgeConflictTab() {
      this.crossReorgTab = 'conflicts';
      this.loadKnowledgeConflicts({ pollIfRunning: true });
    },
    stopCrossReorgPoll() {
      if (this.crossReorgPollTimer) {
        clearInterval(this.crossReorgPollTimer);
        this.crossReorgPollTimer = null;
      }
    },
    stopKcPoll() {
      if (this.kcPollTimer) {
        clearInterval(this.kcPollTimer);
        this.kcPollTimer = null;
      }
    },
    isKcItemOpen(id) {
      return !!(this.kcOpenIds && this.kcOpenIds[id]);
    },
    toggleKcItem(id) {
      if (!id) return;
      this.kcOpenIds = { ...this.kcOpenIds, [id]: !this.kcOpenIds[id] };
    },
    kcItemHasDetail(item) {
      if (!item) return false;
      const summary = (item.summary || '').trim();
      const insight = (item.insight || '').trim();
      return !!(item.tension || item.why_not_forced || (insight && insight !== summary));
    },
    loadKnowledgeConflicts({ pollIfRunning = false } = {}) {
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.kcLoading = true;
      knowledge_conflict_get({ username }).then((res) => {
        this.kcLoading = false;
        if (res && res.error_num === 0) {
          this.kcData = res.conflicts || null;
          const st = (this.kcData && this.kcData.status) || '';
          const emptyRunning = !this.kcData && pollIfRunning;
          if (pollIfRunning && (emptyRunning || st === 'running')) {
            this.stopKcPoll();
            this.kcPollTimer = setInterval(() => {
              knowledge_conflict_status({ username }).then((r2) => {
                if (r2 && r2.error_num === 0) {
                  if (r2.conflicts) this.kcData = r2.conflicts;
                  const jobSt = (r2.job && r2.job.status) || '';
                  const st2 = (this.kcData && this.kcData.status) || '';
                  if ((jobSt && jobSt !== 'running') || (st2 && st2 !== 'running' && this.kcData)) {
                    this.stopKcPoll();
                  }
                }
              }).catch(() => {});
            }, 4000);
          }
        }
      }).catch(() => {
        this.kcLoading = false;
      });
    },
    setKcFeedback(item, status) {
      if (!item || !item.id || this.kcSaving) return;
      const username = localStorage.getItem('userId');
      this.kcSaving = true;
      knowledge_conflict_feedback({
        username,
        id: item.id,
        user_status: status,
        user_note: item.user_note || '',
      }).then((res) => {
        this.kcSaving = false;
        if (res && res.error_num === 0 && res.item) {
          Object.assign(item, res.item);
        } else {
          this.$message.error((res && res.msg) || '保存失败');
        }
      }).catch(() => {
        this.kcSaving = false;
        this.$message.error('保存失败');
      });
    },
    onKcNoteChange(item, ev) {
      if (!item || !item.id) return;
      const note = (ev && ev.target && ev.target.value) || '';
      item.user_note = note;
      const username = localStorage.getItem('userId');
      knowledge_conflict_feedback({
        username,
        id: item.id,
        user_status: item.user_status || 'pending',
        user_note: note,
      }).then((res) => {
        if (res && res.error_num === 0 && res.item) Object.assign(item, res.item);
      }).catch(() => {});
    },
    loadCrossReorgIndex({ pollIfRunning = false } = {}) {
      const username = localStorage.getItem('userId');
      if (!username) return;
      this.crossReorgLoading = true;
      cross_reorganize_index({ username }).then((res) => {
        this.crossReorgLoading = false;
        if (res && res.error_num === 0) {
          this.crossReorgIndex = res.index_cross || null;
          const st = (this.crossReorgIndex && this.crossReorgIndex.status) || '';
          if (pollIfRunning && (st === 'running' || !this.crossReorgIndex)) {
            this.stopCrossReorgPoll();
            this.crossReorgPollTimer = setInterval(() => {
              cross_reorganize_skills_status({ username }).then((r2) => {
                if (r2 && r2.error_num === 0 && r2.index_cross) {
                  this.crossReorgIndex = r2.index_cross;
                  const st2 = r2.index_cross.status || '';
                  if (st2 && st2 !== 'running') this.stopCrossReorgPoll();
                }
              }).catch(() => {});
            }, 4000);
          }
        }
      }).catch(() => {
        this.crossReorgLoading = false;
      });
    },
    openCrossSkillViewer(name, title) {
      const username = localStorage.getItem('userId');
      cross_reorganize_skill_get({ username, name }).then((res) => {
        if (res && res.error_num === 0) {
          this.crossSkillViewerTitle = title || name;
          this.crossSkillViewerName = name;
          this.crossSkillViewerRaw = res.raw || '';
          this.crossSkillViewerFrontmatter = res.frontmatter || null;
          this.crossSkillViewMode = 'preview';
          this.crossSkillViewerVisible = true;
        } else {
          this.$message.error((res && res.msg) || '无法打开 Skill');
        }
      }).catch((e) => {
        this.$message.error(e.message || '无法打开 Skill');
      });
    },
    closeCrossSkillViewer() {
      this.crossSkillViewerVisible = false;
      this.crossSkillViewerRaw = '';
      this.crossSkillViewerFrontmatter = null;
      this.crossSkillViewMode = 'preview';
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
        if (typeof raw === 'object') return;
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
      return escaped
        .replace(/\s*(Use\s+when)\b/gi, '<br><span class="skill-desc-mark">$1</span>')
        .replace(/\s*(NOT\s+for)\b/gi, '<br><span class="skill-desc-mark">$1</span>');
    },
    parseFrontmatterRowsFromText(text) {
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
          const cont = [value];
          while (i < lines.length) {
            const next = lines[i];
            if (/^[A-Za-z0-9_-]+\s*:/.test(next)) break;
            if (/^\s*$/.test(next)) break;
            if (!/^\s+/.test(next)) break;
            cont.push(next.replace(/^\s+/, ''));
            i++;
          }
          value = cont.join(' ').replace(/\s+/g, ' ').trim();
        }
        if (value) rows.push({ key, value });
      }
      return rows;
    },

    hideCardDialog() {
      // [TODO] 这里提到有bug，有时关闭卡片关不掉，可能是双击误触？？连续双击？？暂时先注释掉else部分
      // if(this.doubleClick === false) {
        this.stopSpeech()
        this.stopCrossReorgPoll();
        this.stopKcPoll();
        this.isCardDialogVisible = false;
        this.cardMediaViewMode = 'image';
        this.cardHtmlMenuVisible = false;
        this.showingSuggestions = false;  // 让卡片右栏打开的红蓝建议也关掉
        this.showLastContentNormal = false;   // 单卡迭代回退显示上一版，标志重置
        this.firstClickAftDrag = false; // 重置拖拽后的第一次点击(取消高亮)标记
        if (!this.isCiFeedbackLoading) {
          if (this.ciFeedbackStatusClearTimer) {
            clearTimeout(this.ciFeedbackStatusClearTimer);
            this.ciFeedbackStatusClearTimer = null;
          }
          this.ciFeedbackStatus = '';
          this.ciFeedbackStatusMsg = '';
        }
        
        if (this.shouldBeFront === true) {
          this.shouldBeFront = false
          let formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          formData.append('cid', this.cid);
          set_card(formData).then(data => {
            this.$emit('updateOrder');
          }).catch(error => {
            console.error("An error occurred:", error); // 错误处理
          });
        }
      // } else {
      //   this.$message.error('您操作过快，请您稍等2s，再关闭卡片');
      // }
    },
    editContent() {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限编辑卡片');
      //   return
      // }
      if(!this.hasCardEditPermission()) {
        this.$message.error('您没有权限编辑此卡片');
        return
      }

      if(this.isContentLoading === true) {
        this.$message.warning('正在加载完整卡片内容，请您稍等几秒钟');
        return;
      }

      this.showEditDialog = true;
      this.editForm.contentTitle = this.cardInfo.contentTitle
      this.editForm.content = this.cardInfo.content;
      this.editForm.keyWords = this.cardInfo.keyWords
    },
    deleteCard() {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限删除卡片');
      //   return
      // }
      if(!this.hasCardEditPermission()) {
        this.$message.error('您没有权限删除此卡片');
        return
      }

      // 🔥 添加确认弹框
      this.$confirm('确定要删除这张卡片吗？此操作不可恢复。', '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        deleteChoosedCard(this.cid).then(response => { 
          this.$emit('deleteCard');
          this.$message.success('删除成功');
        }).catch(error => {
          this.$message.error('删除失败');
          console.log('error', error.message);
        });

        this.showEditDialog = false;
        this.isCardDialogVisible = false;
      }).catch(() => {
        // 用户取消删除，不做任何操作
      });
    },
    cancelDialog() {
      this.showEditDialog = false;
      // this.isCardDialogVisible = false;
    },
    saveContent() {
      this.shouldBeFront = true

      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('newContent', this.editForm.content);
      formData.append('newContentTitle', this.editForm.contentTitle);
      formData.append('newKeyWords', this.editForm.keyWords);
      chageContent(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('保存成功');
          this.$emit('updateOrDeleteCard');
        }
        else {
          alert("error!");
        }
      }).catch(error => {
        alert("error!2");
        console.log('error', error.message);
      })

      this.cardInfo.content = this.editForm.content;
      this.cardInfo.contentTitle = this.editForm.contentTitle
      this.cardInfo.keyWords = this.editForm.keyWords
      this.showEditDialog = false;
      // this.isCardDialogVisible = false;
      // this.$router.go(0);
    },

    changeTextLen(length) {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }
      
      let formData = new FormData();
      formData.append('cid', this.cid);
      formData.append('content', this.cardInfo.content);
      formData.append('tarLen', length);
      formData.append('username', localStorage.getItem('userId'));
      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', this.subSceneName);
      formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递
      this.$emit("cardTextNum")
      changeText(formData).then(response => {
        if (response.error_num === 0) {
          let finalContent=response.finalContent;
          let cid = response.cardId
          this.$emit("cardTextNumOver")
          this.waitDecodedResult(cid, finalContent)
        }
        else {
          this.$emit("cardTextNumOver")
          alert("error!");
        }
      }).catch(error => {
        alert("error!2");
        console.log('error', error.message);
      })
    },
    async waitDecodedResult(cid, finalContent) {
      // 等待 modelHL 异步函数执行完成，并将结果赋值给 decodedResult
      let decodedResult = await modelHL(finalContent); 
      console.log("红蓝微调评测模型打分：", decodedResult);

      if (decodedResult === "fail") {
        this.$message.error('卡片保存成功，但红蓝微调评测模型打分失败');
        this.$emit("cardTextNumOver")
      } else {
        let formDataSFT = new FormData();
        formDataSFT.append('content', decodedResult);
        formDataSFT.append('cid', cid);
        card_evalSFT(formDataSFT).then(responseSFT => {
          if (responseSFT.error_num === 0) {
            this.$message.success('字数改写卡片保存成功！');
          } else {
            this.$message.error('字数改写卡片保存成功，但红蓝微调评测模型打分保存失败');
          }
          this.$emit("cardTextNumOver")
        });
      }
    },

    textTo1500() {
      this.changeTextLen(1500);
    },
    textTo500() {
      this.changeTextLen(500);
    },
    textTo1000() {
      this.changeTextLen(1000);
    },
  }
};
</script>

<style scoped>
.notebook-card {
  height: 200px;
  width: 290px;
  border-radius: 10px;
  overflow: hidden;

  padding: 20px;
  background-color: #fff;
  margin: 10px;

  position: relative;
  transition: transform 0.3s ease, box-shadow 0.3s ease;
  /* position: absolute; */

  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1), 0 6px 20px rgba(0, 0, 0, 0.2);
}

/* 🔥 抬起效果：当卡片与勾选的卡片或文档相关时 */
.notebook-card.card-raised {
  transform: translateY(-4px);
  box-shadow: 0 8px 16px rgba(0, 0, 0, 0.15), 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 10;
}

.card-top {
  display: flex;
  position: relative;
  width: 100%;
  height: 58%;
}

/* 🔥 深色永久卡片：调整card-top高度，为card-content留更多空间 */
.notebook-card.deep-permanent-card .card-top {
  height: 44%;
}

.card-top-left {
  width: 50%;
}

.card-top-right {
  width: 50%;
}

.card-top-from {
  width: 100%;
}

.card-top-from-img {
  background-image: url('@/assets/img/cardwindow/response.png');
  background-size: contain;
  background-repeat: no-repeat;
  vertical-align: middle;
  height: 20.8px;
  width: 20.8px;
  border-radius: 3px;
  float: left;
}

/* 生图时：圆形箭头（刷新）转圈图标，与原文图标同尺寸，完成后恢复原文图标 */
.card-image-spinner-wrap {
  display: inline-block;
  float: left;
  width: 20.8px;
  height: 20.8px;
  vertical-align: middle;
  color: #666;
}
.card-image-spinner-svg {
  display: block;
  width: 20.8px;
  height: 20.8px;
  animation: card-image-spin 0.9s linear infinite;
}
.card-image-spinner-svg-overlay {
  color: #8b5a2b;
}
@keyframes card-image-spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* HTML 生成中：三角形（箭头感）转圈，与生图圆形箭头区分 */
.card-html-spinner-wrap {
  display: inline-block;
  float: left;
  width: 20.8px;
  height: 20.8px;
  vertical-align: middle;
  color: #3a6ea5;
}
.card-html-spinner-svg {
  display: block;
  width: 20.8px;
  height: 20.8px;
  animation: card-image-spin 0.85s linear infinite;
}

/* 🔥 深色永久卡片：图标filter（将蓝色转为白色） */
.notebook-card.deep-permanent-card .card-top-from-img {
  filter: hue-rotate(160deg) saturate(0.1) brightness(1.5) drop-shadow(0 0 1px rgba(254, 254, 254, 0.8));
}

/* 共生卡片：左上角图标紫色（与 .card-top-from-img 同元素，单类覆盖 filter） */
.purple-icon {
  filter: hue-rotate(75deg) drop-shadow(0 0 1px rgba(128, 0, 128, 0.8));  /* 将蓝色转为紫色，并让其看起来更粗 */
}

/* 已有附图的卡片：左上角图标对比更强（颜色更饱和、线条更粗感）+ 绿色发光 */
.notebook-card .card-top-from-img.card-has-image-icon {
  filter: brightness(0.68) sepia(1) hue-rotate(128deg) saturate(3.2) drop-shadow(0 0 1.5px rgba(5, 150, 105, 0.95)) drop-shadow(0 0 4px rgba(16, 185, 129, 0.9)) drop-shadow(0 0 9px rgba(52, 211, 153, 0.6));
  opacity: 1;
  transform: scale(1.22);
  box-sizing: border-box;
  border-radius: 4px;
}
/* 深卡：内层绿色光晕（显粗）+ 外层白色光晕 */
.notebook-card.deep-permanent-card .card-top-from-img.card-has-image-icon {
  filter: brightness(0.58) sepia(1) hue-rotate(128deg) saturate(3.5) drop-shadow(0 0 2px rgba(16, 185, 129, 0.95)) drop-shadow(0 0 4px rgba(16, 185, 129, 0.85)) drop-shadow(0 0 6px rgba(255, 255, 255, 0.95)) drop-shadow(0 0 12px rgba(255, 255, 255, 0.8)) drop-shadow(0 0 20px rgba(255, 255, 255, 0.5));
}

.card-top-from-text {
  font-size: 14px;
  margin-left: 10px;
  color: #6eb7ff
}

.intergrowth-card {
  color: purple;
  text-shadow: 0 0 3px rgba(128, 0, 128, 0.3); /* 添加淡紫色阴影 */
  font-weight: bold;
  font-size: 15px;
}

.card-top-title {
  font-size: 19px;
  font-weight: bold;
  color: #3b3b3b;
  margin-bottom: 10px;
  width: 100%;
  word-wrap: break-word;
  border-radius: 8px;
  background-color: #ffffffda;
  position: relative;
  z-index: 1;
  text-shadow: 1px 1px 1px rgba(75, 75, 75, 0.09); /* 添加文字阴影 */
  /* 可选，为内容提供一些内边距 */
  /* padding: 1px;  */
  /* 确保内边距和边框宽度包含在宽度内 */
  /* box-sizing: border-box;  */
}

/* 🔥 深色永久卡片：标题文字保持深色（不反白） */
.notebook-card.deep-permanent-card .card-top-title {
  color: #3b3b3b;  /* 保持原来的深色，不反白 */
}

.card-top-right-button {
  background-size: contain;
  background-repeat: no-repeat;
  vertical-align: middle;
  height: 20.8px;
  width: 20.8px;
  border-radius: 3px;
  float: right;
  right: 0;
}


.card-top-right-button.checked {
  background-image: url('@/assets/img/pin_blue.png');
}

.card-top-right-button:not(.checked) {
  background-image: url('@/assets/img/pin_grey.png');
}

.card-content {
  font-size: 16px;
  color: #666;
  line-height: 1.6;
  overflow: hidden;
  width: 100%;
  word-wrap: break-word;
  height: 40%;
}

/* 🔥 深色永久卡片：内容文字变白亮一点，并调整高度以显示4行 */
.notebook-card.deep-permanent-card .card-content {
  color: #fafafa;
  height: 50% !important; /* 增加高度以容纳4行内容 */
  min-height: 7em; /* 确保至少有4行的空间（line-height: 1.6 × 4行 + 边距 ≈ 7em） */
  margin-top: -5px; /* 上移card-content */
}

.notebook-card.deep-permanent-card .card-content-text {
  color: #fafafa;
  -webkit-line-clamp: 4 !important;
  max-height: 6.4em !important; /* 4行文本的空间（line-height: 1.6 × 4行 = 6.4em） */
}

/* 🔥 深色永久卡片：字数显示变白色 */
.notebook-card.deep-permanent-card .word-count {
  color: white !important;
  text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
}

/* 🔥 深色永久卡片：contentTitle上方一行蓝色标识（自定义 | 根(T)）也反白 */
.notebook-card.deep-permanent-card .card-top-from-text {
  color: white !important;
  text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.5);
}

.card-content-text {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 7;
  margin-bottom: 10px;
  max-height: 9em;
  /* 根据行高计算最大高度，确保有5行文本的空间 */
  position: relative;
  overflow: hidden;
}

.card-content-text::before {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 3em;
  z-index: 1;
}






/* 🔥 预览内容样式：区分关键词、标题、加粗、句子 */
.preview-content {
  line-height: 1.6;
}

.preview-keyword, .preview-heading, .preview-bold, .preview-sentence, .preview-line {
  margin: 3px 0;
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

/* 🔥 标题和加粗在同一行显示 */
.preview-heading-bold-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 3px 0;
  flex-wrap: nowrap;
}

.preview-heading-bold-row .preview-heading-part {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #E6A23C; /* 标题颜色 */
}

.preview-heading-bold-row .preview-bold-part {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #F56C6C; /* 加粗颜色 */
}

.preview-heading-bold-row .preview-heading-part .preview-text {
  font-weight: 600;
}

.preview-heading-bold-row .preview-bold-part .preview-text {
  font-weight: 500;
}

/* 🔥 多个加粗在同一行显示 */
.preview-bold-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 3px 0;
  flex-wrap: nowrap;
}

.preview-bold-row .preview-bold-part {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #F56C6C; /* 加粗颜色 */
}

.preview-bold-row .preview-bold-part .preview-text {
  font-weight: 500;
}

.preview-icon {
  font-size: 14px;
  flex-shrink: 0;
  margin-top: 1px;
  line-height: 1;
}

.preview-label {
  font-size: 12px;
  color: #888;
  font-weight: 500;
  flex-shrink: 0;
}

.preview-text {
  flex: 1;
  word-wrap: break-word;
}

.preview-keyword {
  color: #409EFF;
}

.preview-keyword .preview-text {
  font-weight: 500;
}

.preview-heading {
  color: #E6A23C;
}

.preview-heading .preview-text {
  font-weight: 600;
}

.preview-bold {
  color: #F56C6C;
}

.preview-bold .preview-text {
  font-weight: 500;
}

.preview-sentence {
  color: #606266;
}

.preview-line {
  color: #606266;
}




.card-rate {
  width: 30%;
  display: flex;
  position: absolute;
  bottom: 75px;
  left: 160px;
  z-index: 3;
}

/* 🔥 深色永久卡片：调整card-rate位置，防止溢出 */
.notebook-card.deep-permanent-card .card-rate {
  bottom: 48px; /* 下移，避免溢出到card-top外面 */
}

/* 新增的中间容器，用于垂直排列 card-rate-left 和 card-rate-left2 */
.card-rate-middle {
  display: flex;
  flex-direction: column; /* 垂直排列 */
  justify-content: center; /* 水平居中 */
}

.card-rate-left, .card-rate-left-single {
  display: flex;
  /* 启用 Flexbox */
  justify-content: center;
  /* 水平居中 */
  align-items: center;
  /* 垂直居中 */
  width: 30px;
  height: 20px;
  border-radius: 6px;
  background-color: #911787;
  font-size: 14px;
  font-weight: bold;
  color: #000000;
  transition: filter 0.3s ease;
  cursor: pointer;
}

.card-rate-left-single {
  height: 40px;
}

.card-rate-right {
  display: flex;
  /* 启用 Flexbox */
  justify-content: center;
  /* 水平居中 */
  align-items: center;
  /* 垂直居中 */
  width: 30px;
  height: 40px;
  border-radius: 6px;
  background-color: #c81b1bac;
  font-size: 12px;
  /* font-weight: bold; */
  color: #000000;
  transition: filter 0.3s ease;
  /* 添加过渡效果 */
}

.card-rate-history {
  display: flex;
  justify-content: center;
  align-items: center;
  width: 30px;
  height: 40px;
  border-radius: 6px;
  background-color: #0b0be79f;
  font-size: 12px;
  color: #000000;
  transition: filter 0.3s ease;
  cursor: pointer;
}

.card-rate-right:hover {
  filter: brightness(130%);
  /* 增加亮度 */
}


.card-rate-history:hover {
  filter: brightness(130%);
  /* 增加亮度 */
}

.tooltip {
  position: absolute;
  z-index: 10;
  background-color: #a2b1c1;
  border: 2px solid #72677b;
  padding: 5px;
  border-radius: 9px;
  width: 120px;
  height: 60px;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  /* 启用 Flexbox */
  flex-direction: column;
  /* 设置主轴方向为垂直 */
  align-items: center;
  /* 水平居中子元素 */
}



.historyTip {
  position: absolute;
  z-index: 10;
  background-color: #a2b1c1;
  border: 2px solid #72677b;
  padding: 5px;
  border-radius: 9px;
  width: 50vw;
  height: 60vh;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
  display: flex;
  /* 启用 Flexbox */
  flex-direction: column;
  /* 设置主轴方向为垂直 */
  align-items: center;
  /* 水平居中子元素 */
}

.nav-button {
  width: 60px;
  margin-top: 7px;
  display: flex;
  justify-content: center;

  .el-button {
    font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
    font-size: 14px;
    font-weight: 550;
    color: #6a45c2;
    cursor: pointer;
    transition: background-color 0.5s;
    background-color: #bccfe3;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

    &:hover {
      background-color: #ced8d8;
      box-shadow: 0 4px 8px rgba(106, 106, 106, 0.3);
    }
  }
}

.card-rate-text {
  font-size: 15px;
}

.more-text,
.less-text {
  color: #409eff;
  cursor: pointer;
}

.card-settings {
  position: relative;
  padding-top: 10px;
  bottom: 0px;
  right: 0px;
}

.el-dropdown-link {
  cursor: pointer;
  color: #409eff;
  font-size: 14px;
}

.custom-checkbox {
  cursor: pointer;
  width: 20px;
  /* 设置图片的宽度 */
  height: 20px;
  /* 设置图片的高度 */
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;

}

.custom-checkbox.checked {
  background-image: url('@/assets/img/pin_blue.png');
}

.custom-checkbox:not(.checked) {
  background-image: url('@/assets/img/pin_grey.png');
}



.card-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 25;
  width: 45vw;
  height: 60vh;
  max-width: 100%;

  overflow: scroll;
}

/* 解释精要 HTML 含侧栏 + 核验弹窗，打开时加宽加高；其他卡不受影响 */
.card-dialog.card-dialog--grading-excerpt {
  width: min(960px, 92vw);
  height: min(84vh, 920px);
}

.history-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 23;
  width: 45vw;
  height: 60vh;
  max-width: 100%;

  overflow: scroll;
}

.card-dialog .card-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.history-dialog .history-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.card-dialog h2 {
  margin: 0;
  font-size: 1.2em;
}

.card-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}

.card-dialog .close:hover {
  color: #333;
}

.card-dialog .card-dialog-body {
  margin-top: 10px;
}

.card-dialog p {
  margin: 5px 0;
  white-space: pre-wrap;
}

.card-dialog pre {
  white-space: pre-wrap;
}

.card-merge-info {
  display: flex;
  /* 使用Flexbox布局 */
  align-items: center;
  /* 垂直居中对齐 */
  margin-top: 10px;
  /* 根据需要调整 */
  color: #333;
  /* 文字颜色 */
  font-size: 12px;
  /* 减小字体大小 */
}

.card-merge-info .merge-info-text {
  margin-right: 5px;
  /* 为数字和文字之间添加一些间距 */
  white-space: nowrap;
  /* 防止文本换行 */
}

.model-info-text {
  position: absolute;
  right: 0;        /* 靠右 */
  bottom: 0;      /* 靠下 */
  margin-bottom: 8px;  /* 如果需要在底部留出空间，可以移除或调整这个值 */
  margin-right: 1px; /* 靠右时，可能需要右边距来保持距离容器边缘 */
  font-size: 12px;
  font-weight: bold;
  color: #8b8b8b;
  padding: 4px;     /* 内边距 */
  background: #e0e0e0; /* 背景颜色 */
  border-radius: 8px; /* 圆角 */
  box-shadow: 0px 0px 10px rgba(113, 113, 113, 0.15); /* 边缘阴影 */
  word-wrap: break-word;  /* 允许在单词内换行 */
  white-space: normal;     /* 正常处理空白和换行 */
  width: auto;
  max-width: 45%; /* 限制最大宽度 */
  box-sizing: border-box; /* 确保padding和border不会使元素宽度超出 */
}

.card-down {
  width: 100%;
  height: 10%;
  float: bottom;
}

/* 🔥 类型编辑相关样式 */
.card-type-edit {
  display: inline-block;
  margin-left: 10px;
  vertical-align: middle;
  cursor: pointer;
}

.type-edit-label {
  font-size: 12px;
  color: #666;
  padding: 2px 8px;
  border-radius: 4px;
  background-color: #f5f5f5;
  transition: background-color 0.3s;
}

.type-edit-label:hover {
  background-color: #e8e8e8;
}

.type-label-text {
  font-weight: bold;
  margin-right: 4px;
}

.type-value {
  font-weight: 500;
}

.type-separator {
  margin: 0 4px;
  color: #999;
}

.type-edit-content {
  padding: 10px 0;
}

.type-explain {
  margin-bottom: 20px;
  padding: 15px;
  background-color: #f9f9f9;
  border-radius: 6px;
}

.type-explain h4 {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #333;
}

.type-explain ul {
  margin: 0;
  padding-left: 20px;
}

.type-explain li {
  margin: 5px 0;
  font-size: 13px;
  color: #666;
  line-height: 1.6;
}

.type-selector {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.type-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.type-group label {
  min-width: 80px;
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.type-select {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  background-color: #fff;
  cursor: pointer;
  transition: border-color 0.3s;
}

.type-select:focus {
  outline: none;
  border-color: #4dabf7;
}



/* 🔥 卡片进化等待提示覆盖层 */
.card-tidying-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(255, 255, 255, 0.9);
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  pointer-events: all; /* 阻止点击操作 */
}

.card-tidying-content {
  text-align: center;
  padding: 20px;
}

.card-tidying-content .waiting-text {
  font-size: 16px;
  color: #333;
  font-weight: 500;
}



/* 卡片作者标识样式 */
.card-title-content {
  /* display: flex; */
  align-items: center;
  justify-content: space-between;
}

.card-author-badge {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-size: 10px;
  padding: 2px 2px;
  border-radius: 10px;
  font-weight: 500;
  margin-right: 2px;
  white-space: nowrap;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  transition: all 0.3s ease;
}

.card-author-badge:hover {
  transform: scale(1.05);
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3);
}

/* 作者筛选输入框样式 */
.author-filter {
  margin-top: 8px;
}

.author-filter .filter-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 12px;
  background-color: #f9f9f9;
  transition: all 0.3s ease;
}

.author-filter .filter-input:focus {
  outline: none;
  border-color: #667eea;
  background-color: white;
  box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
}

.editContentDialog {
  height: 100%;
  width: 100%;

  display: flex;
  align-items: center;
  /* 这两行可以让textarea输入框下拉时整个dialog也跟随 */
}

.contentInput textarea {
  resize: vertical;
  /* 允许垂直调整大小 */
  overflow: auto;
  /* 添加滚动条 */
  width: 100%;
  /* 设置宽度以适应其父元素 */

  height: 700px;
}




/* 内容区域样式 */
.content-section {
  position: relative;
}

/* 卡片布局 */
/* 🔥 永久卡片布局样式 */
.permanent-card-layout {
  display: flex;
  flex-direction: column;
  min-height: calc(60vh - 100px);
}

.permanent-card-header-bar {
  display: flex;
  align-items: center;
  padding: 10px 15px;
  background-color: #f5f5f5;
  border-bottom: 1px solid #ddd;
  flex-wrap: wrap;
  gap: 8px;
  flex-shrink: 0;
}

.permanent-card-meta-item {
  white-space: nowrap;
  font-size: 14px;
}

.permanent-card-meta-separator {
  color: #999;
  margin: 0 5px;
}

.permanent-card-content-area {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 300px;
  margin: 8px 0;
}

.permanent-card-content-section {
  display: flex;
  flex-direction: column;
  padding: 15px;
  height: 100%;
}

.permanent-card-content-body {
  flex: 1;
  overflow-y: auto;
  padding: 15px;
  border-radius: 8px;
  min-height: 200px;
  max-height: 400px;
}

.permanent-card-footer-bar {
  display: flex;
  align-items: center;
  padding: 10px 15px;
  background-color: #f5f5f5;
  border-top: 1px solid #ddd;
  border-bottom: 1px solid #ddd;
  flex-wrap: wrap;
  gap: 8px;
  flex-shrink: 0;
}

.permanent-card-footer-item {
  font-size: 14px;
}

.permanent-card-footer-separator {
  color: #999;
  margin: 0 5px;
  flex-shrink: 0;
}

.permanent-card-postindex-container {
  flex: 1;
  display: flex;
  align-items: flex-start;
  min-width: 0;
}

.permanent-card-postindex-list {
  display: inline;
  word-wrap: break-word;
  word-break: break-all;
  font-size: 1.0em;
  line-height: 1.6;
}

.permanent-card-postindex-item {
  cursor: pointer;
  color: #0055cc;
  white-space: normal;
  margin-right: 6px;
  margin-bottom: 4px;
  display: inline-block;
  padding: 3px 8px;
  background-color: #e6f2ff;
  border: 1px solid #b3d9ff;
  border-radius: 12px;
  font-size: 0.95em;
  transition: all 0.2s ease;
  text-decoration: none;
  line-height: 1.4;
}

.permanent-card-postindex-item:hover {
  color: #003399;
  background-color: #cce5ff;
  border-color: #80ccff;
  transform: translateY(-1px);
  box-shadow: 0 2px 4px rgba(0, 85, 204, 0.2);
}

.permanent-card-postindex-item:not(:last-child)::after {
  display: none;
}

/* 卡片内容区工具栏：朗读/生图/图理解反馈 */
.card-toolbar-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
  min-width: 0;
}
.card-toolbar-row-inline {
  margin-bottom: 4px;
  margin-top: 0;
  justify-content: flex-start;
}
.card-content-block {
  width: 100%;
}
.card-content-block .card-toolbar-row-inline {
  margin-bottom: 2px;
}
.card-toolbar-content-gap {
  height: 6px;
  margin: 0;
  flex-shrink: 0;
}
.card-content-zone {
  padding: 8px 15px;
}
.card-toolbar-left {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.card-toolbar-btn {
  padding: 6px 12px;
  font-size: 12px;
  border: 1px solid #c0c4cc;
  border-radius: 6px;
  background: #fff;
  color: #303133;
  cursor: pointer;
  white-space: nowrap;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}
.card-toolbar-btn:hover:not(:disabled) {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
}
.card-toolbar-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.card-image-gen-group {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid #b3d8ff;
  border-radius: 6px;
  background: #ecf5ff;
}
.card-toolbar-btn-gen {
  padding: 4px 10px;
  font-size: 12px;
  border: none;
  background: transparent;
  color: #409eff;
}
.card-toolbar-btn-gen:hover {
  background: rgba(64, 158, 255, 0.12);
  border-radius: 4px;
}
.card-toolbar-btn-gen-single {
  /* 与 .card-toolbar-btn 一致，仅语义区分“单次生图” */
  padding: 6px 12px;
}
.card-toolbar-btn-ci {
  max-width: 100%;
  white-space: normal;
  line-height: 1.3;
  min-height: 32px;
}
.card-image-generating-tip {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}
.card-ci-feedback-status {
  font-size: 12px;
  margin-left: 6px;
  white-space: nowrap;
}
.card-ci-feedback-loading {
  color: #909399;
}
.card-ci-feedback-success {
  color: #67c23a;
}
.card-ci-feedback-error {
  color: #f56c6c;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.iterate-image-dialog-hint {
  margin: 0 0 12px 0;
  font-size: 13px;
  color: #606266;
}
.iterate-dmt-preset-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin: 0 0 8px 0;
}
.iterate-dmt-preset-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.4;
  flex: 1 1 220px;
}
.overlay-test-mode-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
}
.overlay-test-panel {
  margin-top: 12px;
  padding: 10px;
  background: #f7f9fc;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}
.overlay-test-layout {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}
.overlay-test-left {
  flex: 1 1 62%;
  min-width: 0;
}
.overlay-test-right {
  flex: 1 1 38%;
  min-width: 320px;
  max-width: 460px;
}
.overlay-test-desc {
  margin: 0 0 8px;
  font-size: 12px;
  line-height: 1.5;
  color: #606266;
}
.overlay-test-base-row,
.overlay-test-opacity-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.overlay-test-label {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
}
.overlay-test-opacity-text {
  width: 42px;
  font-size: 12px;
  color: #409eff;
}
.overlay-test-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.overlay-iterate-panel {
  margin-top: 0;
  padding: 10px;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #fff;
}
.overlay-iterate-title {
  margin: 0 0 6px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.overlay-iterate-desc {
  margin: 0 0 8px;
  font-size: 12px;
  color: #606266;
}
.overlay-iterate-stage {
  position: relative;
  display: inline-block;
  max-width: 100%;
  vertical-align: top;
  user-select: none;
  cursor: crosshair;
}
.overlay-iterate-stage img {
  display: block;
  max-width: 100%;
  height: auto;
  pointer-events: none;
}
.overlay-iterate-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin: 8px 0;
}
.overlay-iterate-ref-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}
.overlay-iterate-actions {
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.overlay-iterate-history-text {
  font-size: 12px;
  color: #909399;
}
.overlay-manual-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 10px;
}
.overlay-manual-mini {
  width: 48px;
  font-size: 12px;
  color: #606266;
}
.overlay-manual-save-hint {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}
.overlay-manual-color-presets {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  vertical-align: middle;
}
.overlay-manual-color-dot {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  border: 1px solid #c0c4cc;
  cursor: pointer;
  padding: 0;
  box-sizing: border-box;
}
.overlay-manual-color-dot.active {
  outline: 2px solid #409eff;
  outline-offset: 1px;
}
.overlay-manual-color-input {
  width: 28px;
  height: 24px;
  padding: 0;
  border: none;
  vertical-align: middle;
  cursor: pointer;
  background: transparent;
}
.overlay-manual-stage-wrap {
  display: inline-block;
  vertical-align: top;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  background: #f8fafc;
  max-width: 100%;
  max-height: 62vh;
  overflow: auto;
}
.overlay-manual-stage {
  display: inline-block;
  padding: 0;
  position: relative;
}
.overlay-manual-canvas {
  display: block;
  background: #fff;
  border: 1px solid #dcdfe6;
  box-sizing: border-box;
  cursor: crosshair;
}
.overlay-manual-selection-box {
  position: absolute;
  border: 2px dashed #409eff;
  background: rgba(64, 158, 255, 0.1);
  box-sizing: border-box;
  pointer-events: none;
  z-index: 20;
}
.selection-move-area {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  cursor: move;
  pointer-events: auto;
}
.overlay-manual-drag-preview {
  position: absolute;
  pointer-events: none;
  opacity: 0.7;
  z-index: 100;
}
.selection-edge {
  position: absolute;
  background: rgba(64, 158, 255, 0.3);
  z-index: 10;
  pointer-events: auto;
}
.selection-edge-top, .selection-edge-bottom {
  left: 0;
  right: 0;
  height: 8px;
  cursor: ns-resize;
}
.selection-edge-left, .selection-edge-right {
  top: 0;
  bottom: 0;
  width: 8px;
  cursor: ew-resize;
}
.selection-edge-top {
  top: -4px;
}
.selection-edge-bottom {
  bottom: -4px;
}
.selection-edge-left {
  left: -4px;
}
.selection-edge-right {
  right: -4px;
}
.overlay-test-stage {
  position: relative;
  display: inline-block;
  max-width: 100%;
  user-select: none;
}
/* 仅底图限制在容器内；覆盖层需允许宽/高超 100%，否则左右拉伸时会被 max-width 截断，看起来像只平移 */
.overlay-test-stage > img.overlay-test-base-img {
  display: block;
  max-width: 100%;
  height: auto;
}
.overlay-test-layer {
  position: absolute;
  pointer-events: none;
  opacity: 0.88;
  max-width: none;
  max-height: none;
  object-fit: fill;
}
.overlay-test-box {
  position: absolute;
  border: 2px dashed #409eff;
  box-sizing: border-box;
  cursor: move;
  z-index: 3;
}
.overlay-test-handle {
  position: absolute;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1px solid #fff;
  background: #409eff;
}
.overlay-test-handle-left {
  left: -6px;
  top: 50%;
  transform: translateY(-50%);
  cursor: ew-resize;
}
.overlay-test-handle-right {
  right: -6px;
  top: 50%;
  transform: translateY(-50%);
  cursor: ew-resize;
}
.overlay-test-handle-top {
  top: -6px;
  left: 50%;
  transform: translateX(-50%);
  cursor: ns-resize;
}
.overlay-test-handle-bottom {
  bottom: -6px;
  left: 50%;
  transform: translateX(-50%);
  cursor: ns-resize;
}
.iterate-image-reference-zone {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}
.iterate-image-reference-label {
  display: block;
  font-size: 13px;
  color: #606266;
  margin-bottom: 8px;
}
.iterate-image-file-input {
  display: none;
}
.iterate-image-reference-actions {
  margin-bottom: 8px;
}
.iterate-image-reference-actions .el-button + .el-button {
  margin-left: 8px;
}
.iterate-image-paste-hint {
  margin-left: 10px;
  font-size: 12px;
  color: #909399;
}
.iterate-image-reference-preview {
  margin-top: 8px;
}
.iterate-image-reference-preview img {
  max-width: 100%;
  max-height: 200px;
  display: block;
  border-radius: 6px;
  border: 1px solid #dcdfe6;
}
.iterate-region-panel {
  margin-top: 12px;
  padding: 10px;
  background: #f7f9fc;
  border-radius: 8px;
  border: 1px solid #e4e7ed;
}
.iterate-region-title {
  margin: 0 0 6px;
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}
.iterate-region-desc {
  margin: 0 0 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
}
.iterate-region-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.iterate-region-coords {
  font-size: 12px;
  color: #409eff;
}
.iterate-crop-full-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #606266;
  cursor: pointer;
  user-select: none;
}
.iterate-crop-full-switch input {
  margin: 0;
  cursor: pointer;
}
.iterate-region-stage {
  position: relative;
  display: inline-block;
  max-width: 100%;
  vertical-align: top;
  user-select: none;
  cursor: crosshair;
}
.iterate-region-stage img {
  display: block;
  max-width: 100%;
  height: auto;
  pointer-events: none;
}
.iterate-region-rect {
  position: absolute;
  box-sizing: border-box;
  border: 2px solid #e91e63;
  background: rgba(233, 30, 99, 0.12);
  pointer-events: none;
  z-index: 2;
}
.iterate-region-rect-drawing {
  border-style: dashed;
  background: rgba(233, 30, 99, 0.08);
  z-index: 3;
}

.iterate-image-reference-hint {
  margin: 6px 0 0 0;
  font-size: 12px;
  color: #909399;
}
.card-ci-feedback-wordcount-loading {
  margin-left: 8px;
  vertical-align: middle;
  display: inline-flex;
  align-items: center;
}
.card-ci-feedback-spinner {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid #e0e0e0;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: card-ci-feedback-spin 0.8s linear infinite;
}
@keyframes card-ci-feedback-spin {
  to { transform: rotate(360deg); }
}

/* 图无损理解反馈：选择分析弹窗 */
.ci-feedback-dialog .el-dialog__body {
  padding: 12px 20px 16px;
  max-height: 70vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.ci-feedback-empty {
  color: #909399;
  margin: 0;
  padding: 8px 0;
}
.ci-feedback-list-wrap {
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ci-feedback-list-title {
  margin: 0 0 10px 0;
  font-size: 14px;
  color: #303133;
}
.ci-feedback-list {
  overflow-y: auto;
  max-height: 50vh;
  padding-right: 6px;
}
.ci-analysis-item {
  margin-bottom: 10px;
}
.ci-analysis-item .el-radio {
  align-items: flex-start;
  width: 100%;
  margin-right: 0;
}
.ci-analysis-item .el-radio__label {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  width: 100%;
  min-width: 0;
}
.ci-analysis-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1 1 auto;
}
.ci-analysis-time {
  color: #909399;
  font-size: 12px;
  flex-shrink: 0;
}

.permanent-card-auxiliary-section {
  padding: 15px;
  flex-shrink: 0;
}

.permanent-card-review-section {
  margin-bottom: 20px;
}

.permanent-card-score-box {
  padding: 10px;
  border-radius: 8px;
  margin-bottom: 10px;
}

.permanent-card-reason-box {
  padding: 10px;
  border-radius: 8px;
  margin-bottom: 10px;
  position: relative;
  max-height: 120px;
  overflow-y: auto;
}

.permanent-card-suggestion-box {
  padding: 10px;
  border-radius: 8px;
  margin-bottom: 10px;
  position: relative;
  max-height: 150px;
  overflow-y: auto;
}

.permanent-card-button-group {
  display: flex;
  gap: 10px;
  justify-content: center;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid #ddd;
}

.permanent-card-button-group button {
  padding: 8px 16px;
  font-size: 14px;
  border-radius: 4px;
  border: 1px solid #ddd;
  background-color: #fff;
  cursor: pointer;
}

.permanent-card-button-group button:hover {
  background-color: #f5f5f5;
}

/* 🔥 永久卡片：展开/折叠图标 */
.permanent-card-expand-icon {
  display: inline-block;
  margin-left: 8px;
  font-size: 0.8em;
  transition: transform 0.3s ease;
  color: rgba(255, 255, 255, 0.8);
}

.permanent-card-expand-icon.expanded {
  transform: rotate(180deg);
}

/* 🔥 永久卡片：评阅详情区域 */
.permanent-card-review-details {
  animation: slideDown 0.3s ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
  }
  to {
    opacity: 1;
    max-height: 1000px;
  }
}

.card-layout {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.card-content-layout {
  display: flex;
  gap: 20px;
}

.card-left-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-right-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.section-title {
  margin: 5px 0;
}

.section-title h3 {
  margin: 0;
}

.reason-suggestion-container {
  display: flex;
  gap: 10px;
}

/* 展开按钮样式 */
.expand-button {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 24px;
  height: 24px;
  background-color: rgba(255, 255, 255, 0.7);
  border-radius: 4px;
  display: flex;
  justify-content: center;
  align-items: center;
  cursor: pointer;
  z-index: 10;
}

.expand-button:hover {
  background-color: rgba(255, 255, 255, 0.9);
}

.expand-icon {
  font-size: 14px;
  font-weight: bold;
}

/* 展开视图遮罩层 */
.expanded-view-overlay {
  /* position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.5);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000; */

  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background-color: rgba(0, 0, 0, 0.5);
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  width: 45vw;
  height: 60vh;
  max-width: 100%;

  padding: 20px;
}

/* 展开视图内容区 */
.expanded-view-content {
  width: 80%;
  height: 80%;
  background-color: white;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  max-width: 1000px;
}

/* 展开视图标题栏 */
.expanded-view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 20px;
  border-bottom: 1px solid #eee;
}

.expanded-view-header h3 {
  margin: 0;
}

/* 展开视图正文区 */
.expanded-view-body {
  flex: 1;
  padding: 20px;
  overflow-y: auto;
}




/* 编辑状态的高亮样式 */
.editable-field {
  cursor: pointer;
  padding: 3px;
  border-radius: 3px;
  transition: background-color 0.2s;
}

.editable-field:hover {
  background-color: #d0e5ff;
}

.keywords-generating-tip {
  color: #909399;
  font-size: 13px;
  margin-left: 4px;
}

/* 正在编辑状态的样式 */
.editing-field {
  background-color: #d0e5ff;
  padding: 3px;
  border-radius: 3px;
}

/* 内容编辑区样式 */
.content-edit-area {
  background-color: #e8f4e8;
  border: 1px solid #c2e0c2;
  border-radius: 4px;
  width: 100%;
  padding: 10px;
  min-height: 150px;
}

/* 内容区域悬停效果 */
.content-hover-area {
  transition: background-color 0.2s ease;
}

.content-hover-area:hover {
  background-color: #e8e8e8f6;
}

.content-hover-area-tidy {
  transition: background-color 0.2s ease;
}

.nkcn-card-page-nav {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 12px;
  padding: 8px 0 4px;
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  font-size: 13px;
  color: #5b6472;
}
.nkcn-card-page-nav button {
  appearance: none;
  border: 1px solid #d8d2c6;
  background: #fff;
  color: #1f2430;
  border-radius: 999px;
  padding: 4px 12px;
  cursor: pointer;
}
.nkcn-card-page-nav button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* 编辑按钮样式 */
.edit-button {
  margin-left: 10px;
  background-color: #e6f7ff;
  border: 1px solid #91d5ff;
  color: #1890ff;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.edit-button:hover {
  background-color: #bae7ff;
}

/* 保存和取消按钮样式 */
.save-button {
  margin-left: 10px;
  background-color: #f6ffed;
  border: 1px solid #b7eb8f;
  color: #52c41a;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.save-button:hover {
  background-color: #d9f7be;
}

.cancel-button {
  margin-left: 5px;
  background-color: #fff1f0;
  border: 1px solid #ffa39e;
  color: #ff4d4f;
  border-radius: 4px;
  padding: 2px 8px;
  cursor: pointer;
  transition: all 0.3s;
}

.cancel-button:hover {
  background-color: #ffccc7;
}



/* 共生区部分 */
.intergrowth-area {
  position: fixed;
  top: 50%;
  left: calc(50% + 33.75vw + 40px); /* 向右偏移一半的宽度 */
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #f9f9f9;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 25;
  width: 22.5vw; /* 一半宽度 */
  height: 60vh;
  max-width: 100%;
  overflow: scroll;
}

.intergrowth-section {
  margin-bottom: 15px;
  padding: 10px;
  border-radius: 5px;
  cursor: pointer;
  border: 1px solid #eaeaea;
  transition: all 0.1s ease;
}

.intergrowth-section:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
}

.incomplete {
  background-color: #ffcccc; /* 红色背景 */
  border-left: 3px solid #f5222d;
}

.completed {
  background-color: #ccffcc; /* 绿色背景 */
  border-left: 3px solid #52c41a;
}

.edit-area {
  margin-top: 10px;
}

.edit-area textarea {
  width: 100%;
  min-height: 80px;
  margin-bottom: 10px;
  padding: 10px;
  resize: vertical; /* 只允许垂直调整大小 */
  box-sizing: border-box;
}

.author-edit-area {
  margin-top: 20px;
}

.author-edit-area textarea {
  width: 100%;
  min-height: 150px;
  margin-bottom: 10px;
  padding: 10px;
  resize: vertical; /* 只允许垂直调整大小 */
  box-sizing: border-box;
}

.format-tip {
  margin-bottom: 10px;
  padding: 10px;
  background-color: #f8f8f8;
  border-left: 3px solid #2196F3;
}

.user-reply {
  margin-top: 8px;
  padding: 8px;
  background-color: #f0f8ff;
  border-radius: 4px;
  border-left: 2px solid #1976D2;
  display: block;  /* 确保每个回复都独占一行 */
}

.alert-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 4px;
}

.exclamation-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background-color: #ff4d4f;  /* 红色感叹号 */
  color: white;
  font-weight: bold;
  font-size: 18px;
}

.progress-indicator {
  display: inline-flex;
  margin-left: 4px;
}


.area-section {
  margin-bottom: 24px;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
}

.area-title {
  margin-top: 0;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: bold;

  padding-bottom: 8px;
  border-bottom: 2px solid;
}

.goal-area {
  background-color: #f8f0fc; /* 更柔和的淡紫色 */
  border: 1px solid #e3d0f5;
}
.goal-area .area-title {
  color: #7950c1;
  border-bottom-color: #7950c1;
}

.task-area {
  background-color: #e8f4fd; /* 更柔和的淡蓝色 */
  border: 1px solid #d0e8f5;
}
.task-area .area-title {
  color: #2b7cb4;
  border-bottom-color: #2b7cb4;
}

.division-area {
  background-color: #fff8e6; /* 更柔和的淡黄色 */
  border: 1px solid #f5e9d0;
}
.division-area .area-title {
  color: #b4892b;
  border-bottom-color: #b4892b;
}


.area-assignment {
  margin: 15px 0;
  padding: 15px;
  background-color: #f9f9f9;
  border-radius: 6px;
  border: 1px solid #eaeaea;
}

.question-area-selector {
  margin: 10px 0;
  display: flex;
  align-items: center;
}

.question-number {
  font-weight: bold;
  font-size: 14px;
  margin-right: 10px;
  min-width: 80px;
}

.question-area-selector select {
  padding: 6px 10px;
  border-radius: 4px;
  border: 1px solid #d9d9d9;
  background-color: white;
}


/* 共生区回答评分及建议 */
.edit-buttons {
  display: flex;
  margin-top: 10px;
  gap: 10px;
}

.ai-feedback-btn {
  background-color: #f0f0f0;
  border: 1px solid #d9d9d9;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.confirm-btn {
  background-color: #1890ff;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.ai-feedback-area {
  margin-top: 15px;
  border: 1px solid #d9d9d9;
  border-radius: 4px;
  padding: 15px;
  background-color: #f9f9f9;
}

.feedback-header {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}

.score-display {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  margin-right: 10px;
}

.feedback-title {
  font-weight: bold;
  font-size: 14px;
}

.suggestion-item {
  display: flex;
  margin: 8px 0;
}

.suggestion-icon {
  color: #faad14;
  margin-right: 10px;
}

.modify-btn {
  background-color: #1890ff;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
  margin-top: 10px;
}

.user-ratings {
  margin-top: 8px;
}

.user-rating {
  margin-bottom: 2px;
}

.user-rating-row {
  display: flex;
  align-items: center;
}

.user-rating-score {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  margin-right: 5px;
}

.suggestions-button {
  background: #f0f0f0;
  border: 1px solid #ccc;
  border-radius: 3px;
  width: 24px;
  height: 24px;
  cursor: pointer;
}

.suggestions-modal {
  position: fixed;
  top: 50%;
  left: calc(50% + 33.75vw + 40px); /* 向右偏移一半的宽度 */
  transform: translate(-50%, -50%);
  background-color: rgba(0, 0, 0, 0.5);
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1000;
  width: 22.5vw;
  height: 60vh;
  padding: 20px;
}

.suggestions-content {
  background: white;
  border-radius: 8px;
  width: 80%;
  max-width: 500px;
  max-height: 80vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 15px;
  border-bottom: 1px solid #e8e8e8;
}

.close-btn {
  background: none;
  border: none;
  font-size: 18px;
  cursor: pointer;
}

.suggestion-body {
  padding: 15px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  padding: 15px;
  gap: 10px;
  border-top: 1px solid #e8e8e8;
}

.accept-btn {
  background-color: #52c41a;
  color: white;
  border: none;
  padding: 6px 12px;
  border-radius: 4px;
  cursor: pointer;
}

.improvement-point {
  color: #fa8c16;
  display: block;
  margin-top: 10px;
  margin-bottom: 5px;
}

.ai-modifying-overlay {
  position: fixed;
  top: 50%;
  left: calc(50% + 33.75vw + 40px); /* 向右偏移一半的宽度 */
  transform: translate(-50%, -50%);
  background-color: rgba(0, 0, 0, 0.6);
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1500;
  width: 22.5vw;
  height: 60vh;
  padding: 20px;
}

.loading-container {
  text-align: center;
  color: white;
}

.loading-spinner {
  border: 5px solid #f3f3f3;
  border-top: 5px solid #1890ff;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  animation: spin 2s linear infinite;
  margin: 0 auto 15px;
}

.close-btn-bottom {
  background-color: #f0f0f0;
  border: 1px solid #d9d9d9;
  padding: 8px 16px;
  border-radius: 4px;
  cursor: pointer;
}

.rating-divider {
  margin: 15px 0;
  border: 0;
  border-top: 1px solid #c0c0c0;
  box-shadow: 0 1px 2px rgba(0,0,0,0.1);
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}





/* 综合建议区 */
.comprehensive-area {
  position: fixed;
  top: 50%;
  left: calc(50% - 33.75vw - 40px); /* 向左偏移一半的宽度 */
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 25;
  width: 22.5vw; /* 一半宽度 */
  height: 60vh;
  max-width: 100%;
  overflow: scroll;
}

.advice-content h4 {
  color: #1890ff;
  margin: 15px 0 5px 0;
  border-left: 3px solid #1890ff;
  padding-left: 10px;
}

.loading-advice {
  position: fixed;
  top: 50%;
  left: calc(50% - 33.75vw - 40px); /* 向左偏移一半的宽度 */
  transform: translate(-50%, -50%);
  background-color: rgba(0, 0, 0, 0.6);
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 1500;
  width: 22.5vw;
  height: 60vh;
  padding: 20px;
}

.user-selector {
  display: inline-flex;
  align-items: center;
  font-size: 14px;
  font-weight: normal;
}




@keyframes flash {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.1); }
}

.flashing {
  animation: flash 1s infinite; /* 可以设置为无限循环以便更容易观察 */
}





/* 按钮组容器 */
.card-button {
  display: flex;
  gap: 10px;
  margin-top: 16px;
  padding: 14px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-radius: 10px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.04);
  flex-wrap: wrap;
  justify-content: flex-start;
  align-items: center;
}

/* 按钮基础样式 */
.card-button button {
  padding: 8px 14px;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  min-width: 80px;
  height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  white-space: nowrap;
  letter-spacing: 0.025em;
}

/* 按钮悬停效果前的伪元素 */
.card-button button::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.5s;
}

.card-button button:hover::before {
  left: 100%;
}

/* 编辑按钮 - 主紫色 */
.card-edit {
  background: linear-gradient(135deg, #a78bfa 0%, #9333ea 100%);
  color: white;
  box-shadow: 0 2px 6px rgba(167, 139, 250, 0.15);
}

.card-edit:hover {
  background: linear-gradient(135deg, #9333ea 0%, #7e22ce 100%);
  box-shadow: 0 3px 8px rgba(147, 51, 234, 0.2);
  transform: translateY(-1px);
}

.card-edit:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(147, 51, 234, 0.15);
}

/* 删除按钮 - 粉紫色调 */
.card-delete {
  background: linear-gradient(135deg, #d8b4fe 0%, #c084fc 100%);
  color: white;
  box-shadow: 0 2px 6px rgba(216, 180, 254, 0.15);
}

.card-delete:hover {
  background: linear-gradient(135deg, #c084fc 0%, #a855f7 100%);
  box-shadow: 0 3px 8px rgba(192, 132, 252, 0.2);
  transform: translateY(-1px);
}

.card-delete:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(192, 132, 252, 0.15);
}

/* 历史按钮 - 蓝紫色调 */
.card-history {
  background: linear-gradient(135deg, #818cf8 0%, #6366f1 100%);
  color: white;
  box-shadow: 0 2px 6px rgba(129, 140, 248, 0.15);
}

.card-history:hover {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  box-shadow: 0 3px 8px rgba(99, 102, 241, 0.2);
  transform: translateY(-1px);
}

.card-history:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(99, 102, 241, 0.15);
}

/* 复制按钮 - 灰紫色调 */
.card-paste {
  background: linear-gradient(135deg, #a8a3d8 0%, #8b85c1 100%);
  color: white;
  box-shadow: 0 2px 6px rgba(168, 163, 216, 0.15);
}

.card-paste:hover {
  background: linear-gradient(135deg, #8b85c1 0%, #736fa0 100%);
  box-shadow: 0 3px 8px rgba(139, 133, 193, 0.2);
  transform: translateY(-1px);
}

.card-paste:active {
  transform: translateY(0);
  box-shadow: 0 1px 4px rgba(139, 133, 193, 0.15);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .card-button {
    flex-direction: column;
    gap: 10px;
    padding: 14px;
  }
  
  .card-button button {
    width: 100%;
    min-width: unset;
  }
}

@media (max-width: 480px) {
  .card-button {
    padding: 12px;
    gap: 8px;
  }
  
  .card-button button {
    padding: 12px 16px;
    height: 44px;
    font-size: 15px;
  }
}

/* 焦点状态样式 */
.card-button button:focus {
  outline: none;
  box-shadow: 0 0 0 2px rgba(147, 51, 234, 0.15);
}

/* 禁用状态样式 */
.card-button button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none !important;
}

.card-button button:disabled:hover {
  transform: none !important;
}



/* 质量评估悬浮框 */
.quality-assessment-tooltip {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 8px;
  background: #303133;
  color: white;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 12px;
  white-space: nowrap;
  z-index: 1000;
  box-shadow: 0 2px 12px rgba(0,0,0,0.2);
  min-width: 200px;
}

.quality-assessment-tooltip::before {
  content: '';
  position: absolute;
  top: -6px;
  left: 20px;
  border-left: 6px solid transparent;
  border-right: 6px solid transparent;
  border-bottom: 6px solid #303133;
}

.quality-assessment-tooltip div {
  line-height: 1.6;
}

/* 卡片 HTML 右键菜单与内嵌预览 */
.card-html-ctx-menu {
  position: fixed;
  z-index: 100000;
  min-width: 168px;
  background: #1e1e24;
  color: #eee;
  border-radius: 8px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  padding: 6px 0;
  font-size: 13px;
}
.card-html-ctx-item {
  padding: 10px 14px;
  cursor: pointer;
  white-space: nowrap;
}
.card-html-ctx-item:hover {
  background: #2f2f38;
}
.card-image-stack {
  position: relative;
  margin-bottom: 6px;
}
.card-html-chrome {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: #25252c;
  color: #e8e8ea;
  border-radius: 8px;
  border: 1px solid #3a3a44;
}
.card-html-chrome-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.card-html-chrome-title {
  font-size: 12px;
  opacity: 0.92;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-html-chrome-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.card-html-seg {
  border: 1px solid #4a4a55;
  background: #2b2b33;
  color: #ddd;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
}
.card-html-seg.on {
  background: #3d5a80;
  border-color: #5a7caf;
  color: #fff;
}
.card-html-seg.primary {
  background: #2e6b4f;
  border-color: #3a8c68;
}
.card-html-iframe {
  width: 100%;
  min-height: 320px;
  height: 420px;
  border: none;
  border-radius: 8px;
  background: #fff;
}
.card-html-iframe.card-html-iframe--grading-excerpt {
  min-height: 560px;
  height: min(68vh, 720px);
}
.card-html-source-pre {
  margin: 0;
  max-height: 420px;
  overflow: auto;
  padding: 10px;
  font-size: 11px;
  background: #0d1117;
  color: #c9d1d9;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ========== 交叉梳理 1+n 专区 ========== */
.cross-reorg-tabs {
  margin: 8px 0 12px;
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  background: #eef2f6;
  border-radius: 10px;
}
.cross-reorg-tab {
  border: none;
  background: transparent;
  color: #5b6b7c;
  font-size: 13px;
  padding: 7px 14px;
  border-radius: 8px;
  cursor: pointer;
  font-weight: 500;
}
.cross-reorg-tab.active {
  background: #fff;
  color: #1f2a37;
  box-shadow: 0 1px 3px rgba(20, 30, 50, 0.08);
}
/* 知识冲突面板 */
.kc-panel {
  padding: 14px;
  background: linear-gradient(165deg, #f7f3ef 0%, #f0f4f8 55%, #eef2f7 100%);
  border-radius: 12px;
  margin-bottom: 14px;
  border: 1px solid #e6ddd3;
}
.kc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}
.kc-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: #8a5a2b;
  background: #f3e4d2;
  padding: 3px 8px;
  border-radius: 999px;
  margin-right: 8px;
}
.kc-meta {
  font-size: 12px;
  color: #6b7c8f;
}
.kc-note {
  font-size: 12px;
  color: #7a6a58;
  background: #fff8f0;
  border: 1px solid #edd9c3;
  border-radius: 8px;
  padding: 8px 10px;
  margin: 0 0 12px;
}
.kc-card {
  background: #fff;
  border: 1px solid #e8e0d6;
  border-radius: 12px;
  padding: 12px 12px 10px;
  margin-bottom: 10px;
  box-shadow: 0 1px 2px rgba(40, 30, 20, 0.04);
  border-left: 4px solid #c9a27a;
}
.kc-card.kc-st-confirm { border-left-color: #3a9b6a; background: #f7fcf9; }
.kc-card.kc-st-unsure { border-left-color: #d0a14a; background: #fffbf3; }
.kc-card.kc-st-deny { border-left-color: #c06a5a; background: #fdf7f6; }
.kc-card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.kc-cat {
  font-size: 11px;
  font-weight: 650;
  color: #8a5a2b;
  background: #f6ebe0;
  padding: 2px 8px;
  border-radius: 6px;
}
.kc-id { font-size: 11px; color: #9aa6b2; }
.kc-title {
  margin: 0 0 6px;
  font-size: 15px;
  color: #243447;
  font-weight: 650;
  line-height: 1.35;
}
.kc-summary, .kc-tension, .kc-insight, .kc-why {
  margin: 0 0 8px;
  font-size: 13px;
  color: #3d4d5f;
  line-height: 1.5;
}
.kc-summary.is-clamped {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  margin-bottom: 6px;
  color: #52657a;
}
.kc-toggle {
  border: none;
  background: transparent;
  color: #6b7c8f;
  font-size: 12px;
  padding: 0;
  margin: 0 0 8px;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}
.kc-toggle:hover { color: #3d4d5f; }
.kc-detail {
  margin: 0 0 8px;
  padding: 8px 10px;
  background: #f7f9fb;
  border-radius: 8px;
  border: 1px solid #e8eef4;
}
.kc-detail .kc-tension,
.kc-detail .kc-insight,
.kc-detail .kc-why { margin-bottom: 6px; }
.kc-detail .kc-note-box { margin-top: 8px; margin-bottom: 0; }
.kc-tension b, .kc-insight b, .kc-why b {
  color: #6b7c8f;
  font-weight: 650;
  margin-right: 6px;
}
.kc-parties {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 4px 0 8px;
}
.kc-actions { margin-bottom: 0; }
.kc-party {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 999px;
  background: #eef2f6;
  color: #4a5a6a;
}
.kc-party.kind-doc { background: #e8f0fa; color: #2f5f8f; }
.kc-party.kind-pack { background: #eaf6ef; color: #2f6b4a; }
.kc-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.kc-act {
  border: 1px solid #d8e0e8;
  background: #fff;
  color: #5b6b7c;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 999px;
  cursor: pointer;
  font-weight: 550;
}
.kc-act.confirm.on { background: #e6f6ee; border-color: #8fc9a8; color: #1f8a55; }
.kc-act.unsure.on { background: #fff3dc; border-color: #e2c48a; color: #a06a18; }
.kc-act.deny.on { background: #fdeceb; border-color: #e3a59b; color: #b04a3a; }
.kc-note-box label {
  display: block;
  font-size: 11px;
  color: #8a96a3;
  margin-bottom: 4px;
}
.kc-note-box textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #e3e9f0;
  border-radius: 8px;
  padding: 8px 10px;
  font-size: 12px;
  color: #243447;
  resize: vertical;
  background: #fafbfc;
  font-family: inherit;
  line-height: 1.45;
}
.cross-reorg-skills-panel {
  padding: 12px;
  background: linear-gradient(180deg, #f4f7fb 0%, #eef2f7 100%);
  border-radius: 12px;
  margin-bottom: 14px;
  border: 1px solid #e3e9f0;
}
.cross-reorg-empty {
  color: #8a96a3;
  font-size: 13px;
  padding: 18px 8px;
  text-align: center;
}
.cross-reorg-aim {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e5ebf1;
}
.cross-reorg-aim-label {
  display: inline-block;
  font-size: 11px;
  font-weight: 650;
  color: #6b7c8f;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  margin-right: 8px;
}
.cross-reorg-aim-text {
  font-size: 13px;
  color: #243447;
  line-height: 1.55;
}
.cross-reorg-status {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 650;
  padding: 3px 9px;
  border-radius: 999px;
  background: #eef2f6;
  color: #5b6b7c;
}
.cross-reorg-status.st-ok {
  background: #e8f6ef;
  color: #1f8a55;
}
.cross-reorg-status.st-partial {
  background: #fff6e6;
  color: #b76b20;
}
.cross-reorg-status.st-failed {
  background: #fdecec;
  color: #c45656;
}
.cross-reorg-status.st-running {
  background: #e8f1fc;
  color: #3a6ea8;
}
.cross-reorg-hub-card,
.cross-reorg-theme-card {
  margin-bottom: 10px;
  padding: 12px 14px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e5ebf1;
  box-shadow: 0 1px 2px rgba(20, 30, 50, 0.04);
}
.cross-reorg-hub-card {
  border-left: 3px solid #3d6ea8;
}
.cross-reorg-theme-card.is-failed {
  border-left: 3px solid #c45656;
  opacity: 0.92;
}
.cross-reorg-hub-badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 650;
  color: #3d6ea8;
  background: #eaf2fb;
  padding: 2px 8px;
  border-radius: 999px;
  margin-bottom: 6px;
}
.cross-reorg-theme-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}
.cross-reorg-card-title {
  font-weight: 650;
  font-size: 15px;
  color: #1f2a37;
}
.cross-reorg-card-desc {
  font-size: 13px;
  color: #4a5a6a;
  line-height: 1.55;
  margin: 4px 0 8px;
}
.cross-reorg-meta-row {
  display: grid;
  grid-template-columns: 64px 1fr;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 6px;
  align-items: start;
}
.cross-reorg-meta-k {
  color: #8a6a3b;
  font-weight: 650;
  padding-top: 1px;
}
.cross-reorg-meta-v {
  color: #3d4a58;
  line-height: 1.5;
}
.cross-reorg-kw-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 8px 0;
}
.cross-reorg-kw {
  font-size: 11px;
  color: #3d4a58;
  background: #f1f4f8;
  border: 1px solid #e5ebf1;
  border-radius: 999px;
  padding: 2px 8px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cross-reorg-kw.more {
  background: transparent;
  border-style: dashed;
  color: #8a96a3;
}
.cross-reorg-rel {
  font-size: 12px;
  color: #7a8694;
  line-height: 1.55;
  margin-bottom: 8px;
}
.cross-reorg-rel b {
  color: #5b6b7c;
  font-weight: 600;
  margin-right: 4px;
}
.cross-reorg-btn {
  border: 1px solid #c5d4e6;
  background: #f5f9fd;
  color: #2f5f8f;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
  cursor: pointer;
}
.cross-reorg-btn:hover {
  background: #e8f1fc;
  border-color: #9bb8d9;
}
.cross-reorg-err {
  font-size: 12px;
  color: #c45656;
}

/* ========== Skill 查看对话框（对齐 FileCard 文档 Skill 样式） ========== */
.skill-dlg-overlay {
  position: fixed;
  inset: 0;
  background: rgba(22, 28, 36, 0.48);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 30000;
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
  box-shadow: 0 1px 2px rgba(20, 30, 50, 0.08);
}
.skill-dlg-body {
  padding: 12px 22px;
  overflow: auto;
  flex: 1;
  min-height: 0;
}
.skill-dlg-body--edit {
  display: flex;
  flex-direction: column;
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
.skill-md-source {
  flex: 1;
  min-height: 360px;
  margin: 0;
  overflow: auto;
  border: 1px solid #e5ebf1;
  border-radius: 10px;
  background: #fbfcfe;
  padding: 14px 16px;
  font-family: Consolas, 'SF Mono', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.55;
  color: #1f2a37;
  white-space: pre-wrap;
  word-break: break-word;
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
.skill-md-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0 0 12px;
  font-size: 13px;
}
.skill-md-body :deep(th),
.skill-md-body :deep(td) {
  border: 1px solid #e5ebf1;
  padding: 6px 8px;
  text-align: left;
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
  gap: 8px;
}
.skill-btn {
  border: 1px solid #d7dee7;
  background: #fff;
  color: #334155;
  font-size: 13px;
  padding: 7px 14px;
  border-radius: 8px;
  cursor: pointer;
}
.skill-btn--ghost:hover {
  background: #f2f4f7;
}
</style>
