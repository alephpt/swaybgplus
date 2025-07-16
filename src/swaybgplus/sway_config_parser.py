#!/usr/bin/env python3
"""
Sway configuration parser for extracting output configurations
"""

import re
import subprocess
import json
import os
import shutil
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple


@dataclass
class OutputConfig:
    """Represents a sway output configuration"""
    name: str
    position: Tuple[int, int]  # x, y coordinates
    resolution: Tuple[int, int]  # width, height
    scale: float = 1.0
    transform: str = "normal"
    enabled: bool = True
    available_modes: List[Tuple[int, int]] = None  # Available resolution modes


class SwayConfigParser:
    """Parser for sway configuration files and runtime output information"""
    
    def __init__(self, config_path: str = None):
        self.outputs: List[OutputConfig] = []
        self.config_path = config_path or self._find_config_path()
        self.config_content = ""
    
    def _find_config_path(self) -> Optional[str]:
        """Find sway config file in default locations"""
        possible_paths = [
            os.path.expanduser("~/.config/sway/config"),
            "/etc/sway/config"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def set_config_path(self, path: str):
        """Set the sway config file path"""
        self.config_path = path
    
    def get_config_path(self) -> Optional[str]:
        """Get current config file path"""
        return self.config_path
    
    def get_current_outputs(self) -> List[OutputConfig]:
        """Get current output configuration from sway via swaymsg"""
        try:
            result = subprocess.run(
                ['swaymsg', '-t', 'get_outputs'], 
                capture_output=True, 
                text=True, 
                check=True
            )
            
            outputs_data = json.loads(result.stdout)
            outputs = []
            
            for output in outputs_data:
                if not output.get('active', False):
                    continue
                    
                # Get position and resolution
                rect = output.get('rect', {})
                x = rect.get('x', 0)
                y = rect.get('y', 0)
                width = rect.get('width', 1920)
                height = rect.get('height', 1080)
                
                # Get scale factor
                scale = output.get('scale', 1.0)
                
                # Get transform
                transform = output.get('transform', 'normal')
                
                # Get available modes
                available_modes = []
                for mode in output.get('modes', []):
                    available_modes.append((mode['width'], mode['height']))
                
                output_config = OutputConfig(
                    name=output['name'],
                    position=(x, y),
                    resolution=(width, height),
                    scale=scale,
                    transform=transform,
                    enabled=True,
                    available_modes=available_modes
                )
                outputs.append(output_config)
            
            self.outputs = outputs
            return outputs
            
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            print(f"Error getting current outputs: {e}")
            return []
    
    def parse_config_file(self, config_path: str = None) -> List[OutputConfig]:
        """Parse sway config file for output configurations"""
        if config_path:
            self.config_path = config_path
        
        if not self.config_path or not os.path.exists(self.config_path):
            print(f"Config file not found: {self.config_path}")
            return []
        
        try:
            with open(self.config_path, 'r') as f:
                self.config_content = f.read()
            
            outputs = []
            
            # Parse output commands using regex
            output_pattern = r'output\s+([^\s]+)\s+(.+)'
            
            for line in self.config_content.split('\n'):
                line = line.strip()
                if line.startswith('#') or not line.startswith('output'):
                    continue
                
                match = re.match(output_pattern, line)
                if not match:
                    continue
                
                output_name = match.group(1)
                output_config_str = match.group(2)
                
                # Parse individual output configuration
                output_config = self._parse_output_config(output_name, output_config_str)
                if output_config:
                    outputs.append(output_config)
            
            self.outputs = outputs
            return outputs
            
        except Exception as e:
            print(f"Error parsing config file: {e}")
            return []
    
    def _parse_output_config(self, name: str, config_str: str) -> Optional[OutputConfig]:
        """Parse individual output configuration string"""
        # Default values
        position = (0, 0)
        resolution = (1920, 1080)
        scale = 1.0
        transform = "normal"
        enabled = True
        
        # Parse position
        pos_match = re.search(r'pos(?:ition)?\s+(\d+)\s+(\d+)', config_str)
        if pos_match:
            position = (int(pos_match.group(1)), int(pos_match.group(2)))
        
        # Parse resolution
        res_match = re.search(r'(?:res|resolution|mode)\s+(\d+)x(\d+)', config_str)
        if res_match:
            resolution = (int(res_match.group(1)), int(res_match.group(2)))
        
        # Parse scale
        scale_match = re.search(r'scale\s+([\d.]+)', config_str)
        if scale_match:
            scale = float(scale_match.group(1))
        
        # Parse transform
        transform_match = re.search(r'transform\s+(\w+)', config_str)
        if transform_match:
            transform = transform_match.group(1)
        
        # Check if disabled
        if 'disable' in config_str:
            enabled = False
        
        return OutputConfig(
            name=name,
            position=position,
            resolution=resolution,
            scale=scale,
            transform=transform,
            enabled=enabled,
            available_modes=[]  # Will be populated by get_current_outputs
        )
    
    def update_output_config(self, output_name: str, position: Tuple[int, int] = None, 
                           resolution: Tuple[int, int] = None, scale: float = None,
                           transform: str = None, enabled: bool = None) -> bool:
        """Update output configuration in memory"""
        for output in self.outputs:
            if output.name == output_name:
                if position is not None:
                    output.position = position
                if resolution is not None:
                    output.resolution = resolution
                if scale is not None:
                    output.scale = scale
                if transform is not None:
                    output.transform = transform
                if enabled is not None:
                    output.enabled = enabled
                return True
        return False
    
    def apply_output_config(self, output: OutputConfig) -> bool:
        """Apply output configuration using swaymsg"""
        try:
            # Build sway output command
            cmd_parts = ['swaymsg', 'output', output.name]
            
            if not output.enabled:
                cmd_parts.append('disable')
            else:
                cmd_parts.extend(['res', f"{output.resolution[0]}x{output.resolution[1]}"])
                cmd_parts.extend(['pos', str(output.position[0]), str(output.position[1])])
                cmd_parts.extend(['scale', str(output.scale)])
                if output.transform != "normal":
                    cmd_parts.extend(['transform', output.transform])
            
            result = subprocess.run(cmd_parts, capture_output=True, text=True, check=True)
            return True
            
        except subprocess.CalledProcessError as e:
            print(f"Error applying output config for {output.name}: {e}")
            return False
    
    def save_config_file(self, backup: bool = True) -> bool:
        """Save current output configurations to sway config file"""
        if not self.config_path:
            print("No config file path set")
            return False
        
        try:
            # Create backup if requested
            if backup and os.path.exists(self.config_path):
                backup_path = f"{self.config_path}.backup"
                shutil.copy2(self.config_path, backup_path)
                print(f"Created backup: {backup_path}")
            
            # Read current config or use cached content
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    content = f.read()
            else:
                content = self.config_content or ""
            
            # Remove existing output configuration section
            lines = content.split('\n')
            new_lines = []
            skip_section = False
            
            for line in lines:
                stripped = line.strip()
                
                # Check if this is the start of our output configuration section
                if stripped == "# Output configurations (updated by SwayBG+)":
                    skip_section = True
                    continue
                
                # Skip output lines and empty lines in our section
                if skip_section:
                    if stripped.startswith('output '):
                        continue
                    elif stripped == "":
                        continue
                    else:
                        # End of our section, stop skipping
                        skip_section = False
                        new_lines.append(line)
                else:
                    # Keep lines that are not part of our managed section
                    # But still remove any standalone output lines that might be from manual edits
                    if not stripped.startswith('output '):
                        new_lines.append(line)
            
            # Add updated output configurations
            new_lines.append("")
            new_lines.append("# Output configurations (updated by SwayBG+)")
            
            for output in self.outputs:
                if output.enabled:
                    output_line = (f"output {output.name} "
                                 f"res {output.resolution[0]}x{output.resolution[1]} "
                                 f"pos {output.position[0]} {output.position[1]} "
                                 f"scale {output.scale}")
                    
                    if output.transform != "normal":
                        output_line += f" transform {output.transform}"
                    
                    new_lines.append(output_line)
                else:
                    new_lines.append(f"output {output.name} disable")
            
            # Write updated config
            with open(self.config_path, 'w') as f:
                f.write('\n'.join(new_lines))
            
            print(f"Saved config to {self.config_path}")
            return True
            
        except Exception as e:
            print(f"Error saving config file: {e}")
            return False
    
    def get_total_screen_bounds(self) -> Tuple[int, int, int, int]:
        """Get the total bounds of all screens (min_x, min_y, max_x, max_y)"""
        if not self.outputs:
            return (0, 0, 1920, 1080)
        
        min_x = min(output.position[0] for output in self.outputs)
        min_y = min(output.position[1] for output in self.outputs)
        max_x = max(output.position[0] + output.resolution[0] for output in self.outputs)
        max_y = max(output.position[1] + output.resolution[1] for output in self.outputs)
        
        return (min_x, min_y, max_x, max_y)
    
    def get_total_resolution(self) -> Tuple[int, int]:
        """Get the total resolution spanning all screens"""
        min_x, min_y, max_x, max_y = self.get_total_screen_bounds()
        return (max_x - min_x, max_y - min_y)
    
    def get_available_resolutions(self, output_name: str) -> List[str]:
        """Get available resolutions for a specific output"""
        try:
            result = subprocess.run(['swaymsg', '-t', 'get_outputs'], 
                                  capture_output=True, text=True, check=True)
            outputs_data = json.loads(result.stdout)
            
            for output in outputs_data:
                if output['name'] == output_name:
                    resolutions = set()  # Use set to avoid duplicates
                    for mode in output.get('modes', []):
                        width = mode.get('width')
                        height = mode.get('height')
                        if width and height:
                            resolutions.add(f"{width}x{height}")
                    
                    # Sort resolutions by total pixels (descending)
                    sorted_resolutions = sorted(list(resolutions), 
                                              key=lambda x: int(x.split('x')[0]) * int(x.split('x')[1]), 
                                              reverse=True)
                    return sorted_resolutions
            
            return []
            
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as e:
            print(f"Error getting available resolutions for {output_name}: {e}")
            return []


if __name__ == "__main__":
    parser = SwayConfigParser()
    
    print("Current outputs:")
    current_outputs = parser.get_current_outputs()
    for output in current_outputs:
        print(f"  {output.name}: {output.resolution[0]}x{output.resolution[1]} at {output.position}")
        if output.available_modes:
            print(f"    Available modes: {output.available_modes[:5]}...")  # Show first 5
    
    print(f"\nTotal resolution: {parser.get_total_resolution()}")
    print(f"Total bounds: {parser.get_total_screen_bounds()}")
    print(f"Config path: {parser.get_config_path()}") 