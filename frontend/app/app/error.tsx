"use client";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <div className="page"><div className="card empty"><h1>Chain data unavailable</h1><p>This panel could not load its finalized data. The rest of the SentinelX console remains available.</p><button className="button ghost" onClick={reset}>Retry panel</button></div></div>;
}
