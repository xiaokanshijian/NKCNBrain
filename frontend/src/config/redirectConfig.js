// 浏览器访问跳转配置管理
const REDIRECT_CONFIG = {
  // 可选的跳转目标
  TARGETS: {
    SILICON_VALLEY: {
      name: '硅谷服务器',
      url: (process.env.VUE_APP_APP_URL || "http://localhost:8000"),
      description: '硅谷应用服务器'
    },
    CHINA: {
      name: '国内服务器', 
      url: (process.env.VUE_APP_SERVICE_8000_URL || "http://localhost:8000"),
      description: '国内应用服务器'
    },
    LOCAL: {
      name: '本地开发',
      url: 'http://localhost:8080',
      description: '本地开发环境'
    }
  },

  // 默认不跳转
  DEFAULT_TARGET: null,

  // 存储键名
  STORAGE_KEY: 'nkcn_redirect_target'
};

class RedirectManager {
  constructor() {
    this.currentTarget = null;
    this.initialized = false;
    this.initPromise = this.initialize();
  }

  // 异步初始化
  async initialize() {
    try {
      this.currentTarget = await this.loadTarget();
      this.initialized = true;
      console.log('[RedirectManager] 初始化完成:', this.currentTarget?.name || '无跳转');
    } catch (error) {
      console.error('[RedirectManager] 初始化失败:', error);
      this.currentTarget = null;
      this.initialized = true;
    }
  }

  // 确保初始化完成
  async ensureInitialized() {
    if (!this.initialized) {
      await this.initPromise;
    }
  }

  // 获取当前跳转目标
  getCurrentTarget() {
    return this.currentTarget;
  }

  // 设置跳转目标
  async setTarget(targetKey) {
    try {
      if (!targetKey || targetKey === 'NONE') {
        this.currentTarget = null;
        // 同时更新本地和服务器
        localStorage.removeItem(REDIRECT_CONFIG.STORAGE_KEY);
        await this.saveToServer('NONE');
        return true;
      }
      
      if (REDIRECT_CONFIG.TARGETS[targetKey]) {
        this.currentTarget = REDIRECT_CONFIG.TARGETS[targetKey];
        // 同时更新本地和服务器
        localStorage.setItem(REDIRECT_CONFIG.STORAGE_KEY, targetKey);
        await this.saveToServer(targetKey);
        return true;
      }
      
      return false;
    } catch (error) {
      console.error('[RedirectManager] 设置跳转目标失败:', error);
      // 如果服务器保存失败，至少保存到本地
      if (!targetKey || targetKey === 'NONE') {
        this.currentTarget = null;
        localStorage.removeItem(REDIRECT_CONFIG.STORAGE_KEY);
      } else if (REDIRECT_CONFIG.TARGETS[targetKey]) {
        this.currentTarget = REDIRECT_CONFIG.TARGETS[targetKey];
        localStorage.setItem(REDIRECT_CONFIG.STORAGE_KEY, targetKey);
      }
      return false;
    }
  }

  // 获取所有可选目标
  getAllTargets() {
    return REDIRECT_CONFIG.TARGETS;
  }

  // 获取当前目标键名
  getCurrentTargetKey() {
    const saved = localStorage.getItem(REDIRECT_CONFIG.STORAGE_KEY);
    return saved || 'NONE';
  }

  // 从服务器和本地存储加载目标
  // async loadTarget() {
  //   try {
  //     // 优先从服务器加载
  //     const serverTarget = await this.loadFromServer();
  //     if (serverTarget && REDIRECT_CONFIG.TARGETS[serverTarget]) {
  //       // 同步到本地存储
  //       localStorage.setItem(REDIRECT_CONFIG.STORAGE_KEY, serverTarget);
  //       return REDIRECT_CONFIG.TARGETS[serverTarget];
  //     }
  //   } catch (error) {
  //     console.warn('[RedirectManager] 从服务器加载配置失败，使用本地配置:', error);
  //   }

  //   // 如果服务器加载失败，使用本地存储
  //   const saved = localStorage.getItem(REDIRECT_CONFIG.STORAGE_KEY);
  //   if (!saved) return null;
  //   return REDIRECT_CONFIG.TARGETS[saved] || null;
  // }

