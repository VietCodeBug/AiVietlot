import type { ResearchEntry } from './research'

export interface ResearchMetrics {
  tickets: number; draws: number; distribution: number[]; baselineDistribution: number[];
  matches: number; baselineMatches: number; hitRate: number; baselineHitRate: number;
  delta: number; interval: [number,number]|null; excludedTiming: number
}

/** Resample entire draw clusters, retaining pairing and all misses. */
export function researchMetrics(entries: ResearchEntry[], purchasedOnly: boolean): ResearchMetrics {
  const selected=entries.filter(e=>!purchasedOnly||e.purchased)
  const evaluated=selected.filter(e=>e.outcome?.timing_status==='prospective')
  const distribution=Array<number>(7).fill(0),baselineDistribution=Array<number>(7).fill(0)
  const groups=new Map<number,{tickets:number;hits:number;baseline:number}>()
  for(const entry of evaluated){
    const out=entry.outcome!;distribution[out.match_count]++;baselineDistribution[out.baseline_match_count]++
    const group=groups.get(entry.target_draw_id)??{tickets:0,hits:0,baseline:0};group.tickets++
    group.hits+=Number(out.match_count>=3);group.baseline+=Number(out.baseline_match_count>=3);groups.set(entry.target_draw_id,group)
  }
  const tickets=evaluated.length,hits=distribution.slice(3).reduce((a,b)=>a+b,0),baseHits=baselineDistribution.slice(3).reduce((a,b)=>a+b,0)
  let interval:[number,number]|null=null
  if(groups.size>=2){
    let state=20261015;const random=()=>{state=(Math.imul(1664525,state)+1013904223)>>>0;return state/4294967296}
    const clusters=[...groups.values()],deltas=[]
    for(let i=0;i<1000;i++){let n=0,a=0,b=0;for(let j=0;j<clusters.length;j++){const g=clusters[Math.floor(random()*clusters.length)];n+=g.tickets;a+=g.hits;b+=g.baseline}deltas.push((a-b)/n)}
    deltas.sort((a,b)=>a-b);interval=[deltas[24],deltas[974]]
  }
  return {tickets,draws:groups.size,distribution,baselineDistribution,matches:hits,baselineMatches:baseHits,
    hitRate:tickets?hits/tickets:0,baselineHitRate:tickets?baseHits/tickets:0,delta:tickets?(hits-baseHits)/tickets:0,
    interval,excludedTiming:selected.filter(e=>e.outcome?.timing_status==='invalid_timing').length}
}
