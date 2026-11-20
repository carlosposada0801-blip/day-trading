// Builds site/claude.html: the same app, set up to run as a private page on your Claude
// account (data saved to your account instead of this browser). Run: npm run build:claude
import { readFileSync, writeFileSync } from "node:fs";

const html = readFileSync(new URL("../site/index.html", import.meta.url), "utf8");
const out = html
  // installable-app bits only apply to the website version
  .replace(/\s*<link rel="manifest"[^>]*>/, "")
  .replace(/\s*<meta name="(apple-mobile-web-app-[a-z-]+|mobile-web-app-capable)"[^>]*>/g, "")
  .replace(/\s*<link rel="apple-touch-icon"[^>]*>/, "")
  .replace('<script type="module" src="app.js"></script>',
           '<script>window.STREAKS_HOST = "claude";</script>\n  <script type="module" src="app.js"></script>');
if (!out.includes('STREAKS_HOST = "claude"')) throw new Error("couldn't add the host marker");
writeFileSync(new URL("../site/claude.html", import.meta.url), out);
console.log("wrote site/claude.html");
