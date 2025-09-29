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
from . import utils

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
artifact_bucket = "insightwave-final-artifacts"


def _print_token_usage(response, call_description: str):
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


def _log_llm_error(
    debug_dir: str, prompt: str, error: Exception, call_description: str
):
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
        print(
            f"    ERROR: LLM call failed for '{call_description}'. Details logged to {os.path.abspath(log_file_path)}"
        )
    except Exception as log_e:
        print(f"    FATAL: Could not write to error log. Log Error: {log_e}")
        print(f"    Original Error: {error}")


def _generate_content_with_retry(
    prompt: str,
    call_description: str,
    debug_dir: str,
    max_retries: int = 5,
    delay: int = 10,
):
    """
    Calls model.generate_content with retry logic for transient service errors.
    Uses exponential backoff with jitter.
    Includes specific handling for 429 (resource exhaustion) and max_tokens errors.
    """
    response = None
    for attempt in range(max_retries):
        try:
            # The generation_config is defined here, including the Vertex-specific 'thinking_config'.
            # The safety_settings are passed as a separate argument. This resolves the validation error.
            current_generation_config = generation_config
            response = client.models.generate_content(
                model=MODEL, contents=prompt, config=current_generation_config
            )

            # Check for empty response which can happen with safety filters etc.
            if not response.candidates:
                error_message = "LLM response was empty (no candidates returned)."
                try:
                    # The prompt_feedback is on the top-level response object
                    block_reason = response.prompt_feedback.block_reason.name
                    safety_ratings = str(response.prompt_feedback.safety_ratings)
                    error_message += f" Block Reason: {block_reason}. Safety Ratings: {safety_ratings}"
                except (AttributeError, IndexError):
                    error_message += (
                        " No specific block reason found in prompt_feedback."
                    )

                raise ValueError(error_message)

            # Also check that the response actually contains text to parse.
            # The .text property is a shortcut that can fail or be None if the response is empty.
            try:
                if not response.text:
                    # This can happen if the model returns a response, but the content is empty.
                    # This is often related to a safety filter on the *output*, even if the prompt was OK.
                    finish_reason = "Unknown"
                    safety_ratings_str = "Not available"
                    try:
                        finish_reason = response.candidates[0].finish_reason.name
                        safety_ratings_str = str(response.candidates[0].safety_ratings)
                    except (AttributeError, IndexError):
                        pass  # Keep default values if we can't access details

                    error_message = (
                        "Model response was empty (contained no text). "
                        f"Finish Reason: {finish_reason}. Safety Ratings: {safety_ratings_str}"
                    )
                    raise ValueError(error_message)
            except (AttributeError, IndexError):
                # This case handles a malformed response object where .text can't even be accessed.
                raise ValueError(
                    "Could not extract text from a malformed model response candidate."
                )

            _print_token_usage(response, call_description)
            return response
        except exceptions.ServiceUnavailable as e:
            if attempt + 1 >= max_retries:
                print(
                    f"    ERROR: Max retries reached for '{call_description}'. Failing. Error: {e}"
                )
                _log_llm_error(debug_dir, prompt, e, call_description)
                raise e

            jitter = random.uniform(0, 5)
            backoff_delay = delay * (2**attempt) + jitter
            print(
                f"    WARNING: Service unavailable for '{call_description}' (Attempt {attempt + 1}/{max_retries}). Retrying in {backoff_delay:.2f}s..."
            )
            time.sleep(backoff_delay)
        except exceptions.ResourceExhausted as e:  # Catch 429 errors explicitly
            if attempt + 1 >= max_retries:
                print(
                    f"    ERROR: Max retries reached for '{call_description}' after resource exhaustion. Failing. Error: {e}"
                )
                _log_llm_error(debug_dir, prompt, e, call_description)
                raise e

            jitter = random.uniform(0, 5)
            backoff_delay = delay * (2**attempt) + jitter
            print(
                f"    WARNING: Resource exhausted for '{call_description}' (Attempt {attempt + 1}/{max_retries}). Retrying in {backoff_delay:.2f}s..."
            )
            time.sleep(backoff_delay)
        except ValueError as e:
            # Make the check case-insensitive to catch "MAX_TOKENS" finish reason.
            if (
                "max_tokens" in str(e).lower()
                or "maximum context length" in str(e).lower()
            ):
                if response:
                    _print_token_usage(
                        response, f"{call_description} (on MAX_TOKENS error)"
                    )

                if attempt + 1 >= max_retries:
                    print(
                        f"    ERROR: Max tokens reached for '{call_description}' after max retries.  Please decrease the size of the input data or increase token limit"
                    )
                    _log_llm_error(debug_dir, prompt, e, call_description)
                    raise e  # Re-raise the exception after max retries

                jitter = random.uniform(0, 5)
                backoff_delay = delay * (2**attempt) + jitter
                print(
                    f"    WARNING: Max tokens error encountered for '{call_description}' (Attempt {attempt + 1}/{max_retries}). Retrying in {backoff_delay:.2f}s..."
                )
                time.sleep(backoff_delay)
            else:
                # If it's a ValueError other than max_tokens, re-raise it immediately
                raise
        except Exception as e:
            _log_llm_error(debug_dir, prompt, e, call_description)
            raise e
    # This line is technically unreachable if the loop raises, but it's good practice for clarity.
    final_error = exceptions.ServiceUnavailable(
        f"Failed to get response for '{call_description}' after {max_retries} attempts."
    )
    _log_llm_error(debug_dir, prompt, final_error, call_description)
    raise final_error


