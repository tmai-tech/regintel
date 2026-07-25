package com.logicrequire.regintel

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.logicrequire.regintel.ui.RegIntelAppRoot
import com.logicrequire.regintel.ui.theme.RegIntelTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            RegIntelTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    RegIntelAppRoot()
                }
            }
        }
    }
}
