"""Safe errors raised by external generation providers."""


class ProviderError(RuntimeError):
    """A provider could not complete a request without exposing implementation details."""


class ProviderConfigurationError(ProviderError):
    """A provider cannot run because a required setting is absent or invalid."""
