const { app, BrowserWindow, ipcMain, session, shell } = require('electron');
const path = require('path');
const { randomUUID } = require('crypto');

const SUNO_HOME = 'https://suno.com/';
const SUNO_CREATE = 'https://suno.com/create';
const SUNO_STUDIO = 'https://suno.com/studio';
const SUNO_API = 'https://studio-api-prod.suno.com';
const MODEL_MAP = {
  'v5.5': 'chirp-fenix',
  'v5': 'chirp-crow',
  'v4.5+': 'chirp-bluejay',
  'v4.5-all': 'chirp-bluejay',
};

let mainWindow;
const accountWindows = new Map();

function partitionFor(slot) {
  return `persist:suno-original-demo-${slot}`;
}

function isAllowedAccountUrl(url) {
  try {
    const u = new URL(url);
    const h = u.hostname.toLowerCase();
    const allowed = new Set([
      'accounts.google.com', 'appleid.apple.com', 'discord.com',
      'login.live.com', 'account.live.com', 'signup.live.com',
      'login.microsoftonline.com', 'login.microsoft.com', 'account.microsoft.com'
    ]);
    return u.protocol === 'https:' && (
      h === 'suno.com' || h.endsWith('.suno.com') ||
      h.endsWith('.clerk.accounts.dev') || allowed.has(h)
    );
  } catch {
    return false;
  }
}

function configureNavigation(win, partition) {
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedAccountUrl(url)) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: {
          autoHideMenuBar: true,
          webPreferences: {
            partition,
            contextIsolation: true,
            nodeIntegration: false,
            sandbox: true,
            webSecurity: true,
          },
        },
      };
    }
    if (url.startsWith('https://')) shell.openExternal(url);
    return { action: 'deny' };
  });
  win.webContents.on('will-navigate', (event, url) => {
    if (!isAllowedAccountUrl(url)) {
      event.preventDefault();
      if (url.startsWith('https://')) shell.openExternal(url);
    }
  });
}

async function ensureAccountWindow(slot, show = false, target = SUNO_HOME) {
  slot = String(slot);
  let win = accountWindows.get(slot);
  if (win && !win.isDestroyed()) {
    if (show) { win.show(); win.focus(); }
    return win;
  }
  const partition = partitionFor(slot);
  win = new BrowserWindow({
    width: 1320,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    title: `Suno 账号 ${slot}`,
    autoHideMenuBar: true,
    show,
    backgroundColor: '#090a0f',
    webPreferences: {
      partition,
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      allowRunningInsecureContent: false,
      backgroundThrottling: false,
    },
  });
  configureNavigation(win, partition);
  win.on('closed', () => accountWindows.delete(slot));
  accountWindows.set(slot, win);
  await win.loadURL(target);
  if (show) { win.show(); win.focus(); }
  return win;
}

async function waitReady(win, timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      const ok = await win.webContents.executeJavaScript('document.readyState === "complete"');
      if (ok) return;
    } catch {}
    await new Promise(r => setTimeout(r, 300));
  }
  throw new Error('Suno 页面加载超时');
}

async function accountStatus(slot) {
  const ses = session.fromPartition(partitionFor(slot));
  const cookies = await ses.cookies.get({ url: SUNO_HOME });
  let loggedIn = cookies.some(c => c.name === '__session' || c.name.startsWith('__session_'));
  const win = accountWindows.get(String(slot));
  if (loggedIn && win && !win.isDestroyed() && win.webContents.getURL().startsWith('https://suno.com/')) {
    try {
      const state = await win.webContents.executeJavaScript(`(() => {
        if (window.Clerk !== undefined) return Boolean(window.Clerk?.session);
        return null;
      })()`);
      if (typeof state === 'boolean') loggedIn = state;
    } catch {}
  }
  return { slot: String(slot), loggedIn, partition: partitionFor(slot), windowOpen: !!(win && !win.isDestroyed()) };
}

