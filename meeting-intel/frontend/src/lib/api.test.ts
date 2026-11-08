import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch } from "./api";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  const fn = vi.fn().mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status,
      headers: { "content-type": contentType },
    }),
  );
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("apiFetch", () => {
  it("returns parsed JSON on success", async () => {
    mockFetch(200, { ok: 1 });
    await expect(apiFetch<{ ok: number }>("/api/x")).resolves.toEqual({ ok: 1 });
  });

  it("parses the error envelope into ApiError", async () => {
    mockFetch(404, { error: { code: "not_found", message: "Meeting not found", details: null } });
    const err = await apiFetch("/api/meetings/x", { redirectOn401: false }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "not_found", message: "Meeting not found" });
  });

  it("maps a non-JSON gateway error", async () => {
    mockFetch(502, "<html>Bad gateway</html>", "text/html");
    const err = await apiFetch("/api/x").catch((e) => e);
    expect(err).toMatchObject({ status: 502, code: "bad_gateway" });
  });

  it("sends JSON bodies with the right content type and cookies", async () => {
    const fn = mockFetch(200, {});
    await apiFetch("/api/search", { method: "POST", json: { q: "revenue" } });
    const [, init] = fn.mock.calls[0];
    expect(init.body).toBe(JSON.stringify({ q: "revenue" }));
    expect(new Headers(init.headers).get("content-type")).toBe("application/json");
    expect(init.credentials).toBe("include");
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));
    await expect(apiFetch("/api/auth/logout", { method: "POST" })).resolves.toBeUndefined();
  });

  it("redirects to login on 401 outside auth endpoints", async () => {
    mockFetch(401, { error: { code: "unauthenticated", message: "Please sign in." } });
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/search", search: "?q=x", assign } as unknown as Location);
    await apiFetch("/api/meetings").catch(() => undefined);
    expect(assign).toHaveBeenCalledWith("/login?next=%2Fsearch%3Fq%3Dx");
  });

  it("does not redirect for auth endpoints", async () => {
    mockFetch(401, { error: { code: "invalid_credentials", message: "Incorrect email or password." } });
    const assign = vi.fn();
    vi.stubGlobal("location", { pathname: "/login", search: "", assign } as unknown as Location);
    const err = (await apiFetch("/api/auth/login", { method: "POST", json: {} }).catch((e) => e)) as ApiError;
    expect(assign).not.toHaveBeenCalled();
    expect(err.code).toBe("invalid_credentials");
  });
});
