// Types supported by the backend text-extraction pipeline (pypdf / plain read / python-docx).
// Images, videos, and binary formats are excluded — they cannot be chunked into embeddings.
export const RAG_ELIGIBLE_MIME_TYPES = new Set([
  "application/pdf",
  "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

export function isRagEligible(mimeType: string): boolean {
  return RAG_ELIGIBLE_MIME_TYPES.has(mimeType);
}
