"""
simulator/protocol_simulator.py — Artificial Protocol Simulator

Simulates real building automation protocols:
  - BACnet/IP  (Building Automation and Control Networks)
  - MQTT       (IoT sensor telemetry)
  - Modbus TCP (legacy HVAC/electrical PLCs)

Each protocol generates realistic raw packets, which are then
parsed by a ProtocolParser and routed into the agent memory system.

In a real deployment, these parsers would receive live data from
physical gateways (e.g. Niagara N4, Johnson Controls Metasys, Siemens Desigo).
"""

import random
import struct
import json
import time
import threading
from datetime import datetime
from typing import Optional


# ── BACnet Object Type codes (subset of ASHRAE 135) ────────────────────────
BACNET_OBJECT_TYPES = {
    0:  "analog-input",       # sensor reading
    1:  "analog-output",      # setpoint
    2:  "analog-value",       # calculated value
    3:  "binary-input",       # on/off sensor
    4:  "binary-output",      # on/off control
    8:  "device",             # device descriptor
    13: "multi-state-input",  # enum sensor (e.g. mode)
    19: "trend-log",          # historical log
}

BACNET_PROPERTIES = {
    85: "present-value",
    77: "object-name",
    28: "description",
    111: "status-flags",
    117: "units",
}

BACNET_UNITS = {
    62: "degrees-celsius",
    63: "degrees-fahrenheit",
    98: "percent",
    82: "watts",
    119: "pascals",
    47: "liters-per-second",
}

# ── MQTT topic schema used by CBRE IoT gateway ──────────────────────────────
# Pattern: cbre/{building_id}/{floor}/{system}/{device_id}/{measurement}
MQTT_TOPIC_SCHEMA = "cbre/{building}/{floor}/{system}/{device}/{measurement}"

MQTT_SYSTEMS = ["hvac", "electrical", "elevator", "access", "environmental", "plumbing"]

# ── Modbus register map for HVAC PLCs ───────────────────────────────────────
MODBUS_REGISTER_MAP = {
    100: {"name": "supply_air_temp",     "unit": "°C",  "scale": 0.1},
    101: {"name": "return_air_temp",     "unit": "°C",  "scale": 0.1},
    102: {"name": "chiller_efficiency",  "unit": "%",   "scale": 0.1},
    103: {"name": "fan_speed_rpm",       "unit": "RPM", "scale": 1.0},
    104: {"name": "static_pressure",     "unit": "Pa",  "scale": 1.0},
    105: {"name": "co2_ppm",             "unit": "ppm", "scale": 1.0},
    106: {"name": "humidity_pct",        "unit": "%",   "scale": 0.1},
    107: {"name": "valve_position",      "unit": "%",   "scale": 0.1},
    200: {"name": "main_power_kw",       "unit": "kW",  "scale": 0.01},
    201: {"name": "floor_power_kw",      "unit": "kW",  "scale": 0.01},
    202: {"name": "power_factor",        "unit": "",    "scale": 0.001},
    300: {"name": "water_pressure_bar",  "unit": "bar", "scale": 0.01},
    301: {"name": "flow_rate_lps",       "unit": "L/s", "scale": 0.1},
}


# ═══════════════════════════════════════════════════════════════════════════
# PACKET GENERATORS
# ═══════════════════════════════════════════════════════════════════════════

