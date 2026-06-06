export type SqlInsightPanelProps = {
  embedded?: boolean
  instanceId?: number | null
}

export type SlowlogInstanceOption = {
  id: number
  instance_name: string
  db_type?: string | null
}

export type SlowlogDatabaseOption = {
  db_name: string
  is_active?: boolean
}
