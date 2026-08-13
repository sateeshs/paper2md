"use client";

import { useEffect, useRef, useState } from "react";
import type { MathBlock as MathBlockType } from "@/lib/supabase/types";
import { KATEX_OPTIONS, isDisplayMode, prepareLatex } from "@/lib/katex-helpers";
import { ProseWithMath } from "@/components/ProseWithMath";
import { CodePanel } from "@/components/CodePanel";
import type { CodeSection, CodeArtifactForSave } from "@/components/CodePanel";
import { flags } from "@/lib/feature-flags";

interface MathBlockProps {
  block: MathBlockType;
}

type Library = "numpy" | "pytorch" | "jax" | "scipy";
type CodeState = "idle" | "loading" | "ready" | "error" | "not_implementable";
type VizMode = "static" | "animated";
type VizState = "idle" | "loading" | "ready" | "error" | "saving";

interface CodeArtifact {
  function_name?: string;
  imports?: string;
  code?: string;
  parameters?: unknown;
  example_usage?: string;
  test_code?: string | null;
  notes?: string;
  prompt_context?: {
    formula?: string;
    what_it_computes?: string;
    symbol_meanings?: string;
    context_before?: string;
    context_after?: string;
    library?: string;
  };
  generated_model?: string;
}

const LIBRARIES: Library[] = ["numpy", "pytorch", "jax", "scipy"];

const NOTATION_KW = [
  "is purely notation",
  "is notation for",
  "introduces notation",
  "shorthand for",
  "symbol for",
  "no computation",
  "cannot be computed",
  "not a computation",
];

function isImplementable(block: MathBlockType): boolean {
  if (!block.explanation) return false;
  if (block.env_type === "inline" && (block.latex_expr ?? "").length < 10) return false;
  try {
    const exp = JSON.parse(block.explanation) as { what_it_computes?: string };
    const what = (exp.what_it_computes ?? "").toLowerCase();
    if (NOTATION_KW.some((kw) => what.includes(kw))) return false;
    return !!exp.what_it_computes;
  } catch {
    return false;
  }
}

