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

// --- Haptic backend management ----------------------------------------

export interface BackendInfo {
  id: string;
  name: string;
  description: string;
  features: string[];
}

export const listHapticBackends = callable<[], BackendInfo[]>(
  "list_haptic_backends"
);
export const getHapticBackendInfo = callable<[], BackendInfo>(
  "get_haptic_backend_info"
);
export const switchHapticBackend = callable<[backendId: string], BackendInfo>(
  "switch_haptic_backend"
);

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

export interface EvdevDeviceInfo {
  path: string;
  name: string;
  vendor: string;
  has_ff: boolean;
}

export interface HapticDump {
  version: string;
  backend: BackendInfo;
  params: { gain: number; balance: number };
  backends: BackendInfo[];
  devices: EvdevDeviceInfo[];
  pid: number;
  uid: number;
}

export const debugHapticDump = callable<[], HapticDump>("debug_haptic_dump");
