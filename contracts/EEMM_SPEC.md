# Edge Emergency Minimal Mode (EEMM) Specification

**Version:** 1.0
**Status:** AUTHORITATIVE
**Derived From:** FAILURE_MATRIX.md (F01, F02, F06, F10)
**Last Updated:** 2026-01-30

---

## 1. Purpose

EEMM defines the **minimum guaranteed behavior** of HomeAI Edge when Brain is unavailable. This is the "reflex" layer - fast, deterministic, and safe.

**Philosophy:**
> When in doubt, protect the home. Don't think, act.

---

## 2. EEMM Trigger Conditions

Edge enters EEMM when ANY of these conditions are true during an emergency:

| Trigger | Detection Method | Threshold |
|---------|------------------|-----------|
| **T1: Brain Heartbeat Timeout** | No heartbeat response | > 5 seconds |
| **T2: Brain Decision Timeout** | Decision request sent, no response | > 2 seconds |
| **T3: Network Partition** | All outbound connections fail | > 5 seconds |
| **T4: Brain Explicit EEMM Command** | Brain sends `enter_eemm` command | Immediate |
| **T5: Ambiguous State** | State corruption detected | Immediate |

**Important:** EEMM is ONLY entered during active emergency. Normal operation with Brain down = "Degraded Mode" (different behavior).

---

## 3. EEMM Entry State Machine

```
                    EMERGENCY DETECTED
                           │
                           ▼
                  ┌─────────────────┐
                  │  Check Brain    │
                  │  Availability   │
                  └────────┬────────┘
                           │
            ┌──────────────┴──────────────┐
            │                             │
     Brain Available              Brain Unavailable
     (< 2s response)              (timeout/partition)
            │                             │
            ▼                             ▼
    ┌───────────────┐            ┌───────────────┐
    │ NORMAL MODE   │            │    EEMM       │
    │ Brain decides │            │ Edge decides  │
    └───────────────┘            └───────────────┘
```

---

## 4. EEMM Allowed Actions

These actions are **PRE-AUTHORIZED** and execute without Brain consultation:

| Action | Implementation | Notes |
|--------|---------------|-------|
| **SIREN_ON** | Activate all sirens | Max volume, all zones |
| **LIGHTS_ON** | All lights to 100% | Interior + exterior |
| **LIGHTS_STROBE** | Strobe pattern | If supported by hardware |
| **LOCAL_RECORDING** | Start recording | Max 5 minutes, local storage only |
| **OWNER_NOTIFY** | Send notification | Pre-configured channel only |
| **LOCK_DOORS** | Engage all locks | If lock hardware available |

### Action Priority Order

When entering EEMM, actions execute in this order:

```
1. SIREN_ON        (immediate - 0ms)
2. LIGHTS_ON       (immediate - 0ms)
3. LOCK_DOORS      (immediate - 0ms)
4. LOCAL_RECORDING (after 100ms)
5. OWNER_NOTIFY    (after 500ms)
```

**Rationale:** Physical deterrence first, then evidence, then notification.

---

## 5. EEMM Forbidden Actions

These actions are **NEVER** allowed in EEMM:

| Forbidden Action | Reason |
|------------------|--------|
| **CALL_POLICE** | Requires explicit consent + policy |
| **CALL_FIRE** | Requires explicit consent + policy |
| **CALL_AMBULANCE** | Requires explicit consent + policy |
| **ALERT_TRUSTED** | Requires Brain to resolve contacts |
| **CLOUD_UPLOAD** | Network may be down, don't block |
| **COMPLEX_REASONING** | No ML, no heuristics, no "maybe" |
| **CONSENT_OVERRIDE** | Never override user settings |
| **EXTEND_RECORDING** | 5 minute hard limit |

---

## 6. EEMM by Emergency Type

Different emergencies have slightly different EEMM responses:

### 6.1 Intrusion

```yaml
trigger: motion_in_secured_zone OR door_breach OR window_breach
actions:
  - SIREN_ON
  - LIGHTS_ON (all)
  - LOCK_DOORS
  - LOCAL_RECORDING
  - OWNER_NOTIFY
duration: until Brain available OR 30 minutes max
```

### 6.2 Fire

```yaml
trigger: smoke_detected OR heat_anomaly OR fire_sensor
actions:
  - SIREN_ON (fire pattern if available)
  - LIGHTS_ON (all, guide to exit)
  - UNLOCK_DOORS (fire safety - egress)
  - LOCAL_RECORDING
  - OWNER_NOTIFY
special: doors UNLOCK for fire (opposite of intrusion)
duration: until Brain available OR fire_all_clear
```

### 6.3 Violence

