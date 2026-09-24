 # Decisiones técnicas — Sistema de Asistencia CU2-BUAP

Bitácora de decisiones de diseño y su justificación. Cada entrada explica qué se
decidió, qué alternativas se consideraron, por qué se descartaron, y qué límites
quedan conocidos y sin resolver. Este archivo es material directo de la tesis: debe
poder defenderse línea por línea ante el jurado.

---

## 2026-09-12 — Cierre del hueco de identidad en el canje de asistencia

### Modelo de amenazas

Cuatro perfiles de atacante, su capacidad real, y qué parte del diseño (detallado en
las secciones siguientes) lo detiene o no. Los mecanismos en sí se explican una sola
vez en "Decisión"; aquí solo se cruzan contra cada perfil.

| Perfil | Capacidad | Qué lo detiene | Qué no detiene |
|---|---|---|---|
| Compañero sin conocimientos técnicos | Conoce o adivina la matrícula de otro alumno (casi información pública en el salón); no programa ni usa herramientas de red | No conoce la contraseña de la cuenta ajena, y aunque la consiguiera, canjear con un dispositivo distinto exige enrolarlo — lo cual desactiva el dispositivo real del dueño y queda registrado | Si la contraseña se comparte voluntariamente, o si alcanza a reclamar la cuenta durante la ventana de exposición del alta (ver "Límites conocidos") |
| Atacante con `curl` o script directo, sin presencia física ni credenciales | Lee la URL del QR, manda peticiones HTTP arbitrarias, puede intentar fuerza bruta de contraseñas | No tiene ninguna contraseña válida ni la llave privada de ningún dispositivo enrolado — no puede producir ni un `Bearer` ni una `X-SIGNATURE` válidos. El límite de intentos de `/login` frena la fuerza bruta; el candado de un solo uso frena el replay de un token capturado | Nada del canje en sí — este es el perfil para el que está pensado el diseño completo |
| Dispositivo rooteado (el del propio alumno, u otro comprometido) | Lectura de memoria y almacenamiento del proceso de la app — puede extraer cualquier valor que la app misma pueda leer | La llave privada EC nunca existe como bytes legibles fuera de Keystore [PENDIENTE: citas] — al contrario del secreto HMAC simétrico descartado, que sí sería extraíble así (razón original del cambio de diseño, ver "Alternativas") | Root no impide *usar* la capacidad de firmar mientras la app sigue instalada y autorizada en ese dispositivo (p. ej. mediante instrumentación en tiempo de ejecución) — Keystore protege la extracción del material de la llave, no el uso indebido de la operación de firma desde el mismo dispositivo ya enrolado. Queda como límite residual, no se resuelve en esta tarea |
| Préstamo consciente con presencia física | Acceso legítimo a una contraseña real y, opcionalmente, al teléfono ya enrolado de otra persona | Nada lo impide técnicamente — ver "Matiz importante" (más abajo, en "Decisión") y "Límites conocidos" para el mecanismo de disuasión con rastro | El préstamo en sí; solo se penaliza con la pérdida del enrolamiento propio y quedar registrado, no se bloquea de forma preventiva |

### Contexto

La sección 5 de `CLAUDE.md` identifica el hueco principal del sistema: el HMAC de
`GET /get_token` protege quién puede *pedir* un token (el proyector `visor.py`), pero
no protege quién puede *canjearlo*. En el flujo real (`backend/server.py`), la ruta
`/` acepta `POST` con `nombre` y `matricula` como texto libre en `checkin_form.html`,
sin verificarlos contra nada, y los graba en el nodo `(:Token)` de Neo4j vía
`update_token_used`. La app Android (`QRScannerScreen.kt`, función
`enviarAsistencia()`) hace exactamente lo mismo que un navegador: arma un `FormBody`
con `nombre`/`matricula` leídos de `UserPrefs` (texto plano) y hace `POST` directo a
la URL que trae el QR. Nada distingue esa petición de un `curl` hecho desde fuera del
aula con una matrícula inventada.

Se separó el problema en dos preguntas independientes que el hueco original mezclaba:

1. **¿Quién es la persona?** — no resuelto en absoluto hoy; se resuelve con
   credencial.
2. **¿La petición salió del dispositivo correcto?** — tampoco resuelto hoy, y no lo
   resuelve por sí solo un simple token de sesión, porque un token es una cadena de
   texto copiable y reproducible con `curl`.

