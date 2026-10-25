<template>
  <div class="notebook-homepage">
    <!-- 左侧悬浮导航栏 -->
    <div class="floating-nav" :class="{ 'nav-collapsed': navCollapsed }">
      <div class="nav-toggle" @click="toggleNav">
        <!-- <i :class="navCollapsed ? 'custom-icon icon-expand' : 'el-icon-s-fold'" style="font-size: 18px;"></i> -->
        <div :class="navCollapsed ? 'custom-icon icon-expand' : 'custom-icon icon-fold'"></div>
      </div>
      <div class="nav-content" v-show="!navCollapsed">
        <div class="nav-title">快速导航</div>
        <div class="nav-items">
          <div 
            class="nav-item" 
            :class="{ active: activeSection === 'users' }"
            @click="scrollToSection('users')"
          >
            <!-- <i class="el-icon-user" style="font-size: 16px;"></i> -->
            <div class="custom-icon icon-user"></div>
            <span>用户管理</span>
          </div>
          <div 
            class="nav-item" 
            :class="{ active: activeSection === 'models' }"
            @click="scrollToSection('models')"
          >
            <!-- <i class="el-icon-cpu" style="font-size: 16px;"></i> -->
            <div class="custom-icon icon-cpu"></div>
            <span>模型管理</span>
          </div>
          <div 
            class="nav-item" 
            :class="{ active: activeSection === 'chroma' }"
            @click="scrollToSection('chroma')"
          >
            <!-- <i class="el-icon-connection" style="font-size: 16px;"></i> -->
            <div class="custom-icon icon-connection"></div>
            <span>Chroma管理</span>
          </div>
        </div>
      </div>
    </div>

    <div class="header">
      <h1>NKCN·Brain V3.2 欢迎您 {{ this.curUserName }}</h1>
        <!-- <div class="redirect-config-container">
          <label for="redirect-select">跳转配置:</label>
          <el-select 
            v-model="currentRedirectKey" 
            @change="changeRedirectTarget"
            placeholder="选择跳转目标"
            style="width: 200px; margin-right: 10px;"
          >
            <el-option 
              label="不跳转" 
              value="NONE"
            >
              <div>
                <span>不跳转</span>
                <div style="font-size: 12px; color: #999;">保持当前访问地址</div>
              </div>
            </el-option>
            <el-option 
              v-for="(target, key) in allTargets" 
              :key="key" 
              :label="target.name" 
              :value="key"
            >
              <div>
                <span>{{ target.name }}</span>
                <div style="font-size: 12px; color: #999;">{{ target.url }}</div>
              </div>
            </el-option>
          </el-select>
          <span class="current-redirect-info">
            当前: {{ currentRedirectKey === 'NONE' ? '不跳转' : (currentRedirectTarget ? currentRedirectTarget.name : '不跳转') }}
          </span>
        </div> -->
      <button @click="backtologin" class="action-button">返回登录</button>
      <button @click="gotoUse" class="action-button">继续使用</button>
    </div>

    <div class="content">
      <div id="users-section" class="online-users-container">
        <h3>当前在线用户：{{ onlineNum }}</h3>
        <ul>
          <li v-for="(userObj, index) in combinedOnlineData" :key="index">
            用户名：{{ userObj.user }}<br>正在使用的本子名：{{ userObj.userbook }}<br><br>
          </li>
        </ul>
      </div>

      <div class="actions">
        <h1>用户列表</h1>
      </div>
      <div class="actions">
        <el-table :data="userList" style="width: min-content;">
          <el-table-column prop="username" label="用户名" width="180">
            <template #default="{ row }">
              <el-popover
                placement="top-start"
                trigger="hover"
                width="200"
              >
                <template #default>
                  <div>
                    <p><strong>coacher领航员:</strong> {{ row.coacher || '无' }}</p>
                    <p><strong>组织层级:</strong> {{ getLevelName(row.level) }}</p>
                  </div>
                </template>
                <template #reference>
                  <span style="cursor: pointer;">{{ row.username }}</span>
                </template>
              </el-popover>
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="140">
            <template #default="{ row }">
              <el-tag :type="row.allowed ? 'success' : 'warning'">
                {{ row.allowed ? '可使用' : '待通过' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="跳转配置" width="120">
            <template #default="{ row }">
              <el-select 
                v-model="userRedirectConfigs[row.username]"
                @change="(val) => changeUserRedirect(row.username, val)"
                size="small"
                placeholder="选择跳转"
              >
                <el-option label="不跳转" value="NONE" />
                <el-option label="硅谷服务器" value="SILICON_VALLEY" />
                <el-option label="国内服务器" value="CHINA" />
                <el-option label="本地开发" value="LOCAL" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="300">
            <template #default="{ row }">
              <el-button type="primary"  style="width: 80px;" @click="editUser(row)">查看</el-button>
              <el-button type="danger"  style="width: 80px;" @click="banUser(row)">禁止</el-button>
              <el-button style="width: 80px; background-color: #0f9d58; color: white;" @click="openUser(row)">通过</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div id="models-section" class="model-form-container">
      <h2>添加模型 API</h2>
      <el-form :model="modelForm" label-width="120px" style="max-width: 600px;">
        <el-form-item label="模型缩写名">
          <el-input v-model="modelForm.abbreviation" placeholder="请输入模型缩写名"></el-input>
        </el-form-item>
        <el-form-item label="模型全名">
          <el-input v-model="modelForm.fullName" placeholder="请输入模型全名"></el-input>
        </el-form-item>
        <el-form-item label="模型类型">
          <el-select v-model="modelForm.type" placeholder="请选择模型类型">
            <el-option label="OpenAI" value="openai"></el-option>
            <el-option label="HuggingFace" value="huggingface"></el-option>
            <el-option label="Anthropic" value="anthropic"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="URL 地址">
          <el-input v-model="modelForm.url" placeholder="请输入 URL 地址"></el-input>
        </el-form-item>
        <el-form-item label="API 密钥">
          <el-input
            v-model="modelForm.apiKey"
            placeholder="请输入 API 密钥"
            show-password
          ></el-input>
        </el-form-item>
        <!-- <el-form-item label="模型能力">
          <el-checkbox v-model="modelForm.isInference">推理模型</el-checkbox>
          <el-checkbox v-model="modelForm.supportsImages">支持图片</el-checkbox>
        </el-form-item> -->
        <el-form-item label="模型基本信息">
          <el-input
            v-model="modelForm.description"
            type="textarea"
            :rows="3"
            placeholder="请输入模型的基本信息描述"
          ></el-input>
        </el-form-item>
        <el-form-item label="响应速度">
          <el-select v-model="modelForm.responseSpeed" placeholder="请选择响应速度">
            <el-option label="快" value="fast"></el-option>
            <el-option label="中快" value="medium_fast"></el-option>
            <el-option label="中慢" value="medium_slow"></el-option>
            <el-option label="较慢" value="slow"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="推理水平">
          <el-select v-model="modelForm.reasoningLevel" placeholder="请选择推理水平">
            <el-option label="高-原生" value="high_native"></el-option>
            <el-option label="中-原生" value="medium_native"></el-option>
            <el-option label="低-原生" value="low_native"></el-option>
            <el-option label="高-非原生" value="high_nonnative"></el-option>
            <el-option label="中-非原生" value="medium_nonnative"></el-option>
            <el-option label="低-非原生" value="low_nonnative"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="多模态能力">
          <el-select v-model="modelForm.multimodalLevel" placeholder="请选择多模态能力">
            <el-option label="高" value="high"></el-option>
            <el-option label="中" value="medium"></el-option>
            <el-option label="低" value="low"></el-option>
            <el-option label="无" value="none"></el-option>
          </el-select>
        </el-form-item>
        
        <el-form-item label="Prompt 模板">
          <el-input
            v-model="modelForm.promptTemplate"
            type="textarea"
            :rows="3"
            placeholder="暂时不支持输入 Prompt 模板"
          ></el-input>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="addModel">添加模型</el-button>
        </el-form-item>
      </el-form>
    </div>
    <!-- 显示已添加的模型列表 -->
    <div class="model-list-container">
      <h2>已添加的模型列表</h2>
      <el-table :data="modelBaseInfo" style="width: 100%">
        <el-table-column prop="abbreviation" label="模型缩写名" width="150"></el-table-column>
        <el-table-column prop="fullName" label="模型全名" width="200"></el-table-column>
        <el-table-column prop="type" label="实际格式" width="100">
          <template #default="{ row }">
            <el-tag :type="getModelTypeTagType(row.type)">
              {{ getModelTypeDisplayName(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="url" label="URL 地址" width="250"></el-table-column>
        <el-table-column label="操作" width="120" align="center">
          <template #default="{row}">
            <el-button type="primary" size="small" @click="editModelInfo(row)">编辑</el-button>
          </template>
        </el-table-column>
        <!-- <el-table-column label="推理/图片" width="100" align="center">
          <template #default="{row}">
            <span class="status-dot" :class="{
              'disabled-dot': !row.isInference && !row.supportsImages,  // 灰色（都不支持）
              'inference-dot': row.isInference && !row.supportsImages,  // 蓝色（仅推理）
              'image-dot': !row.isInference && row.supportsImages,      // 红色（仅图片）
              'both-dot': row.isInference && row.supportsImages         // 紫色（两者都支持）
            }"></span>
            <span style="margin-left: 8px; font-size: 12px; color: #666">
              {{ 
                !row.isInference && !row.supportsImages ? "无" :
                row.isInference && !row.supportsImages ? "推理" :
                !row.isInference && row.supportsImages ? "图片" :
                "推理+图片"
              }}
            </span>
          </template>
        </el-table-column> -->
        <el-table-column prop="responseSpeed" label="响应速度" width="120">
          <template #default="{ row }">
            {{ 
              row.responseSpeed === 'fast' ? '快' :
              row.responseSpeed === 'medium_fast' ? '中快' :
              row.responseSpeed === 'medium_slow' ? '中慢' :
              row.responseSpeed === 'slow' ? '较慢' : '未知'
            }}
          </template>
        </el-table-column>

        <el-table-column prop="reasoningLevel" label="推理水平" width="150">
          <template #default="{ row }">
            {{ 
              row.reasoningLevel === 'high_native' ? '高-原生' :
              row.reasoningLevel === 'medium_native' ? '中-原生' :
              row.reasoningLevel === 'low_native' ? '低-原生' :
              row.reasoningLevel === 'high_nonnative' ? '高-非原生' :
              row.reasoningLevel === 'medium_nonnative' ? '中-非原生' :
              row.reasoningLevel === 'low_nonnative' ? '低-非原生' : '未知'
            }}
          </template>
        </el-table-column>

        <el-table-column prop="multimodalLevel" label="多模态能力" width="100">
          <template #default="{ row }">
            {{ 
              row.multimodalLevel === 'high' ? '高' :
              row.multimodalLevel === 'medium' ? '中' :
              row.multimodalLevel === 'low' ? '低' :
              row.multimodalLevel === 'none' ? '无' : '未知'
            }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 三窗口默认模型配置 -->
    <div class="default-models-container" style="margin: 30px 0; padding: 20px; background: #f5f7fa; border-radius: 8px;">
      <h2>三窗口默认模型配置</h2>
      <p style="color: #666; margin-bottom: 20px;">配置后，其他用户登录进入本子时会自动加载这些默认模型</p>
      
      <el-form label-width="150px" style="max-width: 700px;">
        <el-form-item label="主窗口默认模型">
          <el-select v-model="defaultModels.main" placeholder="请选择主窗口默认模型" style="width: 300px;">
            <el-option 
              v-for="model in modelBaseInfo" 
              :key="model.id" 
              :label="model.abbreviation" 
              :value="model.id">
            </el-option>
          </el-select>
          <span style="margin-left: 10px; color: #999;">当前: {{ getModelNameById(defaultModels.main) }}</span>
        </el-form-item>
        
        <el-form-item label="右上窗口默认模型">
          <el-select v-model="defaultModels.topRight" placeholder="请选择右上窗口默认模型" style="width: 300px;">
            <el-option 
              v-for="model in modelBaseInfo" 
              :key="model.id" 
              :label="model.abbreviation" 
              :value="model.id">
            </el-option>
          </el-select>
          <span style="margin-left: 10px; color: #999;">当前: {{ getModelNameById(defaultModels.topRight) }}</span>
        </el-form-item>
        
        <el-form-item label="右下窗口默认模型">
          <el-select v-model="defaultModels.bottomRight" placeholder="请选择右下窗口默认模型" style="width: 300px;">
            <el-option 
              v-for="model in modelBaseInfo" 
              :key="model.id" 
              :label="model.abbreviation" 
              :value="model.id">
            </el-option>
          </el-select>
          <span style="margin-left: 10px; color: #999;">当前: {{ getModelNameById(defaultModels.bottomRight) }}</span>
        </el-form-item>
        
        <el-form-item>
          <el-button type="primary" @click="saveDefaultModels">保存配置</el-button>
          <el-button @click="loadDefaultModels">刷新当前配置</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- 场景模型配置（P0-P5 业务写死模型） -->
    <div class="scene-models-container" style="margin: 30px 0; padding: 20px; background: #f0f9eb; border-radius: 8px;">
      <h2>一些系统能力的模型配置</h2>
      <p style="color: #666; margin-bottom: 12px;">
        红蓝浅评、文档摘要、卡片 HTML 整理更新/卡片生图、输出目录卡、连续图片OCR/识别/理解、作业批改、交叉梳理 Skill 等处的模型。保存后立即生效，无需重启。
      </p>
      <p style="color: #909399; margin-bottom: 20px; font-size: 13px;">
        <strong style="color: #67c23a;">标准配置</strong>：从已有模型配置里选择，只换模型缩写名，调用方式不变；
        <strong style="color: #e6a23c;">专用接口</strong>：直连 API 的模型名，只能在同调用方式的可选项内切换。
      </p>
      <div v-for="group in sceneModelGroups" :key="group.name" style="margin-bottom: 24px;">
        <h3 style="margin-bottom: 12px; color: #409eff;">{{ group.label }}</h3>
        <p v-if="group.name === 'P5'" style="color: #909399; font-size: 13px; margin: 0 0 12px 0;">
          以下项仅作展示，暂不支持在此修改。
        </p>
        <el-form label-width="280px" style="max-width: 900px;">
          <el-form-item v-for="slot in group.slots" :key="slot.key" :label="slot.label">
            <el-select
              v-model="sceneModelValues[slot.key]"
              style="width: 360px;"
              filterable
              :disabled="slot.type === 'display_only' || slot.editable === false">
              <el-option
                v-for="opt in slot.options"
                :key="opt"
                :label="opt"
                :value="opt">
              </el-option>
            </el-select>
            <el-tag
              v-if="slot.type === 'display_only'"
              size="small"
              style="margin-left: 10px;"
              type="info">
              暂不可改
            </el-tag>
            <el-tag
              v-else
              size="small"
              style="margin-left: 10px;"
              :type="slot.type === 'config_abbr' ? 'success' : (slot.type === 'llm_slot' ? 'primary' : 'warning')">
              {{ slot.type === 'config_abbr' ? '标准配置' : (slot.type === 'llm_slot' ? '语义模型' : '专用接口') }}
            </el-tag>
            <span v-if="slot.type !== 'display_only'" style="margin-left: 8px; color: #999; font-size: 12px;">默认: {{ slot.default }}</span>
            <div v-if="slot.hint" style="margin-top: 6px; color: #909399; font-size: 12px; line-height: 1.5;">{{ slot.hint }}</div>
          </el-form-item>
        </el-form>
      </div>
      <el-button type="primary" @click="saveSceneModels">保存这套模型配置</el-button>
      <el-button @click="loadSceneModels">刷新</el-button>
    </div>

    <!-- 长短记忆 AutoDream -->
    <div class="scene-models-container" style="margin: 30px 0; padding: 20px; background: #fdf6ec; border-radius: 8px;">
      <h2>长短记忆 · AutoDream</h2>
      <p style="color: #666; margin-bottom: 12px;">
        手动触发本子记忆整理（合并同义、修正矛盾、日记剪枝、可选上浮场景 MEMORY）。username 填「账户_本子」完整本子键。
      </p>
      <el-form label-width="120px" style="max-width: 720px;">
        <el-form-item label="本子键">
          <el-input v-model="dreamUsername" placeholder="例如：lyf_某本子名" clearable />
        </el-form-item>
        <el-form-item label="场景名">
          <el-input v-model="dreamSceneName" placeholder="可选，有则一并整理 scene_memory" clearable />
        </el-form-item>
        <el-form-item>
          <el-button type="warning" :loading="dreamLoading" @click="triggerNotebookMemoryDream">
            {{ dreamLoading ? 'Dream 运行中…' : '手动触发 AutoDream' }}
          </el-button>
          <el-button @click="loadNotebookMemoryStatus" :disabled="!dreamUsername">查状态</el-button>
        </el-form-item>
      </el-form>
      <pre v-if="dreamResultText" style="margin-top: 12px; padding: 12px; background: #fff; border-radius: 6px; font-size: 12px; white-space: pre-wrap; max-height: 280px; overflow: auto;">{{ dreamResultText }}</pre>
    </div>

    <!-- Chroma管理区域 -->
    <div id="chroma-section" class="chroma-management-container">
      <h2>Chroma向量库管理</h2>
      <div class="chroma-controls">
        <el-button 
          type="primary" 
          @click="triggerChromaUnlock" 
          :loading="chromaUnlockLoading"
          :disabled="chromaUnlockLoading"
        >
          {{ chromaUnlockLoading ? '解锁中...' : '手动触发解锁' }}
        </el-button>
        <el-button 
          type="info" 
          @click="refreshChromaLogs"
          :loading="logsLoading"
        >
          刷新日志
        </el-button>
        <el-button 
          type="success" 
          @click="clearChromaLogs"
        >
          清空日志
        </el-button>
      </div>
      
      <!-- Chroma状态显示 -->
      <div class="chroma-status">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Chroma解锁状态</span>
              <el-tag :type="chromaStatus.type" size="small">
                {{ chromaStatus.text }}
              </el-tag>
            </div>
          </template>
          <div class="status-info">
            <p><strong>最后执行时间:</strong> {{ chromaStatus.lastExecution || '未执行' }}</p>
            <p><strong>执行次数:</strong> {{ chromaStatus.executionCount }}</p>
            <p><strong>成功率:</strong> {{ chromaStatus.successRate }}%</p>
            <p><strong>平均耗时:</strong> {{ chromaStatus.avgDuration }}秒</p>
          </div>

          <!-- 测试耗时统计 -->
          <div class="duration-stats" v-if="testDurationStats && testDurationStats.totalExecutions > 0">
            <h4>测试耗时统计 (总执行{{ testDurationStats.totalExecutions }}次，成功{{ testDurationStats.total }}次，成功率{{ testDurationStats.successRate }}%)</h4>
            <div class="stats-grid">
              <div class="stat-item fast">
                <div class="stat-label">快速 (&lt; 0.5s)</div>
                <div class="stat-value">{{ testDurationStats.fast.count }}次</div>
                <div class="stat-percentage">{{ testDurationStats.fast.percentage }}%</div>
              </div>
              <div class="stat-item normal">
                <div class="stat-label">正常 (0.5s - 20s)</div>
                <div class="stat-value">{{ testDurationStats.normal.count }}次</div>
                <div class="stat-percentage">{{ testDurationStats.normal.percentage }}%</div>
              </div>
              <div class="stat-item slow">
                <div class="stat-label">缓慢 (&gt; 20s)</div>
                <div class="stat-value">{{ testDurationStats.slow.count }}次</div>
                <div class="stat-percentage">{{ testDurationStats.slow.percentage }}%</div>
              </div>
            </div>
          </div>
        </el-card>
      </div>

      <!-- Chroma日志显示 -->
      <div class="chroma-logs">
        <el-card>
          <template #header>
            <div class="card-header">
              <span>Chroma解锁日志</span>
              <el-button 
                type="text" 
                @click="toggleLogsAutoRefresh"
                size="small"
              >
                {{ logsAutoRefresh ? '停止自动刷新' : '开启自动刷新' }}
              </el-button>
            </div>
          </template>
          <div class="logs-container" ref="logsContainer">
            <div 
              v-for="(log, index) in displayLogs" 
              :key="index" 
              :class="['log-item', log.type]"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-message">{{ log.message }}</span>
            </div>
            <div v-if="displayLogs.length === 0" class="no-logs">
              暂无日志记录
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <!-- 模型编辑弹窗 -->
    <el-dialog title="编辑模型信息" v-model="modelEditDialogVisible" width="600px">
      <el-form :model="editingModel" label-width="120px">
        <el-form-item label="模型缩写名">
          <el-input v-model="editingModel.abbreviation" placeholder="请输入模型缩写名"></el-input>
        </el-form-item>
        <el-form-item label="模型全名">
          <el-input v-model="editingModel.fullName" placeholder="请输入模型全名"></el-input>
        </el-form-item>
        <el-form-item label="模型类型">
          <el-select v-model="editingModel.type" placeholder="请选择模型类型">
            <el-option label="OpenAI" value="openai"></el-option>
            <el-option label="HuggingFace" value="huggingface"></el-option>
            <el-option label="Anthropic" value="anthropic"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="URL 地址">
          <el-input v-model="editingModel.url" placeholder="请输入 URL 地址"></el-input>
        </el-form-item>
        <el-form-item label="API 密钥">
          <el-input
            v-model="editingModel.apiKey"
            placeholder="请输入 API 密钥"
            show-password
          ></el-input>
        </el-form-item>
        <!-- <el-form-item label="模型能力">
          <el-checkbox v-model="editingModel.isInference">推理模型</el-checkbox>
          <el-checkbox v-model="editingModel.supportsImages">支持图片</el-checkbox>
        </el-form-item> -->
        <el-form-item label="模型基本信息">
          <el-input
            v-model="editingModel.description"
            type="textarea"
            :rows="3"
            placeholder="请输入模型的基本信息描述"
          ></el-input>
        </el-form-item>
        <el-form-item label="响应速度">
          <el-select v-model="editingModel.responseSpeed" placeholder="请选择响应速度">
            <el-option label="快" value="fast"></el-option>
            <el-option label="中快" value="medium_fast"></el-option>
            <el-option label="中慢" value="medium_slow"></el-option>
            <el-option label="较慢" value="slow"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="推理水平">
          <el-select v-model="editingModel.reasoningLevel" placeholder="请选择推理水平">
            <el-option label="高-原生" value="high_native"></el-option>
            <el-option label="中-原生" value="medium_native"></el-option>
            <el-option label="低-原生" value="low_native"></el-option>
            <el-option label="高-非原生" value="high_nonnative"></el-option>
            <el-option label="中-非原生" value="medium_nonnative"></el-option>
            <el-option label="低-非原生" value="low_nonnative"></el-option>
          </el-select>
        </el-form-item>

        <el-form-item label="多模态能力">
          <el-select v-model="editingModel.multimodalLevel" placeholder="请选择多模态能力">
            <el-option label="高" value="high"></el-option>
            <el-option label="中" value="medium"></el-option>
            <el-option label="低" value="low"></el-option>
            <el-option label="无" value="none"></el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="Prompt 模板">
          <el-input
            v-model="editingModel.promptTemplate"
            type="textarea"
            :rows="3"
            placeholder="输入 Prompt 模板"
          ></el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="modelEditDialogVisible = false">取消</el-button>
          <el-button type="danger" @click="deleteModel">删除模型</el-button>
          <el-button type="primary" @click="saveModelChanges">保存修改</el-button>
        </span>
      </template>
    </el-dialog>

    <footer class="footer">
      <p>© 2026 NKCN-Brain. All rights reserved.</p>
    </footer>
  </div>
</template>

<script>
import router from '@/router'
import { ElForm, ElFormItem, ElInput, ElButton, ElDialog, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { getList, ban_user, open_user, get_onlineNum, get_userUpDownLevelInfo} from '@/api/user'
import { request_base_info, delete_model } from "@/api/chat/send_message"
import { saveDefaultModelsConfig, getDefaultModelsConfig, saveSceneModelsConfig, getSceneModelsConfig, notebookMemoryAutodream, notebookMemoryStatus } from "@/api/getData"
import { format } from 'echarts'
import { modelManager } from "@/utils/ModelManager"
import { ModelFormatter } from "@/utils/ModelFormatter"
import redirectManager from '@/config/redirectConfig'
// import { convertModelFormat } from "@/utils/modelConverter"
import { API_BASE_URL } from '@/config/apiConfig';

export default {
  components: {
    ElForm,
    ElFormItem,
    ElInput,
    ElButton,
    ElDialog,
    ElTable, 
    ElTableColumn,
    ElTag
  },
  data() {
    return {
      modelEditDialogVisible : false, // 控制编辑模型弹窗的显示
      editingModel: {}, // 用于存储正在编辑的模型信息

      onlineNum: 0,
      onlineUsername: [],
      onlineUserBookName: [],
      curUserName: '',
      userList: [], // 用于保存用户列表

      // 跳转配置相关
      currentRedirectKey: redirectManager.getCurrentTargetKey(),
      allTargets: redirectManager.getAllTargets(),
      currentRedirectTarget: redirectManager.getCurrentTarget(),

      // 三窗口默认模型配置
      defaultModels: {
        main: '1002',        // 主窗口默认GPT-4o
        topRight: '1006',    // 右上窗口默认Claude-3.5-Sonnet
        bottomRight: '1007'  // 右下窗口默认Deepseek-v3
      },

      sceneModelSlots: [],
      sceneModelValues: {},

      dreamUsername: '',
      dreamSceneName: '',
      dreamLoading: false,
      dreamResultText: '',

      userRedirectConfigs: {}, // 存储每个用户的跳转配置

      modelForm: {
        id: '',     // 模型 ID
        type: 'openai',   // 模型类型
        abbreviation: '', // 模型缩写名
        fullName: '',     // 模型全名
        url: '',          // URL 地址
        apiKey: '',       // API 密钥
        promptTemplate: '', // Prompt 模板

        responseSpeed: 'fast',      // 快、中快、中慢、较慢
        reasoningLevel: 'low_nonnative',     // 高、中、低、无
        multimodalLevel: 'none',     // 高、中、低、无
        description: '暂无描述'   // 新增：模型基本信息描述
      },
      modelBaseInfo: [], // 存储已添加的模型列表
      // modelTmpInfo: []

      // Chroma管理相关数据
      chromaUnlockLoading: false,
      logsLoading: false,
      logsAutoRefresh: false,
      logsRefreshTimer: null,
      chromaStatus: {
        type: 'info',
        text: '未知',
        lastExecution: null,
        executionCount: 0,
        successRate: 0,
        avgDuration: 0
      },
      chromaLogs: [],

      // 导航相关数据
      navCollapsed: false,
      activeSection: 'users',

      // 测试耗时统计数据
      testDurationStats: {
        fast: { count: 0, percentage: '0.0' },
        normal: { count: 0, percentage: '0.0' },
        slow: { count: 0, percentage: '0.0' },
        total: 0
      },
      // 用于显示的日志（只显示最近的一些）
      displayLogs: []
    };
  },
  async mounted() {
    // admin用户不会跳转，直接初始化页面
    try {
      await redirectManager.ensureInitialized();
      this.currentRedirectTarget = redirectManager.getCurrentTarget();
    } catch (error) {
      console.error('初始化跳转配置失败:', error);
    }

    // 加载三窗口默认模型配置
    this.loadDefaultModels();
    this.loadSceneModels();

    // 构造 FormData
    const formData = new FormData();
    formData.append('username', this.curUserName || 'admin'); // 默认使用 admin 用户名

    // 调用后端接口获取模型基本信息
    request_base_info(formData)
      .then(response => {
        if (response && response.success) {
          // 将 modelTmpInfo 的内容写入 modelBaseInfo
          this.modelBaseInfo = response.model_info_list.map(model => ({
            id: model.model_id, // 模型 ID
            // isInference: model.is_inference, // 是否支持推理
            // supportsImages: model.supports_images, // 是否支持图片
            responseSpeed: model.response_speed || 'medium_fast',
            reasoningLevel: model.reasoning_level || 'low_nonnative',
            multimodalLevel: model.multimodal_level || 'none',
            description: model.description || '暂无描述', // 模型基本信息描述

            abbreviation: model.model_name, // 模型缩写名
            fullName: model.model_full_name, // 模型全名
            url: model.model_base_url, // URL 地址
            apiKey: '', // API 密钥（默认为空）
            // type: '', // 模型类型
            type: model.model_type || 'openai', // 模型类型
            promptTemplate: '' // Prompt 模板（默认为空）
          }));
          console.log('get model_info_list: ', this.modelBaseInfo);
        } else {
          console.error('Failed to fetch model base info:', response);
          this.$message.error('获取模型基本信息失败');
        }
      })
      .catch(error => {
        console.error('An error occurred while fetching model base info:', error);
        this.$message.error('获取模型基本信息时发生错误');
      });

    this.fetchUserList();
    this.getOnlineNum();

    // 初始化Chroma管理
    this.initChromaManagement();

    // 添加滚动监听
    window.addEventListener('scroll', this.handleScroll);

    // 调试：调用方法
    this.updateTestDurationStats();
    console.log("mounted 中调用 updateTestDurationStats:", this.testDurationStats);
  },
  beforeDestroy() {
    // 移除滚动监听
    window.removeEventListener('scroll', this.handleScroll);
  },
  created() {
    this.curUserName = 'admin';
    localStorage.setItem('realName', 'admin');
    localStorage.setItem('originRealName', 'admin');
    localStorage.setItem('home2login', 'false');
  },
  computed: {
    combinedOnlineData() {
      const combined = [];
      for (let i = 0; i < this.onlineUsername.length; i++) {
        combined.push({ user: this.onlineUsername[i], userbook: this.onlineUserBookName[i] });
      }
      return combined;
    },
    sceneModelGroups() {
      const groupLabels = {
        P0: 'P0 · 建卡浅评/文档摘要/卡片助记 HTML/Group.md整理更新/卡片生图',
        P1: 'P1 · 输出目录卡（Claude 思考/校验）',
        P2: 'P2 · 连续图片理解（OCR、识字、版面精修、覆盖层等）',
        P3: 'P3 · 作业批改',
        P4: 'P4 · 语义梳理',
        P5: 'P5 · 语音合成',
      };
      const buckets = {};
      (this.sceneModelSlots || []).forEach(slot => {
        const g = slot.group || '其他';
        if (!buckets[g]) buckets[g] = [];
        buckets[g].push(slot);
      });
      return Object.keys(groupLabels)
        .filter(g => buckets[g] && buckets[g].length)
        .map(g => ({ name: g, label: groupLabels[g], slots: buckets[g] }));
    },
  },
  methods: {
    // 从动态模型列表中获取模型名称
    getModelNameById(modelId) {
      const model = this.modelBaseInfo.find(m => m.id === modelId);
      return model ? model.abbreviation : '未选择';
    },
    
    // 加载三窗口默认模型配置
    async loadDefaultModels() {
      try {
        const response = await getDefaultModelsConfig();
        if (response.error_num === 0) {
          this.defaultModels = response.config;
          console.log('[Admin] 从服务器加载三窗口默认模型配置:', this.defaultModels);
        } else {
          console.error('[Admin] 加载默认模型配置失败:', response.message);
          this.$message.error('加载配置失败');
        }
      } catch (e) {
        console.error('[Admin] 加载默认模型配置异常:', e);
        this.$message.error('加载配置失败');
      }
    },
    
    // 保存三窗口默认模型配置
    async saveDefaultModels() {
      try {
        const response = await saveDefaultModelsConfig(this.defaultModels);
        if (response.error_num === 0) {
          console.log('[Admin] 保存三窗口默认模型配置到服务器:', this.defaultModels);
          this.$message.success('三窗口默认模型配置已保存！所有用户下次登录时将使用这些默认模型。');
        } else {
          console.error('[Admin] 保存默认模型配置失败:', response.message);
          this.$message.error('保存配置失败: ' + response.message);
        }
      } catch (e) {
        console.error('[Admin] 保存默认模型配置异常:', e);
        this.$message.error('保存配置失败');
      }
    },

    async loadSceneModels() {
      try {
        const response = await getSceneModelsConfig();
        if (response.error_num === 0) {
          this.sceneModelSlots = response.slots || [];
          const values = {};
          (response.slots || []).forEach(slot => {
            values[slot.key] = slot.value || slot.default;
          });
          this.sceneModelValues = values;
        } else {
          this.$message.error('加载场景模型配置失败: ' + (response.message || ''));
        }
      } catch (e) {
        console.error('[Admin] 加载场景模型配置异常:', e);
        this.$message.error('加载场景模型配置失败');
      }
    },

    async saveSceneModels() {
      try {
        const editableValues = {};
        (this.sceneModelSlots || []).forEach(slot => {
          if (slot.type === 'display_only' || slot.editable === false) return;
          editableValues[slot.key] = this.sceneModelValues[slot.key];
        });
        const response = await saveSceneModelsConfig({ values: editableValues });
        if (response.error_num === 0) {
          this.$message.success('场景模型配置已保存，立即生效。');
          await this.loadSceneModels();
        } else {
          this.$message.error('保存失败: ' + (response.message || ''));
        }
      } catch (e) {
        console.error('[Admin] 保存场景模型配置异常:', e);
        this.$message.error('保存场景模型配置失败');
      }
    },

    async triggerNotebookMemoryDream() {
      const username = (this.dreamUsername || '').trim();
      if (!username) {
        this.$message.warning('请填写本子键（账户_本子）');
        return;
      }
      this.dreamLoading = true;
      this.dreamResultText = '';
      try {
        const response = await notebookMemoryAutodream({
          username,
          sceneName: (this.dreamSceneName || '').trim(),
        });
        this.dreamResultText = JSON.stringify(response, null, 2);
        if (response && response.error_num === 0) {
          this.$message.success(response.msg || 'AutoDream 完成');
        } else {
          this.$message.error((response && response.msg) || 'AutoDream 失败');
        }
      } catch (e) {
        console.error('[Admin] AutoDream 异常:', e);
        this.dreamResultText = String(e);
        this.$message.error('AutoDream 请求失败');
      } finally {
        this.dreamLoading = false;
      }
    },

    async loadNotebookMemoryStatus() {
      const username = (this.dreamUsername || '').trim();
      if (!username) {
        this.$message.warning('请填写本子键');
        return;
      }
      try {
        const response = await notebookMemoryStatus({ username });
        this.dreamResultText = JSON.stringify(response, null, 2);
        if (response && response.error_num === 0) {
          this.$message.success('已拉取记忆状态');
        } else {
          this.$message.error((response && response.msg) || '查状态失败');
        }
      } catch (e) {
        console.error('[Admin] 记忆状态异常:', e);
        this.dreamResultText = String(e);
        this.$message.error('查状态请求失败');
      }
    },
    
    getUserRedirectTarget(username) {
      return this.userRedirectConfigs[username] || 'NONE';
    },

    async changeUserRedirect(username, targetKey) {
      try {
        await redirectManager.setUserTarget(username, targetKey);
        // 更新本地缓存
        this.userRedirectConfigs[username] = targetKey;
        this.$message.success(`已设置 ${username} 的跳转配置`);
      } catch (error) {
        this.$message.error('设置失败: ' + error.message);
      }
    },

    // 优化loadUserRedirectConfigs
    async loadUserRedirectConfigs() {
      try {
        // 先初始化所有用户的默认配置
        const defaultConfigs = {};
        this.userList.forEach(user => {
          defaultConfigs[user.username] = 'NONE';
        });
        this.userRedirectConfigs = { ...defaultConfigs };
        
        // 然后从服务器加载实际配置
        const formData = new FormData();
        formData.append('username', 'admin');
        // 需要先导入API_BASE_URL
        const { default: API_BASE_URL } = await import('@/config/apiConfig');
        const response = await fetch(`${API_BASE_URL}/api/get_all_user_redirect_configs`, {
          method: 'POST',
          body: formData
        });
        const result = await response.json();
        if (result.error_num === 0) {
          // this.userRedirectConfigs = result.configs || {};
          // 合并服务器配置
          this.userRedirectConfigs = { ...defaultConfigs, ...result.configs };
        }
      } catch (error) {
        console.error('加载用户跳转配置失败:', error);
      }
    },

    // 跳转目标切换
    async changeRedirectTarget(targetKey) {
      try {
        // 显示加载消息
        const loadingMessage = this.$message({
          message: '正在保存配置...',
          type: 'info',
          duration: 0, // 不自动关闭
        });
        
        const success = await redirectManager.setTarget(targetKey);
        
        // 关闭加载消息
        loadingMessage.close();
        
        if (success) {
          await redirectManager.ensureInitialized();
          this.currentRedirectTarget = redirectManager.getCurrentTarget();
          
          if (targetKey === 'NONE') {
            this.$message.success('已取消跳转设置并保存到服务器');
          } else {
            this.$message.success(`已设置跳转到 ${this.currentRedirectTarget.name} 并保存到服务器`);
          }
          
          // admin用户不会跳转，但其他用户会受影响
          this.$message.info('配置已生效，其他用户访问时会自动跳转到设置的服务器');
        } else {
          this.$message.error('设置跳转目标失败');
        }
      } catch (error) {
        console.error('设置跳转目标出错:', error);
        this.$message.error('设置跳转目标失败: ' + (error.message || '未知错误'));
      }
    },

    // 打开编辑模型弹窗
    editModelInfo(model) {
      this.editingModel = JSON.parse(JSON.stringify(model)); // 深拷贝避免直接修改原数据
      this.modelEditDialogVisible = true;
    },

    // 保存模型修改
    saveModelChanges() {
      // 1. 验证必填字段
      if (!this.editingModel.abbreviation || !this.editingModel.fullName) {
        this.$message.error('请至少填写模型缩写名、全名和API密钥');
        return;
      }

      try {
        // 2. 在modelBaseInfo数组中找到并更新对应的模型
        const modelIndex = this.modelBaseInfo.findIndex(model => model.id === this.editingModel.id);
        if (modelIndex !== -1) {
          // 3. 调用modelManager更新本地存储
          // 注意：这里假设modelManager有updateModel方法，实际使用时需确认
          modelManager.updateModel(this.editingModel).then(() => {
            // 4. 更新本地数组中的模型数据
            this.modelBaseInfo[modelIndex] = JSON.parse(JSON.stringify(this.editingModel));

            // 5. 显示成功消息
            this.$message.success('模型信息更新成功');
            
            // 6. 关闭编辑弹窗
            this.modelEditDialogVisible = false;
          }).catch(error => {
            console.error('更新模型失败:', error);
            this.$message.error(`更新失败: ${error.message}`);
          });
        } else {
          this.$message.error('未找到要更新的模型');
        }
      } catch (error) {
        console.error('保存模型修改时发生错误:', error);
        this.$message.error(`操作失败: ${error.message}`);
      }
    },

    // 删除模型
    deleteModel() {
      // 1. 显示确认对话框
      this.$confirm('此操作将永久删除该模型, 是否继续?', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        try {
          // 2. 调用modelManager从本地存储中删除模型
          // 注意：这里假设modelManager有deleteModel方法，实际使用时需确认
          modelManager.deleteModel(this.editingModel.id).then(() => {
            // 3. 从modelBaseInfo数组中过滤掉该模型
            this.modelBaseInfo = this.modelBaseInfo.filter(model => model.id !== this.editingModel.id);
            
            // 4. 构造FormData并发送到后端API
            const formData = new FormData();
            formData.append('model_id', this.editingModel.id);
            formData.append('username', 'admin'); // 确保有权限验证

            delete_model(formData).then(response => {
              if (response && response.success) {
                this.$message.success('模型已成功删除');
              } else {
                this.$message.error('删除模型失败：' + (response.message || '未知错误'));
              }
            }).catch(error => {
              console.error('删除模型时发生错误:', error);
              this.$message.error('删除模型时发生网络错误');
            });
            
            // 5. 关闭编辑弹窗
            this.modelEditDialogVisible = false;
          }).catch(error => {
            console.error('删除模型失败:', error);
            this.$message.error(`删除失败: ${error.message}`);
          });
        } catch (error) {
          console.error('删除模型时发生错误:', error);
          this.$message.error(`操作失败: ${error.message}`);
        }
      }).catch(() => {
        // 用户取消删除操作
        this.$message.info('已取消删除操作');
      });
    },

    async addModel() {
      // 验证必填字段
      if (!this.modelForm.abbreviation || !this.modelForm.fullName || !this.modelForm.apiKey) {
        this.$message.error('请至少填写模型缩写名、全名和API密钥');
        return;
      }

      const existingModel = this.modelBaseInfo.find(model => model.abbreviation === this.modelForm.abbreviation);
      if (existingModel) {
        this.$message.error('模型缩写名已存在，请使用其他名称');
        return;
      }

      // 创建模型对象
      const rawModel = {
        id: null, // 模型 ID 由后端生成
        abbreviation: this.modelForm.abbreviation,
        fullName: this.modelForm.fullName,
        url: this.modelForm.url,
        apiKey: this.modelForm.apiKey,
        promptTemplate: this.modelForm.promptTemplate,
        type: this.modelForm.type,
        // isInference: this.modelForm.isInference,
        // supportsImages: this.modelForm.supportsImages
        responseSpeed: this.modelForm.responseSpeed,
        reasoningLevel: this.modelForm.reasoningLevel,
        multimodalLevel: this.modelForm.multimodalLevel,
        description: this.modelForm.description,
      };

      try {
        // ========== 第一步：调用ModelManager，保存到模型列表与本地 ==========
        const format3Model = await modelManager.addModelFromForm(rawModel);
        
        // ========== 第二步：更新ID并添加到modelBaseInfo ==========
        rawModel.id = format3Model.id; // 获取生成的ID
        this.modelBaseInfo.push(rawModel); // 添加格式3数据

        // ========== 第三步：发送到后端的接口中（格式4） ==========

        this.$message.success('模型添加成功');
        this.resetModelForm(); // 清空表单

      } catch (error) {
        console.error('添加模型失败:', error);
        this.$message.error(`添加失败: ${error.message}`);
      }
    },

    resetModelForm() {
      this.modelForm = {
        id: '',
        type: 'openai',
        abbreviation: '',
        fullName: '',
        url: '',
        apiKey: '',
        promptTemplate: '',

        responseSpeed: 'fast',
        reasoningLevel: 'low_nonnative',
        multimodalLevel: 'none',
        description: '暂无描述'
        // isInference: false,
        // supportsImages: false
      };
    },

    getModelTypeDisplayName(type) {
      const typeNames = {
        'openai': 'OpenAI',
        'huggingface': 'HuggingFace',
        'anthropic': 'Anthropic'
      };
      
      return typeNames[type] || '未知';
    },
    getModelTypeTagType(type) {
      const tagTypes = {
        'openai': 'primary',
        'huggingface': 'success',
        'anthropic': 'warning'
      };
      
      return tagTypes[type] || 'info';
    },

    backtologin() {
      localStorage.setItem('home2login', 'true');
      router.push('/');
    },
    getLevelName(level) {
      const levelNames = {
        'S': '超级组织电脑',
        'T': '教师',
        'TA': 'TA助教',
        'GL': '组长',
        'GM': '组员'
      };
      
      return levelNames[level] || '未设置';
    },
    editUser(row) {
      localStorage.setItem('userId', row.username);
      localStorage.setItem('realName', row.username);
      localStorage.setItem('originRealName', row.username);
      localStorage.setItem('byadmin', 'true');
      localStorage.setItem('fromPath', '/adminhome')

      let formData = new FormData();
      formData.append('username', localStorage.getItem('originRealName'));
      get_userUpDownLevelInfo(formData).then(data => {
        if(data['error_num'] === 0) {
          localStorage.setItem('coacherName', data['coacher']);
          localStorage.setItem('level', data['level']);
          router.push('/home');
        } else {
          this.$message.error(data['message'])
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });

      // router.push('/home');
    },
    banUser(row) {
      let formData = new FormData();
      formData.append('username', row.username);
      ban_user(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('操作成功');
          // 更新本地状态，避免重新请求整个列表
          const userIndex = this.userList.findIndex(user => user.id === row.id);
          if (userIndex !== -1) {
            this.userList[userIndex].allowed = 0;
          }
        } else {
          this.$message.error('操作失败');
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
        this.$message.error('操作失败');
      });
    },
    openUser(row) {
      let formData = new FormData();
      formData.append('username', row.username);
      open_user(formData).then(response => {
        if (response.error_num === 0) {
          this.$message.success('操作成功');
          // 更新本地状态，避免重新请求整个列表
          const userIndex = this.userList.findIndex(user => user.id === row.id);
          if (userIndex !== -1) {
            this.userList[userIndex].allowed = 1;
          }
        } else {
          this.$message.error('操作失败');
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
        this.$message.error('操作失败');
      });
    },
    getOnlineNum() {
      let formData = new FormData();
      formData.append('username', localStorage.getItem('userId'));
      get_onlineNum(formData).then(data => {
        if(data['error_num'] === 0) {
          this.onlineNum = data['onlineNum']
          this.onlineUsername = data['onlineUsername']
          this.onlineUserBookName = data['onlineUserBookName']
        }
      }).catch(error => {
        console.error("An error occurred:", error); // 错误处理
      });
    },
    fetchUserList() {
      getList().then(response => {
        if (response.error_num === 0) {
          this.userList = response.list.map(user => {
            return {
              id: user.pk,
              username: user.fields.username,
              allowed: user.fields.allowed, // 添加allowed字段
              coacher: user.fields.coacher, // 添加此字段，用于admin审核
              level: user.fields.level // 添加此字段，用于admin审核
            };
          }).filter(user => user.username !== 'admin')   // 过滤掉 username 为 'admin'
          .reverse(); // 反转列表顺序

          // 获取用户列表后，加载跳转配置
          this.loadUserRedirectConfigs();
        } else {
          this.$message.error('获取用户列表失败');
        }
      })
    },
    gotoUse() {
      // 通过他人用户名查看信息后，返回时改回admin自身信息
      localStorage.setItem('userId', 'admin');
      localStorage.setItem('realName', 'admin');
      localStorage.setItem('originRealName', 'admin');
      localStorage.setItem('fromPath', '/adminhome')
      router.push('/home');
    },

    // Chroma管理相关方法
    initChromaManagement() {
      // 初始化Chroma状态
      this.refreshChromaStatus();
      // 加载初始日志
      this.refreshChromaLogs();
    },

    // 更新测试耗时统计的方法
    updateTestDurationStats() {
      console.log("updateTestDurationStats 被调用", this.chromaLogs);
      
      // 确保 chromaLogs 存在且为数组
      if (!this.chromaLogs || !Array.isArray(this.chromaLogs)) {
        console.log("chromaLogs 不存在或不是数组，重置为默认值");
        this.testDurationStats = {
          fast: { count: 0, percentage: '0.0' },
          normal: { count: 0, percentage: '0.0' },
          slow: { count: 0, percentage: '0.0' },
          total: 0
        };
        return;
      }
      
      const logs = this.chromaLogs;
      // 与后端保持一致：只统计包含'Chroma解锁测试完成'的日志
      const executionLogs = logs.filter(log => 
        log && log.message && typeof log.message === 'string' && 
        log.message.includes('Chroma解锁测试完成')
      );
      
      // 从执行日志中筛选出有耗时信息的日志
      const durationLogs = executionLogs.filter(log => 
        log.message.includes('耗时:') && log.message.includes('秒')
      );
      
      console.log("总执行次数:", executionLogs.length, "条");
      console.log("有耗时信息的执行:", durationLogs.length, "条");
      
      let fastCount = 0;    // < 0.5s
      let normalCount = 0;  // 0.5s - 20s
      let slowCount = 0;    // > 20s
      
      durationLogs.forEach(log => {
        try {
          const match = log.message.match(/耗时:\s*([\d.]+)秒/);
          if (match) {
            const duration = parseFloat(match[1]);
            if (!isNaN(duration)) {
              if (duration < 0.5) {
                fastCount++;
              } else if (duration <= 20) {
                normalCount++;
              } else {
                slowCount++;
              }
            }
          }
        } catch (error) {
          console.warn('解析日志耗时失败:', error, log);
        }
      });
      
      const total = fastCount + normalCount + slowCount;
      const totalExecutions = executionLogs.length;
      const successRate = totalExecutions > 0 ? (total / totalExecutions * 100).toFixed(1) : '0.0';
      
      console.log("统计结果:", { 
        fastCount, normalCount, slowCount, 
        total, totalExecutions, successRate 
      });
      
      // 直接更新 data 变量
      this.testDurationStats = {
        fast: { count: fastCount, percentage: total > 0 ? (fastCount / total * 100).toFixed(1) : '0.0' },
        normal: { count: normalCount, percentage: total > 0 ? (normalCount / total * 100).toFixed(1) : '0.0' },
        slow: { count: slowCount, percentage: total > 0 ? (slowCount / total * 100).toFixed(1) : '0.0' },
        total: total,
        totalExecutions: totalExecutions,
        successRate: successRate
      };
      
      console.log("更新后的 testDurationStats:", this.testDurationStats);
    },

    async triggerChromaUnlock() {
      this.chromaUnlockLoading = true;
      try {
        // 需要先导入API_BASE_URL
        const { default: API_BASE_URL } = await import('@/config/apiConfig');
        const response = await fetch(`${API_BASE_URL}/api/force_chroma_unlock`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({})
        });
        
        const result = await response.json();
        
        if (result.error_num === 0) {
          this.$message.success('Chroma解锁测试已触发');
          // 添加成功日志
          this.addChromaLog('success', `手动触发解锁成功: ${result.message}`);
          // 刷新状态
          this.refreshChromaStatus();
        } else {
          this.$message.error(`触发失败: ${result.message}`);
          this.addChromaLog('error', `手动触发解锁失败: ${result.message}`);
        }
      } catch (error) {
        console.error('触发Chroma解锁失败:', error);
        this.$message.error('触发Chroma解锁失败');
        this.addChromaLog('error', `触发Chroma解锁失败: ${error.message}`);
      } finally {
        this.chromaUnlockLoading = false;
      }
    },

    async refreshChromaStatus() {
      try {
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取

        const response = await fetch(`${BASE_URL}/api/get_chroma_status`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({})
        });
        
        const result = await response.json();
        
        if (result.error_num === 0) {
          this.chromaStatus = result.data;
        } else {
          console.error('获取Chroma状态失败:', result.message);
          // 使用默认状态
          this.chromaStatus = {
            type: 'warning',
            text: '状态未知',
            lastExecution: null,
            executionCount: 0,
            successRate: 0,
            avgDuration: 0
          };
        }
      } catch (error) {
        console.error('获取Chroma状态失败:', error);
        // 使用默认状态
        this.chromaStatus = {
          type: 'error',
          text: '连接失败',
          lastExecution: null,
          executionCount: 0,
          successRate: 0,
          avgDuration: 0
        };
      }
    },

    async refreshChromaLogs() {
      this.logsLoading = true;
      try {
        const BASE_URL = API_BASE_URL; // 统一从配置文件获取

        const response = await fetch(`${BASE_URL}/api/get_chroma_logs`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({})
        });

        // 同时刷新日志和状态
        const [logsResponse, statusResponse] = await Promise.all([
          fetch(`${BASE_URL}/api/get_chroma_logs`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
          }),
          fetch(`${BASE_URL}/api/get_chroma_status`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
          })
        ]);
        
        const logsResult = await logsResponse.json();
        const statusResult = await statusResponse.json();
        
        if (logsResult.error_num === 0) {
          this.chromaLogs = logsResult.data;
          // 只显示最近50条日志
          this.displayLogs = (logsResult.data || []).slice(-50);
          console.log("refreshChromaLogs 更新后，总日志数:", this.chromaLogs.length, "显示日志数:", this.displayLogs.length);

          // 更新状态信息
          if (statusResult.error_num === 0) {
            this.chromaStatus = statusResult.data;
            console.log("状态信息已更新:", this.chromaStatus);
          }

          this.$nextTick(() => {
            this.scrollToBottom();
            // 在DOM更新后再次更新统计
            this.updateTestDurationStats();
            console.log("DOM更新后调用 updateTestDurationStats:", this.testDurationStats);
          });
        } else {
          console.error('获取Chroma日志失败:', logsResult.message);
          this.$message.error('获取日志失败');
          // 使用默认日志
          this.chromaLogs = [{
            time: new Date().toLocaleString(),
            message: '获取日志失败',
            type: 'error'
          }];
        }
      } catch (error) {
        console.error('刷新Chroma日志失败:', error);
        this.$message.error('刷新日志失败');
        // 使用默认日志
        this.chromaLogs = [{
          time: new Date().toLocaleString(),
          message: '连接失败',
          type: 'error'
        }];
      } finally {
        this.logsLoading = false;
      }
    },

    addChromaLog(type, message) {
      const log = {
        time: new Date().toLocaleString(),
        message: message,
        type: type
      };
      this.chromaLogs.unshift(log);
      
      // 限制日志数量，最多保留100条
      if (this.chromaLogs.length > 100) {
        this.chromaLogs = this.chromaLogs.slice(0, 100);
      }

      // 更新显示日志（只显示最近50条）
      this.displayLogs = this.chromaLogs.slice(-50);
      
      this.scrollToBottom();
    },

    clearChromaLogs() {
      this.$confirm('确定要清空所有日志吗？', '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        this.chromaLogs = [];
        this.$message.success('日志已清空');
      });
    },

    toggleLogsAutoRefresh() {
      this.logsAutoRefresh = !this.logsAutoRefresh;
      
      if (this.logsAutoRefresh) {
        // 开启自动刷新，每30秒刷新一次
        this.logsRefreshTimer = setInterval(() => {
          this.refreshChromaLogs();
        }, 30000);
        this.$message.success('已开启自动刷新');
      } else {
        // 关闭自动刷新
        if (this.logsRefreshTimer) {
          clearInterval(this.logsRefreshTimer);
          this.logsRefreshTimer = null;
        }
        this.$message.info('已关闭自动刷新');
      }
    },

    scrollToBottom() {
      this.$nextTick(() => {
        const container = this.$refs.logsContainer;
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      });
    },

    // 导航相关方法
    toggleNav() {
      this.navCollapsed = !this.navCollapsed;
    },

    scrollToSection(section) {
      this.activeSection = section;
      const element = document.getElementById(section + '-section');
      if (element) {
        element.scrollIntoView({ 
          behavior: 'smooth',
          block: 'start'
        });
      }
    },

    handleScroll() {
      // 监听滚动，更新当前激活的section
      const sections = ['users', 'models', 'chroma'];
      for (let section of sections) {
        const element = document.getElementById(section + '-section');
        if (element) {
          const rect = element.getBoundingClientRect();
          if (rect.top <= 100 && rect.bottom >= 100) {
            this.activeSection = section;
            break;
          }
        }
      }
    }
  },

};
</script>

