from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
import pandas as pd
import os
import glob
import json
import datetime
from google.cloud import storage
from . import utils

def inspect_and_load_data_context(tool_context: ToolContext ) -> str:
    """
    Inspects a directory for CSV files and returns a JSON string containing the schema (columns) for each file.
    """
    directory_path = tool_context.state.get('directory_path', '')
    if not os.path.isdir(directory_path):
        return json.dumps({"error": f"Directory not found at '{directory_path}'"})

    schema = {}
    search_pattern = os.path.join(directory_path, "*.csv")
    csv_files = glob.glob(search_pattern)

    if not csv_files:
        return json.dumps({"error": f"No CSV files found in directory '{directory_path}'"})

    for file_path in csv_files:
        filename = os.path.basename(file_path)
        try:
            df_header = pd.read_csv(file_path, nrows=0)
            schema[filename] = list(df_header.columns)
        except Exception as e:
            print(
                f"Warning: Could not read headers from {filename}. Skipping. Error: {e}"
            )
            continue

    return json.dumps({"data_schema": schema})
    
def generate_and_save_consolidated_csv(tool_context: ToolContext) -> str:
    """
    Consolidates multiple CSV files into a single golden record using a master index merge strategy.
    This ensures all unique assets are included without data loss from join operations.
    """
    
    directory_path = tool_context.state.get('directory_path')
    if not directory_path or not os.path.isdir(directory_path):
        return json.dumps({"error": f"Directory path not found or invalid in tool_context state."})

    consolidation_config = tool_context.state.get('consolidation_config')
    if not consolidation_config:
        return json.dumps({"error": "consolidation_config not found in tool_context state."})

    consolidation_config_path = os.path.join(directory_path, "consolidation_config.json")
    try:
        with open(consolidation_config_path, "w") as f:
            json.dump(consolidation_config, f, indent=2)
        print(f"Configuration saved to: {os.path.abspath(consolidation_config_path)}")
        # Set the paths in the tool_context state for the next agent
        tool_context.state["consolidation_config_path"] = consolidation_config_path
        tool_context.state["directory_path"] = directory_path
    except Exception as e:
        return json.dumps({"error": f"Could not save configuration file. {e}"})
    

    if not directory_path:
        return json.dumps({"error": "directory_path not found in tool_context state. Cannot proceed."})
    if not consolidation_config_path:
        return json.dumps({"error": "consolidation_config_path not found in tool_context state. Cannot proceed."})

    try:
        with open(consolidation_config_path, 'r') as f:
            consolidation_config = json.load(f)
        print(f"Loaded configuration from: {os.path.abspath(consolidation_config_path)}")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return f"Error: Could not load or parse configuration file at {consolidation_config_path}. {e}"
    
    try:    
        all_files_config = [consolidation_config['base_file']] + consolidation_config.get('files_to_merge', [])
        all_dataframes = {}
        master_key_set = set()
        standardized_master_key = "asset_name" # The target name for our primary key

        # --- Step 1: Pre-load and Standardize All DataFrames ---
        # Read each file, apply its specific renames, and collect all unique primary keys.
        print("--- Phase 1: Pre-loading and Standardizing DataFrames ---")
        for file_config in all_files_config:
            file_path = os.path.join(directory_path, file_config['filename'])
            if not os.path.exists(file_path):
                print(f"Warning: File '{file_config['filename']}' not found. Skipping.")
                continue

            original_key = file_config['key']
            columns_to_keep = [item['column_name'] for item in file_config.get('columns_to_keep', [])]
            
            # Ensure the original key is in the list of columns to read
            if original_key not in columns_to_keep:
                columns_to_keep.append(original_key)

            df = pd.read_csv(file_path, usecols=lambda c: c in columns_to_keep, low_memory=False)

            # Apply renames to standardize column names *before* any merge
            rename_map = file_config.get('rename_map', {})
            df.rename(columns=rename_map, inplace=True)
            
            # Determine the standardized key name for this file
            current_standardized_key = rename_map.get(original_key, original_key)
            if standardized_master_key not in df.columns and current_standardized_key in df.columns:
                 df.rename(columns={current_standardized_key: standardized_master_key}, inplace=True)

            # Drop rows where the primary key is null/empty, as they cannot be merged
            df.dropna(subset=[standardized_master_key], inplace=True)

            # Collect all unique keys for the master index
            master_key_set.update(df[standardized_master_key].unique())
            all_dataframes[file_config['filename']] = df
        
        if not master_key_set:
            return "Error: No valid data or primary keys found in any of the source files. Cannot create a master record."

        # --- Step 2: Create the Master DataFrame ---
        # This DataFrame contains a single column with every unique VM/asset name.
        print(f"\n--- Phase 2: Building Master Index of {len(master_key_set)} Unique Assets ---")
        master_df = pd.DataFrame(list(master_key_set), columns=[standardized_master_key])

        # --- Step 3: Iteratively Left-Join to the Master DataFrame ---
        # This enriches the master list with data from each source file.
        print("\n--- Phase 3: Merging all data onto Master Index ---")
        for filename, df_to_merge in all_dataframes.items():
            print(f"  Merging data from: {filename}")
            # Ensure the DataFrame to be merged is unique on the key to avoid row duplication
            df_to_merge.drop_duplicates(subset=[standardized_master_key], keep='first', inplace=True)
            
            master_df = pd.merge(
                master_df,
                df_to_merge,
                on=standardized_master_key,
                how='left',
                suffixes=('', f'_{filename.replace(".csv", "")}') # Add suffix to handle duplicate columns
            )

        # --- Step 4: Coalesce Duplicate Columns ---
        # If multiple files had the same column (e.g., 'guest_os'), merge them into one.
        print("\n--- Phase 4: Cleaning and Finalizing Golden Record ---")
        cols_to_coalesce = [col for col in master_df.columns if '_' in col and col.rsplit('_', 1)[0] in master_df.columns]
        base_cols = set(col.rsplit('_', 1)[0] for col in cols_to_coalesce)

        for base_col in base_cols:
            print(f"  Coalescing column: {base_col}")
            related_cols = [base_col] + [c for c in master_df.columns if c.startswith(f"{base_col}_")]
            # Forward-fill across the row to take the first non-null value
            master_df[base_col] = master_df[related_cols].bfill(axis=1).iloc[:, 0]
            # Drop the now-redundant suffixed columns
            master_df.drop(columns=[c for c in related_cols if c != base_col], inplace=True)

        # --- Final Step: Save the Consolidated File ---
        output_filename = os.path.join(directory_path, "consolidated_migration_data.csv")
        master_df.to_csv(output_filename, index=False)
        print("Cleaning up intermediate source files...")
        source_csvs = glob.glob(os.path.join(directory_path, "*.csv"))
        for csv_file in source_csvs:
            if os.path.abspath(csv_file) != os.path.abspath(output_filename):
                try:
                    os.remove(csv_file)
                    print(f"  -> Removed {os.path.basename(csv_file)}")
                except Exception as e:
                    print(
                        f"  -> Warning: Could not remove {os.path.basename(csv_file)}. Error: {e}"
                    )

        success_message = f"Success! Consolidated data saved to: {os.path.abspath(output_filename)}"
        print(f"\n{success_message}")

        # Set the paths in the tool_context state for the next agent
        tool_context.state["golden_record_path"] = os.path.abspath(output_filename)

        # Return a structured JSON object containing both paths for the next agent.
        return json.dumps({
            "consolidation_config_path": os.path.abspath(consolidation_config_path),
            "golden_record_path": os.path.abspath(output_filename)
        })

    except KeyError as e:
        return f"Error: The 'consolidation_config' is missing a required key: {e}"
    except Exception as e:
        return f"Error during data processing: {e}"

