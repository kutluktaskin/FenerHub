/* Panel aç/kapat */
window.toggleForum = function () {
  const f = document.getElementById("fchat");
  if (!f) return;
  const open = !f.classList.contains("open");
  f.classList.toggle("open", open);
  document.body.classList.toggle("fchat-open", open);
  try { localStorage.setItem("fhChatOpen", open ? "1" : "0"); } catch (e) {}
  if (open) {
    const feed = document.getElementById("forumFeed");
    if (feed) feed.scrollTop = feed.scrollHeight;
  }
};

(() => {
  const API = API_BASE; // api.js'de tanımlı (önce yüklenir)
  const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/forum";
  const ROOMS = [
    { key: "genel", label: "Genel" },
    { key: "mac", label: "Gelecek Maç" },
    { key: "transfer", label: "Transfer" }
  ];
  const SHORT = { "Fenerbahçe": "FB", "Galatasaray": "GS", "Beşiktaş": "BJK", "Trabzonspor": "TS" };
  const MAX_DOM = 200;
  console.log("12. Adam (forum.js v8) yüklendi");
  let tabKey = "genel", room = "genel", nextMatch = null, ws, stick = true, replyTo = null;
  
  const mine = new Set();
  try { JSON.parse(localStorage.getItem("fhMine") || "[]").forEach(i => mine.add(i)); } catch (e) {}
  function saveMine() {
    try { localStorage.setItem("fhMine", JSON.stringify([...mine].slice(-300))); } catch (e) {}
  }

  const $ = id => document.getElementById(id);
  let feed, err, newBtn, replyBar;

  let ownerMem = null;
  function owner() {
    try {
      let t = localStorage.getItem("fhOwner");
      if (!t) {
        t = (crypto.randomUUID ? crypto.randomUUID() : (Math.random().toString(36).slice(2) + Date.now().toString(36) + "xxxxxxxx"));
        localStorage.setItem("fhOwner", t);
      }
      return t;
    } catch (e) {
      if (!ownerMem) ownerMem = Math.random().toString(36).slice(2) + Date.now().toString(36) + "xxxxxxxx";
      return ownerMem;
    }
  }

  function ago(ts) {
    const s = Math.max(1, Math.floor(Date.now() / 1000 - ts));
    if (s < 60) return "şimdi";
    if (s < 3600) return Math.floor(s / 60) + " dk";
    if (s < 86400) return Math.floor(s / 3600) + " sa";
    return Math.floor(s / 86400) + " gün";
  }
  const nearBottom = () => feed.scrollHeight - feed.scrollTop - feed.clientHeight < 80;
  function scrollBottom() { feed.scrollTop = feed.scrollHeight; newBtn.hidden = true; }

  function info(text) {
    feed.textContent = "";
    const n = document.createElement("div");
    n.className = "fchat-empty";
    n.textContent = text;
    feed.append(n);
  }

  // html: sadece sabit ikon + sayı (kullanıcı metni buraya girmez)
  function mkBtn(cls, html, title, onclick) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = cls;
    b.innerHTML = html;
    if (title) { b.title = title; b.setAttribute("aria-label", title); }
    b.onclick = onclick;
    return b;
  }

  const reactLabel = (type, count) => `${icon(type === "fire" ? "flame" : "heart")}<span>${Number(count) || 0}</span>`;

  function postEl(p) {
    const isMine = p.mine || mine.has(p.id);
    if (isMine) mine.add(p.id);

    const el = document.createElement("article");
    el.className = "fc2-msg" + (isMine ? " is-mine" : "") + (p.deleted ? " is-deleted" : "");
    el.dataset.id = p.id;

    const main = document.createElement("div");
    main.className = "fc2-main";

    const head = document.createElement("div");
    head.className = "fc2-head";
    
    const nick = document.createElement("strong");
    nick.className = "fc2-nick";
    nick.textContent = p.nick;
    head.append(nick);

    const rightMeta = document.createElement("div");
    rightMeta.className = "fc2-right-meta";

    if (isMine) {
      const you = document.createElement("span");
      you.className = "fc2-you";
      you.textContent = "Sen";
      rightMeta.append(you);
    }
    const time = document.createElement("span");
    time.className = "fc2-time fchat-time";
    time.dataset.ts = p.ts;
    time.textContent = ago(p.ts);
    rightMeta.append(time);
    
    head.append(rightMeta);
    main.append(head);

    if (p.parent_id) {
      const q = document.createElement("div");
      q.className = "fc2-quote";
      q.dataset.parent = p.parent_id;
      const qn = document.createElement("b");
      qn.textContent = "Yanıt: " + (p.parent_nick || "");
      const qb = document.createElement("span");
      qb.className = "fc2-quote-body";
      qb.textContent = p.parent_deleted ? "Bu mesaj silindi" : (p.parent_body || "");
      if (p.parent_deleted) qb.classList.add("gone");
      q.append(qn, qb);
      q.onclick = () => jumpTo(p.parent_id);
      main.append(q);
    }

    const body = document.createElement("p");
    body.className = "fc2-body";
    body.textContent = p.deleted ? "Bu mesaj silindi" : p.body;
    main.append(body);

    if (!p.deleted) {
      const acts = document.createElement("div");
      acts.className = "fc2-acts";
      
      // Backend sadece fire ve heart tepkilerini kabul ediyor
      [
        ["fire", p.fire, "Ateş ver"],
        ["heart", p.heart, "Beğen"]
      ].forEach(([type, count, title]) => {
        const b = mkBtn("fc2-react", reactLabel(type, count), title, () => react(p.id, type));
        b.dataset.type = type;
        acts.append(b);
      });

      acts.append(mkBtn("fc2-act", icon("reply"), "Yanıtla", () => setReply(p)));

      // Backend başkasının mesajını silmeye izin vermez (403)
      if (isMine) {
        acts.append(mkBtn("fc2-act fc2-del", icon("trash"), "Sil", (e) => removePost(p.id, e)));
      }
      main.append(acts);
    }

    el.append(main);
    return el;
  }

  function markDeleted(id) {
    const el = feed.querySelector(`.fc2-msg[data-id="${id}"]`);
    if (el) el.remove();
    if (mine.delete(id)) saveMine();
    feed.querySelectorAll(`.fc2-quote[data-parent="${id}"] .fc2-quote-body`).forEach(s => {
      s.textContent = "Bu mesaj silindi";
      s.classList.add("gone");
    });
    if (replyTo && replyTo.id === id) clearReply();
    if (!feed.querySelector(".fc2-msg")) info("Bu odada henüz mesaj yok. İlk yazan sen ol!");
  }

  function jumpTo(id) {
    const el = feed.querySelector(`.fc2-msg[data-id="${id}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.remove("flash");
    void el.offsetWidth;
    el.classList.add("flash");
  }

  function setReply(p) {
    replyTo = { id: p.id, nick: p.nick, body: p.body };
    replyBar.textContent = "";
    const t = document.createElement("div");
    t.className = "fc2-reply-text";
    const b = document.createElement("b");
    b.textContent = `${p.nick} adlı kullanıcıya yanıt`;
    const s = document.createElement("span");
    s.textContent = p.body.slice(0, 70);
    t.append(b, s);
    const x = mkBtn("fc2-reply-x", icon("x"), "Yanıtı iptal et", clearReply);
    replyBar.append(t, x);
    replyBar.hidden = false;
    $("forumText").focus();
  }
  function clearReply() {
    replyTo = null;
    if (replyBar) { replyBar.hidden = true; replyBar.textContent = ""; }
  }

  function addPost(p) {
    const empty = feed.querySelector(".fchat-empty");
    if (empty) empty.remove();
    if (feed.querySelector(`[data-id="${p.id}"]`)) return;
    const wasNear = nearBottom();
    feed.append(postEl(p));
    while (feed.children.length > MAX_DOM) feed.firstChild.remove();
    if (stick || wasNear) { scrollBottom(); stick = false; }
    else newBtn.hidden = false;
  }

  async function load() {
    if (!room) { info("Yaklaşan maç bulunamadı."); return; }
    info("Yükleniyor...");
    try {
      const r = await fetch(`${API}/api/forum/posts?room=${encodeURIComponent(room)}&owner=${encodeURIComponent(owner())}`);
      if (!r.ok) throw new Error();
      const posts = (await r.json()).reverse().filter(p => !p.deleted);
      feed.textContent = "";
      if (!posts.length) info("Bu odada henüz mesaj yok. İlk yazan sen ol!");
      posts.forEach(p => feed.append(postEl(p)));
      scrollBottom();
    } catch {
      info("Forum sunucusuna bağlanılamadı.");
    }
  }

  async function send(e) {
    if (e && typeof e.preventDefault === 'function') e.preventDefault();
    err.textContent = "";
    const nick = $("forumNick").value.trim(), body = $("forumText").value.trim();
    if (!room) { err.textContent = "Bu sekmede şu an oda yok."; return; }
    if (nick.length < 2 || !body) { err.textContent = "Takma ad (min 2 harf) ve mesaj gerekli."; return; }
    try { localStorage.setItem("fhNick", nick); } catch (e) {}
    try {
      const r = await fetch(`${API}/api/forum/posts`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room, nick, body, owner: owner(), parent_id: replyTo ? replyTo.id : null })
      });
      if (!r.ok) {
        const d = (await r.json()).detail;
        err.textContent = typeof d === "string" ? d : "Gönderilemedi.";
        return;
      }
      const p = await r.json();
      mine.add(p.id);
      saveMine();
      p.mine = true;
      $("forumText").value = "";
      clearReply();
      const ex = feed.querySelector(`.fc2-msg[data-id="${p.id}"]`);
      if (ex) ex.replaceWith(postEl(p));
      else addPost(p);
      scrollBottom();
    } catch { err.textContent = "Sunucuya bağlanılamadı."; }
  }

  async function removePost(id, e) {
    if (e) e.preventDefault();
    if (!confirm("Bu mesajı silmek istiyor musun?")) return;
    err.textContent = "";
    try {
      const r = await fetch(`${API}/api/forum/posts/${id}/delete`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ owner: owner() })
      });
      if (!r.ok) {
        let d = null;
        try { d = (await r.json()).detail; } catch (e) {}
        err.textContent = (typeof d === "string" ? d : "Silinemedi.") + ` (HTTP ${r.status})`;
        return;
      }
      markDeleted(id);
    } catch { err.textContent = "Sunucuya bağlanılamadı."; }
  }

  function react(id, type) {
    const k = `fhR${id}${type}`;
    try { if (localStorage.getItem(k)) return; localStorage.setItem(k, "1"); } catch (e) {}
    fetch(`${API}/api/forum/posts/${id}/react`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type })
    }).catch(() => {});
  }

  function connect() {
    try { ws = new WebSocket(WS_URL); } catch { return; }
    ws.onmessage = e => {
      const m = JSON.parse(e.data);
      if (m.type === "online") $("forumOnline").textContent = m.count;
      if (m.type === "post" && m.post.room === room) addPost(m.post);
      if (m.type === "delete") markDeleted(m.id);
      if (m.type === "react") {
        const el = feed.querySelector(`.fc2-msg[data-id="${m.id}"]`);
        if (el) {
          const f = el.querySelector('[data-type="fire"]');
          const h = el.querySelector('[data-type="heart"]');
          if (f) f.innerHTML = reactLabel("fire", m.fire);
          if (h) h.innerHTML = reactLabel("heart", m.heart);
        }
      }
    };
    ws.onclose = () => setTimeout(connect, 2000);
  }

  const roomFor = key => key === "mac" ? (nextMatch && nextMatch.room) : key;

  async function refreshMatch() {
    try {
      const m = await (await fetch(`${API}/api/forum/next-match`)).json();
      const changed = (nextMatch && nextMatch.room) !== m.room;
      nextMatch = m.room ? m : null;
      const btn = $("forumRooms").querySelector('[data-key="mac"]');
      const label = nextMatch ? (SHORT[nextMatch.opponent] || nextMatch.opponent) : "Gelecek Maç";
      if (btn) btn.textContent = label;
      if (changed && tabKey === "mac") { room = roomFor("mac"); clearReply(); load(); }
    } catch {}
  }

  function init() {
    feed = $("forumFeed"); err = $("forumError"); newBtn = $("forumNew");
    if (!feed) return;

    replyBar = document.createElement("div");
    replyBar.className = "fc2-reply-bar";
    replyBar.hidden = true;
    const nickEl = $("forumNick");
    nickEl.parentNode.insertBefore(replyBar, nickEl);

    const roomsEl = $("forumRooms");
    ROOMS.forEach(({ key, label }) => {
      const b = document.createElement("button");
      b.textContent = label;
      b.dataset.key = key;
      if (key === tabKey) b.classList.add("on");
      b.onclick = () => {
        tabKey = key;
        room = roomFor(key);
        roomsEl.querySelectorAll("button").forEach(x => x.classList.remove("on"));
        b.classList.add("on");
        clearReply();
        load();
      };
      roomsEl.append(b);
    });

    let nick = "";
    try { nick = localStorage.getItem("fhNick") || ""; } catch (e) {}
    nickEl.value = nick;
    $("forumSend").onclick = (e) => send(e);
    $("forumText").addEventListener("keydown", e => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(e); }
    });
    newBtn.onclick = scrollBottom;
    feed.addEventListener("scroll", () => { if (nearBottom()) newBtn.hidden = true; });

    setInterval(() => {
      feed.querySelectorAll(".fchat-time").forEach(t => t.textContent = ago(+t.dataset.ts));
    }, 30000);

    let saved = null;
    try { saved = localStorage.getItem("fhChatOpen"); } catch (e) {}
    const wantOpen = saved === null ? window.innerWidth >= 1400 : saved === "1";
    if (wantOpen) window.toggleForum();

    refreshMatch();
    setInterval(refreshMatch, 60 * 1000);
    load(); connect();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();