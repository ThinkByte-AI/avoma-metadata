"use client";

import { Info, Loader2, RotateCw, SendHorizonal, SlidersHorizontal, Sparkles, Trash2 } from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { AnswerMarkdown } from "@/components/assistant/answer-markdown";
import { CitationList, citationAnchorId } from "@/components/assistant/citation-list";
import { PeoplePicker } from "@/components/people-picker";
import { PageHeader } from "@/components/states";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError, api } from "@/lib/api";
import type { AskResponse, DatePreset, SearchFilters } from "@/lib/types";

const EXAMPLES = [
  "What did John promise in his previous meetings?",
  "Summarize all discussions about the product launch.",
  "What decisions were made about pricing?",
  "Which meetings discussed pending tasks?",
  "What commitments were made by each participant?",
  "Compare discussions about revenue across different months.",
];

const PRESETS: { value: DatePreset | "all"; label: string }[] = [
  { value: "all", label: "Entire archive" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "6m", label: "Last 6 months" },
  { value: "1y", label: "Last year" },
];

const HISTORY_TURNS = 6;

type Turn =
  | { id: string; role: "user"; content: string }
  | { id: string; role: "assistant"; status: "pending"; question: string }
  | { id: string; role: "assistant"; status: "done"; question: string; response: AskResponse }
  | { id: string; role: "assistant"; status: "error"; question: string; message: string };

let seq = 0;
const newId = () => `t${Date.now().toString(36)}${(seq++).toString(36)}`;

function errorMessage(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "rate_limited") return "You've asked a lot of questions in the last minute. Please wait a moment, then try again.";
    if (e.code === "ai_unavailable") return "The AI assistant is unavailable right now. Please try again shortly.";
    return e.message;
  }
  return "Something went wrong while asking the assistant.";
}

/** Conversation so far as {role, content}, last few turns only (answers only once they completed). */
function historyFrom(turns: Turn[]): { role: "user" | "assistant"; content: string }[] {
  const out: { role: "user" | "assistant"; content: string }[] = [];
  for (const t of turns) {
    if (t.role === "user") out.push({ role: "user", content: t.content });
    else if (t.status === "done") out.push({ role: "assistant", content: t.response.answer_markdown });
  }
  return out.slice(-HISTORY_TURNS);
}

function AssistantAnswer({ turn, onRetry }: { turn: Exclude<Turn, { role: "user" }>; onRetry: () => void }) {
  const [highlighted, setHighlighted] = useState<number | null>(null);

  if (turn.status === "pending") {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <Loader2 className="size-4 animate-spin" /> Searching the archive…
      </div>
    );
  }
  if (turn.status === "error") {
    return (
      <div role="alert" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
        <span>{turn.message}</span>
        <Button size="sm" variant="outline" onClick={onRetry}>
          <RotateCw className="size-3.5" /> Retry
        </Button>
      </div>
    );
  }

  const r = turn.response;
  const numbers = r.citations.map((c) => c.n);
  const scrollTo = (n: number) => {
    setHighlighted(n);
    document.getElementById(citationAnchorId(turn.id, n))?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  return (
    <div className="space-y-4">
      {!r.evidence_found && (
        <div className="flex items-start gap-2 rounded-lg border bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
          <Info className="mt-0.5 size-4 shrink-0" />
          <span>No matching evidence in the meeting archive. Try different words, a person's name, or a wider date range.</span>
        </div>
      )}
      <AnswerMarkdown markdown={r.answer_markdown} citationNumbers={numbers} onCite={scrollTo} />
      <CitationList messageId={turn.id} citations={r.citations} highlighted={highlighted} />
      <p className="text-[11px] text-muted-foreground">
        {(r.took_ms / 1000).toFixed(1)} s · {r.model}
      </p>
    </div>
  );
}

