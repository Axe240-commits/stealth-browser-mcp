"""Proxy management stub. Phase 2: Tor integration."""


class ProxyManager:
    """Stub proxy manager. Returns None (direct connection) for MVP."""

    def get_proxy(self, domain: str = "") -> dict | None:
        """Get proxy config for a domain. Returns None for direct connection."""
        return None
