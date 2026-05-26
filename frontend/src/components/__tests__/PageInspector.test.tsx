// Coverage for PageInspector. Spec §9.2: 2 tests.
//   1. row click opens, ESC closes
//   2. dirty + ESC → confirm dialog

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { PageInspector } from '../PageInspector';
import type { Decision } from '../../types';

function makeDecision(): Decision {
  return {
    stem: 'hermes-zombie-session',
    path: 'wiki/entities/hermes/2026-05/hermes-zombie-session.md',
    type: 'entity',
    category: 'system-ops',
    tags: [],
    review_status: 'approved',
    sources: [],
    captured_at: '2026-05-01T12:00:00+09:00',
    last_edited_at: '2026-05-26T14:23:00+09:00',
    dispatch_summary: null,
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
  // The inspector fans out two GETs on mount: /api/enums/categories
  // (load suggestions) and /api/pages/{stem}/timeline. Default mock
  // returns a shape that satisfies both contracts; individual tests
  // override per-call when needed.
  fetchMock.mockImplementation((url: string) => {
    if (url.includes('/enums/categories')) {
      return Promise.resolve(mockResponse({ body: { categories: [] } }));
    }
    return Promise.resolve(mockResponse({ body: { items: [], total: 0 } }));
  });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('PageInspector', () => {
  it('renders when given a decision and closes on Escape', async () => {
    const onClose = vi.fn();
    render(<PageInspector decision={makeDecision()} onClose={onClose} />);

    // The inspector renders the stem as a mono header line. No body
    // preview — spec §7.3 is "two zones only".
    await waitFor(() => {
      expect(screen.getByText('hermes-zombie-session')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /copy path/i })).toBeInTheDocument();

    // Escape with no dirty state closes immediately (no confirm).
    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('dirty + ESC opens a confirm dialog before closing', async () => {
    const onClose = vi.fn();

    // Mock window.confirm so the test can assert it's the gate that
    // decides whether onClose fires. First call returns false (user
    // cancels) — onClose should NOT fire. Second call returns true.
    const confirmSpy = vi
      .spyOn(window, 'confirm')
      .mockReturnValueOnce(false)
      .mockReturnValueOnce(true);

    render(<PageInspector decision={makeDecision()} onClose={onClose} />);

    await waitFor(() => {
      expect(screen.getByText('hermes-zombie-session')).toBeInTheDocument();
    });

    // Dirty the editor.
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /review_status/i }));
    });
    const opt = await screen.findByRole('option', { name: /rejected/i });
    await act(async () => {
      fireEvent.click(opt);
    });

    // Esc #1: user cancels confirm → onClose should NOT fire.
    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(confirmSpy).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();

    // Esc #2: user confirms → onClose fires.
    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' });
    });
    expect(confirmSpy).toHaveBeenCalledTimes(2);
    expect(onClose).toHaveBeenCalledTimes(1);

    confirmSpy.mockRestore();
  });
});
