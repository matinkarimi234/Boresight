from gpiozero import Button
class ButtonControl:
    def __init__(self, overlay_display, step=10):
        self.overlay_display = overlay_display
        self.step = step

        # Setup GPIO buttons
        self.button_left = Button(5)
        self.button_down = Button(14)
        self.button_right = Button(18)
        self.button_up = Button(15)

        # Attach callbacks to button press events
        self.button_left.when_pressed = self.on_left
        self.button_right.when_pressed = self.on_right
        self.button_up.when_pressed = self.on_up
        self.button_down.when_pressed = self.on_down

    def on_left(self):
        """Move the crosshair left."""
        self.overlay_display.vertical_x = max(0, self.overlay_display.vertical_x - self.step)
        self.overlay_display.update_overlay(0, 0, self.overlay_display.scale_overlay())

    def on_right(self):
        """Move the crosshair right."""
        self.overlay_display.vertical_x = min(self.overlay_display.desired_res[0]-1, self.overlay_display.vertical_x + self.step)
        self.overlay_display.update_overlay(0, 0, self.overlay_display.scale_overlay())

    def on_up(self):
        """Move the crosshair up."""
        self.overlay_display.horizontal_y = max(0, self.overlay_display.horizontal_y - self.step)
        self.overlay_display.update_overlay(0, 0, self.overlay_display.scale_overlay())

    def on_down(self):
        """Move the crosshair down."""
        self.overlay_display.horizontal_y = min(self.overlay_display.desired_res[1]-1, self.overlay_display.horizontal_y + self.step)
        self.overlay_display.update_overlay(0, 0, self.overlay_display.scale_overlay())

    def save_offset(self):
        """Save the current crosshair offset."""
        self.overlay_display.save_offset()
