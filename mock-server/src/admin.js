import { dirname, join } from "path";
import { fileURLToPath } from "url";
import express from "express";

const __dirname = dirname(fileURLToPath(import.meta.url));
const adminStatic = join(__dirname, "..", "public", "admin");

export function registerAdmin(app, dataStore, { adminPassword = "" } = {}) {
  const requireAuth = (req, res, next) => {
    if (!adminPassword) return next();
    const header = req.headers.authorization || "";
    const token = header.startsWith("Bearer ") ? header.slice(7) : "";
    if (token === adminPassword) return next();
    res.status(401).json({ error: "Unauthorized — set Authorization: Bearer <ADMIN_PASSWORD>" });
  };

  const router = express.Router();

  router.get("/api/config", (_req, res) => {
    res.json({ requiresAuth: !!adminPassword });
  });

  router.get("/api/datasets", requireAuth, (_req, res) => {
    res.json({ datasets: dataStore.list() });
  });

  router.get("/api/data/:key", requireAuth, (req, res) => {
    try {
      res.json({ key: req.params.key, data: dataStore.get(req.params.key) });
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  });

  router.put("/api/data/:key", requireAuth, async (req, res) => {
    try {
      const saved = await dataStore.set(req.params.key, req.body);
      console.log(`[admin] saved ${req.params.key}`);
      res.json({ ok: true, key: req.params.key, data: saved });
    } catch (e) {
      res.status(400).json({ error: e.message });
    }
  });

  router.post("/api/reload/:key", requireAuth, async (req, res) => {
    try {
      const data = await dataStore.reload(req.params.key);
      res.json({ ok: true, key: req.params.key, data });
    } catch (e) {
      res.status(404).json({ error: e.message });
    }
  });

  router.use(express.static(adminStatic));
  router.get("/", (_req, res) => {
    res.sendFile(join(adminStatic, "index.html"));
  });

  app.use("/admin", router);
}
