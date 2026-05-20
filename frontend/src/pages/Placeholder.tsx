import { Result, Button } from 'antd'
import { HomeOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'

export default function Placeholder({ title }: { title: string }) {
  const navigate = useNavigate()
  return (
    <Result
      status="info"
      title={title}
      subTitle="此功能正在开发中，敬请期待"
      extra={<Button type="primary" icon={<HomeOutlined />} onClick={() => navigate('/dashboard')}>返回首页</Button>}
    />
  )
}
