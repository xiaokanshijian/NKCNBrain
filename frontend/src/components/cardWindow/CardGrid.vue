<template>
  <div class="multi-card-func" v-if="choosedCardIdList.length >= 2">
    <button class="card-combine-btn" @click="cardCombine">多卡融合</button>
    <button class="card-summarize-btn" @click="cardSummarize">多卡内容总结</button>
    <button class="card-study-guide-btn" @click="cardStudyGuide">多卡学习指导</button>
    <button class="card-suggest-ideas-btn" @click="cardSuggestIdeas">多卡建议想法</button>
    <button class="card-user-define" @click="cardUserDefine">动态追问</button>
  </div>
  <div class="multi-card-func" v-if="choosedCardIdList.length == 1">
    <button class="card-combine-btn" @click="singleCardUnderstand">单卡辅助理解</button>
    <button class="card-summarize-btn" @click="singleCardCrtique">单卡批判</button>
    <button class="card-study-guide-btn" @click="singleCardCreateOutline">单卡大纲</button>
    <button v-if="isPlus" class="card-react-btn" @click="singleCardReact">React加强</button>
    <button class="card-user-define" @click="cardUserDefine">动态追问</button>
    <button class="card-react-btn" @click="cardTidyUp">卡片进化整理</button>
  </div>

  <!-- 悬浮显示的菜单，鼠标悬停时才可见 -->
  <div class="tags-container" v-if="menuVisible" @mouseover="showMenu" @mouseleave="handleTagsContainerMouseLeave">
    <!-- 第一行：卡片层级筛选、标题-卡片筛选、作者-卡片筛选横向并排 -->
    <div class="filter-row">
      <!-- 卡片层级筛选 -->
      <div class="filter-item">
        <div class="tags-header">
          <span>卡片层级筛选</span>
        </div>
        <div class="layer-filter-slider" @click="toggleCardLayer">
          <div class="slider-track">
            <div class="slider-thumb" :class="{ 'high-value': cardLayerMode === 'high_value' }"></div>
            <span class="slider-text" v-if="cardLayerMode === 'white'">白卡层</span>
            <span class="slider-text right" v-if="cardLayerMode === 'high_value'">DMT四色化卡片层</span>
          </div>
        </div>
      </div>
      
      <!-- 标题-卡片筛选 -->
      <div class="filter-item">
        <div class="tags-header">
          <span>标题-卡片筛选</span>
        </div>
        <div class="title-filter">
          <input type="text" v-model="titleFilter" placeholder="请输入标题，模糊匹配筛选卡片" class="filter-input"/>
        </div>
      </div>

      <!-- 作者-卡片筛选 -->
      <div class="filter-item">
        <div class="tags-header">
          <span>作者-卡片筛选</span>
        </div>
        <div class="author-filter">
          <input type="text" v-model="authorFilter" placeholder="请输入作者名称，模糊匹配筛选卡片" class="filter-input"/>
        </div>
      </div>
    </div>

    <!-- 第二行：标签(关键词)-卡片筛选 -->
    <div class="tags-header">
      <span>语义关键词-卡片筛选</span>
      <button class="generate-permanent-card-btn" @click="generatePermanentCard" :disabled="generatingPermanentCard">
        <span v-if="generatingPermanentCard">
          生成中... ({{ permanentCardProgress.current }}/{{ permanentCardProgress.total }})
          <span v-if="permanentCardProgress.keyword"> - {{ permanentCardProgress.keyword }}</span>
        </span>
        <span v-else>生成关键词神经元永久卡</span>
      </button>
      <button class="analyze-cognitive-state-btn" @click="analyzeCognitiveState" :disabled="analyzingCognitiveState">
        {{ analyzingCognitiveState ? '分析中...' : '关键词节点图主体性认知状态分析' }}
      </button>
      <button class="semantic-reorganize-btn" @click="startSemanticReorganize('full')" :disabled="semanticReorganizing || semanticReorganizeRollingBack">
        {{ semanticReorganizeLabel('full') }}
      </button>
      <button class="semantic-reorganize-btn incremental" @click="startSemanticReorganize('incremental')" :disabled="semanticReorganizing || semanticReorganizeRollingBack">
        {{ semanticReorganizeLabel('incremental') }}
      </button>
      <button
        v-if="semanticReorganizeCanRollback"
        class="semantic-rollback-btn"
        @click="rollbackSemanticReorganize"
        :disabled="semanticReorganizing || semanticReorganizeRollingBack"
      >
        {{ semanticReorganizeRollingBack ? '回退中…' : '撤销本次梳理' }}
      </button>
      <button class="reset-btn" @click="clearSelectedTopics">恢复</button>
    </div>
    <KeywordNetworkGraph
      ref="keywordNetworkGraph"
      :keywords="keyTopics"
      :cards="keywordNetworkCards"
      :selected-keywords="selectedTopics"
      :filter-strategy="keywordFilterStrategy"
      :keyword-four-color-dmt="keywordFourColorDMTPure"
      :semantic-reorganize-meta="semanticReorganizeMeta"
      :initial-keywords="getInitialKeywordsArray()"
      :tribal-keywords="tribalKeywords"
      :scene-name="sceneName"
      :author-filter="authorFilter"
      :keyword-fusion-relations="keywordFusionRelations"
      @toggle-keyword="toggleTopicSelection"
      @filter-strategy-change="handleFilterStrategyChange"
      @keyword-renamed="handleKeywordRename"
      @keyword-rename-start="handleKeywordRenameStart"
    />
  </div>
  
  <!-- gutter:每列20间隔；span是一列占多少单位，一共24个单位，这里指定24就是占满了一行只有一个 -->
  <div class="grid-container">
    <el-row class="grid-row" :gutter="2">
      <!-- 索引卡 -->
      <el-col class="grid-col" :span="8" v-if="filteredCards.length > 0">
        <div class="notebook-card-index" shadow="hover">
          <div class="index-card-header">
            <span>标题索引卡</span>
            <span class="index-card-count">共 {{ filteredCards.length }} 张卡片</span>
          </div>

          <div class="index-card-content">
            <!-- 所有条目拉通按datetime倒排显示 -->
            <template v-if="seriesGroups && Object.keys(seriesGroups).length > 0">
              <ul class="index-card-list">
                <li 
                  v-for="(card, idx) in seriesGroups[Object.keys(seriesGroups)[0]]" 
                  :key="idx" 
                  class="index-card-item"
                  @click="scrollToCard(card.cid)"
                >
                  <div class="index-card-item-dot"></div>
                  <span class="index-card-item-title" :class="{ 'has-dmt': hasFourColorOrDmt(card) }">{{ card.contentTitle }}</span>
                    <!-- {{ card.contentTitle }} -->
                    
                    <!-- 后置索引信息图标气泡 -->
                    <div class="post-index-icon" 
                        ref="indexIcon" 
                        @mouseenter="showTooltip($event, card)" 
                        @mouseleave="hideTooltip"
                        @click.stop="openPostIndexEditor(card)">
                      <!-- <i class="el-icon-info-circle"></i> -->
                      <span class="post-index-count">{{ getPostIndexCount(card) }}</span>
                    </div>
                  </li>
                </ul>
            </template>
            <!-- 如果没有分组，则显示全部卡片 -->
            <template v-else>
              <ul class="index-card-list">
                <li 
                  v-for="(card, idx) in filteredCards" 
                  :key="idx" 
                  class="index-card-item"
                  @click="scrollToCard(card.cid)"
                >
                  <div class="index-card-item-dot"></div>
                  <span class="index-card-item-title" :class="{ 'has-dmt': hasFourColorOrDmt(card) }">{{ card.contentTitle }}</span>

                  <!-- 信息图标 -->
                  <div class="post-index-icon" 
                      ref="indexIcon" 
                      @mouseenter="showTooltip($event, card)" 
                      @mouseleave="hideTooltip"
                      @click.stop="openPostIndexEditor(card)">
                    <!-- <i class="el-icon-info-circle"></i> -->
                    <span class="post-index-count">{{ getPostIndexCount(card) }}</span>
                  </div>
                </li>
              </ul>
            </template>
          </div>

          <div class="index-card-footer" v-if="selectedTopics.length > 0">
            已筛选: {{ selectedTopics.join(', ') }}
          </div>
        </div>
      </el-col>

      <!-- 问题索引卡 -->
      <el-col class="grid-col" :span="8" v-if="questionCards.length > 0">
        <div class="notebook-card-index question-index" shadow="hover">
          <div class="index-card-header">
            <span>问题链索引卡</span>
            <span class="index-card-count">共 {{ questionCards.length }} 个问题</span>
          </div>

          <div class="index-card-content">
            <ul class="index-card-list">
              <template v-for="(question, idx) in questionCards">
                <!-- 分类标题 -->
                <li 
                  v-if="question.isCategoryHeader" 
                  :key="`category_${idx}`"
                  class="index-card-item question-category-header"
                  @click="toggleQuestionCategory(question.category)"
                >
                  <!-- <div class="question-category-title">{{ question.category }}</div> -->
                  <div class="question-category-title">
                    <span 
                      class="category-arrow"
                      :class="{ 'category-arrow-expanded': !isCategoryCollapsed(question.category) }"
                    ></span>
                    <span>{{ question.category }}</span>
                  </div>
                </li>
                <!-- 问题项 -->
                <li 
                  v-else-if="!isCategoryCollapsed(question.category)"
                  :key="idx" 
                  class="index-card-item question-item"
                  @click="handleQuestionClick(question, $event)"
                  @dblclick.prevent="openQuestionComment(question, idx)"
                  @mouseenter="showQuestionTooltip($event, question)"
                  @mouseleave="hideQuestionTooltip"
                >
                  <div class="index-card-item-dot question-dot"></div>
                  <!-- 🔥 DMT字母标识，使用四色颜色 -->
                  <span 
                    class="question-dmt-badge" 
                    :style="{ color: getQuestionDMTColor(question), fontWeight: 'bold' }"
                    :title="getQuestionDMTTitle(question)"
                  >{{ getQuestionDMTLetter(question) }}</span>
                  <div class="indexcard-question-content">
                    <!-- <div class="question-text">{{ question.question }}</div> -->
                    <div class="question-text" 
                         @mouseenter="showQuestionFullText($event, question.question)"
                         @mouseleave="hideQuestionFullText">
                      {{ question.question }}
                    </div>
                    <div class="question-meta">
                      <span class="question-author" title="对应卡片作者">
                        {{ question.author ? question.author.split('_')[0] : '' }}
                      </span>
                      <span class="question-comment" title="已添加评论" v-if="question.comment">💬</span>
                      <span class="question-score" title="对应卡片红蓝卡标">{{ question.score }}</span>
                    </div>
                  </div>
                </li>
              </template>
            </ul>
          </div>
        </div>
      </el-col>

      <!-- 🔥 文档交叉梳理建议索引卡（第三个位置） -->
      <el-col class="grid-col" :span="8" v-if="crossDocumentSuggestionCard">
        <div class="notebook-card-index cross-document-index" shadow="hover">
          <div class="index-card-header">
            <span>文档交叉梳理建议</span>
            <div style="display: flex; gap: 10px; align-items: center;">
              <span
                class="index-card-count"
                @click.stop="scrollToCard(crossDocumentSuggestionCard.cid)"
                @contextmenu.prevent.stop="openGroupTwinMarkdownDialog"
                style="cursor: pointer;"
                :title="crossDocumentDetailTitle"
              >查看详情</span>
              <span 
                class="index-card-generate" 
                @click.stop="extractTribalKnowledge"
                :style="{ cursor: isExtractingTribalKnowledge ? 'not-allowed' : 'pointer', opacity: isExtractingTribalKnowledge ? 0.6 : 1 }"
                title="提取部落知识"
              >
                <span v-if="isExtractingTribalKnowledge">
                  提取中...
                  <span v-if="tribalKnowledgeProgress.total > 0">({{ tribalKnowledgeProgress.current }}/{{ tribalKnowledgeProgress.total }})</span>
                  <span v-if="tribalKnowledgeProgress.currentSection" style="font-size: 11px; color: #999;">- {{ tribalKnowledgeProgress.currentSection }}</span>
                </span>
                <span v-else>提取部落知识</span>
              </span>
            </div>
          </div>

          <div class="index-card-content cross-document-content">
            <div 
              class="cross-document-preview"
              @click="scrollToCard(crossDocumentSuggestionCard.cid)"
            >
              <div class="cross-document-text" v-html="formatCrossDocumentContent(crossDocumentSuggestionCard.content_preview)"></div>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 🔥 本子输出文章卡索引（可多张） -->
      <el-col class="grid-col" :span="8" v-for="outputCard in outputArticleCards" :key="`output-article-index-${outputCard.cid}`">
        <div class="notebook-card-index output-article-index" shadow="hover">
          <div class="index-card-header">
            <span>本子输出文章卡</span>
            <div style="display: flex; gap: 10px; align-items: center;">
              <span 
                class="index-card-count" 
                @click.stop="scrollToCard(outputCard.cid)" 
                style="cursor: pointer;" 
                title="点击跳转到卡片"
              >
                查看详情
              </span>
              <span 
                class="index-card-generate" 
                @click.stop="generateOutputArticle(outputCard)"
                :style="{ 
                  cursor: isGeneratingArticle ? 'not-allowed' : 'pointer',
                  opacity: (isGeneratingArticle && generatingOutputArticleCid !== outputCard.cid) ? 0.45 : 1
                }"
                :title="getOutputArticleMeta(outputCard).hasArticleContent ? `第${getOutputArticleMeta(outputCard).iterationCount}次迭代报告` : '生成报告'"
              >
                <span v-if="isGeneratingArticle && generatingOutputArticleCid === outputCard.cid">
                  {{ getOutputArticleMeta(outputCard).hasArticleContent ? '迭代中...' : '生成中...' }}
                  <span v-if="articleGenerationProgress.total > 0">
                    ({{ articleGenerationProgress.current }}/{{ articleGenerationProgress.total }})
                  </span>
                  <span v-if="articleGenerationProgress.currentSection" style="font-size: 11px; color: #999;">
                    - {{ articleGenerationProgress.currentSection }}
                  </span>
                </span>
                <span v-else>{{ getOutputArticleMeta(outputCard).hasArticleContent ? `第${getOutputArticleMeta(outputCard).iterationCount}次迭代报告` : '生成报告' }}</span>
              </span>
            </div>
          </div>

          <div class="index-card-content output-article-content">
            <div 
              class="output-article-preview"
              @click="scrollToCard(outputCard.cid)"
            >
              <div class="output-article-text">{{ outputCard.content_preview }}</div>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 问题评论对话框 -->
      <el-dialog
        title="问题评论"
        v-model="questionCommentDialogVisible"
        width="600px"
        :close-on-click-modal="false"
        :close-on-press-escape="false"
      >
        <div class="question-comment-dialog">
          <div class="question-info">
            <h4>问题内容：</h4>
            <p class="question-preview">{{ currentQuestionComment?.question }}</p>
          </div>
          <div class="comment-section">
            <h4>添加评论：</h4>
            <el-input
              type="textarea"
              :rows="4"
              v-model="questionCommentText"
              placeholder="请输入对问题的评论..."
              maxlength="500"
              show-word-limit
            ></el-input>
          </div>
        </div>
        <div slot="footer" class="dialog-footer">
          <el-button @click="cancelQuestionComment">取消</el-button>
          <el-button type="primary" @click="saveQuestionComment" :loading="commentSaving">保存评论</el-button>
        </div>
      </el-dialog>

      <!-- NK2026：右键「查看详情」打开；进度仅在弹窗内展示 -->
      <el-dialog
        title="小组本体形成（Gxx.md）"
        v-model="groupTwinDialogVisible"
        width="85%"
        top="5vh"
        class="group-twin-md-dialog"
      >
        <div v-if="groupTwinProgressBannerVisible" class="group-twin-progress-banner">
          {{ groupTwinProgressBannerText }}
        </div>
        <div style="margin-bottom: 12px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;">
          <span>切换小组文件</span>
          <el-select
            v-model="selectedGroupTwinFile"
            placeholder="选择 Gxx.md"
            style="width: 260px"
            @change="loadSelectedTwinContent"
          >
            <el-option v-for="n in groupTwinFileNames" :key="n" :label="n" :value="n" />
          </el-select>
        </div>
        <div v-loading="groupTwinLoading" class="group-twin-parser-wrap" style="max-height: 70vh; overflow: auto;">
          <AnswerParser v-if="groupTwinMarkdown" :answer="groupTwinMarkdown" />
          <div v-else-if="!groupTwinLoading" style="color: #909399; padding: 12px;">
            暂无小组本体数字孪生：请等待后台生成完成；或在文档导入区上传含组号、主题的文件后，重新双击文档导入区生成/更新文档交叉梳理建议卡。
          </div>
        </div>
      </el-dialog>

      <!-- 已有卡片集合，根据selectedTopics和titleFilter过滤展示 -->
      <!-- 空白内容表示等待生成完成 - 移到第一张白卡位置 -->
      <el-col class="grid-col" :span="8" v-if="showBlankCard || cardMaking" :key="'waiting-card'" ref="waitingCardRef">
        <div class="notebook-card-waiting" shadow="hover">
          <img class="waiting-gif" src="@/assets/img/chatwindow/card_waiting.gif" alt="Loading...">
          <div class="waiting-text">正在生成卡片，请稍等...</div>
        </div>
      </el-col>
      <!-- <el-col class="grid-col" :span="8" v-if="cardSingleMaking"> -->
      <!-- 单卡合并/整理等待提示 -->
      <!-- <div class="notebook-card-waiting-single" shadow="hover" v-if="cardSingleMaking || cardTidying" ref="waitingSingleRef">
        <div class="waiting-text">请稍等...正在合并/整理到原卡</div>
      </div> -->
      <!-- </el-col> -->
      <!-- 已有卡片集合，根据selectedTopics和titleFilter过滤展示 -->
      <el-col class="grid-col" :span="8" v-for="(card, index) in filteredCards" :key="index">
        <Card ref="cardRefs" :title="card.title" :content="card.content" :score="card.score" :idx="index" :cid="card.cid" :cardcolor="card.color" :reason="card.reason" :colorhlSFT="card.colorSFT" :scoreSFT="card.scoreSFT" :reasonSFT="card.reasonSFT"
          :model_id="card.model_id" :status="card.status" :contentTitle="card.contentTitle" @change="addChoseCard2List" @checkParams="handleCheck"
          @update-history="handelUpdateHistory" @hint="handleHint" :needflashing="card.cid === flashingCid" :card="card"
          @MultiHint="handleMultiHint" :needMultiFlashing="flashingCids.includes(card.cid)" @updateOrder="updateOrder"
          :reAcquire="reAcquire" @reAcquireOver="reAcquireOver" @deleteCard="deleteCard" @cardClickLog="cardClickLog"
          :activeModel="activeModel" :updateCheckbox="updateCheckbox" :choosedCardIdList="choosedCardIdList" 
          @cardTextNum="cardTextNum" @cardTextNumOver="cardTextNumOver" :keyTopics="keyTopics" :subSceneName="subSceneName" :sceneName="sceneName"
          @chosenOver="chosenOver" :cidToTitleMap="cidToTitleMap" :postIndex="card.postIndex" @openPostIndexDialog="openPostIndexDialog"
          :HLOpeContent="HLOpeContent" :HLContent="HLContent" :confidenceScore="card.confidence_score" :rotScore="card.rot_score"
          :fourColorType="card.four_color_type" :dmtLevel="card.dmt_level" :isHighValue="hasFourColorOrDmt(card)"
          :isRelatedToSelected="isCardRelatedToSelected(card)" :selectedDocs="card.selected_docs" :selectedCardId="selectedCardId"
          :cardTidying="(cardTidying && choosedCardIdList.includes(card.cid)) || (cardSingleMaking && choosedCardIdList.includes(card.cid)) || updatingPermanentCards.has(card.cid)" :cardList="cardList"
          :cardImageGeneratingCids="cardImageGeneratingCids"
          :cardHtmlGeneratingCids="cardHtmlGeneratingCids"
          :hasCardImage="cardHasImageCids.includes(card.cid)"
          :fileNameList="fileNameList"
          :leftSelectList="leftSelectList"
          :rightSelectList="rightSelectList"
          @openCardByCid="handleOpenCardByCid"
          @single-card-image-requested="onSingleCardImageRequested"
          @card-has-image="onCardHasImage"/>
      </el-col>
    </el-row>
  </div>

  <el-dialog v-model="showDialog" width="60%" class="createCardQuestion" :close-on-click-modal="false"
    :close-on-press-escape="false">
    <h1 class="cardQuestion">卡片追问</h1>
    <!--    <div class="ButtonListContainer">-->
    <!--      <el-button v-for="text in this.cardQuestionList" class="ButtonList" @click="createRelCard(text)" >-->
    <!--        {{text}}-->
    <!--      </el-button>-->
    <!--    </div>-->

    <el-form :model="userDefineForm" label-width="80px" class="inline-form">
      <div class="form-container">
        <!-- 模板按钮组 -->
        <div class="template-buttons">
          <el-button v-for="(template, index) in promptTemplates" :key="index" @click="applyTemplate(template)">
            {{ template.label }}
          </el-button>
        </div>

        <!-- 使用div包裹输入框和按钮，应用flex布局 -->
        <div class="input-button-group">
          <el-input type="textarea" placeholder="提出您的自定义追问，建议在上方点选模板使用" v-model="userDefineForm.userText"></el-input>
          <el-button class="userDefineButton" @click="createRelCard(userDefineForm.userText)">追问</el-button>
        </div>
      </div>
    </el-form>
  </el-dialog>


  <!-- 后置索引编辑弹窗 -->
  <el-dialog
    title="编辑后置索引"
    v-model="postIndexDialogVisible"
    width="500px">
    <div v-if="currentEditCard">
      <p>为 "{{ currentEditCard.contentTitle }}" 卡片设置后置索引：</p>
      
      <el-form>
        <el-form-item label="选择后置索引">
          <el-select
            v-model="selectedPostIndices"
            multiple
            filterable
            placeholder="请选择后置索引卡片"
            style="width: 100%">
            <el-option
              v-for="option in postIndexOptions"
              :key="option.value"
              :label="option.label"
              :value="option.value">
            </el-option>
          </el-select>
        </el-form-item>
        
        <!-- 可以移除自定义输入，因为我们需要存储的是cid -->
        <!-- <el-form-item label="自定义索引">
          <el-input 
            v-model="customPostIndex"
            placeholder="输入自定义后置索引，多个关键词用逗号分隔">
          </el-input>
        </el-form-item> -->
        <el-form-item label="已选卡片">
          <div class="selected-cards-preview">
            <el-tag 
              v-for="(title, index) in selectedPostTitles" 
              :key="index"
              size="small"
              closable
              @close="selectedPostIndices.splice(index, 1)">
              {{ title }}
            </el-tag>
            <div v-if="selectedPostTitles.length === 0" class="no-selection">
              未选择任何卡片
            </div>
          </div>
        </el-form-item>
      </el-form>
    </div>
    
    <span slot="footer" class="dialog-footer">
      <el-button @click="postIndexDialogVisible = false">取消</el-button>
      <el-button type="primary" @click="savePostIndex">确定</el-button>
    </span>
  </el-dialog>


  <div class="cardParams-dialog" v-if="this.showCardParams">
    <div class="dialog-header">
      <h2>Card生成时参数图</h2>
      <div class="close" @click="hideDialog">&times;</div>
    </div>
    <radarChartCard :params="params" :timeParams="timeParams" :timeModel="timeModel"></radarChartCard>
  </div>

  <!-- 问题评估提示框 -->
  <div v-if="questionTooltipVisible" class="question-tooltip" :style="questionTooltipStyle">
    <div class="tooltip-header">问题质量评估</div>
    <div class="tooltip-content">
      <div class="evaluation-item">
        <span class="evaluation-label">信息熵评分:</span>
        <span class="evaluation-value">{{ currentQuestionEvaluation?.entropyScore || 'N/A' }}</span>
      </div>
      <div class="evaluation-item">
        <span class="evaluation-label">场景匹配度:</span>
        <span class="evaluation-value">{{ currentQuestionEvaluation?.sceneMatch || 'N/A' }}</span>
      </div>
      <div class="evaluation-item">
        <span class="evaluation-label">文档相关度:</span>
        <span class="evaluation-value">{{ currentQuestionEvaluation?.docRelevance || 'N/A' }}</span>
      </div>
      <div class="evaluation-item">
        <span class="evaluation-label">综合评分:</span>
        <span class="evaluation-value total-score">{{ currentQuestionEvaluation?.totalScore || 'N/A' }}</span>
      </div>
    </div>
  </div>

  <!-- 问题完整文本提示框 -->
  <!-- <div v-if="questionFullTextVisible" class="question-fulltext-tooltip" :style="questionFullTextStyle">
    <div class="tooltip-header">完整问题</div>
    <div class="fulltext-content">{{ currentQuestionFullText }}</div>
  </div> -->

  <!-- 语义梳理进度（右下角固定浮层，避免 ElNotification 每 2 秒关闭重开闪烁） -->
  <div v-if="semanticReorganizeFloatingVisible" class="semantic-reorganize-floating-progress">
    <div class="semantic-reorganize-floating-header">
      <span class="semantic-reorganize-floating-title">{{ semanticReorganizePanelTitle }}</span>
      <button type="button" class="semantic-reorganize-floating-close" @click="dismissSemanticReorganizeFloating">×</button>
    </div>
    <el-progress
      :percentage="semanticReorganizeProgressPercent"
      :status="semanticReorganizeProgressStatus"
      :stroke-width="12"
    />
    <div class="semantic-reorganize-floating-detail">{{ semanticReorganizeNotificationSubtext }}</div>
  </div>
</template>

<script>
import Card from './Card.vue';
import radarChartCard from '@/components/radar-chartCard.vue';
import KeywordNetworkGraph from './KeywordNetworkGraph.vue';
import AnswerParser from '@/components/chatWindow/AnswerParser.vue';

import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElSelect, ElOption, ElMessageBox, ElProgress } from 'element-plus'

