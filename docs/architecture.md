# ArtiLens 架构（目标态）

> 状态：设计定稿，实施中。基线快照来自 `GYunnnnnX/ArtiLens@19f9a49`（2025-07-25）。
> 本文档是重构期间的唯一权威依据；与代码不一致时，先改本文档再改代码。

## 1. 目标与约束

| 项目 | 结论 |
|---|---|
| 当前形态 | **本地单机自用**：一个用户、一台机器、无 Docker、无 Redis、无 Postgres |
| 下一阶段 | **产品化**：多用户、可部署、可观测、可计费（按次/按月） |
| 硬约束 | 本机仅有 **Python 3.13.1**、无 Docker / conda / Node（Node 由工具链提供） |
| 原则 | 本地跑得起来的最简实现 = 产品化目标实现的**替身适配器**，不是一次性代码 |

一句话：**接口按产品化设计，实现按本地单机落地。** 换 Postgres 是改一行 DSN，而不是重写数据层。

## 2. 分层

```
api/         HTTP 层：路由、鉴权、序列化、SSE
services/    用例编排：上传、分析流水线、问答、翻译
domain/      实体、值对象、端口（Protocol 接口）
adapters/    端口实现：db / vector / llm / parsing / storage
workers/     后台任务执行器（进程内 → ARQ/Celery）
core/        配置、日志、错误、依赖装配
```

依赖方向严格单向：`api → services → domain`，`adapters` 只被 `core` 装配进 `services`。

**明确的"不做"**（避免过度设计）：

- 不引入 DI 框架，用一个 `core/container.py` 手工装配即可
- 不做事件总线、CQRS、微服务拆分
- 不为每个实体都造 repository，只为**会被替换或有多种实现**的建接口：存储、向量、LLM、解析器

## 3. 技术选型与理由

| 关注点 | 旧（GY 快照） | 新 | 理由 |
|---|---|---|---|
| Web 框架 | FastAPI 0.116 | **FastAPI（保留）** | 生态正确，不换 |
| 配置 | `os.getenv` + dotenv | **pydantic-settings** | 类型安全、启动即校验、`.env` 统一 |
| ORM | SQLAlchemy 1.x 写法 + `create_all` | **SQLAlchemy 2.0 async + Alembic** | 迁移从第一天就有；async 与 FastAPI 同构 |
| 元数据库 | SQLite（同步、无迁移） | **SQLite/aiosqlite（本地）→ Postgres（目标）** | 同一套 SQLAlchemy 模型，只换 DSN |
| 向量库 | Chroma，按论文分目录 | **LanceDB（本地）→ pgvector（目标）** | 嵌入式起步；与元数据同库收口 |
| Embedding | `all-MiniLM-L6-v2`（本地 torch） | **DashScope `text-embedding-v4`（托管）** | 砍掉 torch + sentence-transformers（约 2 GB） |
| 编排 | LangChain `AgentExecutor` + LangGraph | **裸 SDK + 类型化 tool loop + Pydantic 结构化输出** | 4 个依赖 + 版本地雷，换 150 行自己可控的循环 |
| PDF 解析 | `unstructured[hi_res]` + Tesseract + Poppler | **PyMuPDF 快路径**（可选 MinerU 作为深度解析 worker） | 系统级依赖清零；单篇 30–60 s → <1 s |
| 任务 | `BackgroundTasks`（进程内，无持久化） | **`jobs` 表 + 进程内 worker**（目标态换 ARQ） | 进程重启不丢任务；接口不变 |
| 流式 | 部分接口 `StreamingResponse` | **SSE（sse-starlette），全链路统一** | 前端统一用 `EventSource` 消费 |
| 前端 | 1779 行原生 JS 单文件 | **Vite + React + TS + Tailwind + TanStack Query + pdfjs-dist** | 状态与组件化，支持产品化迭代 |
| 日志 | `print()` | **structlog（JSON）** | 可检索、可接 Loki |
| 质量 | 无 | **ruff + mypy + pytest** | 重构期的安全网，必须有 |

**净效果**：顶层第三方依赖从 19 个降到约 10 个，系统级依赖（Tesseract/Poppler）归零，`torch` 出局。

## 4. 数据模型（v1）

```
users        id, email, display_name, password_hash(nullable), created_at
papers       id, user_id, filename, storage_path, sha256, page_count,
             status(uploaded|parsing|analyzing|ready|failed),
             created_at, updated_at
analyses     id, paper_id, version, title, authors, abstract_zh, summary,
             key_points(json), research_context, keywords(json),
             model, prompt_version, created_at        # 可重跑、可对比
chunks       id, paper_id, section, page_from, page_to, text, token_count,
             embedding(vector|blob)
messages     id, paper_id, user_id, role, content, citations(json),
             created_at
jobs         id, paper_id, kind(parse|analyze), status, progress,
             stage, error, created_at, updated_at
```

