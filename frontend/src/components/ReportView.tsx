"use client";

import ReactMarkdown from "react-markdown";
import MermaidDiagram from "./MermaidDiagram";

export default function ReportView({ markdown }: { markdown: string }) {
  return (
    <article className="prose prose-invert prose-sm max-w-none prose-headings:text-gray-200 prose-p:text-gray-300 prose-li:text-gray-300 prose-strong:text-gray-100 prose-a:text-blue-400">
      <ReactMarkdown
        components={{
          code({ className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || "");
            if (match && match[1] === "mermaid") {
              return <MermaidDiagram code={String(children).trim()} />;
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  );
}
