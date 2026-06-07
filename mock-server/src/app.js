import cors from "cors";
import express from "express";
import morgan from "morgan";
import { registerAdmin } from "./admin.js";
import { registerRoutes } from "./routes.js";
import { initDataStore } from "./init-data-store.js";

const PORT = Number(process.env.PORT || 9090);
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "";

function resolvePublicUrl() {
  if (process.env.PUBLIC_URL) return process.env.PUBLIC_URL.replace(/\/$/, "");
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return `http://localhost:${PORT}`;
}

export async function createApp() {
  const dataStore = await initDataStore();
  const publicUrl = resolvePublicUrl();
  process.env.PUBLIC_URL = publicUrl;

  function getCredentials() {
    const settings = dataStore.get("settings");
    return {
      demoUsername: settings.demoUsername || process.env.DEMO_USERNAME || "demo",
      demoPassword: settings.demoPassword || process.env.DEMO_PASSWORD || "demo123",
    };
  }

  const app = express();
  app.set("trust proxy", 1);
  app.use(cors());
  app.use(morgan("dev"));
  app.use(express.json({ limit: "2mb" }));
  app.use(express.urlencoded({ extended: true }));

  registerAdmin(app, dataStore, { adminPassword: ADMIN_PASSWORD });
  registerRoutes(app, { dataStore, getCredentials });

  app.locals.dataStore = dataStore;
  app.locals.publicUrl = publicUrl;

  return app;
}

export function logStartup(app) {
  const dataStore = app.locals.dataStore;
  const publicUrl = app.locals.publicUrl;
  const settings = dataStore.get("settings");
  const demoUsername = settings.demoUsername || process.env.DEMO_USERNAME || "demo";
  const demoPassword = settings.demoPassword || process.env.DEMO_PASSWORD || "demo123";

  console.log("");
  console.log("  ╔══════════════════════════════════════════════════╗");
  console.log("  ║   Santander Clone — Full Mock API Server         ║");
  console.log("  ║   Live data · Admin UI · instant app updates     ║");
  console.log("  ╚══════════════════════════════════════════════════╝");
  console.log("");
  console.log(`  Backend:   ${dataStore.backend || "files"}`);
  console.log(`  Public:    ${publicUrl}`);
  console.log(`  Admin UI:  ${publicUrl}/admin`);
  console.log(`  Health:    ${publicUrl}/health`);
  console.log(`  Login:     username=${demoUsername}  password=${demoPassword}`);
  if (ADMIN_PASSWORD) {
    console.log("  Admin auth: set Bearer token (ADMIN_PASSWORD) in admin sidebar");
  } else if (process.env.NODE_ENV === "production") {
    console.log("  WARNING: set ADMIN_PASSWORD in production — admin is open");
  }
  console.log("");
}
