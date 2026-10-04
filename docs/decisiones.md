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

---

## 2026-09-24 — Canje autenticado en `process_checkin` (punto de cambio 4)

### Decisión

El `POST` de `process_checkin` (ruta `/?token=...`) ahora pasa por
`verificar_canje(token_qr)` **antes** de cualquier consulta al nodo `Token`. En orden:

1. `Authorization: Bearer` con `verificar_token_sesion(token, "completo")`, reutilizada
   sin cambios (401 sin sesión o sesión revocada/expirada, 403 con alcance
   `"cambiar_password"`).
2. `X-TIMESTAMP` (entero, igual que `/get_token`) dentro de ±60 s
   (`VENTANA_CANJE_SEGUNDOS`), por el desfase de reloj del teléfono ya justificado el
   2026-09-12.
3. `X-SIGNATURE`: firma ECDSA con SHA-256 sobre `f"{timestamp}/asistencia:{token_qr}"`,
   verificada contra la llave pública del `Dispositivo` activo del alumno
   (`identidad.obtener_dispositivo_activo`, ya existente). Sin dispositivo activo → 403;
   firma inválida o base64 corrupto → 401.
4. Solo si todo pasa, continúa la lógica de siempre (`get_token_status`,
   `increment_token_warnings`, `update_token_used`, señal `new_token_signal`), con
   `nombre` y `matricula` tomados del nodo `Alumno` de la sesión autenticada. Lo que
   venga en `request.form` se ignora.

**Formato de la firma:** DER en base64, que es exactamente lo que devuelve
`Signature.getInstance("SHA256withECDSA").sign()` en Android, así la app no tiene que
convertir a formato `r||s`. La llave se lee en PEM porque `/dispositivos/registrar` la
guarda ya normalizada.

**Por qué la verificación va antes de `get_token_status`:** un `POST` rechazado no
consume el token ni incrementa `warnings`. Así `warnings` sigue significando lo mismo
que antes (reintentos sobre un token ya canjeado) y un atacante sin credenciales no
puede inflar ese contador ni "quemar" el QR que está proyectado.

**Diff sobre `process_checkin`:** un bloque de 6 líneas antes de `# Token status` y dos
líneas en la rama `POST` (`nombre`/`matricula` salen de `alumno` en lugar de
`request.form`). No se modificaron las funciones de `Token`, la rama `GET`, la cookie
ni la emisión por Socket.IO. Los errores de autenticación responden JSON, como el
resto de los endpoints de identidad, porque el cliente es la app.

### Verificación

`backend/tests/probar_canje_firmado.py` (test_client de Flask, Neo4j real, alumno
sintético SIM0001). Genera una llave P-256 local, la enrola por
`/dispositivos/registrar` y firma igual que Keystore. Salida en
`docs/evidencias/canje_firmado_2026-09-24.txt`: 8/8 verificaciones correctas.

| Caso | Resultado | Estado del token |
|---|---|---|
| Navegador: solo formulario, sin encabezados | 401 | sin usar, `warnings=0` |
| `curl` con sesión válida y sin `X-SIGNATURE` | 401 | sin usar, `warnings=0` |
| Firma de otra llave P-256 no enrolada | 401 | sin usar, `warnings=0` |
| Timestamp −120 s con firma correcta | 401 | sin usar, `warnings=0` |
| Firma válida de otro `token_qr` | 401 | sin usar, `warnings=0` |
| Firma válida, formulario con nombre/matrícula falsos | 200 | usado, con la matrícula y el nombre de la sesión |
| Replay exacto de la petición anterior | 200 (`warning.html`) | `warnings=1`, registro sin cambios |

> **Corregido el 2026-09-30:** el replay autenticado ahora responde `409`
> (`token_reutilizado`), con el mismo incremento de `warnings`. La fila se conserva
> como registro de lo verificado ese día; ver la entrada "Firma del canje en Android".

El script borra al terminar los nodos `Token` que creó, para no mezclar datos de prueba
con el conjunto de datos de la tesis. La regresión de
`probar_registro_dispositivo.py` sigue en 17/17.

### Límites conocidos

- **Los rechazos todavía no se registran:** los 401/403 del canje no dejan rastro en
  Neo4j. Corresponde al punto de cambio 7, y es necesario para las métricas de
  detección de la sección 9 de `CLAUDE.md`.
- **La rama `GET` sigue sirviendo `checkin_form.html`:** su envío ahora recibe 401, así
  que el flujo web está bloqueado en la práctica. Retirarlo o conservarlo como respaldo
  documentado es el punto de cambio 10.
- **El replay dentro de la ventana de 60 s no se bloquea criptográficamente:** una
  firma capturada solo sirve para ese mismo `token_qr`, y ese token ya se canjeó, así
  que el replay cae en la lógica de un solo uso y cuenta como `warning`. No se
  agregó un registro de nonces porque el candado de un solo uso del token ya cumple
  esa función.
- **Uso indebido de la firma desde un dispositivo rooteado ya enrolado:** sin cambios
  respecto al modelo de amenazas del 2026-09-12. Keystore impide extraer la llave, no
  impide usarla.
- **`ruff` no está instalado** en el entorno del proyecto; el formato del código nuevo
  no se verificó con esa herramienta.

---

