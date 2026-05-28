import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSocraticStream } from './useSocraticStream';

class ControlledStream {
  private controller: ReadableStreamDefaultController<Uint8Array> | null = null;
  readonly readable = new ReadableStream<Uint8Array>({
    start: controller => {
      this.controller = controller;
    },
  });

  enqueue(text: string): void {
    this.controller?.enqueue(new TextEncoder().encode(text));
  }

  close(): void {
    this.controller?.close();
  }
}

async function pushChunk(stream: ControlledStream, chunk: string): Promise<void> {
  await act(async () => {
    stream.enqueue(chunk);
    await Promise.resolve();
  });
}

async function closeStream(stream: ControlledStream): Promise<void> {
  await act(async () => {
    stream.close();
    await Promise.resolve();
  });
}

describe('useSocraticStream lifecycle', () => {
  let streams: ControlledStream[];

  beforeEach(() => {
    streams = [];
    vi.stubGlobal('fetch', vi.fn(() => {
      const stream = new ControlledStream();
      streams.push(stream);
      return Promise.resolve(new Response(stream.readable, { status: 200, statusText: 'OK' }));
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('marks cancellation explicitly without completing the stream', async () => {
    const { result } = renderHook(() => useSocraticStream());

    act(() => {
      void result.current.askSocrates('第一问');
    });

    await waitFor(() => expect(streams).toHaveLength(1));
    expect(fetch).toHaveBeenCalledWith(
      `${window.location.protocol}//${window.location.hostname}:8000/api/v1/socratic/stream`,
      expect.objectContaining({ credentials: 'include' }),
    );
    await pushChunk(streams[0], 'event: token\ndata: {"content":"半截"}\n\n');
    await waitFor(() => expect(result.current.agentState.socratic_question).toBe('半截'));

    act(() => {
      result.current.cancel();
    });

    await waitFor(() => expect(result.current.streamStatus).toBe('canceled'));
    expect(result.current.isThinking).toBe(false);
  });

  it('ignores chunks from an older request after a newer request starts', async () => {
    const { result } = renderHook(() => useSocraticStream());

    act(() => {
      void result.current.askSocrates('旧请求');
    });

    await waitFor(() => expect(streams).toHaveLength(1));
    await pushChunk(streams[0], 'event: token\ndata: {"content":"旧"}\n\n');
    await waitFor(() => expect(result.current.agentState.socratic_question).toBe('旧'));

    act(() => {
      void result.current.askSocrates('新请求');
    });

    await waitFor(() => expect(streams).toHaveLength(2));
    await waitFor(() => expect(result.current.agentState.socratic_question).toBe(''));

    await pushChunk(streams[0], 'event: token\ndata: {"content":"迟到"}\n\n');
    await closeStream(streams[0]);

    expect(result.current.agentState.socratic_question).toBe('');
    expect(result.current.streamStatus).toBe('streaming');

    await pushChunk(
      streams[1],
      'event: token\ndata: {"content":"新"}\n\nevent: done\ndata: {"socratic_question":"新完成","turn":1}\n\ndata: [DONE]\n\n',
    );
    await closeStream(streams[1]);

    await waitFor(() => expect(result.current.streamStatus).toBe('completed'));
    expect(result.current.agentState.socratic_question).toBe('新完成');
    expect(result.current.agentState.has_contradiction).toBe(false);
    expect(result.current.isThinking).toBe(false);
  });

  it('keeps defensive stream aborts in error state', async () => {
    const { result } = renderHook(() => useSocraticStream());

    act(() => {
      void result.current.askSocrates('超长请求');
    });

    await waitFor(() => expect(streams).toHaveLength(1));
    await pushChunk(
      streams[0],
      `event: token\ndata: ${JSON.stringify({ content: 'x'.repeat(8001) })}\n\n`,
    );

    await waitFor(() => expect(result.current.streamStatus).toBe('error'));
    expect(result.current.agentState.error_message).toBe('请求失败，请稍后重试。');
    expect(result.current.isThinking).toBe(false);
  });

  it('rejects oversized done payloads', async () => {
    const { result } = renderHook(() => useSocraticStream());

    act(() => {
      void result.current.askSocrates('超长完成');
    });

    await waitFor(() => expect(streams).toHaveLength(1));
    await pushChunk(
      streams[0],
      `event: done\ndata: ${JSON.stringify({ socratic_question: 'x'.repeat(8001), turn: 1 })}\n\n`,
    );

    await waitFor(() => expect(result.current.streamStatus).toBe('error'));
    expect(result.current.agentState.socratic_question).toBe('');
    expect(result.current.agentState.error_message).toBe('请求失败，请稍后重试。');
  });

  it('ignores invalid SSE payload field types', async () => {
    const { result } = renderHook(() => useSocraticStream());

    act(() => {
      void result.current.askSocrates('错误类型');
    });

    await waitFor(() => expect(streams).toHaveLength(1));
    await pushChunk(
      streams[0],
      'event: node_end\ndata: {"node":"Retriever","output":{"rag_relevance_score":"bad"}}\n\nevent: done\ndata: {"socratic_question":"完成","has_contradiction":"bad","contradiction_details":42,"target_premise_id":false,"turn":"bad"}\n\ndata: [DONE]\n\n',
    );
    await closeStream(streams[0]);

    await waitFor(() => expect(result.current.streamStatus).toBe('completed'));
    expect(result.current.agentState.rag_relevance_score).toBe(0);
    expect(result.current.agentState.has_contradiction).toBe(false);
    expect(result.current.agentState.contradiction_details).toBeNull();
    expect(result.current.agentState.target_premise_id).toBeNull();
    expect(result.current.agentState.turn_count).toBe(0);
  });

  it('keeps streamed tokens when done has an empty final question', async () => {
    const { result } = renderHook(() => useSocraticStream());

    act(() => {
      void result.current.askSocrates('空完成');
    });

    await waitFor(() => expect(streams).toHaveLength(1));
    await pushChunk(
      streams[0],
      'event: token\ndata: {"content":"已流式"}\n\nevent: done\ndata: {"socratic_question":"","turn":1}\n\ndata: [DONE]\n\n',
    );
    await closeStream(streams[0]);

    await waitFor(() => expect(result.current.streamStatus).toBe('completed'));
    expect(result.current.agentState.socratic_question).toBe('已流式');
  });

  it('reports an error when the stream closes without a terminal event', async () => {
    const { result } = renderHook(() => useSocraticStream());

    act(() => {
      void result.current.askSocrates('无终止');
    });

    await waitFor(() => expect(streams).toHaveLength(1));
    await pushChunk(streams[0], 'event: token\ndata: {"content":"半截"}\n\n');
    await closeStream(streams[0]);

    await waitFor(() => expect(result.current.streamStatus).toBe('error'));
    expect(result.current.agentState.error_message).toBe('请求失败，请稍后重试。');
    expect(result.current.isThinking).toBe(false);
  });
});
