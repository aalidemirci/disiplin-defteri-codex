import { readFile, readdir } from "node:fs/promises";
import { resolve } from "node:path";

const root = resolve(process.cwd(), "website");
const required = ["index.html", "kilavuz.html", "gizlilik.html", "assets/styles.css", "assets/site.js"];
const forbidden = [
  /google-analytics/i,
  /googletagmanager/i,
  /facebook\.net/i,
  /hotjar/i,
  /localStorage/i,
  /document\.cookie/i,
  /<form\b/i,
  /<script[^>]+src=["']https?:/i,
  /<link[^>]+href=["']https?:[^>]+stylesheet/i,
];

for (const relative of required) {
  const content = await readFile(resolve(root, relative), "utf8");
  for (const pattern of forbidden) {
    if (pattern.test(content)) throw new Error(`${relative} yasaklı ağ/veri toplama kalıbı içeriyor: ${pattern}`);
  }
}

const files = await readdir(root, { recursive: true });
const sensitiveExtensions = [".sqlite3", ".ddbak", ".xlsx", ".xls", ".csv", ".log"];
for (const file of files) {
  if (sensitiveExtensions.some((extension) => file.toLowerCase().endsWith(extension))) {
    throw new Error(`Site paketinde hassas olabilecek dosya bulundu: ${file}`);
  }
}

console.log("Site içerik, ağ isteği ve hassas dosya kontrollerinden geçti.");
