from google.api_core import exceptions
from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
import pandas as pd
import json
import os
import logging
import time
from . import utils


def get_token_count(contents, model):
    return utils.client.models.count_tokens(model=model, contents=contents).total_tokens


def dynamic_chunking(
    df: pd.DataFrame,
    overhead_tokens: int,
    max_prompt_tokens: int = 900000,
    sample_size: int = 200,
):
    """
    Calculates an intelligent chunk size by sampling the data to get a more accurate
    tokens-per-row estimate. This is much faster than counting tokens for every row or for the entire file.
    """
    if df.empty:
        return 0

    # 1. Take a representative sample of the data.
    sample_df = df.sample(n=min(len(df), sample_size), random_state=42)
    if sample_df.empty:
        # If for some reason the sample is empty but the df is not, fall back to a safe default.
        return 100

    # 2. Count tokens for the JSON representation of the sample, which is what the model sees.
    sample_tokens = get_token_count(sample_df.to_json(orient="records"), utils.MODEL)
    logging.debug(
        f"Dynamic chunking: Sample of {len(sample_df)} rows has {sample_tokens} tokens."
    )

    # 3. Calculate a more accurate average tokens per row based on the sample.
    tokens_per_row = sample_tokens / len(sample_df) if len(sample_df) > 0 else 1

    # 4. Calculate the available token budget for the data portion of the prompt.
    data_token_budget = max_prompt_tokens - overhead_tokens
    if data_token_budget <= 0:
        logging.warning(
            f"Prompt overhead ({overhead_tokens} tokens) exceeds the max prompt token limit ({max_prompt_tokens}). This will likely fail. Chunk size set to a minimal 10 rows."
        )
        return 10

    # 5. Calculate how many rows can fit into the data budget.
    rows_per_chunk = (
        int(data_token_budget / tokens_per_row) if tokens_per_row > 0 else len(df)
    )
    logging.debug(
        f"Dynamic chunking: Tokens per row: ~{tokens_per_row:.2f}. Data budget: {data_token_budget} tokens. Calculated rows per chunk: {rows_per_chunk}."
    )

    # 6. Ensure we return a sensible chunk size.
    return max(1, rows_per_chunk)


def _merge_blueprint_changes(current_blueprint, changes):
    """
    Merges a 'diff' of changes into the current blueprint.
    Handles removals, additions, and modifications, then re-sorts.
    """
    if not isinstance(changes, dict):
        logging.warning(
            f"Refinement response is not a valid JSON object. Skipping refinement. Raw response: {changes}"
        )
        return current_blueprint

    wave_names_to_remove = changes.get("wave_names_to_remove", [])
    if wave_names_to_remove:
        logging.info(
            f"Removing {len(wave_names_to_remove)} wave definition(s): {wave_names_to_remove}"
        )
        if "wave_definitions" in current_blueprint and isinstance(
            current_blueprint.get("wave_definitions"), list
        ):
            current_blueprint["wave_definitions"] = [
                wave
                for wave in current_blueprint["wave_definitions"]
                if wave.get("wave_name") not in wave_names_to_remove
            ]

    new_waves = changes.get("new_wave_definitions", [])
    if new_waves:
        logging.info(f"Adding {len(new_waves)} new wave definition(s).")
        if "wave_definitions" not in current_blueprint or not isinstance(
            current_blueprint.get("wave_definitions"), list
        ):
            current_blueprint["wave_definitions"] = []
        current_blueprint["wave_definitions"].extend(new_waves)

    modified_waves = changes.get("modified_wave_definitions", [])
    if modified_waves:
        logging.info(f"Modifying {len(modified_waves)} existing wave definition(s).")
        if "wave_definitions" not in current_blueprint or not isinstance(
            current_blueprint.get("wave_definitions"), list
        ):
            current_blueprint["wave_definitions"] = []

        existing_waves_dict = {
            wave.get("wave_name"): wave
            for wave in current_blueprint["wave_definitions"]
            if isinstance(wave, dict)
        }

        for modified_wave in modified_waves:
            wave_name_to_modify = modified_wave.get("wave_name")
            if wave_name_to_modify in existing_waves_dict:
                for i, wave in enumerate(current_blueprint["wave_definitions"]):
                    if (
                        isinstance(wave, dict)
                        and wave.get("wave_name") == wave_name_to_modify
                    ):
                        current_blueprint["wave_definitions"][i] = modified_wave
                        break
            else:
                logging.warning(
                    f"Model tried to modify a non-existent wave: '{wave_name_to_modify}'. Adding it as a new wave instead."
                )
                current_blueprint["wave_definitions"].append(modified_wave)

    if new_waves or modified_waves or wave_names_to_remove:
        if "wave_definitions" in current_blueprint and isinstance(
            current_blueprint["wave_definitions"], list
        ):
            current_blueprint["wave_definitions"].sort(
                key=lambda x: x.get("priority", 999) if isinstance(x, dict) else 999
            )

    return current_blueprint


