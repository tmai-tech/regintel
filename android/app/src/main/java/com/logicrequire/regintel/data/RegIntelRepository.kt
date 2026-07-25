package com.logicrequire.regintel.data

import android.content.Context
import com.google.firebase.firestore.FirebaseFirestore
import com.google.firebase.firestore.Query
import com.google.gson.Gson
import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.util.UUID

class RegIntelRepository(
    private val context: Context,
    private val db: FirebaseFirestore = FirebaseFirestore.getInstance(),
) {
    private val gson = Gson()

    suspend fun loadMeta(): CatalogMeta = withContext(Dispatchers.IO) {
        runCatching {
            val snap = db.collection(COL_META).document("catalog").get().await()
            if (snap.exists()) {
                CatalogMeta(
                    generatedAt = snap.getString("generated_at"),
                    lastCollectorRun = snap.getString("last_collector_run"),
                    primarySources = (snap.getLong("primary_sources") ?: 0L).toInt(),
                    trackingRecords = (snap.getLong("tracking_records") ?: 0L).toInt(),
                    gazetteSources = (snap.getLong("gazette_sources") ?: 0L).toInt(),
                    secondarySources = (snap.getLong("secondary_sources") ?: 0L).toInt(),
                    updates = (snap.getLong("updates") ?: 0L).toInt(),
                    source = "firestore",
                )
            } else {
                loadMetaFromAssets()
            }
        }.getOrElse { loadMetaFromAssets() }
    }

    suspend fun loadTracking(): List<TrackingRow> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_TRACKING).limit(1000).get().await().documents.map { d ->
                TrackingRow(
                    id = d.id,
                    country = d.getString("country"),
                    federalOrState = d.getString("federal_or_state"),
                    dateOfTracking = d.getString("date_of_tracking"),
                    dateOfPublication = d.getString("date_of_publication"),
                    lawArea = d.getString("law_area"),
                    topicalRelevance = d.getString("topical_relevance"),
                    link = d.getString("link"),
                    remarks = d.getString("remarks"),
                    trackedBy = d.getString("tracked_by"),
                    relevancy = d.getString("relevancy"),
                    comments = d.getString("comments"),
                    corImpact = d.getString("cor_impact"),
                    alertStatus = d.getString("alert_status"),
                )
            }
        }.getOrDefault(emptyList())
        if (remote.isNotEmpty()) remote else loadTrackingFromAssets()
    }

    suspend fun loadPrimary(limit: Long = 2000): List<PrimarySource> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_PRIMARY).limit(limit).get().await().documents.map { d ->
                @Suppress("UNCHECKED_CAST")
                val topics = (d.get("topics") as? List<*>)?.mapNotNull { it?.toString() } ?: emptyList()
                PrimarySource(
                    id = d.id,
                    region = d.getString("region"),
                    jurisdiction = d.getString("jurisdiction"),
                    authority = d.getString("authority"),
                    authorityType = d.getString("authority_type"),
                    linkNature = d.getString("link_nature"),
                    url = d.getString("url"),
                    frequency = d.getString("frequency"),
                    segment = d.getString("segment"),
                    topics = topics,
                    status = d.getString("status"),
                )
            }
        }.getOrDefault(emptyList())
        if (remote.isNotEmpty()) remote else loadPrimaryFromAssets()
    }

    suspend fun loadUpdates(): List<UpdateRow> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_UPDATES)
                .orderBy("discovered_at", Query.Direction.DESCENDING)
                .limit(1000)
                .get()
                .await()
                .documents
                .map { d ->
                    UpdateRow(
                        id = d.id,
                        discoveredAt = d.getString("discovered_at"),
                        country = d.getString("country"),
                        region = d.getString("region"),
                        authority = d.getString("authority"),
                        title = d.getString("title"),
                        lawArea = d.getString("law_area"),
                        topicalRelevance = d.getString("topical_relevance"),
                        link = d.getString("link"),
                        relevancy = d.getString("relevancy"),
                        alertStatus = d.getString("alert_status"),
                        trackedBy = d.getString("tracked_by"),
                    )
                }
        }.getOrDefault(emptyList())
        if (remote.isNotEmpty()) remote else loadUpdatesFromAssets()
    }

    suspend fun loadGazette(): List<GazetteRow> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_GAZETTE).limit(500).get().await().documents.map { d ->
                GazetteRow(
                    id = d.id,
                    jurisdiction = d.getString("jurisdiction"),
                    parliamentaryBills = d.getString("parliamentary_bills"),
                    officialGazette = d.getString("official_gazette"),
                    legalDatabases = d.getString("legal_databases"),
                )
            }
        }.getOrDefault(emptyList())
        if (remote.isNotEmpty()) remote else loadGazetteFromAssets()
    }

    suspend fun loadSecondary(): List<SecondarySource> = withContext(Dispatchers.IO) {
        val remote = runCatching {
            db.collection(COL_SECONDARY).limit(500).get().await().documents.map { d ->
                SecondarySource(
                    id = d.id,
                    name = d.getString("name"),
                    url = d.getString("url"),
                    coverageArea = d.getString("coverage_area"),
                    status = d.getString("status"),
                )
            }
        }.getOrDefault(emptyList())
        if (remote.isNotEmpty()) remote else loadSecondaryFromAssets()
    }

    private fun assetText(name: String): String =
        context.assets.open(name).bufferedReader().use { it.readText() }

    private fun loadMetaFromAssets(): CatalogMeta {
        val o = gson.fromJson(assetText("meta.json"), JsonObject::class.java)
        val c = o.getAsJsonObject("counts")
        return CatalogMeta(
            generatedAt = o.get("generated_at")?.asString,
            lastCollectorRun = o.get("last_collector_run")?.asString,
            primarySources = c?.get("primary_sources")?.asInt ?: 0,
            trackingRecords = c?.get("tracking_records")?.asInt ?: 0,
            gazetteSources = c?.get("gazette_sources")?.asInt ?: 0,
            secondarySources = c?.get("secondary_sources")?.asInt ?: 0,
            updates = c?.get("updates")?.asInt ?: 0,
            source = "assets",
        )
    }

    private fun loadTrackingFromAssets(): List<TrackingRow> {
        val arr = gson.fromJson(assetText("tracking.json"), JsonArray::class.java)
        return arr.mapIndexed { i, el ->
            val o = el.asJsonObject
            TrackingRow(
                id = "local-$i",
                country = o.str("country"),
                federalOrState = o.str("federal_or_state"),
                dateOfTracking = o.str("date_of_tracking"),
                dateOfPublication = o.str("date_of_publication"),
                lawArea = o.str("law_area"),
                topicalRelevance = o.str("topical_relevance"),
                link = o.str("link"),
                remarks = o.str("remarks"),
                trackedBy = o.str("tracked_by"),
                relevancy = o.str("relevancy"),
                comments = o.str("comments"),
                corImpact = o.str("cor_impact"),
                alertStatus = o.str("alert_status"),
            )
        }
    }

    private fun loadPrimaryFromAssets(): List<PrimarySource> {
        val type = object : TypeToken<List<Map<String, Any?>>>() {}.type
        val list: List<Map<String, Any?>> = gson.fromJson(assetText("primary_sources.json"), type)
        return list.mapIndexed { i, m ->
            @Suppress("UNCHECKED_CAST")
            val topics = (m["topics"] as? List<*>)?.mapNotNull { it?.toString() } ?: emptyList()
            PrimarySource(
                id = "local-$i",
                region = m["region"]?.toString(),
                jurisdiction = m["jurisdiction"]?.toString(),
                authority = m["authority"]?.toString(),
                authorityType = m["authority_type"]?.toString(),
                linkNature = m["link_nature"]?.toString(),
                url = m["url"]?.toString(),
                frequency = m["frequency"]?.toString(),
                segment = m["segment"]?.toString(),
                topics = topics,
                status = m["status"]?.toString(),
            )
        }
    }

    private fun loadUpdatesFromAssets(): List<UpdateRow> {
        val arr = runCatching {
            gson.fromJson(assetText("updates.json"), JsonArray::class.java)
        }.getOrDefault(JsonArray())
        return arr.mapIndexed { i, el ->
            val o = el.asJsonObject
            UpdateRow(
                id = o.str("id") ?: "local-$i",
                discoveredAt = o.str("discovered_at"),
                country = o.str("country"),
                region = o.str("region"),
                authority = o.str("authority"),
                title = o.str("title"),
                lawArea = o.str("law_area"),
                topicalRelevance = o.str("topical_relevance"),
                link = o.str("link"),
                relevancy = o.str("relevancy"),
                alertStatus = o.str("alert_status"),
                trackedBy = o.str("tracked_by"),
            )
        }
    }

    private fun loadGazetteFromAssets(): List<GazetteRow> {
        val arr = gson.fromJson(assetText("gazette.json"), JsonArray::class.java)
        return arr.mapIndexed { i, el ->
            val o = el.asJsonObject
            GazetteRow(
                id = "local-$i",
                jurisdiction = o.str("jurisdiction"),
                parliamentaryBills = o.str("parliamentary_bills"),
                officialGazette = o.str("official_gazette"),
                legalDatabases = o.str("legal_databases"),
            )
        }
    }

    private fun loadSecondaryFromAssets(): List<SecondarySource> {
        val arr = gson.fromJson(assetText("secondary_sources.json"), JsonArray::class.java)
        return arr.mapIndexed { i, el ->
            val o = el.asJsonObject
            SecondarySource(
                id = "local-$i",
                name = o.str("name"),
                url = o.str("url"),
                coverageArea = o.str("coverage_area"),
                status = o.str("status"),
            )
        }
    }

    private fun JsonObject.str(key: String): String? =
        if (has(key) && !get(key).isJsonNull) get(key).asString else null

    companion object {
        const val COL_META = "regintel_meta"
        const val COL_TRACKING = "regintel_tracking"
        const val COL_PRIMARY = "regintel_primary_sources"
        const val COL_UPDATES = "regintel_updates"
        const val COL_GAZETTE = "regintel_gazette"
        const val COL_SECONDARY = "regintel_secondary"
    }
}
