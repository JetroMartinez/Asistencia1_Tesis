package mx.buap.fcc.asistencia

import android.net.Uri
import androidx.compose.runtime.Composable
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import mx.buap.fcc.asistencia.ui.auth.CambiarPasswordScreen
import mx.buap.fcc.asistencia.ui.auth.DestinoLogin
import mx.buap.fcc.asistencia.ui.auth.LoginScreen

object Rutas {
    const val LOGIN = "login?aviso={aviso}"
    const val CAMBIAR_PASSWORD = "cambiar_password"
    const val ESCANER = "escaner"

    fun login(aviso: String) = "login?aviso=${Uri.encode(aviso)}"
}

/**
 * Sin sesion vigente: login. Alcance "cambiar_password": cambio forzado.
 * Alcance completo: escaner. MainActivity decide el destino inicial.
 */
@Composable
fun AppNavHost(
    startDestination: String,
    avisoInicial: String?,
    navController: NavHostController = rememberNavController(),
) {
    NavHost(navController = navController, startDestination = startDestination) {

        composable(
            route = Rutas.LOGIN,
            arguments = listOf(navArgument("aviso") {
                type = NavType.StringType
                nullable = true
                defaultValue = avisoInicial
            }),
        ) { entry ->
            LoginScreen(
                aviso = entry.arguments?.getString("aviso"),
                onDestino = { destino ->
                    val ruta = when (destino) {
                        DestinoLogin.CAMBIAR_PASSWORD -> Rutas.CAMBIAR_PASSWORD
                        DestinoLogin.ESCANER -> Rutas.ESCANER
                    }
                    navController.reemplazarPila(ruta)
                },
            )
        }

        composable(Rutas.CAMBIAR_PASSWORD) {
            CambiarPasswordScreen(
                onSalir = { aviso -> navController.reemplazarPila(Rutas.login(aviso)) },
            )
        }

        composable(Rutas.ESCANER) {
            QRScannerScreen()
        }
    }
}

/** Navega vaciando la pila, para que Atras no regrese a una pantalla de auth anterior. */
private fun NavHostController.reemplazarPila(ruta: String) {
    navigate(ruta) {
        popUpTo(0) { inclusive = true }
        launchSingleTop = true
    }
}
