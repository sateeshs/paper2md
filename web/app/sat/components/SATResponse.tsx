"use client";

import { useState } from "react";
import type { SATSession, SATSubject } from "@/lib/supabase/sat-queries";
import { ProseWithMath } from "@/components/ProseWithMath";

interface SATResponseProps {
  session: SATSession;
  subject: SATSubject;
}

function Section({ title, children, className = "" }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-zinc-200 bg-white overflow-hidden ${className}`}>
      <div className="px-5 py-3 border-b border-zinc-100 bg-zinc-50">
        <h3 className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">{title}</h3>
      </div>
      <div className="px-5 py-4 text-sm text-zinc-800 leading-relaxed">
        {children}
      </div>
    </div>
  );
}

function StepByStep({ text }: { text: string }) {
  // Split numbered steps for visual clarity
  const lines = text.split(/\n/).filter(Boolean);
  return (
    <ol className="space-y-3 list-none">
      {lines.map((line, i) => {
        const match = line.match(/^(\d+)[.)]\s*(.+)/);
        if (match) {
          return (
            <li key={i} className="flex gap-3">
              <span className="shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-xs font-bold flex items-center justify-center mt-0.5">
                {match[1]}
              </span>
              <ProseWithMath text={match[2]} className="flex-1" />
            </li>
          );
        }
        return (
          <li key={i}>
            <ProseWithMath text={line} />
          </li>
        );
      })}
    </ol>
  );
}

function HintsPanel({ hintsJson }: { hintsJson: string }) {
  const [revealed, setRevealed] = useState(0);

  let hints: string[] = [];
  try {
    const parsed = JSON.parse(hintsJson);
    if (Array.isArray(parsed)) hints = parsed.map(String);
  } catch {
    hints = [hintsJson];
  }

  return (
    <div className="space-y-3">
      {hints.map((hint, i) => (
        <div key={i}>
          {i < revealed ? (
            <div className="rounded-lg bg-amber-50 border border-amber-100 px-4 py-3 text-sm text-zinc-800">
              <span className="text-xs font-semibold text-amber-600 block mb-1">Hint {i + 1}</span>
              <ProseWithMath text={hint} />
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setRevealed(i + 1)}
              className="w-full text-left rounded-lg border border-dashed border-zinc-300 px-4 py-3 text-sm text-zinc-400 hover:border-amber-300 hover:text-amber-600 transition-colors"
            >
              Reveal hint {i + 1}{i === 0 ? " (gentle nudge)" : i === 1 ? " (key insight)" : " (almost there)"}
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

export function SATResponse({ session, subject }: SATResponseProps) {
  const isMath = subject === "math";

  return (
    <div className="space-y-4 mt-2">
      {/* Concept */}
      {session.explanation && (
        <Section title="What this question tests">
          <ProseWithMath text={session.explanation} />
        </Section>
      )}

      {/* Key concepts chips */}
      {session.key_concepts && (
        <div className="flex flex-wrap gap-2">
          {session.key_concepts.split(",").map((concept, i) => (
            <span
              key={i}
              className="text-xs bg-blue-50 text-blue-700 border border-blue-100 rounded-full px-3 py-1 font-medium"
            >
              {concept.trim()}
            </span>
          ))}
        </div>
      )}

      {/* Step-by-step */}
      {session.step_by_step && (
        <Section title={isMath ? "Step-by-step solution" : "Step-by-step reasoning"}>
          <StepByStep text={session.step_by_step} />
        </Section>
      )}

      {/* Progressive hints */}
      {session.hints && (
        <Section title="Hints (reveal one at a time)">
          <HintsPanel hintsJson={session.hints} />
        </Section>
      )}

      {/* Answer */}
      {session.answer && (
        <Section title="Answer" className="border-green-200">
          <div className="bg-green-50 rounded-lg px-4 py-3">
            <ProseWithMath text={session.answer} />
          </div>
        </Section>
      )}

      {/* Common mistakes */}
      {session.common_mistakes && (
        <Section title="Common mistakes">
          <div className="flex gap-3">
            <span className="text-lg shrink-0">⚠️</span>
            <ProseWithMath text={session.common_mistakes} />
          </div>
        </Section>
      )}

      {/* SAT strategy */}
      {session.sat_strategy && (
        <Section title="SAT strategy">
          <div className="flex gap-3">
            <span className="text-lg shrink-0">💡</span>
            <ProseWithMath text={session.sat_strategy} />
          </div>
        </Section>
      )}

      {/* Footer */}
      {session.agent_model && (
        <p className="text-xs text-zinc-400 text-right">
          Generated by {session.agent_model}
        </p>
      )}
    </div>
  );
}