## 2026-09-26 — Android: login, sesión cifrada y cambio de contraseña forzado (puntos de cambio 8, primera parte, y 9)

### Decisión

**Identidad en la app:** `RegisterScreen` y `UserPrefs` se retiraron. La app ya no
captura nombre ni matrícula autodeclarados; la identidad es el token que emite
`POST /login`. La matrícula se guarda solo para mostrarla en la UI; el nombre deja de
guardarse (`/login` no lo devuelve y el servidor lo toma del nodo `Alumno` en el canje).

**Almacenamiento (`data/SessionStore.kt`):** `EncryptedSharedPreferences` con una
`MasterKey` AES256-GCM en Android Keystore. Guarda `token`, `alcance`, `expira_en`,
`desfase_reloj_ms` y `matricula`. La vigencia se compara contra la hora del servidor
estimada (`hora_local + desfase`), no contra el reloj del teléfono. Al arrancar se borra
el archivo en claro de la versión anterior (`asistencias_prefs`).

**Exclusión del respaldo:** `sesion_cifrada.xml` se excluye en `backup_rules.xml` y
`data_extraction_rules.xml`. La `MasterKey` no viaja en el respaldo de Android, así que
restaurar el archivo en otro dispositivo solo produciría datos que no se pueden descifrar.
Si aun así el archivo resulta ilegible, `SessionStore` lo descarta y el alumno vuelve a
iniciar sesión.

**Desfase de reloj:** la fórmula es la del 2026-09-12,
`desfase = hora_servidor - (t0 + (t1-t0)/2)`, con una variante: `t0` es la hora de pared
al enviar, pero `t1-t0` se mide con `SystemClock.elapsedRealtime()` (reloj monotónico).
Así, un ajuste automático de hora del teléfono durante la petición no altera la
estimación del viaje. `t1` se toma al recibir la respuesta, antes de parsear el cuerpo.

**Cambio de contraseña forzado:** si `/login` devuelve `alcance: "cambiar_password"`, la
app muestra solo esa pantalla. Exige ≥12 caracteres y confirmación, con la misma regla
que `LONGITUD_MINIMA_PASSWORD` del servidor; el servidor sigue siendo quien decide. Con
`200` el servidor invalida la sesión, así que la app la borra y regresa al login con un
aviso.

**Red fuera de Composables:** `AuthApi` (OkHttp, `suspend` en `Dispatchers.IO`) y un
`ViewModel` por pantalla. Los Composables solo leen `StateFlow` y llaman a funciones del
`ViewModel`.

**Accesibilidad:** etiquetas en todos los campos, `error()` semántico en campos con
error, encabezados marcados con `heading()`, áreas táctiles de 48 dp mínimo,
`contentDescription` en el indicador de carga y en el botón de mostrar contraseña, y
mensajes de estado en *live regions* (`Assertive` para errores, `Polite` para carga y
avisos), que TalkBack anuncia sin mover el foco. Los colores salen de
`MaterialTheme.colorScheme` en vez del `Color.Black` fijo de `RegisterScreen`.

### Límites conocidos

- **El canje sigue respondiendo 401:** `enviarAsistencia` ya manda `Authorization: Bearer`
  y dejó de mandar nombre y matrícula, pero falta `X-SIGNATURE`. Se resuelve en la
  siguiente tarea (llaves EC en Keystore, `/dispositivos/registrar` y firma del canje).
- **`security-crypto` está deprecada** por Google desde 1.1.0. Funciona y cubre lo que
  se necesita; la alternativa futura es Keystore + DataStore directo.
- **Háptica diferenciada pendiente:** va con el canje, donde hay un éxito o error real
  que distinguir.
- **Sin verificación en dispositivo todavía:** esta entrada se escribió con la
  compilación de debug y release verificada, pero sin dispositivo conectado. Faltan la
  prueba manual contra el servidor local, la inspección de `shared_prefs` y la pasada
  con TalkBack.

---

## 2026-09-29 — Android: enrolamiento del dispositivo (punto de cambio 8, segunda parte)

### Decisión

**Par de llaves (`data/LlaveDispositivo.kt`):** EC P-256 generado dentro de Android
Keystore con `KeyGenParameterSpec.Builder(ALIAS, PURPOSE_SIGN)`,
`ECGenParameterSpec("secp256r1")`, `DIGEST_SHA256` y
`setUserAuthenticationRequired(false)`. El alias es fijo
(`llave_dispositivo_asistencia`) y la llave se genera solo si el alias no existe; si
ya existe, se reutiliza.

- **No exportable por construcción:** AndroidKeyStore no entrega los bytes de la
  llave privada. La app solo tiene un manejador `PrivateKey` con el que pide firmas.
- **Llave pública:** se envía como DER X.509 SubjectPublicKeyInfo en base64, el
  formato que `/dispositivos/registrar` ya acepta.
- **`firmar()`:** usa `SHA256withECDSA` y devuelve la firma DER en base64, que es lo
  que espera `verificar_canje`. Queda lista, pero todavía no se conecta al canje.
- **No se pide autenticación del usuario para firmar.** Pedir huella o PIN en cada
  canje agregaría fricción en el aula. La identidad ya la aporta la sesión.

**StrongBox con respaldo a TEE:**

