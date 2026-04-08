/**
 * Encore CLI sürümü package.json'daki encore.dev'den düşükse `encore version update` çalıştırır.
 * Güncelse veya karşılaştırılamazsa güncelleme atlanır (gereksiz ağ çağrısı yok).
 */
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const pkgPath = path.join(__dirname, "..", "package.json");
let pkg;
try {
  pkg = JSON.parse(fs.readFileSync(pkgPath, "utf8"));
} catch {
  process.exit(0);
}

const raw =
  (pkg.dependencies && pkg.dependencies["encore.dev"]) ||
  (pkg.devDependencies && pkg.devDependencies["encore.dev"]) ||
  "";
const desiredStr = String(raw)
  .replace(/^[\^~>=\s]+/, "")
  .trim()
  .split(/[\s,]/)[0];

function parseSemver(s) {
  const m = String(s).match(/(\d+)\.(\d+)\.(\d+)/);
  if (!m) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function cmp(a, b) {
  for (let i = 0; i < 3; i++) {
    if (a[i] < b[i]) return -1;
    if (a[i] > b[i]) return 1;
  }
  return 0;
}

function runUpdate() {
  console.log("[encore-sync] encore version update çalıştırılıyor (CLI < package.json)…");
  execSync("encore version update", { stdio: "inherit", env: process.env });
}

const want = parseSemver(desiredStr);
if (!want) {
  process.exit(0);
}

let out = "";
try {
  out = execSync("encore version", {
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
    env: process.env,
  });
} catch {
  runUpdate();
  process.exit(0);
}

const m = out.match(/(\d+)\.(\d+)\.(\d+)/);
const cur = m
  ? [Number(m[1]), Number(m[2]), Number(m[3])]
  : null;

if (!cur) {
  runUpdate();
  process.exit(0);
}

if (cmp(cur, want) < 0) {
  try {
    runUpdate();
  } catch (e) {
    console.error("[encore-sync] encore version update başarısız:", (e && e.message) || e);
    process.exit(0);
  }
} else {
  console.log(
    `[encore-sync] Encore CLI güncel (${m[0]} ≥ ${want.join(".")}), atlanıyor.`,
  );
}
