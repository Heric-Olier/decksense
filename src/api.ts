import { callable } from "@decky/api";

export type UpdateState =
  | "idle"
  | "checking"
  | "available"
  | "up_to_date"
  | "installing"
  | "done"
  | "error"
  | "restarting";

export interface UpdateStatus {
  state: UpdateState;
  current_version: string;
  latest_version?: string | null;
  release_notes?: string | null;
  asset_url?: string | null;
  error?: string | null;
}

export interface RestartResult {
  state: string;
  error?: string;
}

export const checkForUpdate = callable<[force: boolean], UpdateStatus>(
  "check_for_update"
);
export const installUpdate = callable<[], UpdateStatus>("install_update");
export const restartLoader = callable<[], RestartResult>("restart_loader");
export const getCurrentVersion = callable<[], string>("get_current_version");

// --- Haptic ---

export interface HapticParams {
  gain: number;
  balance: number;
}

export interface PreviewResult {
  state: "playing" | "stopped" | "error";
  intensity?: number;
  gain?: number;
  balance?: number;
  error?: string;
}

export const getHapticParams = callable<[], HapticParams>("get_haptic_params");
export const setHapticGain = callable<[value: number], HapticParams>(
  "set_haptic_gain"
);
export const setHapticBalance = callable<[value: number], HapticParams>(
  "set_haptic_balance"
);
export const previewRumble = callable<[rawIntensity: number], PreviewResult>(
  "preview_rumble"
);
export const stopRumble = callable<[], PreviewResult>("stop_rumble");

// --- Debug ---

export interface DebugInfo {
  pid: number;
  uid: number;
  gid: number;
  env_keys: string[];
  state: "ok" | "error";
  error?: string;
}

export const debugHapticTest = callable<[], DebugInfo>("debug_haptic_test");