- Si el dispositivo anuncia `FEATURE_STRONGBOX_KEYSTORE` (API 28+), la llave se pide
  con `setIsStrongBoxBacked(true)`. Si lanza `StrongBoxUnavailableException`, se
  genera en el TEE y el respaldo se registra en el log.
- **Por qué:** sin pedir StrongBox, la llave de un Pixel 9a vive en el TEE del Tensor
  y no en el chip Titan M2. StrongBox es un elemento seguro aparte, más resistente a
  ataques físicos.
- **Costo:** StrongBox es más lento para firmar, y eso se suma a cada canje. Se mide
  en la tarea de la firma del canje.

**Huella de instalación (`data/Instalacion.kt`):** `huella_dispositivo` es un
`UUID.randomUUID()` creado la primera vez que se pide. Dura mientras la app esté
instalada y cambia al reinstalarla o al borrar sus datos.

- Vive en un archivo propio (`instalacion.xml`) y no en la sesión cifrada, porque
  `SessionStore.borrar()` se ejecuta en cada cierre de sesión.
- Se excluye del respaldo en `backup_rules.xml` y `data_extraction_rules.xml`. Si se
  restaurara en otro teléfono, dos teléfonos compartirían la huella.

Por privacidad **no se usa ningún identificador de hardware ni de publicidad**:

| Identificador | Por qué se descarta |
|---|---|
| ID de publicidad | Existe para rastreo publicitario entre apps |
| IMEI y número de serie | Identifican el hardware de forma permanente, y desde API 29 exigen `READ_PRIVILEGED_PHONE_STATE`, que no se concede a apps normales |
| `ANDROID_ID` | Sobrevive a la reinstalación, así que ya no sería por instalación |

**"Enrolado" va atado a la sesión, no es permanente.** `SessionStore` guarda `enrolado`
y `huella_llave`. `guardar()` (login nuevo) pone `enrolado = false`, y `borrar()`
limpia todo. Así, cada login con alcance `"completo"` vuelve a enrolar.

- **Por qué:** con la política de un dispositivo activo, iniciar sesión en un teléfono
  significa "este es mi teléfono ahora". Si la bandera fuera permanente, este caso se
  rompe:
  1. El alumno inicia sesión en el teléfono A.
  2. Inicia sesión en el teléfono B, lo que desactiva A en el servidor.
  3. Vuelve a A e inicia sesión. A se saltaría el enrolamiento y cada canje
     respondería 403, sin forma de recuperarse.
- **Costo:** una petición extra por login y un nodo `Dispositivo` nuevo con la misma
  llave y la misma huella. La regla de anomalía de re-enrolamientos frecuentes
  (2026-09-12) debe contar como re-enrolamiento solo los cambios de llave o de huella,
  no la repetición de la misma. Con los datos que ya se guardan, esa distinción es
  directa.
- **Por qué se reutiliza la llave:** si dos alumnos enrolan el mismo teléfono, el
  servidor ve la misma llave con dos matrículas. Esa es la señal de proxy del
  2026-09-23. Generar una llave nueva en cada login la ocultaría.

**Flujo sin estados a medias:** una pantalla propia (`EnrolamientoScreen` +
`EnrolamientoViewModel`) va entre el login y el escáner.

- Obtiene o crea la llave fuera del hilo principal, lee la huella y llama a
  `/dispositivos/registrar`.
- Solo marca `enrolado` si el servidor responde 201 **y** la `huella_llave` que
  devuelve coincide con la calculada localmente (primeros 16 hexadecimales de SHA-256
  del DER).
- Si falla la llave, la red, el servidor o la huella: mensaje en *live region*
  `Assertive` y botón **Reintentar**. Reintentar es seguro, porque la llave se
  reutiliza y el servidor reemplaza el dispositivo activo.
- Con 401/403: borra la sesión y vuelve al login con aviso.
- Botón **Cerrar sesión**, para que el alumno nunca quede atrapado.
- Al arrancar, `MainActivity` manda a esta pantalla si la sesión es completa pero no
  está enrolada. Eso cubre que el proceso muera a la mitad del enrolamiento y a
  quien actualice la app con una sesión ya guardada.

**Nivel de seguridad en el log:** `LlaveDispositivo` escribe con la etiqueta
`LlaveDispositivo`, también en release, porque no contiene datos personales:

- si la llave es nueva o reutilizada
- si se pidió StrongBox y si hubo respaldo a TEE
- el nivel de seguridad reportado por `KeyInfo` (`securityLevel` en API 31+;
  `isInsideSecureHardware` antes)
- la huella de la llave, el API y el modelo

**Observado en el Pixel 9a (Titan M2): STRONGBOX en todos los casos, tanto en la
prueba instrumentada como en el flujo manual. respaldo_tee=false, o sea que
no hizo falta el respaldo al TEE. Evidencia en
docs/evidencias/enrolamiento_dispositivo_2026-09-29.txt.
Se verifico ademas que la llave sobrevive al cierre de
sesion:tras cerrar sesion y volver a entrar, el log muestra llave=reutilizada con
la misma huella_llave, que es lo que permite a la regla de anomalia
distinguir "mismo telefono otra vez" de "telefono distinto".

### Verificación

- `./gradlew assembleDebug assembleRelease assembleDebugAndroidTest`: compila sin
  errores.
