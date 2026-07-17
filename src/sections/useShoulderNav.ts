import { useEffect, useRef } from "react";
import { cycleTab } from "./nav";

interface Options {
  ids: string[];
  active: string;
  onSelect: (id: string) => void;
}

// Per Steam Input: 30 = LSHOULDER (L1), 31 = RSHOULDER (R1).
const LSHOULDER = 30;
const RSHOULDER = 31;

/**
 * L1/R1 (SteamOS bumpers — "shoulders") to cycle tabs.
 *
 * The listener is registered once on mount. Refs keep `ids`, `active`
 * and `onSelect` fresh inside the callback without re-registering.
 *
 * Degrades silently when `SteamClient.Input.RegisterForControllerInputMessages`
 * is unavailable (non-Steam runtime, future API change, etc.).
 *
 * Callback signature: `(idx, button, pressed)` — three positional args,
 * not an object. Pattern lifted from Panel de Control.
 */
export function useShoulderNav({ ids, active, onSelect }: Options) {
  const idsRef = useRef(ids);
  const activeRef = useRef(active);
  const onSelectRef = useRef(onSelect);

  idsRef.current = ids;
  activeRef.current = active;
  onSelectRef.current = onSelect;

  useEffect(() => {
    let reg: { unregister?: () => void } | null = null;
    try {
      const input = (SteamClient as any)?.Input;
      if (!input || typeof input.RegisterForControllerInputMessages !== "function") {
        return;
      }
      reg = input.RegisterForControllerInputMessages(
        (_idx: number, button: number, pressed: boolean) => {
          if (!pressed) return;
          if (button !== LSHOULDER && button !== RSHOULDER) return;
          const direction = button === RSHOULDER ? 1 : -1;
          const next = cycleTab(idsRef.current, activeRef.current, direction);
          if (next !== activeRef.current) {
            onSelectRef.current(next);
          }
        }
      );
    } catch {
      // Input API unavailable; degrade silently.
    }

    return () => {
      try {
        reg?.unregister?.();
      } catch {
        // ignore
      }
    };
  }, []);
}
