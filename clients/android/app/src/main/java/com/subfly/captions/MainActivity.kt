package com.subfly.captions

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    private lateinit var prefs: Prefs
    private lateinit var statusText: TextView
    private lateinit var serverUrl: EditText
    private lateinit var apiToken: EditText
    private lateinit var language: EditText
    private lateinit var kodiHost: EditText
    private lateinit var kodiPort: EditText
    private lateinit var kodiUser: EditText
    private lateinit var kodiPass: EditText

    private val projectionRequest =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK && result.data != null) {
                saveFields()
                val intent = Intent(this, CaptureService::class.java).apply {
                    putExtra(CaptureService.EXTRA_RESULT_CODE, result.resultCode)
                    putExtra(CaptureService.EXTRA_RESULT_DATA, result.data)
                }
                startForegroundService(intent)
                statusText.text = "Running"
            } else {
                Toast.makeText(
                    this,
                    "Capture permission denied — captions can't start without it",
                    Toast.LENGTH_LONG,
                ).show()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        prefs = Prefs(this)

        statusText = findViewById(R.id.statusText)
        serverUrl = findViewById(R.id.serverUrl)
        apiToken = findViewById(R.id.apiToken)
        language = findViewById(R.id.language)
        kodiHost = findViewById(R.id.kodiHost)
        kodiPort = findViewById(R.id.kodiPort)
        kodiUser = findViewById(R.id.kodiUser)
        kodiPass = findViewById(R.id.kodiPass)

        loadFields()

        findViewById<Button>(R.id.grantOverlayButton).setOnClickListener { requestOverlayPermission() }
        findViewById<Button>(R.id.startButton).setOnClickListener { startCaptions() }
        findViewById<Button>(R.id.stopButton).setOnClickListener { stopCaptions() }
    }

    override fun onResume() {
        super.onResume()
        statusText.text = if (Settings.canDrawOverlays(this)) {
            "Overlay permission granted — ready"
        } else {
            "Step 1: grant overlay permission first"
        }
    }

    private fun loadFields() {
        serverUrl.setText(prefs.serverUrl)
        apiToken.setText(prefs.apiToken)
        language.setText(prefs.language)
        kodiHost.setText(prefs.kodiHost)
        kodiPort.setText(prefs.kodiPort.toString())
        kodiUser.setText(prefs.kodiUser)
        kodiPass.setText(prefs.kodiPass)
    }

    private fun saveFields() {
        prefs.serverUrl = serverUrl.text.toString().trim()
        prefs.apiToken = apiToken.text.toString().trim()
        prefs.language = language.text.toString().trim().ifEmpty { "en" }
        prefs.kodiHost = kodiHost.text.toString().trim().ifEmpty { "127.0.0.1" }
        prefs.kodiPort = kodiPort.text.toString().toIntOrNull() ?: 8080
        prefs.kodiUser = kodiUser.text.toString().trim()
        prefs.kodiPass = kodiPass.text.toString()
    }

    private fun requestOverlayPermission() {
        if (Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Overlay permission already granted", Toast.LENGTH_SHORT).show()
            return
        }
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:$packageName"),
        )
        startActivity(intent)
    }

    private fun startCaptions() {
        if (!Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Grant overlay permission first", Toast.LENGTH_LONG).show()
            return
        }
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) {
            Toast.makeText(
                this,
                "Live audio capture needs Android 10 (Q) or newer",
                Toast.LENGTH_LONG,
            ).show()
            return
        }
        saveFields()
        val mpm = getSystemService(MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        projectionRequest.launch(mpm.createScreenCaptureIntent())
    }

    private fun stopCaptions() {
        val intent = Intent(this, CaptureService::class.java).setAction(CaptureService.ACTION_STOP)
        startService(intent)
        statusText.text = "Stopped"
    }
}
