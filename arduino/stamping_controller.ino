/*
  Optional custom Arduino protocol example.

  Use GRBL if your writing-robot controller already runs GRBL.
  Use this sketch only if you want a custom Arduino firmware that replies "ok"
  after real physical movement is finished.

  Reserved paper roller signal: D8.
*/

const int PAPER_FEED_PIN = 8;

void setup() {
  Serial.begin(115200);
  pinMode(PAPER_FEED_PIN, OUTPUT);
  digitalWrite(PAPER_FEED_PIN, LOW);
  Serial.println("ok");
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) {
    return;
  }

  if (line.startsWith("G0") || line.startsWith("G1")) {
    runMotion(line);
    Serial.println("ok");
    return;
  }

  if (line.startsWith("G4")) {
    runDwell(line);
    Serial.println("ok");
    return;
  }

  if (line.startsWith("M100")) {
    feedPaper();
    Serial.println("ok");
    return;
  }

  if (line == "?") {
    Serial.println("<Idle|MPos:0.000,0.000,0.000>");
    return;
  }

  Serial.print("error: unsupported command ");
  Serial.println(line);
}

void runMotion(String line) {
  // TODO: parse X/Y/Z/F and drive your stepper drivers.
  // Important: print ok only after physical movement is complete.
}

void runDwell(String line) {
  float seconds = readParam(line, 'P', 0.0);
  if (seconds > 0.0) {
    delay((unsigned long)(seconds * 1000.0));
  }
}

void feedPaper() {
  digitalWrite(PAPER_FEED_PIN, HIGH);
  delay(300);
  digitalWrite(PAPER_FEED_PIN, LOW);
}

float readParam(String line, char key, float fallback) {
  int index = line.indexOf(key);
  if (index < 0) {
    return fallback;
  }
  int end = index + 1;
  while (end < line.length() && line[end] != ' ') {
    end++;
  }
  return line.substring(index + 1, end).toFloat();
}

