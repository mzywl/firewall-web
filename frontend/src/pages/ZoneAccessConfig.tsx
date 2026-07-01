/**
 * ZoneAccessConfig 全局视图
 *
 * 设计对应 重构.md §1 spec (按防火墙视角聚合):
 *   - 按 firewall 分组展示所有跨区配置
 *   - 字段: source_region, dest_region, boundary_source_zone, boundary_dest_zone,
 *           need_nat, snat_pool, description
 *   - 老的 source_zone/dest_zone 已 rename 为 source_region/dest_region
 *
 * 跳转:
 *   - 点防火墙 → /firewalls/:id (详情)
 *   - 新增/编辑某防火墙的 cfg → /firewalls/:id/access
 *
 * 本页是"全局只读 + 跳转到 per-firewall 编辑"的设计, 避免之前表单在同一页维护多 fw 的混乱
 */
import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Network, ChevronRight, Filter } from 'lucide-react';
import { toast } from '../lib/toast';

interface Firewall {
  id: number;
  name: string;
  alias: string;
  belong_region: string;
  is_zone_boundary: number;
}

interface ZoneAccessConfig {
  id: number;
  firewall_id: number;
  source_region: string;
  dest_region: string;
  boundary_source_zone: string;
  boundary_dest_zone: string;
  need_nat: number;
  snat_pool: string | null;
  description: string | null;
}

interface ConfigsResponse {
  firewalls: Firewall[];
  configs: ZoneAccessConfig[];
}

