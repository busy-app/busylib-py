class BusyBarAPIError(Exception):
    def __init__(self, error: str, code: int | None = None):
        self.error = error
        self.code = code
        super().__init__(f"API Error: {error} (code: {code})")
