import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from tests.income_verification.security.authentication_test_support import public_jwk


@pytest.fixture
def rsa_keys() -> tuple[rsa.RSAPrivateKey, jwt.PyJWK]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    signing_key = jwt.PyJWK.from_dict(public_jwk(private_key))
    return private_key, signing_key
