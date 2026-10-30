// Render captured terminal output to a PNG "screenshot". The text is shown exactly as captured: each capture file's
// first line is the command as typed ("$ ..."), the rest is that command's output; any later line starting "$ " is a
// further command. A matching .when file supplies the capture note: in the title bar when every capture shares one,
// otherwise above each block. Nothing is retyped or edited, so every image can be checked against its text.
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
const note = f => {
  const w = f.replace(/\.txt$/, ".when");
  return fs.existsSync(w) ? fs.readFileSync(w, "utf8").replace(/^#\s*/, "").trim() : "";
};
const notes = caps.map(note);
const when = notes.every(n => n === notes[0]) ? notes[0] : "";
const blocks = caps.map((f, i) => {
  const lines = fs.readFileSync(f, "utf8").replace(/\s+$/, "").split("\n");
  const body = lines.map(l => l.startsWith("$ ") ? `<span class="cmd">${esc(l)}</span>` : esc(l)).join("\n");
  return (when || !notes[i] ? "" : `<span class="note"># ${esc(notes[i])}</span>\n`) + body;
}).join("\n\n");

const html = `<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; background: #0d0b0a; }
.term { width: 1000px; background: #141110; border: 1px solid #3a302a; border-radius: 8px; overflow: hidden;
        font: 13.5px/1.45 "DejaVu Sans Mono", "Ubuntu Mono", "Liberation Mono", monospace; color: #ece6df; }
.bar { display: flex; justify-content: space-between; gap: 24px; padding: 7px 12px; background: #211b16;
       color: #a99d90; font: 12.5px/1.4 system-ui, sans-serif; }
pre { margin: 0; padding: 12px 14px 14px; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
.cmd { color: #eaad72; }
.note { color: #8f8478; }
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
