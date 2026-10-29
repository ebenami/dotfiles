#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["tomlkit==0.13.3", "json5==0.12.1", "configobj==5.0.9"]
# ///
"""Explicit, credential-free capture and application of portable configuration."""
import argparse
import configparser
import copy
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import json5
import tomlkit
from configobj import ConfigObj

ROOT = Path(__file__).resolve().parent.parent
WORK_CONTENT = re.compile(r'mobileye|remdevme|spartacus|snippets-mcp|gitlab\.mobileye|720146705806|OneDrive\s*-?\s*Mobileye|/Users/eranba|/home/eranba', re.I)
SECRET = re.compile(r"(?:^|[_.-])(?:password|passwd|token|secret|client_secret|access_token|refresh_token|id_token|api_key|apikey|private_key|aws_access_key_id|aws_secret_access_key|aws_session_token|authorization|bearer_token)(?:$|[_.-])", re.I)
SECRET_VALUE = re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}|(?:AKIA|ASIA)[A-Z0-9]{16}|(?:glpat-|ghp_|github_pat_|sk-proj-)[A-Za-z0-9_-]{15,}|-----BEGIN .*PRIVATE KEY-----|https?://[^\s/@]+:[^\s/@]+@")
TEXT_SECRET = re.compile(r"((?:X-[A-Za-z-]*(?:TOKEN|KEY)|Authorization|api[_-]?key|api[_-]?token|password|client_secret)\s*[:=]\s*[\"']?)(?:Bearer\s+)?[A-Za-z0-9_./+=-]{16,}", re.I)


def redact_text(text):
    return TEXT_SECRET.sub(lambda m: m.group(1) + '${LOCAL_SECRET}', text)


LOCAL_KEYS = {'projects', 'history', 'lastLoggedInUser', 'accounts', 'oauth', 'auth', 'installation_id', 'installationId', 'session', 'sessions'}


def host_platform():
    return 'macos' if sys.platform == 'darwin' else 'ubuntu'


def xdg(home, name, default):
    # Isolated test homes must never inherit the real user's XDG directories.
    return Path(os.environ.get(name, str(home / default))) if home == Path.home() else home / default


def profile(root):
    return load(root / 'config/profile.json', {}).get('profile', 'snippets')


def expand(value, home, root, platform=None):
    config_home = xdg(home, 'XDG_CONFIG_HOME', '.config')
    appbase = home / 'Library/Application Support' if (platform or host_platform()) == 'macos' else config_home
    value = value.replace('${SNIPPETS}', str(root)).replace('${DOTFILES}', str(root)).replace('${HOME}', str(home)).replace('${APP_CONFIG}', str(appbase)).replace('${CONFIG_HOME}', str(config_home))
    for product in re.findall(r'\$\{JETBRAINS_([A-Za-z]+)\}', value):
        versions = sorted(p.name for p in (appbase / 'JetBrains').glob(product + '[0-9]*') if p.is_dir())
        recorded = load(root / 'config/tools.json', {}).get('jetbrains_versions', {})
        chosen = versions[-1] if versions else recorded.get(product, product)
        value = value.replace('${JETBRAINS_' + product + '}', chosen)
    return value


def portable(value, home, root, key=''):
    if isinstance(value, dict):
        return {k: portable(v, home, root, k) for k, v in value.items()
                if not SECRET.search(k) and not re.search(r'password|secret|(?:access|refresh|id|api)Token|ApiKey|PrivateKey', k, re.I) and k not in LOCAL_KEYS and not (isinstance(v, str) and SECRET_VALUE.search(v))}
    if isinstance(value, list):
        return [portable(x, home, root, key) for x in value if not (isinstance(x, str) and SECRET_VALUE.search(x))]
    if isinstance(value, str):
        if key == 'command' and re.search(r'/\.nvm/versions/node/[^/]+/bin/(npx|node|npm)$', value):
            return value.rsplit('/', 1)[-1]
        value = redact_text(value)
        for path, replacement in [(root, '${SNIPPETS}'), (home, '${HOME}')]:
            variants = {str(path), str(path.resolve())}
            variants.update(v.removeprefix('/private') for v in list(variants) if v.startswith('/private/var/'))
            for variant in sorted(variants, key=len, reverse=True):
                value = value.replace(variant, replacement)
        return value
    return value


def deep_merge(current, incoming):
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            deep_merge(current[key], value)
        else:
            current[key] = copy.deepcopy(value)
    return current