def generate_consolidation_config(tool_context: ToolContext, user_feedback: str = "") -> dict:
    """
    Inspects data schemas and uses a GenAI model to generate or refine a consolidation_config.json.
    The resulting config is stored in the tool_context state.
    """
    directory_path = tool_context.state.get('directory_path')
    if not directory_path:
        return {"error": "directory_path not found in tool_context state."}

    debug_dir = os.path.join(directory_path, "debug")
    os.makedirs(debug_dir, exist_ok=True)

    # Step 1: Get the data schema
    schema_json_str = inspect_and_load_data_context(tool_context)
    schema_data = json.loads(schema_json_str)
    if "error" in schema_data:
        return schema_data

    # Step 2: Prepare the prompt
    previous_config = tool_context.state.get("consolidation_config")

    prompt_template = """You are an expert Cloud Migration Automation Specialist. Your primary objective is to create a `consolidation_config.json` object.

**Rules:**
- Your entire plan MUST be based on the filenames and columns present in the `data_schema`. Do not invent or assume any filenames or columns.
- **Assess Each Source**: Based *only* on the `data_schema` from the previous step, analyze every column to determine its weightage for migration wave planning. Choose columns that are input agnostic by principle but does not lose the inherent context present in the input.
- **Categorize Columns**: Create two lists for each source format:
    - **Columns to Keep**: Identify all columns that can be used as a parameter for filtering or grouping (e.g., Cluster, Powerstate, OS, app_name, criticality, Annotation). Apply caution while determining the column names which could sometimes belong to a destination placeholder (example : Datacenter in TxTure) rather than source. And add a field with the rationale for the inclusion crtieria.
    - **Columns to Strip**: Identify all columns that provide no value for grouping and should be discarded (e.g., internal SDK versions, transient heartbeat status, specific timestamps, file paths). And add a field with the rationale for the inclusion crtieria
- **Define the Golden Record Standard**: Propose a standardized set of column names for your Golden Record. This record must be comprehensive enough to hold technical, business, and operational data. Start with this baseline and expand if necessary:
`asset_id, asset_name, source_platform, power_state, cpu_cores, memory_gb, total_storage_gb, guest_os, ip_address, network_name, datacenter_loc, cluster_name, app_name, app_type_name, environment, business_unit, owner_name, criticality, recovery_time_objective`.

- Based on the **Columns to Keep** determined above, you must create a `consolidation_config` JSON object from scratch.
- **CRITICAL: The final consolidated file MUST contain a column named `asset_name`.** This column is the primary human-readable identifier for servers (e.g., the VM name). You MUST ensure that the source column containing the server name (like 'VM', 'ServerName', 'name', etc.) is mapped to `asset_name` in your `rename_map`. This is non-negotiable.

- **Identify Base File & Key**: From the filenames provided in the `data_schema`, choose a `base_file` that seems most central (e.g., most records, most columns, or contains a clear primary identifier like 'VM' or 'ServerName'). Identify its primary key. **CRITICAL**: The filenames you use in the configuration MUST exist in the `data_schema`.
- **Define Merge Strategy**: Determine which other files from the `data_schema` should be merged into the base file and on which key.
- **Construct the Config**: Build the `consolidation_config` object with the `base_file` and `files_to_merge` you have defined. Each file must have its `filename`, its join `key`, and its own inferred list of map of `columns_to_keep` with the `column_name` and  `rationale`. And similarly a list of map of `columns_to_strip` with the `column_name` and  `rationale`.
- **Apply Mappings**: To align with the Golden Record, you can add a `rename_map` object to each file's configuration. This map should contain source_column_name as key and golden_record_column_name as value.

**CRITICAL RULE FOR EXAMPLES:** The following example is for STRUCTURE ONLY. You MUST use the actual filenames and columns discovered in the `data_schema`.

**Example `consolidation_config` structure:**
```json
{{
    "base_file": {{
        "filename": "source_data_1.csv",
        "key": "VM",
        "columns_to_keep": [
            {{"column_name": "VM", "rationale": "Primary identifier for the virtual machine."}},
            {{"column_name": "Powerstate", "rationale": "Indicates if the server is running or not."}}
        ],
        "rename_map": {{ "VM": "asset_name" }}
    }},
    "files_to_merge": [
        {{
            "filename": "source_data_2.csv",
            "key": "Server Name",
            "columns_to_keep": [
                {{"column_name": "Server Name", "rationale": "Primary identifier for mapping."}},
                {{"column_name": "Application", "rationale": "Provides business context."}}
            ],
            "rename_map": {{ "Server Name": "asset_name", "Application": "app_name" }}
        }}
    ]
}}
```

**Data Schema:**
{data_schema}

{feedback_section}

Based on the above, provide the complete, updated `consolidation_config` JSON object.
"""

    feedback_section = ""
    if user_feedback and previous_config:
        feedback_section = f"""
**Previous Configuration:**
{json.dumps(previous_config, indent=2)}

**User Feedback for Refinement:**
"{user_feedback}"

Please refine the 'Previous Configuration' based on the 'User Feedback'.
"""
    elif user_feedback:
        feedback_section = f"""
**User Feedback to Incorporate:**
"{user_feedback}"

Please create the initial configuration incorporating this feedback.
"""

    prompt = prompt_template.format(
        data_schema=json.dumps(schema_data, indent=2),
        feedback_section=feedback_section
    )

    # Step 3: Call the model
    try:
        call_desc = "Generate Consolidation Config"
        if user_feedback:
            call_desc = "Refine Consolidation Config"

        response = utils.generate_content_with_retry(prompt, call_desc, debug_dir)
        config_json = utils.parse_model_response(response)

        # Step 4: Store in context and return
        tool_context.state["consolidation_config"] = config_json
        return config_json

    except (json.JSONDecodeError, Exception) as e:
        error_msg = f"Failed to generate/refine consolidation config. Error: {e}"
        print(error_msg)
        return {"error": error_msg}


