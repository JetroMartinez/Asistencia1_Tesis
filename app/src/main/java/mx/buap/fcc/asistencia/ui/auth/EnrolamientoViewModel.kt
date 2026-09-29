package mx.buap.fcc.asistencia.ui.auth

import android.app.Application
import android.util.Log
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mx.buap.fcc.asistencia.data.AuthApi
import mx.buap.fcc.asistencia.data.Instalacion
import mx.buap.fcc.asistencia.data.LlaveDispositivo
import mx.buap.fcc.asistencia.data.ResultadoAuth
import mx.buap.fcc.asistencia.data.SessionStore
import java.security.GeneralSecurityException
import java.security.ProviderException

data class EnrolamientoUiState(
    val enrolando: Boolean = true,
    val error: String? = null,
    /** Enrolamiento confirmado; la pantalla pasa al escaner. */
    val listo: Boolean = false,
    /** Aviso para la pantalla de login; al fijarse, la pantalla regresa al login. */
    val avisoSalida: String? = null,
)

/**
 * Enrola este dispositivo tras un login con alcance "completo"
 * (docs/decisiones.md, 2026-09-29). Solo marca `enrolado` en SessionStore cuando el
 * servidor respondio 201 y la huella de la llave coincide; cualquier falla deja la
 * sesion sin enrolar y la pantalla ofrece reintentar. Reintentar es seguro: la llave
 * se reutiliza y el servidor reemplaza el dispositivo activo.
 */
class EnrolamientoViewModel(application: Application) : AndroidViewModel(application) {

    private val sessionStore = SessionStore(application)
    private val api = AuthApi()

    private val _state = MutableStateFlow(EnrolamientoUiState())
    val state: StateFlow<EnrolamientoUiState> = _state.asStateFlow()

    init {
        enrolar()
    }

    fun onReintentar() {
        if (_state.value.enrolando) return
        enrolar()
    }

    fun onCerrarSesion() {
        sessionStore.borrar()
        _state.update { it.copy(avisoSalida = AVISO_SESION_CERRADA) }
    }

    private fun enrolar() {
        val sesion = sessionStore.sesionVigente()
        if (sesion == null) {
            sessionStore.borrar()
            _state.update { it.copy(avisoSalida = CambiarPasswordViewModel.AVISO_SESION_EXPIRADA) }
            return
        }
        _state.update { it.copy(enrolando = true, error = null) }

        viewModelScope.launch {
            val app = getApplication<Application>()
            val llave = try {
                // Generar en StrongBox puede tardar; fuera del hilo principal
                withContext(Dispatchers.Default) {
                    val estado = LlaveDispositivo.obtenerOCrear(app)
                    estado to LlaveDispositivo.llavePublicaDerBase64()
                }
            } catch (e: Exception) {
                // KeyStoreException, ProviderException, GeneralSecurityException, etc.
                Log.e(TAG, "No se pudo generar o leer la llave del dispositivo", e)
                _state.update { it.copy(enrolando = false, error = mensajeLlave(e)) }
                return@launch
            }
            val (estado, llavePublica) = llave
            val huella = Instalacion.huellaDispositivo(app)

            when (val resultado = api.registrarDispositivo(sesion.token, llavePublica, huella)) {
                is ResultadoAuth.Exito -> {
                    if (resultado.valor != estado.huellaLlave) {
                        Log.e(
                            TAG,
                            "huella_llave no coincide: servidor=${resultado.valor} " +
                                "local=${estado.huellaLlave}",
                        )
                        _state.update { it.copy(enrolando = false, error = MENSAJE_HUELLA) }
                    } else {
                        sessionStore.marcarEnrolado(resultado.valor)
                        _state.update { it.copy(enrolando = false, listo = true) }
                    }
                }
                ResultadoAuth.SesionInvalida -> {
                    sessionStore.borrar()
                    _state.update {
                        it.copy(
                            enrolando = false,
                            avisoSalida = CambiarPasswordViewModel.AVISO_SESION_EXPIRADA,
                        )
                    }
                }
                else -> _state.update { it.copy(enrolando = false, error = mensajePara(resultado)) }
            }
        }
    }

    private fun mensajeLlave(e: Exception): String = when (e) {
        is ProviderException, is GeneralSecurityException ->
            "No se pudo crear la llave de seguridad de este teléfono. Intenta de nuevo."
        else -> "Error al preparar la llave de seguridad. Intenta de nuevo."
    }

    private fun mensajePara(resultado: ResultadoAuth<*>): String = when (resultado) {
        is ResultadoAuth.Rechazado -> resultado.mensaje
        ResultadoAuth.SinConexion -> "No se pudo conectar con el servidor. Revisa tu conexión."
        is ResultadoAuth.ErrorServidor -> "Error del servidor (código ${resultado.codigo})."
        else -> "Error inesperado."
    }

    companion object {
        private const val TAG = "Enrolamiento"
        const val AVISO_SESION_CERRADA = "Cerraste sesión."
        private const val MENSAJE_HUELLA =
            "El servidor registró una llave distinta a la de este teléfono. Intenta de nuevo."
    }
}
