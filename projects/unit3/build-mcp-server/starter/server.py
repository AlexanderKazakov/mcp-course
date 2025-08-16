#!/usr/bin/env python3
"""
Module 1: Basic MCP Server - Starter Code
Implement tools for analyzing git changes and suggesting PR templates
"""

import json
import subprocess
from pathlib import Path
from difflib import SequenceMatcher
import logging

from mcp.server.fastmcp import FastMCP

# Initialize the FastMCP server
mcp = FastMCP("pr-agent")

# Set up a dedicated file logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Prevent adding duplicate handlers if the script is reloaded
if not logger.handlers:
    LOG_FILE = Path(__file__).parent / "server.log"
    file_handler = logging.FileHandler(LOG_FILE, mode="a")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)


# PR template directory (shared across all modules)
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"


@mcp.tool()
async def analyze_file_changes(
    base_branch: str = "main", 
    include_diff: bool = True, 
    max_diff_lines: int = 500,
) -> str:
    """Get the full diff and list of changed files in the current git repository.

    Args:
        base_branch: Base branch to compare against (default: main)
        include_diff: Include the full diff content (default: true)
        max_diff_lines: The maximum number of lines for the diff (default: 500)
    """
    # IMPORTANT: MCP tools have a 25,000 token response limit!
    # Large diffs can easily exceed this. Consider:
    # - Adding a max_diff_lines parameter (e.g., 500 lines)
    # - Truncating large outputs with a message
    # - Returning summary statistics alongside limited diffs

    # NOTE: Git commands run in the server's directory by default!
    # To run in Claude's working directory, use MCP roots:
    # context = mcp.get_context()
    # roots_result = await context.session.list_roots()
    # working_dir = roots_result.roots[0].uri.path
    # subprocess.run(["git", "diff"], cwd=working_dir)

    try:
        context = mcp.get_context()  # it somehow returns an object even if no context actually exists
        if context is None:
            return json.dumps({"error": "No MCP context found"})
        
        roots_result = await context.session.list_roots()
        if not roots_result.roots:
            return json.dumps({"error": "No workspace roots found."})
        working_dir = roots_result.roots[0].uri.path
        logger.info(f"Working directory: {working_dir}")

        # Get changed files
        changed_files_cmd = ["git", "diff", "--name-only", base_branch]
        changed_files_result = subprocess.run(
            changed_files_cmd,
            capture_output=True,
            text=True,
            cwd=working_dir,
            check=True,
        )
        changed_files = changed_files_result.stdout.strip().splitlines()

        response = {"changed_files": changed_files}

        if include_diff:
            diff_cmd = ["git", "diff", base_branch]
            diff_result = subprocess.run(
                diff_cmd,
                capture_output=True,
                text=True,
                cwd=working_dir,
                check=True,
            )
            diff_content = diff_result.stdout
            diff_lines = diff_content.splitlines()

            if len(diff_lines) > max_diff_lines:
                truncated_diff = "\n".join(diff_lines[:max_diff_lines])
                response["diff"] = truncated_diff
                response[
                    "message"
                ] = f"Diff truncated to {max_diff_lines} lines. Full diff has {len(diff_lines)} lines."
            else:
                response["diff"] = diff_content

        return json.dumps(response, indent=2)

    except subprocess.CalledProcessError as e:
        return json.dumps(
            {"error": "Git command failed", "details": e.stderr.strip()}, indent=2
        )
    except Exception as e:
        return json.dumps(
            {"error": f"An unexpected error occurred: {str(e)}"}, indent=2
        )


@mcp.tool()
async def get_pr_templates() -> str:
    """List available PR templates with their content."""
    if not TEMPLATES_DIR.is_dir():
        return json.dumps({"error": f"Templates directory not found at {TEMPLATES_DIR}"})

    templates = [
        {
            "filename": f.name,
            "type": f.stem,
            "content": f.read_text()
        }
        for f in TEMPLATES_DIR.iterdir()
        if f.is_file() and f.suffix == ".md"
    ]

    return json.dumps(templates, indent=2)


@mcp.tool()
async def suggest_template(changes_summary: str, change_type: str) -> str:
    """Let AI Agent analyze the changes and suggest the most appropriate PR template.
    
    Args:
        changes_summary: Your analysis of what the changes do
        change_type: The type of change you've identified (bug, feature, docs, refactor, test, etc.)
    """
    logger.info(f"Arguments:\nchanges_summary: {changes_summary}\nchange_type: {change_type}")
    
    # Get available templates
    templates_response = await get_pr_templates()
    templates = json.loads(templates_response)

    # get the template with the name closest to the change_type
    selected_template = max(
        templates, 
        key=lambda x: SequenceMatcher(None, x["type"].lower(), change_type.lower()).ratio()
    )
    
    suggestion = {
        "recommended_template": selected_template["type"],
        "template_content": selected_template["content"],
    }
    
    return json.dumps(suggestion, indent=2)


if __name__ == "__main__":
    mcp.run()