export interface PickedExecutable {
  /** Executable file name used as the matching identity. */
  name: string;
  /**
   * Verified absolute path. The browser preview cannot provide one, so it is
   * stored as `null` and only the executable identity is persisted.
   */
  path: string | null;
}

function isTauriShell(): boolean {
  return (
    typeof window !== "undefined" &&
    (window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost")
  );
}

export function executableName(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

/** Use the packaged shell's native picker; browser preview keeps a safe file-input fallback. */
export async function pickExecutable(): Promise<PickedExecutable | null> {
  if (isTauriShell()) {
    const { invoke } = await import("@tauri-apps/api/core");
    const path = await invoke<string | null>("pick_executable");
    if (!path) return null;
    return { name: executableName(path), path };
  }
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".exe,application/vnd.microsoft.portable-executable";
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) {
        resolve(null);
        return;
      }
      // A browser file input deliberately does not expose a trustworthy
      // absolute path, so only the executable identity is stored.
      resolve({ name: file.name, path: null });
    };
    input.click();
  });
}
