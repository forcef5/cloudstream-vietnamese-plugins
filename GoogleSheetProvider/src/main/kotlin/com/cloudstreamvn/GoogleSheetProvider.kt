package com.cloudstreamvn

import com.lagradost.cloudstream3.*
import com.lagradost.cloudstream3.utils.*
import com.lagradost.cloudstream3.utils.AppUtils.parseJson
import java.io.StringReader
import java.io.BufferedReader

class GoogleSheetProvider : MainAPI() {
    override var mainUrl = "https://docs.google.com/spreadsheets/d/1DZAw3-cSn1FFIZA17_6ZjdtdLqI8J3xFf0FogTab4lg"
    override var name = "Kho Phim Sheet"
    override val hasMainPage = true
    override var lang = "vi"
    override val hasDownloadSupport = true
    override val supportedTypes = setOf(
        TvType.Movie,
        TvType.TvSeries
    )

    // Fshare getlink API
    private val fshareGetlinkApi = "http://fspoint.shop:8308/getlink"

    // Google Sheet ID - can be changed
    private val sheetId = "1DZAw3-cSn1FFIZA17_6ZjdtdLqI8J3xFf0FogTab4lg"

    // Cache for movie data
    private var cachedMovies: List<SheetMovie>? = null
    private var lastFetchTime: Long = 0
    private val cacheTimeMs = 30 * 60 * 1000L // 30 minutes cache

    override val mainPage = mainPageOf(
        "all" to "Tất Cả Phim",
        "new" to "Phim Mới Thêm",
    )

    override suspend fun getMainPage(page: Int, request: MainPageRequest): HomePageResponse {
        val movies = fetchMovies()

        val itemsPerPage = 20
        val startIndex = (page - 1) * itemsPerPage

        val displayMovies = when (request.data) {
            "new" -> movies.take(50)  // Latest 50 movies
            else -> movies
        }

        val pagedMovies = displayMovies.drop(startIndex).take(itemsPerPage)
        val hasNext = startIndex + itemsPerPage < displayMovies.size

        val home = pagedMovies.mapNotNull { movie ->
            movie.toSearchResponse()
        }

        return newHomePageResponse(
            list = HomePageList(
                name = request.name,
                list = home
            ),
            hasNext = hasNext
        )
    }

    override suspend fun search(query: String): List<SearchResponse> {
        val movies = fetchMovies()
        val searchLower = query.lowercase()

        return movies.filter { movie ->
            movie.title.lowercase().contains(searchLower) ||
            movie.cleanTitle.lowercase().contains(searchLower) ||
            movie.description.lowercase().contains(searchLower)
        }.mapNotNull { it.toSearchResponse() }
    }

    override suspend fun load(url: String): LoadResponse? {
        // URL format: googlesheet://INDEX
        val index = url.removePrefix("googlesheet://").toIntOrNull() ?: return null
        val movies = fetchMovies()
        if (index < 0 || index >= movies.size) return null

        val movie = movies[index]

        val title = movie.cleanTitle
        val poster = movie.posterUrl
        val description = movie.description
        val fshareUrl = movie.fshareUrl

        // Determine type based on fshare URL (folder = series, file = movie)
        val isSeries = fshareUrl.contains("/folder/")

        if (isSeries) {
            // For folders, create a single episode pointing to the folder
            val episodes = listOf(
                newEpisode(fshareUrl) {
                    this.name = title
                    this.episode = 1
                }
            )

            return newTvSeriesLoadResponse(title, url, TvType.TvSeries, episodes) {
                this.posterUrl = poster
                this.plot = description
                this.tags = movie.extractTags()
            }
        } else {
            return newMovieLoadResponse(title, url, TvType.Movie, fshareUrl) {
                this.posterUrl = poster
                this.plot = description
                this.tags = movie.extractTags()
            }
        }
    }

