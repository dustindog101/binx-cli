# Updating binx-cli

binx-cli can check for and install updates from GitHub. Updates are optional — if GitHub is unreachable, binx keeps working normally.

## Check for updates

```bash
binx update
# or
binx --check-update
```

This compares your installed version against the latest [GitHub Release](https://github.com/dustindog101/binx-cli/releases).

**What you'll see:**

| Result | Meaning |
|--------|---------|
| `✓ binx-cli v1.2.0 is up to date.` | You're on the latest release |
| `⬆ Update available: v1.1.0 → v1.2.0` | A newer release exists |
| `Could not reach GitHub (offline).` | Network issue — binx still works |

Update checks are cached for 24 hours so binx doesn't hit GitHub on every lookup.

## Install an update

```bash
binx update install
```

**Git install** (if you cloned the repo):
- Runs `git fetch` + `git pull --ff-only`
- Refreshes Python dependencies if a `venv` exists

**Standard install** (via `install.sh`):
- Downloads the latest release tarball from GitHub
- Validates the file before replacing anything
- Backs up your current `binx.py` before updating
- Restores the backup automatically if something goes wrong

## Fresh install

```bash
npm install -g binx-cli
# or
curl -fsSL https://raw.githubusercontent.com/dustindog101/binx-cli/main/install.sh | bash
```

This installs to `~/.local/share/binx` and adds `binx` to `~/.local/bin`.

Make sure `~/.local/bin` is in your `PATH`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Automatic update hints

When you run a normal BIN lookup, binx may show a quiet hint if an update is available:

```
Update available: v1.2.0 — run `binx update install`
```

To disable all background update checks:

```bash
export BINX_SKIP_UPDATE_CHECK=1
```

## Version info

```bash
binx --version
```

Shows the installed version and current API domain (`binx.cz`).

## Troubleshooting

**"No releases published yet"**
- The project hasn't tagged a release on GitHub yet. You can still use binx normally.

**Update install fails**
- Check your internet connection
- If installed via git, make sure you don't have uncommitted changes blocking `git pull`
- Try a fresh install with the `install.sh` command above

**Still on old domain (binx.vip)**
- Run `binx update install` to get the latest version pointing at `binx.cz`