- `androidTest/.../LlaveDispositivoTest.kt` verifica:
  - creación y reutilización de la llave (misma llave pública)
  - que la llave es P-256
  - que una firma verifica y falla con un mensaje alterado
  - que en API 31+ el nivel es `STRONGBOX` o `TRUSTED_ENVIRONMENT`
  - la prueba instrumentada y la manual se
   corrieron el 2026-09-29 en el Pixel 9a con resultado correcto.
  - login → enrolamiento → 201 → escáner
  - `Dispositivo` activo en Neo4j con la huella UUID
  - error y reintento con el servidor apagado
  - re-login con la misma llave

### Límites conocidos

- **El nivel de seguridad no lo puede verificar el servidor (Key Attestation):**
  - `KeyInfo.getSecurityLevel` lo reporta el propio cliente. Una app modificada o
    instrumentada podría mentir sobre él: reportar `STRONGBOX` con la llave en
    software, o enrolar una llave generada fuera de Keystore. El servidor recibe solo
    una llave pública y no puede distinguir ninguno de los dos casos.
  - La única prueba verificable por el servidor sería Key Attestation:
    1. generar la llave con `setAttestationChallenge` sobre un reto emitido por el
       servidor;
    2. enviar la cadena de certificados de atestación;
    3. validarla en el servidor hasta la raíz de atestación de Google;
    4. leer en la extensión de atestación el `attestationSecurityLevel` y las
       propiedades de la llave.
  - Queda **fuera de alcance por el congelamiento de código del 12 de octubre de
    2026** y se documenta como trabajo futuro. El nivel que aparece en el log es una
    observación del dispositivo de pruebas, no una garantía del sistema.
- **La latencia de firma en StrongBox todavía no se mide.** Se mide en la tarea de la
  firma del canje. Si resulta prohibitiva, la alternativa es el TEE, y la comparación
  misma es un resultado.
- **Root:** sin cambios respecto al 2026-09-12. Keystore impide extraer la llave, no
  usarla desde el dispositivo ya enrolado.
- **El canje sigue respondiendo 401:** `enviarAsistencia` aún no manda `X-TIMESTAMP` ni
  `X-SIGNATURE`. Es la siguiente tarea, junto con la háptica diferenciada.
- **Cierre de sesión solo local:** el botón "Cerrar sesión" del escáner (con diálogo de
  confirmación) borra `sesion_cifrada` y vuelve al login. No toca la llave de Keystore
  ni la huella de instalación, así que el siguiente login re-enrola la misma llave (en
  el log aparece `llave=reutilizada` con la misma `huella_llave`).
  - El servidor no tiene `POST /logout`, así que el token borrado **sigue siendo
    válido** hasta su `expira_en`, o hasta el siguiente `/login` de esa matrícula, que
    lo revoca porque solo hay una sesión activa.
  - El riesgo residual es bajo: el token ya no existe en el teléfono, y por sí solo no
    permite canjear, porque el canje exige también la firma del dispositivo. Pero una
    copia obtenida antes del cierre (tráfico capturado, dispositivo rooteado) seguiría
    sirviendo para `/dispositivos/registrar` hasta que expire.
  - Revocar en el servidor requiere un endpoint nuevo. Queda como trabajo futuro.

---

## 2026-09-30 — Firma del canje en Android (punto de cambio 8, tercera parte)

### Decisión

**Encabezados del canje** (`enviarAsistencia` en `QRScannerScreen.kt`):

- `Authorization: Bearer` con el token de la sesión vigente.
- `X-TIMESTAMP`: la hora del servidor estimada, `SessionStore.ahoraServidorMs() / 1000`
  (hora local + desfase medido en el login), en segundos enteros, como la parsea
  `verificar_canje`.
- `X-SIGNATURE`: `LlaveDispositivo.firmar` sobre `"{timestamp}/asistencia:{token_qr}"`.
  Es SHA256withECDSA, con firma DER en base64.
- El `token_qr` es el valor ya decodificado del parámetro `token` del QR. La URL se
  arma siempre sobre `BuildConfig.BASE_URL`, igual que antes.

**Firma fuera del hilo principal:** el analizador de CameraX usa `getMainExecutor`, así
que el QR llega en el hilo principal. La firma corre en `Dispatchers.Default` y la
petición en `Dispatchers.IO`, desde un `rememberCoroutineScope`. La lógica de red
sigue en una función fuera del Composable.

**Hueco encontrado: el replay no se distinguía del éxito.** Al escribir el cliente
Android se encontró que el replay de un token ya canjeado (200 con `warning.html`) no
se distinguía del éxito (200 con `success.html`) por el código de estado. Por eso la
app mostraba "Asistencia registrada" en un reuso. El diseño documentado (2026-09-12,
punto de cambio 4, y 2026-09-24) no fijaba una respuesta para este caso.

Se corrige en `process_checkin` con un `if` dentro de la rama `is_used`:

- **Solo el POST responde `409`:** `{"error": "token_reutilizado", "warnings": n}`. A
  esa rama solo llega un POST que ya pasó `verificar_canje` (Bearer y `X-SIGNATURE`
  válidos); uno sin autenticar se corta antes con 401 o 403.