### Decisión

**Identidad (¿quién?):** cuentas propias del sistema (`matricula` + contraseña,
nodo `Alumno` en Neo4j), no integración con un proveedor de identidad institucional
(fuera de alcance). Login emite un token de sesión firmado (mismo formato HMAC que ya
usa el proyecto), con **una sola sesión activa por alumno**: el hash del token vigente
se guarda en `Alumno.sesion_token_hash` y cada login lo sobrescribe, revocando de
inmediato cualquier sesión anterior de esa matrícula. Vigencia de punto de partida:
8 horas.

**Origen del dispositivo (¿desde dónde?):** par de llaves EC P-256 generado dentro de
Android Keystore, llave privada no exportable. La app firma cada canje
(`SHA256withECDSA`) con esa llave; el servidor verifica con la llave pública
registrada (biblioteca `cryptography`, ya dependencia del proyecto por el uso de
RSA/X.509 en `reporte4.py`). El mensaje firmado es `f"{timestamp}/asistencia:{token_qr}"`
— incluye la ruta del endpoint, igual convención que ya usa `/get_token`
(`f"{timestamp}/get_token"`), y además el `token_qr`, para que la firma quede atada a
ese canje específico y no sea reutilizable con otro token dentro de la misma ventana
de tiempo. Política de un dispositivo activo por alumno: enrolar uno nuevo desactiva
el anterior — responde a la vez a la revocación (teléfono perdido/robado) y al cambio
de teléfono (ver más abajo).

**Señal de anomalía, no bloqueo (¿algo raro?):** la huella de dispositivo se registra
en todo intento, aceptado o no, pero nunca decide por sí sola si algo se acepta.
Alimenta el conjunto de datos de detección por reglas de la sección 9 de `CLAUDE.md`.
Dos reglas concretas quedaron especificadas (a nivel de qué datos capturar, no de
implementación): (a) una misma huella canjeando tokens de varias matrículas distintas
en la misma sesión de clase — patrón de asistencia por proxy con un solo teléfono;
(b) una matrícula que aparece desde una huella distinta a la de su dispositivo
activo — puede ser legítimo (cambio de teléfono) o sospechoso si se repite con
frecuencia inusual.

**Cambio obligatorio de contraseña en el primer login, verificado por el servidor:**
el nodo `Alumno` nace con `debe_cambiar_password: true`. Mientras esa bandera esté
activa, `/login` solo entrega un token de **alcance limitado**, válido únicamente para
llamar a `POST /cambiar_password` — cualquier otro endpoint lo rechaza por su campo
`alcance`, sin depender de que la app muestre o no la pantalla correspondiente.

**Límite de intentos en `/login`:** contadores atómicos en Neo4j
(`(:BloqueoLogin {clave, conteo, primer_intento, bloqueado_hasta})`), uno por
matrícula y uno por IP. El contador por IP solo cuenta intentos fallidos contra
matrículas **sin `Dispositivo` activo** — la población realmente vulnerable durante
la ventana de exposición del primer login (ver abajo) — para no disparar el umbral
con el tráfico normal de un salón completo saliendo por el mismo NAT del campus.
Umbrales de punto de partida: 5 fallidos en 15 min por matrícula, 50 fallidos en
15 min por IP (población filtrada); se ajustan con datos reales del banco de pruebas.

**Alta de cuentas:** extensión aditiva de `excel_ver/app.py` — al cargar la lista del
grupo, se genera por alumno un código inicial **aleatorio** (no la matrícula) cuyo
hash se guarda como `password_hash`; la lista de códigos se exporta aparte para
entrega manual del docente y no se commitea (mismo tratamiento que
`uploads_excel/`/`resultados_excel/` en `.gitignore`).

**Desfase de reloj:** el `X-TIMESTAMP` de la firma ECDSA lo genera el teléfono del
alumno, así que —a diferencia del token de `/get_token`, generado y verificado
íntegramente por el servidor— el desfase de reloj del dispositivo sí importa aquí.
Se corrige activamente: `POST /login` devuelve `hora_servidor`; la app mide el tiempo
de ida y vuelta de esa misma petición (`t0` antes de enviarla, `t1` al recibir la
respuesta), estima el retraso de red como `(t1-t0)/2`, y calcula
`desfase = hora_servidor - (t0 + (t1-t0)/2)`. Cada canje usa
`hora_local + desfase` como `X-TIMESTAMP`. La ventana de tolerancia del servidor se
amplía de los 30s de `/get_token` (entorno controlado, PC de aula con NTP) a 60s
(teléfono de alumno, sin esa garantía), para cubrir el margen de error de la medición
sin abrir una ventana tan amplia que facilite un replay tardío.

