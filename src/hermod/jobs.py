import asyncio
import hashlib
import logging
import os
import re
import time

from . import POLICY_VERSION
from .authz import authorize
from .db import TERMINAL
from .errors import HermodError, require
from .providers.fixture import FixtureProvider
from .providers.chatgpt import ChatGPTProvider

LOGGER = logging.getLogger('hermod')


class JobManager:
    def __init__(self, config, store, browser):
        self.config, self.store, self.browser = config, store, browser
        self.queue = asyncio.Queue(maxsize=config.queue_limit)
        self.payloads, self.results = {}, {}
        self.active_job = self.active_task = None

    def create(self, params, uid):
        required = {'idempotency_key', 'provider', 'action', 'conversation_ref', 'requested_by', 'purpose', 'policy_version'}
        require(isinstance(params, dict) and required <= params.keys() <= required | {'text', 'mode', 'expected_url_sha256'})
        require(all(isinstance(v, str) for v in params.values()))
        require(re.fullmatch(r'[A-Za-z0-9:_-]{1,128}', params['idempotency_key']) is not None)
        require(re.fullmatch(r'[A-Za-z0-9:_-]{1,64}', params['requested_by']) is not None)
        require(not any(re.search(r'\d{6,}:[A-Za-z0-9_-]{20,}', params[k]) for k in
                        ('idempotency_key', 'requested_by')), 'FORBIDDEN')
        require(params['purpose'] in {'manual', 'fixture_test', 'handoff'})
        require(params['policy_version'] == POLICY_VERSION, 'UNSUPPORTED_VERSION')
        require(params.get('mode', 'manual_handoff') in {'manual_handoff', 'fixture'})
        require(len(params.get('text', '')) <= 12000)
        url = authorize(self.config, params['provider'], params['action'], params['conversation_ref'])
        if 'expected_url_sha256' in params:
            require(re.fullmatch(r'[0-9a-f]{64}', params['expected_url_sha256']) is not None)
            require(hashlib.sha256(url.encode()).hexdigest() == params['expected_url_sha256'], 'PAGE_MISMATCH')
        if params['action'] == 'conversation.send':
            require(bool(params.get('text', '').strip()))
        elif params['action'] != 'conversation.search':
            require(not params.get('text'))
        # Collection is tied to the exact send receipt inside conversation.send.
        # A free-standing collect would risk returning an unrelated old response.
        require(params['action'] != 'conversation.collect', 'INVALID_ARGUMENT')
        existing = self.store.conn.execute('SELECT 1 FROM jobs WHERE idempotency_key=?', (params['idempotency_key'],)).fetchone()
        require(existing or not self.queue.full(), 'RESOURCE_EXHAUSTED')
        result, duplicate = self.store.create(uid, params, self.config.queue_limit)
        if not duplicate:
            self.payloads[result['job_id']] = dict(params)
            self.queue.put_nowait((result['job_id'], uid))
        return {**result, 'duplicate': duplicate}

    def get(self, job_id, uid):
        result = self.store.get(job_id, uid)
        cached = self.results.get(job_id)
        result['result_available'] = bool(cached and cached[0] > time.monotonic())
        if result['result_available']:
            result['result'] = cached[1]
        return result

    def cancel(self, job_id, uid):
        result = self.store.get(job_id, uid)
        if result['state'] in TERMINAL:
            return result
        self.store.transition(job_id, 'cancelled', 'CANCELLED')
        self.payloads.pop(job_id, None)
        if self.active_job == job_id and self.active_task:
            self.active_task.cancel()
        return self.get(job_id, uid)

    async def execute(self, job_id, uid, payload):
        started = time.monotonic()
        self.store.transition(job_id, 'preflight')
        try:
            async with asyncio.timeout(self.config.job_timeout), self.browser.lock:
                authorize(self.config, payload['provider'], payload['action'], payload['conversation_ref'])
                await self.browser.ensure(payload['provider'])
                provider = FixtureProvider(self.browser) if payload['provider'] == 'local_fixture' else ChatGPTProvider(self.browser)
                result = await provider.open_conversation(payload['conversation_ref'])
                self.store.transition(job_id, 'running')
                if payload['action'] == 'conversation.send':
                    baseline = {'url_sha256': hashlib.sha256(self.browser.page.url.encode()).hexdigest(),
                                'conversation_verified': result.get('conversation_verified') is True,
                                'receipt': job_id}
                    self.store.attempted(job_id, baseline)  # Durable intent BEFORE any send/compose.
                    await provider.send_message(payload['text'], receipt_id=job_id)
                    self.store.confirmed(job_id)
                    result = await provider.wait_for_response(receipt_id=job_id, timeout_s=self.config.job_timeout)
                elif payload['action'] == 'conversation.search':
                    result = await provider.search(payload.get('text', ''))
                elif payload['action'] == 'conversation.inspect':
                    result = await provider.inspect_context()
                self.store.transition(job_id, 'completed')
                while len(self.results) >= 128:
                    self.results.pop(next(iter(self.results)))
                self.results[job_id] = (time.monotonic() + 120, result)
        except asyncio.CancelledError:
            row = self.store.get(job_id, uid)
            if row['state'] not in TERMINAL:
                self.store.transition(job_id, 'uncertain', 'ACTION_UNCERTAIN')
            await self.browser.close()
            raise
        except Exception as exc:
            row = self.store.get(job_id, uid)
            if row['state'] not in TERMINAL:
                code = exc.code if isinstance(exc, HermodError) else ('TIMEOUT' if isinstance(exc, TimeoutError) else 'NAVIGATION_FAILED')
                state = ('uncertain' if row['may_have_side_effects'] else
                         'auth_required' if code == 'AUTH_REQUIRED' else
                         'human_action_required' if code == 'HUMAN_ACTION_REQUIRED' else 'failed')
                self.store.transition(job_id, state, code)
            await self.browser.close()
        finally:
            self.browser.last_used = time.monotonic()
            LOGGER.info('job job_id=%s provider=%s action=%s state=%s duration_ms=%d error_code=%s profile_version=1 ui_adapter_version=v1',
                        job_id, payload['provider'], payload['action'], self.store.get(job_id, uid)['state'],
                        (time.monotonic() - started) * 1000, self.store.get(job_id, uid)['error_code'])

    async def worker(self):
        while True:
            self.results = {k: v for k, v in self.results.items() if v[0] > time.monotonic()}
            try:
                job_id, uid = await asyncio.wait_for(self.queue.get(), .25)
            except asyncio.TimeoutError:
                await self.browser.idle()
                continue
            payload = self.payloads.pop(job_id, None)
            if not payload:
                self.queue.task_done()
                continue
            self.active_job = job_id
            self.active_task = asyncio.create_task(self.execute(job_id, uid, payload))
            try:
                await self.active_task
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
            finally:
                self.active_task = self.active_job = None
                self.queue.task_done()
