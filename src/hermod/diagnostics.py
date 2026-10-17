"""Safe diagnostic metadata only; screenshots require a synthetic opt-in smoke."""
from .browser import package_version, process_rss


def metadata():
    return {'playwright': package_version(), 'observed_rss_bytes': process_rss(),
            'screenshots_enabled': False, 'traces_enabled': False, 'har_enabled': False}