```yaml
trigger: violence_detected (audio/video)
actions:
  - LOCAL_RECORDING (evidence priority)
  - OWNER_NOTIFY
  - NO SIREN (could escalate situation)
  - NO LIGHTS CHANGE (could alert aggressor)
special: silent mode - evidence collection priority
duration: until Brain available OR 30 minutes max
```

### 6.4 Panic Button

```yaml
trigger: panic_button_pressed
actions:
  - SIREN_ON
  - LIGHTS_ON (all)
  - LOCAL_RECORDING
  - OWNER_NOTIFY
special: user explicitly requested help
duration: until Brain available OR user_cancel
```

### 6.5 Water Leak

```yaml
trigger: water_sensor_triggered
actions:
  - SIREN_ON (short burst, not continuous)
  - LIGHTS_ON (affected area)
  - VALVE_SHUTOFF (if available)
  - OWNER_NOTIFY
special: property protection, not personal safety
duration: until Brain available OR user_acknowledge
```

### 6.6 Power Emergency

```yaml
trigger: power_anomaly OR electrical_fault
actions:
  - SIREN_ON (short burst)
  - CIRCUIT_BREAKER_TRIP (if controllable)
  - OWNER_NOTIFY
special: prevent fire from electrical fault
duration: until Brain available OR user_acknowledge
```

---

## 7. EEMM Exit Conditions

Edge exits EEMM when ANY of these conditions are met:

| Exit Condition | Action |
|----------------|--------|
| **Brain Reconnects** | Sync state, transfer control to Brain |
| **User Cancel** | Via local interface (keypad, app on LAN) |
| **Timeout** | 30 minutes max EEMM duration |
| **All Clear Signal** | Sensor indicates threat resolved |

### Exit Procedure

```
1. Stop siren (if user cancel or all clear)
2. Maintain lights ON for 5 minutes
3. Continue recording until Brain sync
4. Flush event buffer to Brain
5. Report EEMM duration and actions taken
6. Return to NORMAL mode
```

---

## 8. EEMM State Persistence

Edge MUST persist EEMM state to survive restart:

```rust
struct EemmState {
    entered_at: u64,           // Unix timestamp
    trigger: EemmTrigger,      // Why we entered
    emergency_type: EmergencyType,
    actions_taken: Vec<EemmAction>,
    recording_started: bool,
    recording_path: Option<String>,
    owner_notified: bool,
    notification_channel: Option<String>,
    exit_reason: Option<EemmExitReason>,
    exited_at: Option<u64>,
}
```

