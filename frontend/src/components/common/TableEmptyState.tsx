import { Empty, Typography } from 'antd'

const { Text } = Typography

type TableEmptyStateProps = {
  title?: string
}

export default function TableEmptyState({
  title = '暂无数据',
}: TableEmptyStateProps) {
  return (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={<Text type="secondary">{title}</Text>}
    />
  )
}
