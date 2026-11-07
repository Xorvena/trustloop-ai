class ServiceError(Exception):
    """Domain error mapped to an HTTP response by main.py. Messages are safe to show to clients."""
    def __init__(self, status_code: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status_code, self.code, self.message, self.extra = status_code, code, message, extra or {}
