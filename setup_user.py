#!/usr/bin/env python3
"""CLI tool to set up dashboard users.

Usage:
    python setup_user.py --username jason --password "secure_password" --name "Jason Heath"
    python setup_user.py --username michelle --password "michelles_password" --name "Michelle Heath"
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Set up email dashboard user")
    parser.add_argument("--username", required=True, help="Username for login")
    parser.add_argument("--password", required=True, help="Password (stored as bcrypt hash)")
    parser.add_argument("--name", required=True, help="Display name")
    parser.add_argument("--email", default=None, help="Email address (optional)")
    parser.add_argument("--db", default=None, help="Path to auth.db (default: ./auth.db)")
    args = parser.parse_args()

    db_path = Path(args.db) if args.db else Path(__file__).parent / "auth.db"
    
    from auth import UserManager
    
    manager = UserManager(db_path)
    
    # Check if user exists
    if manager.get_user(args.username):
        print(f"✗ User '{args.username}' already exists.")
        sys.exit(1)
    
    # Create user
    success = manager.create_user(
        username=args.username,
        password=args.password,
        display_name=args.name,
        email=args.email
    )
    
    if success:
        print(f"✓ User '{args.username}' created successfully.")
        print(f"  Display name: {args.name}")
        if args.email:
            print(f"  Email: {args.email}")
        print(f"\n  Login at http://localhost:9999/login")
    else:
        print(f"✗ Failed to create user '{args.username}'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
