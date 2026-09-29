package mx.buap.fcc.asistencia.data

import android.os.SystemClock
import android.util.Log
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mx.buap.fcc.asistencia.BuildConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlin.math.roundToLong

/** Resultado de una llamada a los endpoints de identidad del servidor. */
sealed interface ResultadoAuth<out T> {
    data class Exito<T>(val valor: T) : ResultadoAuth<T>
    /** 401 en /login */
    data object CredencialesInvalidas : ResultadoAuth<Nothing>
    /** 429 en /login: bloqueo por intentos fallidos */
    data object Bloqueado : ResultadoAuth<Nothing>
    /** 401/403 con Bearer: sesion expirada, revocada o de alcance incorrecto */
    data object SesionInvalida : ResultadoAuth<Nothing>
    /** 400 con el mensaje que devolvio el servidor */
    data class Rechazado(val mensaje: String) : ResultadoAuth<Nothing>
    data object SinConexion : ResultadoAuth<Nothing>
    data class ErrorServidor(val codigo: Int) : ResultadoAuth<Nothing>
}

/**
 * Cliente de POST /login, POST /cambiar_password y POST /dispositivos/registrar.
 * Solo habla con BuildConfig.BASE_URL.
 */
class AuthApi(private val client: OkHttpClient = clienteCompartido) {

    /**
     * Inicia sesion y mide el desfase de reloj con la misma peticion
     * (docs/decisiones.md, 2026-09-12):
     *   desfase = hora_servidor - (t0 + (t1 - t0) / 2)
     * t0 es la hora de pared al enviar; el viaje (t1 - t0) se mide con el reloj
     * monotonico para que un ajuste de hora durante la peticion no lo altere.
     */
    suspend fun login(matricula: String, password: String): ResultadoAuth<Sesion> =
        withContext(Dispatchers.IO) {
            val cuerpo = JSONObject()
                .put("matricula", matricula)
                .put("password", password)
            val request = Request.Builder()
                .url("${BuildConfig.BASE_URL}/login")
                .post(cuerpo.toString().toRequestBody(JSON))
                .build()

            val t0Pared = System.currentTimeMillis()
            val t0Mono = SystemClock.elapsedRealtime()
            try {
                client.newCall(request).execute().use { response ->
                    // t1: respuesta recibida, antes de leer y parsear el cuerpo
                    val viajeMs = SystemClock.elapsedRealtime() - t0Mono
                    val texto = response.body?.string().orEmpty()

                    when (response.code) {
                        200 -> {
                            val json = JSONObject(texto)
                            val horaServidorMs = (json.getDouble("hora_servidor") * 1000).roundToLong()
                            val desfase = horaServidorMs - (t0Pared + viajeMs / 2)
                            if (BuildConfig.DEBUG) {
                                Log.d(TAG, "Desfase de reloj: $desfase ms (viaje $viajeMs ms)")
                            }
                            ResultadoAuth.Exito(
                                Sesion(
                                    token = json.getString("token"),
                                    alcance = json.getString("alcance"),
                                    expiraEn = json.getDouble("expira_en"),
                                    desfaseRelojMs = desfase,
                                    matricula = matricula,
                                )
                            )
                        }
                        400 -> ResultadoAuth.Rechazado(mensajeError(texto))
                        401 -> ResultadoAuth.CredencialesInvalidas
                        429 -> ResultadoAuth.Bloqueado
                        else -> ResultadoAuth.ErrorServidor(response.code)
                    }
                }
            } catch (e: IOException) {
                ResultadoAuth.SinConexion
            } catch (e: JSONException) {
                ResultadoAuth.ErrorServidor(200)
            }
        }

    /** Cambio obligatorio de contrasena con el token de alcance "cambiar_password". */
    suspend fun cambiarPassword(token: String, passwordNuevo: String): ResultadoAuth<Unit> =
        withContext(Dispatchers.IO) {
            val cuerpo = JSONObject().put("password_nuevo", passwordNuevo)
            val request = Request.Builder()
                .url("${BuildConfig.BASE_URL}/cambiar_password")
                .header("Authorization", "Bearer $token")
                .post(cuerpo.toString().toRequestBody(JSON))
                .build()
            try {
                client.newCall(request).execute().use { response ->
                    val texto = response.body?.string().orEmpty()
                    when (response.code) {
                        200 -> ResultadoAuth.Exito(Unit)
                        400 -> ResultadoAuth.Rechazado(mensajeError(texto))
                        401, 403 -> ResultadoAuth.SesionInvalida
                        else -> ResultadoAuth.ErrorServidor(response.code)
                    }
                }
            } catch (e: IOException) {
                ResultadoAuth.SinConexion
            }
        }

    /**
     * Enrola la llave publica de este dispositivo con el token de alcance "completo".
     * El servidor desactiva el dispositivo activo anterior. Devuelve `huella_llave`.
     */
    suspend fun registrarDispositivo(
        token: String,
        llavePublica: String,
        huellaDispositivo: String,
    ): ResultadoAuth<String> =
        withContext(Dispatchers.IO) {
            val cuerpo = JSONObject()
                .put("llave_publica", llavePublica)
                .put("huella_dispositivo", huellaDispositivo)
            val request = Request.Builder()
                .url("${BuildConfig.BASE_URL}/dispositivos/registrar")
                .header("Authorization", "Bearer $token")
                .post(cuerpo.toString().toRequestBody(JSON))
                .build()
            try {
                client.newCall(request).execute().use { response ->
                    val texto = response.body?.string().orEmpty()
                    when (response.code) {
                        201 -> ResultadoAuth.Exito(JSONObject(texto).getString("huella_llave"))
                        400 -> ResultadoAuth.Rechazado(mensajeError(texto))
                        401, 403 -> ResultadoAuth.SesionInvalida
                        else -> ResultadoAuth.ErrorServidor(response.code)
                    }
                }
            } catch (e: IOException) {
                ResultadoAuth.SinConexion
            } catch (e: JSONException) {
                ResultadoAuth.ErrorServidor(201)
            }
        }

    private fun mensajeError(texto: String): String =
        try {
            JSONObject(texto).optString("error").ifBlank { "Solicitud rechazada." }
        } catch (e: JSONException) {
            "Solicitud rechazada."
        }

    companion object {
        private const val TAG = "AuthApi"
        private val JSON = "application/json; charset=utf-8".toMediaType()

        private val clienteCompartido: OkHttpClient by lazy {
            OkHttpClient.Builder()
                .connectTimeout(15, TimeUnit.SECONDS)
                .readTimeout(15, TimeUnit.SECONDS)
                .writeTimeout(15, TimeUnit.SECONDS)
                .build()
        }
    }
}
