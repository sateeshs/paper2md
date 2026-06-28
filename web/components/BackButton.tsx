"use client";

import { useRouter } from "next/navigation";

interface BackButtonProps {
  fallbackHref: string;
  label: string;
  className?: string;
}

export function BackButton({ fallbackHref, label, className }: BackButtonProps) {
  const router = useRouter();

  function handleClick(e: React.MouseEvent<HTMLAnchorElement>) {
    // If there's browser history to go back to, use it (preserves scroll + client state).
    // Otherwise fall through to the href.
    if (window.history.length > 1) {
      e.preventDefault();
      router.back();
    }
  }

  return (
    <a href={fallbackHref} onClick={handleClick} className={className}>
      {label}
    </a>
  );
}
