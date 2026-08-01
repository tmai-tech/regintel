(function () {
  const DISMISS_KEY = "regintel_install_dismissed_v1";
  const MAX_CARDS = 400;

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }
  function escapeAttr(s) {
    return escapeHtml(s).replaceAll("'", "&#39;");
  }

  function isHttpUrl(u) {
    return typeof u === "string" && /^https?:\/\//i.test(u.trim());
  }

  function shortenUrl(u, max = 56) {
    if (!u || u === "—") return u || "—";
    try {
      const url = new URL(u);
      let s = url.hostname.replace(/^www\./, "") + url.pathname + url.search;
      if (s.length > max) s = s.slice(0, max - 1) + "…";
      return s;
    } catch {
      return u.length > max ? u.slice(0, max - 1) + "…" : u;
    }
  }

  function formatBytes(n) {
    if (!n || n <= 0) return null;
    if (n < 1024) return n + " B";
    if (n < 1024 * 1024) return Math.round(n / 1024) + " KB";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  }

  function formatKind(k) {
    if (!k) return null;
    return String(k).replaceAll("_", " ");
  }

  function formatLawType(t) {
    if (!t) return null;
    return String(t)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function pdfUrl(row) {
    return row.open_url || row.download_url || row.url || "";
  }

  function matchesQuery(row, q) {
    if (!q) return true;
    const blob = [
      row.title,
      row.filename,
      row.jurisdiction,
      row.source_kind,
      row.law_type,
      row.year,
      row.language,
      row.host,
      row.source_page,
      row.open_url,
      row.url,
      ...(Array.isArray(row.filename_tags) ? row.filename_tags : []),
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return blob.includes(q);
  }

  function lawMatchesQuery(row, q) {
    if (!q) return true;
    const blob = [
      row.name,
      row.summary,
      row.country,
      row.level,
      row.level_detail || row.levelDetail,
      row.law_area || row.lawArea,
      row.topic,
      row.authority,
      row.link,
      row.authority_url || row.authorityUrl,
      row.region,
      row.source,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return blob.includes(q);
  }

  function fillSelect(sel, values, allLabel) {
    const opts = [allLabel, ...values];
    sel.innerHTML = opts
      .map((v) => {
        let label = v;
        if (v !== allLabel) {
          if (sel.id === "filterLaw") label = formatLawType(v);
          else if (sel.id === "filterKind") label = formatKind(v);
        }
        return `<option value="${escapeAttr(v)}">${escapeHtml(label)}</option>`;
      })
      .join("");
  }

  function showInstallBannerIfNeeded() {
    const el = document.getElementById("installBanner");
    if (!el) return;
    try {
      if (localStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      /* private mode */
    }
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      window.navigator.standalone === true;
    if (standalone) return;

    const ua = navigator.userAgent || "";
    const isIos =
      /iPad|iPhone|iPod/.test(ua) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    if (!isIos) return;

    el.hidden = false;
    const btn = document.getElementById("dismissInstall");
    if (btn) {
      btn.addEventListener("click", () => {
        el.hidden = true;
        try {
          localStorage.setItem(DISMISS_KEY, "1");
        } catch {
          /* ignore */
        }
      });
    }
  }

  function setupTabs() {
    const tabs = document.querySelectorAll(".tab");
    const panels = {
      laws: document.getElementById("panelLaws"),
      pdfs: document.getElementById("panelPdfs"),
      crawl: document.getElementById("panelCrawl"),
    };
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const key = tab.dataset.tab;
        tabs.forEach((t) => {
          const on = t === tab;
          t.classList.toggle("active", on);
          t.setAttribute("aria-selected", on ? "true" : "false");
        });
        Object.entries(panels).forEach(([k, panel]) => {
          if (!panel) return;
          panel.hidden = k !== key;
        });
        if (key === "crawl" && typeof window.__regintelRefreshCrawl === "function") {
          window.__regintelRefreshCrawl();
        }
      });
    });
  }

  function renderCrawlStatus(st) {
    const body = document.getElementById("crawlBody");
    const updated = document.getElementById("crawlUpdated");
    if (!body) return;
    if (!st) {
      body.innerHTML =
        '<div class="empty">No crawl status yet. GitHub Actions crawl will publish <code>crawl_status.json</code> as PDFs are found.</div>';
      if (updated) updated.textContent = "No status file";
      return;
    }
    const totals = st.totals || {};
    const phase = st.phase || "unknown";
    const cur = st.current_source || {};
    const byJ = st.by_jurisdiction || [];
    const recent = st.recent_pdfs || [];
    if (updated) {
      updated.textContent =
        "Updated " +
        (st.updated_at ? new Date(st.updated_at).toLocaleString() : "—") +
        " · phase: " +
        phase;
    }
    const phaseClass =
      phase === "running" || phase === "starting"
        ? "badge-state"
        : phase === "paused"
          ? "badge-src"
          : "badge-fed";
    const runLink = isHttpUrl(st.github_run_url)
      ? `<a class="link" href="${escapeAttr(st.github_run_url)}" target="_blank" rel="noopener">GitHub Actions run</a>`
      : "";
    const jurisRows = byJ
      .slice(0, 25)
      .map(
        (r) =>
          `<tr><td>${escapeHtml(r.jurisdiction)}</td><td class="num">${escapeHtml(String(r.count))}</td></tr>`,
      )
      .join("");
    const recentRows = recent
      .map((r) => {
        const title = r.title || r.url || "PDF";
        const link = isHttpUrl(r.url)
          ? `<a class="link" href="${escapeAttr(r.url)}" target="_blank" rel="noopener">${escapeHtml(title.slice(0, 80))}</a>`
          : escapeHtml(title.slice(0, 80));
        return `<tr><td>${escapeHtml(r.jurisdiction || "—")}</td><td>${link}</td><td class="muted">${escapeHtml((r.downloaded_at || "").slice(0, 19))}</td></tr>`;
      })
      .join("");

    body.innerHTML = `
      <div class="crawl-hero">
        <div class="card-badges">
          <span class="badge ${phaseClass}">${escapeHtml(phase)}</span>
          ${runLink ? `<span class="badge badge-src">${runLink}</span>` : ""}
        </div>
        <p class="summary-line">${escapeHtml(st.message || "—")}</p>
        <div class="crawl-metrics">
          <div class="metric"><div class="metric-val">${escapeHtml(String(totals.pdfs ?? 0))}</div><div class="metric-label">PDFs in catalog</div></div>
          <div class="metric"><div class="metric-val">${escapeHtml(String(totals.jurisdictions ?? 0))}</div><div class="metric-label">Jurisdictions</div></div>
          <div class="metric"><div class="metric-val">${escapeHtml(String(totals.errors ?? 0))}</div><div class="metric-label">Errors logged</div></div>
        </div>
        <p class="meta-line">Current source: <strong>${escapeHtml(cur.jurisdiction || "—")}</strong>
          ${cur.source_kind ? " · " + escapeHtml(cur.source_kind) : ""}
          ${cur.url ? `<br/><a class="link" href="${escapeAttr(cur.url)}" target="_blank" rel="noopener">${escapeHtml(shortenUrl(cur.url, 70))}</a>` : ""}
        </p>
      </div>
      <div class="crawl-grid">
        <div>
          <h3 class="crawl-h">By jurisdiction</h3>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>Jurisdiction</th><th>PDFs</th></tr></thead><tbody>${jurisRows || "<tr><td colspan=2 class=muted>None yet</td></tr>"}</tbody></table></div>
        </div>
        <div>
          <h3 class="crawl-h">Recently extracted</h3>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>Place</th><th>PDF</th><th>When</th></tr></thead><tbody>${recentRows || "<tr><td colspan=3 class=muted>None yet</td></tr>"}</tbody></table></div>
        </div>
      </div>
      <p class="muted crawl-note">Catalog refreshes on the live site as the GitHub Actions crawl finds PDFs (resume-safe chunks every few hours). Open the <strong>PDFs</strong> tab to browse them.</p>
    `;
  }

  function initCrawl() {
    const btn = document.getElementById("crawlRefresh");
    async function refresh() {
      try {
        const st = await fetchJson("data/crawl_status.json").catch(() => null);
        renderCrawlStatus(st);
      } catch (e) {
        renderCrawlStatus(null);
      }
    }
    window.__regintelRefreshCrawl = refresh;
    if (btn) btn.addEventListener("click", refresh);
    refresh();
    // auto-refresh every 60s while page open
    setInterval(refresh, 60000);
  }

  function normalizeLawRow(r) {
    return {
      id: r.id || "",
      name: r.name || r.title || "Untitled",
      summary: r.summary || "",
      country: r.country || "",
      level: r.level || "Federal",
      levelDetail: r.level_detail || r.levelDetail || r.level || "",
      lawArea: r.law_area || r.lawArea || "",
      topic: r.topic || r.topical_relevance || "",
      link: r.link || "",
      authority: r.authority || "",
      authorityUrl: r.authority_url || r.authorityUrl || r.source_url || "",
      region: r.region || "",
      date: r.date || r.discovered_at || "",
      source: r.source || "catalog",
      relevancy: r.relevancy || "",
    };
  }

  function linkBlock(label, url) {
    if (isHttpUrl(url)) {
      return `<p class="field-label">${escapeHtml(label)}</p>
        <p class="url-line"><a class="link" href="${escapeAttr(url)}" target="_blank" rel="noopener">${escapeHtml(shortenUrl(url))}</a></p>`;
    }
    return `<p class="field-label">${escapeHtml(label)}</p>
      <p class="url-line muted">—</p>`;
  }

  function sourceBadge(source) {
    if (source === "collector") return `<span class="badge badge-src">Update</span>`;
    if (source === "tracking") return `<span class="badge badge-src">Tracking</span>`;
    if (source === "source") return `<span class="badge badge-src">Authority</span>`;
    return `<span class="badge badge-src">${escapeHtml(source || "Law")}</span>`;
  }

  function lawCardHtml(raw) {
    const r = normalizeLawRow(raw);
    const meta = [
      r.country,
      r.levelDetail && r.levelDetail !== r.level
        ? r.level + " · " + r.levelDetail
        : r.level,
      r.lawArea,
    ]
      .filter(Boolean)
      .join(" · ");

    const linkOk = isHttpUrl(r.link);
    const authUrlOk = isHttpUrl(r.authorityUrl);
    const authorityName = r.authority || "—";
    const primaryLabel = r.source === "source" ? "Open authority page" : "Open law link";

    const actions = `
      <div class="card-actions">
        ${
          linkOk
            ? `<a class="btn primary" href="${escapeAttr(r.link)}" target="_blank" rel="noopener">${escapeHtml(primaryLabel)}</a>`
            : `<span class="btn ghost" aria-disabled="true">No link</span>`
        }
        ${
          authUrlOk && r.authorityUrl !== r.link
            ? `<a class="btn secondary" href="${escapeAttr(r.authorityUrl)}" target="_blank" rel="noopener">Authority page</a>`
            : ""
        }
      </div>`;

    return `<article class="pdf-card law-card" role="listitem">
      <div class="card-badges">
        ${r.level ? `<span class="badge ${r.level === "Federal" ? "badge-fed" : "badge-state"}">${escapeHtml(r.level)}</span>` : ""}
        ${sourceBadge(r.source)}
      </div>
      <h3>${escapeHtml(r.name)}</h3>
      <p class="meta-line">${escapeHtml(meta)}</p>
      <p class="field-label">Summary</p>
      <p class="summary-line">${escapeHtml(r.summary || "—")}</p>
      ${linkBlock(r.source === "source" ? "Authority / law link" : "Law link", r.link)}
      <p class="field-label">Authority</p>
      <p class="authority-line">${
        authUrlOk
          ? `<a class="link" href="${escapeAttr(r.authorityUrl)}" target="_blank" rel="noopener">${escapeHtml(authorityName)}</a>`
          : escapeHtml(authorityName)
      }</p>
      ${authUrlOk && r.authorityUrl !== r.link ? linkBlock("Authority page", r.authorityUrl) : ""}
      ${actions}
    </article>`;
  }

  function pdfCardHtml(r) {
    const open = pdfUrl(r);
    const src = r.source_page || "";
    const meta = [
      r.jurisdiction,
      formatLawType(r.law_type),
      r.year ? String(r.year) : null,
      formatKind(r.source_kind),
      r.language && r.language !== "und" ? r.language : null,
      formatBytes(r.bytes),
    ]
      .filter(Boolean)
      .join(" · ");
    const title = r.title || r.filename || "PDF";
    const openOk = isHttpUrl(open);
    const srcOk = isHttpUrl(src);

    const srcBlock = srcOk
      ? `<p class="field-label">Extracted from</p>
         <p class="url-line"><a class="link" href="${escapeAttr(src)}" target="_blank" rel="noopener">${escapeHtml(shortenUrl(src))}</a></p>`
      : `<p class="field-label">Extracted from</p>
         <p class="url-line muted">—</p>`;

    const pdfBlock = openOk
      ? `<p class="field-label">PDF link</p>
         <p class="url-line"><a class="link" href="${escapeAttr(open)}" target="_blank" rel="noopener">${escapeHtml(shortenUrl(open))}</a></p>`
      : "";

    const actions = `
      <div class="card-actions">
        ${
          openOk
            ? `<a class="btn primary" href="${escapeAttr(open)}" target="_blank" rel="noopener">Open PDF</a>`
            : `<span class="btn ghost" aria-disabled="true">No PDF URL</span>`
        }
        ${
          srcOk
            ? `<a class="btn secondary" href="${escapeAttr(src)}" target="_blank" rel="noopener">Source page</a>`
            : ""
        }
      </div>`;

    return `<article class="pdf-card" role="listitem">
      <h3>${escapeHtml(title)}</h3>
      <p class="meta-line">${escapeHtml(meta)}</p>
      ${srcBlock}
      ${pdfBlock}
      ${actions}
    </article>`;
  }

  function renderList(listEl, emptyEl, countEl, items, htmlFn) {
    countEl.textContent = items.length + " shown";
    if (items.length === 0) {
      listEl.innerHTML = "";
      emptyEl.hidden = false;
      return;
    }
    emptyEl.hidden = true;
    const slice = items.slice(0, MAX_CARDS);
    listEl.innerHTML =
      slice.map(htmlFn).join("") +
      (items.length > MAX_CARDS
        ? `<p class="muted" style="text-align:center;padding:8px">Showing first ${MAX_CARDS} of ${items.length}. Narrow search to see more.</p>`
        : "");
  }

  async function fetchJson(path) {
    const res = await fetch(path + "?t=" + Date.now(), { cache: "no-cache" });
    if (!res.ok) throw new Error("Could not load " + path + " (" + res.status + ")");
    return res.json();
  }

  function initLaws(laws) {
    const selCountry = document.getElementById("filterCountry");
    const selLevel = document.getElementById("filterLevel");
    const selArea = document.getElementById("filterLawArea");
    const search = document.getElementById("lawSearch");
    const list = document.getElementById("lawList");
    const empty = document.getElementById("lawEmpty");
    const rowCount = document.getElementById("lawRowCount");

    const normalized = laws.map(normalizeLawRow);

    fillSelect(
      selCountry,
      [...new Set(normalized.map((r) => r.country).filter(Boolean))].sort((a, b) =>
        a.localeCompare(b),
      ),
      "All countries",
    );

    const areas = [
      ...new Set(
        normalized.flatMap((r) =>
          (r.lawArea || "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        ),
      ),
    ].sort((a, b) => a.localeCompare(b));
    fillSelect(selArea, areas, "All law areas");

    // Kind filter: Updates / Tracking / Authority sources
    let selKind = document.getElementById("filterLawKind");
    if (!selKind) {
      selKind = document.createElement("select");
      selKind.id = "filterLawKind";
      selKind.setAttribute("aria-label", "Record type filter");
      selArea.insertAdjacentElement("afterend", selKind);
    }
    fillSelect(
      selKind,
      [
        ...new Set(
          normalized
            .map((r) => r.source)
            .filter(Boolean)
            .map((s) =>
              s === "collector" ? "Update" : s === "tracking" ? "Tracking" : s === "source" ? "Authority" : s,
            ),
        ),
      ].sort(),
      "All types",
    );

    function typeOf(r) {
      if (r.source === "collector") return "Update";
      if (r.source === "tracking") return "Tracking";
      if (r.source === "source") return "Authority";
      return r.source || "";
    }

    function render() {
      const q = search.value.trim().toLowerCase();
      const country = selCountry.value;
      const level = selLevel.value;
      const area = selArea.value;
      const kind = selKind.value;
      const filtered = normalized.filter((r) => {
        if (country !== "All countries" && r.country !== country) return false;
        if (level !== "All levels" && r.level !== level) return false;
        if (kind !== "All types" && typeOf(r) !== kind) return false;
        if (area !== "All law areas") {
          const parts = (r.lawArea || "")
            .split(",")
            .map((s) => s.trim().toLowerCase());
          if (!parts.includes(area.toLowerCase())) return false;
        }
        return lawMatchesQuery(r, q);
      });
      renderList(list, empty, rowCount, filtered, lawCardHtml);
    }

    let t = null;
    search.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(render, 120);
    });
    [selCountry, selLevel, selArea, selKind].forEach((el) =>
      el.addEventListener("change", render),
    );
    render();
  }

  function initPdfs(rows) {
    const selJ = document.getElementById("filterJ");
    const selLaw = document.getElementById("filterLaw");
    const selYear = document.getElementById("filterYear");
    const selKind = document.getElementById("filterKind");
    const search = document.getElementById("search");
    const list = document.getElementById("list");
    const empty = document.getElementById("empty");
    const rowCount = document.getElementById("rowCount");

    fillSelect(
      selJ,
      [...new Set(rows.map((r) => r.jurisdiction).filter(Boolean))].sort((a, b) =>
        a.localeCompare(b),
      ),
      "All locations",
    );
    fillSelect(
      selLaw,
      [...new Set(rows.map((r) => r.law_type).filter(Boolean))].sort((a, b) =>
        a.localeCompare(b),
      ),
      "All law types",
    );
    fillSelect(
      selYear,
      [...new Set(rows.map((r) => r.year).filter(Boolean))]
        .sort((a, b) => b - a)
        .map(String),
      "All years",
    );
    fillSelect(
      selKind,
      [...new Set(rows.map((r) => r.source_kind).filter(Boolean))].sort((a, b) =>
        a.localeCompare(b),
      ),
      "All sources",
    );

    function render() {
      const q = search.value.trim().toLowerCase();
      const j = selJ.value;
      const law = selLaw.value;
      const year = selYear.value;
      const kind = selKind.value;
      const filtered = rows.filter((r) => {
        if (j !== "All locations" && r.jurisdiction !== j) return false;
        if (law !== "All law types" && r.law_type !== law) return false;
        if (year !== "All years" && String(r.year) !== year) return false;
        if (kind !== "All sources" && r.source_kind !== kind) return false;
        return matchesQuery(r, q);
      });
      renderList(list, empty, rowCount, filtered, pdfCardHtml);
    }

    let t = null;
    search.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(render, 120);
    });
    [selJ, selLaw, selYear, selKind].forEach((el) =>
      el.addEventListener("change", render),
    );
    render();
  }

  async function load() {
    const metaBar = document.getElementById("metaBar");
    showInstallBannerIfNeeded();
    setupTabs();

    let laws = [];
    let pdfs = [];

    try {
      const [lawsRes, pdfsRes] = await Promise.all([
        fetchJson("data/laws_catalog.json").catch(() => null),
        fetchJson("data/pdfs_catalog.json"),
      ]);
      if (Array.isArray(lawsRes) && lawsRes.length) {
        laws = lawsRes;
      } else {
        // Fallback: client-side merge if catalog missing
        const [u, t, s] = await Promise.all([
          fetchJson("data/updates.json").catch(() => []),
          fetchJson("data/tracking.json").catch(() => []),
          fetchJson("data/primary_sources.json").catch(() => []),
        ]);
        laws = legacyBuildLaws(
          Array.isArray(u) ? u : [],
          Array.isArray(t) ? t : [],
          Array.isArray(s) ? s : [],
        );
      }
      if (!Array.isArray(pdfsRes)) throw new Error("PDF catalog is not a list");
      pdfs = pdfsRes;
    } catch (e) {
      metaBar.textContent = "Error";
      document.getElementById("lawList").innerHTML =
        '<div class="error-state">Failed to load data.<br/>' +
        escapeHtml(e.message || String(e)) +
        "</div>";
      return;
    }

    const nState = laws.filter((r) => (r.level || "") === "State").length;
    const nFed = laws.filter((r) => (r.level || "") === "Federal").length;
    metaBar.textContent =
      laws.length + " laws (" + nFed + " fed · " + nState + " state) · " + pdfs.length + " PDFs";

    initLaws(laws);
    initPdfs(pdfs);
    initCrawl();
  }

  /** Minimal fallback if laws_catalog.json is absent. */
  function legacyBuildLaws(updates, tracking, sources) {
    const rows = [];
    const seen = new Set();
    for (const u of updates) {
      const name = u.title || "Update";
      const link = u.link || "";
      const key = (link || name).toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      rows.push({
        id: u.id,
        name,
        summary: [u.topical_relevance, u.law_area].filter(Boolean).join(" · "),
        country: String(u.country || "").replace(/\s*[-–—]\s*federal$/i, "").trim(),
        level: /federal/i.test(u.country || "") ? "Federal" : "Federal",
        level_detail: "Federal",
        law_area: u.law_area || "",
        topic: u.topical_relevance || "",
        link,
        authority: u.authority || "",
        authority_url: u.source_url || "",
        source: "collector",
        date: u.discovered_at || "",
      });
    }
    for (const t of tracking) {
      const name = t.remarks || t.topical_relevance || "Tracked";
      const link = t.link || "";
      const key = (link || name).toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      const fos = t.federal_or_state || "Federal";
      rows.push({
        name,
        summary: [t.remarks, t.topical_relevance, t.law_area].filter(Boolean).join(" · "),
        country: t.country || "",
        level: /^federal$/i.test(fos) ? "Federal" : "State",
        level_detail: fos,
        law_area: t.law_area || "",
        topic: t.topical_relevance || "",
        link,
        authority: "",
        authority_url: "",
        source: "tracking",
      });
    }
    for (const s of sources) {
      const name = s.authority || "";
      const link = s.url || "";
      if (!name || !link) continue;
      const key = link.toLowerCase();
      if (seen.has(key)) continue;
      seen.add(key);
      const j = s.jurisdiction || "";
      rows.push({
        name,
        summary: [s.segment, Array.isArray(s.topics) ? s.topics.slice(0, 4).join(", ") : ""]
          .filter(Boolean)
          .join(" · "),
        country: String(j).replace(/\s*[-–—]\s*federal$/i, "").trim(),
        level: /federal/i.test(j) ? "Federal" : "State",
        level_detail: j,
        law_area: s.segment || "",
        topic: Array.isArray(s.topics) ? s.topics.join(", ") : "",
        link,
        authority: name,
        authority_url: link,
        source: "source",
      });
    }
    return rows;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();
