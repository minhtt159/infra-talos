#!/usr/bin/env python3
"""
es_size_cap.py — enforce a TOTAL store-size budget across the logs-* data
streams. ILM caps age (delete phase, 30d); ES has no ILM action for a total
size cap, so this deletes the globally-oldest non-write backing index until the
pool is under budget.

SAFE:
  * never deletes a write (current) backing index — a data stream must keep one.
  * deletes oldest-first (by index creation date), so freshest logs survive.
  * --dry-run prints the plan and deletes nothing.
  * if the budget can't be met without deleting a write index, it stops and
    reports (rollover is ILM's job, not ours).

Usage:
  python3 es_size_cap.py --es-url https://host --pattern 'logs-*' \
      --max-bytes 53687091200 [--dry-run]
Auth: ES_API_KEY env (ApiKey header).
Exit: 0 ok / under budget, 1 error, 2 usage.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request


class ES:
    def __init__(self, base, api_key):
        self.base = base.rstrip("/")
        self.auth = "ApiKey " + api_key
        self.ctx = None  # system CA bundle; TLS always verified

    def _req(self, method, path):
        req = urllib.request.Request(f"{self.base}/{path.lstrip('/')}", method=method)
        req.add_header("Authorization", self.auth)
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
        except urllib.error.URLError as e:
            return 0, f"connection error: {e.reason}"

    def json(self, method, path):
        status, body = self._req(method, path)
        if status not in (200, 201):
            raise SystemExit(f"{method} {path} -> {status} {body[:200]}")
        return json.loads(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--es-url", default=os.environ.get("ES_URL", "https://localhost:9200"))
    ap.add_argument("--pattern", default="logs-*")
    ap.add_argument("--max-bytes", type=int, required=True)
    ap.add_argument("--api-key", default=os.environ.get("ES_API_KEY", ""))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.api_key:
        print("error: no ES_API_KEY", file=sys.stderr)
        return 2

    es = ES(args.es_url, args.api_key)

    # write (current) backing index per data stream — never delete these
    streams = es.json("GET", f"_data_stream/{args.pattern}").get("data_streams", [])
    write_idx = set()
    for ds in streams:
        idxs = ds.get("indices", [])
        if idxs:
            write_idx.add(idxs[-1]["index_name"])

    # every backing index with byte size + creation epoch, oldest first
    cat = es.json("GET", f"_cat/indices/.ds-{args.pattern}"
                         "?format=json&bytes=b&h=index,store.size,creation.date")
    rows = [(r["index"], int(r["store.size"] or 0), int(r["creation.date"] or 0)) for r in cat]
    total = sum(sz for _, sz, _ in rows)
    print(f"pool={total} bytes  budget={args.max_bytes} bytes  indices={len(rows)}")

    if total <= args.max_bytes:
        print("under budget — nothing to do")
        return 0

    deletable = sorted((r for r in rows if r[0] not in write_idx), key=lambda r: r[2])
    for name, size, _ in deletable:
        if total <= args.max_bytes:
            break
        if args.dry_run:
            print(f"[DRY-RUN] would delete {name} ({size} bytes)")
            total -= size
            continue
        status, resp = es._req("DELETE", name)
        if status == 200:
            total -= size
            print(f"[DELETED] {name} ({size} bytes)  pool now {total}")
        else:
            print(f"[FAIL] delete {name} -> {status} {resp[:150]}")
            return 1

    if total > args.max_bytes:
        print(f"WARNING: still over budget ({total} > {args.max_bytes}) — only "
              f"write indices remain; ILM rollover must cut them first.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
