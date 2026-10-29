#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.pyenv/bin:$HOME/.local/share/fnm:$PATH"
install_script="$(mktemp)"
trap 'rm -f "$install_script"' EXIT
if ! command -v uv >/dev/null 2>&1; then
  curl -fsSL https://astral.sh/uv/install.sh -o "$install_script"
  UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$install_script"
fi
uv_bin="$(command -v uv)"
if command -v pyenv >/dev/null 2>&1; then
  pyenv_bin="$(command -v pyenv)"
else
  pyenv_checkout="$HOME/.local/share/dotfiles-pyenv"
  if [[ ! -d "$pyenv_checkout/.git" ]]; then
    git clone --depth 1 https://github.com/pyenv/pyenv.git "$pyenv_checkout"
  fi
  ln -sf "$pyenv_checkout/bin/pyenv" "$HOME/.local/bin/pyenv"
  pyenv_bin="$HOME/.local/bin/pyenv"
fi
export PYENV_ROOT="$HOME/.pyenv"

# Return the real executable only for a usable interpreter matching the request.
working_python() {
  "$1" -I -c '
import bz2, ctypes, lzma, os, sqlite3, ssl, sys, zlib
requested = sys.argv[1]
actual = ".".join(map(str, sys.version_info[:3]))
matches = actual.startswith("3.10.") if requested.startswith("3.10.") else actual == requested
sys.exit(1) if not matches else print(os.path.realpath(sys.executable))
' "$2" 2>/dev/null
}

install_linux_python() {
  local version="$1" target="$PYENV_ROOT/versions/$1" selected='' candidate executable directory
  local path_dirs=()
  if working_python "$target/bin/python3" "$version" >/dev/null; then
    echo "Using existing Python selection: $version"
    return
  fi
  # Search PATH and other pyenv installations before downloading another Python.
  IFS=: read -r -a path_dirs <<< "$PATH"
  for directory in "${path_dirs[@]}"; do
    for candidate in "python${version%.*}" python3 python; do
      executable="${directory:-.}/$candidate"
      if [[ -x "$executable" ]] && selected="$(working_python "$executable" "$version")"; then
        break 2
      fi
      selected=''
    done
  done
  if [[ -z "$selected" ]]; then
    for executable in "$PYENV_ROOT"/versions/*/bin/python3; do
      if selected="$(working_python "$executable" "$version")"; then
        break
      fi
      selected=''
    done
  fi
  if [[ -z "$selected" ]]; then
    # Prebuilt interpreters need neither sudo nor local Python build libraries.
    if ! UV_PYTHON_INSTALL_BIN=0 "$uv_bin" python install "$version" 2>"$install_script"; then
      printf '%s\n' "$(< "$install_script")" >&2
      if [[ "$(< "$install_script")" != *'No download found for request:'* ]]; then
        return 1
      fi
      echo 'Refreshing user-local uv to update its Python download catalog.' >&2
      curl -fsSL https://astral.sh/uv/install.sh -o "$install_script"
      UV_INSTALL_DIR="$HOME/.local/bin" UV_NO_MODIFY_PATH=1 sh "$install_script"
      uv_bin="$HOME/.local/bin/uv"
      UV_PYTHON_INSTALL_BIN=0 "$uv_bin" python install "$version"
    else
      printf '%s' "$(< "$install_script")" >&2
    fi
    executable="$("$uv_bin" python find --managed-python --no-python-downloads "$version")"
    selected="$(working_python "$executable" "$version")" || {
      echo "Downloaded Python $version failed its core module check." >&2
      return 1
    }
  fi
  mkdir -p "$PYENV_ROOT/versions"
  if [[ -e "$target" || -L "$target" ]]; then
    rm -rf -- "$target"
  fi
  # A system prefix can contain several Python versions; link the selected binary,
  # rather than the whole prefix (whose python3 may be a different minor version).
  mkdir -p "$target/bin"
  for candidate in python python3 "python${version%.*}"; do
    ln -s "$selected" "$target/bin/$candidate"
  done
  if "$selected" -I -c 'import pip' 2>/dev/null; then
    for candidate in pip pip3 "pip${version%.*}"; do
      printf '#!/usr/bin/env bash\nexec "%s" -m pip "$@"\n' "$target/bin/python" > "$target/bin/$candidate"
      chmod +x "$target/bin/$candidate"
    done
  fi
  echo "Using $selected for pyenv selection $version"
}

# Ubuntu/Linux reuses any working 3.10 patch release for the recorded 3.10 selection.
if [[ -f "$repo_root/config/shared/python/pyenv-version" ]]; then
  while IFS= read -r version; do
    [[ -n "$version" && "$version" != system ]] || continue
    if [[ "$(uname -s)" == Linux ]]; then
      install_linux_python "$version"
    else
      "$pyenv_bin" install -s "$version"
    fi
  done < "$repo_root/config/shared/python/pyenv-version"
  "$pyenv_bin" rehash
fi
mkdir -p "$HOME/.vim/backups" "$HOME/.vim/swapfiles"
