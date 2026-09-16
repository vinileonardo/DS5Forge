import { describe, expect, it, vi } from "vitest";

import { dictionaries, LOCALE_STORAGE_KEY, persistLocale, readLocale, translate } from "./index";

describe("typed i18n", () => {
  it("keeps pt-BR and en-US key parity", () => {
    expect(Object.keys(dictionaries["pt-BR"]).sort()).toEqual(Object.keys(dictionaries["en-US"]).sort());
  });

  it("persists the selected locale when storage is available", () => {
    localStorage.clear();
    persistLocale("pt-BR");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("pt-BR");
    expect(readLocale()).toBe("pt-BR");
    expect(translate("pt-BR", "nav.games")).toBe("Jogos");
  });

  it("falls back safely when offline storage is unavailable", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("storage unavailable");
    });
    expect(readLocale()).toBe("en-US");
    getItem.mockRestore();
  });
});
