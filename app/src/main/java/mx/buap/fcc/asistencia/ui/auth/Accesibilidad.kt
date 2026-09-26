package mx.buap.fcc.asistencia.ui.auth

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics

enum class TipoMensaje { ERROR, INFO }

/**
 * Mensaje de estado que TalkBack anuncia al aparecer o cambiar, sin mover el foco.
 * Los errores interrumpen (Assertive); carga y avisos esperan su turno (Polite).
 */
@Composable
fun MensajeEstado(texto: String, tipo: TipoMensaje, modifier: Modifier = Modifier) {
    val color = when (tipo) {
        TipoMensaje.ERROR -> MaterialTheme.colorScheme.error
        TipoMensaje.INFO -> MaterialTheme.colorScheme.onBackground
    }
    Text(
        text = texto,
        color = color,
        style = MaterialTheme.typography.bodyLarge,
        modifier = modifier
            .fillMaxWidth()
            .semantics {
                liveRegion = when (tipo) {
                    TipoMensaje.ERROR -> LiveRegionMode.Assertive
                    TipoMensaje.INFO -> LiveRegionMode.Polite
                }
            },
    )
}
