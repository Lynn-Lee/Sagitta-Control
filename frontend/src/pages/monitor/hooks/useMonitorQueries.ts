import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'

import type { AlertEvent } from '@/api/commercial'
import apiClient from '@/api/client'

import { formatWindowMinutes } from '../formatters'
import type { MonitorInstance, MonitorOverview, UnifiedCollectConfigItem, UnifiedCollectConfigListResponse } from '../types'

type MonitorQueryParams = {
  selectedId: number | null
  dbTypeFilter?: string
  riskFilter?: string
  collectStatusFilter?: string
  trendHours: number
  topSqlWindowMinutes: number
  topSqlDateStart?: string
  topSqlDateEnd?: string
  topSqlRangeStartLabel?: string
  topSqlRangeEndLabel?: string
  canViewSql: boolean
  tableDb?: string
  tableSearch: string
  tablePage: number
  tablePageSize: number
}

export function useMonitorQueries(params: MonitorQueryParams) {
  const {
    selectedId,
    dbTypeFilter,
    riskFilter,
    collectStatusFilter,
    trendHours,
    topSqlWindowMinutes,
    topSqlDateStart,
    topSqlDateEnd,
    topSqlRangeStartLabel,
    topSqlRangeEndLabel,
    canViewSql,
    tableDb,
    tableSearch,
    tablePage,
    tablePageSize,
  } = params

  const { data, isLoading } = useQuery({
    queryKey: ['native-monitor-instances'],
    queryFn: () => apiClient.get('/monitor/native/instances/').then(r => r.data),
  })
  const { data: overview } = useQuery<MonitorOverview>({
    queryKey: ['native-monitor-overview'],
    queryFn: () => apiClient.get('/monitor/native/overview/').then(r => r.data),
  })
  const { data: collectConfigData } = useQuery<UnifiedCollectConfigListResponse>({
    queryKey: ['unified-collect-configs'],
    queryFn: () => apiClient.get('/monitor/native/collect-configs/').then(r => r.data),
  })
  const allInstances: MonitorInstance[] = useMemo(
    () => overview?.items || data?.items || [],
    [overview?.items, data?.items],
  )
  const collectConfigByInstance = useMemo(() => {
    const map = new Map<number, UnifiedCollectConfigItem>()
    ;(collectConfigData?.items || []).forEach(item => map.set(item.instance_id, item))
    return map
  }, [collectConfigData?.items])
  const instances = useMemo(() => allInstances.filter(item => {
    if (dbTypeFilter && item.db_type !== dbTypeFilter) return false
    if (riskFilter && item.risk_level !== riskFilter) return false
    if (collectStatusFilter && item.last_collect_status !== collectStatusFilter) return false
    return true
  }), [allInstances, dbTypeFilter, riskFilter, collectStatusFilter])
  const activeId = selectedId || instances[0]?.instance_id || null
  const active = instances.find(i => i.instance_id === activeId) || null

  const { data: detail } = useQuery({
    queryKey: ['native-monitor-detail', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: trendData } = useQuery({
    queryKey: ['native-monitor-trend', activeId, trendHours],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/trend/`, { params: { hours: trendHours } }).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: healthData } = useQuery({
    queryKey: ['native-monitor-health', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/health/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: topSqlData } = useQuery({
    queryKey: ['native-monitor-top-sql', activeId, topSqlWindowMinutes, topSqlDateStart, topSqlDateEnd],
    queryFn: () => {
      const queryParams: Record<string, any> = { window_minutes: topSqlWindowMinutes }
      if (topSqlDateStart && topSqlDateEnd) {
        queryParams.date_start = topSqlDateStart
        queryParams.date_end = topSqlDateEnd
      }
      return apiClient.get(`/monitor/native/instances/${activeId}/top-sql/`, { params: queryParams }).then(r => r.data)
    },
    enabled: !!activeId && canViewSql,
  })
  const topSqlRangeLabel = topSqlDateStart && topSqlDateEnd
    ? `${topSqlRangeStartLabel} 至 ${topSqlRangeEndLabel}`
    : `最近 ${formatWindowMinutes(topSqlData?.window_minutes || topSqlWindowMinutes)}`
  const { data: waitsData } = useQuery({
    queryKey: ['native-monitor-waits', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/waits/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: growthData } = useQuery({
    queryKey: ['native-monitor-capacity-growth', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/capacity-growth/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: engineDetail } = useQuery({
    queryKey: ['native-monitor-engine-detail', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/engine-detail/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: alertRules } = useQuery({
    queryKey: ['native-monitor-alerts', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/alerts/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: alertEvents } = useQuery<{ total: number; items: AlertEvent[] }>({
    queryKey: ['monitor-alert-events', activeId],
    queryFn: () => apiClient.get('/monitor/alerts/events', { params: { instance_id: activeId, page_size: 20 } }).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: dbCapacity } = useQuery({
    queryKey: ['native-monitor-db-capacity', activeId],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/databases/`).then(r => r.data),
    enabled: !!activeId,
  })
  const { data: tableCapacity, isLoading: tableLoading } = useQuery({
    queryKey: ['native-monitor-table-capacity', activeId, tableDb, tableSearch, tablePage, tablePageSize],
    queryFn: () => apiClient.get(`/monitor/native/instances/${activeId}/tables/`, { params: { db_name: tableDb, search: tableSearch, page: tablePage, page_size: tablePageSize } }).then(r => r.data),
    enabled: !!activeId,
  })

  return {
    data,
    isLoading,
    overview,
    collectConfigData,
    allInstances,
    collectConfigByInstance,
    instances,
    activeId,
    active,
    detail,
    trendData,
    healthData,
    topSqlData,
    topSqlRangeLabel,
    waitsData,
    growthData,
    engineDetail,
    alertRules,
    alertEvents,
    dbCapacity,
    tableCapacity,
    tableLoading,
  }
}
