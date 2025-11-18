from google.cloud import storage
import json
import csv
import os
import datetime
import json
import logging
from docx import Document
import time
import random
from google import genai
from google.genai.types import (
    HarmCategory,
    HarmBlockThreshold,
    GenerateContentConfig,
    SafetySetting,
    ThinkingConfig,
)
from google.api_core import exceptions

# --- Logging Configuration ---
# Set the logging level from an environment variable, defaulting to INFO
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level, format="%(asctime)s - %(levelname)s - [%(module)s] - %(message)s"
)


# --- Google AI Configuration ---
client = genai.Client(vertexai=True)

safety_settings = [
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
    SafetySetting(
        category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=HarmBlockThreshold.BLOCK_NONE,
    ),
]

generation_config = GenerateContentConfig(
    temperature=0.3,
    top_p=0.95,
    response_mime_type="application/json",
    thinking_config=ThinkingConfig(thinking_budget=10000),
    safety_settings=safety_settings,
)

# Initialize the Vertex AI model
MODEL = "gemini-2.5-flash"


def print_token_usage(response, call_description: str):
    """Prints the token usage from the LLM response."""
    try:
        usage = response.usage_metadata
        logging.debug(
            f"LLM Token usage for '{call_description}': "
            f"Prompt: {usage.prompt_token_count}, "
            f"Response: {usage.candidates_token_count or 0}, "
            f"Thought Token Count : {getattr(usage, 'thoughts_token_count', 'N/A')},"
            f"Total: {usage.total_token_count}"
        )
    except Exception as e:
        logging.warning(f"Unable to retrieve token usage: {e}")


def log_llm_error(debug_dir: str, prompt: str, error: Exception, call_description: str):
    """Logs LLM errors to a file in the debug directory."""
    try:
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        log_file_path = os.path.join(debug_dir, "error.log")
        with open(log_file_path, "a") as f:
            f.write(f"--- LLM Error: {time.ctime()} ---\n")
            f.write(f"Call Description: {call_description}\n")
            f.write(f"Error Type: {type(error).__name__}\n")
            f.write(f"Error Details: {error}\n")
            f.write("--- Full Prompt ---\n")
            f.write(prompt)
            f.write("\n--- End of Error Log ---\n\n")
        logging.error(
            f"LLM call failed for '{call_description}'. Details logged to {os.path.abspath(log_file_path)}"
        )
    except Exception as log_e:
        logging.critical(f"Could not write to error log. Log Error: {log_e}")
        logging.critical(f"Original Error: {error}")


def generate_content_with_retry(
    prompt: str,
    call_description: str,
    debug_dir: str,
    max_retries: int = 5,
    delay: int = 10,
):
    """
    Calls model.generate_content with retry logic for transient service errors.
    """
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL, contents=prompt, config=generation_config
            )
            if not response.candidates:
                raise ValueError("LLM response was empty (no candidates).")
            print_token_usage(response, call_description)
            return response
        except (exceptions.ServiceUnavailable, exceptions.ResourceExhausted) as e:
            if attempt + 1 >= max_retries:
                log_llm_error(debug_dir, prompt, e, call_description)
                raise e
            jitter = random.uniform(0, 5)
            backoff_delay = delay * (2**attempt) + jitter
            logging.warning(
                f"Service error for '{call_description}' (Attempt {attempt + 1}/{max_retries}). Retrying in {backoff_delay:.2f}s..."
            )
            time.sleep(backoff_delay)
        except Exception as e:
            log_llm_error(debug_dir, prompt, e, call_description)
            raise e


def parse_model_response(response):
    """Parses the JSON from a model's text response robustly."""
    raw_text = response.text
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace == -1 or last_brace == -1:
        raise json.JSONDecodeError("No JSON object found in response.", raw_text, 0)
    clean_json_text = raw_text[first_brace : last_brace + 1]
    return json.loads(clean_json_text)


