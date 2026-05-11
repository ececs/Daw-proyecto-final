# Guion y Estructura de Diapositivas para la Videodefensa

Este documento proporciona el esqueleto visual de las diapositivas y el guion de voz en off recomendado para tu presentación, optimizado para una duración aproximada de **20-25 minutos** (dentro del límite de 30 min) siguiendo las pautas oficiales.

---

## Estructura del Tiempo Recomendada

1. **Introducción y Contexto:** 4 minutos
2. **Arquitectura y Diseño:** 6 minutos
3. **Desarrollo Técnico Clave:** 6 minutos
4. **Demostración Práctica en Vivo:** 6 minutos
5. **Problemas, Resultados y Cierre:** 3 minutos

---

## DIAPOSITIVA 1: Portada
**Visual:**
- Título: "D4-Ticket AI: Plataforma Inteligente de Gestión de Incidencias mediante Agentes de IA"
- Tu nombre: Eudaldo Álvaro Cal Saúl
- Logotipo del ciclo / DAW.
- Fecha: Mayo 2026.

**Guion de voz en off:**
> "Hola, buenos días. Mi nombre es Eudaldo Cal y a continuación voy a presentar la defensa de mi proyecto final de ciclo superior en Desarrollo de Aplicaciones Web. Mi proyecto se titula D4-Ticket AI, una plataforma avanzada de gestión de incidencias que integra asistentes conversacionales inteligentes, búsqueda híbrida y un motor de diagnóstico AI Co-pilot. Este proyecto nació respondiendo a un reto técnico real del mercado, lo que nos ha permitido construir una solución orientada a producción desde el primer minuto."

---

## DIAPOSITIVA 2: Contextualización y Necesidad (Cap 3.2 Pautas)
**Visual:**
- Iconos representativos del problema: Procesos manuales repetitivos ❌, Búsquedas imprecisas ❌, Desconexión del conocimiento técnico ❌.
- La oportunidad: LLM (Modelos de Lenguaje) + RAG (Recuperación Aumentada).

**Guion de voz en off:**
> "Para situarnos en el problema, la gestión tradicional de tickets en empresas tecnológicas a menudo sufre de lentitud operativa. Los operadores gastan mucho tiempo buscando soluciones pasadas o leyendo documentación densa. Mi propuesta con D4-Ticket AI no es solo crear otro software de ticketing clásico, sino dotar al sistema de una 'capa cognitiva' de Inteligencia Artificial. Queremos que el sistema entienda el lenguaje natural, sugiera diagnósticos automáticamente basándose en el contexto del cliente y pueda operar autónomamente sobre la base de datos para agilizar la resolución."

---

## DIAPOSITIVA 3: Objetivos del Proyecto (Cap 3.3 Pautas)
**Visual:**
- Una tabla limpia con checkmarks verdes ✅.
- 1. Autenticación OAuth 2.0 ✅
- 2. Panel Kanban Real-Time ✅
- 3. Agente IA con Tool Calling ✅
- 4. Búsqueda Híbrida (pgvector) ✅
- 5. Notificaciones Multi-usuario ✅
- 6. Despliegue CI/CD Automatizado ✅

**Guion de voz en off:**
> "Los objetivos marcados en el anteproyecto se han cumplido al 100%. Como se observa en pantalla, hemos implementado un flujo completo que va desde la seguridad con Google OAuth, pasando por la interfaz reactiva Kanban con sincronización instantánea vía WebSockets, hasta el núcleo del proyecto: la integración de un Agente de IA construido con LangGraph que realiza búsquedas semánticas a través de pgvector y procesa información RAG para enriquecer las respuestas."

---

## DIAPOSITIVA 4: Arquitectura del Sistema (Cap 3.4 Pautas)
**Visual:**
- Imagen del diagrama de arquitectura (Front ↔ Back ↔ DB/IA).
- Tecnologías destacadas: Next.js 16, FastAPI, PostgreSQL+pgvector, Redis.

**Guion de voz en off:**
> "Entrando en el diseño técnico, hemos optado por una arquitectura moderna, desacoplada y orientada al rendimiento. En el Frontend utilizamos Next.js 16 con React 19 y Tailwind. En el Backend, hemos elegido FastAPI sobre Python debido a su tipado fuerte y su soporte nativo asíncrono, crítico para operar con flujos de IA. Para la persistencia confiamos en PostgreSQL complementado con la extensión pgvector, lo que nos evita tener que pagar por una base vectorial externa. Finalmente, Redis actúa como el corazón de la mensajería en tiempo real para propagar eventos a través de toda la infraestructura."

---

## DIAPOSITIVA 5: El Agente Inteligente (Diseño de IA)
**Visual:**
- Diagrama simplificado del ciclo ReAct (Pensar → Herramienta → Observar).
- Nombres de 3 o 4 herramientas clave: `query_tickets`, `search_knowledge`, `update_status`.

**Guion de voz en off:**
> "El motor de IA no es un simple 'wrapper' de ChatGPT. Se ha diseñado un Agente basado en el patrón ReAct utilizando el framework LangGraph. ¿Qué significa esto? Que el agente razona sobre lo que pide el usuario y decide qué herramienta técnica invocar de una caja de 10 funciones que conectan directamente con nuestra base de datos. Además, cuenta con un sistema de memoria persistente que le permite recordar hilos de conversación previos y un sistema de failover que conmuta automáticamente entre Gemini y OpenAI si uno de los proveedores falla o limita la cuota."

