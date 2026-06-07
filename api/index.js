import { createApp } from "../mock-server/src/app.js";

export const config = {
  maxDuration: 60,
};

let app;

export default async function handler(req, res) {
  try {
    if (!app) app = await createApp();
    return app(req, res);
  } catch (err) {
    console.error("[api] startup error:", err);
    res.status(500).json({
      error: "Server failed to start",
      message: err?.message || String(err),
    });
  }
}
