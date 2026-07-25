package com.logicrequire.regintel.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColors = darkColorScheme(
    primary = Color(0xFF5B8CFF),
    secondary = Color(0xFF3DD6C6),
    background = Color(0xFF0B1220),
    surface = Color(0xFF151F36),
    onPrimary = Color(0xFF081018),
    onSecondary = Color(0xFF081018),
    onBackground = Color(0xFFE8EEFC),
    onSurface = Color(0xFFE8EEFC),
)

private val LightColors = lightColorScheme(
    primary = Color(0xFF2F5BD1),
    secondary = Color(0xFF0F9B8E),
    background = Color(0xFFF4F6FB),
    surface = Color(0xFFFFFFFF),
)

@Composable
fun RegIntelTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    MaterialTheme(
        colorScheme = if (darkTheme) DarkColors else LightColors,
        content = content,
    )
}
