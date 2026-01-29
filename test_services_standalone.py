#!/usr/bin/env python3
# ===============================
# test_services_standalone.py - Service Test (No Flask)
# ===============================
# This test verifies service layer WITHOUT Flask/network dependencies.

import os
import sys
import tempfile
import sqlite3

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Use temp database
TEST_DB = os.path.join(tempfile.gettempdir(), 'homeai_test.db')

def init_test_db(db_path):
    """Initialize database schema directly."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            plan_name TEXT DEFAULT 'Basic',
            avatar TEXT,
            verified INTEGER DEFAULT 1,
            is_deleted INTEGER DEFAULT 0,
            telegram_chat_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            device_type TEXT,
            location TEXT,
            power_watts INTEGER DEFAULT 100,
            status TEXT DEFAULT 'pending_payment',
            desired_state INTEGER DEFAULT 0,
            is_online INTEGER DEFAULT 0,
            payment_proof TEXT,
            payment_date TIMESTAMP,
            activated_at TIMESTAMP,
            activated_by INTEGER,
            reject_reason TEXT,
            price INTEGER DEFAULT 20000,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS family_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role TEXT,
            photo_identity TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS energy_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id INTEGER NOT NULL,
            watt REAL NOT NULL,
            measured_at INTEGER NOT NULL
        )
    """)
    
    c.execute("""
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()


def test_base_service():
    """Test BaseService."""
    print("\n🔹 Testing BaseService...")
    from services.base import BaseService
    
    svc = BaseService(TEST_DB)
    
    # Test run_query - SELECT
    result = svc.run_query("SELECT 1 as test", one=True)
    assert result is not None
    assert result['test'] == 1
    print("  ✓ run_query SELECT")
    
    # Test exists
    assert svc.exists("users", "id", 99999) == False
    print("  ✓ exists")


def test_user_service():
    """Test UserService."""
    print("\n🔹 Testing UserService...")
    from services.user import UserService
    
    svc = UserService(TEST_DB)
    
    # Create user
    user_id = svc.create_user("Test User", "test@example.com", "password123")
    assert user_id is not None
    print(f"  ✓ create_user: user_id={user_id}")
    
    # Email exists
    assert svc.email_exists("test@example.com") == True
    assert svc.email_exists("nobody@example.com") == False
    print("  ✓ email_exists")
    
    # Verify login
    user = svc.verify_login("test@example.com", "password123")
    assert user is not None
    assert user['email'] == "test@example.com"
    print("  ✓ verify_login")
    
    # Bad login
    assert svc.verify_login("test@example.com", "wrongpassword") is None
    print("  ✓ verify_login (bad password)")
    
    # Get by ID
    user = svc.get_by_id(user_id)
    assert user is not None
    print("  ✓ get_by_id")
    
    # Update avatar
    assert svc.update_avatar(user_id, "avatar.jpg") == True
    print("  ✓ update_avatar")
    
    # Family members
    member_id = svc.add_family_member(user_id, "Child", "child", "photo.jpg")
    assert member_id is not None
    print(f"  ✓ add_family_member: member_id={member_id}")
    
    members = svc.get_family_members(user_id)
    assert len(members) == 1
    print(f"  ✓ get_family_members: {len(members)} members")
    
    assert svc.family_photo_belongs_to_user("photo.jpg", user_id) == True
    assert svc.family_photo_belongs_to_user("other.jpg", user_id) == False
    print("  ✓ family_photo_belongs_to_user")
    
    assert svc.delete_family_member(member_id, user_id) == True
    print("  ✓ delete_family_member")
    
    return user_id


def test_device_service(user_id):
    """Test DeviceService."""
    print("\n🔹 Testing DeviceService...")
    from services.device import DeviceService
    
    svc = DeviceService(TEST_DB)
    
    # Add device
    device_id = svc.add_device(user_id, "Smart Plug", "plug", "Room", 100)
    assert device_id is not None
    print(f"  ✓ add_device: device_id={device_id}")
    
    # Get user devices
    devices = svc.get_user_devices(user_id)
    assert len(devices) == 1
    print(f"  ✓ get_user_devices: {len(devices)} devices")
    
    # Get device (with ownership)
    device = svc.get_device(device_id, user_id)
    assert device is not None
    assert device['name'] == "Smart Plug"
    print("  ✓ get_device")
    
    # Get device (wrong user)
    assert svc.get_device(device_id, 99999) is None
    print("  ✓ get_device (wrong user = None)")
    
    # Get device by ID
    device = svc.get_device_by_id(device_id)
    assert device is not None
    print("  ✓ get_device_by_id")
    
    # Attach payment
    count = svc.attach_payment_proof_bulk([device_id], user_id, "payment.jpg")
    assert count == 1
    device = svc.get_device(device_id, user_id)
    assert device['status'] == 'pending_review'
    print("  ✓ attach_payment_proof_bulk")
    
    # Payment belongs to user
    assert svc.payment_file_belongs_to_user("payment.jpg", user_id) == True
    print("  ✓ payment_file_belongs_to_user")
    
    return device_id


def test_admin_service(user_id, device_id):
    """Test AdminService."""
    print("\n🔹 Testing AdminService...")
    from services.admin import AdminService
    from services.user import UserService
    
    admin_svc = AdminService(TEST_DB)
    user_svc = UserService(TEST_DB)
    
    # Create admin user
    admin_id = user_svc.create_user("Admin", "admin@test.com", "admin123", role='admin')
    print(f"  ✓ created admin user: admin_id={admin_id}")
    
    # Get dashboard data
    data = admin_svc.get_dashboard_data()
    assert 'users' in data
    assert 'stats' in data
    print(f"  ✓ get_dashboard_data: {data['stats']['total_users']} users")
    
    # Get all orders
    orders = admin_svc.get_all_orders()
    assert len(orders) >= 1
    print(f"  ✓ get_all_orders: {len(orders)} orders")
    
    # Get user detail
    user = admin_svc.get_user_detail(user_id)
    assert user is not None
    print("  ✓ get_user_detail")
    
    # Activate device
    result = admin_svc.activate_device(device_id, admin_id)
    assert result == True
    print("  ✓ activate_device")
    
    # Update user plan
    result = admin_svc.update_user_plan(user_id, "Premium", admin_id)
    assert result == True
    print("  ✓ update_user_plan")
    
    # Get admin logs
    logs = admin_svc.get_admin_logs()
    assert len(logs) >= 1
    print(f"  ✓ get_admin_logs: {len(logs)} entries")
    
    return admin_id


def test_energy_service(device_id, user_id):
    """Test EnergyService."""
    print("\n🔹 Testing EnergyService...")
    from services.energy import EnergyService
    import time
    
    svc = EnergyService(TEST_DB)
    now = int(time.time())
    
    # Log sensor data
    log_id = svc.log_sensor_data(device_id, 85.5, now - 3600)
    assert log_id is not None
    print(f"  ✓ log_sensor_data: log_id={log_id}")
    
    # Add more readings
    svc.log_sensor_data(device_id, 90.2, now - 1800)
    svc.log_sensor_data(device_id, 87.3, now - 900)
    svc.log_sensor_data(device_id, 88.1, now)
    print("  ✓ added 4 readings")
    
    # Batch insert
    batch = [
        {'device_id': device_id, 'watt': 91.0, 'measured_at': now + 60},
        {'device_id': device_id, 'watt': 89.5, 'measured_at': now + 120},
    ]
    count = svc.log_sensor_data_batch(batch)
    assert count == 2
    print(f"  ✓ log_sensor_data_batch: {count} rows")
    
    # Get latest readings
    readings = svc.get_latest_readings(user_id, limit=10)
    assert len(readings) >= 4
    print(f"  ✓ get_latest_readings: {len(readings)} readings")
    
    # Get daily summary
    summary = svc.get_daily_summary(user_id, days=7)
    print(f"  ✓ get_daily_summary: {len(summary)} days")
    
    # Calculate cost
    cost = svc.calculate_cost(100, 1444.70)
    assert cost == 144470.0
    print(f"  ✓ calculate_cost: Rp {cost}")


def test_device_toggle(user_id, device_id):
    """Test device state management."""
    print("\n🔹 Testing Device Toggle...")
    from services.device import DeviceService
    
    svc = DeviceService(TEST_DB)
    
    # Toggle ON
    result = svc.request_toggle_device(device_id, user_id)
    assert result['desired_state'] == 1
    print(f"  ✓ toggle ON: {result['message']}")
    
    # Toggle OFF
    result = svc.request_toggle_device(device_id, user_id)
    assert result['desired_state'] == 0
    print(f"  ✓ toggle OFF: {result['message']}")
    
    # Disable device
    result = svc.disable_device(device_id, user_id)
    assert result == True
    device = svc.get_device(device_id, user_id)
    assert device['status'] == 'disabled'
    print(f"  ✓ disable_device: status={device['status']}")


def test_service_container():
    """Test service container initialization."""
    print("\n🔹 Testing Service Container...")
    from services.container import init_services, get_service_info
    
    services = init_services(TEST_DB)
    assert 'user' in services
    assert 'device' in services
    assert 'energy' in services
    assert 'admin' in services
    print("  ✓ init_services: all services initialized")
    
    info = get_service_info()
    assert len(info) == 4
    print(f"  ✓ get_service_info: {len(info)} services documented")


def main():
    print("=" * 60)
    print("HomeAI Service Verification Test (Standalone)")
    print("=" * 60)
    
    # Setup
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    
    init_test_db(TEST_DB)
    print(f"\n📁 Test database: {TEST_DB}")
    
    try:
        # Run tests
        test_base_service()
        user_id = test_user_service()
        device_id = test_device_service(user_id)
        admin_id = test_admin_service(user_id, device_id)
        test_energy_service(device_id, user_id)
        test_device_toggle(user_id, device_id)
        test_service_container()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
            print(f"\n🧹 Cleaned up test database")


if __name__ == "__main__":
    main()
