# Brain ↔ Edge Communication Contract

**Version:** 1.0
**Status:** AUTHORITATIVE
**Derived From:** FAILURE_MATRIX.md, EEMM_SPEC.md
**Last Updated:** 2026-01-30

---

## 1. Purpose

This document defines the **exact communication protocol** between:
- **Brain** (Python, Cloud/Server) - Policy, Consent, Intelligence
- **Edge** (Rust, Local) - Safety, Detection, Execution

All messages MUST conform to these schemas. No ad-hoc fields allowed.

---

## 2. Transport Layer

### 2.1 Primary: WebSocket

```
Edge ←→ Brain: wss://brain.homeai.io/edge/{edge_id}
```

- Persistent connection
- Binary frames (MessagePack)
- Ping/pong every 5 seconds
- Reconnect with exponential backoff (1s, 2s, 4s, 8s, max 30s)

### 2.2 Fallback: HTTP

```
Edge → Brain: POST https://brain.homeai.io/api/edge/event
Brain → Edge: POST https://edge.local:8443/api/brain/command
```

Used when WebSocket fails. Edge MUST expose local HTTPS endpoint.

---

## 3. Message Envelope

All messages use this envelope:

```json
{
  "v": 1,                          // Protocol version
  "id": "uuid-v4",                 // Message ID
  "ts": 1706640000,                // Unix timestamp (seconds)
  "type": "event|command|response|heartbeat",
  "payload": { ... }               // Type-specific payload
}
```

---

## 4. Edge → Brain Messages

### 4.1 Heartbeat

Sent every 5 seconds.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "heartbeat",
  "payload": {
    "edge_id": "edge-001",
    "status": "normal|degraded|eemm|ha_bypass",
    "uptime_seconds": 86400,
    "ha_connected": true,
    "pending_events": 0,
    "last_emergency_at": null,
    "eemm_active": false,
    "storage_used_pct": 45,
    "sensors_online": 12,
    "sensors_offline": 1
  }
}
```

### 4.2 Event

Sent when sensor/detection event occurs.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "event",
  "payload": {
    "event_id": "evt-uuid",
    "event_type": "MotionDetected|DoorOpened|SmokeDetected|...",
    "category": "user|anomaly|emergency",
    "severity": "info|warning|critical|fatal",
    "source": "edge|ha|sensor",
    "device_id": "sensor-001",
    "zone": "living_room",
    "user_id": 1,
    "confidence": 0.85,
    "data": {
      // Event-specific data
    },
    "corroborating_events": ["evt-uuid-2"],
    "requires_decision": true,
    "decision_timeout_ms": 2000
  }
}
```

### 4.3 Emergency Event

Special event for emergencies. MUST trigger immediate Brain response.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "event",
  "payload": {
    "event_id": "emg-uuid",
    "event_type": "IntrusionDetected|FireDetected|ViolenceDetected|...",
    "category": "emergency",
    "severity": "critical",
    "emergency_type": "intrusion|fire|violence|water_leak|power_emergency|panic",
    "source": "edge",
    "device_id": "camera-001",
    "zone": "front_door",
    "user_id": 1,
    "confidence": 0.92,
    "multiple_sensors": true,
    "duration_seconds": 5.2,
    "evidence": {
      "has_local_recording": true,
      "recording_path": "/var/homeai/rec/emg-uuid.mp4",
      "snapshot_base64": "..."  // Optional, small thumbnail
    },
    "requires_decision": true,
    "decision_timeout_ms": 2000
  }
}
```

### 4.4 EEMM Status

Sent when Edge enters/exits EEMM.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "event",
  "payload": {
    "event_id": "eemm-uuid",
    "event_type": "EemmEntered|EemmExited",
    "category": "emergency",
    "severity": "critical",
    "trigger": "brain_timeout|network_down|decision_timeout|explicit|ambiguous",
    "emergency_id": "emg-uuid",  // Original emergency
    "emergency_type": "intrusion",
    "actions_taken": ["siren_on", "lights_on", "recording_started"],
    "eemm_duration_seconds": 0,  // 0 on entry, actual duration on exit
    "exit_reason": null  // On exit: "brain_reconnected|user_cancel|timeout|all_clear"
  }
}
```

### 4.5 Confirmation Response (Local)

When user responds to confirmation via local interface during EEMM.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "event",
  "payload": {
    "event_id": "conf-resp-uuid",
    "event_type": "ConfirmationResponseLocal",
    "category": "user",
    "original_event_id": "emg-uuid",
    "confirmation_id": 123,
    "response": "confirmed_safe|confirmed_threat",
    "response_method": "keypad|app_lan|physical_button",
    "responded_at": 1706640000
  }
}
```

### 4.6 Event Buffer Flush

Sent when Edge reconnects after partition.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "event",
  "payload": {
    "event_id": "flush-uuid",
    "event_type": "BufferFlush",
    "category": "system",
    "buffer_start_ts": 1706630000,
    "buffer_end_ts": 1706640000,
    "event_count": 42,
    "events": [
      // Array of buffered events
    ]
  }
}
```

---

## 5. Brain → Edge Messages

