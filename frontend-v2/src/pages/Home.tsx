import { useNavigate } from 'react-router-dom';
import { Button } from '../components/ui/Button';
import { Card, CardHeader, CardTitle, CardDescription } from '../components/ui/Card';
import { Upload, FileText } from 'lucide-react';

export const Home = () => {
  const navigate = useNavigate();

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      <div className="text-center space-y-4">
        <h1 className="text-4xl font-bold tracking-tight">
          防火墙策略自动化管理系统
        </h1>
        <p className="text-xl text-muted-foreground">
          简化策略管理，提升运维效率
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-6 mt-12">
        <Card className="hover:shadow-lg transition-shadow cursor-pointer" onClick={() => navigate('/upload')}>
          <CardHeader className="text-center space-y-4 p-8">
            <div className="mx-auto w-16 h-16 rounded-full bg-primary/10 flex items-center justify-center">
              <Upload className="h-8 w-8 text-primary" />
            </div>
            <CardTitle className="text-2xl">上传新文件</CardTitle>
            <CardDescription className="text-base">
              上传 Excel 文件创建新的策略工单
            </CardDescription>
            <Button className="mt-4">
              开始上传
            </Button>
          </CardHeader>
        </Card>

        <Card className="hover:shadow-lg transition-shadow">
          <CardHeader className="text-center space-y-4 p-8">
            <div className="mx-auto w-16 h-16 rounded-full bg-secondary/50 flex items-center justify-center">
              <FileText className="h-8 w-8 text-secondary-foreground" />
            </div>
            <CardTitle className="text-2xl">工单列表</CardTitle>
            <CardDescription className="text-base">
              查看和管理现有的策略工单
            </CardDescription>
            <Button variant="secondary" className="mt-4" disabled>
              即将推出
            </Button>
          </CardHeader>
        </Card>
      </div>

      <div className="mt-16 p-6 bg-muted/50 rounded-lg">
        <h2 className="text-xl font-semibold mb-4">功能特性</h2>
        <div className="grid md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <h3 className="font-medium">📤 智能上传</h3>
            <p className="text-sm text-muted-foreground">
              支持拖拽上传，自动解析 Excel 文件
            </p>
          </div>
          <div className="space-y-2">
            <h3 className="font-medium">✏️ 在线编辑</h3>
            <p className="text-sm text-muted-foreground">
              可视化表格编辑，支持版本管理
            </p>
          </div>
          <div className="space-y-2">
            <h3 className="font-medium">🚀 自动推送</h3>
            <p className="text-sm text-muted-foreground">
              实时推送进度，WebSocket 通信
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
