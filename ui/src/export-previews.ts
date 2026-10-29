/*
  The export tool's page script (see export.html). Draws the preview images and posts each to the
  dev server's /__previews endpoint (scripts/previews-plugin.mjs), which saves it into
  public/previews/. Plain DOM, no React: it is a tool, and it never ships.
*/
import "./index.css";
import { loadGalleryIndex } from "@/lib/gallery";
import { drawHomeCard, drawShareCard } from "@/lib/share-card";

const app = document.getElementById("app");
if (!app) throw new Error("export.html has no #app element.");

const heading = document.createElement("h1");
heading.textContent = "Export preview images";
heading.style.cssText = "font-size:1.25rem;color:var(--foreground-strong)";
const note = document.createElement("p");
note.textContent =
  "Draws the home card and one card per gallery session at 1200 by 630 and saves them to ui/public/previews/. Run it again whenever the gallery changes.";
note.style.cssText = "color:var(--muted-foreground);line-height:1.5";
const button = document.createElement("button");
button.type = "button";
button.textContent = "Export previews";
button.style.cssText =
  "margin:1rem 0;padding:.6rem 1.2rem;border-radius:999px;border:0;background:var(--primary);color:var(--primary-foreground);font:inherit;cursor:pointer";
const log = document.createElement("pre");
log.style.cssText = "white-space:pre-wrap;color:var(--foreground)";
log.setAttribute("role", "status");
app.append(heading, note, button, log);

async function save(name: string, blob: Blob): Promise<string> {
  const response = await fetch(`/__previews/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "X-Preview-Export": "1", "Content-Type": "image/png" },
    body: blob,
  });
  const message = await response.text();
  if (!response.ok) throw new Error(`${name}: ${message}`);
  return message;
}

button.addEventListener("click", async () => {
  button.disabled = true;
  log.textContent = "";
  try {
    // host null: these are public files; the footer must not print this dev server's address.
    log.textContent += `${await save("home", await drawHomeCard(1, null))}\n`;
    const index = await loadGalleryIndex();
    for (const session of index.sessions) {
      log.textContent += `${await save(session.id, await drawShareCard(session, 1, null))}\n`;
    }
    log.textContent += `\nDone: ${index.sessions.length + 1} images in ui/public/previews/.`;
  } catch (error) {
    log.textContent += `\nStopped: ${error instanceof Error ? error.message : String(error)}`;
  } finally {
    button.disabled = false;
  }
});