### 5.1 Heartbeat Response

Sent in response to Edge heartbeat.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "response",
  "payload": {
    "reply_to": "heartbeat-msg-id",
    "status": "ok",
    "brain_time": 1706640000,
    "pending_commands": 0,
    "confirmations_sync": [
      // Active confirmations Edge should know about
      {
        "confirmation_id": 123,
        "event_id": "emg-uuid",
        "emergency_type": "intrusion",
        "created_at": 1706639970,
        "expires_at": 1706640000,
        "fallback_actions": ["alert_trusted", "call_police"]
      }
    ],
    "policy_version": "2024-01-30-001",
    "policy_update_available": false
  }
}
```

### 5.2 Escalation Outcome

Sent in response to emergency event. Edge MUST receive within 2 seconds.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "command",
  "payload": {
    "command": "escalation_outcome",
    "reply_to": "emg-uuid",
    "event_id": "emg-uuid",
    "emergency_type": "intrusion",
    "confidence_tier": "high",
    "decision_id": "dec-uuid",

    "immediate_actions": [
      {
        "action": "local_alarm",
        "params": {}
      },
      {
        "action": "alert_owner",
        "params": {
          "channel": "telegram",
          "message": "Intrusion detected at front door"
        }
      }
    ],

    "deferred_actions": [
      {
        "action": "alert_trusted",
        "params": {}
      }
    ],

    "blocked_actions": [
      {
        "action": "call_police",
        "reason": "no_consent"
      }
    ],

    "confirmation": {
      "required": true,
      "confirmation_id": 124,
      "window_seconds": 30,
      "fallback_actions": ["alert_trusted"]
    },

    "issued_at": 1706640000,
    "ttl_seconds": 60,

    "reason": "High confidence intrusion with multiple sensors"
  }
}
```

### 5.3 Action Command

Direct command from Brain to Edge.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "command",
  "payload": {
    "command": "execute_action",
    "action": "siren_on|siren_off|lights_on|lights_off|lock_doors|unlock_doors|start_recording|stop_recording",
    "params": {
      "zone": "all",
      "duration_seconds": 60
    },
    "reason": "User requested via app",
    "actor": "user|system|admin",
    "actor_id": 1
  }
}
```

### 5.4 Enter EEMM Command

Brain can explicitly tell Edge to enter EEMM.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "command",
  "payload": {
    "command": "enter_eemm",
    "reason": "Brain maintenance window",
    "duration_seconds": 300,
    "emergency_type": null  // null = no active emergency
  }
}
```

### 5.5 Policy Update

Sent when escalation policy changes.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "command",
  "payload": {
    "command": "policy_update",
    "policy_version": "2024-01-30-002",
    "eemm_config": {
      "brain_heartbeat_timeout_ms": 5000,
      "brain_decision_timeout_ms": 2000,
      "max_eemm_duration_minutes": 30,
      "recording_max_minutes": 5
    },
    "emergency_configs": {
      "intrusion": {
        "siren_enabled": true,
        "lights_enabled": true
      },
      "violence": {
        "siren_enabled": false,
        "lights_enabled": false
      }
    },
    "notification_config": {
      "owner_telegram_chat_id": "123456789",
      "owner_phone": "+1234567890"
    },
    "cancel_pin_hash": "sha256:..."
  }
}
```

### 5.6 Confirmation Update

Sent when confirmation status changes.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "command",
  "payload": {
    "command": "confirmation_update",
    "confirmation_id": 123,
    "event_id": "emg-uuid",
    "status": "confirmed_safe|confirmed_threat|cancelled",
    "resolved_by": "user|system|admin",
    "resolved_at": 1706640000
  }
}
```

---

## 6. Response Messages

### 6.1 Generic Acknowledgment

Edge acknowledges Brain commands.

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "response",
  "payload": {
    "reply_to": "command-msg-id",
    "status": "ok|error",
    "error": null,
    "executed_actions": ["siren_on", "lights_on"],
    "failed_actions": []
  }
}
```

---

## 7. SLA Requirements

| Message Type | Max Latency | Timeout Behavior |
|--------------|-------------|------------------|
| **Heartbeat** | 5 seconds | Edge enters DEGRADED, then EEMM if persists |
| **Emergency Event → Outcome** | 2 seconds | Edge enters EEMM, executes local response |
| **Normal Event** | 30 seconds | Retry with backoff |
| **Action Command** | 1 second | Log failure, continue |
| **Policy Update** | N/A | Apply on next restart if missed |

---

## 8. Error Handling

### 8.1 Error Response

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "response",
  "payload": {
    "reply_to": "msg-id",
    "status": "error",
    "error": {
      "code": "INVALID_PAYLOAD|TIMEOUT|UNAUTHORIZED|INTERNAL",
      "message": "Human readable message",
      "retryable": true
    }
  }
}
```

### 8.2 Error Codes

| Code | Meaning | Retryable |
|------|---------|-----------|
| `INVALID_PAYLOAD` | Schema validation failed | No |
| `TIMEOUT` | Request timed out | Yes |
| `UNAUTHORIZED` | Edge not registered | No |
| `INTERNAL` | Server error | Yes |
| `RATE_LIMITED` | Too many requests | Yes (with backoff) |
| `NOT_FOUND` | Resource not found | No |

