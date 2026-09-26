#!/usr/bin/env node
// Software-factory profile commands for keel (django-next).
//
// Every command is slot-aware: FACTORY_SLOT (0-9, default 0) picks a port
// block (default port + slot*100) and a compose project (keel-s<slot>), so
// parallel git worktrees never share containers, volumes or ports.
//
//   node scripts/factory/factory.mjs <command> [args]
//
//   env         write .env + apps/web/.env.local for this slot
//   env:up      env, then start this slot's compose stack and wait healthy
//   env:down    stop this slot's stack and delete its volumes
//   env:reset   env:down, env:up, build emails, migrate, seed_demo
//   dev         run api + stream + celery worker + web on this slot's ports
//   health      exit 0 when api /readyz/ and web both answer
//   e2e [args]  run Playwright against this slot (starts dev if not up)
//   ports       print this slot's port map as JSON
//
// Slot 0 reproduces the historical ports (web 3000, api 8000, pg 5433...).
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdirSync, openSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const MARKER = "# managed-by: scripts/factory/factory.mjs";
const IS_WINDOWS = process.platform === "win32";

const BASE_PORTS = {
  WEB_PORT: 3000,
  API_PORT: 8000,
  STREAM_PORT: 8001,
  PG_PORT: 5433,
  REDIS_PORT: 6379,
  MAILPIT_SMTP_PORT: 1025,
  MAILPIT_UI_PORT: 8025,
  MINIO_PORT: 9000,
  MINIO_CONSOLE_PORT: 9001,
};

/** FACTORY_SLOT from the environment, else the slot the managed .env was
 * written for (so plain `pnpm e2e` in a worktree stays on its slot), else 0. */
function slot() {
  const raw = process.env.FACTORY_SLOT ?? fileSlot() ?? "0";
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 0 || value > 9) {
    fail(`FACTORY_SLOT must be an integer 0-9, got "${raw}"`);
  }
  return value;
}

function ports(s = slot()) {
  return Object.fromEntries(Object.entries(BASE_PORTS).map(([k, v]) => [k, v + s * 100]));
}

function fail(message) {
  console.error(`factory: ${message}`);
  process.exit(1);
}

// ---------------------------------------------------------------- env files

function slotVars(s) {
  const p = ports(s);
  return {
    FACTORY_SLOT: String(s),
    KEEL_COMPOSE_SUFFIX: `s${s}`,
    ...Object.fromEntries(Object.entries(p).map(([k, v]) => [k, String(v)])),
    E2E_WEB_PORT: String(p.WEB_PORT),
    E2E_BASE_URL: `http://lvh.me:${p.WEB_PORT}`,
    E2E_LVH_BASE_URL: `http://lvh.me:${p.WEB_PORT}`,
    E2E_API_URL: `http://localhost:${p.API_PORT}`,
    E2E_API_LVH_URL: `http://api.lvh.me:${p.API_PORT}`,
    E2E_MAILPIT_URL: `http://localhost:${p.MAILPIT_UI_PORT}`,
  };
}

/** .env.example with every default port rewritten to this slot's port. */
function renderRootEnv(s) {
  const p = ports(s);
  const remap = new Map(Object.entries(BASE_PORTS).map(([k, v]) => [String(v), String(p[k])]));
  const example = readFileSync(join(ROOT, ".env.example"), "utf8");
  const body = example
    .split(/\r?\n/)
    .map((line) =>
      /^[A-Z0-9_]+=/.test(line)
        ? line
            // host:port inside URLs, and bare port values such as EMAIL_PORT=1025
            .replace(/:(\d{4})\b/g, (m, port) => (remap.has(port) ? `:${remap.get(port)}` : m))
            .replace(/=(\d{4})$/, (m, port) => (remap.has(port) ? `=${remap.get(port)}` : m))
        : line,
    )
    .join("\n");
  const extra = Object.entries(slotVars(s))
    .map(([k, v]) => `${k}=${v}`)
    .join("\n");
  return `${MARKER} (slot ${s}); regenerate with \`pnpm env:up\`, do not hand-edit.\n${body}\n\n# --- factory slot ${s} ---\n${extra}\n`;
}

