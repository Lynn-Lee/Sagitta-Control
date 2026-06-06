import { Alert, Button, Card, Descriptions, Progress, Space, Table, Tag, Typography } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'

import type { OptimizeAnalyzeResponse, OptimizeFinding, OptimizeRecommendation } from '@/api/optimize'
import { formatDbTypeLabel } from '@/utils/dbType'

import { RISK_COLOR, SEVERITY_COLOR } from '../helpers'

const { Text, Paragraph } = Typography

type DiagnosisPanelProps = {
  result?: OptimizeAnalyzeResponse | null
  onCopySql?: () => void
}

const findingColumns: ColumnsType<OptimizeFinding> = [
  { title: '级别', dataIndex: 'severity', width: 92, render: (v: string) => <Tag color={SEVERITY_COLOR[v]}>{v?.toUpperCase()}</Tag> },
  { title: '问题', dataIndex: 'title', width: 170 },
  { title: '说明', dataIndex: 'detail' },
  { title: '证据', dataIndex: 'evidence', width: 180, ellipsis: true },
]

const recommendationColumns: ColumnsType<OptimizeRecommendation> = [
  { title: '优先级', dataIndex: 'priority', width: 80 },
  { title: '类型', dataIndex: 'type', width: 110, render: (v: string) => <Tag>{v}</Tag> },
  { title: '建议', dataIndex: 'title', width: 180 },
  { title: '操作', dataIndex: 'action' },
  { title: '原因', dataIndex: 'reason' },
]

export default function DiagnosisPanel({ result, onCopySql }: DiagnosisPanelProps) {
  if (!result) return null

  return (
    <Card size="small" title="诊断结果">
      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        {!result.supported && <Alert type="info" showIcon message={result.msg || '当前引擎不进入 SQL 优化主链路'} />}
        <Space align="start" size={16} wrap>
          <Progress
            type="dashboard"
            percent={result.risk_score}
            size={104}
            strokeColor={RISK_COLOR(result.risk_score)}
          />
          <Space direction="vertical" style={{ maxWidth: 620 }}>
            <Space wrap>
              <Tag color="blue">{formatDbTypeLabel(result.engine)}</Tag>
              <Tag>{result.support_level}</Tag>
              <Tag>{result.source === 'manual' ? '手工 SQL' : result.source === 'fingerprint' ? 'SQL 指纹' : 'SQL 样本'}</Tag>
            </Space>
            <Text strong>{result.summary}</Text>
            <Button
              className="sagitta-action-btn sagitta-action-btn--copy"
              icon={<CopyOutlined />}
              onClick={() => navigator.clipboard.writeText(result.sql).then(onCopySql)}
            >
              复制 SQL
            </Button>
          </Space>
        </Space>
        <Table<OptimizeFinding>
          title={() => '关键问题'}
          dataSource={(result.findings || []).map((item, i) => ({ ...item, key: `${item.code}-${i}` }))}
          columns={findingColumns}
          size="small"
          tableLayout="fixed"
          scroll={{ x: 760 }}
          pagination={false}
        />
        <Table<OptimizeRecommendation>
          title={() => '优化建议'}
          dataSource={(result.recommendations || []).map((item, i) => ({ ...item, key: `${item.priority}-${i}` }))}
          columns={recommendationColumns}
          size="small"
          tableLayout="fixed"
          scroll={{ x: 980 }}
          pagination={false}
        />
        <Descriptions size="small" bordered column={{ xs: 1, sm: 2 }}>
          <Descriptions.Item label="全表扫描">{result.plan?.summary?.full_scan ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="估算行数">{result.plan?.summary?.rows_estimate ?? 0}</Descriptions.Item>
          <Descriptions.Item label="最大成本">{result.plan?.summary?.max_cost ?? 0}</Descriptions.Item>
          <Descriptions.Item label="临时表">{result.plan?.summary?.temporary ? '是' : '否'}</Descriptions.Item>
          <Descriptions.Item label="涉及表" span={2}>
            <Space wrap size={[4, 4]}>
              {(result.metadata?.tables || []).map(table => <Tag key={table}>{table}</Tag>)}
              {!(result.metadata?.tables || []).length && <Text type="secondary">未识别到表名</Text>}
            </Space>
          </Descriptions.Item>
        </Descriptions>
        {result.raw && (
          <Paragraph code copyable style={{ whiteSpace: 'pre-wrap', maxHeight: 260, overflow: 'auto' }}>
            {JSON.stringify(result.raw, null, 2)}
          </Paragraph>
        )}
      </Space>
    </Card>
  )
}
