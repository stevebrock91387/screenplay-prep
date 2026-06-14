#!/usr/bin/env python3
"""make_cast_report.py — build a landscape cast report (PDF + DOCX) from a cast CSV.

Reads a cast CSV (columns: Role, Description, Performer — e.g. a scene-scoped cast
export), optionally fills blank descriptions from `Claude Docs/casting_editorial.json`
and/or blanks the Performer column, and writes alongside (or to --out-stem):

    <stem>.html   10pt, letter LANDSCAPE, bold headers, each role's row kept whole
    <stem>.pdf    rendered via Chrome headless (honors print CSS: page-breaks,
                  repeating header row, @page orientation — the Swift renderer does NOT)
    <stem>.docx   md2docx.js + a landscape / full-width-table patch
    <stem>.md     the Markdown source (kept; feeds the DOCX)

Examples
    # A casting-service submission sheet — descriptions filled, performers blanked:
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/make_cast_report.py" \
        --csv "Cast - Scenes 1-30.csv" \
        --title "<Project> — Cast Submission" \
        --subtitle "Scenes 1-30" \
        --blank-performer

    # Keep performers, don't backfill descriptions:
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/make_cast_report.py" --csv "<cast>.csv" --no-fill

Defaults: descriptions ARE filled from the project's casting_editorial.json when
blank; the Performer column is KEPT (pass --blank-performer to empty it). Requires
Google Chrome for the PDF (falls back to the project's Conversion Tools/html2pdf.swift
with a warning — that path can split long rows across pages). DOCX requires node +
the project's Conversion Tools/md2docx.js; if absent, the PDF still builds and DOCX
is skipped with a note. Paths resolve against $CLAUDE_PROJECT_DIR when set.
"""
import argparse, csv, html, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def repo_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def load_editorial(repo: Path) -> dict:
    p = repo / "Claude Docs" / "casting_editorial.json"
    if not p.exists():
        return {}
    roles = json.loads(p.read_text(encoding="utf-8")).get("roles", {})
    return {k.strip().upper(): " ".join((v.get("description") or "").split())
            for k, v in roles.items()}