def upload_to_gcs(bucket_name: str, source_path: str, destination_path: str):
    """Uploads all files to a GCS bucket to a unique, timestamped directory.

    Args:
        bucket_name (str): The name of your GCS bucket.
        source_path (str): The local path to the file to upload.
        destination_path (str): The path to the file in the GCS bucket.

    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    try:
        blob = bucket.blob(destination_path)
        blob.upload_from_filename(source_path)
        logging.info(
            f"Successfully uploaded {source_path} to gs://{bucket_name}/{destination_path}"
        )
    except Exception as e:
        logging.error(f"Error uploading {source_path} to GCS: {e}")


def generate_signed_url(
    bucket_name: str, blob_name: str, expiration_minutes: int = 60
) -> str:
    """Generates a signed URL for a GCS object.

    Args:
        bucket_name (str): The name of your GCS bucket.
        blob_name (str): The name of the object (file) within the bucket.
        expiration_minutes (int): The number of minutes the URL should be valid for.

    Returns:
        str: The generated signed URL.
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Set the expiration time for the URL
        expiration_time = datetime.timedelta(minutes=expiration_minutes)

        # Generate the signed URL using the v4 signing process
        signed_url = blob.generate_signed_url(
            version="v4",
            expiration=expiration_time,
            method="GET",
        )
        return signed_url
    except Exception as e:
        logging.error(
            f"Error generating signed URL for gs://{bucket_name}/{blob_name}. Error: {e}"
        )
        # Fallback to a standard URL to avoid breaking the flow, though it may not be accessible.
        return f"https://storage.cloud.google.com/{bucket_name}/{blob_name}"


def read_document(file_path):
    """Reads the document paragraphs and tables.

    Args:
        file_path (str): Path to the document file.

    Returns:
        str: The generated signed URL.
    """
    try:
        doc = Document(file_path)

        for paragraph in doc.paragraphs:
            logging.debug(f"Doc Paragraph: {paragraph.text}")

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    logging.debug(f"Doc Cell: {cell.text}")

        return None
    except Exception as e:
        logging.error(f"Error reading document: {e}")
        return None


def update_document(json_data, file_path):
    """Updates the document with the wave plan summary.

    Args:
        json_data (str): Path to the JSON file.
        file_path (str): Path to the document file.

    Returns:
        doc: The updated document object.
    """
    try:
        doc = Document(file_path)
        with open(json_data, "r") as f:
            json_data = json.load(f)
            doc.add_paragraph("7. Wave Plan Summary")
            doc.add_paragraph(json.dumps(json_data))
            doc.save(file_path)

        return doc
    except Exception as e:
        logging.error(f"Error updating document: {e}")
        return None


def download_gcs_file(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the GCS bucket to a local file.

    Args:
        bucket_name (str): The ID of your GCS bucket.
        source_blob_name (str): The ID of your GCS object (the file in GCS).
        destination_file_name (str): The path and name where the file should be downloaded locally.
    """
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(source_blob_name)

        blob.download_to_filename(destination_file_name)

        logging.info(
            f"File {source_blob_name} downloaded to {destination_file_name} successfully."
        )
    except Exception as e:
        logging.error(f"Error downloading file: {e}")


def convert_migration_plan_to_csv(json_file_path, csv_file_path):
    """
    Reads a migration plan from a JSON file and converts it into a CSV format.

    The script iterates through each migration wave defined in the JSON,
    and for each server assigned to a wave, it writes a corresponding row
    to the CSV file.

    Args:
        json_file_path (str): The path to the input JSON file.
        csv_file_path (str): The path for the output CSV file.
    """
    # Check if the JSON file exists
    if not os.path.exists(json_file_path):
        logging.error(f"The file '{json_file_path}' was not found.")
        logging.error(
            "Please make sure the JSON file is in the same directory as the script."
        )
        return

    # Load the JSON data from the file
    with open(json_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Open the CSV file for writing
    with open(csv_file_path, "w", newline="", encoding="utf-8") as csvfile:
        # Define the CSV header
        header = [
            "Server Name",
            "Wave Name",
            "Wave Priority",
            "Wave Objective",
            "Wave Rationale",
        ]
        writer = csv.writer(csvfile)

        # Write the header row
        writer.writerow(header)

        # Get the wave definitions from the JSON data
        wave_definitions = data.get("wave_definitions", {})

        # Iterate through each wave in the wave definitions
        for wave_name, wave_details in wave_definitions.items():
            priority = wave_details.get("priority", "N/A")
            objective = wave_details.get("objective", "N/A")
            rationale = wave_details.get("rationale", "N/A")
            servers = wave_details.get("wave_assignment", [])

            # For each server in the wave, write a row to the CSV
            if not servers:
                # Write a row even if the wave has no servers assigned
                writer.writerow(["", wave_name, priority, objective, rationale])
            else:
                for server_name in servers:
                    writer.writerow(
                        [server_name, wave_name, priority, objective, rationale]
                    )

    logging.info(f"Successfully converted '{json_file_path}' to '{csv_file_path}'.")
    logging.info(
        f"Total servers processed: {data.get('summary', {}).get('total_servers_migrating', 'N/A')}"
    )
