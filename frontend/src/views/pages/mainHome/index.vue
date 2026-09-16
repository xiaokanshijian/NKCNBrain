<template>
  <div class="notebook-homepage">
    <div id="particles" :style="{ background: backgroundStyle }"></div>
    <div class="header">
      <h1>NKCN·Brain V3.2 欢迎你 {{ this.curUserName }}</h1>
      <div class="header-buttons">
        <div class="system-choice-slider" @click="toggleSystem">
          <div class="slider-track">
            <div class="slider-thumb" :class="{ 'slow': systemChoice === 0 }"></div>
            <!-- 🔥 修复：滑钮在哪边就显示哪边的字，即当前状态的文字 -->
            <!-- systemChoice === 0 时滑块在右边（slow），显示"慢思考" -->
            <!-- systemChoice === 1 时滑块在左边，显示"快思考" -->
            <span class="slider-text" v-if="systemChoice === 1">快思考</span>
            <span class="slider-text right" v-if="systemChoice === 0">慢思考</span>
          </div>
        </div>
        <button @click="backtologin" class="action-button">
          {{ (isByAdmin === 'true' || isByUplevel === 'true') ? '返回上一页面' : '返回登录' }}
        </button>
      </div>
    </div>

    <div class="content">
      <div class="select-scene">
        <select v-model="selectedScene" @change="handleSelect" class="custom-select">
          <option disabled value="">场景列表</option>
          <option v-for="scene in  this.sceneList " :key="scene['sid']" :value="scene['sid']" :style="{
            color: scene['needDemo'] ? '#FF5733' : '#A9A9A9'
          }">
            {{ scene['description'] }}
          </option>
        </select>
        <button @click="showCreateDialog2" class="action-button">新建场景</button>
      </div>

      <div class="actions-2">
        <button @click="bookshelf" class="action-button-2" :class="{ 'active': activeButtonIndex === 0 }">书架型</button>
        <button @click="flatlayer" class="action-button-2" :class="{ 'active': activeButtonIndex === 1 }">平铺型</button>
        <button @click="taskClusterView" class="action-button-2" :class="{ 'active': activeButtonIndex === 2 }">任务簇型</button>
        <div class="view-more-wrap">
          <button class="view-more-btn" @click.stop="showHeaderMoreMenu = !showHeaderMoreMenu" title="更多">⋯</button>
          <div v-if="showHeaderMoreMenu" class="view-more-menu" @click.stop>
            <button class="view-more-item" @click="openHiddenIntergrowth">共生型（旧版）</button>
          </div>
        </div>
      </div>

      <div v-for="scene in sceneList" :key="scene.sid" class="scene-wrapper" v-if="activeButtonIndex === 0">
        <div class="actions">
          <h1 :style="{ color: scene['needDemo'] ? '#FF5733' : '#A9A9A9' }">
            {{ scene.description }}场景
            <!-- 为第8个之后的场景添加刷新图标 -->
            <svg 
              v-if="sceneList.indexOf(scene) >= sceneNumLimit || (sceneList.indexOf(scene) < sceneNumLimit && shouldShowLoadIcon(scene))"
              @click="loadSpecificScene(scene)"
              viewBox="0 0 24 24" 
              width="24" 
              height="24" 
              style="display: inline-block; margin-left: 8px; cursor: pointer; vertical-align: middle;"
              title="加载此场景的笔记本">
              <path 
                fill="currentColor" 
                d="M17.65 6.35A7.958 7.958 0 0012 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08A5.99 5.99 0 0112 18c-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z" 
              />
            </svg>
            <span
              class="scene-ontology-btn"
              :class="{ 'scene-ontology-btn--ready': ontologyStateOf('scene', scene.sid).has_result }"
              title="场景大本体语义梳理"
              @click.stop="toggleOntologyMenu('scene', scene.sid, scene.description + '场景', $event)"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
                <circle cx="6" cy="7" r="2.2" fill="currentColor"/>
                <circle cx="18" cy="7" r="2.2" fill="currentColor"/>
                <circle cx="12" cy="17" r="2.2" fill="currentColor"/>
                <circle cx="12" cy="10" r="1.6" fill="currentColor"/>
                <path d="M7.8 8.2 L10.6 9.4 M16.2 8.2 L13.4 9.4 M12 11.6 L12 14.8" stroke="currentColor" stroke-width="1.4" fill="none"/>
              </svg>
            </span>
          </h1>
          <button @click="showCreateDialog(scene)" class="action-button" v-if="needDemoBtn(scene.sid)">新建{{ scene.description
          }}场景Demo笔记本</button>
          <button @click="showCreateDialog(scene)" class="action-button" v-else>新建{{ scene.description }}场景笔记本</button>
        </div>
        <div class="notebook-list-row">
          <div class="notebook-item" v-for="notebook in notebooks[scene.description]" :key="notebook.id"
            @contextmenu.prevent="showNotebookContextMenu($event, notebook, scene)">
            <div class="notebook-info">
              <div class="title-comment-wrapper">
                <h3 v-if="!isEditing||isEditingBookTitle!==notebook.title||isEditingBookWriter!==notebook.writer" 
                  @click="editDescription(notebook)">
                    {{ notebook.description }}
                </h3>
                <input v-if="isEditing&&isEditingBookTitle===notebook.title&&isEditingBookWriter===notebook.writer" 
                  v-model="editedDescription" 
                  @blur="saveDescription(notebook)" 
                  ref="inputRef" 
                  class="bookDescriptionEdit"
                />
                <button
                  class="book-comment-btn"
                  @click.stop="doComment(notebook)"
                >留言</button>
              </div>
              <div class="description-shared-wrapper">
                <p class="break-words">{{ notebook.title }}</p>
                <span v-if="isInTodoList(notebook)" class="alert-icon" v-bind:title="'您有未完成的共生问答'">
                  <i class="exclamation-icon">!</i>
                </span>
                <span v-if="notebook.syncUsers !== ''" class="group-icon" v-bind:title="`${notebook.writer}共享的群组共生笔记本`">
                  组
                </span>
                <span v-else-if="notebook.isShared === 1" class="shared-icon" v-bind:title="`这是${notebook.writer}分享来的笔记本`">
                  享
                </span>
                <span v-else-if="notebook.title === demoBookNames[scene.description]" class="demo-icon" v-bind:title="`这是场景发布者${notebook.writer}的示例笔记本`">
                  例
                </span>
              </div>
              <div style="color: lavender; font-size: 0.85rem;">
                页数：{{ notebook.cardNum }}&nbsp;&nbsp;&nbsp;&nbsp;作者：{{
                  notebook.title === demoBookNames[scene.description] 
                    ? (notebook.writer ? notebook.writer + '（场景作者）' : '无记录')
                    : (notebook.writer || '无记录')
                }}
              </div>
            </div>
            <div class="notebook-actions">
              <button @click="openNotebook(notebook, scene)" v-if="showOpenBookButton" class="open-button">打开</button>
              <button @click="deleteNotebook(notebook, scene)" v-if="showOpenBookButton" class="delete-button">删除</button>
              <button @click="shareNotebook(notebook, scene)" v-if="showOpenBookButton && !needDemoBtn(scene.sid)"
                class="share-button">分享</button>
              <button @click="shareDemoNotebook(notebook, scene)" v-if="showOpenBookButton && needDemoBtn(scene.sid)"
                class="share-button">发布</button>
              <button @click="" v-if="showOpenBookButton === false" class="open-button">正在载入新笔记本，请稍后</button>
            </div>
          </div>
        </div>
        <div class="line"></div>
      </div>

      <div class="scene-wrapper" v-if="activeButtonIndex === 1">
        <div class="notebook-list-row">
          <!-- 渲染所有排序后的笔记本 -->
          <div class="notebook-item" v-for="notebook in allNotebooksSorted" :key="notebook.id"
            @contextmenu.prevent="showNotebookContextMenu($event, notebook, { description: notebook.scene })">
            <div class="notebook-info">
              <div class="title-comment-wrapper">
                <h3 v-if="!isEditing||isEditingBookTitle!==notebook.title||isEditingBookWriter!==notebook.writer" 
                  @click="editDescription(notebook)">
                    {{ notebook.description }}
                </h3>
                <input v-if="isEditing&&isEditingBookTitle===notebook.title&&isEditingBookWriter===notebook.writer" 
                  v-model="editedDescription" 
                  @blur="saveDescriptionPingpu(notebook)" 
                  ref="inputRef" 
                  class="bookDescriptionEdit"
                />
                <button
                  class="book-comment-btn"
                  @click.stop="doComment(notebook)"
                >留言</button>
              </div>
              <div class="description-shared-wrapper">
                <p class="break-words">{{ notebook.title }}</p>
                <span v-if="isInTodoList(notebook)" class="alert-icon" v-bind:title="'您有未完成的共生问答'">
                  <i class="exclamation-icon">!</i>
                </span>
                <span v-if="notebook.syncUsers !== ''" class="group-icon" v-bind:title="`${notebook.writer}共享的${notebook.scene}场景群组笔记本`">
                  组
                </span>
                <span v-else-if="notebook.isShared === 1" class="shared-icon" v-bind:title="`${notebook.writer}分享来的${notebook.scene}场景笔记本`">
                  享
                </span>
                <span v-else-if="notebook.title === demoBookNames[notebook.scene]" class="demo-icon" v-bind:title="`${notebook.scene}场景发布者${notebook.writer}的示例笔记本`">
                  例
                </span>
                <span v-else class="common-icon" v-bind:title="`您自己的${notebook.scene}场景普通笔记本`">
                  普
                </span>
              </div>
              <div style="color: lavender; font-size: 0.85rem;">
                页数：{{ notebook.cardNum }}&nbsp;&nbsp;&nbsp;&nbsp;作者：{{
                  notebook.title === demoBookNames[notebook.scene] 
                    ? (notebook.writer ? notebook.writer + '（场景作者）' : '无记录')
                    : (notebook.writer || '无记录')
                }}
              </div>
            </div>
            <div class="notebook-actions">
              <button @click="openNotebook(notebook, findSceneByNotebook(notebook, sceneList))" v-if="showOpenBookButton" class="open-button">打开</button>
              <button @click="deleteNotebook(notebook, findSceneByNotebook(notebook, sceneList))" v-if="showOpenBookButton" class="delete-button">删除</button>
              <button @click="shareNotebook(notebook, findSceneByNotebook(notebook, sceneList))" v-if="showOpenBookButton && !needDemoBtn(findSceneByNotebook(notebook, sceneList).sid)"
                class="share-button">分享</button>
              <button @click="shareDemoNotebook(notebook, findSceneByNotebook(notebook, sceneList))" v-if="showOpenBookButton && needDemoBtn(findSceneByNotebook(notebook, sceneList).sid)"
                class="share-button">发布</button>
              <button @click="" v-if="showOpenBookButton === false" class="open-button">正在载入新笔记本，请稍后</button>
            </div>
          </div>
        </div>
      </div>

      <div class="scene-wrapper task-cluster-wrapper" v-if="activeButtonIndex === 2">
        <div class="task-cluster-header">
          <h1 class="task-cluster-title">任务簇视图</h1>
          <p class="task-cluster-desc">
            按任务关联性聚类你的本子（含个人本、组本作者本、协作者组本）。同场景未必同簇，跨场景也可能同簇。
          </p>
          <div class="task-cluster-toolbar">
            <button class="open-button" @click="runTaskClusterAnalyze(false)" :disabled="taskClusterLoading">
              {{ taskClusterResult.processed ? '刷新结果' : '开始任务簇分析' }}
            </button>
            <button class="share-button" @click="confirmRerunTaskClusterAnalyze" :disabled="taskClusterLoading">重新分析</button>
            <button
              v-if="taskClusterResult.processed"
              class="open-button"
              @click="openCreateTaskClusterDialog"
              :disabled="taskClusterLoading"
            >新增任务簇</button>
          </div>
          <p v-if="taskClusterResult.analyzed_at" class="task-cluster-meta">
            上次分析：{{ taskClusterResult.analyzed_at }}
            <span v-if="taskClusterResult.model"> · 模型 {{ taskClusterResult.model }}</span>
            <span v-if="taskClusterResult.notebook_count"> · 共 {{ taskClusterResult.notebook_count }} 个本子</span>
          </p>
        </div>

        <div v-if="taskClusterLoading" class="task-cluster-progress-panel">
          <el-progress
            :percentage="taskClusterProgressPercent"
            :status="taskClusterProgressStatus"
          />
          <p class="task-cluster-meta">{{ taskClusterProgressMessage || '正在分析…' }}</p>
        </div>

        <template v-else-if="taskClusterResult.processed">
          <div
            v-for="cluster in sortedTaskClusters"
            :key="cluster.cluster_id"
            class="task-cluster-block"
          >
            <div class="task-cluster-block-header">
              <div class="task-cluster-block-main">
                <h3
                  v-if="!isEditingCluster || isEditingClusterId !== cluster.cluster_id || isEditingClusterField !== 'name'"
                  class="task-cluster-name editable-cluster-field"
                  @click="editClusterField(cluster, 'name')"
                >
                  {{ cluster.cluster_name }}
                  <span
                    class="scene-ontology-btn"
                    :class="{ 'scene-ontology-btn--ready': ontologyStateOf('task_cluster', cluster.cluster_id).has_result }"
                    title="任务簇大本体语义梳理"
                    @click.stop="toggleOntologyMenu('task_cluster', cluster.cluster_id, cluster.cluster_name, $event)"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
                      <circle cx="6" cy="7" r="2.2" fill="currentColor"/>
                      <circle cx="18" cy="7" r="2.2" fill="currentColor"/>
                      <circle cx="12" cy="17" r="2.2" fill="currentColor"/>
                      <circle cx="12" cy="10" r="1.6" fill="currentColor"/>
                      <path d="M7.8 8.2 L10.6 9.4 M16.2 8.2 L13.4 9.4 M12 11.6 L12 14.8" stroke="currentColor" stroke-width="1.4" fill="none"/>
                    </svg>
                  </span>
                </h3>
                <input
                  v-else
                  v-model="editedClusterText"
                  @blur="saveClusterField(cluster)"
                  ref="clusterInputRef"
                  class="bookDescriptionEdit task-cluster-name-edit"
                />
                <p
                  v-if="!isEditingCluster || isEditingClusterId !== cluster.cluster_id || isEditingClusterField !== 'summary'"
                  class="task-cluster-summary editable-cluster-field"
                  @click="editClusterField(cluster, 'summary')"
                >{{ cluster.summary }}</p>
                <input
                  v-else
                  v-model="editedClusterText"
                  @blur="saveClusterField(cluster)"
                  ref="clusterInputRef"
                  class="bookDescriptionEdit task-cluster-summary-edit"
                />
              </div>
              <button
                class="delete-button task-cluster-delete-btn"
                @click="confirmDeleteTaskCluster(cluster)"
              >删除任务簇</button>
            </div>
            <div
              v-if="(cluster.notebooks && cluster.notebooks.length) || hasPinnedNotebooksForCluster"
              class="notebook-list-row"
            >
              <div
                v-for="nb in (cluster.notebooks || [])"
                :key="nb.notebook_key"
                class="notebook-item"
                @contextmenu.prevent="showNotebookContextMenu($event, taskClusterNbToShelf(nb), taskClusterSceneOf(nb))"
              >
                <div class="notebook-info">
                  <div class="title-comment-wrapper">
                    <h3>{{ nb.bookdescription }}</h3>
                    <div
                      class="notebook-pin-btn"
                      :class="{ 'notebook-pin-btn--active': isNotebookPinned(taskClusterNbToShelf(nb)) }"
                      :title="isNotebookPinned(taskClusterNbToShelf(nb)) ? '取消任务簇勾选' : '勾选本子，便于点任务簇「+」加入'"
                      @click.stop="handleToggleNotebookPin(taskClusterNbToShelf(nb), nb.scene_name)"
                    ></div>
                  </div>
                  <div class="description-shared-wrapper">
                    <p class="break-words">{{ nb.bookName }}</p>
                    <span v-if="nb.syncUsers !== ''" class="group-icon" v-bind:title="`${nb.writer}共享的群组笔记本`">组</span>
                    <span v-else-if="nb.isShared === 1" class="shared-icon" v-bind:title="`这是${nb.writer}分享来的笔记本`">享</span>
                    <span v-else class="common-icon" v-bind:title="`您自己的普通笔记本`">普</span>
                  </div>
                  <div style="color: lavender; font-size: 0.85rem;">
                    场景：{{ nb.scene_name }}&nbsp;&nbsp;&nbsp;&nbsp;页数：{{ nb.cardNum != null ? nb.cardNum : 0 }}
                  </div>
                  <div style="color: lavender; font-size: 0.85rem;">
                    作者：{{ nb.writer || '无记录' }}&nbsp;&nbsp;&nbsp;&nbsp;最近使用：{{ nb.last_used }}
                  </div>
                </div>
                <div class="notebook-actions">
                  <button @click="openTaskClusterNotebook(nb)" v-if="showOpenBookButton" class="open-button">打开</button>
                  <button
                    @click="removeNotebookFromCluster(nb, cluster)"
                    v-if="showOpenBookButton"
                    class="delete-button"
                  >从此簇移除</button>
                </div>
              </div>
              <div
                v-if="hasPinnedNotebooksForCluster"
                class="notebook-item notebook-item--add-to-cluster"
                title="将勾选的本子加入此任务簇（可同时属于多个簇）"
                @click="addPinnedNotebooksToCluster(cluster)"
              >
                <div class="add-to-cluster-plus">+</div>
                <p class="add-to-cluster-hint">将勾选本子加入此簇</p>
              </div>
            </div>
            <p
              v-if="!(cluster.notebooks && cluster.notebooks.length) && !hasPinnedNotebooksForCluster"
              class="task-cluster-empty-hint"
            >暂无本子。勾选本子后点「+」可加入此簇</p>
          </div>

          <div v-if="taskClusterResult.unclustered && taskClusterResult.unclustered.length" class="task-cluster-unclustered">
            <h3 class="task-cluster-name">未强关联入簇的本子</h3>
            <div class="notebook-list-row">
              <div
                v-for="item in taskClusterResult.unclustered"
                :key="item.notebook_key"
                class="notebook-item"
                @contextmenu.prevent="item.notebook && showNotebookContextMenu($event, taskClusterNbToShelf(item.notebook), taskClusterSceneOf(item.notebook))"
              >
                <div class="notebook-info" v-if="item.notebook">
                  <div class="title-comment-wrapper">
                    <h3>{{ item.notebook.bookdescription }}</h3>
                    <div
                      class="notebook-pin-btn"
                      :class="{ 'notebook-pin-btn--active': isNotebookPinned(taskClusterNbToShelf(item.notebook)) }"
                      :title="isNotebookPinned(taskClusterNbToShelf(item.notebook)) ? '取消任务簇勾选' : '勾选本子，便于点任务簇「+」加入'"
                      @click.stop="handleToggleNotebookPin(taskClusterNbToShelf(item.notebook), item.notebook.scene_name)"
                    ></div>
                  </div>
                  <div class="description-shared-wrapper">
                    <p class="break-words">{{ item.notebook.bookName }}</p>
                    <span v-if="item.notebook.syncUsers !== ''" class="group-icon">组</span>
                    <span v-else-if="item.notebook.isShared === 1" class="shared-icon">享</span>
                    <span v-else class="common-icon">普</span>
                  </div>
                  <div style="color: lavender; font-size: 0.85rem;">
                    场景：{{ item.notebook.scene_name }}&nbsp;&nbsp;&nbsp;&nbsp;页数：{{ item.notebook.cardNum != null ? item.notebook.cardNum : 0 }}
                  </div>
                  <div style="color: lavender; font-size: 0.85rem;">
                    作者：{{ item.notebook.writer || '无记录' }}&nbsp;&nbsp;&nbsp;&nbsp;最近使用：{{ item.notebook.last_used }}
                  </div>
                  <div style="color: #94a3b8; font-size: 0.82rem; margin-top: 4px;">{{ item.reason }}</div>
                </div>
                <div class="notebook-actions" v-if="item.notebook">
                  <button @click="openTaskClusterNotebook(item.notebook)" v-if="showOpenBookButton" class="open-button">打开</button>
                </div>
              </div>
            </div>
          </div>

          <div
            v-if="!sortedTaskClusters.length && !(taskClusterResult.unclustered && taskClusterResult.unclustered.length)"
            class="task-cluster-empty"
          >
            <p>当前没有任务簇。可点击「新增任务簇」，或「重新分析」生成聚类。</p>
          </div>
        </template>

        <div v-else class="task-cluster-empty">
          <p>尚未进行任务簇分析。点击「开始任务簇分析」后，系统将汇总你的本子元数据并聚类。</p>
        </div>
      </div>

      <div class="scene-wrapper" v-if="activeButtonIndex === 4">
        <!-- 添加个人信息和领航员修改部分 -->
        <div class="personal-info">
          <div class="level-info">
            <span class="info-label">我的层级: {{ myLevel }}</span>
            <select v-model="selectedNewLevel" class="select-input">
              <option value="S">S级</option>
              <option value="T">T级</option>
              <option value="TA">TA级</option>
              <option value="GL">GL级</option>
              <option value="GM">GM级</option>
            </select>
            <button @click="updateLevel" class="update-btn">更新层级</button>
          </div>
          <div class="coacher-info">
            <span class="info-label">我的领航员: {{ myCoacher }}</span>
            <input v-model="newCoacher" placeholder="输入新的领航员用户名" class="text-input"/>
            <button @click="updateCoacher" class="update-btn">更新领航员</button>
          </div>
        </div>
        <!-- 添加下属用户选择框 -->
        <div class="subordinates-selector">
          <span class="info-label" style="margin-right: 4px;">下级用户列表：</span>
          <select v-model="selectedSubordinate" @change="getOnlineNum" class="select-input">
            <option value="" disabled>请选择下级用户</option>
            <option v-for="user in subordinateUsers" :key="user" :value="user">
              {{ user }}
            </option>
          </select>
        </div>
        <!-- 原有的用户信息展示部分 -->
        <div v-if="selectedSubordinate" class="user-info">
          <div>用户: {{ selectedSubordinate }}</div>
          <div>状态: {{ onlinestatus }}</div>
          <div v-if="firstBook">
            <p>最近/正在使用的本子名称: {{ firstBook.bookdescription }}</p>
            <p>最近/正在使用的开始时间: {{ formattedBookId }}</p>
            <p>归属状态: {{ firstBook.isShared ? '他人分享给' + selectedSubordinate + '的本子' : selectedSubordinate + '自己创建的本子' }}</p>
            <!-- <p>节点流: {{ firstBook.context_data }}</p> -->

            <div class="notebook-item">
              <div class="notebook-info">
                <div class="title-comment-wrapper">
                  <h3>{{ firstBook.bookdescription }}</h3>
                  <button class="book-comment-btn" @click="doIntergrowthComment()">留言</button>
                </div>
                <div class="description-shared-wrapper">
                  <p class="break-words">{{ firstBook.bookName }}</p>
                </div>
              </div>
              <div class="notebook-actions">
                <button @click="openIntergrowthBookOperation()" class="open-button">查看操作</button>
                <button @click="openIntergrowthBookSelf()" class="open-button">查看本子</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="scene-wrapper" v-if="activeButtonIndex === 5">
      </div>

    </div>
    <footer class="footer">
      <p>© 2026 NKCN·Brain V3.2. All rights reserved.</p>
    </footer>

    <div
      v-if="notebookContextMenu.visible"
      class="notebook-ctx-menu"
      :style="{ left: notebookContextMenu.x + 'px', top: notebookContextMenu.y + 'px' }"
      @click.stop
    >
      <div class="notebook-ctx-menu-title">其他功能</div>
      <button class="notebook-ctx-menu-item" @click="contextMenuDoComment">留言</button>
    </div>
  </div>

  <el-dialog
    v-model="showRerunTaskClusterDialog"
    title="重新分析"
    width="480px"
    :close-on-click-modal="false"
  >
    <el-radio-group v-model="rerunTaskClusterMode" class="task-cluster-rerun-mode">
      <div class="task-cluster-rerun-option">
        <el-radio label="full">完全重做分析</el-radio>
        <p class="task-cluster-adjust-hint">调用模型重新聚类全部本子，会覆盖你手动调整过的任务簇名称、描述与本子归属。</p>
      </div>
      <div class="task-cluster-rerun-option">
        <el-radio label="incremental">基于现有迭代</el-radio>
        <p class="task-cluster-adjust-hint">保留已有任务簇及本子归属不变，仅处理：上次分析后新增、且最近使用时间晚于上次分析时间的本子。</p>
      </div>
    </el-radio-group>
    <template #footer>
      <el-button @click="showRerunTaskClusterDialog = false">取消</el-button>
      <el-button type="primary" @click="confirmRerunTaskClusterAnalyzeSubmit">确定</el-button>
    </template>
  </el-dialog>

  <el-dialog
    v-model="showCreateTaskClusterDialog"
    title="新增任务簇"
    width="420px"
    :close-on-click-modal="false"
  >
    <el-form label-width="90px">
      <el-form-item label="簇名称">
        <el-input v-model="createTaskClusterName" placeholder="新任务簇名称" />
      </el-form-item>
      <el-form-item label="一句话描述">
        <el-input v-model="createTaskClusterSummary" placeholder="描述该任务簇的共同任务" />
      </el-form-item>
    </el-form>
    <p class="task-cluster-adjust-hint">仅新增空分类；勾选本子后点任务簇内「+」即可加入（可同时属于多个簇）。</p>
    <template #footer>
      <el-button @click="showCreateTaskClusterDialog = false">取消</el-button>
      <el-button type="primary" @click="confirmCreateTaskCluster">确定</el-button>
    </template>
  </el-dialog>

  <!-- 场景/任务簇大本体菜单 -->
  <div
    v-if="ontologyMenu.visible"
    class="ontology-menu-backdrop"
    @click="closeOntologyMenu"
  ></div>
  <div
    v-if="ontologyMenu.visible"
    class="ontology-menu-panel"
    :style="{ left: ontologyMenu.x + 'px', top: ontologyMenu.y + 'px' }"
  >
    <button
      v-if="!ontologyMenu.has_result"
      class="ontology-menu-item"
      @click="startOntologyFull"
    >梳理语义</button>
    <button
      v-else
      class="ontology-menu-item"
      @click="startOntologyFull"
    >重新梳理语义</button>
    <button class="ontology-menu-item" @click="onOntologyIterateClick">迭代梳理语义</button>
    <button
      v-if="ontologyMenu.rollback_available"
      class="ontology-menu-item"
      @click="rollbackOntology"
    >撤销本次梳理</button>
    <button
      v-if="ontologyMenu.has_result"
      class="ontology-menu-item"
      @click="openOntologyGraph"
    >查看语义网络图</button>
  </div>

  <!-- 大本体梳理进度（右下角） -->
  <div v-if="ontologyFloating.visible" class="semantic-reorganize-floating-progress ontology-floating-progress">
    <div class="semantic-reorganize-floating-header">
      <span class="semantic-reorganize-floating-title">{{ ontologyFloating.title }}</span>
      <button type="button" class="semantic-reorganize-floating-close" @click="ontologyFloating.visible = false">×</button>
    </div>
    <el-progress
      :percentage="ontologyFloating.percent"
      :status="ontologyFloating.status"
      :stroke-width="12"
    />
    <div class="semantic-reorganize-floating-detail">{{ ontologyFloating.detail }}</div>
  </div>

  <!-- 大本体网络图 -->
  <el-dialog
    v-model="ontologyGraph.visible"
    :title="ontologyGraph.title"
    width="92%"
    top="4vh"
    class="ontology-graph-dialog"
    destroy-on-close
  >
    <div class="ontology-graph-wrap" v-if="ontologyGraph.visible && ontologyGraph.keywords.length">
      <KeywordNetworkGraph
        :keywords="ontologyGraph.keywords"
        :cards="[]"
        :selected-keywords="[]"
        :keyword-four-color-dmt="ontologyGraph.keywordFourColorDMT"
        :semantic-reorganize-meta="ontologyGraph.semanticMeta"
        :initial-keywords="ontologyGraph.keywords"
        :tribal-keywords="ontologyGraph.tribalKeywords || []"
        :scene-name="ontologyGraph.scopeName"
        :ontology-scope-type="ontologyGraph.scopeType"
        :ontology-scope-id="ontologyGraph.scopeId"
        author-filter=""
        :keyword-fusion-relations="{}"
        @hierarchy-links-updated="onOntologyHierarchyLinksUpdated"
        @ontology-keywords-renamed="onOntologyKeywordsRenamed"
        @keyword-dmt-updated="onOntologyKeywordDmtUpdated"
      />
    </div>
    <p v-else class="task-cluster-adjust-hint">暂无大本体结果</p>
  </el-dialog>

  <el-dialog v-model="showDialog" width="30%" class="createNotebookDialog" :close-on-click-modal="false"
    :close-on-press-escape="false">
    <h1 class="createNotebookTitle" v-if="needDemoBtn(this.selectedScene)">创建{{ this.selectedName }}场景Demo笔记本</h1>
    <h1 class="createNotebookTitle" v-else>创建{{ this.selectedName }}场景笔记本</h1>
    <el-form :model="notebookForm" label-width="80px">
      <el-form-item label="名称(英文)">
        <el-input class="myinput" v-model="notebookForm.title"></el-input>
      </el-form-item>
      <el-form-item label="笔记描述">
        <el-input class="myinput" v-model="notebookForm.description"></el-input>
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="footer">
        <el-button class="cancelButton" @click="cancelDialog">取 消</el-button>
        <el-button class="createButton" type="primary" @click="addNewNotebook">确 定</el-button>
      </div>
    </template>
  </el-dialog>

  <el-dialog v-model="showDialog2" width="30%" class="createSceneDialog" :close-on-click-modal="false"
    :close-on-press-escape="false">
    <h1 class="createNotebookTitle">创建新场景</h1>
    <el-form :model="sceneForm" label-width="80px">
      <el-form-item label="场景名称">
        <el-input class="myinput" v-model="sceneForm.description"></el-input>
      </el-form-item>

    </el-form>
    <template #footer>
      <div class="footer">
        <input ref="fileInput" type="file" accept=".xls,.xlsx" style="display: none;" @change="handleFileChange">
        <input ref="docInput" type="file" accept=".pdf" multiple style="display: none;" @change="handleFileChange2">
        <el-button class="cancelButton" @click="cancelDialog2">取 消</el-button>
        <el-button class="import-doc" v-if="showDocButton" type="primary" @click="importDoc">导入默认文件</el-button>
        <!--        <el-button class="import-doc" type="primary" @click="importDoc">导入默认文件</el-button>-->
        <el-button class="import-prompt" v-if="!showDocButton" type="primary" @click="importPrompt">导入提示词</el-button>
        <!--        <el-button class="createButton" type="primary" @click="createNewScene">确 定</el-button>-->
      </div>
    </template>
  </el-dialog>

  <el-dialog v-model="showDialog3" width="30%" class="createSceneDialog" :close-on-click-modal="false"
    :close-on-press-escape="false">
    <h1 class="createNotebookTitle">是否为新场景添加默认文件</h1>


    <el-button class="cancelButton" @click="cancelDialog2">不加入默认文件</el-button>
    <el-button class="import-doc" type="primary" @click="yesImportDoc">加入默认文件</el-button>

  </el-dialog>


  <el-dialog v-model="shareDialogVisible" :modal="true" @open="handleOpen" @close="handleClose">
    <div class="share-actions">
      <h1>可分享用户列表</h1>
    </div>
    <div class="tab-group">
      <div style="padding: 10px 20px; font-size: 14px; font-weight: bold;">请选择分享类型:</div>
      <div 
        class="tab-item" 
        :class="{ active: shareMode === 0 }" 
        @click="shareMode = 0">
        复制(请手动指定)
      </div>
      <div 
        class="tab-item" 
        :class="{ active: shareMode === 1 }" 
        @click="changeShareMode">
        群组公开(默认您的组织上下层，可手动调整)
      </div>
    </div>
    <div class="share-actions">
      <el-table :data="userList" style="width: min-content;">
        <el-table-column prop="username" label="用户名" width="240"></el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <div 
              :class="[
                'shared-ready',
                { 'shared-intergrowth': shareMode === 1&&isUserSharedInterGrowth(row.username) },
                { 'shared-copy': shareMode === 0&&isUserSharingInProgress(row.username) }
              ]"
              @click="shareToUser(row)"
            >
              <span v-if="shareMode === 1&&isUserSharedInterGrowth(row.username)">已共享给此用户</span>
              <span v-else-if="shareMode === 0&&isUserSharingInProgress(row.username)">已复制给此用户</span>
              <!-- <span v-else>{{ row.username !== curUserName ? '分享给此用户' : '复制给自己' }}</span> -->
              <span v-else-if="shareMode === 0">{{ row.username !== curUserName ? '复制给此用户' : '复制给自己' }}</span>
              <span v-else>{{ row.username !== curUserName ? '分享给此用户' : '分享给自己（此项不点）' }}</span>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </div>
    <el-button style="margin-top: 20px; margin-left: 20px;" @click="handleSubmitInterGrowth">确认</el-button>
  </el-dialog>

  <el-dialog v-model="showCommentDialog" width="40%" :close-on-click-modal="false"
    :close-on-press-escape="false" @close="handleCommentClose">
    <div class="comment-update-group">
      <el-input type="textarea" v-model="comments"></el-input>
      <el-button class="updateCommentButton" @click="updateComments">确认</el-button>
    </div>
  </el-dialog>

  <el-dialog
    v-model="loading"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    width="30%"
  >
    <div class="dialog-content">
      <h2>加载中，请耐心等待一会...</h2>
      <i class="el-icon-loading" style="font-size: 48px; color: #409eff;"></i>
    </div>
  </el-dialog>

  <!-- 加载进度对话框 -->
  <el-dialog
    title="加载用户数据"
    v-model="showProgress"
    :close-on-click-modal="false"
    :close-on-press-escape="false"
    @close="handleProgressClose">
    <div class="progress-container">
      <el-progress 
        :percentage="loadProgress" 
        :status="progressStatus">
      </el-progress>
      <p class="progress-message">{{ progressMessage }}</p>
    </div>
  </el-dialog>

