// Coverage for EditTimeline. Spec §9.2: 1 test — verify the
// arrow-anchored row format `{timestamp} {field}: {old} → {new}` for
// audit-driven rows. Dispatch/status rows have a separate kind.

import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import { EditTimeline } from '../EditTimeline';
import type { TimelineEvent } from '../../types';

describe('EditTimeline', () => {
  it('renders an edit row as `field: old → new`', () => {
    const events: TimelineEvent[] = [
      {
        kind: 'edit',
        at: '2026-05-26T14:23:00+09:00',
        field: 'review_status',
        old_value: 'pending_for_approve',
        new_value: 'approved',
        source: 'console',
      },
    ];

    const { container } = render(<EditTimeline events={events} total={1} />);

    // The row body must contain the arrow-anchored old → new string.
    // textContent flattens nested spans (timestamp · field · old → new).
    const row = container.querySelector('li');
    expect(row).not.toBeNull();
    const flat = (row?.textContent ?? '').replace(/\s+/g, ' ').trim();
    expect(flat).toMatch(/review_status:\s*pending_for_approve\s*→\s*approved/);
  });
});
