package mx.buap.fcc.asistencia

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.os.Build
import android.os.SystemClock
import android.util.Log
import android.view.HapticFeedbackConstants
import android.view.View
import androidx.compose.runtime.*
import androidx.compose.material3.*
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.core.*
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.compose.foundation.background
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.viewinterop.AndroidView
import com.google.mlkit.vision.barcode.BarcodeScanning
import com.google.mlkit.vision.common.InputImage
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import mx.buap.fcc.asistencia.data.LlaveDispositivo
import mx.buap.fcc.asistencia.data.SessionStore
import org.json.JSONObject
import java.io.IOException
import java.util.Locale
import java.util.concurrent.TimeUnit


// ===========================================================
//                PANTALLA PRINCIPAL DEL QR
// ===========================================================
@Composable
fun QRScannerScreen(
    onCerrarSesion: () -> Unit,
    onSesionInvalida: (aviso: String) -> Unit,
) {

    val context = LocalContext.current
    val view = LocalView.current
    val scope = rememberCoroutineScope()


    var scannedUrl by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf("") }
    var esError by remember { mutableStateOf(false) }
    var puedeReintentar by remember { mutableStateOf(false) }
    var confirmarSalida by remember { mutableStateOf(false) }

    fun mostrarError(texto: String) {
        vibrar(view, exito = false)
        esError = true
        message = texto
        puedeReintentar = true
    }

    // Cierre de sesion solo local: no borra la llave de Keystore ni la huella de
    // instalacion, para que el siguiente login re-enrole la misma llave.
    if (confirmarSalida) {
        AlertDialog(
            onDismissRequest = { confirmarSalida = false },
            title = { Text("¿Cerrar sesión?") },
            text = { Text("Tendrás que volver a iniciar sesión para registrar asistencia.") },
            confirmButton = {
                TextButton(
                    onClick = {
                        confirmarSalida = false
                        SessionStore(context).borrar()
                        onCerrarSesion()
                    },
                    modifier = Modifier.heightIn(min = 48.dp),
                ) { Text("Cerrar sesión") }
            },
            dismissButton = {
                TextButton(
                    onClick = { confirmarSalida = false },
                    modifier = Modifier.heightIn(min = 48.dp),
                ) { Text("Cancelar") }
            },
        )
    }

    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (!granted) message = "Permiso de cámara denegado"
    }

    val hasPermission =
        ContextCompat.checkSelfPermission(context, Manifest.permission.CAMERA) ==
                PackageManager.PERMISSION_GRANTED

    LaunchedEffect(Unit) {
        if (!hasPermission) {
            permissionLauncher.launch(Manifest.permission.CAMERA)
        }
    }

    Column(
        modifier = Modifier.fillMaxSize().padding(0.dp)
            .background(Color.Black),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Text("Escanea el QR", style = MaterialTheme.typography.headlineSmall.copy(fontWeight = FontWeight.Bold),color = Color.White)
        TextButton(
            onClick = { confirmarSalida = true },
            modifier = Modifier
                .align(Alignment.End)
                .heightIn(min = 48.dp)
                .semantics { contentDescription = "Cerrar sesión y volver al inicio de sesión" },
        ) {
            Text("Cerrar sesión", color = Color.White)
        }
        Spacer(Modifier.height(40.dp))

        Box(Modifier.weight(1f)) {
            CameraPreview { url ->
                if (scannedUrl == null) {
                    scannedUrl = url
                    esError = false
                    message = "Enviando…"

                    scope.launch {
                        when (val resultado = enviarAsistencia(context, url)) {
                            // Sin finish(): cerrar la app cortaria el anuncio de TalkBack
                            ResultadoCanje.Exito -> {
                                vibrar(view, exito = true)
                                message = "Asistencia registrada"
                            }
                            // Iniciar sesion de nuevo renueva el token, re-enrola la llave
                            // y recalcula el desfase de reloj: corrige cualquier causa
                            is ResultadoCanje.NoAutorizado, ResultadoCanje.SinDispositivo -> {
                                vibrar(view, exito = false)
                                SessionStore(context).borrar()
                                onSesionInvalida(AVISO_REINICIAR_SESION)
                            }
                            ResultadoCanje.TokenUsado -> mostrarError(
                                "Este código ya se usó. Espera el código nuevo y escanéalo."
                            )
                            ResultadoCanje.TokenInvalido -> mostrarError(
                                "El código no es válido para registrar asistencia."
                            )
                            ResultadoCanje.SinConexion -> mostrarError(
                                "No se pudo conectar con el servidor. Revisa tu conexión."
                            )
                            is ResultadoCanje.ErrorServidor -> mostrarError(
                                "Error del servidor (código ${resultado.codigo})."
                            )
                            ResultadoCanje.ErrorLlave -> mostrarError(
                                "No se pudo firmar con la llave de este teléfono. Intenta de nuevo."
                            )
                        }
                    }

                }
            }
        }

        Spacer(Modifier.height(10.dp))
        // TalkBack anuncia cada cambio sin mover el foco; los errores interrumpen
        Text(
            text = message,
            color = Color.White,
            style = MaterialTheme.typography.bodyLarge,
            modifier = Modifier
                .padding(horizontal = 16.dp)
                .semantics {
                    liveRegion = if (esError) LiveRegionMode.Assertive else LiveRegionMode.Polite
                },
        )
        if (puedeReintentar) {
            Button(
                onClick = {
                    puedeReintentar = false
                    esError = false
                    message = ""
                    scannedUrl = null
                },
                modifier = Modifier
                    .padding(16.dp)
                    .fillMaxWidth()
                    .heightIn(min = 48.dp)
                    .semantics { contentDescription = "Escanear de nuevo el código QR" },
            ) {
                Text("Escanear de nuevo")
            }
        }
    }
}

