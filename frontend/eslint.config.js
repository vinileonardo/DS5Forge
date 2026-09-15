import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  {
    ignores: ["dist", "node_modules", "src-tauri/target", "playwright-report", "test-results"],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/consistent-type-imports": ["error", { prefer: "type-imports" }],
    },
  },
  {
    files: ["**/*.{js,mjs,cjs}"],
    rules: {
      "@typescript-eslint/no-unsafe-assignment": "off",
    },
  },
);
