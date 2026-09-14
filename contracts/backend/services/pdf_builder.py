from __future__ import annotations

import os
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.services.calculator import format_money, load_tariffs
from backend.services.contract_builder import (
    executor_block,
    fixed_sections_for,
    normalize_payload,
    payment_lines,
    requisites_block,
    vat_phrase,
)


def _font_candidates() -> tuple[list[Path], list[Path]]:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    normal = [
        windir / "Fonts" / "arial.ttf",
        windir / "Fonts" / "calibri.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSans.ttf"),
    ]
    bold = [
        windir / "Fonts" / "arialbd.ttf",
        windir / "Fonts" / "calibrib.ttf",
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"),
    ]
    return normal, bold


def _register_fonts() -> tuple[str, str]:
    normal_candidates, bold_candidates = _font_candidates()
    normal_path = next((p for p in normal_candidates if p.exists()), None)
    bold_path = next((p for p in bold_candidates if p.exists()), None)

    if normal_path is None:
        # Last-resort fallback. On standard Windows installations Arial is present,
        # so this branch is mainly for very unusual minimal systems.
        return "Helvetica", "Helvetica-Bold"

    pdfmetrics.registerFont(TTFont("ContractFont", str(normal_path)))
    pdfmetrics.registerFont(TTFont("ContractFontBold", str(bold_path or normal_path)))
    return "ContractFont", "ContractFontBold"


def _p(text: str) -> str:
    return escape(str(text or "")).replace("\n", "<br/>")


def _base_styles(font: str, bold_font: str) -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "normal": ParagraphStyle(
            "ContractNormal",
            parent=sample["Normal"],
            fontName=font,
            fontSize=8.5,
            leading=10.2,
            alignment=TA_LEFT,
            spaceAfter=3,
        ),
        "small": ParagraphStyle(
            "ContractSmall",
            parent=sample["Normal"],
            fontName=font,
            fontSize=7.3,
            leading=8.6,
            alignment=TA_LEFT,
        ),
        "heading": ParagraphStyle(
            "ContractHeading",
            parent=sample["Heading2"],
            fontName=bold_font,
            fontSize=9.5,
            leading=11,
            alignment=TA_CENTER,
            spaceBefore=5,
            spaceAfter=4,
        ),
        "title": ParagraphStyle(
            "ContractTitle",
            parent=sample["Heading1"],
            fontName=bold_font,
            fontSize=11.5,
            leading=13.5,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "right": ParagraphStyle(
            "ContractRight",
            parent=sample["Normal"],
            fontName=font,
            fontSize=8.5,
            leading=10.2,
            alignment=TA_RIGHT,
        ),
        "table": ParagraphStyle(
            "ContractTable",
            parent=sample["Normal"],
            fontName=font,
            fontSize=7.4,
            leading=8.6,
        ),
        "table_bold": ParagraphStyle(
            "ContractTableBold",
            parent=sample["Normal"],
            fontName=bold_font,
            fontSize=7.4,
            leading=8.6,
        ),
    }


