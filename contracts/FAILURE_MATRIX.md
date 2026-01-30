# HomeAI Failure Matrix

**Version:** 1.0
**Status:** AUTHORITATIVE
**Last Updated:** 2026-01-30

---

## Purpose

This document defines how HomeAI responds to component failures. Every scenario MUST answer:

1. **What failed?**
2. **Who detects first?**
3. **Detection time (max)?**
4. **Edge immediate action?**
5. **Forbidden actions?**

If any row cannot answer all 5, the design is incomplete.

---

## Component Legend

| Component | Role | Can Fail? | Mitigation Owner |
|-----------|------|-----------|------------------|
| **HA** | Hardware/Protocol Layer | YES | Edge |
| **Edge** | Local Safety Brain | NO* | Out of scope Stage 1 |
| **Brain** | Policy & Social Intelligence | YES | Edge |
| **Network** | Edge ↔ Brain connectivity | YES | Edge |
| **Sensors** | Input devices | YES | Edge |
| **Actuators** | Output devices (siren, lights) | YES | Edge |

*Edge failure mitigation is Stage 2+ (hardware watchdog, redundant nodes).

---

## Failure Scenarios

### F01: Brain Unreachable (Network Up)

| Aspect | Value |
|--------|-------|
| **What Failed** | Brain process crashed / Cloud down / Brain overloaded |
| **Detection Signal** | Heartbeat response timeout |
| **Who Detects First** | Edge |
| **Max Detection Time** | 5 seconds |
| **Edge Immediate Action** | Mark brain_status = UNREACHABLE, continue local processing |
| **During Emergency** | Enter EEMM (siren, lights, local recording, notify owner if channel available) |
| **During Normal** | Buffer events locally, retry connection with exponential backoff |
| **Brain Expected Action** | N/A (dead) |
| **Forbidden Actions** | ❌ Call authority, ❌ Complex reasoning, ❌ Override consent, ❌ Wait indefinitely |
| **Recovery** | When heartbeat resumes → flush buffer, sync state, exit EEMM |
| **Notes** | Owner notification via direct channel (Telegram/SMS) if pre-configured |

---

### F02: Network Down (Total Partition)

| Aspect | Value |
|--------|-------|
| **What Failed** | Internet connection / Router / ISP |
| **Detection Signal** | All outbound connections fail + heartbeat timeout |
| **Who Detects First** | Edge |
| **Max Detection Time** | 5 seconds (same as heartbeat) |
| **Edge Immediate Action** | Mark network_status = DOWN, full local autonomous mode |
| **During Emergency** | EEMM immediately, NO waiting for Brain |
| **During Normal** | Continue local monitoring, buffer all events |
| **Brain Expected Action** | N/A (unreachable) |
| **Forbidden Actions** | ❌ Call authority (no channel), ❌ Cloud notifications, ❌ Assume network will return |
| **Recovery** | When connectivity resumes → sync buffered events, verify Brain state |
| **Notes** | Edge MUST NOT block on network operations during emergency |

---

### F03: Home Assistant Down

| Aspect | Value |
|--------|-------|
| **What Failed** | HA process / HA container / HA corruption |
| **Detection Signal** | HA API health check fails / WebSocket disconnected |
| **Who Detects First** | Edge |
| **Max Detection Time** | 3 seconds |
| **Edge Immediate Action** | Mark ha_status = DOWN, switch to direct sensor/actuator mode |
| **During Emergency** | Use GPIO/direct control for actuators, bypass HA |
| **During Normal** | Log warning, attempt reconnection |
| **Brain Expected Action** | Receive notification of degraded mode |
| **Forbidden Actions** | ❌ Assume HA will recover, ❌ Skip actuator commands, ❌ Treat as full system failure |
| **Recovery** | When HA reconnects → verify device states, sync any missed commands |
| **Notes** | HA is OPTIONAL layer - Edge MUST work without it |

---

### F04: Sensor Failure (Single)

| Aspect | Value |
|--------|-------|
| **What Failed** | Individual sensor (motion, smoke, door) |
| **Detection Signal** | No heartbeat from sensor / Invalid readings / Battery dead |
| **Who Detects First** | Edge |
| **Max Detection Time** | Sensor-dependent (typically 60-300 seconds for battery devices) |
| **Edge Immediate Action** | Mark sensor_status = OFFLINE, increase sensitivity on adjacent sensors |
| **During Emergency** | Continue with remaining sensors, note degraded coverage |
| **During Normal** | Alert owner about sensor offline |
| **Brain Expected Action** | Log maintenance event, notify user |
| **Forbidden Actions** | ❌ Ignore the gap, ❌ Assume sensor is fine, ❌ Disable zone entirely |
| **Recovery** | When sensor reconnects → verify calibration, clear offline status |
| **Notes** | Single sensor failure should NOT disable entire zone security |

---

### F05: Actuator Failure (Siren/Lights)

