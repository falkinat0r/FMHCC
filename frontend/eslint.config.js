import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

// R0-Grundgeruest (Flat Config, ESLint 9). Agent 2 baut aus.
// R1 (QA): typescript-eslint ergaenzt — zuvor wurden .ts/.tsx-Dateien ohne
// TS-Parser gelintet (Parsing-Fehler) bzw. still uebersprungen, der
// Lint-Gate war dadurch nicht verlaesslich.
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
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  {
    // Tests duerfen Vitest-Globalen nutzen
    files: ["**/*.test.{ts,tsx}", "vitest.setup.ts"],
    languageOptions: {
      globals: globals.jest,
    },
  },
];
