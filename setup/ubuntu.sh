#!/usr/bin/env bash
set -euo pipefail

mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$HOME/.local/share/fnm:$PATH"

apt_command=()
if [[ "$EUID" -eq 0 ]]; then
  apt_command=(apt-get)
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  apt_command=(sudo -n apt-get)
else
  echo 'No passwordless sudo access; skipping system packages and continuing with user-local setup.' >&2
fi
if [[ "${#apt_command[@]}" -gt 0 ]]; then
  if ! { "${apt_command[@]}" update &&
    "${apt_command[@]}" install -y ca-certificates curl direnv fzf git unzip zsh build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncurses-dev xz-utils tk-dev; }; then
    echo 'System package installation failed; continuing with user-local setup.' >&2
  fi
fi

missing=()
for tool in curl git unzip zsh; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    missing+=("$tool")
  fi
done
if [[ "${#missing[@]}" -gt 0 ]]; then
  echo "Missing required tools: ${missing[*]}. Ask an administrator to install them, or add user-local versions to PATH, then rerun setup." >&2
  exit 1
fi
for tool in direnv fzf; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Optional tool $tool is unavailable; its shell integration will be skipped." >&2
  fi
done

install_script="$(mktemp)"
trap 'rm -f "$install_script"' EXIT

if ! command -v starship >/dev/null 2>&1; then
  curl -fsSL https://starship.rs/install.sh -o "$install_script"
  sh "$install_script" -y -b "$HOME/.local/bin"
fi
if ! command -v fnm >/dev/null 2>&1; then
  curl -fsSL https://fnm.vercel.app/install -o "$install_script"
  bash "$install_script" --skip-shell
fi
if ! command -v zoxide >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/ajeetdsouza/zoxide/main/install.sh -o "$install_script"
  sh "$install_script" --bin-dir "$HOME/.local/bin"
fi
fnm install 24.18.0
fnm default 24.18.0
