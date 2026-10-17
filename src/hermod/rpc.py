import asyncio
import grp
import json
import os
import socket
import stat
import struct

from . import PROTOCOL_VERSION
from .errors import HermodError, require

MAX_REQUEST = 65536
MAX_RESPONSE = 262144


def loads(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result
    def constant(_):
        raise HermodError('INVALID_ARGUMENT')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


class RpcServer:
    def __init__(self, config, dispatch):
        self.config, self.dispatch = config, dispatch
        self.server = None
        self.connections = set()

    async def start(self):
        path = self.config.socket_path
        require(not any(p.is_symlink() for p in [path, *path.parents]), 'FORBIDDEN')
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = path.parent.stat()
        require(info.st_uid == os.getuid() and info.st_mode & 0o007 == 0, 'FORBIDDEN')
        if self.config.socket_group:
            gid = grp.getgrnam(self.config.socket_group).gr_gid
            os.chown(path.parent, -1, gid)
            os.chmod(path.parent, 0o770)
        if path.exists():
            info = path.lstat()
            require(stat.S_ISSOCK(info.st_mode) and info.st_uid == os.getuid(), 'FORBIDDEN')
            try:
                _, writer = await asyncio.wait_for(asyncio.open_unix_connection(path), .5)
            except ConnectionRefusedError:
                path.unlink()  # Exact stale owned socket, never a directory/glob.
            else:
                writer.close()
                await writer.wait_closed()
                raise HermodError('SESSION_BUSY')
        self.server = await asyncio.start_unix_server(self.handle, path=path, limit=MAX_REQUEST)
        if self.config.socket_group:
            os.chown(path, -1, gid)
        os.chmod(path, 0o660 if self.config.socket_group else 0o600)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.connections.add(task)
        request_id = None
        try:
            require(len(self.connections) <= 16, 'RESOURCE_EXHAUSTED')
            peer = writer.get_extra_info('socket')
            require(hasattr(socket, 'SO_PEERCRED'), 'FORBIDDEN')
            _, uid, _ = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            require(uid in self.config.allowed_uids, 'FORBIDDEN')
            data = await asyncio.wait_for(reader.readuntil(b'\n'), 5)
            require(len(data) <= MAX_REQUEST)
            request = loads(data.decode('utf-8'))
            require(isinstance(request, dict) and set(request) == {'version', 'request_id', 'method', 'params'})
            require(type(request['version']) is int and request['version'] == PROTOCOL_VERSION, 'UNSUPPORTED_VERSION')
            request_id = request['request_id']
            require(isinstance(request_id, str) and 1 <= len(request_id) <= 64 and
                    all(c.isalnum() or c in '-_' for c in request_id))
            require(isinstance(request['method'], str) and isinstance(request['params'], dict))
            async with asyncio.timeout(15):
                result = await self.dispatch(request['method'], request['params'], uid)
            response = {'version': 1, 'request_id': request_id, 'ok': True, 'result': result}
        except asyncio.CancelledError:
            writer.close()
            self.connections.discard(task)
            raise
        except Exception as exc:
            code = exc.code if isinstance(exc, HermodError) else 'INVALID_ARGUMENT'
            response = {'version': 1, 'request_id': request_id, 'ok': False,
                        'error': {'code': code, 'message': 'Hermod 요청을 완료하지 못했습니다.', 'retryable': False}}
        try:
            encoded = (json.dumps(response, ensure_ascii=False) + '\n').encode()
            if len(encoded) > MAX_RESPONSE:
                encoded = (json.dumps({'version': 1, 'request_id': request_id, 'ok': False,
                    'error': {'code': 'RESOURCE_EXHAUSTED', 'retryable': False}}) + '\n').encode()
            writer.write(encoded)
            await asyncio.wait_for(writer.drain(), 5)
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass
            self.connections.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
            self.config.socket_path.unlink(missing_ok=True)
        for task in tuple(self.connections):
            task.cancel()
        if self.connections:
            await asyncio.gather(*tuple(self.connections), return_exceptions=True)


async def call(path, method, params=None):
    import uuid
    request_id = uuid.uuid4().hex
    data = (json.dumps({'version': 1, 'request_id': request_id, 'method': method,
                        'params': params or {}}, ensure_ascii=False) + '\n').encode()
    require(len(data) <= MAX_REQUEST)
    async with asyncio.timeout(20):
        reader, writer = await asyncio.open_unix_connection(path, limit=MAX_RESPONSE)
        try:
            writer.write(data)
            await writer.drain()
            response = loads((await reader.readuntil(b'\n')).decode())
            require(response['version'] == 1, 'UNSUPPORTED_VERSION')
            if not response['ok']:
                require(response.get('request_id') in (None, request_id), 'UNSUPPORTED_VERSION')
                raise HermodError(response['error']['code'])
            require(response['request_id'] == request_id, 'UNSUPPORTED_VERSION')
            return response['result']
        finally:
            writer.close()
            await writer.wait_closed()
