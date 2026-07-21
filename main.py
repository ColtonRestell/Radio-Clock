from machine import Pin, I2C, SPI, PWM
import time
import _thread
from ssd1309 import Display


# =====================================================================
# HARDWARE CONFIGURATION & PIN OUTS
# =====================================================================

SCREEN_WIDTH = 128
SCREEN_HEIGHT = 64

# Encoder pins - NO internal pull needed. The external hardware
# debounce network already biases these lines cleanly (verified: stable
# resting state, clean 4-state Gray code cycle on rotation). Adding an
# internal Pin.PULL_UP here fights that network and breaks the encoder.
EncoderA = Pin(4, Pin.IN)
EncoderB = Pin(2, Pin.IN)

# Mode button (active low): short press = change mode / snooze,
# long press = arm/disarm alarm / stop alarm (see Button class + main loop)
ModeButton = Pin(15, Pin.IN, Pin.PULL_UP)

# Sound-select button (active low): short press = cycle alarm sound + preview it
SoundButton = Pin(14, Pin.IN, Pin.PULL_UP)

# Alarm audio output (PWM square wave -> piezo/speaker)
AudioPin = Pin(16)

# Display SPI pins
spi_sck = Pin(18)
spi_sda = Pin(19)
spi_res = Pin(21)
spi_dc  = Pin(20)
spi_cs  = Pin(17)
SPI_DEVICE = 0


# =====================================================================
# ALARM SOUNDS (procedural tone sequences)
#
# Each sound is a list of (frequency_hz, duration_ms) notes.
# frequency_hz == 0 means "rest" (silence) for that duration.
# To add a new sound, just add a new list here and its name to
# SOUND_NAMES - nothing else needs to change.
#
# To later swap these for real recordings (e.g. an actual rooster crow),
# replace the body of AudioEngine.tick() with WAV-sample playback; every
# other call site (PlayAlarm/StopAlarm/the button/alarm code) stays the
# same because they only ever call the engine's play()/stop() API.
# =====================================================================

SOUND_NAMES = ["Rooster", "Bell", "Beep", "Birds", "Radio"]

# All alarm choices start at this level (0-15).  For Radio, this is the
# radio-chip volume; for the tone sounds, it controls the PWM output level.
ALARM_VOLUME = 10

SOUNDS = {
    "Rooster": [
        (800, 150), (0, 40), (1200, 180), (0, 40),
        (900, 320), (0, 500),
    ],
    "Bell": [
        (1000, 120), (0, 60),
        (1000, 120), (0, 60),
        (1000, 120), (0, 60),
        (1000, 120), (0, 500),
    ],
    "Beep": [
        (2000, 150), (0, 150),
        (2000, 150), (0, 150),
        (2000, 150), (0, 500),
    ],
    "Birds": [
        (1800, 70), (0, 35), (2200, 70), (0, 35),
        (1600, 70), (0, 35), (2000, 90), (0, 500),
    ],
}


# =====================================================================
# AUDIO ENGINE (non-blocking tone sequencer)
#
# Call PlayAlarm(name, loop) to start, StopAlarm() to stop, and
# AudioTick(now) once per main-loop iteration to advance playback.
# Nothing here ever blocks, so it never interferes with the encoder,
# buttons, or radio.
# =====================================================================

