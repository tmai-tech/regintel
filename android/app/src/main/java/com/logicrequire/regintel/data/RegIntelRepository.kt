package com.logicrequire.regintel.data

import android.content.Context
import com.google.firebase.firestore.FirebaseFirestore
import com.google.gson.Gson
import com.google.gson.JsonArray
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

class RegIntelRepository(
    private val context: Context,
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
) {
    private val gson = Gson()

    suspend fun loadPdfs(limit: Long = 2000): List<PdfDoc> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_PDFS).limit(limit).get().await().documents.mapNotNull { d ->
                val pdfUrl = d.getString("open_url")
                    ?: d.getString("download_url")
                    ?: d.getString("url")
                PdfDoc(
                    id = d.id,
                    title = d.getString("title"),
                    filename = d.getString("filename"),
                    jurisdiction = d.getString("jurisdiction"),
                    sourceKind = d.getString("source_kind"),
                    sourcePage = d.getString("source_page"),
                    pdfUrl = pdfUrl,
                    bytes = d.getLong("bytes") ?: 0L,
                    downloadedAt = d.getString("downloaded_at"),
                )
            }
        }.getOrDefault(emptyList())

        val list = if (remote.isNotEmpty()) remote else loadPdfsFromAssets()
        list.sortedWith(
            compareByDescending<PdfDoc> { it.downloadedAt ?: "" }
                .thenBy { it.jurisdiction ?: "" }
                .thenBy { it.title ?: "" },
        )
    }

    /**
     * Download PDF bytes to app cache; return local file for in-app viewer.
     */
    suspend fun cachePdf(doc: PdfDoc): File = withContext(Dispatchers.IO) {
        val url = doc.pdfUrl?.trim().orEmpty()
        require(url.startsWith("http")) { "No PDF URL for this document" }

        val cacheDir = File(context.cacheDir, "pdfs").apply { mkdirs() }
        val name = (doc.shaName() + ".pdf")
        val out = File(cacheDir, name)
        if (out.exists() && out.length() > 100 && isPdfFile(out)) {
            return@withContext out
        }

        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 25_000
            readTimeout = 60_000
            instanceFollowRedirects = true
            setRequestProperty(
                "User-Agent",
                "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 Chrome/122.0.0.0 Mobile Safari/537.36 RegIntel/1.0",
            )
            setRequestProperty("Accept", "application/pdf,*/*")
            doc.sourcePage?.let { setRequestProperty("Referer", it) }
        }
        try {
            val code = conn.responseCode
            if (code >= 400) error("HTTP $code downloading PDF")
            conn.inputStream.use { input ->
                out.outputStream().use { output -> input.copyTo(output) }
            }
            if (!isPdfFile(out)) {
                out.delete()
                error("Downloaded file is not a PDF (site may block direct download)")
            }
            out
        } finally {
            conn.disconnect()
        }
    }

    private fun isPdfFile(file: File): Boolean {
        return try {
            file.inputStream().use { input ->
                val magic = ByteArray(4)
                val n = input.read(magic)
                n == 4 && magic.contentEquals("%PDF".toByteArray())
            }
        } catch (_: Exception) {
            false
        }
    }

    private fun PdfDoc.shaName(): String =
        id.ifBlank { (pdfUrl ?: title ?: "doc").hashCode().toUInt().toString(16) }

    private fun loadPdfsFromAssets(): List<PdfDoc> {
        val text = runCatching {
            context.assets.open("pdfs_catalog.json").bufferedReader().use { it.readText() }
        }.getOrNull() ?: return emptyList()
        val arr = gson.fromJson(text, JsonArray::class.java) ?: return emptyList()
        return arr.mapIndexed { i, el ->
            val o = el.asJsonObject
            fun s(k: String) = if (o.has(k) && !o.get(k).isJsonNull) o.get(k).asString else null
            fun n(k: String) = if (o.has(k) && !o.get(k).isJsonNull) o.get(k).asLong else 0L
            val open = s("open_url") ?: s("download_url") ?: s("url")
            PdfDoc(
                id = s("id") ?: "local-$i",
                title = s("title"),
                filename = s("filename"),
                jurisdiction = s("jurisdiction"),
                sourceKind = s("source_kind"),
                sourcePage = s("source_page"),
                pdfUrl = open,
                bytes = n("bytes"),
                downloadedAt = s("downloaded_at"),
            )
        }
    }

    companion object {
        const val COL_PDFS = "regintel_pdfs"
    }
}
