import { readFileSync, existsSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";
import { DATASETS } from "./data-store.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
export const SEED_DIR = join(__dirname, "..", "data");

export function loadSeed(key) {
  const meta = DATASETS[key];
  if (!meta) throw new Error(`Unknown dataset: ${key}`);
  const path = join(SEED_DIR, meta.file);
  if (!existsSync(path)) return {};
  return JSON.parse(readFileSync(path, "utf8"));
}

export function loadAllSeeds() {
  const out = {};
  for (const key of Object.keys(DATASETS)) {
    out[key] = loadSeed(key);
  }
  return out;
}

export function isValidGlobalPosition(data) {
  const accounts = data?.contractsBalances?.accounts?.accountsList;
  return Array.isArray(accounts) && accounts.length > 0;
}

export function dashboardStats(data) {
  const cb = data?.contractsBalances || {};
  const accounts = cb.accounts?.accountsList || [];
  const cards = cb.cards?.cardList || [];
  return {
    accounts: accounts.length,
    cards: cards.length,
    segment: cb.customerSegment || null,
    totalMainBalance: cb.accounts?.totalBalancesAccounts?.totalMainBalance?.amount ?? null,
  };
}

const PT_DATE = (iso) => {
  const m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[1]}${m[2]}${m[3]}T000000000` : "20260529T000000000";
};

const PT_AMOUNT = (value) => {
  if (value == null) return { amount: 0, currencyCode: "EUR" };
  if (typeof value === "object" && "currencyCode" in value) {
    return {
      amount: Number(value.amount) || 0,
      currencyCode: value.currencyCode || "EUR",
    };
  }
  return {
    amount: Number(value.amount ?? value) || 0,
    currencyCode: value.currency || "EUR",
  };
};

/** Portugal app expects transactionsDataList + nested transactionDetails (not Omni _transactionsDataList). */
export function normalizeAccountTransactions(raw = {}) {
  if (Array.isArray(raw.transactionsDataList) && raw.transactionsDataList.length > 0) {
    return raw;
  }

  const legacy = raw._transactionsDataList;
  if (!Array.isArray(legacy) || legacy.length === 0) {
    return {
      accountId: raw.accountId || "000365542813020",
      alias: raw.alias || "Current Account",
      displayNumber: raw.displayNumber || "PT50001800036554281302058",
      transactionsDataList: [],
      _links: raw._links || {
        accountDetailsLink: "/santander/eeic/retail_accounts/000365542813020",
        _first: "/santander/eeic/retail_accounts/000365542813020/transactions?_offset=0&_limit=20",
        _next: null,
      },
    };
  }

  const accountId = raw.accountId || "000365542813020";
  return {
    accountId,
    alias: raw.alias || "Current Account",
    displayNumber: raw.displayNumber || "PT50001800036554281302058",
    transactionsDataList: legacy.map((tx) => ({
      transactionDetails: {
        transactionId: tx.transactionId,
        description: tx.description || tx.statementDesc || "",
        description2: tx.description2 || "",
        amount: PT_AMOUNT(tx.amount),
        balanceResult: PT_AMOUNT(tx.balanceResult),
        accountingDate: PT_DATE(tx.accountingDateTime || tx.creationDateTime),
        creationDate: PT_DATE(tx.creationDateTime),
        processedDate: PT_DATE(tx.processedDateTime || tx.creationDateTime),
        transactionCategory: tx.categoryCode || "TAX",
        transactionType: tx.typeCode || "CHG",
        status: "Emitida",
      },
      transactionDetailsLink:
        tx.link?.href ||
        `/santander/eeic/retail_accounts/${accountId}/transactions/${tx.transactionId}`,
    })),
    _links: {
      accountDetailsLink:
        raw._links?.accountDetailLink?.href ||
        raw._links?.accountDetailsLink ||
        `/santander/eeic/retail_accounts/${accountId}`,
      _first:
        raw._links?._first?.href ||
        `/santander/eeic/retail_accounts/${accountId}/transactions?_offset=0&_limit=20`,
      _next: raw._links?._next?.href || null,
    },
  };
}
