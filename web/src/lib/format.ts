export const integer = (n: number) => n.toLocaleString('vi-VN')
export const ballNumber = (n: number) => String(n).padStart(2, '0')
export const drawCode = (n: number) => `#${String(n).padStart(5, '0')}`
export const dateLabel = (s: string, short = false) => new Intl.DateTimeFormat('vi-VN', { day: '2-digit', month: '2-digit', ...(short ? {} : {year: 'numeric'}), timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(s.includes('T') ? s : s + 'T00:00:00+07:00'))
export const timeLabel = (s: string) => new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(s))
export const percent = (n: number, decimals = 2) => `${(n * 100).toLocaleString('vi-VN', { maximumFractionDigits: decimals, minimumFractionDigits: decimals })}%`

/** A scheduled date is used only to flag potentially stale data, never to invent a result. */
export function needsUpdate(latest: string): boolean {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hourCycle: 'h23' }).formatToParts(new Date())
  const get = (type: string) => parts.find(p => p.type === type)?.value ?? ''
  const day = new Date(`${get('year')}-${get('month')}-${get('day')}T00:00:00Z`)
  if (Number(get('hour')) < 19) day.setUTCDate(day.getUTCDate() - 1)
  while (![0, 3, 5].includes(day.getUTCDay())) day.setUTCDate(day.getUTCDate() - 1)
  return latest < day.toISOString().slice(0, 10)
}
