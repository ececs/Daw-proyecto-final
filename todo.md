# Próximas mejoras

## 1. Tests E2E con Playwright
Objetivo:
- Automatizar el ciclo de vida crítico completo de la aplicación utilizando Playwright, validando la interacción real entre frontend, backend, base de datos y WebSockets en tiempo real.

Flujos críticos a cubrir:
- **Flujo de Acceso y Seguridad (Auth):**
  - Protección de rutas: Intentar acceder a `/board` sin estar autenticado redirige automáticamente a `/login`.
  - Login exitoso: Iniciar sesión con el usuario demo accede correctamente y mantiene la sesión al recargar la página.
- **Ciclo de Vida del Ticket (CRUD & Kanban):**
  - Creación de ticket: Abrir formulario, rellenar campos y confirmar que el ticket aparece en la columna "Por hacer" (`Todo`).
  - Transición de estado: Abrir detalle, modificar el estado a "En progreso" y validar el cambio visual de columna en el tablero.
- **Interacción Social (Comentarios y Adjuntos):**
  - Añadir comentario: Publicar un mensaje en el detalle del ticket y confirmar su aparición inmediata en el historial.
  - Subir adjunto: Cargar un archivo simulado y verificar su presencia en la lista de recursos del ticket.
- **Sincronización en Tiempo Real (WebSockets):**
  - Dos contextos de navegación simultáneos: Modificar un ticket en la ventana A y confirmar que la ventana B se actualiza al instante sin refrescar la página.
- **Asistente de IA (Copilot):**
  - Interacción con el agente: Abrir panel lateral de chat, enviar una consulta y verificar la respuesta del asistente en tiempo real con indicador de carga.

Valor:
- Añade una robusta capa de validación real de extremo a extremo.
- Complementa y expande los tests unitarios existentes en frontend y backend.
- Representa una de las señales de calidad e ingeniería de software más valoradas de cara a la evaluación del proyecto final.

## 2. RAG con adjuntos seleccionables
Objetivo:
- permitir marcar ciertos adjuntos del ticket para usarlos como contexto IA

Idea:
- toggle por adjunto tipo "usar para IA"
- extraer texto de PDF / texto plano
- indexarlo en la base de conocimiento igual que la web del cliente
- usarlo en diagnóstico y asistente

Valor:
- cierra el círculo del proyecto
- enriquece el contexto del ticket
- aporta valor claro al proyecto final de DAW

## 3. Observabilidad ligera del asistente
Objetivo:
- hacer visible el estado operativo de la IA sin montar un dashboard grande

Versión mínima:
- proveedor activo
- modelo activo
- fallback disponible
- último error o estado
- contador simple de acciones IA

Valor:
- mejora operatividad
- ayuda a depurar
- da mejor visibilidad del comportamiento del asistente
