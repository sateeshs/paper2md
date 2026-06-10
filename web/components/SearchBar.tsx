"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTransition, useState, useEffect, useRef } from "react";

interface Suggestion {
  id: string;
  arxiv_id: string | null;
  title: string;
  authors: string[];
}

export function SearchBar() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [isPending, startTransition] = useTransition();
  const [value, setValue] = useState(searchParams.get("q") ?? "");
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(-1);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Fetch suggestions on input change (debounced 250ms)
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (value.trim().length < 2) {
      setSuggestions([]);
      setOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(value.trim())}`);
        const data: Suggestion[] = await res.json();
        setSuggestions(data);
        setOpen(data.length > 0);
        setActiveIdx(-1);
      } catch {
        setSuggestions([]);
      }
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [value]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function navigate(q: string) {
    setOpen(false);
    startTransition(() => {
      router.push(q ? `/?q=${encodeURIComponent(q)}` : "/");
    });
  }

  function selectSuggestion(s: Suggestion) {
    setValue(s.title);
    setOpen(false);
    if (s.arxiv_id) {
      router.push(`/paper/${s.arxiv_id}`);
    } else {
      navigate(s.title);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, -1));
    } else if (e.key === "Enter" && activeIdx >= 0) {
      e.preventDefault();
      selectSuggestion(suggestions[activeIdx]);
    } else if (e.key === "Escape") {
      setOpen(false);
      setActiveIdx(-1);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    navigate(value.trim());
  }

  return (
    <div ref={containerRef} className="relative w-full">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="search"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => suggestions.length > 0 && setOpen(true)}
          placeholder="Search papers by title…"
          autoComplete="off"
          className="flex-1 rounded-lg border border-zinc-300 bg-white px-4 py-2.5 text-sm shadow-sm placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          aria-autocomplete="list"
          aria-expanded={open}
        />
        <button
          type="submit"
          disabled={isPending}
          className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 transition-colors"
        >
          {isPending ? "…" : "Search"}
        </button>
      </form>

      {/* Dropdown */}
      {open && (
        <ul
          role="listbox"
          className="absolute z-20 mt-1.5 w-full bg-white rounded-xl border border-zinc-200 shadow-lg overflow-hidden"
        >
          {suggestions.map((s, i) => (
            <li
              key={s.id}
              role="option"
              aria-selected={i === activeIdx}
              onMouseDown={() => selectSuggestion(s)}
              onMouseEnter={() => setActiveIdx(i)}
              className={`px-4 py-3 cursor-pointer flex items-start gap-3 ${
                i === activeIdx ? "bg-blue-50" : "hover:bg-zinc-50"
              }`}
            >
              <span className="text-zinc-300 mt-0.5 shrink-0 text-xs">📄</span>
              <div className="min-w-0">
                <p className={`text-sm font-medium truncate ${i === activeIdx ? "text-blue-700" : "text-zinc-900"}`}>
                  {s.title}
                </p>
                <div className="flex items-center gap-2 mt-0.5 text-xs text-zinc-400">
                  {s.arxiv_id && <span>arXiv:{s.arxiv_id}</span>}
                  {s.authors.length > 0 && <span>{s.authors.join(", ")}</span>}
                </div>
              </div>
            </li>
          ))}
          <li
            onMouseDown={() => navigate(value.trim())}
            className="px-4 py-2.5 border-t border-zinc-100 cursor-pointer hover:bg-zinc-50 text-xs text-zinc-400 flex items-center gap-2"
          >
            <span>🔍</span>
            <span>Search for <span className="font-medium text-zinc-600">"{value}"</span></span>
          </li>
        </ul>
      )}
    </div>
  );
}
