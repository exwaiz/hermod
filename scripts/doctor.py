"""Read-only environment report; browser smoke is an explicit separate command."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import pwd
import grp
import shutil

from hermod.browser import package_version, process_rss


def account(kind, name):
    try:
        (pwd.getpwnam if kind == 'user' else grp.getgrnam)(name)
        return 'checked_exists'
    except KeyError:
        return 'not_present'


def main():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = {'checked': True, 'executable': p.chromium.executable_path,
                       'exists': Path(p.chromium.executable_path).is_file()}
    except Exception:
        browser = {'checked': False, 'error_code': 'BROWSER_UNAVAILABLE'}
    print(json.dumps({'os': platform.system(), 'architecture': platform.machine(),
        'python': platform.python_version(), 'playwright': package_version(),
        'browser': browser, 'controller_rss_bytes': process_rss(),
        'disk_free_bytes': shutil.disk_usage(Path.cwd()).free,
        'dedicated_user': account('user', 'hermod'), 'client_group': account('group', 'hermod-clients'),
        'browser_launch': 'not_checked_run_smoke_fixture', 'chatgpt_login': 'not_checked',
        'memory_cgroup': 'checked_present' if 'memory' in Path('/sys/fs/cgroup/cgroup.controllers').read_text().split() else 'not_available'}, indent=2))


if __name__ == '__main__':
    main()