| Aspect | Value |
|--------|-------|
| **What Failed** | Siren not responding / Lights not controllable |
| **Detection Signal** | Command sent but state not confirmed |
| **Who Detects First** | Edge |
| **Max Detection Time** | 2 seconds (command timeout) |
| **Edge Immediate Action** | Retry once, then try alternative actuators |
| **During Emergency** | Use ALL available actuators (redundancy), don't depend on single device |
| **During Normal** | Alert owner about actuator issue |
| **Brain Expected Action** | Log maintenance event |
| **Forbidden Actions** | ❌ Give up on alerting, ❌ Silent failure, ❌ Single retry only |
| **Recovery** | When actuator responds → verify state, clear error |
| **Notes** | Emergency alerting MUST have redundancy (multiple sirens/lights) |

---

### F06: Brain Slow (High Latency)

| Aspect | Value |
|--------|-------|
| **What Failed** | Brain responding but > 2 second latency |
| **Detection Signal** | Heartbeat OK but decision response slow |
| **Who Detects First** | Edge |
| **Max Detection Time** | Per-request timeout (2 seconds for emergency decisions) |
| **Edge Immediate Action** | Mark brain_status = DEGRADED |
| **During Emergency** | Don't wait for Brain decision, execute EEMM |
| **During Normal** | Continue with cached policies, log latency |
| **Brain Expected Action** | Eventually respond (may be stale) |
| **Forbidden Actions** | ❌ Wait for slow response during emergency, ❌ Queue emergency decisions |
| **Recovery** | When latency normalizes → resume normal flow |
| **Notes** | Emergency SLA: 2 seconds. If Brain can't decide in 2s, Edge decides. |

---

### F07: Database Corruption (Brain)

