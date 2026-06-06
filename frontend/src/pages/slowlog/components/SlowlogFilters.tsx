import { Button, DatePicker, Input, InputNumber, Select, Space, Typography } from 'antd'
import { ClearOutlined, CloudDownloadOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import FilterCard from '@/components/common/FilterCard'
import { formatDbTypeLabel } from '@/utils/dbType'
import { SOURCE_OPTIONS } from '../helpers'
import type { SlowlogDatabaseOption, SlowlogInstanceOption } from '../types'

const { Text } = Typography
const { RangePicker } = DatePicker

type SlowlogFiltersProps = {
  embedded: boolean
  dateRange: [string, string] | null
  instanceId: number | undefined
  dbName: string
  source: string | undefined
  sqlKeyword: string
  username: string
  tag: string | undefined
  minDurationMs: number
  instances: SlowlogInstanceOption[]
  databases: SlowlogDatabaseOption[]
  selectedInstance?: SlowlogInstanceOption
  tagSelectOptions: Array<{ label: string; value: string }>
  tagOptionsLoading: boolean
  canManageCollect: boolean
  collectLoading: boolean
  filterWidth: (width: number) => number | string
  onDateRangeChange: (value: [string, string] | null) => void
  onInstanceIdChange: (value: number | undefined) => void
  onDbNameChange: (value: string) => void
  onSourceChange: (value: string | undefined) => void
  onSqlKeywordChange: (value: string) => void
  onUsernameChange: (value: string) => void
  onTagChange: (value: string | undefined) => void
  onMinDurationMsChange: (value: number) => void
  onRefresh: () => void
  onCollect: () => void
  onReset: () => void
}

export function SlowlogFilters({
  embedded,
  dateRange,
  instanceId,
  dbName,
  source,
  sqlKeyword,
  username,
  tag,
  minDurationMs,
  instances,
  databases,
  selectedInstance,
  tagSelectOptions,
  tagOptionsLoading,
  canManageCollect,
  collectLoading,
  filterWidth,
  onDateRangeChange,
  onInstanceIdChange,
  onDbNameChange,
  onSourceChange,
  onSqlKeywordChange,
  onUsernameChange,
  onTagChange,
  onMinDurationMsChange,
  onRefresh,
  onCollect,
  onReset,
}: SlowlogFiltersProps) {
  return (
    <FilterCard marginBottom={16}>
      <Space wrap size={[8, 8]} style={{ display: 'flex' }}>
        <RangePicker
          showTime
          value={dateRange ? [dayjs(dateRange[0]), dayjs(dateRange[1])] : null}
          style={{ width: filterWidth(360) }}
          onChange={(_, strs) => onDateRangeChange(strs[0] ? [dayjs(strs[0]).toISOString(), dayjs(strs[1]).toISOString()] : null)}
        />
        {!embedded ? (
          <Select
            placeholder="实例"
            allowClear
            showSearch
            optionFilterProp="label"
            style={{ width: filterWidth(210) }}
            value={instanceId}
            onChange={(v) => onInstanceIdChange(v)}
            onClear={() => onDbNameChange('')}
            options={instances.map(inst => ({
              value: inst.id,
              label: inst.instance_name,
              children: inst.instance_name,
            }))}
          />
        ) : (
          <Text strong>{selectedInstance ? `${selectedInstance.instance_name} / ${formatDbTypeLabel(selectedInstance.db_type)}` : '请选择实例'}</Text>
        )}
        <Select
          placeholder="数据库"
          allowClear
          showSearch
          optionFilterProp="label"
          disabled={!instanceId}
          style={{ width: filterWidth(150) }}
          value={dbName || undefined}
          onChange={(v) => onDbNameChange(v || '')}
          options={databases
            .filter(db => db.is_active)
            .map(db => ({ value: db.db_name, label: db.db_name }))}
        />
        <Select placeholder="来源" allowClear style={{ width: filterWidth(140) }} value={source} onChange={(v) => onSourceChange(v)} options={SOURCE_OPTIONS} />
        <Input placeholder="SQL 关键字" allowClear style={{ width: filterWidth(180) }} value={sqlKeyword} onChange={(e) => onSqlKeywordChange(e.target.value)} />
        <Input placeholder="用户" allowClear style={{ width: filterWidth(130) }} value={username} onChange={(e) => onUsernameChange(e.target.value)} />
        <Select
          placeholder={instanceId ? '标签' : '先选实例'}
          allowClear
          disabled={!instanceId || !tagSelectOptions.length}
          loading={tagOptionsLoading}
          style={{ width: filterWidth(150) }}
          value={tag}
          onChange={(v) => onTagChange(v)}
          options={tagSelectOptions}
        />
        <InputNumber min={0} step={500} addonAfter="ms" style={{ width: filterWidth(140) }} value={minDurationMs} onChange={(v) => onMinDurationMsChange(Number(v || 0))} />
        <Button className="sagitta-action-btn sagitta-action-btn--refresh" icon={<ReloadOutlined />} onClick={onRefresh}>刷新</Button>
        <Button icon={<CloudDownloadOutlined />} type="primary" disabled={!canManageCollect} loading={collectLoading} onClick={onCollect}>立即采集一次</Button>
        <Button className="sagitta-action-btn sagitta-action-btn--neutral" icon={<ClearOutlined />} onClick={onReset}>{embedded ? '重置条件' : '重置'}</Button>
      </Space>
    </FilterCard>
  )
}
