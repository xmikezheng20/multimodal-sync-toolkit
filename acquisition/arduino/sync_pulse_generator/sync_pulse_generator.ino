// Serial-controlled sync pulse generator.
//
// Send "1" over serial to enable the pulse train.
// Send "0" over serial to stop the pulse train and hold the output low.

int pulseEnabled = 0;
String serialInput = "0";

const int syncPin = 11;
const unsigned long pulseHighUs = 9926;
const unsigned long pulseLowUs = 9926;

void setup() {
  pinMode(syncPin, OUTPUT);
  digitalWrite(syncPin, LOW);
  Serial.begin(9600);
}

void loop() {
  // Bonsai and the Arduino IDE Serial Monitor send simple text commands.
  // toInt() converts "1" to 1 and "0" to 0.
  if (Serial.available() > 0) {
    serialInput = Serial.readString();
    pulseEnabled = serialInput.toInt();
  }

  // If pulseEnabled is 1, the sync pin is high for pulseHighUs.
  // If pulseEnabled is 0, the sync pin remains low.
  digitalWrite(syncPin, pulseEnabled);
  delayMicroseconds(pulseHighUs);

  // The output is always pulled low between pulses. This also ensures that
  // sending "0" stops the train with the sync line in the low state.
  digitalWrite(syncPin, LOW);
  delayMicroseconds(pulseLowUs);
}
