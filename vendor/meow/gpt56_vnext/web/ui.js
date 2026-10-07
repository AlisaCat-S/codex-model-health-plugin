/* Shared, dependency-free UI behavior. Bundled verbatim for the public site. */
const MeowUI = (() => {
  function modelName(id, fallback=id) { return id === 'other_known_external' ? 'other' : fallback; }
  function partialNote(fingerprint, running=false, language='zh-CN') {
    if(running || fingerprint?.quality_status!=='sufficient' || !(fingerprint.valid_samples<fingerprint.planned_samples))return '';
    return language==='en' ? 'Some samples are missing; the result may be less reliable.' : '有效样本未满额，结果可靠性可能下降。';
  }
  function error(value, fallback = code => code) {
    const detail = value?.upstream || value?.local;
    return [value?.http_status != null ? `HTTP ${value.http_status}` : '',
      value?.local ? fallback(value.code) : '',
      detail ? [detail.type, detail.code, detail.reason, detail.message].filter(Boolean).join(' · ') : fallback(value?.code || 'request_failed')]
      .filter(Boolean).join(' · ');
  }
  function alias(model, endpoint) {
    if (model?.reference_only) return '';
    const name = model?.request_model || model?.id || '';
    let openrouter = false;
    try { const url = new URL(endpoint); openrouter = url.protocol === 'https:' && url.hostname === 'openrouter.ai' && url.pathname.replace(/\/$/, '') === '/api/v1'; } catch {}
    if (openrouter) return name;
    const short = name.replace(/^[^/]+\//, '');
    return short.startsWith('claude-') ? short.replace(/(\d)\.(?=\d)/g, '$1-') : short;
  }
  function baselineName(item) {
    if (item.publisher === 'maintainer' && /^meow-(gpt|claude)-(baseline|other-cap98)$/.test(item.id)) return item.mode === 'gpt' ? 'GPT' : 'Claude';
    return item.name || item.id;
  }
  function progress({done,valid,planned,attempts,retries,budget},language='zh-CN') {
    return language === 'en'
      ? `Processed ${done}/${planned} · Valid samples ${valid}/${planned} · Attempts ${attempts}`+(budget==null?'':` · Retries ${retries}/${budget}`)
      : `已处理 ${done}/${planned} · 有效样本 ${valid}/${planned} · 实际尝试 ${attempts}`+(budget==null?'':` · 重试 ${retries}/${budget}`);
  }
  function reportMeta({model,requestModel,url,group},language='zh-CN') {
    const en=language==='en';
    return [(en?'Claimed ':'申报 ')+model+(requestModel!==model?(en?' · Request ':' · 实际请求 ')+requestModel:''),url,(en?'Group: ':'分组：')+(group||(en?'Not specified':'未填写'))].join('\n');
  }
  function matches(container, fingerprint, {models=[],display=id=>id,valid=0,running=false,language='zh-CN'}={}) {
    const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
    if(!valid){container.replaceChildren(node('p',language==='en'?(running?'Waiting for valid answers…':'No valid samples'):(running?'等待有效回答…':'尚无有效样本'),'field-notice'));return;}
    const order=[...new Set([...models.map(m=>m.id),...Object.keys(fingerprint.matches)])];
    container.replaceChildren(...order.filter(id=>id in fingerprint.matches).map(id=>{
      const row=node('div',null,'match-row'),bar=node('progress'),value=node('strong',(fingerprint.matches[id]*100).toFixed(3)+'%');
      bar.max=1;bar.value=fingerprint.matches[id];bar.setAttribute('aria-label',display(id));
      const threshold=fingerprint.thresholds?.[id];
      value.append(node('small',Number.isFinite(threshold)?(language==='en'?'Threshold ':'强指向线 ')+(threshold*100).toFixed(3)+'%':(language==='en'?'Not calibrated':'未校准')));
      row.append(node('span',display(id)),bar,value);return row;
    }));
  }
  function history(container, rows, {selected, empty, open, resume, language='zh-CN'}) {
    const label = (zh,en) => language === 'en' ? en : zh;
    const signature=JSON.stringify([rows,selected,empty,language]);
    if(container.dataset.signature===signature)return;
    container.dataset.signature=signature;
    const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
    const cards=rows.map(row=>{
      const card=node('div');const button=node('button',null,'history-entry');button.type='button';
      button.dataset.id=row.id;button.setAttribute('aria-pressed',String(row.id===selected));
      const top=node('span',null,'history-title');
      top.append(node('b',row.model),node('time',new Date(row.created).toLocaleString(language,{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'}),'history-date'));
      button.append(top,node('span',row.url,'history-url'));
      if(row.requestModel && row.requestModel!==row.model)button.append(node('span',label('请求：','Request: ')+row.requestModel,'history-url'));
      if(row.group)button.append(node('span',label('分组：','Group: ')+row.group,'history-url'));
      const counts=node('span',null,'history-progress');
      counts.append(node('span',label('已处理 ','Processed ')+row.done+'/'+row.planned),node('span',label('有效样本 ','Valid ')+row.valid+'/'+row.planned));
      button.append(counts,node('span',row.status,'history-status '+row.color));button.onclick=()=>open(row.id);card.append(button);
      if(row.resumable && resume){const controls=node('div',null,'history-resume'),r=node('button',label('按原配置恢复','Resume original run'));r.type='button';r.onclick=()=>resume(row.id);controls.append(r);card.append(controls);}
      return card;
    });
    const scroll=container.scrollTop;
    container.replaceChildren(...(cards.length ? cards : [node('p',empty,'history-empty')]));
    container.scrollTop=scroll;
  }
  function theme(select) {
    const system = matchMedia('(prefers-color-scheme: dark)');
    try { select.value = localStorage.getItem('meow-theme') || 'system'; } catch {}
    if (!select.value) select.value = 'system';
    const apply = () => { document.documentElement.dataset.theme = select.value === 'system' ? (system.matches ? 'dark' : 'light') : select.value; };
    select.addEventListener('change', () => { try { localStorage.setItem('meow-theme', select.value); } catch {} apply(); });
    system.addEventListener('change', apply); apply();
  }
  function autofill(input, model, endpoint, force=false) {
    if(force || !input.value || input.value===input.dataset.autofill) {
      input.value=alias(model,endpoint);input.dataset.autofill=input.value;
    }
  }
  function models({button, input, list, notice, fields, connection, fetchModels}) {
    let revision = 0;
    const invalidate = () => { revision++; list.replaceChildren(); notice.textContent = ''; button.disabled = false; };
    for (const field of fields) { field.addEventListener('input', invalidate); field.addEventListener('change', invalidate); }
    button.addEventListener('click', async () => {
      const current = ++revision, request = connection(); button.disabled = true; notice.textContent = '…';
      try {
        const result = await fetchModels(request);
        if (current !== revision) return;
        list.replaceChildren(...result.models.map(id => new Option(id, id)));
        notice.textContent = document.documentElement.lang === 'en' ? `${result.models.length} models available` : `已获取 ${result.models.length} 个模型，可输入名称筛选`; input.focus();
      } catch (failure) { if (current === revision) notice.textContent = failure.message; }
      finally { if (current === revision) button.disabled = false; }
    });
    return invalidate;
  }
  return {error, alias, autofill, theme, models, history, baselineName, progress, reportMeta, matches, modelName, partialNote};
})();