class AudioEngine:
    def __init__(self, pin):
        self.pwm = PWM(pin)
        self.pwm.duty_u16(0)
        self.active = False
        self.loop = False
        self.sound_name = None
        self.notes = None
        self.index = 0
        self.note_start = 0

    def play(self, sound_name, loop=True, volume=ALARM_VOLUME):
        if sound_name not in SOUNDS:
            return
        self.sound_name = sound_name
        self.notes = SOUNDS[sound_name]
        self.loop = loop
        self.index = 0
        self.active = True
        self.note_start = time.ticks_ms()
        self.volume = max(0, min(15, volume))
        self._apply_note(self.notes[0])

    def stop(self):
        self.active = False
        self.pwm.duty_u16(0)

    def _apply_note(self, note):
        freq, _duration = note
        if freq <= 0:
            self.pwm.duty_u16(0)
        else:
            self.pwm.freq(freq)
            self.pwm.duty_u16((32768 * self.volume) // 15)

    def tick(self, now):
        if not self.active:
            return
        _freq, duration = self.notes[self.index]
        if time.ticks_diff(now, self.note_start) >= duration:
            self.index += 1
            if self.index >= len(self.notes):
                if self.loop:
                    self.index = 0
                else:
                    self.stop()
                    return
            self.note_start = now
            self._apply_note(self.notes[self.index])


Audio = AudioEngine(AudioPin)

def PlayAlarm(sound_name, loop=True):
    Audio.play(sound_name, loop, ALARM_VOLUME)

def StopAlarm():
    Audio.stop()


# =====================================================================
# BUTTON DEBOUNCE (shared by both physical buttons)
#
# update(now) returns 'short', 'long', or None. Debounce timing and
# long-press timing are both handled here so no button-handling code
# in the main loop needs to duplicate this logic.
# =====================================================================

class Button:
    def __init__(self, pin, debounce_ms=50, long_press_ms=1000):
        self.pin = pin
        self.debounce_ms = debounce_ms
        self.long_press_ms = long_press_ms
        self.last_raw = pin.value()
        self.debounced = self.last_raw
        self.last_change = time.ticks_ms()
        self.press_start = 0
        self.long_fired = False

    def update(self, now):
        event = None
        raw = self.pin.value()

        if raw != self.last_raw:
            self.last_change = now
        self.last_raw = raw

        if time.ticks_diff(now, self.last_change) > self.debounce_ms:
            if raw != self.debounced:
                self.debounced = raw
                if self.debounced == 0:
                    # just pressed
                    self.press_start = now
                    self.long_fired = False
                else:
                    # just released
                    if not self.long_fired:
                        event = 'short'

        if self.debounced == 0 and not self.long_fired:
            if time.ticks_diff(now, self.press_start) > self.long_press_ms:
                self.long_fired = True
                event = 'long'

        return event


# =====================================================================
# GLOBAL MULTI-THREAD STATE
# =====================================================================

Count = 2
FrequencyStep = 139
UpdateDisplay = True
PrevAB = (EncoderA.value() << 1) | EncoderB.value()

RadioNeedsUpdate = False

hour = 0
minute = 0
alm_hour = 0
alm_min = 0
seconds = 0

# Raw position trackers for smooth half-step encoder debouncing
encoder_pos_vol  = Count * 2
encoder_pos_freq = FrequencyStep * 2
encoder_pos_hr   = hour * 2
encoder_pos_min  = minute * 2
encoder_pos_ahr  = alm_hour * 2
encoder_pos_amin = alm_min * 2

last_second_tick = time.ticks_ms()
AdjustMode = 0

# --- Alarm state machine ---
AlarmArmed = False          # was "LP" - now ONLY controls whether the alarm can fire
AlarmFiring = False         # alarm is actively ringing right now
AlarmRingStart = 0          # ticks_ms() when it started ringing (for the 30s auto-snooze)
PreAlarmMute = False        # radio mute state to restore after the alarm ends
PreAlarmVolume = 0          # radio volume to restore after the alarm ends

SnoozeActive = False
SnoozeUntilMinute = 0       # minute-of-day (0-1439) when a snoozed alarm should re-fire

AlarmSoundIndex = 0
AlarmSound = SOUND_NAMES[AlarmSoundIndex]

alarm_flash_state = False
alarm_flash_last = time.ticks_ms()

AUTO_SNOOZE_MS = 30000      # auto-snooze if the alarm isn't handled within 30s


# =====================================================================
# CORE 0: ENCODER ISR
#
# Decode only - no blocking calls (no I2C) inside the ISR. Blocking
# calls here previously caused missed edges and broke one direction.
# =====================================================================

def VolumeEncoderInterrupt(pin):
    global Count, PrevAB, UpdateDisplay, AdjustMode, RadioNeedsUpdate
    global encoder_pos_vol, encoder_pos_freq, encoder_pos_hr, encoder_pos_min, encoder_pos_ahr, encoder_pos_amin
    global hour, minute, alm_hour, alm_min, FrequencyStep

    table = [[0, -1, +1, 0], [+1, 0, 0, -1], [-1, 0, 0, +1], [0, +1, -1, 0]]
    curr = (EncoderA.value() << 1) | EncoderB.value()
    delta = table[PrevAB][curr]
    PrevAB = curr

    if delta == 0:
        return

    # MODE 0: VOLUME
    if AdjustMode == 0:
        new_pos = encoder_pos_vol + delta
        if 0 <= new_pos <= 30:
            encoder_pos_vol = new_pos
            new_vol = encoder_pos_vol // 2
            if new_vol != Count:
                Count = new_vol
                RadioNeedsUpdate = True
                UpdateDisplay = True

    # MODE 1: FREQUENCY
    elif AdjustMode == 1:
        new_pos = encoder_pos_freq + delta
        if 0 <= new_pos <= 400:
            encoder_pos_freq = new_pos
            new_step = encoder_pos_freq // 2
            if new_step != FrequencyStep:
                FrequencyStep = new_step
                RadioNeedsUpdate = True
                UpdateDisplay = True

    # MODE 2: HOUR
    elif AdjustMode == 2:
        encoder_pos_hr = (encoder_pos_hr + delta) % 48
        new_val = encoder_pos_hr // 2
        if new_val != hour:
            hour = new_val
            UpdateDisplay = True

    # MODE 3: MINUTE
    elif AdjustMode == 3:
        encoder_pos_min = (encoder_pos_min + delta) % 120
        new_val = encoder_pos_min // 2
        if new_val != minute:
            minute = new_val
            UpdateDisplay = True

    # MODE 4: ALARM HOUR
    elif AdjustMode == 4:
        encoder_pos_ahr = (encoder_pos_ahr + delta) % 48
        new_val = encoder_pos_ahr // 2
        if new_val != alm_hour:
            alm_hour = new_val
            UpdateDisplay = True

    # MODE 5: ALARM MINUTE
    elif AdjustMode == 5:
        encoder_pos_amin = (encoder_pos_amin + delta) % 120
        new_val = encoder_pos_amin // 2
        if new_val != alm_min:
            alm_min = new_val
            UpdateDisplay = True


# =====================================================================
# RADIO CHIP DRIVER
# =====================================================================

class Radio:
    def __init__(self, NewFrequency, NewVolume, NewMute):
        self.Volume = 2
        self.Frequency = 88
        self.Mute = False
        self.needs_tune = True

        self.SetVolume(NewVolume)
        self.SetFrequency(NewFrequency)
        self.SetMute(NewMute)

        self.i2c_sda = Pin(26)
        self.i2c_scl = Pin(27)
        self.i2c_device = 1
        self.i2c_device_address = 0x10
        self.Settings = bytearray(8)

        self.radio_i2c = I2C(self.i2c_device, scl=self.i2c_scl, sda=self.i2c_sda, freq=200000)
        self.ProgramRadio()

    def SetVolume(self, NewVolume):
        try:
            NewVolume = int(NewVolume)
        except:
            return False
        if not isinstance(NewVolume, int) or (NewVolume < 0 or NewVolume >= 16):
            return False
        self.Volume = NewVolume
        return True

    def SetFrequency(self, NewFrequency):
        try:
            NewFrequency = float(NewFrequency)
        except:
            return False
        if not isinstance(NewFrequency, float) or (NewFrequency < 88.0 or NewFrequency > 108.0):
            return False
        self.Frequency = NewFrequency
        self.needs_tune = True
        return True

    def SetMute(self, NewMute):
        try:
            self.Mute = bool(int(NewMute))
        except:
            return False
        return True

    def ComputeChannelSetting(self, Frequency):
        Frequency = int(Frequency * 10) - 870
        ByteCode = bytearray(2)
        ByteCode[0] = (Frequency >> 2) & 0xFF
        ByteCode[1] = ((Frequency & 0x03) << 6) & 0xC0
        return ByteCode

    def UpdateSettings(self):
        self.Settings = bytearray(8)
        self.Settings[0] = 0x80 if self.Mute else 0xC0
        self.Settings[1] = 0x09 | 0x04

        channel = self.ComputeChannelSetting(self.Frequency)
        self.Settings[2] = channel[0]
        self.Settings[3] = channel[1]

        if self.needs_tune:
            self.Settings[3] |= 0x10
            self.needs_tune = False

        self.Settings[4] = 0x04
        self.Settings[5] = 0x00
        self.Settings[6] = 0x84
        self.Settings[7] = 0x80 + self.Volume
        self.Settings = self.Settings[:8]

    def ProgramRadio(self):
        self.UpdateSettings()
        self.radio_i2c.writeto(self.i2c_device_address, self.Settings)


# =====================================================================
# CORE 1: DISPLAY THREAD
# =====================================================================

def display_core_thread():
    global UpdateDisplay, Count, AdjustMode, seconds, hour, minute, alm_hour, alm_min
    global AlarmFiring, alarm_flash_state, AlarmArmed, AlarmSound, SnoozeActive, SnoozeUntilMinute

    oled_spi = SPI(SPI_DEVICE, baudrate=1000000, sck=spi_sck, mosi=spi_sda)

    oled = Display(
        spi=oled_spi,
        cs=spi_cs,
        dc=spi_dc,
        rst=spi_res,
        width=SCREEN_WIDTH,
        height=SCREEN_HEIGHT,
        flip=False
    )

    mode_names = ["VOL", "FREQ", "HOUR", "MIN", "ALM HR", "ALM MIN"]

    while True:
        if UpdateDisplay:
            UpdateDisplay = False
            oled.clear_buffers()

            if AlarmFiring:
                # --- Ringing screen ---
                if alarm_flash_state:
                    oled.draw_text8x8(0, 0, "!!! ALARM !!!")
                oled.draw_text8x8(0, 16, "Sound: %s" % AlarmSound)
                oled.draw_text8x8(0, 32, "Long : Stop")
                oled.draw_text8x8(0, 40, "Short: Snooze")

            else:
                # --- Normal clock / status screen ---
                oled.draw_text8x8(0, 0, "Alarm: %02d:%02d" % (alm_hour, alm_min))
                oled.draw_text8x8(99, 0, "ON" if AlarmArmed else "OFF")

                if SnoozeActive:
                    oled.draw_text8x8(0, 8, "Snooze til %02d:%02d" %
                                       (SnoozeUntilMinute // 60, SnoozeUntilMinute % 60))
                else:
                    oled.draw_text8x8(0, 8, "Sound: %s" % AlarmSound)

                oled.draw_text8x8(0, 16, "Time : %02d:%02d:%02d" % (hour, minute, seconds))
                oled.draw_text8x8(0, 24, "Freq : %5.1f MHz" % fm_radio.Frequency)
                oled.draw_text8x8(0, 32, "Vol  : %2d/15" % Count)
                oled.draw_text8x8(0, 40, "Mode : %s" % mode_names[AdjustMode])

                bar_width = int((Count / 15) * 128)
                oled.draw_rectangle(0, 56, bar_width, 5)

            oled.present()

        time.sleep_ms(15)


# =====================================================================
# STARTUP
# =====================================================================

fm_radio = Radio(98.5, 2, False)

def StartAlarmOutput():
    if AlarmSound == "Radio":
        StopAlarm()  # make sure an earlier tone preview is not still playing
        fm_radio.SetVolume(ALARM_VOLUME)
        fm_radio.SetMute(False)
        fm_radio.ProgramRadio()
    else:
        fm_radio.SetMute(True)
        fm_radio.ProgramRadio()
        PlayAlarm(AlarmSound, loop=True)

def StopAlarmOutput():
    StopAlarm()
    fm_radio.SetVolume(PreAlarmVolume)
    fm_radio.SetMute(PreAlarmMute)
    fm_radio.ProgramRadio()

EncoderA.irq(handler=VolumeEncoderInterrupt, trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, hard=False)
EncoderB.irq(handler=VolumeEncoderInterrupt, trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, hard=False)

_thread.start_new_thread(display_core_thread, ())

ModeBtn = Button(ModeButton)
SoundBtn = Button(SoundButton)


# =====================================================================
# MAIN LOOP
# =====================================================================

while True:
    now = time.ticks_ms()

    # --- Radio update (moved out of the encoder ISR) ---
    if RadioNeedsUpdate:
        RadioNeedsUpdate = False
        fm_radio.SetVolume(Count)
        fm_radio.SetFrequency(round(88.0 + (FrequencyStep * 0.1), 1))
        fm_radio.ProgramRadio()

    # --- Audio engine (advances whatever alarm sound is playing) ---
    Audio.tick(now)

    # --- Mode button: dual purpose depending on whether the alarm is ringing ---
    mode_event = ModeBtn.update(now)
    if mode_event:
        if AlarmFiring:
            if mode_event == 'short':
                # SNOOZE
                StopAlarmOutput()
                AlarmFiring = False
                SnoozeActive = True
                SnoozeUntilMinute = ((hour * 60 + minute) + 10) % 1440
                UpdateDisplay = True
            elif mode_event == 'long':
                # STOP FOR THE DAY (alarm stays armed for tomorrow)
                StopAlarmOutput()
                AlarmFiring = False
                SnoozeActive = False
                UpdateDisplay = True
        else:
            if mode_event == 'short':
                AdjustMode = (AdjustMode + 1) % 6
                UpdateDisplay = True
            elif mode_event == 'long':
                # A long press after snoozing cancels the snooze too.
                if SnoozeActive:
                    SnoozeActive = False
                    AlarmArmed = False
                else:
                    AlarmArmed = not AlarmArmed
                UpdateDisplay = True

    # --- Sound-select button: cycle + preview (only when alarm isn't ringing) ---
    sound_event = SoundBtn.update(now)
    if sound_event == 'short' and not AlarmFiring:
        AlarmSoundIndex = (AlarmSoundIndex + 1) % len(SOUND_NAMES)
        AlarmSound = SOUND_NAMES[AlarmSoundIndex]
        if AlarmSound == "Radio":
            StopAlarm()  # Radio is not previewed until the alarm fires.
        else:
            PlayAlarm(AlarmSound, loop=False)
        UpdateDisplay = True

    # --- Auto-snooze if the alarm has been ringing, unattended, too long ---
    if AlarmFiring and time.ticks_diff(now, AlarmRingStart) >= AUTO_SNOOZE_MS:
        StopAlarmOutput()
        AlarmFiring = False
        SnoozeActive = True
        SnoozeUntilMinute = ((hour * 60 + minute) + 10) % 1440
        UpdateDisplay = True

    # --- System timer (1 real second per tick) ---
    time_advanced = False

    while time.ticks_diff(now, last_second_tick) >= 1000:
        last_second_tick = time.ticks_add(last_second_tick, 1000)
        seconds += 1
        time_advanced = True

        if seconds >= 60:
            seconds = 0
            minute += 1
            encoder_pos_min = minute * 2

            if minute >= 60:
                minute = 0
                encoder_pos_min = 0
                hour += 1
                encoder_pos_hr = hour * 2

                if hour >= 24:
                    hour = 0
                    encoder_pos_hr = 0

        # Fires exactly once per second, only on the :00 mark
        now_minute_of_day = hour * 60 + minute

        should_ring = False
        if AlarmArmed and not AlarmFiring and not SnoozeActive:
            if now_minute_of_day == (alm_hour * 60 + alm_min) and seconds == 0:
                should_ring = True
        if SnoozeActive and not AlarmFiring:
            if now_minute_of_day == SnoozeUntilMinute and seconds == 0:
                should_ring = True
                SnoozeActive = False

        if should_ring:
            print("ALARM TRIGGERED!")
            PreAlarmMute = fm_radio.Mute
            PreAlarmVolume = fm_radio.Volume

            AlarmFiring = True
            AlarmRingStart = now
            alarm_flash_state = True
            alarm_flash_last = now
            StartAlarmOutput()
            UpdateDisplay = True

    # --- Alarm flash (only matters while ringing) ---
    if AlarmFiring:
        if time.ticks_diff(now, alarm_flash_last) >= 300:
            alarm_flash_last = time.ticks_add(alarm_flash_last, 300)
            alarm_flash_state = not alarm_flash_state
            UpdateDisplay = True

    if time_advanced:
        UpdateDisplay = True

    time.sleep_ms(20)

