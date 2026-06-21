/**
 * PrerequisitesPanel — Server Component.
 *
 * Displays a collapsible badge grid of prerequisite concepts aggregated
 * from all math block explanations in a section.
 *
 * Uses native <details>/<summary> for zero-JS toggle — no client bundle cost.
 */

interface PrerequisitesPanelProps {
  prerequisites: string[];
}

export function PrerequisitesPanel({ prerequisites }: PrerequisitesPanelProps) {
  if (prerequisites.length === 0) return null;

  return (
    <details className="group mb-6 rounded-lg border border-blue-200 dark:border-blue-800 bg-blue-50 dark:bg-blue-950/40 overflow-hidden">
      <summary className="flex cursor-pointer items-center justify-between px-4 py-3 select-none list-none">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-blue-800 dark:text-blue-200">
            Prerequisites for this section
          </span>
          <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-900 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-700">
            {prerequisites.length}
          </span>
        </div>
        {/* Chevron rotates when open — pure CSS via group-open */}
        <svg
          className="h-4 w-4 text-blue-500 transition-transform duration-200 group-open:rotate-180"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </summary>

      <div className="px-4 pb-4 pt-2 border-t border-blue-200 dark:border-blue-800">
        <p className="text-xs text-blue-600 dark:text-blue-400 mb-3">
          Concepts you should know before working through the math in this section.
        </p>
        <div className="flex flex-wrap gap-2">
          {prerequisites.map((concept) => (
            <span
              key={concept}
              className="inline-flex items-center rounded-full border border-blue-200 dark:border-blue-700 bg-white dark:bg-blue-900/50 px-3 py-1 text-xs font-medium text-blue-700 dark:text-blue-300"
            >
              {concept}
            </span>
          ))}
        </div>
      </div>
    </details>
  );
}
