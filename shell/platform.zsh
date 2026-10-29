typeset -U path PATH
path=("$HOME/.local/bin" "$HOME/bin" $path)

if [[ "$OSTYPE" == darwin* ]]; then
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
  [[ -d /opt/homebrew/opt/findutils/libexec/gnubin ]] && path=(/opt/homebrew/opt/findutils/libexec/gnubin $path)
  [[ -d /opt/homebrew/opt/rustup/bin ]] && path=(/opt/homebrew/opt/rustup/bin $path)
  [[ -d /Applications/PyCharm.app/Contents/MacOS ]] && path=(/Applications/PyCharm.app/Contents/MacOS $path)
  if [[ -n "$SSH_AUTH_SOCK" ]] && (( $+commands[ssh-add] )); then
    ssh-add -q 2>/dev/null
  fi
fi

export PYENV_ROOT="$HOME/.pyenv"
[[ -d "$PYENV_ROOT/bin" ]] && path=("$PYENV_ROOT/bin" $path)
[[ -d "$HOME/.cargo/bin" ]] && path=("$HOME/.cargo/bin" $path)
[[ -d "$HOME/.local/share/fnm" ]] && path=("$HOME/.local/share/fnm" $path)

export SDKMAN_DIR="$HOME/.sdkman"
[[ -f "$SDKMAN_DIR/bin/sdkman-init.sh" ]] && source "$SDKMAN_DIR/bin/sdkman-init.sh"
