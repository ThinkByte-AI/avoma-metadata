const FALLBACK = "/overview";
// A fixed origin lets us resolve the value exactly as the browser would, then check it stays on this site.
const BASE = "http://same-site.invalid";

/** Where to go after sign-in. Only same-site paths are allowed; anything else goes to the overview. */
export function safeNext(next: string | null | undefined): string {
  if (!next || !next.startsWith("/")) return FALLBACK;
  let url: URL;
  try {
    url = new URL(next, BASE);
  } catch {
    return FALLBACK;
  }
  if (url.origin !== BASE) return FALLBACK; // e.g. "//evil.com" or "/\evil.com"
  return `${url.pathname}${url.search}${url.hash}`;
}