def _left_right(left: str, right: str, styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [[Paragraph(_p(left), styles["normal"]), Paragraph(_p(right), styles["right"])]],
        colWidths=[8.8 * cm, 8.8 * cm],
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _requisites_table(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [
            Paragraph("<b>Заказчик</b>", styles["table_bold"]),
            Paragraph("<b>Исполнитель</b>", styles["table_bold"]),
        ],
        [
            Paragraph(_p(requisites_block(data)), styles["table"]),
            Paragraph(_p(executor_block()), styles["table"]),
        ],
    ]
    table = Table(rows, colWidths=[8.8 * cm, 8.8 * cm], repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return table


def _services_table(data: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    rows: list[list[Any]] = [[
        Paragraph("<b>№</b>", styles["table_bold"]),
        Paragraph("<b>Наименование услуги</b>", styles["table_bold"]),
        Paragraph("<b>Стоимость услуги,<br/>рублей</b>", styles["table_bold"]),
    ]]
    section_no = 0
    row_types = ["header"]
    for item in data["rows"]:
        if item["type"] == "section":
            section_no += 1
            no = str(section_no)
        elif item["type"] == "total":
            no = str(section_no + 1)
        else:
            no = ""
        style = styles["table_bold"] if item["type"] in {"section", "total"} else styles["table"]
        rows.append([
            Paragraph(_p(no), style),
            Paragraph(_p(item["name"]), style),
            Paragraph(_p(format_money(item["amount"])), style),
        ])
        row_types.append(item["type"])

    table = Table(rows, colWidths=[0.65 * cm, 12.0 * cm, 4.9 * cm], repeatRows=1)
    commands: list[tuple[Any, ...]] = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EEEEEE")),
    ]
    for idx, row_type in enumerate(row_types[1:], start=1):
        if row_type == "total":
            commands.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#E9ECEF")))
    table.setStyle(TableStyle(commands))
    return table


def build_pdf(payload: dict[str, Any]) -> bytes:
    """Build a standalone PDF without LibreOffice or Microsoft Word."""
    data = normalize_payload(payload)
    font, bold_font = _register_fonts()
    styles = _base_styles(font, bold_font)
    output = BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=1.6 * cm,
        leftMargin=1.6 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.4 * cm,
        title=f"Договор №{data['contract_number']}",
        author="Генератор договоров",
    )

    story: list[Any] = []
    story.append(Paragraph(
        f"ДОГОВОР<br/>ОБ ОКАЗАНИИ УСЛУГ №{_p(data['contract_number'])}",
        styles["title"],
    ))
    story.append(_left_right("г. Москва", data["contract_date_formatted"], styles))
    story.append(Paragraph(
        _p(
            f"{data.get('customer_legal_name', '')}, в лице {data.get('customer_director_position', '')} "
            f"{data.get('customer_long_name', '')}, действующего на основании {data.get('customer_basis', '')}, "
            "именуемый далее «Заказчик», с одной стороны, и"
        ),
        styles["normal"],
    ))
    story.append(Paragraph(
        _p(
            f"{load_tariffs()['executor']['name']}, именуемый далее «Исполнитель», "
            "с другой стороны, вместе именуемые стороны, заключили настоящий договор о нижеследующем:"
        ),
        styles["normal"],
    ))

    for title, paragraphs in fixed_sections_for(data):
        story.append(Paragraph(_p(title), styles["heading"]))
        for para in paragraphs:
            if title.startswith("1.") and para.startswith("1.5"):
                story.append(Paragraph(_p(
                    f"1.4. Услуги оказываются в течение {data['months']} ({data['months_text']}) месяцев. "
                    "Начало оказания услуг - не позднее 7 календарных дней с момента оплаты Исполнителем."
                ), styles["normal"]))
            story.append(Paragraph(_p(para), styles["normal"]))

    story.append(Paragraph("9. ЮРИДИЧЕСКИЕ АДРЕСА И БАНКОВСКИЕ РЕКВИЗИТЫ", styles["heading"]))
    story.append(_requisites_table(data, styles))

    story.append(PageBreak())
    story.append(Paragraph("ПРИЛОЖЕНИЕ №1", styles["right"]))
    story.append(Paragraph(
        f"к Договору №{_p(data['contract_number'])} от {_p(data['contract_date_formatted'])}",
        styles["right"],
    ))
    story.append(Spacer(1, 3))
    story.append(_left_right("г. Москва", data["contract_date_formatted"], styles))
    story.append(Paragraph(
        _p(
            f"{data.get('customer_legal_name', '')}, в лице {data.get('customer_director_position', '')} "
            f"{data.get('customer_long_name', '')}, действующего на основании {data.get('customer_basis', '')}, "
            "именуемый далее «Заказчик», с одной стороны, и"
        ), styles["normal"]
    ))
    story.append(Paragraph(
        _p(
            f"{load_tariffs()['executor']['name']}, именуемый далее «Исполнитель», "
            "с другой стороны, вместе именуемые стороны, заключили настоящий договор о нижеследующем:"
        ), styles["normal"]
    ))
    story.append(_services_table(data, styles))
    story.append(Spacer(1, 4))
    story.append(Paragraph(_p(
        f"1. Общая стоимость оказываемых Исполнителем Услуг составляет: "
        f"{format_money(data['total_price'])} ({data['total_price_text']}){vat_phrase(data)}"
    ), styles["normal"]))
    story.append(Paragraph(_p(
        "2. Указанные Услуги оказываются Заказчику для следующих объектов (точек):"
    ), styles["normal"]))
    story.append(Paragraph(_p(
        f"{data.get('org_name', '')}\nАдрес: {data.get('org_address', '')}\n"
        f"Ссылка на организацию в Яндекс картах: {data.get('maps_link', '')}"
    ), styles["normal"]))
    for line in payment_lines(data):
        story.append(Paragraph(_p(line), styles["normal"]))
    story.append(Paragraph(_p(
        "3. Оплата услуг осуществляется Заказчиком путем безналичного перевода денежных средств на "
        "расчетный счет Исполнителя, с обязательным указанием в платежном поручении реквизитов настоящего "
        "Договора или выставленного счета в полном объеме, не позднее 5 дней с момента выставления счета, "
        "в случае если Счетом не предусмотрен иной порядок оплаты."
    ), styles["normal"]))
    service_points = "1.1.-1.3" if data.get("include_reputation") else "1.1.-1.2"
    story.append(Paragraph(_p(
        f"4. В рамках оказываемых услуг, предусмотренных п.п. {service_points} договора, Исполнитель обязуется:\n"
        "- подготовить и опубликовать 2-3 новости в Яндекс.Бизнес в месяц\n"
        "- подготовить и опубликовать 8-12 сторис в Яндекс за все время договора\n"
        "- подготовить и опубликовать 40-50 позиций прайс-листа за все время договора."
    ), styles["normal"]))
    story.append(Paragraph(_p(
        f"5. Настоящее Приложение является неотъемлемой частью Договора №{data['contract_number']} "
        f"от {data['contract_date_formatted']}"
    ), styles["normal"]))
    story.append(_requisites_table(data, styles))

    doc.build(story)
    return output.getvalue()
