from google.adk.agents import LlmAgent
from google.adk.tools import ToolContext
import pandas as pd
import json
import os
import math
import re

# --- Helper Functions ---

def _check_criteria(server_row: pd.Series, criteria_node: dict) -> bool:
    """Recursively checks if a server row matches the blueprint criteria."""
    if not isinstance(criteria_node, dict):
        return False

    for key, value in criteria_node.items():
        if key.lower() == 'and':
            return all(_check_criteria(server_row, sub_node) for sub_node in value)
        if key.lower() == 'or':
            return any(_check_criteria(server_row, sub_node) for sub_node in value)

        # This is a leaf node (a condition)
        field = key
        if field not in server_row:
            return False # Field not present, condition fails

        server_value = str(server_row[field])
        condition = value.get('operator', '').lower()
        target_value = value.get('value')

        if condition == 'equals':
            return server_value == str(target_value)
        if condition == 'contains':
            return str(target_value).lower() in server_value.lower()
        if condition == 'not_contains':
            return str(target_value).lower() not in server_value.lower()
        if condition == 'in':
            return server_value in [str(v) for v in target_value]
        if condition == 'like':
            pattern = str(target_value)
            val = str(server_value)
            # Handle SQL LIKE wildcards by converting to Python equivalents
            if pattern.startswith('%') and pattern.endswith('%'):
                return pattern.strip('%').lower() in val.lower()
            elif pattern.startswith('%'):
                return val.lower().endswith(pattern.strip('%').lower())
            elif pattern.endswith('%'):
                return val.lower().startswith(pattern.strip('%').lower())
            else: # No wildcards, treat as equals
                return val.lower() == pattern.lower()
        if condition == 'not like':
            pattern = str(target_value)
            val = str(server_value)
            # Handle SQL NOT LIKE wildcards
            if pattern.startswith('%') and pattern.endswith('%'):
                return pattern.strip('%').lower() not in val.lower()
            elif pattern.startswith('%'):
                return not val.lower().endswith(pattern.strip('%').lower())
            elif pattern.endswith('%'):
                return not val.lower().startswith(pattern.strip('%').lower())
            else: # No wildcards, treat as not equals
                return val.lower() != pattern.lower()

    return False # Should not be reached if criteria is well-formed


def _get_os_family(os_string: str) -> str:
    """Categorizes an OS string into a general family."""
    os_lower = str(os_string).lower()
    if 'windows' in os_lower:
        return 'Windows'
    if any(distro in os_lower for distro in ['linux', 'rhel', 'red hat', 'centos', 'ubuntu', 'suse', 'debian']):
        return 'Linux'
    if 'aix' in os_lower:
        return 'AIX'
    if 'solaris' in os_lower:
        return 'Solaris'
    return 'Other'


# --- Tool Definition ---