async function getAuthToken(slot) {
  const win = await ensureAccountWindow(slot, false, SUNO_STUDIO);
  if (!win.webContents.getURL().startsWith('https://suno.com/')) await win.loadURL(SUNO_STUDIO);
  await waitReady(win);
  const token = await win.webContents.executeJavaScript(`(async () => {
    for (let i = 0; i < 24; i++) {
      if (window.Clerk?.session) break;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    try {
      const t = await window.Clerk?.session?.getToken?.();
      if (t) return t;
    } catch {}
    const cookie = Object.fromEntries(document.cookie.split(';').map(part => {
      const [key, ...rest] = part.trim().split('=');
      return [key, rest.join('=')];
    }));
    return cookie.__session || Object.entries(cookie).find(([k]) => k.startsWith('__session'))?.[1] || '';
  })()`);
  if (!String(token || '').trim()) throw new Error(`账号 ${slot} 尚未登录，请先点击“登录/打开”完成 Suno 登录`);
  return String(token).trim();
}

function browserToken() {
  return JSON.stringify({ token: Buffer.from(JSON.stringify({ timestamp: Date.now() }), 'utf8').toString('base64') });
}

async function apiHeaders(slot) {
  const token = await getAuthToken(slot);
  const ses = session.fromPartition(partitionFor(slot));
  const cookies = await ses.cookies.get({ url: SUNO_HOME });
  const device = cookies.find(c => c.name === 'suno_device_id')?.value || '';
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    'Browser-Token': browserToken(),
    ...(device ? { 'Device-Id': device } : {}),
  };
}

async function precheckVerification(slot, headers) {
  const ses = session.fromPartition(partitionFor(slot));
  try {
    const res = await ses.fetch(`${SUNO_API}/api/c/check`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ ctype: 'generation' }),
    });
    if (!res.ok) return { required: false };
    const data = await res.json().catch(() => ({}));
    return { required: !!data.required, captchaVersion: data.captcha_version };
  } catch {
    return { required: false };
  }
}

function buildOriginalPayload(input) {
  const sliders = {};
  if (Number.isFinite(Number(input.weirdness))) sliders.weirdness_constraint = Math.max(0, Math.min(1, Number(input.weirdness) / 100));
  if (Number.isFinite(Number(input.styleInfluence))) sliders.style_weight = Math.max(0, Math.min(1, Number(input.styleInfluence) / 100));
  const genderTag = input.vocalGender === 'female' ? 'female vocal' : input.vocalGender === 'male' ? 'male vocal' : '';
  const tags = [String(input.stylePrompt || '').trim(), genderTag].filter(Boolean).join(', ');
  return {
    token: null,
    generation_type: 'TEXT',
    title: String(input.title || '').trim(),
    tags,
    negative_tags: '',
    mv: MODEL_MAP[input.modelVersion] || 'chirp-fenix',
    prompt: String(input.lyrics || ''),
    make_instrumental: false,
    user_uploaded_images_b64: null,
    metadata: {
      web_client_pathname: '/create',
      is_max_mode: false,
      is_mumble: false,
      create_mode: 'custom',
      user_tier: '',
      create_session_token: randomUUID(),
      disable_volume_normalization: false,
      ...(Object.keys(sliders).length ? {
        can_control_sliders: ['weirdness_constraint', 'style_weight'],
        control_sliders: sliders,
      } : {}),
      ...(input.vocalGender ? { vocal_gender: input.vocalGender === 'female' ? 'f' : 'm' } : {}),
    },
    override_fields: [],
    cover_clip_id: null,
    cover_start_s: null,
    cover_end_s: null,
    persona_id: null,
    artist_clip_id: null,
    artist_start_s: null,
    artist_end_s: null,
    continue_clip_id: null,
    continued_aligned_prompt: null,
    continue_at: null,
    transaction_uuid: randomUUID(),
  };
}

