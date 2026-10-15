import { numbers, type Draw } from './analytics'

const url = (import.meta.env.VITE_SUPABASE_URL ?? '').replace(/\/$/, '')
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ?? ''
const fields = 'draw_id,draw_date,n1,n2,n3,n4,n5,n6,source_name,source_url,fetched_at,verification_status'
const CACHE_KEY = 'mega-lab-public-draws-v1'
export const configured = Boolean(url && key && !key.startsWith('sb_secret_'))

export interface DataSnapshot { draws: Draw[]; readAt: string; cached: boolean }
export interface Comparison { algorithm: string; label: string; meanMatches: number; prizeRate: number; deltaMean: number; ciLow: number; ciHigh: number; distribution: number[]; testDraws: number; tickets: number; ticketsPerDraw: number; seedCount: number }
export interface AnalysisWindow { testDraws: number; comparisons: Comparison[]; range: {first_draw_id: number; last_draw_id: number; first_date: string; last_date: string} }
export interface AnalysisRun { id: string; created_at: string; algorithm_version: string; config: Record<string, unknown>; metrics: {comparisons: Comparison[]; windows: AnalysisWindow[]; range: AnalysisWindow['range']; notes: string[]; seed: number} }

function validDraw(d: Draw): boolean {
  return Boolean(d && Number.isInteger(d.draw_id) && d.draw_id > 0 && /^\d{4}-\d{2}-\d{2}$/.test(d.draw_date)
    && Number.isFinite(Date.parse(d.draw_date)) && Number.isFinite(Date.parse(d.fetched_at))
    && typeof d.source_url === 'string' && d.source_url.startsWith('https://')
    && numbers(d).every(n => Number.isInteger(n) && n >= 1 && n <= 45) && new Set(numbers(d)).size === 6)
}

async function request(table: string, query: URLSearchParams, signal?: AbortSignal) {
  if (!configured) throw new Error('Chưa cấu hình kết nối dữ liệu. Cần URL Supabase và publishable key trong cấu hình web.')
  const response = await fetch(`${url}/rest/v1/${table}?${query}`, {
    headers: { apikey: key, Prefer: 'count=exact' }, signal,
  })
  if (!response.ok) throw new Error(response.status === 404 ? 'Chưa có bảng dữ liệu này trên server.' : 'Không đọc được dữ liệu. Vui lòng thử lại sau.')
  return response
}

export function readCached(): DataSnapshot | null {
  try {
    const cached = JSON.parse(localStorage.getItem(CACHE_KEY) ?? 'null') as DataSnapshot | null
    if (cached && Array.isArray(cached.draws) && cached.draws.length && cached.draws.every(validDraw)
      && new Set(cached.draws.map(d => d.draw_id)).size === cached.draws.length && Number.isFinite(Date.parse(cached.readAt))) return { ...cached, cached: true }
  } catch { /* Offline storage is optional. */ }
  return null
}

export async function loadDraws(): Promise<DataSnapshot> {
  const all: Draw[] = []
  let total = Infinity
  let upperBound: number | null = null
  while (all.length < total) {
    const query = new URLSearchParams({ select: fields, order: 'draw_id.desc', limit: '500', offset: String(all.length) })
    if (upperBound !== null) query.set('draw_id', `lte.${upperBound}`)
    const response = await request('mega645_draws', query)
    const chunk: Draw[] = await response.json()
    if (!Array.isArray(chunk)) throw new Error('Định dạng dữ liệu không hợp lệ.')
    if (!chunk.length) break
    if (!chunk.every(validDraw)) throw new Error('Dữ liệu có bản ghi không hợp lệ. Vui lòng kiểm tra nguồn.')
    upperBound ??= chunk[0].draw_id
    all.push(...chunk)
    const count = response.headers.get('content-range')?.split('/')[1]
    if (count && count !== '*' && Number.isFinite(Number(count))) total = Number(count)
  }
  if (!all.length) throw new Error('Chưa có kết quả quay trong database.')
  if (new Set(all.map(d => d.draw_id)).size !== all.length) throw new Error('Dữ liệu phân trang có mã kỳ trùng. Vui lòng tải lại.')
  const result: DataSnapshot = { draws: all, readAt: new Date().toISOString(), cached: false }
  try { localStorage.setItem(CACHE_KEY, JSON.stringify(result)) } catch { /* Quota or private mode: keep in memory. */ }
  return result
}

export async function loadHistory(page: number, filter: {drawId: string; number: string; from: string; to: string}, signal?: AbortSignal) {
  const params = new URLSearchParams({ select: fields, order: 'draw_id.desc', limit: '15', offset: String(page * 15) })
  if (filter.drawId) params.set('draw_id', `eq.${Number(filter.drawId)}`)
  if (filter.number) params.set('or', `(${[1, 2, 3, 4, 5, 6].map(i => `n${i}.eq.${Number(filter.number)}`).join(',')})`)
  if (filter.from) params.append('draw_date', `gte.${filter.from}`)
  if (filter.to) params.append('draw_date', `lte.${filter.to}`)
  const response = await request('mega645_draws', params, signal)
  const rows: Draw[] = await response.json()
  const count = Number(response.headers.get('content-range')?.split('/')[1])
  return { rows, total: Number.isFinite(count) ? count : rows.length }
}

export async function loadAnalysis(): Promise<AnalysisRun | null> {
  const response = await request('analysis_runs', new URLSearchParams({ select: '*', status: 'eq.succeeded', order: 'created_at.desc', limit: '1' }))
  const rows: AnalysisRun[] = await response.json()
  return rows[0] ?? null
}

export function downloadCsv(draws: Draw[]) {
  const columns = fields.split(',') as (keyof Draw)[]
  const csv = '\ufeff' + [columns.join(','), ...draws.map(d => columns.map(k => `"${String(d[k]).replaceAll('"', '""')}"`).join(','))].join('\r\n')
  const objectUrl = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a'); anchor.href = objectUrl; anchor.download = `mega645-${new Date().toISOString().slice(0, 10)}.csv`; anchor.click()
  setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

export function clearPublicCache() { localStorage.removeItem(CACHE_KEY) }
