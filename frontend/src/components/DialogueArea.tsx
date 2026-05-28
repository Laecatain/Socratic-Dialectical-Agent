import { useState, useRef, useEffect, useMemo, type ReactNode } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import ReactMarkdown from 'react-markdown';
import type { AgentState, StreamStatus } from '../types';
import { NODE_LABELS } from '../types';

const MARKDOWN_COMPONENTS = {
  img: () => null,
  a: ({ href, children }: { href?: string; children?: ReactNode }) => (
    <a href={href} target="_blank" rel="noreferrer noopener">
      {children}
    </a>
  ),
};

type Message = { role: 'user' | 'socrates' | 'alert'; text: string };

function finalMessagesFor(agentState: AgentState): Message[] {
  if (!agentState.socratic_question) return [];

  if (agentState.has_contradiction) {
    return [
      {
        role: 'alert',
        text: `⚡ **逻辑伏击！** ${agentState.contradiction_details || '你前后的说法似乎不太一致...'}`,
      },
      { role: 'socrates', text: agentState.socratic_question },
    ];
  }

  return [{ role: 'socrates', text: agentState.socratic_question }];
}

function visibleMessagesFor(
  messages: Message[],
  agentState: AgentState,
  streamStatus: StreamStatus,
): Message[] {
  if (streamStatus === 'completed') {
    return [...messages, ...finalMessagesFor(agentState)];
  }

  if (streamStatus === 'error' && agentState.error_message) {
    return [...messages, { role: 'alert', text: agentState.error_message }];
  }

  return messages;
}

interface DialogueAreaProps {
  agentState: AgentState;
  isThinking: boolean;
  streamStatus: StreamStatus;
  currentNode: string;
  askSocrates: (input: string) => void;
  reset: () => void;
  cancel: () => void;
}

export default function DialogueArea({
  agentState,
  isThinking,
  streamStatus,
  currentNode,
  askSocrates,
  reset,
  cancel,
}: DialogueAreaProps) {
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const visibleMessages = useMemo(
    () => visibleMessagesFor(messages, agentState, streamStatus),
    [agentState, messages, streamStatus],
  );

  // Auto-scroll
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [agentState.socratic_question, visibleMessages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || isThinking) return;

    const completedMessages = streamStatus === 'completed' ? finalMessagesFor(agentState) : [];
    setMessages(prev => [...prev, ...completedMessages, { role: 'user', text: trimmed }]);
    setInput('');
    askSocrates(trimmed);
  };

  const handleReset = () => {
    reset();
    setMessages([]);
    inputRef.current?.focus();
  };

  return (
    <main className="dialogue-area">
      <div className="dialogue-header">
        <h1>苏格拉底辩证对话</h1>
        <div className="header-info">
          {agentState.turn_count > 0 && (
            <span className="turn-badge">第 {agentState.turn_count} 轮</span>
          )}
          {isThinking && (
            <span className="thinking-indicator">
              正在{NODE_LABELS[currentNode] || '思考'}...
            </span>
          )}
        </div>
      </div>

      {/* 消息列表 */}
      <div className="messages-container" ref={scrollRef}>
        <AnimatePresence>
          {visibleMessages.map((msg, i) => (
            <motion.div
              key={i}
              className={`message ${msg.role}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            >
              <div className="message-role">
                {msg.role === 'user' && '🧑 你的暴论'}
                {msg.role === 'socrates' && '🏛️ 苏格拉底'}
                {msg.role === 'alert' && '⚡ 逻辑伏击'}
              </div>
              <div className={`message-content ${msg.role}`}>
                {msg.role === 'socrates' || msg.role === 'alert' ? (
                  <ReactMarkdown components={MARKDOWN_COMPONENTS}>{msg.text}</ReactMarkdown>
                ) : (
                  <p>{msg.text}</p>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>

        {/* 流式输出中的苏格拉底回复 */}
        {streamStatus === 'streaming' && agentState.socratic_question && (
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
              <ReactMarkdown components={MARKDOWN_COMPONENTS}>{agentState.socratic_question}</ReactMarkdown>
              <span className="inline-cursor">▌</span>
            </div>
          </motion.div>
        )}

        {visibleMessages.length === 0 && !isThinking && (
          <div className="empty-state">
            <div className="empty-icon">🏛️</div>
            <p>提出你的暴论，让苏格拉底来检验它的根基。</p>
            <p className="empty-hint">
              系统会记住你每一轮的前提，一旦发现矛盾，苏格拉底将发动逻辑伏击。
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
          {visibleMessages.length > 0 && !isThinking && (
            <button type="button" className="btn btn-reset" onClick={handleReset}>
              新对话
            </button>
          )}
        </div>
      </form>
    </main>
  );
}
