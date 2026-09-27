# 招标智能体后端

采购人侧招标智能体 MVP，包含市场调研产品对比、招标文件生成和招标文件合规检测三个 LangGraph 工作流，以及对应的 Vue 3 采购工作台。市场调研 Agent 可以自动调用产品搜索、厂商搜索、历史成交搜索和网页取证工具。

## 运行环境

本机已验证可直接使用 `E:\anaconda3\envs\ai-job-agent`。推荐直接运行项目启动脚本，不依赖当前 PowerShell 是否已初始化 Conda：

```powershell
.\run.ps1
```

如果 PowerShell 阻止脚本执行，可以在当前窗口运行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\run.ps1
```

也可以在当前窗口手动加载 Conda hook 后激活环境：

```powershell
& "E:\anaconda3\shell\condabin\conda-hook.ps1"
conda activate ai-job-agent
```

`conda init` 执行完成后，新打开的 PowerShell 通常可以直接使用 `conda activate ai-job-agent`。项目依赖声明在 `pyproject.toml`，默认配置参考 `.env.example`。

## 启动

```powershell
.\run.ps1
```

不使用启动脚本时，也可以完全绕过 Conda 激活：

```powershell
Copy-Item .env.example .env -ErrorAction SilentlyContinue
& "E:\anaconda3\envs\ai-job-agent\python.exe" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/docs` 查看接口文档，健康检查地址为 `http://127.0.0.1:8000/api/v1/health`。

## 前端工作台

项目现已包含 Vue 3 前端，覆盖采购项目、市场调研、招标文件编制、合规检测、文档中心和任务审计页面。保持后端运行，再新开一个 PowerShell 窗口执行：

```powershell
.\run-frontend.ps1
```

访问 `http://127.0.0.1:5173`。前端开发服务器会将 `/api` 请求代理到本地 FastAPI 服务，详细说明见 `frontend/README.md`。

开发模式启动时会自动创建 SQLite 表和 FTS5 索引。需要显式管理数据库版本时可执行：

```powershell
alembic upgrade head
```

## 模型配置

默认 `LLM_MODE=mock`，不会访问外部模型，也不会虚构厂商、价格或历史成交记录。

当 `WEB_SEARCH_ENABLED=true` 时，mock 模式仍会自动执行产品、厂商和历史成交三类网络搜索并返回来源链接，但不会把搜索摘要直接当成已验证产品。配置真实模型后，LangChain Agent 会自主调用搜索和网页读取工具，提取带来源的候选产品与历史成交记录。

接入 OpenAI 兼容接口时配置：

```dotenv
LLM_MODE=openai_compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=replace-me
LLM_MODEL=your-default-model
MARKET_RESEARCH_MODEL=optional-market-model
TENDER_GENERATION_MODEL=optional-generation-model
COMPLIANCE_REVIEW_MODEL=optional-review-model
```

三个专用模型为空时回退到 `LLM_MODEL`。密钥不会写入数据库或执行日志。

## 任务流程

1. 通过 `POST /api/v1/documents` 上传 DOCX 或 PDF 资料。
2. 创建市场调研任务，Agent 自动搜索产品、主流厂商和历史成交公告；也可补充人工确认的候选产品数据。
3. 轮询 `GET /api/v1/tasks/{task_id}`，完成后读取结果接口。
4. 使用市场调研任务 ID 创建招标文件草案。
5. 对生成任务或人工上传文件发起合规检测。
6. 从结果中的 `artifacts` 下载 JSON、DOCX 或 PDF。

任务在单进程内存队列中执行，开发环境必须使用一个 Uvicorn worker。生产部署应将队列替换为 Redis/Celery 等外部任务系统。

## 测试

```powershell
python -m pytest
```

## 当前边界

- 已包含 Vue 前端；登录鉴权和 OCR 尚未实现。
- 网络调研当前使用无需 API Key 的 DuckDuckGo 搜索；生产环境建议替换为稳定的商业搜索 API，并针对政府采购公告源增加专用连接器。
- SQLite/FTS5 已实现；PostgreSQL、向量数据库和 reranker 只保留扩展位置。
- 生成结果均为待复核材料，不替代采购、法务或监管部门的最终判断。
