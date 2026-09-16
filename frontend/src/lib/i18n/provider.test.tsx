import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { I18nProvider, LOCALE_STORAGE_KEY, useI18n } from "./index";

function ShellConsumer() {
  const { t } = useI18n();
  return <span data-testid="shell">{t("nav.games")}</span>;
}

function PageConsumer() {
  const { t } = useI18n();
  return <span data-testid="page">{t("games.exclusiveToggle")}</span>;
}

function LocaleSwitcher() {
  const { locale, setLocale } = useI18n();
  return (
    <button type="button" onClick={() => setLocale(locale === "en-US" ? "pt-BR" : "en-US")}>
      switch
    </button>
  );
}

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("app-global i18n provider", () => {
  it("updates mounted shell and active page consumers from one locale switch", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en-US");
    render(
      <I18nProvider>
        <ShellConsumer />
        <PageConsumer />
        <LocaleSwitcher />
      </I18nProvider>,
    );

    expect(screen.getByTestId("shell")).toHaveTextContent("Games");
    expect(screen.getByTestId("page")).toHaveTextContent("Exclusive input mode");

    fireEvent.click(screen.getByRole("button", { name: "switch" }));

    expect(screen.getByTestId("shell")).toHaveTextContent("Jogos");
    expect(screen.getByTestId("page")).toHaveTextContent("Modo de entrada exclusivo");
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe("pt-BR");
  });

  it("keeps pt-BR product copy free of awkward English leftovers", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "pt-BR");
    render(
      <I18nProvider>
        <PageConsumer />
      </I18nProvider>,
    );
    const text = screen.getByTestId("page").textContent ?? "";
    expect(text).not.toMatch(/Exclusive|provider|provenance/i);
  });
});
