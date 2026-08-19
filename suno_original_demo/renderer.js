const $ = (id) => document.getElementById(id);
let currentTask = null;

function log(text, cls = '') {
  const box = $('log');
  const time = new Date().toLocaleTimeString();
  box.innerHTML += `\n<span class="${cls}">[${time}] ${escapeHtml(String(text))}</span>`;
  box.scrollTop = box.scrollHeight;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
}

async function refreshAccounts() {
  const root = $('accounts');
  root.innerHTML = '';
  for (const slot of ['1','2','3']) {
    let st;
    try { st = await window.demoApi.accountStatus(slot); }
    catch { st = { loggedIn:false }; }
    const div = document.createElement('div');
    div.className = 'account';
    div.innerHTML = `<div><span class="dot ${st.loggedIn ? 'ok' : ''}"></span>账号 ${slot}<div class="small">${st.loggedIn ? '已登录' : '未登录'}</div></div><button class="secondary">${st.loggedIn ? '打开' : '登录'}</button>`;
    div.querySelector('button').onclick = async () => {
      await window.demoApi.openLogin(slot);
      log(`已打开 Suno 账号 ${slot} 登录窗口。`);
    };
    root.appendChild(div);
  }
}

function renderTask(task) {
  const root = $('taskArea');
  if (!task) { root.innerHTML = '还没有提交任务。'; return; }
  const tracks = task.tracks || task.clipIds?.map(id => ({id,status:'submitted',url:`https://suno.com/song/${id}`})) || [];
  root.innerHTML = `<div><b>${escapeHtml(task.title || '未命名')}</b></div><div class="small">账号 ${escapeHtml(String(task.slot || ''))} · ${escapeHtml(task.submittedAt || '')}</div>` + tracks.map((t, i) => `
    <div class="track">
      <div><div>版本 ${i+1}</div><div class="status ${t.status === 'complete' ? 'oktxt' : t.status === 'error' ? 'err' : ''}">${escapeHtml(t.status || 'submitted')} ${t.duration ? `· ${Number(t.duration).toFixed(1)}s` : ''}</div>${t.error ? `<div class="small err">${escapeHtml(t.error)}</div>` : ''}</div>
      <button class="secondary" data-url="${escapeHtml(t.url)}">打开</button>
    </div>`).join('');
  root.querySelectorAll('button[data-url]').forEach(btn => btn.onclick = () => window.demoApi.openSong(btn.dataset.url));
}

$('refreshAccounts').onclick = refreshAccounts;

if (window.demoApi.onVerificationState) {
  window.demoApi.onVerificationState((state) => {
    const msg = state?.message || '';
    if (state?.state === 'required') {
      log(`检测到账号 ${state.slot} 需要 Suno 人机验证：${msg}`, 'err');
    } else if (state?.state === 'waiting') {
      log(msg || '等待人机验证完成……');
    } else if (state?.state === 'passed') {
      log(msg || '人机验证已通过，正在自动继续。', 'oktxt');
      refreshAccounts();
    }
  });
}

$('submitBtn').onclick = async () => {
  const payload = {
    title: $('title').value,
    lyrics: $('lyrics').value,
    stylePrompt: $('style').value,
    slot: $('slot').value,
    modelVersion: $('model').value,
    vocalGender: $('gender').value,
    weirdness: Number($('weirdness').value),
    styleInfluence: Number($('styleInfluence').value),
  };
  $('submitBtn').disabled = true;
  try {
    log(`开始提交：${payload.title || '未填写歌名'} / 账号 ${payload.slot}`);
    currentTask = await window.demoApi.submitOriginal(payload);
    renderTask(currentTask);
    $('refreshTaskBtn').disabled = false;
    log(`提交成功，返回 ${currentTask.clipIds.length} 个作品编号。`, 'oktxt');
  } catch (e) {
    log(e?.message || e, 'err');
    alert(e?.message || String(e));
  } finally {
    $('submitBtn').disabled = false;
  }
};

$('refreshTaskBtn').onclick = async () => {
  if (!currentTask) return;
  $('refreshTaskBtn').disabled = true;
  try {
    log('正在刷新任务状态……');
    currentTask = await window.demoApi.refreshTask(currentTask);
    renderTask(currentTask);
    const allDone = (currentTask.tracks || []).every(t => t.status === 'complete');
    log(allDone ? '当前任务的所有版本都已完成。' : '任务状态已刷新。', allDone ? 'oktxt' : '');
  } catch (e) {
    log(e?.message || e, 'err');
  } finally {
    $('refreshTaskBtn').disabled = false;
  }
};

refreshAccounts();
