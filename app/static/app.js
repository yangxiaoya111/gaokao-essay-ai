const $ = (id) => document.getElementById(id);

// ---- DOM 引用 ----
const topicEl = $("topic");
const styleEl = $("style");
const wordCountEl = $("word_count");
const generateBtn = $("generate");
const resultEl = $("result");
const metaEl = $("meta");
const copyBtn = $("copy");

const welcomeEl = $("welcome");
const btnLogin = $("btn-login");
const btnRegister = $("btn-register");
const btnHistory = $("btn-history");
const btnLogout = $("btn-logout");
const historyCard = $("history-card");
const historyList = $("history-list");

const authModal = $("auth-modal");
const authTitle = $("auth-title");
const authUsername = $("auth-username");
const authPassword = $("auth-password");
const authError = $("auth-error");
const authSubmit = $("auth-submit");

let lastFullText = "";
let authMode = "login"; // login | register

// ---- 认证状态 ----
function getToken() {
  return localStorage.getItem("gaokao_token") || "";
}
function getAuthUser() {
  try {
    return JSON.parse(localStorage.getItem("gaokao_user") || "null");
  } catch {
    return null;
  }
}
function setAuth(token, user) {
  localStorage.setItem("gaokao_token", token);
  localStorage.setItem("gaokao_user", JSON.stringify(user));
}
function clearAuth() {
  localStorage.removeItem("gaokao_token");
  localStorage.removeItem("gaokao_user");
}
function authHeaders() {
  return { "Content-Type": "application/json", Authorization: "Bearer " + getToken() };
}

function updateAuthUI() {
  const user = getAuthUser();
  const loggedIn = !!getToken() && !!user;
  welcomeEl.style.display = loggedIn ? "" : "none";
  btnLogin.style.display = loggedIn ? "none" : "";
  btnRegister.style.display = loggedIn ? "none" : "";
  btnHistory.style.display = loggedIn ? "" : "none";
  btnLogout.style.display = loggedIn ? "" : "none";
  historyCard.style.display = loggedIn ? "" : "none";
  if (loggedIn) welcomeEl.textContent = `欢迎，${user.username}`;
  if (loggedIn) loadHistory();
}

// ---- 工具 ----
function escapeHtml(text) {
  return text.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}
function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

// ---- 生成作文 ----
async function generate() {
  const topic = topicEl.value.trim();
  if (!topic) {
    resultEl.innerHTML = '<p class="error">请先输入作文题目。</p>';
    topicEl.focus();
    return;
  }

  generateBtn.disabled = true;
  copyBtn.disabled = true;
  lastFullText = "";
  metaEl.textContent = "";
  resultEl.innerHTML = '<div class="spinner">⏳ 正在生成中，请稍候（通常需要 10～30 秒）……</div>';

  const loggedIn = !!getToken();
  const body = JSON.stringify({
    topic,
    style: styleEl.value,
    word_count: parseInt(wordCountEl.value, 10),
  });

  try {
    const resp = await fetch(loggedIn ? "/api/essays" : "/api/generate", {
      method: "POST",
      headers: authHeaders(),
      body,
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "生成失败");

    let title, content, charCount, elapsed, demo;
    if (loggedIn) {
      const e = data.essay;
      title = e.title;
      content = e.content;
      charCount = e.char_count;
      elapsed = data.elapsed;
      demo = data.demo;
    } else {
      title = data.title;
      content = data.content;
      charCount = data.char_count;
      elapsed = data.elapsed;
      demo = data.demo;
    }

    lastFullText = title + "\n\n" + content;
    renderEssay(title, content, charCount, elapsed, demo);
    copyBtn.disabled = false;
    if (loggedIn) loadHistory(); // 生成后刷新历史
  } catch (err) {
    resultEl.innerHTML = `<p class="error">生成失败：${escapeHtml(String(err.message || err))}</p>`;
  } finally {
    generateBtn.disabled = false;
  }
}

function renderEssay(title, content, charCount, elapsed, demo) {
  const paras = content
    .split(/\n+/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => `<p>${escapeHtml(p)}</p>`)
    .join("\n");

  metaEl.textContent = `约 ${charCount} 字 · 用时 ${elapsed}s${demo ? " · 演示模式" : ""}`;

  resultEl.innerHTML = `
    ${demo ? '<p class="demo-badge">演示模式：未配置 API Key，显示示例作文</p>' : ""}
    <h3 class="essay-title">${escapeHtml(title || "（未命名）")}</h3>
    <div class="essay-body">${paras}</div>
  `;
}

async function copyText() {
  if (!lastFullText) return;
  try {
    await navigator.clipboard.writeText(lastFullText);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = lastFullText;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  const old = copyBtn.textContent;
  copyBtn.textContent = "已复制 ✓";
  setTimeout(() => (copyBtn.textContent = old), 1500);
}

// ---- 认证弹窗 ----
function openAuth(mode) {
  authMode = mode;
  authTitle.textContent = mode === "login" ? "登录" : "注册";
  authSubmit.textContent = mode === "login" ? "登录" : "注册";
  authError.style.display = "none";
  authError.textContent = "";
  setTabActive(mode);
  authModal.style.display = "flex";
}
function closeAuth() {
  authModal.style.display = "none";
}
function setTabActive(mode) {
  $("tab-login").classList.toggle("active", mode === "login");
  $("tab-register").classList.toggle("active", mode === "register");
}

async function submitAuth() {
  const username = authUsername.value.trim();
  const password = authPassword.value;
  authError.style.display = "none";
  if (!username || !password) {
    authError.textContent = "请填写用户名和密码";
    authError.style.display = "";
    return;
  }
  try {
    const resp = await fetch("/api/auth/" + authMode, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "操作失败");
    setAuth(data.token, data.user);
    closeAuth();
    authUsername.value = "";
    authPassword.value = "";
    updateAuthUI();
  } catch (err) {
    authError.textContent = String(err.message || err);
    authError.style.display = "";
  }
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST", headers: authHeaders() });
  } catch {
    /* 忽略网络错误 */
  }
  clearAuth();
  historyList.innerHTML = "";
  updateAuthUI();
}

// ---- 历史记录 ----
async function loadHistory() {
  if (!getToken()) return;
  try {
    const resp = await fetch("/api/essays", { headers: authHeaders() });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "加载失败");
    renderHistory(data.essays || []);
  } catch (err) {
    historyList.innerHTML = `<p class="error">加载历史失败：${escapeHtml(String(err.message || err))}</p>`;
  }
}

