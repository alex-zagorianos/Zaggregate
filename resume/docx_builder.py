from io import BytesIO
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


def build_resume_docx(data: dict) -> BytesIO:
    doc = Document()
    _set_margins(doc, top=0.75, bottom=0.75, left=0.9, right=0.9)

    contact = data.get("contact", {})
    _add_name_header(doc, contact.get("name", ""))
    _add_contact_line(doc, contact)

    _add_section_heading(doc, "SUMMARY")
    p = doc.add_paragraph(data.get("summary", ""))
    if p.runs:
        p.runs[0].font.size = Pt(10)

    _add_section_heading(doc, "TECHNICAL SKILLS")
    skills_p = doc.add_paragraph(" | ".join(data.get("skills", [])))
    if skills_p.runs:
        skills_p.runs[0].font.size = Pt(10)

    _add_section_heading(doc, "EXPERIENCE")
    for job in data.get("experience", []):
        _add_job_entry(doc, job)

    _add_section_heading(doc, "EDUCATION")
    for edu in data.get("education", []):
        _add_education_entry(doc, edu)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def build_cover_letter_docx(data: dict) -> BytesIO:
    doc = Document()
    _set_margins(doc, top=1.0, bottom=1.0, left=1.25, right=1.25)

    contact = data.get("contact", {})
    _add_name_header(doc, contact.get("name", ""))
    _add_contact_line(doc, contact)
    doc.add_paragraph("")

    cover_letter = data.get("cover_letter", "")
    for para_text in cover_letter.split("\n\n"):
        p = doc.add_paragraph(para_text.strip())
        p.paragraph_format.space_after = Pt(12)
        if p.runs:
            p.runs[0].font.size = Pt(11)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def _set_margins(doc, top, bottom, left, right):
    for section in doc.sections:
        section.top_margin = Inches(top)
        section.bottom_margin = Inches(bottom)
        section.left_margin = Inches(left)
        section.right_margin = Inches(right)


def _add_name_header(doc, name: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(name)
    run.bold = True
    run.font.size = Pt(16)


def _add_contact_line(doc, contact: dict):
    parts = [contact.get("email", ""), contact.get("phone", ""), contact.get("location", "")]
    line = "  |  ".join(p for p in parts if p)
    p = doc.add_paragraph(line)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if p.runs:
        p.runs[0].font.size = Pt(10)


def _add_section_heading(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = RGBColor(0x1A, 0x1A, 0x2E)
    pPr = p._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "1A1A2E")
    pBdr.append(bottom)
    pPr.append(pBdr)


def _add_job_entry(doc, job: dict):
    p = doc.add_paragraph()
    r = p.add_run(job.get("company", ""))
    r.bold = True
    r.font.size = Pt(11)
    title_run = p.add_run(f"  —  {job.get('title', '')}")
    title_run.font.size = Pt(10)
    meta = doc.add_paragraph(f"{job.get('duration', '')}  |  {job.get('location', '')}")
    if meta.runs:
        meta.runs[0].font.size = Pt(9)
        meta.runs[0].italic = True
    meta.paragraph_format.space_after = Pt(2)
    for bullet in job.get("bullets", []):
        bp = doc.add_paragraph(bullet, style="List Bullet")
        if bp.runs:
            bp.runs[0].font.size = Pt(10)


def _add_education_entry(doc, edu: dict):
    p = doc.add_paragraph()
    r = p.add_run(edu.get("institution", ""))
    r.bold = True
    r.font.size = Pt(10)
    detail_run = p.add_run(f"  —  {edu.get('degree', '')}  ({edu.get('graduated', '')})")
    detail_run.font.size = Pt(10)
    for detail in edu.get("details", []):
        dp = doc.add_paragraph(detail, style="List Bullet")
        if dp.runs:
            dp.runs[0].font.size = Pt(10)
