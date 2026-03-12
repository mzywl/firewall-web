// API 响应类型
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
  original_data?: Policy[];
  formatted_data?: Policy[];
}

export interface Policy {
  id?: number;
  order_id?: number;
  source_zone: string;
  dest_zone: string;
  source_ip: string;
  dest_ip: string;
  service: string;
  action: string;
  firewall_id?: number | null;
  push_status?: 'success' | 'failed' | null;
  push_message?: string | null;
}

export interface PolicyVersion {
  id: number;
  version_type: 'original' | 'formatted_v1' | 'formatted_v2' | 'user_modified';
  created_at: string;
  policy_count: number;
}

export interface PushStatus {
  order_id: number;
  order_status: string;
  total: number;
  success: number;
  failed: number;
  pending: number;
  progress: number;
}

export interface PushProgress {
  progress: number;
  current: number;
  total: number;
  success: number;
  failed: number;
}

export interface PushLog {
  level: 'info' | 'success' | 'error' | 'warning';
  message: string;
  timestamp: number;
}

export interface PushStatusUpdate {
  status: 'processing' | 'completed' | 'failed';
  message: string;
  success_count: number;
  failed_count: number;
}

// API 请求类型
export interface UploadRequest {
  file: File;
  title?: string;
  created_by?: string;
}

export interface UpdatePoliciesRequest {
  policies: Policy[];
}
