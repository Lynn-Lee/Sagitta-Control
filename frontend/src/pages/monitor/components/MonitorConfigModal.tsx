import { Alert, Form, InputNumber, Modal, Switch, Tabs, type FormInstance } from 'antd'

// 观测中心「统一采集配置」弹窗。纯展示：表单实例、开关状态与保存/关闭回调均由父组件注入，
// 采集配置的原生 / 会话 / SQL 三档表单项内聚在此，从 MonitorPage 抽离以降低页面体量。
export function MonitorConfigModal({
  open,
  scope,
  targetName,
  instancesCount,
  form,
  isSaving,
  onOk,
  onClose,
}: {
  open: boolean
  scope: 'single' | 'all'
  targetName: string
  instancesCount: number
  form: FormInstance
  isSaving: boolean
  onOk: () => void
  onClose: () => void
}) {
  return (
    <Modal
      title={scope === 'all' ? '统一采集配置 - 全部实例' : `统一采集配置 - ${targetName}`}
      open={open}
      onCancel={onClose}
      onOk={onOk}
      confirmLoading={isSaving}
      okText="保存"
      cancelText="取消"
      maskClosable={false}
      width={720}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginTop: 8 }}
        message={scope === 'all' ? '该配置将应用到全部可见实例' : '该配置仅作用于当前实例'}
        description={scope === 'all' ? `保存后会为当前列表中的 ${instancesCount} 个实例写入相同采集配置。手动立即采集指标不会改变这些开关。` : '保存后会同时更新当前实例的指标/容量、会话和 SQL 采集配置。手动立即采集指标不会改变这些开关。'}
      />
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Tabs
          items={[
            {
              key: 'native',
              label: '原生监控',
              children: (
                <>
                  <Form.Item name={['native', 'is_enabled']} label="启用指标/容量采集" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name={['native', 'collect_interval']} label="实例指标采集间隔（秒）" rules={[{ required: true }]}>
                    <InputNumber min={10} max={3600} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name={['native', 'capacity_collect_interval']} label="容量采集间隔（秒）" rules={[{ required: true }]}>
                    <InputNumber min={300} max={86400} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name={['native', 'retention_days']} label="指标保留天数" rules={[{ required: true }]}>
                    <InputNumber min={1} max={365} style={{ width: '100%' }} />
                  </Form.Item>
                </>
              ),
            },
            {
              key: 'session',
              label: '会话采集',
              children: (
                <>
                  <Form.Item name={['session', 'is_enabled']} label="启用会话采集" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name={['session', 'collect_interval']} label="会话采样间隔（秒）" rules={[{ required: true }]}>
                    <InputNumber min={10} max={86400} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name={['session', 'retention_days']} label="会话数据保留天数" rules={[{ required: true }]}>
                    <InputNumber min={1} max={365} style={{ width: '100%' }} />
                  </Form.Item>
                </>
              ),
            },
            {
              key: 'sql',
              label: 'SQL 采集',
              children: (
                <>
                  <Form.Item name={['sql', 'is_enabled']} label="启用 SQL 采集" valuePropName="checked">
                    <Switch />
                  </Form.Item>
                  <Form.Item name={['sql', 'threshold_ms']} label="SQL 耗时阈值（ms）" rules={[{ required: true }]}>
                    <InputNumber min={0} max={3600000} step={500} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name={['sql', 'collect_interval']} label="SQL 采集间隔（秒）" rules={[{ required: true }]}>
                    <InputNumber min={30} max={86400} step={30} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name={['sql', 'retention_days']} label="SQL 数据保留天数" rules={[{ required: true }]}>
                    <InputNumber min={1} max={365} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name={['sql', 'collect_limit']} label="单次采集上限" rules={[{ required: true }]}>
                    <InputNumber min={1} max={1000} style={{ width: '100%' }} />
                  </Form.Item>
                </>
              ),
            },
          ]}
        />
      </Form>
    </Modal>
  )
}
