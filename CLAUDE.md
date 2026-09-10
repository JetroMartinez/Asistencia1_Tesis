# CLAUDE.md — Sistema de Asistencia CU2-BUAP

Contexto permanente para Claude Code en este repositorio. Léelo completo antes de proponer cambios.

---

## 1. Contexto del proyecto

Este repositorio es el desarrollo de una **tesis de licenciatura** en Ingeniería en
Ciencias de la Computación (BUAP, Facultad de Ciencias de la Computación).

- **Título:** Automatización del pase de lista para el uso cotidiano en CU2-BUAP
- **Autor:** Jetro Eliezer Martínez Hernández
- **Fecha límite de entrega:** 7 de noviembre de 2026
- **Congelamiento de código:** 7 de noviembre 

Esto NO es un proyecto de software comercial. Es un artefacto académico que debe ser
**defendible ante un jurado**. Un sistema sencillo cuyo comportamiento está medido vale
más aquí que uno sofisticado sin evidencia.

### Implicaciones de que sea una tesis

1. **Prioriza lo medible sobre lo vistoso.** Un módulo con métricas reproducibles vale
   más que tres módulos sin evidencia.
2. **Toda decisión de diseño necesita una razón explicable.** Si eliges HMAC sobre JWT,
   escribe el porqué en `docs/decisiones.md`.
3. **Genera evidencia continuamente.** Logs, mediciones y capturas van a
   `docs/evidencias/` con fecha en el nombre.
4. **El autor debe entender cada línea.** Después de implementar algo no trivial,
   explica qué hiciste y por qué, en español y sin jerga innecesaria.

---

## 2. Stack técnico

| Capa | Tecnología |
|------|-----------|
| Móvil | Kotlin + Jetpack Compose (Android nativo, minSdk 24) |
| Cámara / QR | CameraX + ML Kit Barcode Scanning |
| Backend | Python 3.12 + FastAPI |
| Base de datos | PostgreSQL (SQLite aceptable para pruebas locales) |
| HTTP cliente | OkHttp |
| Pruebas de carga | Locust |
| Entorno de desarrollo | CachyOS (Arch Linux) |

**Paquete Android:** `mx.buap.fcc.asistencia` (NO usar `com.example.*`)

---

## 3. Estructura del repositorio

```
.
├── app/                    # Aplicación Android (Kotlin/Compose)
├── backend/
│   ├── app/                # Código FastAPI
│   ├── tests/              # Pruebas del backend
│   └── scripts/            # Scripts de ataque y pruebas de carga
├── docs/
│   ├── evidencias/         # Mediciones, logs, capturas para la tesis
│   └── decisiones.md       # Bitácora de decisiones técnicas
└── CLAUDE.md
```

---

## 4. Alcance: qué SÍ y qué NO

### Dentro del alcance (hay que terminarlo)

- App Android funcional: registro de usuario, escaneo de QR, envío de asistencia
- Backend FastAPI con endpoints de autenticación, generación de QR y registro
- **QR dinámico firmado**: token HMAC, expiración corta, un solo uso
- Detección de peticiones automatizadas **basada en reglas** (no ML)
- Device fingerprinting no invasivo (sin biometría)
- Accesibilidad: TalkBack, `contentDescription`, retroalimentación háptica
- Exportación de reportes a Excel/CSV
- Banco de pruebas de ataque y pruebas de carga con métricas

### Fuera del alcance (NO implementar, va como trabajo futuro)

- Entrenamiento de modelos de machine learning para detección de bots
  (solo se genera el conjunto de datos que permitiría entrenarlos después)
- Cloudflare Zero Trust completo (basta con TLS y un túnel; Zero Trust se
  documenta como arquitectura de referencia)
- Reconocimiento facial o cualquier biometría
- Integración con sistemas institucionales de la BUAP
- Manuales de usuario extensos (basta con uno breve)

**Si una petición implica algo fuera del alcance, dilo antes de implementarlo.**
El riesgo número uno de este proyecto es que el alcance se expanda y no se termine.

---

## 5. Modelo de seguridad (lo más importante del proyecto)

### El problema que hay que resolver

La versión inicial de la app tenía un fallo de diseño central: `enviarAsistencia()`
hacía un POST a **la URL que venía dentro del código QR**, enviando nombre y matrícula
escritos por el propio usuario. Eso significa que:

- Cualquiera puede fotografiar el QR, leer la URL y hacer `curl` desde fuera del aula
- La identidad es autodeclarada: no hay autenticación de ninguna clase
- Un QR malicioso puede cosechar matrículas de otros estudiantes

Esto invalida el argumento central de la tesis. **Corregirlo es la prioridad número uno.**

### Diseño correcto (invariantes que nunca se rompen)

