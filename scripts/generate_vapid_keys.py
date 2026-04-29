from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_numbers = private_key.private_numbers()
    public_numbers = private_numbers.public_numbers

    private_bytes = private_numbers.private_value.to_bytes(32, "big")
    public_bytes = (
        b"\x04"
        + public_numbers.x.to_bytes(32, "big")
        + public_numbers.y.to_bytes(32, "big")
    )

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    print("WEB_PUSH_VAPID_PUBLIC_KEY=" + b64url(public_bytes))
    print("WEB_PUSH_VAPID_PRIVATE_KEY=" + b64url(private_bytes))
    print()
    print("# PEM copy for backup")
    print(pem)


if __name__ == "__main__":
    main()
