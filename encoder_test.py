from machine import Pin
import time

# Rotary encoder A and B pins.
encoder_a = Pin(4, Pin.IN)
encoder_b = Pin(2, Pin.IN)

last_a = encoder_a.value()

print("Encoder test running")

while True:
    a = encoder_a.value()

    # Count only one edge of A, then read B to determine direction.
    if a != last_a and a == 1:
        if encoder_b.value() != a:
            print("Clockwise")
        else:
            print("Counter-clockwise")

    last_a = a
    time.sleep_ms(2)
