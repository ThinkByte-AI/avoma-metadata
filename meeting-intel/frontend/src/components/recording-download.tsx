"use client";

import { Film, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import type { RecordingUrl } from "@/lib/types";

/** The mp4 is offered as a download only (playback uses the smaller mp3). */
export function VideoDownloadButton({ meetingId }: { meetingId: string }) {
  const [busy, setBusy] = useState(false);
  const download = async () => {
    setBusy(true);
    try {
      const r = await api.get<RecordingUrl>(`/api/meetings/${meetingId}/recording?kind=video&download=true`);
      location.assign(r.url);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Download failed");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Button size="sm" variant="outline" onClick={download} disabled={busy} aria-label="Download video">
      {busy ? <Loader2 className="size-4 animate-spin" /> : <Film className="size-4" />} Video
    </Button>
  );
}
