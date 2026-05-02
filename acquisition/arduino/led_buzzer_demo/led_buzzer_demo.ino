// Simple audio-video demo stimulus.
//
// The LED and buzzer turn on together for 1 second, then remain off for
// 3 seconds. This creates a visible event for video and an audible event
// for audio recording.

const int ledPin = 8;
const int buzzerPin = 10;

const unsigned int buzzerFrequencyHz = 1000;
const unsigned long onDurationMs = 1000;
const unsigned long offDurationMs = 3000;

void setup() {
  pinMode(ledPin, OUTPUT);
  pinMode(buzzerPin, OUTPUT);
  digitalWrite(ledPin, LOW);
  digitalWrite(buzzerPin, LOW);
}

void loop() {
  digitalWrite(ledPin, HIGH);
  tone(buzzerPin, buzzerFrequencyHz);
  delay(onDurationMs);

  digitalWrite(ledPin, LOW);
  noTone(buzzerPin);
  delay(offDurationMs);
}
