# 🎬 Guion de Demostración en Vivo — D4-Ticket AI

### Proyecto Final DAW | Demo: ~14-16 minutos

---

> **Checklist antes de empezar:**
>
> - ✅ Navegador en URL de producción (Vercel), pantalla completa
> - ✅ Segunda pestaña abierta con la misma URL (para demo WebSocket)
> - ✅ Archivo `tesia_technical_doc.pdf` en el escritorio listo para subir
> - ✅ Haber hecho logout para que el login sea visible

---

## 1. Login y modo demo `~1 min`

*Vamos a ver el sistema en funcionamiento. Accedo a la plataforma en la URL de producción.*

*El sistema soporta autenticación con Google OAuth 2.0. El flujo es el estándar: el usuario es redirigido a Google, autoriza el acceso y el backend intercambia el código por un token, emite un JWT propio y lo almacena en una cookie HttpOnly — nunca expuesto al JavaScript del navegador por seguridad.*

*Para esta demostración utilizaré el modo demo, que genera una sesión de usuario de prueba sin necesidad de configurar credenciales de Google.*

**[ACCIÓN: Introducir el código `DAW@2026Xproyecto` y pulsar "Acceder"]**

*Al entrar accedemos directamente al panel principal. El JWT está firmado con HS256 y tiene una validez de 7 días.*

---

## 2. Panel principal `~30 seg`

*Esta es la pantalla principal. Vemos el tablero de tickets con toda la información relevante de un vistazo: numero de ticket, titulo, estado, prioridad, asignado y fecha de creación.*

*La vista tiene capacidades de **filtrado y ordenación**: podemos filtrar por estado, prioridad o usuario asignado, y ordenar por cualquier columna de forma ascendente o descendente. Esto permite a los equipos de soporte localizar rápidamente los tickets más urgentes sin tener que revisar toda la lista.*

**[ACCIÓN: Mostrar brevemente los filtros y aplicar uno — por ejemplo filtrar por prioridad Alta]**

*Deshago el filtro y paso a la vista Kanban, que es la más visual para gestionar el flujo de trabajo del equipo.*

---

## 3. Panel Kanban en tiempo real `~1.5 min`

*Este es el panel Kanban. Los tickets están organizados en columnas según su estado de flujo de trabajo: open, in progress, in review y closed.*

*El estado del tablero se gestiona con Zustand, que permite que cualquier componente — esté donde esté en la jerarquía — reciba actualizaciones sin pasar datos manualmente de padre a hijo.*

**[ACCIÓN: Arrastrar un ticket de "Por hacer" a "En progreso"]**

*El cambio se persiste inmediatamente en PostgreSQL a través de la API FastAPI. Pero lo más interesante es esto:*

**[ACCIÓN: Abrir la segunda pestaña del navegador sin refrescar]**

*En esta segunda pestaña — que simula a otro usuario conectado — el ticket ya ha cambiado de columna sin ninguna interacción. Esto es posible gracias a los WebSockets: el backend mantiene una conexión bidireccional permanente con cada cliente. Cuando alguien mueve un ticket, el servidor publica el evento en Redis Pub/Sub, y Redis se encarga de propagarlo a todas las instancias activas del servidor para que llegue a todos los usuarios conectados. Esto garantiza la escalabilidad: si mañana hay tres servidores corriendo en paralelo, todos recibirán el evento.*

**[ACCIÓN: Cerrar la segunda pestaña, volver a la principal]**

---

## 4. Notificaciones en tiempo real `~30 seg`

*Fijaos en el icono de campana de la barra superior. Las notificaciones también llegan por WebSocket y se almacenan en la tabla `notifications` de PostgreSQL con su estado de lectura.*

**[ACCIÓN: Hacer clic en la campana para mostrar las notificaciones]**

*Cada notificación tiene un estado leído/no leído. Al hacer clic se marcan como leídas, actualizando el badge en tiempo real. El sistema diferencia entre actualizaciones de tickets, alertas del sistema y notificaciones del agente de IA.*

---

## 5. Creación de ticket en vivo `~2 min`

*Voy a crear un ticket nuevo para mostrar el flujo completo.*

**[ACCIÓN: Pulsar el botón "Nuevo Ticket"]**

Rellenar con estos datos:

| Campo           | Valor                                                                                                                                                                                                                                                                                        |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Título**      | `Error de login con Google en dispositivos móviles iOS`                                                                                                                                                                                                                                      |
| **Descripción** | `Varios usuarios reportan que al intentar autenticarse con Google desde Safari en iPhone, el proceso de OAuth redirige correctamente pero la sesión no persiste. Al volver a la app aparecen como no autenticados. Afecta: iOS 17 + Safari. En Android y escritorio funciona correctamente.` |
| **Prioridad**   | `Alta`                                                                                                                                                                                                                                                                                       |
| **Estado**      | `Por hacer`                                                                                                                                                                                                                                                                                  |
| **Asignado a**  | *(asignarte a ti mismo)*                                                                                                                                                                                                                                                                     |

