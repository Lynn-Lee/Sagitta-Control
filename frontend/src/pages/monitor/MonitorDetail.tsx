import PageHeader from '@/components/common/PageHeader'
import SectionCard from '@/components/common/SectionCard'
import TableEmptyState from '@/components/common/TableEmptyState'

export default function MonitorDetail() {
  return (
    <div>
      <PageHeader
        title="监控详情"
        meta="指标详情页正在分阶段完善中"
        marginBottom={24}
      />
      <SectionCard marginBottom={0}>
        <div style={{ padding: 24 }}>
          <TableEmptyState title="监控详情能力将在后续迭代中开放" />
        </div>
      </SectionCard>
    </div>
  )
}
