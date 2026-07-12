// 工单状态码 → antd Tag 颜色的单一事实源。
// 收敛自 WorkflowList 与 WorkflowDetail 此前逐字节相同的内联映射。
export const STATUS_COLOR: Record<number, string> = {
  0: 'processing', 1: 'error', 2: 'success', 3: 'warning',
  4: 'default', 5: 'processing', 6: 'success', 7: 'error', 8: 'default',
}
