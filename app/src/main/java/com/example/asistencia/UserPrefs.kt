package com.example.asistencia   // ← IMPORTANTE: usa EXACTAMENTE este package

import android.content.Context

object UserPrefs {

    private const val PREFS_NAME = "asistencias_prefs"
    private const val KEY_NAME = "name"
    private const val KEY_MATRICULA = "matricula"

    fun saveUser(context: Context, name: String, matricula: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit()
            .putString(KEY_NAME, name)
            .putString(KEY_MATRICULA, matricula)
            .apply()
    }

    fun getName(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_NAME, "") ?: ""
    }

    fun getMatricula(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_MATRICULA, "") ?: ""
    }

    fun hasUser(context: Context): Boolean {
        return getName(context).isNotEmpty() && getMatricula(context).isNotEmpty()
    }
}