| Aspect | Value |
|--------|-------|
| **What Failed** | SQLite corruption / Disk full / Write failure |
| **Detection Signal** | Database query errors |
| **Who Detects First** | Brain |
| **Max Detection Time** | Immediate (on query) |
| **Edge Immediate Action** | N/A (Edge doesn't know) - Brain heartbeat may still work |
| **Brain Behavior** | Log error, attempt recovery, notify admin |
| **If Brain Becomes Unresponsive** | Edge enters EEMM |
| **Forbidden Actions** | ❌ Lose evidence, ❌ Silent corruption, ❌ Continue without logging |
| **Recovery** | Restore from backup, replay WAL if available |
| **Notes** | Evidence MUST be written to separate append-only store |

---

### F08: Edge Local Storage Full

| Aspect | Value |
|--------|-------|
| **What Failed** | Edge disk/storage full |
| **Detection Signal** | Write failures |
| **Who Detects First** | Edge |
| **Max Detection Time** | Immediate (on write) |
| **Edge Immediate Action** | Rotate oldest non-emergency logs, alert owner |
| **During Emergency** | NEVER delete emergency evidence, fail other writes instead |
| **During Normal** | Aggressive log rotation |
| **Brain Expected Action** | Receive storage alert |
| **Forbidden Actions** | ❌ Delete emergency evidence, ❌ Stop processing events, ❌ Crash |
| **Recovery** | Owner clears space or auto-rotation frees space |
| **Notes** | Emergency evidence has infinite priority over other data |

---

### F09: Partial Network (Edge ↔ HA OK, Edge ↔ Brain FAIL)

| Aspect | Value |
|--------|-------|
| **What Failed** | WAN connectivity (LAN still works) |
| **Detection Signal** | HA responds, Brain heartbeat fails |
| **Who Detects First** | Edge |
| **Max Detection Time** | 5 seconds |
| **Edge Immediate Action** | brain_status = UNREACHABLE, continue with HA integration |
| **During Emergency** | EEMM with full HA actuator control |
| **During Normal** | Local operation, buffer for Brain |
| **Forbidden Actions** | ❌ Disable HA integration, ❌ Treat as full network failure |
| **Recovery** | When WAN resumes → sync with Brain |
| **Notes** | This is actually a BETTER failure mode than F02 - actuators work |

---

### F10: Confirmation Window Active + Brain Dies

| Aspect | Value |
|--------|-------|
| **What Failed** | Brain dies mid-confirmation (user has 30s window active) |
| **Detection Signal** | Heartbeat timeout while confirmation pending |
| **Who Detects First** | Edge |
| **Max Detection Time** | 5 seconds |
| **Edge Immediate Action** | Take over confirmation timeout tracking |
| **If Window Expires** | Execute fallback actions (EEMM-level only) |
| **User Response Handling** | If user responds via local channel → honor it |
| **Brain Expected Action** | N/A (dead) |
| **Forbidden Actions** | ❌ Ignore pending confirmation, ❌ Execute authority calls, ❌ Extend window indefinitely |
| **Recovery** | When Brain returns → sync confirmation outcome |
| **Notes** | Edge MUST know about pending confirmations (sync on heartbeat) |

---

### F11: Multiple Simultaneous Emergencies

| Aspect | Value |
|--------|-------|
| **What Failed** | Not a failure - stress scenario |
| **Detection Signal** | Multiple emergency events within short window |
| **Who Detects First** | Edge |
| **Max Detection Time** | N/A |
| **Edge Immediate Action** | Process ALL emergencies, don't drop any |
| **Priority Order** | 1. Fire, 2. Violence, 3. Intrusion, 4. Other |
| **Actuator Strategy** | All alerts active simultaneously |
| **Forbidden Actions** | ❌ Drop lower-priority emergency, ❌ Sequential-only processing that blocks |
| **Notes** | Edge queue must handle burst without head-of-line blocking for evidence storage |

---

### F12: Malformed Event from HA/Sensor

| Aspect | Value |
|--------|-------|
| **What Failed** | Sensor sends garbage / HA sends invalid data |
| **Detection Signal** | Schema validation failure |
| **Who Detects First** | Edge |
| **Max Detection Time** | Immediate |
| **Edge Immediate Action** | Log error, discard event, continue processing |
| **During Emergency** | Do NOT let bad data trigger false emergency |
| **During Normal** | Alert about sensor health |
| **Forbidden Actions** | ❌ Crash on bad input, ❌ Trust unvalidated data, ❌ Propagate garbage to Brain |
| **Notes** | Edge MUST be defensive against malformed input |

---

## Priority Classification

### P0 - Must Handle in Stage 1

| ID | Scenario | Reason |
|----|----------|--------|
| F01 | Brain Unreachable | Core EEMM trigger |
| F02 | Network Down | Core EEMM trigger |
| F03 | HA Down | HA is optional layer |
| F06 | Brain Slow | Emergency SLA |
| F10 | Confirmation + Brain Dies | Active safety flow |

### P1 - Should Handle in Stage 1

| ID | Scenario | Reason |
|----|----------|--------|
| F04 | Sensor Failure | Graceful degradation |
| F05 | Actuator Failure | Redundancy |
| F09 | Partial Network | Common failure mode |
| F11 | Multiple Emergencies | Stress resilience |
| F12 | Malformed Event | Defensive programming |

### P2 - Stage 2+

| ID | Scenario | Reason |
|----|----------|--------|
| F07 | DB Corruption | Requires backup infra |
| F08 | Storage Full | Requires storage management |

---

## Invariants (MUST NEVER BE VIOLATED)

```
INV-01: Edge MUST enter EEMM within 5 seconds of Brain unreachable during emergency
INV-02: Edge MUST NOT call authority without pre-authorization
INV-03: Edge MUST NOT wait for Brain response during active emergency if SLA exceeded
INV-04: Edge MUST NOT depend on HA for safety-critical actuator control
INV-05: Emergency evidence MUST be stored before any other action
INV-06: Confirmation window MUST be minimum 30 seconds (no override)
INV-07: Edge MUST NOT perform complex reasoning in EEMM
INV-08: Edge MUST NOT override user consent settings
INV-09: Single component failure MUST NOT disable entire system
INV-10: Edge MUST be stateless-recoverable (deterministic from persisted state)
```

---

## State Machine: Edge Operating Modes

```
                    ┌─────────────┐
                    │   NORMAL    │
                    │  (Brain OK) │
                    └──────┬──────┘
                           │
           ┌───────────────┼───────────────┐
           │               │               │
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │  DEGRADED   │ │    EEMM     │ │  HA_BYPASS  │
    │(Brain slow) │ │(Brain down) │ │ (HA down)   │
    └─────────────┘ └─────────────┘ └─────────────┘
           │               │               │
           │               │               │
           └───────────────┴───────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  RECOVERY   │
                    │ (Syncing)   │
                    └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │   NORMAL    │
                    └─────────────┘
```

**Mode Transitions:**
- NORMAL → DEGRADED: Brain latency > 500ms
- NORMAL → EEMM: Brain heartbeat timeout (5s)
- NORMAL → HA_BYPASS: HA health check fails
- Any → RECOVERY: Component comes back online
- RECOVERY → NORMAL: State sync complete

---

## Implementation Checklist (For Rust Edge)

### P0 Required Before Stage 1 Complete

- [ ] Heartbeat mechanism to Brain (5s timeout)
- [ ] EEMM state machine
- [ ] Local actuator control (bypass HA)
- [ ] Event buffering during partition
- [ ] Emergency SLA enforcement (2s decision timeout)
- [ ] Confirmation takeover on Brain death

### P1 Required for Production

- [ ] Sensor health monitoring
- [ ] Actuator redundancy management
- [ ] Partial network detection
- [ ] Burst handling for multiple emergencies
- [ ] Input validation / defensive parsing

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-30 | Claude | Initial failure matrix |

---

## Approval

This document requires review and approval before implementation.

- [ ] Architecture Review
- [ ] Security Review
- [ ] Safety Review
