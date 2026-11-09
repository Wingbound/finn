import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  // Fixture checks read untyped JSON on purpose.
  { files: ["tests/**", "e2e/**"], rules: { "@typescript-eslint/no-explicit-any": "off" } },
  { rules: { "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }] } },
  globalIgnores([".next/**", "node_modules/**", "playwright-report/**", "test-results/**", "next-env.d.ts"]),
]);