- **`increment_token_warnings` se ejecuta antes de responder,** igual que antes, así
  que el contador de reintentos, dato de la sección 9 de `CLAUDE.md`, no se pierde.
- **La rama GET y `warning.html` no cambian** para el navegador.

**Respuestas y reacción de la app:**

| Código | Causa en el servidor | App |
|---|---|---|
| 200 | Canje registrado | Háptica de confirmación, "Asistencia registrada" |
| 401 | Sesión expirada o revocada, firma inválida, timestamp fuera de ventana | Borra la sesión y vuelve al login |
| 403 | Sin dispositivo activo (otro teléfono se enroló) o alcance incorrecto | Borra la sesión y vuelve al login |
| 409 | `token_reutilizado` | Háptica de rechazo, mensaje y "Escanear de nuevo" |
| 404 | Token QR inexistente | Háptica de rechazo, mensaje y "Escanear de nuevo" |
| Red o 5xx | — | Háptica de rechazo, mensaje y "Escanear de nuevo" |

**Recuperación uniforme por re-login:** 401 y 403 llevan al mismo lugar porque un
nuevo inicio de sesión corrige todas sus causas:

- emite un token nuevo;
- vuelve a enrolar la llave (entrada 2026-09-29), lo que reactiva este teléfono si
  otro lo había desplazado;
- recalcula el desfase de reloj, lo que corrige un timestamp fuera de ventana.

**Háptica y TalkBack (sección 10 de `CLAUDE.md`):**

- La háptica usa `View.performHapticFeedback`: `CONFIRM` y `REJECT` en API 30+, y
  `CONTEXT_CLICK` y `LONG_PRESS` en versiones anteriores. No requiere el permiso
  `VIBRATE`.
- El mensaje de resultado está en una *live region*: `Polite` para "Enviando…" y
  el éxito, `Assertive` para los errores. Es texto blanco sobre el fondo negro de la
  cámara (contraste 21:1); antes usaba el color por defecto, ilegible en tema claro.
- El botón "Escanear de nuevo" mide 48 dp y tiene `contentDescription`. Antes, tras un
  error, la pantalla quedaba bloqueada porque nunca se limpiaba el QR escaneado.

**Se quitó `activity?.finish()` tras el éxito.** Cerrar la app de inmediato cortaba el
anuncio de TalkBack, y el alumno no alcanzaba a leer la confirmación.

### Latencia de firma: StrongBox contra TEE

Hay dos fuentes de datos, las dos con la etiqueta `LlaveDispositivo` o `LatenciaFirma`
en logcat, sin datos personales:

- **Prueba reproducible:** `LlaveDispositivoTest.medirLatenciaFirma`. Hace 10 firmas
  de calentamiento y 100 medidas con la llave de producción, y lo mismo con una llave
  TEE de prueba con los mismos parámetros, que se crea y se borra dentro de la prueba.
  Las dos rutas se miden igual que en el canje (abrir Keystore, obtener la llave,
  firmar) y se reportan mínimo, p50, p95, p99 y máximo.
- **Flujo real:** cada canje registra `canje firma_ms=… nivel=…`.

| Nivel | n | mín | p50 | p95 | p99 | máx (ms) |
|---|---|---|---|---|---|---|
| STRONGBOX (Titan M2) | 100 | 38.9–41.5 | 49.6–49.8 | 53.5–53.7 | 55.3–55.9 | 55.3–58.8 |
| TRUSTED_ENVIRONMENT (llave de prueba) | 100 | 4.8–5.4 | 7.9–8.1 | 9.4–12.2 | 10.9–12.6 | 11.9–15.7 |

Pixel 9a, API 37. Dos corridas el 2026-09-30 (11:12 y 12:00), cada una con 10 firmas de
calentamiento y 100 medidas por nivel. Cada celda muestra el rango entre las dos
corridas. Fuente: `docs/evidencias/latencia_firma_2026-09-30.txt`, que contiene las dos.

**Lo que muestran los datos:**
- En la mediana, StrongBox tarda unas 6 veces lo que tarda el TEE (49.6–49.8 contra
  7.9–8.1 ms). En valor absoluto, son unos 42 ms más por canje en p50.
- StrongBox es estable entre corridas: la mediana varía 0.2 ms. Su dispersión es baja y
  no hay colas largas, con un máximo de 58.8 ms.

**Conclusión: se mantiene StrongBox.** Cuesta unos 6 veces más que el TEE, pero son
unos 50 ms por canje. Se considera imperceptible frente al tiempo total del canje, que
además de la firma incluye:
- detectar el QR con la cámara;
- el viaje de ida y vuelta por la red;
- la verificación y la escritura en Neo4j del lado del servidor.

A cambio, la llave vive en un elemento seguro aparte del procesador principal, más
resistente a ataques físicos (entrada 2026-09-29).

La afirmación de que el costo es imperceptible se apoya en la escala de los otros
pasos, **no en una medición del canje completo**. Se confirma cuando exista la métrica
3 de la sección 9 (tiempo de registro por alumno). Si esa métrica mostrara que la firma
pesa de forma apreciable, cambiar a TEE es quitar `setIsStrongBoxBacked` en
`LlaveDispositivo`.

[PENDIENTE: muestras `canje firma_ms` del flujo real; la evidencia actual solo contiene
la prueba instrumentada.]