几个刻意的决定：

- **分析结果独立成表**，不塞进 `papers` 的十几个 `Text` 列。换模型重跑可留档，产品化时能做 A/B。
- **`chunks` 带 `page_from/page_to` 和 `section`**，这是"答案可溯源到页码"的前提，也是旧架构最缺的能力。
- **`jobs` 持久化**，前端刷新不丢进度。

## 5. API 面（v1，`/api/v1`）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/papers` | 上传 PDF，返回 paper_id，入队解析 |
| GET | `/papers` | 列表（分页） |
| GET | `/papers/{id}` | 详情（含最新 analysis） |
| POST | `/papers/{id}/analyze` | 触发分析，返回 job_id |
| GET | `/jobs/{id}` | 轮询进度（SSE 版：`/jobs/{id}/events`） |
| GET | `/papers/{id}/file` | 受控下载/Range 读取，替代裸 `/uploads` |
| POST | `/papers/{id}/chat` | 提问，**SSE 流式**返回 token + 引用 |
| GET | `/papers/{id}/messages` | 会话历史 |
| POST | `/papers/{id}/translate` | 选中段落翻译，SSE |
| POST | `/papers/{id}/explain` | 术语/公式解释，SSE |
| GET | `/health` | 存活与依赖探针 |

## 6. 迁移路径（每阶段结束都能跑）

| 阶段 | 内容 | 验收 | 估时 |
|---|---|---|---|
| **S0 地基** | 目录骨架、`pyproject.toml`、settings、日志、`/health`、Alembic、ruff/mypy/pytest | `uvicorn` 起得来，`/health` 200，CI 三件套全绿 | 0.5 天 |
| **S1 数据+解析** | 模型与仓储、PyMuPDF 解析器、上传/查询/文件接口 | 上传一篇真 PDF，`GET /papers/{id}` 返回标题/作者/页数/章节数 | 1–2 天 |
| **S2 LLM 层** | provider 客户端、结构化输出、prompt 迁移、分析流水线（job 化） | 一键分析出 summary/key_points/研究脉络，进度可轮询 | 2 天 |
| **S3 检索** | 章节感知分块、embedding、向量端口、混合检索 + 重排 | 给定问题能召回正确段落并带页码 | 1–2 天 |
| **S4 问答** | 类型化 tool loop（检索/思维导图/流程图）、SSE 流式、引用回填 | 前端流式输出，点引用跳页码 | 1 天 |
| **S5 前端** | Vite+React+TS+Tailwind、PDF 阅读器、聊天、图表渲染 | 完整走通：上传→分析→阅读→问答 | 3–5 天 |
| **S6 硬化** | 认证、限流、docker-compose（Postgres+pgvector）、测试补齐、文档 | 一条 `docker compose up` 起产品化形态 | 2 天 |

S0–S4 是后端主线的"换核心部件"，S5 换前端，S6 收口。

## 7. 从旧代码保留什么（资产清单）

**不要重写、直接迁移**（这些是调优出来的领域知识，不是框架胶水）：

- `src/services/tools.py` 里的纯函数：`extract_core_sections`、`classify_section`、`group_sections_by_prefix`、`extract_references_section`、`extract_reference_title`、`is_person_name`、`is_abstract`、`fix_hyphenated_words`、`normalize_title`、`clean_title_for_search`
- `ai_service.py` 里的 prompt 正文（摘要、关键内容、术语、研究脉络、翻译）——原样搬进 `services/prompts/`，只把调用方式从 LangChain 换成 SDK
- 进度估算的**阶段权重模型**（`PHASES` + `progress` 计算），改成 `jobs.stage/progress` 写入
- 前端已跑通的交互细节（PDF 高亮坐标、思维导图渲染参数）

**丢弃**：LangChain/LangGraph 的 `AgentExecutor`、`RetrievalQA`、`ChatPromptTemplate` 用法；`pdf_parser_old` 系列；`_upload_to_oss`（本地不需要，产品化时另做对象存储适配器）。

## 8. 已知风险

1. **Python 3.13 的轮子覆盖**（LanceDB、pgvector 客户端）需在 S0 实测确认，S0 结束前不锁死。
2. **托管 embedding 的成本与配额**：单篇论文约 5–15 万 token，需在 S2 做预算上限。
3. **前端重写的日历风险**：S5 是最大一块，期间后端接口必须先冻结，否则并行返工。
4. **不要在同一分支上既重构又加功能**：S0–S6 期间新需求一律排队。
