import asyncio
import fcntl
import os
import platform
import pwd
import shutil

from . import __version__, POLICY_VERSION
from .authz import CAPABILITIES
from .browser import BrowserManager, package_version
from .config import private_directory
from .db import Store
from .errors import require, HermodError
from .jobs import JobManager
from .rpc import RpcServer


class Daemon:
    def __init__(self, config):
        self.config = config.validate()
        require(config.test_mode or pwd.getpwuid(os.getuid()).pw_name == 'hermod', 'FORBIDDEN')
        private_directory(config.state_dir)
        self.lock = (config.state_dir / 'daemon.lock').open('a')
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lock.close()
            raise HermodError('SESSION_BUSY') from None
        self.store = Store(config)
        self.store.recover()
        self.browser = BrowserManager(config)
        self.jobs = JobManager(config, self.store, self.browser)
        self.server = RpcServer(config, self.dispatch)
        self.worker = None

    async def dispatch(self, method, params, uid):
        require(uid in self.config.allowed_uids, 'FORBIDDEN')
        if method in {'system.health', 'browser.status', 'session.login_required'}:
            require(not params)
            return {'protocol_version': 1, 'policy_version': POLICY_VERSION, 'version': __version__,
                    **self.browser.status(), 'active_job': self.jobs.active_job,
                    'queue_depth': self.jobs.queue.qsize(), 'python': platform.python_version(),
                    'architecture': platform.machine(), 'playwright': package_version(),
                    'profile_uid_isolated': not self.config.test_mode,
                    'capabilities': {k: sorted(v) for k, v in CAPABILITIES.items()
                                     if k != 'local_fixture' or self.config.test_mode},
                    'disk_free_bytes': shutil.disk_usage(self.config.state_dir).free}
        if method == 'browser.ensure':
            require(not params)
            require(not self.jobs.active_job, 'SESSION_BUSY')
            async with self.browser.lock:
                await self.browser.ensure()
            return self.browser.status()
        if method == 'jobs.create':
            return self.jobs.create(params, uid)
        if method in {'jobs.get', 'jobs.cancel'}:
            require(set(params) == {'job_id'})
            return (self.jobs.get if method == 'jobs.get' else self.jobs.cancel)(params['job_id'], uid)
        if method == 'jobs.resolve':
            require(set(params) == {'job_id', 'state', 'owner_confirmed'} and params['owner_confirmed'] is True)
            require(params['state'] in {'completed', 'failed'})
            job = self.store.get(params['job_id'], uid)
            require(job['state'] == 'uncertain', 'INVALID_TRANSITION')
            require(self.jobs.active_job != params['job_id'], 'SESSION_BUSY')
            self.store.transition(params['job_id'], params['state'])
            return self.jobs.get(params['job_id'], uid)
        raise HermodError('INVALID_ARGUMENT')

    async def start(self):
        await self.server.start()
        self.worker = asyncio.create_task(self.jobs.worker())

    async def close(self):
        await self.server.close()
        if self.worker:
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)
        await self.browser.close()
        self.jobs.payloads.clear()
        self.jobs.results.clear()
        self.store.close()
        self.lock.close()
