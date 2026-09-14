import Link from "next/link";

export default function NotFound() { return <div className="page"><div className="card empty"><h3>Page not found</h3><p>This SentinelX route does not exist.</p><Link className="button ghost" href="/app">Return to overview</Link></div></div>; }
