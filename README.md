# Animal-Themed Clock Radio (ECE 299 Project)

A MicroPython-based clock-radio system built on the Raspberry Pi Pico W. The device combines real-time clock functionality with FM radio control, displayed on an SPI SSD1309 OLED and controlled via a rotary encoder and push button interface.

This project is currently in **prototype stage**: core firmware, UI, encoder handling, radio control, and display system are implemented. PCB design and enclosure are still in progress.

---

## Features (Implemented)

### Clock System
- Real-time second counter (software-based timing loop)
- Alarm time variables and UI placeholders
- Alarm toggle (long-press button feature)
- Mode-based time/alarm adjustment system (framework complete)

### FM Radio
- FM frequency tuning (88.0 – 108.0 MHz)
- Volume control (0–15 levels)
- I2C communication with FM radio chip
- Frequency step adjustment via encoder
- Radio state updates pushed immediately to hardware

### User Interface
- SSD1309 OLED display via SPI
- Live updates of:
  - Time
  - Frequency
  - Volume bar
  - Alarm state (ON/OFF)
  - Mode indicator (VOL / FREQ / HOUR / MIN / ALM HR / ALM MIN)
- Visual volume bar graph
- Mode cycling via button press
- Long-press toggle functionality

### Input System
- Rotary encoder with interrupt-based handling
- Debounce filtering for stable input
- Dual-mode encoder behavior:
  - Volume control mode
  - Frequency tuning mode
- Push button:
  - Short press → mode change
  - Long press → alarm toggle

---

## System Architecture

- **Core 0 (Main Loop)**
  - Button handling
  - Mode switching
  - Timekeeping (1-second tick)

- **Core 1 (Display Thread)**
  - OLED rendering loop
  - UI refresh only on state change

- **Interrupt Handler**
  - Rotary encoder decoding (quadrature table)
  - Updates volume or frequency depending on mode

---

## Hardware Overview

### Microcontroller
- Raspberry Pi Pico W

### Display
- SSD1309 OLED (SPI)
  - SCK → GPIO 18
  - MOSI → GPIO 19
  - DC → GPIO 20
  - RES → GPIO 21
  - CS → GPIO 17

### Inputs
- Rotary Encoder:
  - A → GPIO 4
  - B → GPIO 2
- Mode Button:
  - GPIO 15 (Pull-up, active low)

### Radio Module
- I2C FM radio chip
  - SDA → GPIO 26
  - SCL → GPIO 27
  - Address: 0x10

---

## 📁 Project Structure
│
├── main.py # Core firmware (clock, UI, input, radio)
├── ssd1309.py # OLED driver (provided library)
├── encoder/ # Encoder utilities (if externalized)
├── radio_driver.py # (currently embedded in main.py)
└── README.md
---

## ⚙️ Key Design Decisions

- Multithreading used to separate UI rendering from control logic
- Interrupt-driven encoder for responsiveness
- Display updates optimized using UpdateDisplay flag
- Software timing loop used for clock tick (no RTC module yet)
- State machine approach for UI modes

---

## 🧪 Current Limitations

- No hardware RTC (time resets on reboot)
- Alarm triggering logic not fully implemented
- No snooze functionality yet
- PCB not designed or fabricated yet
- Enclosure design not started
- Audio output stage not yet integrated

---

## 🧭 TODO (Next Steps)

### Clock System
- Add RTC module (or NTP sync via Pico W)
- Implement alarm trigger logic
- Add snooze + alarm stop actions
- Add 12/24-hour format toggle

### Radio System
- Improve frequency tuning stability
- Add station presets
- Improve audio output stage integration

### Hardware
- Design 2-layer PCB (required for course)
- Component layout optimization
- Power regulation design (battery support if possible)

### UI/UX
- Improve menu navigation
- Add clearer mode indicators
- Refine display layout

### Enclosure
- Animal-themed casing design
- Physical interface ergonomics
- Assembly planning

---

## 🏁 Project Status

| Component        | Status        |
|----------------|--------------|
| Clock Logic     | In Progress |
| Alarm System    | Partial     |
| Radio Control   | Working     |
| OLED UI         | Working     |
| Encoder Input   | Working     |
| PCB Design      | Not Started |
| Enclosure       | Not Started |

---

## Course Context

ECE 299 Project: Clock-radio system using a single Raspberry Pi Pico W with:
- SPI display interface
- FM radio tuning and playback
- Encoder-based UI control
- Full PCB + enclosure design requirement

---

## External Libraries

- SSD1309 OLED driver (`ssd1309.py`)  
  Source: https://github.com/rdagger/micropython-ssd1309
  Used for SPI communication with the SSD1309 OLED display.
## Notes

This is a prototype implementation focused on validating core functionality before hardware finalization. The architecture is designed to scale into the final PCB-based system.
