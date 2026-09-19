import { chromium } from '@playwright/test';
import type { FullConfig } from '@playwright/test';

/**
 * Runs once after all webServers are ready and before the first test.
 *
 * Vite answers its HTTP readiness probe instantly but compiles the app
 * bundle lazily on the first browser request (dep optimization + module
 * graph build). A warm page load here makes the first test deterministic
 * instead of racing the dev-server compile.
 *
 * The URL comes from the resolved config, not a literal host:port: a pinned
 * port warms whatever else happens to own it (another project's dev server)
 * and leaves every first test racing the compile.
 */
export default async function globalSetup(config: FullConfig) {
  const baseURL = config.projects[0].use.baseURL;
  if (!baseURL) {
    throw new Error('e2e globalSetup: use.baseURL is unset — refusing to warm an unknown origin');
  }
  const browser = await chromium.launch({ channel: 'chromium' });
  const page = await browser.newPage();
  try {
    await page.goto(baseURL, {
      waitUntil: 'networkidle',
      timeout: 120_000,
    });
  } finally {
    await browser.close();
  }
}
