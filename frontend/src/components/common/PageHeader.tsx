import type { ReactNode } from 'react'
import { Grid, Space, Typography } from 'antd'

const { Title, Text } = Typography
const { useBreakpoint } = Grid

type PageHeaderProps = {
  title: ReactNode
  meta?: ReactNode
  actions?: ReactNode
  marginBottom?: number
}

export default function PageHeader({
  title,
  meta,
  actions,
  marginBottom = 16,
}: PageHeaderProps) {
  const screens = useBreakpoint()
  const isMobile = !screens.md

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: isMobile ? 'stretch' : 'center',
        flexWrap: 'wrap',
        gap: 12,
        marginBottom,
      }}
    >
      <Space align="center" size={8} wrap>
        {typeof title === 'string'
          ? <Title level={2} style={{ margin: 0 }}>{title}</Title>
          : title}
        {meta ? (
          typeof meta === 'string'
            ? <Text type="secondary" style={{ fontSize: 13 }}>{meta}</Text>
            : meta
        ) : null}
      </Space>
      {actions}
    </div>
  )
}
