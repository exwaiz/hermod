from .errors import require


async def unique(locator):
    require(await locator.count() == 1, 'UI_CHANGED')
    return locator
