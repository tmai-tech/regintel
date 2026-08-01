package com.logicrequire.regintel.data

import android.content.Context
import android.util.Log
import com.google.firebase.firestore.FirebaseFirestore
import com.google.gson.Gson
import com.google.gson.JsonArray
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.io.BufferedInputStream
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLDecoder
import java.nio.charset.StandardCharsets

class RegIntelRepository(
    private val context: Context,
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
) {
    private val gson = Gson()

    suspend fun loadPdfs(limit: Long = 2000): List<PdfDoc> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_PDFS).limit(limit).get().await().documents.mapNotNull { d ->
                runCatching {
                    val pdfUrl = d.getString("open_url")
                        ?: d.getString("download_url")
                        ?: d.getString("url")
                    if (pdfUrl.isNullOrBlank()) return@runCatching null
                    val bytes = when (val v = d.get("bytes")) {
                        is Long -> v
                        is Int -> v.toLong()
                        is Double -> v.toLong()
                        is Number -> v.toLong()
                        else -> 0L
                    }
                    PdfDoc(
                        id = d.id,
                        title = d.getString("title"),
                        filename = d.getString("filename"),
                        jurisdiction = d.getString("jurisdiction"),
                        sourceKind = d.getString("source_kind"),
                        sourcePage = d.getString("source_page"),
                        pdfUrl = pdfUrl.trim(),
                        bytes = bytes,
                        downloadedAt = d.getString("downloaded_at"),
                    )
                }.getOrNull()
            }
        }.onFailure { Log.e(TAG, "Firestore load failed", it) }
            .getOrDefault(emptyList())

        val list = if (remote.isNotEmpty()) remote else loadPdfsFromAssets()
        list.sortedWith(
            compareByDescending<PdfDoc> { it.downloadedAt ?: "" }
                .thenBy { it.jurisdiction ?: "" }
                .thenBy { it.title ?: "" },
        )
    }

    /**
     * Download PDF to cache. Throws with a user-readable message on failure.
     */
    suspend fun cachePdf(doc: PdfDoc): File = withContext(Dispatchers.IO) {
        val raw = doc.pdfUrl?.trim().orEmpty()
        require(raw.startsWith("http://") || raw.startsWith("https://")) {
            "No valid PDF URL for this document"
        }
        val url = sanitizeUrl(raw)

        val cacheDir = File(context.cacheDir, "pdfs").apply { mkdirs() }
        val out = File(cacheDir, safeCacheName(doc) + ".pdf")
        if (out.exists() && out.length() > 128 && isPdfFile(out)) {
            return@withContext out
        }
        if (out.exists()) out.delete()

        var lastError: Exception? = null
        // try original, then without query junk, then with encoded spaces
        val candidates = linkedSetOf(
            url,
            url.replace(" ", "%20"),
            URLDecoder.decode(url, StandardCharsets.UTF_8.name()).replace(" ", "%20"),
        )
        for (candidate in candidates) {
            try {
                downloadToFile(candidate, out, referer = doc.sourcePage)
                if (isPdfFile(out)) return@withContext out
                out.delete()
                lastError = IllegalStateException("Response was not a PDF")
            } catch (e: Exception) {
                lastError = e
                Log.w(TAG, "Download failed for $candidate: ${e.message}")
                if (out.exists()) out.delete()
            }
        }
        throw lastError ?: IllegalStateException("Could not download PDF")
    }

    private fun downloadToFile(urlStr: String, out: File, referer: String?) {
        var current = urlStr
        var redirects = 0
        while (redirects < 8) {
            val conn = (URL(current).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = 30_000
                readTimeout = 90_000
                requestMethod = "GET"
                setRequestProperty(
                    "User-Agent",
                    "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
                )
                setRequestProperty("Accept", "application/pdf,application/octet-stream,*/*;q=0.8")
                setRequestProperty("Accept-Language", "en-US,en;q=0.9")
                if (!referer.isNullOrBlank()) {
                    setRequestProperty("Referer", referer)
                }
            }
            try {
                val code = conn.responseCode
                when (code) {
                    in 200..299 -> {
                        val stream = conn.inputStream
                            ?: error("Empty response body (HTTP $code)")
                        BufferedInputStream(stream).use { input ->
                            FileOutputStream(out).use { output ->
                                input.copyTo(output)
                            }
                        }
                        return
                    }
                    HttpURLConnection.HTTP_MOVED_PERM,
                    HttpURLConnection.HTTP_MOVED_TEMP,
                    HttpURLConnection.HTTP_SEE_OTHER,
                    307, 308 -> {
                        val loc = conn.getHeaderField("Location")
                            ?: error("Redirect without Location (HTTP $code)")
                        current = if (loc.startsWith("http")) loc else URL(URL(current), loc).toString()
                        redirects++
                    }
                    else -> {
                        val errBody = runCatching {
                            conn.errorStream?.bufferedReader()?.readText()?.take(200)
                        }.getOrNull()
                        error("HTTP $code downloading PDF${errBody?.let { ": $it" } ?: ""}")
                    }
                }
            } finally {
                conn.disconnect()
            }
        }
        error("Too many redirects")
    }

    private fun sanitizeUrl(url: String): String {
        // strip whitespace / angle brackets sometimes scraped into links
        return url.trim().trim('<', '>', '"', '\'')
    }

    private fun isPdfFile(file: File): Boolean {
        return try {
            file.inputStream().use { input ->
                val magic = ByteArray(5)
                val n = input.read(magic)
                n >= 4 &&
                    magic[0] == '%'.code.toByte() &&
                    magic[1] == 'P'.code.toByte() &&
                    magic[2] == 'D'.code.toByte() &&
                    magic[3] == 'F'.code.toByte()
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun safeCacheName(doc: PdfDoc): String {
        val base = doc.id.ifBlank { doc.pdfUrl ?: doc.title ?: "doc" }
        return base.replace(Regex("[^A-Za-z0-9._-]"), "_").take(80)
    }

    private fun loadPdfsFromAssets(): List<PdfDoc> {
        val text = runCatching {
            context.assets.open("pdfs_catalog.json").bufferedReader().use { it.readText() }
        }.getOrNull() ?: return emptyList()
        val arr = gson.fromJson(text, JsonArray::class.java) ?: return emptyList()
        return arr.mapIndexedNotNull { i, el ->
            runCatching {
                val o = el.asJsonObject
                fun s(k: String) = if (o.has(k) && !o.get(k).isJsonNull) o.get(k).asString else null
                fun n(k: String): Long = try {
                    if (o.has(k) && !o.get(k).isJsonNull) o.get(k).asLong else 0L
                } catch (_: Exception) {
                    0L
                }
                val open = s("open_url") ?: s("download_url") ?: s("url")
                if (open.isNullOrBlank()) return@runCatching null
                PdfDoc(
                    id = s("id") ?: "local-$i",
                    title = s("title"),
                    filename = s("filename"),
                    jurisdiction = s("jurisdiction"),
                    sourceKind = s("source_kind"),
                    sourcePage = s("source_page"),
                    pdfUrl = open.trim(),
                    bytes = n("bytes"),
                    downloadedAt = s("downloaded_at"),
                )
            }.getOrNull()
        }
    }

    /**
     * Load laws: Firestore `regintel_laws` → bundled `laws_catalog.json` →
     * legacy merge of updates/tracking/primary assets.
     */
    suspend fun loadLaws(limit: Long = 5000): List<LawDoc> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_LAWS).limit(limit).get().await().documents.mapNotNull { d ->
                runCatching { lawFromMap(d.id, d.data) }.getOrNull()
            }
        }.onFailure { Log.e(TAG, "Firestore laws load failed", it) }
            .getOrDefault(emptyList())

        val list = when {
            remote.isNotEmpty() -> remote
            else -> {
                val fromCatalog = loadLawsFromCatalogAsset()
                if (fromCatalog.isNotEmpty()) fromCatalog else loadLawsLegacyFromAssets()
            }
        }
        list.sortedWith(
            compareBy<LawDoc> {
                when (it.source) {
                    "collector" -> 0
                    "tracking" -> 1
                    else -> 2
                }
            }.thenByDescending { it.date }
                .thenBy { it.country }
                .thenBy { it.name },
        )
    }

    private fun lawFromMap(id: String, data: Map<String, Any?>?): LawDoc? {
        if (data == null) return null
        fun s(key: String): String {
            val v = data[key] ?: return ""
            return when (v) {
                is String -> v
                is Number -> v.toString()
                else -> v.toString()
            }.trim()
        }
        val name = s("name").ifBlank { s("title") }.ifBlank { return null }
        val link = s("link")
        return LawDoc(
            id = id.ifBlank { s("id") }.ifBlank { "law-${name.hashCode()}" },
            name = name,
            summary = s("summary"),
            country = s("country"),
            level = s("level").ifBlank { "Federal" },
            levelDetail = s("level_detail").ifBlank { s("levelDetail") }.ifBlank { s("level") },
            lawArea = s("law_area").ifBlank { s("lawArea") },
            topic = s("topic").ifBlank { s("topical_relevance") },
            link = link,
            authority = s("authority"),
            authorityUrl = s("authority_url").ifBlank { s("authorityUrl") }.ifBlank { s("source_url") },
            source = s("source").ifBlank { "catalog" },
            date = s("date").ifBlank { s("discovered_at") },
        )
    }

    private fun loadLawsFromCatalogAsset(): List<LawDoc> {
        val arr = loadJsonArray("laws_catalog.json")
        if (arr.size() == 0) return emptyList()
        return arr.mapIndexedNotNull { i, el ->
            runCatching {
                val o = el.asJsonObject
                val map = o.entrySet().associate { (k, v) ->
                    k to if (v.isJsonNull) null else {
                        when {
                            v.isJsonPrimitive && v.asJsonPrimitive.isString -> v.asString
                            v.isJsonPrimitive && v.asJsonPrimitive.isNumber -> v.asNumber
                            else -> v.toString()
                        }
                    }
                }
                lawFromMap(o.get("id")?.takeIf { !it.isJsonNull }?.asString ?: "local-$i", map)
            }.getOrNull()
        }
    }

    /** Fallback when laws_catalog.json is missing from the APK. */
    private fun loadLawsLegacyFromAssets(): List<LawDoc> {
        val updates = loadJsonArray("updates.json")
        val tracking = loadJsonArray("tracking.json")
        val sources = loadJsonArray("primary_sources.json")
        val authByHost = buildAuthorityIndex(sources)
        val seen = linkedSetOf<String>()
        val out = mutableListOf<LawDoc>()

        updates.forEachIndexed { i, el ->
            runCatching {
                val o = el.asJsonObject
                fun s(k: String) =
                    if (o.has(k) && !o.get(k).isJsonNull) o.get(k).asString else null
                val title = s("title")?.trim().orEmpty().ifBlank { "Untitled update" }
                val link = s("link")?.trim().orEmpty()
                val key = (link.ifBlank { title }).lowercase()
                if (!seen.add(key)) return@runCatching
                val parsed = parseJurisdiction(s("country"))
                val topic = s("topical_relevance")?.trim().orEmpty()
                val area = normalizeLawArea(s("law_area"))
                out += LawDoc(
                    id = s("id") ?: "upd-$i",
                    name = title,
                    summary = listOfNotNull(topic, area.takeIf { it.isNotBlank() }?.let { "Law area: $it" })
                        .joinToString(" · ").ifBlank { "Regulatory update." },
                    country = parsed.country,
                    level = parsed.level.ifBlank { "Federal" },
                    levelDetail = parsed.levelDetail,
                    lawArea = area,
                    topic = topic,
                    link = link,
                    authority = s("authority")?.trim().orEmpty(),
                    authorityUrl = s("source_url")?.trim().orEmpty(),
                    source = "collector",
                    date = s("discovered_at").orEmpty(),
                )
            }
        }

        tracking.forEachIndexed { i, el ->
            runCatching {
                val o = el.asJsonObject
                fun s(k: String) =
                    if (o.has(k) && !o.get(k).isJsonNull) o.get(k).asString else null
                val remarks = s("remarks")?.trim().orEmpty()
                val topic = s("topical_relevance")?.trim().orEmpty()
                val name = remarks.ifBlank { topic.ifBlank { "Tracked update" } }
                val link = s("link")?.trim().orEmpty()
                val key = (link.ifBlank { name }).lowercase()
                if (!seen.add(key)) return@runCatching
                val levelRaw = s("federal_or_state")?.trim().orEmpty()
                val level = if (levelRaw.isNotBlank() && !levelRaw.equals("Federal", true)) {
                    "State"
                } else {
                    "Federal"
                }
                val matched = matchAuthority(authByHost, link)
                out += LawDoc(
                    id = "trk-$i",
                    name = name,
                    summary = listOfNotNull(
                        remarks.takeIf { it.isNotBlank() && it != name },
                        topic.takeIf { it.isNotBlank() },
                        s("law_area")?.let { "Law area: $it" },
                    ).joinToString(" · ").ifBlank { "Tracked regulatory item." },
                    country = s("country")?.trim().orEmpty(),
                    level = level,
                    levelDetail = levelRaw.ifBlank { level },
                    lawArea = normalizeLawArea(s("law_area")),
                    topic = topic,
                    link = link,
                    authority = matched?.first.orEmpty(),
                    authorityUrl = matched?.second.orEmpty(),
                    source = "tracking",
                    date = s("date_of_publication") ?: s("date_of_tracking").orEmpty(),
                )
            }
        }

        sources.forEachIndexed { i, el ->
            runCatching {
                val o = el.asJsonObject
                fun s(k: String) =
                    if (o.has(k) && !o.get(k).isJsonNull) o.get(k).asString else null
                val name = s("authority")?.trim().orEmpty()
                val link = s("url")?.trim().orEmpty()
                if (name.isBlank() || link.isBlank()) return@runCatching
                val key = link.lowercase()
                if (!seen.add(key)) return@runCatching
                val parsed = parseJurisdiction(s("jurisdiction"))
                val topics = if (o.has("topics") && o.get("topics").isJsonArray) {
                    o.getAsJsonArray("topics").mapNotNull {
                        if (it.isJsonPrimitive) it.asString else null
                    }.joinToString(", ")
                } else {
                    ""
                }
                out += LawDoc(
                    id = "src-$i",
                    name = name,
                    summary = listOfNotNull(
                        s("authority_type")?.let { "$it authority" },
                        s("segment")?.let { "Law area: $it" },
                        topics.takeIf { it.isNotBlank() }?.let { "Topics: $it" },
                    ).joinToString(" · ").ifBlank { "Regulatory authority." },
                    country = parsed.country,
                    level = parsed.level,
                    levelDetail = parsed.levelDetail,
                    lawArea = normalizeLawArea(s("segment")),
                    topic = topics,
                    link = link,
                    authority = name,
                    authorityUrl = link,
                    source = "source",
                    date = "",
                )
            }
        }

        return out
    }

    private fun loadJsonArray(assetName: String): JsonArray {
        val text = runCatching {
            context.assets.open(assetName).bufferedReader().use { it.readText() }
        }.getOrNull() ?: return JsonArray()
        return gson.fromJson(text, JsonArray::class.java) ?: JsonArray()
    }

    private fun buildAuthorityIndex(sources: JsonArray): Map<String, Pair<String, String>> {
        val map = linkedMapOf<String, Pair<String, String>>()
        sources.forEach { el ->
            runCatching {
                val o = el.asJsonObject
                val name = o.get("authority")?.takeIf { !it.isJsonNull }?.asString?.trim().orEmpty()
                val url = o.get("url")?.takeIf { !it.isJsonNull }?.asString?.trim().orEmpty()
                val host = hostOf(url)
                if (name.isNotBlank() && host.isNotBlank() && !map.containsKey(host)) {
                    map[host] = name to url
                }
            }
        }
        return map
    }

    private fun matchAuthority(
        index: Map<String, Pair<String, String>>,
        link: String,
    ): Pair<String, String>? {
        val h = hostOf(link)
        if (h.isBlank()) return null
        index[h]?.let { return it }
        val parts = h.split('.')
        for (i in 1 until (parts.size - 1).coerceAtLeast(0)) {
            val parent = parts.drop(i).joinToString(".")
            index[parent]?.let { return it }
        }
        for ((key, value) in index) {
            if (h.endsWith(".$key") || key.endsWith(".$h")) return value
        }
        return null
    }

    private fun hostOf(url: String?): String {
        if (url.isNullOrBlank()) return ""
        return try {
            val u = java.net.URI(url.trim())
            (u.host ?: "").removePrefix("www.").lowercase()
        } catch (_: Exception) {
            ""
        }
    }

    private data class ParsedJurisdiction(
        val country: String,
        val level: String,
        val levelDetail: String,
    )

    private fun parseJurisdiction(raw: String?): ParsedJurisdiction {
        val s = raw?.trim().orEmpty()
        if (s.isEmpty()) return ParsedJurisdiction("", "", "")
        val fedMatch = Regex("^(.+?)\\s*[-–—]\\s*federal$", RegexOption.IGNORE_CASE).find(s)
        if (fedMatch != null) {
            return ParsedJurisdiction(fedMatch.groupValues[1].trim(), "Federal", "Federal")
        }
        if (Regex("\\bfederal\\b", RegexOption.IGNORE_CASE).containsMatchIn(s)) {
            val country = s.replace(Regex("\\s*[-–—]?\\s*federal\\b", RegexOption.IGNORE_CASE), "")
                .trim().ifBlank { s }
            return ParsedJurisdiction(country, "Federal", "Federal")
        }
        val lower = s.lowercase()
        if (lower in STATE_HINTS) {
            val country = when {
                lower in CA_PROVINCES -> "Canada"
                lower in AU_STATES -> "Australia"
                lower in UK_NATIONS -> "UK"
                else -> "US"
            }
            return ParsedJurisdiction(country, "State", s)
        }
        return ParsedJurisdiction(s, "Federal", "Federal")
    }

    private fun normalizeLawArea(raw: String?): String {
        if (raw.isNullOrBlank()) return ""
        return raw.replace('\n', ' ').replace(';', ',').replace(Regex("\\s+"), " ").trim()
    }

    companion object {
        const val COL_PDFS = "regintel_pdfs"
        const val COL_LAWS = "regintel_laws"
        private const val TAG = "RegIntelRepo"

        private val CA_PROVINCES = setOf(
            "ontario", "quebec", "british columbia", "alberta", "manitoba", "saskatchewan",
            "nova scotia", "new brunswick", "newfoundland", "prince edward island", "yukon",
            "northwest territories", "nunavut",
        )
        private val AU_STATES = setOf(
            "new south wales", "victoria", "queensland", "south australia", "western australia",
            "tasmania", "australian capital territory", "northern territory",
        )
        private val UK_NATIONS = setOf("england", "scotland", "wales", "northern ireland")
        private val STATE_HINTS = setOf(
            "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
            "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
            "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
            "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
            "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio",
            "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota",
            "tennessee", "texas", "utah", "vermont", "virginia", "washington", "west virginia",
            "wisconsin", "wyoming", "district of columbia", "dc",
        ) + CA_PROVINCES + AU_STATES + UK_NATIONS
    }
}
