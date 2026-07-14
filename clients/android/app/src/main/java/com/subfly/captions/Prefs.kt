package com.subfly.captions

import android.content.Context
import android.content.SharedPreferences

/** Thin wrapper around SharedPreferences for all user-configurable settings. */
class Prefs(context: Context) {
    private val sp: SharedPreferences =
        context.getSharedPreferences("subfly_prefs", Context.MODE_PRIVATE)

    var serverUrl: String
        get() = sp.getString(KEY_SERVER_URL, "http://192.168.1.50:8765") ?: ""
        set(value) = sp.edit().putString(KEY_SERVER_URL, value).apply()

    var apiToken: String
        get() = sp.getString(KEY_API_TOKEN, "") ?: ""
        set(value) = sp.edit().putString(KEY_API_TOKEN, value).apply()

    var language: String
        get() = sp.getString(KEY_LANGUAGE, "en") ?: "en"
        set(value) = sp.edit().putString(KEY_LANGUAGE, value).apply()

    var kodiHost: String
        get() = sp.getString(KEY_KODI_HOST, "127.0.0.1") ?: "127.0.0.1"
        set(value) = sp.edit().putString(KEY_KODI_HOST, value).apply()

    var kodiPort: Int
        get() = sp.getInt(KEY_KODI_PORT, 8080)
        set(value) = sp.edit().putInt(KEY_KODI_PORT, value).apply()

    var kodiUser: String
        get() = sp.getString(KEY_KODI_USER, "") ?: ""
        set(value) = sp.edit().putString(KEY_KODI_USER, value).apply()

    var kodiPass: String
        get() = sp.getString(KEY_KODI_PASS, "") ?: ""
        set(value) = sp.edit().putString(KEY_KODI_PASS, value).apply()

    companion object {
        private const val KEY_SERVER_URL = "server_url"
        private const val KEY_API_TOKEN = "api_token"
        private const val KEY_LANGUAGE = "language"
        private const val KEY_KODI_HOST = "kodi_host"
        private const val KEY_KODI_PORT = "kodi_port"
        private const val KEY_KODI_USER = "kodi_user"
        private const val KEY_KODI_PASS = "kodi_pass"
    }
}
