"use client";

import { Download, Loader2, MicOff, Pause, Play, Volume2, VolumeX } from "lucide-react";
import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useLayoutEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type Ref,
} from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { ApiError, api } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type { RecordingUrl } from "@/lib/types";

export interface AudioPlayerHandle {
  seek: (t: number) => void;
  play: () => void;
}

const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2];

type LoadState = { kind: "loading" } | { kind: "ready"; url: string } | { kind: "missing" } | { kind: "error"; message: string };

export function AudioPlayer({
  meetingId,
  canDownload,
  initialTime,
  onTimeUpdate,
  ref,
}: {
  meetingId: string;
  canDownload: boolean;
  initialTime?: number;
  onTimeUpdate?: (t: number) => void;
  ref?: Ref<AudioPlayerHandle>;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [state, setState] = useState<LoadState>({ kind: "loading" });
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useState(1);
  const pendingSeek = useRef<number | null>(initialTime ?? null);
  const resumeAfterReload = useRef(false);
  const retried = useRef(false);

  const loadUrl = useCallback(async () => {
    try {
      const r = await api.get<RecordingUrl>(`/api/meetings/${meetingId}/recording?kind=audio`);
      setState({ kind: "ready", url: r.url });
    } catch (e) {
      if (e instanceof ApiError && e.code === "recording_not_found") setState({ kind: "missing" });
      else setState({ kind: "error", message: e instanceof Error ? e.message : "Could not load the recording." });
    }
  }, [meetingId]);

  useEffect(() => {
    void loadUrl();
  }, [loadUrl]);

  // Pages stay mounted (hidden) after navigation: stop audio when this one is hidden.
  useLayoutEffect(() => {
    const a = audioRef.current;
    return () => a?.pause();
  }, [state.kind]);

  const seek = useCallback((t: number) => {
    const a = audioRef.current;
    if (!a || !Number.isFinite(a.duration || NaN)) {
      pendingSeek.current = t;
      return;
    }
    a.currentTime = Math.max(0, t);
    setTime(a.currentTime);
  }, []);

  const play = useCallback(() => {
    void audioRef.current?.play().catch(() => undefined);
  }, []);

  useImperativeHandle(ref, () => ({ seek, play }), [seek, play]);

  const onError = () => {
    const a = audioRef.current;
    if (!a || retried.current) {
      setState({ kind: "error", message: "The recording could not be played." });
      return;
    }
    // Most likely the short-lived link expired: fetch a fresh one and continue where we were.
    retried.current = true;
    pendingSeek.current = a.currentTime;
    resumeAfterReload.current = !a.paused || playing;
    void loadUrl();
  };

  const onLoadedMetadata = () => {
    const a = audioRef.current!;
    setDuration(Number.isFinite(a.duration) ? a.duration : 0);
    if (pendingSeek.current !== null) {
      a.currentTime = pendingSeek.current;
      setTime(pendingSeek.current);
      pendingSeek.current = null;
    }
    a.playbackRate = speed;
    if (resumeAfterReload.current) {
      resumeAfterReload.current = false;
      play();
    }
  };

  const download = async () => {
    try {
      const r = await api.get<RecordingUrl>(`/api/meetings/${meetingId}/recording?kind=audio&download=true`);
      window.location.assign(r.url);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Download failed");
    }
  };

  const onKey = (e: KeyboardEvent) => {
    const a = audioRef.current;
    if (!a || (e.target as HTMLElement).closest("input,[role=slider],[role=combobox]")) return;
    if (e.key === " ") {
      e.preventDefault();
      if (a.paused) play();
      else a.pause();
    } else if (e.key === "ArrowLeft") seek(a.currentTime - 5);
    else if (e.key === "ArrowRight") seek(a.currentTime + 5);
  };

  if (state.kind === "missing") {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-dashed px-4 py-3 text-sm text-muted-foreground">
        <MicOff className="size-4" /> No recording available
      </div>
    );
  }
  if (state.kind === "error") {
    return (
      <div role="alert" className="flex items-center justify-between gap-2 rounded-lg border border-destructive/30 px-4 py-3 text-sm">
        {state.message}
        <Button size="sm" variant="outline" onClick={() => { retried.current = false; setState({ kind: "loading" }); void loadUrl(); }}>
          Retry
        </Button>
      </div>
    );
  }

  return (
    <div
      tabIndex={0}
      onKeyDown={onKey}
      aria-label="Audio player"
      className="flex flex-wrap items-center gap-3 rounded-lg border bg-card px-3 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {state.kind === "ready" && (
        <audio
          ref={audioRef}
          src={state.url}
          preload="metadata"
          onLoadedMetadata={onLoadedMetadata}
          onCanPlay={() => { retried.current = false; }}
          onTimeUpdate={(e) => {
            const t = e.currentTarget.currentTime;
            setTime(t);
            onTimeUpdate?.(t);
          }}
          onDurationChange={(e) => setDuration(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : 0)}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onError={onError}
        />
      )}
      <Button
        size="icon"
        className="rounded-full"
        disabled={state.kind !== "ready"}
        aria-label={playing ? "Pause" : "Play"}
        onClick={() => (playing ? audioRef.current?.pause() : play())}
      >
        {state.kind === "loading" ? <Loader2 className="size-4 animate-spin" /> : playing ? <Pause className="size-4" /> : <Play className="size-4" />}
      </Button>
      <span className="w-24 shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
        {formatTimestamp(time)} / {formatTimestamp(duration)}
      </span>
      <Slider
        className="min-w-40 flex-1"
        min={0}
        max={duration || 1}
        step={1}
        value={[Math.min(time, duration || 1)]}
        onValueChange={([v]) => seek(v)}
        aria-label="Seek"
        disabled={!duration}
      />
      <div className="flex items-center gap-1">
        <Button
          size="icon"
          variant="ghost"
          aria-label={muted ? "Unmute" : "Mute"}
          onClick={() => {
            const m = !muted;
            setMuted(m);
            if (audioRef.current) audioRef.current.muted = m;
          }}
        >
          {muted || volume === 0 ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
        </Button>
        <Slider
          className="w-20"
          min={0}
          max={1}
          step={0.05}
          value={[muted ? 0 : volume]}
          onValueChange={([v]) => {
            setVolume(v);
            setMuted(v === 0);
            if (audioRef.current) {
              audioRef.current.volume = v;
              audioRef.current.muted = v === 0;
            }
          }}
          aria-label="Volume"
        />
      </div>
      <Select
        value={String(speed)}
        onValueChange={(v) => {
          const s = Number(v);
          setSpeed(s);
          if (audioRef.current) audioRef.current.playbackRate = s;
        }}
      >
        <SelectTrigger size="sm" className="h-8 w-20" aria-label="Playback speed"><SelectValue /></SelectTrigger>
        <SelectContent>{SPEEDS.map((s) => <SelectItem key={s} value={String(s)}>{s}×</SelectItem>)}</SelectContent>
      </Select>
      {canDownload && (
        <Button size="sm" variant="outline" onClick={download} aria-label="Download recording">
          <Download className="size-4" /> Download
        </Button>
      )}
    </div>
  );
}
