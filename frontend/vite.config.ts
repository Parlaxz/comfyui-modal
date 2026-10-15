import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

// Modal Studio Vue substrate — production output strategy.
//
// ComfyUI's extension discovery (server.py `get_extensions`) serves every
// `**/*.js` file under each custom node's WEB_DIRECTORY as an
// auto-executed frontend extension. A normal Vite app build emits `.js`
// chunks, so dropping it directly under `web/` would make every chunk run
// as an independent ComfyUI extension (duplicate registration, crashes).
//
// The `.js` glob does NOT match `.mjs`, so this build emits:
//
//   web/assets/studio/studio.mjs   — one stable entry (no content hash)
//   web/assets/studio/chunks/*.mjs — code-split chunks (hashed, safe)
//   web/assets/studio/studio.css   — scoped stylesheet (no .js, safe)
//
// The ComfyUI host entry (web/studio-vue-host.js, a normal auto-loaded
// extension module) dynamically imports the stable `studio.mjs` entry.
// No dev server is required; asset URLs resolve relative to the host
// module under `/extensions/comfyui-modal/…`.
export default defineConfig({
  plugins: [vue(), tailwindcss()],
  base: "./",
  // Browser bundle: no `process` exists in ComfyUI. Replace the standard
  // NODE_ENV checks at build time (also drops dev-only branches).
  define: {
    "process.env.NODE_ENV": JSON.stringify("production"),
  },
  build: {
    // Library mode: the entry's exports (mountStudioPreview) are the
    // public interface dynamically imported by web/studio-vue-host.js.
    // A plain app build tree-shakes entry exports away.
    lib: {
      entry: fileURLToPath(new URL("./src/studio.ts", import.meta.url)),
      formats: ["es"],
      fileName: () => "studio.mjs",
    },
    outDir: "../web/assets/studio",
    emptyOutDir: true,
    target: "es2022",
    cssCodeSplit: false,
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        chunkFileNames: "chunks/[name]-[hash].mjs",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".css")) return "studio.css";
          return "assets/[name]-[hash][extname]";
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
