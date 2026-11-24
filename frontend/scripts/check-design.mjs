#!/usr/bin/env node
// Mechanical design checks, taken from the "floor" of the Hallmark anti-slop design skill
// (https://github.com/nutlope/hallmark): the rules that can be verified by reading source.
// It does not replace looking at the screen; it stops the common tells from coming back.
//
//   node scripts/check-design.mjs [--skip=rule,rule] [dir ...]      (default: src)
//
// A project may skip a rule it has a reason to break (for example inline-style where no CSP
// forbids it); the skip belongs in that project's package.json script so it is visible.
//
// Exit status 1 when a rule is broken. A line may opt out with `/* design-ok: reason */`.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, extname, basename } from "node:path";

const args = process.argv.slice(2);
const skipped = new Set(args.filter((a) => a.startsWith("--skip=")).flatMap((a) => a.slice(7).split(",")));
const roots = args.filter((a) => !a.startsWith("--"));
if (roots.length === 0) roots.push("src");

const TOKEN_FILES = new Set(["tokens.css"]);
const files = [];
const walk = (path) => {
  if (statSync(path).isDirectory()) {
    for (const entry of readdirSync(path)) {
      if (entry === "node_modules" || entry === "dist" || entry === "test") continue;
      walk(join(path, entry));
    }
  } else if ([".css", ".tsx", ".ts", ".html", ".js", ".jsx"].includes(extname(path))) files.push(path);
};
roots.forEach(walk);

const rules = [
  { id: "tokens", css: true, notIn: TOKEN_FILES, re: /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/, why: "a literal colour past the token block; use a var(--color-*)" },
  { id: "font-literal", css: true, notIn: TOKEN_FILES, re: /font-family\s*:(?!\s*var\()/, why: "a literal font-family past the token block" },
  { id: "transition-all", css: true, re: /transition\s*:\s*all\b|transition-property\s*:\s*all\b/, why: "never transition: all" },
  { id: "animate-layout", css: true, re: /transition[^;{]*\b(width|height|top|left)\b/, why: "never animate width, height, top or left" },
  { id: "tracked-caps", css: true, re: /text-transform\s*:\s*uppercase|font-variant(-caps)?\s*:\s*(all-)?small-caps|letter-spacing\s*:\s*0?\.[1-9]/, why: "no tracked capitals or small caps for labels" },
  { id: "viewport-width", css: true, re: /\b100vw\b/, why: "never 100vw (it overflows with a scrollbar)" },
  { id: "overflow-hidden-x", css: true, re: /overflow-x\s*:\s*hidden/, why: "use overflow-x: clip on html and body" },
  { id: "gradient", css: true, re: /(linear|radial|conic)-gradient\(/, why: "no gradients as decoration" },
  { id: "glow", css: true, re: /box-shadow\s*:[^;]*\s\d+(px)?\s+\d+px\s+(2\d|[3-9]\d)px/, why: "no large soft glows" },
  { id: "dot-meta", jsx: true, re: />[^<>{}]*\s·\s[^<>{}]*<|`[^`]*\s·\s[^`]*`|"[^"\n]*\s·\s[^"\n]*"/, why: "no middle-dot-joined meta strings; use separate fields" },
  { id: "emoji-icon", jsx: true, re: /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u, why: "no emoji as icons" },
  { id: "arrow-link", jsx: true, re: />[^<>{}]*\s[→↗➜]\s*<|[→↗]\s*</, why: "no arrows glued to link text" },
  { id: "inline-style", jsx: true, re: /\bstyle=\{\{|\sstyle="/, why: "no inline styles (the CSP forbids them)" },
  { id: "eyebrow", jsx: true, re: /className="[^"]*\beyebrow\b/, why: "no eyebrow above a heading" },
];

let failures = 0;
for (const file of files) {
  const isCss = extname(file) === ".css";
  const text = readFileSync(file, "utf8");
  const lines = text.split("\n");
  const name = basename(file);
  lines.forEach((line, i) => {
    if (line.includes("design-ok")) return;
    for (const rule of rules) {
      if (rule.css && !isCss) continue;
      if (rule.jsx && isCss) continue;
      if (rule.notIn?.has(name) || skipped.has(rule.id)) continue;
      if (rule.re.test(line)) {
        console.log(`${file}:${i + 1}  ${rule.id}: ${rule.why}\n    ${line.trim().slice(0, 140)}`);
        failures += 1;
      }
    }
  });
  if (isCss && !TOKEN_FILES.has(name)) {
    if (/:focus-visible/.test(text) === false && /button|input|a\s*\{/.test(text)) {
      console.log(`${file}:1  focus: no :focus-visible rule in a stylesheet that styles controls`);
      failures += 1;
    }
    if (/animation\s*:|@keyframes/.test(text) && !/prefers-reduced-motion\s*:\s*reduce/.test(text)) {
      console.log(`${file}:1  reduced-motion: animation without a prefers-reduced-motion fallback`);
      failures += 1;
    }
  }
}
console.log(failures === 0 ? `design check passed (${files.length} files)` : `${failures} design finding(s)`);
process.exit(failures === 0 ? 0 : 1);