### Extensión del esquema de Neo4j (aditiva, no se rehace nada existente)

```
(:Token {token, used, warnings, nombre, matricula, ip, date, cookie})   ← sin cambios

(:Alumno {matricula, nombre, password_hash, debe_cambiar_password,
          sesion_token_hash, sesion_expira_en, creado_en})
     -[:USA]->
(:Dispositivo {llave_publica, creado_en, activo})

(:BloqueoLogin {clave, conteo, primer_intento, bloqueado_hasta})

(:Alumno)-[:REGISTRO {ip, date, cookie, huella_dispositivo}]->(:Token {...})
```

Ninguna de las queries existentes (`get_token_status`, `increment_token_warnings`,
`update_token_used`) se modifica; los nodos y relaciones nuevos se agregan alrededor.

### Alternativas consideradas y por qué se descartaron

| Alternativa | Por qué se descartó |
|---|---|
| Secreto HMAC simétrico por instalación (en vez de par de llaves EC) | Reutilizaba literalmente la verificación ya existente de `/get_token`, pero un secreto simétrico es un valor que la propia app puede leer en memoria para firmar — extraíble en un dispositivo rooteado, lo que permitiría reproducir el canje con `curl` sin volver a tocar la app. Se documenta como posible comparación experimental futura (latencia HMAC vs. ECDSA) si el tiempo lo permite. |
| Contraseña inicial = la propia matrícula | La matrícula de un compañero es prácticamente información pública dentro del salón (listas, credenciales, pizarrón); usarla como contraseña no protege nada durante la ventana de exposición entre el alta de la cuenta y el primer login, que es justo el riesgo que había que reducir. |
| Bloqueo de intentos de login basado en archivo JSONL (reutilizando el patrón de `consultas_bloqueadas.jsonl` de `reporte4.py`) | Ese patrón, correcto para lo que protege hoy (una consulta de reporte por IP), tiene condiciones de carrera al leer y reescribir un archivo compartido bajo peticiones concurrentes, y competiría por I/O de disco justo con las pruebas de 60-90 peticiones simultáneas de la sección 9. |
| Contadores de login en memoria del proceso Flask | Viable bajo el modelo de `eventlet` (greenlets cooperativos, no hilos con condiciones de carrera reales), pero se pierde en cada reinicio/despliegue y es más difícil de defender ante el jurado que la atomicidad de una transacción de Neo4j, que es una propiedad conocida y citable. |
| Umbral de login por IP sin distinguir población (15 fallidos/15 min, sin filtro) | Un salón entero sale por el mismo NAT del campus; ese umbral se dispara con tráfico normal y con el propio banco de ataques de la sección 9 durante las pruebas de carga. Se corrigió filtrando el contador de IP a solo matrículas sin dispositivo activo y subiendo el umbral sobre esa población más pequeña. |
| Requerir solo `Authorization: Bearer` para bloquear el flujo web/`curl` | Un token de sesión es una cadena de texto reproducible fuera de la app (tráfico capturado, dispositivo rooteado, backup). No prueba origen de dispositivo, solo posesión de un valor copiable. |

### Límites conocidos, documentados en vez de ocultados

- **Préstamo consciente de credencial + dispositivo entre dos personas presentes:**
  ningún mecanismo técnico lo impide por completo. La política de un dispositivo
  activo por alumno le pone un costo real (enrolar el dispositivo de otro desactiva
  el propio, y el evento queda registrado con marca de tiempo y huella distinta a la
  histórica), pero es disuasión con rastro, no un bloqueo preventivo. Cerrarlo del
  todo requeriría biometría, fuera del alcance de esta tesis.
- **Ventana de exposición en el alta de cuentas:** entre generar los códigos
  iniciales y que cada alumno haga su primer login, la cuenta existe pero nadie la ha
  reclamado. Sin una fuente de identidad institucional (fuera de alcance), ningún
  diseño construido desde cero garantiza que la primera persona en reclamar una cuenta
  sea su dueña legítima; solo se puede acortar la ventana repartiendo los códigos en
  persona, en la misma sesión de clase en que se estrena el sistema.
