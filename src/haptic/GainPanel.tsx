import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  Focusable,
  PanelSection,
  PanelSectionRow,
  SliderField,
  staticClasses,
} from "@decky/ui";
import {
  debugHapticDump,
  getHapticBackendInfo,
  getHapticParams,
  listHapticBackends,
  previewRumble,
  setHapticBalance,
  setHapticGain,
  stopRumble,
  switchHapticBackend,
  type BackendInfo,
  type DebugInfo,
  type HapticDump,
  debugHapticTest,
} from "../api";
import { BackendCard } from "./BackendCard";
import { LuRadio, LuZap, LuShuffle } from "react-icons/lu";

const PREVIEW_INTENSITY = 0.5;

const BACKEND_ICONS: Record<string, React.ComponentType<{ size?: number }>> = {
  inputplumber: LuRadio,
  ff_gain: LuZap,
  uinput_proxy: LuShuffle,
};

const FEATURE_LABELS: Record<string, string> = {
  gain: "Preview gain",
  balance: "Preview balance",
  game_gain: "Game gain",
  game_balance: "Game balance",
};

export function GainPanel() {
  const [backends, setBackends] = useState<BackendInfo[]>([]);
  const [activeBackend, setActiveBackend] = useState<BackendInfo | null>(null);
  const [switching, setSwitching] = useState(false);

  const [gain, setGain] = useState(1.0);
  const [balance, setBalance] = useState(0.5);
  const [previewing, setPreviewing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debug, setDebug] = useState<string | null>(null);
  const [dumping, setDumping] = useState(false);
  const stopTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    void (async () => {
      const [bList, active, params] = await Promise.all([
        listHapticBackends(),
        getHapticBackendInfo(),
        getHapticParams(),
      ]);
      setBackends(bList);
      setActiveBackend(active);
      setGain(params.gain);
      setBalance(params.balance);
    })();
    return () => {
      if (stopTimeoutRef.current !== null) {
        window.clearTimeout(stopTimeoutRef.current);
      }
    };
  }, []);

  const hasFeature = (f: string) => activeBackend?.features.includes(f) ?? false;

  const onBackendSelect = async (id: string) => {
    if (id === activeBackend?.id || switching) return;
    setSwitching(true);
    setError(null);
    try {
      const info = await switchHapticBackend(id);
      setActiveBackend(info);
    } catch (e) {
      setError(String(e));
    } finally {
      setSwitching(false);
    }
  };

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
      {/* Backend chip selector */}
      <PanelSectionRow>
        <Focusable
          style={{
            display: "flex",
            gap: 6,
          }}
        >
          {backends.map((b) => {
            const Icon = BACKEND_ICONS[b.id] ?? LuRadio;
            return (
              <BackendCard
                key={b.id}
                backend={b}
                active={b.id === activeBackend?.id}
                onSelect={onBackendSelect}
                icon={Icon}
              />
            );
          })}
        </Focusable>
      </PanelSectionRow>

      {/* Description + feature badges */}
      {activeBackend && (
        <PanelSectionRow>
          <div
            style={{
              fontSize: "0.7em",
              lineHeight: 1.4,
              opacity: 0.65,
              padding: "2px 0 6px",
            }}
          >
            {activeBackend.description}
          </div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {activeBackend.features.map((f) => (
              <span
                key={f}
                style={{
                  fontSize: "0.6em",
                  padding: "1px 5px",
                  borderRadius: 3,
                  background: "rgba(255,255,255,0.08)",
                  opacity: 0.75,
                }}
              >
                {FEATURE_LABELS[f] ?? f}
              </span>
            ))}
          </div>
        </PanelSectionRow>
      )}

      {/* Gain slider */}
      <PanelSectionRow>
        <SliderField
          label="Gain"
          value={gain}
          min={0}
          max={2}
          step={0.05}
          onChange={onGainChange}
          description={`${gain.toFixed(2)}x`}
        />
      </PanelSectionRow>

      {/* Balance slider (only when supported) */}
      {hasFeature("balance") && (
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
                ? "Light"
                : balance > 0.66
                  ? "Heavy"
                  : "Balanced"
            }
          />
        </PanelSectionRow>
      )}

      {/* Preview */}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={previewing ? onStop : onPreview}>
          {previewing
            ? "Stop preview"
            : `Preview at ${(PREVIEW_INTENSITY * gain).toFixed(2)}`}
        </ButtonItem>
      </PanelSectionRow>

      {error && (
        <PanelSectionRow>
          <div
            className={staticClasses.Text}
            style={{ opacity: 0.6, padding: "0 8px" }}
          >
            {error}
          </div>
        </PanelSectionRow>
      )}

      {/* FF_GAIN test — only shown when the backend supports game_gain */}
      {hasFeature("game_gain") && (
        <PanelSectionRow>
          <div style={{ display: "flex", gap: 6 }}>
            <div style={{ flex: 1 }}>
              <ButtonItem
                layout="below"
                onClick={async () => {
                  await setHapticGain(0);
                  setGain(0);
                }}
              >
                Gain 0 (mute)
              </ButtonItem>
            </div>
            <div style={{ flex: 1 }}>
              <ButtonItem
                layout="below"
                onClick={async () => {
                  await setHapticGain(1);
                  setGain(1);
                }}
              >
                Gain 1 (full)
              </ButtonItem>
            </div>
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
          Haptic test
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={dumping}
          onClick={async () => {
            setDumping(true);
            try {
              const r: HapticDump = await debugHapticDump();
              setDebug(JSON.stringify(r, null, 2));
            } finally {
              setDumping(false);
            }
          }}
        >
          {dumping ? "Dumping..." : "Export debug log"}
        </ButtonItem>
      </PanelSectionRow>
      {debug && (
        <PanelSectionRow>
          <pre
            style={{
              whiteSpace: "pre-wrap",
              margin: 0,
              background: "rgba(255,255,255,0.05)",
              padding: 8,
              borderRadius: 4,
              fontSize: "0.8em",
              maxHeight: 200,
              overflow: "auto",
            }}
          >
            {debug}
          </pre>
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
