"""Independent daemon process and CLI client, no browser or account access."""
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from hermod.rpc import call


async def smoke():
    with tempfile.TemporaryDirectory(prefix='hermod-process-') as directory:
        root = Path(directory)
        config = root / 'config.toml'
        config.write_text(f'state_dir = "{root}/state"\nsocket_path = "{root}/run/h.sock"\nallowed_uids = [{os.getuid()}]\ntest_mode = true\nmin_disk_bytes = 0\n')
        command = [sys.executable, '-m', 'hermod', '--config', str(config)]
        process = subprocess.Popen([*command, 'serve'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            async with asyncio.timeout(10):
                while not (root / 'run/h.sock').exists():
                    if process.poll() is not None:
                        raise RuntimeError('daemon_start_failed')
                    await asyncio.sleep(.03)
            result = await call(root / 'run/h.sock', 'system.health')
            assert result['browser'] == 'stopped'
            client = await asyncio.create_subprocess_exec(*command, 'call', 'system.health',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            output, _ = await client.communicate()
            assert client.returncode == 0 and json.loads(output)['protocol_version'] == 1
        finally:
            process.send_signal(signal.SIGTERM)
            _, logs = await asyncio.to_thread(process.communicate, timeout=10)
        assert process.returncode == 0 and not (root / 'run/h.sock').exists()
        print(json.dumps({'independent_daemon': True, 'standalone_cli': True,
                          'protocol_version': 1, 'graceful_stop': True, 'browser_started': False}))


if __name__ == '__main__':
    asyncio.run(smoke())