**On Edge Restart During EEMM:**
1. Load persisted state
2. Resume EEMM (don't re-trigger actions already taken)
3. Continue countdown from where it stopped
4. Check if Brain is now available

---

## 9. Owner Notification in EEMM

Since Brain is unavailable, Edge uses **pre-configured direct channels**:

### 9.1 Supported Channels (Priority Order)

1. **Local Push** - HomeAI app on LAN (no internet needed)
2. **Telegram Bot** - Direct API call (if internet available)
3. **SMS Gateway** - Direct API call (if configured)
4. **Email** - Direct SMTP (lowest priority)

### 9.2 Notification Content

```
🚨 HOMEAI EMERGENCY ALERT

Type: [INTRUSION/FIRE/etc]
Location: [Zone name]
Time: [Timestamp]
Status: EEMM ACTIVE (Brain Offline)

Actions Taken:
- Siren activated
- Lights on
- Recording started

⚠️ System operating in local safety mode.
Cloud services unavailable.

To cancel false alarm:
- Use keypad code: [PIN]
- Or app on local network
```

### 9.3 Notification Retry

```
Attempt 1: Immediate
Attempt 2: +30 seconds
Attempt 3: +60 seconds
Attempt 4: +120 seconds
Max attempts: 4
```

---

## 10. EEMM Local Interface

User MUST be able to interact with Edge locally during EEMM:

### 10.1 Cancel Methods

| Method | Authentication |
|--------|---------------|
| **Keypad PIN** | 4-6 digit code |
| **App on LAN** | Stored credentials |
| **Physical Button** | Hardware button + PIN |

### 10.2 Cancel Flow

```
1. User enters PIN
2. Edge verifies PIN locally (no Brain needed)
3. If valid:
   - Stop siren
   - Log "user_cancelled" with timestamp
   - Continue recording for 1 more minute
   - Exit EEMM
4. If invalid:
   - Log failed attempt
   - After 3 failures: lock cancel for 5 minutes
```

---

## 11. EEMM Confirmation Takeover (F10)

When Brain dies with active confirmation window:

### 11.1 Sync Requirement

Edge MUST receive confirmation state on every heartbeat:

```rust
struct ConfirmationSync {
    event_id: String,
    emergency_type: EmergencyType,
    created_at: u64,
    expires_at: u64,
    fallback_actions: Vec<EscalationAction>,
    user_id: u32,
}
```

### 11.2 Takeover Procedure

```
1. Brain heartbeat fails
2. Edge checks: any pending confirmations?
3. If yes:
   a. Edge takes over timeout tracking
   b. Edge continues countdown from sync'd state
   c. If window expires:
      - Execute EEMM actions only (not full fallback)
      - Log "confirmation_expired_in_eemm"
   d. If user responds via local channel:
      - Honor the response
      - Log "confirmation_resolved_locally"
4. When Brain returns:
   - Report confirmation outcome
   - Brain updates its state
```

### 11.3 Important Limitation

In EEMM confirmation takeover:
- Edge **CAN** execute: SIREN, LIGHTS, RECORDING, NOTIFY
- Edge **CANNOT** execute: CALL_AUTHORITY, ALERT_TRUSTED

Even if original fallback_actions included CALL_POLICE, Edge will NOT do it in EEMM.

---

## 12. EEMM Logging Requirements

All EEMM activity MUST be logged locally with these fields:

```rust
struct EemmLog {
    timestamp: u64,
    event_type: EemmEventType,  // ENTERED, ACTION, EXIT, ERROR
    details: String,
    emergency_id: String,
    action: Option<EemmAction>,
    success: bool,
    error: Option<String>,
}
```

**Log Retention:** 30 days minimum, survive Edge restart.

---

## 13. EEMM Testing Requirements

Before Stage 1 deployment, MUST test:

| Test Case | Expected Result |
|-----------|-----------------|
| Kill Brain process during emergency | Edge enters EEMM within 5s |
| Disconnect network during emergency | Edge enters EEMM within 5s |
| EEMM siren activation | All sirens ON within 100ms |
| EEMM cancel via keypad | Siren stops, EEMM exits |
| Edge restart during EEMM | EEMM state restored, continues |
| Confirmation takeover | Edge tracks timeout correctly |
| Brain reconnect during EEMM | Clean handoff, state sync |

---

## 14. EEMM Configuration

User-configurable EEMM settings (stored in Edge):

```yaml
eemm_config:
  # Timeouts
  brain_heartbeat_timeout_ms: 5000
  brain_decision_timeout_ms: 2000
  max_eemm_duration_minutes: 30

  # Notification
  owner_telegram_chat_id: "123456789"
  owner_phone: "+1234567890"
  notification_retry_count: 4

  # Cancel
  cancel_pin: "1234"
  cancel_lockout_minutes: 5
  failed_attempts_before_lockout: 3

  # Recording
  recording_max_minutes: 5
  recording_storage_path: "/var/homeai/recordings"

  # Per-emergency overrides
  intrusion:
    siren_enabled: true
    lights_enabled: true
  fire:
    siren_enabled: true
    unlock_doors: true  # Fire egress
  violence:
    siren_enabled: false  # Silent mode
    lights_enabled: false
```

---

## 15. Invariants (MUST NEVER VIOLATE)

```
EEMM-INV-01: EEMM entry MUST complete within 100ms of trigger
EEMM-INV-02: Siren MUST activate within 100ms of EEMM entry
EEMM-INV-03: EEMM MUST NOT call emergency services
EEMM-INV-04: EEMM MUST NOT exceed 30 minute duration
EEMM-INV-05: EEMM state MUST survive Edge restart
EEMM-INV-06: User MUST be able to cancel via local interface
EEMM-INV-07: Recording MUST NOT exceed 5 minutes per incident
EEMM-INV-08: PIN verification MUST work without Brain/network
EEMM-INV-09: EEMM actions MUST be idempotent (safe to retry)
EEMM-INV-10: Violence EEMM MUST NOT activate siren
```

---

## 16. Implementation Checklist

### Rust Edge Requirements

- [ ] Heartbeat monitoring (5s timeout)
- [ ] Decision timeout tracking (2s)
- [ ] EEMM state machine
- [ ] State persistence (survive restart)
- [ ] Siren control (direct GPIO / HA API)
- [ ] Light control (direct GPIO / HA API)
- [ ] Local recording (ffmpeg / direct)
- [ ] Telegram notification (direct API)
- [ ] SMS notification (Twilio / direct)
- [ ] Keypad PIN verification
- [ ] Confirmation sync parsing
- [ ] Confirmation timeout takeover
- [ ] EEMM logging
- [ ] Configuration loading

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-30 | Claude | Initial EEMM spec |

---

## Approval

- [ ] Architecture Review
- [ ] Safety Review
- [ ] Security Review (PIN handling)
- [ ] Legal Review (recording limits)
