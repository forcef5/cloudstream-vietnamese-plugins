package com.cloudstreamvn

import com.lagradost.cloudstream3.plugins.CloudstreamPlugin
import com.lagradost.cloudstream3.plugins.Plugin
import android.content.Context

@CloudstreamPlugin
class ThuVienCinePlugin: Plugin() {
    override fun load(context: Context) {
        registerMainAPI(ThuVienCineProvider())
    }
}
