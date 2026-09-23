"""Stable business errors for the content service boundary."""


class ContentError(ValueError):
    def __init__(self, code: str, status: int = 400) -> None:
        self.code = code
        self.status = status
        super().__init__(code)
