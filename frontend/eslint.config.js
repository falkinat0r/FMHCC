import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";

// R0-Grundgeruest (Flat Config, ESLint 9). Agent 2 baut aus.
export default [
  { ignores: ["dist", "node_modules", "src/api/generated"] },
  js.configs.recommended,
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
    files: ["**/*.test.{ts,tsx}"],
    languageOptions: {
      globals: globals.jest,
    },
  },
];
