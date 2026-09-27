# 招标智能体后端

采购人侧招标智能体 MVP 后端，基于 FastAPI、LangGraph、SQLAlchemy 和 SQLite，包含市场调研、招标文件生成、招标文件合规检测三个工作流。市场调研 Agent 可调用产品搜索、厂商搜索、历史成交搜索和网页取证工具。

## 环境要求

- Git
- Python 3.11（项目当前约束为 `>=3.11,<3.12`）
- Windows PowerShell；其他系统可直接使用对应 Shell 执行 Python 命令

所有 Python 依赖统一声明在 `pyproject.toml`。不要提交个人虚拟环境、`.env`、数据库、上传文件或生成产物。

## 获取代码

```powershell
git clone https://github.com/zhongyiziqi/tender-agent.git
Set-Location tender-agent
```

## 创建开发环境

团队成员可选择 `venv` 或 Conda，二选一即可。

### 方式一：venv（推荐）

```powershell
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

如果系统没有 `py` 命令，请确认当前 `python` 是 3.11 后执行：

```powershell
python -m venv .venv
```

### 方式二：Conda

```powershell
conda create -n tender-agent python=3.11 -y
conda activate tender-agent
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

验证环境：

```powershell
python --version
python -c "import fastapi, langgraph, sqlalchemy; print('dependencies ok')"
```

## 配置

首次运行时复制团队配置模板：

```powershell
Copy-Item .env.example .env
```

默认配置可直接以 mock 模式启动，无需模型密钥。常用配置如下：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/tender_agent.db` | 数据库连接地址 |
| `UPLOAD_DIR` | `./data/uploads` | 上传文件目录 |
| `ARTIFACT_DIR` | `./data/artifacts` | 生成产物目录 |
| `MAX_UPLOAD_MB` | `30` | 单文件大小上限 |
| `WEB_SEARCH_ENABLED` | `true` | 是否启用网络搜索 |
| `WEB_SEARCH_REGION` | `cn-zh` | DuckDuckGo 搜索区域 |
| `LLM_MODE` | `mock` | `mock` 或 `openai_compatible` |
| `LOG_LEVEL` | `INFO` | 日志级别 |

接入 OpenAI 兼容模型服务时，在个人 `.env` 中配置：

```dotenv
LLM_MODE=openai_compatible
LLM_BASE_URL=https://your-provider.example/v1
LLM_API_KEY=replace-with-your-own-key
LLM_MODEL=your-default-model
MARKET_RESEARCH_MODEL=
TENDER_GENERATION_MODEL=
COMPLIANCE_REVIEW_MODEL=
```

三个专用模型为空时会回退到 `LLM_MODEL`。`.env` 已被 Git 忽略，禁止把真实密钥写入 `.env.example`、源码、测试或提交记录。需要新增公共配置项时，应同步修改 `.env.example`、`app/core/config.py` 和本 README。

## 初始化数据库

应用启动时会自动创建开发所需的 SQLite 表和 FTS5 索引。也可以显式运行迁移：

```powershell
python -m alembic upgrade head
```

默认数据库和运行数据位于 `data/`，该目录不会提交到 Git。每位开发者使用自己的本地数据；如需共享测试数据，应先脱敏并通过单独的约定交付。

## 启动服务

确保虚拟环境已经激活，然后执行：

```powershell
.\run.ps1
```

脚本会优先使用项目 `.venv` 中的 Python，否则使用当前 Shell 环境中的 `python`，并在缺少 `.env` 时自动从 `.env.example` 创建。

也可以手动启动：

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

启动后可访问：

- API 文档：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

开发环境必须保持单个 Uvicorn worker，因为任务队列当前存放在进程内存中。

## 测试与代码检查

提交代码前至少运行：

```powershell
python -m pytest
python -m ruff check app tests
```

如果修改了依赖，请更新 `pyproject.toml` 并在干净环境中重新执行安装和测试。不要只在本机环境中手动安装而不更新依赖声明。

## 团队协作约定

1. 开始开发前先拉取最新的 `main`，并从最新代码创建功能分支。
2. 公共依赖只通过 `pyproject.toml` 维护，公共配置模板只通过 `.env.example` 维护。
3. 真实密钥、`.env`、虚拟环境、缓存、数据库和 `data/` 目录不得提交。
4. 数据库结构变化需要新增 Alembic migration，并验证 `python -m alembic upgrade head`。
5. 提交前运行测试和 Ruff；涉及 API 变更时同步更新 README 和接口测试。

## 项目结构

```text
app/
  agents/          LangGraph 工作流与市场调研 Agent
  api/             FastAPI 路由
  core/            配置
  db/              数据库会话与基础模型
  llm/             模型工厂与调用封装
  models/          SQLAlchemy 实体
  repositories/    数据访问层
  schemas/         API 数据模型
  services/        文档、导出、规则、评分、任务和搜索服务
alembic/            数据库迁移
tests/              自动化测试
.env.example        可提交的公共配置模板
pyproject.toml      Python 版本、依赖和工具配置
run.ps1             Windows 开发启动脚本
```

## 任务流程

1. 通过 `POST /api/v1/documents` 上传 DOCX 或 PDF 资料。
2. 创建市场调研任务，搜索产品、主流厂商和历史成交公告，也可补充人工确认的数据。
3. 轮询 `GET /api/v1/tasks/{task_id}`，完成后读取结果。
4. 使用市场调研任务 ID 创建招标文件草案。
5. 对生成任务或人工上传文件发起合规检测。
6. 从结果中的 `artifacts` 下载 JSON、DOCX 或 PDF。

## 当前边界

- 登录鉴权和 OCR 尚未实现。
- 网络调研使用无需 API Key 的 DuckDuckGo 搜索；生产环境建议替换为稳定的商业搜索 API，并为政府采购公告源增加专用连接器。
- 当前使用 SQLite/FTS5；PostgreSQL、向量数据库和 reranker 只保留扩展位置。
- 任务队列为单进程内存队列；生产部署应替换为 Redis/Celery 等外部任务系统。
- 生成结果均为待复核材料，不替代采购、法务或监管部门的最终判断。
