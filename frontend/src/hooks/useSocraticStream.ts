import { useState, useRef, useCallback, useEffect, type Dispatch, type SetStateAction } from 'react';
import type { AgentState, StreamStatus } from '../types';
import { parseSseChunk, parseSseJsonEvent } from '../lib/sse';

const MAX_STREAMED_QUESTION_LENGTH = 8000;
const STREAM_ERROR_MESSAGE = '请求失败，请稍后重试。';

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
  error_message: '',
  turn_count: 0,
  has_contradiction: false,
  contradiction_details: null,
  target_premise_id: null,
};

/** 生成唯一会话 ID */
function generateThreadId(): string {
  return `web_${crypto.randomUUID()}`;
}

function hasExceededStreamLimit(currentLength: number, addition: string): boolean {
  return currentLength + addition.length > MAX_STREAMED_QUESTION_LENGTH;
}

function safeString(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value.slice(0, MAX_STREAMED_QUESTION_LENGTH) : fallback;
}

function rawString(value: unknown): string | null {
  return typeof value === 'string' ? value : null;
}

function safeNullableString(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  return typeof value === 'string' ? value.slice(0, MAX_STREAMED_QUESTION_LENGTH) : null;
}

function safeNumber(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function safeBoolean(value: unknown): boolean {
  return typeof value === 'boolean' ? value : false;
}

function setGenericError(
  setAgentState: Dispatch<SetStateAction<AgentState>>,
  setCurrentNode: Dispatch<SetStateAction<string>>,
  setStreamStatus: Dispatch<SetStateAction<StreamStatus>>,
  setIsThinking: Dispatch<SetStateAction<boolean>>,
): void {
  setStreamStatus('error');
  setIsThinking(false);
  setCurrentNode('idle');
  setAgentState(prev => ({
    ...prev,
    currentNode: 'idle',
    error_message: STREAM_ERROR_MESSAGE,
  }));
}

function getApiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL;
  if (configured) return configured.replace(/\/$/, '');

  const protocol = window.location.protocol || 'http:';
  const hostname = window.location.hostname || 'localhost';
  return `${protocol}//${hostname}:8000`;
}

