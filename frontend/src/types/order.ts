// Order 域类型 (工单生命周期相关)
// 跟后端 /api/orders/* 路由返回对应

import type { Policy } from './policy';

/** 工单 (跟后端 Order ORM 对应, 字段是英文 snake_case) */
export interface Order {
  id: number;
  order_no: string;
  title: string;
  description: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  excel_file_path: string;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  // 上传响应里附带的原始/格式化数据 (中文字段, 跟 Policy 字段名不一致!)
  // 实际类型是 string-keyed dict, 这里用 Policy 是 loose typing, 见 SKILL.md 坑点 1
  original_data?: Policy[];
  formatted_data?: Policy[];
}

/** 策略版本快照 (工单的子资源, 跟 order 生命周期绑定) */
export interface PolicyVersion {
  id: number;
  version_type: 'original' | 'formatted_v1' | 'formatted_v2' | 'user_modified';
  created_at: string;
  policy_count: number;
}

/** 上传 Excel 请求 */
export interface UploadRequest {
  file: File;
  title?: string;
  created_by?: string;
}
