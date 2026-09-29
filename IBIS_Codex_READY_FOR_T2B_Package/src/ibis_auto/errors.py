class IbisError(Exception):
    """A diagnosed generation failure."""

    def __init__(self, code: str, message: str, level: str = "PROJECT"):
        super().__init__(message)
        self.code = code
        self.level = level

