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

from services.user import UserService
from services.device import DeviceService
from services.energy import EnergyService
from services.admin import AdminService
from services.event import EventService
from services.evidence import EvidenceService
from services.decision import DecisionService
from services.dispatcher import EventDispatcher, create_default_handlers
from services.integrity import IntegrityService


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

    # Event dispatcher (depends on event services)
    dispatcher = EventDispatcher(
        event_service=event_service,
        evidence_service=evidence_service,
        decision_service=decision_service,
    )

    # Register default handlers
    create_default_handlers(dispatcher)

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
    }
