const base = process.argv[2] ?? 'https://mega-lab-iota.vercel.app'
const paths = [
  ['/', 200, 'text/html'], ['/lich-su', 200, 'text/html'], ['/thong-ke', 200, 'text/html'],
  ['/thi-nghiem', 200, 'text/html'], ['/kiem-thu', 200, 'text/html'], ['/cai-dat', 200, 'text/html'],
  ['/manifest.webmanifest', 200, 'application/manifest+json'], ['/icon-192.png', 200, 'image/png'],
  ['/icon-512.png', 200, 'image/png'], ['/sw.js', 200, 'javascript'], ['/assets/nonexistent-test.js', 404, null],
]
for (const [path, status, content] of paths) {
  const response = await fetch(base + path)
  if (response.status !== status || (content && !response.headers.get('content-type')?.includes(content))) throw new Error(`Unexpected response for ${path}: ${response.status} ${response.headers.get('content-type')}`)
  console.log(`PASS ${path} ${response.status}`)
}
