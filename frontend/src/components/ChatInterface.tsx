"use client";

import { useState, useRef, useEffect, ReactNode } from "react";
import { sendChatSync, ToolCall } from "@/lib/api";
import ToolCallTrace from "./ToolCallTrace";

function renderMarkdown(text: string): ReactNode[] {
  const lines = text.split("\n");
  return lines.map((line, i) => {
    if (line.startsWith("### ")) {
      return (
        <h3 key={i} className="text-base font-semibold mt-4 mb-1">
          {formatInline(line.slice(4))}
        </h3>
      );
    }
    if (line.startsWith("## ")) {
      return (
        <h2 key={i} className="text-lg font-bold mt-5 mb-2">
          {formatInline(line.slice(3))}
        </h2>
      );
    }
    if (line.startsWith("# ")) {
      return (
        <h1 key={i} className="text-xl font-bold mt-4 mb-2">
          {formatInline(line.slice(2))}
        </h1>
      );
    }
    if (line.startsWith("- ") || line.startsWith("  - ")) {
      const indent = line.startsWith("  ") ? "ml-4" : "";
      return (
        <div key={i} className={`${indent} py-0.5`}>
          {formatInline(line)}
        </div>
      );
    }
    if (line.trim() === "") return <br key={i} />;
    return (
      <p key={i} className="py-0.5">
        {formatInline(line)}
      </p>
    );
  });
}

function formatInline(text: string): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={i} className="font-semibold">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("`") && part.endsWith("`")) {
      return (
        <code key={i} className="bg-brand-light text-brand-dark px-1 rounded text-xs font-mono">
          {part.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCall[];
  duration?: number;
}

export default function ChatInterface() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setLoading(true);
    setChatError(null);

    try {
      const history = messages.map((m) => ({ role: m.role, content: m.content }));
      const result = await sendChatSync(userMessage, history);

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.response,
          toolCalls: result.tool_calls,
          duration: result.duration_seconds,
        },
      ]);
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "Failed to get response");
    } finally {
      setLoading(false);
    }
  };

  const suggestions = [
    "Why did you flag the Knicks game?",
    "Which books should I avoid tonight?",
    "Is there any arbitrage opportunity?",
    "What's the best bet on the Lakers game?",
    "Show me the vig at DraftKings",
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-8">
            <p className="text-text-muted text-sm mb-4">
              Ask follow-up questions about the briefing
            </p>
            <div className="flex flex-wrap gap-2 justify-center">
              {suggestions.map((s) => (
                <button
                  key={s}
                  onClick={() => setInput(s)}
                  className="text-xs px-3 py-1.5 bg-brand-light text-brand-dark rounded-full hover:bg-brand/10 transition-colors font-medium"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                msg.role === "user"
                  ? "bg-brand text-white"
                  : "bg-surface-secondary border border-border text-text-primary"
              }`}
            >
              {msg.role === "assistant" && msg.toolCalls && msg.toolCalls.length > 0 && (
                <div className="mb-3">
                  <ToolCallTrace toolCalls={msg.toolCalls} />
                </div>
              )}
              <div className="text-sm leading-relaxed">
                {msg.role === "assistant" ? renderMarkdown(msg.content) : msg.content}
              </div>
              {msg.duration && (
                <div className={`text-xs mt-2 ${msg.role === "user" ? "text-white/60" : "text-text-muted"}`}>
                  {msg.duration}s
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-surface-secondary border border-border rounded-2xl px-4 py-3">
              <div className="flex items-center gap-2 text-sm text-text-secondary">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-brand rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                  <span className="w-2 h-2 bg-brand rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                  <span className="w-2 h-2 bg-brand rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                </div>
                Analyzing with tools...
              </div>
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Error banner */}
      {chatError && (
        <div className="bg-red-50 border border-red-200 rounded-lg px-4 py-2.5 text-sm text-red-700 flex items-center justify-between">
          <span>{chatError}</span>
          <button onClick={() => setChatError(null)} className="text-red-500 hover:text-red-700 text-xs underline ml-2">
            Dismiss
          </button>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="flex gap-2 pt-3 border-t border-border">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about the briefing..."
          className="flex-1 bg-surface-secondary border border-border text-text-primary rounded-xl px-4 py-2.5 text-sm placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand transition-colors"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="px-5 py-2.5 bg-brand text-white rounded-xl text-sm font-medium hover:bg-brand-dark disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          Send
        </button>
      </form>
    </div>
  );
}