export function MathBlock({ block }: MathBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [renderError, setRenderError] = useState(false);
  const [showExplanation, setShowExplanation] = useState(false);

  // Code toggle state
  const [showCode, setShowCode] = useState(false);
  const [codeState, setCodeState] = useState<CodeState>("idle");
  const [codeData, setCodeData] = useState<CodeArtifact | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [library, setLibrary] = useState<Library>("numpy");

  // Visualize state
  const [showViz, setShowViz] = useState(false);
  const [vizMode, setVizMode] = useState<VizMode>("static");
  const [vizState, setVizState] = useState<VizState>("idle");
  const [vizUrl, setVizUrl] = useState<string | null>(null);
  const [vizCode, setVizCode] = useState<string | null>(null);
  const [vizError, setVizError] = useState<string | null>(null);
  const [vizSaved, setVizSaved] = useState(false);
  const [vizImageData, setVizImageData] = useState<string | null>(null);
  const [vizContentType, setVizContentType] = useState<string | null>(null);

  const displayMode = isDisplayMode(block.env_type);
  const prepared = prepareLatex(block.latex_expr, displayMode);

  useEffect(() => {
    if (!prepared || !containerRef.current) return;

    import("katex").then(({ default: katex }) => {
      try {
        katex.render(prepared, containerRef.current!, {
          ...KATEX_OPTIONS,
          displayMode,
        });
        setRenderError(false);
      } catch {
        setRenderError(true);
      }
    });
  }, [prepared, displayMode]);

  function handleLibraryChange(next: Library) {
    setLibrary(next);
    // Reset so next expand re-fetches for new library
    if (codeState === "ready") {
      setCodeState("idle");
      setCodeData(null);
    }
  }

  async function handleCodeToggle() {
    const next = !showCode;
    setShowCode(next);

    if (next && codeState === "idle") {
      setCodeState("loading");
      try {
        const res = await fetch(`/api/math/${block.id}/code`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ library }),
        });
        const data = await res.json();
        if (data.error && String(data.error).startsWith("block is not implementable")) {
          setCodeState("not_implementable");
        } else if (!res.ok || data.error) {
          setCodeError(data.error ?? "Unknown error");
          setCodeState("error");
        } else {
          setCodeData(data as CodeArtifact);
          setCodeState("ready");
          // Cache in localStorage so DownloadSectionButton can include generated code
          try {
            localStorage.setItem(`code:${block.id}:${library}`, JSON.stringify(data))
          } catch { /* quota exceeded — non-fatal */ }
        }
      } catch (err) {
        setCodeError(err instanceof Error ? err.message : "Network error");
        setCodeState("error");
      }
    }
  }

  function handleVizModeChange(next: VizMode) {
    setVizMode(next);
    if (vizState === "ready") {
      setVizState("idle");
      setVizUrl(null);
      setVizCode(null);
      setVizSaved(false);
      setVizImageData(null);
      setVizContentType(null);
    }
  }

  async function handleVizToggle() {
    const next = !showViz;
    setShowViz(next);

    if (next && vizState === "idle") {
      setVizState("loading");
      try {
        const res = await fetch(`/api/math/${block.id}/visualize`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode: vizMode }),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          setVizError(data.error ?? "Visualization failed");
          setVizCode(data.manim_code ?? null);
          setVizState("error");
        } else if (data.saved) {
          // Previously saved — URL from DB
          setVizUrl(data.image_url ?? data.video_url ?? null);
          setVizCode(data.manim_code ?? null);
          setVizSaved(true);
          setVizState("ready");
        } else {
          // Fresh render — base64 preview (not yet saved)
          setVizImageData(data.image_data ?? null);
          setVizContentType(data.content_type ?? null);
          setVizCode(data.manim_code ?? null);
          setVizSaved(false);
          setVizState("ready");
        }
      } catch (err) {
        setVizError(err instanceof Error ? err.message : "Network error");
        setVizState("error");
      }
    }
  }

  async function handleVizSave() {
    if (!vizImageData) return;
    setVizState("saving");
    try {
      const res = await fetch(`/api/math/${block.id}/visualize/save`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image_data: vizImageData,
          manim_code: vizCode,
          mode: vizMode,
          content_type: vizContentType,
        }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        setVizError(data.error ?? "Save failed");
        setVizState("error");
      } else {
        setVizUrl(data.image_url ?? data.video_url ?? null);
        setVizSaved(true);
        setVizImageData(null);
        setVizState("ready");
      }
    } catch (err) {
      setVizError(err instanceof Error ? err.message : "Save failed");
      setVizState("error");
    }
  }

  // Expression is entirely commented-out or empty — nothing to render
  if (!prepared) return null;

  const codeSections: CodeSection[] = codeData
    ? [
        {
          label: "PROMPT CONTEXT",
          content: codeData.prompt_context
            ? [
                `Formula: ${codeData.prompt_context.formula ?? ""}`,
                `What it computes: ${codeData.prompt_context.what_it_computes ?? ""}`,
                `Symbols: ${codeData.prompt_context.symbol_meanings ?? ""}`,
                codeData.prompt_context.context_before ? `Context before: ${codeData.prompt_context.context_before}` : "",
                codeData.prompt_context.context_after ? `Context after: ${codeData.prompt_context.context_after}` : "",
                `Library: ${codeData.prompt_context.library ?? library}`,
              ]
                .filter(Boolean)
                .join("\n")
            : "",
          defaultOpen: false,
        },
        {
          label: "IMPORTS",
          content: codeData.imports ?? "",
          defaultOpen: true,
        },
        {
          label: "FUNCTION",
          content: codeData.code ?? "",
          defaultOpen: true,
        },
        {
          label: "EXAMPLE USAGE",
          content: codeData.example_usage ?? "",
          defaultOpen: true,
        },
        ...(codeData.test_code
          ? [{ label: "TESTS", content: codeData.test_code, defaultOpen: false }]
          : []),
      ]
    : [];

  return (
    <div className="my-4 rounded-lg border border-zinc-200 dark:border-zinc-700 overflow-hidden">
      {/* Rendered math */}
      <div className="px-4 py-3 bg-zinc-50 dark:bg-zinc-900">
        {renderError ? (
          <code className="text-sm text-zinc-600 dark:text-zinc-400 break-all">
            {block.latex_expr}
          </code>
        ) : (
          <div
            ref={containerRef}
            className={displayMode ? "overflow-x-auto py-1" : "inline"}
          />
        )}
      </div>

      {/* Explanation toggle */}
      <div className="border-t border-zinc-200 dark:border-zinc-700">
        {block.explanation ? (
          <>
            <button
              onClick={() => setShowExplanation((v) => !v)}
              className="w-full px-4 py-2 text-left text-sm text-zinc-500 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors flex items-center gap-2"
            >
              <span>{showExplanation ? "▾" : "▸"}</span>
              <span>Explanation</span>
              {block.explanation_model && (
                <span className="ml-auto text-xs text-zinc-400 dark:text-zinc-500">
                  {block.explanation_model}
                </span>
              )}
            </button>
            {showExplanation && (
              <ExplanationPanel explanation={block.explanation} />
            )}
          </>
        ) : (
          <p className="px-4 py-2 text-xs text-zinc-400 dark:text-zinc-600 italic">
            Explanation not yet available
          </p>
        )}
      </div>

      {/* Code toggle (only when feature flag is on and block is implementable) */}
      {flags.SHOW_CODE_TOGGLE && isImplementable(block) && (
        <div className="border-t border-zinc-200 dark:border-zinc-700">
          <div className="flex items-center gap-2 px-4 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
            <button
              onClick={handleCodeToggle}
              className="flex items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400 flex-1 text-left"
            >
              <span>{showCode ? "▾" : "▸"}</span>
              <span>Code</span>
              {codeState === "loading" && (
                <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-ping ml-1 opacity-75" />
              )}
            </button>

            {/* Library picker */}
            <select
              value={library}
              onChange={(e) => handleLibraryChange(e.target.value as Library)}
              className="text-xs text-zinc-500 dark:text-zinc-400 bg-transparent border border-zinc-200 dark:border-zinc-600 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-400"
              aria-label="Target library"
            >
              {LIBRARIES.map((lib) => (
                <option key={lib} value={lib}>
                  {lib}
                </option>
              ))}
            </select>
          </div>

          {showCode && (
            <>
              {codeState === "loading" && (
                <div className="px-4 py-4 flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="inline-block w-3 h-3 rounded-full bg-blue-500 animate-ping opacity-75" />
                  Generating {library} implementation… this may take 30–90s
                </div>
              )}
              {codeState === "not_implementable" && (
                <p className="px-4 py-3 text-xs text-zinc-500 dark:text-zinc-400 italic">
                  This formula defines notation rather than computing a value — no runnable implementation available.
                </p>
              )}
              {codeState === "error" && (
                <p className="px-4 py-3 text-xs text-red-600 bg-red-50 dark:bg-red-950">
                  {codeError ?? "Code generation failed. Try again."}
                </p>
              )}
              {codeState === "ready" && codeData && (
                <CodePanel
                  sections={codeSections}
                  functionName={codeData.function_name ?? ""}
                  generatedModel={codeData.generated_model ?? null}
                  artifact={flags.SHOW_REVIEW_UI ? {
                    block_id: block.id,
                    library,
                    function_name: codeData.function_name,
                    imports: codeData.imports,
                    code: codeData.code,
                    example_usage: codeData.example_usage,
                    test_code: codeData.test_code,
                    parameters: codeData.parameters,
                    notes: codeData.notes,
                    generated_model: codeData.generated_model,
                  } satisfies CodeArtifactForSave : undefined}
                />
              )}
            </>
          )}
        </div>
      )}

      {/* Visualize toggle (ManimGL-generated diagrams) */}
      {flags.SHOW_VISUALIZE && block.explanation && (
        <div className="border-t border-zinc-200 dark:border-zinc-700">
          <div className="flex items-center gap-2 px-4 py-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
            <button
              onClick={handleVizToggle}
              className="flex items-center gap-1.5 text-sm text-zinc-500 dark:text-zinc-400 flex-1 text-left"
            >
              <span>{showViz ? "▾" : "▸"}</span>
              <span>Visualize</span>
              {vizState === "loading" && (
                <span className="inline-block w-2 h-2 rounded-full bg-purple-500 animate-ping ml-1 opacity-75" />
              )}
            </button>

            {/* Mode picker: Static vs Animated */}
            <select
              value={vizMode}
              onChange={(e) => handleVizModeChange(e.target.value as VizMode)}
              className="text-xs text-zinc-500 dark:text-zinc-400 bg-transparent border border-zinc-200 dark:border-zinc-600 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-purple-400"
              aria-label="Visualization mode"
            >
              <option value="static">Static</option>
              <option value="animated">Animated</option>
            </select>
          </div>

          {showViz && (
            <div className="bg-white dark:bg-zinc-950">
              {(vizState === "loading" || vizState === "saving") && (
                <div className="px-4 py-4 flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                  <span className="inline-block w-3 h-3 rounded-full bg-purple-500 animate-ping opacity-75" />
                  {vizState === "saving"
                    ? "Saving…"
                    : `Generating ${vizMode === "animated" ? "animation" : "diagram"}… this may take 30–60s on first load`}
                </div>
              )}
              {vizState === "error" && (
                <div className="px-4 py-3">
                  <p className="text-xs text-red-600 dark:text-red-400">
                    {vizError ?? "Visualization failed. Try again."}
                  </p>
                  {vizCode && (
                    <details className="mt-2">
                      <summary className="text-xs text-zinc-400 cursor-pointer">
                        Show generated ManimGL code
                      </summary>
                      <pre className="mt-1 text-xs text-zinc-500 overflow-x-auto p-2 bg-zinc-50 dark:bg-zinc-900 rounded">
                        {vizCode}
                      </pre>
                    </details>
                  )}
                </div>
              )}
              {vizState === "ready" && (
                <div className="px-4 py-3">
                  {/* Show image: base64 preview OR saved URL */}
                  {vizImageData && !vizSaved && (
                    <img
                      src={`data:${vizContentType ?? "image/png"};base64,${vizImageData}`}
                      alt={vizMode === "animated" ? "Math animation preview" : "Math visualization preview"}
                      className="max-w-full rounded border border-zinc-200 dark:border-zinc-700"
                    />
                  )}
                  {vizUrl && vizSaved && (
                    <img
                      src={vizUrl}
                      alt={vizMode === "animated" ? "Math animation" : "Math visualization"}
                      className="max-w-full rounded border border-zinc-200 dark:border-zinc-700"
                    />
                  )}

                  {/* Save button — only shown for unsaved previews */}
                  {!vizSaved && vizImageData && (
                    <button
                      onClick={handleVizSave}
                      className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-white bg-purple-600 hover:bg-purple-700 rounded transition-colors"
                    >
                      Save
                    </button>
                  )}
                  {vizSaved && (
                    <span className="mt-2 inline-block text-xs text-green-600 dark:text-green-400">
                      ✓ Saved
                    </span>
                  )}

                  {vizCode && (
                    <details className="mt-2">
                      <summary className="text-xs text-zinc-400 cursor-pointer">
                        Show ManimGL code
                      </summary>
                      <pre className="mt-1 text-xs text-zinc-500 overflow-x-auto p-2 bg-zinc-50 dark:bg-zinc-900 rounded">
                        {vizCode}
                      </pre>
                    </details>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

type ExplanationV2 = {
  what_it_computes?: string;
  symbol_meanings?: string;
  derivation?: string;
  intuition?: string;
  proof_role?: string;
  prerequisites?: string;
  mathematical_significance?: string;
  paper_relevance?: string; // legacy key — kept for backward compat
};

function ExplanationPanel({ explanation }: { explanation: string }) {
  // Explanation is a JSON string from DSPy structured output
  let parsed: ExplanationV2 | null = null;
  try {
    parsed = JSON.parse(explanation);
  } catch {
    // plain text fallback
  }

  if (parsed) {
    const hasFields = !!(
      parsed.what_it_computes ||
      parsed.symbol_meanings ||
      parsed.derivation ||
      parsed.intuition ||
      parsed.proof_role ||
      parsed.prerequisites ||
      parsed.mathematical_significance ||
      parsed.paper_relevance
    );

    if (!hasFields) {
      return (
        <p className="px-4 py-3 text-sm text-zinc-400 dark:text-zinc-500 italic bg-white dark:bg-zinc-950">
          Explanation data is empty — the paper may need re-processing.
        </p>
      );
    }

    return (
      <dl className="px-4 py-3 space-y-2 text-sm bg-white dark:bg-zinc-950">
        {parsed.what_it_computes && (
          <ExplanationRow label="What it computes" value={parsed.what_it_computes} />
        )}
        {parsed.symbol_meanings && (
          <ExplanationRow label="Symbols" value={parsed.symbol_meanings} />
        )}
        {parsed.derivation && (
          <ExplanationRow label="Derivation" value={parsed.derivation} />
        )}
        {parsed.intuition && (
          <ExplanationRow label="Intuition" value={parsed.intuition} />
        )}
        {parsed.proof_role && (
          <ExplanationRow label="Role in proof" value={parsed.proof_role} />
        )}
        {parsed.prerequisites && (
          <ExplanationRow label="Prerequisites" value={parsed.prerequisites} />
        )}
        {(parsed.mathematical_significance ?? parsed.paper_relevance) && (
          <ExplanationRow
            label="Why it matters"
            value={(parsed.mathematical_significance ?? parsed.paper_relevance)!}
          />
        )}
      </dl>
    );
  }

  return (
    <p className="px-4 py-3 text-sm text-zinc-700 dark:text-zinc-300 bg-white dark:bg-zinc-950">
      <ProseWithMath text={explanation} />
    </p>
  );
}

function ExplanationRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-medium text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className="mt-0.5 text-zinc-700 dark:text-zinc-300 leading-relaxed">
        <ProseWithMath text={value} />
      </dd>
    </div>
  );
}
