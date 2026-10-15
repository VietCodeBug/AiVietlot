"""Import an explicitly requested self-report without inventing a pre-draw timestamp."""
import argparse,json
from pathlib import Path
from dotenv import load_dotenv
import psycopg
from migrate import ROOT,connection_options
parser=argparse.ArgumentParser()
parser.add_argument('--draw',type=int,required=True)
parser.add_argument('--numbers',nargs=6,type=int,required=True)
parser.add_argument('--purchase-date',required=True)
args=parser.parse_args()
load_dotenv(ROOT/'.env',encoding='utf-8-sig')
with psycopg.connect(**connection_options()) as connection:
 assert connection.execute('select public.mega_numbers_valid(%s)',(sorted(args.numbers),)).fetchone()[0]
 assert connection.execute('select exists(select 1 from public.mega645_draws where draw_id=%s) or exists(select 1 from public.research_targets where target_draw_id=%s)',(args.draw,args.draw)).fetchone()[0]
 row=connection.execute("""insert into public.research_purchase_reports(claim_email,target_draw_id,numbers,reported_purchase_date,note)
 values('',%s,%s,%s,'Người dùng khai báo trong cuộc trò chuyện: đã mua cho kỳ này. Chưa có bằng chứng thời điểm tạo dãy trước khi nhập sổ.')
 on conflict(claim_email,target_draw_id,numbers) do update set note=research_purchase_reports.note
 returning id,target_draw_id,numbers,reported_purchase_date,recorded_at""",(args.draw,sorted(args.numbers),args.purchase_date)).fetchone()
 result=dict(zip(('id','target_draw_id','numbers','reported_purchase_date','recorded_at'),row))
 result['claim_url']='https://mega-lab-iota.vercel.app/theo-doi?nhan-ve='+str(row[0])
 Path('artifacts/requested-purchase-report.json').write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(result,default=str,ensure_ascii=False))
