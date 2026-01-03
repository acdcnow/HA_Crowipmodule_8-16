# Crow/AAP Alarm IP Module

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Maintainer](https://img.shields.io/badge/maintainer-acdcnow-blue)](https://github.com/acdcnow)
[![Version](https://img.shields.io/badge/version-1.1.4-green)]()

**A robust Home Assistant integration for Crow Runner and AAP (Arrowhead Alarm Products) alarm systems via the IP Module.**

This integration provides local, real-time control and monitoring of your alarm system without relying on cloud services.
This is a custom component for Home Assistant to integrate **Crow Runner** alarm systems equipped with the **IP Module** (IA-IP-MODULE) running Firmware Ver 2.10.3628 2017 Oct 20 09:48:43.

## ✨ Features

* **Full Control:** Arm Away, Arm Home (Stay), Disarm, and Trigger Panic directly from Home Assistant.
* **Instant Feedback:** Uses a persistent TCP connection for immediate state updates.
* **Multi-Area:** Supports systems with up to 2 separate partitions (Area A & B).
* **Zone Monitoring:** Configure and monitor up to **16 zones** with specific types (Window, Door, Motion, Smoke, etc.).
* **Output Control:** Control the **2 switchable outputs** (e.g., for gates or garage doors).
* **System Health:** Dedicated binary sensors for Mains Power, Battery Status, Tamper, and Phone Line status.
* **Auto-Reconnect:** Built-in logic to handle network interruptions and restore connection automatically.
* **Multilingual:** Interface available in English, German, French, Italian, and Spanish.

---

## ⚙️ Configuration

Setup is handled entirely through the Home Assistant UI.

1.  Go to **Settings** > **Devices & Services**.
2.  Click **Add Integration** and search for **Crow/AAP Alarm IP Module**.
3.  **Connection:** Enter the IP address and port (default `5002`) of your IP Module.
4.  **Areas:** Select if you use 1 or 2 areas and name them.
5.  **Outputs:** Name your 2 outputs (Output 1 & Output 2).
6.  **Zones:** Configure up to 16 zones across multiple pages (4 zones per page). You can assign custom names and select the specific device class (e.g., `window`, `motion`, `smoke`) for proper icon and state representation in Home Assistant.

---

## 🎮 Entities Created

Once configured, the integration will create the following entities:

* **Alarm Control Panel:** `alarm_control_panel.area_1` (and `area_2` if enabled).
* **Switches:** `switch.output_1` and `switch.output_2`.
* **Binary Sensors:**
    * One sensor for each configured Zone (e.g., `binary_sensor.kitchen_window`).
    * System sensors: `Mains Power`, `System Battery`, `Tamper`, `Phone Line`, `Dialler`.
* **Sensor:** A text sensor showing the raw status message from the panel (e.g., "Ready", "Mains Failure").

---

## ⚠️ Important Notes

1.  **Single Connection:** The IP Module hardware typically supports only **one** active TCP connection. Ensure no other software (like the Crow configuration tool) is connected to the module while Home Assistant is running.
2.  **Reloading:** If you reload the integration, there is a safety delay of 2 seconds to allow the previous network socket to close cleanly before reconnecting.
3.  **Initial State:** After a restart, the entity states might show as "Unknown" for a few seconds until the alarm panel sends its full status dump.

---

## 🐛 Troubleshooting

If you need to debug issues, you can enable verbose logging by adding this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.crowipmodule: debug
    pycrowipmodule: debug

## Credits

Based on the `pycrowipmodule` library.
Original custom component author: @febalci.
Refactored for Home Assistant 2025+ with Config Flow support.
