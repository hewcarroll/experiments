// Render captured terminal output to a PNG "screenshot". The text is shown exactly as captured: each capture file's
// first line is the command as typed ("$ ..."), the rest is that command's output. A matching .when file supplies the
// capture time shown in the title bar. Nothing is retyped or edited, so every image can be checked against its text.
//
// Usage: node render-terminal.mjs OUT.png "Title" CAPTURE1.txt [CAPTURE2.txt ...]
// Needs playwright-core and a Chromium headless shell (set PLAYWRIGHT_CORE to the package dir and CHROMIUM to the
// binary, or keep the defaults below).
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";

const [out, title, ...caps] = process.argv.slice(2);
if (!out || !title || !caps.length) { console.error("usage: render-terminal.mjs OUT.png Title CAPTURE.txt..."); process.exit(2); }

const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const when = (fs.existsSync(caps[0].replace(/\.txt$/, ".when")) ? fs.readFileSync(caps[0].replace(/\.txt$/, ".when"), "utf8") : "")
  .replace(/^#\s*/, "").trim();
const blocks = caps.map(f => {
  const [cmd, ...rest] = fs.readFileSync(f, "utf8").replace(/\s+$/, "").split("\n");
  return `<span class="cmd">${esc(cmd)}</span>\n${esc(rest.join("\n"))}`;
}).join("\n\n");

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; background: #0d0b0a; }
.term { width: 1000px; background: #141110; border: 1px solid #3a302a; border-radius: 8px; overflow: hidden;
        font: 13.5px/1.45 "DejaVu Sans Mono", "Ubuntu Mono", "Liberation Mono", monospace; color: #ece6df; }
.bar { display: flex; justify-content: space-between; gap: 24px; padding: 7px 12px; background: #211b16;
       color: #a99d90; font: 12.5px/1.4 system-ui, sans-serif; }
pre { margin: 0; padding: 12px 14px 14px; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
.cmd { color: #eaad72; }
</style></head><body><div class="term"><div class="bar"><span>${esc(title)}</span><span>${esc(when)}</span></div><pre>${blocks}</pre></div></body></html>`;

const req = createRequire(path.join(process.env.PLAYWRIGHT_CORE || "/media/hew/Archive/Projects/a11y-triage", "package.json"));
const { chromium } = req("playwright-core");
const exe = process.env.CHROMIUM ||
  fs.globSync(path.join(process.env.HOME, ".cache/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell"))[0];
const browser = await chromium.launch({ executablePath: exe, args: ["--no-sandbox"] });
const page = await browser.newPage({ viewport: { width: 1040, height: 400 }, deviceScaleFactor: 2 });
await page.setContent(html);
await page.locator(".term").screenshot({ path: out });
await browser.close();
console.log(`wrote ${out}`);
