# ===============================
# services/energy.py - Energy Monitoring Service (PRODUCTION)
# ===============================
# Handles: Energy logging, analytics, cost calculation
#
# SCHEMA (from database.py):
# energy_logs: id, device_id, watt (REAL), measured_at (INTEGER/unix timestamp)
#
# NOTE: This service receives data from Edge (Rust) via API.
# Edge is responsible for real-time collection; Python stores & analyzes.

from typing import Optional
from datetime import datetime, timedelta
from services.base import BaseService


class EnergyService(BaseService):
    """
    Service untuk energy monitoring dan sensor data.
    
    Methods required by routes:
    - log_sensor_data(device_id, watt, measured_at) -> routes/api.py
    - get_latest_readings(user_id, limit) -> routes/api.py
    - get_daily_summary(user_id, days) -> routes/api.py
    
    Data Flow:
    1. Edge (Rust) collects watt readings from smart plugs
    2. Edge batches & sends to Python via POST /api/sensor/update
    3. Python stores in energy_logs table
    4. Python provides analytics via API
    """
    
    # ===============================
    # SENSOR DATA LOGGING
    # ===============================
    
    def log_sensor_data(
        self, 
        device_id: int, 
        watt: float, 
        measured_at: int
    ) -> Optional[int]:
        """
        Log energy reading from Edge/sensor.
        
        Args:
            device_id: Device that reported the reading
            watt: Power consumption in watts
            measured_at: Unix timestamp (seconds) when measured
        
        Returns: log_id on success, None on failure
        """
        return self.run_query(
            """
            INSERT INTO energy_logs (device_id, watt, measured_at)
            VALUES (?, ?, ?)
            """,
            (device_id, watt, measured_at),
            commit=True
        )
    
    def log_sensor_data_batch(
        self, 
        readings: list[dict]
    ) -> Optional[int]:
        """
        Log multiple energy readings at once.
        
        Args:
            readings: List of dicts with device_id, watt, measured_at
        
        Returns: Number of rows inserted
        """
        if not readings:
            return 0
        
        args_list = [
            (r['device_id'], r['watt'], r['measured_at']) 
            for r in readings
        ]
        
        return self.run_query_many(
            """
            INSERT INTO energy_logs (device_id, watt, measured_at)
            VALUES (?, ?, ?)
            """,
            args_list,
            commit=True
        )
    
    # ===============================
    # DATA RETRIEVAL
    # ===============================
    
    def get_latest_readings(self, user_id: int, limit: int = 20) -> list:
        """
        Get latest energy readings for all user's devices.
        
        Returns readings ordered by time (oldest first for charts).
        """
        result = self.run_query(
            """
            SELECT 
                e.id,
                e.device_id,
                e.watt,
                e.measured_at,
                d.name as device_name
            FROM energy_logs e
            JOIN devices d ON e.device_id = d.id
            WHERE d.user_id = ?
            ORDER BY e.measured_at DESC
            LIMIT ?
            """,
            (user_id, limit)
        )
        
        # Reverse for chronological order (charts expect left-to-right)
        return (result or [])[::-1]
    
    def get_device_readings(
        self, 
        device_id: int, 
        user_id: int, 
        limit: int = 100
    ) -> list:
        """
        Get readings for specific device with ownership check.
        """
        result = self.run_query(
            """
            SELECT 
                e.id,
                e.device_id,
                e.watt,
                e.measured_at
            FROM energy_logs e
            JOIN devices d ON e.device_id = d.id
            WHERE e.device_id = ? AND d.user_id = ?
            ORDER BY e.measured_at DESC
            LIMIT ?
            """,
            (device_id, user_id, limit)
        )
        return (result or [])[::-1]
    
    def get_readings_in_range(
        self, 
        user_id: int, 
        start_ts: int, 
        end_ts: int
    ) -> list:
        """
        Get readings within a time range.
        
        Args:
            user_id: Owner of devices
            start_ts: Start timestamp (unix seconds)
            end_ts: End timestamp (unix seconds)
        """
        result = self.run_query(
            """
            SELECT 
                e.id,
                e.device_id,
                e.watt,
                e.measured_at,
                d.name as device_name
            FROM energy_logs e
            JOIN devices d ON e.device_id = d.id
            WHERE d.user_id = ? 
              AND e.measured_at >= ? 
              AND e.measured_at <= ?
            ORDER BY e.measured_at ASC
            """,
            (user_id, start_ts, end_ts)
        )
        return result or []
    
    # ===============================
    # ANALYTICS
    # ===============================
    
    def get_daily_summary(self, user_id: int, days: int = 7) -> list:
        """
        Get daily energy summary for user's devices.
        
        Returns aggregated stats per day:
        - date: YYYY-MM-DD
        - avg_watt: Average power
        - max_watt: Peak power
        - min_watt: Minimum power
        - total_wh: Total watt-hours (approximate)
        - reading_count: Number of samples
        """
        # Calculate start timestamp
        start_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        
        result = self.run_query(
            """
            SELECT 
                DATE(measured_at, 'unixepoch') as date,
                AVG(e.watt) as avg_watt,
                MAX(e.watt) as max_watt,
                MIN(e.watt) as min_watt,
                COUNT(*) as reading_count
            FROM energy_logs e
            JOIN devices d ON e.device_id = d.id
            WHERE d.user_id = ? AND e.measured_at >= ?
            GROUP BY DATE(measured_at, 'unixepoch')
            ORDER BY date DESC
            """,
            (user_id, start_ts)
        )
        
        # Calculate approximate watt-hours
        # Assuming readings are ~1 minute apart on average
        summaries = []
        for row in (result or []):
            summary = dict(row)
            # Rough estimate: avg_watt * hours_of_readings
            # reading_count / 60 = approximate hours if readings per minute
            hours = summary['reading_count'] / 60.0
            summary['total_wh'] = round(summary['avg_watt'] * hours, 2)
            summaries.append(summary)
        
        return summaries
    
    def get_device_daily_summary(
        self, 
        device_id: int, 
        user_id: int, 
        days: int = 7
    ) -> list:
        """Get daily summary for specific device."""
        start_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        
        result = self.run_query(
            """
            SELECT 
                DATE(e.measured_at, 'unixepoch') as date,
                AVG(e.watt) as avg_watt,
                MAX(e.watt) as max_watt,
                MIN(e.watt) as min_watt,
                COUNT(*) as reading_count
            FROM energy_logs e
            JOIN devices d ON e.device_id = d.id
            WHERE e.device_id = ? AND d.user_id = ? AND e.measured_at >= ?
            GROUP BY DATE(e.measured_at, 'unixepoch')
            ORDER BY date DESC
            """,
            (device_id, user_id, start_ts)
        )
        return result or []
    
    def get_current_power(self, user_id: int) -> dict:
        """
        Get current total power consumption across all devices.
        Uses most recent reading from each device.
        """
        result = self.run_query(
            """
            SELECT 
                d.id as device_id,
                d.name as device_name,
                e.watt,
                e.measured_at
            FROM devices d
            LEFT JOIN (
                SELECT device_id, watt, measured_at,
                       ROW_NUMBER() OVER (PARTITION BY device_id ORDER BY measured_at DESC) as rn
                FROM energy_logs
            ) e ON d.id = e.device_id AND e.rn = 1
            WHERE d.user_id = ? AND d.status = 'active'
            """,
            (user_id,)
        )
        
        devices = result or []
        total_watts = sum(d['watt'] or 0 for d in devices)
        
        return {
            'total_watts': round(total_watts, 2),
            'devices': devices,
            'device_count': len(devices)
        }
    
    # ===============================
    # COST CALCULATION
    # ===============================
    
    def calculate_cost(
        self, 
        total_kwh: float, 
        tarif_per_kwh: float = 1444.70
    ) -> float:
        """
        Calculate electricity cost (Indonesian PLN tariff).
        
        Args:
            total_kwh: Total kilowatt-hours consumed
            tarif_per_kwh: Price per kWh (default: PLN R1/1300VA)
        
        Returns: Cost in IDR (Rupiah)
        """
        return round(total_kwh * tarif_per_kwh, 2)
    
    def get_monthly_cost_estimate(
        self, 
        user_id: int, 
        tarif_per_kwh: float = 1444.70
    ) -> dict:
        """
        Estimate monthly electricity cost based on recent usage.
        """
        # Get last 7 days summary
        summary = self.get_daily_summary(user_id, days=7)
        
        if not summary:
            return {
                'daily_avg_kwh': 0,
                'monthly_estimate_kwh': 0,
                'monthly_estimate_cost': 0,
                'tarif_per_kwh': tarif_per_kwh
            }
        
        # Calculate daily average kWh
        total_wh = sum(s.get('total_wh', 0) for s in summary)
        days_with_data = len(summary)
        daily_avg_wh = total_wh / days_with_data if days_with_data > 0 else 0
        daily_avg_kwh = daily_avg_wh / 1000.0
        
        # Project to 30 days
        monthly_kwh = daily_avg_kwh * 30
        monthly_cost = self.calculate_cost(monthly_kwh, tarif_per_kwh)
        
        return {
            'daily_avg_kwh': round(daily_avg_kwh, 3),
            'monthly_estimate_kwh': round(monthly_kwh, 2),
            'monthly_estimate_cost': monthly_cost,
            'tarif_per_kwh': tarif_per_kwh
        }
    
    # ===============================
    # CLEANUP
    # ===============================
    
    def cleanup_old_logs(self, days_to_keep: int = 90) -> int:
        """
        Delete energy logs older than specified days.
        Run periodically to manage database size.
        
        Returns: Number of rows deleted
        """
        cutoff_ts = int((datetime.utcnow() - timedelta(days=days_to_keep)).timestamp())
        
        result = self.run_query(
            "DELETE FROM energy_logs WHERE measured_at < ?",
            (cutoff_ts,),
            commit=True
        )
        return result or 0
