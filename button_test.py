from machine import Pin
import time

# Button 1 = Mode button; Button 2 = Sound button.
button1 = Pin(15, Pin.IN, Pin.PULL_UP)
button2 = Pin(14, Pin.IN, Pin.PULL_UP)

last1 = 1
last2 = 1

print("Button test running")

while True:
    now1 = button1.value()
    now2 = button2.value()

    if last1 == 1 and now1 == 0:
        print("Button 1 pressed")
    if last2 == 1 and now2 == 0:
        print("Button 2 pressed")

    last1 = now1
    last2 = now2
    time.sleep_ms(20)
