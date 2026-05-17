import { motion, AnimatePresence } from 'framer-motion';
import type { AgentState } from '../types';
import { NODE_LABELS, PHILOSOPHY_COLORS } from '../types';

interface SidebarProps {
  agentState: AgentState;
  nodeProgress: string[];
  currentNode: string;
  isThinking: boolean;
}

/** 节点图标映射 */
const NODE_ICONS: Record<string, string> = {
  Analyzer: '🔍',
  Retriever: '📚',
  Web_Search: '🌐',
  Socratic_Ironist: '🎭',
  idle: '⏸️',
};

const FLOW_ORDER = ['Analyzer', 'Retriever', 'Web_Search', 'Socratic_Ironist'];

export default function Sidebar({ agentState, nodeProgress, currentNode, isThinking }: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h2>思想解剖台</h2>
        <div className={`status-dot ${isThinking ? 'active' : ''}`} />
      </div>

      {/* 矛盾伏击警报 */}
      <AnimatePresence>
        {agentState.has_contradiction && (
          <motion.section
            className="sidebar-section contradiction-alert"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.4 }}
          >
            <h3>⚡ 逻辑矛盾检测</h3>
            <div className="alert-content">
              <span className="alert-premise">
                伏击前提: {agentState.target_premise_id || 'N/A'}
              </span>
              {agentState.contradiction_details && (
                <p className="alert-detail">{agentState.contradiction_details}</p>
              )}
            </div>
          </motion.section>
        )}
      </AnimatePresence>

      {/* 当前执行节点 */}
      <section className="sidebar-section">
        <h3>执行流程</h3>
        <div className="node-flow">
          {FLOW_ORDER.map((nodeName, i) => {
            const isActive = currentNode === nodeName;
            const isDone = nodeProgress.includes(nodeName);
            const isPending = !isDone && !isActive;

            return (
              <div key={nodeName} className="node-flow-item">
                {i > 0 && (
                  <div className={`flow-connector ${isDone ? 'done' : ''}`} />
                )}
                <div
                  className={`node-badge ${isActive ? 'active' : ''} ${isDone ? 'done' : ''} ${isPending ? 'pending' : ''}`}
                >
                  <span className="node-icon">{NODE_ICONS[nodeName] || '⚙️'}</span>
                  <span className="node-label">{NODE_LABELS[nodeName] || nodeName}</span>
                  {isActive && <span className="pulse-dot" />}
                  {isDone && <span className="check-mark">✓</span>}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 哲学雷达面板 */}
      <AnimatePresence>
        {agentState.core_claim && (
          <motion.section
            className="sidebar-section philosophy-panel"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
          >
            <h3>哲学雷达</h3>

            <div className="field-item">
              <span className="field-label">核心主张</span>
              <p className="field-value claim-text">{agentState.core_claim}</p>
            </div>

            {agentState.underlying_assumption && (
              <div className="field-item">
                <span className="field-label">隐含前提</span>
                <p className="field-value">{agentState.underlying_assumption}</p>
              </div>
            )}

            {agentState.matched_philosophy && (
              <div className="field-item">
                <span className="field-label">🎯 归属流派</span>
                <span
                  className="philosophy-tag"
                  style={{
                    backgroundColor: PHILOSOPHY_COLORS[agentState.matched_philosophy] || '#95a5a6',
                  }}
                >
                  {agentState.matched_philosophy}
                </span>
              </div>
            )}

            {agentState.opponent_philosophy && (
              <div className="field-item">
                <span className="field-label">⚔️ 宿敌流派</span>
                <span className="philosophy-tag opponent">
                  {agentState.opponent_philosophy}
                </span>
              </div>
            )}

            {agentState.opponent_core_argument && (
              <div className="field-item">
                <span className="field-label">对立论证</span>
                <p className="field-value">{agentState.opponent_core_argument}</p>
              </div>
            )}
          </motion.section>
        )}
      </AnimatePresence>

      {/* RAG 检索面板 */}
      <AnimatePresence>
        {(agentState.rag_relevance_score > 0 || agentState.knowledge_source) && (
          <motion.section
            className="sidebar-section rag-panel"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}
          >
            <h3>RAG 检索面板</h3>

            {agentState.rag_relevance_score > 0 && (
              <div className="field-item">
                <span className="field-label">相似度分数</span>
                <SimilarityGauge score={agentState.rag_relevance_score} />
              </div>
            )}

            {agentState.knowledge_source && (
              <div className="field-item">
                <span className="field-label">知识来源</span>
                <span className={`source-badge ${agentState.knowledge_source}`}>
                  {agentState.knowledge_source === 'chromadb' ? '📦 ChromaDB' :
                   agentState.knowledge_source === 'web_search' ? '🌐 联网搜索' :
                   agentState.knowledge_source === 'fallback' ? '⚠️ 降级' :
                   agentState.knowledge_source}
                </span>
              </div>
            )}

            {agentState.rag_counter_example && (
              <div className="field-item">
                <span className="field-label">反例卡片</span>
                <blockquote className="counter-example-card">
                  {agentState.rag_counter_example}
                </blockquote>
              </div>
            )}
          </motion.section>
        )}
      </AnimatePresence>
    </aside>
  );
}

/** 相似度分数仪表盘 */
function SimilarityGauge({ score }: { score: number }) {
  const THRESHOLD = 0.5;
  // S_similarity = 1.0 - D_cosine, so ≥0.5 is good
  const percentage = Math.min((score / 1.0) * 100, 100);
  const isGood = score >= THRESHOLD;

  return (
    <div className="similarity-gauge">
      <div className="gauge-bar">
        <motion.div
          className={`gauge-fill ${isGood ? 'good' : 'bad'}`}
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.6, ease: 'easeOut' }}
        />
        <div className="gauge-threshold" style={{ left: '50%' }} />
      </div>
      <div className="gauge-labels">
        <span className={`gauge-value ${isGood ? 'good' : 'bad'}`}>
          {score.toFixed(3)}
        </span>
        <span className="gauge-verdict">
          {isGood ? '✅ 达标 — 直接提问' : '❌ 未达标 — 触发降级'}
        </span>
      </div>
    </div>
  );
}
