import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createTheme, createThemeVars, getThemeVarName } from '@codex-proxy/ui/theme'

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
