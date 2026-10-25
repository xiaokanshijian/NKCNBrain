# NKCN Brain — public snapshot

此目录是独立的公开发布候选副本，包含 Vue 前端、Django 后端和可选的连续图片复核界面。发布提交只衔接目标公开仓库已有历史，不导入私有仓库历史；当前文件不包含真实凭据、用户上传文件或运行缓存。

## 目录

- `frontend/`：Vue 主前端。
- `backend/`：Django 主后端，业务路由位于 `/api/`。
- `reviewer/`：可选的连续图片复核界面。
- `docs/configuration-map.json`：凭据环境变量与使用文件的对应关系。
- `tools/check_public_release.py`：只读发布检查工具。

## 配置和启动

前端使用 Node.js 18.20.6、npm 10.8.2。后端以 requirements.txt 为依赖声明。
此发布工作未更改原开发环境，也不附带虚拟环境或 node_modules。

1. 在后端目录将 `.env.example` 复制为 `.env`，设置自己的随机 `DJANGO_SECRET_KEY`、独立数据库配置和模型凭据。
2. 模型 JSON 中的 `env:VARIABLE` 引用由配置管理器解析。不要将真实密钥写回 JSON。新增/更新模型配置会拒绝明文凭据。
3. 历史启动链路会初始化多种模型；需要配置启用链路对应的凭据。第三方网关地址默认指向 localhost 示例，部署者必须自行指定。不能把官方服务密钥与其他网关混用。
4. 在前端目录复制 `.env.example` 为 `.env.local`，设置公开的后端地址。禁止把密钥放入 `VUE_APP_*`。
5. 在后端目录使用自己的 Python 环境执行 `python manage.py check`。确认连接的是自己的独立数据库后，才能自行执行迁移和启动服务。本次交付没有执行数据库迁移。
6. 在前端目录执行 `npm ci`、`npm run serve` 或 `npm run build`。

运行时配置默认只读取后端目录内的 .env，不向上查找其他开发目录。
辅助 Node 数据库服务使用独立的 AUX_DB_* 环境变量，见对应示例文件。

## 语音签名与认证

现有 NKCN 普通账号登录已接入服务端会话，无需另行登录 Django 管理后台。
语音组件向 /api/voice/session 请求服务端签名；浏览器源码不内置长期签名密钥。
服务端仍需配置自己的 XFYUN_APP_ID、XFYUN_API_KEY、XFYUN_API_SECRET。

- 登录客户端先取得 CSRF token，再 POST /api/verify_user（兼容末尾斜线）。
  保留原登录响应字段，密码不再放在 URL 中。旧的 GET 登录调用须改用 POST。
- 验证用户名、密码和 allowed 状态成功后，轮换会话 ID 并将账号绑定到服务端 session。
  会话只保存账号 ID 与不可逆校验值，不保存明文密码。
- 客户端在提示登录成功前会回读 /api/auth/session，确认浏览器 Cookie 确实生效。
  自动登录也核验该接口，不再将 localStorage 中的用户名当作登录证明。
- POST /api/auth/logout 注销当前浏览器会话。回到登录页会先等待注销完成。
  原 user_exit 仍只处理离开笔记本，不会误注销账号。
- 会话过期、账号删除/禁用或密码变更后，拒绝新的语音签名请求。
- 签名接口仍支持 Django 已认证用户。匿名/失效会话返回 401，
  缺少语音凭据返回 503，身份数据库暂不可用返回 503。

本地开发请统一使用 localhost（不要把 localhost 前端与 127.0.0.1 后端混用）。
按部署地址配置 DJANGO_CORS_ALLOWED_ORIGINS 和 DJANGO_CSRF_TRUSTED_ORIGINS；
认证请求使用 withCredentials，CORS 已允许携带 Cookie。
副本使用独立的 nkcn_public_sessionid / nkcn_public_csrftoken Cookie 名，
默认 HttpOnly、SameSite=Lax、会话有效期 12 小时。
真正跨站的 HTTPS 部署需要 SameSite=None 与 Secure=1，并配置精确的可信来源。
部署数据库需具备 Django 标准 session 表；本次未对真实数据库执行迁移。

签名 URL 是短时访问凭证，不应写入日志或持久存储；API_SECRET 不返回客户端。
也可通过 VUE_APP_VOICE_SESSION_URL 指定符合相同响应契约的已认证签名服务。

## 发布内容

保留业务源码、数据库迁移、课程标准、规则数据和运行必需的通用 UI 资源。
不发布私有 .env、数据库备份、日志、Pickle 缓存、上传资料、内部实验报告、
外部参考工作区及单独的 OCR 实验工程。
私有固定样例配置保留空容器；五张运行截图替换为合成示例图。

尚未配置和验证真实模型、真实数据库以及语音厂商服务。这里的脱敏检查不等于整个应用的生产安全审计。
上游已经公开过的凭据仍需由凭据所有者轮换；生成本副本不会撤销凭据或清理远端历史。

## 本地验证命令

```text
python tools/check_public_release.py
cd backend
python -B -m unittest tests.test_public_release -v
python -B -m django test tests.test_login_voice --settings=tests.session_test_settings
python manage.py check
cd ../frontend
node tests/voiceSession.test.cjs
node tests/authSession.test.cjs
npm run build
```

Windows 上如果现有 ONNX Runtime 与其他原生依赖出现 DLL 装载顺序冲突，
可在同一 Python 进程中先 import onnxruntime，再执行 manage.py。
本次完整 Django 检查采用了这种预加载方式，使用虚拟凭据并阻断业务网络连接；
没有安装或更新原虚拟环境中的任何包。

发布目标为 https://github.com/xiaokanshijian/NKCNBrain 的 main 分支。
发布使用独立副本的完整干净文件清单，并以目标仓库当前公开提交为父提交。
不会合并私有分支、复制私有 .git 或重写目标仓库已有历史。
当前文件的脱敏不能消除旧公开提交中已经披露的凭据；凭据轮换和旧历史清理须另行处理。

发布仓库不附带本地依赖、验证目录和交付压缩包。
