export function Skeleton({
  className = "",
}: {
  className?: string;
}) {
  return (
    <div
      className={["skeleton rounded-[var(--radius-md)]", className].join(" ")}
      aria-hidden
    />
  );
}

export function GameCardSkeleton() {
  return (
    <div className="flex gap-4 p-4 rounded-[var(--radius-lg)] bg-surface border border-border">
      <Skeleton className="size-20 shrink-0" />
      <div className="flex-1 flex flex-col gap-2 min-w-0">
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-4 w-1/2 mt-2" />
        <Skeleton className="h-6 w-24 mt-3" />
      </div>
    </div>
  );
}
