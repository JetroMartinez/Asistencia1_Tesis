package mx.buap.fcc.asistencia.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun EnrolamientoScreen(
    onListo: () -> Unit,
    onSalir: (aviso: String) -> Unit,
    viewModel: EnrolamientoViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsState()

    LaunchedEffect(state.listo) {
        if (state.listo) onListo()
    }
    LaunchedEffect(state.avisoSalida) {
        state.avisoSalida?.let(onSalir)
    }

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "Registrando este teléfono",
                style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold),
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.semantics { heading() },
            )
            Text(
                text = "Este teléfono quedará como tu dispositivo para registrar asistencia. " +
                    "Si tenías otro registrado, dejará de funcionar.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onBackground,
            )

            if (state.enrolando) {
                CircularProgressIndicator(
                    modifier = Modifier
                        .size(48.dp)
                        .semantics { contentDescription = "Registrando teléfono" },
                )
                MensajeEstado(texto = "Registrando teléfono…", tipo = TipoMensaje.INFO)
            }

            state.error?.let { MensajeEstado(texto = it, tipo = TipoMensaje.ERROR) }

            if (!state.enrolando && state.error != null) {
                Button(
                    onClick = viewModel::onReintentar,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(min = 48.dp),
                ) {
                    Text("Reintentar", style = MaterialTheme.typography.titleMedium)
                }
            }

            TextButton(
                onClick = viewModel::onCerrarSesion,
                enabled = !state.enrolando,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp),
            ) {
                Text("Cerrar sesión")
            }
        }
    }
}
