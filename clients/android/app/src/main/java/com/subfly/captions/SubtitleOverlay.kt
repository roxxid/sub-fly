package com.subfly.captions

import android.content.Context
import android.graphics.Color
import android.os.Build
import android.util.TypedValue
import android.view.Gravity
import android.view.WindowManager
import android.widget.TextView

/**
 * Draws live captions in a system overlay window on top of whatever is on
 * screen (Kodi, a live TV channel, anything) using
 * TYPE_APPLICATION_OVERLAY. Requires the "draw over other apps" permission
 * (Settings.canDrawOverlays).
 */
class SubtitleOverlay(private val context: Context) {
    private val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
    private var view: TextView? = null

    fun attach() {
        if (view != null) return
        val tv = TextView(context).apply {
            setTextColor(Color.WHITE)
            setBackgroundColor(0xB0000000.toInt())
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 24f)
            gravity = Gravity.CENTER
            setPadding(24, 12, 24, 12)
            text = ""
        }
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        } else {
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_SYSTEM_ALERT
        }
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
            android.graphics.PixelFormat.TRANSLUCENT,
        ).apply {
            gravity = Gravity.BOTTOM or Gravity.CENTER_HORIZONTAL
            y = 80
        }
        windowManager.addView(tv, params)
        view = tv
    }

    fun show(text: String) {
        view?.text = text
    }

    fun clear() {
        view?.text = ""
    }

    fun detach() {
        val tv = view ?: return
        try {
            windowManager.removeView(tv)
        } catch (_: Exception) {
        }
        view = null
    }
}
