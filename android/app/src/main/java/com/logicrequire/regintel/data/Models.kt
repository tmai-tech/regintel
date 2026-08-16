package com.logicrequire.regintel.data

/**
 * A bill/amendment PDF discovered by the gazette collector.
 * [sourcePage] = page URL it was extracted from
 * [pdfUrl] = direct PDF link used to open/download
 */
data class PdfDoc(
    val id: String = "",
    val title: String? = null,
    val filename: String? = null,
    val jurisdiction: String? = null,
    val sourceKind: String? = null,
    val sourcePage: String? = null,
    val pdfUrl: String? = null,
    val bytes: Long = 0,
    val downloadedAt: String? = null,
) {
    /** Anchor text is often "click here" / "embedded-url" — prefer a real file name. */
    fun displayTitle(): String {
        val raw = title?.trim().orEmpty()
        if (raw.isNotEmpty() && !isPlaceholderTitle(raw)) return raw
        prettyFileStem(filename)?.let { return it }
        prettyFileStem(pdfUrl?.substringBefore('?')?.substringAfterLast('/'))?.let { return it }
        return filename?.takeIf { it.isNotBlank() } ?: "PDF"
    }
}

private val PLACEHOLDER_TITLE = Regex(
    """^(embedded[\s_-]?url|clicke?\s*here(?:\s+to\b.*)?|show|here|link|download|view|تنزيل|هنا|اضغط\s*هنا.*)$""",
    RegexOption.IGNORE_CASE,
)
private val UUID_PREFIX = Regex(
    """^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}[_-]*""",
    RegexOption.IGNORE_CASE,
)
private val DISCOVERY_METHODS = setOf(
    "embedded-url", "href", "script", "sitemap", "seed_list",
    "playwright_net", "nav_api", "json_api", "embed", "direct",
)

private fun isPlaceholderTitle(title: String): Boolean {
    val t = title.replace(Regex("""[\s\u200b\u200c\u200d\ufeff]+"""), " ").trim()
    if (t.length < 3) return true
    if (t.lowercase() in DISCOVERY_METHODS) return true
    if (t.startsWith("http://", true) || t.startsWith("https://", true)) return true
    return PLACEHOLDER_TITLE.matches(t)
}

private fun prettyFileStem(name: String?): String? {
    var raw = name?.trim().orEmpty()
    if (raw.isEmpty()) return null
    raw = raw.substringBefore('?').substringAfterLast('/')
    try {
        raw = java.net.URLDecoder.decode(raw, "UTF-8")
    } catch (_: Exception) {
        /* keep raw */
    }
    raw = raw.replace(Regex("""(?i)\.pdf$"""), "")
    raw = UUID_PREFIX.replace(raw, "")
    raw = raw.replace('_', ' ').replace('-', ' ')
    raw = raw.replace(Regex("""\s+"""), " ").trim(' ', '.', '_', '-')
    if (raw.isEmpty() || isPlaceholderTitle(raw)) return null
    return raw
}

/**
 * Normalized law / regulatory update for browse & filter UI.
 * Built from collector updates + tracking log (+ primary source authority match).
 */
data class LawDoc(
    val id: String = "",
    /** Display name of the law / update */
    val name: String = "",
    /** Short summary / description */
    val summary: String = "",
    val country: String = "",
    /** "Federal" or "State" */
    val level: String = "",
    /** State/province name when level is State */
    val levelDetail: String = "",
    val lawArea: String = "",
    val topic: String = "",
    /** Clickable link to the law / update */
    val link: String = "",
    val authority: String = "",
    /** Clickable link to the authority's page */
    val authorityUrl: String = "",
    val source: String = "",
    val date: String = "",
)
