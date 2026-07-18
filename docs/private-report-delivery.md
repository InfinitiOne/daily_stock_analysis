# Private Google Drive report delivery

JEAC creates completed reports on the GitHub Actions runner and uploads them only
to the selected private Google Drive folder. It never uploads generated reports
to GitHub Actions artifacts.

## Personal Gmail / My Drive (recommended)

A Service Account has no My Drive storage quota. For a personal Gmail account,
use OAuth so that the scheduled workflow uploads as **your own Google account**.

| Type | Name | Value |
| --- | --- | --- |
| Secret | `GOOGLE_DRIVE_OAUTH_CLIENT_JSON` | Entire downloaded Desktop OAuth Client JSON |
| Secret | `GOOGLE_DRIVE_OAUTH_TOKEN_JSON` | JSON produced by `scripts/authorize_google_drive_oauth.py` |
| Variable | `GOOGLE_DRIVE_AUTH_MODE` | `oauth` |
| Variable | `GOOGLE_DRIVE_REPORT_FOLDER_ID` | Raw ID of the destination folder, not its URL |
| Variable | `PRIVATE_REPORT_EXPORT_ENABLED` | `true` |

The OAuth client and refresh token are secrets. Do not commit them, upload them
as artifacts, or paste them into an issue/PR.

### Generate the token once on your computer

1. Save the downloaded OAuth client file locally, for example
   `~/Downloads/client_secret.json`.
2. In a local checkout of this repository, install dependencies:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Run:

   ```bash
   python scripts/authorize_google_drive_oauth.py \
     --client-json ~/Downloads/client_secret.json
   ```

4. A browser opens. Sign in with the Gmail account that owns the target folder,
   choose **Allow**, and return to the terminal.
5. Copy the whole JSON in `google_drive_oauth_token.json` into the
   `GOOGLE_DRIVE_OAUTH_TOKEN_JSON` GitHub Actions Secret.

The token includes a refresh token, so scheduled runs can renew access without
asking you to log in again. Use OAuth consent's **Production** publishing state
after your first successful test; Testing refresh tokens expire after seven
days.

## Service Account / Shared Drive (optional)

This mode remains available for a Google Workspace Shared Drive or another
storage arrangement where the Service Account has quota.

| Type | Name | Value |
| --- | --- | ---|
| Secret | `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` | Entire Service Account JSON key |
| Variable | `GOOGLE_DRIVE_AUTH_MODE` | `service_account` |

## Export policy

- Daily: DOCX
- Weekly: DOCX and PPTX
- Monthly: DOCX and PPTX
- Export happens only after all required stock data and the market section pass
  integrity checks.
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
