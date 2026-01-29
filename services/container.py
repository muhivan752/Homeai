# ===============================
# services/container.py - Service Container (PRODUCTION)
# ===============================
# SINGLE SOURCE OF TRUTH for service initialization.
# 
# All services are initialized here and injected into Flask app.
# Routes access services via: current_app.config["SERVICES"]["service_name"]

from services.user import UserService
from services.device import DeviceService
from services.energy import EnergyService
from services.admin import AdminService


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
    return {
        "user": UserService(db_path),
        "device": DeviceService(db_path),
        "energy": EnergyService(db_path),
        "admin": AdminService(db_path),
    }


def get_service_info() -> dict:
    """
    Get information about available services.
    Useful for debugging and documentation.
    """
    return {
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
        }
    }
