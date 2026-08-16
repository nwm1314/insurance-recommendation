/**
 * Cross-platform backend launcher for Playwright E2E.
 *
 * Responsibilities (runs as the backend webServer):
 *   1. Run `alembic upgrade head` against an isolated SQLite DB
 *      (data/e2e-backend.db) so the schema gate (TASK-017) is satisfied.
 *   2. Start uvicorn (backend.main:app) from the repo root with a hermetic
 *      environment: e2e admin bootstrap via FIRST_ADMIN_*, raised rate
 *      limits, scheduler disabled and no LLM key (no external services).
 *
 * Python resolution: $E2E_PYTHON (CI) > backend/venv (local) > `python`.
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, '..', '..', '..');
const backendDir = path.join(repoRoot, 'backend');
const isWin = process.platform === 'win32';

const venvPython = path.join(
  backendDir, 'venv', isWin ? 'Scripts/python.exe' : 'bin/python',
);
const python = process.env.E2E_PYTHON || (existsSync(venvPython) ? venvPython : 'python');

const port = Number(process.argv[process.argv.indexOf('--port') + 1]) || 8000;
const dbFile = process.env.E2E_BACKEND_DB || path.join(repoRoot, 'data', 'e2e-backend.db');
const dbUrl = `sqlite:///${dbFile.split(path.sep).join('/')}`;

const env = {
  ...process.env,
  DATABASE_URL: dbUrl,
  FIRST_ADMIN_EMAIL: process.env.E2E_FIRST_ADMIN_EMAIL || 'e2e-admin@e2e-test.com',
  FIRST_ADMIN_PASSWORD: process.env.E2E_FIRST_ADMIN_PASSWORD || 'E2eAdmin!2026',
  RATE_LIMIT_IP_PER_MINUTE: '10000',
  RATE_LIMIT_USER_PER_MINUTE: '10000',
  RATE_LIMIT_USER_PER_DAY: '100000',
  LLM_API_KEY: '',
  DISABLE_SCHEDULER_IN_TESTS: 'true',
  // E2E 需要非空演示目录驱动规则引擎推荐（生产产品池来自真实抓取数据）
  SEED_DEMO_PRODUCTS: 'true',
  AUTO_PUBLISH_ENABLED: 'false',
};

function fail(message) {
  console.error(`[e2e-backend] ${message}`);
  process.exit(1);
}

if (!process.env.E2E_PYTHON && !existsSync(python)) {
  fail(`python not found at ${python}; set E2E_PYTHON (e.g. E2E_PYTHON=python)`);
}

const migration = spawnSync(python, ['-m', 'alembic', 'upgrade', 'head'], {
  cwd: backendDir,
  env,
  encoding: 'utf8',
});
if (migration.status !== 0) {
  fail(`alembic upgrade head failed:\n${migration.stdout}\n${migration.stderr}`);
}

const child = spawn(
  python,
  ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(port)],
  { cwd: repoRoot, env, stdio: 'inherit' },
);

child.on('error', (err) => fail(`uvicorn failed to start: ${err.message}`));
child.on('exit', (code) => process.exit(code ?? 1));

for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => child.kill(signal));
}
