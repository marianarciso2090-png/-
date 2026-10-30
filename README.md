# A 股个股研究 AI 智能体

面向个人研究者的中文 Web 服务。输入 A 股代码或简称与可选截至日，系统通过 iFinD 采集公司、财务、行情、风险、公告和新闻证据，并通过 DeepSeek 生成有证据编号的基本面研究报告。

它输出相对估值与审慎/基准/乐观情景分析，不输出买入、持有或卖出评级。所有报告均显示“仅供研究参考，不构成投资建议”。

## 在自己的 Windows 电脑上试用（无需 Docker）

这台电脑已有 Python 和 Node.js。先在 PowerShell 里确认本机已设置 `DEEPSEEK_API_KEY` 和 `IFIND_MCP_API_KEY` 两个环境变量，随后在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run-local.ps1
```

脚本首次运行会建立项目专用 Python 环境、安装依赖、构建网页，然后只监听 `127.0.0.1:8765`。在浏览器打开 `http://127.0.0.1:8765`；管理员账号为 `admin`，一次性密码显示在启动终端。保持终端打开以运行服务，按 Ctrl+C 停止。

本地报告和证据存放在 `backend/local_research.db`；该文件已被 Git 忽略。每次启动会生成新的登录密码，已有报告不会丢失。如需固定密码，可在运行脚本前设置 `ADMIN_PASSWORD` 环境变量。API 密钥只从本机进程环境读取，脚本不会将其写入配置文件。

## 使用 Docker 部署到服务器（可选）

1. 复制 `.env.example` 为 `.env`，替换数据库密码、管理员密码、会话密钥、`DEEPSEEK_API_KEY` 和 `IFIND_MCP_API_KEY`。密钥只会被 `api` 与 `worker` 容器读取。
2. 将受信任 TLS 证书放到 `deploy/certs/fullchain.pem` 和 `deploy/certs/privkey.pem`。这两个文件已被 Git 忽略。Nginx 仅在 HTTPS 上提供应用，并将 HTTP 重定向到 HTTPS。
3. 在安装 Docker Compose 的服务器运行：

   ```powershell
   docker compose up --build -d
   ```

4. 访问 `https://<你的域名或服务器地址>`，使用 `.env` 的管理员账户登录。

首次启动会自动创建数据库表。报告和原始证据快照存储在 Docker 的 `postgres_data` 卷中；请对该卷做定期、加密的异机备份。

## 使用与数据边界

- 默认按最新可得财报与最近交易日数据研究；可填写历史截至日。
- 任务为异步队列：`queued → collecting → analysing → reviewing → completed/failed`。
- 每次生成都会形成独立版本；报告、iFinD 请求参数、响应快照哈希和采集时间都可复核。
- iFinD 调用被限制为白名单工具，默认每秒最多 2 次；响应会缓存一小时。若账户权限不足、限流或网络失败，任务会明确失败或标出数据缺口。
- iFinD MCP 默认直连 `api-mcp.51ifind.com:8643`，避免系统代理不支持非标准 HTTPS 端口。只有部署网络必须走代理时才设置 `IFIND_USE_ENV_PROXY=true`。
- 公告和新闻仅使用 iFinD 语义检索返回的片段，不声称阅读了完整原始公告。

## 开发与测试

后端测试在 `backend` 目录运行：

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

仅验证 DeepSeek 接入时，可在已设置 `DEEPSEEK_API_KEY` 的 PowerShell 中运行一次低用量烟雾测试：

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -c "from app.core.config import Settings; from app.services.deepseek import DeepSeekClient; c=DeepSeekClient(Settings()); print(c.create_plan('600519', None).model_dump_json()); c.close()"
```

密钥只通过环境变量读取，请勿写入代码、截图或 Git 提交。

前端在 `frontend` 目录运行：

```powershell
npm install
npm run lint
npm run build
```

## 安全运维

- 不要把 `.env`、TLS 私钥、数据库备份或 iFinD/DeepSeek 原始凭证上传到仓库。
- 生产环境保持 `APP_ENV=production`，这样管理员会话 Cookie 必须通过 HTTPS 发送。
- 部署前替换示例管理员密码和会话密钥，限制服务器 443 端口访问，并按服务商说明保护 iFinD 使用额度。
- 本 MVP 没有公开注册、多用户协作、PDF 导出、实时预警、港美股或网页检索；这些能力不能通过前端参数绕过。
