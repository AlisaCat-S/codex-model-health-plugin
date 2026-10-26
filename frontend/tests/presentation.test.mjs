import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source=readFileSync(new URL('../src/presentation.ts',import.meta.url),'utf8')
const {outputText}=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2024}})
const {verdict,tone,methodText,runStatusText}=await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)
test('partial results never claim completed identity verification',()=>{for (const status of ['ready','running','paused']) {assert.equal(verdict({verdict:'match'},status),'检测尚未结束');assert.equal(tone({verdict:'mismatch'},status),'primary')}})
test('insufficient samples are distinct from mismatch',()=>{assert.equal(verdict({verdict:'insufficient'},'completed'),'证据不足');assert.equal(verdict({verdict:'mismatch'},'completed'),'行为偏离所选基线')})
test('legacy reports remain Meow and methods are distinguishable',()=>{assert.equal(methodText(),'Meow');assert.equal(methodText('modeltrace'),'ModelTrace')})
test('ModelTrace reports relative attribution not identity verification',()=>{const r={method:'modeltrace',verdict:'attributed',analysis:{prediction_name:'candidate'}};assert.equal(verdict(r,'completed'),'更接近 candidate');assert.equal(tone(r,'completed'),'primary');assert.equal(verdict(r,'ready'),'检测尚未结束');assert.equal(verdict({...r,verdict:'insufficient'},'stopped'),'证据不足')})

test('queued background tasks are distinct from legacy ready and paused tasks',()=>{assert.equal(runStatusText({status:'ready',background:true,queued_at:1}),'排队中');assert.equal(runStatusText({status:'ready'}),'等待继续');assert.equal(runStatusText({status:'paused',background:true,queued_at:null}),'已暂停');assert.equal(runStatusText({status:'running',background:true,queued_at:1}),'检测中')})
