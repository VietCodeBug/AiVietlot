import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { addPurchaseReport, claimPurchaseReport, getPurchaseReports, readPurchaseClaim, type PurchaseReport, type ResearchTarget } from '../lib/research'
import { Balls, Card, SectionTitle, SourceLink } from './ui'
import { dateLabel, drawCode, timeLabel } from '../lib/format'

export function PurchaseReports({target}:{target:ResearchTarget|null}) {
  const [rows,setRows]=useState<PurchaseReport[]>([]),[error,setError]=useState(''),[message,setMessage]=useState(''),[busy,setBusy]=useState(false)
  const [claim,setClaim]=useState(readPurchaseClaim)
  const [values,setValues]=useState(''),[draw,setDraw]=useState(''),[date,setDate]=useState(''),[note,setNote]=useState('')
  const refresh=useCallback(async()=>{setRows(await getPurchaseReports())},[])
  useEffect(()=>{let active=true;const load=()=>void getPurchaseReports().then(data=>{if(active)setRows(data)}).catch(e=>{if(active)setError(e.message)});load();const timer=setInterval(load,60000);return()=>{active=false;clearInterval(timer)}},[])
  const save=(event:FormEvent)=>{event.preventDefault();setError('');setMessage('');setBusy(true);void(async()=>{
    try{const numbers=values.trim().split(/[\s,;–-]+/).map(Number).sort((a,b)=>a-b)
      if(numbers.length!==6||new Set(numbers).size!==6||numbers.some(n=>!Number.isInteger(n)||n<1||n>45))throw new Error('Nhập đúng 6 số khác nhau từ 1 đến 45.')
      await addPurchaseReport(Number(draw),numbers,date,note);await refresh();setValues('');setMessage('Đã lưu vé đã mua. Ngày bạn khai báo và thời điểm nhập được giữ riêng.')
    }catch(e){setError(e instanceof Error?e.message:'Không lưu được vé.')}finally{setBusy(false)}
  })()}
  return <Card><SectionTitle title="Vé đã mua · khai báo bổ sung"/><p className="muted">Nhập vé mua trước khi dùng sổ này. Hệ thống tự đối chiếu đúng kỳ và giữ ngày mua bạn khai báo; các vé bổ sung không tính vào thống kê dự đoán đăng ký trước kỳ.</p>
    {claim&&<div className="banner"><span>Có vé đã mua được chuẩn bị từ cuộc trò chuyện.</span><button disabled={busy} onClick={()=>{setBusy(true);void claimPurchaseReport(claim).then(async()=>{setClaim(null);await refresh();setMessage('Đã nhận vé vào tài khoản này.')}).catch(e=>setError(e.message)).finally(()=>setBusy(false))}}>Nhận vé vào tài khoản này</button></div>}
    {error&&<p className="form-error" role="alert">{error}</p>}{message&&<p role="status">{message}</p>}
    <details className="research-import"><summary>Thêm vé tôi đã mua</summary><form className="research-import" onSubmit={save}><label>Sáu số trên vé<input value={values} onChange={e=>setValues(e.target.value)} placeholder="Ví dụ: 01, 09, 17, 25, 33, 45" required/></label><div className="form-two"><label>Mã kỳ trên vé<input type="number" min="1" value={draw} onChange={e=>setDraw(e.target.value)} required/></label><label>Ngày bạn đã mua<input type="date" value={date} onChange={e=>setDate(e.target.value)} required/></label></div>{target&&<p className="input-help">Kết quả mới nhất: {drawCode(target.latest_draw_id)} ngày {dateLabel(target.latest_draw_date)}. Kỳ sắp tới: {drawCode(target.target_draw_id)} ngày dự kiến {dateLabel(target.planned_date)}. Chọn đúng mã trên vé.</p>}<label>Ghi chú<input maxLength={2000} value={note} onChange={e=>setNote(e.target.value)}/></label><button className="button primary" disabled={busy}>{busy?'Đang lưu…':'Lưu vé đã mua'}</button></form></details>
    {!rows.length?<p className="input-help">Chưa có vé khai báo bổ sung.</p>:<div className="research-ticket-list">{rows.map(row=><article className="research-entry" key={row.id}><div className="research-entry-top"><strong>{row.target_draw_id?drawCode(row.target_draw_id):'Chờ xác định kỳ'}</strong><span className="pill neutral">Đã mua · {row.actual_numbers?`Khớp ${row.matched_numbers?.length??0}/6`:'Chờ kết quả'}</span></div><Balls small values={row.numbers} matched={row.matched_numbers??[]}/><p className="input-help">Ngày mua tự khai báo: {dateLabel(row.reported_purchase_date)} · Nhập thực tế: {timeLabel(row.recorded_at)}.</p>{row.note&&<p>{row.note}</p>}{row.actual_numbers&&<div className="research-outcome"><span>Kết quả ngày {dateLabel(row.draw_date!)}</span><Balls small values={row.actual_numbers} matched={row.matched_numbers??[]}/>{row.source_url&&<SourceLink url={row.source_url}>Nguồn kết quả</SourceLink>}</div>}<p className="input-help">Khai báo bổ sung, không phải bằng chứng đã đăng ký dự đoán trước kỳ quay.</p></article>)}</div>}
  </Card>
}
