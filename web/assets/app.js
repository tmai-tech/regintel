async function load() {
  const res = await fetch("data/pdfs_catalog.json?t=" + Date.now());
  const rows = await res.json();
  document.getElementById("metaBar").textContent = rows.length + " PDFs";
  const juris = ["All", ...[...new Set(rows.map((r) => r.jurisdiction).filter(Boolean))].sort()];
  const sel = document.getElementById("filterJ");
  sel.innerHTML = juris.map((j) => `<option value="${escapeAttr(j)}">${escapeHtml(j)}</option>`).join("");

  function render() {
    const q = document.getElementById("search").value.trim().toLowerCase();
    const j = sel.value;
    const filtered = rows.filter((r) => {
      if (j !== "All" && r.jurisdiction !== j) return false;
      if (!q) return true;
      return JSON.stringify(r).toLowerCase().includes(q);
    });
    document.getElementById("rowCount").textContent = filtered.length + " shown";
    document.getElementById("list").innerHTML = filtered
      .map((r) => {
        const open = r.open_url || r.download_url || r.url || "#";
        const src = r.source_page || "—";
        return `<article class="pdf-card">
          <h3>${escapeHtml(r.title || r.filename || "PDF")}</h3>
          <p class="muted">${escapeHtml([r.jurisdiction, r.source_kind, r.bytes ? Math.round(r.bytes/1024)+" KB" : null].filter(Boolean).join(" · "))}</p>
          <p><strong>Extracted from</strong><br/><a class="link" href="${escapeAttr(src)}" target="_blank" rel="noopener">${escapeHtml(src)}</a></p>
          <p><strong>PDF</strong><br/><a class="link" href="${escapeAttr(open)}" target="_blank" rel="noopener">${escapeHtml(open)}</a></p>
          <p><a class="btn" href="${escapeAttr(open)}" target="_blank" rel="noopener">Open PDF</a></p>
        </article>`;
      })
      .join("");
  }
  document.getElementById("search").oninput = render;
  sel.onchange = render;
  render();
}
function escapeHtml(s) {
  return String(s ?? "").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}
function escapeAttr(s) { return escapeHtml(s).replaceAll("'","&#39;"); }
load().catch((e) => { document.getElementById("metaBar").textContent = e.message; });
