package mx.buap.fcc.asistencia.ui.auth

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import mx.buap.fcc.asistencia.data.AuthApi
import mx.buap.fcc.asistencia.data.ResultadoAuth
import mx.buap.fcc.asistencia.data.SessionStore

/** Igual que LONGITUD_MINIMA_PASSWORD en backend/server.py */
const val LONGITUD_MINIMA_PASSWORD = 12

data class CambiarPasswordUiState(
    val passwordNuevo: String = "",
    val confirmacion: String = "",
    val passwordVisible: Boolean = false,
    val cargando: Boolean = false,
    val error: String? = null,
    /** Aviso para la pantalla de login; al fijarse, la pantalla regresa al login. */
    val avisoSalida: String? = null,
) {
    val longitudSuficiente: Boolean
        get() = passwordNuevo.length >= LONGITUD_MINIMA_PASSWORD

    val coinciden: Boolean
        get() = passwordNuevo == confirmacion

    val puedeEnviar: Boolean
        get() = !cargando && longitudSuficiente && coinciden
}

class CambiarPasswordViewModel(application: Application) : AndroidViewModel(application) {

    private val sessionStore = SessionStore(application)
    private val api = AuthApi()

    private val _state = MutableStateFlow(CambiarPasswordUiState())
    val state: StateFlow<CambiarPasswordUiState> = _state.asStateFlow()

    fun onPasswordNuevoChange(valor: String) =
        _state.update { it.copy(passwordNuevo = valor, error = null) }

    fun onConfirmacionChange(valor: String) =
        _state.update { it.copy(confirmacion = valor, error = null) }

    fun onTogglePasswordVisible() = _state.update { it.copy(passwordVisible = !it.passwordVisible) }

    fun onCambiar() {
        val actual = _state.value
        if (!actual.puedeEnviar) return

        val sesion = sessionStore.leer()
        if (sesion == null) {
            _state.update { it.copy(avisoSalida = AVISO_SESION_EXPIRADA) }
            return
        }
        _state.update { it.copy(cargando = true, error = null) }

        viewModelScope.launch {
            val resultado = api.cambiarPassword(sesion.token, actual.passwordNuevo)
            // En 200 el servidor invalida la sesion; en 401/403 ya no sirve. En ambos
            // casos se borra la local y se vuelve al login.
            when (resultado) {
                is ResultadoAuth.Exito -> {
                    sessionStore.borrar()
                    _state.update { it.copy(cargando = false, avisoSalida = AVISO_CAMBIADA) }
                }
                ResultadoAuth.SesionInvalida -> {
                    sessionStore.borrar()
                    _state.update { it.copy(cargando = false, avisoSalida = AVISO_SESION_EXPIRADA) }
                }
                else -> _state.update { it.copy(cargando = false, error = mensajePara(resultado)) }
            }
        }
    }

    private fun mensajePara(resultado: ResultadoAuth<*>): String = when (resultado) {
        is ResultadoAuth.Rechazado -> resultado.mensaje
        ResultadoAuth.SinConexion -> "No se pudo conectar con el servidor. Revisa tu conexión."
        is ResultadoAuth.ErrorServidor -> "Error del servidor (código ${resultado.codigo})."
        else -> "Error inesperado."
    }

    companion object {
        const val AVISO_CAMBIADA =
            "Contraseña actualizada. Inicia sesión con tu nueva contraseña."
        const val AVISO_SESION_EXPIRADA = "Tu sesión expiró. Inicia sesión de nuevo."
    }
}
