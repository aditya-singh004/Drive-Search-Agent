"""Google Drive API integration (service account, files.list)."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from google.auth.exceptions import GoogleAuthError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.core.config import Settings, get_settings
from app.utils.helpers import escape_drive_query_value

logger = logging.getLogger(__name__)

DRIVE_READONLY_SCOPE = ["https://www.googleapis.com/auth/drive.readonly"]

# Fields returned from files.list (keep small for bandwidth)
LIST_FIELDS = (
    "nextPageToken, files(id, name, mimeType, modifiedTime, webViewLink)"
)


class DriveServiceError(Exception):
    """Domain error for Drive failures with a user-safe message."""

    def __init__(self, message: str, *, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


class DriveService:
    """Thin async-friendly wrapper around the synchronous Drive client."""

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._service: Any = None

    def _build_service(self) -> Any:
        path = self._settings.service_account_path
        if not path.is_file():
            raise DriveServiceError(
                f"Service account file not found at: {path}",
                code="missing_credentials",
            )
        try:
            creds = service_account.Credentials.from_service_account_file(
                str(path),
                scopes=DRIVE_READONLY_SCOPE,
            )
        except GoogleAuthError as exc:
            logger.exception("Failed to load service account credentials")
            raise DriveServiceError(
                "Could not load Google credentials. Check GOOGLE_SERVICE_ACCOUNT_FILE.",
                code="invalid_credentials",
            ) from exc

        return build("drive", "v3", credentials=creds, cache_discovery=False)

    @property
    def service(self) -> Any:
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _compose_query(self, user_fragment: str) -> str:
        """
        Always scope to the configured folder and exclude trash.

        The model supplies the semantic fragment (mimeType, name contains, etc.).
        """
        folder = escape_drive_query_value(self._settings.google_drive_folder_id)
        base = f"'{folder}' in parents and trashed=false"
        fragment = (user_fragment or "").strip()
        if not fragment:
            return base
        return f"({fragment}) and {base}"

    def search_sync(
        self,
        q_fragment: str,
        *,
        page_size: Optional[int] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """
        Execute files.list with composed `q`.

        Returns (full_q_used, raw_file_dicts).
        """
        full_q = self._compose_query(q_fragment)
        size = page_size or self._settings.drive_page_size
        try:
            request = (
                self.service.files()
                .list(
                    q=full_q,
                    pageSize=size,
                    fields=LIST_FIELDS,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                )
                .execute()
            )
        except HttpError as exc:
            status = getattr(exc, "status_code", None) or getattr(exc.resp, "status", "")
            content = exc.content.decode(errors="replace") if exc.content else ""
            logger.warning("Drive HttpError status=%s body=%s", status, content[:800])
            if str(status) == "429":
                raise DriveServiceError(
                    "Google Drive rate limit reached. Please wait a moment and try again.",
                    code="rate_limited",
                ) from exc
            if str(status) in {"403", "404"}:
                raise DriveServiceError(
                    "Google Drive denied access (HTTP "
                    f"{status}). Share the folder with your service account email as Viewer, "
                    "confirm GOOGLE_DRIVE_FOLDER_ID matches that folder, and ensure Drive API is enabled.",
                    code="drive_permission",
                ) from exc
            if str(status) == "400":
                raise DriveServiceError(
                    "Google Drive rejected the search query (HTTP 400). "
                    "The query may be invalid; try a simpler filter.",
                    code="drive_bad_query",
                ) from exc
            raise DriveServiceError(
                f"Google Drive API error (HTTP {status}). Check Render logs for details.",
                code="drive_http_error",
            ) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unexpected Drive API error")
            raise DriveServiceError(
                "Unexpected error while contacting Google Drive.",
                code="drive_unknown",
            ) from exc

        files = request.get("files", []) or []
        normalized: list[dict[str, Any]] = []
        for f in files:
            fid = f.get("id", "") or ""
            normalized.append(
                {
                    "id": fid,
                    "name": f.get("name", ""),
                    "mimeType": f.get("mimeType", ""),
                    "modifiedTime": f.get("modifiedTime", ""),
                    "webViewLink": f.get("webViewLink")
                    or (f"https://drive.google.com/file/d/{fid}/view" if fid else None),
                }
            )
        return full_q, normalized

    async def search(
        self,
        q_fragment: str,
        *,
        page_size: Optional[int] = None,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Async wrapper around `search_sync` (thread offload)."""
        return await asyncio.to_thread(self.search_sync, q_fragment, page_size=page_size)


def format_tool_result_for_llm(files: list[dict[str, Any]]) -> str:
    """Compact JSON for ToolMessage content."""
    return json.dumps({"count": len(files), "files": files}, ensure_ascii=False)
