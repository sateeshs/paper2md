interface ExplanationsInProgressProps {
  status: string | null | undefined;
}

/** Notice shown while a readable paper's math explanations are still being generated. */
export function ExplanationsInProgress({ status }: ExplanationsInProgressProps) {
  if (status !== "explaining") return null;
  return (
    <p
      role="status"
      className="my-3 flex items-start gap-2 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-sm text-indigo-800 dark:border-indigo-800/50 dark:bg-indigo-950/40 dark:text-indigo-200"
    >
      <span aria-hidden className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-indigo-500 animate-pulse" />
      <span>
        <span className="font-medium">Explanations in progress.</span> Equations are
        readable now; their step-by-step explanations are still being generated and
        appear as each one finishes.
      </span>
    </p>
  );
}