class BACnetPacket:
    """
    Simulates a BACnet/IP ReadPropertyMultiple response packet.
    Based on ASHRAE 135-2020 standard.
    """

    def __init__(self, device_id: int, floor: str, object_type: int,
                 object_instance: int, value: float, status_flags: int = 0):
        self.device_id       = device_id
        self.floor           = floor
        self.object_type     = object_type
        self.object_instance = object_instance
        self.value           = value
        self.status_flags    = status_flags  # bit 0=alarm, 1=fault, 2=overridden, 3=out-of-service
        self.timestamp       = datetime.now().isoformat()

    def to_bytes(self) -> bytes:
        """Serialize to a simplified BACnet APDU (Application Protocol Data Unit)."""
        # BACnet Virtual Link Control header (4 bytes)
        bvlc_type    = 0x81        # BACnet/IP
        bvlc_func    = 0x0A        # Original-Unicast-NPDU
        apdu_type    = 0x30        # Complex-ACK PDU
        service      = 0x0E        # readPropertyMultiple-ACK

        payload = struct.pack(
            '>BBBBHHHH',
            bvlc_type,
            bvlc_func,
            apdu_type,
            service,
            self.device_id,
            self.object_type,
            self.object_instance,
            int(self.value * 10),
        ) + struct.pack('>B', self.status_flags)

        length = len(payload) + 4
        header = struct.pack('>BBH', bvlc_type, bvlc_func, length)
        return header + payload[4:]  # simplified

    def to_dict(self) -> dict:
        flags = self.status_flags
        return {
            "protocol":        "BACnet/IP",
            "standard":        "ASHRAE 135-2020",
            "device_id":       self.device_id,
            "floor":           self.floor,
            "object_type":     BACNET_OBJECT_TYPES.get(self.object_type, "unknown"),
            "object_instance": self.object_instance,
            "property":        "present-value",
            "value":           round(self.value, 2),
            "status_flags": {
                "alarm":          bool(flags & 0b0001),
                "fault":          bool(flags & 0b0010),
                "overridden":     bool(flags & 0b0100),
                "out_of_service": bool(flags & 0b1000),
            },
            "timestamp": self.timestamp,
        }

    def __repr__(self):
        d = self.to_dict()
        return (f"BACnet[device={self.device_id} floor={self.floor} "
                f"obj={d['object_type']}#{self.object_instance} "
                f"val={self.value:.2f} flags={self.status_flags:04b}]")


class MQTTPacket:
    """
    Simulates an MQTT sensor telemetry message.
    Follows CBRE's IoT topic schema.
    """

    def __init__(self, building: str, floor: str, system: str,
                 device_id: str, measurement: str, value, unit: str = "",
                 qos: int = 1, retain: bool = False):
        self.building    = building
        self.floor       = floor
        self.system      = system
        self.device_id   = device_id
        self.measurement = measurement
        self.value       = value
        self.unit        = unit
        self.qos         = qos
        self.retain      = retain
        self.timestamp   = datetime.now().isoformat()
        self.topic       = f"cbre/{building}/floor{floor}/{system}/{device_id}/{measurement}"

    def to_bytes(self) -> bytes:
        """Serialize to MQTT 3.1.1 PUBLISH packet bytes."""
        payload_dict = {
            "v": self.value,
            "u": self.unit,
            "ts": self.timestamp,
            "q": self.qos,
        }
        payload_bytes = json.dumps(payload_dict).encode("utf-8")
        topic_bytes   = self.topic.encode("utf-8")

        # Fixed header: packet type 3 (PUBLISH), QoS in flags
        fixed_header = (0x30 | (self.qos << 1) | (0x01 if self.retain else 0x00))
        # Variable header: topic length (2 bytes) + topic
        var_header = struct.pack('>H', len(topic_bytes)) + topic_bytes
        # Remaining length (variable encoding)
        remaining = len(var_header) + len(payload_bytes)

        return bytes([fixed_header, remaining]) + var_header + payload_bytes

    def to_dict(self) -> dict:
        return {
            "protocol":    "MQTT 3.1.1",
            "topic":       self.topic,
            "qos":         self.qos,
            "retain":      self.retain,
            "building":    self.building,
            "floor":       self.floor,
            "system":      self.system,
            "device_id":   self.device_id,
            "measurement": self.measurement,
            "value":       self.value,
            "unit":        self.unit,
            "timestamp":   self.timestamp,
        }

    def __repr__(self):
        return (f"MQTT[{self.topic} = {self.value}{self.unit} "
                f"qos={self.qos}]")


