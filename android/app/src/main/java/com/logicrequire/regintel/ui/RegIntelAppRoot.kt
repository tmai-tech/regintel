package com.logicrequire.regintel.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Gavel
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.PictureAsPdf
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.logicrequire.regintel.data.LawDoc
import com.logicrequire.regintel.data.PdfDoc
import com.logicrequire.regintel.data.RegIntelRepository
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RegIntelAppRoot() {
    val context = LocalContext.current
    val repo = remember { RegIntelRepository(context) }
    val scope = rememberCoroutineScope()

    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var laws by remember { mutableStateOf<List<LawDoc>>(emptyList()) }
    var pdfs by remember { mutableStateOf<List<PdfDoc>>(emptyList()) }
    var tab by remember { mutableIntStateOf(0) }
    var selectedPdf by remember { mutableStateOf<PdfDoc?>(null) }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                laws = repo.loadLaws()
                pdfs = repo.loadPdfs()
            }.onFailure {
                error = it.message ?: "Failed to load data"
            }
            loading = false
        }
    }

    LaunchedEffect(Unit) { reload() }

    selectedPdf?.let { doc ->
        PdfViewerScreen(
            doc = doc,
            repo = repo,
            onBack = { selectedPdf = null },
        )
        return
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("RegIntel", fontWeight = FontWeight.Bold)
                        Text(
                            "${laws.size} laws · ${pdfs.size} PDFs",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { reload() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            TabRow(selectedTabIndex = tab) {
                Tab(
                    selected = tab == 0,
                    onClick = { tab = 0 },
                    text = { Text("Laws") },
                    icon = { Icon(Icons.Default.Gavel, contentDescription = null) },
                )
                Tab(
                    selected = tab == 1,
                    onClick = { tab = 1 },
                    text = { Text("PDFs") },
                    icon = { Icon(Icons.Default.PictureAsPdf, contentDescription = null) },
                )
            }

            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(error ?: "Error", color = MaterialTheme.colorScheme.error)
                }
                tab == 0 -> LawsTab(laws = laws)
                else -> PdfsTab(
                    pdfs = pdfs,
                    onOpenPdf = { doc ->
                        if (doc.pdfUrl.isNullOrBlank()) {
                            error = "This item has no PDF URL"
                        } else {
                            selectedPdf = doc
                        }
                    },
                )
            }
        }
    }
}

@Composable
private fun LawsTab(laws: List<LawDoc>) {
    var query by remember { mutableStateOf("") }
    var countryFilter by remember { mutableStateOf("All") }
    var levelFilter by remember { mutableStateOf("All") }
    var typeFilter by remember { mutableStateOf("All") }

    val countries = remember(laws) {
        listOf("All") + laws.map { it.country }.filter { it.isNotBlank() }.distinct().sorted()
    }
    val levels = listOf("All", "Federal", "State")
    val types = listOf("All", "Update", "Tracking", "Authority")

    fun typeLabel(source: String): String = when (source) {
        "collector" -> "Update"
        "tracking" -> "Tracking"
        "source" -> "Authority"
        else -> source.ifBlank { "Other" }
    }

    val filtered = remember(laws, query, countryFilter, levelFilter, typeFilter) {
        val q = query.trim().lowercase()
        laws.filter { row ->
            (countryFilter == "All" || row.country == countryFilter) &&
                (levelFilter == "All" || row.level == levelFilter) &&
                (typeFilter == "All" || typeLabel(row.source) == typeFilter) &&
                (
                    q.isEmpty() ||
                        listOf(
                            row.name,
                            row.summary,
                            row.country,
                            row.level,
                            row.levelDetail,
                            row.lawArea,
                            row.topic,
                            row.authority,
                            row.link,
                            row.authorityUrl,
                        ).joinToString(" ").lowercase().contains(q)
                    )
        }
    }

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            singleLine = true,
            label = { Text("Search by name of the law") },
            shape = RoundedCornerShape(12.dp),
        )

        ChipRow(
            options = levels,
            selected = levelFilter,
            onSelect = { levelFilter = it },
            labelPrefix = null,
        )
        ChipRow(
            options = types,
            selected = typeFilter,
            onSelect = { typeFilter = it },
            labelPrefix = null,
        )
        if (countries.size > 1) {
            ChipRow(
                options = countries.take(60),
                selected = countryFilter,
                onSelect = { countryFilter = it },
                labelPrefix = null,
            )
        }

        Text(
            text = "${filtered.size} laws",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )

        if (filtered.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No laws match your filters")
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(filtered, key = { it.id }) { law ->
                    LawListItem(law = law)
                }
            }
        }
    }
}

