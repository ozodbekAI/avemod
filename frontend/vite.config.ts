// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, cloudflare (build-only),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... } }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

function vendorChunk(id: string): string | undefined {
  if (!id.includes("/node_modules/")) return undefined;
  if (
    id.includes("/node_modules/react/") ||
    id.includes("/node_modules/react-dom/") ||
    id.includes("/node_modules/scheduler/")
  ) {
    return "vendor-react";
  }
  if (
    id.includes("/node_modules/@radix-ui/") ||
    id.includes("/node_modules/@floating-ui/") ||
    id.includes("/node_modules/@floating-ui-react-dom/") ||
    id.includes("/node_modules/@floating-ui-react-dom-interactions/") ||
    id.includes("/node_modules/@react-aria/") ||
    id.includes("/node_modules/@react-stately/") ||
    id.includes("/node_modules/cmdk/") ||
    id.includes("/node_modules/vaul/") ||
    id.includes("/node_modules/react-remove-scroll") ||
    id.includes("/node_modules/react-style-singleton") ||
    id.includes("/node_modules/aria-hidden/")
  ) {
    return "vendor-ui";
  }
  if (
    id.includes("/node_modules/lucide-react/") ||
    id.includes("/node_modules/lucide/")
  ) {
    return "vendor-icons";
  }
  if (
    id.includes("/node_modules/recharts/") ||
    id.includes("/node_modules/d3-") ||
    id.includes("/node_modules/victory-vendor/")
  ) {
    return "vendor-charts";
  }
  if (
    id.includes("/node_modules/react-hook-form/") ||
    id.includes("/node_modules/@hookform/") ||
    id.includes("/node_modules/zod/")
  ) {
    return "vendor-forms";
  }
  if (
    id.includes("/node_modules/date-fns/") ||
    id.includes("/node_modules/react-day-picker/")
  ) {
    return "vendor-date";
  }
  return undefined;
}

// Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
// @cloudflare/vite-plugin builds from this — wrangler.jsonc main alone is insufficient.
export default defineConfig({
  tanstackStart: {
    server: { entry: "server" },
  },
  vite: {
    build: {
      rollupOptions: {
        output: {
          manualChunks: vendorChunk,
        },
      },
    },
  },
});
