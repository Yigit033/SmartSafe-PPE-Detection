import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import readline from "readline";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Dosya yollari
const versionFilePath = path.join(__dirname, "..", "VERSION");
const packageJsonPath = path.join(__dirname, "..", "..", "package.json");

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(query) {
  return new Promise((resolve) => rl.question(query, resolve));
}

async function main() {
  try {
    if (!fs.existsSync(versionFilePath)) {
      console.log("⚠️ infra/VERSION bulunamadı, 1.0.0 olarak oluşturuluyor...");
      fs.writeFileSync(versionFilePath, "1.0.0", "utf8");
    }

    const currentVersion = fs.readFileSync(versionFilePath, "utf8").trim();
    console.log(`\n===================================================`);
    console.log(`🚀 Mevcut Versiyon: ${currentVersion}`);
    console.log(`===================================================`);

    const parts = currentVersion.split(".").map((val) => parseInt(val, 10));
    if (parts.length !== 3) {
      console.warn("⚠️ Versiyon formatı X.Y.Z değil, manuel giriş gerekecek.");
    }

    let fixVersion = "";
    let featureVersion = "";
    let majorVersion = "";

    if (parts.length === 3) {
      fixVersion = `${parts[0]}.${parts[1]}.${parts[2] + 1}`;
      featureVersion = `${parts[0]}.${parts[1] + 1}.0`;
      majorVersion = `${parts[0] + 1}.0.0`;
    }

    console.log("\nArtış tipini seçin:");
    if (fixVersion) console.log(`1) Fix/Patch  -> ${fixVersion}`);
    if (featureVersion) console.log(`2) Feature    -> ${featureVersion}`);
    if (majorVersion) console.log(`3) Major      -> ${majorVersion}`);
    console.log(`4) Manuel Giriş`);
    console.log(`5) Değiştirme (Sabit tut)`);

    const choice = await question("\nSeçim (1-5): ");
    let newVersion = "";

    switch (choice) {
      case "1": newVersion = fixVersion; break;
      case "2": newVersion = featureVersion; break;
      case "3": newVersion = majorVersion; break;
      case "4": newVersion = await question("Yeni versiyonu girin (örn: 1.2.0): "); break;
      case "5": newVersion = currentVersion; break;
      default:
        console.log("❌ Geçersiz seçim, iptal edildi.");
        process.exit(0);
    }

    if (!newVersion) {
      console.log("❌ Versiyon belirtilmedi, iptal edildi.");
      process.exit(0);
    }

    // infra/VERSION Güncelle
    fs.writeFileSync(versionFilePath, newVersion, "utf8");
    console.log(`✅ infra/VERSION güncellendi: ${newVersion}`);

    // root/package.json Güncelle (Opsiyonel ama önerilir)
    if (fs.existsSync(packageJsonPath)) {
      const pkg = JSON.parse(fs.readFileSync(packageJsonPath, "utf8"));
      pkg.version = newVersion;
      fs.writeFileSync(packageJsonPath, JSON.stringify(pkg, null, 2), "utf8");
      console.log(`✅ package.json güncellendi: ${newVersion}`);
    }

  } catch (error) {
    console.error("❌ Hata:", error.message);
  } finally {
    rl.close();
  }
}

main();
