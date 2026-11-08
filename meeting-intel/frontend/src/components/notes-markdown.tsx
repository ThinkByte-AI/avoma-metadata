"use client";

import ReactMarkdown from "react-markdown";

/** Renders Avoma's notes.md. Raw HTML in the markdown is never rendered (react-markdown default). */
export function NotesMarkdown({ markdown }: { markdown: string }) {
  // Title and date line duplicate the page header.
  const body = markdown.replace(/^# .*\n/, "").replace(/^_[^_\n]+_\s*\n/m, "");
  return (
    <div className="space-y-3 text-sm leading-relaxed">
      <ReactMarkdown
        components={{
          h1: ({ children }) => <h2 className="text-base font-semibold">{children}</h2>,
          h2: ({ children }) => <h3 className="mt-5 text-sm font-semibold first:mt-0">{children}</h3>,
          h3: ({ children }) => <h4 className="mt-3 text-sm font-medium">{children}</h4>,
          ul: ({ children }) => <ul className="ml-5 list-disc space-y-1 marker:text-muted-foreground">{children}</ul>,
          ol: ({ children }) => <ol className="ml-5 list-decimal space-y-1">{children}</ol>,
          p: ({ children }) => <p>{children}</p>,
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noreferrer noopener" className="underline underline-offset-2">
              {children}
            </a>
          ),
        }}
      >
        {body}
      </ReactMarkdown>
    </div>
  );
}
