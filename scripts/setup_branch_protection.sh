#!/usr/bin/env bash
# 設定 GitHub 分支保護規則，要求所有 CI 矩陣測試通過後才能合併。
#
# 前置條件：
#   - gh CLI 已安裝並已登入（gh auth login）
#   - 執行者對目標 repo 有 admin 權限
#
# 用法：
#   bash scripts/setup_branch_protection.sh [分支名稱]
#
# 預設分支：main

set -euo pipefail

BRANCH="${1:-main}"
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || echo "")

if [ -z "$REPO" ]; then
  echo "錯誤：無法取得 repo 資訊，請確認 gh CLI 已登入且在 repo 目錄中。" >&2
  exit 1
fi

echo "設定分支保護規則：${REPO} @ ${BRANCH}"
echo ""

# 必要狀態檢查清單（與 CI workflow 中 test job 的 matrix ID 對齊）
REQUIRED_CHECKS=(
  "test-matrix-required"
)

echo "必要狀態檢查："
for check in "${REQUIRED_CHECKS[@]}"; do
  echo "  - ${check}"
done
echo ""

# 設定分支保護規則
gh api \
  --method PUT \
  "repos/${REPO}/branches/${BRANCH}/protection" \
  -f "required_status_checks[strict]=true" \
  -f "required_status_checks[contexts][]=${REQUIRED_CHECKS[0]}" \
  -f "enforce_admins[enabled]=true" \
  -f "required_pull_request_reviews[required_approving_review_count]=1" \
  -f "restrictions[users][]=" \
  -f "restrictions[teams][]=" \
  --input - <<EOF
{
  "required_status_checks": {
    "strict": true,
    "contexts": $(printf '%s\n' "${REQUIRED_CHECKS[@]}" | jq -R . | jq -s .)
  },
  "enforce_admins": {
    "enabled": true
  },
  "required_pull_request_reviews": {
    "required_approving_review_count": 1
  },
  "restrictions": {
    "users": [],
    "teams": []
  }
}
EOF

echo ""
echo "分支保護規則已設定完成。"
echo "合併前必須通過以下檢查："
for check in "${REQUIRED_CHECKS[@]}"; do
  echo "  ✓ ${check}"
done
