/** Focus ring styles — inspired by Panel de Control.
 *
 * Steam stamps ``gpfocus`` on the ``Focusable`` element that currently
 * holds gamepad focus.  We inject a stylesheet that makes that ring
 * visible with an accent-coloured glow.
 */

const FOCUS_STYLE_ID = "deckysense-focus-styles";

export function buildFocusCss(): string {
  return `
.gpfocus {
  border-radius: 8px !important;
  box-shadow: 0 0 0 2px rgba(0,0,0,0.6),
              0 0 0 4px rgba(255,255,255,0.6),
              0 0 12px 3px rgba(255,255,255,0.25) !important;
  filter: brightness(1.08);
  transition: box-shadow 120ms ease, filter 120ms ease;
  position: relative;
  z-index: 1;
}`;
}

export function ensureFocusStyles(): void {
  try {
    if (document.getElementById(FOCUS_STYLE_ID)) return;
    const el = document.createElement("style");
    el.id = FOCUS_STYLE_ID;
    el.textContent = buildFocusCss();
    document.head.appendChild(el);
  } catch {
    /* best-effort */
  }
}
