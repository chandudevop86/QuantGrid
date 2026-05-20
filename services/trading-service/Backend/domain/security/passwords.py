from __future__ import annotations

import re

from passlib.context import CryptContext

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return password_context.verify(password, password_hash)


def validate_password_policy(password: str) -> None:
    if len(password) < 10:
        raise ValueError("Password must be at least 10 characters.")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must include a lowercase letter.")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must include an uppercase letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must include a number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must include a special character.")
