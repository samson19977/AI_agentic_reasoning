"use client";

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  theme: "dark",
  themeVariables: {
    primaryColor: "#3b82f6",
    primaryTextColor: "#e5e7eb",
    lineColor: "#6b7280",
    secondaryColor: "#1e3a5f",
    tertiaryColor: "#1f2937",
  },
});

let idCounter = 0;

export default function MermaidDiagram({ code }: { code: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");

  useEffect(() => {
    const id = `mermaid-${idCounter++}`;
    let cancelled = false;

    mermaid
      .render(id, code)
      .then(({ svg: rendered }) => {
        if (!cancelled) setSvg(rendered);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });

    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <pre className="rounded bg-red-900/30 p-3 text-xs text-red-300 overflow-x-auto">
        {code}
      </pre>
    );
  }

  if (!svg) {
    return (
      <div className="animate-pulse rounded bg-gray-800 p-4 text-center text-sm text-gray-400">
        Rendering diagram…
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="my-4 flex justify-center overflow-x-auto [&>svg]:max-w-full"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
