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
      summary: document.getElementById("panelSummary"),
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

  function isSdaiaRow(p) {
    const j = String((p && p.jurisdiction) || "");
    const h = String((p && p.host) || "");
    const u = String((p && (p.url || p.open_url || p.source_page)) || "");
    return (
      j.includes("SDAIA") ||
      h.toLowerCase().includes("sdaia") ||
      u.toLowerCase().includes("sdaia")
    );
  }

  function normalizePdfKey(u) {
    try {
      const x = new URL(String(u || "").trim());
      x.hash = "";
      // strip common tracking params
      ["utm_source", "utm_medium", "utm_campaign", "gclid", "fbclid"].forEach((k) =>
        x.searchParams.delete(k),
      );
      return x.href.replace(/\/$/, "").toLowerCase();
    } catch {
      return String(u || "")
        .split("#")[0]
        .replace(/\/$/, "")
        .toLowerCase();
    }
  }

  /** Merge SDAIA catalog PDFs with Eva extractive summaries for the Summary tab. */
  function buildSdaiaSummaryRows(pdfs, evaSummaries) {
    const byUrl = new Map();
    const byId = new Map();
    for (const e of evaSummaries || []) {
      if (!e || !isSdaiaRow(e)) continue;
      const url = e.open_url || e.url || "";
      const k = normalizePdfKey(url);
      if (k) byUrl.set(k, e);
      if (e.id) byId.set(String(e.id), e);
    }
    const rows = [];
    const seen = new Set();
    for (const p of pdfs || []) {
      if (!isSdaiaRow(p)) continue;
      const url = p.open_url || p.url || "";
      const k = normalizePdfKey(url);
      const eva = (k && byUrl.get(k)) || (p.id && byId.get(String(p.id))) || null;
      const id = String(p.id || (eva && eva.id) || k || rows.length);
      if (seen.has(id) && !eva) continue;
      seen.add(id);
      const summary = eva && eva.summary ? String(eva.summary).trim() : "";
      const keyPoints = Array.isArray(eva && eva.key_points)
        ? eva.key_points
        : typeof (eva && eva.key_points) === "string"
          ? (() => {
              try {
                const parsed = JSON.parse(eva.key_points);
                return Array.isArray(parsed) ? parsed : [];
              } catch {
                return [];
              }
            })()
          : [];
      rows.push({
        id,
        title: p.title || (eva && eva.title) || "Untitled PDF",
        url,
        open_url: url,
        summary,
        key_points: keyPoints,
        has_summary: Boolean(summary),
        method: (eva && eva.method) || "",
        summarized_at: (eva && eva.summarized_at) || "",
        jurisdiction: p.jurisdiction || (eva && eva.jurisdiction) || "Saudi Arabia - SDAIA",
      });
    }
    // Eva-only SDAIA rows not in catalog
    for (const e of evaSummaries || []) {
      if (!e || !isSdaiaRow(e)) continue;
      const url = e.open_url || e.url || "";
      const k = normalizePdfKey(url);
      const id = String(e.id || k);
      if (seen.has(id) || (k && [...seen].some(() => false))) {
        // already added via catalog match on id
      }
      if (seen.has(id)) continue;
      // also skip if URL already in rows
      if (k && rows.some((r) => normalizePdfKey(r.url) === k)) continue;
      seen.add(id);
      const summary = e.summary ? String(e.summary).trim() : "";
      rows.push({
        id,
        title: e.title || "Untitled PDF",
        url,
        open_url: url,
        summary,
        key_points: Array.isArray(e.key_points) ? e.key_points : [],
        has_summary: Boolean(summary),
        method: e.method || "",
        summarized_at: e.summarized_at || "",
        jurisdiction: e.jurisdiction || "Saudi Arabia - SDAIA",
      });
    }
    rows.sort((a, b) => {
      if (a.has_summary !== b.has_summary) return a.has_summary ? -1 : 1;
      // Prefer English extracts first so default Summary view is English-forward
      const aEn = a.summary && detectSourceLang(a.summary) === "en" ? 0 : 1;
      const bEn = b.summary && detectSourceLang(b.summary) === "en" ? 0 : 1;
      if (aEn !== bEn) return aEn - bEn;
      return String(a.title).localeCompare(String(b.title));
    });
    return rows;
  }

  const TRANSLATE_LANGS = [
    { code: "en", label: "English" },
    { code: "ar", label: "Arabic" },
    { code: "fr", label: "French" },
    { code: "es", label: "Spanish" },
    { code: "de", label: "German" },
    { code: "hi", label: "Hindi" },
    { code: "ur", label: "Urdu" },
    { code: "zh-CN", label: "Chinese (Simplified)" },
    { code: "tr", label: "Turkish" },
    { code: "pt", label: "Portuguese" },
  ];

  function translateLangOptionsHtml(selected) {
    const sel = selected || "en";
    return TRANSLATE_LANGS.map(
      (l) =>
        `<option value="${escapeAttr(l.code)}"${l.code === sel ? " selected" : ""}>${escapeHtml(l.label)}</option>`,
    ).join("");
  }

  /** Guess source language — MyMemory rejects langpair source "auto". */
  function detectSourceLang(text) {
    const s = String(text || "");
    const letters = s.replace(/\s+/g, "");
    if (!letters) return "en";
    const ar = (s.match(/[\u0600-\u06FF]/g) || []).length;
    const cjk = (s.match(/[\u4e00-\u9fff]/g) || []).length;
    const dev = (s.match(/[\u0900-\u097F]/g) || []).length;
    const cyr = (s.match(/[\u0400-\u04FF]/g) || []).length;
    const lat = (s.match(/[A-Za-z]/g) || []).length;
    const n = Math.max(ar + cjk + dev + cyr + lat, 1);
    if (ar / n > 0.25) return "ar";
    if (cjk / n > 0.25) return "zh-CN";
    if (dev / n > 0.25) return "hi";
    if (cyr / n > 0.25) return "ru";
    return "en";
  }

  function normalizeMyMemoryLang(code) {
    const c = String(code || "en").trim();
    // MyMemory expects codes like en, ar, zh-CN (not "auto")
    if (c === "auto" || c === "Autodetect" || !c) return "en";
    if (c.toLowerCase() === "zh" || c === "zh-cn") return "zh-CN";
    if (c.includes("-")) {
      const [a, b] = c.split("-");
      if (a.toLowerCase() === "zh") return "zh-CN";
      return a.toLowerCase() + "-" + b.toUpperCase();
    }
    return c.toLowerCase();
  }

  /** Free MyMemory API (chunked). Best-effort client-side translation. */
  async function translateTextChunks(text, targetLang) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    let target = normalizeMyMemoryLang(targetLang || "en");
    let source = detectSourceLang(raw);
    source = normalizeMyMemoryLang(source);
    // Same language → no-op
    if (source.split("-")[0] === target.split("-")[0]) return raw;

    // MyMemory free tier: keep chunks modest
    const maxLen = 450;
    const chunks = [];
    let rest = raw;
    while (rest.length) {
      if (rest.length <= maxLen) {
        chunks.push(rest);
        break;
      }
      let cut = rest.lastIndexOf(" ", maxLen);
      if (cut < maxLen * 0.5) cut = maxLen;
      chunks.push(rest.slice(0, cut));
      rest = rest.slice(cut).trimStart();
    }
    const out = [];
    for (const chunk of chunks) {
      const tryPairs = [
        source + "|" + target,
        // fallbacks if source guess is wrong
        "en|" + target,
        "ar|" + target,
      ];
      // dedupe pairs
      const pairs = [...new Set(tryPairs.filter((p) => {
        const [a, b] = p.split("|");
        return a && b && a.split("-")[0] !== b.split("-")[0];
      }))];

      let translated = "";
      let lastErr = "";
      for (const pair of pairs) {
        const url =
          "https://api.mymemory.translated.net/get?q=" +
          encodeURIComponent(chunk) +
          "&langpair=" +
          encodeURIComponent(pair);
        try {
          const res = await fetch(url);
          if (!res.ok) {
            lastErr = "Translate HTTP " + res.status;
            continue;
          }
          const data = await res.json();
          const t =
            (data && data.responseData && data.responseData.translatedText) ||
            "";
          const status = data && data.responseStatus;
          if (
            !t ||
            /QUERY LENGTH LIMIT/i.test(t) ||
            /INVALID SOURCE LANGUAGE/i.test(t) ||
            /IS AN INVALID TARGET LANGUAGE/i.test(t) ||
            /MYMEMORY WARNING/i.test(t) ||
            (status && status !== 200 && status !== "200")
          ) {
            lastErr = t || "Translation failed (" + pair + ")";
            continue;
          }
          translated = t;
          break;
        } catch (e) {
          lastErr = e.message || String(e);
        }
      }
      if (!translated) throw new Error(lastErr || "Translation failed");
      out.push(translated);
      // polite pause between chunks
      if (chunks.length > 1) await new Promise((r) => setTimeout(r, 200));
    }
    return out.join(" ");
  }

  function googleTranslatePdfUrl(pdfUrl, targetLang) {
    const tl = String(targetLang || "en").split("-")[0];
    return (
      "https://translate.google.com/translate?sl=auto&tl=" +
      encodeURIComponent(tl) +
      "&u=" +
      encodeURIComponent(pdfUrl)
    );
  }

  /** Stable short hash for translation cache keys. */
  function simpleHash(str) {
    let h = 5381;
    const s = String(str || "");
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h) ^ s.charCodeAt(i);
    return (h >>> 0).toString(36);
  }

  function readEnCache(key) {
    try {
      const raw = localStorage.getItem("regintel_en_" + key);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  function writeEnCache(key, payload) {
    try {
      localStorage.setItem("regintel_en_" + key, JSON.stringify(payload));
    } catch {
      /* quota / private mode */
    }
  }

  /**
   * Default UI language for Summary cards: English.
   * Prefer stored preference when valid; never default to Arabic for primary display.
   */
  function preferredSummaryTargetLang() {
    try {
      const stored =
        typeof localStorage !== "undefined"
          ? localStorage.getItem("regintel_summary_lang")
          : null;
      if (stored && TRANSLATE_LANGS.some((l) => l.code === stored)) return stored;
    } catch {
      /* ignore */
    }
    return "en";
  }

  function summaryCardHtml(r) {
    const link = r.open_url || r.url || "";
    const hasLink = isHttpUrl(link);
    const origSummary = r.summary ? String(r.summary) : "";
    const pointsArr = (r.key_points || []).slice(0, 4).map((p) => String(p));
    // Prefer cached English display when extract is non-English (default UX = English)
    const cacheKey = simpleHash(origSummary + "\n" + (r.title || "") + "\n" + pointsArr.join("\n"));
    const cached = origSummary && detectSourceLang(origSummary) !== "en" ? readEnCache(cacheKey) : null;
    const displayTitle = (cached && cached.title) || r.title || "Untitled PDF";
    const displaySummary = (cached && cached.summary) || origSummary;
    const displayPoints =
      cached && Array.isArray(cached.points) && cached.points.length
        ? cached.points
        : pointsArr;
    const summary = displaySummary
      ? escapeHtml(displaySummary)
      : '<span class="muted">No extractive summary yet for this PDF.</span>';
    const points = displayPoints.map((p) => `<li>${escapeHtml(p)}</li>`).join("");
    const badge = r.has_summary
      ? `<span class="badge badge-fed">Extracted</span>`
      : `<span class="badge badge-src">Pending</span>`;
    const method =
      r.method || r.summarized_at
        ? `<p class="meta-line">${escapeHtml(r.method || "summary")}${
            r.summarized_at ? " · " + escapeHtml(String(r.summarized_at).slice(0, 19)) : ""
          }</p>`
        : "";
    const cardId = "sum-" + String(r.id || "").replace(/[^\w-]/g, "_").slice(0, 40);
    const defaultLang = preferredSummaryTargetLang();
    const needsEn =
      Boolean(origSummary) && detectSourceLang(origSummary) !== "en" && !cached;
    return `
      <article class="pdf-card summary-card" role="listitem" id="${escapeAttr(cardId)}"
        data-orig-title="${escapeAttr(r.title || "Untitled PDF")}"
        data-orig-summary="${escapeAttr(origSummary)}"
        data-orig-points="${escapeAttr(JSON.stringify(pointsArr))}"
        data-en-cache-key="${escapeAttr(cacheKey)}"
        data-needs-en="${needsEn ? "1" : "0"}"
        data-pdf-url="${escapeAttr(link)}">
        <div class="card-badges">${badge}</div>
        <h3 class="sum-title">${escapeHtml(displayTitle)}</h3>
        <p class="field-label">PDF link</p>
        <p class="url-line">${
          hasLink
            ? `<a class="link sum-pdf-link" href="${escapeAttr(link)}" target="_blank" rel="noopener">${escapeHtml(shortenUrl(link, 72))}</a>`
            : `<span class="muted">—</span>`
        }</p>
        <p class="field-label">Summary</p>
        <p class="summary-line summary-line-full sum-summary">${summary}</p>
        ${
          points
            ? `<p class="field-label">Key points</p><ul class="summary-points sum-points">${points}</ul>`
            : `<ul class="summary-points sum-points" hidden></ul>`
        }
        ${method}
        <div class="translate-bar">
          <label class="sr-only" for="${escapeAttr(cardId)}-lang">Translate language</label>
          <select id="${escapeAttr(cardId)}-lang" class="sum-lang" aria-label="Target language">
            ${translateLangOptionsHtml(defaultLang)}
          </select>
          <button type="button" class="btn ghost sum-translate-btn" data-card="${escapeAttr(cardId)}">
            Translate
          </button>
          <button type="button" class="btn ghost sum-restore-btn" data-card="${escapeAttr(cardId)}" ${
            cached ? "" : "hidden"
          }>
            Original
          </button>
          ${
            hasLink
              ? `<a class="btn ghost sum-pdf-translate-link" href="${escapeAttr(googleTranslatePdfUrl(link, defaultLang))}" target="_blank" rel="noopener" data-card="${escapeAttr(cardId)}">Translate PDF</a>`
              : ""
          }
        </div>
        <p class="meta-line sum-translate-status"${cached ? "" : " hidden"}>${
          cached
            ? "Showing English (cached). Use Translate for other languages or Original for source text."
            : ""
        }</p>
        ${
          hasLink
            ? `<div class="card-actions"><a class="btn primary" href="${escapeAttr(link)}" target="_blank" rel="noopener">Open PDF</a></div>`
            : ""
        }
      </article>`;
  }

  /**
   * For Arabic/other non-English extracts, produce English display text
   * (MyMemory with explicit source lang — never langpair=auto|…).
   * Limited concurrency + localStorage cache so Summary tab defaults to English.
   */
  async function ensureEnglishSummaries(listEl) {
    if (!listEl) return;
    const cards = [...listEl.querySelectorAll(".summary-card[data-needs-en='1']")];
    if (!cards.length) return;
    // Cap auto-translate work per render to protect free API quota
    const maxAuto = 12;
    const queue = cards.slice(0, maxAuto);
    let idx = 0;
    const workers = 2;

    async function workOne(card) {
      const origTitle = card.getAttribute("data-orig-title") || "";
      const origSummary = card.getAttribute("data-orig-summary") || "";
      const cacheKey = card.getAttribute("data-en-cache-key") || simpleHash(origSummary);
      let origPoints = [];
      try {
        origPoints = JSON.parse(card.getAttribute("data-orig-points") || "[]");
      } catch {
        origPoints = [];
      }
      const status = card.querySelector(".sum-translate-status");
      const restoreBtn = card.querySelector(".sum-restore-btn");
      if (status) {
        status.hidden = false;
        status.textContent = "Preparing English summary…";
      }
      try {
        let titleEn = origTitle;
        if (origTitle && detectSourceLang(origTitle) !== "en") {
          titleEn = await translateTextChunks(origTitle, "en");
        }
        let summaryEn = origSummary;
        if (origSummary && detectSourceLang(origSummary) !== "en") {
          summaryEn = await translateTextChunks(origSummary, "en");
        }
        const pointsEn = [];
        for (const p of origPoints) {
          if (p && detectSourceLang(p) !== "en") {
            pointsEn.push(await translateTextChunks(p, "en"));
          } else {
            pointsEn.push(p);
          }
        }
        writeEnCache(cacheKey, {
          title: titleEn,
          summary: summaryEn,
          points: pointsEn,
        });
        // Only apply if card still in DOM
        if (!card.isConnected) return;
        const titleEl = card.querySelector(".sum-title");
        const sumEl = card.querySelector(".sum-summary");
        const pointsEl = card.querySelector(".sum-points");
        if (titleEl) titleEl.textContent = titleEn;
        if (sumEl) sumEl.textContent = summaryEn;
        if (pointsEl && pointsEn.length) {
          pointsEl.hidden = false;
          pointsEl.innerHTML = pointsEn.map((p) => `<li>${escapeHtml(p)}</li>`).join("");
        }
        card.setAttribute("data-needs-en", "0");
        if (restoreBtn) restoreBtn.hidden = false;
        if (status) {
          status.textContent =
            "Showing English. Use Translate for other languages or Original for source text.";
        }
      } catch (e) {
        if (status) {
          status.hidden = false;
          status.textContent =
            "English auto-translate unavailable: " +
            (e.message || String(e)) +
            ". Select English and click Translate.";
        }
      }
    }

    async function worker() {
      while (idx < queue.length) {
        const i = idx++;
        await workOne(queue[i]);
      }
    }
    await Promise.all(Array.from({ length: Math.min(workers, queue.length) }, () => worker()));
  }

  function wireSummaryTranslateButtons(listEl) {
    if (!listEl) return;
    listEl.querySelectorAll(".sum-lang").forEach((sel) => {
      sel.addEventListener("change", () => {
        try {
          localStorage.setItem("regintel_summary_lang", sel.value);
        } catch (_) {
          /* ignore */
        }
        const card = sel.closest(".summary-card");
        if (!card) return;
        const pdfUrl = card.getAttribute("data-pdf-url") || "";
        const a = card.querySelector(".sum-pdf-translate-link");
        if (a && isHttpUrl(pdfUrl)) {
          a.href = googleTranslatePdfUrl(pdfUrl, sel.value);
        }
      });
    });

    listEl.querySelectorAll(".sum-translate-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const cardId = btn.getAttribute("data-card");
        const card = cardId ? document.getElementById(cardId) : btn.closest(".summary-card");
        if (!card) return;
        const langSel = card.querySelector(".sum-lang");
        const status = card.querySelector(".sum-translate-status");
        const restoreBtn = card.querySelector(".sum-restore-btn");
        const targetLang = (langSel && langSel.value) || "en";
        const origTitle = card.getAttribute("data-orig-title") || "";
        const origSummary = card.getAttribute("data-orig-summary") || "";
        let origPoints = [];
        try {
          origPoints = JSON.parse(card.getAttribute("data-orig-points") || "[]");
        } catch (_) {
          origPoints = [];
        }
        if (!origSummary && !origTitle) {
          if (status) {
            status.hidden = false;
            status.textContent = "Nothing to translate for this PDF.";
          }
          return;
        }
        btn.disabled = true;
        if (status) {
          status.hidden = false;
          status.textContent = "Translating title & summary…";
        }
        try {
          try {
            localStorage.setItem("regintel_summary_lang", targetLang);
          } catch (_) {
            /* ignore */
          }
          const titleEl = card.querySelector(".sum-title");
          const sumEl = card.querySelector(".sum-summary");
          const pointsEl = card.querySelector(".sum-points");
          let titleOut = origTitle;
          let summaryOut = origSummary;
          let pointsOut = origPoints.slice();
          if (origTitle) {
            titleOut = await translateTextChunks(origTitle, targetLang);
            if (titleEl) titleEl.textContent = titleOut;
          }
          if (origSummary) {
            summaryOut = await translateTextChunks(origSummary, targetLang);
            if (sumEl) sumEl.textContent = summaryOut;
          } else if (sumEl) {
            sumEl.innerHTML =
              '<span class="muted">No extractive summary yet for this PDF.</span>';
          }
          if (pointsEl && origPoints.length) {
            pointsOut = [];
            for (const p of origPoints) {
              pointsOut.push(await translateTextChunks(p, targetLang));
            }
            pointsEl.hidden = false;
            pointsEl.innerHTML = pointsOut
              .map((p) => `<li>${escapeHtml(p)}</li>`)
              .join("");
          }
          // Cache English for default Summary display on next visit
          if (normalizeMyMemoryLang(targetLang).split("-")[0] === "en" && summaryOut) {
            const cacheKey =
              card.getAttribute("data-en-cache-key") || simpleHash(origSummary);
            writeEnCache(cacheKey, {
              title: titleOut,
              summary: summaryOut,
              points: pointsOut,
            });
            card.setAttribute("data-needs-en", "0");
          }
          const pdfLink = card.querySelector(".sum-pdf-translate-link");
          const pdfUrl = card.getAttribute("data-pdf-url") || "";
          if (pdfLink && isHttpUrl(pdfUrl)) {
            pdfLink.href = googleTranslatePdfUrl(pdfUrl, targetLang);
          }
          if (restoreBtn) restoreBtn.hidden = false;
          if (status) {
            status.textContent =
              "Translated to " +
              targetLang +
              ". Use “Translate PDF” to open the document in Google Translate.";
          }
        } catch (e) {
          if (status) {
            status.hidden = false;
            status.textContent =
              "Translation failed: " + (e.message || String(e)) + ". Try again later.";
          }
        } finally {
          btn.disabled = false;
        }
      });
    });

    listEl.querySelectorAll(".sum-restore-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cardId = btn.getAttribute("data-card");
        const card = cardId ? document.getElementById(cardId) : btn.closest(".summary-card");
        if (!card) return;
        const origTitle = card.getAttribute("data-orig-title") || "";
        const origSummary = card.getAttribute("data-orig-summary") || "";
        let origPoints = [];
        try {
          origPoints = JSON.parse(card.getAttribute("data-orig-points") || "[]");
        } catch (_) {
          origPoints = [];
        }
        const titleEl = card.querySelector(".sum-title");
        const sumEl = card.querySelector(".sum-summary");
        const pointsEl = card.querySelector(".sum-points");
        const status = card.querySelector(".sum-translate-status");
        if (titleEl) titleEl.textContent = origTitle;
        if (sumEl) {
          if (origSummary) sumEl.textContent = origSummary;
          else
            sumEl.innerHTML =
              '<span class="muted">No extractive summary yet for this PDF.</span>';
        }
        if (pointsEl) {
          if (origPoints.length) {
            pointsEl.hidden = false;
            pointsEl.innerHTML = origPoints
              .map((p) => `<li>${escapeHtml(String(p))}</li>`)
              .join("");
          } else {
            pointsEl.innerHTML = "";
            pointsEl.hidden = true;
          }
        }
        btn.hidden = true;
        if (status) {
          status.hidden = false;
          status.textContent = "Showing original text.";
        }
      });
    });

    // Fire-and-forget English default for non-English extracts (re-wired after each render)
    ensureEnglishSummaries(listEl).catch(() => {
      /* non-fatal */
    });
  }

  function initSummaries(pdfs, evaSummaries) {
    const list = document.getElementById("summaryList");
    const empty = document.getElementById("summaryEmpty");
    const countEl = document.getElementById("summaryCount");
    const search = document.getElementById("summarySearch");
    const filter = document.getElementById("summaryFilter");
    if (!list) return;

    const rows = buildSdaiaSummaryRows(pdfs, evaSummaries);
    const withSum = rows.filter((r) => r.has_summary).length;

    function render() {
      const q = (search && search.value ? search.value : "").trim().toLowerCase();
      const mode = (filter && filter.value) || "with";
      let filtered = rows;
      if (mode === "with") filtered = filtered.filter((r) => r.has_summary);
      if (mode === "pending") filtered = filtered.filter((r) => !r.has_summary);
      if (q) {
        filtered = filtered.filter((r) => {
          const blob = (
            (r.title || "") +
            " " +
            (r.summary || "") +
            " " +
            (r.url || "") +
            " " +
            (r.key_points || []).join(" ")
          ).toLowerCase();
          return blob.includes(q);
        });
      }
      if (countEl) {
        countEl.textContent =
          filtered.length +
          " shown · " +
          withSum +
          " with summary · " +
          rows.length +
          " SDAIA PDFs";
      }
      if (!filtered.length) {
        list.innerHTML = "";
        if (empty) empty.hidden = false;
        return;
      }
      if (empty) empty.hidden = true;
      list.innerHTML = filtered.map(summaryCardHtml).join("");
      wireSummaryTranslateButtons(list);
    }

    let t = null;
    if (search) {
      search.addEventListener("input", () => {
        clearTimeout(t);
        t = setTimeout(render, 120);
      });
    }
    if (filter) filter.addEventListener("change", render);
    render();
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
    const withSummaries = evaSummaries.filter((e) => e && String(e.summary || "").trim()).length;
    metaBar.textContent =
      "SDAIA catalog · " +
      pdfs.length +
      " PDFs · " +
      withSummaries +
      " summaries";

    initMinistries(ministries, pdfs);
    initEva(evaSummaries, evaMeta, pdfs.length);
    initPdfs(pdfs);
    initSummaries(pdfs, evaSummaries);
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
