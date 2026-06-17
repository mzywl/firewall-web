import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileUploader } from '../components/upload/FileUploader';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '../components/ui/Card';
import { useUploadExcel } from '../hooks/useUpload';
import { Loader2 } from 'lucide-react';
import { toast } from '../lib/toast';

export const Upload = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const uploadMutation = useUploadExcel();

  const handleUpload = async () => {
    if (!file) return;

    try {
      const result = await uploadMutation.mutateAsync({
        file,
        title: title || file.name,
        createdBy: 'admin',
      });

      // 上传成功，跳转到编辑页面
      navigate(`/order/${result.id}/edit`);
    } catch (error) {
      toast.apiError(error, '上传失败，请重试');
    }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <h1 className="text-3xl font-bold mb-2">上传策略文件</h1>
        <p className="text-muted-foreground">
          上传 Excel 文件以创建新的防火墙策略工单
        </p>
      </div>

      <FileUploader
        onFileSelect={setFile}
        isUploading={uploadMutation.isPending}
      />

      {file && (
        <Card>
          <CardHeader>
            <CardTitle>工单信息</CardTitle>
            <CardDescription>
              为此工单设置工单号（可选，留空则自动生成）
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <label htmlFor="title" className="text-sm font-medium">
                工单号
              </label>
              <Input
                id="title"
                placeholder="输入工单号（留空则自动生成，格式：ORD-YYYYMMDDHHMMSS）"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                disabled={uploadMutation.isPending}
              />
            </div>
          </CardContent>
          <CardFooter className="flex justify-between">
            <Button
              variant="outline"
              onClick={() => {
                setFile(null);
                setTitle('');
              }}
              disabled={uploadMutation.isPending}
            >
              取消
            </Button>
            <Button
              onClick={handleUpload}
              disabled={uploadMutation.isPending}
            >
              {uploadMutation.isPending && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              {uploadMutation.isPending ? '上传中...' : '开始上传'}
            </Button>
          </CardFooter>
        </Card>
      )}
    </div>
  );
};
