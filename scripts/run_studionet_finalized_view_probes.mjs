/*
 * Managed-signer adapter for the disposable finalized-view probes.
 * The private key is read from the existing OS keychain and passed only to
 * the child process environment; it is never printed or written by this file.
 */
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

const keytarModule = await import(pathToFileURL(
  "C:/Users/DELL/AppData/Roaming/npm/node_modules/genlayer/node_modules/keytar/lib/keytar.js",
).href);
const keytar = keytarModule.default ?? keytarModule;
const privateKey = await keytar.getPassword("genlayer-cli", "account:meritround-v2-studionet");
if (!privateKey) {
  console.error("The managed Studionet account is not unlocked in the OS keychain.");
  process.exit(2);
}

const child = spawn(
  ".venv/Scripts/python.exe",
  ["scripts/studionet_finalized_view_probes.py"],
  {
    cwd: process.cwd(),
    env: {
      ...process.env,
      SENTINELX_EPHEMERAL_PRIVATE_KEY: privateKey,
      SENTINELX_STUDIONET_PROFILE_STATE: process.env.SENTINELX_STUDIONET_PROFILE_STATE ?? "studionet-finalized-view-probes-r1",
    },
    stdio: "inherit",
    windowsHide: true,
  },
);
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
