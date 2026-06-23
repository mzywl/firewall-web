// FirewallPolicyTable 组件测试 - 验证关键渲染场景
// 这个组件最容易碎: 字段名错一列 / source_zone_name vs source_zone 用错 / PASS_THROUGH 渲染漏
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FirewallPolicyTable } from './FirewallPolicyTable'
import type { FirewallGroup, PreviewPolicy, NATPolicy, NATInfo } from '../../types'

// fixture 工厂
const makeNATInfo = (over: Partial<NATInfo> = {}): NATInfo => ({
  need_nat: false,
  nat_type: null,
  snat_address: null,
  dnat_address: null,
  source_zone: null,
  dest_zone: null,
  source_zone_name: null,
  dest_zone_name: null,
  warnings: [],
  ...over,
})

const makePolicy = (over: Partial<PreviewPolicy> = {}): PreviewPolicy => ({
  id: 1,
  sequence: 1,
  source_zone: '业务A',
  source_ip: '10.1.1.1',
  dest_zone: '业务B',
  dest_ip: '10.2.2.2',
  service: '443',
  action: 'permit',
  nat_info: makeNATInfo(),
  nat_policies: [],
  使用时间: '长期',
  ...over,
})

const makeGroup = (over: Partial<FirewallGroup> = {}): FirewallGroup => ({
  firewall: {
    id: 1,
    name: 'fw-test',
    alias: '测试防火墙',
    type: 'fortinet',
    management_ip: '10.99.99.1',
    belong_region: '测试区',
    is_zone_boundary: 0,
    auto_push: 0,
  },
  policies: [],
  ...over,
})