private const val AVISO_REINICIAR_SESION =
    "Tu sesión o el registro de este teléfono ya no son válidos. Inicia sesión de nuevo."


@Composable
fun CameraPreview(onQrDetected: (String) -> Unit) {

    val context = LocalContext.current

    AndroidView(factory = { ctx ->
        val previewView = PreviewView(ctx)

        val cameraProviderFuture = ProcessCameraProvider.getInstance(ctx)

        cameraProviderFuture.addListener({

            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder().build().apply {
                setSurfaceProvider(previewView.surfaceProvider)
            }

            val scanner = BarcodeScanning.getClient()

            val analysis = ImageAnalysis.Builder()
                .setOutputImageFormat(ImageAnalysis.OUTPUT_IMAGE_FORMAT_RGBA_8888)
                .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
                .build()


            analysis.setAnalyzer(ContextCompat.getMainExecutor(ctx)) { imageProxy ->

                val bitmap = imageProxy.toBitmap()  // ⭐ NUNCA usa imageProxy.image

                val image = InputImage.fromBitmap(bitmap, imageProxy.imageInfo.rotationDegrees)

                scanner.process(image)
                    .addOnSuccessListener { codes ->
                        for (code in codes) {
                            val value = code.rawValue ?: ""
                            if (value.contains("token=")) {
                                onQrDetected(value)
                            }
                        }
                    }
                    .addOnCompleteListener {
                        imageProxy.close()
                    }
            }

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    ctx as androidx.lifecycle.LifecycleOwner,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    analysis
                )
            } catch (e: Exception) {
                e.printStackTrace()
            }

        }, ContextCompat.getMainExecutor(ctx))

        previewView
    })
}



// ===========================================================
//        EXTENSIÓN → ImageProxy → Bitmap (SIN EXPERIMENTAL)
// ===========================================================
fun ImageProxy.toBitmap(): Bitmap {

    val buffer = planes[0].buffer
    val bytes = ByteArray(buffer.capacity())
    buffer.get(bytes)

    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    bitmap.copyPixelsFromBuffer(java.nio.ByteBuffer.wrap(bytes))
    return bitmap
}



// ===========================================================
//       ENVÍO AUTOMÁTICO DE ASISTENCIA AL SERVIDOR
// ===========================================================

/** Resultado del canje, segun el codigo de process_checkin (docs/decisiones.md, 2026-09-30). */
sealed interface ResultadoCanje {
    /** 200 */
    data object Exito : ResultadoCanje
    /** 401: sesion expirada o revocada, firma invalida o timestamp fuera de ventana */
    data class NoAutorizado(val mensaje: String) : ResultadoCanje
    /** 403: no hay dispositivo activo (otro telefono se enrolo) o alcance incorrecto */
    data object SinDispositivo : ResultadoCanje
    /** 409 token_reutilizado */
    data object TokenUsado : ResultadoCanje
    /** 404, o QR sin token */
    data object TokenInvalido : ResultadoCanje
    data object SinConexion : ResultadoCanje
    data class ErrorServidor(val codigo: Int) : ResultadoCanje
    /** Keystore no pudo firmar */
    data object ErrorLlave : ResultadoCanje
}

