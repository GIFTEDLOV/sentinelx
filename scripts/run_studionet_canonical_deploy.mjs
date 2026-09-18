/*
 * Canonical managed-signer adapter.  The OS-keychain secret is passed only
 * through the child environment and is never printed or persisted.
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
  ["scripts/studionet_canonical_deploy.py"],
  {
    cwd: process.cwd(),
    env: {
      ...process.env,
      SENTINELX_EPHEMERAL_PRIVATE_KEY: privateKey,
      SENTINELX_STUDIONET_PROFILE_STATE: "studionet-v23-canonical-r1",
      SENTINELX_STUDIONET_SOURCE_REVISION: "cfb25215497adeb41357196caa8c755a685b4cf2",
    },
    stdio: "inherit",
    windowsHide: true,
  },
);
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
