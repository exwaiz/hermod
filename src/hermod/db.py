from contextlib import contextmanager
import hashlib
import json
import os
import re
import sqlite3
import time

from .config import private_directory
from .errors import require

TERMINAL = frozenset({'completed', 'failed', 'cancelled', 'uncertain', 'auth_required', 'human_action_required'})


class Store:
    def __init__(self, config):
        root = private_directory(config.state_dir)
        path = root / 'jobs.sqlite3'
        require(not path.is_symlink(), 'FORBIDDEN')
        if path.exists():
            require(path.stat().st_uid == os.getuid() and path.stat().st_mode & 0o077 == 0, 'FORBIDDEN')
        self.conn = sqlite3.connect(path, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        os.chmod(path, 0o600)
        self.conn.executescript('''PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON;
            PRAGMA busy_timeout=5000;
            CREATE TABLE IF NOT EXISTS jobs(
            number INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT NOT NULL UNIQUE,
            creator_uid INTEGER NOT NULL, provider TEXT NOT NULL, action TEXT NOT NULL,
            conversation_ref TEXT NOT NULL, requested_by TEXT NOT NULL, purpose TEXT NOT NULL,
            policy_version TEXT NOT NULL, payload_sha256 TEXT NOT NULL, text_sha256 TEXT NOT NULL,
            state TEXT NOT NULL, action_attempted_at REAL, action_confirmed_at REAL,
            pre_action_baseline TEXT, may_have_side_effects INTEGER NOT NULL DEFAULT 0,
            error_code TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(state,created_at);''')

    @contextmanager
    def transaction(self):
        self.conn.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.conn.execute('COMMIT')
        except BaseException:
            self.conn.execute('ROLLBACK')
            raise

    def create(self, uid, params, maximum):
        fingerprint = hashlib.sha256(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.transaction():
            row = self.conn.execute('SELECT * FROM jobs WHERE idempotency_key=?', (params['idempotency_key'],)).fetchone()
            if row:
                require(row['creator_uid'] == uid and row['payload_sha256'] == fingerprint, 'DUPLICATE_REQUEST')
                return self.public(row), True
            require(self.conn.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','preflight','running')").fetchone()[0] < maximum,
                    'RESOURCE_EXHAUSTED')
            require(self.conn.execute('SELECT count(*) FROM jobs').fetchone()[0] < 100000,
                    'RESOURCE_EXHAUSTED')
            stamp = time.time()
            cursor = self.conn.execute('''INSERT INTO jobs(idempotency_key,creator_uid,provider,action,
                conversation_ref,requested_by,purpose,policy_version,payload_sha256,text_sha256,state,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,'queued',?,?)''',
                (params['idempotency_key'], uid, params['provider'], params['action'], params['conversation_ref'],
                 params['requested_by'], params['purpose'], params['policy_version'], fingerprint,
                 hashlib.sha256(params.get('text', '').encode()).hexdigest(), stamp, stamp))
            return self.get(f'HB-{cursor.lastrowid:06d}', uid), False

    def public(self, row):
        return {'job_id': f"HB-{row['number']:06d}", **{k: row[k] for k in
            ('state', 'provider', 'action', 'error_code', 'action_attempted_at', 'action_confirmed_at')},
            'may_have_side_effects': bool(row['may_have_side_effects'])}

    def row(self, job_id, uid):
        require(isinstance(job_id, str) and re.fullmatch(r'HB-\d{6,10}', job_id) is not None)
        row = self.conn.execute('SELECT * FROM jobs WHERE number=? AND creator_uid=?', (int(job_id[3:]), uid)).fetchone()
        require(row is not None, 'JOB_NOT_FOUND')
        return row

    def get(self, job_id, uid):
        return self.public(self.row(job_id, uid))

    def transition(self, job_id, state, error=None):
        row = self.conn.execute('SELECT state FROM jobs WHERE number=?', (int(job_id[3:]),)).fetchone()
        transitions = {'queued': {'preflight', 'cancelled', 'failed'}, 'preflight': {'running', *TERMINAL},
                       'running': set(TERMINAL), 'uncertain': {'completed', 'failed'}}
        require(row and state in transitions.get(row[0], set()), 'INVALID_TRANSITION')
        self.conn.execute('UPDATE jobs SET state=?,error_code=?,updated_at=? WHERE number=?',
                          (state, error, time.time(), int(job_id[3:])))

    def attempted(self, job_id, baseline):
        self.conn.execute('''UPDATE jobs SET action_attempted_at=?,may_have_side_effects=1,
            pre_action_baseline=?,updated_at=?
            WHERE number=? AND state='running' ''', (time.time(), json.dumps(baseline), time.time(), int(job_id[3:])))

    def confirmed(self, job_id):
        self.conn.execute('UPDATE jobs SET action_confirmed_at=?,updated_at=? WHERE number=?',
                          (time.time(), time.time(), int(job_id[3:])))

    def recover(self):
        with self.transaction():
            self.conn.execute("UPDATE jobs SET state='uncertain',error_code='ACTION_UNCERTAIN',updated_at=? WHERE state IN ('running','preflight')", (time.time(),))
            self.conn.execute("UPDATE jobs SET state='failed',error_code='PAYLOAD_UNAVAILABLE',updated_at=? WHERE state='queued'", (time.time(),))

    def close(self):
        self.conn.close()
