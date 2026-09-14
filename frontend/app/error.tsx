"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) { return <div className="page"><div className="card empty"><h3>Something went wrong</h3><p>The console could not render this view. Chain state has not been changed.</p><button className="button ghost" onClick={reset}>Try again</button></div></div>; }
