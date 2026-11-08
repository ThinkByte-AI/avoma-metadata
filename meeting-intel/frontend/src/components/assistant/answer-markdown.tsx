"use client";

import { Children, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { splitCitations } from "@/lib/citations";

/** Replace [n] markers inside plain-text children with small superscript buttons. */
function withCitations(children: ReactNode, known: Set<number>, onCite: (n: number) => void): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child !== "string") return child;
    return splitCitations(child).map((part, i) =>
      part.type === "text" ? (
        part.value
      ) : known.has(part.n) ? (
        <button
          key={`c${i}`}
          type="button"
          onClick={() => onCite(part.n)}
          className="mx-0.5 inline-flex -translate-y-1 items-center rounded bg-primary/10 px-1 align-baseline text-[10px] font-semibold leading-4 text-primary hover:bg-primary/20"
          aria-label={`Source ${part.n}`}
        >
          {part.n}
        </button>
      ) : null,
    );
  });
}

/** Renders the assistant's answer. Raw HTML in the markdown is never rendered (react-markdown default). */
export function AnswerMarkdown({
  markdown,
  citationNumbers,
  onCite,
}: {
  markdown: string;
  citationNumbers: number[];
  onCite: (n: number) => void;
}) {
  const known = new Set(citationNumbers);
  const cite = (children: ReactNode) => withCitations(children, known, onCite);
  return (
    <div className="space-y-2.5 text-sm leading-relaxed">
      <ReactMarkdown
        components={{
          h1: ({ children }) => <h3 className="text-base font-semibold">{cite(children)}</h3>,
          h2: ({ children }) => <h3 className="mt-3 text-sm font-semibold first:mt-0">{cite(children)}</h3>,
          h3: ({ children }) => <h4 className="mt-2 text-sm font-medium">{cite(children)}</h4>,
          p: ({ children }) => <p>{cite(children)}</p>,
          li: ({ children }) => <li>{cite(children)}</li>,
          strong: ({ children }) => <strong className="font-semibold">{cite(children)}</strong>,
          em: ({ children }) => <em>{cite(children)}</em>,
          ul: ({ children }) => <ul className="ml-5 list-disc space-y-1 marker:text-muted-foreground">{children}</ul>,
          ol: ({ children }) => <ol className="ml-5 list-decimal space-y-1">{children}</ol>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className="underline underline-offset-2">
              {children}
            </a>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
