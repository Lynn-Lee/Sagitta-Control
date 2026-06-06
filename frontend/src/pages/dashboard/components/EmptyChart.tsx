import { DASHBOARD_CHART_HEIGHT } from '../helpers'

export default function EmptyChart({ text }: { text: string }) {
  return (
    <div
      style={{
        height: DASHBOARD_CHART_HEIGHT,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#AEAEB2',
      }}
    >
      {text}
    </div>
  )
}