class ModbusPacket:
    """
    Simulates a Modbus TCP response frame (Function Code 0x03 - Read Holding Registers).
    """

    def __init__(self, unit_id: int, floor: str, register: int,
                 raw_value: int, transaction_id: Optional[int] = None):
        self.unit_id        = unit_id
        self.floor          = floor
        self.register       = register
        self.raw_value      = raw_value
        self.transaction_id = transaction_id or random.randint(1, 65535)
        self.timestamp      = datetime.now().isoformat()

        reg_info            = MODBUS_REGISTER_MAP.get(register, {})
        self.reg_name       = reg_info.get("name", f"register_{register}")
        self.unit           = reg_info.get("unit", "")
        self.scale          = reg_info.get("scale", 1.0)
        self.scaled_value   = round(raw_value * self.scale, 2)

    def to_bytes(self) -> bytes:
        """Serialize to Modbus TCP Application Data Unit (MBAP + PDU)."""
        # MBAP Header (6 bytes): transaction_id, protocol_id=0, length, unit_id
        protocol_id = 0x0000  # Modbus protocol
        pdu_length  = 3 + 2   # func_code(1) + byte_count(1) + register_data(2) + unit_id(1)

        mbap = struct.pack('>HHHB',
            self.transaction_id,
            protocol_id,
            pdu_length,
            self.unit_id,
        )
        # PDU: function code 0x03, byte count, register value (2 bytes big-endian)
        pdu = struct.pack('>BBH', 0x03, 0x02, self.raw_value)
        return mbap + pdu

    def to_dict(self) -> dict:
        return {
            "protocol":       "Modbus TCP",
            "standard":       "IEC 61158",
            "transaction_id": self.transaction_id,
            "unit_id":        self.unit_id,
            "floor":          self.floor,
            "function_code":  "0x03 (Read Holding Registers)",
            "register":       self.register,
            "register_name":  self.reg_name,
            "raw_value":      self.raw_value,
            "scaled_value":   self.scaled_value,
            "unit":           self.unit,
            "timestamp":      self.timestamp,
        }

    def __repr__(self):
        return (f"Modbus[unit={self.unit_id} floor={self.floor} "
                f"reg={self.register}({self.reg_name}) "
                f"raw={self.raw_value} → {self.scaled_value}{self.unit}]")


# ═══════════════════════════════════════════════════════════════════════════
# PROTOCOL PARSER  — converts raw packets into agent-ready events
# ═══════════════════════════════════════════════════════════════════════════

