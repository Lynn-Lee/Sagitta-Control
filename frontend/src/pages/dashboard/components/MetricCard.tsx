import { Card, Space, Typography } from 'antd'

import {
  DASHBOARD_CARD_STYLE,
  DASHBOARD_METRIC_CARD_BODY_STYLE,
} from '../helpers'
import type { DashboardStatCard } from '../types'

const { Text } = Typography

export default function MetricCard({ title, value, icon, color }: DashboardStatCard) {
  return (
    <Card
      hoverable
      style={DASHBOARD_CARD_STYLE}
      styles={{ body: DASHBOARD_METRIC_CARD_BODY_STYLE }}
    >
      <Space align="start" size={10} style={{ width: '100%' }}>
        <span
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: `${color}14`,
            color,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 16,
            flex: '0 0 30px',
          }}
        >
          {icon}
        </span>
        <span style={{ minWidth: 0, flex: 1 }}>
          <Text
            type="secondary"
            style={{
              display: 'block',
              fontSize: 12,
              lineHeight: '18px',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {title}
          </Text>
          <Text
            strong
            style={{
              display: 'block',
              color,
              fontSize: 24,
              lineHeight: '30px',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {Number(value || 0).toLocaleString('zh-CN')}
          </Text>
        </span>
      </Space>
    </Card>
  )
}