def create_blueprint_iteratively(
    df_input: pd.DataFrame,
    config_path: str,
    debug_dir: str,
    primary_key_column: str,
    user_feedback: str = "",
):
    """
    Creates a migration blueprint by generating an initial version from the first
    data chunk and then iteratively refining it with all subsequent chunks.
    The sole output is the final, refined blueprint.
    """
    logging.info("--- Starting Blueprint Creation via Iterative Refinement ---")

    try:
        with open(config_path, "r") as f:
            config_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logging.critical(f"Could not load config file at '{config_path}'. Error: {e}")
        return None

    df = df_input

    # Prompt for creating the initial blueprint from the first chunk
    initial_prompt_template = """You are a master migration wave planner which runs third in the sequence of a multi agent migration planning framework called "Insight Wave". Your task is to create a strategic "Migration Blueprint" in JSON format. This blueprint must define concrete, data-driven rules for grouping servers into logical migration waves.

**Your Goal:**
To analyze the provided `consolidation_config.json` AND a chunk of server data to produce a balanced, specific set of wave definitions. Your rules must be derived from the data and the configuration's intent.

**CRITICAL: How to Create Balanced, Multi-Factor Waves**
Your primary goal is to create a BALANCED migration plan. Avoid creating waves based on a single dimension like `datacenter_loc` or `network_name` alone. Instead, you MUST create wave definitions that combine multiple attributes to represent a true logical grouping.

**Instructions:**
1.  **Isolate Decommission/Out-of-Scope Assets First:** Your first priority MUST be to create a wave for assets that are not part of the active migration but need to be cataloged. This includes powered-off machines, VM templates, vSphere Cluster Service (vCLS) VMs and other similar VMs.
    *   Create a high-priority (e.g., `priority: 1`) wave named "Decommission & Out-of-Scope".
    *   For example, the criteria for this wave should be an 'OR' condition to find:
        *   Templates (e.g., `Template` column is `True`).
        *   vCLS VMs (e.g., `asset_name` starts with `vCLS-`).
        *   Powered-off VMs (e.g., `power_state` is `poweredOff`).
        *   And any other similar Vms that fit the category.
2.  **Create Data-Driven Wave Definitions:**
    *   Based on the principles above, examine the Server Data Chunk `chunk_json` to find recurring patterns of combined attributes.
    *   For example, if you see many servers coming from one datacenter, within a specific cluster, and on a given network, that is a perfect candidate for a wave.
    *   Create a specific `wave_definition` for each significant pattern you find.
    *   Each definition MUST have a unique `wave_name`, a `priority`, an `objective`, a `rationale`, a `criteria` object, and a `sql_query`.
    *   The `wave_name` MUST be a descriptive, unique name for the group (e.g., "Production RHEL Applications", "Decommissioned Servers"). Do NOT add prefixes like "Wave 1:" or "Group A:". The name should only describe the contents of the wave. If multiple waves have a similar application context, differentiate them with a number (e.g., "SAP Apps 1", "SAP Apps 2").
    *   The `sql_query` MUST be a valid pandasql query that selects the `{primary_key_column}` from a DataFrame named `df` based on the logic in the `criteria`.
3.  **Infer Field Importance from Rationale:**
    *   Use the `rationale` in `consolidation_config.json` to understand the purpose of each field.
    *   **Application/Business Context (Highest Priority):** `cluster_name`, `app_name`, `Annotation` or other metadata fields.
    *   **Network & Location Context (Medium Priority):** `network_name`, `ip_address`, `datacenter_loc`.
    *   **Technical Context (Lowest Priority):** `guest_os`, `power_state`.
4.  **Define Field Roles:**
    *   Categorize the standardized fields from the config into `identification_fields` and `additional_context_fields`.
5.  **Format the Output:**
    *   The final output MUST be a single, clean JSON object with a root key "migration_blueprint".
    *   Inside the "migration_blueprint" object, you MUST create a key named "wave_definitions". This key must hold a JSON array containing all the wave definition objects you have created.
    *   The `criteria` object MUST follow the nested structure shown in the example below.

{user_feedback_prompt}

**Example Blueprint Structure:**
```json
{{
  "migration_blueprint": {{
    "description": "A strategic blueprint for grouping servers into logical migration waves.",
    "wave_definitions": [
      {{
        "wave_name": "Decommission & Out-of-Scope",
        "objective": "Isolate and catalog assets that are not active migration candidates.",
        "rationale": "This wave groups powered-off servers, VM templates, and internal vSphere VMs (vCLS) that should be decommissioned or are otherwise out of scope.",
        "priority": 1,
        "criteria": {{
          "or": [
            {{ "power_state": {{ "operator": "equals", "value": "poweredOff" }} }},
            {{ "Template": {{ "operator": "equals", "value": "True" }} }},
            {{ "asset_name": {{ "operator": "like", "value": "vCLS-%" }} }}
          ]
        }},
        "sql_query": "SELECT \\"{primary_key_column}\\" FROM df WHERE \\"power_state\\" = 'poweredOff' OR \\"Template\\" = 'True' OR \\"asset_name\\" LIKE 'vCLS-%'"
      }},
      {{
        "wave_name": "Production RHEL Applications",
        "objective": "To migrate all production Red Hat Enterprise Linux application servers.",
        "rationale": "This wave focuses on a homogenous group of production Linux servers.",
        "priority": 2,
        "criteria": {{
          "and": [
            {{ "environment": {{ "operator": "equals", "value": "PROD" }} }},
            {{ "guest_os": {{ "operator": "contains", "value": "Red Hat" }} }}
          ]
        }},
        "sql_query": "SELECT \\"{primary_key_column}\\" FROM df WHERE (\\"environment\\" = 'PROD' AND \\"guest_os\\" LIKE '%Red Hat%')"
      }}
    ]
  }}
}}
```

**Configuration File (`consolidation_config.json`):**
{config_json}

**Server Data Chunk (`chunk_json`):**
{chunk_json}
"""

    refinement_prompt_template = """You are a master migration wave planner. Your task is to refine an existing "Migration Blueprint" using a new chunk of server data.

    **Your Goal:**
    Analyze the `New Data Chunk` and the `Current Blueprint`. Identify new patterns or necessary modifications and return ONLY the changes.

    **Instructions:**
    1.  **Review Current Blueprint:** Understand the existing rules in the `Current Blueprint`.
    2.  **Analyze New Data:** Look for patterns in the `New Data Chunk` that are NOT well-covered by the current rules.
    3.  **Add, Modify, Consolidate, or Remove Rules:**
        *   **CRITICAL: Feel free to revamp the existing rules if the new data reveals a more logical grouping strategy. This is more important than preserving old wave definitions.**
        *   **Add:** If you find a new, distinct group of servers, create a new wave definition object for it and add it to the `new_wave_definitions` list.
        *   **Modify:** If an existing rule is too specific or inaccurate, create a modified version of that wave definition object and add it to the `modified_wave_definitions` list. Ensure the `wave_name` matches the original exactly so it can be updated.
        *   **Consolidate:** If you find that two or more waves are very similar and should be merged, create a new consolidated wave definition and add it to `new_wave_definitions` (or `modified_wave_definitions` if it's an update to one of the existing waves). Then, list the names of the old waves that are now redundant in the `wave_names_to_remove` list.
        *   **Remove:** If a wave is redundant, empty, or no longer makes sense based on the new data, add its name to the `wave_names_to_remove` list.
    4.  **Return ONLY the Changes:** Your output MUST be a JSON object containing any of the following keys: "new_wave_definitions", "modified_wave_definitions", and "wave_names_to_remove".
        *   If no changes are needed, return an empty object or empty lists (e.g., `{{ "new_wave_definitions": [], "modified_wave_definitions": [], "wave_names_to_remove": [] }}`).
        *   **CRITICAL: Do NOT return the entire blueprint. Only return the changes.**
        *   For any new or modified wave, you MUST include the `objective`, `rationale`, `criteria` object, and the corresponding `sql_query` string. The `wave_name` MUST be a descriptive, unique name for the group (e.g., "New Application Stack"). Do NOT add prefixes like "Wave 15:" or "Group B:".

    **Example Output (if you add one wave, modify another, and remove a third):**
    ```json
    {{
      "new_wave_definitions": [
        {{
            "wave_name": "New Application Stack",
            "objective": "Migrate the newly identified 'NewApp' application stack.",
            "rationale": "This creates a dedicated wave for a new application discovered in the data, ensuring it is handled as a distinct work package.",
            "priority": 15,
            "criteria": {{
                "and": [
                    {{ "app_name": {{ "operator": "equals", "value": "NewApp" }} }},
                    {{ "environment": {{ "operator": "equals", "value": "PROD" }} }}
                ]
            }},
            "sql_query": "SELECT \\"{primary_key_column}\\" FROM df WHERE (\\"app_name\\" = 'NewApp' AND \\"environment\\" = 'PROD')"
        }}
      ],
      "modified_wave_definitions": [
        {{
            "wave_name": "Production RHEL Applications & Databases",
            "objective": "Expand the production Linux wave to include Oracle databases.",
            "rationale": "The data shows a strong correlation between RHEL and Oracle in the production environment. Merging them into a single wave streamlines the migration of this tightly coupled stack.",
            "priority": 2,
            "criteria": {{
                "and": [
                    {{ "environment": {{ "operator": "equals", "value": "PROD" }} }},
                    {{ "or": [
                        {{ "guest_os": {{ "operator": "contains", "value": "Red Hat" }} }},
                        {{ "app_name": {{ "operator": "contains", "value": "Oracle" }} }}
                    ]}}
                ]
            }},
            "sql_query": "SELECT \\"{primary_key_column}\\" FROM df WHERE (\\"environment\\" = 'PROD' AND (\\"guest_os\\" LIKE '%Red Hat%' OR \\"app_name\\" LIKE '%Oracle%'))"
        }}
      ],
      "wave_names_to_remove": [
        "Old Redundant Wave"
      ]
    }}
    ```

    **Current Blueprint:**
    {blueprint_json}

    **New Data Chunk to Incorporate:**
    {chunk_json}
    """

    config_json_str = json.dumps(config_data, indent=2)
    user_feedback_prompt = ""
    if user_feedback:
        logging.info(f"Incorporating user feedback: {user_feedback}")
        user_feedback_prompt = (
            f"\n**USER FEEDBACK TO INCORPORATE:**\n- {user_feedback}\n"
        )

    base_prompt_for_size_calc = initial_prompt_template.format(
        primary_key_column=primary_key_column,
        config_json=config_json_str,
        chunk_json="",
        user_feedback_prompt=user_feedback_prompt,
    )
    overhead_tokens = get_token_count(base_prompt_for_size_calc, utils.MODEL)
    logging.info(
        f"Calculated prompt overhead (template + config + feedback): {overhead_tokens} tokens."
    )

    chunk_size = dynamic_chunking(df=df, overhead_tokens=overhead_tokens)
    logging.info(f"The dynamic chunk size is determined to be: {chunk_size} rows.")

    chunk_iterator = [df[i : i + chunk_size] for i in range(0, df.shape[0], chunk_size)]
    max_json_retries = 3
    current_blueprint = None

    for j, chunk_df in enumerate(chunk_iterator):
        logging.info(f"--- Processing chunk {j+1} to refine blueprint... ---")
        chunk_json_str = chunk_df.to_json(orient="records")

        if j == 0:
            logging.info("This is the first chunk. Creating initial blueprint...")
            prompt = initial_prompt_template.format(
                primary_key_column=primary_key_column,
                config_json=config_json_str,
                chunk_json=chunk_json_str,
                user_feedback_prompt=user_feedback_prompt,
            )
            logging.debug(f"Full prompt for Initial Blueprint Creation:\n{prompt}")
            call_desc = "Initial Blueprint Creation"
        else:
            if not isinstance(current_blueprint, dict):
                logging.critical(
                    "Cannot refine blueprint because it is not a valid dictionary. Aborting."
                )
                return None

            logging.info(f"Refining existing blueprint with data from chunk {j+1}...")
            prompt = refinement_prompt_template.format(
                primary_key_column=primary_key_column,
                blueprint_json=json.dumps(current_blueprint, indent=2),
                chunk_json=chunk_json_str,
            )
            logging.debug(
                f"Full prompt for Blueprint Refinement with Chunk {j+1}:\n{prompt}"
            )
            call_desc = f"Blueprint Refinement with Chunk {j+1}"

        response_json = None
        for attempt in range(max_json_retries):
            try:
                response = utils.generate_content_with_retry(
                    prompt, call_desc, debug_dir
                )
                response_json = utils.parse_model_response(response)
                break
            except json.JSONDecodeError as e:
                logging.warning(
                    f"Failed to decode JSON for '{call_desc}' (Attempt {attempt + 1}/{max_json_retries}). Retrying..."
                )
                if attempt + 1 >= max_json_retries:
                    logging.critical(
                        f"Could not parse JSON response for '{call_desc}' after {max_json_retries} attempts. Aborting blueprint creation."
                    )
                    utils.log_llm_error(debug_dir, prompt, e, call_desc)
                    return None
                time.sleep(5 * (attempt + 1))  # Exponential backoff
            except Exception as e:
                # Catch specific 503 errors that might be wrapped in a generic Exception
                if (
                    isinstance(e, exceptions.ServiceUnavailable)
                    or "503" in str(e)
                    or "UNAVAILABLE" in str(e)
                ):
                    logging.warning(
                        f"LLM service unavailable for '{call_desc}' (Attempt {attempt + 1}/{max_json_retries}). Retrying... Error: {e}"
                    )
                    if attempt + 1 >= max_json_retries:
                        logging.critical(
                            f"LLM service still unavailable after {max_json_retries} attempts. Aborting blueprint creation."
                        )
                        utils.log_llm_error(debug_dir, prompt, e, call_desc)
                        return None
                    time.sleep(5 * (attempt + 1))  # Exponential backoff
                else:
                    # Handle other, truly unrecoverable errors
                    logging.critical(
                        f"Unrecoverable error during content generation for '{call_desc}': {e}. Aborting blueprint creation."
                    )
                    utils.log_llm_error(debug_dir, prompt, e, call_desc)
                    return None

        if response_json:
            if j == 0:
                if not isinstance(response_json, dict):
                    logging.critical(
                        f"Initial blueprint response is not a valid JSON object (expected dict). Got: {type(response_json)}. Raw response: {response.text}. Aborting."
                    )
                    return None
                current_blueprint = response_json.get(
                    "migration_blueprint", response_json
                )
                if (
                    "migration_waves" in current_blueprint
                    and "wave_definitions" not in current_blueprint
                ):
                    logging.info(
                        "Normalizing blueprint key from 'migration_waves' to 'wave_definitions'."
                    )
                    current_blueprint["wave_definitions"] = current_blueprint.pop(
                        "migration_waves"
                    )

                if not isinstance(current_blueprint, dict):
                    logging.critical(
                        f"current_blueprint is not a dictionary after initial creation attempt for chunk {j+1}. Type: {type(current_blueprint)}. Aborting."
                    )
                    return None
            else:
                current_blueprint = _merge_blueprint_changes(
                    current_blueprint, response_json
                )
                logging.debug(
                    f"LLM response for chunk {j+1} refinement: {json.dumps(response_json, indent=2)}"
                )

            refined_blueprint_filename = os.path.join(
                debug_dir, f"migration_blueprint_after_chunk_{j+1}.json"
            )
            with open(refined_blueprint_filename, "w") as f:
                json.dump(current_blueprint, f, indent=4)
            logging.info(
                f"Blueprint after chunk {j+1} saved to: {os.path.abspath(refined_blueprint_filename)}"
            )
        else:
            logging.critical(
                f"Failed to get a valid JSON response for chunk {j+1}. Aborting."
            )
            return None

    logging.info("--- Blueprint refinement complete. ---")
    return current_blueprint


