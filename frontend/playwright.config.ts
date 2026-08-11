import { defineConfig } from '@playwright/test';

const PORT = Number(process.env.E2E_FRONTEND_PORT || 3000);
const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT || 8000);

export default defineConfig({
  testDir: './tests/e2e',
  globalSetup: './tests/e2e/global-setup.ts',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  // Fixed at 2 workers: 6 workers triggered vite dev on-demand compilation
  // races with flaky failures (see TASK-015 handoff); 2 is proven stable.
  workers: 2,
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
  ],
  outputDir: 'test-results',
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium', channel: 'chromium' },
    },
  ],
  webServer: [
    {
      // Real backend: alembic upgrade head (idempotent, isolated SQLite DB at
      // data/e2e-backend.db) + uvicorn on 127.0.0.1:8000. See start-backend.mjs.
      command: `node tests/e2e/start-backend.mjs --port ${BACKEND_PORT}`,
      url: `http://127.0.0.1:${BACKEND_PORT}/api/products?page_size=1`,
      reuseExistingServer: false,
      timeout: 180000,
    },
    {
      // --strictPort makes vite fail loudly instead of silently binding
      // 3001/3002 when port 3000 is occupied by an orphaned dev server
      // (the root cause of "Vite not ready on expected port" in the audit).
      // Spawn vite's node bin directly (no npm.cmd wrapper) so Playwright's
      // process-tree teardown kills it reliably on Windows too.
      command: `node node_modules/vite/bin/vite.js --strictPort --port ${PORT}`,
      url: `http://localhost:${PORT}`,
      reuseExistingServer: false,
      timeout: 60000,
    },
  ],
});
