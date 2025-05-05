#include <DFRobot_PN532.h>
#include <WiFi.h>
#include <HTTPClient.h>

// WiFi credentials
const char* ssid = "Proximus-Home-2918";
const char* password = "wj6xupaprwsd4";

// Flask server details
const char* serverUrl = "http://192.168.129.36:5000/receive_nfc";  // POST endpoint

#define  PN532_IRQ      (2)
#define  POLLING        (0)

// Use this line for a breakout or shield with an I2C connection
DFRobot_PN532_IIC  nfc(PN532_IRQ, POLLING); 
DFRobot_PN532::sCard_t NFCcard;

void setup() {
  Serial.begin(115200);
  
  // Connect to WiFi
  WiFi.begin(ssid, password);
  Serial.println("Connecting to WiFi...");
  
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("");
  Serial.println("WiFi connected");
  Serial.println("IP address: ");
  Serial.println(WiFi.localIP());
  
  // Initialize the NFC module
  while (!nfc.begin()) {
    Serial.println("NFC module initialization failed");
    delay(1000);
  }        
  Serial.println("Please place the NFC card/tag on module to read UID..... ");
}

void sendNfcDataToServer() {
  HTTPClient http;
  
  // Prepare the request
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");
  
  // Build UID string
  String uid = "";
  for (int i = 0; i < NFCcard.uidlenght; i++) {
    if (NFCcard.uid[i] < 0x10) uid += "0";
    uid += String(NFCcard.uid[i], HEX);
  }
  uid.toUpperCase();

  // Create JSON payload with all card details
  String jsonPayload = "{";
  jsonPayload += "\"uid\":\"" + uid + "\",";
  jsonPayload += "\"type\":\"" + String(NFCcard.cardType) + "\",";
  jsonPayload += "\"manufacturer\":\"" + String(NFCcard.Manufacturer) + "\",";
  jsonPayload += "\"size\":" + String(NFCcard.size);
  jsonPayload += "}";

  // Send the request
  int httpResponseCode = http.POST(jsonPayload);
  
  if (httpResponseCode > 0) {
    String response = http.getString();
    Serial.println("HTTP Response code: " + String(httpResponseCode));
    Serial.println("Response: " + response);
  } else {
    Serial.print("Error on sending POST: ");
    Serial.println(httpResponseCode);
  }
  
  http.end();
}

void loop() {
  // Scan NFC card
  if (nfc.scan()) {
    // Read the card information
    NFCcard = nfc.getInformation();
    
    // Send NFC data to Flask server
    if (WiFi.status() == WL_CONNECTED) {
      sendNfcDataToServer();
    } else {
      Serial.println("WiFi not connected");
    }
    
    delay(2000); // Prevent multiple rapid reads of the same card
  }
}