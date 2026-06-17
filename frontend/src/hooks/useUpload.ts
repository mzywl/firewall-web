// 上传域 hooks
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../lib/api';

/** POST /api/orders/upload — 上传 Excel 创建工单 */
export const useUploadExcel = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ file, title, createdBy }: { file: File; title?: string; createdBy?: string }) =>
      api.uploadExcel(file, title, createdBy),
    onSuccess: () => {
      // 失效工单列表缓存 (虽然本项目暂无工单列表 page, 但防御性写)
      queryClient.invalidateQueries({ queryKey: ['orders'] });
    },
  });
};
