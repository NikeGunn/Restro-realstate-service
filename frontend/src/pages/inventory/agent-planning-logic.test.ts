import { describe, it, expect } from 'vitest'
import { deriveStageStatus } from './agent-planning-logic'

// The Inventory AI timeline has 5 stages:
// 0 parse · 1 scan · 2 alerts · 3 movements · 4 synthesize
const TOTAL = 5

describe('deriveStageStatus', () => {
  it('marks earlier stages success, the active one active, later ones pending while planning', () => {
    // stepper at stage 2 (alerts) in flight
    expect(deriveStageStatus('planning', 2, 0, TOTAL)).toBe('success')
    expect(deriveStageStatus('planning', 2, 1, TOTAL)).toBe('success')
    expect(deriveStageStatus('planning', 2, 2, TOTAL)).toBe('active')
    expect(deriveStageStatus('planning', 2, 3, TOTAL)).toBe('pending')
    expect(deriveStageStatus('planning', 2, 4, TOTAL)).toBe('pending')
  })

  it('at the very start only the first stage is active', () => {
    expect(deriveStageStatus('planning', 0, 0, TOTAL)).toBe('active')
    expect(deriveStageStatus('planning', 0, 1, TOTAL)).toBe('pending')
  })

  it('marks every stage success once the answer is done', () => {
    for (let i = 0; i < TOTAL; i++) {
      expect(deriveStageStatus('done', TOTAL, i, TOTAL)).toBe('success')
    }
  })

  it('on error, lead-up stages succeeded and only synthesize fails', () => {
    expect(deriveStageStatus('error', TOTAL, 0, TOTAL)).toBe('success')
    expect(deriveStageStatus('error', TOTAL, 1, TOTAL)).toBe('success')
    expect(deriveStageStatus('error', TOTAL, 2, TOTAL)).toBe('success')
    expect(deriveStageStatus('error', TOTAL, 3, TOTAL)).toBe('success')
    expect(deriveStageStatus('error', TOTAL, 4, TOTAL)).toBe('error')
  })

  it('never reports active after completion (no stuck spinner in production)', () => {
    for (let i = 0; i < TOTAL; i++) {
      expect(deriveStageStatus('done', TOTAL, i, TOTAL)).not.toBe('active')
      expect(deriveStageStatus('error', TOTAL, i, TOTAL)).not.toBe('active')
    }
  })
})