def read_rows(csv_path: Path, editorial: dict, fill: bool, blank_perf: bool):
    rows = []
    with csv_path.open(encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        # tolerant, case-insensitive column lookup
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        rc, dc, pc = cols.get("role"), cols.get("description"), cols.get("performer")
        for r in reader:
            role = (r.get(rc, "") if rc else "").strip()
            if not role:
                continue
            desc = " ".join((r.get(dc, "") if dc else "").split())
            if not desc and fill:
                desc = editorial.get(role.upper(), "")
            perf = "" if blank_perf else (r.get(pc, "") if pc else "").strip()
            rows.append((role, desc, perf))
    return rows


def write_html(stem: Path, title: str, subtitle: str, rows):
    def h(s): return html.escape(s)
    trs = "\n".join(
        f"      <tr><td class='role'>{h(r)}</td><td class='desc'>{h(d)}</td>"
        f"<td class='perf'>{h(p)}</td></tr>" for r, d, p in rows)
    doc = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>{h(title)}</title>
<style>
  @page {{ size: 11in 8.5in; margin: 0.5in; }}   /* letter LANDSCAPE */
  html, body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; font-size: 10pt; color: #111; }}
  h1 {{ font-size: 13pt; margin: 0 0 2pt 0; }}
  p.sub {{ font-size: 10pt; color: #444; margin: 0 0 10pt 0; }}
  table {{ border-collapse: collapse; width: 100%; }}
  thead {{ display: table-header-group; }}
  th {{ font-weight: bold; text-align: left; font-size: 10pt; border-bottom: 1.5px solid #111; padding: 4pt 10pt 4pt 0; }}
  td {{ font-size: 10pt; vertical-align: top; padding: 6pt 10pt 6pt 0; border-bottom: 0.5px solid #ccc; }}
  td.role {{ font-weight: bold; white-space: nowrap; padding-right: 14pt; }}
  td.perf {{ white-space: nowrap; min-width: 1.6in; }}
  tr, td {{ break-inside: avoid; page-break-inside: avoid; }}
</style></head>
<body>
  <h1>{h(title)}</h1>
  <p class="sub">{h(subtitle)}</p>
  <table>
    <thead><tr><th>Role</th><th>Description</th><th>Performer</th></tr></thead>
    <tbody>
{trs}
    </tbody>
  </table>
</body></html>
"""
    (stem.parent / f"{stem.name}.html").write_text(doc, encoding="utf-8")


def render_pdf(stem: Path, repo: Path):
    html_path = stem.parent / f"{stem.name}.html"
    pdf_path = stem.parent / f"{stem.name}.pdf"
    if Path(CHROME).exists():
        with tempfile.TemporaryDirectory() as td:
            tin, tout = Path(td) / "in.html", Path(td) / "out.pdf"
            shutil.copy(html_path, tin)
            subprocess.run([CHROME, "--headless=new", "--disable-gpu",
                            "--no-pdf-header-footer", f"--print-to-pdf={tout}",
                            tin.as_uri()], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            shutil.copy(tout, pdf_path)
        return pdf_path, "chrome"
    # fallback — honors landscape but NOT page-break-inside (rows may split)
    swift = repo / "Conversion Tools" / "html2pdf.swift"
    subprocess.run(["swift", str(swift), str(html_path), str(pdf_path), "landscape"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("  WARNING: Chrome not found — used html2pdf.swift; long rows may split across pages.")
    return pdf_path, "swift-fallback"


def write_md(stem: Path, title: str, subtitle: str, rows):
    def m(s): return s.replace("|", r"\|")
    body = "\n".join(f"| **{m(r)}** | {m(d)} | {m(p)} |" for r, d, p in rows)
    md = (f"# {title}\n\n*{subtitle}*\n\n"
          "| Role | Description | Performer |\n| --- | --- | --- |\n" + body + "\n")
    md_path = stem.parent / f"{stem.name}.md"
    md_path.write_text(md, encoding="utf-8")
    return md_path


def build_docx(stem: Path, repo: Path, md_path: Path):
    md2docx = repo / "Conversion Tools" / "md2docx.js"
    if not md2docx.exists():
        print("  (skipped DOCX — Conversion Tools/md2docx.js not found)")
        return None
    docx_path = stem.parent / f"{stem.name}.docx"
    # md2docx.js now emits full-width AutoFit tables and accepts a landscape arg,
    # so the cast report just calls it directly — no OOXML post-patch needed.
    subprocess.run(["node", str(md2docx), str(md_path), str(docx_path), "landscape"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return docx_path


def main():
    ap = argparse.ArgumentParser(description="Build a landscape cast report (PDF + DOCX) from a cast CSV.")
    ap.add_argument("--csv", required=True, type=Path, help="cast CSV (Role, Description, Performer)")
    ap.add_argument("--title", default="Cast Report")
    ap.add_argument("--subtitle", default="")
    ap.add_argument("--out-stem", default=None, help="output path stem (no extension); default: <csv> - Report")
    ap.add_argument("--blank-performer", action="store_true", help="empty the Performer column")
    ap.add_argument("--no-fill", action="store_true", help="do NOT fill blank descriptions from casting_editorial.json")
    a = ap.parse_args()

    repo = repo_root()
    csv_path = a.csv if a.csv.is_absolute() else (repo / a.csv)
    if not csv_path.exists():
        sys.exit(f"ERROR: CSV not found: {csv_path}")
    stem = Path(a.out_stem) if a.out_stem else (csv_path.parent / f"{csv_path.stem} - Report")
    if not stem.is_absolute():
        stem = repo / stem

    editorial = {} if a.no_fill else load_editorial(repo)
    rows = read_rows(csv_path, editorial, fill=not a.no_fill, blank_perf=a.blank_performer)
    if not rows:
        sys.exit("ERROR: no roles read from the CSV.")

    write_html(stem, a.title, a.subtitle, rows)
    pdf_path, how = render_pdf(stem, repo)
    md_path = write_md(stem, a.title, a.subtitle, rows)
    docx_path = build_docx(stem, repo, md_path)

    print(f"roles: {len(rows)}  (performer {'blanked' if a.blank_performer else 'kept'}, "
          f"descriptions {'as-is' if a.no_fill else 'filled-from-editorial when blank'})")
    print(f"  PDF  ({how}): {pdf_path.name}")
    if docx_path: print(f"  DOCX (landscape, full-width): {docx_path.name}")
    print(f"  HTML/MD sources alongside.")


if __name__ == "__main__":
    main()
