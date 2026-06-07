import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import pg from "pg";
import { DATASETS } from "./data-store.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const SEED_DIR = join(__dirname, "..", "data");

export async function createPostgresDataStore(connectionString) {
  const pool = new pg.Pool({
    connectionString,
    ssl: connectionString.includes("localhost") ? false : { rejectUnauthorized: false },
    max: 3,
  });

  const cache = {};

  async function ensureSchema() {
    await pool.query(`
      CREATE TABLE IF NOT EXISTS datasets (
        key TEXT PRIMARY KEY,
        data JSONB NOT NULL DEFAULT '{}',
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
      )
    `);
  }

  async function seedIfEmpty() {
    const { rows } = await pool.query("SELECT COUNT(*)::int AS n FROM datasets");
    if (rows[0].n > 0) return;

    console.log("[data] seeding Supabase from bundled JSON defaults");
    for (const [key, meta] of Object.entries(DATASETS)) {
      const path = join(SEED_DIR, meta.file);
      const data = existsSync(path) ? JSON.parse(readFileSync(path, "utf8")) : {};
      await pool.query(
        `INSERT INTO datasets (key, data) VALUES ($1, $2::jsonb)
         ON CONFLICT (key) DO NOTHING`,
        [key, JSON.stringify(data)]
      );
      cache[key] = data;
    }
  }

  async function warmCache() {
    const { rows } = await pool.query("SELECT key, data FROM datasets");
    for (const row of rows) {
      cache[row.key] = row.data;
    }
    for (const key of Object.keys(DATASETS)) {
      if (cache[key] === undefined) cache[key] = {};
    }
  }

  await ensureSchema();
  await seedIfEmpty();
  await warmCache();

  function list() {
    return Object.entries(DATASETS).map(([key, meta]) => ({
      key,
      label: meta.label,
      description: meta.description,
      file: meta.file,
    }));
  }

  function get(key) {
    const meta = DATASETS[key];
    if (!meta) throw new Error(`Unknown dataset: ${key}`);
    if (cache[key] === undefined) cache[key] = {};
    return cache[key];
  }

  async function set(key, data) {
    const meta = DATASETS[key];
    if (!meta) throw new Error(`Unknown dataset: ${key}`);
    cache[key] = data;
    await pool.query(
      `INSERT INTO datasets (key, data, updated_at) VALUES ($1, $2::jsonb, NOW())
       ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = NOW()`,
      [key, JSON.stringify(data)]
    );
    return data;
  }

  async function reload(key) {
    const meta = DATASETS[key];
    if (!meta) throw new Error(`Unknown dataset: ${key}`);
    const { rows } = await pool.query("SELECT data FROM datasets WHERE key = $1", [key]);
    cache[key] = rows[0]?.data ?? {};
    return cache[key];
  }

  return {
    get,
    set,
    reload,
    list,
    backend: "postgres",
    async close() {
      await pool.end();
    },
  };
}
