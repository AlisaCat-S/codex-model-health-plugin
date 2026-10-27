// 异常记录的 UI 合同测试；真实状态恢复由 backend/tests/protocol.rs 覆盖。
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
try {
  const seedPage = await browser.newPage()
  await seedPage.goto(`${base}?preview=1`)
  await seedPage.getByRole('heading', {name:'任务列表', exact:true}).waitFor()
  const { boot, seed, theme } = await seedPage.evaluate(async () => {
    const read = async(path, body) => JSON.parse(new TextDecoder().decode((await window.codexProxyPlugin.request({path:`api/${path}`,method:body?'POST':'GET',...(body?{body:JSON.stringify(body),contentType:'application/json'}:{})})).body))
    return {boot:await read('bootstrap'), seed:(await read('runs/get',{id:'0-1'})).run,
      theme:{attributes:Array.from(document.documentElement.attributes,a=>[a.name,a.value]),bodyStyle:document.body.getAttribute('style'),runtimeStyle:document.getElementById('cp-runtime-theme').textContent}}
  })
  await seedPage.close()
  const broken = {...structuredClone(seed), id:'1-1', account_name:'', status:'paused', attempts:[], plan:boot.catalog, report:seed.plan,
    data_error:'检测计划不完整，无法继续；请结束此任务后新建检测，已有请求明细会保留'}
  const badReport = {...structuredClone(seed), id:'2-2', account_name:'报告异常账号', report:null,
    data_error:'检测报告不完整，请新建检测；已有请求明细会保留'}
  const runs = [broken, badReport], calls = [], errors = []
  const context = await browser.newContext({viewport:{width:1440,height:1050}})
  await context.exposeBinding('__recoveryHost', async(_, input) => {
    calls.push(input.path)
    const data = input.body ? JSON.parse(input.body) : {}
    let value
    if (input.path==='api/bootstrap') value=boot
    else if (input.path==='api/models') value={models:['gpt-6-astra']}
    else if (input.path==='api/runs') value={runs:runs.map(r=>({...r,method:r.plan.method,tier:r.plan.tier,request_model:r.plan.request_model,claimed_model:r.plan.claimed_model,attempts:r.attempts.length}))}
    else if (input.path==='api/runs/get') value={run:runs.find(r=>r.id===data.id)}
    else if (input.path==='api/runs/control') {
      assert.equal(data.action,'stop','异常记录不能继续检测')
      const run=runs.find(r=>r.id===data.id)
      run.status='stopped'; run.data_error='检测计划不完整，请新建检测；已有请求明细会保留'; value={run}
    } else if (input.path==='api/runs/start') {
      assert.equal(data.background,true)
      const run={...structuredClone(seed),id:'3-3',account_name:'primary@example.com',status:'ready',background:true,queued_at:Date.now(),attempts:[],data_error:null}
      Object.assign(run.report,{verdict:'insufficient',valid_samples:0,reasons:['no_valid_samples']})
      runs.unshift(run); value={run}
    } else throw new Error(`unexpected recovery call: ${input.path}`)
    return JSON.stringify(value)
  })
  await context.addInitScript(() => {
    window.codexProxyPlugin={version:2,request:async input=>({status:200,contentType:'application/json',body:new TextEncoder().encode(await window.__recoveryHost(input)).buffer})}
  })
  await context.addInitScript(theme => {
    document.addEventListener('DOMContentLoaded',() => {
      for (const [name,value] of theme.attributes) document.documentElement.setAttribute(name,value)
      const style=document.createElement('style')
      style.id='cp-runtime-theme';style.textContent=theme.runtimeStyle;document.head.append(style)
      document.body.setAttribute('style',theme.bodyStyle)
    })
  },theme)
  const page=await context.newPage()
  page.on('pageerror',e=>errors.push(e.message))
  await page.goto(base)
  assert.ok(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--cp-card-bg').trim()),'隔离测试页面必须携带宿主主题')
  await page.getByRole('button',{name:`查看 ${broken.account_id} 的检测报告`,exact:true}).click()
  await page.getByText(broken.data_error,{exact:true}).waitFor()
  await page.getByText('尚未发起检测请求',{exact:true}).waitFor()
  assert.equal(await page.locator('progress').count(),0)
  assert.equal(await page.getByRole('button',{name:'继续检测',exact:true}).count(),0)
  await page.screenshot({path:`${root}/review/screenshots/recovery-broken-plan.png`,fullPage:true})
  await page.setViewportSize({width:390,height:844})
  await page.getByRole('button',{name:'结束检测',exact:true}).scrollIntoViewIfNeeded()
  await page.screenshot({path:`${root}/review/screenshots/recovery-narrow.png`,fullPage:true})
  await page.getByRole('button',{name:'结束检测',exact:true}).click()
  await page.getByRole('button',{name:'结束检测',exact:true}).waitFor({state:'hidden'})
  assert.equal(broken.status,'stopped')
  assert.deepEqual(broken.plan,boot.catalog)
  await page.reload()
  await page.getByRole('button',{name:`查看 ${broken.account_id} 的检测报告`,exact:true}).click()
  await page.getByText(broken.data_error,{exact:true}).waitFor()
  await page.getByRole('button',{name:'查看 报告异常账号 的检测报告',exact:true}).click()
  await page.getByText(badReport.data_error,{exact:true}).waitFor()
  await page.getByText('preview-request-1',{exact:true}).waitFor()
  assert.equal(await page.locator('progress').count(),0)
  await page.setViewportSize({width:1440,height:1050})
  await page.screenshot({path:`${root}/review/screenshots/recovery-request-details.png`,fullPage:true})
  async function select(label,option) {
    const trigger=page.getByRole('combobox',{name:label,exact:true});await trigger.click()
    const controls=await trigger.getAttribute('aria-controls')
    await page.locator(`[id="${controls}"]`).getByRole('option',{name:option,exact:true}).click()
  }
  await select('检测账号','primary@example.com');await select('计量 Key','模型体检专用')
  await select('请求模型','gpt-6-astra');await select('对照基线','gpt-6-astra')
  await page.getByRole('button',{name:'开始检测',exact:true}).click()
  await page.locator('progress').waitFor()
  await page.getByRole('button',{name:'当前题完成后暂停',exact:true}).waitFor()
  assert.equal(runs.length,3)
  assert.equal(calls.filter(path=>path==='api/runs/control').length,1)
  assert.ok(!calls.includes('api/runs/step'))
  assert.deepEqual(errors,[])
  console.log('RECOVERY UI PASS: broken plan / null report / inspect / stop / reopen / preserved request IDs / narrow screen / new task; real model calls=0')
} finally { await browser.close() }
