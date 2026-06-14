import type { ReactNode } from 'react'
import { Empty, Space, Typography } from 'antd'

const { Text } = Typography

type TableEmptyStateProps = {
  title?: string
  description?: ReactNode
  action?: ReactNode
  tone?: 'default' | 'filter' | 'permission' | 'setup'
}

export default function TableEmptyState({
  title = '暂无数据',
  description,
  action,
  tone = 'default',
}: TableEmptyStateProps) {
  const hint = description || {
    default: '当前范围内还没有可展示的记录。',
    filter: '可以调整筛选条件或刷新后再试。',
    permission: '当前账号暂未获得该数据范围的访问权限。',
    setup: '完成基础配置后，这里会展示对应数据。',
  }[tone]

  return (
    <div className="sagitta-table-empty">
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={(
          <Space direction="vertical" size={4}>
            <Text strong className="sagitta-table-empty__title">{title}</Text>
            {hint ? <Text type="secondary" className="sagitta-table-empty__description">{hint}</Text> : null}
            {action ? <div className="sagitta-table-empty__action">{action}</div> : null}
          </Space>
        )}
      />
    </div>
  )
}
