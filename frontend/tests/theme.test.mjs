import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createTheme, createThemeVars, getThemeVarName } from '@codex-proxy/ui/theme'

test('material changes preserve default and customized theme dimensions', () => {
  for (const scheme of ['light', 'dark']) {
    for (const customization of [undefined, {
      seed: { borderRadius: 11, fontSize: 16, sizeUnit: 5, sizeStep: 3, controlHeight: 40 },
      component: { cardBorderRadius: 21, tableRowHeight: 52 },
    }]) {
      const normal = createTheme({ scheme, preset: 'default', customization }).tokens
      const soft = createTheme({ scheme, preset: 'soft', customization }).tokens
      for (const name of Object.keys(normal).filter(name => /radius|font-size|line-height|size-unit|size-step|height/u.test(name)))
        assert.equal(soft[name], normal[name], `${scheme}: ${name}`)
      assert.equal(soft['border-radius'], customization ? '11px' : '8px')
      assert.equal(soft['card-border-radius'], customization ? '21px' : '18px')
      assert.equal(soft['layout-sider-border-radius'], '0px')
      assert.notEqual(soft['card-bg-image'], normal['card-bg-image'])
    }
  }
})

test('page styles use current UI tokens and the host theme namespace', () => {
  const variables = createThemeVars(createTheme().tokens)
  // 宿主主题桥额外提供等宽字体，不属于 UI 的颜色和尺寸 Token。
  variables[getThemeVarName('font-family-code')] = 'monospace'
  for (const file of ['App.vue', 'SourceUpdates.vue', 'styles/index.css', 'preview.ts']) {
    const source = readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
    assert.doesNotMatch(source, /(?:--|text-)cp-/u, file)
    for (const [, name] of source.matchAll(/var\((--z-[\w-]+)/gu))
      assert.ok(name in variables, `${file}: unknown theme variable ${name}`)
  }
})
