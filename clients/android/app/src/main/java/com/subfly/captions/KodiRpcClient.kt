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
