from google import genai
from google.genai.types import (
    HarmCategory,
    HarmBlockThreshold,
    GenerateContentConfig,
    SafetySetting,
    ThinkingConfig,
)
from google.adk.tools import ToolContext
from google.api_core import exceptions
from google.adk.agents import LlmAgent
import pandas as pd
import json
import os
import time
import math
import re
import random
from pandasql import sqldf
import logging
from . import utils

# Configure logging
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
artifact_bucket = os.environ.get(
    "INSIGHTWAVE_ARTIFACT_BUCKET", "insightwave-final-artifacts"
)


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

    # Handle wave removal first to prevent trying to modify a deleted wave.
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

    # Handle new waves
    new_waves = changes.get("new_wave_definitions", [])
    if new_waves:
        logging.info(f"Adding {len(new_waves)} new wave definition(s).")
        if "wave_definitions" not in current_blueprint or not isinstance(
            current_blueprint.get("wave_definitions"), list
        ):
            current_blueprint["wave_definitions"] = []
        current_blueprint["wave_definitions"].extend(new_waves)

    # Handle modified waves
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

    # Re-sort waves by priority
    if new_waves or modified_waves or wave_names_to_remove:
        if "wave_definitions" in current_blueprint and isinstance(
            current_blueprint["wave_definitions"], list
        ):
            current_blueprint["wave_definitions"].sort(
                key=lambda x: (
                    int(x.get("priority", 999)) if isinstance(x, dict) else 999
                )
            )

    return current_blueprint


def assign_waves_with_sql(
    blueprint: dict, debug_dir: str, df_input: pd.DataFrame, primary_key_column: str
):
    """Assigns servers to waves by generating and executing SQL queries based on the blueprint."""
    logging.info("--- Phase 2: Assigning Servers to Waves using SQL ---")
    df = df_input
    logging.info("Using provided DataFrame for assignments.")

    if "wave_definitions" not in blueprint or not blueprint["wave_definitions"]:
        logging.critical("Blueprint contains no wave definitions.")
        return None

    all_server_assignments = {}
    assigned_servers = set()

    wave_defs = blueprint.get("wave_definitions", [])
    if not isinstance(wave_defs, list):
        logging.warning(
            f"'wave_definitions' is not a list, it's a {type(wave_defs)}. Cannot assign waves."
        )
        return {}

    sorted_waves = sorted(
        wave_defs, key=lambda x: x.get("priority", 999) if isinstance(x, dict) else 999
    )

    for wave in sorted_waves:
        if not isinstance(wave, dict):
            logging.warning(
                f"Found a non-dictionary item in wave_definitions. Skipping. Item: {wave}"
            )
            continue

        wave_name = wave.get("wave_name")
        query = wave.get("sql_query")
        if not wave_name or not query:
            logging.warning(
                f"Wave '{wave_name}' is missing a name or a SQL query. Skipping."
            )
            continue

        # --- ROBUST GUARDRAIL ---
        # Programmatically enforce the selection of the primary identifier column ("asset_name").
        # This is more resilient than checking for specific incorrect column names, as the LLM
        # could hallucinate any column. This regex replaces whatever the LLM put
        # between SELECT and FROM with the correct column name.
        pk_for_sql = f'"{primary_key_column}"'
        original_query = query
        # Use re.IGNORECASE for 'select' vs 'SELECT' and count=1 for subqueries.
        query = re.sub(
            r"SELECT\s+.*?\s+FROM",
            f"SELECT {pk_for_sql} FROM",
            original_query,
            count=1,
            flags=re.IGNORECASE,
        )
        if query != original_query:
            logging.info(
                f"Standardizing query for wave '{wave_name}' to select the primary identifier."
            )

        logging.info(f"Processing '{wave_name}'...")
        try:
            logging.info(f"  Executing query: {query}")
            # Execute the query, passing the DataFrame explicitly to avoid scope issues.
            result_df = sqldf(query, {"df": df})
            newly_assigned_count = 0
            for asset_name in result_df[primary_key_column]:
                if asset_name not in assigned_servers:
                    all_server_assignments[asset_name] = wave_name
                    assigned_servers.add(asset_name)
                    newly_assigned_count += 1
            logging.info(
                f"  -> Matched {len(result_df)} servers. Assigned {newly_assigned_count} new servers."
            )
        except Exception as e:
            logging.error(f"Could not execute query for wave '{wave_name}'. Error: {e}")
            continue

    unassigned_servers = set(df[primary_key_column]) - assigned_servers
    for server in unassigned_servers:
        all_server_assignments[server] = "Residual VMs-Needs Review"
    logging.info(
        f"Assigned {len(unassigned_servers)} servers to 'Residual VMs-Needs Review'."
    )
    logging.info("--- Server assignment complete. ---")
    return all_server_assignments


