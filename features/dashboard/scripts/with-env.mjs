import { spawn } from "node:child_process";

const [name, value, command, ...args] = process.argv.slice(2);
if (!name || value === undefined || !command) {
  console.error("usage: node scripts/with-env.mjs NAME VALUE command [args...]");
  process.exit(1);
}

const child = spawn(command, args, {
  stdio: "inherit",
  shell: process.platform === "win32",
  env: { ...process.env, [name]: value },
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});
