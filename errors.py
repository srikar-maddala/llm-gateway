def classify_error(exc: Exception) -> str:
    """Return a category name for an exception raised by LiteLLM."""
    # Names of this error's class and every class it inherits from,
    # e.g. {"NotFoundError", "OpenAIError", "Exception", ...}
    names = {cls.__name__ for cls in type(exc).__mro__}

    if "RateLimitError" in names:
        return "rate_limit"
    if "Timeout" in names or "APITimeoutError" in names:
        return "timeout"
    if "AuthenticationError" in names or "PermissionDeniedError" in names:
        return "auth_error"
    if "NotFoundError" in names:
        return "model_not_found"
    if "ServiceUnavailableError" in names or "InternalServerError" in names:
        return "server_error"
    if "APIConnectionError" in names:
        return "connection_error"
    if "BadRequestError" in names:
        return "bad_request"

    # Fallback: many errors carry the provider's HTTP status code
    status = getattr(exc, "status_code", None)
    if status == 429:
        return "rate_limit"
    if status in (401, 403):
        return "auth_error"
    if status == 404:
        return "model_not_found"
    if status == 408:
        return "timeout"
    if isinstance(status, int) and status >= 500:
        return "server_error"
    if isinstance(status, int) and 400 <= status < 500:
        return "bad_request"

    return "unknown"