</template>

<script>
import router from '@/router'
import { addBook, getBookListByName, deleteBook, check_load_progress, makeAndGetProgressId, loadUser, getSceneByName, addScene, saveSceneExcel, saveSceneDoc, saveSceneDocOK, shareBook, uploadDemoNotebook, updateBookTime, updateBookDescri, updateBookSyncUsers, getFirstBookByName, getSubordinatesList, updateUserLevel, updateUserCoacher, get_same_level_users, getTaskCluster, analyzeTaskCluster, getTaskClusterProgress, updateTaskClusterMeta, adjustTaskClusterNotebook, createTaskCluster, deleteTaskCluster, sceneClusterSemanticStart, sceneClusterSemanticStatus, sceneClusterSemanticRollback, sceneClusterSemanticResult } from "@/views/pages/mainHome/my_js";
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElTable, ElTableColumn, ElProgress, ElMessageBox, ElRadio, ElRadioGroup } from 'element-plus'
import { getList, get_onlineNum } from '@/api/user'
import { prompt_upload } from "@/api/chat/send_message";
import { mergeCardBackend, updateComment, getComment } from "@/api/card_zym/card_js";
import KeywordNetworkGraph from '@/components/cardWindow/KeywordNetworkGraph.vue';
import {
  isNotebookPinned as checkNotebookPinned,
  toggleNotebookPin,
  loadPinnedNotebookKeys,
} from '@/utils/pinnedCrossNotebooks';