function renderHistory(essays) {
  if (!essays.length) {
    historyList.innerHTML = '<p class="history-empty">暂无历史记录，生成一篇作文后会自动保存到这里。</p>';
    return;
  }
  historyList.innerHTML = essays.map((e) => `
    <div class="history-item" data-id="${escapeHtml(String(e.id))}">
      <div class="h-main">
        <div class="h-title">${escapeHtml(e.title || "（未命名）")}</div>
        <div class="h-topic">题目：${escapeHtml(e.topic || "")}</div>
        <div class="h-meta">${escapeHtml(e.style || "")} · 约 ${e.char_count || 0} 字 · ${escapeHtml(fmtDate(e.created_at))}</div>
      </div>
      <div class="h-actions">
        <button class="btn-small" data-action="view">查看</button>
        <button class="btn-small danger" data-action="delete">删除</button>
      </div>
    </div>
  `).join("");
}

async function viewEssay(id) {
  try {
    const resp = await fetch("/api/essays/" + id, { headers: authHeaders() });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "加载失败");
    const e = data.essay;
    lastFullText = (e.title || "") + "\n\n" + (e.content || "");
    renderEssay(e.title, e.content, e.char_count, 0, false);
    copyBtn.disabled = false;
    resultEl.scrollIntoView({ behavior: "smooth" });
  } catch (err) {
    alert("加载失败：" + (err.message || err));
  }
}

async function deleteEssay(id) {
  if (!confirm("确定删除这篇作文吗？")) return;
  try {
    const resp = await fetch("/api/essays/" + id, { method: "DELETE", headers: authHeaders() });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "删除失败");
    loadHistory();
  } catch (err) {
    alert("删除失败：" + (err.message || err));
  }
}

// ---- 事件绑定 ----
generateBtn.addEventListener("click", generate);
copyBtn.addEventListener("click", copyText);
btnLogin.addEventListener("click", () => openAuth("login"));
btnRegister.addEventListener("click", () => openAuth("register"));
btnLogout.addEventListener("click", logout);
btnHistory.addEventListener("click", () => historyCard.scrollIntoView({ behavior: "smooth" }));
$("refresh-history").addEventListener("click", loadHistory);
$("auth-close").addEventListener("click", closeAuth);
$("tab-login").addEventListener("click", () => { authMode = "login"; openAuth("login"); });
$("tab-register").addEventListener("click", () => { authMode = "register"; openAuth("register"); });
authSubmit.addEventListener("click", submitAuth);
authPassword.addEventListener("keydown", (e) => { if (e.key === "Enter") submitAuth(); });

historyList.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const id = e.target.closest(".history-item").dataset.id;
  if (btn.dataset.action === "view") viewEssay(id);
  if (btn.dataset.action === "delete") deleteEssay(id);
});

// Ctrl+Enter 快捷生成
topicEl.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") generate();
});

// 支持 URL 参数自动生成（便于演示与截图）：/?topic=xxx&style=议论文&word_count=800
(function autoRunFromQuery() {
  const params = new URLSearchParams(window.location.search);
  const topic = params.get("topic");
  if (!topic) return;
  topicEl.value = topic;
  if (params.get("style")) styleEl.value = params.get("style");
  if (params.get("word_count")) wordCountEl.value = params.get("word_count");
  window.addEventListener("load", () => setTimeout(generate, 300));
})();

// 支持 URL 参数自动打开登录/注册弹窗（便于演示与截图）：/?auth=login 或 /?auth=register
(function autoOpenAuth() {
  const p = new URLSearchParams(window.location.search);
  const mode = p.get("auth");
  if (mode === "login" || mode === "register") {
    window.addEventListener("load", () => setTimeout(() => openAuth(mode), 300));
  }
})();

// 初始化
updateAuthUI();
