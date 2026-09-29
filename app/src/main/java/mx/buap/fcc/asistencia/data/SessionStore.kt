package mx.buap.fcc.asistencia.data

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

/** Sesion emitida por POST /login. */
data class Sesion(
    val token: String,
    val alcance: String,
    /** Segundos epoch segun el reloj del servidor. */
    val expiraEn: Double,
    /** hora_servidor - hora_local, en milisegundos. Ver docs/decisiones.md. */
    val desfaseRelojMs: Long,
    /** Solo para mostrar en la UI; la identidad la da el token, no este campo. */
    val matricula: String,
)

/**
 * Sesion guardada con EncryptedSharedPreferences (llave maestra en Android Keystore).
 * Reemplaza a UserPrefs, que guardaba nombre y matricula autodeclarados en claro.
 */
class SessionStore(context: Context) {

    private val appContext = context.applicationContext
    private val prefs: SharedPreferences = abrir()

    init {
        // Migracion: borra el archivo en claro de la version anterior (UserPrefs)
        appContext.deleteSharedPreferences(PREFS_LEGADO)
    }

    fun guardar(sesion: Sesion) {
        prefs.edit()
            .putString(KEY_TOKEN, sesion.token)
            .putString(KEY_ALCANCE, sesion.alcance)
            .putLong(KEY_EXPIRA_EN, sesion.expiraEn.toRawBits())
            .putLong(KEY_DESFASE, sesion.desfaseRelojMs)
            .putString(KEY_MATRICULA, sesion.matricula)
            // Sesion nueva: hay que volver a enrolar (docs/decisiones.md, 2026-09-29)
            .putBoolean(KEY_ENROLADO, false)
            .remove(KEY_HUELLA_LLAVE)
            .apply()
    }

    /** El servidor confirmo el registro de la llave de este dispositivo en esta sesion. */
    fun marcarEnrolado(huellaLlave: String) {
        prefs.edit()
            .putBoolean(KEY_ENROLADO, true)
            .putString(KEY_HUELLA_LLAVE, huellaLlave)
            .apply()
    }

    fun estaEnrolado(): Boolean = prefs.getBoolean(KEY_ENROLADO, false)

    fun leer(): Sesion? {
        val token = prefs.getString(KEY_TOKEN, null) ?: return null
        return Sesion(
            token = token,
            alcance = prefs.getString(KEY_ALCANCE, "") ?: "",
            expiraEn = Double.fromBits(prefs.getLong(KEY_EXPIRA_EN, 0L)),
            desfaseRelojMs = prefs.getLong(KEY_DESFASE, 0L),
            matricula = prefs.getString(KEY_MATRICULA, "") ?: "",
        )
    }

    fun borrar() {
        prefs.edit().clear().apply()
    }

    /** Hora del servidor estimada con el desfase medido en el ultimo login. */
    fun ahoraServidorMs(): Long =
        System.currentTimeMillis() + prefs.getLong(KEY_DESFASE, 0L)

    /** Sesion con token y aun no expirada segun la hora del servidor estimada. */
    fun sesionVigente(): Sesion? {
        val sesion = leer() ?: return null
        return if (sesion.expiraEn * 1000 > ahoraServidorMs()) sesion else null
    }

    private fun abrir(): SharedPreferences = try {
        crear()
    } catch (e: Exception) {
        // Archivo ilegible (p. ej. restaurado sin la llave de Keystore). Se descarta:
        // el alumno solo tiene que volver a iniciar sesion.
        Log.w(TAG, "Sesion cifrada ilegible, se descarta", e)
        appContext.deleteSharedPreferences(PREFS_NAME)
        crear()
    }

    private fun crear(): SharedPreferences {
        val masterKey = MasterKey.Builder(appContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            appContext,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    companion object {
        private const val TAG = "SessionStore"

        // Excluido del respaldo en backup_rules.xml y data_extraction_rules.xml
        const val PREFS_NAME = "sesion_cifrada"
        private const val PREFS_LEGADO = "asistencias_prefs"

        private const val KEY_TOKEN = "token"
        private const val KEY_ALCANCE = "alcance"
        private const val KEY_EXPIRA_EN = "expira_en"
        private const val KEY_DESFASE = "desfase_reloj_ms"
        private const val KEY_MATRICULA = "matricula"
        private const val KEY_ENROLADO = "enrolado"
        private const val KEY_HUELLA_LLAVE = "huella_llave"

        const val ALCANCE_CAMBIAR_PASSWORD = "cambiar_password"
        const val ALCANCE_COMPLETO = "completo"
    }
}
