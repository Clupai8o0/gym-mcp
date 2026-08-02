import { defineConfig, globalIgnores } from "eslint/config";
import tempoNext from "@tempo/eslint-config/next";

const eslintConfig = defineConfig([
  ...tempoNext,
  {
    rules: {
      /*
       * Two barrels are deliberately absent — deleted, not overlooked. Each bundled a heavy
       * component with light ones, and a barrel import pulls the whole group into the route's
       * client bundle:
       *
       *   @/components/log       — `SessionLogger` carries the `motion` runtime (~42 KB gz),
       *                            which rode onto `/dashboard` and `/log`, neither of which
       *                            animates anything.
       *   @/components/dashboard — `PrList` → `IllustrationImage` carries the `next/image`
       *                            cluster onto `/progress/volume` and `/progress/frequency`.
       *
       * Import the component you actually use. The rule (rather than just the missing file)
       * is what stops someone re-adding an `index.ts` and quietly undoing it. Barrels
       * elsewhere — `@/components/ui`, `@/components/home` — are fine: uniformly light members.
       */
      "no-restricted-imports": [
        "error",
        {
          paths: [
            {
              name: "@/components/log",
              message:
                "Import the component directly (e.g. @/components/log/SessionStarter) — the barrel pulls the motion runtime onto routes that never animate.",
            },
            {
              name: "@/components/dashboard",
              message:
                "Import the component directly (e.g. @/components/dashboard/VolumeChart) — the barrel pulls the next/image cluster onto chart-only routes.",
            },
          ],
        },
      ],
    },
  },
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "lib/api-types.ts", // generated from the FastAPI OpenAPI schema (see `gen:api`)
  ]),
]);

export default eslintConfig;
