#!/usr/bin/env python3
"""
binx-cli — BIN lookup & reviews from binx.vip

Requirements:  pip install curl_cffi
Usage:
  python3 binx.py 403306
  python3 binx.py 400895 402018 403306
  python3 binx.py --file bins.txt
  python3 binx.py 403306 --json out.json
"""

import sys, json, time, argparse
from pathlib import Path

try:
    from curl_cffi import requests as cffi_requests
    from curl_cffi.curl import CurlOpt
except ImportError:
    sys.exit("Missing: pip install curl_cffi")

# ── Colors ────────────────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()
def c(t, code): return f"\033[{code}m{t}\033[0m" if USE_COLOR else str(t)
def bold(t):  return c(t, "1")
def cyan(t):  return c(t, "36")
def yellow(t):return c(t, "33")
def green(t): return c(t, "32")
def red(t):   return c(t, "31")
def dim(t):   return c(t, "2")

# ── Session: curl_cffi with DoH to bypass Verizon/ISP SNI interception ────────
SESSION = cffi_requests.Session(
    impersonate="chrome124",
    curl_options={CurlOpt.DOH_URL: "https://cloudflare-dns.com/dns-query"}
)
API = "https://api.binx.vip/api"
HEADERS = {
    "Accept": "application/json",
    "Origin": "https://binx.vip",
    "Referer": "https://binx.vip/",
}

# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch_bin(bin_number: str, proxy: str = None) -> dict:
    proxies = {"http": proxy, "https": proxy} if proxy else None
    kwargs = dict(headers=HEADERS, timeout=20, proxies=proxies)

    # BIN info
    try:
        r = SESSION.get(f"{API}/bins/{bin_number}", **kwargs)
        if r.status_code != 200:
            return {"bin": bin_number, "error": f"HTTP {r.status_code}", "info": {}, "reviews": []}
        info_data = r.json().get("data", {})
    except Exception as e:
        return {"bin": bin_number, "error": str(e).split("\n")[0], "info": {}, "reviews": []}

    # Reviews
    reviews = []
    try:
        rr = SESSION.get(f"{API}/bins/{bin_number}/reviews", **kwargs)
        if rr.status_code == 200:
            for rev in rr.json().get("reviews", []):
                reviews.append({
                    "user":   rev.get("user", {}).get("display_name") or "Anonymous",
                    "rating": f"{rev.get('rating', 0)}/5",
                    "text":   rev.get("description") or "",
                    "time":   rev.get("created_at", ""),
                })
    except Exception:
        pass

    return {"bin": bin_number, "info": info_data, "reviews": reviews}

# ── Display ───────────────────────────────────────────────────────────────────
def stars(rating_str):
    try:
        n = int(rating_str.split("/")[0])
        return "★" * n + "☆" * (5 - n)
    except Exception:
        return rating_str

def print_bin(result: dict):
    info = result.get("info", {})
    print(f"\n{cyan('═' * 62)}")
    bank = info.get("bank", "")
    avg  = info.get("avg_rating", "")
    cnt  = info.get("review_count", 0)
    print(f"  {bold('BIN')} {bold(result['bin'])}  ·  {dim(bank)}")
    print(cyan("═" * 62))

    if result.get("error"):
        print(f"  {red('✗')} {result['error']}\n")
        return

    parts = [info.get("brand",""), info.get("type",""), info.get("category",""), info.get("country_name","")]
    print("  " + "  |  ".join(p for p in parts if p))
    if info.get("bank_phone"):  print(f"  {dim('Phone:')} {info['bank_phone']}")
    if info.get("bank_url"):    print(f"  {dim('URL:')}   {info['bank_url']}")
    if avg: print(f"  {dim('Avg rating:')} {stars(str(avg)+'/5')} {avg}/5  ({cnt} review{'s' if cnt!=1 else ''})")

    reviews = result.get("reviews", [])
    if not reviews:
        print(f"\n  {dim('(no reviews yet)')}\n")
        return

    print(f"\n  {yellow(bold(f'Reviews ({len(reviews)}):'))}")
    print(f"  {'─' * 58}")
    for r in reviews:
        ts = f"  {dim(r['time'][:10])}" if r.get("time") else ""
        print(f"  {bold(r['user'])}  {green(stars(r['rating']))} {r['rating']}{ts}")
        words, line = r["text"].split(), ""
        for w in words:
            if len(line) + len(w) + 1 > 56:
                print(f"    {line}")
                line = w
            else:
                line = (line + " " + w).strip()
        if line: print(f"    {line}")
        print(f"  {dim('·' * 30)}")
    print()

# ── Args ──────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(prog="binx", description="BIN lookup & reviews from binx.vip")
    p.add_argument("bins", nargs="*", help="BIN number(s)")
    p.add_argument("--file", "-f", metavar="FILE", help="File with one BIN per line")
    p.add_argument("--json", "-j", metavar="FILE", help="Save results to JSON file")
    p.add_argument("--proxy", metavar="URL", help="Proxy URL to bypass blocks (e.g. http://1.2.3.4:8080)")
    p.add_argument("--delay", type=float, default=0.3, metavar="SECS", help="Delay between requests (default: 0.3s)")
    p.add_argument("--no-color", action="store_true", help="Disable color output")
    return p.parse_args()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global USE_COLOR
    args = parse_args()
    if args.no_color: USE_COLOR = False

    bins = list(args.bins)
    if args.file:
        path = Path(args.file)
        if not path.exists(): sys.exit(f"File not found: {args.file}")
        bins += [l.strip() for l in path.read_text().splitlines() if l.strip().isdigit() and 4 <= len(l.strip()) <= 8]

    seen = set()
    bins = [b for b in bins if not (b in seen or seen.add(b))]

    if not bins:
        print(__doc__)
        sys.exit(0)

    print(f"\n{bold('🔍 binx-cli')}  —  {len(bins)} BIN(s)\n")

    results = []
    for i, b in enumerate(bins):
        sys.stdout.write(f"  Fetching {bold(b)}... ")
        sys.stdout.flush()
        result = fetch_bin(b, proxy=args.proxy)
        if result.get("error"):
            print(red(f"✗  {result['error']}"))
        else:
            n = len(result["reviews"])
            print(green(f"✓  {n} review{'s' if n!=1 else ''}"))
        results.append(result)
        if i < len(bins) - 1:
            time.sleep(args.delay)

    for r in results:
        print_bin(r)

    if args.json:
        out = {r["bin"]: {"info": r["info"], "reviews": r["reviews"]} for r in results}
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"{green('✅')} JSON saved to {bold(args.json)}")

    print(f"{green('✅')} Done — {len(results)} BIN(s) checked.\n")

if __name__ == "__main__":
    main()
