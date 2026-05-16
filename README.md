# 苏格拉底辩证智能体

**Socratic Dialectical Agent** — 基于 LangGraph 的苏格拉底式提问引擎。

你说出一个关于"社会公平"的观点，智能体从不给出答案——而是通过对抗性检索和哲学分析，生成一记尖锐的反问，迫使你重新审视自己的前提。

## 快速开始

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 和 EMBEDDING_API_KEY

# 2. 安装后端依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. 构建向量知识库
.venv\Scripts\python.exe ingest.py

# 4. 安装前端依赖
cd frontend && npm install && cd ..

# 5. 启动后端（FastAPI :8000）
.venv\Scripts\python.exe server.py

# 6. 启动前端（Vite :5173）
cd frontend && npm run dev

# 或纯 CLI 模式（无需前端）
.venv\Scripts\python.exe main.py "富人应该多交税"
```

> Windows 中文乱码？先执行 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`

## 管线

```
START → Analyzer → Retriever (ChromaDB) ──距离≤阈值──→ Socratic_Ironist → 反问
                                         ──距离>阈值──→ Web_Search (Tavily) ──→ Socratic_Ironist → 反问
                                                   (无 Tavily Key 时降级直通 Ironist)
```

条件路由由 [`graph.py`](graph.py) 中的 `route_after_retriever()` 实现，基于 ChromaDB 余弦距离与 `SIMILARITY_THRESHOLD` 的比较。

| 节点 | 文件 | 职责 |
|------|------|------|
| **Analyzer** | `nodes.py` | 深度哲学分析。提取 5 个字段：`core_claim`（核心主张）、`underlying_assumption`（隐含前提）、`matched_philosophy`（匹配流派）、`opponent_philosophy`（经典对立流派）、`opponent_core_argument`（对立核心理由） |
| **Retriever** | `retriever_node.py` | 对抗性检索。先用 LLM 生成反事实查询词（而非搜索相似文本），再到 ChromaDB 中搜索经典反例，返回余弦距离分数 |
| **Web_Search** | `web_search_node.py` | 动态知识流。当 ChromaDB 检索质量不足时，通过 Tavily API 搜索互联网反例作为补充。含多重降级策略（Key 缺失/包未安装/API 异常） |
| **Socratic_Ironist** | `nodes.py` | 苏格拉底式讽刺审问者。佯装无知、推向极端、揭示定义中的不一致，输出一句生活化反问 |

### 数据模型 ([state.py](state.py))

`DialogueState` (TypedDict) 在节点间流转，完整字段：

| 字段 | 类型 | 来源节点 | 说明 |
|------|------|----------|------|
| `user_input` | `str` | 用户 | 原始输入 |
| `core_claim` | `str` | Analyzer | 提取的核心哲学主张 |
| `underlying_assumption` | `str` | Analyzer | 主张的隐含前提 |
| `matched_philosophy` | `str` | Analyzer | 匹配的哲学流派 |
| `opponent_philosophy` | `str` | Analyzer | 经典对立流派 |
| `opponent_core_argument` | `str` | Analyzer | 对立流派的核心理由 |
| `rag_counter_example` | `str` | Retriever / Web_Search | 检索到的反例文本 |
| `rag_relevance_score` | `float` | Retriever | ChromaDB 余弦距离（越小越相关） |
| `knowledge_source` | `str` | Retriever / Web_Search | `chromadb` / `web_search` / `fallback` |
| `socratic_question` | `str` | Socratic_Ironist | 最终反问 |
| `turn_count` | `int` | 调用方 | 对话轮数 |

`AnalyzerOutput` (Pydantic) 定义了 Analyzer 节点的结构化输出模型，包含 `PhilosophyCategory` 字面量类型。

## 架构

### 核心特点

**对抗性检索**: 不搜索"与用户观点相似"的文本，而是先生成"能反驳用户观点"的反事实查询词，再检索匹配的反例。这使得反驳更有针对性。

**质量感知路由**: ChromaDB 返回余弦距离分数（越小越相似）。分数达标 → 直接使用知识库反例；不达标 → 路由到 Tavily 网络搜索作为补充。

