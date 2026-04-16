package com.cloudstreamvn

import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.utils.*
import com.lagradost.cloudstream3.utils.AppUtils.parseJson
import org.jsoup.nodes.Element

class ThuVienCineProvider : MainAPI() {
    override var mainUrl = "https://thuviencine.com"
    override var name = "ThuVienCine"
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
        "$mainUrl/movies/page/" to "Phim Lẻ",
        "$mainUrl/tv-series/page/" to "Phim Bộ",
        "$mainUrl/top/page/" to "Trending",
        "$mainUrl/phim-hanh-dong/page/" to "Hành Động",
        "$mainUrl/phim-kinh-di/page/" to "Kinh Dị",
        "$mainUrl/phim-vien-tuong/page/" to "Viễn Tưởng",
        "$mainUrl/phim-hai/page/" to "Hài",
        "$mainUrl/phim-hoat-hinh/page/" to "Hoạt Hình",
        "$mainUrl/phim-tam-ly/page/" to "Tâm Lý",
        "$mainUrl/phim-gay-can/page/" to "Gây Cấn",
    )

    override suspend fun getMainPage(page: Int, request: MainPageRequest): HomePageResponse {
        val url = request.data + page
        val document = app.get(url).document

        val home = document.select("div.item, div.items article, div.result-item article, div#archive-content article").mapNotNull {
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
        val aTag = this.selectFirst("a")
        val title = aTag?.attr("title") ?: this.selectFirst(".movie-title")?.text()?.trim() ?: this.selectFirst("div.data h3 a, h3 a, div.data a")?.text()?.trim() ?: return null
        val href = aTag?.attr("href") ?: this.selectFirst("div.data h3 a, h3 a, div.data a")?.attr("href") ?: return null
        val posterUrl = this.selectFirst("div.poster img, img")?.let {
            it.attr("data-lazy-src").ifEmpty { it.attr("data-src").ifEmpty { it.attr("src") } }
        }
        val year = this.selectFirst("span.year, div.data span, span.movie-date")?.text()?.trim()?.toIntOrNull()
        val quality = this.selectFirst("span.quality, span.item-quality")?.text()?.trim()

        // Determine type based on URL
        val type = if (this.selectFirst("span.item-tv") != null || href.contains("/tv-series/") || href.contains("-season-") || href.contains("-phan-")) {
            TvType.TvSeries
        } else {
            TvType.Movie
        }

        return newMovieSearchResponse(title, href, type) {
            this.posterUrl = posterUrl
            this.year = year
            this.quality = getSearchQuality(quality)
        }
    }

    override suspend fun search(query: String): List<SearchResponse> {
        val url = "$mainUrl/?s=$query"
        val document = app.get(url).document

        return document.select("div.item, div.result-item article, div.items article, div#archive-content article").mapNotNull {
            it.toSearchResult()
        }
    }

    override suspend fun load(url: String): LoadResponse? {
        val document = app.get(url).document

        val title = document.selectFirst("h1, div.sheader h1, h1.entry-title")?.text()?.trim()
            ?: return null
        val poster = document.selectFirst("div.poster img, div.sheader div.poster img, meta[property='og:image']")?.let {
            it.attr("content").ifEmpty {
                it.attr("data-lazy-src").ifEmpty { it.attr("data-src").ifEmpty { it.attr("src") } }
            }
        }

        val descriptionRaw = document.selectFirst("div.wp-content p, div#info div.wp-content, meta[property='og:description']")
        val description = descriptionRaw?.let {
            it.attr("content").ifEmpty { it.text() }
        }?.trim()

        val year = document.selectFirst("a[href*='/years/'], span.date, span.year")?.text()?.trim()?.toIntOrNull()

        val tags = document.select("div.sgeneros a, a[rel='tag']").map { it.text().trim() }

        val director = document.select("a[href*='/director/']")
            .joinToString(", ") { it.text().trim() }

        val actors = document.select("a[href*='/actors/']")
            .map { ActorData(Actor(it.text().trim())) }

        val recommendations = document.select("div.owl-item article, div.srelac article, .item-container .item").mapNotNull {
            it.toSearchResult()
        }

        // Extract Fshare links
        val fshareLinks = mutableListOf<String>()
        document.select("a[href*='fshare.vn']").forEach { link ->
            val fshareUrl = link.attr("href")
            if (fshareUrl.isNotEmpty()) {
                fshareLinks.add(fshareUrl)
            }
        }

        // Check download page
        val downloadLink = document.selectFirst("a[href*='/download?id=']")?.attr("href")
        if (downloadLink != null) {
            try {
                val dlUrl = if (downloadLink.startsWith("http")) downloadLink else "$mainUrl$downloadLink"
                val downloadPage = app.get(dlUrl).document
                downloadPage.select("a[href*='fshare.vn']").forEach { link ->
                    val fshareUrl = link.attr("href")
                    if (fshareUrl.isNotEmpty() && fshareUrl !in fshareLinks) {
                        fshareLinks.add(fshareUrl)
                    }
                }
            } catch (_: Exception) {}
        }

        // Check if TV Series
        val isSeries = url.contains("/tv-series/") ||
                tags.any { it.contains("Phim Bộ", ignoreCase = true) } ||
                document.select("div.episodios li, ul.episodios li, div.se-c").isNotEmpty()

        if (isSeries) {
            val episodes = mutableListOf<Episode>()

            val episodeElements = document.select("div.episodios li, ul.episodios li")
            if (episodeElements.isNotEmpty()) {
                episodeElements.forEachIndexed { index, ep ->
                    val epTitle = ep.selectFirst("a")?.text()?.trim() ?: "Tập ${index + 1}"
                    val epLink = ep.selectFirst("a")?.attr("href") ?: url
                    episodes.add(newEpisode(epLink) {
                        this.name = epTitle
                        this.episode = index + 1
                    })
                }
            } else {
                // Use fshare links as episodes
                fshareLinks.forEachIndexed { index, link ->
                    episodes.add(newEpisode(link) {
                        this.name = "Link ${index + 1}"
                        this.episode = index + 1
                    })
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
            // It's a page URL, extract fshare links
            try {
                val document = app.get(data).document
                val links = mutableListOf<String>()
                document.select("a[href*='fshare.vn']").forEach { link ->
                    val fshareUrl = link.attr("href")
                    if (fshareUrl.isNotEmpty()) links.add(fshareUrl)
                }

                val downloadLink = document.selectFirst("a[href*='/download?id=']")?.attr("href")
                if (downloadLink != null) {
                    try {
                        val dlUrl = if (downloadLink.startsWith("http")) downloadLink else "$mainUrl$downloadLink"
                        val downloadPage = app.get(dlUrl).document
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
                val linkCode = fshareUrl.substringAfterLast("/")
                if (linkCode.isNotEmpty()) {
                    val getlinkUrl = "$fshareGetlinkApi?id=$linkCode"
                    val response = app.get(getlinkUrl).text

                    try {
                        val jsonResponse = parseJson<FshareResponse>(response)
                        val videoUrl = jsonResponse.URL
                        val fileName = jsonResponse.Name ?: "Video ${index + 1}"

                        if (videoUrl.isNotEmpty()) {
                            val qualityVal = when {
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
                                    type = ExtractorLinkType.VIDEO
                                ) {
                                    this.referer = mainUrl
                                    this.quality = qualityVal
                                }
                            )
                        }
                    } catch (_: Exception) {}
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
