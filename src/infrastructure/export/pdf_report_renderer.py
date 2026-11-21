from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.application.dtos import SessionClinicalReportOutputDTO
from src.domain.value_objects import format_utc_z


class ReportLabPdfReportRenderer:
    """Pure-Python clinical PDF report renderer using ReportLab."""

    def render_pdf(self, report: SessionClinicalReportOutputDTO) -> bytes:
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title=f"ParkinStep Clinical Screening Report - {report.session_id}",
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "ParkinTitle",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#0F172A"),
            spaceAfter=6,
        )
        section_style = ParagraphStyle(
            "ParkinSection",
            parent=styles["Heading2"],
            fontSize=11,
            textColor=colors.HexColor("#1E3A8A"),
            spaceBefore=10,
            spaceAfter=4,
        )
        body_style = ParagraphStyle(
            "ParkinBody",
            parent=styles["Normal"],
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor("#1F2937"),
        )
        disclaimer_style = ParagraphStyle(
            "ParkinDisclaimer",
            parent=styles["Normal"],
            fontSize=8.5,
            leading=12,
            textColor=colors.HexColor("#7F1D1D"),
        )

        ended_str = format_utc_z(report.ended_at_utc) if report.ended_at_utc else "-"
        classifier_str = report.classifier_used.value if report.classifier_used else "-"
        threshold_str = f"{report.threshold_used:.2f}" if report.threshold_used is not None else "-"

        elements = [
            Paragraph("ParkinStep (Mobile-FOG) - Laporan Skrining Klinis", title_style),
            Paragraph(
                f"<b>Pasien:</b> {escape(report.patient_display_name)} &nbsp;|&nbsp; "
                f"<b>ID Sesi:</b> {report.session_id}",
                body_style,
            ),
            Paragraph(
                f"<b>Dicetak (UTC):</b> {format_utc_z(report.generated_at_utc)}",
                body_style,
            ),
            Spacer(1, 6),
            Paragraph("1. Ringkasan Parameter &amp; Metrik Klinis", section_style),
        ]

        summary_rows = [
            ["Protokol Tes", report.protocol.value, "Status Medikasi", report.med_state.value],
            [
                "Mode Inferensi",
                report.inference_mode.value,
                "Classifier / Thr",
                f"{classifier_str} ({threshold_str})",
            ],
            [
                "Mulai (UTC)",
                format_utc_z(report.started_at_utc),
                "Selesai (UTC)",
                ended_str,
            ],
            [
                "Durasi Sesi",
                f"{report.duration_sec:.1f} detik",
                "Valid LB6 Ratio",
                f"{report.valid_lb6_ratio * 100:.1f}%",
            ],
            [
                "Persentase FoG",
                f"{report.fog_percentage:.2f}%",
                "Jumlah Episode",
                str(report.episode_count),
            ],
            [
                "Total Durasi FoG",
                f"{report.total_fog_duration_sec:.1f} detik",
                "Median Episode",
                f"{report.median_episode_duration_sec:.1f} detik",
            ],
            [
                "Mean Freeze Index",
                f"{report.mean_freeze_index:.3f}",
                "Asimetri Bilateral",
                f"{report.mean_bilateral_asymmetry:.3f} ({report.asymmetry_level_id})",
            ],
            [
                "Fall Guard False Alarm",
                str(report.fall_guard_false_alarms),
                "Privasi Video",
                "Zero Raw-Video Retention" if report.video_securely_deleted else "Pending",
            ],
        ]
        summary_table = Table(summary_rows, colWidths=[36 * mm, 50 * mm, 36 * mm, 50 * mm])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EFF6FF")),
                    ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EFF6FF")),
                    ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(summary_table)

        elements.append(
            Paragraph("2. Daftar Episode Freezing of Gait Terkonfirmasi", section_style)
        )
        if report.episodes:
            ep_rows = [["#", "Mulai (s)", "Selesai (s)", "Durasi (s)", "Skor Puncak", "Mean FI"]]
            for ep in report.episodes:
                fi_val = f"{ep.mean_freeze_index:.2f}" if ep.mean_freeze_index is not None else "-"
                ep_rows.append(
                    [
                        str(ep.episode_index),
                        f"{ep.start_sec:.1f}",
                        f"{ep.end_sec:.1f}",
                        f"{ep.duration_sec:.1f}",
                        f"{ep.peak_calibrated_score:.1f}%",
                        fi_val,
                    ]
                )
            ep_table = Table(
                ep_rows,
                colWidths=[16 * mm, 30 * mm, 30 * mm, 30 * mm, 33 * mm, 33 * mm],
            )
            ep_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("PADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            elements.append(ep_table)
        else:
            elements.append(
                Paragraph(
                    "Tidak terdapat episode Freezing of Gait terkonfirmasi (min_run >= 2) "
                    "pada sesi ini.",
                    body_style,
                )
            )

        elements.append(Spacer(1, 14))
        disclaimer_table = Table(
            [[Paragraph(escape(report.medical_disclaimer), disclaimer_style)]],
            colWidths=[172 * mm],
        )
        disclaimer_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FEF2F2")),
                    ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#DC2626")),
                    ("PADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        elements.append(disclaimer_table)

        doc.build(elements)
        return buffer.getvalue()