def normalize(text, kind, home, root):
    if kind == 'configobj':
        return structured_dump(portable(structured_load(text, kind), home, root), kind)
    if kind in ('json', 'jsonc'):
        return json.dumps(portable(json5.loads(text), home, root), indent=2, ensure_ascii=False) + '\n'
    if kind == 'toml':
        doc = tomlkit.parse(text)
        data = portable(doc.unwrap(), home, root)
        return tomlkit.dumps(data)
    if kind == 'ini':
        doc = configparser.RawConfigParser(strict=False, interpolation=None)
        doc.read_string(text)
        for section in doc.sections():
            for key, value in list(doc.items(section)):
                if SECRET.search(key) or SECRET_VALUE.search(value) or section.lower().startswith('credential '):
                    doc.remove_option(section, key)
                else:
                    doc.set(section, key, portable(value, home, root))
        output = io.StringIO()
        doc.write(output)
        return output.getvalue()
    if kind == 'xml':
        doc = ET.fromstring(text)
        for parent in doc.iter():
            for child in list(parent):
                name = child.get('name', '')
                if SECRET.search(name) or any(SECRET_VALUE.search(v) for v in child.attrib.values()):
                    parent.remove(child)
        text = ET.tostring(doc, encoding='unicode') + '\n'
    text = redact_text(text)
    if SECRET_VALUE.search(text):
        raise ValueError('possible embedded credential; file requires a manual configuration-only export')
    return portable(text, home, root)


def structured_load(text, kind):
    if kind in ('json', 'jsonc'):
        return json5.loads(text) if text.strip() else {}
    if kind == 'toml':
        return tomlkit.parse(text).unwrap()
    if kind == 'configobj':
        return ConfigObj(text.splitlines(), interpolation=False, encoding='utf-8', raise_errors=True).dict()
    doc = configparser.RawConfigParser(strict=False, interpolation=None)
    doc.read_string(text)
    return {s: dict(doc.items(s)) for s in doc.sections()}


def structured_dump(data, kind):
    if kind in ('json', 'jsonc'):
        return json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    if kind == 'toml':
        return tomlkit.dumps(data)
    if kind == 'configobj':
        doc = ConfigObj(interpolation=False, encoding='utf-8')
        doc.update(data)
        return b'\n'.join(doc.write()).decode('utf-8') + '\n'
    doc = configparser.RawConfigParser(interpolation=None)
    doc.read_dict(data)
    output = io.StringIO()
    doc.write(output)
    return output.getvalue()


def project(data, ownership):
    if not isinstance(data, dict):
        raise ValueError('managed configuration table changed type')
    return {key: project(data[key], selection) if isinstance(selection, dict) else data[key]
            for key, selection in ownership.items() if key in data}


def normalize_entry(text, entry, home, root):
    normalized = normalize(text, entry.get('format', 'text'), home, root)
    if entry.get('omit_mcp'):
        doc = tomlkit.parse(normalized)
        servers = doc.get('mcp_servers', {})
        for name in entry['omit_mcp']:
            servers.pop(name, None)
        normalized = tomlkit.dumps(doc)
    if entry.get('keys'):
        data = json.loads(normalized)
        normalized = json.dumps({k: data[k] for k in entry['keys'] if k in data}, indent=2, ensure_ascii=False) + '\n'
    if entry.get('select'):
        data = json.loads(normalized)
        def platform_setting(key, value):
            return bool(re.search(r'\.(osx|linux|windows)(?:\.|$)', key) or re.search(r'/Applications/|/opt/homebrew/|[A-Z]:\\', json.dumps(value)))
        wanted = entry['select'] == 'platform'
        normalized = json.dumps({k:v for k,v in data.items() if platform_setting(k,v) == wanted}, indent=2, ensure_ascii=False) + '\n'
    if 'owned' in entry:
        kind = entry['format']
        normalized = structured_dump(project(structured_load(normalized, kind), entry['owned']), kind)
    return normalized


