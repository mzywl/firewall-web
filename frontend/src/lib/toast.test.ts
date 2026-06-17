// lib/toast.ts 纯函数测试
// 不依赖 DOM, 最快, 跑在最前面
import { describe, it, expect } from 'vitest'
import { extractErrorMessage } from './toast'

describe('extractErrorMessage', () => {
  it('returns fallback when err is null/undefined', () => {
    expect(extractErrorMessage(null)).toBe('操作失败')
    expect(extractErrorMessage(undefined)).toBe('操作失败')
    expect(extractErrorMessage(null, '自定义')).toBe('自定义')
  })

  it('returns fallback when err shape is unknown', () => {
    expect(extractErrorMessage('string error', 'fallback')).toBe('fallback')
    expect(extractErrorMessage(42, 'fallback')).toBe('fallback')
  })

  it('extracts string detail (FastAPI 4xx/5xx)', () => {
    const err = { response: { data: { detail: '工单不存在' } } }
    expect(extractErrorMessage(err)).toBe('工单不存在')
  })

  it('extracts array detail (FastAPI 422 validation)', () => {
    const err = {
      response: {
        data: {
          detail: [
            { msg: 'field required', loc: ['body', 'name'] },
            { msg: 'value error', loc: ['body', 'age'] },
          ],
        },
      },
    }
    expect(extractErrorMessage(err)).toBe('field required; value error')
  })

  it('skips array entries without msg', () => {
    const err = {
      response: {
        data: {
          detail: [{ loc: ['body'] }, { msg: 'has message' }],
        },
      },
    }
    expect(extractErrorMessage(err)).toBe('has message')
  })

  it('falls back to data.message when no detail', () => {
    const err = { response: { data: { message: 'server message' } } }
    expect(extractErrorMessage(err)).toBe('server message')
  })

  it('falls back to err.message when no response', () => {
    const err = new Error('network timeout')
    expect(extractErrorMessage(err)).toBe('network timeout')
  })

  it('handles empty err.message', () => {
    const err = { message: '' }
    expect(extractErrorMessage(err, 'fallback')).toBe('fallback')
  })
})