**[ACCIÓN: Guardar el ticket]**

*El ticket aparece al instante en el tablero. El backend asigna un UUID v4 como identificador y genera también un embedding vectorial del título y descripción en segundo plano — esto permite búsquedas semánticas sobre los propios tickets, no solo sobre la base de conocimiento.*

*Para demostrar las capacidades avanzadas de IA voy a usar este otro ticket que llevamos trabajando desde el día 6 — tiene más contexto acumulado.*

**[ACCIÓN: Hacer clic en el ticket "El progreso de estudio no se guarda en el panel de estadísticas"]**

---

## 6. URL del cliente y scraping RAG `~1.5 min`

*Dentro del detalle del ticket, veis el campo Client URL con `https://tesia.es`. Cuando este campo se rellena al crear o actualizar un ticket, el sistema lanza automáticamente en segundo plano un proceso de scraping.*

*Internamente, usamos `trafilatura` — una librería especializada en extracción de texto limpio desde páginas web — para obtener el contenido de la URL. El texto extraído se fragmenta en bloques de 500 caracteres con un solapamiento de 50 caracteres para no perder contexto en los cortes. Cada fragmento se convierte en un vector de 768 dimensiones usando la API de embeddings de Google. Estos vectores se almacenan en la tabla `knowledge_chunks` de PostgreSQL con la extensión `pgvector`, con un índice HNSW que permite búsquedas de similitud coseno en milisegundos.*

*El campo Client Summary que veis debajo es diferente: es texto libre que el operador escribe sobre el cliente y que se inyecta directamente en el prompt del LLM sin pasar por vectorización — información de contexto inmediato.*

---

## 7. Adjuntar documento técnico — RAG con PDF `~1.5 min`

*Además de la web, el sistema puede indexar documentos adjuntos. Tengo aquí el PDF con la documentación técnica interna de TesIA.*

**[ACCIÓN: En la sección de adjuntos, subir el archivo `tesia_technical_doc.pdf`]**

*Mientras se procesa, os explico qué ocurre por dentro: el backend recibe el archivo, detecta que es un PDF y usa `pypdf` para extraer el texto página a página. El texto se fragmenta igual que antes y se genera un embedding por cada fragmento. La diferencia es que estos chunks quedan asociados al ticket concreto mediante un metadato `ticket_id`, lo que permite al agente filtrar la búsqueda por ticket cuando hace el diagnóstico.*

*Si fuera un `.docx`, usaríamos `python-docx`. Si fuera `.txt`, decodificación UTF-8 directa. El sistema soporta los tres formatos de forma transparente.*

**[ACCIÓN: Verificar que aparece confirmación de que el adjunto ha sido indexado]**

*La notificación de "indexación completada" que acaba de aparecer en la campana también llegó por WebSocket — el proceso de indexación corre en background y cuando termina avisa a todos los usuarios del ticket.*

---

## 8. Chat con el agente IA — Razonamiento y Human in the Loop `~3 min`

*Ahora le voy a pedir al agente que haga algo sobre el sistema usando lenguaje natural. Pero primero, voy a aplicar un filtro para que podáis ver el cambio en tiempo real mientras el agente actúa.*

**[ACCIÓN: En el panel principal, filtrar por prioridad "Alta" + ordenar por columna fecha de creación ascendente]**

*Tenemos aquí los tickets de alta prioridad ordenados del más antiguo al más reciente — podemos ordenar por cualquier columna haciendo clic en su cabecera. El primero de la lista es nuestro candidato. Ahora abro el chat sin quitar el filtro.*

**[ACCIÓN: Abrir el chat lateral pulsando el botón "AI" — mantener el panel filtrado visible]**

Escribir en el chat:

> **"¿Cuántos tickets hay abiertos con prioridad alta? Cambia el estado del más antiguo a En Progreso y añade un comentario diciendo que estás analizando el problema."**

*El agente usa LangGraph para orquestar un ciclo de razonamiento ReAct — Reasoning and Acting. Observad el proceso: primero razona qué herramientas necesita, luego las ejecuta, lee el resultado y decide si necesita hacer algo más.*

