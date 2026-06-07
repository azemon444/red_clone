import { copyFileSync, existsSync, mkdirSync, readdirSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { createDataStore, bootstrapDataDir } from "./data-store.js";
import { createPostgresDataStore } from "./postgres-store.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const defaultDataDir = join(__dirname, "..", "data");

/** Pick Supabase/Postgres in cloud, JSON files locally. */
export async function initDataStore() {
  const databaseUrl = process.env.DATABASE_URL?.trim();
  if (databaseUrl) {
    console.log("[data] using PostgreSQL (Supabase)");
    try {
      return await createPostgresDataStore(databaseUrl);
    } catch (err) {
      console.error("[data] PostgreSQL connection failed:", err.message);
      throw new Error(`Database connection failed: ${err.message}`);
    }
  }

  const activeDataDir = process.env.DATA_DIR || defaultDataDir;
  bootstrapDataDir(activeDataDir, defaultDataDir);
  console.log("[data] using JSON files at", activeDataDir);
  const store = createDataStore(activeDataDir);
  return { ...store, backend: "files" };
}
