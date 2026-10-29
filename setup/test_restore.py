"""Extension restoration checks without installing real extensions."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import restore


class ExtensionRestoreTests(unittest.TestCase):
    def test_failed_extension_does_not_block_remaining_extensions_or_editors(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'config').mkdir()
            (root / 'config/tools.json').write_text(json.dumps({'extensions': {
                'code': ['already.installed', 'incompatible.extension', 'working.extension'],
                'cursor': ['another.extension'],
                'code-insiders': ['deferred.extension'],
            }}))
            stderr = io.StringIO()
            with patch.object(restore, 'ROOT', root), \
                 patch.object(restore.Path, 'home', return_value=root), \
                 patch('sys.argv', ['restore.py', '--extensions']), \
                 patch.object(restore.shutil, 'which', side_effect=lambda cli: None if cli == 'code-insiders' else '/bin/' + cli), \
                 patch.object(restore.subprocess, 'check_output', return_value='Already.Installed\n'), \
                 patch.object(restore.subprocess, 'run', side_effect=[
                     subprocess.CompletedProcess([], 1),
                     subprocess.CompletedProcess([], 0),
                     subprocess.CompletedProcess([], 0),
                 ]) as run, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                restore.main()
            self.assertEqual([call.args[0] for call in run.call_args_list], [
                ['/bin/code', '--install-extension', 'incompatible.extension'],
                ['/bin/code', '--install-extension', 'working.extension'],
                ['/bin/cursor', '--install-extension', 'another.extension'],
            ])
            self.assertIn('code: incompatible.extension', stderr.getvalue())
            self.assertNotIn('working.extension', stderr.getvalue())
            self.assertNotIn('another.extension', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
