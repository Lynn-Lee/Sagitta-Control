import { useState } from 'react'
import {
  Alert, Button, Card, Col, Form, Input, Row, Select,
  Space, Tabs, Tag, Timeline, Typography, message,
} from 'antd'
import {
  BugOutlined, CodeOutlined, FileTextOutlined,
  RollbackOutlined, ToolOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation } from '@tanstack/react-query'
import { instanceApi } from '@/api/instance'
import apiClient from '@/api/client'
import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import SectionLoading from '@/components/common/SectionLoading'
import { formatDbTypeLabel } from '@/utils/dbType'

const { Text, Paragraph } = Typography
const { Option } = Select
const { TextArea } = Input

const STRATEGY_COLORS: Record<string, string> = {
  binlog: 'blue', wal: 'geekblue', logminer: 'purple',
  transaction_log: 'cyan', oplog: 'green',
  aof: 'orange', snapshot: 'gold', unsupported: 'default',
}

export default function BinlogPage() {
  const [reverseForm] = Form.useForm()
  const [my2sqlForm] = Form.useForm()
  const [reverseResult, setReverseResult] = useState<any>(null)
  const [my2sqlResult, setMy2sqlResult] = useState<any>(null)
  const [selectedDbType, setSelectedDbType] = useState('mysql')
  const [msgApi, msgCtx] = message.useMessage()

  const { data: instances } = useQuery({
    queryKey: ['instances-for-binlog'],
    queryFn: () => instanceApi.list({ page_size: 200 }),
  })

  const { data: allGuides } = useQuery({
    queryKey: ['rollback-guides'],
    queryFn: () => apiClient.get('/rollback/guide/all/').then(r => r.data),
  })

  const { data: dbGuide } = useQuery({
    queryKey: ['rollback-guide', selectedDbType],
    queryFn: () => apiClient.get(`/rollback/guide/?db_type=${selectedDbType}`).then(r => r.data),
    enabled: !!selectedDbType,
  })

  const reverseMut = useMutation({
    mutationFn: (data: any) => apiClient.post('/rollback/reverse-sql/', data).then(r => r.data),
    onSuccess: (res) => { setReverseResult(res); msgApi.success('逆向 SQL 生成完成') },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || '生成失败'),
  })

  const my2sqlMut = useMutation({
    mutationFn: (data: any) => apiClient.post('/rollback/my2sql/command/', data).then(r => r.data),
    onSuccess: (res) => { setMy2sqlResult(res) },
    onError: (e: any) => msgApi.error(e.response?.data?.detail || '生成失败'),
  })

  const tabItems = [
    // Tab 1: 逆向 SQL 生成
    {
      key: 'reverse',
      label: <Space><CodeOutlined />逆向 SQL 生成</Space>,
      children: (
        <div>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="基于 sqlglot 解析工单 SQL，生成逆向操作模板。适用于所有数据库。"
            description="注意：DELETE 的逆向需要原始数据，UPDATE 的逆向需要原始字段值，生成的是操作模板供参考。" />

          <Form form={reverseForm} layout="vertical">
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="db_type" label="数据库类型"
                  rules={[{ required: true }]} initialValue="mysql">
                  <Select>
                    {['mysql', 'tidb', 'pgsql', 'oracle', 'mssql', 'clickhouse', 'doris'].map(t => (
                      <Option key={t} value={t}>{formatDbTypeLabel(t)}</Option>
                    ))}
                  </Select>
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="table_name" label="表名（可选）">
                  <Input placeholder="如：orders" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="primary_keys" label="主键字段（可选）">
                  <Select mode="tags" placeholder="如：id（回车确认）" />
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="sql" label="原始 SQL" rules={[{ required: true }]}>
              <TextArea rows={5} placeholder={
                `DELETE FROM orders WHERE created_at < '2024-01-01';\n` +
                `UPDATE users SET status=0 WHERE last_login < '2023-01-01';\n` +
                `INSERT INTO log_archive SELECT * FROM logs WHERE id < 1000;`
              } style={{ fontFamily: 'monospace', fontSize: 13 }} />
            </Form.Item>
            <Button type="primary" icon={<RollbackOutlined />}
              loading={reverseMut.isPending}
              onClick={() => reverseForm.validateFields().then(v => reverseMut.mutate(v))}>
              生成逆向 SQL
            </Button>
          </Form>

          {reverseResult && (
            <div style={{ marginTop: 24 }}>
              <Text strong>生成结果（{reverseResult.total} 条语句）：</Text>
              {reverseResult.warnings?.length > 0 && (
                <Alert type="warning" showIcon style={{ marginTop: 8, marginBottom: 8 }}
                  message={reverseResult.warnings.join('；')} />
              )}
              {reverseResult.reverse_sqls?.map((item: any, i: number) => (
                <Card key={i} size="small" style={{ marginTop: 12, borderRadius: 8 }}
                  title={<Space>
                    <Tag color="blue">{item.type}</Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>{item.note}</Text>
                  </Space>}>
                  <div style={{ marginBottom: 8 }}>
                    <Text type="secondary" style={{ fontSize: 11 }}>原始 SQL：</Text>
                    <pre style={{ background: '#f5f5f7', padding: 8, borderRadius: 4,
                      fontSize: 12, fontFamily: 'monospace', margin: '4px 0',
                      overflowX: 'auto' }}>{item.original}</pre>
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>逆向操作：</Text>
                    <pre style={{ background: '#1e1e1e', color: '#9cdcfe', padding: 12,
                      borderRadius: 4, fontSize: 12, fontFamily: 'monospace',
                      margin: '4px 0', overflowX: 'auto',
                      whiteSpace: 'pre-wrap' }}>{item.reverse}</pre>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      ),
    },

    // Tab 2: MySQL my2sql 命令生成
    {
      key: 'my2sql',
      label: <Space><ToolOutlined />my2sql 命令（MySQL/TiDB）</Space>,
      children: (
        <div>
          <Alert type="info" showIcon style={{ marginBottom: 16 }}
            message="my2sql 是基于 MySQL Binlog 的回滚工具，生成精确的逆向 SQL。"
            description={
              <span>需要在 MySQL 服务器上安装：
                <a href="https://github.com/liuhr/my2sql" target="_blank" rel="noreferrer">
                  {' '}https://github.com/liuhr/my2sql
                </a>
              </span>
            } />

          <Form form={my2sqlForm} layout="vertical">
            <Form.Item name="instance_id" label="MySQL/TiDB 实例" rules={[{ required: true }]}>
              <Select placeholder="选择实例" showSearch optionFilterProp="label">
                {instances?.items
                  ?.filter((i: any) => ['mysql', 'tidb'].includes(i.db_type))
                  .map((i: any) => (
                    <Option key={i.id} value={i.id} label={i.instance_name}>
                      <Tag color="blue">{formatDbTypeLabel(i.db_type)}</Tag> {i.instance_name}
                    </Option>
                  ))}
              </Select>
            </Form.Item>
            <Row gutter={12}>
              <Col span={12}>
                <Form.Item name="start_time" label="开始时间" rules={[{ required: true }]}>
                  <Input placeholder="如：2026-03-24 00:00:00" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item name="stop_time" label="结束时间" rules={[{ required: true }]}>
                  <Input placeholder="如：2026-03-24 23:59:59" />
                </Form.Item>
              </Col>
            </Row>
            <Row gutter={12}>
              <Col span={8}>
                <Form.Item name="databases" label="过滤数据库（可选）">
                  <Input placeholder="如：mydb" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="tables" label="过滤表名（可选）">
                  <Input placeholder="如：orders" />
                </Form.Item>
              </Col>
              <Col span={8}>
                <Form.Item name="sql_types" label="SQL 类型" initialValue="insert,update,delete">
                  <Select mode="multiple" defaultValue={['insert', 'update', 'delete']}>
                    <Option value="insert">INSERT</Option>
                    <Option value="update">UPDATE</Option>
                    <Option value="delete">DELETE</Option>
                  </Select>
                </Form.Item>
              </Col>
            </Row>
            <Form.Item name="output_dir" label="输出目录" initialValue="/tmp/rollback">
              <Input placeholder="/tmp/rollback" />
            </Form.Item>
            <Button type="primary" icon={<FileTextOutlined />}
              loading={my2sqlMut.isPending}
              onClick={() => my2sqlForm.validateFields().then(v => my2sqlMut.mutate(v))}>
              生成 my2sql 命令
            </Button>
          </Form>

          {my2sqlResult && (
            <div style={{ marginTop: 24 }}>
              {my2sqlResult.success === false ? (
                <Alert type="error" message={my2sqlResult.msg} />
              ) : (
                <>
                  <Text strong>执行步骤：</Text>
                  <Timeline style={{ marginTop: 16 }}
                    items={my2sqlResult.steps?.map((s: string, i: number) => ({
                      children: (
                        <pre style={{
                          background: i === 1 ? '#1e1e1e' : '#f5f5f7',
                          color: i === 1 ? '#9cdcfe' : '#333',
                          padding: 12, borderRadius: 6,
                          fontSize: 12, fontFamily: 'monospace',
                          whiteSpace: 'pre-wrap', margin: 0,
                        }}>{s}</pre>
                      ),
                    }))}
                  />
                  {my2sqlResult.note && (
                    <Alert type="warning" showIcon message={my2sqlResult.note}
                      style={{ marginTop: 8 }} />
                  )}
                </>
              )}
            </div>
          )}
        </div>
      ),
    },

    // Tab 3: 各数据库回滚方案说明
    {
      key: 'guide',
      label: <Space><BugOutlined />各数据库回滚方案</Space>,
      children: (
        <div>
          <Row gutter={16}>
            <Col span={8}>
              <Text strong>选择数据库类型：</Text>
              <Select style={{ width: '100%', marginTop: 8 }}
                value={selectedDbType} onChange={setSelectedDbType}>
                {allGuides && Object.keys(allGuides.guides).map(db => (
                  <Option key={db} value={db}>
                    <Tag color={STRATEGY_COLORS[allGuides.guides[db].strategy] || 'default'}>
                      {allGuides.guides[db].strategy}
                    </Tag>
                    {formatDbTypeLabel(db)}
                  </Option>
                ))}
              </Select>

              {allGuides && (
                <div style={{ marginTop: 16 }}>
                  <Text strong>全部数据库一览：</Text>
                  {Object.entries(allGuides.guides).map(([db, info]: any) => (
                    <div key={db} style={{
                      padding: '6px 0', borderBottom: '1px solid #f0f0f0',
                      cursor: 'pointer',
                    }} onClick={() => setSelectedDbType(db)}>
                      <Space>
                        <Tag color={STRATEGY_COLORS[info.strategy] || 'default'}
                          style={{ fontSize: 10 }}>{info.strategy}</Tag>
                        <Text style={{ fontSize: 13 }}>{formatDbTypeLabel(db)}</Text>
                      </Space>
                    </div>
                  ))}
                </div>
              )}
            </Col>
            <Col span={16}>
              {dbGuide && (
                <Card title={`${formatDbTypeLabel(selectedDbType)} 回滚方案`}
                  style={{ borderRadius: 8 }}>
                  <Space direction="vertical" style={{ width: '100%' }}>
                    <div>
                      <Text type="secondary">推荐工具：</Text>
                      <Tag color="blue" style={{ marginLeft: 8 }}>{dbGuide.tool || '无'}</Tag>
                    </div>
                    <Alert type="info" showIcon message={dbGuide.desc} />
                    {dbGuide.install && (
                      <div>
                        <Text type="secondary">安装/参考：</Text>
                        <Paragraph copyable style={{ marginTop: 4 }}>
                          {dbGuide.install}
                        </Paragraph>
                      </div>
                    )}
                    {dbGuide.strategy === 'binlog' && (
                      <Button type="primary" size="small"
                        onClick={() => {
                          // 切换到 my2sql tab
                          document.querySelector('[data-node-key="my2sql"]')?.dispatchEvent(
                            new MouseEvent('click', { bubbles: true })
                          )
                        }}>
                        使用 my2sql 命令生成器 →
                      </Button>
                    )}
                    {dbGuide.strategy === 'wal' && (
                      <Button size="small" onClick={() =>
                        apiClient.get('/rollback/pg-wal/').then(r => {
                          setReverseResult({ reverse_sqls: r.data.steps?.map((s: string, i: number) => ({
                            type: `步骤 ${i+1}`, original: '', reverse: s, note: r.data.note || ''
                          })), total: r.data.steps?.length || 0, warnings: [r.data.prereq || ''] })
                        })
                      }>查看 WAL 查询语句 →</Button>
                    )}
                  </Space>
                </Card>
              )}
              {!dbGuide && <SectionLoading text="加载回滚方案中..." compact />}
            </Col>
          </Row>
        </div>
      ),
    },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="SQL 回滚辅助"
        meta="基于 sqlglot 生成逆向 SQL 模板，MySQL/TiDB 支持 my2sql Binlog 回滚命令生成"
        marginBottom={20}
      />
      <SectionCard marginBottom={0}>
        <Tabs items={tabItems} defaultActiveKey="reverse" />
      </SectionCard>
    </div>
  )
}
