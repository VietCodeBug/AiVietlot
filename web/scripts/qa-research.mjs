import { chromium } from '@playwright/test'
import { mkdir, writeFile } from 'node:fs/promises'
const base=process.argv[2]??'http://127.0.0.1:4173'
const browser=await chromium.launch({channel:'msedge',headless:true})
const checks=[]
const check=(condition,label)=>{if(!condition)throw new Error(label);checks.push(label)}
const context=await browser.newContext({viewport:{width:1440,height:1000}})
const page=await context.newPage(),errors=[]
page.on('pageerror',e=>errors.push(e.message))
try{
  await page.goto(base);await page.locator('.recent-row .ball').first().waitFor()
  check(await page.locator('.recent-row .ball').first().evaluate(el=>{
    const range=document.createRange();range.selectNodeContents(el);const text=range.getBoundingClientRect(),ball=el.getBoundingClientRect()
    return getComputedStyle(el).display==='grid'&&Math.abs(text.x+text.width/2-ball.x-ball.width/2)<2&&Math.abs(text.y+text.height/2-ball.y-ball.height/2)<4
  }),'Recent lottery ball text is horizontally and vertically centered')
  check(await page.locator('.recent-row .text-link').first().locator('svg').count()===1,'Source link has one arrow')
  await page.goto(base+'/lich-su')
  await page.locator('.history-row').first().waitFor()
  const latest=await page.locator('.history-date strong').first().innerText()
  await page.getByLabel('Số xuất hiện').selectOption('13')
  await page.waitForTimeout(800)
  await page.getByRole('button',{name:/^Kỳ mới nhất ·/}).click()
  await page.waitForFunction(code=>document.querySelector('.history-date strong')?.textContent===code,latest)
  check(await page.getByLabel('Số xuất hiện').inputValue()===''&&await page.locator('.history-row').count()===1,'Latest draw shortcut clears an old number filter and selects the actual newest draw')
  await page.getByRole('button',{name:'Ngày có kết quả mới nhất',exact:true}).click()
  await page.waitForTimeout(500)
  check(await page.getByLabel('Từ ngày').inputValue()===await page.getByLabel('Đến ngày').inputValue(),'Newest result date shortcut fills both date bounds')
  await page.getByRole('button',{name:'Xóa lọc',exact:true}).click()
  await page.getByLabel('Sắp xếp',{exact:true}).selectOption('asc')
  await page.waitForFunction(()=>document.querySelector('.history-date strong')?.textContent==='#00001')
  check(true,'Oldest-first ordering is applied by the database')
  await page.evaluate(()=>{document.documentElement.dataset.theme='dark';localStorage.setItem('mega-lab-theme','dark')})
  check(await page.locator('h1').evaluate(el=>{
    const parse=s=>s.match(/[\d.]+/g).slice(0,3).map(Number).map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4})
    const lum=s=>{const c=parse(s);return .2126*c[0]+.7152*c[1]+.0722*c[2]}
    const fg=lum(getComputedStyle(el).color),bg=lum(getComputedStyle(document.body).backgroundColor)
    return (Math.max(fg,bg)+.05)/(Math.min(fg,bg)+.05)>=4.5
  }),'Dark theme heading has readable contrast of at least 4.5:1')
  await page.screenshot({path:'../artifacts/web-qa/dark-history.png',fullPage:true})
  await page.goto(base+'/thi-nghiem');await page.getByRole('button',{name:'Tạo dãy thí nghiệm'}).click()
  await page.getByRole('button',{name:'Đưa vào theo dõi'}).click()
  await page.getByRole('heading',{name:'Ghi trước. Đối chiếu sau.'}).waitFor()
  await page.getByRole('heading',{name:/Kỳ theo dõi #/}).waitFor()
  check(await page.locator('.research-draft-row').count()===5,'Generated tickets transfer intact to future tracking')
  check(await page.getByRole('button',{name:/Lưu cho kỳ/}).isDisabled(),'Anonymous visitors cannot register personal research')
  await page.getByLabel('Email',{exact:true}).fill('invalid@gmailcom')
  await page.getByLabel('Mật khẩu',{exact:true}).fill('test-only-password')
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click()
  await page.getByRole('status').filter({hasText:'dấu chấm'}).waitFor()
  check(true,'Incomplete email domain is explained beside the auth form')
  await page.reload();await page.locator('.research-draft-row').first().waitFor()
  check(await page.locator('.research-draft-row').count()===5,'Unconfirmed research draft survives reload')
  if(process.env.RESEARCH_QA_EMAIL){
    await page.getByLabel('Email',{exact:true}).fill(process.env.RESEARCH_QA_EMAIL)
    await page.getByLabel('Mật khẩu',{exact:true}).fill(process.env.RESEARCH_QA_PASSWORD)
    await page.getByRole('button',{name:'Đăng nhập',exact:true}).click()
    await page.getByRole('button',{name:'Đăng xuất',exact:true}).waitFor()
    check(true,'Supabase password login succeeds through product UI')
    await page.locator('.research-draft-row').first().getByRole('checkbox').check()
    await page.getByRole('button',{name:/Lưu cho kỳ/}).click()
    await page.locator('.research-entry').first().waitFor()
    check(await page.locator('.research-entry').count()===5,'All five tickets are saved on server for one future draw')
    check(await page.locator('.research-entry input:checked').count()===1,'Selected purchased ticket persists separately')
    await page.reload();await page.locator('.research-entry').first().waitFor()
    check(await page.locator('.research-entry').count()===5,'Server tickets and auth session survive reload')
    const other=page.locator('.research-entry').filter({has:page.locator('input:not(:checked)')}).first()
    await other.getByRole('checkbox').click()
    await page.waitForFunction(()=>document.querySelectorAll('.research-entry input:checked').length===2)
    await page.getByLabel('Chỉ vé đã mua').check()
    await page.waitForFunction(()=>document.querySelectorAll('.research-entry').length===2)
    check(true,'Purchase updates and purchased-only history work')
    await page.getByText('Thêm vé tôi đã mua',{exact:true}).click()
    await page.getByLabel('Sáu số trên vé',{exact:true}).fill('01, 02, 03, 04, 05, 06')
    const targetCode=(await page.getByRole('heading',{name:/Kỳ theo dõi #/}).innerText()).match(/#(\d+)/)[1]
    await page.getByLabel('Mã kỳ trên vé',{exact:true}).fill(String(Number(targetCode)))
    await page.getByLabel('Ngày bạn đã mua',{exact:true}).fill(new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh'}).format(new Date()))
    await page.getByRole('button',{name:'Lưu vé đã mua',exact:true}).click()
    await page.getByRole('status').filter({hasText:'Đã lưu vé đã mua.'}).waitFor()
    check((await page.locator('.research-entry').allTextContents()).some(text=>text.includes('Ngày mua tự khai báo')),'Supplementary purchased ticket preserves the declared date separately from registration time')
    await page.getByRole('button',{name:'Đăng xuất',exact:true}).click()
    await page.getByRole('button',{name:'Đăng nhập',exact:true}).waitFor()
    check(await page.locator('.research-entry').count()===0,'Signing out clears private ticket content')
  }
  for(const width of [360,390,768,1440]){
    await page.setViewportSize({width,height:1000})
    check(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Research screen fits ${width}px viewport`)
  }
  await mkdir('../artifacts/web-qa',{recursive:true})
  await page.setViewportSize({width:1440,height:1000})
  await page.screenshot({path:'../artifacts/web-qa/desktop-research.png',fullPage:true})
  check(errors.length===0,'Research UI has no uncaught runtime errors')
  await writeFile('../artifacts/web-qa/research-report.json',JSON.stringify({base,checks},null,2))
  console.log(JSON.stringify({status:'passed',checks},null,2))
}finally{await browser.close()}
