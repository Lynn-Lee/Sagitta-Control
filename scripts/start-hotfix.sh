#!/usr/bin/env bash

set -Eeuo pipefail

version="${1:-}"

usage() {
  cat <<'EOF'
用法：
  bash scripts/start-hotfix.sh <major.minor.patch>

示例：
  bash scripts/start-hotfix.sh 2.0.0
EOF
}

[[ -n "${version}" ]] || { usage; exit 1; }
[[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "版本号格式应类似 2.0.0"; exit 1; }

minor="$(printf '%s' "${version}" | awk -F. '{print $1 "." $2}')"
release_branch="release/${minor}"
hotfix_branch="hotfix/${version}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "当前跟踪文件存在本地改动。创建 ${hotfix_branch} 前请先提交或暂存。"
  exit 1
fi

git fetch origin --tags
git switch "${release_branch}"
git merge --ff-only "origin/${release_branch}" 2>/dev/null || true
git switch -c "${hotfix_branch}"

cat <<EOF
已从 ${release_branch} 创建 ${hotfix_branch}。

修复提交后执行：
  git tag v${version}
  git push -u origin ${hotfix_branch}
  git push origin v${version}
EOF
