import { NextRequest } from "next/server";

const STUDIONET_RPC = "https://studio.genlayer.com/api";
const READ_METHODS = new Set([
  "eth_chainId",
  "eth_blockNumber",
  "eth_estimateGas",
  "eth_getTransactionByHash",
  "gen_call",
]);

export async function POST(request: NextRequest): Promise<Response> {
  let payload: { id?: unknown; jsonrpc?: unknown; method?: unknown; params?: unknown[] };
  try {
    payload = await request.json() as typeof payload;
  } catch {
    return Response.json({ jsonrpc: "2.0", id: null, error: { code: -32700, message: "Invalid JSON" } }, { status: 400 });
  }

  if (payload.jsonrpc !== "2.0" || typeof payload.method !== "string" || !READ_METHODS.has(payload.method)) {
    return Response.json({ jsonrpc: "2.0", id: payload.id ?? null, error: { code: -32601, message: "Only stable Studionet read methods are proxied" } }, { status: 405 });
  }

  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      const upstream = await fetch(STUDIONET_RPC, {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json" },
        body: JSON.stringify(payload),
        cache: "no-store",
      });
      const body = await upstream.text();
      if (upstream.ok || attempt === 2) {
        return new Response(body, {
          status: upstream.status,
          headers: { "content-type": upstream.headers.get("content-type") || "application/json" },
        });
      }
    } catch {
      if (attempt === 2) break;
    }
    await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
  }

  return Response.json({ jsonrpc: "2.0", id: payload.id ?? null, error: { code: -32000, message: "Studionet RPC unavailable" } }, { status: 502 });
}
