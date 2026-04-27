import { Alert, Space, Tag, Typography } from 'antd'
import type { RiskPlan } from '@/api/workflow'

const { Text, Paragraph } = Typography

const LEVEL_META = {
  low: { color: 'success', label: '低风险' },
  medium: { color: 'warning', label: '中风险' },
  high: { color: 'error', label: '高风险' },
} as const

export default function RiskPlanAlert({ plan }: { plan?: RiskPlan | null }) {
  if (!plan) return null
  const meta = LEVEL_META[plan.level] || LEVEL_META.low
  const renderItems = (title: string, items: string[] = [], tone: 'risk' | 'suggestion') => {
    if (!items.length) return null
    return (
      <div style={{ marginTop: 10 }}>
        <Text strong style={{ display: 'block', marginBottom: 6, color: tone === 'risk' ? '#991b1b' : '#334155' }}>
          {title}
        </Text>
        <Space direction="vertical" size={6} style={{ width: '100%' }}>
          {items.map((item, idx) => (
            <div
              key={`${tone}-${idx}`}
              style={{
                display: 'grid',
                gridTemplateColumns: '22px minmax(0, 1fr)',
                columnGap: 8,
                alignItems: 'start',
              }}
            >
              <span
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 4,
                  textAlign: 'center',
                  lineHeight: '22px',
                  fontSize: 12,
                  fontWeight: 600,
                  color: tone === 'risk' ? '#b91c1c' : '#2563eb',
                  background: tone === 'risk' ? '#fee2e2' : '#dbeafe',
                }}
              >
                {idx + 1}
              </span>
              <Paragraph
                style={{
                  marginBottom: 0,
                  color: tone === 'risk' ? '#1f2937' : '#64748b',
                  lineHeight: 1.65,
                  wordBreak: 'break-word',
                }}
              >
                {item}
              </Paragraph>
            </div>
          ))}
        </Space>
      </div>
    )
  }
  const description = (
    <div style={{ width: '100%' }}>
      {renderItems('风险点', plan.risks, 'risk')}
      {renderItems('执行建议', plan.suggestions, 'suggestion')}
    </div>
  )
  return (
    <Alert
      showIcon
      type={plan.level === 'high' ? 'error' : plan.level === 'medium' ? 'warning' : 'info'}
      message={
        <Space align="start" size={8} style={{ width: '100%' }}>
          <Tag color={meta.color} style={{ marginInlineEnd: 0, flex: '0 0 auto' }}>{meta.label}</Tag>
          <Text strong style={{ lineHeight: 1.6 }}>{plan.summary}</Text>
        </Space>
      }
      description={description}
    />
  )
}
