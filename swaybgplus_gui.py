#!/usr/bin/env python3
"""
SwayBG+ GUI - A graphical interface for managing sway backgrounds across multiple monitors
"""

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GdkPixbuf', '2.0')

from gi.repository import Gtk, GdkPixbuf, Gdk, GLib, Gio, GObject
import os
import sys
import threading
from typing import List, Optional, Tuple
from PIL import Image
import cairo
import subprocess

from sway_config_parser import SwayConfigParser, OutputConfig
from background_manager import BackgroundManager


class MonitorWidget(Gtk.DrawingArea):
    """Widget to display and arrange monitors"""
    
    __gsignals__ = {
        'output-selected': (GObject.SignalFlags.RUN_FIRST, None, (object,)),
        'output-changed': (GObject.SignalFlags.RUN_FIRST, None, (object,))
    }
    
    def __init__(self, outputs: List[OutputConfig]):
        super().__init__()
        self.outputs = outputs
        self.scale_factor = 0.1  # Scale down monitors for display
        self.selected_output = None
        self.dragging = False
        self.dragging_image = False  # For dragging image
        self.resizing_image = False  # For resizing image
        self.drag_start = (0, 0)
        self.preview_image = None  # Preview image to show on monitors
        self.preview_mode = "stretched"  # Background mode for preview
        self.image_offset = (0, 0)  # Image offset for repositioning
        self.image_scale = 1.0  # Image scale factor for manual scaling
        self.resize_handle = None  # Which resize handle is being dragged
        
        self.set_size_request(800, 600)
        self.set_can_focus(True)
        
        # Connect drawing and mouse events
        self.connect('draw', self.on_draw)
        self.connect('button-press-event', self.on_button_press)
        self.connect('button-release-event', self.on_button_release)
        self.connect('motion-notify-event', self.on_motion)
        self.connect('key-press-event', self.on_key_press)
        
        # Enable mouse and keyboard events
        self.set_events(Gdk.EventMask.BUTTON_PRESS_MASK | 
                       Gdk.EventMask.BUTTON_RELEASE_MASK |
                       Gdk.EventMask.POINTER_MOTION_MASK |
                       Gdk.EventMask.KEY_PRESS_MASK)
        
        self.update_scale()
    
    def set_preview_image(self, image_path: str):
        """Set preview image to display on monitors"""
        try:
            self.preview_image = Image.open(image_path)
            self.queue_draw()
        except Exception as e:
            print(f"Error loading preview image: {e}")
            self.preview_image = None
    
    def clear_preview(self):
        """Clear preview image"""
        self.preview_image = None
        self.queue_draw()
    
    def get_effective_resolution(self, output: OutputConfig) -> Tuple[int, int]:
        """Get the effective resolution accounting for transform/rotation"""
        width, height = output.resolution
        
        # For 90 and 270 degree rotations, swap width and height
        if output.transform in ['90', '270', 'flipped-90', 'flipped-270']:
            return (height, width)
        else:
            return (width, height)
    
    def update_scale(self):
        """Update scale factor based on monitor layout"""
        if not self.outputs:
            return
        
        # Find total bounds using effective resolutions
        min_x = min(output.position[0] for output in self.outputs)
        min_y = min(output.position[1] for output in self.outputs)
        
        # Use effective resolution for max calculations
        max_x = max(output.position[0] + self.get_effective_resolution(output)[0] for output in self.outputs)
        max_y = max(output.position[1] + self.get_effective_resolution(output)[1] for output in self.outputs)
        
        total_width = max_x - min_x
        total_height = max_y - min_y
        
        # Calculate scale to fit in widget
        widget_width = 750
        widget_height = 550
        
        scale_x = widget_width / total_width if total_width > 0 else 0.1
        scale_y = widget_height / total_height if total_height > 0 else 0.1
        
        self.scale_factor = min(scale_x, scale_y, 0.3)  # Cap at 0.3 for readability
    
    def on_draw(self, widget, cr):
        """Draw the monitors"""
        if not self.outputs:
            return False
        
        # Clear background
        cr.set_source_rgb(0.2, 0.2, 0.2)
        cr.paint()
        
        # Find offset to center the layout using effective resolutions
        min_x = min(output.position[0] for output in self.outputs)
        min_y = min(output.position[1] for output in self.outputs)
        
        # Use effective resolution for max calculations
        max_x = max(output.position[0] + self.get_effective_resolution(output)[0] for output in self.outputs)
        max_y = max(output.position[1] + self.get_effective_resolution(output)[1] for output in self.outputs)
        
        widget_width = widget.get_allocated_width()
        widget_height = widget.get_allocated_height()
        
        offset_x = (widget_width - (max_x - min_x) * self.scale_factor) / 2
        offset_y = (widget_height - (max_y - min_y) * self.scale_factor) / 2
        
        # Prepare preview image if available
        preview_surface = None
        if self.preview_image:
            try:
                # Always use the original image for preview surface creation
                # The scaling and positioning will be handled in the drawing logic
                preview_resized = self.preview_image
                
                # Convert to RGBA format for Cairo
                if preview_resized.mode != 'RGBA':
                    preview_resized = preview_resized.convert('RGBA')
                
                # Create Cairo surface from image data
                width, height = preview_resized.size
                stride = cairo.ImageSurface.format_stride_for_width(cairo.FORMAT_ARGB32, width)
                
                # Convert PIL image to Cairo-compatible format (BGRA)
                img_data = bytearray(preview_resized.tobytes('raw', 'BGRa'))
                
                preview_surface = cairo.ImageSurface.create_for_data(
                    img_data, cairo.FORMAT_ARGB32, width, height, stride
                )
            except Exception as e:
                print(f"Error creating preview surface: {e}")
                preview_surface = None
        
        # Draw each monitor
        for output in self.outputs:
            # Use effective resolution for drawing
            effective_width, effective_height = self.get_effective_resolution(output)
            
            x = (output.position[0] - min_x) * self.scale_factor + offset_x
            y = (output.position[1] - min_y) * self.scale_factor + offset_y
            width = effective_width * self.scale_factor
            height = effective_height * self.scale_factor
            
            # Draw monitor background color first
            if output == self.selected_output:
                cr.set_source_rgb(0.3, 0.6, 1.0)  # Blue for selected
            else:
                cr.set_source_rgb(0.6, 0.6, 0.6)  # Gray for normal
            
            # Draw monitor rectangle background
            cr.rectangle(x, y, width, height)
            cr.fill()
            
            # Draw preview image if available (overlay on top of background)
            if preview_surface:
                # Save the current Cairo state before any transformations
                cr.save()
                
                # Set clipping region to monitor bounds (in original coordinate system)
                cr.rectangle(x, y, width, height)
                cr.clip()
                
                if self.preview_mode == "stretched":
                    # For stretched mode, we need to match the background manager's logic exactly
                    # Calculate virtual screen dimensions (same as background manager)
                    virtual_width = max_x - min_x
                    virtual_height = max_y - min_y
                    
                    # Get image dimensions
                    img_width, img_height = preview_surface.get_width(), preview_surface.get_height()
                    
                    # Apply manual scaling (same as background manager)
                    scaled_width = int(img_width * self.image_scale)
                    scaled_height = int(img_height * self.image_scale)
                    
                    # Calculate where to place the image on the virtual canvas (same as background manager)
                    # This matches: img_x = (canvas_width - scaled_width) // 2 + image_offset[0] - crop_x
                    virtual_img_x = (virtual_width - scaled_width) // 2 + self.image_offset[0]
                    virtual_img_y = (virtual_height - scaled_height) // 2 + self.image_offset[1]
                    
                    # Position of this monitor in the virtual screen (using effective resolution)
                    monitor_x_in_virtual = output.position[0] - min_x
                    monitor_y_in_virtual = output.position[1] - min_y
                    
                    # Calculate which part of the scaled image appears on this monitor
                    # This matches the background manager's cropping logic
                    img_x_on_monitor = virtual_img_x - monitor_x_in_virtual
                    img_y_on_monitor = virtual_img_y - monitor_y_in_virtual
                    
                    # Only draw if the image intersects with this monitor
                    if (img_x_on_monitor < effective_width and img_y_on_monitor < effective_height and 
                        img_x_on_monitor + scaled_width > 0 and img_y_on_monitor + scaled_height > 0):
                        
                        # Calculate the portion of the image that fits on this monitor
                        src_x = max(0, -img_x_on_monitor)
                        src_y = max(0, -img_y_on_monitor)
                        dst_x = max(0, img_x_on_monitor)
                        dst_y = max(0, img_y_on_monitor)
                        
                        copy_width = min(scaled_width - src_x, effective_width - dst_x)
                        copy_height = min(scaled_height - src_y, effective_height - dst_y)
                        
                        if copy_width > 0 and copy_height > 0:
                            # Apply transformations: translate to monitor position, scale for display
                            cr.translate(x, y)
                            cr.scale(self.scale_factor, self.scale_factor)
                            
                            # Scale the image to match the manual scaling
                            cr.scale(self.image_scale, self.image_scale)
                            
                            # Position the image so the correct portion shows on this monitor
                            # We need to account for the source cropping
                            cr.set_source_surface(preview_surface, 
                                                (dst_x - src_x) / self.image_scale, 
                                                (dst_y - src_y) / self.image_scale)
                            
                            # Set clipping to only show the portion that should be visible
                            cr.rectangle(dst_x / self.image_scale, dst_y / self.image_scale, 
                                       copy_width / self.image_scale, copy_height / self.image_scale)
                            cr.clip()
                            
                            cr.paint_with_alpha(0.9)
                
                elif self.preview_mode == "fill":
                    # Scale image to fill monitor, maintaining aspect ratio
                    img_width, img_height = preview_surface.get_width(), preview_surface.get_height()
                    monitor_width, monitor_height = effective_width, effective_height
                    
                    scale_x = monitor_width / img_width
                    scale_y = monitor_height / img_height
                    scale = max(scale_x, scale_y) * self.image_scale  # Apply manual scale
                    
                    scaled_width = img_width * scale
                    scaled_height = img_height * scale
                    
                    # Center the scaled image
                    offset_x_calc = (monitor_width - scaled_width) / 2 - self.image_offset[0]
                    offset_y_calc = (monitor_height - scaled_height) / 2 - self.image_offset[1]
                    
                    cr.translate(x, y)
                    cr.scale(self.scale_factor, self.scale_factor)
                    cr.scale(scale, scale)
                    cr.set_source_surface(preview_surface, offset_x_calc / scale, offset_y_calc / scale)
                    cr.paint_with_alpha(0.9)
                    
                elif self.preview_mode == "fit":
                    # Scale image to fit monitor, maintaining aspect ratio
                    img_width, img_height = preview_surface.get_width(), preview_surface.get_height()
                    monitor_width, monitor_height = effective_width, effective_height
                    
                    scale_x = monitor_width / img_width
                    scale_y = monitor_height / img_height
                    scale = min(scale_x, scale_y) * self.image_scale  # Apply manual scale
                    
                    scaled_width = img_width * scale
                    scaled_height = img_height * scale
                    
                    # Center the scaled image
                    offset_x_calc = (monitor_width - scaled_width) / 2 - self.image_offset[0]
                    offset_y_calc = (monitor_height - scaled_height) / 2 - self.image_offset[1]
                    
                    cr.translate(x, y)
                    cr.scale(self.scale_factor, self.scale_factor)
                    cr.scale(scale, scale)
                    cr.set_source_surface(preview_surface, offset_x_calc / scale, offset_y_calc / scale)
                    cr.paint_with_alpha(0.9)
                    
                elif self.preview_mode == "center":
                    # Center image with manual scaling
                    img_width, img_height = preview_surface.get_width(), preview_surface.get_height()
                    monitor_width, monitor_height = effective_width, effective_height
                    
                    # Apply manual scaling
                    scaled_width = img_width * self.image_scale
                    scaled_height = img_height * self.image_scale
                    
                    offset_x_calc = (monitor_width - scaled_width) / 2 - self.image_offset[0]
                    offset_y_calc = (monitor_height - scaled_height) / 2 - self.image_offset[1]
                    
                    cr.translate(x, y)
                    cr.scale(self.scale_factor, self.scale_factor)
                    cr.scale(self.image_scale, self.image_scale)
                    cr.set_source_surface(preview_surface, offset_x_calc / self.image_scale, offset_y_calc / self.image_scale)
                    cr.paint_with_alpha(0.9)
                    
                elif self.preview_mode == "tile":
                    # Tile image across monitor with manual scaling
                    img_width, img_height = preview_surface.get_width(), preview_surface.get_height()
                    monitor_width, monitor_height = effective_width, effective_height
                    
                    cr.translate(x, y)
                    cr.scale(self.scale_factor, self.scale_factor)
                    cr.scale(self.image_scale, self.image_scale)  # Apply manual scale to tiles
                    
                    # Create tiled pattern
                    pattern = cairo.SurfacePattern(preview_surface)
                    pattern.set_extend(cairo.Extend.REPEAT)
                    
                    # Apply image offset (scaled for the tile scaling)
                    matrix = cairo.Matrix()
                    matrix.translate(self.image_offset[0] / self.image_scale, self.image_offset[1] / self.image_scale)
                    pattern.set_matrix(matrix)
                    
                    cr.set_source(pattern)
                    cr.rectangle(0, 0, monitor_width / self.image_scale, monitor_height / self.image_scale)
                    cr.fill()
                
                # Restore the Cairo state to undo all transformations
                cr.restore()
            
            # Always draw border (on top of everything)
            if output == self.selected_output:
                cr.set_source_rgb(1.0, 1.0, 0.0)  # Yellow border for selected
                cr.set_line_width(3)
            else:
                cr.set_source_rgb(0.8, 0.8, 0.8)  # Light gray border for normal
                cr.set_line_width(2)
            
            cr.rectangle(x, y, width, height)
            cr.stroke()
            
            # Draw monitor label
            cr.set_source_rgb(1, 1, 1)  # White text
            cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            cr.set_font_size(12)
            
            # Include transform information if not normal
            transform_text = f" ({output.transform})" if output.transform != "normal" else ""
            text = f"{output.name}\n{effective_width}x{effective_height}{transform_text}"
            text_lines = text.split('\n')
            
            # Calculate text position to center in monitor
            text_height = len(text_lines) * 15  # Rough line height
            text_y = y + (height - text_height) / 2 + 15  # Center vertically
            
            for i, line in enumerate(text_lines):
                text_extents = cr.text_extents(line)
                text_x = x + (width - text_extents.width) / 2  # Center horizontally
                cr.move_to(text_x, text_y + i * 15)
                cr.show_text(line)
        
        # Draw resize handles if image is loaded
        if self.preview_image:
            self.draw_resize_handles(cr)
        
        return True
    
    def on_button_press(self, widget, event):
        """Handle mouse button press"""
        if event.button == 1:  # Left click
            # First check for monitor selection (highest priority)
            clicked_output = self.get_output_at_position(event.x, event.y)
            if clicked_output:
                # Check if clicking on resize handle first
                if self.preview_image:
                    resize_handle = self.get_resize_handle_at_position(event.x, event.y)
                    if resize_handle:
                        self.resizing_image = True
                        self.resize_handle = resize_handle
                        self.drag_start = (event.x, event.y)
                        return True
                    
                    # Check if clicking on image for dragging (only if within monitor bounds)
                    if self.is_point_in_image(event.x, event.y):
                        self.dragging_image = True
                        self.drag_start = (event.x, event.y)
                        return True
                
                # Otherwise, select and potentially drag the monitor
                self.selected_output = clicked_output
                self.dragging = True
                self.drag_start = (event.x, event.y)
                self.queue_draw()
                # Emit signal for output selection
                self.emit('output-selected', clicked_output)
                return True
        return False
    
    def on_button_release(self, widget, event):
        """Handle mouse button release"""
        if event.button == 1:
            self.dragging = False
            self.dragging_image = False
            self.resizing_image = False
            self.resize_handle = None
        return False
    
    def on_motion(self, widget, event):
        """Handle mouse motion"""
        if self.resizing_image and self.resize_handle:
            # Handle image resizing
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]
            
            # Calculate scale change based on resize handle and movement
            movement_factor = 0.005  # Sensitivity factor
            
            if self.resize_handle in ['bottom-right']:
                # Bottom-right: positive movement increases size
                scale_change = 1.0 + (dx + dy) * movement_factor
            elif self.resize_handle in ['top-left']:
                # Top-left: negative movement increases size
                scale_change = 1.0 + (-dx - dy) * movement_factor
            elif self.resize_handle in ['bottom-left']:
                # Bottom-left: left-down movement increases size
                scale_change = 1.0 + (-dx + dy) * movement_factor
            elif self.resize_handle in ['top-right']:
                # Top-right: right-up movement increases size
                scale_change = 1.0 + (dx - dy) * movement_factor
            else:
                scale_change = 1.0
            
            # Apply scale change
            new_scale = self.image_scale * scale_change
            self.image_scale = max(0.1, min(5.0, new_scale))
            
            self.drag_start = (event.x, event.y)
            self.queue_draw()
            return True
            
        elif self.dragging_image:
            # Handle image dragging - fix inverse direction
            dx = event.x - self.drag_start[0]
            dy = event.y - self.drag_start[1]
            
            # Convert screen movement to image offset (correct direction)
            # Positive dx should move image right, positive dy should move image down
            offset_scale = 1.0 / self.scale_factor
            self.image_offset = (
                self.image_offset[0] + dx * offset_scale,
                self.image_offset[1] + dy * offset_scale
            )
            
            self.drag_start = (event.x, event.y)
            self.queue_draw()
            return True
            
        elif self.dragging and self.selected_output:
            # Handle monitor dragging
            dx = (event.x - self.drag_start[0]) / self.scale_factor
            dy = (event.y - self.drag_start[1]) / self.scale_factor
            
            # Update output position
            new_x = int(self.selected_output.position[0] + dx)
            new_y = int(self.selected_output.position[1] + dy)
            
            # Snap to grid (optional)
            new_x = (new_x // 10) * 10
            new_y = (new_y // 10) * 10
            
            self.selected_output.position = (new_x, new_y)
            
            self.drag_start = (event.x, event.y)
            self.queue_draw()
            
            # Emit signal for position change
            self.emit('output-changed', self.selected_output)
            
            return True
        return False
    
    def on_key_press(self, widget, event):
        """Handle keyboard events"""
        if event.keyval == Gdk.KEY_r and event.state & Gdk.ModifierType.CONTROL_MASK:
            # Ctrl+R to reset image position and scale
            self.reset_image_position()
            return True
        return False
    
    def get_output_at_position(self, x, y) -> Optional[OutputConfig]:
        """Get output at the given screen position"""
        if not self.outputs:
            return None
        
        min_x = min(output.position[0] for output in self.outputs)
        min_y = min(output.position[1] for output in self.outputs)
        
        widget_width = self.get_allocated_width()
        widget_height = self.get_allocated_height()
        
        offset_x = (widget_width - (max(output.position[0] + output.resolution[0] for output in self.outputs) - min_x) * self.scale_factor) / 2
        offset_y = (widget_height - (max(output.position[1] + output.resolution[1] for output in self.outputs) - min_y) * self.scale_factor) / 2
        
        for output in self.outputs:
            output_x = (output.position[0] - min_x) * self.scale_factor + offset_x
            output_y = (output.position[1] - min_y) * self.scale_factor + offset_y
            output_width = output.resolution[0] * self.scale_factor
            output_height = output.resolution[1] * self.scale_factor
            
            if (output_x <= x <= output_x + output_width and 
                output_y <= y <= output_y + output_height):
                return output
        
        return None
    
    def set_preview_mode(self, mode: str):
        """Set the background mode for preview"""
        self.preview_mode = mode.lower()
        self.queue_draw()
    
    def reset_image_position(self):
        """Reset image position and scale to defaults"""
        self.image_offset = (0, 0)
        self.image_scale = 1.0
        self.queue_draw()

    def get_image_bounds(self):
        """Get the bounds of the image preview in screen coordinates"""
        if not self.preview_image or not self.outputs:
            return None
        
        # For now, use the first output as reference for image bounds
        # In stretched mode, this represents the virtual screen
        output = self.outputs[0]
        
        min_x = min(output.position[0] for output in self.outputs)
        min_y = min(output.position[1] for output in self.outputs)
        
        widget_width = self.get_allocated_width()
        widget_height = self.get_allocated_height()
        
        offset_x = (widget_width - (max(output.position[0] + output.resolution[0] for output in self.outputs) - min_x) * self.scale_factor) / 2
        offset_y = (widget_height - (max(output.position[1] + output.resolution[1] for output in self.outputs) - min_y) * self.scale_factor) / 2
        
        # Calculate image bounds based on mode
        if self.preview_mode == "stretched":
            # Image spans entire virtual screen
            max_x = max(output.position[0] + output.resolution[0] for output in self.outputs)
            max_y = max(output.position[1] + output.resolution[1] for output in self.outputs)
            virtual_width = max_x - min_x
            virtual_height = max_y - min_y
            
            x = offset_x
            y = offset_y
            width = virtual_width * self.scale_factor
            height = virtual_height * self.scale_factor
        else:
            # Use first output as reference
            x = (output.position[0] - min_x) * self.scale_factor + offset_x
            y = (output.position[1] - min_y) * self.scale_factor + offset_y
            width = output.resolution[0] * self.scale_factor
            height = output.resolution[1] * self.scale_factor
        
        return (x, y, width, height)
    
    def draw_resize_handles(self, cr):
        """Draw resize handles around the image"""
        bounds = self.get_image_bounds()
        if not bounds:
            return
        
        x, y, width, height = bounds
        handle_size = 12  # Increased size for better visibility
        
        # Draw semi-transparent overlay border
        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.set_line_width(2)
        cr.rectangle(x, y, width, height)
        cr.stroke()
        
        # Draw corner handles with better visibility
        handles = [
            (x - handle_size/2, y - handle_size/2),  # top-left
            (x + width - handle_size/2, y - handle_size/2),  # top-right
            (x - handle_size/2, y + height - handle_size/2),  # bottom-left
            (x + width - handle_size/2, y + height - handle_size/2),  # bottom-right
        ]
        
        # Draw handle backgrounds (white with border)
        for hx, hy in handles:
            # White fill
            cr.set_source_rgba(1, 1, 1, 0.9)
            cr.rectangle(hx, hy, handle_size, handle_size)
            cr.fill()
            
            # Dark border
            cr.set_source_rgba(0, 0, 0, 0.8)
            cr.set_line_width(1)
            cr.rectangle(hx, hy, handle_size, handle_size)
            cr.stroke()
    
    def get_resize_handle_at_position(self, x, y):
        """Get which resize handle is at the given position"""
        bounds = self.get_image_bounds()
        if not bounds:
            return None
        
        bx, by, width, height = bounds
        handle_size = 12  # Match the increased size
        
        handles = {
            'top-left': (bx - handle_size/2, by - handle_size/2),
            'top-right': (bx + width - handle_size/2, by - handle_size/2),
            'bottom-left': (bx - handle_size/2, by + height - handle_size/2),
            'bottom-right': (bx + width - handle_size/2, by + height - handle_size/2),
        }
        
        for handle_name, (hx, hy) in handles.items():
            if (hx <= x <= hx + handle_size and 
                hy <= y <= hy + handle_size):
                return handle_name
        
        return None
    
    def is_point_in_image(self, x, y):
        """Check if point is inside the image bounds"""
        bounds = self.get_image_bounds()
        if not bounds:
            return False
        
        bx, by, width, height = bounds
        return bx <= x <= bx + width and by <= y <= by + height


class SwayBGPlusGUI:
    """Main GUI application"""
    
    def __init__(self):
        self.parser = SwayConfigParser()
        self.background_manager = BackgroundManager()
        self.outputs: List[OutputConfig] = []
        self.current_image_path: Optional[str] = None
        self.current_mode: str = "stretched"  # Current background mode
        self.selected_output: Optional[OutputConfig] = None
        self.config_changed: bool = False  # Track if config has unsaved changes
        self.background_applied: bool = False  # Track if background has been applied
        
        self.build_ui()
        self.refresh_outputs()
        self.detect_current_background()  # Try to detect existing background
    
    def build_ui(self):
        """Build the user interface"""
        # Main window
        self.window = Gtk.Window()
        self.window.set_title("SwayBG+ - Multi-Monitor Background Manager")
        self.window.set_default_size(1400, 900)
        self.window.connect('delete-event', self.on_quit)  # Handle X button and window close
        
        # Create menu bar
        self.create_menu_bar()
        
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.window.add(main_box)
        
        # Create a box to hold menubar and close button
        menubar_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        
        # Add menubar to the left
        menubar_box.pack_start(self.menubar, True, True, 0)
        
        # Add close button to the right
        close_btn = Gtk.Button.new_with_label("✕")
        close_btn.connect('clicked', self.on_quit)
        close_btn.set_tooltip_text("Close application")
        close_btn.set_size_request(40, -1)
        menubar_box.pack_end(close_btn, False, False, 0)
        
        # Menu bar with close button
        main_box.pack_start(menubar_box, False, False, 0)
        
        # Content area
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        main_box.pack_start(content_box, True, True, 0)
        
        # Instructions label
        instructions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        instructions = Gtk.Label()
        instructions.set_markup("<small><i>💡 Drag image to move • Drag corners to resize • Ctrl+R to reset</i></small>")
        instructions.set_halign(Gtk.Align.CENTER)
        instructions_box.pack_start(instructions, True, True, 0)
        content_box.pack_start(instructions_box, False, False, 0)
        
        # Main content area - horizontal paned
        main_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        content_box.pack_start(main_paned, True, True, 0)
        
        # Left panel - monitor layout
        left_frame = Gtk.Frame()
        left_frame.set_label("Monitor Layout & Preview")
        left_frame.set_size_request(500, -1)
        main_paned.pack1(left_frame, True, False)
        
        self.monitor_widget = MonitorWidget([])
        self.monitor_widget.connect('output-selected', self.on_output_selected)
        self.monitor_widget.connect('output-changed', self.on_output_changed)
        left_frame.add(self.monitor_widget)
        
        # Right panel - vertical paned for output info and image preview
        right_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        right_paned.set_size_request(500, -1)
        main_paned.pack2(right_paned, False, False)
        
        # Top right - output configuration with inline editing
        output_frame = Gtk.Frame()
        output_frame.set_label("Output Configuration")
        right_paned.pack1(output_frame, True, False)
        
        output_main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        output_main_box.set_margin_start(12)
        output_main_box.set_margin_end(12)
        output_main_box.set_margin_top(12)
        output_main_box.set_margin_bottom(12)
        output_frame.add(output_main_box)
        
        # Output controls section
        output_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        output_main_box.pack_end(output_controls_box, False, False, 0)
        
        # Refresh button (bottom right of output section)
        refresh_btn = Gtk.Button.new_with_label("🔄 Refresh Outputs")
        refresh_btn.connect('clicked', self.on_refresh_outputs)
        refresh_btn.set_tooltip_text("Refresh monitor configuration")
        output_controls_box.pack_end(refresh_btn, False, False, 0)
        
        # Create output list with inline editing
        self.create_output_list(output_main_box)
        
        # Bottom right - image preview
        preview_frame = Gtk.Frame()
        preview_frame.set_label("Image Preview")
        right_paned.pack2(preview_frame, True, False)
        
        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        preview_box.set_margin_start(12)
        preview_box.set_margin_end(12)
        preview_box.set_margin_top(12)
        preview_box.set_margin_bottom(12)
        preview_frame.add(preview_box)
        
        # Image preview widget
        self.preview_image = Gtk.Image()
        self.preview_image.set_size_request(300, 200)
        
        preview_scrolled = Gtk.ScrolledWindow()
        preview_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        preview_scrolled.add(self.preview_image)
        preview_box.pack_start(preview_scrolled, True, True, 0)
        
        # Image info label (includes filename and technical details)
        self.image_info_label = Gtk.Label()
        self.image_info_label.set_text("No image loaded")
        self.image_info_label.set_halign(Gtk.Align.START)
        preview_box.pack_start(self.image_info_label, False, False, 0)
        
        # Image controls section (bottom right of image section)
        image_controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        preview_box.pack_end(image_controls_box, False, False, 0)
        
        # Load image button
        load_image_btn = Gtk.Button.new_with_label("📁 Load Image")
        load_image_btn.connect('clicked', self.on_load_image)
        image_controls_box.pack_end(load_image_btn, False, False, 0)

        # Apply background button
        apply_bg_btn = Gtk.Button.new_with_label("🖼️ Apply Background")
        apply_bg_btn.connect('clicked', self.on_apply_background)
        apply_bg_btn.set_tooltip_text("Apply the current image as wallpaper to all monitors")
        image_controls_box.pack_end(apply_bg_btn, False, False, 0)
        
        # Mode selection
        self.mode_combo = Gtk.ComboBoxText()
        self.mode_combo.append_text("Stretched")
        self.mode_combo.append_text("Fill")
        self.mode_combo.append_text("Fit")
        self.mode_combo.append_text("Center")
        self.mode_combo.append_text("Tile")
        self.mode_combo.set_active(0)  # Default to stretched
        self.mode_combo.connect('changed', self.on_mode_changed)
        image_controls_box.pack_end(self.mode_combo, False, False, 0)
        
        # Mode label
        mode_label = Gtk.Label()
        mode_label.set_text("Mode:")
        image_controls_box.pack_end(mode_label, False, False, 0)
        
        # Status bar area with Reset and Save buttons
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        # Status bar (takes up most space)
        self.status_bar = Gtk.Statusbar()
        status_box.pack_start(self.status_bar, True, True, 0)
        
        # Reset button (to the left of Save)
        reset_bottom_btn = Gtk.Button.new_with_label("🔄 Reset")
        reset_bottom_btn.connect('clicked', self.on_reset_image_position)
        reset_bottom_btn.set_tooltip_text("Reset image position and scale")
        status_box.pack_end(reset_bottom_btn, False, False, 0)
        
        # Save button in bottom right
        save_bottom_btn = Gtk.Button.new_with_label("💾 Save")
        save_bottom_btn.connect('clicked', self.on_save_monitor_config)
        save_bottom_btn.set_tooltip_text("Save monitor configuration to sway config file")
        status_box.pack_end(save_bottom_btn, False, False, 0)
        
        content_box.pack_end(status_box, False, False, 0)
        
        self.window.show_all()
    
    def create_menu_bar(self):
        """Create the menu bar"""
        self.menubar = Gtk.MenuBar()
        
        # File menu
        file_menu = Gtk.Menu()
        file_item = Gtk.MenuItem.new_with_label("File")
        file_item.set_submenu(file_menu)
        self.menubar.append(file_item)
        
        # Select config file
        config_item = Gtk.MenuItem.new_with_label("Select Sway Config...")
        config_item.connect('activate', self.on_select_config)
        file_menu.append(config_item)
        
        file_menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        quit_item = Gtk.MenuItem.new_with_label("Quit")
        quit_item.connect('activate', self.on_quit)
        file_menu.append(quit_item)
        
        # View menu
        view_menu = Gtk.Menu()
        view_item = Gtk.MenuItem.new_with_label("View")
        view_item.set_submenu(view_menu)
        self.menubar.append(view_item)
        
        # Show config path
        show_config_item = Gtk.MenuItem.new_with_label("Show Config Path")
        show_config_item.connect('activate', self.on_show_config_path)
        view_menu.append(show_config_item)
        
        # Show backgrounds directory
        show_bg_dir_item = Gtk.MenuItem.new_with_label("Show Backgrounds Directory")
        show_bg_dir_item.connect('activate', self.on_show_backgrounds_dir)
        view_menu.append(show_bg_dir_item)
    
    def create_output_list(self, parent_container):
        """Create the output list with inline editing capabilities"""
        list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        
        # Instructions label
        instructions = Gtk.Label()
        instructions.set_markup("<i>Double-click position, resolution, scale, or transform values to edit</i>")
        instructions.set_halign(Gtk.Align.START)
        list_box.pack_start(instructions, False, False, 0)
        
        # Output list with editable cells
        # Store: name, resolution, position, scale, transform, enabled, output_object
        self.output_store = Gtk.ListStore(str, str, str, str, str, bool, object)
        self.output_tree = Gtk.TreeView(model=self.output_store)
        self.output_tree.set_grid_lines(Gtk.TreeViewGridLines.BOTH)
        
        # Name column (read-only)
        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Output", renderer, text=0)
        column.set_min_width(100)
        column.set_resizable(True)
        self.output_tree.append_column(column)
        
        # Resolution column (editable with dropdown)
        self.resolution_renderer = Gtk.CellRendererCombo()
        self.resolution_renderer.set_property("editable", True)
        
        # Create resolution model with common resolutions
        resolution_model = Gtk.ListStore(str)
        common_resolutions = [
            "1920x1080", "2560x1440", "3840x2160", "1680x1050", "1600x900",
            "1366x768", "1280x720", "1024x768", "800x600", "640x480",
            "3440x1440", "2560x1080", "1920x1200", "1440x900", "1280x1024"
        ]
        for res in common_resolutions:
            resolution_model.append([res])
        
        self.resolution_renderer.set_property("model", resolution_model)
        self.resolution_renderer.set_property("text-column", 0)
        self.resolution_renderer.set_property("has-entry", True)  # Allow custom input
        self.resolution_renderer.connect("edited", self.on_resolution_edited)
        
        column = Gtk.TreeViewColumn("Resolution", self.resolution_renderer, text=1)
        column.set_min_width(150)  # Increased minimum width
        column.set_expand(True)    # Allow column to expand
        column.set_resizable(True)
        self.output_tree.append_column(column)
        
        # Position column (editable)
        position_renderer = Gtk.CellRendererText()
        position_renderer.set_property("editable", True)
        position_renderer.connect("edited", self.on_position_edited)
        
        column = Gtk.TreeViewColumn("Position (X,Y)", position_renderer, text=2)
        column.set_min_width(120)
        column.set_resizable(True)
        self.output_tree.append_column(column)
        
        # Scale column (editable)
        scale_renderer = Gtk.CellRendererText()
        scale_renderer.set_property("editable", True)
        scale_renderer.connect("edited", self.on_scale_edited)
        
        column = Gtk.TreeViewColumn("Scale", scale_renderer, text=3)
        column.set_min_width(80)
        column.set_resizable(True)
        self.output_tree.append_column(column)
        
        # Transform/Orientation column (editable dropdown)
        self.transform_renderer = Gtk.CellRendererCombo()
        self.transform_renderer.set_property("editable", True)
        
        # Create transform model with valid transforms
        transform_model = Gtk.ListStore(str)
        valid_transforms = ['normal', '90', '180', '270', 'flipped', 'flipped-90', 'flipped-180', 'flipped-270']
        for transform in valid_transforms:
            transform_model.append([transform])
        
        self.transform_renderer.set_property("model", transform_model)
        self.transform_renderer.set_property("text-column", 0)
        self.transform_renderer.connect("edited", self.on_transform_edited)
        
        column = Gtk.TreeViewColumn("Transform", self.transform_renderer, text=4)
        column.set_min_width(100)
        column.set_resizable(True)
        self.output_tree.append_column(column)
        
        # Enabled column (checkbox)
        enabled_renderer = Gtk.CellRendererToggle()
        enabled_renderer.connect("toggled", self.on_enabled_toggled)
        
        column = Gtk.TreeViewColumn("Enabled", enabled_renderer, active=5)
        column.set_min_width(80)
        self.output_tree.append_column(column)
        
        # Connect selection changed
        selection = self.output_tree.get_selection()
        selection.connect("changed", self.on_tree_selection_changed)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_size_request(-1, 300)
        scrolled.add(self.output_tree)
        list_box.pack_start(scrolled, True, True, 0)
        
        parent_container.pack_start(list_box, True, True, 0)
    
    def refresh_outputs(self):
        """Refresh the list of outputs"""
        self.outputs = self.parser.get_current_outputs()
        
        # Update monitor widget
        self.monitor_widget.outputs = self.outputs
        self.monitor_widget.update_scale()
        self.monitor_widget.queue_draw()
        
        # Update output list
        self.output_store.clear()
        for output in self.outputs:
            self.output_store.append([
                output.name,
                f"{output.resolution[0]}x{output.resolution[1]}",
                f"{output.position[0]}, {output.position[1]}",
                f"{output.scale:.1f}",
                output.transform,
                output.enabled,
                output
            ])
        
        self.update_status(f"Found {len(self.outputs)} outputs")
        
        # Update config path in status
        config_path = self.parser.get_config_path()
        if config_path:
            self.update_status(f"Found {len(self.outputs)} outputs | Config: {config_path}")
        else:
            self.update_status(f"Found {len(self.outputs)} outputs | No config file found")
    
    def update_status(self, message: str):
        """Update status bar"""
        context_id = self.status_bar.get_context_id("main")
        self.status_bar.push(context_id, message)
    
    def on_output_selected(self, widget, output):
        """Handle output selection from monitor widget"""
        self.selected_output = output
        
        # Find and select in tree view
        for i, row in enumerate(self.output_store):
            if row[6] == output:  # Compare output objects
                selection = self.output_tree.get_selection()
                selection.select_iter(self.output_store.get_iter(i))
                break
    
    def on_output_changed(self, widget, output):
        """Handle output change from monitor widget"""
        self.selected_output = output
        self.refresh_output_list()
        self.mark_config_changed()  # Mark as changed when output is modified
    
    def refresh_output_list(self):
        """Refresh the output list display"""
        self.output_store.clear()
        for output in self.outputs:
            self.output_store.append([
                output.name,
                f"{output.resolution[0]}x{output.resolution[1]}",
                f"{output.position[0]}, {output.position[1]}",
                f"{output.scale:.1f}",
                output.transform,
                output.enabled,
                output
            ])
    
    def on_tree_selection_changed(self, selection):
        """Handle tree selection change"""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            output = model[tree_iter][6]  # Get output object from column 6 (updated index)
            self.selected_output = output
            self.monitor_widget.selected_output = output
            self.monitor_widget.queue_draw()
            
            # Update resolution dropdown for this output
            available_resolutions = self.parser.get_available_resolutions(output.name)
            resolution_model = self.resolution_renderer.get_property("model")
            resolution_model.clear()
            
            # Add available resolutions
            for res in available_resolutions:
                resolution_model.append([res])
            
            # Add some common fallbacks if none available
            if not available_resolutions:
                common_resolutions = [
                    "1920x1080", "2560x1440", "3840x2160", "1680x1050", "1600x900",
                    "1366x768", "1280x720", "1024x768"
                ]
                for res in common_resolutions:
                    resolution_model.append([res])
    
    def on_resolution_edited(self, renderer, path, new_text):
        """Handle resolution cell editing"""
        tree_iter = self.output_store.get_iter(path)
        output = self.output_store[tree_iter][6]  # Get output object
        
        # Update resolution dropdown with available resolutions for this output
        available_resolutions = self.parser.get_available_resolutions(output.name)
        resolution_model = renderer.get_property("model")
        resolution_model.clear()
        
        # Add available resolutions
        for res in available_resolutions:
            resolution_model.append([res])
        
        # Add some common fallbacks if none available
        if not available_resolutions:
            common_resolutions = [
                "1920x1080", "2560x1440", "3840x2160", "1680x1050", "1600x900",
                "1366x768", "1280x720", "1024x768"
            ]
            for res in common_resolutions:
                resolution_model.append([res])
        
        if 'x' in new_text:
            try:
                width, height = map(int, new_text.split('x'))
                output.resolution = (width, height)
                self.output_store[tree_iter][1] = new_text
                self.monitor_widget.update_scale()
                self.monitor_widget.queue_draw()
                self.update_status(f"Updated {output.name} resolution to {new_text}")
                self.mark_config_changed()
            except ValueError:
                self.show_error(f"Invalid resolution format: {new_text}. Use format like '1920x1080'")
    
    def on_position_edited(self, renderer, path, new_text):
        """Handle position cell editing"""
        tree_iter = self.output_store.get_iter(path)
        output = self.output_store[tree_iter][6]  # Get output object
        
        # Parse position - accept formats like "0,0" or "0, 0" or "0 0"
        try:
            # Replace common separators with comma and split
            clean_text = new_text.replace(' ', ',').replace(',', ' ').strip()
            parts = clean_text.split()
            if len(parts) == 2:
                x, y = map(int, parts)
                output.position = (x, y)
                self.output_store[tree_iter][2] = f"{x}, {y}"
                self.monitor_widget.queue_draw()
                self.update_status(f"Updated {output.name} position to ({x}, {y})")
                self.mark_config_changed()
            else:
                raise ValueError("Need exactly 2 values")
        except ValueError:
            self.show_error(f"Invalid position format: {new_text}. Use format like '0, 0' or '1920 0'")
    
    def on_scale_edited(self, renderer, path, new_text):
        """Handle scale cell editing"""
        tree_iter = self.output_store.get_iter(path)
        output = self.output_store[tree_iter][6]  # Get output object
        
        try:
            scale = float(new_text)
            if 0.1 <= scale <= 5.0:
                output.scale = scale
                self.output_store[tree_iter][3] = f"{scale:.1f}"
                self.update_status(f"Updated {output.name} scale to {scale:.1f}")
                self.mark_config_changed()
            else:
                raise ValueError("Scale must be between 0.1 and 5.0")
        except ValueError as e:
            self.show_error(f"Invalid scale value: {new_text}. {str(e)}")
    
    def on_enabled_toggled(self, renderer, path):
        """Handle enabled checkbox toggle"""
        tree_iter = self.output_store.get_iter(path)
        output = self.output_store[tree_iter][6]  # Get output object
        
        # Toggle enabled state
        output.enabled = not output.enabled
        self.output_store[tree_iter][5] = output.enabled
        
        status = "enabled" if output.enabled else "disabled"
        self.update_status(f"{output.name} {status}")
        self.mark_config_changed()
    
    def on_select_config(self, widget):
        """Handle select config file"""
        dialog = Gtk.FileChooserDialog(
            title="Select Sway Config File",
            parent=self.window,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        
        # Set default path
        current_config = self.parser.get_config_path()
        if current_config:
            dialog.set_filename(current_config)
        else:
            dialog.set_current_folder(os.path.expanduser("~/.config/sway"))
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            config_path = dialog.get_filename()
            self.parser.set_config_path(config_path)
            self.update_status(f"Config file set to: {config_path}")
        
        dialog.destroy()
    
    def on_save_monitor_config(self, widget):
        """Handle save monitor config"""
        if not self.parser.get_config_path():
            self.show_error("No config file selected. Please select a config file first.")
            return
        
        try:
            success = self.parser.save_config_file(backup=True)
            if success:
                self.mark_config_saved()  # Mark as saved
                self.show_info("Monitor Configuration Saved", 
                             "Monitor configuration has been saved to the sway config file.\n"
                             "A backup was created with .backup extension.")
            else:
                self.show_error("Failed to save config file")
        except Exception as e:
            self.show_error(f"Error saving config: {e}")
    
    def on_apply_monitor_config(self, button_or_widget):
        """Handle apply monitor config"""
        for output in self.outputs:
            success = self.parser.apply_output_config(output)
            if not success:
                self.show_error(f"Failed to apply config for {output.name}")
                return
        
        self.show_info("Configuration Applied", 
                      "Monitor configuration has been applied to sway.\n"
                      "Changes will take effect immediately.")
    
    def on_show_config_path(self, widget):
        """Show current config path"""
        config_path = self.parser.get_config_path()
        if config_path:
            self.show_info("Sway Config Path", f"Current config file:\n{config_path}")
        else:
            self.show_info("Sway Config Path", "No config file found or selected.")
    
    def on_show_backgrounds_dir(self, widget):
        """Show backgrounds directory"""
        backgrounds_dir = self.background_manager.config_dir
        if os.path.exists(backgrounds_dir):
            self.show_info("Backgrounds Directory", f"SwayBG+ backgrounds directory:\n{backgrounds_dir}")
        else:
            self.show_error("Backgrounds Directory", "Backgrounds directory not found.")
    
    def on_refresh_outputs(self, button):
        """Handle refresh outputs button"""
        self.refresh_outputs()
    
    def on_reset_image_position(self, button):
        """Handle reset image position button"""
        self.monitor_widget.reset_image_position()
        self.update_status("Image position and scale reset to defaults")
    
    def on_mode_changed(self, combo):
        """Handle mode selection change"""
        active_text = combo.get_active_text()
        if active_text:
            self.current_mode = active_text.lower()
            # Update preview mode
            self.monitor_widget.set_preview_mode(self.current_mode)
            self.update_status(f"Mode changed to: {active_text}")

    def on_apply_background(self, button):
        """Handle apply background button - saves and sets wallpaper"""
        # Check if an image is loaded
        if not self.current_image_path:
            self.show_error("No image loaded. Please load an image first.")
            return

        # Check if we have outputs
        if not self.outputs:
            self.show_error("No monitor outputs detected. Please check your display configuration.")
            return

        try:
            # Get current positioning from monitor widget
            image_offset = self.monitor_widget.image_offset
            image_scale = self.monitor_widget.image_scale

            # Apply the background based on the current mode
            success = False
            if self.current_mode == "stretched":
                # Use stretched mode for spanning across monitors
                success = self.background_manager.set_background_stretched(
                    self.current_image_path,
                    self.outputs,
                    image_offset,
                    image_scale
                )
            else:
                # Use fitted mode for individual monitor backgrounds (fill, fit, center, tile)
                success = self.background_manager.set_background_fitted(
                    self.current_image_path,
                    self.outputs,
                    self.current_mode,
                    image_offset,
                    image_scale
                )

            if success:
                # Mark as applied and save the original path
                self.background_applied = True
                self.save_original_image_path(self.current_image_path)

                # Show success message
                self.show_info("Background Applied",
                             f"Successfully applied background in {self.current_mode} mode.\n"
                             f"The wallpaper has been saved to ~/.config/sway/backgrounds/")
                self.update_status(f"Background applied: {os.path.basename(self.current_image_path)}")
            else:
                self.show_error("Failed to apply background. Please check your sway configuration.")

        except Exception as e:
            self.show_error(f"Error applying background: {str(e)}")
            print(f"Error applying background: {e}")
    
    def on_load_image(self, button):
        """Handle load image button"""
        dialog = Gtk.FileChooserDialog(
            title="Choose an image",
            parent=self.window,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_buttons(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_OPEN, Gtk.ResponseType.OK
        )
        
        # Add image filter
        filter_images = Gtk.FileFilter()
        filter_images.set_name("Images")
        filter_images.add_mime_type("image/jpeg")
        filter_images.add_mime_type("image/png")
        filter_images.add_mime_type("image/gif")
        filter_images.add_mime_type("image/bmp")
        filter_images.add_mime_type("image/tiff")
        dialog.add_filter(filter_images)
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.current_image_path = dialog.get_filename()
            self.load_image_preview()
            self.update_status(f"Loaded image: {self.current_image_path}")
            
            # Reset image position when loading new image
            self.monitor_widget.reset_image_position()
        
        dialog.destroy()
    
    def load_image_preview(self):
        """Load and display image preview"""
        if not self.current_image_path:
            return
        
        try:
            # Load image info
            with Image.open(self.current_image_path) as img:
                width, height = img.size
                format_name = img.format or "Unknown"
                file_size = os.path.getsize(self.current_image_path)
                file_size_mb = file_size / (1024 * 1024)
                
                # Combine filename and technical details
                filename = os.path.basename(self.current_image_path)
                self.image_info_label.set_text(
                    f"Image: {filename}\n"
                    f"Size: {width}×{height}\n"
                    f"Format: {format_name}\n"
                    f"File size: {file_size_mb:.1f} MB"
                )
            
            # Load preview for the image widget
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                self.current_image_path, 300, 200, True
            )
            self.preview_image.set_from_pixbuf(pixbuf)
            
            # Set preview on monitor widget
            self.monitor_widget.set_preview_image(self.current_image_path)
            
        except Exception as e:
            self.show_error(f"Error loading image preview: {e}")
            self.image_info_label.set_text("Error loading image")
    
    def show_error(self, message: str):
        """Show error dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text=message
        )
        dialog.run()
        dialog.destroy()
    
    def show_info(self, title: str, message: str):
        """Show info dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
    
    def on_quit(self, widget, event=None):
        """Handle quit event"""
        # Only ask about saving if there are unsaved config changes
        if self.config_changed and self.outputs and self.parser.get_config_path():
            dialog = Gtk.MessageDialog(
                transient_for=self.window,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Save Configuration Changes?"
            )
            dialog.format_secondary_text(
                "You have unsaved monitor configuration changes.\n\n"
                "• Yes: Save changes and quit\n"
                "• No: Quit without saving"
            )
            
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.YES:
                try:
                    success = self.parser.save_config_file(backup=True)
                    if success:
                        print("Configuration saved successfully")
                    else:
                        print("Failed to save configuration")
                except Exception as e:
                    print(f"Error saving configuration: {e}")
        
        self.background_manager.cleanup()
        Gtk.main_quit()
        
        # Return False to allow window to close normally
        return False
    
    def save_original_image_path(self, image_path: str):
        """Save the original image path for future detection"""
        try:
            config_dir = os.path.expanduser("~/.config/sway")
            os.makedirs(config_dir, exist_ok=True)
            
            # Save the original image path
            with open(os.path.join(config_dir, "current_wallpaper"), 'w') as f:
                f.write(image_path)
        except Exception as e:
            print(f"Error saving original image path: {e}")
    
    def detect_current_background(self):
        """Try to detect current background image from multiple sources"""
        try:
            # Method 0: Check for saved configuration first
            config = self.background_manager.load_background_config()
            if config:
                image_path = config.get('image_path')
                mode = config.get('mode', 'stretched')
                image_offset = tuple(config.get('image_offset', [0, 0]))
                image_scale = config.get('image_scale', 1.0)
                
                if image_path and os.path.exists(image_path):
                    self.load_detected_background(image_path, "saved configuration")
                    # Restore image positioning
                    self.monitor_widget.image_offset = image_offset
                    self.monitor_widget.image_scale = image_scale
                    # Set mode
                    mode_index = ['stretched', 'fill', 'fit', 'center', 'tile'].index(mode.lower())
                    self.mode_combo.set_active(mode_index)
                    self.current_mode = mode.lower()
                    self.monitor_widget.set_preview_mode(self.current_mode)
                    return
            
            # Method 1: Check our saved wallpaper path
            saved_wallpaper_path = os.path.expanduser("~/.config/sway/current_wallpaper")
            if os.path.exists(saved_wallpaper_path):
                try:
                    with open(saved_wallpaper_path, 'r') as f:
                        image_path = f.read().strip()
                        if os.path.exists(image_path):
                            self.load_detected_background(image_path, "saved wallpaper config")
                            return
                except (OSError, IOError):
                    pass
            
            # Method 2: Check running swaybg processes for non-temporary files
            result = subprocess.run(['pgrep', '-f', 'swaybg'], capture_output=True, text=True)
            if result.returncode == 0:
                pids = result.stdout.strip().split('\n')
                for pid in pids:
                    if pid:
                        try:
                            # Get full command line
                            result = subprocess.run(['ps', '-p', pid, '-o', 'args='], 
                                                  capture_output=True, text=True)
                            if result.returncode == 0:
                                cmdline = result.stdout.strip()
                                # Look for image file in command line
                                parts = cmdline.split()
                                for i, part in enumerate(parts):
                                    if part in ['-i', '--image'] and i + 1 < len(parts):
                                        image_path = parts[i + 1]
                                        # Skip temporary files, look for original images
                                        if not image_path.startswith('/tmp/'):
                                            if os.path.exists(image_path):
                                                self.load_detected_background(image_path, "running swaybg process")
                                                return
                        except (OSError, IOError):
                            continue
            
            # Method 3: Check for recently used background files
            recent_paths = [
                os.path.expanduser("~/.cache/sway/last_wallpaper"),
                os.path.expanduser("~/.local/share/sway/wallpaper"),
            ]
            
            for path in recent_paths:
                if os.path.exists(path):
                    try:
                        with open(path, 'r') as f:
                            image_path = f.read().strip()
                            if os.path.exists(image_path):
                                self.load_detected_background(image_path, f"cache file {path}")
                                return
                    except (OSError, IOError):
                        continue
            
            # Method 4: Check common background locations
            common_bg_paths = [
                os.path.expanduser("~/.config/sway/wallpaper.jpg"),
                os.path.expanduser("~/.config/sway/wallpaper.png"),
                os.path.expanduser("~/.config/sway/background.jpg"),
                os.path.expanduser("~/.config/sway/background.png"),
                os.path.expanduser("~/Pictures/wallpaper.jpg"),
                os.path.expanduser("~/Pictures/wallpaper.png"),
                os.path.expanduser("~/Pictures/background.jpg"),
                os.path.expanduser("~/Pictures/background.png"),
                os.path.expanduser("~/wallpaper.jpg"),
                os.path.expanduser("~/wallpaper.png"),
                os.path.expanduser("~/background.jpg"),
                os.path.expanduser("~/background.png"),
            ]
            
            for path in common_bg_paths:
                if os.path.exists(path):
                    self.load_detected_background(path, "common location")
                    return
            
            # Method 5: Check most recent image files in Pictures directory
            pictures_dir = os.path.expanduser("~/Pictures")
            if os.path.exists(pictures_dir):
                try:
                    import glob
                    import time
                    image_files = []
                    for ext in ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.webp']:
                        image_files.extend(glob.glob(os.path.join(pictures_dir, ext)))
                        image_files.extend(glob.glob(os.path.join(pictures_dir, ext.upper())))
                    
                    if image_files:
                        # Sort by modification time, get most recent
                        image_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                        most_recent = image_files[0]
                        # Only use if it's been modified recently (within last 7 days)
                        if time.time() - os.path.getmtime(most_recent) < 7 * 24 * 3600:
                            self.load_detected_background(most_recent, "recent Pictures file")
                            return
                except Exception:
                    pass
                    
        except Exception as e:
            print(f"Error detecting current background: {e}")
    
    def load_detected_background(self, image_path: str, source: str):
        """Load a detected background image"""
        try:
            self.current_image_path = image_path
            self.load_image_preview()
            self.update_status(f"Auto-loaded background from {source}: {os.path.basename(image_path)}")
        except Exception as e:
            print(f"Error loading detected background {image_path}: {e}")
    
    def mark_config_changed(self):
        """Mark configuration as changed"""
        self.config_changed = True
    
    def mark_config_saved(self):
        """Mark configuration as saved"""
        self.config_changed = False
    
    def on_transform_edited(self, renderer, path, new_text):
        """Handle transform cell editing"""
        tree_iter = self.output_store.get_iter(path)
        output = self.output_store[tree_iter][6]  # Get output object
        
        # Validate transform
        valid_transforms = ['normal', '90', '180', '270', 'flipped', 'flipped-90', 'flipped-180', 'flipped-270']
        if new_text not in valid_transforms:
            self.show_error(f"Invalid transform '{new_text}'. Valid transforms: {', '.join(valid_transforms)}")
            return
        
        try:
            # Update output configuration
            if self.parser.update_output_config(output.name, transform=new_text):
                # Update the store
                self.output_store[tree_iter][4] = new_text
                # Update the output object
                output.transform = new_text
                self.mark_config_changed()
                
                # Auto-apply if user wants immediate changes
                if hasattr(self, 'auto_apply_changes') and self.auto_apply_changes:
                    self.parser.apply_output_config(output)
                    self.refresh_outputs()  # Refresh to get updated state
                else:
                    self.update_status(f"Transform changed to {new_text} for {output.name} (click Apply to activate)")
            else:
                self.show_error(f"Failed to update transform for {output.name}")
        except Exception as e:
            self.show_error(f"Error updating transform: {e}")
    
    def run(self):
        """Run the application"""
        Gtk.main()


def main():
    """Main entry point"""
    app = SwayBGPlusGUI()
    app.run()


if __name__ == "__main__":
    main() 