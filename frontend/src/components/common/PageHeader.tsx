import type { ReactNode } from 'react'
import { Grid, Space, Typography } from 'antd'

const { Title, Text } = Typography
const { useBreakpoint } = Grid

type PageHeaderProps = {
  title: ReactNode
  meta?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  marginBottom?: number
}

export default function PageHeader({
  title,
  meta,
  description,
  actions,
  marginBottom = 16,
}: PageHeaderProps) {
  const screens = useBreakpoint()
  const isMobile = !screens.md

  return (
    <div
      className="sagitta-page-header"
      style={{
        marginBottom,
      }}
    >
      <div className="sagitta-page-header__main">
        <Space align="center" size={8} wrap>
          {typeof title === 'string'
            ? <Title level={2} className="sagitta-page-header__title">{title}</Title>
            : title}
          {meta ? (
            typeof meta === 'string'
              ? <Text className="sagitta-page-header__meta">{meta}</Text>
              : meta
          ) : null}
        </Space>
        {description ? (
          typeof description === 'string'
            ? <Text className="sagitta-page-header__description">{description}</Text>
            : description
        ) : null}
      </div>
      {actions ? (
        <div className="sagitta-page-header__actions" style={isMobile ? { width: '100%' } : undefined}>
          {actions}
        </div>
      ) : null}
    </div>
  )
}
