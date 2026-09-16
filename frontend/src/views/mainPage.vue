<template>
  <div class="scene-name">
    <div class="content-wrapper">
      <span class="scene-text">当前场景：{{ this.sceneName }}</span>
      <!-- 半自动化新增 -->
      <div 
        class="custom-switch"
        :title="recordMode ? '普通状态（停止记录）' : '涌现示范状态（开始记录）'"
        :class="{ 'active': recordMode }"
        @click="toggleRecordMode">
        <div class="switch-thumb"></div>
      </div>
      <!-- 🔥 当前状态文字显示（只显示文字，不做滑钮操作） -->
      <span class="system-status-text">当前状态：{{ systemChoice === 0 ? '慢思考' : '快思考' }}</span>
      <!-- 🔥 本子信息显示 -->
      <span class="notebook-info-text" v-if="notebookInfo">
        &nbsp;&nbsp;当前本子：{{ notebookInfo.name }}({{ notebookInfo.deepCount }}/{{ notebookInfo.dmtCount }}/{{ notebookInfo.totalCount }})
      </span>
    </div>
  </div>
  <div class="sub-scene-name">切换子场景：</div>

  <div class="button-container">
    <button 
      v-for="(text, index) in this.subSceneList"
      :key="index"
      ref="buttons"
      class="change-sub-scene" 
      :class="{ 'change-sub-scene-active': isActive(index) }"
      @click="changeSubScene(text, index)"
    >
      {{ text }}
    </button>

    <button 
      class="change-plus" 
      ref="buttonPlus"
      :class="{ 'change-plus-active': isPlus }"
      @click="changePlus()"
    >
      {{ isPlus ? '取消LUI·Plus' : '启用LUI·Plus' }}
    </button>
    <button 
      class="open-config" 
      ref="buttonConfig"
      v-if="isPlus"
      :style="{ left: (100 + subSceneWidth) + 'px' }"
      @click="openConfig()"
    >
      配置Plus角色
    </button>
  </div>

  <div class="voice-background">
    <div class="vbg-name">当前摘要：{{ this.currentBgc.name }}</div>
    <button class="vbg-cards" @click="showBgcChecked = true">摘要卡片</button>
  </div>

  <div ref="MainPage">
    <el-container height="50vh">
      <el-header>
        <MainNav ref="MainNav" @updateStyle="updateStyle" @update:params="handleParamsUpdate" @updateContext="updateContext"
          :currentModule="this.currentModule" @userFeedBack="userFeedBack" :needWaitFile="needWaitFile" :clickAdmin="clickAdmin"
          @clickOver="clickOver">
        </MainNav>
      </el-header>
      <el-main>
        <!-- <div class="main-left1" v-if="this.currentModule === 0"> -->
        <div class="main-left1" v-show="this.currentModule === 0">
          <!-- 左侧内容，当currentModule为'0'时显示 -->
          <div class="left-addfile">
            <span class="left-addfile-text">{{ this.sceneName }}场景</span>
            <span 
              class="left-addfile-text document-import-area" 
              @dblclick="handleGenerateCrossDocumentSuggestion"
              title="双击此处可以生成文档交叉梳理建议卡"
            >文档导入区</span>
            <span style="display: none;">
              <label for="docFile">
                <span class="left-addfile-button"></span>
              </label>
              <input type="file" id="docFile" @change="addfile" accept="application/*,text/*,image/*,.xlsx,.xls,audio/*,.mp3,.wav,.ogg,.m4a,.aac,.flac,.webm" />
            </span>
          </div>
          <div class="left-filelist">
            <FileList key="fileList" @FileNameListFromFileList="handleFileList" @ImportImagePoolFromFileList="handleImportImagePool" @update:fileSummary="handleFileSummaryUpdate"
              @update:fileLeftSelection="handleFileLeftSelectUpdate"
              @update:fileRightSelection="handleFileRightSelectUpdate" 
              :sceneName="sceneName"
              :needWaitFile="needWaitFile" :waitFileNames="waitFileNames" :waitFileSizes="waitFileSizes" ref="FileList"
              @fileUploadLog="fileUploadLog" @reloadAutoCards="reloadAutoCards" :isRecording="recordMode"
              @startRecordWithTarget="handleStartRecordWithTarget" @endRecordWithTarget="handleEndRecordWithTarget"
              @delete-file="refreshFileListAfterDel" @material-settings="openFeedbackMaterial('grading', $event)"
              @open-batch-sketch-r-dialog="openBatchSketchRDialog"></FileList>
          </div>
        </div>

        <div class="main-left2" v-if="this.currentModule === 1">
          <!-- 左侧内容，当currentModule为'1'时显示 -->
          <div class="left-nav">
            <div
              class="left-nav-title"
              :title="curFileInfo.name ? `${curFileInfo.name}（双击触发图片理解）` : ''"
              @dblclick="handleCIDocumentPreviewDoubleClick(curFileInfo.name)"
            >{{ curFileInfo.name }}</div>
            <div class="left-nav-switch" @click="displaySummary">Summary & Topics</div>
            <div class="left-nav-close" @click="fileSummaryClose">
              <i class="left-nav-close-icon"></i>
            </div>
          </div>
          <div class="left-summary">
            <div class="left-summary-top">
              <div class="left-summary-abstract">
                <div class="left-summary-abstract-title">
                  <span>Summary</span>
                  <div class="summary-pin-icon" @click="pinSummaryToCard" title="将摘要内容钉成卡片">
                    📌
                  </div>
                  <div v-if="summaryStreamComplete && curFileInfo.content && curFileInfo.content !== '正在生成摘要中'" class="summary-hint-wrap">
                    <span class="summary-hint-icon" aria-label="配图说明">ⓘ</span>
                    <span class="summary-hint-label">钉卡即配图</span>
                    <div class="summary-hint-tooltip">
                      <span class="summary-hint-tooltip-title">等待配图生成...</span>
                      <span class="summary-hint-tooltip-tip">点击钉子图标钉卡片后，考虑原文&摘要配图将自动保存到钉出的卡片中（摘要默认带图）。</span>
                    </div>
                  </div>
                  <span v-if="LUI1_plus" class="lui1-plus-icon" @click="run_LUI1_plus" title="点此进一步做主题裂解群组增强">
                    plus
                  </span>
                </div>
                <div class="left-summary-abstract-content" ref="summaryContent">
                  <!-- {{ curFileInfo.content }} -->
                  <AnswerParser :answer="curFileInfo.content"/>
                </div>
              </div>
              <div class="left-summary-topics">
                <div class="left-summary-topics-title">Key Topics</div>
                <div class="left-summary-topics-item" v-for="(item, index) in this.topicContents" :key="index"
                  @click="topicDialog(item)">
                  {{ item }} <!-- 显示div的内容 -->
                </div>
              </div>
            </div>
            <div class="left-summary-bottom">
              <div class="summary-img-list" v-if="shouldShowImages">
                <div class="summary-img-list-item" v-for="(item, index) in this.imgContents" :key="index"
                  @click="handleImageClick(item, index, 'pdf')">
                  <!-- @click="ImgDialog(item, index, 'pdf')" -->
                  <!-- 使用 v-bind 将 base64 编码的图片显示出来 -->
                  <img :src="'data:image/png;base64,' + item" alt="Image" />
                  <!-- 图片处理状态覆盖层 -->
                  <div v-if="isImageProcessing(index)" class="image-processing-overlay">
                    <div class="processing-spinner"></div>
                    <div class="processing-text">处理中...</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div class="left-text">
            <!-- {{ curFileInfo.text }} -->
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
              <div style="flex-grow: 1; display: flex; flex-wrap: wrap; align-items: center; gap: 0;">
                <button @click="chooseEn" class="card-src-btn" v-if="showPdfViewer&&isObjScene">
                  {{ chooseEnOrEnZh === 'EnZh' || chooseEnOrEnZh === 'Zh' ? '原文' : '译文' }}
                </button>
                <button @click="chooseEnZh" class="card-obj-btn" v-if="showPdfViewer&&isObjScene">中英对比</button>
                <button @click="handleOpenHomeworkPageView('layout')" class="card-obj-btn card-hg-btn" v-if="showPdfViewer&&ciHomeworkToolbarReady">无损版面</button>
                <button @click="handleOpenHomeworkPageView('understanding')" class="card-obj-btn card-hg-btn" v-if="showPdfViewer&&ciHomeworkToolbarReady">无损理解</button>
                <button @click="handleOpenHomeworkPageView('grading')" class="card-obj-btn card-hg-btn" v-if="showPdfViewer&&ciHomeworkToolbarReady">三区批改</button>
              </div>
              <div style="display: flex; align-items: flex-start; gap: 8px;">
                <button @click="openPdfInNewWindows" class="card-obj-btn" v-if="showPdfViewer">新窗口显示</button>
                <button @click="openTxtInNewWindow" class="card-obj-btn" v-if="showTxtViewer">新窗口显示</button>
                <div class="flexing-button" :class="{ 'flexBtnChecked': flexBtnChecked }" v-if="showPdfViewer&&isObjScene" 
                  @click="maybeEnZhDisplay">
                </div>
              </div>
            </div>
            <div style="display: flex; width: 100%; height: 90%">
              <div class="show-text" v-if="showTxtViewer">
                <pre style="white-space: pre-wrap; word-wrap: break-word;">{{ curFileInfo.text }}</pre>
              </div>
              <!-- 点击加载PDF进度显示 -->
              <div v-if="showPdfViewer&&isLoading" class="loading-overlay">
                <div class="progress-bar">
                  <div class="progress-fill" :style="{ width: loadingProgress + '%' }"></div>
                </div>
                <div class="progress-text">{{ loadingText }}</div>
                <div class="progress-details">
                  {{ formatBytes(loadedBytes) }} / {{ formatBytes(totalBytes) }}
                </div>
              </div>
              <!-- PDF显示 -->
              <!-- <iframe :src="fileUrl"
                id="pdfFrame"
                v-if="showPdfViewer"
                style="width: 50%; height: 100%"
                @load="onPdfLoaded"
              ></iframe> -->
              <iframe :src="fileUrl"
                id="pdfFrame"
                v-if="showPdfViewer && !isAudioFile"
                style="width: 50%; height: 100%"
              ></iframe>
              <!-- 音频播放器 -->
              <div v-if="showPdfViewer && isAudioFile" class="audio-player-container">
                <div class="audio-player-header">
                  <h3>{{ currentAudioFileName }}</h3>
                </div>
                <div class="audio-player-body">
                  <audio
                    ref="audioPlayer"
                    :src="currentAudioUrl"
                    @loadedmetadata="onAudioLoaded"
                    @timeupdate="onAudioTimeUpdate"
                    @ended="onAudioEnded"
                    @error="onAudioError"
                  ></audio>
                  <div class="audio-controls">
                    <button
                      class="audio-play-btn"
                      @click="toggleAudioPlay"
                      :disabled="!audioReady"
                    >
                      <span v-if="!isAudioPlaying">▶</span>
                      <span v-else>⏸</span>
                    </button>
                    <div class="audio-progress-container">
                      <div class="audio-progress-bar" @click="seekAudio">
                        <div
                          class="audio-progress-fill"
                          :style="{ width: audioProgressPercent + '%' }"
                        ></div>
                        <div
                          class="audio-progress-handle"
                          :style="{ left: audioProgressPercent + '%' }"
                        ></div>
                      </div>
                      <div class="audio-time">
                        <span>{{ formatAudioTime(audioCurrentTime) }}</span>
                        <span> / </span>
                        <span>{{ formatAudioTime(audioDuration) }}</span>
                      </div>
                    </div>
                    <button
                      class="audio-stop-btn"
                      @click="stopAudio"
                      :disabled="!audioReady"
                    >
                      ⏹
                    </button>
                  </div>
                  <div v-if="audioLoading" class="audio-loading">
                    正在加载音频文件...
                  </div>
                  <div v-if="audioError" class="audio-error">
                    {{ audioError }}
                  </div>
                </div>
              </div>
              <div v-if="showPdfViewer&&chooseEnOrEnZh==='EnZh'&&isTranslating" class="loading-overlay">
                <div class="spinner-container">
                  <div class="spinner"></div>
                </div>
                <div class="progress-text">{{ '正在翻译文件...' }}</div>
              </div>

              <!-- 加载进度显示 -->
              <div v-if="showPdfViewer&&isLoadingTrans&&!isTranslating" class="loading-overlay-trans">
                <div class="progress-bar">
                  <div class="progress-fill" :style="{ width: loadingTransProgress + '%' }"></div>
                </div>
                <div class="progress-text">{{ loadingTransText }}</div>
                <div class="progress-details">
                  {{ formatBytes(loadedTransBytes) }} / {{ formatBytes(totalTransBytes) }}
                </div>
              </div>
              <iframe :src="fileTransUrl"
                id="pdfTransFrame"
                v-if="showPdfViewer&&chooseEnOrEnZh==='EnZh'&&!isTranslating"
                style="width: 50%; height: 100%"
              ></iframe>
            </div>
          </div>
        </div>
        <div class="main-else" v-else>
          <!-- 左侧内容，当currentModule为'0'时显示 -->
        </div>
        <div class="main-right">
          <!-- 右侧内容 -->
          <div class="right-nav">
            <div class="right-nav-title">卡片输出窗口</div>
            <div class="right-nav-buttons">
              <el-button @mouseover="showMenu">
                <i class="el-icon-tag"></i>
              </el-button>
              <el-button @click="changeCardGrid">
                {{ classCardGrid === 'Grid' ? 'Fold' : classCardGrid === 'GridFold' ? 'Unfold' : '' }}
              </el-button>
              <el-button @click="addCardDirectly">Add Card</el-button>
            </div>
          </div>

          <div class="right-cardgrid" v-if="classCardGrid === 'Grid'">
            <CardGrid ref="CardGrid" :cardUpdate="cardUpdate" :params="params" :activeModel="activeModel" :isPlus="isPlus"
              :fileNameList="fileNameList" :leftSelectList="leftSelectList" :rightSelectList="rightSelectList"
              @cardMerge="cardMerge"
              @cardUpdateOver="handleCardUpdateOver" @update-history="handleHistoryUpdate" :cardMaking="cardMaking" @update:cardMaking="cardMaking = $event"
              @cardClickLog="cardClickLog" :menuVis="menuVis" @menuVisNo="hideMenu" @sendKeyTopics="saveKeyTopics"
              @chooseCardChange="chooseCardChange" :cardSingleMaking="cardSingleMaking" :subSceneName="subSceneName" :sceneName="sceneName"
              @chosenOver="chosenOver" :HLContent="HLContent" :cardUpdateStream="cardUpdateStream" :HLOpeContent="HLOpeContent" :cardOpeUpdStream="cardOpeUpdStream"
              @record-operation="handleCardRecordOperation"
              :groupTwinProgress="nk2026GroupTwinProgress">
            </CardGrid>
          </div>
          <div class="right-cardgrid" v-if="classCardGrid === 'GridFold'">
            <CardGridFold ref="CardGridFold" :cardUpdate="cardUpdate" :params="params" :activeModel="activeModel" :isPlus="isPlus" @cardMerge="cardMerge"
              @cardUpdateOver="handleCardUpdateOver" @update-history="handleHistoryUpdate" :cardMaking="cardMaking" @update:cardMaking="cardMaking = $event"
              @cardClickLog="cardClickLog" :menuVis="menuVis" @menuVisNo="hideMenu" @sendKeyTopics="saveKeyTopics"
              @chooseCardChange="chooseCardChange" :cardSingleMaking="cardSingleMaking" :subSceneName="subSceneName" :sceneName="sceneName">
            </CardGridFold>
          </div>

          
          <div class="chat-up">
            <div class="chat-left-div" 
                 :class="{ 'chat-window-container': true }" 
                 @click="showModelLeft" @dragover.prevent @drop="handleDrop($event, 'left')">
              <!-- 拖拽合并，添加遮罩层提示，事件触发顺序：dragStart -> dragover -> drop -> dragEnd -->
              <div 
                class="drop-mask" 
                v-show="isHighlighted && activeDragWindow !== 'left'">
              </div>
              <div 
                class="close-mask" 
                v-show="closeMain"
                @click="showModelLeft">
              </div>
              <div class="chat-left-one-div">
                <ChatWindow ref="ChatWindow" windowId="left" :chatModelInfo="curModelInfo" :params="params" :isPlus="isPlus" 
                  :isQuestionWindow="isQuestionWindow1" @update:questionContents="handleQuestionContentsUpdate" @update:answerList="handleAnswerListUpdate"
                  @cardUpdate="handleCardUpdate" @cardUpdateStream="handleCardUpdateStream" @cardUpdateStreamOver="handleCardUpdateStreamOver" 
                  @cardOpeUpdStream="handleCardOpeUpdStream" @cardOpeUpdStreamOver="handleCardOpeUpdStreamOver" @cardOpeUpd="handleCardOpeUpd" @update:fileList="refreshFileList" @waitFile="waitFile" 
                  :formLui2="formLui2" @LUI2_agent="LUI2_agent" @LUI2_A_dia="LUI2_A_dia" @LUI2_A_err="LUI2_A_err"
                  :LUI2_result_index="LUI2_result_index" :isHistoryUsed="isHistoryUsed" :isSummaryUsed="isSummaryUsed"
                  :isMemorySystemUsed="isMemorySystemUsed"
                  @goCardGrid="showCardWindow" :keyTopics="keyTopics" @dragStart="handleDragStart" @dragEnd="handleDragEnd"
                  :rounds="rounds" :portraitStates="portraitStates" :threeModelQAState="threeModelQAState" :ModelContentMerge="ModelContentMerge"
                  @mergeEnd="mergeEnd" :choosedCardIdList="choosedCardIdList" @getCardRelQue="getCardRelQue"
                  @goCardGridWithoutMaking="showCardWindowWithoutMaking" :subSceneName="subSceneName" :sceneName="sceneName"
                  :openCardId="openCardId" :chosenContent="chosenContent" :fileNameList="fileNameList" @updateFileCardBanStyle="updateFileCardBanStyle"
                  @pinCard="pinCard" @retryCompleted="handleRetryCompleted" @pdfUploaded="handlePdfUploaded"
                  @scrollToCardGridTop="handleScrollToCardGridTop" @clearCardSingleMaking="handleClearCardSingleMaking"
                  :coreKeyword="coreKeyword"
                  :crossNotebookContext="isCrossNotebookContext">
                </ChatWindow>
              </div>
            </div>

            <div class="chat-right-div">
              <div class="chat-right-upper-div chat-window-container" 
                   @click="showModelUp" @dragover.prevent @drop="handleDrop($event, 'upper')">
                <!-- 添加遮罩层 -->
                <div 
                  class="drop-mask" 
                  v-show="isHighlighted && activeDragWindow !== 'upper'">
                </div>
                <div 
                  class="close-mask" 
                  v-show="closeUp"
                  @click="showModelUp">
                </div>
                <ChatWindow ref="ChatWindowUp" windowId="upper" :chatModelInfo="curModelInfoUp" :params="params" :isPlus="isPlus"
                  :isQuestionWindow="isQuestionWindow2" @update:questionContents="handleQuestionContentsUpdate" @update:answerList="handleAnswerListUpdate"
                  @cardUpdate="handleCardUpdate" @cardUpdateStream="handleCardUpdateStream" @cardUpdateStreamOver="handleCardUpdateStreamOver" 
                  @cardOpeUpdStream="handleCardOpeUpdStream" @cardOpeUpdStreamOver="handleCardOpeUpdStreamOver" @cardOpeUpd="handleCardOpeUpd" :formLui2="formLui2" @LUI2_agent="LUI2_agent" @LUI2_A_dia="LUI2_A_dia"
                  @LUI2_A_err="LUI2_A_err" :LUI2_result_index="LUI2_result_index" :isHistoryUsed="isHistoryUsed"
                  :isSummaryUsed="isSummaryUsed" :isMemorySystemUsed="isMemorySystemUsed" @goCardGrid="showCardWindow" :keyTopics="keyTopics"
                  @dragStart="handleDragStart" @dragEnd="handleDragEnd" :rounds="rounds" :portraitStates="portraitStates"
                  :choosedCardIdList="choosedCardIdList" @goCardGridWithoutMaking="showCardWindowWithoutMaking"
                  :subSceneName="subSceneName" :sceneName="sceneName" :openCardId="openCardId" :chosenContent="chosenContent"
                  :fileNameList="fileNameList" @updateFileCardBanStyle="updateFileCardBanStyle" @pinCard="pinCard" @retryCompleted="handleRetryCompleted"
                  @scrollToCardGridTop="handleScrollToCardGridTop" @clearCardSingleMaking="handleClearCardSingleMaking"
                  :coreKeyword="coreKeyword"
                  :crossNotebookContext="isCrossNotebookContext">
                </ChatWindow>
              </div>

              <div class="chat-right-lower-div chat-window-container" 
                   @click="showModelDown" @dragover.prevent @drop="handleDrop($event, 'lower')"
                   @mouseover="lowerhover = false" @mouseout="lowerhover = false">
                <!-- 添加遮罩层 -->
                <div 
                  class="drop-mask" 
                  v-show="isHighlighted && activeDragWindow !== 'lower'">
                </div>
                <div 
                  class="close-mask" 
                  v-show="closeDown"
                  @click="showModelDown">
                </div>
                <ChatWindow ref="ChatWindowDown" windowId="lower" :chatModelInfo="curModelInfoDown" :params="params" :isPlus="isPlus"
                  :isQuestionWindow="isQuestionWindow3" @update:questionContents="handleQuestionContentsUpdate" @update:answerList="handleAnswerListUpdate"
                  @cardUpdate="handleCardUpdate" @cardUpdateStream="handleCardUpdateStream" @cardUpdateStreamOver="handleCardUpdateStreamOver" 
                  @cardOpeUpdStream="handleCardOpeUpdStream" @cardOpeUpdStreamOver="handleCardOpeUpdStreamOver" @cardOpeUpd="handleCardOpeUpd" :formLui2="formLui2" @LUI2_agent="LUI2_agent" @LUI2_A_dia="LUI2_A_dia"
                  @LUI2_A_err="LUI2_A_err" :LUI2_result_index="LUI2_result_index" :isHistoryUsed="isHistoryUsed"
                  :isSummaryUsed="isSummaryUsed" :isMemorySystemUsed="isMemorySystemUsed" @goCardGrid="showCardWindow" :keyTopics="keyTopics"
                  @dragStart="handleDragStart" @dragEnd="handleDragEnd" :rounds="rounds" :portraitStates="portraitStates"
                  :choosedCardIdList="choosedCardIdList" @goCardGridWithoutMaking="showCardWindowWithoutMaking"
                  :subSceneName="subSceneName" :sceneName="sceneName" :openCardId="openCardId" :chosenContent="chosenContent"
                  :fileNameList="fileNameList" @updateFileCardBanStyle="updateFileCardBanStyle" @pinCard="pinCard" @retryCompleted="handleRetryCompleted"
                  @scrollToCardGridTop="handleScrollToCardGridTop" @clearCardSingleMaking="handleClearCardSingleMaking"
                  :coreKeyword="coreKeyword"
                  :crossNotebookContext="isCrossNotebookContext">
                </ChatWindow>
              </div>
            </div>
          </div>


          <div :class="lowerhover ? 'chat-down-none' : 'chat-down'">
            <div class="chat-input-box">
              <div class="chat-input-boxup">
                <div class="chat-boxup-button-model" @click="showModel" style="display: none;">
                </div>
                <!-- <div class="chat-boxup-button-voice" @click="showVoice">
                </div> -->
                <div class="chat-boxup-button-voice" @click="showSpeakDialog">
                </div>
                <!-- <div class="chat-boxup-list">
                  <div class="chat-boxup-list-item" v-for="(item, index) in this.questionContents" :key="index"
                    @click="handleQuestionClick(item)" :class="{ 'blue-bg': item.includes('xxx') }">
                    {{ (index + 1) + '.' + item }}
                  </div>
                </div> -->
                <div class="chat-boxup-list">
                  <div class="chat-boxup-list-item" v-for="(item, index) in this.questionContents" :key="index"
                    :class="{ 'blue-bg': item.includes('xxx') }">
                    
                    <!-- 序号部分 - 点击可编辑 -->
                    <span class="question-number" 
                          @click="handleNumberClick(item)"
                          @dblclick="handleNumberDoubleClick(item)"
                          :title="'点击编辑问题，双击模型赋能'">
                      {{ index + 1 }}.
                    </span>
                    
                    <!-- 主体内容部分 - 根据是否含xxx决定行为 -->
                    <span class="question-content" 
                          @click="handleContentClick(item)">
                      {{ item }}
                    </span>
                  </div>
                </div>
                <div class="chat-boxup-button" :class="{ 'chatBtnChecked': chatBtnChecked }" @click="showChatWindow">
                </div>
              </div>

              <!-- <div class="chat-choose-boxup">
                <div class="bottom-nav-buttons"> -->
                  <!-- <el-button @click="handleClick('陈述型')">陈述型</el-button>
                  <el-button @click="handleClick('平衡型')">平衡型</el-button>
                  <el-button @click="handleClick('创造型')">创造型</el-button> -->
                  <!-- zyr种子, 现在不用了 -->
                  <!-- <select v-model="seedMode" @change="handleSeedModeSelected" class="seedmode-select">
                    <option v-for="option in seedmodeOptionsData" :key="option" :value="option">
                      {{ option }}
                    </option>
                  </select> -->
                  <!-- <span class="history-icon" @click="toggleTooltip" ref="historyBtn" title="回答启用/关闭历史记录">
                    历史
                  </span>
                  <span class="usersum-icon" @click="OnOffSummary" title="回答启用/关闭个人摘要">
                    摘要
                  </span> -->

                  <!-- Tooltip -->
                  <!-- <div
                    v-if="isTooltipOpen"
                    :style="{
                      top: `${tooltipPosition.top}px`,
                      left: `${tooltipPosition.left}px`
                    }"
                    class="tooltip-container"
                  > -->
                    <!-- 多轮历史开关 -->
                    <!-- <div class="toggle-row">
                      <span class="label">启用多轮历史</span>
                      <button
                        @click="OnOffHistory"
                        :class="['toggle-switch', isHistoryUsed ? 'enabled' : '']"
                      >
                        <span :class="['toggle-dot', isHistoryUsed ? 'enabled' : '']">
                        </span>
                      </button>
                    </div> -->

                    <!-- 多轮对话留存轮数 -->
                    <!-- <div class="rounds-container">
                      <div class="rounds-header">
                        <span class="label">记忆轮数</span>
                        <input type="number" min="2" max="10" v-model.number="rounds"
                          class="rounds-input"
                        />
                      </div>
                      <input type="range" min="2" max="10" v-model.number="rounds"
                        class="rounds-slider"
                      />
                      <div class="range-limits">
                        <span>2</span>
                        <span>10</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div> -->

              <div class="chat-input-boxdown">
                <div class="chat-input">
                  <!-- <input type="text" class="chat-input-field" v-model="inputMsg" :placeholder="placeholderText" @keyup.enter="sendMsg"> -->
                  <!-- 处理Enter键发送消息，Shift+Enter插入换行 -->
                  <textarea class="chat-input-field" 
                    v-model="inputMsg" 
                    :placeholder="placeholderText" 
                    @keydown="handleKeyDown"
                  ></textarea>

                  <span class="history-icon" @click="toggleTooltip" ref="historyBtn" title="回答启用/关闭历史记录">
                    历史
                  </span>
                  <span class="usersum-icon" @click="OnOffSummary" title="回答启用/关闭个人摘要">
                    摘要
                  </span>
                  <span
                    class="usersum-icon"
                    :style="{ color: isCrossNotebookContext ? '#409EFF' : '' }"
                    @click="OnOffCrossNotebook"
                    title="开启后问答将自动关联其他相关本子的文档"
                  >
                    跨本
                  </span>

                  <!-- Tooltip -->
                  <div
                    v-if="isTooltipOpen"
                    :style="{
                      top: `${tooltipPosition.top}px`,
                      left: `${tooltipPosition.left}px`
                    }"
                    class="tooltip-container"
                  >
                    <!-- 多轮历史开关 -->
                    <div class="toggle-row">
                      <span class="label">启用多轮历史</span>
                      <button
                        @click="OnOffHistory"
                        :class="['toggle-switch', isHistoryUsed ? 'enabled' : '']"
                      >
                        <span :class="['toggle-dot', isHistoryUsed ? 'enabled' : '']">
                        </span>
                      </button>
                    </div>

                    <!-- 长短记忆注入开关（USER / 场景 / 本子 MEMORY·规矩·日记·快照） -->
                    <div class="toggle-row">
                      <span class="label">启用长短记忆</span>
                      <button
                        @click="OnOffMemorySystem"
                        :class="['toggle-switch', isMemorySystemUsed ? 'enabled' : '']"
                      >
                        <span :class="['toggle-dot', isMemorySystemUsed ? 'enabled' : '']">
                        </span>
                      </button>
                    </div>

                    <!-- 多轮对话留存轮数 -->
                    <div class="rounds-container">
                      <div class="rounds-header">
                        <span class="label">记忆轮数</span>
                        <input type="number" min="2" max="10" v-model.number="rounds"
                          class="rounds-input"
                        />
                      </div>
                      <input type="range" min="2" max="10" v-model.number="rounds"
                        class="rounds-slider"
                      />
                      <div class="range-limits">
                        <span>2</span>
                        <span>10</span>
                      </div>
                    </div>

                    <!-- 跨本子关联 -->
                    <div class="toggle-row">
                      <span class="label">跨本子关联</span>
                      <button
                        @click="OnOffCrossNotebook"
                        :class="['toggle-switch', isCrossNotebookContext ? 'enabled' : '']"
                      >
                        <span :class="['toggle-dot', isCrossNotebookContext ? 'enabled' : '']">
                        </span>
                      </button>
                    </div>
                  </div>

                  <a class="chat-send-button" @click="sendMsg">
                    <i class="chat-send-img"></i>
                  </a>
                </div>
              </div>

              <div class="chat-input-boxfoot"></div>
            </div>
          </div>

        </div>

        <div class="bgc-dialog" v-if="this.showBgcChecked">
          <div class="bgc-dialog-header">
            <h2>选择摘要卡片</h2>
            <div class="close" @click="hideBgcDialog">&times;</div>
          </div>
          <div class="bgc-bgcList">
            <BackgroundCard @update:selectBgc="handleSelectBgcUpdate" @update:bgcList="handleUpdateBgcList"
              :bgcList="bgcList"></BackgroundCard>
          </div>
        </div>

        <div class="model-dialog" v-if="this.showModelChecked">
          <div class="model-dialog-header">
            <h2>选择大模型</h2>
            <div class="close" @click="hideModelDialog">&times;</div>
          </div>
          <div class="model-modelList">
            <ModelCard 
              @update:selectModel="handleSelectModelUpdate" 
              @update:portraitStates="handlePortraitStatesUpdate"
              :activeModel="activeModel"
              :portraitStates="portraitStates"
            ></ModelCard>
            <h2>选择小模型</h2>
            <LittleModelCard 
              @update:selectModel="handleSelectLittleModelUpdate" 
              :activeModel="activeModel"
              :littlePortraitStates="littlePortraitStates"
            ></LittleModelCard>
            <h2>选择多模态小模型</h2>
            <MultimodalLittleModelCard
              @update:selectModel="handleSelectMultimodalLittleModelUpdate"
              :activeModel="activeModel"
              :multimodalLittlePortraitStates="multimodalLittlePortraitStates"
            ></MultimodalLittleModelCard>
          </div>
        </div>

        <div v-if="isLoadingImg" class="loading-overlay">
          <div class="spinner-container">
            <div class="spinner"></div>
          </div>
          <div class="progress-text">{{ '正在加载图片...' }}</div>
        </div>

        <div class="img-dialog" v-if="this.showImgChecked">
          <div class="img-dialog-header">
            <h2
              @dblclick="handleCIDocumentPreviewDoubleClick(curFileInfo.name)"
              @contextmenu.prevent="handleCIDocumentPreviewRightClick(curFileInfo.name)"
              title="双击：图片理解；右键：原草图作 R 层复现图并打开单图迭代工作区"
            >查看图片</h2>

            <!-- 添加HLScore指示器 -->
            <div class="hl-score-indicator" v-if="imgHLScore"
                  @mouseenter="showScoreTooltip = true" 
                  @mouseleave="showScoreTooltip = false">
              <div class="score-circle" 
                  :style="getRatingStyle(imgHLScore)">
                {{ parseFloat(imgHLScore).toFixed(1) }}
              </div>
              
              <!-- 悬浮弹窗 -->
              <div class="score-tooltip" v-if="showScoreTooltip">
                <div class="tooltip-header" :style="getRatingStyle(imgHLScore)">
                  <span class="tooltip-score">{{ parseFloat(imgHLScore).toFixed(1) }}</span>
                  <span class="tooltip-color">{{ imgHLColor }}</span>
                </div>
                <div class="tooltip-content">
                  {{ imgHLReason }}
                </div>
              </div>
            </div>

            <!-- <button class="vbg-cards" @click="startDMTAnalysis">DMT化理解</button> -->
            <button class="vbg-cards" @click="regenerateImgDescription">重新生成图片描述</button>
            <button class="vbg-cards" @click="regenerateImgTopics">重新生成关键词</button>

            <!-- 红蓝卡标闭环控制阈值滑动条 -->
            <div class="threshold-slider-container">
              <label class="threshold-label">红蓝卡标闭环控制阈值:</label>
              <div class="slider-wrapper">
                <ElSlider 
                  v-model="cardScoreThreshold" 
                  :min="0" 
                  :max="5" 
                  :step="0.1" 
                  :show-tooltip="true"
                  :format-tooltip="(val) => val.toFixed(1)"
                  class="threshold-slider"
                />
                <span class="threshold-value">{{ cardScoreThreshold.toFixed(1) }}</span>
              </div>
            </div>

            <div class="close" @click="hideImgDialog">&times;</div>
          </div>
          <div class="img-dialog-body">
            <div class="img-dialog-body-left">
              <img :src="'data:image/png;base64,' + this.imgClicked" alt="Image" />
            </div>
            <div class="img-dialog-body-right">
              <div class="img-dialog-body-rightup" ref="imgDialogText">
                <!-- {{ this.imgClickedText }} -->
                <!-- <AnswerParser :answer="this.imgClickedText" @startReading="startFromIndex" @doubleClickOver="doubleClickOver"/> -->
                <!-- 分页信息显示 -->
                <div class="img-text-pagination-info" v-if="imgTextTotalPages > 1">
                  {{ imgTextPaginationInfo }}
                </div>
                
                <!-- 显示当前页内容 -->
                <AnswerParser :answer="currentImgText" @startReading="startFromIndex" @doubleClickOver="doubleClickOver"/>
                
                <!-- 分页控件 -->
                <div class="img-text-pagination" v-if="imgTextTotalPages > 1">
                  <button 
                    class="pagination-btn" 
                    :disabled="imgTextCurrentPage === 1"
                    @click="prevImgTextPage">
                    ‹ 上一页
                  </button>
                  
                  <span class="pagination-current">
                    {{ imgTextCurrentPage }} / {{ imgTextTotalPages }}
                  </span>
                  
                  <button 
                    class="pagination-btn" 
                    :disabled="imgTextCurrentPage === imgTextTotalPages"
                    @click="nextImgTextPage">
                    下一页 ›
                  </button>
                </div>
              </div>
              <div class="img-dialog-body-rightdown">
                <div class="img-dialog-list">
                  <div class="img-dialog-list-item" v-for="(item, index) in this.imgTopicContents" :key="index"
                    @click="handleImgTopicClick(item)">
                    {{ (index + 1) + '.' + item }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="topic-dialog" v-if="this.showTopicChecked">
          <div class="topic-dialog-header">
            <h2>选择操作</h2>
            <div class="close" @click="hideTopicDialog">&times;</div>
          </div>
          <div class="topic-select-list">
            <div class="topic-list-item" @click="discussTopic">
              <div class="info">
                <div class="info-detail">
                  <div class="name">讨论</div>
                  <div class="detail">进一步讨论某一个话题</div>
                </div>
              </div>
            </div>
            <div class="topic-list-item" @click="illustrateTopic">
              <div class="info">
                <div class="info-detail">
                  <div class="name">解释</div>
                  <div class="detail">进一步解释某一个话题</div>
                </div>
              </div>
            </div>
            <div v-for="question in topicRelQuestions" class="topic-rel-list-item" @click="handleQuestionClick(question)">
              <div class="info">
                <div class="info-detail">
                  <div class="name"> {{ question }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 参数介绍 -->
        <el-dialog v-model="dialogInnerVisible" width="30%" class="myDialogParamInfo" :close-on-press-escape="false">
          <el-form-item label="推荐值: " style="font-weight: bold; color: rgba(39, 42, 55, 0.8)">
            <span>{{ initValue }}</span>
          </el-form-item>
          <el-form-item label="简介: " style="font-weight: bold; color: rgba(39, 42, 55, 0.8)">
            <span>{{ info }}</span>
          </el-form-item>
          <el-form-item label="定义: " style="font-weight: bold; color: rgba(39, 42, 55, 0.8)">
            <span>{{ what }}</span>
          </el-form-item>
        </el-dialog>

        <!-- 参数面板 -->
        <el-dialog v-model="dialogVisible" width="30%" class="myDialogParam" :close-on-press-escape="false">
          <!-- 不同模型的不同参数 -->
          <div class="params-nav-buttons">
            <el-button
              v-for="model in modelList"
              :key="model.name"
              @click="handleParamsModelClick(model.name)"
              :class="{ 'is-active': configModel === model.name }"
            >
              {{ model.displayName }}
            </el-button>
            <!-- <el-button @click="handleParamsModelClick('GPT4')"
              :class="{ 'is-active': configModel === 'GPT4' }">GPT4</el-button>
            <el-button @click="handleParamsModelClick('Mixtral')"
              :class="{ 'is-active': configModel === 'Mixtral' }">Mixtral
              7B×8</el-button>
            <el-button @click="handleParamsModelClick('Kimi')"
              :class="{ 'is-active': configModel === 'Kimi' }">Kimi</el-button>
            <el-button @click="handleParamsModelClick('llama3')"
              :class="{ 'is-active': configModel === 'llama3' }">llama3</el-button>
            <el-button @click="handleParamsModelClick('Claude')"
              :class="{ 'is-active': configModel === 'Claude' }">Claude3.5</el-button>
            <el-button @click="handleParamsModelClick('Deepseek')"
              :class="{ 'is-active': configModel === 'Deepseek' }">Deepseek</el-button> -->
          </div>
 
  


          <div class="spider-web-container">
            <!-- 雷达图标签-->
            <div style="width: 98%; height: 98%; border: 3px solid white; margin: 5px; border-radius: 12px;">

              <radarChart2 :configModel="configModel" :clickClass="clickClass"
                :creativitySatisfaction="creativitySatisfaction" :repetitionSatisfaction="repetitionSatisfaction"
                :comprehensivenessSatisfaction="comprehensivenessSatisfaction" :feedBack="feedBack"
                @feedBackOK="handleFeedBackOK" @paramsUpdate="handleUpdate"></radarChart2>
            </div>
          </div>
        </el-dialog>

        <!-- <el-dialog v-model="showDialog" width="60%" class="createCardQuestion" :close-on-click-modal="false"
          :close-on-press-escape="false">
          <h1 class="cardQuestion">切换子场景</h1>
          <div class="ButtonListContainer">
            <el-button v-for="text in this.subSceneList" class="ButtonList" @click="changeSubScene(text)">
              {{ text }}
            </el-button>
          </div>
        </el-dialog> -->

        <!-- 用户反馈评价对话框 -->
        <el-dialog title="用户反馈评价" v-model="dialogFeedBackVisible" width="30%">
          <button @click="getUseToFinetune">获取使用数据微调小模型</button>
          <div class="feedback-item">
            <span>创意性满意程度</span>
            <el-rate v-model="creativitySatisfaction" show-score text-color="#ff9900" score-template="{value}" />
          </div>

          <div class="feedback-item">
            <span>重复率满意程度</span>
            <el-rate v-model="repetitionSatisfaction" show-score text-color="#ff9900" score-template="{value}" />
          </div>

          <div class="feedback-item">
            <span>全面性满意程度</span>
            <el-rate v-model="comprehensivenessSatisfaction" show-score text-color="#ff9900" score-template="{value}" />
          </div>

          <template #footer>
            <span class="dialog-footer">
              <el-button @click="closeDialog">取消</el-button>
              <el-button type="primary" @click="submitFeedback">提交</el-button>
            </span>
          </template>
        </el-dialog>


        <!-- 此PDF原版显示放到LUI1左下部分left-text里了 -->
        <!-- <el-dialog v-model="showPdfViewer">
          <iframe :src="fileUrl"
            style="width: 100%; height: 440px"
          ></iframe>
        </el-dialog> -->


        <el-dialog 
          title="配置agent角色信息" 
          v-model="dialogPlusVisible" 
          width="30%" 
          class="myDialogPlus"
          :close-on-press-escape="false"
          :close-on-click-modal="false"
        >
          <div class="import-button-container">
            <el-button type="primary" @click="importFromFile">导入</el-button>
            <input type="file" ref="fileInput" style="display: none" accept=".xlsx" @change="handleFileChange" />
          </div>

          <div class="dialog-content">
            <!-- LUI·1加强配置 -->
            <div class="config-section">
              <h3>多agent角色扮演-<span style="color: rgb(203, 81, 81);">主题裂解</span>人机群组增强</h3>
              <el-form ref="formLui1" :model="formLui1" label-width="90px">
                <el-form-item label="群组信息">
                  <el-input v-model="formLui1.groupInfo" placeholder="输入群组信息"></el-input>
                </el-form-item>
                <el-form-item label="角色1身份">
                  <el-input v-model="formLui1.roleIdentity1" placeholder="输入角色1职能"></el-input>
                </el-form-item>
                <el-form-item label="角色1特点">
                  <el-input v-model="formLui1.roleFeature1" placeholder="输入角色1特征描述"></el-input>
                </el-form-item>
                <el-form-item label="角色2身份">
                  <el-input v-model="formLui1.roleIdentity2" placeholder="输入角色2职能"></el-input>
                </el-form-item>
                <el-form-item label="角色2特点">
                  <el-input v-model="formLui1.roleFeature2" placeholder="输入角色2特征描述"></el-input>
                </el-form-item>
                <el-form-item label="回答方式">
                  <el-radio-group v-model="formLui1.responseMethod">
                    <el-radio :label="1">1人工 + 1大模型agent</el-radio>
                    <el-radio :label="2">2大模型agent</el-radio>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="群组目标">
                  <el-input
                    type="textarea"
                    v-model="formLui1.groupObjective"
                    placeholder="输入群组目标说明文本"
                  ></el-input>
                </el-form-item>
                <el-form-item label="核心问题">
                  <el-input type="textarea" v-model="formLui1.coreProblem" placeholder="输入要解决的任务/核心问题"></el-input>
                </el-form-item>
                <el-form-item label="最大轮数">
                  <el-input-number v-model="formLui1.maxRounds" controls-position="right" min="1"></el-input-number>
                </el-form-item>
              </el-form>
            </div>

            <!-- LUI·2加强配置 -->
            <div class="config-section">
              <h3>多agent辩论-<span style="color: rgb(203, 81, 81);">问答追问</span>人机群组增强</h3>
              <el-form ref="formLui2" :model="formLui2" label-width="90px">
                <el-form-item label="角色数">
                  <el-select v-model="formLui2.roleCount" placeholder="请选择参与辩论的角色数">
                    <el-option label="3" value="3"></el-option>
                    <el-option label="4" value="4"></el-option>
                    <el-option label="5" value="5"></el-option>
                  </el-select>
                </el-form-item>

                <el-form-item label="群组信息">
                  <el-input v-model="formLui2.groupInfo" placeholder="输入群组信息"></el-input>
                </el-form-item>

                <el-form-item v-for="(role, index) in formLui2.roles" :key="index" v-bind:label="'角色' + (index + 1) + '信息'">
                  <div>
                    <el-input v-model="role.identity" placeholder="输入角色身份特征"></el-input>
                    <el-input v-model="role.function" placeholder="输入角色职能"></el-input>
                    <el-select v-model="role.responseMethod" placeholder="回答方式">
                      <el-option label="人工" value="human"></el-option>
                      <el-option label="大模型agent" value="agent"></el-option>
                    </el-select>
                  </div>
                </el-form-item>

                <el-form-item label="群组目标">
                  <el-input
                    type="textarea"
                    v-model="formLui2.groupObjective"
                    placeholder="输入群组目标说明文本"
                  ></el-input>
                </el-form-item>

                <el-form-item label="核心问题">
                  <el-input
                    type="textarea"
                    v-model="formLui2.coreProblem"
                    placeholder="输入辩论讨论的群组任务/核心问题"
                  ></el-input>
                </el-form-item>

                <el-form-item label="最大轮数">
                  <el-input-number v-model="formLui2.maxRounds" controls-position="right" :min="2" :max="5"></el-input-number>
                </el-form-item>
              </el-form>
            </div>
          </div>

          <template #footer>
            <span class="dialog-footer">
              <el-button @click="closePlusDialog">取消</el-button>
              <el-button type="primary" @click="submitPlusConfig">确认</el-button>
            </span>
          </template>
        </el-dialog>


        <el-dialog 
          title="主题裂解·人机群组加强" 
          v-model="dialogPlusLUI1" 
          width="30%" 
          class="myDialogPlusLUI1"
          :close-on-press-escape="false"
          :close-on-click-modal="false"
          :before-close="closePlusLUI1Dialog"
        >
          <div v-if="displayScore" class="dialog-content-plus" v-html="formattedLoopHistory"></div>
          <br/>
          <div v-if="displayScore" class="rating-container">
            <span style="color: orangered; font-weight: bold;">主题裂解·红蓝卡标（加强前->加强后）：</span>
            <span class="card-rate-left" :style="{ backgroundColor: colorBeforeStyle }">
              {{ scoreBefore }}
            </span>
            <span class="card-rate-left" :style="{ backgroundColor: colorEndStyle }">
              {{ scoreEnd }}
            </span>
          </div>
          <br/>
          <div v-if="displayScore" class="rating-container">
            <span style="color: orangered; font-weight: bold;">点击替换为修正后的内容，并更新topics：</span>
            <span class="override-icon" @click="overrideLUI1" title="替换为修正后的内容">
              替
            </span>
          </div>

          <img style="width: 700px; height: 350px;" v-if="!displayScore" src="@/assets/img/chatwindow/loading.jpg" alt="Loading" />

          <template #footer>
            <span class="dialog-footer">
              <!-- <el-button @click="closePlusDialog">取消</el-button> -->
              <el-button type="primary" @click="submitPlusLUI1Config">确认</el-button>
            </span>
          </template>
        </el-dialog>


        <el-dialog 
          title="问答追问·人机群组加强" 
          v-model="dialogPlusLUI2" 
          width="30%" 
          class="myDialogPlusLUI2"
          :close-on-press-escape="false"
          :close-on-click-modal="false"
          :before-close="closePlusLUI2Dialog"
        >
          <div v-if="displayScoreLUI2" class="dialog-content-plus" v-html="formattedHistory"></div>
          <br/>
          <div v-if="displayScoreLUI2" class="rating-container">
            <span style="color: orangered; font-weight: bold;">问答追问·红蓝卡标（加强前->加强后）：</span>
            <span class="card-rate-left" :style="{ backgroundColor: colorBeforeStyleLUI2 }">
              {{ scoreBeforeLUI2 }}
            </span>
            <span class="card-rate-left" :style="{ backgroundColor: colorEndStyleLUI2 }">
              {{ scoreEndLUI2 }}
            </span>
            <!-- <img @click="handleButtonClick" class="img-button" src="@/assets/img/pin.png" alt="添加卡片" /> -->
          </div>
          <br/>
          <div v-if="displayScoreLUI2" class="rating-container">
            <span style="color: orangered; font-weight: bold;">点击替换为修正后的内容，并更新追问框：</span>
            <span class="override-icon" @click="overrideLUI2" title="替换为修正后的内容">
              替
            </span>
          </div>

          <img style="width: 700px; height: 350px;" v-if="!displayScoreLUI2" src="@/assets/img/chatwindow/loading.jpg" alt="Loading" />

          <template #footer>
            <span class="dialog-footer">
              <!-- <el-button @click="closePlusDialog">取消</el-button> -->
              <el-button type="primary" @click="submitPlusLUI2Config">确认</el-button>
            </span>
          </template>
        </el-dialog>

        <el-dialog v-model="showAddDirectDialog" width="60%" class="createCardQuestion" :close-on-click-modal="false"
          :close-on-press-escape="false">
          <h1 
            class="cardQuestion" 
            @contextmenu.prevent="handleRightClick"
            @dblclick="handleDoubleClick"
          >
            直接生成卡片
          </h1>
          
          <!-- 隐藏的文件输入框 -->
          <input 
            ref="fileInput" 
            type="file" 
            accept=".txt" 
            style="display: none" 
            @change="handleFileImport"
          />
          <!-- <div
            class="draggable"
            @mousedown="startDrag"
            @mouseup="stopDrag"
            @mousemove="onDrag"
            :style="{ left: position.x + 'px', top: position.y + 'px' }"
          >
            拖拽我
          </div> -->
          <button class="change-multiQAScore" :class="{ 'change-multiQAScore-active': isMultiQAScore || isAppendSuggestions }" @click="changeMultiQAScore()">
            {{ 
              !isMultiQAScore && !isAppendSuggestions 
                ? '启用多QA对打分' 
                : isMultiQAScore && !isAppendSuggestions 
                  ? '追加建议及初始滚动迭代' 
                  : '切回普通生成' 
            }}
          </button>
          <el-form :model="userDefineForm" label-width="80px" class="inline-form">
            <div class="input-button-group">
              <!-- <el-input type="textarea" placeholder="请写出要直接生成卡片的内容" v-model="userDefineForm.userText"></el-input> -->
              <el-input 
                type="textarea" 
                placeholder="请写出要直接生成卡片的内容" 
                v-model="userDefineForm.userText"
                @paste="handlePaste">  <!-- 新增这一行 -->
              </el-input>

              <!-- 添加图片上传组件 -->
              <!-- <div class="actions-row">
                <el-upload
                  class="card-image-upload"
                  action="#"
                  :auto-upload="false"
                  :on-change="handleCardImgFileChange"
                  :limit="1"
                  :file-list="cardImgFileList">
                  <el-button type="default">
                    <i class="el-icon-picture-outline"></i> 传入一张图片（可选）
                  </el-button>
                </el-upload>
              </div> -->
              <div class="actions-row">
                <el-upload
                  class="card-image-upload"
                  action="#"
                  :auto-upload="false"
                  :on-change="handleCardImgFileChange"
                  :on-remove="handleRemove"
                  :limit="1"
                  :file-list="cardImgFileList"
                  drag>  <!-- 添加 drag 属性 -->
                  <div class="upload-content">
                    <i class="el-icon-upload"></i>
                    <div class="upload-text">
                      <span>拖拽图片到此处，或</span>
                      <em>点击上传</em>
                    </div>
                    <div class="upload-tip">支持 Ctrl+V 粘贴图片</div>
                  </div>
                </el-upload>
                
                <!-- 图片预览区域 -->
                <div v-if="imagePreview" class="image-preview">
                  <img :src="imagePreview" alt="预览图片" />
                  <el-button 
                    type="danger" 
                    size="small" 
                    circle 
                    class="remove-btn"
                    @click="removeImage">
                    <i class="el-icon-close"></i>
                  </el-button>
                </div>
              </div>

              <el-button class="userDefineButton" @click="createDirectCard(userDefineForm.userText)">生成</el-button>
            </div>
          </el-form>
        </el-dialog>

        <ASRVoice style="display: none;" ref="ASRVoice" :identifyStatus="true" :showIdentifyTextStatus="true"
          @voiceRecognitionTextChanged="updateVoiceRecognitionText"
          @voiceRecognitionBreaked="updateVoiceRecognitionStatus" />
        <audio ref="audioElement" controls style="display: none;"></audio>

        <!-- 类似chatgpt的语音对话界面 -->
        <el-dialog v-model="dialogSpeakVisible" 
            width="30%" 
            class="myDialogSpeak" 
            :close-on-press-escape="false" 
            :close-on-click-modal="false" 
            :before-close="handleSpeakClose"
            style="background-color: rgba(105, 160, 137, 0.2);"
          >
          <div class="chat-boxup-button-voice" 
              :class="{ 'chat-boxup-button-voice-ban': voiceStatus !== 1 }" 
              :ref="chatBoxUpButtonVoice"
              @click="showVoice">
          </div>
          <!-- 下拉框 -->
          <div class="custom-select-wrapper" @click="toggleDropdown">
            <div class="custom-select-display">
              <span>{{ selectedOptionLabel || '请选择' }}</span>
            </div>
            <div class="custom-select-options" v-if="isOpen">
              <div
                v-for="option in options"
                :key="option.value"
                :class="{ 'is-selected': option.value === selectedOption }"
                @click="selectOption(option)"
                class="custom-select-option"
              >
                {{ option.label }}
              </div>
            </div>
          </div>
          <div class="emotion-select-wrapper" @click="toggleEmotionDropdown">
            <div class="emotion-select-display">
              <span>{{ selectedEmotionOptionLabel || '请选择' }}</span>
            </div>
            <div class="emotion-select-options" v-if="isEmotionOpen">
              <div
                v-for="option in currentOptions"
                :key="option.value"
                :class="{ 'is-selected': option.value === selectedEmotionOption }"
                @click="selectEmotionOption(option)"
                class="emotion-select-option"
              >
                {{ option.label }}
              </div>
            </div>
          </div>

          <!-- <transition name="fade">
            <video style="width: 700px; height: 394px; margin-top: 25px; border-radius: 200px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.4); position: absolute;" 
                autoplay muted loop
                v-if="voiceStatus===1"
                src="@/assets/img/chatwindow/listening.mp4" alt="Listening" />
          </transition> -->
          <video style="width: 700px; height: 394px; margin-top: 32px; border-radius: 200px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.4);" 
              autoplay muted loop
              v-if="voiceStatus===1"
              src="@/assets/img/chatwindow/listening.mp4" 
              alt="Listening" />
          <video style="width: 700px; height: 394px; margin-top: 32px; border-radius: 200px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.4);" 
              autoplay muted loop
              v-if="voiceStatus===0 || voiceStatus===2"
              src="@/assets/img/chatwindow/thinking.mp4" 
              alt="Thinking" />
          <video style="width: 700px; height: 394px; margin-top: 32px; border-radius: 200px; box-shadow: 0 0 10px rgba(0, 0, 0, 0.4);" 
              autoplay muted loop
              v-if="voiceStatus===3"
              src="@/assets/img/chatwindow/speaking.mp4" 
              alt="Speaking" />
          <div style="font-size:15px; font-weight:bold; color:#063214E5; margin-top:17px; text-align:center;" 
              v-if="voiceStatus === 0">正在准备，请等几秒</div>
          <div style="font-size:15px; font-weight:bold; color:#063214E5; margin-top:17px; text-align:center;" 
              v-if="voiceStatus === 1">我正在听您说话</div>
          <div style="font-size:15px; font-weight:bold; color:#063214E5; margin-top:17px; text-align:center;" 
              v-if="voiceStatus === 2">我正在思考，请稍等</div>
          <div style="font-size:15px; font-weight:bold; color:#063214E5; margin-top:17px; text-align:center;" 
              v-if="voiceStatus === 3">请听我回答您</div>
        </el-dialog>
        <!-- 自定义遮罩层 -->
        <transition name="fade">
          <div v-if="dialogSpeakVisible" class="custom-backdrop"></div>
        </transition>

      </el-main>
    </el-container>
  </div>

  <FeedbackMaterialDialog :visible="ciMaterialVisible" :filename="ciMaterialFilename"
    :username="ciMaterialUsername" :scene-name="sceneName" :submitting="ciMaterialSubmitting"
    :initial-context="ciMaterialInitialContext"
    @close="ciMaterialVisible = false" @submit="submitFeedbackMaterial" />

  <!-- 连续图片作业批改面板 -->
  <HomeworkGradingPanel
    ref="homeworkGradingPanelRef"
    v-if="showContinuousImagePanel && (
      (ciActiveResult && ciActiveResult.analysis_type === 'homework_grading')
      || (ciRunningTask && ciRunningTask.analysis_type === 'homework_grading' && (!ciRunningTask.completed || ciRunningTask.error))
    )"
    :activeAnalysisId="ciActiveAnalysisId"
    :activeResult="ciActiveResult"
    :activeRunId="ciHomeworkRunId"
    :homeworkVersions="ciHomeworkVersions"
    :versionsLoading="ciHomeworkVersionsLoading"
    :keyVersionLoading="ciHomeworkKeyVersionLoading"
    :rerunLoading="ciHomeworkRerunLoading"
    :redBlueRetryLoading="ciHomeworkRedBlueRetryLoading"
    :runningTask="ciRunningTask"
    :page-view-only="ciHomeworkPageViewOnly"
    @close="handleCloseContinuousImagePanel"
    @start-pass3="handleCIStartPass3"
    @rerun="handleCIHomeworkRerun"
    @retry-red-blue="handleCIHomeworkRedBlueRetry"
    @switch-version="handleCIHomeworkSwitchVersion"
    @toggle-key-version="handleCIHomeworkToggleKeyVersion"
  />

  <!-- 双科交叉诊断面板 -->
  <CrossSubjectPanel
    v-if="showContinuousImagePanel && ciActiveResult && ciActiveResult.analysis_type === 'cross_subject'"
    :activeResult="ciActiveResult"
    :runningTask="ciRunningTask"
    @close="handleCloseContinuousImagePanel"
  />


  <!-- 连续图片认知理解面板 -->
  <ContinuousImagePanel
    v-if="showContinuousImagePanel && (
      ciActiveResult
        ? (ciActiveResult.analysis_type !== 'homework_grading' && ciActiveResult.analysis_type !== 'cross_subject')
        : !(ciRunningTask && ciRunningTask.analysis_type === 'homework_grading' && !ciRunningTask.completed)
    )"
    :availableAnalyses="ciAvailableAnalyses"
    :activeAnalysisId="ciActiveAnalysisId"
    :activeResult="ciActiveResult"
    :runningTask="ciRunningTask"
    :singleWorkAreaAutoOpenSignal="ciSingleWorkAreaAutoOpenSignal"
    :selectedContextDocs="fileNameList"
    :selectedContextCardIds="choosedCardIdList"
    :sceneName="sceneName"
    :docImportImageFileNames="importAreaImagePool"
    @close="handleCloseContinuousImagePanel"
    @switch-tab="handleCISwitchTab"
    @redo="handleCIRedo"
    @generate-reproduction="handleCIReproductionGenerate"
    @save-reproduction-context="handleCISaveReproductionContext"
    @iterate-reproduction-unit="handleCIIterateReproductionUnit"
    @iterate-reproduction-layout-regions="handleCIIterateReproductionLayoutRegions"
    @auto-iterate-reproduction-round="handleCIAutoIterateReproductionRound"
    @apply-lite-bundle-reproduction="handleCIApplyLiteBundleReproduction"
    @rollback-reproduction-unit="handleCIRollbackReproductionUnit"
  />

  <!-- 批量原草图作 R 层复现图 -->
  <el-dialog
    v-model="ciBatchSketchRDialogVisible"
    title="批量图自动逐张：原草图作 R 层复现图"
    width="520px"
    :close-on-click-modal="!ciBatchSketchR.running"
    :close-on-press-escape="!ciBatchSketchR.running"
    :show-close="!ciBatchSketchR.running"
  >
    <template v-if="!ciBatchSketchR.running">
      <p class="ci-batch-sketch-hint">请选择文档导入区中要处理的图片（将按顺序逐张执行，与右键单张「原草图作 R」相同，不打开单图迭代工作区）。</p>
      <div class="ci-batch-sketch-actions">
        <el-button size="small" @click="ciBatchSketchRSelectAll">全选</el-button>
        <el-button size="small" @click="ciBatchSketchRClearAll">清空</el-button>
      </div>
      <el-checkbox-group v-model="ciBatchSketchRSelected" class="ci-batch-sketch-list">
        <el-checkbox v-for="name in ciBatchSketchRCandidates" :key="name" :label="name">
          {{ name }}
        </el-checkbox>
      </el-checkbox-group>
    </template>
    <template v-else>
      <p>共 {{ ciBatchSketchR.total }} 张 · 已完成 {{ ciBatchSketchR.done }} · 失败 {{ ciBatchSketchR.failed }}</p>
      <p v-if="ciBatchSketchR.skipped">已跳过（已有 R）{{ ciBatchSketchR.skipped }} 张</p>
      <p><b>当前：</b>第 {{ ciBatchSketchR.current }} / {{ ciBatchSketchR.total }} 张</p>
      <p class="ci-batch-sketch-filename">{{ ciBatchSketchR.currentFile }}</p>
      <p v-if="ciRunningTask"><b>步骤：</b>{{ ciRunningTask.section || '处理中' }} ({{ _ciProgressPercent }}%)</p>
      <el-progress :percentage="_ciProgressPercent" :status="ciRunningTask?.error ? 'exception' : undefined" />
    </template>
    <template #footer>
      <el-button v-if="!ciBatchSketchR.running" @click="ciBatchSketchRDialogVisible = false">取消</el-button>
      <el-button
        v-if="!ciBatchSketchR.running"
        type="primary"
        :disabled="!ciBatchSketchRSelected.length"
        @click="confirmBatchSketchR"
      >开始处理（{{ ciBatchSketchRSelected.length }} 张）</el-button>
      <el-button v-else type="danger" disabled>处理中…</el-button>
    </template>
  </el-dialog>

  <!-- <div class="stream-test-section">
    <h3>流式输出测试</h3>
    <div>
      <textarea v-model="testText" placeholder="输入要测试的文本" rows="4" class="test-input"></textarea>
    </div>
    <button @click="testStreamOutput" class="test-button">测试流式输出</button>
    
    <div id="stream-result-container" class="result-container">
      <div class="placeholder">点击按钮开始测试流式输出</div>
    </div>
  </div> -->
</template>

<script>
import Nav from "@/components/Nav.vue";
import ChatWindow from "@/views/pages/chatHome/chatwindow.vue"
import CardWindow from "@/views/pages/cardHome/index.vue"
import VoiceBtn from "@/components/chatWindow/VoiceBtn.vue"
import MainNav from "@/views/mainNav.vue"
import FileList from "@/components/fileWindow/FileList.vue"
import { feedbackMaterialSettings } from '@/api/continuous_image'
import ContinuousImagePanel from "@/components/fileWindow/ContinuousImagePanel.vue"
import HomeworkGradingPanel from "@/components/fileWindow/HomeworkGradingPanel.vue"
import FeedbackMaterialDialog from "@/components/fileWindow/FeedbackMaterialDialog.vue"
import CrossSubjectPanel from "@/components/fileWindow/CrossSubjectPanel.vue"
import { queryCIAnalyses, startCIAnalysis, startHomeworkFeedback, startImageUnderstanding, getCIProgress, getCIResult, redoCIAnalysis, listCIHomeworkVersions, markCIHomeworkVersionKey, rerunCIHomework, retryCIHomeworkRedBlue, startCIReproduction, startCISketchRQuickstart, updateCIReproductionContext, iterateCIReproductionUnit, iterateCIReproductionLayoutRegions, autoIterateCIReproductionRound, applyCILiteBundleToReproduction, rollbackCIReproductionUnit, getCIPdfPageCount, startCIPass3 } from "@/api/continuous_image"
import CardGrid from "@/components/cardWindow/CardGrid.vue"
import CardGridFold from "@/components/cardWindow/CardGridFold.vue"
import ModelCard from "@/components/chatWindow/ModelCard.vue"
import LittleModelCard from "@/components/chatWindow/LittleModelCard.vue"
import MultimodalLittleModelCard from "@/components/chatWindow/MultimodalLittleModelCard.vue"
import BackgroundCard from "@/components/BackgroundCard.vue"
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElRate, ElSelect, ElOption, ElInputNumber, ElUpload, ElNotification, ElProgress, ElSlider, ElMessageBox, ElCheckbox, ElCheckboxGroup } from 'element-plus'
import { h } from 'vue'
import radarChart from '@/components/radar-chart.vue';
import { get_file, get_file_summary, get_file_topics, get_file_text, get_img_text, update_img_text, update_img_text_stream, topic_getRelQuestions, get_card, card_generate_single_card_image } from "@/api/card/get_card"
import { animation } from "@/utils/util";
import { card_evalSFT } from "@/api/card/send_card"
import radarChart2 from '@/components/radar-chart2.vue';
import { getModel, modelHL, modelHLStream, getLittleModel, getMultimodalLittleModel, getDefaultModelsConfig, getDepthSuggestion } from "@/api/getData"
import { getUseToFinetune } from "@/api/getBackData"
import { chat_switch, img_getTopics, asr_chat_send } from "@/api/chat/send_message"
import { test_get_speech_text } from '@/api/test'
import router from '@/router'
import { getSubScene, setNewSubExcel, addCardDirect, multiQAScore, multiQAScorePlus, merge2Responses, getCardsContentByIds } from "@/api/card_zym/card_js";
import { card_upload, card_updateContentById } from "@/api/card/send_card";
import { chat_sendParams, chat_sendSuperParams, agent_LUI1, reget_topics, reget_ques, update_context, execute_commands, question_enhance, enhance_question_with_small_model, generate_cross_document_suggestion_card, update_cross_document_suggestion_card, group_twin_gxx_start, get_group_twin_gxx_progress } from "@/api/chat/send_message"
import { user_exit } from '@/api/user'
import { saveAutomationRecords, checkHasRecords } from "@/api/automation"
import { exportUserData, importUserData } from '@/api/dataExport'
import * as XLSX from 'xlsx';
import ASRVoice from '@/components/xftest.vue'
import AnswerParser from '@/components/chatWindow/AnswerParser.vue';
import { generate_bgc, send_bgc_card, get_bgc_card, update_bgc_card, delete_bgc_card } from "@/api/chat/backgroundcard"
import { startDMTAnalysis, getDMTAnalysisStatus, getDMTAnalysisResult, stopDMTAnalysis } from "@/api/dmt/dmt_analysis"
import { interruptAllOnNewMessage } from "@/api/interrupt"
import { modelManager } from '@/utils/ModelManager.js';
import { API_BASE_URL } from '@/config/apiConfig';
import {
  formatAnalysisResultAsPrompt,
  uploadAudioForAnalysis,
  loadMergedMetadataForInference,
  saveAudioBlockSummary,
  getLongTermUserIdFromAudioOrBlockName,
  getPreviousBlockIdsForBacktrack,
  getBacktrackHistoryPrompt,
  formatBlockIdAsDate
} from '@/api/chat/audio_analysis';
import { callMultimodalLittleModel, formatMultimodalLittleModelResult } from '@/api/chat/multimodal_little_model';

// 将 HYPER_PARAMS_LIST 转换为 params 格式
const params = modelManager.getHyperParamsDictionary();

export default {
  name: "App",
  components: {
    Nav,
    MainNav,
    ChatWindow,
    CardWindow,
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    ElRate,
    ElSelect,
    ElOption,
    ElInputNumber,
    ElUpload,
    ElNotification, 
    ElProgress,
    ElSlider,
    ElMessageBox,
    ElCheckbox,
    ElCheckboxGroup,
    FileList,
    CardGrid,
    CardGridFold,
    ModelCard,
    LittleModelCard,
    MultimodalLittleModelCard,
    radarChart,
    radarChart2,
    VoiceBtn,
    ASRVoice,
    BackgroundCard,
    AnswerParser,
    ContinuousImagePanel,
    HomeworkGradingPanel,
    FeedbackMaterialDialog,
    CrossSubjectPanel
  },
  watch: {
    'formLui2.roleCount': function(newVal, oldVal) {
      this.updateRolesCount();
    },
    subSceneName(newValue, oldValue) {
      if (newValue === '中英对比阅读' || newValue === 'S1:轮廓粗读>>' || newValue === 'S2:结构精读>>' || newValue === 'S3:综合深读>>' || newValue === 'S4:核心辨读>>' || (newValue === 'S5:神经元卡' && ['S1:轮廓粗读>>', 'S2:结构精读>>', 'S3:综合深读>>', 'S4:核心辨读>>'].includes(oldValue))) {
        this.isObjScene = true
        this.chooseEnOrEnZh = 'EnZh'
      } else {
        this.isObjScene = false
        this.chooseEnOrEnZh = 'En'
      }
    },
    dialogSpeakVisible(newValue) {
      if (newValue) {
        this.$nextTick(() => {
          // 对话框和遮罩层已经渲染，可以添加 visible 类
          const backdrop = document.querySelector('.custom-backdrop');
          if (backdrop) {
            backdrop.classList.add('visible');
          }
        });
      } else {
        // 移除 visible 类，遮罩层将开始淡出
        const backdrop = document.querySelector('.custom-backdrop');
        if (backdrop) {
          backdrop.classList.remove('visible');
        }
      }
    },
    dialogVisible(newVal, oldVal) {
      if (newVal === false && oldVal === true) {
        let paramFormData = new FormData();
        const runtime_params = modelManager.getHyperParamsDictionary();
        // let paramString = JSON.stringify(this.params);
        let paramString = JSON.stringify(runtime_params);

        paramFormData.append('params', paramString);
        paramFormData.append('modelID', '1000')
        paramFormData.append('username', localStorage.getItem('userId'));

        // 首先执行 chat_sendParams
        chat_sendSuperParams(paramFormData)
          .then(response => {
            console.log("超参传后端", response['msg']);

          })
      }
    },
  },
  data() {
    return {
      // 🔥 本子信息（用于显示）
      _notebookInfo: null,
      _notebookInfoInterval: null, // 本子信息更新定时器

      // 🔥 快慢思考系统选择（仅用于显示当前状态）
      systemChoice: 0, // 系统选择：0=System2慢思考，1=System1快思考

      // 自动化流程
      recordTargetFile: "",
      recordMode: false,  // 是否处于记录模式
      operationRecords: [],  // 操作记录列表

      isEnhancing: false, // 防止重复点击
      isEnhancingQuestion: false, // 🔥 Tab键触发小模型辅助问题补全的loading状态
      lastQuestion: "", // 记录上一次问的问题，作为追问问题增强的必要上下文
      coreKeyword: null, // 🔥 Tab增强后提取的核心关键词（xxx）

      // 图片文档可能显示红蓝卡标
      imgHLScore: null,
      imgHLColor: null,
      imgHLReason: null,
      showScoreTooltip: false, // 控制悬浮弹窗的显示

      cardScoreThreshold: 3.5, // 红蓝卡标闭环控制阈值，范围0-5，默认3.5

      // 图片摘要分页相关
      imgTextCurrentPage: 1,
      imgTextTotalPages: 1,
      imgTextPageSize: 3000, // 每页最大字符数
      imgTextPages: [], // 分页后的文本数组

      testText: '测试流式输出的示例文本。这里可以输入你想要分析的文本内容。',

      // 卡片add图文化
      cardImgFileList: [], // 用于存储上传的文件列表
      selectedFile: null, // 存储选中的图片文件
      imagePreview: null,  // 新增：图片预览URL

      doubleClick: false,
      selectedIndex: 0, // 存储双击的开始位置
      speech: null, // 用于存储语音合成实例
      isSpeaking: false,

      openCardId: null,   // 最近打开的一张卡片id
      chosenContent: "",  // ctrl+k选中的卡片局部内容

      // 卡片勾选列表
      choosedCardIdList: [],

      // 0：未开始问答；1：点击发送问答开始；2：各窗口问答完整结束
      threeModelQAState: 0,
      ModelContentMerge: "",
      isMainWindowOpen: false,
      validNum: 0,

      clickAdmin: false,
      // 拖拽合并回答相关
      isHighlighted: false,
      activeDragWindow: null,

      keyTopics: [],      // 将提取出的已有的卡片关键词放入此数组，作为此后的备选Tags
      menuVis: false,
      classCardGrid: 'Grid',

      context: {
        beginTime: 0,
        stream: []
      },

      cardMaking: false,
      cardSingleMaking: false,
      /** NK2026：小组 Gxx.md 孪生成进度（轮询 group_twin_gxx_progress） */
      nk2026GroupTwinProgress: { active: false, total: 0, done: 0, message: '' },
      nk2026GroupTwinPollTimer: null,

      // 拖拽测试demo（之后用于卡片拖拽）
      isDragging: false,
      position: { x: 0, y: 0 },
      offset: { x: 0, y: 0 },

      iframeSelected: '',
      // chooseEnOrEnZh: 'EnZh',
      chooseEnOrEnZh: '',
      isObjScene: false,
      isTransPdfReady: false,
      leftPdfViewMode: 0,
      // 类似gpt的语音界面
      isListening: false,
      isSpeaking: false,
      audioContext: null,
      analyser: null,
      microphone: null,
      justCutSpeak: false,
      justCloseSpeak: false,
      dialogSpeakVisible: false,
      voiceStatus: 0,
      isOpen: false,
      selectedOption: 'BV700_V2_streaming',
      selectedOptionLabel: '灿灿 2.0',
      options: [
        { value: 'BV700_V2_streaming', label: '灿灿 2.0' },
        { value: 'BV701_V2_streaming', label: '擎苍 2.0' },
        { value: 'BV705_streaming', label: '炀炀' },
        { value: 'BV405_streaming', label: '甜美小源' },
        { value: 'BV009_streaming', label: '知性女声' },
        { value: 'BV008_streaming', label: '亲切男声' },
        // 更多选项...
      ],
      isEmotionOpen: false,
      selectedEmotionOption: 'no',
      selectedEmotionOptionLabel: '通用',
      emotionCanCanOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },
        { value: 'annoyed', label: '嗔怪' },
        { value: 'happy', label: '开心' },
        { value: 'angry', label: '愤怒' },
        { value: 'hate', label: '厌恶' },
        { value: 'surprise', label: '惊讶' },
        { value: 'sad', label: '悲伤' },
        { value: 'scare', label: '害怕' },
        { value: 'tear', label: '哭腔' },
        { value: 'customer_service', label: '客服' },
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' },
        { value: 'tsundere', label: '傲娇' },
        { value: 'comfort', label: '安慰鼓励' },
        { value: 'conniving', label: '绿茶' },
        { value: 'charming', label: '娇媚' },
        { value: 'radio', label: '情感电台' },
        { value: 'lovey-dovey', label: '撒娇' },
        { value: 'yoga', label: '瑜伽' },
        { value: 'storytelling', label: '讲故事' }
      ],
      emotionQingCangOptions: [
        { value: 'narrator', label: '旁白-舒缓' },
        { value: 'narrator_immersive', label: '旁白-沉浸' },
        { value: 'novel_dialog', label: '平和' },
        { value: 'happy', label: '开心' },
        { value: 'angry', label: '愤怒' },
        { value: 'hate', label: '厌恶' },
        { value: 'surprise', label: '惊讶' },
        { value: 'sad', label: '悲伤' },
        { value: 'scare', label: '害怕' },
        { value: 'tear', label: '哭腔' }
      ],
      emotionYangYangOptions: [
        { value: 'no', label: '通用' },
        { value: 'chat', label: '自然对话' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },
        { value: 'annoyed', label: '嗔怪' },
        { value: 'comfort', label: '安慰鼓励' },
        { value: 'storytelling', label: '讲故事' }
      ],
      emotionTianMeiXiaoYuanOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },        
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' }
      ],
      emotionZhiXingGirlOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },        
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' }
      ],
      emotionQinQieBoyOptions: [
        { value: 'no', label: '通用' },
        { value: 'pleased', label: '愉悦' },
        { value: 'sorry', label: '抱歉' },        
        { value: 'professional', label: '专业' },
        { value: 'serious', label: '严肃' }
      ],

      // 是否启用历史/摘要
      isTooltipOpen: false,
      rounds: 3,
      tooltipPosition: {
        top: 0,
        left: 0
      },
      isHistoryUsed: true,
      isMemorySystemUsed: false,
      isSummaryUsed: false,
      isCrossNotebookContext: false,

      // 卡片直接生成 (含是否启用多QA打分)
      multiQASplit: [],
      isMultiQAScore: false,
      isAppendSuggestions: false,
      userDefineForm: {
        userText: ''
      },
      showAddDirectDialog: false,

      msgPlus: '',            // LUI2 index要替换的内容对应的当时问题
      LUI2_result_index: '',  // LUI2 index要替换的内容，是all_history一部分
      // 这五个是LUI2_agent_plus_dia的红蓝卡标前后对比显示
      displayScoreLUI2: false,
      scoreBeforeLUI2: 1.0,
      colorBeforeLUI2: "紫",
      scoreEndLUI2: 1.0,
      colorEndLUI2: "紫",
      // 这五个是LUI1_agent_plus_dia的红蓝卡标前后对比显示
      displayScore: false,
      scoreBefore: 1.0,
      colorBefore: "紫",
      scoreEnd: 1.0,
      colorEnd: "紫",
      // 这两个控制plus圆形图标的显示
      LUI1_plus: false,
      LUI2_plus: false,
      loop_history: '',
      all_history: '',
      dialogPlusLUI1: false,
      dialogPlusLUI2: false,
      importFile: null, // 用于存储选择的文件对象
      formLui1: {
        groupInfo: '',
        roleIdentity1: '',
        roleFeature1: '',
        roleIdentity2: '',
        roleFeature2: '',
        responseMethod: 1,
        groupObjective: '',
        coreProblem: '',
        maxRounds: 3,
      },
      formLui2: {
        roleCount: 3,
        groupInfo: '',
        roles: [
          // 初始化角色列表，每个角色都有 identity, function, responseMethod, 初始化3个
          { identity: '', function: '', responseMethod: 'agent' },
          { identity: '', function: '', responseMethod: 'agent' },
          { identity: '', function: '', responseMethod: 'agent' },
        ],
        groupObjective: '',
        coreProblem: '',
        maxRounds: 3,
      },
      dialogPlusVisible: false,
      // plus能力总控变量
      isPlus: false,
      subSceneWidth: 0,
      fresh: null,
      fileUrl: '',
      fileTransUrl: '',
      bufferBlobUrls: {},
      useFileCache: true, // 是否使用文件缓存
      cacheExpiration: 7, // 缓存过期天数
      dbName: 'pdfCache',
      dbVersion: 1,

      isLoading: false,
      isLoadingTrans: false,
      isLoadingImg: false,
      isTranslating: false,
      loadingProgress: 0,
      loadingTransProgress: 0,
      loadingText: '准备加载PDF...',
      loadingTransText: '准备加载PDF...',
      totalBytes: 0,
      loadedBytes: 0,
      totalTransBytes: 0,
      loadedTransBytes: 0,

      showPdfViewer: false,
      showTxtViewer: false,

      // 音频播放相关
      isAudioFile: false,
      currentAudioUrl: '',
      currentAudioFileName: '',
      audioReady: false,
      isAudioPlaying: false,
      audioCurrentTime: 0,
      audioDuration: 0,
      audioProgressPercent: 0,
      audioLoading: false,
      audioError: '',

      waitFileNames: [],
      waitFileSizes: [],
      needWaitFile: 0,
      activeIndex: 0,
      bgcList: [
        {
          cid: 0,
          name: '默认背景摘要',
          detail: '此时大模型不具备任何背景知识',
          content: '',
          datetime: '',
          status: 0,
        },
      ],
      feedBack: false,
      dialogFeedBackVisible: false, // 控制对话框显示
      creativitySatisfaction: null, // 创意性满意程度星级
      repetitionSatisfaction: null, // 重复率满意程度星级
      comprehensivenessSatisfaction: null, // 全面性满意程度星级

      curFileInfo: {},
      summaryStreamComplete: false, // 摘要流式输出是否已完成（用于显示“正在等待配图生成中...”）
      seedmodeOptionsData: ['默认', 'topic', 'question'],
      seedMode: '默认',

      // PDF图片处理状态
      pdfImageProcessingStatus: {}, // 记录每个PDF文件的图片处理状态
      imageProcessingCheckInterval: null, // 定时检查间隔

      portraitStates: {}, // 保存每个模型的开关状态
      littlePortraitStates: {}, // 保存小模型的状态（灰、绿）
      multimodalLittlePortraitStates: {}, // 保存多模态小模型状态（灰、绿）

      activeModel: 'GPT4',       // 用于跟踪当前激活的模型，更改参数表
      configModel: 'GPT4',
      currentModule: 0,      // 0：左窄右宽，1：左显示文件示图变宽
      currentStyle: 0,       // 0: 亮风格，1: 暗风格
      dialogVisible: false,       // 控制对话框显示/隐藏
      dialogInnerVisible: false,  // 各参数的详细显示
      dialogVisibleInner: false,  // 保留原有手动调节参数
      // showMask: false,         // 控制遮罩层显示的变量
      cardUpdate: false,          // 是否有卡片更新/生成
      cardUpdateStream: false,
      cardOpeUpdStream: false,
      HLContent: new Map(),
      HLOpeContent: new Map(),
      clickClass: '陈述型',       // 对话界面点选class更新Navigator显示
      navigatorCreated: false,    // Navigator是否已经创建
      paramsClass: '陈述型',
      initValue: '',
      info: '',
      what: '',
      lowerhover: false,


      params: {
        GPT4: {
          temperature: 0.7,
          top_p: 0.95,
          frequency_penalty: 1.0,
          presence_penalty: 1.0,
          max_tokens: 2048,
          n: 1
        },
        Mixtral: {
          temperature: 0.1,
          top_p: 0.95,
          top_k: 15,
          max_length: 2048,
          do_sample: 1,
          num_beams: 1,
          num_beam_groups: 1,
          num_return_sequences: 1,
          repetition_penalty: 0.5,
          max_new_tokens: 2048,
          diversity_penalty: 1.1,
          length_penalty: 0
        },
        Kimi: {
          temperature: 0.7,
          top_p: 0.95,
          frequency_penalty: 1.0,
          presence_penalty: 1.0,
          max_tokens: 2048,
          n: 1
        },
        llama3: {
          temperature: 0.7,
          top_p: 0.95,
          frequency_penalty: 1.0,
          presence_penalty: 1.0,
          max_tokens: 2048
        },
        Claude: {
          temperature: 0.7,
          top_p: 0.95,
          top_k: 30,
          max_tokens: 2048
        },
        Deepseek: {
          temperature: 0.7,
          top_p: 0.95,
          frequency_penalty: 1.0,
          presence_penalty: 1.0,
          max_tokens: 2048
        },
        DeepseekR1: {
          temperature: 0.7,
          top_p: 0.95,
          frequency_penalty: 1.0,
          presence_penalty: 1.0,
          max_tokens: 2048
        },
        Gemini: {
          temperature: 0.7,
          top_p: 0.95,
          frequency_penalty: 1.0,
          presence_penalty: 1.0,
          max_tokens: 2048
        },
        Qwq: {
          temperature: 0.7,
          top_p: 0.95,
          frequency_penalty: 1.0,
          presence_penalty: 1.0,
          max_tokens: 2048
        },
      },

      selectAllClass: 'left-selectall-button',
      chatBtnChecked: false,
      flexBtnChecked: false,
      displaySummaryBtn: false,
      depthSuggestionForSummary: '',  // 存储摘要深度建议

      multimodalAnalysisResult: null, // 当前音频多模态结果（发送前拼接）
      backtrackHistoryPrompt: null,   // 回溯历史摘要（发送前拼接）
      curMultimodalLittleInfo: null,

      showBgcChecked: false,          // 显示选择摘要的对话框
      showModelChecked: false,       // 显示选择模型的对话框
      showTopicChecked: false,       // 显示选择topic的对话框
      showImgChecked: false,         // 显示文档图片的对话框
      showVoiceChecked: false,
      curModelInfo: null,
      curModelInfoUp: null,
      curModelInfoDown: null,
      inputMsg: "",
      fileNameList: [],
      importAreaImagePool: [],
      leftSelectList: [],
      rightSelectList: [],
      fileName: '',
      topicContents: ['正在获取topics'],
      questionContents: ['正在获取相关问题...'],
      imgTopicContents: ['正在生成关键词...'],
      imgTopicQuestionContents: ['相关问题1', '相关问题2', '相关问题3'],
      topicRelQuestions: ['正在获取相关问题...'],   // topicdialog里面除了讨论和理解，还有topic相关问题
      imgContents: '',
      imgClickedText: '正在获取图片和描述',
      answerList: [],
      shouldClearQuestionsOnNextUpdate: false,  // 标记是否需要在下次追问更新时清空（用于跨问答清空）

      closeMain: false,
      closeUp: false,
      closeDown: false,
      toBeSwitched: 0,          // 正在被选择要切换模型的div，0是左，1是右上，2是右下
      isQuestionWindow1: true,  // 是返回相关问题的窗口
      isQuestionWindow2: false,
      isQuestionWindow3: false,

      sceneName: localStorage.getItem('sceneName'),
      currentBgc: {
        name: '默认背景摘要'
      },
      subSceneList: ["test1", "test2"],
      subSceneName: '',
      showDialog: false,
      // 🔥 卡片勾选状态管理：保存初始状态和卡片状态历史
      initialFileState: null,  // 初始的文件勾选和子场景状态
      cardStateHistory: [],    // 卡片状态历史：[{cardId, fileNameList, subSceneName}, ...]
      voiceRecognizing: false,  // 正在语音识别
      voiceRecognitionText: '',

      // DMT分析相关 - 改为支持多任务的字典结构
      dmtTasks: {}, // 存储所有DMT任务的状态和进度信息
      // 每个任务的结构：
      // {
      //   [taskId]: {
      //     status: 'processing'|'completed'|'failed',
      //     progress: 0-100,
      //     currentStage: '阶段描述',
      //     progressDialog: null,
      //     configFile: null,
      //     imageFile: null
      //   }
      // }

      // 连续图片认知理解相关（新架构）
      showContinuousImagePanel: false,
      ciMaterialVisible: false,
      ciMaterialSubmitting: false,
      ciMaterialFilename: "",
      ciMaterialUsername: "",
      ciMaterialTarget: "grading",
      ciMaterialInitialContext: null,
      ciMaterialRerunId: '',
      // 面板查询到的可用分析列表 { singles: [], groups: [] }
      ciAvailableAnalyses: { singles: [], groups: [] },
      // 当前正在查看/运行的 analysis_id
      ciActiveAnalysisId: '',
      // 当前展示的完整结果
      ciActiveResult: null,
      // 运行中任务进度 { task_id, analysis_id, section, item, total, error } | null
      ciRunningTask: null,
      ciHomeworkRunId: 'current',
      ciHomeworkAnalysisId: '',
      ciHomeworkVersions: [],
      ciHomeworkVersionsLoading: false,
      ciHomeworkKeyVersionLoading: false,
      ciHomeworkRerunLoading: false,
      ciHomeworkRedBlueRetryLoading: false,
      ciHomeworkToolbarReady: false,
      ciHomeworkToolbarFilename: '',
      ciHomeworkPageViewOnly: false,
      ciHomeworkPendingPageView: '',
      ciSingleWorkAreaAutoOpenSignal: null,
      ciReproductionConfirming: '',
      ciPollTimer: null,
      // ElNotification 实例引用
      ciProgressNotification: null,
      ciBatchSketchRDialogVisible: false,
      ciBatchSketchRCandidates: [],
      ciBatchSketchRSelected: [],
      ciBatchSketchR: {
        running: false,
        total: 0,
        current: 0,
        currentFile: '',
        done: 0,
        failed: 0,
        skipped: 0,
      },
      ciSuppressAutoOpenWorkArea: false,
      ciSuppressOpenCIPanelOnComplete: false,
      _ciBatchWaitResolve: null,
      _ciBatchWaitReject: null,
      _ciBatchWaitTimer: null,
    };
  },
  computed: {
    // 🔥 本子信息（当前本子名及有四色DMT属性的卡片数/卡片总数）
    notebookInfo() {
      // 🔥 使用data属性，通过watch更新，因为computed中访问$refs可能时机不对
      return this._notebookInfo || null;
    },

    // 连续图片理解：勾选文件中是否包含图片或 PDF（用于内部判断，不再显示按钮）
    _ciImageFiles() {
      if (!this.fileNameList || !this.fileNameList.length) return []
      const imgExts = ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff']
      return this.fileNameList.filter(name => {
        const lower = (name || '').toLowerCase()
        return lower.endsWith('.pdf') || imgExts.some(ext => lower.endsWith(ext))
      })
    },
    // 连续图片理解任务是否正在运行中
    ciAnalysisRunning() {
      return !!(this.ciRunningTask && !this.ciRunningTask.completed)
    },
    // 连续图片理解进度百分比（用于通知组件）
    _ciProgressPercent() {
      if (!this.ciRunningTask || this.ciRunningTask.total <= 0) return 10
      return Math.min(Math.round((this.ciRunningTask.item / this.ciRunningTask.total) * 100), 100)
    },

    placeholderText() {
      if (this.curModelInfo === null) {
        return '请先选择主窗口模型';
      }
      return `(主窗口)向${this.curModelInfo.name}提问...`;
    },
    // 计算属性：是否应该显示图片（排除无图片的PDF）
    shouldShowImages() {
      if (!this.curFileInfo || !this.curFileInfo.name) {
        return false;
      }
      
      // 如果不是PDF文件，按原逻辑显示
      if (!this.curFileInfo.name.endsWith('.pdf')) {
        return this.curFileInfo.imgs && this.curFileInfo.imgs.length > 0;
      }
      
      // 对于PDF文件，检查是否有图片
      const fileName = this.curFileInfo.name;
      const status = this.pdfImageProcessingStatus[fileName];
      
      // 如果状态显示图片总数为0，不显示图片区域
      if (status && status.image_count === 0) {
        return false;
      }
      
      // 其他情况按原逻辑显示
      return this.curFileInfo.imgs && this.curFileInfo.imgs.length > 0;
    },
    currentOptions() {
      switch (this.selectedOptionLabel) {
        case '灿灿 2.0':
          return this.emotionCanCanOptions;
        case '擎苍 2.0':
          return this.emotionQingCangOptions;
        case '炀炀':
          return this.emotionYangYangOptions;
        case '甜美小源':
          return this.emotionTianMeiXiaoYuanOptions;
        case '知性女声':
          return this.emotionZhiXingGirlOptions;
        case '亲切男声':
          return this.emotionQinQieBoyOptions;
        default:
          return this.emotionCanCanOptions;
      }
    },
    maxIndex() {
      return this.subSceneList.length;
    },
    // 这两个是LUI1加强显示前后卡标
    colorBeforeStyle() {
      return this.color(this.scoreBefore, this.colorBefore);
    },
    colorEndStyle() {
      return this.color(this.scoreEnd, this.colorEnd);
    },
    // 这两个是LUI2加强显示前后卡标
    colorBeforeStyleLUI2() {
      return this.color(this.scoreBeforeLUI2, this.colorBeforeLUI2);
    },
    colorEndStyleLUI2() {
      return this.color(this.scoreEndLUI2, this.colorEndLUI2);
    },

    // 图片摘要分页相关计算属性
    currentImgText() {
      if (this.imgTextPages.length === 0) {
        return '';
      }
      return this.imgTextPages[this.imgTextCurrentPage - 1] || '';
    },
    
    // 分页信息显示
    imgTextPaginationInfo() {
      if (this.imgTextTotalPages <= 1) {
        return '';
      }
      return `第 ${this.imgTextCurrentPage} 页，共 ${this.imgTextTotalPages} 页`;
    },

    formattedHistory() {
      // 格式化 all_history 文本
      let history = this.all_history;
      this.formLui2.roles.forEach((role, index) => {
        const roleRegex = new RegExp(`(${role.identity})(\\(.*?\\):)`, 'g');
        if(index === 0)
          history = history.replace(roleRegex, '<span style="color: blue; font-weight: bold;">$1</span><span style="color: purple; font-weight: bold;">$2</span>');
        else
          history = history.replace(roleRegex, '<br/><span style="color: blue; font-weight: bold;">$1</span><span style="color: purple; font-weight: bold;">$2</span>');
      });
      history = history.replace(/第(\d+)轮/g, '<br/><br/><span style="color: darkred; font-weight: bold;">第$1轮</span>');
      const roleEndRegex = new RegExp("(问答追问最终修正结果:)", 'g');
      history = history.replace(roleEndRegex, '<br/><br/><span style="color: orangered; font-weight: bold;">$1</span>');
      return history;
    },
    formattedLoopHistory() {
      // 格式化 loop_history 文本
      let history = this.loop_history;
      const role1Regex = new RegExp(`(${this.formLui1.roleIdentity1})(\\(.*?\\):)`, 'g');
      history = history.replace(role1Regex, '<br/><span style="color: blue; font-weight: bold;">$1</span><span style="color: purple; font-weight: bold;">$2</span>');
      const role2Regex = new RegExp(`(${this.formLui1.roleIdentity2})(\\(.*?\\):)`, 'g');
      history = history.replace(role2Regex, '<br/><span style="color: blue; font-weight: bold;">$1</span><span style="color: purple; font-weight: bold;">$2</span>');
      const roleEndRegex = new RegExp("(主题裂解最终修正结果:)", 'g');
      history = history.replace(roleEndRegex, '<br/><br/><span style="color: orangered; font-weight: bold;">$1</span>');
      return history;
    },
  },
  mounted() {
    console.log('mounted');

    // 🔥 新增：读取用户的system选择
    const savedChoice = localStorage.getItem('systemChoice');
    this.systemChoice = savedChoice !== null ? parseInt(savedChoice) : 0;
    const savedCrossNb = localStorage.getItem('crossNotebookContext');
    this.isCrossNotebookContext = savedCrossNb === 'true';
    const savedMem = localStorage.getItem('isMemorySystemUsed');
    if (savedMem !== null) {
      this.isMemorySystemUsed = savedMem !== 'false';
    }
    console.log('[MainPage] System Choice:', this.systemChoice === 0 ? 'System2(慢思考)' : 'System1(快思考)');

    this.handleUpdateBgcList();
    this.context.beginTime = localStorage.getItem('time')
    this.audioElement = this.$refs.audioElement; // 设置播放tts音频的变量
    let modelInfoList = getModel();
    // this.curModelInfo = modelInfoList[0];
    // this.curModelInfoUp = modelInfoList[1];
    // this.curModelInfoDown = modelInfoList[2];

    // 从后端API读取admin配置的三窗口默认模型
    getDefaultModelsConfig().then(response => {
      if (response.error_num === 0) {
        const defaultModels = response.config;
        console.log('[三窗口] 从服务器加载admin配置的默认模型:', defaultModels);
        
        // 根据模型ID查找对应的模型信息
        const mainModel = modelInfoList.find(m => m.id === defaultModels.main);
        const topRightModel = modelInfoList.find(m => m.id === defaultModels.topRight);
        const bottomRightModel = modelInfoList.find(m => m.id === defaultModels.bottomRight);
        
        // 只有找到对应模型时才替换，并激活对应的portraitState
        if (mainModel) {
          this.curModelInfo = mainModel;
          // 激活主窗口模型
          const mainIndex = this.idToIndex(mainModel.id);
          this.portraitStates[mainIndex] = true;
          console.log('[三窗口] 主窗口模型设置为:', mainModel.abbreviation, mainModel.id, 'index:', mainIndex);
        }
        
        if (topRightModel) {
          this.curModelInfoUp = topRightModel;
          // 激活右上窗口模型
          const topRightIndex = this.idToIndex(topRightModel.id);
          this.portraitStates[topRightIndex] = true;
          console.log('[三窗口] 右上窗口模型设置为:', topRightModel.abbreviation, topRightModel.id, 'index:', topRightIndex);
        }
        
        if (bottomRightModel) {
          this.curModelInfoDown = bottomRightModel;
          // 激活右下窗口模型
          const bottomRightIndex = this.idToIndex(bottomRightModel.id);
          this.portraitStates[bottomRightIndex] = true;
          console.log('[三窗口] 右下窗口模型设置为:', bottomRightModel.abbreviation, bottomRightModel.id, 'index:', bottomRightIndex);
        }

        // 关闭其他未使用的模型（必须用 sequence 做 key，与 idToIndex / 发送校验一致）
        this.modelList.forEach((model) => {
          if (model.id !== mainModel?.id && model.id !== topRightModel?.id && model.id !== bottomRightModel?.id) {
            this.portraitStates[model.sequence] = false;
          }
        });
        // 再次确保三窗口模型为激活，防止被误清
        if (mainModel) this.portraitStates[this.idToIndex(mainModel.id)] = true;
        if (topRightModel) this.portraitStates[this.idToIndex(topRightModel.id)] = true;
        if (bottomRightModel) this.portraitStates[this.idToIndex(bottomRightModel.id)] = true;
        
        console.log('[三窗口] portraitStates状态:', this.portraitStates);
        
        console.log('[三窗口] 最终模型配置:', {
          main: this.curModelInfo.abbreviation,
          topRight: this.curModelInfoUp.abbreviation,
          bottomRight: this.curModelInfoDown.abbreviation
        });
      } else {
        console.error('[三窗口] 加载默认模型配置失败，使用默认值');
      }
    }).catch(error => {
      console.error('[三窗口] 加载默认模型配置异常，使用默认值:', error);
    });

    // 先使用默认值初始化，等API返回后再更新
    this.curModelInfo = modelInfoList[0];
    this.curModelInfoUp = modelInfoList[1];
    this.curModelInfoDown = modelInfoList[2];


    let LittleModelInfoList = getLittleModel();
    this.curLittleInfo = LittleModelInfoList[0];
    let multimodalLittleModelInfoList = getMultimodalLittleModel();
    this.curMultimodalLittleInfo = multimodalLittleModelInfoList[0] || null;

    // 进入本子时，重置小模型ID为3003
    localStorage.setItem('currentLittleModelId', "3003");
    // 进入本子时，重置多模态小模型ID为4002（CaReAQA）
    localStorage.setItem('currentMultimodalLittleModelId', this.curMultimodalLittleInfo ? this.curMultimodalLittleInfo.id : "4002");

    // 切换模型：1002(GPT4o)
    let formData = new FormData();
    formData.append('model_id', "1002");
    formData.append('username', localStorage.getItem('userId'));
    chat_switch(formData).then(data => {
    }).catch(error => {
      console.error("An error occurred:", error); // 错误处理
    });

    this.$message.success('已选主窗口模型：' + modelInfoList[0].name);

    localStorage.setItem('seed', '默认');
    
    this.curFileInfo.content = "正在生成摘要中";
    this.curFileInfo.text = "正在获取正文内容";
    this.topicContents = ['正在获取topic'];
    localStorage.setItem('seed', '默认');
    // 组件挂载后初始化雷达图
    // this.initRadarChart();

    // 确保所有子场景按钮已经被渲染
    this.$nextTick(() => {
      // 计算并设置每个按钮的 left 属性
      for (let index in this.$refs.buttons) {
        if (this.$refs.buttons[index]) {
          let leftValue = this.getButtonLeft(parseInt(index)) + 200 + 10*index;
          this.$refs.buttons[index].style.left = `${leftValue}px`;
        }
      }
      if (this.$refs.buttonPlus) {
        let leftValue = this.getButtonLeft(parseInt(this.maxIndex)) + 200 + 10*(this.maxIndex);
        console.log("按钮", this.$refs.buttonPlus)
        this.$refs.buttonPlus.style.left = `${leftValue}px`;
        this.subSceneWidth = leftValue
      }
    });

    // 初始化模型状态：一律按 sequence 建 key（勿用数组下标，否则会与发送校验错位）
    this.modelList = getModel();
    this.modelList.forEach((model, index) => {
      // 临时默认：列表前 3 个模型开启，随后会被 admin 三窗口配置覆盖
      this.portraitStates[model.sequence] = index === 0 || index === 1 || index === 2;
    });

    this.littleModelList = getLittleModel();
    this.littleModelList.forEach((_, index) => {
      // true = green, false = grey
      if(index === 0)
        this.littlePortraitStates[index] = true;
      else
        this.littlePortraitStates[index] = false;
    });
    this.multimodalLittleModelList = getMultimodalLittleModel();
    this.multimodalLittleModelList.forEach((_, index) => {
      this.multimodalLittlePortraitStates[index] = (index === 0);
    });

    if (localStorage.getItem('byadmin') !== 'true' && localStorage.getItem('byuplevel') !== 'true') {
      this.startPeriodicUpdate();
    }
    // 当组件挂载后，添加退出事件监听器
    window.addEventListener('beforeunload', this.handleBeforeUnload);
    // 监听区域外点击以改变或关闭多轮对话配置tooltip
    document.addEventListener('click', this.handleClickOutside)
    window.addEventListener('scroll', this.updateTooltipPosition)
    window.addEventListener('resize', this.updateTooltipPosition)

    // 添加全局粘贴事件监听
    document.addEventListener('paste', this.handleGlobalPaste);

    // 🔥 初始化本子信息，并设置定时更新
    this.$nextTick(() => {
      setTimeout(() => { 
        this.updateNotebookInfo();
      }, 2000); // 2s后检查

      setTimeout(() => { 
        this.updateNotebookInfo();
      }, 6000); // 6s后再次检查
      
      setTimeout(() => { 
        this.updateNotebookInfo();
      }, 10000); // 10s后再次检查

      this._notebookInfoInterval = setInterval(() => {
        this.updateNotebookInfo();
      }, 300000); // 每5min更新一次
    });
  },
  beforeDestroy() {
    console.log('beforeDestroy');
    // 当组件销毁前，移除事件监听器
    window.removeEventListener('beforeunload', this.handleBeforeUnload);
    // 组件销毁前停止定时器
    // this.stopPeriodicUpdate(); 
    document.removeEventListener('click', this.handleClickOutside)
    window.removeEventListener('scroll', this.updateTooltipPosition)
    window.removeEventListener('resize', this.updateTooltipPosition)

    // 移除事件监听
    document.removeEventListener('paste', this.handleGlobalPaste);
    // 组件销毁时清理
    this.cleanupBlobUrl();
  },
  beforeUnmount() {
    console.log('beforeUnmount');
    // 当组件销毁前，移除事件监听器
    window.removeEventListener('beforeunload', this.handleBeforeUnload);
    // 组件销毁前停止定时器
    // this.stopPeriodicUpdate(); 
    document.removeEventListener('click', this.handleClickOutside)
    window.removeEventListener('scroll', this.updateTooltipPosition)
    window.removeEventListener('resize', this.updateTooltipPosition)

    // 移除事件监听
    document.removeEventListener('paste', this.handleGlobalPaste);
    // 组件销毁时清理
    this.cleanupBlobUrl();

    // 🔥 清理本子信息定时器
    if (this._notebookInfoInterval) {
      clearInterval(this._notebookInfoInterval);
      this._notebookInfoInterval = null;
    }

    if (this.nk2026GroupTwinPollTimer) {
      clearInterval(this.nk2026GroupTwinPollTimer);
      this.nk2026GroupTwinPollTimer = null;
    }

    // 清理连续图片理解轮询定时器
    this.clearCIPollTimer();
    this._closeCIProgressNotification();
  },
  activated() {
    console.log('activated');
    // this.stopPeriodicUpdate();
    // if (localStorage.getItem('byadmin') !== 'true' && localStorage.getItem('byuplevel') !== 'true') {
    //   this.startPeriodicUpdate();
    // }
  },
  deactivated() {
    console.log('deactivated');
    // 清理图片处理状态检查
    this.stopImageProcessingCheck();
    // this.stopPeriodicUpdate();
    // // 移除事件监听器
    // window.removeEventListener('beforeunload', this.handleBeforeUnload);
    // // 停止定时器
    // document.removeEventListener('click', this.handleClickOutside)
    // window.removeEventListener('scroll', this.updateTooltipPosition)
    // window.removeEventListener('resize', this.updateTooltipPosition)
  },
  created() {
    console.log('created');
    let modelInfoList = getModel();
    // this.curModelInfo = modelInfoList[0];
    // this.curModelInfoUp = modelInfoList[1];
    // this.curModelInfoDown = modelInfoList[2];
    
    // 先使用默认值初始化
    this.curModelInfo = modelInfoList[0];
    this.curModelInfoUp = modelInfoList[1];
    this.curModelInfoDown = modelInfoList[2];
    
    // 从后端API读取admin配置的三窗口默认模型（异步）
    getDefaultModelsConfig().then(response => {
      if (response.error_num === 0) {
        const defaultModels = response.config;
        console.log('[三窗口-created] 从服务器加载admin配置的默认模型:', defaultModels);
        
        // 根据模型ID查找对应的模型信息
        const mainModel = modelInfoList.find(m => m.id === defaultModels.main);
        const topRightModel = modelInfoList.find(m => m.id === defaultModels.topRight);
        const bottomRightModel = modelInfoList.find(m => m.id === defaultModels.bottomRight);
        
        // 只有找到对应模型时才替换，并激活对应的portraitState
        if (mainModel) {
          this.curModelInfo = mainModel;
          const mainIndex = this.idToIndex(mainModel.id);
          this.portraitStates[mainIndex] = true;
          console.log('[三窗口-created] 主窗口模型设置为:', mainModel.abbreviation, mainModel.id, 'index:', mainIndex);
        }
        
        if (topRightModel) {
          this.curModelInfoUp = topRightModel;
          const topRightIndex = this.idToIndex(topRightModel.id);
          this.portraitStates[topRightIndex] = true;
          console.log('[三窗口-created] 右上窗口模型设置为:', topRightModel.abbreviation, topRightModel.id, 'index:', topRightIndex);
        }
        
        if (bottomRightModel) {
          this.curModelInfoDown = bottomRightModel;
          const bottomRightIndex = this.idToIndex(bottomRightModel.id);
          this.portraitStates[bottomRightIndex] = true;
          console.log('[三窗口-created] 右下窗口模型设置为:', bottomRightModel.abbreviation, bottomRightModel.id, 'index:', bottomRightIndex);
        }

        // 关闭其他未使用的模型（必须用 sequence 做 key，与 idToIndex / 发送校验一致）
        this.modelList.forEach((model) => {
          if (model.id !== mainModel?.id && model.id !== topRightModel?.id && model.id !== bottomRightModel?.id) {
            this.portraitStates[model.sequence] = false;
          }
        });
        if (mainModel) this.portraitStates[this.idToIndex(mainModel.id)] = true;
        if (topRightModel) this.portraitStates[this.idToIndex(topRightModel.id)] = true;
        if (bottomRightModel) this.portraitStates[this.idToIndex(bottomRightModel.id)] = true;
        
        console.log('[三窗口-created] portraitStates状态:', this.portraitStates);
      }
    }).catch(error => {
      console.error('[三窗口-created] 加载默认模型配置异常，使用默认值:', error);
    });

    
    this.getSubSceneList();
    console.log("场景分支：", this.subSceneList)
    this.subSceneName = this.subSceneList[0];
    localStorage.setItem('subSceneName', this.subSceneName);
    if(this.subSceneName === '中英对比阅读' || this.sceneName.includes("中英文专业阅读"))
      this.isObjScene = true

    // 半自动化：检查是否有记录
    this.checkAutomationRecords();

    this.cleanCacheOnMount();
  },
  // 添加离开路由前的保存
  // beforeRouteLeave(to, from, next) {
  //   if(to.path === '/live') {
  //     // 只有去 live 页面时才保存数据
  //     const mainPageData = {
  //       mainData: this.$data,  // 保存主页面数据
  //       chatWindowLeftData: this.$refs.ChatWindow?.$data,  // 保存左侧 ChatWindow 数据
  //       chatWindowUpData: this.$refs.ChatWindowUp?.$data,  // 保存上方 ChatWindow 数据
  //       chatWindowDownData: this.$refs.ChatWindowDown?.$data,  // 保存下方 ChatWindow 数据
  //       fileListData: this.$refs.FileList?.$data  // 保存 FileList 组件数据
  //     };
  //     sessionStorage.setItem('mainPageFullData', JSON.stringify(mainPageData));
  //   }
  //   next();
  // },
  // 添加进入路由前的恢复
  // beforeRouteEnter(to, from, next) {
  //   next(vm => {
  //     if(from.path === '/live') {
  //       // 从 live 页面返回时恢复数据
  //       const savedData = JSON.parse(sessionStorage.getItem('mainPageFullData'));
  //       if(savedData) {
  //         // 恢复主页面数据
  //         Object.assign(vm.$data, savedData.mainData);
          
  //         // 等待子组件挂载完成后恢复它们的数据
  //         vm.$nextTick(() => {
  //           // 恢复各个 ChatWindow 数据
  //           if(vm.$refs.ChatWindow && savedData.chatWindowLeftData) {
  //             Object.assign(vm.$refs.ChatWindow.$data, savedData.chatWindowLeftData);
  //           }
  //           if(vm.$refs.ChatWindowUp && savedData.chatWindowUpData) {
  //             Object.assign(vm.$refs.ChatWindowUp.$data, savedData.chatWindowUpData);
  //           }
  //           if(vm.$refs.ChatWindowDown && savedData.chatWindowDownData) {
  //             Object.assign(vm.$refs.ChatWindowDown.$data, savedData.chatWindowDownData);
  //           }
  //           // 恢复 FileList 数据
  //           if(vm.$refs.FileList && savedData.fileListData) {
  //             Object.assign(vm.$refs.FileList.$data, savedData.fileListData);
  //           }
  //         });
  //       }
  //     }
  //   });
  // },
  methods: {
    // 🔥 更新本子信息
    updateNotebookInfo() {
      try {
        if (!this.$refs.CardGrid || !this.$refs.CardGrid.cardList) {
          this._notebookInfo = null;
          return;
        }
        
        const cardList = this.$refs.CardGrid.cardList;
        if (!Array.isArray(cardList)) {
          this._notebookInfo = null;
          return;
        }
        
        // 🔥 使用CardGrid中的本子描述（中文），如果没有则使用bookName
        let bookName = '未命名本子';
        try {
          // 优先使用CardGrid的notebookDescription（中文描述）
          if (this.$refs.CardGrid && this.$refs.CardGrid.notebookDescription) {
            bookName = this.$refs.CardGrid.notebookDescription;
          } else {
            // 如果没有，从username中提取本子名（bookName）
            const username = localStorage.getItem('userId') || '';
            if (username && username.includes('_')) {
              const parts = username.split('_');
              if (parts.length > 1) {
                bookName = parts.slice(1).join('_'); // 支持bookName中包含下划线的情况
              }
            }
          }
        } catch (e) {
          console.warn('[mainPage] 获取本子名失败:', e);
        }
        
        // 🔥 使用CardGrid的hasFourColorOrDmt方法，如果没有则使用默认逻辑
        const hasFourColorOrDmt = (card) => {
          if (!card) return false;
          const hasFourColor = card.four_color_type && card.four_color_type.trim() !== '';
          const hasDmt = card.dmt_level && card.dmt_level.trim() !== '';
          return hasFourColor || hasDmt;
        };
        
        // 🔥 如果CardGrid有hasFourColorOrDmt方法，使用它
        let checkMethod = hasFourColorOrDmt;
        if (this.$refs.CardGrid && typeof this.$refs.CardGrid.hasFourColorOrDmt === 'function') {
          checkMethod = this.$refs.CardGrid.hasFourColorOrDmt.bind(this.$refs.CardGrid);
        }
        
        const dmtCount = cardList.filter(card => checkMethod(card)).length;  // b: 有颜色的卡数（浅+深）
        const totalCount = cardList.length;  // c: 卡片总数
        
        // 🔥 计算深色卡数（a）：永久卡片且有四色属性的卡片
        const deepCount = cardList.filter(card => {
          return card.type && card.type.includes('永久') && card.four_color_type && card.four_color_type.trim() !== '';
        }).length;
        
        this._notebookInfo = {
          name: bookName,
          deepCount: deepCount,  // a: 深色卡数
          dmtCount: dmtCount,    // b: 有颜色的卡数（浅+深）
          totalCount: totalCount  // c: 卡片总数
        };
      } catch (e) {
        console.warn('[mainPage] 更新本子信息失败:', e);
        this._notebookInfo = null;
      }
    },

    // 图片文本分页相关方法
    // 分割文本为页面
    splitImgTextIntoPages() {
      if (!this.imgClickedText || this.imgClickedText.length <= this.imgTextPageSize) {
        this.imgTextPages = [this.imgClickedText || ''];
        this.imgTextTotalPages = 1;
        this.imgTextCurrentPage = 1;
        return;
      }
      
      const text = this.imgClickedText;
      const pages = [];
      let currentPos = 0;
      
      while (currentPos < text.length) {
        let endPos = currentPos + this.imgTextPageSize;
        
        // 如果不是最后一页，尝试在句号、问号、感叹号处断开
        if (endPos < text.length) {
          const searchRange = Math.min(100, this.imgTextPageSize / 10); // 在末尾100字符内查找
          const searchStart = Math.max(endPos - searchRange, currentPos);
          
          let breakPoint = -1;
          for (let i = endPos - 1; i >= searchStart; i--) {
            if (text[i] === '。' || text[i] === '？' || text[i] === '！' || text[i] === '\n') {
              breakPoint = i + 1;
              break;
            }
          }
          
          if (breakPoint > currentPos) {
            endPos = breakPoint;
          }
        }
        
        pages.push(text.slice(currentPos, endPos));
        currentPos = endPos;
      }
      
      this.imgTextPages = pages;
      this.imgTextTotalPages = pages.length;
      this.imgTextCurrentPage = 1;
    },
    
    // 上一页
    prevImgTextPage() {
      if (this.imgTextCurrentPage > 1) {
        this.imgTextCurrentPage--;
      }
    },
    
    // 下一页
    nextImgTextPage() {
      if (this.imgTextCurrentPage < this.imgTextTotalPages) {
        this.imgTextCurrentPage++;
      }
    },

    // 新旧服务器数据共通（本子内导出导入相关数据）
    // 右键导出数据
    handleRightClick() {
      const userId = localStorage.getItem('userId');
      
      if (!userId) {
        this.$message.error('未找到用户ID');
        return;
      }

      this.$message.info('正在导出数据...');

      const formData = new FormData();
      formData.append('username', userId);
      
      exportUserData(formData).then(response => {
        // 🔥 处理blob响应：axios返回的response.data才是blob
        const blob = response.data || response;
        
        // 检查是否是错误响应（如果服务器返回JSON错误）
        if (blob.type && blob.type.includes('application/json')) {
          blob.text().then(text => {
            try {
              const errorData = JSON.parse(text);
              this.$message.error(`导出失败: ${errorData.msg || '未知错误'}`);
            } catch (e) {
              this.$message.error('导出失败: 服务器返回了错误响应');
            }
          });
          return;
        }

        // 创建下载链接
        // const url = window.URL.createObjectURL(response);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `user_data_${userId}_${new Date().getTime()}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        
        this.$message.success('数据导出成功');
      }).catch(error => {
        console.error('导出错误:', error);
        // 🔥 更详细的错误处理
        if (error.response) {
          // 服务器返回了错误响应
          if (error.response.data instanceof Blob) {
            error.response.data.text().then(text => {
              try {
                const errorData = JSON.parse(text);
                this.$message.error(`导出失败: ${errorData.msg || '服务器错误'}`);
              } catch (e) {
                this.$message.error(`导出失败: HTTP ${error.response.status}`);
              }
            });
          } else {
            this.$message.error(`导出失败: ${error.response.data?.msg || `HTTP ${error.response.status}`}`);
          }
        } else if (error.request) {
          // 请求已发送但没有收到响应
          this.$message.error('导出失败: 服务器无响应，可能是数据量太大导致超时');
        } else {
          // 请求配置错误
          this.$message.error(`导出失败: ${error.message || '未知错误'}`);
        }
      });
    },

    // 双击导入数据
    handleDoubleClick() {
      this.$refs.fileInput.click();
    },

    // 处理文件导入
    handleFileImport(event) {
      const file = event.target.files[0];
      if (!file) return;

      if (!file.name.endsWith('.txt')) {
        this.$message.error('请选择txt格式的文件');
        return;
      }

      this.$message.info('正在导入数据...');

      const formData = new FormData();
      formData.append('file', file);

      importUserData(formData).then(response => {
        if (response.data.error_num === 0) {
          this.$message.success(`数据导入成功: ${response.data.msg}`);
        } else {
          console.log("导入失败", response.data.error_detail)
          this.$message.error(`导入失败: ${response.data.msg}`);
        }
      }).catch(error => {
        console.error('导入错误:', error);
        this.$message.error('导入失败');
      });

      // 清空文件输入框
      event.target.value = '';
    },


    // 半自动化添加方法
    handleEndRecordWithTarget() {
      this.saveOperationRecords();
      this.$message.success('涌现示范流程记录完成！');
      this.recordMode = false;
    },

    handleStartRecordWithTarget(fileName) {
      // 设置目标文件并开始记录
      this.recordTargetFile = fileName;
      this.recordMode = true;
      this.operationRecords = [];
      this.$message.success(`开始涌现示范(记录操作流程)，目标文件：${fileName}`);
    },

    checkAutomationRecords() {
      const formData = new FormData();
      formData.append('notebook_id', localStorage.getItem('userId'));
      
      checkHasRecords(formData).then(response => {
        if (response.has_records) {
          localStorage.setItem('hasRecords', 'true');
          // 通知FileList刷新
          if (this.$refs.FileList) {
            this.$refs.FileList.getAllUserFiles();
          }
        } else {
          localStorage.setItem('hasRecords', 'false');
        }
      });
    },

    reloadAutoCards() {
      this.$refs.CardGrid.reloadAutoCards();
    },

    pinCard(cardData) {
      this.recordOperation('create_card', cardData);

      // 🔥 获取当前三窗口模型配置并保存到卡片
      if (cardData.created_card_id) {
        const threeWindowModels = {
          main: this.curModelInfo ? this.curModelInfo.id : null,
          up: this.curModelInfoUp ? this.curModelInfoUp.id : null,
          down: this.curModelInfoDown ? this.curModelInfoDown.id : null
        };
        
        // 调用后端API更新卡片的三窗口模型配置
        this.updateCardThreeWindowModels(cardData.created_card_id, threeWindowModels);
      }
    },

    // 🔥 更新卡片的三窗口模型配置
    async updateCardThreeWindowModels(cardId, threeWindowModels) {
      try {
        const formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', cardId);
        formData.append('three_window_models', JSON.stringify(threeWindowModels));
        
        const response = await fetch(`${API_BASE_URL}/api/update_card_three_window_models`, {
          method: 'POST',
          body: formData
        });
        
        const data = await response.json();
        if (data.error_num === 0) {
          console.log('[mainPage] 卡片三窗口模型配置已保存:', threeWindowModels);
        } else {
          console.warn('[mainPage] 保存卡片三窗口模型配置失败:', data.msg);
        }
      } catch (e) {
        console.error('[mainPage] 更新卡片三窗口模型配置失败:', e);
      }
    },

    handleCardRecordOperation(payload) {
      this.recordOperation(payload.type, payload.data);
    },

    saveOperationRecords() {
      const formData = new FormData();
      formData.append('notebook_id', localStorage.getItem('userId'));
      formData.append('records', JSON.stringify(this.operationRecords));
      formData.append('target_file', this.recordTargetFile || ''); // 使用记录的目标文件
      
      saveAutomationRecords(formData).then(response => {
        console.log('操作记录已保存');
        // 设置标记，表示已有记录
        localStorage.setItem('hasRecords', 'true');
        // 通知FileList刷新
        this.$refs.FileList.getAllUserFiles();
      });
    },

    // 🔥 加载用户的系统选择（快慢思考，仅用于显示当前状态）
    async loadSystemChoice() {
      try {
        const { getSystemChoice } = await import('@/api/system')
        const response = await getSystemChoice({
          username: localStorage.getItem('originRealName')
        })
        if (response.error_num === 0) {
          this.systemChoice = response.choose
          localStorage.setItem('systemChoice', response.choose)
        }
      } catch (error) {
        console.error('加载系统选择失败:', error)
        // 如果加载失败，使用localStorage中的值
        const savedChoice = localStorage.getItem('systemChoice')
        if (savedChoice !== null) {
          this.systemChoice = parseInt(savedChoice)
        }
      }
    },

    toggleRecordMode() {
        // this.recordMode = !this.recordMode;
        // if (this.recordMode) {
        //     this.operationRecords = [];
        //     this.$message.success('开始记录操作流程');
        // } else {
        //     this.saveOperationRecords();
        //     this.$message.success('操作流程记录完成');
        // }
        if (this.recordMode) {
            // 正在记录，停止记录
            this.saveOperationRecords();
            this.$message.success('操作流程记录完成');
            this.recordMode = !this.recordMode;
        } else {
            // 未在记录，提示需要从文件开始
            this.$message.info('请从某个文件开始记录涌现示范');
        }
    },

    recordOperation(actionType, actionData) {
        if (!this.recordMode) return;
        
        const record = {
            step: this.operationRecords.length + 1,
            actionType: actionType,
            actionData: actionData,
            timestamp: new Date().toISOString()
        };
        this.operationRecords.push(record);

        console.log("看看到底什么情况", this.operationRecords)
    },


    // 图片文档显示可能的红蓝卡标指示器底色
    getRatingStyle(score) {
      // 将字符串转换为数字
      const numScore = parseFloat(score);
      
      // 小于1分区间
      if (numScore < 0.5) {
        return { backgroundColor: '#FF4D4F' };  // 红色 (0-0.5分)
      } else if (numScore < 1) {
        return { backgroundColor: '#1890FF' };  // 蓝色 (0.5-1分)
      } 
      // 1-4分区间，紫色渐变
      else if (numScore < 1.5) {
        return { backgroundColor: '#F3E5F5' };  // 紫色1级 (1-1.5分)
      } else if (numScore < 2) {
        return { backgroundColor: '#E1BEE7' };  // 紫色2级 (1.5-2分)
      } else if (numScore < 2.5) {
        return { backgroundColor: '#CE93D8' };  // 紫色3级 (2-2.5分)
      } else if (numScore < 3) {
        return { backgroundColor: '#BA68C8' };  // 紫色4级 (2.5-3分)
      } else if (numScore < 3.5) {
        return { backgroundColor: '#AB47BC' };  // 紫色5级 (3-3.5分)
      } else if (numScore < 4) {
        return { backgroundColor: '#9C27B0' };  // 紫色6级 (3.5-4分)
      } 
      // 4分以上区间
      else if (numScore < 4.5) {
        return { backgroundColor: '#8E24AA' };  // 深紫色1级 (4-4.5分)
      } else if (numScore < 5) {
        return { backgroundColor: '#7B1FA2' };  // 深紫色2级 (4.5-5分)
      } else {
        return { backgroundColor: '#6A1B9A' };  // 最深紫色 (5分及以上)
      }
    },

    // 图片文档的向量库摘要文本可修改, 更新时对应FileCard灰色禁用样式显示切换
    updateFileCardBanStyle(fileName, isProcessing) {
      // 调用FileList组件的方法
      this.$refs.FileList.updateFileCardBanStyle(fileName, isProcessing);
    },

    // 卡片Add图文化
    // 处理粘贴事件（在输入框中）
    handlePaste(event) {
      this.processPasteEvent(event);
    },

    // 处理全局粘贴事件（当对话框打开时）
    handleGlobalPaste(event) {
      // 仅在对话框打开且焦点不在其他输入框时处理
      if (this.showAddDirectDialog && !event.target.closest('input, textarea')) {
        this.processPasteEvent(event);
      }
    },

    // 处理粘贴事件的核心逻辑
    processPasteEvent(event) {
      const items = event.clipboardData?.items;
      if (!items) return;
      
      for (let item of items) {
        if (item.type.indexOf('image') !== -1) {
          event.preventDefault();
          const file = item.getAsFile();
          if (file) {
            this.handlePastedImage(file);
          }
          break;
        }
      }
    },

    // 处理粘贴的图片
    handlePastedImage(file) {
      const uploadFile = {
        name: `pasted-image-${Date.now()}.${file.type.split('/')[1]}`,
        raw: file,
        size: file.size,
        type: file.type,
        uid: Date.now(),
        status: 'ready'
      };
      
      this.selectedFile = file;
      this.cardImgFileList = [uploadFile];
      this.createImagePreview(file);
      
      this.$message.success('图片粘贴成功');
    },

    // 创建图片预览
    createImagePreview(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        this.imagePreview = e.target.result;
      };
      reader.readAsDataURL(file);
    },

    // 移除图片
    removeImage() {
      this.selectedFile = null;
      this.cardImgFileList = [];
      this.imagePreview = null;
    },

    // 处理文件移除（从上传组件）
    handleRemove() {
      this.removeImage();
    },

    handleCardImgFileChange(file) {
      // 处理文件变更
      this.selectedFile = file.raw;
      this.cardImgFileList = [file];
      this.createImagePreview(file.raw);  // 新增这一行
    },

    // 双击点读功能
    startFromIndex(index, answer) {
      this.selectedIndex = index;
      this.doubleClick = true;
      this.speakText();
    },
    speakText() {
      this.stopSpeech()
      // 截取从用户双击位置开始的内容
      const content = this.imgClickedText.slice(this.selectedIndex);
      const utterance = new SpeechSynthesisUtterance(content);
      this.speech = window.speechSynthesis.speak(utterance);
      this.isSpeaking = true;
    },
    stopSpeech() {
      if (this.isSpeaking) {
        window.speechSynthesis.cancel();
        this.isSpeaking = false;
        this.speech = null;
      }
    },
    doubleClickOver() {
      this.doubleClick = false
    },

    chosenOver(openCardId, chosenContent) {
      this.openCardId = openCardId
      this.chosenContent = chosenContent
    },

    handleKeyDown(event) {
      // 如果按下Enter键但没有按Shift键
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault(); // 阻止默认行为（不插入换行）
        this.sendMsg(); // 发送消息
      }
      // 🔥 Tab键触发小模型辅助问题补全
      else if (event.key === 'Tab') {
        event.preventDefault(); // 阻止默认行为（切换焦点）
        this.handleTabKeyEnhance();
      }
      // 如果按下Shift+Enter，不做任何处理，默认行为会插入换行
    },

    // 🔥 勾选推荐的文档列表
    selectSuggestedDocuments(suggestedDocuments) {
      if (!suggestedDocuments || suggestedDocuments.length === 0) {
        return;
      }
      
      if (!this.$refs.FileList || !this.$refs.FileList.fileList) {
        console.warn('[selectSuggestedDocuments] FileList组件或fileList不可用');
        return;
      }
      
      this.$nextTick(() => {
        const fileList = this.$refs.FileList.fileList || [];
        let checkedCount = 0;
        
        suggestedDocuments.forEach(docName => {
          // 查找匹配的文件（可能文档名包含或不包含扩展名）
          const fileIndex = fileList.findIndex(f => {
            if (!f.file) return false;
            const fileName = f.file.name;
            // 完全匹配或去掉扩展名后匹配
            return fileName === docName || 
                   fileName.replace(/\.[^.]+$/, '') === docName.replace(/\.[^.]+$/, '');
          });
          
          if (fileIndex >= 0) {
            const fileItem = fileList[fileIndex];
            // 🔥 过滤掉 split=0 的文件
            if (fileItem.split === 0) {
              return;
            }
            if (!fileItem.checked) {
              fileItem.checked = true;
              this.$refs.FileList.handleFileCheckedUpdate(true, fileIndex);
              checkedCount++;
            }
          }
        });
        
        if (checkedCount > 0) {
          console.log(`[selectSuggestedDocuments] 已勾选 ${checkedCount} 个推荐文档`);
        }
      });
    },

    // 🔥 Tab键触发小模型辅助问题补全
    async handleTabKeyEnhance() {
      // 如果输入框为空，不处理
      if (!this.inputMsg || this.inputMsg.trim() === '') {
        return;
      }
      
      // 防止重复触发
      if (this.isEnhancingQuestion) {
        return;
      }
      
      try {
        this.isEnhancingQuestion = true;
        this.$message.info('正在使用小模型补全问题...');
        
        // 获取勾选的文档信息（从FileList组件）
        const selectedDocuments = [];
        if (this.$refs.FileList && this.$refs.FileList.fileList) {
          this.$refs.FileList.fileList.forEach(file => {
            if (file.checked) {
              selectedDocuments.push({
                name: file.file.name,
                main_four_color: file.mainFourColor || '',
                secondary_four_color: file.secondaryFourColor || '',
                dmt_level: file.dmtLevel || ''
              });
            }
          });
        }
        
        // 🔥 获取勾选的卡片信息（从CardGrid组件获取）
        const selectedCards = [];
        if (this.$refs.CardGrid && this.$refs.CardGrid.choosedCardIdList && this.$refs.CardGrid.cardList) {
          const choosedCardIds = this.$refs.CardGrid.choosedCardIdList;
          const cardList = this.$refs.CardGrid.cardList;
          
          choosedCardIds.forEach(cardId => {
            const card = cardList.find(c => c.cid === cardId);
            if (card) {
              selectedCards.push({
                title: card.contentTitle || card.title || '',
                keyWords: card.keyWords || '',
                four_color_type: card.four_color_type || '',
                dmt_level: card.dmt_level || ''
              });
            }
          });
        }
        
        // 调用API
        // 🔥 默认使用中转服务器调用8卡服务端小模型，可通过配置切换
        const useRelay = false; // TODO: 可以从配置中读取，允许用户切换
        const response = await enhance_question_with_small_model({
          userQuestion: this.inputMsg,
          username: localStorage.getItem('userId'),
          sceneName: this.sceneName,
          subSceneName: this.subSceneName,
          selectedDocuments: selectedDocuments,
          selectedCards: selectedCards,
          useRelay: useRelay  // 🔥 传递useRelay参数
        });
        
        if (response && response.error_num === 0 && response.enhancedQuestion) {
          const enhancedQuestion = response.enhancedQuestion;
          
          const suggestedSubScene = response.suggestedSubScene; // 🔥 建议的子场景（S1, S2等）
          const suggestedDocuments = response.suggestedDocuments || []; // 🔥 推荐的文档列表
          const coreKeyword = response.coreKeyword || null; // 🔥 核心关键词（xxx）
          
          // 🔥 构建对话框内容
          let dialogMessage = `补全后的问题：\n\n${enhancedQuestion}\n\n`;
          let showSubSceneSwitch = false;
          let targetSubSceneName = null;
          let hasDocumentSuggestion = suggestedDocuments && suggestedDocuments.length > 0;
          
          // 如果提供了子场景建议，检查是否需要切换
          if (suggestedSubScene && this.subSceneList && this.subSceneList.length > 0) {
            // 尝试从子场景列表中查找匹配的子场景（可能格式为"S1: 子场景名"或直接是子场景名）
            const subSceneMatch = this.subSceneList.find(scene => {
              // 检查子场景名是否以建议的标识开头（如"S1"）
              return scene.includes(suggestedSubScene) || scene.startsWith(suggestedSubScene + ':') || scene.startsWith(suggestedSubScene + '：');
            });
            
            // // 🔥 如果找到了匹配的子场景，无论是否与当前相同，都显示两个按钮
            // // 因为即使建议的是当前子场景，用户也可能想切换到其他子场景
            if (subSceneMatch) {
              showSubSceneSwitch = true;
              targetSubSceneName = subSceneMatch;
              if (subSceneMatch !== this.subSceneName) {
                dialogMessage += `\n💡 建议切换子场景：${targetSubSceneName}`;
              } else {
                dialogMessage += `\n💡 建议保持当前子场景：${targetSubSceneName}`;
              }
            }
          }
          
          // 如果提供了文档推荐，添加到对话框内容
          if (hasDocumentSuggestion) {
            dialogMessage += `\n\n📄 推荐的文档（${suggestedDocuments.length}个）：\n${suggestedDocuments.map((doc, idx) => `${idx + 1}. ${doc}`).join('\n')}`;
          }
          
          // 🔥 判断显示几个按钮：有文档推荐且有子场景建议时显示四个按钮，否则显示相应数量的按钮
          if (hasDocumentSuggestion && showSubSceneSwitch && targetSubSceneName) {
            // 四个按钮：只接受增强后问题、接受问题和文档勾选、接受问题和子场景推荐、全部接受
            // 使用自定义HTML消息框
            // const h = this.$createElement;
            const messageVNode = h('div', {
              style: { whiteSpace: 'pre-line', textAlign: 'left' }
            }, dialogMessage);
            
            ElMessageBox({
              title: '问题补全建议',
              message: messageVNode,
              showCancelButton: true,
              showConfirmButton: true,
              confirmButtonText: '全部接受',
              cancelButtonText: '只接受增强后问题',
              distinguishCancelAndClose: true,
              closeOnClickModal: false,
              type: 'info',
              customClass: 'enhanced-question-dialog',
              // 添加额外的按钮
              beforeClose: (action, instance, done) => {
                if (action === 'confirm') {
                  // 全部接受：更新问题 + 切换子场景 + 勾选文档
                  this.inputMsg = enhancedQuestion;
                  this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
                  const subSceneIndex = this.subSceneList.indexOf(targetSubSceneName);
                  if (subSceneIndex >= 0) {
                    this.changeSubScene(targetSubSceneName, subSceneIndex);
                  }
                  this.selectSuggestedDocuments(suggestedDocuments);
                  this.$message.success('已全部接受：问题已更新，已切换子场景，已勾选推荐文档');
                  done();
                } else if (action === 'cancel') {
                  // 只接受增强后问题
                  this.inputMsg = enhancedQuestion;
                  this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
                  this.$message.success('问题已更新');
                  done();
                } else {
                  // 关闭按钮
                  this.$message.info('已取消');
                  done();
                }
              }
            }).catch(() => {
              // 关闭
              this.$message.info('已取消');
            });
            
            // 手动添加另外两个按钮
            this.$nextTick(() => {
              const msgboxEl = document.querySelector('.enhanced-question-dialog');
              if (msgboxEl) {
                const buttonContainer = msgboxEl.querySelector('.el-message-box__btns');
                if (buttonContainer && buttonContainer.children.length === 2) {
                  // 创建"接受问题和文档勾选"按钮
                  const btn1 = document.createElement('button');
                  btn1.className = 'el-button el-button--default';
                  btn1.textContent = '接受问题和文档勾选';
                  btn1.onclick = () => {
                    this.inputMsg = enhancedQuestion;
                    this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
                    this.selectSuggestedDocuments(suggestedDocuments);
                    this.$message.success('问题已更新，已勾选推荐文档');
                    // 关闭消息框
                    const closeBtn = msgboxEl.querySelector('.el-message-box__closebtn');
                    if (closeBtn) closeBtn.click();
                  };
                  
                  // 创建"接受问题和子场景推荐"按钮
                  const btn2 = document.createElement('button');
                  btn2.className = 'el-button el-button--default';
                  btn2.textContent = '接受问题和子场景推荐';
                  btn2.onclick = () => {
                    this.inputMsg = enhancedQuestion;
                    this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
                    const subSceneIndex = this.subSceneList.indexOf(targetSubSceneName);
                    if (subSceneIndex >= 0) {
                      this.changeSubScene(targetSubSceneName, subSceneIndex);
                      this.$message.success(`问题已更新，已切换到子场景：${targetSubSceneName}`);
                    } else {
                      this.$message.success('问题已更新');
                    }
                    // 关闭消息框
                    const closeBtn = msgboxEl.querySelector('.el-message-box__closebtn');
                    if (closeBtn) closeBtn.click();
                  };
                  
                  // 在确认按钮前插入这两个按钮
                  buttonContainer.insertBefore(btn1, buttonContainer.children[1]);
                  buttonContainer.insertBefore(btn2, buttonContainer.children[1]);
                }
              }
            });
          } else if (hasDocumentSuggestion) {
            // 只有文档推荐，没有子场景建议：两个按钮（只接受问题、接受问题和文档勾选）
            ElMessageBox({
              title: '问题补全建议',
              message: dialogMessage + '\n\n请选择操作：',
              showCancelButton: true,
              showConfirmButton: true,
              confirmButtonText: '接受问题和文档勾选',
              cancelButtonText: '只接受增强后问题',
              distinguishCancelAndClose: true,
              closeOnClickModal: false,
              type: 'info',
              customClass: 'enhanced-question-dialog',
              beforeClose: (action, instance, done) => {
                if (action === 'confirm') {
                  // 接受问题和文档勾选
                  this.inputMsg = enhancedQuestion;
                  this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
                  this.selectSuggestedDocuments(suggestedDocuments);
                  this.$message.success('问题已更新，已勾选推荐文档');
                  done();
                } else if (action === 'cancel') {
                  // 只接受增强后问题
                  this.inputMsg = enhancedQuestion;
                  this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
                  this.$message.success('问题已更新');
                  done();
                } else {
                  // 关闭按钮
                  this.$message.info('已取消');
                  done();
                }
              }
            }).catch(() => {
              // 关闭
              this.$message.info('已取消');
            });
          } else if (showSubSceneSwitch && targetSubSceneName) {
            // 只有子场景建议，没有文档推荐：两个按钮（只接受问题、接受问题和子场景推荐）
            ElMessageBox.confirm(
              dialogMessage + '\n\n请选择操作：',
              '问题补全建议',
              {
                confirmButtonText: '接受问题和子场景推荐',
                cancelButtonText: '只接受增强后问题',
                distinguishCancelAndClose: true,
                closeOnClickModal: false,
                type: 'info',
                customClass: 'enhanced-question-dialog'
              }
            ).then(() => {
              // 接受问题和子场景推荐
              this.inputMsg = enhancedQuestion;
              this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
              const subSceneIndex = this.subSceneList.indexOf(targetSubSceneName);
              if (subSceneIndex >= 0) {
                this.changeSubScene(targetSubSceneName, subSceneIndex);
                this.$message.success(`问题已更新，已切换到子场景：${targetSubSceneName}`);
              } else {
                this.$message.success('问题已更新');
              }
            }).catch((action) => {
              if (action === 'cancel') {
                // 只接受增强后问题
                this.inputMsg = enhancedQuestion;
                this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
                this.$message.success('问题已更新');
              } else {
                // 关闭按钮
                this.$message.info('已取消');
              }
            });
          } else {
            // 既没有文档推荐也没有子场景建议：原来的简单对话框
            ElMessageBox.confirm(
              dialogMessage + '\n\n是否接受并替换当前问题？',
              '问题补全建议',
              {
                confirmButtonText: '接受',
                cancelButtonText: '拒绝',
                type: 'info',
                customClass: 'enhanced-question-dialog'
              }
            ).then(() => {
              // 用户选择接受
              this.inputMsg = enhancedQuestion;
              this.coreKeyword = coreKeyword; // 🔥 保存核心关键词
              this.$message.success('问题已更新');
            }).catch(() => {
              // 用户选择拒绝，不做任何操作
              this.$message.info('已取消');
            });
          }
        } else {
          const errorMsg = response?.msg || '未知错误';
          this.$message.warning('问题补全失败: ' + errorMsg);
        }
      } catch (error) {
        console.error('[handleTabKeyEnhance] 错误:', error);
        let errorMsg = '未知错误';
        if (error.response && error.response.data) {
          // 服务器返回了错误响应
          errorMsg = error.response.data.msg || error.response.data.message || '服务器错误';
        } else if (error.message) {
          errorMsg = error.message;
        }
        this.$message.error('问题补全失败: ' + errorMsg);
      } finally {
        this.isEnhancingQuestion = false;
      }
    },
    
    // // 🔥 生成/更新文档全面交叉梳理建议卡片（双击文档导入区时调用）
    // async handleGenerateCrossDocumentSuggestion() {
    //   try {
    //     if (!this.hasCardOperationPermission()) {
    //       this.$message.error('您没有权限添加卡片');
    //       return;
    //     }

    //     // 🔥 先检查是否已存在文档交叉梳理卡片
    //     let existingCardId = null;
    //     if (this.$refs.CardGrid) {
    //       existingCardId = this.$refs.CardGrid.getCrossDocumentSuggestionCardId();
    //     }

    //     // 🔥 参考Summary钉卡：先滚动到顶部，再显示等待卡片（在API调用之前）
    //     if (this.$refs.CardGrid) {
    //       this.$refs.CardGrid.scrollToTop();
    //     }
    //     this.cardMaking = true;
        
    //     const actionText = existingCardId ? '更新' : '生成';
    //     this.$message.info(`正在${actionText}文档全面交叉梳理建议卡片...`);
        
    //     const response = await generate_cross_document_suggestion_card({
    //       username: localStorage.getItem('userId'),
    //       sceneName: this.sceneName,
    //       subSceneName: this.subSceneName
    //     });
        
    //     if (response && response.error_num === 0 && response.content) {
    //       const suggestionContent = response.content;
          
    //       // // 🔥 将建议内容生成Card卡片，而不是显示对话框
    //       // // 先滚动到顶部，再显示等待卡片
    //       // if (this.$refs.CardGrid) {
    //       //   this.$refs.CardGrid.scrollToTop();
    //       // }
    //       // this.cardMaking = true;
          
    //       // 构造卡片内容
    //       const cardContent = `【文档全面交叉梳理建议卡片】\n\n${suggestionContent}`;
          
    //       // // 创建FormData（add_card_directly只需要这些参数）
    //       // let formData = new FormData();
    //       // formData.append('username', localStorage.getItem('userId'));
    //       // formData.append('originRealName', localStorage.getItem('originRealName') || '');
    //       // formData.append('content', cardContent);
    //       // formData.append('sceneName', this.sceneName);
    //       // formData.append('subSceneName', this.subSceneName);
    //       // formData.append('keyTopics', JSON.stringify(this.keyTopics || []));
          
    //       // // 使用addCardDirect创建卡片
    //       // addCardDirect(formData).then(data => {
    //       //   if(data.data['error_num'] === 0) {
    //       //     let cid = data.data['cardId'];
    //       //     // 🔥 参考Summary钉卡：设置新生成的卡片ID，关闭等待卡，触发浅评和深评
    //       //     if (this.$refs.CardGrid) {
    //       //       this.$refs.CardGrid.setLastCreatedCardId(cid);
    //       //     }
    //       //     // this.handleCardUpdate(cid); // 🔥 关闭等待卡并触发卡片更新
    //       //     this.cardMaking = false;
    //       //     this.cardUpdate = true;
    //       //     // 🔥 参考Summary钉卡：调用浅评和深评
    //       //     this.$refs.ChatWindow.getModelEval(cardContent, cid);
    //       //     this.$refs.ChatWindow.getOurModelEval(cardContent, cid, -1);
    //       //     this.$message.success('文档全面交叉梳理建议卡片已创建！');
    //       //   } else {
    //       //     this.$message.error('创建卡片失败: ' + (data.data['msg'] || '未知错误'));
    //       //     this.cardMaking = false;
    //       //   }
    //       // }).catch(error => {
    //       //   console.error('[handleGenerateCrossDocumentSuggestion] 创建卡片失败:', error);
    //       //   this.$message.error('创建卡片失败: ' + (error.message || '未知错误'));
    //       //   this.cardMaking = false;
    //       // });

    //       // 🔥 如果已存在，则更新；否则创建新卡片
    //       if (existingCardId) {
    //         // 更新现有卡片
    //         let formData = new FormData();
    //         formData.append('cid', existingCardId);
    //         formData.append('content', cardContent);
    //         formData.append('username', localStorage.getItem('userId'));
            
    //         card_updateContentById(formData).then(data => {
    //           if(data.data && data.data['error_num'] === 0) {
    //             this.cardMaking = false;
    //             this.cardUpdate = true;
    //             // 🔥 更新后也触发浅评和深评
    //             this.$refs.ChatWindow.getModelEval(cardContent, existingCardId);
    //             this.$refs.ChatWindow.getOurModelEval(cardContent, existingCardId, -1);
    //             this.$message.success('文档全面交叉梳理建议卡片已更新！');
    //           } else {
    //             this.$message.error('更新卡片失败: ' + (data.data?.['msg'] || '未知错误'));
    //             this.cardMaking = false;
    //           }
    //         }).catch(error => {
    //           console.error('[handleGenerateCrossDocumentSuggestion] 更新卡片失败:', error);
    //           this.$message.error('更新卡片失败: ' + (error.message || '未知错误'));
    //           this.cardMaking = false;
    //         });
    //       } else {
    //         // 创建新卡片
    //         let formData = new FormData();
    //         formData.append('username', localStorage.getItem('userId'));
    //         formData.append('originRealName', localStorage.getItem('originRealName') || '');
    //         formData.append('content', cardContent);
    //         formData.append('sceneName', this.sceneName);
    //         formData.append('subSceneName', this.subSceneName);
    //         formData.append('keyTopics', JSON.stringify(this.keyTopics || []));
            
    //         // 使用addCardDirect创建卡片
    //         addCardDirect(formData).then(data => {
    //           if(data.data['error_num'] === 0) {
    //             let cid = data.data['cardId'];
    //             // 🔥 参考Summary钉卡：设置新生成的卡片ID，关闭等待卡，触发浅评和深评
    //             if (this.$refs.CardGrid) {
    //               this.$refs.CardGrid.setLastCreatedCardId(cid);
    //             }
    //             this.cardMaking = false;
    //             this.cardUpdate = true;
    //             // 🔥 参考Summary钉卡：调用浅评和深评
    //             this.$refs.ChatWindow.getModelEval(cardContent, cid);
    //             this.$refs.ChatWindow.getOurModelEval(cardContent, cid, -1);
    //             this.$message.success('文档全面交叉梳理建议卡片已创建！');
    //           } else {
    //             this.$message.error('创建卡片失败: ' + (data.data['msg'] || '未知错误'));
    //             this.cardMaking = false;
    //           }
    //         }).catch(error => {
    //           console.error('[handleGenerateCrossDocumentSuggestion] 创建卡片失败:', error);
    //           this.$message.error('创建卡片失败: ' + (error.message || '未知错误'));
    //           this.cardMaking = false;
    //         });
    //       }
    //     } else {
    //       const errorMsg = response?.msg || '未知错误';
    //       this.$message.error(`生成建议卡片失败: ${errorMsg}`);
    //       this.cardMaking = false;
    //     }
    //   } catch (error) {
    //     console.error('[handleGenerateCrossDocumentSuggestion] 错误:', error);
    //     let errorMsg = '未知错误';
    //     if (error.response && error.response.data) {
    //       // 服务器返回了错误响应
    //       errorMsg = error.response.data.msg || error.response.data.message || '服务器错误';
    //     } else if (error.message) {
    //       errorMsg = error.message;
    //     }
    //     this.$message.error('生成建议卡片失败: ' + errorMsg);
    //     this.cardMaking = false;
    //   }
    // },

    // 🔥 生成/更新文档全面交叉梳理建议卡片（双击文档导入区时调用）
    async handleGenerateCrossDocumentSuggestion() {
      try {
        if (!this.hasCardOperationPermission()) {
          this.$message.error('您没有权限添加卡片');
          return;
        }

        // 🔥 先检查是否已存在文档交叉梳理卡片
        let existingCardId = null;
        if (this.$refs.CardGrid) {
          existingCardId = this.$refs.CardGrid.getCrossDocumentSuggestionCardId();
        }

        // 🔥 如果已存在，使用更新API；否则创建新卡片
        if (existingCardId) {
          // 🔥 更新现有卡片：显示单个卡片等待状态，不显示全局等待卡
          // 将文档交叉梳理卡片ID添加到choosedCardIdList，以便显示等待状态
          if (this.$refs.CardGrid) {
            if (!this.$refs.CardGrid.choosedCardIdList.includes(existingCardId)) {
              this.$refs.CardGrid.choosedCardIdList.push(existingCardId);
            }
          }
          this.cardSingleMaking = true;
          this.$message.info('正在更新文档全面交叉梳理建议卡片...');
          
          // 🔥 调用更新API，后端会重新生成内容并更新
          update_cross_document_suggestion_card({
            username: localStorage.getItem('userId'),
            sceneName: this.sceneName,
            subSceneName: this.subSceneName,
            cid: existingCardId
          }).then(response => {
            if (response && response.error_num === 0) {
              this.cardSingleMaking = false;
              // 从choosedCardIdList中移除
              if (this.$refs.CardGrid) {
                const index = this.$refs.CardGrid.choosedCardIdList.indexOf(existingCardId);
                if (index > -1) {
                  this.$refs.CardGrid.choosedCardIdList.splice(index, 1);
                }
              }
              this.cardUpdate = true;
              // 🔥 更新后也触发浅评和深评
              const cardContent = `【文档全面交叉梳理建议卡片】\n\n${response.content || ''}`;
              this.$refs.ChatWindow.getModelEval(cardContent, existingCardId);
              this.$refs.ChatWindow.getOurModelEval(cardContent, existingCardId, -1);
              this.$message.success('文档全面交叉梳理建议卡片已更新！');
              this.maybeStartGroupTwinAfterCrossDoc();
            } else {
              const errorMsg = response?.msg || '未知错误';
              this.$message.error('更新卡片失败: ' + errorMsg);
              this.cardSingleMaking = false;
              // 从choosedCardIdList中移除
              if (this.$refs.CardGrid) {
                const index = this.$refs.CardGrid.choosedCardIdList.indexOf(existingCardId);
                if (index > -1) {
                  this.$refs.CardGrid.choosedCardIdList.splice(index, 1);
                }
              }
            }
          }).catch(error => {
            console.error('[handleGenerateCrossDocumentSuggestion] 更新卡片失败:', error);
            let errorMsg = '未知错误';
            if (error.response && error.response.data) {
              errorMsg = error.response.data.msg || error.response.data.message || '服务器错误';
            } else if (error.message) {
              errorMsg = error.message;
            }
            this.$message.error('更新卡片失败: ' + errorMsg);
            this.cardSingleMaking = false;
            // 从choosedCardIdList中移除
            if (this.$refs.CardGrid) {
              const index = this.$refs.CardGrid.choosedCardIdList.indexOf(existingCardId);
              if (index > -1) {
                this.$refs.CardGrid.choosedCardIdList.splice(index, 1);
              }
            }
          });
        } else {
          // 🔥 创建新卡片：显示全局等待卡
          // 🔥 参考Summary钉卡：先滚动到顶部，再显示等待卡片（在API调用之前）
          if (this.$refs.CardGrid) {
            this.$refs.CardGrid.scrollToTop();
          }
          this.cardMaking = true;
          
          this.$message.info('正在生成文档全面交叉梳理建议卡片...');
          
          const response = await generate_cross_document_suggestion_card({
            username: localStorage.getItem('userId'),
            sceneName: this.sceneName,
            subSceneName: this.subSceneName
          });
          
          if (response && response.error_num === 0 && response.content) {
            const suggestionContent = response.content;
            
            // 构造卡片内容
            const cardContent = `【文档全面交叉梳理建议卡片】\n\n${suggestionContent}`;
            
            // 创建新卡片
            let formData = new FormData();
            formData.append('username', localStorage.getItem('userId'));
            formData.append('originRealName', localStorage.getItem('originRealName') || '');
            formData.append('content', cardContent);
            formData.append('sceneName', this.sceneName);
            formData.append('subSceneName', this.subSceneName);
            formData.append('keyTopics', JSON.stringify(this.keyTopics || []));
            
            // 使用addCardDirect创建卡片
            addCardDirect(formData).then(data => {
              if(data.data['error_num'] === 0) {
                let cid = data.data['cardId'];
                // 🔥 参考Summary钉卡：设置新生成的卡片ID，关闭等待卡，触发浅评和深评
                if (this.$refs.CardGrid) {
                  this.$refs.CardGrid.setLastCreatedCardId(cid);
                }
                this.cardMaking = false;
                this.cardUpdate = true;
                // 🔥 参考Summary钉卡：调用浅评和深评
                this.$refs.ChatWindow.getModelEval(cardContent, cid);
                this.$refs.ChatWindow.getOurModelEval(cardContent, cid, -1);
                this.refreshCardWhenKeywordsReady(cid);
                this.$message.success('文档全面交叉梳理建议卡片已创建！');
                this.maybeStartGroupTwinAfterCrossDoc();
              } else {
                this.$message.error('创建卡片失败: ' + (data.data['msg'] || '未知错误'));
                this.cardMaking = false;
              }
            }).catch(error => {
              console.error('[handleGenerateCrossDocumentSuggestion] 创建卡片失败:', error);
              this.$message.error('创建卡片失败: ' + (error.message || '未知错误'));
              this.cardMaking = false;
            });
          } else {
            const errorMsg = response?.msg || '未知错误';
            this.$message.error(`生成建议卡片失败: ${errorMsg}`);
            this.cardMaking = false;
          }
        }
      } catch (error) {
        console.error('[handleGenerateCrossDocumentSuggestion] 错误:', error);
        let errorMsg = '未知错误';
        if (error.response && error.response.data) {
          // 服务器返回了错误响应
          errorMsg = error.response.data.msg || error.response.data.message || '服务器错误';
        } else if (error.message) {
          errorMsg = error.message;
        }
        this.$message.error('生成建议卡片失败: ' + errorMsg);
        this.cardMaking = false;
        this.cardSingleMaking = false;
      }
    },

    /** NK2026：文档交叉梳理卡就绪后，后台按组生成 Gxx.md 孪生（非阻塞） */
    maybeStartGroupTwinAfterCrossDoc() {
      const sn = this.sceneName || '';
      if (!sn.includes('NK2026梯子图') || sn.indexOf('群组公能') === -1) return;
      if (this.nk2026GroupTwinProgress && this.nk2026GroupTwinProgress.active) return;
      this.startNk2026GroupTwinJob();
    },
    async startNk2026GroupTwinJob() {
      try {
        const res = await group_twin_gxx_start({
          username: localStorage.getItem('userId'),
          sceneName: this.sceneName,
        });
        if (!res || res.error_num !== 0 || !res.job_id) {
          return;
        }
        this.nk2026GroupTwinProgress = {
          active: true,
          total: 0,
          done: 0,
          message: '排队中…',
        };
        this.pollNk2026GroupTwin(res.job_id);
      } catch (e) {
        console.error('[startNk2026GroupTwinJob]', e);
      }
    },
    pollNk2026GroupTwin(jobId) {
      if (this.nk2026GroupTwinPollTimer) {
        clearInterval(this.nk2026GroupTwinPollTimer);
        this.nk2026GroupTwinPollTimer = null;
      }
      const applyPayload = (res) => {
        const st = res.status || '';
        const terminal = st === 'done' || st === 'done_with_errors' || st === 'error';
        this.nk2026GroupTwinProgress = {
          active: !terminal,
          total: res.total || 0,
          done: res.done || 0,
          message: res.message || '',
        };
        if (terminal && this.nk2026GroupTwinPollTimer) {
          clearInterval(this.nk2026GroupTwinPollTimer);
          this.nk2026GroupTwinPollTimer = null;
        }
        if (terminal && (st === 'done' || st === 'done_with_errors')) {
          this.$message.success(res.message || '小组本体孪生已生成');
        }
      };
      const tick = async () => {
        try {
          const res = await get_group_twin_gxx_progress(jobId);
          if (!res || res.error_num !== 0) {
            if (this.nk2026GroupTwinPollTimer) {
              clearInterval(this.nk2026GroupTwinPollTimer);
              this.nk2026GroupTwinPollTimer = null;
            }
            // this.nk2026GroupTwinProgress = { active: false, total: 0, done: 0, message: '' };
            // 保留已有进度文案（弹窗关闭再打开仍可见），仅结束轮询
            const prev = this.nk2026GroupTwinProgress || {};
            this.nk2026GroupTwinProgress = {
              ...prev,
              active: false,
            };
            return;
          }
          applyPayload(res);
        } catch (e) {
          console.error('[pollNk2026GroupTwin]', e);
        }
      };
      tick();
      this.nk2026GroupTwinPollTimer = setInterval(tick, 2000);
    },

    chooseCardChange(choosedCardIdList, currentCard, isChecked) {
      // 半自动化新增：记录勾选卡片
      this.recordOperation('select_cards', {         
        cardIdList: [...choosedCardIdList],  // 创建新数组
        previousList: [...this.choosedCardIdList]  // 创建previousList的拷贝       
      }); 

      // 🔥 保存初始状态（如果还没有保存）
      if (!this.initialFileState) {
        this.initialFileState = {
          fileNameList: Array.isArray(this.fileNameList) ? [...this.fileNameList] : [],
          subSceneName: this.subSceneName || '',
          threeWindowModels: {
            main: this.curModelInfo ? this.curModelInfo.id : null,
            up: this.curModelInfoUp ? this.curModelInfoUp.id : null,
            down: this.curModelInfoDown ? this.curModelInfoDown.id : null
          }
        };
      }

      this.choosedCardIdList = choosedCardIdList

      if(this.choosedCardIdList.length === 0) {
        this.openCardId = null
        this.chosenContent = ""
        // 🔥 全部取消勾选，恢复到初始状态
        if (this.initialFileState) {
          this.restoreInitialState();
        }
        return;
      }

      // 🔥 自动勾选文档和切换子场景
      if (isChecked && choosedCardIdList.length > 0) {
        // 🔥 如果是勾选，总是应用最后一张卡片的状态（以最后一张为准）
        const lastCardId = choosedCardIdList[choosedCardIdList.length - 1];
        let lastCard = currentCard && currentCard.cid === lastCardId ? currentCard : null;
        
        // 如果 currentCard 不是最后一张，从 CardGrid 获取最后一张卡片的数据
        if (!lastCard && this.$refs.CardGrid && this.$refs.CardGrid.cardList) {
          lastCard = this.$refs.CardGrid.cardList.find(card => card.cid === lastCardId);
        }
        
        if (lastCard) {
          this.applyCardState(lastCard);
        }
      } else if (!isChecked) {
        // 🔥 取消勾选，恢复到上一张卡片的状态
        this.restorePreviousCardState();
      }
    },

    // 🔥 从卡片中提取文件列表（优先 selected_docs，其次 history）
    // 返回 Promise，因为可能需要异步获取完整卡片数据
    async extractFileListFromCard(card) {
      let fileList = [];
      
      // 1. 优先从 selected_docs 获取
      if (card.selected_docs) {
        try {
          const selectedDocs = typeof card.selected_docs === 'string' 
            ? JSON.parse(card.selected_docs) 
            : card.selected_docs;
          if (Array.isArray(selectedDocs) && selectedDocs.length > 0) {
            fileList = [...selectedDocs];
            return fileList;
          }
        } catch (e) {
          console.error('[extractFileListFromCard] 解析 selected_docs 失败:', e);
        }
      }
      
      // 2. 如果 selected_docs 为空，从 history 中提取
      let history = card.history;
      
      // 🔥 如果 history 不存在，异步获取完整卡片数据（包括 history）
      if (!history) {
        try {
          const formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          formData.append('cid', card.cid);
          
          const response = await get_card(formData);
          if (response && response.error_num === 0 && response.content && response.content.history) {
            history = response.content.history;
            // 更新卡片数据，避免重复请求
            card.history = history;
          }
        } catch (e) {
          console.error('[extractFileListFromCard] 获取完整卡片数据失败:', e);
        }
      }
      
      // 从 history 中提取所有轮次的文件列表并集
      if (history) {
        try {
          // 如果 history 是字符串，先解析
          if (typeof history === 'string') {
            history = JSON.parse(history);
          }
          
          // history 可能是 { data: [...] } 结构，或者直接是 data 数组
          let historyData = null;
          if (history && history.data && Array.isArray(history.data)) {
            historyData = history.data;
          } else if (Array.isArray(history)) {
            historyData = history;
          }
          
          // 🔥 从所有轮次对话中提取文件列表的并集
          const fileSet = new Set();
          if (historyData && Array.isArray(historyData)) {
            historyData.forEach(dataItem => {
              if (dataItem && dataItem.filelist && Array.isArray(dataItem.filelist)) {
                dataItem.filelist.forEach(fileName => {
                  if (fileName) {
                    fileSet.add(fileName);
                  }
                });
              }
            });
          }
          
          fileList = Array.from(fileSet);
        } catch (e) {
          console.error('[extractFileListFromCard] 从 history 提取文件列表失败:', e);
        }
      }
      
      return fileList;
    },

    // 🔥 从 contentTitle 中提取子场景编号（Sn）
    extractSubSceneFromContentTitle(contentTitle) {
      if (!contentTitle) return null;
      
      // 匹配 S1:、S2: 等格式
      const match = contentTitle.match(/^S(\d+):/);
      if (match) {
        const subSceneIndex = parseInt(match[1]) - 1; // S1 对应索引 0
        if (this.subSceneList && subSceneIndex >= 0 && subSceneIndex < this.subSceneList.length) {
          return this.subSceneList[subSceneIndex];
        }
      }
      
      return null;
    },

    // 🔥 应用卡片状态：自动勾选文档和切换子场景
    async applyCardState(card) {
      if (!card) return;
      
      // 🔥 保存当前状态到历史（在应用新状态之前）
      // 移除同一卡片的历史记录（如果存在），然后添加新的
      this.cardStateHistory = this.cardStateHistory.filter(state => state.cardId !== card.cid);
      this.cardStateHistory.push({
        cardId: card.cid,
        fileNameList: [...this.fileNameList],
        subSceneName: this.subSceneName,
        threeWindowModels: {
          main: this.curModelInfo ? this.curModelInfo.id : null,
          up: this.curModelInfoUp ? this.curModelInfoUp.id : null,
          down: this.curModelInfoDown ? this.curModelInfoDown.id : null
        }
      });
      
      // 提取子场景
      const targetSubScene = this.extractSubSceneFromContentTitle(card.contentTitle);
      
      // 切换子场景（如果有）
      if (targetSubScene && targetSubScene !== this.subSceneName) {
        const subSceneIndex = this.subSceneList.indexOf(targetSubScene);
        if (subSceneIndex >= 0) {
          this.changeSubScene(targetSubScene, subSceneIndex);
          // 提示用户
          this.$message.info(`已自动切换到子场景：${targetSubScene}`);
        }
      }

      // 🔥 恢复三窗口模型配置
      try {
        let threeWindowModels = null;
        if (card.three_window_models) {
          // 如果卡片数据中已有三窗口模型配置
          threeWindowModels = typeof card.three_window_models === 'string' 
            ? JSON.parse(card.three_window_models) 
            : card.three_window_models;
        } else {
          // 如果卡片数据中没有，尝试从后端获取完整卡片数据
          const formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          formData.append('cid', card.cid);
          
          const cardData = await get_card(formData);
          if (cardData.error_num === 0 && cardData.content) {
            const fullCard = cardData.content;
            if (fullCard.three_window_models) {
              threeWindowModels = typeof fullCard.three_window_models === 'string' 
                ? JSON.parse(fullCard.three_window_models) 
                : fullCard.three_window_models;
            }
          }
        }
        
        // 恢复三窗口模型配置
        if (threeWindowModels) {
          this.restoreThreeWindowModels(threeWindowModels);
          this.$message.info('已自动恢复三窗口模型配置');
        }
      } catch (e) {
        console.error('[applyCardState] 恢复三窗口模型配置失败:', e);
      }
      
      // 🔥 异步提取文件列表（可能需要获取完整卡片数据）
      try {
        const targetFileList = await this.extractFileListFromCard(card);
        
        // 自动勾选文档（如果有，且排除 split=0 的文件）
        if (targetFileList.length > 0 && this.$refs.FileList && this.$refs.FileList.fileList) {
          this.$nextTick(() => {
            const fileList = this.$refs.FileList.fileList || [];
            
            // 🔥 先取消所有文件的勾选
            fileList.forEach((file, index) => {
              if (file.checked) {
                file.checked = false;
                this.$refs.FileList.handleFileCheckedUpdate(false, index);
              }
            });
            
            // 🔥 然后勾选目标文件列表中的文件（排除 split=0 的文件）
            let checkedCount = 0;
            targetFileList.forEach(fileName => {
              const fileIndex = fileList.findIndex(f => f.file && f.file.name === fileName);
              if (fileIndex >= 0) {
                const fileItem = fileList[fileIndex];
                // 🔥 过滤掉 split=0 的文件
                if (fileItem.split === 0) {
                  return;
                }
                if (!fileItem.checked) {
                  fileItem.checked = true;
                  this.$refs.FileList.handleFileCheckedUpdate(true, fileIndex);
                  checkedCount++;
                }
              }
            });
            
            if (checkedCount > 0) {
              this.$message.info(`已自动勾选 ${checkedCount} 个文档`);
            }
          });
        }
      } catch (e) {
        console.error('[applyCardState] 提取文件列表失败:', e);
      }
    },

    // 🔥 恢复初始状态
    restoreInitialState() {
      if (!this.initialFileState) return;
      
      // 🔥 先保存初始状态的副本，避免异步回调时被清空
      const currentInitialState = this.initialFileState;
      if (!currentInitialState) return;
      
      const savedInitialState = {
        fileNameList: Array.isArray(currentInitialState.fileNameList) 
          ? [...currentInitialState.fileNameList] 
          : [],
        subSceneName: currentInitialState.subSceneName || this.subSceneName || ''
      };
      
      // 恢复子场景
      if (savedInitialState.subSceneName && savedInitialState.subSceneName !== this.subSceneName) {
        const subSceneIndex = this.subSceneList.indexOf(savedInitialState.subSceneName);
        if (subSceneIndex >= 0) {
          this.changeSubScene(savedInitialState.subSceneName, subSceneIndex);
        }
      }

      // 🔥 恢复三窗口模型配置
      if (currentInitialState.threeWindowModels) {
        this.restoreThreeWindowModels(currentInitialState.threeWindowModels);
      }
      
      // 恢复文件勾选状态
      if (this.$refs.FileList && Array.isArray(savedInitialState.fileNameList)) {
        this.$nextTick(() => {
          if (!this.$refs.FileList) return;
          const fileList = this.$refs.FileList.fileList || [];
          const initialFileSet = new Set(savedInitialState.fileNameList);
          
          fileList.forEach((file, index) => {
            const shouldBeChecked = file.file && initialFileSet.has(file.file.name);
            if (file.checked !== shouldBeChecked) {
              file.checked = shouldBeChecked;
              this.$refs.FileList?.handleFileCheckedUpdate(shouldBeChecked, index);
            }
          });
        });
      }
      
      // 清空状态历史
      this.cardStateHistory = [];
      this.initialFileState = null;
    },

    // 🔥 恢复到倒数第二张卡片的状态
    restorePreviousCardState() {
      // 获取最后一张还勾选的卡片ID
      if (this.choosedCardIdList.length === 0) {
        // 如果没有勾选的卡片，恢复到初始状态
        this.restoreInitialState();
        return;
      }
      
      const lastCardId = this.choosedCardIdList[this.choosedCardIdList.length - 1];
      
      // 从历史中找到对应卡片的状态
      const lastCardState = this.cardStateHistory.find(state => state.cardId === lastCardId);
      
      if (lastCardState) {
        // 恢复子场景
        if (lastCardState.subSceneName !== this.subSceneName) {
          const subSceneIndex = this.subSceneList.indexOf(lastCardState.subSceneName);
          if (subSceneIndex >= 0) {
            this.changeSubScene(lastCardState.subSceneName, subSceneIndex);
          }
        }

        // 🔥 恢复三窗口模型配置
        if (lastCardState.threeWindowModels) {
          this.restoreThreeWindowModels(lastCardState.threeWindowModels);
        }
        
        // 恢复文件勾选状态
        if (this.$refs.FileList && lastCardState && lastCardState.fileNameList) {
          // 🔥 先保存状态副本，避免异步回调时被修改
          const savedFileNameList = Array.isArray(lastCardState.fileNameList) 
            ? [...lastCardState.fileNameList] 
            : [];
          
          this.$nextTick(() => {
            const fileList = this.$refs.FileList?.fileList || [];
            const previousFileSet = new Set(savedFileNameList);
            
            fileList.forEach((file, index) => {
              const shouldBeChecked = file.file && previousFileSet.has(file.file.name);
              if (file.checked !== shouldBeChecked) {
                file.checked = shouldBeChecked;
                this.$refs.FileList?.handleFileCheckedUpdate(shouldBeChecked, index);
              }
            });
          });
        }
        
        // 移除已取消勾选卡片的历史
        this.cardStateHistory = this.cardStateHistory.filter(state => 
          this.choosedCardIdList.includes(state.cardId)
        );
      } else {
        // 如果没有找到状态，恢复到初始状态
        this.restoreInitialState();
      }
    },

    // 🔥 恢复三窗口模型配置
    restoreThreeWindowModels(threeWindowModels) {
      if (!threeWindowModels) return;
      
      try {
        const modelInfoList = this.modelList || [];
        
        // 恢复主窗口模型
        if (threeWindowModels.main) {
          const mainModel = modelInfoList.find(m => m.id === threeWindowModels.main);
          if (mainModel && this.curModelInfo && this.curModelInfo.id !== mainModel.id) {
            this.toBeSwitched = 0;
            this.handleSelectModelUpdate(mainModel);
          }
        }
        
        // 恢复右上窗口模型
        if (threeWindowModels.up) {
          const upModel = modelInfoList.find(m => m.id === threeWindowModels.up);
          if (upModel && this.curModelInfoUp && this.curModelInfoUp.id !== upModel.id) {
            this.toBeSwitched = 1;
            this.handleSelectModelUpdate(upModel);
          }
        }
        
        // 恢复右下窗口模型
        if (threeWindowModels.down) {
          const downModel = modelInfoList.find(m => m.id === threeWindowModels.down);
          if (downModel && this.curModelInfoDown && this.curModelInfoDown.id !== downModel.id) {
            this.toBeSwitched = 2;
            this.handleSelectModelUpdate(downModel);
          }
        }
      } catch (e) {
        console.error('[restoreThreeWindowModels] 恢复三窗口模型配置失败:', e);
      }
    },
    
    getCardRelQue() {
      this.$refs.ChatWindow.getCardRelQue(this.fileNameList, this.rightSelectList);
    },

    handleDragStart(windowId) {
      this.isHighlighted = true;
      this.activeDragWindow = windowId;
    },
    handleDragEnd() {
      this.isHighlighted = false;
      this.activeDragWindow = null;
    },
    
    handleDrop(event, targetWindowId) {
      if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
        this.$message.error('您不是作者，暂时没有权限融合回答生成卡片');
        return
      }

      // 这里event是原生DOM事件的原生DragEvent对象，所以能取到拖拽开始时chatwindow.vue存入此对象的数据
      // 原生DOM事件不同于$emit触发的自定义事件，是Vue的两种事件类型
      const sourceData = JSON.parse(event.dataTransfer.getData('application/json'));
      
      // 防止拖到自己的窗口
      if (sourceData.sourceWindowId === targetWindowId) {
        return;
      }

      // 获取目标窗口的ref组件引用
      const targetWindow = targetWindowId === 'left' 
        ? this.$refs.ChatWindow
        : targetWindowId === 'upper'
          ? this.$refs.ChatWindowUp
          : this.$refs.ChatWindowDown;
      
      // 获取源窗口的ref组件引用
      const sourceWindow = sourceData.sourceWindowId === 'left'
        ? this.$refs.ChatWindow
        : sourceData.sourceWindowId === 'upper'
          ? this.$refs.ChatWindowUp
          : this.$refs.ChatWindowDown;
      
      // 调用2模型输出的主辅merge合并方法
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('sourceModel', sourceData.modelName);
      formData.append('targetModel', targetWindow.chatList[targetWindow.chatList.length - 1].name);
      formData.append('sourceResponse', sourceData.modelResponse);
      formData.append('targetResponse', targetWindow.chatList[targetWindow.chatList.length - 1].msg);
      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', this.subSceneName);
      formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递
      console.log("dragData:", sourceData.modelResponse, targetWindow.chatList[targetWindow.chatList.length - 1].msg)
      this.showCardWindow()
      merge2Responses(formData).then(data => {
        if(data['error_num'] === 0) {
          let cid = data['cardId']
          let mergeContent = data['mergeContent']
          this.$message.success("2模型回复合并成功，留存卡片")
          this.cardMaking = false;
          this.cardUpdate = true;
          this.waitDecodedResult(cid, mergeContent)
        } else {
          this.$message.error("2模型回复合并失败")
          this.cardMaking = false;
          this.cardUpdate = true;
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
      
      this.isHighlighted = false;
      this.activeDragWindow = null;
    },

    saveKeyTopics(keyTopics) {
      this.keyTopics = keyTopics
    },
    showMenu() {
      this.menuVis = true;
    },
    hideMenu() {
      this.menuVis = false
    },
    changeCardGrid() {
      this.menuVis = false
      if(this.classCardGrid === 'Grid')
        this.classCardGrid = 'GridFold'
      else
        this.classCardGrid = 'Grid'
    },

    getUseToFinetune() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('realName'));
      this.$message.success("请求已提交")
      getUseToFinetune(formData).then(data => {
        if(data['error_num'] === 0) {
          this.$message.success("成功提取用户卡片数据，将用于微调")
        } else {
          this.$message.error("提取用户卡片数据失败")
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },

    fileUploadLog(filename) {
      this.context.stream.push({
        time: Date.now(),
        action: "进行了文件上传",
        Specifics: { 
          "human": "上传了文件，已经成功上传系统", 
          "AI":  + "上传的文件名：\n" + filename
        },
        comments: "请给些点评/改进建议吧"
      });
    },
    cardClickLog(content, score, reason, keyWords, contentTitle) {
      this.context.stream.push({
        time: Date.now(),
        action: "进行了卡片点击查看",
        Specifics: { 
          "human": "点击了卡片，查看卡片内容", 
          "AI":  + "关键词：\n" + keyWords + "\n\n一句话标题：\n" + contentTitle + "\n\n卡片内容如下：\n" + content + "\n\n红蓝卡标评分：\n" + score + "\n\nreview及改进建议：\n" + reason
        },
        comments: "请给些点评/改进建议吧"
      });
    },
    updateContext() {
      if (localStorage.getItem('byadmin') !== 'true' && localStorage.getItem('byuplevel') !== 'true') {
        this.sendContextToServer()
      }
    },
    stopPeriodicUpdate() {
      const intervalId = localStorage.getItem('intervalId');
      if (intervalId) {
        clearInterval(Number(intervalId));
        this.intervalId = null;
        localStorage.removeItem('intervalId');
      }
      // 获取一个足够大的数字，确保覆盖所有可能的定时器ID
      const interval_id = window.setInterval(()=>{}, 9999);
      for (let i = 1; i <= interval_id; i++) {
        window.clearInterval(i);
      }
    },
    startPeriodicUpdate() {
      // 保存定时器的ID，以便后续可以清除
      let intervalId = setInterval(this.sendContextToServer, 30000); // 每分钟1次更新
      localStorage.setItem('intervalId', intervalId);
    },
    sendContextToServer() {
      let formData = new FormData();
      let notebookName = localStorage.getItem('userId').substring(localStorage.getItem('realName').length + 1);
      formData.append('username', localStorage.getItem('realName'));
      formData.append('bookName', notebookName);
      // 将 context 对象转换为 JSON 字符串
      let contextString = JSON.stringify(this.context);
      formData.append('context', contextString);
      console.log("当次操作流：", this.context)
      update_context(formData).then(data => {
        if(data['error_num'] === 0) {
          console.log("保存操作流成功")
          if(data['controlled'] !== 0) {
            localStorage.setItem('controlled', 'true');
            this.clickAdmin = true
          }
        } else {
          console.log("保存操作流失败")
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    clickOver() {
      this.clickAdmin = false
    },
    cardMerge(finalContent, choosedText) {
      if(choosedText === '') {
        this.context.stream.push({
          time: Date.now(),
          action: "进行了卡片迭代",
          Specifics: { 
            "human1": "请对卡片进行迭代", 
            "AI1": "迭代完成，新的卡片内容：\n" + finalContent
          },
          comments: "请给些点评吧"
        });
      } else {
        this.context.stream.push({
          time: Date.now(),
          action: "进行了卡片迭代追问：\n" + choosedText,
          Specifics: { 
            "human1": "请对卡片进行迭代", 
            "AI1": "迭代完成，新的卡片内容：\n" + finalContent
          },
          comments: "请给些点评吧"
        });
      }  
    },
    handleBeforeUnload(event) {
      // 调用后端 API 来更新用户状态
      // 对于大多数浏览器，返回一个字符串将触发确认对话框，但是一些浏览器（如 Chrome）不允许自定义退出提示
      // return event.returnValue = '您确定要离开吗？';
      console.log("退出")
      let formData = new FormData();
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
    },
    // 拖拽测试demo（之后用于卡片拖拽）
    startDrag(event) {
      this.isDragging = true;
      this.offset.x = event.clientX - this.position.x;
      this.offset.y = event.clientY - this.position.y;
    },
    stopDrag() {
      this.isDragging = false;
    },
    onDrag(event) {
      if (this.isDragging) {
        this.position.x = event.clientX - this.offset.x;
        this.position.y = event.clientY - this.offset.y;
      }
    },

    closeChangeLeftPdfView() {
      var main_right_container = document.querySelector('.main-right');
      var text_container = document.querySelector('.main-left2');
      // var input_btn_container = document.querySelector('.chat-choose-boxup');
      // if (this.chooseEnOrEnZh === 'EnZh' && this.isTransPdfReady === true) {
      if ((this.sceneName === "阅读" && this.subSceneName === "中英对比阅读") || this.sceneName.includes("中英文专业阅读")) {
        text_container.style.width = '44%';
        main_right_container.style.width = '76%';
        // input_btn_container.style.display = 'block';
        // text_container.style.transition = '0.5s ease';
        // main_right_container.style.transition = '0.5s ease';
        // input_btn_container.style.transition = '0.5s ease';
        this.leftPdfViewMode = 0
      }
    },
    maybeEnZhDisplay() {
      // 🔥 修复：移除对isTransPdfReady的限制，让伸缩按钮随时都能工作（控制左侧和右侧区域的宽度比例）
      var main_right_container = document.querySelector('.main-right');
      var text_container = document.querySelector('.main-left2');
      // var input_btn_container = document.querySelector('.chat-choose-boxup');
      
      // 🔥 修复：先根据当前leftPdfViewMode状态执行操作，再切换flexBtnChecked，确保状态一致
      if (this.leftPdfViewMode === 0) {
        // 当前是右侧宽、左侧窄，切换到左侧宽、右侧窄
        text_container.style.width = '70%';
        main_right_container.style.width = '30%';
        // input_btn_container.style.display = 'none';
        text_container.style.transition = '0.5s ease';
        main_right_container.style.transition = '0.5s ease';
        // input_btn_container.style.transition = '0.5s ease';
        this.leftPdfViewMode = 1;
        this.flexBtnChecked = true; // 左侧宽时，显示向左箭头
      } 
      else {
        // 当前是左侧宽、右侧窄，切换到左侧窄、右侧宽
        text_container.style.width = '30%';
        main_right_container.style.width = '70%';
        // input_btn_container.style.display = 'block';
        text_container.style.transition = '0.5s ease';
        main_right_container.style.transition = '0.5s ease';
        // input_btn_container.style.transition = '0.5s ease';
        this.leftPdfViewMode = 0;
        this.flexBtnChecked = false; // 右侧宽时，显示向右箭头
      }
    },
    chooseEn() {
      if(this.chooseEnOrEnZh === 'EnZh' || this.chooseEnOrEnZh === 'Zh') {
        this.chooseEnOrEnZh = 'En'
        // 🔥 修复：检查元素是否存在再设置样式
        const pdfFrame = document.getElementById("pdfFrame");
        if (pdfFrame) pdfFrame.style.width = '100%';
        // 🔥 修复：切换到只显示原文时，重置伸缩按钮状态
        // 默认状态下（较宽），应该显示向左箭头（表示点击后会向左收缩），所以flexBtnChecked应该是true
        this.flexBtnChecked = true;  // 向左箭头，表示当前可以向左收缩
        this.leftPdfViewMode = 1;    // 初始状态设为1（左侧宽），这样第一次点击会收缩到0（右侧宽）
      } else if(this.chooseEnOrEnZh === 'En') {
        this.chooseEnOrEnZh = 'EnZh'
        this.$nextTick(() => {
          // pdfViewer已经渲染
          // 🔥 修复：检查元素是否存在再设置样式
          const pdfFrame = document.getElementById("pdfFrame");
          const pdfTransFrame = document.getElementById("pdfTransFrame");
          if (pdfFrame) pdfFrame.style.width = '0%';
          if (pdfTransFrame) pdfTransFrame.style.width = '100%';
        });
      }
    },
    chooseEnZh() {
      // 🔥 用户点击"中英对比"时，检查是否有译文PDF，如果没有才触发翻译
      if((this.sceneName === "阅读" && this.subSceneName === "中英对比阅读") || this.sceneName.includes("中英文专业阅读")) {
        const filePath = this.curFileInfo?.name || '';
        const userId = localStorage.getItem('userId');
        
        if (filePath && !this.isTransPdfReady) {
          // 还没有译文PDF，先检查是否有译文PDF
          this.$message.success("稍作等待后，将开始翻译或获取已有结果，请稍等");
          const checkUrl = `${API_BASE_URL}/api/check-translation/?url=${encodeURIComponent(filePath)}&userbook=${encodeURIComponent(userId)}`;
          fetch(checkUrl)
            .then(response => response.json())
            .then(data => {
              if (data.status === 'completed') {
                // 已有译文PDF，直接触发翻译状态检查
                this.chooseEnOrEnZh = 'EnZh';
                this.$nextTick(() => {
                  // 🔥 修复：检查元素是否存在再设置样式
                  const pdfFrame = document.getElementById("pdfFrame");
                  const pdfTransFrame = document.getElementById("pdfTransFrame");
                  if (pdfFrame) pdfFrame.style.width = '50%';
                  if (pdfTransFrame) pdfTransFrame.style.width = '50%';
                });
                this.checkTranslationStatus(filePath, userId, API_BASE_URL + "/");
              } else {
                // 没有译文PDF，触发翻译API调用
                this.chooseEnOrEnZh = 'EnZh';
                this.$nextTick(() => {
                  // 🔥 修复：检查元素是否存在再设置样式
                  const pdfFrame = document.getElementById("pdfFrame");
                  const pdfTransFrame = document.getElementById("pdfTransFrame");
                  if (pdfFrame) pdfFrame.style.width = '50%';
                  if (pdfTransFrame) pdfTransFrame.style.width = '50%';
                });
                this.$message.success("正在翻译或获取结果，请稍等，您可以关闭或退出，翻译将在后台执行");
                this.checkTranslationStatus(filePath, userId, API_BASE_URL + "/");
              }
            })
            .catch(error => {
              console.error('检查翻译状态失败:', error);
              // 检查失败时，也触发翻译API调用
              this.chooseEnOrEnZh = 'EnZh';
              this.$nextTick(() => {
                // 🔥 修复：检查元素是否存在再设置样式
                const pdfFrame = document.getElementById("pdfFrame");
                const pdfTransFrame = document.getElementById("pdfTransFrame");
                if (pdfFrame) pdfFrame.style.width = '50%';
                if (pdfTransFrame) pdfTransFrame.style.width = '50%';
              });
              this.$message.success("正在翻译或获取结果，请稍等，您可以关闭或退出，翻译将在后台执行");
              this.checkTranslationStatus(filePath, userId, API_BASE_URL + "/");
            });
        } else {
          // 已有译文PDF或不需要翻译的场景，直接显示
          this.chooseEnOrEnZh = 'EnZh';
          this.$nextTick(() => {
            // 🔥 修复：检查元素是否存在再设置样式
            const pdfFrame = document.getElementById("pdfFrame");
            const pdfTransFrame = document.getElementById("pdfTransFrame");
            if (pdfFrame) pdfFrame.style.width = '50%';
            if (pdfTransFrame) pdfTransFrame.style.width = '50%';
          });
        }
      } else {
        // 其他场景，保持原有逻辑
        this.chooseEnOrEnZh = 'EnZh';
        this.$nextTick(() => {
          // 🔥 修复：检查元素是否存在再设置样式
          const pdfFrame = document.getElementById("pdfFrame");
          const pdfTransFrame = document.getElementById("pdfTransFrame");
          if (pdfFrame) pdfFrame.style.width = '50%';
          if (pdfTransFrame) pdfTransFrame.style.width = '50%';
        });
      }
    },

    // 🔥 中英对比阅读：新窗口显示（原文/译文各一个标签；若存在OCR转换PDF再开第3个）
    // 文本文档：新窗口显示
    openTxtInNewWindow() {
      try {
        if (!this.showTxtViewer) return;
        const title = (this.curFileInfo?.name || '文档').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        const text = String(this.curFileInfo?.text || '');
        const w = window.open('', '_blank');
        if (!w) {
          this.$message.warning('浏览器拦截了弹窗，无法打开新窗口');
          return;
        }
        const scriptCloseTag = '</scr' + 'ipt>';
        w.document.open();
        w.document.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${title}</title>
  <style>
    html, body { margin:0; padding:0; height:100%; background:#f6f6f6; }
    .bar { height:40px; display:flex; align-items:center; padding:0 12px; background:#fff; border-bottom:1px solid #e5e5e5; font:14px/1.2 sans-serif; color:#333; }
    pre { margin:0; padding:16px 20px; white-space:pre-wrap; word-wrap:break-word; font:15px/1.7 Consolas, monospace; background:#fff; min-height:calc(100% - 40px); box-sizing:border-box; }
  </style>
</head>
<body>
  <div class="bar"><span>${title}</span></div>
  <pre id="t"></pre>
  <script>
    document.getElementById('t').textContent = ${JSON.stringify(text)};
  ${scriptCloseTag}
</body>
</html>`);
        w.document.close();
      } catch (e) {
        console.error('[openTxtInNewWindow] error:', e);
        this.$message.error('新窗口打开失败');
      }
    },

    // 新窗口显示 PDF（全场景可用；OCR 有则开；译文仅阅读类子场景）
    async openPdfInNewWindows() {
      try {
        // if (!this.showPdfViewer || !this.isObjScene || !this.curFileInfo?.name?.endsWith?.('.pdf')) return;
        if (!this.showPdfViewer || !this.curFileInfo?.name?.endsWith?.('.pdf')) return;

        // 原文是否加载好
        if (this.isLoading || !this.fileUrl) {
          this.$message.warning('原文PDF尚未加载完成，请稍等');
          return;
        }

        // 🔥 根据当前显示状态和翻译状态决定是否打开原文/译文窗口
        // 非阅读类场景无译文时：只开原文
        const shouldOpenOriginal = this.chooseEnOrEnZh !== 'Zh';  // 只有显示译文时不打开原文
        // const shouldOpenTranslated = this.chooseEnOrEnZh === 'Zh' || (this.chooseEnOrEnZh === 'EnZh' && !this.isTranslating && !this.isLoadingTrans && this.isTransPdfReady && this.fileTransUrl);
        const shouldOpenTranslated = this.isObjScene && (
          this.chooseEnOrEnZh === 'Zh' ||
          (this.chooseEnOrEnZh === 'EnZh' && !this.isTranslating && !this.isLoadingTrans && this.isTransPdfReady && this.fileTransUrl)
        );

        const getScrollPercentage = (frameId) => {
          try {
            const frame = document.getElementById(frameId);
            if (!frame || !frame.contentWindow) return 0;
            const doc = frame.contentWindow.document;
            const body = doc.body;
            const html = doc.documentElement;
            const scrollTop = (body && body.scrollTop) || (html && html.scrollTop) || 0;
            const scrollHeight = (body && body.scrollHeight) || (html && html.scrollHeight) || 0;
            const clientHeight = (html && html.clientHeight) || 0;
            if (scrollHeight <= clientHeight || clientHeight === 0) return 0;
            return Math.max(0, Math.min(1, scrollTop / (scrollHeight - clientHeight)));
          } catch (e) {
            return 0;
          }
        };

        const spLeft = shouldOpenOriginal ? getScrollPercentage('pdfFrame') : 0;
        const spRight = shouldOpenTranslated ? getScrollPercentage('pdfTransFrame') : 0;

        // 🔥 不走路由：直接新开标签页（about:blank）写入iframe，并按滚动百分比恢复
        // 为避免部分浏览器只允许打开1个弹窗：先同步预开窗口，再写入内容
        const writePdfIntoWindow = (w, src, sp, title) => {
          if (!w) return;

          const safeTitle = String(title || 'PDF').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          const spNum = Number(sp);
          const spSafe = Number.isFinite(spNum) ? Math.max(0, Math.min(1, spNum)) : 0;
          const srcEsc = String(src || '').replace(/"/g, '&quot;');

          w.document.open();
          // 注意：Vue SFC 内不能出现字面量 “</scr” + “ipt>”，否则会被解析器误判为结束标签
          const scriptCloseTag = '</scr' + 'ipt>';
          w.document.write(`<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${safeTitle}</title>
  <style>
    html, body { margin:0; padding:0; height:100%; background:#f6f6f6; }
    .bar { height:40px; display:flex; align-items:center; padding:0 12px; background:#fff; border-bottom:1px solid #e5e5e5; font:14px/1.2 sans-serif; color:#333; }
    .tip { margin-left:10px; font-size:12px; color:#999; }
    iframe { width:100%; height:calc(100% - 40px); border:none; background:#fff; }
  </style>
</head>
<body>
  <div class="bar">
    <span>${safeTitle}</span>
    <span class="tip" id="tip"></span>
  </div>
  <iframe id="f" src="${srcEsc}"></iframe>
  <script>
    (function() {
      var sp = ${spSafe};
      var tip = document.getElementById('tip');
      var f = document.getElementById('f');
      function apply() {
        try {
          var doc = f.contentWindow.document;
          var body = doc.body;
          var html = doc.documentElement;
          var sh = (body && body.scrollHeight) || (html && html.scrollHeight) || 0;
          var ch = (html && html.clientHeight) || 0;
          if (sh <= ch || ch === 0) return false;
          var top = sp * (sh - ch);
          if (body) body.scrollTop = top;
          if (html) html.scrollTop = top;
          tip.textContent = '已恢复位置';
          return true;
        } catch(e) {
          // 若PDF插件导致不可访问内部document，直接放弃恢复
          tip.textContent = '';
          return true;
        }
      }
      f.addEventListener('load', function() {
        tip.textContent = '正在恢复位置...';
        for (var i=0; i<10; i++) {
          (function(ii){
            setTimeout(function(){ var ok = apply(); if(ok) return; }, ii*250);
          })(i);
        }
      });
    })();
  ${scriptCloseTag}
</body>
</html>`);
          w.document.close();
        };

        const userId = localStorage.getItem('userId');
        const fileName = this.curFileInfo.name;
        const base = fileName.replace(/\.pdf$/i, '');

        // 🔥 为了让浏览器内置PDF"下载"按钮带正确默认文件名：
        // 不使用blob URL（会导致 uuid.pdf），改为打开后端PDF直链，并通过 download_name 指定文件名
        const originalDownloadName = `${base}_原文.pdf`;
        const translatedDownloadName = `${base}_译文.pdf`;
        const originalUrl = `${API_BASE_URL}/api/pdf/?url=${encodeURIComponent(fileName)}&userbook=${encodeURIComponent(userId)}&download_name=${encodeURIComponent(originalDownloadName)}`;
        const translatedUrl = `${API_BASE_URL}/api/pdf/?url=${encodeURIComponent(fileName)}&userbook=${encodeURIComponent(userId)}&sceneName=${encodeURIComponent(this.sceneName + "_result")}&download_name=${encodeURIComponent(translatedDownloadName)}`;

        // 🔥 根据shouldOpenOriginal和shouldOpenTranslated决定打开哪些窗口
        let winLeft = null;
        if (shouldOpenOriginal) {
          winLeft = window.open('', '_blank');
        }
        let winRight = null;
        if (shouldOpenTranslated) {
          winRight = window.open('', '_blank');
        }

        // 🔥 弹窗被拦截时的处理
        if (shouldOpenOriginal && !winLeft) {
          this.$message.warning('浏览器拦截了弹窗，无法打开原文PDF窗口');
        }
        if (shouldOpenTranslated && !winRight) {
          this.$message.warning('浏览器拦截了弹窗，无法打开译文PDF窗口');
        }
        
        // 如果两个窗口都需要打开但都被拦截，显示详细提示
        if (shouldOpenOriginal && shouldOpenTranslated && !winLeft && !winRight) {
          window.focus();
          this.$message({
            type: 'warning',
            duration: 8000,
            dangerouslyUseHTMLString: true,
            message: `<div style="line-height:1.6">
              <b>浏览器拦截了弹窗</b><br/>
              请点击地址栏右侧的 <span style="color:#409EFF">🚫 弹窗拦截图标</span>，选择"始终允许弹窗"后重试。<br/>
              <span style="color:#909399;font-size:12px">（Chrome/Edge：地址栏右侧 | Firefox：地址栏左侧）</span>
            </div>`
          });
          // 不return，继续执行后续OCR窗口逻辑
        }

        // 打开窗口
        if (winLeft) {
          winLeft.location.href = originalUrl;
        }
        if (winRight) {
          winRight.location.href = translatedUrl;
        }

        // OCR 转换 PDF：与场景无关；有则开、无则关预开窗口（译文仍仅阅读类子场景）
        // // 第三个：如果后端存在 xxx_ocr/xxx_converted.pdf（兼容xxx_convert.pdf），再开一个后端直链标签页
        // const userId = localStorage.getItem('userId');
        // const fileName = this.curFileInfo.name;
        // const base = fileName.replace(/\.pdf$/i, '');
        const ocrDownloadName = `${base}_ocr.pdf`;
        const ocrOriginDownloadName = `${base}_ocr_origin.pdf`;

        // 为避免异步后弹窗被拦截：先预开一个窗口，若不存在则自动关闭
        const ocrWin = window.open('', '_blank');
        if (ocrWin) {
          ocrWin.document.open();
          ocrWin.document.write('<!doctype html><html><head><meta charset="utf-8"><title>OCR转换PDF</title></head><body style="font-family:sans-serif;padding:12px;">正在检测OCR转换PDF...</body></html>');
          ocrWin.document.close();
        }
        const ocrOriginWin = window.open('', '_blank');
        if (ocrOriginWin) {
          ocrOriginWin.document.open();
          ocrOriginWin.document.write('<!doctype html><html><head><meta charset="utf-8"><title>OCR转换原始PDF</title></head><body style="font-family:sans-serif;padding:12px;">正在检测OCR转换后的原始PDF...</body></html>');
          ocrOriginWin.document.close();
        }

        // 🔥 通过后端JSON接口检测（避免跨域fetch PDF被CORS阻断）
        const resolveConvertedPdfUrl = async () => {
          try {
            const resp = await fetch(`${API_BASE_URL}/api/check_ocr_converted_pdf?userbook=${encodeURIComponent(userId)}&filename=${encodeURIComponent(fileName)}`);
            if (!resp || !resp.ok) return '';
            const j = await resp.json();
            if (j && j.exists && j.rel_path) {
              return `${API_BASE_URL}/api/pdf/?url=${encodeURIComponent(j.rel_path)}&userbook=${encodeURIComponent(userId)}&download_name=${encodeURIComponent(ocrDownloadName)}`;
            }
          } catch (e) {}
          return '';
        };

        // 🔥 通过后端JSON接口检测（避免跨域fetch PDF被CORS阻断）
        const resolveOriginConvertedPdfUrl = async () => {
          try {
            const resp = await fetch(`${API_BASE_URL}/api/check_ocr_origin_converted_pdf?userbook=${encodeURIComponent(userId)}&filename=${encodeURIComponent(fileName)}`);
            if (!resp || !resp.ok) return '';
            const j = await resp.json();
            if (j && j.exists && j.rel_path) {
              return `${API_BASE_URL}/api/pdf/?url=${encodeURIComponent(j.rel_path)}&userbook=${encodeURIComponent(userId)}&download_name=${encodeURIComponent(ocrOriginDownloadName)}`;
            }
          } catch (e) {}
          return '';
        };

        const ocrUrl = await resolveConvertedPdfUrl();
        const ocrOriginUrl = await resolveOriginConvertedPdfUrl();
        if (ocrWin) {
          if (ocrUrl) {
            ocrWin.location.href = ocrUrl;
          } else {
            ocrWin.close();
          }
        } else if (ocrUrl) {
          // 若预开失败（被拦截），尽量再尝试一次直接打开
          window.open(ocrUrl, '_blank');
        }
        if (ocrOriginWin) {
          if (ocrOriginUrl) {
            ocrOriginWin.location.href = ocrOriginUrl;
          } else {
            ocrOriginWin.close();
          }
        } else if (ocrOriginUrl) {
          // 若预开失败（被拦截），尽量再尝试一次直接打开
          window.open(ocrOriginUrl, '_blank');
        }
      } catch (e) {
        console.error('[openPdfInNewWindows] error:', e);
        this.$message.error('新窗口打开失败');
      }
    },

    toggleDropdown() {
      this.isOpen = !this.isOpen;
    },
    selectOption(option) {
      this.selectedOption = option.value;
      this.selectedOptionLabel = option.label;
      this.isOpen = false;
      event.stopPropagation(); // 阻止事件冒泡到wrapper又变成true
    },
    toggleEmotionDropdown() {
      this.isEmotionOpen = !this.isEmotionOpen;
    },
    selectEmotionOption(option) {
      this.selectedEmotionOption = option.value;
      this.selectedEmotionOptionLabel = option.label;
      this.isEmotionOpen = false;
      event.stopPropagation(); // 阻止事件冒泡到wrapper又变成true
    },
    stopListening() {
      this.isSpeaking = false; // 重置状态
      this.isListening = false; // 重置标志位
      if (this.microphone) {
        const tracks = this.microphone.mediaStream.getTracks();
        tracks.forEach(track => track.stop()); // 停止音频轨道
        this.microphone = null; // 清理引用
      }
      if (this.audioContext) {
        this.audioContext.close(); // 关闭音频上下文
        this.audioContext = null;
      }
    },
    async startListening() {
      // if (this.audioContext) {
      //   this.stopListening(); // 如果正在检测，先停止
      // }
      // 检查浏览器是否支持 getUserMedia
      if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        try {
          // 创建音频上下文
          this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
          // 获取麦克风输入
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          this.microphone = this.audioContext.createMediaStreamSource(stream);
          this.analyser = this.audioContext.createAnalyser();
          this.microphone.connect(this.analyser);
          this.analyser.fftSize = 2048;

          // 创建低通和高通滤波器，只听取人声，过滤环境音和待打断的系统音
          const lowPassFilter = this.audioContext.createBiquadFilter();
          lowPassFilter.type = 'lowpass';
          lowPassFilter.frequency.setValueAtTime(3400, this.audioContext.currentTime); // 高通滤波器，去除3400Hz以上的频率

          const highPassFilter = this.audioContext.createBiquadFilter();
          highPassFilter.type = 'highpass';
          highPassFilter.frequency.setValueAtTime(300, this.audioContext.currentTime); // 低通滤波器，去除300Hz以下的频率

          // 将麦克风音频连接到滤波器
          this.microphone.connect(lowPassFilter);
          lowPassFilter.connect(highPassFilter);
          highPassFilter.connect(this.analyser);
          
          // 开启检测声音
          this.isListening = true; // 设置为正在监听
          this.detectSound();
        } catch (error) {
          console.error('获取麦克风失败:', error);
          this.$message.error('获取麦克风失败');
        }
      } else {
        this.$message.error('您的浏览器不支持音频输入');
      }
    },
    detectSound() {
      const bufferLength = this.analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);
      
      const checkSound = () => {
        if (!this.isListening) return; // 检查标志位

        this.analyser.getByteFrequencyData(dataArray);
        // 检测声音分贝
        const average = dataArray.reduce((sum, value) => sum + value) / bufferLength;
        if (average > 35) { // 根据需要调整这个阈值
          // 声音超过35分贝，就模拟点击一下打断TTS说话，停止打断检测，准备打断后重新进入听阶段
          // this.stopListening()
          this.showVoice()
          if (this.audioContext) {
            this.audioContext.close(); // 关闭音频上下文
            this.audioContext = null;
          }
          this.isListening = false; // 停止检测
          return; // 退出检测
        } else {
          this.isSpeaking = false;
        }

        requestAnimationFrame(checkSound);
      };

      checkSound();
    },
    handleSpeakClose() {
      if(this.voiceStatus !== 0) {
        if(this.voiceStatus === 2) {
          this.$message.error('我还在思考，请听我回答后再决定退出');
        } else {
          this.$message.success('语音听说对话即将结束');
          this.dialogSpeakVisible = false
          this.stopListening();
          this.$refs.ASRVoice.closeVoice();
          this.voiceRecognizing = false;
          this.audioElement.pause();
          this.justCloseSpeak = true
          setTimeout(() => { 
            this.justCloseSpeak = false
          }, 3000); 
        }
      } else {
        this.$message.error('请您等3秒后，初始化完成才可退出');
      }
    },
    showSpeakDialog() {
      if(this.justCloseSpeak === false) {
        this.dialogSpeakVisible = true
        this.voiceRecognizing = false
        this.voiceRecognitionText = ''
        this.voiceStatus = 0
        // 打开语音界面后 2000 毫秒执行，如果2s后用户还没自己点击左上角控制按钮 ，就帮用户自动模拟点击一次
        setTimeout(() => { 
          if(this.voiceStatus === 0) {
            this.showVoice()
          }
        }, 2000); 
      } else {
        this.$message.error('请您等3秒缓冲后，再重新进入听说通道');
      }
    },

    handleClickOutside(event) {
      if (this.isTooltipOpen && 
          !this.$refs.historyBtn.contains(event.target) && 
          !event.target.closest('.tooltip-container')) {
        this.isTooltipOpen = false
      }
      if (this.menuVis &&
          !event.target.closest('.tags-container')) {
        this.hideMenu()
      }
    },
    updateTooltipPosition() {
      if (!this.isTooltipOpen || !this.$refs.historyBtn) return

      const btnRect = this.$refs.historyBtn.getBoundingClientRect()
      const tooltipHeight = 150 // 预估的tooltip高度，可以根据实际调整
      const spacing = 10 // tooltip和按钮之间的间距

      // 计算位置，使tooltip位于按钮上方
      this.tooltipPosition = {
        top: window.scrollY + btnRect.top - tooltipHeight - spacing,
        left: window.scrollX + btnRect.left + (btnRect.width / 2)
      }
    },
    toggleTooltip() {
      this.isTooltipOpen = !this.isTooltipOpen
      if (this.isTooltipOpen) {
        this.$nextTick(() => {
          this.updateTooltipPosition()
        })
      }
    },
    OnOffHistory() {
      this.isHistoryUsed = !this.isHistoryUsed
      if(this.isHistoryUsed === true) {
        this.$message.success('继续问答将参考历史聊天记录');
      } else {
        this.$message.success('继续问答将不再参考历史聊天记录');
      }
    },
    OnOffMemorySystem() {
      this.isMemorySystemUsed = !this.isMemorySystemUsed
      localStorage.setItem('isMemorySystemUsed', this.isMemorySystemUsed ? 'true' : 'false')
      if (this.isMemorySystemUsed) {
        this.$message.success('继续问答将注入账户/场景/本子长短记忆');
      } else {
        this.$message.success('继续问答将不再注入长短记忆（写盘与 Dream 仍可后台进行）');
      }
    },
    OnOffSummary() {
      this.isSummaryUsed = !this.isSummaryUsed
      if(this.isSummaryUsed === true) {
        this.$message.success('继续问答将参考您在当前场景已有卡片的整体摘要');
      } else {
        this.$message.success('继续问答将不再参考您在当前场景已有卡片的整体摘要');
      }
    },
    OnOffCrossNotebook() {
      this.isCrossNotebookContext = !this.isCrossNotebookContext
      localStorage.setItem('crossNotebookContext', this.isCrossNotebookContext ? 'true' : 'false')
      if (this.isCrossNotebookContext) {
        this.$message.success('已开启跨本子关联：问答将自动检索其他相关本子的文档');
      } else {
        this.$message.success('已关闭跨本子关联');
      }
    },

    isUserTextValid(userText) {
      // 正则表达式，确保整个字符串严格符合序号分条的格式
      // 条件a: 以序号（数字.或数字. ）开头，每个序号后面紧跟内容
      // 条件b: 两个条目之间可以用一个或多个换行符分隔，可以有空行，但不能仅用空格分隔
      const regexSplit = /^(\d+\.[\s\S]+?)(\n\s*)*$/gm;
      // const regex = /^(\d+\.[\s\S]+?)(\n+)(\d+\.[\s\S]+?)(\n+)*$/gm;
      const regex = /^(\d+\.[\s\S]+?)(\n+)((\d+\.[\s\S]+?)(\n+))*((\d+\.[\s\S]+?)(\n*))?$/gm;

      // 检查是否每个条目都严格符合序号和内容的格式
      // 这里我们使用match而不是test，因为我们需要检查整个字符串
      const matches = userText.match(regex);
      const matchesSplit = userText.match(regexSplit);
      // console.log("matches: ", matches.length, matches)
      // console.log("matchesSplit: ", matchesSplit.length, matchesSplit)
      this.multiQASplit = matchesSplit

      // 检查匹配结果是否完全符合预期
      // 如果matches为null或长度不为1，说明没有完全匹配或格式不正确
      // 如果有匹配，我们进一步检查是否有多余的内容
      if (matches && matches.length === 1 && matches[0] === userText) {
        return true;
      }
      return false;
    },
    // 流式使用测试
    // 测试按钮的点击处理函数
    async testStreamOutput() {
      if (!this.testText.trim()) {
        this.$message.warning('请先输入测试文本');
        return;
      }
      
      try {        
        // 调用流式处理函数
        const result = await this.waitDecodedResultStream(this.testText);
        
        // 测试完成后提示
        if (result && result !== 'fail') {
          this.$message.success('流式测试完成！');
          console.log('完整结果:', result);
        } else {
          this.$message.error('流式测试失败');
        }
      } catch (error) {
        console.error('测试过程中出错:', error);
        this.$message.error('测试过程中出错: ' + error.message);
      }
    },
    async waitDecodedResultStream(userText) {
      let completeResult = '';
      let partialResults = '';
      
      // 创建或获取用于显示流式输出的元素
      const resultContainer = document.getElementById('stream-result-container');
      if (resultContainer) {
        resultContainer.innerHTML = '<div class="loading">正在分析中...</div>';
      }
      
      await modelHLStream(userText, (result, isDone) => {
        if (!isDone) {
          // 部分结果更新
          partialResults += result;
          if (resultContainer) {
            // 更新UI显示
            resultContainer.innerHTML = `<div class="partial-result">${partialResults}</div>`;
          }
        } else {
          // 流结束，处理完整结果
          completeResult = result;
        }
      });
      
      return completeResult;
    },
    async waitDecodedResult(cid, userText) {
      // 等待 modelHL 异步函数执行完成，并将结果赋值给 decodedResult
      let decodedResult = await modelHL(userText); 
      console.log("红蓝微调评测模型打分：", decodedResult);

      if (decodedResult === "fail") {
        this.$message.error('卡片保存成功，但红蓝微调评测模型打分失败');
        // this.cardMaking = false;
        this.cardUpdate = true;   // 更新CardGrid显示
      } else {
        let formDataSFT = new FormData();
        formDataSFT.append('content', decodedResult);
        formDataSFT.append('cid', cid);
        card_evalSFT(formDataSFT).then(responseSFT => {
          if (responseSFT.error_num === 0) {
            this.$message.success('卡片保存成功！');
          } else {
            this.$message.error('卡片保存成功，但红蓝微调评测模型打分保存失败');
          }
          // this.cardMaking = false;
          this.cardUpdate = true;   // 更新CardGrid显示
        });
      }
      this.context.stream.push({
        time: Date.now(),
        action: "进行了手动的直接卡片生成",
        Specifics: { 
          "human1": "请导入我的人工卡片：\n" + userText, 
          "AI1": "导入成功！"
        },
        comments: "请给些点评吧"
      });
    },
    createDirectCard(userText) {
      if(userText === "") {
        this.$message.warning('文本内容不可为空！');
        return
      }

      if(this.isMultiQAScore === false && this.isAppendSuggestions === false) {
        // level1：普通卡片生成
        // 半自动化新增：记录直接生成卡片
        this.recordOperation('direct_card', {
          content: userText,
          sceneName: this.sceneName,
          subSceneName: this.subSceneName,
          keyTopics: this.keyTopics,
          isMultiQAScore: this.isMultiQAScore,
          isAppendSuggestions: this.isAppendSuggestions
        });

        this.$message.success('正在生成卡片，请稍等');
        this.showAddDirectDialog = false;
        // 🔥 先滚动到顶部，再显示等待卡片
        if (this.$refs.CardGrid) {
          this.$refs.CardGrid.scrollToTop();
        }
        this.cardMaking = true;
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('originRealName', localStorage.getItem('originRealName')); // 添加作者信息
        formData.append('content', userText);
        formData.append('sceneName', this.sceneName);
        formData.append('subSceneName', this.subSceneName);
        formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递
        // 如果选择了图片，则添加到formData
        if (this.selectedFile) {
          formData.append('image', this.selectedFile);
        }

        addCardDirect(formData).then(data => {
          // 注意！！必须是data.data，因为为了传图片新写了不带拦截器的axios实例，其不预处理同时也没有后处理，
          // response的data字段需要手动取出来
          if(data.data['error_num'] === 0) {
            let cid = data.data['cardId']
            // 🔥 设置新生成的卡片ID，用于等待卡消失后滚动到新卡片
            if (this.$refs.CardGrid) {
              this.$refs.CardGrid.setLastCreatedCardId(cid);
            }
            this.cardMaking = false;
            this.cardUpdate = true;
            // this.waitDecodedResult(cid, userText)
            this.$refs.ChatWindow.getModelEval(userText, cid);
            this.$refs.ChatWindow.getOurModelEval(userText, cid, -1);
            this.refreshCardWhenKeywordsReady(cid);

            // 成功后清空文件选择
            this.fileList = [];
            this.selectedFile = null;
            // this.$message.success('卡片生成成功');
            // this.context.stream.push({
            //   time: Date.now(),
            //   action: "进行了手动的直接卡片生成",
            //   Specifics: { 
            //     "human1": "请导入我的人工卡片：" + userText, 
            //     "AI1": "导入成功！"
            //   },
            //   comments: "请给些点评吧"
            // });
            // this.cardMaking = false;
            // this.cardUpdate = true;   // 更新CardGrid显示
          } else {
            this.cardMaking = false;
            this.cardUpdate = true;
            this.$message.error('出错了，请退出重登再试，若再次出错，请联系管理员并暂勿使用此功能');
          }
        })
      } else if(this.isMultiQAScore === true && this.isAppendSuggestions === false) {
        // level2：多QA打分
        if(this.isUserTextValid(userText) === true) {
          this.$message.success('格式正确，请等待，结束后将以卡片保存逐条QA打分结果');
          let formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          formData.append('multiQASplit', JSON.stringify(this.multiQASplit));
          multiQAScore(formData).then(data => {
            if(data['error_num'] === 0) {
              this.$message.success('逐条打分完成，卡片生成成功');
              this.cardUpdate = true;   // 更新CardGrid显示
            } else {
              this.$message.error('出错了，请退出重登再试，若再次出错，请联系管理员并暂勿使用此功能');
            }
          })
        } else {
          alert("格式错误，请调整，要求如下：\n条件a: QA条目均以序号（数字.或数字. ）开头，每个序号后面紧跟内容\n条件b: 两个条目之间可以用一个或多个换行符分隔，可以有空行，但不能仅用空格分隔\n条件c: 除以上外不能有任何其他格式的内容");
        }
      } else {
        // level3：多QA打分追加建议及初始滚动迭代样例 & 二次迭代建议Prompt
        // 首先验证模板
        if (!this.isUserTextValidPlus(userText)) {
          alert("格式错误，请调整，要求如下：\n1.请确保不要改变模板的固定文本和换行！\n2.请确保编号在1-10000之间且单次处理不超过50条\n3.确保所有部分都已填写")
          return;
        }

        this.$message.success('请等待，结束后将以卡片保存多QA打分+建议+初始迭代滚动样例+二次迭代建议Prompt结果');
        this.showAddDirectDialog = false;
        this.cardMaking = true;
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('message', userText);
        formData.append('filenamelist', this.fileNameList);
        formData.append('leftSelectList', this.leftSelectList);
        formData.append('rightSelectList', this.rightSelectList);

        formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递

        multiQAScorePlus(formData).then(data => {
          if(data['error_num'] === 0) {
            let cid = data['cardId']
            let contentTotalSample = data['contentTotalSample']
            this.cardMaking = false;
            this.cardUpdate = true;
            this.waitDecodedResult(cid, contentTotalSample)
            this.$message.success('逐条回答打分建议及初始迭代滚动&二次迭代建议完成，卡片生成成功');
          } else {
            this.cardMaking = false;
            this.cardUpdate = true;
            this.$message.error(data['status']);
          }
        })
      }
    },
    isUserTextValidPlus(userText) {
      // 定义模板结构中必须包含的固定部分
      const requiredStructure = [
        '请勿修改模板结构，仅可调整内容：\n',
        '要处理的问题序号首尾：',
        '\n\n问题列表：\n',
        '\n\n问题出回答的Prompt：\n',
        'TODO（下为默认模板，可随着制备过程发现问题随时调整修改）：\n',
        '\n\n分角色给出OTCL建议、初步迭代滚动样例、二次迭代建议的Prompt：\n',
        'TODO（下为默认模板，可随着制备过程发现问题随时调整修改）：\n'
      ];

      // 检查模板基本结构
      for (let part of requiredStructure) {
        if (!userText.includes(part)) {
          this.$message.error('模板结构被修改，请确保不要改变模板的固定文本和换行！');
          return false;
        }
      }

      // 检查问题序号格式
      const rangeMatch = userText.match(/要处理的问题序号首尾：(\d+)-(\d+)/);
      if (!rangeMatch) {
        this.$message.error('问题序号格式不正确，请使用"数字-数字"的格式！');
        return false;
      }

      const startNum = parseInt(rangeMatch[1]);
      const endNum = parseInt(rangeMatch[2]);
      if (isNaN(startNum) || isNaN(endNum) || startNum > endNum || startNum < 1 || endNum > 10000 || endNum - startNum > 50) {
        this.$message.error('问题序号范围不合法，请确保：\n1. 起始编号小于结束编号\n2. 编号在1-10000之间');
        return false;
      }

      // 检查各部分是否都有内容
      const sections = userText.split('\n\n');
      if (sections.length < 4) {
        this.$message.error('模板缺少必要部分，请确保所有部分都已填写！');
        return false;
      }

      // 检查是否包含问题列表
      const questionListIndex = userText.indexOf('问题列表：');
      const promptIndex = userText.indexOf('问题出回答的Prompt：');
      if (questionListIndex >= promptIndex || questionListIndex === -1) {
        this.$message.error('问题列表部分缺失或位置不正确！');
        return false;
      }

      const questionListContent = userText.substring(
        questionListIndex + '问题列表：'.length,
        promptIndex
      ).trim();

      if (questionListContent === '将《1k问T+Q.doc》中对应序号问题复制粘贴到这里') {
        this.$message.error('请将具体问题内容复制到问题列表部分！');
        return false;
      }
      return true;
    },

    addCardDirectly() {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限添加卡片');
      //   return
      // }
      if (!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限添加卡片');
        return
      }
      this.showAddDirectDialog = true
    },
    updateVoiceRecognitionStatus() {
      setTimeout(() => {
        if (this.inputMsg === "") {
          console.log('this.inputMsg is an empty string.');
          return; // 空的直接返回
        }
        if (this.voiceRecognizing === false) {
          console.log('ASR is closed');
          return; // 已经关闭了直接返回
        }
        let voiceinput = this.inputMsg;
        this.$refs.ChatWindow.sendVoiceMsg(voiceinput);
        if (this.chatBtnChecked === false) this.showChatWindow();
        this.inputMsg = "";

        // 检测是否包含关键词切换，如果要切换，则更新background
        const keyword = "切换";
        if (voiceinput.includes(keyword)) {
          let voiceinput_nopunc = this.removePunctuation(voiceinput);
          const trimmedInput = voiceinput_nopunc.slice(voiceinput_nopunc.indexOf(keyword) + keyword.length);
          console.log(trimmedInput);
          const matchedCard = this.bgcList.find(bgc => bgc.name.includes(trimmedInput));
          if (matchedCard) {
            console.log(matchedCard);
            this.currentBgc = matchedCard;
            this.$message.success('切换成功');
          } else {
            this.$message.error('没有找到卡片');
          }
          return;//直接返回，因为这是一个唤醒词识别过程
        }

        this.voiceStatus = 2
        let responsemsg = '让我思考片刻，稍后给您回复！';
        this.$refs.ChatWindow.sendVoiceModelMsg(responsemsg);
        let formData = new FormData()
        formData.append('username', localStorage.getItem('userId'));
        formData.append('message', voiceinput);
        formData.append('background', this.currentBgc.content);
        formData.append('role', this.selectedOption);
        formData.append('emotion', this.selectedEmotionOption);
        formData.append('rounds', this.rounds);
        // TODO语音：把这里的地址改了，再上传服务器
        fetch(`${API_BASE_URL}/api/asr_chat_send`,
          {
            method: 'POST',
            body: formData,
          })
          .then(response => {
            if (response.ok) {
              console.log('response ok，转换为blob');
              return response.blob();
            }
            throw new Error('Network response was not ok.');
          })
          .then(blob => {
            const audioURL = URL.createObjectURL(blob);
            this.audioElement.src = audioURL;
            let text_formData = new FormData();
            text_formData.append('username', localStorage.getItem('userId'));
            test_get_speech_text(text_formData).then(response => {
              let response_text = response['response_text'];
              this.$refs.ChatWindow.sendVoiceModelMsg(response_text);
            });
            this.audioElement.addEventListener('ended', () => {
              if(this.voiceRecognizing === true) {
                this.isListening = false; // 停止打断检测
                this.voiceStatus = 1
                this.$refs.ASRVoice.openVoice(); // 继续下一轮的识别
              }
            });
            this.voiceStatus = 3
            this.audioElement.play();           // 播放音频
            this.startListening();
            // this.audioElement.play().then(() => {
            //   this.$refs.ASRVoice.openVoice();//继续下一轮的识别
            // }).catch((error) => {
            //   // 播放过程中可能发生的错误处理
            //   console.error("Error playing audio:", error);
            // });;
          })
          .catch(error => {
            // 处理错误
            console.error('There has been a problem with your fetch operation:', error);
          });
      }, 2000);
    },

    updateVoiceRecognitionText(newText) {
      // this.voiceRecognitionText = newText;
      this.inputMsg = newText;
    },
    stringToArray(str) {
      // 去除字符串两端的方括号
      let trimmedStr = str.replace(/^\[|\]$/g, '');
      trimmedStr = trimmedStr.replace(/^\'|\'$/g, '');
      // 使用split方法以逗号分割字符串
      var resultArray = trimmedStr.split("','");
      return resultArray;
    },
    overrideLUI1 () {
      let history = this.loop_history;
      // 定义正则表达式，匹配 "主题裂解最终修正结果：" 及其前面的所有内容，移除可能存在的首尾空白字符
      const roleEndRegex = /主题裂解最终修正结果:(.*)/s;
      const match = roleEndRegex.exec(history);
      let resultAfter = match ? match[1].trim() : '';
      this.curFileInfo.content = resultAfter
      this.$message.success('已覆盖，正在根据修正内容生成新的topics');

      // 覆盖后更新topics
      let formData = new FormData();
      formData.append('summary', this.curFileInfo.content);
      formData.append('topics', this.topicContents);
      console.log("修改前:", this.topicContents)
      this.topicContents = ['正在获取topics'];
      reget_topics(formData).then(data => {
        if(data['error_num'] === 0) {
          this.$message.success('topics更新完成');
          console.log(data['topics'])
          let noSpaceStrTopics = data['topics'].replace(/\s+/g, '');
          this.topicContents = this.stringToArray(noSpaceStrTopics);
          console.log("修改后:", this.topicContents)
        } else {
          this.$message.error('出错了，请退出重登再试，若再次出错，请联系管理员并暂勿使用此功能');
        }
      })
    },
    overrideLUI2 () {
      let history = this.all_history;
      // 定义正则表达式，匹配 "问答追问最终修正结果：" 及其前面的所有内容，移除可能存在的首尾空白字符
      const roleEndRegex = /(.*问答追问最终修正结果:)/gs;
      let resultAfter = history.replace(roleEndRegex, '');
      resultAfter = resultAfter.trim();
      this.LUI2_result_index = resultAfter
      this.$message.success('已覆盖，正在根据修正内容生成新的追问框问题');

      // 覆盖后更新追问que
      this.questionContents = ['正在获取相关问题...'];
      let formData = new FormData();
      formData.append('message', this.msgPlus);
      formData.append('answer', resultAfter);
      formData.append('username', localStorage.getItem('userId'));
      formData.append('filenamelist', this.fileNameList);     // chat_send复制过来的，这个居然是tm小写
      formData.append('rightSelectList', this.rightSelectList);
      reget_ques(formData).then(data => {
        if(data['error_num'] === 0) {
          let rel_questions = data['questions']
          let array_questions = []
          for (let i = 0; i < rel_questions.length; i++) {
            array_questions[i] = rel_questions[i];
          }
          this.questionContents = array_questions;
          this.$message.success('追问框问题更新完成');
        } else {
          this.$message.error('出错了，请退出重登再试，若再次出错，请联系管理员并暂勿使用此功能');
        }
      })
    },
    getButtonLeft(index) {
      let totalWidth = 0;
      for (let i = 0; i < index; i++) {
        // 确保按钮已经被渲染，并且可以通过 ref 访问
        if (this.$refs.buttons[i]) {
          totalWidth += this.$refs.buttons[i].offsetWidth;
        }
      }
      return totalWidth;
    },
    color(score, color) {
      // 假设饱和度为50%，亮度范围从90%到10%，根据score调整
      let baseHue = 270; // 紫色的基准色调
      const saturation = 50; // 饱和度固定为50%
      const minLightness = 50; // 最暗的亮度值
      const maxLightness = 90; // 最亮的亮度值
      const lightnessRange = maxLightness - minLightness;

      let lightness;
      if (score >= 1 && score <= 5) {
        baseHue = 270; // 紫色的基准色调
        lightness = maxLightness - ((score - 1) / 4) * lightnessRange;
      } else if (score > 0 && score < 1) {
        if (color === "红") {
          baseHue = 0; // 红色的基准色调
        } else if (color === "蓝") {
          baseHue = 240; // 蓝色的基准色调
        } else {
          baseHue = 100; // 默认
        }
        lightness = maxLightness - (score / 1) * lightnessRange;
      } else {
        lightness = 100; // 完全透明，相当于白色
      }
      return `hsl(${baseHue}, ${saturation}%, ${lightness}%)`;
    },
    importFromFile() {
      // 清除之前选择的文件
      this.$refs.fileInput.value = null;
      this.$refs.fileInput.click(); // 触发文件选择输入的点击事件
    },
    handleFileChange(event) {
      const file = event.target.files[0];
      if (file) {
        this.importFile = file;
        this.readFile(file); // 读取文件内容
      }
    },
    readFile(file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const data = e.target.result;
        const workbook = XLSX.read(data, { type: 'binary' });

        // 分别处理两个工作表
        const sheetNames = workbook.SheetNames;
        const lui1Data = XLSX.utils.sheet_to_json(workbook.Sheets[sheetNames[0]]);
        const lui2Data = XLSX.utils.sheet_to_json(workbook.Sheets[sheetNames[1]], { header: 1 });
        console.log("LUI2表原始内容:", workbook.Sheets[sheetNames[1]])
        console.log("LUI2表加载内容:", lui2Data)

        const result = {
          lui1: this.convertLui1Data(lui1Data),
          lui2: this.convertLui2Data(lui2Data),
        };

        // 将解析后的数据赋值到表单模型中
        console.log("LUI1:", result.lui1)
        console.log("LUI2:", result.lui2)
        this.formLui1 = result.lui1;
        this.formLui2 = result.lui2;
      };
      reader.readAsBinaryString(file);
    },

    convertLui1Data(lui1Data) {
      // 假设lui1Data[0]包含键名，lui1Data[1]包含对应的值
      const lui1 = {};
      lui1Data.forEach((row, index) => {
        const key = row['键名'];
        const value = row['描述'];
        lui1[key] = isNaN(value) ? value : Number(value); // 转换为数字，如果适用
      });
      return lui1;
    },

    convertLui2Data(lui2Data) {
      const lui2 = {
        roleCount: 3,
        groupInfo: '',
        roles: [],
        groupObjective: '',
        coreProblem: '',
        maxRounds: 0,
      };

      // 假设第一行是标题，从第二行开始是数据
      lui2Data.forEach((row, index) => {
        if (index === 0)
          return;

        if (row[1] === 'identity') {
          // 处理roles行数据
          const role = {
            identity: row[2],
            function: row[4], // 职能在第五列
            responseMethod: row[6], // 回答方式在第七列
          };
          lui2.roles.push(role);
        } else {
          const key = row[0];
          const value = row[1];
          lui2[key] = isNaN(value) ? value : Number(value); // 转换为数字，如果适用
        }
      });

      return lui2;
    },
    updateRolesCount() {
      // 根据 formLui2.roleCount 更新 roles 数组的长度
      while (this.formLui2.roles.length > this.formLui2.roleCount) {
        this.formLui2.roles.pop();
      }
      while (this.formLui2.roles.length < this.formLui2.roleCount) {
        this.formLui2.roles.push({ identity: '', function: '', responseMethod: 'agent' });
      }
    },
    submitPlusConfig() {
      this.dialogPlusVisible = false
    },
    closePlusDialog() {
      this.dialogPlusVisible = false
      // 重置表单数据
      // this.$refs.formLui1.resetFields();
      // this.$refs.formLui2.resetFields();
    },
    submitPlusLUI1Config() {
      this.dialogPlusLUI1 = false
      this.displayScore = false
    },
    closePlusLUI1Dialog() {
      this.dialogPlusLUI1 = false
      this.displayScore = false
    },
    submitPlusLUI2Config() {
      this.dialogPlusLUI2 = false
      this.displayScoreLUI2 = false
    },
    closePlusLUI2Dialog() {
      this.dialogPlusLUI2 = false
      this.displayScoreLUI2 = false
    },
    openConfig() {
      this.dialogPlusVisible = true
    },
    changePlus() {
      this.isPlus = !this.isPlus
      if(this.isPlus === true) {
        this.$message.success("已经启用LUI·Plus能力，请配置好角色后使用");
        this.dialogPlusVisible = true
      } else {
        this.$message.success("已切换回普通LUI能力");
      }
    },
    changeMultiQAScore() {
      if (!this.isMultiQAScore && !this.isAppendSuggestions) {
        this.isMultiQAScore = true;
        this.userDefineForm.userText = ""
        this.$message.success("已启用level2: 多QA对打分，逐条打分后生成完整卡片");
      } else if (this.isMultiQAScore && !this.isAppendSuggestions) {
        this.isAppendSuggestions = true;
        this.isMultiQAScore = false;
        // 设置模板文本
        this.userDefineForm.userText = `请勿修改模板结构，仅可调整内容：
要处理的问题序号首尾：1-50

问题列表：
将《1k问T+Q.doc》中对应序号问题复制粘贴到这里

问题出回答的Prompt：
TODO（下为默认模板，可随着制备过程发现问题随时调整修改）：
请根据这个问题给出清晰、详细的回答。回答要有逻辑性和条理性，要能体现出对问题的深入理解，要求如下：
（1）注意面向的对象是助教火种示范还是小组跟随创造，需要解答的针对性强、照顾对象的接受度，分别的具体要求建议已经告知过你；同时请记得此问答的目的不仅仅限于主题课设，而是课设-课程-计算机领域-更深些的教育认知泛化这个链条指向，需要兼容兼顾，一定不能只停留在某个阶段的视角！
（2）你需要对文档素材中特别是与课程总观和课设精进四主题有关的材料有更深刻的理解，才能真正帮助助教和小组完成精进分级落实，而不是仅有空话套话
（3）文档素材中有给出从W3到W16每周的课设周组织目标和对应的章节课程目标，这是教师给出的，需要结合授课章节内容，同时注意随时间阶段递进的代码和注释主题精进双O目标/除乘加分析的助教模板示范张力，或本组真实化。这些都不要刻意强调，而是要真正理解后，融入到回答中去
（4）我们做这些问答的目标是要将这些零碎的知识以大单元的方式递进组织起来，将知识上升到能力，再上升到习惯，培养学生的质量控制意识和利己利他利当下利未来的习惯规范，包括组织规范和代码命名段注释规范等等，从中筛分出蛙鸣级的精进、涌现，这些内容微小而重要，要让训练出的模型有能判别这些先进行为、牵引学生提高涌现出现的频率的指向
（5）代码及注释综合能力也是很重要的一部分，如果涉及需要具体的已有相关代码和段注释，给你的参考文档素材里有车联、纸联、体联、体联升级各主题（体联在新学期确认使用软硬升级底座）的深度课设代码底座，包括目录结构、文件作用及说明、Lint分析、项目关键代码内容等。如果你在此问答中需要做针对组织不同角色的专业精准理解生成与合并，包括初级注释及代码理解筛分、种子注释及代码升维生成、以及综合合并回底座。你要根据问题或问答情况，考虑侧重于哪一个：
a. 根据往年已有的真实精进发生，如助教精进火种示范、小组精进问解提交、小组报告等，顺着进一步给出精进结果，包括需求、梯子图阶段、目标对齐及公私份任务拆解分配到角色、段注释、代码、XML日志记录、简单小结等综合的for TA或for 小组的精进种子；
b. 根据给你的全部文档素材的各种内容，先提取有潜在价值的代码/注释/文本片段，生成精进提示，即精进点方向是什么，需要简洁而深刻（涉及体联精进的，其在新学期将使用软硬升级底座）；然后使用精进提示细化出plan，再通过plan得到精进结果，即前面说到过的for TA或for 小组的精进种子；
c. 普通的问答。
（6）回答的方向尽量主要关注此问题所属的话题，和话题所属的目标能力
（7<这条很重要>）在（6）的前提下，对不同问题的回答要尽可能保持多样性，一定避免不同问题的回答部分出现类似和冗余重复，以上这些要求都是需要你理解并融入到回答中的，而不是直接原封不动或机械化地放进去，不要在不同回答中重复相同的内容或者这里的要求原话，而是转换为你的深刻理解，并体现为可实施的非常具体的操作，杜绝空话套话和车轱辘话在不同回答里来回说，如果一个问题的回答用在其他问题上也适用，那就不是好回答！想象你自己就是助教或者小组角色，正在进行课设精进，会希望看到什么样的回答。另外对回答中每个关键点都要做些解释说明，以及给你的材料素材里的相关内容，要以身临其境的感受深刻理解并用于回答
（8）回答的格式不要太机械化，不要都用一样的回答格式，前面的这些条目要求也不是一定要全用上的，不要太死板，该用哪些时用哪些。比如如果是一般性的问题，不明确涉及助教或小组，你就根据文档素材里的相关内容回答即可。整体自然一些，避免不同问题却是差不多的回答
（9）其他已经告知过你的要求
（10）单个解答/回答不超过300字，不低于120字（如果你有Thinking或Checking过程，这两个过程总共控制在150字以内）
以上供你参考，虽然是你主要的参照遵循，但还请就题论题（只需回答这一个问题，即前面的[[问题]]标识），随机应变，不同的问题参照合适的条目、素材以及你自己的一些深刻思考理解，并适度放缩视角，综合回答。

分角色给出OTCL建议、初步迭代滚动样例、二次迭代建议的Prompt：
TODO（下为默认模板，可随着制备过程发现问题随时调整修改）：
请针对当前这个问答内容中或其提到的素材中涉及的筛分&方法&策略等关键文字以及可能有的注释和代码等，分别进行如下几个步骤（如果你有Thinking或Checking过程，这两个过程总共控制在100到150字以内）：
1. 针对涉及到的不同角色（2个左右），先分别给出进一步迭代的O/T<目标/任务>改进建议（O和T分开但要有关联），再分别给出C/L<如果文本涉及编程代码注释，C/L是代码/日志或注释，否则就是广义的习作/日志>结合改进建议（C和L分开但要有关联）。这些改进建议一定要具体清晰且完整，高度针对与问答文本相关的，给出足够“专”的建议，而不是通用的、其他问答也可以用的建议，总共200字左右；
2. 再对于当前问题回答内容中或其提到的文档素材中涉及的筛分&方法&策略等关键文字以及注释和代码等（根据此问答是侧重组织、方法之类文字，还是侧重通用的、主题课设的注释和代码，或是二者都涉及且无明显侧重，来考虑给出的初步滚动样例是针对前面所提相关文字性内容，还是针对前面所提相关注释<以承上启下的段注释为主>和代码，还是二者都需要涉及一些。如果与注释和代码有关，原有四主题底座代码均以安卓、java为主，体联升级代码主要为cpp，尽量基于已有的，不要随意使用其他语言；如果问答内容与代码和注释关系不大，则不可以强行补充），提供一个具体的初步迭代滚动优化精进样例，展示如何将前述问答内容本身及建议落实到位，注意迭代精进应该是局域性的、非颠覆的调控递进。字数合适即可，不必过多重复原有的，重点是给出一份含着几个精髓点的修改递进结果；
3. 最后给出下一轮二次迭代优化的指导性建议或一份二次迭代Prompt<含CoT/SoT(Story of Thought)等策略>，帮助持续改进，要和当前问答和以上内容强相关而又有所发散的精进，可以先以SoT将思考总结为故事的形式，简要讲述内涵和目标，再给出3步左右的CoT迭代建议（必要或偏复杂时可考虑ToT或GoT，但分支数量仍需精炼，不可过多），分别表述清楚每一步所处阶段和需要做的事，字数不要过多或过少，总共150到200字左右，清晰、完整、含适当的解释说明，且可立即落实，不空话套话。
注意这些改进建议和迭代精进中，更重要和期望的目标是高度关注蛙鸣创造、熵减指向、升维张力、显隐蜕变（不可直接出现在文字中，需要你深刻理解并融入其中。方向上要往这些拔高点靠拢，内容上要注意一定具体精细，不可泛泛而谈）：
【习惯训练】手拉手普通话·专业命名·熵减发问能力·自学打点变被为主·内观精进·真实目标牵引
【先进组织训练】红蓝公能融合（可牵引公份私份）｛扩长化短（短板者走出舒适圈，领导者熟悉组员角色职责并能够带领）·四步并举（指导型<干什么>-教练型<为什么&怎么干>-支持型<我也干>-授权型<干得怎样>）}
注意：三个步骤是循序渐进的，每一步都在前面步骤的基础上思考和生成，针对不同组织角色进行专业精准的理解、迭代生成与合并，但三步都需要紧密基于当前这一个问题的回答内容，同时别忘了问题内容（只需要考虑前面给你的[[问题]]和[[回答]]标识内容，不要回答或迭代其他相似问题）；且在这三个步骤之前，不要复述当前的这个问题和回答内容！`;
        this.$message.success("已启用level3: 多QA对打分，追加建议及初始滚动迭代，此后留存卡片");
      } else {
        this.isMultiQAScore = false;
        this.isAppendSuggestions = false;
        this.userDefineForm.userText = ""
        this.$message.success("已切回level1: 普通的直接卡片生成");
      }
    },

    setupScrollSync() {
      let isScrolling = false;
      
      const handleScroll = (sourceFrame, targetFrame) => {
        if (isScrolling) return;
        
        isScrolling = true;
        
        // 获取源框架的滚动位置
        const sourceDoc = sourceFrame.contentWindow.document;
        const sourceBody = sourceDoc.body;
        const sourceHtml = sourceDoc.documentElement;
        
        // 计算滚动百分比
        const scrollTop = sourceBody.scrollTop || sourceHtml.scrollTop;
        const scrollHeight = sourceBody.scrollHeight || sourceHtml.scrollHeight;
        const clientHeight = sourceHtml.clientHeight;
        const scrollPercentage = scrollTop / (scrollHeight - clientHeight);
        
        // 将相同的滚动百分比应用到目标框架
        const targetDoc = targetFrame.contentWindow.document;
        const targetBody = targetDoc.body;
        const targetHtml = targetDoc.documentElement;
        const targetScrollHeight = targetBody.scrollHeight || targetHtml.scrollHeight;
        const targetClientHeight = targetHtml.clientHeight;
        
        const targetScrollTop = scrollPercentage * (targetScrollHeight - targetClientHeight);
        targetBody.scrollTop = targetScrollTop;
        targetHtml.scrollTop = targetScrollTop;
        
        setTimeout(() => {
          isScrolling = false;
        }, 50);
      };

      const setupFrameSync = () => {
        const pdfFrame = document.getElementById('pdfFrame');
        const pdfTransFrame = document.getElementById('pdfTransFrame');
        
        if (!pdfFrame || !pdfTransFrame) return;
        
        // 为两个框架添加滚动事件监听器
        pdfFrame.onload = () => {
          pdfFrame.contentWindow.document.addEventListener('scroll', () => {
            handleScroll(pdfFrame, pdfTransFrame);
          }, { passive: true });
        };
        
        pdfTransFrame.onload = () => {
          pdfTransFrame.contentWindow.document.addEventListener('scroll', () => {
            handleScroll(pdfTransFrame, pdfFrame);
          }, { passive: true });
        };
      };

      // 在PDF加载完成后设置滚动同步
      if (this.showPdfViewer && this.chooseEnOrEnZh === 'EnZh' && this.isTransPdfReady) {
        setTimeout(setupFrameSync, 10000);
      }
    },

    // checkTranslationStatus(filePath, userId, previewURL) {
    //   this.isTranslating = true;
    //   fetch(previewURL + '/api/check-translation/?url=' + encodeURIComponent(filePath) + "&userbook=" + encodeURIComponent(userId))
    //     .then(response => response.json())
    //     .then(data => {
    //       if (data.status === 'completed') {
    //         console.log('翻译完成，后端已经有译文pdf');
    //         this.isTranslating = false;
    //         this.isTransPdfReady = true;
    //         this.fileTransUrl = previewURL + "api/pdf/?url=" + encodeURIComponent(filePath) + "&userbook=" + encodeURIComponent(userId) + "&sceneName=" + encodeURIComponent(this.sceneName + "_result");
    //         this.$nextTick(() => {
    //           this.setupScrollSync();
    //         });
    //       } 
    //       else {
    //         if(data.status === 'no') {
    //           console.log('翻译中...');
    //           setTimeout(() => { this.checkTranslationStatus(filePath, userId, previewURL) }, 13000); // 每13秒检查一次
    //         }
    //         else {
    //           this.isTranslating = false;
    //           this.$message.error("翻译文档加载失败，余额不足或译文文件下载失败！");
    //         }
    //       }
    //     })
    //     .catch(error => console.error('检查翻译状态失败:', error));
    // },
    async checkTranslationStatus(filePath, userId, previewURL) {
      this.isLoadingTrans = true;
      this.loadingTransProgress = 0;
      this.loadingTransText = '正在获取PDF文件...';
      this.isTranslating = true;

      var url = previewURL + "api/pdf/?url=" + encodeURIComponent(filePath) + "&userbook=" + encodeURIComponent(userId) + "&sceneName=" + encodeURIComponent(this.sceneName + "_result");
      // 检查内存缓存是否有这个URL的Blob URL
      if(url in this.bufferBlobUrls) {
        // 如果已经有这个URL的Blob URL，直接使用
          const cachedData = this.bufferBlobUrls[url];
          this.fileTransUrl = cachedData.blobUrl;
          this.totalTransBytes = cachedData.size;
          this.loadedTransBytes = this.totalTransBytes;
          console.log("从内存缓存获取 totalTransBytes:", this.totalTransBytes, " loadedTransBytes:", this.loadedTransBytes);
          this.loadingTransProgress = 90; // 已完成下载，预留10%给渲染
          setTimeout(() => {
            this.isTransPdfReady = true;
            this.isLoadingTrans = false;
            this.isTranslating = false;
          }, 1000);
          // 等待iframe加载完成
          this.loadingTransText = '正在渲染PDF...';
          return;
      }
      // 然后尝试从IndexedDB缓存中获取
      try {
        const cachedBlob = await this.getFileFromCache(url, userId);
        if (cachedBlob) {
          // 从缓存获取到了文件
          this.loadingTransText = 'PDF从本地缓存加载中...';
          this.loadingTransProgress = 70;
          
          // 创建Blob URL
          const blobUrl = URL.createObjectURL(cachedBlob);
          this.fileTransUrl = blobUrl;
          
          // 存储到内存缓存
          this.bufferBlobUrls[url] = {
            blobUrl: blobUrl,
            size: cachedBlob.size
          };
          
          this.totalTransBytes = cachedBlob.size;
          this.loadedTransBytes = this.totalTransBytes;
          this.loadingTransProgress = 90;
          
          setTimeout(() => {
            this.isTransPdfReady = true;
            this.isLoadingTrans = false;
            this.isTranslating = false;
          }, 1000);
          // 等待iframe加载完成
          this.loadingTransText = '正在渲染PDF...';
          return;
        }
      } catch (error) {
        console.error('从本地缓存获取文件失败:', error);
        // 失败时继续从服务器获取
      }
      // 如果没有缓存，继续从服务器获取
      fetch(previewURL + '/api/check-translation/?url=' + encodeURIComponent(filePath) + "&userbook=" + encodeURIComponent(userId))
        .then(response => response.json())
        .then(async data => {
          if (data.status === 'completed') {
            console.log('翻译完成，后端已经有译文pdf');
            this.isTranslating = false;
            this.isTransPdfReady = true;
            // this.fileTransUrl = previewURL + "api/pdf-trans/?url=" + encodeURIComponent(filePath) + "&userbook=" + encodeURIComponent(userId) + "&sceneName=" + encodeURIComponent(this.sceneName + "_result");
            // var url = previewURL + "api/pdf/?url=" + encodeURIComponent(filePath) + "&userbook=" + encodeURIComponent(userId) + "&sceneName=" + encodeURIComponent(this.sceneName + "_result");
            this.isLoadingTrans = true;

            this.bufferBlobUrls[url] = {}; // 先占位，防止重复下载

            try {
              // 使用XMLHttpRequest下载PDF并监控进度
              const blob = await this.downloadTransPdfWithProgress(url);
              
              // 创建Blob URL
              const blobUrl = URL.createObjectURL(blob);
              this.fileTransUrl = blobUrl;

              // 存储存储到内存缓存
              this.bufferBlobUrls[url] = {
                blobUrl: blobUrl,
                size: blob.size
              };

              // 存储到IndexedDB
              this.saveFileToCache(url, blob, userId, 'pdf');

              setTimeout(() => {
                this.isLoadingTrans = false;
                console.log("isLoadingTrans", this.isLoadingTrans);
              }, 1000);
              
              // 等待iframe加载完成
              this.loadingTransText = '正在渲染PDF...';
              console.log("loadingTransText", this.loadingTransText);
            } catch (error) {
              console.error('翻译PDF加载失败:', error);
              this.loadingTransText = 'PDF加载失败';
              this.isLoadingTrans = false;
            }
            // this.$nextTick(() => {
            //   this.setupScrollSync();
            // });
          } else {
            if(data.status === 'no') {
              console.log('翻译中...');
              setTimeout(() => { this.checkTranslationStatus(filePath, userId, previewURL) }, 13000); // 每13秒检查一次
            } else if (data.status === 'unable') {
              this.isTranslating = false;
              this.isLoadingTrans = false;
              console.log('isLoading', this.isLoading);
              console.log('isLoadingTrans', this.isLoadingTrans);
              this.chooseEn();
              this.isTransPdfReady = false;
              this.$message.error("该文档不支持翻译！");
            } else {
              this.isTranslating = false;
              this.isLoadingTrans = false;
              console.log('isLoading', this.isLoading);
              console.log('isLoadingTrans', this.isLoadingTrans);
              this.chooseEn();
              this.isTransPdfReady = false;
              this.$message.error("翻译文档加载失败，余额不足或译文文件下载失败！");
            }
          }
        })
        .catch(error => console.error('检查翻译状态失败:', error));
    },
    // 初始化数据库
    initDB() {
      return new Promise((resolve, reject) => {
        const request = indexedDB.open(this.dbName, this.dbVersion);
        
        request.onerror = (event) => {
          console.error('IndexedDB 打开失败:', event);
          this.useFileCache = false; // 如果数据库打开失败，禁用缓存功能
          reject(event);
        };
        
        request.onupgradeneeded = (event) => {
          const db = event.target.result;
          if (!db.objectStoreNames.contains('files')) {
            const store = db.createObjectStore('files', { keyPath: 'url' });
            store.createIndex('timestamp', 'timestamp', { unique: false });
            store.createIndex('userId', 'userId', { unique: false });
          }
        };
        
        request.onsuccess = (event) => {
          console.log('IndexedDB 打开成功');
          resolve(event.target.result);
        };
      });
    },
    // 存储文件到 IndexedDB
    async saveFileToCache(url, blob, userId, mode) {
      if (!this.useFileCache) return Promise.resolve();
      
      try {
        const db = await this.initDB();
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction(['files'], 'readwrite');
          const store = transaction.objectStore('files');

          const fileData = {
            url: url,
            blob: blob,
            // size: blob.size,
            size: 0,
            userId: userId,
            timestamp: Date.now()
          };
          if (mode === 'pdf') {
            fileData.size = blob.size; // PDF文件的大小
          }

          const request = store.put(fileData);

          request.onsuccess = () => {
            console.log('文件已缓存:', url);
            resolve();
          };

          request.onerror = (event) => {
            console.error('缓存文件失败:', event);
            reject(event);
          };
        });
      } catch (error) {
        console.error('保存文件到缓存时出错:', error);
      }
    },
    // 从 IndexedDB 获取文件
    async getFileFromCache(url, userId) {
      if (!this.useFileCache) return Promise.resolve(null);
      
      try {
        const db = await this.initDB();
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction(['files'], 'readonly');
          const store = transaction.objectStore('files');
          const request = store.get(url);

          request.onsuccess = (event) => {
            const fileData = event.target.result;
            if (fileData && fileData.userId === userId) {
              // 检查是否过期
              const now = Date.now();
              const age = now - fileData.timestamp;
              const maxAge = this.cacheExpiration * 24 * 60 * 60 * 1000; // 天数转毫秒
              // const maxAge = this.cacheExpiration * 10 * 1000; // 调试
              // const maxAge = 3 * 60 * 1000; // 3分钟转毫秒

              if (age > maxAge) {
                console.log('缓存已过期:', url);
                this.removeFileFromCache(url);
                resolve(null);
              } else {
                console.log('从浏览器缓存获取文件:', url);
                resolve(fileData.blob);
              }
            } else {
              resolve(null);
            }
          };

          request.onerror = (event_1) => {
            console.error('获取缓存文件失败:', event_1);
            reject(event_1);
          };
        });
      } catch (error) {
        console.error('从浏览器缓存获取文件时出错:', error);
        return null;
      }
    },
    // 从缓存中删除文件
    async removeFileFromCache(url) {
      if (!this.useFileCache) return Promise.resolve();
      
      try {
        const db = await this.initDB();
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction(['files'], 'readwrite');
          const store = transaction.objectStore('files');
          const request = store.delete(url);

          request.onsuccess = () => {
            console.log('已从缓存中删除文件:', url);
            resolve();
          };

          request.onerror = (event) => {
            console.error('删除缓存文件失败:', event);
            reject(event);
          };
        });
      } catch (error) {
        console.error('从缓存删除文件时出错:', error);
      }
    },
    // 清理过期缓存
    async cleanupExpiredCache() {
      if (!this.useFileCache) return Promise.resolve();
      
      try {
        const db = await this.initDB();
        return await new Promise((resolve, reject) => {
          const transaction = db.transaction(['files'], 'readwrite');
          const store = transaction.objectStore('files');
          const index = store.index('timestamp');

          const now = Date.now();
          const maxAge = this.cacheExpiration * 24 * 60 * 60 * 1000; // 天数转毫秒
          const range = IDBKeyRange.upperBound(now - maxAge);

          const request = index.openCursor(range);

          request.onsuccess = (event) => {
            const cursor = event.target.result;
            if (cursor) {
              store.delete(cursor.primaryKey);
              cursor.continue();
            } else {
              resolve();
            }
          };

          request.onerror = (event_1) => {
            console.error('清理过期缓存失败:', event_1);
            reject(event_1);
          };
        });
      } catch (error) {
        console.error('清理过期缓存时出错:', error);
      }
    },
    // 打开音频文件
    async openAudio(filename, userId) {
      this.isAudioFile = true;
      this.currentAudioFileName = filename;
      this.currentAudioUrl = '';
      this.audioReady = false;
      this.isAudioPlaying = false;
      this.audioCurrentTime = 0;
      this.audioDuration = 0;
      this.audioProgressPercent = 0;
      this.audioLoading = true;
      this.audioError = '';

      this.showPdfViewer = true;
      this.showTxtViewer = false;
      this.updateModule(1);

      const url = encodeURIComponent(filename) + "&userbook=" + encodeURIComponent(userId);

      if (url in this.bufferBlobUrls) {
        const cached = this.bufferBlobUrls[url];
        const blob = await this.normalizeAudioBlob(cached, filename);
        if (!(blob instanceof Blob)) {
          this.audioError = '音频缓存无效，正在重新下载';
          delete this.bufferBlobUrls[url];
        } else {
        this.audioError = '';
        this.currentAudioUrl = URL.createObjectURL(blob);
        this.bufferBlobUrls[url] = blob;
        this.audioLoading = false;
        return;
        }
      }

      try {
        const cachedBlob = await this.getFileFromCache(url, userId);
        if (cachedBlob) {
          const normalizedBlob = await this.normalizeAudioBlob(cachedBlob, filename);
          if (!(normalizedBlob instanceof Blob)) {
            throw new Error('缓存音频格式异常');
          }
          this.audioError = '';
          this.currentAudioUrl = URL.createObjectURL(normalizedBlob);
          this.bufferBlobUrls[url] = normalizedBlob;
          this.audioLoading = false;
          return;
        }
      } catch (error) {
        console.error('从本地缓存获取音频失败:', error);
      }

      try {
        const audioUrl = `${API_BASE_URL}/api/pdf/?url=${url}`;
        const response = await fetch(audioUrl, {
          headers: {
            Accept: 'audio/wav,audio/*,application/octet-stream;q=0.9,*/*;q=0.8'
          }
        });
        if (response.ok) {
          const rawBlob = await response.blob();
          const blob = await this.normalizeAudioBlob(rawBlob, filename);
          if (!(blob instanceof Blob)) {
            throw new Error('音频数据格式无法识别');
          }
          this.audioError = '';
          this.currentAudioUrl = URL.createObjectURL(blob);
          this.bufferBlobUrls[url] = blob;
          this.saveFileToCache(url, blob, userId, 'audio');
          this.audioLoading = false;
        } else {
          this.audioError = '音频文件加载失败';
          this.audioLoading = false;
        }
      } catch (error) {
        console.error('获取音频文件失败:', error);
        this.audioError = '音频文件加载失败: ' + error.message;
        this.audioLoading = false;
      }
    },
    // 音频播放控制方法
    toggleAudioPlay() {
      if (!this.audioReady || !this.$refs.audioPlayer) return;
      if (this.isAudioPlaying) {
        this.$refs.audioPlayer.pause();
        this.isAudioPlaying = false;
      } else {
        this.$refs.audioPlayer.play();
        this.isAudioPlaying = true;
      }
    },
    stopAudio() {
      if (!this.$refs.audioPlayer) return;
      this.$refs.audioPlayer.pause();
      this.$refs.audioPlayer.currentTime = 0;
      this.isAudioPlaying = false;
      this.audioCurrentTime = 0;
      this.audioProgressPercent = 0;
    },
    seekAudio(event) {
      if (!this.audioReady || !this.$refs.audioPlayer) return;
      const progressBar = event.currentTarget;
      const clickX = event.offsetX;
      const width = progressBar.offsetWidth;
      const percent = clickX / width;
      const newTime = percent * this.audioDuration;
      this.$refs.audioPlayer.currentTime = newTime;
      this.audioCurrentTime = newTime;
      this.audioProgressPercent = percent * 100;
    },
    onAudioLoaded() {
      if (!this.$refs.audioPlayer) return;
      this.audioDuration = this.$refs.audioPlayer.duration;
      this.audioReady = true;
      this.audioLoading = false;
      this.audioError = '';
    },
    onAudioTimeUpdate() {
      if (!this.$refs.audioPlayer) return;
      this.audioCurrentTime = this.$refs.audioPlayer.currentTime;
      if (this.audioDuration > 0) {
        this.audioProgressPercent = (this.audioCurrentTime / this.audioDuration) * 100;
      }
    },
    onAudioEnded() {
      this.isAudioPlaying = false;
      this.audioCurrentTime = 0;
      this.audioProgressPercent = 0;
    },
    onAudioError(event) {
      if (!this.audioReady) {
        this.audioError = '音频文件加载或播放失败';
        this.audioLoading = false;
        this.audioReady = false;
        console.error('音频加载错误:', event);
      }
    },
    formatAudioTime(seconds) {
      if (!seconds || isNaN(seconds)) return '00:00';
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    },
    looksLikeBase64Text(input) {
      if (!input || typeof input !== 'string') return false;
      const s = input.trim().replace(/\s+/g, '');
      if (s.length < 64 || (s.length % 4 !== 0)) return false;
      return /^[A-Za-z0-9+/=]+$/.test(s);
    },
    base64ToUint8Array(base64) {
      const cleaned = base64.replace(/\s+/g, '');
      const binaryString = atob(cleaned);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      return bytes;
    },
    async normalizeAudioBlob(inputBlob, filename = '') {
      if (!(inputBlob instanceof Blob)) return null;
      const arrayBuffer = await inputBlob.arrayBuffer();
      if (!arrayBuffer || arrayBuffer.byteLength < 8) return null;

      const bytes = new Uint8Array(arrayBuffer);
      const isRiffWav =
        bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
        bytes[8] === 0x57 && bytes[9] === 0x41 && bytes[10] === 0x56 && bytes[11] === 0x45;

      if (isRiffWav) {
        return new Blob([arrayBuffer], { type: 'audio/wav' });
      }

      // 兼容后端返回 base64 文本或 data URL 文本的情况
      const text = new TextDecoder('utf-8').decode(bytes).trim();
      if (text.startsWith('data:audio/')) {
        const commaIndex = text.indexOf(',');
        if (commaIndex > 0) {
          const meta = text.substring(0, commaIndex).toLowerCase();
          const payload = text.substring(commaIndex + 1);
          if (meta.includes(';base64')) {
            const decoded = this.base64ToUint8Array(payload);
            return new Blob([decoded.buffer], { type: 'audio/wav' });
          }
        }
      }

      if (this.looksLikeBase64Text(text)) {
        const decoded = this.base64ToUint8Array(text);
        if (decoded.length >= 12 &&
            decoded[0] === 0x52 && decoded[1] === 0x49 && decoded[2] === 0x46 && decoded[3] === 0x46 &&
            decoded[8] === 0x57 && decoded[9] === 0x41 && decoded[10] === 0x56 && decoded[11] === 0x45) {
          return new Blob([decoded.buffer], { type: 'audio/wav' });
        }
      }

      // 兜底：按扩展名强制指定MIME，避免浏览器错误推断编码
      const ext = (filename.split('.').pop() || '').toLowerCase();
      const fallbackType = ext === 'wav' ? 'audio/wav' : (inputBlob.type || 'audio/*');
      return new Blob([arrayBuffer], { type: fallbackType });
    },
    async openPDF(name) {
      this.isAudioFile = false;
      this.currentAudioUrl = '';
      this.currentAudioFileName = '';
      this.audioReady = false;
      this.isAudioPlaying = false;
      this.audioCurrentTime = 0;
      this.audioDuration = 0;
      this.audioProgressPercent = 0;
      this.audioLoading = false;
      this.audioError = '';

      // 清理之前的Blob URL
      // this.cleanupBlobUrl();
      // const apiBaseUrl = 'http://localhost:8000/api';
      // this.fileUrl = `${apiBaseUrl}/pdf/${encodeURIComponent(pdfFileName)}`;
      // 🔥 清空旧的URL，防止显示上一个文件的内容
      this.fileUrl = '';
      this.fileTransUrl = '';
      this.fresh = new Date().getTime();//时间戳

      var filePath = name
      var userId = localStorage.getItem('userId');
      
      // 🔥 设置curFileInfo.name，供后续使用
      this.curFileInfo.name = name;

      var url = `${API_BASE_URL}/api/pdf/?url=${encodeURIComponent(filePath)}&userbook=${encodeURIComponent(userId)}`;

      this.showPdfViewer = true;
      this.isLoading = true;
      this.loadingProgress = 0;
      this.loadingText = '正在获取PDF文件...';
      this.showTxtViewer = false;
      this._refreshHomeworkToolbarReady(name);

      // 🔥 中英文专业阅读场景或阅读场景的中英对比阅读子场景的特殊处理
      if((this.sceneName === "阅读" && this.subSceneName === "中英对比阅读") || this.sceneName.includes("中英文专业阅读")) {
        // 默认还是显示原文+译文PDF
        this.chooseEnOrEnZh = 'EnZh';
        
        // 🔥 无论是否有译文PDF，0.6s后都自动点击"原文"按钮，切换到只显示原文
        // 翻译只会在用户主动点击"中英对比"按钮时触发（在chooseEnZh函数中处理）
        setTimeout(() => {
          this.chooseEn();
        }, 600);
      }
      this.$message.success("正在获取文档，请稍等");
      if(url in this.bufferBlobUrls) {
        // 如果已经有这个URL的Blob URL，直接使用
        const cachedData = this.bufferBlobUrls[url];
        this.fileUrl = cachedData.blobUrl;
        this.totalBytes = cachedData.size;
        this.loadedBytes = this.totalBytes;
        console.log("从内存缓存获取 totalBytes", this.totalBytes, "loadedBytes", this.loadedBytes);
        this.loadingProgress = 90; // 已完成下载，预留10%给渲染
        setTimeout(() => {
          this.isLoading = false;
          console.log("isLoading", this.isLoading);
        }, 1000);
        // 等待iframe加载完成
        this.loadingText = '正在渲染PDF...';
        if(!((this.subSceneName === "中英对比阅读" && this.chooseEnOrEnZh === "EnZh") || (this.sceneName.includes("中英文专业阅读") && this.chooseEnOrEnZh === "EnZh"))) {
          this.$nextTick(() => {
            // 确保 DOM 已经更新
            document.getElementById("pdfFrame").style.width = '100%';
          });
        }
        return;
      }
      
      console.log("url", url);
      // 然后尝试从IndexedDB缓存中获取
      try {
        const cachedBlob = await this.getFileFromCache(url, userId);
        if (cachedBlob) {
          // 从缓存获取到了文件
          this.loadingText = 'PDF从本地缓存加载中...';
          this.loadingProgress = 70;
          
          // 创建Blob URL
          const blobUrl = URL.createObjectURL(cachedBlob);
          this.fileUrl = blobUrl;
          
          // 存储到内存缓存
          this.bufferBlobUrls[url] = {
            blobUrl: blobUrl,
            size: cachedBlob.size
          };
          
          this.totalBytes = cachedBlob.size;
          this.loadedBytes = this.totalBytes;
          this.loadingProgress = 90;
          
          setTimeout(() => {
            this.isLoading = false;
          }, 1000);
          
          this.loadingText = '正在渲染PDF...';
          
          if(!((this.subSceneName === "中英对比阅读" && this.chooseEnOrEnZh === "EnZh") || (this.sceneName.includes("中英文专业阅读") && this.chooseEnOrEnZh === "EnZh"))) {
            this.$nextTick(() => {
              document.getElementById("pdfFrame").style.width = '100%';
            });
          }
          return;
        }
      } catch (error) {
        console.error('从本地缓存获取文件失败:', error);
        // 失败时继续从服务器获取
      }
      
      // 如果没有缓存，从服务器下载
      this.bufferBlobUrls[url] = {}; // 先占位，防止重复下载
      try {
        // 使用XMLHttpRequest下载PDF并监控进度
        const blob = await this.downloadPdfWithProgress(url);
        
        // 创建Blob URL
        const blobUrl = URL.createObjectURL(blob);
        this.fileUrl = blobUrl;

        // 存储到内存缓存
        this.bufferBlobUrls[url] = {
          blobUrl: blobUrl,
          size: blob.size
        };
        // 存储到IndexedDB
        this.saveFileToCache(url, blob, userId, 'pdf');

        setTimeout(() => {
          this.isLoading = false;
          console.log("isLoading", this.isLoading);
        }, 1000);
        
        // 等待iframe加载完成
        this.loadingText = '正在渲染PDF...';
        if(!((this.sceneName === "阅读" && this.subSceneName === "中英对比阅读" && this.chooseEnOrEnZh === "EnZh") || (this.sceneName.includes("中英文专业阅读") && this.chooseEnOrEnZh === "EnZh"))) {
          this.$nextTick(() => {
            // 确保 DOM 已经更新
            document.getElementById("pdfFrame").style.width = '100%'
          });
        }
        console.log("loadingText", this.loadingText)
      } catch (error) {
        console.error('PDF加载失败:', error);
        this.loadingText = 'PDF加载失败';
        this.isLoading = false;
      }
    },
    // 清理Blob URL的方法
    cleanupBlobUrl() {
      if (this.fileUrl != '') {
        URL.revokeObjectURL(this.fileUrl);
        console.log('已释放' + this.fileUrl + '内存');
        this.fileUrl = '';
      }
    },
    // 在组件创建时，清理过期缓存
    cleanCacheOnMount() {
      this.cleanupExpiredCache();
    },
    downloadTransPdfWithProgress(url) {
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        
        xhr.open('GET', url, true);
        xhr.responseType = 'blob';
        
        // 监听下载进度
        xhr.onprogress = (event) => {
          if (event.lengthComputable) {
            if(url.endsWith("_result")) {
              this.totalTransBytes = event.total;
              this.loadedTransBytes = event.loaded;
              console.log("从事件获取 totalTransBytes", this.totalTransBytes, "loadedTransBytes", this.loadedTransBytes);
              this.loadingTransProgress = Math.round((event.loaded / event.total) * 90); // 预留10%给渲染
              this.loadingTransText = `正在下载PDF... ${this.loadingTransProgress}%`;
              console.log("loadingTransText", this.loadingTransText);
            } else {
              this.totalBytes = event.total;
              this.loadedBytes = event.loaded;
              console.log("从事件获取 totalBytes", this.totalBytes, "loadedBytes", this.loadedBytes);
              this.loadingProgress = Math.round((event.loaded / event.total) * 90); // 预留10%给渲染
              this.loadingText = `正在下载PDF... ${this.loadingProgress}%`;
              console.log("loadingText", this.loadingText);
            }
          } else {
            // 如果无法获取总大小，尝试从响应头获取
            const contentLength = xhr.getResponseHeader('Content-Length');
            if (contentLength) {
              if(url.endsWith("_result")) {
                // 显示从响应头获取的总字节数
                this.totalTransBytes = parseInt(contentLength);
                this.loadedTransBytes = event.loaded;
                console.log("从响应头获取 totalTransBytes", this.totalTransBytes, "loadedTransBytes", this.loadedTransBytes);
                this.loadingTransProgress = Math.round((event.loaded / this.totalTransBytes) * 90);
                this.loadingTransText = `正在下载PDF... ${this.loadingTransProgress}%`;
              } else {
                // 显示从响应头获取的总字节数
                this.totalBytes = parseInt(contentLength);
                this.loadedBytes = event.loaded;
                console.log("从响应头获取 totalBytes", this.totalBytes, "loadedBytes", this.loadedBytes);
                this.loadingProgress = Math.round((event.loaded / this.totalBytes) * 90);
                this.loadingText = `正在下载PDF... ${this.loadingProgress}%`;
              }
            } else {
              if(url.endsWith("_result")) {
                // 显示已下载的字节数
                this.loadedTransBytes = event.loaded;
                console.log("loadedTransBytes", this.loadedTransBytes);
                this.loadingTransText = `已下载 ${this.formatBytes(event.loaded)}...`;
              } else {
                // 显示已下载的字节数
                this.loadedBytes = event.loaded;
                console.log("loadedBytes", this.loadedBytes);
                this.loadingText = `已下载 ${this.formatBytes(event.loaded)}...`;
              }
            }
          }
        };
        
        xhr.onload = () => {
          if (xhr.status === 200) {
            this.loadingTransProgress = 90;
            this.loadingTransText = 'PDF下载完成，正在渲染...';
            resolve(xhr.response);
          } else {
            reject(new Error(`HTTP ${xhr.status}`));
          }
        };
        
        xhr.onerror = () => {
          reject(new Error('网络错误'));
        };
        
        xhr.send();
      });
    },
    downloadPdfWithProgress(url) {
      return new Promise(async (resolve, reject) => {
        try {
          // 🔥 使用fetch API进行流式下载，对大文件更友好
          const response = await fetch(url);
          
          if (!response.ok) {
            reject(new Error(`HTTP ${response.status}`));
            return;
          }
          
          // 获取文件大小
          const contentLength = response.headers.get('Content-Length');
          if (contentLength) {
            this.totalBytes = parseInt(contentLength);
          }
          
          // 使用ReadableStream进行流式读取
          const reader = response.body.getReader();
          const chunks = [];
          let receivedLength = 0;
          
          while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
              break;
            }
            
            chunks.push(value);
            receivedLength += value.length;
            this.loadedBytes = receivedLength;
            
            // 更新进度
            if (this.totalBytes) {
              this.loadingProgress = Math.round((receivedLength / this.totalBytes) * 90);
              this.loadingText = `正在下载PDF... ${this.loadingProgress}%`;
            } else {
              this.loadingText = `已下载 ${this.formatBytes(receivedLength)}...`;
            }
          }
          
          // 将所有chunks组合成Blob
          const blob = new Blob(chunks, { type: 'application/pdf' });
          
          this.loadingProgress = 90;
          this.loadingText = 'PDF下载完成，正在渲染...';
          resolve(blob);
        } catch (error) {
          console.error('[downloadPdfWithProgress] 下载失败:', error);
          reject(error);
        }
      });
    },
    onPdfLoaded() {
      // PDF iframe加载完成
      this.loadingProgress = 100;
      this.loadingText = 'PDF加载完成';
      
      setTimeout(() => {
        this.isLoading = false;
      }, 500);
    },
    formatBytes(bytes) {
      if (bytes === 0) return '0 Bytes';
      const k = 1024;
      const sizes = ['Bytes', 'KB', 'MB', 'GB'];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    },

    openTXT(name) {
      this.showPdfViewer = false;
      this.showTxtViewer = true;
      this.isAudioFile = false;
      this.currentAudioUrl = '';
      this.currentAudioFileName = '';
      this.audioReady = false;
      this.isAudioPlaying = false;
      this.audioCurrentTime = 0;
      this.audioDuration = 0;
      this.audioProgressPercent = 0;
      this.audioLoading = false;
      this.audioError = '';
    },
    waitFile(name, size) {
      this.needWaitFile++;
      this.waitFileNames.push(name)
      this.waitFileSizes.push(size)
    },
    isActive(index) {
      // 返回分支是否应该被激活
      return this.activeIndex === index;
    },
    refreshFileListAfterDel(){
      // this.currentModule = 1;
      // setTimeout(() => {
      //   this.currentModule = 0;
      // }, 50);
      this.$refs.FileList.getAllUserFiles();  // 重新获取文件列表
    },
    refreshFileList(filename) {
      // this.needWaitFile = false
      // this.currentModule = 1;
      // setTimeout(() => {
      //   this.currentModule = 0;
      // }, 50);

      if(this.needWaitFile > 0) {
        this.needWaitFile--;
        const index = this.waitFileNames.indexOf(filename);
        if (index > -1) {
          this.waitFileNames.splice(index, 1);
          this.waitFileSizes.splice(index, 1);
        }
      }
      this.$refs.FileList.getAllUserFiles(filename);  // 重新获取文件列表
      // this.currentModule = 1;
      // setTimeout(() => {
      //   this.currentModule = 0;
      // }, 50);

      // this.$nextTick(() => {
      //   // DOM 更新后的操作
      //   this.$refs.FileList.getAllUserFiles();  // 重新获取文件列表
      // });
    },
    userFeedBack() {
      this.dialogFeedBackVisible = true
    },
    closeDialog() {
      this.dialogFeedBackVisible = false;
    },
    submitFeedback() {
      console.log('提交的反馈评价为：', {
        creativitySatisfaction: this.creativitySatisfaction,
        repetitionSatisfaction: this.repetitionSatisfaction,
        comprehensivenessSatisfaction: this.comprehensivenessSatisfaction,
      });
      this.feedBack = true;
      // 之后在这里添加提交反馈的逻辑
      this.closeDialog();
    },
    handleFeedBackOK() {
      this.feedBack = false
    },
    handleHistoryUpdate(history, title) {
      this.$refs.ChatWindow.sendHistoryMsg(history, title);
      if (!this.chatBtnChecked) this.showChatWindow();

    },
    handleSeedModeSelected() {
      localStorage.setItem('seed', this.seedMode);
      this.$message.success(localStorage.getItem('seed'));
    },
    backtoDefault() {
      this.questionContents = ['正在获取相关问题...'];
      this.imgTopicContents = ['正在生成关键词...'];
      this.imgTopicQuestionContents = ['相关问题1', '相关问题2', '相关问题3'];
      this.topicRelQuestions = ['正在获取相关问题...'];
    },

    displaySummary() {
      if(this.LUI1_plus === true)
        this.LUI1_plus = false

      this.displaySummaryBtn = !this.displaySummaryBtn; // 切换isChecked的值
      var container = document.querySelector('.left-summary');
      var container_top = document.querySelector('.left-summary-top');
      var container_bottom = document.querySelector('.left-summary-bottom');
      var text_container = document.querySelector('.left-text');
      if (container.style.display === 'none' || container.style.display === '') {
        container.style.display = 'block';
        container_top.style.display = 'flex';
        container_bottom.style.display = 'flex';
        container.style.height = '50vh';
        text_container.style.height = '50vh';

        container.style.transition = '0.5s ease';
        text_container.style.transition = '0.5s ease';
      } else {
        container.style.height = '0vh';
        container.style.display = 'none';
        container_top.style.display = 'none';
        container_bottom.style.display = 'none';
        text_container.style.height = '80vh';

        container.style.transition = '0.5s ease';
        text_container.style.transition = '0.5s ease';
      }

      if(this.displaySummaryBtn === true) {
        this.curFileInfo.name = this.fileName;
        // this.getFileSummary();
        // this.getFileTopics();

        // 先获取深度建议，再生成summary和topics
        const audioExtensions = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm'];
        const currentFileName = (this.fileName || '').toLowerCase();
        const isAudioFile = audioExtensions.some(ext => currentFileName.endsWith(ext));

        // 音频文件：先执行多模态/音频预分析，再生成摘要与主题。
        // 其它文件：保持原有深度建议链路。
        const preparePromise = isAudioFile
          ? this.getAudioAnalysisForSummary()
          : this.getDepthSuggestionForSummary();

        preparePromise.then(() => {
          this.getFileSummary();
          this.getFileTopics();
        });
      } else {
        this.curFileInfo.content = "正在生成摘要中";
        this.topicContents = ['正在获取topics'];
        this.summaryStreamComplete = false;
      }
    },

    // 文档内容采样函数：获取开头150字、结尾150字、中间段落样本（每段前40字+后40字）
    sampleDocumentContent(content) {
      if (!content || content.length === 0) {
        return "文档内容为空";
      }
      
      const MAX_LENGTH = 3000;
      
      // 1. 开头150字
      const prefix = content.substring(0, 150);
      
      // 2. 结尾150字
      const suffix = content.length > 150 ? content.substring(content.length - 150) : "";
      
      // 3. 中间段落样本：每段取前40字和后40字
      const middleSamples = [];
      const lines = content.split('\n');
      
      // 跳过开头和结尾，处理中间段落
      const middleStart = Math.max(1, Math.floor(lines.length * 0.2));
      const middleEnd = Math.min(lines.length - 2, Math.ceil(lines.length * 0.8));
      
      for (let i = middleStart; i < middleEnd; i++) {
        const line = lines[i].trim();
        if (line.length > 0) {
          if (line.length <= 80) {
            middleSamples.push({ line, isPartial: false });
          } else {
            const startPart = line.substring(0, 40);
            const endPart = line.substring(line.length - 40);
            middleSamples.push({ line: startPart + endPart, isPartial: true });
          }
        }
      }
      
      // 4. 计算总长度
      let totalLength = prefix.length;
      if (suffix) totalLength += 3 + suffix.length; // +3 for "..." separator
      middleSamples.forEach(sample => {
        totalLength += 3 + sample.line.length; // +3 for "..." separator
      });
      
      // 5. 如果超过3000字，随机移除部分中间段落样本
      if (totalLength > MAX_LENGTH) {
        const excess = totalLength - MAX_LENGTH;
        const samplesToRemove = Math.ceil(excess / 83); // 每个样本平均83字（80字内容+3字分隔符）
        const removableSamples = middleSamples.filter(s => s.isPartial);
        
        if (removableSamples.length > 0) {
          // 随机选择要移除的样本
          const toRemove = Math.min(samplesToRemove, removableSamples.length);
          for (let i = 0; i < toRemove; i++) {
            const randomIndex = Math.floor(Math.random() * removableSamples.length);
            removableSamples.splice(randomIndex, 1);
          }
        }
      }
      
      // 6. 拼接结果
      let result = prefix;
      if (middleSamples.length > 0) {
        result += "...";
        middleSamples.forEach(sample => {
          result += sample.line + "...";
        });
      }
      if (suffix) {
        result += suffix;
      }
      
      // 7. 最终长度检查（如果仍超限，截断）
      if (result.length > MAX_LENGTH) {
        result = result.substring(0, MAX_LENGTH);
      }
      
      return result;
    },

    async getDepthSuggestionForSummary() {
      // 模拟进度条：3秒完成，每0.5秒更新一次
      const progressDuration = 3000; // 3秒
      const progressInterval = 500; // 每0.5秒更新一次
      let progress = 0;
      
      // // 构造输入文本（文档内容预览）
      // const inputText = `文档名称：${this.fileName}\n请为摘要和主题关键词生成提供深度建议`;
      
      this.curFileInfo.content = "正在获取深度建议...";
      
      // 更新进度提示
      const updateProgress = setInterval(() => {
        progress += (progressInterval / progressDuration) * 100;
        if (progress >= 100) progress = 100;
        this.curFileInfo.content = `正在获取深度建议... ${Math.round(progress)}%`;
      }, progressInterval);
      
      try {
        // 先获取文档内容
        const formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('filename', this.fileName);
        console.log(this.fileName)
        
        const docData = await get_file_text(formData);
        
        if (docData.error_num === 0 && docData.text) {
          // 采样文档内容
          const sampledContent = this.sampleDocumentContent(docData.text);
          
          const inputText = `文档名称：${this.fileName}\n\n文档内容：\n${sampledContent}\n\n请为摘要和主题关键词生成提供深度建议`;
          
          // 获取深度建议
          const suggestion = await getDepthSuggestion(inputText, localStorage.getItem('userId'), "summary");
          
          // 清除进度更新
          clearInterval(updateProgress);
          this.curFileInfo.content = "正在生成摘要中";
          
          // 将深度建议存储起来，后续使用
          this.depthSuggestionForSummary = suggestion;
          console.log('[深度建议] 获取成功:', suggestion);
          
          return suggestion;
        } else {
          throw new Error('无法获取文档内容');
        }
      } catch (error) {
        console.error('[深度建议] 获取失败:', error);
        clearInterval(updateProgress);
        this.curFileInfo.content = "正在生成摘要中";
        return '';
      }
    },

    async getAudioAnalysisForSummary() {
      const audioFileName = this.fileName;
      if (!audioFileName) {
        this.depthSuggestionForSummary = '';
        return '';
      }

      this.curFileInfo.content = "正在分析音频文件...";
      this.multimodalAnalysisResult = null;
      this.backtrackHistoryPrompt = null;

      try {
        await this.processAudioContextForMessage(audioFileName, '', { enableBacktrack: false });
        const analysisText = this.multimodalAnalysisResult || '';

        if (!analysisText) {
          this.depthSuggestionForSummary = '';
          return '';
        }

        this.depthSuggestionForSummary =
          `【多模态小模型分析结果】请在回答最前、在【章节摘要】之前，先写一段「多模态小模型分析结果」，` +
          `必须体现关键结论与关键数值（如预测、置信度、解释等）；随后再完成【章节摘要】与【整体摘要】。\n\n` +
          `--- 以下为音频预分析输出（请优先参考）---\n${analysisText}`;
        return this.depthSuggestionForSummary;
      } catch (error) {
        console.warn('[音频摘要预分析] 失败，回退到通用深度建议:', error);
        this.$message.warning('音频预分析失败，将按普通文档流程生成摘要');
        this.depthSuggestionForSummary = '';
        return this.getDepthSuggestionForSummary();
      } finally {
        this.curFileInfo.content = "正在生成摘要中";
      }
    },
    /**
     * 点击音频显示摘要时，只查找「同名 txt」和「长期记忆块 txt」。
     * 若当前文件不是短期块/音频（解析不出 longTermUserId），返回 null，使用完整 fileNameList。
     */
    getSummaryFileListForCurrentFile(filenameOverride) {
      const fn = filenameOverride != null ? filenameOverride : this.fileName;
      if (!fn || typeof fn !== 'string') return null;
      const longTermUserId = getLongTermUserIdFromAudioOrBlockName(fn);
      if (longTermUserId == null) return null;
      const baseName = fn.replace(/\.[^/.]+$/, '').trim();
      const sameNameTxt = baseName + '.txt';
      const longTermTxt = longTermUserId + '_LONG.txt';
      if (longTermTxt === sameNameTxt) return { fileList: [sameNameTxt], filenameForMain: sameNameTxt };
      return { fileList: [longTermTxt, sameNameTxt], filenameForMain: sameNameTxt };
    },

    getFileSummary() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      // formData.append('model_id', this.curModelInfo.id);
      formData.append('model_id', '1126');  // 对应claude-4-sonnet

      // 体联音频/短期块：收窄为 LONG + 同名 txt；常规 pdf/txt 等与改前完全一致
      const summaryPayload = this.getSummaryFileListForCurrentFile();
      if (summaryPayload) {
        const fileList = summaryPayload.fileList;
        formData.append('filename', summaryPayload.filenameForMain);
        formData.append('fileNameList', JSON.stringify(fileList));
        formData.append('leftSelectList', fileList.map(() => '0').join(','));
        formData.append('rightSelectList', fileList.map(() => '0').join(','));
      } else {
        formData.append('filename', this.fileName);
        // formData.append('fileNameList', this.fileNameList);
        // 【修改这里】使用 JSON.stringify 包裹
        formData.append('fileNameList', JSON.stringify(this.fileNameList));
        formData.append('leftSelectList', this.leftSelectList);
        formData.append('rightSelectList', this.rightSelectList);
      }
      if (this.sceneName) {
        formData.append('sceneName', this.sceneName);
      }

      // 传递深度建议（如果存在）
      if (this.depthSuggestionForSummary) {
        formData.append('depth_suggestion', this.depthSuggestionForSummary);
      }
      get_file_summary(formData).then(response => {
          this.summaryStreamComplete = false; // 新一轮流式摘要开始
          const reader = response.body.getReader(); // 使用响应的ReadableStream来处理数据
          // 后端传回数据，显示
          const processStream = () => {
            const decoder = new TextDecoder('utf-8');
            reader.read().then(({done, value}) => {
              if (done) {
                console.log('Stream reading complete');
                this.summaryStreamComplete = true; // 流式摘要完成，显示“正在等待配图生成中...”提醒

                // 保存“Summary & Topics”到 audio_block_summary，用于后续回溯提示拼接
                // 触发时机：用户点击文档生成摘要（get_file_summary 流式完成）时。
                try {
                  if (summaryPayload && typeof summaryPayload.filenameForMain === 'string'
                      && summaryPayload.filenameForMain.endsWith('.txt')) {
                    const targetBlockId = summaryPayload.filenameForMain.replace(/\.txt$/, '');
                    const summaryText = this.curFileInfo?.content;
                    const uid = localStorage.getItem('userId');
                    if (uid && targetBlockId && typeof summaryText === 'string' && summaryText.trim()) {
                      saveAudioBlockSummary(targetBlockId, summaryText, uid)
                        .catch(err => console.warn('[保存 Summary&Topics]', err));
                    }
                  }
                } catch (e) {
                  console.warn('[保存 Summary&Topics] 失败', e);
                }

                this.context.stream.push({
                  time: Date.now(),
                  action: "进行了LUI1文档主题裂解",
                  Specifics: { 
                    "human1": "请总结文档：\n" + JSON.stringify(this.numberArray), 
                    "AI1": "摘要:\n" + this.curFileInfo.content
                  },
                  comments: "请给些点评吧"
                });
                // this.updateModule(1); // 切换到文件视图 
                if(this.isPlus === true) {
                  this.LUI1_plus = true
                }
                return;
              }
              const resp = decoder.decode(value);
              // console.log('Processed chunk:', resp);
              let responseData;
              // 使用正则表达式匹配和提取每个独立的 JSON 对象
              const jsonObjects = resp.match(/{[\s\S]*?}(?=\s*{|$)/g);
              if (jsonObjects) {
                jsonObjects.forEach(jsonObject => {
                  responseData = JSON.parse(jsonObject);
                  // 处理解析后的 JSON 数据
                  // if(this.chatModelInfo.name == response["model"]) {
                  if(this.curFileInfo.content == '正在生成摘要中') {
                    this.curFileInfo.content = '';
                  }
                  this.curFileInfo.content += responseData["content"];
                  this.shouldScroll = true;
                  // this.shouldScroll = true;
                  setTimeout(() => {
                    const scrollDom = this.$refs.summaryContent;
                    this.scrollBottom(scrollDom);
                  }, 100); // 延迟100毫秒
                });
              } else {
                console.error('No JSON objects found in the stream:', resp);
                this.$message.error('出错，可尝试降低最大词数后重试，若再次出错，请联系管理员并暂勿使用此功能');
              }
              // 继续读取下一块数据
              processStream();
            })
          };
          processStream();
          // if (data['error_num'] === 0) {
          //   this.curFileInfo.name = this.fileName;
          //   // 这个content是摘要，不是文本
          //   this.curFileInfo.content = data['content'];
          // } else {
          //   this.$message.error('出错，可尝试降低最大词数后重试，若再次出错，请联系管理员并暂勿使用此功能');
          // }
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
    },
    //获取窗口高度并滚动至最底层
    scrollBottom(scrollDom) {
      if (this.shouldScroll) {
        // const scrollDom = this.$refs.summaryContent;
        animation(scrollDom, scrollDom.scrollHeight - scrollDom.offsetHeight);
        this.shouldScroll = false; // 重置标志位
      }
    },
    getFileTopics() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));

      // 体联音频/短期块：收窄为 LONG + 同名 txt；常规 pdf/txt 等与改前完全一致
      const summaryPayload = this.getSummaryFileListForCurrentFile();
      if (summaryPayload) {
        const fileList = summaryPayload.fileList;
        formData.append('filename', summaryPayload.filenameForMain);
        formData.append('fileNameList', JSON.stringify(fileList));
        console.log('[getFileTopics]', fileList);
        formData.append('leftSelectList', fileList.map(() => '0').join(','));
        formData.append('rightSelectList', fileList.map(() => '0').join(','));
      } else {
        formData.append('filename', this.fileName);
        // formData.append('fileNameList', this.fileNameList);
        // 【修改这里】使用 JSON.stringify 包裹
        formData.append('fileNameList', JSON.stringify(this.fileNameList));
        console.log('[getFileTopics]', this.fileNameList);
        formData.append('leftSelectList', this.leftSelectList);
        formData.append('rightSelectList', this.rightSelectList);
      }

      // 传递深度建议（如果存在）
      if (this.depthSuggestionForSummary) {
        formData.append('depth_suggestion', this.depthSuggestionForSummary);
      }
      // 继续获取summary和topic
      get_file_topics(formData).then(data => {
        if (data['error_num'] === 0) {
          this.topicContents = data['topic'];
          this.context.stream.push({
            time: Date.now(),
            action: "进行了LUI1文档主题裂解",
            Specifics: { 
              "human1": "请总结文档：\n" + JSON.stringify(this.numberArray), 
              "AI1": "topics:\n" + data['topic']
            },
            comments: "请给些点评吧"
          });
          // this.updateModule(1); // 切换到文件视图 
          if(this.isPlus === true) {
            this.LUI1_plus = true
          }
        } else {
          this.$message.error('出错，可尝试降低最大词数后重试，若再次出错，请联系管理员并暂勿使用此功能');
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    pinSummaryToCard() {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限添加卡片');
      //   return;
      // }
      if (!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限添加卡片');
        return;
      }
      
      if (!this.curFileInfo.content || this.curFileInfo.content.trim() === '' || this.curFileInfo.content === "正在生成摘要中") {
        this.$message.warning('摘要内容为空或正在生成中，无法创建卡片');
        return;
      }

      this.$message.success('正在将摘要内容创建为卡片，请稍等...');

      // 半自动化新增：记录获取文档摘要操作
      this.recordOperation('get_file_summary', {
        // filename: filename,
        filename: this.curFileInfo.name,
        fileNameList: this.fileNameList,
        leftSelectList: this.leftSelectList,
        rightSelectList: this.rightSelectList,

        otherFiles: this.fileNameList.filter(f => f !== this.curFileInfo.name),
        sceneName: this.sceneName,
        subSceneName: this.subSceneName,
        keyTopics: this.keyTopics,
      });
      
      const rawSummary = this.curFileInfo.content || '';
      const summaryContent = rawSummary.trim().startsWith('【综合摘要】')
        ? rawSummary
        : `【文件摘要】${this.curFileInfo.name}\n\n${rawSummary}`;
      
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('originRealName', localStorage.getItem('originRealName')); // 添加作者信息
      formData.append('content', summaryContent);
      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', this.subSceneName);
      formData.append('keyTopics', JSON.stringify(this.keyTopics));

      // 🔥 先滚动到顶部，再显示等待卡片
      if (this.$refs.CardGrid) {
        this.$refs.CardGrid.scrollToTop();
      }
      this.cardMaking = true;
      
      addCardDirect(formData).then(data => {
        if(data.data['error_num'] === 0) {
          let cid = data.data['cardId'];
          // 🔥 设置新生成的卡片ID，用于等待卡消失后滚动到新卡片
          if (this.$refs.CardGrid) {
            this.$refs.CardGrid.setLastCreatedCardId(cid);
          }
          this.cardMaking = false;
          this.cardUpdate = true;
          // this.waitDecodedResult(cid, summaryContent);
          this.$refs.ChatWindow.getModelEval(summaryContent, cid);
          this.$refs.ChatWindow.getOurModelEval(summaryContent, cid, -1);
          this.refreshCardWhenKeywordsReady(cid);
          this.$message.success('摘要卡片创建成功！');
          // 摘要默认带图：钉卡成功后自动加入单卡生图队列，配图将保存到钉出的卡片中
          const username = localStorage.getItem('userId');
          if (username) {
            card_generate_single_card_image({ username, cid }).then(res => {
              const d = res.data || res;
              if (d.error_num === 0 && (d.generating_cids || []).includes(cid) && this.$refs.CardGrid) {
                this.$refs.CardGrid.onSingleCardImageRequested(cid);
              }
            }).catch(() => {});
          }
        } else {
          this.cardMaking = false;
          this.cardUpdate = true;
          this.$message.error('摘要卡片创建失败，请重试');
        }
      }).catch(error => {
        this.cardMaking = false;
        this.cardUpdate = true;
        this.$message.error('摘要卡片创建失败，请重试');
        console.error('Error creating summary card:', error);
      });
    },

    run_LUI1_plus() {
      this.dialogPlusLUI1 = true

      let formData = new FormData();
      let formLui1 = JSON.stringify(this.formLui1);
      formData.append('formLui1', formLui1);
      formData.append('sumContent', this.curFileInfo.content);
      formData.append('username', localStorage.getItem('userId'));
      agent_LUI1(formData).then(data => {
        if(data['error_num'] === 0) {
          this.loop_history = data['loop_history']
          this.scoreBefore = data['score']
          this.colorBefore = data['color']
          this.scoreEnd = data['scoreEnd']
          this.colorEnd = data['colorEnd']
          this.displayScore = true
        } else {
          this.dialogPlusLUI1 = false
          this.$message.error('出错了，请重试，若再次出错，请联系管理员并暂勿使用此功能');
        }
      })
    },
    LUI2_A_dia() {
      this.dialogPlusLUI2 = true
    },
    LUI2_A_err() {
      this.dialogPlusLUI2 = false
    },
    LUI2_agent(all_history, score, color, scoreEnd, colorEnd, msgPlus) {
      this.all_history = all_history
      this.scoreBeforeLUI2 = score
      this.colorBeforeLUI2 = color
      this.scoreEndLUI2 = scoreEnd
      this.colorEndLUI2 = colorEnd
      this.displayScoreLUI2 = true
      this.msgPlus = msgPlus
    },
    handleParamsUpdate() {
      this.dialogVisible = true;
    },
    fileSummaryClose() {
      this.flexBtnChecked = false
      // this.chooseEnOrEnZh = 'EnZh'  // 这两个是中英阅读场景新点开每个文件卡片前的初始化
      // this.chooseEnOrEnZh = ''
      this.closeChangeLeftPdfView()
      this.updateModule(0);
      // 记得把内容都清空
      if(this.displaySummaryBtn === true)
        this.displaySummaryBtn = false
      this.LUI1_plus = false
      this.curFileInfo.content = "正在生成摘要中";
      this.curFileInfo.text = "正在获取正文内容";
      this.topicContents = ['正在获取topic'];
      this.summaryStreamComplete = false;

      // 清理之前文件的图片处理状态和图片内容
      // this.stopImageProcessingCheck();
      this.cleanupPreviousFileState();
    },
    handleMouseDown(event) {
      // 如果遮罩层显示，则阻止事件冒泡到对话框，防止关闭对话框
      if (this.showMask) {
        // event.stopPropagation();
      }
    },
    handleCardOpeUpd(score, qaTotalStr) {
      this.context.stream.push({
        time: Date.now(),
        action: "将chat channel的一轮问答钉成了卡片",
        Specifics: { 
          "human1": "请为本轮问答内容打分: \n" + qaTotalStr, 
          "AI1": "GPT4o给出了红蓝卡标，评分为" + score.toString() + "分"
        },
        comments: "请给些点评吧"
      });
      // this.cardUpdate = true;
      this.cardMaking = false;
    },
    handleCardUpdate(cardId) {
      // 🔥 如果有新生成的卡片ID，设置给CardGrid用于等待卡消失后滚动
      if (cardId && this.$refs.CardGrid) {
        this.$refs.CardGrid.setLastCreatedCardId(cardId);
      }
      this.cardUpdate = true;
      this.cardMaking = false;
      this.cardSingleMaking = false;
      if (cardId) {
        this.refreshCardWhenKeywordsReady(cardId);
      }
    },
    /** 建卡后语义关键词后台补全完成时再刷一次卡片列表 */
    refreshCardWhenKeywordsReady(cid) {
      if (!cid) return;
      let tries = 0;
      const maxTries = 60;
      const tick = () => {
        tries += 1;
        if (tries > maxTries) return;
        const formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', cid);
        get_card(formData).then(data => {
          const kw = ((data && data.content && data.content.keyWords) || '').trim();
          if (kw && kw !== '（理解生成中）') {
            this.cardUpdate = false;
            this.$nextTick(() => {
              this.cardUpdate = true;
            });
          } else {
            setTimeout(tick, 3500);
          }
        }).catch(() => {
          setTimeout(tick, 3500);
        });
      };
      setTimeout(tick, 2500);
    },
    handleCardUpdateStream(result, cardId) {
      const newMap = new Map(this.HLContent);
      newMap.set(cardId, result);
      this.HLContent = newMap; // 替换整个引用
      this.cardUpdateStream = true;
      this.cardMaking = false;
      this.cardSingleMaking = false;
    },
    handleCardUpdateStreamOver() {
      this.cardUpdateStream = false;
    },
    handleCardOpeUpdStream(result, cardId) {
      const newMap = new Map(this.HLOpeContent);
      newMap.set(cardId, result);
      this.HLOpeContent = newMap; // 替换整个引用
      this.cardOpeUpdStream = true;
      this.cardMaking = false;
      this.cardSingleMaking = false;
    },
    handleCardOpeUpdStreamOver() {
      this.cardOpeUpdStream = false;
      // 浅评流式完成后，触发卡片更新以刷新显示的分数
      // (之前钉卡片浅评都先于深评完成，深评完成后更新卡片可以将深浅评两个打分结果都更新到卡片上显示；而现在小模型深评明显变快，
      // 导致深评先完成，从而显示出来是分子有分数分母-2分，应该先转圈，等浅评后完成后刷新卡片更新)
      this.cardUpdate = true;
    },
    handleCardUpdateOver() {
      this.cardUpdate = false;
    },

    // 🔥 问答钉卡时，立即滚动到CardGrid顶部
    handleScrollToCardGridTop() {
      // 🔥 立即同步滚动，确保在等待卡片显示前就滚动到顶部
      if (this.$refs.CardGrid) {
        this.$refs.CardGrid.scrollToTop();
      }
    },
    // 🔥 合并回原卡完成时，清除cardSingleMaking状态
    handleClearCardSingleMaking() {
      this.cardSingleMaking = false;
    },

    handleShowParam(paramsIndex) {
      if (paramsIndex === 1) {
        // this.show1()
      }
      if (paramsIndex === 2) {
        // this.show2()
      }
    },
    handleHandChangeParams() {
      this.dialogVisibleInner = true
    },
    // // 初始化雷达图的方法
    // initRadarChart() {
    //   this.$nextTick(() => {
    //   });
    // },
    handleUpdate(newVal) {
      // 此函数有三种触发情况：点 3 个更改参数按钮、手动拖拽更改参数、点选思维模式
      // 前两种情况只改变一个模型超参，第三种会全部改变，所以此处的函数不能再用了，三种情况都全部修改，以兼容
      // Object.keys(newVal[this.configModel]).forEach(key => {
      //   this.params[this.configModel][key] = newVal[this.configModel][key];
      // });
      Object.keys(newVal.GPT4).forEach(key => {
        this.params.GPT4[key] = newVal.GPT4[key];
      });
      Object.keys(newVal.Mixtral).forEach(key => {
        this.params.Mixtral[key] = newVal.Mixtral[key];
      });
      Object.keys(newVal.Kimi).forEach(key => {
        this.params.Kimi[key] = newVal.Kimi[key];
      });
      Object.keys(newVal.llama3).forEach(key => {
        this.params.llama3[key] = newVal.llama3[key];
      });
      Object.keys(newVal.Claude).forEach(key => {
        this.params.Claude[key] = newVal.Claude[key];
      });
      Object.keys(newVal.Deepseek).forEach(key => {
        this.params.Deepseek[key] = newVal.Deepseek[key];
      });
      console.log("主页面参数最终真正更新完成：", this.params);
    },
    handleClick(type) {
      if (type === '陈述型') {
        if (this.dialogVisible === false)
          this.dialogVisible = true;
        this.clickClass = '陈述型';
        this.paramsClass = '陈述型';
        // this.$message.success('当前模式：简短聊天，有助于事实调查');
      } if (type === '平衡型') {
        if (this.dialogVisible === false)
          this.dialogVisible = true;
        this.clickClass = '平衡型';
        this.paramsClass = '平衡型';
        // this.$message.success('当前模式：均衡问答，用于日常的有料对话');
      } if (type === '创造型') {
        // this.params[this.configModel].value1 = 1.8;
        if (this.dialogVisible === false)
          this.dialogVisible = true;
        this.clickClass = '创造型';
        this.paramsClass = '创造型';
        // this.$message.success('当前模式：创造想象，开始原创和富有想象力的对话');
      }
    },
    handleParamsModelClick(type) {
      // if (type === 'GPT4') {
      //   this.$message.success('GPT-4，如下可调超参');
      //   this.configModel = 'GPT4';
      //   // this.handleSelectModelUpdate(getModel()[0]);
      // } if (type === 'Mixtral') {
      //   this.$message.success('Mixtral，如下可调超参');
      //   this.configModel = 'Mixtral';
      //   // this.handleSelectModelUpdate(getModel()[1]);
      // } if (type === 'Kimi') {
      //   this.$message.success('Kimi，如下可调超参');
      //   this.configModel = 'Kimi';
      //   // this.handleSelectModelUpdate(getModel()[2]);
      // } if (type === 'llama3') {
      //   this.$message.success('llama3，如下可调超参');
      //   this.configModel = 'llama3';
      //   // this.handleSelectModelUpdate(getModel()[3]);
      // } if (type === 'Claude') {
      //   this.$message.success('Claude，如下可调超参');
      //   this.configModel = 'Claude';
      //   // this.handleSelectModelUpdate(getModel()[3]);
      // } if (type === 'Deepseek') {
      //   this.$message.success('Deepseek，如下可调超参');
      //   this.configModel = 'Deepseek';
      //   // this.handleSelectModelUpdate(getModel()[3]);
      // }
        const matchedModel = this.modelList.find(model => model.name === type);
        if (matchedModel) {
          this.$message.success(`${matchedModel.name}，如下可调超参`);
          this.configModel = matchedModel.name;
        }
    },
    handleSelectBgcUpdate(bgcInfo) {
      console.log(bgcInfo);
      this.currentBgc = bgcInfo;
      this.showBgcChecked = false;
    },
    handleUpdateBgcList() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('realName', localStorage.getItem('realName'));
      formData.append('sceneName', localStorage.getItem('sceneName'))
      get_bgc_card(formData).then(response => {
        this.bgcList = response.content;
        this.bgcList.push({
          cid: 0,
          name: '默认背景摘要',
          detail: '此时大模型不具备任何背景知识',
          content: '',
          datetime: '',
          status: 0,
        });
        const matchedCard = this.bgcList.find(bgc => bgc.name.includes("全部笔记本"));
        if (matchedCard) {
          console.log(matchedCard);
          this.currentBgc = matchedCard;
          this.$message.success('默认用户个人摘要');
        } else {
          this.$message.success('暂无用户个人摘要');
        }
      }).catch(e => {
        this.$message.error(e);
      });
    },

    idToIndex(id) {
      // 根据切换的模型更改超参表盘
      // 生成 { id: sequence } 的映射表
      const idToSequence = this.modelList.reduce((map, model) => {
        map[model.id] = model.sequence;
        return map;
      }, {});

      console.log("id转为sequence，id = ", id)
      console.log("id转为sequence，sequence = ", idToSequence[id])

      return idToSequence[id] ?? 0; // 默认返回 0
      // 此处index是模型切换dialog里显示的顺序
      // let index = 0
      // // 根据切换的模型更改超参表盘
      // if (id === "1002") {
      //   // "1002" 对应 'GPT4'
      //   index = 0
      // } if (id === "1003") {
      //   // "1003" 对应 'Mixtral'
      //   index = 6
      // } if (id === "1004") {
      //   // "1004" 对应 'Kimi'
      //   index = 5
      // } if (id === "1005") {
      //   // "1005" 对应 'llama3'
      //   index = 4
      // } if (id === "1006") {
      //   // "1006" 对应 'Claude3.5'
      //   index = 1
      // } if (id === "1007") {
      //   // "1007" 对应 'Deepseek-v3'
      //   index = 2
      // } if (id === "1008") {
      //   // "1008" 对应 'Deepseek-r1'
      //   index = 3
      // } if (id === "1009") {
      //   // "1009" 对应 'Gemini'
      //   index = 7
      // } if (id === "1010") {
      //   // "1010" 对应 'Qwq'
      //   index = 8
      // }
      // return index
    },
    littleidToIndex(id) {
      // 此处index是模型切换dialog里显示的顺序
      // 显示顺序：3003(索引0) → 3002(索引1) → 3001(索引2) → 3004(索引3) → 3005(索引4) → 3006(索引5) → 3007(索引6)
      let index = 0
      // 根据切换的模型更改超参表盘
      if (id === "3003") {
        index = 0
      } if (id === "3002") {
        index = 1
      } if (id === "3001") {
        index = 2
      } if (id === "3004") {
        index = 3
      } if (id === "3005") {
        index = 4
      } if (id === "3006") {
        index = 5
      } if (id === "3007") {
        index = 6
      }
      return index
    },
    multimodalLittleIdToIndex(id) {
      let index = 0
      if (id === "4002") index = 0
      if (id === "4001") index = 1
      return index
    },
    handlePortraitStatesUpdate() {
      let index = 0
      if (this.toBeSwitched == 0) {
        this.closeMain = true
        index = this.idToIndex(this.curModelInfo.id)
      } else if (this.toBeSwitched == 1) {
        this.closeUp = true
        index = this.idToIndex(this.curModelInfoUp.id)
      } else {
        this.closeDown = true
        index = this.idToIndex(this.curModelInfoDown.id)
      }
      this.portraitStates[index] = false

      // 关闭dialog
      this.showModelChecked = false;
    },
    handleSelectModelUpdate(curModelInfo) {

      // 先获取模型的id，再进行对比
      const curModelId = curModelInfo.id;
      const mainModelId = this.curModelInfo.id;
      const upModelId = this.curModelInfoUp.id;
      const downModelId = this.curModelInfoDown.id;

      if(curModelId != mainModelId && curModelId != upModelId && curModelId != downModelId) {
      //if(curModelInfo !== this.curModelInfo && curModelInfo !== this.curModelInfoUp && curModelInfo !== this.curModelInfoDown) {
        let indexOld = 0
        let indexNew = 0
        // 新加，多模型
        if (this.toBeSwitched == 0) {
          indexOld = this.idToIndex(this.curModelInfo.id)
          this.curModelInfo = curModelInfo;
          this.closeMain = false
        }
        else if (this.toBeSwitched == 1) {
          indexOld = this.idToIndex(this.curModelInfoUp.id)
          this.curModelInfoUp = curModelInfo;
          this.closeUp = false
        }
        else {
          indexOld = this.idToIndex(this.curModelInfoDown.id)
          this.curModelInfoDown = curModelInfo;
          this.closeDown = false
        }
        indexNew = this.idToIndex(curModelInfo.id)
        
        this.portraitStates[indexOld] = false
        this.portraitStates[indexNew] = true
      } else {
        let indexOld = 0
        let indexNew = 0
        if (this.toBeSwitched == 0) {
          indexOld = this.idToIndex(this.curModelInfo.id)
        } else if (this.toBeSwitched == 1) {
          indexOld = this.idToIndex(this.curModelInfoUp.id)
        } else {
          indexOld = this.idToIndex(this.curModelInfoDown.id)
        }
        indexNew = this.idToIndex(curModelInfo.id)

        if(indexOld === indexNew) {
          this.portraitStates[indexNew] = true
        } else {
          if((this.toBeSwitched === 0 && this.closeMain === true) || (this.toBeSwitched === 1 && this.closeUp === true) || (this.toBeSwitched === 2 && this.closeDown === true)) {
            this.portraitStates[indexOld] = true
            this.portraitStates[indexNew] = true
          } else {
            let old = this.portraitStates[indexOld]
            this.portraitStates[indexOld] = this.portraitStates[indexNew]
            this.portraitStates[indexNew] = old
          }
        }

        let repeatWhich = "main"
        // if (curModelInfo === this.curModelInfoUp)
        if (curModelId === this.curModelInfoUp.id)
          repeatWhich = "up"
        // if (curModelInfo === this.curModelInfoDown)
        if (curModelId === this.curModelInfoDown.id)
          repeatWhich = "down"

        let replaced = this.curModelInfo
        if (this.toBeSwitched == 0) {
          this.curModelInfo = curModelInfo;
          if(this.closeMain === true) {
            this.closeMain = false
            this.$refs.ChatWindow.clearChatList()
          }
          if(this.closeUp === true && repeatWhich === "up")
            this.$refs.ChatWindowUp.clearChatList()
          if(this.closeDown === true && repeatWhich === "down")
            this.$refs.ChatWindowDown.clearChatList()
        }
        else if (this.toBeSwitched == 1) {
          replaced = this.curModelInfoUp
          this.curModelInfoUp = curModelInfo;
          if(this.closeUp === true) {
            this.closeUp = false
            this.$refs.ChatWindowUp.clearChatList()
          }
          if(this.closeMain === true && repeatWhich === "main")
            this.$refs.ChatWindow.clearChatList()
          if(this.closeDown === true && repeatWhich === "down")
            this.$refs.ChatWindowDown.clearChatList()
        }
        else {
          replaced = this.curModelInfoDown
          this.curModelInfoDown = curModelInfo;
          if(this.closeDown === true) {
            this.closeDown = false
            this.$refs.ChatWindowDown.clearChatList()
          }
          if(this.closeMain === true && repeatWhich === "main")
            this.$refs.ChatWindow.clearChatList()
          if(this.closeUp === true && repeatWhich === "up")
            this.$refs.ChatWindowUp.clearChatList()
        }

        if (repeatWhich === "main") {
          this.curModelInfo = replaced
        } else if (repeatWhich === "up") {
          this.curModelInfoUp = replaced
        } else {
          this.curModelInfoDown = replaced
        }
      }
      const idToModelName = this.modelList.reduce((map, model) => {
        map[model.id] = model.name;
        return map;
      }, {});
      console.log("id转为model_name，id = ", curModelInfo.id)
      console.log("id转为model_name，model_name = ", idToModelName[curModelInfo.id])
      this.activeModel = idToModelName[curModelInfo.id] ?? 'GPT4'; // 默认值为 'GPT4'

      // 根据切换的模型更改超参表盘
      // if (curModelInfo.id === "1002") {
      //   this.activeModel = 'GPT4';   // "1002" 对应 'GPT4'
      // } if (curModelInfo.id === "1003") {
      //   this.activeModel = 'Mixtral';   // "1003" 对应 'Mixtral'
      // } if (curModelInfo.id === "1004") {
      //   this.activeModel = 'Kimi';   // "1004" 对应 'Kimi'
      // } if (curModelInfo.id === "1005") {
      //   this.activeModel = 'llama3';   // "1005" 对应 'llama3'
      // } if (curModelInfo.id === "1006") {
      //   this.activeModel = 'Claude';   // "1006" 对应 'Claude3.5'
      // } if (curModelInfo.id === "1007") {
      //   this.activeModel = 'Deepseek';   // "1007" 对应 'Deepseek-v3'
      // } if (curModelInfo.id === "1008") {
      //   this.activeModel = 'Deepseek';   // "1008" 对应 'Deepseek-r1'
      // } if (curModelInfo.id === "1009") {
      //   this.activeModel = 'Gemini';   // "1009" 对应 'Gemini'
      // } if (curModelInfo.id === "1010") {
      //   this.activeModel = 'Qwq';   // "1010" 对应 'Qwq'
      // }

      // 切换模型：1002、1003、1004、1005、1006、1007、1008、1009、1010
      let formData = new FormData();
      formData.append('model_id', this.curModelInfo.id);
      formData.append('username', localStorage.getItem('userId'));
      chat_switch(formData).then(data => {
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
      console.log("真正完成切换")

      this.showModelChecked = false;
    },
    handleSelectLittleModelUpdate(curModelInfo) {
      // 特殊处理：3006 (llama3.3 70B) 暂时没有实际功能
      // if(curModelInfo.id === "3006") {
      //   this.$message.warning('Llama3.3 70B模型正在开发中，暂不可用');
      //   return;
      // }

      if(curModelInfo !== this.curLittleInfo) {
        let indexOld = this.littleidToIndex(this.curLittleInfo.id)
        this.curLittleInfo = curModelInfo
        let indexNew = this.littleidToIndex(curModelInfo.id)
        
        // this.littlePortraitStates[indexOld] = false
        // this.littlePortraitStates[indexNew] = true
        // 使用Vue.set确保响应式更新，或者重新赋值整个对象
        this.littlePortraitStates = {
          ...this.littlePortraitStates,
          [indexOld]: false,
          [indexNew]: true
        }
      } 

      // 更新localStorage
      localStorage.setItem('currentLittleModelId', this.curLittleInfo.id);

      // 切换模型：3001,3002,3003,3004,3005,3006,3007
      let formData = new FormData();
      formData.append('model_id', this.curLittleInfo.id);
      formData.append('username', localStorage.getItem('userId'));
      chat_switch(formData).then(data => {
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
      // const response = await fetch('http://192.0.2.1:8000/model_switch', {
      //   method: 'POST',
      //   headers: {
      //     'Content-Type': 'application/json; charset=utf-8',
      //   },
      //   body: JSON.stringify({
      //     username: localStorage.getItem('userId'),
      //     model_id: this.curLittleInfo.id,
      //   }),
      // });

      // if (response.ok) {
      //   const data = await response.json(); // 解析 JSON 响应体
      //   const resultObject = JSON.parse(data); // 解码返回的 JSON
      //   console.log("resultObj: ", resultObject)
      // } else {
      //   console.log("resultObj fail")
      // }
      console.log("真正完成切换")

      this.showModelChecked = false;
    },
    handleSelectMultimodalLittleModelUpdate(curModelInfo) {
      if (curModelInfo !== this.curMultimodalLittleInfo) {
        const oldId = this.curMultimodalLittleInfo ? this.curMultimodalLittleInfo.id : "4002";
        const indexOld = this.multimodalLittleIdToIndex(oldId);
        this.curMultimodalLittleInfo = curModelInfo;
        const indexNew = this.multimodalLittleIdToIndex(curModelInfo.id);
        this.multimodalLittlePortraitStates = {
          ...this.multimodalLittlePortraitStates,
          [indexOld]: false,
          [indexNew]: true
        };
      }
      localStorage.setItem('currentMultimodalLittleModelId', this.curMultimodalLittleInfo.id);
      this.$message.success('已选多模态小模型：' + this.curMultimodalLittleInfo.name);
      this.showModelChecked = false;
    },
    showModel() {
      this.showModelChecked = true;
    },
    removePunctuation(str) {
      // 正则表达式匹配所有标点符号
      const punctuationRegex = /[.,，。、？?/#!$%^&*;:{}=\-_`~()]/gi;
      // 替换标点符号为空字符串
      return str.replace(punctuationRegex, '');
    },
    
    showVoice() {
      if(this.voiceStatus !== 2 && this.justCutSpeak !== true) {
        if(this.selectedEmotionOption === null || this.selectedEmotionOptionLabel === '' || this.selectedOption === null || this.selectedOptionLabel === '') {
          this.$message.error('您还未选音色及情感，请选好后再开始对话哦');
        } 
        else {
          if(this.voiceStatus === 0)
            this.voiceStatus = 1
          else
            this.voiceStatus = 0

          // 更改为开始录音的逻辑
          // this.showVoiceChecked = true;
          if (!this.voiceRecognizing) {
            //没有在识别，点击后开启识别
            this.$message.success('您可以开始说话了');
            this.$refs.ASRVoice.openVoice();
            this.voiceRecognizing = true;
          } else {
            // 已经在识别，点击后停止识别
            this.isListening = false; // 停止打断检测
            this.$refs.ASRVoice.closeVoice();
            this.voiceRecognizing = false;
            this.audioElement.pause();
            this.voiceRecognitionText = ''
            // 等close结束，模拟再点一下，重新open开始录音
            this.justCutSpeak = true
            setTimeout(() => { 
              this.justCutSpeak = false
              this.showVoice();
            }, 1000); 
          }
        }
      } else if(this.justCutSpeak === true) {
        this.$message.error('打断需等待1秒，然后您可以开始说话');
      } else {
        this.$message.error('我还在思考，请稍后先听我回答，再决定是否重新开始对话');
      }
    },
    async showTopic() {
      this.showTopicChecked = true;

      // 先获取小模型深度建议
      try {
        const inputText = `主题关键词：${this.topicClicked}\n\n部分文档内容（节选）：\n${this.topicRelText}`;
        const depthSuggestion = await getDepthSuggestion(inputText, localStorage.getItem('userId'), "topic_qa");
        
        // 根据topicRelText、topicClicked、深度建议，获得相关问题
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('topicRelText', this.topicRelText);
        formData.append('topicClicked', this.topicClicked);
        if (depthSuggestion) {
          formData.append('depth_suggestion', depthSuggestion);
          console.log('[深度建议] 获取成功:', depthSuggestion);
        }
        
        console.log('点击了topic', this.topicClicked, this.topicRelText);
        topic_getRelQuestions(formData).then(data => {
          this.topicRelQuestions = data['topicRelQuestions'];
        }).catch(error => {
          console.error("An error occurred:", error);
        });
      } catch (error) {
        console.error('[深度建议] 获取失败:', error);
        // 即使深度建议获取失败，也继续生成追问
        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('topicRelText', this.topicRelText);
        formData.append('topicClicked', this.topicClicked);
        topic_getRelQuestions(formData).then(data => {
          this.topicRelQuestions = data['topicRelQuestions'];
        }).catch(err => {
          console.error("An error occurred:", err);
        });
      }
    },
    showImg() {
      console.log("isLoadingImg", this.isLoadingImg);
      this.isLoadingImg = false;
      this.showImgChecked = true;
    },
    showModelLeft() {
      this.toBeSwitched = 0;   // 表明是左边的div要切换模型
      this.showModel();
    },
    showModelUp() {
      this.toBeSwitched = 1;
      this.showModel();
    },
    showModelDown() {
      this.toBeSwitched = 2;
      this.showModel();
    },
    hideModelDialog() {
      this.showModelChecked = false;
    },
    hideBgcDialog() {
      this.showBgcChecked = false;
    },
    hideTopicDialog() {
      this.showTopicChecked = false;
    },
    hideVoiceDialog() {
      this.showVoiceChecked = false;
    },
    hideImgDialog() {
      // this.showImgChecked = false;
      if(this.doubleClick === false) {
        this.stopSpeech()
        this.showImgChecked = false;
      } else {
        this.$message.error('您操作过快，请您稍等2s，再关闭图片查看');
      }
    },
    showCardWindowWithoutMaking() {
      this.chatBtnChecked = !this.chatBtnChecked; // 切换isChecked的值
      var container = document.querySelector('.chat-up');
      if (container.style.display === 'none' || container.style.display === '') {
        container.style.display = 'flex';
        container.style.height = '100%';
      } else {
        container.style.height = '0';
        container.style.display = 'none';
      }
      this.cardSingleMaking = true
    },
    showCardWindow() {
      this.chatBtnChecked = !this.chatBtnChecked; // 切换isChecked的值
      var container = document.querySelector('.chat-up');
      if (container.style.display === 'none' || container.style.display === '') {
        container.style.display = 'flex';
        container.style.height = '100%';
      } else {
        container.style.height = '0';
        container.style.display = 'none';
      }
      // 🔥 先滚动到顶部，再显示等待卡片
      if (this.$refs.CardGrid) {
        this.$refs.CardGrid.scrollToTop();
      }
      this.cardMaking = true
    },
    showChatWindow() {
      this.chatBtnChecked = !this.chatBtnChecked; // 切换isChecked的值
      var container = document.querySelector('.chat-up');
      if (container.style.display === 'none' || container.style.display === '') {
        container.style.display = 'flex';
        container.style.height = '100%';
      } else {
        container.style.height = '0';
        container.style.display = 'none';
      }
    },

    resolveCurrentAudioFileName() {
      if (!this.fileNameList || this.fileNameList.length === 0) return null;
      const audioExt = ['wav', 'mp3', 'm4a', 'aac', 'flac', 'ogg'];
      const hit = this.fileNameList.find(name => {
        if (!name || typeof name !== 'string' || !name.includes('.')) return false;
        const ext = name.split('.').pop().toLowerCase();
        return audioExt.includes(ext);
      });
      return hit || null;
    },
    async getAudioFileForAnalysis(audioFileName, userId) {
      const encoded = encodeURIComponent(audioFileName) + "&userbook=" + encodeURIComponent(userId);
      const url = `${API_BASE_URL}/api/pdf/?url=${encoded}`;
      try {
        const cachedBlob = await this.getFileFromCache(url, userId);
        if (cachedBlob) {
          return new File([cachedBlob], audioFileName, { type: cachedBlob.type || 'audio/wav' });
        }
      } catch (error) {
        console.warn('从本地缓存获取音频失败:', error);
      }
      const response = await fetch(url);
      if (!response.ok) throw new Error('无法从服务器获取音频文件');
      const blob = await response.blob();
      this.saveFileToCache(url, blob, userId, 'audio');
      return new File([blob], audioFileName, { type: blob.type || 'audio/wav' });
    },
    async processAudioContextForMessage(audioFileName, originalInputMsg, options = {}) {
      const { enableBacktrack = true } = options;
      const userId = localStorage.getItem('userId');
      if (!userId || !audioFileName) return;
      const summaryPayloadForAudio = this.getSummaryFileListForCurrentFile(audioFileName);
      const metadataFileListForAudio = summaryPayloadForAudio ? summaryPayloadForAudio.fileList : (this.fileNameList || []);
      const metadata = await loadMergedMetadataForInference(audioFileName, metadataFileListForAudio, userId);
      const audioFile = await this.getAudioFileForAnalysis(audioFileName, userId);
      const modelIdRaw = localStorage.getItem('currentMultimodalLittleModelId') || localStorage.getItem('currentLittleModelId') || '';
      const modelId = String(modelIdRaw).trim();
      const isMultimodal = modelId === '4001' || modelId === '4002';
      let formattedResult = '';
      let inferenceResult = null;
      if (isMultimodal) {
        this.$message.info('正在调用多模态小模型分析音频文件...');
        inferenceResult = await callMultimodalLittleModel({
          audioFile,
          model_id: modelId,
          userText: originalInputMsg,
          metadata: { ...metadata, model_id: modelId }
        });
        formattedResult = formatMultimodalLittleModelResult(inferenceResult, modelId, metadata);
        if (formattedResult) {
          this.$message.success('多模态小模型分析完成，结果将添加到回答上下文中');
        }
      } else {
        const requestParams = {
          audioFile,
          task_type: metadata.task_type || 'copd',
          modality: metadata.modality || 'cough',
          metadata: { ...metadata },
          return_probs: true
        };
        const analysisResult = await uploadAudioForAnalysis(requestParams);
        const enrichedResult = {
          ...analysisResult,
          task_type: requestParams.task_type,
          modality: requestParams.modality,
          metadata: requestParams.metadata,
          audio_filename: audioFileName
        };
        inferenceResult = enrichedResult;
        formattedResult = formatAnalysisResultAsPrompt(enrichedResult);
      }

      const blockId = audioFileName.replace(/\.[^/.]+$/, '');
      this.multimodalAnalysisResult = formattedResult || null;

      if (enableBacktrack) {
        const previousBlockIds = await getPreviousBlockIdsForBacktrack(blockId, userId, 3);
        this.backtrackHistoryPrompt = await getBacktrackHistoryPrompt(userId, previousBlockIds, blockId);
      } else {
        this.backtrackHistoryPrompt = null;
      }
    },

    async sendMsg() {
      if (this.isEnhancing) {
        this.$message.warning('正在增强导问中，请稍候...');
        return;
      }

      // === 步骤1：全局中断所有窗口 ===
      const username = localStorage.getItem('userId');
      try {
        console.log('[全局中断] 发送新消息前，中断所有窗口');
        await interruptAllOnNewMessage(username);
        console.log('[全局中断] 所有窗口中断请求已发送');
      } catch (error) {
        console.error('[全局中断] 中断请求失败:', error);
        // 即使中断失败也继续发送消息
      }

      // 半自动化添加记录 - 添加更多必要字段
      this.recordOperation('send_message', {
        message: this.inputMsg,
        fileNameList: this.fileNameList,
        leftSelectList: this.leftSelectList,
        rightSelectList: this.rightSelectList,
        choosedCardIdList: this.choosedCardIdList,
        sceneName: this.sceneName,
        subSceneName: this.subSceneName,
        // 添加缺失的字段
        otherFiles: this.fileNameList,
        modelId: this.curModelInfo.id,  // 假设使用主窗口模型
        isHistoryUsed: this.isHistoryUsed,
        isMemorySystemUsed: this.isMemorySystemUsed,
        isSummaryUsed: this.isSummaryUsed,
        rounds: this.rounds,
        modelStates: this.portraitStates
      });

      this.lastQuestion = this.inputMsg

      this.threeModelQAState = 1
      // 这里再补一层重置处理，在未找到根本原因前，暂时避免例如answerList加到6导致不出综合的情况
      this.answerList = []
      this.ModelContentMerge = ""
      this.isMainWindowOpen = false
      this.validNum = 0
      // 标记下次追问更新时需要清空（跨问答逻辑：下一次提问的第一个窗口追问要先清空上一次的追问）
      this.shouldClearQuestionsOnNextUpdate = true

      if (!this.chatBtnChecked) this.showChatWindow();

      if (this.choosedCardIdList.length === 0) {
        const originalInputMsg = this.inputMsg;
        const audioFileName = this.resolveCurrentAudioFileName();
        const hasAudioFile = !!audioFileName;
        this.multimodalAnalysisResult = null;
        this.backtrackHistoryPrompt = null;
        if (hasAudioFile) {
          try {
            await this.processAudioContextForMessage(audioFileName, originalInputMsg);
          } catch (error) {
            console.warn('[音频多模态链路] 预处理失败，继续原始提问:', error);
            this.$message.warning('多模态小模型调用失败，将直接发送消息: ' + (error.message || '未知错误'));
          }
        }

        try {
          let windowModelNames = {
            "left": this.$refs.ChatWindow.chatModelInfo.name,
            "upper": this.$refs.ChatWindowUp.chatModelInfo.name,
            "lower": this.$refs.ChatWindowDown.chatModelInfo.name
          }

          let messageToSend = this.inputMsg;  // 用户提问
          if (this.multimodalAnalysisResult || this.backtrackHistoryPrompt) {
            const parts = [];
            if (this.multimodalAnalysisResult) {
              const currentBlockId = hasAudioFile && audioFileName ? audioFileName.replace(/\.[^/.]+$/, '') : '';
              const currentDateLabel = currentBlockId ? formatBlockIdAsDate(currentBlockId) : '';
              const header = currentDateLabel ? `当前文件推理结果（${currentDateLabel}）：` : '当前文件推理结果：';
              parts.push(header + '\n' + this.multimodalAnalysisResult);
            }
            if (this.backtrackHistoryPrompt) parts.push(this.backtrackHistoryPrompt);
            parts.push(this.inputMsg);
            messageToSend = parts.join('\n\n');
          }

          let fileListForRAG = this.fileNameList;
          let leftSelectForRAG = this.leftSelectList;
          let rightSelectForRAG = this.rightSelectList;
          if (hasAudioFile) {
            fileListForRAG = [];
            leftSelectForRAG = '';
            rightSelectForRAG = '';
          }

          // 反问判定：取主窗口上一轮完整问答（多窗共用主窗回答）
          let socraticPrevTurn = null;
          try {
            if (this.$refs.ChatWindow && typeof this.$refs.ChatWindow.getLastCompletedQaTurnForSocratic === 'function') {
              socraticPrevTurn = this.$refs.ChatWindow.getLastCompletedQaTurnForSocratic();
            }
          } catch (e) {
            socraticPrevTurn = null;
          }

          // 首先发送消息到 ChatWindow
          this.$refs.ChatWindow.sendText(messageToSend, fileListForRAG, leftSelectForRAG, rightSelectForRAG, windowModelNames, this.coreKeyword, socraticPrevTurn);

          // 然后发送消息到 ChatWindowUp
          this.$refs.ChatWindowUp.sendText(messageToSend, fileListForRAG, leftSelectForRAG, rightSelectForRAG, windowModelNames, this.coreKeyword, socraticPrevTurn);

          // 最后发送消息到 ChatWindowDown
          this.$refs.ChatWindowDown.sendText(messageToSend, fileListForRAG, leftSelectForRAG, rightSelectForRAG, windowModelNames, this.coreKeyword, socraticPrevTurn);

          // await Promise.all([
          //   this.$refs.ChatWindow.sendText(this.inputMsg, this.fileNameList, this.leftSelectList, this.rightSelectList),
          //   this.$refs.ChatWindowUp.sendText(this.inputMsg, this.fileNameList, this.leftSelectList, this.rightSelectList),
          //   this.$refs.ChatWindowDown.sendText(this.inputMsg, this.fileNameList, this.leftSelectList, this.rightSelectList)
          // ]);

        } catch (error) {
          console.error('发送消息时发生错误:', error);
        }
        console.log("发送信息：", this.inputMsg);
        // 🔥 保存当前coreKeyword，在发送消息时传递
        const currentCoreKeyword = this.coreKeyword;
        this.inputMsg = "";
        this.multimodalAnalysisResult = null;
        this.backtrackHistoryPrompt = null;
        // 注意：coreKeyword在发送时已经传递，这里不清空，让它在下次tab增强时更新
        // 但发送后可以清空，因为下次tab增强时会重新获取
        this.coreKeyword = null;
      } else {
        // 选了卡片时也支持体联音频：先做多模态/回溯，再拼卡片素材发出
        const originalInputMsg = this.inputMsg;  // 用户输入
        const audioFileName = this.resolveCurrentAudioFileName();
        const hasAudioFile = !!audioFileName;
        this.multimodalAnalysisResult = null;
        this.backtrackHistoryPrompt = null;
        if (hasAudioFile) {
          try {
            await this.processAudioContextForMessage(audioFileName, originalInputMsg);
          } catch (error) {
            console.warn('[音频多模态链路] 预处理失败，继续原始提问:', error);
            this.$message.warning('多模态小模型调用失败，将直接发送消息: ' + (error.message || '未知错误'));
          }
        }

        let formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('choosedCardIdList', this.choosedCardIdList);
        if(this.openCardId !== null) {
          formData.append('openCardId', this.openCardId);
        }
        if(this.chosenContent !== "") {
          formData.append('chosenContent', this.chosenContent);
        }
        getCardsContentByIds(formData).then(data => {
          let content = data['content'];
          content += "上面的重要素材文本是你完成下面的问题或请求需要参考的重点内容，也可能含有待修改的目标内容，请你回答：\n"
          try {
            let windowModelNames = {
              "left": this.$refs.ChatWindow.chatModelInfo.name,
              "upper": this.$refs.ChatWindowUp.chatModelInfo.name,
              "lower": this.$refs.ChatWindowDown.chatModelInfo.name
            }

            let userPart = originalInputMsg;  // 用户输入
            if (this.multimodalAnalysisResult || this.backtrackHistoryPrompt) {
              const parts = [];
              if (this.multimodalAnalysisResult) {
                const currentBlockId = hasAudioFile && audioFileName ? audioFileName.replace(/\.[^/.]+$/, '') : '';
                const currentDateLabel = currentBlockId ? formatBlockIdAsDate(currentBlockId) : '';
                const header = currentDateLabel ? `当前文件推理结果（${currentDateLabel}）：` : '当前文件推理结果：';
                parts.push(header + '\n' + this.multimodalAnalysisResult);
              }
              if (this.backtrackHistoryPrompt) parts.push(this.backtrackHistoryPrompt);
              parts.push(originalInputMsg);
              userPart = parts.join('\n\n');
            }
            const messageToSend = content + userPart;  // 卡片拼接用户输入
            let fileListForRAG = this.fileNameList;
            let leftSelectForRAG = this.leftSelectList;
            let rightSelectForRAG = this.rightSelectList;
            if (hasAudioFile) {
              fileListForRAG = [];
              leftSelectForRAG = '';
              rightSelectForRAG = '';
            }
            let socraticPrevTurn = null;
            try {
              if (this.$refs.ChatWindow && typeof this.$refs.ChatWindow.getLastCompletedQaTurnForSocratic === 'function') {
                socraticPrevTurn = this.$refs.ChatWindow.getLastCompletedQaTurnForSocratic();
              }
            } catch (e) {
              socraticPrevTurn = null;
            }
            this.$refs.ChatWindow.sendText(messageToSend, fileListForRAG, leftSelectForRAG, rightSelectForRAG, windowModelNames, this.coreKeyword, socraticPrevTurn);
            this.$refs.ChatWindowUp.sendText(messageToSend, fileListForRAG, leftSelectForRAG, rightSelectForRAG, windowModelNames, this.coreKeyword, socraticPrevTurn);
            this.$refs.ChatWindowDown.sendText(messageToSend, fileListForRAG, leftSelectForRAG, rightSelectForRAG, windowModelNames, this.coreKeyword, socraticPrevTurn);
          } catch (error) {
            console.error('发送消息时发生错误:', error);
          }
          console.log("发送信息：", this.inputMsg);
          this.inputMsg = "";
          this.multimodalAnalysisResult = null;
          this.backtrackHistoryPrompt = null;
          this.coreKeyword = null;
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
      }
    },

    // 精细处理三个窗口问答完成后的追问问题，在mainPage的最终显示
    handleQuestionContentsUpdate(data) {
      console.log('handleQuestionContentsUpdate:', data);

      // 跨问答逻辑：如果标记需要清空（新一轮问答的第一个窗口完成），先清空上一次的追问
      if (this.shouldClearQuestionsOnNextUpdate) {
        console.log('[追问更新] 新一轮问答第一个窗口完成，清空上一次的追问');
        this.questionContents = [];
        this.shouldClearQuestionsOnNextUpdate = false;  // 清除标记，后续窗口追加
      }

      // 如果已经有6个追问，不再追加（避免由多变少）
      if (this.questionContents && this.questionContents.length >= 6) {
        console.log('[追问更新] 已有6个追问，跳过更新避免由多变少');
        return;
      }
      
      // 追加而非覆盖，并去重
      if (data && data.length > 0) {
        // 追加新追问到现有列表
        let allQuestions = [...this.questionContents, ...data];
        
        // 去重逻辑
        let deduplicated = this.deduplicateQuestions(allQuestions);
        this.questionContents = deduplicated;
      } else {
        this.questionContents = data;
      }
    },

    // 追问去重逻辑
    deduplicateQuestions(questions) {
      if (!questions || questions.length === 0) return [];
      
      let minLength = 25; // 最小字数
      let finalQuestions = [];
      
      // 逐趟筛选
      for (let level = 0; level < 5; level++) {
        // 字数过滤
        let filtered = questions.filter(q => q && q.length >= minLength);
        let candidates = [...filtered];
        let toRemove = new Set();
        
        // 相似度去重（各批次之间比较，不在批次内比较）
        for (let i = 0; i < candidates.length; i++) {
          if (toRemove.has(i)) continue;
          for (let j = i + 1; j < candidates.length; j++) {
            if (toRemove.has(j)) continue;
            
            let sim = this.calculateSimilarity(candidates[i], candidates[j]);
            let threshold = 0.7 - level * 0.1;
            
            if (sim > threshold) {
              // 只保留最长的那个
              if (candidates[i].length > candidates[j].length) {
                toRemove.add(j);
              } else {
                toRemove.add(i);
                break;
              }
            }
          }
        }
        
        finalQuestions = candidates.filter((q, idx) => !toRemove.has(idx));
        
        // 数量控制
        if (finalQuestions.length >= 3 && finalQuestions.length <= 6) break;
        
        // 调整过滤条件
        if (level > 0) {
          if (finalQuestions.length > 6) {
            minLength += 5;
          } else if (finalQuestions.length < 3) {
            minLength = Math.max(15, minLength - 5);
          }
        }
      }
      
      return finalQuestions.slice(0, 6);
    },

    // 计算相似度
    calculateSimilarity(str1, str2) {
      const longer = str1.length > str2.length ? str1 : str2;
      const editDistance = this.levenshteinDistance(str1, str2);
      return (longer.length - editDistance) / longer.length;
    },

    // Levenshtein距离
    levenshteinDistance(str1, str2) {
      const matrix = [];
      for (let i = 0; i <= str2.length; i++) {
        matrix[i] = [i];
      }
      for (let j = 0; j <= str1.length; j++) {
        matrix[0][j] = j;
      }
      for (let i = 1; i <= str2.length; i++) {
        for (let j = 1; j <= str1.length; j++) {
          if (str2.charAt(i - 1) === str1.charAt(j - 1)) {
            matrix[i][j] = matrix[i - 1][j - 1];
          } else {
            matrix[i][j] = Math.min(matrix[i - 1][j - 1] + 1, matrix[i][j - 1] + 1, matrix[i - 1][j] + 1);
          }
        }
      }
      return matrix[str2.length][str1.length];
    },


    isValidAnswer(answer) {
      if (!answer) {
        console.log(`[isValidAnswer] 回答为空`);
        return false;
      }

      // 定义无效回答的模式
      const invalidPatterns = [
        "此模型您已暂时关闭使用",
        "出错，参考文档内容偏多，或服务器繁忙！",
        "API调用出错",
        "API调用超时",
        "服务器繁忙"
      ];
      
      // 检查回答长度
      const answerLength = answer.trim().length;
      const minValidLength = 50; // 最小有效长度
      
      // 检查是否包含无效模式
      const containsInvalidPattern = invalidPatterns.some(pattern => answer.includes(pattern));
      
      // 如果内容过短（小于50字符），且包含无效模式，判定为无效
      if (answerLength < minValidLength && containsInvalidPattern) {
        console.log(`[isValidAnswer] 回答无效: 长度${answerLength}字符，且包含无效模式`);
        return false;
      }
      
      // 如果内容足够长，即使包含无效模式，也视为有效（可能是思考过程中提到）
      console.log(`[isValidAnswer] 回答有效，长度: ${answer.length}`);
      return true;
    },
    mergeEnd(nowTurnQuestion, processedResult) {
      this.threeModelQAState = 0
      this.ModelContentMerge = ""
      this.isMainWindowOpen = false
      this.validNum = 0

      // 检查是否以中文叹号！或英文叹号!结尾
      // const endsWithExclamation = nowTurnQuestion.endsWith('!') || nowTurnQuestion.endsWith('！');
      // const endsWithExclamation = last6Chars.includes('!') || last6Chars.includes('！');
      // 检查最后6个字符里是否有叹号
      const last6Chars = nowTurnQuestion.slice(-6); // 获取最后6个字符
      const exclamationMatch = last6Chars.match(/!(\+{1,3})?|！(\+{1,3})?/);
      const endsWithExclamation = exclamationMatch !== null;
      let exclamationPlusCount = 0;

      if (endsWithExclamation) {
        console.log("问题以叹号结尾");
        
        // Count plus signs if exclamation mark is found
        if (exclamationMatch) {
          const matchString = exclamationMatch[0];
          exclamationPlusCount = (matchString.match(/\+/g) || []).length;
          console.log("叹号加号检测", matchString, "加号数量:", exclamationPlusCount);
        }
        
        setTimeout(() => { 
          let basePrompt = "对于前一次用户（我）提出的问题，你给出了回答，针对你的回答内容，下面会给你一些修改样例或再次迭代的建议Prompt。";
          let instructionPrompt = "注意其中可能只有部分对你有用，请你先仔细阅读和思考，筛取出其中的优质内容，排除掉关联性不大、价值不高、重复或混乱的内容，用于你修改提升对原问题的回答质量";
          
          // SoT基础技巧部分
          const sotBaseTechniques = `请采用Story of Thought的叙事策略框架：
1. 渐进式披露，逐步揭示信息，引导思考
2. 使用分支描述，探索多个思路路径和观点
3. 运用类比和类比推理，将抽象概念与熟悉情境结合来理解深层问题结构`;

          const Object = `你应该基于用户的问题本身，根据下面给你的修改样例及再次迭代的建议Prompt，并从场景阶段、可能给你的相关图文、重要素材等内容中先筛分过滤一遍，
找出强关联片段，然后将这些片段通过上面的策略技巧、方式组织起来，思考应该如何修改提升你自己上一轮对用户的问题给出的回复，并完整地完成此次修改提升`;

          // 根据加号数量应用不同的思维框架组合
          let thinkingFramework = "";
          let alignmentPercent = "增改幅度在20%左右为佳";
          let enhancementStyle = "且应该是整体和局部修改相结合，既有击穿性的整体拔高，又有局部的段落细节提升";

          if (exclamationPlusCount === 0) {
            // 基础SoT
            thinkingFramework = `${sotBaseTechniques}
请合理使用这些技巧，形成思维探索加深，${Object}`;
          } else if (exclamationPlusCount === 1) {
            // SoT+CoT
            alignmentPercent = "增改幅度在20%左右为宜";
            thinkingFramework = `${sotBaseTechniques}
结合Chain-of-Thought(CoT)链式思维框架，通过这种SoT+CoT组合方式，形成一个线性推理的回答表述，${Object}`;
            enhancementStyle = "且注重局部的段落细节提升，适度整体优化";
          } else if (exclamationPlusCount === 2) {
            // SoT+ToT
            alignmentPercent = "增改幅度在25%左右为宜";
            thinkingFramework = `${sotBaseTechniques}
结合Tree-of-Thought(ToT)树状思维框架，即多个可能的思考路径，对每个分支进行评估和比较，通过这种SoT+ToT组合方式，形成一个多分支探索的回答表述，${Object}`;
            enhancementStyle = "且应该是整体和局部修改相结合，更加注重整体思维提升";
          } else if (exclamationPlusCount === 3) {
            // SoT+ToT&GoT
            alignmentPercent = "增改幅度在30%左右为宜";
            thinkingFramework = `${sotBaseTechniques}
结合Graph-of-Thought(GoT)图状思维框架，即不同思路进行评估，并建立联系，聚合优势，消除劣势，必要时循环迭代，形成思维网络，通过这种SoT+GoT组合方式，形成一个思维聚合与循环的回答表述，${Object}`;
            enhancementStyle = "且应该重点强化整体击穿性的深度思维提升";
          }
          
          // 构建最终提示词(第二轮自动加强：大小模型对齐的提问)
          this.inputMsg = `${basePrompt}。${instructionPrompt}，然后对你自己上一轮对用户的问题给出的回答做一次修改提升，注意幅度合适，不要出现偏浮夸的比喻和过于宏大的叙事回答，要基于你的已有回答，以增强对原问题的回答质量为目的，${alignmentPercent}，${enhancementStyle}。\n${thinkingFramework}：\n【评估、修改样例或再次迭代的建议Prompt】` + processedResult;
          this.sendMsg();
        }, 400);
      }
      
      // if (endsWithExclamation) {
      //   console.log("问题以叹号结尾");
      //   setTimeout(() => { 
      //     this.inputMsg = `对于前一次用户提出的问题，你给出了回答，针对你的回答内容，这是一些修改样例及再次迭代的建议Prompt。
      //     注意其中可能只有部分对你有用，请你先仔细阅读和思考，筛取出其中的优质内容，排除掉关联性不大、价值不高、重复或混乱的内容，
      //     并简单总结你的修改思路，然后对你自己上一轮对用户的问题给出的回答做一次修改提升，增改幅度在30%到40%为佳，且应该是整体和
      //     局部修改相结合，既有击穿性的整体拔高，又有局部的段落细节提升：\n` + processedResult
      //     this.sendMsg()
      //   }, 200); 
      // }
    },
    handleAnswerListUpdate(message, filenamelist, answer, modelName, windowId) {
      this.answerList.push(answer);
      this.ModelContentMerge += "待融合文本段（" + modelName + "生成）:\n" + answer + "\n\n"
      const openWindowModelNum = Object.values(this.portraitStates).filter(value => value === true).length;

      if (this.answerList.length === 3) {
        this.context.stream.push({
          time: Date.now(),
          action: "进行了LUI2输入框对话问答",
          Specifics: {
            "human1": "请仔细看我的这些文档：\n" + JSON.stringify(filenamelist) + "\n按下面的要求回答: \n" + message,
            "AI1": "模型给出了答复:\n\n" + "第一个模型:\n" + this.answerList[0] + "\n\n第二个模型:\n" + this.answerList[1] + "\n\n第三个模型:\n" + this.answerList[2]
          },
          comments: "请给些点评吧"
        });
      }

      if (windowId === "left")
        this.isMainWindowOpen = true
      if (this.isValidAnswer(answer))
        this.validNum += 1

      console.log("answerList长度/窗口打开数：", this.answerList.length, openWindowModelNum)
      console.log("模型名/当前待融合：", modelName, this.ModelContentMerge)
      if (this.answerList.length === openWindowModelNum && this.isMainWindowOpen === true && openWindowModelNum !== 1 && this.validNum > 1) {
        // 等待0.4s让最后一个模型的追问请求先把历史记录正确保存，再开始综合回答
        setTimeout(() => { 
          this.threeModelQAState = 2
          this.answerList = []
          console.log("clear")
        }, 400); 
      }
      if (openWindowModelNum === 1 || (this.answerList.length === openWindowModelNum && this.isMainWindowOpen === false) || (this.answerList.length === openWindowModelNum && this.validNum <= 1)) {
        this.threeModelQAState = 0
        this.ModelContentMerge = ""
        this.isMainWindowOpen = false
        this.validNum = 0
      }
    },

    handleRetryCompleted(retryData) {
      // 处理重做完成事件
      console.log('收到重做完成事件:', retryData);
      
      const { windowId, modelName, answer, question } = retryData;
      
      // 更新对应窗口的回答到融合内容中
      this.updateMergeContentAfterRetry(windowId, modelName, answer);
      
      // 检查是否需要触发融合综述
      this.checkMergeTriggerAfterRetry();
    },

    updateMergeContentAfterRetry(windowId, modelName, answer) {
      // 更新融合内容，替换重做窗口的回答
      const openWindowModelNum = Object.values(this.portraitStates).filter(value => value === true).length;
      
      // 重新构建ModelContentMerge，替换对应窗口的回答
      this.ModelContentMerge = "";
      
      // 获取所有窗口的最新回答
      const allAnswers = [];
      const windowRefs = {
        'left': this.$refs.ChatWindow,
        'upper': this.$refs.ChatWindowUp,
        'lower': this.$refs.ChatWindowDown
      };
      
      // 遍历所有窗口，获取最新的回答
      Object.keys(windowRefs).forEach(wid => {
        const windowRef = windowRefs[wid];
        if (windowRef && windowRef.chatList && windowRef.chatList.length > 0) {
          // 找到最后一个模型回答（普通回答，非融合的<如果已经完成融合再重做，避免把融合的作为主窗口模型原回答纳入重新构建融合内容>）
          for (let i = windowRef.chatList.length - 1; i >= 0; i--) {
            const item = windowRef.chatList[i];
            if (item.uid !== '1001' && item.uid !== '2000' && this.isValidAnswer(item.msg)) {
              allAnswers.push({
                windowId: wid,
                modelName: item.name,
                answer: item.msg
              });
              break;
            }
          }
        }
      });
      
      // 重新构建融合内容
      allAnswers.forEach(answerData => {
        this.ModelContentMerge += "待融合文本段（" + answerData.modelName + "生成）:\n" + answerData.answer + "\n\n";
      });
      
      console.log('重做后更新融合内容:', this.ModelContentMerge);
    },

    checkMergeTriggerAfterRetry() {
      // 检查重做后是否需要触发融合综述
      const openWindowModelNum = Object.values(this.portraitStates).filter(value => value === true).length;
      
      // 重新计算有效回答数量
      let validCount = 0;
      const windowRefs = {
        'left': this.$refs.ChatWindow,
        'upper': this.$refs.ChatWindowUp,
        'lower': this.$refs.ChatWindowDown
      };
      
      Object.keys(windowRefs).forEach(wid => {
        const windowRef = windowRefs[wid];
        if (windowRef && windowRef.chatList && windowRef.chatList.length > 0) {
          // 找到最后一个模型回答
          for (let i = windowRef.chatList.length - 1; i >= 0; i--) {
            const item = windowRef.chatList[i];
            if (item.uid !== '1001' && item.uid !== '2000' && this.isValidAnswer(item.msg)) {
              validCount++;
              break;
            }
          }
        }
      });

      console.log('重做后有效回答数量:', validCount, '打开窗口数:', openWindowModelNum, '主窗口状态:', this.isMainWindowOpen);
      
      // 如果有效回答数量达到2个或以上，且主窗口打开，则触发融合综述
      // if (validCount >= 2 && this.isMainWindowOpen && openWindowModelNum > 1) {
      // 如果有效回答数量达到2个或以上，则触发融合综述
      if (validCount >= 2 && openWindowModelNum > 1) {
        setTimeout(() => {
          this.threeModelQAState = 2;
          this.answerList = [];
          console.log('重做后开始融合综述');
        }, 400);
      } else if (validCount < 2) {
        // 如果有效回答不足2个，重置状态
        this.threeModelQAState = 0;
        this.ModelContentMerge = "";
        this.isMainWindowOpen = false;
        this.validNum = 0;
        console.log('重做后有效回答不足，重置融合状态');
      }
    },

    handleNumberDoubleClick(item) {
      if (this.isEnhancing) {
        this.$message.warning('正在增强导问中，请稍候...');
        return;
      }

      this.isEnhancing = true;
      this.hideTopicDialog();
      this.hideImgDialog();
      this.inputMsg = item;
      
      // 显示加载状态
      this.$message.success('正在增强导问...');
      
      if (this.choosedCardIdList.length === 0) {
        // 准备请求数据
        let formData = new FormData();
        let userId = localStorage.getItem('userId');
        let realName = localStorage.getItem('realName');
        
        // 基础信息
        formData.append('username', userId);
        formData.append('original_question', item);
        formData.append('sceneName', this.sceneName);
        formData.append('subSceneName', this.subSceneName);
        if(this.lastQuestion !== "") 
          formData.append('last_question', this.lastQuestion);
        question_enhance(formData).then(data => {
          if(data['error_num'] === 0) {
            this.inputMsg = data['modified_question']
          } else {           
            console.log("保存操作流失败")         
          }      
          this.isEnhancing = false; 
        }).catch(error => {         
          console.error("An error occurred:", error); // 错误处理      
          this.isEnhancing = false; 
        });
      } else {
        let formDataPre = new FormData();
        formDataPre.append('username', localStorage.getItem('userId'));
        formDataPre.append('choosedCardIdList', this.choosedCardIdList);
        if(this.openCardId !== null) {
          formDataPre.append('openCardId', this.openCardId);
        }
        if(this.chosenContent !== "") {
          formDataPre.append('chosenContent', this.chosenContent);
        }
        getCardsContentByIds(formDataPre).then(data => {
          let content = data['content'];
          content += "\n上面的重要素材文本是完成问题/请求/追问等需要参考的重点内容，也可能含有待修改的目标内容"
          
          // 准备请求数据
          let formData = new FormData();
          let userId = localStorage.getItem('userId');
          let realName = localStorage.getItem('realName');
          
          // 基础信息
          formData.append('username', userId);
          formData.append('original_question', item);
          formData.append('card_content', content);
          formData.append('sceneName', this.sceneName);
          formData.append('subSceneName', this.subSceneName);
          if(this.lastQuestion !== "") 
            formData.append('last_question', this.lastQuestion);
          question_enhance(formData).then(data => {
            if(data['error_num'] === 0) {
              this.inputMsg = data['modified_question']
            } else {           
              console.log("保存操作流失败")         
            }      
            this.isEnhancing = false; 
          }).catch(error => {         
            console.error("An error occurred:", error); // 错误处理      
            this.isEnhancing = false; 
          });
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
      }
    },
    // 点击序号 - 始终进入编辑模式
    handleNumberClick(item) {
      // 半自动化新增
      this.recordOperation('enhance_question', {
        original_question: item,
        last_question: this.lastQuestion,
        card_content: "", // 可以根据需要添加
        fileNameList: this.fileNameList,
        leftSelectList: this.leftSelectList,
        rightSelectList: this.rightSelectList,
        choosedCardIdList: this.choosedCardIdList,
        sceneName: this.sceneName,
        subSceneName: this.subSceneName
      });

      this.hideTopicDialog();
      this.hideImgDialog();
      this.inputMsg = item;
    },
    // 点击主体内容 - 根据是否含xxx决定行为
    handleContentClick(item) {
      this.hideTopicDialog();
      this.hideImgDialog();
      this.inputMsg = item;
      if (item.includes('xxx') === false) {
        // 不含xxx的主体内容点击 - 直接发送
        this.sendMsg();
        this.backtoDefault();
      }
    },
    // 原有的点击方法
    handleQuestionClick(item) {
      // 半自动化新增
      this.recordOperation('click_question', {
        question: item,
        fileNameList: this.fileNameList,
        leftSelectList: this.leftSelectList,
        rightSelectList: this.rightSelectList,
        choosedCardIdList: this.choosedCardIdList,
        sceneName: this.sceneName,
        subSceneName: this.subSceneName
      });

      this.hideTopicDialog();
      this.hideImgDialog();
      this.inputMsg = item;
      if (item.includes('xxx') === false) {
        this.sendMsg();
        this.backtoDefault();
      }
    },
    handleImgTopicClick(item) {
      this.topicClicked = item; // 把点击的topic存起来
      this.topicRelText = this.imgClickedText; // 图片相关的文本作为点击topic的上下文
      this.showTopic();
    },

    // DMT分析相关方法

    // startDMTAnalysis() {
    //   // 创建文件选择器
    //   const input = document.createElement('input');
    //   input.type = 'file';
    //   input.accept = '.xlsx,.xls';
    //   input.onchange = (event) => {
    //     const file = event.target.files[0];
    //     if (file) {
    //       this.processDMTAnalysis(file);
    //     }
    //   };
    //   input.click();
    // },
    async startDMTAnalysis() {
      try {
        // 先检查是否有匹配的Excel配置文件
        const username = localStorage.getItem('userId'); // 格式：用户名_本子名
        const imageName = this.curFileInfo.name || 'analysis_image.png';
        
        // 获取图片文件名（不含扩展名）第一个下划线"_"前的部分
        const imageBaseName = imageName.replace(/\.[^/.]+$/, "").split('_')[0];
        
        // 检查是否有匹配的Excel文件
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取

        const checkResponse = await fetch(`${BASE_URL}/api/check_dmt_config`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username: username,
            imageBaseName: imageBaseName
          })
        });
        
        const checkResult = await checkResponse.json();
        
        if (checkResult.hasConfig) {
          // 有匹配的配置文件，直接使用
          console.log('[DMT] 找到匹配的配置文件:', checkResult.configFile);
          this.processDMTAnalysisWithConfig(checkResult.configFile);
        } else {
          // 没有匹配的配置文件，提示用户需要上传
          this.$message.warning('未找到匹配的DMT配置文件，请先通过文件上传功能上传Excel配置文件（文件名需以图片名开头）');
        }
      } catch (error) {
        console.error('[DMT] 检查配置文件失败:', error);
        this.$message.error('检查配置文件失败，请确保已上传Excel配置文件');
      }
    },

    async processDMTAnalysisWithConfig(configFilePath) {
      try {
        console.log('[DMT] 使用现有配置文件进行分析...');
        
        // 验证必要参数
        const username = localStorage.getItem('userId');
        console.log('[DMT] 用户名:', username);
        console.log('[DMT] 配置文件路径:', configFilePath);
        console.log('[DMT] 图片数据:', this.imgClicked ? '存在' : '缺失');
        
        if (!username) {
          throw new Error('用户名未设置');
        }
        if (!configFilePath) {
          throw new Error('配置文件路径缺失');
        }
        if (!this.imgClicked) {
          throw new Error('图片数据缺失');
        }

        // 准备FormData
        const formData = new FormData();
        formData.append('username', username);
        formData.append('configPath', configFilePath);
        
        // 将当前图片转换为文件对象
        const imageBlob = this.base64ToBlob(this.imgClicked);
        const imageName = this.curFileInfo.name || 'analysis_image.png';
        const imageFile = new File([imageBlob], imageName, { type: 'image/png' });
        formData.append('image', imageFile);
        
        console.log('[DMT] FormData准备完成, 图片名: ', imageName);
        for (let [key, value] of formData.entries()) {
          console.log(`[DMT] FormData - ${key}:`, value);
        }

        // 启动DMT分析
        const response = await startDMTAnalysis(formData);
        
        if (response.error_num === 0) {
          const taskId = response.task_id;
          
          // 初始化任务数据
          this.dmtTasks[taskId] = {
            status: 'processing',
            progress: 0,
            currentStage: '准备分析...',
            progressDialog: null,
            configFile: configFilePath,
            imageFile: imageFile,
            imageName: imageName
          };
          
          // 创建进度通知
          this.dmtTasks[taskId].progressDialog = ElNotification({
            title: `DMT分析进度 - ${imageName}`,
            message: () => h('div', null, [
              h(ElProgress, {
                percentage: this.dmtTasks[taskId].progress,
                status: this.dmtTasks[taskId].status === 'failed' ? 'exception' : (this.dmtTasks[taskId].status === 'completed' ? 'success' : ''),
                format: () => `${this.dmtTasks[taskId].currentStage} (${this.dmtTasks[taskId].progress}%)`
              })
            ]),
            duration: 0,
            position: 'bottom-right'
          });
          
          this.$message.success('DMT分析已启动（使用现有配置文件）');
          
          // 开始轮询状态
          this.pollDMTStatus(taskId);
        } else {
          this.$message.error('启动DMT分析失败: ' + response.msg);
        }
      } catch (error) {
        console.error('DMT分析失败:', error);
        this.$message.error('DMT分析失败: ' + error.message);
      }
    },

    async processDMTAnalysis(configFile) {
      try {
        console.log('[DMT] 开始处理DMT分析...');
        
        // 验证必要参数
        const username = localStorage.getItem('userId');
        const realName = localStorage.getItem('realName');
        console.log('[DMT] 用户名:', username);
        console.log('[DMT] 配置文件:', configFile);
        console.log('[DMT] 图片数据:', this.imgClicked ? '存在' : '缺失');
        
        if (!username) {
          throw new Error('用户名未设置');
        }
        if (!configFile) {
          throw new Error('请选择配置Excel文件');
        }
        if (!this.imgClicked) {
          throw new Error('图片数据缺失');
        }

        // 准备FormData
        const formData = new FormData();
        formData.append('username', username);
        formData.append('realName', realName);
        formData.append('config', configFile);
        
        // 将当前图片转换为文件对象，使用原图片名而非固定名
        const imageBlob = this.base64ToBlob(this.imgClicked);
        const imageName = this.curFileInfo.name || 'analysis_image.png'; // 使用原图片名
        const imageFile = new File([imageBlob], imageName, { type: 'image/png' });
        formData.append('image', imageFile);
        formData.append('cardScoreThreshold', this.cardScoreThreshold);
        
        console.log('[DMT] FormData准备完成, 图片名: ', imageName);
        for (let [key, value] of formData.entries()) {
          console.log(`[DMT] FormData - ${key}:`, value);
        }

        // 启动DMT分析
        const response = await startDMTAnalysis(formData);
        
        if (response.error_num === 0) {
          const taskId = response.task_id;
          
          // 初始化任务数据
          this.dmtTasks[taskId] = {
            status: 'processing',
            progress: 0,
            currentStage: '准备分析...',
            progressDialog: null,
            configFile: configFile,
            imageFile: imageFile,
            imageName: imageName
          };
          
          // 创建进度通知
          this.dmtTasks[taskId].progressDialog = ElNotification({
            title: `DMT分析进度 - ${imageName}`,
            message: () => h('div', null, [
              h(ElProgress, {
                percentage: this.dmtTasks[taskId].progress,
                status: this.dmtTasks[taskId].status === 'failed' ? 'exception' : (this.dmtTasks[taskId].status === 'completed' ? 'success' : ''),
                format: () => `${this.dmtTasks[taskId].currentStage} (${this.dmtTasks[taskId].progress}%)`
              })
            ]),
            duration: 0,
            position: 'bottom-right',
            // offset: 20 + Object.keys(this.dmtTasks).length * 120 // 根据任务数量调整偏移
          });
          
          this.$message.success('DMT分析已启动');
          
          // 开始轮询状态
          this.pollDMTStatus(taskId);
        } else {
          this.$message.error('启动DMT分析失败: ' + response.msg);
        }
      } catch (error) {
        console.error('DMT分析失败:', error);
        this.$message.error('DMT分析失败: ' + error.message);
      }
    },

    async pollDMTStatus(taskId) {
      const task = this.dmtTasks[taskId];
      if (!task || task.status === 'completed' || task.status === 'failed') {
        console.log('[DMT] 轮询已停止 - taskId:', taskId, 'status:', task ? task.status : '任务不存在');
        return;
      }

      try {
        console.log('[DMT] 开始轮询状态，taskId:', taskId);
        const response = await getDMTAnalysisStatus(taskId);
        
        console.log('[DMT] 状态响应:', response);
        
        if (response.error_num === 0) {
          task.status = response.status;
          
          console.log('[DMT] 更新进度:', {
            status: response.status,
            progress: response.progress,
            stage: response.current_stage
          });
          
          // 更新响应式数据
          task.progress = response.progress || 0;
          task.currentStage = response.current_stage || '分析中...';
          
          // 强制更新进度条显示
          if (task.progressDialog) {
            task.progressDialog.message = () => h('div', null, [
              h(ElProgress, {
                percentage: task.progress,
                status: response.status === 'failed' ? 'exception' : (response.status === 'completed' ? 'success' : ''),
                format: () => `${task.currentStage} (${task.progress}%)`
              })
            ]);
          }

          if (response.status === 'completed') {
            console.log('[DMT] 分析完成，准备获取结果');
            // 分析完成，获取结果
            setTimeout(() => {
              task.progressDialog.close();
              this.getDMTResult(taskId);
            }, 1000);
          } else if (response.status === 'failed') {
            console.log('[DMT] 分析失败:', response.error_message);
            // 分析失败
            this.$message.error('DMT分析失败: ' + response.error_message);
            setTimeout(() => {
              task.progressDialog.close();
            }, 2000);
          } else {
            console.log('[DMT] 继续轮询，2秒后再次检查');
            // 继续轮询
            setTimeout(() => {
              this.pollDMTStatus(taskId);
            }, 2000);
          }
        } else {
          console.error('[DMT] API返回错误:', response);
          this.$message.error('获取状态失败: ' + response.msg);
        }
      } catch (error) {
        console.error('获取DMT状态失败:', error);
        setTimeout(() => {
          this.pollDMTStatus(taskId);
        }, 5000); // 出错时延长轮询间隔
      }
    },

    async getDMTResult(taskId) {
      try {
        const response = await getDMTAnalysisResult(taskId);
        
        if (response.error_num === 0) {
          // 显示分析结果
          this.showDMTResult(response.result);
          this.$message.success('DMT分析完成！');
        } else {
          this.$message.error('获取DMT结果失败: ' + response.msg);
        }
      } catch (error) {
        console.error('获取DMT结果失败:', error);
        this.$message.error('获取DMT结果失败: ' + error.message);
      }
    },

    showDMTResult(result) {
      // 将DMT分析结果格式化为目录树形式显示
      let resultText = '📊 DMT分析结果目录树\n';
      resultText += '═══════════════════════════════════════\n\n';
      
      // 对T级键进行排序，确保显示顺序一致
      const tKeys = Object.keys(result).filter(key => key.startsWith('T')).sort();
      // 统计M节点的数量
      let mNodeCount = 0;
      for (let tKey of tKeys) {
        const tValue = result[tKey];
        const mKeys = Object.keys(tValue).filter(key => key.startsWith('M'));
        mNodeCount += mKeys.length;
      }
      for (let i = 0; i < tKeys.length; i++) {
        const tKey = tKeys[i];
        const tValue = result[tKey];
        
        if (typeof tValue === 'object' && tValue !== null) {
          // T级版面（根节点）
          const isLastT = i === tKeys.length - 1;
          resultText += `${isLastT ? '└─' : '├─'} 📄 **${tKey}**`;
          if (tValue.T级描述) {
            resultText += ` - **${tValue.T级描述}**`;
          }
          resultText += '\n';
          
          // T级分析内容
          if (tValue.context_analysis || tValue.deficiency_detection || tValue.final_explanation) {
            const tPrefix = isLastT ? '    ' : '│   ';
            if (mNodeCount > 10) { // M节点总数大于10时，显示T级（除T0外）分析内容
              if (tValue.context_analysis) {
                resultText += `${tPrefix}🔍 **裂变分析**: ${tValue.context_analysis}\n`;
              }
              if (tValue.deficiency_detection) {
                resultText += `${tPrefix}⚡ **聚变分析**: ${tValue.deficiency_detection}\n`;
              }
            }
            if (tValue.final_explanation) {
              resultText += `${tPrefix}📜 **总体分析**: ${tValue.final_explanation}\n`;
            }
          }
          if (mNodeCount > 10) { // M节点总数大于10时，隐藏M级及以下内容
            continue;
          }
          // 获取M级键并排序
          const mKeys = Object.keys(tValue).filter(key => key.startsWith('M')).sort();
          
          for (let j = 0; j < mKeys.length; j++) {
            const mKey = mKeys[j];
            const mValue = tValue[mKey];
            
            if (typeof mValue === 'object') {
              const isLastM = j === mKeys.length - 1;
              const mPrefix1 = isLastT ? '    ' : '│   ';
              const mPrefix2 = isLastT ? '        ' : '│       ';
              
              // M级版面（二级节点）
              resultText += `${mPrefix1}${isLastM ? '└─' : '├─'} 📝 **${mKey}**`;
              if (mValue.M级区域描述) {
                resultText += ` - **${mValue.M级区域描述}**`;
              }
              resultText += '\n';
              
              // M级分析内容
              if (mValue.context_analysis || mValue.deficiency_detection) {
                const analysisPrefix = mPrefix2.replace(/├─|└─/, '');
                if (mValue.context_analysis) {
                  resultText += `${analysisPrefix}🔍 **裂变分析**: ${mValue.context_analysis}\n`;
                }
                if (mValue.deficiency_detection) {
                  resultText += `${analysisPrefix}⚡ **聚变分析**: ${mValue.deficiency_detection}\n`;
                }
              }
              
              // 获取D级键并排序
              // const dKeys = Object.keys(mValue).filter(key => key.startsWith('D')).sort();
              
              // for (let k = 0; k < dKeys.length; k++) {
              //   const dKey = dKeys[k];
              //   const dValue = mValue[dKey];
                
              //   if (typeof dValue === 'object') {
              //     const isLastD = k === dKeys.length - 1;
              //     const dPrefix1 = isLastM ? mPrefix2 : mPrefix2.replace('    ', '│   ');
              //     const dPrefix2 = isLastM ? 
              //       (isLastD ? mPrefix2 + '    ' : mPrefix2 + '│   ') : 
              //       mPrefix2.replace('    ', '│   ') + (isLastD ? '    ' : '│   ');
                  
              //     // D级版面（三级节点）
              //     resultText += `${dPrefix1}${isLastD ? '└─' : '├─'} 📋 ${dKey}`;
              //     if (dValue.D级区域描述) {
              //       resultText += ` - ${dValue.D级区域描述}`;
              //     }
              //     resultText += '\n';
                  
              //     // D级详细内容
              //     const contentItems = [];
              //     if (dValue.content_text) {
              //       contentItems.push(`📄 内容: ${dValue.content_text}`);
              //     }
              //     if (dValue.otcl_analysis) {
              //       contentItems.push(`🎯 OTCL分析: ${dValue.otcl_analysis}`);
              //     }
              //     if (dValue.format_evaluation) {
              //       contentItems.push(`✍️ 书写评估: ${dValue.format_evaluation}`);
              //     }
              //     if (dValue.confidence) {
              //       contentItems.push(`📊 置信度: ${dValue.confidence}`);
              //     }
              //     if (dValue.abnormality_eval) {
              //       contentItems.push(`🚨 异常评估: ${dValue.abnormality_eval}`);
              //     }

              //     for (let l = 0; l < contentItems.length; l++) {
              //       const isLastItem = l === contentItems.length - 1;
              //       resultText += `${dPrefix2}${isLastItem ? '└─' : '├─'} ${contentItems[l]}\n`;
              //     }
              //   }
              // }
            }
          }
          
          // 在每个T级版面后添加空行，除了最后一个
          if (!isLastT) {
            resultText += '\n';
          }
        }
      }
      
      // 添加结束标记
      resultText += '\n═══════════════════════════════════════\n';
      resultText += '📊 分析完成 | Generated by DMT Analysis System';

      // 更新图片描述为DMT分析结果
      this.imgClickedText = resultText;
      // 分页处理
      this.splitImgTextIntoPages();
    },

    base64ToBlob(base64String) {
      // 移除可能存在的data URL前缀
      const base64Data = base64String.replace(/^data:image\/[a-z]+;base64,/, '');
      
      try {
        // 将base64字符串转换为Blob对象
        const byteCharacters = atob(base64Data);
        const byteNumbers = new Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        const byteArray = new Uint8Array(byteNumbers);
        return new Blob([byteArray], { type: 'image/png' });
      } catch (error) {
        console.error('Base64转换失败:', error);
        throw new Error('图片数据格式无效');
      }
    },

    async regenerateImgDescription() {
      try {
        // 先检查是否有匹配的Excel配置文件
        const username = localStorage.getItem('userId');
        const imageName = this.curFileInfo.name || 'analysis_image.png';
        const imageBaseName = imageName.replace(/\.[^/.]+$/, "").split('_')[0];
        
        const BASE_URL = API_BASE_URL;
        const checkResponse = await fetch(`${BASE_URL}/api/check_dmt_config`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username: username,
            imageBaseName: imageBaseName
          })
        });
        
        const checkResult = await checkResponse.json();
        
        if (checkResult.hasConfig) {
          // 有匹配的配置文件，执行DMT化理解
          console.log('[DMT] 找到匹配的配置文件，执行DMT化理解');
          this.processDMTAnalysisWithConfig(checkResult.configFile);
        } else {
          // 没有匹配的配置文件，执行原有的图片描述生成逻辑，提示用户可能需要上传DMT Excel
          console.log('[图片描述] 未找到配置文件，执行普通图片描述生成');
          this.$message.warning('未找到匹配的DMT配置文件，默认普通的重做图片描述；若要强化图片分析请先上传Excel配置文件（文件名需以图片名开头）');
          this.generateNormalImgDescription();
        }
      } catch (error) {
        console.error('[regenerateImgDescription] 检查配置文件失败:', error);
        // 出错时执行原有的图片描述生成逻辑
        this.generateNormalImgDescription();
      }
    },

    generateNormalImgDescription() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('filename', this.curFileInfo.name);
      formData.append('imgid', this.imgClickedIndex);
      formData.append('content', '');

      // update_img_text(formData).then(data => {
      //   this.imgClickedText = data['content'];
      // }).then(() => {
      //   // 把imgClickedText发送后端，拿到相关关键词
      //   formData.append('imgtext', this.imgClickedText);
      //   img_getTopics(formData).then(data => {
      //     this.imgTopicContents = data['topics'];
      //   }).catch(error => {
      //     console.error("An error occurred:", error); // 错误处理
      //   });
      // }).catch(error => {
      //   console.error("An error occurred:", error); // 错误处理
      // });
      this.imgClickedText = '正在获取图片和描述';
      update_img_text_stream(formData).then(response => {
        const reader = response.body.getReader(); // 使用响应的ReadableStream来处理数据
        // 后端传回数据，显示
        const processStream = () => {
          const decoder = new TextDecoder('utf-8');
          reader.read().then(({done, value}) => {
            if (done) {
              console.log('Stream reading complete');
              this.$message.success('图片描述已更新');
              // 更新后端向量数据库
              formData.append('imgtext', this.imgClickedText);
              update_img_text(formData);
              // 把imgClickedText发送后端，拿到相关关键词
              img_getTopics(formData).then(data => {
                this.imgTopicContents = data['topics'];
              }).catch(error => {
                console.error("An error occurred:", error); // 错误处理
              });
              return;
            }
            console.log('Received chunk:', value);
            const resp = decoder.decode(value);
            // console.log('Processed chunk:', resp);
            let responseData;
            // 使用正则表达式匹配和提取每个独立的 JSON 对象
            const jsonObjects = resp.match(/{[\s\S]*?}(?=\s*{|$)/g);
            if (jsonObjects) {
              jsonObjects.forEach(jsonObject => {
                responseData = JSON.parse(jsonObject);
                // 处理解析后的 JSON 数据
                if(this.imgClickedText == '正在获取图片和描述') {
                  this.imgClickedText = '';
                }
                this.imgClickedText += responseData["content"];
                // 分页处理
                this.splitImgTextIntoPages();
                this.shouldScroll = true;
                // this.shouldScroll = true;
                setTimeout(() => {
                  const scrollDom = this.$refs.imgDialogText;
                  this.scrollBottom(scrollDom);
                }, 100); // 延迟100毫秒
              });
            } else {
              console.error('No JSON objects found in the stream:', resp);
              this.$message.error('出错，可尝试降低最大词数后重试，若再次出错，请联系管理员并暂勿使用此功能');
            }
            // 继续读取下一块数据
            processStream();
          })
        };
        processStream();
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    regenerateImgTopics() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('filename', this.curFileInfo.name);
      formData.append('imgid', this.imgClickedIndex);
      formData.append('imgtext', this.imgClickedText);

      img_getTopics(formData).then(data => {
        this.imgTopicContents = data['topics'];
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },

    // 改进两段式处理带图片的PDF文档
    handleImageClick(item, index, mode) {
      // 检查图片是否还在处理中
      if (this.isImageProcessing(index)) {
        this.$message.warning('图片还在处理中，请稍后再试');
        return;
      }
      // 如果不在处理中，正常打开图片对话框
      this.ImgDialog(item, index, mode);
    },
    
    isImageProcessing(index) {
      const fileName = this.curFileInfo.name;
      const status = this.pdfImageProcessingStatus[fileName];
      // return status && !status.is_processing_complete;
      // 如果状态不存在或者处理未完成，则显示处理中
      // return !status || !status.is_processing_complete;
      // 如果状态不存在，显示处理中
      if (!status) {
        return true;
      }
      
      // 如果处理完成，不显示处理中
      if (status.is_processing_complete) {
        return false;
      }
      
      // 如果还没有图片数据，显示处理中
      if (!this.imgContents || this.imgContents.length === 0) {
        return true;
      }

      // 根据已处理的图片数量判断当前图片是否还在处理中
      const processedCount = status.processed_image_count || 0;
      return index >= processedCount;
    },
    
    async checkPdfImageProcessingStatus(fileName) {
      // 检查是否是当前打开的文件，避免处理其他文件的状态
      if (this.curFileInfo.name !== fileName) {
        console.log(`跳过状态检查，当前文件是 ${this.curFileInfo.name}，不是 ${fileName}`);
        return;
      }

      try {
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取

        const response = await fetch(`${BASE_URL}/api/check_pdf_image_processing_status`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username: localStorage.getItem('userId'),
            docs_name: fileName
          })
        });
        
        const data = await response.json();
        if (data.error_num === 0) {
          const previousStatus = this.pdfImageProcessingStatus[fileName];

          this.pdfImageProcessingStatus[fileName] = {
            is_processing_complete: data.is_processing_complete,
            has_images: data.has_images,
            has_text_docs: data.has_text_docs,
            has_image_docs: data.has_image_docs,
            image_count: data.image_count || 0,
            processed_image_count: data.processed_image_count || 0
          };

          console.log(`[状态检查] ${fileName}: 图片总数=${data.image_count}, 已处理=${data.processed_image_count}, 完成=${data.is_processing_complete}`);
          
          // 检查是否有新的图片被处理完成
          const previousProcessedCount = previousStatus ? previousStatus.processed_image_count || 0 : 0;
          const currentProcessedCount = data.processed_image_count || 0;
          
          if (currentProcessedCount > previousProcessedCount) {
            console.log(`检测到图片处理进度更新: ${previousProcessedCount} -> ${currentProcessedCount}`);
            this.refreshFileImages(fileName);
          }

          // 如果图片状态发生变化，更新图片内容
          if (data.has_images && (!previousStatus || !previousStatus.has_images)) {
            console.log('检测到图片已处理，更新图片内容');
            this.refreshFileImages(fileName);
          }
          
          // 即使图片状态没有变化，也定期刷新以获取最新图片
          if (data.has_images && !data.is_processing_complete) {
            this.refreshFileImages(fileName);
          }

          // 如果处理未完成，也尝试获取图片（可能部分图片已处理）
          if (!data.is_processing_complete) {
            this.refreshFileImages(fileName);
          }
          
          // 如果处理完成，增加完成计数器
          if (data.is_processing_complete) {
            // 重新获取文件信息以更新图片内容
            this.refreshFileImages(fileName);
            
            // 增加完成计数器
            if (!this.pdfImageProcessingStatus[fileName].completed_count) {
              this.pdfImageProcessingStatus[fileName].completed_count = 0;
            }
            this.pdfImageProcessingStatus[fileName].completed_count++;
            
            console.log(`PDF图片处理完成 (${this.pdfImageProcessingStatus[fileName].completed_count}/3)`);
            
            // 连续3次检查都完成才停止
            if (this.pdfImageProcessingStatus[fileName].completed_count >= 3) {
              this.stopImageProcessingCheck();
              console.log('PDF图片处理确认完成，停止检查');
            }
          } else {
            // 如果未完成，重置计数器
            this.pdfImageProcessingStatus[fileName].completed_count = 0;
          }
        }
      } catch (error) {
        console.error('检查PDF图片处理状态失败:', error);
      }
    },
    
    startImageProcessingCheck(fileName) {
      this.stopImageProcessingCheck();

      // 初始化状态
      this.pdfImageProcessingStatus[fileName] = {
        is_processing_complete: false,
        has_images: false,
        has_text_docs: true,
        has_image_docs: false,
        completed_count: 0 // 添加完成计数器
      };
      
      // 🔥 3秒后先检查一次
      setTimeout(() => {
        this.checkPdfImageProcessingStatus(fileName);
      }, 3000);
      
      // 🔥 之后每15秒检查一次
      this.imageProcessingCheckInterval = setInterval(() => {
        this.checkPdfImageProcessingStatus(fileName);
      }, 15000);
    },
    
    stopImageProcessingCheck() {
      if (this.imageProcessingCheckInterval) {
        clearInterval(this.imageProcessingCheckInterval);
        this.imageProcessingCheckInterval = null;
      }
    },
    
    async refreshFileImages(fileName) {
      // 检查是否是当前打开的文件，避免更新其他文件的图片内容
      if (this.curFileInfo.name !== fileName) {
        console.log(`跳过更新，当前文件是 ${this.curFileInfo.name}，不是 ${fileName}`);
        return;
      }

      // 重新获取文件的图片信息
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('filename', fileName);
      formData.append('fileNameList', '');
      formData.append('leftSelectList', '');
      formData.append('rightSelectList', '');
      
      try {
        const data = await get_file_text(formData);
        if (data && data.images) {
          // this.imgContents = data.images;
          // this.curFileInfo.imgs = data.images;

          // // 更新处理状态为完成
          // if (this.pdfImageProcessingStatus[fileName]) {
          //   this.pdfImageProcessingStatus[fileName].is_processing_complete = true;
          //   this.pdfImageProcessingStatus[fileName].has_images = true;
          //   this.pdfImageProcessingStatus[fileName].has_image_docs = true;
          // }

          // 逐步更新图片内容，保留已处理的图片
          const newImages = data.images;
          const currentImages = this.imgContents || [];
          
          // 如果有新图片数据，更新图片内容
          if (newImages.length > 0) {
            // 如果新图片数量更多，则更新
            if (newImages.length >= currentImages.length) {
              this.imgContents = newImages;
              this.curFileInfo.imgs = newImages;
              console.log(`图片内容已更新，当前图片数量: ${newImages.length}`);
            }
            
            // 更新处理状态
            if (this.pdfImageProcessingStatus[fileName]) {
              this.pdfImageProcessingStatus[fileName].has_images = true;
              this.pdfImageProcessingStatus[fileName].has_image_docs = true;
              
              // 如果所有图片都处理完成，标记为完成
              if (newImages.length > 0) {
                this.pdfImageProcessingStatus[fileName].is_processing_complete = true;
              }
            }
          } else {
            // 如果后端还没有图片，根据状态信息创建或调整占位图片
            const status = this.pdfImageProcessingStatus[fileName];
            const expectedImageCount = status ? status.image_count : 0;
            
            if (expectedImageCount > 0) {
              // 根据预期的图片数量创建占位图片
              this.createPdfPlaceholderImagesWithCount(fileName, expectedImageCount);
              console.log(`根据后端状态创建了 ${expectedImageCount} 个占位图片`);
            } else {
              // 如果不知道图片数量，保持默认占位图片
              console.log('后端还没有图片，保持占位图片');
              if (!this.imgContents || this.imgContents.length === 0) {
                this.createPdfPlaceholderImages(fileName);
              }
            }
          }
        } else {
          // 如果后端还没有图片，保持占位图片
          console.log('后端还没有图片，保持占位图片');
        }
      } catch (error) {
        console.error('刷新文件图片失败:', error);
      }
    },

    createPdfPlaceholderImages(fileName) {
      // 为PDF文件创建占位图片缩略图
      // 这里我们创建一个简单的占位图片，实际应该从PDF中提取缩略图
      const placeholderImages = [];
      const placeholderCount = 12; // 假设PDF有12张图片，实际应该从PDF获取
      
      for (let i = 0; i < placeholderCount; i++) {
        // 创建一个更美观的占位图片
        const canvas = document.createElement('canvas');
        canvas.width = 100;
        canvas.height = 100;
        const ctx = canvas.getContext('2d');
        
        // 背景渐变
        const gradient = ctx.createLinearGradient(0, 0, 100, 100);
        gradient.addColorStop(0, '#f8f9fa');
        gradient.addColorStop(1, '#e9ecef');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 100, 100);
        
        // 边框
        ctx.strokeStyle = '#dee2e6';
        ctx.lineWidth = 2;
        ctx.strokeRect(1, 1, 98, 98);
        
        // 图标（简单的文档图标）
        ctx.fillStyle = '#6c757d';
        ctx.font = 'bold 24px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('📄', 50, 35);
        
        // 文字
        ctx.fillStyle = '#495057';
        ctx.font = '10px Arial';
        ctx.fillText(`图片${i+1}`, 50, 55);
        ctx.fillText('处理中...', 50, 70);
        
        // 转换为base64
        const base64 = canvas.toDataURL('image/png').split(',')[1];
        placeholderImages.push(base64);
      }
      
      this.imgContents = placeholderImages;
      this.curFileInfo.imgs = placeholderImages;
      
      // 初始化PDF图片处理状态
      this.pdfImageProcessingStatus[fileName] = {
        is_processing_complete: false,
        has_images: false,
        has_text_docs: true,
        has_image_docs: false
      };
      
      console.log(`为PDF文件 ${fileName} 创建了 ${placeholderCount} 个占位图片`);
    },

    createPdfPlaceholderImagesWithCount(fileName, imageCount) {
      // 根据实际图片数量创建占位图片
      const placeholderImages = [];
      
      for (let i = 0; i < imageCount; i++) {
        // 创建一个更美观的占位图片
        const canvas = document.createElement('canvas');
        canvas.width = 100;
        canvas.height = 100;
        const ctx = canvas.getContext('2d');
        
        // 背景渐变
        const gradient = ctx.createLinearGradient(0, 0, 100, 100);
        gradient.addColorStop(0, '#f8f9fa');
        gradient.addColorStop(1, '#e9ecef');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, 100, 100);
        
        // 边框
        ctx.strokeStyle = '#dee2e6';
        ctx.lineWidth = 2;
        ctx.strokeRect(1, 1, 98, 98);
        
        // 图标（简单的文档图标）
        ctx.fillStyle = '#6c757d';
        ctx.font = 'bold 24px Arial';
        ctx.textAlign = 'center';
        ctx.fillText('📄', 50, 35);
        
        // 文字
        ctx.fillStyle = '#495057';
        ctx.font = '10px Arial';
        ctx.fillText(`图片${i+1}`, 50, 55);
        ctx.fillText('处理中...', 50, 70);
        
        // 转换为base64
        const base64 = canvas.toDataURL('image/png').split(',')[1];
        placeholderImages.push(base64);
      }
      
      this.imgContents = placeholderImages;
      this.curFileInfo.imgs = placeholderImages;
      
      // 初始化PDF图片处理状态
      this.pdfImageProcessingStatus[fileName] = {
        is_processing_complete: false,
        has_images: false,
        has_text_docs: true,
        has_image_docs: false,
        image_count: imageCount,
        processed_image_count: 0
      };
      
      console.log(`为PDF文件 ${fileName} 创建了 ${imageCount} 个占位图片`);
    },
    
    updatePdfImages(actualImages) {
      // 更新PDF图片内容，替换占位图片
      if (actualImages && actualImages.length > 0) {
        // this.imgContents = actualImages;
        // this.curFileInfo.imgs = actualImages;
        // console.log('PDF图片内容已更新');

        // 逐步更新图片，保留已处理的图片
        const currentImages = this.imgContents || [];
        if (actualImages.length >= currentImages.length) {
          this.imgContents = actualImages;
          this.curFileInfo.imgs = actualImages;
          console.log(`PDF图片内容已更新，当前图片数量: ${actualImages.length}`);
        }
      }
    },


    ImgDialog(clickedItem, index, mode) {
      this.imgClicked = clickedItem; // 把点击的img存起来
      this.imgClickedIndex = index; // 点击的图片的index
      this.showImg();

      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      formData.append('realName', localStorage.getItem('realName'));
      formData.append('filename', this.curFileInfo.name);
      formData.append('imgid', index);
      formData.append('mode', mode);

      get_img_text(formData).then(data => {
        if (data['result_type'] === 'dmt_analysis') {
          // 显示分析结果
          this.showDMTResult(data['content']);
        } else if (data['result_type'] === 'pdf_image_sum') {
          let description = data['content']; // 获取原始描述
          const prefix = "文件中的一张图片，内容为";
          if (description && description.includes(prefix)) {
            // 如果包含前缀，则截取前缀之后的部分并去除首尾空格
            this.imgClickedText = description.substring(description.indexOf(prefix) + prefix.length).trim();
          } else {
            // 否则，使用原始描述
            this.imgClickedText = description;
          }
          // 分页处理
          this.splitImgTextIntoPages();
        }

        // 查看有无HLScore
        if (data.hasOwnProperty('HLScore')) {
          console.log("接收到图片HLScore评分:", data['HLScore']);
          // 在这里添加对HLScore的处理逻辑
          // 提取分数和颜色并显示
          try {
            // HLScore的格式类似: "3.5_紫色_具体理由和建议"
            const hlScoreParts = data['HLScore'].split('_');
            if (hlScoreParts.length >= 2) {
              this.imgHLScore = hlScoreParts[0]; // 分数部分
              this.imgHLColor = hlScoreParts[1]; // 颜色部分
              
              // 如果有第三部分(理由和建议)
              if (hlScoreParts.length >= 3) {
                this.imgHLReason = hlScoreParts.slice(2).join('_'); // 理由和建议部分，这样处理是为了包含此部分本身可能包含_的情况
              }
            }
          } catch (e) {
            console.error("解析HLScore出错:", e);
          }
        } else {
          // 如果没有返回HLScore字段，重置相关状态
          console.log("未接收到HLScore评分");
          this.imgHLScore = null;
          this.imgHLColor = null;
          this.imgHLReason = null;
        }
      }).then(() => {
        // 把imgClickedText发送后端，拿到相关关键词
        // formData.append('imgtext', truncatedText);
        formData.append('imgtext', this.imgClickedText);
        img_getTopics(formData).then(data => {
          this.imgTopicContents = data['topics'];
        }).catch(error => {
          console.error("An error occurred:", error); // 错误处理
        });
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });

      // this.imgClicked = clickedItem; // 把点击的img存起来
      // this.imgClickedIndex = index; // 点击的图片的index
      // this.showImg();
    },
    addfile(event) {
      const files = event.target.files;
      if (!files || !files.length) {
        return;
      }
      this.$refs.ChatWindow.sendFile(event);
      const userId = localStorage.getItem('userId');
      for (let i = 0; i < files.length; i++) {
        const filePath = files[i].name;
        var url = `${API_BASE_URL}/api/pdf/?url=${encodeURIComponent(filePath)}&userbook=${encodeURIComponent(userId)}`;
        this.removeFileFromCache(url);
        var transUrl = `${API_BASE_URL}/api/pdf/?url=${encodeURIComponent(filePath)}&userbook=${encodeURIComponent(userId)}&sceneName=${encodeURIComponent(this.sceneName + "_result")}`;
        this.removeFileFromCache(transUrl);
      }
    },

    handlePdfUploaded(fileName) {
      // PDF文件上传完成，开始图片处理状态检查
      console.log(`PDF文件 ${fileName} 上传完成，开始图片处理状态检查`);
      // this.startImageProcessingCheck(fileName);
      // 如果当前打开的是这个PDF文件，立即开始检查
      if (this.curFileInfo.name === fileName) {
        this.startImageProcessingCheck(fileName);
      }
    },

    cleanupPreviousFileState() {
      // 停止当前文件的图片处理检查
      this.stopImageProcessingCheck();
      
      // 清空图片内容
      this.imgContents = [];
      this.curFileInfo.imgs = [];
      
      // 清空当前文件的图片处理状态
      if (this.curFileInfo.name) {
        delete this.pdfImageProcessingStatus[this.curFileInfo.name];
      }
      
      console.log('已清理之前文件的状态和图片内容');
    },

    async handleFileSummaryUpdate(filename, fileNameList, leftSelectList, rightSelectList) {
      this.isTransPdfReady = false  // 每次点击新的文件卡片打开前，默认为翻译文档没准备好，等后续查验

      // 点开某个文件将执行此函数
      let formData = new FormData();
      // formData.append('username', 'admin');
      var userId = localStorage.getItem('userId');
      formData.append('username', userId);
      formData.append('filename', filename);
      formData.append('fileNameList', fileNameList);
      formData.append('leftSelectList', leftSelectList);
      formData.append('rightSelectList', rightSelectList);
      this.fileName = filename
      this.curFileInfo.name = filename;

      // // ── CI：单图点击处理 ─────────────────────────────────────
      // this._queryCIForSingleClick(filename);

      console.log('file clicked', new Date().toISOString());
      var url = encodeURIComponent(filename) + "&userbook=" + encodeURIComponent(userId);
      if (filename.endsWith('.png') || filename.endsWith('.jpg') || filename.endsWith('.jpeg')) {
        this.isLoadingImg = true;
        // 如果是图片文件，先检查内存缓存
        if (url in this.bufferBlobUrls) {
          console.log('从内存缓存获取图片:', url);
          this.ImgDialog(this.bufferBlobUrls[url], 0, 'img')
          return;
        }
        // 如果内存缓存没有，尝试从本地缓存获取
        try {
          const cachedBlob = await this.getFileFromCache(url, userId);
          if (cachedBlob) {
            // 从缓存获取到了文件
            this.ImgDialog(cachedBlob, 0, 'img');
            // 存储到内存缓存
            this.bufferBlobUrls[url] = cachedBlob;
            return;
          }
        } catch (error) {
          console.error('从本地缓存获取文件失败:', error);
        }
      }
      // 切换到PDF文件视图
      if (!filename.endsWith('.png') && !filename.endsWith('.jpg') && !filename.endsWith('.jpeg')) {
        this.updateModule(1); 
      
        // 这里如果要双语对比阅读，将有2个iframe并排显示，如果不先拉伸，位置不足，iframe宽度过小，将显示不出工具栏（工具栏里图标摆不下）
        if(filename.endsWith('.pdf') && (this.subSceneName === "中英对比阅读") || this.sceneName.includes("中英文专业阅读")) {
          this.$nextTick(() => {
            // 确保 DOM 已经更新
            this.flexBtnChecked = !this.flexBtnChecked
            var main_right_container = document.querySelector('.main-right');
            var text_container = document.querySelector('.main-left2');
            // var input_btn_container = document.querySelector('.chat-choose-boxup');

            text_container.style.width = '70%';
            main_right_container.style.width = '30%';
            // input_btn_container.style.display = 'none';
            text_container.style.transition = '0.5s ease';
            main_right_container.style.transition = '0.5s ease';
            // input_btn_container.style.transition = '0.5s ease';
            this.leftPdfViewMode = 1
          });
        }
      }

      // 音频文件：显示播放条
      const currentLowerFilename = filename.toLowerCase();
      const isAudioCard = ['.mp3', '.wav', '.ogg', '.m4a', '.aac', '.flac', '.webm']
        .some(ext => currentLowerFilename.endsWith(ext));
      if (isAudioCard) {
        await this.openAudio(filename, userId);
      }

      // openPDF挪到这里执行，点击文件卡片就会执行到这里，显示完整PDF内容在左下部分
      if(filename.endsWith('.pdf')) {
        this.openPDF(filename);
        let hasCachedImages = false;

        if(url in this.bufferBlobUrls) {
          console.log('从内存缓存获取PDF中的图片:', url);
          this.imgContents = this.bufferBlobUrls[url];
          this.curFileInfo.imgs = this.imgContents;
          // 检查缓存内容是否有效
          if (this.imgContents && this.imgContents.length > 0) {
            console.log('内存缓存有效，使用缓存图片');
            hasCachedImages = true;
          } else {
            console.log('内存缓存为空，继续从服务器获取');
          }
        }

        // 如果内存缓存没有，尝试从本地缓存获取
        // try {
        //   let i = 0;
        //   let cachedImages = [];
        //   while (true) {
        //     const cachedBlob = await this.getFileFromCache(url + `_${i}`, userId);
        //     if (cachedBlob) {
        //       // 从缓存获取到了文件
        //       cachedImages.push(cachedBlob);
        //       i++;
        //     } else {
        //       break; // 没有更多缓存了
        //     }
        //   }
        //   if (cachedImages.length > 0) {
        //     console.log('从本地缓存获取PDF中的图片:', cachedImages);
        //     // 存储到内存缓存
        //     this.bufferBlobUrls[url] = cachedImages;
        //     this.curFileInfo.imgs = cachedImages;
        //     this.imgContents = cachedImages;
        //     return;
        //   } else {
        //     console.log('本地缓存为空，继续从服务器获取');
        //   }
        // } catch (error) {
        //   console.error('从本地缓存获取文件失败:', error);
        // }
        if (!hasCachedImages) {
          try {
            let i = 0;
            let cachedImages = [];
            while (true) {
              const cachedBlob = await this.getFileFromCache(url + `_${i}`, userId);
              if (cachedBlob) {
                // 从缓存获取到了文件
                cachedImages.push(cachedBlob);
                i++;
              } else {
                break; // 没有更多缓存了
              }
            }
            if (cachedImages.length > 0) {
              console.log('从本地缓存获取PDF中的图片:', cachedImages);
              // 存储到内存缓存
              this.bufferBlobUrls[url] = cachedImages;
              this.curFileInfo.imgs = cachedImages;
              this.imgContents = cachedImages;
              hasCachedImages = true;
            } else {
              console.log('本地缓存为空，继续从服务器获取');
            }
          } catch (error) {
            console.error('从本地缓存获取文件失败:', error);
          }
        }
        
        // 无论是否有缓存，都要检查图片处理状态
        if (hasCachedImages) {
          // 有缓存图片，先显示占位图片，然后开始检查状态
          this.createPdfPlaceholderImages(filename);
          this.startImageProcessingCheck(filename);
        } else {
          // 没有缓存，创建占位图片并开始检查
          this.createPdfPlaceholderImages(filename);
          this.startImageProcessingCheck(filename);
        }
      }

      // // 对于PDF文件，先显示占位图片缩略图
      // if(filename.endsWith('.pdf')) {
      //   // 为PDF文件创建占位图片缩略图
      //   this.createPdfPlaceholderImages(filename);
      //   // 开始检查图片处理状态
      //   this.startImageProcessingCheck(filename);
      // }

      // 失败时继续从服务器获取
      get_file_text(formData).then(data => {
        this.curFileInfo.text = data['text'];
        this.curFileInfo.imgs = data['images'];

        // this.imgContents = this.curFileInfo.imgs;
        // 对于PDF文件，只有在有真实图片数据时才更新imgContents
        if (filename.endsWith('.pdf')) {
          if (data['images'] && data['images'].length > 0) {
            this.imgContents = data['images'];
            console.log('PDF文件获取到真实图片，更新imgContents');
          } else {
            console.log('PDF文件暂无真实图片，保持占位图片');
          }
        } else {
          this.imgContents = this.curFileInfo.imgs;
        }
        // this.curFileInfo.name = filename;
        
        if(filename.endsWith('.txt')) {
          this.openTXT(filename)
        } else if(this.curFileInfo.name.endsWith('.png') || this.curFileInfo.name.endsWith('.jpg') || this.curFileInfo.name.endsWith('.jpeg')) {
          // 存储到内存缓存
          this.bufferBlobUrls[url] = this.imgContents[0];
          // 存储到IndexedDB
          this.saveFileToCache(url, this.imgContents[0], userId, 'img');
          this.ImgDialog(this.imgContents[0], 0, 'img')
        } else if(filename.endsWith('.pdf')) {
          // 存储PDF中的图片到内存缓存
          this.bufferBlobUrls[url] = this.curFileInfo.imgs;
          // 存储到IndexedDB
          for (let i = 0; i < this.curFileInfo.imgs.length; i++) {
            this.saveFileToCache(url + `_${i}`, this.curFileInfo.imgs[i], userId, 'img');
          }

          // 更新PDF图片内容
          this.updatePdfImages(this.curFileInfo.imgs);
        }

        // // 继续获取summary和topic
        // get_file(formData).then(data => {
        //   this.topicContents = data['topic'];
        //   this.curFileInfo.name = filename;
        //   // 这个content是摘要，不是文本
        //   this.curFileInfo.content = data['content'];
        //   // this.updateModule(1); // 切换到文件视图 
        // }).catch(error => {
        //   console.error("An error occurred:", error); // 错误处理
        // });
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    handleFileLeftSelectUpdate(index, leftSelect) {
      console.log(index, leftSelect);
    },
    handleFileRightSelectUpdate(index, rightSelect) {
      console.log(index, rightSelect);
    },
    selectall() {
      console.log('selectall clicked');
      let unclicked = this.selectAllClass === 'left-selectall-button';
      if (unclicked) {  // 还没有全选，这时候全选
        this.selectAllClass = 'left-selectall-button-clicked';
        // TODO:把所有文件都选中
      }
      else {
        this.selectAllClass = 'left-selectall-button';
        // TODO:把所有文件都不选中
      }
    },
    topicDialog(clickedItem) {
      // 半自动化新增
      this.recordOperation('topic_click', {
        topicClicked: clickedItem,
        topicRelText: this.curFileInfo.content
      });

      this.topicClicked = clickedItem; // 把点击的topic存起来
      this.topicRelText = this.curFileInfo.content;
      this.showTopic();
    },
    discussTopic() {
      this.inputMsg = "请进一步讨论：" + this.topicClicked;
      this.sendMsg();
      this.backtoDefault();
      this.hideTopicDialog();
      this.hideImgDialog();
      this.$message.success('递进讨论话题');
    },
    illustrateTopic() {
      this.inputMsg = "请解释这个关键词：" + this.topicClicked;
      this.sendMsg();
      this.backtoDefault();
      this.hideTopicDialog();
      this.hideImgDialog();
      this.$message.success('给出建议');
    },
    updateModule(newModule) {
      console.log(newModule);
      this.currentModule = newModule;
    },
    updateStyle(newStyle) {
      this.currentStyle = newStyle;
    },
    handleCase4() {
      this.dialogVisible = true
    },
    handleCustomEvent(data) {
      this.currentModule = data;
      console.log('module_id:' + this.currentModule);
    },
    handleImportImagePool(list) {
      this.importAreaImagePool = Array.isArray(list) ? [...list] : []
    },
    handleFileList(data, leftSelectList, rightSelectList) {
      this.fileNameList = data;
      this.leftSelectList = leftSelectList;
      this.rightSelectList = rightSelectList;
      console.log('[mainpage]handleFileList');
      console.log(this.fileNameList);
      console.log(this.leftSelectList);
      console.log(this.rightSelectList);

      // // ── CI：多图勾选处理 ─────────────────────────────────────
      // this._handleCIMultiImageChecked(this._ciImageFiles);
    },

    // ====== 连续图片认知理解（新架构）======

    /** 判断是否为图片/PDF 文件 */
    _isImageOrPdf(filename) {
      if (!filename) return false
      const lower = filename.toLowerCase()
      const imgExts = ['.png', '.jpg', '.jpeg', '.bmp', '.webp', '.tiff']
      return lower.endsWith('.pdf') || imgExts.some(e => lower.endsWith(e))
    },

    _normalizeCIFileName(filename) {
      return (filename || '').trim().toLowerCase()
    },

    _isSameCIFile(left, right) {
      return this._normalizeCIFileName(left) === this._normalizeCIFileName(right)
    },

    _ciFileListContains(files, filename) {
      const target = this._normalizeCIFileName(filename)
      return (files || []).some(file => this._normalizeCIFileName(file) === target)
    },

    _ciSelectedTargetFiles() {
      const seen = new Set()
      const targets = []
      for (const name of (this.fileNameList || [])) {
        const key = this._normalizeCIFileName(name)
        if (!key || seen.has(key) || !this._isImageOrPdf(name)) continue
        seen.add(key)
        targets.push(name)
      }
      return targets
    },

    _ciSelectedContextDocs(analysisFiles = []) {
      const analysisSet = new Set((analysisFiles || []).map(name => this._normalizeCIFileName(name)))
      const seen = new Set()
      const contextDocs = []
      for (const name of (this.fileNameList || [])) {
        const key = this._normalizeCIFileName(name)
        if (!key || seen.has(key) || analysisSet.has(key) || this._isImageOrPdf(name)) continue
        seen.add(key)
        contextDocs.push(name)
      }
      return contextDocs
    },

    _findCompletedSingleForFile(records, filename, preferredAnalysisType = '') {
      const matches = (records || []).filter(record =>
        record?.status === 'completed' && this._ciFileListContains(record.files || [], filename)
      )
      if (preferredAnalysisType) {
        const preferred = matches.find(record => record.analysis_type === preferredAnalysisType)
        if (preferred) return preferred
      }
      return matches[0] || null
    },

    /** 按文件查找任意 CI 单图记录（优先 completed，用于右键原草图直出 R） */
    _findSingleRecordForFile(records, filename, preferredAnalysisType = '') {
      const matches = (records || []).filter(record =>
        record?.analysis_id && this._ciFileListContains(record.files || [], filename)
      )
      if (!matches.length) return null
      const completed = matches.filter(record => record.status === 'completed')
      const pool = completed.length ? completed : matches
      if (preferredAnalysisType) {
        const preferred = pool.find(record => record.analysis_type === preferredAnalysisType)
        if (preferred) return preferred
      }
      return pool[0] || null
    },

    _findCompletedGroupForFiles(records, targetFiles, supersetMatch) {
      const targetSet = new Set((targetFiles || []).map(file => this._normalizeCIFileName(file)))
      const exact = (records || []).find(record => {
        if (record?.status !== 'completed' || !Array.isArray(record.files)) return false
        const recordSet = new Set(record.files.map(file => this._normalizeCIFileName(file)))
        return recordSet.size === targetSet.size && [...targetSet].every(file => recordSet.has(file))
      })
      if (exact) return exact
      return supersetMatch?.status === 'completed' ? supersetMatch : null
    },

    _setCIAvailableAnalyses(singleRecord, groupRecord) {
      this.ciAvailableAnalyses = {
        singles: singleRecord ? [singleRecord] : [],
        groups: groupRecord ? [groupRecord] : [],
      }
    },

    async _openCIExistingResult(analysisId, username, singleRecord = null, groupRecord = null) {
      if (!analysisId) return
      this._setCIAvailableAnalyses(singleRecord, groupRecord)
      this.showContinuousImagePanel = true
      await this._loadCIResult(analysisId, username)
    },

    async _getCIPdfHint(files, username, singleMode = false) {
      const pdfFiles = (files || []).filter(file => this._normalizeCIFileName(file).endsWith('.pdf'))
      if (!pdfFiles.length) return ''
      if (singleMode && pdfFiles.length === 1) {
        let pageCount = 0
        try {
          const pcResp = await getCIPdfPageCount({ username, filename: pdfFiles[0] })
          if (pcResp.error_num === 0) pageCount = pcResp.page_count || 0
        } catch (_) { /* 查询页数失败不阻断 */ }
        return pageCount > 0
          ? `该PDF共 ${pageCount} 页，每页将单独进行OCR识别与AI分析。\n\n`
          : '该PDF将按页展开，每页单独进行OCR识别与AI分析。\n\n'
      }

      const counts = await Promise.all(pdfFiles.map(async file => {
        try {
          const resp = await getCIPdfPageCount({ username, filename: file })
          return resp.error_num === 0 ? (resp.page_count || 1) : 1
        } catch (_) {
          return 1
        }
      }))
      const totalPages = counts.reduce((sum, count) => sum + count, 0)
      return `\n（含 ${pdfFiles.length} 个PDF共 ${totalPages} 页，每页将单独分析）`
    },

    async _confirmCIAction(message, title, confirmButtonText, cancelButtonText) {
      try {
        await ElMessageBox.confirm(message, title, {
          confirmButtonText,
          cancelButtonText,
          distinguishCancelAndClose: true,
          type: 'info',
        })
        return 'confirm'
      } catch (action) {
        return action === 'cancel' ? 'cancel' : 'close'
      }
    },

    _findHomeworkRecordForFile(records, filename, preferredAnalysisType = 'homework_grading') {
      const matches = (records || []).filter(record =>
        record?.analysis_id
        && this._ciFileListContains(record.files || [], filename)
        && (!preferredAnalysisType || record.analysis_type === preferredAnalysisType)
      )
      if (!matches.length) return null
      const rank = { completed: 3, partial: 2, running: 1, failed: 0 }
      return [...matches].sort((a, b) => (rank[b.status] || 0) - (rank[a.status] || 0))[0]
    },

    _isHomeworkStageReadyFromManifest(manifest, mode = 'grading') {
      const stages = manifest?.stages || {}
      if (stages[mode] === 'done') return true
      return mode === 'grading' && manifest?.status === 'completed'
    },

    openFeedbackMaterial(target = 'grading', selectedFilename = '') {
      const filename = (selectedFilename || this.curFileInfo?.name || '').trim()
      if (!filename.toLowerCase().endsWith('.pdf')) return
      if (this.ciRunningTask && !this.ciRunningTask.completed) {
        this.$message.warning('当前任务仍在运行，请完成后再启动下一份材料')
        return
      }
      this.ciMaterialFilename = filename
      this.ciMaterialUsername = localStorage.getItem('userId') || ''
      this.ciMaterialTarget = target
      this.ciMaterialInitialContext = null
      this.ciMaterialRerunId = ''
      this.ciMaterialVisible = true
    },

    async submitFeedbackMaterial(material) {
      this.ciMaterialSubmitting = true
      try {
        const response = await feedbackMaterialSettings({ username: this.ciMaterialUsername,
          files: [this.ciMaterialFilename], save: true, material })
        if (response?.error_num === 0) {
          this.ciMaterialVisible = false
          this.$message.success('材料设置已保存')
          if (this.curFileInfo?.name === this.ciMaterialFilename) await this._refreshHomeworkToolbarReady(this.ciMaterialFilename)
        } else this.$message.error(response?.msg || '材料设置保存失败')
      } finally { this.ciMaterialSubmitting = false }
    },

    async startExplicitUnderstanding() {
      const filename = (this.curFileInfo?.name || '').trim()
      if (!filename) return
      if (this.ciRunningTask && !this.ciRunningTask.completed) {
        this.$message.warning('当前任务仍在运行，请稍后再启动')
        return
      }
      await this._startCIAnalysis([filename], 'single', localStorage.getItem('userId'), { requestedAction: 'understanding' })
    },

    async _openHomeworkPageViewMode(mode = 'grading') {
      this.ciHomeworkPageViewOnly = mode === 'layout' || mode === 'understanding'
      this.showContinuousImagePanel = true
      await this.$nextTick()
      await this.$nextTick()
      const panel = this.$refs.homeworkGradingPanelRef
      if (panel?.openPageViewAt) {
        panel.openPageViewAt(0, mode)
      } else {
        this.ciHomeworkPageViewOnly = false
        this.$message.warning('批改面板尚未就绪，请稍后再试')
      }
    },

    async handleOpenHomeworkPageView(mode = 'grading') {
      const filename = (this.curFileInfo?.name || '').trim()
      if (!filename || !this._isImageOrPdf(filename)) return
      const username = localStorage.getItem('userId')
      if (!username) return

      try {
        const files = this.ciActiveResult?.manifest?.selected_files || []
        const activeMatches = this.ciActiveResult?.analysis_type === 'homework_grading'
          && files.includes(filename)
        let record = null
        if (activeMatches) {
          if (this._isHomeworkStageReadyFromManifest(this.ciActiveResult?.manifest, mode)) {
            await this._openHomeworkPageViewMode(mode)
            return
          }
          this.showContinuousImagePanel = true
          this.$message.info('已打开已有结果；该阶段尚未完成，如需重新处理请使用迭代')
          return
        }

        const resp = await queryCIAnalyses({ username, files: [filename], scene_name: this.sceneName })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '查询作业批改记录失败')
          return
        }
        record = this._findHomeworkRecordForFile(resp.singles, filename, 'homework_grading')

        if (record?.status === 'running') {
          const active = this.ciRunningTask?.analysis_id === record.analysis_id && !this.ciRunningTask?.completed
          if (active) {
            this.$message.warning('作业批改进行中，请稍候')
            return
          }
        }

        if (record?.analysis_id) {
          const resultResp = await getCIResult({ username, analysis_id: record.analysis_id })
          if (resultResp.error_num === 0 && this._isHomeworkStageReadyFromManifest(resultResp.manifest, mode)) {
            await this._openCIExistingResult(record.analysis_id, username, record, null)
            await this._openHomeworkPageViewMode(mode)
            return
          }
          if (resultResp.error_num === 0) {
            await this._openCIExistingResult(record.analysis_id, username, record, null)
            this.showContinuousImagePanel = true
            this.$message.info('已打开已有结果；该阶段尚未完成，如需重新处理请使用迭代')
          } else this.$message.error(resultResp.msg || '旧结果读取失败，未启动重做')
          return
        }

        const settings = await feedbackMaterialSettings({ username, files: [filename] })
        if (settings.error_num !== 0) { this.$message.error(settings.msg); return }
        if (!settings.feedback_eligible || (!settings.material_saved && settings.parse_status !== 'parsed')) {
          this.$message.info('请右键点击PDF文件卡片，保存材料设置后再操作')
          return
        }
        this.ciHomeworkPendingPageView = mode
        await this._startCIAnalysis([filename], 'single', username, {
          requestedAction: 'grading', material: settings.material, homeworkTargetStage: mode,
        })
      } catch (e) {
        console.error('[CI] handleOpenHomeworkPageView error:', e)
        this.$message.error('打开作业批改视图失败')
      }
    },

    async _refreshHomeworkToolbarReady(filename) {
      const name = (filename || this.curFileInfo?.name || '').trim()
      if (!name || !this._isImageOrPdf(name)) {
        this.ciHomeworkToolbarReady = false
        this.ciHomeworkToolbarFilename = ''
        return
      }
      const username = localStorage.getItem('userId')
      if (!username) {
        this.ciHomeworkToolbarReady = false
        return
      }
      try {
        const resp = await feedbackMaterialSettings({ username, files: [name] })
        if (resp.error_num !== 0) {
          this.ciHomeworkToolbarReady = false
          return
        }
        const records = await queryCIAnalyses({ username, files: [name], scene_name: this.sceneName })
        const existing = records.error_num === 0 && this._findHomeworkRecordForFile(records.singles, name, 'homework_grading')
        const isHomework = !!existing || (resp.feedback_eligible && (resp.material_saved || resp.parse_status === 'parsed'))
        this.ciHomeworkToolbarReady = isHomework
        this.ciHomeworkToolbarFilename = name
      } catch (e) {
        console.warn('[CI] _refreshHomeworkToolbarReady error:', e)
        this.ciHomeworkToolbarReady = false
      }
    },

    async handleCIDocumentPreviewDoubleClick(filename) {
      const currentFile = (filename || this.curFileInfo?.name || '').trim()
      if (!this._isImageOrPdf(currentFile)) return
      const username = localStorage.getItem('userId')
      if (!username) return

      try {
        const selectedTargets = this._ciSelectedTargetFiles()
        if (selectedTargets.length >= 2) {
          if (!this._ciFileListContains(selectedTargets, currentFile)) {
            this.$message.info('当前文档不在已勾选的图片/PDF组合中，请先勾选该文档后再触发图片理解')
            return
          }
        }

        this._resetCIState()

        if (selectedTargets.length >= 2) {
          await this._handleCIExplicitMultiTrigger(currentFile, selectedTargets, username)
        } else {
          await this._handleCIExplicitSingleTrigger(currentFile, username)
        }
      } catch (e) {
        console.error('[CI] handleCIDocumentPreviewDoubleClick error:', e)
      }
    },

    /** 查看图片标题右键：原草图直出 R 层复现图，完成后打开单图迭代工作区（已有 R 则直接打开；无需先双击理解） */
    async handleCIDocumentPreviewRightClick(filename) {
      const currentFile = (filename || this.curFileInfo?.name || '').trim()
      if (!this._isImageOrPdf(currentFile)) return
      const username = localStorage.getItem('userId')
      if (!username) return

      try {
        const resp = await queryCIAnalyses({ username, files: [currentFile], scene_name: this.sceneName })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '查询图片理解记录失败')
          return
        }

        const isHomework = resp.homework_status?.analysis_type === 'homework_grading'
        const preferredType = isHomework ? 'homework_grading' : ''
        const singleRecord = this._findSingleRecordForFile(resp.singles, currentFile, preferredType)

        if (!singleRecord?.analysis_id) {
          await this._startCISketchRQuickstartTask(currentFile, username)
          return
        }

        const analysisId = singleRecord.analysis_id
        if (
          this.ciRunningTask?.analysis_id === analysisId
          && !this.ciRunningTask?.completed
        ) {
          this.$message.warning('该文档的复现图任务进行中，请稍候')
          return
        }

        await this._openCIExistingResult(analysisId, username, singleRecord, null)

        if (this._ciHasReadyReproduction(this.ciActiveResult)) {
          await this.$nextTick()
          this._signalOpenCISingleWorkArea(analysisId)
          return
        }

        await this._startCIReproductionTask(analysisId, username, false, true, true)
      } catch (e) {
        console.error('[CI] handleCIDocumentPreviewRightClick error:', e)
      }
    },

    openBatchSketchRDialog() {
      const pool = Array.isArray(this.importAreaImagePool) ? [...this.importAreaImagePool] : []
      if (!pool.length) {
        this.$message.warning('文档导入区暂无图片文件')
        return
      }
      this.ciBatchSketchRCandidates = pool
      this.ciBatchSketchRSelected = [...pool]
      this.ciBatchSketchRDialogVisible = true
    },

    ciBatchSketchRSelectAll() {
      this.ciBatchSketchRSelected = [...this.ciBatchSketchRCandidates]
    },

    ciBatchSketchRClearAll() {
      this.ciBatchSketchRSelected = []
    },

    async confirmBatchSketchR() {
      const files = [...(this.ciBatchSketchRSelected || [])].filter(Boolean)
      if (!files.length) {
        this.$message.warning('请至少选择一张图片')
        return
      }
      if (this.ciBatchSketchR.running || this.ciAnalysisRunning) {
        this.$message.warning('已有图片任务进行中，请稍候')
        return
      }
      this.ciBatchSketchR.running = true
      this.ciBatchSketchR.total = files.length
      this.ciBatchSketchR.current = 0
      this.ciBatchSketchR.done = 0
      this.ciBatchSketchR.failed = 0
      this.ciBatchSketchR.skipped = 0
      this.ciSuppressAutoOpenWorkArea = true
      this.ciSuppressOpenCIPanelOnComplete = true
      const username = localStorage.getItem('userId')
      try {
        for (let i = 0; i < files.length; i++) {
          const file = files[i]
          this.ciBatchSketchR.current = i + 1
          this.ciBatchSketchR.currentFile = file
          try {
            const outcome = await this._processBatchSketchRFile(file, username)
            if (outcome?.status === 'skipped') {
              this.ciBatchSketchR.skipped++
            } else {
              this.ciBatchSketchR.done++
            }
          } catch (err) {
            console.error('[CI] batch sketch R file error:', file, err)
            this.ciBatchSketchR.failed++
            this.$message.error(`「${file}」处理失败：${err?.message || err}`)
          }
        }
        this.$message.success(
          `批量处理结束：成功 ${this.ciBatchSketchR.done}，跳过 ${this.ciBatchSketchR.skipped}，失败 ${this.ciBatchSketchR.failed}`
        )
      } finally {
        this.ciBatchSketchR.running = false
        this.ciSuppressAutoOpenWorkArea = false
        this.ciSuppressOpenCIPanelOnComplete = false
        this._clearCIBatchWait()
        this.clearCIPollTimer()
        this._closeCIProgressNotification()
        this.ciBatchSketchRDialogVisible = false
      }
    },

    _clearCIBatchWait() {
      if (this._ciBatchWaitTimer) {
        clearTimeout(this._ciBatchWaitTimer)
        this._ciBatchWaitTimer = null
      }
      this._ciBatchWaitResolve = null
      this._ciBatchWaitReject = null
    },

    _waitCIRunningTaskComplete(timeoutMs = 900000) {
      if (this.ciRunningTask?.completed && !this.ciRunningTask?.error) {
        return Promise.resolve()
      }
      if (this.ciRunningTask?.error) {
        return Promise.reject(new Error(this.ciRunningTask.error))
      }
      return new Promise((resolve, reject) => {
        this._ciBatchWaitResolve = resolve
        this._ciBatchWaitReject = reject
        this._ciBatchWaitTimer = setTimeout(() => {
          this._clearCIBatchWait()
          reject(new Error('当前图片处理超时'))
        }, timeoutMs)
      })
    },

    _resolveCIBatchWait(err = null) {
      if (err && this._ciBatchWaitReject) {
        const rej = this._ciBatchWaitReject
        this._clearCIBatchWait()
        rej(err)
        return
      }
      if (this._ciBatchWaitResolve) {
        const res = this._ciBatchWaitResolve
        this._clearCIBatchWait()
        res()
      }
    },

    async _processBatchSketchRFile(filename, username) {
      const currentFile = (filename || '').trim()
      if (!this._isImageOrPdf(currentFile)) {
        throw new Error('非图片文件')
      }
      const resp = await queryCIAnalyses({ username, files: [currentFile], scene_name: this.sceneName })
      if (resp.error_num !== 0) {
        throw new Error(resp.msg || '查询图片理解记录失败')
      }

      const isHomework = resp.homework_status?.analysis_type === 'homework_grading'
      const preferredType = isHomework ? 'homework_grading' : ''
      const singleRecord = this._findSingleRecordForFile(resp.singles, currentFile, preferredType)

      if (singleRecord?.analysis_id) {
        const resultResp = await getCIResult({ username, analysis_id: singleRecord.analysis_id })
        if (resultResp.error_num === 0 && this._ciHasReadyReproduction(resultResp)) {
          return { status: 'skipped', reason: '已有 R 层复现图' }
        }
        if (
          this.ciRunningTask?.analysis_id === singleRecord.analysis_id
          && !this.ciRunningTask?.completed
        ) {
          await this._waitCIRunningTaskComplete()
          return { status: 'ok' }
        }
        await this._startCIReproductionTaskAndWait(
          singleRecord.analysis_id,
          username,
          false,
          true,
          true,
        )
        return { status: 'ok' }
      }

      await this._startCISketchRQuickstartTaskAndWait(currentFile, username)
      return { status: 'ok' }
    },

    async _startCISketchRQuickstartTaskAndWait(filename, username) {
      const u = username || localStorage.getItem('userId')
      const file = (filename || '').trim()
      if (!file) return
      const resp = await startCISketchRQuickstart({ username: u, files: [file] })
      if (resp.error_num !== 0) {
        throw new Error(resp.msg || '启动原草图复现失败')
      }
      const analysisId = resp.analysis_id || ''
      this.ciRunningTask = {
        task_id: resp.task_id,
        analysis_id: analysisId,
        unit_id: '',
        task_kind: 'reproduction_generate',
        section: '准备中',
        item: 0,
        total: 0,
        error: '',
        completed: false,
      }
      if (!this.ciBatchSketchR.running) {
        this._showCIProgressNotification([file])
      }
      this._startCIPoll(resp.task_id, analysisId, u)
      await this._waitCIRunningTaskComplete()
    },

    async _startCIReproductionTaskAndWait(
      analysisId,
      username,
      forceRebuild = false,
      useSketchInput = true,
      useOriginalSketchAsR = false,
    ) {
      if (!analysisId) return
      const u = username || localStorage.getItem('userId')
      const resp = await startCIReproduction({
        username: u,
        analysis_id: analysisId,
        force_rebuild: forceRebuild,
        use_sketch_input: useSketchInput,
        use_original_sketch_as_r: Boolean(useSketchInput && useOriginalSketchAsR),
      })
      if (resp.error_num !== 0) {
        throw new Error(resp.msg || '启动复现图生成失败')
      }
      const files = [this.ciBatchSketchR.currentFile || '升维复现']
      this.ciRunningTask = {
        task_id: resp.task_id,
        analysis_id: analysisId,
        unit_id: '',
        task_kind: 'reproduction_generate',
        section: '准备中',
        item: 0,
        total: 0,
        error: '',
        completed: false,
      }
      if (!this.ciBatchSketchR.running) {
        this._showCIProgressNotification(files)
      }
      this._startCIPoll(resp.task_id, analysisId, u)
      await this._waitCIRunningTaskComplete()
    },

    _signalOpenCISingleWorkArea(analysisId, preferredUnitId = '') {
      if (!analysisId) return
      const unitId = preferredUnitId
        || this.ciActiveResult?.m_layer?.sections?.[0]?.unit_id
        || this.ciActiveResult?.r_layer?.items?.[0]?.unit_id
        || ''
      this.ciSingleWorkAreaAutoOpenSignal = {
        analysisId,
        unitId,
        nonce: `open-workarea-${Date.now()}`,
      }
    },

    async _handleCIExplicitSingleTrigger(filename, username) {
      if (filename.toLowerCase().endsWith('.pdf')) {
        return this._startCIAnalysis([filename], 'single', username, { requestedAction: 'understanding' })
      }
      const resp = await queryCIAnalyses({ username, files: [filename], scene_name: this.sceneName })
      if (resp.error_num !== 0) {
        this.$message.error(resp.msg || '查询图片理解记录失败')
        return
      }

      const isHomework = resp.homework_status?.analysis_type === 'homework_grading'
      if (isHomework) {
        this.$message.info('作业 PDF 请使用上方「无损版面 / 无损理解 / 三区批改」按钮')
        return
      }

      const singleRecord = this._findCompletedSingleForFile(resp.singles, filename, '')
      this._setCIAvailableAnalyses(singleRecord, null)
      if (singleRecord) {
        await this._openCIExistingResult(singleRecord.analysis_id, username, singleRecord, null)
        return
      }

      const pdfHint = await this._getCIPdfHint([filename], username, true)
      const action = await this._confirmCIAction(
        `${pdfHint}当前文档还没有${isHomework ? '作业批改' : '单图理解'}结果，是否开始${isHomework ? '批改' : '图片理解'}？`,
        `${isHomework ? '作业批改' : '图片理解'}确认 - ${filename}`,
        isHomework ? '开始批改' : '开始分析',
        '取消'
      )
      if (action === 'confirm') {
        await this._startCIAnalysis([filename], 'single', username, {
          contextDocs: this._ciSelectedContextDocs([filename]),
        })
      }
    },

    async _handleCIExplicitMultiTrigger(openedFile, targetFiles, username) {
      const [singleResp, groupResp] = await Promise.all([
        queryCIAnalyses({ username, files: [openedFile], scene_name: this.sceneName }),
        queryCIAnalyses({ username, files: targetFiles, scene_name: this.sceneName }),
      ])
      if (singleResp.error_num !== 0 || groupResp.error_num !== 0) {
        this.$message.error(singleResp.msg || groupResp.msg || '查询图片理解记录失败')
        return
      }

      const singleRecord = this._findCompletedSingleForFile(singleResp.singles, openedFile)
      const groupRecord = this._findCompletedGroupForFiles(groupResp.groups, targetFiles, groupResp.superset_match)
      this._setCIAvailableAnalyses(singleRecord, groupRecord)

      if (singleRecord && groupRecord) {
        await this._openCIExistingResult(singleRecord.analysis_id, username, singleRecord, groupRecord)
        return
      }

      const fileNames = targetFiles.join('、')
      const pdfHint = await this._getCIPdfHint(targetFiles, username, false)
      const groupSummary = `已勾选 ${targetFiles.length} 个图片/PDF文件：${fileNames}${pdfHint}`

      if (!groupRecord && !singleRecord) {
        const action = await this._confirmCIAction(
          `${groupSummary}\n\n当前文档和勾选组合都还没有理解结果，请选择本次操作。`,
          '图片理解确认',
          '分析当前文档',
          '分析勾选组合'
        )
        if (action === 'confirm') {
          await this._startCIAnalysis([openedFile], 'single', username, {
            contextDocs: this._ciSelectedContextDocs([openedFile]),
          })
        } else if (action === 'cancel') {
          await this._startCIAnalysis(targetFiles, 'group', username, {
            contextDocs: this._ciSelectedContextDocs(targetFiles),
          })
        }
        return
      }

      if (!groupRecord && singleRecord) {
        const action = await this._confirmCIAction(
          `${groupSummary}\n\n当前文档已有单图理解结果，勾选组合还没有多图理解结果，请选择本次操作。`,
          '图片理解确认',
          '查看单图结果',
          '分析勾选组合'
        )
        if (action === 'confirm') {
          await this._openCIExistingResult(singleRecord.analysis_id, username, singleRecord, null)
        } else if (action === 'cancel') {
          await this._startCIAnalysis(targetFiles, 'group', username, {
            contextDocs: this._ciSelectedContextDocs(targetFiles),
          })
        }
        return
      }

      if (groupRecord && !singleRecord) {
        const action = await this._confirmCIAction(
          `${groupSummary}\n\n勾选组合已有多图理解结果，当前文档还没有单图理解结果，请选择本次操作。`,
          '图片理解确认',
          '分析当前文档',
          '查看多图结果'
        )
        if (action === 'confirm') {
          await this._startCIAnalysis([openedFile], 'single', username, {
            contextDocs: this._ciSelectedContextDocs([openedFile]),
          })
        } else if (action === 'cancel') {
          await this._openCIExistingResult(groupRecord.analysis_id, username, null, groupRecord)
        }
      }
    },

    /** 启动分析（内部使用） */
    async _startCIAnalysis(files, mode, username, options = {}) {
      try {
        const contextDocs = Array.isArray(options.contextDocs)
          ? options.contextDocs
          : this._ciSelectedContextDocs(files)
        const payload = { username, files, mode, scene_name: this.sceneName, ...(options.material || {}) }
        if (contextDocs.length > 0) {
          payload.context_docs = contextDocs
        }
        // 传入当前勾选的卡片ID列表作为上下文
        if (this.choosedCardIdList && this.choosedCardIdList.length > 0) {
          payload.context_card_ids = [...this.choosedCardIdList]
        }
        if (options.homeworkTargetStage) {
          payload.homework_target_stage = options.homeworkTargetStage
        }
        console.log('[CI] files:', files, 'context_docs:', contextDocs, 'context_card_ids:', payload.context_card_ids || [], 'homework_target_stage:', payload.homework_target_stage || '')
        const start = options.requestedAction === 'grading' ? startHomeworkFeedback
          : options.requestedAction === 'understanding' ? startImageUnderstanding : startCIAnalysis
        const resp = await start(payload)
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动分析失败')
          return
        }
        const { task_id, analysis_id, msg, analysis_type } = resp

        this.ciActiveAnalysisId = analysis_id
        if (analysis_type === 'homework_grading' || String(analysis_id).startsWith('homework_')) {
          this.ciHomeworkAnalysisId = analysis_id
        }

        if (msg === 'existing_result' || msg === 'superset_exists') {
          await this._loadCIResult(analysis_id, username)
          this.showContinuousImagePanel = true
          if (options.homeworkTargetStage) {
            await this._openHomeworkPageViewMode(options.homeworkTargetStage)
            this.ciHomeworkPendingPageView = ''
          }
          return resp
        }

        // 初始化进度状态并显示右下角通知
        this.ciActiveResult = null
        this.ciHomeworkRunId = 'current'
        this.ciRunningTask = { ...resp, task_id, analysis_id, analysis_type: analysis_type || 'continuous_image', section: '准备中', item: 0, total: 0, error: '', completed: false }
        this._showCIProgressNotification(files)
        this._startCIPoll(task_id, analysis_id, username)
        return resp
      } catch (e) {
        console.error('[CI] _startCIAnalysis error:', e)
        this.$message.error(e.message || '启动失败')
        return null
      }
    },

    _formatCIProgressSection(section) {
      let text = String(section || '处理中').replace(/\s+/g, ' ').trim()
      if (!text) return '处理中'
      text = text.replace(/Session\s*(\d+)\/(\d+)[（(][^，),]*[，,]\s*(\d+)页[，,]\s*前序有[）)]/i, '正在批改第$1/$2篇（$3页，已参考前面错题）')
      text = text.replace(/Session\s*(\d+)\/(\d+)[（(][^，),]*[，,]\s*(\d+)页[，,]\s*前序无[）)]/i, '正在批改第$1/$2篇（$3页）')
      text = text.replace(/逐页批改\s*Session\s*(\d+)\/(\d+)[（(]刚完成第(\d+)页[）)]/i, '已完成第$3页，继续第$1/$2篇')
      text = text.replace(/Session\s*预切分（双通道）/i, '识别作业篇目结构')
      text = text.replace(/逐页批改准备中（\d+并行）/g, '准备逐页批改')
      text = text.replace(/未归\s*session\s*第(\d+)页/ig, '第$1页')
      text = text.replace(/\bsession\b/ig, '篇目')
      text = text.replace(/构建数字孪生体（?L5）?/g, '生成整篇学习诊断')
      text = text.replace(/生成三区诊断（消费 ontology）/ig, '整理问题与提升建议')
      text = text.replace(/幻觉过滤校验（三件套回写）/g, '复核批改结果')
      text = text.replace(/学科约束校验（L4验算）/g, '复核学科规则')
      text = text.replace(/汇总错题记忆与规则基线/g, '汇总错题线索')
      text = text.replace(/ontology/ig, '诊断结果')
      text = text.replace(/\bL[45]\b/g, '')
      return text.replace(/\s+/g, ' ').trim() || '处理中'
    },

    /** 创建/更新右下角进度通知 */
    _showCIProgressNotification(files) {
      // 先关闭旧的
      this._closeCIProgressNotification()
      const label = this.ciBatchSketchR.running
        ? `批量 ${this.ciBatchSketchR.current}/${this.ciBatchSketchR.total}`
        : (files.length === 1 ? files[0] : `${files.length}张图片`)
      const ciType = this.ciRunningTask?.analysis_type
      const titlePrefix = this.ciBatchSketchR.running
        ? '批量原草图作 R'
        : (ciType === 'homework_grading'
          ? '作业批改进度'
          : (ciType === 'cross_subject' ? '双科交叉诊断进度' : '图片理解进度'))
      this.ciProgressNotification = ElNotification({
        title: `${titlePrefix} - ${label}`,
        message: () => h('div', null, [
          h(ElProgress, {
            percentage: this._ciProgressPercent,
            status: this.ciRunningTask?.error ? 'exception' : (this.ciRunningTask?.completed ? 'success' : ''),
            format: () => {
              const task = this.ciRunningTask
              if (!task) return '准备中...'
              if (task.error) return `失败: ${task.error}`
              return `${this._formatCIProgressSection(task.section)} (${this._ciProgressPercent}%)`
            }
          })
        ]),
        duration: 0,
        position: 'bottom-right',
        zIndex: 10000,
      })
    },

    /** 关闭右下角进度通知 */
    _closeCIProgressNotification() {
      if (this.ciProgressNotification) {
        this.ciProgressNotification.close()
        this.ciProgressNotification = null
      }
    },

    /** 加载已完成的分析结果 */
    async _loadCIResult(analysisId, username, runId) {
      if (!analysisId) return
      const u = username || localStorage.getItem('userId')
      const effectiveRunId = runId ?? this.ciHomeworkRunId ?? 'current'
      try {
        const payload = { username: u, analysis_id: analysisId }
        if (String(analysisId).startsWith('homework_') && effectiveRunId) {
          payload.run_id = effectiveRunId
        }
        const resp = await getCIResult(payload)
        if (resp.error_num === 0) {
          this.ciActiveAnalysisId = analysisId
          this.ciActiveResult = resp
          this.ciRunningTask = null
          if (resp.analysis_type === 'homework_grading') {
            this.ciHomeworkRunId = resp.run_id || effectiveRunId || 'current'
            this.ciHomeworkAnalysisId = analysisId
            await this._loadCIHomeworkVersions(analysisId, u)
          }
          if (resp.analysis_type !== 'homework_grading' && resp.analysis_type !== 'cross_subject') {
            await this._maybeConfirmCIReproduction(resp, u)
          }
          return
        }
        this.ciActiveResult = null
        this.showContinuousImagePanel = false
        this.$message.error(resp.msg || '读取图片理解结果失败')
      } catch (e) {
        console.error('[CI] _loadCIResult error:', e)
        this.ciActiveResult = null
        this.showContinuousImagePanel = false
        this.$message.error('读取图片理解结果失败：' + (e.message || e))
      }
    },

    async _loadCIHomeworkVersions(analysisId, username) {
      if (!analysisId) return
      const u = username || localStorage.getItem('userId')
      this.ciHomeworkVersionsLoading = true
      try {
        const resp = await listCIHomeworkVersions({ username: u, analysis_id: analysisId })
        if (resp.error_num === 0) {
          this.ciHomeworkVersions = Array.isArray(resp.versions) ? resp.versions : []
        }
      } catch (e) {
        console.error('[CI] _loadCIHomeworkVersions error:', e)
      } finally {
        this.ciHomeworkVersionsLoading = false
      }
    },

    _ciNeedsReproductionConfirm(result) {
      if (!result || !result.analysis_id) return false
      const sectionCount = Array.isArray(result?.m_layer?.sections) ? result.m_layer.sections.length : 0
      if (sectionCount === 1) return false
      if (result.reproduction_confirmation_required === true) return true
      const status = result.reproduction_status || ''
      if (status) return status === 'pending_confirm'
      const items = (((result.r_layer || {}).items) || [])
      return !items.some(item => item.status === 'ready') && items.length === 0
    },

    _ciHasReadyReproduction(result) {
      const items = (((result || {}).r_layer || {}).items) || []
      return items.some(item => item?.status === 'ready' && String(item?.reproduction_path || '').trim())
    },

    async _promptCIReproductionSketchAndOriginalOptions(firstMessage, firstTitle) {
      let useSketchInput = null
      try {
        await ElMessageBox.confirm(
          firstMessage,
          firstTitle,
          {
            confirmButtonText: '输入草图生成',
            cancelButtonText: '不输入草图生成',
            type: 'info',
            distinguishCancelAndClose: true,
          },
        )
        useSketchInput = true
      } catch (action) {
        if (action === 'cancel') {
          useSketchInput = false
        } else {
          useSketchInput = null
        }
      }
      if (useSketchInput === null) {
        return null
      }
      if (useSketchInput === false) {
        return { useSketchInput: false, useOriginalSketchAsR: false }
      }
      let useOriginalSketchAsR = false
      try {
        await ElMessageBox.confirm(
          '已选择「输入草图生成」。是否直接用原草图作为 R 层复现图（不调用升维模型）？\n\n确定：直接用原草图\n取消：按理解结果做升维复现生成\n关闭：取消本次操作',
          '原草图作为复现图',
          {
            confirmButtonText: '直接用原草图',
            cancelButtonText: '升维生成复现图',
            type: 'info',
            distinguishCancelAndClose: true,
          },
        )
        useOriginalSketchAsR = true
      } catch (action2) {
        if (action2 === 'cancel') {
          useOriginalSketchAsR = false
        } else {
          return null
        }
      }
      return { useSketchInput: true, useOriginalSketchAsR }
    },

    async _promptCIUseOriginalSketchAsROnly() {
      let useOriginalSketchAsR = false
      try {
        await ElMessageBox.confirm(
          '已选择「输入草图生成」。是否直接用原草图作为 R 层复现图（不调用升维模型）？\n\n确定：直接用原草图\n取消：按理解结果做升维复现生成\n关闭：取消本次操作',
          '原草图作为复现图',
          {
            confirmButtonText: '直接用原草图',
            cancelButtonText: '升维生成复现图',
            type: 'info',
            distinguishCancelAndClose: true,
          },
        )
        useOriginalSketchAsR = true
      } catch (action2) {
        if (action2 === 'cancel') {
          useOriginalSketchAsR = false
        } else {
          return null
        }
      }
      return useOriginalSketchAsR
    },

    async _maybeConfirmCIReproduction(result, username) {
      if (!this._ciNeedsReproductionConfirm(result)) return
      const analysisId = result.analysis_id
      if (!analysisId || this.ciReproductionConfirming === analysisId) return

      this.ciReproductionConfirming = analysisId
      let useSketchInput = null
      let useOriginalSketchAsR = false
      try {
        const picked = await this._promptCIReproductionSketchAndOriginalOptions(
          '请选择升维复现图的生成方式：\n\n确定：输入草图进行生成\n取消：不输入草图，直接按理解结果生成\n关闭：本次不生成',
          '升维复现生成方式',
        )
        if (!picked) {
          useSketchInput = null
        } else {
          useSketchInput = picked.useSketchInput
          useOriginalSketchAsR = picked.useOriginalSketchAsR
        }
      } finally {
        this.ciReproductionConfirming = ''
      }

      if (useSketchInput !== null) {
        await this._startCIReproductionTask(analysisId, username, false, useSketchInput, useOriginalSketchAsR)
      }
    },

    /** 无 CI 记录时：建最小工作区并以原草图直出 R */
    async _startCISketchRQuickstartTask(filename, username) {
      const u = username || localStorage.getItem('userId')
      const file = (filename || '').trim()
      if (!file) return
      try {
        const resp = await startCISketchRQuickstart({ username: u, files: [file] })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动原草图复现失败')
          return
        }
        const analysisId = resp.analysis_id || ''
        this.showContinuousImagePanel = true
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          unit_id: '',
          task_kind: 'reproduction_generate',
          section: '准备中',
          item: 0,
          total: 0,
          error: '',
          completed: false,
        }
        this._showCIProgressNotification([file])
        this._startCIPoll(resp.task_id, analysisId, u)
      } catch (e) {
        console.error('[CI] _startCISketchRQuickstartTask error:', e)
        this.$message.error('启动原草图复现失败')
      }
    },

    async _startCIReproductionTask(analysisId, username, forceRebuild = false, useSketchInput = true, useOriginalSketchAsR = false) {
      if (!analysisId) return
      const u = username || localStorage.getItem('userId')
      try {
        const resp = await startCIReproduction({
          username: u,
          analysis_id: analysisId,
          force_rebuild: forceRebuild,
          use_sketch_input: useSketchInput,
          use_original_sketch_as_r: Boolean(useSketchInput && useOriginalSketchAsR),
        })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动复现图生成失败')
          return
        }

        const files = this.ciActiveResult?.manifest?.selected_files || ['升维复现']
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          unit_id: '',
          task_kind: 'reproduction_generate',
          section: '准备中',
          item: 0,
          total: 0,
          error: '',
          completed: false,
        }
        this._showCIProgressNotification(files)
        this._startCIPoll(resp.task_id, analysisId, u)
      } catch (e) {
        console.error('[CI] _startCIReproductionTask error:', e)
      }
    },

    /** 开始轮询任务进度 */
    _startCIPoll(taskId, analysisId, username) {
      this.clearCIPollTimer()
      this.ciPollTimer = setInterval(async () => {
        await this._pollCIProgress(taskId, analysisId, username)
      }, 2000)
    },

    async _pollCIProgress(taskId, analysisId, username) {
      if (!taskId) return
      try {
        const resp = await getCIProgress(taskId)
        if (resp.error_num !== 0) {
          this.ciRunningTask = { ...this.ciRunningTask, error: resp.msg || '任务查询失败', failure_stage: resp.failure_stage || 'recovery' }
          this.clearCIPollTimer()
          return
        }

        this.ciRunningTask = {
          ...(this.ciRunningTask?.task_id === taskId ? this.ciRunningTask : {}),
          ...resp,
          task_id: taskId,
          analysis_id: analysisId,
          unit_id: resp.unit_id || '',
          task_kind: resp.task_kind || '',
          analysis_type: resp.analysis_type || this.ciRunningTask?.analysis_type || '',
          section: this._formatCIProgressSection(resp.current_section || '处理中'),
          item: resp.current_item || 0,
          total: resp.total_items || 0,
          error: resp.error || '',
          completed: resp.completed || false,
        }

        if (resp.error) {
          this.clearCIPollTimer()
          this.ciHomeworkPendingPageView = ''
          if (resp.task_kind === 'homework_red_blue_review') {
            this.ciHomeworkRedBlueRetryLoading = false
          }
          if (this.ciBatchSketchR.running) {
            this._resolveCIBatchWait(new Error(resp.error))
          }
          return
        }
        if (resp.completed) {
          const completedTaskKind = resp.task_kind || this.ciRunningTask?.task_kind || ''
          const completedUnitId = resp.unit_id || this.ciRunningTask?.unit_id || ''
          this.clearCIPollTimer()
          if (completedTaskKind === 'homework_red_blue_review') {
            this.ciHomeworkRedBlueRetryLoading = false
          }
          const u = username || localStorage.getItem('userId')
          if (!this.ciSuppressOpenCIPanelOnComplete) {
            await this._loadCIResult(analysisId, u)
          }
          const sectionCount = Array.isArray(this.ciActiveResult?.m_layer?.sections)
            ? this.ciActiveResult.m_layer.sections.length
            : 0
          const shouldAutoOpenSingleWorkArea = !this.ciSuppressAutoOpenWorkArea
            && sectionCount === 1
            && ['reproduction_generate', 'reproduction_iterate_unit', 'reproduction_iterate_layout_regions', 'reproduction_auto_iterate_round', 'reproduction_apply_lite_bundle'].includes(completedTaskKind)
          if (shouldAutoOpenSingleWorkArea) {
            this._signalOpenCISingleWorkArea(analysisId, completedUnitId)
          }
          if (!this.ciSuppressOpenCIPanelOnComplete) {
            const files = this.ciActiveResult?.manifest?.selected_files || []
            if (files.length) {
              const qr = await queryCIAnalyses({ username: u, files, scene_name: this.sceneName })
              if (qr.error_num === 0) {
                this.ciAvailableAnalyses = {
                  singles: (qr.singles || []).filter(r => r.status === 'completed' || r.status === 'partial'),
                  groups: (qr.groups || []).filter(r => r.status === 'completed'),
                }
              }
            }
            const pendingPageView = this.ciHomeworkPendingPageView
            if (pendingPageView) {
              this.ciHomeworkPendingPageView = ''
              await this._openHomeworkPageViewMode(pendingPageView)
            }
            setTimeout(() => {
              this._closeCIProgressNotification()
              if (!pendingPageView) {
                this.showContinuousImagePanel = true
              }
            }, 800)
          } else if (!this.ciBatchSketchR.running) {
            this._closeCIProgressNotification()
          }
          if (this.ciBatchSketchR.running) {
            this._resolveCIBatchWait()
          }
        }
      } catch (e) {
        console.error('[CI] _pollCIProgress error:', e)
      }
    },

    clearCIPollTimer() {
      if (this.ciPollTimer) {
        clearInterval(this.ciPollTimer)
        this.ciPollTimer = null
      }
    },

    /** 重置所有 CI 状态（打开新分析前 / 关闭面板时调用） */
    _resetCIState() {
      this.ciActiveResult = null
      this.ciActiveAnalysisId = ''
      this.ciAvailableAnalyses = { singles: [], groups: [] }
      this.ciRunningTask = null
      this.ciHomeworkRunId = 'current'
      this.ciHomeworkAnalysisId = ''
      this.ciHomeworkVersions = []
      this.ciHomeworkVersionsLoading = false
      this.ciHomeworkKeyVersionLoading = false
      this.ciHomeworkRerunLoading = false
      this.ciHomeworkRedBlueRetryLoading = false
      this.ciHomeworkPendingPageView = ''
      this.ciSingleWorkAreaAutoOpenSignal = null
      this.clearCIPollTimer()
      this._closeCIProgressNotification()
    },

    /** 面板：关闭（不中断后台分析轮询） */
    handleCloseContinuousImagePanel() {
      this.showContinuousImagePanel = false
      this.ciHomeworkPageViewOnly = false
      // 只重置面板展示状态，不要清理 poll timer、running task 和作业 analysis_id
      this.ciActiveResult = null
      this.ciActiveAnalysisId = ''
      this.ciHomeworkRunId = 'current'
      this.ciHomeworkVersions = []
      this.ciHomeworkKeyVersionLoading = false
      this.ciHomeworkRedBlueRetryLoading = false
      this.ciAvailableAnalyses = { singles: [], groups: [] }
      this.ciSingleWorkAreaAutoOpenSignal = null
    },

    /** 面板 emit：切换标签（查看另一个 analysis） */
    async handleCISwitchTab(analysisId) {
      const username = localStorage.getItem('userId')
      await this._loadCIResult(analysisId, username)
    },

    /** 面板 emit：启动双科交叉诊断（Pass3） */
    async handleCIStartPass3(payload) {
      const analysisIdA = payload?.analysis_id_a || ''
      const analysisIdB = payload?.analysis_id_b || ''
      if (!analysisIdA || !analysisIdB) return
      const username = localStorage.getItem('userId')
      try {
        const resp = await startCIPass3({ username, analysis_id_a: analysisIdA, analysis_id_b: analysisIdB })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动双科交叉诊断失败')
          return
        }
        const { task_id, analysis_id, msg } = resp
        this.ciActiveAnalysisId = analysis_id
        if (msg === 'existing_result') {
          await this._loadCIResult(analysis_id, username)
          this.showContinuousImagePanel = true
          return
        }
        this.ciRunningTask = {
          task_id, analysis_id, analysis_type: 'cross_subject',
          section: '准备双科交叉诊断', item: 0, total: 0, error: '', completed: false,
        }
        this._showCIProgressNotification(['双科交叉诊断'])
        this._startCIPoll(task_id, analysis_id, username)
      } catch (e) {
        console.error('[CI] handleCIStartPass3 error:', e)
        this.$message.error('启动双科交叉诊断失败')
      }
    },

    /** 作业批改：切换历史版本 */
    async handleCIHomeworkSwitchVersion(runId) {
      const analysisId = this.ciActiveAnalysisId
      if (!analysisId) return
      const username = localStorage.getItem('userId')
      this.ciHomeworkRunId = runId || 'current'
      await this._loadCIResult(analysisId, username, this.ciHomeworkRunId)
    },

    /** 作业批改：设置/取消关键历史版本 */
    async handleCIHomeworkToggleKeyVersion(payload) {
      const analysisId = this.ciActiveAnalysisId || this.ciHomeworkAnalysisId || this.ciActiveResult?.analysis_id || ''
      const runId = (payload?.runId || '').trim()
      if (!analysisId || !runId || runId === 'current') return
      const username = localStorage.getItem('userId')
      this.ciHomeworkKeyVersionLoading = true
      try {
        const resp = await markCIHomeworkVersionKey({
          username,
          analysis_id: analysisId,
          run_id: runId,
          is_key: !!payload?.isKey,
        })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '设置关键历史版本失败')
          return
        }
        this.ciHomeworkVersions = Array.isArray(resp.versions) ? resp.versions : this.ciHomeworkVersions
        this.$message.success(payload?.isKey ? '已设为关键历史版本' : '已取消关键历史版本')
      } catch (e) {
        console.error('[CI] handleCIHomeworkToggleKeyVersion error:', e)
        this.$message.error('设置关键历史版本失败')
      } finally {
        this.ciHomeworkKeyVersionLoading = false
      }
    },

    /** 作业批改：仅重试当前版本红蓝卡标 */
    async handleCIHomeworkRedBlueRetry() {
      const analysisId = (
        this.ciActiveAnalysisId
        || this.ciHomeworkAnalysisId
        || this.ciActiveResult?.analysis_id
        || ''
      ).trim()
      if (!analysisId || this.ciHomeworkRunId !== 'current') return
      const username = localStorage.getItem('userId')
      this.ciHomeworkRedBlueRetryLoading = true
      try {
        const resp = await retryCIHomeworkRedBlue({
          username,
          analysis_id: analysisId,
        })
        if (resp.error_num !== 0) {
          this.ciHomeworkRedBlueRetryLoading = false
          this.$message.error(resp.msg || '重新评分失败')
          return
        }
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          analysis_type: 'homework_grading',
          task_kind: 'homework_red_blue_review',
          section: '准备重新评分',
          item: 0,
          total: 1,
          error: '',
          completed: false,
        }
        this._startCIPoll(resp.task_id, analysisId, username)
        this.$message.success('已开始重新评分，批改结果仍可正常查看')
      } catch (e) {
        console.error('[CI] handleCIHomeworkRedBlueRetry error:', e)
        this.ciHomeworkRedBlueRetryLoading = false
        this.$message.error('启动重新评分失败')
      }
    },

    /** 作业批改：迭代 */
    async handleCIHomeworkRerun(payload) {
      const analysisId = (
        payload?.analysisId
        || this.ciActiveAnalysisId
        || this.ciHomeworkAnalysisId
        || this.ciActiveResult?.analysis_id
        || ''
      ).trim()
      if (!analysisId) {
        this.$message.error('无法确定作业分析 ID，请重新打开批改面板后再试')
        return
      }
      const username = localStorage.getItem('userId')
      const files = (Array.isArray(payload?.files) && payload.files.length)
        ? payload.files
        : (this.ciActiveResult?.manifest?.selected_files || ['作业批改迭代'])
      const rerunStage = ['all', 'layout', 'understanding', 'grading'].includes(payload?.rerunStage)
        ? payload.rerunStage
        : 'all'
      const sessionIds = Array.isArray(payload?.sessionIds)
        ? payload.sessionIds.filter(Boolean)
        : []
      const resume = payload?.resume === true
      this.ciHomeworkRerunLoading = true
      try {
        const resp = await rerunCIHomework({
          username,
          analysis_id: analysisId,
          scene_name: this.sceneName,
          rerun_stage: rerunStage,
          ...(payload?.fullRecompute ? { full_recompute: true } : {}),
          ...(payload?.material || {}),
          use_red_blue_feedback: payload?.useRedBlueFeedback === true,
          ...(payload?.preprocessMode ? { preprocess_mode: payload.preprocessMode } : {}),
          ...(sessionIds.length ? { session_ids: sessionIds } : {}),
          ...(resume ? { resume: true } : {}),
        })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '迭代失败')
          return
        }
        this.ciHomeworkRunId = 'current'
        this.ciHomeworkAnalysisId = analysisId
        this.ciActiveAnalysisId = analysisId
        this.showContinuousImagePanel = true
        this.ciActiveResult = null
        this.ciRunningTask = {
          ...resp,
          task_id: resp.task_id,
          analysis_id: analysisId,
          analysis_type: 'homework_grading',
          section: '准备作业批改',
          item: 0,
          total: 0,
          error: '',
          completed: false,
        }
        this.ciHomeworkPendingPageView = rerunStage === 'all' ? '' : rerunStage
        this._showCIProgressNotification(files)
        this._startCIPoll(resp.task_id, analysisId, username)
        if (resume) {
          this.$message.success('已从当前状态继续迭代剩余篇目')
        } else if (resp.archived_run_id) {
          this.$message.success('已开始迭代，上一版已归档为历史版本')
        } else {
          this.$message.success(sessionIds.length
            ? `已开始迭代 ${resp.effective_session_ids?.length || sessionIds.length} 个篇目`
            : (rerunStage === 'all' ? '已开始完整迭代批改' : '已开始分阶段迭代'))
        }
        return resp
      } catch (e) {
        console.error('[CI] handleCIHomeworkRerun error:', e)
        this.$message.error('启动迭代失败')
      } finally {
        this.ciHomeworkRerunLoading = false
      }
    },

    /** 面板 emit：重做分析 */
    async handleCIRedo(analysisPayload) {
      const analysisId = typeof analysisPayload === 'object'
        ? (analysisPayload?.analysisId || '')
        : analysisPayload
      if (!analysisId) return
      const username = localStorage.getItem('userId')
      let redoScope = typeof analysisPayload === 'object'
        ? (analysisPayload?.redoScope || 'mt')
        : 'mt'
      if (!['mt', 't'].includes(redoScope)) redoScope = 'mt'

      if (typeof analysisPayload !== 'object') {
        try {
          await ElMessageBox.confirm(
            '请选择迭代范围：\n\n确定：迭代 M/T 层\n取消：仅迭代 T 层\n关闭：取消本次操作',
            '迭代范围',
            {
              confirmButtonText: '迭代 M/T 层',
              cancelButtonText: '仅迭代 T 层',
              type: 'info',
              distinguishCancelAndClose: true,
            }
          )
          redoScope = 'mt'
        } catch (action) {
          if (action === 'cancel') {
            redoScope = 't'
          } else {
            return
          }
        }
      }

      try {
        const resp = await redoCIAnalysis({ username, analysis_id: analysisId, redo_scope: redoScope })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '迭代失败')
          return
        }
        // 关闭面板，用通知显示进度
        this.showContinuousImagePanel = false
        this.ciActiveAnalysisId = analysisId
        const files = this.ciActiveResult?.manifest?.selected_files || [redoScope === 't' ? '仅迭代T层' : '迭代分析']
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          unit_id: '',
          task_kind: redoScope === 't' ? 'redo_t_only' : 'redo_analysis',
          section: '准备中',
          item: 0,
          total: 0,
          error: '',
          completed: false,
        }
        this.ciActiveResult = null
        this._showCIProgressNotification(files)
        this._startCIPoll(resp.task_id, analysisId, username)
        this.$message.success(redoScope === 't' ? '已启动仅T层迭代' : '已启动M/T层迭代')
      } catch (e) {
        console.error('[CI] handleCIRedo error:', e)
      }
    },

    /** 面板 emit：显式生成/重生复现图 */
    async handleCIReproductionGenerate(analysisPayload) {
      const analysisId = typeof analysisPayload === 'object'
        ? (analysisPayload?.analysisId || '')
        : analysisPayload
      if (!analysisId) return
      const username = localStorage.getItem('userId')
      const status = this.ciActiveResult?.reproduction_status || ''
      const forceRebuild = typeof analysisPayload === 'object'
        ? Boolean(analysisPayload?.forceRebuild)
        : (status === 'completed' || status === 'failed')
      const hasReadyReproduction = this._ciHasReadyReproduction(this.ciActiveResult)
      const hasPresetUseSketch = typeof analysisPayload === 'object' && typeof analysisPayload?.useSketchInput === 'boolean'
      const hasPresetUseOriginal = typeof analysisPayload === 'object' && typeof analysisPayload?.useOriginalSketchAsR === 'boolean'
      let useSketchInput = hasPresetUseSketch ? Boolean(analysisPayload.useSketchInput) : null
      let useOriginalSketchAsR = hasPresetUseOriginal ? Boolean(analysisPayload.useOriginalSketchAsR) : false

      if (!hasPresetUseSketch) {
        this.ciReproductionConfirming = analysisId
        try {
          const firstTitle = forceRebuild ? '重新生成复现图' : (status === 'pending_confirm' || !hasReadyReproduction ? '生成复现图' : '迭代生图')
          const picked = await this._promptCIReproductionSketchAndOriginalOptions(
            '请选择升维复现图的生成方式：\n\n确定：输入草图进行生成\n取消：不输入草图，直接按理解结果生成\n关闭：取消本次操作',
            firstTitle,
          )
          if (!picked) {
            useSketchInput = null
          } else {
            useSketchInput = picked.useSketchInput
            useOriginalSketchAsR = picked.useOriginalSketchAsR
          }
        } finally {
          this.ciReproductionConfirming = ''
        }
      } else if (useSketchInput && !hasPresetUseOriginal) {
        this.ciReproductionConfirming = analysisId
        try {
          const sub = await this._promptCIUseOriginalSketchAsROnly()
          if (sub === null) {
            useSketchInput = null
          } else {
            useOriginalSketchAsR = sub
          }
        } finally {
          this.ciReproductionConfirming = ''
        }
      }

      if (useSketchInput !== null) {
        await this._startCIReproductionTask(analysisId, username, forceRebuild, useSketchInput, useOriginalSketchAsR)
      }
    },

    async handleCISaveReproductionContext(payload) {
      const username = localStorage.getItem('userId')
      const analysisId = payload?.analysisId || this.ciActiveAnalysisId
      const unitId = payload?.unitId || ''
      const iterContext = payload?.iterContext || {}
      if (!username || !analysisId || !unitId) return
      try {
        const resp = await updateCIReproductionContext({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          iter_context: iterContext,
        })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '保存R层生成依据失败')
          return
        }
        const nextItem = resp.r_item || null
        if (nextItem && this.ciActiveResult?.r_layer?.items) {
          const items = (this.ciActiveResult.r_layer.items || []).map(item => item?.unit_id === unitId ? nextItem : item)
          this.ciActiveResult = {
            ...this.ciActiveResult,
            r_layer: {
              ...(this.ciActiveResult.r_layer || {}),
              items,
            },
          }
        }
        this.$message.success('R层生成依据已保存')
      } catch (e) {
        console.error('[CI] handleCISaveReproductionContext error:', e)
        this.$message.error('保存R层生成依据失败：' + (e.message || e))
      }
    },

    async handleCIIterateReproductionUnit(payload) {
      const username = localStorage.getItem('userId')
      const analysisId = payload?.analysisId || this.ciActiveAnalysisId
      const unitId = payload?.unitId || ''
      if (!username || !analysisId || !unitId) return
      try {
        const resp = await iterateCIReproductionUnit({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          revision_instruction: payload?.revisionInstruction || undefined,
          reference_image: payload?.referenceImage || undefined,
          image_quality: payload?.imageQuality || 'normal',
          iter_context: payload?.iterContext || undefined,
        })
        if (resp.error_num === 1 && resp.generating) {
          this.$message.warning('该页复现图正在迭代中，请稍等')
          return
        }
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动R层单页迭代失败')
          return
        }
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          unit_id: unitId,
          task_kind: 'reproduction_iterate_unit',
          section: '准备中',
          item: 0,
          total: 1,
          error: '',
          completed: false,
        }
        const files = this.ciActiveResult?.manifest?.selected_files || ['复现图单页迭代']
        this._showCIProgressNotification(files)
        this._startCIPoll(resp.task_id, analysisId, username)
        this.$message.success('已加入R层单页迭代队列')
      } catch (e) {
        console.error('[CI] handleCIIterateReproductionUnit error:', e)
        this.$message.error('启动R层单页迭代失败：' + (e.message || e))
      }
    },

    async handleCIIterateReproductionLayoutRegions(payload) {
      const username = localStorage.getItem('userId')
      const analysisId = payload?.analysisId || this.ciActiveAnalysisId
      const unitId = payload?.unitId || ''
      const iterationMode = payload?.iterationMode === 'crop' ? 'crop' : 'rewrite'
      if (!username || !analysisId || !unitId) return
      try {
        const resp = await iterateCIReproductionLayoutRegions({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          selected_regions: payload?.selectedRegions || [],
          iteration_mode: iterationMode,
          reference_image: payload?.referenceImage || undefined,
          image_quality: payload?.imageQuality || 'normal',
          iter_context: payload?.iterContext || undefined,
        })
        if (resp.error_num === 1 && resp.generating) {
          this.$message.warning('该页复现图正在迭代中，请稍等')
          return
        }
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动版面级单页迭代失败')
          return
        }
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          unit_id: unitId,
          task_kind: 'reproduction_iterate_layout_regions',
          iteration_mode: iterationMode,
          section: '准备中',
          item: 0,
          total: 1,
          error: '',
          completed: false,
        }
        const files = this.ciActiveResult?.manifest?.selected_files || [iterationMode === 'crop' ? '复现图局部裁切迭代' : '复现图版面级定向迭代']
        this._showCIProgressNotification(files)
        this._startCIPoll(resp.task_id, analysisId, username)
        this.$message.success(iterationMode === 'crop' ? '已加入局部裁切迭代队列' : '已加入版面级单页迭代队列')
      } catch (e) {
        console.error('[CI] handleCIIterateReproductionLayoutRegions error:', e)
        this.$message.error('启动版面级单页迭代失败：' + (e.message || e))
      }
    },

    async handleCIApplyLiteBundleReproduction(payload) {
      const username = localStorage.getItem('userId')
      const analysisId = payload?.analysisId || this.ciActiveAnalysisId
      const unitId = payload?.unitId || ''
      if (!username || !analysisId || !unitId) return
      try {
        const resp = await applyCILiteBundleToReproduction({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          image_quality: payload?.imageQuality || 'normal',
          iter_context: payload?.iterContext || undefined,
        })
        if (resp.error_num === 1 && resp.generating) {
          this.$message.warning('该页复现图正在处理中，请稍等')
          return
        }
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动轻量识字贴补失败')
          return
        }
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          unit_id: unitId,
          task_kind: 'reproduction_apply_lite_bundle',
          section: '准备中',
          item: 0,
          total: 1,
          error: '',
          completed: false,
        }
        const files = this.ciActiveResult?.manifest?.selected_files || ['轻量识字贴补R层']
        this._showCIProgressNotification(files)
        this._startCIPoll(resp.task_id, analysisId, username)
        this.$message.success('已加入轻量识字贴补队列')
      } catch (e) {
        console.error('[CI] handleCIApplyLiteBundleReproduction error:', e)
        this.$message.error('启动轻量识字贴补失败：' + (e.message || e))
      }
    },

    async handleCIAutoIterateReproductionRound(payload) {
      const username = localStorage.getItem('userId')
      const analysisId = payload?.analysisId || this.ciActiveAnalysisId
      const unitId = payload?.unitId || ''
      if (!username || !analysisId || !unitId) return
      try {
        const resp = await autoIterateCIReproductionRound({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
          mode: payload?.mode || 'full',
          selected_region_ids: Array.isArray(payload?.selectedRegionIds) ? payload.selectedRegionIds : undefined,
          gray_resolutions: Array.isArray(payload?.grayResolutions) ? payload.grayResolutions : undefined,
          start_region_id: payload?.startRegionId || undefined,
          continue_from_cursor: payload?.continueFromCursor !== false,
          image_quality: payload?.imageQuality || 'normal',
          iter_context: payload?.iterContext || undefined,
          sketch_preprocess: typeof payload?.sketchPreprocess === 'boolean' ? payload.sketchPreprocess : undefined,
          use_recognition_context: payload?.useRecognitionContext !== false,
        })
        if (resp.error_num === 1 && resp.generating) {
          this.$message.warning('该页复现图正在处理中，请稍等')
          return
        }
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '启动单图自动迭代失败')
          return
        }
        this.ciRunningTask = {
          task_id: resp.task_id,
          analysis_id: analysisId,
          unit_id: unitId,
          task_kind: 'reproduction_auto_iterate_round',
          section: '准备中',
          item: 0,
          total: 1,
          error: '',
          completed: false,
        }
        const files = this.ciActiveResult?.manifest?.selected_files || ['单图自动迭代']
        this._showCIProgressNotification(files)
        this._startCIPoll(resp.task_id, analysisId, username)
        this.$message.success('已加入单图自动迭代队列')
      } catch (e) {
        console.error('[CI] handleCIAutoIterateReproductionRound error:', e)
        this.$message.error('启动单图自动迭代失败：' + (e.message || e))
      }
    },

    async handleCIRollbackReproductionUnit(payload) {
      const username = localStorage.getItem('userId')
      const analysisId = payload?.analysisId || this.ciActiveAnalysisId
      const unitId = payload?.unitId || ''
      if (!username || !analysisId || !unitId) return
      try {
        await ElMessageBox.confirm(
          '将把当前页复现图回滚到上一版本，是否继续？',
          '回滚复现图',
          {
            confirmButtonText: '回滚',
            cancelButtonText: '取消',
            type: 'warning',
          }
        )
      } catch (_) {
        return
      }

      try {
        const resp = await rollbackCIReproductionUnit({
          username,
          analysis_id: analysisId,
          unit_id: unitId,
        })
        if (resp.error_num !== 0) {
          this.$message.error(resp.msg || '回滚R层复现图失败')
          return
        }
        const nextItem = resp.r_item || null
        if (nextItem && this.ciActiveResult?.r_layer?.items) {
          const items = (this.ciActiveResult.r_layer.items || []).map(item => item?.unit_id === unitId ? nextItem : item)
          this.ciActiveResult = {
            ...this.ciActiveResult,
            r_layer: {
              ...(this.ciActiveResult.r_layer || {}),
              items,
            },
            reproduction_status: 'completed',
          }
        }
        this.$message.success('已回滚到上一版复现图')
      } catch (e) {
        console.error('[CI] handleCIRollbackReproductionUnit error:', e)
        this.$message.error('回滚R层复现图失败：' + (e.message || e))
      }
    },

    // ====== 连续图片认知理解结束 ======

    formatTooltip(val) {
      return `${val} `
    },
    show1() {
      this.dialogInnerVisible = true
      this.initValue = '0.1（0.05~3）'
      this.info = '这个值越大生成内容越随机，多样性更好'
      this.what = '这个参数控制生成的随机性。较高的温度（如 1.2）会增加文本的多样性和创造性，但会牺牲一些准确性或连贯性。temperature=1，没有任何调整；如果>1，则会生成更加随机的文本；如果<1，则生成的文本更加保守。'
    },
    show2() {
      this.dialogInnerVisible = true
      this.initValue = '0.95（0.05~0.95）'
      this.info = 'top_p越大越多token会被考虑，但一般建议只修改 temperature 和 top_p 其中一个。'
      this.what = '单步累计采用阈值，top_p值越大，多样性越高，但推理速度更慢；top_p值越小，生成越保守，但推理速度更快'
    },
    show3() {
      this.dialogInnerVisible = true
      this.initValue = '15（10~100）'
      this.info = '单步考虑token的数量，越大则考虑的token数会越多，更建议使用 temperature 或 top_p'
      this.what = 'top_k是单步中最多考虑的token数量'
    },
    show4() {
      this.dialogInnerVisible = true
      this.initValue = '512（20~1024）'
      this.info = '最大采样长度，它是输入prompt的长度加上最大新词数的值。如果同时设置了最大新词数，则会覆盖此参数'
      this.what = '模型生成的文本最大长度，超过的话会做截断，512是参考值，这个依赖于实际情况自己设置'
    },
    show5() {
      this.dialogInnerVisible = true
      this.initValue = '1（1~20）'
      this.info = 'beam搜索数量，越大文本质量可能越高，正常推理时设置成1即可'
      this.what = '在每个时刻，记录概率最高的前num_beams个路径，在下一个时刻可以有多个基础路径同时搜索，有助于生成更加陈述和高质量的文本，但推理速度将变慢，且多样性不高。'
    },
    show6() {
      this.dialogInnerVisible = true
      this.initValue = '1（0/1）'
      this.info = '通常设置为 1，当设置为 0 时，temperature、top_k、top_p这些参数是不起作用的，只有设置为 1 时，它们才能够生效'
      this.what = '是否概率采样tokens得到结果，当设置为 0 时，模型在生成文本时不会随机采样，而是选择最可能的下一个词。这使得生成的文本非常固定'
    },
    show7() {
      this.dialogInnerVisible = true
      this.initValue = '1（1~20）'
      this.info = '分成num_beam_groups组进行搜索，通常设置为 1 即可，“beam搜索”值应能被此参数整除'
      this.what = '这个参数与束搜索相关。它将搜索的束分为不同的组，每个组内部进行搜索，且引入多样性惩罚值。这可以增加文本的多样性。'
    },
    show8() {
      this.dialogInnerVisible = true
      this.initValue = '1（1~3）'
      this.info = '正常推理设置为 1 即可'
      this.what = '模型返回多少条结果，要和beam 搜索数量num_beams一致'
    },
    show9() {
      this.dialogInnerVisible = true
      this.initValue = '1（0~5）'
      this.info = '重复惩罚值，越大越不会生成重复token'
      this.what = '较高的值意味着更强的惩罚，生成的文本中将出现更少的重复。如果取值为0，则没有惩罚，但生成的文本可能包含大量重复的内容。'
    },
    show10() {
      this.dialogInnerVisible = true
      this.initValue = '256（128~1024）'
      this.info = '在这里设置为256，意味着每次生成的文本最多包含256个词。'
      this.what = '模型生成的最大新词数'
    },
    show11() {
      this.dialogInnerVisible = true
      this.initValue = '1.1（-2~2）'
      this.info = '当使用多束搜索时，这个参数惩罚那些在不同束中过于相似的词，以提高生成文本的多样性。'
      this.what = '设置为1.5意味着对不同组之间的beams生成过于相似时，施加较大的惩罚。仅在 num_beam_groups 启用时这个值才有效'
    },
    show12() {
      this.dialogInnerVisible = true
      this.initValue = '1（-2~2）'
      this.info = '设置为 0：无惩罚，设置为 <0：鼓励模型生成短句子，设置为 >0.0：鼓励模型生成长句子'
      this.what = '用于 beam 搜素，会受到生成序列长度的惩罚'
    },

    changeSubSceneButton() {
      this.getSubSceneList();
      this.showDialog = true;
    },
    changeSubScene(subSceneName, index) {
      // 半自动化新增：记录子场景切换
      this.recordOperation('change_subscene', {
        sceneName: this.sceneName,
        subSceneName: subSceneName,
        previousSubScene: this.subSceneName
      });

      this.activeIndex = index;

      // alert(subSceneName);
      let formData = new FormData();
      // formData.append('username', 'admin');
      formData.append('username', localStorage.getItem('userId'));
      // 与 chatwindow 发消息一致：真实登录名 + userId 去掉本子主人 realName 后的后缀，便于与问答时 prompt 存储键一致
      let originRealNameForPrompt = (localStorage.getItem('originRealName') || '') +
        (localStorage.getItem('userId') || '').replace(localStorage.getItem('realName') || '', '');
      formData.append('originRealName', originRealNameForPrompt);

      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', subSceneName);
      setNewSubExcel(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success("子场景切换成功");
        }
      })

      this.subSceneName = subSceneName;
      localStorage.setItem('subSceneName', subSceneName);
      this.showDialog = false;
    },
    getSubSceneList() {
      this.subSceneList = localStorage.getItem('subSceneList').split(',');
    },

    // 检查是否有卡片操作权限（作者或群组协作用户）
    hasCardOperationPermission() {
      const isAuthor = localStorage.getItem('originRealName') === localStorage.getItem('realName');
      
      // 如果是作者，直接返回true
      if (isAuthor) return true;
      
      // 检查是否为群组本子协作用户
      const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
      if (currentNotebook.syncUsers && currentNotebook.syncUsers !== '') {
        const syncUsers = currentNotebook.syncUsers.split(',').map(user => user.trim()).filter(user => user);
        const currentUser = localStorage.getItem('originRealName');
        return syncUsers.includes(currentUser);
      }
      
      return false;
    }
  },
};

</script>

<!-- <style lang="scss" scoped> -->
<style lang="scss">
.feedback-entry-actions { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px; }
.el-header {
  padding: 0;
  height: 6vh;
}

.el-main {
  display: flex;
  flex-direction: row;
  padding: 0;
  height: 94vh;
}

.el-main::-webkit-scrollbar {
  display: none;
}

/* 当currentModule为'0'时，.main-left的宽度为36% */
.main-left1 {
  width: 24%;
  background-color: #fff;
  height: 94vh;
}

/* 当currentModule为'1'时，.main-left的宽度为50% */
/* 你可以使用计算属性或者watch来动态添加这个类 */
.main-left2 {
  width: 44%;
  background-color: #fff;
  height: 94vh;
}

.mainNav {
  height: 10vh;
}


.left-addfile {
  margin-top: 20px;

  input {
    display: none;
  }
}

.left-addfile-text {
  display: inline-block;
  vertical-align: middle;
  line-height: normal;
  font-weight: bold;
  padding-left: 20px;
  font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
  font-size: 20px;
  color: #333;
}

.left-addfile-button {
  background-image: url('@/assets/img/filewindow/addfile.png');
  background-size: contain;
  background-repeat: no-repeat;
  margin-right: 20px;
  vertical-align: middle;
  height: 20.8px;
  width: 20.8px;
  border-radius: 5px;
  float: right;

  background-color: transparent;
  cursor: pointer;
  transition: background-color 0.5s;

}


.left-addfile-button:hover {
  background-color: #b1b1b1;
}

.left-selectall {
  margin-top: 20px;
}

.left-selectall-text {
  display: inline-block;
  vertical-align: middle;
  line-height: normal;
  font-weight: bold;
  padding-left: 20px;
  font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
  font-size: 16px;
  color: #333;
}

.left-selectall-button {
  background-image: url('@/assets/img/filewindow/selectall.png');
  background-size: contain;
  background-repeat: no-repeat;
  margin-right: 20px;
  vertical-align: middle;
  height: 20.8px;
  width: 20.8px;
  border-radius: 3px;
  float: right;

  background-color: transparent;
  cursor: pointer;
  transition: background-color 0.5s;
}

.left-selectall-button:hover {
  background-color: #b1b1b1;
}

.left-selectall-button-clicked {
  background-image: url('@/assets/img/filewindow/selectall_blue.png');
  background-size: contain;
  background-repeat: no-repeat;
  margin-right: 20px;
  vertical-align: middle;
  height: 20.8px;
  width: 20.8px;
  border-radius: 3px;
  float: right;

  background-color: transparent;
  cursor: pointer;
  transition: background-color 0.5s;
}

.main-right {
  width: 100%;
  background-color: #d8e9fb;
  position: relative;
  z-index: 2;
}


.right-nav {
  margin-top: 10px;
  display: flex;
  width: 100%;
  height: 3vh;
  background-color: #d8e9fb;
  position: relative;
}

.right-nav-title {
  display: inline-block;
  vertical-align: middle;
  line-height: normal;
  font-weight: bold;
  padding-left: 16px;
  font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
  font-size: 16px;
  color: #333;
}

.right-nav-buttons {
  position: absolute;
  right: 20px;

  .el-button {
    margin: 0 10px;
    font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
    font-size: 16px;
    color: #333;
    cursor: pointer;
    transition: background-color 0.5s;
    background-color: #b6d4f4;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);

    &:hover {
      background-color: #a3d2d2;
      box-shadow: 0 4px 8px rgba(106, 106, 106, 0.3);
    }
  }
}

.bottom-nav-buttons {
  position: absolute;
  right: 360px;
  top: 77px;

  .el-button {
    margin: 0 10px;
    font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
    font-size: 16px;
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

.total-container {
  margin-top: 20px;
  /* 与按钮组的间距 */
  padding: 20px;
  /* 内边距 */
  /* 其他样式 ... */
}

.params-nav-buttons {
  position: absolute;
  width: 96%;
  height: 10%;
  display: flex;
  justify-content: center;
  left: 50%;
  /* 将容器向左移动其自身宽度的50%，以便居中 */
  transform: translateX(-50%);
  /* 向右移动容器，以抵消 left 属性的偏移 */

  .el-button {
    margin: 0 10px;
    font-family: 'Open Sans', 'Helvetica Neue', sans-serif;
    font-size: 16px;
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

.right-cardgrid {
  padding: 0px;
}


.chat-up {
  width: 100%;
  height: 0;
  display: none;
  background-color: rgb(234, 234, 234);
  position: absolute;
  bottom: 0;
  z-index: 5;
  transition: 0.5s ease;
}


.chat-left-div {
  width: 62%;
  height: 80%;
  text-align: center;
  background-color: lightblue;
  transition: 0.5s ease-in-out;
  // border-right: 20px solid #b1d7ff;

  overflow-y: auto;
  border: 10px solid #b1d7ff;
  border-right: 0;
}

.chat-left-div::-webkit-scrollbar {
  display: none;
}

.chat-left-one-div {
  width: 100%;
  height: 100%;
}

.chat-right-div {
  width: 35%;
  max-height: 100%;
  transition: 0.5s ease;
}


.chat-right-upper-div {
  background-color: #b1d7ff;
  height: 45%;
  width: 100%;
  transition: 0.5s ease;

  overflow-y: scroll;
  // border-bottom: 20px solid #b1d7ff;

  border: 10px solid #b1d7ff;

}

.chat-right-upper-div::-webkit-scrollbar {
  display: none;
}

.chat-right-lower-div {
  background-color: #b1d7ff;
  height: 45%;
  width: 100%;
  transition: 0.5s ease;
  overflow-y: scroll;

  border: 10px solid #b1d7ff;
}

.chat-right-lower-div::-webkit-scrollbar {
  display: none;
}

// .chat-left-div:hover {}
.chat-left-div:hover+.chat-right-lower-div {
  opacity: 0.1;
}

.chat-left-div:hover+.chat-right-lower-div {
  opacity: 0.1;
}

.chat-left-div:hover+.chat-right-upper-div {
  opacity: 0.1;
}


.chat-right-upper-div:hover {
  transform-origin: top right;
  // transform: scale(1.5);
  transform: scale(1.0);
  z-index: 8;
}

// ??? o_O?
// .chat-right-upper-div:hover+.chat-right-lower-div {
//   opacity: 0.1;
// }

.chat-right-upper-div:hover+.chat-left-one-div {
  opacity: 0.1;
}

.chat-right-lower-div:hover {
  transform-origin: bottom right;
  transform: scale(1.0);
  z-index: 8;
}

.chat-right-lower-div:hover+.chat-right-upper-div {
  opacity: 0.1;
}

.chat-right-lower-div:hover+.chat-left-div {
  opacity: 0.1;
}



.chat-down {
  height: 32%;
  width: 64%;
  display: flex;
  position: absolute;
  margin-left: 0%;
  margin-right: 36%;
  flex: 1;
  bottom: 0;
  z-index: 22;
  opacity: 0.8;
  transition: 0.5s ease;


  &:hover .chat-send-button {
    background-color: #fff;

  }

  &:hover .chat-input-field {
    width: 85%;
  }

  &:hover .chat-input {
    width: 100%;
  }

  &:hover {
    opacity: 1;
  }
}

.chat-down-none {
  height: 32%;
  width: 64%;
  display: none;
  position: absolute;
  margin-left: 0%;
  margin-right: 36%;
  flex: 1;
  bottom: 0;
  z-index: 6;
  opacity: 0.6;
  transition: 0.5s ease;
}

.chat-input-box {
  width: 100%;
  border-radius: 20px;
  background-color: #d8e9fb;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
  height: 100%;
  z-index: 4;
  margin: auto;

  display: flex;
  flex-direction: column; /* Stack children vertically */
  overflow: auto; /* Prevent content from spilling out */
}

.chat-input-boxup {
  width: 96%;
  height: 32%;
  margin: auto;
  display: flex;
}

.chat-choose-boxup {
  width: 96%;
  height: 8%;
  margin-top: 10px;
  display: flex;
}

.chat-params-boxup {
  width: 96%;
  height: 20%;
  margin: auto;
  display: flex;
}

.chat-boxup-list {
  width: 90%;
  height: 95%;
  margin-bottom: 10px;

  overflow: hidden;
  overflow-x: auto;
  white-space: nowrap;
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

.chat-boxup-list-item {
  // display: inline-block;
  display: inline-flex; /* 改为inline-flex，保持inline特性同时支持flex布局 */
  align-items: center; /* 垂直居中 */
  margin: 0 5px;
  margin-top: 10px;
  height: 50%;
  overflow: hidden;
  font-size: 18px;
  padding: 4px;
  background-color: #fff;
  border-radius: 10px;
  vertical-align: middle;
  transition: 0.5s ease;
  cursor: pointer;

  &:hover {
    background: #b9b9b9;
  }
}

.blue-bg {
  background-color: #c4c4fc;  /* 浅紫色 */
  
  &:hover {
    background-color: #a9a9f5;  /* 稍深一点的浅紫色 */
  }
}

// 开始：调整导问点击序号可编辑
.question-number {
  color: #666;
  font-weight: 500;
  margin-right: 6px;
  padding: 2px 6px;
  border-radius: 4px;
  min-width: 20px;
  text-align: center;
  transition: all 0.2s ease;
  user-select: none;
  flex-shrink: 0; /* 防止序号被压缩 */
}

.question-number:hover {
  background-color: #2196F3;
  color: white;
  transform: scale(1.1);
}

.question-content {
  flex: 1;
  padding: 2px 4px;
  border-radius: 4px;
  transition: background-color 0.2s ease;
}

.question-content:hover {
  background-color: rgba(33, 149, 243, 0.252);
}

/* 鼠标悬停时的提示效果 */
.question-number {
  position: relative;
}

.question-number::after {
  content: '点击编辑';
  position: absolute;
  bottom: -25px;
  left: 50%;
  transform: translateX(-50%);
  background-color: #333;
  color: white;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease;
  z-index: 1000;
}

.question-number:hover::after {
  opacity: 1;
}
// 结束

.chat-boxup-button-model {
  background-image: url('@/assets/img/chatwindow/ai.png');
  cursor: pointer;
  width: 20px;
  height: 20px;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;
  border-radius: 20px;
  margin: auto;
  transition: background-color 0.5s;

  &:hover {
    background-color: #b7b7b7;
  }
}

.chat-boxup-button-voice {
  background-image: url('@/assets/img/chatwindow/voice.png');
  cursor: pointer;
  width: 30px;
  height: 30px;
  background-color: #70dfab;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;
  border-radius: 20px;
  margin: auto;
  transition: background-color 0.5s;

  &:hover {
    background-color: #58f3ab;
  }
}

.chat-boxup-button-voice-ban {
  background-image: url('@/assets/img/chatwindow/EpMute.png');
  cursor: pointer;
  width: 30px;
  height: 30px;
  // background-color: #41220a;
  background-color: #651a0d;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;
  border-radius: 20px;
  margin: auto;
  transition: background-color 0.5s;

  &:hover {
    background-color: #581710;
  }
}

.chat-boxup-button {
  cursor: pointer;
  width: 30px;
  height: 30px;
  background-color: #70dfc7;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: middle;
  border-radius: 20px;
  margin: auto;
  transition: background-color 0.5s;

  &:hover {
    background-color: #b7b7b7;
  }
}

.chat-boxup-button.chatBtnChecked {
  background-image: url('@/assets/img/chatwindow/down.png');
}

.chat-boxup-button:not(.chatBtnChecked) {
  background-image: url('@/assets/img/chatwindow/up.png');
}


.chat-input-boxdown {
  width: 80%;
  height: 60%;
  margin: auto;
  // position: relative;
  display: flex;
  align-items: center;
  // flex-grow: 1; /* Take remaining space */
}

.chat-input {
  width: 100%;
  height: 100%;
  top: 50%;
  left: 50%;
  padding-left: 20px;

  // margin-top: 40px;
  background-color: rgb(234, 234, 234);
  border-radius: 40px;
  display: flex;

}


.chat-input-field {
  border: none;
  background: none;
  float: left;
  padding: 0;
  color: #000;
  font-size: 24px;
  line-height: 100%;

  width: 85%;
  resize: none; /* 禁止调整大小 */
  min-height: 50px; /* 最小高度 */
  max-height: 200px; /* 最大高度 */
  overflow-y: auto; /* 添加垂直滚动条 */
  white-space: pre-wrap; /* 允许文本换行 */
  word-wrap: break-word; /* 确保长单词也会换行 */

  &:focus {
    border: none;
    outline: none;
  }
}

.chat-send-button {
  cursor: pointer;
  vertical-align: middle;
  border-radius: 70px;
  display: flex;
  width: 70px;
  height: 70px;
  background-color: #8eaeda;
  justify-content: center;
  align-items: center;

  margin-left: auto;
  /* 将子组件推向最右侧 */
  margin-top: auto;
  /* 将子组件推向最下侧 */

  .chat-send-img {
    background-image: url('@/assets/img/chatwindow/send.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 40px;
    height: 40px;

  }
}

// .chat-input-boxfoot {}

.left-nav {
  width: 100%;
  height: 10vh;

  display: flex;
  padding-bottom: 10px;
}

.left-nav-title {
  width: 50%;
  height: 100%;
  line-height: 200%;
  font-family: 'Arial', sans-serif;
  font-size: 20px;
  font-weight: 600;
  color: #333;
  text-align: center;
  padding: 10px 0;
  background-color: #f8f8f8;
  // border-bottom: 1px solid #eaeaea;
  box-sizing: border-box;
  transition: background-color 0.3s ease, color 0.3s ease;
  overflow: hidden;
  text-overflow: ellipsis;

  &:hover {
    background-color: #eaeaea;
    color: #111;
    cursor: default;
  }

}

.left-nav-switch {
  background-color: #f8f8f8;
  width: 30%;
  text-align: center;
  height: 100%;
  line-height: 200%;
  transition: background-color 0.3s ease, color 0.3s ease;

  &:hover {
    background-color: #eaeaea;
    color: #111;
    cursor: default;
  }
}

.left-nav-close {
  width: 20%;
  cursor: pointer;
  vertical-align: middle;
  background-color: #fff;
  justify-content: center;
  align-items: center;
  display: flex;
  margin-left: auto;
  border-radius: 20px;
  transition: 0.5s;

  &:hover {
    background-color: #b8b5b5;
    box-shadow: 0 4px 8px rgba(106, 106, 106, 0.3);
  }

  .left-nav-close-icon {
    background-image: url('@/assets/img/filewindow/close.png');
    background-size: contain;
    background-repeat: no-repeat;
    display: inline-block;
    width: 20px;
    height: 20px;
  }
}


.left-summary {
  background-color: #abcef9;
  width: 100%;
  height: 0vh;
}

.left-summary-top {
  width: 100%;
  font-size: 15px;
  height: 60%;
  display: none;
  transition: 0.5s ease;
}

.left-summary-bottom {
  width: 100%;
  font-size: 15px;
  height: 40%;
  background-color: #ff9898;
}

.summary-img-list {
  width: 90%;
  height: 100%;

  overflow: hidden;
  overflow-x: auto;
  white-space: nowrap;
}

.summary-img-list-item {
  display: inline-block;
  margin: 0 5px;
  margin-top: 15px;
  height: 100px;
  width: 100px;
  background-color: #fff;
  border-radius: 10px;
  vertical-align: middle;
  transition: ease 0.5s;
  cursor: pointer;
  /* 使用object-fit属性来保持图片的宽高比 */
  object-fit: cover;
  overflow: hidden;

  position: relative; /* 新增两段式带图PDF上传处理，确保覆盖层正确定位 */

  &:hover {
    background-color: #b3b3b3;
  }
}

.summary-img-list-item img {
  width: 100%;
  height: 100%;
  object-position: center;
}


.image-processing-overlay {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  z-index: 10;
}

.processing-spinner {
  width: 24px;
  height: 24px;
  border: 3px solid #f3f3f3;
  border-top: 3px solid #409eff;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 8px;
}

.processing-text {
  color: white;
  font-size: 12px;
  text-align: center;
}

@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}





.left-summary-abstract {
  height: 100%;
  width: 60%;
  font-size: 15px;
  padding: 10px;
}

/*
.left-summary-abstract-title {
  width: 100%;
  font-size: 22px;
  height: 15%;
  overflow-y: hidden;
}
*/
.left-summary-abstract-title {
  width: 100%;
  font-size: 22px;
  min-height: 15%;
  overflow-y: visible;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
}

.left-summary-abstract-content {
  width: 100%;
  // word-break: break-all;
  word-break: break-word;  /* 改为 break-word */
  word-wrap: break-word;   /* 添加这行 */
  white-space: normal;     /* 添加这行，确保允许换行 */
  // text-indent: 2em;
  height: 80%;
  overflow-y: auto;
}

.summary-pin-icon {
  width: 24px;
  height: 24px;
  cursor: pointer;
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 15px;
  background-color: rgba(255, 255, 255, 0.9);
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.1);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
  transition: all 0.3s ease;
  z-index: 10;
  vertical-align: middle;
}

.summary-pin-icon:hover {
  background-color: rgba(64, 158, 255, 0.9);
  color: white;
  transform: scale(1.15);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.25);
}

/* 钉子旁提示图标：仅占位图标，悬停显示完整说明 */
.summary-hint-wrap {
  position: relative;
  display: inline-block;
  vertical-align: middle;
  margin-left: 8px;
}
.summary-hint-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #e6a23c 0%, #f0c78a 100%);
  color: #fff;
  font-size: 13px;
  font-weight: bold;
  font-style: normal;
  cursor: help;
  box-shadow: 0 2px 8px rgba(230, 162, 60, 0.45);
  transition: transform 0.2s, box-shadow 0.2s;
}
.summary-hint-icon:hover {
  transform: scale(1.1);
  box-shadow: 0 3px 12px rgba(230, 162, 60, 0.55);
}
.summary-hint-label {
  margin-left: 4px;
  font-size: 12px;
  color: #606266;
  vertical-align: middle;
}
.summary-hint-tooltip {
  display: none;
  position: absolute;
  left: 0;
  top: 100%;
  margin-top: 6px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
  font-size: 13px;
  line-height: 1.5;
  color: #303133;
  white-space: normal;
  width: 280px;
  z-index: 2000;
}
.summary-hint-wrap:hover .summary-hint-tooltip {
  display: block;
}
.summary-hint-tooltip-title {
  display: block;
  color: #409eff;
  font-weight: 600;
  margin-bottom: 6px;
}
.summary-hint-tooltip-tip {
  display: block;
  color: #606266;
  font-size: 12px;
}

.left-summary-topics {
  width: 40%;
  height: 100%;
  font-size: 15px;
  padding: 5px;
  overflow-y: auto;
}

.left-summary-topics-title {
  width: 100%;
  font-size: 22px;
}

.left-summary-topics-item {
  width: 100;
  overflow-x: hidden;
  margin: 10px;
  background-color: #d0cfcf;
  border-radius: 20px;
  padding: 5px;
  cursor: pointer;

  &:hover {
    background-color: #fff;
  }
}

.left-text {
  height: 80vh;
  width: 96%;
  // width: 90%;
  word-break: break-all;
  text-indent: 2em;
  overflow-y: auto;
  overflow-x: auto;
  padding: 2%;
  // padding: 5%;
  transition: 0.5s ease;
  white-space: pre-wrap;
}

.model-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 9;
  width: 40vw;
  height: 60vh;
  max-width: 100%;
}

.model-modelList {
  height: 90%;
  overflow: auto;
}

.model-dialog .model-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.model-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}




.bgc-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 9;
  width: 40vw;
  height: 60vh;
  max-width: 100%;
}

.bgc-bgcList {
  height: 90%;
  overflow: auto;
}

.bgc-dialog .bgc-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.bgc-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}


.img-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 15;
  width: 70vw;
  height: 80vh;
  max-width: 100%;
}

.img-dialog .img-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.img-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}

.img-dialog-body {
  width: 100%;
  height: 100%;
  display: flex;
}

.img-dialog-body-left {
  height: 90%;
  width: 50%;
  object-fit: cover;
}

.img-dialog-body-left img {
  width: 100%;
  height: 100%;
  object-position: center;
}

.img-dialog-body-right {
  height: 90%;
  width: 50%;
}

.img-dialog-body-rightup {
  height: 76%;
  width: 90%;
  background-color: #ddf9fd;
  font-size: 15px;
  text-indent: 2em;
  overflow: auto;
  padding: 5%;
}

.img-dialog-body-rightdown {
  height: 14%;
  width: 100%;
  background-color: #68f789;
}

.img-dialog-list {
  width: 90%;
  height: 100%;

  overflow: hidden;
  overflow-x: auto;
  white-space: nowrap;
}

.img-dialog-list-item {
  display: inline-block;
  margin: 0 5px;
  margin-top: 10px;
  height: 55%;
  overflow-x: hidden;
  font-size: 18px;
  padding: 4px;
  background-color: #fff;
  border-radius: 10px;
  vertical-align: middle;
  transition: 0.5s ease;
  cursor: pointer;

  &:hover {
    background-color: #9f9f9f;
  }
}


.topic-dialog {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  border: 1px solid #ccc;
  background-color: #fff;
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
  z-index: 9;
  width: 40vw;
  height: 60vh;
  max-width: 100%;
}

.topic-dialog .topic-dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.topic-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}

.topic-select-list {
  height: 80%;
  width: 100%;
  overflow-y: auto;
}

.topic-list-item {
  width: 400px;
  height: 100px;
  border-radius: 20px;
  background-color: rgb(50, 54, 68);
  position: relative;
  margin: auto;
  margin-top: 20px;
  cursor: pointer;

  .info {
    position: absolute;
    left: 50%;
    top: 50%;
    width: 90%;
    transform: translate(-50%, -50%);
    overflow: hidden;
    display: flex;

    .info-detail {
      margin-top: 5px;
      margin-left: 20px;

      .name {
        color: #fff;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        margin-bottom: 5px;
      }

      .detail {
        color: #5c6675;
        overflow: hidden;
        white-space: nowrap;
        text-overflow: ellipsis;
        font-size: 12px;
      }
    }
  }

  &:hover {
    background-color: #1d90f5;
    transition: 0.3s;
    box-shadow: 0px 0px 10px 0px rgb(0, 136, 255);

    // box-shadow:  0 5px 20px rgba(251, 152, 11, .5);
    .info {
      .info-detail {
        .detail {
          color: #fff;
        }
      }
    }
  }
}


// .topic-rel-list-item {
//   width: 400px;
//   min-height: 40px;
//   word-wrap: break-word;
//   border-radius: 20px;
//   background-color: rgb(50, 54, 68);
//   position: relative;
//   margin: auto;
//   margin-top: 20px;
//   cursor: pointer;

//   .info {
//     position: absolute;
//     left: 50%;
//     top: 50%;
//     width: 90%;
//     transform: translate(-50%, -50%);
//     display: flex;

//     .info-detail {
//       margin-top: 5px;
//       margin-left: 20px;

//       .name {
//         color: #fff;
//         white-space: nowrap;
//         word-wrap: break-word;
//         white-space: normal;
//         margin-bottom: 5px;
//       }
//     }
//   }

//   &:hover {
//     background-color: #1d90f5;
//     transition: 0.3s;
//     box-shadow: 0px 0px 10px 0px rgb(0, 136, 255);

//     // box-shadow:  0 5px 20px rgba(251, 152, 11, .5);
//     .info {
//       .info-detail {
//         .detail {
//           color: #fff;
//         }
//       }
//     }
//   }
// }

.topic-rel-list-item {
  width: 400px;
  min-height: 40px;
  word-wrap: break-word;
  border-radius: 20px;
  background-color: rgb(50, 54, 68);
  position: relative;
  margin: auto;
  margin-top: 20px;
  cursor: pointer;
  padding: 15px 20px;  /* 添加内边距 */

  .info {
    /* 移除绝对定位 */
    /* position: absolute;
    left: 50%;
    top: 50%;
    transform: translate(-50%, -50%); */
    width: 100%;
    display: flex;
    align-items: center;  /* 垂直居中 */

    .info-detail {
      /* margin-top: 5px; */  /* 不需要了 */
      /* margin-left: 20px; */  /* 不需要了，用父容器padding */
      width: 100%;  /* 添加 */

      .name {
        color: #fff;
        word-wrap: break-word;
        overflow-wrap: break-word;  /* 添加 */
        white-space: normal;  /* 保留这个，移除nowrap */
        line-height: 1.5;  /* 添加行高 */
      }
    }
  }

  &:hover {
    background-color: #1d90f5;
    transition: 0.3s;
    box-shadow: 0px 0px 10px 0px rgb(0, 136, 255);

    .info {
      .info-detail {
        .detail {
          color: #fff;
        }
      }
    }
  }
}

.myDialogParam {
  position: relative;
  top: -40px;
  width: 750px;
  height: 570px;
  border-radius: 10px;
  // background: transparent;
  // background-image: url('https://pic1.zhimg.com/v2-d1bacfc77261b554e8fc65a43efd7880_r.jpg');
  // background-image: url('https://img.tukuppt.com/ad_preview/00/05/01/5c98cdf474338.jpg!/fw/980');
  // background-image: url('https://bpic.588ku.com/back_our/bg/20201021/bg/d22a73a368c76_431735.jpg');
  background-size: 100% 100%;
}

.myDialogSpeak {
  position: relative;
  top: -40px;
  width: 750px;
  height: 570px;
  border-radius: 10px;
  background-size: 100% 100%;
}
/* 遮罩层的样式 */
.custom-backdrop {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  // background-color: rgb(15, 63, 33);
  // background-color: rgb(27, 114, 60);
  background-color: rgb(48, 212, 111);
  z-index: 999; /* 确保遮罩层在其他元素之上 */
  display: flex;
  justify-content: center;
  align-items: center;
}
/* 定义过渡的样式 */
.fade-enter-active, .fade-leave-active {
  transition: opacity 0.6s ease-in-out;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}


.myDialogPlus {
  position: relative;
  top: -40px;
  width: 750px;
  height: 570px;
  border-radius: 10px;
  background-size: 100% 100%;
  overflow-y: auto;
}

.myDialogPlusLUI1,
.myDialogPlusLUI2 {
  position: relative;
  top: -40px;
  width: 750px;
  height: 570px;
  border-radius: 10px;
  background-size: 100% 100%;
  overflow-y: auto;
}

.myDialogParamInner {
  position: relative;
  top: -20px;
  width: 750px;
  height: 500px;
  border-radius: 10px;
  background: transparent;
  background-image: url('https://pic1.zhimg.com/v2-d1bacfc77261b554e8fc65a43efd7880_r.jpg');
  background-size: 100% 100%;
}

.myDialogParamInfo {
  position: relative;
  top: 80px;
  width: 400px;
  height: 300px;
  border-radius: 10px;
  background: transparent;
  background-image: url('https://img.51miz.com/Element/00/81/24/29/076d7b3d_E812429_87bc8600.jpg');
  background-size: 100% 100%;
}


.slider-demo-block {
  max-width: 300px;
  display: flex;
  align-items: center;
  margin: 0 auto 0 0;
  /* 水平靠左 */
  margin-left: 10px;
}

.slider-demo-block .el-slider {
  margin-top: 0;
  margin-left: 12px;
}

.slider-demo-block .demonstration {
  font-size: 14px;
  font-weight: bold;
  color: var(--el-text-color-secondary);
  line-height: 44px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 0;
}

.slider-demo-block .highlight {
  font-size: 14px;
  color: red;
  /* 设置高亮颜色 */
  // line-height: 44px;
  // flex: 1;
  // overflow: hidden;
  // text-overflow: ellipsis;
  // white-space: nowrap;
  // margin-bottom: 0;
}

.slider-demo-block .demonstration+.el-slider {
  flex: 0 0 65%;
}

// .slider-demo-block .highlight + .el-slider {
//   flex: 0 0 70%;
// }


.slider-demo-block2 {
  max-width: 300px;
  display: flex;
  align-items: center;
  margin: 0 0 0 auto;
  /* 水平靠右 */
  margin-right: 10px;
}

.slider-demo-block2 .el-slider {
  margin-top: 0;
  margin-left: 12px;
}

.slider-demo-block2 .demonstration {
  font-size: 14px;
  font-weight: bold;
  color: var(--el-text-color-secondary);
  line-height: 44px;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-bottom: 0;
}

.slider-demo-block2 .highlight {
  font-size: 14px;
  color: red;
  /* 设置高亮颜色 */
}

.slider-demo-block2 .demonstration+.el-slider {
  flex: 0 0 65%;
}


.param-container {
  display: flex;
  // margin-bottom: 10px;
  margin-top: 20px;
}

.el-button.is-active {
  /* 激活状态的样式 */
  color: #fff;
  background-color: #669fd7;
  border-color: #409eff;
}

.mask-layer {
  position: absolute;
  top: 140px;
  left: 20px;
  width: 95%;
  height: 65%;
  background-color: rgba(115, 62, 230, 0.5);
  /* 半透明遮罩层 */
  z-index: 10;
  /* 确保遮罩层在最上层 */
  display: flex;
  justify-content: center;
  align-items: center;
  /* 居中遮罩层内容，如果有的话 */
  font-size: 35px;
  font-weight: bold;
  color: #b72424;
  letter-spacing: 2px;
  user-select: none;
  /* 禁止用户选择文本 */
}


.spider-web-container {
  position: relative;
  top: 48px;
  width: 96%;
  height: 460px;
  margin: 0 auto;
}

.center-point {
  width: 10px;
  height: 10px;
  background-color: #333;
  border-radius: 50%;
  position: absolute;
}




.web-ray {
  position: absolute;
  width: 1px;
  height: 200px;
  /* Adjust the height as needed */
  background-color: #ccc;
  transform-origin: 50% 100%;
}

.data-point {
  position: absolute;
  width: 20px;
  height: 20px;
  background-color: #409eff;
  border-radius: 50%;
  cursor: grab;
}

.data-point:active {
  cursor: grabbing;
}


.voice-background {
  position: absolute;
  top: 0px;
  left: 62vw;
  font-size: 15px;
  font-weight: bold;
}

.scene-name {
  position: absolute;
  top: 0px;
  left: 80px;
  font-size: 15px;
  font-weight: bold;
}

.sub-scene-name {
  position: absolute;
  top: 20px;
  left: 80px;
  font-size: 15px;
  font-weight: bold;
}

.change-sub-scene {
  position: absolute;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
}

.change-sub-scene-active {
  color: white;
  background-color: rgb(72, 72, 74); /* 按钮背景颜色变深 */
  border-radius: 4px;
}

.change-plus {
  position: absolute;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
  color: rgb(51, 41, 41);
  background-color: rgb(203, 81, 81);
  border-color: rgb(203, 81, 81);
  border-radius: 4px;
  // margin-left: 0;
}

.change-plus-active {
  color: rgb(235, 227, 227);
  background-color: #8B3626; /* 按钮背景颜色变深 */
  border-color: #8B3626;
  border-radius: 4px;
}

.change-multiQAScore {
  position: absolute;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
  color: rgb(226, 216, 235);
  background-color: rgb(114, 81, 203);
  border-color: rgb(114, 81, 203);
  border-radius: 4px;
  // margin-left: 0;
}

.change-multiQAScore-active {
  color: rgb(226, 216, 235);
  background-color: #5e268b; /* 按钮背景颜色变深 */
  border-color: #5e268b;
  border-radius: 4px;
}

.open-config {
  position: absolute;
  top: 20px;
  font-size: 14px;
  font-weight: bold;
  color: rgb(51, 41, 41);
  background-color: rgb(203, 81, 81);
  border-color: rgb(203, 81, 81);
  border-radius: 4px;
}

.button-container {
  display: flex;           /* 使用 flex 布局 */
  justify-content: flex-start; /* 默认从容器的最后位置排列 */
  align-items: center;     /* 垂直居中对齐 */
  position: relative; /* 为绝对定位的子元素提供参考 */
}


.feedback-item {
  margin-bottom: 20px;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
}


.voice-container {
  position: absolute;
  top: 0vh;
  height: 100vh;
  width: 100vw;
  background-color: rgba(0, 0, 0, 0.8);
  z-index: 9999;
}

.voice-dialog-header {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  top: 0;
  width: 100%;
  height: 5vh;
  position: relative;
}

.voice-dialog-close {
  position: absolute;
  right: 1em;
  top: 50%;
  transform: translateY(-50%);
  font-size: 2em;
  color: white;
  cursor: pointer;
}

.voice-dialog-body {
  height: 95vh;
  width: 100vw;
}

.voice-dialog-chatwindow {
  height: 50vh;
}

.voice-asr {
  height: 25vh;
}

.voice-tts {
  height: 25vh;
  align-items: center;
  justify-content: center;
  display: flex;
}

.tts-input-visible {
  white-space: pre-wrap;
  line-height: 1em;
  width: 80%;
  min-height: 15vh;
  max-height: 30vh;
  background-color: white;
  text-align: left;
  overflow-y: auto;
  resize: none;
  font-size: 2em;
  word-wrap: break-word;
  overflow-wrap: break-word;
  vertical-align: top;
  padding: 0.5em;
  box-shadow: 10px 10px 50px rgba(255, 255, 255, 0.3);
  transition: box-shadow 0.3s ease;

  &:hover {
    box-shadow: 15px 15px 50px rgba(255, 255, 255, 0.5);
  }
}

.voice-dialog-navigator {
  height: 20vh;
  margin-top: 20vh;
}


.sound-sonic_wave {
  width: 100vw;
  height: 20vh;
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 10000;
}

.voice-middle-btn {
  width: 100vw;
  height: 20vh;
  z-index: 10001;
  position: relative;
}

.voice-wave {
  position: absolute;
  top: calc((100% - 60px)/2);
  left: calc((100% - 60px)/2);
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background-attachment: fixed;
  background-position: center center;
}

.voice-circle {
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
  z-index: 10004;
}

.w1 {
  z-index: 10002;
  border: 1px solid red;
  background-size: auto 106%;
  /* animation: wave 1s infinite; */
  animation: none;
}

.w2 {
  z-index: 10003;
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


#pdf-viewer {
  width: 100%;        /* 占满容器宽度 */
  height: 400px;      /* 设置一个合适的高度，或使用 min-height 以适应内容 */
  overflow: auto;     /* 如果内容超出了容器，显示滚动条 */
  position: relative; /* 相对定位，以便正确地包含 Viewer.js 的元素 */
  border: 1px solid #ddd; /* 边框，根据需要调整 */
  box-sizing: border-box; /* 边框计算在宽度和高度内 */
  z-index: 10000;
}


.dialog-content {
  display: flex;
  justify-content: space-around;
  overflow-y: auto;
}

.dialog-content-plus {
  white-space: pre-wrap; /* 保持文本的格式并允许换行 */
  overflow-y: auto;
  overflow-x: hidden;        /* 隐藏横向滚动条 */
  padding: 10px; /* 增加一些内边距 */
}

.config-section {
  width: 45%;
  margin: 0 20px;
}

.import-button-container{
  margin-bottom: 10px;
  margin-left: 20px;
}



.card-rate-left {
  display: flex;
  /* 启用 Flexbox */
  justify-content: center;
  /* 水平居中 */
  align-items: center;
  /* 垂直居中 */
  width: 30px;
  height: 30px;
  border-radius: 6px;
  background-color: #911787;
  font-size: 14px;
  font-weight: bold;
  color: #000000;
}

.lui1-plus-icon {
  display: inline-block;
  width: auto;            /* 设置为自动，以适应内容 */
  height: auto;
  border-radius: 50%;
  color: #f5e3ff;
  text-align: center;
  line-height: 20px;
  font-size: 14px;
  margin-left: 45px;
  background-color: #6112b5;
  cursor: pointer;
  padding: 4px;           /* 内边距，确保文字不会太靠近边框 */
  box-sizing: border-box;  /* 边框计算在宽度和高度内 */
  &:hover {
    background-color: #40057f;
  }
}

.history-icon {
  position: absolute;
  right: 145px; /* 根据需要调整这个值来定位图标到合适的位置 */

  display: inline-block;
  width: auto;            /* 设置为自动，以适应内容 */
  height: auto;
  border-radius: 50%;
  color: #f5e3ff;
  text-align: center;
  line-height: 20px;
  font-size: 13px;
  font-weight: bold;
  margin-left: 15px;
  color: #2f360c;
  background-color: #97b512;
  cursor: pointer;
  padding: 4px;           /* 内边距，确保文字不会太靠近边框 */
  box-sizing: border-box;  /* 边框计算在宽度和高度内 */
  &:hover {
    background-color: #819b10;
  }
}

.usersum-icon {
  position: absolute;
  right: 100px; /* 根据需要调整这个值来定位图标到合适的位置 */

  display: inline-block;
  width: auto;            /* 设置为自动，以适应内容 */
  height: auto;
  border-radius: 50%;
  color: #f5e3ff;
  text-align: center;
  line-height: 20px;
  font-size: 13px;
  font-weight: bold;
  margin-left: 15px;
  color: #4d3a0f;
  background-color: #c6901b;
  cursor: pointer;
  padding: 4px;           /* 内边距，确保文字不会太靠近边框 */
  box-sizing: border-box;  /* 边框计算在宽度和高度内 */
  &:hover {
    background-color: #ad7e19;
  }
}



.img-button {
  margin-left: 10px;
  border: 0;
  transition: 0.3s;
  box-shadow: 0px 0px 5px 0px rgb(125, 125, 125);
  cursor: pointer;

  &:hover {
    box-shadow: 0px 0px 10px 0px rgb(0, 0, 0);
  }
}

.rating-container {
  display: flex;
  align-items: center;
  justify-content: flex-start;  /* 水平方向从开始位置排列 */
}

.override-icon {
  display: inline-block;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  color: #f5f5f5;
  text-align: center;
  line-height: 20px;
  font-size: 14px;
  margin-left: 10px;
  cursor: pointer;
  background-color: #b94291;
  &:hover {
    background-color: #8f1e69;
  }
}



.createCardQuestion .el-dialog {
  width: 60%;
  /* 根据需要调整宽度 */
  border-radius: 8px;
  /* 轻微圆角 */
  overflow: hidden;
  /* 隐藏溢出内容 */
  background-color: #ffffff;
  /* 背景色 */
  box-shadow: 0 4px 12px 0 rgba(0, 0, 0, 0.1);
  /* 添加阴影 */
}

.createCardQuestion .el-dialog__header {
  padding: 15px 20px;
  /* 头部内边距 */
  background-color: #eef1f6;
  /* 淡蓝色背景 */
  border-bottom: 1px solid #d3dce6;
  /* 下边框 */
}

.createCardQuestion .el-dialog__title {
  font-size: 18px;
  /* 标题字体大小 */
  color: #333;
  /* 标题颜色 */
}

.createCardQuestion .el-dialog__body {
  padding: 20px;
  /* 内容区域内边距 */
}

/* 追问标题样式 */
.createCardQuestion .cardQuestion {
  margin: 0 0 20px;
  /* 重置外边距和下边距 */
  font-size: 16px;
  /* 字体大小 */
  color: #333;
  /* 字体颜色 */
  text-align: center;
  /* 文本居中 */
}

/* 自定义追问按钮样式 */
.createCardQuestion .userDefineButton {
  margin-left: 10px;
  /* 与输入框的间距 */
  padding: 8px 15px;
  /* 内边距 */
  font-size: 14px;
  /* 字体大小 */
  border: none;
  /* 无边框 */
  border-radius: 4px;
  /* 圆角 */
  background-color: #67c23a;
  /* 背景色 */
  color: white;
  /* 字体颜色 */
  transition: background-color 0.3s;
  /* 渐变效果 */
}

.createCardQuestion .userDefineButton:hover {
  background-color: #85ce61;
  /* 鼠标悬停效果 */
}

.inline-form {
  display: flex;
  align-items: center;
  /* 垂直居中对齐 */
}

.input-button-group {
  // flex: 1;
  // /* 让这个容器占据剩余空间 */
  // display: flex;
  // /* 使用flex布局 */
  // align-items: center;
  // /* 垂直居中对齐 */
  // justify-content: flex-start;
  // /* 水平开始对齐 */

  display: flex;
  flex-direction: column;
  width: 100%;
}

.actions-row {
  display: flex;
  flex-direction: column;
  align-items: flex-start;  /* 这行很重要，确保其子元素靠左 */
  width: 100%;              /* 占满整行 */
  margin-top: 10px;
  margin-bottom: 10px;
}

/* 添加这个选择器确保上传组件靠左 */
.el-upload {
  display: block;
  text-align: left !important;
  margin-left: 0 !important;
}
/* 如果Element UI有自己的居中样式，可能需要覆盖它 */
.el-upload-list {
  text-align: left !important;
}

.card-image-upload {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  margin-left: 0;           /* 确保靠左 */
  width: auto;              /* 宽度自适应内容 */
}

.card-image-upload .el-upload-list {
  margin-top: 8px;
}



/* 上传组件样式 */
.card-image-upload ::v-deep .el-upload-dragger {
  width: 300px;
  height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  border: 2px dashed #d9d9d9;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.3s;
}

.card-image-upload ::v-deep .el-upload-dragger:hover {
  border-color: #409eff;
}

.upload-content {
  text-align: center;
}

.upload-content .el-icon-upload {
  font-size: 40px;
  color: #c0c4cc;
  margin-bottom: 10px;
}

.upload-text {
  color: #606266;
  font-size: 14px;
  margin-bottom: 5px;
}

.upload-text em {
  color: #409eff;
  font-style: normal;
}

.upload-tip {
  color: #909399;
  font-size: 12px;
}

/* 图片预览样式 */
.image-preview {
  position: relative;
  display: inline-block;
  max-width: 200px;
  max-height: 150px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.image-preview img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.image-preview .remove-btn {
  position: absolute;
  top: 5px;
  right: 5px;
  width: 24px;
  height: 24px;
  padding: 0;
}

/* 隐藏默认的文件列表 */
.card-image-upload ::v-deep .el-upload-list {
  display: none;
}



.custom-select-wrapper {
  position: relative;
  display: inline-block;
  left: 26px;
  width: 200px; /* 根据需要调整宽度 */
}
.emotion-select-wrapper {
  position: relative;
  display: inline-block;
  left: 52px;
  width: 200px; /* 根据需要调整宽度 */
}

.custom-select-wrapper:after,
.emotion-select-wrapper:after {
  content: '\25BC'; /* 下拉箭头字符 */
  position: absolute;
  right: 17px;
  top: 50%;
  transform: translateY(-50%);
  pointer-events: none; /* 防止箭头捕获点击事件 */
  color: #2e6805; /* 根据需要调整箭头颜色 */
}

.custom-select-wrapper:before,
.emotion-select-wrapper:before {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: 1em;
  pointer-events: none; /* 防止捕获点击事件 */
  background: #094331; /* 根据需要调整背景颜色 */
}

.custom-select-display,
.emotion-select-display {
  padding: 10px;
  border: 1px solid #094e17;
  border-radius: 5px;
  background-color: #063214;
  color: #17e593da;
  font-size: 16px;
  cursor: pointer;
}

.custom-select-options,
.emotion-select-options {
  margin-top: 5px;
  position: absolute;
  width: 100%;
  background-color: #043122;
  border: 1px solid #094e17;
  border-radius: 5px;
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
  z-index: 100;
}

.custom-select-option,
.emotion-select-option {
  padding: 10px;
  color: #22c99d;
  border-bottom: 1px solid #083a12;
  cursor: pointer;
}

.custom-select-option:last-child,
.emotion-select-option:last-child {
  border-bottom: none;
}

.custom-select-option:hover,
.emotion-select-option:hover {
  background-color: #084723;
  border: 1px solid #073a12; /* 根据需要调整边框 */
}

.custom-select-option.is-selected,
.emotion-select-option.is-selected {
  background-color: #074029;
  border: 1px solid #052b0d; /* 根据需要调整边框 */
}




.card-src-btn,
.card-obj-btn {
  height: 40px;
  width: 120px;
  margin-bottom: 15px;
  padding: 2px 4px; /* 保持原定的padding */
  border: none; /* 无边框 */
  border-radius: 4px; /* 保持原定的圆角 */
  cursor: pointer; /* 鼠标悬停时显示手形光标 */
  box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2); /* 轻微的阴影，增加了深度 */
  transition: 
    box-shadow 0.3s ease-in-out, 
    background-color 0.3s ease-in-out,
    transform 0.1s ease-out; /* 平滑的阴影和背景颜色过渡 */
  letter-spacing: 0.5px; /* 字母间距微调，提升视觉效果 */
  text-transform: uppercase; /* 所有字母大写，增加正式感 */
  overflow: hidden; /* 确保阴影不会溢出 */
  position: relative; /* 为添加元素做准备 */
}

.card-src-btn::before,
.card-obj-btn::before {
  content: ''; /* 创建一个伪元素 */
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(45deg, rgba(255, 255, 255, 0.1), rgba(0, 0, 0, 0.1));
  transform: scale(0);
  transition: transform 0.3s ease-in-out; /* 伪元素过渡动画 */
}

.card-src-btn:hover,
.card-obj-btn:hover {
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3); /* 鼠标悬停时更大的阴影 */
  transform: translateY(-2px); /* 轻微提升，制造按下效果 */
}

.card-src-btn:hover::before,
.card-obj-btn:hover::before {
  transform: scale(1); /* 鼠标悬停时伪元素放大，增加光泽感 */
}

/* 原文件按钮 */
.card-src-btn {
  background-color: #5e3380; /* 深蓝色背景，保持神秘感 */
  color: rgb(255, 255, 255); /* 白色文字 */
}

.card-src-btn:hover {
  background-color: #4b2355; /* 鼠标悬停时更深的蓝色 */
}

/* 双语对比按钮 */
.card-obj-btn {
  background-color: #8B3626;
  color: white;
}

.card-obj-btn:hover {
  background-color: #5C2121;
}

.card-hg-btn {
  background-color: #2f5d8a;
}

.card-hg-btn:hover {
  background-color: #234a6e;
}


.flexing-button {
  cursor: pointer;
  width: 30px;
  height: 30px;
  // background-color: #70dfc7;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  display: inline-block;
  vertical-align: top;
  border-radius: 20px;
  // margin: auto;
  transition: background-color 0.5s;

  &:hover {
    background-color: #b7b7b7;
  }
}

.flexing-button.flexBtnChecked {
  background-image: url('@/assets/img/chatwindow/EpDArrowLeft.png');
}

.flexing-button:not(.flexBtnChecked) {
  background-image: url('@/assets/img/chatwindow/EpDArrowRight.png');
}


// 拖拽测试demo
.draggable {
  width: 100px;
  height: 100px;
  background-color: lightblue;
  position: absolute;
  cursor: move;
}

.el-icon-tag {
  background-image: url('@/assets/img/cardwindow/tagSearchOutline.png');
  background-size: contain;
  background-repeat: no-repeat;
  display: inline-block;
  width: 20px;
  height: 20px;
}


// 添加高亮效果的样式
.chat-window-container {
  position: relative;  // 用于定位遮罩层
}

.close-mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(55, 57, 59, 0.933);  // 使用半透明的蓝色
  border: 2px dashed #7a7c7d;  // 添加虚线边框
  border-radius: 8px;  // 圆角边框
  z-index: 100;  // 确保遮罩层在内容之上
  
  // 添加动画效果
  animation: maskClosePulse 4.5s infinite;
  
  // 添加提示文本
  &::after {
    content: "此窗口模型关闭，再次点击可选择模型打开";
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: #101011;
    font-size: 18px;
    font-weight: bold;
    text-shadow: 0 0 14px rgba(255, 255, 255, 0.995);
  }
}

.drop-mask {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(29, 144, 245, 0.15);  // 使用半透明的蓝色
  border: 2px dashed #1d90f5;  // 添加虚线边框
  border-radius: 8px;  // 圆角边框
  z-index: 100;  // 确保遮罩层在内容之上
  pointer-events: none;  // 确保不影响拖拽操作
  
  // 添加动画效果
  animation: maskPulse 1.5s infinite;
  
  // 添加提示文本
  &::after {
    content: "拖放至此处合并";
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    color: #1d90f5;
    font-size: 18px;
    font-weight: bold;
    text-shadow: 0 0 10px rgba(255, 255, 255, 0.8);
  }
}

// 添加遮罩层的呼吸动画
@keyframes maskClosePulse {
  0% {
    background-color: rgb(55, 57, 59);
  }
  50% {
    background-color: rgba(55, 57, 59, 0.99);
  }
  100% {
    background-color: rgb(55, 57, 59);
  }
}

@keyframes maskPulse {
  0% {
    background-color: rgba(29, 144, 245, 0.15);
  }
  50% {
    background-color: rgba(29, 144, 245, 0.3);
  }
  100% {
    background-color: rgba(29, 144, 245, 0.15);
  }
}

// 当拖拽经过时的效果
.chat-window-container {
  &[draggover="true"] .drop-mask {
    background-color: rgba(29, 144, 245, 0.3);
    border-style: solid;
  }
}



// 多轮对话历史tooltip
.tooltip-container {
  position: fixed;
  /* 会根据点击的span位置动态计算 */
  transform: translateX(-50%);
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 0.5rem;
  padding: 1rem;
  // width: 16rem;
  width: 256px; /* 固定宽度 */
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
  z-index: 1000;
}

/* 添加小三角形指示器 */
.tooltip-container::after {
  content: '';
  position: absolute;
  bottom: -8px;
  left: 50%;
  transform: translateX(-50%);
  border-width: 8px 8px 0;
  border-style: solid;
  border-color: white transparent transparent;
}

/* 添加小三角形的边框 */
.tooltip-container::before {
  content: '';
  position: absolute;
  bottom: -9px;
  left: 50%;
  transform: translateX(-50%);
  border-width: 9px 9px 0;
  border-style: solid;
  border-color: #e2e8f0 transparent transparent;
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
}

.toggle-switch {
  position: relative;
  width: 2.75rem;
  height: 1.5rem;
  border-radius: 9999px;
  background-color: #e2e8f0;
  transition: background-color 0.2s;
}

.toggle-switch.enabled {
  background-color: #2563eb;
}

.toggle-dot {
  position: absolute;
  top: 0.25rem;
  left: 0.25rem;
  width: 1rem;
  height: 1rem;
  background-color: white;
  border-radius: 9999px;
  transition: transform 0.2s;
}

.toggle-dot.enabled {
  transform: translateX(1.25rem);
}

.rounds-container {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.rounds-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.label {
  font-size: 0.875rem;
  font-weight: 500;
  color: #4b5563;
}

.rounds-input {
  width: 4rem;
  padding: 0.25rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.25rem;
  font-size: 0.875rem;
}

.rounds-slider {
  width: 100%;
  height: 0.5rem;
  background-color: #e2e8f0;
  border-radius: 9999px;
  cursor: pointer;
}

.range-limits {
  display: flex;
  justify-content: space-between;
  font-size: 0.75rem;
  color: #6b7280;
}




// 流式输出测试用的
.stream-test-section {
  margin: 20px 0;
  padding: 15px;
  border: 1px solid #ddd;
  border-radius: 5px;
}

.test-input {
  width: 100%;
  padding: 10px;
  margin-bottom: 10px;
  border: 1px solid #ccc;
  border-radius: 4px;
  font-family: inherit;
}

.test-button {
  background-color: #4CAF50;
  color: white;
  padding: 10px 15px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  margin-bottom: 15px;
}

.test-button:hover {
  background-color: #45a049;
}

.result-container {
  min-height: 200px;
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #eee;
  padding: 10px;
  border-radius: 4px;
  background-color: #f9f9f9;
  white-space: pre-wrap;
  font-family: monospace;
}

.loading {
  color: #666;
  font-style: italic;
}

.partial-result {
  color: #333;
}

.placeholder {
  color: #999;
  text-align: center;
  padding: 20px;
}




// 图片文档红蓝卡标指示器
/* HLScore指示器样式 */
.hl-score-indicator {
  position: relative;
  display: inline-block;
  margin: 0 10px;
}

.score-circle {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  color: white;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.2s;
}

.score-circle:hover {
  transform: scale(1.1);
}

.score-tooltip {
  position: absolute;
  top: 30px; /* 紧贴圆圈底部，消除空隙 */
  left: 50%;
  transform: translateX(-50%);
  width: 300px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  z-index: 1000;
  overflow: hidden;
  animation: fadeIn 0.2s ease-in-out;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateX(-50%) translateY(-10px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

.tooltip-header {
  padding: 10px 15px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: white;
}

.tooltip-score {
  font-size: 18px;
  font-weight: bold;
}

.tooltip-color {
  font-size: 14px;
  opacity: 0.9;
}

.tooltip-content {
  padding: 15px;
  font-size: 14px;
  line-height: 1.5;
  max-height: 200px;
  overflow-y: auto;
  color: #333;

  white-space: pre-line; /* 保持换行 */
}



.content-wrapper {
  display: inline-flex;        /* 使内容内联显示 */
  align-items: center;         /* 垂直居中 */
  white-space: nowrap;         /* 防止换行 */
}

.custom-switch {
  width: 30px;          /* 总宽度 */
  height: 15px;         /* 总高度 */
  // bottom: 18px;
  // left: 150px;
  margin-left: 15px;
  background-color: #9d9c9c; /* 关闭状态颜色 */
  border-radius: 15px;  /* 圆角，形成圆形开关 */
  position: relative;
  cursor: pointer;
  transition: background-color 0.3s;
}

.custom-switch.active {
  background-color: #4CAF50; /* 开启状态颜色（绿色） */
}

.switch-thumb {
  width: 13px;          /* 滑块宽度 */
  height: 13px;         /* 滑块高度 */
  background-color: #fff; /* 滑块颜色 */
  border-radius: 50%;   /* 完全圆形 */
  position: absolute;
  top: 1px;             /* 垂直居中 */
  left: 1px;            /* 初始位置（关闭状态） */
  transition: left 0.3s; /* 滑块移动动画 */
}

.custom-switch.active .switch-thumb {
  left: 16px;           /* 开启状态位置（向右移动） */
}

/* 🔥 当前状态文字显示（仅显示，不操作） */
.system-status-text {
  margin-left: 15px;
  font-size: 0.9rem;
  color: #334155;
  font-weight: bold;
  white-space: nowrap;
}

/* 🔥 本子信息显示 */
.notebook-info-text {
  margin-left: 15px;
  font-size: 0.9rem;
  color: #334155;
  font-weight: bold;
  white-space: nowrap;
}



/* 添加到现有的style部分 */
.spinner-container {
  display: flex;
  justify-content: center;
  margin-bottom: 15px;
}

.spinner {
  width: 40px;
  height: 40px;
  border: 4px solid rgba(0, 123, 255, 0.2);
  border-radius: 50%;
  border-top-color: #007bff;
  animation: spin 1s ease-in-out infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.loading-overlay {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 400px;
  text-align: center;
  z-index: 1000;
  background: rgba(255, 255, 255, 0.95);
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.loading-overlay-trans {
  position: absolute;
  top: 70%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 400px;
  text-align: center;
  z-index: 1000;
  background: rgba(255, 255, 255, 0.95);
  padding: 20px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.progress-bar {
  width: 100%;
  height: 24px;
  background-color: #f0f0f0;
  border-radius: 12px;
  overflow: hidden;
  margin-bottom: 15px;
  position: relative;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(45deg, #007bff, #0056b3);
  transition: width 0.3s ease;
  border-radius: 12px;
  position: relative;
}

.progress-fill::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  right: 0;
  background-image: linear-gradient(
    -45deg,
    rgba(255, 255, 255, 0.2) 25%,
    transparent 25%,
    transparent 50%,
    rgba(255, 255, 255, 0.2) 50%,
    rgba(255, 255, 255, 0.2) 75%,
    transparent 75%,
    transparent
  );
  background-size: 50px 50px;
  animation: move 2s linear infinite;
}

@keyframes move {
  0% {
    background-position: 0 0;
  }
  100% {
    background-position: 50px 50px;
  }
}

.progress-text {
  color: #333;
  font-size: 16px;
  font-weight: 500;
  margin-bottom: 8px;
}

.progress-details {
  color: #666;
  font-size: 14px;
  font-family: monospace;
}




/* 红蓝卡标阈值滑动条样式 */
.threshold-slider-container {
  display: inline-flex;
  align-items: center;
  margin-left: 15px;
  padding: 8px 12px;
  background-color: rgba(255, 255, 255, 0.9);
  border-radius: 6px;
  border: 1px solid #e0e0e0;
}

.threshold-label {
  font-size: 12px;
  color: #333;
  font-weight: 500;
  margin-right: 10px;
  white-space: nowrap;
}

.slider-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.threshold-slider {
  width: 120px;
}

.threshold-value {
  font-size: 12px;
  color: #007bff;
  font-weight: bold;
  min-width: 30px;
  text-align: center;
}

/* 重写Element Plus滑动条样式 */
.threshold-slider-container .el-slider__runway {
  height: 4px;
  background-color: #e4e7ed;
}

.threshold-slider-container .el-slider__bar {
  background-color: #007bff;
}

.threshold-slider-container .el-slider__button {
  width: 16px;
  height: 16px;
  border: 2px solid #007bff;
  background-color: #ffffff;
}

/* 图片文本分页样式 */
.img-dialog-pagination {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 0;
  border-top: 1px solid #e4e7ed;
  margin-top: 10px;
}

.img-pagination-controls {
  display: flex;
  gap: 8px;
}

.img-pagination-info {
  font-size: 12px;
  color: #606266;
  line-height: 32px;
}

.img-pagination-btn {
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 4px;
  border: 1px solid #dcdfe6;
  background: #ffffff;
  color: #606266;
  cursor: pointer;
  transition: all 0.3s;
}

.img-pagination-btn:hover:not(:disabled) {
  border-color: #409eff;
  color: #409eff;
}

.img-pagination-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.img-pagination-btn:disabled:hover {
  border-color: #dcdfe6;
  color: #606266;
}

.threshold-slider-container .el-slider__button:hover {
  transform: scale(1.1);
  transition: transform 0.2s ease;
}





// 🔥 文档导入区样式：鼠标悬停时显示提示
.document-import-area {
  cursor: pointer;
  transition: color 0.3s;
  
  &:hover {
    color: #409eff;
    text-decoration: underline;
  }
}

// ====== 连续图片理解入口 ======
.ci-entry-bar {
  display: flex;
  gap: 8px;
  padding: 6px 20px 10px;
}
.ci-entry-btn {
  padding: 5px 14px;
  font-size: 12px;
  border: 1px solid #1890ff;
  border-radius: 4px;
  background: #1890ff;
  color: #fff;
  cursor: pointer;
  transition: all .2s;
  white-space: nowrap;
  &:hover:not(:disabled) {
    background: #40a9ff;
    border-color: #40a9ff;
  }
  &:disabled {
    opacity: .6;
    cursor: not-allowed;
  }
}
.ci-entry-btn-view {
  background: #fff;
  color: #1890ff;
  &:hover {
    background: #e6f7ff;
  }
}

.ci-batch-sketch-hint {
  margin: 0 0 10px;
  font-size: 13px;
  color: #666;
  line-height: 1.5;
}
.ci-batch-sketch-actions {
  margin-bottom: 8px;
}
.ci-batch-sketch-list {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  max-height: 320px;
  overflow-y: auto;
  gap: 4px;
}
.ci-batch-sketch-filename {
  word-break: break-all;
  color: #333;
  margin: 6px 0;
}





/* 音频播放器样式 */
.audio-player-container {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f5f5f5;
  padding: 20px;
  box-sizing: border-box;
}

.audio-player-header {
  margin-bottom: 20px;
}

.audio-player-header h3 {
  margin: 0;
  font-size: 18px;
  color: #333;
  word-break: break-all;
}

.audio-player-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.audio-controls {
  width: 100%;
  max-width: 600px;
  display: flex;
  align-items: center;
  gap: 15px;
  padding: 20px;
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.audio-play-btn,
.audio-stop-btn {
  width: 50px;
  height: 50px;
  border: none;
  border-radius: 50%;
  background-color: #007bff;
  color: white;
  font-size: 20px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background-color 0.3s;
  flex-shrink: 0;
}

.audio-play-btn:hover:not(:disabled),
.audio-stop-btn:hover:not(:disabled) {
  background-color: #0056b3;
}

.audio-play-btn:disabled,
.audio-stop-btn:disabled {
  background-color: #ccc;
  cursor: not-allowed;
}

.audio-progress-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.audio-progress-bar {
  position: relative;
  width: 100%;
  height: 8px;
  background-color: #e0e0e0;
  border-radius: 4px;
  cursor: pointer;
  overflow: hidden;
}

.audio-progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  background-color: #007bff;
  border-radius: 4px;
  transition: width 0.1s linear;
}

.audio-progress-handle {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 16px;
  height: 16px;
  background-color: #007bff;
  border-radius: 50%;
  border: 2px solid white;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  cursor: pointer;
  transition: left 0.1s linear;
}

.audio-time {
  font-size: 14px;
  color: #666;
  text-align: center;
}

.audio-loading {
  margin-top: 20px;
  color: #666;
  font-size: 14px;
}

.audio-error {
  margin-top: 20px;
  color: #f56c6c;
  font-size: 14px;
}
</style>
