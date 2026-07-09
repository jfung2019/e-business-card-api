class OpenRouterError(Exception):
    """Raised when OpenRouter returns an error or unusable response."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OpenRouterTimeoutError(OpenRouterError):
    """Raised when OpenRouter does not respond within the configured timeout."""


class OpenRouterSafetyError(OpenRouterError):
    """Raised when OCR input or LLM output fails safety validation."""


class LlmRateLimitExceeded(Exception):
    """Raised when a user exceeds configured LLM call quotas."""

    def __init__(self, message: str, *, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class CardPersistenceError(Exception):
    """Raised when MongoDB persistence fails validation or write operations."""


class ScanImageNotFoundError(Exception):
    """Raised when a card has no scan image or the GridFS file is missing."""


class CardNotFoundError(Exception):
    """Raised when a captured card cannot be found for the authenticated user."""
