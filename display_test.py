from machine import Pin, SPI
from ssd1309 import Display
import time


spi = SPI(
    0,
    baudrate=1_000_000,
    sck=Pin(18),
    mosi=Pin(19),
)

oled = Display(
    spi=spi,
    cs=Pin(17),
    dc=Pin(20),
    rst=Pin(21),
    width=128,
    height=64,
    flip=False,
)

oled.clear_buffers()
oled.draw_text8x8(0, 0, "DISPLAY TEST")
oled.draw_text8x8(0, 16, "Hello from Pico!")
oled.draw_text8x8(0, 32, "SSD1309 is working")
oled.draw_text8x8(0, 48, "Pins: 17-21")
oled.present()


while True:
    time.sleep(1)
