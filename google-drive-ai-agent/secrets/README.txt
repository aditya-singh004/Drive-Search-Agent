Place your Google service account JSON here (local dev), for example:

  secrets/service-account.json

Docker Compose mounts this file into the API container. Update `GOOGLE_SERVICE_ACCOUNT_FILE`
in `backend/.env` to match your local path, and in Docker set it to `/app/service-account.json`.

Share your target Drive folder with the service account email (Viewer is enough for searches).
