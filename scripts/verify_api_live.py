#!/usr/bin/env python3
"""Direct Live HTTP Verification of all AquaShift Phase 4 API Endpoints.

Starts uvicorn in a subprocess, executes real HTTP requests against each endpoint,
verifies status codes and structured response schemas, and terminates cleanly.
"""
import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_venv_python() -> str:
    venv_python = ROOT_DIR / ".venv" / "bin" / "python"
    return str(venv_python) if venv_python.exists() else sys.executable


def http_get(url: str):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def http_post(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def main():
    python_bin = get_venv_python()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT_DIR)

    print("=" * 60)
    print("🌾 Starting AquaShift Live API Server Verification")
    print(f"🐍 Python: {python_bin}")
    print("=" * 60)

    # Start Uvicorn backend
    server_proc = subprocess.Popen(
        [python_bin, "-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8008"],
        cwd=str(ROOT_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = "http://127.0.0.1:8008"

    try:
        # Wait for server to become responsive
        max_attempts = 20
        connected = False
        for i in range(max_attempts):
            time.sleep(0.5)
            try:
                status, data = http_get(f"{base_url}/api/health")
                if status == 200 and data.get("status") == "ok":
                    connected = True
                    break
            except Exception:
                continue

        if not connected:
            print("❌ Failed to connect to Uvicorn server within timeout.")
            return 1

        print("✅ Backend server live on port 8008.\n")

        # 1. GET /api/health
        st, data = http_get(f"{base_url}/api/health")
        print(f"1. GET /api/health -> HTTP {st}")
        print(f"   Status: {data.get('status')} | Version: {data.get('version')} | Offline: {data.get('offline_mode')}\n")
        assert st == 200 and data.get("status") == "ok"

        # 2. GET /api/config
        st, data = http_get(f"{base_url}/api/config")
        print(f"2. GET /api/config -> HTTP {st}")
        print(f"   Crops ({len(data['crops'])}): {[c['crop_id'] for c in data['crops']]}")
        print(f"   Scenarios ({len(data['rainfall_scenarios'])}): {[s['scenario_id'] for s in data['rainfall_scenarios']]}")
        print(f"   Modes: {data['optimization_modes']}\n")
        assert st == 200 and len(data["crops"]) == 5

        # 3. GET /api/baseline
        st, data = http_get(f"{base_url}/api/baseline?total_land_ha=10.0")
        print(f"3. GET /api/baseline -> HTTP {st}")
        print(f"   Land: {data['total_land_ha']} ha | Water: {data['total_water_use_m3']:,.1f} m³ | Food: {data['total_food_kcal']/1e6:.2f}M kcal | Net Income: ₹{data['total_net_income_inr']:,.1f}\n")
        assert st == 200 and data["total_food_kcal"] == 162750000.0

        # 4. POST /api/predict
        pred_req = {"rainfall_scenario": "deficit", "water_availability_ratio": 0.80}
        st, data = http_post(f"{base_url}/api/predict", pred_req)
        print(f"4. POST /api/predict -> HTTP {st}")
        paddy = data["predictions"]["paddy"]
        print(f"   Paddy: yield={paddy['predicted_yield_t_ha']} t/ha, water={paddy['predicted_water_demand_m3_ha']} m³/ha")
        wheat = data["predictions"]["wheat"]
        print(f"   Wheat: yield={wheat['predicted_yield_t_ha']} t/ha, water={wheat['predicted_water_demand_m3_ha']} m³/ha\n")
        assert st == 200 and len(data["predictions"]) == 5

        # 5. POST /api/optimize
        opt_req = {
            "total_land_ha": 10.0,
            "rainfall_scenario": "normal",
            "water_budget_reduction_pct": 20.0,
            "optimization_mode": "weighted",
        }
        st, data = http_post(f"{base_url}/api/optimize", opt_req)
        print(f"5. POST /api/optimize -> HTTP {st}")
        print(f"   Solver: {data['solver_status']} | Mode: {data['optimization_mode']}")
        print(f"   Water Used: {data['total_water_use_m3']:,.1f} m³ / Budget: {data['water_budget_m3']:,.1f} m³ (slack: {data['water_slack_m3']})")
        print(f"   Food Prod: {data['total_food_kcal']:,.0f} kcal (slack: {data['food_slack_kcal']})")
        print(f"   Net Income: ₹{data['total_net_income_inr']:,.1f} (slack: {data['income_slack_inr']})")
        print(f"   Bottlenecks: {data['diagnosis']['missed_targets'] or 'None (All targets satisfied)'}\n")
        assert st == 200 and data["solver_status"] in ("OPTIMAL", "FEASIBLE")

        # 6. POST /api/stress-test
        st, data = http_post(f"{base_url}/api/stress-test", {})
        print(f"6. POST /api/stress-test -> HTTP {st}")
        print(f"   Strict Status: {data['strict_solve_status']}")
        print(f"   Recovery Status: {data['recovery_solve_status']}")
        print(f"   Bottleneck Ranks: {[b['dimension'] + ': ' + b['severity'] for b in data['closest_feasible_plan']['diagnosis']['bottleneck_ranking']]}\n")
        assert st == 200 and data["strict_solve_status"] == "INFEASIBLE" and data["recovery_solve_status"] == "OPTIMAL"

        # 7. POST /api/simulate/sweep
        sweep_req = {"total_land_ha": 10.0, "start_ratio": 1.0, "end_ratio": 0.2, "step": 0.1}
        st, data = http_post(f"{base_url}/api/simulate/sweep", sweep_req)
        print(f"7. POST /api/simulate/sweep -> HTTP {st}")
        print(f"   Points Count: {len(data['points'])}")
        print(f"   First Point: {data['points'][0]['water_availability_ratio']} -> Water: {data['points'][0]['total_water_use_m3']:,.1f} m³")
        print(f"   Last Point:  {data['points'][-1]['water_availability_ratio']} -> Water: {data['points'][-1]['total_water_use_m3']:,.1f} m³")
        print(f"   Tipping Point: {data['tipping_point_water_ratio']} ({data['tipping_point_description']})\n")
        assert st == 200 and len(data["points"]) == 9

        print("🎉 ALL 7 LIVE API ENDPOINTS VERIFIED SUCCESSFULLY WITH REAL HTTP REQUESTS!")
        return 0

    finally:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            server_proc.kill()
        print("🛑 Uvicorn live server terminated cleanly.")


if __name__ == "__main__":
    sys.exit(main() or 0)
