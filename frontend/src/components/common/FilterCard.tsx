import type { ReactNode } from 'react'
import { Card } from 'antd'

type FilterCardProps = {
  children: ReactNode
  marginBottom?: number
  title?: ReactNode
  extra?: ReactNode
  compact?: boolean
}

export default function FilterCard({
  children,
  marginBottom = 12,
  title,
  extra,
  compact = false,
}: FilterCardProps) {
  return (
    <Card
      className={['sagitta-filter-card', compact ? 'sagitta-filter-card--compact' : ''].filter(Boolean).join(' ')}
      title={title}
      extra={extra}
      style={{
        marginBottom,
      }}
      styles={{ body: { padding: compact ? '10px 14px' : '14px 16px' } }}
    >
      {children}
    </Card>
  )
}
