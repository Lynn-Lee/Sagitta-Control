import { TruncatedCell } from './TruncatedCell'

export const renderTruncatedCell = (value?: unknown, ...tableRenderArgs: unknown[]) => {
  void tableRenderArgs
  return <TruncatedCell value={value} />
}
