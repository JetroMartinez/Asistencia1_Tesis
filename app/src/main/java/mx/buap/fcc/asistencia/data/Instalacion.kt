package mx.buap.fcc.asistencia.data

import android.content.Context
import java.util.UUID

/**
 * Identificador por instalacion que se envia como `huella_dispositivo`
 * (docs/decisiones.md, 2026-09-29).
 *
 * Es un UUID aleatorio creado la primera vez que se pide. Dura mientras la app este
 * instalada y cambia al reinstalarla o al borrar sus datos. No identifica el hardware.
 *
 * Por privacidad, NO se usan:
 * - El ID de publicidad: existe para rastreo publicitario entre apps.
 * - El IMEI ni el numero de serie: identifican el hardware de forma permanente, y
 *   desde API 29 exigen READ_PRIVILEGED_PHONE_STATE, que no se concede a apps normales.
 * - ANDROID_ID: sobrevive a la reinstalacion, asi que ya no seria por instalacion.
 *
 * Se guarda en un archivo aparte de la sesion cifrada, porque [SessionStore.borrar]
 * se llama en cada cierre de sesion y la huella debe sobrevivirlo. El archivo se
 * excluye del respaldo (backup_rules.xml y data_extraction_rules.xml): restaurado en
 * otro telefono, dos telefonos compartirian la huella.
 */
object Instalacion {

    // Excluido del respaldo en backup_rules.xml y data_extraction_rules.xml
    const val PREFS_NAME = "instalacion"
    private const val KEY_HUELLA = "huella_dispositivo"

    @Synchronized
    fun huellaDispositivo(context: Context): String {
        val prefs = context.applicationContext.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.getString(KEY_HUELLA, null)?.let { return it }
        val nueva = UUID.randomUUID().toString()
        // commit y no apply: la huella debe estar escrita antes de enviarse al servidor
        prefs.edit().putString(KEY_HUELLA, nueva).commit()
        return nueva
    }
}
