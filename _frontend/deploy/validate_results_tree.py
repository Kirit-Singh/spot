#!/usr/bin/env python3
"""Content-address validator for the OPTIONAL downstream results/ staging tree.

Given a results root, verifies that results/current.json (schema spot.ui_results_current.v1) carries a
complete inventory[] (path + sha256) that content-addresses EVERY file under the tree, that no file is
unlisted or missing, that no path escapes into data/ or outside the tree, and that every route's
manifest_path is inventoried. FAIL-CLOSED: any violation prints a single `ERR <reason>` line; a valid
tree prints `OK` followed by one `FILE <relpath>` line per served result file (sorted). It always exits
0 so the caller inspects the verdict (never a silent partial pass). It re-hashes bytes; it trusts nothing.
"""
import hashlib
import json
import os
import sys


def die(msg: str) -> None:
    print('ERR ' + msg)
    sys.exit(0)


def main() -> None:
    if len(sys.argv) != 2:
        die('usage: validate_results_tree.py <results_root>')
    root = sys.argv[1]
    if not os.path.isdir(root):
        die('results root is not a directory: %s' % root)
    cur_path = os.path.join(root, 'current.json')
    if not os.path.isfile(cur_path):
        die('missing results/current.json (content-address pointer)')
    try:
        with open(cur_path) as fh:
            cur = json.load(fh)
    except Exception as exc:  # noqa: BLE001 — any parse failure is a refusal
        die('current.json is not valid JSON: %s' % exc)

    if cur.get('schema') != 'spot.ui_results_current.v1':
        die('current.json schema != spot.ui_results_current.v1')

    inv = cur.get('inventory')
    if not isinstance(inv, list) or not inv:
        die('current.json carries no inventory[] (must content-address every result file)')

    listed = {}
    for i, entry in enumerate(inv):
        if not isinstance(entry, dict) or 'path' not in entry or 'sha256' not in entry:
            die('inventory[%d] must have path + sha256' % i)
        path, sha = entry['path'], entry['sha256']
        if path == 'current.json' or path == 'data' or path.startswith('data/') \
                or path.startswith('/') or '..' in path.split('/'):
            die('illegal inventory path: %s' % path)
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in '0123456789abcdef' for c in sha):
            die('inventory[%d] sha256 must be 64-hex: %s' % (i, sha))
        listed[path] = sha

    ondisk = []
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            rel = os.path.relpath(os.path.join(dirpath, fname), root)
            if rel == 'current.json':
                continue
            ondisk.append(rel)
            if rel not in listed:
                die('unlisted result file (not in current.json inventory): %s' % rel)
            with open(os.path.join(root, rel), 'rb') as fh:
                got = hashlib.sha256(fh.read()).hexdigest()
            if got != listed[rel]:
                die('content-address mismatch %s: on-disk %s != inventory %s' % (rel, got, listed[rel]))

    for path in listed:
        if not os.path.isfile(os.path.join(root, path)):
            die('inventory lists a missing file (partial tree): %s' % path)

    for route_key, entry in (cur.get('routes') or {}).items():
        manifest_path = (entry or {}).get('manifest_path')
        if manifest_path not in listed:
            die('route %s manifest_path not in inventory: %s' % (route_key, manifest_path))

    print('OK')
    for rel in sorted(ondisk):
        print('FILE ' + rel)


if __name__ == '__main__':
    main()
