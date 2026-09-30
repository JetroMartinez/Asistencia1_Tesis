package mx.buap.fcc.asistencia

import android.os.Build
import android.os.SystemClock
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import mx.buap.fcc.asistencia.data.LlaveDispositivo
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.PrivateKey
import java.security.Signature
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.X509EncodedKeySpec
import java.util.Locale

/**
 * Verifica LlaveDispositivo en un dispositivo real. Borra la llave antes y despues:
 * no correr en un telefono con una sesion enrolada que se quiera conservar.
 */
@RunWith(AndroidJUnit4::class)
class LlaveDispositivoTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext

    @Before
    fun limpiar() = LlaveDispositivo.borrar()

    @After
    fun limpiarDespues() = LlaveDispositivo.borrar()

    @Test
    fun creaYReutilizaLaLlave() {
        assertFalse(LlaveDispositivo.existe())
        val primera = LlaveDispositivo.obtenerOCrear(context)
        assertTrue(primera.nueva)
        assertTrue(LlaveDispositivo.existe())
        val publica1 = LlaveDispositivo.llavePublicaDerBase64()

        val segunda = LlaveDispositivo.obtenerOCrear(context)
        assertFalse(segunda.nueva)
        assertEquals(publica1, LlaveDispositivo.llavePublicaDerBase64())
        assertEquals(primera.huellaLlave, segunda.huellaLlave)
    }

    @Test
    fun laLlavePublicaEsP256() {
        LlaveDispositivo.obtenerOCrear(context)
        val publica = llavePublica() as ECPublicKey
        assertEquals(256, publica.params.curve.field.fieldSize)
    }

    @Test
    fun laFirmaVerificaYFallaConMensajeAlterado() {
        LlaveDispositivo.obtenerOCrear(context)
        val mensaje = "1759190400/asistencia:token-de-prueba".toByteArray()
        val firma = Base64.decode(LlaveDispositivo.firmar(mensaje), Base64.NO_WRAP)

        val verificador = Signature.getInstance("SHA256withECDSA")
        verificador.initVerify(llavePublica())
        verificador.update(mensaje)
        assertTrue(verificador.verify(firma))

        verificador.initVerify(llavePublica())
        verificador.update("1759190400/asistencia:otro-token".toByteArray())
        assertFalse(verificador.verify(firma))
    }

    @Test
    fun registraElNivelDeSeguridad() {
        val estado = LlaveDispositivo.obtenerOCrear(context)
        Log.i("LlaveDispositivoTest", "nivel=${estado.nivelSeguridad} modelo=${Build.MODEL}")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            assertTrue(
                "Se esperaba respaldo de hardware, se obtuvo ${estado.nivelSeguridad}",
                estado.nivelSeguridad in setOf("STRONGBOX", "TRUSTED_ENVIRONMENT"),
            )
        }
    }

    /**
     * Latencia de firma de la llave de produccion (StrongBox si el telefono lo tiene)
     * contra una llave de prueba en el TEE con los mismos parametros. Las dos se miden
     * igual que en el canje: abrir Keystore, obtener la llave y firmar.
     * Salida en logcat con la etiqueta LatenciaFirma (docs/decisiones.md, 2026-09-30).
     */
    @Test
    fun medirLatenciaFirma() {
        val estado = LlaveDispositivo.obtenerOCrear(context)
        val mensaje = "1759190400/asistencia:0123456789abcdef0123456789abcdef".toByteArray()

        val produccion = medir { LlaveDispositivo.firmar(mensaje) }
        registrar(estado.nivelSeguridad, produccion)

        val specTee = KeyGenParameterSpec.Builder(ALIAS_TEE, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(false)
            .build()
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, "AndroidKeyStore").run {
            initialize(specTee)
            generateKeyPair()
        }
        try {
            val tee = medir {
                val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
                Signature.getInstance("SHA256withECDSA").run {
                    initSign(ks.getKey(ALIAS_TEE, null) as PrivateKey)
                    update(mensaje)
                    sign()
                }
            }
            registrar("TRUSTED_ENVIRONMENT (llave de prueba)", tee)
        } finally {
            KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(ALIAS_TEE)
        }
    }

    private fun medir(firmar: () -> Unit): List<Double> {
        repeat(CALENTAMIENTO) { firmar() }
        return List(MUESTRAS) {
            val inicio = SystemClock.elapsedRealtimeNanos()
            firmar()
            (SystemClock.elapsedRealtimeNanos() - inicio) / 1_000_000.0
        }.sorted()
    }

    private fun registrar(nivel: String, ms: List<Double>) {
        // Percentil por rango mas cercano sobre la lista ordenada
        fun p(q: Double) = ms[(Math.ceil(q * ms.size).toInt() - 1).coerceIn(0, ms.lastIndex)]
        fun f(x: Double) = "%.1f".format(Locale.US, x)
        Log.i(
            "LatenciaFirma",
            "nivel=$nivel n=${ms.size} calentamiento=$CALENTAMIENTO min=${f(ms.first())} " +
                "p50=${f(p(0.50))} p95=${f(p(0.95))} p99=${f(p(0.99))} max=${f(ms.last())} " +
                "ms modelo=${Build.MODEL} api=${Build.VERSION.SDK_INT}",
        )
    }

    private companion object {
        const val ALIAS_TEE = "llave_dispositivo_asistencia_prueba_tee"
        const val CALENTAMIENTO = 10
        const val MUESTRAS = 100
    }

    private fun llavePublica() = KeyFactory.getInstance("EC").generatePublic(
        X509EncodedKeySpec(Base64.decode(LlaveDispositivo.llavePublicaDerBase64(), Base64.NO_WRAP)),
    )
}
