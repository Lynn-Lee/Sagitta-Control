import type { ReactNode } from 'react'

import { Card } from 'antd'

import {
  DASHBOARD_CARD_STYLE,
  DASHBOARD_CHART_CARD_BODY_STYLE,
} from '../helpers'

export default function ChartCard({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <Card
      title={title}
      style={DASHBOARD_CARD_STYLE}
      styles={{ body: DASHBOARD_CHART_CARD_BODY_STYLE }}
    >
      {children}
    </Card>
  )
}
