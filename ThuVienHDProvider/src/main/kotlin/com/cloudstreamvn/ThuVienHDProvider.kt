package com.cloudstreamvn

import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.utils.*
import com.lagradost.cloudstream3.utils.AppUtils.parseJson
import org.jsoup.nodes.Element

class ThuVienHDProvider : MainAPI() {
    override var mainUrl = "https://thuvienhd.top"
    override var name = "ThuVienHD"
    override val hasMainPage = true
    override var lang = "vi"
    override val hasDownloadSupport = true
    override val supportedTypes = setOf(
        TvType.Movie,
        TvType.TvSeries
    )

    // Fshare getlink API
    private val fshareGetlinkApi = "http://fspoint.shop:8308/getlink"

    override val mainPage = mainPageOf(
        "$mainUrl/recent/page/" to "Phim Mới Nhất",
        "$mainUrl/trending/page/" to "Phim HOT",
        "$mainUrl/genre/phim-le/page/" to "Phim Lẻ",
        "$mainUrl/genre/series/page/" to "Phim Bộ",
        "$mainUrl/genre/thuyet-minh-tieng-viet/page/" to "Thuyết Minh",
        "$mainUrl/genre/long-tieng-tieng-viet/page/" to "Lồng Tiếng",
        "$mainUrl/genre/action/page/" to "Hành Động",
        "$mainUrl/genre/horror/page/" to "Kinh Dị",
        "$mainUrl/genre/sci-fi/page/" to "Viễn Tưởng",
        "$mainUrl/genre/korean/page/" to "Hàn Quốc",
        "$mainUrl/genre/4k/page/" to "4K",
        "$mainUrl/genre/animation/page/" to "Hoạt Hình",
    )

    override suspend fun getMainPage(page: Int, request: MainPageRequest): HomePageResponse {
        val url = request.data + page
        val document = app.get(url).document

        val home = document.select("div.items article, div.result-item article").mapNotNull {
            it.toSearchResult()
        }

        return newHomePageResponse(
            list = HomePageList(
                name = request.name,
                list = home
            ),
            hasNext = true
        )
    }

    private fun Element.toSearchResult(): SearchResponse? {
        val title = this.selectFirst("div.data h3 a, h3 a")?.text()?.trim() ?: return null
        val href = this.selectFirst("div.data h3 a, h3 a")?.attr("href") ?: return null
        val posterUrl = this.selectFirst("div.poster img, img")?.let {
            it.attr("data-lazy-src").ifEmpty { it.attr("data-src").ifEmpty { it.attr("src") } }
        }
        val year = this.selectFirst("div.data span, span.year")?.text()?.trim()?.toIntOrNull()
        val quality = this.selectFirst("span.quality")?.text()?.trim()

        return newMovieSearchResponse(title, href, TvType.Movie) {
            this.posterUrl = posterUrl
            this.year = year
            this.quality = getSearchQuality(quality)
        }
    }

    override suspend fun search(query: String): List<SearchResponse> {
        val url = "$mainUrl/?s=$query"
        val document = app.get(url).document

        return document.select("div.result-item article, div.items article").mapNotNull {
            it.toSearchResult()
        }
    }