private const val TAG_LLAVE = "LlaveDispositivo"

private val clienteCanje: OkHttpClient by lazy {
    OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .writeTimeout(15, TimeUnit.SECONDS)
        .build()
}

/** Se consulta una vez por proceso, solo para acompañar la medicion en el log. */
private val nivelLlave: String by lazy {
    runCatching { LlaveDispositivo.nivelSeguridad() }.getOrDefault("DESCONOCIDO")
}

/**
 * Canje firmado. El servidor verifica, antes de tocar el token:
 * Authorization: Bearer, X-TIMESTAMP (±60 s) y X-SIGNATURE, una firma ECDSA de
 * "{timestamp}/asistencia:{token_qr}" con la llave del dispositivo activo.
 */
suspend fun enviarAsistencia(
    context: android.content.Context,
    qrContent: String,
): ResultadoCanje {
    // Del QR solo se toma el token; host, esquema y ruta se ignoran para que
    // un QR falso no pueda redirigir los datos del alumno a otro servidor.
    val token = android.net.Uri.parse(qrContent).getQueryParameter("token")
    if (token.isNullOrBlank()) return ResultadoCanje.TokenInvalido

    val url = "${BuildConfig.BASE_URL}/".toHttpUrl().newBuilder()
        .addQueryParameter("token", token)
        .build()

    // La identidad la da la sesion; el servidor toma nombre y matricula del nodo Alumno.
    val sessionStore = SessionStore(context)
    val sesion = sessionStore.sesionVigente()
        ?: return ResultadoCanje.NoAutorizado("Sesión expirada")

    // Hora del servidor estimada con el desfase medido en el login, en segundos enteros
    // como la parsea verificar_canje.
    val timestamp = sessionStore.ahoraServidorMs() / 1000
    val mensaje = "$timestamp/asistencia:$token".toByteArray()

    // Firmar en StrongBox tarda; fuera del hilo principal (el analizador de CameraX
    // entrega el QR en el hilo principal).
    val firma = try {
        withContext(Dispatchers.Default) {
            val inicio = SystemClock.elapsedRealtimeNanos()
            val firma = LlaveDispositivo.firmar(mensaje)
            val ms = (SystemClock.elapsedRealtimeNanos() - inicio) / 1_000_000.0
            // Sin datos personales ni el token: material de la tesis
            Log.i(TAG_LLAVE, "canje firma_ms=${"%.1f".format(Locale.US, ms)} nivel=$nivelLlave")
            firma
        }
    } catch (e: Exception) {
        Log.e(TAG_LLAVE, "No se pudo firmar el canje", e)
        return ResultadoCanje.ErrorLlave
    }

    val request = Request.Builder()
        .url(url)
        .header("Authorization", "Bearer ${sesion.token}")
        .header("X-TIMESTAMP", timestamp.toString())
        .header("X-SIGNATURE", firma)
        .post(FormBody.Builder().build())
        .build()

    return withContext(Dispatchers.IO) {
        try {
            clienteCanje.newCall(request).execute().use { response ->
                val texto = response.body?.string().orEmpty()
                when (response.code) {
                    200 -> ResultadoCanje.Exito
                    401 -> ResultadoCanje.NoAutorizado(
                        runCatching { JSONObject(texto).optString("error") }.getOrDefault("")
                    )
                    403 -> ResultadoCanje.SinDispositivo
                    404 -> ResultadoCanje.TokenInvalido
                    409 -> ResultadoCanje.TokenUsado
                    else -> ResultadoCanje.ErrorServidor(response.code)
                }
            }
        } catch (e: IOException) {
            ResultadoCanje.SinConexion
        }
    }
}

/** Háptica diferenciada; respeta el ajuste de "respuesta táctil" del sistema. */
private fun vibrar(view: View, exito: Boolean) {
    val constante = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
        if (exito) HapticFeedbackConstants.CONFIRM else HapticFeedbackConstants.REJECT
    } else {
        if (exito) HapticFeedbackConstants.CONTEXT_CLICK else HapticFeedbackConstants.LONG_PRESS
    }
    view.performHapticFeedback(constante)
}
