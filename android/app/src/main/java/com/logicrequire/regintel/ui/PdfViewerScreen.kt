package com.logicrequire.regintel.ui

import android.annotation.SuppressLint
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import android.util.Log
import android.view.ViewGroup
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.ArrowForward
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.logicrequire.regintel.data.PdfDoc
import com.logicrequire.regintel.data.RegIntelRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.net.URLEncoder
import kotlin.math.max
import kotlin.math.roundToInt

private const val TAG = "PdfViewer"

private enum class ViewMode { Loading, Web, Native, Error }

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PdfViewerScreen(
    doc: PdfDoc,
    repo: RegIntelRepository,
    onBack: () -> Unit,
) {
    val scope = rememberCoroutineScope()
    val context = LocalContext.current
    val density = LocalDensity.current

    var mode by remember { mutableStateOf(ViewMode.Loading) }
    var error by remember { mutableStateOf<String?>(null) }
    var localFile by remember { mutableStateOf<File?>(null) }
    var pageIndex by remember { mutableIntStateOf(0) }
    var pageCount by remember { mutableIntStateOf(0) }
    var pageBitmap by remember { mutableStateOf<Bitmap?>(null) }
    var status by remember { mutableStateOf("Opening…") }
    var useWebFirst by remember { mutableStateOf(true) }

    fun clearBitmap() {
        pageBitmap?.let { if (!it.isRecycled) it.recycle() }
        pageBitmap = null
    }

    fun loadNative(file: File, index: Int) {
        scope.launch {
            status = "Rendering page ${index + 1}…"
            val targetWidth = with(density) {
                // ~ screen width in px, capped
                (context.resources.displayMetrics.widthPixels).coerceIn(480, 1400)
            }
            val result = withContext(Dispatchers.IO) {
                renderSinglePage(file, index, targetWidth)
            }
            result.onSuccess { (bmp, count) ->
                clearBitmap()
                pageBitmap = bmp
                pageCount = count
                pageIndex = index.coerceIn(0, (count - 1).coerceAtLeast(0))
                mode = ViewMode.Native
                status = "Page ${pageIndex + 1} / $pageCount"
            }.onFailure { e ->
                Log.e(TAG, "Native render failed", e)
                error = e.message ?: "Could not render PDF"
                mode = ViewMode.Error
            }
        }
    }

    fun startNativeDownload() {
        mode = ViewMode.Loading
        error = null
        status = "Downloading PDF…"
        scope.launch {
            runCatching { repo.cachePdf(doc) }
                .onSuccess { file ->
                    localFile = file
                    loadNative(file, 0)
                }
                .onFailure { e ->
                    Log.e(TAG, "cachePdf failed", e)
                    error = e.message ?: "Download failed"
                    mode = ViewMode.Error
                }
        }
    }

    LaunchedEffect(doc.id) {
        // Prefer native download+render for reliability (works offline after cache).
        // WebView Google viewer is a fallback if native fails.
        useWebFirst = false
        startNativeDownload()
    }

    DisposableEffect(Unit) {
        onDispose { clearBitmap() }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text(
                            doc.title ?: doc.filename ?: "PDF",
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                        Text(
                            text = status,
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                        )
                    }
                },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = {
                        clearBitmap()
                        localFile = null
                        startNativeDownload()
                    }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Retry")
                    }
                },
            )
        },
    ) { padding ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .background(MaterialTheme.colorScheme.background),
        ) {
            when (mode) {
                ViewMode.Loading -> {
                    Column(
                        Modifier.fillMaxSize(),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        CircularProgressIndicator()
                        Spacer(Modifier.height(12.dp))
                        Text(status, style = MaterialTheme.typography.bodyMedium)
                        Spacer(Modifier.height(8.dp))
                        Text(
                            doc.pdfUrl ?: "",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f),
                            maxLines = 3,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.padding(horizontal = 24.dp),
                        )
                    }
                }

                ViewMode.Web -> {
                    val url = doc.pdfUrl
                    if (url.isNullOrBlank()) {
                        mode = ViewMode.Error
                        error = "No PDF URL"
                    } else {
                        PdfWebView(
                            pdfUrl = url,
                            onFatal = {
                                // fall back to native
                                startNativeDownload()
                            },
                        )
                    }
                }

                ViewMode.Native -> {
                    val uriHandler = LocalUriHandler.current
                    Column(Modifier.fillMaxSize()) {
                        // source link banner — tappable when a URL is present
                        val source = doc.sourcePage
                        val sourceIsUrl = !source.isNullOrBlank() &&
                            (source.startsWith("http://", ignoreCase = true) ||
                                source.startsWith("https://", ignoreCase = true))
                        Text(
                            text = "From: ${source ?: "—"}",
                            style = MaterialTheme.typography.labelSmall,
                            maxLines = 2,
                            overflow = TextOverflow.Ellipsis,
                            color = if (sourceIsUrl) {
                                MaterialTheme.colorScheme.primary
                            } else {
                                MaterialTheme.colorScheme.onSurface.copy(alpha = 0.65f)
                            },
                            textDecoration = if (sourceIsUrl) TextDecoration.Underline else TextDecoration.None,
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 6.dp)
                                .then(
                                    if (sourceIsUrl) {
                                        Modifier.clickable { uriHandler.openUri(source!!) }
                                    } else {
                                        Modifier
                                    },
                                ),
                        )
                        Box(
                            Modifier
                                .weight(1f)
                                .fillMaxWidth()
                                .verticalScroll(rememberScrollState()),
                            contentAlignment = Alignment.TopCenter,
                        ) {
                            val bmp = pageBitmap
                            if (bmp != null && !bmp.isRecycled) {
                                Image(
                                    bitmap = bmp.asImageBitmap(),
                                    contentDescription = "PDF page ${pageIndex + 1}",
                                    contentScale = ContentScale.FillWidth,
                                    modifier = Modifier
                                        .fillMaxWidth()
                                        .padding(8.dp),
                                )
                            } else {
                                CircularProgressIndicator(Modifier.padding(32.dp))
                            }
                        }
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .padding(8.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            IconButton(
                                enabled = pageIndex > 0 && localFile != null,
                                onClick = {
                                    val f = localFile ?: return@IconButton
                                    loadNative(f, pageIndex - 1)
                                },
                            ) {
                                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Previous page")
                            }
                            Text(
                                "${pageIndex + 1} / ${pageCount.coerceAtLeast(1)}",
                                style = MaterialTheme.typography.titleSmall,
                            )
                            IconButton(
                                enabled = pageIndex < pageCount - 1 && localFile != null,
                                onClick = {
                                    val f = localFile ?: return@IconButton
                                    loadNative(f, pageIndex + 1)
                                },
                            ) {
                                Icon(Icons.AutoMirrored.Filled.ArrowForward, contentDescription = "Next page")
                            }
                        }
                        Button(
                            onClick = {
                                // try Google Docs embedded viewer as alternate
                                mode = ViewMode.Web
                                status = "Web viewer"
                            },
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(horizontal = 12.dp, vertical = 4.dp),
                        ) {
                            Text("Try web viewer")
                        }
                    }
                }

                ViewMode.Error -> {
                    val uriHandler = LocalUriHandler.current
                    Column(
                        Modifier
                            .fillMaxSize()
                            .padding(24.dp)
                            .verticalScroll(rememberScrollState()),
                        verticalArrangement = Arrangement.Center,
                        horizontalAlignment = Alignment.CenterHorizontally,
                    ) {
                        Text(
                            "Could not open this PDF",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.error,
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            error ?: "Unknown error",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Spacer(Modifier.height(12.dp))
                        Text(
                            "Extracted from:",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                        )
                        ExternalLinkText(
                            url = doc.sourcePage,
                            emptyLabel = "—",
                            onOpenUrl = { uriHandler.openUri(it) },
                        )
                        Spacer(Modifier.height(8.dp))
                        Text(
                            "PDF link:",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                        )
                        ExternalLinkText(
                            url = doc.pdfUrl,
                            emptyLabel = "—",
                            onOpenUrl = { uriHandler.openUri(it) },
                        )
                        Spacer(Modifier.height(16.dp))
                        Row {
                            Button(onClick = { startNativeDownload() }) { Text("Retry download") }
                            Spacer(Modifier.width(12.dp))
                            Button(onClick = {
                                mode = ViewMode.Web
                                status = "Web viewer"
                                error = null
                            }) { Text("Web viewer") }
                        }
                        Spacer(Modifier.height(12.dp))
                        Button(onClick = onBack) { Text("Back to list") }
                    }
                }
            }
        }
    }
}