@Composable
private fun PdfsTab(pdfs: List<PdfDoc>, onOpenPdf: (PdfDoc) -> Unit) {
    var query by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf("All") }

    val jurisdictions = remember(pdfs) {
        listOf("All") + pdfs.mapNotNull { it.jurisdiction }.distinct().sorted()
    }

    val filtered = remember(pdfs, query, filter) {
        val q = query.trim().lowercase()
        pdfs.filter { row ->
            (filter == "All" || row.jurisdiction == filter) &&
                (
                    q.isEmpty() ||
                        listOf(
                            row.displayTitle(),
                            row.title,
                            row.filename,
                            row.jurisdiction,
                            row.sourceKind,
                            row.sourcePage,
                            row.pdfUrl,
                        ).joinToString(" ").lowercase().contains(q)
                    )
        }
    }

    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(
            value = query,
            onValueChange = { query = it },
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 12.dp, vertical = 8.dp),
            leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
            singleLine = true,
            label = { Text("Search title, jurisdiction, source link") },
            shape = RoundedCornerShape(12.dp),
        )

        if (jurisdictions.size > 1) {
            ChipRow(
                options = jurisdictions.take(50),
                selected = filter,
                onSelect = { filter = it },
                labelPrefix = null,
            )
            Spacer(Modifier.height(4.dp))
        }

        Text(
            text = "${filtered.size} PDFs",
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
            modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
        )

        if (filtered.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("No PDFs found")
            }
        } else {
            LazyColumn(
                contentPadding = PaddingValues(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(filtered, key = { it.id }) { doc ->
                    PdfListItem(doc = doc, onOpen = { onOpenPdf(doc) })
                }
            }
        }
    }
}

@Composable
private fun ChipRow(
    options: List<String>,
    selected: String,
    onSelect: (String) -> Unit,
    labelPrefix: String?,
) {
    Row(
        modifier = Modifier
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 2.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        options.forEach { opt ->
            val label = if (labelPrefix != null && opt != "All") "$labelPrefix: $opt" else opt
            FilterChip(
                selected = selected == opt,
                onClick = { onSelect(opt) },
                label = { Text(label) },
            )
        }
    }
}

