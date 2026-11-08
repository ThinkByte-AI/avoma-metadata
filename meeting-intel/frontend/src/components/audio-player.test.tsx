import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { AudioPlayer } from "./audio-player";

beforeAll(() => {
  // jsdom has no media playback; give the element a settable clock and no-op controls.
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true,
    get() {
      return (this as unknown as { _t?: number })._t ?? 0;
    },
    set(v: number) {
      (this as unknown as { _t?: number })._t = v;
    },
  });
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

afterEach(() => vi.unstubAllGlobals());

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

const urlBody = (url: string) => ({ url, expires_at: "2030-01-01T00:00:00Z", content_type: "audio/mpeg", kind: "audio" });

describe("AudioPlayer", () => {
  it("refetches an expired URL once and resumes at the same second", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json(200, urlBody("https://s3.example/first.mp3")))
      .mockResolvedValueOnce(json(200, urlBody("https://s3.example/second.mp3")));
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(<AudioPlayer meetingId="m1" canDownload={false} />);
    const audio = await waitFor(() => {
      const a = container.querySelector("audio")!;
      expect(a.getAttribute("src")).toBe("https://s3.example/first.mp3");
      return a;
    });

    audio.currentTime = 42;
    fireEvent.error(audio);
    await waitFor(() => expect(audio.getAttribute("src")).toBe("https://s3.example/second.mp3"));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    fireEvent.loadedMetadata(audio);
    expect(audio.currentTime).toBe(42);

    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
  });

  it("shows a download button only when allowed", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(200, urlBody("https://s3.example/a.mp3"))));
    render(<AudioPlayer meetingId="m1" canDownload />);
    expect(await screen.findByRole("button", { name: /download/i })).toBeInTheDocument();
  });

  it("says when there is no recording", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      json(404, { error: { code: "recording_not_found", message: "This meeting has no audio recording." } }),
    ));
    const { container } = render(<AudioPlayer meetingId="m1" canDownload />);
    expect(await screen.findByText("No recording available")).toBeInTheDocument();
    expect(container.querySelector("audio")).toBeNull();
  });

  it("seeks to the initial time once metadata is loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(200, urlBody("https://s3.example/a.mp3"))));
    const { container } = render(<AudioPlayer meetingId="m1" canDownload={false} initialTime={125} />);
    const audio = await waitFor(() => {
      const a = container.querySelector("audio")!;
      expect(a.getAttribute("src")).toBeTruthy();
      return a;
    });
    fireEvent.loadedMetadata(audio);
    expect(audio.currentTime).toBe(125);
  });
});
