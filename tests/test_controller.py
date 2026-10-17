import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hermod import POLICY_VERSION
from hermod.authz import authorize, allowed_url
from hermod.config import Config, chatgpt_url
from hermod.daemon import Daemon
from hermod.db import Store
from hermod.errors import HermodError
from hermod.fixture_site import FixtureSite
from hermod.rpc import call, loads


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hermod-test-')
        self.root = Path(self.temp.name)
        self.site = FixtureSite().__enter__()
        self.config = Config(self.root / 'state', self.root / 'run/h.sock', (os.getuid(),),
                             test_mode=True, fixture_origin=self.site.origin, job_timeout=5,
                             navigation_timeout=2, min_disk_bytes=0)
        self.daemon = Daemon(self.config)
        await self.daemon.start()
        self.sequence = 0

    async def asyncTearDown(self):
        await self.daemon.close()
        self.site.__exit__(None, None, None)
        self.temp.cleanup()

    def payload(self, ref='fixture:demo', action='conversation.send'):
        self.sequence += 1
        value = dict(idempotency_key=f'test:{self.sequence}', provider='local_fixture', action=action,
                     conversation_ref=ref, requested_by='fixture-owner', purpose='fixture_test',
                     policy_version=POLICY_VERSION)
        if action == 'conversation.send':
            value['text'] = 'synthetic private body, not a log record'
        return value

    async def wait(self, job):
        async with asyncio.timeout(15):
            while True:
                result = await call(self.config.socket_path, 'jobs.get', {'job_id': job['job_id']})
                if result['state'] not in {'queued', 'preflight', 'running'}:
                    return result
                await asyncio.sleep(.03)

    async def test_health_no_browser_required(self):
        result = await call(self.config.socket_path, 'system.health')
        self.assertEqual(result['browser'], 'stopped')
        self.assertEqual(result['auth'], 'unknown')
        self.assertEqual(result['capabilities']['chatgpt'], ['OPEN'])
        self.assertEqual(self.config.socket_path.stat().st_mode & 0o777, 0o600)

    async def test_real_browser_send_stream_collect_duplicate_exactly_once(self):
        payload = self.payload()
        first = await call(self.config.socket_path, 'jobs.create', payload)
        second = await call(self.config.socket_path, 'jobs.create', payload)
        self.assertEqual(first['job_id'], second['job_id'])
        self.assertTrue(second['duplicate'])
        result = await self.wait(first)
        self.assertEqual(result['state'], 'completed', result)
        self.assertEqual(result['result']['text'], 'Fixture reply: ' + payload['text'])
        self.assertEqual(len(self.site.receipts), 1)
        again = await call(self.config.socket_path, 'jobs.create', payload)
        self.assertTrue(again['duplicate'])
        self.assertEqual(len(self.site.receipts), 1)
        # Ledger has hashes/status, not request or response bodies.
        rows = repr([tuple(r) for r in self.daemon.store.conn.execute('SELECT * FROM jobs')])
        self.assertNotIn(payload['text'], rows)
        self.assertNotIn('Fixture reply:', rows)
        self.assertTrue(result['action_attempted_at'])
        self.assertTrue(result['action_confirmed_at'])

    async def test_policy_rejected_before_browser_launch(self):
        for action in ('conversation.send', 'conversation.collect', 'conversation.search'):
            payload = self.payload(action=action)
            payload.update(provider='chatgpt', conversation_ref='cgpt:unknown')
            with self.assertRaisesRegex(HermodError, 'POLICY_REVIEW_REQUIRED'):
                await call(self.config.socket_path, 'jobs.create', payload)
        self.assertIsNone(self.daemon.browser.context)
        self.assertEqual(self.daemon.store.conn.execute('SELECT count(*) FROM jobs').fetchone()[0], 0)

    async def test_unknown_ref_and_arbitrary_inputs_rejected(self):
        for field, value in (('url', 'http://localhost'), ('selector', '#submit'), ('script', 'alert(1)')):
            payload = self.payload()
            payload[field] = value
            with self.assertRaises(HermodError):
                await call(self.config.socket_path, 'jobs.create', payload)
        payload = self.payload('fixture:unregistered')
        with self.assertRaisesRegex(HermodError, 'PAGE_MISMATCH'):
            await call(self.config.socket_path, 'jobs.create', payload)

    async def test_payload_conflict(self):
        self.daemon.worker.cancel()
        await asyncio.gather(self.daemon.worker, return_exceptions=True)
        payload = self.payload(action='conversation.open')
        self.daemon.jobs.create(payload, os.getuid())
        payload['conversation_ref'] = 'fixture:second'
        with self.assertRaisesRegex(HermodError, 'DUPLICATE_REQUEST'):
            self.daemon.jobs.create(payload, os.getuid())

    async def test_fixture_auth_and_human_required(self):
        for ref, state in [('fixture:auth', 'auth_required'), ('fixture:human', 'human_action_required')]:
            job = await call(self.config.socket_path, 'jobs.create', self.payload(ref))
            result = await self.wait(job)
            self.assertEqual(result['state'], state, result)
            self.assertIsNone(result['action_attempted_at'])
        self.assertFalse(self.site.receipts)

    async def test_fixture_page_mismatch(self):
        job = await call(self.config.socket_path, 'jobs.create', self.payload('fixture:mismatch'))
        result = await self.wait(job)
        self.assertEqual(result['error_code'], 'PAGE_MISMATCH')
        self.assertFalse(self.site.receipts)

    async def test_changed_ui_no_guess_click(self):
        job = await call(self.config.socket_path, 'jobs.create', self.payload('fixture:changed'))
        result = await self.wait(job)
        self.assertEqual(result['error_code'], 'UI_CHANGED', result)
        self.assertFalse(self.site.receipts)

    async def test_timeout_after_submit_is_uncertain_no_replay(self):
        async with self.daemon.browser.lock:
            await self.daemon.browser.ensure('local_fixture')
        self.daemon.jobs.config = replace(self.config, job_timeout=2)
        payload = self.payload('fixture:slow')
        job = await call(self.config.socket_path, 'jobs.create', payload)
        result = await self.wait(job)
        self.assertEqual(result['state'], 'uncertain', result)
        self.assertTrue(result['may_have_side_effects'])
        self.assertEqual(len(self.site.receipts), 1)
        self.assertTrue((await call(self.config.socket_path, 'jobs.create', payload))['duplicate'])
        self.assertEqual(len(self.site.receipts), 1)
        with self.assertRaises(HermodError):
            await call(self.config.socket_path, 'jobs.resolve', {'job_id': job['job_id'], 'state': 'completed', 'owner_confirmed': False})
        async with asyncio.timeout(5):
            while self.daemon.jobs.active_job:
                await asyncio.sleep(.03)
        await call(self.config.socket_path, 'jobs.resolve', {'job_id': job['job_id'], 'state': 'completed', 'owner_confirmed': True})

    async def test_cancel_after_submit_does_not_claim_retraction(self):
        job = await call(self.config.socket_path, 'jobs.create', self.payload('fixture:slow'))
        async with asyncio.timeout(10):
            while not self.site.receipts:
                await asyncio.sleep(.03)
        result = await call(self.config.socket_path, 'jobs.cancel', {'job_id': job['job_id']})
        self.assertEqual(result['state'], 'cancelled')
        self.assertTrue(result['may_have_side_effects'])

    async def test_fixture_search_actual_browser(self):
        payload = self.payload(action='conversation.search')
        payload['text'] = 'second'
        result = await self.wait(await call(self.config.socket_path, 'jobs.create', payload))
        self.assertEqual(result['result']['matches'], ['fixture:second'])

    async def test_queue_bound_and_cancel_queued(self):
        self.daemon.worker.cancel()
        await asyncio.gather(self.daemon.worker, return_exceptions=True)
        for _ in range(10):
            job = self.daemon.jobs.create(self.payload(action='conversation.open'), os.getuid())
        with self.assertRaisesRegex(HermodError, 'RESOURCE_EXHAUSTED'):
            self.daemon.jobs.create(self.payload(action='conversation.open'), os.getuid())
        self.assertEqual(self.daemon.jobs.cancel(job['job_id'], os.getuid())['state'], 'cancelled')

    async def test_recovery_never_replays_queued_or_running(self):
        self.daemon.worker.cancel()
        await asyncio.gather(self.daemon.worker, return_exceptions=True)
        queued = self.daemon.jobs.create(self.payload(), os.getuid())
        running = self.daemon.jobs.create(self.payload(), os.getuid())
        self.daemon.store.transition(running['job_id'], 'preflight')
        self.daemon.store.transition(running['job_id'], 'running')
        self.daemon.store.recover()
        self.assertEqual(self.daemon.jobs.get(queued['job_id'], os.getuid())['state'], 'failed')
        self.assertEqual(self.daemon.jobs.get(running['job_id'], os.getuid())['state'], 'uncertain')

    async def test_peer_uid_denied(self):
        self.daemon.server.config = replace(self.config, allowed_uids=(os.getuid() + 999,))
        with self.assertRaisesRegex(HermodError, 'FORBIDDEN'):
            await call(self.config.socket_path, 'system.health')

    async def test_raw_rpc_validation(self):
        for data, code in [
            (b'{"version":2,"request_id":"x","method":"system.health","params":{}}\n', 'UNSUPPORTED_VERSION'),
            (b'{"version":true,"request_id":"x","method":"system.health","params":{}}\n', 'UNSUPPORTED_VERSION'),
            (b'{"version":1,"version":1}\n', 'INVALID_ARGUMENT'),
            (b'not json\n', 'INVALID_ARGUMENT'),
            (b'x' * 65537 + b'\n', 'INVALID_ARGUMENT')]:
            reader, writer = await asyncio.open_unix_connection(self.config.socket_path)
            writer.write(data)
            await writer.drain()
            response = json.loads(await reader.readline())
            self.assertEqual(response['error']['code'], code)
            writer.close()
            await writer.wait_closed()

    async def test_same_profile_daemon_lock(self):
        with self.assertRaisesRegex(HermodError, 'SESSION_BUSY'):
            Daemon(self.config)

    async def test_result_expiry_not_reinterpreted_as_failure(self):
        self.daemon.worker.cancel()
        await asyncio.gather(self.daemon.worker, return_exceptions=True)
        job = self.daemon.jobs.create(self.payload(action='conversation.open'), os.getuid())
        self.daemon.jobs.results[job['job_id']] = (time.monotonic() - 1, {'text': 'old'})
        self.assertFalse(self.daemon.jobs.get(job['job_id'], os.getuid())['result_available'])

    async def test_closed_world_origin_policy(self):
        for url in ['http://127.0.0.1:1/threads/demo', 'http://localhost:1/',
                    'https://chatgpt.com.evil.test/c/a', 'file:///etc/passwd', 'http://169.254.169.254/']:
            self.assertFalse(allowed_url(self.config, url, 'local_fixture'))
        for url in ['https://chatgpt.com.evil.test/c/a', 'https://chatgpt.com/c/a?token=x',
                    'https://user@chatgpt.com/c/a', 'https://chatgpt.com:443/c/a']:
            with self.assertRaises(HermodError):
                chatgpt_url(url)

    async def test_no_implicit_production_under_owner_uid(self):
        with self.assertRaises(HermodError):
            replace(self.config, test_mode=False).validate()

    async def test_symlink_state_rejected(self):
        link = self.root / 'linked'
        link.symlink_to(self.config.state_dir, target_is_directory=True)
        with self.assertRaises(HermodError):
            Store(replace(self.config, state_dir=link))

    async def test_secret_fields_and_nan_rejected(self):
        with self.assertRaises(HermodError):
            loads('{"password":NaN}')
        payload = self.payload()
        payload['cookies'] = 'not allowed'
        with self.assertRaises(HermodError):
            self.daemon.jobs.create(payload, os.getuid())

    async def test_registered_reference_expected_url_hash_mismatch(self):
        self.daemon.jobs.config = replace(self.config, conversations={'cgpt:demo':
            {'provider': 'chatgpt', 'url': 'https://chatgpt.com/c/owner-supplied', 'verified': True}})
        payload = self.payload(action='conversation.open')
        payload.update(provider='chatgpt', conversation_ref='cgpt:demo', expected_url_sha256='0' * 64)
        with self.assertRaisesRegex(HermodError, 'PAGE_MISMATCH'):
            self.daemon.jobs.create(payload, os.getuid())
        self.assertIsNone(self.daemon.browser.context)

    async def test_logs_do_not_include_request_or_response_text(self):
        payload = self.payload()
        with self.assertLogs('hermod', level='INFO') as logs:
            job = self.daemon.jobs.create(payload, os.getuid())
            result = await self.wait(job)
        self.assertEqual(result['state'], 'completed')
        self.assertNotIn(payload['text'], '\n'.join(logs.output))
        self.assertNotIn('Fixture reply:', '\n'.join(logs.output))
        self.assertEqual((self.config.state_dir / 'browser-profile').stat().st_mode & 0o777, 0o700)
