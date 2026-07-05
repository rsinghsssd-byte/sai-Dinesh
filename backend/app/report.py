"""
report.py
---------
Builds a single, self-contained HTML report (no external assets) for a
completed job. It's downloadable as-is and can be printed to PDF from any
browser (Ctrl/Cmd+P -> Save as PDF) with no extra server-side PDF library
dependency required. If you want native PDF generation server-side, add
`weasyprint` to requirements.txt and pipe this HTML through it -- the
template below already uses print-friendly CSS (@media print) for that.
"""
from __future__ import annotations
import html
from datetime import datetime


def _score_color(score: float) -> str:
    if score >= 0.75:
        return "#c0392b"
    if score >= 0.5:
        return "#e67e22"
    if score >= 0.25:
        return "#f1c40f"
    return "#27ae60"


def generate_html_report(job_id: str, request: dict, result: dict) -> str:
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    repos = result.get("repos_analyzed", [])
    matrix = result.get("similarity_matrix", {})
    flagged = result.get("flagged_pairs_summary", [])
    large_commits = result.get("large_commit_flags", [])
    pair_details = result.get("repo_pairs", {})

    matrix_rows = ""
    for r in repos:
        cells = ""
        for c in repos:
            score = matrix.get(r, {}).get(c, 0.0)
            color = "#eee" if r == c else _score_color(score)
            text_color = "#fff" if r != c else "#333"
            cells += f'<td style="background:{color};color:{text_color};text-align:center;padding:8px;">{score:.2f}</td>'
        matrix_rows += f'<tr><th style="text-align:left;padding:8px;">{html.escape(_short(r))}</th>{cells}</tr>'

    header_cells = "".join(f'<th style="padding:8px;">{html.escape(_short(r))}</th>' for r in repos)

    flagged_rows = "".join(
        f'<tr><td>{html.escape(_short(f["repo_a"]))}</td><td>{html.escape(_short(f["repo_b"]))}</td>'
        f'<td style="text-align:center;">{f["score"]:.2f}</td>'
        f'<td style="text-align:center;">{f["flagged_files"]}</td></tr>'
        for f in flagged
    ) or '<tr><td colspan="4" style="text-align:center;color:#888;">No repository pairs exceeded the similarity threshold.</td></tr>'

    commit_rows = "".join(
        f'<tr><td>{html.escape(_short(c["repo"]))}</td><td>{html.escape(c["sha"])}</td>'
        f'<td>{html.escape(c["message"][:80])}</td>'
        f'<td style="text-align:center;">{c["lines_added"]}</td>'
        f'<td style="text-align:center;">{c["z_score"]}</td></tr>'
        for c in large_commits
    ) or '<tr><td colspan="5" style="text-align:center;color:#888;">No unusually large commits detected.</td></tr>'

    file_detail_sections = ""
    for key, pair in pair_details.items():
        if not pair["flagged_file_pairs"]:
            continue
        rows = ""
        for fp in pair["flagged_file_pairs"][:25]:
            rows += (
                f'<tr><td>{html.escape(fp["file_a"])}</td><td>{html.escape(fp["file_b"])}</td>'
                f'<td style="text-align:center;">{fp["score"]:.2f}</td>'
                f'<td style="text-align:center;">{fp["containment"]:.2f}</td>'
                f'<td style="text-align:center;">{fp["jaccard"]:.2f}</td></tr>'
            )
        msg_matches = pair.get("commit_message_matches", [])
        msg_rows = "".join(
            f'<tr><td>{html.escape(m["sha_a"])}</td><td>{html.escape(m["message_a"][:60])}</td>'
            f'<td>{html.escape(m["sha_b"])}</td><td>{html.escape(m["message_b"][:60])}</td>'
            f'<td style="text-align:center;">{m["similarity"]:.2f}</td></tr>'
            for m in msg_matches
        )
        file_detail_sections += f"""
        <h3>{html.escape(_short(pair['repo_a']))} &harr; {html.escape(_short(pair['repo_b']))}
            <span style="color:{_score_color(pair['repo_similarity_score'])};">
            (repo score: {pair['repo_similarity_score']:.2f})</span></h3>
        <table class="detail">
          <tr><th>File A</th><th>File B</th><th>Score</th><th>Containment</th><th>Jaccard</th></tr>
          {rows}
        </table>
        {"<h4>Near-identical commit messages</h4><table class='detail'><tr><th>Commit A</th><th>Message A</th><th>Commit B</th><th>Message B</th><th>Similarity</th></tr>" + msg_rows + "</table>" if msg_rows else ""}
        """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Plagiarism Detection Report - {html.escape(job_id)}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; color:#222; max-width:1000px; margin:0 auto; padding:24px; }}
  h1 {{ margin-bottom:0; }}
  .subtitle {{ color:#666; margin-top:4px; }}
  table {{ border-collapse: collapse; width:100%; margin:12px 0 28px; font-size:14px; }}
  table.matrix th, table.matrix td {{ border:1px solid #ddd; }}
  table.detail th, table.detail td {{ border:1px solid #ddd; padding:6px 8px; font-size:13px; }}
  th {{ background:#2c3e50; color:#fff; }}
  .disclaimer {{ background:#fff8e1; border-left:4px solid #f1c40f; padding:12px 16px; margin:20px 0; font-size:13px; }}
  @media print {{ body {{ padding:0; }} }}
</style>
</head>
<body>
  <h1>GitHub Repository Plagiarism Detection Report</h1>
  <p class="subtitle">Job ID: {html.escape(job_id)} &middot; Generated {generated_at} &middot;
     Language: {html.escape(request.get('language','-'))} &middot; Branch: {html.escape(request.get('branch','main'))} &middot;
     Threshold: {request.get('similarity_threshold', 0.75)}</p>

  <div class="disclaimer">
    <strong>How to read this report:</strong> Scores reflect structural code similarity after
    normalizing comments, whitespace, and identifier names, plus commit-history signals. High
    similarity indicates that a deeper manual review is warranted -- it is not, by itself, proof
    of academic or hiring-policy violation. Shared boilerplate, standard library usage, and
    common course/starter templates can also produce elevated scores.
  </div>

  <h2>Repository Similarity Matrix</h2>
  <table class="matrix">
    <tr><th></th>{header_cells}</tr>
    {matrix_rows}
  </table>

  <h2>Flagged Repository Pairs</h2>
  <table class="detail">
    <tr><th>Repo A</th><th>Repo B</th><th>Score</th><th># Flagged Files</th></tr>
    {flagged_rows}
  </table>

  <h2>Unusually Large / Sudden Commits</h2>
  <table class="detail">
    <tr><th>Repo</th><th>Commit</th><th>Message</th><th>Lines Added</th><th>Z-score</th></tr>
    {commit_rows}
  </table>

  <h2>File-Level Detail</h2>
  {file_detail_sections or '<p style="color:#888;">No flagged file pairs.</p>'}

</body>
</html>"""


def _short(repo_url: str) -> str:
    return repo_url.rstrip("/").split("/")[-1] or repo_url
