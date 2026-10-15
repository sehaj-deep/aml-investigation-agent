import { Layout, Menu, Segmented, Space, Tag, Tooltip, Typography } from 'antd'
import {
  AlertOutlined,
  AuditOutlined,
  DashboardOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { useUser, type Role } from './user'
import AlertQueue from './pages/AlertQueue'
import CaseWorkspace from './pages/CaseWorkspace'
import Dashboard from './pages/Dashboard'
import Governance from './pages/Governance'

const { Header, Sider, Content } = Layout

const NAV = [
  { key: '/alerts', icon: <AlertOutlined />, label: 'Alert queue' },
  { key: '/dashboard', icon: <DashboardOutlined />, label: 'Operations' },
  { key: '/governance', icon: <SafetyCertificateOutlined />, label: 'Governance' },
]

export default function App() {
  const navigate = useNavigate()
  const location = useLocation()
  const user = useUser()
  const selected = NAV.find((n) => location.pathname.startsWith(n.key))?.key ?? '/alerts'

  return (
    <Layout style={{ height: '100vh' }}>
      <Header style={{ display: 'flex', alignItems: 'center', gap: 16, paddingInline: 16 }}>
        <Space size={10} style={{ color: '#fff' }}>
          <AuditOutlined style={{ fontSize: 18 }} />
          <Typography.Text strong style={{ color: '#fff', fontSize: 15 }}>
            AML Case Manager
          </Typography.Text>
          <Tooltip title="Sandbox environment: all accounts and transactions are synthetic (IBM AMLworld).">
            <Tag color="gold" style={{ marginInlineStart: 4 }}>
              SANDBOX
            </Tag>
          </Tooltip>
        </Space>
        <div style={{ flex: 1 }} />
        <Space size={8}>
          <Typography.Text style={{ color: '#c9d6ea', fontSize: 12 }}>
            Working as <b style={{ color: '#fff' }}>{user.name}</b>
          </Typography.Text>
          <Segmented<Role>
            size="small"
            value={user.role}
            onChange={user.setRole}
            options={[
              { label: 'Analyst', value: 'analyst' },
              { label: 'Supervisor', value: 'supervisor' },
            ]}
          />
        </Space>
      </Header>
      <Layout style={{ flex: 1, minHeight: 0 }}>
        <Sider width={208} breakpoint="lg" collapsedWidth={56}>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selected]}
            items={NAV}
            onClick={(e) => navigate(e.key)}
            style={{ paddingTop: 8 }}
          />
        </Sider>
        <Content style={{ overflow: 'auto' }}>
          <Routes>
            <Route path="/" element={<Navigate to="/alerts" replace />} />
            <Route path="/alerts" element={<AlertQueue />} />
            <Route path="/cases" element={<Navigate to="/alerts" replace />} />
            <Route path="/cases/:caseId" element={<CaseWorkspace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/governance" element={<Governance />} />
            <Route path="*" element={<Navigate to="/alerts" replace />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  )
}
