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

    companion object {
        const val COL_PDFS = "regintel_pdfs"
        private const val TAG = "RegIntelRepo"
    }
}
