# HomeAI Companion Mode Specification

**Version:** 1.0
**Status:** AUTHORITATIVE
**Last Updated:** 2026-01-30

---

## 1. Philosophy

> HomeAI Stage 1 hadir untuk menemani, bukan untuk mengambil alih.

### Core Identity

| Aspect | Companion Mode | NOT Companion Mode |
|--------|---------------|-------------------|
| **Role** | Friend, presence | Robot, automation engine |
| **Default** | Silent | Noisy |
| **Action** | Inform, offer | Push, force |
| **Control** | User decides | System decides |
| **Trust** | Earned over time | Assumed |

### One-Liner (North Star)

```
Emergency = Guardian (protect)
Daily life = Companion (accompany)
```

---

## 2. Interaction Pattern (LOCKED)

### The Only Pattern: Inform → Offer → User Chooses

```
┌─────────────────────────────────────────┐
│                                         │
│  [Context - what happened]              │
│  [Duration/detail - optional]           │
│                                         │
│  [Offer - question, not statement]      │
│                                         │
│  [Lihat]  [Nanti]  [Abaikan]           │
│                                         │
└─────────────────────────────────────────┘
```

### Examples

```
✅ GOOD:
"Ada tamu di depan rumah, sudah menunggu ±4 menit. Mau lihat?"

"Kurir baru datang saat kamu tidak di rumah. Perlu lihat snapshot?"

"Ada aktivitas di dapur jam 2 pagi. Tidak biasa. Mau cek?"
```

```
❌ BAD:
"ALERT: Person detected at front door"
"Motion sensor triggered in kitchen"
"Delivery arrived at 14:32:05"
```

---

## 3. Silence Policy (NON-NEGOTIABLE)

### Default = DIAM

HomeAI does NOT notify for:
- Expected behavior
- Routine activities
- Pattern-matching events
- Things that don't add new information

### When to Speak

HomeAI MAY notify when ANY of these are true:

| Condition | Example |
|-----------|---------|
| **Unusual vs baseline** | Child home 30min late |
| **User is away** | Activity while no one home |
| **User opted-in** | Explicitly subscribed |
| **User asked** | User-initiated query |
| **Reduces anxiety** | High confidence helpful |

### When in Doubt

```
IF uncertain whether message helps:
    DO NOT SEND
```

---

## 4. Data Philosophy

### Raw Data = Ephemeral

```
NOT STORED (beyond processing):
- Video streams
- Audio streams
- Full-resolution images
- Continuous recordings
```

### Patterns = Kept

```
STORED (for context):
- "Tamu datang jam 14:00"
- "Kurir biasa datang Senin-Jumat"
- "Anak biasa pulang jam 15:30"
- Activity summaries
- Behavioral baselines
- Event metadata
```

### On-Demand Only

```
ALLOWED (when user requests):
- Snapshot (single image)
- Live camera view
- Short clip replay
```

---

## 5. Event Categories

### 5.1 Presence Events

| Event | Default | Notify When |
|-------|---------|-------------|
| `FamilyMemberArrived` | DIAM | Late vs schedule, user away |
| `FamilyMemberLeft` | DIAM | Unusual time, user away |
| `ChildArrived` | DIAM | Late vs school schedule |
| `ChildLeft` | DIAM | Earlier than expected |
| `GuestArrived` | Notify if away | Unknown person at door |
| `UnknownPerson` | Notify | Not in whitelist |

### 5.2 Activity Events

| Event | Default | Notify When |
|-------|---------|-------------|
| `MotionDetected` | DIAM | Unusual zone/time, user away |
| `DoorOpened` | DIAM | Unusual time, user away |
| `DoorBellRing` | Notify | Always (user expects response) |
| `ActivityInZone` | DIAM | Anomaly vs baseline |

### 5.3 Delivery Events

| Event | Default | Notify When |
|-------|---------|-------------|
| `CourierArrived` | DIAM | User away, unusual time |
| `PackageDelivered` | DIAM | User away |
| `PackagePickedUp` | DIAM | By unknown person |

