<script setup lang="ts">
import { ZTable, ZTag } from '@codex-proxy/ui'
import type { TableColumn } from '@codex-proxy/ui'
import type { Attempt } from './api'

defineProps<{attempts: Attempt[]}>()
const columns = [{key:'number',label:'#',kind:'index'},{key:'job_id',label:'样本',kind:'mono',size:'xl'},{key:'status',label:'状态',kind:'status'},{key:'answer',label:'回答 / 错误',kind:'custom',size:'2xl'},{key:'request_id',label:'请求 ID',kind:'mono',size:'2xl'}] satisfies TableColumn[]
</script>

<template>
  <ZTable :columns="columns" :data="attempts.map((a,i)=>({...a,number:i+1,id:i}))" empty-text="尚未发起检测请求"><template #status="{row}"><ZTag :type="row.status === 'ok' ? 'success' : row.status === 'pending' ? 'primary' : 'warning'">{{ row.status === 'ok' ? '有效' : row.status === 'pending' ? '进行中' : '异常' }}</ZTag></template><template #answer="{row}"><span class="sample-answer">{{ row.error || row.answer || '—' }}{{ row.answer_truncated ? '（展示已截短，评分使用完整回答）' : '' }}</span></template></ZTable>
</template>
