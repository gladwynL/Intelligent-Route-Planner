"""Render docs/diagrams/*.mmd (Mermaid source) to high-resolution PNG and SVG.

Uses headless Chromium (Playwright) and Mermaid loaded from the jsDelivr CDN,
so no Node.js tooling is required.

    python scripts/render_diagrams.py
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMS = ROOT / "docs" / "diagrams"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<style>body{margin:0;background:#fff;font-family:Segoe UI,Arial,sans-serif}#out{display:inline-block;padding:24px}</style>
<script src="%s"></script></head><body><div id="out"></div></body></html>""" % MERMAID


def main():
    sources = sorted(DIAGRAMS.glob("*.mmd"))
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(device_scale_factor=2.5, viewport={"width": 1800, "height": 1200})
        page.set_content(PAGE)
        page.wait_for_function("window.mermaid !== undefined")
        page.evaluate("mermaid.initialize({startOnLoad:false, theme:'default', securityLevel:'strict',"
                      " flowchart:{htmlLabels:true, curve:'basis'}, er:{layoutDirection:'TB'}})")
        for src in sources:
            code = src.read_text(encoding="utf-8")
            svg = page.evaluate(
                "async (code) => { const {svg} = await mermaid.render('d' + Date.now(), code);"
                " document.getElementById('out').innerHTML = svg; return svg; }", code)
            (DIAGRAMS / f"{src.stem}.svg").write_text(svg, encoding="utf-8")
            page.locator("#out").screenshot(path=str(DIAGRAMS / f"{src.stem}.png"))
            print(f"rendered {src.name} -> {src.stem}.png / .svg")
        browser.close()


if __name__ == "__main__":
    main()