---

## 9. Security

### 9.1 Authentication

Edge authenticates with Brain using:

```
Authorization: Bearer <edge_token>
X-Edge-ID: edge-001
X-Edge-Signature: HMAC-SHA256(payload, edge_secret)
```

### 9.2 Token Refresh

Edge token expires every 24 hours. Refresh flow:

```
Edge → Brain: POST /auth/edge/refresh
{
  "edge_id": "edge-001",
  "refresh_token": "..."
}

Brain → Edge:
{
  "access_token": "...",
  "expires_in": 86400
}
```

### 9.3 Message Signing

All commands from Brain are signed:

```json
{
  "v": 1,
  "id": "...",
  "ts": 1706640000,
  "type": "command",
  "payload": { ... },
  "signature": "HMAC-SHA256(payload, shared_secret)"
}
```

Edge MUST verify signature before executing commands.

---

## 10. Versioning

### 10.1 Protocol Version

Current version: `1`

Version is included in every message envelope (`"v": 1`).

### 10.2 Backward Compatibility

- Brain MUST support current version and previous version
- Edge MUST reject messages with unsupported version
- Version bump requires coordinated deployment

---

## 11. Message Flow Diagrams

### 11.1 Normal Emergency Flow

```
Edge                          Brain
  │                             │
  │──── Emergency Event ───────>│
  │                             │ (EscalationEngine.decide)
  │<─── Escalation Outcome ─────│
  │                             │
  │ (Execute immediate_actions) │
  │                             │
  │──── Action ACK ────────────>│
  │                             │
  │    [30s confirmation window]│
  │                             │
  │<─── Confirmation Update ────│ (user confirmed_safe)
  │                             │
  │ (Cancel deferred actions)   │
  │                             │
```

### 11.2 EEMM Flow (Brain Timeout)

```
Edge                          Brain
  │                             │
  │──── Emergency Event ───────>│
  │                             │
  │     [2s timeout waiting]    │ (Brain slow/dead)
  │                             │
  │ *** ENTER EEMM ***          │
  │ (Execute EEMM actions)      │
  │                             │
  │──── EEMM Entered Event ────>│ (if connection exists)
  │                             │
  │     [Brain recovers]        │
  │                             │
  │<─── Heartbeat Response ─────│
  │                             │
  │ *** EXIT EEMM ***           │
  │                             │
  │──── EEMM Exited Event ─────>│
  │                             │
```

### 11.3 Confirmation Takeover Flow

```
Edge                          Brain
  │                             │
  │──── Emergency Event ───────>│
  │                             │
  │<─── Escalation Outcome ─────│ (confirmation required)
  │                             │
  │     [Brain dies]            │
  │                             │
  │──── Heartbeat ─────────────>│ (no response)
  │                             │
  │ *** ENTER EEMM ***          │
  │ (Take over confirmation)    │
  │                             │
  │     [Confirmation expires]  │
  │                             │
  │ (Execute EEMM actions only) │
  │ (NOT full fallback_actions) │
  │                             │
  │     [Brain recovers]        │
  │                             │
  │<─── Heartbeat Response ─────│
  │                             │
  │──── Confirmation Resolved ─>│
  │                             │
```

---

## 12. Implementation Checklist

### Brain (Python)

- [ ] WebSocket server for Edge connections
- [ ] Message envelope validation
- [ ] Heartbeat handler with confirmation sync
- [ ] Emergency event → EscalationEngine integration
- [ ] Escalation outcome message builder
- [ ] Command signing
- [ ] Edge authentication

### Edge (Rust)

- [ ] WebSocket client with reconnection
- [ ] Message envelope parsing
- [ ] Heartbeat sender (5s interval)
- [ ] Emergency event builder
- [ ] Escalation outcome parser
- [ ] Action executor
- [ ] Command signature verification
- [ ] EEMM trigger on timeout
- [ ] Confirmation state tracking
- [ ] Event buffering during partition
- [ ] Buffer flush on reconnect

---

## 13. Shared Types (Cross-Language)

These types MUST be identical in Python and Rust:

```
# Python: contracts/types.py
# Rust: src/contracts/types.rs

EventCategory: user | anomaly | emergency
EventSeverity: debug | info | warning | critical | fatal
EmergencyType: intrusion | fire | violence | water_leak | power_emergency | panic
EscalationAction: local_alarm | alert_owner | alert_family | alert_trusted | call_police | call_fire | call_ambulance | record_evidence | lockdown | disable_device
ConfirmationStatus: pending | confirmed_safe | confirmed_threat | expired | cancelled
EdgeStatus: normal | degraded | eemm | ha_bypass | recovery
EemmTrigger: brain_timeout | network_down | decision_timeout | explicit | ambiguous
EemmExitReason: brain_reconnected | user_cancel | timeout | all_clear
```

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-30 | Claude | Initial contract |

---

## Approval

- [ ] Architecture Review
- [ ] Security Review (authentication, signing)
- [ ] API Review
