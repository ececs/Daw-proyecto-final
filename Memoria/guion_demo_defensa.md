# 🎬 Guion de Demostración en Vivo — D4-Ticket AI
### Proyecto Final DAW | Tiempo estimado: 8-10 minutos

---

> **Antes de empezar:**
> - Tener el navegador abierto en la URL de producción (Vercel)
> - Tener otra pestaña lista con la misma URL (para demo de tiempo real)
> - El PDF técnico de TesIA guardado en el escritorio listo para subir
> - Modo pantalla completa activado

---

## 1. Login y modo demo

*Vamos a ver el sistema en funcionamiento. Accedo a la plataforma en la URL de producción.*
*El sistema soporta autenticación con Google OAuth 2.0, que requiere que la dirección de email esté registrada en las variables de entorno del backend. Para esta demostración utilizaré el modo demo, que genera una sesión de usuario de prueba sin necesidad de configurar credenciales de Google.*

**[ACCIÓN: Introducir el código de acceso demo y pulsar "Acceder"]**

*Como podéis ver, al entrar accedemos directamente al panel principal.*

---

## 2. Panel Kanban en tiempo real

*Este es el panel Kanban. Los tickets están organizados en columnas según su estado: Por hacer, En progreso, En revisión y Resuelto.*

*Puedo mover un ticket entre columnas con drag & drop, y el cambio se persiste inmediatamente en la base de datos.*

**[ACCIÓN: Arrastrar un ticket de "Por hacer" a "En progreso"]**

*Si abriese otra pestaña del navegador, vería el cambio reflejado al instante sin necesidad de refrescar — esto es posible gracias a los WebSockets que mantienen una conexión bidireccional permanente con el servidor.*

**[ACCIÓN OPCIONAL: Abrir segunda pestaña y mostrar el cambio en tiempo real]**

---

## 3. Creación de ticket en vivo

*Ahora voy a crear un ticket nuevo para mostrar el flujo completo de creación.*

**[ACCIÓN: Pulsar el botón "Nuevo Ticket" o el botón "+" del tablero]**

Rellenar los campos exactamente así:

| Campo | Valor |
|-------|-------|
| **Título** | `Error de login con Google en dispositivos móviles iOS` |
| **Descripción** | `Varios usuarios reportan que al intentar autenticarse con Google desde Safari en iPhone, el proceso de OAuth redirige correctamente pero la sesión no persiste. Al volver a la app aparecen como no autenticados. Afecta: iOS 17 + Safari. En Android y escritorio funciona correctamente.` |
| **Prioridad** | `Alta` |
| **Estado** | `Por hacer` |
| **Asignado a** | *(asignarte a ti mismo)* |

**[ACCIÓN: Guardar el ticket]**

*Como veis, el ticket aparece al instante en la columna correspondiente del Kanban.*

*Para mostrar las funcionalidades de Inteligencia Artificial voy a usar este otro ticket que llevamos trabajando desde el día 6, que ya tiene contexto del cliente y documentación técnica adjunta indexada.*

**[ACCIÓN: Hacer clic sobre el ticket "El progreso de estudio no se guarda en el panel de estadísticas"]**

---

## 4. Chat con el agente IA

*Ahora le voy a pedir al agente que haga algo sobre el sistema usando lenguaje natural.*

**[ACCIÓN: Abrir el chat lateral pulsando el botón "AI"]**

Escribir en el chat:

> **"¿Cuántos tickets hay abiertos con prioridad alta? Cambia el estado del más antiguo a En Progreso y añade un comentario diciendo que estás analizando el problema."**

*Observad cómo el agente razona: primero consulta los tickets, identifica el más antiguo, cambia su estado y añade el comentario; todo en una sola instrucción. Las respuestas llegan en streaming, token a token, lo que da una experiencia muy fluida.*

> ⚠️ **NOTA:** Si la demo en vivo falla, pasar a mostrar capturas de pantalla preparadas de antemano. No interrumpas el flujo de la presentación.

---

## 5. Adjuntar documento técnico (RAG)

*Una funcionalidad clave del sistema es la capacidad de indexar documentos adjuntos en la base de conocimiento vectorial para que la IA pueda recuperar información específica.*

**[ACCIÓN: Dentro del ticket de TesIA, ir a la sección de adjuntos y subir el archivo `tesia_technical_doc.pdf`]**

*Al subir este PDF con la documentación técnica interna del cliente, el sistema lo procesa en segundo plano: extrae el texto, lo fragmenta en bloques de 500 caracteres y genera embeddings vectoriales con pgvector. A partir de ese momento, el agente puede recuperar esa información en cualquier análisis.*

*Fíjate que también hemos configurado la URL del cliente — tesia.es — que el sistema ya ha scrapeado automáticamente al abrir el ticket.*

---

## 6. Diagnóstico IA por ticket

*Otra funcionalidad clave es el diagnóstico automático por ticket. Desde el detalle del ticket, puedo solicitar un diagnóstico IA que analiza el título, la descripción, los comentarios y los adjuntos indexados en RAG para proponer una solución.*

**[ACCIÓN: Pulsar el botón "Diagnóstico IA" dentro del ticket de TesIA]**

*El agente devuelve un análisis contextualizado basado en todo el conocimiento disponible: el texto del ticket, la web del cliente y el PDF técnico que acabamos de adjuntar. Podéis ver que identifica correctamente que el problema es el agotamiento del pool de conexiones de PostgreSQL en horas punta — información que estaba en el documento técnico.*

---

## 7. AI Reply — Borrador asistido

*La última funcionalidad que voy a mostrar es el AI Reply. Permite a los técnicos generar borradores de respuesta profesionales para el cliente.*

**[ACCIÓN: Ir a la sección de comentarios del ticket y pulsar "Generar borrador AI"]**

Escribir en el campo de nota del técnico:

> **"He identificado que el pool de conexiones de PostgreSQL se agota en horas punta. Hemos aumentado max_connections a 200 y configurado PgBouncer como pooler. El problema debería estar resuelto. Monitorización activa durante 24h."**

**[ACCIÓN: Pulsar "Generar borrador"]**

*El técnico escribe una nota breve con la solución y la IA genera un comentario profesional completo, reutilizando el contexto del ticket, el historial de comentarios y el conocimiento del cliente. El técnico puede editarlo antes de publicarlo.*

---

## 8. Cierre

*En resumen, D4-Ticket AI es un sistema de ticketing que combina:*
- *Colaboración en tiempo real mediante WebSockets*
- *Un agente de IA con razonamiento ReAct capaz de actuar sobre el sistema*
- *Un motor RAG que aprende de la documentación del cliente*
- *Herramientas de productividad como el diagnóstico automático y el borrador asistido*

*Todo desplegado en producción con Next.js en Vercel y FastAPI en Railway, con PostgreSQL + pgvector como único almacén de datos tanto relacional como vectorial.*

---

> **Tiempo estimado por sección:**
> | Sección | Tiempo |
> |---------|--------|
> | Login | 30s |
> | Kanban + tiempo real | 1 min |
> | Creación de ticket | 1.5 min |
> | Chat con agente IA | 2 min |
> | Adjuntar PDF | 45s |
> | Diagnóstico IA | 1 min |
> | AI Reply | 1 min |
> | Cierre | 30s |
> | **Total** | **~8.5 min** |
