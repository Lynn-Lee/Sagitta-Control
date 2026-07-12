// 风险等级元数据的单一事实源。收敛自归档 / 工单 / 查询权限等页面此前各自内联的
// low/medium/high → 标签 + 颜色映射（以及等价的三元判断）。

export type RiskAlertType = 'success' | 'warning' | 'error' | 'info'
export type RiskMeta = { label: string; color: string; alertType: RiskAlertType }

export const RISK_LEVEL_META: Record<'low' | 'medium' | 'high', RiskMeta> = {
  low: { label: '低风险', color: 'success', alertType: 'success' },
  medium: { label: '中风险', color: 'warning', alertType: 'warning' },
  high: { label: '高风险', color: 'error', alertType: 'error' },
}

// 已知等级取标准元数据；未知 / 缺省回落到低风险——与归档、工单列表页原有
// `high ? error : medium ? warning : success` 三元判断逐分支等价。
export function resolveRiskMeta(level?: string): RiskMeta {
  return RISK_LEVEL_META[level as keyof typeof RISK_LEVEL_META] ?? RISK_LEVEL_META.low
}
