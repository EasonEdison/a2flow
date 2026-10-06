"""Validation failure with a stable machine-readable code."""

class ValidationError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code, self.status = code, status
        super().__init__(code)