@Composable
private fun LawListItem(law: LawDoc) {
    val uriHandler = LocalUriHandler.current
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Default.Gavel,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary,
                )
                Spacer(Modifier.width(10.dp))
                Text(
                    text = law.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f),
                )
            }
            Spacer(Modifier.height(6.dp))
            Text(
                text = listOfNotNull(
                    law.level.takeIf { it.isNotBlank() },
                    when (law.source) {
                        "collector" -> "Update"
                        "tracking" -> "Tracking"
                        "source" -> "Authority"
                        else -> null
                    },
                    law.country.takeIf { it.isNotBlank() },
                    law.levelDetail.takeIf { it.isNotBlank() && it != law.level },
                    law.lawArea.takeIf { it.isNotBlank() },
                ).joinToString(" · "),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Summary",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
            )
            Text(
                text = law.summary.ifBlank { "—" },
                style = MaterialTheme.typography.bodyMedium,
                maxLines = 4,
                overflow = TextOverflow.Ellipsis,
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Law link",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
            )
            ClickableUrlText(
                url = law.link,
                emptyLabel = "—",
                maxLines = 2,
                onOpenUrl = { uriHandler.openUri(it) },
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Authority",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
            )
            val authName = law.authority.ifBlank { "—" }
            if (law.authorityUrl.isNotBlank() && law.authority.isNotBlank()) {
                Text(
                    text = authName,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    color = MaterialTheme.colorScheme.primary,
                    textDecoration = TextDecoration.Underline,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.clickable { uriHandler.openUri(law.authorityUrl) },
                )
            } else {
                Text(
                    text = authName,
                    style = MaterialTheme.typography.bodyMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
            if (law.authorityUrl.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "Authority page",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                )
                ClickableUrlText(
                    url = law.authorityUrl,
                    emptyLabel = "—",
                    maxLines = 2,
                    onOpenUrl = { uriHandler.openUri(it) },
                )
            }
            if (law.link.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier.clickable { uriHandler.openUri(law.link) },
                ) {
                    Icon(
                        Icons.Default.OpenInNew,
                        contentDescription = null,
                        tint = MaterialTheme.colorScheme.secondary,
                        modifier = Modifier.height(16.dp),
                    )
                    Spacer(Modifier.width(4.dp))
                    Text(
                        text = "Open law link",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.secondary,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
        }
    }
}

@Composable
private fun PdfListItem(doc: PdfDoc, onOpen: () -> Unit) {
    val sizeLabel = if (doc.bytes > 0) "${doc.bytes / 1024} KB" else null
    val uriHandler = LocalUriHandler.current
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onOpen),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        shape = RoundedCornerShape(14.dp),
    ) {
        Row(
            modifier = Modifier.padding(14.dp),
            verticalAlignment = Alignment.Top,
        ) {
            Icon(
                Icons.Default.PictureAsPdf,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.primary,
            )
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    text = doc.displayTitle(),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = listOfNotNull(doc.jurisdiction, doc.sourceKind, sizeLabel)
                        .joinToString(" · "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Extracted from",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                )
                ClickableUrlText(
                    url = doc.sourcePage,
                    emptyLabel = "—",
                    maxLines = 3,
                    onOpenUrl = { uriHandler.openUri(it) },
                )
                if (!doc.pdfUrl.isNullOrBlank() && doc.pdfUrl != doc.sourcePage) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = "PDF link",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                    )
                    ClickableUrlText(
                        url = doc.pdfUrl,
                        emptyLabel = "",
                        maxLines = 2,
                        onOpenUrl = { uriHandler.openUri(it) },
                    )
                }
                Spacer(Modifier.height(6.dp))
                Text(
                    text = "Tap to read in app",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.secondary,
                    fontWeight = FontWeight.Medium,
                )
            }
        }
    }
}

/**
 * Renders a URL as a tappable link (opens in browser). Nested [clickable] consumes
 * the gesture so the parent card does not also fire.
 */
@Composable
private fun ClickableUrlText(
    url: String?,
    emptyLabel: String,
    maxLines: Int,
    onOpenUrl: (String) -> Unit,
) {
    val text = url?.takeIf { it.isNotBlank() }
    if (text == null) {
        Text(
            text = emptyLabel,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
            maxLines = maxLines,
            overflow = TextOverflow.Ellipsis,
        )
        return
    }
    val looksLikeUrl = text.startsWith("http://", ignoreCase = true) ||
        text.startsWith("https://", ignoreCase = true)
    Text(
        text = text,
        style = MaterialTheme.typography.bodySmall,
        color = MaterialTheme.colorScheme.primary,
        textDecoration = if (looksLikeUrl) TextDecoration.Underline else TextDecoration.None,
        maxLines = maxLines,
        overflow = TextOverflow.Ellipsis,
        modifier = if (looksLikeUrl) {
            Modifier.clickable { onOpenUrl(text) }
        } else {
            Modifier
        },
    )
}
