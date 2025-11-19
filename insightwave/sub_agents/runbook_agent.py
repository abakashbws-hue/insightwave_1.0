from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types
import time
import os
from . import utils

artifact_bucket = os.environ.get(
    "INSIGHTWAVE_ARTIFACT_BUCKET", "insightwave-final-artifacts"
)

mig_planning_doc_agent = LlmAgent(
    model="gemini-2.5-pro",
    name="mig_planning_doc_agent",
    instruction=f"""
You are an intelligent Cloud Migration Agent. Your primary function is to generate a comprehensive and detailed Migration Plan based on the provided inputs. The plan must be tailored specifically to the chosen destination environment on Google Cloud.

Input:

You will be provided with the following information in a structured format (e.g., JSON, CSV, or plain text):

destination_environment: The target Google Cloud environment. This will be one of GCE (Google Compute Engine), GCVE (Google Cloud VMware Engine), or GKE (Google Kubernetes Engine).

source_environment: A description of the current environment (e.g., on-premises vSphere 6.7, AWS EC2, another Google Cloud project).

Output:

Return the migration planning doc template based on the following rules:
1. If source_environment is "on-prem(vSphere)" AND destination_environment is "GKE":

Return : [Click here to download]({utils.generate_signed_url(artifact_bucket, 'migration-pattern-doc-template/Migration Pattern_ On-prem(vSphere) to GKE.docx')})

2. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCVE":

Return : [Click here to download]({utils.generate_signed_url(artifact_bucket, 'migration-pattern-doc-template/Migration Pattern_ On-Prem (vSphere) to Google Cloud VMware Engine (GCVE).docx')})

3. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCE":

Return : [Click here to download]({utils.generate_signed_url(artifact_bucket, 'migration-pattern-doc-template/Migration Pattern_ On-Prem (vSphere) to Google Compute Engine (GCE).docx')})

4. For all other combinations:

Return only the exact string: [Coming Soon]...Document is work in progress.
""",
)

runbook_agent = LlmAgent(
    model="gemini-2.5-pro",
    name="runbook_agent",
    instruction=f"""
You are an intelligent migration agent. Your task is to act as a router and provide the user with a runbook template based on the migration path.

Input:

destination_environment: The target Google Cloud environment. This will be one of GCE (Google Compute Engine), GCVE (Google Cloud VMware Engine), or GKE (Google Kubernetes Engine).

source_environment: A description of the current environment (e.g., on-premises vSphere 6.7, AWS EC2, another Google Cloud project).

Output:

You must analyze the inputs and return a text-only response based on the rules below. Do not output the internal URLs; output the specified text string instead.

1. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCVE":

    Return : [Click here to download]({utils.generate_signed_url(artifact_bucket, 'runbook-template/On-prem(vSphere) to GCVE Runbook Template.xlsx')})

2. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCE":

    Return : [Click here to download]({utils.generate_signed_url(artifact_bucket, 'runbook-template/On-prem(vSphere) to GCE Runbook Template.xlsx')})

3. For all other combinations:

    Return only the exact string: [Coming Soon]...Document is work in progress.
""",
)
