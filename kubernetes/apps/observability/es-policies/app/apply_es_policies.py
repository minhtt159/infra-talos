#!/usr/bin/env python3
"""
apply_es_policies.py — idempotent replayer for the ECK Elasticsearch ILM /
index-template definitions under infrastructure/eck/elasticsearch/policy/.

It parses the same Kibana Dev Tools `.txt` blocks that check_es_policies.py lints
(<VERB> <path>\n{json}) and PUTs them to a live cluster. Designed to be run by a
Flux-triggered Job and to be SAFE TO RE-RUN ANY NUMBER OF TIMES:

  * PUT _ilm/policy / _index_template / _component_template  -> idempotent upsert.
  * PUT <index>-000001 {aliases:{...:{is_write_index:true}}}  -> the ONLY non-idempotent
    op. Guarded: we first check whether the rollover ALIAS already exists; if it does,
    the chain is already bootstrapped and we SKIP. "resource_already_exists" is treated
    as success too. So a re-run never hijacks or recreates a live write index.
  * DELETE is refused outright. The replayer never removes anything — deleting a policy
    file from git does NOT delete it from the cluster (that stays a deliberate manual op).

Scope: only `index-and-ilm*.txt` (ILM policies + index templates + bootstrap indices).
RBAC roles (policy/role/*), users (policy/user/*, SOPS-encrypted) and cluster-settings
are intentionally OUT of scope and applied separately.

Usage:
    python3 apply_es_policies.py --dir /policies --es-url https://host:9200 \
        --user elastic --password "$ES_PASSWORD" [--insecure] [--wait-healthy] [--dry-run]

Credentials may also come from env: ES_USER, ES_PASSWORD.
Exit codes: 0 = all applied/idempotent, 1 = an apply failed, 2 = usage/parse error.
"""
import argparse
import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

VERB_RE = re.compile(r"^(PUT|POST|GET|DELETE|HEAD)\s+(\S+)\s*$")


def parse_blocks(text):
    """Yield (verb, path, body_or_None) from a Kibana Dev Tools script.
    Identical block-splitting to check_es_policies.py so lint == apply input."""
    lines = text.splitlines()
    i, n = 0, len(lines)
    out = []
    while i < n:
        line = lines[i].strip()
        if not line or line.startswith("#"):
            i += 1
            continue
        m = VERB_RE.match(line)
        if not m:
            i += 1
            continue
        verb, path = m.group(1), m.group(2)
        body_lines, i = [], i + 1
        while i < n and not VERB_RE.match(lines[i].strip()):
            if not lines[i].strip().startswith("#"):
                body_lines.append(lines[i])
            i += 1
        body_txt = "\n".join(body_lines).strip()
        body = json.loads(body_txt) if body_txt else None
        out.append((verb, path, body))
    return out


class ES:
    def __init__(self, base, user, password, insecure, api_key=None):
        self.base = base.rstrip("/")
        # homelab: external ES authenticated with an API key (ESO-provided);
        # basic auth kept for parity with the upstream (aws-devops-management) script
        if api_key:
            self.auth = "ApiKey " + api_key
        else:
            self.auth = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        self.ctx = ssl._create_unverified_context() if insecure else None

    def _req(self, method, path, body=None, allow=(200, 201)):
        url = f"{self.base}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", self.auth)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()
        except urllib.error.URLError as e:
            return 0, f"connection error: {e.reason}"

    def wait_healthy(self, timeout=600):
        deadline = time.time() + timeout
        while time.time() < deadline:
            status, _ = self._req("GET", "_cluster/health?wait_for_status=yellow&timeout=20s")
            if status == 200:
                return True
            print(f"  ...waiting for cluster (status={status})", flush=True)
            time.sleep(5)
        raise SystemExit("cluster did not reach yellow in time")

    def alias_exists(self, alias):
        status, _ = self._req("GET", f"_alias/{alias}")
        return status == 200


def classify(verb, path, body):
    if verb == "DELETE":
        return "refuse"
    if verb != "PUT":
        return "skip"  # GET/HEAD/POST: read-only or out of scope, never auto-run
    if path.startswith("_ilm/policy/") or "_index_template/" in path \
            or "_component_template/" in path or path.startswith("_ingest/"):
        return "upsert"
    if body and "aliases" in body:
        return "bootstrap"
    return "skip"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="/policies")
    ap.add_argument("--es-url", default=os.environ.get("ES_URL", "https://localhost:9200"))
    ap.add_argument("--user", default=os.environ.get("ES_USER", "elastic"))
    ap.add_argument("--password", default=os.environ.get("ES_PASSWORD", ""))
    ap.add_argument("--api-key", default=os.environ.get("ES_API_KEY", ""))
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--wait-healthy", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = Path(args.dir)
    if not base.is_dir():
        print(f"error: {base} is not a directory", file=sys.stderr)
        return 2
    if not args.password and not args.api_key and not args.dry_run:
        print("error: no credentials (set ES_API_KEY / --api-key or ES_PASSWORD)", file=sys.stderr)
        return 2

    es = ES(args.es_url, args.user, args.password, args.insecure, api_key=args.api_key)
    if args.wait_healthy and not args.dry_run:
        print("Waiting for Elasticsearch health...", flush=True)
        es.wait_healthy()

    # Skip SOPS-managed *secret* files defensively — they must never be applied
    # from a plain ConfigMap (would be ciphertext) and are handled out of band.
    files = sorted(p for p in base.glob("index-and-ilm*.txt") if "secret" not in p.name)
    applied = skipped = failed = 0
    for f in files:
        try:
            blocks = parse_blocks(f.read_text())
        except json.JSONDecodeError as e:
            print(f"[PARSE-FAIL] {f.name}: {e}", flush=True)
            failed += 1
            continue
        for verb, path, body in blocks:
            action = classify(verb, path, body)
            tag = f"{f.name}: {verb} {path}"

            if action == "refuse":
                print(f"[REFUSE ] {tag}  (DELETE is never auto-applied)", flush=True)
                failed += 1
                continue
            if action == "skip":
                continue

            if action == "bootstrap" and not args.dry_run:
                aliases = list((body.get("aliases") or {}).keys())
                if aliases and all(es.alias_exists(a) for a in aliases):
                    print(f"[SKIP   ] {tag}  (alias exists -> already bootstrapped)", flush=True)
                    skipped += 1
                    continue

            if args.dry_run:
                note = "  (bootstrap: would skip if alias exists)" if action == "bootstrap" else ""
                print(f"[DRY-RUN] {action.upper()} {tag}{note}", flush=True)
                applied += 1
                continue

            status, resp = es._req("PUT", path, body)
            if status in (200, 201):
                print(f"[OK     ] {action.upper()} {tag}", flush=True)
                applied += 1
            elif action == "bootstrap" and "resource_already_exists" in resp:
                print(f"[OK     ] {tag}  (index already exists -> idempotent)", flush=True)
                skipped += 1
            else:
                print(f"[FAIL   ] {tag}  -> {status} {resp[:300]}", flush=True)
                failed += 1

    print("\n" + "=" * 70)
    print(f"files={len(files)}  applied={applied}  skipped(idempotent)={skipped}  failed={failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
