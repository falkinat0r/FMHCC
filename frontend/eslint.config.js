import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// R1: Flat Config (ESLint 9) mit TypeScript-Parser (typescript-eslint, R1/QA-
// Befund: ohne TS-Parser war der Lint-Gate fuer .ts/.tsx nicht verlaesslich).
// src/api/generated ist generiert (openapi-typescript) und wird nicht gelintet.
export default [
  { ignores: ["dist", "node_modules", "src/api/generated"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: {
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  {
    // Tests duerfen Vitest-Globalen nutzen (globals: true in vite.config)
    files: ["**/*.test.{ts,tsx}", "vitest.setup.ts"],
    languageOptions: {
      globals: {
        ...globals.jest,
        // Vitest-Global
        vi: "readonly",
      },
    },
  },
];
