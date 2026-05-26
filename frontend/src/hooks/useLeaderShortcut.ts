// "g <letter>" leader-key navigation, Linear-style. Spec §7.4 calls
// out g p / g d / g a for Pending / Decisions / Dashboard.
//
// Behaviour: press `g`, then any of the registered letters within
// `timeoutMs` (200-300 ms per spec). The second keypress invokes the
// matching handler. While inside an input/textarea/contenteditable
// the leader is ignored — keyboard nav must never steal typing.

import { useEffect, useRef } from 'react';

export type LeaderMap = Record<string, () => void>;

export function useLeaderShortcut(map: LeaderMap, timeoutMs = 250) {
  // Stash the latest map in a ref so we don't re-bind the listener on
  // every render. The values are functions consumers may recreate
  // each render; useCallback discipline is not assumed.
  const mapRef = useRef(map);
  mapRef.current = map;

  useEffect(() => {
    let armed = false;
    let armedAt = 0;

    const isEditable = (t: EventTarget | null): boolean => {
      if (!(t instanceof HTMLElement)) return false;
      return t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable;
    };

    const handler = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (isEditable(e.target)) return;

      if (armed) {
        const fresh = Date.now() - armedAt <= timeoutMs;
        armed = false;
        if (!fresh) return;
        const fn = mapRef.current[e.key];
        if (fn) {
          e.preventDefault();
          fn();
        }
        return;
      }

      if (e.key === 'g') {
        armed = true;
        armedAt = Date.now();
      }
    };

    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [timeoutMs]);
}
