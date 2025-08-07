from gpiozero import LED, Buzzer
from time import sleep
import threading

class LEDControl:
    def __init__(self, pin):
        """
        Initialize the LEDControl object.
        :param pin: The GPIO pin number where the LED is connected.
        """
        self.led = LED(pin)
        self.running = False  # Flag to control the LED toggling

    def toggle_led(self, on_time, off_time, repeat_count=None):
        """
        Start toggling the LED on/off every `on_time` and `off_time`.
        :param on_time: Duration (seconds) to keep the LED ON.
        :param off_time: Duration (seconds) to keep the LED OFF.
        """
        self.running = True
        count = 0
        while self.running:
            if repeat_count and count >= repeat_count:
                break  # Stop after repeating the specified number of times
            self.led.on()
            print(f"LED ON")
            sleep(on_time)
            self.led.off()
            print(f"LED OFF")
            sleep(off_time)
            count += 1

    def start_toggle(self, on_time, off_time):
        """
        Start toggling the LED in a separate thread.
        :param on_time: Duration (seconds) to keep the LED ON.
        :param off_time: Duration (seconds) to keep the LED OFF.
        """
        threading.Thread(target=self.toggle_led, args=(on_time, off_time)).start()

    def stop(self):
        """Stop the LED toggling."""
        self.running = False
        self.led.off()
        print("LED stopped")

class BuzzerControl:
    def __init__(self, pin):
        """
        Initialize the BuzzerControl object.
        :param pin: The GPIO pin number where the buzzer is connected.
        """
        self.buzzer = Buzzer(pin)
        self.running = False  # Flag to control the buzzer toggling

    def toggle_buzzer(self, on_time, off_time, repeat_count=None):
        """
        Start toggling the buzzer on/off every `on_time` and `off_time`.
        :param on_time: Duration (seconds) to keep the buzzer ON.
        :param off_time: Duration (seconds) to keep the buzzer OFF.
        """
        self.running = True
        count = 0
        while self.running:
            if repeat_count and count >= repeat_count:
                break  # Stop after repeating the specified number of times
            self.buzzer.on()
            print(f"Buzzer ON")
            sleep(on_time)
            self.buzzer.off()
            print(f"Buzzer OFF")
            sleep(off_time)
            count += 1

    def start_toggle(self, on_time, off_time):
        """
        Start toggling the buzzer in a separate thread.
        :param on_time: Duration (seconds) to keep the buzzer ON.
        :param off_time: Duration (seconds) to keep the buzzer OFF.
        """
        threading.Thread(target=self.toggle_buzzer, args=(on_time, off_time)).start()

    def stop(self):
        """Stop the buzzer toggling."""
        self.running = False
        self.buzzer.off()
        print("Buzzer stopped")
