#!/usr/bin/env python3
"""Proxy fixture Git through the copied read-only policy."""

from pathlib import Path
import sys

from consumer_git_policy import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:], Path(__file__).resolve().parent))
