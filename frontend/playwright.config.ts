import { defineConfig } from '@playwright/test';
import { fileURLToPath } from 'node:url';

// API startuje lokalnie z backend/.venv. Gdy dziala juz `docker compose up`,
// Playwright uzyje dzialajacych serwerow (reuseExistingServer).
// E2E_API_CMD pozwala podmienic komende, np. na "docker compose up api".
const apiCmd =
  process.env.E2E_API_CMD ??
  '../backend/.venv/bin/python -m uvicorn app.main:app --app-dir ../backend --port 8000';

// Testy nie wołają modelu (AGENTS.md): API dostaje atrapę odpowiedzi modelu z fields.json.
// Uwaga: reuseExistingServer użyje API, które już działa na porcie 8000, także bez tej zmiennej.
const llmFixture =
  process.env.LLM_FIXTURE ?? fileURLToPath(new URL('../backend/tests/fixtures/fields.json', import.meta.url));

export default defineConfig({
  testDir: 'tests/e2e',
  use: { baseURL: 'http://localhost:5173' },
  webServer: [
    {
      command: apiCmd,
      url: 'http://localhost:8000/health',
      env: { LLM_FIXTURE: llmFixture },
      reuseExistingServer: true,
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
    },
  ],
});
