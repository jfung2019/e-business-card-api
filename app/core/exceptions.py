class OpenRouterError(Exception):
    """Raised when OpenRouter returns an error or unusable response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenRouterTimeoutError(OpenRouterError):
    """Raised when OpenRouter does not respond within the configured timeout."""


class CardPersistenceError(Exception):
    """Raised when MongoDB persistence fails validation or write operations."""


class ScanImageNotFoundError(Exception):
    """Raised when a card has no scan image or the GridFS file is missing."""


class CardNotFoundError(Exception):
    """Raised when a captured card cannot be found for the authenticated user."""
