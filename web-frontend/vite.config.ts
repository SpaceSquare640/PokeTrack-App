import { defineConfig } from "vite";
import { resolve } from "node:path";

// Build a single, stably-named ES-module bundle straight into Flask's static
// dir. The compiled output IS committed, so running the app needs no Node — the
// TypeScript toolchain is only required to rebuild. base.html loads it as
// <script type="module" src=".../dist/app.js">.
export default defineConfig({
  build: {
    outDir: resolve(__dirname, "../poketrack/web/static/dist"),
    emptyOutDir: true,
    target: "es2020",
    lib: {
      entry: resolve(__dirname, "src/main.ts"),
      formats: ["es"],
      fileName: () => "app.js",
    },
  },
});
