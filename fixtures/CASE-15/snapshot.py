#!/usr/bin/env python3
from __future__ import annotations

import argparse, hashlib, json, subprocess, sys

NAMESPACE = "proofix-case-15"
KINDS = "deployments,replicasets,pods,services,configmaps,events,serviceaccounts,roles,rolebindings"

def load() -> dict:
    raw = subprocess.check_output(["kubectl", "get", KINDS, "-n", NAMESPACE, "-o", "json"], text=True)
    payload = json.loads(raw)
    stable = []
    for item in payload["items"]:
        metadata = item.get("metadata", {})
        entry = {"apiVersion": item.get("apiVersion"), "kind": item.get("kind"),
                 "name": metadata.get("name"), "uid": metadata.get("uid"),
                 "generation": metadata.get("generation"), "spec": item.get("spec"),
                 "data": item.get("data"), "immutable": item.get("immutable")}
        if item.get("kind") == "Pod":
            entry["restartCounts"] = [s.get("restartCount") for s in item.get("status", {}).get("containerStatuses", [])]
        if item.get("kind") == "Event":
            entry["event"] = {k: item.get(k) for k in ("reason", "message", "type", "firstTimestamp", "lastTimestamp", "count")}
        stable.append(entry)
    stable.sort(key=lambda x: (str(x["kind"]), str(x["name"])))
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return {"sha256": hashlib.sha256(canonical.encode()).hexdigest(), "resources": stable}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--output"); parser.add_argument("--compare")
    args = parser.parse_args(); current = load()
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle: json.dump(current, handle, indent=2, sort_keys=True)
    if args.compare:
        with open(args.compare, encoding="utf-8") as handle: before = json.load(handle)
        if before["sha256"] != current["sha256"]:
            print(json.dumps({"passed": False, "before": before["sha256"], "after": current["sha256"]}, indent=2)); return 1
    print(json.dumps({"passed": True, "sha256": current["sha256"]}, sort_keys=True)); return 0

if __name__ == "__main__": sys.exit(main())
