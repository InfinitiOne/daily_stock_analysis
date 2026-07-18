# -*- coding: utf-8 -*-

from datetime import datetime, timezone
from pathlib import Path

from src.services.private_report_delivery import DeliveredReport, PrivateReportDelivery


_SAMPLE = """# JEAC Weekly Investment Strategy

## 市場環境

- 趨勢確認
- 資料日期：2026-07-19

## 持倉與候選股

| 代碼 | 建議 |
| --- | --- |
| 2330.TW | 續抱 |
"""


def test_disabled_delivery_does_not_create_documents(tmp_path: Path) -> None:
    delivery = PrivateReportDelivery(
        enabled=False,
        folder_id="folder",
        service_account_json="{}",
        output_dir=tmp_path,
    )

    assert delivery.export(report_kind="daily", markdown=_SAMPLE) == []
    assert list(tmp_path.iterdir()) == []


def test_weekly_delivery_creates_docx_and_pptx_before_private_upload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    delivery = PrivateReportDelivery(
        enabled=True,
        folder_id="folder",
        service_account_json='{"type": "service_account"}',
        output_dir=tmp_path,
    )
    uploaded = []

    monkeypatch.setattr(delivery, "_build_drive_client", lambda: object())
    monkeypatch.setattr(delivery, "_ensure_folder", lambda drive, parent_id, folder_name: "weekly-folder")

    def fake_upload(drive, path, *, kind, format_name, parent_id):
        assert path.exists()
        assert parent_id == "weekly-folder"
        uploaded.append((path.name, format_name))
        return DeliveredReport(
            report_kind=kind,
            format=format_name,
            file_name=path.name,
            drive_file_id=f"id-{format_name}",
        )

    monkeypatch.setattr(delivery, "_upload_file", fake_upload)

    delivered = delivery.export(
        report_kind="weekly",
        markdown=_SAMPLE,
        report_date=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )

    assert [item.format for item in delivered] == ["docx", "pptx"]
    assert uploaded == [
        ("JEAC_Weekly_2026-07-19.docx", "docx"),
        ("JEAC_Weekly_2026-07-19.pptx", "pptx"),
    ]
    assert (tmp_path / "JEAC_Weekly_2026-07-19.docx").exists()
    assert (tmp_path / "JEAC_Weekly_2026-07-19.pptx").exists()


def test_daily_delivery_creates_only_docx(tmp_path: Path, monkeypatch) -> None:
    delivery = PrivateReportDelivery(
        enabled=True,
        folder_id="folder",
        service_account_json='{"type": "service_account"}',
        output_dir=tmp_path,
    )

    monkeypatch.setattr(delivery, "_build_drive_client", lambda: object())
    monkeypatch.setattr(delivery, "_ensure_folder", lambda *args: "daily-folder")
    monkeypatch.setattr(
        delivery,
        "_upload_file",
        lambda drive, path, *, kind, format_name, parent_id: DeliveredReport(
            report_kind=kind,
            format=format_name,
            file_name=path.name,
            drive_file_id="id-docx",
        ),
    )

    delivered = delivery.export(report_kind="daily", markdown=_SAMPLE)

    assert [item.format for item in delivered] == ["docx"]
    assert list(tmp_path.glob("*.pptx")) == []
