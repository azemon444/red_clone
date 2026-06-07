import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";

/** @type {Record<string, { file: string, label: string, description: string }>} */
export const DATASETS = {
  settings: {
    file: "settings.json",
    label: "Login & settings",
    description: "Demo login credentials shown on pre-login screen",
  },
  "customer-info": {
    file: "customer-info.json",
    label: "Customer info",
    description: "Greeting name, email, phone, language",
  },
  "retail-customer": {
    file: "retail-customer.json",
    label: "Retail customer",
    description: "Full customer profile returned after login",
  },
  "global-position": {
    file: "global-position.json",
    label: "Dashboard (accounts & cards)",
    description: "Home screen balances, accounts, debit/credit cards",
  },
  "account-transactions": {
    file: "account-transactions.json",
    label: "Account transactions",
    description: "Movements list on Accounts screen",
  },
  "mailbox-notifications": {
    file: "mailbox-notifications.json",
    label: "Notifications",
    description: "Inbox / mailbox push notifications",
  },
  payees: {
    file: "payees.json",
    label: "Payees",
    description: "Saved transfer beneficiaries",
  },
  "mbway-cards": {
    file: "mbway-cards.json",
    label: "MB WAY cards",
    description: "Cards enrolled in MB WAY",
  },
  "monthly-balance": {
    file: "monthly-balance.json",
    label: "Monthly balance chart",
    description: "Income vs expenses per month",
  },
  "public-products-en": {
    file: "public-products-en.json",
    label: "Public products (EN)",
    description: "Pre-login product carousel (English)",
  },
  "public-products-pt": {
    file: "public-products-pt.json",
    label: "Public products (PT)",
    description: "Pre-login product carousel (Portuguese)",
  },
};

/** Copy bundled defaults into an empty persistent volume (first cloud deploy). */
export function bootstrapDataDir(targetDir, sourceDir) {
  if (!sourceDir || targetDir === sourceDir || !existsSync(sourceDir)) return;
  mkdirSync(targetDir, { recursive: true });
  const hasJson = readdirSync(targetDir).some((f) => f.endsWith(".json"));
  if (hasJson) return;
  for (const file of readdirSync(sourceDir)) {
    if (!file.endsWith(".json")) continue;
    const dest = join(targetDir, file);
    if (!existsSync(dest)) copyFileSync(join(sourceDir, file), dest);
  }
  console.log(`[data] seeded ${targetDir} from ${sourceDir}`);
}

export function createDataStore(dataDir) {
  const cache = {};

  async function reload(key) {
    const meta = DATASETS[key];
    if (!meta) throw new Error(`Unknown dataset: ${key}`);
    const path = join(dataDir, meta.file);
    if (!existsSync(path)) {
      cache[key] = {};
      return cache[key];
    }
    cache[key] = JSON.parse(readFileSync(path, "utf8"));
    return cache[key];
  }

  function get(key) {
    if (cache[key] === undefined) reload(key);
    return cache[key];
  }

  async function set(key, data) {
    const meta = DATASETS[key];
    if (!meta) throw new Error(`Unknown dataset: ${key}`);
    const path = join(dataDir, meta.file);
    writeFileSync(path, `${JSON.stringify(data, null, 2)}\n`, "utf8");
    cache[key] = data;
    return data;
  }

  function list() {
    return Object.entries(DATASETS).map(([key, meta]) => ({
      key,
      label: meta.label,
      description: meta.description,
      file: meta.file,
    }));
  }

  for (const key of Object.keys(DATASETS)) {
    try {
      reload(key);
    } catch {
      cache[key] = {};
    }
  }

  return { get, set, reload, list, dataDir, backend: "files" };
}
