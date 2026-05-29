from __future__ import annotations

import argparse

from Backend.core.database import SessionLocal, init_database
from Backend.domain.security.models import User
from Backend.domain.security.passwords import hash_password, validate_password_policy


def reset_user_password(username: str, password: str, role: str) -> None:
    validate_password_policy(password)
    init_database()

    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).one_or_none()
        if user is None:
            user = User(username=username, password_hash=hash_password(password), role=role)
            db.add(user)
            action = "Created"
        else:
            user.password_hash = hash_password(password)
            user.role = role
            action = "Updated"
        db.commit()

    print(f"{action} user '{username}' with role '{role}'.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or reset a QuantGrid user password.")
    parser.add_argument("username")
    parser.add_argument("password")
    parser.add_argument("--role", default="admin", choices=["admin", "developer", "trader", "analyst", "viewer", "ops"])
    args = parser.parse_args()

    reset_user_password(args.username, args.password, args.role)


if __name__ == "__main__":
    main()
