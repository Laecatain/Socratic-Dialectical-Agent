# 苏格拉底辩证智能体

**Socratic Dialectical Agent** — 基于 LangGraph 的苏格拉底式提问引擎。

你说出一个关于"社会公平"的观点，智能体从不给出答案——而是通过对抗性检索和哲学分析，生成一记尖锐的反问，迫使你重新审视自己的前提。

## 快速开始

```bash
# 1. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 OPENAI_API_KEY 和 EMBEDDING_API_KEY

# 2. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3. 构建向量知识库
.venv\Scripts\python.exe ingest.py

# 4. 启动 CLI（交互模式）
.venv\Scripts\python.exe main.py

# 或单次执行模式
.venv\Scripts\python.exe main.py "富人应该多交税"
```

> Windows 中文乱码？先执行 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`

## 管线

```
用户输入 → Analyzer → Retriever (ChromaDB) ──达标──→ Socratic_Ironist → 反问
                                        └─不达标─→ Web_Search (Tavily) ──→ Socratic_Ironist
```

| 节点 | 文件 | 职责 |
|------|------|------|
| **Analyzer** | `nodes.py` | 深度哲学分析。提取核心主张、隐含前提、匹配哲学流派，并定位经典对立流派及其核心理由 |
| **Retriever** | `retriever_node.py` | 对抗性检索。先用 LLM 生成反事实查询词（而非搜索相似文本），再到 ChromaDB 中搜索经典反例，返回余弦距离分数 |
| **Web_Search** | `web_search_node.py` | 动态知识流。当 ChromaDB 检索质量不足时，通过 Tavily API 搜索互联网反例作为补充 |
| **Socratic_Ironist** | `nodes.py` | 苏格拉底式讽刺审问者。佯装无知、推向极端、揭示定义中的不一致，输出一句生活化反问 |

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

## 服务端

```bash
# 启动 FastAPI SSE 流式服务器
.venv\Scripts\python.exe server.py
# → http://localhost:8000
# → POST /api/v1/socratic/stream (SSE 流式响应)
# → GET  /health
```

前端可通过 SSE 接收逐节点状态更新与流式 token 输出。

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
