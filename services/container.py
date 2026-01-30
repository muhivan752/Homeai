# ===============================
# services/container.py - Service Container (PRODUCTION)
# ===============================
# SINGLE SOURCE OF TRUTH for service initialization.
#
# All services are initialized here and injected into Flask app.
# Routes access services via: current_app.config["SERVICES"]["service_name"]
#
# SERVICE CATEGORIES:
# 1. Core Business Services (user, device, energy, admin)
# 2. Event Services (event, evidence, decision, dispatcher)
# 3. Escalation Services (escalation, trusted_contacts, confirmation, acknowledgment)
# 4. Companion Services (companion)

from services.user import UserService
from services.device import DeviceService
from services.energy import EnergyService
from services.admin import AdminService
from services.event import EventService
from services.evidence import EvidenceService
from services.decision import DecisionService
from services.dispatcher import EventDispatcher, create_default_handlers
from services.integrity import IntegrityService
from services.escalation import EscalationEngine
from services.trusted_contacts import TrustedContactsService
from services.confirmation import ConfirmationService
from services.acknowledgment import AcknowledgmentService
from services.companion import CompanionService


def init_services(db_path: str) -> dict:
    """
    Initialize all services with database path.

    Usage in app.py:
        from services.container import init_services
        services = init_services(DATABASE_PATH)
        app.config["SERVICES"] = services

    Usage in routes:
        def get_services():
            return current_app.config["SERVICES"]

        services = get_services()
        user = services['user'].verify_login(email, password)

    Returns:
        dict with all service instances
    """
    # Core business services
    user_service = UserService(db_path)
    device_service = DeviceService(db_path)
    energy_service = EnergyService(db_path)
    admin_service = AdminService(db_path)

    # Event-driven services
    event_service = EventService(db_path)
    evidence_service = EvidenceService(db_path)
    decision_service = DecisionService(db_path)
    integrity_service = IntegrityService(db_path)

    # Escalation services
    escalation_engine = EscalationEngine(db_path)
    trusted_contacts_service = TrustedContactsService(db_path)
    confirmation_service = ConfirmationService(db_path)
    acknowledgment_service = AcknowledgmentService(db_path)

    # Companion services
    companion_service = CompanionService(db_path)

    # Start confirmation watchdog
    confirmation_service.start_watchdog()

    # Event dispatcher (depends on event services)
    dispatcher = EventDispatcher(
        event_service=event_service,
        evidence_service=evidence_service,
        decision_service=decision_service,
    )

    # Register default handlers
    create_default_handlers(dispatcher)

    # Register escalation handlers
    from services.dispatcher import create_escalation_handlers
    create_escalation_handlers(
        dispatcher,
        escalation_engine,
        confirmation_service,
        trusted_contacts_service,
        decision_service,
    )

    return {
        # Core Business
        "user": user_service,
        "device": device_service,
        "energy": energy_service,
        "admin": admin_service,

        # Event System
        "event": event_service,
        "evidence": evidence_service,
        "decision": decision_service,
        "dispatcher": dispatcher,
        "integrity": integrity_service,

        # Escalation System
        "escalation": escalation_engine,
        "trusted_contacts": trusted_contacts_service,
        "confirmation": confirmation_service,
        "acknowledgment": acknowledgment_service,

        # Companion System
        "companion": companion_service,
    }


