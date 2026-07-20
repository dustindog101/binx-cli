# Development Guide

Guide for maintaining, testing, and releasing binx-cli.

## Project layout

```
binx-cli/
├── binx.py              # Main CLI (single-file app)
├── install.sh           # User install script
├── requirements.txt     # Runtime deps
├── requirements-dev.txt # Dev/test deps
├── tests/               # pytest unit tests
├── .github/workflows/
│   ├── ci.yml           # Runs on push/PR
│   └── release.yml      # Runs on version tags
└── docs/
    ├── UPDATES.md       # User update docs
    └── DEVELOPMENT.md   # This file
```

## Local setup

```bash
git clone https://github.com/dustindog101/binx-cli.git
cd binx-cli

python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

### Run locally

```bash
python3 binx.py 403306
python3 binx.py --version
python3 binx.py update
```

### Link as global command (optional)

```bash
ln -sf "$(pwd)/venv/bin/python3" ~/.local/bin/binx-python  # not needed if using install.sh
```

Or create a wrapper like:

```bash
#!/usr/bin/env bash
exec "/path/to/binx-cli/venv/bin/python3" "/path/to/binx-cli/binx.py" "$@"
```

## Running tests

```bash
pytest -q                  # unit tests (no network)
pytest -q tests/ -v        # verbose

# Manual integration smoke test
python3 binx.py 403306 --no-color
```

CI runs automatically on every push/PR to `main`:
- Unit tests on Python 3.10 and 3.12
- Live API smoke test against `binx.cz`

## Versioning

Version lives in `binx.py`:

```python
__version__ = "1.2.0"
```

**Always bump `__version__` before cutting a release.** The update system compares this against GitHub release tags.

## Releasing a new version

### 1. Make your changes

```bash
git checkout main
git pull origin main
# ... edit code ...
pytest -q
```

### 2. Bump version

Update `__version__` in `binx.py` (e.g. `1.2.0` → `1.3.0`).

### 3. Commit and push to main

```bash
git add binx.py README.md docs/  # etc.
git commit -m "Add feature X and bump version to 1.3.0"
git push origin main
```

### 4. Tag and push the release

Tags must start with `v` (e.g. `v1.3.0`):

```bash
git tag v1.3.0
git push origin v1.3.0
```

Pushing the tag triggers `.github/workflows/release.yml` which:
1. Runs the full test suite
2. Creates a GitHub Release at `https://github.com/dustindog101/binx-cli/releases`
3. Attaches `binx.py`, `requirements.txt`, and `install.sh` as release assets

### 5. Verify

```bash
# After CI finishes (~1-2 min)
gh release view v1.3.0
binx update          # should show the new version
binx update install  # should install it
```

### Manual release (if CI fails)

```bash
gh release create v1.3.0 \
  --title "binx-cli v1.3.0" \
  --notes "Release notes here." \
  binx.py requirements.txt install.sh
```

## Update system architecture

| Component | Location | Purpose |
|-----------|----------|---------|
| Version constant | `binx.py` `__version__` | Installed version |
| Update cache | `~/.cache/binx/update_check.json` | 24h GitHub API cache |
| Release API | `api.github.com/repos/dustindog101/binx-cli/releases/latest` | Latest version check |
| Git update | `git pull --ff-only` | Dev installs with `.git` |
| Tarball update | GitHub archive URL | `install.sh` / non-git installs |

### Resilience rules (don't break these)

- Update checks must **never crash** the main CLI
- Failed network calls must **preserve** the last good cache
- `update install` must **backup** before replacing `binx.py`
- Downloaded files must be **validated** before install
- API errors during lookups use **cached** update info only (no extra network call)

### Environment variables

| Variable | Effect |
|----------|--------|
| `BINX_SKIP_UPDATE_CHECK=1` | Disable background update hints |
| `BINX_HOME` | Override install directory (used by `install.sh`) |

## Domain changes

API config is centralized at the top of `binx.py`:

```python
DOMAIN = "binx.cz"
API = f"https://api.{DOMAIN}/api"
```

If the domain changes again: update `DOMAIN`, bump version, release.

## CI/CD workflows

### `ci.yml` — continuous integration

Triggers: push/PR to `main`, published releases

- Matrix test on Python 3.10, 3.12
- Integration smoke test against live API

### `release.yml` — automated releases

Triggers: push of tags matching `v*`

- Runs tests
- Creates GitHub Release with assets

## Adding new commands

1. Add handler in `main()` (follow existing pattern: `bins[0] == "command"`)
2. Add help text in `print_help()`
3. Add argparse flag if needed in `parse_args()`
4. Add tests in `tests/test_binx.py`
5. Update `README.md` and docs if user-facing

## First release checklist

If this is the first release on the repo:

```bash
# 1. Ensure everything is committed on main
git push origin main

# 2. Create the first tag
git tag v1.2.0
git push origin v1.2.0

# 3. Wait for GitHub Actions to finish
gh run list --workflow=release.yml

# 4. Confirm release exists
gh release list
```

After the first release, `binx update` will work for all users.
