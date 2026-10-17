import argparse
import asyncio
import json
import logging
import os
import signal

from .config import Config
from .daemon import Daemon
from .errors import HermodError
from .rpc import call


async def serve(config):
    daemon = Daemon(config)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        await daemon.start()
        logging.getLogger('hermod').info('hermod_ready protocol_version=1')
        await stop.wait()
    finally:
        await daemon.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='Independent Hermod daemon and local RPC client')
    parser.add_argument('--config', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('serve')
    request = commands.add_parser('call')
    request.add_argument('method')
    request.add_argument('--params-stdin', action='store_true', help='Read private JSON from stdin, never CLI history')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    try:
        config = Config.load(args.config)
        if args.command == 'serve':
            asyncio.run(serve(config))
        else:
            import sys
            params = json.load(sys.stdin) if args.params_stdin else {}
            print(json.dumps(asyncio.run(call(config.socket_path, args.method, params)), ensure_ascii=False))
    except Exception as exc:
        code = exc.code if isinstance(exc, HermodError) else 'INTERNAL_ERROR'
        print(json.dumps({'ok': False, 'error': {'code': code}}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
