#!/bin/sh
# Version: 1.0.0 | 2026-07-10
# Wrapper script for Citizen Desktop AppImage — works around Chromium SUID sandbox
# issue in read-only squashfs filesystems.
SELF="$(readlink -f "$0")"
HERE="$(dirname "$SELF")"
exec "$HERE/citizen-desktop" --no-sandbox "$@"
