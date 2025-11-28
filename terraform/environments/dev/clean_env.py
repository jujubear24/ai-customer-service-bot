#!/usr/bin/env python3
"""
Script to forcefully clean Terraform cache when paths are too long for OS deletion.
"""

import os
import shutil
import sys
from pathlib import Path


def force_remove_readonly(func: callable, path: str, excinfo: tuple) -> None:
    """
    Error handler for shutil.rmtree.

    If the error is due to an access error (read only file),
    it attempts to add write permission and then retries.
    If the error is "File name too long", we might need to
    rename directories up the tree to shorten the path before deletion,
    but Python's shutil often handles this better than shell.
    """
    # specific handling for read-only files (common in .terraform)
    os.chmod(path, 0o777)
    func(path)


def clean_terraform_cache() -> None:
    """Finds and removes .terraform directories and lock files."""
    cwd = Path.cwd()
    print(f"🧹 Cleaning Terraform cache in: {cwd}")

    # 1. Remove .terraform directory
    terraform_dir = cwd / ".terraform"
    if terraform_dir.exists():
        print(f"   Removing directory: {terraform_dir}")
        try:
            # onerror is required to handle read-only files in the cache
            shutil.rmtree(terraform_dir, onerror=force_remove_readonly)
            print("   ✅ Directory removed.")
        except OSError as e:
            print(f"   ❌ Error removing directory: {e}")
            # Fallback for extreme path lengths on some systems:
            # Rename the deep folder to a single letter to shorten path, then delete.
            # (Simplified version: just advise user if this fails)
            print("   Try running this script again or use 'rsync' deletion method.")

    # 2. Remove lock file
    lock_file = cwd / ".terraform.lock.hcl"
    if lock_file.exists():
        print(f"   Removing file: {lock_file}")
        try:
            lock_file.unlink()
            print("   ✅ Lock file removed.")
        except OSError as e:
            print(f"   ❌ Error removing lock file: {e}")

    print("✨ Cleanup complete. Run 'terraform init' only AFTER fixing the recursion.")


if __name__ == "__main__":
    clean_terraform_cache()
