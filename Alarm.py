from gpiozero import LED, Buzzer
import threading

class _BlinkBase:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._on_time = 0.0
        self._off_time = 0.0
        self._repeat = None  # None = forever

    def _loop(self, turn_on, turn_off):
        count = 0
        try:
            while not self._stop.is_set():
                # ON
                turn_on()
                if self._stop.wait(self._on_time):
                    break

                # OFF
                turn_off()
                if self._repeat is not None:
                    count += 1
                    if count >= self._repeat:
                        break

                if self._stop.wait(self._off_time):
                    break
        finally:
            # Ensure device is OFF when exiting
            try:
                turn_off()
            except Exception:
                pass

    def start_toggle(self, on_time, off_time, repeat_count=None):
        """
        Start blinking. Safe to call repeatedly; if already running,
        it just updates timings and returns.
        """
        with self._lock:
            self._on_time = float(on_time)
            self._off_time = float(off_time)
            self._repeat = repeat_count if (repeat_count is None) else int(repeat_count)

            # Already running? Just update timings and bail.
            if self._thread and self._thread.is_alive():
                return

            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self, timeout=1.0):
        """Stop blinking and wait for the thread to exit."""
        with self._lock:
            self._stop.set()
            t = self._thread
        if t:
            t.join(timeout=timeout)
        # Thread ensures device is off on exit.

    # To be provided by subclass
    def _run(self):
        raise NotImplementedError


class LEDControl(_BlinkBase):
    def __init__(self, pin):
        super().__init__()
        self.led = LED(pin)

    def _run(self):
        self._loop(self.led.on, self.led.off)


class BuzzerControl(_BlinkBase):
    def __init__(self, pin):
        super().__init__()
        self.buzzer = Buzzer(pin)

    def _run(self):
        self._loop(self.buzzer.on, self.buzzer.off)
