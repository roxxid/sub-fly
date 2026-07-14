package com.subfly.captions

import android.util.Log
import okhttp3.Credentials
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

private const val TAG = "SubFlyKodiRpc"
private const val MAX_CAST_NAMES = 8
private const val MAX_PLOT_CHARS = 200
private const val MAX_HINT_CHARS = 480

/** Current Kodi playback state, polled from the local JSON-RPC endpoint. */
data class KodiPlaybackState(
    val playing: Boolean,
    val paused: Boolean,
    val positionSeconds: Double,
    val label: String,
)

/**
 * Minimal Kodi JSON-RPC client, used instead of a Kodi Python addon so this
 * app works no matter what Kodi is playing (files, add-ons, live TV/PVR,
 * anything) — it just asks Kodi "what's the playback clock right now?"
 *
 * Requires Kodi &gt; Settings &gt; Services &gt; Control &gt;
 * "Allow remote control via HTTP".
 */
class KodiRpcClient(
    private val host: String,
    private val port: Int,
    private val username: String,
    private val password: String,
) {
    private val client = OkHttpClient.Builder()
        .connectTimeout(3, TimeUnit.SECONDS)
        .readTimeout(3, TimeUnit.SECONDS)
        .build()

    private val jsonMediaType = "application/json".toMediaType()

    fun getPlaybackState(): KodiPlaybackState? {
        return try {
            val activePlayers = call(
                "Player.GetActivePlayers",
                JSONObject(),
            ) ?: return null
            val results = activePlayers.optJSONArray("result") ?: JSONArray()
            val videoPlayer = (0 until results.length())
                .map { results.getJSONObject(it) }
                .firstOrNull { it.optString("type") == "video" }
                ?: return KodiPlaybackState(playing = false, paused = false, positionSeconds = 0.0, label = "")

            val playerId = videoPlayer.optInt("playerid")
            val params = JSONObject().apply {
                put("playerid", playerId)
                put("properties", JSONArray(listOf("speed", "time", "percentage")))
            }
            val props = call("Player.GetProperties", params) ?: return null
            val result = props.optJSONObject("result") ?: return null
            val speed = result.optInt("speed", 0)
            val time = result.optJSONObject("time")
            val seconds = timeObjToSeconds(time)

            KodiPlaybackState(
                playing = true,
                paused = speed == 0,
                positionSeconds = seconds,
                label = "video",
            )
        } catch (e: Exception) {
            Log.w(TAG, "Kodi RPC unavailable: ${e.message}")
            null
        }
    }

    /**
     * Best-effort "what's playing" text (title/show/cast/genre/plot) used to
     * bias Whisper's decoding toward the specific proper nouns of whatever
     * Kodi is currently playing (sent to the server as `vocabulary_hint`,
     * which becomes faster-whisper's `hotwords`). Coverage depends on how
     * much metadata Kodi actually has for the current item — scraped
     * library items give this plenty to work with; an unscraped file or
     * add-on stream may give it nothing, which is harmless.
     */
    fun getNowPlayingHint(): String {
        return try {
            val activePlayers = call("Player.GetActivePlayers", JSONObject()) ?: return ""
            val results = activePlayers.optJSONArray("result") ?: JSONArray()
            val videoPlayer = (0 until results.length())
                .map { results.getJSONObject(it) }
                .firstOrNull { it.optString("type") == "video" }
                ?: return ""

            val playerId = videoPlayer.optInt("playerid")
            val params = JSONObject().apply {
                put("playerid", playerId)
                put(
                    "properties",
                    JSONArray(listOf("title", "showtitle", "plot", "cast", "genre")),
                )
            }
            val itemResp = call("Player.GetItem", params) ?: return ""
            val item = itemResp.optJSONObject("result")?.optJSONObject("item") ?: return ""

            val bits = mutableListOf<String>()
            item.optString("showtitle").takeIf { it.isNotBlank() }?.let { bits.add(it) }
            item.optString("title").takeIf { it.isNotBlank() }?.let { bits.add(it) }

            val cast = item.optJSONArray("cast")
            if (cast != null && cast.length() > 0) {
                val names = (0 until minOf(cast.length(), MAX_CAST_NAMES)).mapNotNull { i ->
                    cast.optJSONObject(i)?.optString("name")?.takeIf { it.isNotBlank() }
                }
                if (names.isNotEmpty()) bits.add("Characters/cast: " + names.joinToString(", "))
            }

            val genre = item.optJSONArray("genre")
            if (genre != null && genre.length() > 0) {
                val genres = (0 until genre.length()).mapNotNull { i ->
                    genre.optString(i).takeIf { it.isNotBlank() }
                }
                if (genres.isNotEmpty()) bits.add(genres.joinToString(", "))
            }

            item.optString("plot").takeIf { it.isNotBlank() }?.let {
                bits.add(it.take(MAX_PLOT_CHARS))
            }

            bits.joinToString(". ").take(MAX_HINT_CHARS)
        } catch (e: Exception) {
            Log.w(TAG, "could not fetch now-playing metadata: ${e.message}")
            ""
        }
    }

    private fun timeObjToSeconds(time: JSONObject?): Double {
        if (time == null) return 0.0
        val h = time.optInt("hours", 0)
        val m = time.optInt("minutes", 0)
        val s = time.optInt("seconds", 0)
        val ms = time.optInt("milliseconds", 0)
        return h * 3600.0 + m * 60.0 + s + ms / 1000.0
    }

    private fun call(method: String, params: JSONObject): JSONObject? {
        val body = JSONObject().apply {
            put("jsonrpc", "2.0")
            put("id", 1)
            put("method", method)
            put("params", params)
        }
        val requestBuilder = Request.Builder()
            .url("http://$host:$port/jsonrpc")
            .post(body.toString().toRequestBody(jsonMediaType))
        if (username.isNotEmpty()) {
            requestBuilder.header("Authorization", Credentials.basic(username, password))
        }
        client.newCall(requestBuilder.build()).execute().use { resp ->
            if (!resp.isSuccessful) throw IOException("Kodi RPC HTTP ${resp.code}")
            val text = resp.body?.string() ?: return null
            return JSONObject(text)
        }
    }
}
