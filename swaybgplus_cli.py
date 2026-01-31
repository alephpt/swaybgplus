#!/usr/bin/env python3
"""
SwayBG+ CLI - Command line interface for managing sway backgrounds
"""

import argparse
import sys
import os
from typing import List

from sway_config_parser import SwayConfigParser, OutputConfig
from background_manager import BackgroundManager


def main():
    parser = argparse.ArgumentParser(
        description="swaybg+ - Sway Background and Screen Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set stretched background across all monitors
  swaybgplus_cli.py image.jpg --mode stretched
  
  # Set fitted background on each monitor
  swaybgplus_cli.py image.jpg --mode fill
  
  # Set background with vertical monitor orientation
  swaybgplus_cli.py image.jpg --mode stretched --orientation DP-1:90
  
  # Set multiple monitor orientations
  swaybgplus_cli.py image.jpg --orientation DP-1:90 --orientation HDMI-A-1:270
  
  # Restore saved background configuration
  swaybgplus_cli.py --restore
  
  # List current outputs
  swaybgplus_cli.py --list-outputs
        """
    )
    
    parser.add_argument('image', nargs='?', help='Path to background image')
    parser.add_argument('--mode', '-m', 
                       choices=['stretched', 'fill', 'fit', 'center', 'tile'],
                       default='stretched',
                       help='Background mode (default: stretched)')
    parser.add_argument('--restore', '-r', action='store_true',
                       help='Restore saved background configuration')
    parser.add_argument('--list-outputs', '-l', action='store_true',
                       help='List current outputs')
    parser.add_argument('--config', '-c', 
                       help='Path to sway config file')
    parser.add_argument('--offset-x', type=int, default=0,
                       help='Horizontal image offset (default: 0)')
    parser.add_argument('--offset-y', type=int, default=0,
                       help='Vertical image offset (default: 0)')
    parser.add_argument('--scale', type=float, default=1.0,
                       help='Image scale factor (default: 1.0)')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up old background files')
    parser.add_argument('--orientation', '-o', action='append', default=[],
                       help='Set monitor orientation (format: OUTPUT:TRANSFORM where TRANSFORM is normal, 90, 180, 270, flipped, flipped-90, flipped-180, flipped-270). Can be used multiple times.')
    
    args = parser.parse_args()
    
    # Initialize managers
    config_parser = SwayConfigParser()
    background_manager = BackgroundManager()
    
    # Set custom config path if provided
    if args.config:
        config_parser.set_config_path(args.config)
    
    # Handle restore command
    if args.restore:
        print("Restoring saved background configuration...")
        success = background_manager.restore_background()
        if success:
            print("Background restored successfully")
        else:
            print("Failed to restore background")
            sys.exit(1)
        return
    
    # Handle cleanup command
    if args.cleanup:
        print("Cleaning up old background files...")
        background_manager.cleanup()
        print("Cleanup completed")
        return
    
    # Handle list outputs command
    if args.list_outputs:
        outputs = config_parser.get_current_outputs()
        if not outputs:
            print("No outputs found")
            return
        
        print(f"Found {len(outputs)} outputs:")
        for output in outputs:
            status = "enabled" if output.enabled else "disabled"
            print(f"  {output.name}: {output.resolution[0]}x{output.resolution[1]} "
                  f"at ({output.position[0]}, {output.position[1]}) "
                  f"scale {output.scale} transform {output.transform} [{status}]")
        return
    
    # Parse and validate orientation arguments
    orientation_map = {}
    valid_transforms = ['normal', '90', '180', '270', 'flipped', 'flipped-90', 'flipped-180', 'flipped-270']
    
    for orientation_spec in args.orientation:
        if ':' not in orientation_spec:
            print(f"Error: Invalid orientation format '{orientation_spec}'. Use OUTPUT:TRANSFORM")
            sys.exit(1)
        
        output_name, transform = orientation_spec.split(':', 1)
        if transform not in valid_transforms:
            print(f"Error: Invalid transform '{transform}'. Valid transforms: {', '.join(valid_transforms)}")
            sys.exit(1)
        
        orientation_map[output_name] = transform
    
    # Get current outputs
    outputs = config_parser.get_current_outputs()
    if not outputs:
        print("Error: No outputs found")
        sys.exit(1)
    
    # Apply orientation changes if specified
    if orientation_map:
        print("Applying orientation changes...")
        for output in outputs:
            if output.name in orientation_map:
                new_transform = orientation_map[output.name]
                print(f"  {output.name}: {output.transform} -> {new_transform}")
                config_parser.update_output_config(output.name, transform=new_transform)
                if not config_parser.apply_output_config(output):
                    print(f"Error: Failed to apply orientation for {output.name}")
                    sys.exit(1)
        
        # Refresh outputs after orientation changes
        outputs = config_parser.get_current_outputs()
    
    # Handle orientation-only mode (no background setting)
    if not args.image and orientation_map:
        print("Orientation changes applied successfully")
        return
    
    # Require image path for background setting
    if not args.image:
        parser.error("Image path is required unless using --restore, --list-outputs, --cleanup, or orientation-only mode")
    
    # Check if image exists
    if not os.path.exists(args.image):
        print(f"Error: Image file not found: {args.image}")
        sys.exit(1)
    
    print(f"Setting background: {args.image}")
    print(f"Mode: {args.mode}")
    print(f"Outputs: {', '.join(output.name for output in outputs)}")
    
    if args.offset_x != 0 or args.offset_y != 0:
        print(f"Image offset: ({args.offset_x}, {args.offset_y})")
    
    if args.scale != 1.0:
        print(f"Image scale: {args.scale}")
    
    # Apply background
    image_offset = (args.offset_x, args.offset_y)
    
    if args.mode == 'stretched':
        success = background_manager.set_background_stretched(
            args.image, outputs, image_offset, args.scale
        )
    else:
        success = background_manager.set_background_fitted(
            args.image, outputs, args.mode, image_offset, args.scale
        )
    
    if success:
        print("Background applied successfully")
        print(f"Configuration saved to: {background_manager.config_dir}")
    else:
        print("Failed to apply background")
        sys.exit(1)


if __name__ == "__main__":
    main() 