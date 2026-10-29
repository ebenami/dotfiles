# Personal dotfiles

Portable macOS and Ubuntu preferences, independent of employer services. This
repository starts with fresh history and only reviewed configuration files.

```sh
git clone git@github.com:ebenami/dotfiles.git "$HOME/dotfiles"
bash "$HOME/dotfiles/setup/install.sh"
# Existing tools already installed? Apply preferences and install the command only:
bash "$HOME/dotfiles/setup/install.sh" --config-only
```

Run as your normal user. macOS requires Homebrew/Xcode tools for missing Python
build dependencies and an existing fzf installation. Ubuntu attempts apt only when
sudo is available without prompting, then continues with user-local tools where
possible. IDE applications, terminal applications, fonts, and account sign-in are
installed separately. This installer never schedules work authentication.

## Structure

| Path | Responsibility |
| --- | --- |
| `shell/` | Zsh, general aliases, platform integrations, Starship; no downloads on shell startup |
| `config/shared/` | Vim, Git defaults, common terminal settings, general AI/editor preferences |
| `config/macos/` | Mac-specific paths, Monaco for Ghostty, and retained IDE version snapshots |
| `config/ubuntu/` | Monospace Ghostty override and Terminator default-profile appearance |
| `config/manifest.json` | Explicit file/platform allowlist and nested key ownership |
| `config/tools.json` | Recorded public Vim/skill sources, Python inventory, editor extensions |
| `setup/env.py` | Preview, capture/apply, structured merges, conflicts, backups, export screening |
| `setup/restore.py` | Restore missing pinned tool sources and extensions |
| `ai/global-rules.md` | User-authored instructions shared between supported agents |

## Explicit sync

```sh
dotfiles-env status
dotfiles-env status --diff
dotfiles-env capture              # preview local -> repo
dotfiles-env capture --write
dotfiles-env apply                # preview repo -> local
dotfiles-env apply --write
dotfiles-env audit                # screen the entire repository export
```

Review `git diff` and untracked files before committing/pushing. On the other
machine, pull and apply. Git actions never run automatically during sync.

Linked files update their repository source immediately. Settings rewritten by
applications are copied/merged; close those applications before applying. Backup
and conflict state lives under `${XDG_STATE_HOME:-~/.local/state}/personal`.
Conflicts stop the operation before writes; resolve deliberately with
`capture --write --force` or `apply --write --force` after reviewing differences.
Missing local files do not delete repository files.

Each structured entry's `owned` object selects managed keys. A `true` leaf is an
ownership marker; values come from its source configuration. Capture excludes
unowned keys, so shared client files can contain independently managed overlays.
New files and keys must be reviewed and registered explicitly. `discover` lists
existing known targets; it does not automatically import application state.

Secret-pattern screening and personal/work separation checks are safeguards, not
a complete secret detector. Synthetic test fixtures and detector source have
explicit pattern-check exemptions. Never store credential files, OAuth caches,
private keys, transcripts, project trust state, or API tokens here.

## Machine and work overlays

Machine-specific shell additions belong in
`${XDG_CONFIG_HOME:-~/.config}/dotfiles/local.zsh`, outside Git.
The shell loads `dotfiles/work.zsh` only when a separate work installer explicitly
creates it. General setup never creates that work link or depends on a work checkout.

Git defaults omit identity and do not change credential helpers. Set your own
personal identity locally. A separate work installer can scope another identity
by directory. Keep this checkout outside any such work directory.

XDG configuration paths are respected for Linux apps and terminal settings;
macOS editor preferences retain their native Application Support locations.

## Terminals

See [terminal compatibility](docs/terminals.md). Ghostty settings and existing
shortcuts are retained. Ubuntu also applies a Terminator appearance profile without
modifying shortcuts, layouts, other profiles, or custom commands.

## Verification

```sh
uv run --default-index https://pypi.org/simple --script setup/test_env.py
uv run --default-index https://pypi.org/simple --script setup/test_portability.py
```

The tests run in temporary homes. They cover both platforms' configuration files,
secret exclusion, ownership, merges, backups, conflicts, and preservation of local
Terminator settings. Real desktop rendering and application versions still need
validation on the destination machine.

Further improvements: retire unused IDE snapshots and Python versions, pin shell
plugin revisions and downloaded installers, and add real Ubuntu CI coverage.