<style scoped>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
  font-family: 'Arial', sans-serif;
}

/* 全局背景动画 */
.notebook-homepage {
  /* 深色调和冷色调的线性渐变背景 */
  background: linear-gradient(-45deg, #6767bd, #667bb5, #96acc8, #afa1ab);
  background-size: 400% 400%;
  animation: gradientBG 15s ease infinite;
  position: relative;
  overflow: hidden;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

/* 动态粒子效果 */
.notebook-homepage::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: url('https://cdn.jsdelivr.net/gh/wxsms/uiv@main/docs/.vuepress/public/dots.svg');
  background-size: cover;
  opacity: 0.2;
  pointer-events: none;
}

/* 模型表单容器 */
.model-form-container {
  margin: 20px 0;
  padding: 20px;
  background-color: #f9f9f9;
  border-radius: 8px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

/* 模型列表容器 */
.model-list-container {
  margin-top: 20px;
  padding: 20px;
  background-color: #f9f9f9;
  border-radius: 8px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

/* 动画效果 */
@keyframes gradientBG {
  0% {
    background-position: 0% 50%;
  }

  50% {
    background-position: 100% 50%;
  }

  100% {
    background-position: 0% 50%;
  }
}

/* 调整内容区域的背景和阴影 */
.content {
  background-color: rgba(231, 231, 231, 0.8);
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(5px);
  padding: 30px;
  color: #363636;
  z-index: 10;
}

/* 其他样式保持不变 */
/* 容器样式 */
.notebook-homepage {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  min-height: 100vh;
  background-color: #f5f5f5;
  padding: 20px;
}

/* 头部样式 */
.header {
  margin-bottom: 30px;
  color: #333;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 20px;
}

.header h1 {
  font-size: 2.5em;
  margin-right: 50px;
}

.header button {
  background-color: #fff;
  color: black;
  font-size: medium;

  width: 150px;
  height: 50px;

  margin-top: 8px;

  &:hover {
    background-color: #1896da;
  }
}

/* 跳转配置样式 */
.redirect-config-container {
  display: flex;
  align-items: center;
  gap: 10px;
  background-color: #f8f9fa;
  padding: 10px 15px;
  border-radius: 8px;
  border: 1px solid #e9ecef;
  margin-right: auto;
}

.redirect-config-container label {
  font-weight: 500;
  color: #495057;
  white-space: nowrap;
}

.current-redirect-info {
  font-size: 12px;
  color: #28a745;
  font-weight: 500;
  background-color: #d4edda;
  padding: 2px 8px;
  border-radius: 4px;
  white-space: nowrap;
}

/* 内容样式 */
.content {
  width: 100%;
  max-width: 800px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  padding: 30px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* 操作按钮样式 */
.actions {
  display: flex;
  gap: 10px;
  justify-content: center;
}


.action-button {
  margin-left: 10px;
  border: none;
  transform: scale(0.95);
  border-radius: 4px;
  background-color: #1a73e8;
  color: white;
  font-size: 1em;
  cursor: pointer;
  transition: background-color 0.3s;
}

.action-button:hover {
  background-color: #0d47a1;
}


/* 页脚样式 */
.footer {
  margin-top: 30px;
  color: #666;
  text-align: center;
  font-size: 0.8em;
  padding: 10px;
  border-top: 1px solid #eaeaea;
}

.footer {
  display: flex;
  justify-content: flex-end;
  /* 按钮组靠右对齐 */
  gap: 10px;
  /* 按钮之间的间距 */
}

.footer .el-button {
  padding: 10px 20px;
  /* 按钮的内边距 */
  border-radius: 4px;
  /* 按钮的边框圆角 */
  font-size: 1em;
  /* 按钮的字体大小 */
}



.online-users-container {
  margin: 20px;
  padding: 10px;
  border: 1px solid #eaeaea;
  border-radius: 4px;
}

.online-users-container h3 {
  margin-bottom: 10px;
}

.online-users-container ul {
  list-style-type: none;
  padding: 0;
}

.online-users-container li {
  margin: 5px 0;
  font-size: 16px;
}

.status-dot {
  display: inline-block;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  vertical-align: middle;
}

.disabled-dot {
  background-color: #c0c4cc; /* 灰色 - 都不支持 */
}

.inference-dot {
  background-color: #409EFF; /* 蓝色 - 仅推理 */
}

.image-dot {
  background-color: #F56C6C; /* 红色 - 仅图片 */
}

.both-dot {
  background-color: #8A2BE2; /* 紫色 - 推理+图片 */
}



/* Chroma管理区域样式 */
.chroma-management-container {
  margin: 20px 0;
  padding: 20px;
  background-color: #f9f9f9;
  border-radius: 8px;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
}

.chroma-management-container h2 {
  color: #333;
  margin-bottom: 20px;
  font-size: 1.5em;
}

.chroma-controls {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.chroma-status {
  margin-bottom: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.status-info {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}

.status-info p {
  margin: 5px 0;
  font-size: 14px;
}

.chroma-logs {
  margin-top: 20px;
}

.logs-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  padding: 10px;
  background-color: #fafafa;
}

.log-item {
  display: flex;
  margin-bottom: 8px;
  padding: 5px;
  border-radius: 3px;
  font-size: 13px;
}

.log-item.success {
  background-color: #f0f9ff;
  border-left: 3px solid #10b981;
}

.log-item.error {
  background-color: #fef2f2;
  border-left: 3px solid #ef4444;
}

.log-item.info {
  background-color: #f8fafc;
  border-left: 3px solid #3b82f6;
}

.log-time {
  color: #666;
  margin-right: 10px;
  white-space: nowrap;
  min-width: 150px;
}

.log-message {
  color: #333;
  flex: 1;
}

.no-logs {
  text-align: center;
  color: #999;
  font-style: italic;
  padding: 20px;
}



/* 测试耗时统计样式 */
.duration-stats {
  margin-top: 20px;
  padding: 15px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.duration-stats h4 {
  margin: 0 0 15px 0;
  color: #333;
  font-size: 16px;
  font-weight: 600;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 15px;
}

.stat-item {
  padding: 12px;
  border-radius: 6px;
  text-align: center;
  border: 2px solid transparent;
  transition: all 0.3s ease;
}

.stat-item.fast {
  background: #e8f5e8;
  border-color: #4caf50;
}

.stat-item.normal {
  background: #e3f2fd;
  border-color: #2196f3;
}

.stat-item.slow {
  background: #ffebee;
  border-color: #f44336;
}

.stat-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 5px;
  font-weight: 500;
}

.stat-value {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 3px;
}

.stat-item.fast .stat-value {
  color: #2e7d32;
}

.stat-item.normal .stat-value {
  color: #1976d2;
}

.stat-item.slow .stat-value {
  color: #c62828;
}

.stat-percentage {
  font-size: 14px;
  font-weight: 600;
  opacity: 0.8;
}



/* 左侧悬浮导航栏样式 */
.floating-nav {
  position: fixed;
  left: 20px;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(255, 255, 255, 0.95);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  z-index: 1000;
  transition: all 0.3s ease;
  min-width: 200px;
}

.floating-nav.nav-collapsed {
  min-width: 50px;
}

.nav-toggle {
  padding: 12px;
  text-align: center;
  cursor: pointer;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
  color: #666;
  transition: color 0.3s ease;
}

.nav-toggle:hover {
  color: #409eff;
}

.nav-content {
  padding: 16px 0;
}

.nav-title {
  padding: 0 16px 12px;
  font-size: 14px;
  font-weight: 600;
  color: #333;
  border-bottom: 1px solid rgba(0, 0, 0, 0.1);
  margin-bottom: 12px;
}

.nav-items {
  display: flex;
  flex-direction: column;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  transition: all 0.3s ease;
  color: #666;
  border-left: 3px solid transparent;
}

.nav-item:hover {
  background: rgba(64, 158, 255, 0.1);
  color: #409eff;
}

.nav-item.active {
  background: rgba(64, 158, 255, 0.15);
  color: #409eff;
  border-left-color: #409eff;
}

.nav-item i {
  margin-right: 8px;
  font-size: 16px;
  width: 20px;
  text-align: center;
  transition: all 0.3s ease;
}

.nav-item span {
  font-size: 14px;
  font-weight: 500;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .floating-nav {
    left: 10px;
    min-width: 180px;
  }
  
  .floating-nav.nav-collapsed {
    min-width: 40px;
  }
}



/* 自定义图标基础样式 */
.custom-icon {
  display: inline-block;
  position: relative;
  width: 18px;
  height: 18px;
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.custom-icon:hover {
  transform: scale(1.1);
}

/* 展开图标 */
.icon-expand {
  color: #409eff;
}

.icon-expand::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-radius: 3px;
  background: linear-gradient(45deg, transparent 40%, currentColor 40%, currentColor 60%, transparent 60%);
}

.icon-expand::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%) rotate(90deg);
  width: 6px;
  height: 2px;
  background: currentColor;
  border-radius: 1px;
}

.icon-expand:hover {
  color: #66b1ff;
  filter: drop-shadow(0 0 8px rgba(64, 158, 255, 0.4));
}

/* 折叠图标 */
.icon-fold {
  color: #409eff;
}

.icon-fold::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 14px;
  height: 14px;
  border: 2px solid currentColor;
  border-radius: 3px;
}

.icon-fold::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 6px;
  height: 2px;
  background: currentColor;
  border-radius: 1px;
}

.icon-fold:hover {
  color: #66b1ff;
  filter: drop-shadow(0 0 8px rgba(64, 158, 255, 0.4));
  transform: scale(1.1) rotate(180deg);
}

/* 用户图标 */
.icon-user {
  color: #67c23a;
}

.icon-user::before {
  content: '';
  position: absolute;
  top: 2px;
  left: 50%;
  transform: translateX(-50%);
  width: 6px;
  height: 6px;
  background: currentColor;
  border-radius: 50%;
}

.icon-user::after {
  content: '';
  position: absolute;
  bottom: 2px;
  left: 50%;
  transform: translateX(-50%);
  width: 14px;
  height: 8px;
  background: currentColor;
  border-radius: 7px 7px 0 0;
}

.icon-user:hover {
  color: #85ce61;
  filter: drop-shadow(0 2px 4px rgba(103, 194, 58, 0.3));
  transform: translateY(-1px) scale(1.05);
}

/* CPU图标 */
.icon-cpu {
  color: #e6a23c;
}

.icon-cpu::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 10px;
  height: 10px;
  border: 2px solid currentColor;
  border-radius: 2px;
  background: linear-gradient(45deg, transparent 25%, currentColor 25%, currentColor 75%, transparent 75%),
              linear-gradient(-45deg, transparent 25%, currentColor 25%, currentColor 75%, transparent 75%);
  background-size: 3px 3px;
  background-position: 0 0, 1px 1px;
}

