package com.subfly.captions

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Foreground service that owns the MediaProjection token and, while Kodi is
 * playing anything at all, captures system playback audio and streams it to
 * a SubFly server, driving an on-screen caption overlay synced to Kodi's own
 * playback clock (polled via JSON-RPC).
 *
 * Because capture happens after Android's audio mixer (post-decode), the
 * source doesn't matter: local files, external add-on libraries, live
 * TV/PVR, DRM content once decoded for playback — all sound the same to
 * this pipeline.
 */
class CaptureService : Service() {

    private lateinit var prefs: Prefs
    private var mediaProjection: MediaProjection? = null
    private var audioRecord: AudioRecord? = null
    private var captureThread: Thread? = null
    private var wsClient: SubFlyWsClient? = null
    private var overlay: SubtitleOverlay? = null
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var pollJob: Job? = null

    @Volatile private var sessionActive = false
    private var lastKodiPaused = false
    private val cues = mutableListOf<SubtitleCue>()
    private val cuesLock = Object()

    override fun onCreate() {
        super.onCreate()
        prefs = Prefs(this)
        overlay = SubtitleOverlay(this)
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelfCleanly()
            return START_NOT_STICKY
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                buildNotification(),
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION,
            )
        } else {
            startForeground(NOTIFICATION_ID, buildNotification())
        }

        if (mediaProjection == null && intent != null) {
            val resultCode = intent.getIntExtra(EXTRA_RESULT_CODE, -1)
            val resultData: Intent? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                intent.getParcelableExtra(EXTRA_RESULT_DATA, Intent::class.java)
            } else {
                @Suppress("DEPRECATION")
                intent.getParcelableExtra(EXTRA_RESULT_DATA)
            }
            if (resultCode == android.app.Activity.RESULT_OK && resultData != null) {
                val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
                val projection = mpm.getMediaProjection(resultCode, resultData)
                projection.registerCallback(object : MediaProjection.Callback() {
                    override fun onStop() {
                        Log.w(TAG, "MediaProjection stopped externally")
                        stopSelfCleanly()
                    }
                }, Handler(Looper.getMainLooper()))
                mediaProjection = projection
            }
        }

        if (mediaProjection == null) {
            Log.e(TAG, "no media projection available, stopping service")
            stopSelfCleanly()
            return START_NOT_STICKY
        }

        overlay?.attach()
        startPolling()
        return START_STICKY
    }

    override fun onDestroy() {
        stopPolling()
        stopSession()
        mediaProjection?.stop()
        mediaProjection = null
        overlay?.detach()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // --- Kodi playback polling --------------------------------------------

    private fun startPolling() {
        if (pollJob?.isActive == true) return
        pollJob = scope.launch {
            var lastPositionSendMs = 0L
            while (isActive) {
                val rpc = KodiRpcClient(prefs.kodiHost, prefs.kodiPort, prefs.kodiUser, prefs.kodiPass)
                val state = withContext(Dispatchers.IO) { rpc.getPlaybackState() }
                if (state != null && state.playing) {
                    if (!sessionActive) {
                        val hint = withContext(Dispatchers.IO) { rpc.getNowPlayingHint() }
                        startSession(state.positionSeconds, hint)
                    }
                    if (state.paused != lastKodiPaused) {
                        wsClient?.sendPause(state.paused)
                        lastKodiPaused = state.paused
                    }
                    updateOverlay(state.positionSeconds)
                    val now = System.currentTimeMillis()
                    if (now - lastPositionSendMs > 900) {
                        wsClient?.sendPosition(state.positionSeconds)
                        lastPositionSendMs = now
                    }
                } else if (sessionActive) {
                    stopSession()
                }
                delay(POLL_INTERVAL_MS)
            }
        }
    }

    private fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    // --- per-playback session ----------------------------------------------

    private fun startSession(startSeconds: Double, vocabularyHint: String = "") {
        sessionActive = true
        lastKodiPaused = false
        synchronized(cuesLock) { cues.clear() }

        val client = SubFlyWsClient(
            baseUrl = prefs.serverUrl,
            token = prefs.apiToken,
            onSubtitle = { cue -> synchronized(cuesLock) { cues.add(cue) } },
            onError = { msg -> Log.e(TAG, "server error: $msg") },
            onClosed = { Log.i(TAG, "websocket closed") },
        )
        client.connect(prefs.language, startSeconds, vocabularyHint)
        wsClient = client
        startAudioCapture()
    }

    private fun stopSession() {
        sessionActive = false
        stopCapturePipeline()
        wsClient?.close()
        wsClient = null
        overlay?.clear()
        synchronized(cuesLock) { cues.clear() }
    }

    @SuppressLint("MissingPermission")
    private fun startAudioCapture() {
        val projection = mediaProjection ?: return
        val config = AudioPlaybackCaptureConfiguration.Builder(projection)
            .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
            .addMatchingUsage(AudioAttributes.USAGE_UNKNOWN)
            .addMatchingUsage(AudioAttributes.USAGE_GAME)
            .build()

        val format = AudioFormat.Builder()
            .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
            .setSampleRate(SAMPLE_RATE)
            .setChannelMask(AudioFormat.CHANNEL_IN_MONO)
            .build()

        val minBuf = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
        )
        val bufferSize = maxOf(minBuf, SAMPLE_RATE * 2)

        val record = try {
            AudioRecord.Builder()
                .setAudioFormat(format)
                .setBufferSizeInBytes(bufferSize)
                .setAudioPlaybackCaptureConfig(config)
                .build()
        } catch (e: Exception) {
            Log.e(TAG, "failed to create AudioRecord: ${e.message}")
            return
        }

        audioRecord = record
        record.startRecording()

        val thread = Thread({
            val chunk = ByteArray(4096)
            while (!Thread.currentThread().isInterrupted &&
                record.recordingState == AudioRecord.RECORDSTATE_RECORDING
            ) {
                val read = record.read(chunk, 0, chunk.size)
                if (read > 0) {
                    val toSend = if (read == chunk.size) chunk else chunk.copyOf(read)
                    wsClient?.sendPcm(toSend)
                }
            }
        }, "subfly-audio-capture")
        captureThread = thread
        thread.start()
    }

    private fun stopCapturePipeline() {
        captureThread?.interrupt()
        captureThread = null
        audioRecord?.let {
            try {
                it.stop()
            } catch (_: Exception) {
            }
            it.release()
        }
        audioRecord = null
    }

    // --- overlay -------------------------------------------------------------

    private fun updateOverlay(position: Double) {
        val lead = 0.15
        var activeText = ""
        synchronized(cuesLock) {
            cues.removeAll { it.end + 1.0 < position }
            val due = cues.filter { it.start - lead <= position && position <= it.end + 0.35 }
            if (due.isNotEmpty()) activeText = due.last().text
        }
        overlay?.show(activeText)
    }

    // --- lifecycle helpers -----------------------------------------------

    private fun stopSelfCleanly() {
        stopPolling()
        stopSession()
        mediaProjection?.stop()
        mediaProjection = null
        overlay?.detach()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun buildNotification(): Notification {
        val stopIntent = Intent(this, CaptureService::class.java).setAction(ACTION_STOP)
        val stopPending = PendingIntent.getService(
            this,
            0,
            stopIntent,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(getString(R.string.notification_running))
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setOngoing(true)
            .addAction(0, "Stop", stopPending)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel_name),
                NotificationManager.IMPORTANCE_LOW,
            )
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(channel)
        }
    }

    companion object {
        private const val TAG = "SubFlyCapture"
        private const val SAMPLE_RATE = 16000
        private const val POLL_INTERVAL_MS = 500L
        private const val CHANNEL_ID = "subfly_capture"
        private const val NOTIFICATION_ID = 1
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val ACTION_STOP = "com.subfly.captions.STOP"
    }
}
