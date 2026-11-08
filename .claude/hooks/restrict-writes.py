#!/usr/bin/env python3
"""PreToolUse guard for Write/Edit: allow only paths matching the given patterns.

Usage: restrict-writes.py <glob> [<glob> ...]   (globs relative to the repo root)
Reads the hook JSON on stdin; exits 2 (block) when file_path is outside the allowlist.
"""
import fnmatch
import json
import os
import sys

root = os.path.realpath(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
data = json.load(sys.stdin)
path = (data.get("tool_input") or {}).get("file_path")
if not path:
    sys.exit(0)

rel = os.path.relpath(os.path.realpath(os.path.join(root, path)), root)
if not rel.startswith("..") and any(fnmatch.fnmatch(rel, g) for g in sys.argv[1:]):
    sys.exit(0)

print(f"Blocked: {rel} is outside this agent's write scope ({', '.join(sys.argv[1:])}).", file=sys.stderr)
sys.exit(2)