### Verificación

- `backend/tests/probar_canje_firmado.py`: 9/9, salida en
  `docs/evidencias/canje_firmado_2026-09-30.txt`.
  - El caso del replay ahora exige `409` con `token_reutilizado` y `warnings=1`.
  - Se agregó un caso nuevo: el GET del token usado sigue respondiendo `warning.html`
    con 200 e incrementa `warnings`.
- `probar_registro_dispositivo.py` sigue en 17/17.
- `./gradlew assembleDebug assembleRelease assembleDebugAndroidTest` compila.
- Pendiente en dispositivo:
  - la prueba de latencia
  - canje real contra el servidor local con `visor.py`: éxito y rotación del QR,
    reescaneo con 409, y forzar un 403 re-enrolando desde otro dispositivo
  - pasada con TalkBack

### Límites conocidos

- **La app no distingue los motivos del 401:** todos llevan al login. El mensaje JSON
  del servidor se conserva en `ResultadoCanje.NoAutorizado`, pero no se muestra.
- **La háptica respeta el ajuste de "respuesta táctil" del sistema:** si el usuario lo
  desactivó, no vibra. Es intencional; el anuncio de TalkBack no depende de ese ajuste.
- **Los rechazos todavía no se registran en el servidor** (punto de cambio 7).
- **Ejecutar las pruebas del backend afecta a SIM0001:** `probar_canje_firmado.py`
  enrola una llave local e invalida la sesión de SIM0001. Después de correrlo, el
  teléfono de pruebas recibe 401 en su siguiente canje y debe iniciar sesión de nuevo.
  Es el camino de recuperación esperado.

---

## 2026-10-04 — Registro de intentos rechazados (punto de cambio 7)

### Decisión

Cada rechazo de `/login`, `/cambiar_password`, `/dispositivos/registrar` y el canje
(`/?token=...`) crea un nodo `(:IntentoRechazado)` en Neo4j. El nodo es aditivo: no
se relaciona con `Token`, `Alumno` ni `Dispositivo`, y no se modificó ninguna
función que los escriba.

```
(:IntentoRechazado {motivo, endpoint, metodo, status_http,
                    marca_tiempo, fecha, ip_origen,
                    huella_dispositivo?, alumno_id?, rol_alumno?,
                    sesion_id?, token_qr_hash?, encabezados, id_prueba?})
```

- `marca_tiempo` es el epoch del servidor (`time.time()`), indexado para consultas
  por rango; `fecha` es la misma marca en ISO, por legibilidad.
- Índices sobre `motivo`, `marca_tiempo` e `id_prueba` (`rechazos.asegurar_esquema_rechazos`,
  se crea al arrancar junto con el esquema de identidad).

**Implementación:** módulo nuevo `backend/rechazos.py` (catálogo, saneamiento y
escritura) y una función `rechazar(motivo, status, respuesta)` en `server.py` que
registra y devuelve la misma respuesta de antes. **Ningún código de estado ni cuerpo
de respuesta cambió**; la app no se entera del registro.

- `verificar_token_sesion` y `verificar_canje` devuelven ahora el motivo como tercer
  elemento de la tupla de error. Se ajustaron los tres lugares que la desempaquetan.
- El contexto que se resuelve a mitad de la petición (`alumno_id`, `rol_alumno`,
  `huella_dispositivo`) viaja en `flask.g`, que vive solo durante la petición. Así no
  hubo que cambiar las firmas de las funciones para pasarlo de mano en mano.
- Si la escritura del registro falla, se imprime en stderr y se responde igual: un
  fallo del registro no debe convertir un 401 en un 500.

### Catálogo de motivos

Se fijan 15 motivos, cerrados en `rechazos.MOTIVOS`: un motivo fuera de la lista
lanza error en lugar de guardarse. Los 12 originales más tres que aparecieron al
recorrer el código real, porque había rechazos que no cabían en ninguno:
`alcance_insuficiente`, `solicitud_invalida` y `token_qr_inexistente`.

| Motivo | Dónde | Respuesta |
|---|---|---|
| `solicitud_invalida` | Todos los 400: `/login` sin matrícula o password; `/cambiar_password` con contraseña corta o igual a la actual; `/dispositivos/registrar` sin llave, sin huella, huella > 256 o llave no P-256; canje sin `?token=` o `Alumno` sin nombre | 400 |
| `login_bloqueado_matricula` | `/login` con `BloqueoLogin` vigente por matrícula (gana si también hay bloqueo por IP) | 429 |
| `login_bloqueado_ip` | `/login` con `BloqueoLogin` vigente solo por IP | 429 |
| `credenciales_invalidas` | `/login` con matrícula inexistente o password incorrecto | 401 |
| `no_autenticado` | Falta `Authorization: Bearer` (o viene vacío) | 401 |
| `token_invalido` | Token de sesión sin el formato de `/login` o con HMAC inválido | 401 |
| `token_expirado` | Token de sesión con HMAC válido y vencido | 401 |
| `alcance_insuficiente` | Token de alcance distinto al que exige el endpoint | 403 |
| `sesion_cerrada` | Token válido pero revocado (otro login o cambio de contraseña) | 401 |
| `encabezados_faltantes` | Canje sin `X-TIMESTAMP` o sin `X-SIGNATURE` | 401 |
| `timestamp_fuera_ventana` | Canje con `X-TIMESTAMP` no entero o fuera de ±60 s | 401 |
| `sin_dispositivo_activo` | Canje de un alumno sin `Dispositivo` activo | 403 |
| `firma_invalida` | Canje con firma ECDSA que no verifica contra el dispositivo activo | 401 |
| `token_qr_inexistente` | Canje (GET o POST) de un token QR que no existe | 404 |
| `token_reutilizado` | Token QR ya usado: POST autenticado (409) y GET de navegador (`warning.html`) | 409 / 200 |

