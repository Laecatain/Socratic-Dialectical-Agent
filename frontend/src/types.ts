// 与后端 DialogueState 对应的前端状态模型

export interface AgentState {
  currentNode: string;
  /** 当前激活的 LangGraph 节点名 */
  core_claim: string;
  /** 提取出的核心主张 */
  underlying_assumption: string;
  /** 隐含前提 */
  matched_philosophy: string;
  /** 匹配的哲学流派 */
  opponent_philosophy: string;
  /** 经典对立流派 */
  opponent_core_argument: string;
  /** 对立流派的核心理由 */
  rag_counter_example: string;
  /** RAG 检索到的反例 */
  rag_relevance_score: number;
  /** ChromaDB 检索余弦距离 */
  knowledge_source: string;
  /** 知识来源 */
  socratic_question: string;
  /** 最终苏格拉底式提问（流式累加） */
  turn_count: number;
  /** 对话轮数 */
}

export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

/** 后端 SSE 事件类型 */
export type SSEEventType =
  | 'status'
  | 'node_start'
  | 'node_end'
  | 'token'
  | 'done'
  | 'error';

/** 节点中文标签 */
export const NODE_LABELS: Record<string, string> = {
  Analyzer: '思想解剖',
  Retriever: '反例检索',
  Web_Search: '联网搜索',
  Socratic_Ironist: '苏格拉底反诘',
  idle: '等待输入',
};

/** 哲学流派对应的 CSS 颜色 */
export const PHILOSOPHY_COLORS: Record<string, string> = {
  '分配正义': '#e07b39',
  '程序正义': '#4a90d9',
  '功利主义': '#5ba45b',
  '道义论': '#9b59b6',
  '资格理论': '#c0392b',
  '运气平等主义': '#16a085',
  '社群主义': '#d35400',
  '能力进路': '#2980b9',
  '未知': '#95a5a6',
};
