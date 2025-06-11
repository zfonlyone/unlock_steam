import os
import sys
import asyncio
import aiofiles
import json
import vdf
from pathlib import Path
from typing import List, Tuple, Dict, Any


class Logger:
    """Silent logger class - no output"""
    def info(self, message): pass
    def warning(self, message): pass
    def error(self, message): pass


LOG = Logger()


async def parse_key_vdf(file_path: Path) -> List[Tuple[str, str]]:
    """Parse a key.vdf file to extract depot IDs and decryption keys"""
    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
        
        depots = vdf.loads(content)["depots"]
        return [(d_id, d_info["DecryptionKey"]) for d_id, d_info in depots.items()]
    except Exception:
        return []


def extract_depot_manifest_info(filename: str) -> Tuple[str, str]:
    """Extract depot ID and manifest ID from a manifest filename"""
    basename = Path(filename).stem
    if "_" not in basename:
        return None, None
        
    depot_id, manifest_id = basename.split("_", 1)
    if not (depot_id.isdigit() and manifest_id.isdigit()):
        return None, None
        
    return depot_id, manifest_id


async def process_manifest_folder(folder_path: Path) -> Tuple[List[Tuple[str, str]], Dict[str, List[str]]]:
    """Process a folder containing manifest and key files"""
    depot_data = []
    depot_map = {}
    
    # Look for key.vdf files first
    for file in folder_path.glob("**/key.vdf"):
        keys = await parse_key_vdf(file)
        depot_data.extend(keys)
        LOG.info(f"Parsed key file: {file.name} - Found {len(keys)} depot keys")
    
    # Process manifest files
    for file in folder_path.glob("**/*.manifest"):
        depot_id, manifest_id = extract_depot_manifest_info(file.name)
        if depot_id and manifest_id:
            depot_map.setdefault(depot_id, []).append(manifest_id)
            LOG.info(f"Found manifest: {file.name}")
    
    # Sort manifest IDs by newest first (highest number)
    for depot_id in depot_map:
        depot_map[depot_id].sort(key=lambda x: int(x), reverse=True)
    
    return depot_data, depot_map


async def copy_manifests_to_steam(source_folder: Path, steam_path: Path, depot_map: Dict[str, List[str]]) -> None:
    """Copy manifest files to Steam's depotcache directory"""
    depot_cache = steam_path/ "config" / "depotcache"
    depot_cache.mkdir(exist_ok=True)
    
    for depot_id, manifest_ids in depot_map.items():
        for manifest_id in manifest_ids:
            manifest_filename = f"{depot_id}_{manifest_id}.manifest"
            source_file = None
            
            # Search for the manifest file in the source folder
            for file in source_folder.glob(f"**/{manifest_filename}"):
                source_file = file
                break
            
            if source_file:
                dest_file = depot_cache / manifest_filename
                if dest_file.exists():
                    LOG.warning(f"Manifest already exists: {dest_file}")
                    continue
                
                # Copy the file
                async with aiofiles.open(source_file, "rb") as src:
                    content = await src.read()
                    async with aiofiles.open(dest_file, "wb") as dst:
                        await dst.write(content)
                LOG.info(f"Copied manifest: {manifest_filename}")


async def setup_steamtools(depot_data: List[Tuple[str, str]], app_id: str, depot_map: Dict[str, List[str]], steam_path: Path) -> bool:
    """Configure SteamTools for game unlocking"""
    st_path = steam_path / "config" / "stplug-in"
    st_path.mkdir(exist_ok=True)

    # Create Lua script content
    lua_content = f'addappid({app_id}, 1, "None")\n'
    for d_id, d_key in depot_data:
        if d_id in depot_map and depot_map[d_id]:
            for manifest_id in depot_map[d_id]:
                lua_content += f'addappid({d_id}, 1, "{d_key}")\nsetManifestid({d_id},"{manifest_id}")\n'
                break
        else:
            lua_content += f'addappid({d_id}, 1, "{d_key}")\n'

    # Write the Lua file
    lua_file = st_path / f"{app_id}.lua"
    try:
        async with aiofiles.open(lua_file, "w") as f:
            await f.write(lua_content)
        return True
    except:
        return False


async def setup_greenluma(depot_data: List[Tuple[str, str]], steam_path: Path) -> bool:
    """Configure GreenLuma for game unlocking"""
    applist_dir = steam_path / "AppList"
    applist_dir.mkdir(exist_ok=True)
    
    # Delete existing AppList files
    for f in applist_dir.glob("*.txt"):
        f.unlink()
    
    # Create new AppList files
    for idx, (d_id, _) in enumerate(depot_data, 1):
        (applist_dir / f"{idx}.txt").write_text(str(d_id))
        LOG.info(f"Created AppList entry: {idx}.txt with depot ID {d_id}")
    
    # Update Steam config.vdf with decryption keys
    config_path = steam_path / "config" / "config.vdf"
    if config_path.exists():
        try:
            async with aiofiles.open(config_path, "r") as f:
                content = vdf.loads(await f.read())
            
            # Add decryption keys to config
            content.setdefault("depots", {}).update(
                {d_id: {"DecryptionKey": d_key} for d_id, d_key in depot_data}
            )
            
            # Write updated config
            async with aiofiles.open(config_path, "w") as f:
                await f.write(vdf.dumps(content))
                
            LOG.info(f"Updated Steam config with {len(depot_data)} depot keys")
        except Exception as e:
            LOG.error(f"Failed to update Steam config: {str(e)}")
            return False
    else:
        LOG.error(f"Steam config not found at: {config_path}")
        return False
    
    return True


