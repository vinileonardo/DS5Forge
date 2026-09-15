import type { z } from "zod";

import type { ErrorSnapshotSchema } from "./contracts";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail: string | null;
  readonly recoverable: boolean;
  readonly fields: Record<string, unknown>;

  constructor(status: number, payload: z.infer<typeof ErrorSnapshotSchema>) {
    super(payload.message);
    this.name = "ApiError";
    this.status = status;
    this.code = payload.code;
    this.detail = payload.detail;
    this.recoverable = payload.recoverable;
    this.fields = payload.fields;
  }
}

export class ApiProtocolError extends Error {
  constructor(
    message: string,
    public readonly cause?: unknown,
  ) {
    super(message);
    this.name = "ApiProtocolError";
  }
}

export function fieldErrorMap(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError)) return {};
  return Object.fromEntries(
    Object.entries(error.fields).map(([key, value]) => [
      key,
      typeof value === "string" ? value : JSON.stringify(value),
    ]),
  );
}

export function errorMessage(error: unknown, fallback = "The request could not be completed."): string {
  if (error instanceof ApiError || error instanceof ApiProtocolError) return error.message;
  if (error instanceof Error) return error.message;
  return fallback;
}

export function isNetworkError(error: unknown): boolean {
  return error instanceof TypeError || (error instanceof Error && error.name === "AbortError");
}
