from google.cloud import storage
import os
import datetime
import json
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
        print(
            f"    Token usage for '{call_description}': "
            f"Prompt: {usage.prompt_token_count}, "
            f"Response: {usage.candidates_token_count or 0}, "
            f"Thought Token Count : {getattr(usage, 'thoughts_token_count', 'N/A')},"
            f"Total: {usage.total_token_count}"
        )
    except Exception as e:
        print(f"Unable to print the token usage: {e}")


def log_llm_error(debug_dir: str, prompt: str, error: Exception, call_description: str):
    """Logs LLM errors to a file in the debug directory."""
    try:
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        log_file_path = os.path.join(debug_dir, 'error.log')
        with open(log_file_path, 'a') as f:
            f.write(f"--- LLM Error: {time.ctime()} ---\n")
            f.write(f"Call Description: {call_description}\n")
            f.write(f"Error Type: {type(error).__name__}\n")
            f.write(f"Error Details: {error}\n")
            f.write("--- Full Prompt ---\n")
            f.write(prompt)
            f.write("\n--- End of Error Log ---\n\n")
        print(f"    ERROR: LLM call failed for '{call_description}'. Details logged to {os.path.abspath(log_file_path)}")
    except Exception as log_e:
        print(f"    FATAL: Could not write to error log. Log Error: {log_e}")
        print(f"    Original Error: {error}")


def generate_content_with_retry(
    prompt: str, call_description: str, debug_dir: str, max_retries: int = 5, delay: int = 10
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
            print(f"    WARNING: Service error for '{call_description}' (Attempt {attempt + 1}/{max_retries}). Retrying in {backoff_delay:.2f}s...")
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
    try :
        blob = bucket.blob(destination_path)
        blob.upload_from_filename(source_path)
        print("Files uploaded successfully to GCS.")
    except Exception as e:
        print(f"Error uploading files to GCS: {e}")

def generate_signed_url(bucket_name, blob_name, expiration_seconds, method="GET"):
    """Generates a signed URL for a GCS object.

    Args:
        bucket_name (str): The name of your GCS bucket.
        blob_name (str): The name of the object (file) within the bucket.
        expiration_seconds (int): The duration in seconds for which the URL will be valid.
        method (str, optional): The HTTP method allowed for the signed URL (e.g., "GET", "PUT", "DELETE"). Defaults to "GET".

    Returns:
        str: The generated signed URL.
    """
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    # Set the expiration time
    expiration_time = datetime.timedelta(seconds=expiration_seconds)

    # Generate the signed URL
    signed_url = blob.generate_signed_url(
        expiration=expiration_time,
        method=method
    )
    return signed_url

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
            print(paragraph.text)

        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    print(cell.text)

        return None
    except Exception as e:
        print(f"Error reading document: {e}")
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
        with open(json_data, 'r') as f:
            json_data = json.load(f)
            doc.add_paragraph('7. Wave Plan Summary')
            doc.add_paragraph(json.dumps(json_data))
            doc.save(file_path)

        return doc
    except Exception as e:
        print(f"Error reading document: {e}")
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

        print(f"File {source_blob_name} downloaded to {destination_file_name} successfully.")
    except Exception as e:
        print(f"Error downloading file: {e}")