def validate_and_refine_wave_sizes(
    assignments: dict,
    blueprint: dict,
    df: pd.DataFrame,
    debug_dir: str,
    primary_key_column: str,
    min_wave_size: int = 5,
    max_wave_size: int = 150,
    max_refinement_loops: int = 1,
):
    """
    Iteratively validates wave sizes against min/max thresholds and refines the
    blueprint to correct them.
    """
    logging.info("--- Phase 2.5: Starting Wave Size Validation and Refinement ---")
    logging.info(f"Min wave size: {min_wave_size}, Max wave size: {max_wave_size}")

    current_assignments = assignments
    current_blueprint = blueprint

    for i in range(max_refinement_loops):
        logging.info(f"Validation Loop #{i+1}/{max_refinement_loops}...")
        wave_counts = pd.Series(current_assignments).value_counts().to_dict()

        waves_too_small = {
            w: c
            for w, c in wave_counts.items()
            if c < min_wave_size and w != "Residual VMs-Needs Review"
        }
        waves_too_large = {w: c for w, c in wave_counts.items() if c > max_wave_size}

        # Check for a large number of unclassified servers.
        # If the number of unclassified servers is larger than a small wave, it's worth analyzing.
        unclassified_count = wave_counts.get("Residual VMs-Needs Review", 0)
        handle_unclassified = unclassified_count > min_wave_size

        if not waves_too_small and not waves_too_large and not handle_unclassified:
            logging.info(
                "Validation complete! All wave sizes are within boundaries and unclassified count is low."
            )
            return current_assignments, current_blueprint

        # Prepare data for the prompt
        servers_by_wave = {}
        for server, wave_name in current_assignments.items():
            servers_by_wave.setdefault(wave_name, []).append(server)

        anomalous_waves_data = {}
        if waves_too_small:
            logging.info(
                f"Found {len(waves_too_small)} wave(s) smaller than min size: {list(waves_too_small.keys())}"
            )
            for wave_name in waves_too_small:
                server_list = servers_by_wave.get(wave_name, [])
                anomalous_waves_data[wave_name] = {
                    "issue": "too_small",
                    "server_count": len(server_list),
                    "servers": df[df[primary_key_column].isin(server_list)].to_dict(
                        "records"
                    ),
                }

        if waves_too_large:
            logging.info(
                f"Found {len(waves_too_large)} wave(s) larger than max size: {list(waves_too_large.keys())}"
            )
            for wave_name in waves_too_large:
                server_list = servers_by_wave.get(wave_name, [])
                sample_size = min(len(server_list), 200)
                server_sample = (
                    df[df[primary_key_column].isin(server_list)]
                    .sample(n=sample_size, random_state=42)
                    .to_dict("records")
                )
                anomalous_waves_data[wave_name] = {
                    "issue": "too_large",
                    "server_count": len(server_list),
                    "servers_sample": server_sample,
                }

        if handle_unclassified:
            logging.info(
                f"Found {unclassified_count} unclassified servers. Attempting to create new waves for them."
            )
            unclassified_server_list = servers_by_wave.get(
                "Residual VMs-Needs Review", []
            )
            sample_size = min(len(unclassified_server_list), 200)  # Sample up to 200
            server_sample = (
                df[df[primary_key_column].isin(unclassified_server_list)]
                .sample(n=sample_size, random_state=42)
                .to_dict("records")
            )
            anomalous_waves_data["unclassified_servers"] = {
                "issue": "unclassified",
                "server_count": unclassified_count,
                "servers_sample": server_sample,
            }

        validation_prompt = f"""You are a master migration wave planner. Your task is to refine a "Migration Blueprint" to fix waves that are either too small, too large, or to classify servers that are currently unassigned.

        **Your Goal:**
        Analyze the `Anomalous Waves` and the `Current Blueprint`. Modify the blueprint to resolve these issues by merging small waves, splitting large ones, or creating new waves for unclassified servers.

        **Instructions (in order of priority):**
        1.  **Analyze `unclassified_servers` (Highest Priority):**
            *   If the `unclassified_servers` key exists, this is your most important task.
            *   Analyze the `servers_sample` to find common, logical patterns (e.g., by `guest_os`, `app_name`, `cluster_name`, etc.).
            *   Create NEW, specific wave definitions to group these servers. Your goal is to reduce the number of unclassified servers significantly. Add these to the `new_wave_definitions` list in your response.

        2.  **Analyze Waves Marked `too_large`:**
            *   Examine their server sample. Can you find a logical sub-pattern to split the wave?
            *   Create new, more specific wave definitions to break down the large group. Add these to `new_wave_definitions` and list the original large wave in `wave_names_to_remove`.

        3.  **Analyze Waves Marked `too_small`:**
            *   Examine their servers. Can they be logically merged into another existing wave?
            *   If so, modify the target wave's criteria to include them (add to `modified_wave_definitions`) and list the small wave in `wave_names_to_remove`.

        4.  **CRITICAL: Prioritize Logical Grouping.**
            *   Do not just create arbitrary splits or merges. The new or modified waves MUST be based on a logical, data-driven pattern.
            *   If you cannot find a logical way to merge a small wave or split a large one, reassess such waves again through the ruleset and business logic and assign wave groups as appropriate. return the changes "new_wave_definitons", "modified_wave_definitions", and "wave_names_to_remove".


        5.  **Return ONLY the Changes:** Your output MUST be a JSON object containing any of the following keys: "new_wave_definitions", "modified_wave_definitions", and "wave_names_to_remove".
            *   If you merge a small wave into another, you should have a `modified_wave_definitions` entry for the target wave and a `wave_names_to_remove` entry for the small wave.
            *   If you split a large wave, you should have a `new_wave_definitions` list with the new, smaller waves, and a `wave_names_to_remove` entry for the original large wave.
            *   For any new or modified wave, you MUST include the `objective`, `rationale`, `criteria` object, and the corresponding `sql_query` string that selects the `{primary_key_column}`. The `wave_name` MUST be a descriptive, unique name for the group. Do NOT add prefixes like "Wave 1:" or "Group A:".

        **Wave Size Boundaries:**
        - Minimum Wave Size: {min_wave_size}
        - Maximum Wave Size: {max_wave_size}

        **Current Blueprint:**
        {json.dumps(current_blueprint, indent=2)}

        **Anomalous Waves (to be fixed):**
        {json.dumps(anomalous_waves_data, indent=2)}
        """

        try:
            logging.info("Sending request to LLM for wave size validation...")
            response = utils.generate_content_with_retry(
                validation_prompt, f"Wave Size Validation Loop {i+1}", debug_dir
            )
            changes = utils.parse_model_response(response)

            if not any(changes.values()):
                logging.info(
                    "Model returned no changes. Validation is considered complete."
                )
                return current_assignments, current_blueprint

            current_blueprint = _merge_blueprint_changes(current_blueprint, changes)
            validation_blueprint_filename = os.path.join(
                debug_dir, f"migration_blueprint_validated_loop_{i+1}.json"
            )
            with open(validation_blueprint_filename, "w") as f:
                json.dump(current_blueprint, f, indent=4)
            logging.info(
                f"Saved validated blueprint to: {os.path.abspath(validation_blueprint_filename)}"
            )

            logging.info("Re-assigning servers with the refined blueprint...")

            current_assignments = assign_waves_with_sql(
                blueprint=current_blueprint,
                debug_dir=debug_dir,
                df_input=df,
                primary_key_column=primary_key_column,
            )
            if not current_assignments:
                logging.critical(
                    "Re-assignment failed during validation loop. Aborting."
                )
                return assignments, blueprint

        except (json.JSONDecodeError, exceptions.ServiceUnavailable, Exception) as e:
            logging.error(
                f"Error during validation loop {i+1}: {e}. Stopping refinement."
            )
            return current_assignments, current_blueprint

    logging.info(
        "--- Max validation loops reached. Proceeding with current assignments. ---"
    )
    return current_assignments, current_blueprint