class ProtocolParser:
    """
    Translates parsed protocol packets into agent event dicts.
    This is what a real BACnet/MQTT gateway driver would do.
    """

    # Thresholds for anomaly detection
    THRESHOLDS = {
        "supply_air_temp":    {"warn": 24.0,  "crit": 27.0,  "unit": "°C"},
        "return_air_temp":    {"warn": 26.0,  "crit": 29.0,  "unit": "°C"},
        "chiller_efficiency": {"warn": 80.0,  "crit": 70.0,  "unit": "%",  "invert": True},
        "co2_ppm":            {"warn": 1000,  "crit": 1500,  "unit": "ppm"},
        "humidity_pct":       {"warn": 65.0,  "crit": 75.0,  "unit": "%"},
        "main_power_kw":      {"warn": 450.0, "crit": 520.0, "unit": "kW"},
        "fan_speed_rpm":      {"warn": 1400,  "crit": 1600,  "unit": "RPM"},
    }

    @staticmethod
    def parse_bacnet(packet: BACnetPacket) -> Optional[dict]:
        d = packet.to_dict()
        flags = d["status_flags"]
        is_alarm = flags["alarm"] or flags["fault"]
        salience = 0.85 if is_alarm else 0.45

        obj_type = d["object_type"]
        val      = d["value"]
        floor    = d["floor"]

        if "temp" in obj_type or obj_type == "analog-input":
            label = "temperature"
            if val > 28:
                content = (f"BACnet [{obj_type}#{d['object_instance']}] "
                           f"Floor {floor}: temperature {val}°C — "
                           f"{'ALARM' if is_alarm else 'above threshold'}. "
                           f"Status flags: alarm={flags['alarm']} fault={flags['fault']}")
                salience = 0.9 if is_alarm else 0.7
            else:
                content = (f"BACnet [{obj_type}#{d['object_instance']}] "
                           f"Floor {floor}: temperature reading {val}°C — nominal.")
        else:
            content = (f"BACnet [{obj_type}#{d['object_instance']}] "
                       f"Floor {floor}: value={val} "
                       f"{'[ALARM]' if is_alarm else '[OK]'}")

        return {
            "agent":       "ops",
            "event_type":  "bacnet_sensor",
            "content":     content,
            "floor":       floor,
            "salience":    min(1.0, salience),
            "anomaly":     is_alarm,
            "protocol":    "BACnet/IP",
            "raw_packet":  d,
        }

    @staticmethod
    def parse_mqtt(packet: MQTTPacket) -> Optional[dict]:
        d       = packet.to_dict()
        system  = d["system"]
        measure = d["measurement"]
        value   = d["value"]
        floor   = d["floor"]
        salience = 0.4

        # Route by system type
        if system == "hvac":
            if measure == "supply_air_temp" and value > 26:
                salience = 0.85
                content = (f"MQTT [cbre/{d['building']}/floor{floor}/hvac/{d['device_id']}] "
                           f"Supply air temp {value}°C — exceeds comfort threshold (26°C). "
                           f"Tenant impact likely.")
            elif measure == "chiller_efficiency" and value < 75:
                salience = 0.9
                content = (f"MQTT [hvac/{d['device_id']}] Floor {floor}: "
                           f"Chiller efficiency {value}% — critical degradation. "
                           f"Failure risk elevated.")
            elif measure == "co2_ppm" and value > 1000:
                salience = 0.75
                content = (f"MQTT [environmental/{d['device_id']}] Floor {floor}: "
                           f"CO₂ {value}ppm — above ASHRAE 62.1 guideline (1000ppm). "
                           f"Ventilation review required.")
            else:
                content = (f"MQTT [{system}/{d['device_id']}] Floor {floor}: "
                           f"{measure}={value}{d['unit']} — nominal.")

        elif system == "elevator":
            salience = 0.7 if value != 1.0 else 0.3
            status   = "operational" if value == 1.0 else "FAULT DETECTED"
            content  = (f"MQTT [elevator/{d['device_id']}] Floor {floor}: "
                        f"status={status} (raw={value}). "
                        f"{'Inspect immediately.' if value != 1.0 else 'Normal operation.'}")

        elif system == "electrical":
            if value > 480:
                salience = 0.8
                content = (f"MQTT [electrical/{d['device_id']}] Floor {floor}: "
                           f"Power draw {value}kW — above normal range. "
                           f"Investigate load spike.")
            else:
                content = (f"MQTT [electrical/{d['device_id']}] Floor {floor}: "
                           f"Power {value}kW — within limits.")

        else:
            content = (f"MQTT [{system}/{d['device_id']}] Floor {floor}: "
                       f"{measure}={value}{d['unit']}")

        return {
            "agent":      "ops",
            "event_type": f"mqtt_{system}",
            "content":    content,
            "floor":      floor.lstrip("floor").strip(),
            "salience":   salience,
            "anomaly":    salience >= 0.8,
            "protocol":   "MQTT 3.1.1",
            "raw_packet": d,
        }

    @staticmethod
    def parse_modbus(packet: ModbusPacket) -> Optional[dict]:
        d       = packet.to_dict()
        reg     = d["register_name"]
        val     = d["scaled_value"]
        floor   = d["floor"]
        unit    = d["unit"]
        thres   = ProtocolParser.THRESHOLDS.get(reg)
        salience = 0.35

        if thres:
            invert = thres.get("invert", False)  # lower = worse (e.g. efficiency)
            is_crit = (val < thres["crit"]) if invert else (val > thres["crit"])
            is_warn = (val < thres["warn"]) if invert else (val > thres["warn"])

            if is_crit:
                salience = 0.92
                level    = "CRITICAL"
            elif is_warn:
                salience = 0.72
                level    = "WARNING"
            else:
                level = "OK"

            content = (f"Modbus [unit={d['unit_id']} reg={d['register']}({reg})] "
                       f"Floor {floor}: {val}{unit} [{level}]"
                       + (f" — exceeds threshold ({thres['crit']}{unit})." if is_crit else
                          f" — approaching threshold." if is_warn else " — nominal."))
        else:
            content = (f"Modbus [unit={d['unit_id']} reg={d['register']}({reg})] "
                       f"Floor {floor}: {val}{unit}")

        return {
            "agent":      "ops",
            "event_type": f"modbus_{reg}",
            "content":    content,
            "floor":      floor,
            "salience":   salience,
            "anomaly":    salience >= 0.8,
            "protocol":   "Modbus TCP",
            "raw_packet": d,
        }


# ═══════════════════════════════════════════════════════════════════════════
# BUILDING SIGNAL GENERATOR  — produces realistic time-series packets
# ═══════════════════════════════════════════════════════════════════════════

