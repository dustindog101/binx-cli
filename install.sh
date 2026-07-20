#!/usr/bin/env bash
# Install binx-cli from GitHub releases.
# Usage: curl -fsSL https://raw.githubusercontent.com/dustindog101/binx-cli/main/install.sh | bash
set -euo pipefail

REPO="dustindog101/binx-cli"
INSTALL_DIR="${BINX_HOME:-$HOME/.local/share/binx}"
BIN_DIR="${HOME}/.local/bin"
PYTHON="${PYTHON:-python3}"

echo "→ Installing binx-cli to ${INSTALL_DIR}"

mkdir -p "${INSTALL_DIR}" "${BIN_DIR}"

if command -v git >/dev/null 2>&1; then
  if [ -d "${INSTALL_DIR}/.git" ]; then
    echo "→ Updating existing install..."
    git -C "${INSTALL_DIR}" fetch --tags origin
    TAG=$(git -C "${INSTALL_DIR}" describe --tags "$(git -C "${INSTALL_DIR}" rev-list --tags --max-count=1)" 2>/dev/null || true)
    if [ -n "${TAG}" ]; then
      git -C "${INSTALL_DIR}" checkout "${TAG}" 2>/dev/null || git -C "${INSTALL_DIR}" pull --ff-only
    else
      git -C "${INSTALL_DIR}" pull --ff-only
    fi
  else
    echo "→ Cloning repository..."
    git clone --depth 1 "https://github.com/${REPO}.git" "${INSTALL_DIR}"
  fi
else
  echo "→ git not found; downloading latest release tarball..."
  TAG=$(curl -fsSL --max-time 10 "https://api.github.com/repos/${REPO}/releases/latest" \
    | "${PYTHON}" -c "import sys,json; print(json.load(sys.stdin).get('tag_name',''))")
  [ -n "${TAG}" ] || { echo "Could not resolve latest release tag."; exit 1; }
  TMP=$(mktemp -d)
  curl -fsSL --max-time 60 "https://github.com/${REPO}/archive/refs/tags/${TAG}.tar.gz" | tar -xz -C "${TMP}"
  cp -R "${TMP}/"*"/"* "${INSTALL_DIR}/"
  rm -rf "${TMP}"
fi

echo "→ Setting up Python environment..."
if [ ! -d "${INSTALL_DIR}/venv" ]; then
  "${PYTHON}" -m venv "${INSTALL_DIR}/venv"
fi
"${INSTALL_DIR}/venv/bin/pip" install -q --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install -q -r "${INSTALL_DIR}/requirements.txt"

WRAPPER="${BIN_DIR}/binx"
cat > "${WRAPPER}" <<EOF
#!/usr/bin/env bash
exec "${INSTALL_DIR}/venv/bin/python3" "${INSTALL_DIR}/binx.py" "\$@"
EOF
chmod +x "${WRAPPER}"

echo "✓ binx installed. Run: binx --version"
echo "  Update later with: binx update install"
