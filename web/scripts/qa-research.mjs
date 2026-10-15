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
  await page.goto(base+'/thi-nghiem');await page.getByRole('button',{name:'Tạo dãy thí nghiệm'}).click()
  await page.getByRole('button',{name:'Đưa vào theo dõi'}).click()
  await page.getByRole('heading',{name:'Ghi trước. Đối chiếu sau.'}).waitFor()
  await page.getByRole('heading',{name:/Kỳ theo dõi #/}).waitFor()
  check(await page.locator('.research-draft-row').count()===5,'Generated tickets transfer intact to future tracking')
  check(await page.getByRole('button',{name:/Lưu cho kỳ/}).isDisabled(),'Anonymous visitors cannot register personal research')
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
