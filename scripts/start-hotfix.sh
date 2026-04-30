#!/usr/bin/env bash

set -Eeuo pipefail

version="${1:-}"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/start-hotfix.sh <major.minor.patch>

Example:
  bash scripts/start-hotfix.sh 1.0.4
EOF
}

[[ -n "${version}" ]] || { usage; exit 1; }
[[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Version must look like 1.0.4"; exit 1; }

minor="$(printf '%s' "${version}" | awk -F. '{print $1 "." $2}')"
release_branch="release/${minor}"
hotfix_branch="hotfix/${version}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Tracked files have local changes. Commit or stash them before creating ${hotfix_branch}."
  exit 1
fi

git fetch origin --tags
git switch "${release_branch}"
git merge --ff-only "origin/${release_branch}" 2>/dev/null || true
git switch -c "${hotfix_branch}"

cat <<EOF
Created ${hotfix_branch} from ${release_branch}.

After the fix is committed:
  git tag v${version}
  git push -u origin ${hotfix_branch}
  git push origin v${version}
EOF
