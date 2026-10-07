import { createRequire } from 'node:module'
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import assert from 'node:assert/strict'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright')
const root = fileURLToPath(new URL('../', import.meta.url))
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:4179/'
mkdirSync(`${root}/review/screenshots`, {recursive:true})
const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_BINARY, args:['--disable-gpu']})
let page = await browser.newPage({viewport:{width:1440,height:1050}})
const errors = [], network = []
page.on('pageerror', e => errors.push(e.message))
page.on('request', r => network.push(r.url()))
await page.addInitScript(() => {
  window.__calls = []
  let bridge
  Object.defineProperty(window, 'codexProxyPlugin', {configurable:true, get:()=>bridge, set(value) {
    bridge = {...value, request(input) { window.__calls.push(input); return value.request(input) }}
  }})
})
async function load(query = '') {
  await page.goto(`${base}?preview=1${query}`)
  await page.getByRole('button', {name:'检查 Meow 更新',exact:true}).waitFor()
  assert.equal(await page.evaluate(()=>window.__calls.filter(c=>c.path==='api/upstreams/check').length),0)
}
async function shot(name) {
  await page.waitForTimeout(300)
  await page.screenshot({path:`${root}/review/screenshots/${name}.png`,fullPage:true,animations:'disabled'})
}
async function select(label, option) {
  const trigger = page.getByRole('combobox', {name:label,exact:true})
  await trigger.click()
  const id = await trigger.getAttribute('aria-controls')
  await page.locator(`[id="${id}"]`).getByRole('option', {name:option,exact:true}).click()
}
try {
  await load()
  const boot = await page.evaluate(async()=>JSON.parse(new TextDecoder().decode((await window.codexProxyPlugin.request({method:'GET',path:'api/bootstrap'})).body)))
  const theme = await page.evaluate(()=>({css:document.querySelector('[data-cp-runtime-theme]').textContent,name:document.documentElement.dataset.theme,color:document.documentElement.dataset.themeColor}))
  assert.equal(await page.getByRole('textbox',{name:'Meow GitHub 地址',exact:true}).inputValue(),boot.sources[0].url)
  assert.equal(await page.getByRole('textbox',{name:'ModelTrace GitHub 地址',exact:true}).inputValue(),boot.sources[1].url)
  await shot('updates-idle')
  for (const name of ['Meow','ModelTrace']) await page.getByRole('button',{name:`检查 ${name} 更新`,exact:true}).click()
  await page.locator('.source-result-identical').nth(1).waitFor()
  assert.equal(await page.getByText('与内置提交一致',{exact:true}).count(),2)
  await shot('updates-current')
  for (const status of ['ahead','behind','diverged']) {
    await load(`&updates=${status}`)
    await page.getByRole('button',{name:'检查 Meow 更新',exact:true}).click()
    await page.locator(`.source-result-${status}`).waitFor()
    const url = await page.getByRole('textbox',{name:'Meow 提交差异地址',exact:true}).inputValue()
    assert.equal(url,`${boot.sources[0].url}/compare/${boot.sources[0].bundled_commit}...${'a'.repeat(40)}`)
    assert.equal(await page.getByRole('button',{name:'立即更新',exact:true}).count(),0)
    await shot(`updates-${status}`)
  }
  await load('&updates=slow')
  await page.getByRole('button',{name:'检查 Meow 更新',exact:true}).click()
  assert.equal(await page.getByRole('button',{name:'检查 Meow 更新',exact:true}).isDisabled(),true)
  assert.equal(await page.getByRole('button',{name:'检查 ModelTrace 更新',exact:true}).isDisabled(),false)
  await shot('updates-checking')
  await page.locator('.source-result-identical').waitFor()
  assert.equal(await page.evaluate(()=>window.__calls.filter(c=>c.path==='api/upstreams/check').length),1)
  await load('&updates=error')
  await page.getByRole('button',{name:'检查 Meow 更新',exact:true}).click()
  await page.getByRole('alert').filter({hasText:'HTTP 403'}).waitFor()
  await page.getByRole('button',{name:'检查 ModelTrace 更新',exact:true}).click()
  await page.locator('.source-result-identical').waitFor()
  await select('检测账号','主账号 A · 固定代理')
  await select('计量 Key','模型体检专用')
  await select('请求模型','gpt-6-astra')
  await select('对照基线','gpt-6-astra')
  assert.equal(await page.getByRole('button',{name:'开始检测',exact:true}).isDisabled(),false)
  await shot('updates-error-isolated')
  await page.getByRole('radio',{name:'ModelTrace',exact:true}).click()
  await page.getByRole('button',{name:'开始检测',exact:true}).click()
  await page.waitForFunction(()=>document.querySelector('progress')?.value===3)
  await page.getByRole('button',{name:'当前题完成后暂停',exact:true}).waitFor({state:'hidden'})
  assert.equal(await page.getByText('更接近 gpt-6-astra',{exact:true}).count(),2)
  await load('&updates=ahead&theme=dark')
  await page.getByRole('button',{name:'检查 Meow 更新',exact:true}).click()
  await page.locator('.source-result-ahead').waitFor()
  await shot('updates-dark')
  await page.setViewportSize({width:390,height:844})
  await shot('updates-mobile-dark')
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false)
  await load('&updates=diverged')
  await page.getByRole('button',{name:'检查 ModelTrace 更新',exact:true}).click()
  await page.locator('.source-result-diverged').waitFor()
  await shot('updates-mobile-light')
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false)

  // 使用生产 IIFE 和与宿主一致的 sandbox/CSP；不依赖预览页的同源或剪贴板权限。
  await page.close()
  page = await browser.newPage({viewport:{width:1440,height:1050}})
  page.on('pageerror',e=>errors.push(e.message))
  page.on('request',r=>network.push(r.url()))
  const fixture = `${base}__sandbox_fixture__`
  await page.route(fixture,route=>route.fulfill({contentType:'text/html',body:'<!doctype html><html></html>'}))
  await page.goto(fixture)
  const js = readFileSync(`${root}/frontend/dist/app.js`,'utf8')
  const css = readFileSync(`${root}/frontend/dist/app.css`,'utf8')
  assert(!js.includes('preview-request-'))
  const csp = "default-src 'none'; script-src 'unsafe-inline' data:; style-src 'unsafe-inline' data:; img-src data:; font-src data:; media-src data:; connect-src 'none'; worker-src 'none'; child-src 'none'; frame-src 'none'; object-src 'none'; manifest-src 'none'; base-uri 'none'; form-action 'none'"
  const mock = `document.documentElement.dataset.theme=${JSON.stringify(theme.name)};document.documentElement.dataset.themeColor=${JSON.stringify(theme.color)};delete window.codexProxyPlugin;window.__calls=[];window.codexProxyPlugin={version:2,async request(input){window.__calls.push(input);let value;
    if(input.path==='api/bootstrap')value=${JSON.stringify(boot)};
    else if(input.path==='api/runs')value={runs:[]};
    else if(input.path==='api/upstreams/check'){const source=${JSON.stringify(boot.sources)}.find(s=>s.method===JSON.parse(input.body).method);value={check:{method:source.method,status:'identical',checked_at:Date.now(),latest_commit:source.bundled_commit,ahead_by:0,behind_by:0,compare_url:source.url}}}
    else throw Error('unexpected sandbox request');
    return{status:200,contentType:'application/json',body:new TextEncoder().encode(JSON.stringify(value)).buffer}}};`
  const srcdoc = `<html><head><meta http-equiv="Content-Security-Policy" content="${csp}"><style>${css}</style><style>${theme.css}</style></head><body style="padding:24px;background:var(--cp-color-bg-layout)"><div id="app"></div><script>${mock}</script><script>${js.replaceAll('</script','<\\/script')}</script></body></html>`
  await page.setContent('<iframe title="Plugin sandbox" sandbox="allow-scripts" style="border:0;width:100%;height:1000px"></iframe><textarea aria-label="粘贴验收"></textarea>')
  await page.locator('iframe').evaluate((frame, content)=>{frame.srcdoc=content},srcdoc)
  const frame = page.frameLocator('iframe')
  await frame.getByRole('button',{name:'检查 Meow 更新',exact:true}).waitFor()
  assert.equal(await frame.locator('html').evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--cp-color-primary').trim().length>0),true)
  assert.deepEqual(await frame.locator('html').evaluate(()=>window.__calls.map(c=>c.path)),['api/bootstrap','api/runs'])
  await frame.getByRole('button',{name:'复制 Meow 地址',exact:true}).click()
  await frame.getByText('已复制',{exact:true}).waitFor()
  await page.getByRole('textbox',{name:'粘贴验收',exact:true}).focus()
  await page.keyboard.press(process.platform==='darwin'?'Meta+V':'Control+V')
  assert.equal(await page.getByRole('textbox',{name:'粘贴验收',exact:true}).inputValue(),boot.sources[0].url)
  await frame.getByRole('button',{name:'检查 ModelTrace 更新',exact:true}).click()
  await frame.getByText('与内置提交一致',{exact:true}).waitFor()
  await frame.getByRole('textbox',{name:'ModelTrace GitHub 地址',exact:true}).click()
  assert.equal(await frame.getByRole('textbox',{name:'ModelTrace GitHub 地址',exact:true}).evaluate(e=>e.selectionEnd-e.selectionStart),boot.sources[1].url.length)
  await shot('updates-production-sandbox')
  await frame.locator('html').evaluate(()=>{document.execCommand=()=>false})
  await frame.getByRole('button',{name:'复制 ModelTrace 地址',exact:true}).click()
  await frame.getByText('地址已选中，请手动复制',{exact:true}).waitFor()
  assert.equal(await frame.getByRole('textbox',{name:'ModelTrace GitHub 地址',exact:true}).evaluate(e=>e.selectionEnd-e.selectionStart),boot.sources[1].url.length)
  assert.equal(network.filter(url=>!url.startsWith(base) && !url.startsWith('data:')).length,0,'UI must only use the host bridge')
  assert.deepEqual(errors,[])
  const result = 'UPDATES BROWSER PASS: idle/current/ahead/behind/diverged/loading/error-isolation/dark/mobile PASS; sandbox=allow-scripts; production_copy=PASS; direct_http=0; console_errors=0; page_overflow=0\n'
  writeFileSync(`${root}/review/UPDATES-BROWSER-QA.txt`,result)
  console.log(result.trim())
} finally { await browser.close() }
