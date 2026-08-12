"""Scanner adapters: normalize third-party scanner output into Findings."""


class ScannerUnavailableError(RuntimeError):
    """The adapter's scanner cannot run. Callers must fail, never skip:
    a skip would turn CI green while the baseline is effectively disabled."""
