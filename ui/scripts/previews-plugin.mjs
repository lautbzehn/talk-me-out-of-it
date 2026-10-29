// A Vite plugin for the dev server only: lets the export page (export.html) save the preview
// images straight into public/previews/. `configureServer` runs for `npm run dev` and never for
// `npm run build`, so none of this ships.
//
// A page that can write files on your computer deserves care, so the endpoint is narrow:
//   - POST only, to /__previews/<name>, where <name> is "home" or the id of a session in the
//     gallery index. Nothing else can be named, so nothing outside public/previews/ is reachable.
//   - The request must carry a custom header. A web page on another site cannot send one to your
//     localhost without a permission check (a "preflight") that this server's default settings
//     refuse, so only the export page can use the endpoint.
//   - The body must be a PNG (checked by its first eight bytes) and at most 4 MB.
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const publicDir = resolve(here, "..", "public");
const MAX_BYTES = 4 * 1024 * 1024;
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

function allowedNames() {
  const names = new Set(["home"]);
  const index = JSON.parse(readFileSync(join(publicDir, "gallery", "index.json"), "utf8"));
  for (const session of index.sessions ?? []) if (typeof session.id === "string") names.add(session.id);
  return names;
}

export function previewExport() {
  return {
    name: "preview-export",
    apply: "serve",
    configureServer(server) {
      server.middlewares.use("/__previews", (req, res) => {
        const reply = (status, message) => {
          res.statusCode = status;
          res.setHeader("Content-Type", "text/plain");
          res.end(message);
        };
        if (req.method !== "POST") return reply(405, "POST only");
        if (req.headers["x-preview-export"] !== "1") return reply(403, "missing header");
        const name = decodeURIComponent((req.url ?? "").replace(/^\//, ""));
        let allowed;
        try {
          allowed = allowedNames();
        } catch {
          return reply(500, "cannot read public/gallery/index.json; run npm run sync first");
        }
        if (!allowed.has(name)) return reply(400, `unknown preview name ${JSON.stringify(name)}`);

        const chunks = [];
        let size = 0;
        req.on("data", (chunk) => {
          size += chunk.length;
          if (size > MAX_BYTES) {
            reply(413, "too large");
            req.destroy();
            return;
          }
          chunks.push(chunk);
        });
        req.on("end", () => {
          if (res.writableEnded) return;
          const body = Buffer.concat(chunks);
          if (body.length < PNG_SIGNATURE.length || !body.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)) {
            return reply(400, "not a PNG");
          }
          mkdirSync(join(publicDir, "previews"), { recursive: true });
          writeFileSync(join(publicDir, "previews", `${name}.png`), body);
          reply(200, `saved ${name}.png (${Math.round(body.length / 1024)} KB)`);
        });
      });
    },
  };
}
