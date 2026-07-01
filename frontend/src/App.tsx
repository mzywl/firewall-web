import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/layout/Layout';
import { Home } from './pages/Home';
import { Upload } from './pages/Upload';
import { Edit } from './pages/Edit';
import { Preview } from './pages/Preview';
import { Push } from './pages/Push';
import { SnapshotDetail } from './pages/SnapshotDetail';
import FirewallManagement from './pages/FirewallManagement';
import BasicFirewallForm from './pages/BasicFirewallForm';
import FirewallDetail from './pages/FirewallDetail';
import FirewallZones from './pages/FirewallZones';
import FirewallAccessConfigs from './pages/FirewallAccessConfigs';
import ZoneAccessConfig from './pages/ZoneAccessConfig';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Layout>
          <Routes>
            {/* 工单相关 */}
            <Route path="/" element={<Home />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/order/:orderId/edit" element={<Edit />} />
            <Route path="/order/:orderId/preview" element={<Preview />} />
            <Route path="/order/:orderId/push" element={<Push />} />
            <Route path="/snapshot/:snapshotId" element={<SnapshotDetail />} />

            {/* 防火墙管理 — 子路由结构 (Option C 独立路由) */}
            <Route path="/firewalls" element={<FirewallManagement />} />
            <Route path="/firewalls/new" element={<BasicFirewallForm />} />
            <Route path="/firewalls/:id" element={<FirewallDetail />} />
            <Route path="/firewalls/:id/edit" element={<BasicFirewallForm />} />
            <Route path="/firewalls/:id/zones" element={<FirewallZones />} />
            <Route path="/firewalls/:id/access" element={<FirewallAccessConfigs />} />

            {/* 全局跨区配置 (按防火墙聚合, 只读 + 跳转 per-firewall 编辑) */}
            <Route path="/zone-access" element={<ZoneAccessConfig />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;