- `token_invalido` se refiere solo al token de **sesión**; el token **QR** que no
  existe tiene su propio motivo. Juntarlos mezclaría "alguien falsificó una sesión"
  con "alguien escaneó un QR viejo o inventado", que son ataques distintos.
- El GET de un token ya usado responde 200 al navegador (sin cambios), pero se
  registra como `token_reutilizado`: es un reuso aunque el código no lo diga.
- Un `X-TIMESTAMP` que no es entero cae en `timestamp_fuera_ventana` y no en
  `encabezados_faltantes`: el encabezado sí vino, pero no representa un instante
  dentro de la ventana.

### Qué se guarda y qué nunca

- **Encabezados, por lista blanca.** Se guardan los valores de `User-Agent`,
  `Accept-Language`, `Content-Type`, `Origin`, `Referer`, `X-Forwarded-For`,
  `CF-Connecting-IP` y `X-TIMESTAMP`, recortados a 256 caracteres. De `Authorization`,
  `X-SIGNATURE` y `Cookie` solo se guarda si venían (`*_presente: true/false`).
  Neo4j no admite mapas como propiedad, así que van como texto JSON.
- **El cuerpo de la petición no se guarda nunca.** Por eso ninguna contraseña puede
  colarse, ni la del login ni la nueva de `/cambiar_password`.
- **Ningún token en crudo.** `sesion_id` y `token_qr_hash` son los primeros 16
  hexadecimales de SHA-256 del token de sesión y del token QR. Sirven para
  correlacionar intentos (el mismo token QR atacado varias veces, la misma sesión
  insistiendo) sin poder reconstruir el valor.
- **`huella_dispositivo`:** en `/dispositivos/registrar` se toma del cuerpo aunque el
  rechazo sea de autenticación, porque el dato se recibió. En el canje la app no
  la envía, así que solo aparece cuando ya se leyó el `Dispositivo` activo (es decir,
  en `firma_invalida` y `token_reutilizado`).
- **`ip_origen`** es `request.remote_addr`, el mismo dato que usa `BloqueoLogin`.

### Por qué `alumno_id` no se atribuye cuando el HMAC falla

El token de sesión lleva la matrícula en claro (`matricula.alcance.expira_en.firma`).
Antes de verificar la firma HMAC, esa matrícula es texto que cualquiera puede
escribir: un atacante podría mandar miles de tokens falsos con la matrícula de un
compañero, y si el registro la tomara como `alumno_id`, el conjunto de datos de la
tesis mostraría a ese compañero como autor de un ataque que nunca hizo. Eso
contaminaría justo las reglas de anomalía del 2026-09-12, que cuentan intentos por
alumno. Por eso `alumno_id` solo se llena **después** de que el HMAC verifica: en ese
punto la matrícula está firmada por el servidor y es confiable aunque el token haya
expirado, tenga otro alcance o esté revocado. La prueba lo verifica con un token
falsificado que lleva la matrícula SIM0003 y HMAC inválido: el nodo queda sin
`alumno_id`.

`rol_alumno` distingue los dos únicos casos en que se atribuye:

- `titular_sesion`: la matrícula salió de un token con HMAC válido.
- `objetivo_login`: en `/login` con credenciales inválidas, si la matrícula escrita
  **existe**. Es el blanco del intento, no su autor. Si no existe, no se guarda, para
  no almacenar matrículas reales mal tecleadas.

### `X-Id-Prueba`: instrumentación de laboratorio

`X-Id-Prueba` es un encabezado **opcional** que manda el banco de ataques en cada
petición. **El servidor nunca lo usa para decidir si acepta o rechaza**: solo lo
guarda como etiqueta en `id_prueba`, si es hexadecimal en minúsculas de hasta 64
caracteres (si no, se descarta). La prueba lo verifica mandando la misma petición
sin el encabezado, con un valor inválido y con uno válido: las tres respuestas son
idénticas.

Que un atacante real pueda mandarlo no le da nada: no cambia la decisión, y una
etiqueta inventada solo afectaría a una corrida del banco cuyo manifiesto no la
contiene, así que el script de métricas la ignora.

### Métricas: `backend/scripts/metricas_deteccion.py`

La tasa de detección y la de falsos positivos no se pueden calcular solo con los
rechazos: hace falta saber cuántas peticiones se mandaron y cuáles eran ataque. Eso
lo aporta un manifiesto JSONL que escribe el banco de ataques, una línea por
petición: `{id_prueba, escenario, clase: "ataque"|"legitimo", motivo_esperado}`.

