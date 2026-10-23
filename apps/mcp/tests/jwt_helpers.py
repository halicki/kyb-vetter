"""Test-only RSA signer: mints access tokens the hosted server should accept (or refuse)."""

import time
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

ISSUER = "https://tenant.eu.auth0.com/"
JWKS_URL = "https://tenant.eu.auth0.com/.well-known/jwks.json"
DOMAIN = "mcp.example.test"
AUDIENCE = f"https://{DOMAIN}/mcp"


class Signer:
    def __init__(self, kid: str = "key-1") -> None:
        self.kid = kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._pem = self._key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def jwks(self) -> dict[str, Any]:
        public = RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return {"keys": [{**public, "kid": self.kid, "use": "sig", "alg": "RS256"}]}

    def token(self, subject: str = "auth0|alice", **overrides: Any) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "sub": subject,
            "aud": [AUDIENCE, f"{ISSUER}userinfo"],
            "iat": now,
            "exp": now + 3600,
            "azp": "client-abc",
            "scope": "openid",
        }
        claims.update(overrides)
        return jwt.encode(claims, self._pem, algorithm="RS256", headers={"kid": self.kid})
