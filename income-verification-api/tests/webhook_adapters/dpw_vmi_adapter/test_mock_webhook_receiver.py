"""Check the local program webhook receiver."""

import hashlib
import hmac
import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

_SCRIPT = Path(__file__).parents[3] / "packages/adapters/dpw-vmi/scripts/mock_webhook_receiver.py"
_signature_is_valid = cast(Callable[..., bool], runpy.run_path(str(_SCRIPT))["_signature_is_valid"])


def test_signature_validation() -> None:
    body = b'{"event_type":"ReportSubmission"}'
    key = "00000000000000000000000000000000"
    timestamp = "1800000000"
    signature = hmac.new(key.encode(), timestamp.encode() + b":" + body, hashlib.sha512).hexdigest()

    assert _signature_is_valid(body, timestamp=timestamp, signature=signature)
    assert not _signature_is_valid(body, timestamp=timestamp, signature="wrong")