export default {
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    ElTable,
    ElTableColumn,
    ElProgress,
    ElMessageBox,
    ElRadio,
    ElRadioGroup,
    KeywordNetworkGraph,
  },
  data() {
    return {
      systemChoice: 0, // 系统选择：0=System2慢思考，1=System1快思考
      sceneNumLimit: 8,
      bookNumLimit: 4,
      notebookTotalCounts: {}, // 记录每个场景的笔记本总数

      // 打开加载时显示进度条
      showProgress: false,
      loadProgress: 0,
      progressMessage: '',
      progressStatus: '',
      progressInterval: null,
      progressId: null,

      notebookToBeShared: null,
      shareMode: 0, // 默认选中"复制"按钮
      // 存储正在进行共享操作的用户名，按本子名分组
      sharingInterGrowthMap: {},

      // 存储正在进行分享操作的用户名，按本子名分组
      sharingInProgressMap: {}, 
      // 层级关系（上级）
      level_hierarchy_up: {
        'GM': 'GL',
        'GL': 'TA',
        'TA': 'T', 
        'T': 'S',
        'S': 'None'
      },
      // 层级关系（下级）
      level_hierarchy_down: {
        'GM': 'None',
        'GL': 'GM',
        'TA': 'GL', 
        'T': 'TA',
        'S': 'T'
      },
      // 共生优化
      myLevel: '',
      myCoacher: '',
      selectedNewLevel: '',
      newCoacher: '',
      subordinateUsers: [],
      selectedSubordinate: '',
      curLevel: 'GM',
      // 基础共生
      curCoacherName: '',
      firstBook: null,
      backgroundStyle: 'linear-gradient(-45deg, #542090, #143871, #261137, #5971af)',
      onlineUsername: [],
      onlineUserBookName: [],
      onlinestatus: '离线',

      isEditing: false,
      isEditingBookTitle: '',
      isEditingBookWriter: '',
      editedDescription: '',

      // 本子留言批注
      updateCommentsBook: null,
      commentBookName: '',
      comments: '',
      showCommentDialog: false,

      activeButtonIndex: 0, // 存储当前激活的按钮索引
      loading: false,
      sharedUser: null,
      sharedBookName: null,
      userList: [], // 用于保存用户列表
      shareDialogVisible: false,
      isByAdmin: 'false',
      isByUplevel: 'false',
      exampleNoteBook: [
        // { id: 1, title: "示例笔记本1", description: "第一个示例笔记本描述" },
        // { id: 2, title: "示例笔记本2", description: "第二个示例笔记本描述" },
        // { id: 3, title: "示例笔记本3", description: "第三个示例笔记本描述" }
      ],
      notebooks: {},
      demoBookNames: {},
      sceneList: [],
      selectedScene: -1,
      selectedName: '',
      bookName: "",
      //description
      des: "",
      showDialog: false,// 控制对话框显示的变量
      showDialog2: false,// 控制对话框显示的变量
      curUserName: '',
      notebookForm: {
        title: '',
        description: ''
      },
      sceneForm: {
        description: '阅读'
      },
      showDocButton: false,
      showOpenBookButton: true,
      showDialog3: false,

      pinnedNotebookRevision: 0,
      notebookContextMenu: {
        visible: false,
        x: 0,
        y: 0,
        notebook: null,
        scene: null,
      },

      isEditingCluster: false,
      isEditingClusterId: '',
      isEditingClusterField: '',
      editedClusterText: '',

      showRerunTaskClusterDialog: false,
      rerunTaskClusterMode: 'incremental',
      taskClusterAnalyzeMode: 'full',

      showCreateTaskClusterDialog: false,
      createTaskClusterName: '',
      createTaskClusterSummary: '',

      // 场景/任务簇大本体
      ontologyStates: {},
      ontologyMenu: {
        visible: false,
        x: 0,
        y: 0,
        scope_type: 'scene',
        scope_id: '',
        scope_name: '',
        has_result: false,
        rollback_available: false,
      },
      ontologyFloating: {
        visible: false,
        title: '',
        percent: 0,
        detail: '',
        status: undefined,
      },
      ontologyGraph: {
        visible: false,
        title: '',
        scopeName: '',
        scopeType: '',
        scopeId: '',
        keywords: [],
        keywordFourColorDMT: {},
        tribalKeywords: [],
        semanticMeta: {},
      },
      ontologyPollTimer: null,
      ontologyPollKey: '',

      showHeaderMoreMenu: false,
      taskClusterLoading: false,
      taskClusterProgressPercent: 0,
      taskClusterProgressMessage: '',
      taskClusterProgressStatus: '',
      taskClusterProgressTimer: null,
      taskClusterResult: {
        processed: false,
        clusters: [],
        unclustered: [],
        analyzed_at: '',
        model: '',
        notebook_count: 0,
      },
    };
  },
  created() {
    console.log('Home created');
    this.selectedScene = 1;
    this.selectedName = '阅读';
    this.curUserName = localStorage.getItem('originRealName');
    this.curCoacherName = localStorage.getItem('coacherName')
    this.curLevel = localStorage.getItem('level')
    localStorage.setItem('realName', localStorage.getItem('originRealName'));
    localStorage.setItem('sceneName', this.selectedName);
    localStorage.setItem('home2login', 'false');
    console.log("home2login", localStorage.getItem('home2login'))
    this.updateSceneList();
    // this.updateNoteBookList();
  },
  mounted() {
    console.log('Home mounted');
    // import会报错，需要用require
    require('particles.js')
    this.loadParticlesJS();

    // 🔥 加载用户的系统选择
    this.loadSystemChoice();

    // 获取来源路由路径
    if (localStorage.getItem('fromPath') === '/live') {
        console.log('从live页面来的');
        // localStorage.setItem('fromPath', 'no')
        this.isByAdmin = localStorage.getItem('byadmin')
        this.isByUplevel = localStorage.getItem('byuplevel')
        this.openHiddenIntergrowth()
    } else if (localStorage.getItem('fromPath') === '/home?') {
        console.log('从home页面来的D2T');
        // localStorage.setItem('fromPath', 'no')
        localStorage.setItem('byuplevel', 'false')
        this.isByAdmin = localStorage.getItem('byadmin')
        this.isByUplevel = localStorage.getItem('byuplevel')
        this.openHiddenIntergrowth()
    } else {
        this.isByAdmin = localStorage.getItem('byadmin')
        this.isByUplevel = localStorage.getItem('byuplevel')
    }
    document.addEventListener('click', this.handleDocumentClick);
  },
  computed: {
    formattedBookId() {
      if (this.firstBook && this.firstBook.bookId) {
        const date = new Date(this.firstBook.bookId);
        const year = date.getFullYear();
        const month = date.getMonth() + 1; // getMonth() 返回的月份从0开始
        const day = date.getDate();
        const hours = date.getHours();
        const minutes = date.getMinutes();
        const seconds = date.getSeconds();

        // 格式化为两位数
        const formatNumber = (n) => n < 10 ? '0' + n : n;

        return `${year}-${formatNumber(month)}-${formatNumber(day)} ${formatNumber(hours)}:${formatNumber(minutes)}:${formatNumber(seconds)}`;
      }
      return '';
    },
    allNotebooksSorted() {
      let allNotebooks = [];
      // 遍历notebooks对象，扁平化数组
      for (let sceneKey in this.notebooks) {
        if (this.notebooks.hasOwnProperty(sceneKey)) {
          // 扁平化当前场景的所有笔记本，并添加sceneKey到每个笔记本对象
          const notebooksInScene = this.notebooks[sceneKey];
          for (let notebook of notebooksInScene) {
            // 复制notebook对象，避免直接修改原始对象
            const notebookCopy = { ...notebook, scene: sceneKey };
            allNotebooks.push(notebookCopy);
          }
        }
      }
      // 按照notebook.id进行排序
      return allNotebooks.sort((a, b) => b.id - a.id);
    },
    hasPinnedNotebooksForCluster() {
      void this.pinnedNotebookRevision;
      return loadPinnedNotebookKeys().length > 0;
    },
    sortedTaskClusters() {
      const clusters = [...(this.taskClusterResult.clusters || [])];
      const notebookRecency = (nb) => {
        if (!nb) return 0;
        const raw = nb.bookId;
        if (raw != null && String(raw).trim() !== '') {
          let num = Number(raw);
          if (!Number.isNaN(num)) {
            if (num > 1e12) num = num / 1000;
            return num;
          }
        }
        const text = String(nb.last_used || '').trim();
        if (!text || text === '未知') return 0;
        const m = text.match(/(\d{4})年(\d{1,2})月(\d{1,2})日\s+(\d{1,2}):(\d{1,2})/);
        if (m) {
          return new Date(
            Number(m[1]),
            Number(m[2]) - 1,
            Number(m[3]),
            Number(m[4]),
            Number(m[5])
          ).getTime() / 1000;
        }
        const t = Date.parse(text);
        return Number.isNaN(t) ? 0 : t / 1000;
      };
      const clusterRecency = (cl) => {
        const nbs = cl.notebooks || [];
        if (!nbs.length) return 0;
        return Math.max(...nbs.map(notebookRecency));
      };
      return clusters.sort((a, b) => clusterRecency(b) - clusterRecency(a));
    },
  },
  beforeDestroy() {
    // 确保组件销毁时停止轮询
    this.stopProgressPolling();
    document.removeEventListener('click', this.handleDocumentClick);
    this.stopTaskClusterProgressPoll();
  },
  methods: {
    ontologyStateKey(scopeType, scopeId) {
      return `${scopeType}:${scopeId}`;
    },
    ontologyStateOf(scopeType, scopeId) {
      return this.ontologyStates[this.ontologyStateKey(scopeType, scopeId)] || {
        has_result: false,
        rollback_available: false,
        running: false,
      };
    },
    ontologyViewerName() {
      return (
        localStorage.getItem('originRealName')
        || localStorage.getItem('realName')
        || ''
      ).trim();
    },
    async refreshOntologyStatus(scopeType, scopeId) {
      const username = this.ontologyViewerName();
      if (!username || !scopeId) return null;
      try {
        const res = await sceneClusterSemanticStatus({
          scope_type: scopeType,
          scope_id: String(scopeId),
          viewer: username,
        });
        const data = res || {};
        const st = data.status || {};
        const key = this.ontologyStateKey(scopeType, scopeId);
        this.ontologyStates = {
          ...this.ontologyStates,
          [key]: {
            has_result: !!st.has_result,
            rollback_available: !!st.rollback_available,
            running: !!st.running,
            phase: st.phase || 'idle',
            message: st.phase_label || st.message || '',
            percent: Number(st.progress_percent || 0),
          },
        };
        return st;
      } catch (e) {
        console.warn('刷新大本体状态失败', e);
        return null;
      }
    },
    async toggleOntologyMenu(scopeType, scopeId, scopeName, event) {
      const st = await this.refreshOntologyStatus(scopeType, scopeId) || {};
      const x = Math.min((event && event.clientX) || 80, window.innerWidth - 220);
      const y = Math.min((event && event.clientY) || 80, window.innerHeight - 220);
      this.ontologyMenu = {
        visible: true,
        x,
        y,
        scope_type: scopeType,
        scope_id: String(scopeId),
        scope_name: scopeName || '',
        has_result: !!st.has_result,
        rollback_available: !!st.rollback_available,
      };
    },
    closeOntologyMenu() {
      this.ontologyMenu.visible = false;
    },
    onOntologyIterateClick() {
      this.closeOntologyMenu();
      this.$message.info('迭代梳理语义尚未做好，请稍后再试');
    },
    async startOntologyFull() {
      const menu = { ...this.ontologyMenu };
      this.closeOntologyMenu();
      const username = this.ontologyViewerName();
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      const label = menu.scope_type === 'task_cluster' ? '任务簇' : '场景';
      const tip = menu.has_result
        ? `将完全重新梳理「${menu.scope_name}」的${label}大本体语义（与首次流程相同）。是否继续？`
        : `将对「${menu.scope_name}」进行${label}大本体语义梳理。是否继续？`;
      try {
        await this.$confirm(tip, `${label}大本体语义梳理`, { type: 'warning' });
      } catch (e) {
        return;
      }
      try {
        const res = await sceneClusterSemanticStart({
          scope_type: menu.scope_type,
          scope_id: menu.scope_id,
          viewer: username,
          mode: 'full',
        });
        const data = res || {};
        if (Number(data.error_num) !== 0) {
          this.$message.error(data.msg || '发起梳理失败');
          return;
        }
        this.$message.success(menu.has_result ? '已开始重新梳理语义' : '已开始梳理语义');
        this.ontologyFloating = {
          visible: true,
          title: `${label}大本体 · ${menu.scope_name}`,
          percent: 2,
          detail: '已提交任务…',
          status: undefined,
        };
        this.pollOntologyStatus(menu.scope_type, menu.scope_id, menu.scope_name);
      } catch (e) {
        this.$message.error('请求失败：' + (e.message || e));
      }
    },
    pollOntologyStatus(scopeType, scopeId, scopeName) {
      if (this.ontologyPollTimer) clearTimeout(this.ontologyPollTimer);
      this.ontologyPollKey = this.ontologyStateKey(scopeType, scopeId);
      const label = scopeType === 'task_cluster' ? '任务簇' : '场景';
      const tick = async () => {
        const st = await this.refreshOntologyStatus(scopeType, scopeId);
        if (!st) {
          this.ontologyPollTimer = setTimeout(tick, 2500);
          return;
        }
        const running = !!st.running || ['select_books', 'book_prepare', 'scope_keywords', 'scope_connect_attrs'].includes(st.phase);
        this.ontologyFloating.visible = true;
        this.ontologyFloating.title = `${label}大本体 · ${scopeName || ''}`;
        this.ontologyFloating.percent = Math.min(100, Number(st.progress_percent || 0));
        this.ontologyFloating.detail = st.phase_label || st.message || st.phase || '';
        if (st.phase === 'error') {
          this.ontologyFloating.status = 'exception';
          this.ontologyFloating.percent = 100;
          this.$message.error(st.error || st.message || '大本体梳理失败');
          this.ontologyPollTimer = null;
          return;
        }
        if (st.phase === 'completed') {
          this.ontologyFloating.status = 'success';
          this.ontologyFloating.percent = 100;
          this.ontologyFloating.detail = '已完成';
          this.$message.success(`${label}大本体梳理完成`);
          this.ontologyPollTimer = null;
          // 自动打开图
          this.openOntologyGraphFor(scopeType, scopeId, scopeName);
          return;
        }
        if (!running && st.phase === 'idle') {
          this.ontologyPollTimer = null;
          return;
        }
        this.ontologyPollTimer = setTimeout(tick, 2000);
      };
      tick();
    },
    async rollbackOntology() {
      const menu = { ...this.ontologyMenu };
      this.closeOntologyMenu();
      try {
        await this.$confirm('将回退到本次重新梳理前的大本体结果。是否继续？', '撤销本次梳理', { type: 'warning' });
      } catch (e) {
        return;
      }
      const username = this.ontologyViewerName();
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      try {
        const res = await sceneClusterSemanticRollback({
          scope_type: menu.scope_type,
          scope_id: menu.scope_id,
          viewer: username,
        });
        const data = res || {};
        if (Number(data.error_num) !== 0) {
          this.$message.error(data.msg || '回退失败');
          return;
        }
        this.$message.success('已回退');
        await this.refreshOntologyStatus(menu.scope_type, menu.scope_id);
      } catch (e) {
        this.$message.error('回退失败：' + (e.message || e));
      }
    },
    async openOntologyGraph() {
      const menu = { ...this.ontologyMenu };
      this.closeOntologyMenu();
      await this.openOntologyGraphFor(menu.scope_type, menu.scope_id, menu.scope_name);
    },
    async openOntologyGraphFor(scopeType, scopeId, scopeName) {
      try {
        const username = this.ontologyViewerName();
        if (!username) {
          this.$message.warning('请先登录');
          return;
        }
        const res = await sceneClusterSemanticResult({
          scope_type: scopeType,
          scope_id: String(scopeId),
          viewer: username,
        });
        const data = res || {};
        if (!data.has_result) {
          this.$message.info('暂无大本体结果');
          return;
        }
        const label = scopeType === 'task_cluster' ? '任务簇' : '场景';
        // 兼容：属性可能在顶层或 meta 内
        const attrs = {
          ...(data.meta && data.meta.keywordFourColorDMT ? data.meta.keywordFourColorDMT : {}),
          ...(data.keywordFourColorDMT || {}),
        };
        const keywords = data.keywords || (data.meta && data.meta.keywords) || [];
        const links = data.hierarchy_links
          || (data.semantic_reorganize_meta && data.semantic_reorganize_meta.hierarchy_links)
          || (data.meta && data.meta.hierarchy_links)
          || [];
        const tribalKeywords = Object.keys(attrs).filter(
          (k) => String((attrs[k] || {}).knowledge_type || '').toLowerCase() === 'trib'
        );
        this.ontologyGraph = {
          visible: true,
          title: `${label}大本体 · ${scopeName || data.scope_name || ''}`,
          scopeName: scopeName || data.scope_name || '',
          scopeType: scopeType,
          scopeId: String(scopeId),
          keywords,
          keywordFourColorDMT: attrs,
          tribalKeywords,
          semanticMeta: {
            ...(data.semantic_reorganize_meta || {}),
            hierarchy_links: links,
            pipeline: (data.semantic_reorganize_meta && data.semantic_reorganize_meta.pipeline)
              || (data.meta && data.meta.pipeline)
              || 'scene_cluster_v1',
            keywordFourColorDMT: attrs,
          },
        };
      } catch (e) {
        this.$message.error('加载大本体结果失败：' + (e.message || e));
      }
    },
    onOntologyHierarchyLinksUpdated(links) {
      if (!this.ontologyGraph.semanticMeta) {
        this.ontologyGraph.semanticMeta = {};
      }
      this.ontologyGraph.semanticMeta.hierarchy_links = links || [];
    },
    onOntologyKeywordsRenamed(payload) {
      if (!payload) return;
      if (Array.isArray(payload.keywords)) {
        this.ontologyGraph.keywords = payload.keywords;
      }
      if (payload.keywordFourColorDMT) {
        this.ontologyGraph.keywordFourColorDMT = { ...payload.keywordFourColorDMT };
      }
      if (!this.ontologyGraph.semanticMeta) {
        this.ontologyGraph.semanticMeta = {};
      }
      if (Array.isArray(payload.hierarchy_links)) {
        this.ontologyGraph.semanticMeta.hierarchy_links = payload.hierarchy_links;
      }
    },
    onOntologyKeywordDmtUpdated(payload) {
      if (!payload || !payload.keyword) return;
      const kw = payload.keyword;
      const next = { ...(this.ontologyGraph.keywordFourColorDMT || {}) };
      next[kw] = {
        ...(next[kw] || {}),
        four_color_type: payload.four_color_type || '',
        dmt_level: payload.dmt_level || '',
        knowledge_type: payload.knowledge_type || '',
      };
      this.ontologyGraph.keywordFourColorDMT = next;
      this.ontologyGraph.tribalKeywords = Object.keys(next).filter(
        (k) => String((next[k] || {}).knowledge_type || '').toLowerCase() === 'trib'
      );
    },

    isNotebookPinned(notebook) {
      void this.pinnedNotebookRevision;
      return checkNotebookPinned(notebook.writer, notebook.title);
    },
    handleToggleNotebookPin(notebook, sceneName) {
      const pinned = toggleNotebookPin(notebook.writer, notebook.title, sceneName);
      this.pinnedNotebookRevision += 1;
      this.$message.success(pinned ? '已勾选（可点任务簇「+」加入）' : '已取消勾选');
    },
    showNotebookContextMenu(event, notebook, scene) {
      this.notebookContextMenu = {
        visible: true,
        x: event.clientX,
        y: event.clientY,
        notebook,
        scene,
      };
    },
    handleDocumentClick() {
      this.closeNotebookContextMenu();
      this.showHeaderMoreMenu = false;
    },
    closeNotebookContextMenu() {
      if (this.notebookContextMenu.visible) {
        this.notebookContextMenu.visible = false;
        this.notebookContextMenu.notebook = null;
        this.notebookContextMenu.scene = null;
      }
    },
    contextMenuDoComment() {
      const notebook = this.notebookContextMenu.notebook;
      this.closeNotebookContextMenu();
      if (notebook) {
        this.doComment(notebook);
      }
    },
    removeNotebookFromCluster(nb, cluster) {
      const username = localStorage.getItem('originRealName');
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      const notebookKey = (nb && nb.notebook_key) || '';
      const clusterId = (cluster && cluster.cluster_id) || '';
      if (!notebookKey || !clusterId) {
        this.$message.warning('本子或任务簇信息缺失');
        return;
      }
      adjustTaskClusterNotebook({
        username,
        notebook_key: notebookKey,
        action: 'remove_from_cluster',
        target_cluster_id: clusterId,
      }).then((res) => {
        if (res.error_num === 0) {
          this.applyTaskClusterResult(res);
          this.$message.success('已从此簇移除');
        } else {
          this.$message.error(res.msg || '移除失败');
        }
      }).catch((error) => {
        console.error('从此簇移除失败:', error);
        this.$message.error('移除失败');
      });
    },
    async addPinnedNotebooksToCluster(cluster) {
      const username = localStorage.getItem('originRealName');
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      const clusterId = (cluster && cluster.cluster_id) || '';
      if (!clusterId) {
        this.$message.warning('任务簇信息缺失');
        return;
      }
      const pinned = loadPinnedNotebookKeys();
      if (!pinned.length) {
        this.$message.warning('请先勾选要加入的本子');
        return;
      }
      let ok = 0;
      let fail = 0;
      let lastRes = null;
      for (const item of pinned) {
        const notebookKey = (item.key || `${item.writer || ''}_${item.title || ''}`).trim();
        if (!notebookKey) {
          fail += 1;
          continue;
        }
        try {
          const res = await adjustTaskClusterNotebook({
            username,
            notebook_key: notebookKey,
            action: 'add',
            target_cluster_id: clusterId,
          });
          if (res && res.error_num === 0) {
            ok += 1;
            lastRes = res;
          } else {
            fail += 1;
            console.warn('加入任务簇失败:', notebookKey, res && res.msg);
          }
        } catch (error) {
          fail += 1;
          console.error('加入任务簇失败:', notebookKey, error);
        }
      }
      if (lastRes) {
        this.applyTaskClusterResult(lastRes);
      } else {
        this.loadTaskClusterResult(false);
      }
      if (ok && !fail) {
        this.$message.success(`已将 ${ok} 个勾选本子加入此簇`);
      } else if (ok && fail) {
        this.$message.warning(`成功 ${ok} 个，失败 ${fail} 个`);
      } else {
        this.$message.error('加入失败');
      }
    },
    editClusterField(cluster, field) {
      this.isEditingCluster = true;
      this.isEditingClusterId = cluster.cluster_id;
      this.isEditingClusterField = field;
      this.editedClusterText = field === 'name' ? cluster.cluster_name : cluster.summary;
      this.$nextTick(() => {
        const ref = this.$refs.clusterInputRef;
        const input = Array.isArray(ref) ? ref[0] : ref;
        if (input && input.focus) {
          input.focus();
        }
      });
    },
    saveClusterField(cluster) {
      if (!this.isEditingCluster) {
        return;
      }
      const field = this.isEditingClusterField;
      const text = (this.editedClusterText || '').trim();
      const oldVal = field === 'name' ? cluster.cluster_name : cluster.summary;
      this.isEditingCluster = false;
      this.isEditingClusterId = '';
      this.isEditingClusterField = '';
      if (!text || text === oldVal) {
        return;
      }
      const username = localStorage.getItem('originRealName');
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      const payload = {
        username,
        cluster_id: cluster.cluster_id,
      };
      if (field === 'name') {
        payload.cluster_name = text;
      } else {
        payload.summary = text;
      }
      updateTaskClusterMeta(payload).then((res) => {
        if (res.error_num === 0) {
          this.applyTaskClusterResult(res);
          this.$message.success('已更新任务簇信息');
        } else {
          this.$message.error(res.msg || '更新失败');
        }
      }).catch((error) => {
        console.error('更新任务簇信息失败:', error);
        this.$message.error('更新失败');
      });
    },
    // 加载用户的系统选择
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
      }
    },
    // 切换系统（滑块点击）
    toggleSystem() {
      const newChoice = this.systemChoice === 0 ? 1 : 0
      this.switchToSystem(newChoice)
    },
    // 切换系统
    async switchToSystem(choice) {
      try {
        const { setSystemChoice } = await import('@/api/system')
        const response = await setSystemChoice({
          username: localStorage.getItem('originRealName'),
          choose: choice
        })
        if (response.error_num === 0) {
          this.systemChoice = choice
          localStorage.setItem('systemChoice', choice)
          this.$message.success(`已切换到${choice === 1 ? '快思考(System1)' : '慢思考(System2)'}模式`)
        } else {
          this.$message.error('切换失败: ' + response.msg)
        }
      } catch (error) {
        console.error('切换系统失败:', error)
        this.$message.error('切换失败')
      }
    },

    loadParticlesJS() {
      particlesJS("particles", {
        particles: {
          number: {
            value: 80,
            density: {
              enable: true,
              value_area: 1200,
            },
          },
          color: {
            value: "#ffffff",
          },
          shape: {
            type: "circle",
            stroke: {
              width: 0,
              color: "#000000",
            },
            polygon: {
              nb_sides: 5,
            },
            image: {
              src: "img/github.svg",
              width: 100,
              height: 100,
            },
          },
          opacity: {
            value: 0.5,
            random: false,
            anim: {
              enable: false,
              speed: 1,
              opacity_min: 0.1,
              sync: false,
            },
          },
          size: {
            value: 3,
            random: true,
            anim: {
              enable: false,
              speed: 40,
              size_min: 0.1,
              sync: false,
            },
          },
          line_linked: {
            enable: true,
            distance: 150,
            color: "#ffffff",
            opacity: 0.4,
            width: 1,
          },
          move: {
            enable: true,
            speed: 6,
            direction: "none",
            random: false,
            straight: false,
            out_mode: "out",
            bounce: false,
            attract: {
              enable: false,
              rotateX: 600,
              rotateY: 1200,
            },
          },
        },
        interactivity: {
          detect_on: "canvas",
          events: {
            onhover: {
              enable: true,
              mode: "grab",
            },
            onclick: {
              enable: true,
              mode: "push",
            },
            resize: true,
          },
          modes: {
            grab: {
              distance: 400,
              line_linked: {
                opacity: 1,
              },
            },
            bubble: {
              distance: 400,
              size: 40,
              duration: 2,
              opacity: 8,
              speed: 3,
            },
            repulse: {
              distance: 200,
              duration: 0.4,
            },
            push: {
              particles_nb: 4,
            },
            remove: {
              particles_nb: 2,
            },
          },
        },
        retina_detect: true,
      });
    },
    bookshelf() {
      this.activeButtonIndex = 0
      this.backgroundStyle = 'linear-gradient(-45deg, #542090, #143871, #261137, #5971af)';
    },
    flatlayer() {
      this.activeButtonIndex = 1
      this.backgroundStyle = 'linear-gradient(-45deg, #542090, #143871, #261137, #5971af)';
    },
    openHiddenIntergrowth() {
      this.showHeaderMoreMenu = false;
      this.intergrowth();
    },
    taskClusterNbToShelf(nb) {
      if (!nb) return null;
      return {
        id: nb.id || nb.bookId,
        title: nb.bookName || nb.title,
        description: nb.bookdescription || nb.description,
        writer: nb.writer,
        syncUsers: nb.syncUsers || '',
        cardNum: nb.cardNum || 0,
        isShared: nb.isShared || 0,
      };
    },
    taskClusterSceneOf(nb) {
      if (!nb) return { sid: -1, description: '' };
      const found = this.sceneList.find((scene) => scene.sid === nb.sid);
      if (found) return found;
      return { sid: nb.sid, description: nb.scene_name || '阅读' };
    },
    openTaskClusterNotebook(nb) {
      const shelfNb = this.taskClusterNbToShelf(nb);
      const scene = this.taskClusterSceneOf(nb);
      if (shelfNb && scene) {
        this.openNotebook(shelfNb, scene);
      }
    },
    deleteTaskClusterNotebook(nb) {
      this.deleteNotebook(this.taskClusterNbToShelf(nb), this.taskClusterSceneOf(nb));
    },
    shareTaskClusterNotebook(nb) {
      this.shareNotebook(this.taskClusterNbToShelf(nb), this.taskClusterSceneOf(nb));
    },
    stopTaskClusterProgressPoll() {
      if (this.taskClusterProgressTimer) {
        clearInterval(this.taskClusterProgressTimer);
        this.taskClusterProgressTimer = null;
      }
    },
    startTaskClusterProgressPoll(username) {
      this.stopTaskClusterProgressPoll();
      const poll = () => {
        getTaskClusterProgress({ username }).then((progress) => {
          this.taskClusterProgressPercent = Number(progress.percent) || 0;
          this.taskClusterProgressMessage = progress.message || '';
          this.taskClusterProgressStatus = progress.error_num ? 'exception' : '';
          if (progress.done) {
            this.stopTaskClusterProgressPoll();
            this.taskClusterLoading = false;
            if (Number(progress.error_num) === 0) {
              this.loadTaskClusterResult(false);
              if (this.taskClusterAnalyzeMode === 'incremental') {
                this.$message.success('增量分析完成');
              } else if (this.taskClusterAnalyzeMode === 'full') {
                this.$message.success('任务簇已重新分析');
              } else {
                this.$message.success('任务簇分析完成');
              }
            } else {
              this.$message.error(progress.msg || progress.message || '任务簇分析失败');
            }
          }
        }).catch((error) => {
          console.error('轮询任务簇进度失败:', error);
        });
      };
      poll();
      this.taskClusterProgressTimer = setInterval(poll, 1200);
    },
    applyTaskClusterResult(data) {
      this.taskClusterResult = {
        processed: true,
        clusters: data.clusters || [],
        unclustered: data.unclustered || [],
        analyzed_at: data.analyzed_at || '',
        model: data.model || '',
        notebook_count: data.notebook_count || 0,
      };
    },
    taskClusterView() {
      this.activeButtonIndex = 2;
      this.backgroundStyle = 'linear-gradient(-45deg, #542090, #143871, #261137, #5971af)';
      this.loadTaskClusterResult(true);
    },
    loadTaskClusterResult(autoAnalyzeIfMissing = false) {
      const username = localStorage.getItem('originRealName');
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      getTaskClusterProgress({ username }).then((progress) => {
        if (progress.running && !progress.done) {
          this.taskClusterLoading = true;
          this.taskClusterProgressPercent = Number(progress.percent) || 0;
          this.taskClusterProgressMessage = progress.message || '分析进行中…';
          this.startTaskClusterProgressPoll(username);
        }
      }).catch(() => {});

      getTaskCluster({ username }).then((data) => {
        if (data.error_num === 0 && data.processed) {
          this.applyTaskClusterResult(data);
        } else if (autoAnalyzeIfMissing && !this.taskClusterLoading) {
          this.runTaskClusterAnalyze(false);
        } else if (!this.taskClusterLoading) {
          this.taskClusterResult = {
            processed: false,
            clusters: [],
            unclustered: [],
            analyzed_at: '',
            model: '',
            notebook_count: 0,
          };
        }
      }).catch((error) => {
        console.error('加载任务簇失败:', error);
        this.$message.error('加载任务簇失败');
      });
    },
    runTaskClusterAnalyze(force, mode) {
      const username = localStorage.getItem('originRealName');
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      if (this.taskClusterLoading) {
        return;
      }
      const analyzeMode = mode || 'full';
      this.taskClusterAnalyzeMode = analyzeMode;
      this.taskClusterLoading = true;
      this.taskClusterProgressPercent = 0;
      this.taskClusterProgressMessage = '正在启动分析…';
      this.taskClusterProgressStatus = '';
      analyzeTaskCluster({ username, force: !!force, mode: analyzeMode }).then((data) => {
        if (Number(data.error_num) !== 0) {
          this.taskClusterLoading = false;
          this.$message.error(data.msg || '任务簇分析失败');
          return;
        }
        if (data.incremental_skipped) {
          this.applyTaskClusterResult(data);
          this.taskClusterLoading = false;
          this.$message.info(data.msg || '没有需要增量分析的本子');
          return;
        }
        if (data.processed && data.clusters) {
          this.applyTaskClusterResult(data);
          this.taskClusterLoading = false;
          if (data.from_cache) {
            return;
          }
          if (force && analyzeMode === 'incremental') {
            this.$message.success('增量分析完成');
          } else if (force) {
            this.$message.success('任务簇已重新分析');
          } else {
            this.$message.success('任务簇分析完成');
          }
          return;
        }
        if (data.started || data.running) {
          this.startTaskClusterProgressPoll(username);
          return;
        }
        this.taskClusterLoading = false;
      }).catch((error) => {
        console.error('任务簇分析失败:', error);
        this.taskClusterLoading = false;
        this.$message.error('任务簇分析失败');
      });
    },
    confirmRerunTaskClusterAnalyze() {
      if (this.taskClusterLoading) {
        return;
      }
      this.rerunTaskClusterMode = 'incremental';
      this.showRerunTaskClusterDialog = true;
    },
    confirmRerunTaskClusterAnalyzeSubmit() {
      const mode = this.rerunTaskClusterMode || 'full';
      this.showRerunTaskClusterDialog = false;
      this.runTaskClusterAnalyze(true, mode);
    },
    openCreateTaskClusterDialog() {
      this.createTaskClusterName = '';
      this.createTaskClusterSummary = '';
      this.showCreateTaskClusterDialog = true;
    },
    confirmCreateTaskCluster() {
      const username = localStorage.getItem('originRealName');
      if (!username) {
        this.$message.warning('请先登录');
        return;
      }
      const name = (this.createTaskClusterName || '').trim();
      const summary = (this.createTaskClusterSummary || '').trim();
      if (!name) {
        this.$message.warning('请输入任务簇名称');
        return;
      }
      if (!summary) {
        this.$message.warning('请填写一句话描述');
        return;
      }
      createTaskCluster({
        username,
        cluster_name: name,
        summary,
      }).then((res) => {
        if (res.error_num === 0) {
          this.applyTaskClusterResult(res);
          this.showCreateTaskClusterDialog = false;
          this.$message.success('已新增任务簇');
        } else {
          this.$message.error(res.msg || '新增失败');
        }
      }).catch((error) => {
        console.error('新增任务簇失败:', error);
        this.$message.error('新增失败');
      });
    },
    confirmDeleteTaskCluster(cluster) {
      if (!cluster || !cluster.cluster_id) {
        return;
      }
      const nbCount = (cluster.notebooks || []).length;
      const tip = nbCount
        ? `确定删除任务簇「${cluster.cluster_name}」吗？仅删除分类，不会删除本子；其中 ${nbCount} 个本子将移入「未强关联入簇的本子」。`
        : `确定删除空任务簇「${cluster.cluster_name}」吗？`;
      this.$confirm(tip, '确认删除任务簇', {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning',
      }).then(() => {
        const username = localStorage.getItem('originRealName');
        if (!username) {
          this.$message.warning('请先登录');
          return;
        }
        deleteTaskCluster({
          username,
          cluster_id: cluster.cluster_id,
        }).then((res) => {
          if (res.error_num === 0) {
            this.applyTaskClusterResult(res);
            this.$message.success('任务簇已删除');
          } else {
            this.$message.error(res.msg || '删除失败');
          }
        }).catch((error) => {
          console.error('删除任务簇失败:', error);
          this.$message.error('删除失败');
        });
      }).catch(() => {});
    },
    intergrowth() {
      this.backgroundStyle = 'linear-gradient(-45deg, #1c7243, #10513c, #16673c, #0d7c46)';
      const username = localStorage.getItem('originRealName');
      this.activeButtonIndex = 4;
      if (username) {
        this.initPersonalInfo();
        this.getSubordinates();
      }
    },
    // 判断是否需要显示组本待办红色感叹号
    isInTodoList(notebook) {
      if (!notebook.syncTodo) return false;
      
      const currentUser = localStorage.getItem('originRealName');
      const todoUsers = notebook.syncTodo.split(',').map(user => user.trim());
      
      return todoUsers.includes(currentUser);
    },

    getOnlineNum() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      get_onlineNum(formData).then(data => {
        if(data['error_num'] === 0) {
          this.onlineUsername = data['onlineUsername']
          this.onlineUserBookName = data['onlineUserBookName']
          console.log("在线用户，本子：", this.onlineUsername, this.onlineUserBookName)
          if (this.onlineUsername.includes(this.selectedSubordinate)) {
            this.onlinestatus = '在线'
          } else {
            this.onlinestatus = '离线'
          }
        }
        let formFirstData = new FormData();
        formFirstData.append('username', this.selectedSubordinate);
        getFirstBookByName(formFirstData).then(data => {
          if(data['error_num'] === 0) {
            this.firstBook = {
              username: data['firstBook'].username,
              bookId: Number(data['firstBook'].bookId), // 转换为整数
              bookName: data['firstBook'].bookName,
              bookdescription: data['firstBook'].bookdescription,
              comments: data['firstBook'].comments,
              context_data: data['firstBook'].context_data,
              isShared: Number(data['firstBook'].isShared), // 转换为整数
              sid: Number(data['firstBook'].sid) // 转换为整数
            };
          }
        })
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    
    // 初始化个人信息和下属用户列表
    initPersonalInfo() {
      this.myLevel = this.curLevel;
      this.myCoacher = this.curCoacherName;
      this.selectedNewLevel = this.curLevel;
      this.newCoacher = this.curCoacherName;
    },

    getSubordinates() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      getSubordinatesList(formData).then(response => {
        if (response.error_num === 0) {
          this.subordinateUsers = response.subordinates;
          this.$message.success('操作成功');
        } else {
          this.$message.error('操作失败');
        }
      }).catch(error => {
        console.error("获取下属列表失败:", error); // 错误处理
        this.$message.error('操作失败');
      });
    },

    updateLevel() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      formData.append('new_level', this.selectedNewLevel);

      updateUserLevel(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('层级更新成功');
          this.myLevel = this.selectedNewLevel;
        } else {
          this.$message.error(response.msg || '层级更新失败');
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
        this.$message.error('操作失败');
      });
    },

    updateCoacher() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      formData.append('new_coacher', this.newCoacher);
      updateUserCoacher(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('领航员更新成功');
          this.myCoacher = this.newCoacher;
        } else {
          this.$message.error(response.msg || '领航员更新失败');
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
        this.$message.error('操作失败');
      });
    },

    

    editDescription(notebook) {
      // if(notebook.writer !== localStorage.getItem('originRealName') && notebook.writer !== "" && notebook.syncUsers !== "") {
      //   this.$message.error('您不是作者，没有权限修改此群组共享本子名');
      //   return
      // }
      this.isEditing = true;
      this.isEditingBookTitle = notebook.title
      this.isEditingBookWriter = notebook.writer
      this.editedDescription = notebook.description;
      // 聚焦到输入框
      this.$nextTick(() => {
        const inputRef = this.$refs.inputRef;
        if (inputRef) {
          console.log("正在聚焦")
          // 要用下面的方式才可以，不能inputRef.focus()
          const inputElement = document.querySelector('.bookDescriptionEdit');
          inputElement.focus();
        }
      });
    },
    saveDescription(notebook) {
      // this.notebook.description = this.editedDescription;
      this.isEditing = false;
      let formData = new FormData();
      // formData.append('username', localStorage.getItem('originRealName'));
      formData.append('username', notebook.writer);
      formData.append('bookname', notebook.title);
      formData.append('editedDescription', this.editedDescription)
      updateBookDescri(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('已更新本子说明');
          notebook.description = this.editedDescription
        } else {
          this.$message.error('更新本子说明失败');
        }
      });
    },
    saveDescriptionPingpu(notebook) {
      this.isEditing = false;
      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      formData.append('bookname', notebook.title);
      formData.append('editedDescription', this.editedDescription)
      updateBookDescri(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('已更新本子说明');
          notebook.description = this.editedDescription
          for (let sceneKey in this.notebooks) {
            if (this.notebooks.hasOwnProperty(sceneKey)) {
              const notebooksInScene = this.notebooks[sceneKey];
              for (let notebookSingle of notebooksInScene) {
                if (notebookSingle.title === notebook.title) {
                  notebookSingle.description = this.editedDescription
                }
              }
            }
          }
        } else {
          this.$message.error('更新本子说明失败');
        }
      });
    },
    // 共生型中，也有最近使用是群组本子的问题，而获取firstBook暂未包括自己不是作者的群组本子在内，后续再考虑
    doIntergrowthComment() {
      this.showCommentDialog = true
      this.comments = this.firstBook.comments
      this.commentBookName = this.firstBook.bookName
      let formData = new FormData();
      formData.append('username', this.firstBook.username);
      formData.append('bookname', this.commentBookName);
      getComment(formData).then(response => {
        if (response.error_num === 0) {
          this.comments = response.comments
          this.$message.success('获取留言评论成功');
        } else {
          this.$message.error('获取留言评论失败');
        }
      });
    },
    doComment(notebook) {
      this.showCommentDialog = true
      this.comments = notebook.comments
      this.commentBookName = notebook.title
      let formData = new FormData();
      // 群组本子，并非自己的，获取作者本子的留言
      if(notebook.syncUsers !== "") {
        formData.append('username', notebook.writer);
        this.updateCommentsBook = notebook
      } else {
        formData.append('username', localStorage.getItem('originRealName'));
      }
      formData.append('bookname', this.commentBookName);
      getComment(formData).then(response => {
        if (response.error_num === 0) {
          this.comments = response.comments
          this.$message.success('获取留言评论成功');
        } else {
          this.$message.error('获取留言评论失败');
        }
      });
    },
    updateComments() {
      let formData = new FormData();
      // else共生型中，也有最近使用是群组本子的问题，而获取firstBook暂未包括自己不是作者的群组本子在内，后续再考虑
      if(this.activeButtonIndex === 0 || this.activeButtonIndex === 1) {
        // 群组本子，并非自己的，获取作者本子的留言
        if(this.updateCommentsBook !== null)
          formData.append('username', this.updateCommentsBook.writer);
        else
          formData.append('username', localStorage.getItem('originRealName'));
        formData.append('bookname', this.commentBookName);
      } else {
        formData.append('username', this.firstBook.username);
        formData.append('bookname', this.firstBook.bookName);
      }
      formData.append('comments', this.comments);
      updateComment(formData).then(response => {
        this.updateCommentsBook = null
        if (response.error_num === 0) {
          this.$message.success('留言评论更新成功');
        } else {
          this.$message.error('留言评论更新失败');
        }
      });
    },
    findSceneByNotebook(notebook, sceneList) {
      return sceneList.find(scene => scene.description === notebook.scene);
    },
    needDemoBtn(sceneId) {
      // 获取选择的scene对象，返回是否需要demo
      const selectedSceneObject = this.sceneList.find(scene => scene.sid === sceneId);
      return selectedSceneObject ? selectedSceneObject.needDemo : false;
    },
    yesImportDoc() {
      this.showDocButton = true;
      this.showDialog3 = false;
    },
    importDoc() {
      this.$refs.docInput.click();
      this.showDialog2 = false;
    },
    importPrompt() {
      if (this.sceneForm.description.trim() == "") {
        alert("场景名称不能为空");

      } else {
        addScene(this.curUserName, this.sceneForm.description).then(response => {
          if (response.error_num === 0) {
            // this.clearSceneList();
            // this.updateSceneList();
            // this.showDialog2=false;

            this.$refs.fileInput.click();
            // this.$message.success('添加成功');
          } else if (response.error_num === 2) {
            alert("场景名重复，不可创建！");
            this.showDialog2 = false;

          }
          // this.updateNoteBookList();
        })

      }


    },
    handleFileChange(e) {
      // 真牛逼我服了
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          console.log("File read as data URL");
          const fileData = e.target.result.split(',')[1]; // 获取文件的数据，去除前缀
          let formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          formData.append('sname', this.sceneForm.description);
          // formData.append('filename', file.name);
          formData.append('file', fileData); // 添加文件数据到 FormData
          saveSceneExcel(formData).then(response => {
            console.log("场景新建: ", response)
            if (response.error_num === 0) {
              localStorage.setItem('subSceneList', response['subSceneList']);
              this.showDialog3 = true;
            }
          })
          // alert(file.name);
          // console.log(formData);
          // ... 其他代码 ...
        };
        // reader.onerror = (error) => {
        //   console.error("File read error: ", error);
        // };
        try {
          reader.readAsDataURL(file); // 读取文件内容，以Base64编码的形式
        } catch (e) {
          console.error("Exception during readAsDataURL: ", e);
        }
      }
      this.$message.success('场景添加成功');
    },
    handleFileChange2(e) {
      const files = e.target.files; // 获取FileList对象
      if (files.length === 0) {
        console.log("没有文件被选中");
        return;
      }
      this.dfs(files, 0, files.length)
      // 遍历所有选中的文件
    },

    dfs(files, curI, finalI) {
      if (curI === finalI) {
        let okFormData = new FormData();
        okFormData.append('sceneName', this.sceneForm.description);
        okFormData.append('havefile', '1');
        saveSceneDocOK(okFormData).then(data => {
          this.clearSceneList();
          this.updateSceneList();
        });
        this.$message.success('文件添加成功');
        console.log("场景预设文件已经上传解析结束")
        return;
      }// 获取文件的数据，去除前缀

      const file = files[curI];
      if (file) {
        const reader = new FileReader();
        reader.onload = (e) => {
          const fileData = e.target.result.split(',')[1]; // 获取文件的数据，去除前缀
          let formData = new FormData();
          formData.append('username', localStorage.getItem('userId'));
          formData.append('sname', this.sceneForm.description);
          formData.append('filename', file.name); // 如果需要文件名，取消注释这行
          formData.append('file', fileData); // 添加文件数据到 FormData
          // 保存场景，您可以在这里调用您的API
          saveSceneDoc(formData).then(data => {
            this.dfs(files, curI + 1, finalI);
          });
        };
        reader.readAsDataURL(file); // 读取文件内容，以Base64编码的形式
      }

    },
    handleSelect() {
      // alert(this.selectedScene);
      // this.updateNoteBookList();
      // 下为 lyf 注释
      // const selectedSceneObject = this.sceneList.find(scene => scene.sid === this.selectedScene);
      // this.selectedName = selectedSceneObject ? selectedSceneObject.description : '';
      // localStorage.setItem('sceneName', this.selectedName);
      // 1. 转到书架型
      this.bookshelf()

      // 2. 等待DOM更新后再滚动
      this.$nextTick(() => {
        // 查找选中场景对应的场景包装器
        const selectedSceneElement = Array.from(document.querySelectorAll('.scene-wrapper'))
          .find(wrapper => {
            const sceneTitle = wrapper.querySelector('h1');
            const scene = this.sceneList.find(s => s.sid === this.selectedScene);
            return scene && sceneTitle && sceneTitle.textContent.includes(scene.description);
          });

        // 如果找到元素，则滚动到该位置
        if (selectedSceneElement) {
          selectedSceneElement.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start'
          });
        }
      });
    },
    updateSceneList() {
      getSceneByName(this.curUserName).then(response => {
        if (response.error_num === 0) {
          for (let i = response['scene_without_demo'].length - 1; i >= 0; i--) {
            const ele = response['scene_without_demo'][i];
            const curSceneWithoutDemo = {
              sid: ele.pk,
              description: ele.fields['sceneDescription'],
              needDemo: true,
            };
            // alert(ele.pk);
            this.sceneList.push(curSceneWithoutDemo);
          }

          for (let i = response['list'].length - 1; i >= 0; i--) {
            const ele = response['list'][i];
            const curScene = {
              sid: ele.pk,
              description: ele.fields['sceneDescription'],
              needDemo: false,
            };
            // alert(ele.pk);
            this.sceneList.push(curScene);
          }

          // 初始化 notebooks 键值列表，初始化demo笔记本名，并获取所有场景下的笔记本
          this.sceneList.forEach(scene => {
            this.notebooks[scene.description] = [];
            this.demoBookNames[scene.description] = "";
          });
          this.updateNoteBookList();
        }
        else {

        }
        // alert("2");
      }).catch(error => {
        alert("error1");
        console.log('error', error.message);
      })
    },
    cancelDialog() {
      this.showDialog = false;
      this.notebookForm.title = '';
      this.notebookForm.description = '';
    },
    cancelDialog2() {
      this.showDialog3 = false;
      this.showDialog2 = false;
      let formData = new FormData();
      console.log(formData);
      formData.append('sceneName', this.sceneForm.description);
      formData.append('havefile', '0');
      saveSceneDocOK(formData).then(data => {
        this.clearSceneList();
        this.updateSceneList();
      });
    },
    showCreateDialog(scene) {
      this.selectedScene = scene.sid
      this.selectedName = scene.description
      this.showDialog = true;
    },
    showCreateDialog2() {
      this.showDialog2 = true;
    }
    ,
    showName() {
      alert(this.curUserName);
      // this.updateNoteBookList();
    },
    addBook2Database(row) {
      addBook(this.curUserName, Date.now(), this.bookName.trim(), this.des, this.selectedScene, this.selectedName).then(response => {
        if (response.error_num === 0) {
          let uname = localStorage.getItem('userId') + '_' + this.bookName;
          localStorage.setItem('userId', uname);
          localStorage.setItem('sceneName', this.selectedName);
          localStorage.setItem('subSceneList', response['subSceneList']);
          router.push('/main')
        } else if (response.error_num === 1) {
          this.$message.error('添加失败，您可以尝试重新登录或重试');
          this.notebooks[this.selectedName].splice(this.notebooks[this.selectedName].findIndex(item => item.id === row.id), 1);
          this.showOpenBookButton = true;
        } else {
          this.$message.error('添加失败，您的所有笔记本不能重名！请检查您所有场景的笔记本');
          this.notebooks[this.selectedName].splice(this.notebooks[this.selectedName].findIndex(item => item.id === row.id), 1);
          this.showOpenBookButton = true;
        }
        // this.updateNoteBookList();
      })
    },
    // clearNotebook() {
    //   if (this.notebooks.length >= 1) {
    //     this.notebooks.splice(0, this.notebooks.length);
    //   }
    // },
    shouldShowLoadIcon(scene) {
      // 如果是前8个场景，且该场景的笔记本总数大于4个，则显示加载图标
      return this.notebookTotalCounts[scene.description] > this.bookNumLimit;
    },
    clearSceneList() {
      if (this.sceneList.length >= 1) {
        this.sceneList.splice(0, this.sceneList.length);
      }
    },
    loadSpecificScene(scene) {
      this.loading = true;
      // 修改 loadSpecificScene 方法中的调用（不传limit，加载全部）
      getBookListByName(this.curUserName, scene.sid).then(response => {
        if (response.error_num === 0) {
          // 清空该场景原有的笔记本列表
          this.notebooks[scene.description] = [];
          
          for (const ele of response['list']) {
            const newNotebook = {
              id: ele.fields['bookId'],
              title: ele.fields['bookName'],
              description: ele.fields['bookdescription'],
              isShared: ele.fields['isShared'],
              comments: ele.fields['comments'],
              context_data: ele.fields['context_data'],
              cardNum: ele.fields['cardNum'],
              writer: ele.fields['writer'],
              syncUsers: ele.fields['syncUsers'],
              syncTodo: ele.fields['syncTodo']
            };
            this.notebooks[scene.description].push(newNotebook);
            this.demoBookNames[scene.description] = response.demoBookName;
          }
          this.$message.success(`${scene.description}场景笔记本加载成功`);
        } else {
          let msg = response.msg;
          this.$message.error(`${scene.description}场景笔记本加载失败: ${msg}`);
        }
        this.loading = false;
      }).catch(error => {
        this.$message.error(`场景笔记本加载失败Error: ${error}`);
        this.loading = false;
        console.log('error', error.message);
      });
    },
    updateNoteBookList() {
      this.loading = true
      // 获取前8个场景（如果少于8个则获取全部）
      const scenesToLoad = this.sceneList.length > this.sceneNumLimit ? this.sceneList.slice(0, this.sceneNumLimit) : this.sceneList;
      let count = 0
      for (const scene of scenesToLoad) {
        // 修改 updateNoteBookList 方法中的调用，预加载前4个
        getBookListByName(this.curUserName, scene.sid, this.bookNumLimit).then(response => {
          if (response.error_num === 0) {
            // 记录总数
            this.notebookTotalCounts[scene.description] = response.totalCount || 0;
            // this.clearNotebook();
            for (const ele of response['list']) {
              const newNotebook = {
                id: ele.fields['bookId'], // 生成唯一ID
                title: ele.fields['bookName'],
                description: ele.fields['bookdescription'],
                isShared: ele.fields['isShared'],
                comments: ele.fields['comments'],
                context_data: ele.fields['context_data'],
                cardNum: ele.fields['cardNum'],
                writer: ele.fields['writer'],
                syncUsers: ele.fields['syncUsers'],
                syncTodo: ele.fields['syncTodo']
              };
              
              // 快速检查大字段
              const sizes = Object.entries(newNotebook).map(([key, value]) => ({
                field: key,
                size: new Blob([JSON.stringify(value)]).size
              })).sort((a, b) => b.size - a.size);
              console.log(`📖 ${newNotebook.title}: 最大字段 - ${sizes[0].field}(${sizes[0].size}字节), ${sizes[1].field}(${sizes[1].size}字节)`);

              this.notebooks[scene.description].push(newNotebook);
              this.demoBookNames[scene.description] = response.demoBookName;
            }
            this.$message.success(`${scene.description}场景笔记本加载成功`);
            // 检查是否是最后一个元素
            count += 1
            if (count === scenesToLoad.length)
              this.loading = false
          }
          else {
            msg = response.msg
            this.$message.error(`${scene.description}场景笔记本加载失败: ${msg}`);
            this.loading = false
          }
        }).catch(error => {
          this.$message.error(`场景笔记本加载失败Error: ${error}`);
          this.loading = false
          console.log('error', error.message);
        })
      }
      console.log("所有场景的本子列表", this.notebooks)
    },

    // 处理从对话框发出的创建笔记本事件（已废弃）
    handleNotebookCreated(notebookData) {      // 创建新的笔记本并更新列表
      const newNotebook = {
        id: Date.now(), // 生成唯一ID
        title: notebookData.title,
        description: notebookData.description
      };
      this.notebooks.push(newNotebook);
      this.createDialogVisible = false; // 关闭对话框
    },

    createNewNotebook() {
      // 这里应该调用API来创建新的笔记本（已废弃）
      const newNotebook = {
        id: this.notebooks.length + 1,
        title: `新笔记本 ${this.notebooks.length + 1}`,
        description: '这是一个新创建的笔记本。'
      };
      this.notebooks.push(newNotebook);
    },

    createNewScene: function () {
      if (this.sceneForm.description.trim() == "") {
        alert("场景名称不能为空");
        return 0;
      }
      else {
        addScene(this.curUserName, this.sceneForm.description).then(response => {
          // alert(response.error_num);
          if (response.error_num === 0) {
            this.clearSceneList();
            this.updateSceneList();
            this.showDialog2 = false;
            return 1;
          } else if (response.error_num === 2) {
            alert("场景名重复，不可创建！");
            this.showDialog2 = false;
            return 0;
          }
          // this.updateNoteBookList();
        })
        // this.clearSceneList();
        // this.updateSceneList();
        // this.showDialog2=false;
        // alert(this.success);
        // return this.success;
      }
    },
    validateCollectionName(name) {
      const rules = [
        { rule: /^.{2,30}$/, message: "长度必须在2到30个字符之间" },
        { rule: /^[a-zA-Z0-9].*[a-zA-Z0-9]$/, message: "必须以字母或数字开头和结尾" },
        { rule: /^[a-zA-Z0-9](?:[a-zA-Z0-9_-]*[a-zA-Z0-9_-])?$/, message: "中间只能包含字母、数字、下划线或连字符" },
        // 可以继续添加其他规则
      ];

      for (let i = 0; i < rules.length; i++) {
        if (!rules[i].rule.test(name)) {
          return { valid: false, message: rules[i].message };
        }
      }
      // 如果所有规则都通过
      return { valid: true, message: "名称有效" };
    },
    addNewNotebook: function () {
      this.bookName = this.notebookForm.title;
      this.des = this.notebookForm.description;
      if (this.bookName.trim() == "" || this.des.trim() == "") {
        this.$message.error("笔记本名称和描述不能为空");
      } else if (this.validateCollectionName(this.bookName.trim()).valid === false) {
        this.$message.error("笔记本名称格式有误:" + this.validateCollectionName(this.bookName.trim()).message);
      } else {
        this.showOpenBookButton = false;
        const row =
        {
          id: Date.now(),
          title: this.bookName.trim(),
          description: this.des,
        };
        this.notebooks[this.selectedName].push(row);
        this.addBook2Database(row);
        this.showDialog = false;
      }
    },
    openIntergrowthBookOperation() {
      localStorage.setItem('firstBookUser', this.firstBook.username);
      localStorage.setItem('firstBookName', this.firstBook.bookName);
      localStorage.setItem('firstBookContext', this.firstBook.context_data);
      localStorage.setItem('controlled', 'false');
      router.push('/live');
    },
    openIntergrowthBookSelf() {
      localStorage.setItem('coacherNameOrigin', localStorage.getItem('coacherName'));
      localStorage.setItem('coacherName', localStorage.getItem('originRealName'));
      localStorage.setItem('level', this.level_hierarchy_down[this.curLevel]);

      localStorage.setItem('userId', this.selectedSubordinate);
      localStorage.setItem('realName', this.selectedSubordinate);
      localStorage.setItem('originRealName', this.selectedSubordinate);
      localStorage.setItem('byuplevel', 'true');
      localStorage.setItem('fromPath', '/home')
      router.push('/simple');
    },

    handleProgressClose() {
      console.log("关闭打开本子进度条")
      this.stopProgressPolling();
      this.loading = false;
      this.showProgress = false;
    },

    // 开始轮询进度
    startProgressPolling() {
      this.progressInterval = setInterval(() => {
        this.checkProgress();
      }, 2000); // 每2秒检查一次进度
    },
    
    // 停止轮询
    stopProgressPolling() {
      if (this.progressInterval) {
        clearInterval(this.progressInterval);
        this.progressInterval = null;
      }
    },
    
    // 检查进度
    checkProgress() {
      if (!this.progressId) return;
      
      // 调用检查进度API
      check_load_progress(this.progressId).then(response => {
        this.loadProgress = response.progress;
        this.progressMessage = response.message;
        
        // 根据状态更新进度条样式
        if (response.status === 'completed') {
          this.progressStatus = 'success';
          this.stopProgressPolling();
          

          // 延迟一小段时间后跳转，让用户看到100%的进度
          setTimeout(() => {
            this.showProgress = false;
            this.loading = false;
            setTimeout(() => {
              router.push('/main');
            }, 500);
          }, 500);
        } else if (response.status === 'error') {
          this.progressStatus = 'exception';
          this.$message.error('加载错误: ' + response.message);
          this.stopProgressPolling();
          this.loading = false;
        }
      })
      .catch(error => {
        console.error('检查进度失败:', error);
        this.progressStatus = 'exception';
        this.progressMessage = '检查进度失败';
      });
    },

    openNotebook: function (notebookData, scene) {
      this.showProgress = true;
      this.loadProgress = 0;
      this.progressMessage = '准备加载用户数据...';

      let isInCurBookTodoList = this.isInTodoList(notebookData)
      console.log("当前我是否在此本子的syncTodo名单中: ", isInCurBookTodoList)
      localStorage.setItem('isInCurBookTodoList', isInCurBookTodoList);

      const notebook = {
        id: notebookData.id,
        title: notebookData.title,
        description: notebookData.description,
        writer: notebookData.writer,
        syncUsers: notebookData.syncUsers
      };

      // 存储当前本子信息到localStorage，供其他组件使用
      localStorage.setItem('currentNotebook', JSON.stringify(notebook));
      
      this.selectedName = scene.description
      localStorage.setItem('sceneName', this.selectedName);

      // 进入群组共享本子, 获取与作者相同层级的用户列表，以便后续判断卡片共生区域如何显示
      if (notebook.syncUsers !== "") {
        let formData = new FormData();
        formData.append('username', notebook.writer);
        formData.append('syncUsers', notebook.syncUsers);
        get_same_level_users(formData).then(response => {
          if (response.error_num === 0) {
            // 将相同层级用户列表存储到localStorage
            localStorage.setItem('sameLevelUsers', JSON.stringify(response.same_level_users));
            localStorage.setItem('writerCoacher', response.user_coacher);
            // localStorage.setItem('currentUserLevel', response.current_level);
            console.log("相同层级用户列表:", response.same_level_users);
            console.log("作者用户层级:", response.current_level);
          } else {
            console.error('获取相同层级用户失败:', response.msg);
            localStorage.setItem('sameLevelUsers', JSON.stringify([]));
            localStorage.setItem('writerCoacher', '');
          }
        }).catch(error => {
          console.error('获取相同层级用户出错:', error);
          localStorage.setItem('sameLevelUsers', JSON.stringify([]));
          localStorage.setItem('writerCoacher', '');
        });
      } else {
        // 如果不是组本，清空相关数据
        localStorage.setItem('sameLevelUsers', JSON.stringify([]));
        localStorage.setItem('writerCoacher', '');
      }

      setTimeout(() => {
        // 进入本子，默认非组本(用下级用户数置0来代替此判断)，非组本不需要卡片共生区
        localStorage.setItem('downLevelNum', 0)
        // 进入群组共享本子，自己或别人是作者
        if(notebook.syncUsers !== "") {
          localStorage.setItem('realName', notebook.writer)
        }
        console.log("组本作者和当前登录者", notebook.writer, localStorage.getItem('originRealName'))
        // 进入群组共享本子，自己是作者，需要知道几个用户回复后卡片共生区变绿，用内存保存下级用户数(不一定全部加入了协作)
        const sameLevelUsers = JSON.parse(localStorage.getItem('sameLevelUsers') || '[]');
        if(notebook.syncUsers !== "" && (notebook.writer === localStorage.getItem('originRealName') || localStorage.getItem('originRealName') === localStorage.getItem('writerCoacher') || sameLevelUsers.includes(localStorage.getItem('originRealName')) )) {
          this.initPersonalInfo();
          // this.getSubordinates();
          // 分割字符串并去除空白
          const users = notebook.syncUsers.split(',').map(user => user.trim()).filter(user => user);
          let count = users.length;

          // if (this.myCoacher && users.includes(this.myCoacher))
          //   count = count - 1
          // if (localStorage.getItem('originRealName') === localStorage.getItem('writerCoacher') && users.includes(localStorage.getItem('originRealName')))
          //   count = count - 1
          if (users.includes(localStorage.getItem('writerCoacher')))
            count = count - 1
          // 获取作者相同层级用户列表，并从计数中去除同级用户
          for (let sameLevelUser of sameLevelUsers) {
            if (users.includes(sameLevelUser)) {
              count = count - 1;
            }
          }
          console.log("组本协作者下级人数：", count)
          localStorage.setItem('downLevelNum', count)
        }
        let uname = localStorage.getItem('realName') + '_' + notebook.title;
        let originRealName = localStorage.getItem('originRealName') + '_' + notebook.title;
        
        console.log('openNotebook selectName:', this.selectedName);
        // 获取进度ID并开始轮询进度
        makeAndGetProgressId().then(response => {
          this.progressId = response.progress_id;
          setTimeout(() => {
            // 延迟一会再开始轮询试试，给后端少一点压力
            this.startProgressPolling();
          }, 1400);

          loadUser(originRealName, uname, this.selectedName, this.progressId).then(response => {
            if (response.error_num === 0) {
              localStorage.setItem('userId', uname);
              localStorage.setItem('subSceneList', response['subSceneList']);
              let time = Date.now()
              localStorage.setItem('time', time);
              localStorage.setItem('fromPath', '/main')
              // router.push('/main')

              let formData = new FormData();
              formData.append('userName', localStorage.getItem('realName'));
              formData.append('bookName', notebook.title);
              formData.append('newTime', time);
              updateBookTime(formData).then(response => {
                if (response.error_num === 0) {
                  this.$message.success('笔记本时间更新成功');
                } else {
                  this.$message.error('笔记本时间更新失败');
                }
              });
            }
            else {
              throw new Error(response.msg || '打开本子失败');
            }
          }).catch(error => {
            this.stopProgressPolling();
            this.showProgress = false;
            this.loading = false;
            this.$message.error('打开失败: ' + error.message);
            console.log(error);
          });
        }).catch(error => {
          console.log(error);
        });
        // localStorage.setItem('userId', uname);
        // router.push('/main');
      }, 400);
    },

    deleteNotebook(notebook, scene) {
      // 普通的分享（复制）本子是可以删掉的，因为复制本子不复制syncUsers
      if(notebook.writer !== localStorage.getItem('originRealName') && notebook.writer !== "" && notebook.syncUsers !== "") {
        this.$message.error('您不是作者，没有权限删除此群组共享本子');
        return
      }

      // 🔥 添加确认弹框
      this.$confirm('确定要删除这个笔记本吗？此操作不可恢复，将删除所有相关卡片和向量数据。', '确认删除', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        // 在计算索引之前，移除 notebook 中的 scene 属性，深拷贝
        const cleanNotebook = JSON.parse(JSON.stringify(notebook));
        delete cleanNotebook.scene;
        const index = this.notebooks[scene.description].findIndex((nb, idx) => {
          return Object.keys(cleanNotebook).every(key => {
            return nb[key] === cleanNotebook[key];
          });
        });
        // const index = this.notebooks[scene.description].indexOf(cleanNotebook);
        console.log("位置", index)
        if (index > -1) {
          this.notebooks[scene.description].splice(index, 1);
        }
        deleteBook(this.curUserName, notebook.id).then(response => {
          if (response.error_num === 0) {
            this.$message.success('删除成功');
          } else {
            this.$message.error('删除失败');
          }
        })
      }).catch(() => {
        // 用户取消删除，不做任何操作
      });
    },
    shareNotebook(notebook, scene) {
      // if(notebook.writer !== localStorage.getItem('originRealName') && notebook.writer !== "" && notebook.syncUsers !== "") {
      //   this.$message.error('您不是作者，暂时没有权限扩散此群组共享本子');
      //   return
      // }

      this.selectedName = scene.description
      this.selectedScene = scene.sid
      this.shareDialogVisible = true
      this.sharedBookName = notebook.title
      this.shareMode = 0  // 原先默认分享（复制），手动改共享

      this.notebookToBeShared = notebook
      this.changeShareMode() // 现在点分享时，共享为默认逻辑
    },
    shareDemoNotebook(notebook, scene) {
      this.selectedName = scene.description
      this.selectedScene = scene.sid
      uploadDemoNotebook(this.curUserName, notebook.title, this.selectedScene, this.selectedName).then(response => {
        if (response.error_num === 0) {
          this.$message.success('发布成功');
        }
        else {

        }
      });
    },

    changeShareMode() {
      this.shareMode = 1
      if(this.notebookToBeShared.syncUsers === "") {
        const username = localStorage.getItem('originRealName');
        if (username) {
          this.initPersonalInfo();
          this.getSubordinates();

          setTimeout(() => { 
            // 初始化共享列表（如果不存在）
            if (!this.sharingInterGrowthMap[this.sharedBookName]) {
              this.sharingInterGrowthMap[this.sharedBookName] = [];
            }
            // 自动将上级和下属标记为共享状态
            if (this.myCoacher && this.myCoacher !== username) {
              if (!this.sharingInterGrowthMap[this.sharedBookName].includes(this.myCoacher)) {
                this.sharingInterGrowthMap[this.sharedBookName].push(this.myCoacher);
              }
            }
            // 添加所有下属到共享列表
            if (this.subordinateUsers && this.subordinateUsers.length > 0) {
              this.subordinateUsers.forEach(sub => {
                if (!this.sharingInterGrowthMap[this.sharedBookName].includes(sub)) {
                  this.sharingInterGrowthMap[this.sharedBookName].push(sub);
                }
              });
            }
          }, 200); 
        }
      } else {
        const users = this.notebookToBeShared.syncUsers.split(',').map(user => user.trim()).filter(user => user);
        // 初始化共享列表（前端如果还没加载）
        if (!this.sharingInterGrowthMap[this.sharedBookName]) {
          this.sharingInterGrowthMap[this.sharedBookName] = [];
        }
        // 已有共享列表了，直接显示出来
        if (users && users.length > 0) {
          users.forEach(sub => {
            if (!this.sharingInterGrowthMap[this.sharedBookName].includes(sub)) {
              this.sharingInterGrowthMap[this.sharedBookName].push(sub);
            }
          });
        }
      }
    },
    // 获取按钮样式
    getButtonStyle(username) {
      // 共享状态 - 紫色
      if (this.isUserSharedInterGrowth(username)) {
        return 'width: 200px; background-color: #8e44ad; border-color: #8e44ad;';
      }
      // 分享状态 - 绿色
      else if (this.isUserSharingInProgress(username)) {
        return 'width: 200px; background-color: #2c9678; border-color: #2c9678;';
      }
      // 默认状态 - 蓝色
      return 'width: 200px;';
    },

    // 检查用户是否处于共享状态
    isUserSharedInterGrowth(username) {
      if (!this.sharingInterGrowthMap[this.sharedBookName]) {
        return false;
      }
      return this.sharingInterGrowthMap[this.sharedBookName].includes(username);
    },

    isUserSharingInProgress(username) {
      // 检查当前本子是否有该用户正在分享中
      if (!this.sharingInProgressMap[this.sharedBookName]) {
        return false;
      }
      return this.sharingInProgressMap[this.sharedBookName].includes(username);
    },
    shareToUser(row) {
      if (this.shareMode === 0) {
        // 如果已经在分享过程中，不执行
        if (this.isUserSharingInProgress(row.username)) {
          this.$message.error('您刚刚提交的分享请求正在处理中，请勿重复分享给同一人');
          return;
        }
        // 初始化本子的分享列表（如果不存在）
        if (!this.sharingInProgressMap[this.sharedBookName]) {
          this.sharingInProgressMap[this.sharedBookName] = [];
        }
        // 将用户添加到分享列表中
        this.sharingInProgressMap[this.sharedBookName].push(row.username);
        this.$message.success('已开始在后台分享');

        this.sharedUser = row.username
        let formData = new FormData();
        formData.append('sharedUser', this.sharedUser);
        formData.append('user', localStorage.getItem('originRealName'));
        formData.append('sharedBookName', this.sharedBookName);
        formData.append('sceneName', this.selectedName);
        shareBook(formData).then(response => {
          if (response.error_num === 0) {
            this.$message.success('分享(复制)成功');
          } else {
            this.$message.error('分享(复制)失败');
          }
        });
      } else {
        // 共享模式逻辑，将默认的上下级用户加入本子的共享列表syncUsers
        if (this.isUserSharedInterGrowth(row.username)) {
          // 如果已经在共享列表中，则移除（取消共享）
          const index = this.sharingInterGrowthMap[this.sharedBookName].indexOf(row.username);
          this.sharingInterGrowthMap[this.sharedBookName].splice(index, 1);
          this.$message.success('已取消共享');
          return;
        }
        // 初始化本子的共享列表（如果不存在）
        if (!this.sharingInterGrowthMap[this.sharedBookName]) {
          this.sharingInterGrowthMap[this.sharedBookName] = [];
        }
        // 添加到共享列表
        this.sharingInterGrowthMap[this.sharedBookName].push(row.username);
        this.$message.success('已添加到共享列表');
      }
    },
    handleOpen() {
      this.fetchUserList();
    },
    fetchUserList() {
      getList().then(response => {
        if (response.error_num === 0) {
          this.userList = response.list.map(user => {
            return {
              id: user.pk,
              username: user.fields.username
            };
          })
          // }).filter(user => user.username !== localStorage.getItem('realName'));   // 过滤 username 不为自己
        } else {
          this.$message.error('获取用户列表失败');
        }
      })
    },
    handleClose() {
      this.shareDialogVisible = false
      if(this.shareMode === 1) {
        this.$message.success('您已取消共享');
      }
    },
    handleSubmitInterGrowth(){
      // this.shareDialogVisible = false
      // 从共享状态配置退出来
      if(this.shareMode === 1) {
        if(this.notebookToBeShared.syncUsers === ""){
          // 原先非组本，分享（复制给非自己）的本子writer!=username或writer为空的，暂时不能允许共享
          if(this.notebookToBeShared.writer === "" || this.notebookToBeShared.writer !== localStorage.getItem('originRealName')) {
            this.shareDialogVisible = false
            this.$message.error('这个本子的作者不是您，或没有留存作者信息，暂不可做共享');
            return
          }

          // 原先非组本，让用户选择是否需要自己留存一个副本
          ElMessageBox.confirm(
            '是否为自己留存一个副本？',
            '群组公开分享确认',
            {
              confirmButtonText: '是，留存副本',
              cancelButtonText: '否，直接分享',
              distinguishCancelAndClose: true,
              type: 'info',
            }
          ).then(() => {
            // 用户选择"是，留存副本"：保持现有逻辑（复制本子）
            this.shareDialogVisible = false
            this._doGroupShareWithCopy()
          }).catch((action) => {
            if (action === 'cancel') {
              // 用户选择"否，直接分享"：不复制本子，只更新syncUsers
              this.shareDialogVisible = false
              this._doGroupShareWithoutCopy()
            } else {
              // 用户关闭对话框，不执行任何操作
              // shareDialogVisible 保持打开状态
            }
          });
        } else {
          // 原先已经共享为组本过了（且暂时只有作者能点分享配置后关闭确认）
          // 只需要改组本配置，不需要再复制一个副本本子给自己
          this.shareDialogVisible = false

          let formData = new FormData();
          formData.append('username', localStorage.getItem('originRealName'));
          formData.append('bookname', this.sharedBookName);

          // 将数组转换为逗号分隔的字符串
          const editedSyncUsers = this.sharingInterGrowthMap[this.sharedBookName].join(', ');
          formData.append('editedSyncUsers', editedSyncUsers);
          updateBookSyncUsers(formData).then(response => {
            if (response.error_num === 0) {
              this.$message.success('已更新此本子的群组共享范围');
            } else {
              this.$message.error('更新此本子的群组共享范围失败');
            }
          });
        }
      } else {
        // shareMode === 0，直接关闭对话框
        this.shareDialogVisible = false
      }
    },
    // 群组分享并复制副本给自己
    _doGroupShareWithCopy() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      formData.append('bookname', this.sharedBookName);

      // 将数组转换为逗号分隔的字符串
      const editedSyncUsers = this.sharingInterGrowthMap[this.sharedBookName].join(', ');
      formData.append('editedSyncUsers', editedSyncUsers);
      updateBookSyncUsers(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('已更新此本子的群组共享范围');
        } else {
          this.$message.error('更新此本子的群组共享范围失败');
        }
      });

      let formDataShare = new FormData();
      formDataShare.append('sharedUser', localStorage.getItem('originRealName'));
      formDataShare.append('user', localStorage.getItem('originRealName'));
      formDataShare.append('sharedBookName', this.sharedBookName);
      formDataShare.append('sceneName', this.selectedName);
      shareBook(formDataShare).then(response => {
        if (response.error_num === 0) {
          this.$message.success('分享(复制)成功');
          // 浏览器刷新页面
          window.location.reload();
        } else {
          this.$message.error('分享(复制)失败');
        }
      });
    },
    // 群组分享但不复制副本给自己
    _doGroupShareWithoutCopy() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      formData.append('bookname', this.sharedBookName);

      // 将数组转换为逗号分隔的字符串
      const editedSyncUsers = this.sharingInterGrowthMap[this.sharedBookName].join(', ');
      formData.append('editedSyncUsers', editedSyncUsers);
      updateBookSyncUsers(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('群组分享成功，本子已变为群组本');
          // 浏览器刷新页面
          window.location.reload();
        } else {
          this.$message.error('更新此本子的群组共享范围失败');
        }
      });
    },

    handleCommentClose() {
      this.updateCommentsBook = null
    },

    backtologin() {
      let isByAdmin = localStorage.getItem('byadmin')
      let isByUplevel = localStorage.getItem('byuplevel')
      if (isByUplevel === 'true') {
        localStorage.setItem('byuplevel', 'true')
        
        localStorage.setItem('userId', localStorage.getItem('coacherName'));
        localStorage.setItem('realName', localStorage.getItem('coacherName'));
        localStorage.setItem('originRealName', localStorage.getItem('coacherName'));
        localStorage.setItem('byuplevel', 'true');
        localStorage.setItem('fromPath', '/home')

        localStorage.setItem('coacherName', localStorage.getItem('coacherNameOrigin'));
        localStorage.setItem('level', this.level_hierarchy_up[this.curLevel]);
        router.push('/unicast');
      } else if (isByAdmin === 'true') {
        router.push('/adminhome');
      } else {
        localStorage.setItem('home2login', 'true');
        router.push('/');
      }
    }
  },

};
</script>

