package com.example.asistencia

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import com.example.asistencia.ui.theme.Asistencia1Theme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        setContent {
            Asistencia1Theme {

                val context = LocalContext.current
                var registrado by remember { mutableStateOf(UserPrefs.hasUser(context)) }

                if (!registrado) {
                    // Sólo la primera vez
                    RegisterScreen {
                        registrado = true
                    }
                } else {
                    // Aquí irá el QR Scanner
                    QRScannerScreen()
                }
            }
        }
    }
}
