import { chromium } from '@playwright/test'
import { readFile, writeFile, mkdir } from 'node:fs/promises'

const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const svg = await readFile(new URL('../public/favicon.svg', import.meta.url), 'utf8')
  for (const size of [192, 512]) {
    const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 })
    await page.setContent(`<style>html,body{margin:0;width:100%;height:100%;overflow:hidden}svg{width:100%;height:100%}</style>${svg}`)
    await page.screenshot({ path: new URL(`../public/icon-${size}.png`, import.meta.url).pathname.replace(/^\/(\w:)/, '$1'), omitBackground: true })
    await page.close()
  }
} finally { await browser.close() }

// Self-host the actual Vietnamese font subsets; no font request is needed at runtime.
const response = await fetch('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap', { headers: { 'user-agent': 'Mozilla/5.0' } })
if (!response.ok) throw new Error('Font stylesheet could not be fetched')
let css = await response.text()
await mkdir(new URL('../public/fonts', import.meta.url), { recursive: true })
const urls = [...new Set([...css.matchAll(/url\((https:[^)]+)\)/g)].map(match => match[1]))]
for (let i = 0; i < urls.length; i++) {
  const font = await fetch(urls[i]); if (!font.ok) throw new Error('Font subset could not be fetched')
  const ext = urls[i].split('.').pop().split('?')[0]
  const filename = `be-vietnam-pro-${i}.${ext}`
  await writeFile(new URL(`../public/fonts/${filename}`, import.meta.url), Buffer.from(await font.arrayBuffer()))
  css = css.replaceAll(urls[i], `/fonts/${filename}`)
}
await writeFile(new URL('../src/fonts.css', import.meta.url), css)
console.log(`Prepared two app icons and ${urls.length} self-hosted font files.`)
