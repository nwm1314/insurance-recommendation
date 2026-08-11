import { chromium } from '@playwright/test';

/**
 * Runs once after all webServers are ready and before the first test.
 *
 * Vite answers its HTTP readiness probe instantly but compiles the app
 * bundle lazily on the first browser request (dep optimization + module
 * graph build). A warm page load here makes the first test deterministic
 * instead of racing the dev-server compile.
 */
export default async function globalSetup() {
  const browser = await chromium.launch({ channel: 'chromium' });
  const page = await browser.newPage();
  try {
    await page.goto('http://localhost:3000/', {
      waitUntil: 'networkidle',
      timeout: 120_000,
    });
  } finally {
    await browser.close();
  }
}