- **Sin recuperación de contraseña:** un alumno que la olvide necesita intervención
  manual del docente. Aceptable dado el tamaño del grupo; queda fuera del alcance de
  esta tarea.
- **Una sola sesión activa por alumno:** si el mismo alumno inicia sesión en un
  segundo dispositivo, el primero recibe `401` en su siguiente petición. Es
  intencional (coherente con "un dispositivo activo por alumno"), no un error, y debe
  poder explicarse así ante el jurado si se pregunta "¿qué pasa si un alumno usa dos
  dispositivos a la vez?".

### Qué pasa si el alumno cambia de teléfono o reinstala la app

Inicia sesión con matrícula y contraseña en el dispositivo nuevo — esto revoca de
inmediato la sesión vieja (una sola sesión activa) y recalcula el desfase de reloj.
La app genera un par de llaves EC nuevo en el Keystore del dispositivo nuevo y lo
registra; el servidor desactiva el `Dispositivo` anterior, así que el teléfono viejo
(perdido, robado o simplemente reemplazado) deja de poder firmar canjes válidos sin
ninguna intervención manual. El evento queda registrado con marca de tiempo, dato que
alimenta la regla de anomalía de re-enrolamientos frecuentes.

### Puntos de cambio concretos (referencia para las tareas de implementación)

Cada uno de estos puntos es una tarea acotada, con su propia revisión — no se
implementan en conjunto:

1. `server.py`: `POST /login` (verifica `BloqueoLogin`, devuelve `hora_servidor`,
   responde con token limitado o completo según `debe_cambiar_password`).
2. `server.py`: `POST /cambiar_password` (token de alcance limitado).
3. `server.py`: `POST /dispositivos/registrar` (requiere `Bearer` completo).
4. `server.py`: en `process_checkin()`, verificar `Bearer` y `X-SIGNATURE` ECDSA
   antes de la lógica de `Token` existente, sin modificar esa lógica.
5. `server.py`: nodos y funciones Neo4j nuevos (`Alumno`, `Dispositivo`,
   `BloqueoLogin`) — no se editan las funciones existentes para `Token`.
6. `excel_ver/app.py`: generación de códigos iniciales y alta de `Alumno` al cargar
   la lista del grupo (extensión aditiva).
7. Registro de todo intento (rechazado o no, incluyendo login) con
   `huella_dispositivo`, `alumno_id` (si se resolvió), `sesion_id` (si aplica),
   motivo y marca de tiempo.
8. Android: login, cambio de contraseña forzado, cálculo del desfase de reloj,
   generación del par de llaves EC en Keystore, registro del dispositivo, firma
   ECDSA de cada canje.
9. Migración del token de sesión y el desfase de reloj en `UserPrefs.kt` a
   `EncryptedSharedPreferences`.
10. Restricción de `checkin_form.html`/ruta `/` por navegador (queda bloqueada de
    hecho al exigir `X-SIGNATURE` de dispositivo; conservar una ruta web de respaldo
    documentada es una decisión aparte).

---

## 2026-09-16 — Almacenamiento de contraseñas

### Decisión

El hash de contraseñas usa `werkzeug.security.generate_password_hash` /
`check_password_hash`, ya en uso en el proyecto antes de esta tarea: lo llama
`backend/scripts/sembrar_identidad.py` al generar el `password_hash` de cada
`Alumno` sintético, y ya lo usaba `backend/firma_calificaciones/app.py` para
verificar la contraseña del panel de firma de calificaciones
(`check_password_hash(ADMIN_PASSWORD_HASH, password)`, línea 1160).

Ninguna de las dos llamadas pasa el argumento `method`, así que ambas quedan en el
algoritmo por omisión de la versión instalada. Se verificó la versión real
instalada — **no la de `backend/requirements.txt`, ver "Nota" abajo** — en
`/home/jetromtz/Asistencia1_Tesis/.venv/lib/python3.14/site-packages/werkzeug-3.1.8.dist-info`:
**Werkzeug 3.1.8**. Se leyó directamente `werkzeug/security.py` de esa instalación:
desde Werkzeug 2.3 el default de `generate_password_hash` es **scrypt**
(`n=32768, r=8, p=1`), no PBKDF2 — versiones anteriores a la 2.3 usaban PBKDF2 por
omisión, así que fijar la versión real importa para no describir un algoritmo que
el código no está usando.

