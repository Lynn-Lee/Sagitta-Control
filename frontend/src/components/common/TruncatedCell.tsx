import type { CSSProperties, ReactNode } from 'react'
import { Tooltip, Typography } from 'antd'

const { Text } = Typography

type TruncatedCellProps = {
  value?: unknown
  tooltipValue?: unknown
  empty?: ReactNode
  className?: string
  style?: CSSProperties
  textStyle?: CSSProperties
  type?: 'secondary' | 'success' | 'warning' | 'danger'
  strong?: boolean
  code?: boolean
  inline?: boolean
}

const isEmptyValue = (value: unknown) =>
  value === null || value === undefined || value === ''

export function TruncatedCell({
  value,
  tooltipValue,
  empty = '—',
  className,
  style,
  textStyle,
  type,
  strong,
  code,
  inline = false,
}: TruncatedCellProps) {
  if (isEmptyValue(value)) {
    return <Text type="secondary">{empty}</Text>
  }

  const text = String(value)
  const tooltipText = isEmptyValue(tooltipValue) ? text : String(tooltipValue)
  const classes = [
    'sagitta-table-truncated-cell',
    inline ? 'sagitta-table-truncated-cell--inline' : '',
    className || '',
  ].filter(Boolean).join(' ')

  return (
    <Tooltip title={tooltipText} placement="topLeft" overlayClassName="sagitta-table-truncated-tooltip">
      <span className={classes} style={style}>
        <Text type={type} strong={strong} code={code} style={textStyle}>
          {text}
        </Text>
      </span>
    </Tooltip>
  )
}
