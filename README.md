# Animal-Themed Clock Radio (ECE 299)
This project contains MicroPython firmware for the Raspberry Pi Pico 2 W, implementing an FM radio with an OLED display and a configurable alarm system. 
As instructed by P. Drissen, the use of Claude Code was used for parts of the development.

## Hardware Overview
- **Microcontroller:** Raspberry Pi Pico 2 W
- **Radio:** RDA5807 FM Module (I2C)
- **Display:** SSD1309 OLED (SPI)
- **Rotary Encoder:** Used for user navigation and control
- **Push Buttons:** Used for user input and mode selection
- **Audio Amplifier:** LM386N-4 used to amplify the FM radio audio signal before driving the speaker.

## Controls 
| Input | Action | Function |
|-------|--------|----------|
| Rotary Encoder | Rotate | Adjust currently selected cycle value |
| Cycle Button | Short Press | Cycle through adjustable settings |
| Cycle Button | Long Press | Arm/Disarm alarm |
| Cycle Button | Short Press | Snooze (when ringing) |
| Alarm Button | Short Press | Change alarm sound | 



