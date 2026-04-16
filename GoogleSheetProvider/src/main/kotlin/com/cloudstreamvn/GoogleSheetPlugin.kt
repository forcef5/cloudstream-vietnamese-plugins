package com.cloudstreamvn

import com.lagradost.cloudstream3.plugins.CloudstreamPlugin
import com.lagradost.cloudstream3.plugins.Plugin
import android.content.Context

@CloudstreamPlugin
class GoogleSheetPlugin: Plugin() {
    override fun load(context: Context) {
        registerMainAPI(GoogleSheetProvider())
    }
}
