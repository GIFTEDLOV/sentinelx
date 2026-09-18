/*
 * Local managed-signer adapter.  keytar reads the already-unlocked OS
 * keychain entry and passes the key only through the child process environment
 * to the stable Python bridge.  It never prints or persists the key.
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
  [process.env.SENTINELX_PYTHON_SCRIPT ?? "scripts/studionet_stable_profile.py"],
  {
    cwd: process.cwd(),
    env: {
      ...process.env,
      SENTINELX_EPHEMERAL_PRIVATE_KEY: privateKey,
      SENTINELX_STUDIONET_PROFILE_STATE: process.env.SENTINELX_STUDIONET_PROFILE_STATE ?? "studionet-v23-profile-r1",
    },
    stdio: "inherit",
    windowsHide: true,
  },
);
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