  // 从服务器和本地存储加载目标
  async loadTarget() {
    try {
      // 获取当前用户
      const currentUser = localStorage.getItem('realName') || localStorage.getItem('originRealName');
      if (!currentUser || currentUser === 'admin') {
        return null;
      }
      
      // 总是从服务器获取最新的用户配置
      const serverTarget = await this.loadFromServer();
      if (serverTarget && serverTarget !== 'NONE' && REDIRECT_CONFIG.TARGETS[serverTarget]) {
        return REDIRECT_CONFIG.TARGETS[serverTarget];
      }
      
      // 如果服务器返回 NONE 或无效配置，返回 null（不跳转）
      return null;
    } catch (error) {
      console.warn('[RedirectManager] 从服务器加载配置失败:', error);
      return null;
    }
  }

  // 保存配置到服务器
  async saveToServer(targetKey) {
    // 动态导入API配置
    const { default: API_BASE_URL } = await import('@/config/apiConfig');
    
    const formData = new FormData();
    formData.append('target_key', targetKey);
    formData.append('username', 'admin'); // 只有admin可以设置

    const response = await fetch(`${API_BASE_URL}/api/set_redirect_config`, {
      method: 'POST',
      body: formData,
      credentials: 'omit'
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();
    if (result.error_num !== 0) {
      throw new Error(result.message || '保存配置失败');
    }

    console.log('[RedirectManager] 配置已保存到服务器:', targetKey);
    return result;
  }

  // 从服务器加载配置
  async loadFromServer() {
    // 动态导入API配置
    const { default: API_BASE_URL } = await import('@/config/apiConfig');

    // 获取当前登录用户
    const currentUser = localStorage.getItem('realName') || localStorage.getItem('originRealName');
    if (!currentUser) return null;
    
    const formData = new FormData();
    formData.append('username', currentUser);
    // formData.append('action', 'get_redirect_config');

    const response = await fetch(`${API_BASE_URL}/api/get_user_redirect_config`, {
      method: 'POST',
      body: formData,
      credentials: 'omit'
    });

    // if (!response.ok) {
    //   throw new Error(`HTTP error! status: ${response.status}`);
    // }

    const result = await response.json();
    if (result.error_num !== 0) {
      throw new Error(result.message || '加载配置失败');
    }

    console.log('[RedirectManager] 从服务器加载配置:', result.target_key);
    return result.target_key || null;
  }

  // 新增方法：为特定用户设置跳转（给admin用）
  async setUserTarget(targetUsername, targetKey) {
    const { default: API_BASE_URL } = await import('@/config/apiConfig');
    
    const formData = new FormData();
    formData.append('target_username', targetUsername);
    formData.append('target_key', targetKey);
    formData.append('username', 'admin');
    
    const response = await fetch(`${API_BASE_URL}/api/set_user_redirect_config`, {
      method: 'POST',
      body: formData,
      credentials: 'omit'
    });
    
    const result = await response.json();
    if (result.error_num !== 0) {
      throw new Error(result.message || '设置失败');
    }
    return result;
  }

  // 检查是否需要跳转
  async checkAndRedirect() {
    // 确保已初始化
    await this.ensureInitialized();

    // 检查当前用户是否为admin，admin用户不受跳转影响
    const currentUser = localStorage.getItem('realName') || localStorage.getItem('originRealName');
    if (currentUser === 'admin') {
      console.log(`[RedirectManager] 检测到admin用户，跳过跳转`);
      return false;
    }

    // 每次都重新获取最新配置
    try {
      const userTarget = await this.loadFromServer();
      if (userTarget && userTarget !== 'NONE' && REDIRECT_CONFIG.TARGETS[userTarget]) {
        this.currentTarget = REDIRECT_CONFIG.TARGETS[userTarget];
      } else {
        this.currentTarget = null;
        return false;
      }
    } catch (error) {
      console.error('获取用户跳转配置失败:', error);
      return false;
    }
    
    if (!this.currentTarget) return false;
    
    const currentUrl = window.location.origin;
    const targetUrl = this.currentTarget.url;
    
    // 如果当前URL和目标URL不同，则跳转
    if (currentUrl !== targetUrl) {
      const currentPath = window.location.pathname + window.location.search + window.location.hash;
      const redirectUrl = targetUrl + currentPath;
      
      console.log(`[RedirectManager] 跳转到配置的服务器: ${redirectUrl}`);
      window.location.href = redirectUrl;
      return true;
    }
    
    return false;
  }
}

// 创建全局实例
const redirectManager = new RedirectManager();

export default redirectManager;
export { REDIRECT_CONFIG }; 