export function useSocraticStream() {
  const [agentState, setAgentState] = useState<AgentState>(INITIAL_STATE);
  const [isThinking, setIsThinking] = useState(false);
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('idle');
  const [nodeProgress, setNodeProgress] = useState<string[]>([]);
  const [currentNode, setCurrentNode] = useState('idle');
  const abortRef = useRef<AbortController | null>(null);
  const questionLengthRef = useRef(0);
  const requestIdRef = useRef(0);
  const threadIdRef = useRef<string>(generateThreadId());

  useEffect(() => () => {
    requestIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    requestIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    questionLengthRef.current = 0;
    setAgentState(INITIAL_STATE);
    setIsThinking(false);
    setStreamStatus('idle');
    setNodeProgress([]);
    setCurrentNode('idle');
    threadIdRef.current = generateThreadId();
  }, []);

  const cancel = useCallback(() => {
    requestIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    questionLengthRef.current = 0;
    setIsThinking(false);
    setStreamStatus('canceled');
    setCurrentNode('idle');
    setAgentState(prev => ({ ...prev, currentNode: 'idle' }));
  }, []);

  const parseSSEMessage = useCallback((message: string, requestId: number) => {
    if (requestId !== requestIdRef.current) return;

    const parsed = parseSseJsonEvent(message);
    if (!parsed) return;

    const { event, data } = parsed;

    switch (event) {
      case 'status':
        setAgentState(prev => ({
          ...prev,
          currentNode: safeString(data.phase, 'started'),
          turn_count: safeNumber(data.turn, prev.turn_count),
        }));
        break;

      case 'node_start': {
        const node = safeString(data.node);
        if (!node) return;
        setCurrentNode(node);
        setAgentState(prev => ({ ...prev, currentNode: node }));
        break;
      }

      case 'node_end': {
        const node = safeString(data.node);
        if (!node) return;
        const output = data.output && typeof data.output === 'object' && !Array.isArray(data.output)
          ? data.output as Record<string, unknown>
          : {};
        setNodeProgress(prev => (prev.includes(node) ? prev : [...prev, node]));
        setAgentState(prev => ({
          ...prev,
          core_claim: safeString(output.core_claim, prev.core_claim),
          underlying_assumption: safeString(output.underlying_assumption, prev.underlying_assumption),
          matched_philosophy: safeString(output.matched_philosophy, prev.matched_philosophy),
          opponent_philosophy: safeString(output.opponent_philosophy, prev.opponent_philosophy),
          opponent_core_argument: safeString(output.opponent_core_argument, prev.opponent_core_argument),
          rag_counter_example: safeString(output.rag_counter_example, prev.rag_counter_example),
          rag_relevance_score: safeNumber(output.rag_relevance_score, prev.rag_relevance_score),
          knowledge_source: safeString(output.knowledge_source, prev.knowledge_source),
        }));
        break;
      }

      case 'token': {
        const content = rawString(data.content);
        if (content) {
          if (hasExceededStreamLimit(questionLengthRef.current, content)) {
            requestIdRef.current += 1;
            abortRef.current?.abort();
            abortRef.current = null;
            setGenericError(setAgentState, setCurrentNode, setStreamStatus, setIsThinking);
            return;
          }

          questionLengthRef.current += content.length;
          setCurrentNode('Socratic_Ironist');
          setAgentState(prev => ({
            ...prev,
            currentNode: 'Socratic_Ironist',
            socratic_question: prev.socratic_question + content,
          }));
        }
        break;
      }

      case 'done': {
        const rawQuestion = rawString(data.socratic_question);
        const finalQuestion = rawQuestion || null;
        const questionLength = finalQuestion?.length ?? questionLengthRef.current;

        if (questionLength > MAX_STREAMED_QUESTION_LENGTH) {
          requestIdRef.current += 1;
          abortRef.current?.abort();
          abortRef.current = null;
          setGenericError(setAgentState, setCurrentNode, setStreamStatus, setIsThinking);
          break;
        }

        questionLengthRef.current = finalQuestion?.length ?? questionLengthRef.current;
        setStreamStatus('completed');
        setIsThinking(false);
        setCurrentNode('idle');
        setAgentState(prev => ({
          ...prev,
          currentNode: 'idle',
          socratic_question: finalQuestion ?? prev.socratic_question,
          error_message: '',
          core_claim: safeString(data.core_claim, prev.core_claim),
          matched_philosophy: safeString(data.philosophy, prev.matched_philosophy),
          opponent_philosophy: safeString(data.opponent_philosophy, prev.opponent_philosophy),
          opponent_core_argument: safeString(data.opponent_core_argument, prev.opponent_core_argument),
          turn_count: safeNumber(data.turn, prev.turn_count),
          has_contradiction: safeBoolean(data.has_contradiction),
          contradiction_details: safeNullableString(data.contradiction_details),
          target_premise_id: safeNullableString(data.target_premise_id),
        }));
        break;
      }

      case 'error':
        setGenericError(setAgentState, setCurrentNode, setStreamStatus, setIsThinking);
        break;
    }
  }, []);

  const askSocrates = useCallback(async (userInput: string) => {
    abortRef.current?.abort();
    const abortController = new AbortController();
    let hasTerminalEvent = false;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    abortRef.current = abortController;
    questionLengthRef.current = 0;

    setIsThinking(true);
    setStreamStatus('streaming');
    setAgentState(prev => ({
      ...prev,
      socratic_question: '',
      error_message: '',
      currentNode: 'Analyzer',
      has_contradiction: false,
      contradiction_details: null,
      target_premise_id: null,
    }));
    setNodeProgress([]);
    setCurrentNode('Analyzer');

    try {
      const response = await fetch(`${getApiBaseUrl()}/api/v1/socratic/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ text: userInput, thread_id: threadIdRef.current }),
        signal: abortController.signal,
      });

      if (requestId !== requestIdRef.current) return;

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
        if (requestId !== requestIdRef.current) return;

        if (value) {
          const result = parseSseChunk(buffer, decoder.decode(value, { stream: !done }));
          buffer = result.buffer;

          for (const event of result.events) {
            const parsed = parseSseJsonEvent(event);
            if (parsed?.event === 'done' || parsed?.event === 'error') {
              hasTerminalEvent = true;
            }
            parseSSEMessage(event, requestId);
          }
        }
      }

      if (requestId !== requestIdRef.current) return;

      if (buffer.trim()) {
        const parsed = parseSseJsonEvent(buffer);
        if (parsed?.event === 'done' || parsed?.event === 'error') {
          hasTerminalEvent = true;
        }
        parseSSEMessage(buffer, requestId);
      }

      if (requestId === requestIdRef.current && !hasTerminalEvent) {
        setGenericError(setAgentState, setCurrentNode, setStreamStatus, setIsThinking);
      }
    } catch (error: unknown) {
      if (requestId !== requestIdRef.current) return;

      if (error instanceof DOMException && error.name === 'AbortError') {
        setStreamStatus('canceled');
        return;
      }
      setGenericError(setAgentState, setCurrentNode, setStreamStatus, setIsThinking);
    } finally {
      if (requestId === requestIdRef.current) {
        setIsThinking(false);
        abortRef.current = null;
      }
    }
  }, [parseSSEMessage]);

  return { agentState, isThinking, streamStatus, nodeProgress, currentNode, askSocrates, reset, cancel };
}