config_normalizer_agent = LlmAgent(
    model="gemini-2.5-pro",
    name="config_normalizer_agent",
    description="Orchestrates data configuration and normalization. It inspects data, works with the user to create a configuration, and then generates a final 'Golden Record' CSV.",
    instruction="""You are the Data Configuration and Normalization Specialist. Your job is to generate a data consolidation plan, get user approval, and then save it.

**WORKFLOW:**

1. Call the `generate_consolidation_config` tool to create an initial `consolidation_config.json`. Present this config to the user for review in a markdown table format. Create two sections: "Columns to Keep" and "Columns to Strip". Each section should have it's own table. The table should have columns like: `Source File`, `Source Column`, `Golden Record Column`, and `Rationale`.
2. Then you MUST ask user for feedback or approval. If user provides feedback, call `generate_consolidation_config` again with the feedback as `user_feedback` parameter to refine the config. Repeat this loop until the user approves the config.
Stop calling the `generate_consolidation_config` tool ONLY when the user mentions ("satisfied", "approved", "looks good") or something similar.
3. Once the user approves the config, call the `generate_and_save_consolidated_csv`. 
4. Once the `generate_and_save_consolidated_csv` tool has finished, call the parent agent.
""",
    tools=[
        generate_consolidation_config,
        generate_and_save_consolidated_csv,
    ],
)