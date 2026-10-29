# /// script
# requires-python = ">=3.10"
# dependencies = ["tomlkit==0.13.3", "json5==0.12.1", "configobj==5.0.9"]
# ///
"""Behavior checks in isolated homes; no live preferences are changed."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import env

class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'home'
        self.root = Path(self.temp.name) / 'repo'
        self.home.mkdir()
        (self.root / 'config').mkdir(parents=True)
        self.entry = {'target': '${HOME}/settings.json', 'source': 'config/settings.json', 'mode': 'copy', 'format': 'json'}
        self.manifest([self.entry])

    def manifest(self, entries):
        (self.root / 'config/manifest.json').write_text(json.dumps(entries))

    def run_sync(self, action, **kw):
        args = argparse.Namespace(command=action, home=self.home, repo=self.root, platform='macos', write=True, force=False, diff=False)
        for key,value in kw.items():setattr(args,key,value)
        with contextlib.redirect_stdout(io.StringIO()):env.config_sync(args)

    def test_capture_excludes_credentials_and_home_paths(self):
        (self.home / 'settings.json').write_text(json.dumps({'fontSize':14,'api_key':'do-not-export','env':{'GITLAB_TOKEN':'do-not-export','HOME':str(self.home)},'projects':{'private':True}}))
        self.run_sync('capture')
        data=json.loads((self.root/'config/settings.json').read_text())
        self.assertEqual(data,{'fontSize':14,'env':{'HOME':'${HOME}'}})

    def test_apply_preserves_local_credentials_and_unmanaged_settings(self):
        (self.home/'settings.json').write_text('{"api_key":"keep-local","local":true,"fontSize":10}')
        (self.root/'config/settings.json').write_text('{"fontSize":14}')
        self.run_sync('apply')
        data=json.loads((self.home/'settings.json').read_text())
        self.assertEqual(data,{'api_key':'keep-local','local':True,'fontSize':14})
        self.assertTrue(list((self.home/'.local/state/snippets/backups').rglob('settings.json')))

    def test_preview_does_not_write_configuration_or_state(self):
        (self.root/'config/settings.json').write_text('{"fontSize":14}')
        self.run_sync('apply',write=False)
        self.assertFalse((self.home/'settings.json').exists())
        self.assertFalse((self.home/'.local').exists())

    def test_three_way_conflict_stops_all_changes(self):
        (self.home/'settings.json').write_text('{"fontSize":10}')
        self.run_sync('capture')
        (self.home/'settings.json').write_text('{"fontSize":12}')
        (self.root/'config/settings.json').write_text('{"fontSize":14}')
        with self.assertRaises(RuntimeError):self.run_sync('apply')
        self.assertEqual(json.loads((self.home/'settings.json').read_text())['fontSize'],12)
        self.run_sync('apply',force=True)
        self.assertEqual(json.loads((self.home/'settings.json').read_text())['fontSize'],14)

    def test_link_updates_repository_directly(self):
        self.entry.update(target='${HOME}/vimrc',source='config/vimrc',format='text',mode='link')
        self.manifest([self.entry])
        (self.root/'config/vimrc').write_text('set number\n')
        self.run_sync('apply')
        target=self.home/'vimrc'
        self.assertTrue(target.is_symlink())
        target.write_text('set nonumber\n')
        self.assertEqual((self.root/'config/vimrc').read_text(),'set nonumber\n')

    def test_aws_merge_keeps_static_credentials_local(self):
        raw='[profile dev]\nregion=eu-west-1\naws_access_key_id=local-only\naws_secret_access_key=local-only\ncredential_process=cloud-ssov3 credentials\n'
        exported=env.normalize(raw,'ini',self.home,self.root)
        self.assertNotIn('local-only',exported)
        self.assertIn('credential_process',exported)
        applied=env.merged(raw,exported,'ini')
        self.assertIn('aws_secret_access_key = local-only',applied)

    def test_toml_merge_keeps_local_secrets_and_project_trust(self):
        raw='model="old"\n[projects."/local"]\ntrust_level="trusted"\n[mcp_servers.gitlab.env]\nGITLAB_TOKEN="local-only"\n'
        exported=env.normalize(raw,'toml',self.home,self.root)
        self.assertNotIn('local-only',exported)
        self.assertNotIn('trust_level',exported)
        applied=env.merged(raw,'model="new"\n','toml')
        self.assertIn('local-only',applied)
        self.assertIn('trust_level',applied)

    def test_jsonc_is_accepted(self):
        text='// settings\n{"fontSize":14, /* note */ "api_key":"private",}'
        self.assertEqual(json.loads(env.normalize(text,'jsonc',self.home,self.root)),{'fontSize':14})

    def test_header_credentials_in_markdown_are_redacted(self):
        token='12345678-abcd-1234-abcd-123456789012'
        text='curl -H \"X-API-TOKEN: '+token+'\" https://example.com'
        exported=env.normalize(text,'text',self.home,self.root)
        self.assertNotIn(token,exported)
        self.assertIn('${LOCAL_SECRET}',exported)

    def test_known_embedded_secrets_rejected(self):
        with self.assertRaises(ValueError):env.normalize('https://user:password@example.com','text',self.home,self.root)

    def test_platform_entries_are_filtered(self):
        self.entry['platform']='macos';self.manifest([self.entry])
        (self.root/'config/settings.json').write_text('{}')
        self.run_sync('apply',platform='ubuntu')
        self.assertFalse((self.home/'settings.json').exists())

    def test_only_selected_claude_keys_exported(self):
        self.entry['keys']=['mcpServers'];self.manifest([self.entry])
        (self.home/'settings.json').write_text('{"oauthAccount":{"email":"private"},"mcpServers":{},"history":["private"]}')
        self.run_sync('capture')
        self.assertEqual(json.loads((self.root/'config/settings.json').read_text()),{'mcpServers':{}})

    def test_xml_password_option_removed(self):
        text='<application><component name="Thing"><option name="password" value="private"/><option name="font" value="Monaco"/></component></application>'
        self.assertNotIn('private',env.normalize(text,'xml',self.home,self.root))

    def test_xml_merge_keeps_local_credential_options(self):
        current='<application><component name="Thing"><option name="password" value="local-only"/><option name="font" value="old"/></component></application>'
        incoming='<application><component name="Thing"><option name="font" value="new"/></component></application>'
        result=env.merged(current,incoming,'xml')
        self.assertIn('local-only',result)
        self.assertIn('value="new"',result)

    def test_shared_ide_preferences_exclude_macos_paths(self):
        entry={'format':'json','select':'shared'}
        text='{"editor.fontSize":14,"terminal.integrated.env.osx":{"PATH":"/opt/homebrew/bin"},"tool.path":"/Applications/Tool.app/tool"}'
        result=json.loads(env.normalize_entry(text,entry,self.home,self.root))
        self.assertEqual(result,{'editor.fontSize':14})





class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.bin = self.base / 'bin'
        self.root = self.base / 'repo'
        self.home.mkdir()
        self.bin.mkdir()
        (self.home / '.local/bin').mkdir(parents=True)
        (self.root / 'setup').mkdir(parents=True)
        (self.root / 'config/shared/python').mkdir(parents=True)
        for name in ('tools.sh', 'ubuntu.sh'):
            shutil.copy(Path(__file__).parent / name, self.root / 'setup' / name)
        self.versions = self.root / 'config/shared/python/pyenv-version'
        self.versions.write_text('3.10.13\n3.12.12\n')
        self.log = self.base / 'calls'
        self.env = {'HOME': str(self.home), 'PATH': str(self.bin),
                    'CALL_LOG': str(self.log), 'SUDO_PROBE': '0',
                    'APT_UPDATE': '0', 'APT_INSTALL': '0'}
        for name in ('bash', 'sh', 'cp', 'dirname', 'mkdir', 'mktemp', 'rm', 'ln', 'mv', 'date', 'chmod'):
            (self.bin / name).symlink_to(shutil.which(name))
        self.script('uname', 'echo Linux')
        self.script('pyenv', 'echo "pyenv $*" >> "$CALL_LOG"; [[ "$1" == rehash ]]')
        self.script('uv', 'echo "uv $*" >> "$CALL_LOG"\n'
                    'for argument in "$@"; do [[ "$argument" != --no-bin ]] || exit 2; done\n'
                    'if [[ "$2" == install ]]; then echo "install-bin=$UV_PYTHON_INSTALL_BIN" >> "$CALL_LOG"; fi\n'
                    'if [[ "$2" == find ]]; then echo "$UV_PYTHON_EXE"; fi')
        for name in ('curl', 'git', 'unzip', 'zsh', 'direnv', 'fzf', 'starship', 'zoxide', 'fnm'):
            self.script(name, 'echo "' + name + ' $*" >> "$CALL_LOG"')
        self.script('sudo', 'echo "sudo $*" >> "$CALL_LOG"\n'
                    'shift\nif [[ "$1" == true ]]; then exit "$SUDO_PROBE"; fi\n"$@"')
        self.script('apt-get', 'echo "apt $*" >> "$CALL_LOG"\n'
                    'if [[ "$1" == update ]]; then exit "$APT_UPDATE"; fi\nexit "$APT_INSTALL"')

    def script(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/bash\n' + body + '\n')
        path.chmod(0o755)
        return path

    def python(self, path, version, broken=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f'#!{sys.executable}\n'
                        'import bz2, ctypes, lzma, os, sqlite3, ssl, sys, zlib\n'
                        + ('sys.exit(1)\n' if broken else '')
                        + f'sys.version_info = {tuple(map(int, version.split(".")))!r}\n'
                        'sys.executable = os.path.realpath(__file__)\n'
                        'code = sys.argv[3]\nsys.argv = ["-c", *sys.argv[4:]]\nexec(code)\n')
        path.chmod(0o755)
        return path

    def run_setup(self, name='tools.sh'):
        result = subprocess.run(['/bin/bash', str(self.root / 'setup' / name)],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def calls(self):
        return self.log.read_text() if self.log.exists() else ''

    def test_reuses_system_310_and_downloads_missing_312_once(self):
        system = self.python(self.bin / 'python3.10', '3.10.12')
        downloaded = self.python(self.base / 'uv-python/bin/python3', '3.12.12')
        self.env['UV_PYTHON_EXE'] = str(downloaded)
        self.run_setup()
        selection = self.home / '.pyenv/versions/3.10.13/bin'
        for name in ('python', 'python3', 'python3.10'):
            self.assertEqual((selection / name).resolve(), system)
        self.assertNotIn('uv python install 3.10.13', self.calls())
        self.assertEqual(self.calls().count('uv python install 3.12.12'), 1)
        self.assertIn('install-bin=0', self.calls())
        self.run_setup()
        self.assertEqual(self.calls().count('uv python install'), 1)
        self.assertNotIn('pyenv install', self.calls())

    def test_broken_selection_is_replaced_without_backup_and_system_python_reused(self):
        self.versions.write_text('3.10.13\n')
        broken = self.python(self.home / '.pyenv/versions/3.10.13/bin/python3', '3.10.13', broken=True)
        # A broken shim earlier in PATH must not hide the usable system binary.
        self.python(self.home / '.local/bin/python3.10', '3.10.13', broken=True)
        system = self.python(self.bin / 'python3.10', '3.10.16')
        self.run_setup()
        self.assertEqual(broken.resolve(), system)
        self.assertFalse((self.home / '.pyenv/backups').exists())
        self.assertNotIn('uv python install', self.calls())

    def test_reuses_another_pyenv_310_patch(self):
        self.versions.write_text('3.10.13\n')
        existing = self.python(self.home / '.pyenv/versions/3.10.18/bin/python3', '3.10.18')
        self.run_setup()
        self.assertEqual((self.home / '.pyenv/versions/3.10.13/bin/python').resolve(), existing)
        self.assertNotIn('uv python install', self.calls())

    def test_preserves_working_pinned_installation(self):
        self.versions.write_text('3.10.13\n')
        existing = self.python(self.home / '.pyenv/versions/3.10.13/bin/python3', '3.10.13')
        original = existing.read_text()
        self.run_setup()
        self.assertFalse(existing.is_symlink())
        self.assertEqual(existing.read_text(), original)
        self.assertFalse((self.home / '.pyenv/backups').exists())
        self.assertNotIn('uv python install', self.calls())

    def test_missing_310_uses_prebuilt_download(self):
        self.versions.write_text('3.10.13\n')
        downloaded = self.python(self.base / 'uv-python/bin/python3', '3.10.13')
        self.env['UV_PYTHON_EXE'] = str(downloaded)
        self.run_setup()
        self.assertEqual((self.home / '.pyenv/versions/3.10.13/bin/python').resolve(), downloaded)
        self.assertIn('uv python install 3.10.13', self.calls())
        self.assertIn('install-bin=0', self.calls())

    def test_failed_download_preserves_incomplete_installation(self):
        self.versions.write_text('3.10.13\n')
        broken = self.python(self.home / '.pyenv/versions/3.10.13/bin/python3', '3.10.13', broken=True)
        original = broken.read_text()
        self.script('uv', 'exit 1')
        result = subprocess.run(['/bin/bash', str(self.root / 'setup/tools.sh')],
                                env=self.env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(broken.read_text(), original)
        self.assertFalse((self.home / '.pyenv/backups').exists())
        self.assertNotIn('curl ', self.calls())

    def stale_uv(self):
        updated = self.base / 'updated-uv'
        shutil.copy(self.bin / 'uv', updated)
        installer = self.base / 'install-uv.sh'
        installer.write_text('[ "$UV_INSTALL_DIR" = "$HOME/.local/bin" ] && [ "$UV_NO_MODIFY_PATH" = 1 ] || exit 1\n'
                             'cp "$UPDATED_UV" "$UV_INSTALL_DIR/uv"\n')
        self.env.update(UPDATED_UV=str(updated), UV_INSTALLER=str(installer))
        self.script('uv', 'echo "stale uv $*" >> "$CALL_LOG"\n'
                    'echo "error: No download found for request: cpython-3.12.12-linux-x86_64-gnu" >&2\nexit 1')
        self.script('curl', 'echo "curl $*" >> "$CALL_LOG"\ncp "$UV_INSTALLER" "$4"')

    def test_stale_uv_catalog_is_refreshed_and_python_install_retried(self):
        self.versions.write_text('3.12.12\n')
        downloaded = self.python(self.base / 'uv-python/bin/python3', '3.12.12')
        self.env['UV_PYTHON_EXE'] = str(downloaded)
        self.stale_uv()
        result = self.run_setup()
        self.assertIn('Refreshing user-local uv', result.stderr)
        self.assertEqual(self.calls().count('curl '), 1)
        self.assertEqual(self.calls().count('uv python install 3.12.12'), 2)
        self.assertIn('install-bin=0', self.calls())
        self.assertEqual((self.home / '.pyenv/versions/3.12.12/bin/python').resolve(), downloaded)

    def test_catalog_refresh_is_not_repeated_if_version_remains_unavailable(self):
        self.versions.write_text('3.12.12\n')
        self.stale_uv()
        shutil.copy(self.bin / 'uv', self.base / 'updated-uv')
        result = subprocess.run(['/bin/bash', str(self.root / 'setup/tools.sh')],
                                env=self.env, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls().count('curl '), 1)
        self.assertEqual(self.calls().count('uv python install 3.12.12'), 2)
        self.assertFalse((self.home / '.pyenv/versions/3.12.12').exists())

    def test_denied_sudo_and_apt_failures_allow_user_setup(self):
        # EUID is supplied by Bash. Use an ordinary shell variable in this fixture
        # so these non-root paths can also be exercised by root in Linux CI.
        ubuntu = self.root / 'setup/ubuntu.sh'
        ubuntu.write_text(ubuntu.read_text().replace('"$EUID"', '"1000"'))
        for probe, update, install in [('1', '0', '0'), ('0', '1', '0'), ('0', '0', '1')]:
            with self.subTest(probe=probe, update=update, install=install):
                self.log.unlink(missing_ok=True)
                self.env.update(SUDO_PROBE=probe, APT_UPDATE=update, APT_INSTALL=install)
                self.run_setup('ubuntu.sh')
                self.assertIn('fnm default 24.18.0', self.calls())
                if probe == '1':
                    self.assertNotIn('apt update', self.calls())
                if update == '1':
                    self.assertNotIn('apt install', self.calls())
        (self.bin / 'sudo').unlink()
        self.log.unlink()
        self.run_setup('ubuntu.sh')
        self.assertIn('fnm default 24.18.0', self.calls())
        self.assertNotIn('apt update', self.calls())


if __name__ == "__main__": unittest.main()
