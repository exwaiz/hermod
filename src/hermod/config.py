from dataclasses import dataclass, field
from pathlib import Path
import os
import pwd
import re
import stat
import tomllib
from urllib.parse import urlsplit

from .errors import require


def private_directory(path):
    path = Path(path)
    require(path.is_absolute() and path not in (Path('/'), Path.home()), 'FORBIDDEN')
    for parent in [path, *path.parents]:
        require(not parent.is_symlink(), 'FORBIDDEN')
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid() and
            stat.S_IMODE(info.st_mode) == 0o700, 'FORBIDDEN')
    return path


def chatgpt_url(url):
    require(isinstance(url, str) and len(url) <= 2048)
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and parsed.netloc == 'chatgpt.com' and
            re.fullmatch(r'/c/[A-Za-z0-9_-]{1,160}', parsed.path) is not None and
            not parsed.query and not parsed.fragment, 'PAGE_MISMATCH')
    return url


@dataclass(frozen=True)
class Config:
    state_dir: Path
    socket_path: Path
    allowed_uids: tuple[int, ...]
    test_mode: bool = False
    socket_group: str | None = None
    fixture_origin: str | None = None
    browser_executable: str | None = None
    queue_limit: int = 10
    job_timeout: float = 120
    navigation_timeout: float = 30
    idle_timeout: float = 600
    min_disk_bytes: int = 104857600
    soft_rss_bytes: int = 805306368
    conversations: dict = field(default_factory=dict, repr=False)

    def validate(self):
        require(os.getuid() != 0, 'FORBIDDEN')
        require(type(self.test_mode) is bool)
        require(self.state_dir.is_absolute() and self.socket_path.is_absolute() and
                len(str(self.socket_path).encode()) < 104)
        require(self.allowed_uids and all(type(v) is int and v > 0 for v in self.allowed_uids))
        for value, low, high in ((self.queue_limit, 1, 10), (self.job_timeout, 1, 120),
                                 (self.navigation_timeout, 1, 30), (self.idle_timeout, 1, 600),
                                 (self.min_disk_bytes, 0, 10**12), (self.soft_rss_bytes, 50000000, 2000000000)):
            require(type(value) in (int, float) and low <= value <= high)
        if not self.test_mode:
            require(self.state_dir == Path('/var/lib/hermod') and
                    self.socket_path == Path('/run/hermod/hermod.sock') and
                    self.socket_group == 'hermod-clients', 'FORBIDDEN')
            require(self.fixture_origin is None, 'FORBIDDEN')
        if self.fixture_origin:
            u = urlsplit(self.fixture_origin)
            require(self.test_mode and u.scheme == 'http' and u.hostname == '127.0.0.1' and
                    u.port and u.netloc == f'127.0.0.1:{u.port}' and not u.path and
                    not u.query and not u.fragment, 'FORBIDDEN')
        require(isinstance(self.conversations, dict) and len(self.conversations) <= 10000)
        for ref, record in self.conversations.items():
            require(re.fullmatch(r'cgpt:[A-Za-z0-9_-]{1,160}', ref) is not None)
            require(set(record) == {'provider', 'url', 'verified'} and record['provider'] == 'chatgpt' and
                    record['verified'] is True, 'PAGE_MISMATCH')
            chatgpt_url(record['url'])
        return self

    @classmethod
    def load(cls, path):
        raw = tomllib.loads(Path(path).read_text())
        raw['state_dir'] = Path(raw['state_dir'])
        raw['socket_path'] = Path(raw['socket_path'])
        raw['allowed_uids'] = tuple(raw['allowed_uids'])
        return cls(**raw).validate()
