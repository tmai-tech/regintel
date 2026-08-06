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
      pdfs: document.getElementById("panelPdfs"),
      crawl: document.getElementById("panelCrawl"),
      ministries: document.getElementById("panelMinistries"),
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

  function hostOf(u) {
    try {
      return new URL(u).hostname.replace(/^www\./i, "").toLowerCase();
    } catch {
      return "";
    }
  }

  function ministryCardHtml(m, pdfs) {
    const related = pdfs.filter((p) => {
      const j = (p.jurisdiction || "").toLowerCase().trim();
      const h = hostOf(p.open_url || p.url || "");
      const mh = hostOf(m.url);
      const code = (m.code || "").toLowerCase();
      // Strict label: "Saudi Arabia - CODE" (never bare code — "ia" false-matches Columbia)
      const labelOk =
        j === "saudi arabia - " + code ||
        j.startsWith("saudi arabia - " + code + " ") ||
        j === code ||
        j.endsWith(" - " + code);
      // Host must be same site as the official ministry domain
      const hostOk =
        !!mh &&
        !!h &&
        (h === mh || h.endsWith("." + mh));
      // Do NOT use reverse host match (mh.endsWith("." + h)) — too loose for .gov.sa
      return labelOk || hostOk;
    });
    const pdfLinks = related
      .slice(0, 12)
      .map((p) => {
        const open = p.open_url || p.url || "";
        const title = p.title || p.filename || "PDF";
        if (!isHttpUrl(open)) return "";
        return `<li><a class="link" href="${escapeAttr(open)}" target="_blank" rel="noopener">${escapeHtml(title.slice(0, 90))}</a></li>`;
      })
      .filter(Boolean)
      .join("");
    const more =
      related.length > 12
        ? `<p class="muted">+${related.length - 12} more PDFs (see PDFs tab, filter “${escapeHtml(m.code)}”)</p>`
        : "";

    return `<article class="pdf-card law-card" role="listitem">
      <div class="card-badges">
        <span class="badge badge-fed">${escapeHtml(m.authority_type || "Authority")}</span>
        <span class="badge badge-src">${escapeHtml(m.code || "")}</span>
        <span class="badge badge-state">${related.length} PDF${related.length === 1 ? "" : "s"}</span>
      </div>
      <h3>${escapeHtml(m.name)}</h3>
      <p class="meta-line">${escapeHtml(m.country || "Saudi Arabia")}</p>
      <p class="field-label">Official website</p>
      <p class="url-line"><a class="link" href="${escapeAttr(m.url)}" target="_blank" rel="noopener">${escapeHtml(shortenUrl(m.url, 64))}</a></p>
      <div class="card-actions">
        <a class="btn primary" href="${escapeAttr(m.url)}" target="_blank" rel="noopener">Open authority site</a>
      </div>
      ${
        related.length
          ? `<p class="field-label">Extracted PDFs</p><ul class="ministry-pdf-list">${pdfLinks}</ul>${more}`
          : `<p class="muted">No PDFs extracted yet for this authority — crawl in progress.</p>`
      }
    </article>`;
  }

  const EVA_STOP = new Set([
    "the", "and", "for", "are", "you", "your", "what", "when", "where", "which",
    "who", "how", "does", "did", "with", "from", "that", "this", "have", "has",
    "was", "were", "will", "can", "could", "would", "should", "about", "into",
    "more", "any", "all", "our", "its", "not", "but", "also", "than", "then",
    "them", "they", "there", "these", "those", "please", "tell", "give", "show",
    "read", "reading", "pdf", "pdfs", "document", "documents", "file", "files",
    "summary", "summaries", "index", "indexed",
  ]);

  function tokenizeEva(s) {
    return (String(s || "").toLowerCase().match(/[a-z0-9]{3,}/g) || []).filter(
      (t) => !EVA_STOP.has(t),
    );
  }

  /** Questions about Eva herself / indexing status — not about bill content. */
  function isEvaMetaQuestion(q) {
    const s = String(q || "")
      .toLowerCase()
      .trim()
      .replace(/[’']/g, "'");
    if (!s) return false;

    // short status-like
    if (/^(status|progress|update|hello|hi|hey|thanks|thank you)[\s?!.,]*$/i.test(s)) {
      return true;
    }

    // "will/are/do/can you … extract/read/index more pdfs?"
    const processVerb =
      /(read|reading|extract|extracting|index|indexing|process|processing|summariz(?:e|ing)?|crawl(?:ing)?|download(?:ing)?|fetch(?:ing)?|scrape|scraping|ingest(?:ing)?)/;
    if (
      /\b(will|are|do|can|could|would|shall)\s+you\b/.test(s) &&
      processVerb.test(s)
    ) {
      return true;
    }
    // "extracting more pdfs", "more documents", "reading more"
    if (
      processVerb.test(s) &&
      /\b(more|additional|new|other|further)\b/.test(s) &&
      /\b(pdfs?|documents?|files?|bills?|summaries|data)\b/.test(s)
    ) {
      return true;
    }
    if (/\b(more|additional)\s+(pdfs?|documents?|files?)\b/.test(s)) return true;
    if (/\bhow many\b/.test(s) && /\b(pdfs?|summaries|documents?)\b/.test(s)) return true;
    if (/\b(are you|do you)\b/.test(s) && processVerb.test(s)) return true;
    if (/\bhave you (read|finished|done|indexed|extracted)\b/.test(s)) return true;
    // "list/show those 38 pdfs", "give me the list"
    if (
      /\b(list|show|display|name)\b/.test(s) &&
      /\b(pdfs?|summaries|documents?|files?|them|those|index)\b/.test(s)
    ) {
      return true;
    }
    if (/\bgive me (a |the )?list\b/.test(s)) return true;
    if (/\bwhich pdfs?\b/.test(s) || /\bwhat (pdfs?|documents?) (do you|have you)\b/.test(s)) {
      return true;
    }

    const patterns = [
      /\b(still )?(working|running|crawling|indexing|extracting)\b/,
      /\b(how much|progress|update me|status|coverage)\b/,
      /\b(who are you|what (can|do) you do|what is eva)\b/,
      /\b(thank(s| you)|help me)\b/,
      /\bknowledge base\b/,
      /\b(keep|continue)\s+(reading|extracting|indexing|processing)\b/,
    ];
    return patterns.some((re) => re.test(s));
  }

  function evaMetaAnswer(question, corpus, meta, pdfCatalogCount) {
    const count = corpus.length;
    const total = (meta && (meta.total_indexed || meta.count)) || count;
    const updated = meta && meta.updated_at ? new Date(meta.updated_at).toLocaleString() : "—";
    const llm = meta && meta.llm_available;
    const s = String(question || "").toLowerCase();

    if (/^(hi|hello|hey)\b/.test(s) || /who are you|what (can|do) you do|what is eva/.test(s)) {
      return {
        answer:
          "I’m Eva, RegIntel’s legal research assistant. I read bill and gazette PDFs, keep short summaries, and answer your questions with links to the source PDFs.\n\n" +
          `Right now I have ${count} SDAIA PDF summary(ies) in my index` +
          (pdfCatalogCount ? ` (${pdfCatalogCount} SDAIA PDFs in the catalog).` : ".") +
          "\n\nAsk about SDAIA policies, PDPL, AI ethics, or a document name.",
        citations: [],
      };
    }

    if (/thank/.test(s)) {
      return { answer: "You’re welcome. Ask anytime about a bill, regulation, or jurisdiction.", citations: [] };
    }

    // list / show all indexed PDFs
    if (
      /\b(list|show|display|name|which|what)\b/.test(s) &&
      /\b(pdfs?|summaries|documents?|files?|index|indexed|read|you have|you've)\b/.test(s)
    ) {
      if (!count) {
        return {
          answer: "I don’t have any PDF summaries indexed yet. Summarization is still running in batches.",
          citations: [],
        };
      }
      const citations = corpus.map((h, i) => ({
        n: i + 1,
        title: h.title || "Untitled",
        url: h.open_url || h.url,
        jurisdiction: h.jurisdiction,
      }));
      const lines = [
        `Here are the ${count} PDF(s) I’ve summarized so far (catalog has ~${pdfCatalogCount != null ? pdfCatalogCount : "many"} total):`,
        "",
      ];
      citations.forEach((c) => {
        lines.push(
          `[${c.n}] ${c.title} (${c.jurisdiction || "—"})` +
            (c.url ? `\n    ${c.url}` : ""),
        );
      });
      lines.push("");
      lines.push("Click a reference link below (or open the URL) to view the PDF.");
      return { answer: lines.join("\n"), citations };
    }

    // status / are you reading more
    return {
      answer:
        `Yes — PDF summarization runs in batches (GitHub Actions + local jobs), separate from this chat.\n\n` +
        `• Summaries I’ve finished: ${count}` +
        (total && total !== count ? ` (store reports ${total})` : "") +
        `\n• PDFs in the RegIntel catalog: ${pdfCatalogCount != null ? pdfCatalogCount : "unknown"}` +
        `\n• Last index update: ${updated}` +
        `\n• Summary engine: ${llm ? "SpaceXAI LLM" : "extractive (set XAI_API_KEY for higher quality)"}` +
        `\n\nAsk “list the PDFs” to see every document I’ve summarized.\n` +
        `Or ask a content question, e.g. “Delaware order paper” or “Manitoba bills”.`,
      citations: [],
    };
  }

  function retrieveEva(question, corpus, k) {
    const tokens = tokenizeEva(question);
    if (!tokens.length) return [];
    const q = new Set(tokens);
    const scored = [];
    for (const doc of corpus) {
      const title = String(doc.title || "");
      const blob = [
        title,
        doc.jurisdiction,
        doc.summary,
        ...(doc.key_points || []),
        ...(doc.topics || []),
      ]
        .filter(Boolean)
        .join(" ");
      const dt = new Set(tokenizeEva(blob));
      let score = 0;
      q.forEach((t) => {
        if (dt.has(t)) score += 1;
      });
      // strong title match
      const titleToks = new Set(tokenizeEva(title));
      q.forEach((t) => {
        if (titleToks.has(t)) score += 3;
      });
      // jurisdiction phrase
      const j = String(doc.jurisdiction || "").toLowerCase();
      tokens.forEach((t) => {
        if (j.includes(t)) score += 2;
      });
      if (score >= 2) scored.push({ score, doc });
    }
    scored.sort((a, b) => b.score - a.score);
    // drop weak tail: keep only scores close to best
    if (!scored.length) return [];
    const best = scored[0].score;
    return scored
      .filter((x) => x.score >= Math.max(2, best * 0.4))
      .slice(0, k)
      .map((x) => x.doc);
  }

  function evaAnswerLocal(question, hits) {
    if (!hits.length) {
      return {
        answer:
          "I couldn’t find a strong match in my PDF summaries for that question.\n\n" +
          "Tips:\n" +
          "• Name a jurisdiction (e.g. Delaware, Manitoba, Saudi, UK)\n" +
          "• Use a topic (tax, cyber, securities, housing)\n" +
          "• Or a bill/document title word\n\n" +
          "Ask “status” if you want to know how many PDFs I’ve indexed so far.",
        citations: [],
      };
    }
    const lines = [
      `Here’s what I found in ${hits.length} related PDF summary(ies). I only use summaries I’ve completed — each answer cites the source:`,
      "",
    ];
    const citations = [];
    hits.forEach((h, i) => {
      const n = i + 1;
      citations.push({
        n,
        title: h.title,
        url: h.open_url || h.url,
        jurisdiction: h.jurisdiction,
      });
      lines.push(`[${n}] ${h.title || "Untitled"} (${h.jurisdiction || "—"})`);
      let sum = (h.summary || "").trim();
      if (sum.length > 380) sum = sum.slice(0, 377) + "…";
      lines.push(sum || "(No summary text.)");
      if (h.key_points && h.key_points.length) {
        lines.push("Key points: " + h.key_points.slice(0, 3).join("; "));
      }
      lines.push("");
    });
    lines.push("References (open the PDF):");
    citations.forEach((c) => {
      lines.push(`[${c.n}] ${c.title}${c.url ? " — " + c.url : ""}`);
    });
    return { answer: lines.join("\n"), citations };
  }

  function initEva(summaries, meta, pdfCatalogCount) {
    const chat = document.getElementById("evaChat");
    const form = document.getElementById("evaForm");
    const input = document.getElementById("evaInput");
    const metaEl = document.getElementById("evaMeta");
    const fab = document.getElementById("evaFab");
    const panel = document.getElementById("evaPanel");
    const closeBtn = document.getElementById("evaClose");
    const widget = document.getElementById("evaWidget");
    if (!chat || !form || !fab || !panel) return;

    const corpus = Array.isArray(summaries) ? summaries : [];
    const count = corpus.length;
    const llmHint =
      meta && meta.llm_available
        ? "LLM index · " + count + " PDFs"
        : count
          ? count + " summaries"
          : "indexing…";
    if (metaEl) {
      metaEl.textContent = llmHint;
    }

    let greeted = false;

    function setOpen(open) {
      panel.hidden = !open;
      fab.setAttribute("aria-expanded", open ? "true" : "false");
      if (widget) widget.classList.toggle("eva-open", open);
      if (open) {
        if (!greeted) {
          greeted = true;
          addBubble(
            "bot",
            count
              ? `Hi, I’m Eva — your legal research assistant.\n\nI’ve summarized ${count} PDF(s) so far` +
                  (pdfCatalogCount
                    ? ` (catalog has ~${pdfCatalogCount} PDFs; more summaries are added in batches).`
                    : ".") +
                  `\n\nAsk a content question (topic / jurisdiction / bill name). For indexing progress, ask “are you reading more PDFs?” or “status”.`
              : "Hi, I’m Eva. PDF summaries are still being built. Ask “status” anytime, or a topic once indexing has started.",
          );
        }
        setTimeout(() => input && input.focus(), 50);
      }
    }

    fab.addEventListener("click", () => {
      setOpen(panel.hidden);
    });
    if (closeBtn) {
      closeBtn.addEventListener("click", () => setOpen(false));
    }

    function addBubble(role, text, citations) {
      const div = document.createElement("div");
      div.className = "eva-bubble eva-" + role;
      if (role === "bot") {
        const who = document.createElement("div");
        who.className = "eva-who";
        who.textContent = "👩‍⚖️ Eva";
        div.appendChild(who);
      }
      const body = document.createElement("div");
      body.className = "eva-bubble-text";
      body.textContent = text;
      div.appendChild(body);
      if (citations && citations.length) {
        const ul = document.createElement("ul");
        ul.className = "eva-cites";
        citations.forEach((c) => {
          const li = document.createElement("li");
          const label = `[${c.n}] ${c.title || "PDF"}`;
          if (isHttpUrl(c.url)) {
            const a = document.createElement("a");
            a.className = "link";
            a.href = c.url;
            a.target = "_blank";
            a.rel = "noopener";
            a.textContent = label;
            li.appendChild(a);
          } else {
            li.textContent = label;
          }
          ul.appendChild(li);
        });
        div.appendChild(ul);
      }
      chat.appendChild(div);
      chat.scrollTop = chat.scrollHeight;
    }

    async function handleAsk(q) {
      addBubble("user", q);
      const typing = document.createElement("div");
      typing.className = "eva-bubble eva-bot eva-typing";
      typing.textContent = "Eva is thinking…";
      chat.appendChild(typing);
      chat.scrollTop = chat.scrollHeight;

      const finish = (answer, citations) => {
        typing.remove();
        addBubble("bot", answer || "No answer.", citations || []);
      };

      // Meta questions about Eva / indexing — never fake PDF hits
      if (isEvaMetaQuestion(q)) {
        const out = evaMetaAnswer(q, corpus, meta, pdfCatalogCount);
        finish(out.answer, out.citations);
        return;
      }

      const apiBase = (
        window.REGINTEL_EVA_API ||
        localStorage.getItem("regintel_eva_api") ||
        ""
      ).replace(/\/$/, "");
      if (apiBase) {
        try {
          const res = await fetch(apiBase + "/api/eva/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question: q, k: 8 }),
          });
          if (res.ok) {
            const data = await res.json();
            finish(data.answer, data.citations || []);
            return;
          }
        } catch {
          /* fall through */
        }
      }
      const hits = retrieveEva(q, corpus, 5);
      const out = evaAnswerLocal(q, hits);
      finish(out.answer, out.citations);
    }

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const q = (input.value || "").trim();
      if (!q) return;
      input.value = "";
      if (panel.hidden) setOpen(true);
      handleAsk(q);
    });
  }

  function initMinistries(ministries, pdfs) {
    const list = document.getElementById("ministryList");
    const empty = document.getElementById("ministryEmpty");
    const search = document.getElementById("ministrySearch");
    const count = document.getElementById("ministryCount");
    if (!list || !Array.isArray(ministries)) return;

    function render() {
      const q = (search && search.value.trim().toLowerCase()) || "";
      const filtered = ministries.filter((m) => {
        if (!q) return true;
        const blob = [m.name, m.code, m.url, m.authority_type, m.country]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return blob.includes(q);
      });
      if (count) count.textContent = filtered.length + " authorities";
      if (!filtered.length) {
        list.innerHTML = "";
        if (empty) empty.hidden = false;
        return;
      }
      if (empty) empty.hidden = true;
      list.innerHTML = filtered.map((m) => ministryCardHtml(m, pdfs || [])).join("");
    }

    if (search) {
      let t = null;
      search.addEventListener("input", () => {
        clearTimeout(t);
        t = setTimeout(render, 100);
      });
    }
    render();
  }

  function statusBadge(status) {
    const s = String(status || "to_download");
    const map = {
      downloaded: "badge-fed",
      to_download: "badge-src",
      download_failed: "badge-state",
      scanned_pdf: "badge-src",
      listed: "badge-src",
    };
    return `<span class="badge ${map[s] || "badge-src"}">${escapeHtml(s)}</span>`;
  }

  function fmtWhen(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch (_) {
      return String(iso).slice(0, 19);
    }
  }

  function renderCrawlStatus(st, docList, catalogCount) {
    const body = document.getElementById("crawlBody");
    const updated = document.getElementById("crawlUpdated");
    if (!body) return;
    if (!st && !docList) {
      body.innerHTML =
        '<div class="empty">No crawl status yet. Ministry crawl publishes a full document list (to download / downloaded / failed / scanned) then downloads.</div>';
      if (updated) updated.textContent = "No status file";
      return;
    }
    st = st || {};
    docList = docList && typeof docList === "object" ? docList : null;
    const totals = st.totals || {};
    const phase = st.phase || "unknown";
    const cur = st.current_source || {};
    // Merge list file (full docs) with crawl_status summary — prefer newer timestamps
    const stMdl = st.ministry_document_list || {};
    const listFile = docList || {};
    const stMdlAt = Date.parse(stMdl.updated_at || "") || 0;
    const listAt = Date.parse(listFile.updated_at || "") || 0;
    const newerList = listAt >= stMdlAt ? listFile : { ...listFile, ...stMdl };
    // Always prefer document array from the dedicated list file when present
    const docs =
      (Array.isArray(listFile.documents) && listFile.documents.length
        ? listFile.documents
        : null) ||
      (Array.isArray(stMdl.documents) && stMdl.documents.length
        ? stMdl.documents
        : null) ||
      [];
    const countsFromFile = newerList.counts || listFile.counts || stMdl.counts || {};
    // Discovered total = master list size (explicit count or length of list)
    const discoveredTotal = Number(
      countsFromFile.listed_total ??
        totals.ministry_listed ??
        (docs.length ? docs.length : 0),
    );
    const toDl = Number(countsFromFile.to_download ?? totals.ministry_to_download ?? 0);
    const dlOk = Number(countsFromFile.downloaded ?? totals.ministry_downloaded ?? 0);
    const scanned = Number(countsFromFile.scanned_pdf ?? totals.ministry_scanned ?? 0);
    const failed = Number(countsFromFile.download_failed ?? totals.ministry_failed ?? 0);
    // Catalog = published PDFs tab inventory (NOT the same as discovered list)
    const catalogPdfs = Number(
      catalogCount != null
        ? catalogCount
        : totals.pdfs != null
          ? totals.pdfs
          : 0,
    );
    const listUpdated = listFile.updated_at || stMdl.updated_at || null;
    const statusUpdated = st.updated_at || null;
    const pagesVisited =
      newerList.pages_visited != null
        ? newerList.pages_visited
        : stMdl.pages_visited != null
          ? stMdl.pages_visited
          : listFile.pages_visited;
    const methods =
      newerList.discovery_methods ||
      stMdl.discovery_methods ||
      listFile.discovery_methods ||
      {};
    const methodLine = Object.keys(methods).length
      ? Object.entries(methods)
          .map(([k, v]) => `${k}: ${v}`)
          .join(" · ")
      : "—";
    const label = newerList.label || stMdl.label || listFile.label || cur.jurisdiction || "SDAIA";
    const targetUrl = newerList.target_url || stMdl.target_url || listFile.target_url || cur.url || "";

    if (updated) {
      updated.textContent =
        "Status " +
        fmtWhen(statusUpdated) +
        " · list " +
        fmtWhen(listUpdated) +
        " · phase: " +
        phase +
        " · discovered " +
        discoveredTotal +
        " · catalog " +
        catalogPdfs;
    }
    const phaseClass =
      phase === "running" ||
      phase === "starting" ||
      phase === "discovering" ||
      phase === "downloading" ||
      phase === "listed"
        ? "badge-state"
        : phase === "paused"
          ? "badge-src"
          : "badge-fed";
    const runLink = isHttpUrl(st.github_run_url)
      ? `<a class="link" href="${escapeAttr(st.github_run_url)}" target="_blank" rel="noopener">GitHub Actions run #${escapeHtml(String(st.run_id || "").slice(-6) || "open")}</a>`
      : "";
    const failedSample =
      (listFile && listFile.failed_sample) ||
      docs.filter((d) => d.status === "download_failed").slice(0, 40);
    const statusFilterId = "crawlStatusFilter";
    const allDocs = docs;
    const failRows = failedSample
      .slice(0, 50)
      .map((d) => {
        const name = d.filename || d.url || "doc";
        return `<tr><td>${escapeHtml(String(name).slice(0, 50))}</td><td class="muted">${escapeHtml(String(d.download_error || "failed").slice(0, 80))}</td></tr>`;
      })
      .join("");

    body.innerHTML = `
      <div class="crawl-hero">
        <div class="card-badges">
          <span class="badge ${phaseClass}">${escapeHtml(phase)}</span>
          ${runLink ? `<span class="badge badge-src">${runLink}</span>` : ""}
        </div>
        <p class="summary-line">${escapeHtml(st.message || "—")}</p>

        <h3 class="crawl-h" style="margin:1rem 0 0.35rem">1 · Discovered master list <span class="muted" style="font-weight:400">(URLs found on the ministry site — not the catalog)</span></h3>
        <div class="crawl-metrics">
          <div class="metric"><div class="metric-val">${escapeHtml(String(discoveredTotal))}</div><div class="metric-label">Discovered PDFs (total)</div></div>
          <div class="metric"><div class="metric-val">${escapeHtml(String(toDl))}</div><div class="metric-label">Still to download</div></div>
          <div class="metric"><div class="metric-val">${escapeHtml(String(dlOk))}</div><div class="metric-label">Downloaded OK</div></div>
          <div class="metric"><div class="metric-val">${escapeHtml(String(scanned))}</div><div class="metric-label">Scanned (image PDF)</div></div>
          <div class="metric"><div class="metric-val">${escapeHtml(String(failed))}</div><div class="metric-label">Download failed</div></div>
          <div class="metric"><div class="metric-val">${escapeHtml(String(pagesVisited != null ? pagesVisited : "—"))}</div><div class="metric-label">Pages scanned</div></div>
        </div>
        <p class="meta-line">
          Master list updated: <strong>${escapeHtml(fmtWhen(listUpdated))}</strong>
          ${docs.length ? ` · rows in table: <strong>${docs.length}</strong>` : " · full row list not published yet"}
          <br/>Target: <strong>${escapeHtml(label)}</strong>
          ${targetUrl ? ` · <a class="link" href="${escapeAttr(targetUrl)}" target="_blank" rel="noopener">${escapeHtml(shortenUrl(targetUrl, 60))}</a>` : ""}
          <br/>How found: ${escapeHtml(methodLine)}
        </p>

        <h3 class="crawl-h" style="margin:1.25rem 0 0.35rem">2 · SDAIA catalog <span class="muted" style="font-weight:400">(PDFs tab / published inventory — separate from discovery)</span></h3>
        <div class="crawl-metrics">
          <div class="metric"><div class="metric-val">${escapeHtml(String(catalogPdfs))}</div><div class="metric-label">SDAIA catalog PDFs</div></div>
        </div>
        <p class="meta-line">
          Catalog status updated: <strong>${escapeHtml(fmtWhen(statusUpdated))}</strong>
          <br/><span class="muted">Discovered total and catalog total are different numbers. Discovery = every PDF URL found. Catalog = what is published on the PDFs tab after download/merge.</span>
        </p>
      </div>
      <div class="toolbar" style="margin:0.75rem 0;gap:0.5rem;flex-wrap:wrap">
        <label class="muted" for="${statusFilterId}">Filter master list status</label>
        <select id="${statusFilterId}" aria-label="Filter by document status">
          <option value="">All discovered (${allDocs.length})</option>
          <option value="to_download">to_download</option>
          <option value="downloaded">downloaded</option>
          <option value="scanned_pdf">scanned_pdf</option>
          <option value="download_failed">download_failed</option>
        </select>
        <span class="muted" id="crawlDocCount"></span>
      </div>
      <div class="crawl-grid">
        <div style="grid-column:1/-1">
          <h3 class="crawl-h">Master list — every discovered PDF URL (${discoveredTotal})</h3>
          <div class="table-wrap" style="max-height:28rem;overflow:auto"><table class="data-table" id="crawlDocTable"><thead><tr><th>#</th><th>File</th><th>Status</th><th>Found via</th><th>Error</th></tr></thead><tbody></tbody></table></div>
        </div>
        <div>
          <h3 class="crawl-h">Download failures</h3>
          <div class="table-wrap"><table class="data-table"><thead><tr><th>File</th><th>Error</th></tr></thead><tbody>${failRows || "<tr><td colspan=2 class=muted>No failures recorded</td></tr>"}</tbody></table></div>
        </div>
      </div>
      <p class="muted crawl-note"><strong>Two counters (do not mix them):</strong>
        <br/>• <strong>Discovered PDFs</strong> = master list size from the latest ministry crawl (URLs found).
        <br/>• <strong>SDAIA catalog PDFs</strong> = published PDFs tab count (files already in catalog).
        <br/><strong>Flow:</strong> discover list → download with status → merge into catalog.
      </p>
    `;

    function paintDocs(filter) {
      const tbody = document.querySelector("#crawlDocTable tbody");
      const countEl = document.getElementById("crawlDocCount");
      if (!tbody) return;
      const filtered = filter
        ? allDocs.filter((d) => d.status === filter)
        : allDocs;
      if (countEl) countEl.textContent = filtered.length + " shown";
      tbody.innerHTML = filtered
        .map((d, i) => {
          const name = d.filename || d.title || "doc";
          const link = isHttpUrl(d.url)
            ? `<a class="link" href="${escapeAttr(d.url)}" target="_blank" rel="noopener">${escapeHtml(String(name).slice(0, 70))}</a>`
            : escapeHtml(String(name).slice(0, 70));
          const err = d.download_error
            ? `<span class="muted">${escapeHtml(String(d.download_error).slice(0, 70))}</span>`
            : "—";
          return `<tr><td class="num">${i + 1}</td><td>${link}</td><td>${statusBadge(d.status)}</td><td class="muted">${escapeHtml(d.discovery_method || "—")}</td><td>${err}</td></tr>`;
        })
        .join("") || `<tr><td colspan="5" class="muted">No documents in list yet</td></tr>`;
    }
    const sel = document.getElementById(statusFilterId);
    if (sel) {
      sel.addEventListener("change", () => paintDocs(sel.value));
    }
    paintDocs("");
  }

  function initCrawl() {
    const btn = document.getElementById("crawlRefresh");
    async function refresh() {
      try {
        const bust = "t=" + Date.now();
        const [st, docList, catalog] = await Promise.all([
          fetchJson("data/crawl_status.json?" + bust).catch(() => null),
          fetchJson("data/ministry_document_list.json?" + bust).catch(() => null),
          fetchJson("data/pdfs_catalog.json?" + bust).catch(() => null),
        ]);
        const catalogCount = Array.isArray(catalog) ? catalog.length : null;
        renderCrawlStatus(st, docList, catalogCount);
      } catch (e) {
        renderCrawlStatus(null, null, null);
      }
    }
    window.__regintelRefreshCrawl = refresh;
    if (btn) btn.addEventListener("click", refresh);
    refresh();
    // auto-refresh every 45s while page open (live discovery progress)
    setInterval(refresh, 45000);
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

    let ministries = [];
    let evaSummaries = [];
    let evaMeta = null;
    try {
      const [lawsRes, pdfsRes, minRes, evaRes, evaMetaRes] = await Promise.all([
        fetchJson("data/laws_catalog.json").catch(() => null),
        fetchJson("data/pdfs_catalog.json"),
        fetchJson("data/saudi_ministries.json").catch(() => []),
        fetchJson("data/eva_summaries.json").catch(() => []),
        fetchJson("data/eva_meta.json").catch(() => null),
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
      // Site is SDAIA-only — drop any residual non-SDAIA rows
      pdfs = pdfsRes.filter((p) => {
        const j = String(p.jurisdiction || "");
        const h = String(p.host || "");
        const u = String(p.url || p.open_url || "");
        return (
          j.includes("SDAIA") ||
          h.toLowerCase().includes("sdaia") ||
          u.toLowerCase().includes("sdaia")
        );
      });
      ministries = (Array.isArray(minRes) ? minRes : []).filter(
        (m) => String(m.code || "").toUpperCase() === "SDAIA" || /sdaia/i.test(m.name || ""),
      );
      if (!ministries.length) {
        ministries = [
          {
            code: "SDAIA",
            name: "Saudi Data and Artificial Intelligence Authority (SDAIA)",
            url: "https://sdaia.gov.sa",
            country: "Saudi Arabia",
            authority_type: "Authority",
          },
        ];
      }
      evaSummaries = (Array.isArray(evaRes) ? evaRes : []).filter((e) => {
        const j = String(e.jurisdiction || "");
        const u = String(e.url || e.open_url || e.source_page || "");
        return j.includes("SDAIA") || u.toLowerCase().includes("sdaia");
      });
      evaMeta = evaMetaRes;
    } catch (e) {
      metaBar.textContent = "Error";
      const host = document.getElementById("ministryList") || document.getElementById("list");
      if (host) {
        host.innerHTML =
          '<div class="error-state">Failed to load data.<br/>' +
          escapeHtml(e.message || String(e)) +
          "</div>";
      }
      return;
    }

    // Meta: catalog (PDFs tab) is not the same as discovered master-list count
    metaBar.textContent = "SDAIA catalog · " + pdfs.length + " PDFs";

    initMinistries(ministries, pdfs);
    initEva(evaSummaries, evaMeta, pdfs.length);
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
