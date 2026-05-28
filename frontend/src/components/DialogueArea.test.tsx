import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DialogueArea from './DialogueArea';
import type { AgentState, StreamStatus } from '../types';

const baseState: AgentState = {
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

interface RenderOptions {
  state?: Partial<AgentState>;
  streamStatus?: StreamStatus;
  isThinking?: boolean;
}

function renderDialogue({ state, streamStatus = 'idle', isThinking = false }: RenderOptions = {}) {
  return render(
    <DialogueArea
      agentState={{ ...baseState, ...state }}
      isThinking={isThinking}
      streamStatus={streamStatus}
      currentNode="idle"
      askSocrates={vi.fn()}
      reset={vi.fn()}
      cancel={vi.fn()}
    />,
  );
}

describe('DialogueArea stream finalization', () => {
  it('does not append partial Socrates output after cancellation', async () => {
    renderDialogue({
      streamStatus: 'canceled',
      state: { socratic_question: '半截回答' },
    });

    await waitFor(() => {
      expect(screen.queryByText('半截回答')).not.toBeInTheDocument();
    });
  });

  it('appends Socrates output only after completed streams', async () => {
    renderDialogue({
      streamStatus: 'completed',
      isThinking: true,
      state: { socratic_question: '完整反问' },
    });

    expect(await screen.findByText('完整反问')).toBeInTheDocument();
    expect(screen.queryByText('▌')).not.toBeInTheDocument();
  });

  it('shows a safe user-facing error after failed streams', async () => {
    renderDialogue({
      streamStatus: 'error',
      state: { error_message: '请求失败，请稍后重试。' },
    });

    expect(await screen.findByText('请求失败，请稍后重试。')).toBeInTheDocument();
  });

  it('does not render markdown images from completed content', async () => {
    renderDialogue({
      streamStatus: 'completed',
      state: { socratic_question: '![tracker](https://example.invalid/pixel.png)链接' },
    });

    expect(await screen.findByText('链接')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('does not render markdown images while streaming', async () => {
    renderDialogue({
      streamStatus: 'streaming',
      state: { socratic_question: '![tracker](https://example.invalid/pixel.png)流式链接' },
    });

    expect(await screen.findByText('流式链接')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});
