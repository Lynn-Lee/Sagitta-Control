#!/usr/bin/env bash

set -Eeuo pipefail

version="${1:-}"
base_ref="${2:-main}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/create-release-branch.sh <major.minor> [base-ref]

Examples:
  bash scripts/create-release-branch.sh 1.0
  bash scripts/create-release-branch.sh 1.1 main
EOF
}

[[ -n "${version}" ]] || { usage; exit 1; }
[[ "${version}" =~ ^[0-9]+\.[0-9]+$ ]] || { echo "版本号格式应类似 2.0"; exit 1; }

branch="release/${version}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Tracked files have local changes. Commit or stash them before creating ${branch}."
  exit 1
fi

git fetch origin --tags
git switch "${base_ref}"
git merge --ff-only "origin/${base_ref}" 2>/dev/null || true
git switch -c "${branch}"

cat <<EOF
Created ${branch}.

Next:
  git push -u origin ${branch}
  git tag v${version}.0
  git push origin v${version}.0
EOF