/** Next.js only reads apps/web/.env*, never the repo-root .env. */
function renderWebEnv(rootEnv) {
  const wanted = /^(NEXT_PUBLIC_[A-Z0-9_]*|KEEL_API_INTERNAL_URL|KEEL_API_STREAM_INTERNAL_URL)=/;
  const lines = rootEnv.split("\n").filter((line) => wanted.test(line));
  return `${MARKER}\n${lines.join("\n")}\n`;
}

function writeManaged(path, content) {
  if (existsSync(path) && !readFileSync(path, "utf8").startsWith(MARKER)) {
    fail(
      `${path} exists and was not written by the factory; move it aside (it is probably a hand-made dev .env) and re-run`,
    );
  }
  writeFileSync(path, content);
}

function cmdEnv() {
  const s = slot();
  const rootEnv = renderRootEnv(s);
  writeManaged(join(ROOT, ".env"), rootEnv);
  writeManaged(join(ROOT, "apps/web/.env.local"), renderWebEnv(rootEnv));
  console.log(`factory: wrote .env and apps/web/.env.local for slot ${s}`);
}

function fileSlot() {
  const path = join(ROOT, ".env");
  if (!existsSync(path)) return undefined;
  const text = readFileSync(path, "utf8");
  if (!text.startsWith(MARKER)) return undefined;
  return /^FACTORY_SLOT=(\d)$/m.exec(text)?.[1];
}

function envFromFile() {
  const path = join(ROOT, ".env");
  if (fileSlot() !== String(slot())) cmdEnv();
  const vars = {};
  for (const line of readFileSync(path, "utf8").split(/\r?\n/)) {
    const m = /^([A-Z0-9_]+)=(.*)$/.exec(line);
    if (m) vars[m[1]] = m[2];
  }
  return { ...process.env, ...vars };
}

// ------------------------------------------------------------- processes

