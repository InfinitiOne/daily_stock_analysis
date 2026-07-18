# Private Google Drive report delivery

JEAC can upload completed investment reports directly to a private Google Drive
folder. Generated DOCX/PPTX files are never uploaded as GitHub Actions
artifacts.

## Required GitHub Actions settings

| Type | Name | Value |
| --- | --- | --- |
| Secret | `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` | Entire Service Account JSON key |
| Variable | `GOOGLE_DRIVE_REPORT_FOLDER_ID` | ID of the Drive folder shared with the Service Account |
| Variable | `PRIVATE_REPORT_EXPORT_ENABLED` | `true` |

The Service Account must be an **Editor** of the designated folder only. Do not
grant it Google Cloud Project Owner or Editor permissions.

## Export policy

- Daily: DOCX
- Weekly: DOCX and PPTX
- Monthly: DOCX and PPTX
- The report is exported only after all required stock data and the market
  section have passed integrity checks.
- Missing core data or an LLM 429 response produces no DOCX/PPTX.
- GitHub Actions uploads only limited diagnostics under `logs/`; it never
  uploads `reports/`.

## Resulting Drive paths

```text
Daily/JEAC_Daily_YYYY-MM-DD.docx
Weekly/JEAC_Weekly_YYYY-MM-DD.docx
Weekly/JEAC_Weekly_YYYY-MM-DD.pptx
Monthly/JEAC_Monthly_YYYY-MM.docx
Monthly/JEAC_Monthly_YYYY-MM.pptx
```

To create a monthly export workflow, set `JEAC_REPORT_KIND=monthly` in that
workflow. The shared report-export service will then create both formats.
