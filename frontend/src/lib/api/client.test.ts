import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";
import { ApiError } from "./errors";

afterEach(() => vi.restoreAllMocks());

describe("local API client", () => {
  it("validates successful health responses at the boundary", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            status: "waiting_for_controller",
            process_alive: true,
            controller_available: false,
            subsystems: { core: "ready" },
            degraded: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(api.health()).resolves.toMatchObject({ status: "waiting_for_controller" });
  });

  it("preserves structured server validation errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: "api.validation",
              message: "The request payload is invalid.",
              detail: null,
              recoverable: true,
              fields: { "rumble.gate": "must be between 0 and 1" },
            },
          }),
          { status: 422, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    const result = api.updateConfig({ rumble: { gate: 2 } });
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({
      code: "api.validation",
      fields: { "rumble.gate": "must be between 0 and 1" },
    });
  });
});
