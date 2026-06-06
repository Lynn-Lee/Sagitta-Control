import { InputNumber, Select, Space, Typography } from 'antd'

import { clampRangeDays, RANGE_OPTIONS } from '../helpers'

const { Text } = Typography

type SmallRangeSelectorProps = {
  days: number
  setDays: (value: number) => void
  daysInput: number
  setDaysInput: (value: number) => void
  scopeLabel?: string
}

export default function SmallRangeSelector({
  days,
  setDays,
  setDaysInput,
  scopeLabel,
}: SmallRangeSelectorProps) {
  const presetOptions = RANGE_OPTIONS.map(option => ({ label: `${option}天`, value: option }))
  const options = presetOptions.some(option => option.value === days)
    ? presetOptions
    : [{ label: `${days}天`, value: days }, ...presetOptions]

  return (
    <Space className="overview-range" wrap align="center">
      <Text type="secondary">
        {scopeLabel || '我的数据'}
      </Text>
      <Select
        size="small"
        value={days}
        options={options}
        popupClassName="overview-range-select-popup"
        onChange={value => {
          const nextDays = clampRangeDays(Number(value))
          setDays(nextDays)
          setDaysInput(nextDays)
        }}
      />
      <Text type="secondary">
        自定义
      </Text>
      <InputNumber
        className="overview-range-days-input"
        size="small"
        min={1}
        max={365}
        value={days}
        addonAfter="天"
        onChange={value => {
          const nextDays = clampRangeDays(Number(value ?? 1))
          setDays(nextDays)
          setDaysInput(nextDays)
        }}
      />
    </Space>
  )
}
