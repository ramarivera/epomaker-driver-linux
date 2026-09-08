import { resolve } from "node:path";
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8934",
    viewport: { width: 1586, height: 992 },
  },
  webServer: {
    command: `${process.env.EPOMAKER_TEST_PYTHON || resolve("../.venv/bin/python")} ../tests/serve_ui.py --port 8934`,
    url: "http://127.0.0.1:8934/",
    reuseExistingServer: false,
  },
});