def _parse_model_response(response):
    """
    Parses the JSON from a model's text response in a robust way.
    It extracts the JSON object even if it's surrounded by other text.
    """
    raw_text = response.text
    # Make JSON parsing more robust. The model can sometimes return extra text
    # or markdown formatting around the JSON object. This finds the first
    # opening brace and the last closing brace to isolate the JSON object.
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")

    if first_brace == -1 or last_brace == -1:
        raise json.JSONDecodeError(
            "No JSON object found in the model's response.", raw_text, 0
        )

    clean_json_text = raw_text[first_brace : last_brace + 1]
    return json.loads(clean_json_text)


def _merge_blueprint_changes(current_blueprint, changes):
    """
    Merges a 'diff' of changes into the current blueprint.
    Handles removals, additions, and modifications, then re-sorts.
    """
    if not isinstance(changes, dict):
        print(
            f"    WARNING: Refinement response is not a valid JSON object. Skipping refinement. Raw response: {changes}"
        )
        return current_blueprint

    # Handle wave removal first to prevent trying to modify a deleted wave.
    wave_names_to_remove = changes.get("wave_names_to_remove", [])
    if wave_names_to_remove:
        print(
            f"  Removing {len(wave_names_to_remove)} wave definition(s): {wave_names_to_remove}"
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
        print(f"  Adding {len(new_waves)} new wave definition(s).")
        if "wave_definitions" not in current_blueprint or not isinstance(
            current_blueprint.get("wave_definitions"), list
        ):
            current_blueprint["wave_definitions"] = []
        current_blueprint["wave_definitions"].extend(new_waves)

    # Handle modified waves
    modified_waves = changes.get("modified_wave_definitions", [])
    if modified_waves:
        print(f"  Modifying {len(modified_waves)} existing wave definition(s).")
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
                print(
                    f"  Warning: Model tried to modify a non-existent wave: '{wave_name_to_modify}'. Adding it as a new wave instead."
                )
                current_blueprint["wave_definitions"].append(modified_wave)

    # Re-sort waves by priority
    if new_waves or modified_waves or wave_names_to_remove:
        if "wave_definitions" in current_blueprint and isinstance(
            current_blueprint["wave_definitions"], list
        ):
            current_blueprint["wave_definitions"].sort(
                key=lambda x: x.get("priority", 999) if isinstance(x, dict) else 999
            )

    return current_blueprint


def assign_waves_with_sql(
    blueprint: dict, debug_dir: str, df_input: pd.DataFrame, primary_key_column: str
):
    """Assigns servers to waves by generating and executing SQL queries based on the blueprint."""
    print("\n--- Phase 2: Assigning Servers to Waves using SQL ---")
    df = df_input
    print("  Using provided DataFrame for assignments.")

    if "wave_definitions" not in blueprint or not blueprint["wave_definitions"]:
        print("FATAL: Blueprint contains no wave definitions.")
        return None

    all_server_assignments = {}
    assigned_servers = set()

    wave_defs = blueprint.get("wave_definitions", [])
    if not isinstance(wave_defs, list):
        print(
            f"  WARNING: 'wave_definitions' is not a list, it's a {type(wave_defs)}. Cannot assign waves."
        )
        return {}

    sorted_waves = sorted(
        wave_defs, key=lambda x: x.get("priority", 999) if isinstance(x, dict) else 999
    )

    for wave in sorted_waves:
        if not isinstance(wave, dict):
            print(f"  WARNING: Found a non-dictionary item in wave_definitions. Skipping. Item: {wave}")
            continue

        wave_name = wave.get("wave_name")
        query = wave.get("sql_query")
        if not wave_name or not query:
            print(f"    WARNING: Wave '{wave_name}' is missing a name or a SQL query. Skipping.")
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
            r'SELECT\s+.*?\s+FROM',
            f'SELECT {pk_for_sql} FROM',
            original_query,
            count=1,
            flags=re.IGNORECASE,
        )
        if query != original_query:
            print(f"    INFO: Standardizing query for wave '{wave_name}' to select the primary identifier.")

        print(f"  Processing '{wave_name}'...")
        try:
            print(f"    Executing query: {query}")
            # Execute the query, passing the DataFrame explicitly to avoid scope issues.
            result_df = sqldf(query, {"df": df})
            newly_assigned_count = 0
            for asset_name in result_df[primary_key_column]:
                if asset_name not in assigned_servers:
                    all_server_assignments[asset_name] = wave_name
                    assigned_servers.add(asset_name)
                    newly_assigned_count += 1
            print(
                f"    -> Matched {len(result_df)} servers. Assigned {newly_assigned_count} new servers."
            )
        except Exception as e:
            print(
                f"    ERROR: Could not execute query for wave '{wave_name}'. Error: {e}"
            )
            continue

    unassigned_servers = set(df[primary_key_column]) - assigned_servers
    for server in unassigned_servers:
        all_server_assignments[server] = "Residual VMs-Needs Review"
    print(f"  Assigned {len(unassigned_servers)} servers to 'Residual VMs-Needs Review'.")
    print("\n--- Server assignment complete. ---")
    return all_server_assignments


