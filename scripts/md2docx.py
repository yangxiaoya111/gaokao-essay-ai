"""将 README.md 转换为 docx（用于提交"系统运行说明书"）。

用法：
    python scripts/md2docx.py README.md 系统运行说明书.docx

支持：标题、表格、代码块、有序/无序列表、引用、加粗、行内代码、图片、分隔线。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

CN_FONT = "Microsoft YaHei"


def set_cn(style, size=None):
    """为样式设置中文字体。"""
    style.font.name = "Calibri"
    if size:
        style.font.size = Pt(size)
    rpr = style.element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn("w:eastAsia"), CN_FONT)


def add_inline(paragraph, text: str) -> None:
    """解析并写入行内格式：**加粗** 与 `行内代码`。"""
    # 先按 **bold** 切分
    for seg in re.split(r"(\*\*[^*]+\*\*)", text):
        if not seg:
            continue
        if seg.startswith("**") and seg.endswith("**"):
            run = paragraph.add_run(seg[2:-2])
            run.bold = True
        else:
            # 再按 `code` 切分
            for sub in re.split(r"(`[^`]+`)", seg):
                if not sub:
                    continue
                if sub.startswith("`") and sub.endswith("`"):
                    run = paragraph.add_run(sub[1:-1])
                    run.font.name = "Consolas"
                    run.font.size = Pt(9.5)
                else:
                    paragraph.add_run(sub)


def add_hyperlink(paragraph, url, text):
    """添加超链接（降级为普通文本亦可）。"""
    run = paragraph.add_run(text)
    run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    run.font.underline = True


def convert(md_path: Path, out_path: Path) -> None:
    lines = md_path.read_text(encoding="utf-8").splitlines()
    base = md_path.parent

    doc = Document()
    set_cn(doc.styles["Normal"], 11)
    for sname in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4"):
        try:
            set_cn(doc.styles[sname])
        except KeyError:
            pass

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 空行
        if not stripped:
            i += 1
            continue

        # 分隔线
        if re.match(r"^[-*_]{3,}$", stripped):
            p = doc.add_paragraph()
            pPr = p._p.get_or_add_pPr()
            pbdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single")
            bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:space"), "1")
            bottom.set(qn("w:color"), "CCCCCC")
            pbdr.append(bottom)
            pPr.append(pbdr)
            i += 1
            continue

        # 代码块
        if stripped.startswith("```"):
            lang = stripped[3:].strip()
            i += 1
            code = []
            while i < n and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # 跳过结束的 ```
            p = doc.add_paragraph()
            p.style = doc.styles["Normal"]
            run = p.add_run("\n".join(code))
            run.font.name = "Consolas"
            run.font.size = Pt(9)
            # 浅灰底纹
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), "F5F5F5")
            pPr.append(shd)
            continue

        # 表格
        if stripped.startswith("|"):
            rows = []
            j = i
            while j < n and lines[j].strip().startswith("|"):
                cell_texts = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                rows.append(cell_texts)
                j += 1
            # 去掉分隔行（形如 | --- | --- |）
            if len(rows) >= 2 and all(re.match(r"^:?-{2,}:?$", c) for c in rows[1]):
                header = rows[0]
                body = rows[2:]
                table = doc.add_table(rows=1 + len(body), cols=len(header))
                table.style = "Light Grid Accent 1"
                for k, h in enumerate(header):
                    cell = table.rows[0].cells[k]
                    cell.text = ""
                    p = cell.paragraphs[0]
                    r = p.add_run(h)
                    r.bold = True
                for ri, row in enumerate(body, start=1):
                    for k in range(len(header)):
                        txt = row[k] if k < len(row) else ""
                        table.rows[ri].cells[k].text = txt
                doc.add_paragraph()
                i = j
                continue
            # 否则按普通段落处理
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            p = doc.add_paragraph()
            p.style = doc.styles[f"Heading {level}"]
            add_inline(p, text)
            i += 1
            continue

        # 图片
        m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", stripped)
        if m:
            alt = m.group(1)
            img_path = base / m.group(2)
            p = doc.add_paragraph()
            if img_path.exists():
                p.add_run().add_picture(str(img_path), width=Inches(6.0))
            else:
                p.add_run(f"[图片缺失：{m.group(2)}]")
            i += 1
            continue

        # 引用
        if stripped.startswith(">"):
            p = doc.add_paragraph()
            text = stripped.lstrip(">").strip()
            add_inline(p, text)
            p.paragraph_format.left_indent = Inches(0.3)
            for r in p.runs:
                r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            i += 1
            continue

        # 无序列表
        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            p = doc.add_paragraph(style="List Bullet")
            add_inline(p, m.group(1))
            i += 1
            continue

        # 有序列表
        m = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if m:
            p = doc.add_paragraph(style="List Number")
            add_inline(p, m.group(1))
            i += 1
            continue

        # 普通段落
        p = doc.add_paragraph()
        add_inline(p, stripped)
        i += 1

    doc.save(out_path)
    print(f"已生成：{out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法：python scripts/md2docx.py <输入.md> <输出.docx>")
        sys.exit(1)
    convert(Path(sys.argv[1]), Path(sys.argv[2]))
