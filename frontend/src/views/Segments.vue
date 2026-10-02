<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

interface QuotaEdit { priority: number | null; max_stalls: number | null }

const rows = ref<any[]>([])
const edits = ref<Record<number, QuotaEdit[]>>({})
const errors = ref<Record<number, string>>({})
const saved = ref<Record<number, boolean>>({})

async function load() {
  rows.value = await api('/segments')
  const e: Record<number, QuotaEdit[]> = {}
  for (const r of rows.value) {
    e[r.id] = (r.quotas || []).map((q: any) => ({ priority: q.priority, max_stalls: q.max_stalls }))
  }
  edits.value = e
}
onMounted(load)

function addRow(segId: number) {
  ;(edits.value[segId] ||= []).push({ priority: null, max_stalls: null })
  saved.value[segId] = false
}
function removeRow(segId: number, i: number) {
  edits.value[segId].splice(i, 1)
  saved.value[segId] = false
}

async function save(segId: number) {
  errors.value[segId] = ''
  saved.value[segId] = false
  const quotas: { priority: number; max_stalls: number }[] = []
  for (const r of edits.value[segId] || []) {
    const emptyMax = r.max_stalls == null || (r.max_stalls as any) === ''
    if (r.priority == null && emptyMax) continue
    if (r.priority == null || r.priority < 1) { errors.value[segId] = '请填写正整数优先级'; return }
    quotas.push({ priority: r.priority, max_stalls: emptyMax ? 0 : Number(r.max_stalls) })
  }
  try {
    await api(`/segments/${segId}/quotas`, { method: 'PUT', body: JSON.stringify({ quotas }) })
    saved.value[segId] = true
    await load()
  } catch (e: any) {
    let msg = e?.message || String(e)
    try { const j = JSON.parse(msg); if (j.detail) msg = j.detail } catch { /* keep raw */ }
    errors.value[segId] = '保存失败：' + msg
    await load() // 拒绝后回到改前状态，不留半成功
  }
}
</script>
<template>
  <h1>街段</h1>
  <p class="sub">沿街可用宽度（米）· 同优先配额：同一优先数字最多可落档数，留空或 0 为不限制</p>
  <div class="card">
    <table>
      <thead><tr><th>街段</th><th>宽度(m)</th><th>集日ID</th><th>同优先配额</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.name }}</td><td>{{ r.width_m }}</td><td>{{ r.market_day_id }}</td>
          <td>
            <span v-for="q in r.quotas" :key="q.priority" class="badge badge-warn">优先{{ q.priority }} ≤ {{ q.max_stalls }} 档</span>
            <span v-if="!r.quotas || !r.quotas.length" class="muted">不限制</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="card" v-for="r in rows" :key="'quota-' + r.id">
    <h2 class="ss-quota-title">{{ r.name }} · 同优先配额</h2>
    <div v-for="(q, i) in edits[r.id] || []" :key="i" class="ss-quota-row">
      <label>优先 <input type="number" min="1" step="1" v-model.number="q.priority" placeholder="如 1" /></label>
      <label>最多 <input type="number" min="0" step="1" v-model.number="q.max_stalls" placeholder="不限" /> 档</label>
      <button type="button" class="ss-link-btn" @click="removeRow(r.id, i)">移除</button>
    </div>
    <p v-if="!(edits[r.id] || []).length" class="muted ss-quota-empty">未设上限：各优先均不限制</p>
    <div class="ss-quota-actions">
      <button type="button" class="ss-link-btn" @click="addRow(r.id)">＋添加配额</button>
      <button type="button" class="btn" @click="save(r.id)">保存配额</button>
      <span v-if="errors[r.id]" class="ss-err">{{ errors[r.id] }}</span>
      <span v-else-if="saved[r.id]" class="ss-ok-msg">已保存</span>
    </div>
  </div>
</template>
