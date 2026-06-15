import { Typography } from 'antd'
import { formatDateTime } from '@/utils/datetime'

const { Text } = Typography

type DateTimeCellProps = {
  value?: string | null
  fallback?: string
}

export default function DateTimeCell({ value, fallback = '—' }: DateTimeCellProps) {
  return (
    <Text className="sagitta-nowrap-cell sagitta-date-time-cell">
      {formatDateTime(value, fallback)}
    </Text>
  )
}
