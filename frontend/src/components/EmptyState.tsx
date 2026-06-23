import Link from "next/link";
import type { Icon as PhosphorIcon } from "@phosphor-icons/react";

export function EmptyState({
  icon: IconComponent,
  title,
  description,
  actionLabel,
  actionHref,
}: {
  icon: PhosphorIcon;
  title: string;
  description: string;
  actionLabel?: string;
  actionHref?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-20 px-6 text-center">
      <div className="relative flex size-16 items-center justify-center mb-6">
        <div className="absolute inset-0 rounded-full bg-primary/20 blur-xl" />
        <div className="relative flex size-16 items-center justify-center rounded-[var(--radius-xl)] holo-panel border border-border-bright">
          <IconComponent className="size-7 text-accent" weight="duotone" aria-hidden />
        </div>
      </div>
      <h2 className="font-display text-xl font-bold text-ink">{title}</h2>
      <p className="mt-3 text-sm text-muted max-w-sm text-pretty leading-relaxed">
        {description}
      </p>
      {actionLabel && actionHref ? (
        <Link
          href={actionHref}
          className="mt-8 inline-flex h-11 items-center px-6 rounded-[var(--radius-md)] btn-neon text-sm font-semibold"
        >
          {actionLabel}
        </Link>
      ) : null}
    </div>
  );
}
