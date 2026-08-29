#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
vm4_host="34.42.240.99"
vm4_user="ahmad_shakeelceo"
vm4_target="${vm4_user}@${vm4_host}"
agy_binary="/home/ahmad_shakeelceo/.local/bin/agy"
agy_token="/home/ahmad_shakeelceo/.gemini/antigravity-cli/antigravity-oauth-token"

cd "${root_dir}"
PYTHONPATH=src python3 scripts/run_matrix.py \
  --cases CASE-13 \
  --trials 1,2,3 \
  --systems react,proofix \
  --backend antigravity \
  --model gemini-3.7-flash-medium

gcloud container clusters delete proofix-storage \
  --zone us-central1-a \
  --quiet
gcloud compute instances start vm-4 \
  --zone us-central1-a \
  --quiet

for _ in $(seq 1 90); do
  if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    -o ConnectTimeout=5 "${vm4_target}" true 2>/dev/null; then
    break
  fi
  sleep 10
done
ssh -o BatchMode=yes -o ConnectTimeout=5 "${vm4_target}" true

ssh "${vm4_target}" \
  'mkdir -p ~/.local/bin ~/.gemini/antigravity-cli ~/.ssh /tmp/proofix-fleet'
scp "${agy_binary}" "${vm4_target}:/home/ahmad_shakeelceo/.local/bin/agy"
scp "${agy_token}" \
  "${vm4_target}:/home/ahmad_shakeelceo/.gemini/antigravity-cli/antigravity-oauth-token"
ssh "${vm4_target}" '
  chmod 700 ~/.local/bin/agy
  chmod 600 ~/.gemini/antigravity-cli/antigravity-oauth-token
  chmod 700 ~/.ssh
  if [ ! -f ~/.ssh/id_ed25519 ]; then
    ssh-keygen -q -t ed25519 -N "" -f ~/.ssh/id_ed25519
  fi
  ssh-keygen -y -f ~/.ssh/id_ed25519 > /tmp/proofix-self.pub
  touch ~/.ssh/authorized_keys
  if ! grep -qxFf /tmp/proofix-self.pub ~/.ssh/authorized_keys; then
    sed -n "1p" /tmp/proofix-self.pub >> ~/.ssh/authorized_keys
  fi
  chmod 600 ~/.ssh/authorized_keys
  sudo cp /etc/rancher/k3s/k3s.yaml /tmp/proofix-fleet-kubeconfig
  sudo chown ahmad_shakeelceo:ahmad_shakeelceo /tmp/proofix-fleet-kubeconfig
  chmod 600 /tmp/proofix-fleet-kubeconfig
'
ssh "${vm4_target}" \
  "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new ${vm4_host} hostname"

rsync -az \
  --exclude='.git/' \
  --exclude='.venv/' \
  --exclude='artifacts/' \
  "${root_dir}/" "${vm4_target}:/tmp/proofix-fleet/"

ssh "${vm4_target}" '
  cd /tmp/proofix-fleet
  mkdir -p artifacts/shards/vm4
  nohup bash -lc "PYTHONPATH=src python3 scripts/run_matrix.py \
    --hosts 34.42.240.99 \
    --trials 1,2,3 \
    --systems react,proofix \
    --backend antigravity \
    --model gemini-3.7-flash-medium" \
    > artifacts/shards/vm4/shard.log 2>&1 < /dev/null &
  echo $! > artifacts/shards/vm4/shard.pid
  cat artifacts/shards/vm4/shard.pid
'
