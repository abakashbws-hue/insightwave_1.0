from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
import pandas as pd
import os
from google.cloud import storage
import datetime
import re
import io
import google.auth
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
import logging
from typing import Any

# --- Helper Functions ---


def _get_timestamped_dir():
    """Creates a unique directory for this run."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    output_directory = f"processed_csvs_{timestamp}"
    os.makedirs(output_directory, exist_ok=True)
    return os.path.abspath(output_directory)


def _process_local_file(file_path, output_dir):
    """
    Processes a local file. If Excel, converts to CSVs and deletes original.
    If CSV, verifies it and leaves it.
    """
    filename = os.path.basename(file_path)

    if filename.lower().endswith(".xlsx"):
        logging.info(f"Converting Excel file: {filename}")
        try:
            xlsx = pd.ExcelFile(file_path)
            base_name = os.path.splitext(filename)[0]

            for sheet_name in xlsx.sheet_names:
                # Sanitize sheet name
                safe_sheet_name = "".join(
                    [
                        c
                        for c in sheet_name
                        if c.isalpha() or c.isdigit() or c in (" ", "-")
                    ]
                ).rstrip()
                csv_filename = f"{base_name} - {safe_sheet_name}.csv"
                csv_filepath = os.path.join(output_dir, csv_filename)

                df = pd.read_excel(xlsx, sheet_name)
                df.to_csv(csv_filepath, index=False)
                logging.info(f"  -> Saved sheet '{sheet_name}' as '{csv_filename}'")

            # Remove the original .xlsx file after conversion
            os.remove(file_path)
        except Exception as e:
            logging.error(
                f"Failed to convert Excel file {filename}. Error: {e}. Deleting file."
            )
            # If conversion fails, we might want to remove the corrupt/unusable xlsx
            if os.path.exists(file_path):
                os.remove(file_path)
    else:
        # It's a CSV (filtered by the downloader)
        logging.info(f"Saved CSV file: {filename}")


def _extract_drive_id(url):
    """Extracts file or folder ID from a Google Drive URL."""
    patterns = [r"folders/([a-zA-Z0-9-_]+)", r"/d/([a-zA-Z0-9-_]+)"]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return url


# --- Tools ---


def download_and_process_files_from_gcs(bucket_name: str, tool_context: ToolContext):
    """
    Downloads only .xlsx and .csv files from a GCS bucket to a unique local directory.
    Converts Excel files to CSVs.
    """
    storage_client = storage.Client()

    absolute_output_dir = _get_timestamped_dir()
    logging.info(f"Saving GCS files to: {absolute_output_dir}")

    try:
        bucket = storage_client.bucket(bucket_name)
        blobs = list(storage_client.list_blobs(bucket_name))

        if not blobs:
            return f"Warning: No files found in bucket '{bucket_name}'."

        files_processed_count = 0

        for blob in blobs:
            if blob.name.endswith("/"):
                continue  # Skip directories

            # FILTER: Only allow .xlsx and .csv
            if not (
                blob.name.lower().endswith(".xlsx")
                or blob.name.lower().endswith(".csv")
            ):
                logging.info(f"Skipping unsupported file type: {blob.name}")
                continue

            destination_path = os.path.join(
                absolute_output_dir, os.path.basename(blob.name)
            )
            logging.info(f"Downloading {blob.name}...")
            blob.download_to_filename(destination_path)

            _process_local_file(destination_path, absolute_output_dir)
            files_processed_count += 1

        if files_processed_count == 0:
            return f"No valid .xlsx or .csv files found in bucket '{bucket_name}'."

        success_msg = f"✅ Success! {files_processed_count} files processed from GCS into: {absolute_output_dir}"
        logging.info(success_msg)
        tool_context.state["directory_path"] = absolute_output_dir
        return success_msg

    except Exception as e:
        return f"An error occurred during GCS processing: {e}"


def download_and_process_files_from_drive(drive_url: str, tool_context: ToolContext):
    """
    Downloads only .xlsx and .csv files from Google Drive to a local directory.
    """
    creds, _ = google.auth.default()

    # FIX: Type hint as 'Any' to suppress 'no member' linter errors
    service: Any = build("drive", "v3", credentials=creds)

    file_id = _extract_drive_id(drive_url)
    logging.info(f"The FILE ID for GDrive is: {file_id}")
    absolute_output_dir = _get_timestamped_dir()
    logging.info(f"Saving Drive files to: {absolute_output_dir}")

    try:
        # Linter will now ignore .files() calls on 'service'
        file_metadata = (
            service.files().get(fileId=file_id, fields="id, name, mimeType").execute()
        )
        mime_type = file_metadata.get("mimeType")

        logging.debug(f"File metadata: {file_metadata}")

        files_to_download = []

        if mime_type == "application/vnd.google-apps.folder":
            logging.info(f"Detected Folder: {file_metadata.get('name')}")
            # Efficiently query for only supported file types within the folder.
            query = (
                f"'{file_id}' in parents and trashed = false and ("
                f"mimeType = 'application/vnd.google-apps.spreadsheet' or "
                f"mimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' or "
                f"mimeType = 'text/csv'"
                f")"
            )
            results = (
                service.files()
                .list(q=query, fields="files(id, name, mimeType)")
                .execute()
            )
            files_to_download = results.get("files", [])
        else:
            logging.info(f"Detected Single File: {file_metadata.get('name')}")
            files_to_download = [file_metadata]

        if not files_to_download:
            return "No files found at the provided Drive URL."

        files_processed_count = 0

        for file_item in files_to_download:
            f_id = file_item["id"]
            f_name = file_item["name"]
            f_mime_type = file_item.get("mimeType")

            # --- Robust File Type Handling ---
            is_google_sheet = f_mime_type == "application/vnd.google-apps.spreadsheet"
            is_xlsx = f_name.lower().endswith(".xlsx")
            is_csv = f_name.lower().endswith(".csv")

            if not (is_google_sheet or is_xlsx or is_csv):
                logging.info(
                    f"Skipping unsupported file type: {f_name} ({f_mime_type})"
                )
                continue

            try:
                if is_google_sheet:
                    logging.info(f"Exporting Google Sheet: {f_name}...")
                    # Google Sheets must be exported, not downloaded directly.
                    request = service.files().export_media(
                        fileId=f_id,
                        mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                    # Save with an .xlsx extension so it can be processed correctly.
                    destination_path = os.path.join(
                        absolute_output_dir, f"{os.path.splitext(f_name)[0]}.xlsx"
                    )
                else:
                    # For regular .xlsx and .csv files
                    logging.info(f"Downloading {f_name}...")
                    request = service.files().get_media(fileId=f_id)
                    destination_path = os.path.join(absolute_output_dir, f_name)

                # Common download logic
                fh = io.FileIO(destination_path, "wb")
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while done is False:
                    status, done = downloader.next_chunk()
                    logging.debug(
                        f"    -> Downloading {f_name}: {int(status.progress() * 100)}%"
                    )

                _process_local_file(destination_path, absolute_output_dir)
                files_processed_count += 1
            except Exception as download_error:
                logging.error(
                    f"Failed to process file {f_name}. Error: {download_error}"
                )

        if files_processed_count == 0:
            return "No valid .xlsx or .csv files found at the provided Drive URL."

        success_msg = f"✅ Success! {files_processed_count} files processed from Drive into: {absolute_output_dir}"
        logging.info(success_msg)
        tool_context.state["directory_path"] = absolute_output_dir
        return success_msg

    except Exception as e:
        if isinstance(e, HttpError) and e.resp.status in [403, 404]:
            error_message = (
                "Error: Access to the Google Drive file or folder failed. This can happen if the item doesn't exist, was deleted, or if the agent does not have permission.\n\n"
                "**Please ensure you have shared the Google Drive file or folder with `insightwave-agent@google.com` and granted at least 'Viewer' access.**"
            )
            logging.error(f"Google Drive access error: {e}. Instructing user to share file.")
            return error_message
        else:
            logging.error(f"An unexpected error occurred during Drive processing: {e}")
            return f"An unexpected error occurred during Drive processing: {e}"


# --- Agent Definition ---

ingestion_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="ingestion_agent",
    instruction="""
You are a file ingestion agent. Your job is to process data files from external sources.
1. If the user provides a GCS bucket name, use `download_and_process_files_from_gcs`.
2. If the user provides a Google Drive URL (folder or file link), use `download_and_process_files_from_drive`.
3. Once the tool has finished, call the parent agent.
""",
    tools=[download_and_process_files_from_gcs, download_and_process_files_from_drive],
)
