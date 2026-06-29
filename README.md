# 科研文献智能解析与知识服务系统（前后端完整实现版）

本工程在 group44-backend 后端结构基础上，按照需求说明书、概要设计文档、详细设计文档补全为前后端一体化工程。

## 1. 实现范围

### 后端
- FastAPI + Router / Service / Repository / Model 分层架构。
- MySQL 8.0：用户、文献、解析任务、结构化内容、问答、报告、知识图谱、复现指南、学习记录、运维日志等结构化数据。
- Redis + Celery：文献解析、结构化抽取、向量化等异步任务。
- MinIO：PDF 原文与导出文件对象存储。
- GROBID + PyMuPDF + pdfplumber：PDF 版面和逻辑结构解析。
- BGE Embedding：文本向量化。
- Milvus：向量入库、ANN 检索和语义索引。
- BGE Reranker：候选片段重排。
- OpenAI-compatible LLM：Qwen、DeepSeek、vLLM、Xinference 等推理接口。
- RAG 问答：问题改写 / 向量检索 / 重排 / Prompt 增强 / 生成 / 溯源。
- 管理后台接口：用户、模型、解析任务、向量库、备份、日志、运营统计。
- 增强功能：证据矩阵、研究雷达、热点分析、报告导出。

### 前端
- Vue 3 + TypeScript + Vite + Pinia + Vue Router + Axios。
- Element Plus 高级玻璃拟态 UI。
- PDF/结构化内容研读工作台。
- 智能问答面板，支持单篇与多篇文献上下文。
- 研读报告、知识图谱、多文献对比、实验复现建议、证据矩阵。
- 学习档案统计与 ECharts 可视化。
- 管理端：用户配额、模型配置、解析任务、向量库监控、日志审计、运营统计。
- AntV G6 知识图谱可视化。
- Markdown-it + KaTeX 报告和问答结果渲染。

## 2. 数据库初始化说明

本版本已融合 `database/literature_system.sql`。该文件来自项目数据库脚本，并已做与后端 ORM 兼容的最小工程化补充：增加 MinIO 对象键、资源配额、完整解析状态、任务优先级、reranker 模型类型等字段；同时保留原脚本中的表结构、外键、索引和命名。

Docker 首次启动 MySQL 时会自动执行：

```text
/docker-entrypoint-initdb.d/01_literature_system.sql
```

如果本机已经存在旧的 `mysql_data` 卷，MySQL 不会重复执行初始化脚本。需要重新建库时执行：

```bash
docker compose down -v
docker compose up -d mysql
```

本地非 Docker 方式也可以手动导入：

```bash
mysql -u root -p < database/literature_system.sql
python scripts/init_db.py
```

`python scripts/init_db.py` 主要用于补充默认管理员、默认模型配置和任务调度配置。

## 3. 本地开发启动

### 2.1 启动中间件

```bash
cp .env .env
docker compose up -d mysql redis minio etcd milvus grobid flower
```

如果使用 Docker 内部服务名运行后端，可以复制 Docker 环境变量：

```bash
cp .env.docker .env
```

### 2.2 启动后端

