"""Real Chromium + real UDS, synthetic data only, temporary profile cleaned up."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import time

from hermod import POLICY_VERSION
from hermod.browser import process_rss
from hermod.config import Config
from hermod.daemon import Daemon
from hermod.fixture_site import FixtureSite
from hermod.rpc import call


async def smoke():
    with tempfile.TemporaryDirectory(prefix='hermod-smoke-') as directory, FixtureSite() as site:
        root = Path(directory)
        cfg = Config(root / 'state', root / 'run/h.sock', (os.getuid(),), test_mode=True,
                     fixture_origin=site.origin, min_disk_bytes=0)
        daemon = Daemon(cfg)
        started = time.monotonic()
        try:
            await daemon.start()
            payload = dict(idempotency_key='smoke:1', provider='local_fixture', action='conversation.send',
                           conversation_ref='fixture:demo', requested_by='smoke', purpose='fixture_test',
                           policy_version=POLICY_VERSION, text='Synthetic Hermod fixture question')
            job = await call(cfg.socket_path, 'jobs.create', payload)
            duplicate = await call(cfg.socket_path, 'jobs.create', payload)
            async with asyncio.timeout(30):
                while True:
                    result = await call(cfg.socket_path, 'jobs.get', {'job_id': job['job_id']})
                    if result['state'] not in {'queued', 'preflight', 'running'}:
                        break
                    await asyncio.sleep(.03)
            assert result['state'] == 'completed', result['error_code']
            assert result['result']['text'] == 'Fixture reply: ' + payload['text']
            assert len(site.receipts) == 1 and duplicate['duplicate']
            # Explicit test-only screenshot; no private login/profile is involved.
            screenshot = await daemon.browser.page.screenshot()
            print(json.dumps({'state': result['state'], 'submissions': len(site.receipts),
                'duplicate_suppressed': duplicate['duplicate'], 'duration_ms': round((time.monotonic()-started)*1000),
                'controller_browser_rss_bytes': process_rss(), 'screenshot_bytes': len(screenshot),
                'browser_version': daemon.browser.context.browser.version, 'sandbox': True,
                'profile_uid_isolated': False, 'fixture_only': True}))
        finally:
            await daemon.close()


if __name__ == '__main__':
    asyncio.run(smoke())