def get_service_info() -> dict:
    """
    Get information about available services.
    Useful for debugging and documentation.
    """
    return {
        # ===== CORE BUSINESS SERVICES =====
        "user": {
            "class": "UserService",
            "description": "Authentication, profile, family members",
            "methods": [
                "verify_login", "create_user", "email_exists",
                "get_by_id", "update_avatar", "update_profile",
                "get_family_members", "add_family_member", "delete_family_member",
                "family_photo_belongs_to_user",
                "update_telegram_chat_id", "get_by_telegram_chat_id"
            ]
        },
        "device": {
            "class": "DeviceService",
            "description": "Device CRUD, state management, payment processing",
            "methods": [
                "get_user_devices", "get_device", "get_device_by_id",
                "add_device", "update_device", "delete_device",
                "request_toggle_device", "disable_device",
                "update_device_online_status",
                "attach_payment_proof_bulk", "resubmit_payment",
                "payment_file_belongs_to_user",
                "get_pending_payment_devices", "get_pending_review_devices",
                "get_active_devices", "get_rejected_devices"
            ]
        },
        "energy": {
            "class": "EnergyService",
            "description": "Energy logging, analytics, cost calculation",
            "methods": [
                "log_sensor_data", "log_sensor_data_batch",
                "get_latest_readings", "get_device_readings", "get_readings_in_range",
                "get_daily_summary", "get_device_daily_summary",
                "get_current_power",
                "calculate_cost", "get_monthly_cost_estimate",
                "cleanup_old_logs"
            ]
        },
        "admin": {
            "class": "AdminService",
            "description": "Admin dashboard, user management, device approval",
            "methods": [
                "get_dashboard_data",
                "get_user_detail", "delete_user", "restore_user",
                "update_user_plan", "update_user_role",
                "get_all_orders", "get_pending_orders",
                "activate_device", "reject_device",
                "get_admin_logs", "get_admin_logs_by_admin",
                "get_revenue_stats", "get_user_stats"
            ]
        },

        # ===== EVENT SERVICES =====
        "event": {
            "class": "EventService",
            "description": "Central event store - ALL events pass through here",
            "methods": [
                "store_event", "get_event",
                "get_events_by_category", "get_events_by_severity",
                "get_user_events", "get_device_events",
                "get_recent_events", "count_events_by_category",
                "get_emergency_events", "get_anomaly_events"
            ]
        },
        "evidence": {
            "class": "EvidenceService",
            "description": "Immutable evidence storage for EMERGENCY events only",
            "methods": [
                "store_evidence", "get_evidence",
                "get_all_emergency_evidence", "get_evidence_by_type",
                "verify_all_integrity", "get_retention_report",
                # FORBIDDEN: update_evidence, delete_evidence
            ]
        },
        "decision": {
            "class": "DecisionService",
            "description": "AI/automation decision logging for audit trail",
            "methods": [
                "log_decision", "log_no_action_decision",
                "update_outcome", "get_decision",
                "get_decisions_for_event", "get_decisions_by_type",
                "get_recent_decisions", "get_emergency_decisions",
                "get_decision_stats", "explain_decision"
            ]
        },
        "dispatcher": {
            "class": "EventDispatcher",
            "description": "Event routing with pub/sub pattern, isolated emergency pipeline",
            "methods": [
                "register_handler", "unregister_handler",
                "enable_handler", "disable_handler",
                "dispatch", "dispatch_batch",
                "get_handler_info", "get_dispatch_log", "get_stats", "shutdown"
            ]
        },
        "integrity": {
            "class": "IntegrityService",
            "description": "Hash chain & external anchoring for legal compliance",
            "methods": [
                "create_block", "verify_chain",
                "get_daily_digest", "record_external_anchor",
                "get_latest_block", "get_anchor_status"
            ]
        },

        # ===== ESCALATION SERVICES =====
        "escalation": {
            "class": "EscalationEngine",
            "description": "Core escalation decision engine with policy-driven autonomy",
            "methods": [
                "decide", "set_policy", "get_user_policies",
                "grant_consent", "revoke_consent", "get_user_consents", "has_consent",
                "invalidate_cache"
            ]
        },
        "trusted_contacts": {
            "class": "TrustedContactsService",
            "description": "Trusted contacts for emergency notifications",
            "methods": [
                "add_contact", "update_contact", "remove_contact",
                "get_contact", "get_user_contacts",
                "get_contacts_for_event", "get_verified_contacts_for_event",
                "verify_contact", "set_notification_preferences",
                "get_contact_count", "has_verified_contacts"
            ]
        },
        "confirmation": {
            "class": "ConfirmationService",
            "description": "30-second confirmation window for emergency events",
            "methods": [
                "create_confirmation", "confirm_safe", "confirm_threat",
                "cancel_confirmation", "extend_window",
                "get_pending", "get_pending_for_event", "get_confirmation_history",
                "get_time_remaining", "get_stats",
                "start_watchdog", "stop_watchdog", "register_callback"
            ]
        },
        "acknowledgment": {
            "class": "AcknowledgmentService",
            "description": "Active acknowledgment flow for system limitations",
            "methods": [
                "get_acknowledgment_status", "get_acknowledgment_text",
                "get_all_acknowledgment_texts", "acknowledge_item",
                "is_fully_acknowledged", "requires_reacknowledgment",
                "get_pending_acknowledgments", "reset_acknowledgments",
                "get_acknowledgment_stats"
            ]
        },

        # ===== COMPANION SERVICES =====
        "companion": {
            "class": "CompanionService",
            "description": "Companion mode notification routing and message composition",
            "methods": [
                "should_notify", "log_notification",
                "set_user_preferences", "compose_daily_digest",
                "get_notification_stats"
            ]
        },
    }
