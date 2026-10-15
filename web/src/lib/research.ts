import { createClient, type Session } from '@supabase/supabase-js'
import { numbers, type Algorithm, type Draw } from './analytics'

const projectUrl = import.meta.env.VITE_SUPABASE_URL ?? ''
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? ''
export const researchClient = projectUrl && publishableKey && !publishableKey.startsWith('sb_secret_')
  ? createClient(projectUrl, publishableKey, { auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } }) : null
export type { Session }

export interface ResearchGeneration {
  seed: string; algorithm: Algorithm; lastDraw: number; firstDraw: number; scope: number;
  inputCount: number; halfLife: number; smoothing: number; inputHash: string; algorithmVersion: string
}
export interface ResearchTarget {
  target_draw_id: number; planned_date: string; cutoff_at: string; schedule_status: 'planned'|'confirmed';
  latest_draw_id: number; latest_draw_date: string; server_now: string; accepting_entries: boolean
}
export interface ResearchOutcome {
  prediction_id: string; draw_id: number; draw_date: string; actual_numbers: number[]; matched_numbers: number[];
  match_count: number; baseline_matched_numbers: number[]; baseline_match_count: number;
  timing_status: 'prospective'|'invalid_timing'; result_source_name: string; result_source_url: string;
  result_verification_status: string; compared_at: string; revision: number
}
export interface ResearchEntry {
  id: string; target_draw_id: number; numbers: number[]; baseline_numbers: number[]; algorithm: Algorithm|'manual';
  algorithm_version: string; seed: string; config: Record<string, unknown>; created_at: string;
  purchased: boolean; purchased_at: string|null; first_draw_id: number; last_draw_id: number; input_hash: string;
  input_count: number; target: {planned_date: string; cutoff_at: string; schedule_status: string}; outcome: ResearchOutcome|null
}
export interface ResearchDraft { version: 1; tickets: number[][]; generation: ResearchGeneration }
const DRAFT_KEY = 'mega-lab-research-draft-v1'

export async function inputFingerprint(draws: Draw[]): Promise<string> {
  const canonical = [...draws].sort((a,b)=>a.draw_id-b.draw_id)
    .map(d=>`${d.draw_id}|${d.draw_date}|${numbers(d).join(',')}`).join('\n')
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical))
  return Array.from(new Uint8Array(digest), n=>n.toString(16).padStart(2,'0')).join('')
}
export function saveResearchDraft(tickets: number[][], generation: ResearchGeneration) {
  sessionStorage.setItem(DRAFT_KEY, JSON.stringify({version:1,tickets,generation}))
}
export function readResearchDraft(): ResearchDraft|null {
  try { const value=JSON.parse(sessionStorage.getItem(DRAFT_KEY)??'null') as ResearchDraft|null;
    return value?.version===1 && Array.isArray(value.tickets) && value.tickets.length && value.generation?.inputHash ? value : null
  } catch { return null }
}
export function clearResearchDraft() { sessionStorage.removeItem(DRAFT_KEY) }

export interface PurchaseReport {
  id:string;target_draw_id:number|null;numbers:number[];reported_purchase_date:string;recorded_at:string;note:string;
  draw_date:string|null;actual_numbers:number[]|null;matched_numbers:number[]|null;source_url:string|null
}
export async function getPurchaseReports():Promise<PurchaseReport[]> {
  if(!researchClient)throw new Error('Chưa cấu hình kết nối.')
  const {data,error}=await researchClient.rpc('get_purchase_reports')
  if(error)throw new Error(error.message)
  return data??[]
}
export async function addPurchaseReport(drawId:number,values:number[],purchaseDate:string,note:string) {
  if(!researchClient)throw new Error('Chưa cấu hình kết nối.')
  const {error}=await researchClient.rpc('add_purchase_report',{p_target_draw_id:drawId,p_numbers:values,p_purchase_date:purchaseDate,p_note:note})
  if(error)throw new Error(error.message)
}
const CLAIM_KEY='mega-lab-purchase-claim'
export function readPurchaseClaim():string|null {
  const token=new URL(location.href).searchParams.get('nhan-ve')??sessionStorage.getItem(CLAIM_KEY)
  if(!token||!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(token))return null
  sessionStorage.setItem(CLAIM_KEY,token);return token
}
export async function claimPurchaseReport(id:string) {
  if(!researchClient)throw new Error('Chưa cấu hình kết nối.')
  const {error}=await researchClient.rpc('claim_purchase_report',{p_report_id:id})
  if(error)throw new Error(error.message)
  sessionStorage.removeItem(CLAIM_KEY)
  const url=new URL(location.href);url.searchParams.delete('nhan-ve');history.replaceState({},'',url.pathname+url.search)
}

export async function getResearchTarget(): Promise<ResearchTarget> {
  if (!researchClient) throw new Error('Chưa cấu hình Supabase.')
  const {data,error}=await researchClient.rpc('get_research_target')
  if(error) throw new Error(error.message)
  return data as ResearchTarget
}

export async function getResearchEntries(serverNow: string): Promise<ResearchEntry[]> {
  if(!researchClient) throw new Error('Chưa cấu hình Supabase.')
  const entries: ResearchEntry[]=[]
  for(let offset=0;;offset+=500){
    const {data,error}=await researchClient.from('research_predictions')
      .select('*,research_targets(planned_date,cutoff_at,schedule_status),research_outcomes(*)')
      .lte('created_at',serverNow).order('created_at',{ascending:false}).order('id',{ascending:true}).range(offset,offset+499)
    if(error)throw new Error(error.message)
    for(const row of data??[]){
      const outcome=Array.isArray(row.research_outcomes)?row.research_outcomes[0]:row.research_outcomes
      entries.push({...row,target:row.research_targets,outcome:outcome??null} as ResearchEntry)
    }
    if((data?.length??0)<500)break
  }
  return entries
}

export async function registerDraft(draft: ResearchDraft,target: ResearchTarget,purchased: Set<number>) {
  if(!researchClient) throw new Error('Chưa cấu hình Supabase.')
  if(!navigator.onLine)throw new Error('Cần kết nối mạng để xác nhận đã lưu trên server.')
  const g=draft.generation
  const {data,error}=await researchClient.rpc('register_research_tickets',{
    p_target_draw_id:target.target_draw_id,
    p_tickets:draft.tickets.map((ticket,i)=>({numbers:ticket,purchased:purchased.has(i)})),
    p_algorithm:g.algorithm,p_algorithm_version:g.algorithmVersion,p_seed:g.seed,
    p_config:{scope:g.scope,halfLife:g.halfLife,smoothing:g.smoothing,inputCount:g.inputCount,inputHashEncoding:'rows-asc-v1'},
    p_first_draw_id:g.firstDraw,p_last_draw_id:g.lastDraw,p_input_hash:g.inputHash,
  })
  if(error)throw new Error(error.message)
  return data as ResearchEntry[]
}

export async function setResearchPurchase(id: string,purchased: boolean) {
  if(!researchClient)throw new Error('Chưa cấu hình Supabase.')
  if(!navigator.onLine)throw new Error('Cần kết nối mạng để lưu dấu đã mua.')
  const {error}=await researchClient.rpc('set_research_purchase',{p_prediction_id:id,p_purchased:purchased})
  if(error)throw new Error(error.message)
}
