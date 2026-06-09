import { existsSync, readFileSync } from "fs";
import { dirname, join, normalize } from "path";
import { fileURLToPath } from "url";
import { emptySuccess } from "./responses.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

function resolveAssetsRoot() {
  if (process.env.ASSETS_ROOT) return process.env.ASSETS_ROOT;
  const candidates = [
    join(process.cwd(), "patched-app", "assets", "default"),
    join(__dirname, "..", "..", "patched-app", "assets", "default"),
    join(__dirname, "..", "assets", "default"),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) {
      console.log("[microsite] assets root:", candidate);
      return candidate;
    }
  }
  return candidates[0];
}

const ASSETS_ROOT = resolveAssetsRoot();

const MIME = {
  json: "application/json; charset=utf-8",
  xml: "application/xml; charset=utf-8",
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  html: "text/html; charset=utf-8",
  css: "text/css; charset=utf-8",
  svg: "image/svg+xml",
};

/** Minimal 1x1 transparent PNG for missing offer/card images */
const TRANSPARENT_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64"
);

const CONFIG_OVERRIDES = {
  enableGeolocationControl: "false",
  enableContactsControl: "false",
  enableCameraControl: "false",
  enableNotificationsControl: "false",
  enablePhotoControl: "false",
  logoutTimer: "0",
};

function normalizeRelPath(requestPath) {
  let rel = requestPath.replace(/^\//, "");

  if (rel.startsWith("filesFF/")) {
    rel = rel.slice("filesFF/".length);
  }

  const plexus = rel.match(/(?:^|\/)movilidad\/files_(?:dev|qa)\/(.+)$/);
  if (plexus) {
    rel = plexus[1];
  }

  const sftp = rel.match(/^sftpgo\/webserver\/public_html\/movilidad\/files_(?:dev|qa)\/(.+)$/);
  if (sftp) {
    rel = sftp[1];
  }

  return rel;
}

function assetCandidates(rel) {
  const candidates = [rel];

  if (rel.includes("apps/SAN/") && rel.includes("offersV4.xml") && !rel.includes("/offers/")) {
    candidates.push(rel.replace("apps/SAN/", "apps/SAN/offers/"));
  }

  if (/apps\/SAN\/(en|pt)_app_config_v2\.json$/.test(rel)) {
    const lang = rel.match(/(en|pt)_app_config_v2\.json$/)[1];
    candidates.push(`apps/newArq/android/${lang}_app_config_v2.json`);
  }

  return candidates;
}

function resolveAssetPath(requestPath) {
  const rel = normalizeRelPath(requestPath);

  for (const candidate of assetCandidates(rel)) {
    const resolved = normalize(join(ASSETS_ROOT, candidate));
    if (resolved.startsWith(ASSETS_ROOT) && existsSync(resolved)) {
      return resolved;
    }
  }

  const resolved = normalize(join(ASSETS_ROOT, rel));
  if (!resolved.startsWith(ASSETS_ROOT)) {
    return null;
  }
  return existsSync(resolved) ? resolved : null;
}

function patchAppConfig(body) {
  try {
    const data = JSON.parse(body);
    if (data.defaultConfig) {
      Object.assign(data.defaultConfig, CONFIG_OVERRIDES);
    }
    return JSON.stringify(data);
  } catch {
    return body;
  }
}

function sendAsset(res, filePath, log) {
  const ext = filePath.split(".").pop()?.toLowerCase() || "";
  let body = readFileSync(filePath);

  if (filePath.endsWith("app_config_v2.json")) {
    body = Buffer.from(patchAppConfig(body.toString("utf8")), "utf8");
  }

  res.setHeader("Content-Type", MIME[ext] || "application/octet-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.status(200).send(body);
  log?.("microsite-asset", { path: filePath.replace(ASSETS_ROOT, "") });
}

export function registerMicrositeRoutes(app) {
  const handler = (req, res) => {
    const filePath = resolveAssetPath(req.path);

    if (filePath && existsSync(filePath)) {
      return sendAsset(res, filePath, (tag, meta) =>
        console.log(`[${tag}] GET ${req.path}${meta?.path || ""}`)
      );
    }

    const ext = req.path.split(".").pop()?.toLowerCase() || "";
    if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) {
      console.log(`[microsite-img-stub] GET ${req.path}`);
      res.setHeader("Content-Type", "image/png");
      return res.status(200).send(TRANSPARENT_PNG);
    }

    if (ext === "xml") {
      console.log(`[microsite-xml-miss] GET ${req.path}`);
      return res
        .status(200)
        .type("application/xml")
        .send('<?xml version="1.0" encoding="UTF-8"?><root/>');
    }

    if (ext === "json") {
      console.log(`[microsite-json-miss] GET ${req.path}`);
      return res.json(emptySuccess());
    }

    console.log(`[microsite-miss] GET ${req.path}`);
    res.status(204).end();
  };

  app.use("/microsite/filesFF", handler);
  app.use("/microsite", handler);
}
