/*
  One address per session: /s/<session id>, so a verdict can be linked to and shared.

  There is no router library. The page is one file; the browser's History API changes the
  address without reloading (pushState), and tells the app when the visitor goes back or
  forward (popstate). On Cloudflare Pages, public/_redirects serves index.html for every /s/
  path, and the app reads the id from the address. The id is the session's own id from the
  gallery index, written by the engine, so a link stays valid as long as the session is in the
  gallery.
*/

const PREFIX = `${import.meta.env.BASE_URL}s/`;

/** The session id in an address like /s/20261029-043202-noise-cancelling-headphones, or null. */
export function sessionIdFromPath(pathname: string): string | null {
  if (!pathname.startsWith(PREFIX)) return null;
  const rest = pathname.slice(PREFIX.length).replace(/\/+$/, "");
  if (rest === "" || rest.includes("/")) return null;
  try {
    return decodeURIComponent(rest);
  } catch {
    return null;
  }
}

export function sessionPath(id: string): string {
  return `${PREFIX}${encodeURIComponent(id)}`;
}

export function sessionUrl(id: string): string {
  return new URL(sessionPath(id), window.location.origin).href;
}

export const HOME_PATH = import.meta.env.BASE_URL;