// Windows needs a shell to resolve pnpm/uv shims (.cmd). Node deprecates
// passing an args array alongside shell:true, so build one quoted string.
function shellArgs(cmd, args) {
  if (!IS_WINDOWS) return [cmd, args, false];
  const quote = (a) => (/[\s"&|<>^]/.test(a) ? `"${a.replace(/"/g, '\\"')}"` : a);
  return [[cmd, ...args].map(quote).join(" "), [], true];
}

function run(cmd, args, opts = {}) {
  const [c, a, shell] = shellArgs(cmd, args);
  const res = spawnSync(c, a, {
    cwd: opts.cwd ?? ROOT,
    env: opts.env ?? envFromFile(),
    stdio: "inherit",
    shell,
  });
  if (res.status !== 0 && !opts.allowFail) {
    fail(`\`${cmd} ${args.join(" ")}\` exited ${res.status}`);
  }
  return res.status ?? 1;
}

function compose(args, opts) {
  return run(
    "docker",
    ["compose", "-f", "infra/compose.dev.yml", "--env-file", ".env", ...args],
    opts,
  );
}

function killTree(child) {
  if (!child.pid || child.exitCode !== null) return;
  if (IS_WINDOWS)
    spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch {
      child.kill("SIGTERM");
    }
  }
}

/** With `logPath`, every process writes straight to that file (used by e2e,
 * whose Playwright run would otherwise leave piped output undrained and
 * stall the servers once their pipe buffers fill). Without it, output is
 * prefixed and streamed to this terminal. */
function devProcesses(env, logPath) {
  const p = ports();
  const logFd = logPath ? openSync(logPath, "a") : undefined;
  return [
    ["api", "uv", ["run", "python", "manage.py", "runserver", `0.0.0.0:${p.API_PORT}`], "apps/api"],
    [
      "stream",
      "uv",
      [
        "run",
        "uvicorn",
        "config.asgi_stream:application",
        "--host",
        "0.0.0.0",
        "--port",
        String(p.STREAM_PORT),
      ],
      "apps/api",
    ],
    [
      "worker",
      "uv",
      [
        "run",
        "celery",
        "-A",
        "config",
        "worker",
        "-Q",
        "default,email,external,scheduled",
        "-l",
        "info",
        ...(IS_WINDOWS ? ["-P", "solo"] : []),
      ],
      "apps/api",
    ],
    ["web", "pnpm", ["exec", "next", "dev", "-p", String(p.WEB_PORT)], "apps/web"],
  ].map(([name, cmd, args, cwd]) => {
    const [c, a, shell] = shellArgs(cmd, args);
    const child = spawn(c, a, {
      cwd: join(ROOT, cwd),
      env,
      shell,
      detached: !IS_WINDOWS,
      stdio: logFd === undefined ? ["ignore", "pipe", "pipe"] : ["ignore", logFd, logFd],
    });
    if (logFd !== undefined) return child;
    const prefix = `[${name}] `;
    for (const stream of [child.stdout, child.stderr]) {
      stream.on("data", (chunk) => {
        for (const line of String(chunk).split(/\r?\n/))
          if (line) process.stdout.write(prefix + line + "\n");
      });
    }
    return child;
  });
}

function cmdDev() {
  const env = envFromFile();
  const p = ports();
  console.log(
    `factory: slot ${slot()} -> web http://lvh.me:${p.WEB_PORT}  api http://api.lvh.me:${p.API_PORT}  mail http://localhost:${p.MAILPIT_UI_PORT}`,
  );
  const children = devProcesses(env);
  const stop = () => {
    children.forEach(killTree);
    process.exit(0);
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
  for (const child of children)
    child.on("exit", (code) => code && console.error(`factory: a dev process exited ${code}`));
}

// ---------------------------------------------------------------- health

async function probe(url) {
  try {
    const res = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(5000) });
    return res.status < 500;
  } catch {
    return false;
  }
}

async function healthy() {
  const p = ports();
  const [api, web] = await Promise.all([
    probe(`http://localhost:${p.API_PORT}/readyz/`),
    probe(`http://localhost:${p.WEB_PORT}/`),
  ]);
  return { slot: slot(), api, web, ok: api && web };
}

async function cmdHealth() {
  const result = await healthy();
  console.log(JSON.stringify(result));
  process.exit(result.ok ? 0 : 1);
}

// ------------------------------------------------------------------- e2e

async function cmdE2e(args) {
  const env = envFromFile();
  let started = [];
  if (!(await healthy()).ok) {
    mkdirSync(join(ROOT, ".factory"), { recursive: true });
    const logPath = join(ROOT, ".factory", `dev-slot${slot()}.log`);
    console.log(`factory: slot not serving; starting dev processes (log: ${logPath})`);
    started = devProcesses(env, logPath);
    const deadline = Date.now() + 240_000;
    while (!(await healthy()).ok) {
      if (Date.now() > deadline) {
        started.forEach(killTree);
        fail("dev processes did not become healthy within 240s");
      }
      await new Promise((r) => setTimeout(r, 2000));
    }
  }
  // One worker by default: runserver + `next dev` on a dev machine drop
  // requests under Playwright's default parallelism (auth-flows specs time
  // out). E2E_WORKERS or an explicit --workers overrides it.
  const workers = args.some((a) => a.startsWith("--workers"))
    ? []
    : [`--workers=${process.env.E2E_WORKERS ?? "1"}`];
  const status = run("pnpm", ["exec", "playwright", "test", ...workers, ...args], {
    cwd: join(ROOT, "apps/web"),
    env,
    allowFail: true,
  });
  started.forEach(killTree);
  process.exit(status);
}

// -------------------------------------------------------------- dispatch

const [command, ...rest] = process.argv.slice(2);
switch (command) {
  case "env":
    cmdEnv();
    break;
  case "env:up":
    cmdEnv();
    compose(["up", "-d", "--wait"]);
    break;
  case "env:down":
    if (existsSync(join(ROOT, ".env"))) compose(["down", "-v", "--remove-orphans"]);
    break;
  case "env:reset":
    cmdEnv();
    compose(["down", "-v", "--remove-orphans"]);
    compose(["up", "-d", "--wait"]);
    run("pnpm", ["--filter", "@keel/emails", "build"]);
    run("uv", ["run", "python", "manage.py", "migrate", "--noinput"], {
      cwd: join(ROOT, "apps/api"),
    });
    run("uv", ["run", "python", "manage.py", "seed_demo"], { cwd: join(ROOT, "apps/api") });
    break;
  case "dev":
    cmdDev();
    break;
  case "health":
    await cmdHealth();
    break;
  case "e2e":
    await cmdE2e(rest);
    break;
  case "ports":
    console.log(JSON.stringify({ slot: slot(), ...ports() }));
    break;
  default:
    fail(`unknown command "${command ?? ""}"; see the header of scripts/factory/factory.mjs`);
}
