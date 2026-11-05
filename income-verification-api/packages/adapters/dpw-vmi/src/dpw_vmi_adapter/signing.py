"""Sign DPW VMI webhook request bodies."""

import hashlib
import hmac


def sign(body: bytes, *, key: str, timestamp: str) -> str:
    """Return the lowercase hex HMAC-SHA512 of the timestamp, a colon, and the body."""
    message = timestamp.encode() + b":" + body
    return hmac.new(key.encode(), message, hashlib.sha512).hexdigest()


def verify(body: bytes, *, key: str, timestamp: str, signature: str) -> bool:
    """Return whether signature matches; the caller checks the timestamp's age."""
    expected_signature = sign(body, key=key, timestamp=timestamp)
    return hmac.compare_digest(signature.encode(), expected_signature.encode())