*Fijaos en el panel — mientras el agente todavía está respondiendo en el chat, el ticket ya ha cambiado de columna. Las respuestas llegan en streaming token a token y los cambios se propagan por WebSocket en tiempo real. El agente tiene acceso a herramientas como: listar tickets, cambiar estado, añadir comentarios, buscar en la base de conocimiento y crear tickets nuevos.*

*Ahora voy a pedirle al agente una acción destructiva para mostrar otro mecanismo importante del sistema.*

Escribir en el chat:

> **"Elimina el ticket sobre el error de login en iOS que acabo de crear."**

*Observad que el agente NO ejecuta la eliminación directamente. En su lugar, el sistema muestra una confirmación — esto es lo que se llama **Human in the Loop**: para acciones irreversibles como borrar datos, el agente pausa su ejecución y espera una confirmación explícita del usuario antes de proceder. Es un mecanismo de seguridad fundamental en sistemas de IA que actúan sobre datos reales.*

**[ACCIÓN: Confirmar la eliminación en el diálogo de confirmación]**

*Una vez confirmado, el agente ejecuta la herramienta de borrado y el ticket desaparece del panel en tiempo real. Sin la confirmación, el agente cancela la operación y no toca nada.*

> ⚠️ **NOTA si falla en vivo:** Mostrar captura de pantalla preparada. No interrumpas el flujo.

**[ACCIÓN: Quitar el filtro y hacer clic en el ticket de TesIA para continuar]**

---

## 9. Panel de IA — Estado y selección de modelo `~1 min`

*Una vez ejecutadas las acciones por parte del agente, quiero mostraros el panel de estado de la IA. Al estar activo en la barra superior, registra métricas de rendimiento reales.*

**[ACCIÓN: Pulsar el botón de estado IA (icono de actividad + nombre del modelo) en la barra superior]**

*Este panel muestra en tiempo real qué proveedor y modelo está activo y las estadísticas del trabajo que acabamos de realizar: mensajes de chat enviados, acciones de herramientas invocadas por el agente y latencia media.*

*Lo más interesante es la selección de preferencia: podemos elegir entre "Automático", donde el sistema elige el mejor modelo disponible con fallback automático si uno falla, o forzar un proveedor concreto.*

**[ACCIÓN: Cambiar la preferencia de "Automático" a "GPT-4o-mini" o "Gemini 2.5 Flash"]**

*Si el modelo primario falla, el sistema hace fallback al secundario de forma transparente — el usuario ni lo nota. El contador de "Fallback used" registraría este evento. También observamos en la sección histórica el coste acumulado estimado por ejecución y la tasa de aciertos (hit rate) del RAG.*

**[ACCIÓN: Cerrar el panel]**

---

## 10. Diagnóstico IA por ticket `~1.5 min`

*Ahora el diagnóstico automático. Desde el detalle de un ticket, el Co-pilot analiza todo el contexto disponible: el título, la descripción, el historial de comentarios, la web del cliente y los adjuntos indexados.*

**[ACCIÓN: Pulsar "Diagnóstico IA" dentro del ticket de TesIA]**

*Internamente, el sistema hace dos búsquedas semánticas en paralelo sobre `knowledge_chunks`: una búsqueda global para contexto histórico y una filtrada por `ticket_id` para recuperar solo los chunks del cliente y adjuntos de este ticket concreto. Los resultados se inyectan en el prompt junto con el contexto del ticket y el LLM genera el análisis.*

*Fijaos que el diagnóstico identifica correctamente el agotamiento del pool de conexiones de PostgreSQL — esa información estaba en el PDF técnico que acabamos de adjuntar. El RAG ha funcionado.*

---

## 11. AI Reply — Borrador asistido `~1.5 min`

*Por último, el AI Reply. Permite generar borradores de respuesta profesionales para el cliente final.*

**[ACCIÓN: Ir a comentarios y pulsar "Generar borrador AI" o equivalente]**

Escribir en el campo de nota del técnico:

> **"He identificado que el pool de conexiones de PostgreSQL se agota en horas punta con más de 200 usuarios. Hemos aumentado max_connections a 200 y configurado PgBouncer como connection pooler. El problema está resuelto. Monitorización activa durante 24h."**

**[ACCIÓN: Pulsar "Generar"]**

*El técnico escribe en su lenguaje natural, sin formalismos. El LLM lee esa nota como fuente de verdad principal — con instrucción explícita de no inventar nada que no esté en la nota o el contexto — y genera un comentario profesional completo listo para enviar al cliente. El técnico puede revisarlo y editarlo antes de publicarlo.*

---

## 12. Cierre `~30 seg`

*En resumen, D4-Ticket AI integra:*

