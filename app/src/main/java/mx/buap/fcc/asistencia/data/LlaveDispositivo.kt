package mx.buap.fcc.asistencia.data

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyInfo
import android.security.keystore.KeyProperties
import android.security.keystore.StrongBoxUnavailableException
import android.util.Base64
import android.util.Log
import java.security.KeyFactory
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.PublicKey
import java.security.Signature
import java.security.spec.ECGenParameterSpec

/**
 * Par de llaves EC P-256 del dispositivo en Android Keystore (docs/decisiones.md,
 * 2026-09-12 y 2026-09-29).
 *
 * La llave privada se genera dentro de Keystore y nunca sale de ahi: la app solo
 * tiene un manejador [PrivateKey] con el que pide firmas; AndroidKeyStore no entrega
 * los bytes del material de la llave. La publica se envia a /dispositivos/registrar.
 *
 * Se pide StrongBox (en el Pixel 9a, el chip Titan M2) cuando el dispositivo lo
 * anuncia; si no esta disponible, se genera en el TEE. El nivel obtenido se registra
 * en el log con la etiqueta [TAG].
 */
object LlaveDispositivo {

    const val ALIAS = "llave_dispositivo_asistencia"
    private const val PROVEEDOR = "AndroidKeyStore"
    private const val TAG = "LlaveDispositivo"

    /** Resultado de [obtenerOCrear]. */
    data class Estado(
        val nueva: Boolean,
        /** null si la llave ya existia: no se sabe con que se pidio. */
        val strongBoxSolicitado: Boolean?,
        val respaldoATee: Boolean,
        val nivelSeguridad: String,
        val huellaLlave: String,
    )

    private fun keyStore(): KeyStore = KeyStore.getInstance(PROVEEDOR).apply { load(null) }

    fun existe(): Boolean = keyStore().containsAlias(ALIAS)

    /**
     * Genera el par solo si el alias no existe; si ya existe, lo reutiliza para que la
     * llave publica sea estable por instalacion. Puede tardar (StrongBox): llamar
     * fuera del hilo principal.
     */
    fun obtenerOCrear(context: Context): Estado {
        var strongBoxSolicitado: Boolean? = null
        var respaldoATee = false
        val nueva = !existe()

        if (nueva) {
            val tieneStrongBox = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P &&
                context.packageManager.hasSystemFeature(PackageManager.FEATURE_STRONGBOX_KEYSTORE)
            strongBoxSolicitado = tieneStrongBox
            if (tieneStrongBox) {
                try {
                    generar(strongBox = true)
                } catch (e: StrongBoxUnavailableException) {
                    Log.w(TAG, "StrongBox no disponible, se genera en el TEE", e)
                    respaldoATee = true
                    generar(strongBox = false)
                }
            } else {
                generar(strongBox = false)
            }
        }

        val estado = Estado(
            nueva = nueva,
            strongBoxSolicitado = strongBoxSolicitado,
            respaldoATee = respaldoATee,
            nivelSeguridad = nivelSeguridad(),
            huellaLlave = huellaLlave(),
        )
        // Sin datos personales: solo propiedades de la llave. Material de la tesis.
        Log.i(
            TAG,
            "llave=${if (nueva) "nueva" else "reutilizada"} " +
                "strongbox_solicitado=${strongBoxSolicitado ?: "n/a"} " +
                "respaldo_tee=$respaldoATee nivel=${estado.nivelSeguridad} " +
                "huella_llave=${estado.huellaLlave} api=${Build.VERSION.SDK_INT} " +
                "modelo=${Build.MODEL}",
        )
        return estado
    }

    private fun generar(strongBox: Boolean) {
        val spec = KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256)
            .setUserAuthenticationRequired(false)
            .apply {
                if (strongBox && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                    setIsStrongBoxBacked(true)
                }
            }
            .build()
        KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, PROVEEDOR).run {
            initialize(spec)
            generateKeyPair()
        }
    }

    private fun llavePublica(): PublicKey =
        keyStore().getCertificate(ALIAS)?.publicKey
            ?: throw IllegalStateException("No existe la llave $ALIAS")

    private fun llavePrivada(): PrivateKey =
        keyStore().getKey(ALIAS, null) as? PrivateKey
            ?: throw IllegalStateException("No existe la llave $ALIAS")

    /** Llave publica X.509 SubjectPublicKeyInfo (DER) en base64, sin saltos de linea. */
    fun llavePublicaDerBase64(): String =
        Base64.encodeToString(llavePublica().encoded, Base64.NO_WRAP)

    /**
     * Primeros 16 hexadecimales de SHA-256 del DER, igual que la `huella_llave` que
     * devuelve /dispositivos/registrar.
     */
    fun huellaLlave(): String =
        MessageDigest.getInstance("SHA-256")
            .digest(llavePublica().encoded)
            .joinToString("") { "%02x".format(it) }
            .take(16)

    /** Firma SHA256withECDSA; devuelve la firma DER en base64, como la espera el servidor. */
    fun firmar(mensaje: ByteArray): String {
        val firma = Signature.getInstance("SHA256withECDSA").run {
            initSign(llavePrivada())
            update(mensaje)
            sign()
        }
        return Base64.encodeToString(firma, Base64.NO_WRAP)
    }

    /**
     * Donde vive la llave segun KeyInfo. Lo reporta el propio cliente; el servidor no
     * puede verificarlo sin Key Attestation (ver docs/decisiones.md, 2026-09-29).
     */
    fun nivelSeguridad(): String {
        val privada = llavePrivada()
        val info = KeyFactory.getInstance(privada.algorithm, PROVEEDOR)
            .getKeySpec(privada, KeyInfo::class.java)
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            when (info.securityLevel) {
                KeyProperties.SECURITY_LEVEL_STRONGBOX -> "STRONGBOX"
                KeyProperties.SECURITY_LEVEL_TRUSTED_ENVIRONMENT -> "TRUSTED_ENVIRONMENT"
                KeyProperties.SECURITY_LEVEL_SOFTWARE -> "SOFTWARE"
                KeyProperties.SECURITY_LEVEL_UNKNOWN_SECURE -> "UNKNOWN_SECURE"
                else -> "UNKNOWN"
            }
        } else {
            @Suppress("DEPRECATION")
            if (info.isInsideSecureHardware) "HARDWARE_LEGACY" else "SOFTWARE"
        }
    }

    /** Solo para pruebas: borra el par del Keystore. */
    fun borrar() {
        keyStore().deleteEntry(ALIAS)
    }
}
