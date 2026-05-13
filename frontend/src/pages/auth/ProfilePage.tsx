import PageHeader from '@/components/common/PageHeader'
import ProfileSettingsContent from '@/components/auth/ProfileSettingsContent'

export default function ProfilePage() {
  return (
    <div>
      <PageHeader
        title="个人设置"
        meta="查看并修改账号信息，管理二步验证"
        marginBottom={24}
      />
      <ProfileSettingsContent />
    </div>
  )
}