    override suspend fun loadLinks(
        data: String,
        isCasting: Boolean,
        subtitleCallback: (SubtitleFile) -> Unit,
        callback: (ExtractorLink) -> Unit
    ): Boolean {
        if (!data.contains("fshare.vn")) return false

        val linkCode = data.substringAfterLast("/")
        if (linkCode.isEmpty()) return false

        try {
            val getlinkUrl = "$fshareGetlinkApi?id=$linkCode"
            val response = app.get(getlinkUrl).text

            try {
                val jsonResponse = parseJson<FshareResponse>(response)
                val videoUrl = jsonResponse.URL
                val fileName = jsonResponse.Name ?: "Video"

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
                            this.referer = ""
                            this.quality = qualityVal
                        }
                    )
                    return true
                }
            } catch (_: Exception) {}
        } catch (_: Exception) {}

        return false
    }

    private suspend fun fetchMovies(): List<SheetMovie> {
        val currentTime = System.currentTimeMillis()
        if (cachedMovies != null && (currentTime - lastFetchTime) < cacheTimeMs) {
            return cachedMovies!!
        }

        val csvUrl = "https://docs.google.com/spreadsheets/d/$sheetId/gviz/tq?tqx=out:csv"
        val csvText = app.get(csvUrl).text

        val movies = parseCSV(csvText)
        cachedMovies = movies
        lastFetchTime = currentTime

        return movies
    }

    private fun parseCSV(csvText: String): List<SheetMovie> {
        val movies = mutableListOf<SheetMovie>()
        val reader = BufferedReader(StringReader(csvText))

        var line: String?
        var index = 0

        while (reader.readLine().also { line = it } != null) {
            val currentLine = line ?: continue

            try {
                val fields = parseCSVLine(currentLine)
                if (fields.size < 4) continue

                val rawTitle = fields[0]
                val fshareUrl = fields[1]
                val posterUrl = if (fields.size > 2) fields[2] else ""
                val description = if (fields.size > 3) fields[3] else ""

                // Skip header row or empty rows
                if (rawTitle.isBlank() || fshareUrl.isBlank()) continue
                // Skip non-fshare entries
                if (!fshareUrl.contains("fshare.vn")) continue

                val cleanTitle = cleanBBCode(rawTitle)

                movies.add(
                    SheetMovie(
                        index = index,
                        title = rawTitle,
                        cleanTitle = cleanTitle,
                        fshareUrl = fshareUrl.trim(),
                        posterUrl = posterUrl.trim(),
                        description = description.trim()
                    )
                )
                index++
            } catch (_: Exception) {
                continue
            }
        }

        return movies
    }

    /**
     * Parse a CSV line handling quoted fields with commas and escaped quotes
     */
    private fun parseCSVLine(line: String): List<String> {
        val fields = mutableListOf<String>()
        val current = StringBuilder()
        var inQuotes = false
        var i = 0

        while (i < line.length) {
            val c = line[i]
            when {
                c == '"' && !inQuotes -> {
                    inQuotes = true
                }
                c == '"' && inQuotes -> {
                    // Check for escaped quote ""
                    if (i + 1 < line.length && line[i + 1] == '"') {
                        current.append('"')
                        i++ // Skip next quote
                    } else {
                        inQuotes = false
                    }
                }
                c == ',' && !inQuotes -> {
                    fields.add(current.toString())
                    current.clear()
                }
                else -> {
                    current.append(c)
                }
            }
            i++
        }
        fields.add(current.toString())

        return fields
    }

    /**
     * Remove BBCode formatting from title
     * Example: "Tiệc Ăn Chơi Đẫm Máu 2 [B][COLOR yellow]{Sub Việt Mux Sẵn}[/COLOR][/B] Slumber Party Massacre II 1987"
     * Becomes: "Tiệc Ăn Chơi Đẫm Máu 2 - Slumber Party Massacre II 1987"
     */
    private fun cleanBBCode(text: String): String {
        var cleaned = text
        // Remove [B], [/B], [COLOR xxx], [/COLOR] tags
        cleaned = cleaned.replace(Regex("\\[/?B\\]", RegexOption.IGNORE_CASE), "")
        cleaned = cleaned.replace(Regex("\\[COLOR\\s+[^\\]]*\\]", RegexOption.IGNORE_CASE), "")
        cleaned = cleaned.replace(Regex("\\[/COLOR\\]", RegexOption.IGNORE_CASE), "")
        // Remove {xxx} content (like {Sub Việt Mux Sẵn})
        cleaned = cleaned.replace(Regex("\\{[^}]*\\}"), "")
        // Clean up extra spaces
        cleaned = cleaned.replace(Regex("\\s+"), " ").trim()
        return cleaned
    }

    private fun SheetMovie.toSearchResponse(): SearchResponse? {
        if (cleanTitle.isBlank()) return null

        // Extract year from title if possible
        val yearMatch = Regex("(19|20)\\d{2}").findAll(cleanTitle).lastOrNull()
        val year = yearMatch?.value?.toIntOrNull()

        val type = if (fshareUrl.contains("/folder/")) TvType.TvSeries else TvType.Movie

        return newMovieSearchResponse(cleanTitle, "googlesheet://$index", type) {
            this.posterUrl = this@toSearchResponse.posterUrl
            this.year = year
        }
    }

    private fun SheetMovie.extractTags(): List<String> {
        val tags = mutableListOf<String>()
        val titleLower = title.lowercase()

        if (titleLower.contains("thuyết minh")) tags.add("Thuyết Minh")
        if (titleLower.contains("sub việt") || titleLower.contains("vietsub")) tags.add("Vietsub")
        if (titleLower.contains("lồng tiếng") || titleLower.contains("lồng tiềng")) tags.add("Lồng Tiếng")
        if (titleLower.contains("bluray")) tags.add("BluRay")
        if (titleLower.contains("4k") || titleLower.contains("2160p")) tags.add("4K")
        if (titleLower.contains("1080p")) tags.add("1080p")
        if (titleLower.contains("phim việt nam")) tags.add("Phim Việt Nam")

        return tags
    }

    data class SheetMovie(
        val index: Int,
        val title: String,
        val cleanTitle: String,
        val fshareUrl: String,
        val posterUrl: String,
        val description: String
    )

    data class FshareResponse(
        val URL: String = "",
        val Name: String? = null
    )
}
