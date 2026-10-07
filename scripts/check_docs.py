# -*- coding: utf-8 -*-
"""Documentation consistency checks.

    py -3 scripts/check_docs.py

Checks
  1. every relative link / #anchor in every *.md resolves
  2. zh-CN and en versions of each doc have the same heading outline (levels and numbers)
  3. spec/ble-business-commands.json commands == command index in docs/ble-common (both languages)
  4. no placeholder markers left in customer-facing docs (TBD / TO FILL / 待确认 / 待填)
Exit code 1 on any problem.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
problems = 0


def bad(msg):
    global problems
    problems += 1
    print("PROBLEM", msg)


def slug(h):
    h = h.strip().lower().replace("`", "")
    h = re.sub(r"[^\w\- ]", "", h, flags=re.UNICODE)
    return h.replace(" ", "-")


def headings(path):
    out, incode = [], False
    for l in path.read_text(encoding="utf-8").split("\n"):
        if l.startswith("```"):
            incode = not incode
            continue
        m = None if incode else re.match(r"(#{1,6})\s+(.*)", l)
        if m:
            out.append((len(m.group(1)), m.group(2).strip()))
    return out


md_files = [p for p in ROOT.rglob("*.md") if not {".git", "vendor", "dist", "node_modules"} & set(p.parts)]
anchor_cache = {}

# 1. links
for f in md_files:
    incode = False
    for n, l in enumerate(f.read_text(encoding="utf-8").split("\n"), 1):
        if l.startswith("```"):
            incode = not incode
            continue
        if incode:
            continue
        for m in re.finditer(r"\]\(([^)\s]+)\)", l):
            tgt = m.group(1)
            if tgt.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, frag = tgt.partition("#")
            tf = f if path == "" else (f.parent / path).resolve()
            if not tf.exists():
                bad(f"{f.relative_to(ROOT)}:{n} missing file {tgt}")
                continue
            if frag and tf.suffix == ".md":
                if tf not in anchor_cache:
                    anchor_cache[tf] = {slug(t) for _, t in headings(tf)}
                if frag not in anchor_cache[tf]:
                    bad(f"{f.relative_to(ROOT)}:{n} bad anchor {tgt}")

# 2. zh/en outline parity
for zh in ROOT.rglob("*.zh-CN.md"):
    if {".git", "dist"} & set(zh.parts):
        continue
    en = zh.with_name(zh.name.replace(".zh-CN.md", ".en.md"))
    if not en.exists():
        bad(f"{zh.relative_to(ROOT)} has no English counterpart")
        continue
    hz, he = headings(zh), headings(en)
    key = lambda hs: [(lvl, (re.match(r"^(\d+(?:\.\d+)*)", t).group(1) if re.match(r"^\d", t) else re.sub(r"^(附录|Appendix)\s+([A-Z]).*", r"APP-\2", t) if re.match(r"^(附录|Appendix)\s+[A-Z]", t) else "-")) for lvl, t in hs if lvl >= 2]
    kz, ke = key(hz), key(he)
    if kz != ke:
        bad(f"{zh.relative_to(ROOT)}: heading outline differs from {en.name} ({len(kz)} vs {len(ke)})")
        for a, b in zip(kz, ke):
            if a != b:
                print("   first difference:", a, "vs", b)
                break

# 3. spec vs docs index
spec = json.loads((ROOT / "spec/ble-business-commands.json").read_text(encoding="utf-8"))
spec_cmds = {c["cmd"] for c in spec["commands"]}
for lang, name in (("zh-CN", "ble-business-api.zh-CN.md"), ("en", "ble-business-api.en.md")):
    t = (ROOT / "docs/ble-common" / name).read_text(encoding="utf-8")
    m = re.search(r"\n## 4\.[^\n]*\n\n[^\n]*\n\n([^\n]+)\n", t)
    idx = set(re.findall(r"`([^`]+)`", m.group(1))) if m else set()
    if idx != spec_cmds:
        bad(f"{name}: command index differs from spec  only-in-doc={sorted(idx - spec_cmds)} only-in-spec={sorted(spec_cmds - idx)}")

# 4. placeholder markers in customer-facing docs
for f in (ROOT / "docs").rglob("*.md"):
    if f.name in ("SUMMARY.md",):
        continue
    t = f.read_text(encoding="utf-8")
    for pat in (r"【待[填确]认?】", r"\[TBD\]", r"\[TO FILL\]"):
        for m in re.finditer(pat, t):
            bad(f"{f.relative_to(ROOT)} placeholder {m.group(0)}")

print("checked", len(md_files), "markdown files; problems:", problems)
sys.exit(1 if problems else 0)
