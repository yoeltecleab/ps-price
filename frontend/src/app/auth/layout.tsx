import { Suspense } from "react";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense
      fallback={
        <div className="max-w-md mx-auto holo-panel-strong rounded-[var(--radius-xl)] p-8 text-center text-muted">
          Loading…
        </div>
      }
    >
      {children}
    </Suspense>
  );
}