async function submitOriginal(input) {
  const slot = String(input.slot || '1');
  const title = String(input.title || '').trim();
  const lyrics = String(input.lyrics || '').trim();
  if (!title) throw new Error('请填写歌名');
  if (!lyrics) throw new Error('请填写歌词');
  const headers = await apiHeaders(slot);
  const verification = await precheckVerification(slot, headers);
  if (verification.required) {
    const win = await ensureAccountWindow(slot, true, SUNO_CREATE);
    if (!win.webContents.getURL().startsWith(SUNO_CREATE)) await win.loadURL(SUNO_CREATE);
    win.show(); win.focus();
    throw new Error('Suno 当前要求人机验证。我已经打开账号窗口，请手动完成验证后，再回到 Demo 重新点击提交。');
  }
  const ses = session.fromPartition(partitionFor(slot));
  const res = await ses.fetch(`${SUNO_API}/api/generate/v2-web/`, {
    method: 'POST',
    headers,
    body: JSON.stringify(buildOriginalPayload(input)),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body);
    if (res.status === 402 || /enough credits|out of credits|out of songs|buy more/i.test(detail || '')) {
      throw new Error('Suno 账号歌曲额度不足');
    }
    if (res.status === 422 && /verify|verification|captcha/i.test(detail || '')) {
      const win = await ensureAccountWindow(slot, true, SUNO_CREATE);
      win.show(); win.focus();
      throw new Error('Suno 要求人机验证，请在打开的账号窗口完成验证后重试。');
    }
    throw new Error(`Suno 原创提交失败（${res.status}）：${detail || '未知错误'}`);
  }
  const clips = (body?.clips || []).map(x => x?.id).filter(Boolean).slice(0, 2);
  if (!clips.length) throw new Error('Suno 没有返回原创作品编号');
  return {
    slot,
    title,
    clipIds: clips,
    submittedAt: new Date().toISOString(),
    tracks: clips.map(id => ({ id, url: `https://suno.com/song/${id}`, status: 'submitted' })),
  };
}

async function refreshTask(task) {
  const slot = String(task?.slot || '1');
  const ids = Array.isArray(task?.clipIds) ? task.clipIds.filter(Boolean) : [];
  if (!ids.length) throw new Error('任务没有作品编号');
  const headers = await apiHeaders(slot);
  const ses = session.fromPartition(partitionFor(slot));
  const url = `${SUNO_API}/api/feed/v2?ids=${encodeURIComponent(ids.join(','))}`;
  const res = await ses.fetch(url, { headers });
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new Error(`读取 Suno 任务失败（${res.status}）`);
  const raw = Array.isArray(body) ? body : (body?.clips || body?.items || []);
  const byId = new Map(raw.map(x => [x.id, x]));
  const tracks = ids.map(id => {
    const x = byId.get(id) || {};
    return {
      id,
      url: `https://suno.com/song/${id}`,
      status: String(x.status || 'submitted'),
      title: x.title || task.title || '',
      audioUrl: x.audio_url || '',
      imageUrl: x.image_url || '',
      duration: Number(x.metadata?.duration || 0),
      error: x.error_message || x.metadata?.error_message || '',
    };
  });
  return { ...task, tracks, refreshedAt: new Date().toISOString() };
}

function createMainWindow() {
  mainWindow = new BrowserWindow({
    width: 1180,
    height: 820,
    minWidth: 1000,
    minHeight: 700,
    title: 'Suno 原创 Demo v0.1.0',
    backgroundColor: '#0b0c10',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.loadFile('index.html');
}

app.whenReady().then(() => {
  ipcMain.handle('account:status', (_, slot) => accountStatus(slot));
  ipcMain.handle('account:open-login', async (_, slot) => {
    const win = await ensureAccountWindow(String(slot), true, SUNO_HOME);
    win.show(); win.focus();
    return true;
  });
  ipcMain.handle('original:submit', (_, payload) => submitOriginal(payload || {}));
  ipcMain.handle('task:refresh', (_, task) => refreshTask(task || {}));
  ipcMain.handle('song:open', (_, url) => {
    if (typeof url === 'string' && url.startsWith('https://suno.com/song/')) shell.openExternal(url);
  });
  createMainWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createMainWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
