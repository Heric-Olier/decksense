import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  SliderField,
  staticClasses,
} from "@decky/ui";
import {
  debugHapticTest,
  getHapticParams,
  previewRumble,
  setHapticBalance,
  setHapticGain,
  stopRumble,
  type DebugInfo,
} from "../api";

const PREVIEW_INTENSITY = 0.5;

/**
 * Haptic Studio — gain + motor balance with live preview.
 */
export function GainPanel() {
  const [gain, setGain] = useState(1.0);
  const [balance, setBalance] = useState(0.5);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debug, setDebug] = useState<string | null>(null);
  const stopTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    void (async () => {
      const params = await getHapticParams();
      setGain(params.gain);
      setBalance(params.balance);
    })();
    return () => {
      if (stopTimeoutRef.current !== null) {
        window.clearTimeout(stopTimeoutRef.current);
      }
    };
  }, []);

  const onGainChange = async (value: number) => {
    setGain(value);
    setError(null);
    try {
      await setHapticGain(value);
    } catch (e) {
      setError(String(e));
    }
  };

  const onBalanceChange = async (value: number) => {
    setBalance(value);
    setError(null);
    try {
      await setHapticBalance(value);
    } catch (e) {
      setError(String(e));
    }
  };

  const onPreview = async () => {
    setError(null);
    const result = await previewRumble(PREVIEW_INTENSITY);
    if (result.state === "error") {
      setError(result.error ?? "unknown error");
      return;
    }
    setPreviewing(true);
    if (stopTimeoutRef.current !== null) {
      window.clearTimeout(stopTimeoutRef.current);
    }
    stopTimeoutRef.current = window.setTimeout(async () => {
      await onStop();
    }, 1200);
  };

  const onStop = async () => {
    if (stopTimeoutRef.current !== null) {
      window.clearTimeout(stopTimeoutRef.current);
      stopTimeoutRef.current = null;
    }
    await stopRumble();
    setPreviewing(false);
  };

  return (
    <PanelSection title="Haptic Studio">
      <PanelSectionRow>
        <SliderField
          label="Global gain"
          value={gain}
          min={0}
          max={2}
          step={0.05}
          onChange={onGainChange}
          description={`${gain.toFixed(2)}× multiplier`}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <SliderField
          label="Motor balance"
          value={balance}
          min={0}
          max={1}
          step={0.05}
          onChange={onBalanceChange}
          description={
            balance < 0.33
              ? "Light / buzzy"
              : balance > 0.66
                ? "Deep / heavy"
                : "Balanced"
          }
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={previewing ? onStop : onPreview}>
          {previewing
            ? "Stop preview"
            : `Preview at ${(PREVIEW_INTENSITY * gain).toFixed(2)} intensity`}
        </ButtonItem>
      </PanelSectionRow>
      {error && (
        <PanelSectionRow>
          <div className={staticClasses.Text} style={{ opacity: 0.6, padding: "0 8px" }}>
            {error}
          </div>
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={async () => {
            const r: DebugInfo = await debugHapticTest();
            setDebug(JSON.stringify(r, null, 2));
          }}
        >
          Run haptic debug
        </ButtonItem>
      </PanelSectionRow>
      {debug && (
        <PanelSectionRow>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              margin: 0,
              background: "rgba(255,255,255,0.05)",
              padding: "8px",
              borderRadius: "4px",
              fontSize: "0.8em",
            }}
          >
            {debug}
          </pre>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
