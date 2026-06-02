"""
Admin CLI to create a new user in the database.

Usage:
    python scripts/create_user.py <email> <password>

Requires DATABASE_URL and MASTER_ENCRYPTION_KEY env vars to be set (or a .env file).
"""
import sys
import os

# Allow running from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from modules.auth import user_store


def main():
    if len(sys.argv) != 3:
        print("Usage: python scripts/create_user.py <email> <password>")
        sys.exit(1)

    email = sys.argv[1]
    password = sys.argv[2]

    if len(password) < 8:
        print("Error: password must be at least 8 characters.")
        sys.exit(1)

    try:
        user_store.init_db()
        existing = user_store.get_user_by_email(email)
        if existing:
            print(f"Error: user with email '{email}' already exists (id={existing.id}).")
            sys.exit(1)
        user = user_store.create_user(email, password)
        print(f"User created successfully: id={user.id}, email={user.email}")
    except Exception as exc:
        print(f"Failed to create user: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
