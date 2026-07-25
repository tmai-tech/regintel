package com.logicrequire.regintel.data

data class TrackingRow(
    val id: String = "",
    val country: String? = null,
    val federalOrState: String? = null,
    val dateOfTracking: String? = null,
    val dateOfPublication: String? = null,
    val lawArea: String? = null,
    val topicalRelevance: String? = null,
    val link: String? = null,
    val remarks: String? = null,
    val trackedBy: String? = null,
    val relevancy: String? = null,
    val comments: String? = null,
    val corImpact: String? = null,
    val alertStatus: String? = null,
)

data class PrimarySource(
    val id: String = "",
    val region: String? = null,
    val jurisdiction: String? = null,
    val authority: String? = null,
    val authorityType: String? = null,
    val linkNature: String? = null,
    val url: String? = null,
    val frequency: String? = null,
    val segment: String? = null,
    val topics: List<String> = emptyList(),
    val status: String? = null,
)

data class UpdateRow(
    val id: String = "",
    val discoveredAt: String? = null,
    val country: String? = null,
    val region: String? = null,
    val authority: String? = null,
    val title: String? = null,
    val lawArea: String? = null,
    val topicalRelevance: String? = null,
    val link: String? = null,
    val relevancy: String? = null,
    val alertStatus: String? = null,
    val trackedBy: String? = null,
)

data class GazetteRow(
    val id: String = "",
    val jurisdiction: String? = null,
    val parliamentaryBills: String? = null,
    val officialGazette: String? = null,
    val legalDatabases: String? = null,
)

data class SecondarySource(
    val id: String = "",
    val name: String? = null,
    val url: String? = null,
    val coverageArea: String? = null,
    val status: String? = null,
)

data class CatalogMeta(
    val generatedAt: String? = null,
    val lastCollectorRun: String? = null,
    val primarySources: Int = 0,
    val trackingRecords: Int = 0,
    val gazetteSources: Int = 0,
    val secondarySources: Int = 0,
    val updates: Int = 0,
    val source: String = "unknown",
)
