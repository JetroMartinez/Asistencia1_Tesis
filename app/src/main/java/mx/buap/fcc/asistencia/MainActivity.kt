package mx.buap.fcc.asistencia

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import mx.buap.fcc.asistencia.data.SessionStore
import mx.buap.fcc.asistencia.ui.auth.CambiarPasswordViewModel
import mx.buap.fcc.asistencia.ui.theme.Asistencia1Theme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val sessionStore = SessionStore(this)
        val sesion = sessionStore.sesionVigente()

        // Habia una sesion guardada pero ya expiro: se descarta y se avisa
        val avisoInicial = if (sesion == null && sessionStore.leer() != null) {
            sessionStore.borrar()
            CambiarPasswordViewModel.AVISO_SESION_EXPIRADA
        } else {
            null
        }

        val startDestination = when {
            sesion == null -> Rutas.LOGIN
            sesion.alcance == SessionStore.ALCANCE_CAMBIAR_PASSWORD -> Rutas.CAMBIAR_PASSWORD
            // Sesion completa sin enrolar (p. ej. la app se cerro a la mitad): se reintenta
            !sessionStore.estaEnrolado() -> Rutas.ENROLAMIENTO
            else -> Rutas.ESCANER
        }

        setContent {
            Asistencia1Theme {
                AppNavHost(startDestination = startDestination, avisoInicial = avisoInicial)
            }
        }
    }
}
