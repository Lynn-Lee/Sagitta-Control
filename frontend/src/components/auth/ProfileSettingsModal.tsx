import { Modal } from 'antd'
import ProfileSettingsContent from './ProfileSettingsContent'

type ProfileSettingsModalProps = {
  open: boolean
  onClose: () => void
}

export default function ProfileSettingsModal({ open, onClose }: ProfileSettingsModalProps) {
  return (
    <Modal
      title="个人设置"
      open={open}
      onCancel={onClose}
      footer={null}
      width={1000}
      destroyOnClose
      styles={{ body: { maxHeight: 'calc(100vh - 180px)', overflowY: 'auto' } }}
    >
      <ProfileSettingsContent />
    </Modal>
  )
}
