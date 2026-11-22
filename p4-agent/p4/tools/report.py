from pathlib import Path
from docx import Document

def generate_report(title: str, sections: list[dict], approved: bool,
                    output_path: str = "outputs/P4_competitive_research_brief.docx") -> dict:
    if not approved:
        return {"status": "approval_required",
                "message": "A human must approve the preview before report export."}
    doc = Document()
    doc.add_heading(title, 0)
    for section in sections:
        doc.add_heading(section.get("heading", "Section"), level=1)
        doc.add_paragraph(section.get("content", ""))
        for citation in section.get("citations", []):
            doc.add_paragraph(str(citation), style="Caption")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return {"status": "exported", "format": "docx", "path": str(path)}
