package com.example.asistencia

import android.Manifest
import android.annotation.SuppressLint
import android.content.pm.PackageManager
import android.graphics.Bitmap
import androidx.compose.runtime.*
import androidx.compose.material3.*
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
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
import java.io.IOException


// ===========================================================
//                PANTALLA PRINCIPAL DEL QR
// ===========================================================
@SuppressLint("ContextCastToActivity")
@Composable
fun QRScannerScreen() {

    val context = LocalContext.current
    val activity = LocalContext.current as? android.app.Activity


    var scannedUrl by remember { mutableStateOf<String?>(null) }
    var message by remember { mutableStateOf("") }

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
        Spacer(Modifier.height(40.dp))

        Box(Modifier.weight(1f)) {
            CameraPreview { url ->
                if (scannedUrl == null) {
                    scannedUrl = url
                    message = "Enviando…"

                    enviarAsistencia(context, url) { ok ->
                        if (ok) {
                            message = "Asistencia registrada"

                            activity?.finish()

                        } else {
                            message = "Error al registrar"
                        }
                    }

                }
            }
        }

        Spacer(Modifier.height(10.dp))
        Text(message)
    }
}


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
fun enviarAsistencia(
    context: android.content.Context,
    url: String,
    callback: (Boolean) -> Unit
) {
    val name = UserPrefs.getName(context)
    val matricula = UserPrefs.getMatricula(context)

    val client = OkHttpClient()

    val form = FormBody.Builder()
        .add("nombre", name)
        .add("matricula", matricula)
        .build()

    val request = Request.Builder()
        .url(url)
        .post(form)
        .build()

    client.newCall(request).enqueue(object : Callback {

        override fun onFailure(call: Call, e: IOException) {
            callback(false)
        }

        override fun onResponse(call: Call, response: Response) {
            callback(response.isSuccessful)
        }
    })
}
