import { NextResponse, type NextRequest } from "next/server";

// Runs before every matched request:
//  - /api/*  → forwarded to the FastAPI backend (same-origin for the browser, so the httpOnly cookie works)
//  - pages   → sign-in redirect when there is no session cookie (the backend still checks every call)

const SESSION_COOKIE = "mi_session";
const PUBLIC_PAGES = ["/login"];

function backendUrl(): string {
  return (process.env.BACKEND_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  if (pathname.startsWith("/api/")) {
    return NextResponse.rewrite(new URL(`${pathname}${search}`, backendUrl()));
  }

  const hasSession = Boolean(request.cookies.get(SESSION_COOKIE)?.value);
  if (!hasSession && !PUBLIC_PAGES.includes(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except Next internals and static files.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico|txt)$).*)"],
};
