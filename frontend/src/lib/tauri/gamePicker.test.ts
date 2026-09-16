import { afterEach, describe, expect, it, vi } from "vitest";

import { executableName, pickExecutable } from "./gamePicker";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("browser executable picker fallback", () => {
  it("stores only the executable identity when the browser cannot provide a path", async () => {
    const input = {
      type: "",
      accept: "",
      files: [{ name: "candidate.exe" }] as unknown as FileList,
      onchange: null as null | (() => void),
      click: vi.fn(() => input.onchange?.()),
    };
    vi.spyOn(document, "createElement").mockReturnValue(input as unknown as HTMLElement);

    const picked = await pickExecutable();

    expect(picked).toEqual({ name: "candidate.exe", path: null });
  });

  it("never treats a basename as an absolute path", () => {
    expect(executableName("C:\\Games\\candidate.exe")).toBe("candidate.exe");
    expect(executableName("/opt/games/candidate.exe")).toBe("candidate.exe");
  });
});
