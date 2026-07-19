import { useCallback, useEffect, useState } from "react";
import {
  checkForUpdate,
  installUpdate,
  restartLoader,
  UpdateStatus,
} from "../api";

const INITIAL: UpdateStatus = { state: "idle", current_version: "" };

export function useUpdate() {
  const [status, setStatus] = useState<UpdateStatus>(INITIAL);

  const check = useCallback(async (force = false) => {
    setStatus((prev) => ({ ...prev, state: "checking" }));
    const result = await checkForUpdate(force);
    setStatus(result);
  }, []);

  const install = useCallback(async () => {
    setStatus((prev) => ({ ...prev, state: "installing" }));
    const result = await installUpdate();
    setStatus(result);
  }, []);

  const restart = useCallback(async () => {
    await restartLoader();
    setStatus((prev) => ({ ...prev, state: "restarting" }));
  }, []);

  // Auto-check on mount. The backend caches results per session,
  // so duplicate calls from multiple consumers only hit GitHub once.
  useEffect(() => {
    void check(false);
  }, [check]);

  return { status, check, install, restart };
}
