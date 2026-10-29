#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
config_only=false
case "${1:-}" in
  --config-only) config_only=true ;;
  '') ;;
  *) echo 'Usage: install.sh [--config-only]' >&2; exit 2 ;;
esac
if ! "$config_only"; then
case "$(uname -s)" in
  Darwin) bash "$repo_root/setup/macos.sh" ;;
  Linux)
    . /etc/os-release
    if [[ "${ID:-}" != ubuntu && " ${ID_LIKE:-} " != *" ubuntu "* ]]; then
      echo 'This setup script supports Ubuntu Linux.' >&2
      exit 1
    fi
    bash "$repo_root/setup/ubuntu.sh"
    ;;
  *) echo 'This setup script supports macOS and Ubuntu.' >&2; exit 1 ;;
esac

plugin_home="${XDG_DATA_HOME:-$HOME/.local/share}/dotfiles-shell-plugins"
zinit_home="${XDG_DATA_HOME:-$HOME/.local/share}/zinit/zinit.git"
mkdir -p "$plugin_home" "$(dirname "$zinit_home")"

clone_once() {
  local url="$1" target="$2"
  if [[ ! -d "$target/.git" ]]; then
    git clone --depth 1 "$url" "$target"
  fi
}

clone_once https://github.com/zdharma-continuum/zinit.git "$zinit_home"
clone_once https://github.com/ohmyzsh/ohmyzsh.git "$plugin_home/ohmyzsh"
clone_once https://github.com/Aloxaf/fzf-tab.git "$plugin_home/fzf-tab"
clone_once https://github.com/zsh-users/zsh-autosuggestions.git "$plugin_home/zsh-autosuggestions"
clone_once https://github.com/zsh-users/zsh-syntax-highlighting.git "$plugin_home/zsh-syntax-highlighting"

bash "$repo_root/setup/tools.sh"
fi
mkdir -p "$HOME/.local/bin"
ln -sfn "$repo_root/setup/run" "$HOME/.local/bin/dotfiles-env"
"$repo_root/setup/run" apply --write
if ! "$config_only"; then
  python3 "$repo_root/setup/restore.py" --skills --extensions
fi
printf '%s\n' 'Open a new Zsh shell. Use dotfiles-env status to inspect preferences.'
