import { useState } from 'react'
import { Button, Card, Form, Input, Modal, Popconfirm, Select, Space, Switch, Table, Tag, Typography, Upload, message, Grid } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { PlusOutlined, EditOutlined, DeleteOutlined, DownloadOutlined, InboxOutlined, UploadOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { userApi, roleApi, userGroupApi } from '@/api/system'
import FilterCard from '@/components/common/FilterCard'
import PageHeader from '@/components/common/PageHeader'
import TableEmptyState from '@/components/common/TableEmptyState'

const { Text } = Typography
const { Dragger } = Upload
const { useBreakpoint } = Grid

type ImportErrorRow = {
  row: number
  username: string
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

const IMPORT_DEFAULT_PASSWORD = 'Sagitta@2026A'

function extractFileName(contentDisposition?: string, fallback = 'users_export.xlsx') {
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
  const headers = (importHeaders && importHeaders.length ? importHeaders : ['username']).filter(Boolean)
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
    'users_import_errors.csv',
  )
}

export default function UserManagement() {
  const passwordRules = [
    { required: true, message: '请输入密码' },
    { min: 8, message: '密码长度不能少于 8 位' },
    { pattern: /[A-Z]/, message: '密码必须包含至少 1 个大写字母' },
    { pattern: /[a-z]/, message: '密码必须包含至少 1 个小写字母' },
    { pattern: /\d/, message: '密码必须包含至少 1 个数字' },
    { pattern: /[^A-Za-z0-9]/, message: '密码必须包含至少 1 个特殊字符' },
  ]

  const qc = useQueryClient()
  const screens = useBreakpoint()
  const isMobile = !screens.lg
  const [modalOpen, setModalOpen] = useState(false)
  const [importOpen, setImportOpen] = useState(false)
  const [importResultOpen, setImportResultOpen] = useState(false)
  const [editId, setEditId] = useState<number | null>(null)
  const [search, setSearch] = useState('')
  const [roleIds, setRoleIds] = useState<number[]>([])
  const [userGroupIds, setUserGroupIds] = useState<number[]>([])
  const [departments, setDepartments] = useState<string[]>([])
  const [titles, setTitles] = useState<string[]>([])
  const [statuses, setStatuses] = useState<boolean[]>([])
  const [exportScope, setExportScope] = useState<'filtered' | 'selected'>('filtered')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [selectedRowKeys, setSelectedRowKeys] = useState<number[]>([])
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [form] = Form.useForm()
  const [importForm] = Form.useForm()
  const [msgApi, msgCtx] = message.useMessage()

  const { data, isLoading } = useQuery({
    queryKey: ['users', page, pageSize, search, roleIds, userGroupIds, departments, titles, statuses],
    queryFn: () => userApi.list({
      page,
      page_size: pageSize,
      search: search || undefined,
      role_ids: roleIds.length ? roleIds : undefined,
      user_group_ids: userGroupIds.length ? userGroupIds : undefined,
      departments: departments.length ? departments : undefined,
      titles: titles.length ? titles : undefined,
      statuses: statuses.length ? statuses : undefined,
    }),
  })

  const { data: rolesData } = useQuery({
    queryKey: ['all-roles'],
    queryFn: () => roleApi.list({ page: 1, page_size: 200 }),
  })

  const { data: allUsersForManagerData } = useQuery({
    queryKey: ['all-users-for-manager'],
    queryFn: () => userApi.list({ page: 1, page_size: 200 }),
  })

  const { data: groupsData } = useQuery({
    queryKey: ['all-user-groups'],
    queryFn: () => userGroupApi.list({ page: 1, page_size: 200 }),
  })

  const roleOptions = (rolesData?.items ?? []).map((r: any) => ({
    value: r.id, label: r.name_cn || r.name,
  }))

  const allUsersForManager = allUsersForManagerData?.items ?? []
  const managerOptions = allUsersForManager.map((u: any) => ({
    value: u.id, label: `${u.display_name || u.username} (${u.username})`,
  }))

  const groupOptions = (groupsData?.items ?? []).map((g: any) => ({
    value: g.id, label: g.name_cn || g.name,
  }))
  const departmentOptions = Array.from(
    new Set((allUsersForManagerData?.items ?? []).map((u: any) => u.department).filter(Boolean)),
  ).map((value) => ({ value, label: value }))
  const titleOptions = Array.from(
    new Set((allUsersForManagerData?.items ?? []).map((u: any) => u.title).filter(Boolean)),
  ).map((value) => ({ value, label: value }))
  const statusOptions = [
    { value: true, label: '启用' },
    { value: false, label: '停用' },
  ]

  const createMut = useMutation({
    mutationFn: userApi.create,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setModalOpen(false); msgApi.success('用户创建成功') },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '创建失败'),
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => userApi.update(id, data),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); setModalOpen(false); msgApi.success('已更新') },
  })
  const deleteMut = useMutation({
    mutationFn: userApi.delete,
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['users'] }); msgApi.success('已删除') },
  })
  const exportMut = useMutation({
    mutationFn: (params: {
      export_format: 'xlsx' | 'csv'
      search?: string
      role_ids?: number[]
      user_group_ids?: number[]
      departments?: string[]
      titles?: string[]
      statuses?: boolean[]
      user_ids?: number[]
    }) => userApi.export(params),
    onSuccess: ({ blob, contentDisposition }, variables) => {
      triggerDownload(blob, extractFileName(contentDisposition, `users_export.${variables.export_format}`))
      msgApi.success(`用户数据已导出为 ${variables.export_format.toUpperCase()}`)
    },
    onError: (e: any) => msgApi.error(e.response?.data?.msg || '导出失败'),
  })
  const importMut = useMutation({
    mutationFn: ({ file, defaultPassword }: { file: File; defaultPassword: string }) =>
      userApi.import(file, defaultPassword),
    onSuccess: (resp: any) => {
      qc.invalidateQueries({ queryKey: ['users'] })
      const data = resp?.data as ImportResult
      setImportOpen(false)
      setImportFile(null)
      importForm.resetFields()
      setImportResult(data)
      setImportResultOpen(true)
      if (data?.failed) {
        const firstError = data.errors?.[0]?.error ? `，首条错误：${data.errors[0].error}` : ''
        msgApi.warning(`导入完成：新增 ${data.created}，更新 ${data.updated}，失败 ${data.failed}${firstError}`)
      } else {
        msgApi.success(`导入完成：新增 ${data?.created ?? 0}，更新 ${data?.updated ?? 0}`)
      }
    },
    onError: (e: any) => {
      const detail = e.response?.data?.msg || e.response?.data?.detail || e.message || '导入失败'
      msgApi.error(`导入失败：${detail}`)
    },
  })

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (!values.password && editId) delete values.password
      editId ? updateMut.mutate({ id: editId, data: values }) : createMut.mutate(values)
    } catch { /* validation */ }
  }
  const openCreate = async () => {
    await qc.invalidateQueries({ queryKey: ['all-user-groups'] })
    setEditId(null)
    form.resetFields()
    setModalOpen(true)
  }
  const openEdit = (r: any) => {
    setEditId(r.id)
    form.setFieldsValue({
      ...r,
      password: '',
      role_id: r.role_id,
      manager_id: r.manager_id,
      employee_id: r.employee_id,
      department: r.department,
      title: r.title,
      user_group_ids: (r.user_groups ?? []).map((ug: any) => ug.id ?? ug),
    })
    setModalOpen(true)
  }
  const openEditWithLatestGroups = async (r: any) => {
    await qc.invalidateQueries({ queryKey: ['all-user-groups'] })
    openEdit(r)
  }
  const openImport = () => {
    setImportFile(null)
    importForm.setFieldsValue({ defaultPassword: IMPORT_DEFAULT_PASSWORD })
    setImportOpen(true)
  }
  const handleImport = async () => {
    try {
      const values = await importForm.validateFields()
      if (!importFile) {
        msgApi.warning('请先选择要导入的 Excel 或 CSV 文件')
        return
      }
      importMut.mutate({ file: importFile, defaultPassword: values.defaultPassword })
    } catch {
      // validation
    }
  }
  const handleDownloadTemplate = async (exportFormat: 'xlsx' | 'csv') => {
    try {
      const { blob, contentDisposition } = await userApi.downloadTemplate({ export_format: exportFormat })
      triggerDownload(blob, extractFileName(contentDisposition, `users_import_template.${exportFormat}`))
      msgApi.success(`模板已下载为 ${exportFormat.toUpperCase()}`)
    } catch (e: any) {
      msgApi.error(e.response?.data?.msg || '模板下载失败')
    }
  }

  const handleSearch = (value: string) => {
    setPage(1)
    setSelectedRowKeys([])
    setSearch(value)
  }
  const handleFilterChange = <T,>(setter: (value: T) => void, value: T) => {
    setPage(1)
    setSelectedRowKeys([])
    setter(value)
  }
  const resetFilters = () => {
    setPage(1)
    setSelectedRowKeys([])
    setSearch('')
    setRoleIds([])
    setUserGroupIds([])
    setDepartments([])
    setTitles([])
    setStatuses([])
  }

  const filterWidth = (desktopWidth: number) => (isMobile ? '100%' : desktopWidth)
  const handleExport = (exportFormat: 'xlsx' | 'csv') => {
    if (exportScope === 'selected' && !selectedRowKeys.length) {
      msgApi.warning('当前导出范围为“勾选结果”，请先勾选要导出的用户')
      return
    }
    exportMut.mutate({
      export_format: exportFormat,
      search: exportScope === 'filtered' ? search || undefined : undefined,
      role_ids: exportScope === 'filtered' && roleIds.length ? roleIds : undefined,
      user_group_ids: exportScope === 'filtered' && userGroupIds.length ? userGroupIds : undefined,
      departments: exportScope === 'filtered' && departments.length ? departments : undefined,
      titles: exportScope === 'filtered' && titles.length ? titles : undefined,
      statuses: exportScope === 'filtered' && statuses.length ? statuses : undefined,
      user_ids: exportScope === 'selected' ? selectedRowKeys : undefined,
    })
  }
  const activeFilterTags = [
    ...(search ? [{ key: `search:${search}`, label: `关键词：${search}`, onClose: () => handleSearch('') }] : []),
    ...roleIds.map((roleId) => {
      const label = roleOptions.find((item) => item.value === roleId)?.label || String(roleId)
      return {
        key: `role:${roleId}`,
        label: `角色：${label}`,
        onClose: () => handleFilterChange(setRoleIds, roleIds.filter((id) => id !== roleId)),
      }
    }),
    ...userGroupIds.map((groupId) => {
      const label = groupOptions.find((item) => item.value === groupId)?.label || String(groupId)
      return {
        key: `group:${groupId}`,
        label: `用户组：${label}`,
        onClose: () => handleFilterChange(setUserGroupIds, userGroupIds.filter((id) => id !== groupId)),
      }
    }),
    ...departments.map((department) => ({
      key: `department:${department}`,
      label: `部门：${department}`,
      onClose: () => handleFilterChange(setDepartments, departments.filter((item) => item !== department)),
    })),
    ...titles.map((title) => ({
      key: `title:${title}`,
      label: `职位：${title}`,
      onClose: () => handleFilterChange(setTitles, titles.filter((item) => item !== title)),
    })),
    ...statuses.map((status) => ({
      key: `status:${status}`,
      label: `状态：${status ? '启用' : '停用'}`,
      onClose: () => handleFilterChange(setStatuses, statuses.filter((item) => item !== status)),
    })),
  ]

  const importErrorColumns: ColumnsType<ImportErrorRow> = [
    { title: '行号', dataIndex: 'row', width: 90 },
    { title: '用户名', dataIndex: 'username', width: 180, render: (value) => value || <Text type="secondary">—</Text> },
    { title: '失败原因', dataIndex: 'error' },
  ]

  const columns: ColumnsType<any> = [
    {
      title: '用户名',
      dataIndex: 'username',
      width: 180,
      render: (n, r) => (
        <Space direction="vertical" size={0}>
          <Text strong>{n}</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>{r.display_name}</Text>
        </Space>
      ),
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      width: 220,
      ellipsis: { showTitle: true },
      render: v => v || <Text type="secondary">—</Text>,
    },
    {
      title: '手机号',
      dataIndex: 'phone',
      width: 140,
      render: v => v || <Text type="secondary">—</Text>,
    },
    { title: '角色', dataIndex: 'role_name', width: 120, render: (name, r) => {
      if (r.is_superuser) return <Tag color="red">超级管理员</Tag>
      return name ? <Tag color="blue">{name}</Tag> : <Tag>普通用户</Tag>
    }},
    {
      title: '直属上级',
      width: 160,
      ellipsis: { showTitle: true },
      render: (_, r) => {
        const label = r.manager_display_name || r.manager_username
        return label ? <Text>{label}</Text> : <Text type="secondary">—</Text>
      },
    },
    { title: '用户组', dataIndex: 'user_groups', width: 180, render: (ugs: any[]) => {
      if (!ugs || !ugs.length) return <Text type="secondary">—</Text>
      return <Space wrap size={[4, 4]}>{ugs.map((ug: any) => (
        <Tag key={ug.id} color="cyan" style={{ fontSize: 12 }}>{ug.name_cn || ug.name}</Tag>
      ))}</Space>
    }},
    {
      title: '部门',
      dataIndex: 'department',
      width: 130,
      ellipsis: { showTitle: true },
      render: v => v || <Text type="secondary">—</Text>,
    },
    {
      title: '职位',
      dataIndex: 'title',
      width: 130,
      ellipsis: { showTitle: true },
      render: v => v || <Text type="secondary">—</Text>,
    },
    { title: '状态', dataIndex: 'is_active', width: 80, render: (v, r) => <Switch checked={v} size="small" onChange={c => updateMut.mutate({ id: r.id, data: { is_active: c } })} /> },
    { title: '操作', width: 100, render: (_, r) => <Space><Button size="small" icon={<EditOutlined />} onClick={() => void openEditWithLatestGroups(r)} /><Popconfirm title="确认删除？" onConfirm={() => deleteMut.mutate(r.id)} okText="删除" cancelText="取消"><Button size="small" danger icon={<DeleteOutlined />} /></Popconfirm></Space> },
  ]

  return (
    <div>
      {msgCtx}
      <PageHeader
        title="用户管理"
        marginBottom={20}
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
          <Button icon={<UploadOutlined />} onClick={openImport} style={isMobile ? { flex: 1 } : undefined}>导入用户</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => void openCreate()}
            style={isMobile ? { flex: 1 } : undefined}>新建用户</Button>
          </Space>
        )}
      />
      <FilterCard marginBottom={16}>
        <Space wrap size={[12, 12]} style={{ display: 'flex' }}>
          <Input.Search
            placeholder="搜索用户名 / 显示名 / 邮箱 / 电话号码"
            allowClear
            style={{ width: filterWidth(320) }}
            value={search}
            onSearch={handleSearch}
            onChange={e => {
              if (!e.target.value) handleSearch('')
              else {
                setPage(1)
                setSelectedRowKeys([])
                setSearch(e.target.value)
              }
            }}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="角色"
            style={{ width: filterWidth(180) }}
            options={roleOptions}
            value={roleIds}
            onChange={(value) => handleFilterChange(setRoleIds, value)}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="用户组"
            style={{ width: filterWidth(200) }}
            options={groupOptions}
            value={userGroupIds}
            onChange={(value) => handleFilterChange(setUserGroupIds, value)}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="部门"
            style={{ width: filterWidth(180) }}
            options={departmentOptions}
            value={departments}
            onChange={(value) => handleFilterChange(setDepartments, value)}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="职位"
            style={{ width: filterWidth(180) }}
            options={titleOptions}
            value={titles}
            onChange={(value) => handleFilterChange(setTitles, value)}
          />
          <Select
            mode="multiple"
            allowClear
            placeholder="状态"
            style={{ width: filterWidth(160) }}
            options={statusOptions}
            value={statuses}
            onChange={(value) => handleFilterChange(setStatuses, value)}
          />
          <Select
            style={{ width: filterWidth(180) }}
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
                <Text type="secondary">当前未设置筛选条件，将展示并导出全部用户。</Text>
              )}
            </Space>
            <Text type="secondary">
              {exportScope === 'selected'
                ? `当前导出范围：勾选结果${selectedRowKeys.length ? `（${selectedRowKeys.length} 条）` : '（未勾选）'}`
                : `当前导出范围：筛选结果（${data?.total ?? 0} 条）`}
            </Text>
          </Space>
        </div>
      </FilterCard>
      <Card style={{ borderRadius: 12, border: '1px solid rgba(0,0,0,0.08)' }} styles={{ body: { padding: 0 } }}>
        <Table dataSource={data?.items} columns={columns} rowKey="id" loading={isLoading}
          locale={{ emptyText: <TableEmptyState title="暂无用户数据" /> }}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys.map((key) => Number(key))),
          }}
          scroll={{ x: 1460 }}
          pagination={{
            current: page,
            total: data?.total,
            pageSize,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            showTotal: t => `共 ${t} 个用户`,
            onChange: (nextPage, nextPageSize) => {
              if (nextPage !== page || nextPageSize !== pageSize) setSelectedRowKeys([])
              if (nextPageSize !== pageSize) {
                setPage(1)
              } else {
                setPage(nextPage)
              }
              setPageSize(nextPageSize)
            },
          }} />
      </Card>
      <Modal title={editId ? '编辑用户' : '新建用户'} open={modalOpen} maskClosable={false} onOk={handleSubmit} onCancel={() => setModalOpen(false)}
        okText={editId ? '保存' : '创建'} confirmLoading={createMut.isPending || updateMut.isPending} width={640}>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item name="username" label="用户名" rules={[{ required: true }]}><Input disabled={!!editId} /></Form.Item>
          <Form.Item name="display_name" label="显示名称"><Input /></Form.Item>
          <Form.Item name="password" label="密码" rules={editId ? [] : passwordRules}><Input.Password placeholder={editId ? '留空不修改' : '至少 8 位，含大小写字母、数字和特殊字符'} /></Form.Item>
          <Form.Item name="email" label="邮箱"><Input type="email" /></Form.Item>
          <Form.Item name="phone" label="手机号"><Input /></Form.Item>
          <Form.Item name="role_id" label="角色">
            <Select allowClear placeholder="选择角色（留空为普通用户）" options={roleOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="manager_id" label="直属上级">
            <Select allowClear placeholder="选择直属上级" options={managerOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="employee_id" label="工号"><Input placeholder="如 EMP001" /></Form.Item>
          <Form.Item name="department" label="部门"><Input placeholder="如 技术部" /></Form.Item>
          <Form.Item name="title" label="职位"><Input placeholder="如 高级工程师" /></Form.Item>
          <Form.Item name="user_group_ids" label="用户组">
            <Select mode="multiple" placeholder="选择用户组" options={groupOptions} showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="is_superuser" label="超级管理员" valuePropName="checked"><Switch /></Form.Item>
        </Form>
      </Modal>
      <Modal
        title="批量导入用户"
        open={importOpen}
        maskClosable={false}
        onOk={handleImport}
        onCancel={() => { setImportOpen(false); setImportFile(null) }}
        okText="开始导入"
        confirmLoading={importMut.isPending}
        width={680}
      >
        <Form form={importForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="defaultPassword"
            label="默认密码"
            extra="当导入文件里没有 password 列或对应单元格为空时，将使用这个默认密码创建新用户。若要重置已存在用户密码，请在导入文件中显式提供 password 列和值。"
            rules={passwordRules}
          >
            <Input.Password placeholder={`例如 ${IMPORT_DEFAULT_PASSWORD}`} />
          </Form.Item>
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
              <p className="ant-upload-hint">文件表头支持模板字段，也兼容中文列名，例如 用户名、显示名称、用户组、角色。</p>
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
            rowKey={(record) => `${record.row}-${record.username}-${record.error}`}
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
    </div>
  )
}