def merged(current, incoming, kind):
    if kind == 'configobj':
        doc = ConfigObj(current.splitlines(), interpolation=False, encoding='utf-8', raise_errors=True)
        doc.merge(structured_load(incoming, kind))
        return b'\n'.join(doc.write()).decode('utf-8') + '\n'
    if kind in ('json', 'jsonc'):
        base = json5.loads(current) if current.strip() else {}
        data = json5.loads(incoming)
        if isinstance(base, dict) and isinstance(data, dict):
            data = deep_merge(base, data)
        return json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    if kind == 'toml':
        base = tomlkit.parse(current) if current.strip() else tomlkit.document()
        def merge_table(target, values):
            for key, value in values.items():
                if isinstance(value, dict) and hasattr(target.get(key), 'items'):
                    merge_table(target[key], value)
                else:
                    target[key] = value
        merge_table(base, tomlkit.parse(incoming).unwrap())
        return tomlkit.dumps(base)
    if kind == 'ini':
        doc = configparser.RawConfigParser(strict=False, interpolation=None)
        if current.strip():
            doc.read_string(current)
        doc.read_string(incoming)
        output = io.StringIO()
        doc.write(output)
        return output.getvalue()
    if kind == 'xml' and current.strip():
        base, new = ET.fromstring(current), ET.fromstring(incoming)
        def merge_node(target, node):
            target.attrib.update(node.attrib)
            if node.text and node.text.strip():
                target.text = node.text
            grouped = {}
            for child in node:
                identity = next(((k, child.get(k)) for k in ('name', 'key', 'id') if child.get(k) is not None), None)
                if identity is None:
                    grouped.setdefault(child.tag, []).append(child)
                    continue
                match = next((c for c in target if c.tag == child.tag and c.get(identity[0]) == identity[1]), None)
                if match is None:
                    target.append(copy.deepcopy(child))
                else:
                    merge_node(match, child)
            for tag, children in grouped.items():
                for old in list(target):
                    if old.tag == tag:
                        target.remove(old)
                target.extend(copy.deepcopy(children))
        merge_node(base, new)
        return ET.tostring(base, encoding='unicode') + '\n'

    return incoming


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.snippets-tmp')
    tmp.write_text(text)
    tmp.chmod(0o600)
    tmp.replace(path)