export default function ZoneAccessConfig() {
  const [data, setData] = useState<ConfigsResponse>({ firewalls: [], configs: [] });
  const [loading, setLoading] = useState(true);
  const [filterRegion, setFilterRegion] = useState<string>('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [fwRes, cfgRes] = await Promise.all([
        fetch('/api/zone-access/firewalls').then((r) => r.json()),
        fetch('/api/zone-access/configs').then((r) => r.json()),
      ]);
      setData({
        firewalls: fwRes.firewalls || [],
        configs: cfgRes.configs || [],
      });
    } catch (error) {
      toast.apiError(error, '加载跨区配置失败');
    } finally {
      setLoading(false);
    }
  };

  // 防火墙 → 它配置的 cfg 列表
  const configsByFw = data.configs.reduce<Record<number, ZoneAccessConfig[]>>((acc, cfg) => {
    (acc[cfg.firewall_id] ||= []).push(cfg);
    return acc;
  }, {});

  // 收集所有 unique region (用于 filter 下拉)
  const allRegions = Array.from(
    new Set(data.firewalls.map((f) => f.belong_region).filter(Boolean)),
  ).sort();

  // 应用 filter
  const filteredFirewalls = data.firewalls.filter(
    (f) => !filterRegion || f.belong_region === filterRegion,
  );

  // 全局统计
  const totalCfgs = data.configs.length;
  const fwWithCfg = new Set(data.configs.map((c) => c.firewall_id)).size;
  const boundaryFw = data.firewalls.filter((f) => f.is_zone_boundary === 1).length;
  const needNatCfgs = data.configs.filter((c) => c.need_nat === 1).length;

  return (
    <div className="container mx-auto p-6 max-w-6xl">
      {/* 顶部 */}
      <div className="flex items-center gap-4 mb-6">
        <Network className="w-8 h-8 text-orange-500" />
        <div>
          <h1 className="text-3xl font-bold">全局跨区配置</h1>
          <p className="text-sm text-gray-500 mt-1">
            按防火墙聚合, 单条 cfg 表达一对 (source_region → dest_region) 的边界 NAT 路径
          </p>
        </div>
      </div>

      {/* 概览卡片 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard label="防火墙总数" value={data.firewalls.length} color="text-gray-700" />
        <StatCard label="边界墙" value={boundaryFw} color="text-orange-600" />
        <StatCard label="已配跨区配置" value={`${fwWithCfg} / ${data.firewalls.length}`} color="text-blue-600" />
        <StatCard label="需 SNAT 的路径" value={`${needNatCfgs} / ${totalCfgs}`} color="text-purple-600" />
      </div>

      {/* 过滤 */}
      <div className="flex items-center gap-3 mb-4">
        <Filter className="w-4 h-4 text-gray-500" />
        <span className="text-sm text-gray-600">过滤大区:</span>
        <select
          className="px-3 py-1.5 border rounded-md text-sm"
          value={filterRegion}
          onChange={(e) => setFilterRegion(e.target.value)}
        >
          <option value="">全部 ({data.firewalls.length})</option>
          {allRegions.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        {filterRegion && (
          <Button variant="outline" size="sm" onClick={() => setFilterRegion('')}>
            清除
          </Button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-gray-500">加载中...</p>
      ) : filteredFirewalls.length === 0 ? (
        <Card className="p-8 text-center">
          <p className="text-sm text-gray-500">没有防火墙或被过滤掉</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredFirewalls.map((fw) => {
            const fwConfigs = configsByFw[fw.id] || [];
            return (
              <Card key={fw.id} className="p-4 hover:shadow-md transition-shadow">
                <div className="flex items-center gap-3 mb-3">
                  <Link to={`/firewalls/${fw.id}`} className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-lg">{fw.name}</span>
                      {fw.alias && (
                        <span className="text-sm text-gray-500">({fw.alias})</span>
                      )}
                      {fw.is_zone_boundary === 1 && (
                        <Badge className="bg-orange-500">边界墙</Badge>
                      )}
                      <Badge variant="outline">{fw.belong_region || '(未设)'}</Badge>
                    </div>
                  </Link>
                  <Link to={`/firewalls/${fw.id}/access`}>
                    <Button variant="outline" size="sm">
                      {fwConfigs.length === 0 ? '+ 新增' : `编辑 (${fwConfigs.length})`}
                      <ChevronRight className="w-3 h-3 ml-1" />
                    </Button>
                  </Link>
                </div>

                {fwConfigs.length === 0 ? (
                  <p className="text-xs text-gray-400 py-2 pl-1">
                    暂无跨区配置{fw.is_zone_boundary === 0 && ' (非边界墙, 通常无配置)'}
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {fwConfigs.map((cfg) => (
                      <div
                        key={cfg.id}
                        className="flex items-center gap-2 text-sm px-3 py-2 bg-gray-50 rounded"
                      >
                        <div className="flex items-center gap-1 font-mono">
                          <Badge>{cfg.source_region}</Badge>
                          <span className="text-gray-400">→</span>
                          <Badge variant="outline">{cfg.dest_region}</Badge>
                        </div>
                        <span className="text-gray-300">|</span>
                        <span className="text-xs font-mono text-gray-600">
                          {cfg.boundary_source_zone} → {cfg.boundary_dest_zone}
                        </span>
                        <span className="text-gray-300">|</span>
                        {cfg.need_nat === 1 ? (
                          <Badge className="bg-orange-500 text-xs">SNAT</Badge>
                        ) : (
                          <Badge variant="outline" className="text-xs">无需 NAT</Badge>
                        )}
                        {cfg.snat_pool && (
                          <span className="text-xs font-mono text-gray-500 truncate">
                            池: {cfg.snat_pool}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      <Card className="p-4 mt-6 bg-blue-50 border-blue-200">
        <h3 className="text-sm font-semibold mb-1">💡 设计说明</h3>
        <ul className="text-xs text-gray-700 space-y-1">
          <li>• 老版本: 全局单页 + 内联表单维护所有防火墙的 cfg (易混乱, 防火墙多了难看)</li>
          <li>• 新版本: 本页只读聚合展示, 真正编辑跳到 <b>/firewalls/:id/access</b> per-firewall 子页</li>
          <li>• 老字段 source_zone / dest_zone 已统一改名为 source_region / dest_region, 跟 belong_region 对齐</li>
          <li>• 每条 cfg 关联一对 boundary_zone (源侧/目的侧), 跟防火墙的 FirewallZone 表保持一致性</li>
        </ul>
      </Card>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string | number; color: string }) {
  return (
    <Card className="p-4">
      <div className="text-xs text-gray-500 mb-1">{label}</div>
      <div className={`text-2xl font-bold ${color}`}>{value}</div>
    </Card>
  );
}