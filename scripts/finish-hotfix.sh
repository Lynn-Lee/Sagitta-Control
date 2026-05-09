#!/usr/bin/env bash

set -Eeuo pipefail

version="${1:-}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/finish-hotfix.sh <major.minor.patch>

This fast-forwards release/<major.minor> from hotfix/<major.minor.patch>,
then cherry-picks the hotfix commits back to main.
EOF
}

[[ -n "${version}" ]] || { usage; exit 1; }
[[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Version must look like 1.0.5"; exit 1; }

minor="$(printf '%s' "${version}" | awk -F. '{print $1 "." $2}')"
release_branch="release/${minor}"
hotfix_branch="hotfix/${version}"
tag="v${version}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Tracked files have local changes. Commit or stash them before finishing ${hotfix_branch}."
  exit 1
fi

git fetch origin --tags

hotfix_base="$(git merge-base "${release_branch}" "${hotfix_branch}")"
hotfix_tip="$(git rev-parse "${hotfix_branch}")"

git switch "${release_branch}"
git merge --ff-only "${hotfix_branch}"
git tag -f "${tag}" "${hotfix_tip}"

git switch main
git merge --ff-only origin/main 2>/dev/null || true
git cherry-pick "${hotfix_base}..${hotfix_tip}"

cat <<EOF
Finished ${hotfix_branch}.

Review the result, then push:
  git push origin ${release_branch}
  git push origin main
  git push origin ${tag}
EOF
