"""
Protocol message building and parsing for the Midea QS2476-90 water softener.
Device type: 0xED, query body type: 0x09.
Byte offsets derived from T_0000_ED_10008619_2024092001.lua (1-indexed in Lua → 0-indexed here).
"""
from __future__ import annotations

from enum import IntEnum

from .const import DEVICE_TYPE, QUERY_BODY_TYPE

_QUERY_CMD_BODY_TYPE = 0x01  # body[0] sent in the outgoing query (Lua: bodyBytes[0]=0x01)
SET_BODY_TYPE = 0x15  # new-style ED set message, same family as water purifier

HEADER_LENGTH = 10

# Lua: leak_water_protection_value (byte18) is in units of 10 L.
_LEAK_THRESHOLD_UNIT_L = 10


class MessageType(IntEnum):
    set = 0x02
    query = 0x03
    notify = 0x04


# ------------------------------------------------------------------
# Request building
# ------------------------------------------------------------------

def _checksum(data: bytes | bytearray) -> int:
    return (~sum(data) + 1) & 0xFF


def _build_message(message_type: int, body_type: int | None, body_content: bytes | bytearray) -> bytes:
    """Assemble a complete Midea protocol message with header and checksum."""
    body = bytearray()
    if body_type is not None:
        body.append(body_type)
    body.extend(body_content)

    length = HEADER_LENGTH + len(body)
    header = bytearray([
        0xAA,           # flag
        length,         # total length
        DEVICE_TYPE,    # device type
        0x00,           # frame checksum (unused)
        0x00, 0x00,     # reserved
        0x00,           # frame ID
        0x00,           # frame protocol version
        0x00,           # device protocol version
        message_type,   # message type
    ])
    stream = header + body
    stream.append(_checksum(stream[1:]))
    return bytes(stream)


def build_query() -> bytes:
    """Build the status query message.
    Lua: bodyBytes={0x01,0x01}, bodyLength=#bodyBytes+1=3, msgLength=3+10+1=14 bytes.
    Body = [_QUERY_CMD_BODY_TYPE=0x01, bodyBytes[0]=0x01, bodyBytes[1]=0x01].
    """
    return _build_message(MessageType.query, _QUERY_CMD_BODY_TYPE, b"\x01\x01")


class SetParam(IntEnum):
    """16-bit parameter IDs for new-style set commands (param_low, param_high in packet)."""
    HARDNESS = 0x0100
    REGEN_INTERVAL = 0x0101
    REGEN_TIME = 0x0102
    REGEN_NOW = 0x0103
    SALT_SETTING = 0x0104
    SOFTEN = 0x0108
    ANTI_LEAKAGE = 0x010A
    INLET = 0x0200


def _pack_param(param: SetParam, value: int, addition: int = 0) -> bytearray:
    """Build a single 5-byte parameter pack: [param_low, param_high, value, add_low, add_high]."""
    return bytearray([
        param & 0xFF,
        (param >> 8) & 0xFF,
        value & 0xFF,
        addition & 0xFF,
        (addition >> 8) & 0xFF,
    ])


def build_set(param: SetParam, value: int, addition: int = 0) -> bytes:
    """Build a new-style set message for a single parameter."""
    pack = _pack_param(param, value, addition)
    # Body: [0x01, pack_count=1, ...5-byte pack...]
    body_content = bytearray([0x01, 0x01]) + pack
    return _build_message(MessageType.set, SET_BODY_TYPE, body_content)


# ------------------------------------------------------------------
# Convenience builders for each control
# ------------------------------------------------------------------

def build_set_soften(on: bool) -> bytes:
    return build_set(SetParam.SOFTEN, 0x01 if on else 0x00)

def build_set_inlet(on: bool) -> bytes:
    return build_set(SetParam.INLET, 0x01 if on else 0x00)

def build_set_anti_leakage(on: bool) -> bytes:
    return build_set(SetParam.ANTI_LEAKAGE, 0x01 if on else 0x00)

def build_set_hardness(ppm: int) -> bytes:
    # ppm fits in 16 bits; pass as addition, value byte unused (0x00)
    return build_set(SetParam.HARDNESS, 0x00, ppm)

def build_set_regen_interval(days: int) -> bytes:
    return build_set(SetParam.REGEN_INTERVAL, 0x00, days)

