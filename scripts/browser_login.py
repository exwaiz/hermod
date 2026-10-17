"""Supervised local GUI only; no remote debugging, password input or cookie export."""
import argparse
import asyncio
import fcntl
import os
import pwd

from hermod.config import Config, private_directory
from hermod.errors import require


async def login(config):
    require(pwd.getpwuid(os.getuid()).pw_name == 'hermod' and not config.test_mode, 'FORBIDDEN')
    require(bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')), 'HUMAN_ACTION_REQUIRED')
    from playwright.async_api import async_playwright
    with (private_directory(config.state_dir) / 'daemon.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        profile = private_directory(config.state_dir / 'browser-profile')
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(str(profile), headless=False,
                chromium_sandbox=True, executable_path=config.browser_executable, accept_downloads=False)
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto('https://chatgpt.com/', wait_until='domcontentloaded')
                print('Complete sign-in yourself in the local GUI. No account state is exported. Press Enter to close.')
                await asyncio.to_thread(input)
            finally:
                await context.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    args = parser.parse_args()
    asyncio.run(login(Config.load(args.config)))