1. **La URL base del servidor vive fija en la app.** El QR transporta ÚNICAMENTE un
   token opaco. Nunca se hace una petición a una URL proveniente de un código escaneado.
2. **El token es efímero y firmado.** HMAC-SHA256 del lado del servidor, con ventana
   de validez corta (30 segundos como punto de partida) y rotación continua del QR
   proyectado por el docente.
3. **El token es de un solo uso.** Se invalida en el servidor al primer canje exitoso.
4. **La identidad se autentica contra el servidor.** La matrícula no se acepta como
   texto libre del cliente; se deriva de una sesión autenticada.
5. **Los secretos nunca entran al repositorio.** Van en variables de entorno.
6. **Todo intento rechazado se registra** con motivo, marca de tiempo y metadatos.
   Ese registro es el conjunto de datos de la tesis.

### Detección de anomalías (por reglas, no ML)

Señales a considerar: peticiones sin los encabezados esperados de la app, tiempos de
respuesta imposibles para un humano, múltiples matrículas desde la misma huella de
dispositivo, reutilización de tokens, tasa de peticiones anómala, indicadores de
emulador.

Cada regla debe tener su **tasa de detección y tasa de falsos positivos medida**
contra el banco de pruebas.

---

## 6. Accesibilidad (requisito, no adorno)

Objetivo declarado: WCAG 2.2 en lo aplicable a móvil.

- Todo elemento interactivo lleva `contentDescription` significativo
- Áreas táctiles de 48dp como mínimo
- Retroalimentación háptica al confirmar registro exitoso y al fallar (patrones distintos)
- Anuncios por TalkBack en los cambios de estado de la pantalla
- Contraste mínimo 4.5:1 en texto
- La app debe ser operable completamente sin depender de la vista

**Nota honesta:** un escáner de QR por cámara es el caso más difícil para un usuario
ciego. Si una barrera no se puede eliminar, **documéntala** en `docs/decisiones.md` en
lugar de fingir que se resolvió. Documentar la tensión entre seguridad y accesibilidad
es un hallazgo válido de la tesis.

---

## 7. Evaluación: métricas que hay que producir

El componente cuantitativo de la tesis depende de estos datos. Cualquier script que los
genere debe ser reproducible y guardar resultados en `docs/evidencias/`.

1. **Concurrencia:** latencia (p50, p95, p99) y tasa de éxito con 60 y 90 peticiones
   simultáneas
2. **Seguridad:** tasa de detección y de falsos positivos por cada regla, contra el
   banco de ataques (proxy attendance, replay de token, emulador, script directo,
   GPS falso)
3. **Tiempo de registro:** por alumno, comparado contra la línea base del pase de lista
   manual
4. **Accesibilidad:** resultados de la auditoría con TalkBack, criterio por criterio

---

## 8. Convenciones

- **Comentarios y mensajes de commit en español.** Nombres de variables y funciones en
  inglés, salvo términos del dominio (`matricula`, `asistencia`, `docente`).
- Commits pequeños y frecuentes, en imperativo: `Agrega validacion HMAC del token`
- Kotlin: seguir las convenciones oficiales; nada de lógica de red en Composables
- Python: type hints obligatorios, `ruff` para formato
- Nunca commitear `build/`, `.gradle/`, `.venv/` ni archivos `.env`

---

## 9. Reglas de trabajo

1. **Usa plan mode para cambios grandes.** Antes de tocar archivos en el diseño del
   backend, el esquema de base de datos o el refactor de seguridad, presenta el plan
   y espera aprobación.
2. **Tareas acotadas.** Prefiere "crea el endpoint X con validación Y" sobre
   "implementa la seguridad".
3. **Explica después de implementar.** Un resumen breve de qué se hizo, por qué se
   eligió ese enfoque y qué alternativas se descartaron.
4. **No inventes referencias bibliográficas.** Si se necesita una fuente, dilo y deja
   que el autor la busque y verifique.
5. **Datos personales:** nunca metas datos reales de estudiantes al repositorio. Para
   pruebas, usa datos sintéticos. La BUAP es sujeto obligado en materia de protección
   de datos personales.
6. **Si algo está fuera del alcance, avísalo antes de escribirlo.**

---

## 10. Estado actual (actualizar conforme avance)

- [x] App Android: pantalla de registro y almacenamiento local
- [x] App Android: escáner de QR con CameraX + ML Kit
- [ ] Refactor de seguridad: URL base fija, QR solo con token
- [ ] Backend FastAPI: estructura base y base de datos
- [ ] Endpoint de generación de QR dinámico firmado
- [ ] Endpoint de registro de asistencia con validación
- [ ] Autenticación real de usuario
- [ ] Detección de anomalías por reglas
- [ ] Accesibilidad: TalkBack y háptica
- [ ] Exportación de reportes
- [ ] Banco de pruebas de ataque
- [ ] Pruebas de carga
