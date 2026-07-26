/* BCI RegIntel UI */
const DATA_BASE = "data";

const TABS = {
  pdfs: {
    file: "pdfs_catalog.json",
    label: "PDFs",
    filters: [
      { key: "jurisdiction", label: "All jurisdictions" },
      { key: "source_kind", label: "All source kinds" },
      { key: "_none", label: "—" },
    ],
    columns: [
      { key: "title", label: "Title" },
      { key: "jurisdiction", label: "Jurisdiction" },
      { key: "source_kind", label: "Source" },
      { key: "filename", label: "File" },
      { key: "bytes", label: "Bytes" },
      { key: "downloaded_at", label: "Downloaded" },
      { key: "open_url", label: "Open PDF", type: "url" },
      { key: "url", label: "Source URL", type: "url" },
    ],
  },
  tracking: {
    file: "tracking.json",
    label: "Tracking log",
    filters: [
      { key: "country", label: "All countries" },
      { key: "law_area", label: "All law areas" },
      { key: "relevancy", label: "All relevancy" },
    ],
    columns: [
      { key: "date_of_tracking", label: "Tracked" },
      { key: "country", label: "Country" },
      { key: "federal_or_state", label: "Fed/State" },
      { key: "law_area", label: "Law area" },
      { key: "topical_relevance", label: "Topic" },
      { key: "remarks", label: "Remarks / update" },
      { key: "link", label: "Link", type: "url" },
      { key: "relevancy", label: "Relevancy", type: "badge" },
      { key: "tracked_by", label: "Tracked by" },
      { key: "comments", label: "Comments" },
      { key: "cor_impact", label: "COR impact" },
      { key: "alert_status", label: "Alert", type: "badge" },
    ],
  },
  primary: {
    file: "primary_sources.json",
    label: "Primary sources",
    filters: [
      { key: "region", label: "All regions" },
      { key: "jurisdiction", label: "All jurisdictions" },
      { key: "status", label: "All statuses" },
    ],
    columns: [
      { key: "region", label: "Region" },
      { key: "jurisdiction", label: "Jurisdiction" },
      { key: "authority", label: "Authority" },
      { key: "authority_type", label: "Type" },
      { key: "link_nature", label: "Link nature" },
      { key: "segment", label: "Segment" },
      { key: "topics", label: "Topics", type: "list" },
      { key: "frequency", label: "Frequency" },
      { key: "url", label: "Website", type: "url" },
      { key: "status", label: "Status", type: "badge" },
    ],
  },
  updates: {
    file: "updates.json",
    label: "Collector updates",
    filters: [
      { key: "region", label: "All regions" },
      { key: "country", label: "All countries" },
      { key: "relevancy", label: "All relevancy" },
    ],
    columns: [
      { key: "discovered_at", label: "Discovered" },
      { key: "country", label: "Country" },
      { key: "authority", label: "Authority" },
      { key: "title", label: "Title" },
      { key: "law_area", label: "Law area" },
      { key: "topical_relevance", label: "Topics" },
      { key: "link", label: "Link", type: "url" },
      { key: "relevancy", label: "Relevancy", type: "badge" },
      { key: "alert_status", label: "Status", type: "badge" },
      { key: "tracked_by", label: "By" },
    ],
  },
  gazette: {
    file: "gazette.json",
    label: "Gazette",
    filters: [
      { key: "jurisdiction", label: "All jurisdictions" },
      { key: "source_kind", label: "All kinds" },
      { key: "_none", label: "—" },
    ],
    columns: [
      { key: "jurisdiction", label: "Jurisdiction" },
      { key: "parliamentary_bills", label: "Parliamentary bills", type: "url" },
      { key: "official_gazette", label: "Official gazette", type: "url" },
      { key: "legal_databases", label: "Legal databases", type: "url" },
    ],
  },
  secondary: {
    file: "secondary_sources.json",
    label: "Secondary",
    filters: [
      { key: "coverage_area", label: "All areas" },
      { key: "status", label: "All statuses" },
      { key: "_none", label: "—" },
    ],
    columns: [
      { key: "name", label: "Source" },
      { key: "coverage_area", label: "Coverage" },
      { key: "url", label: "Link", type: "url" },
      { key: "status", label: "Status", type: "badge" },
    ],
  },
  plan: {
    file: "detailed_plan.json",
    label: "Detailed plan",
    filters: [
      { key: "Workstream", label: "All workstreams" },
      { key: "Sub-Categories", label: "All sub-categories" },
      { key: "Tracking Frequency", label: "All frequencies" },
    ],
    columns: [
      { key: "Workstream", label: "Workstream" },
      { key: "Sub-Categories", label: "Sub-category" },
      { key: "FLR", label: "FLR" },
      { key: "SLR", label: "SLR" },
      { key: "# of URLs", label: "# URLs" },
      { key: "Tracking Frequency", label: "Frequency" },
      { key: "Country Coverage", label: "Country coverage" },
    ],
  },
};

