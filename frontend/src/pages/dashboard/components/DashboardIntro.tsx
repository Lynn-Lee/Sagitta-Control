import type { ReactNode } from 'react'

import { Typography } from 'antd'

import { CHART_COLORS } from '../helpers'

const { Text } = Typography

export default function DashboardIntro({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        marginBottom: 14,
        padding: '10px 12px',
        borderRadius: 10,
        border: '1px solid rgba(22,93,255,0.12)',
        background: 'rgba(22,93,255,0.035)',
        borderLeft: `3px solid ${CHART_COLORS.primary}`,
      }}
    >
      <Text type="secondary" style={{ lineHeight: '22px' }}>
        {children}
      </Text>
    </div>
  )
}
