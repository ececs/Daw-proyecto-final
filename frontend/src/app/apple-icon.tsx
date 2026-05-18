import { ImageResponse } from "next/og";

export const size = {
  width: 180,
  height: 180,
};

export const contentType = "image/png";

export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "linear-gradient(135deg, #0f172a 0%, #2563eb 100%)",
          borderRadius: 40,
          position: "relative",
          fontFamily: "Inter, Arial, sans-serif",
        }}
      >
        <div
          style={{
            width: 112,
            height: 112,
            borderRadius: 24,
            background: "rgba(255,255,255,0.98)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "#0f172a",
            fontSize: 72,
            fontWeight: 800,
            letterSpacing: "-0.06em",
            boxShadow: "0 12px 30px rgba(15, 23, 42, 0.16)",
          }}
        >
          D
        </div>

        <div
          style={{
            position: "absolute",
            top: 24,
            right: 26,
            width: 34,
            height: 34,
            borderRadius: 999,
            background: "#67e8f9",
            boxShadow: "0 0 0 8px rgba(191, 219, 254, 0.28)",
          }}
        />
      </div>
    ),
    size
  );
}
