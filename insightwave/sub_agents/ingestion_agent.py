from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
import pandas as pd
import os
from google.cloud import storage
import json
import datetime

def download_and_process_files_from_gcs(bucket_name: str, tool_context : ToolContext):
    """
    Downloads all files from a GCS bucket to a unique, timestamped local directory.
    If a file is an Excel (.xlsx) file, it converts each sheet into a separate CSV.
    Other files are downloaded as-is.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)

    # Create a unique directory for this run using a timestamp.
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    output_directory = f"processed_csvs_{timestamp}"

    os.makedirs(output_directory, exist_ok=True)
    absolute_output_dir = os.path.abspath(output_directory)
    print(f"Saving files to: {absolute_output_dir}")

    try:
        blobs = list(storage_client.list_blobs(bucket_name))
        if not blobs:
            return f"Warning: No files found in bucket '{bucket_name}'."

        for blob in blobs:
            # Skip directories
            if blob.name.endswith('/'):
                continue

            destination_path = os.path.join(output_directory, os.path.basename(blob.name))
            print(f"  Downloading {blob.name}...")
            blob.download_to_filename(destination_path)

            # If it's an Excel file, process it into multiple CSVs
            if blob.name.endswith('.xlsx'):
                print(f"  Converting Excel file: {os.path.basename(destination_path)}")
                try:
                    xlsx = pd.ExcelFile(destination_path)
                    base_name = os.path.splitext(os.path.basename(destination_path))[0]

                    for sheet_name in xlsx.sheet_names:
                        # Sanitize sheet name for filename
                        safe_sheet_name = "".join([c for c in sheet_name if c.isalpha() or c.isdigit() or c in (' ', '-')]).rstrip()
                        csv_filename = f"{base_name} - {safe_sheet_name}.csv"
                        csv_filepath = os.path.join(output_directory, csv_filename)
                        df = pd.read_excel(xlsx, sheet_name)
                        df.to_csv(csv_filepath, index=False)
                        print(f"    -> Saved sheet '{sheet_name}' as '{csv_filename}'")
                    
                    # Remove the original .xlsx file after conversion
                    os.remove(destination_path)

                except Exception as e:
                    print(f"    -> Failed to convert Excel file {blob.name}. Error: {e}. Leaving as is.")
            else:
                print(f"  Saved non-Excel file: {os.path.basename(destination_path)}")

        success_message = f"✅ Success! Files from GCS bucket '{bucket_name}' were downloaded and processed into directory: {absolute_output_dir}"
        print(success_message)
        
        tool_context.state['directory_path'] = absolute_output_dir

    except Exception as e:
        return f"An error occurred during GCS processing: {e}"

ingestion_agent = LlmAgent(
    model='gemini-2.5-flash',
    name='ingestion_agent',
    instruction="""
You are a file ingestion agent. Your only job is to process files from a GCS bucket.
1.  You will receive a GCS bucket name as input.
2.  You MUST call the `download_and_process_files_from_gcs` tool with the bucket name.
3. Once the tool has finished, call the parent agent.
""",
    tools=[download_and_process_files_from_gcs],
)
