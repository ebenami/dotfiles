#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/fnm"
export PATH="$HOME/.local/bin:$HOME/.local/share/fnm:$PATH"

install_script="$(mktemp)"
trap 'rm -f "$install_script"' EXIT

if ! command -v fzf >/dev/null 2>&1; then
  echo 'Install fzf with Homebrew or from its official release, then rerun setup.' >&2
  exit 1
fi
if ! command -v starship >/dev/null 2>&1; then
  curl -fsSL https://starship.rs/install.sh -o "$install_script"
  sh "$install_script" -y -b "$HOME/.local/bin"
fi
if ! command -v fnm >/dev/null 2>&1; then
  curl -fsSL https://fnm.vercel.app/install -o "$install_script"
  bash "$install_script" --force-install --install-dir "$HOME/.local/share/fnm" --skip-shell
fi
if ! command -v zoxide >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh -o "$install_script"
  sh "$install_script" --bin-dir "$HOME/.local/bin"
fi
if [[ -d "$HOME/.nvm/versions/node" ]]; then
  for version_dir in "$HOME"/.nvm/versions/node/v*; do
    [[ -d "$version_dir" ]] || continue
    fnm install "${version_dir##*/v}"
  done
  fnm default 24.18.0
fi

# Python builds need the Xcode command-line tools and these Homebrew libraries.
if command -v brew >/dev/null 2>&1 && [[ ! -x "$HOME/.pyenv/bin/pyenv" ]]; then
  brew install pyenv openssl@3 readline sqlite3 xz zlib tcl-tk
fi

# A clean Mac may have no nvm versions to migrate. Install the selected Node version.
fnm install 24.18.0
fnm default 24.18.0
