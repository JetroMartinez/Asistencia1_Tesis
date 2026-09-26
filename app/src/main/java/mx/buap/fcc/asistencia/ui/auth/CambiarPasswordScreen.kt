package mx.buap.fcc.asistencia.ui.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.semantics.error
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel

@Composable
fun CambiarPasswordScreen(
    onSalir: (aviso: String) -> Unit,
    viewModel: CambiarPasswordViewModel = viewModel(),
) {
    val state by viewModel.state.collectAsState()

    LaunchedEffect(state.avisoSalida) {
        state.avisoSalida?.let(onSalir)
    }

    val transformacion =
        if (state.passwordVisible) VisualTransformation.None else PasswordVisualTransformation()
    val errorConfirmacion =
        if (state.confirmacion.isNotEmpty() && !state.coinciden) "Las contraseñas no coinciden." else null

    Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .imePadding()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Text(
                text = "Cambia tu contraseña",
                style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold),
                color = MaterialTheme.colorScheme.onBackground,
                modifier = Modifier.semantics { heading() },
            )
            Text(
                text = "Es tu primer inicio de sesión. Elige una contraseña nueva de al menos " +
                    "$LONGITUD_MINIMA_PASSWORD caracteres para continuar.",
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onBackground,
            )

            OutlinedTextField(
                value = state.passwordNuevo,
                onValueChange = viewModel::onPasswordNuevoChange,
                label = { Text("Contraseña nueva") },
                supportingText = {
                    Text("${state.passwordNuevo.length} de $LONGITUD_MINIMA_PASSWORD caracteres mínimo")
                },
                singleLine = true,
                enabled = !state.cargando,
                visualTransformation = transformacion,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Password,
                    imeAction = ImeAction.Next,
                ),
                modifier = Modifier.fillMaxWidth(),
            )

            OutlinedTextField(
                value = state.confirmacion,
                onValueChange = viewModel::onConfirmacionChange,
                label = { Text("Confirma la contraseña nueva") },
                supportingText = errorConfirmacion?.let { { Text(it) } },
                singleLine = true,
                enabled = !state.cargando,
                isError = errorConfirmacion != null,
                visualTransformation = transformacion,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Password,
                    imeAction = ImeAction.Done,
                ),
                keyboardActions = KeyboardActions(onDone = { viewModel.onCambiar() }),
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { errorConfirmacion?.let { error(it) } },
            )

            TextButton(
                onClick = viewModel::onTogglePasswordVisible,
                modifier = Modifier
                    .heightIn(min = 48.dp)
                    .align(Alignment.End)
                    .semantics {
                        contentDescription =
                            if (state.passwordVisible) "Ocultar contraseñas" else "Mostrar contraseñas"
                    },
            ) {
                Text(if (state.passwordVisible) "Ocultar" else "Mostrar")
            }

            state.error?.let { MensajeEstado(texto = it, tipo = TipoMensaje.ERROR) }
            if (state.cargando) {
                MensajeEstado(texto = "Guardando contraseña…", tipo = TipoMensaje.INFO)
            }

            Button(
                onClick = viewModel::onCambiar,
                enabled = state.puedeEnviar,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 48.dp),
            ) {
                if (state.cargando) {
                    CircularProgressIndicator(
                        strokeWidth = 2.dp,
                        modifier = Modifier
                            .size(24.dp)
                            .semantics { contentDescription = "Guardando contraseña" },
                    )
                } else {
                    Text("Guardar contraseña", style = MaterialTheme.typography.titleMedium)
                }
            }
        }
    }
}