### 5.4 Child/Pet Events

| Event | Default | Notify When |
|-------|---------|-------------|
| `ChildCrying` | Notify | Detected (safety concern) |
| `ChildSleeping` | DIAM | Never auto-notify |
| `PetActivity` | DIAM | Unusual, user away |

### 5.5 Environmental Events

| Event | Default | Notify When |
|-------|---------|-------------|
| `TemperatureAnomaly` | Notify | Outside comfort range |
| `HumidityAnomaly` | Notify | Risk of damage |
| `AirQualityPoor` | Notify | Health concern |
| `LoudNoise` | DIAM | Unusual time, user away |

---

## 6. Message Templates

### 6.1 Tone Rules

| Rule | Description |
|------|-------------|
| **Conversational** | Like texting a helpful friend |
| **No jargon** | "Ada orang" not "Person detected" |
| **No timestamps** | "±4 menit" not "14:32:05" |
| **No ALL CAPS** | Never shout |
| **No emoji spam** | Max 1 emoji if any |
| **Question, not statement** | "Mau lihat?" not "Check camera" |

### 6.2 Template Structure

```
[CONTEXT]: Apa yang terjadi, natural language
[DETAIL]: Tambahan konteks jika relevan (opsional)
[OFFER]: Pertanyaan, bukan perintah
[ACTIONS]: Pilihan user
```

### 6.3 Example Templates

#### Presence - Unknown Person

```
Ada orang di depan rumah yang tidak dikenali.
Sudah ±{duration} menit.

Mau lihat?

[Lihat] [Nanti] [Abaikan]
```

#### Presence - Child Late

```
{child_name} belum sampai rumah.
Biasanya sudah pulang jam {expected_time}.

Mau cek lokasi atau hubungi?

[Cek] [Hubungi] [Tunggu]
```

#### Delivery - Courier (User Away)

```
Kurir baru datang ke rumah.
Kamu sedang tidak di rumah.

Perlu lihat snapshot?

[Lihat] [Nanti]
```

#### Activity - Unusual Time

```
Ada aktivitas di {zone} jam {time}.
Tidak biasa untuk jam segini.

Mau cek kamera?

[Cek] [Abaikan]
```

#### Child - Crying

```
Sepertinya {child_name} menangis.
Terdeteksi dari {location}.

Mau lihat?

[Lihat] [Abaikan]
```

#### Environmental - Temperature

```
Suhu di {zone} agak {hot/cold} ({temp}°C).
Biasanya sekitar {normal_temp}°C.

Perlu atur AC?

[Atur] [Biarkan]
```

#### Daily Digest (Opt-in Only)

```
Ringkasan hari ini:

• Kurir datang siang
• {child_name} pulang jam {time}
• Rumah tenang sore hingga malam

Tidak ada yang perlu perhatian khusus.
```

---

## 7. Notification Decision Tree

```
EVENT RECEIVED
      │
      ▼
┌─────────────────────┐
│ Is Emergency?       │──YES──▶ [EMERGENCY MODE]
└──────────┬──────────┘
           │ NO
           ▼
┌─────────────────────┐
│ User opted-in for   │──YES──▶ [NOTIFY]
│ this event type?    │
└──────────┬──────────┘
           │ NO (or default)
           ▼
┌─────────────────────┐
│ Is this unusual     │──YES──▶ [EVALUATE CONTEXT]
│ vs baseline?        │              │
└──────────┬──────────┘              ▼
           │ NO              ┌───────────────┐
           ▼                 │ User away?    │──YES──▶ [NOTIFY]
┌─────────────────────┐      └───────┬───────┘
│ Is user away?       │──YES──▶ [NOTIFY]  │ NO
└──────────┬──────────┘                    ▼
           │ NO                     ┌───────────────┐
           ▼                        │ Safety        │──YES──▶ [NOTIFY]
┌─────────────────────┐             │ concern?      │
│ STAY SILENT         │             └───────┬───────┘
│ (Log internally)    │                     │ NO
└─────────────────────┘                     ▼
                                    ┌───────────────┐
                                    │ STAY SILENT   │
                                    └───────────────┘
```

