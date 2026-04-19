import type { CSSProperties, ReactNode } from 'react'
import { Card } from 'antd'

type SectionCardProps = {
  children: ReactNode
  title?: ReactNode
  extra?: ReactNode
  marginBottom?: number
  bodyPadding?: CSSProperties['padding']
  style?: CSSProperties
  size?: 'default' | 'small'
}

export default function SectionCard({
  children,
  title,
  extra,
  marginBottom = 16,
  bodyPadding,
  style,
  size = 'default',
}: SectionCardProps) {
  return (
    <Card
      title={title}
      extra={extra}
      size={size}
      style={{
        marginBottom,
        borderRadius: 12,
        border: '1px solid rgba(0,0,0,0.08)',
        ...style,
      }}
      styles={bodyPadding === undefined ? undefined : { body: { padding: bodyPadding } }}
    >
      {children}
    </Card>
  )
}