class BuildingSignalGenerator:
    """
    Generates a continuous stream of realistic protocol packets for a building.
    Simulates normal operation with occasional anomalies.
    """

    FLOORS         = ["3", "5", "7", "10", "12", "15", "18", "20"]
    BACNET_DEVICES = {
        "12": [1201, 1202, 1203],
        "7":  [701, 702],
        "15": [1501, 1502],
        "3":  [301],
    }
    MQTT_DEVICES   = {
        "hvac":        ["ahu-01", "ahu-02", "chiller-01"],
        "elevator":    ["elev-01", "elev-02", "elev-03"],
        "electrical":  ["panel-main", "panel-b"],
        "environmental": ["env-sensor-01"],
    }

    def __init__(self, building_id: str, anomaly_mode: bool = False):
        self.building_id  = building_id
        self.anomaly_mode = anomaly_mode

    def _jitter(self, base: float, pct: float = 0.05) -> float:
        return base * (1 + random.uniform(-pct, pct))

    def generate_bacnet_batch(self, floor: Optional[str] = None) -> list[BACnetPacket]:
        floor     = floor or random.choice(self.FLOORS)
        devices   = self.BACNET_DEVICES.get(floor, [random.randint(100, 1999)])
        packets   = []

        for device_id in devices[:2]:
            # Temperature sensor (object type 0 = analog-input)
            base_temp = 28.5 if (self.anomaly_mode and floor == "12") else 21.5
            temp      = self._jitter(base_temp, 0.08)
            status    = 0b0001 if temp > 27 else 0  # alarm flag if too hot
            packets.append(BACnetPacket(
                device_id=device_id, floor=floor,
                object_type=0, object_instance=1,
                value=temp, status_flags=status,
            ))

            # Fan status (object type 3 = binary-input)
            fan_ok = 0 if (self.anomaly_mode and random.random() < 0.3) else 1
            packets.append(BACnetPacket(
                device_id=device_id, floor=floor,
                object_type=3, object_instance=10,
                value=fan_ok, status_flags=(0b0010 if not fan_ok else 0),
            ))

        return packets

    def generate_mqtt_batch(self, floor: Optional[str] = None) -> list[MQTTPacket]:
        floor   = floor or random.choice(self.FLOORS)
        packets = []

        # HVAC telemetry
        hvac_dev = random.choice(self.MQTT_DEVICES["hvac"])
        base_eff = 65.0 if self.anomaly_mode else 88.0
        packets.append(MQTTPacket(
            building=self.building_id, floor=floor,
            system="hvac", device_id=hvac_dev,
            measurement="chiller_efficiency",
            value=round(self._jitter(base_eff, 0.06), 1), unit="%",
        ))
        base_temp = 29.0 if self.anomaly_mode else 21.0
        packets.append(MQTTPacket(
            building=self.building_id, floor=floor,
            system="hvac", device_id=hvac_dev,
            measurement="supply_air_temp",
            value=round(self._jitter(base_temp, 0.05), 1), unit="°C",
        ))

        # CO2
        base_co2 = 1400 if self.anomaly_mode else 680
        packets.append(MQTTPacket(
            building=self.building_id, floor=floor,
            system="environmental",
            device_id=random.choice(self.MQTT_DEVICES["environmental"]),
            measurement="co2_ppm",
            value=int(self._jitter(base_co2, 0.1)), unit="ppm",
        ))

        # Elevator (occasional fault)
        if random.random() < (0.25 if self.anomaly_mode else 0.05):
            packets.append(MQTTPacket(
                building=self.building_id, floor=floor,
                system="elevator",
                device_id=random.choice(self.MQTT_DEVICES["elevator"]),
                measurement="operational_status",
                value=0.0, unit="",
            ))

        return packets

    def generate_modbus_batch(self, floor: Optional[str] = None) -> list[ModbusPacket]:
        floor    = floor or random.choice(self.FLOORS)
        unit_id  = int(floor) if floor.isdigit() else 1
        packets  = []

        # Supply air temp
        base_temp = 285 if self.anomaly_mode else 215  # raw = scaled / 0.1
        packets.append(ModbusPacket(
            unit_id=unit_id, floor=floor,
            register=100,
            raw_value=int(self._jitter(base_temp, 0.08)),
        ))

        # Chiller efficiency
        base_eff = 680 if self.anomaly_mode else 880  # raw = scaled / 0.1
        packets.append(ModbusPacket(
            unit_id=unit_id, floor=floor,
            register=102,
            raw_value=int(self._jitter(base_eff, 0.06)),
        ))

        # Power draw
        base_pw = 48500 if self.anomaly_mode else 32000  # raw = scaled / 0.01
        packets.append(ModbusPacket(
            unit_id=unit_id, floor=floor,
            register=200,
            raw_value=int(self._jitter(base_pw, 0.05)),
        ))

        return packets

    def generate_full_scan(self, floor: Optional[str] = None) -> dict:
        """Generate one complete protocol scan across all three protocols."""
        floor   = floor or random.choice(self.FLOORS)
        bacnet  = self.generate_bacnet_batch(floor)
        mqtt    = self.generate_mqtt_batch(floor)
        modbus  = self.generate_modbus_batch(floor)
        return {
            "floor":   floor,
            "bacnet":  [p.to_dict() for p in bacnet],
            "mqtt":    [p.to_dict() for p in mqtt],
            "modbus":  [p.to_dict() for p in modbus],
            "scanned_at": datetime.now().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════
# LIVE PROTOCOL STREAM  — feeds parsed packets into agent memory
# ═══════════════════════════════════════════════════════════════════════════

class LiveProtocolStream:
    """
    Runs a background thread that continuously generates protocol packets
    and routes them into the agent memory system.
    """

    def __init__(self, building_id: str, interval_seconds: int = 30):
        self.building_id = building_id
        self.interval    = interval_seconds
        self._running    = False
        self._thread     = None
        self._lock       = threading.Lock()
        self.packet_log  = []   # last 50 packets for display

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        print(f"[LiveStream] Started — {self.building_id} @ {self.interval}s intervals")

    def stop(self):
        self._running = False
        print("[LiveStream] Stopped")

    def _loop(self):
        from agents import OpsAgent
        from agents.compression import CompressionEngine

        ops_agent  = OpsAgent(self.building_id)
        gen        = BuildingSignalGenerator(self.building_id)
        parser     = ProtocolParser()
        scan_count = 0

        while self._running:
            try:
                floor   = random.choice(BuildingSignalGenerator.FLOORS)
                packets = []

                # Rotate through protocols each scan
                protocol = ["bacnet", "mqtt", "modbus"][scan_count % 3]

                if protocol == "bacnet":
                    raw     = gen.generate_bacnet_batch(floor)
                    packets = [parser.parse_bacnet(p) for p in raw]
                elif protocol == "mqtt":
                    raw     = gen.generate_mqtt_batch(floor)
                    packets = [parser.parse_mqtt(p) for p in raw]
                else:
                    raw     = gen.generate_modbus_batch(floor)
                    packets = [parser.parse_modbus(p) for p in raw]

                for event in packets:
                    if event:
                        ops_agent.ingest(event)
                        with self._lock:
                            self._packet_log_append({
                                "protocol": event["protocol"],
                                "floor":    event["floor"],
                                "content":  event["content"][:80],
                                "salience": event["salience"],
                                "anomaly":  event["anomaly"],
                                "ts":       datetime.now().isoformat(),
                            })

                scan_count += 1

                # Compress every 5 scans
                if scan_count % 5 == 0:
                    threading.Thread(
                        target=lambda: CompressionEngine(self.building_id).run(),
                        daemon=True
                    ).start()

            except Exception as ex:
                print(f"[LiveStream] Error: {ex}")

            time.sleep(self.interval)

    def _packet_log_append(self, entry: dict):
        self.packet_log.append(entry)
        if len(self.packet_log) > 50:
            self.packet_log.pop(0)

    def get_recent_packets(self, limit: int = 20) -> list:
        with self._lock:
            return list(reversed(self.packet_log[-limit:]))

    def inject_anomaly(self, floor: str = "12"):
        """Inject a burst of anomaly packets on demand (e.g. for demo)."""
        from agents import OpsAgent
        ops_agent = OpsAgent(self.building_id)
        gen       = BuildingSignalGenerator(self.building_id, anomaly_mode=True)
        parser    = ProtocolParser()

        print(f"[LiveStream] Injecting anomaly burst on floor {floor}")
        for proto in ["bacnet", "mqtt", "modbus"]:
            if proto == "bacnet":
                raw = gen.generate_bacnet_batch(floor)
                evts = [parser.parse_bacnet(p) for p in raw]
            elif proto == "mqtt":
                raw = gen.generate_mqtt_batch(floor)
                evts = [parser.parse_mqtt(p) for p in raw]
            else:
                raw = gen.generate_modbus_batch(floor)
                evts = [parser.parse_modbus(p) for p in raw]

            for event in evts:
                if event:
                    ops_agent.ingest(event)
                    with self._lock:
                        self._packet_log_append({
                            "protocol": event["protocol"],
                            "floor":    event["floor"],
                            "content":  event["content"][:80],
                            "salience": event["salience"],
                            "anomaly":  True,
                            "ts":       datetime.now().isoformat(),
                        })


# ── Module-level singleton stream (started by routes.py) ───────────────────
_stream: Optional[LiveProtocolStream] = None

def get_stream(building_id: Optional[str] = None) -> Optional[LiveProtocolStream]:
    global _stream
    if _stream is None and building_id:
        _stream = LiveProtocolStream(building_id, interval_seconds=30)
    return _stream