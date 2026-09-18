/* Managed-signer adapter for the fresh baseline diagnostic caller run. */
import { spawn } from "node:child_process";
import { pathToFileURL } from "node:url";

const keytarModule = await import(pathToFileURL(
  "C:/Users/DELL/AppData/Roaming/npm/node_modules/genlayer/node_modules/keytar/lib/keytar.js",
).href);
const keytar = keytarModule.default ?? keytarModule;
const privateKey = await keytar.getPassword("genlayer-cli", "account:meritround-v2-studionet");
if (!privateKey) process.exit(2);
const child = spawn(".venv/Scripts/python.exe", ["scripts/studionet_baseline_view_probes.py"], {
  cwd: process.cwd(),
  env: {
    ...process.env,
    SENTINELX_EPHEMERAL_PRIVATE_KEY: privateKey,
    SENTINELX_STUDIONET_PROFILE_STATE: process.env.SENTINELX_STUDIONET_PROFILE_STATE ?? "studionet-baseline-view-probes-r1",
  },
  stdio: "inherit",
  windowsHide: true,
});
child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 1);
});
