# binx-cli

<div align="center">

**A fast, lightweight command-line tool for looking up BIN (Bank Identification Number) info and crowdsourced card reviews from [binx.cz](https://binx.cz).**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Features

- 🔍 **Instant BIN lookup** — network, type, category, issuing bank, country
- 💬 **Crowdsourced reviews** — ratings, comments, and timestamps from real users
- ⭐ **Favorites with notes** — save BINs and tag why they're useful
- 📦 **Batch mode** — look up hundreds of BINs at once from a file
- 💾 **JSON export** — dump results to a structured JSON file
- 🔄 **Self-updating** — check and install updates from GitHub
- 🌐 **Works anywhere** — resilient DoH-backed networking bypasses ISP-level blocks
- 🎨 **Beautiful terminal output** — color-coded, star ratings, clean formatting

---

## Installation

**Recommended (one-liner):**

```bash
curl -fsSL https://raw.githubusercontent.com/dustindog101/binx-cli/main/install.sh | bash
```

**Manual:**

```bash
pip install curl_cffi
git clone https://github.com/dustindog101/binx-cli.git
cd binx-cli
python3 binx.py 403306
```

---

## Usage

```bash
# Look up a single BIN
binx 403306

# Look up multiple BINs
binx 400895 402018 403306

# Read from a file (one BIN per line)
binx --file bins.txt

# Export results to JSON
binx 400895 403306 --json results.json

# Favorite a BIN with a note
binx favorite 539689 "good for prizepicks"

# View favorites
binx favorites

# Check for updates
binx update

# Install latest version
binx update install

# Show version
binx --version
```

Run `binx help` for the full command list.

---

## Updating

```bash
binx update              # check GitHub for a new release
binx update install      # download/install the latest release
```

Updates are published via [GitHub Releases](https://github.com/dustindog101/binx-cli/releases). If GitHub is unreachable, binx keeps working — it just skips the check.

See [docs/UPDATES.md](docs/UPDATES.md) for full update documentation.

---

## Example Output

```
🔍 binx-cli  —  1 BIN(s)

  Fetching 403306... ✓  8 reviews

══════════════════════════════════════════════════════════════
  BIN 403306  ·  AXIOM BANK
══════════════════════════════════════════════════════════════
  VISA  |  DEBIT  |  CLASSIC  |  UNITED STATES
  Phone: +18005840015
  URL:   https://www.axiombanking.com
  Avg rating: ★★★★☆ 3.75/5  (8 reviews)

  Reviews (8):
  ──────────────────────────────────────────────────────────
  taylor  ★★★★☆ 4/5  2026-05-06
    just hit costco
  ······························

✅ Done — 1 BIN(s) checked.
```

---

## Options

| Flag | Short | Description |
|------|-------|-------------|
| `--file FILE` | `-f` | Read BINs from a text file (one per line) |
| `--json FILE` | `-j` | Save results as JSON |
| `--proxy URL` | | Use an HTTP/SOCKS proxy |
| `--delay SECS` | | Delay between requests (default: 0.3s) |
| `--offline` | | Use local cache only |
| `--version` | | Show installed version |
| `--check-update` | | Alias for `binx update` |
| `--no-color` | | Disable ANSI color output |

---

## Documentation

| Doc | Audience | Contents |
|-----|----------|----------|
| [docs/UPDATES.md](docs/UPDATES.md) | Users | How to check, install, and troubleshoot updates |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Maintainers | Testing, CI, and how to publish releases |

---

## License

MIT — free to use, modify, and distribute.
