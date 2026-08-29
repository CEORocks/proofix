#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-15"
observer="system:serviceaccount:${namespace}:proofix-observer"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30115}"

require_tools() {
  command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }
  command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
  kubectl version --request-timeout=10s >/dev/null
}
