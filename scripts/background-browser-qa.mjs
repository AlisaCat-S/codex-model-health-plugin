// UI contract test. The mock host and its clock live in Node, not in the page.
// Real maintenance execution is exercised by backend/tests/support/background.rs.
import { createRequire } from 'node:module'
import assert from 'node:assert/strict'
import { mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const { chromium } = require(process.env.PLAYWRIGHT_PATH || 'playwright')
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:4175/'
const root = fileURLToPath(new URL('../', import.meta.url))
mkdirSync(`${root}/review/screenshots`, { recursive: true })
const browser = await chromium.launch({headless:true, executablePath:process.env.CHROME_BINARY})
let clock
try {
  const seedPage = await browser.newPage()
  await seedPage.goto(`${base}?preview=1`)
  await seedPage.getByRole('heading', {name:'任务列表', exact:true}).waitFor()
  const { boot, seed } = await seedPage.evaluate(async () => {
    const read = async(path, body) => JSON.parse(new TextDecoder().decode((await window.codexProxyPlugin.request({path:`api/${path}`,method:body?'POST':'GET',...(body?{body:JSON.stringify(body),contentType:'application/json'}:{})})).body))
    return { boot:await read('bootstrap'), seed:(await read('runs/get',{id:'0-1'})).run }
  })
  await seedPage.close()
  const runs = [], calls = [], errors = []
  let offline = false, holdId, release, held = false
  clock = setInterval(() => {
    const r = runs.find(r=>r.queued_at!=null && ['ready','running'].includes(r.status))
    if (!r) return
    const i = r.attempts.length
    r.attempts.push({job_id:`probe-${i}`,status:'ok',answer:'cat',request_id:`mock-${i}`})
    r.report.valid_samples = r.attempts.length
    r.updated_at = Date.now()
    r.status = r.attempts.length===r.plan.jobs.length ? 'completed' : 'running'
    r.inflight = r.status==='running' ? `probe-${i+1}` : null
    if (r.status==='completed') r.queued_at=null
  }, 700)
  const context = await browser.newContext({viewport:{width:1440,height:1050}})
  await context.exposeBinding('__taskHost', async(_, input) => {
    calls.push(input.path)
    const data = input.body ? JSON.parse(input.body) : {}
    let value
    if (offline && ['api/runs','api/runs/get'].includes(input.path)) throw new Error('fixture disconnected')
    if (input.path==='api/bootstrap') value=boot
    else if (input.path==='api/models') value={models:['gpt-6-astra']}
    else if (input.path==='api/runs/start') {
      assert.equal(data.background,true)
      const r=structuredClone(seed)
      Object.assign(r,{id:`1-${Date.now()}`,account_name:'primary@example.com',created_at:Date.now(),status:'ready',background:true,queued_at:Date.now(),inflight:null,attempts:[]})
      r.plan.jobs=Array.from({length:16},(_,i)=>({job_id:`probe-${i}`}))
      r.report.valid_samples=0
      runs.push(r); value={run:r}
    } else if (input.path==='api/runs') value={runs:[...runs].reverse().map(r=>({...r,method:r.plan.method,tier:r.plan.tier,request_model:r.plan.request_model,claimed_model:r.plan.claimed_model,attempts:r.attempts.length,planned:r.plan.jobs.length}))}
    else if (input.path==='api/runs/get') {
      value={run:structuredClone(runs.find(r=>r.id===data.id))}
      if (holdId===data.id) {
        held=true; holdId=undefined
        await new Promise(resolve=>{release=resolve})
      }
    } else throw new Error(`unexpected page call: ${input.path}`)
    return JSON.stringify(value)
  })
  await context.addInitScript(() => {
    window.codexProxyPlugin={version:2,request:async input=>({status:200,contentType:'application/json',body:new TextEncoder().encode(await window.__taskHost(input)).buffer})}
  })
  const pageErrors = page => page.on('pageerror', e=>errors.push(e.message))
  let page=await context.newPage(); pageErrors(page)
  await page.goto(base)
  async function select(label,option) {
    const trigger=page.getByRole('combobox',{name:label,exact:true});await trigger.click()
    const controls=await trigger.getAttribute('aria-controls')
    await page.locator(`[id="${controls}"]`).getByRole('option',{name:option,exact:true}).click()
  }
  await select('检测账号','primary@example.com');await select('计量 Key','模型体检专用')
  await select('请求模型','gpt-6-astra');await select('对照基线','gpt-6-astra')
  await page.getByRole('button',{name:'开始检测',exact:true}).click()
  await page.locator('progress').waitFor()
  await page.reload()
  await page.getByRole('button',{name:'查看 primary@example.com 的检测报告',exact:true}).click()
  await page.locator('progress').waitFor()
  const before=runs[0].attempts.length
  await page.goto('about:blank')
  await new Promise(r=>setTimeout(r,1600))
  assert.ok(runs[0].attempts.length>before,'leaving the page must not stop the host')
  await page.close()
  const closed=runs[0].attempts.length
  await new Promise(r=>setTimeout(r,900))
  assert.ok(runs[0].attempts.length>closed,'closing the page must not stop the host')
  page=await context.newPage();pageErrors(page)
  await page.goto(base)
  await page.getByRole('button',{name:'查看 primary@example.com 的检测报告',exact:true}).click()
  assert.ok(Number(await page.locator('progress').getAttribute('value'))>=closed)
  offline=true
  await page.getByText('状态连接中断：',{exact:false}).waitFor()
  const disconnected=runs[0].attempts.length
  await new Promise(r=>setTimeout(r,800))
  assert.ok(runs[0].attempts.length>disconnected)
  offline=false
  await page.getByText('状态连接中断：',{exact:false}).waitFor({state:'hidden'})
  await page.waitForFunction(()=>document.querySelector('progress')?.value===16)

  // A delayed old detail response must not overwrite a newer task selection.
  const other=structuredClone(runs[0])
  Object.assign(other,{id:'2-2',account_name:'backup@example.com',queued_at:null})
  other.attempts=other.attempts.slice(0,1);other.report.valid_samples=1
  runs.push(other)
  await page.getByRole('button',{name:'查看 backup@example.com 的检测报告',exact:true}).waitFor()
  holdId=runs[0].id
  while (!held) await new Promise(r=>setTimeout(r,50))
  await page.getByRole('button',{name:'查看 backup@example.com 的检测报告',exact:true}).click()
  release()
  await page.waitForTimeout(500)
  assert.equal(Number(await page.locator('progress').getAttribute('value')),1)
  assert.ok(!calls.includes('api/runs/step'),'page must never dispatch samples')
  assert.deepEqual(errors,[])
  await page.screenshot({path:`${root}/review/screenshots/background-reopened.png`,fullPage:true})
  runs.pop() // retention can evict a selected finished task
  await page.locator('progress').waitFor({state:'hidden'})
  await page.getByRole('button',{name:'查看 primary@example.com 的检测报告',exact:true}).waitFor()
  assert.equal(await page.getByText('状态连接中断：',{exact:false}).count(),0)
  console.log('BACKGROUND UI PASS: refresh / navigate away / close / reopen / live progress / disconnect recovery / stale detail ignored / no page steps')
} finally {clearInterval(clock);await browser.close()}
