import time
import numpy as np
import curses
from picamera import PiCamera
from PIL import Image, ImageDraw

# Initialize camera
camera = PiCamera()
camera.resolution = (1280, 720)
camera.framerate = 30

# Initial line positions (center of screen)
horizontal_y = 360  # Center vertically (for 720p)
vertical_x = 640    # Center horizontally (for 1280p)

# Function to create overlay image with lines
def create_overlay(horizontal_y, vertical_x):
    overlay_img = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay_img)
    # Draw horizontal line (red, 2px thick)
    draw.line([(0, horizontal_y), (1280, horizontal_y)], fill=(255, 0, 0, 128), width=2)
    # Draw vertical line (red, 2px thick)
    draw.line([(vertical_x, 0), (vertical_x, 720)], fill=(255, 0, 0, 128), width=2)
    return overlay_img

# Create initial overlay
overlay_img = create_overlay(horizontal_y, vertical_x)
overlay = camera.add_overlay(np.array(overlay_img), layer=3, alpha=128)

# Start camera preview (show live feed on HDMI output)
camera.start_preview(fullscreen=True)

# Function to update overlay
def update_overlay():
    global overlay
    overlay_img = create_overlay(horizontal_y, vertical_x)
    camera.remove_overlay(overlay)
    overlay = camera.add_overlay(np.array(overlay_img), layer=3, alpha=128)

# Function to handle keyboard input using curses
def handle_input(stdscr):
    global horizontal_y, vertical_x

    stdscr.nodelay(True)  # Non-blocking key detection
    stdscr.timeout(100)    # Set input wait time (milliseconds)

    while True:
        key = stdscr.getch()

        if key == ord('q'):  # Press 'q' to exit
            break
        elif key == curses.KEY_UP:
            horizontal_y = max(0, horizontal_y - 10)  # Move up
        elif key == curses.KEY_DOWN:
            horizontal_y = min(720, horizontal_y + 10)  # Move down
        elif key == curses.KEY_LEFT:
            vertical_x = max(0, vertical_x - 10)  # Move left
        elif key == curses.KEY_RIGHT:
            vertical_x = min(1280, vertical_x + 10)  # Move right
        
        # Update the overlay with new positions
        update_overlay()

try:
    curses.wrapper(handle_input)  # Run the keyboard input loop
except KeyboardInterrupt:
    pass
finally:
    camera.stop_preview()