def generate_migration_blueprint(
    tool_context: ToolContext, user_feedback: str = ""
) -> dict:
    """
    Generates a migration blueprint JSON object from a consolidated CSV file.
    This tool performs the analysis and returns the blueprint in memory.
    """
    golden_record_path = tool_context.state.get("golden_record_path")
    config_path = tool_context.state.get("consolidation_config_path")

    if not golden_record_path:
        return {"error": "golden_record_path not found in tool_context state."}
    if not config_path:
        return {"error": "consolidation_config_path not found in tool_context state."}

    # This function returns a dictionary, not a JSON string.
    processed_csvs_dir = os.path.dirname(golden_record_path)
    debug_dir = os.path.join(processed_csvs_dir, "debug")
    os.makedirs(debug_dir, exist_ok=True)
    logging.info(f"Using debug directory: {debug_dir}")

    primary_key_column = "asset_name"
    logging.info(f"Using standard primary key: '{primary_key_column}'")

    try:
        df = pd.read_csv(golden_record_path, low_memory=False)
    except FileNotFoundError:
        error_msg = f"FATAL: Consolidated data file not found at '{golden_record_path}'. Aborting."
        logging.critical(error_msg)
        return error_msg

    if primary_key_column not in df.columns:
        error_msg = f"FATAL: The required primary key '{primary_key_column}' was not found in the columns of '{golden_record_path}'. Please ensure the data normalization step correctly creates an 'asset_name' column. Aborting."
        logging.critical(error_msg)
        return error_msg

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].fillna("")

    final_blueprint = create_blueprint_iteratively(
        df_input=df,
        config_path=config_path,
        debug_dir=debug_dir,
        primary_key_column=primary_key_column,
        user_feedback=user_feedback,
    )

    if not final_blueprint:
        error_msg = "FATAL: Failed to create the migration blueprint. Aborting."
        logging.critical(error_msg)
        # Return a dictionary with an error key
        return {"error": error_msg}

    # Store the newly generated/refined blueprint in the state for the next turn.
    tool_context.state["blueprint_json"] = final_blueprint

    logging.info("--- Blueprint generation complete. Returning blueprint object. ---")
    # Return the final blueprint dictionary directly.
    return final_blueprint


