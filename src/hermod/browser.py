import asyncio
import fcntl
import importlib.metadata
import os
from pathlib import Path
import shutil
import time

from .authz import allowed_url
from .config import private_directory
from .errors import HermodError, require


def process_rss():
    """Observed RSS of this controller and descendants; not a kernel memory cap."""
    processes = {}
    for directory in Path('/proc').glob('[0-9]*'):
        try:
            fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            processes[int(directory.name)] = (int(fields[1]), int(fields[21]) * os.sysconf('SC_PAGE_SIZE'))
        except (OSError, ValueError, IndexError):
            continue
    found = {os.getpid()}
    for _ in range(20):
        children = {pid for pid, (parent, _) in processes.items() if parent in found}
        if children <= found:
            break
        found |= children
    return sum(processes.get(pid, (0, 0))[1] for pid in found)


class BrowserManager:
    def __init__(self, config):
        self.config = config
        self.playwright = self.context = self.page = self.profile_lock = None
        self.provider = None
        self.auth = 'unknown'
        self.state = 'stopped'
        self.last_used = time.monotonic()
        self.lock = asyncio.Lock()
        self.blocked_requests = 0

    def status(self):
        return {'browser': self.state, 'auth': self.auth, 'blocked_requests': self.blocked_requests,
                'profile_version': 1, 'ui_adapter_version': 'fixture-v1/chatgpt-open-v1',
                'observed_rss_bytes': process_rss(), 'memory_limit_is_soft': True}

    async def ensure(self, provider='chatgpt'):
        require(shutil.disk_usage(self.config.state_dir).free >= self.config.min_disk_bytes, 'RESOURCE_EXHAUSTED')
        require(process_rss() < self.config.soft_rss_bytes, 'RESOURCE_EXHAUSTED')
        if self.context and self.page and not self.page.is_closed():
            if self.provider != provider:
                await self.close()
            else:
                return
        from playwright.async_api import async_playwright
        profile = private_directory(self.config.state_dir / 'browser-profile')
        self.profile_lock = (profile / 'controller.lock').open('a')
        try:
            fcntl.flock(self.profile_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            async def launch():
                self.playwright = await async_playwright().start()
                self.context = await self.playwright.chromium.launch_persistent_context(
                    str(profile), headless=True, chromium_sandbox=True,
                    executable_path=self.config.browser_executable, accept_downloads=False,
                    service_workers='block', permissions=[],
                    args=['--force-webrtc-ip-handling-policy=disable_non_proxied_udp'])
            startup = asyncio.create_task(launch())
            try:
                await asyncio.shield(startup)
            except asyncio.CancelledError:
                # Reap Playwright's subprocess before propagating cancellation.
                # Cancelling midway through driver creation can strand its pipe.
                try:
                    await asyncio.wait_for(startup, 30)
                finally:
                    await self.close()
                raise
            self.provider = provider
            async def route(request):
                if allowed_url(self.config, request.request.url, self.provider):
                    await request.continue_()
                else:
                    self.blocked_requests += 1
                    await request.abort('blockedbyclient')
            await self.context.route('**/*', route)
            await self.context.route_web_socket('**/*', lambda socket: socket.close())
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            for old in self.context.pages:
                if old != self.page:
                    await old.close()
            self.context.on('page', lambda page: asyncio.create_task(page.close()))
            self.page.on('download', lambda download: asyncio.create_task(download.cancel()))
            self.page.set_default_timeout(self.config.navigation_timeout * 1000)
            self.page.set_default_navigation_timeout(self.config.navigation_timeout * 1000)
            self.state = 'ready'
            self.last_used = time.monotonic()
        except BaseException:
            await self.close()
            raise

    async def navigate(self, url):
        require(allowed_url(self.config, url, self.provider), 'FORBIDDEN')
        await self.page.goto(url, wait_until='domcontentloaded')
        require(self.page.url == url, 'PAGE_MISMATCH')
        self.last_used = time.monotonic()

    async def idle(self):
        if self.context and (time.monotonic() - self.last_used > self.config.idle_timeout or
                             process_rss() > self.config.soft_rss_bytes):
            async with self.lock:
                await self.close()

    async def close(self):
        try:
            if self.context:
                await self.context.close()
        finally:
            self.context = self.page = None
            if self.playwright:
                await self.playwright.stop()
                self.playwright = None
            if self.profile_lock:
                self.profile_lock.close()
                self.profile_lock = None
            self.auth, self.state = 'unknown', 'stopped'


def package_version():
    try:
        return importlib.metadata.version('playwright')
    except importlib.metadata.PackageNotFoundError:
        return 'not_installed'