@SuppressLint("SetJavaScriptEnabled")
@Composable
private fun PdfWebView(pdfUrl: String, onFatal: () -> Unit) {
    val encoded = remember(pdfUrl) {
        URLEncoder.encode(pdfUrl, "UTF-8")
    }
    // Google Docs viewer works for many public PDF URLs inside WebView
    val viewerUrl = "https://docs.google.com/gview?embedded=true&url=$encoded"

    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = { ctx ->
            WebView(ctx).apply {
                layoutParams = ViewGroup.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                )
                setBackgroundColor(Color.WHITE)
                settings.javaScriptEnabled = true
                settings.domStorageEnabled = true
                settings.builtInZoomControls = true
                settings.displayZoomControls = false
                settings.loadWithOverviewMode = true
                settings.useWideViewPort = true
                settings.mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                settings.cacheMode = WebSettings.LOAD_DEFAULT
                webChromeClient = WebChromeClient()
                webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(
                        view: WebView?,
                        request: WebResourceRequest?,
                    ): Boolean = false

                    override fun onReceivedError(
                        view: WebView?,
                        errorCode: Int,
                        description: String?,
                        failingUrl: String?,
                    ) {
                        Log.w(TAG, "WebView error $errorCode $description")
                    }
                }
                // Try direct PDF URL first (Chrome WebView often streams it), then gview
                loadUrl(pdfUrl)
            }
        },
        update = { webView ->
            // no-op
        },
    )
}

