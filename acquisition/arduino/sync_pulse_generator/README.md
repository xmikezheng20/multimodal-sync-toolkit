# Sync Pulse Generator

This Arduino sketch generates a serial-controlled digital sync pulse train.

## Test Wiring

Use digital pin `11` as the sync output pin for the LED test.

Wire the circuit as:

```text
Arduino pin 11 -> resistor -> LED long leg
LED short leg -> Arduino GND
```

In later steps, the same sync output is distributed to the recording devices using the appropriate wiring and voltage-level handling for each device. The LED can remain as a simple visual indicator of whether the pulse train is running.

## Upload And Test

Open `sync_pulse_generator.ino` in the Arduino IDE and upload it to the board.

Open the Arduino IDE Serial Monitor. Set the baud rate to `9600`. Send `1` to start the pulse train and `0` to stop it.

At the default 50 Hz sync rate, the LED appears continuously on while the pulse train is running and off when it is stopped.
