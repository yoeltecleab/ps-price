import { type InputHTMLAttributes, forwardRef } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, className = "", id, ...props },
  ref,
) {
  const inputId = id ?? (label ? label.toLowerCase().replace(/\s+/g, "-") : undefined);

  return (
    <div className="flex flex-col gap-1.5">
      {label ? (
        <label htmlFor={inputId} className="text-sm font-medium text-ink">
          {label}
        </label>
      ) : null}
      <input
        ref={ref}
        id={inputId}
        className={[
          "h-10 w-full rounded-[var(--radius-sm)] bg-surface border px-3 text-sm text-ink placeholder:text-muted",
          error ? "border-error" : "border-border",
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/50",
          className,
        ].join(" ")}
        {...props}
      />
      {error ? (
        <p className="text-xs text-error" role="alert">{error}</p>
      ) : hint ? (
        <p className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  );
});