---

## 8. User Preferences (Stage 1 Scope)

### Allowed Configuration

```yaml
notification_preferences:
  # Global mode
  mode: "quieter" | "balanced" | "informative"

  # Per-event-type toggles
  events:
    doorbell: true          # Always notify
    unknown_person: true    # Always notify
    child_crying: true      # Always notify
    courier_arrived: false  # Only if away
    family_arrived: false   # Only if unusual
    motion_detected: false  # Only if unusual + away

  # Daily digest
  daily_digest:
    enabled: false
    time: "21:00"

  # Quiet hours
  quiet_hours:
    enabled: true
    start: "23:00"
    end: "07:00"
```

### NOT Allowed in Stage 1

```
❌ Per-zone configuration
❌ Per-person configuration
❌ Confidence threshold sliders
❌ Complex rule builder
❌ Multiple notification channels
```

Simplicity = Trust.

---

## 9. Channel (Stage 1)

### Telegram Only

- Single channel
- Two-way (user can respond)
- Inline buttons for actions
- No spam, no false urgency

### Message Format

```
[Bot Name]: HomeAI

[Message]: Natural language, as per templates

[Buttons]: Inline keyboard with options
```

---

## 10. Companion Test (Quality Gate)

Every notification MUST pass ALL:

| Test | Question | Fail = Don't Send |
|------|----------|-------------------|
| **Non-intrusive** | Would this annoy a busy person? | Yes = Fail |
| **Choice-based** | Does user have LIHAT/ABAIKAN/NANTI? | No = Fail |
| **Reduces anxiety** | Does this help, not worry? | No = Fail |
| **No raw storage** | Are we storing raw data? | Yes = Fail |
| **Silence valid** | Is "don't send" an option we considered? | No = Fail |
| **Trust-building** | Does this build trust over time? | No = Fail |

---

## 11. Behavioral Learning (Stage 1)

### Mode: PASSIVE ONLY

```
ALLOWED:
- Observe patterns
- Build baselines
- Store summaries
- Learn "normal"

NOT ALLOWED:
- Predict behavior
- Auto-notify based on prediction
- Auto-action based on learning
- Suggest without being asked
```

### Purpose

> Siap untuk masa depan tanpa mengganggu hari ini.

---

## 12. Implementation Checklist

### Services Required

- [ ] `CompanionEventService` - Event classification
- [ ] `NotificationRouter` - Decision tree implementation
- [ ] `MessageComposer` - Template rendering
- [ ] `BaselineService` - Pattern learning (passive)
- [ ] `TelegramService` - Channel integration
- [ ] `UserPreferencesService` - Settings management

### Database Tables

- [ ] `notification_preferences` - User settings
- [ ] `activity_baseline` - Learned patterns
- [ ] `notification_log` - What was sent (for learning)
- [ ] `suppressed_notifications` - What was NOT sent (for audit)

---

## 13. Invariants (MUST NEVER VIOLATE)

```
COMP-INV-01: Default is SILENT, not notify
COMP-INV-02: User ALWAYS has choice (Lihat/Abaikan/Nanti)
COMP-INV-03: Raw data is NEVER stored long-term
COMP-INV-04: No auto-action without user consent
COMP-INV-05: Silence is a valid and preferred outcome
COMP-INV-06: Messages are conversational, not robotic
COMP-INV-07: No prediction-based auto-notification in Stage 1
COMP-INV-08: Telegram is the ONLY channel in Stage 1
COMP-INV-09: Quiet hours are respected (except emergency)
COMP-INV-10: When in doubt, stay silent
```

---

## Document Control

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-30 | Claude | Initial companion spec |

---

## Approval

- [ ] Product Review
- [ ] UX Review
- [ ] Privacy Review
