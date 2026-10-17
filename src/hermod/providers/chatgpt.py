from ..authz import authorize
from ..errors import HermodError


class ChatGPTProvider:
    """Navigation only. No reading answer text, composing, sending or collecting."""
    name = 'chatgpt'

    def __init__(self, manager):
        self.manager = manager

    async def auth_status(self):
        # No live logged-in DOM contract has been approved/observed. Never infer
        # authentication from navigation success, cookie files or guessed selectors.
        return 'unknown'

    async def open_conversation(self, conversation_ref):
        url = authorize(self.manager.config, self.name, 'conversation.open', conversation_ref)
        try:
            await self.manager.navigate(url)
        except HermodError:
            if '/auth/' in self.manager.page.url or '/login' in self.manager.page.url:
                self.manager.auth = 'auth_required'
                raise HermodError('AUTH_REQUIRED') from None
            raise
        self.manager.auth = await self.auth_status()
        return {'mode': 'manual_handoff', 'navigation_verified': True,
                'auth': self.manager.auth, 'conversation_access_verified': False,
                'reason': 'POLICY_REVIEW_REQUIRED'}

    async def inspect_context(self):
        return {'auth': await self.auth_status(), 'mode': 'manual_handoff',
                'conversation_access_verified': False}

    async def send_message(self, text, *, receipt_id):
        raise HermodError('POLICY_REVIEW_REQUIRED')

    async def wait_for_response(self, *, receipt_id, timeout_s):
        raise HermodError('POLICY_REVIEW_REQUIRED')

    async def cancel_operation(self):
        await self.manager.close()
