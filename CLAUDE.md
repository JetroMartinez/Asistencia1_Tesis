# CLAUDE.md — Sistema de Asistencia CU2-BUAP

Contexto permanente para Claude Code en este repositorio. Léelo completo antes de proponer cambios.

---

## 1. Contexto del proyecto

Tesis de licenciatura en Ingeniería en Ciencias de la Computación, BUAP, Facultad de
Ciencias de la Computación.

- **Título:** Automatización del pase de lista para el uso cotidiano en CU2-BUAP
- **Autor:** Jetro Eliezer Martínez Hernández
- **Entrega final:** 7 de noviembre de 2026
- **Congelamiento de código:** 12 de octubre de 2026 (sin excepciones)

**Este es un artefacto académico, no un producto comercial.** Cada decisión técnica
debe ser defendible ante un jurado y estar respaldada por mediciones. Un sistema
sencillo con comportamiento medido vale más que uno sofisticado sin evidencia.

### El proyecto está en fase de CONSOLIDAR, no de CONSTRUIR

La mayor parte del sistema ya existe y funciona. El trabajo restante es **integrar,
asegurar, hacer accesible y medir** lo que hay. No reescribas componentes que ya
funcionan. Si algo parece mejorable pero funciona, déjalo y anótalo como trabajo futuro.

---

## 2. Arquitectura real del sistema

Tres piezas que se comunican en vivo:

```
  [ PC1 / Proyector ]            [ Servidor remoto ]           [ App Android ]
      visor.py          ──HMAC──▶   server.py      ◀──token──    (artefacto
   muestra QR rotativo   (firma)    Flask+Neo4j                    central)
        ▲                          + Socket.IO
        └──────── señal socket ────────┘
                 "genera token nuevo"
```

1. **`visor.py`** corre en la máquina del aula. Pide un token al servidor firmando la
   petición con HMAC-SHA256 (ventana de 30 s) y proyecta el QR. Escucha por Socket.IO
   la señal `new_token_signal` para rotar el QR tras cada registro exitoso.
2. **`server.py`** es el servidor central en `prueba.almxlvx.com` (dominio del director
   de tesis). Flask + Neo4j + Socket.IO. Emite tokens de un solo uso, procesa el
   registro, cuenta reintentos (`warnings`) cuando un token se reusa, y guarda IP,
   fecha y cookie de rastreo.
3. **La aplicación Android** es el cliente del estudiante. Kotlin + Compose, escaneo con
   CameraX + ML Kit.

Componentes de apoyo: `poolling.py` (monitor en vivo), `reporte4.py` (tablero, PDF y
firma digital), `excel_ver/app.py` (carga de listas), `firma_calificaciones/app.py`
(certificados firmados).

---

## 3. Stack técnico REAL

| Capa | Tecnología | Nota |
|------|-----------|------|
| Móvil | Kotlin + Jetpack Compose, minSdk 24 | Artefacto central |
| Cámara / QR | CameraX + ML Kit Barcode Scanning | |
| Backend | **Flask** (no FastAPI) | Ya funciona, no migrar |
| Base de datos | **Neo4j** (no PostgreSQL) | Ya funciona, no migrar |
| Tiempo real | Flask-SocketIO + python-socketio | |
| Firma digital | `cryptography` (RSA + certificado X.509) | |
| PDF | ReportLab | |
| HTTP cliente (Android) | OkHttp | |
| Pruebas de carga | Locust | Por implementar |
| Entorno | CachyOS (Arch Linux) | |

**Paquete Android:** `mx.buap.fcc.asistencia`

**No migrar de stack.** Flask y Neo4j se quedan. Si surge la duda en la defensa, la
justificación de Neo4j es que las relaciones alumno–clase–sesión–asistencia forman
naturalmente un grafo y las consultas de trayectoria son directas en Cypher.

---

## 4. Decisión de diseño: la app Android es el artefacto central

Es uno de los entregables comprometidos en el protocolo y el más importante. Esto tiene
consecuencias que hay que respetar:

- **El flujo web de registro (`checkin_form.html` en la ruta `/`) es hoy un bypass
  completo de la app.** Cualquiera con la URL del QR se registra desde un navegador.
  Hay que cerrarlo o restringirlo: el canje del token debe exigir una prueba de que
  viene de un dispositivo registrado en la app.
- **La accesibilidad se implementa en la app**, no en el HTML. TalkBack, háptica,
  `contentDescription`.
- **Las mediciones de tiempo de registro y usabilidad se hacen sobre la app**, no sobre
  el formulario web.
- Si se conserva alguna ruta web, es como respaldo documentado, no como camino principal,
  y debe exigir la misma autenticación.

