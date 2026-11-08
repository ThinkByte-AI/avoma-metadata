import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VideoDownloadButton } from "./recording-download";

afterEach(() => vi.unstubAllGlobals());

describe("VideoDownloadButton", () => {
  it("asks for a video download link and opens it", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ url: "https://s3.example/v.mp4", expires_at: "2030-01-01T00:00:00Z", content_type: "video/mp4", kind: "video" }),
        { status: 200, headers: { "content-type": "application/json" } }),
    );
    const assign = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("location", { pathname: "/meetings/m1", search: "", assign } as unknown as Location);

    render(<VideoDownloadButton meetingId="m1" />);
    fireEvent.click(screen.getByRole("button", { name: /download video/i }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://s3.example/v.mp4"));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/meetings/m1/recording?kind=video&download=true");
  });
});
