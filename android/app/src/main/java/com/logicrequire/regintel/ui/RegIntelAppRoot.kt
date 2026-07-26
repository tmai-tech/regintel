package com.logicrequire.regintel.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
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
import androidx.compose.material.icons.filled.OpenInNew
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.PictureAsPdf
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
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.logicrequire.regintel.data.CatalogMeta
import com.logicrequire.regintel.data.GazetteRow
import com.logicrequire.regintel.data.PrimarySource
import com.logicrequire.regintel.data.RegIntelRepository
import com.logicrequire.regintel.data.SecondarySource
import com.logicrequire.regintel.data.TrackingRow
import com.logicrequire.regintel.data.PdfDoc
import com.logicrequire.regintel.data.UpdateRow
import kotlinx.coroutines.launch

private enum class TabKind(val label: String) {
    Pdfs("PDFs"),
    Tracking("Tracking"),
    Primary("Primary"),
    Updates("Updates"),
    Gazette("Gazette"),
    Secondary("Secondary"),
}

@OptIn(ExperimentalMaterial3Api::class, ExperimentalLayoutApi::class)
@Composable
fun RegIntelAppRoot() {
    val context = LocalContext.current
    val repo = remember { RegIntelRepository(context) }
    val scope = rememberCoroutineScope()

    var tab by remember { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var meta by remember { mutableStateOf<CatalogMeta?>(null) }
    var tracking by remember { mutableStateOf<List<TrackingRow>>(emptyList()) }
    var primary by remember { mutableStateOf<List<PrimarySource>>(emptyList()) }
    var updates by remember { mutableStateOf<List<UpdateRow>>(emptyList()) }
    var gazette by remember { mutableStateOf<List<GazetteRow>>(emptyList()) }
    var secondary by remember { mutableStateOf<List<SecondarySource>>(emptyList()) }
    var pdfs by remember { mutableStateOf<List<PdfDoc>>(emptyList()) }
    var query by remember { mutableStateOf("") }
    var filter by remember { mutableStateOf("All") }

    fun reload() {
        scope.launch {
            loading = true
            error = null
            runCatching {
                meta = repo.loadMeta()
                tracking = repo.loadTracking()
                primary = repo.loadPrimary()
                updates = repo.loadUpdates()
                gazette = repo.loadGazette()
                secondary = repo.loadSecondary()
                pdfs = repo.loadPdfs()
            }.onFailure {
                error = it.message ?: "Load failed"
            }
            loading = false
        }
    }

    LaunchedEffect(Unit) { reload() }

    val tabs = TabKind.entries
    val current = tabs[tab]

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Column {
                        Text("RegIntel", fontWeight = FontWeight.Bold)
                        Text(
                            text = meta?.let {
                                "src=${it.source} · pdfs=${it.pdfCount.coerceAtLeast(pdfs.size)} · track=${it.trackingRecords} · updates=${it.updates}"
                            } ?: "BCI regulatory tracking",
                            style = MaterialTheme.typography.bodySmall,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis,
                        )
                    }
                },
                actions = {
                    IconButton(onClick = { reload() }) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.surface,
                ),
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding),
        ) {
            ScrollableTabRow(selectedTabIndex = tab, edgePadding = 12.dp) {
                tabs.forEachIndexed { i, t ->
                    Tab(
                        selected = tab == i,
                        onClick = {
                            tab = i
                            query = ""
                            filter = "All"
                        },
                        text = { Text(t.label) },
                    )
                }
            }

            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 12.dp, vertical = 8.dp),
                leadingIcon = { Icon(Icons.Default.Search, contentDescription = null) },
                singleLine = true,
                label = { Text("Search table") },
                shape = RoundedCornerShape(12.dp),
            )

            val filterOptions = when (current) {
                TabKind.Pdfs -> listOf("All") + pdfs.mapNotNull { it.jurisdiction }.distinct().sorted()
                TabKind.Tracking -> listOf("All") + tracking.mapNotNull { it.country }.distinct().sorted()
                TabKind.Primary -> listOf("All") + primary.mapNotNull { it.region }.distinct().sorted()
                TabKind.Updates -> listOf("All") + updates.mapNotNull { it.country }.distinct().sorted()
                TabKind.Gazette -> listOf("All")
                TabKind.Secondary -> listOf("All") + secondary.mapNotNull { it.coverageArea }.distinct().sorted()
            }

            if (filterOptions.size > 1) {
                Row(
                    modifier = Modifier
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 12.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    filterOptions.take(40).forEach { opt ->
                        FilterChip(
                            selected = filter == opt,
                            onClick = { filter = opt },
                            label = { Text(opt) },
                        )
                    }
                }
                Spacer(Modifier.height(4.dp))
            }

            when {
                loading -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator()
                }
                error != null -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text(error ?: "Error")
                }
                else -> {
                    val q = query.trim().lowercase()
                    when (current) {
                        TabKind.Pdfs -> {
                            val rows = pdfs.filter { row ->
                                (filter == "All" || row.jurisdiction == filter) &&
                                    (q.isEmpty() || listOf(
                                        row.title, row.filename, row.jurisdiction,
                                        row.sourceKind, row.openUrl, row.url,
                                    ).joinToString(" ").lowercase().contains(q))
                            }
                            CountBar(rows.size)
                            LazyColumn(
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                items(rows, key = { it.id }) { row ->
                                    val sizeKb = if (row.bytes > 0) "${row.bytes / 1024} KB" else null
                                    DetailCard(
                                        title = row.title ?: row.filename ?: "PDF",
                                        subtitle = listOfNotNull(row.jurisdiction, row.sourceKind, sizeKb)
                                            .joinToString(" · "),
                                        chips = listOfNotNull(row.filename, row.downloadedAt?.take(10)),
                                        body = buildString {
                                            if (!row.sourcePage.isNullOrBlank()) {
                                                appendLine("Source page: ${row.sourcePage}")
                                            }
                                            appendLine("File: ${row.filename ?: "—"}")
                                        },
                                        link = row.openUrl ?: row.url,
                                    )
                                }
                            }
                        }
                        TabKind.Tracking -> {
                            val rows = tracking.filter { row ->
                                (filter == "All" || row.country == filter) &&
                                    (q.isEmpty() || listOf(
                                        row.country, row.lawArea, row.topicalRelevance,
                                        row.remarks, row.relevancy, row.trackedBy, row.link,
                                    ).joinToString(" ").lowercase().contains(q))
                            }
                            CountBar(rows.size)
                            LazyColumn(
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                items(rows, key = { it.id }) { row ->
                                    DetailCard(
                                        title = row.remarks ?: row.topicalRelevance ?: "Update",
                                        subtitle = listOfNotNull(row.country, row.federalOrState, row.lawArea)
                                            .joinToString(" · "),
                                        chips = listOfNotNull(row.relevancy, row.trackedBy, row.alertStatus),
                                        body = buildString {
                                            appendLine("Topic: ${row.topicalRelevance ?: "—"}")
                                            appendLine("Tracked: ${row.dateOfTracking ?: "—"}")
                                            appendLine("Published: ${row.dateOfPublication ?: "—"}")
                                            if (!row.comments.isNullOrBlank()) appendLine("Comments: ${row.comments}")
                                            if (!row.corImpact.isNullOrBlank()) appendLine("COR impact: ${row.corImpact}")
                                        },
                                        link = row.link,
                                    )
                                }
                            }
                        }
                        TabKind.Primary -> {
                            val rows = primary.filter { row ->
                                (filter == "All" || row.region == filter) &&
                                    (q.isEmpty() || listOf(
                                        row.region, row.jurisdiction, row.authority,
                                        row.segment, row.url, row.topics.joinToString(),
                                    ).joinToString(" ").lowercase().contains(q))
                            }
                            CountBar(rows.size)
                            LazyColumn(
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                items(rows, key = { it.id }) { row ->
                                    DetailCard(
                                        title = row.authority ?: "Authority",
                                        subtitle = listOfNotNull(row.region, row.jurisdiction, row.segment)
                                            .joinToString(" · "),
                                        chips = listOfNotNull(row.status, row.frequency, row.linkNature),
                                        body = buildString {
                                            appendLine("Type: ${row.authorityType ?: "—"}")
                                            if (row.topics.isNotEmpty()) {
                                                appendLine("Topics: ${row.topics.joinToString(", ")}")
                                            }
                                        },
                                        link = row.url,
                                    )
                                }
                            }
                        }
                        TabKind.Updates -> {
                            val rows = updates.filter { row ->
                                (filter == "All" || row.country == filter) &&
                                    (q.isEmpty() || listOf(
                                        row.title, row.country, row.authority, row.lawArea, row.link,
                                    ).joinToString(" ").lowercase().contains(q))
                            }
                            CountBar(rows.size)
                            LazyColumn(
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                items(rows, key = { it.id }) { row ->
                                    DetailCard(
                                        title = row.title ?: "Collector update",
                                        subtitle = listOfNotNull(row.country, row.authority, row.discoveredAt)
                                            .joinToString(" · "),
                                        chips = listOfNotNull(row.relevancy, row.alertStatus, row.trackedBy),
                                        body = "Area: ${row.lawArea ?: "—"}\nTopics: ${row.topicalRelevance ?: "—"}",
                                        link = row.link,
                                    )
                                }
                            }
                        }
                        TabKind.Gazette -> {
                            val rows = gazette.filter { row ->
                                q.isEmpty() || listOf(
                                    row.jurisdiction, row.parliamentaryBills,
                                    row.officialGazette, row.legalDatabases,
                                ).joinToString(" ").lowercase().contains(q)
                            }
                            CountBar(rows.size)
                            LazyColumn(
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                items(rows, key = { it.id }) { row ->
                                    DetailCard(
                                        title = row.jurisdiction ?: "Jurisdiction",
                                        subtitle = "Gazette / bills / legal DB",
                                        chips = emptyList(),
                                        body = buildString {
                                            appendLine("Bills: ${row.parliamentaryBills ?: "—"}")
                                            appendLine("Gazette: ${row.officialGazette ?: "—"}")
                                            appendLine("Legal DB: ${row.legalDatabases ?: "—"}")
                                        },
                                        link = row.officialGazette ?: row.parliamentaryBills,
                                    )
                                }
                            }
                        }
                        TabKind.Secondary -> {
                            val rows = secondary.filter { row ->
                                (filter == "All" || row.coverageArea == filter) &&
                                    (q.isEmpty() || listOf(row.name, row.coverageArea, row.url)
                                        .joinToString(" ").lowercase().contains(q))
                            }
                            CountBar(rows.size)
                            LazyColumn(
                                contentPadding = PaddingValues(12.dp),
                                verticalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                items(rows, key = { it.id }) { row ->
                                    DetailCard(
                                        title = row.name ?: "Source",
                                        subtitle = row.coverageArea ?: "—",
                                        chips = listOfNotNull(row.status),
                                        body = "",
                                        link = row.url,
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CountBar(count: Int) {
    Text(
        text = "$count rows",
        style = MaterialTheme.typography.labelMedium,
        color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
        modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp),
    )
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun DetailCard(
    title: String,
    subtitle: String,
    chips: List<String>,
    body: String,
    link: String?,
) {
    val context = LocalContext.current
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
        shape = RoundedCornerShape(14.dp),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            if (subtitle.isNotBlank()) {
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurface.copy(alpha = 0.7f),
                    modifier = Modifier.padding(top = 2.dp),
                )
            }
            if (chips.isNotEmpty()) {
                FlowRow(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                    modifier = Modifier.padding(top = 8.dp),
                ) {
                    chips.filter { it.isNotBlank() }.forEach { c ->
                        FilterChip(selected = false, onClick = {}, label = { Text(c) })
                    }
                }
            }
            if (body.isNotBlank()) {
                Text(
                    body.trim(),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(top = 8.dp),
                )
            }
            if (!link.isNullOrBlank()) {
                Row(
                    verticalAlignment = Alignment.CenterVertically,
                    modifier = Modifier
                        .padding(top = 8.dp)
                        .clickable {
                            val url = if (link.startsWith("http")) link else "https://$link"
                            runCatching {
                                context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url.split(";").first().trim())))
                            }
                        },
                ) {
                    Icon(Icons.Default.OpenInNew, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    Spacer(Modifier.width(6.dp))
                    Text(
                        link,
                        color = MaterialTheme.colorScheme.primary,
                        maxLines = 2,
                        overflow = TextOverflow.Ellipsis,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
    }
}
