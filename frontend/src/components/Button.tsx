"use client";

import { type ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  loading?: boolean;
  size?: "sm" | "md" | "lg";
}

const variantClasses: Record<Variant, string> = {
  primary: "btn-neon font-semibold",
  secondary: "btn-ghost-neon font-medium",
  ghost:
    "bg-transparent text-muted hover:text-accent border border-transparent hover:bg-surface/50",
  danger:
    "bg-error/10 text-error border border-error/40 hover:bg-error/20 font-medium",
};

const sizeClasses = {
  sm: "h-8 px-3.5 text-xs gap-1.5 rounded-[var(--radius-sm)]",
  md: "h-10 px-5 text-sm gap-2 rounded-[var(--radius-md)]",
  lg: "h-12 px-7 text-sm gap-2.5 rounded-[var(--radius-md)]",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    {
      variant = "primary",
      loading = false,
      size = "md",
      className = "",
      disabled,
      children,
      ...props
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={[
          "inline-flex items-center justify-center transition-all duration-200",
          "disabled:opacity-40 disabled:pointer-events-none",
          variantClasses[variant],
          sizeClasses[size],
          className,
        ].join(" ")}
        {...props}
      >
        {loading ? (
          <span
            className="size-4 rounded-full border-2 border-current border-t-transparent animate-spin"
            aria-hidden
          />
        ) : null}
        {children}
      </button>
    );
  },
);
