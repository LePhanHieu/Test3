"""Clinical-style PDF report generation for DermaScan AI."""

from datetime import date, datetime
from html import escape
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from reportlab.graphics.shapes import (
    Drawing,
    Rect,
)

from reportlab.lib import colors

from reportlab.lib.enums import (
    TA_CENTER,
    TA_LEFT,
    TA_RIGHT,
)

from reportlab.lib.pagesizes import A4

from reportlab.lib.styles import (
    ParagraphStyle,
    getSampleStyleSheet,
)

from reportlab.lib.units import cm

from reportlab.pdfbase import pdfmetrics

from reportlab.pdfbase.ttfonts import TTFont

from reportlab.platypus import (
    Image as RLImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..extensions import db

from ..models import (
    Report,
    SiteSetting,
)


# ============================================================
# COLORS
# ============================================================

NAVY = colors.HexColor(
    "#16324F"
)

NAVY_DARK = colors.HexColor(
    "#10283D"
)

TEAL = colors.HexColor(
    "#0F766E"
)

TEAL_LIGHT = colors.HexColor(
    "#ECFDF5"
)

GREEN = colors.HexColor(
    "#15803D"
)

GREEN_LIGHT = colors.HexColor(
    "#F0FDF4"
)

RED = colors.HexColor(
    "#B42318"
)

RED_LIGHT = colors.HexColor(
    "#FEF3F2"
)

AMBER = colors.HexColor(
    "#B7791F"
)

AMBER_LIGHT = colors.HexColor(
    "#FFFBEB"
)

SLATE_900 = colors.HexColor(
    "#17212B"
)

SLATE_700 = colors.HexColor(
    "#334155"
)

SLATE_500 = colors.HexColor(
    "#64748B"
)

SLATE_400 = colors.HexColor(
    "#94A3B8"
)

SLATE_300 = colors.HexColor(
    "#CBD5E1"
)

SLATE_200 = colors.HexColor(
    "#E2E8F0"
)

SLATE_100 = colors.HexColor(
    "#F1F5F9"
)

SLATE_50 = colors.HexColor(
    "#F8FAFC"
)

WHITE = colors.white


# ============================================================
# DISCLAIMER
# ============================================================

DISCLAIMER = (
    "Kết quả do hệ thống trí tuệ nhân tạo cung cấp "
    "chỉ có giá trị hỗ trợ tham khảo trong nghiên cứu "
    "và sàng lọc. Kết quả không thay thế chẩn đoán, "
    "tư vấn hoặc quyết định điều trị của bác sĩ/"
    "chuyên gia y tế."
)


# ============================================================
# REPORT SERVICE
# ============================================================

class ReportService:

    VERSION_RETRY_LIMIT = 5

    def __init__(
        self,
        app,
    ):

        self.app = app

        self.report_root = Path(
            app.config[
                "REPORT_FOLDER"
            ]
        ).resolve()

        self.project_root = Path(
            app.config.get(
                "PROJECT_ROOT",
                Path(__file__)
                .resolve()
                .parents[3],
            )
        ).resolve()

        (
            self.font_name,
            self.font_bold,
        ) = self._register_fonts()

        self.styles = (
            self._build_styles()
        )


    # ========================================================
    # GENERATE
    # ========================================================

    def generate(
        self,
        case,
        analysis,
        generated_by,
    ):

        safe_case_code = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            case.case_code,
        ).strip("_")


        if not safe_case_code:

            safe_case_code = (
                f"case_{case.id}"
            )


        for attempt in range(
            self.VERSION_RETRY_LIMIT
        ):

            version = self._next_version(
                case.id
            )

            relative_path = (
                Path(safe_case_code)
                / f"report_v{version}.pdf"
            )

            pdf_path = (
                self.report_root
                / relative_path
            ).resolve()

            if self.report_root not in pdf_path.parents:
                raise ValueError(
                    "Đường dẫn lưu báo cáo "
                    "không hợp lệ."
                )

            pdf_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            temporary_path = (
                pdf_path.parent
                / (
                    f".{pdf_path.stem}."
                    f"{uuid4().hex}.tmp.pdf"
                )
            )

            report = None
            published = False

            try:
                self._build_pdf(
                    temporary_path,
                    case,
                    analysis,
                    version,
                )

                # Publish without replacing an existing version. The file is
                # ready before its metadata becomes visible to other sessions.
                os.link(
                    temporary_path,
                    pdf_path,
                )
                published = True
                temporary_path.unlink()

                report = Report(
                    case_id=case.id,
                    analysis_id=(
                        analysis.id
                        if analysis
                        else None
                    ),
                    pdf_path=relative_path.as_posix(),
                    generated_by=generated_by.id,
                    report_version=version,
                )

                db.session.add(report)
                db.session.commit()

                return report

            except FileExistsError:
                db.session.rollback()
                temporary_path.unlink(
                    missing_ok=True
                )

                if (
                    attempt + 1
                    < self.VERSION_RETRY_LIMIT
                ):
                    time.sleep(0.02)
                    continue

                raise

            except IntegrityError as exc:
                db.session.rollback()
                temporary_path.unlink(
                    missing_ok=True
                )
                if published:
                    pdf_path.unlink(
                        missing_ok=True
                    )

                if (
                    self._is_version_conflict(exc)
                    and attempt + 1
                    < self.VERSION_RETRY_LIMIT
                ):
                    continue

                raise

            except Exception:
                db.session.rollback()
                temporary_path.unlink(
                    missing_ok=True
                )
                if published:
                    pdf_path.unlink(
                        missing_ok=True
                    )

                raise

        raise RuntimeError(
            "Không thể cấp phiên bản báo cáo."
        )

    @staticmethod
    def _is_version_conflict(error):
        message = str(
            getattr(error, "orig", error)
        ).lower()
        return (
            "reports.case_id"
            in message
            and "report_version"
            in message
        )


    # ========================================================
    # REPORT VERSION
    # ========================================================

    def _next_version(
        self,
        case_id,
    ):

        current = db.session.scalar(

            db.select(
                db.func.max(
                    Report.report_version
                )
            )
            .where(
                Report.case_id
                ==
                case_id
            )
        )


        return (
            int(
                current or 0
            )
            +
            1
        )


    # ========================================================
    # FONTS
    # ========================================================

    def _register_fonts(
        self,
    ):

        windows_root = os.getenv(
            "WINDIR",
            r"C:\Windows",
        )


        regular_candidates = [

            Path(windows_root)
            /
            "Fonts"
            /
            "times.ttf",

            self.project_root
            /
            "skin_cancer"
            /
            "webapp"
            /
            "assets"
            /
            "times.ttf",
        ]


        bold_candidates = [

            Path(windows_root)
            /
            "Fonts"
            /
            "timesbd.ttf",

            self.project_root
            /
            "skin_cancer"
            /
            "webapp"
            /
            "assets"
            /
            "timesbd.ttf",
        ]


        italic_candidates = [

            Path(windows_root)
            /
            "Fonts"
            /
            "timesi.ttf",

            self.project_root
            /
            "skin_cancer"
            /
            "webapp"
            /
            "assets"
            /
            "timesi.ttf",
        ]


        bold_italic_candidates = [

            Path(windows_root)
            /
            "Fonts"
            /
            "timesbi.ttf",

            self.project_root
            /
            "skin_cancer"
            /
            "webapp"
            /
            "assets"
            /
            "timesbi.ttf",
        ]


        def first_existing(
            candidates,
        ):

            for path in candidates:

                if (
                    path
                    and
                    path.is_file()
                ):

                    return path

            return None


        regular_path = (
            first_existing(
                regular_candidates
            )
        )


        bold_path = (
            first_existing(
                bold_candidates
            )
        )


        italic_path = (
            first_existing(
                italic_candidates
            )
        )


        bold_italic_path = (
            first_existing(
                bold_italic_candidates
            )
        )


        # ========================================================
        # TIMES NEW ROMAN
        # ========================================================

        if (
            regular_path
            and
            bold_path
        ):

            pdfmetrics.registerFont(
                TTFont(
                    "TimesNewRoman",
                    str(
                        regular_path
                    ),
                )
            )


            pdfmetrics.registerFont(
                TTFont(
                    "TimesNewRoman-Bold",
                    str(
                        bold_path
                    ),
                )
            )


            if italic_path:

                pdfmetrics.registerFont(
                    TTFont(
                        "TimesNewRoman-Italic",
                        str(
                            italic_path
                        ),
                    )
                )


            if bold_italic_path:

                pdfmetrics.registerFont(
                    TTFont(
                        "TimesNewRoman-BoldItalic",
                        str(
                            bold_italic_path
                        ),
                    )
                )


            pdfmetrics.registerFontFamily(

                "TimesNewRoman",

                normal=
                    "TimesNewRoman",

                bold=
                    "TimesNewRoman-Bold",

                italic=(
                    "TimesNewRoman-Italic"
                    if italic_path
                    else "TimesNewRoman"
                ),

                boldItalic=(
                    "TimesNewRoman-BoldItalic"
                    if bold_italic_path
                    else "TimesNewRoman-Bold"
                ),
            )


            return (
                "TimesNewRoman",
                "TimesNewRoman-Bold",
            )


        # ========================================================
        # FALLBACK
        # ========================================================

        return (
            "Times-Roman",
            "Times-Bold",
        )


    # ========================================================
    # STYLES
    # ========================================================

    def _build_styles(
        self,
    ):

        base = (
            getSampleStyleSheet()
        )


        return {

            # =================================================
            # HEADER
            # =================================================

            "brand": ParagraphStyle(

                "Brand",

                parent=
                    base["Normal"],

                fontName=
                    self.font_bold,

                fontSize=
                    10,

                leading=
                    13,

                textColor=
                    TEAL,
            ),


            "report_type": ParagraphStyle(

                "ReportType",

                parent=
                    base["Normal"],

                fontName=
                    self.font_bold,

                fontSize=
                    7.5,

                leading=
                    9,

                alignment=
                    TA_RIGHT,

                textColor=
                    SLATE_500,
            ),


            "title": ParagraphStyle(

                "ReportTitle",

                parent=
                    base["Title"],

                fontName=
                    self.font_bold,

                fontSize=
                    19,

                leading=
                    23,

                alignment=
                    TA_LEFT,

                textColor=
                    NAVY,

                spaceAfter=
                    2,
            ),


            "subtitle": ParagraphStyle(

                "ReportSubtitle",

                parent=
                    base["Normal"],

                fontName=
                    self.font_name,

                fontSize=
                    8.5,

                leading=
                    12,

                textColor=
                    SLATE_500,
            ),


            # =================================================
            # SECTIONS
            # =================================================

            "section": ParagraphStyle(

                "ReportSection",

                parent=
                    base["Heading2"],

                fontName=
                    self.font_bold,

                fontSize=
                    11,

                leading=
                    14,

                spaceBefore=
                    9,

                spaceAfter=
                    6,

                textColor=
                    NAVY,
            ),


            "section_small": ParagraphStyle(

                "ReportSectionSmall",

                parent=
                    base["Heading3"],

                fontName=
                    self.font_bold,

                fontSize=
                    9.5,

                leading=
                    12,

                spaceBefore=
                    6,

                spaceAfter=
                    4,

                textColor=
                    TEAL,
            ),


            # =================================================
            # BODY
            # =================================================

            "body": ParagraphStyle(

                "ReportBody",

                parent=
                    base["BodyText"],

                fontName=
                    self.font_name,

                fontSize=
                    8.5,

                leading=
                    12,

                textColor=
                    SLATE_700,
            ),


            "body_bold": ParagraphStyle(

                "ReportBodyBold",

                parent=
                    base["BodyText"],

                fontName=
                    self.font_bold,

                fontSize=
                    8.5,

                leading=
                    12,

                textColor=
                    SLATE_900,
            ),


            "small": ParagraphStyle(

                "ReportSmall",

                parent=
                    base["BodyText"],

                fontName=
                    self.font_name,

                fontSize=
                    7,

                leading=
                    10,

                textColor=
                    SLATE_500,
            ),


            "tiny": ParagraphStyle(

                "ReportTiny",

                parent=
                    base["BodyText"],

                fontName=
                    self.font_name,

                fontSize=
                    6.5,

                leading=
                    8,

                textColor=
                    SLATE_500,
            ),


            # =================================================
            # CARD
            # =================================================

            "card_label": ParagraphStyle(

                "CardLabel",

                parent=
                    base["Normal"],

                fontName=
                    self.font_bold,

                fontSize=
                    6.8,

                leading=
                    9,

                textColor=
                    SLATE_500,

                spaceAfter=
                    2,
            ),


            "card_value": ParagraphStyle(

                "CardValue",

                parent=
                    base["Normal"],

                fontName=
                    self.font_bold,

                fontSize=
                    9.5,

                leading=
                    12,

                textColor=
                    SLATE_900,
            ),


            "card_value_small":
                ParagraphStyle(

                    "CardValueSmall",

                    parent=
                        base["Normal"],

                    fontName=
                        self.font_name,

                    fontSize=
                        8,

                    leading=
                        11,

                    textColor=
                        SLATE_700,
                ),


            # =================================================
            # AI
            # =================================================

            "ai_label": ParagraphStyle(

                "AILabel",

                parent=
                    base["Normal"],

                fontName=
                    self.font_bold,

                fontSize=
                    6.5,

                leading=
                    8,

                textColor=
                    SLATE_500,
            ),


            "ai_title": ParagraphStyle(

                "AITitle",

                parent=
                    base["Normal"],

                fontName=
                    self.font_bold,

                fontSize=
                    13,

                leading=
                    16,

                textColor=
                    NAVY,
            ),


            "ai_value": ParagraphStyle(

                "AIValue",

                parent=
                    base["Normal"],

                fontName=
                    self.font_bold,

                fontSize=
                    17,

                leading=
                    20,
            ),


            # =================================================
            # TABLES
            # =================================================

            "table_label":
                ParagraphStyle(

                    "TableLabel",

                    parent=
                        base["Normal"],

                    fontName=
                        self.font_bold,

                    fontSize=
                        7.5,

                    leading=
                        10,

                    textColor=
                        SLATE_500,
                ),


            "table_value":
                ParagraphStyle(

                    "TableValue",

                    parent=
                        base["Normal"],

                    fontName=
                        self.font_name,

                    fontSize=
                        8,

                    leading=
                        11,

                    textColor=
                        SLATE_900,
                ),


            # =================================================
            # DOCTOR
            # =================================================

            "doctor_heading":
                ParagraphStyle(

                    "DoctorHeading",

                    parent=
                        base["Normal"],

                    fontName=
                        self.font_bold,

                    fontSize=
                        8,

                    leading=
                        11,

                    textColor=
                        TEAL,
                ),


            "doctor_text":
                ParagraphStyle(

                    "DoctorText",

                    parent=
                        base["BodyText"],

                    fontName=
                        self.font_name,

                    fontSize=
                        8.5,

                    leading=
                        13,

                    textColor=
                        SLATE_900,
                ),


            # =================================================
            # DISCLAIMER
            # =================================================

            "warning_title":
                ParagraphStyle(

                    "WarningTitle",

                    parent=
                        base["Normal"],

                    fontName=
                        self.font_bold,

                    fontSize=
                        8,

                    leading=
                        10,

                    textColor=
                        AMBER,
                ),


            "warning":
                ParagraphStyle(

                    "Warning",

                    parent=
                        base["BodyText"],

                    fontName=
                        self.font_name,

                    fontSize=
                        7.7,

                    leading=
                        11,

                    textColor=
                        SLATE_700,
                ),
        }


    # ========================================================
    # BUILD PDF
    # ========================================================

    def _build_pdf(
        self,
        pdf_path,
        case,
        analysis,
        version,
    ):

        setting = db.session.get(
            SiteSetting,
            1,
        )


        logo_value = (
            setting.logo_path
            if (
                setting
                and
                setting.logo_path
            )
            else
            self.app.config.get(
                "REPORT_LOGO_PATH"
            )
        )


        logo = self._asset_path(
            logo_value
        )


        site_name = self._text(
            (
                setting.site_name
                if setting
                else None
            ),
            "DermaScan AI",
        )


        patient = (
            self._patient_info(
                case
            )
        )


        result = (
            self._latest_result(
                analysis
            )
        )


        review = (
            self._latest_review(
                analysis
            )
        )


        # ====================================================
        # DOCUMENT
        # ====================================================

        doc = SimpleDocTemplate(

            str(pdf_path),

            pagesize=
                A4,

            rightMargin=
                1.35 * cm,

            leftMargin=
                1.35 * cm,

            topMargin=
                1.35 * cm,

            bottomMargin=
                1.45 * cm,

            title=(
                f"{case.case_code} – "
                f"Báo cáo phân tích v{version}"
            ),

            author=
                site_name,
        )


        story = []


        # ====================================================
        # PAGE 1
        # ====================================================

        story.extend(
            self._build_header(
                logo=
                    logo,

                site_name=
                    site_name,

                case=
                    case,

                version=
                    version,
            )
        )


        # ====================================================
        # PATIENT
        # ====================================================

        story.append(
            self._section_title(
                "01",
                "THÔNG TIN BỆNH NHÂN",
            )
        )


        story.append(
            self._patient_card(
                patient=
                    patient,

                case=
                    case,

                analysis=
                    analysis,
            )
        )


        story.append(
            Spacer(
                1,
                0.18 * cm,
            )
        )


        # ====================================================
        # AI
        # ====================================================

        story.append(
            self._section_title(
                "02",
                "KẾT QUẢ HỖ TRỢ TỪ AI",
            )
        )


        story.append(
            self._ai_summary(
                result
            )
        )


        story.append(
            Spacer(
                1,
                0.18 * cm,
            )
        )


        # ====================================================
        # IMAGES
        # ====================================================

        story.append(
            self._section_title(
                "03",
                "HÌNH ẢNH PHÂN TÍCH",
            )
        )


        image = (
            analysis.image
            if analysis
            else None
        )


        story.append(
            self._image_pair(
                (
                    image.image_path
                    if image
                    else None
                ),

                (
                    analysis.gradcam_path
                    if analysis
                    else None
                ),
            )
        )


        story.append(
            Spacer(
                1,
                0.15 * cm,
            )
        )


        # ====================================================
        # PROBABILITIES
        # ====================================================

        story.append(
            self._section_title(
                "04",
                "PHÂN BỐ XÁC SUẤT MÔ HÌNH",
            )
        )


        probabilities = (
            result.class_probabilities
            if result
            else None
        )


        story.append(
            self._probability_table(
                probabilities
            )
        )


        # ====================================================
        # PAGE 2
        # ====================================================

        story.append(
            PageBreak()
        )


        story.extend(
            self._build_page_two_header(
                site_name=
                    site_name,

                case=
                    case,

                version=
                    version,
            )
        )


        # ====================================================
        # MEASUREMENT
        # ====================================================

        story.append(
            self._section_title(
                "05",
                "ĐO LƯỜNG HÌNH ẢNH",
            )
        )


        story.append(
            self._measurement_summary(
                analysis
            )
        )


        if (
            analysis
            and
            analysis.contour_path
        ):

            story.append(
                Spacer(
                    1,
                    0.22 * cm,
                )
            )


            story.append(
                self._contour_panel(
                    analysis.contour_path
                )
            )


        story.append(
            Spacer(
                1,
                0.18 * cm,
            )
        )


        # ====================================================
        # DOCTOR DIAGNOSIS
        # ====================================================

        story.append(
            self._section_title(
                "06",
                "CHẨN ĐOÁN VÀ NHẬN XÉT CỦA BÁC SĨ",
            )
        )


        story.append(
            self._doctor_review_card(
                review=
                    review,

                doctor=
                    (
                        review.doctor
                        if review
                        else case.doctor
                    ),
            )
        )


        story.append(
            Spacer(
                1,
                0.24 * cm,
            )
        )


        # ====================================================
        # DISCLAIMER
        # ====================================================

        story.append(
            self._section_title(
                "07",
                "LƯU Ý LÂM SÀNG",
            )
        )


        story.append(
            self._warning_panel()
        )


        # ====================================================
        # BUILD
        # ====================================================

        def footer(
            canvas,
            document,
        ):

            self._draw_footer(
                canvas=
                    canvas,

                site_name=
                    site_name,

                case=
                    case,

                version=
                    version,
            )


        doc.build(

            story,

            onFirstPage=
                footer,

            onLaterPages=
                footer,
        )


    # ========================================================
    # HEADER
    # ========================================================

    def _build_header(
        self,
        logo,
        site_name,
        case,
        version,
    ):

        left_content = []


        if logo:

            try:

                logo_image = RLImage(

                    str(
                        logo
                    ),

                    width=
                        2.9 * cm,

                    height=
                        0.82 * cm,

                    kind=
                        "proportional",
                )


                left_content.append(
                    logo_image
                )


            except (
                OSError,
                ValueError,
            ):

                left_content.append(
                    Paragraph(
                        escape(
                            site_name
                        ),
                        self.styles[
                            "brand"
                        ],
                    )
                )


        else:

            left_content.append(
                Paragraph(
                    escape(
                        site_name
                    ),
                    self.styles[
                        "brand"
                    ],
                )
            )


        right_content = [

            Paragraph(
                "CLINICAL AI REPORT",
                self.styles[
                    "report_type"
                ],
            ),

            Spacer(
                1,
                0.07 * cm,
            ),

            Paragraph(
                "Hỗ trợ phân tích ảnh dermoscopy",
                ParagraphStyle(

                    "ReportTypeSub",

                    parent=
                        self.styles[
                            "report_type"
                        ],

                    fontName=
                        self.font_name,

                    fontSize=
                        6.8,

                    textColor=
                        SLATE_400,
                ),
            ),
        ]


        brand_table = Table(

            [
                [
                    left_content,
                    right_content,
                ]
            ],

            colWidths=[
                9.4 * cm,
                8.0 * cm,
            ],
        )


        brand_table.setStyle(
            TableStyle([
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, 0),
                    "RIGHT",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ])
        )


        title = Paragraph(

            "BÁO CÁO PHÂN TÍCH "
            "TỔN THƯƠNG DA",

            self.styles[
                "title"
            ],
        )


        meta = Paragraph(

            (
                f"Case "
                f"<b>{escape(case.case_code)}</b>"
                f"  ·  Phiên bản v{version}"
                f"  ·  "
                f"{escape(self._date(date.today()))}"
            ),

            self.styles[
                "subtitle"
            ],
        )


        divider = Table(

            [[""]],

            colWidths=[
                17.4 * cm
            ],

            rowHeights=[
                0.04 * cm
            ],
        )


        divider.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    TEAL,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ])
        )


        return [

            brand_table,

            Spacer(
                1,
                0.22 * cm,
            ),

            title,

            meta,

            Spacer(
                1,
                0.20 * cm,
            ),

            divider,

            Spacer(
                1,
                0.23 * cm,
            ),
        ]


    # ========================================================
    # PAGE 2 HEADER
    # ========================================================

    def _build_page_two_header(
        self,
        site_name,
        case,
        version,
    ):

        table = Table(

            [[

                Paragraph(
                    escape(
                        site_name
                    ),
                    self.styles[
                        "brand"
                    ],
                ),

                Paragraph(
                    (
                        f"{escape(case.case_code)}"
                        f" · v{version}"
                    ),
                    self.styles[
                        "report_type"
                    ],
                ),
            ]],

            colWidths=[
                10.5 * cm,
                6.9 * cm,
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ALIGN",
                    (1, 0),
                    (1, 0),
                    "RIGHT",
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    5,
                ),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    TEAL,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ])
        )


        return [

            table,

            Spacer(
                1,
                0.2 * cm,
            ),
        ]


    # ========================================================
    # SECTION TITLE
    # ========================================================

    def _section_title(
        self,
        number,
        title,
    ):

        number_box = Table(

            [[
                Paragraph(
                    escape(
                        number
                    ),
                    ParagraphStyle(

                        "SectionNumber",

                        parent=
                            self.styles[
                                "small"
                            ],

                        fontName=
                            self.font_bold,

                        fontSize=
                            7,

                        alignment=
                            TA_CENTER,

                        textColor=
                            WHITE,
                    ),
                )
            ]],

            colWidths=[
                0.65 * cm
            ],

            rowHeights=[
                0.55 * cm
            ],
        )


        number_box.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    TEAL,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "ALIGN",
                    (0, 0),
                    (-1, -1),
                    "CENTER",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ])
        )


        heading = Paragraph(

            escape(
                title
            ),

            self.styles[
                "section"
            ],
        )


        table = Table(

            [[
                number_box,
                heading,
            ]],

            colWidths=[
                0.8 * cm,
                16.6 * cm,
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "MIDDLE",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ])
        )


        return table


    # ========================================================
    # PATIENT INFO
    # ========================================================
    def _patient_card(
        self,
        patient,
        case,
        analysis,
    ):

        # ========================================================
        # DATA
        # ========================================================

        full_name = self._text(
            patient.get(
                "full_name"
            )
        )


        birthday_gender = (

            f"{self._date(patient.get('date_of_birth'))}"
            f" · "
            f"{self._text(patient.get('gender'))}"
        )


        phone = self._text(
            patient.get(
                "phone"
            )
        )


        email = self._text(
            patient.get(
                "email"
            )
        )


        address = self._text(
            patient.get(
                "address"
            )
        )


        doctor_name = (

            case.doctor.full_name

            if case.doctor

            else
            "Chưa có dữ liệu"
        )


        lesion_location = self._text(
            case.lesion_location
        )


        case_code = self._text(
            case.case_code
        )


        analysis_time = (

            self._date(
                analysis.completed_at
                or
                analysis.created_at
            )

            if analysis

            else
            "Chưa có dữ liệu"
        )


        # ========================================================
        # LABEL STYLE
        # ========================================================

        label_style = ParagraphStyle(

            "PatientInlineLabel",

            parent=
                self.styles[
                    "body"
                ],

            fontName=
                self.font_bold,

            fontSize=
                8.2,

            leading=
                11,

            textColor=
                NAVY,
        )


        # ========================================================
        # VALUE STYLE
        # ========================================================

        value_style = ParagraphStyle(

            "PatientInlineValue",

            parent=
                self.styles[
                    "body"
                ],

            fontName=
                self.font_name,

            fontSize=
                8.5,

            leading=
                11,

            textColor=
                SLATE_900,
        )


        # ========================================================
        # HELPER
        # ========================================================

        def label(
            text,
        ):

            return Paragraph(

                escape(
                    text
                ),

                label_style,
            )


        def value(
            text,
        ):

            return Paragraph(

                escape(
                    self._text(
                        text
                    )
                ),

                value_style,
            )


        # ========================================================
        # ROWS
        #
        # Cấu trúc:
        #
        # label | value | label | value
        # ========================================================

        rows = [

            [
                label(
                    "Họ và tên:"
                ),

                value(
                    full_name
                ),

                label(
                    "Ngày sinh / Giới tính:"
                ),

                value(
                    birthday_gender
                ),
            ],


            [
                label(
                    "Số điện thoại:"
                ),

                value(
                    phone
                ),

                label(
                    "Email:"
                ),

                value(
                    email
                ),
            ],


            [
                label(
                    "Địa chỉ:"
                ),

                value(
                    address
                ),

                "",
                "",
            ],


            [
                label(
                    "Bác sĩ phụ trách:"
                ),

                value(
                    doctor_name
                ),

                label(
                    "Vị trí tổn thương:"
                ),

                value(
                    lesion_location
                ),
            ],


            [
                label(
                    "Mã ca:"
                ),

                value(
                    case_code
                ),

                label(
                    "Thời gian phân tích:"
                ),

                value(
                    analysis_time
                ),
            ],
        ]


        # ========================================================
        # TABLE
        # ========================================================

        table = Table(

            rows,

            colWidths=[

                2.65 * cm,

                5.75 * cm,

                3.35 * cm,

                5.35 * cm,
            ],
        )


        # ========================================================
        # STYLE
        # ========================================================

        table.setStyle(
            TableStyle([

                # ================= BACKGROUND =================

                (
                    "BACKGROUND",

                    (0, 0),

                    (-1, -1),

                    SLATE_50,
                ),


                # ================= OUTER BORDER =================

                (
                    "BOX",

                    (0, 0),

                    (-1, -1),

                    0.55,

                    SLATE_200,
                ),


                # ================= ROW LINES =================

                (
                    "LINEBELOW",

                    (0, 0),

                    (-1, -2),

                    0.35,

                    SLATE_200,
                ),


                # ================= ADDRESS SPAN =================

                (
                    "SPAN",

                    (1, 2),

                    (3, 2),
                ),


                # ================= ALIGN =================

                (
                    "VALIGN",

                    (0, 0),

                    (-1, -1),

                    "MIDDLE",
                ),


                # ================= PADDING =================

                (
                    "LEFTPADDING",

                    (0, 0),

                    (-1, -1),

                    8,
                ),


                (
                    "RIGHTPADDING",

                    (0, 0),

                    (-1, -1),

                    8,
                ),


                (
                    "TOPPADDING",

                    (0, 0),

                    (-1, -1),

                    6,
                ),


                (
                    "BOTTOMPADDING",

                    (0, 0),

                    (-1, -1),

                    6,
                ),
            ])
        )


        return table


    def _info_item(
        self,
        label,
        value,
        raw=False,
    ):

        if raw:

            value_text = (
                value
                or
                "Chưa có dữ liệu"
            )

        else:

            value_text = escape(
                self._text(
                    value
                )
            )


        return [

            Paragraph(
                escape(
                    label
                ),
                self.styles[
                    "card_label"
                ],
            ),

            Paragraph(
                value_text,
                self.styles[
                    "card_value_small"
                ],
            ),

            Spacer(
                1,
                0.10 * cm,
            ),
        ]


    # ========================================================
    # AI SUMMARY
    # ========================================================

    def _ai_summary(
        self,
        result,
    ):

        if not result:

            return self._empty_panel(
                "Chưa có kết quả AI."
            )


        malignant = (
            result.binary_result
            ==
            1
        )


        binary_color = (
            RED
            if malignant
            else GREEN
        )


        binary_bg = (
            RED_LIGHT
            if malignant
            else GREEN_LIGHT
        )


        binary_title = (
            "NGHI NGỜ ÁC TÍNH"
            if malignant
            else "LÀNH TÍNH"
        )


        binary_prob = (
            self._prob(
                result.binary_probability
            )
        )


        class_name = (
            result.predicted_class
            or
            "Chưa có dữ liệu"
        )


        class_prob = (
            self._prob(
                result.predicted_probability
            )
        )


        left = [

            Paragraph(
                "PHÂN LOẠI NHỊ PHÂN",
                self.styles[
                    "ai_label"
                ],
            ),

            Spacer(
                1,
                0.06 * cm,
            ),

            Paragraph(
                binary_title,
                ParagraphStyle(

                    "BinaryTitle",

                    parent=
                        self.styles[
                            "ai_title"
                        ],

                    textColor=
                        binary_color,
                ),
            ),

            Spacer(
                1,
                0.08 * cm,
            ),

            Paragraph(
                binary_prob,
                ParagraphStyle(

                    "BinaryProbability",

                    parent=
                        self.styles[
                            "ai_value"
                        ],

                    textColor=
                        binary_color,
                ),
            ),

            Paragraph(
                "Xác suất mô hình",
                self.styles[
                    "small"
                ],
            ),
        ]


        right = [

            Paragraph(
                "PHÂN LOẠI ĐA LỚP",
                self.styles[
                    "ai_label"
                ],
            ),

            Spacer(
                1,
                0.06 * cm,
            ),

            Paragraph(
                escape(
                    class_name
                ),
                self.styles[
                    "ai_title"
                ],
            ),

            Spacer(
                1,
                0.08 * cm,
            ),

            Paragraph(
                class_prob,
                ParagraphStyle(

                    "ClassProbability",

                    parent=
                        self.styles[
                            "ai_value"
                        ],

                    textColor=
                        TEAL,
                ),
            ),

            Paragraph(
                (
                    "Độ tin cậy · "
                    f"{escape(self._text(result.model_name))}"
                ),
                self.styles[
                    "small"
                ],
            ),
        ]


        table = Table(

            [[
                left,
                right,
            ]],

            colWidths=[
                8.55 * cm,
                8.55 * cm,
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, 0),
                    binary_bg,
                ),
                (
                    "BACKGROUND",
                    (1, 0),
                    (1, 0),
                    TEAL_LIGHT,
                ),
                (
                    "BOX",
                    (0, 0),
                    (0, 0),
                    0.7,
                    binary_color,
                ),
                (
                    "BOX",
                    (1, 0),
                    (1, 0),
                    0.7,
                    TEAL,
                ),
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    12,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    12,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
            ])
        )


        return table


    # ========================================================
    # IMAGE PAIR
    # ========================================================

    def _image_pair(
        self,
        original,
        gradcam,
    ):

        original_cell = (
            self._image_card(
                "ẢNH DERMOSCOPY",
                original,
                accent=False,
            )
        )


        gradcam_cell = (
            self._image_card(
                "GRAD-CAM",
                gradcam,
                accent=True,
            )
        )


        table = Table(

            [[
                original_cell,
                gradcam_cell,
            ]],

            colWidths=[
                8.55 * cm,
                8.55 * cm,
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ])
        )


        return table


    def _image_card(
        self,
        label,
        asset,
        accent=False,
    ):

        path = (
            self._asset_path(
                asset
            )
        )


        elements = [

            Paragraph(
                escape(
                    label
                ),
                ParagraphStyle(

                    f"{label}Label",

                    parent=
                        self.styles[
                            "card_label"
                        ],

                    textColor=
                        (
                            TEAL
                            if accent
                            else SLATE_500
                        ),
                ),
            ),

            Spacer(
                1,
                0.08 * cm,
            ),
        ]


        if path:

            try:

                image = RLImage(

                    str(path),

                    width=
                        7.95 * cm,

                    height=
                        5.0 * cm,

                    kind=
                        "proportional",
                )


                elements.append(
                    image
                )


            except (
                OSError,
                ValueError,
            ):

                elements.append(
                    Paragraph(
                        "Không thể hiển thị ảnh.",
                        self.styles[
                            "small"
                        ],
                    )
                )


        else:

            elements.append(
                Paragraph(
                    "Chưa có dữ liệu hình ảnh.",
                    self.styles[
                        "small"
                    ],
                )
            )


        border_color = (
            TEAL
            if accent
            else SLATE_200
        )


        table = Table(

            [[
                elements
            ]],

            colWidths=[
                8.25 * cm
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    WHITE,
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.55,
                    border_color,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    6,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    7,
                ),
            ])
        )


        return table


    # ========================================================
    # PROBABILITY TABLE
    # ========================================================

    def _probability_table(
        self,
        probabilities,
    ):

        if (
            not isinstance(
                probabilities,
                dict,
            )
            or
            not probabilities
        ):

            return self._empty_panel(
                "Chưa có dữ liệu xác suất."
            )


        sorted_items = sorted(

            probabilities.items(),

            key=lambda item:
                float(
                    item[1]
                    or 0
                ),

            reverse=True,
        )


        rows = []


        for (
            label,
            probability,
        ) in sorted_items:

            try:

                value = float(
                    probability
                )

            except (
                TypeError,
                ValueError,
            ):

                value = 0.0


            value = max(
                0.0,
                min(
                    value,
                    1.0,
                ),
            )


            rows.append([

                Paragraph(
                    escape(
                        str(label)
                    ),
                    self.styles[
                        "body_bold"
                    ],
                ),

                self._probability_bar(
                    value
                ),

                Paragraph(
                    f"{value * 100:.2f}%",
                    ParagraphStyle(

                        "ProbabilityValue",

                        parent=
                            self.styles[
                                "body"
                            ],

                        alignment=
                            TA_RIGHT,

                        fontName=
                            self.font_bold,

                        textColor=
                            (
                                TEAL
                                if value
                                ==
                                max(
                                    float(v or 0)
                                    for v
                                    in probabilities.values()
                                )
                                else
                                SLATE_700
                            ),
                    ),
                ),
            ])


        table = Table(

            rows,

            colWidths=[
                1.7 * cm,
                13.5 * cm,
                2.1 * cm,
            ],
        )


        style_commands = [

            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),

            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),

            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                4,
            ),

            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                3.5,
            ),

            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                3.5,
            ),
        ]


        for index in range(
            len(rows)
        ):

            if (
                index % 2
                ==
                1
            ):

                style_commands.append(
                    (
                        "BACKGROUND",
                        (0, index),
                        (-1, index),
                        SLATE_50,
                    )
                )


        table.setStyle(
            TableStyle(
                style_commands
            )
        )


        return table


    def _probability_bar(
        self,
        value,
    ):

        width = (
            310
        )

        height = (
            7
        )


        drawing = Drawing(
            width,
            height,
        )


        drawing.add(
            Rect(

                0,
                0,

                width,
                height,

                rx=
                    3,

                ry=
                    3,

                fillColor=
                    SLATE_200,

                strokeColor=
                    None,
            )
        )


        bar_width = (
            max(
                2,
                width
                *
                value,
            )
            if value > 0
            else 0
        )


        if (
            bar_width > 0
        ):

            drawing.add(
                Rect(

                    0,
                    0,

                    bar_width,
                    height,

                    rx=
                        3,

                    ry=
                        3,

                    fillColor=
                        TEAL,

                    strokeColor=
                        None,
                )
            )


        return drawing


    # ========================================================
    # MEASUREMENT
    # ========================================================

    def _measurement_summary(
        self,
        analysis,
    ):

        if not analysis:

            return self._empty_panel(
                "Chưa có dữ liệu đo lường."
            )


        cards = [

            self._metric_card(
                "DIỆN TÍCH",
                self._number(
                    analysis.lesion_area_px,
                    "px²",
                ),
            ),

            self._metric_card(
                "CHU VI",
                self._number(
                    analysis.lesion_perimeter_px,
                    "px",
                ),
            ),

            self._metric_card(
                "TỶ LỆ TỔN THƯƠNG",
                self._ratio(
                    analysis.lesion_ratio
                ),
            ),

            self._metric_card(
                "BOUNDING BOX",
                self._bbox(
                    analysis
                ),
            ),
        ]


        table = Table(

            [[
                cards[0],
                cards[1],
                cards[2],
                cards[3],
            ]],

            colWidths=[
                4.27 * cm,
                4.27 * cm,
                4.27 * cm,
                4.27 * cm,
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "VALIGN",
                    (0, 0),
                    (-1, -1),
                    "TOP",
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    2,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    2,
                ),
            ])
        )


        return table


    def _metric_card(
        self,
        label,
        value,
    ):

        table = Table(

            [[

                [
                    Paragraph(
                        escape(
                            label
                        ),
                        self.styles[
                            "card_label"
                        ],
                    ),

                    Spacer(
                        1,
                        0.08 * cm,
                    ),

                    Paragraph(
                        escape(
                            self._text(
                                value
                            )
                        ),
                        ParagraphStyle(

                            f"Metric{label}",

                            parent=
                                self.styles[
                                    "card_value"
                                ],

                            textColor=
                                NAVY,
                        ),
                    ),
                ]
            ]],

            colWidths=[
                4.0 * cm
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    SLATE_50,
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    SLATE_200,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    8,
                ),
            ])
        )


        return table


    # ========================================================
    # CONTOUR
    # ========================================================

    def _contour_panel(
        self,
        contour_path,
    ):

        path = (
            self._asset_path(
                contour_path
            )
        )


        content = [

            Paragraph(
                "KHOANH VÙNG TỔN THƯƠNG · OPENCV",
                self.styles[
                    "card_label"
                ],
            ),

            Spacer(
                1,
                0.10 * cm,
            ),
        ]


        if path:

            try:

                content.append(

                    RLImage(

                        str(path),

                        width=
                            8.2 * cm,

                        height=
                            5.0 * cm,

                        kind=
                            "proportional",
                    )
                )


            except (
                OSError,
                ValueError,
            ):

                content.append(
                    Paragraph(
                        "Không thể hiển thị ảnh contour.",
                        self.styles[
                            "small"
                        ],
                    )
                )


        else:

            content.append(
                Paragraph(
                    "Chưa có dữ liệu contour.",
                    self.styles[
                        "small"
                    ],
                )
            )


        content.extend([

            Spacer(
                1,
                0.10 * cm,
            ),

            Paragraph(

                (
                    "Đường viền biểu diễn vùng tổn thương "
                    "được xác định bằng xử lý ảnh OpenCV. "
                    "Các phép đo được tính theo pixel và "
                    "không được quy đổi sang millimeter "
                    "khi chưa có thông tin hiệu chuẩn."
                ),

                self.styles[
                    "small"
                ],
            ),
        ])


        table = Table(

            [[
                content
            ]],

            colWidths=[
                17.1 * cm
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    SLATE_50,
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    SLATE_200,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    9,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
            ])
        )


        return table


    # ========================================================
    # DOCTOR REVIEW
    # ========================================================

    def _doctor_review_card(
        self,
        review,
        doctor,
    ):

        doctor_name = (
            doctor.full_name
            if doctor
            else
            "Chưa có dữ liệu"
        )


        if not review:

            status_text = (
                "CHƯA CÓ CHẨN ĐOÁN"
            )

            clinical_note = (
                "Chưa có dữ liệu"
            )

            conclusion = (
                "Chưa có dữ liệu"
            )

            recommendation = (
                "Chưa có dữ liệu"
            )

        else:

            status_text = (
                "ĐÃ XÁC NHẬN"
                if review.review_status
                ==
                "REVIEWED"
                else "BẢN NHÁP"
            )

            clinical_note = (
                self._text(
                    review.clinical_note
                )
            )

            conclusion = (
                self._text(
                    review.doctor_conclusion
                )
            )

            recommendation = (
                self._text(
                    review.recommendation
                )
            )


        # ================= HEADER =================

        header = Table(

            [[

                Paragraph(
                    (
                        "Bác sĩ: "
                        f"<b>{escape(doctor_name)}</b>"
                    ),
                    self.styles[
                        "body"
                    ],
                ),

                Paragraph(
                    escape(
                        status_text
                    ),
                    ParagraphStyle(

                        "DoctorStatus",

                        parent=
                            self.styles[
                                "small"
                            ],

                        fontName=
                            self.font_bold,

                        alignment=
                            TA_RIGHT,

                        textColor=
                            (
                                GREEN
                                if review
                                and
                                review.review_status
                                ==
                                "REVIEWED"
                                else AMBER
                            ),
                    ),
                ),
            ]],

            colWidths=[
                11.5 * cm,
                5.1 * cm,
            ],
        )


        header.setStyle(
            TableStyle([
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    0,
                ),
            ])
        )


        body = [

            header,

            Spacer(
                1,
                0.15 * cm,
            ),

            Paragraph(
                "GHI CHÚ LÂM SÀNG",
                self.styles[
                    "doctor_heading"
                ],
            ),

            Paragraph(
                escape(
                    clinical_note
                ),
                self.styles[
                    "doctor_text"
                ],
            ),

            Spacer(
                1,
                0.16 * cm,
            ),

            Paragraph(
                "CHẨN ĐOÁN / KẾT LUẬN",
                self.styles[
                    "doctor_heading"
                ],
            ),

            Paragraph(
                escape(
                    conclusion
                ),
                ParagraphStyle(

                    "DoctorConclusion",

                    parent=
                        self.styles[
                            "doctor_text"
                        ],

                    fontName=
                        self.font_bold,

                    fontSize=
                        9.5,

                    leading=
                        14,

                    textColor=
                        NAVY_DARK,
                ),
            ),

            Spacer(
                1,
                0.16 * cm,
            ),

            Paragraph(
                "KHUYẾN NGHỊ",
                self.styles[
                    "doctor_heading"
                ],
            ),

            Paragraph(
                escape(
                    recommendation
                ),
                self.styles[
                    "doctor_text"
                ],
            ),
        ]


        table = Table(

            [[
                body
            ]],

            colWidths=[
                17.1 * cm
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    TEAL_LIGHT,
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.8,
                    TEAL,
                ),
                (
                    "LINEBEFORE",
                    (0, 0),
                    (0, -1),
                    3.0,
                    TEAL,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    11,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    11,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    13,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    13,
                ),
            ])
        )


        return table


    # ========================================================
    # WARNING
    # ========================================================

    def _warning_panel(
        self,
    ):

        content = [

            Paragraph(
                "⚠ THÔNG TIN QUAN TRỌNG",
                self.styles[
                    "warning_title"
                ],
            ),

            Spacer(
                1,
                0.08 * cm,
            ),

            Paragraph(
                escape(
                    DISCLAIMER
                ),
                self.styles[
                    "warning"
                ],
            ),

            Spacer(
                1,
                0.08 * cm,
            ),

            Paragraph(

                (
                    "Grad-CAM chỉ phản ánh khu vực mà mô hình "
                    "tập trung khi đưa ra dự đoán; không phải "
                    "bản đồ phân đoạn tổn thương. "
                    "Các phép đo OpenCV sử dụng đơn vị px/px² "
                    "và tỷ lệ ảnh."
                ),

                self.styles[
                    "warning"
                ],
            ),
        ]


        table = Table(

            [[
                content
            ]],

            colWidths=[
                17.1 * cm
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    AMBER_LIGHT,
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    colors.HexColor(
                        "#F5D48A"
                    ),
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    12,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    12,
                ),
            ])
        )


        return table


    # ========================================================
    # EMPTY PANEL
    # ========================================================

    def _empty_panel(
        self,
        text,
    ):

        table = Table(

            [[
                Paragraph(
                    escape(
                        text
                    ),
                    self.styles[
                        "small"
                    ],
                )
            ]],

            colWidths=[
                17.1 * cm
            ],
        )


        table.setStyle(
            TableStyle([
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    SLATE_50,
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.5,
                    SLATE_200,
                ),
                (
                    "TOPPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "BOTTOMPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "LEFTPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
                (
                    "RIGHTPADDING",
                    (0, 0),
                    (-1, -1),
                    10,
                ),
            ])
        )


        return table


    # ========================================================
    # FOOTER
    # ========================================================

    def _draw_footer(
        self,
        canvas,
        site_name,
        case,
        version,
    ):

        canvas.saveState()


        width, _ = A4


        canvas.setStrokeColor(
            SLATE_200
        )


        canvas.setLineWidth(
            0.5
        )


        canvas.line(

            1.35 * cm,

            1.04 * cm,

            width
            -
            1.35 * cm,

            1.04 * cm,
        )


        canvas.setFont(
            self.font_name,
            6.8,
        )


        canvas.setFillColor(
            SLATE_500
        )


        canvas.drawString(

            1.35 * cm,

            0.67 * cm,

            (
                f"{site_name} · "
                f"{case.case_code} · "
                f"v{version}"
            ),
        )


        canvas.drawCentredString(

            width / 2,

            0.67 * cm,

            "AI chỉ hỗ trợ tham khảo",
        )


        canvas.drawRightString(

            width
            -
            1.35 * cm,

            0.67 * cm,

            (
                f"Trang "
                f"{canvas.getPageNumber()}"
            ),
        )


        canvas.restoreState()


    # ========================================================
    # PATIENT SNAPSHOT
    # ========================================================

    @staticmethod
    def _patient_info(
        case,
    ):

        data = {

            "full_name":
                None,

            "email":
                None,

            "date_of_birth":
                None,

            "gender":
                None,

            "phone":
                None,

            "address":
                None,
        }


        # ====================================================
        # FALLBACK: REGISTERED USER
        # ====================================================

        if (
            case.patient
        ):

            data.update({

                "full_name":
                    case.patient
                    .full_name,

                "email":
                    case.patient
                    .email,

                "date_of_birth":
                    case.patient
                    .date_of_birth,

                "gender":
                    case.patient
                    .gender,

                "phone":
                    case.patient
                    .phone,
            })


        # ====================================================
        # SNAPSHOT HAS PRIORITY
        # ====================================================

        if isinstance(
            case.patient_snapshot,
            dict,
        ):

            for key in data:

                value = (
                    case
                    .patient_snapshot
                    .get(
                        key
                    )
                )


                if (
                    value
                    is not None
                    and
                    value != ""
                ):

                    data[
                        key
                    ] = value


        return data


    # ========================================================
    # ASSET PATH
    # ========================================================

    def _asset_path(
        self,
        value,
    ):

        if not value:

            return None


        path = Path(
            str(
                value
            )
        )


        candidates = (

            [
                path
            ]

            if path.is_absolute()

            else [

                path,

                (
                    self.project_root
                    /
                    path
                ),
            ]
        )


        for candidate in (
            candidates
        ):

            try:

                resolved = (
                    candidate
                    .resolve()
                )


                if (
                    resolved.is_file()
                ):

                    return resolved


            except OSError:

                continue


        return None


    # ========================================================
    # LATEST RESULT
    # ========================================================

    @staticmethod
    def _latest_result(
        analysis,
    ):

        if (
            not analysis
            or
            not analysis.results
        ):

            return None


        return max(

            analysis.results,

            key=lambda item:
                item.id,
        )


    # ========================================================
    # LATEST DOCTOR REVIEW
    # ========================================================

    @staticmethod
    def _latest_review(
        analysis,
    ):

        if (
            not analysis
            or
            not analysis.reviews
        ):

            return None


        # Ưu tiên REVIEWED.
        reviewed = [

            review

            for review
            in analysis.reviews

            if (
                review.review_status
                ==
                "REVIEWED"
            )
        ]


        if reviewed:

            return max(

                reviewed,

                key=lambda item:
                    item.id,
            )


        return max(

            analysis.reviews,

            key=lambda item:
                item.id,
        )


    # ========================================================
    # TEXT
    # ========================================================

    @staticmethod
    def _text(
        value,
        fallback="Chưa có dữ liệu",
    ):

        if (
            value is None
            or
            value == ""
        ):

            return fallback


        return str(
            value
        )


    # ========================================================
    # DATE
    # ========================================================

    @staticmethod
    def _date(
        value,
    ):

        if isinstance(
            value,
            datetime,
        ):

            return value.strftime(
                "%d/%m/%Y %H:%M"
            )


        if isinstance(
            value,
            date,
        ):

            return value.strftime(
                "%d/%m/%Y"
            )


        # Snapshot JSON thường là:
        # YYYY-MM-DD

        if isinstance(
            value,
            str,
        ):

            try:

                parsed = (
                    date.fromisoformat(
                        value[:10]
                    )
                )


                return parsed.strftime(
                    "%d/%m/%Y"
                )


            except ValueError:

                return value


        return (
            "Chưa có dữ liệu"
        )


    # ========================================================
    # PROBABILITY
    # ========================================================

    @staticmethod
    def _prob(
        value,
    ):

        try:

            return (
                f"{float(value) * 100:.2f}%"
            )


        except (
            TypeError,
            ValueError,
        ):

            return (
                "Chưa có dữ liệu"
            )


    # ========================================================
    # NUMBER
    # ========================================================

    @staticmethod
    def _number(
        value,
        unit,
    ):

        if (
            value is None
        ):

            return (
                "Chưa có dữ liệu"
            )


        try:

            numeric = float(
                value
            )


            if (
                numeric.is_integer()
            ):

                value_text = (
                    f"{int(numeric):,}"
                )

            else:

                value_text = (
                    f"{numeric:,.2f}"
                )


            return (
                f"{value_text} {unit}"
            )


        except (
            TypeError,
            ValueError,
        ):

            return (
                f"{value} {unit}"
            )


    # ========================================================
    # RATIO
    # ========================================================

    @staticmethod
    def _ratio(
        value,
    ):

        if (
            value is None
        ):

            return (
                "Chưa có dữ liệu"
            )


        try:

            return (
                f"{float(value) * 100:.2f}%"
            )


        except (
            TypeError,
            ValueError,
        ):

            return (
                "Chưa có dữ liệu"
            )


    # ========================================================
    # BBOX
    # ========================================================

    @staticmethod
    def _bbox(
        analysis,
    ):

        if not analysis:

            return (
                "Chưa có dữ liệu"
            )


        values = [

            analysis.bbox_x,

            analysis.bbox_y,

            analysis.bbox_width,

            analysis.bbox_height,
        ]


        if not all(
            value is not None
            for value
            in values
        ):

            return (
                "Chưa có dữ liệu"
            )


        return (

            f"x={values[0]}, "
            f"y={values[1]}, "
            f"w={values[2]}, "
            f"h={values[3]}"
        )


    # ========================================================
    # BINARY RESULT
    # ========================================================

    @staticmethod
    def _binary_text(
        result,
    ):

        if (
            not result
            or
            result.binary_result
            is None
        ):

            return (
                "Chưa có dữ liệu"
            )


        return (

            "Nghi ngờ ác tính"

            if result.binary_result

            else
            "Lành tính"
        )
