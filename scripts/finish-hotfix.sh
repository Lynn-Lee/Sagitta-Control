#!/usr/bin/env bash

set -Eeuo pipefail

version="${1:-}"

usage() {
  cat <<'EOF'
用法：
  bash scripts/finish-hotfix.sh <major.minor.patch>

该脚本会把 hotfix/<major.minor.patch> 快进合并到 release/<major.minor>，
然后把 hotfix 提交 cherry-pick 回 main。
EOF
}

[[ -n "${version}" ]] || { usage; exit 1; }
[[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "版本号格式应类似 2.0.0"; exit 1; }

minor="$(printf '%s' "${version}" | awk -F. '{print $1 "." $2}')"
release_branch="release/${minor}"
hotfix_branch="hotfix/${version}"
tag="v${version}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "当前跟踪文件存在本地改动。完成 ${hotfix_branch} 前请先提交或暂存。"
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
已完成 ${hotfix_branch}。

请检查结果，然后推送：
  git push origin ${release_branch}
  git push origin main
  git push origin ${tag}
EOF
