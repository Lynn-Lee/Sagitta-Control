import type { CSSProperties, ReactNode } from 'react'
import { Card } from 'antd'
import type { CardProps } from 'antd'

type SectionCardProps = {
  children: ReactNode
  title?: ReactNode
  extra?: ReactNode
  marginBottom?: number
  bodyPadding?: CSSProperties['padding']
  style?: CSSProperties
  size?: 'default' | 'small'
  className?: string
  variant?: 'default' | 'tight' | 'feature'
  loading?: CardProps['loading']
}

export default function SectionCard({
  children,
  title,
  extra,
  marginBottom = 16,
  bodyPadding,
  style,
  size = 'default',
  className,
  variant = 'default',
  loading,
}: SectionCardProps) {
  return (
    <Card
      className={['sagitta-section-card', `sagitta-section-card--${variant}`, className].filter(Boolean).join(' ')}
      title={title}
      extra={extra}
      size={size}
      loading={loading}
      style={{
        marginBottom,
        ...style,
      }}
      styles={bodyPadding === undefined ? undefined : { body: { padding: bodyPadding } }}
    >
      {children}
    </Card>
  )
}