- Una petición del manifiesto con nodo `IntentoRechazado` se cuenta como rechazada;
  sin nodo, como aceptada. No hace falta registrar las peticiones aceptadas.
- **Detección:** ataques rechazados / ataques enviados, global y por escenario.
- **Falsos positivos:** legítimas rechazadas / legítimas enviadas, global, por
  escenario y por motivo (qué control rechazó tráfico legítimo).
- Por escenario también se reporta si el motivo registrado coincide con el
  esperado: un ataque puede quedar detenido por un control distinto al que se
  pretendía probar, y eso es un hallazgo.
- Cada tasa lleva un intervalo de confianza de Wilson al 95 %, porque el banco manda
  decenas de peticiones por escenario y no miles. [PENDIENTE: cita del intervalo de
  Wilson]
- Sin manifiesto, el script solo da conteos por motivo y endpoint en un rango de
  fechas, y lo dice en la salida.
- Salida en `docs/evidencias/metricas_deteccion_<fecha>_<hora>.txt` y `.json`.

Se probó con un manifiesto sintético de 13 peticiones (en un directorio temporal,
no en `docs/evidencias/`): 7/8 ataques detectados y 1/5 legítimas rechazadas,
iguales al conteo a mano.

### Verificación

`backend/tests/probar_registro_rechazos.py` (test_client de Flask, Neo4j real,
alumnos sintéticos SIM0001–SIM0003). Salida en
`docs/evidencias/registro_rechazos_2026-10-04.txt`: **39/39**.

- Provoca los 15 motivos y comprueba, por cada uno, que hay exactamente un nodo con
  motivo, endpoint, status, IP, `alumno_id`, `rol_alumno` y huella esperados.
- Comprueba que el canje válido no deja nodo.
- Revisa todas las propiedades de los 82 nodos de la corrida contra los 16 valores
  secretos que mandó (contraseñas, tokens de sesión, tokens QR, firmas): ninguna
  aparece.
- Los bloqueos de login usan SIM0002 e IPs de documentación (RFC 5737), para no
  bloquear la cuenta del teléfono de pruebas.

**Limpieza:** la prueba borra sus nodos, los `BloqueoLogin` y los `Token` que creó.
`probar_canje_firmado.py` y `probar_registro_dispositivo.py` ahora también generaban
nodos `IntentoRechazado`; se ajustaron para usar una IP de documentación propia y
borrarlos al final. Siguen en 9/9 y 17/17, y tras las tres pruebas el grafo queda con
0 nodos `IntentoRechazado`.

### Límites conocidos

- **Todas las pruebas salen de la misma máquina.** `ip_origen` será casi siempre la
  misma (y detrás del túnel, la del túnel), así que el contador de `BloqueoLogin` por
  IP no se puede evaluar de forma realista: o nunca se dispara, o se dispara para
  todos a la vez. Evaluarlo exige varias fuentes reales o simular orígenes con
  `X-Forwarded-For`, lo que a su vez requiere que el servidor confíe en ese
  encabezado solo detrás de un proxy conocido. Hoy se guarda pero no se usa. En las
  pruebas, la IP se simula con `REMOTE_ADDR` del test_client.
- **Solo se registran los rechazos.** El punto de cambio 7 decía "rechazado o no";
  los intentos aceptados quedan fuera de esta tarea. Para las tasas no hacen falta
  (se infieren del manifiesto), pero las reglas de anomalía que miran canjes
  exitosos (misma huella con varias matrículas) siguen leyendo el nodo `Token`.
- **`/get_token` no se registra.** No estaba entre los cuatro endpoints de la tarea.
- **Token de sesión con caracteres no ASCII → 500 sin registro.** Verificado el
  2026-10-04: `hmac.compare_digest` lanza `TypeError` al comparar cadenas no ASCII,
  así que un `Bearer` con, por ejemplo, `á` produce un error 500 y no llega a
  registrarse. Es previo a esta tarea y no permite autenticarse, pero es un rechazo
  que se escapa del conjunto de datos. La corrección propuesta (no implementada,
  porque toca la verificación de sesión) es comparar bytes
  (`firma_recibida.encode("utf-8")`) o rechazar antes como `token_invalido` todo
  token no ASCII. Lo mismo aplica a `/get_token`.
- **Una escritura por rechazo.** Una inundación de peticiones hace crecer el grafo
  sin límite, y cada rechazo suma una transacción a la latencia que medirán las
  pruebas de carga de la sección 9. No hay retención ni muestreo; queda como trabajo
  futuro.
- **Los 429 no llevan `alumno_id`.** El bloqueo se revisa antes de buscar al alumno y
  no se quiso reordenar `/login` solo para el registro. La matrícula bloqueada se
  puede reconstruir desde `BloqueoLogin` en la misma ventana.
- **Fallo silencioso del registro.** Si Neo4j rechaza la escritura, el rechazo se
  responde pero no queda en el conjunto de datos (solo en stderr). Se prefirió eso a
  responder 500.
- **`solicitud_invalida` por contraseña igual a la actual** no se ejercita en la
  prueba, porque exigiría conocer la contraseña vigente de un alumno sintético; usa
  el mismo `rechazar` que el caso de contraseña corta, que sí se prueba.
- **`ruff` sigue sin estar instalado**; el formato del código nuevo no se verificó
  con esa herramienta.
