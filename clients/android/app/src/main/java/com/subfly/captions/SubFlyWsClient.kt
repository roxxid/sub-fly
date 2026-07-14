package com.subfly.captions

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit

private const val TAG = "SubFlyWs"

data class SubtitleCue(val start: Double, val end: Double, val text: String)

/**
 * Talks to the SubFly server's source-agnostic live endpoint
 * (`/v1/live`). The server never opens a file here — this client just
 * streams raw 16kHz mono s16le PCM continuously and gets caption cues
 * back. Same protocol as clients/python and the Kodi addon's live mode;
 * see PROTOCOL.md.
 */
class SubFlyWsClient(
    private val baseUrl: String,
    private val token: String,
    private val onSubtitle: (SubtitleCue) -> Unit,
    private val onError: (String) -> Unit,
    private val onClosed: () -> Unit,
) {
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private var ws: WebSocket? = null

    val isOpen: Boolean
        get() = ws != null

    fun connect(language: String, startSeconds: Double) {
        val wsScheme = if (baseUrl.startsWith("https")) "wss" else "ws"
        val hostPart = baseUrl.substringAfter("://")
        val urlBuilder = StringBuilder("$wsScheme://$hostPart/v1/live?language=$language&start_seconds=$startSeconds")
        if (token.isNotEmpty()) {
            urlBuilder.append("&token=").append(token)
        }
        val fullUrl = urlBuilder.toString()
        val request = Request.Builder().url(fullUrl).build()
        ws = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                Log.i(TAG, "connected: ${fullUrl.substringBefore('?')}")
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleMessage(text)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                Log.e(TAG, "ws failure: ${t.message}")
                onError(t.message ?: "websocket failure")
                ws = null
                onClosed()
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                Log.i(TAG, "ws closed: $code $reason")
                ws = null
                onClosed()
            }
        })
    }

    private fun handleMessage(text: String) {
        try {
            val data = JSONObject(text)
            when (data.optString("type")) {
                "subtitle" -> onSubtitle(
                    SubtitleCue(
                        start = data.optDouble("start", 0.0),
                        end = data.optDouble("end", 0.0),
                        text = data.optString("text", "").trim(),
                    )
                )
                "error" -> onError(data.optString("message", "server error"))
            }
        } catch (e: Exception) {
            Log.w(TAG, "bad message: $text", e)
        }
    }

    fun sendPcm(pcm: ByteArray) {
        ws?.send(ByteString.of(*pcm))
    }

    fun sendPosition(position: Double) {
        sendJson(JSONObject().apply { put("type", "position"); put("position", position) })
    }

    fun sendPause(paused: Boolean) {
        sendJson(JSONObject().apply { put("type", "pause"); put("paused", paused) })
    }

    fun sendSeek(position: Double) {
        sendJson(JSONObject().apply { put("type", "seek"); put("position", position) })
    }

    private fun sendJson(obj: JSONObject) {
        ws?.send(obj.toString())
    }

    fun close() {
        sendJson(JSONObject().apply { put("type", "stop") })
        ws?.close(1000, "client closing")
        ws = null
    }
}