def perform_wave_plan_validation(
    tool_context: ToolContext
) -> str:
    """
    Performs data integrity checks and calculates a Wave Quality Score (WQS) for a migration plan.
    
    This tool is state-aware and retrieves the necessary file paths from the tool_context.
    """
    golden_record_path = tool_context.state.get("golden_record_path")
    blueprint_path = tool_context.state.get("blueprint_path")
    wave_plan_path = tool_context.state.get("wave_plan_path")

    if not all([golden_record_path, blueprint_path, wave_plan_path]):
        return json.dumps({"error": "One or more required paths (golden_record_path, blueprint_path, wave_plan_path) were not found in the tool_context state."})

    """
    Args:
        golden_record_path (str): Path to the consolidated_migration_data.csv file.
        blueprint_path (str): Path to the final_migration_blueprint.json file.
        wave_plan_path (str): Path to the final_migration_wave_plan.json file.

    Returns:
        str: A detailed validation and quality report in markdown format.
    """
    print("\n--- Starting Migration Wave Plan Validation and Quality Scoring ---")

    # --- 1. Load Input Artifacts ---
    try:
        print(f"  Loading Golden Record from: {golden_record_path}")
        df_golden_record = pd.read_csv(golden_record_path, low_memory=False)
        # Fill NaNs for all object columns to prevent errors in SQL queries
        for col in df_golden_record.columns:
            if df_golden_record[col].dtype == "object":
                df_golden_record[col] = df_golden_record[col].fillna("")

        print(f"  Loading Migration Blueprint from: {blueprint_path}")
        with open(blueprint_path, 'r') as f:
            blueprint = json.load(f)

        print(f"  Loading Final Wave Plan from: {wave_plan_path}")
        with open(wave_plan_path, 'r') as f:
            wave_plan = json.load(f)

    except FileNotFoundError as e:
        return f"Error: Could not find a required input file. {e}"
    except Exception as e:
        return f"Error loading input files: {e}"

    # --- Part A: Data Integrity Checks ---
    print("  Executing Part A: Data Integrity Checks...")
    integrity_results = {}
    
    primary_key_column = 'asset_name'  # Assuming this is the standard key
    all_golden_record_vms = set(df_golden_record[primary_key_column])
    df_golden_record.set_index(primary_key_column, inplace=True, drop=False)

    all_plan_vms = set()
    vms_in_plan_map = {}  # To track which wave a VM is in for uniqueness check
    
    # Get all VMs from the plan and build a map for uniqueness check
    for wave_name, wave_data in wave_plan.get('wave_definitions', {}).items():
        for vm in wave_data.get('wave_assignment', []):
            if vm in vms_in_plan_map:
                vms_in_plan_map[vm].append(wave_name)
            else:
                vms_in_plan_map[vm] = [wave_name]
            all_plan_vms.add(vm)

    # Metric 1: Uniqueness Check
    duplicate_vms = {vm: waves for vm, waves in vms_in_plan_map.items() if len(waves) > 1}
    if duplicate_vms:
        integrity_results["Uniqueness"] = {"Result": "FAILED", "Details": f"{len(duplicate_vms)} VMs are in multiple waves (e.g., {list(duplicate_vms.keys())[0]})."}
    else:
        integrity_results["Uniqueness"] = {"Result": "PASSED", "Details": "Each VM is assigned to exactly one wave."}

    # Metric 2: Asset Count Integrity
    total_golden_record = len(all_golden_record_vms)
    total_in_plan = len(all_plan_vms)
    missing_from_plan = all_golden_record_vms - all_plan_vms
    extra_in_plan = all_plan_vms - all_golden_record_vms
    
    if total_in_plan == total_golden_record:
        integrity_results["Asset Count Integrity"] = {"Result": "PASSED", "Details": f"Total VMs in plan ({total_in_plan}) matches Golden Record ({total_golden_record})."}
    else:
        details = []
        if missing_from_plan:
            details.append(f"{len(missing_from_plan)} VMs missing from plan.")
        if extra_in_plan:
            details.append(f"{len(extra_in_plan)} extra VMs found in plan.")
        integrity_results["Asset Count Integrity"] = {"Result": "FAILED", "Details": " ".join(details)}

    # Metric 3: Wave Size Compliance
    total_vms = len(df_golden_record)
    min_wave_size = int(math.ceil(total_vms * 0.02))
    calculated_max = 35.15 * math.log(total_vms) - 112.14 if total_vms > 0 else 0
    max_wave_size = int(math.ceil(max(calculated_max, min_wave_size))) if total_vms > 0 else 0

    sizing_issues = []
    for wave_name, wave_data in wave_plan.get('wave_definitions', {}).items():
        current_wave_size = len(wave_data.get('wave_assignment', []))
        if not ('unclassified' in wave_name.lower()) and not (min_wave_size <= current_wave_size <= max_wave_size):
            sizing_issues.append(f"'{wave_name}' (size {current_wave_size}) is outside thresholds (Min: {min_wave_size}, Max: {max_wave_size})")

    if sizing_issues:
        integrity_results["Wave Size Compliance"] = {"Result": "FAILED", "Details": " ".join(sizing_issues)}
    else:
        integrity_results["Wave Size Compliance"] = {"Result": "PASSED", "Details": f"All execution waves are within size thresholds (Min: {min_wave_size}, Max: {max_wave_size})."}

    # --- Part B: Wave Quality Scoring ---
    print("  Executing Part B: Wave Quality Scoring...")
    wave_quality_scores = []

    # Create a mapping from renumbered wave name to the original blueprint rule
    blueprint_rules = sorted(
        [w for w in blueprint.get("wave_definitions", []) if isinstance(w, dict)],
        key=lambda x: x.get("priority", 999)
    )
    wave_name_to_rule_map = {}
    for i, rule in enumerate(blueprint_rules):
        old_name = rule.get("wave_name", "")
        descriptive_part_match = re.search(r':\s*(.*)', old_name)
        descriptive_part = descriptive_part_match.group(1) if descriptive_part_match else old_name
        new_name = f"Wave {i + 1}: {descriptive_part}"
        wave_name_to_rule_map[new_name] = rule

    available_cols = df_golden_record.columns
    for wave_name, wave_data in wave_plan.get('wave_definitions', {}).items():
        if 'unclassified' in wave_name.lower() or 'out of scope' in wave_name.lower():
            continue

        wave_vms = wave_data.get('wave_assignment', [])
        if not wave_vms:
            continue

        wave_df = df_golden_record[df_golden_record[primary_key_column].isin(wave_vms)]

        # 1. Cohesion Score (Blueprint-driven)
        cohesion_score = 0
        rule = wave_name_to_rule_map.get(wave_name)
        if rule and 'criteria' in rule:
            matching_vms = sum(wave_df.apply(lambda vm: _check_criteria(vm, rule['criteria']), axis=1))
            cohesion_score = (matching_vms / len(wave_df)) * 100 if len(wave_df) > 0 else 0
        else:
            cohesion_score = 10 # Low score for waves not found in blueprint

        # 2. Risk Score
        risk_score = 0
        # Check for variations of 'production' environment names, case-insensitively.
        if 'environment' in available_cols and wave_df['environment'].str.lower().isin(['prod', 'production', 'prd']).any():
            risk_score += 50
        if 'criticality' in available_cols:
            # Check for variations of criticality, case-insensitively.
            crit_lower = wave_df['criticality'].str.lower()
            if crit_lower.isin(['critical', 'high']).any():
                risk_score += 30
            elif crit_lower.isin(['medium']).any():
                risk_score += 10

        # 3. Simplicity Score
        simplicity_score = 100
        if 'guest_os' in available_cols:
            os_families = wave_df['guest_os'].apply(_get_os_family).nunique()
            if os_families > 1:
                simplicity_score -= (os_families - 1) * 10
        if 'business_unit' in available_cols:
            bus = wave_df['business_unit'].nunique()
            if bus > 1:
                simplicity_score -= (bus - 1) * 5

        # Final WQS
        wqs = (cohesion_score * 0.4) + ((100 - risk_score) * 0.4) + (simplicity_score * 0.2)

        wave_quality_scores.append({
            "Execution Wave ID": wave_name,
            "Priority": wave_data.get('priority', 999),
            "Total VMs": len(wave_vms),
            "Rationale for Grouping": wave_data.get('rationale', 'N/A'),
            "Cohesion Score": cohesion_score,
            "Risk Score": risk_score,
            "Simplicity Score": simplicity_score,
            "Wave Quality Score (WQS)": round(wqs, 2)
        })

    # --- Generate Final Report ---
    print("  Generating final validation and quality report...")
    report_lines = ["# Migration Wave Plan: Validation and Quality Report", "\n---\n"]

    # Section 1: Executive Summary
    report_lines.append("## Executive Summary")
    avg_wqs = sum(w['Wave Quality Score (WQS)'] for w in wave_quality_scores) / len(wave_quality_scores) if wave_quality_scores else 0
    report_lines.append(f"The migration plan has been analyzed, yielding an **average Wave Quality Score (WQS) of {avg_wqs:.2f}**. This score reflects the plan's overall cohesion, risk profile, and simplicity.")
    report_lines.append("\nThis report provides a detailed breakdown of the quality scores for each wave and a summary of data integrity checks.")

    # Section 1: Final Execution Wave Plan & Quality Scores
    report_lines.append("\n## Final Execution Wave Plan & Quality Scores")
    if wave_quality_scores:
        headers = wave_quality_scores[0].keys()
        report_lines.append(f"| {' | '.join(headers)} |")
        report_lines.append(f"| {'--- |' * len(headers)}")
        for score_card in sorted(wave_quality_scores, key=lambda x: x.get('Priority', 999)):
            rationale_short = (score_card['Rationale for Grouping'][:70] + '...') if len(score_card['Rationale for Grouping']) > 70 else score_card['Rationale for Grouping']
            score_card['Rationale for Grouping'] = rationale_short.replace('\n', ' ').replace('|', ' ')
            row_values = [str(score_card[h]) for h in headers]
            report_lines.append(f"| {' | '.join(row_values)} |")
    else:
        report_lines.append("No execution waves were found to score.")

    # Add Score Legend
    report_lines.append("\n### Score Legend")
    report_lines.append("- **Cohesion Score (0-100)**: Measures how well the VMs in a wave adhere to the blueprint's rules. *Higher is better.*")
    report_lines.append("- **Risk Score (0-100)**: Assesses business risk based on environment (e.g., Prod) and asset criticality. *Lower is better.*")
    report_lines.append("- **Simplicity Score (0-100)**: Measures the technical homogeneity of the wave (e.g., OS, Business Unit). *Higher is better.*")
    report_lines.append("- **Wave Quality Score (WQS) (0-100)**: A composite score reflecting the overall quality and readiness of the wave, balancing the factors above. *Higher is better.*")

    # Section 2: Data Integrity Validation Report
    report_lines.append("\n## Data Integrity Validation Report")
    report_lines.append("| Metric | Status | Details |")
    report_lines.append("|---|---|---|")
    for metric, result in integrity_results.items():
        report_lines.append(f"| {metric} | **{result['Result']}** | {result['Details']} |")

    final_report_markdown = "\n".join(report_lines)

    print("--- Validation and Quality Scoring Complete ---")
    output_payload = {
        "validation_report": final_report_markdown,
        "wave_plan_path": wave_plan_path
    }
    return json.dumps(output_payload, indent=2)


# --- Agent Definition ---
validation_agent = LlmAgent(
    model='gemini-2.5-pro',
    name='validation_agent',
    description='An agent that performs data integrity checks, calculates a Wave Quality Score (WQS) for a migration plan using the blueprint, and generates a final quality and validation report.',
    instruction="""
You are an expert Cloud Migration Audit and Validation Specialist. Your primary function is to act as an independent auditor for a migration wave plan.

**Your Mandate:**
1.  You MUST call the `perform_wave_plan_validation` tool.
3.  The tool will return a JSON string containing the markdown report with the key `validation_report`.
4.  You MUST parse this JSON to extract the value of the `validation_report` key.
5.  Your final output MUST be ONLY the markdown report you extracted.
""",
    tools=[perform_wave_plan_validation],
)
