import '@ant-design/v5-patch-for-react-19'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider, theme } from 'antd'
import './index.css'
import App from './App'
import { UserProvider } from './user'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

// Enterprise look: navy brand, compact density, square-ish corners.
const brand = {
  algorithm: [theme.defaultAlgorithm, theme.compactAlgorithm],
  token: {
    colorPrimary: '#1d4e89',
    colorInfo: '#1d4e89',
    borderRadius: 3,
    fontFamily:
      "'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif",
    fontSize: 13,
  },
  components: {
    Layout: { headerBg: '#0b2545', siderBg: '#13315c', headerHeight: 48 },
    Menu: { darkItemBg: '#13315c', darkItemSelectedBg: '#1d4e89' },
    Table: { headerBg: '#eef2f7' },
  },
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ConfigProvider theme={brand}>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <UserProvider>
              <App />
            </UserProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </StrictMode>,
)
