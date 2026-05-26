// Coverage for FrontmatterEditor. Spec §9.2: 5 tests.
//   1. dropdown change → dirty flag
//   2. type change → invalid-category warning + Save disabled
//   3. tag chip add (Enter) + remove (× click)
//   4. lint error inline + form state preserved
//   5. PATCH body: only changed fields + tags full replacement

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FrontmatterEditor } from '../FrontmatterEditor';
import type { Decision } from '../../types';

function makeDecision(overrides: Partial<Decision> = {}): Decision {
  return {
    stem: 'hermes-zombie-session',
    path: 'wiki/entities/hermes/2026-05/hermes-zombie-session.md',
    type: 'entity',
    category: 'system-ops',
    tags: ['hermes', 'zombie'],
    review_status: 'approved',
    sources: ['github.com/owner/repo#1'],
    captured_at: '2026-05-01T12:00:00+09:00',
    last_edited_at: '2026-05-26T14:23:00+09:00',
    dispatch_summary: null,
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
  // /api/enums/categories load on mount returns an empty list by
  // default; individual tests may override.
  fetchMock.mockResolvedValue(mockResponse({ body: { categories: [] } }));
});

afterEach(() => {
  vi.useRealTimers();
});

describe('FrontmatterEditor', () => {
  it('dropdown change sets the dirty flag (· middot indicator visible)', async () => {
    render(<FrontmatterEditor decision={makeDecision()} onSaved={vi.fn()} />);

    // Save is rendered without the dirty marker initially.
    const saveBefore = await screen.findByRole('button', { name: /^save/i });
    expect(saveBefore.textContent ?? '').not.toMatch(/·/);

    // Open review_status dropdown and pick "rejected".
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /review_status/i }));
    });
    const opt = await screen.findByRole('option', { name: /rejected/i });
    await act(async () => {
      fireEvent.click(opt);
    });

    // Now the save row carries the leading mono middot.
    const saveAfter = screen.getByRole('button', { name: /^·\s*save/i });
    expect(saveAfter).toBeInTheDocument();
  });

  it('type change to a directory-incompatible value warns and disables Save', async () => {
    // entity lives in entities/; switching to "concept" requires a
    // file rename → spec §7.3 inline warning + Save disabled.
    render(<FrontmatterEditor decision={makeDecision()} onSaved={vi.fn()} />);

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^type$/i }));
    });
    const opt = await screen.findByRole('option', { name: /concept/i });
    await act(async () => {
      fireEvent.click(opt);
    });

    expect(screen.getByText(/type change requires manual rename/i)).toBeInTheDocument();
    const save = screen.getByRole('button', { name: /save/i });
    expect(save).toBeDisabled();
  });

  it('adds a chip on Enter and removes it via the × button', async () => {
    const user = userEvent.setup();
    render(
      <FrontmatterEditor decision={makeDecision({ tags: [] })} onSaved={vi.fn()} />,
    );

    const input = screen.getByLabelText(/add tag/i);
    await user.type(input, 'daemon');
    await user.keyboard('{Enter}');
    expect(screen.getByText('daemon')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /remove tag daemon/i }));
    expect(screen.queryByText('daemon')).not.toBeInTheDocument();
  });

  it('renders lint errors inline and preserves form state', async () => {
    const onSaved = vi.fn();
    render(<FrontmatterEditor decision={makeDecision()} onSaved={onSaved} />);

    // Dirty the form (review_status -> rejected).
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /review_status/i }));
    });
    const opt = await screen.findByRole('option', { name: /rejected/i });
    await act(async () => {
      fireEvent.click(opt);
    });

    // Next fetch is the PATCH; mock a 409 lint failure.
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        status: 409,
        body: {
          detail: 'kb-lint-wiki failed',
          lint_errors: ['frontmatter:review_status: invalid transition'],
        },
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /save/i }));
    });

    await waitFor(() => {
      expect(
        screen.getByText(/frontmatter:review_status: invalid transition/i),
      ).toBeInTheDocument();
    });

    // Form state: the dirty middot is still on the save button.
    expect(screen.getByRole('button', { name: /^·\s*save/i })).toBeInTheDocument();
    // onSaved was not called (server rejected the candidate).
    expect(onSaved).not.toHaveBeenCalled();
  });

  it('PATCH body contains only changed fields; tags is full replacement', async () => {
    const user = userEvent.setup();
    render(
      <FrontmatterEditor
        decision={makeDecision({ tags: ['hermes'] })}
        onSaved={vi.fn()}
      />,
    );

    // Change tags only (add "daemon"). type, category, review_status
    // stay equal to the loaded values and must NOT appear in the PATCH.
    const tagInput = screen.getByLabelText(/add tag/i);
    await user.type(tagInput, 'daemon');
    await user.keyboard('{Enter}');

    // Next fetch is the PATCH; mock a 200.
    fetchMock.mockResolvedValueOnce(
      mockResponse({
        body: {
          stem: 'hermes-zombie-session',
          frontmatter: {},
          edits: [{ field: 'tags', edited_at: '2026-05-26T15:00:00+09:00' }],
        },
      }),
    );

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /save/i }));
    });

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const lastCall = fetchMock.mock.calls[1];
    expect(lastCall?.[0]).toBe('/api/pages/hermes-zombie-session/frontmatter');
    const bodyText = (lastCall?.[1] as { body: string }).body;
    const parsed = JSON.parse(bodyText);
    // Only `tags` key — review_status / type / category were unchanged
    // and must be absent (merge-patch semantics).
    expect(Object.keys(parsed)).toEqual(['tags']);
    // Full replacement: the entire new array, not a delta.
    expect(parsed.tags).toEqual(['hermes', 'daemon']);
  });
});
