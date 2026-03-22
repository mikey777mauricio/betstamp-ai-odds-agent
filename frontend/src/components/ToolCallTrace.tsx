"use client";

import { useState } from "react";
import { ToolCall } from "@/lib/api";
import { TOOL_LABELS, getToolColor } from "@/lib/tools";

export default function ToolCallTrace({ toolCalls }: { toolCalls: ToolCall[] }) {
  const [expanded, setExpanded] = useState(true);

  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="border border-border rounded-xl bg-surface-secondary overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm hover:bg-brand-light/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="text-text-muted font-mono text-xs uppercase tracking-wider">Agent Reasoning</span>
          <span className="bg-brand text-white px-2.5 py-0.5 rounded-full text-xs font-medium">
            {toolCalls.length} tool{toolCalls.length > 1 ? "s" : ""}
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-text-muted transition-transform ${expanded ? "rotate-180" : ""}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {expanded && (
        <div className="border-t border-border px-4 py-3 space-y-2">
          {toolCalls.map((tc, i) => (
            <ToolCallItem key={i} call={tc} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolCallItem({ call, index }: { call: ToolCall; index: number }) {
  const [showInput, setShowInput] = useState(false);
  const label = TOOL_LABELS[call.tool] || call.tool;
  const colorClass = getToolColor(call.tool);
  const hasInput = call.input && Object.keys(call.input).length > 0;

  return (
    <div className="flex flex-col">
      <div
        className={`flex items-center gap-2 text-sm ${hasInput ? "cursor-pointer" : ""}`}
        onClick={() => hasInput && setShowInput(!showInput)}
      >
        <span className="text-text-muted font-mono text-xs w-5">{index}.</span>
        <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${colorClass}`}>
          {label}
        </span>
        {hasInput && (
          <svg
            className={`w-3 h-3 text-text-muted transition-transform ${showInput ? "rotate-180" : ""}`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </div>
      {showInput && hasInput && (
        <pre className="ml-7 mt-1.5 text-xs text-text-secondary bg-white border border-border rounded-lg p-3 overflow-x-auto font-mono">
          {JSON.stringify(call.input, null, 2)}
        </pre>
      )}
    </div>
  );
}
