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
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
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
    var pdfs by remember { mutableStateOf<List<PdfDoc>>(emptyList()) }
    var query by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf("All") }
    var selected by remember { mutableStateOf<PdfDoc?>(null) }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                pdfs = repo.loadPdfs()
            }.onFailure {
                error = it.message ?: "Failed to load PDFs"
            }
            loading = false
        }
    }

    LaunchedEffect(Unit) { reload() }

    if (selected != null) {
        PdfViewerScreen(
            doc = selected!!,
            repo = repo,
            onBack = { selected = null },
        )
        return
    }

    val jurisdictions = remember(pdfs) {
        listOf("All") + pdfs.mapNotNull { it.jurisdiction }.distinct().sorted()
    }

    val filtered = remember(pdfs, query, filter) {
        val q = query.trim().lowercase()
        pdfs.filter { row ->
            (filter == "All" || row.jurisdiction == filter) &&
                (q.isEmpty() || listOf(
                    row.title,
                    row.filename,
                    row.jurisdiction,
                    row.sourceKind,
                    row.sourcePage,
                    row.pdfUrl,
                ).joinToString(" ").lowercase().contains(q))
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("RegIntel PDFs", fontWeight = FontWeight.Bold)
                        Text(
                            "${pdfs.size} bills & amendments",
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
                Row(
                    modifier = Modifier
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    jurisdictions.take(50).forEach { opt ->
                        FilterChip(
                            selected = filter == opt,
                            onClick = { filter = opt },
                            label = { Text(opt) },
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))
            }

            Text(
                text = "${filtered.size} PDFs",
                style = MaterialTheme.typography.labelMedium,
                color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
            )

            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(error ?: "Error", color = MaterialTheme.colorScheme.error)
                }
                filtered.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("No PDFs found")
                }
                else -> LazyColumn(
                    contentPadding = PaddingValues(12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(filtered, key = { it.id }) { doc ->
                        PdfListItem(doc = doc, onOpen = { selected = doc })
                    }
                }
            }
        }
    }
}

@Composable
private fun PdfListItem(doc: PdfDoc, onOpen: () -> Unit) {
    val sizeLabel = if (doc.bytes > 0) "${doc.bytes / 1024} KB" else null
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
                    text = doc.title ?: doc.filename ?: "PDF",
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
                Text(
                    text = doc.sourcePage ?: "—",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary,
                    maxLines = 3,
                    overflow = TextOverflow.Ellipsis,
                )
                if (!doc.pdfUrl.isNullOrBlank() && doc.pdfUrl != doc.sourcePage) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        text = "PDF link",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.55f),
                    )
                    Text(
                        text = doc.pdfUrl ?: "",
                        style = MaterialTheme.typography.bodySmall,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.85f),
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