- *Tablero Kanban colaborativo con sincronización en tiempo real vía WebSockets y Redis Pub/Sub*
- *Sistema RAG que indexa webs y documentos PDF/DOCX en pgvector para dar memoria al agente*
- *Agente de IA con razonamiento ReAct orquestado por LangGraph*
- *Diagnóstico automático y generación de respuestas asistida por LLM*
- *Todo en producción: Next.js en Vercel (con Vercel Analytics integrado para monitorización de tráfico en tiempo real), FastAPI en Railway, PostgreSQL + pgvector como único almacén relacional y vectorial*

---

## ⏱ Tiempos de referencia

| Sección                                       | Tiempo estimado |
| --------------------------------------------- | --------------- |
| 1. Login y modo demo                          | 1 min           |
| 2. Panel principal + filtros                  | 30 seg          |
| 3. Kanban + WebSocket en tiempo real          | 1.5 min         |
| 4. Notificaciones                             | 30 seg          |
| 5. Creación de ticket                         | 2 min           |
| 6. URL cliente + scraping RAG                 | 1.5 min         |
| 7. Adjuntar PDF + indexación                  | 1.5 min         |
| 8. Chat con agente + Human in the Loop        | 3 min           |
| 9. Panel de IA + Selección de modelo          | 1 min           |
| 10. Diagnóstico IA                            | 1.5 min         |
| 11. AI Reply                                  | 1.5 min         |
| 12. Cierre                                    | 30 seg          |
| **Total**                                     | **~16 min**     |

> 💡 **Si vas sobrado de tiempo:** Explica más despacio la parte del RAG (§6 y §7) o usa el guion extra que aparece abajo para mostrar el Swagger UI (`/docs`) y enseñar los endpoints de la API.
>
> 💡 **Si vas justo:** Fusiona §4 (notificaciones) con §3, o salta el panel de IA (§9) mencionando el cambio de modelo rápidamente de palabra mientras escribes en el chat.

---

# 📜 Guion Extra Opcional: Interfaz Swagger e Integración de API `~2 min`

*(Utiliza esta sección al final de la demo si vas sobrado de tiempo o durante la ronda de preguntas del tribunal para demostrar fortaleza técnica).*

### 1. Introducción y Autogeneración `~30 seg`

*"Para finalizar, me gustaría mostrarles brevemente el núcleo de nuestro backend y cómo se comunica con el frontend. Gracias a **FastAPI**, no hemos tenido que redactar documentación manual propensa a errores."*

**[ACCIÓN: Abrir una pestaña nueva en el navegador con la URL: `https://proyectodaw-production-b679.up.railway.app/docs`]**

*"Esta es la interfaz interactiva de **Swagger UI**, que se autogenera en tiempo real leyendo las clases de Python y los tipados estáticos del código. Está completamente disponible en producción bajo el estándar abierto **OpenAPI 3.0**."*

### 2. Organización Arquitectónica `~30 seg`

*"Como pueden ver, toda la API está estructurada y versionada en `/api/v1`. Los endpoints están agrupados lógicamente por dominio:"*

**[ACCIÓN: Hacer scroll suave hacia abajo señalando los bloques de endpoints]**

*"Tenemos el bloque de `Auth` para la autenticación con cookies seguras, `Tickets` para la lógica principal de negocio, `Comments` y `Attachments` vinculados al almacenamiento en la nube de Cloudflare R2, y los controladores de `AI` que gestionan el agente conversacional y el motor de RAG."*

### 3. Demostración Interactiva en Vivo `~40 seg`

*"Lo más potente no es solo que documenta, sino que es **completamente interactiva**. Vamos a realizar una prueba en vivo contra el servidor de producción."*

**[ACCIÓN: Buscar y desplegar el endpoint `GET /health` (abajo del todo en la sección "Health")]**

**[ACCIÓN: Pulsar el botón "Try it out" y luego el botón azul grande "Execute"]**

*"Al ejecutarlo, vemos instantáneamente la petición CURL real generada y la respuesta HTTP 200 del servidor en formato JSON. Esto facilita enormemente la depuración del sistema y la integración de futuros desarrolladores en el equipo."*

### 4. Validación con Pydantic y Conclusión `~20 seg`

**[ACCIÓN: Hacer scroll rápido hasta el final de la página, a la sección "Schemas"]**

*"Por último, abajo vemos los **Schemas**. FastAPI utiliza la librería **Pydantic** para validar los datos tipados. Cualquier petición que no cumpla exactamente con estas estructuras (tipos incorrectos, campos obligatorios omitidos) es rechazada automáticamente por el backend con un error HTTP 422 de validación sin llegar a tocar la base de datos, lo que nos aporta una capa de seguridad y robustez nativa excelente."*