### Por qué Werkzeug y no `passlib` / `bcrypt` / `argon2`

No fue una comparación criptográfica desde cero: Werkzeug ya es dependencia
transitiva de Flask (cero dependencias nuevas que justificar ante el jurado), y
`werkzeug.security` ya estaba en uso en `firma_calificaciones/app.py` antes de que
existiera esta decisión, así que extender el mismo módulo a `sembrar_identidad.py`
mantiene un solo mecanismo de hash en todo el proyecto en lugar de dos.

### Limitación

Scrypt con los parámetros por omisión de Werkzeug es una opción razonable, pero
OWASP recomienda Argon2id por delante de scrypt como primera opción para hash de
contraseñas nuevas. Además, `check_password_hash` no señala si un hash quedó
desactualizado (por ejemplo, tras subir los parámetros de costo en una versión
futura de Werkzeug), por lo que no hay una ruta de re-hash automático al iniciar
sesión; y el esquema no soporta *pepper* (un secreto adicional guardado fuera de la
base de datos). Ninguna de las cuentas creadas hasta ahora es de un alumno real
(ver sección 6 de `CLAUDE.md`), así que esta limitación no expone datos reales
todavía, pero debe resolverse o quedar explícitamente aceptada antes de sembrar
cuentas con matrículas reales.

### Nota: `backend/requirements.txt` no fija esta dependencia

Al verificar la versión, se encontró que `backend/requirements.txt` no lista Flask
ni Werkzeug — su contenido (`Glances`, `ufw`, `nftables`, `btrfsutil`, `pyalpm`,
`VapourSynth`, entre otros) corresponde a paquetes del Python de sistema de
CachyOS, no a un entorno virtual propio del proyecto. La versión citada arriba se
verificó contra el `.venv` real del proyecto, no contra ese archivo. Esto es una
limitación de trazabilidad de dependencias — no se corrige aquí porque excede el
alcance de esta tarea, pero queda anotado porque cualquier medición o defensa que
cite versiones de paquetes a partir de `requirements.txt` hoy partiría de un dato
incorrecto.

---

## 2026-09-23 — Límite verificado: sin cambio voluntario de contraseña tras el primero obligatorio

### Contexto

Extiende la decisión de identidad del 2026-09-12: `POST /login` emite `alcance`
según `debe_cambiar_password` (`server.py`, línea 187) — `"cambiar_password"`
mientras esté en `true`, `"completo"` en cuanto pasa a `false`. `verificar_token_sesion`
exige coincidencia exacta de alcance (`alcance != alcance_requerido`, línea 228), y
`POST /cambiar_password` llama a esa verificación pidiendo literalmente
`"cambiar_password"` (línea 248), sin aceptar `"completo"` como alternativa.

### Verificación empírica (curl, 2026-09-23, matrícula sintética SIM0001)

1. `POST /login` con la contraseña inicial → responde `alcance: "cambiar_password"`.
2. `POST /cambiar_password` con ese token → `200`, contraseña actualizada,
   `invalidar_sesion` revoca el token usado.
3. `POST /login` de nuevo, ya con la contraseña nueva → responde
   `alcance: "completo"`, `debe_cambiar_password: false`.
4. `POST /cambiar_password` con el token de alcance `"completo"` → `403`:

   ```
   {"error":"Alcance insuficiente para este endpoint"}
   ```

### Consecuencia

Tras el primer cambio obligatorio, el alumno no tiene forma de cambiar su
contraseña por voluntad propia: todo intento contra `/cambiar_password` con una
sesión normal (`alcance: "completo"`) se rechaza con `403`. Esto se suma al límite
ya aceptado el 2026-09-12 ("Sin recuperación de contraseña") — ahora ni siquiera
existe la ruta de cambio voluntario sin haber olvidado nada, solo la del cambio
forzoso del primer login.

### Fuera de alcance

Por el congelamiento de código del 12 de octubre de 2026 (sección 1 de
`CLAUDE.md`), no se implementa aquí. Queda como trabajo futuro documentado, no
como fallo oculto.

### Solución propuesta (no implementada)

