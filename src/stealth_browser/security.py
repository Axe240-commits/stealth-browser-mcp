"""SSRF-hardened URL validation with DNS resolution checks."""

import ipaddress
import socket
from urllib.parse import urlparse


class SecurityError(Exception):
    """Raised when a URL fails security validation."""


BLOCKED_SCHEMES = {"file", "javascript", "data", "ftp", "gopher"}
ALLOWED_SCHEMES = {"http", "https"}


def is_private_ip(ip_str: str) -> bool:
    """Check if IP is private, loopback, link-local, reserved, or cloud metadata."""
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip_str in ("169.254.169.254", "fd00::1")  # cloud metadata
    )


def validate_url(url: str) -> None:
    """Full SSRF validation: scheme check + DNS resolution + IP check.

    Raises SecurityError if the URL is unsafe.
    """
    parsed = urlparse(url)

    # Scheme check
    if parsed.scheme not in ALLOWED_SCHEMES:
        raise SecurityError(f"Blocked scheme: {parsed.scheme!r}. Only http/https allowed.")

    if not parsed.hostname:
        raise SecurityError("No hostname in URL")

    # DNS resolve and check all IPs
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        raise SecurityError(f"DNS resolution failed for: {parsed.hostname}")

    for info in infos:
        ip_str = info[4][0]
        if is_private_ip(ip_str):
            raise SecurityError(
                f"Blocked: {parsed.hostname} resolves to private/reserved IP {ip_str}"
            )


def validate_redirect(url: str) -> None:
    """Validate a redirect target URL. Same checks as validate_url."""
    validate_url(url)


def smart_truncate(text: str, max_length: int) -> tuple[str, bool]:
    """Truncate text on paragraph boundary.

    Returns (text, was_truncated).
    """
    if len(text) <= max_length:
        return text, False

    # Try paragraph boundary first
    cut = text[:max_length].rsplit("\n\n", 1)[0]
    if len(cut) < max_length * 0.5:
        # Paragraph boundary too far back, try line boundary
        cut = text[:max_length].rsplit("\n", 1)[0]
    if len(cut) < max_length * 0.5:
        # Just hard cut
        cut = text[:max_length]

    return cut + "\n\n[... truncated]", True
