import argparse
import signal

from hermod.fixture_site import FixtureSite


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Loopback-only synthetic fixture; no local file serving')
    parser.add_argument('--port', type=int, default=18767)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use a non-privileged port')
    with FixtureSite(args.port) as site:
        print(site.origin, flush=True)
        try:
            signal.pause()
        except KeyboardInterrupt:
            pass
