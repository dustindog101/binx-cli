#!/usr/bin/env python3
"""
binx-cli — BIN lookup & reviews from binx.cz

Requirements:  pip install curl_cffi
Usage:
  python3 binx.py 403306
  python3 binx.py 400895 402018 403306
  python3 binx.py --file bins.txt
  python3 binx.py 403306 --json out.json
"""

import sys, json, time, argparse, os, tempfile, re, shutil, subprocess, tarfile
from pathlib import Path
from typing import Optional, List, Tuple

__version__ = "1.2.0"
DOMAIN = "binx.cz"
GITHUB_REPO = "dustindog101/binx-cli"
UPDATE_CHECK_TTL = 86_400  # 24h
UPDATE_TIMEOUT = 8

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
SITE = f"https://{DOMAIN}"
API = f"https://api.{DOMAIN}/api"
HEADERS = {"Accept": "application/json", "Origin": SITE, "Referer": f"{SITE}/"}
UPDATE_CACHE_FILE = Path.home() / ".cache" / "binx" / "update_check.json"
_update_hint_shown = False

# ── Cache Database Setup ──────────────────────────────────────────────────────
CACHE_FILE = Path(__file__).resolve().parent / "binx_cache.json"

def load_cache() -> dict:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        print(dim(f"⚠️ Cache read/decode error: {e}. Reinitializing clean cache."))
        return {}

def save_cache(cache: dict):
    try:
        # Atomic, corruption-proof save in the same directory as CACHE_FILE
        with tempfile.NamedTemporaryFile("w", delete=False, dir=CACHE_FILE.parent, encoding="utf-8") as tf:
            json.dump(cache, tf, indent=2, ensure_ascii=False)
            temp_path = tf.name
        os.replace(temp_path, CACHE_FILE)
    except Exception as e:
        print(red(f"✗ Failed to save cache: {e}"))

# ── Updates ───────────────────────────────────────────────────────────────────
def install_dir() -> Path:
    return Path(__file__).resolve().parent

def is_connectivity_error(msg: str) -> bool:
    m = (msg or "").lower()
    needles = (
        "resolve", "connection", "timeout", "ssl", "certificate", "refused",
        "unreachable", "name or service not known", "could not connect",
        "failed to perform", "http 404", "http 502", "http 503",
        "binx.vip", "nodename nor servname",
    )
    return any(n in m for n in needles)

def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:3] or [0])

def _compare_versions(current: str, latest: str) -> str:
    cur, lat = _version_tuple(current), _version_tuple(latest)
    if lat > cur:
        return "update_available"
    if lat == cur:
        return "up_to_date"
    return "ahead"

def fetch_latest_release(session=None) -> Tuple[Optional[dict], Optional[str]]:
    session = session or SESSION
    try:
        r = session.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={"Accept": "application/vnd.github+json"},
            timeout=UPDATE_TIMEOUT,
        )
        if r.status_code == 404:
            return None, "No releases published yet"
        if r.status_code != 200:
            return None, f"GitHub API HTTP {r.status_code}"
        data = r.json()
        tag = data.get("tag_name") or ""
        version = tag.lstrip("vV")
        if not version:
            return None, "Release has no version tag"
        return {
            "version": version,
            "tag": tag,
            "url": data.get("html_url") or f"https://github.com/{GITHUB_REPO}/releases/latest",
            "name": data.get("name") or tag,
            "tarball": f"https://github.com/{GITHUB_REPO}/archive/refs/tags/{tag}.tar.gz",
        }, None
    except Exception as e:
        return None, str(e).split("\n")[0]