<style scoped>
/* 全局样式 */
/* Refined Premium UI - Inspired by Nvidia, Meta, and ChatGPT */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: 'SF Pro Display', 'Segoe UI Variable', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Root Element with Refined Variables */
:root {
  --primary-gradient: linear-gradient(135deg, #ff6a00, #ee0979);
  --primary-text-color: #ff6a00;
  --accent-blue: #2563eb;
  --accent-blue-light: #38bdf8;
  --accent-blue-dark: #1d4ed8;
  --accent-purple: #8b5cf6;
  --accent-purple-light: #a78bfa;
  --accent-purple-dark: #7c3aed;
  --accent-teal: #0d9488;
  --accent-orange: #fb923c;
  --dark-bg-1: #0f172a;
  --dark-bg-2: #1e293b;
  --dark-bg-3: #0f172a99;
  --card-bg: #1e293b75;
  --card-hover: #334155;
  --text-primary: #f8fafc;
  --text-secondary: #e2e8f0;
  --text-muted: #94a3b8;
  --glow-primary: rgba(239, 68, 68, 0.25);
  --glow-blue: rgba(56, 189, 248, 0.25);
  --glow-orange: rgba(255, 126, 58, 0.3);
  --glow-green: rgba(74, 222, 128, 0.2);
  --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.1);
  --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
  --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
  --shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.08);
  --transition-all: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

