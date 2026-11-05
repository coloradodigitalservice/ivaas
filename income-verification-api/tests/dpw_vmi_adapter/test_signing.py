"""Tests for DPW VMI webhook signing."""

from dpw_vmi_adapter.signing import sign, verify

BODY = b'{"event_type":"TransmissionComplete"}'
KEY = "test-signing-key"
TIMESTAMP = "1764709880"
SIGNATURE = (
    "44b72ed1c66a1d35de0084d86f269b679030a59bbf32bebfa27020f2d6ccb08d"
    "af5ed7f0909d1cbd9d237d21074a4bf5d0a8b5470dfffd0aa71dd1acd2b4da99"
)


def test_sign_matches_dpw_recipe() -> None:
    # Expected value produced independently with OpenSSL.
    assert sign(BODY, key=KEY, timestamp=TIMESTAMP) == SIGNATURE


def test_verify_accepts_matching_signature() -> None:
    assert verify(BODY, key=KEY, timestamp=TIMESTAMP, signature=SIGNATURE)


def test_verify_rejects_non_matching_signature() -> None:
    assert not verify(BODY, key=KEY, timestamp=TIMESTAMP, signature=f"0{SIGNATURE[1:]}")


def test_verify_rejects_non_ascii_signature() -> None:
    assert not verify(BODY, key=KEY, timestamp=TIMESTAMP, signature="é" * 128)


def test_verify_rejects_tampered_body() -> None:
    assert not verify(BODY + b" ", key=KEY, timestamp=TIMESTAMP, signature=SIGNATURE)
