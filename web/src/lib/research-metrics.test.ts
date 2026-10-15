import { describe, expect, it } from 'vitest'
import { researchMetrics } from './research-metrics'
import { inputFingerprint, type ResearchEntry } from './research'
import type { Draw } from './analytics'

const entry=(draw:number,hit:number,baseline:number,purchased=true,timing='prospective')=>({target_draw_id:draw,purchased,outcome:{match_count:hit,baseline_match_count:baseline,timing_status:timing}} as ResearchEntry)
describe('prospective research accounting',()=>{
  it('keeps misses and pairs the same purchased cohort with its baseline',()=>{
    const rows=[entry(1,3,0),entry(1,0,3),entry(2,0,0,false),entry(2,6,0,true,'invalid_timing')]
    const all=researchMetrics(rows,false),bought=researchMetrics(rows,true)
    expect(all.tickets).toBe(3);expect(all.draws).toBe(2);expect(all.distribution[0]).toBe(2)
    expect(all.excludedTiming).toBe(1);expect(bought.tickets).toBe(2);expect(bought.hitRate).toBe(.5)
    expect(bought.baselineHitRate).toBe(.5);expect(bought.interval).toBeNull()
  })
  it('bootstraps paired draw clusters reproducibly and handles no results',()=>{
    const rows=[entry(1,3,0),entry(1,0,0),entry(2,0,3)]
    expect(researchMetrics(rows,false)).toEqual(researchMetrics(rows,false))
    expect(researchMetrics(rows,false).interval).not.toBeNull()
    expect(researchMetrics([],false)).toMatchObject({tickets:0,draws:0,delta:0,interval:null})
  })
  it('hashes the same canonical ascending rows regardless of fetch order',async()=>{
    const a={draw_id:1,draw_date:'2026-10-11',n1:1,n2:2,n3:3,n4:4,n5:5,n6:6} as Draw
    const b={...a,draw_id:2,draw_date:'2026-10-14'}
    const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode('1|2026-10-11|1,2,3,4,5,6\n2|2026-10-14|1,2,3,4,5,6'))
    const expected=Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('')
    expect(await inputFingerprint([b,a])).toBe(expected)
    expect(await inputFingerprint([a,b])).toBe(expected)
  })
})
