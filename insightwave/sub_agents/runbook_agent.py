from google.adk.agents import LlmAgent
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmResponse
from google.genai import types
import time
import os
from . import utils

## Artifact bucket
# artifact_bucket = "insightwave-final-artifacts"

# def write_res_to_file(callback_context: CallbackContext, llm_response: LlmResponse):
#     if not llm_response.content or not llm_response.content.parts:
#         print("\nLLM response is empty or malformed. No modifications.")

#     filename = f'report_{time.time()}.md' 
#     with open(filename, 'w') as f:
#         f.write(llm_response.content.parts[0].text)
    
#     # Upload the final wave plan to a GCS bucket
#     try:
#         utils.upload_to_gcs(artifact_bucket, os.path.abspath(filename), f'reports/{filename}')
#         # signed_url = utils.generate_signed_url(artifact_bucket, f'reports/{filename}', 60)
#         print(f'Download generated report from: gs://{artifact_bucket}/reports/{filename}')
#         llm_response.content.parts[0].text = f'{llm_response.content.parts[0].text}\n\n**Download generated report from:** <https://storage.cloud.google.com/{artifact_bucket}/reports/{filename}?authuser=1>'
#         return llm_response
#     except Exception as e:
#         return e

mig_planning_doc_agent = LlmAgent(
    model='gemini-2.5-pro',
    name='mig_planning_doc_agent',
    instruction='''
You are an intelligent Cloud Migration Agent. Your primary function is to generate a comprehensive and detailed Migration Plan based on the provided inputs. The plan must be tailored specifically to the chosen destination environment on Google Cloud.

Input:

You will be provided with the following information in a structured format (e.g., JSON, CSV, or plain text):

destination_environment: The target Google Cloud environment. This will be one of GCE (Google Compute Engine), GCVE (Google Cloud VMware Engine), or GKE (Google Kubernetes Engine).

source_environment: A description of the current environment (e.g., on-premises vSphere 6.7, AWS EC2, another Google Cloud project).

Output:

Return the migration planning doc template based on the following rules:
1. If source_environment is "on-prem(vSphere)" AND destination_environment is "GKE":

Return : [Click here to download](https://storage.cloud.google.com/insightwave-final-artifacts/migration-pattern-doc-template/Migration%20Pattern_%20On-prem(vSphere)%20to%20GKE.docx?authuser=1)

2. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCVE":

Return : [Click here to download](https://storage.cloud.google.com/insightwave-final-artifacts/migration-pattern-doc-template/Migration%20Pattern_%20On-Prem%20(vSphere)%20to%20Google%20Cloud%20VMware%20Engine%20(GCVE).docx?authuser=1)

3. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCE":

Return : [Click here to download](https://storage.cloud.google.com/insightwave-final-artifacts/migration-pattern-doc-template/Migration%20Pattern_%20On-Prem%20(vSphere)%20to%20Google%20Compute%20Engine%20(GCE).docx?authuser=1)

4. For all other combinations:

Return only the exact string: [Coming Soon]...Document is work in progress.
''',
    # after_model_callback=write_res_to_file,
)

runbook_agent = LlmAgent(
    model='gemini-2.5-pro',
    name='runbook_agent',
    instruction="""
You are an intelligent migration agent. Your task is to act as a router and provide the user with a runbook template based on the migration path.

Input:

destination_environment: The target Google Cloud environment. This will be one of GCE (Google Compute Engine), GCVE (Google Cloud VMware Engine), or GKE (Google Kubernetes Engine).

source_environment: A description of the current environment (e.g., on-premises vSphere 6.7, AWS EC2, another Google Cloud project).

Output:

You must analyze the inputs and return a text-only response based on the rules below. Do not output the internal URLs; output the specified text string instead.

1. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCVE":

    Return : [Click here to download](https://storage.cloud.google.com/insightwave-final-artifacts/runbook-template/On-prem(vSphere)%20to%20GCVE%20Runbook%20Template.xlsx?authuser=1)

2. If source_environment is "on-prem(vSphere)" AND destination_environment is "GCE":

    Return : [Click here to download](https://storage.cloud.google.com/insightwave-final-artifacts/runbook-template/On-prem(vSphere)%20to%20GCE%20Runbook%20Template.xlsx?authuser=1)

3. For all other combinations:

    Return only the exact string: [Coming Soon]...Document is work in progress.
""",
    # after_model_callback=write_res_to_file,
)