```bash
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS / Linux
pip install -r requirements.txt
python scripts/init_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

另开终端启动 Celery Worker：

```bash
celery -A app.workers.celery_app.celery_app worker -l info -P solo
```

后端接口文档：

```text
http://127.0.0.1:8000/docs
```

### 2.3 启动前端

```bash
cd frontend
cp .env .env
npm install
npm run dev
```

前端地址：

```text
http://127.0.0.1:5173
```

默认管理员：

```text
admin / admin123456
```

## 4. Docker 一体化启动

```bash
cp .env.docker .env
docker compose up -d --build
```

服务地址：

- 前端：http://127.0.0.1:5173
- 后端：http://127.0.0.1:8000/docs
- MinIO 控制台：http://127.0.0.1:9001
- Flower：http://127.0.0.1:5555

## 5. 重要说明

本版本不使用本地 mock 替代核心链路。真实文献解析、向量化、检索、重排和问答效果取决于 GROBID、BGE、Milvus 和 LLM 服务是否正确部署。若相关服务未启动，系统会按真实工程方式返回连接或调用错误，而不是伪造结果。


## 6. 本次终验增强项

本版本在 `group44-fullstack-db-integrated` 基础上继续补齐文档中明确要求但上一版不足的内容：

- 验证码注册与密码重置：`POST /api/v1/auth/verification-code`，验证码存入 Redis，注册和重置密码必须校验验证码。
- 登录失败锁定：同一账号密码连续错误 5 次后锁定 15 分钟。
- 资源配额强制校验：上传前检查单文件大小、总文献数、单用户并发任务数；问答前检查每日问答次数。
- 批量上传：`POST /api/v1/papers/batch-upload`，支持 2-10 篇 PDF。
- 分片上传与断点续传：`/papers/upload/init`、`/papers/upload/chunk`、`/papers/upload/{upload_id}/status`、`/papers/upload/complete`。
- SSE 流式问答：`POST /api/v1/qa/ask-stream`，前端 ChatPanel 已改为打字机式流式输出。
- 解析任务重试与优先级：`/tasks/{id}/retry`、`/tasks/batch-retry`、`/tasks/{id}/priority`、`/tasks/failure-stats`。
- 解析任务实时状态流：`GET /api/v1/tasks/{id}/events`。
- 向量库备份恢复：`/vector-store/backups`、`/vector-store/restore`，支持外部 `milvus-backup` 命令配置。
- 管理端用户全生命周期：新增、编辑、禁用/启用、删除、重置密码、资源配额配置、导出用户 CSV。
- 报告 PDF 导出中文字体支持：优先使用系统 Noto CJK 字体，避免中文乱码。
- 前端 TypeScript 构建错误已修复，新增 `markdown-it-katex` 类型声明。

## 7. 验证记录

已在当前代码包上执行：

```bash
python -m py_compile $(find app scripts -name '*.py')
cd frontend && npm install && npm run build
```

结果：后端 Python 语法检查通过；前端 `vue-tsc --noEmit && vite build` 通过。

## 8. 向量库备份恢复命令配置说明

如果你部署了官方或第三方 `milvus-backup` 工具，可以在 `.env` 中配置：

```bash
MILVUS_BACKUP_COMMAND="milvus-backup create -n $BACKUP_NAME"
MILVUS_RESTORE_COMMAND="milvus-backup restore -n $BACKUP_NAME"
```

系统会在执行备份/恢复接口时传入以下环境变量：

```text
MILVUS_COLLECTION
BACKUP_NAME
BACKUP_LOCATION
BACKUP_ID
```

如果未配置命令，系统会完成 Milvus flush 和备份记录登记；真实物理备份需要部署 `milvus-backup` 后启用上述命令。


## 本版补齐说明

本版在上一版基础上继续补齐了验收差距：

- 前端工作台新增 PDF.js 原文阅读器，支持页码跳转、缩放和引用来源点击定位。
- 智能问答引用来源标签可点击回到对应 PDF 页码。
- 前端上传区支持单篇、批量和分片上传模式；大文件默认走分片上传，保留断点续传会话状态。
- 学习档案接口统一返回 records 与 recent_records，修复前后端字段不一致。
- 报告列表页面补充 PDF 导出按钮。
- 后端任务模块补充 WebSocket 任务进度通道 /api/v1/tasks/{task_id}/ws?token=...，同时保留 SSE 事件流。

仍需在真实部署环境中配置 MySQL、Redis、MinIO、Milvus、GROBID、BGE、LLM 和 Celery Worker 后进行完整联调。

## 9. 本版迭代变更（2026-06-29）

### 9.1 模型缓存路径跨平台修复

**问题**：`bge_embedding.py` / `bge_reranker.py` 中 `cache_dir` 硬编码为容器路径 `/app/hf_cache`，Windows 本地开发时无法识别，抛出 `FileNotFoundError`。

**修复**：
- `config.py` 新增 `hf_cache_dir: str = './runtime/hf_cache'` 配置项，提供跨平台默认相对路径。
- `bge_embedding.py` / `bge_reranker.py` 改为从 `settings.hf_cache_dir` 读取；`_resolve_local_path()` 先查本地缓存再尝试 ModelScope 下载，避免每次启动都联网。
- 新增 `_is_valid_model_dir()` 函数校验模型目录完整性（检查 `config.json`），过滤 HuggingFace / ModelScope 下载中途的临时目录。
- `.env.docker` 新增 `HF_CACHE_DIR=/app/hf_cache`，Docker 环境下走 `/app/hf_cache` volume。
- `.env`（本地）：新增 `HF_CACHE_DIR=./runtime/hf_cache`，模型下载到项目 `runtime/` 目录。

### 9.2 Docker 环境模型卷挂载修复

**问题**：`docker-compose.yml` 中仅 Worker 容器挂载了 `hf_cache` volume，Backend API 容器未挂载，导致 RAG 问答时找不到已下载的模型。

**修复**：
- Backend 服务新增 `- hf_cache:/app/hf_cache` volume 挂载，与 Worker 共享同一模型缓存卷。

### 9.3 RAG 问答流式端点 Session 生命周期修复

**问题**：`ask_stream` 端点使用 FastAPI `Depends(get_db)` 注入 `AsyncSession`，但生成器函数中 `yield` 后 session 可能已被 FastAPI 依赖注入清理，导致 `db.commit()` 时 session 已失效。

**修复**：
- `ask_stream` 不再接收注入的 `db`，改为在生成器内部用 `async with AsyncSessionLocal() as db` 自建 session，生命周期与生成器完全一致。

### 9.4 问答来源外键完整性修复

**问题**：Milvus 向量库中 `chunk_id` 可能在 MySQL `text_chunks` 表中已不存在（论文重新处理时旧 chunks 被删但向量未同步），插入 `qa_message_sources` 时触发外键约束失败（IntegrityError 1452）。

**修复**：
- `RAGService` 新增 `_add_message_sources()` 统一方法：插入 source 前批量 `SELECT id FROM text_chunks WHERE id IN (...)` 校验 chunk_id 有效性；不存在的设 `chunk_id=None`（FK 允许 NULL，`ON DELETE SET NULL`）。

### 9.5 PDF 阅读器连续滚动 + 按需渲染重构

**问题**：旧版 `PdfReader.vue` 使用单 Canvas 翻页模式，长文档（75+ 页）操作不直观，且不支持连续浏览。

**重构内容**：

**9.5.1 连续滚动 + 骨架屏**
- 外层滚动容器 `overflow-y: auto`，内部按 `totalPages` 生成骨架 `<div>` 撑开滚动条高度。
- 首页 viewport 尺寸用于估算骨架高/宽，确保滚动条长度与实际内容一致。
- 未渲染页显示脉冲动画骨架（Skeleton Loading）。

**9.5.2 IntersectionObserver 按需渲染**
- 以滚动容器为 `root`，`rootMargin: 300px` 提前预渲染。
- 每页骨架带 `data-page` 属性，Observer 监听可见性。
- 页面进入 rootMargin → 调用 `page.render()` 渲染到对应 `<canvas>`。
- 维护滑动渲染窗口（`[firstVisible - 2, lastVisible + 3]`），窗口外的 Canvas 置零尺寸释放 GPU 内存。

**9.5.3 文本层对齐修复**
- 引入 `pdfjs-dist/web/pdf_viewer.css` 官方样式。
- 文本层改用 `new pdfjsLib.TextLayer()` API 替代手动 `<span>` 创建 + `Util.transform`。
- 设置 `--scale-factor` CSS 变量确保缩放时文字坐标正确。
- HTML 结构改为汉堡包定位：`.page-inner (relative)` → `canvas + .textLayer + .annotationLayer`（均为 absolute）。

**9.5.4 Zotero-style 悬浮菜单 + 划词高亮**
- `MouseUp` → 计算选区百分比坐标（缩放无关）→ 暂存 `pendingHighlight` → 弹出悬浮菜单（Teleport 到 body）。
- 菜单提供 4 种颜色圆按钮（黄/绿/红/蓝） + 复制按钮。
- 点击颜色 → `confirmHighlight(color)` 将 pending 转为正式高亮，渲染到 `.annotationLayer`。
- 点击菜单外 → `dismissMenu()` 丢弃 pending，取消选中。
- 高亮坐标使用页面容器百分比（0~1），缩放 Canvas 后位置自动复原。

**9.5.5 高亮删除**
- 每个 `.highlight-box` 内嵌 `×` 删除按钮，默认隐藏，hover 高亮框时显示。
- 点击删除 → `deleteHighlight(id)` 移除并重渲染对应页标注层。

### 9.6 本地开发环境文件

- 新建 `.env`（本地开发配置）：所有 host 指向 `127.0.0.1`，路径使用 `./runtime/...` 相对路径。
- `.env.docker` 保持 Docker 容器内 host 名和 `/app/...` 路径不变。

### 9.7 数据流水线元数据增强（Chunk Enrichment）

**问题**：旧流水线将 GROBID 提取的散乱纯文本直接按字符数切片 → BGE 向量化 → Milvus，chunk 丢失文献级上下文。用户提问时检索出的片段无法分辨"该模型"指代什么，大模型回答质量严重下降。

**修复**：在 `_build_vector_index` 向量化阶段前，插入"元数据增强"环节：

**9.7.1 上下文前缀注入（`_build_context_prefix`）**

`pipeline_service.py` 新增方法，从 `paper_extracted_info` 表中读取 LLM 已抽取的结构化信息，构建如下格式的上下文前缀：

```
[文献：基于边缘信息增强的超声图像去噪算法研究]
[核心方法：Canny边缘检测、VGG16特征提取]
```

注入后，每个 chunk 在向量化时实际送入 BGE 的文本变为：

```
[文献：XXX]
[核心方法：YYY]
{原始 chunk 文本}
```

**9.7.2 section_title 填充**

- `_load_content_for_chunks` 新增章节标题查找逻辑：遍历 ContentItem 时维护"当前章节标题"变量，遇 `item_type='heading'` 则更新，后续段落继承该标题。
- `semantic_chunks` 透传 `section_title` 到每个 chunk。
- `_insert_text_chunks` 将 `section_title`（截取前 300 字符）写入 Milvus 的 `section_title` 字段（此前固定为空字符串）。

**9.7.3 双写策略**

| 存储 | 内容 | 用途 |
|------|------|------|
| MySQL `text_chunks.chunk_text` | 原始文本（无前缀） | 前端展示、来源引用 |
| Milvus `text` 字段 | 富文本（上下文前缀 + 原始文本） | 向量检索时展示 |
| BGE 向量化输入 | 富文本 | 提升语义检索精度 |

**效果**：用户提问时，Milvus 返回的检索片段自带文献来源信息，BGE 向量能通过元数据前缀捕捉到"这篇文章做什么"与查询的语义相关性，大模型生成回答时不再面对无头文本片段。
