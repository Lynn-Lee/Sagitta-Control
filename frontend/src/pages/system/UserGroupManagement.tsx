import { useState } from 'react'
import {
  Button, Card, Col, Form, Input, Modal, Row, Select, Space, Switch, Table, Tag, Transfer, Typography, Upload, message, Grid,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, DownloadOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { userGroupApi, userApi, resourceGroupApi } from '@/api/system'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { Dragger } = Upload
const { useBreakpoint } = Grid

type ImportErrorRow = {
  row: number
  name: string
  error: string
  row_data?: Record<string, string>
}

type ImportResult = {
  total: number
  created: number
  updated: number
  failed: number
  import_headers?: string[]
  errors: ImportErrorRow[]
}

function extractFileName(contentDisposition?: string, fallback = 'user_groups_export.xlsx') {
  if (!contentDisposition) return fallback
  const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) return decodeURIComponent(utf8Match[1])
  const normalMatch = contentDisposition.match(/filename="?([^"]+)"?/i)
  return normalMatch?.[1] || fallback
}

function triggerDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  window.URL.revokeObjectURL(url)
}

function downloadImportErrors(errors: ImportErrorRow[], importHeaders?: string[]) {
  const headers = (importHeaders && importHeaders.length ? importHeaders : ['name']).filter(Boolean)
  const lines = [
    ['source_row', ...headers, 'import_error'],
    ...errors.map((item) => [
      String(item.row),
      ...headers.map((header) => item.row_data?.[header] || ''),
      item.error || '',
    ]),
  ]
  const csv = lines
    .map((line) => line.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  triggerDownload(
    new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' }),
    'user_groups_import_errors.csv',
  )
}

const UserGroupManagement: React.FC = () => {
  const screens = useBreakpoint()
  const isMobile = !screens.md
  const [modalOpen, setModalOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importResultOpen, setImportResultOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [leaderIds, setLeaderIds] = useState<number[]>([])
  const [parentIds, setParentIds] = useState<number[]>([])
  const [resourceGroupIds, setResourceGroupIds] = useState<number[]>([])
  const [statuses, setStatuses] = useState<boolean[]>([])
  const [page] = useState(1)
  const [pageSize] = useState(200)
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])
  const [exportScope, setExportScope] = useState<'filtered' | 'selected'>('filtered')
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [form] = Form.useForm()
  const [messageApi, contextHolder] = message.useMessage()
  const qc = useQueryClient()

  const { data: groupsData, isLoading } = useQuery({
    queryKey: ['user-groups', page, pageSize, search, leaderIds, parentIds, resourceGroupIds, statuses],
    queryFn: () => userGroupApi.list({
      page,
      page_size: pageSize,
      search: search || undefined,
      leader_ids: leaderIds.length ? leaderIds : undefined,
      parent_ids: parentIds.length ? parentIds : undefined,
      resource_group_ids: resourceGroupIds.length ? resourceGroupIds : undefined,
      statuses: statuses.length ? statuses : undefined,
    }),
  })

  const { data: usersData } = useQuery({
    queryKey: ['all-users'],
    queryFn: () => userApi.list({ page: 1, page_size: 200, is_active: true }),
  })

  const { data: rgsData } = useQuery({
    queryKey: ['all-resource-groups'],
    queryFn: () => resourceGroupApi.list({ page: 1, page_size: 200 }),
  })

  const allUsers = usersData?.items ?? []
  const allRgItems = rgsData?.items ?? []
  const allRgs = allRgItems.filter((rg: any) => rg.is_active)
  const groups = groupsData?.items ?? []

  const userTransferSource = allUsers.map((u: any) => ({
    key: String(u.id),
    title: `${u.display_name || u.username}`,
  }))

  const rgTransferSource = allRgs.map((rg: any) => ({
    key: String(rg.id),
    title: rg.group_name_cn || rg.group_name,
  }))

  const activeResourceGroupIds = new Set(allRgs.map((rg: any) => rg.id))

  const resourceGroupNameMap = new Map<number, string>(
    allRgItems.map((rg: any) => [
      rg.id,
      `${rg.group_name_cn || rg.group_name}${rg.is_active ? '' : '（已停用）'}`,
    ]),
  )

  const createMut = useMutation({
    mutationFn: (data: any) => userGroupApi.create(data),
    onSuccess: () => {
      messageApi.success('用户组创建成功')
      qc.invalidateQueries({ queryKey: ['user-groups'] })
      qc.invalidateQueries({ queryKey: ['all-user-groups'] })
      qc.invalidateQueries({ queryKey: ['all-user-groups-for-rg'] })
      setModalOpen(false)
      form.resetFields()
    },
    onError: (e: any) => messageApi.error(e.response?.data?.detail || '创建失败'),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => userGroupApi.update(id, data),
    onSuccess: () => {
      messageApi.success('用户组已更新')
      qc.invalidateQueries({ queryKey: ['user-groups'] })
      qc.invalidateQueries({ queryKey: ['all-user-groups'] })
      qc.invalidateQueries({ queryKey: ['all-user-groups-for-rg'] })
      setModalOpen(false)
      form.resetFields()
      setEditId(null)
    },
    onError: (e: any) => messageApi.error(e.response?.data?.detail || '更新失败'),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => userGroupApi.delete(id),
    onSuccess: () => {
      messageApi.success('用户组已删除')
      qc.invalidateQueries({ queryKey: ['user-groups'] })
      qc.invalidateQueries({ queryKey: ['all-user-groups'] })
      qc.invalidateQueries({ queryKey: ['all-user-groups-for-rg'] })
    },
    onError: (e: any) => messageApi.error(e.response?.data?.detail || '删除失败'),
  })

  const exportMut = useMutation({
    mutationFn: (params: {
      export_format: 'xlsx' | 'csv'
      search?: string
      group_ids?: number[]
      leader_ids?: number[]
      parent_ids?: number[]
      resource_group_ids?: number[]
      statuses?: boolean[]
    }) => userGroupApi.export(params),
    onSuccess: ({ blob, contentDisposition }, variables) => {
      triggerDownload(blob, extractFileName(contentDisposition, `user_groups_export.${variables.export_format}`))
      messageApi.success(`用户组数据已导出为 ${variables.export_format.toUpperCase()}`)
    },
    onError: (e: any) => messageApi.error(e.response?.data?.msg || '导出失败'),
  })

  const importMut = useMutation({
    mutationFn: (file: File) => userGroupApi.import(file),
    onSuccess: (resp: any) => {
      qc.invalidateQueries({ queryKey: ['user-groups'] })
      qc.invalidateQueries({ queryKey: ['all-user-groups'] })
      const data = resp?.data as ImportResult
      setImportOpen(false)
      setImportFile(null)
      setImportResult(data)
      setImportResultOpen(true)
      if (data?.failed) {
        const firstError = data.errors?.[0]?.error ? `，首条错误：${data.errors[0].error}` : ''
        messageApi.warning(`导入完成：新增 ${data.created}，更新 ${data.updated}，失败 ${data.failed}${firstError}`)
      } else {
        messageApi.success(`导入完成：新增 ${data?.created ?? 0}，更新 ${data?.updated ?? 0}`)
      }
    },
    onError: (e: any) => messageApi.error(e.response?.data?.msg || '导入失败'),
  })

  const openCreate = () => {
    setEditId(null)
    form.resetFields()
    form.setFieldsValue({
      member_ids: [],
      resource_group_ids: [],
    })
    setModalOpen(true)
  }

  const openEdit = async (id: number) => {
    setEditId(id)
    const group = await userGroupApi.get(id)
    form.setFieldsValue({
      name_cn: group.name_cn,
      description: group.description,
      leader_id: group.leader_id,
      parent_id: group.parent_id,
      is_active: group.is_active,
      member_ids: (group.member_ids ?? []).map(String),
      resource_group_ids: (group.resource_group_ids ?? [])
        .filter((resourceGroupId: number) => activeResourceGroupIds.has(resourceGroupId))
        .map(String),
    })
    setModalOpen(true)
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    const member_ids = (values.member_ids ?? []).map(Number)
    const resource_group_ids = (values.resource_group_ids ?? []).map(Number)
    const payload = { ...values, member_ids, resource_group_ids }
    if (editId) {
      updateMut.mutate({ id: editId, data: payload })
    } else {
      createMut.mutate(payload)
    }
  }

  const openImport = () => {
    setImportFile(null)
    setImportOpen(true)
  }

  const handleImport = () => {
    if (!importFile) {
      messageApi.warning('请先选择要导入的 Excel 或 CSV 文件')
      return
    }
    importMut.mutate(importFile)
  }

  const handleDownloadTemplate = async (exportFormat: 'xlsx' | 'csv') => {
    try {
      const { blob, contentDisposition } = await userGroupApi.downloadTemplate({ export_format: exportFormat })
      triggerDownload(blob, extractFileName(contentDisposition, `user_groups_import_template.${exportFormat}`))
      messageApi.success(`模板已下载为 ${exportFormat.toUpperCase()}`)
    } catch (e: any) {
      messageApi.error(e.response?.data?.msg || '模板下载失败')
    }
  }

  const handleExport = (exportFormat: 'xlsx' | 'csv') => {
    if (exportScope === 'selected' && !selectedRowKeys.length) {
      messageApi.warning('当前导出范围为“勾选结果”，请先勾选要导出的用户组')
      return
    }
    exportMut.mutate({
      export_format: exportFormat,
      search: exportScope === 'filtered' ? search || undefined : undefined,
      group_ids: exportScope === 'selected' ? selectedRowKeys : undefined,
      leader_ids: exportScope === 'filtered' && leaderIds.length ? leaderIds : undefined,
      parent_ids: exportScope === 'filtered' && parentIds.length ? parentIds : undefined,
      resource_group_ids: exportScope === 'filtered' && resourceGroupIds.length ? resourceGroupIds : undefined,
      statuses: exportScope === 'filtered' && statuses.length ? statuses : undefined,
    })
  }

  const handleFilterChange = <T,>(setter: (value: T) => void, value: T) => {
    setSelectedRowKeys([])
    setter(value)
  }

  const resetFilters = () => {
    setSelectedRowKeys([])
    setSearch('')
    setLeaderIds([])
    setParentIds([])
    setResourceGroupIds([])
    setStatuses([])
  }

  const leaderOptions = allUsers.map((u: any) => ({
    value: u.id, label: `${u.display_name || u.username} (${u.username})`,
  }))

  const parentOptions = groups
    .filter((g: any) => g.id !== editId)
    .map((g: any) => ({
      value: g.id, label: g.name_cn || g.name,
    }))

  const statusOptions = [
    { value: true, label: '启用' },
    { value: false, label: '停用' },
  ]

  const userNameMap = new Map<number, string>(
    allUsers.map((u: any) => [u.id, u.display_name || u.username]),
  )

  const groupNameMap = new Map<number, string>(
    groups.map((g: any) => [g.id, g.name_cn || g.name]),
  )

  const activeFilterTags = [
    ...(search ? [{ key: `search:${search}`, label: `关键词：${search}`, onClose: () => setSearch('') }] : []),
    ...leaderIds.map((leaderId) => {
      const label = leaderOptions.find((item) => item.value === leaderId)?.label || String(leaderId)
      return {
        key: `leader:${leaderId}`,
        label: `组长：${label}`,
        onClose: () => handleFilterChange(setLeaderIds, leaderIds.filter((id) => id !== leaderId)),
      }
    }),
    ...parentIds.map((parentId) => {
      const label = parentOptions.find((item) => item.value === parentId)?.label || String(parentId)
      return {
        key: `parent:${parentId}`,
        label: `上级组：${label}`,
        onClose: () => handleFilterChange(setParentIds, parentIds.filter((id) => id !== parentId)),
      }
    }),
    ...resourceGroupIds.map((resourceGroupId) => {
      const label = resourceGroupNameMap.get(resourceGroupId) || String(resourceGroupId)
      return {
        key: `resource-group:${resourceGroupId}`,
        label: `资源组：${label}`,
        onClose: () => handleFilterChange(setResourceGroupIds, resourceGroupIds.filter((id) => id !== resourceGroupId)),
      }
    }),
    ...statuses.map((status) => ({
      key: `status:${status}`,
      label: `状态：${status ? '启用' : '停用'}`,
      onClose: () => handleFilterChange(setStatuses, statuses.filter((item) => item !== status)),
    })),
  ]

  const importErrorColumns: ColumnsType<ImportErrorRow> = [
    { title: '行号', dataIndex: 'row', width: 90 },
    { title: '组标识', dataIndex: 'name', width: 180, render: (value) => value || <Text type="secondary">—</Text> },
    { title: '失败原因', dataIndex: 'error' },
  ]

  const columns: ColumnsType<any> = [
    { title: 'ID', dataIndex: 'id', width: 70 },
    { title: '组标识', dataIndex: 'name', width: 140, ellipsis: true },
    { title: '中文名', dataIndex: 'name_cn', width: 140, ellipsis: true },
    {
      title: '组长',
      dataIndex: 'leader_id',
      width: 130,
      render: (leaderId: number | null | undefined) =>
        leaderId ? userNameMap.get(leaderId) || `用户#${leaderId}` : <span style={{ color: '#999' }}>未设置</span>,
    },
    {
      title: '上级组',
      dataIndex: 'parent_id',
      width: 140,
      render: (parentId: number | null | undefined) =>
        parentId ? groupNameMap.get(parentId) || `用户组#${parentId}` : <span style={{ color: '#999' }}>顶级组</span>,
    },
    { title: '描述', dataIndex: 'description', width: 220, ellipsis: true },
    { title: '成员数', dataIndex: 'member_count', width: 90 },
    {
      title: '关联资源组', dataIndex: 'resource_group_ids', width: 260,
      render: (ids: number[] = []) => {
        if (!ids.length) return <span style={{ color: '#999' }}>未关联</span>
        return (
          <Space wrap size={[4, 4]}>
            {ids.map((id) => (
              <Tag key={id}>{resourceGroupNameMap.get(id) || `资源组#${id}`}</Tag>
            ))}
          </Space>
        )
      },
    },
    {
      title: '状态', dataIndex: 'is_active', width: 80,
      render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag color="red">停用</Tag>,
    },
    {
      title: '操作', width: 140,
      render: (_: any, record: any) => (
        <Space>
          <a onClick={() => void openEdit(record.id)}>编辑</a>
          <a onClick={() => deleteMut.mutate(record.id)} style={{ color: '#ff4d4f' }}>删除</a>
        </Space>
      ),
    },
  ]

  return (
    <>
      {contextHolder}
      <PageHeader
        title="用户组管理"
        actions={(
          <Space wrap size={[8, 8]} style={isMobile ? { display: 'flex', width: '100%' } : undefined}>
            <Button
              icon={<DownloadOutlined />}
              loading={exportMut.isPending}
              onClick={() => handleExport('xlsx')}
              style={isMobile ? { flex: 1 } : undefined}
            >
              导出 Excel
            </Button>
            <Button
              icon={<DownloadOutlined />}
              loading={exportMut.isPending}
              onClick={() => handleExport('csv')}
              style={isMobile ? { flex: 1 } : undefined}
            >
              导出 CSV
            </Button>
            <Button icon={<UploadOutlined />} onClick={openImport} style={isMobile ? { flex: 1 } : undefined}>
              导入用户组
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}
              style={isMobile ? { flex: 1 } : undefined}>新建用户组</Button>
          </Space>
        )}
      />

      <FilterCard marginBottom={16}>
        <Space wrap size={[12, 12]} style={{ display: 'flex' }}>
          <Input.Search
            placeholder="搜索用户组标识或中文名"
            allowClear
            value={search}
            onSearch={setSearch}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: isMobile ? '100%' : 400, maxWidth: '100%' }}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="组长"
            style={{ width: isMobile ? '100%' : 240 }}
            options={leaderOptions}
            value={leaderIds}
            onChange={(value) => handleFilterChange(setLeaderIds, value)}
            showSearch
            optionFilterProp="label"
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="上级组"
            style={{ width: isMobile ? '100%' : 220 }}
            options={parentOptions}
            value={parentIds}
            onChange={(value) => handleFilterChange(setParentIds, value)}
            showSearch
            optionFilterProp="label"
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="关联资源组"
            style={{ width: isMobile ? '100%' : 240 }}
            options={allRgItems.map((rg: any) => ({
              value: rg.id,
              label: rg.group_name_cn || rg.group_name,
            }))}
            value={resourceGroupIds}
            onChange={(value) => handleFilterChange(setResourceGroupIds, value)}
            showSearch
            optionFilterProp="label"
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="状态"
            style={{ width: isMobile ? '100%' : 180 }}
            options={statusOptions}
            value={statuses}
            onChange={(value) => handleFilterChange(setStatuses, value)}
          />
          <Select
            style={{ width: isMobile ? '100%' : 220 }}
            options={[
              { value: 'filtered', label: '导出当前筛选结果' },
              { value: 'selected', label: `导出当前勾选结果${selectedRowKeys.length ? `（${selectedRowKeys.length}）` : ''}` },
            ]}
            value={exportScope}
            onChange={setExportScope}
          />
          <Button onClick={resetFilters} style={isMobile ? { width: '100%' } : undefined}>重置筛选</Button>
        </Space>
        <div style={{ marginTop: 12 }}>
          <Space wrap size={[8, 8]} style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: isMobile ? 'flex-start' : 'center',
          }}>
            <Space wrap size={[8, 8]}>
              {activeFilterTags.length ? (
                activeFilterTags.map((item) => (
                  <Tag
                    key={item.key}
                    closable
                    onClose={(e) => {
                      e.preventDefault()
                      item.onClose()
                    }}
                    style={{ paddingInline: 10, lineHeight: '24px' }}
                  >
                    {item.label}
                  </Tag>
                ))
              ) : (
                <Text type="secondary">当前未设置筛选条件，将展示并导出全部用户组。</Text>
              )}
            </Space>
            <Text type="secondary">
              {exportScope === 'selected'
                ? `当前导出范围：勾选结果${selectedRowKeys.length ? `（${selectedRowKeys.length} 条）` : '（未勾选）'}`
                : `当前导出范围：筛选结果（${groupsData?.total ?? 0} 条）`}
            </Text>
          </Space>
        </div>
      </FilterCard>

      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }}>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={groups}
          loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无用户组数据" /> }}
          tableLayout="fixed"
          scroll={{ x: 1180 }}
          pagination={false}
          size="middle"
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys.map((key) => Number(key))),
          }}
        />
      </Card>

      <Modal
        title={editId ? '编辑用户组' : '新建用户组'}
        open={modalOpen}
        maskClosable={false}
        onOk={() => void handleSubmit()}
        onCancel={() => { setModalOpen(false); form.resetFields(); setEditId(null) }}
        confirmLoading={createMut.isPending || updateMut.isPending}
        width={700}
      >
        <Form form={form} layout="vertical">
          {!editId && (
            <Form.Item name="name" label="组标识" rules={[{ required: true, min: 2, message: '至少2个字符' }]}>
              <Input placeholder="如 dev_team" />
            </Form.Item>
          )}
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="name_cn" label="中文名">
                <Input placeholder="如 开发组" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="leader_id" label="组长">
                <Select
                  allowClear
                  showSearch
                  optionFilterProp="label"
                  options={leaderOptions}
                  placeholder="选择组长"
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={2} placeholder="组用途说明" />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="parent_id" label="父组">
                <Select allowClear options={parentOptions} placeholder="无（顶级组）" />
              </Form.Item>
            </Col>
            <Col span={12}>
              {editId && (
                <Form.Item name="is_active" label="启用" valuePropName="checked">
                  <Switch />
                </Form.Item>
              )}
            </Col>
          </Row>

          <Form.Item
            name="member_ids"
            label="组成员"
            valuePropName="targetKeys"
            getValueFromEvent={(nextTargetKeys) => nextTargetKeys}
          >
            <Transfer
              dataSource={userTransferSource}
              render={(item) => item.title!}
              titles={['可选用户', '已选用户']}
              showSearch
              filterOption={(input, item) => (item.title ?? '').toLowerCase().includes(input.toLowerCase())}
              listStyle={{ width: 280, height: 300 }}
            />
          </Form.Item>

          <Form.Item
            name="resource_group_ids"
            label="关联资源组"
            valuePropName="targetKeys"
            getValueFromEvent={(nextTargetKeys) => nextTargetKeys}
          >
            <Transfer
              dataSource={rgTransferSource}
              render={(item) => item.title!}
              titles={['可选资源组', '已关联']}
              showSearch
              filterOption={(input, item) => (item.title ?? '').toLowerCase().includes(input.toLowerCase())}
              listStyle={{ width: 280, height: 300 }}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="批量导入用户组"
        open={importOpen}
        maskClosable={false}
        onOk={handleImport}
        onCancel={() => { setImportOpen(false); setImportFile(null) }}
        okText="开始导入"
        confirmLoading={importMut.isPending}
        width={680}
      >
        <Form layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="导入文件" required extra="支持 .xlsx 或 .csv。推荐优先下载 Excel 模板，模板内附带“字段说明”sheet，可直接查看每列填写规则和示例值。">
            <Dragger
              accept=".xlsx,.csv"
              maxCount={1}
              beforeUpload={(file) => {
                setImportFile(file)
                return false
              }}
              onRemove={() => {
                setImportFile(null)
              }}
              fileList={importFile ? [importFile as any] : []}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">点击或拖拽 Excel / CSV 文件到这里</p>
              <p className="ant-upload-hint">文件表头支持模板字段，也兼容中文列名，例如 组标识、中文名、组成员、资源组。</p>
            </Dragger>
          </Form.Item>
          <Space wrap size={12}>
            <Button
              style={{
                minWidth: 168,
                whiteSpace: 'nowrap',
                background: '#1677ff',
                borderColor: '#1677ff',
                color: '#ffffff',
              }}
              onClick={() => void handleDownloadTemplate('xlsx')}
            >
              下载 Excel 模板
            </Button>
            <Button
              style={{ minWidth: 168, whiteSpace: 'nowrap' }}
              onClick={() => void handleDownloadTemplate('csv')}
            >
              下载 CSV 模板
            </Button>
          </Space>
        </Form>
      </Modal>

      <Modal
        title="导入结果"
        open={importResultOpen}
        maskClosable={false}
        onCancel={() => setImportResultOpen(false)}
        footer={[
          importResult?.failed ? (
            <Button
              key="export-errors"
              icon={<DownloadOutlined />}
              onClick={() => downloadImportErrors(importResult.errors, importResult.import_headers)}
            >
              导出失败记录
            </Button>
          ) : null,
          <Button key="close" type="primary" onClick={() => setImportResultOpen(false)}>
            关闭
          </Button>,
        ]}
        width={760}
      >
        <Space size={12} wrap style={{ display: 'flex', marginBottom: 16 }}>
          <Card size="small" style={{ minWidth: 110 }}>
            <Text type="secondary">总行数</Text>
            <div><Text strong style={{ fontSize: 20 }}>{importResult?.total ?? 0}</Text></div>
          </Card>
          <Card size="small" style={{ minWidth: 110 }}>
            <Text type="secondary">新增</Text>
            <div><Text strong style={{ fontSize: 20, color: '#1677ff' }}>{importResult?.created ?? 0}</Text></div>
          </Card>
          <Card size="small" style={{ minWidth: 110 }}>
            <Text type="secondary">更新</Text>
            <div><Text strong style={{ fontSize: 20, color: '#52c41a' }}>{importResult?.updated ?? 0}</Text></div>
          </Card>
          <Card size="small" style={{ minWidth: 110 }}>
            <Text type="secondary">失败</Text>
            <div><Text strong style={{ fontSize: 20, color: '#ff4d4f' }}>{importResult?.failed ?? 0}</Text></div>
          </Card>
        </Space>
        {importResult?.failed ? (
          <Table
            rowKey={(record) => `${record.row}-${record.name}-${record.error}`}
            columns={importErrorColumns}
            dataSource={importResult.errors}
            pagination={{ pageSize: 8, showSizeChanger: false }}
            size="small"
            tableLayout="fixed"
            scroll={{ x: 760 }}
            locale={{ emptyText: <TableEmptyState title="本次导入没有失败记录" /> }}
          />
        ) : (
          <Text type="secondary">本次导入没有失败记录。</Text>
        )}
      </Modal>
    </>
  )
}

export default UserGroupManagement