    override suspend fun load(url: String): LoadResponse? {
        val document = app.get(url).document

        val title = document.selectFirst("div.sheader div.data h1, h1.entry-title")?.text()?.trim()
            ?: return null
        val poster = document.selectFirst("div.poster img, div.sheader div.poster img")?.let {
            it.attr("data-lazy-src").ifEmpty { it.attr("data-src").ifEmpty { it.attr("src") } }
        }
        val description = document.selectFirst("div#info div.wp-content p, div.wp-content p")?.text()?.trim()
        val year = document.selectFirst("span.date")?.text()?.trim()?.takeLast(4)?.toIntOrNull()

        val tags = document.select("div.sgeneros a, a[href*='/genre/']").map { it.text().trim() }

        val director = document.select("div.person[itemprop=director] span.name a, a[href*='/director/']")
            .joinToString(", ") { it.text().trim() }

        val actors = document.select("div.person[itemprop=actor] span.name a, a[href*='/cast/']")
            .map { ActorData(Actor(it.text().trim())) }

        // Extract Fshare download links
        val recommendations = document.select("div.owl-item article, div.srelac article").mapNotNull {
            it.toSearchResult()
        }

        // Check if it's a TV Series by looking at episode links or genre
        val isSeries = tags.any { it.contains("Phim Bộ", ignoreCase = true) || it.contains("Series", ignoreCase = true) }
                || document.select("div.episodios li, ul.episodios li").isNotEmpty()

        // Extract Fshare links from the page
        val fshareLinks = mutableListOf<String>()
        document.select("a[href*='fshare.vn']").forEach { link ->
            val fshareUrl = link.attr("href")
            if (fshareUrl.isNotEmpty()) {
                fshareLinks.add(fshareUrl)
            }
        }

        // Also check download page
        val downloadLink = document.selectFirst("a[href*='/download?id=']")?.attr("href")
        if (downloadLink != null) {
            try {
                val downloadPage = app.get(
                    if (downloadLink.startsWith("http")) downloadLink else "$mainUrl$downloadLink"
                ).document
                downloadPage.select("a[href*='fshare.vn']").forEach { link ->
                    val fshareUrl = link.attr("href")
                    if (fshareUrl.isNotEmpty() && fshareUrl !in fshareLinks) {
                        fshareLinks.add(fshareUrl)
                    }
                }
            } catch (_: Exception) {}
        }

        if (isSeries) {
            val episodes = mutableListOf<Episode>()

            // Try to get episodes from the page
            val episodeElements = document.select("div.episodios li, ul.episodios li")
            if (episodeElements.isNotEmpty()) {
                episodeElements.forEachIndexed { index, ep ->
                    val epTitle = ep.selectFirst("a")?.text()?.trim() ?: "Tập ${index + 1}"
                    val epLink = ep.selectFirst("a")?.attr("href") ?: url
                    episodes.add(Episode(epLink, epTitle, episode = index + 1))
                }
            } else {
                // If no episodes found, use fshare links as episodes
                fshareLinks.forEachIndexed { index, link ->
                    val sizeInfo = document.select("a[href='$link']").firstOrNull()
                        ?.parent()?.text()?.trim() ?: "Link ${index + 1}"
                    episodes.add(Episode(
                        data = link,
                        name = sizeInfo,
                        episode = index + 1
                    ))
                }
            }

            return newTvSeriesLoadResponse(title, url, TvType.TvSeries, episodes) {
                this.posterUrl = poster
                this.plot = description
                this.year = year
                this.tags = tags
                this.recommendations = recommendations
                this.actors = actors
            }
        } else {
            // Movie - store fshare links as data
            val dataStr = fshareLinks.joinToString("|||")

            return newMovieLoadResponse(title, url, TvType.Movie, dataStr) {
                this.posterUrl = poster
                this.plot = description
                this.year = year
                this.tags = tags
                this.recommendations = recommendations
                this.actors = actors
            }
        }
    }

    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        val fshareLinks = if (data.contains("|||")) {
            data.split("|||")
        } else if (data.contains("fshare.vn")) {
            listOf(data)
        } else {
            // It's a URL, load the page and extract fshare links
            try {
                val document = app.get(data).document
                val links = mutableListOf<String>()
                document.select("a[href*='fshare.vn']").forEach { link ->
                    val fshareUrl = link.attr("href")
                    if (fshareUrl.isNotEmpty()) links.add(fshareUrl)
                }

                // Also check download page
                val downloadLink = document.selectFirst("a[href*='/download?id=']")?.attr("href")
                if (downloadLink != null) {
                    try {
                        val downloadPage = app.get(
                            if (downloadLink.startsWith("http")) downloadLink else "$mainUrl$downloadLink"
                        ).document
                        downloadPage.select("a[href*='fshare.vn']").forEach { link ->
                            val fshareUrl = link.attr("href")
                            if (fshareUrl.isNotEmpty() && fshareUrl !in links) {
                                links.add(fshareUrl)
                            }
                        }
                    } catch (_: Exception) {}
                }
                links
            } catch (_: Exception) {
                return false
            }
        }

        fshareLinks.forEachIndexed { index, fshareUrl ->
            try {
                // Extract linkcode from fshare URL
                // Format: https://www.fshare.vn/file/XXXXXXXXX or https://www.fshare.vn/folder/XXXXXXXXX
                val linkCode = fshareUrl.substringAfterLast("/")
                if (linkCode.isNotEmpty()) {
                    val getlinkUrl = "$fshareGetlinkApi?id=$linkCode"
                    val response = app.get(getlinkUrl).text

                    try {
                        val jsonResponse = parseJson<FshareResponse>(response)
                        val videoUrl = jsonResponse.URL
                        val fileName = jsonResponse.Name ?: "Video ${index + 1}"

                        if (videoUrl.isNotEmpty()) {
                            val quality = when {
                                fileName.contains("2160p", ignoreCase = true) || fileName.contains("4K", ignoreCase = true) -> Qualities.P2160.value
                                fileName.contains("1080p", ignoreCase = true) -> Qualities.P1080.value
                                fileName.contains("720p", ignoreCase = true) -> Qualities.P720.value
                                fileName.contains("480p", ignoreCase = true) -> Qualities.P480.value
                                else -> Qualities.Unknown.value
                            }

                            callback.invoke(
                                newExtractorLink(
                                    source = this.name,
                                    name = "$name - $fileName",
                                    url = videoUrl,
                                    referer = mainUrl,
                                    quality = quality,
                                    isM3u8 = videoUrl.contains(".m3u8")
                                )
                            )
                        }
                    } catch (_: Exception) {
                        // If JSON parsing fails, the getlink API might return an error
                    }
                }
            } catch (_: Exception) {}
        }

        return fshareLinks.isNotEmpty()
    }

    private fun getSearchQuality(quality: String?): SearchQuality? {
        return when (quality?.lowercase()) {
            "4k", "2160p" -> SearchQuality.FourK
            "hd", "1080p" -> SearchQuality.HD
            "sd", "720p" -> SearchQuality.SD
            "cam" -> SearchQuality.Cam
            "camrip" -> SearchQuality.CamRip
            "hdrip" -> SearchQuality.HD
            "dvd" -> SearchQuality.DVD
            "bluray" -> SearchQuality.BlueRay
            else -> null
        }
    }

    data class FshareResponse(
        val URL: String = "",
        val Name: String? = null
    )
}
