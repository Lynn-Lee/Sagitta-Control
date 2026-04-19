import { Skeleton, Space, Typography } from 'antd'

const { Text } = Typography

type SectionLoadingProps = {
  text?: string
  compact?: boolean
}

export default function SectionLoading({
  text = '加载中...',
  compact = false,
}: SectionLoadingProps) {
  return (
    <div style={{ padding: compact ? 24 : 40, textAlign: 'center' }}>
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Skeleton
          active
          title={false}
          paragraph={{
            rows: compact ? 2 : 3,
            width: compact ? ['80%', '60%'] : ['92%', '86%', '72%'],
          }}
        />
        <Text type="secondary">{text}</Text>
      </Space>
    </div>
  )
}
