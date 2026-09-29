package mx.buap.fcc.asistencia

import android.os.Build
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
import java.security.Signature
import java.security.interfaces.ECPublicKey
import java.security.spec.X509EncodedKeySpec

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

    private fun llavePublica() = KeyFactory.getInstance("EC").generatePublic(
        X509EncodedKeySpec(Base64.decode(LlaveDispositivo.llavePublicaDerBase64(), Base64.NO_WRAP)),
    )
}
