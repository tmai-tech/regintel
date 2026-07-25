package com.logicrequire.regintel

import android.app.Application
import com.google.firebase.FirebaseApp

class RegIntelApp : Application() {
    override fun onCreate() {
        super.onCreate()
        FirebaseApp.initializeApp(this)
    }
}
