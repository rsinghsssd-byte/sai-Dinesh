// ---- Config ----
const API_BASE = ""; // same-origin (FastAPI serves both API + this static frontend)
let currentJobId = null;
let currentResult = null;
let pollTimer = null;

// ---- DOM refs ----
const repoInputsEl = document.getElementById("repoInputs");
const addRepoBtn = document.getElementById("addRepoBtn");
const analyzeForm = document.getElementById("analyzeForm");
const languageSelect = document.getElementById("languageSelect");
const thresholdInput = document.getElementById("thresholdInput");
const thresholdVal = document.getElementById("thresholdVal");
const submitBtn = document.getElementById("submitBtn");
const progressWrap = document.getElementById("progressWrap");
const progressMsg = document.getElementById("progressMsg");
const progressPct = document.getElementById("progressPct");
const progressFill = document.getElementById("progressFill");
const errorBox = document.getElementById("errorBox");
const dashboardPanel = document.getElementById("dashboardPanel");
const detailPanel = document.getElementById("detailPanel");
const apiStatus = document.getElementById("apiStatus");
const historyPanel = document.getElementById("historyPanel");
const historyNavBtn = document.getElementById("historyNavBtn");

// ---- Init ----
window.addEventListener("DOMContentLoaded", async () => {
  await checkHealth();
  await loadLanguages();
  wireRepoInputs();
  thresholdInput.addEventListener("input", () => thresholdVal.textContent = thresholdInput.value);
  analyzeForm.addEventListener("submit", onSubmit);
  document.getElementById("closeDetailBtn").addEventListener("click", () => detailPanel.classList.add("hidden"));
  document.getElementById("downloadReportBtn").addEventListener("click", downloadReport);
  historyNavBtn.addEventListener("click", toggleHistory);
  document.getElementById("closeHistoryBtn").addEventListener("click", closeHistory);
});


async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`);
    if (res.ok) {
      apiStatus.innerHTML = `<span class="dot dot-ok"></span> backend online`;
    } else {
      throw new Error("not ok");
    }
  } catch {
    apiStatus.innerHTML = `<span class="dot dot-bad"></span> backend unreachable`;
  }
}

async function loadLanguages() {
  try {
    const res = await fetch(`${API_BASE}/api/languages`);
    const data = await res.json();
    languageSelect.innerHTML = data.languages
      .map(l => `<option value="${l}">${l[0].toUpperCase() + l.slice(1)}</option>`)
      .join("");
  } catch {
    languageSelect.innerHTML = `<option value="python">Python</option>`;
  }
}

// ---- Repo input rows ----
function wireRepoInputs() {
  addRepoBtn.addEventListener("click", () => {
    const rows = repoInputsEl.querySelectorAll(".repo-row").length;
    if (rows >= 20) return;
    addRepoRow();
  });
  repoInputsEl.addEventListener("click", (e) => {
    if (e.target.classList.contains("remove-repo")) {
      const rows = repoInputsEl.querySelectorAll(".repo-row");
      if (rows.length > 2) e.target.closest(".repo-row").remove();
    }
  });
}

function addRepoRow() {
  const row = document.createElement("div");
  row.className = "repo-row";
  row.innerHTML = `<input type="text" class="repo-url" placeholder="https://github.com/org/repo-name" required />
                    <button type="button" class="remove-repo" title="Remove">✕</button>`;
  repoInputsEl.appendChild(row);
}

// ---- Submit ----
async function onSubmit(e) {
  e.preventDefault();
  errorBox.classList.add("hidden");
  const urls = Array.from(document.querySelectorAll(".repo-url"))
    .map(i => i.value.trim())
    .filter(Boolean);

  const payload = {
    repo_urls: urls,
    language: languageSelect.value,
    branch: document.getElementById("branchInput").value.trim() || "main",
    similarity_threshold: parseFloat(thresholdInput.value),
  };

  submitBtn.disabled = true;
  submitBtn.textContent = "Submitting…";
  dashboardPanel.classList.add("hidden");
  detailPanel.classList.add("hidden");

  try {
    const res = await fetch(`${API_BASE}/api/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(formatApiError(data));
    }
    currentJobId = data.job_id;
    progressWrap.classList.remove("hidden");
    pollJob();
  } catch (err) {
    showError(err.message);
    resetSubmitBtn();
  }
}

function formatApiError(data) {
  if (data.detail) {
    if (Array.isArray(data.detail)) {
      return data.detail.map(d => d.msg).join("; ");
    }
    return data.detail;
  }
  return "Request failed.";
}

function showError(msg) {
  errorBox.textContent = msg;
  errorBox.classList.remove("hidden");
}

function resetSubmitBtn() {
  submitBtn.disabled = false;
  submitBtn.textContent = "Run analysis";
}

