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


def test_weekly_delivery_creates_docx_only_before_private_upload(
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

    assert [item.format for item in delivered] == ["docx"]
    assert uploaded == [
        ("JEAC_Weekly_2026-07-19.docx", "docx"),
    ]
    assert (tmp_path / "JEAC_Weekly_2026-07-19.docx").exists()
    assert not (tmp_path / "JEAC_Weekly_2026-07-19.pptx").exists()


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


def test_docx_renderer_sets_traditional_chinese_east_asian_font(tmp_path: Path) -> None:
    path = tmp_path / "daily.docx"
    PrivateReportDelivery._create_docx(
        path,
        title="JEAC 每日投資報告",
        markdown="# 市場結論\n\n- 等待確認",
        generated_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )

    from zipfile import ZipFile

    with ZipFile(path) as archive:
        styles = archive.read("word/styles.xml").decode("utf-8")
    assert 'w:eastAsia="Microsoft JhengHei"' in styles


def test_oauth_delivery_requires_client_and_refresh_token(tmp_path: Path) -> None:
    delivery = PrivateReportDelivery(
        enabled=True,
        folder_id="folder",
        auth_mode="oauth",
        output_dir=tmp_path,
    )

    import pytest

    with pytest.raises(Exception, match="GOOGLE_DRIVE_OAUTH_CLIENT_JSON"):
        delivery.export(report_kind="daily", markdown=_SAMPLE)


def test_oauth_client_rejects_malformed_client_config() -> None:
    import pytest

    with pytest.raises(Exception, match="installed or web client"):
        PrivateReportDelivery._oauth_client_config({})