/* Base Body Styles with Premium Background */
body {
  background-color: var(--dark-bg-1);
  color: var(--text-primary);
  overflow-x: hidden;
  min-height: 100vh;
}

/* PREMIUM BACKGROUND EFFECT */
.notebook-homepage {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  background-color: transparent;
}

/* Enhanced Mesh Gradient Background with Animation */
#particles {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: radial-gradient(ellipse at top, #1e2a68, transparent 70%),
              radial-gradient(ellipse at bottom, #141852, transparent 70%),
              linear-gradient(135deg, #0c1539 0%, #12143f 50%, #0a0d25 100%);
  z-index: -10;
  background-size: 200% 200%;
  animation: gradientMovement 15s ease infinite;
}

/* Network Grid Lines in Background */
#particles::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-image: 
    linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
  background-size: 40px 40px;
  opacity: 0.5;
  pointer-events: none;
  z-index: -5;
}

/* Glowing Orbs in Background */
#particles::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: 
    radial-gradient(circle at 15% 15%, var(--glow-blue), transparent 25%),
    radial-gradient(circle at 85% 85%, var(--glow-primary), transparent 35%),
    radial-gradient(circle at 75% 10%, var(--glow-green), transparent 15%);
  opacity: 0.4;
  filter: blur(60px);
  z-index: -5;
}