**深度哲学分析**: Analyzer 不仅提取主张和前提，还定位到具体哲学流派（罗尔斯/诺齐克/边沁等），并指出该流派最经典的论敌及其核心论点——Ironist 据此精准攻击。

### 哲学语料

6 篇结构化文档（3 篇主张 + 3 篇反例），覆盖三大哲学传统：

| 流派 | 主张来源 | 反例来源 | 核心争点 |
|------|----------|----------|----------|
| 分配正义 | 罗尔斯《正义论》 | 诺齐克 | 差异原则 vs 自我所有权 |
| 程序正义 | 诺齐克《无政府、国家与乌托邦》 | 罗尔斯 | 资格理论 vs 起点平等 |
| 功利主义 | 边沁/密尔 | 罗尔斯/德沃金 | 最大幸福 vs 个体权利 |

### 环境变量

| 变量 | 用途 |
|------|------|
| `OPENAI_API_KEY` / `OPENAI_API_BASE` / `OPENAI_MODEL_NAME` | 对话 LLM（Analyzer + Ironist） |
| `EMBEDDING_API_KEY` / `EMBEDDING_API_BASE` / `EMBEDDING_MODEL_NAME` | Embedding 模型（ChromaDB 检索） |
| `TAVILY_API_KEY` | 可选。网络搜索（当 ChromaDB 不够时） |
| `SIMILARITY_THRESHOLD` | 可选。余弦距离阈值，默认 0.5 |

> Embedding 与 LLM 可独立配置（DeepSeek 不支持 Embedding，推荐使用阿里云 DashScope 或 OpenAI）。

## 前后端

### 后端 — FastAPI SSE ([server.py](server.py))

```
http://localhost:8000
  POST /api/v1/socratic/stream   SSE 流式响应（请求体 {"text": "..."}）
  GET  /health                   健康检查
```

SSE 事件类型：

| 事件 | 触发时机 | 数据 |
|------|----------|------|
| `status` | 开始分析 | `{"phase": "started", "message": "..."}` |
| `node_start` | 进入节点 | `{"node": "Analyzer\|Retriever\|Web_Search\|Socratic_Ironist", "message": "..."}` |
| `node_end` | 节点完成 | `{"node": "...", "output": {...}}`（返回该节点 5 个分析字段） |
| `token` | Ironist LLM 流式输出 | `{"content": "..."}`（逐 token 推送） |
| `done` | 全流程完成 | 最终 `socratic_question`、`core_claim` 等 |
| `error` | 异常 | `{"message": "..."}` |

### 前端 — React SPA ([frontend/](frontend/))

```bash
cd frontend && npm run dev       # Vite 开发服务器 → http://localhost:5173
cd frontend && npm run build     # 生产构建 → dist/
```

技术栈：**React 19 + TypeScript + Vite + Framer Motion + react-markdown**

组件结构：

| 文件 | 职责 |
|------|------|
| [`useSocraticStream.ts`](frontend/src/hooks/useSocraticStream.ts) | SSE 流解析 Hook — 管理全生命周期（发起/取消/重连），解析 6 种 SSE 事件，逐 token 更新 `socratic_question` |
| [`App.tsx`](frontend/src/App.tsx) | 顶层布局 — 左侧 Sidebar（节点进度）, 右侧 DialogueArea（输入/输出） |
| [`Sidebar.tsx`](frontend/src/components/Sidebar.tsx) | 实时展示 Analyzer/Retriever/Web_Search/Ironist 四节点执行状态，带哲学流派颜色标签 |
| [`DialogueArea.tsx`](frontend/src/components/DialogueArea.tsx) | 用户输入框 + 苏格拉底提问流式渲染（react-markdown），支持撤销/取消 |
| [`types.ts`](frontend/src/types.ts) | `AgentState` 接口与后端 `DialogueState` 一一对应，中文节点标签 + 哲学流派色板 |

## 开发

```bash
# 运行测试
.venv\Scripts\python.exe -m pytest tests/

# 带覆盖率
.venv\Scripts\python.exe -m pytest tests/ --cov=nodes --cov=retriever_node --cov=state --cov-report=term-missing

# 代码检查
.venv\Scripts\python.exe -m ruff check . --exclude .venv
```

## 许可证

CC BY-NC 4.0 — 仅限非商业使用。