import { get_cards, get_filtered_cards, get_card, semantic_reorganize_start, semantic_reorganize_status, semantic_reorganize_rollback, card_generate_four_color_images, card_get_image_generating_status, card_get_html_generating_status } from "@/api/card/get_card"
import { card_evalSFT } from "@/api/card/send_card"
import { mergeCardBackend, cardUserDefine, react, cardTidyUpById, cardUpdPostIndex } from "@/api/card_zym/card_js"
import { getDateTime, modelHL } from "@/api/getData";
import { API_BASE_URL } from '@/config/apiConfig';
import router from "@/router";
export default {
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    ElSelect,
    ElOption,
    ElMessageBox,
    Card,
    radarChartCard,
    KeywordNetworkGraph,
    AnswerParser,
  },
  props: {
    cards: Array,
    cardUpdate: Boolean,
    cardUpdateStream: Boolean,
    cardOpeUpdStream: Boolean,
    HLContent: Map,
    HLOpeContent: Map,
    params: Object,
    activeModel: String,
    isPlus: Boolean,
    cardMaking: Boolean,
    cardSingleMaking: Boolean,
    menuVis: Boolean,
    sceneName: String,
    subSceneName: String,
    /** 当前勾选文档（与聊天一致），供卡片 HTML 生成拉 PDF/图片三层理解 */
    fileNameList: {
      type: Array,
      default: () => [],
    },
    leftSelectList: {
      type: Array,
      default: () => [],
    },
    rightSelectList: {
      type: Array,
      default: () => [],
    },
    /** 小组本体 Gxx 生成进度（仅用于弹窗内展示；索引卡外观不变） */
    groupTwinProgress: {
      type: Object,
      default: () => ({ active: false, total: 0, done: 0, message: '' }),
    },
  },
  data() {
    return {
      // 🔥 记录子组件本地更新的关键词（避免被覆盖）
      locallyUpdatedKeywordsInParent: new Set(),
      // 🔥 本子描述（中文）
      notebookDescription: null,

      // 索引卡是否伸缩后置索引
      tooltipElement: null,
      postIndexDialogVisible: false,
      currentEditCard: null,
      selectedPostIndices: [],  // 存储选中的cid
      customPostIndex: '',
      // 用于存储cid到标题的映射关系
      cidToTitleMap: {},

      openCardId: null,

      // 定义模板数组，每个模板包含一个标签和内容
      promptTemplates: [
        { label: "单卡迭代通用模板", text: "您是根据一段文本进行改进（/创作）迭代的专家，后续将给你一段文本，请用中文完成指定要求：\n（请您在此处填充您的迭代要求）" },
        { label: "多卡迭代通用模板", text: "您是综合多段文本进行改进（/创作）迭代的专家，后续将给你多段文本，请用中文完成指定要求：\n（请您在此处填充您的迭代要求）" },
        { label: "改进型迭代模板", text: "您是根据一段文本（/综合多段文本）进行改进迭代的专家，下面将先指明改进要求，再给你一段（/多段）文本，请用中文完成以下要求：\n下面的这段（/这几段）文本是xxx（简要说明各文本<即各卡片内容>是什么、怎么得来的、有无关联等），其中xxx还不够完善（/xxx有误/xxx还需要修改/缺少xxx内容/没有体现xxx指向/其他），理由是xxx，请你做如下修改（/增加/删除/完善/其他）迭代：\n1.改进迭代任务一：一两句话简单描述目标及内容\n2.改进迭代任务二：一两句话简单描述目标及内容\n3....\n\n注意事项及细节：\n1.注意点一\n2...." },
        { label: "创作型迭代模板", text: "您是根据一段文本（/综合多段文本）进行创作迭代的专家，下面将先指明创作撰写要求，再给你一段（/多段）文本，请用中文完成以下要求：\n下面的这段（/这几段）文本是xxx（简要说明各文本<即各卡片内容>是什么、怎么得来的、有无关联等），请你以这些为素材，进行如下（文本创作/代码编写/其他）迭代：\n1.创作迭代任务一：一两句话简单描述目标及内容\n2.创作迭代任务二：一两句话简单描述目标及内容\n3....\n\n注意事项及细节：\n1.注意点一\n2...." },
        { label: "合并模板", text: "您是综合多段文本进行合并迭代的专家，下面将先指明合并要求，再给你xxx段文本，请用中文完成以下要求：\n下面的这xxx段文本（/问答/回答/其他）是xxx（简要说明各文本<即各卡片内容>是什么、怎么得来的、有什么关联、将要有什么作用等）\n（例如：\n下面这两段问答是对同一个提出的要求，两个不同模型给出的回答/下面这两段文本是针对论文的xxx章节xxx小节，撰写的2个不同版本，它们具有一些共识点，需要你找出；其他内容则分模块、分段落对比两个版本孰优孰劣，然后扩长化短）\n请你以这些为素材，进行迭代，对这xxx段文本进行综合合并\n\n其他注意事项及细节：\n1.注意点一\n2...." }
      ],

      menuVisible: false, // 控制菜单显示状态
      contentTitles: [],
      preIndexs: [],
      keyTopics: [],      // 将提取出的已有的卡片关键词放入此数组，作为此后的备选Tags
      selectedTopics: [], // 当前选中的多个关键词
      keywordFilterStrategy: 'union', // 关键词筛选策略：'union' 并集 或 'intersection' 交集
      titleFilter: "",    // 标题筛选关键词
      authorFilter: "",   // 作者筛选关键词
      keywordFourColorDMT: {}, // 🔥 关键词四色DMT信息（从后端获取）
      keywordFourColorDMTPure: {}, // 🔥 纯对象版本，用于传递给子组件
      keywordFusionRelations: {}, // 🔥 关键词融合关系（从后端获取）
      cardLayerMode: "white",  // 🔥 卡片层级模式："white"白卡层 或 "high_value"DMT四色化卡片层
      highValueCardIds: new Set(),  // 🔥 高价值卡片ID集合
      selectedCardId: null,  // 🔥 当前勾选的卡片ID
      initialKeywords: new Set(),  // 🔥 初始关键词集合（用于标识新关键词）
      tribalKeywords: [],  // 🔥 部落知识关键词（菱形显示）

      // 问题索引卡相关
      questionTooltipVisible: false,
      questionTooltipStyle: {},
      currentQuestionEvaluation: null,
      questionFullTextVisible: false,
      questionFullTextStyle: {},
      currentQuestionFullText: '',

      // 问题评论相关
      questionCommentDialogVisible: false,
      currentQuestionComment: null,
      questionCommentText: '',
      commentSaving: false,
      clickTimer: null, // 用于处理单击双击事件冲突

      // 问题列表相关
      sortedQuestions: [], // 存储排序后的问题列表
      questionChainSortedOrder: [], // 🔥 保存的问题链排序后的CID顺序
      questionChainCategories: {}, // 🔥 保存的问题链分类信息 {分类名: [cid1, cid2, ...]}
      questionCategoryCollapsed: {}, // 🔥 保存每个分类的折叠状态 {分类名: true/false}

      generatingPermanentCard: false, // 🔥 是否正在生成永久卡片
      analyzingCognitiveState: false, // 🔥 是否正在分析认知状态
      semanticReorganizing: false,
      semanticReorganizeStatus: null,
      semanticReorganizePollTimer: null,
      semanticReorganizeCanRollback: false,
      semanticReorganizeRollingBack: false,
      semanticReorganizeMeta: {},
      semanticReorganizeFloatingDismissed: false,
      semanticReorganizeFloatingAutoHideTimer: null,
      semanticReorganizeResultVisible: false,
      cardImageGeneratingCids: [], // 正在生图的卡片 cid 列表
      cardImagePollTimer: null, // 生图状态轮询定时器
      cardHtmlGeneratingCids: [],
      cardHtmlPollTimer: null,
      cardHasImageCids: [], // 已有附图的卡片 cid（左上角图标高亮）
      updatingPermanentCards: new Set(), // 🔥 正在更新的永久卡片CID集合
      isGeneratingArticle: false, // 🔥 是否正在生成输出文章
      outputArticleMetaByCid: {}, // 🔥 每张输出目录卡的正文状态与迭代次数
      generatingOutputArticleCid: null, // 🔥 当前正在生成/迭代的目录卡CID
      isExtractingTribalKnowledge: false,
      tribalKnowledgeProgress: { current: 0, total: 0, currentSection: '' },
      tribalProgressInterval: null,

      groupTwinDialogVisible: false,
      groupTwinFileNames: [],
      selectedGroupTwinFile: '',
      groupTwinMarkdown: '',
      groupTwinLoading: false,
      articleGenerationProgress: {
        current: 0,
        total: 0,
        currentSection: ''
      }, // 🔥 文章生成进度
      articleProgressInterval: null, // 🔥 文章生成进度轮询定时器

      showBlankCard: false, // 控制是否显示空白列
      cardTidying: false, // 是否在整理单卡片
      isInitial: true,
      updateCheckbox: false,
      reAcquire: false,
      flashingIndexes: [], // 需要闪烁的多卡卡片索引数组
      flashingIndex: -1, // 当前需要闪烁的单卡卡片索引, 默认没有卡片闪烁
      flashingCids: [], // 需要闪烁的多卡卡片cid数组
      flashingCid: -1, // 当前需要闪烁的单卡卡片cid, 默认没有卡片闪烁
      lastCreatedCardId: null, // 最后创建的卡片ID，用于等待卡消失后滚动到新卡片
      cardList: [
        // 按理说应该是getall获取完成才知道有多少个，vue才会去加载这些子Card
        // 但这里初始化的时候写了2个默认的，就默认先把前两个位置占用了，导致后来getall之后的前两个位置被占了挂载不上，但后面的不受影响
        // 所以这里不能有默认加载内容
        // {
        //   "title": "title1",
        //   "content": "content1",
        //   "score": 1.7,
        // },
        // {
        //   "title": "title2",
        //   "content": "content2",
        // },
      ],
      choosedCardIdList: [],
      choosedFunc: -1,
      // cardUpdateTmp: false,
      showCardParams: false,
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
      timeModel: '',
      showDialog: false,
      cardQuestionList: ["test", "test2", "test3"],
      choosedText: '',
      userDefineForm: {
        userText: ''
      },
    }
  },
  async created() {
    // 使用 async/await 确保 get_all_cards 在子组件创建前执行完毕
    await this.get_all_cards();
    this.initializeQuestions();
    this.refreshSemanticReorganizeStatus();
    // 此时，子组件的 created 钩子将在 get_all_cards 完成后执行
  },
  mounted() {
    // this.get_all_cards();

    // 创建一个全局的tooltip元素
    this.tooltipElement = document.createElement('div');
    this.tooltipElement.className = 'post-index-tooltip';
    this.tooltipElement.style.display = 'none';
    document.body.appendChild(this.tooltipElement);
  },
  beforeDestroy() {
    this.clearSemanticReorganizeFloatingAutoHide();
    if (this.semanticReorganizePollTimer) {
      clearTimeout(this.semanticReorganizePollTimer);
      this.semanticReorganizePollTimer = null;
    }
    if (this.cardImagePollTimer) {
      clearTimeout(this.cardImagePollTimer);
      this.cardImagePollTimer = null;
    }
    if (this.tooltipElement && document.body.contains(this.tooltipElement)) {
      document.body.removeChild(this.tooltipElement);
    }
  },
  watch: {
    // 🔥 监听输出目录卡变化，刷新每张索引卡的正文状态与迭代次数
    outputArticleCards: {
      handler: async function(newVal) {
        await this.refreshOutputArticleCardMeta(newVal || []);
      },
      immediate: true
    },
    cardUpdate: function (newVal, oldVal) {
      // 当 cardUpdate 从 false 变为 true 时，执行 get_all_cards 函数
      if (newVal === true) {
        this.isInitial = false
        this.get_all_cards();
        // // 🔥 等待卡片消失时，滚动到白底色卡区域的最上方（非高价值卡的第一个位置）
        // setTimeout(() => {
        //   this.scrollToFirstWhiteCard();
        // }, 500); // 延迟500ms确保卡片已渲染
        // 🔥 等待 get_all_cards() 完成后（在 get_all_cards 的 then 回调中），检查是否需要滚动到新生成的卡片
      } else {

      }
    },

    // 🔥 监听showBlankCard和cardMaking变化，触发时立即滚动到CardGrid顶部
    showBlankCard: function (newVal, oldVal) {
      if (newVal === true && oldVal === false) {
        // 立即滚动到CardGrid顶部显示等待卡片
        this.$nextTick(() => {
          this.scrollToTop();
        });
      } else if (newVal === false && oldVal === true) {
        // 等待卡片消失时，滚动到白底色卡区域的最上方
        this.$nextTick(() => {
          setTimeout(() => {
            this.scrollToFirstWhiteCard();
          }, 100);
        });
      }
    },
    cardMaking: function (newVal, oldVal) {
      if (newVal === true && oldVal === false) {
        // 立即滚动到CardGrid顶部显示等待卡片
        this.$nextTick(() => {
          this.scrollToTop();
        });
      } else if (newVal === false && oldVal === true) {
        // 等待卡片消失，滚动逻辑移到 cardUpdate watch 中统一处理
        // 因为需要等待 get_all_cards() 完成后才能判断新卡片是否是高价值卡片
      }
    },
    // cardUpdateStream: function (newVal, oldVal) {
    //   // 当 cardUpdate 从 false 变为 true 时，执行 get_all_cards 函数
    //   if (newVal === true) {
    //     this.isInitial = false
    //     this.get_all_cards();
    //   } else {

    //   }
    // },
    HLContent: function (newVal, oldVal) {
      this.cardList.forEach(card => {
        if (newVal.has(card.cid)) {
          card.reasonSFT = newVal.get(card.cid);
        }
      });
    },
    HLOpeContent: function (newVal, oldVal) {
      this.cardList.forEach(card => {
        if (newVal.has(card.cid)) {
          card.reason = newVal.get(card.cid);
        }
      });
    },
    menuVis: function (newVal, oldVal) {
      if (newVal === true) {
        this.menuVisible = true
        // // 🔥 如果卡片正在更新，不更新子组件数据（避免节点位置被重置）
        // if (this.updatingPermanentCards && this.updatingPermanentCards.size > 0) {
        //   console.log('[CardGrid] 卡片正在更新中，跳过updateKeywordNetworkGraphData，避免节点位置被重置');
        //   return;
        // }
        // 🔥 菜单显示后，如果有数据，立即更新子组件
        this.$nextTick(() => {
          this.updateKeywordNetworkGraphData();
        });
      } else {
        this.menuVisible = false
      }
    },
    menuVisible: function (newVal, oldVal) {
      // 🔥 监听 menuVisible 变化，当变为 true 时更新子组件数据
      if (newVal === true) {
        // // 🔥 如果卡片正在更新，不更新子组件数据（避免节点位置被重置）
        // if (this.updatingPermanentCards && this.updatingPermanentCards.size > 0) {
        //   console.log('[CardGrid] 卡片正在更新中，跳过updateKeywordNetworkGraphData，避免节点位置被重置');
        //   return;
        // }
        // 🔥 延迟更新，临时数据源已经在handleKeywordDMTLocalUpdated中更新过了
        this.$nextTick(() => {
          setTimeout(() => {
            this.updateKeywordNetworkGraphData();
          }, 100);
        });
      }
    },
    filteredCards: function (newVal, oldVal) {
      // 当filteredCards变化时，重新初始化问题列表
      this.initializeQuestions();
    },
    groupTwinProgress: {
      deep: true,
      handler(newVal, oldVal) {
        if (!this.groupTwinDialogVisible) return;
        const d = (newVal && newVal.done) || 0;
        const od = (oldVal && oldVal.done) || 0;
        if (d > od) {
          this.$nextTick(() => {
            this.refreshTwinFileList(false).then(() => {
              if (this.selectedGroupTwinFile) this.loadSelectedTwinContent();
            });
          });
        }
      },
    },
  },
  computed: {
    groupTwinProgressBannerVisible() {
      const p = this.groupTwinProgress;
      if (!p) return false;
      if (p.active) return true;
      if ((p.total || 0) > 0) return true;
      return !!(p.message && String(p.message).trim());
    },
    groupTwinProgressBannerText() {
      const p = this.groupTwinProgress || {};
      const total = p.total || 0;
      const done = p.done || 0;
      const msg = (p.message || '').trim();
      if (p.active) {
        return `小组本体生成进行中：${done}/${total}${msg ? ` · ${msg}` : ''}`;
      }
      if (total > 0 || msg) {
        return `小组本体生成进度：${done}/${total}${msg ? ` · ${msg}` : ''}`;
      }
      return '';
    },
    semanticReorganizePanelVisible() {
      if (this.semanticReorganizing) return true;
      const st = this.semanticReorganizeStatus || {};
      if (st.running) return true;
      return [
        'preparing',
        'extract',
        'extract_condense',
        'key_issues_merge',
        'enrich',
        'connect',
        'attributes',
      ].includes(st.phase);
    },
    semanticReorganizeFloatingVisible() {
      if (this.semanticReorganizeFloatingDismissed) return false;
      if (this.semanticReorganizePanelVisible) return true;
      if (!this.semanticReorganizeResultVisible) return false;
      const st = this.semanticReorganizeStatus || {};
      return st.phase === 'completed' || st.phase === 'error';
    },
    semanticReorganizePanelTitle() {
      const st = this.semanticReorganizeStatus || {};
      if (this.semanticReorganizing || st.running) {
        const mode = st.mode === 'incremental' ? '迭代梳理语义' : '重新梳理语义';
        return `${mode}进行中`;
      }
      if (st.phase === 'completed') {
        return '语义梳理已完成';
      }
      if (st.phase === 'error') {
        return '语义梳理失败';
      }
      return '语义梳理';
    },
    semanticReorganizeProgressPercent() {
      const st = this.semanticReorganizeStatus || {};
      if (typeof st.progress_percent === 'number') return st.progress_percent;
      if (st.phase === 'completed') return 100;
      return 0;
    },
    semanticReorganizeProgressStatus() {
      const st = this.semanticReorganizeStatus || {};
      if (st.phase === 'error') return 'exception';
      if (st.phase === 'completed' && !st.running) return 'success';
      return undefined;
    },
    semanticReorganizeProgressDetail() {
      const st = this.semanticReorganizeStatus || {};
      if (st.phase_label) return st.phase_label;
      if (st.phase === 'extract') {
        const title = st.current_title ? ` - ${st.current_title}` : '';
        return `提取关键词 ${st.current_index || 0}/${st.total_cards || '?'}${title}`;
      }
      if (st.phase === 'attributes') {
        return `属性分析 ${st.attr_batch_end || 0}/${st.total_keywords || '?'}`;
      }
      if (st.phase === 'completed') {
        return `共 ${st.total_keywords || 0} 个关键词，处理 ${st.cards_processed || 0} 张卡片`;
      }
      if (st.phase === 'error' && st.error) return st.error;
      return '';
    },
    semanticReorganizeNotificationSubtext() {
      const st = this.semanticReorganizeStatus || {};
      const parts = [];
      if (st.phase_label) parts.push(st.phase_label);
      if (st.api_calls_deepseek != null) parts.push(`分析语义 ${st.api_calls_deepseek} 次`);
      if (st.api_calls_claude != null && st.api_calls_claude > 0) {
        // Claude 在核心问题/补词/连边阶段也会调用，勿一律写成「四色DMT」
        if (st.phase === 'attributes' || (st.phase === 'completed' && st.last_action && String(st.last_action).includes('属性'))) {
          parts.push(`分析四色DMT三类知识 ${st.api_calls_claude} 次`);
        } else if (st.phase === 'completed') {
          parts.push(`Claude调用 ${st.api_calls_claude} 次`);
        } else {
          parts.push(`Claude分析 ${st.api_calls_claude} 次`);
        }
      }
      // 备选池：抽词阶段展示；完成后若有值也展示
      const poolSize = st.keyword_pool_size;
      if (poolSize != null && (
        st.phase === 'extract_condense'
        || st.phase === 'extract'
        || poolSize > 0
      )) {
        parts.push(`备选池 ${poolSize} 词`);
      }
      return parts.join(' · ') || '准备中…';
    },
    /** 语义梳理后：节点图只用新梳理选中卡（v2）或旧版抽样 processed */
    keywordNetworkCards() {
      const meta = this.semanticReorganizeMeta || {};
      const selected = meta.reorganize_selected_cids;
      if (
        meta.pipeline === 'v2_condense_hierarchy'
        && Array.isArray(selected)
        && selected.length > 0
      ) {
        const pid = new Set(selected.map((c) => Number(c)));
        return (this.cardList || []).filter((c) => pid.has(Number(c.cid)));
      }
      if (!meta.sampled) {
        return this.cardList || [];
      }
      const processed = meta.processed_cids;
      if (!Array.isArray(processed) || processed.length === 0) {
        return this.cardList || [];
      }
      const pid = new Set(processed.map((c) => Number(c)));
      return (this.cardList || []).filter((c) => pid.has(Number(c.cid)));
    },
    /** 文档交叉梳理索引卡「查看详情」：仅 NK2026 梯子图场景替换 title 说明 */
    crossDocumentDetailTitle() {
      const sn = this.sceneName || '';
      if (sn.includes('NK2026梯子图') && sn.includes('群组公能')) {
        return '左键：跳转到卡片；右键：打开小组本体建模（Gxx.md）';
      }
      return '点击跳转到卡片';
    },
    // 生成后置索引选项
    // postIndexOptions() {
    //   // 为了避免重复，使用Set收集唯一的标题关键词
    //   const keywords = new Set();
      
    //   this.cardList.forEach(card => {
    //     // 提取标题
    //     // const extracted = this.extractKeyword(card.contentTitle);
    //     const extracted = card.contentTitle;
    //     if (extracted) {
    //       keywords.add(extracted);
    //     }
        
    //     // 从标题中提取系列名称
    //     // const match = card.contentTitle.match(/^(S\d+):/);
    //     // if (match && match[1]) {
    //     //   keywords.add(match[1]);
    //     // }

    //     // 如果已有后置索引，也添加到选项中
    //     if (card.postIndex) {
    //       this.parsePostIndex(card.postIndex).forEach(item => {
    //         if (item) keywords.add(item);
    //       });
    //     }
    //   });
      
    //   // 转换为选项格式
    //   return Array.from(keywords).map(keyword => ({
    //     value: keyword,
    //     label: keyword
    //   }));
    // },
    postIndexOptions() {
      // 构建cid到标题的映射
      this.cidToTitleMap = {};
      this.cardList.forEach(card => {
        this.cidToTitleMap[card.cid] = card.contentTitle;
      });
      
      // 生成选项
      return this.cardList.map(card => ({
        value: card.cid.toString(), // 使用cid作为值
        label: card.contentTitle     // 使用标题作为标签
      }));
    },

    // 获取当前选中的后置索引对应的标题
    selectedPostTitles() {
      return this.selectedPostIndices.map(cid => 
        this.cidToTitleMap[cid] || `未知卡片(${cid})`
      );
    },


    // 根据 selectedTopic 过滤卡片
    filteredCards() {
      // 没有选中topic，则显示所有卡片
      // 根据 selectedTopics 和 titleFilter 过滤卡片列表
      let filteredList = this.cardList;

      // 先按关键词进行过滤
      if (this.selectedTopics.length > 0) {
        if (this.keywordFilterStrategy === 'intersection') {
          // 交集策略：卡片必须包含所有选中的关键词
          filteredList = filteredList.filter(card => {
            if (!card.keyWords) return false;
            const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
            return this.selectedTopics.every(topic => cardKeywords.includes(topic));
          });
        } else {
          // 并集策略（默认）：卡片只要包含任意一个选中的关键词即可
          filteredList = filteredList.filter(card => 
            this.selectedTopics.some(topic => card.keyWords && card.keyWords.includes(topic))
          );
        }
      }

      // 再按标题进行模糊过滤
      if (this.titleFilter) {
        const filterText = this.titleFilter.trim();
        const requiredMatchCount = Math.ceil(filterText.length * 0.7); // 计算70%匹配字符数

        filteredList = filteredList.filter(card => {
          const contentTitle = card.contentTitle;
          let matchCount = 0;

          // 统计 filterText 中的字符在 contentTitle 中出现的次数
          for (let char of filterText) {
            if (contentTitle.includes(char)) {
              matchCount++;
            }
            if (matchCount >= requiredMatchCount) {
              return true; // 达到80%匹配则认为匹配成功
            }
          }
          return false; // 未达到70%则不匹配
        });
      }

      // 最后按作者进行过滤
      if (this.authorFilter) {
        const filterText = this.authorFilter.trim();
        filteredList = filteredList.filter(card => 
          card.writer.toLowerCase().includes(filterText.toLowerCase())
        );
      }

      // 🔥 根据卡片层级模式进行筛选
      if (this.cardLayerMode === "high_value") {
        // 四色DMT化卡片层：只显示有四色/DMT标识的卡片
        filteredList = filteredList.filter(card => this.hasFourColorOrDmt(card));
      } else {
        // 白卡层：显示所有卡片，但四色DMT化卡片在前
        // 🔥 对卡片进行排序：深色永久卡始终在最前面，然后是有四色/DMT标识的卡片，最后是其他卡片
        filteredList = filteredList.sort((a, b) => {
          // 判断是否为深色永久卡
          const aIsDeepPermanent = a.type && a.type.includes('永久') && (a.four_color_type);
          const bIsDeepPermanent = b.type && b.type.includes('永久') && (b.four_color_type);
          
          // 深色永久卡始终在最前面
          if (aIsDeepPermanent && !bIsDeepPermanent) {
            return -1;
          }
          if (!aIsDeepPermanent && bIsDeepPermanent) {
            return 1;
          }
          
          // 如果都是深色永久卡，按datetime排序（最新的在前）
          if (aIsDeepPermanent && bIsDeepPermanent) {
            const dateA = new Date(a.datetime || 0);
            const dateB = new Date(b.datetime || 0);
            return dateB - dateA; // 降序：最新的在前
          }
          
          // 如果都不是深色永久卡，按原有逻辑排序（有四色/DMT标识的在前）
          const aHasFourColorOrDmt = this.hasFourColorOrDmt(a);
          const bHasFourColorOrDmt = this.hasFourColorOrDmt(b);
          
          // 如果a有四色/DMT而b没有，a排在前面
          if (aHasFourColorOrDmt && !bHasFourColorOrDmt) {
            return -1;
          }
          // 如果b有四色/DMT而a没有，b排在前面
          if (!aHasFourColorOrDmt && bHasFourColorOrDmt) {
            return 1;
          }
          
          // 如果都有或都没有，按datetime排序（最新的在前）
          const dateA = new Date(a.datetime || 0);
          const dateB = new Date(b.datetime || 0);
          return dateB - dateA; // 降序：最新的在前
        });
      }

      // // 🔥 排除文档交叉梳理卡片（它要作为索引卡显示，不作为普通卡片）
      // filteredList = filteredList.filter(card => {
      //   const content = card.content_preview || '';
      //   return !content.trim().startsWith('【文档全面交叉梳理建议卡片】');
      // });

      return filteredList;
    },

    // 🔥 文档交叉梳理建议卡片（作为索引卡）
    crossDocumentSuggestionCard() {
      if (!this.cardList || this.cardList.length === 0) return null;
      
      // 查找以"【文档全面交叉梳理建议卡片】"开头的卡片
      const suggestionCard = this.cardList.find(card => {
        const content = card.content_preview || '';
        return content.trim().startsWith('【文档全面交叉梳理建议卡片】');
      });
      
      return suggestionCard || null;
    },

    // 🔥 本子输出目录卡索引（可多张，按时间倒序）
    outputArticleCards() {
      if (!Array.isArray(this.cardList) || this.cardList.length === 0) return [];
      return this.cardList
        .filter(card => card && card.title === '本子输出目录卡')
        .sort((a, b) => {
          const da = new Date(a?.datetime || 0).getTime();
          const db = new Date(b?.datetime || 0).getTime();
          if (db !== da) return db - da;
          return Number(b?.cid || 0) - Number(a?.cid || 0);
        });
    },

    // 问题索引卡 - 提取并评估问题
    questionCards() {
      // 🔥 如果有分类信息，按照分类组织问题；否则直接返回排序后的问题
      console.log('[questionCards] questionChainCategories:', this.questionChainCategories);
      console.log('[questionCards] questionChainCategories keys:', Object.keys(this.questionChainCategories || {}));
      if (!this.questionChainCategories || Object.keys(this.questionChainCategories).length === 0) {
        console.log('[questionCards] 没有分类信息，直接返回sortedQuestions');
        return this.sortedQuestions;
      }
      
      // 构建CID到问题的映射
      const cidToQuestion = new Map();
      this.sortedQuestions.forEach(q => {
        cidToQuestion.set(String(q.cid), q);
      });
      
      // 构建CID到分类的映射
      const cidToCategory = new Map();
      Object.keys(this.questionChainCategories).forEach(categoryName => {
        const cidsInCategory = this.questionChainCategories[categoryName] || [];
        cidsInCategory.forEach(cid => {
          cidToCategory.set(String(cid), categoryName);
        });
      });
      
      // 将所有问题按分类分组
      const questionsByCategory = {};
      this.sortedQuestions.forEach(q => {
        const category = cidToCategory.get(String(q.cid)) || '其他';
        if (!questionsByCategory[category]) {
          questionsByCategory[category] = [];
        }
        questionsByCategory[category].push(q);
      });
      
      // 对每个分类内部的问题进行排序
      let categorizedQuestions = [];
      
      if (this.questionChainSortedOrder && this.questionChainSortedOrder.length > 0) {
        // 如果有排序顺序，分类内部按照sorted_cids的顺序排序
        Object.keys(questionsByCategory).forEach(categoryName => {
          const categoryQuestions = questionsByCategory[categoryName];
          categoryQuestions.sort((a, b) => {
            const indexA = this.questionChainSortedOrder.indexOf(String(a.cid));
            const indexB = this.questionChainSortedOrder.indexOf(String(b.cid));
            // 如果都在sorted_cids中，按照索引排序
            if (indexA !== -1 && indexB !== -1) {
              return indexA - indexB;
            }
            // 如果只有一个在sorted_cids中，在sorted_cids中的排在前面
            if (indexA !== -1) return -1;
            if (indexB !== -1) return 1;
            // 如果都不在sorted_cids中，保持原顺序
            return 0;
          });
        });
        
        // 按照分类中第一个问题在sorted_cids中的位置来确定分类的顺序
        const categoryOrder = [];
        Object.keys(questionsByCategory).forEach(categoryName => {
          const categoryQuestions = questionsByCategory[categoryName];
          let minIndex = Infinity;
          categoryQuestions.forEach(q => {
            const index = this.questionChainSortedOrder.indexOf(String(q.cid));
            if (index !== -1 && index < minIndex) {
              minIndex = index;
            }
          });
          categoryOrder.push({
            category: categoryName,
            minIndex: minIndex === Infinity ? 999999 : minIndex
          });
        });
        categoryOrder.sort((a, b) => a.minIndex - b.minIndex);
        
        // 按照分类顺序组织问题
        categoryOrder.forEach(({ category }) => {
          categorizedQuestions.push(...questionsByCategory[category].map(q => ({
            ...q,
            category: category,
            isCategoryHeader: false
          })));
        });
      } else {
        // 如果没有排序顺序，直接按照分类顺序组织问题
        Object.keys(questionsByCategory).forEach(categoryName => {
          categorizedQuestions.push(...questionsByCategory[categoryName].map(q => ({
            ...q,
            category: categoryName,
            isCategoryHeader: false
          })));
        });
      }
      
      // 转换为带分类标题的列表
      const result = [];
      let currentCategory = null;
      categorizedQuestions.forEach(q => {
        if (q.category !== currentCategory) {
          currentCategory = q.category;
          result.push({
            cid: `category_${currentCategory}`,
            question: currentCategory,
            isCategoryHeader: true,
            category: currentCategory
          });
        }
        result.push(q);
      });
      
      return result;
    },


    // 🔥 标题索引卡：所有条目拉通按datetime时间倒排（不再按S1-Sn分组）
    seriesGroups() {
      if (!this.filteredCards || this.filteredCards.length === 0) return {};
      
      // 所有卡片按datetime倒序排序
      const sortedCards = [...this.filteredCards].sort((a, b) => {
        const aDate = new Date(a.datetime || 0);
        const bDate = new Date(b.datetime || 0);
        return bDate - aDate; // 倒序：最新的在前
      });
      
      // 返回一个包含所有卡片的单一组
      return {
        '全部': sortedCards
      };
    },
  },
  methods: {
    // 🔥 切换问题分类的折叠/展开状态
    toggleQuestionCategory(categoryName) {
      this.questionCategoryCollapsed[categoryName] = !this.isCategoryCollapsed(categoryName);
    },
    
    // 🔥 检查分类是否折叠
    isCategoryCollapsed(categoryName) {
      // 默认展开（如果未设置，返回false表示展开）
      return this.questionCategoryCollapsed[categoryName] === true;
    },


    _extractOutputArticleIterationCount(fullContent) {
      const text = String(fullContent || '');
      const pattern = /<第(\d+)次修改内容>/g;
      const matches = [];
      let match;
      while ((match = pattern.exec(text)) !== null) {
        matches.push(parseInt(match[1], 10));
      }
      if (matches.length === 0) return 1;
      return Math.max(...matches) + 1;
    },
    getOutputArticleMeta(card) {
      const cid = String(card?.cid || '');
      return this.outputArticleMetaByCid[cid] || { hasArticleContent: false, iterationCount: 1 };
    },
    async refreshOutputArticleCardMeta(cards) {
      const list = Array.isArray(cards) ? cards : [];
      const nextMeta = {};
      await Promise.all(list.map(async (card) => {
        const cid = String(card?.cid || '');
        if (!cid) return;
        try {
          const formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          formData.append('cid', cid);
          const cardData = await get_card(formData);
          const fullContent = cardData?.content?.content || '';
          nextMeta[cid] = {
            hasArticleContent: String(fullContent).includes('# '),
            iterationCount: this._extractOutputArticleIterationCount(fullContent),
          };
        } catch (e) {
          console.error('[refreshOutputArticleCardMeta] 获取卡片完整内容失败:', cid, e);
          nextMeta[cid] = { hasArticleContent: false, iterationCount: 1 };
        }
      }));
      this.outputArticleMetaByCid = nextMeta;
    },

    // 🔥 生成输出文章（支持指定目录卡）
    async generateOutputArticle(targetCard = null) {
      const card = targetCard || this.outputArticleCards[0] || null;
      if (!card || !card.cid || this.isGeneratingArticle) {
        return;
      }

      // 🔥 检查是否已有正文内容（调用API获取完整内容来判断）
      let hasArticleContent = false;
      try {
        const formData = new FormData();
        formData.append('username', localStorage.getItem('userId'));
        formData.append('cid', card.cid);
        const cardData = await get_card(formData);
        if (cardData && cardData.content && cardData.content.content) {
          const fullContent = cardData.content.content;
          // 检查完整内容中是否有"# "（说明已有正文）
          hasArticleContent = fullContent.includes('# ');
        }
      } catch (e) {
        console.error('[generateOutputArticle] 获取卡片完整内容失败:', e);
        // 如果获取失败，不阻止生成
      }
      
      // 如果有正文内容，需要确认
      if (hasArticleContent) {
        try {
          await ElMessageBox.confirm(
            '目录卡片已有正文内容，是否重新生成（可通过"回退"恢复）？',
            '确认重新生成',
            {
              confirmButtonText: '确定',
              cancelButtonText: '取消',
              type: 'warning'
            }
          );
        } catch {
          // 用户取消
          return;
        }
      }
      
      this.isGeneratingArticle = true;
      this.generatingOutputArticleCid = card.cid;
      this.articleGenerationProgress = {
        current: 0,
        total: 0,
        currentSection: ''
      };
      
      // 清理之前的轮询
      if (this.articleProgressInterval) {
        clearInterval(this.articleProgressInterval);
        this.articleProgressInterval = null;
      }
      
      try {
        const { API_BASE_URL } = require('@/config/apiConfig');
        
        // 声明taskId变量（在收到响应后赋值）
        let taskId = null;
        
        // 启动进度轮询函数
        const pollProgress = async () => {
          if (!taskId) return;
          try {
            const progressResponse = await fetch(`${API_BASE_URL}/api/article_generation_progress/${taskId}/`);
            if (progressResponse.ok) {
              const progressData = await progressResponse.json();
              this.articleGenerationProgress = {
                current: progressData.current_item || 0,
                total: progressData.total_items || this.articleGenerationProgress.total,
                currentSection: progressData.current_section || ''
              };
              
              // 如果任务完成，停止轮询
              if (progressData.completed || (this.articleGenerationProgress.current >= this.articleGenerationProgress.total && this.articleGenerationProgress.total > 0 && this.articleGenerationProgress.current > 0)) {
                if (this.articleProgressInterval) {
                  clearInterval(this.articleProgressInterval);
                  this.articleProgressInterval = null;
                }
                await this.get_all_cards();
                await this.refreshOutputArticleCardMeta(this.outputArticleCards);
                this.isGeneratingArticle = false;
                this.generatingOutputArticleCid = null;
                this.$message.success('文章生成成功');
                return;
              }
            }
          } catch (error) {
            console.error('[generateOutputArticle] 进度查询失败:', error);
          }
        };
        
        // 在发送请求的同时启动轮询（3秒后第一次，之后每15秒）
        setTimeout(() => {
          pollProgress();
          this.articleProgressInterval = setInterval(() => {
            pollProgress();
          }, 15000);
        }, 3000);
        
        // 发送生成请求
        const response = await fetch(`${API_BASE_URL}/api/generate_output_article`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            card_id: card.cid,
            username: localStorage.getItem('userId'),
            scene_name: this.sceneName
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        
        // 获取task_id和总任务数
        if (data.task_id && data.total_tasks) {
          taskId = data.task_id;
          this.articleGenerationProgress.total = data.total_tasks;
        }
        
        if (data.error_num === 0) {
          this.$message.success('文章生成中，请稍候...');
          // 进度更新和完成处理由SSE连接在后台处理
        } else {
          this.$message.error(data.msg || '文章生成失败');
          this.isGeneratingArticle = false;
          this.generatingOutputArticleCid = null;
          this.articleGenerationProgress = {
            current: 0,
            total: 0,
            currentSection: ''
          };
          // 清理轮询
          if (this.articleProgressInterval) {
            clearInterval(this.articleProgressInterval);
            this.articleProgressInterval = null;
          }
        }
      } catch (error) {
        console.error('[generateOutputArticle] 错误:', error);
        this.$message.error('文章生成失败');
        this.isGeneratingArticle = false;
        this.generatingOutputArticleCid = null;
        this.articleGenerationProgress = {
          current: 0,
          total: 0,
          currentSection: ''
        };
        // 清理轮询
        if (this.articleProgressInterval) {
          clearInterval(this.articleProgressInterval);
          this.articleProgressInterval = null;
        }
      }
    },

    // 🔥 提取部落知识
    async extractTribalKnowledge() {
      if (this.isExtractingTribalKnowledge) return;
      const { API_BASE_URL } = require('@/config/apiConfig');
      this.isExtractingTribalKnowledge = true;
      this.tribalKnowledgeProgress = { current: 0, total: 0, currentSection: '' };
      if (this.tribalProgressInterval) {
        clearInterval(this.tribalProgressInterval);
        this.tribalProgressInterval = null;
      }

      // 获取关键词网络图（与 analyzeCognitiveState 一致，供认知状态分析卡使用）
      let networkImageBase64 = '';
      const keywordGraph = this.$refs.keywordNetworkGraph;
      if (keywordGraph && keywordGraph.$refs && keywordGraph.$refs.networkSvg) {
        try {
          const svgElement = keywordGraph.$refs.networkSvg;
          const viewBox = svgElement.getAttribute('viewBox');
          let svgWidth = 800, svgHeight = 600;
          if (viewBox) {
            const parts = viewBox.split(' ');
            if (parts.length >= 4) { svgWidth = parseFloat(parts[2]) || 800; svgHeight = parseFloat(parts[3]) || 600; }
          }
          const svgData = new XMLSerializer().serializeToString(svgElement);
          const svgWithSize = svgData.replace(/<svg/, `<svg width="${svgWidth}" height="${svgHeight}"`);
          const svgBlob = new Blob([svgWithSize], { type: 'image/svg+xml;charset=utf-8' });
          const url = URL.createObjectURL(svgBlob);
          networkImageBase64 = await new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => {
              const canvas = document.createElement('canvas');
              canvas.width = svgWidth; canvas.height = svgHeight;
              const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0);
              resolve(canvas.toDataURL('image/png'));
              URL.revokeObjectURL(url);
            };
            img.onerror = () => { URL.revokeObjectURL(url); reject(); };
            img.src = url;
          });
        } catch (e) { console.warn('[extractTribalKnowledge] 获取网络图失败:', e); }
      }

      let taskId = null;
      const pollProgress = async () => {
        if (!taskId) return;
        try {
          const r = await fetch(`${API_BASE_URL}/api/tribal_knowledge_progress/${taskId}/`);
          if (r.ok) {
            const d = await r.json();
            this.tribalKnowledgeProgress = { current: d.current_item || 0, total: d.total_items || this.tribalKnowledgeProgress.total, currentSection: d.current_section || '' };
            if (d.completed || (this.tribalKnowledgeProgress.current >= this.tribalKnowledgeProgress.total && this.tribalKnowledgeProgress.total > 0 && this.tribalKnowledgeProgress.current > 0)) {
              if (this.tribalProgressInterval) { clearInterval(this.tribalProgressInterval); this.tribalProgressInterval = null; }
              await this.get_all_cards();
              this.isExtractingTribalKnowledge = false;
              this.$message.success(d.error ? '提取完成但部分失败：' + d.error : '部落知识提取完成');
              return;
            }
          }
        } catch (e) { console.error('[extractTribalKnowledge] 进度查询失败:', e); }
      };
      setTimeout(() => { pollProgress(); this.tribalProgressInterval = setInterval(pollProgress, 3000); }, 2000);
      try {
        const r = await fetch(`${API_BASE_URL}/api/extract_tribal_knowledge`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            username: localStorage.getItem('userId'),
            network_image: networkImageBase64
          })
        });
        const data = await r.json();
        if (data.task_id) taskId = data.task_id;
        if (data.total_tasks) this.tribalKnowledgeProgress.total = data.total_tasks;
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '提取失败');
          this.isExtractingTribalKnowledge = false;
          if (this.tribalProgressInterval) { clearInterval(this.tribalProgressInterval); this.tribalProgressInterval = null; }
        } else {
          this.$message.success('部落知识提取已启动，请稍候...');
        }
      } catch (e) {
        console.error('[extractTribalKnowledge] 错误:', e);
        this.$message.error('提取失败');
        this.isExtractingTribalKnowledge = false;
        if (this.tribalProgressInterval) { clearInterval(this.tribalProgressInterval); this.tribalProgressInterval = null; }
      }
    },

    // 🔥 格式化文档交叉梳理建议卡片内容（用于索引卡预览）
    formatCrossDocumentContent(content) {
      if (!content) return '';
      
      // 移除开头的"【文档全面交叉梳理建议卡片】"（如果存在）
      let formatted = content.replace(/^【文档全面交叉梳理建议卡片】\s*\n*/i, '').trim();

      // 🔥 去掉所有markdown字符（##、**、*、_、`、[]、()等）
      formatted = formatted
        .replace(/##\s*/g, '') // 去掉二级标题标记
        .replace(/#\s*/g, '')  // 去掉一级标题标记
        .replace(/\*\*([^*]+)\*\*/g, '$1') // 去掉加粗标记 **text** -> text
        .replace(/\*([^*]+)\*/g, '$1')     // 去掉斜体标记 *text* -> text
        .replace(/_([^_]+)_/g, '$1')       // 去掉下划线标记 _text_ -> text
        .replace(/`([^`]+)`/g, '$1')       // 去掉代码标记 `text` -> text
        .replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1') // 去掉链接标记 [text](url) -> text
        .replace(/[#*_`\[\]()]/g, '')      // 去掉所有剩余的markdown字符
        .replace(/\n{3,}/g, '\n\n');       // 多个换行压缩为两个
      
      // 截取前300字符作为预览
      // if (formatted.length > 300) {
      //   formatted = formatted.substring(0, 300) + '...';
      // }

      // 🔥 HTML转义，防止XSS攻击
      formatted = this.escapeHtml(formatted);
      
      // 将换行转换为<br>
      formatted = formatted.replace(/\n/g, '<br>');
      
      return formatted;
    },

    // 🔥 HTML转义函数（防止XSS攻击）
    escapeHtml(text) {
      const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
      };
      return text.replace(/[&<>"']/g, m => map[m]);
    },

    // 🔥 获取文档交叉梳理建议卡片的ID（供外部调用）
    getCrossDocumentSuggestionCardId() {
      const card = this.crossDocumentSuggestionCard;
      return card ? card.cid : null;
    },

    /** 仅绑在「查看详情」右键：打开小组本体弹窗，AnswerParser 渲染 Gxx.md */
    async openGroupTwinMarkdownDialog() {
      this.groupTwinDialogVisible = true;
      this.groupTwinMarkdown = '';
      await this.refreshTwinFileList(true);
    },

    async refreshTwinFileList(selectFirst) {
      const uid = localStorage.getItem('userId');
      if (!uid) return;
      this.groupTwinLoading = true;
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/group_twin_gxx_list?username=${encodeURIComponent(uid)}`
        );
        const data = await response.json();
        const files = (data && data.files) || [];
        this.groupTwinFileNames = files.map((f) => f.name).filter(Boolean);
        if (selectFirst && this.groupTwinFileNames.length > 0) {
          this.selectedGroupTwinFile = this.groupTwinFileNames[0];
          await this.loadSelectedTwinContent();
        } else if (!this.groupTwinFileNames.includes(this.selectedGroupTwinFile)) {
          this.selectedGroupTwinFile = this.groupTwinFileNames[0] || '';
          if (this.selectedGroupTwinFile) await this.loadSelectedTwinContent();
        }
      } catch (e) {
        console.error('[groupTwin] list failed', e);
        this.$message.error('加载小组本体数字孪生文件列表失败');
      } finally {
        this.groupTwinLoading = false;
      }
    },

    async loadSelectedTwinContent() {
      const uid = localStorage.getItem('userId');
      const name = this.selectedGroupTwinFile;
      if (!uid || !name) {
        this.groupTwinMarkdown = '';
        return;
      }
      this.groupTwinLoading = true;
      try {
        const response = await fetch(
          `${API_BASE_URL}/api/group_twin_gxx_content?username=${encodeURIComponent(uid)}&name=${encodeURIComponent(name)}`
        );
        const data = await response.json();
        if (data && data.error_num === 0 && data.content) {
          this.groupTwinMarkdown = data.content;
        } else {
          this.groupTwinMarkdown = '';
          this.$message.warning(data.msg || '读取失败');
        }
      } catch (e) {
        console.error('[groupTwin] content failed', e);
        this.$message.error('读取小组本体数字孪生内容失败');
      } finally {
        this.groupTwinLoading = false;
      }
    },

    // 问题评论相关方法
    handleQuestionClick(question, event) {
      // 防止双击时触发单击事件
      if (this.clickTimer) {
        clearTimeout(this.clickTimer);
        this.clickTimer = null;
        return; // 双击事件会处理，不执行单击逻辑
      }
      
      // 延迟执行单击事件，给双击事件留出时间
      this.clickTimer = setTimeout(() => {
        this.scrollToCard(question.cid);
        this.clickTimer = null;
      }, 200);
    },

    openQuestionComment(question, idx) {
      console.log('双击事件触发', question);
      // 清除单击定时器，防止单击事件执行
      if (this.clickTimer) {
        clearTimeout(this.clickTimer);
        this.clickTimer = null;
      }
      
      this.currentQuestionComment = question;
      this.questionCommentText = question.comment || '';
      this.questionCommentDialogVisible = true;
    },

    cancelQuestionComment() {
      this.questionCommentDialogVisible = false;
      this.currentQuestionComment = null;
      this.questionCommentText = '';
    },

    async saveQuestionComment() {
      if (!this.currentQuestionComment) return;
      
      this.commentSaving = true;
      try {
        // 调用后端API保存评论
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取

        const response = await fetch(`${BASE_URL}/api/save_question_comment`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            cid: this.currentQuestionComment.cid,
            question: this.currentQuestionComment.question,
            comment: this.questionCommentText,
            user: localStorage.getItem('userId')
          })
        });
        
        const result = await response.json();
        if (result.error_num === 0) {
          // 更新本地数据
          this.currentQuestionComment.comment = this.questionCommentText;
          this.$message.success('评论保存成功');
          this.questionCommentDialogVisible = false;
        } else {
          this.$message.error('保存失败：' + result.message);
        }
      } catch (error) {
        console.error('保存评论失败:', error);
        this.$message.error('保存评论失败');
      } finally {
        this.commentSaving = false;
      }
    },


    // 问题提取和评估方法
    extractQuestionsFromCard(card) {
      const questions = [];
      // 🔥 使用content_preview字段（content前100字符）来提取提问内容，确保能提取到"提问：xxx"
      const content = card.content_preview || card.content || '';
      
      // 匹配 "提问：xxx" 或 "迭代追问：xxx" 格式
      const questionPatterns = [
        /提问：\s*([^\n\r]+)/g,
        /迭代追问：\s*([^\n\r]+)/g
      ];
      
      questionPatterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
          const question = match[1].trim();
          if (question && question.length > 5) { // 过滤太短的问题
            questions.push({
              question: question,
              type: pattern.source.includes('提问') ? '提问' : '迭代追问'
            });
          }
        }
      });
      
      return questions;
    },

    // 初始化问题列表
    initializeQuestions() {
      if (!this.filteredCards || this.filteredCards.length === 0) {
        this.sortedQuestions = [];
        return;
      }
      
      const questions = [];
      
      this.filteredCards.forEach(card => {
        const extractedQuestions = this.extractQuestionsFromCard(card);
        extractedQuestions.forEach(questionData => {
          // 异步评估，先设置默认值
          questions.push({
            cid: card.cid,
            question: questionData.question,
            author: card.writer || card.username,
            score: card.scoreSFT > 0 ? card.scoreSFT : card.score,
            comment: card.question_comment || '',
            evaluation: {
              entropyScore: '计算中...',
              sceneMatch: '计算中...',
              docRelevance: '计算中...',
              totalScore: '0.0'
            },
            originalCard: card
          });
        });
      });
      
      // // 初始排序（按默认值）
      // this.sortedQuestions = questions.sort((a, b) => {
      //   const scoreA = parseFloat(a.evaluation.totalScore) || 0;
      //   const scoreB = parseFloat(b.evaluation.totalScore) || 0;
      //   return scoreB - scoreA; // 降序排列
      // });
      
      // // 异步评估所有问题
      // this.evaluateAllQuestions(questions);

      // 🔥 尝试使用保存的排序顺序
      const savedOrder = this.questionChainSortedOrder || [];
      if (savedOrder && savedOrder.length > 0) {
        const cidToQuestion = new Map();
        questions.forEach(q => {
          cidToQuestion.set(String(q.cid), q);
        });
        
        const sortedQuestions = [];
        savedOrder.forEach(cid => {
          const question = cidToQuestion.get(String(cid));
          if (question) {
            sortedQuestions.push(question);
          }
        });
        
        // 添加未在排序顺序中的问题（按原有顺序）
        const orderedCidSet = new Set(savedOrder.map(c => String(c)));
        questions.forEach(q => {
          if (!orderedCidSet.has(String(q.cid))) {
            sortedQuestions.push(q);
          }
        });
        
        this.sortedQuestions = sortedQuestions;
        console.log('[CardGrid] 使用保存的排序顺序，问题数量:', sortedQuestions.length);
      } else {
        // 初始排序（按默认值）
        this.sortedQuestions = questions.sort((a, b) => {
          const scoreA = parseFloat(a.evaluation.totalScore) || 0;
          const scoreB = parseFloat(b.evaluation.totalScore) || 0;
          return scoreB - scoreA; // 降序排列
        });
      }
      
      // 异步评估所有问题
      this.evaluateAllQuestions(this.sortedQuestions);
    },

    async evaluateQuestion(question, card) {
      // 1. 信息熵评分 (基于问题长度、词汇多样性等)
      const entropyScore = this.calculateEntropyScore(question);
      
      // 2. 场景匹配度 (基于卡片标题中的子场景)
      const sceneMatch = await this.calculateSceneMatch(question, card);
      
      // 3. 文档相关度 (如果有文件列表)
      const docRelevance = await this.calculateDocRelevance(question, card);
      
      // 4. 综合评分
      const totalScore = (entropyScore * 0.45 + sceneMatch * 0.2 + docRelevance * 0.35);
      
      return {
        entropyScore: entropyScore.toFixed(1),
        sceneMatch: sceneMatch.toFixed(1),
        docRelevance: docRelevance.toFixed(1),
        totalScore: totalScore.toFixed(1)
      };
    },

    calculateEntropyScore(question) {
      // 基于问题长度、问号数量、词汇多样性等计算信息熵（中文优化）
      const length = question.length;
      const questionMarks = (question.match(/[？?]/g) || []).length;
      
      // 中文分词：按字符分割，但考虑中文词汇边界
      const words = this.chineseWordSegmentation(question);
      const uniqueWords = new Set(words).size;
      
      // 基础分数（调整为5分制）
      let score = Math.min(length / 10, 2.0); // 长度分数，中文每10字符1分，最多2.0分
      score += Math.min(questionMarks * 1, 1.5); // 问号分数，最多1.5分
      score += Math.min(uniqueWords / Math.max(words.length, 1) * 2.5, 1.5); // 词汇多样性，最多1.5分
      
      return Math.min(score, 5); // 总分不超过5分
    },

    // 简单的中文分词
    chineseWordSegmentation(text) {
      // 移除标点符号，按中文字符和英文单词分割
      const cleanText = text.replace(/[，。！？；：""''（）【】\s]/g, ' ');
      const words = [];
      
      // 分割中文字符和英文单词
      const segments = cleanText.split(/([a-zA-Z]+|[^\u4e00-\u9fa5a-zA-Z\s]+)/);
      
      segments.forEach(segment => {
        if (segment.trim()) {
          if (/[\u4e00-\u9fa5]/.test(segment)) {
            // 中文字符，按2-3字符组合
            for (let i = 0; i < segment.length - 1; i++) {
              words.push(segment.substr(i, 2));
            }
            if (segment.length >= 3) {
              for (let i = 0; i < segment.length - 2; i++) {
                words.push(segment.substr(i, 3));
              }
            }
          } else if (/[a-zA-Z]/.test(segment)) {
            // 英文单词
            words.push(segment.toLowerCase());
          }
        }
      });
      
      return words;
    },

    async calculateSceneMatch(question, card) {
      // 基于卡片标题中的子场景编号和LUI2 systemPrompt符合度
      const title = card.contentTitle || '';
      const sceneMatch = title.match(/S(\d+)[:：]/);
      
      if (!sceneMatch) return 2.5; // 默认分数（5分制）
      
      const sceneNumber = parseInt(sceneMatch[1]);
      console.log("获取场景LUI2 Prompt，用于问题链索引卡问题质量评估排序")
      
      try {
        // 获取LUI2 systemPrompt
        const systemPrompt = await this.getLUI2SystemPrompt(sceneNumber);
        if (!systemPrompt) return 2.5;
        
        // 计算问题与systemPrompt的相似度
        const similarity = this.calculateTextSimilarity(question, systemPrompt);
        
        // 基础分数 + 相似度分数（调整为5分制）
        let baseScore = 2.5;
        if (sceneNumber < 2) baseScore = 2.2; // 早期场景
        else if (sceneNumber <= 3) baseScore = 2.5; // 中期场景
        else if (sceneNumber >= 5) baseScore = 3; // 后期场景
        else baseScore = 2.8; // 中后期场景

        // 根据场景阶段和问题类型调整基础分数
        if (sceneNumber < 2) {
          // 初期阶段：鼓励基础问题
          if (question.includes('什么') || question.includes('是否') || question.includes('为什么')) {
            baseScore += 0.5; // 提高基础分数
          }
        } else if (sceneNumber <= 3) {
          // 中期阶段：鼓励方法性问题
          if (question.includes('如何') || question.includes('怎样') || question.includes('怎么')) {
            baseScore += 0.3; // 提高基础分数
          }
        } else if (sceneNumber >= 5) {
          // 后期阶段：鼓励深入思考
          if (question.includes('优化') || question.includes('改进') || 
              question.includes('策略') || question.includes('方案') || question.includes('框架') ||
              question.includes('体系') || question.includes('机制') || question.includes('模式') ||
              question.includes('趋势') || question.includes('关联') ||
              question.includes('本质') || question.includes('深层') || question.includes('根本')) {
            baseScore += 0.2; // 适度提高基础分数
          }
        }
        
        return Math.min(baseScore + similarity * 2, 5); // 相似度最多加2分，确保不超过5分
      } catch (error) {
        console.warn('获取LUI2 systemPrompt失败:', error);
        return 2.5; // 默认分数
      }
    },

    // 获取LUI2 systemPrompt
    async getLUI2SystemPrompt(sceneNumber) {
      try {
        const userId = localStorage.getItem('userId');
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取
        const response = await fetch(`${BASE_URL}/api/get_lui2_prompt?scene=${sceneNumber}&user=${userId}`);
        if (response.ok) {
          const data = await response.json();
          return data.prompt;
        }
      } catch (error) {
        console.warn('获取LUI2 prompt失败:', error);
      }
      return null;
    },

    // 计算文本相似度（中文相似度计算）
    calculateTextSimilarity(text1, text2) {
      // 中英文混合文本相似度计算
      const tokens1 = this.extractMixedLanguageTokens(text1);
      const tokens2 = this.extractMixedLanguageTokens(text2);
      
      // 计算多种相似度指标
      const jaccardSim = this.calculateJaccardSimilarity(tokens1, tokens2);
      const overlapSim = this.calculateOverlapSimilarity(tokens1, tokens2);
      const semanticSim = this.calculateSemanticSimilarity(tokens1, tokens2);
      
      // 加权平均，语义相似度权重更高
      const finalSimilarity = jaccardSim * 0.3 + overlapSim * 0.3 + semanticSim * 0.4;
      
      return Math.min(finalSimilarity, 1.0);
    },

    // 提取中英文混合词汇
    extractMixedLanguageTokens(text) {
      const tokens = [];
      
      // 处理中文字符（2-3字符组合）
      const chineseMatches = text.match(/[\u4e00-\u9fa5]+/g) || [];
      chineseMatches.forEach(match => {
        // 2字符组合
        for (let i = 0; i < match.length - 1; i++) {
          tokens.push(match.substr(i, 2));
        }
        // 3字符组合
        for (let i = 0; i < match.length - 2; i++) {
          tokens.push(match.substr(i, 3));
        }
        // 完整词（如果长度>3）
        if (match.length > 3) {
          tokens.push(match);
        }
      });
      
      // 处理英文单词
      const englishMatches = text.match(/[a-zA-Z]+/g) || [];
      englishMatches.forEach(match => {
        const word = match.toLowerCase();
        if (word.length > 1) {
          tokens.push(word);
          // 添加词根（简单处理）
          if (word.length > 3) {
            tokens.push(word.substring(0, word.length - 1));
          }
        }
      });
      
      // 处理数字
      const numberMatches = text.match(/\d+/g) || [];
      numberMatches.forEach(match => {
        tokens.push(match);
      });
      
      return tokens;
    },

    // 计算Jaccard相似度
    calculateJaccardSimilarity(tokens1, tokens2) {
      const set1 = new Set(tokens1);
      const set2 = new Set(tokens2);
      
      const intersection = new Set([...set1].filter(x => set2.has(x)));
      const union = new Set([...set1, ...set2]);
      
      return union.size > 0 ? intersection.size / union.size : 0;
    },

    // 计算重叠相似度
    calculateOverlapSimilarity(tokens1, tokens2) {
      const set1 = new Set(tokens1);
      const set2 = new Set(tokens2);
      
      const intersection = new Set([...set1].filter(x => set2.has(x)));
      const minSize = Math.min(set1.size, set2.size);
      
      return minSize > 0 ? intersection.size / minSize : 0;
    },

    // 计算语义相似度（基于部分匹配和长度相似性）
    calculateSemanticSimilarity(tokens1, tokens2) {
      let totalScore = 0;
      let matchCount = 0;
      
      // 精确匹配
      const set1 = new Set(tokens1);
      const set2 = new Set(tokens2);
      const exactMatches = new Set([...set1].filter(x => set2.has(x)));
      totalScore += exactMatches.size * 1.0;
      matchCount += exactMatches.size;
      
      // 部分匹配（子字符串匹配）
      for (const token1 of tokens1) {
        for (const token2 of tokens2) {
          if (token1 !== token2 && token1.length > 2 && token2.length > 2) {
            if (token1.includes(token2) || token2.includes(token1)) {
              totalScore += 0.5;
              matchCount += 0.5;
            }
          }
        }
      }
      
      // 长度相似性奖励
      const lengthRatio = Math.min(tokens1.length, tokens2.length) / Math.max(tokens1.length, tokens2.length);
      totalScore += lengthRatio * 0.5;
      matchCount += 0.5;
      
      return matchCount > 0 ? totalScore / matchCount : 0;
    },

    async calculateDocRelevance(question, card) {
      // 🔥 优化：基于卡片的selected_docs或history中的文件列表计算相关度
      try {
        // 尝试从多个来源获取文件列表
        let fileList = [];
        
        // 1. 优先从 selected_docs 获取
        if (card.selected_docs) {
          const docs = typeof card.selected_docs === 'string' ? card.selected_docs : '';
          fileList = docs.split(',').map(d => d.trim()).filter(d => d);
        }
        
        // 2. 如果没有，从 history 获取
        if (fileList.length === 0 && card.history && card.history.data && card.history.data.length > 0) {
          fileList = card.history.data[0]?.filelist || [];
        }
        
        // 3. 如果还是没有，尝试从 history 的其他格式获取
        if (fileList.length === 0 && card.history) {
          // 尝试解析 history 中可能的文件引用
          const historyStr = typeof card.history === 'string' ? card.history : JSON.stringify(card.history);
          const fileMatches = historyStr.match(/["']([^"']+\.(pdf|txt|docx?|md))["']/gi);
          if (fileMatches) {
            fileList = fileMatches.map(m => m.replace(/["']/g, '')).slice(0, 5);
          }
        }
        
        // 如果没有文件列表，基于问题和卡片内容计算基础相关度
        if (fileList.length === 0) {
          // 使用问题和卡片内容的关键词重叠度作为替代
          const cardContent = card.content || '';
          const overlap = this.calculateKeywordOverlap(question, cardContent.substring(0, 500));
          // 🔥 调整：提高基础分数，放大重叠度贡献
          // overlap通常在0.05-0.3之间，使用平方根放大小值
          const amplifiedOverlap = Math.sqrt(overlap);
          return 2.8 + amplifiedOverlap * 2.2;  // 基础2.8分 + 最多2.2分
        }
        
        // 获取文档内容并计算相似度
        const docSimilarities = await this.calculateDocSimilarities(question, fileList);
        
        if (docSimilarities.length === 0) {
          return 3.0;  // 🔥 提高默认分数
        }
        
        // 计算平均相似度和关键词重叠度
        const avgSimilarity = docSimilarities.reduce((sum, sim) => sum + sim.similarity, 0) / docSimilarities.length;
        const avgKeywordOverlap = docSimilarities.reduce((sum, sim) => sum + sim.keywordOverlap, 0) / docSimilarities.length;
        
        // 🔥 调整：使用平方根放大低相似度值，提高基础分和权重
        // avgSimilarity 和 avgKeywordOverlap 通常在 0.05-0.3 之间
        const amplifiedSimilarity = Math.sqrt(avgSimilarity);
        const amplifiedOverlap = Math.sqrt(avgKeywordOverlap);
        
        // 🔥 新公式：基础3分 + 相似度贡献（最多1分）+ 关键词重叠贡献（最多1分）
        // 有文档关联本身就说明相关度不低，所以基础分给高
        const relevanceScore = 3.0 + amplifiedSimilarity * 1.0 + amplifiedOverlap * 1.0;
        
        return Math.min(relevanceScore, 5);
      } catch (error) {
        console.warn('计算文档相关度失败:', error);
        return 3.0;
      }
    },

    // 计算与多个文档的相似度
    async calculateDocSimilarities(question, fileList) {
      const similarities = [];
      
      // 随机选择3个文件（如果文件数超过3个）
      const selectedFiles = fileList.length > 3 
        ? fileList.sort(() => 0.5 - Math.random()).slice(0, 3)
        : fileList;
      
      for (const fileName of selectedFiles) {
        try {
          const docContent = await this.getDocumentContent(fileName);
          if (docContent) {
            // 随机选择500字符的片段
            const randomSnippets = this.getRandomSnippets(docContent, 3, 300);
            
            let maxSimilarity = 0;
            let maxKeywordOverlap = 0;
            
            for (const snippet of randomSnippets) {
              const similarity = this.calculateTextSimilarity(question, snippet);
              const keywordOverlap = this.calculateKeywordOverlap(question, snippet);
              
              maxSimilarity = Math.max(maxSimilarity, similarity);
              maxKeywordOverlap = Math.max(maxKeywordOverlap, keywordOverlap);
            }
            
            similarities.push({
              similarity: maxSimilarity,
              keywordOverlap: maxKeywordOverlap
            });
          }
        } catch (error) {
          console.warn(`获取文档内容失败: ${fileName}`, error);
        }
      }
      
      return similarities;
    },

    // 获取文档内容
    async getDocumentContent(fileName) {
      try {
        const userId = localStorage.getItem('userId');
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取
        const response = await fetch(`${BASE_URL}/api/get_document_content?file=${encodeURIComponent(fileName)}&user=${userId}`);
        if (response.ok) {
          const data = await response.json();
          return data.content;
        }
      } catch (error) {
        console.warn('获取文档内容失败:', error);
      }
      return null;
    },

    // 获取随机文档片段
    getRandomSnippets(content, count, length) {
      if (content.length <= length) return [content];
      
      const snippets = [];
      for (let i = 0; i < count; i++) {
        const start = Math.floor(Math.random() * (content.length - length));
        snippets.push(content.substr(start, length));
      }
      return snippets;
    },

    // 计算关键词重叠度
    calculateKeywordOverlap(text1, text2) {
      const words1 = this.chineseWordSegmentation(text1);
      const words2 = this.chineseWordSegmentation(text2);
      
      // 提取关键词（长度大于1的词）
      const keywords1 = words1.filter(word => word.length > 1);
      const keywords2 = words2.filter(word => word.length > 1);
      
      const set1 = new Set(keywords1);
      const set2 = new Set(keywords2);
      
      const intersection = new Set([...set1].filter(x => set2.has(x)));
      const union = new Set([...set1, ...set2]);
      
      return intersection.size / Math.max(union.size, 1);
    },

    // 问题提示框相关方法
    showQuestionTooltip(event, question) {
      this.currentQuestionEvaluation = question.evaluation;
      this.questionTooltipVisible = true;
      
      const rect = event.target.getBoundingClientRect();
      this.questionTooltipStyle = {
        position: 'fixed',
        top: `${rect.top - 10}px`,
        left: `${rect.right + 10}px`,
        zIndex: 9999
      };
    },

    hideQuestionTooltip() {
      this.questionTooltipVisible = false;
      this.currentQuestionEvaluation = null;
    },

    // 显示问题完整文本
    showQuestionFullText(event, questionText) {
      this.currentQuestionFullText = questionText;
      this.questionFullTextVisible = true;
      
      const rect = event.target.getBoundingClientRect();
      this.questionFullTextStyle = {
        position: 'fixed',
        top: `${rect.top - 10}px`,
        left: `${rect.right + 10}px`,
        zIndex: 9999
      };
    },

    hideQuestionFullText() {
      this.questionFullTextVisible = false;
      this.currentQuestionFullText = '';
    },

    // 异步评估所有问题
    async evaluateAllQuestions(questions) {
      for (const question of questions) {
        try {
          const evaluation = await this.evaluateQuestion(question.question, question.originalCard);
          question.evaluation = evaluation;
        } catch (error) {
          console.warn('评估问题失败:', error);
          question.evaluation = {
            entropyScore: '错误',
            sceneMatch: '错误',
            docRelevance: '错误',
            totalScore: '0.0'
          };
        }
      }
      
      // 🔥 如果有保存的排序顺序，保持排序顺序不变，不重新排序
      const savedOrder = this.questionChainSortedOrder || [];
      if (savedOrder && savedOrder.length > 0) {
        console.log('[CardGrid] 有保存的排序顺序，保持排序不变');
        // 保持当前sortedQuestions的顺序（已经在initializeQuestions中应用了排序）
        return;
      }
      
      // 🔥 如果没有保存的排序顺序，重新排序：先按是否有四色DMT属性排序，紫色/绿色优先，没有属性的放后面
      this.sortedQuestions = questions.sort((a, b) => {
        const cardA = a.originalCard || {};
        const cardB = b.originalCard || {};
        
        // 获取四色类型
        const colorA = cardA.four_color_type || '';
        const colorB = cardB.four_color_type || '';
        
        // 优先级：紫色P=1, 绿色G=2, 红色R=3, 蓝色B=4, 无色=5
        const colorPriority = { 'P': 1, 'G': 2, 'R': 3, 'B': 4 };
        const priorityA = colorA ? (colorPriority[colorA] || 4) : 5;
        const priorityB = colorB ? (colorPriority[colorB] || 4) : 5;
        
        // 先按颜色优先级排序
        if (priorityA !== priorityB) {
          return priorityA - priorityB;
        }
        
        // 同优先级下，按评分降序
        const scoreA = parseFloat(a.evaluation.totalScore) || 0;
        const scoreB = parseFloat(b.evaluation.totalScore) || 0;
        return scoreB - scoreA;
      });
    },

    // 🔥 智能排序问题链
    async smartSortQuestions() {
      try {
        // 1. 收集所有问题
        if (!this.sortedQuestions || this.sortedQuestions.length === 0) {
          console.log('[CardGrid] 没有问题需要排序');
          return;
        }
        
        const questions = this.sortedQuestions.map(q => {
          const card = q.originalCard || {};
          // 提取子场景（从contentTitle中提取S1、S2等）
          let sub_scene = '';
          if (card.contentTitle) {
            const match = card.contentTitle.match(/^(S\d+)/);
            if (match) {
              sub_scene = match[1];
            }
          }
          
          return {
            cid: String(q.cid),
            question: q.question,
            author: q.author || card.writer || card.username || '',
            sub_scene: sub_scene,
            datetime: card.datetime || ''
          };
        });
        
        console.log(`[CardGrid] 准备调用智能排序API，问题数量: ${questions.length}`);
        
        // 2. 调用后端API
        const { API_BASE_URL } = require('@/config/apiConfig');
        const response = await fetch(`${API_BASE_URL}/api/smart_sort_questions`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            username: localStorage.getItem('userId'),
            scene_name: this.sceneName,
            questions: questions
          })
        });
        
        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }
        
        const data = await response.json();
        if (!data.success) {
          throw new Error(data.msg || '排序失败');
        }
        
        const sorted_cids = data.sorted_cids || [];
        if (sorted_cids.length === 0) {
          console.warn('[CardGrid] 排序API返回空的CID列表');
          return;
        }
        
        console.log(`[CardGrid] 排序成功，排序后的CID数量: ${sorted_cids.length}`);
        
        // 3. 根据排序结果重新排列sortedQuestions
        const cidToQuestion = new Map();
        this.sortedQuestions.forEach(q => {
          cidToQuestion.set(String(q.cid), q);
        });
        
        const sortedQuestions = [];
        sorted_cids.forEach(cid => {
          const question = cidToQuestion.get(cid);
          if (question) {
            sortedQuestions.push(question);
          }
        });
        
        // 如果排序后的数量与原始不一致，添加缺失的问题
        if (sortedQuestions.length < this.sortedQuestions.length) {
          const sortedCidSet = new Set(sorted_cids);
          this.sortedQuestions.forEach(q => {
            if (!sortedCidSet.has(String(q.cid))) {
              sortedQuestions.push(q);
            }
          });
        }
        
        this.sortedQuestions = sortedQuestions;
        this.questionChainSortedOrder = sorted_cids; // 保存排序结果
        this.questionChainCategories = data.categories || {}; // 保存分类结果
        console.log('[CardGrid] 问题链智能排序完成，已保存排序顺序和分类信息');
        
      } catch (error) {
        console.error('[CardGrid] 智能排序问题链失败:', error);
        // 排序失败不影响正常使用，只记录错误
      }
    },

    // 🔥 获取问题对应卡片的DMT字母
    getQuestionDMTLetter(question) {
      const card = question.originalCard || {};
      const dmtLevel = card.dmt_level || '';
      const fourColor = card.four_color_type || '';
      if (!dmtLevel && !fourColor) return '无';
      return dmtLevel || '-';
    },
    
    // 🔥 获取问题对应卡片的四色颜色
    getQuestionDMTColor(question) {
      const card = question.originalCard || {};
      const fourColor = card.four_color_type || '';
      const colorMap = {
        'R': '#dc3545',  // 红色
        'B': '#007bff',  // 蓝色
        'P': '#6f42c1',  // 紫色
        'G': '#28a745'   // 绿色
      };
      return colorMap[fourColor] || '#888888';  // 无色时用灰色
    },
    
    // 🔥 获取问题DMT的tooltip标题
    getQuestionDMTTitle(question) {
      const card = question.originalCard || {};
      const dmtLevel = card.dmt_level || '';
      const fourColor = card.four_color_type || '';
      
      const dmtNames = { 'D': '枝（具体执行）', 'M': '干（策略连接）', 'T': '根（抽象框架）' };
      const colorNames = { 'R': '红色（专业业务）', 'B': '蓝色（工具手段）', 'P': '紫色（思维框架）', 'G': '绿色（简单深刻）' };
      
      const parts = [];
      if (fourColor) parts.push(colorNames[fourColor] || fourColor);
      if (dmtLevel) parts.push(dmtNames[dmtLevel] || dmtLevel);
      
      return parts.length > 0 ? parts.join(' / ') : '无四色/DMT属性';
    },


    reloadAutoCards() {
      this.isInitial = false
      this.get_all_cards();
      this.$message.success('后台自动完成的卡片已加载！');
    },

    // 后置索引设置的弹窗
    openPostIndexDialog(card) {
      this.openPostIndexEditor(card)
    },

    // 获取后置索引数量
    getPostIndexCount(card) {
      if (!card.postIndex) return 0;
      
      // 如果 postIndex 是数组
      if (Array.isArray(card.postIndex)) {
        return card.postIndex.length;
      }
      
      // 如果 postIndex 是字符串，按逗号分割计算
      if (typeof card.postIndex === 'string') {
        return card.postIndex.split(',').filter(item => item.trim()).length;
      }
      
      return 0;
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

    // 显示tooltip
    showTooltip(event, card) {
      // 获取后置索引内容
      let indexContent = '';
      
      if (card.postIndex) {
        // 解析cid并转换为对应的标题, 使用用户设置的后置索引
        const cidList = this.parsePostIndex(card.postIndex);
        const titles = cidList.map(cid => {
          // 查找对应的标题
          // return this.cidToTitleMap[cid] || this.extractKeyword(this.findCardByCid(cid)?.contentTitle) || `未知(${cid})`;
          const card = this.findCardByCid(cid);
          if (card && card.contentTitle) {
            return this.cidToTitleMap[cid] || this.extractKeyword(card.contentTitle) || card.contentTitle || `未知(${cid})`;
          }
          return this.cidToTitleMap[cid] || `未知(${cid})`;
        });
        
        indexContent = titles.length > 0 ? titles.join(' · ') : '点击设置后置索引';
      } else {
        // 没有设置后置索引时，显示需要设置
        indexContent = "暂无后置索引，请先设置";
      }
      
      // 设置内容
      this.tooltipElement.innerHTML = indexContent || '点击设置后置索引';
      
      // 计算位置
      const iconRect = event.target.getBoundingClientRect();
      
      // 将tooltip定位在图标右侧
      this.tooltipElement.style.left = (iconRect.right + 10) + 'px';
      this.tooltipElement.style.top = (iconRect.top + (iconRect.height / 2) - 10) + 'px';
      
      // 显示tooltip
      this.tooltipElement.style.display = 'block';
    },
    
    // 隐藏tooltip
    hideTooltip() {
      this.tooltipElement.style.display = 'none';
    },

    // 根据cid查找卡片
    findCardByCid(cid) {
      return this.cardList.find(card => card.cid.toString() === cid.toString());
    },
    
    // 打开后置索引编辑器
    openPostIndexEditor(card) {
      this.currentEditCard = card;

      // 解析现有的后置索引（cid列表）
      // this.selectedPostIndices = [...(card.postIndex || [])];
      this.selectedPostIndices = this.parsePostIndex(card.postIndex);
      this.customPostIndex = '';
      this.postIndexDialogVisible = true;
    },
    
    // 保存后置索引
    savePostIndex() {
      if (!this.currentEditCard) return;
      
      // 使用选中的cid
      let indices = [...this.selectedPostIndices];

      // 处理自定义索引（这里需要考虑如何处理自定义输入，因为我们存储的是cid）
      // 自定义输入可能需要另外处理或者禁用，因为用户输入的是标题而非cid
      // 这里简化处理，假设用户输入的是cid
      if (this.customPostIndex.trim()) {
        const customIndices = this.customPostIndex.split(/[,，、]+/)
          .map(item => item.trim())
          .filter(item => item);
        
        indices = [...indices, ...customIndices];
      }
      
      // // 处理自定义索引（按逗号分隔）
      // if (this.customPostIndex.trim()) {
      //   const customIndices = this.customPostIndex.split(',')
      //     .map(item => item.trim())
      //     .filter(item => item);
        
      //   indices = [...indices, ...customIndices];
      // }
      
      // 去重
      indices = [...new Set(indices)];
      
      // 更新卡片的后置索引
      // this.currentEditCard.postIndex = indices;
      // 更新卡片的后置索引（转为JSON字符串）
      this.currentEditCard.postIndex = JSON.stringify(indices);
      
      // 关闭对话框
      this.postIndexDialogVisible = false;
      
      // 可能需要将更新后的数据保存到数据库
      this.saveCardsToDatabase(this.currentEditCard);
    },
    
    // 保存卡片数据到数据库（根据实际情况实现）
    saveCardsToDatabase(card) {
      // 实现数据持久化逻辑
      console.log('保存卡片数据', card);

      let formData = new FormData();
      formData.append('cid', card.cid);
      formData.append('username', localStorage.getItem('userId'));
      formData.append('postIndex', card.postIndex);

      cardUpdPostIndex(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('后置索引更新成功！');
        }
        else {
          this.$message.error(`后置索引更新未成功: ${response.msg}`);
        }
      })
    },

    // 提取关键词（辅助方法）
    extractKeyword(title) {
      if (!title || typeof title !== 'string') {
        return '';
      }

      const match = title.match(/.*[：:]\s*(.*?)$/);
      if (match && match[1]) {
        const content = match[1].trim();
        if (content.length > 4) {
          return content.slice(-2);
        }
        return content;
      }
      return title.length > 2 ? title.slice(-2) : title;
    },

    // // 显示tooltip
    // showTooltip(event, content) {
    //   // 设置内容
    //   this.tooltipElement.innerHTML = content;
      
    //   // 计算位置
    //   const iconRect = event.target.getBoundingClientRect();
    //   const tooltipRect = this.tooltipElement.getBoundingClientRect();
      
    //   // 将tooltip定位在图标右侧
    //   this.tooltipElement.style.left = (iconRect.right + 10) + 'px';
    //   this.tooltipElement.style.top = (iconRect.top + (iconRect.height / 2) - (tooltipRect.height / 2)) + 'px';
      
    //   // 显示tooltip
    //   this.tooltipElement.style.display = 'block';
    // },
    
    // // 隐藏tooltip
    // hideTooltip() {
    //   this.tooltipElement.style.display = 'none';
    // },
    
    // // 获取简短标题（可以根据需要自定义截取逻辑）
    // extractKeyword(title) {
    //   // 例如：从"S1:小学生数学作业"提取"作业"，或者其他缩略显示方式
    //   const match = title.match(/^S\d+:(.+)/);
    //   if (match && match[1]) {
    //     const fullText = match[1].trim();
    //     if (fullText.length > 4) {
    //       return fullText.slice(-2); // 返回最后两个字符
    //     }
    //     return fullText;
    //   }
    //   return title;
    // },

    chosenOver(chosenContent) {
      if (this.openCardId) {
        console.log('当前打开的卡片ID:', this.openCardId);
        
        // 查找具有该cid的卡片组件
        const cardRef = this.$refs.cardRefs && this.$refs.cardRefs.find(card => card.cid === this.openCardId);
        
        if (cardRef) {
          console.log('找到对应的卡片组件，调用onCheckboxChange方法');
          cardRef.onCheckboxChange();
          setTimeout(() => {
            if(this.choosedCardIdList.includes(this.openCardId)) {
            } else {
              cardRef.onCheckboxChange();
            }
            this.$emit('chosenOver', this.openCardId, chosenContent)
          }, 200);
        } else {
          console.log('未找到对应的卡片组件');
        }
      }
    },

    cardTidyUp() {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }
      
      let formData = new FormData();
      let cid = this.choosedCardIdList[0]
      formData.append('cid', cid);
      formData.append('username', localStorage.getItem('userId'));
      // 构建卡片标题和前置索引的字符串
      let titlesAndIndexes = '';
      if (this.contentTitles && this.preIndexs) {
        for (let i = 0; i < this.contentTitles.length; i++) {
          titlesAndIndexes += `卡片${i+1}标题：${this.contentTitles[i]}，前置索引：${this.preIndexs[i] !== null ? this.preIndexs[i] : '无'}\n`;
        }
      }
      formData.append('cardAllTitlesAndIndexes', titlesAndIndexes);

      this.cardTidying = true
      cardTidyUpById(formData).then(response => {
        if (response.error_num === 0) {
          // let finalContent=response.finalContent;
          // let cid = response.cardId
          this.isInitial = false
          this.get_all_cards();
          this.cardTidying = false
        }
        else {
          this.isInitial = false
          this.get_all_cards();
          this.cardTidying = false
          alert("error!");
        }
      }).catch(error => {
        this.isInitial = false
        this.get_all_cards();
        this.cardTidying = false
        alert("error!2");
        console.log('error', error.message);
      })
    },

    // 添加滚动到特定卡片的方法
    scrollToCard(cid) {
      // 找到对应的卡片元素
      this.$nextTick(() => {
        // 使用document.querySelector替代this.$el.querySelector
        const cardElement = document.querySelector(`[data-cid="${cid}"]`);
        if (cardElement) {
          // 平滑滚动到卡片位置
          cardElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
          
          // 可选：添加闪烁效果提示用户
          this.flashingCid = cid;
          setTimeout(() => {
            this.flashingCid = null;
          }, 2000);
        }
      });
    },

    // 通过CID打开卡片
    handleOpenCardByCid(cid) {
      // 找到对应的Card组件并触发点击事件
      this.$nextTick(() => {
        const cardRefs = this.$refs.cardRefs;
        if (cardRefs && Array.isArray(cardRefs)) {
          const targetCard = cardRefs.find(card => card.cid === cid);
          if (targetCard) {
            targetCard.onCardClick();
          } else {
            // 如果找不到对应的Card组件，尝试通过DOM查找并点击
            const cardElement = document.querySelector(`[data-cid="${cid}"]`);
            if (cardElement) {
              // 滚动到卡片位置
              cardElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
              // 添加闪烁效果
              this.flashingCid = cid;
              setTimeout(() => {
                this.flashingCid = null;
                // 尝试触发点击事件
                const clickableElement = cardElement.querySelector('.card-top-title, .card-content');
                if (clickableElement) {
                  clickableElement.click();
                }
              }, 500);
            }
          }
        }
      });
    },

    applyTemplate(template) {
      // 将模板内容插入到输入框中以供编辑
      this.userDefineForm.userText = template.text;
    },
    // 选择 topics 用于计算属性过滤
    toggleTopicSelection(topic) {
      // 切换选择状态
      if (this.selectedTopics.includes(topic)) {
        this.selectedTopics = this.selectedTopics.filter(t => t !== topic);
      } else {
        this.selectedTopics.push(topic);
      }
    },
    clearSelectedTopics() {
      this.selectedTopics = [];
    },

    // 🔥 生成永久卡片
    async generatePermanentCard() {
      if (this.generatingPermanentCard) return;
      
      try {
        this.generatingPermanentCard = true;

        // 1. 获取当前关键词网络图中的节点信息（通过ref调用子组件方法）
        const keywordGraph = this.$refs.keywordNetworkGraph;
        if (!keywordGraph || !keywordGraph.nodes) {
          alert('无法获取关键词节点信息，请稍后重试');
          return;
        }

        const nodes = keywordGraph.nodes;
        const keywordFourColorDMTData = this.keywordFourColorDMTPure || {};

        // 2. 选择关键词：频率最高的节点、T级节点、绿色/紫色高价值节点
        const selectedKeywords = new Set();
        
        // 2.1 频率最高的节点（前3个）
        // 计算每个节点的频率（关联的卡片数量）
        const nodeFrequency = {};
        nodes.forEach(node => {
          const keyword = node.label;
          const matchingCards = this.cardList.filter(card => {
            if (!card.keyWords) return false;
            const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
            return cardKeywords.includes(keyword);
          });
          nodeFrequency[keyword] = matchingCards.length;
        });
        
        const sortedByFrequency = [...nodes].sort((a, b) => 
          (nodeFrequency[b.label] || 0) - (nodeFrequency[a.label] || 0)
        );
        sortedByFrequency.slice(0, 3).forEach(node => {
          selectedKeywords.add(node.label);
        });

        // 2.2 T级节点
        nodes.forEach(node => {
          const keywordData = keywordFourColorDMTData[node.label] || {};
          if (keywordData.dmt_level === 'T') {
            selectedKeywords.add(node.label);
          }
        });

        // 2.3 绿色/紫色高价值节点
        nodes.forEach(node => {
          const keywordData = keywordFourColorDMTData[node.label] || {};
          const fourColorType = keywordData.four_color_type || '';
          if (fourColorType === 'G' || fourColorType === 'P') {
            selectedKeywords.add(node.label);
          }
        });

        if (selectedKeywords.size === 0) {
          alert('未找到合适的关键词，请确保关键词网络图中有节点');
          return;
        }

        // 🔥 限制关键词数量不超过10个
        const keywordArray = Array.from(selectedKeywords);
        const finalKeywords = keywordArray.slice(0, 10);

        console.log(`[generatePermanentCard] 筛选到的关键词数量: ${selectedKeywords.size}, 限制后数量: ${finalKeywords.length}, 关键词列表:`, finalKeywords);

        // 3.0 初始化进度
        this.permanentCardProgress = { current: 0, total: finalKeywords.length, keyword: '' };

        // 3. 为每个关键词筛选相关卡片并生成永久卡片
        let successCount = 0;
        let failCount = 0;
        for (let idx = 0; idx < finalKeywords.length; idx++) {
          const keyword = finalKeywords[idx];
          // 更新进度
          this.permanentCardProgress = { current: idx + 1, total: finalKeywords.length, keyword: keyword };
          try {
            // 3.1 找到包含此关键词的卡片
            let keywordCards = this.cardList.filter(card => {
              if (!card.keyWords) return false;
              const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
              return cardKeywords.includes(keyword);
            });

            // 3.2 筛选：有四色DMT属性且绿色/紫色/红蓝深评综合得分≥3.5
            keywordCards = keywordCards.filter(card => {
              // 必须有四色DMT属性
              if (!card.four_color_type && !card.dmt_level) return false;

              // 计算综合得分：score×0.3+scoreSFT×0.7
              const score = card.score || 0;
              const scoreSFT = card.scoreSFT || 0;
              const combinedScore = score * 0.3 + scoreSFT * 0.7;

              // 必须≥3.5
              if (combinedScore < 3.5) return false;

              // 必须是绿色、紫色或红蓝（R或B）
              const fourColorType = card.four_color_type || '';
              return fourColorType === 'G' || fourColorType === 'P' || fourColorType === 'R' || fourColorType === 'B';
            });

            // 3.3 对于QA问答卡，分析问题链（按datetime排序）
            const qaCards = keywordCards.filter(card => {
              // 判断是否为QA卡：有history字段或content中包含"提问"
              return card.history || (card.content && card.content.includes('提问'));
            });

            // 按datetime排序QA卡
            qaCards.sort((a, b) => {
              const dateA = new Date(a.datetime || 0);
              const dateB = new Date(b.datetime || 0);
              return dateA - dateB; // 升序：最早的在前
            });

            // 3.4 综合排序：先按综合得分排序，最多取前5张
            keywordCards.sort((a, b) => {
              const scoreA = (a.score || 0) * 0.3 + (a.scoreSFT || 0) * 0.7;
              const scoreB = (b.score || 0) * 0.3 + (b.scoreSFT || 0) * 0.7;
              return scoreB - scoreA; // 降序：得分高的在前
            });

            let selectedCards = keywordCards.slice(0, 5);

            // 🔥 备用策略：如果筛选后没有符合条件的卡片，从包含该关键词的所有卡片中选择综合得分最高的一张
            if (selectedCards.length === 0) {
              console.log(`[generatePermanentCard] 关键词"${keyword}"未找到符合条件的卡片，使用备用策略`);
              // 重新获取包含该关键词的所有卡片
              const allKeywordCards = this.cardList.filter(card => {
                if (!card.keyWords) return false;
                const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
                return cardKeywords.includes(keyword);
              });
              
              if (allKeywordCards.length > 0) {
                // 按综合得分排序（即使不满足严格条件，也选得分最高的）
                allKeywordCards.sort((a, b) => {
                  const scoreA = (a.score || 0) * 0.3 + (a.scoreSFT || 0) * 0.7;
                  const scoreB = (b.score || 0) * 0.3 + (b.scoreSFT || 0) * 0.7;
                  return scoreB - scoreA; // 降序：得分高的在前
                });
                // 至少选一张
                selectedCards = [allKeywordCards[0]];
                console.log(`[generatePermanentCard] 备用策略：选择综合得分最高的卡片 (得分: ${(selectedCards[0].score || 0) * 0.3 + (selectedCards[0].scoreSFT || 0) * 0.7})`);
              } else {
                console.log(`[generatePermanentCard] 关键词"${keyword}"未找到任何相关卡片，跳过`);
                continue;
              }
            }

            const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
            const isGroupNotebook = currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
            const originRealName = localStorage.getItem('originRealName') || '';

            // 4. 调用后端API生成永久卡片
            const { API_BASE_URL } = require('@/config/apiConfig');
            const response = await fetch(`${API_BASE_URL}/api/generate_permanent_card`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                keyword: keyword,
                cards: selectedCards,
                qa_cards: qaCards,
                username: localStorage.getItem('userId'),
                scene_name: this.sceneName,
                sub_scene_name: this.subSceneName,
                is_group_notebook: isGroupNotebook,
                origin_real_name: originRealName
              })
            });

            if (!response.ok) {
              throw new Error(`HTTP错误: ${response.status}`);
            }

            const data = await response.json();
            if (data.error_num !== 0) {
              throw new Error(data.msg || '生成失败');
            }

            console.log(`[generatePermanentCard] 关键词"${keyword}"的永久卡片生成成功`);
            successCount++;
          } catch (error) {
            console.error(`[generatePermanentCard] 关键词"${keyword}"生成失败:`, error);
            failCount++;
            // 🔥 继续处理下一个关键词，不中断整个流程
          }
        }

        // 5. 刷新卡片列表
        await this.get_all_cards();

        // 6. 重置进度并显示完成消息
        this.permanentCardProgress = { current: 0, total: 0, keyword: '' };
        if (failCount === 0) {
          this.$message.success(`关键词神经元永久卡生成完成！成功生成 ${successCount} 张卡片`);
        } else {
          this.$message.warning(`关键词神经元永久卡生成完成！成功 ${successCount} 张，失败 ${failCount} 张`);
        }
      } catch (error) {
        console.error('[generatePermanentCard] 生成关键词神经元永久卡片失败:', error);
        this.permanentCardProgress = { current: 0, total: 0, keyword: '' };
        this.$message.error('生成关键词神经元永久卡片未完全成功：' + error.message);
      } finally {
        this.generatingPermanentCard = false;
      }
    },

    // 处理筛选策略变化
    handleFilterStrategyChange(strategy) {
      this.keywordFilterStrategy = strategy;
    },

    // 🔥 分析认知状态
    async analyzeCognitiveState() {
      if (this.analyzingCognitiveState) return;
      
      try {
        this.analyzingCognitiveState = true;

        // 1. 判断是个人本子还是群组本子
        const currentNotebook = JSON.parse(localStorage.getItem('currentNotebook') || '{}');
        const isGroupNotebook = currentNotebook.syncUsers && currentNotebook.syncUsers !== '';
        const originRealName = localStorage.getItem('originRealName') || '';

        // 2. 如果是群组本子，在作者筛选框自动填上当前使用者的originRealName
        // if (isGroupNotebook && originRealName) {
        //   this.authorFilter = originRealName;
        //   // 等待筛选生效，让关键词网络图重新渲染
        //   await this.$nextTick();
        //   await new Promise(resolve => setTimeout(resolve, 1000)); // 增加等待时间，确保网络图重新渲染
        // }

        // 3. 获取关键词网络图的SVG并转换为图片
        const keywordGraph = this.$refs.keywordNetworkGraph;
        if (!keywordGraph) {
          alert('无法获取关键词网络图，请稍后重试');
          return;
        }

        let networkImageBase64 = '';
        try {
          const svgElement = keywordGraph.$refs.networkSvg;
          if (svgElement) {
            // 获取SVG的viewBox或宽高
            const viewBox = svgElement.getAttribute('viewBox');
            let svgWidth = 800;
            let svgHeight = 600;
            
            if (viewBox) {
              const parts = viewBox.split(' ');
              if (parts.length >= 4) {
                svgWidth = parseFloat(parts[2]) || 800;
                svgHeight = parseFloat(parts[3]) || 600;
              }
            } else {
              svgWidth = parseFloat(svgElement.getAttribute('width')) || 800;
              svgHeight = parseFloat(svgElement.getAttribute('height')) || 600;
            }
            
            // 将SVG转换为base64图片
            const svgData = new XMLSerializer().serializeToString(svgElement);
            // 确保SVG有正确的宽高属性
            const svgWithSize = svgData.replace(
              /<svg/,
              `<svg width="${svgWidth}" height="${svgHeight}"`
            );
            const svgBlob = new Blob([svgWithSize], { type: 'image/svg+xml;charset=utf-8' });
            const url = URL.createObjectURL(svgBlob);
            
            // 使用canvas转换为base64
            const img = new Image();
            await new Promise((resolve, reject) => {
              img.onload = () => {
                const canvas = document.createElement('canvas');
                canvas.width = svgWidth;
                canvas.height = svgHeight;
                const ctx = canvas.getContext('2d');
                ctx.drawImage(img, 0, 0);
                networkImageBase64 = canvas.toDataURL('image/png');
                URL.revokeObjectURL(url);
                resolve();
              };
              img.onerror = (e) => {
                console.error('[analyzeCognitiveState] 图片加载失败:', e);
                URL.revokeObjectURL(url);
                reject(e);
              };
              img.src = url;
            });
          }
        } catch (e) {
          console.error('[analyzeCognitiveState] 截图失败:', e);
          // 如果截图失败，继续执行，只是没有图片
        }

        // 🔥 调试：检查图片是否成功获取
        if (networkImageBase64) {
          console.log(`[analyzeCognitiveState] 成功获取关键词网络图，Base64长度: ${networkImageBase64.length}`);
        } else {
          console.warn('[analyzeCognitiveState] 警告：未能获取关键词网络图，将只发送文本数据');
        }

        // 4. 收集数据来源信息（文本）
        const keywordGraphData = keywordGraph.nodes || [];
        const keywordFourColorDMTData = this.keywordFourColorDMTPure || {};
        
        // // 获取当前使用者的卡片（如果是群组本子，只获取当前使用者的卡片）
        // 🔥 组本时分析所有writer的卡片，不进行作者筛选
        let userCards = this.cardList;
        // if (isGroupNotebook && originRealName) {
        //   userCards = userCards.filter(card => {
        //     const cardWriter = (card.writer || '').split('_')[0];
        //     return cardWriter === originRealName;
        //   });
        // }

        // 提取QA问答卡的问题链（按datetime排序）
        const qaQuestionsChain = [];
        userCards.forEach(card => {
          if (card.history || (card.content && card.content.includes('提问'))) {
            // 提取问题
            let question = '';
            if (card.history && Array.isArray(card.history) && card.history.length > 0) {
              const firstMsg = card.history[0];
              if (firstMsg && typeof firstMsg === 'object' && firstMsg.content) {
                question = firstMsg.content;
              }
            } else if (card.content) {
              const match = card.content.match(/提问[：:]\s*([^\n\r]+)/);
              if (match) {
                question = match[1].trim();
              }
            }
            
            if (question) {
              qaQuestionsChain.push({
                datetime: card.datetime || '',
                question: question,
                sub_scene: card.contentTitle ? (card.contentTitle.match(/^(S\d+)/) ? card.contentTitle.match(/^(S\d+)/)[1] : '') : '',
                writer: card.writer || ''  // 🔥 添加作者信息（组本需要）
              });
            }
          }
        });

        // 按datetime排序
        qaQuestionsChain.sort((a, b) => {
          const dateA = new Date(a.datetime || 0);
          const dateB = new Date(b.datetime || 0);
          return dateA - dateB;
        });

        // 计算每个关键词的频率（关联的卡片数量）
        const keywordFrequency = {};
        keywordGraphData.forEach(node => {
          const keyword = node.label;
          const matchingCards = userCards.filter(card => {
            if (!card.keyWords) return false;
            const cardKeywords = card.keyWords.split(/[,，]/).map(k => k.trim());
            return cardKeywords.includes(keyword);
          });
          keywordFrequency[keyword] = matchingCards.length;
        });

        // 构建数据来源信息文本
        const dataSourceInfo = {
          keywords: keywordGraphData.map(node => ({
            label: node.label,
            frequency: keywordFrequency[node.label] || 0,
            four_color_type: keywordFourColorDMTData[node.label]?.four_color_type || '',
            dmt_level: keywordFourColorDMTData[node.label]?.dmt_level || '',
            knowledge_type: keywordFourColorDMTData[node.label]?.knowledge_type || ''
          })),
          cards_count: userCards.length,
          qa_questions_chain: qaQuestionsChain,
          notebook_name: currentNotebook.bookName || currentNotebook.bookdescription || '',
          scene_name: this.sceneName,
          sub_scene_name: this.subSceneName
        };

        // 5. 调用后端API
        const { API_BASE_URL } = require('@/config/apiConfig');
        const response = await fetch(`${API_BASE_URL}/api/analyze_cognitive_state`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            network_image: networkImageBase64,
            data_source_info: dataSourceInfo,
            username: localStorage.getItem('userId'),
            scene_name: this.sceneName,
            sub_scene_name: this.subSceneName,
            is_group_notebook: isGroupNotebook,
            origin_real_name: originRealName
          })
        });

        if (!response.ok) {
          throw new Error(`HTTP错误: ${response.status}`);
        }

        const data = await response.json();
        if (data.error_num !== 0) {
          throw new Error(data.msg || '分析失败');
        }

        // 6. 刷新卡片列表
        await this.get_all_cards();

        this.$message.success('关键词节点图主体性认知状态分析完成！已生成分析卡片。');
      } catch (error) {
        console.error('[analyzeCognitiveState] 分析认知状态失败:', error);
        this.$message.error('关键词节点图主体性认知状态分析失败：' + error.message);
      } finally {
        this.analyzingCognitiveState = false;
      }
    },

    semanticReorganizeLabel(mode) {
      if (!this.semanticReorganizing) {
        return mode === 'incremental' ? '迭代梳理语义' : '重新梳理语义';
      }
      const st = this.semanticReorganizeStatus || {};
      if (st.phase === 'attributes') {
        return `属性分析中… (${st.attr_batch_end || 0}/${st.total_keywords || '?'})`;
      }
      if (st.phase === 'extract') {
        const title = st.current_title ? ` - ${st.current_title}` : '';
        return `梳理中 ${st.current_index || 0}/${st.total_cards || '?'}${title}`;
      }
      return mode === 'incremental' ? '迭代梳理中…' : '重新梳理中…';
    },

    async startSemanticReorganize(mode) {
      if (this.semanticReorganizing) return;
      const username = localStorage.getItem('userId');
      if (!username) {
        this.$message.warning('未获取到本子信息');
        return;
      }
      const isIncremental = mode === 'incremental';
      const confirmMsg = isIncremental
        ? '将保留已有语义备选池，仅从未纳入梳理的卡片中抽样（浅卡最多40、另抽白卡最多20，合计最多60），并发抽词+浓缩后做核心问题/合并同类项、层次补词、连边与属性分析。是否继续？'
        : '将对本子卡片抽样（浅卡≤40全取或最近10+随机30；另从其余白卡最多抽20；合计最多60），并发抽词+浓缩后做核心问题/合并同类项、层次补词、连边与属性分析。是否继续？';
      try {
        await this.$confirm(confirmMsg, '语义梳理', { type: 'warning' });
      } catch (e) {
        return;
      }
      try {
        this.semanticReorganizeFloatingDismissed = false;
        this.semanticReorganizeResultVisible = false;
        this.clearSemanticReorganizeFloatingAutoHide();
        this.semanticReorganizing = true;
        const res = await semantic_reorganize_start({
          username,
          scene_name: this.sceneName || '',
          mode: isIncremental ? 'incremental' : 'full',
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '发起语义梳理失败');
          this.semanticReorganizing = false;
          return;
        }
        this.$message.success(isIncremental ? '已开始迭代梳理语义' : '已开始重新梳理语义');
        this.semanticReorganizeStatus = (data.status || { running: true, phase: 'preparing' });
        this.pollSemanticReorganizeStatus(username);
      } catch (e) {
        this.semanticReorganizing = false;
        this.$message.error('语义梳理请求失败：' + (e.message || e));
      }
    },

    pollSemanticReorganizeStatus(username) {
      if (this.semanticReorganizePollTimer) clearTimeout(this.semanticReorganizePollTimer);
      const poll = async () => {
        try {
          const res = await semantic_reorganize_status({
            username,
            scene_name: this.sceneName || '',
          });
          const data = res.data || res;
          const st = data.status || {};
          this.semanticReorganizeStatus = st;
          this.semanticReorganizeCanRollback = !!st.rollback_available;

          const activePhases = [
            'preparing',
            'extract',
            'extract_condense',
            'key_issues_merge',
            'enrich',
            'connect',
            'attributes',
          ];
          if (st.running || activePhases.includes(st.phase)) {
            this.semanticReorganizing = true;
            this.semanticReorganizePollTimer = setTimeout(poll, 2000);
            return;
          }

          this.semanticReorganizing = false;
          this.semanticReorganizePollTimer = null;

          if (st.phase === 'error') {
            this.$message.error('语义梳理失败：' + (st.error || '未知错误'));
            this.scheduleSemanticReorganizeFloatingAutoHide(5000);
            return;
          }
          if (st.phase === 'completed') {
            const skipped = st.skipped_cards || 0;
            const extra = skipped > 0 ? `（本次处理 ${st.selected_cards || st.cards_processed || 0} 张，跳过 ${skipped} 张）` : '';
            this.$message.success(`语义梳理完成，共 ${st.total_keywords || 0} 个关键词${extra}`);
            await this.get_all_cards();
            this.scheduleSemanticReorganizeFloatingAutoHide(3000);
          }
        } catch (e) {
          if (this.semanticReorganizing) {
            this.semanticReorganizePollTimer = setTimeout(poll, 3000);
          }
        }
      };
      poll();
    },

    dismissSemanticReorganizeFloating() {
      this.semanticReorganizeFloatingDismissed = true;
      this.semanticReorganizeResultVisible = false;
      this.clearSemanticReorganizeFloatingAutoHide();
    },

    clearSemanticReorganizeFloatingAutoHide() {
      if (this.semanticReorganizeFloatingAutoHideTimer) {
        clearTimeout(this.semanticReorganizeFloatingAutoHideTimer);
        this.semanticReorganizeFloatingAutoHideTimer = null;
      }
    },

    scheduleSemanticReorganizeFloatingAutoHide(delayMs) {
      this.clearSemanticReorganizeFloatingAutoHide();
      this.semanticReorganizeResultVisible = true;
      this.semanticReorganizeFloatingDismissed = false;
      this.semanticReorganizeFloatingAutoHideTimer = setTimeout(() => {
        this.semanticReorganizeFloatingDismissed = true;
        this.semanticReorganizeResultVisible = false;
        this.semanticReorganizeFloatingAutoHideTimer = null;
      }, delayMs);
    },

    async refreshSemanticReorganizeStatus() {
      const username = localStorage.getItem('userId');
      if (!username) return;
      try {
        const res = await semantic_reorganize_status({
          username,
          scene_name: this.sceneName || '',
        });
        const data = res.data || res;
        const st = data.status || {};
        this.semanticReorganizeStatus = st;
        this.semanticReorganizeCanRollback = !!st.rollback_available;
        if (st.running || [
          'preparing',
          'extract',
          'extract_condense',
          'key_issues_merge',
          'enrich',
          'connect',
          'attributes',
        ].includes(st.phase)) {
          this.semanticReorganizing = true;
          this.semanticReorganizeFloatingDismissed = false;
          this.semanticReorganizeResultVisible = false;
          this.pollSemanticReorganizeStatus(username);
        } else {
          this.semanticReorganizing = false;
          this.semanticReorganizeFloatingDismissed = true;
          this.semanticReorganizeResultVisible = false;
        }
      } catch (e) {
        // 静默忽略
      }
    },

    async rollbackSemanticReorganize() {
      if (this.semanticReorganizing || this.semanticReorganizeRollingBack) return;
      const username = localStorage.getItem('userId');
      if (!username) {
        this.$message.warning('未获取到本子信息');
        return;
      }
      try {
        await this.$confirm(
          '将恢复本次「重新/迭代梳理语义」开始前的全部卡片关键词、语义备选池与梳理进度记录。是否继续？',
          '撤销本次梳理',
          { type: 'warning' }
        );
      } catch (e) {
        return;
      }
      try {
        this.semanticReorganizeRollingBack = true;
        const res = await semantic_reorganize_rollback({
          username,
          scene_name: this.sceneName || '',
        });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '回退失败');
          return;
        }
        this.$message.success(data.msg || '已回退到梳理前状态');
        this.semanticReorganizeCanRollback = false;
        this.semanticReorganizeStatus = data.status || { running: false, phase: 'idle' };
        await this.get_all_cards();
      } catch (e) {
        this.$message.error('回退请求失败：' + (e.message || e));
      } finally {
        this.semanticReorganizeRollingBack = false;
      }
    },

    // 四色卡片生图（单卡仍可用；批量按钮已移除）
    async startFourColorCardImages() {
      if (this.cardImageGeneratingCids.length > 0) return;
      const username = localStorage.getItem('userId');
      if (!username) {
        this.$message.warning('未获取到本子信息');
        return;
      }
      try {
        const res = await card_generate_four_color_images({ username });
        const data = res.data || res;
        if (data.error_num !== 0) {
          this.$message.error(data.msg || '发起生图失败');
          return;
        }
        this.cardImageGeneratingCids = data.generating_cids || [];
        if (data.queued > 0) {
          this.$message.success(`已加入队列 ${data.queued} 张卡片，正在后台生图`);
        } else {
          this.$message.info('当前没有需要生图的四色卡片（可能已有图）');
          return;
        }
        const poll = () => {
          card_get_image_generating_status({ username }).then(r => {
            const d = r.data || r;
            if (d.error_num === 0) {
              const nextCids = d.generating_cids || [];
              const prevSet = new Set(this.cardImageGeneratingCids);
              const nextSet = new Set(nextCids);
              const finished = [...prevSet].filter(c => !nextSet.has(c));
              this.cardImageGeneratingCids = nextCids;
              if (finished.length) this.cardHasImageCids = [...new Set([...this.cardHasImageCids, ...finished])];
            }
            if (this.cardImageGeneratingCids.length > 0) this.cardImagePollTimer = setTimeout(poll, 2000);
            else this.cardImagePollTimer = null;
          }).catch(() => {
            if (this.cardImageGeneratingCids.length > 0) this.cardImagePollTimer = setTimeout(poll, 2000);
          });
        };
        this.cardImagePollTimer = setTimeout(poll, 2000);
      } catch (e) {
        this.$message.error('四色卡片生图请求失败：' + (e.message || e));
      }
    },

    onCardHasImage(cid) {
      if (!this.cardHasImageCids.includes(cid)) this.cardHasImageCids = [...this.cardHasImageCids, cid];
    },

    _normCardCid(cid) {
      const n = Number(cid);
      return Number.isFinite(n) ? n : null;
    },
    // 单张卡片点击「卡片生图」后，将 cid 加入生图列表并启动轮询
    onSingleCardImageRequested(cid) {
      const id = this._normCardCid(cid);
      if (id == null) return;
      if (!this._imageGenSeenServer) this._imageGenSeenServer = new Set();
      this._imageGenSeenServer.delete(id);
      // 统一成 number，避免与后端 generating_cids(int) / Card.cid 比较失败
      this.cardImageGeneratingCids = [
        ...new Set([
          ...this.cardImageGeneratingCids.map((c) => this._normCardCid(c)).filter((c) => c != null),
          id,
        ]),
      ];
      // 迭代重出图时可能已有图：先摘掉「已有图」标记，左上角改回生成中
      this.cardHasImageCids = this.cardHasImageCids
        .map((c) => this._normCardCid(c))
        .filter((c) => c != null && c !== id);
      const username = localStorage.getItem('userId');
      if (!username) return;
      let emptyPolls = 0;
      const poll = () => {
        card_get_image_generating_status({ username }).then(r => {
          const d = r.data || r;
          if (d.error_num === 0) {
            const nextCids = (d.generating_cids || [])
              .map((c) => this._normCardCid(c))
              .filter((c) => c != null);
            const prevSet = new Set(this.cardImageGeneratingCids);
            const nextSet = new Set(nextCids);
            nextCids.forEach((c) => this._imageGenSeenServer.add(c));
            if (nextCids.length) emptyPolls = 0;
            else emptyPolls += 1;
            // 服务端队列 ∪ 尚未在服务端出现过的本地乐观 cid（避免登记前被冲掉）
            let optimistic = [...prevSet].filter((c) => !nextSet.has(c) && !this._imageGenSeenServer.has(c));
            // 连续空队列仍只有乐观项：放弃，避免左上角永久转圈
            if (!nextCids.length && emptyPolls >= 4) optimistic = [];
            const finished = [...prevSet].filter((c) => !nextSet.has(c) && this._imageGenSeenServer.has(c));
            this.cardImageGeneratingCids = [...new Set([...nextCids, ...optimistic])];
            if (finished.length) {
              this.cardHasImageCids = [...new Set([
                ...this.cardHasImageCids.map((c) => this._normCardCid(c)).filter((c) => c != null),
                ...finished,
              ])];
            }
          }
          if (this.cardImageGeneratingCids.length > 0) this.cardImagePollTimer = setTimeout(poll, 2000);
          else this.cardImagePollTimer = null;
        }).catch(() => {
          if (this.cardImageGeneratingCids.length > 0) this.cardImagePollTimer = setTimeout(poll, 2000);
        });
      };
      if (this.cardImagePollTimer) {
        clearTimeout(this.cardImagePollTimer);
        this.cardImagePollTimer = null;
      }
      this.cardImagePollTimer = setTimeout(poll, 800);
    },

    onSingleCardHtmlRequested(cid) {
      const id = this._normCardCid(cid);
      if (id == null) return;
      if (!this._htmlGenSeenServer) this._htmlGenSeenServer = new Set();
      this._htmlGenSeenServer.delete(id);
      this.cardHtmlGeneratingCids = [
        ...new Set([
          ...this.cardHtmlGeneratingCids.map((c) => this._normCardCid(c)).filter((c) => c != null),
          id,
        ]),
      ];
      const username = localStorage.getItem('userId');
      if (!username) return;
      let emptyPolls = 0;
      const poll = () => {
        card_get_html_generating_status({ username }).then(r => {
          const d = r.data || r;
          if (d.error_num === 0) {
            const nextCids = (d.generating_cids || [])
              .map((c) => this._normCardCid(c))
              .filter((c) => c != null);
            const prevSet = new Set(this.cardHtmlGeneratingCids);
            const nextSet = new Set(nextCids);
            nextCids.forEach((c) => this._htmlGenSeenServer.add(c));
            if (nextCids.length) emptyPolls = 0;
            else emptyPolls += 1;
            let optimistic = [...prevSet].filter((c) => !nextSet.has(c) && !this._htmlGenSeenServer.has(c));
            if (!nextCids.length && emptyPolls >= 4) optimistic = [];
            this.cardHtmlGeneratingCids = [...new Set([...nextCids, ...optimistic])];
          }
          if (this.cardHtmlGeneratingCids.length > 0) this.cardHtmlPollTimer = setTimeout(poll, 2000);
          else this.cardHtmlPollTimer = null;
        }).catch(() => {
          if (this.cardHtmlGeneratingCids.length > 0) this.cardHtmlPollTimer = setTimeout(poll, 2000);
        });
      };
      if (this.cardHtmlPollTimer) {
        clearTimeout(this.cardHtmlPollTimer);
        this.cardHtmlPollTimer = null;
      }
      this.cardHtmlPollTimer = setTimeout(poll, 800);
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
    },

    // 🔥 更新子组件关键词四色DMT数据
    updateKeywordNetworkGraphData() {
      if (!this.keywordFourColorDMT || Object.keys(this.keywordFourColorDMT).length === 0) {
        return;
      }
      
      const updateSubComponent = () => {
        if (this.$refs.keywordNetworkGraph && typeof this.$refs.keywordNetworkGraph.updateKeywordFourColorDMT === 'function') {
          const pureData = JSON.parse(JSON.stringify(this.keywordFourColorDMT));
          console.log("[CardGrid] ✅ 调用子组件 updateKeywordFourColorDMT，数据键数量:", Object.keys(pureData).length);
          this.$refs.keywordNetworkGraph.updateKeywordFourColorDMT(pureData);
          return true;
        }
        return false;
      };
      
      // 尝试多次调用
      this.$nextTick(() => {
        this.$nextTick(() => {
          if (!updateSubComponent()) {
            console.log("[CardGrid] ⚠️ 第一次尝试失败，延迟500ms再试");
            setTimeout(() => {
              if (!updateSubComponent()) {
                console.log("[CardGrid] ⚠️ 第二次尝试失败，延迟1000ms再试");
                setTimeout(() => {
                  if (!updateSubComponent()) {
                    console.log("[CardGrid] ❌ 多次尝试失败，子组件可能未挂载");
                  }
                }, 1000);
              }
            }, 500);
          }
        });
      });
    },

    showMenu() {
      this.menuVisible = true;
    },
    hideMenu() {
      this.menuVisible = false;
      this.$emit("menuVisNo")
    },
    // 🔥 处理tags-container的mouseleave事件，防止在弹框显示时关闭菜单
    handleTagsContainerMouseLeave(event) {
      // 检查是否有弹框正在显示（融合对话框、四色对话框、DMT对话框）
      const hasFusionDialog = document.querySelector('.color-dmt-dialog-overlay') && 
                             document.querySelector('.fusion-dialog');
      const hasColorDialog = document.querySelector('.color-dmt-dialog-overlay') && 
                            !document.querySelector('.fusion-dialog');
      
      // 如果有弹框显示，不关闭菜单
      if (hasFusionDialog || hasColorDialog) {
        return;
      }
      
      // 检查鼠标是否真的移出了tags-container（而不是移到了弹框上）
      const relatedTarget = event.relatedTarget;
      if (relatedTarget && (
          relatedTarget.closest('.color-dmt-dialog') ||
          relatedTarget.closest('.color-dmt-dialog-overlay') ||
          relatedTarget.closest('.fusion-dialog')
        )) {
        return;
      }
      
      // 正常关闭菜单
      this.hideMenu();
    },

    // 🔥 切换卡片层级模式（白卡层/DMT四色化卡片层）
    toggleCardLayer() {
      // 🔥 保存当前勾选状态，避免切换时丢失
      const savedChoosedCardIdList = [...this.choosedCardIdList];
      this.cardLayerMode = this.cardLayerMode === "white" ? "high_value" : "white";
      // 🔥 恢复勾选状态并更新所有Card组件的checked状态
      this.$nextTick(() => {
        this.choosedCardIdList = savedChoosedCardIdList;
        this.$emit('chooseCardChange', [...this.choosedCardIdList]);
        // 🔥 触发updateCheckbox来更新所有Card组件的checked状态
        this.updateCheckbox = true;
        setTimeout(() => {
          this.updateCheckbox = false;
        }, 50);
      });
    },

    // 🔥 滚动到第一张白卡位置
    scrollToFirstCard() {
      this.$nextTick(() => {
        // 先尝试找到等待卡片（多卡生成）
        const waitingCard = document.querySelector('.notebook-card-waiting');
        if (waitingCard) {
          waitingCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
          return;
        }
        // 如果没有等待卡片，找到第一张实际卡片
        if (this.filteredCards && this.filteredCards.length > 0) {
          const firstCardCid = this.filteredCards[0].cid;
          this.scrollToCard(firstCardCid);
        }
      });
    },

    // 🔥 滚动到CardGrid顶部（用于问答钉卡时）
    scrollToTop() {
      // 🔥 滚动到CardGrid顶部 - 使用和scrollToCard相同的scrollIntoView方法
      this.$nextTick(() => {
        const indexCard = document.querySelector('.notebook-card-index');
        if (indexCard) {
          indexCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } else {
          // 如果没有索引卡，滚动到grid-container顶部
          const gridContainer = document.querySelector('.grid-container');
          if (gridContainer) {
            gridContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
          }
        }
      });
    },
    
    // 🔥 滚动到白底色卡区域的最上方（非高价值卡的第一个位置）
    scrollToFirstWhiteCard() {
      this.$nextTick(() => {
        // 找到第一个非高价值卡片
        if (this.filteredCards && this.filteredCards.length > 0) {
          // 在白卡层模式下，找到第一个非高价值卡片
          if (this.cardLayerMode === "white") {
            const firstWhiteCard = this.filteredCards.find(card => !this.hasFourColorOrDmt(card));
            if (firstWhiteCard) {
              this.scrollToCard(firstWhiteCard.cid);
              return;
            }
          }
          // 如果没找到非高价值卡片，或者在高价值层模式下，滚动到第一张卡片
          const firstCardCid = this.filteredCards[0].cid;
          this.scrollToCard(firstCardCid);
        }
      });
    },

    // 🔥 设置最后创建的卡片ID，用于等待卡消失后滚动到新卡片
    setLastCreatedCardId(cid) {
      this.lastCreatedCardId = cid;
    },

    // 🔥 滚动到新生成的卡片或第一张白卡
    scrollToNewCardOrFirstWhite() {
      // 如果有新生成的卡片ID，先尝试滚动到新卡片
      if (this.lastCreatedCardId) {
        // 检查卡片是否在列表中
        const newCard = this.filteredCards.find(card => card.cid === this.lastCreatedCardId);
        if (newCard) {
          // 检查新卡片是否是四色DMT化卡片
          if (this.hasFourColorOrDmt(newCard)) {
            // 如果是高价值卡片，滚动到这张卡片并闪烁
            this.scrollToCard(this.lastCreatedCardId);
            const savedCardId = this.lastCreatedCardId;
            this.lastCreatedCardId = null; // 清除
            return;
          }
        }
        // 如果不是高价值卡片或找不到卡片，继续滚动到第一张白卡
        this.lastCreatedCardId = null;
      }
      // 默认滚动到第一张白卡
      this.scrollToFirstWhiteCard();
    },

    // 🔥 判断卡片是否有四色/DMT标识（用于判断是否为四色DMT化卡片）
    hasFourColorOrDmt(card) {
      if (!card) return false;
      const hasFourColor = card.four_color_type && card.four_color_type.trim() !== '';
      const hasDmt = card.dmt_level && card.dmt_level.trim() !== '';
      return hasFourColor || hasDmt;
    },

    // 🔥 判断卡片是否与当前勾选的卡片相关（postIndex中包含selectedCardId）
    isCardRelatedToSelected(card) {
      if (!this.selectedCardId) return false;
      
      try {
        const postIndex = card.postIndex;
        if (!postIndex) return false;
        
        const postIndexList = typeof postIndex === 'string' ? JSON.parse(postIndex) : postIndex;
        if (Array.isArray(postIndexList)) {
          return postIndexList.includes(this.selectedCardId);
        }
      } catch (e) {
        console.error('解析postIndex失败:', e);
      }
      
      return false;
    },

    cardTextNum() {
      this.showBlankCard = true
    },
    cardTextNumOver() {
      this.isInitial = false
      this.get_all_cards();
      this.showBlankCard = false  // 🔥 等待卡片消失
    },
    cardClickLog(content, score, reason, keyWords, contentTitle, cid) {
      this.openCardId = cid
      this.$emit('cardClickLog', content, score, reason, keyWords, contentTitle)
    },
    handleMultiHint(numbers, groupIndex) {
      // 找到所有匹配的卡片索引
      // const flashingIndexes = numbers.reduce((indexes, number) => {
      //   const card = this.cardList.find(card => card.cid === number);
      //   if (card) {
      //     const index = this.cardList.indexOf(card);
      //     if (index !== -1) { // 确保索引有效
      //       indexes.push(index);
      //     }
      //   }
      //   return indexes;
      // }, []);

      // if (flashingIndexes.length > 0) {
      //   this.flashingIndexes = flashingIndexes;
      //   console.log("要闪烁的卡片indexes: ", this.flashingIndexes);
      //   setTimeout(() => {
      //     // 停止所有卡片的闪烁
      //     this.flashingIndexes = [];
      //   }, 2000); 
      // } else {
      //   console.log("没有找到匹配的卡片");
      // }
      const flashingCids = numbers.reduce((cids, number) => {
        const card = this.cardList.find(card => card.cid === number);
        if (card) {
          const cid = card.cid;
          if (cid !== -1) { // 确保索引有效
            cids.push(cid);
          }
        }
        return cids;
      }, []);

      if (flashingCids.length > 0) {
        this.flashingCids = flashingCids;
        setTimeout(() => {
          // 停止所有卡片的闪烁
          this.flashingCids = [];
        }, 2000); 
      } else {
        console.log("没有找到匹配的卡片");
      }
    },
    handleHint(number, groupIndex) {
      const card = this.cardList.find(card => card.cid === parseInt(number, 10));
      if (card) {
        // this.flashingIndex = this.cardList.indexOf(card);
        // console.log("要闪烁的卡片index: ", this.flashingIndex);
        // setTimeout(() => {
        //   this.flashingIndex = -1; // 停止闪烁
        // }, 2000); // 2秒后停止闪烁
        this.flashingCid = card.cid;
        setTimeout(() => {
          this.flashingCid = -1; // 停止闪烁
        }, 2000); // 2秒后停止闪烁
      }
    },
    handelUpdateHistory(history, title) {
      this.$emit('update-history', history, title);
    },
    handleCheck(timeParams, timeModel) {
      this.showCardParams = true;
      this.timeParams = timeParams;
      this.timeModel = timeModel;
    },
    hideDialog() {
      this.showCardParams = false;
    },
    cardUserDefine() {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      this.showDialog = true;
      // this.mergeCard();
    },
    createRelCard(text) {
      this.choosedFunc = 10;
      this.choosedText = text;
      this.showDialog = false;
      this.mergeCard();
    },

    singleCardReact() {
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      this.$message.success('开始对本卡片的react加强, 请耐心等待一会!');
      let formData = new FormData();
      formData.append('cardIndexList', this.choosedCardIdList);
      react(formData).then(data => {
        if(data['error_num'] === 0) {
          this.isInitial = false
          this.get_all_cards();
          this.$message.success('卡片内容及红蓝评分更新完成');
        } else {
          this.$message.error('出错了，请退出重登再试，若再次出错，请联系管理员并暂勿使用此功能');
        }
      })
    },
    singleCardUnderstand() {
      // Help me understand the selected note
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      this.choosedFunc = 4;
      this.mergeCard();
    },
    singleCardCrtique() {
      // Critique the selected note
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      this.choosedFunc = 5;
      this.mergeCard();
    },
    singleCardCreateOutline() {
      // Create an outline for the selected note
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      this.choosedFunc = 6;
      this.mergeCard();
    },
    cardSummarize() {
      // Summarize the selected notes
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      // 半自动化新增：记录卡片操作
      this.$emit('record-operation', {
        type: 'card_operation',
        data: {
          operationType: 'summarize',
          cardIdList: this.choosedCardIdList,
          sceneName: this.sceneName,
          subSceneName: this.subSceneName,
          keyTopics: this.keyTopics
        }
      });

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 0;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },
    cardSuggestIdeas() {
      // Suggest ideas from my sources related to the selected notes
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 1;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },

    cardStudyGuide() {
      // Create a study guide for the selected notes
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 2;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },
    cardCombine() {
      // Combine the selected notes into a single note
      // if(localStorage.getItem('originRealName') !== localStorage.getItem('realName')) {
      //   this.$message.error('您不是作者，暂时没有权限执行此操作');
      //   return
      // }
      if(!this.hasCardOperationPermission()) {
        this.$message.error('您没有权限执行此操作');
        return
      }

      // 半自动化新增：记录卡片操作
      this.$emit('record-operation', {
        type: 'card_operation',
        data: {
          operationType: 'combine',
          cardIdList: this.choosedCardIdList,
          sceneName: this.sceneName,
          subSceneName: this.subSceneName,
          keyTopics: this.keyTopics
        }
      });

      if (this.choosedCardIdList.length >= 1) {
        this.choosedFunc = 3;
        this.mergeCard();
      }
      else alert("请选择卡片");
    },
    updateC() {

      // this.$router.go(0);
      // this.$message.success('保存成功！');
    },
    mergeCard() {
      let formData = new FormData();
      formData.append('cardIndexList', this.choosedCardIdList);
      formData.append('username', localStorage.getItem('userId'));
      let originRealName = localStorage.getItem('originRealName') || '';
      formData.append('originRealName', originRealName)
      formData.append('datetime', getDateTime());
      //model_id 栏改为参与融合的卡片的数量
      //status 栏改为参与迭代的次数
      formData.append('model_id', 1003);//1003表示是迭代得到的卡片
      formData.append('status', 2);//status=2表示卡片由迭代得到
      formData.append('func', this.choosedFunc);
      formData.append('sceneName', this.sceneName);
      formData.append('subSceneName', this.subSceneName);
      formData.append('keyTopics', JSON.stringify(this.keyTopics)); // 将keyTopics数组转换为字符串传递
      if (this.choosedFunc == 10) {
        formData.append('text', this.choosedText);
      }
      else {
        formData.append('text', '');
      }
      // 🔥 先滚动到顶部，再显示等待卡片
      this.scrollToTop()
      this.showBlankCard = true
      mergeCardBackend(formData).then(response => {
        if (response.error_num === 0) {
          let finalContent=response.finalContent;
          let cid = response.cardId
          this.isInitial = false
          this.get_all_cards();
          this.waitDecodedResult(cid, finalContent)
          // 🔥 等待卡片消失时，滚动到白底色卡区域的最上方（由watch处理）
          // this.isInitial = false
          // this.get_all_cards();
          // this.$message.success('卡片添加成功');
          // this.$emit('cardMerge', finalContent)
        }
        else {
          this.isInitial = false
          this.get_all_cards();
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
        this.isInitial = false
        this.get_all_cards();
        this.showBlankCard = false  // 🔥 等待卡片消失
        this.$emit('cardMerge', finalContent, this.choosedText)
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
          this.isInitial = false
          this.get_all_cards();
          this.showBlankCard = false  // 🔥 等待卡片消失
          this.$emit('cardMerge', finalContent, this.choosedText)
        });
      }
    },

    addChoseCard2List(para) {
      if (para['checked']) {
        this.choosedCardIdList.push(para['cid']);
        // 🔥 更新当前勾选的卡片ID（用于抬起效果）
        this.selectedCardId = para['cid'];
        // alert(para['cid']);
      }
      else {
        const index = this.choosedCardIdList.indexOf(para['cid']);
        if (index > -1) {
          this.choosedCardIdList.splice(index, 1);
          // 🔥 如果取消勾选，清除selectedCardId
          if (this.selectedCardId === para['cid']) {
            this.selectedCardId = null;
          }
        }
      }
      // this.$emit('chooseCardChange', this.choosedCardIdList)
      // 🔥 传递卡片ID列表和当前操作的卡片完整数据（用于自动勾选文档和切换子场景）
      const currentCard = this.cardList.find(card => card.cid === para['cid']);
      // 传递数组副本而不是原数组引用，同时传递当前卡片数据和操作类型
      this.$emit('chooseCardChange', [...this.choosedCardIdList], currentCard || null, para['checked'])
    },
    deleteCard() {
      this.isInitial = false
      this.$message.success('删除成功！');
      this.get_all_cards();
    },
    updateOrder() {
      this.isInitial = false
      this.get_all_cards();
      this.$message.success('您刚刚打开的卡片以及相关卡片已被移动至最前！');
    },
    reAcquireOver() {
      this.reAcquire = false
    },
    generateKeyTopics() {
      // 获取所有 keyWords，分割后去重并存入 keyTopics
      const keywordsSet = new Set();
      const meta = this.semanticReorganizeMeta || {};
      const metaFiltered = !!(
        meta.sampled
        || (meta.pipeline === 'v2_condense_hierarchy'
          && Array.isArray(meta.reorganize_selected_cids)
          && meta.reorganize_selected_cids.length > 0)
      );
      const networkCards = this.keywordNetworkCards;

      networkCards.forEach(card => {
        if (card.keyWords) {
          const keywords = card.keyWords.split(/[,，]/);
          keywords.forEach(keyword => {
            const trimmedKeyword = keyword.trim();
            if (trimmedKeyword && !keywordsSet.has(trimmedKeyword)) {
              keywordsSet.add(trimmedKeyword);
            }
          });
        }
      });

      this.cardList.forEach(card => {
        if (card.contentTitle) {
          this.contentTitles.push(card.contentTitle);
          this.preIndexs.push(card.preIndex);
        }
      });

      // 🔥 合并部落知识关键词（v2/抽样时仅保留已梳理选中卡片上出现的部落词）
      (this.tribalKeywords || []).forEach(kw => {
        if (!kw || keywordsSet.has(kw)) return;
        if (metaFiltered) {
          const onProcessed = networkCards.some((card) => {
            if (!card.keyWords) return false;
            return card.keyWords.split(/[,，]/).map((k) => k.trim()).includes(kw);
          });
          if (onProcessed) keywordsSet.add(kw);
        } else {
          keywordsSet.add(kw);
        }
      });

      // 🔥 如果是第一次调用，记录初始关键词集合
      if (this.initialKeywords.size === 0) {
        this.initialKeywords = new Set(keywordsSet);
      }

      this.keyTopics = Array.from(keywordsSet); // 转换为数组并赋值
      this.$emit("sendKeyTopics", this.keyTopics)
    },

    // 🔥 获取初始关键词数组（安全方法）
    getInitialKeywordsArray() {
      try {
        if (this.initialKeywords && this.initialKeywords.size > 0) {
          return Array.from(this.initialKeywords);
        }
      } catch (e) {
        console.warn('[CardGrid] getInitialKeywordsArray 出错:', e);
      }
      return [];
    },

    // 🔥 处理子组件本地更新通知
    handleKeywordDMTLocalUpdated(data) {
      const keyword = data.keyword;
      if (keyword) {
        this.locallyUpdatedKeywordsInParent.add(keyword);
        
        // 🔥 立即更新父组件的临时数据源，这样重新加载时就是最新数据
        if (!this.keywordFourColorDMT[keyword]) {
          this.keywordFourColorDMT[keyword] = {};
        }
        this.keywordFourColorDMT[keyword].four_color_type = data.four_color_type || '';
        this.keywordFourColorDMT[keyword].dmt_level = data.dmt_level || '';
        this.keywordFourColorDMT[keyword].knowledge_type = data.knowledge_type || '';
        
        if (!this.keywordFourColorDMTPure[keyword]) {
          this.keywordFourColorDMTPure[keyword] = {};
        }
        this.keywordFourColorDMTPure[keyword].four_color_type = data.four_color_type || '';
        this.keywordFourColorDMTPure[keyword].dmt_level = data.dmt_level || '';
        this.keywordFourColorDMTPure[keyword].knowledge_type = data.knowledge_type || '';
        
        console.log('[CardGrid] 更新临时数据源，关键词:', keyword, '，四色:', data.four_color_type, '，DMT:', data.dmt_level, '，三类知识:', data.knowledge_type);
      }
    },
    
    // 🔥 处理关键词重命名事件
    // async handleKeywordRename({ oldKeyword, newKeyword, needReAnalyze }) {
    //   console.log('[CardGrid] handleKeywordRename被调用:', { oldKeyword, newKeyword, needReAnalyze });

    //   // 🔥 找到对应的永久卡片并设置loading状态
    //   const permanentCard = this.cardList.find(card => {
    //     return card.title === '关键词神经元永久卡' && 
    //            card.keyWords && 
    //            card.keyWords.split(/[,，]/).map(k => k.trim()).includes(oldKeyword);
    //   });
      
    //   if (permanentCard && !needReAnalyze) {
    //     // 非合并操作，设置永久卡loading状态
    //     this.updatingPermanentCards.add(permanentCard.cid);
    //     console.log(`[CardGrid] 设置永久卡 ${permanentCard.cid} 的loading状态`);
    //   }
      
    //   // 🔥 显示加载提示
    //   this.$message({
    //     message: `正在更新关键词"${newKeyword}"的相关卡片...`,
    //     type: 'info',
    //     duration: 0, // 不自动关闭
    //     showClose: false
    //   });
      
    //   try {
    //     // 更新初始关键词集合（如果旧关键词在集合中）
    //     if (this.initialKeywords && this.initialKeywords.has(oldKeyword)) {
    //       this.initialKeywords.delete(oldKeyword);
    //       this.initialKeywords.add(newKeyword);
    //     }
        
    //     // 🔥 如果不是合并操作（needReAnalyze为false），先手动迁移前端数据映射
    //     if (!needReAnalyze && oldKeyword && newKeyword) {
    //       // 将旧关键词的四色DMT数据迁移到新关键词
    //       if (this.keywordFourColorDMT[oldKeyword]) {
    //         this.keywordFourColorDMT[newKeyword] = { ...this.keywordFourColorDMT[oldKeyword] };
    //         delete this.keywordFourColorDMT[oldKeyword];
    //         console.log(`[CardGrid] 已迁移前端数据映射: '${oldKeyword}' -> '${newKeyword}'`);
    //       }
    //       // 同步更新纯对象版本
    //       if (this.keywordFourColorDMTPure[oldKeyword]) {
    //         this.keywordFourColorDMTPure[newKeyword] = { ...this.keywordFourColorDMTPure[oldKeyword] };
    //         delete this.keywordFourColorDMTPure[oldKeyword];
    //       }
    //       // 更新本地更新标记
    //       if (this.locallyUpdatedKeywordsInParent && this.locallyUpdatedKeywordsInParent.has(oldKeyword)) {
    //         this.locallyUpdatedKeywordsInParent.delete(oldKeyword);
    //         this.locallyUpdatedKeywordsInParent.add(newKeyword);
    //       }
    //     }
        
    //     // 🔥 先刷新卡片列表以更新关键词显示（这会从后端获取最新的keywordFourColorDMT数据）
    //     await this.get_all_cards();
        
    //     // 🔥 如果需要重新分析新关键词的四色DMT（在刷新后分析，确保能获取到最新数据）
    //     if (needReAnalyze && newKeyword) {
    //       console.log('[CardGrid] 准备分析新关键词的四色DMT:', newKeyword);
    //       try {
    //         // 🔥 等待一下确保数据已更新
    //         await this.$nextTick();
            
    //         // 🔥 使用旧关键词查找卡片（因为重命名API已经将这些卡片的关键词更新为新关键词，
    //         // 但我们可以先通过旧关键词找到这些卡片，这些卡片现在应该包含新关键词）
    //         const cardsWithKeyword = this.cardList.filter(card => {
    //           if (!card.keyWords) return false;
    //           const keywords = card.keyWords.split(/[,，]/).map(k => k.trim());
    //           // 先尝试用新关键词查找（如果已更新）
    //           if (keywords.includes(newKeyword)) {
    //             return true;
    //           }
    //           // 如果找不到，用旧关键词查找（可能还没刷新）
    //           if (keywords.includes(oldKeyword)) {
    //             return true;
    //           }
    //           return false;
    //         });
            
    //         console.log('[CardGrid] 找到相关卡片数量:', cardsWithKeyword.length);
            
    //         if (cardsWithKeyword.length > 0) {
    //           console.log('[CardGrid] 准备调用分析API，关键词:', newKeyword, '卡片内容长度:', cardsWithKeyword.map(c => c.content).join('\n\n').substring(0, 4000).length);
    //           // 合并所有卡片内容用于分析
    //           const cardContent = cardsWithKeyword.map(card => card.content).join('\n\n');
              
    //           // 调用后端API分析新关键词的四色DMT
    //           const { API_BASE_URL } = require('@/config/apiConfig');
    //           const response = await fetch(`${API_BASE_URL}/api/analyze_keyword_four_color_dmt`, {
    //             method: 'POST',
    //             headers: {
    //               'Content-Type': 'application/json',
    //             },
    //             body: JSON.stringify({
    //               keyword: newKeyword,
    //               card_content: cardContent.substring(0, 4000), // 限制长度
    //               username: localStorage.getItem('userId'),
    //               scene_name: this.sceneName,
    //               sub_scene_name: this.subSceneName
    //             })
    //           });
              
    //           const data = await response.json();
    //           if (data.error_num === 0) {
    //             console.log(`[CardGrid] 新关键词'${newKeyword}'的四色DMT分析完成: 四色=${data.four_color_type}, DMT=${data.dmt_level}`);
    //             // 🔥 分析完成后，再次刷新数据以确保前端显示最新结果
    //             // this.get_all_cards();
    //             await this.get_all_cards();
    //           } else {
    //             console.error(`[CardGrid] 新关键词'${newKeyword}'的四色DMT分析失败:`, data.msg);
    //           }
    //         } else {
    //           console.warn(`[CardGrid] 未找到包含关键词'${oldKeyword}'或'${newKeyword}'的卡片`);
    //         }
    //       } catch (error) {
    //         console.error('[CardGrid] 分析新关键词四色DMT失败:', error);
    //       }
    //     }

    //     // 🔥 清除永久卡的loading状态
    //     if (permanentCard && !needReAnalyze) {
    //       this.updatingPermanentCards.delete(permanentCard.cid);
    //       console.log(`[CardGrid] 清除永久卡 ${permanentCard.cid} 的loading状态`);
    //     }
        
    //     // 🔥 关闭加载提示并显示完成消息
    //     this.$message.closeAll();
    //     this.$message.success(`关键词"${newKeyword}"更新完成`);
    //   } catch (error) {
    //     console.error('[CardGrid] 处理关键词重命名失败:', error);
    //     // 出错时也要清除loading状态
    //     if (permanentCard && !needReAnalyze) {
    //       this.updatingPermanentCards.delete(permanentCard.cid);
    //     }
    //     this.$message.closeAll();
    //     this.$message.error('更新关键词时出错：' + error.message);
    //   }
    // },

    // 🔥 处理关键词融合开始（显示等待卡、跳转顶部）
    handleFusionKeywordStart(newCardId) {
      console.log('[CardGrid] handleFusionKeywordStart被调用:', { newCardId });
      // 使用$emit通知父组件更新cardMaking状态
      this.$emit('update:cardMaking', true);
      // 保存新卡片ID，用于后续跳转（如果传入的是null，后续会在complete中更新）
      if (newCardId) {
        this.lastCreatedCardId = newCardId;
      }
      // 跳转到顶部（scrollToTop会在watch中自动触发）
    },
    
    // 🔥 处理关键词融合完成（隐藏等待卡、跳转到新卡片）
    handleFusionKeywordComplete(newCardId) {
      console.log('[CardGrid] handleFusionKeywordComplete被调用:', { newCardId });
      // 使用$emit通知父组件更新cardMaking状态
      this.$emit('update:cardMaking', false);
      // 如果传入null，说明融合失败，直接返回
      if (!newCardId) {
        this.lastCreatedCardId = null;
        return;
      }
      // 更新lastCreatedCardId
      this.lastCreatedCardId = newCardId;
      // 等待DOM更新后跳转到新卡片（确保get_all_cards已完成）
      this.$nextTick(() => {
        setTimeout(() => {
          if (newCardId) {
            this.scrollToCard(newCardId);
          }
          this.lastCreatedCardId = null;
        }, 2000); // 延迟2000ms确保卡片已渲染
      });
    },

    // 🔥 处理永久卡生成开始（显示等待卡、跳转顶部）
    handlePermanentCardGenerateStart() {
      console.log('[CardGrid] handlePermanentCardGenerateStart被调用');
      // 使用$emit通知父组件更新cardMaking状态
      this.$emit('update:cardMaking', true);
    },
    
    // 🔥 处理永久卡生成完成（隐藏等待卡、跳转到新卡片）
    handlePermanentCardGenerateComplete(newCardId) {
      console.log('[CardGrid] handlePermanentCardGenerateComplete被调用:', { newCardId });
      // 使用$emit通知父组件更新cardMaking状态
      this.$emit('update:cardMaking', false);
      // 如果传入null，说明生成失败，直接返回
      if (!newCardId) {
        this.lastCreatedCardId = null;
        return;
      }
      // 更新lastCreatedCardId（用于后续跳转）
      this.lastCreatedCardId = newCardId;
      // 等待DOM更新后跳转到新卡片（确保get_all_cards已完成，cardMaking状态已更新，等待卡片已消失）
      this.$nextTick(() => {
        // 使用多个nextTick确保Vue的响应式更新已完成
        this.$nextTick(() => {
          setTimeout(() => {
            if (newCardId) {
              console.log('[CardGrid] 尝试跳转到新生成的卡片:', newCardId);
              console.log('[CardGrid] cardList长度:', this.cardList ? this.cardList.length : 0);
              console.log('[CardGrid] filteredCards长度:', this.filteredCards ? this.filteredCards.length : 0);
              
              // 尝试多次查找卡片，因为DOM可能还在更新
              const tryScrollToCard = (attempt = 0) => {
                const cardElement = document.querySelector(`[data-cid="${newCardId}"]`);
                if (cardElement) {
                  console.log('[CardGrid] 找到卡片元素，开始滚动');
                  cardElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                  // 添加闪烁效果提示用户
                  this.flashingCid = newCardId;
                  setTimeout(() => {
                    this.flashingCid = null;
                  }, 2000);
                  this.lastCreatedCardId = null;
                } else if (attempt < 5) {
                  // 如果找不到，再试一次（最多5次）
                  console.log(`[CardGrid] 第${attempt + 1}次尝试未找到卡片元素，100ms后重试`);
                  setTimeout(() => tryScrollToCard(attempt + 1), 100);
                } else {
                  console.warn('[CardGrid] 多次尝试后仍未找到卡片元素:', newCardId);
                  this.lastCreatedCardId = null;
                }
              };
              
              tryScrollToCard();
            }
          }, 800); // 延迟800ms，确保DOM已更新
        });
      });
    },
    
    // 🔥 处理永久卡更新开始（设置loading状态、滚动到原卡片）
    handlePermanentCardUpdateStart(cid) {
      console.log('[CardGrid] handlePermanentCardUpdateStart被调用:', { cid });
      if (cid) {
        this.updatingPermanentCards.add(cid);
        console.log(`[CardGrid] 设置永久卡 ${cid} 的loading状态`);
        // 🔥 滚动到原卡片位置
        this.$nextTick(() => {
          setTimeout(() => {
            console.log('[CardGrid] 更新开始，跳转到原卡片:', cid);
            this.scrollToCard(cid);
          }, 100); // 短暂延迟确保DOM已更新
        });
      }
    },
    
    // 🔥 处理永久卡更新完成（清除loading状态、滚动到原卡片）
    handlePermanentCardUpdateComplete(cid) {
      console.log('[CardGrid] handlePermanentCardUpdateComplete被调用:', { cid });
      if (cid) {
        this.updatingPermanentCards.delete(cid);
        console.log(`[CardGrid] 清除永久卡 ${cid} 的loading状态`);
        // 🔥 更新完成后滚动到原卡片位置
        this.$nextTick(() => {
          setTimeout(() => {
            console.log('[CardGrid] 更新完成，跳转到原卡片:', cid);
            this.scrollToCard(cid);
          }, 300); // 延迟确保loading overlay已消失
        });
      }
    },

    // 🔥 处理关键词重命名开始事件（在API调用之前）
    handleKeywordRenameStart({ oldKeyword, newKeyword }) {
      console.log('[CardGrid] handleKeywordRenameStart被调用:', { oldKeyword, newKeyword });
      
      // 🔥 找到对应的永久卡片并设置loading状态
      const permanentCard = this.cardList.find(card => {
        if (card.title !== '关键词神经元永久卡' || !card.keyWords) return false;
        const keywords = card.keyWords.split(/[,，]/).map(k => k.trim());
        return keywords.includes(oldKeyword) || keywords.includes(newKeyword);
      });
      
      if (permanentCard) {
        this.updatingPermanentCards.add(permanentCard.cid);
        console.log(`[CardGrid] 设置永久卡 ${permanentCard.cid} 的loading状态`);
      }
    },
    
    // 🔥 处理关键词重命名事件（API调用完成后）
    async handleKeywordRename(event) {
      const { oldKeyword, newKeyword, needReAnalyze } = event || {};
      console.log('[CardGrid] handleKeywordRename被调用:', { oldKeyword, newKeyword, needReAnalyze, event });
      
      // 🔥 保存旧的永久卡CID（用于后续清除loading状态，需要在get_all_cards之前查找）
      let oldPermanentCardCid = null;
      const oldPermanentCard = this.cardList.find(card => {
        if (card.title !== '关键词神经元永久卡' || !card.keyWords) return false;
        const keywords = card.keyWords.split(/[,，]/).map(k => k.trim());
        return keywords.includes(oldKeyword) || keywords.includes(newKeyword);
      });
      
      if (oldPermanentCard && !needReAnalyze) {
        oldPermanentCardCid = oldPermanentCard.cid;
      }
      
      try {
        // 🔥 刷新卡片列表以获取最新数据（参照cardTidyUpById的处理方式）
        this.isInitial = false;
        await this.get_all_cards();
        
        // 更新初始关键词集合（如果旧关键词在集合中）
        if (this.initialKeywords && this.initialKeywords.has(oldKeyword)) {
          this.initialKeywords.delete(oldKeyword);
          this.initialKeywords.add(newKeyword);
        }
        
        // 🔥 如果不是合并操作（needReAnalyze为false），先手动迁移前端数据映射
        if (!needReAnalyze && oldKeyword && newKeyword) {
          // 将旧关键词的四色DMT数据迁移到新关键词
          if (this.keywordFourColorDMT[oldKeyword]) {
            this.keywordFourColorDMT[newKeyword] = { ...this.keywordFourColorDMT[oldKeyword] };
            delete this.keywordFourColorDMT[oldKeyword];
            console.log(`[CardGrid] 已迁移前端数据映射: '${oldKeyword}' -> '${newKeyword}'`);
          }
          // 同步更新纯对象版本
          if (this.keywordFourColorDMTPure[oldKeyword]) {
            this.keywordFourColorDMTPure[newKeyword] = { ...this.keywordFourColorDMTPure[oldKeyword] };
            delete this.keywordFourColorDMTPure[oldKeyword];
          }
          // 更新本地更新标记
          if (this.locallyUpdatedKeywordsInParent && this.locallyUpdatedKeywordsInParent.has(oldKeyword)) {
            this.locallyUpdatedKeywordsInParent.delete(oldKeyword);
            this.locallyUpdatedKeywordsInParent.add(newKeyword);
          }
        }
        
        // 🔥 如果需要重新分析新关键词的四色DMT（在刷新后分析，确保能获取到最新数据）
        if (needReAnalyze && newKeyword) {
        console.log('[CardGrid] 准备分析新关键词的四色DMT:', newKeyword);
        try {
          // 🔥 等待一下确保数据已更新
          await this.$nextTick();
          
          // 🔥 使用旧关键词查找卡片（因为重命名API已经将这些卡片的关键词更新为新关键词，
          // 但我们可以先通过旧关键词找到这些卡片，这些卡片现在应该包含新关键词）
          const cardsWithKeyword = this.cardList.filter(card => {
            if (!card.keyWords) return false;
            const keywords = card.keyWords.split(/[,，]/).map(k => k.trim());
            // 先尝试用新关键词查找（如果已更新）
            if (keywords.includes(newKeyword)) {
              return true;
            }
            // 如果找不到，用旧关键词查找（可能还没刷新）
            if (keywords.includes(oldKeyword)) {
              return true;
            }
            return false;
          });
          
          console.log('[CardGrid] 找到相关卡片数量:', cardsWithKeyword.length);
          
          if (cardsWithKeyword.length > 0) {
            console.log('[CardGrid] 准备调用分析API，关键词:', newKeyword, '卡片内容长度:', cardsWithKeyword.map(c => c.content).join('\n\n').substring(0, 4000).length);
            // 合并所有卡片内容用于分析
            const cardContent = cardsWithKeyword.map(card => card.content).join('\n\n');
            
            // 调用后端API分析新关键词的四色DMT
            const { API_BASE_URL } = require('@/config/apiConfig');
            const response = await fetch(`${API_BASE_URL}/api/analyze_keyword_four_color_dmt`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
              },
              body: JSON.stringify({
                keyword: newKeyword,
                card_content: cardContent.substring(0, 4000), // 限制长度
                username: localStorage.getItem('userId'),
                scene_name: this.sceneName,
                sub_scene_name: this.subSceneName
              })
            });
            
            const data = await response.json();
            if (data.error_num === 0) {
              console.log(`[CardGrid] 新关键词'${newKeyword}'的四色DMT分析完成: 四色=${data.four_color_type}, DMT=${data.dmt_level}`);
              // 🔥 分析完成后，再次刷新数据以确保前端显示最新结果
              await this.get_all_cards();
            } else {
              console.error(`[CardGrid] 新关键词'${newKeyword}'的四色DMT分析失败:`, data.msg);
            }
          } else {
            console.warn(`[CardGrid] 未找到包含关键词'${oldKeyword}'或'${newKeyword}'的卡片`);
          }
        } catch (error) {
          console.error('[CardGrid] 分析新关键词四色DMT失败:', error);
        }
        }
      } catch (error) {
        console.error('[CardGrid] 处理关键词重命名失败:', error);
        this.$message.error('更新关键词时出错：' + error.message);
      } finally {
        // 🔥 清除永久卡的loading状态（参照cardTidyUpById的处理方式，无论成功失败都清除）
        if (oldPermanentCardCid && !needReAnalyze) {
          this.updatingPermanentCards.delete(oldPermanentCardCid);
          console.log(`[CardGrid] 清除永久卡 ${oldPermanentCardCid} 的loading状态`);
        }
      }
    },

    analyzeFieldSizes() {
      if (!this.cardList || this.cardList.length === 0) {
        console.log("没有卡片数据可分析");
        return;
      }
      
      // 字段大小统计
      const fieldSizes = {};
      
      // 分析每张卡片的每个字段
      this.cardList.forEach(card => {
        Object.keys(card).forEach(fieldName => {
          const value = card[fieldName];
          // 转成字符串测量大小
          const size = JSON.stringify(value).length;
          
          if (!fieldSizes[fieldName]) {
            fieldSizes[fieldName] = {
              totalSize: 0,
              count: 0,
              maxSize: 0,
              minSize: Infinity
            };
          }
          
          fieldSizes[fieldName].totalSize += size;
          fieldSizes[fieldName].count++;
          fieldSizes[fieldName].maxSize = Math.max(fieldSizes[fieldName].maxSize, size);
          fieldSizes[fieldName].minSize = Math.min(fieldSizes[fieldName].minSize, size);
        });
      });
      
      // 计算平均值并按总大小排序
      const results = Object.keys(fieldSizes).map(fieldName => {
        const stats = fieldSizes[fieldName];
        return {
          field: fieldName,
          totalSizeKB: (stats.totalSize / 1024).toFixed(2),
          avgSizeKB: (stats.totalSize / stats.count / 1024).toFixed(2),
          maxSizeKB: (stats.maxSize / 1024).toFixed(2)
        };
      }).sort((a, b) => b.totalSizeKB - a.totalSizeKB);
      
      console.table(results);
      return results;
    },

    async get_all_cards() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      // 🔥 调用筛分API获取所有卡片（高价值卡片在前）
      // get_cards(formData).then(data => {
      get_filtered_cards(formData).then(data => {
        this.showBlankCard = false

        let content = data.content;
        this.cardList = content;
        // 初次加载即标注有附图的卡片（左上角图标高亮）
        this.cardHasImageCids = (content || []).filter(c => c.has_card_image).map(c => c.cid);

        // 🔥 保存本子描述（中文）到组件数据中
        if (data.notebook_description) {
          this.notebookDescription = data.notebook_description;
        } else {
          this.notebookDescription = null;
        }

        // 🔥 使用后端明确返回的高价值卡片ID列表（固定的集合，不依赖排序）
        this.highValueCardIds = new Set();
        if (data.high_value_cids && Array.isArray(data.high_value_cids)) {
          // 后端明确返回的高价值卡片ID列表
          data.high_value_cids.forEach(cid => {
            this.highValueCardIds.add(cid);
          });
        } else {
          // 兼容旧逻辑：如果没有返回high_value_cids，从前N张提取（不应该出现）
          console.warn('[CardGrid] 后端未返回high_value_cids，使用兼容逻辑');
          let totalCount = this.cardList.length;
          let targetCount = totalCount > 50 ? Math.max(1, Math.floor(totalCount / 10)) : Math.max(1, Math.floor(totalCount / 5));
          for (let i = 0; i < Math.min(targetCount, this.cardList.length); i++) {
            this.highValueCardIds.add(this.cardList[i].cid);
          }
        }

        // 🔥 保存问题链排序顺序和分类信息（必须在initializeQuestions之前设置）
        this.questionChainSortedOrder = data.question_chain_sorted_order || [];
        this.questionChainCategories = data.question_chain_categories || {};
        console.log('[CardGrid] 加载问题链排序顺序，CID数量:', this.questionChainSortedOrder.length);
        console.log('[CardGrid] 加载问题链分类信息，分类数量:', Object.keys(this.questionChainCategories).length);
        console.log('[CardGrid] 分类信息详情:', this.questionChainCategories);

        this.initializeQuestions();

        // 🔥 检查问题链排序状态，如果未排序则自动排序
        const questionChainSorted = data.question_chain_sorted || false;
        if (!questionChainSorted && this.filteredCards && this.filteredCards.length > 0) {
          console.log('[CardGrid] 问题链未排序，开始智能排序...');
          // 延迟执行排序，确保initializeQuestions已经完成并提取了问题
          this.$nextTick(() => {
            setTimeout(() => {
              this.smartSortQuestions();
            }, 2000); // 延迟2秒，确保问题评估开始后执行排序
            });
        }

        // 新增，cid到标题的映射
        this.cardList.forEach(card => {
          this.cidToTitleMap[card.cid] = card.contentTitle;
        });

        console.log("获取到的卡片列表: ", this.cardList);
        console.log("高价值卡片数量: ", this.highValueCardIds.size);

        this.analyzeFieldSizes()

        // 🔥 接收关键词四色DMT信息
        // this.keywordFourColorDMT = data.keyword_four_color_dmt || {};
        // console.log("关键词四色DMT信息: ", this.keywordFourColorDMT);
        // 🔥 部落知识关键词
        this.tribalKeywords = data.tribal_keywords || [];
        this.semanticReorganizeMeta = data.semantic_reorganize_meta || {};

        // 🔥 接收关键词四色DMT信息
        const rawData = data.keyword_four_color_dmt || {};
        console.log("关键词四色DMT信息（原始数据）: ", rawData);
        console.log("关键词四色DMT信息（原始数据类型）: ", typeof rawData);
        
        // 🔥 使用 JSON 序列化/反序列化来创建一个纯对象，避免 Vue Proxy 响应式代理问题
        let keywordData = {};
        try {
          if (rawData && typeof rawData === 'object') {
            // 先尝试 JSON 序列化/反序列化，确保是纯对象
            const jsonStr = JSON.stringify(rawData);
            console.log("关键词四色DMT信息（JSON序列化长度）: ", jsonStr.length);
            
            if (jsonStr && jsonStr !== '{}' && jsonStr.length > 2) {
              keywordData = JSON.parse(jsonStr);
              console.log("关键词四色DMT信息（JSON解析后键数量）: ", Object.keys(keywordData).length);
              console.log("关键词四色DMT信息（键示例）: ", Object.keys(keywordData).slice(0, 5));
            } else {
              // 如果序列化结果是空对象，直接使用原始数据
              keywordData = rawData;
              console.log("关键词四色DMT信息（使用原始数据，键数量）: ", Object.keys(keywordData).length);
            }
          }
        } catch (e) {
          console.error("处理关键词四色DMT信息时出错: ", e);
          keywordData = rawData;
        }
        
        // 🔥 赋值给响应式对象（如果已有本地更新，需要合并保留）
        // 先检查是否有本地更新的关键词，如果有则合并保留
        if (this.locallyUpdatedKeywordsInParent && this.locallyUpdatedKeywordsInParent.size > 0) {
          this.locallyUpdatedKeywordsInParent.forEach(keyword => {
            const localData = this.keywordFourColorDMT[keyword];
            if (localData && (localData.four_color_type || localData.dmt_level || localData.knowledge_type)) {
              keywordData[keyword] = {
                four_color_type: localData.four_color_type || (keywordData[keyword] && keywordData[keyword].four_color_type) || '',
                dmt_level: localData.dmt_level || (keywordData[keyword] && keywordData[keyword].dmt_level) || '',
                knowledge_type: localData.knowledge_type || (keywordData[keyword] && keywordData[keyword].knowledge_type) || ''
              };
            }
          });
        }
        this.keywordFourColorDMT = keywordData;
        
        // 🔥 同时创建一个纯对象版本用于传递（避免 Vue Proxy 问题）
        this.keywordFourColorDMTPure = JSON.parse(JSON.stringify(keywordData));
        
        console.log("关键词四色DMT信息（最终赋值）: ", this.keywordFourColorDMT);
        console.log("关键词四色DMT信息（最终键数量）: ", Object.keys(this.keywordFourColorDMT).length);
        console.log("关键词四色DMT信息（纯对象版本键数量）: ", Object.keys(this.keywordFourColorDMTPure).length);
        console.log("关键词四色DMT信息（纯对象版本类型）: ", typeof this.keywordFourColorDMTPure);

        // 🔥 接收关键词融合关系信息
        const fusionRelationsRaw = data.keyword_fusion_relations || {};
        this.keywordFusionRelations = typeof fusionRelationsRaw === 'object' ? fusionRelationsRaw : {};
        console.log("关键词融合关系信息: ", this.keywordFusionRelations);
        
        // 🔥 强制触发子组件更新（使用多次 nextTick 和延迟确保组件已挂载）
        const updateSubComponent = () => {
          if (this.$refs.keywordNetworkGraph && typeof this.$refs.keywordNetworkGraph.updateKeywordFourColorDMT === 'function') {
            const pureData = JSON.parse(JSON.stringify(keywordData));
            console.log("[CardGrid] ✅ 调用子组件 updateKeywordFourColorDMT，数据键数量:", Object.keys(pureData).length);
            this.$refs.keywordNetworkGraph.updateKeywordFourColorDMT(pureData);
            return true;
          }
          return false;
        };
        
        // 尝试多次调用
        this.$nextTick(() => {
          this.$nextTick(() => {
            if (!updateSubComponent()) {
              console.log("[CardGrid] ⚠️ 第一次尝试失败，延迟500ms再试");
              setTimeout(() => {
                if (!updateSubComponent()) {
                  console.log("[CardGrid] ⚠️ 第二次尝试失败，延迟1000ms再试");
                  setTimeout(() => {
                    if (!updateSubComponent()) {
                      console.log("[CardGrid] ❌ 多次尝试失败，子组件可能未挂载");
                    }
                  }, 1000);
                }
              }, 500);
            }
          });
        });

        this.generateKeyTopics();

        // 🔥 等待卡片列表更新完成后，检查是否需要滚动到新生成的卡片
        this.$nextTick(() => {
          setTimeout(() => {
            // 只有在cardMaking为false时才处理滚动（避免在显示等待卡片时滚动）
            if (!this.cardMaking && this.lastCreatedCardId) {
              this.scrollToNewCardOrFirstWhite();
            }
          }, 200); // 延迟200ms确保DOM已渲染
        });
        
        // 更新完毕，传回mainpage避免watch重复更新卡片
        this.$emit('cardUpdateOver');
        // 除了初始化外，调用此函数的位置均需要reacquire
        // 到上面为止只更新了cardList，但是cardList传到Card的信息并没有都被正确地用上，Card中使用了很多CardInfo信息，而它之前只在mounted
        // 更新一次，更新cardList并不会重新执行mounted，所以只能通过reAcquire变量通知其执行与mounted内一样的代码段，正确更新CardInfo
        if(this.isInitial === false) {
          // this.reAcquire = true
          this.updateCheckbox = true
          setTimeout(() => {
            this.updateCheckbox = false
          }, 50);
        }
      }).catch(error => {
        this.showBlankCard = false
        console.error("An error occurred:", error); // 错误处理
        this.$message.error("发生了一个错误, 具体log: ", error);
      });
    }
  }
};
</script>

<style>
.cardParams-dialog {
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
  width: 40vw;
  height: 60vh;
  max-width: 100%;
}

.cardParams-dialog .dialog-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.cardParams-dialog .close {
  cursor: pointer;
  font-size: 1.2em;
  color: #888;
}

.grid-container {
  max-height: 78vh;
  overflow-y: auto;

  padding: 30px;
  padding-left: 40px;

  .grid-row {
    padding: 0px;
  }

  .grid-col {
    padding: 0px;
  }
}



.card-combine-btn,
.card-summarize-btn,
.card-study-guide-btn,
.card-suggest-ideas-btn,
.card-react-btn,
.card-user-define {
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

.card-combine-btn::before,
.card-summarize-btn::before,
.card-study-guide-btn::before,
.card-suggest-ideas-btn::before,
.card-react-btn::before,
.card-user-define::before {
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

.card-combine-btn:hover,
.card-summarize-btn:hover,
.card-study-guide-btn:hover,
.card-suggest-ideas-btn:hover,
.card-react-btn:hover,
.card-user-define:hover {
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3); /* 鼠标悬停时更大的阴影 */
  transform: translateY(-2px); /* 轻微提升，制造按下效果 */
}

.card-combine-btn:hover::before,
.card-summarize-btn:hover::before,
.card-study-guide-btn:hover::before,
.card-suggest-ideas-btn:hover::before,
.card-react-btn:hover::before,
.card-user-define:hover::before {
  transform: scale(1); /* 鼠标悬停时伪元素放大，增加光泽感 */
}

/* 卡片融合按钮 */
.card-combine-btn {
  background-color: #5e3380; /* 深蓝色背景，保持神秘感 */
  color: rgb(255, 255, 255); /* 白色文字 */
}

.card-combine-btn:hover {
  background-color: #4b2355; /* 鼠标悬停时更深的蓝色 */
}

/* 多卡片内容总结按钮 */
.card-summarize-btn {
  background-color: #8B3626;
  color: white;
}

.card-summarize-btn:hover {
  background-color: #5C2121;
}

/* 多卡片学习指导按钮 */
.card-study-guide-btn {
  background-color: #1E4D3C;
  color: white;
}

.card-study-guide-btn:hover {
  background-color: #0F3B2B;
}

/* 总结想法按钮 */
.card-suggest-ideas-btn {
  background-color: #00796B;
  color: white;
}

.card-suggest-ideas-btn:hover {
  background-color: #005662;
}

/* 自定义追问按钮 */
.card-user-define {
  background-color: #4A2C2A;
  color: white;
}

.card-user-define:hover {
  background-color: #2E1B1B;
}

/* react加强按钮 */
.card-react-btn {
  background-color: #275176; /* 深蓝色背景，保持神秘感 */
  color: rgb(255, 255, 255); /* 白色文字 */
}

.card-react-btn:hover {
  background-color: #2a2e91; /* 鼠标悬停时更深的蓝色 */
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

/* 按钮容器样式 */
.ButtonListContainer {
  display: flex;
  flex-wrap: wrap;
  /* 允许换行 */
  justify-content: center;
  /* 水平居中对齐 */
  gap: 10px;
  /* 按钮之间间距 */
}

/* 按钮样式 */
.ButtonList {
  flex: 0 1 150px;
  /* 允许按钮宽度至少为150px，但可以更宽 */
  margin: 5px;
  /* 按钮外边距 */
  padding: 10px;
  /* 内边距 */
  font-size: 14px;
  /* 字体大小 */
  border-radius: 4px;
  /* 圆角 */
  background-color: #409eff;
  /* 背景色 */
  color: white;
  /* 字体颜色 */
  transition: background-color 0.3s;
  /* 渐变效果 */
  text-align: center;
  /* 文本居中 */
  word-break: break-word;
  /* 单词断行 */
  box-sizing: border-box;
  /* 边框计算在宽度内 */
}

.ButtonList:hover {
  background-color: #50bfff;
  /* 鼠标悬停效果 */
}

/* 输入框样式 */
.createCardQuestion .myinput .el-input__inner {
  border-radius: 4px;
  /* 圆角 */
  padding: 8px 10px;
  /* 内边距 */
  font-size: 14px;
  /* 字体大小 */
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
  flex: 1;
  /* 让这个容器占据剩余空间 */
  display: flex;
  /* 使用flex布局 */
  align-items: center;
  /* 垂直居中对齐 */
  justify-content: flex-start;
  /* 水平开始对齐 */
}

/* 移除el-input的margin，因为我们不需要Element UI默认的间距 */
.myinput .el-input__inner {
  margin: 0;
  /* 移除输入框的外边距 */
}

/* 调整按钮的margin，使其与输入框对齐 */
.userDefineButton {
  margin-left: 10px;
  /* 按钮与输入框之间的间距 */
}


@keyframes flash {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.1); }
}

.flashing {
  animation: flash 1s infinite; /* 可以设置为无限循环以便更容易观察 */
}


/* 索引卡片样式 */
.notebook-card-index {
  height: 200px;
  width: 290px;
  border-radius: 10px;
  overflow-y: auto; /* 只允许垂直滚动 */
  overflow-x: hidden; /* 禁止水平滚动 */

  padding: 20px;
  background: linear-gradient(135deg, #fef7dd 0%, #fcf2ce 100%);
  margin: 10px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08), 0 2px 4px rgba(0, 0, 0, 0.12);
  color: #50462c;
  font-family: 'Arial', sans-serif;
  position: relative;
  display: flex;
  flex-direction: column;
}

.index-card-header {
  border-bottom: 2px solid #e2bc4a;
  padding-bottom: 8px;
  margin-bottom: 10px;
  font-weight: bold;
  font-size: 16px;
  color: #50462c;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.index-card-title {
  font-size: 14px;
  font-weight: bold;
  margin-bottom: 12px;
  text-align: center;
}

.index-card-count {
  font-size: 13px;
  font-weight: normal;
  color: #827c5a;
  margin-left: 5px;
}

.index-card-content {
  flex: 1;
  overflow-y: auto;
}

.index-card-content.output-article-content {
  overflow-y: visible !important; /* 🔥 输出文章卡不需要外层滚动条 */
}

.output-article-preview {
  max-height: 140px; /* 🔥 降低高度，避免双层滚动条 */
  overflow-y: auto; /* 🔥 内层滚动条 */
  padding-right: 8px; /* 为滚动条留出空间 */
}

.index-series-title {
  font-size: 14px;
  margin-top: 8px;
  margin-bottom: 5px;
  color: #e2aa4a;
  font-weight: bold;
}

.index-card-list {
  list-style-type: none;
  padding: 0;
  margin: 0;
}

.index-card-item {
  font-size: 13px;
  padding: 3px 5px 3px 4px;
  margin: 2px 0;
  display: flex;
  align-items: flex-start;
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 4px;
  word-break: break-word;
  line-height: 1.3;
}

.index-card-item:hover {
  background-color: rgba(221, 180, 67, 0.201);
  padding-left: 6px;
  padding-right: 3px;
}

.index-card-item-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: #e2af4a;
  margin-right: 8px;
  margin-top: 4px;
  flex-shrink: 0;
}

.index-card-footer {
  font-size: 12px;
  color: #a5a684;
  margin-top: 8px;
  text-align: right;
  font-style: italic;
}


.notebook-card-waiting-single {
  position: absolute;
  top: 0;
  left: 66.6%;

  height: 200px;
  width: 290px;
  border-radius: 10px;
  overflow: hidden;

  padding: 20px;
  background-color: #ffffffdd;
  margin: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: #1d1d1d;
  font-family: 'Arial', sans-serif;
  z-index: 10;
  /* position: relative; */
}



.notebook-card-waiting {
  height: 200px;
  width: 290px;
  border-radius: 10px;
  overflow: hidden;

  padding: 20px;
  background: linear-gradient(to right, #d7def2 0%, #ffffff 30%, #ffffff 70%);
  margin: 10px;
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1), 0 6px 20px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  color: #1d1d1d;
  font-family: 'Arial', sans-serif;
  position: relative;
}

.notebook-card-waiting::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 10px;
  z-index: 1;
}

.waiting-text {
  position: relative;
  z-index: 2;
  font-size: 1.2em;
  font-weight: bold;
  text-align: center;
}

.waiting-gif {
  position: relative;
  z-index: 2;
  width: 150px;
  height: 150px;
}




.tags-container {
  position: absolute;
  top: 0px; /* 菜单出现在按钮旁 */
  right: 16px;
  left: auto;
  display: inline-flex;
  flex-direction: column;
  flex-wrap: nowrap;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 10px; /* Adjust the gap between tags */
  background-color: rgba(255, 255, 255, 0.9); /* Semi-transparent background */
  border-radius: 8px; /* Rounded corners */
  padding: 10px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); /* Optional: Adds a subtle shadow */
  margin-top: 5px;
  z-index: 1000; /* 保证菜单显示在前面 */
  width: min(1480px, calc(100vw - 48px));
  min-width: min(1180px, calc(100vw - 48px));
  max-width: calc(100vw - 32px);
}

/* 第一行筛选区域横向布局 */
.filter-row {
  display: flex;
  flex-direction: row;
  align-items: flex-start;
  justify-content: flex-start;
  gap: 15px;
  width: 100%;
  margin-bottom: 15px;
}

.filter-item {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  flex: 1;
  min-width: 0;
}

/* 标题筛选部分 */
.title-filter {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

/* 作者筛选部分 */
.author-filter {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.filter-input {
  padding: 4px 8px;
  border: 2px solid #2f2f2f;
  border-radius: 4px;
  width: 100%; /* 使用100%宽度，适应父容器 */
  min-width: 150px;
  max-width: 220px;
}




/* 🔥 卡片层级筛选滑块样式 */
.layer-filter-slider {
  cursor: pointer;
  user-select: none;
  margin-bottom: 0; /* 移除底部边距，因为现在在横向布局中 */
  width: 100%;
}

.layer-filter-slider .slider-track {
  width: 100%;
  max-width: 200px;
  height: 32px;
  background: rgba(255, 255, 255, 0.95);
  border: 1.5px solid rgba(148, 163, 184, 0.25);
  border-radius: 16px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  transition: all 0.3s ease;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.layer-filter-slider .slider-thumb {
  position: absolute;
  width: 100px;
  height: 28px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  border-radius: 14px;
  left: 2px;
  top: 50%;
  transform: translateY(-50%);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
}

.layer-filter-slider .slider-thumb.high-value {
  left: calc(100% - 102px);
}

.layer-filter-slider .slider-text {
  font-size: 0.85rem;
  font-weight: 600;
  color: #334155;
  z-index: 1;
  position: relative;
  white-space: nowrap;
}

.layer-filter-slider .slider-text.right {
  margin-left: auto;
}

.layer-filter-slider:hover .slider-track {
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.4);
}

.layer-filter-slider:hover .slider-thumb {
  box-shadow: 0 4px 10px rgba(59, 130, 246, 0.5);
}





/* 标签标题和恢复按钮 */
.tags-header {
  display: flex;
  align-items: center;
  width: 100%;
  justify-content: space-between;
  font-weight: bold;
  margin-bottom: 8px;
}

.generate-permanent-card-btn {
  background-color: #6f559f;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  margin-right: 8px;
}

.generate-permanent-card-btn:hover:not(:disabled) {
  background-color: #493d8b;
}

.generate-permanent-card-btn:disabled {
  background-color: #999;
  cursor: not-allowed;
}

.analyze-cognitive-state-btn {
  background-color: #9370db;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  margin-right: 8px;
}

.analyze-cognitive-state-btn:hover:not(:disabled) {
  background-color: #7b68ee;
}

.analyze-cognitive-state-btn:disabled {
  background-color: #999;
  cursor: not-allowed;
}

.semantic-reorganize-btn {
  background-color: #2e7d6a;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  margin-right: 8px;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.semantic-reorganize-btn.incremental {
  background-color: #3a8f7b;
}

.semantic-reorganize-btn:hover:not(:disabled) {
  filter: brightness(0.92);
}

.semantic-reorganize-btn:disabled {
  background-color: #999;
  cursor: not-allowed;
}

.semantic-rollback-btn {
  background-color: #c45c26;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
  margin-right: 8px;
}

.semantic-rollback-btn:hover:not(:disabled) {
  filter: brightness(0.92);
}

.semantic-rollback-btn:disabled {
  background-color: #999;
  cursor: not-allowed;
}

.semantic-reorganize-floating-progress {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 10000;
  width: 360px;
  max-width: calc(100vw - 40px);
  padding: 14px 16px 12px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.semantic-reorganize-floating-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.semantic-reorganize-floating-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.semantic-reorganize-floating-close {
  border: none;
  background: transparent;
  font-size: 18px;
  line-height: 1;
  color: #909399;
  cursor: pointer;
  padding: 0 4px;
}

.semantic-reorganize-floating-close:hover {
  color: #606266;
}

.semantic-reorganize-floating-detail {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
  word-break: break-all;
}

.reset-btn {
  background-color: #ff5555;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  font-size: 12px;
}

.tag-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 4px; /* Rounded corners for buttons */
  background-color: #6f559f; /* GitLab-like background color */
  color: white;
  font-size: 14px;
  cursor: pointer;
  outline: none;
  transition: background-color 0.3s ease;
  margin: 2px; /* Optional: Adds margin around each button */
}

.tag-btn:hover {
  background-color: #493d8b; /* Darker color on hover */
}

/* 已选中状态的按钮 */
.tag-btn.selected {
  background-color: #1f1652;
}


/* 标签筛选滚动容器 */
.tags-scroll-container {
  max-height: 200px; /* 最大高度200px */
  overflow-y: auto; /* 竖向滚动条 */
  overflow-x: hidden; /* 隐藏横向滚动条 */
  padding: 5px 0; /* 上下留出一点空间 */
}

/* 自定义滚动条样式 */
.tags-scroll-container::-webkit-scrollbar {
  width: 6px; /* 滚动条宽度 */
}

.tags-scroll-container::-webkit-scrollbar-track {
  background: #f1f1f1; /* 滚动条轨道颜色 */
  border-radius: 3px;
}

.tags-scroll-container::-webkit-scrollbar-thumb {
  background: #888; /* 滚动条滑块颜色 */
  border-radius: 3px;
}

.tags-scroll-container::-webkit-scrollbar-thumb:hover {
  background: #555; /* 滚动条滑块悬停颜色 */
}




/* 🔥 文档交叉梳理建议索引卡样式 */
.cross-document-index {
  background: linear-gradient(135deg, #fef7dd 0%, #fcf2ce 100%);
}

.group-twin-progress-banner {
  margin: -6px 0 14px;
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.55;
  color: #5c4a21;
  background: #faf6e8;
  border-radius: 4px;
  border: 1px solid #ede4c9;
}

.cross-document-content {
  padding: 0;
}

.cross-document-preview {
  cursor: pointer;
  padding: 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.cross-document-preview:hover {
  background-color: rgba(221, 180, 67, 0.201);
}

.cross-document-text {
  font-size: 13px;
  line-height: 1.6;
  color: #50462c;
  max-height: 140px;
  overflow-y: auto;
}

/* 🔥 本子输出文章索引卡样式 */
.output-article-index {
  background: linear-gradient(135deg, #fff5e6 0%, #ffe6cc 100%);
}

.output-article-content {
  padding: 0;
  overflow-y: visible !important; /* 🔥 输出文章卡不需要滚动条 */
}

.output-article-preview {
  cursor: pointer;
  padding: 8px;
  border-radius: 4px;
  transition: background-color 0.2s;
  max-height: 140px; /* 🔥 限制高度，避免双层滚动条 */
  overflow-y: auto; /* 🔥 内层滚动条 */
  padding-right: 8px; /* 为滚动条留出空间 */
}

.output-article-preview:hover {
  background-color: rgba(255, 165, 0, 0.1);
}

.output-article-text {
  font-size: 13px;
  line-height: 1.6;
  color: #8b4513;
  white-space: pre-wrap;
}

.index-card-generate {
  color: #ff6600;
  font-size: 12px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.index-card-generate:hover {
  text-decoration: underline;
}



/* 问题索引卡样式 */
.question-index {
  background: linear-gradient(135deg, #fff2c8 0%, #fff1bc 100%);
  color: rgb(0, 0, 0);
}

/* .question-category-header {
  padding: 8px 12px;
  margin: 8px 0 4px 0;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 4px;
  border-left: 3px solid #007bff;
  cursor: default;
}

.question-category-title {
  font-weight: 600;
  font-size: 13px;
  color: #495057;
  letter-spacing: 0.5px;
} */

.question-category-header {
  padding: 8px 12px;
  margin: 8px 0 4px 0;
  background: rgba(255, 255, 255, 0.6);
  border-radius: 4px;
  border-left: 3px solid #007bff;
  cursor: pointer;
  user-select: none;
  transition: background-color 0.2s;
}

.question-category-header:hover {
  background: rgba(255, 255, 255, 0.8);
}

.question-category-title {
  font-weight: 600;
  font-size: 13px;
  color: #495057;
  letter-spacing: 0.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.category-arrow {
  display: inline-block;
  width: 0;
  height: 0;
  border-style: solid;
  border-width: 5px 0 5px 8px;
  border-color: transparent transparent transparent #6c757d;
  transition: transform 0.2s;
  margin-right: 6px;
  vertical-align: middle;
  cursor: pointer;
}

.category-arrow-expanded {
  transform: rotate(90deg);
}

.question-item {
  background: #fcf8e3;
  border: 1px solid #fdf7cc;
  border-radius: 8px;
  margin-bottom: 8px;
  padding: 12px;
  transition: all 0.3s ease;
  cursor: pointer;
}

.question-index .index-card-header {
  border-bottom: 2px solid #e0b841;
  padding-bottom: 8px;
  margin-bottom: 10px;
  font-weight: bold;
  font-size: 16px;
  color: #50462c;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.question-item {
  background: #fcf8e3;
  border: 1px solid #fdf7cc;
  border-radius: 8px;
  margin-bottom: 8px;
  padding: 12px;
  transition: all 0.3s ease;
  cursor: pointer;
}

.question-item:hover {
  background: #fcf8e3;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(106, 72, 0, 0.1);
  border-color: #e1ba3982;
}

.question-dot {
  background: #ffbf00;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  flex-shrink: 0;
}

/* 🔥 DMT字母标识样式 */
.question-dmt-badge {
  font-size: 12px;
  font-weight: bold;
  min-width: 16px;
  text-align: center;
  margin-right: 8px;
  flex-shrink: 0;
}

.indexcard-question-content {
  flex: 1;
  min-width: 0;
  border-radius: 4px;
}

.indexcard-question-content:hover {
  background: #fff4c1 !important;
  border-color: #f6d15882 !important;
}

.question-text {
  font-size: 14px;
  line-height: 1.4;
  margin-bottom: 8px;
  color: rgb(0, 0, 0);
  word-wrap: break-word;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.question-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #7d766c;
}

.question-author {
  font-weight: 500;
  color: #495057;
}

.question-score {
  background: #e7deb1;
  color: #495057;
  padding: 2px 8px;
  border-radius: 12px;
  font-weight: bold;
}

/* 问题评估提示框样式 */
.question-tooltip {
  background: rgba(0, 0, 0, 0.9);
  color: white;
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  font-size: 12px;
  min-width: 200px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.tooltip-header {
  font-weight: bold;
  margin-bottom: 8px;
  color: #ffd700;
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
  padding-bottom: 4px;
}

.tooltip-content {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.evaluation-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.evaluation-label {
  color: rgba(255, 255, 255, 0.8);
  font-size: 11px;
}

.evaluation-value {
  color: #4CAF50;
  font-weight: bold;
  font-size: 11px;
}

.evaluation-value.total-score {
  color: #ffd700;
  font-size: 12px;
}



/* 问题完整文本提示框样式 */
.question-fulltext-tooltip {
  background: rgba(0, 0, 0, 0.9);
  color: white;
  padding: 12px;
  border-radius: 8px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
  font-size: 12px;
  max-width: 400px;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.question-fulltext-tooltip .tooltip-header {
  font-weight: bold;
  margin-bottom: 8px;
  color: #ffd700;
  border-bottom: 1px solid rgba(255, 255, 255, 0.2);
  padding-bottom: 4px;
}

.question-fulltext-tooltip .fulltext-content {
  line-height: 1.5;
  word-wrap: break-word;
  white-space: pre-wrap;
}



/* 问题评论相关样式 */
.question-comment {
  color: #007bff;
  font-size: 12px;
  margin-left: auto; /* 新增这行 */
  margin-right: 4px; /* 原来的margin-left改为margin-right */
}

.question-comment-dialog {
  padding: 20px 0;
}

.question-info {
  margin-bottom: 20px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  border-left: 4px solid #007bff;
}

.question-info h4 {
  margin: 0 0 10px 0;
  color: #495057;
  font-size: 14px;
}

.question-preview {
  margin: 0;
  color: #6c757d;
  font-size: 13px;
  line-height: 1.5;
  word-wrap: break-word;
}

.comment-section h4 {
  margin: 0 0 10px 0;
  color: #495057;
  font-size: 14px;
}

.dialog-footer {
  text-align: right;
  padding-top: 20px;
  border-top: 1px solid #e9ecef;
}




.form-container {
  display: flex;
  flex-direction: column; /* 垂直堆叠子元素 */
  gap: 10px;
  width: 100%; /* 占据父容器的全部宽度 */
}

.template-buttons {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}



/* 索引卡片伸缩后置索引样式 */
.post-index-icon {
  width: 17px;
  height: 17px;
  border-radius: 50%;
  background-color: #daa438;
  color: white;
  font-size: 12px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 8px;
  margin-top: 1px;
  flex-shrink: 0;
  cursor: pointer;
  padding: 0 4px;
  box-sizing: border-box;
}

.index-card-item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.index-card-item-title.has-dmt {
  font-weight: bold;
}

.post-index-icon:hover {
  background-color: #a7a51c;
  color: #fff9f1;
}

.post-index-count {
  line-height: 1;
  white-space: nowrap;
}

.post-index-tooltip {
  position: fixed;
  z-index: 9999;
  background: white;
  border-radius: 4px;
  padding: 8px 12px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  font-size: 14px;
  pointer-events: none;
}
</style>