import { useState, useRef, useCallback } from 'react';
import type { AgentState } from '../types';

const INITIAL_STATE: AgentState = {
  currentNode: 'idle',
  core_claim: '',
  underlying_assumption: '',
  matched_philosophy: '',
  opponent_philosophy: '',
  opponent_core_argument: '',
  rag_counter_example: '',
  rag_relevance_score: 0,
  knowledge_source: '',
  socratic_question: '',
  turn_count: 0,
};

export function useSocraticStream() {
  const [agentState, setAgentState] = useState<AgentState>(INITIAL_STATE);
  const [isThinking, setIsThinking] = useState(false);
  const [nodeProgress, setNodeProgress] = useState<string[]>([]);
  const [currentNode, setCurrentNode] = useState('idle');
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    setAgentState(INITIAL_STATE);
    setIsThinking(false);
    setNodeProgress([]);
    setCurrentNode('idle');
  }, []);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    setIsThinking(false);
  }, []);

  const askSocrates = useCallback(async (userInput: string) => {
    // Abort previous request if any
    abortRef.current?.abort();
    const abortController = new AbortController();
    abortRef.current = abortController;

    setIsThinking(true);
    setAgentState({ ...INITIAL_STATE, turn_count: 1 });
    setNodeProgress([]);
    setCurrentNode('Analyzer');

    try {
      const response = await fetch('http://localhost:8000/api/v1/socratic/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: userInput }),
        signal: abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      if (!response.body) throw new Error('No readable stream');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let done = false;

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;
        if (value) {
          buffer += decoder.decode(value, { stream: !done });
          // Process complete SSE messages from buffer
          const parts = buffer.split('\n\n');
          buffer = parts.pop() || ''; // Keep incomplete last part

          for (const part of parts) {
            if (!part.trim() || part.trim() === 'data: [DONE]') continue;
            parseSSEMessage(part);
          }
        }
      }

      // Process any remaining buffer
      if (buffer.trim() && buffer.trim() !== 'data: [DONE]') {
        parseSSEMessage(buffer);
      }
    } catch (error: unknown) {
      if (error instanceof DOMException && error.name === 'AbortError') {
        return; // User cancelled, ignore
      }
      console.error('Stream error:', error);
      setAgentState(prev => ({
        ...prev,
        socratic_question: prev.socratic_question || `[错误] ${error instanceof Error ? error.message : '连接中断'}`,
      }));
    } finally {
      setIsThinking(false);
    }
  }, []);

  const parseSSEMessage = useCallback((message: string) => {
    const lines = message.split('\n');
    let eventType = '';
    let dataStr = '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        dataStr = line.slice(6).trim();
      }
    }

    if (!dataStr || dataStr === '[DONE]') return;

    try {
      const data = JSON.parse(dataStr);

      switch (eventType) {
        case 'status':
          setAgentState(prev => ({ ...prev, currentNode: data.phase || 'started' }));
          break;

        case 'node_start': {
          const node = data.node as string;
          setCurrentNode(node);
          setNodeProgress(prev => [...prev, node]);
          setAgentState(prev => ({ ...prev, currentNode: node }));
          break;
        }

        case 'node_end': {
          const output = (data.output || {}) as Record<string, unknown>;
          setAgentState(prev => ({
            ...prev,
            core_claim: (output.core_claim as string) ?? prev.core_claim,
            underlying_assumption: (output.underlying_assumption as string) ?? prev.underlying_assumption,
            matched_philosophy: (output.matched_philosophy as string) ?? prev.matched_philosophy,
            opponent_philosophy: (output.opponent_philosophy as string) ?? prev.opponent_philosophy,
            opponent_core_argument: (output.opponent_core_argument as string) ?? prev.opponent_core_argument,
            rag_counter_example: (output.rag_counter_example as string) ?? prev.rag_counter_example,
            rag_relevance_score: (output.rag_relevance_score as number) ?? prev.rag_relevance_score,
            knowledge_source: (output.knowledge_source as string) ?? prev.knowledge_source,
          }));
          break;
        }

        case 'token': {
          const content = data.content as string;
          if (content) {
            setCurrentNode('Socratic_Ironist');
            setAgentState(prev => ({
              ...prev,
              currentNode: 'Socratic_Ironist',
              socratic_question: prev.socratic_question + content,
            }));
          }
          break;
        }

        case 'done':
          setAgentState(prev => ({
            ...prev,
            currentNode: 'idle',
            socratic_question: (data.socratic_question as string) || prev.socratic_question,
            core_claim: (data.core_claim as string) || prev.core_claim,
            matched_philosophy: (data.philosophy as string) || prev.matched_philosophy,
            opponent_philosophy: (data.opponent_philosophy as string) || prev.opponent_philosophy,
            opponent_core_argument: (data.opponent_core_argument as string) || prev.opponent_core_argument,
          }));
          setCurrentNode('idle');
          break;

        case 'error':
          setAgentState(prev => ({
            ...prev,
            socratic_question: `[错误] ${data.message || '未知错误'}`,
          }));
          break;
      }
    } catch {
      // Ignore malformed JSON
    }
  }, []);

  return { agentState, isThinking, nodeProgress, currentNode, askSocrates, reset, cancel };
}
