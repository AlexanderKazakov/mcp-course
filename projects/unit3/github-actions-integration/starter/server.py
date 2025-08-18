#!/usr/bin/env python3
"""
Module 2: GitHub Actions Integration - STARTER CODE
Extend your PR Agent with webhook handling and MCP Prompts for CI/CD workflows.
"""

import json
import os
import subprocess
from typing import Optional
from pathlib import Path
from datetime import datetime
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# File to store events
EVENTS_FILE = Path(__file__).parent / "github_events.json"

# Initialize the FastMCP server
mcp = FastMCP("pr-agent-actions")

# PR template directory (shared between starter and solution)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

# Default PR templates
DEFAULT_TEMPLATES = {
    "bug.md": "Bug Fix",
    "feature.md": "Feature",
    "docs.md": "Documentation",
    "refactor.md": "Refactor",
    "test.md": "Test",
    "performance.md": "Performance",
    "security.md": "Security"
}

# TODO: Add path to events file where webhook_server.py stores events
# Hint: EVENTS_FILE = Path(__file__).parent / "github_events.json"

# Type mapping for PR templates
TYPE_MAPPING = {
    "bug": "bug.md",
    "fix": "bug.md",
    "feature": "feature.md",
    "enhancement": "feature.md",
    "docs": "docs.md",
    "documentation": "docs.md",
    "refactor": "refactor.md",
    "cleanup": "refactor.md",
    "test": "test.md",
    "testing": "test.md",
    "performance": "performance.md",
    "optimization": "performance.md",
    "security": "security.md"
}


# ===== Module 1 Tools (Already includes output limiting fix from Module 1) =====

