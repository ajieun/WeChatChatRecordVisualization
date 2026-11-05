const $ = (id) => document.getElementById(id);

const S = {
  chats: [],
  chat: null,
  msgs: [],
  loading: false,
  hasMore: true,
  filter: { after: null, before: null },
  searchQ: '',
  hits: [],
  hitTotal: 0,
  hitOffset: 0,
  meta: {},
  chatQ: '',
  chatKind: '',
};

/* ---------------- 工具 ---------------- */
async function api(name, params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') qs.set(k, v);
  });
  const res = await fetch(`/api/${name}?${qs}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
  { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function highlight(text, q) {
  const safe = esc(text);
  if (!q) return safe;
  const needle = esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return safe.replace(new RegExp(needle, 'gi'), (m) => `<mark>${m}</mark>`);
}

const pad = (n) => String(n).padStart(2, '0');
const d2 = (ts) => new Date(ts * 1000);
const dayKey = (ts) => { const d = d2(ts); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
const hhmm = (ts) => { const d = d2(ts); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };

function dayLabel(ts) {
  const d = d2(ts), now = new Date();
  const same = (a, b) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (same(d, now)) return '今天';
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (same(d, y)) return '昨天';
  const sameYear = d.getFullYear() === now.getFullYear();
  return sameYear ? `${d.getMonth() + 1}月${d.getDate()}日` : `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

function listTime(ts) {
  if (!ts) return '';
  const d = d2(ts), now = new Date();
  if (d.toDateString() === now.toDateString()) return hhmm(ts);
  if (d.getFullYear() === now.getFullYear()) return `${d.getMonth() + 1}/${d.getDate()}`;
  return `${d.getFullYear()}/${d.getMonth() + 1}/${d.getDate()}`;
}

function fullTime(ts) {
  const d = d2(ts);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${hhmm(ts)}`;
}

function avatarStyle(name) {
  let h = 0;
  for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `background: hsl(${h} 55% 58%)`;
}
const initial = (name) => (String(name || '?').trim()[0] || '?').toUpperCase();

const MEDIA_ICON = { image: '🖼', voice: '🎤', video: '🎬', file: '📎', link: '🔗', sticker: '😀', location: '📍', transfer: '💰', redpacket: '🧧', miniapp: '🔳', card: '👤', xml: '📄' };

/* ---------------- 会话列表 ---------------- */
async function loadChats() {
  const data = await api('chats');
  S.chats = data.chats || [];
  renderChats();
}

function filteredChats() {
  const q = S.chatQ.toLowerCase();
  return S.chats.filter((c) => {
    const isGroup = c.kind === 'group';
    if (S.chatKind === 'group' && !isGroup) return false;
    if (S.chatKind === 'single' && isGroup) return false;
    if (!q) return true;
    return String(c.name).toLowerCase().includes(q) ||
           String(c.preview || '').toLowerCase().includes(q);
  });
}

function renderChats() {
  const box = $('chatList');
  const list = filteredChats();
  if (!S.chats.length) {
    box.innerHTML = `<div class="empty" style="padding:40px 16px">还没有导入数据</div>`;
    return;
  }
  if (!list.length) {
    box.innerHTML = `<div class="empty" style="padding:40px 16px">没有匹配的会话</div>`;
    return;
  }
  const q = S.chatQ;
  $('chatCount').textContent = q || S.chatKind
    ? `${list.length} / ${S.chats.length} 个`
    : `${S.chats.length} 个`;
  box.innerHTML = list.map((c) => {
    const badge = c.kind === 'group' ? '<span class="kind-badge group">群</span>' : '';
    return `
    <div class="chat-item ${S.chat && S.chat.id === c.id ? 'active' : ''}" data-id="${c.id}">
      <div class="avatar" style="${avatarStyle(c.name)}">${esc(initial(c.name))}</div>
      <div class="chat-meta">
        <div class="chat-name"><b>${highlight(c.name, q)}</b>${badge}<span>${listTime(c.last_ts)}</span></div>
        <div class="chat-preview">${q ? highlight((c.preview || '（无消息）').replace(/\n/g, ' ').slice(0, 40), q)
                                      : esc((c.preview || '（无消息）').replace(/\n/g, ' ').slice(0, 40))}</div>
      </div>
    </div>`;
  }).join('');
  box.querySelectorAll('.chat-item').forEach((el) => {
    el.onclick = () => {
      const c = S.chats.find((x) => x.id === Number(el.dataset.id));
      if (c) selectChat(c);
    };
  });
}

/* ---------------- 会话内容 ---------------- */
async function selectChat(chat, opts = {}) {
  S.chat = chat;
  S.msgs = [];
  S.hasMore = true;
  S.filter = { after: null, before: null };
  $('dateFrom').value = '';
  $('dateTo').value = '';
  $('inChatSearch').value = '';
  renderChats();
  $('convAvatar').style.display = 'flex';
  $('convAvatar').style.cssText = avatarStyle(chat.name);
  $('convAvatar').textContent = initial(chat.name);
  $('convTitle').textContent = chat.name;
  $('convSub').textContent = `${chat.msg_count} 条消息` +
    (chat.last_ts ? ` · 最近 ${fullTime(chat.last_ts)}` : '');
  await loadMessages(opts);
}

async function loadMessages(opts = {}) {
  if (!S.chat || S.loading) return;
  S.loading = true;
  try {
    const params = { chat_id: S.chat.id, limit: opts.limit || 80 };
    if (opts.around != null) params.around_ts = Math.floor(opts.around);
    if (opts.before != null) params.before_ts = Math.floor(opts.before);
    if (S.filter.after) params.after_ts = S.filter.after;
    if (S.filter.before) params.before_ts = S.filter.before;
    if (opts.q) params.q = opts.q;

    const data = await api('messages', params);
    const list = data.messages || [];
    if (opts.around != null) {
      S.msgs = list;
      S.hasMore = true;
      renderMessages(true);
      const target = S.msgs.find((m) => Math.abs(m.ts - opts.around) <= 60) || S.msgs[0];
      if (target) flashTo(target.id);
      return;
    }
    if (opts.before != null) {
      S.msgs = list.concat(S.msgs);
      S.hasMore = list.length >= (opts.limit || 80);
      renderMessages(false, true);
      return;
    }
    S.msgs = list;
    S.hasMore = list.length >= (opts.limit || 80);
    renderMessages(true);
  } finally {
    S.loading = false;
  }
}

function renderMessages(scrollBottom, keepPos = false) {
  const box = $('messages');
  const prevHeight = box.scrollHeight;
  const prevTop = box.scrollTop;

  if (!S.msgs.length) {
    box.innerHTML = `<div class="empty">该条件下没有消息</div>`;
    return;
  }
  box.innerHTML = '';
  const stream = document.createElement('div');
  stream.className = 'stream';
  box.appendChild(stream);

  if (S.hasMore && !S.filter.after) {
    const b = document.createElement('div');
    b.className = 'loadmore';
    b.textContent = '载入更早的消息';
    b.onclick = () => loadMessages({ before: S.msgs[0].ts });
    stream.appendChild(b);
  }

  let lastDay = null, lastTs = 0, lastWho = null;
  S.msgs.forEach((m) => {
    const dk = dayKey(m.ts);
    const who = m.sender || (m.is_self ? '我' : S.chat.name);
    if (dk !== lastDay) {
      const sep = document.createElement('div');
      sep.className = 'day';
      sep.textContent = dayLabel(m.ts);
      stream.appendChild(sep);
      lastDay = dk;
      lastTs = 0;
      lastWho = null;
    } else if (m.ts - lastTs > 900) {
      const sep = document.createElement('div');
      sep.className = 'time-sep';
      sep.textContent = hhmm(m.ts);
      stream.appendChild(sep);
      lastWho = null;
    }
    const sameRun = lastWho === who && m.ts - lastTs < 180;
    lastTs = m.ts;
    lastWho = who;

    const isSelf = !!m.is_self;
    const row = document.createElement('div');
    row.className = 'row' + (isSelf ? ' self' : '');
    row.id = `m-${m.id}`;
    const showName = !isSelf && S.chat.kind === 'group' && !!m.sender && !sameRun;
    const isMedia = m.mtype && m.mtype !== 'text';
    const icon = MEDIA_ICON[m.mtype] || '';
    row.innerHTML = `
      <div class="avatar ${sameRun ? 'ghost' : ''}" style="${avatarStyle(who)}">${esc(initial(who))}</div>
      <div class="body">
        ${showName ? `<div class="sender">${esc(m.sender)}</div>` : ''}
        <div class="bubble ${isMedia ? 'media' : ''}" title="${esc(fullTime(m.ts))}">${
          isMedia ? `${icon} ${highlight(m.content || '', S.searchQ)}` : highlight(m.content || '', S.searchQ)
        }</div>
      </div>`;
    stream.appendChild(row);
  });

  if (scrollBottom) box.scrollTop = box.scrollHeight;
  else if (keepPos) box.scrollTop = box.scrollHeight - prevHeight + prevTop;
}

function flashTo(id) {
  const el = $(`m-${id}`);
  if (!el) return;
  el.scrollIntoView({ block: 'center' });
  const b = el.querySelector('.bubble');
  b.classList.add('flash');
  setTimeout(() => b.classList.remove('flash'), 2000);
}

/* ---------------- 全局搜索 ---------------- */
let searchTimer = null;
function onSearchInput() {
  const q = $('globalSearch').value.trim();
  clearTimeout(searchTimer);
  if (!q) { $('results').classList.remove('show'); return; }
  searchTimer = setTimeout(() => runSearch(q, 0), 260);
}

async function runSearch(q, offset, chatScoped = false) {
  S.searchQ = q;
  const params = { q, limit: 40, offset };
  if (chatScoped && S.chat) params.chat_id = S.chat.id;
  if (S.filter.after) params.start = S.filter.after;
  if (S.filter.before) params.end = S.filter.before;
  const data = await api('search', params);
  S.hits = data.hits || [];
  S.hitTotal = data.total || 0;
  S.hitOffset = offset;
  renderResults(q, chatScoped);
}

function renderResults(q, chatScoped) {
  $('results').classList.add('show');
  $('resultsTitle').textContent = `${chatScoped ? '会话内' : '全部聊天'}搜索「${q}」 · 命中 ${S.hitTotal} 条`;
  const box = $('resultsList');
  if (!S.hits.length) {
    box.innerHTML = `<div class="empty">没有找到匹配的消息</div>`;
    return;
  }
  box.innerHTML = S.hits.map((h) => `
    <div class="hit" data-id="${h.id}" data-ts="${h.ts}" data-chat="${h.chat_id}">
      <div class="hit-top"><b>${esc(h.chat_name)}${h.sender ? ' · ' + esc(h.sender) : ''}</b><span>${fullTime(h.ts)}</span></div>
      <div class="hit-body">${highlight(h.content || '', q)}</div>
    </div>`).join('') + (S.hitOffset + S.hits.length < S.hitTotal
      ? `<div style="text-align:center;margin:14px"><button class="btn" id="moreHits">加载更多</button></div>` : '');

  box.querySelectorAll('.hit').forEach((el) => {
    el.onclick = async () => {
      const chatId = Number(el.dataset.chat);
      const ts = Number(el.dataset.ts);
      let chat = S.chats.find((c) => c.id === chatId);
      if (!chat) { await loadChats(); chat = S.chats.find((c) => c.id === chatId); }
      $('results').classList.remove('show');
      await selectChat(chat, { around: ts });
      setTimeout(() => flashTo(Number(el.dataset.id)), 120);
    };
  });
  const more = $('moreHits');
  if (more) more.onclick = () => runSearch(q, S.hitOffset + 40, chatScoped);
}

/* ---------------- 统计 ---------------- */
async function showStats() {
  const params = {};
  if (S.chat) params.chat_id = S.chat.id;
  const data = await api('stats', params);
  const max = Math.max(1, ...data.senders.map((s) => s.n));
  const bars = data.senders.map((s) => `
    <div class="bar-row">
      <div class="nm" title="${esc(s.sender)}">${esc(s.sender || '未标注')}</div>
      <div class="bar" style="width:${Math.max(3, (s.n / max) * 240)}px"></div>
      <div class="num">${s.n}</div>
    </div>`).join('');
  const years = data.yearly.map((y) => `<span style="margin-right:14px">${y.y || '未知'}：<b>${y.n}</b></span>`).join('');
  $('modal').innerHTML = `
    <h3>${S.chat ? esc(S.chat.name) + ' · 统计' : '全部聊天 · 统计'}</h3>
    <div style="margin-bottom:14px;color:#666;font-size:13px">${years || '暂无数据'}</div>
    <div style="font-size:13px;font-weight:600;margin:8px 0 6px">消息条数排行</div>
    ${bars || '<div class="empty">暂无</div>'}
    <div style="margin-top:18px;text-align:right"><button class="btn" onclick="document.getElementById('modalMask').classList.remove('show')">关闭</button></div>`;
  $('modalMask').classList.add('show');
}

/* ---------------- 事件绑定 ---------------- */
function bind() {
  $('globalSearch').addEventListener('input', onSearchInput);
  $('btnCloseResults').onclick = () => $('results').classList.remove('show');
  $('btnStats').onclick = showStats;
  $('modalMask').onclick = (e) => { if (e.target.id === 'modalMask') e.target.classList.remove('show'); };

  // 会话（群组/联系人）搜索
  let chatTimer = null;
  $('chatSearch').addEventListener('input', (e) => {
    clearTimeout(chatTimer);
    chatTimer = setTimeout(() => { S.chatQ = e.target.value.trim(); renderChats(); }, 120);
  });
  document.querySelectorAll('.kind-btn').forEach((btn) => {
    btn.onclick = () => {
      document.querySelectorAll('.kind-btn').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      S.chatKind = btn.dataset.kind;
      renderChats();
    };
  });

  $('inChatSearch').addEventListener('input', (e) => {
    const q = e.target.value.trim();
    if (!q || !S.chat) { $('results').classList.remove('show'); return; }
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => runSearch(q, 0, true), 260);
  });

  const applyDate = () => {
    const f = $('dateFrom').value, t = $('dateTo').value;
    S.filter.after = f ? Math.floor(new Date(f + 'T00:00:00').getTime() / 1000) : null;
    S.filter.before = t ? Math.floor(new Date(t + 'T23:59:59').getTime() / 1000) : null;
    if (S.chat) { S.msgs = []; S.hasMore = true; loadMessages({ limit: 200 }); }
  };
  $('dateFrom').onchange = applyDate;
  $('dateTo').onchange = applyDate;
  $('btnClearFilter').onclick = () => {
    $('dateFrom').value = ''; $('dateTo').value = ''; $('inChatSearch').value = '';
    S.filter = { after: null, before: null };
    if (S.chat) { S.msgs = []; S.hasMore = true; loadMessages({ limit: 80 }); }
    $('results').classList.remove('show');
  };

  $('messages').addEventListener('scroll', (e) => {
    const el = e.target;
    if (el.scrollTop < 120 && S.hasMore && !S.loading && S.msgs.length) {
      loadMessages({ before: S.msgs[0].ts });
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault(); $('globalSearch').focus();
    }
    if ((e.ctrlKey && e.key.toLowerCase() === 'k') ||
        (e.key === 'f' && document.activeElement.tagName !== 'INPUT' && !e.ctrlKey)) {
      e.preventDefault(); $('chatSearch').focus(); $('chatSearch').select();
    }
    if (e.key === 'Escape') {
      if (document.activeElement === $('chatSearch')) {
        $('chatSearch').value = ''; S.chatQ = ''; renderChats();
        document.activeElement.blur();
      }
      $('results').classList.remove('show');
      $('modalMask').classList.remove('show');
    }
  });
}

async function boot() {
  bind();
  try {
    S.meta = await api('meta');
    const m = S.meta;
    if (m.demo) {
      const b = $('banner');
      b.style.display = 'block';
      b.innerHTML = '当前是<b>演示数据</b>，用于预览界面。导入真实记录后会自动替换：<code>python app/importer.py 你的导出文件</code>';
    }
    $('metaInfo').textContent = m.messages
      ? `共 ${m.chats} 个会话 / ${m.messages} 条消息` : '';
  } catch (e) { /* ignore */ }
  await loadChats();
  if (S.chats.length) await selectChat(S.chats[0]);

  // 支持 URL 直达：?q=关键词 搜索，?stats=1 打开统计
  const qp = new URLSearchParams(location.search);
  const q = qp.get('q');
  if (q) {
    $('globalSearch').value = q;
    runSearch(q, 0);
  }
  if (qp.get('stats')) showStats();
  const cq = qp.get('chat');
  const ck = qp.get('kind');
  if (ck) {
    S.chatKind = ck;
    document.querySelectorAll('.kind-btn').forEach((b) => {
      b.classList.toggle('active', b.dataset.kind === ck);
    });
  }
  if (cq || ck) {
    if (cq) { $('chatSearch').value = cq; S.chatQ = cq; }
    renderChats();
  }
}

boot();
