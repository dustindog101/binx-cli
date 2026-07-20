#!/usr/bin/env node
/**
 * npm entrypoint for binx-cli.
 * Requires Python 3.8+ on PATH. Installs curl_cffi automatically on first run.
 */
const { spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const ROOT = path.join(__dirname, "..");
const SCRIPT = path.join(ROOT, "binx.py");
const PYTHON = process.env.PYTHON || process.env.PYTHON3 || "python3";

function fail(msg) {
  console.error(`binx-cli: ${msg}`);
  process.exit(1);
}

function run(cmd, args, opts = {}) {
  return spawnSync(cmd, args, { stdio: "inherit", ...opts });
}

if (!fs.existsSync(SCRIPT)) {
  fail(`missing binx.py at ${SCRIPT}`);
}

const pyCheck = spawnSync(PYTHON, ["--version"], { stdio: "pipe" });
if (pyCheck.error || pyCheck.status !== 0) {
  fail(`${PYTHON} not found. Install Python 3.8+ or set PYTHON=/path/to/python3`);
}

const depCheck = spawnSync(PYTHON, ["-c", "import curl_cffi"], { stdio: "pipe" });
if (depCheck.status !== 0) {
  console.error("binx-cli: installing curl_cffi...");
  const pip = run(PYTHON, ["-m", "pip", "install", "-q", "curl_cffi"]);
  if (pip.status !== 0) {
    fail("failed to install curl_cffi. Try: pip install curl_cffi");
  }
}

const result = run(PYTHON, [SCRIPT, ...process.argv.slice(2)]);
process.exit(result.status ?? 1);
