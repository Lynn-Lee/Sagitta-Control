import type { ReactNode } from 'react'
import { Card } from 'antd'

type FilterCardProps = {
  children: ReactNode
  marginBottom?: number
}

export default function FilterCard({
  children,
  marginBottom = 12,
}: FilterCardProps) {
  return (
    <Card
      style={{
        marginBottom,
        borderRadius: 12,
        border: '1px solid rgba(0,0,0,0.08)',
      }}
      styles={{ body: { padding: '12px 16px' } }}
    >
      {children}
    </Card>
  )
}
