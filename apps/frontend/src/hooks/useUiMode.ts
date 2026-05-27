import { useEffect, useState } from "react";
import { getCurrentUiMode, type UiMode } from "../mode";

export function useUiMode() {
  const [uiMode, setUiMode] = useState<UiMode>(getCurrentUiMode());

  useEffect(() => {
    const sync = () => setUiMode(getCurrentUiMode());
    window.addEventListener("quantgrid-ui-mode-change", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("quantgrid-ui-mode-change", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return uiMode;
}
