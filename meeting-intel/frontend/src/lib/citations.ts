export type CitationPart = { type: "text"; value: string } | { type: "cite"; n: number };

const CITE = /\[(\d+)\]/g;

/** Split an answer into text runs and [n] citation markers. Brackets that are not plain numbers stay text. */
export function splitCitations(markdown: string): CitationPart[] {
  const parts: CitationPart[] = [];
  let last = 0;
  for (const m of markdown.matchAll(CITE)) {
    const i = m.index ?? 0;
    if (i > last) parts.push({ type: "text", value: markdown.slice(last, i) });
    parts.push({ type: "cite", n: Number(m[1]) });
    last = i + m[0].length;
  }
  if (last < markdown.length) parts.push({ type: "text", value: markdown.slice(last) });
  return parts;
}
