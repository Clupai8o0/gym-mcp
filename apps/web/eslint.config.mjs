import { defineConfig, globalIgnores } from "eslint/config";
import tempoNext from "@tempo/eslint-config/next";

const eslintConfig = defineConfig([
  ...tempoNext,
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);

export default eslintConfig;
