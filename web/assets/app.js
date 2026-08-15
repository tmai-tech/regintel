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
    // Latin + Arabic tokens (SDAIA corpus is bilingual)
    const raw = String(s || "").toLowerCase();
    const lat = raw.match(/[a-z0-9]{3,}/g) || [];
    const ar = raw.match(/[\u0600-\u06ff]{2,}/g) || [];
    return [...lat, ...ar].filter((t) => !EVA_STOP.has(t));
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
          "I’m Eva — RegIntel’s research assistant for **our PDF library**.\n\n" +
          "Think of ChatGPT with browsing: I don’t invent from the open web; I **search our indexed SDAIA PDFs**, pull relevant summaries and passages, and answer with **citations + PDF links**.\n\n" +
          `Indexed now: **${count}** summarized PDF(s)` +
          (pdfCatalogCount ? ` · catalog ~${pdfCatalogCount}` : "") +
          ".\n\nAsk about PDPL, privacy, AI ethics, data sharing, or a document title.",
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
    const qRaw = String(question || "").toLowerCase().trim();
    if (!tokens.length && qRaw.length < 2) return [];
    const q = new Set(tokens);
    const scored = [];
    for (const doc of corpus) {
      const title = String(doc.title || "");
      const summary = String(doc.summary || "");
      const points = (doc.key_points || []).join(" ");
      const topics = (doc.topics || []).join(" ");
      const j = String(doc.jurisdiction || "");
      const blob = [title, j, summary, points, topics].join(" ");
      const dt = new Set(tokenizeEva(blob));
      let score = 0;
      q.forEach((t) => {
        if (dt.has(t)) score += 1;
      });
      const titleToks = new Set(tokenizeEva(title));
      q.forEach((t) => {
        if (titleToks.has(t)) score += 4;
      });
      // phrase / substring boosts
      tokens.forEach((t) => {
        if (t.length >= 4 && title.toLowerCase().includes(t)) score += 2;
        if (t.length >= 4 && summary.toLowerCase().includes(t)) score += 1;
        if (j.toLowerCase().includes(t)) score += 2;
      });
      if (qRaw.length >= 6 && title.toLowerCase().includes(qRaw.slice(0, 40))) {
        score += 6;
      }
      if (score >= 1) scored.push({ score, doc });
    }
    scored.sort((a, b) => b.score - a.score);
    if (!scored.length) return [];
    const best = scored[0].score;
    const minKeep = best >= 6 ? Math.max(2, best * 0.35) : 1;
    return scored
      .filter((x) => x.score >= minKeep)
      .slice(0, k)
      .map((x) => x.doc);
  }

  /** Split page text into short passages and rank by query overlap. */
  function rankPassagesForQuestion(question, pages, maxPassages) {
    const q = new Set(tokenizeEva(question));
    if (!q.size || !pages || !pages.length) return [];
    const scored = [];
    for (const pg of pages) {
      const full = String(pg.text || "").trim();
      if (full.length < 40) continue;
      // windows ~500 chars
      const step = 400;
      for (let i = 0; i < full.length; i += step) {
        const window = full.slice(i, i + 550).trim();
        if (window.length < 40) continue;
        const dt = tokenizeEva(window);
        let score = 0;
        q.forEach((t) => {
          if (dt.includes(t) || window.toLowerCase().includes(t)) score += 1;
        });
        if (score >= 1) {
          scored.push({
            score,
            page: pg.page,
            text: window.length > 700 ? window.slice(0, 697) + "…" : window,
          });
        }
      }
    }
    scored.sort((a, b) => b.score - a.score);
    // dedupe near-identical starts
    const out = [];
    const seen = new Set();
    for (const s of scored) {
      const key = s.text.slice(0, 80);
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(s);
      if (out.length >= (maxPassages || 4)) break;
    }
    return out;
  }

  /**
   * ChatGPT-style synthesis over retrieved PDFs + optional deep passages.
   * Only uses our corpus (summaries + extracted snippets), never the open web.
   */
  function evaAnswerLocal(question, hits) {
    if (!hits.length) {
      return {
        answer:
          "I searched our indexed SDAIA PDFs and didn’t find a strong match.\n\n" +
          "Tips:\n" +
          "• Use topic words (privacy, PDPL, AI ethics, data sharing, cybersecurity)\n" +
          "• Or a document title word (newsletter, guideline, policy)\n" +
          "• Ask “list the PDFs” or “status” for what I’ve indexed\n\n" +
          "I only answer from our PDF library — not the open web.",
        citations: [],
      };
    }
    const citations = hits.map((h, i) => ({
      n: i + 1,
      title: h.title,
      url: h.open_url || h.url,
      jurisdiction: h.jurisdiction,
    }));

    const lines = [
      "I searched our SDAIA PDF library (like ChatGPT browsing, but only our documents) and pulled the most relevant sources.",
      "",
      "Answer:",
    ];

    // Synthesize from key points first (more answer-like than dump of full summaries)
    const bullets = [];
    hits.forEach((h, i) => {
      const n = i + 1;
      const pts = (h.key_points || []).slice(0, 3);
      if (pts.length) {
        pts.forEach((p) => bullets.push(`[${n}] ${String(p).trim()}`));
      } else {
        let sum = (h.summary || "").trim();
        if (sum.length > 320) sum = sum.slice(0, 317) + "…";
        if (sum) bullets.push(`[${n}] ${sum}`);
      }
      // deep passages from live PDF extract
      (h.passages || []).slice(0, 2).forEach((p) => {
        bullets.push(
          `[${n} p.${p.page}] “${String(p.text || "").trim()}”`,
        );
      });
    });
    if (bullets.length) {
      bullets.slice(0, 12).forEach((b) => lines.push("• " + b));
    } else {
      lines.push("• See the cited PDF summaries below — I couldn’t extract sharper points.");
    }

    lines.push("");
    lines.push("Sources used:");
    hits.forEach((h, i) => {
      const n = i + 1;
      lines.push(`[${n}] ${h.title || "Untitled"} (${h.jurisdiction || "SDAIA"})`);
      let sum = (h.summary || "").trim();
      if (sum.length > 280) sum = sum.slice(0, 277) + "…";
      if (sum) lines.push("    " + sum);
    });
    lines.push("");
    lines.push("References (open the PDF):");
    citations.forEach((c) => {
      lines.push(`[${c.n}] ${c.title || "PDF"}${c.url ? " — " + c.url : ""}`);
    });
    lines.push("");
    lines.push(
      "I only use our RegIntel/SDAIA PDF index for answers — I don’t browse the open web.",
    );
    return { answer: lines.join("\n"), citations };
  }

  /** Deepen top hits by extracting matching passages from the actual PDFs. */
  async function enrichHitsFromPdfs(question, hits) {
    const out = [];
    for (const h of (hits || []).slice(0, 3)) {
      const url = h.open_url || h.url || "";
      const copy = { ...h, passages: [] };
      if (isHttpUrl(url) && typeof extractPdfTextByPage === "function") {
        try {
          const extracted = await extractPdfTextByPage(url, 12);
          copy.passages = rankPassagesForQuestion(
            question,
            extracted.pages || [],
            3,
          );
        } catch (_) {
          /* CORS / scanned PDF — keep summary-only */
        }
      }
      out.push(copy);
    }
    // keep remaining hits without deep extract
    for (const h of (hits || []).slice(3)) out.push({ ...h, passages: [] });
    return out;
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
        ? "PDF RAG · LLM · " + count + " docs"
        : count
          ? "PDF RAG · " + count + " docs"
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
              ? `Hi, I’m Eva — your SDAIA PDF research assistant.\n\n` +
                  `Like ChatGPT with web browsing, I search a library for answers — but mine is **our RegIntel PDF corpus**, not the open web.\n\n` +
                  `Indexed: **${count}** summarized PDF(s)` +
                  (pdfCatalogCount
                    ? ` · catalog ~${pdfCatalogCount} PDFs`
                    : "") +
                  `.\n\nAsk about privacy, PDPL, AI ethics, data sharing, or a document name. I’ll pull the relevant PDFs, extract supporting points, and cite links.\n\nAsk “status” or “list the PDFs” anytime.`
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

      // Prefer optional local Eva API (SpaceXAI RAG) when configured
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
            body: JSON.stringify({ question: q, k: 10, deep: true }),
          });
          if (res.ok) {
            const data = await res.json();
            finish(data.answer, data.citations || []);
            return;
          }
        } catch {
          /* fall through to client-side PDF RAG */
        }
      }

      // Client-side: search summaries → open top PDFs → extract matching passages → answer + cite
      typing.textContent = "Eva is searching our PDFs…";
      const hits = retrieveEva(q, corpus, 8);
      typing.textContent = hits.length
        ? "Eva is reading the top matching PDFs…"
        : "Eva is thinking…";
      let enriched = hits;
      try {
        enriched = await enrichHitsFromPdfs(q, hits);
      } catch (_) {
        enriched = hits;
      }
      const out = evaAnswerLocal(q, enriched);
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

  /** Public site: original Saudi sheet + SDAIA/TGA/MC/MEWA (not global gazette). */
  function isAllowedSaudiMinistryRow(p) {
    const j = String((p && p.jurisdiction) || "");
    const h = String((p && p.host) || "").toLowerCase();
    const u = String((p && (p.url || p.open_url || p.source_page)) || "").toLowerCase();
    const blob = (j + " " + h + " " + u).toLowerCase();
    const hosts = [
      "sdaia.gov", "tga.gov", "mc.gov", "mewa.gov", "momah.gov", "mof.gov",
      "nca.gov", "ia.gov.sa", "socpa.org", "moi.gov", "nazaha.gov", "sama.gov",
      "moj.gov", "gac.gov", "cst.gov", "cma.org", "saudiexchange", "gosi.gov",
      "saso.gov", "saip.gov", "zatca.gov",
    ];
    if (hosts.some((x) => blob.includes(x))) return true;
    return /Saudi Arabia - /i.test(j) || /Ministry of Commerce/i.test(j);
  }
  // backward-compatible alias used elsewhere
  function isSdaiaRow(p) {
    return isAllowedSaudiMinistryRow(p);
  }

  function siteCodeFromLabel(jurisdiction) {
    const j = String(jurisdiction || "").trim();
    const m = /^Saudi Arabia\s*[-–—]\s*([A-Za-z0-9]+)\s*$/i.exec(j);
    if (!m) return "";
    return m[1].toUpperCase();
  }

  function siteCodeForPdf(p) {
    const fromLabel = siteCodeFromLabel(p && p.jurisdiction);
    if (fromLabel) return fromLabel;
    return siteCodeFromUrl((p && (p.open_url || p.url || p.host)) || "");
  }

  function pdfMatchesSite(p, site) {
    if (!site) return isAllowedSaudiMinistryRow(p);
    const want = String(site.code || "").toUpperCase();
    if (!want) return false;
    return siteCodeForPdf(p) === want;
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

  /** Merge catalog PDFs with Eva extractive summaries. Optional site filter. */
  function buildSdaiaSummaryRows(pdfs, evaSummaries, site) {
    const pred = (p) => pdfMatchesSite(p, site);
    const byUrl = new Map();
    const byId = new Map();
    for (const e of evaSummaries || []) {
      if (!e || !pred(e)) continue;
      const url = e.open_url || e.url || "";
      const k = normalizePdfKey(url);
      if (k) byUrl.set(k, e);
      if (e.id) byId.set(String(e.id), e);
    }
    const rows = [];
    const seen = new Set();
    for (const p of pdfs || []) {
      if (!pred(p)) continue;
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
      if (!e || !pred(e)) continue;
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

  /** Guess source language (never send "auto" to APIs that reject it). */
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

  function normalizeTranslateLang(code) {
    const c = String(code || "en").trim();
    if (!c || c === "auto" || c === "Autodetect") return "en";
    if (c.toLowerCase() === "zh" || c.toLowerCase() === "zh-cn") return "zh-CN";
    if (c.includes("-")) {
      const [a, b] = c.split("-");
      if (a.toLowerCase() === "zh") return "zh-CN";
      return a.toLowerCase();
    }
    return c.toLowerCase();
  }

  // Session cache + global queue avoid MyMemory/Google 429 spam
  const _translateCache = new Map();
  let _translateChain = Promise.resolve();

  function translateCacheKey(text, source, target) {
    return source + ">" + target + ":" + text;
  }

  function getCachedTranslation(text, source, target) {
    const k = translateCacheKey(text, source, target);
    if (_translateCache.has(k)) return _translateCache.get(k);
    try {
      const raw = sessionStorage.getItem("regintel_tr_" + hashStr(k));
      if (raw) {
        _translateCache.set(k, raw);
        return raw;
      }
    } catch (_) {
      /* ignore */
    }
    return null;
  }

  function setCachedTranslation(text, source, target, translated) {
    const k = translateCacheKey(text, source, target);
    _translateCache.set(k, translated);
    try {
      sessionStorage.setItem("regintel_tr_" + hashStr(k), translated);
    } catch (_) {
      /* ignore quota */
    }
  }

  function hashStr(s) {
    let h = 0;
    const str = String(s);
    for (let i = 0; i < str.length; i++) h = (Math.imul(31, h) + str.charCodeAt(i)) | 0;
    return (h >>> 0).toString(36);
  }

  function chunkText(text, maxLen) {
    const chunks = [];
    let rest = String(text || "");
    while (rest.length) {
      if (rest.length <= maxLen) {
        chunks.push(rest);
        break;
      }
      let cut = rest.lastIndexOf(" ", maxLen);
      if (cut < maxLen * 0.4) cut = rest.lastIndexOf("\n", maxLen);
      if (cut < maxLen * 0.4) cut = maxLen;
      chunks.push(rest.slice(0, cut));
      rest = rest.slice(cut).trimStart();
    }
    return chunks;
  }

  /** Unofficial Google Translate (client=gtx) — no API key; works in browser CORS. */
  async function translateViaGoogleGtx(chunk, source, target) {
    const sl = source === "zh-CN" ? "zh-CN" : source;
    const tl = target === "zh-CN" ? "zh-CN" : target;
    const url =
      "https://translate.googleapis.com/translate_a/single?client=gtx&sl=" +
      encodeURIComponent(sl) +
      "&tl=" +
      encodeURIComponent(tl) +
      "&dt=t&q=" +
      encodeURIComponent(chunk);
    const res = await fetch(url);
    if (res.status === 429) throw new Error("HTTP 429");
    if (!res.ok) throw new Error("Google translate HTTP " + res.status);
    const data = await res.json();
    // data[0] = [[translated, original, ...], ...]
    if (!Array.isArray(data) || !Array.isArray(data[0])) {
      throw new Error("Unexpected Google translate response");
    }
    return data[0]
      .map((row) => (Array.isArray(row) ? row[0] : ""))
      .join("");
  }

  /** MyMemory free tier — secondary; often 429 if overused. */
  async function translateViaMyMemory(chunk, source, target) {
    const pair = source + "|" + target;
    const url =
      "https://api.mymemory.translated.net/get?q=" +
      encodeURIComponent(chunk) +
      "&langpair=" +
      encodeURIComponent(pair);
    const res = await fetch(url);
    if (res.status === 429) throw new Error("HTTP 429");
    if (!res.ok) throw new Error("MyMemory HTTP " + res.status);
    const data = await res.json();
    const t =
      (data && data.responseData && data.responseData.translatedText) || "";
    const status = data && data.responseStatus;
    if (
      !t ||
      /QUERY LENGTH LIMIT/i.test(t) ||
      /INVALID SOURCE LANGUAGE/i.test(t) ||
      /INVALID TARGET LANGUAGE/i.test(t) ||
      /MYMEMORY WARNING/i.test(t) ||
      (status && Number(status) !== 200)
    ) {
      throw new Error(t || "MyMemory failed");
    }
    return t;
  }

  /** Lingva public mirror (Google-backed). */
  async function translateViaLingva(chunk, source, target) {
    const sl = source === "zh-CN" ? "zh" : source;
    const tl = target === "zh-CN" ? "zh" : target;
    const hosts = [
      "https://lingva.ml",
      "https://lingva.thedaviddelta.com",
    ];
    let lastErr = "";
    for (const host of hosts) {
      try {
        const url =
          host +
          "/api/v1/" +
          encodeURIComponent(sl) +
          "/" +
          encodeURIComponent(tl) +
          "/" +
          encodeURIComponent(chunk);
        const res = await fetch(url);
        if (res.status === 429) {
          lastErr = "HTTP 429";
          continue;
        }
        if (!res.ok) {
          lastErr = "Lingva HTTP " + res.status;
          continue;
        }
        const data = await res.json();
        if (data && data.translation) return data.translation;
        lastErr = "Empty Lingva response";
      } catch (e) {
        lastErr = e.message || String(e);
      }
    }
    throw new Error(lastErr || "Lingva failed");
  }

  async function translateOneChunk(chunk, source, target) {
    const cached = getCachedTranslation(chunk, source, target);
    if (cached != null) return cached;

    const engines = [
      translateViaGoogleGtx,
      translateViaLingva,
      translateViaMyMemory,
    ];
    let lastErr = "";
    for (const eng of engines) {
      try {
        const t = await eng(chunk, source, target);
        if (t && String(t).trim()) {
          setCachedTranslation(chunk, source, target, t);
          return t;
        }
      } catch (e) {
        lastErr = e.message || String(e);
        // brief backoff on rate limit before next engine
        if (/429/.test(lastErr)) await new Promise((r) => setTimeout(r, 400));
      }
    }
    throw new Error(
      lastErr ||
        "All free translate services failed (often rate-limited). Wait a minute and retry.",
    );
  }

  /**
   * Translate text to target language. Uses Google gtx first (avoids MyMemory 429),
   * then Lingva, then MyMemory. Cached + serialized to reduce rate limits.
   */
  async function translateTextChunks(text, targetLang) {
    const raw = String(text || "").trim();
    if (!raw) return "";
    const target = normalizeTranslateLang(targetLang || "en");
    let source = normalizeTranslateLang(detectSourceLang(raw));
    if (source.split("-")[0] === target.split("-")[0]) return raw;

    const fullCached = getCachedTranslation(raw, source, target);
    if (fullCached != null) return fullCached;

    // Serialize all card translates so we don't fire 10 requests at once
    const run = _translateChain.then(async () => {
      const chunks = chunkText(raw, 900);
      const out = [];
      for (let i = 0; i < chunks.length; i++) {
        // try detected source, then en, then ar
        const sources = [...new Set([source, "en", "ar"])].filter(
          (s) => s.split("-")[0] !== target.split("-")[0],
        );
        let translated = "";
        let lastErr = "";
        for (const sl of sources) {
          try {
            translated = await translateOneChunk(chunks[i], sl, target);
            break;
          } catch (e) {
            lastErr = e.message || String(e);
          }
        }
        if (!translated) throw new Error(lastErr || "Translation failed");
        out.push(translated);
        if (i < chunks.length - 1) await new Promise((r) => setTimeout(r, 250));
      }
      const joined = out.join(" ");
      setCachedTranslation(raw, source, target, joined);
      return joined;
    });
    // keep chain alive even on failure
    _translateChain = run.catch(() => {});
    return run;
  }

  /** Pack title/summary/points so one Google gtx call can translate the whole card. */
  function packCardTranslatePayload(title, summary, points) {
    let s = "[[T]]\n" + String(title || "") + "\n[[S]]\n" + String(summary || "");
    (points || []).forEach((p, i) => {
      s += "\n[[P" + i + "]]\n" + String(p || "");
    });
    return s;
  }

  function unpackCardTranslatePayload(text, nPoints) {
    const t = String(text || "");
    const idxS = t.search(/\[\[S\]\]/i);
    const idxT = t.search(/\[\[T\]\]/i);
    if (idxS < 0) return null;
    const titleStart = idxT >= 0 ? idxT + 5 : 0;
    const title = t.slice(titleStart, idxS).trim();
    const pAt = [];
    for (let i = 0; i < nPoints; i++) {
      const m = t.search(new RegExp("\\[\\[P" + i + "\\]\\]", "i"));
      pAt.push(m);
    }
    const firstP = pAt.find((x) => x >= 0);
    const summary = t.slice(idxS + 5, firstP >= 0 ? firstP : t.length).trim();
    const points = [];
    for (let i = 0; i < nPoints; i++) {
      if (pAt[i] < 0) {
        points.push("");
        continue;
      }
      const start = pAt[i] + ("[[P" + i + "]]").length;
      let end = t.length;
      for (let j = i + 1; j < nPoints; j++) {
        if (pAt[j] > pAt[i]) {
          end = pAt[j];
          break;
        }
      }
      points.push(t.slice(start, end).trim());
    }
    if (!title && !summary && !points.some(Boolean)) return null;
    return { title, summary, points };
  }

  /**
   * One Google call for the whole Summary card. Falls back to per-field
   * translateTextChunks (Google → Lingva → MyMemory, chunked) on any failure.
   */
  async function translateCardFields(title, summary, points, targetLang) {
    const titleIn = String(title || "");
    const summaryIn = String(summary || "");
    const pointsIn = (points || []).map((p) => String(p || ""));
    const target = normalizeTranslateLang(targetLang || "en");
    const blob = [titleIn, summaryIn, ...pointsIn].join("\n");
    const source = normalizeTranslateLang(detectSourceLang(blob || "en"));
    if (source.split("-")[0] === target.split("-")[0]) {
      return { title: titleIn, summary: summaryIn, points: pointsIn };
    }

    const packed = packCardTranslatePayload(titleIn, summaryIn, pointsIn);
    const cacheKey = "card:" + packed;
    const cached = getCachedTranslation(cacheKey, source, target);
    if (cached != null) {
      const fromCache = unpackCardTranslatePayload(cached, pointsIn.length);
      if (fromCache) {
        return {
          title: fromCache.title || titleIn,
          summary: fromCache.summary || summaryIn,
          points: pointsIn.map((p, i) => fromCache.points[i] || p),
        };
      }
    }

    const SINGLE_MAX = 3500;
    if (packed.length <= SINGLE_MAX) {
      try {
        const translated = await translateViaGoogleGtx(packed, source, target);
        const fields = unpackCardTranslatePayload(translated, pointsIn.length);
        if (fields && (fields.summary || fields.title || fields.points.some(Boolean))) {
          setCachedTranslation(cacheKey, source, target, translated);
          return {
            title: fields.title || titleIn,
            summary: fields.summary || summaryIn,
            points: pointsIn.map((p, i) => fields.points[i] || p),
          };
        }
      } catch (_) {
        /* fall through to per-field */
      }
    }

    const titleOut = titleIn ? await translateTextChunks(titleIn, targetLang) : "";
    const summaryOut = summaryIn ? await translateTextChunks(summaryIn, targetLang) : "";
    const pointsOut = [];
    for (const p of pointsIn) {
      pointsOut.push(p ? await translateTextChunks(p, targetLang) : "");
    }
    return { title: titleOut, summary: summaryOut, points: pointsOut };
  }

  function googleTranslatePdfUrl(pdfUrl, targetLang) {
    // Webpage translator — often fails for binary PDFs; kept as last-resort link
    const tl = normalizeTranslateLang(targetLang || "en");
    return (
      "https://translate.google.com/translate?sl=auto&tl=" +
      encodeURIComponent(tl) +
      "&u=" +
      encodeURIComponent(pdfUrl)
    );
  }

  function googleTranslateDocsUrl(targetLang) {
    const tl = normalizeTranslateLang(targetLang || "en");
    return (
      "https://translate.google.com/?sl=auto&tl=" +
      encodeURIComponent(tl) +
      "&op=docs"
    );
  }

  function ensurePdfXlateModal() {
    return {
      modal: document.getElementById("pdfXlateModal"),
      status: document.getElementById("pdfXlateStatus"),
      body: document.getElementById("pdfXlateBody"),
      actions: document.getElementById("pdfXlateActions"),
      title: document.getElementById("pdfXlateTitle"),
      close: document.getElementById("pdfXlateClose"),
      backdrop: document.getElementById("pdfXlateBackdrop"),
    };
  }

  function openPdfXlateModal(title) {
    const ui = ensurePdfXlateModal();
    if (!ui.modal) return ui;
    if (ui.title) ui.title.textContent = title || "Translate PDF";
    if (ui.status) ui.status.textContent = "Starting…";
    if (ui.body) ui.body.innerHTML = "";
    if (ui.actions) {
      ui.actions.hidden = true;
      ui.actions.innerHTML = "";
    }
    ui.modal.hidden = false;
    return ui;
  }

  function closePdfXlateModal() {
    const ui = ensurePdfXlateModal();
    if (ui.modal) ui.modal.hidden = true;
  }

  function setupPdfXlateModalOnce() {
    if (window.__regintelPdfXlateReady) return;
    window.__regintelPdfXlateReady = true;
    const ui = ensurePdfXlateModal();
    if (ui.close) ui.close.addEventListener("click", closePdfXlateModal);
    if (ui.backdrop) ui.backdrop.addEventListener("click", closePdfXlateModal);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closePdfXlateModal();
    });
  }

  let _pdfJsLoading = null;
  function loadPdfJs() {
    if (window.pdfjsLib) return Promise.resolve(window.pdfjsLib);
    if (_pdfJsLoading) return _pdfJsLoading;
    _pdfJsLoading = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src =
        "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js";
      s.async = true;
      s.onload = () => {
        try {
          const lib = window.pdfjsLib;
          if (!lib) {
            reject(new Error("pdf.js failed to load"));
            return;
          }
          lib.GlobalWorkerOptions.workerSrc =
            "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js";
          resolve(lib);
        } catch (e) {
          reject(e);
        }
      };
      s.onerror = () => reject(new Error("Could not load pdf.js"));
      document.head.appendChild(s);
    });
    return _pdfJsLoading;
  }

  async function fetchPdfBytes(pdfUrl) {
    // Direct CORS fetch (works if host allows)
    try {
      const res = await fetch(pdfUrl, { mode: "cors", credentials: "omit" });
      if (res.ok) {
        const buf = await res.arrayBuffer();
        if (buf && buf.byteLength > 100) return new Uint8Array(buf);
      }
    } catch (_) {
      /* try proxies */
    }
    // Public CORS proxies (best-effort for locked gov hosts)
    const proxies = [
      (u) => "https://api.allorigins.win/raw?url=" + encodeURIComponent(u),
      (u) => "https://corsproxy.io/?" + encodeURIComponent(u),
    ];
    for (const make of proxies) {
      try {
        const res = await fetch(make(pdfUrl), { credentials: "omit" });
        if (!res.ok) continue;
        const buf = await res.arrayBuffer();
        if (buf && buf.byteLength > 500) {
          const u8 = new Uint8Array(buf);
          // PDF magic
          if (u8[0] === 0x25 && u8[1] === 0x50 && u8[2] === 0x44 && u8[3] === 0x46) {
            return u8;
          }
        }
      } catch (_) {
        /* next */
      }
    }
    return null;
  }

  async function extractPdfTextByPage(pdfUrl, maxPages) {
    const pdfjsLib = await loadPdfJs();
    const bytes = await fetchPdfBytes(pdfUrl);
    if (!bytes) {
      const err = new Error("CORS_BLOCKED");
      err.code = "CORS_BLOCKED";
      throw err;
    }
    const doc = await pdfjsLib.getDocument({ data: bytes }).promise;
    const total = doc.numPages || 0;
    const limit = Math.min(total, maxPages || 40);
    const pages = [];
    for (let i = 1; i <= limit; i++) {
      const page = await doc.getPage(i);
      const content = await page.getTextContent();
      const text = (content.items || [])
        .map((it) => (it && it.str != null ? String(it.str) : ""))
        .join(" ")
        .replace(/\s+/g, " ")
        .trim();
      pages.push({ page: i, text });
    }
    return { pages, totalPages: total, limitedTo: limit };
  }

  /**
   * Translate full PDF text (extracted) into target language and show in modal.
   * Google's webpage translator does not reliably translate binary PDFs.
   */
  async function translateFullPdf(pdfUrl, targetLang, docTitle) {
    setupPdfXlateModalOnce();
    const tl = normalizeTranslateLang(targetLang || "en");
    const ui = openPdfXlateModal(
      "Translate PDF" + (docTitle ? " — " + String(docTitle).slice(0, 60) : ""),
    );
    const setStatus = (msg) => {
      if (ui.status) ui.status.textContent = msg;
    };
    const setActions = (html) => {
      if (!ui.actions) return;
      ui.actions.hidden = !html;
      ui.actions.innerHTML = html || "";
    };

    setActions(
      `<a class="btn ghost" href="${escapeAttr(pdfUrl)}" target="_blank" rel="noopener">Download original PDF</a>` +
        `<a class="btn ghost" href="${escapeAttr(googleTranslateDocsUrl(tl))}" target="_blank" rel="noopener">Google Translate · Documents</a>`,
    );

    try {
      setStatus("Loading PDF and extracting text…");
      const extracted = await extractPdfTextByPage(pdfUrl, 40);
      const nonEmpty = extracted.pages.filter((p) => p.text && p.text.length > 20);
      if (!nonEmpty.length) {
        setStatus(
          "No extractable text (scanned/image PDF). Use Google Translate Documents: download the PDF, then upload it there.",
        );
        if (ui.body) {
          ui.body.innerHTML =
            `<p class="muted">This file has little or no selectable text. Full-layout translation needs Google’s document upload tool.</p>` +
            `<p><a class="link" href="${escapeAttr(googleTranslateDocsUrl(tl))}" target="_blank" rel="noopener">Open Google Translate → Documents</a></p>`;
        }
        return;
      }

      if (ui.body) ui.body.innerHTML = "";
      const note =
        extracted.totalPages > extracted.limitedTo
          ? `Translating pages 1–${extracted.limitedTo} of ${extracted.totalPages} (cap for free translate). `
          : `Translating ${nonEmpty.length} text page(s). `;
      setStatus(note + "This can take a minute…");

      for (let i = 0; i < nonEmpty.length; i++) {
        const p = nonEmpty[i];
        setStatus(
          `${note}Page ${p.page} (${i + 1}/${nonEmpty.length}) → ${tl}…`,
        );
        // Cap very long pages
        const src = p.text.length > 4500 ? p.text.slice(0, 4500) + "…" : p.text;
        let translated = src;
        try {
          translated = await translateTextChunks(src, tl);
        } catch (e) {
          translated =
            "[Translation incomplete for this page: " +
            (e.message || String(e)) +
            "]\n\n" +
            src;
        }
        if (ui.body) {
          const block = document.createElement("div");
          block.className = "page-block";
          block.innerHTML =
            `<p class="page-label">Page ${escapeHtml(String(p.page))}</p>` +
            `<div>${escapeHtml(translated)}</div>`;
          ui.body.appendChild(block);
          ui.body.scrollTop = ui.body.scrollHeight;
        }
      }
      setStatus(
        `Done — text from ${nonEmpty.length} page(s) translated to ${tl}. ` +
          (extracted.totalPages > extracted.limitedTo
            ? `Only first ${extracted.limitedTo} of ${extracted.totalPages} pages. `
            : "") +
          "Formatting/images are not preserved; use Google Documents upload for full layout.",
      );
    } catch (e) {
      const code = e && e.code;
      const cors = code === "CORS_BLOCKED" || /CORS/i.test(e.message || "");
      setStatus(
        cors
          ? "Cannot read this PDF in the browser (site blocks cross-origin access)."
          : "PDF translate failed: " + (e.message || String(e)),
      );
      if (ui.body) {
        ui.body.innerHTML =
          `<p><strong>Why the old “Translate PDF” failed:</strong> Google’s page translator only works well on HTML pages, not full PDF files.</p>` +
          `<p><strong>What to do:</strong></p>` +
          `<ol>` +
          `<li>Download the original PDF.</li>` +
          `<li>Open Google Translate → Documents and upload it (layout-preserving).</li>` +
          `</ol>` +
          `<p>` +
          `<a class="btn primary" href="${escapeAttr(pdfUrl)}" target="_blank" rel="noopener">Download PDF</a> ` +
          `<a class="btn ghost" href="${escapeAttr(googleTranslateDocsUrl(tl))}" target="_blank" rel="noopener">Google Translate Documents</a>` +
          `</p>` +
          (cors
            ? `<p class="muted">This host does not allow the app to read the PDF bytes, so in-page full-text extract is blocked.</p>`
            : "");
      }
    }
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

  /** Last language chosen on Summary (for select default only — no auto-translate). */
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
    // Show original extract only — translate only when user clicks Translate
    const cacheKey = simpleHash(origSummary + "\n" + (r.title || "") + "\n" + pointsArr.join("\n"));
    const displayTitle = r.title || "Untitled PDF";
    const summary = origSummary
      ? escapeHtml(origSummary)
      : '<span class="muted">No extractive summary yet for this PDF.</span>';
    const points = pointsArr.map((p) => `<li>${escapeHtml(p)}</li>`).join("");
    const badge = r.has_summary
      ? `<span class="badge badge-fed">Extracted</span>`
      : `<span class="badge badge-src">Pending</span>`;
    const method =
      r.method || r.summarized_at
        ? `<p class="meta-line">${escapeHtml(r.method || "summary")}${
            r.summarized_at ? " · " + escapeHtml(String(r.summarized_at).slice(0, 19)) : ""
          }</p>`
        : "";
    // Must be unique per card: catalog has many duplicate `id`s (www vs apex twins).
    const cardId =
      "sum-" +
      simpleHash(String(r.id || "") + "|" + String(link || r.title || "") + "|" + String(r.summarized_at || ""));
    const defaultLang = preferredSummaryTargetLang();
    return `
      <article class="pdf-card summary-card" role="listitem" id="${escapeAttr(cardId)}"
        data-orig-title="${escapeAttr(r.title || "Untitled PDF")}"
        data-orig-summary="${escapeAttr(origSummary)}"
        data-orig-points="${escapeAttr(JSON.stringify(pointsArr))}"
        data-en-cache-key="${escapeAttr(cacheKey)}"
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
          <button type="button" class="btn ghost sum-restore-btn" data-card="${escapeAttr(cardId)}" hidden>
            Original
          </button>
          ${
            hasLink
              ? `<button type="button" class="btn ghost sum-pdf-translate-btn" data-card="${escapeAttr(cardId)}">Translate PDF</button>`
              : ""
          }
        </div>
        <p class="meta-line sum-translate-status" hidden></p>
        ${
          hasLink
            ? `<div class="card-actions"><a class="btn primary" href="${escapeAttr(link)}" target="_blank" rel="noopener">Open PDF</a></div>`
            : ""
        }
      </article>`;
  }

  function wireSummaryTranslateButtons(listEl) {
    if (!listEl) return;
    setupPdfXlateModalOnce();
    listEl.querySelectorAll(".sum-lang").forEach((sel) => {
      sel.addEventListener("change", () => {
        try {
          localStorage.setItem("regintel_summary_lang", sel.value);
        } catch (_) {
          /* ignore */
        }
      });
    });

    listEl.querySelectorAll(".sum-pdf-translate-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const card = btn.closest(".summary-card");
        if (!card) return;
        const langSel = card.querySelector(".sum-lang");
        const targetLang = (langSel && langSel.value) || "en";
        const pdfUrl = card.getAttribute("data-pdf-url") || "";
        const title = card.getAttribute("data-orig-title") || "PDF";
        if (!isHttpUrl(pdfUrl)) return;
        try {
          localStorage.setItem("regintel_summary_lang", targetLang);
        } catch (_) {
          /* ignore */
        }
        btn.disabled = true;
        try {
          await translateFullPdf(pdfUrl, targetLang, title);
        } finally {
          btn.disabled = false;
        }
      });
    });

    listEl.querySelectorAll(".sum-translate-btn").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const card = btn.closest(".summary-card");
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
          const translated = await translateCardFields(
            origTitle,
            origSummary,
            origPoints,
            targetLang,
          );
          const titleOut = translated.title;
          const summaryOut = translated.summary;
          const pointsOut = translated.points;
          if (titleEl) titleEl.textContent = titleOut || origTitle;
          if (sumEl) {
            if (summaryOut) sumEl.textContent = summaryOut;
            else
              sumEl.innerHTML =
                '<span class="muted">No extractive summary yet for this PDF.</span>';
          }
          if (pointsEl && origPoints.length) {
            pointsEl.hidden = false;
            pointsEl.innerHTML = pointsOut
              .map((p) => `<li>${escapeHtml(p)}</li>`)
              .join("");
          }
          // Optional cache when user explicitly translates to English
          if (normalizeTranslateLang(targetLang).split("-")[0] === "en" && summaryOut) {
            const cacheKey =
              card.getAttribute("data-en-cache-key") || simpleHash(origSummary);
            writeEnCache(cacheKey, {
              title: titleOut,
              summary: summaryOut,
              points: pointsOut,
            });
          }
          if (restoreBtn) restoreBtn.hidden = false;
          if (status) {
            const unchanged =
              titleOut === origTitle &&
              summaryOut === origSummary &&
              pointsOut.join("\n") === origPoints.join("\n");
            status.textContent = unchanged
              ? "Already in " +
                targetLang +
                " (or same as original). Pick another language if you expected a change."
              : "Summary translated to " +
                targetLang +
                ". Use “Translate PDF” for full document text (opens a viewer).";
          }
        } catch (e) {
          if (status) {
            status.hidden = false;
            const msg = e.message || String(e);
            status.textContent = /429/.test(msg)
              ? "Rate limited (too many free translate requests). Wait ~30s and try again — or use “Translate PDF”."
              : "Translation failed: " + msg + ". Try again, or use “Translate PDF”.";
          }
        } finally {
          btn.disabled = false;
        }
      });
    });

    listEl.querySelectorAll(".sum-restore-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const card = btn.closest(".summary-card");
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
  }

  const summaryView = { rows: [], withSum: 0, wired: false };

  function initSummaries(pdfs, evaSummaries, site) {
    const list = document.getElementById("summaryList");
    const empty = document.getElementById("summaryEmpty");
    const countEl = document.getElementById("summaryCount");
    const search = document.getElementById("summarySearch");
    const filter = document.getElementById("summaryFilter");
    if (!list) return;

    summaryView.rows = buildSdaiaSummaryRows(pdfs, evaSummaries, site);
    summaryView.withSum = summaryView.rows.filter((r) => r.has_summary).length;

    function render() {
      const rows = summaryView.rows;
      const withSum = summaryView.withSum;
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
          " PDFs";
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
    if (!summaryView.wired) {
      summaryView.wired = true;
      if (search) {
        search.addEventListener("input", () => {
          clearTimeout(t);
          t = setTimeout(render, 120);
        });
      }
      if (filter) filter.addEventListener("change", render);
    }
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

  function defaultMinistries() {
    return [
      {
        code: "SDAIA",
        name: "Saudi Data and Artificial Intelligence Authority (SDAIA)",
        url: "https://sdaia.gov.sa",
      },
      {
        code: "TGA",
        name: "Transport General Authority (TGA)",
        url: "https://tga.gov.sa",
      },
      {
        code: "MC",
        name: "Ministry of Commerce (MC)",
        url: "https://mc.gov.sa",
      },
      {
        code: "MEWA",
        name: "Ministry of Environment, Water and Agriculture (MEWA)",
        url: "https://mewa.gov.sa",
      },
    ];
  }

  function crawlLabelFromUrl(raw) {
    const h = hostOf(raw);
    if (h.includes("sdaia")) return "Saudi Arabia - SDAIA";
    if (h.includes("mewa")) return "Saudi Arabia - MEWA";
    if (h.includes("tga.gov")) return "Saudi Arabia - TGA";
    if (h.includes("mc.gov")) return "Saudi Arabia - MC";
    if (h.includes("momah")) return "Saudi Arabia - MOMAH";
    if (h.includes("mof.gov")) return "Saudi Arabia - MOF";
    if (h.includes("nca.gov")) return "Saudi Arabia - NCA";
    if (h === "ia.gov.sa" || h.endsWith(".ia.gov.sa")) return "Saudi Arabia - IA";
    if (h.includes("socpa")) return "Saudi Arabia - SOCPA";
    if (h.includes("moi.gov")) return "Saudi Arabia - MOI";
    if (h.includes("nazaha")) return "Saudi Arabia - Nazaha";
    if (h.includes("sama.gov")) return "Saudi Arabia - SAMA";
    if (h.includes("moj.gov")) return "Saudi Arabia - MOJ";
    if (h.includes("gac.gov")) return "Saudi Arabia - GAC";
    if (h.includes("cst.gov")) return "Saudi Arabia - CST";
    if (h.includes("cma.org")) return "Saudi Arabia - CMA";
    if (h.includes("saudiexchange")) return "Saudi Arabia - Tadawul";
    if (h.includes("gosi.gov")) return "Saudi Arabia - GOSI";
    if (h.includes("saso.gov")) return "Saudi Arabia - SASO";
    if (h.includes("saip.gov")) return "Saudi Arabia - SAIP";
    if (h.includes("zatca")) return "Saudi Arabia - ZATCA";
    return h ? "Ministry - " + h : "Ministry";
  }

  function collectSites(ministries, pdfs) {
    const known = (ministries && ministries.length ? ministries : defaultMinistries()).map((m) => ({
      code: String(m.code || hostOf(m.url) || "SITE").toUpperCase(),
      name: m.name || m.code || hostOf(m.url),
      url: m.url || "",
    }));
    const byCode = new Map(known.map((s) => [s.code, { ...s, count: 0, summaries: 0 }]));
    for (const p of pdfs || []) {
      const code = siteCodeForPdf(p);
      if (!code) continue;
      if (!byCode.has(code)) {
        const h = hostOf(p.open_url || p.url || "") || String(p.host || "").replace(/^www\./i, "");
        byCode.set(code, {
          code,
          name: code,
          url: h ? "https://" + h : "",
          count: 0,
          summaries: 0,
        });
      }
      byCode.get(code).count += 1;
    }
    return [...byCode.values()].sort((a, b) => b.count - a.count || a.code.localeCompare(b.code));
  }

  function siteCodeFromUrl(raw) {
    const h = hostOf(raw);
    if (h.includes("sdaia")) return "SDAIA";
    if (h.includes("mewa")) return "MEWA";
    if (h.includes("tga.gov")) return "TGA";
    if (h.includes("mc.gov")) return "MC";
    if (h.includes("momah")) return "MOMAH";
    if (h.includes("mof.gov")) return "MOF";
    if (h.includes("nca.gov")) return "NCA";
    if (h === "ia.gov.sa" || h.endsWith(".ia.gov.sa")) return "IA";
    if (h.includes("socpa")) return "SOCPA";
    if (h.includes("moi.gov")) return "MOI";
    if (h.includes("nazaha")) return "NAZAHA";
    if (h.includes("sama.gov")) return "SAMA";
    if (h.includes("moj.gov")) return "MOJ";
    if (h.includes("gac.gov")) return "GAC";
    if (h.includes("cst.gov")) return "CST";
    if (h.includes("cma.org")) return "CMA";
    if (h.includes("saudiexchange")) return "TADAWUL";
    if (h.includes("gosi.gov")) return "GOSI";
    if (h.includes("saso.gov")) return "SASO";
    if (h.includes("saip.gov")) return "SAIP";
    if (h.includes("zatca")) return "ZATCA";
    return (h.split(".")[0] || "SITE").toUpperCase();
  }

  // Only the "I just clicked Start" overlay lives in this browser.
  // Shared jobs come from web/data/active_crawls.json so every device matches.
  const LOCAL_START_KEY = "regintel_local_starts_v2";
  function readLocalStarts() {
    try {
      const raw = localStorage.getItem(LOCAL_START_KEY);
      const arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr : [];
    } catch {
      return [];
    }
  }
  function writeLocalStarts(list) {
    try {
      localStorage.setItem(LOCAL_START_KEY, JSON.stringify(list.slice(0, 8)));
    } catch {
      /* ignore */
    }
  }
  function ageMs(iso) {
    const t = Date.parse(iso || "");
    return Number.isFinite(t) ? Date.now() - t : Infinity;
  }
  function isLivePhase(phase) {
    const p = String(phase || "").toLowerCase();
    return (
      p === "discovering" ||
      p === "downloading" ||
      p === "starting" ||
      p === "running" ||
      p === "queued"
    );
  }

  function crawlLooksFinished(phase, listed, downloaded, toDownload, message) {
    const p = String(phase || "").toLowerCase();
    if (p === "idle" || p === "complete" || p === "stopped" || p === "listed") return true;
    const rem = Number(toDownload);
    const found = Number(listed) || 0;
    const saved = Number(downloaded) || 0;
    if (
      (p === "downloading" || p === "listed") &&
      rem === 0 &&
      (found > 0 || saved > 0 || /ok=\d+/.test(String(message || "")))
    ) {
      return true;
    }
    return false;
  }

  async function dispatchMinistryCrawl(siteUrl) {
    const url = siteUrl.startsWith("http") ? siteUrl : "https://" + siteUrl;
    const label = crawlLabelFromUrl(url);
    const payload = {
      url,
      label,
      max_pages: "2000",
      delay: "0.25",
      discover_only: "false",
    };
    const bases = [
      window.REGINTEL_CRAWL_API,
      window.REGINTEL_EVA_API,
      typeof localStorage !== "undefined" && localStorage.getItem("regintel_crawl_api"),
      typeof localStorage !== "undefined" && localStorage.getItem("regintel_eva_api"),
      "http://127.0.0.1:8787",
      "",
    ]
      .map((s) => String(s || "").replace(/\/$/, ""))
      .filter((v, i, a) => a.indexOf(v) === i);

    let lastErr = "";
    for (const apiBase of bases) {
      try {
        const res = await fetch(apiBase + "/api/crawl", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) return Object.assign({ ok: true, url, label }, data);
        lastErr = data.error || "HTTP " + res.status;
      } catch (e) {
        lastErr = e.message || String(e);
      }
    }
    const token =
      (typeof localStorage !== "undefined" && localStorage.getItem("regintel_gh_token")) || "";
    if (token) {
      const res = await fetch(
        "https://api.github.com/repos/tmai-tech/regintel/actions/workflows/crawl-ministry.yml/dispatches",
        {
          method: "POST",
          headers: {
            Accept: "application/vnd.github+json",
            Authorization: "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
          },
          body: JSON.stringify({ ref: "main", inputs: payload }),
        },
      );
      if (res.status === 204 || res.ok) return { ok: true, via: "github", url, label };
      lastErr = await res.text();
    }
    const err = new Error(lastErr || "no-backend");
    err.code = "no-backend";
    throw err;
  }

  function initHome(pdfs, ministries, evaSummaries) {
    const home = document.getElementById("viewHome");
    const detail = document.getElementById("viewDetail");
    const siteList = document.getElementById("siteList");
    const siteEmpty = document.getElementById("siteEmpty");
    const form = document.getElementById("crawlForm");
    const urlInput = document.getElementById("crawlUrl");
    const statusEl = document.getElementById("crawlStatus");
    const back = document.getElementById("detailBack");
    const detailName = document.getElementById("detailName");
    const detailMeta = document.getElementById("detailMeta");
    const progressList = document.getElementById("progressList");
    const progressTitle = document.getElementById("progressTitle");
    const progressHead = document.getElementById("progressHead");
    const progressRefresh = document.getElementById("progressRefresh");
    if (!siteList) return;

    const sites = collectSites(ministries, pdfs);
    let active = readLocalStarts().filter((j) => {
      return (
        j &&
        j.code &&
        (j.phase === "starting" || j.phase === "queued") &&
        ageMs(j.startedAt) < 10 * 60 * 1000
      );
    });

    function showHome() {
      if (home) home.hidden = false;
      if (detail) detail.hidden = true;
      try {
        history.replaceState(null, "", location.pathname + location.search);
      } catch (_) {
        /* ignore */
      }
    }

    function openSite(site) {
      if (home) home.hidden = true;
      if (detail) detail.hidden = false;
      if (detailName) detailName.textContent = site.code || site.name;
      if (detailMeta) {
        const withSum = (evaSummaries || []).filter(
          (e) => pdfMatchesSite(e, site) && String(e.summary || "").trim(),
        ).length;
        detailMeta.textContent =
          site.count +
          " PDFs · " +
          withSum +
          " summaries · " +
          (site.url || "");
      }
      initSummaries(pdfs, evaSummaries, site);
      try {
        history.replaceState(null, "", "#site=" + encodeURIComponent(site.code));
      } catch (_) {
        /* ignore */
      }
    }

    const extracted = sites.filter((s) => s.count > 0);
    siteList.innerHTML = extracted
      .map((s) => {
        return `<button type="button" class="site-card" role="listitem" data-code="${escapeAttr(s.code)}">
          <div>
            <div class="site-card-name">${escapeHtml(s.code)}</div>
            <div class="site-card-host">${escapeHtml(s.name || s.url || "")}</div>
          </div>
          <div class="site-card-count">
            <strong>${escapeHtml(String(s.count))}</strong>
            <span>PDFs</span>
          </div>
        </button>`;
      })
      .join("");
    if (siteEmpty) siteEmpty.hidden = extracted.length > 0;
    siteList.querySelectorAll(".site-card").forEach((btn) => {
      btn.addEventListener("click", () => {
        const code = btn.getAttribute("data-code");
        const site = sites.find((s) => s.code === code);
        if (site) openSite(site);
      });
    });

    function renderProgress() {
      if (!progressList) return;
      const jobs = active.filter((j) => j && j.code);
      if (progressHead) progressHead.hidden = jobs.length === 0;
      if (progressTitle) progressTitle.hidden = jobs.length === 0;
      progressList.innerHTML = jobs
        .map((j) => {
          const phase = j.phase || "starting";
          const checked = j.checkedAt
            ? "Updated " + new Date(j.checkedAt).toLocaleTimeString()
            : "Not checked yet";
          return `<article class="site-card site-card-live" role="listitem" data-live="${escapeAttr(j.code)}">
            <div class="live-top">
              <div>
                <div class="site-card-name">${escapeHtml(j.code)}</div>
                <div class="site-card-host">${escapeHtml(j.url || "")}</div>
              </div>
              <span class="live-pill${phase === "stopped" ? " stopped" : ""}">${escapeHtml(phase)}</span>
            </div>
            <div class="live-stats">
              <div class="live-stat"><strong>${escapeHtml(String(j.pages ?? 0))}</strong><span>Pages</span></div>
              <div class="live-stat"><strong>${escapeHtml(String(j.listed ?? 0))}</strong><span>PDFs found</span></div>
              <div class="live-stat"><strong>${escapeHtml(String(j.downloaded ?? 0))}</strong><span>Downloaded</span></div>
            </div>
            <p class="live-action">${escapeHtml(j.message || "Waiting for crawl worker…")}</p>
            <div class="live-foot">
              <span class="live-checked">${escapeHtml(checked)}</span>
              <button type="button" class="btn ghost live-dismiss" data-code="${escapeAttr(j.code)}">Dismiss</button>
            </div>
          </article>`;
        })
        .join("");
      progressList.querySelectorAll(".live-dismiss").forEach((btn) => {
        btn.addEventListener("click", () => {
          const code = btn.getAttribute("data-code");
          active = active.filter((j) => j.code !== code);
          writeLocalStarts(active.filter((j) => j.phase === "starting" || j.phase === "queued"));
          renderProgress();
        });
      });
    }

    function jobFromStatus(st) {
      if (!st) return null;
      const cur = st.current_source || {};
      const prog = st.ministry_document_list || {};
      const counts = prog.counts || {};
      const url = cur.url || prog.target_url || "";
      const label = cur.jurisdiction || prog.label || "";
      const code = siteCodeFromUrl(url || label);
      if (!code) return null;
      const listed = cur.listed != null ? cur.listed : counts.listed_total || 0;
      const downloaded =
        Number(cur.downloaded || counts.downloaded || 0) +
        Number(cur.scanned_pdf || counts.scanned_pdf || 0);
      const toDownload = cur.to_download != null ? cur.to_download : counts.to_download;
      const pages =
        cur.pages_visited != null
          ? cur.pages_visited
          : prog.pages_visited != null
            ? prog.pages_visited
            : 0;
      const phase = st.phase || prog.phase || "";
      const finished = crawlLooksFinished(phase, listed, downloaded, toDownload, st.message);
      return {
        code,
        url,
        label,
        phase: finished ? "stopped" : phase || "running",
        message: st.message || phase || "",
        pages,
        listed,
        downloaded,
        to_download: toDownload,
        updated_at: st.updated_at,
        checkedAt: st.updated_at,
      };
    }

    function normalizeSharedJob(j, nowIso) {
      const listed = Number(j.listed || 0);
      const downloaded = Number(j.downloaded || 0);
      const toDownload = j.to_download;
      const phase = j.phase || "";
      const updated = j.updated_at || j.checkedAt || "";
      // Long crawls often go 30–90+ min between status writes. Do not treat
      // a quiet file as finished — that emptied the board while jobs ran.
      const finished = crawlLooksFinished(phase, listed, downloaded, toDownload, j.message);
      let message = j.message || phase + "…";
      if (!finished && updated && ageMs(updated) > 15 * 60 * 1000) {
        message = (message ? message + " · " : "") + "Last publish " + new Date(updated).toLocaleTimeString();
      }
      return {
        code: j.code,
        url: j.url || "",
        label: j.label || j.code,
        phase: finished ? "stopped" : phase || "running",
        message: finished
          ? listed || downloaded
            ? "Crawl finished · " + listed + " PDFs found, " + downloaded + " downloaded."
            : j.message || "Crawl stopped."
          : message,
        pages: j.pages || 0,
        listed,
        downloaded,
        startedAt: j.startedAt || updated,
        checkedAt: nowIso,
        updated_at: updated,
      };
    }

    async function refreshLiveStatus(fromClick) {
      const nowIso = new Date().toISOString();
      if (fromClick && statusEl) statusEl.textContent = "Refreshing crawl status…";
      try {
        const [shared, st] = await Promise.all([
          fetchJson("data/active_crawls.json").catch(() => null),
          fetchJson("data/crawl_status.json").catch(() => null),
        ]);

        const byCode = new Map();
        const serverJobs = (shared && Array.isArray(shared.jobs) && shared.jobs) || [];
        for (const row of serverJobs) {
          if (!row || !row.code) continue;
          byCode.set(row.code, normalizeSharedJob(row, nowIso));
        }
        const fallback = jobFromStatus(st);
        if (fallback && fallback.code) {
          const existing = byCode.get(fallback.code);
          const newer =
            !existing ||
            Date.parse(fallback.updated_at || 0) >= Date.parse(existing.updated_at || 0);
          const richer =
            existing &&
            (Number(fallback.listed || 0) > Number(existing.listed || 0) ||
              Number(fallback.pages || 0) > Number(existing.pages || 0));
          if (!existing || newer || richer) {
            byCode.set(
              fallback.code,
              normalizeSharedJob(Object.assign({}, existing || {}, fallback), nowIso),
            );
          }
        }

        const locals = readLocalStarts().filter((j) => {
          return (
            j &&
            j.code &&
            (j.phase === "starting" || j.phase === "queued") &&
            ageMs(j.startedAt) < 10 * 60 * 1000
          );
        });
        for (const j of locals) {
          if (!byCode.has(j.code)) {
            byCode.set(j.code, Object.assign({}, j, { checkedAt: nowIso }));
          }
        }

        active = [...byCode.values()].filter((j) => {
          const stamp = j.updated_at || j.startedAt || j.checkedAt;
          if (isLivePhase(j.phase)) return ageMs(stamp) < 4 * 3600 * 1000;
          if (j.phase === "stopped") return ageMs(stamp) < 30 * 60 * 1000;
          return false;
        });
        active.sort((a, b) => {
          const la = isLivePhase(a.phase) ? 0 : 1;
          const lb = isLivePhase(b.phase) ? 0 : 1;
          return la - lb || String(a.code).localeCompare(String(b.code));
        });
        writeLocalStarts(
          locals.filter((j) => {
            const srv = byCode.get(j.code);
            return !srv || srv.phase === "starting" || srv.phase === "queued";
          }),
        );
        renderProgress();
        if (fromClick && statusEl) {
          const liveN = active.filter((j) => isLivePhase(j.phase)).length;
          statusEl.textContent =
            liveN > 0
              ? liveN + " crawl" + (liveN === 1 ? "" : "s") + " in progress. Same status on every device."
              : "No crawl in progress. Cards updated " +
                new Date(nowIso).toLocaleTimeString() +
                ".";
        }
      } catch (_) {
        active = active.map((j) => Object.assign(j, { checkedAt: nowIso }));
        renderProgress();
        if (fromClick && statusEl) statusEl.textContent = "Refresh failed — try again.";
      }
    }

    if (back) back.addEventListener("click", showHome);

    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const raw = (urlInput && urlInput.value ? urlInput.value : "").trim();
        if (!raw) return;
        const url = raw.startsWith("http") ? raw : "https://" + raw;
        const code = siteCodeFromUrl(url);
        const job = {
          code,
          url,
          label: crawlLabelFromUrl(url),
          startedAt: new Date().toISOString(),
          phase: "starting",
          message: "Starting deep crawl on this site…",
          pages: 0,
          listed: 0,
          downloaded: 0,
        };
        active = [job, ...active.filter((j) => j.code !== code)];
        writeLocalStarts(active.filter((j) => j.phase === "starting" || j.phase === "queued"));
        renderProgress();
        if (statusEl) statusEl.textContent = "Crawl in progress for " + code + " — stay on this page.";
        try {
          await dispatchMinistryCrawl(url);
          job.message = "Worker accepted the job. Discovering pages and PDFs…";
          writeLocalStarts(active.filter((j) => j.phase === "starting" || j.phase === "queued"));
          renderProgress();
        } catch (err) {
          job.phase = "queued";
          job.message =
            "Watching live status on this page. A crawl worker will pick this up when connected.";
          writeLocalStarts(active.filter((j) => j.phase === "starting" || j.phase === "queued"));
          renderProgress();
          if (statusEl) {
            statusEl.textContent =
              "Tracking " + code + " here. Click Refresh status to check the worker.";
          }
        }
        refreshLiveStatus();
      });
    }

    if (progressRefresh) {
      progressRefresh.addEventListener("click", () => refreshLiveStatus(true));
    }
    renderProgress();
    refreshLiveStatus(false);

    const hash = (location.hash || "").replace(/^#/, "");
    const m = /^site=(.+)$/i.exec(hash);
    if (m) {
      const site = sites.find((s) => s.code.toLowerCase() === decodeURIComponent(m[1]).toLowerCase());
      if (site) openSite(site);
    }
  }

  async function load() {
    let pdfs = [];
    let ministries = [];
    let evaSummaries = [];
    let evaMeta = null;
    const statusEl = document.getElementById("crawlStatus");
    try {
      const [pdfsRes, minRes, evaRes, evaMetaRes] = await Promise.all([
        fetchJson("data/pdfs_catalog.json"),
        fetchJson("data/saudi_ministries.json").catch(() => []),
        fetchJson("data/eva_summaries.json").catch(() => []),
        fetchJson("data/eva_meta.json").catch(() => null),
      ]);
      if (!Array.isArray(pdfsRes)) throw new Error("PDF catalog is not a list");
      pdfs = pdfsRes.filter((p) => isAllowedSaudiMinistryRow(p));
      ministries = Array.isArray(minRes) && minRes.length ? minRes : defaultMinistries();
      evaSummaries = (Array.isArray(evaRes) ? evaRes : []).filter((e) =>
        isAllowedSaudiMinistryRow(e),
      );
      evaMeta = evaMetaRes;
    } catch (e) {
      if (statusEl) statusEl.textContent = "Failed to load catalog: " + (e.message || e);
      const host = document.getElementById("siteList");
      if (host) {
        host.innerHTML =
          '<div class="error-state">Failed to load data.<br/>' +
          escapeHtml(e.message || String(e)) +
          "</div>";
      }
      return;
    }

    initHome(pdfs, ministries, evaSummaries);
    initEva(evaSummaries, evaMeta, pdfs.length);
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
