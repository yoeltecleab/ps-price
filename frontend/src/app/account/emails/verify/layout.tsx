import { Suspense } from "react";
import VerifyNotificationEmailPage from "./page";

export default function VerifyNotificationEmailLayout() {
  return (
    <Suspense fallback={<p className="text-center text-muted py-20">Loading…</p>}>
      <VerifyNotificationEmailPage />
    </Suspense>
  );
}