def _create_summary_report(
    blueprint: dict,
    assignments: dict,
    output_path: str,
    df: pd.DataFrame,
    primary_key_column: str,
):
    """Generates a final JSON report."""
    asset_name_column = "asset_name"
    if (
        primary_key_column != asset_name_column
        and primary_key_column in df.columns
        and asset_name_column in df.columns
    ):
        id_to_name_map = (
            df.drop_duplicates(subset=[primary_key_column])
            .set_index(primary_key_column)[asset_name_column]
            .to_dict()
        )
        assignments = {
            id_to_name_map.get(server_id, server_id): wave
            for server_id, wave in assignments.items()
        }

    wave_defs = blueprint.get("wave_definitions", [])
    if not isinstance(wave_defs, list):
        return

    servers_by_wave = {}
    for server, wave_name in assignments.items():
        servers_by_wave.setdefault(wave_name, []).append(server)

    final_wave_definitions_dict = {}
    for wave_def in wave_defs:
        if not isinstance(wave_def, dict):
            continue
        wave_name = wave_def.get("wave_name")
        if not wave_name:
            continue
        final_wave_definitions_dict[wave_name] = {
            "priority": wave_def.get("priority"),
            "objective": wave_def.get("objective", "N/A"),
            "rationale": wave_def.get("rationale", "N/A"),
            "wave_assignment": sorted(servers_by_wave.get(wave_name, [])),
        }

    if "Residual VMs-Needs Review" in servers_by_wave:
        max_priority = max(
            [
                d.get("priority")
                for d in final_wave_definitions_dict.values()
                if d.get("priority") is not None
            ]
            or [0]
        )
        final_wave_definitions_dict["Residual VMs-Needs Review"] = {
            "priority": max_priority + 1,
            "objective": "Migrate servers that did not match any defined wave criteria.",
            "rationale": "These servers are grouped here for review and manual assignment.",
            "wave_assignment": sorted(
                servers_by_wave.get("Residual VMs-Needs Review", [])
            ),
        }

    wave_counts = {
        name: len(data["wave_assignment"])
        for name, data in final_wave_definitions_dict.items()
    }
    summary = {
        "total_servers_migrating": sum(wave_counts.values()),
        "total_waves": len(
            [w for w in wave_counts if w != "Residual VMs-Needs Review"]
        ),
        "servers_per_wave": {k: v for k, v in sorted(wave_counts.items())},
    }

    # --- Final Cleanup: Remove empty waves and re-order priorities ---
    logging.info(
        "Cleaning final report: Removing empty waves and re-ordering priorities..."
    )
    # Filter out waves that have no servers assigned
    non_empty_waves = {
        name: data
        for name, data in final_wave_definitions_dict.items()
        if data.get("wave_assignment")
    }

    # Sort the remaining waves by their original priority
    sorted_non_empty_waves = sorted(
        non_empty_waves.values(), key=lambda x: x.get("priority", 999)
    )

    # Re-assign sequential priorities and build the final dictionary
    final_cleaned_wave_definitions = {}
    for i, wave_data in enumerate(sorted_non_empty_waves):
        wave_data["priority"] = i + 1
        # Find the original wave name to use as the key
        for name, original_data in non_empty_waves.items():
            if original_data is wave_data:
                final_cleaned_wave_definitions[name] = wave_data
                break

    final_report = {
        "summary": summary,
        "wave_definitions": final_cleaned_wave_definitions,
    }
    with open(output_path, "w") as f:
        json.dump(final_report, f, indent=4)
    logging.info(f"Generated final migration wave plan: {os.path.abspath(output_path)}")


