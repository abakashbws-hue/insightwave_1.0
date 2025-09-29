from google.adk.agents import LlmAgent, SequentialAgent
from google.adk.tools import AgentTool

# --- Import your defined sub-agents ---
from .sub_agents.blueprint_generator_agent import blueprint_generator_agent
from .sub_agents.config_normalizer_agent import config_normalizer_agent
from .sub_agents.group_assignment_agent import group_assignment_agent
from .sub_agents.ingestion_agent import ingestion_agent
from .sub_agents.runbook_agent import runbook_agent, mig_planning_doc_agent
from .sub_agents.report_export_agent import report_export_agent
from .sub_agents.validation_agent import validation_agent


grouping_and_validation_agent = SequentialAgent(
    name="grouping_and_validation_agent",
    description="An orchestrator agent that takes a blueprint and golden record, assigns servers to waves, validates the plan, and generates final reports.",
    sub_agents=[
        group_assignment_agent,
        validation_agent,
        report_export_agent,
    ],
)


migration_agent = LlmAgent(
    model="gemini-2.5-pro",
    name="migration_agent",
    description="Orchestrates the data-driven wave planning process, handling user feedback at each stage.",
    instruction="""
    You are the master orchestrator for a migration planning workflow. Your only job is to execute a sequence of specialist agents based on the guidelines below. 
    You must PROACTIVELY call the next sub-agent in the sequence as soon as the previous one completes, without waiting for user input.
    **WORKFLOW:**
    You must follow thse steps in the EXACT sequence below:
    1. Call `ingestion_agent` to ingest data from the provided GCS path.
    2. Call `config_normalizer_agent` to normalize the configuration files.
    3. Call `blueprint_generator_agent` to create the migration blueprint.
    4. Call `grouping_and_validation_agent` to group the servers and validate the plan.
    """,
    sub_agents=[ingestion_agent, config_normalizer_agent, blueprint_generator_agent, grouping_and_validation_agent],
)

pattern_doc_agent = LlmAgent(
    model='gemini-2.5-pro',
    name='pattern_doc_agent',
    description="A specialist agent for generating high-level, human-readable migration documentation. Use this agent ONLY when the user explicitly asks for a 'migration plan' or a 'runbook' document. This agent does not process raw data.",    
    instruction='''
    You are a Migration Assistant Agent. Your purpose is to help users generate migration documentation for Google Cloud. Your primary function is to gather the necessary information from the user and then call the correct sub-agent to fulfill the request.
    
    [CONTEXT]
    You need to fill two critical information slots before you can proceed:
    - destination: The target Google Cloud service. Must be one of GCE, GCVE, or GKE.
    - document_type: The type of document to generate. Must be one of migration_plan or migration_runbook.
    
    You have access to two sub-agents:
    - mig_planning_doc_agent(destination, source): Generates a strategic migration plan.
    - runbook_agent(destination, source): Generates a tactical migration runbook.
    
    [TASK]
    Your task is to manage a conversation with the user to fill the destination and document_type slots. Follow this logic:
    
    1. Initial Analysis: First, analyze the user's initial query to see if the destination or document_type is already provided.
    2. Gather Destination: If the destination is missing, ask the user for it: "What is your target destination on Google Cloud? You can choose from GCE, GCVE, or GKE."
    3. Validation: If the user provides an invalid destination, gently correct them: "That's not a valid option. Please choose from GCE, GCVE, or GKE."
    4. Gather Document Type: If the document_type is missing, ask the user for it: "Great. Now, what type of document do you need? A strategic 'migration plan' or a step-by-step 'migration runbook'?"
    5. Execution: Once both destination and document_type slots are filled, execute the final tool call.
        - IF document_type is migration_plan, THEN you MUST call the mig_planning_doc_agent.
        - IF document_type is migration_runbook, THEN you MUST call the runbook_agent.
    
    Pass the collected destination and any other relevant details from the conversation to the chosen sub-agent.
''',
    sub_agents=[runbook_agent, mig_planning_doc_agent]
)

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="root_agent",
    instruction="""
    You are the master router for the "Insight Wave" migration planning framework. Your sole responsibility is to analyze the user's initial request and delegate it to the correct specialist agent.
    
    - If the user's request mentions a GCS bucket path (`gs://...`) or analyzing server data, delegate to the `migration_agent`.
    - If the user asks for a generic "migration plan" or "runbook" without a data source, delegate to the `pattern_doc_agent`.
    """,
    sub_agents=[migration_agent, pattern_doc_agent],
)