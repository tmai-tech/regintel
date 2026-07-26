package com.logicrequire.regintel

import android.os.Bundle
import android.util.Log
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
        // Last-resort: log crashes instead of silent death during debug
        val prior = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            Log.e("RegIntel", "Uncaught on ${t.name}", e)
            prior?.uncaughtException(t, e)
        }
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
