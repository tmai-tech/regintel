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