def load(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def entries(root, platform):
    return [e for e in load(root / 'config/manifest.json', []) if e.get('platform', platform) == platform]


def audit_repository(root):
    """Screen every export file, including files outside the sync manifest."""
    checked = 0
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if any(part in {'.git', '__pycache__', '.venv', 'node_modules'} for part in rel.parts):
            continue
        if path.is_symlink():
            raise RuntimeError(f'Export symlink needs review: {rel}')
        if not path.is_file():
            continue
        text = path.read_text()
        # Synthetic fixtures and the detector definition contain known patterns.
        fixture = path.name.startswith('test_') or rel == Path('setup/env.py')
        if not fixture and (SECRET_VALUE.search(text) or redact_text(text) != text or WORK_CONTENT.search(text)):
            raise RuntimeError(f'Export content needs review: {rel}')
        checked += 1
    print(f'{checked} export files screened. Review git diff before publishing; pattern checks cannot prove absence of secrets.')


def config_sync(args):
    home, root = args.home.resolve(), args.repo.resolve()
    platform = args.platform or host_platform()
    namespace = profile(root)
    state_path = xdg(home, 'XDG_STATE_HOME', '.local/state') / namespace / 'config-state.json'
    state = load(state_path, {})
    operations = []
    pending = {}
    errors = []
    for e in entries(root, platform):
        target = Path(expand(e['target'], home, root, platform))
        source = root / e['source']
        kind = e.get('format', 'text')
        if not source.exists() and not target.exists():
            continue
        try:
            current = pending.get(target, target.read_text() if target.exists() else '')
            local = normalize_entry(current, e, home, root) if current else ''
            saved = normalize_entry(source.read_text(), e, home, root) if source.exists() else ''
            if namespace == 'personal' and args.command in ('capture', 'apply'):
                candidate = local if args.command == 'capture' else saved
                if WORK_CONTENT.search(candidate):
                    errors.append(f"Work-specific content rejected from personal {args.command}: {e['target']}")
                    continue
            linked = target.is_symlink() and target.resolve() == source.resolve()
            key = e['target'] + ':' + e['source']
            baseline = state.get(key)
            conflict = bool(baseline and digest(local) != baseline['local'] and digest(saved) != baseline['repo'] and local != saved)
            if conflict and args.command != 'status' and not args.force:
                errors.append(f"CONFLICT {e['target']}: both local and repository settings changed; review status, then choose capture/apply --force")
                continue
            if args.command == 'capture':
                if not target.exists():
                    continue
                if linked or local == saved:
                    state[key] = {'local': digest(local), 'repo': digest(saved)}
                    continue
                operations.append(('capture', source, local, e, local))
            elif args.command == 'apply':
                if not source.exists():
                    continue
                if e['mode'] == 'link':
                    if not linked:
                        operations.append(('link', target, str(source), e, saved))
                else:
                    if local == saved:
                        state[key] = {'local': digest(local), 'repo': digest(saved)}
                        continue
                    incoming = expand(saved, home, root, platform)
                    result = merged(current, incoming, kind)
                    if current != result:
                        pending[target] = result
                        operations.append(('apply', target, result, e, normalize_entry(result, e, home, root)))
                state[key] = {'local': digest(normalize_entry(expand(saved, home, root, platform), e, home, root)), 'repo': digest(saved)}
            else:
                status = 'CONFLICT' if conflict else 'linked' if linked else 'in sync' if local == saved else 'different' if current and saved else 'local only' if current else 'repository only'
                print(f"{status:16} {e['target']}")
                if args.diff and local != saved:
                    print(''.join(difflib.unified_diff(saved.splitlines(True), local.splitlines(True), fromfile=e['source'], tofile=e['target'])), end='')
        except (ValueError, OSError, ET.ParseError, configparser.Error) as exc:
            # Never echo source text or a parser's potentially secret-containing excerpt.
            errors.append(f"Cannot process {e['target']}: {type(exc).__name__}")
    if errors:
        raise RuntimeError('\n'.join(errors))
    for action, path, text, e, normalized in operations:
        print(f"{'Would ' if not args.write else ''}{action}: {e['target']}")
        if not args.write:
            continue
        if action in ('link', 'apply') and (path.exists() or path.is_symlink()):
            relative = path.relative_to(home) if path.is_relative_to(home) else Path('external') / digest(str(path))[:16] / path.name
            backup = xdg(home, 'XDG_STATE_HOME', '.local/state') / namespace / 'backups' / time.strftime('%Y%m%d-%H%M%S') / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists():
                shutil.copy2(path, backup, follow_symlinks=True)
                backup.chmod(0o600)
        if action == 'link':
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() or path.is_symlink():
                path.unlink()
            path.symlink_to(text)
        else:
            write(path, text)
        source = root / e['source']
        state[e['target'] + ':' + e['source']] = {
            'local': digest(normalized), 'repo': digest(normalize_entry(source.read_text(), e, home, root))}
    if args.write:
        write(state_path, json.dumps(state, indent=2) + '\n')
    if args.command != 'status' and not args.write:
        print('Preview only. Repeat with --write to perform these operations.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = ['status', 'capture', 'apply', 'discover', 'audit']
    if profile(ROOT) != 'personal':
        commands.append('mcp')
    parser.add_argument('command', choices=commands)
    parser.add_argument('--write', action='store_true', help='Perform changes; otherwise preview only')
    parser.add_argument('--diff', action='store_true', help='Show portable configuration differences')
    parser.add_argument('--force', action='store_true', help='Resolve a conflict in the explicitly selected direction')
    parser.add_argument('--home', type=Path, default=Path.home(), help=argparse.SUPPRESS)
    parser.add_argument('--repo', type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument('--platform', choices=['macos', 'ubuntu'], help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.command == 'audit':
            if profile(args.repo) == 'personal':
                audit_repository(args.repo)
                return
            count = 0
            for e in entries(args.repo, args.platform or host_platform()):
                target = Path(expand(e['target'], args.home, args.repo))
                if not target.exists():
                    continue
                text = normalize(target.read_text(), e.get('format', 'text'), args.home, args.repo)
                if SECRET_VALUE.search(text):
                    raise RuntimeError('Credential scan failed: ' + e['target'])
                if e.get('format') == 'xml' and re.search(r'Bearer [A-Za-z0-9_-]{15,}', text):
                    raise RuntimeError('Embedded XML authorization needs manual review: ' + e['target'])
                count += 1
            print(f'{count} allowlisted files parsed and screened; no known credential values remain in the portable export.')
        elif args.command == 'discover':
            for e in entries(args.repo, args.platform or host_platform()):
                target = Path(expand(e['target'], args.home, args.repo, args.platform))
                if target.exists():
                    print(e['target'])
            print('Only reviewed manifest destinations are inspected. Add new files/keys to the appropriate repository manifest explicitly.')
        elif args.command == 'mcp':
            from configure_mcp import configure
            configure(args.home.resolve(), args.repo.resolve(), args.write)
        else:
            config_sync(args)
    except RuntimeError as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
