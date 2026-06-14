import { Empty, Typography } from 'antd'

import { DASHBOARD_CHART_HEIGHT } from '../helpers'

const { Text } = Typography

type EmptyChartProps = {
  text: string
  hint?: string
  height?: number
}

export default function EmptyChart({ text, hint, height = DASHBOARD_CHART_HEIGHT }: EmptyChartProps) {
  return (
    <div
      style={{
        height,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
        color: '#86909C',
        textAlign: 'center',
      }}
    >
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <span>
            <Text type="secondary" style={{ display: 'block' }}>
              {text}
            </Text>
            {hint ? (
              <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 4 }}>
                {hint}
              </Text>
            ) : null}
          </span>
        }
      />
    </div>
  )
}