def validate_and_refine_wave_sizes(
    assignments: dict,
    blueprint: dict,
    df: pd.DataFrame,
    debug_dir: str,
    primary_key_column: str,
    min_wave_size: int = 5,
    max_wave_size: int = 150,
    max_refinement_loops: int = 3,
):
    """
    Iteratively validates wave sizes against min/max thresholds and refines the
    blueprint to correct them.
    """
    print("\n--- Phase 2.5: Starting Wave Size Validation and Refinement ---")
    print(f"  Min wave size: {min_wave_size}, Max wave size: {max_wave_size}")

    current_assignments = assignments
    current_blueprint = blueprint

    for i in range(max_refinement_loops):
        print(f"\n  Validation Loop #{i+1}/{max_refinement_loops}...")
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
            print(
                "  Validation complete! All wave sizes are within boundaries and unclassified count is low."
            )
            return current_assignments, current_blueprint

        # Prepare data for the prompt
        servers_by_wave = {}
        for server, wave_name in current_assignments.items():
            servers_by_wave.setdefault(wave_name, []).append(server)

        anomalous_waves_data = {}
        if waves_too_small:
            print(
                f"  Found {len(waves_too_small)} wave(s) smaller than min size: {list(waves_too_small.keys())}"
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
            print(
                f"  Found {len(waves_too_large)} wave(s) larger than max size: {list(waves_too_large.keys())}"
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
            print(f"  Found {unclassified_count} unclassified servers. Attempting to create new waves for them.")
            unclassified_server_list = servers_by_wave.get("Residual VMs-Needs Review", [])
            sample_size = min(len(unclassified_server_list), 200) # Sample up to 200
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
            print("  Sending request to LLM for wave size validation...")
            response = _generate_content_with_retry(
                validation_prompt, f"Wave Size Validation Loop {i+1}", debug_dir
            )
            changes = _parse_model_response(response)

            if not any(changes.values()):
                print("  Model returned no changes. Validation is considered complete.")
                return current_assignments, current_blueprint

            current_blueprint = _merge_blueprint_changes(current_blueprint, changes)
            validation_blueprint_filename = os.path.join(
                debug_dir, f"migration_blueprint_validated_loop_{i+1}.json"
            )
            with open(validation_blueprint_filename, "w") as f:
                json.dump(current_blueprint, f, indent=4)
            print(
                f"  Saved validated blueprint to: {os.path.abspath(validation_blueprint_filename)}"
            )

            print("  Re-assigning servers with the refined blueprint...")

            current_assignments = assign_waves_with_sql(
                blueprint=current_blueprint,
                debug_dir=debug_dir,
                df_input=df,
                primary_key_column=primary_key_column,
            )
            if not current_assignments:
                print("  FATAL: Re-assignment failed during validation loop. Aborting.")
                return assignments, blueprint

        except (json.JSONDecodeError, exceptions.ServiceUnavailable, Exception) as e:
            print(
                f"    ERROR: Error during validation loop {i+1}: {e}. Stopping refinement."
            )
            return current_assignments, current_blueprint

    print(
        "\n--- Max validation loops reached. Proceeding with current assignments. ---"
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
    print("  Cleaning final report: Removing empty waves and re-ordering priorities...")
    # Filter out waves that have no servers assigned
    non_empty_waves = {
        name: data for name, data in final_wave_definitions_dict.items() if data.get("wave_assignment")
    }

    # Sort the remaining waves by their original priority
    sorted_non_empty_waves = sorted(non_empty_waves.values(), key=lambda x: x.get("priority", 999))

    # Re-assign sequential priorities and build the final dictionary
    final_cleaned_wave_definitions = {}
    for i, wave_data in enumerate(sorted_non_empty_waves):
        wave_data["priority"] = i + 1
        # Find the original wave name to use as the key
        for name, original_data in non_empty_waves.items():
            if original_data is wave_data:
                final_cleaned_wave_definitions[name] = wave_data
                break

    final_report = {"summary": summary, "wave_definitions": final_cleaned_wave_definitions}
    with open(output_path, "w") as f:
        json.dump(final_report, f, indent=4)
    print(f"  Generated final migration wave plan: {os.path.abspath(output_path)}")


def assign_groups_and_generate_plan(tool_context: ToolContext) -> str:
    """
    Orchestrates assigning servers to waves based on a blueprint, refining the waves,
    and generating the final migration plan artifacts.
    """
    golden_record_path = tool_context.state.get("golden_record_path")
    blueprint_path = tool_context.state.get("blueprint_path")

    if not golden_record_path:
        return json.dumps({"error": "golden_record_path not found in tool_context state."})
    if not blueprint_path:
        return json.dumps({"error": "blueprint_path not found in tool_context state."})

    processed_csvs_dir = os.path.dirname(golden_record_path)

    try:
        with open(blueprint_path, 'r') as f:
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
    print(
        f"  Dynamically calculated wave sizes: min={min_wave_size}, max={max_wave_size}"
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

    print("\n--- Phase 3: Saving Artifacts and Generating Summary ---")
    if "wave_definitions" in final_blueprint and isinstance(
        final_blueprint.get("wave_definitions"), list
    ):
        valid_wave_defs = [
            w for w in final_blueprint["wave_definitions"] if isinstance(w, dict)
        ]
        sorted_wave_defs = sorted(valid_wave_defs, key=lambda x: x.get("priority", 999))
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
    _create_summary_report(final_blueprint, final_assignments, final_report_path, df, primary_key_column)

    # Set the new artifact path in the tool_context state for the next agent
    tool_context.state["wave_plan_path"] = os.path.abspath(final_report_path)

    # --- Inject blueprint data into dashboard.html ---
    template_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
    dashboard_html_path = os.path.join(template_dir, "dashboard.html")
    output_dashboard_path = None
    if os.path.exists(dashboard_html_path):
        print(f"  Found dashboard.html. Injecting data using placeholder method...")
        try:
            with open(dashboard_html_path, 'r', encoding='utf-8') as f:
                dashboard_content = f.read()

            # The final_blueprint object is already in memory
            blueprint_json_string = json.dumps(final_blueprint)

            # Define the placeholder. It should be a string literal in the JS file.
            # e.g., const migrationBlueprint = "__MIGRATION_BLUEPRINT_PLACEHOLDER__";
            placeholder = '"__MIGRATION_BLUEPRINT_PLACEHOLDER__"'

            # Replace the placeholder with the actual JSON data.
            # This is more robust and elegant than a broad regex.
            modified_content = dashboard_content.replace(placeholder, blueprint_json_string)

            output_dashboard_path = os.path.join(processed_csvs_dir, "wave_plan_dashboard.html")

            if modified_content != dashboard_content:
                with open(output_dashboard_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                print(f"    Successfully injected data into {output_dashboard_path}")
            else:
                print(f"    WARNING: Could not find placeholder '{placeholder}' in {dashboard_html_path}. Dashboard will not be updated.")
                print(f"    Please ensure the dashboard.html file contains a line like: const migrationBlueprint = {placeholder};")
        except Exception as e:
            print(f"    ERROR: Failed to inject data into dashboard.html. Error: {e}")


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
    print(summary_text)

    # Create a structured JSON output for the next agent
    output_payload = {
        "message": "Successfully generated migration wave plan.",
        "artifacts": {
            "golden_record_path": os.path.abspath(golden_record_path),
            "blueprint_path": os.path.abspath(final_blueprint_path),
            "wave_plan_path": os.path.abspath(final_report_path),
        },
    }

    try:
        utils.upload_to_gcs(
            artifact_bucket,
            os.path.abspath(final_report_path),
            f"waveplan/{os.path.basename(final_report_path)}",
        )
        output_payload["artifacts"][
            "wave_plan_gcs_path"
        ] = f"https://storage.cloud.google.com/{artifact_bucket}/waveplan/{os.path.basename(final_report_path)}?authuser=1"
        print(f"View generated wave plan at: [{output_payload['artifacts']['wave_plan_gcs_path']}]({output_payload['artifacts']['wave_plan_gcs_path']})")
    except Exception as e:
        print(e)
        output_payload["artifacts"]["wave_plan_gcs_path"] = f"Failed to upload: {e}"

    # Upload the dashboard to GCS
    if output_dashboard_path and os.path.exists(output_dashboard_path):
        try:
            dashboard_gcs_path = f'dashboards/{os.path.basename(output_dashboard_path)}'
            utils.upload_to_gcs(artifact_bucket, os.path.abspath(output_dashboard_path), dashboard_gcs_path)
            dashboard_url = f'https://storage.cloud.google.com/{artifact_bucket}/{dashboard_gcs_path}?authuser=1'
            print(f'View generated dashboard at: [{dashboard_url}]({dashboard_url})')
            output_payload["artifacts"]["dashboard_gcs_path"] = dashboard_url
        except Exception as e:
            print(f"    ERROR: Failed to upload dashboard to GCS. Error: {e}")
            output_payload["artifacts"]["dashboard_gcs_path"] = f"Failed to upload: {e}"

    final_output_string = json.dumps(output_payload, indent=2)
    print(final_output_string)
    return final_output_string


group_assignment_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="group_assignment_agent",
    description="Assigns servers to waves based on an approved blueprint, refines wave sizes, and generates the final migration plan.",
    instruction="""
You are a migration wave assignment specialist. Your purpose is to take an approved migration blueprint and a golden record of server data to produce a final, validated wave plan and present the results to the user.

**YOUR TASK:**
1.  You MUST call the `assign_groups_and_generate_plan` tool.
2.  You MUST parse the JSON string returned by the tool to extract the GCS links for the `wave_plan_gcs_path` and the `dashboard_gcs_path`.
3.  Then You MUST respond with a user-friendly message in markdown that presents the GCS links.

For example:
    "The migration plan has been successfully generated.
    You can view the full artifacts here:
    - **Migration Wave Plan**: View Plan
    - **Interactive Dashboard**: View Dashboard"
""",
    tools=[assign_groups_and_generate_plan],
)