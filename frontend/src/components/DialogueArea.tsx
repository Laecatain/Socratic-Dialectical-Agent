import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import type { AgentState } from '../types';
import { NODE_LABELS } from '../types';

interface DialogueAreaProps {
  agentState: AgentState;
  isThinking: boolean;
  currentNode: string;
  askSocrates: (input: string) => void;
  reset: () => void;
  cancel: () => void;
}

export default function DialogueArea({
  agentState,
  isThinking,
  currentNode,
  askSocrates,
  reset,
  cancel,
}: DialogueAreaProps) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'socrates'; text: string }>>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevQuestion = useRef('');

  // When socratic_question finalizes, add it to messages
  useEffect(() => {
    if (!isThinking && agentState.socratic_question && agentState.socratic_question !== prevQuestion.current) {
      prevQuestion.current = agentState.socratic_question;
      setMessages(prev => [
        ...prev,
        { role: 'socrates', text: agentState.socratic_question },
      ]);
    }
  }, [isThinking, agentState.socratic_question]);

  // Auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [agentState.socratic_question, messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isThinking) return;

    prevQuestion.current = '';
    setMessages(prev => [...prev, { role: 'user', text: trimmed }]);
    setInput('');
    askSocrates(trimmed);
  };

  const handleReset = () => {
    reset();
    setMessages([]);
    prevQuestion.current = '';
    inputRef.current?.focus();
  };

  return (
    <main className="dialogue-area">
      <div className="dialogue-header">
        <h1>苏格拉底辩证对话</h1>
        {isThinking && (
          <span className="thinking-indicator">
            正在{NODE_LABELS[currentNode] || '思考'}...
          </span>
        )}
      </div>

      {/* 消息列表 */}
      <div className="messages-container" ref={scrollRef}>
        <AnimatePresence>
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              className={`message ${msg.role}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            >
              <div className="message-role">
                {msg.role === 'user' ? '🧑 你的暴论' : '🏛️ 苏格拉底'}
              </div>
              <div className={`message-content ${msg.role}`}>
                {msg.role === 'socrates' ? (
                  <ReactMarkdown>{msg.text}</ReactMarkdown>
                ) : (
                  <p>{msg.text}</p>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* 流式输出中的苏格拉底回复 */}
        {isThinking && agentState.socratic_question && (
          <motion.div
            className="message socrates streaming"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
          >
            <div className="message-role">
              🏛️ 苏格拉底
              <span className="typing-cursor" />
            </div>
            <div className="message-content socrates">
              <ReactMarkdown>{agentState.socratic_question}</ReactMarkdown>
              <span className="inline-cursor">▌</span>
            </div>
          </motion.div>
        )}

        {messages.length === 0 && !isThinking && (
          <div className="empty-state">
            <div className="empty-icon">🏛️</div>
            <p>提出你的暴论，让苏格拉底来检验它的根基。</p>
            <p className="empty-hint">
              「未经审视的人生不值得过」 — 苏格拉底
            </p>
          </div>
        )}
      </div>

      {/* 输入区域 */}
      <form className="input-area" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          className="socratic-input"
          placeholder="输入你的主张，例如：「富人应该多交税」..."
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={isThinking}
          autoFocus
        />
        <div className="input-actions">
          {isThinking ? (
            <button type="button" className="btn btn-cancel" onClick={cancel}>
              中断
            </button>
          ) : (
            <button type="submit" className="btn btn-send" disabled={!input.trim()}>
              发问
            </button>
          )}
          {messages.length > 0 && !isThinking && (
            <button type="button" className="btn btn-reset" onClick={handleReset}>
              重置
            </button>
          )}
        </div>
      </form>
    </main>
  );
}
