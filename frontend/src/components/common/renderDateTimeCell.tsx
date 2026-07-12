import DateTimeCell from './DateTimeCell'

// 表格日期时间列的共享渲染。收敛自 QueryHistoryPage 与 QueryPrivPage 的同名内联实现。
export const renderDateTimeCell = (value?: string | null) => <DateTimeCell value={value} />
