import { describe, expect, it } from 'vitest';
import { parseSseChunk, parseSseJsonEvent } from './sse';

describe('SSE parsing', () => {
  it('parses a JSON event from a complete chunk', () => {
    const result = parseSseChunk('', 'event: token\ndata: {"content":"你"}\n\n');

    expect(result.buffer).toBe('');
    expect(result.events).toHaveLength(1);
    expect(parseSseJsonEvent(result.events[0])).toEqual({
      event: 'token',
      data: { content: '你' },
    });
  });

  it('keeps incomplete events buffered across chunks', () => {
    const first = parseSseChunk('', 'event: token\ndata: {"content":"你"}\n\nevent: token\ndata: {"content":"好"}\n');
    const second = parseSseChunk(first.buffer, '\n');

    expect(first.events.map(event => parseSseJsonEvent(event)?.data)).toEqual([{ content: '你' }]);
    expect(second.events.map(event => parseSseJsonEvent(event)?.data)).toEqual([{ content: '好' }]);
    expect(second.buffer).toBe('');
  });

  it('preserves token order for multiple events in one chunk', () => {
    const result = parseSseChunk(
      '',
      'event: token\ndata: {"content":"贫"}\n\nevent: token\ndata: {"content":"困"}\n\n',
    );

    const tokens = result.events.map(event => parseSseJsonEvent(event)?.data.content);

    expect(tokens).toEqual(['贫', '困']);
  });

  it('ignores comments and malformed JSON deterministically', () => {
    const result = parseSseChunk('', ': keep-alive\n\nevent: token\ndata: {bad json}\n\n');

    expect(result.events).toHaveLength(1);
    expect(parseSseJsonEvent(result.events[0])).toBeNull();
  });

  it('accepts many complete events in a large network chunk', () => {
    const event = 'event: token\ndata: {"content":"a"}\n\n';
    const result = parseSseChunk('', event.repeat(3000));

    expect(result.events).toHaveLength(3000);
    expect(result.buffer).toBe('');
  });

  it('keeps event blocks that start with comments', () => {
    const result = parseSseChunk('', ': keep-alive\nevent: token\ndata: {"content":"注释后事件"}\n\n');

    expect(result.events).toHaveLength(1);
    expect(parseSseJsonEvent(result.events[0])).toEqual({
      event: 'token',
      data: { content: '注释后事件' },
    });
  });

  it('rejects oversized incomplete buffers', () => {
    expect(() => parseSseChunk('', 'x'.repeat(64 * 1024 + 1))).toThrow(
      'SSE buffer exceeded maximum size',
    );
  });

  it('rejects oversized complete events', () => {
    expect(() => parseSseChunk('', `event: token\ndata: ${'x'.repeat(64 * 1024 + 1)}\n\n`)).toThrow(
      'SSE event exceeded maximum size',
    );
  });
});
