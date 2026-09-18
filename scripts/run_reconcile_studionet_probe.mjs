/* Managed-signer adapter for exact-hash diagnostic reconciliation. */
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

const keytarModule = await import(pathToFileURL(
  "C:/Users/DELL/AppData/Roaming/npm/node_modules/genlayer/node_modules/keytar/lib/keytar.js",
).href);
const keytar = keytarModule.default ?? keytarModule;
const privateKey = await keytar.getPassword("genlayer-cli", "account:meritround-v2-studionet");
if (!privateKey) process.exit(2);
const child = spawn(".venv/Scripts/python.exe", ["scripts/reconcile_studionet_probe.py"], {
  cwd: process.cwd(),
  env: { ...process.env, SENTINELX_EPHEMERAL_PRIVATE_KEY: privateKey },
  stdio: "inherit",
  windowsHide: true,
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