def assign_groups_and_generate_plan(tool_context: ToolContext) -> str:
    """
    Orchestrates assigning servers to waves based on a blueprint, refining the waves,
    and generating the final migration plan artifacts.
    """
    golden_record_path = tool_context.state.get("golden_record_path")
    blueprint_path = tool_context.state.get("blueprint_path")

    if not golden_record_path:
        return json.dumps(
            {"error": "golden_record_path not found in tool_context state."}
        )
    if not blueprint_path:
        return json.dumps({"error": "blueprint_path not found in tool_context state."})

    processed_csvs_dir = os.path.dirname(golden_record_path)

    try:
        with open(blueprint_path, "r") as f:
            blueprint = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return f"FATAL: Could not load or parse the blueprint file at '{blueprint_path}'. Error: {e}"

    debug_dir = os.path.join(processed_csvs_dir, "debug")
    os.makedirs(debug_dir, exist_ok=True)
    primary_key_column = "asset_name"

    try:
        df = pd.read_csv(golden_record_path, low_memory=False)
    except FileNotFoundError:
        return f"FATAL: Golden record file not found at '{golden_record_path}'."

    if primary_key_column not in df.columns:
        return (
            f"FATAL: Primary key '{primary_key_column}' not in '{golden_record_path}'."
        )

    for col in df.select_dtypes(include=["object"]).columns:
        df[col] = df[col].fillna("")

    initial_assignments = assign_waves_with_sql(
        blueprint=blueprint,
        debug_dir=debug_dir,
        df_input=df,
        primary_key_column=primary_key_column,
    )
    if not initial_assignments:
        return "FATAL: Failed to assign servers to waves initially."

    total_vms = len(df)
    min_wave_size = int(math.ceil(total_vms * 0.02))
    max_wave_size = (
        int(math.ceil(max(35.15 * math.log(total_vms) - 112.14, min_wave_size)))
        if total_vms > 0
        else 0
    )
    logging.info(
        f"Dynamically calculated wave sizes: min={min_wave_size}, max={max_wave_size}"
    )

    final_assignments, final_blueprint = validate_and_refine_wave_sizes(
        assignments=initial_assignments,
        blueprint=blueprint,
        df=df,
        debug_dir=debug_dir,
        min_wave_size=min_wave_size,
        max_wave_size=max_wave_size,
        primary_key_column=primary_key_column,
    )

    logging.info("--- Phase 3: Saving Artifacts and Generating Summary ---")
    if "wave_definitions" in final_blueprint and isinstance(
        final_blueprint.get("wave_definitions"), list
    ):
        valid_wave_defs = [
            w for w in final_blueprint["wave_definitions"] if isinstance(w, dict)
        ]
        sorted_wave_defs = sorted(
            valid_wave_defs, key=lambda x: int(x.get("priority", 999))
        )
        for i, wave_def in enumerate(sorted_wave_defs):
            wave_def["priority"] = i + 1
        final_blueprint["wave_definitions"] = sorted_wave_defs

    wave_counts = pd.Series(final_assignments).value_counts().to_dict()
    if "wave_definitions" in final_blueprint and isinstance(
        final_blueprint.get("wave_definitions"), list
    ):
        for wave_def in final_blueprint["wave_definitions"]:
            if isinstance(wave_def, dict) and "wave_name" in wave_def:
                wave_def["vm_count"] = wave_counts.get(wave_def["wave_name"], 0)

    final_blueprint_path = os.path.join(debug_dir, "final_migration_blueprint.json")
    with open(final_blueprint_path, "w") as f:
        json.dump(final_blueprint, f, indent=4)

    final_report_path = os.path.join(debug_dir, "final_migration_wave_plan.json")
    final_csv_path = os.path.join(debug_dir, "final_migration_wave_plan.csv")
    _create_summary_report(
        final_blueprint, final_assignments, final_report_path, df, primary_key_column
    )
    utils.convert_migration_plan_to_csv(final_report_path, final_csv_path)

    # Set the new artifact path in the tool_context state for the next agent
    tool_context.state["wave_plan_path"] = os.path.abspath(final_report_path)

    # --- Inject blueprint data into dashboard.html ---
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    dashboard_html_path = os.path.join(template_dir, "dashboard.html")
    output_dashboard_path = None
    if os.path.exists(dashboard_html_path):
        logging.info("Found dashboard.html. Injecting data using placeholder method...")
        try:
            with open(dashboard_html_path, "r", encoding="utf-8") as f:
                dashboard_content = f.read()

            # The final_blueprint object is already in memory
            blueprint_json_string = json.dumps(final_blueprint)

            # Define the placeholder. It should be a string literal in the JS file.
            # e.g., const migrationBlueprint = "__MIGRATION_BLUEPRINT_PLACEHOLDER__";
            placeholder = '"__MIGRATION_BLUEPRINT_PLACEHOLDER__"'

            # Replace the placeholder with the actual JSON data.
            # This is more robust and elegant than a broad regex.
            modified_content = dashboard_content.replace(
                placeholder, blueprint_json_string
            )

            output_dashboard_path = os.path.join(
                processed_csvs_dir, "wave_plan_dashboard.html"
            )

            if modified_content != dashboard_content:
                with open(output_dashboard_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)
                logging.info(f"Successfully injected data into {output_dashboard_path}")
            else:
                logging.warning(
                    f"Could not find placeholder '{placeholder}' in {dashboard_html_path}. Dashboard will not be updated."
                )
                logging.warning(
                    f"Please ensure the dashboard.html file contains a line like: const migrationBlueprint = {placeholder};"
                )
        except Exception as e:
            logging.error(f"Failed to inject data into dashboard.html. Error: {e}")

    # Create a human-readable summary message for the console
    total_assigned = sum(wave_counts.values())
    summary_lines = ["\nMigration Wave Plan Summary:"]
    summary_lines.append(f"- Total Servers Processed: {total_assigned}")
    summary_lines.append(f"- Final Wave Count: {len(wave_counts)}")
    if wave_counts:
        summary_lines.append("  Server Counts per Wave:")
        for wave_name, server_count in sorted(wave_counts.items()):
            summary_lines.append(f"    - {wave_name}: {server_count} servers")
    summary_text = "\n".join(summary_lines)
    logging.info(summary_text)

    # Create a structured JSON output for the next agent
    output_payload = {
        "message": "Successfully generated migration wave plan.",
        "artifacts": {
            "golden_record_path": os.path.abspath(golden_record_path),
            "blueprint_path": os.path.abspath(final_blueprint_path),
            "wave_plan_path": os.path.abspath(final_report_path),
            "wave_plan_csv": os.path.abspath(final_csv_path),
        },
    }

    try:
        wave_plan_gcs_path = f"waveplan/{os.path.basename(final_report_path)}"
        utils.upload_to_gcs(
            artifact_bucket, os.path.abspath(final_report_path), wave_plan_gcs_path
        )
        wave_plan_url = utils.generate_signed_url(
            artifact_bucket, wave_plan_gcs_path, expiration_minutes=60
        )
        output_payload["artifacts"]["wave_plan_gcs_path"] = wave_plan_url
        logging.info(f"View generated wave plan at: [{wave_plan_url}]({wave_plan_url})")
    except Exception as e:
        logging.error(e)
        output_payload["artifacts"]["wave_plan_gcs_path"] = f"Failed to upload: {e}"

    try:
        csv_gcs_path = f"waveplan/{os.path.basename(final_csv_path)}"
        utils.upload_to_gcs(
            artifact_bucket, os.path.abspath(final_csv_path), csv_gcs_path
        )
        csv_url = utils.generate_signed_url(
            artifact_bucket, csv_gcs_path, expiration_minutes=60
        )
        output_payload["artifacts"]["wave_plan_csv_gcs_path"] = csv_url
        logging.info(f"View generated wave plan CSV at: [{csv_url}]({csv_url})")
    except Exception as e:
        logging.error(f"Failed to upload wave plan CSV to GCS. Error: {e}")
        output_payload["artifacts"]["wave_plan_csv_gcs_path"] = f"Failed to upload: {e}"

    # Upload the dashboard to GCS
    if output_dashboard_path and os.path.exists(output_dashboard_path):
        try:
            dashboard_gcs_path = f"dashboards/{os.path.basename(output_dashboard_path)}"
            utils.upload_to_gcs(
                artifact_bucket,
                os.path.abspath(output_dashboard_path),
                dashboard_gcs_path,
            )
            dashboard_url = utils.generate_signed_url(
                artifact_bucket, dashboard_gcs_path, expiration_minutes=60
            )
            logging.info(
                f"View generated dashboard at: [{dashboard_url}]({dashboard_url})"
            )
            output_payload["artifacts"]["dashboard_gcs_path"] = dashboard_url
        except Exception as e:
            logging.error(f"Failed to upload dashboard to GCS. Error: {e}")
            output_payload["artifacts"]["dashboard_gcs_path"] = f"Failed to upload: {e}"

    final_output_string = json.dumps(output_payload, indent=2)
    logging.debug(f"Final output payload for next agent: {final_output_string}")
    return final_output_string


group_assignment_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="group_assignment_agent",
    description="Assigns servers to waves based on an approved blueprint, refines wave sizes, and generates the final migration plan.",
    instruction="""
You are a migration wave assignment specialist. Your purpose is to take an approved migration blueprint and a golden record of server data to produce a final, validated wave plan and present the results to the user.

**YOUR TASK:**
1.  You MUST call the `assign_groups_and_generate_plan` tool.
2.  You MUST parse the JSON string returned by the tool to extract the GCS links for the `wave_plan_gcs_path`, `wave_plan_csv_gcs_path` and the `dashboard_gcs_path`.
3.  Then You MUST respond with a user-friendly message in markdown that presents the GCS links as hyperlinks to the user.

For example:
    "The migration plan has been successfully generated.
    You can view the full artifacts here:
    - **Migration Wave Plan JSON**: View JSON Plan
    - ** Migration Wave Plan CSV**: View CSV
    - **Interactive Dashboard**: View Dashboard"
""",
    tools=[assign_groups_and_generate_plan],
)