def _read_update_cache() -> dict:
    if not UPDATE_CACHE_FILE.exists():
        return {}
    try:
        return json.loads(UPDATE_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_update_cache(data: dict):
    try:
        UPDATE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_CACHE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass

def check_for_updates(force: bool = False) -> dict:
    """Check GitHub for updates. Never raises; returns cached data when offline."""
    if os.environ.get("BINX_SKIP_UPDATE_CHECK"):
        cached = _read_update_cache()
        if cached:
            return cached
        return {"current": __version__, "status": "skipped", "latest": None, "url": f"https://github.com/{GITHUB_REPO}/releases"}

    cached = _read_update_cache()
    now = time.time()
    if not force and cached.get("checked_at", 0) + UPDATE_CHECK_TTL > now:
        return cached

    release, err = fetch_latest_release()
    if release:
        result = {
            "checked_at": now,
            "current": __version__,
            "latest": release["version"],
            "tag": release["tag"],
            "url": release["url"],
            "tarball": release["tarball"],
            "status": _compare_versions(__version__, release["version"]),
            "error": None,
        }
        _write_update_cache(result)
        return result

    # Network failed — keep last known good cache, never wipe it
    if cached.get("latest"):
        cached["checked_at"] = now
        cached["status"] = cached.get("status", "unavailable")
        cached["error"] = err
        return cached

    return {
        "checked_at": now,
        "current": __version__,
        "latest": None,
        "status": "unavailable",
        "error": err,
        "url": f"https://github.com/{GITHUB_REPO}/releases",
    }

def print_update_status(info: dict):
    status, cur, lat = info.get("status"), info.get("current", __version__), info.get("latest")
    if status == "skipped":
        print(dim("Update check disabled (BINX_SKIP_UPDATE_CHECK=1)."))
        return
    if not lat:
        print(dim(f"Could not reach GitHub ({info.get('error', 'offline')})."))
        print(dim(f"binx-cli v{cur} is still usable. Try again later or visit {info.get('url')}."))
        return
    if status == "update_available":
        print(yellow(f"⬆  Update available: v{cur} → v{lat}"))
        print(f"   Run {cyan('binx update install')} or visit {cyan(info['url'])}")
    elif status == "up_to_date":
        print(green(f"✓  binx-cli v{cur} is up to date."))
    else:
        print(dim(f"Running v{cur} (latest release: v{lat})"))

def notify_if_update_available():
    """Quiet one-line hint before lookups. Never blocks or errors."""
    if os.environ.get("BINX_SKIP_UPDATE_CHECK") or not sys.stdout.isatty():
        return
    try:
        info = check_for_updates()
        if info.get("status") == "update_available":
            print(dim(f"Update available: v{info['latest']} — run `binx update install`\n"))
    except Exception:
        pass

def maybe_suggest_update(err_msg: str = ""):
    """On API errors, hint about updates using cache only (no extra network call)."""
    global _update_hint_shown
    if _update_hint_shown or not is_connectivity_error(err_msg):
        return
    _update_hint_shown = True
    info = _read_update_cache()
    print(yellow("\n⚠  Connection/API error — a newer release may fix this."))
    if info.get("latest") and _version_tuple(info["latest"]) > _version_tuple(__version__):
        print(f"   Latest: v{info['latest']}  →  {cyan(info['url'])}")
        print(f"   Run {cyan('binx update install')}")
    else:
        print(f"   Run {cyan('binx update')} when online.")
    print(dim(f"   Current: v{__version__}  ·  API: {API}\n"))

def _validate_script(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
        return "__version__" in text and "def fetch_bin" in text
    except Exception:
        return False

def _update_via_git(root: Path) -> Tuple[bool, str]:
    try:
        subprocess.run(["git", "fetch", "--tags", "origin"], cwd=root, check=True, capture_output=True, text=True, timeout=60)
        subprocess.run(["git", "pull", "--ff-only"], cwd=root, check=True, capture_output=True, text=True, timeout=60)
        return True, "Updated via git pull."
    except subprocess.CalledProcessError as e:
        err = (e.stderr or e.stdout or str(e)).strip().split("\n")[-1]
        return False, f"Git update failed: {err}"
    except Exception as e:
        return False, f"Git update failed: {e}"

def _update_via_release(info: dict, root: Path) -> Tuple[bool, str]:
    tag, tarball = info.get("tag"), info.get("tarball")
    if not tag or not tarball:
        return False, "No release info available. Run `binx update` when online."
    script = root / "binx.py"
    backup = root / f"binx.py.bak.{int(time.time())}"
    tmp = Path(tempfile.mkdtemp(prefix="binx-update-"))
    try:
        r = SESSION.get(tarball, timeout=60)
        if r.status_code != 200:
            return False, f"Download failed: HTTP {r.status_code}"
        archive = tmp / "release.tar.gz"
        archive.write_bytes(r.content)
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(tmp, filter="data")
        extracted = next(tmp.glob(f"*/binx.py"), None)
        if not extracted or not _validate_script(extracted):
            return False, "Downloaded release failed validation."
        if script.exists():
            shutil.copy2(script, backup)
        shutil.copy2(extracted, script)
        os.chmod(script, 0o755)
        req = next(tmp.glob("*/requirements.txt"), None)
        if req:
            shutil.copy2(req, root / "requirements.txt")
        ver = re.search(r'__version__\s*=\s*["\']([^"\']+)', extracted.read_text(encoding="utf-8"))
        new_ver = ver.group(1) if ver else tag
        return True, f"Updated to v{new_ver} from GitHub release {tag}."
    except Exception as e:
        if backup.exists() and script.exists():
            shutil.copy2(backup, script)
        return False, f"Release update failed: {e}".split("\n")[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def perform_update(force: bool = False) -> int:
    root = install_dir()
    if (root / ".git").is_dir():
        ok, msg = _update_via_git(root)
        if ok:
            print(green(f"✓  {msg}"))
            return 0
        print(yellow(f"⚠  {msg}"))
        return 1

    info = check_for_updates(force=True)
    if info.get("status") == "up_to_date" and not force:
        print(green(f"✓  binx-cli v{__version__} is already up to date."))
        return 0
    if not info.get("latest"):
        print(dim(f"Could not reach GitHub ({info.get('error', 'offline')}). Try again later."))
        return 0

    ok, msg = _update_via_release(info, root)
    if ok:
        print(green(f"✓  {msg}"))
        # refresh deps if venv exists
        venv_pip = root / "venv" / "bin" / "pip"
        if venv_pip.exists() and (root / "requirements.txt").exists():
            try:
                subprocess.run([str(venv_pip), "install", "-q", "-r", str(root / "requirements.txt")], check=False, timeout=120)
                print(dim("   Dependencies refreshed."))
            except Exception:
                pass
        return 0
    print(yellow(f"⚠  {msg}"))
    return 1

def handle_update_command(subcmd: Optional[str] = None, force: bool = False) -> int:
    sub = (subcmd or "check").lower()
    if sub in ("check", "status"):
        print_update_status(check_for_updates(force=force))
        return 0
    if sub == "install":
        return perform_update(force=force)
    print(red(f"Unknown update command: {sub}"))
    print(dim("Usage: binx update [check|install]"))
    return 1

def _is_bin(tok: str) -> bool:
    return tok.isdigit() and 4 <= len(tok) <= 8

def parse_favorite_tokens(tokens: list) -> List[Tuple[str, Optional[str]]]:
    """Return [(bin, note|None)]. note=None → toggle; note=str → favorite + set note."""
    out, i = [], 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("--note", "-n"):
            if out and i + 1 < len(tokens):
                out[-1] = (out[-1][0], tokens[i + 1])
                i += 2
                continue
            i += 1
            continue
        if not _is_bin(tok):
            i += 1
            continue
        if i + 1 < len(tokens):
            nxt = tokens[i + 1]
            if len(nxt) >= 2 and nxt[0] == nxt[-1] and nxt[0] in "\"'":
                out.append((tok, nxt[1:-1]))
                i += 2
                continue
            if not _is_bin(nxt):
                parts, j = [], i + 1
                while j < len(tokens) and not _is_bin(tokens[j]):
                    if tokens[j] in ("--note", "-n") and j + 1 < len(tokens):
                        j += 1
                        parts.append(tokens[j])
                    else:
                        parts.append(tokens[j])
                    j += 1
                note = " ".join(parts).strip() or None
                out.append((tok, note))
                i = j
                continue
        out.append((tok, None))
        i += 1
    return out

# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch_bin(bin_number: str, session=None, proxy: str = None) -> dict:
    if session is None:
        session = SESSION
    proxies = {"http": proxy, "https": proxy} if proxy else None
    kwargs = dict(headers=HEADERS, timeout=20, proxies=proxies)

    # BIN info
    try:
        r = session.get(f"{API}/bins/{bin_number}", **kwargs)
        if r.status_code != 200:
            err = f"HTTP {r.status_code}"
            maybe_suggest_update(err)
            return {"bin": bin_number, "error": err, "info": {}, "reviews": []}
        info_data = r.json().get("data", {})
    except Exception as e:
        err = str(e).split("\n")[0]
        maybe_suggest_update(err)
        return {"bin": bin_number, "error": err, "info": {}, "reviews": []}

    # Reviews
    reviews = []
    review_count = int(info_data.get("review_count") or 0)
    if review_count > 0:
        offset = 0
        limit = 50
        while True:
            try:
                url = f"{API}/bins/{bin_number}/reviews?offset={offset}&limit={limit}"
                rr = session.get(url, **kwargs)
                if rr.status_code != 200:
                    break
                
                data = rr.json()
                page_reviews = data.get("reviews", [])
                if not page_reviews:
                    break
                
                for rev in page_reviews:
                    reviews.append({
                        "user":   rev.get("user", {}).get("display_name") or "Anonymous",
                        "rating": f"{rev.get('rating', 0)}/5",
                        "text":   rev.get("description") or "",
                        "time":   rev.get("created_at", ""),
                    })
                
                offset += len(page_reviews)
                total = data.get("total", 0)
                if len(reviews) >= total or offset >= total:
                    break
                
                time.sleep(0.1)  # Respectful delay between page fetches
            except Exception:
                break

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
    
    stamp = ""
    if result.get("offline"):
        stamp = f"  {yellow('[OFFLINE CACHE]')}"
    elif result.get("fallback"):
        stamp = f"  {yellow('[OFFLINE FALLBACK]')}"
        
    fav_star = f" {yellow('★')}" if result.get("favorite") else ""
    fav_note = result.get("favorite_note")
    print(f"  {bold('BIN')} {bold(result['bin'])}{fav_star}  ·  {dim(bank)}{stamp}")
    if fav_note:
        print(f"  {dim('Note:')} {fav_note}")
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

# ── Help ──────────────────────────────────────────────────────────────────────
def print_help():
    print(f"\n{bold(cyan('╔══════════════════════════════════════════════════════════════════════╗'))}")
    print(f"{bold(cyan('║'))}  {bold(green('🔍 binx-cli'))} — Modern Crowdsourced BIN Lookup & Reviews         {bold(cyan('║'))}")
    print(f"{bold(cyan('╚══════════════════════════════════════════════════════════════════════╝'))}")
    
    print(f"\n{bold(yellow('USAGE:'))}")
    print(f"  python3 binx.py {cyan('<bin1> [bin2] ...')} [options]")
    print(f"  python3 binx.py {cyan('--file')} <file.txt> [options]")
    print(f"  python3 binx.py {cyan('help')}")
    print(f"  python3 binx.py {cyan('list')}")
    print(f"  python3 binx.py {cyan('favorite')} <bin1> [\"note\"] [bin2] ...")
    print(f"  python3 binx.py {cyan('favorites')}")
    print(f"  python3 binx.py {cyan('favorites remove')} <bin1> [bin2] ...")
    print(f"  python3 binx.py {cyan('favorites clear')}")
    print(f"  python3 binx.py {cyan('--version')}")
    print(f"  python3 binx.py {cyan('update')}")
    print(f"  python3 binx.py {cyan('update install')}")
    print(f"  python3 binx.py {cyan('--check-update')}")
    print(f"  python3 binx.py {cyan('remove')} <bin1> [bin2] ...")
    print(f"  python3 binx.py {cyan('clean')} <text_or_file>")

    print(f"\n{bold(yellow('COMMANDS:'))}")
    print(f"  {green('help')}                        Show this beautiful, customized help screen.")
    print(f"  {green('list')}                        Display all the BINs saved in the local cache.")
    print(f"  {green('update')} [check|install]       Check for or install updates from GitHub.")
    print(f"  {green('favorite')} <bin> [\"note\"]     Toggle favorite, or favorite with an optional note.")
    print(f"  {green('favorites')}                   Display all favorited BINs saved in the local cache.")
    print(f"  {green('favorites remove')} <bin1> ...   Remove one or more BINs from the favorites list.")
    print(f"  {green('favorites clear')}            Clear all favorites from the local database.")
    print(f"  {green('remove')} <bin1> ...             Remove one or more BINs entirely from the local cache.")
    print(f"  {green('clean')} <text_or_file>        Extract and clean BINs from raw text or a file path.")

    print(f"\n{bold(yellow('OPTIONS:'))}")
    print(f"  {green('-f, --file')} {cyan('FILE')}             A text file with one BIN per line to process in bulk.")
    print(f"  {green('-j, --json')} {cyan('FILE')}             Export results as a structured JSON file.")
    print(f"  {green('-c, --concurrency')} {cyan('NUM')}       Number of concurrent lookup threads.")
    print(f"                           Auto-calculates based on BIN count by default.")
    print(f"                           Set to 1 for sequential processing.")
    print(f"  {green('--proxy')} {cyan('URL')}                  Proxy URL to route through (e.g. http://1.2.3.4:8080).")
    print(f"  {green('--delay')} {cyan('SECS')}                 Delay between sequential requests in seconds (default: {bold('0.3')}).")
    print(f"  {green('--offline')} / {green('--cache-only')}       Search and display exclusively from the local cache.")
    print(f"  {green('--list-cache')} / {green('--list')}      Display all the BINs saved in the local cache.")
    print(f"  {green('--fav')} / {green('--favorite')} {cyan('BIN')}        Toggle favorite or set note with --note.")
    print(f"  {green('--favs')} / {green('--favorites')}        Display all favorited BINs.")
    print(f"  {green('--version')}                 Show installed version.")
    print(f"  {green('--check-update')}            Alias for {cyan('binx update')}.")
    print(f"  {green('BINX_SKIP_UPDATE_CHECK=1')}   Disable background update hints.")
    print(f"  {green('--remove')} {cyan('BIN')}                 Remove one or more BINs entirely from the local cache.")
    print(f"  {green('--clean')} {cyan('TEXT_OR_FILE')}         Extract and clean BINs from raw text or a file path.")
    print(f"  {green('--clear-cache')}               Safely clear the local cache file.")
    print(f"  {green('--no-color')}                 Disable all ANSI color codes in output.")
    print(f"  {green('-h, --help')}                 Show this custom help message and exit.")

    print(f"\n{bold(yellow('EXAMPLES:'))}")
    print(f"  {dim('# Lookup a single BIN')}")
    print(f"  python3 binx.py {cyan('400022')}")
    print(f"  ")
    print(f"  {dim('# Lookup multiple BINs concurrently')}")
    print(f"  python3 binx.py {cyan('400022 486796 432359')} -c 10")
    print(f"  ")
    print(f"  {dim('# Query in fully offline mode from local database')}")
    print(f"  python3 binx.py {cyan('486796')} --offline")
    print(f"  ")
    print(f"  {dim('# List all cached BINs saved locally')}")
    print(f"  python3 binx.py {cyan('list')}")
    print(f"  ")
    print(f"  {dim('# Toggle favorite status for BINs')}")
    print(f"  python3 binx.py {cyan('favorite 539689 \"good for prizepicks\"')}")
    print(f"  ")
    print(f"  {dim('# View all favorited BINs')}")
    print(f"  python3 binx.py {cyan('favorites')}")
    print(f"  ")
    print(f"  {dim('# Remove specific BINs from favorites')}")
    print(f"  python3 binx.py {cyan('favorites remove 486796')}")
    print(f"  ")
    print(f"  {dim('# Clear all favorited BINs')}")
    print(f"  python3 binx.py {cyan('favorites clear')}")
    print(f"  ")
    print(f"  {dim('# Delete specific BINs entirely from local cache')}")
    print(f"  python3 binx.py {cyan('remove 486796 400895')}")
    print(f"  ")
    print(f"  {dim('# Clean and extract BINs from raw text')}")
    print(f"  python3 binx.py {cyan('clean \"cards: 4867961234567890, 4008951234567890\"')}")
    print(f"  ")
    print(f"  {dim('# Clean and extract BINs from a text file')}")
    print(f"  python3 binx.py {cyan('clean dump.txt')}")
    print(f"\n{dim('Powered by DoH (DNS-over-HTTPS) to guarantee secure, un-interceptable lookups.')}\n")

# ── Args ──────────────────────────────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser(prog="binx", description=f"BIN lookup & reviews from {DOMAIN}", add_help=False)
    p.add_argument("bins", nargs="*", help="BIN number(s)")
    p.add_argument("--file", "-f", metavar="FILE", help="File with one BIN per line")
    p.add_argument("--json", "-j", metavar="FILE", help="Save results to JSON file")
    p.add_argument("--proxy", metavar="URL", help="Proxy URL to bypass blocks (e.g. http://1.2.3.4:8080)")
    p.add_argument("--delay", type=float, default=0.3, metavar="SECS", help="Delay between sequential requests (default: 0.3s)")
    p.add_argument("--concurrency", "-c", type=int, default=None, metavar="NUM", help="Number of concurrent lookups (default: auto, set to 1 for sequential)")
    p.add_argument("--offline", "--cache-only", action="store_true", help="Search and display exclusively from the local cache")
    p.add_argument("--list-cache", "--list", action="store_true", help="Display all the BINs saved in the local cache")
    p.add_argument("--fav", "--favorite", metavar="BIN", nargs="*", default=None, help="Toggle favorite or set note (--note)")
    p.add_argument("--favs", "--favorites", action="store_true", help="Display all favorited BINs")
    p.add_argument("--note", "-n", metavar="TEXT", help="Note/reason when favoriting a BIN")
    p.add_argument("--version", action="store_true", help="Show installed version")
    p.add_argument("--check-update", action="store_true", help="Check GitHub for a newer release")
    p.add_argument("--remove", metavar="BIN", nargs="*", default=None, help="Remove one or more BINs entirely from the local cache")
    p.add_argument("--clean", metavar="TEXT_OR_FILE", nargs="*", default=None, help="Extract and clean BINs from raw text or a file path")
    p.add_argument("--clear-cache", action="store_true", help="Safely clear the local cache file")
    p.add_argument("--no-color", action="store_true", help="Disable color output")
    p.add_argument("-h", "--help", action="store_true", help="Show this beautiful help message and exit")
    return p.parse_args()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global USE_COLOR
    args = parse_args()
    if args.no_color: USE_COLOR = False

    if args.help:
        print_help()
        sys.exit(0)

    if args.version:
        print(f"binx-cli v{__version__}  ({DOMAIN})")
        sys.exit(0)

    if args.check_update:
        sys.exit(handle_update_command("check", force=True))

    bins = list(args.bins)
    if bins and bins[0] == "update":
        sys.exit(handle_update_command(bins[1] if len(bins) > 1 else None))

    # ── 1. Clear Cache check ──────────────────────────────────────────────────
    if args.clear_cache:
        if CACHE_FILE.exists():
            try:
                CACHE_FILE.unlink()
                print(green("✅ Local cache successfully cleared."))
            except Exception as e:
                print(red(f"✗ Failed to clear cache: {e}"))
        else:
            print(dim("Cache is already empty."))
        sys.exit(0)

    # ── 2. Load Cache ─────────────────────────────────────────────────────────
    cache = load_cache()
    cache_modified = False

    if "help" in bins:
        print_help()
        sys.exit(0)

    # ── Clean Command ─────────────────────────────────────────────────────────
    if args.clean is not None or (bins and bins[0] == "clean"):
        clean_targets = args.clean if args.clean is not None else bins[1:]
        if not clean_targets:
            print(red("Error: Please specify raw text or a file path to clean."))
            sys.exit(1)
            
        import re
        text_to_clean = ""
        # Check if single target matches an existing file path
        if len(clean_targets) == 1 and os.path.exists(clean_targets[0]):
            try:
                file_path = Path(clean_targets[0]).resolve()
                text_to_clean = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                print(red(f"Error reading file {clean_targets[0]}: {e}"))
                sys.exit(1)
        else:
            text_to_clean = " ".join(clean_targets)
            
        found_nums = re.findall(r"\b\d{6,19}\b", text_to_clean)
        
        cleaned_bins = []
        for num in found_nums:
            if 6 <= len(num) <= 8:
                cleaned_bins.append(num)
            elif len(num) > 8:
                cleaned_bins.append(num[:6])
                
        seen_bins = set()
        unique_bins = []
        for b in cleaned_bins:
            if b not in seen_bins:
                seen_bins.add(b)
                unique_bins.append(b)
                
        if not unique_bins:
            print(dim("No valid BINs found in the text."))
            sys.exit(0)
            
        print(f"\n{bold(green('🧼 Cleaned BINs'))}  —  {bold(len(unique_bins))} unique BIN(s) found:\n")
        print(" ".join(unique_bins))
        print()
        sys.exit(0)

    # ── Favorites Commands ────────────────────────────────────────────────────
    if args.favs or (bins and bins[0] in ("favs", "favorites")):
        if bins and len(bins) > 1:
            if bins[1] == "remove":
                remove_targets = bins[2:]
                if not remove_targets:
                    print(red("Error: Please specify one or more BINs to remove from favorites."))
                    sys.exit(1)
                cache_modified = False
                for b in remove_targets:
                    if b in cache and cache[b].get("favorite", False):
                        cache[b]["favorite"] = False
                        cache_modified = True
                        print(f"  ☆ {bold(b)} has been removed from favorites.")
                    else:
                        print(dim(f"  BIN {b} is not in favorites."))
                if cache_modified:
                    save_cache(cache)
                sys.exit(0)
            elif bins[1] == "clear":
                cache_modified = False
                for b, entry in cache.items():
                    if entry.get("favorite", False):
                        entry["favorite"] = False
                        cache_modified = True
                if cache_modified:
                    save_cache(cache)
                    print(green("⭐ All favorites successfully cleared."))
                else:
                    print(dim("No favorites to clear."))
                sys.exit(0)
        fav_bins = [b for b, entry in cache.items() if entry.get("favorite", False)]
        if not fav_bins:
            print(dim("\n  (no favorited BINs saved yet)\n"))
            sys.exit(0)
            
        sorted_bins = sorted(fav_bins)
        print(f"\n{bold(yellow('⭐ Favorited BINs in Local Cache'))}  —  {bold(len(sorted_bins))} BIN(s) total\n")
        
        h_bin     = "BIN"
        h_brand   = "Brand"
        h_type    = "Type"
        h_country = "Country"
        h_bank    = "Bank"
        h_reviews = "Reviews"
        h_note    = "Note"
        
        print(f"  {bold(h_bin.ljust(10))}  {bold(h_brand.ljust(10))}  {bold(h_type.ljust(8))}  {bold(h_country.ljust(15))}  {bold(h_bank.ljust(30))}  {bold(h_reviews.rjust(7))}  {bold(h_note)}")
        print(dim("  " + "─" * 115))
        
        total_reviews = 0
        for b in sorted_bins:
            entry = cache[b]
            info = entry.get("info", {})
            reviews = entry.get("reviews", [])
            rev_len = len(reviews)
            total_reviews += rev_len
            
            brand   = (info.get("brand") or "UNKNOWN")[:10]
            type_   = (info.get("type") or "UNKNOWN")[:8]
            country = (info.get("country_name") or "UNKNOWN")[:15]
            bank    = (info.get("bank") or "UNKNOWN")[:30]
            note    = (entry.get("favorite_note") or "")[:40]
            
            bin_display = f"{b} ★"
            print(f"  {cyan(bin_display.ljust(10))}  {brand.ljust(10)}  {type_.ljust(8)}  {country.ljust(15)}  {dim(bank.ljust(30))}  {green(str(rev_len).rjust(7))}  {note}")
            
        print(dim("  " + "─" * 115))
        print(f"  {bold('Total Favorites Stats:')} {green(str(total_reviews))} reviews across {bold(str(len(sorted_bins)))} favorited BIN(s)\n")
        sys.exit(0)

    if args.fav is not None or (bins and bins[0] in ("fav", "favorite")):
        raw_targets = list(args.fav if args.fav is not None else bins[1:])
        if args.note and raw_targets:
            raw_targets.extend(["--note", args.note])
        fav_pairs = parse_favorite_tokens(raw_targets)
        if not fav_pairs:
            print(red("Error: Please specify one or more BINs to favorite."))
            sys.exit(1)
            
        for b, note in fav_pairs:
            if not b.isdigit() or not (4 <= len(b) <= 8):
                print(yellow(f"⚠  Skipping invalid BIN: {b}"))
                continue
                
            entry = cache.get(b, {})
            current_fav = entry.get("favorite", False)
            new_fav = True if note is not None else not current_fav
            
            if b not in cache:
                print(dim(f"  BIN {b} not in cache. Fetching details online to save..."))
                try:
                    res = fetch_bin(b, session=SESSION, proxy=args.proxy)
                    if not res.get("error"):
                        entry = {
                            "info": res.get("info", {}),
                            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "reviews": res.get("reviews", [])
                        }
                    else:
                        entry = {"info": {}, "reviews": []}
                except Exception:
                    entry = {"info": {}, "reviews": []}
            
            entry["favorite"] = new_fav
            if note is not None and new_fav:
                entry["favorite_note"] = note
            elif not new_fav:
                entry.pop("favorite_note", None)
            cache[b] = entry
            cache_modified = True
            
            status_str = green("Added to") if new_fav else red("Removed from")
            star_char = yellow("★") if new_fav else "☆"
            line = f"  {star_char} {bold(b)} has been {status_str} favorites."
            if new_fav and entry.get("favorite_note"):
                line += f"  {dim('Note:')} {entry['favorite_note']}"
            print(line)
            
        if cache_modified:
            save_cache(cache)
        sys.exit(0)

    # ── Remove Cache Commands ──────────────────────────────────────────────────
    if args.remove is not None or (bins and bins[0] == "remove"):
        remove_targets = args.remove if args.remove is not None else bins[1:]
        if not remove_targets:
            print(red("Error: Please specify one or more BINs to remove from cache."))
            sys.exit(1)
        cache_modified = False
        for b in remove_targets:
            if b in cache:
                del cache[b]
                cache_modified = True
                print(f"  🗑️  {bold(b)} has been deleted from cache.")
            else:
                print(dim(f"  BIN {b} is not in cache."))
        if cache_modified:
            save_cache(cache)
        sys.exit(0)

    if args.list_cache or "list" in bins or "list-cache" in bins:
        if not cache:
            print(dim("\n  (no BINs saved in cache yet)\n"))
            sys.exit(0)
        
        sorted_bins = sorted(cache.keys())
        print(f"\n{bold('📦 Saved BINs in Local Cache')}  —  {bold(len(sorted_bins))} BIN(s) total\n")
        
        h_bin     = "BIN"
        h_brand   = "Brand"
        h_type    = "Type"
        h_country = "Country"
        h_bank    = "Bank"
        h_reviews = "Reviews"
        
        print(f"  {bold(h_bin.ljust(8))}  {bold(h_brand.ljust(10))}  {bold(h_type.ljust(8))}  {bold(h_country.ljust(15))}  {bold(h_bank.ljust(35))}  {bold(h_reviews)}")
        print(dim("  " + "─" * 90))
        
        total_reviews = 0
        for b in sorted_bins:
            entry = cache[b]
            info = entry.get("info", {})
            reviews = entry.get("reviews", [])
            rev_len = len(reviews)
            total_reviews += rev_len
            
            brand   = (info.get("brand") or "UNKNOWN")[:10]
            type_   = (info.get("type") or "UNKNOWN")[:8]
            country = (info.get("country_name") or "UNKNOWN")[:15]
            bank    = (info.get("bank") or "UNKNOWN")[:35]
            
            print(f"  {cyan(b.ljust(8))}  {brand.ljust(10)}  {type_.ljust(8)}  {country.ljust(15)}  {dim(bank.ljust(35))}  {green(str(rev_len).rjust(7))}")
            
        print(dim("  " + "─" * 90))
        print(f"  {bold('Total Database Stats:')} {green(str(total_reviews))} reviews across {bold(str(len(sorted_bins)))} cached BIN(s)\n")
        sys.exit(0)

    if args.file:
        path = Path(args.file)
        if not path.exists(): sys.exit(f"File not found: {args.file}")
        bins += [l.strip() for l in path.read_text().splitlines() if l.strip().isdigit() and 4 <= len(l.strip()) <= 8]

    seen = set()
    bins = [b for b in bins if not (b in seen or seen.add(b))]

    if not bins:
        print_help()
        sys.exit(0)

    results = [None] * len(bins)

    # ── 3. Offline Mode Lookups ───────────────────────────────────────────────
    if args.offline:
        print(f"\n{bold('🔍 binx-cli')}  —  {len(bins)} BIN(s)  [{yellow('offline mode')}]\n")
        for i, b in enumerate(bins):
            if b in cache:
                cached_entry = cache[b]
                results[i] = {
                    "bin": b,
                    "info": cached_entry.get("info", {}),
                    "reviews": cached_entry.get("reviews", []),
                    "offline": True
                }
                n = len(results[i]["reviews"])
                suffix = "s" if n != 1 else ""
                print(f"  Fetching {bold(b)}... " + green(f"✓  [Loaded from Cache] ({n} review{suffix})"))
            else:
                results[i] = {
                    "bin": b,
                    "error": "Not found in local cache (offline mode)",
                    "info": {},
                    "reviews": []
                }
                print(f"  Fetching {bold(b)}... " + red("✗  Not cached"))

    else:
        notify_if_update_available()
        # Determine optimal concurrency if not set
        concurrency = args.concurrency
        if concurrency is None:
            if len(bins) <= 1:
                concurrency = 1
            elif len(bins) <= 5:
                concurrency = len(bins)
            elif len(bins) <= 50:
                concurrency = 15
            else:
                concurrency = 25

        if concurrency > 1 and len(bins) > 1:
            concurrency_source = "auto-calculated" if args.concurrency is None else "manual"
            print(f"\n{bold('🔍 binx-cli')}  —  {len(bins)} BIN(s)  [concurrency: {concurrency} ({concurrency_source})]\n")
        else:
            print(f"\n{bold('🔍 binx-cli')}  —  {len(bins)} BIN(s)  [sequential]\n")

        if concurrency > 1 and len(bins) > 1:
            import concurrent.futures
            import threading
            
            thread_local = threading.local()
            max_workers = min(concurrency, len(bins))
            
            def get_thread_session():
                if not hasattr(thread_local, "session"):
                    thread_local.session = cffi_requests.Session(
                        impersonate="chrome124",
                        curl_options={CurlOpt.DOH_URL: "https://cloudflare-dns.com/dns-query"}
                    )
                return thread_local.session
            
            def worker(idx, b):
                return idx, fetch_bin(b, session=get_thread_session(), proxy=args.proxy)
                
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(worker, idx, b): b for idx, b in enumerate(bins)}
                for future in concurrent.futures.as_completed(futures):
                    b = futures[future]
                    try:
                        idx, result = future.result()
                        if result.get("error"):
                            err_msg = result["error"]
                            # Cache fallback
                            if b in cache:
                                cached_entry = cache[b]
                                results[idx] = {
                                    "bin": b,
                                    "info": cached_entry.get("info", {}),
                                    "reviews": cached_entry.get("reviews", []),
                                    "fallback": True
                                }
                                print(f"  Fetching {bold(b)}... " + yellow(f"⚠  Failed ({err_msg}), loaded from cache"))
                            else:
                                results[idx] = result
                                print(f"  Fetching {bold(b)}... " + red(f"✗  {err_msg}"))
                                maybe_suggest_update(err_msg)
                        else:
                            results[idx] = result
                            n = len(result["reviews"])
                            suffix = "s" if n != 1 else ""
                            print(f"  Fetching {bold(b)}... " + green(f"✓  {n} review{suffix}"))
                    except Exception as e:
                        err_msg = str(e)
                        if b in cache:
                            cached_entry = cache[b]
                            results[idx] = {
                                "bin": b,
                                "info": cached_entry.get("info", {}),
                                "reviews": cached_entry.get("reviews", []),
                                "fallback": True
                            }
                            print(f"  Fetching {bold(b)}... " + yellow(f"⚠  Failed ({err_msg}), loaded from cache"))
                        else:
                            results[idx] = {"bin": b, "error": err_msg, "info": {}, "reviews": []}
                            print(f"  Fetching {bold(b)}... {red(f'✗  {err_msg}')}")
        else:
            # Sequential fallback
            for i, b in enumerate(bins):
                sys.stdout.write(f"  Fetching {bold(b)}... ")
                sys.stdout.flush()
                result = fetch_bin(b, session=SESSION, proxy=args.proxy)
                if result.get("error"):
                    err_msg = result["error"]
                    if b in cache:
                        cached_entry = cache[b]
                        results[i] = {
                            "bin": b,
                            "info": cached_entry.get("info", {}),
                            "reviews": cached_entry.get("reviews", []),
                            "fallback": True
                        }
                        print(yellow(f"⚠  Failed ({err_msg}), loaded from cache"))
                    else:
                        print(red(f"✗  {err_msg}"))
                        maybe_suggest_update(err_msg)
                        results[i] = result
                else:
                    n = len(result["reviews"])
                    print(green(f"✓  {n} review{'s' if n!=1 else ''}"))
                    results[i] = result
                if i < len(bins) - 1:
                    time.sleep(args.delay)

    # ── 4. Merge Successful Online Lookups into Cache ─────────────────────────
    total_reviews_added = 0
    total_bins_updated = 0
    if not args.offline:
        for r in results:
            if r is not None and not r.get("error") and not r.get("offline") and not r.get("fallback"):
                b = r["bin"]
                cached_entry = cache.get(b, {})
                
                # Fingerprint existing cached reviews
                cached_reviews = cached_entry.get("reviews", [])
                seen_fps = set()
                for rev in cached_reviews:
                    fp = (rev.get("user", ""), rev.get("rating", ""), rev.get("text", ""), rev.get("time", ""))
                    seen_fps.add(fp)
                
                # Merge and keep only unique reviews
                new_reviews = r.get("reviews", [])
                merged_reviews = list(cached_reviews)
                added_any = False
                reviews_added_for_this_bin = 0
                for rev in new_reviews:
                    fp = (rev.get("user", ""), rev.get("rating", ""), rev.get("text", ""), rev.get("time", ""))
                    if fp not in seen_fps:
                        merged_reviews.append(rev)
                        seen_fps.add(fp)
                        added_any = True
                        reviews_added_for_this_bin += 1
                
                # Sort reviews by date descending (newest first)
                merged_reviews.sort(key=lambda x: x.get("time", ""), reverse=True)
                
                # Prepare updated entry
                updated_entry = {
                    "info": r.get("info", {}),
                    "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "reviews": merged_reviews,
                }
                if cached_entry.get("favorite"):
                    updated_entry["favorite"] = True
                if cached_entry.get("favorite_note"):
                    updated_entry["favorite_note"] = cached_entry["favorite_note"]
                
                # Compare to detect changes
                if (b not in cache or 
                    cached_entry.get("info") != updated_entry["info"] or 
                    len(cached_reviews) != len(merged_reviews) or 
                    added_any):
                    cache[b] = updated_entry
                    cache_modified = True
                    total_bins_updated += 1
                    total_reviews_added += reviews_added_for_this_bin

    # ── 5. Print Output Results ───────────────────────────────────────────────
    for r in results:
        if r is not None:
            r["favorite"] = cache.get(r["bin"], {}).get("favorite", False)
            r["favorite_note"] = cache.get(r["bin"], {}).get("favorite_note")
            print_bin(r)

    # ── 6. JSON Export Check ──────────────────────────────────────────────────
    if args.json:
        # Filter out failed index spots just in case
        valid_results = [r for r in results if r is not None]
        out = {r["bin"]: {"info": r["info"], "reviews": r["reviews"]} for r in valid_results}
        Path(args.json).write_text(json.dumps(out, indent=2))
        print(f"{green('✅')} JSON saved to {bold(args.json)}")

    # ── 7. Save Cache (Only if modified, atomic/corruption-proof) ─────────────
    if cache_modified:
        save_cache(cache)

    bins_checked = len(results)
    bins_from_cache = sum(1 for r in results if r is not None and (r.get("offline") or r.get("fallback")))
    
    stats = [
        f"{bold(bins_checked)} BIN(s) checked",
        f"{yellow(bins_from_cache)} cached",
        f"{green(total_bins_updated)} modified",
        f"{cyan(total_reviews_added)} reviews added"
    ]
        
    print(f"{green('✅')} Done — {', '.join(stats)}.\n")

if __name__ == "__main__":
    main()