@keyframes gradientMovement {
  0% { background-position: 0% 0%; }
  50% { background-position: 100% 100%; }
  100% { background-position: 0% 0%; }
}

/* Enhanced Header */
.header {
  padding: 2rem 3rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  max-width: 1400px;
  margin: 0 auto;
  z-index: 10;
  position: relative;
}

/* Enhanced Title with Better Contrast */
.header h1 {
  font-size: 2.75rem;
  font-weight: 800;
  margin: 0;
  color: #ffffff;
  letter-spacing: -0.02em;
  
  /* 关键改进部分 */
  text-shadow: 
    0 0 5px rgba(217, 249, 255, 0.6), /* 发光效果 */
    0 0 10px rgba(207, 202, 198, 0.3), /* 次级发光 */
    2px 2px 4px rgba(0, 0, 0, 0.3);  /* 基础阴影 */
  
  /* 边缘抗锯齿 */
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  
  /* 可选：微妙的背景渐变增强立体感 */
  background: linear-gradient(10deg, #ffffff, #d5d5d5);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  
  position: relative;
  z-index: 1;
  display: inline-block;
  padding: 0 2px; /* 给发光效果留空间 */

  animation: glow-pulse 3s ease-in-out infinite;
}

/* 添加动画光效（可选） */
@keyframes glow-pulse {
  0% { text-shadow: 0 0 8px rgba(189, 255, 250, 0.6); }
  50% { text-shadow: 0 0 16px rgba(197, 249, 255, 0.8); }
  100% { text-shadow: 0 0 8px rgba(189, 255, 250, 0.6); }
}

/* Subtle Glow Behind Header Text */
.header h1::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 100%;
  height: 100%;
  transform: translate(-50%, -50%);
  background: radial-gradient(ellipse, rgba(61, 206, 255, 0.3), transparent 70%);
  filter: blur(20px);
  z-index: -1;
}