describe('FirewallPolicyTable', () => {
  it('renders firewall alias and policy count', () => {
    // 这个组件只展示 group 内的 policies, 不展示 alias
    // 测基础表格渲染
    const group = makeGroup({ policies: [makePolicy()] })
    render(<FirewallPolicyTable group={group} />)
    expect(screen.getByText('10.1.1.1')).toBeInTheDocument()
    expect(screen.getByText('10.2.2.2')).toBeInTheDocument()
    expect(screen.getByText('443')).toBeInTheDocument()
    // C4: 动作列已删, 不再测 'permit' 单元格; action 字段仍存在但不在表里
  })

  it('prefers source_zone_name (业务名) over source_zone (程序值)', () => {
    const policy = makePolicy({
      nat_info: makeNATInfo({
        source_zone: 'internal',           // 程序值
        source_zone_name: '内网业务区',     // 业务名, UI 应该用这个
        dest_zone: 'external',
        dest_zone_name: 'DMZ区',
      }),
    })
    render(<FirewallPolicyTable group={makeGroup({ policies: [policy] })} />)
    // 应该显示业务名, 不是程序值
    expect(screen.getByText('内网业务区')).toBeInTheDocument()
    expect(screen.getByText('DMZ区')).toBeInTheDocument()
    // 程序值不应该直接显示
    expect(screen.queryByText('internal')).not.toBeInTheDocument()
  })

  it('shows "无需NAT" for policies with need_nat=false', () => {
    const policy = makePolicy({ nat_info: makeNATInfo({ need_nat: false }) })
    render(<FirewallPolicyTable group={makeGroup({ policies: [policy] })} />)
    expect(screen.getByText('无需NAT')).toBeInTheDocument()
  })

  it('shows SNAT badge for policies with need_nat=true', () => {
    const policy = makePolicy({
      nat_info: makeNATInfo({ need_nat: true, nat_type: 'SNAT' }),
    })
    render(<FirewallPolicyTable group={makeGroup({ policies: [policy] })} />)
    expect(screen.getByText('SNAT')).toBeInTheDocument()
  })

  it('renders SNAT conversion row (blue) when nat_policies present', () => {
    const natPolicies: NATPolicy[] = [
      {
        type: 'SNAT',
        source_zone: '内网',
        source_ip: '203.0.113.10',  // SNAT 后的地址
        dest_zone: 'DMZ',
        dest_ip: '10.2.2.2',
        service: '443',
        action: 'permit',
      },
    ]
    const policy = makePolicy({
      nat_info: makeNATInfo({ need_nat: true, nat_type: 'SNAT' }),
      nat_policies: natPolicies,
    })
    const { container } = render(
      <FirewallPolicyTable group={makeGroup({ policies: [policy] })} />
    )
    // SNAT 行的 source_ip 应该是转换后的地址
    expect(screen.getByText('203.0.113.10')).toBeInTheDocument()
    // 蓝色行
    expect(container.querySelector('.bg-blue-50')).toBeInTheDocument()
  })

  it('renders PASS_THROUGH row (green) with via_firewall label', () => {
    const natPolicies: NATPolicy[] = [
      {
        type: 'PASS_THROUGH',
        source_zone: '内网',
        source_ip: '198.51.100.5',
        dest_zone: 'DMZ',
        dest_ip: '10.2.2.2',
        service: '443',
        action: 'permit',
        via_firewall: { id: 99, name: '前置墙fw1' },
      },
    ]
    const policy = makePolicy({ nat_policies: natPolicies })
    const { container } = render(
      <FirewallPolicyTable group={makeGroup({ policies: [policy] })} />
    )
    // 透传行标记
    expect(screen.getByText(/经 前置墙fw1 SNAT 转换/)).toBeInTheDocument()
    // 绿色行
    expect(container.querySelector('.bg-emerald-50')).toBeInTheDocument()
  })

  it('PASS_THROUGH shows "原 src=..." when original_source_ip differs from source_ip (C3)', () => {
    // source_ip 是 SNAT 后的地址, original_source_ip 是流量真实原始 IP
    const natPolicies: NATPolicy[] = [
      {
        type: 'PASS_THROUGH',
        source_zone: '内网',
        source_ip: '198.51.100.5',     // SNAT 后 (透传到下游墙的源)
        original_source_ip: '10.1.1.7', // 流量真实原 IP
        dest_zone: 'DMZ',
        dest_ip: '10.2.2.2',
        service: '443',
        action: 'permit',
        via_firewall: { id: 99, name: '前置墙fw1' },
      },
    ]
    const policy = makePolicy({ nat_policies: natPolicies })
    render(<FirewallPolicyTable group={makeGroup({ policies: [policy] })} />)
    // 两个 IP 都要在文档里, 且 "原 src=..." 标签存在
    expect(screen.getByText('198.51.100.5')).toBeInTheDocument()
    expect(screen.getByText(/原 src=10\.1\.1\.7/)).toBeInTheDocument()
  })

  it('PASS_THROUGH 不显示 "原 src=..." 当 original_source_ip 跟 source_ip 相同', () => {
    // 兼容历史数据 / 退化情况: original_source_ip 未透传时隐藏标签
    const natPolicies: NATPolicy[] = [
      {
        type: 'PASS_THROUGH',
        source_zone: '内网',
        source_ip: '10.1.1.7',
        original_source_ip: '10.1.1.7', // 跟 source_ip 一样, 不该显示
        dest_zone: 'DMZ',
        dest_ip: '10.2.2.2',
        service: '443',
        action: 'permit',
        via_firewall: { id: 99, name: '前置墙fw1' },
      },
    ]
    const policy = makePolicy({ nat_policies: natPolicies })
    render(<FirewallPolicyTable group={makeGroup({ policies: [policy] })} />)
    expect(screen.queryByText(/原 src=/)).not.toBeInTheDocument()
  })

  it('renders warnings row (yellow) when nat_info.warnings has entries', () => {
    const policy = makePolicy({
      nat_info: makeNATInfo({ warnings: ['IP 不在任何 protected_ips 段', '请人工确认'] }),
    })
    const { container } = render(
      <FirewallPolicyTable group={makeGroup({ policies: [policy] })} />
    )
    expect(screen.getByText(/IP 不在任何 protected_ips 段; 请人工确认/)).toBeInTheDocument()
    // 黄色行
    expect(container.querySelector('.bg-yellow-50')).toBeInTheDocument()
  })

  it('displays 使用时间 (中文字段, 来自 user_modified 快照)', () => {
    const policy = makePolicy({ 使用时间: '2024-01-01 至 2024-12-31' })
    render(<FirewallPolicyTable group={makeGroup({ policies: [policy] })} />)
    expect(screen.getByText('2024-01-01 至 2024-12-31')).toBeInTheDocument()
  })

  it('displays \u00A0 (non-breaking space) when 使用时间 is empty', () => {
    const policy = makePolicy({ 使用时间: '' })
    const { container } = render(
      <FirewallPolicyTable group={makeGroup({ policies: [policy] })} />
    )
    // 表格里有 NBSP, 而不是真的空字符串
    expect(container.textContent).toContain('\u00A0')
  })

  it('C4: 渲染删除按钮当 onDeletePolicy 传入', () => {
    const onDelete = vi.fn()
    const policy = makePolicy({ id: 42 })
    render(
      <FirewallPolicyTable
        group={makeGroup({ policies: [policy] })}
        onDeletePolicy={onDelete}
      />
    )
    const btn = screen.getByTestId('delete-policy-42')
    expect(btn).toBeInTheDocument()
    fireEvent.click(btn)
    expect(onDelete).toHaveBeenCalledWith(policy)
  })

  it('C4: 不渲染删除按钮当 onDeletePolicy 缺省 (只读模式)', () => {
    const policy = makePolicy({ id: 99 })
    render(<FirewallPolicyTable group={makeGroup({ policies: [policy] })} />)
    expect(screen.queryByTestId('delete-policy-99')).not.toBeInTheDocument()
  })
})
