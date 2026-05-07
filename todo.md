# Próximas mejoras

## 1. Tests E2E con Playwright
Objetivo:
- automatizar 1-2 flujos críticos reales de navegador

Versión mínima recomendada:
- login demo -> board visible
- crear ticket -> aparece en lista

Valor:
- añade una capa de validación real de frontend + backend + auth
- complementa los tests backend y frontend unitarios
- mejora la señal de ingeniería del proyecto

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
