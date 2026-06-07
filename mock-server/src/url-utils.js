export function publicBase() {
  return (process.env.PUBLIC_URL || "http://10.0.2.2:9090").replace(/\/$/, "");
}

/** Rewrite baked-in emulator URLs so one data set works locally and in the cloud. */
export function rewriteLocalUrls(value) {
  const base = publicBase();
  const json = JSON.stringify(value);
  if (!json.includes("10.0.2.2")) return value;
  return JSON.parse(json.replaceAll("http://10.0.2.2:9090", base));
}
