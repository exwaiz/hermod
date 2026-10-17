from urllib.parse import urlsplit

from .errors import require, HermodError

CAPABILITIES = {
    'chatgpt': frozenset({'OPEN'}),
    'local_fixture': frozenset({'OPEN', 'SEARCH', 'COMPOSE', 'SUBMIT', 'COLLECT', 'READ_HISTORY'}),
}
ACTIONS = {'conversation.open': 'OPEN', 'conversation.inspect': 'OPEN',
           'conversation.search': 'SEARCH', 'conversation.send': 'SUBMIT', 'conversation.collect': 'COLLECT'}


def authorize(config, provider, action, ref):
    require(provider in CAPABILITIES and action in ACTIONS)
    if ACTIONS[action] not in CAPABILITIES[provider]:
        raise HermodError('POLICY_REVIEW_REQUIRED')
    if provider == 'local_fixture':
        require(config.test_mode and config.fixture_origin, 'PROVIDER_DISABLED')
        require(ref in {'fixture:demo', 'fixture:second', 'fixture:auth', 'fixture:changed',
                        'fixture:slow', 'fixture:mismatch', 'fixture:human'}, 'PAGE_MISMATCH')
        return config.fixture_origin + '/threads/' + ref.split(':')[1]
    require(ref in config.conversations, 'PAGE_MISMATCH')
    return config.conversations[ref]['url']


def allowed_url(config, url, provider):
    try:
        u = urlsplit(url)
        if u.username or u.password or u.fragment:
            return False
        if provider == 'local_fixture':
            return config.test_mode and f'{u.scheme}://{u.netloc}' == config.fixture_origin
        return u.scheme == 'https' and u.netloc == 'chatgpt.com'
    except ValueError:
        return False