const state = {
  tab: "pdfs",
  cache: {},
  meta: null,
  sortKey: null,
  sortDir: 1,
  page: 1,
  pageSize: 50,
  search: "",
  f1: "",
  f2: "",
  f3: "",
};

const $ = (sel) => document.querySelector(sel);

async function fetchJSON(name) {
  const res = await fetch(`${DATA_BASE}/${name}?t=${Date.now()}`);
  if (!res.ok) throw new Error(`Failed to load ${name}: ${res.status}`);
  return res.json();
}

function badgeClass(val) {
  const v = String(val || "").toLowerCase();
  if (v === "relevant" || v === "active" || v === "ok") return "relevant";
  if (v.includes("not relevant") || v === "broken" || v === "fail") return "not";
  if (v === "pending" || v === "seed") return "pending";
  if (v === "new") return "new";
  if (v === "active") return "active";
  return "pending";
}

function cellHTML(val, type) {
  if (val == null || val === "") return '<span class="muted">—</span>';
  if (type === "list" && Array.isArray(val)) {
    return `<div class="cell-clip">${escapeHtml(val.join(", "))}</div>`;
  }
  if (type === "badge") {
    return `<span class="badge ${badgeClass(val)}">${escapeHtml(String(val))}</span>`;
  }
  if (type === "url") {
    const raw = String(val);
    // multi-url separated by ;
    const parts = raw.split(/;\s*/).filter(Boolean);
    return parts
      .map((u) => {
        const href = u.startsWith("http") ? u : `https://${u}`;
        const label = u.length > 48 ? u.slice(0, 45) + "…" : u;
        return `<a class="link" href="${escapeAttr(href)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${escapeHtml(label)}</a>`;
      })
      .join("<br/>");
  }
  const s = Array.isArray(val) ? val.join(", ") : String(val);
  return `<div class="cell-clip">${escapeHtml(s)}</div>`;
}

function escapeHtml(s) {
  return s
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
function escapeAttr(s) {
  return escapeHtml(s).replaceAll("'", "&#39;");
}

function uniqueValues(rows, key) {
  if (!key || key === "_none") return [];
  const set = new Set();
  for (const r of rows) {
    const v = r[key];
    if (v != null && String(v).trim() !== "") set.add(String(v));
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}

function applyFilters(rows) {
  const conf = TABS[state.tab];
  let out = rows.slice();
  const filters = [state.f1, state.f2, state.f3];
  conf.filters.forEach((f, i) => {
    const val = filters[i];
    if (!val || f.key === "_none") return;
    out = out.filter((r) => String(r[f.key] ?? "") === val);
  });
  if (state.search.trim()) {
    const q = state.search.trim().toLowerCase();
    out = out.filter((r) => JSON.stringify(r).toLowerCase().includes(q));
  }
  if (state.sortKey) {
    const k = state.sortKey;
    const dir = state.sortDir;
    out.sort((a, b) => {
      const av = a[k] ?? "";
      const bv = b[k] ?? "";
      const as = Array.isArray(av) ? av.join(", ") : String(av);
      const bs = Array.isArray(bv) ? bv.join(", ") : String(bv);
      return as.localeCompare(bs, undefined, { numeric: true, sensitivity: "base" }) * dir;
    });
  }
  return out;
}

function renderStats() {
  const m = state.meta || {};
  const c = m.counts || {};
  const stats = [
    ["Primary sources", c.primary_sources ?? "—"],
    ["Tracking rows", c.tracking_records ?? "—"],
    ["Gazette", c.gazette_sources ?? "—"],
    ["Secondary", c.secondary_sources ?? "—"],
    ["Collector updates", c.updates ?? "—", true],
    ["Bill/amendment PDFs", c.pdfs ?? c.pdf_count ?? "—", true],
  ];
  $("#stats").innerHTML = stats
    .map(
      ([label, value, accent]) =>
        `<div class="stat"><div class="label">${label}</div><div class="value${accent ? " accent" : ""}">${value}</div></div>`
    )
    .join("");
  const last = m.last_collector_run
    ? `Last collector: ${m.last_collector_run} · ok ${m.last_collector_stats?.ok ?? "—"} / fail ${m.last_collector_stats?.fail ?? "—"} · new ${m.last_collector_stats?.new_updates ?? 0}`
    : `Catalog generated: ${m.generated_at || "—"}`;
  $("#metaBar").textContent = last;
}

function fillFilterSelects(rows) {
  const conf = TABS[state.tab];
  [1, 2, 3].forEach((n, i) => {
    const sel = $(`#filter${n}`);
    const f = conf.filters[i];
    if (!f || f.key === "_none") {
      sel.style.display = "none";
      sel.innerHTML = "";
      return;
    }
    sel.style.display = "";
    const vals = uniqueValues(rows, f.key);
    const current = state[`f${n}`];
    sel.innerHTML =
      `<option value="">${f.label}</option>` +
      vals.map((v) => `<option value="${escapeAttr(v)}"${v === current ? " selected" : ""}>${escapeHtml(v)}</option>`).join("");
  });
}

function renderTable() {
  const conf = TABS[state.tab];
  const rows = state.cache[state.tab] || [];
  const filtered = applyFilters(rows);
  const total = filtered.length;
  const pages = Math.max(1, Math.ceil(total / state.pageSize));
  if (state.page > pages) state.page = pages;
  const start = (state.page - 1) * state.pageSize;
  const pageRows = filtered.slice(start, start + state.pageSize);

  const thead = $("#dataTable thead");
  thead.innerHTML =
    "<tr>" +
    conf.columns
      .map((col) => {
        const arrow =
          state.sortKey === col.key ? (state.sortDir > 0 ? " ▲" : " ▼") : "";
        return `<th data-key="${col.key}">${escapeHtml(col.label)}${arrow}</th>`;
      })
      .join("") +
    "</tr>";

  const tbody = $("#dataTable tbody");
  if (!pageRows.length) {
    tbody.innerHTML = `<tr><td colspan="${conf.columns.length}"><div class="empty">No rows match your filters.</div></td></tr>`;
  } else {
    tbody.innerHTML = pageRows
      .map((row, idx) => {
        const cells = conf.columns
          .map((col) => `<td>${cellHTML(row[col.key], col.type)}</td>`)
          .join("");
        return `<tr data-idx="${start + idx}">${cells}</tr>`;
      })
      .join("");
  }

  $("#rowCount").textContent = `${total.toLocaleString()} row${total === 1 ? "" : "s"}`;
  $("#pageInfo").textContent = `Page ${state.page} / ${pages}`;
  $("#prevPage").disabled = state.page <= 1;
  $("#nextPage").disabled = state.page >= pages;

  thead.querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      if (state.sortKey === key) state.sortDir *= -1;
      else {
        state.sortKey = key;
        state.sortDir = 1;
      }
      renderTable();
    });
  });

  tbody.querySelectorAll("tr[data-idx]").forEach((tr) => {
    tr.addEventListener("click", () => {
      const i = Number(tr.dataset.idx);
      const row = filtered[i];
      $("#detailTitle").textContent = conf.label + " · row detail";
      $("#detailBody").textContent = JSON.stringify(row, null, 2);
      $("#detailDialog").showModal();
    });
  });
}

