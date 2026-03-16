import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from './components/layout/Layout';
import { Home } from './pages/Home';
import { Upload } from './pages/Upload';
import { Edit } from './pages/Edit';
import { Preview } from './pages/Preview';
import { Push } from './pages/Push';
import FirewallManagement from './pages/FirewallManagement';
import FirewallForm from './pages/FirewallForm';
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
            <Route path="/" element={<Home />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/order/:orderId/edit" element={<Edit />} />
            <Route path="/order/:orderId/preview" element={<Preview />} />
            <Route path="/order/:orderId/push" element={<Push />} />
            <Route path="/firewalls" element={<FirewallManagement />} />
            <Route path="/firewalls/new" element={<FirewallForm />} />
            <Route path="/firewalls/:id/edit" element={<FirewallForm />} />
            <Route path="/zone-access" element={<ZoneAccessConfig />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