.icon-cpu::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  right: 3px;
  bottom: 3px;
  border: 1px solid currentColor;
  border-radius: 1px;
}

.icon-cpu:hover {
  color: #ebb563;
  filter: drop-shadow(0 0 12px rgba(230, 162, 60, 0.4));
  transform: scale(1.1) rotate(5deg);
}

/* 连接图标 */
.icon-connection {
  color: #f56c6c;
  background: linear-gradient(90deg, transparent 0%, transparent 40%, currentColor 40%, currentColor 60%, transparent 60%, transparent 100%);
  background-position: center;
  background-repeat: no-repeat;
  background-size: 100% 2px;
}

.icon-connection::before {
  content: '';
  position: absolute;
  top: 50%;
  left: 15%;
  transform: translateY(-50%);
  width: 5px;
  height: 5px;
  border: 2px solid currentColor;
  border-radius: 50%;
  background: currentColor;
}

.icon-connection::after {
  content: '';
  position: absolute;
  top: 50%;
  right: 15%;
  transform: translateY(-50%);
  width: 5px;
  height: 5px;
  border: 2px solid currentColor;
  border-radius: 50%;
  background: currentColor;
}

.icon-connection:hover {
  color: #f78989;
  filter: drop-shadow(0 0 10px rgba(245, 108, 108, 0.4));
}
</style>
  