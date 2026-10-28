import { useEffect, useRef } from 'react';

/**
 * Calls `fn` now and then every `interval` ms while `active` is true.
 * Skips ticks while the browser tab is hidden, and never overlaps calls.
 */
export default function usePolling(fn, interval, active = true) {
  const saved = useRef(fn);
  saved.current = fn;

  useEffect(() => {
    if (!active) return undefined;
    let stopped = false;
    let busy = false;
    let timer;
    const tick = async () => {
      if (stopped) return;
      if (!busy && !document.hidden) {
        busy = true;
        try {
          await saved.current();
        } catch {
          /* the caller shows its own errors */
        } finally {
          busy = false;
        }
      }
      timer = setTimeout(tick, interval);
    };
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [interval, active]);
}