@Composable
private fun ExternalLinkText(
    url: String?,
    emptyLabel: String,
    onOpenUrl: (String) -> Unit,
) {
    val text = url?.takeIf { it.isNotBlank() }
    if (text == null) {
        Text(emptyLabel, style = MaterialTheme.typography.bodySmall)
        return
    }
    val looksLikeUrl = text.startsWith("http://", ignoreCase = true) ||
        text.startsWith("https://", ignoreCase = true)
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.primary,
        textDecoration = if (looksLikeUrl) TextDecoration.Underline else TextDecoration.None,
        modifier = if (looksLikeUrl) {
            Modifier.clickable { onOpenUrl(text) }
        } else {
            Modifier
        },
    )
}

/**
 * Render a single PDF page scaled to [targetWidthPx]. Uses RGB_565 to reduce memory.
 */
private fun renderSinglePage(
    file: File,
    pageIndex: Int,
    targetWidthPx: Int,
): Result<Pair<Bitmap, Int>> = runCatching {
    require(file.exists() && file.length() > 0) { "PDF file missing" }
    val pfd = ParcelFileDescriptor.open(file, ParcelFileDescriptor.MODE_READ_ONLY)
    try {
        val renderer = PdfRenderer(pfd)
        try {
            val count = renderer.pageCount
            require(count > 0) { "PDF has no pages" }
            val idx = pageIndex.coerceIn(0, count - 1)
            val page = renderer.openPage(idx)
            try {
                val scale = max(1f, targetWidthPx.toFloat() / page.width.toFloat())
                // Cap scale to avoid huge bitmaps (OOM)
                val capped = scale.coerceAtMost(2.0f)
                val w = max(1, (page.width * capped).roundToInt())
                val h = max(1, (page.height * capped).roundToInt())
                // Guard absolute pixel budget (~8MP)
                val pixels = w.toLong() * h.toLong()
                val (fw, fh) = if (pixels > 8_000_000L) {
                    val r = kotlin.math.sqrt(8_000_000.0 / pixels)
                    max(1, (w * r).roundToInt()) to max(1, (h * r).roundToInt())
                } else {
                    w to h
                }
                val bmp = Bitmap.createBitmap(fw, fh, Bitmap.Config.ARGB_8888)
                bmp.eraseColor(Color.WHITE)
                page.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                bmp to count
            } finally {
                page.close()
            }
        } finally {
            renderer.close()
        }
    } finally {
        pfd.close()
    }
}