export default function AssistantPage() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [preset, setPreset] = useState<DatePreset | "all">("all");
  const [participants, setParticipants] = useState<number[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const busy = turns.some((t) => t.role === "assistant" && t.status === "pending");
  const filterCount = (preset !== "all" ? 1 : 0) + (participants.length ? 1 : 0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns.length]);

  const filters = (): SearchFilters | undefined => {
    const f: SearchFilters = {};
    if (preset !== "all") f.date_preset = preset;
    if (participants.length) f.participant_ids = participants;
    return Object.keys(f).length ? f : undefined;
  };

  const run = async (answerId: string, question: string, history: ReturnType<typeof historyFrom>) => {
    try {
      const response = await api.post<AskResponse>("/api/ai/ask", { question, filters: filters(), history });
      setTurns((ts) => ts.map((t) => (t.id === answerId ? { id: answerId, role: "assistant", status: "done", question, response } : t)));
    } catch (e) {
      setTurns((ts) =>
        ts.map((t) => (t.id === answerId ? { id: answerId, role: "assistant", status: "error", question, message: errorMessage(e) } : t)),
      );
    }
  };

  const ask = (text: string) => {
    const question = text.trim();
    if (!question || busy) return;
    const history = historyFrom(turns);
    const answerId = newId();
    setTurns((ts) => [
      ...ts,
      { id: newId(), role: "user", content: question },
      { id: answerId, role: "assistant", status: "pending", question },
    ]);
    setDraft("");
    void run(answerId, question, history);
  };

  const retry = (answerId: string, question: string) => {
    if (busy) return;
    const idx = turns.findIndex((t) => t.id === answerId);
    const history = historyFrom(turns.slice(0, Math.max(0, idx - 1)));
    setTurns((ts) => ts.map((t) => (t.id === answerId ? { id: answerId, role: "assistant", status: "pending", question } : t)));
    void run(answerId, question, history);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      ask(draft);
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col">
      <PageHeader
        title="AI Assistant"
        description="Ask questions across all your meetings. Every answer cites the transcript passages it uses."
        actions={
          turns.length > 0 && (
            <Button variant="ghost" size="sm" onClick={() => setTurns([])} disabled={busy}>
              <Trash2 className="size-4" /> New chat
            </Button>
          )
        }
      />

      {turns.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6">
          <div className="mb-4 flex items-center gap-2 text-sm font-medium">
            <Sparkles className="size-4 text-primary" /> Try asking
          </div>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => ask(q)}
                className="rounded-full border bg-background px-3 py-1.5 text-left text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-6" aria-live="polite">
          {turns.map((t) =>
            t.role === "user" ? (
              <div key={t.id} className="flex justify-end">
                <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm text-primary-foreground">
                  {t.content}
                </div>
              </div>
            ) : (
              <div key={t.id} className="flex gap-3">
                <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Sparkles className="size-3.5" />
                </span>
                <div className="min-w-0 flex-1">
                  <AssistantAnswer turn={t} onRetry={() => retry(t.id, t.question)} />
                </div>
              </div>
            ),
          )}
        </div>
      )}
      <div ref={bottomRef} />

      <div className="sticky bottom-0 mt-6 bg-background/90 pb-4 pt-2 backdrop-blur">
        <div className="rounded-xl border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask about decisions, commitments, people or topics…"
            rows={2}
            maxLength={2000}
            className="min-h-12 resize-none border-0 shadow-none focus-visible:ring-0"
            aria-label="Question"
          />
          <div className="flex items-center justify-between gap-2 px-1 pt-1">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="ghost" size="sm" className="h-8 text-muted-foreground">
                  <SlidersHorizontal className="size-4" /> Filters
                  {filterCount > 0 && (
                    <span className="rounded bg-primary px-1 text-[10px] text-primary-foreground">{filterCount}</span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" className="w-72 space-y-3">
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground">Date range</p>
                  <Select value={preset} onValueChange={(v) => setPreset(v as DatePreset | "all")}>
                    <SelectTrigger size="sm" className="h-8 w-full" aria-label="Date range"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {PRESETS.map((p) => <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground">Only meetings with</p>
                  <PeoplePicker label="Participants" value={participants} onChange={setParticipants} />
                </div>
                {filterCount > 0 && (
                  <Button variant="ghost" size="sm" className="h-7 px-2" onClick={() => { setPreset("all"); setParticipants([]); }}>
                    Clear filters
                  </Button>
                )}
              </PopoverContent>
            </Popover>
            <div className="flex items-center gap-2">
              <span className="hidden text-[11px] text-muted-foreground sm:inline">Enter to send · Shift+Enter for a new line</span>
              <Button size="sm" onClick={() => ask(draft)} disabled={busy || !draft.trim()} aria-label="Send question">
                {busy ? <Loader2 className="size-4 animate-spin" /> : <SendHorizonal className="size-4" />} Ask
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
