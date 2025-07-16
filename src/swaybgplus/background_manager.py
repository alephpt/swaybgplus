#!/usr/bin/env python3
"""
Background manager for stretching images across multiple sway outputs
"""

import os
import subprocess
import shutil
from PIL import Image, ImageOps
from typing import List, Tuple, Optional
from swaybgplus.sway_config_parser import OutputConfig, SwayConfigParser


class BackgroundManager:
    """Manages background images for sway outputs"""
    
    def __init__(self):
        self.parser = SwayConfigParser()
        self.config_dir = os.path.expanduser("~/.config/sway/backgrounds")
        self.ensure_config_dir()
    
    def ensure_config_dir(self):
        """Ensure the backgrounds directory exists"""
        os.makedirs(self.config_dir, exist_ok=True)
    
    def get_permanent_image_path(self, original_path: str, suffix: str = "") -> str:
        """Get permanent path for saving background image"""
        filename = os.path.basename(original_path)
        name, ext = os.path.splitext(filename)
        if suffix:
            filename = f"{name}_{suffix}{ext}"
        return os.path.join(self.config_dir, filename)
    
    def save_background_config(self, image_path: str, mode: str, image_offset: Tuple[int, int] = (0, 0), image_scale: float = 1.0):
        """Save background configuration for persistence"""
        config = {
            'image_path': image_path,
            'mode': mode,
            'image_offset': image_offset,
            'image_scale': image_scale
        }
        
        config_file = os.path.join(self.config_dir, "current_config.json")
        try:
            import json
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Error saving background config: {e}")
    
    def load_background_config(self) -> Optional[dict]:
        """Load saved background configuration"""
        config_file = os.path.join(self.config_dir, "current_config.json")
        if os.path.exists(config_file):
            try:
                import json
                with open(config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading background config: {e}")
        return None
    
    def create_startup_script(self):
        """Create a startup script to restore backgrounds on boot"""
        script_content = f'''#!/bin/bash
# SwayBG+ startup script - restores backgrounds on sway startup

CONFIG_FILE="{os.path.join(self.config_dir, 'current_config.json')}"

if [ -f "$CONFIG_FILE" ]; then
    # Kill existing swaybg processes
    pkill swaybg 2>/dev/null || true
    
    # Wait a moment for processes to die
    sleep 0.5
    
    # Restore background using our CLI
    python3 "{os.path.dirname(os.path.abspath(__file__))}/swaybgplus_cli.py" --restore
fi
'''
        
        script_path = os.path.join(self.config_dir, "restore_background.sh")
        try:
            with open(script_path, 'w') as f:
                f.write(script_content)
            os.chmod(script_path, 0o755)  # Make executable
            
            # Add to sway config if not already present
            self.add_to_sway_config(script_path)
            
        except Exception as e:
            print(f"Error creating startup script: {e}")
    
    def add_to_sway_config(self, script_path: str):
        """Add background restoration to sway config"""
        sway_config = self.parser.get_config_path()
        if not sway_config:
            return
        
        exec_line = f"exec {script_path}"
        
        try:
            # Check if already in config
            with open(sway_config, 'r') as f:
                content = f.read()
            
            if "SwayBG+ startup" in content or script_path in content:
                return  # Already added
            
            # Add to config
            with open(sway_config, 'a') as f:
                f.write(f"\n# SwayBG+ startup - restore backgrounds\n")
                f.write(f"{exec_line}\n")
            
            print(f"Added background restoration to sway config")
            
        except Exception as e:
            print(f"Error adding to sway config: {e}")
    
    def get_effective_resolution(self, output: OutputConfig) -> Tuple[int, int]:
        """Get the effective resolution accounting for transform/rotation"""
        width, height = output.resolution
        
        # For 90 and 270 degree rotations, swap width and height
        if output.transform in ['90', '270', 'flipped-90', 'flipped-270']:
            return (height, width)
        else:
            return (width, height)
    
    def create_stretched_background(self, image_path: str, outputs: List[OutputConfig], 
                                  image_offset: Tuple[int, int] = (0, 0), image_scale: float = 1.0) -> str:
        """Create a single stretched background image spanning all outputs"""
        if not outputs:
            raise ValueError("No outputs provided")
        
        # Load the source image
        try:
            source_image = Image.open(image_path)
        except Exception as e:
            raise ValueError(f"Could not load image: {e}")
        
        # Calculate total canvas size using effective resolutions
        min_x = min(output.position[0] for output in outputs)
        min_y = min(output.position[1] for output in outputs)
        
        # Use effective resolution that accounts for transforms
        max_x = max(output.position[0] + self.get_effective_resolution(output)[0] for output in outputs)
        max_y = max(output.position[1] + self.get_effective_resolution(output)[1] for output in outputs)
        
        canvas_width = max_x - min_x
        canvas_height = max_y - min_y
        
        # Create a new canvas
        canvas = Image.new('RGB', (canvas_width, canvas_height), (0, 0, 0))
        
        # Apply manual scaling and positioning
        scaled_width = int(source_image.width * image_scale)
        scaled_height = int(source_image.height * image_scale)
        resized_image = source_image.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
        
        # Calculate position with offset
        paste_x = (canvas_width - scaled_width) // 2 + image_offset[0]
        paste_y = (canvas_height - scaled_height) // 2 + image_offset[1]
        
        # Handle tiling if image is smaller than canvas
        if scaled_width < canvas_width or scaled_height < canvas_height:
            # Tile the image
            for y in range(paste_y, canvas_height, scaled_height):
                for x in range(paste_x, canvas_width, scaled_width):
                    canvas.paste(resized_image, (x, y))
        else:
            # Crop if image is larger than canvas
            crop_x = max(0, -paste_x)
            crop_y = max(0, -paste_y)
            crop_width = min(scaled_width - crop_x, canvas_width - max(0, paste_x))
            crop_height = min(scaled_height - crop_y, canvas_height - max(0, paste_y))
            
            if crop_width > 0 and crop_height > 0:
                cropped_image = resized_image.crop((crop_x, crop_y, crop_x + crop_width, crop_y + crop_height))
                canvas.paste(cropped_image, (max(0, paste_x), max(0, paste_y)))
        
        # Save to permanent location
        permanent_path = self.get_permanent_image_path(image_path, "stretched")
        canvas.save(permanent_path, 'PNG')
        
        return permanent_path
    
    def create_individual_backgrounds(self, image_path: str, outputs: List[OutputConfig], 
                                    image_offset: Tuple[int, int] = (0, 0), image_scale: float = 1.0) -> List[Tuple[str, str]]:
        """Create individual background images for each output"""
        if not outputs:
            raise ValueError("No outputs provided")
        
        # Load the source image
        try:
            source_image = Image.open(image_path)
        except Exception as e:
            raise ValueError(f"Could not load image: {e}")
        
        # Calculate total canvas size using effective resolutions
        min_x = min(output.position[0] for output in outputs)
        min_y = min(output.position[1] for output in outputs)
        
        # Use effective resolution that accounts for transforms
        max_x = max(output.position[0] + self.get_effective_resolution(output)[0] for output in outputs)
        max_y = max(output.position[1] + self.get_effective_resolution(output)[1] for output in outputs)
        
        canvas_width = max_x - min_x
        canvas_height = max_y - min_y
        
        # Apply manual scaling
        scaled_width = int(source_image.width * image_scale)
        scaled_height = int(source_image.height * image_scale)
        resized_image = source_image.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
        
        # Create individual images for each output
        output_images = []
        
        for output in outputs:
            # Get effective resolution for this output (accounts for rotation)
            effective_width, effective_height = self.get_effective_resolution(output)
            
            # Calculate crop area for this output using effective resolution
            crop_x = output.position[0] - min_x
            crop_y = output.position[1] - min_y
            crop_width = effective_width
            crop_height = effective_height
            
            # Create canvas for this output using effective resolution
            output_canvas = Image.new('RGB', (crop_width, crop_height), (0, 0, 0))
            
            # Calculate where to place the image on this output
            img_x = (canvas_width - scaled_width) // 2 + image_offset[0] - crop_x
            img_y = (canvas_height - scaled_height) // 2 + image_offset[1] - crop_y
            
            # Paste the image (with proper clipping)
            if img_x < crop_width and img_y < crop_height and img_x + scaled_width > 0 and img_y + scaled_height > 0:
                # Calculate the portion of the image that fits on this output
                src_x = max(0, -img_x)
                src_y = max(0, -img_y)
                dst_x = max(0, img_x)
                dst_y = max(0, img_y)
                
                copy_width = min(scaled_width - src_x, crop_width - dst_x)
                copy_height = min(scaled_height - src_y, crop_height - dst_y)
                
                if copy_width > 0 and copy_height > 0:
                    cropped_portion = resized_image.crop((src_x, src_y, src_x + copy_width, src_y + copy_height))
                    output_canvas.paste(cropped_portion, (dst_x, dst_y))
            
            # Save to permanent location
            permanent_path = self.get_permanent_image_path(image_path, output.name)
            output_canvas.save(permanent_path, 'PNG')
            
            output_images.append((output.name, permanent_path))
        
        return output_images
    
    def set_background_stretched(self, image_path: str, outputs: List[OutputConfig] = None, 
                               image_offset: Tuple[int, int] = (0, 0), image_scale: float = 1.0) -> bool:
        """Set a stretched background across all outputs"""
        if outputs is None:
            outputs = self.parser.get_current_outputs()
        
        if not outputs:
            print("No outputs available")
            return False
        
        try:
            # Create individual background images
            output_images = self.create_individual_backgrounds(image_path, outputs, image_offset, image_scale)
            
            # Set background for each output using swaybg
            for output_name, bg_image_path in output_images:
                self._set_output_background(output_name, bg_image_path)
            
            # Save configuration for persistence
            self.save_background_config(image_path, "stretched", image_offset, image_scale)
            
            # Create startup script
            self.create_startup_script()
            
            return True
            
        except Exception as e:
            print(f"Error setting background: {e}")
            return False
    
    def set_background_fitted(self, image_path: str, outputs: List[OutputConfig] = None, 
                            mode: str = "fill", image_offset: Tuple[int, int] = (0, 0), 
                            image_scale: float = 1.0) -> bool:
        """Set a fitted background on each output individually"""
        if outputs is None:
            outputs = self.parser.get_current_outputs()
        
        if not outputs:
            print("No outputs available")
            return False
        
        try:
            # Copy original image to permanent location
            permanent_image = self.get_permanent_image_path(image_path, "original")
            shutil.copy2(image_path, permanent_image)
            
            # Set the same image on all outputs with the specified mode
            for output in outputs:
                self._set_output_background(output.name, permanent_image, mode)
            
            # Save configuration for persistence
            self.save_background_config(image_path, mode, image_offset, image_scale)
            
            # Create startup script
            self.create_startup_script()
            
            return True
            
        except Exception as e:
            print(f"Error setting background: {e}")
            return False
    
    def restore_background(self) -> bool:
        """Restore background from saved configuration"""
        config = self.load_background_config()
        if not config:
            print("No saved background configuration found")
            return False
        
        image_path = config.get('image_path')
        mode = config.get('mode', 'stretched')
        image_offset = tuple(config.get('image_offset', [0, 0]))
        image_scale = config.get('image_scale', 1.0)
        
        if not image_path or not os.path.exists(image_path):
            print(f"Saved image path not found: {image_path}")
            return False
        
        if mode == "stretched":
            return self.set_background_stretched(image_path, None, image_offset, image_scale)
        else:
            return self.set_background_fitted(image_path, None, mode, image_offset, image_scale)
    
    def _set_output_background(self, output_name: str, image_path: str, mode: str = "stretch"):
        """Set background for a specific output using swaybg"""
        try:
            # Kill any existing swaybg processes for this output
            subprocess.run(['pkill', '-f', f'swaybg.*{output_name}'], 
                         capture_output=True, check=False)
            
            # Start new swaybg process
            cmd = ['swaybg', '-o', output_name, '-i', image_path, '-m', mode]
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            
        except Exception as e:
            print(f"Error setting background for {output_name}: {e}")
    
    def kill_all_backgrounds(self):
        """Kill all swaybg processes"""
        try:
            subprocess.run(['pkill', 'swaybg'], capture_output=True, check=False)
        except Exception as e:
            print(f"Error killing swaybg processes: {e}")
    
    def cleanup(self):
        """Clean up old background files (keep last 5)"""
        try:
            if not os.path.exists(self.config_dir):
                return
            
            # Get all background files
            files = []
            for f in os.listdir(self.config_dir):
                if f.endswith(('.png', '.jpg', '.jpeg')) and f != "current_config.json":
                    full_path = os.path.join(self.config_dir, f)
                    files.append((full_path, os.path.getmtime(full_path)))
            
            # Sort by modification time, keep newest 5
            files.sort(key=lambda x: x[1], reverse=True)
            for file_path, _ in files[5:]:
                try:
                    os.unlink(file_path)
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        self.cleanup()


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python background_manager.py <image_path> [mode]")
        print("Modes: stretched, fitted")
        print("       python background_manager.py --restore")
        sys.exit(1)
    
    manager = BackgroundManager()
    
    if sys.argv[1] == "--restore":
        success = manager.restore_background()
    else:
        image_path = sys.argv[1]
        mode = sys.argv[2] if len(sys.argv) > 2 else "stretched"
        
        if mode == "stretched":
            success = manager.set_background_stretched(image_path)
        else:
            success = manager.set_background_fitted(image_path)
    
    if success:
        print("Background applied successfully")
    else:
        print("Failed to apply background")
        sys.exit(1) 
