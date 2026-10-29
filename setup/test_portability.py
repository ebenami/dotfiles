# /// script
# requires-python = ">=3.10"
# dependencies = ["tomlkit==0.13.3", "json5==0.12.1", "configobj==5.0.9"]
# ///
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import env


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.home = self.base / 'home'
        self.home.mkdir()
        self.repo = self.base / 'personal'
        (self.repo / 'config').mkdir(parents=True)
        (self.repo / 'config/profile.json').write_text('{"profile":"personal"}')

    def sync(self, command, repo=None, platform='ubuntu', write=True):
        args = argparse.Namespace(command=command, home=self.home, repo=repo or self.repo,
                                  platform=platform, write=write, force=False, diff=False)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            env.config_sync(args)
        return output.getvalue()

    def entry(self, data, kind, owned):
        e = {'source':'config/preferences', 'target':'${CONFIG_HOME}/preferences',
             'format':kind, 'mode':'copy', 'owned':owned}
        (self.repo / e['source']).write_text(env.structured_dump(data, kind))
        (self.repo / 'config/manifest.json').write_text(json.dumps([e]))
        return e

    def test_capture_and_apply_manage_only_owned_nested_keys(self):
        for kind in ('json', 'toml', 'ini', 'configobj'):
            with self.subTest(kind=kind):
                (self.home/'.local/state/personal/config-state.json').unlink(missing_ok=True)
                original = {'general':{'font':'12'}, 'work':{'endpoint':'https://company.invalid'}}
                self.entry({'general':{'font':'10'}}, kind, {'general':{'font':True}})
                target = self.home / '.config/preferences'
                target.parent.mkdir(exist_ok=True)
                target.write_text(env.structured_dump(original, kind))
                self.sync('capture')
                self.assertEqual(env.structured_load((self.repo/'config/preferences').read_text(), kind),
                                 {'general':{'font':'12'}})
                (self.repo/'config/preferences').write_text(env.structured_dump({'general':{'font':'14'}}, kind))
                self.sync('apply')
                result = env.structured_load(target.read_text(), kind)
                self.assertEqual(result['general']['font'], '14')
                self.assertEqual(result['work'], original['work'])

    def test_personal_capture_rejects_work_endpoint_before_writing(self):
        self.entry({'general':{'endpoint':'https://example.org'}}, 'json', {'general':{'endpoint':True}})
        target = self.home / '.config/preferences'
        target.parent.mkdir()
        target.write_text('{"general":{"endpoint":"https://gitlab.mobileye.com"}}')
        before = (self.repo/'config/preferences').read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'Work-specific'):
            self.sync('capture')
        self.assertEqual((self.repo/'config/preferences').read_bytes(), before)

    def test_terminator_preserves_shortcuts_layouts_and_other_profiles(self):
        self.repo = env.ROOT
        e = next(e for e in env.entries(self.repo,'ubuntu') if e['format']=='configobj')
        current = {'keybindings':{'split_vert':'<Super>d', 'copy':'<Control>Insert'},
                   'layouts':{'default':{'window0':{'type':'Window','parent':''}}},
                   'profiles':{'custom':{'font':'Custom 9','custom_command':'echo local'},
                               'default':{'custom_command':'echo keep','font':'Old 9'}}}
        target = self.home / '.config/terminator/config'
        target.parent.mkdir(parents=True)
        target.write_text(env.structured_dump(current,'configobj'))
        self.sync('apply')
        result = env.structured_load(target.read_text(),'configobj')
        for section in ('keybindings','layouts'):
            self.assertEqual(result[section],current[section])
        self.assertEqual(result['profiles']['custom'],current['profiles']['custom'])
        self.assertEqual(result['profiles']['default']['custom_command'],'echo keep')
        self.assertEqual(result['profiles']['default']['font'],'Monospace 12')
        captured = env.structured_load(env.normalize_entry(target.read_text(),e,self.home,self.repo),'configobj')
        self.assertNotIn('keybindings',captured)
        self.assertNotIn('layouts',captured)
        self.assertNotIn('custom',captured['profiles'])
        self.assertNotIn('custom_command',captured['profiles']['default'])
        self.assertTrue(list((self.home/'.local/state/personal/backups').rglob('config')))

    def test_personal_snapshots_apply_cleanly_on_both_platforms(self):
        for platform in ('macos','ubuntu'):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as temp:
                self.home=Path(temp).resolve()
                self.repo=env.ROOT
                self.sync('apply',platform=platform)
                self.assertTrue((self.home/'.zshrc').is_symlink())
                self.assertTrue((self.home/'.vimrc').is_symlink())
                self.assertEqual((self.home/'.config/terminator/config').exists(),platform=='ubuntu')
                status=self.sync('status',platform=platform)
                self.assertNotIn('different',status)
                self.assertNotIn('CONFLICT',status)
                for path in self.home.rglob('*'):
                    if path.is_file() and path.suffix != '.json':
                        self.assertNotIn('gitlab.mobileye.com',path.read_text())

    def test_personal_and_work_state_are_independent(self):
        self.entry({'general':{'font':'10'}},'json',{'general':{'font':True}})
        self.sync('apply')
        work=self.base/'work';(work/'config').mkdir(parents=True)
        (work/'config/profile.json').write_text('{"profile":"snippets"}')
        (work/'config/manifest.json').write_text('[]')
        self.sync('apply',repo=work)
        self.assertTrue((self.home/'.local/state/personal/config-state.json').exists())
        self.assertTrue((self.home/'.local/state/snippets/config-state.json').exists())

    def test_shared_and_platform_settings_compose_in_one_apply(self):
        base=self.entry({'general':{'font':'12'}},'json',{'general':{'font':True}})
        platform=dict(base,source='config/platform',owned={'platform':{'path':True}})
        (self.repo/'config/platform').write_text('{"platform":{"path":"/local/tool"}}')
        (self.repo/'config/manifest.json').write_text(json.dumps([base,platform]))
        self.sync('apply')
        data=json.loads((self.home/'.config/preferences').read_text())
        self.assertEqual(data,{'general':{'font':'12'},'platform':{'path':'/local/tool'}})
        self.assertNotIn('different',self.sync('status'))

    def test_xdg_paths_are_used_for_real_home_only(self):
        with patch.dict(os.environ,{'XDG_CONFIG_HOME':str(self.base/'settings')}):
            self.assertEqual(env.expand('${CONFIG_HOME}/terminator/config',Path.home(),self.repo,'ubuntu'),
                             str(self.base/'settings/terminator/config'))
            self.assertEqual(env.expand('${CONFIG_HOME}/terminator/config',self.home,self.repo,'ubuntu'),
                             str(self.home/'.config/terminator/config'))

    def test_export_audit_checks_files_outside_manifest(self):
        (self.repo/'config/manifest.json').write_text('[]')
        (self.repo/'notes.txt').write_text('https://gitlab.mobileye.com')
        with self.assertRaisesRegex(RuntimeError,'notes.txt'):
            env.audit_repository(self.repo)


if __name__ == '__main__':
    unittest.main()
