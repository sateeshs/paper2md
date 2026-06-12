"use client";

import { useState } from "react";
import type { SATSubject, SATSession } from "@/lib/supabase/sat-queries";
import { SATResponse } from "./SATResponse";

const SUBJECTS: { id: SATSubject; label: string; desc: string }[] = [
  { id: "math",    label: "Math",    desc: "Algebra, geometry, data analysis" },
  { id: "reading", label: "Reading", desc: "Comprehension, evidence, inference" },
  { id: "english", label: "English", desc: "Grammar, expression of ideas" },
];

type Status = "idle" | "loading" | "streaming" | "complete" | "error";

export function SATForm() {
  const [subject, setSubject] = useState<SATSubject>("math");
  const [question, setQuestion] = useState("");
  const [context, setContext] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [result, setResult] = useState<Partial<SATSession> | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;

    setStatus("loading");
    setErrorMsg(null);
    setResult(null);
    setSessionId(null);

    let sid: string;
    try {
      const res = await fetch("/api/sat/queue", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: question.trim(), subject, user_context: context.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error ?? `Server error ${res.status}`);
      }
      const data = await res.json();
      sid = data.session_id;
    } catch (err) {
      setStatus("error");
      setErrorMsg(String(err));
      return;
    }

    setSessionId(sid);
    setStatus("streaming");

    // Open SSE stream
    const es = new EventSource(`/api/sat/status/${sid}`);

    es.onmessage = (ev) => {
      const payload = JSON.parse(ev.data) as { status: string } & Partial<SATSession>;
      if (payload.status === "complete") {
        setResult(payload);
        setStatus("complete");
        es.close();
      } else if (payload.status === "error") {
        setErrorMsg(payload.error_msg ?? "An error occurred.");
        setStatus("error");
        es.close();
      }
    };

    es.onerror = () => {
      setErrorMsg("Lost connection while waiting for results.");
      setStatus("error");
      es.close();
    };
  }

  function handleReset() {
    setStatus("idle");
    setErrorMsg(null);
    setResult(null);
    setSessionId(null);
  }

  return (
    <div className="space-y-6">
      {/* Subject tabs */}
      <div className="flex gap-2 bg-zinc-100 p-1 rounded-xl">
        {SUBJECTS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSubject(s.id)}
            disabled={status === "loading" || status === "streaming"}
            className={`flex-1 rounded-lg py-2 px-3 text-sm font-medium transition-colors ${
              subject === s.id
                ? "bg-white text-zinc-900 shadow-sm"
                : "text-zinc-500 hover:text-zinc-700"
            }`}
          >
            {s.label}
            <span className="block text-xs font-normal opacity-60">{s.desc}</span>
          </button>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Question */}
        <div>
          <label className="block text-sm font-medium text-zinc-700 mb-1">
            SAT Question
          </label>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={status === "loading" || status === "streaming"}
            rows={6}
            placeholder={
              subject === "math"
                ? "Paste the full question, including answer choices A–D…"
                : "Paste the passage and question, including answer choices A–D…"
            }
            className="w-full rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y disabled:opacity-50"
          />
        </div>

        {/* Context */}
        <div>
          <label className="block text-sm font-medium text-zinc-700 mb-1">
            Your context{" "}
            <span className="text-zinc-400 font-normal">(optional)</span>
          </label>
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            disabled={status === "loading" || status === "streaming"}
            rows={3}
            placeholder="What did you try? Which answer did you pick and why? What's confusing you?"
            className="w-full rounded-xl border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-y disabled:opacity-50"
          />
        </div>

        <div className="flex gap-3">
          <button
            type="submit"
            disabled={!question.trim() || status === "loading" || status === "streaming"}
            className="flex-1 rounded-xl bg-blue-600 px-6 py-3 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {status === "loading" || status === "streaming" ? "Thinking…" : "Explain this question"}
          </button>
          {(status === "complete" || status === "error") && (
            <button
              type="button"
              onClick={handleReset}
              className="rounded-xl border border-zinc-200 px-4 py-3 text-sm font-medium text-zinc-600 hover:bg-zinc-50 transition-colors"
            >
              New question
            </button>
          )}
        </div>
      </form>

      {/* Status indicator */}
      {(status === "loading" || status === "streaming") && (
        <div className="flex items-center gap-3 rounded-xl bg-blue-50 border border-blue-100 px-5 py-4">
          <span className="relative flex h-3 w-3">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-blue-500" />
          </span>
          <span className="text-sm text-blue-700">
            {status === "loading"
              ? "Queuing your question…"
              : "AI tutor is working on your question (this takes ~30–60 seconds)…"}
          </span>
        </div>
      )}

      {/* Error */}
      {status === "error" && errorMsg && (
        <div className="rounded-xl bg-red-50 border border-red-100 px-5 py-4 text-sm text-red-700">
          {errorMsg}
        </div>
      )}

      {/* Response */}
      {status === "complete" && result && (
        <SATResponse session={result as SATSession} subject={subject} />
      )}
    </div>
  );
}
