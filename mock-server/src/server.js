import cors from "cors";
import express from "express";
import morgan from "morgan";
import { dirname, join } from "path";
import { fileURLToPath } from "url";
import { bootstrapDataDir, createDataStore } from "./data-store.js";
import { registerAdmin } from "./admin.js";
import { registerRoutes } from "./routes.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const dataDir = join(__dirname, "..", "data");

const PORT = Number(process.env.PORT || 9090);
const HOST = process.env.HOST || "0.0.0.0";
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || "";
const PUBLIC_URL = (process.env.PUBLIC_URL || `http://localhost:${PORT}`).replace(/\/$/, "");

const activeDataDir = process.env.DATA_DIR || dataDir;
bootstrapDataDir(activeDataDir, dataDir);
const dataStore = createDataStore(activeDataDir);

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

registerRoutes(app, {
  dataStore,
  getCredentials,
});

app.listen(PORT, HOST, () => {
  const { demoUsername, demoPassword } = getCredentials();
  console.log("");
  console.log("  ╔══════════════════════════════════════════════════╗");
  console.log("  ║   Santander Clone — Full Mock API Server         ║");
  console.log("  ║   Live data · Admin UI · instant app updates     ║");
  console.log("  ╚══════════════════════════════════════════════════╝");
  console.log("");
  console.log(`  Public:    ${PUBLIC_URL}`);
  console.log(`  Admin UI:  ${PUBLIC_URL}/admin`);
  console.log(`  Health:    ${PUBLIC_URL}/health`);
  console.log(`  Login:     username=${demoUsername}  password=${demoPassword}`);
  if (ADMIN_PASSWORD) {
    console.log(`  Admin auth: set Bearer token (ADMIN_PASSWORD) in admin sidebar`);
  } else if (process.env.NODE_ENV === "production") {
    console.log(`  WARNING: set ADMIN_PASSWORD in production — admin is open`);
  }
  console.log("");
});
