// Vitest + Testing Library coverage for KanbanDispatchPanel.
// All network calls go through global fetch, which we mock per test.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { KanbanDispatchPanel } from '../KanbanDispatchPanel';
import type { ReviewPage } from '../../types';

function makePage(overrides: Partial<ReviewPage> = {}): ReviewPage {
  return {
    stem: 'improvement-test-page',
    rel_path: 'wiki/improvements/improvement-test-page.md',
    abs_path: '/tmp/improvement-test-page.md',
    frontmatter: {},
    body: '# improvement-test-page\n',
    ...overrides,
  };
}

interface MockResponseInit {
  status?: number;
  body?: unknown;
}

function mockResponse({ status = 200, body = {} }: MockResponseInit): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'ERR',
    json: async () => body,
  } as unknown as Response;
}

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  globalThis.fetch = fetchMock as unknown as typeof fetch;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('KanbanDispatchPanel', () => {
  it('renders the board dropdown after boards load', async () => {
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: {
          boards: [
            { slug: 'ops', name: 'Ops', counts: { todo: 2 } },
            { slug: 'kb', name: 'Knowledge Base', counts: {} },
          ],
        },
      }),
    );

    render(<KanbanDispatchPanel page={makePage()} />);
    expect(screen.getByText(/loading kanban boards/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByLabelText(/kanban board/i)).toBeInTheDocument();
    });
    const select = screen.getByLabelText(/kanban board/i) as HTMLSelectElement;
    expect(select.value).toBe('ops');
    expect(screen.getByRole('option', { name: /Ops/ })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Knowledge Base/ })).toBeInTheDocument();
  });

  it('shows install hint and disables the button when no boards exist', async () => {
    fetchMock.mockResolvedValueOnce(mockResponse({ body: { boards: [] } }));

    render(<KanbanDispatchPanel page={makePage()} />);
    await waitFor(() => {
      expect(screen.getByText(/no kanban boards available/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /send to kanban/i })).toBeDisabled();
  });

  it('renders the re-dispatch warning when kanban_dispatches has entries', async () => {
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: { boards: [{ slug: 'ops', name: 'Ops', counts: {} }] },
      }),
    );

    const page = makePage({
      frontmatter: {
        // Spec §6.1: persisted entry uses `board:` (not `board_slug`).
        kanban_dispatches: [
          {
            board: 'ops',
            task_id: 'task-abc-123',
            dispatched_at: '2026-05-26T09:30:00Z',
            direction: 'investigate retries',
          },
        ],
      },
    });
    render(<KanbanDispatchPanel page={page} />);

    await waitFor(() => {
      expect(
        screen.getByText(/sending again creates a new task/i),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole('button', { name: /send again to kanban/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('task-abc-123')).toBeInTheDocument();
  });

  it('POSTs the dispatch, calls onDispatched, and shows the inline banner', async () => {
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: { boards: [{ slug: 'ops', name: 'Ops', counts: { todo: 1 } }] },
      }),
    );
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: {
          task_id: 'task-new-7',
          board_slug: 'ops',
          dispatched_at: '2026-05-26T11:00:00Z',
        },
      }),
    );

    const onDispatched = vi.fn();
    render(<KanbanDispatchPanel page={makePage()} onDispatched={onDispatched} />);

    await waitFor(() => {
      expect(screen.getByLabelText(/kanban board/i)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/task direction/i), {
      target: { value: 'do the thing' },
    });
    fireEvent.click(screen.getByRole('button', { name: /send to kanban/i }));

    await waitFor(() => expect(onDispatched).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('status')).toHaveTextContent('task-new-7');

    // Spec §7.2: request body field is `direction_note` (nullable).
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/pages/improvement-test-page/send-to-kanban',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({
          board_slug: 'ops',
          direction_note: 'do the thing',
        }),
      }),
    );
  });

  it('sends direction_note: null when the textarea is empty', async () => {
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: { boards: [{ slug: 'ops', name: 'Ops', counts: {} }] },
      }),
    );
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: {
          task_id: 'task-empty-1',
          board_slug: 'ops',
          dispatched_at: '2026-05-26T11:30:00Z',
        },
      }),
    );

    render(<KanbanDispatchPanel page={makePage()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/kanban board/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send to kanban/i }));
    });

    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/pages/improvement-test-page/send-to-kanban',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ board_slug: 'ops', direction_note: null }),
      }),
    );
  });

  it('renders a 503 error message verbatim from the API detail', async () => {
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: { boards: [{ slug: 'ops', name: 'Ops', counts: {} }] },
      }),
    );
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        status: 503,
        body: { detail: 'Hermes is unavailable. Try again later.' },
      }),
    );

    render(<KanbanDispatchPanel page={makePage()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/kanban board/i)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /send to kanban/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/hermes is unavailable\. try again later\./i),
      ).toBeInTheDocument();
    });
  });

  it('renders a 502 upstream message verbatim', async () => {
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: { boards: [{ slug: 'ops', name: 'Ops', counts: {} }] },
      }),
    );
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        status: 502,
        body: { detail: 'Upstream Hermes rejected: invalid board' },
      }),
    );

    render(<KanbanDispatchPanel page={makePage()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/kanban board/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send to kanban/i }));
    });

    expect(
      screen.getByText(/upstream hermes rejected: invalid board/i),
    ).toBeInTheDocument();
  });

  it('renders the orphan-task instruction when 500 carries orphan_task_id', async () => {
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: { boards: [{ slug: 'ops', name: 'Ops', counts: {} }] },
      }),
    );
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        status: 500,
        body: {
          detail: 'Rollback failed after dispatch.',
          orphan_task_id: 'orphan-task-99',
        },
      }),
    );

    render(<KanbanDispatchPanel page={makePage()} />);
    await waitFor(() => {
      expect(screen.getByLabelText(/kanban board/i)).toBeInTheDocument();
    });

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /send to kanban/i }));
    });

    expect(screen.getByText(/rollback failed after dispatch/i)).toBeInTheDocument();
    expect(screen.getByText(/orphan task: orphan-task-99/i)).toBeInTheDocument();
    expect(
      screen.getByText(/hermes kanban archive orphan-task-99/i),
    ).toBeInTheDocument();
  });
});
