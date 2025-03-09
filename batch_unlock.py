#!/usr/bin/env python3
import asyncio
import os
import shutil
import tempfile
import argparse
import json
from pathlib import Path
import subprocess
from typing import List, Dict, Tuple, Optional

# Import from unlock_script.py - assuming it's in the same directory
from unlock_script import (
    Logger, process_manifest_folder, copy_manifests_to_steam,
    setup_steamtools, unlock_process, unlock_process_lua
)

# Set up logger
LOG = Logger()

async def run_command(cmd: List[str], cwd: Optional[str] = None) -> Tuple[bool, str]:
    """Run a shell command asynchronously and return success status and output"""
    LOG.info(f"Running command: {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        stdout, stderr = await proc.communicate()
        
        output = stdout.decode()
        if proc.returncode != 0:
            LOG.error(f"Command failed: {stderr.decode()}")
            return False, stderr.decode()
        return True, output
    except Exception as e:
        LOG.error(f"Failed to run command: {str(e)}")
        return False, str(e)

async def setup_git_worktree(repo_path: Path, branch: str, temp_dir: Path) -> Tuple[bool, Path]:
    """Setup a git worktree for a specific branch in a temporary directory"""
    worktree_path = temp_dir / branch
    
    # Create worktree
    success, output = await run_command(
        ["git", "worktree", "add", str(worktree_path), branch],
        cwd=str(repo_path)
    )
    
    if not success:
        return False, Path()
    
    LOG.info(f"Created worktree for branch {branch} at {worktree_path}")
    return True, worktree_path

async def cleanup_git_worktree(repo_path: Path, worktree_path: Path) -> bool:
    """Clean up a git worktree"""
    if not worktree_path.exists():
        return True
        
    success, output = await run_command(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=str(repo_path)
    )
    
    if not success:
        LOG.error(f"Failed to remove worktree at {worktree_path}")
        return False
        
    LOG.info(f"Removed worktree at {worktree_path}")
    return True

async def process_app(app_id: str, worktree_path: Path, steam_path: Path) -> bool:
    """Process a single app using the appropriate unlock method"""
    # Check if the worktree contains an app_id.lua file
    lua_file = worktree_path / f"{app_id}.lua"
    
    LOG.info(f"Processing app {app_id} from {worktree_path}")
    
    if lua_file.exists():
        LOG.info(f"Found Lua file for {app_id}, using direct copy method")
        # Use the lua copy method
        success = await unlock_process_lua(steam_path, worktree_path, app_id)
    else:
        LOG.info(f"No Lua file found for {app_id}, using depot key method")
        # Use the original method with depot keys
        success = await unlock_process(steam_path, worktree_path, app_id)
    
    return success

async def batch_unlock(repo_path: Path, app_ids: List[str], steam_path: Path) -> None:
    """Process multiple apps from a git repository using worktrees"""
    # Create temporary directory for worktrees
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        LOG.info(f"Created temporary directory: {temp_dir}")
        
        # Get list of branches from the repository
        success, output = await run_command(
            ["git", "branch", "-a"], 
            cwd=str(repo_path)
        )
        
        if not success:
            LOG.error("Failed to list branches")
            return
        
        # Parse branch names
        branches = []
        for line in output.splitlines():
            branch = line.strip().replace("* ", "")
            if branch and not branch.startswith("remotes/"):
                branches.append(branch)
        
        LOG.info(f"Found {len(branches)} branches")
        
        # Process each app ID
        results = {}
        for app_id in app_ids:
            LOG.info(f"\n--- Processing app {app_id} ---")
            
            # Look for a branch matching the app ID
            matching_branches = [b for b in branches if app_id in b]
            
            if not matching_branches:
                LOG.warning(f"No matching branch found for app ID {app_id}")
                results[app_id] = False
                continue
            
            # Use the first matching branch
            branch = matching_branches[0]
            LOG.info(f"Using branch {branch} for app ID {app_id}")
            
            # Create worktree
            success, worktree_path = await setup_git_worktree(repo_path, branch, temp_dir)
            if not success:
                LOG.error(f"Failed to create worktree for {app_id}")
                results[app_id] = False
                continue
            
            try:
                # Process the app
                result = await process_app(app_id, worktree_path, steam_path)
                results[app_id] = result
            finally:
                # Clean up worktree
                await cleanup_git_worktree(repo_path, worktree_path)
        
        # Print summary
        LOG.info("\n--- Unlock Summary ---")
        for app_id, success in results.items():
            status = "SUCCESS" if success else "FAILED"
            LOG.info(f"App {app_id}: {status}")
        
        successful = sum(1 for success in results.values() if success)
        LOG.info(f"Successfully unlocked {successful} out of {len(app_ids)} apps")

async def extract_app_ids_from_branches(repo_path: Path) -> List[str]:
    """Extract app IDs from branch names in the repository"""
    success, output = await run_command(
        ["git", "branch", "-r"], 
        cwd=str(repo_path)
    )
    
    if not success:
        LOG.error("Failed to list remote branches")
        return []
    
    app_ids = set()
    for line in output.splitlines():
        branch = line.strip().replace("* ", "").replace("origin/", "")
        # Extract numeric app ID from branch name
        # Common branch naming patterns include: app_1234567, 1234567_game, 1234567, etc.
        parts = branch.split('_')
        for part in parts:
            # If the part is a numeric string, it might be an app ID
            if part.isdigit() and len(part) >= 5:  # Most Steam appIDs are at least 5 digits
                app_ids.add(part)
                break
    
    LOG.info(f"Extracted {len(app_ids)} app IDs from branch names")
    return list(app_ids)

async def main():
    parser = argparse.ArgumentParser(description="Batch unlock Steam games using Git worktree")
    parser.add_argument("--repo", type=str, required=True, help="Path to the local Git repository")
    parser.add_argument("--apps", type=str, help="Optional: Comma-separated list of specific app IDs to process")
    parser.add_argument("--steam", type=str, help="Path to Steam installation folder")
    
    args = parser.parse_args()
    
    repo_path = Path(args.repo)
    if not repo_path.exists() or not (repo_path / ".git").exists():
        LOG.error(f"Invalid Git repository: {repo_path}")
        return
    
    # Parse app IDs
    app_ids = []
    if args.apps:
        app_ids = [app_id.strip() for app_id in args.apps.split(",")]
        LOG.info(f"Using {len(app_ids)} app IDs provided via command line")
    else:
        # Extract app IDs from branch names
        app_ids = await extract_app_ids_from_branches(repo_path)
        if not app_ids:
            LOG.error("Could not extract any app IDs from branch names")
            return
    
    if not app_ids:
        LOG.error("No app IDs provided or detected")
        return
    
    # Determine Steam path
    steam_path = None
    if args.steam:
        steam_path = Path(args.steam)
    else:
        # Try common Steam installation paths
        potential_paths = [
            Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam",
            Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Steam",
            Path("D:/Steam"),
            Path("C:/Steam"),
        ]
        
        for path in potential_paths:
            if path.exists() and (path / "steam.exe").exists():
                steam_path = path
                break
    
    if not steam_path or not steam_path.exists():
        LOG.error("Steam installation not found. Please specify the path with --steam")
        return
    
    LOG.info(f"Using Steam installation at: {steam_path}")
    LOG.info(f"Processing {len(app_ids)} app IDs: {', '.join(app_ids)}")
    
    await batch_unlock(repo_path, app_ids, steam_path)

if __name__ == "__main__":
    asyncio.run(main()) 