---

## DIAPOSITIVA 6: Implementación Destacada: Tiempo Real y Búsqueda
**Visual:**
- Fragmento de código muy breve (ejemplo: el hook websocket o la función RRF de búsqueda híbrida).
- Diagrama de secuencia breve: Cambio en Kanban ➔ Redis Pub/Sub ➔ Todos los Navegadores Actualizados.

**Guion de voz en off:**
> "En el desarrollo, quiero destacar dos retos técnicos resueltos. Primero, la colaboración en tiempo real. Implementamos WebSockets con un bus de mensajes Redis Pub/Sub, permitiendo que cuando alguien arrastra una tarjeta Kanban, esta se mueva instantáneamente en el monitor de los demás compañeros. Y segundo, la búsqueda híbrida: combinamos la búsqueda clásica por palabras clave con la búsqueda semántica basada en distancias vectoriales, fusionando ambos resultados con el algoritmo Reciprocal Rank Fusion (RRF) para dar el resultado más preciso posible al agente."

---

## DIAPOSITIVA 7: DEMOSTRACIÓN (SECCIÓN MÁS IMPORTANTE)
**Visual:**
- Un vídeo de fondo o pasar a compartir la pantalla de la aplicación real (https://daw-proyecto-final-beta.vercel.app/board).
- Guion de demostración paso a paso.

**Guion de voz en off (Mientras manejas la App):**
> "Pasamos ahora a ver el sistema en acción. 
> *(Explicas el login)*: Accedo de forma segura mediante el módulo de autenticación.
> *(Muestras el Kanban)*: Como pueden ver, aquí está el centro de mando. Puedo crear un ticket y arrastrarlo con total fluidez gracias a las actualizaciones optimistas.
> *(Abres el detalle)*: En la ficha técnica podemos subir adjuntos y añadir comentarios.
> *(ABRES EL CHAT IA)*: Y aquí es donde reside la potencia. Le voy a pedir al asistente mediante lenguaje natural: 'Dime qué tickets urgentes tenemos y quién los está llevando'. El asistente invoca su herramienta, consulta la base de datos y me responde en streaming detallando el estado real de la plataforma. Fijaos en cómo la IA es capaz incluso de reasignar un ticket a otro compañero con tan solo pedírselo de palabra."

---

## DIAPOSITIVA 8: Pruebas y Aseguramiento de la Calidad
**Visual:**
- Foto del terminal pasando los tests con un enorme `PASSED` en verde.
- Cifras clave: +200 tests Backend (pytest), +50 tests Frontend (Vitest), Cobertura E2E con Playwright.

**Guion de voz en off:**
> "Para garantizar la fiabilidad del sistema antes de pasarlo a producción, se ha construido una pirámide de pruebas muy sólida. El backend cuenta con más de 200 tests automatizados de integración que verifican cada endpoint. El frontend está protegido por 58 pruebas unitarias sobre los almacenes de estado global. Y finalmente, corremos tests 'End-to-End' con Playwright, que abren navegadores reales simulando al usuario para asegurar que los flujos críticos de negocio nunca se rompen en las nuevas actualizaciones."

---

## DIAPOSITIVA 9: Problemas Encontrados y Solución (Cap 3.7 Pautas)
**Visual:**
- Problema 1: Límites de cuota API IA ➔ Solución: Caché en Redis + Búsqueda Léxica de respaldo.
- Problema 2: Sincronización concurrente en Kanban ➔ Solución: Actualizaciones optimistas con rollback.

**Guion de voz en off:**
> "Durante el desarrollo no todo fue un camino de rosas. Nos enfrentamos al reto de los límites de peticiones en las APIs de Google embeddings al indexar documentos. Lo solucionamos implementando una caché inteligente en Redis y un sistema de degradación elegante hacia la búsqueda léxica clásica en caso de saturación de la red. También refinamos la concurrencia en el tablero Kanban mediante un sistema de rollback visual ante posibles conflictos de escritura, asegurando la consistencia del estado para todos los usuarios."

---

## DIAPOSITIVA 10: Resultados y Conclusiones (Cap 3.9 Pautas)
**Visual:**
- Bullet points de aprendizaje: Aplicación Real, Control de Complejidad, Arquitectura N-Capas.
- Futuro: Soporte multi-idioma, Celery para colas de procesamiento pesado.

**Guion de voz en off:**
> "Para finalizar, el proyecto ha concluido con un éxito rotundo, superando incluso el alcance previsto gracias a la inclusión del procesamiento de PDFs mediante RAG. Mis principales aprendizajes han sido la gestión avanzada del estado asíncrono, el despliegue automatizado en la nube mediante CI/CD y, sobre todo, comprender cómo integrar de forma útil y segura la inteligencia artificial dentro de un software corporativo clásico. A futuro, la plataforma está preparada estructuralmente para crecer, integrando colas distribuidas como Celery o extendiendo el soporte a multi-idioma."

---

## DIAPOSITIVA 11: Cierre y Agradecimiento
**Visual:**
- Texto grande: "Gracias por su atención".
- Tus datos de contacto / URL del proyecto.

**Guion de voz en off:**
> "Con esto doy por finalizada la presentación de la defensa. Ha sido un reto apasionante condensar todas las competencias adquiridas en el ciclo superior dentro de una única plataforma coherente y productiva. Quedo a su entera disposición para cualquier aclaración. Muchísimas gracias por su atención."
