import { Tag, Tooltip, Typography } from 'antd'

import { resolveRiskMeta, type RiskMeta } from '@/utils/riskLevel'

const { Text } = Typography

// 风险等级标签的共享渲染：空值显示占位符，否则渲染彩色 Tag，带摘要时包一层 Tooltip。
// 收敛自归档 / 工单 / 查询权限页此前逐字节相同的 renderRiskTag / renderRisk。
// resolve 默认按标准元数据解析（未知回落低风险）；调用方可传入自定义解析以保留各自的回落语义。
export const renderRiskTag = (
  level?: string,
  summary?: string,
  resolve: (level: string) => RiskMeta = resolveRiskMeta,
) => {
  if (!level) return <Text type="secondary">—</Text>
  const meta = resolve(level)
  const tag = <Tag color={meta.color}>{meta.label}</Tag>
  return summary ? <Tooltip title={summary}>{tag}</Tooltip> : tag
}