/* Premium Return Button */
.header button {
  background: rgba(23, 30, 41, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 0.8rem 1.7rem;
  border-radius: 8px;
  color: white;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition-all);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
  font-size: 0.95rem;
  letter-spacing: 0.01em;
}

.header button:hover {
  background: rgba(30, 41, 59, 0.9);
  transform: translateY(-2px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
}

/* Main Content Container */
.content {
  width: 90%;
  max-width: 1400px;
  margin: 0 auto 3rem;
  border-radius: 20px;
  background: rgba(15, 23, 42, 0.8);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(255, 255, 255, 0.05);
  padding: 2.5rem;
  position: relative;
  overflow: hidden;
  z-index: 5;
}

/* Glass Effect Border Highlights */
.content::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg, 
    rgba(255, 255, 255, 0), 
    rgba(255, 255, 255, 0.1), 
    rgba(255, 255, 255, 0));
  z-index: 5;
}

/* Scene Selector */
.select-scene {
  background: rgba(30, 41, 59, 0.7);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  padding: 1.75rem;
  margin-bottom: 2.5rem;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 1rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

.custom-select {
  flex: 1;
  min-width: 280px;
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: whitesmoke;
  font-size: 1.05rem;
  padding: 0.85rem 1rem;
  cursor: pointer;
  transition: var(--transition-all);
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-size: 1rem;
  background-position: calc(100% - 1rem) center;
  padding-right: 2.5rem;
  margin: 0;
}

.custom-select:hover, .custom-select:focus {
  background-color: rgba(30, 41, 59, 0.9);
  border-color: rgba(255, 255, 255, 0.2);
  outline: none;
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

/* New Scene Button */
.action-button {
  background: linear-gradient(135deg, #3b82f6, #1d4ed8);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.85rem 1.75rem;
  font-weight: 500;
  font-size: 0.95rem;
  cursor: pointer;
  transition: var(--transition-all);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1), 0 0 0 1px rgba(59, 130, 246, 0.5) inset;
  position: relative;
  isolation: isolate;
  overflow: hidden;
  white-space: nowrap;
}

.action-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1), 0 0 0 1px rgba(59, 130, 246, 0.7) inset;
  background: linear-gradient(135deg, #4f86f7, #2855e0);
}

/* Shimmer Effect on Buttons */
.action-button::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 50%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.2),
    transparent
  );
  transform: skewX(-25deg);
  transition: left 0.75s ease;
  z-index: -1;
}

.action-button:hover::before {
  left: 150%;
}

/* View Tabs - Interactive Buttons */
.actions-2 {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 1rem;
  margin: 0 auto 3.5rem;
  position: relative;
}

.action-button-2 {
  background: rgba(30, 41, 59, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: rgba(210, 210, 210, 0.842);
  border-radius: 10px;
  padding: 0.9rem 2.25rem;
  font-weight: 500;
  font-size: 0.95rem;
  cursor: pointer;
  transition: var(--transition-all);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
  position: relative;
}

.action-button-2:hover {
  background: rgba(51, 65, 85, 0.7);
  transform: translateY(-2px);
  color: rgb(236, 236, 236);
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
  border-color: rgba(255, 255, 255, 0.15);
}

.action-button-2.active {
  background: linear-gradient(135deg, #10b981, #0d9488);
  border-color: rgba(255, 255, 255, 0.1);
  color: white;
  box-shadow: 0 0 15px rgba(16, 185, 129, 0.35);
}

.view-more-wrap {
  position: relative;
  margin-left: 0.25rem;
}

.view-more-btn {
  min-width: 46px;
  height: 46px;
  padding: 0 12px;
  font-size: 1.35rem;
  line-height: 1;
  background: rgba(30, 41, 59, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  color: #e2e8f0;
  border-radius: 10px;
  cursor: pointer;
  transition: var(--transition-all);
}

.view-more-btn:hover {
  background: rgba(51, 65, 85, 0.85);
  border-color: rgba(255, 255, 255, 0.18);
}

.view-more-menu {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  min-width: 160px;
  background: rgba(30, 41, 59, 0.98);
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 10px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  z-index: 100;
  overflow: hidden;
}

.view-more-item {
  display: block;
  width: 100%;
  padding: 10px 14px;
  text-align: left;
  background: transparent;
  border: none;
  color: #e2e8f0;
  cursor: pointer;
  font-size: 0.9rem;
}

.view-more-item:hover {
  background: rgba(59, 130, 246, 0.25);
}

/* Scene Title with Accent */
.scene-wrapper {
  margin-bottom: 3rem;
}

.actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
  gap: 1rem;
}

.actions h1 {
  font-size: 1.95rem;
  font-weight: 700;
  letter-spacing: -0.01em;
  position: relative;
  display: inline-block;
  color: #ff7e3a; /* Enhanced orange color for better contrast */
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
}

/* Accent Color Underline */
.actions h1::after {
  content: '';
  position: absolute;
  bottom: -6px;
  left: 0;
  width: 50px;
  height: 3px;
  background: linear-gradient(90deg, #ff7e3a, #ff5757);
  border-radius: 3px;
}

/* Premium Notebook List */
.notebook-list-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.notebook-item {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.07);
  padding: 1.5rem;
  position: relative;
  transition: var(--transition-all);
  box-shadow: var(--shadow-md);
  min-height: 190px;
  display: flex;
  flex-direction: column;
}

/* Premium Card Hover Effects */
.notebook-item:hover {
  transform: translateY(-5px);
  background: rgba(51, 65, 85, 0.7);
  border-color: rgba(255, 255, 255, 0.15);
  box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.2), 0 4px 6px -2px rgba(0, 0, 0, 0.1), 0 0 25px rgba(14, 165, 233, 0.15);
}

/* Top Border Color Highlight */
.notebook-item::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #38bdf8, #8b5cf6);
  border-radius: 3px 3px 0 0;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.notebook-item:hover::before {
  opacity: 1;
}

.notebook-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  margin-bottom: 1rem;
}

