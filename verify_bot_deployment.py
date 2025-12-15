#!/usr/bin/env python3
"""
🔍 Verifica Deploy Bot ErixCast
Script per verificare che il bot sia completamente operativo
"""

import requests
import time
import json
from datetime import datetime

def test_health_endpoint():
    """Test health check endpoint"""
    print("🏥 Testing health endpoint...")
    try:
        response = requests.get("https://erixcastbot.onrender.com/health", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Health check PASSED")
            print(f"   Status: {data.get('status', 'unknown')}")
            print(f"   Database: {data.get('database_status', 'unknown')}")
            print(f"   Bot: {data.get('bot_status', 'unknown')}")
            print(f"   Uptime: {data.get('uptime', 'unknown')}")
            return True
        else:
            print(f"❌ Health check FAILED - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check ERROR: {e}")
        return False

def test_ping_endpoint():
    """Test ping endpoint"""
    print("\n🎯 Testing ping endpoint...")
    try:
        response = requests.get("https://erixcastbot.onrender.com/ping", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Ping PASSED")
            print(f"   Status: {data.get('status', 'unknown')}")
            print(f"   Timestamp: {data.get('timestamp', 'unknown')}")
            return True
        else:
            print(f"❌ Ping FAILED - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Ping ERROR: {e}")
        return False

def test_status_endpoint():
    """Test status endpoint"""
    print("\n📊 Testing status endpoint...")
    try:
        response = requests.get("https://erixcastbot.onrender.com/status", timeout=30)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Status PASSED")
            print(f"   Status: {data.get('status', 'unknown')}")
            print(f"   Memory: {data.get('memory_usage_mb', 'unknown')} MB")
            print(f"   CPU: {data.get('cpu_percent', 'unknown')}%")
            print(f"   Uptime: {data.get('uptime_seconds', 'unknown')}s")
            return True
        else:
            print(f"❌ Status FAILED - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Status ERROR: {e}")
        return False

def test_root_endpoint():
    """Test root endpoint"""
    print("\n🌐 Testing root endpoint...")
    try:
        response = requests.get("https://erixcastbot.onrender.com/", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Root PASSED")
            print(f"   Service: {data.get('service', 'unknown')}")
            print(f"   Status: {data.get('status', 'unknown')}")
            print(f"   Version: {data.get('version', 'unknown')}")
            return True
        else:
            print(f"❌ Root FAILED - Status: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Root ERROR: {e}")
        return False

def comprehensive_test():
    """Run comprehensive deployment test"""
    print("🚀 ErixCast Bot Deployment Verification")
    print("=" * 50)
    print(f"⏰ Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    tests = [
        ("Root Endpoint", test_root_endpoint),
        ("Health Check", test_health_endpoint),
        ("Ping Test", test_ping_endpoint),
        ("Status Check", test_status_endpoint)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} EXCEPTION: {e}")
            results.append((test_name, False))
        
        time.sleep(2)  # Brief pause between tests
    
    print("\n" + "=" * 50)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n📈 Overall Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED - Bot is FULLY OPERATIONAL!")
        print("✅ ErixCast Bot deployment SUCCESSFUL")
        print("🌐 Bot is ready for production use")
        return True
    else:
        print(f"⚠️ {total - passed} tests failed - Bot may have issues")
        print("🔍 Check Render logs for more details")
        return False

if __name__ == "__main__":
    success = comprehensive_test()
    
    print(f"\n🔗 Useful Links:")
    print(f"   🏥 Health: https://erixcastbot.onrender.com/health")
    print(f"   📊 Status: https://erixcastbot.onrender.com/status")
    print(f"   🎯 Ping: https://erixcastbot.onrender.com/ping")
    print(f"   📋 Actions: https://github.com/flyerix/erixbot/actions")
    print(f"   🌐 Render: https://dashboard.render.com")
    
    if success:
        print(f"\n🎯 DEPLOYMENT VERIFICATION: ✅ SUCCESS")
    else:
        print(f"\n🎯 DEPLOYMENT VERIFICATION: ❌ ISSUES DETECTED")