function exportCSV() {
  const conf = TABS[state.tab];
  const rows = applyFilters(state.cache[state.tab] || []);
  const cols = conf.columns;
  const header = cols.map((c) => c.label);
  const lines = [header.map(csvEscape).join(",")];
  for (const r of rows) {
    lines.push(
      cols
        .map((c) => {
          let v = r[c.key];
          if (Array.isArray(v)) v = v.join("; ");
          return csvEscape(v == null ? "" : String(v));
        })
        .join(",")
    );
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `bci-regintel-${state.tab}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

function csvEscape(s) {
  if (/[",\n]/.test(s)) return `"${s.replaceAll('"', '""')}"`;
  return s;
}

async function loadTab(tab) {
  state.tab = tab;
  state.page = 1;
  state.sortKey = null;
  state.f1 = state.f2 = state.f3 = "";
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tab);
  });
  if (!state.cache[tab]) {
    $("#dataTable tbody").innerHTML = `<tr><td colspan="12"><div class="empty">Loading…</div></td></tr>`;
    try {
      state.cache[tab] = await fetchJSON(TABS[tab].file);
    } catch (e) {
      state.cache[tab] = [];
      $("#dataTable tbody").innerHTML = `<tr><td colspan="12"><div class="empty">${escapeHtml(e.message)}</div></td></tr>`;
      return;
    }
  }
  fillFilterSelects(state.cache[tab]);
  renderTable();
}

async function boot() {
  try {
    state.meta = await fetchJSON("meta.json");
  } catch {
    state.meta = { counts: {} };
  }
  renderStats();
  await loadTab("pdfs");
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => loadTab(btn.dataset.tab));
});
$("#search").addEventListener("input", (e) => {
  state.search = e.target.value;
  state.page = 1;
  renderTable();
});
["filter1", "filter2", "filter3"].forEach((id, i) => {
  $(`#${id}`).addEventListener("change", (e) => {
    state[`f${i + 1}`] = e.target.value;
    state.page = 1;
    renderTable();
  });
});
$("#pageSize").addEventListener("change", (e) => {
  state.pageSize = Number(e.target.value);
  state.page = 1;
  renderTable();
});
$("#prevPage").addEventListener("click", () => {
  if (state.page > 1) {
    state.page--;
    renderTable();
  }
});
$("#nextPage").addEventListener("click", () => {
  state.page++;
  renderTable();
});
$("#btnExport").addEventListener("click", exportCSV);
$("#btnRefresh").addEventListener("click", async () => {
  delete state.cache[state.tab];
  try {
    state.meta = await fetchJSON("meta.json");
    renderStats();
  } catch {}
  await loadTab(state.tab);
});

boot();