def build_set_regen_time(hour: int, minute: int) -> bytes:
    # addition_low = hour, addition_high = minute
    addition = hour | (minute << 8)
    return build_set(SetParam.REGEN_TIME, 0x00, addition)

def build_regen_now() -> bytes:
    return build_set(SetParam.REGEN_NOW, 0x01)


# ------------------------------------------------------------------
# Response parsing
# ------------------------------------------------------------------

class DeviceStatus:
    """Parsed status from a 0x09 query response body."""

    __slots__ = (
        "flow_rate",
        "soft_water_remaining",
        "water_consumption_raw",
        "water_consumption_total",
        "salt_remaining",
        "use_days",
        "water_hardness",
        "regen_interval",
        "regen_hour",
        "regen_min",
        "regen_seconds_remaining",
        "soften",
        "anti_leakage",
        "inlet",
        "standby",
        "regenerating",
        "leak_detected",
        "leak_threshold",
        "error",
    )

    def __init__(self) -> None:
        for slot in self.__slots__:
            setattr(self, slot, None)


def parse_response(raw: bytes | bytearray) -> DeviceStatus | None:
    """
    Parse a raw response from the device (full packet including header).
    Returns None if the packet is malformed or not a query/notify response.

    Lua mapping: byteN = messageBytes[N-10] = body[N-10] (body is 0-indexed, starts at raw[10]).
    All offsets verified against T_0000_ED_10008619_2024092001.lua assembleJsonByGlobalProperty().
    """
    if len(raw) < HEADER_LENGTH + 2:
        return None

    msg_type = raw[9]
    if msg_type not in (MessageType.query, MessageType.notify):
        return None

    # body = everything between header and trailing checksum byte
    body = raw[HEADER_LENGTH:-1]

    # body[0] = byte10 in Lua = response body type (must be 0x09)
    if len(body) < 1 or body[0] != QUERY_BODY_TYPE:
        return None

    # Minimum body length to read through salt_setting (body[20] = byte30)
    if len(body) < 21:
        return None

    s = DeviceStatus()

    # Lua byteN → body[N-10]. Field names match Lua stream keys.
    s.flow_rate             = body[2]                        # byte12: velocity, L/min
    s.soft_water_remaining  = body[3]  + (body[4]  << 8)    # byte13+14: soft_available, L
    s.water_consumption_raw = body[5]  + (body[6]  << 8)    # byte15+16: water_consumption, 100L units
    s.salt_remaining        = body[7]                        # byte17: left_salt, %
    s.leak_threshold        = body[8] * _LEAK_THRESHOLD_UNIT_L  # byte18: leak_water_protection_value, 10 L units → L
    s.water_hardness        = body[11] + (body[12] << 8)    # byte21+22: water_hardness, ppm (LE)
    s.regen_interval        = body[13]                       # byte23: flushing_days
    s.regen_hour            = body[14]                       # byte24: timing_regeneration_hour
    s.regen_min             = body[15]                       # byte25: timing_regeneration_min
    s.regen_seconds_remaining = body[16] + (body[17] << 8)  # byte26+27: regeneration_left_seconds
    s.use_days              = body[18] + (body[19] << 8)    # byte28+29: use_days

    # 4-byte soft water remaining in L — soft_available_big (byte31-34 → body[21:25])
    if len(body) >= 25:
        s.soft_water_remaining = (
            body[21] + (body[22] << 8) + (body[23] << 16) + (body[24] << 24)
        )

    # 4-byte total consumption in L — water_consumption_big (byte35-38 → body[25:29]), little-endian
    if len(body) >= 29:
        s.water_consumption_total = (
            body[25] + (body[26] << 8) + (body[27] << 16) + (body[28] << 24)
        )

    # Flags — byte61 → body[51]
    if len(body) >= 52:
        flags = body[51]
        s.soften       = bool(flags & 0x01)   # bit0: soften
        s.anti_leakage = bool(flags & 0x04)   # bit2: leak_water_protection
        s.leak_detected= bool(flags & 0x08)   # bit3: leak_water
        s.inlet        = bool(flags & 0x10)   # bit4: water_way
        s.standby      = bool(flags & 0x20)   # bit5: rsj_stand_by
        s.regenerating = bool(flags & 0x80)   # bit7: regeneration

    # Error — byte62 → body[52]
    if len(body) >= 53:
        s.error = body[52]

    return s
