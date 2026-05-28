const MAX_SSE_BUFFER_LENGTH = 64 * 1024;
const MAX_SSE_EVENT_LENGTH = 64 * 1024;

export interface ParsedSseEvent {
  event: string;
  data: string;
}

export interface SseChunkResult {
  events: string[];
  buffer: string;
}

export interface ParsedSseJsonEvent {
  event: string;
  data: Record<string, unknown>;
}

export function parseSseChunk(buffer: string, chunk: string): SseChunkResult {
  const normalized = `${buffer}${chunk}`.replace(/\r\n/g, '\n');
  const parts = normalized.split('\n\n');
  const nextBuffer = parts.pop() ?? '';

  if (nextBuffer.length > MAX_SSE_BUFFER_LENGTH) {
    throw new Error('SSE buffer exceeded maximum size');
  }

  const events = parts.filter(part => {
    const lines = part.split('\n').map(line => line.trim());
    return lines.some(line => line.startsWith('data:'));
  });

  if (events.some(event => event.length > MAX_SSE_EVENT_LENGTH)) {
    throw new Error('SSE event exceeded maximum size');
  }

  return { events, buffer: nextBuffer };
}

export function parseSseEvent(message: string): ParsedSseEvent | null {
  const lines = message.replace(/\r\n/g, '\n').split('\n');
  const dataLines: string[] = [];
  let event = 'message';

  for (const line of lines) {
    if (!line || line.startsWith(':')) continue;

    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) return null;

  return {
    event,
    data: dataLines.join('\n'),
  };
}

export function parseSseJsonEvent(message: string): ParsedSseJsonEvent | null {
  const event = parseSseEvent(message);

  if (!event || event.data === '[DONE]') return null;

  try {
    const data: unknown = JSON.parse(event.data);

    if (!data || typeof data !== 'object' || Array.isArray(data)) return null;

    return { event: event.event, data: data as Record<string, unknown> };
  } catch {
    return null;
  }
}