def save_blueprint(tool_context: ToolContext) -> str:
    """
    Saves the approved blueprint JSON to a file and constructs the final output payload.
    This tool should be called only after the user has approved the blueprint.
    """
    golden_record_path = tool_context.state.get("golden_record_path")
    blueprint_json = tool_context.state.get("blueprint_json")

    if not golden_record_path:
        return json.dumps(
            {"error": "golden_record_path not found in tool_context state."}
        )
    if not blueprint_json:
        return json.dumps({"error": "blueprint_json not found in tool_context state."})

    processed_csvs_dir = os.path.dirname(golden_record_path)
    debug_dir = os.path.join(processed_csvs_dir, "debug")
    os.makedirs(debug_dir, exist_ok=True)

    final_blueprint_path = os.path.join(debug_dir, "final_migration_blueprint.json")
    try:
        with open(final_blueprint_path, "w") as f:
            json.dump(blueprint_json, f, indent=4)
        logging.info(
            f"Approved blueprint saved to: {os.path.abspath(final_blueprint_path)}"
        )
    except Exception as e:
        return json.dumps({"error": f"Failed to save final blueprint. Error: {e}"})

    tool_context.state["blueprint_path"] = os.path.abspath(final_blueprint_path)

    output_payload = {
        "golden_record_path": os.path.abspath(golden_record_path),
        "blueprint_path": os.path.abspath(final_blueprint_path),
    }
    final_payload_str = json.dumps(output_payload, indent=2)
    logging.debug(f"Final payload from save_blueprint: {final_payload_str}")
    return final_payload_str


blueprint_generator_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="blueprint_generator_agent",
    description="An agent that analyzes consolidated data to create a strategic migration blueprint.",
    instruction="""You are the Migration Blueprint Architect. Your job is to generate a migration blueprint and work with the user until they approve it and save the approved blueprint.

**WORKFLOW:**

1. Call the `generate_migration_blueprint` tool to create an initial `migration_wave_plan`. Present this blueprint to the user for review in a markdown table format with 4 columns "Wave Name", "Objective", "Rationale", and "Priority".
2. you MUST ask user for feedback or approval. If user provides feedback, call `generate_migration_blueprint` again with the feedback as `user_feedback` parameter to refine the blueprint. Repeat this loop until the user approves the blueprint.
Stop calling the `generate_migration_blueprint` tool ONLY when the user mentions ("satisfied", "approved", "looks good") or something similar.
3. Once the user approves the config, call the `save_blueprint` tool.
4. Once the `save_blueprint` tool has finished, call the parent agent.
""",
    tools=[generate_migration_blueprint, save_blueprint],
)
