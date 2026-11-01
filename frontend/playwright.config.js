import { defineConfig } from '@playwright/test'

// Browser tests drive the real UI against the real API on a throwaway database (see
// backend/tests/e2e_server.py). They use the installed Google Chrome, so no browser download.
export default defineConfig({
  testDir: './e2e',
  timeout: 5 * 60 * 1000,
  expect: { timeout: 15_000 },
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    channel: 'chrome',
    acceptDownloads: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: '../.venv/bin/python -m tests.e2e_server 8765',
    cwd: '../backend',
    url: 'http://127.0.0.1:8765/api/health',
    timeout: 120_000,
    reuseExistingServer: false,
    env: { OMP_NUM_THREADS: '2' },
  },
})