---

## 5. Modelo de seguridad

### Lo que YA está implementado (no rehacer)

- Firma HMAC-SHA256 con ventana de 30 s y `hmac.compare_digest` en `/get_token`
- Tokens de un solo uso, invalidados al primer canje
- Contador de reintentos (`warnings`) y pantalla de advertencia ante reuso de token
- Rotación del QR mediante señal por Socket.IO tras cada registro
- Registro de IP, marca de tiempo y cookie por intento
- Firma digital RSA de reportes con certificado, log de firmas y endpoint de validación
- Bloqueo de consultas por IP y por matrícula (`consultas_bloqueadas.jsonl`)

### EL HUECO PRINCIPAL (prioridad número uno)

El HMAC protege que el **proyector** pida tokens. No protege el **canje**. En la ruta `/`
el estudiante escribe su nombre y matrícula a mano y nadie verifica quién es. El token
de un solo uso limita el daño a una persona por token, pero la identidad sigue siendo
autodeclarada.

**Hay que cerrar esto.** Dirección propuesta: registro del dispositivo en la app
(vinculación matrícula ↔ dispositivo), y que el canje del token exija una petición
firmada desde ese dispositivo registrado. Discutir alternativas antes de implementar.

### Fallos concretos que hay que corregir

1. `visor.py` corre con `debug=True`: expone el depurador de Werkzeug y permite
   ejecución remota de código. Quitarlo.
2. `cors_allowed_origins="*"` en Socket.IO: restringir a los orígenes reales.
3. `prueba.almxlvx.com` está incrustado en el código: moverlo a configuración.
4. La cookie `user_tracker` se emite sin `Secure`, `HttpOnly` ni `SameSite`.

### Invariantes que no se rompen

- Los secretos viven en `.env`, nunca en el código ni en el repositorio
- Las llaves privadas nunca entran al control de versiones
- Todo intento rechazado se registra con motivo, marca de tiempo y metadatos: ese
  registro ES el conjunto de datos de la tesis

---

## 6. Protección de datos personales (crítico)

En el disco existen datos REALES de estudiantes: listas en Excel, PDFs de certificados,
logs de firmas. **Ninguno está en el repositorio y así debe permanecer.**

- Nunca hagas `git add` de `*.pem`, `*.xlsx`, `*.pdf`, `*.jsonl`, ni de
  `firma_digital/`, `data_firmas/`, `uploads_excel/`, `resultados_excel/`
- Para pruebas y para la tesis, usa datos **sintéticos**
- La BUAP es sujeto obligado en materia de protección de datos personales
- Si necesitas datos de ejemplo en documentación o capturas, anonimízalos

---

## 7. Estructura del repositorio

```
.
├── app/                      # Aplicación Android (Kotlin/Compose)
├── backend/
│   ├── server.py             # Servidor central (Flask + Neo4j + Socket.IO)
│   ├── visor.py              # Cliente proyector del aula (PC1)
│   ├── poolling.py           # Monitor en vivo
│   ├── reporte4.py           # Tablero vigente + firma digital
│   ├── templates/            # checkin_form, success, warning, qr_display
│   ├── excel_ver/            # Carga de listas
│   ├── firma_calificaciones/ # Certificados firmados
│   ├── legacy/               # reporte.py, reporte2.py, reporte3.py (archivados)
│   ├── tests/
│   └── scripts/              # Ataques y pruebas de carga
├── docs/
│   ├── evidencias/           # Mediciones, logs y capturas para la tesis
│   └── decisiones.md         # Bitácora de decisiones técnicas
└── CLAUDE.md
```

**`reporte4.py` es la versión vigente.** Las versiones 1 a 3 van a `legacy/` y no se
tocan; existen solo como historial.

---

## 8. Alcance

### Dentro del alcance (trabajo restante)

- Cerrar el hueco de identidad: registro de dispositivo y canje autenticado
- Cerrar o restringir el flujo web de registro
- Corregir los cuatro fallos de seguridad de la sección 5
- Consolidar `reporte*.py` y archivar las versiones viejas
- Accesibilidad en la app: TalkBack, `contentDescription`, retroalimentación háptica
- Configuración externalizada (dominio, puertos, secretos)
- Banco de scripts de ataque y pruebas de carga con métricas
- Redacción de `docs/decisiones.md` conforme se avanza

### Fuera del alcance (trabajo futuro)

- Entrenamiento de modelos de ML para detección de bots (solo se genera el conjunto
  de datos que permitiría entrenarlos)