async def unlock_process(steam_path: Path, manifests_path: Path, app_id: str) -> bool:
    """直接复制清单文件到Steam目录"""
    # 复制清单文件到depot缓存
    depot_cache = steam_path / "config" / "depotcache"
    depot_cache.mkdir(exist_ok=True)
    
    # 复制所有manifest文件
    try:
        for manifest_file in manifests_path.glob("**/*.manifest"):
            dest_file = depot_cache / manifest_file.name
            if not dest_file.exists():
                try:
                    async with aiofiles.open(manifest_file, "rb") as src:
                        content = await src.read()
                        async with aiofiles.open(dest_file, "wb") as dst:
                            await dst.write(content)
                except:
                    pass
        return True
    except:
        return False


async def unlock_process_lua(steam_path: Path, manifests_path: Path, app_id: str) -> bool:
    """直接复制Lua文件到Steam目录"""
    # 设置路径
    st_path = steam_path / "config" / "stplug-in"
    st_path.mkdir(exist_ok=True)
    
    # 复制app_id.lua文件
    source_lua = manifests_path / f"{app_id}.lua"
    if source_lua.exists():
        lua_file = st_path / f"{app_id}.lua"
        try:
            async with aiofiles.open(source_lua, "rb") as src:
                content = await src.read()
                async with aiofiles.open(lua_file, "wb") as dst:
                    await dst.write(content)
        except:
            return False
    
    # 同时复制清单文件
    depot_cache = steam_path / "config" / "depotcache"
    depot_cache.mkdir(exist_ok=True)
    
    for manifest_file in manifests_path.glob("**/*.manifest"):
        dest_file = depot_cache / manifest_file.name
        if not dest_file.exists():
            try:
                async with aiofiles.open(manifest_file, "rb") as src:
                    content = await src.read()
                    async with aiofiles.open(dest_file, "wb") as dst:
                        await dst.write(content)
            except:
                pass
    
    return True


async def main():
    print(r"""
    _____                       _   _       _            _    
   / ____|                     | | | |     | |          | |   
  | (___  _   _  ___  ___ _ __ | |_| |_   _| | ___   ___| | __
   \___ \| | | |/ _ \/ _ \ '_ \|  _  | | | | |/ _ \ / __| |/ /
   ____) | |_| |  __/  __/ | | | | | | |_| | | (_) | (__|   < 
  |_____/ \__, |\___|\___|_| |_\_| |_/\__,_|_|\___/ \___|_|\_\
           __/ |                                              
          |___/                                               
    """)
    print("Steam Game Unlock Tool")

    
    # Get inputs from user
    steam_path_str = input("Enter your Steam installation path (default: C:/Program Files (x86)/Steam): ").strip()
    if not steam_path_str:
        steam_path_str = "C:/Program Files (x86)/Steam"
    
    steam_path = Path(steam_path_str)
    if not steam_path.exists():
        LOG.error(f"Steam path does not exist: {steam_path}")
        return
    
    manifests_path_str = input("Enter the folder path containing manifest and key files: ").strip()
    if not manifests_path_str:
        manifests_path_str="C:/Program Files (x86)/Steam"
        return
    
    manifests_path = Path(manifests_path_str)
    if not manifests_path.exists():
        LOG.error(f"Manifest folder does not exist: {manifests_path}")
        return
    
    app_id = input("Enter the game's AppID: ").strip()
    if not app_id.isdigit():
        LOG.error(f"Invalid AppID: {app_id}")
        return


    # Check for installed unlock tools
    has_steamtools = (steam_path / "config" / "stplug-in").is_dir()
    has_greenluma = any(
        (steam_path / dll).exists()
        for dll in ["GreenLuma_2024_x86.dll", "GreenLuma_2024_x64.dll", "hid.dll"]
    )
    
    if not (has_steamtools or has_greenluma):
        LOG.error("No supported unlock tools detected. Please install SteamTools or GreenLuma first.")
        return
    
    # List available tools
    print("\nDetected unlock tools:")
    if has_steamtools:
        print("1. SteamTools")
    if has_greenluma:
        print("2. GreenLuma")
    
    # Get tool choice
    tool_choice_str = input("\nSelect unlock tool (1 or 2): ").strip()
    if not tool_choice_str.isdigit():
        LOG.error("Invalid choice")
        return
    
    tool_choice = int(tool_choice_str)
    if tool_choice not in [1, 2]:
        LOG.error("Invalid choice")
        return
    
    if tool_choice == 1 and not has_steamtools:
        LOG.error("SteamTools not detected")
        return
    
    if tool_choice == 2 and not has_greenluma:
        LOG.error("GreenLuma not detected")
        return
    #验证密钥
    depot_data, depot_map = await process_manifest_folder(manifests_path)

    if not depot_data:
        LOG.error("No depot keys found in the manifest folder")
        return

    LOG.info(f"Found {len(depot_data)} depot keys and {sum(len(v) for v in depot_map.values())} manifest files")

    # Copy manifests to Steam's depotcache
    await copy_manifests_to_steam(manifests_path, steam_path, depot_map)

    # Setup selected unlock tool
    success = False
    if tool_choice == 1:
        success = await setup_steamtools(depot_data, app_id, depot_map, steam_path)
    else:
        success = await setup_greenluma(depot_data, steam_path)
    
    if success:
        LOG.info("Game unlock configuration completed successfully!")
        LOG.info("Restart Steam for changes to take effect")
    else:
        LOG.error("Failed to configure game unlock")




    input("Press Enter to exit...")


# This allows the file to be used both as a script and as a module
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        LOG.error(f"Error: {str(e)}")
        import traceback
        LOG.error(traceback.format_exc())
        input("Press Enter to exit...") 