.title-comment-wrapper {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* Enhanced Title with Better Contrast */
.notebook-info h3 {
  font-size: 1.1rem;
  font-weight: 600;
  color: #67f2ff; /* Brighter blue for better contrast */
  cursor: pointer;
  margin: 0;
  transition: var(--transition-all);
  text-shadow: 0 1px 1px rgba(0, 0, 0, 0.2);
}

.notebook-info h3:hover {
  color: #8bddff;
  text-shadow: 0 0 8px rgba(96, 205, 255, 0.4);
}

.description-shared-wrapper {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.notebook-info p {
  font-size: 0.9rem;
  color: #e2e8f08f;
  margin: 0;
  line-height: 1.4;
}

.break-words {
  word-wrap: break-word;
  white-space: normal;
  overflow-wrap: break-word;
  width: 80%;
}

/* 任务簇整理钉子勾选 */
.notebook-pin-btn {
  cursor: pointer;
  width: 28px;
  height: 28px;
  flex-shrink: 0;
  background-repeat: no-repeat;
  background-position: center;
  background-size: contain;
  background-image: url('@/assets/img/pin_grey.png');
  transition: transform 0.15s ease;
}

.notebook-pin-btn:hover {
  transform: scale(1.08);
}

.notebook-pin-btn--active {
  background-image: url('@/assets/img/pin_blue.png');
  background-color: rgba(59, 130, 246, 0.35);
  border-radius: 8px;
  box-shadow:
    0 0 0 2px rgba(147, 197, 253, 0.95),
    0 0 14px rgba(59, 130, 246, 0.75);
  transform: scale(1.12);
}

.notebook-item--add-to-cluster {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 190px;
  cursor: pointer;
  border: 1.5px dashed rgba(56, 189, 248, 0.45);
  background: rgba(14, 165, 233, 0.08);
}
.notebook-item--add-to-cluster:hover {
  border-color: rgba(56, 189, 248, 0.85);
  background: rgba(14, 165, 233, 0.16);
}
.notebook-item--add-to-cluster::before {
  display: none;
}
.add-to-cluster-plus {
  font-size: 3rem;
  line-height: 1;
  color: #38bdf8;
  font-weight: 300;
}
.add-to-cluster-hint {
  margin-top: 0.75rem;
  color: #94a3b8;
  font-size: 0.9rem;
  text-align: center;
}

.notebook-ctx-menu {
  position: fixed;
  z-index: 9999;
  min-width: 140px;
  background: rgba(30, 27, 46, 0.96);
  border: 1px solid rgba(139, 92, 246, 0.45);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  padding: 6px 0;
}

.notebook-ctx-menu-title {
  font-size: 0.75rem;
  color: #a78bfa;
  padding: 6px 14px 4px;
  font-weight: 600;
  letter-spacing: 0.04em;
}

.notebook-ctx-menu-item {
  display: block;
  width: 100%;
  text-align: left;
  background: transparent;
  border: none;
  color: #e9d5ff;
  font-size: 0.9rem;
  padding: 8px 14px;
  cursor: pointer;
}

.notebook-ctx-menu-item:hover {
  background: rgba(139, 92, 246, 0.25);
}

/* Premium Comment Button (保留样式供其他位置复用) */
.book-comment-btn {
  background: rgba(139, 92, 246, 0.3);
  border: 1px solid rgba(139, 92, 246, 0.4);
  color: #d8b4fe;
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0.35rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  transition: var(--transition-all);
  letter-spacing: 0.02em;
  display: flex;
  align-items: center;
  justify-content: center;
}

.book-comment-btn:hover {
  background: rgba(139, 92, 246, 0.4);
  transform: translateY(-1px);
  color: white;
  box-shadow: 0 0 8px rgba(139, 92, 246, 0.35);
}

/* Status Icons */
.alert-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-right: 4px;
}

.exclamation-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background-color: #ff4d4f;
  color: white;
  font-weight: bold;
  font-size: 18px;
}

.shared-icon,
.demo-icon,
.common-icon,
.group-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  color: white;
  font-size: 0.75rem;
  font-weight: 600;
  margin-left: 0.5rem;
  position: relative;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
}

.shared-icon {
  background: linear-gradient(135deg, #10b981, #059669);
}

.demo-icon {
  background: linear-gradient(135deg, #ec4899, #db2777);
}

.common-icon {
  background: linear-gradient(135deg, #0ea5e9, #0284c7);
}

.group-icon {
  background: linear-gradient(135deg, #8031c6, #7425c8);
}

/* Icon Glow Effect on Hover */
.shared-icon::after,
.demo-icon::after,
.common-icon::after,
.group-icon::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  z-index: -1;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.shared-icon::after {
  background: radial-gradient(circle, rgba(16, 185, 129, 0.4), transparent 70%);
}

.demo-icon::after {
  background: radial-gradient(circle, rgba(236, 72, 153, 0.4), transparent 70%);
}

.common-icon::after {
  background: radial-gradient(circle, rgba(14, 165, 233, 0.4), transparent 70%);
}

.group-icon::after {
  background: radial-gradient(circle, rgba(153, 14, 233, 0.4), transparent 70%);
}

.shared-icon:hover::after,
.demo-icon:hover::after,
.common-icon:hover::after,
.group-icon:hover::after {
  opacity: 1;
}

/* Action Buttons Container */
.notebook-actions {
  display: flex;
  gap: 0.75rem;
  width: 100%;
}

/* Stylish Button Group */
.open-button,
.delete-button,
.share-button {
  padding: 0.6rem 0.5rem;
  border-radius: 8px;
  border: none;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition-all);
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

/* Open Button - Primary Action */
.open-button {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: white;
  box-shadow: 0 0 10px rgba(37, 99, 235, 0.3);
}

.open-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 15px rgba(37, 99, 235, 0.5);
  background: linear-gradient(135deg, #3a75f7, #2355e5);
}

/* Delete Button - Destructive Action */
.delete-button {
  background: linear-gradient(135deg, #ef4444, #dc2626);
  color: white;
  box-shadow: 0 0 10px rgba(239, 68, 68, 0.3);
}

.delete-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 15px rgba(239, 68, 68, 0.5);
  background: linear-gradient(135deg, #f25757, #e82f2f);
}

/* Share Button - Secondary Action */
.share-button {
  background: linear-gradient(135deg, #8b5cf6, #7c3aed);
  color: white;
  box-shadow: 0 0 10px rgba(139, 92, 246, 0.3);
}

.share-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 15px rgba(139, 92, 246, 0.5);
  background: linear-gradient(135deg, #9d6dff, #8a4af1);
}

/* Shimmer Effect for Buttons */
.open-button::before,
.delete-button::before,
.share-button::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 50%;
  height: 100%;
  background: linear-gradient(
    90deg,
    transparent,
    rgba(255, 255, 255, 0.15),
    transparent
  );
  transform: skewX(-25deg);
  transition: left 0.75s ease;
  z-index: 1;
}

.open-button:hover::before,
.delete-button:hover::before,
.share-button:hover::before {
  left: 150%;
}

/* Premium Separator Line */
.line::after {
  content: '';
  display: block;
  height: 2px;
  background: linear-gradient(to right, 
    transparent, 
    rgba(138, 92, 246, 0.374), 
    transparent);
  margin: 2.5rem 0;
}

/* Personal Info Section - Glass Card */
.personal-info {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 12px;
  padding: 1.75rem;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
}

.level-info, 
.coacher-info {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  margin-bottom: 1.25rem;
}

.level-info:last-child,
.coacher-info:last-child {
  margin-bottom: 0;
}

.info-label {
  font-size: 0.95rem;
  font-weight: 500;
  color: #f8fafc;
  min-width: 120px;
}

/* Premium Form Inputs */
.select-input,
.text-input {
  background: rgba(15, 23, 42, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  color: #f8fafc;
  font-size: 0.9rem;
  padding: 0.7rem 1rem;
  min-width: 180px;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.select-input {
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-size: 1rem;
  background-position: calc(100% - 1rem) center;
  padding-right: 2.5rem;
  cursor: pointer;
}

.text-input::placeholder {
  color: #94a3b8;
}

.select-input:hover, 
.text-input:hover {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(30, 41, 59, 0.7);
}

.select-input:focus, 
.text-input:focus {
  outline: none;
  border-color: rgba(56, 189, 248, 0.5);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

/* Update Button */
.update-btn {
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.3), rgba(14, 165, 233, 0.3));
  color: #c6ecfe;
  border: 1px solid rgba(56, 189, 248, 0.4);
  border-radius: 8px;
  padding: 0.7rem 1.25rem;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition-all);
}

.update-btn:hover {
  background: linear-gradient(135deg, rgba(56, 189, 248, 0.4), rgba(14, 165, 233, 0.4));
  transform: translateY(-2px);
  box-shadow: 0 0 10px rgba(56, 189, 248, 0.3);
  color: white;
}

/* Subordinates Selector */
.subordinates-selector {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 12px;
  padding: 1.25rem 1.75rem;
  margin-bottom: 1.5rem;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
}

/* User Info Card */
.user-info {
  background: rgba(30, 41, 59, 0.7);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 12px;
  padding: 1.75rem;
  color: #e2e8f0;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
}

.user-info > div {
  margin-bottom: 0.75rem;
  font-size: 0.95rem;
}

.user-info p {
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
  line-height: 1.5;
}

/* 修复嵌套卡片的布局问题 */
.user-info .notebook-item{
  max-width: 22%;
}

/* Edit Description Input */
.bookDescriptionEdit {
  border: 1px solid rgba(56, 189, 248, 0.3);
  background: rgba(15, 23, 42, 0.7);
  color: #60cdff;
  font-size: 1rem;
  font-weight: 500;
  padding: 0.35rem 0.75rem;
  border-radius: 6px;
  width: 75%;
  transition: var(--transition-all);
}

.bookDescriptionEdit:focus {
  outline: none;
  border-color: rgba(56, 189, 248, 0.5);
  box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.15);
}

/* Comment Update Button */
.updateCommentButton {
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.3), rgba(67, 56, 202, 0.3));
  color: #bec8ff;
  border: 1px solid rgba(79, 70, 229, 0.4);
  border-radius: 8px;
  padding: 0.5rem 1rem;
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition-all);
  margin-left: 0.75rem;
}

.updateCommentButton:hover {
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.4), rgba(67, 56, 202, 0.4));
  transform: translateY(-2px);
  box-shadow: 0 0 10px rgba(79, 70, 229, 0.3);
  color: white;
}

/* Footer */
.footer {
  text-align: center;
  padding: 1.5rem;
  color: rgb(210, 241, 235);
  font-size: 0.85rem;
  background: linear-gradient(to right, transparent, rgba(255, 255, 255, 0.03), transparent);
  margin-top: 2rem;
  position: relative;
  z-index: 5;
}

/* Dialog Styling */
.el-dialog {
  background: rgba(15, 23, 42, 0.95);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-radius: 16px;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.2), 0 10px 10px -5px rgba(0, 0, 0, 0.08), 0 0 0 1px rgba(255, 255, 255, 0.05);
  overflow: hidden;
  border: none;
}

.el-dialog__header {
  background: rgba(30, 41, 59, 0.95);
  padding: 1.5rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.05);
}

.el-dialog__title {
  color: #f8fafc;
  font-weight: 600;
}

.el-dialog__body {
  padding: 2rem;
  color: #e2e8f0;
}

.el-dialog__footer {
  background: rgba(30, 41, 59, 0.95);
  padding: 1.25rem 1.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.05);
}

.el-button {
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: white;
  border: none;
  border-radius: 8px;
  padding: 0.75rem 1.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition-all);
  box-shadow: 0 0 10px rgba(37, 99, 235, 0.2);
}

.el-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 0 15px rgba(37, 99, 235, 0.3);
  background: linear-gradient(135deg, #3a75f7, #2355e5);
}

/* Custom Scrollbar */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: rgba(15, 23, 42, 0.5);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background: rgba(56, 189, 248, 0.4);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(56, 189, 248, 0.6);
}

/* Loading States */
.notebook-item button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
  transform: none !important;
  box-shadow: none !important;
}

/* Small utility classes */
.flex {
  display: flex;
}

.items-center {
  align-items: center;
}

.justify-between {
  justify-content: space-between;
}

.gap-2 {
  gap: 0.5rem;
}

/* Responsive Adjustments */
@media (max-width: 1200px) {
  .content {
    padding: 2rem;
  }
  
  .notebook-list-row {
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  }
}

@media (max-width: 768px) {
  .header {
    padding: 1.5rem;
    flex-wrap: wrap;
  }
  
  .content {
    padding: 1.5rem;
  }
  
  .select-scene {
    padding: 1.25rem;
  }
  
  .notebook-list-row {
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  }
  
  .actions-2 {
    flex-wrap: wrap;
  }
}

/* Enhanced dropdown/select styling */
select {
  height: auto;
  line-height: normal;
}



.tab-group {
  display: flex;
  margin: 20px 0;
  border-bottom: 1px solid #e4e7ed;
}

.tab-item {
  padding: 10px 20px;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.3s;
  position: relative;
  color: #606266;
}

.tab-item.active {
  color: #409EFF;
  font-weight: 500;
}

.tab-item.active:after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  width: 100%;
  height: 2px;
  background-color: #409EFF;
}

.tab-item:hover:not(.active) {
  color: #409EFF;
}



.shared-ready {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 200px;
  height: 36px;
  border-radius: 6px;
  background-color: #4070ff;
  color: white;
  cursor: pointer;
  font-size: 14px;
  transition: background-color 0.3s, transform 0.1s, box-shadow 0.3s;
  border: none;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  letter-spacing: 0.5px;
  position: relative;
  overflow: hidden;
}

.shared-ready:before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(to bottom, rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0));
  pointer-events: none;
}

.shared-ready:hover {
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
}

.shared-ready:active {
  transform: translateY(1px);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.shared-intergrowth {
  background-color: #7f349f;
}

.shared-copy {
  background-color: #2c9678;
}


.progress-container {
  padding: 20px;
  text-align: center;
}
.progress-message {
  margin-top: 15px;
  color: #606266;
}



/* System Choice Toggle Styles */
.header-buttons {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  position: relative;
}

/* 滑块整体容器 */
.system-choice-slider {
  cursor: pointer;
  user-select: none;
}

/* 滑块轨道（类似iOS toggle）*/
.slider-track {
  width: 150px;
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

/* 滑块椭圆按钮（柔和渐变）*/
.slider-thumb {
  position: absolute;
  width: 75px;
  height: 28px;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  border-radius: 14px;
  left: 2px;
  top: 50%;
  transform: translateY(-50%);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.3);
}

/* 慢思考模式：滑块移到右边 */
.slider-thumb.slow {
  left: calc(100% - 77px);
  /* background: linear-gradient(135deg, #8b5cf6, #ec4899); */
}

/* 滑块内文字（只显示在非激活侧）*/
.slider-text {
  font-size: 0.85rem;
  font-weight: 600;
  color: #334155;
  z-index: 1;
  position: relative;
  white-space: nowrap;
}

/* 右侧文字 */
.slider-text.right {
  margin-left: auto;
}

/* hover效果 */
.system-choice-slider:hover .slider-track {
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.4);
}

.system-choice-slider:hover .slider-thumb {
  box-shadow: 0 4px 10px rgba(59, 130, 246, 0.5);
}

.task-cluster-wrapper {
  max-width: 1200px;
  margin: 0 auto;
}

.task-cluster-header {
  margin-bottom: 24px;
}

.task-cluster-title {
  color: #a5b4fc;
  margin-bottom: 8px;
}

.task-cluster-desc {
  color: lavender;
  font-size: 0.95rem;
  line-height: 1.5;
  margin-bottom: 16px;
}

.task-cluster-toolbar {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.task-cluster-toolbar .open-button,
.task-cluster-toolbar .share-button,
.task-cluster-toolbar .delete-button {
  flex: 0 0 auto;
  width: auto;
  padding: 0.55rem 1.1rem;
}

.task-cluster-meta {
  color: #94a3b8;
  font-size: 0.85rem;
}

.task-cluster-loading,
.task-cluster-empty,
.task-cluster-progress-panel {
  color: lavender;
  padding: 24px;
  text-align: center;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  margin-bottom: 20px;
}

.task-cluster-progress-panel {
  text-align: left;
}

.task-cluster-block {
  margin-bottom: 28px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 14px;
}

.task-cluster-block-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.task-cluster-block-main {
  flex: 1;
  min-width: 0;
}

.task-cluster-delete-btn {
  flex: 0 0 auto;
  width: auto;
  padding: 0.45rem 0.9rem;
  margin-top: 2px;
}

.task-cluster-empty-hint {
  color: #94a3b8;
  font-size: 0.88rem;
  margin: 4px 0 0 0;
}

.task-cluster-name {
  color: #c4b5fd;
  margin: 0 0 8px 0;
}

.task-cluster-summary {
  color: #cbd5e1;
  font-size: 0.92rem;
  margin: 0 0 16px 0;
  line-height: 1.5;
}

.editable-cluster-field {
  cursor: pointer;
}

.editable-cluster-field:hover {
  color: #e0e7ff;
}

.task-cluster-name-edit,
.task-cluster-summary-edit {
  width: 100%;
  margin-bottom: 8px;
}

.task-cluster-adjust-mode {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 16px;
}

.task-cluster-adjust-form {
  margin-top: 8px;
}

.task-cluster-adjust-hint {
  color: #94a3b8;
  font-size: 0.9rem;
  margin: 0 0 8px 0;
}

.task-cluster-adjust-empty {
  color: #f87171;
  font-size: 0.85rem;
  margin-top: 8px;
}

.task-cluster-unclustered {
  margin-top: 12px;
  padding-top: 8px;
}

.scene-ontology-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-left: 10px;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  cursor: pointer;
  vertical-align: middle;
  color: #94a3b8;
  background: rgba(148, 163, 184, 0.12);
  transition: color 0.15s, background 0.15s;
}
.scene-ontology-btn:hover {
  color: #e2e8f0;
  background: rgba(99, 102, 241, 0.35);
}
.scene-ontology-btn--ready {
  color: #a5b4fc;
  background: rgba(99, 102, 241, 0.28);
}

.ontology-menu-backdrop {
  position: fixed;
  inset: 0;
  z-index: 10040;
  background: transparent;
}
.ontology-menu-panel {
  position: fixed;
  z-index: 10050;
  min-width: 168px;
  padding: 6px 0;
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
}
.ontology-menu-item {
  display: block;
  width: 100%;
  border: none;
  background: transparent;
  color: #e2e8f0;
  text-align: left;
  padding: 8px 14px;
  font-size: 13px;
  cursor: pointer;
}
.ontology-menu-item:hover {
  background: rgba(99, 102, 241, 0.35);
}

.ontology-floating-progress {
  background: #0f172a !important;
  border-color: #334155 !important;
}
.ontology-floating-progress .semantic-reorganize-floating-title,
.ontology-floating-progress .semantic-reorganize-floating-detail {
  color: #e2e8f0 !important;
}
.ontology-floating-progress .semantic-reorganize-floating-close {
  color: #94a3b8 !important;
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
.semantic-reorganize-floating-detail {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.5;
  word-break: break-all;
}

.ontology-graph-wrap {
  min-height: 70vh;
}
.ontology-graph-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}
</style>
