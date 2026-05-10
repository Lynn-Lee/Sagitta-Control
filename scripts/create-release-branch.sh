#!/usr/bin/env bash

set -Eeuo pipefail

version="${1:-}"
base_ref="${2:-main}"

usage() {
  cat <<'EOF'
用法：
  bash scripts/create-release-branch.sh <major.minor> [base-ref]

示例：
  bash scripts/create-release-branch.sh 1.0
  bash scripts/create-release-branch.sh 1.1 main
EOF
}

[[ -n "${version}" ]] || { usage; exit 1; }
[[ "${version}" =~ ^[0-9]+\.[0-9]+$ ]] || { echo "版本号格式应类似 2.0"; exit 1; }

branch="release/${version}"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "已跟踪文件存在本地改动，请先提交或暂存后再创建 ${branch}。"
  exit 1
fi

git fetch origin --tags
git switch "${base_ref}"
git merge --ff-only "origin/${base_ref}" 2>/dev/null || true
git switch -c "${branch}"

cat <<EOF
已创建 ${branch}。

下一步：
  git push -u origin ${branch}
  git tag v${version}.0
  git push origin v${version}.0
EOF