Aceptar también `alcance == "completo"` en `/cambiar_password`, exigiendo en ese
caso la contraseña actual en el cuerpo de la petición y verificándola con
`check_password_hash` antes de aplicar el cambio — igual que ya hace el propio
endpoint para rechazar que la contraseña nueva sea igual a la actual (línea 259).
Así el cambio voluntario queda autenticado por posesión de la contraseña vigente,
no solo por el alcance del token, y no se abre una puerta para que un token de
sesión robado cambie la contraseña sin conocerla.

---

## 2026-09-23 — `POST /dispositivos/registrar` (punto de cambio 3)

### Decisión

El endpoint exige `Authorization: Bearer` con `verificar_token_sesion(token, "completo")`:
un token de alcance `"cambiar_password"` recibe `403`, así que no se puede enrolar un
dispositivo antes del cambio obligatorio de contraseña. El cuerpo JSON trae
`llave_publica` y `huella_dispositivo`; la escritura la hace
`identidad.registrar_dispositivo`, que en una sola transacción desactiva el
`Dispositivo` activo anterior y crea el nuevo.

**Validación de la llave antes de guardarla** (`cargar_llave_publica_p256`, con
`cryptography`, ya dependencia por `reporte4.py`): se acepta PEM o DER en base64
estricto (`b64decode(..., validate=True)`). DER base64 es el formato natural de la
app, porque `KeyStore` entrega `publicKey.encoded` como DER X.509
SubjectPublicKeyInfo. La llave solo se acepta si es `EllipticCurvePublicKey` sobre
`SECP256R1`; RSA, Ed25519, otras curvas (p. ej. P-384), base64 o PEM corruptos y
puntos que no están sobre la curva (OpenSSL los rechaza al cargar) responden `400`.
`huella_dispositivo` es obligatoria y tiene un tope de 256 caracteres, para no
guardar cadenas arbitrarias en el grafo.

**Normalización:** la llave se guarda siempre re-serializada como PEM
SubjectPublicKeyInfo, llegue como llegue. Así la verificación ECDSA del canje (punto
de cambio 4) lee un solo formato y la misma llave no queda en Neo4j con dos
representaciones distintas. La respuesta `201` incluye `huella_llave` (los primeros
16 caracteres hexadecimales de SHA-256 del DER) para que la app y los registros
puedan confirmar qué llave quedó enrolada sin devolverla completa.

**Diff aditivo:** no se modificaron `process_checkin`, `/get_token`, las funciones
de `Token` ni `identidad.py`. La lectura del `Bearer` se duplicó (4 líneas) en vez
de extraerse a una función común, porque extraerla obligaba a modificar
`/cambiar_password`.

### Verificación

`backend/tests/probar_registro_dispositivo.py`, con el `test_client` de Flask contra
el Neo4j real y el alumno sintético SIM0001. La salida está en
`docs/evidencias/registro_dispositivo_2026-09-23.txt`: 17/17 verificaciones correctas,
incluyendo que el dispositivo anterior queda `activo: false`, que solo queda uno
activo y que los rechazos no alteran el dispositivo activo. El script emite el token
de sesión con el mismo formato que `/login` en lugar de llamar a `/login`, porque la
contraseña de SIM0001 se cambió en la verificación del 2026-09-23; la verificación de
firma, expiración, alcance y sesión vigente sí se ejercita completa.

### Límites conocidos

- **Los rechazos no se registran todavía.** Los `400`/`401`/`403` de este endpoint
  aún no dejan rastro; eso corresponde al punto de cambio 7.
- **Carrera entre dos registros simultáneos de la misma matrícula:** bajo aislamiento
  *read committed* de Neo4j, dos transacciones concurrentes pueden desactivar cada una
  solo el dispositivo activo que ven y crear cada una el suyo, dejando dos
  `Dispositivo` activos. Solo ocurre si el mismo alumno enrola dos veces en el mismo
  instante; cerrarlo requiere tocar `identidad.registrar_dispositivo` (p. ej. tomar
  primero un candado de escritura sobre el nodo `Alumno`). Queda como trabajo futuro.
- **Una misma llave pública enrolada por dos matrículas distintas no se bloquea.**
  Es una señal de proxy, coherente con el principio de "señal, no bloqueo": queda
  para las reglas de anomalía de la sección 9 de `CLAUDE.md`.
- **Corrección del esquema del 2026-09-12:** `identidad.registrar_dispositivo`
  guarda también `huella_dispositivo` en el nodo; el esquema real es
  `(:Dispositivo {llave_publica, huella_dispositivo, creado_en, activo})`.
