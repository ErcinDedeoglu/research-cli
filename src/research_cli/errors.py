class MissingKeyError(Exception):
    def __init__(
        self,
        provider: str,
        env_vars: tuple[str, ...],
        *,
        detail: str | None = None,
    ) -> None:
        self.provider = provider
        self.env_vars = env_vars
        listed = " or ".join(env_vars)
        super().__init__(detail or f"missing API key for {provider}; set {listed}")


class ProviderHttpError(Exception):
    def __init__(self, provider: str, status: int, body: str) -> None:
        self.provider = provider
        self.status = status
        self.body = body
        snippet = body.strip() or "(empty body)"
        if len(snippet) > 2000:
            snippet = snippet[:2000] + "…"
        super().__init__(f"{provider} HTTP {status}: {snippet}")


class UpdateError(Exception):
    """Raised when an explicit --self-update cannot finish."""
