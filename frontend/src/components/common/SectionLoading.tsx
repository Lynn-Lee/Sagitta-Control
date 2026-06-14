import { Skeleton, Space, Typography } from 'antd'

const { Text } = Typography

type SectionLoadingProps = {
  text?: string
  compact?: boolean
  variant?: 'page' | 'card' | 'table' | 'inline'
}

export default function SectionLoading({
  text = '加载中...',
  compact = false,
  variant = compact ? 'card' : 'page',
}: SectionLoadingProps) {
  const isInline = variant === 'inline'
  const rows = variant === 'table' ? 5 : compact ? 2 : 3
  const padding = {
    page: 40,
    card: 24,
    table: 16,
    inline: 8,
  }[variant]

  return (
    <div className={`sagitta-section-loading sagitta-section-loading--${variant}`} style={{ padding, textAlign: isInline ? 'left' : 'center' }}>
      <Space direction="vertical" size={isInline ? 8 : 12} style={{ width: '100%' }}>
        <Skeleton
          active
          title={false}
          paragraph={{
            rows,
            width: variant === 'table'
              ? ['98%', '94%', '96%', '88%', '92%']
              : compact || isInline
                ? ['80%', '60%']
                : ['92%', '86%', '72%'],
          }}
        />
        <Text type="secondary">{text}</Text>
      </Space>
    </div>
  )
}
