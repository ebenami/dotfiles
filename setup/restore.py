#!/usr/bin/env python3
"""Restore recorded tool installations; skip existing files and never overwrite local plugins."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def git_checkout(source, revision, target):
    if not (target / '.git').exists():
        subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout', source, str(target)], check=True)
        subprocess.run(['git', '-C', str(target), 'checkout', '--detach', revision], check=True)
    return target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skills', action='store_true', help='Restore missing third-party skills from recorded sources')
    parser.add_argument('--extensions', action='store_true', help='Install recorded VS Code/Cursor extensions when their CLI is available')
    args=parser.parse_args()
    home=Path.home()
    data=json.loads((ROOT/'config/tools.json').read_text())
    for plugin in data.get('vim_plugins',[]):
        target=home/'.vim/bundle'/plugin['name']
        if not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            git_checkout(plugin['source'],plugin['revision'],target)
    pathogen=home/'.vim/autoload/pathogen.vim'
    if not pathogen.exists() and 'pathogen' in data:
        info=data['pathogen']
        checkout=home/'.local/share/dotfiles-sources/vim-pathogen'
        git_checkout(info['source'],info['revision'],checkout)
        pathogen.parent.mkdir(parents=True,exist_ok=True)
        pathogen.symlink_to(checkout/'autoload/pathogen.vim')
    if args.skills:
        for source in data.get('skill_sources',[]):
            needed=[s for s in source['skills'] if not (home/'.agents/skills'/s).exists()]
            if not needed:
                continue
            identifier=hashlib.sha256(source['source'].encode()).hexdigest()[:16]
            checkout=home/'.local/share/dotfiles-sources'/identifier
            git_checkout(source['source'],source['revision'],checkout)
            candidates={}
            for file in checkout.rglob('SKILL.md'):
                if '.git' not in file.parts:
                    candidates.setdefault(file.parent.name, file.parent)
            for name in needed:
                if name not in candidates:
                    raise RuntimeError('Recorded skill not found in source: '+name)
                target=home/'.agents/skills'/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.symlink_to(candidates[name])
    for entry in data.get('skill_links',[]):
        target=home/entry['target']
        source=home/entry['source'] if entry['source'].startswith('.') else ROOT/entry['source']
        if source.exists() and not (target.exists() or target.is_symlink()):
            target.parent.mkdir(parents=True,exist_ok=True)
            target.symlink_to(source)
    failed_extensions=[]
    if args.extensions:
        for cli, extensions in data.get('extensions',{}).items():
            executable=shutil.which(cli)
            if not executable:
                print(f'{cli} CLI unavailable; extension list retained for later restoration.')
                continue
            installed=subprocess.check_output([executable,'--list-extensions'],text=True).lower().splitlines()
            for name in extensions:
                if name.lower() not in installed:
                    result=subprocess.run([executable,'--install-extension',name],check=False)
                    if result.returncode:
                        failed_extensions.append(f'{cli}: {name}')
    if failed_extensions:
        print('Warning: these extensions could not be installed; setup will continue:', file=sys.stderr)
        for extension in failed_extensions:
            print(f'  {extension}', file=sys.stderr)
        print('Review the CLI errors above, resolve compatibility or installation issues, then rerun restoration.', file=sys.stderr)
    print('Tool restoration finished; existing installations were preserved.')


if __name__=='__main__':
    main()
