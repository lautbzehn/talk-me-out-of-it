// Copies the curated gallery (sessions/gallery/*.json) into public/gallery/ so the
// dev server and the static build can serve it. The engine's files stay the source of
// truth; public/gallery/ is a build output and is ignored by git.
import { cpSync, mkdirSync, readdirSync, rmSync, statSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "..", "..", "sessions", "gallery");
const target = resolve(here, "..", "public", "gallery");

let files;
try {
  files = readdirSync(source).filter((name) => name.endsWith(".json"));
} catch (error) {
  console.error(`sync-gallery: cannot read ${source}: ${error.message}`);
  process.exit(1);
}
if (!files.includes("index.json")) {
  console.error(`sync-gallery: ${source} has no index.json`);
  process.exit(1);
}

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
let bytes = 0;
for (const name of files) {
  cpSync(join(source, name), join(target, name));
  bytes += statSync(join(target, name)).size;
}
console.log(`sync-gallery: copied ${files.length} files (${Math.round(bytes / 1024)} KB) to public/gallery/`);
