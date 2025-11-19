from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
from . import utils
from google.cloud import storage
import json
import os

artifact_bucket = os.environ.get(
    "INSIGHTWAVE_ARTIFACT_BUCKET", "insightwave-final-artifacts"
)


def update_pattern_doc(tool_context: ToolContext, destination_environment: str):
    """Appends the wave plan summary to the pattern doc template"""
    json_file_path = tool_context.state.get("wave_plan_path")
    if destination_environment not in ["GKE", "GCVE", "GCE"]:
        return "Not a valid destination environment."
    else:
        template_path = (
            "Migration Pattern_ On-Prem (vSphere) to Google Cloud VMware Engine (GCVE).docx"
            if destination_environment == "GCVE"
            else (
                "Migration Pattern_ On-Prem (vSphere) to Google Compute Engine (GCE).docx"
                if destination_environment == "GCE"
                else "Migration Pattern_ On-prem(vSphere) to GKE.docx"
            )
        )
        output_path = "/".join(json_file_path.split("/")[:-1]) + template_path
        utils.download_gcs_file(
            artifact_bucket,
            f"migration-pattern-doc-template/{template_path}",
            output_path,
        )
        utils.update_document(json_file_path, output_path)
        blob_path = f"reports/{template_path}"
        utils.upload_to_gcs(artifact_bucket, output_path, blob_path)
        return utils.generate_signed_url(artifact_bucket, blob_path)


report_export_agent = LlmAgent(
    model="gemini-2.5-pro",
    name="report_export_agent",
    instruction="""
You are an intelligent Cloud Migration Agent. Your primary function is to generate a comprehensive and detailed Migration Plan based on the provided inputs. The plan must be tailored specifically to the chosen destination environment on Google Cloud.

Instructions:

1. Prompt User: Ask the user the following question exactly and wait for their response:

    "Please select the destination migration pattern. The source is on-prem vSphere.

        a. GCE (on-prem vSphere to GCE)

        b. GKE (on-prem vSphere to GKE)

        c. GCVE (on-prem vSphere to GCVE)

        Please reply with GCE, GKE, or GCVE."

2. Receive Response: Get the user's string response (e.g., "GCE").

3. Validate Response: Confirm the user's response is one of "GCE", "GKE", or "GCVE".

4. Call Tool: Execute the `update_pattern_doc` tool and pass the validated `destination_environment` as a parameter.

5. Return Output: Respond with a user-friendly message in markdown with the GCS URL returned by the update_pattern tool.

For example:
    "The migration pattern doc has been successfully generated.
    You can view the full artifacts here:
    - **Pattern Doc**: View Pattern Document

""",
    tools=[update_pattern_doc],
)
