import asyncio

from ..authz import authorize
from ..errors import require, HermodError
from ..locator import unique


class FixtureProvider:
    name = 'local_fixture'

    def __init__(self, manager):
        self.manager = manager
        self.ref = None

    async def auth_status(self):
        page = self.manager.page
        if await page.get_by_role('heading', name='Manual security check', exact=True).count():
            return 'human_action_required'
        if await page.get_by_role('heading', name='Sign in required', exact=True).count():
            return 'auth_required'
        return 'ready'

    async def open_conversation(self, conversation_ref):
        url = authorize(self.manager.config, self.name, 'conversation.open', conversation_ref)
        await self.manager.navigate(url)
        self.manager.auth = await self.auth_status()
        if self.manager.auth != 'ready':
            raise HermodError(self.manager.auth.upper())
        marker = await unique(self.manager.page.get_by_role('main'))
        require(await marker.get_attribute('data-thread') == conversation_ref, 'PAGE_MISMATCH')
        self.ref = conversation_ref
        return {'conversation_verified': True, 'mode': 'fixture'}

    async def inspect_context(self):
        require(self.ref is not None, 'PAGE_MISMATCH')
        return {'conversation_verified': True, 'auth': await self.auth_status()}

    async def search(self, text):
        field = await unique(self.manager.page.get_by_role('searchbox', name='Find conversation', exact=True))
        await field.fill(text)
        links = self.manager.page.get_by_role('link', name='Second fixture conversation', exact=True)
        require(await links.count() == 1, 'UI_CHANGED')
        return {'matches': ['fixture:second'] if 'second' in text.casefold() else []}

    async def send_message(self, text, *, receipt_id):
        page = self.manager.page
        field = await unique(page.get_by_role('textbox', name='Message', exact=True))
        receipt = await unique(page.get_by_role('textbox', name='Receipt', exact=True))
        button = await unique(page.get_by_role('button', name='Send', exact=True))
        await receipt.fill(receipt_id)
        await field.fill(text)
        await button.click()
        marker = page.locator(f'[data-submitted="{receipt_id}"]')
        await marker.wait_for(state='attached')
        require(await marker.get_attribute('data-submitted') == receipt_id, 'ACTION_UNCERTAIN')
        return {'receipt_confirmed': True}

    async def wait_for_response(self, *, receipt_id, timeout_s):
        page = self.manager.page
        # Selector and receipt format are internal, not arbitrary user input.
        response = page.get_by_role('status', name='Assistant response', exact=True)
        async with asyncio.timeout(timeout_s):
            while True:
                require(await response.count() == 1, 'UI_CHANGED')
                if await response.get_attribute('data-receipt') == receipt_id and await response.get_attribute('data-state') == 'complete':
                    text = await response.inner_text()
                    await asyncio.sleep(.15)
                    require(await response.get_attribute('data-state') == 'complete' and
                            text == await response.inner_text(), 'RESULT_UNCERTAIN')
                    require(len(text) <= 12000, 'UNSUPPORTED_RESULT')
                    return {'text': text, 'receipt_verified': True, 'completion_verified': True}
                await asyncio.sleep(.03)

    async def cancel_operation(self):
        await self.manager.close()
