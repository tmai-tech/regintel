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
)

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