// ---- Poll job status ----
function pollJob() {
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${currentJobId}`);
      const data = await res.json();
      progressMsg.textContent = data.progress_message || data.status;
      progressPct.textContent = `${data.progress}%`;
      progressFill.style.width = `${data.progress}%`;

      if (data.status === "completed") {
        clearInterval(pollTimer);
        progressWrap.classList.add("hidden");
        resetSubmitBtn();
        await loadResult();
      } else if (data.status === "failed") {
        clearInterval(pollTimer);
        progressWrap.classList.add("hidden");
        resetSubmitBtn();
        showError(data.error || "Analysis failed.");
      }
    } catch (err) {
      clearInterval(pollTimer);
      resetSubmitBtn();
      showError("Lost connection to backend while polling job status.");
    }
  }, 1200);
}

async function loadResult() {
  const res = await fetch(`${API_BASE}/api/jobs/${currentJobId}/result`);
  const result = await res.json();
  currentResult = result;
  if (result.status !== "completed") {
    showError(result.error || "Analysis did not complete successfully.");
    return;
  }
  renderDashboard(result);
}

// ---- Dashboard rendering ----
function scoreColor(score) {
  if (score >= 0.75) return "var(--red)";
  if (score >= 0.5) return "var(--orange)";
  if (score >= 0.25) return "var(--yellow)";
  return "var(--green)";
}
function shortName(url) {
  return url.replace(/\/$/, "").split("/").slice(-2).join("/");
}

function renderDashboard(result) {
  dashboardPanel.classList.remove("hidden");
  const repos = result.repos_analyzed;
  const matrix = result.similarity_matrix;
  const threshold = result.similarity_threshold;

  // -- matrix table --
  let html = "<table class='matrix-table'><tr><th></th>";
  repos.forEach(r => html += `<th title="${r}">${shortName(r)}</th>`);
  html += "</tr>";
  repos.forEach(r => {
    html += `<tr><th class="row-head" title="${r}">${shortName(r)}</th>`;
    repos.forEach(c => {
      const score = matrix[r][c];
      if (r === c) {
        html += `<td class="cell-diag">—</td>`;
      } else {
        const flagged = score >= threshold ? "cell-flagged" : "";
        html += `<td class="cell-score ${flagged}" style="background:${scoreColor(score)}">${score.toFixed(2)}</td>`;
      }
    });
    html += "</tr>";
  });
  html += "</table>";
  document.getElementById("matrixContainer").innerHTML = html;

  // -- flagged pairs --
  const flaggedList = document.getElementById("flaggedList");
  const flagged = result.flagged_pairs_summary || [];
  if (!flagged.length) {
    flaggedList.innerHTML = `<div class="empty-note">No repository pairs exceeded the ${threshold} threshold.</div>`;
  } else {
    flaggedList.innerHTML = flagged.map(f => `
      <div class="flagged-item" data-key="${f.repo_a}||${f.repo_b}">
        <span class="names">${shortName(f.repo_a)} &harr; ${shortName(f.repo_b)}<br/>
          <span style="color:var(--muted)">${f.flagged_files} file(s) flagged</span></span>
        <span class="score-pill" style="background:${scoreColor(f.score)}">${f.score.toFixed(2)}</span>
      </div>
    `).join("");
    flaggedList.querySelectorAll(".flagged-item").forEach(el => {
      el.addEventListener("click", () => openDetail(el.dataset.key));
    });
  }

  // -- large commit flags --
  const commitFlags = document.getElementById("commitFlags");
  const flags = result.large_commit_flags || [];
  if (!flags.length) {
    commitFlags.innerHTML = `<div class="empty-note">No unusually large or sudden commits detected.</div>`;
  } else {
    commitFlags.innerHTML = flags.map(f => `
      <div class="commit-flag">
        <span class="msg">"${escapeHtml(f.message.slice(0, 90))}"<br/><span class="repo">${shortName(f.repo)} · ${f.sha}</span></span>
        <span>${f.lines_added} lines</span>
        <span class="z">z=${f.z_score}</span>
      </div>
    `).join("");
  }

  dashboardPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- Detail view ----
function openDetail(pairKey) {
  const pair = currentResult.repo_pairs[pairKey];
  if (!pair) return;
  detailPanel.classList.remove("hidden");
  document.getElementById("detailTitle").textContent =
    `${shortName(pair.repo_a)} ↔ ${shortName(pair.repo_b)} — score ${pair.repo_similarity_score.toFixed(2)}`;

  let html = "";

  // file-wise similarity table
  html += `<div class="detail-section"><h4>File-wise similarity</h4>`;
  if (!pair.flagged_file_pairs.length) {
    html += `<div class="empty-note">No file pairs exceeded the threshold.</div>`;
  } else {
    html += `<table class="file-table"><tr><th>File A</th><th>File B</th><th>Score</th><th>Containment</th><th>Jaccard</th></tr>`;
    pair.flagged_file_pairs.forEach(fp => {
      html += `<tr>
        <td>${escapeHtml(fp.file_a)}</td><td>${escapeHtml(fp.file_b)}</td>
        <td class="num" style="color:${scoreColor(fp.score)}">${fp.score.toFixed(2)}</td>
        <td class="num">${fp.containment.toFixed(2)}</td>
        <td class="num">${fp.jaccard.toFixed(2)}</td>
      </tr>`;
    });
    html += `</table>`;
  }
  html += `</div>`;

  // commit-wise indicators
  html += `<div class="detail-section"><h4>Commit-wise indicators</h4>`;
  if (!pair.commit_message_matches.length) {
    html += `<div class="empty-note">No near-identical commit messages found between these two repositories.</div>`;
  } else {
    pair.commit_message_matches.forEach(m => {
      html += `<div class="commit-msg-row">
        <span>${m.sha_a} — "${escapeHtml(m.message_a.slice(0,60))}"</span>
        <span class="sim">${(m.similarity*100).toFixed(0)}%</span>
        <span>${m.sha_b} — "${escapeHtml(m.message_b.slice(0,60))}"</span>
      </div>`;
    });
  }
  html += `</div>`;

  // note about side-by-side code view
  html += `<div class="detail-section"><h4>Side-by-side comparison</h4>
    <div class="empty-note">Full highlighted source is included in the downloadable report for each flagged file pair listed above (containment/jaccard scores link back to the exact matching regions detected by the fingerprinting engine).</div>
  </div>`;

  document.getElementById("detailBody").innerHTML = html;
  detailPanel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, c => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
}

// ---- Report download ----
function downloadReport() {
  if (!currentJobId) return;
  window.location.href = `${API_BASE}/api/jobs/${currentJobId}/report`;
}

// ---- History panel ----
function toggleHistory() {
  const isOpen = !historyPanel.classList.contains("hidden");
  if (isOpen) {
    closeHistory();
  } else {
    openHistory();
  }
}

function openHistory() {
  historyPanel.classList.remove("hidden");
  historyNavBtn.classList.add("active");
  historyPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  loadHistory();
}

function closeHistory() {
  historyPanel.classList.add("hidden");
  historyNavBtn.classList.remove("active");
}

async function loadHistory() {
  const loadingEl = document.getElementById("historyLoading");
  const emptyEl = document.getElementById("historyEmpty");
  const listEl = document.getElementById("historyList");

  loadingEl.classList.remove("hidden");
  emptyEl.classList.add("hidden");
  listEl.innerHTML = "";

  try {
    const res = await fetch(`${API_BASE}/api/jobs`);
    if (!res.ok) throw new Error("Failed to fetch history");
    const jobs = await res.json();

    loadingEl.classList.add("hidden");

    if (!jobs.length) {
      emptyEl.classList.remove("hidden");
      return;
    }

    listEl.innerHTML = jobs.map(job => renderHistoryItem(job)).join("");
  } catch (err) {
    loadingEl.classList.add("hidden");
    listEl.innerHTML = `<div class="error-box" style="margin:0">Could not load history: ${escapeHtml(err.message)}</div>`;
  }
}

function renderHistoryItem(job) {
  const req = job.request || {};
  const repos = (req.repo_urls || []);
  const lang = req.language || "—";
  const branch = req.branch || "main";
  const threshold = req.similarity_threshold != null ? req.similarity_threshold : "—";
  const createdAt = formatTimestamp(job.created_at);
  const updatedAt = formatTimestamp(job.updated_at);
  const statusClass = `status-${job.status}`;
  const repoCount = repos.length;

  const repoTags = repos.map(url => {
    const label = url.replace(/\/$/, "").split("/").slice(-2).join("/");
    return `<span class="repo-tag">
      <span class="repo-tag-icon">⎇</span>
      <a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(label)}</a>
    </span>`;
  }).join("");

  return `
    <div class="history-item">
      <div class="history-item-top">
        <div class="history-item-meta">
          <span class="status-pill ${statusClass}">${job.status}</span>
          <span class="history-time">
            <strong>Started:</strong> ${createdAt}
          </span>
          ${job.updated_at !== job.created_at
            ? `<span class="history-time"><strong>Finished:</strong> ${updatedAt}</span>`
            : ""}
        </div>
        <span class="history-time" style="color:var(--amber)">
          ${repoCount} repo${repoCount !== 1 ? "s" : ""}
        </span>
      </div>

      <div class="history-repos">
        ${repoTags || '<span class="history-time">No repos recorded</span>'}
      </div>

      <div class="history-item-footer">
        <span>🌐 ${escapeHtml(lang)}</span>
        <span>⎇ branch: ${escapeHtml(branch)}</span>
        <span>⚖ threshold: ${threshold}</span>
        <span style="margin-left:auto;color:var(--muted);font-size:10.5px">id: ${job.id.slice(0,8)}…</span>
      </div>
    </div>
  `;
}

function formatTimestamp(isoStr) {
  if (!isoStr) return "—";
  try {
    const d = new Date(isoStr.endsWith("Z") ? isoStr : isoStr + "Z");
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit", second: "2-digit"
    });
  } catch {
    return isoStr;
  }
}

