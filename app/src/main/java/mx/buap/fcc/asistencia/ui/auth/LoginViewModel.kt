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

/** A donde lleva un login exitoso, segun el alcance del token. */
enum class DestinoLogin { CAMBIAR_PASSWORD, ESCANER }

data class LoginUiState(
    val matricula: String = "",
    val password: String = "",
    val passwordVisible: Boolean = false,
    val cargando: Boolean = false,
    val error: String? = null,
    val destino: DestinoLogin? = null,
) {
    val puedeEnviar: Boolean
        get() = !cargando && matricula.isNotBlank() && password.isNotEmpty()
}

class LoginViewModel(application: Application) : AndroidViewModel(application) {

    private val sessionStore = SessionStore(application)
    private val api = AuthApi()

    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun onMatriculaChange(valor: String) = _state.update { it.copy(matricula = valor, error = null) }

    fun onPasswordChange(valor: String) = _state.update { it.copy(password = valor, error = null) }

    fun onTogglePasswordVisible() = _state.update { it.copy(passwordVisible = !it.passwordVisible) }

    fun onLogin() {
        val actual = _state.value
        if (!actual.puedeEnviar) return
        _state.update { it.copy(cargando = true, error = null) }

        viewModelScope.launch {
            val resultado = api.login(actual.matricula.trim(), actual.password)
            _state.update { estado ->
                when (resultado) {
                    is ResultadoAuth.Exito -> {
                        sessionStore.guardar(resultado.valor)
                        val destino =
                            if (resultado.valor.alcance == SessionStore.ALCANCE_CAMBIAR_PASSWORD) {
                                DestinoLogin.CAMBIAR_PASSWORD
                            } else {
                                DestinoLogin.ESCANER
                            }
                        estado.copy(cargando = false, password = "", destino = destino)
                    }
                    else -> estado.copy(cargando = false, error = mensajePara(resultado))
                }
            }
        }
    }

    /** La pantalla ya navego; evita repetir la navegacion al recomponer. */
    fun onNavegado() = _state.update { it.copy(destino = null) }

    private fun mensajePara(resultado: ResultadoAuth<*>): String = when (resultado) {
        ResultadoAuth.CredencialesInvalidas -> "Matrícula o contraseña incorrectas."
        ResultadoAuth.Bloqueado ->
            "Demasiados intentos fallidos. Espera 15 minutos e intenta de nuevo."
        ResultadoAuth.SinConexion -> "No se pudo conectar con el servidor. Revisa tu conexión."
        is ResultadoAuth.Rechazado -> resultado.mensaje
        is ResultadoAuth.ErrorServidor -> "Error del servidor (código ${resultado.codigo})."
        ResultadoAuth.SesionInvalida, is ResultadoAuth.Exito -> "Error inesperado."
    }
}
