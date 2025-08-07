from gpiozero import Button
from State_Machine import StateMachineEnum
class ButtonControl:
        # Define the flags as constants in the ButtonControl class
    OK_PRESSED = "OK_PRESSED"
    OK_RELEASED = "OK_RELEASED"
    LEFT_UP_BUTTON_PRESSED = "LEFT_UP_BUTTON_PRESSED"
    LEFT_UP_BUTTON_RELEASED = "LEFT_UP_BUTTON_RELEASED"
    RIGHT_DOWN_BUTTON_PRESSED = "RIGHT_DOWN_BUTTON_PRESSED"
    RIGHT_DOWN_BUTTON_RELEASED = "RIGHT_DOWN_BUTTON_RELEASED"



    def __init__(self, state_machine, state_update_callback):
        self.state_machine = state_machine
        self.state_update_callback = state_update_callback

        # Setup GPIO buttons
        self.button_left_up = Button(14)
        self.button_ok = Button(15)
        self.button_right_down = Button(18)

        # Attach callbacks to button press events
        self.button_left_up.when_pressed = self.on_left_or_up
        self.button_left_up.when_released = self.on_left_or_up_released
        self.button_right_down.when_pressed = self.on_right_or_down
        self.button_right_down.when_released = self.on_right_or_down_released
        self.button_ok.when_pressed = self.on_ok_pressed
        self.button_ok.when_released = self.on_ok_released

    def on_left_or_up(self):
        """Move the crosshair left/up."""
        self.state_update_callback(ButtonControl.LEFT_UP_BUTTON_PRESSED)
    def on_left_or_up_released(self):
        self.state_update_callback(ButtonControl.LEFT_UP_BUTTON_RELEASED)

    def on_right_or_down(self):
        """Move the crosshair right/down."""
        self.state_update_callback(ButtonControl.RIGHT_DOWN_BUTTON_PRESSED)
        
    def on_right_or_down_released(self):
        self.state_update_callback(ButtonControl.RIGHT_DOWN_BUTTON_RELEASED)

    def on_ok_pressed(self):
        self.state_update_callback(ButtonControl.OK_PRESSED)

    def on_ok_released(self):
        self.state_update_callback(ButtonControl.OK_RELEASED)