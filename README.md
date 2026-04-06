# binx-cli

<div align="center">

**A fast, lightweight command-line tool for looking up BIN (Bank Identification Number) info and crowdsourced card reviews.**

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue?style=flat-square)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

</div>

---

## Features

- 🔍 **Instant BIN lookup** — network, type, category, issuing bank, country
- 💬 **Crowdsourced reviews** — ratings, comments, and timestamps from real users
- 📦 **Batch mode** — look up hundreds of BINs at once from a file
- 💾 **JSON export** — dump results to a structured JSON file
- 🌐 **Works anywhere** — resilient DoH-backed networking bypasses ISP-level blocks
- 🎨 **Beautiful terminal output** — color-coded, star ratings, clean formatting

---

## Installation

```bash
pip install curl_cffi
```

That's it. No browser, no headless Chrome, no heavy dependencies.

---

## Usage

```bash
# Look up a single BIN
python3 binx.py 403306

# Look up multiple BINs at once
python3 binx.py 400895 402018 403306

# Read from a file (one BIN per line)
python3 binx.py --file bins.txt

# Export results to JSON
python3 binx.py 400895 403306 --json results.json

# Use a proxy (optional)
python3 binx.py 400895 --proxy http://1.2.3.4:8080

# Disable colors (for piping/logging)
python3 binx.py 400895 --no-color
```

---

## Example Output

```
🔍 binx-cli  —  1 BIN(s)

  Fetching 403306... ✓  3 reviews

══════════════════════════════════════════════════════════════
  BIN 403306  ·  AXIOM BANK
══════════════════════════════════════════════════════════════
  VISA  |  DEBIT  |  CLASSIC  |  UNITED STATES
  Phone: +18005840015
  URL:   https://www.axiombanking.com
  Avg rating: ★★★☆☆ 3.33/5  (3 reviews)

  Reviews (3):
  ──────────────────────────────────────────────────────────
  bincc  ★★★★★ 5/5  2026-03-27
    perfect for cashapp
  ······························
  mugs  ★★★★☆ 4/5  2026-03-26
    Got approved on 4 different banks with the $450
  ······························
  Anonymous  ★☆☆☆☆ 1/5  2025-04-25
    bad bin
  ······························

✅ Done — 1 BIN(s) checked.
```

---

## JSON Output Format

```json
{
  "403306": {
    "info": {
      "bin": "403306",
      "brand": "VISA",
      "type": "DEBIT",
      "category": "CLASSIC",
      "bank": "AXIOM BANK",
      "country_name": "UNITED STATES",
      "avg_rating": "3.33",
      "review_count": 3
    },
    "reviews": [
      {
        "user": "bincc",
        "rating": "5/5",
        "text": "perfect for cashapp",
        "time": "2026-03-27 04:01:20"
      }
    ]
  }
}
```

---

## Options

| Flag           | Short | Description                               |
| -------------- | ----- | ----------------------------------------- |
| `--file FILE`  | `-f`  | Read BINs from a text file (one per line) |
| `--json FILE`  | `-j`  | Save results as JSON                      |
| `--proxy URL`  |       | Use an HTTP/SOCKS proxy                   |
| `--delay SECS` |       | Delay between requests (default: 0.3s)    |
| `--no-color`   |       | Disable ANSI color output                 |

---

## License

MIT — free to use, modify, and distribute.
