/**
 * Helpers around the attachment RAG eligibility rule.
 *
 * The backend extracts text from PDFs (`pypdf`), plain text and
 * DOCX (`python-docx`) only — images, videos and other binary
 * formats cannot be chunked into embeddings and are excluded from
 * the RAG toggle in the UI.
 */

/** MIME types the backend can ingest as RAG knowledge. */
export const RAG_ELIGIBLE_MIME_TYPES = new Set([
  "application/pdf",
  "text/plain",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
]);

/** Return `true` when an attachment of `mimeType` can be indexed for RAG. */
export function isRagEligible(mimeType: string): boolean {
  return RAG_ELIGIBLE_MIME_TYPES.has(mimeType);
}