@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main",
    include_diff: bool = True,
    max_diff_lines: int = 500
) -> str:
    """Get the full diff and list of changed files in the current git repository.
    
    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
        max_diff_lines: Maximum number of diff lines to include (default: 500)
    """
    try:
        # Get list of changed files
        files_result = subprocess.run(
            ["git", "diff", "--name-status", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Get diff statistics
        stat_result = subprocess.run(
            ["git", "diff", "--stat", f"{base_branch}...HEAD"],
            capture_output=True,
            text=True
        )
        
        # Get the actual diff if requested
        diff_content = ""
        truncated = False
        if include_diff:
            diff_result = subprocess.run(
                ["git", "diff", f"{base_branch}...HEAD"],
                capture_output=True,
                text=True
            )
            diff_lines = diff_result.stdout.split('\n')
            
            # Check if we need to truncate (learned from Module 1)
            if len(diff_lines) > max_diff_lines:
                diff_content = '\n'.join(diff_lines[:max_diff_lines])
                diff_content += f"\n\n... Output truncated. Showing {max_diff_lines} of {len(diff_lines)} lines ..."
                diff_content += "\n... Use max_diff_lines parameter to see more ..."
                truncated = True
            else:
                diff_content = diff_result.stdout
        
        # Get commit messages for context
        commits_result = subprocess.run(
            ["git", "log", "--oneline", f"{base_branch}..HEAD"],
            capture_output=True,
            text=True
        )
        
        analysis = {
            "base_branch": base_branch,
            "files_changed": files_result.stdout,
            "statistics": stat_result.stdout,
            "commits": commits_result.stdout,
            "diff": diff_content if include_diff else "Diff not included (set include_diff=true to see full diff)",
            "truncated": truncated,
            "total_diff_lines": len(diff_lines) if include_diff else 0
        }
        
        return json.dumps(analysis, indent=2)
        
    except subprocess.CalledProcessError as e:
        return json.dumps({"error": f"Git error: {e.stderr}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    templates = [
        {
            "filename": filename,
            "type": template_type,
            "content": (TEMPLATES_DIR / filename).read_text()
        }
        for filename, template_type in DEFAULT_TEMPLATES.items()
    ]
    
    return json.dumps(templates, indent=2)


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let AI Agent analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    
    # Get available templates
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)
    
    # Find matching template
    template_file = TYPE_MAPPING.get(change_type.lower(), "feature.md")
    selected_template = next(
        (t for t in templates if t["filename"] == template_file),
        templates[0]  # Default to first template if no match
    )
    
    suggestion = {
        "recommended_template": selected_template,
        "reasoning": f"Based on your analysis: '{changes_summary}', this appears to be a {change_type} change.",
        "template_content": selected_template["content"],
        "usage_hint": "AI Agent can help you fill out this template based on the specific changes in your PR."
    }
    
    return json.dumps(suggestion, indent=2)


# ===== Module 2: New GitHub Actions Tools =====

@mcp.tool()
async def get_recent_actions_events(limit: int = 10) -> str:
    """Get recent GitHub Actions events received via webhook.
    
    Args:
        limit: Maximum number of events to return (default: 10)
    """
    if not EVENTS_FILE.exists():
        return json.dumps([])

    try:
        with open(EVENTS_FILE, "r") as f:
            events = json.load(f)
        
        # Sort events by timestamp (assuming 'timestamp' field exists)
        # Taking the last `limit` events to get the most recent ones
        recent_events = sorted(events, key=lambda x: x.get("timestamp", ""), reverse=True)[:limit]
        return json.dumps(recent_events, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to read or parse events file: {e}"})


@mcp.tool()
async def get_workflow_status(workflow_name: Optional[str] = None) -> str:
    """Get the current status of GitHub Actions workflows.
    
    Args:
        workflow_name: Optional specific workflow name to filter by
    """
    if not EVENTS_FILE.exists():
        return json.dumps({"status": "No events file found. No workflows to report."})

    try:
        with open(EVENTS_FILE, "r") as f:
            events = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return json.dumps({"error": f"Failed to read or parse events file: {e}"})

    # Filter for workflow_run events
    workflow_runs = [
        event["payload"]
        for event in events
        if event.get("event_type") == "workflow_run" and "payload" in event
    ]

    if not workflow_runs:
        return json.dumps({"status": "No workflow run events found."})

    # If a specific workflow name is provided, filter by it
    if workflow_name:
        workflow_runs = [
            run for run in workflow_runs
            if run.get("workflow", {}).get("name") == workflow_name
        ]
        if not workflow_runs:
            return json.dumps({"status": f"No workflow runs found for '{workflow_name}'."})

    # Group by workflow and find the latest status
    latest_statuses = {}
    for run in workflow_runs:
        name = run.get("workflow", {}).get("name")
        if not name:
            continue
        
        # Using run ID to get the latest run
        run_id = run.get("workflow_run", {}).get("id")
        timestamp = run.get("workflow_run", {}).get("updated_at")

        if name not in latest_statuses or run_id > latest_statuses[name]["id"]:
            latest_statuses[name] = {
                "id": run_id,
                "status": run.get("workflow_run", {}).get("status"),
                "conclusion": run.get("workflow_run", {}).get("conclusion"),
                "timestamp": timestamp
            }

    return json.dumps(latest_statuses, indent=2)


# ===== Module 2: MCP Prompts =====

@mcp.prompt()
async def analyze_ci_results():
    """Analyze recent CI/CD results and provide insights."""
    return """
Analyze the recent CI/CD activity using the available tools.

1.  **Get Recent Events**: Use `get_recent_actions_events` to see the latest webhook events.
2.  **Get Workflow Status**: Use `get_workflow_status` to check the status of all workflows.
3.  **Summarize Findings**: Based on the tool outputs, provide a summary of the CI/CD health.
    - Highlight any recent failures.
    - Mention any workflows that are consistently succeeding.
    - Identify any patterns or anomalies in the CI/CD activity.
"""


@mcp.prompt()
async def create_deployment_summary():
    """Generate a deployment summary for team communication."""
    return """
Create a concise deployment summary suitable for sharing with the team.

1.  **Identify Deployments**: Use `get_workflow_status` to find workflows related to deployment (e.g., names containing 'deploy').
2.  **Check Status**: Note the status (success, failure) and conclusion of the latest deployment runs.
3.  **Correlate with Changes**: Use `analyze_file_changes` to identify what code changes were included in the recent deployments.
4.  **Draft Summary**: Write a brief summary including:
    - Which workflows were deployed.
    - Whether the deployments were successful.
    - Key features or fixes included in the deployment.
"""


@mcp.prompt()
async def generate_pr_status_report():
    """Generate a comprehensive PR status report including CI/CD results."""
    return """
Generate a comprehensive status report for the current Pull Request.

1.  **Analyze Code Changes**: Use `analyze_file_changes` to get a summary of the code changes, changed files, and commits.
2.  **Check CI/CD Status**: Use `get_workflow_status` to see the results of the CI/CD pipeline for this PR.
3.  **Combine Information**: Create a report that includes:
    - A summary of the PR's purpose based on commit messages and changed files.
    - The status of all related CI/CD checks (e.g., tests, linting, builds).
    - Highlight any failures and provide context if possible.
"""


@mcp.prompt()
async def troubleshoot_workflow_failure():
    """Help troubleshoot a failing GitHub Actions workflow."""
    return """
Let's troubleshoot a failing GitHub Actions workflow.

1.  **Identify Failing Workflows**: Use `get_workflow_status` to find workflows that have a status of 'completed' and a conclusion of 'failure'.
2.  **Get Details**: For a specific failing workflow you want to investigate, use `get_workflow_status(workflow_name="...")` to get its latest status.
3.  **Analyze Events**: Use `get_recent_actions_events` to look for any related events that might provide more context on the failure.
4.  **Suggest Next Steps**: Based on the information, suggest potential causes for the failure and recommend next steps. For example:
    - "Check the GitHub Actions logs for the specific workflow run for detailed error messages."
    - "Review the recent commits to see if a change might have caused the failure."
    - "Verify that any required secrets or environment variables are correctly configured."
"""


if __name__ == "__main__":
    print("Starting PR Agent MCP server...")
    print("NOTE: Run webhook_server.py in a separate terminal to receive GitHub events")
    mcp.run()