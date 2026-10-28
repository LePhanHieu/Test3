"""
Safe PDF email delivery.

- Gửi PDF qua Flask-Mail.
- Không hard-code SMTP credentials.
- Lưu lịch sử EmailLog.
- Lỗi SMTP không làm crash Flask.
- Lưu chi tiết kỹ thuật vào database để debug.
"""

from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path, PureWindowsPath
import re

from flask import Flask
from flask_mail import Message

from ..extensions import (
    db,
    mail,
)

from ..models import (
    Case,
    EmailLog,
    Report,
)


EMAIL_PATTERN = re.compile(
    r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$"
)


INVALID_EMAIL = (
    "Địa chỉ email người nhận "
    "không hợp lệ."
)

MISSING_PDF = (
    "Không tìm thấy file PDF báo cáo."
)

UNSAFE_PDF = (
    "Đường dẫn PDF không hợp lệ."
)

SMTP_NOT_CONFIGURED = (
    "SMTP chưa được cấu hình đầy đủ."
)

SMTP_SEND_FAILED = (
    "Không thể gửi email qua SMTP."
)


@dataclass
class EmailSendResult:
    log: EmailLog
    ok: bool
    message: str


class EmailService:

    def __init__(
        self,
        app: Flask,
    ):
        self.app = app


    # ========================================================
    # SEND
    # ========================================================

    def send_report(
        self,
        report: Report,
        sent_by,
        recipient_email=None,
        subject=None,
    ):

        recipient = self._recipient(
            report,
            recipient_email,
        )

        subject_value = self._subject(
            report,
            subject,
        )

        # ----------------------------------------------------
        # EMAIL VALIDATION
        # ----------------------------------------------------

        if not self._valid_email(
            recipient
        ):

            return self._failed(
                report,
                sent_by,
                recipient,
                subject_value,
                INVALID_EMAIL,
            )


        # ----------------------------------------------------
        # PDF
        # ----------------------------------------------------

        (
            pdf_path,
            path_error,
        ) = self._pdf_path(
            report
        )

        if path_error:

            return self._failed(
                report,
                sent_by,
                recipient,
                subject_value,
                path_error,
            )


        # ----------------------------------------------------
        # SMTP CONFIG
        # ----------------------------------------------------

        smtp_error = (
            self._validate_smtp_config()
        )

        if smtp_error:

            return self._failed(
                report,
                sent_by,
                recipient,
                subject_value,
                smtp_error,
            )


        sender = str(
            self.app.config.get(
                "MAIL_DEFAULT_SENDER",
                "",
            )
        ).strip()


        # ----------------------------------------------------
        # CREATE PENDING LOG
        # ----------------------------------------------------

        log = EmailLog(
            report_id=report.id,
            recipient_email=recipient,
            subject=subject_value,
            sent_by=sent_by.id,
            status="PENDING",
        )

        db.session.add(log)
        db.session.commit()


        # ----------------------------------------------------
        # SEND EMAIL
        # ----------------------------------------------------

        try:

            message = Message(
                subject=subject_value,
                recipients=[
                    recipient
                ],
                sender=sender,
            )

            case = db.session.get(
                Case,
                report.case_id,
            )

            case_code = (
                case.case_code
                if case
                else f"#{report.case_id}"
            )

            patient_name = ""

            if (
                case
                and case.patient
            ):
                patient_name = (
                    case.patient.full_name
                    or ""
                ).strip()


            greeting = (
                f"Xin chào {patient_name},"
                if patient_name
                else "Xin chào,"
            )


            message.body = (
                f"{greeting}\n\n"
                "Đính kèm email này là "
                "báo cáo phân tích tổn thương da "
                f"của ca {case_code}.\n\n"
                "Kết quả do hệ thống DermaScan AI "
                "cung cấp chỉ có giá trị hỗ trợ "
                "tham khảo và không thay thế "
                "chẩn đoán chuyên môn của bác sĩ."
                "\n\n"
                "Trân trọng,\n"
                "DermaScan AI"
            )


            # Đọc PDF chỉ tại thời điểm gửi.
            pdf_data = (
                pdf_path.read_bytes()
            )

            message.attach(
                pdf_path.name,
                "application/pdf",
                pdf_data,
            )


            # Flask-Mail
            mail.send(
                message
            )


        except Exception as exc:

            # Log traceback phía server,
            # không trả traceback cho browser.
            self.app.logger.exception(
                "SMTP send failed "
                "for report_id=%s",
                report.id,
            )

            # Pending log đã commit trước đó.
            db.session.rollback()

            log = (
                db.session.get(
                    EmailLog,
                    log.id,
                )
                or log
            )

            log.status = "FAILED"

            # Giữ lỗi kỹ thuật trong DB
            # để debug nhưng không chứa password.
            technical_error = (
                f"{type(exc).__name__}: "
                f"{str(exc)}"
            )

            log.error_message = (
                f"{SMTP_SEND_FAILED} "
                f"{technical_error}"
            )

            log.sent_at = None

            db.session.commit()

            # Frontend chỉ nhận message an toàn
            return EmailSendResult(
                log=log,
                ok=False,
                message=(
                    SMTP_SEND_FAILED
                ),
            )


        # ----------------------------------------------------
        # SUCCESS
        # ----------------------------------------------------

        log.status = "SENT"

        log.sent_at = (
            db.func.current_timestamp()
        )

        log.error_message = None

        db.session.commit()

        return EmailSendResult(
            log=log,
            ok=True,
            message=(
                "Email đã được gửi "
                "thành công."
            ),
        )


    # ========================================================
    # SMTP VALIDATION
    # ========================================================

    def _validate_smtp_config(
        self,
    ):

        server = str(
            self.app.config.get(
                "MAIL_SERVER",
                "",
            )
        ).strip()

        username = str(
            self.app.config.get(
                "MAIL_USERNAME",
                "",
            )
        ).strip()

        password = self.app.config.get(
            "MAIL_PASSWORD"
        )

        sender = str(
            self.app.config.get(
                "MAIL_DEFAULT_SENDER",
                "",
            )
        ).strip()


        if not server:
            return (
                "SMTP chưa được cấu hình: "
                "thiếu MAIL_SERVER."
            )

        if not username:
            return (
                "SMTP chưa được cấu hình: "
                "thiếu MAIL_USERNAME."
            )

        if not password:
            return (
                "SMTP chưa được cấu hình: "
                "thiếu MAIL_PASSWORD."
            )

        if not sender:
            return (
                "SMTP chưa được cấu hình: "
                "thiếu MAIL_DEFAULT_SENDER."
            )


        use_tls = bool(
            self.app.config.get(
                "MAIL_USE_TLS",
                False,
            )
        )

        use_ssl = bool(
            self.app.config.get(
                "MAIL_USE_SSL",
                False,
            )
        )

        if use_tls and use_ssl:
            return (
                "Cấu hình SMTP không hợp lệ: "
                "MAIL_USE_TLS và MAIL_USE_SSL "
                "không được cùng bật."
            )

        return None


    # ========================================================
    # RECIPIENT
    # ========================================================

    def _recipient(
        self,
        report,
        recipient_email,
    ):

        if recipient_email is not None:

            return str(
                recipient_email
            ).strip()


        case = db.session.get(
            Case,
            report.case_id,
        )

        if (
            case
            and case.patient
        ):

            return (
                case.patient.email
                or ""
            ).strip()

        return ""


    # ========================================================
    # SUBJECT
    # ========================================================

    def _subject(
        self,
        report,
        subject,
    ):

        if (
            subject is not None
            and str(subject).strip()
        ):

            return str(
                subject
            ).strip()[:255]


        case = db.session.get(
            Case,
            report.case_id,
        )

        case_code = (
            case.case_code
            if case
            else f"#{report.case_id}"
        )


        return (
            "DermaScan AI - "
            f"Báo cáo phân tích "
            f"{case_code} - "
            f"v{report.report_version}"
        )


    # ========================================================
    # VALID EMAIL
    # ========================================================

    @staticmethod
    def _valid_email(
        value,
    ):

        if (
            not isinstance(
                value,
                str,
            )
            or not value
            or len(value) > 254
        ):
            return False


        address = parseaddr(
            value
        )[1]

        return (
            address == value
            and bool(
                EMAIL_PATTERN.fullmatch(
                    value
                )
            )
        )


    # ========================================================
    # PDF PATH
    # ========================================================

    def _pdf_path(
        self,
        report,
    ):

        raw = Path(
            report.pdf_path
        )


        if (
            raw.is_absolute()
            or PureWindowsPath(
                report.pdf_path
            ).drive
            or ".." in raw.parts
        ):

            return (
                None,
                UNSAFE_PDF,
            )


        root = Path(
            self.app.config[
                "REPORT_FOLDER"
            ]
        ).resolve()


        path = (
            root / raw
        ).resolve()


        if not path.is_relative_to(
            root
        ):

            return (
                None,
                UNSAFE_PDF,
            )


        if (
            path.suffix.lower()
            != ".pdf"
            or not path.is_file()
        ):

            return (
                None,
                MISSING_PDF,
            )


        return (
            path,
            None,
        )


    # ========================================================
    # FAILURE BEFORE SMTP
    # ========================================================

    @staticmethod
    def _failed(
        report,
        sent_by,
        recipient,
        subject,
        error,
    ):

        log = EmailLog(
            report_id=report.id,

            recipient_email=(
                recipient or ""
            )[:254],

            subject=(
                subject or ""
            )[:255],

            sent_by=sent_by.id,

            status="FAILED",

            error_message=error,
        )

        db.session.add(log)
        db.session.commit()


        return EmailSendResult(
            log=log,
            ok=False,
            message=error,
        )