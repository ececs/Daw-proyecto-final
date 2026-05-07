import { describe, expect, it } from "vitest";
import { isRagEligible, RAG_ELIGIBLE_MIME_TYPES } from "./attachmentUtils";
import { formatFileSize } from "./utils";

describe("isRagEligible", () => {
  it("allows PDF files", () => {
    expect(isRagEligible("application/pdf")).toBe(true);
  });

  it("allows plain text files", () => {
    expect(isRagEligible("text/plain")).toBe(true);
  });

  it("allows DOCX files", () => {
    expect(isRagEligible(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )).toBe(true);
  });

  it("rejects JPEG images", () => {
    expect(isRagEligible("image/jpeg")).toBe(false);
  });

  it("rejects PNG images", () => {
    expect(isRagEligible("image/png")).toBe(false);
  });

  it("rejects GIF images", () => {
    expect(isRagEligible("image/gif")).toBe(false);
  });

  it("rejects WEBP images", () => {
    expect(isRagEligible("image/webp")).toBe(false);
  });

  it("rejects legacy DOC (binary) format", () => {
    expect(isRagEligible("application/msword")).toBe(false);
  });

  it("rejects unknown mime types", () => {
    expect(isRagEligible("application/octet-stream")).toBe(false);
    expect(isRagEligible("")).toBe(false);
    expect(isRagEligible("video/mp4")).toBe(false);
  });

  it("RAG_ELIGIBLE_MIME_TYPES contains exactly the three allowed types", () => {
    expect(RAG_ELIGIBLE_MIME_TYPES.size).toBe(3);
    expect(RAG_ELIGIBLE_MIME_TYPES.has("application/pdf")).toBe(true);
    expect(RAG_ELIGIBLE_MIME_TYPES.has("text/plain")).toBe(true);
    expect(RAG_ELIGIBLE_MIME_TYPES.has(
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )).toBe(true);
  });
});

describe("formatFileSize", () => {
  it("formats bytes", () => {
    expect(formatFileSize(512)).toBe("512 B");
  });

  it("formats kilobytes", () => {
    expect(formatFileSize(1536)).toBe("1.5 KB");
  });

  it("formats megabytes", () => {
    expect(formatFileSize(2.5 * 1024 * 1024)).toBe("2.5 MB");
  });

  it("formats exactly 1 KB", () => {
    expect(formatFileSize(1024)).toBe("1.0 KB");
  });

  it("formats 10 MB limit boundary", () => {
    expect(formatFileSize(10 * 1024 * 1024)).toBe("10.0 MB");
  });
});
