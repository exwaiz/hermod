class HermodError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code='INVALID_ARGUMENT'):
    if not condition:
        raise HermodError(code)
