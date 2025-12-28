# Crow/AAP Alarm IP Module for Home Assistant

This is a custom component for Home Assistant to integrate **Crow Runner** alarm systems equipped with the **IP Module** (IA-IP-MODULE) running Firmware Ver 2.10.3628 2017 Oct 20 09:48:43.

## ✨ Features

* **Alarm Control Panel:** Full support for Arm Away, Arm Home (Stay), and Disarm.
* **Real-time Updates:** Instant feedback via local TCP connection (no cloud required).
* **Multi-Area Support:** Supports up to 2 separate areas (Partitions A & B).
* **Zone Monitoring:** Monitor up to 16 zones with configurable types (Motion, Window, Door, etc.).
* **Output Control:** Control up to 2 outputs (e.g., for garage doors, gates, or lights).
* **System Status:** Binary sensors for Mains Power, Battery Status, Tamper, Phone Line, and Dialer.
* **Robust Connection:** Auto-reconnection logic and status synchronization upon Home Assistant restarts.
* **Multilingual:** Fully translated into English, German, French, Italian, and Spanish.

---

## 🚀 Installation

### Option 1: HACS (Recommended)
1.  Open HACS in Home Assistant.
2.  Go to "Integrations" > "Custom repositories".
3.  Add the URL of this repository and select **Integration** as the category.
4.  Click "Install".
5.  Restart Home Assistant.

### Option 2: Manual Installation
1.  Download the `custom_components/crowipmodule` folder from this repository.
2.  Copy the folder into your Home Assistant's `config/custom_components/` directory.
3.  Restart Home Assistant.

---

## ⚙️ Configuration

Once installed, the integration is configured via the Home Assistant UI (**Settings** -> **Devices & Services** -> **Add Integration** -> **Crow/AAP Alarm IP Module**).

### 1. Connection Settings
* **Host:** The IP address of your Crow IP Module.
* **Port:** Usually `5002`.
* **Keepalive:** Time in seconds to check connection health (Default: 60s).
* **Timeout:** Connection timeout (Default: 10s).

### 2. Device Quantities
You will be asked to define how many devices you have.
* **Number of Areas:** 1 or 2.
* **Number of Zones:** 1 to 16.

### 3. Naming & Setup
The configuration flow is paginated to keep the UI clean:
* **Areas:** Name your areas (e.g., "House", "Garage") and optionally set a PIN code.
* **Outputs:** Name your 2 switchable outputs.
* **Zones:** You will configure your zones in blocks of 4 per page. You can set the **Name** and the **Type** for each zone.

#### Available Zone Types:
* `window` (Default)
* `door`
* `motion`
* `smoke`
* `gas`
* `co` (Carbon Monoxide)
* `tamper`
* `safety`

---

## 🎮 Usage

### Alarm Control Panel
Two entities will be created (if 2 areas are selected), typically `alarm_control_panel.area_1` and `alarm_control_panel.area_2`.

* **Arm Away:** Activates the full alarm system.
* **Arm Home (Stay):** Activates the "Stay" mode (usually perimeter protection only).
* **Disarm:** Deactivates the alarm. Requires the user code configured in the panel or the integration settings.
* **Trigger:** Activates the Panic alarm.

### Switches (Outputs)
The integration creates exactly **2 switches** (`switch.output_1` and `switch.output_2`).
* These correspond to the controllable outputs on the alarm board.
* Often used for opening gates or triggering external sirens manually.

### Sensors
* **Binary Sensors:** Provide status for `Mains Power` (Connectivity), `System Battery`, `Tamper` (Sabotage), etc.
    * *Note:* Tamper shows `On` if sabotage is detected. Battery shows `On` if the battery is Low.
* **Text Sensor:** A diagnostic sensor showing the raw system status text (e.g., "Ready", "Power Failure").

---

## 🐛 Debugging & Logging

If you encounter issues or want to see the raw data coming from the alarm panel, you can enable debug logging.

Add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.crowipmodule: debug
    pycrowipmodule: debug
