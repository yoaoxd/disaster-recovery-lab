#!/usr/bin/env python3
"""Compatibility entry point; install the package to use the dr-lab command."""
from disaster_recovery_lab import check_archive, digest, main, metrics, positive

if __name__ == '__main__':
    raise SystemExit(main())
