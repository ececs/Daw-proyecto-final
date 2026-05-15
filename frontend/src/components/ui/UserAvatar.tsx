"use client";

import { useState, useEffect } from "react";

interface UserAvatarProps {
  /** The optional avatar URL (e.g. Google Profile, Dicebear seed). */
  src?: string | null;
  /** The user's full name, utilized for generating initials and alt text. */
  name: string;
  /** Visual diameter scaling preset (xs, sm, md, lg). Defaults to 'sm'. */
  size?: "xs" | "sm" | "md" | "lg";
  /** Additional Tailwind class names for layout overrides. */
  className?: string;
}

const SIZE_MAP = {
  xs: "w-5 h-5 text-[10px]",
  sm: "w-7 h-7 text-xs",
  md: "w-10 h-10 text-sm",
  lg: "w-16 h-16 text-xl",
};

/**
 * `UserAvatar` — profile picture with a graceful initials fallback.
 *
 * Renders the supplied `src` (Google avatar, DiceBear, …) and falls
 * back to a coloured circle with the user's first initial when:
 * - `src` is `null` / empty (no avatar URL on the user record), or
 * - the image fails to load (404, blocked, CORS, ad-blocker).
 */
export function UserAvatar({ src, name, size = "sm", className = "" }: UserAvatarProps) {
  const [hasError, setHasError] = useState(false);
  const initials = name ? name.charAt(0).toUpperCase() : "?";

  // Why: a new `src` deserves a fresh attempt; without this, an avatar
  // that failed once would stay broken even after the user updates it.
  useEffect(() => {
    setHasError(false);
  }, [src]);

  const sizeClass = SIZE_MAP[size];

  if (!src || hasError) {
    return (
      <div
        className={`${sizeClass} rounded-full bg-slate-100 flex items-center justify-center font-semibold text-slate-500 border border-slate-200 shrink-0 ${className}`}
        title={name}
      >
        {initials}
      </div>
    );
  }

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt={name}
      referrerPolicy="no-referrer"
      onError={() => setHasError(true)}
      className={`${sizeClass} rounded-full object-cover border border-slate-200 shrink-0 ${className}`}
    />
  );
}