- Migración de Flask a FastAPI o de Neo4j a otra base
- Cloudflare Zero Trust completo (basta TLS y túnel; Zero Trust se documenta como
  arquitectura de referencia)
- Biometría o reconocimiento facial
- Integración con sistemas institucionales de la BUAP
- Reescritura de los módulos de Excel y certificados que ya funcionan

**Si una petición implica algo fuera del alcance, dilo antes de implementarlo.**

---

## 9. Evaluación: métricas que hay que producir

Todo script que genere métricas debe ser reproducible y guardar resultados en
`docs/evidencias/` con fecha en el nombre.

1. **Concurrencia:** latencia p50, p95 y p99, y tasa de éxito con 60 y 90 peticiones
   simultáneas contra `server.py`
2. **Seguridad:** tasa de detección y de falsos positivos contra el banco de ataques
   (reuso de token, registro desde navegador sin la app, script directo, emulador,
   suplantación de matrícula)
3. **Tiempo de registro:** por alumno con la app, contra la línea base del pase de
   lista manual
4. **Accesibilidad:** auditoría con TalkBack criterio por criterio de WCAG 2.2

---

## 10. Accesibilidad

Se implementa en la app Android. Requisitos: `contentDescription` en todo elemento
interactivo, áreas táctiles de 48dp mínimo, háptica diferenciada para éxito y error,
anuncios por TalkBack en los cambios de estado, contraste mínimo 4.5:1.

**Nota honesta:** un escáner de QR por cámara es el caso más difícil para un usuario
ciego. Si una barrera no se puede eliminar, documéntala en `docs/decisiones.md` en
lugar de fingir que se resolvió. La tensión entre seguridad y accesibilidad es un
hallazgo válido de la tesis.

---

## 11. Convenciones

- Comentarios y mensajes de commit en español; identificadores en inglés salvo términos
  del dominio (`matricula`, `asistencia`, `docente`, `token`)
- Commits pequeños, en imperativo: `Agrega validacion de dispositivo en el canje`
- Kotlin: convenciones oficiales, sin lógica de red dentro de Composables
- Python: `ruff` para formato, type hints en código nuevo
- No commitear `build/`, `.gradle/`, `.venv/`, `.env` ni nada de la sección 6

---

## 12. Reglas de trabajo

1. **Plan mode para cambios grandes.** Antes de tocar el flujo de autenticación o el
   esquema de Neo4j, presenta el plan y espera aprobación.
2. **Tareas acotadas.** "Agrega verificación de dispositivo en el canje del token",
   no "arregla la seguridad".
3. **Explica después de implementar.** Qué se hizo, por qué ese enfoque, qué se
   descartó. El autor debe poder defender cada línea ante el jurado.
4. **No reescribas lo que funciona.** Si encuentras código mejorable pero funcional,
   anótalo como trabajo futuro en lugar de refactorizarlo.
5. **No inventes referencias bibliográficas.** Si hace falta una fuente, dilo y deja
   que el autor la busque y verifique.

---

## 13. Estado actual

### Terminado
- [x] App Android: registro de usuario y persistencia local
- [x] App Android: escáner de QR con CameraX + ML Kit
- [x] `server.py`: emisión de tokens con firma HMAC y ventana temporal
- [x] `server.py`: tokens de un solo uso y contador de reintentos
- [x] `visor.py`: proyección de QR rotativo con Socket.IO
- [x] `poolling.py`: monitor en vivo
- [x] `reporte4.py`: tablero, PDF y firma digital RSA con validación
- [x] Carga de listas en Excel y certificados firmados

### Pendiente
- [ ] Nodos Alumno, Dispositivo y BloqueoLogin en Neo4j + script de siembra
- [ ] POST /login con límite de intentos, hora_servidor y token de alcance limitado
- [ ] POST /cambiar_password
- [ ] POST /dispositivos/registrar
- [ ] Verificación ECDSA en process_checkin
- [ ] Registro de todo intento rechazado
- [ ] Android: login, Keystore, firma del canje, EncryptedSharedPreferences
- [ ] Alta de cuentas desde Excel 
- [ ] Cerrar o restringir el flujo web de registro
- [ ] Quitar `debug=True` de `visor.py`
- [ ] Restringir CORS de Socket.IO
- [ ] Externalizar dominio y configuración
- [ ] Endurecer la cookie `user_tracker`
- [ ] Archivar `reporte.py`, `reporte2.py`, `reporte3.py` en `legacy/`
- [ ] Accesibilidad en la app: TalkBack y háptica
- [ ] Banco de scripts de ataque
- [ ] Pruebas de carga con Locust
- [ ] `docs/decisiones.md`
