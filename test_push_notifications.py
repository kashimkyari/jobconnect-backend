#!/usr/bin/env python3
"""
Test script for push notifications end-to-end workflow
Tests mobile token registration and admin broadcast sending

Usage:
    python test_push_notifications.py <admin_token> <user_token> <expo_token>
    
Example:
    python test_push_notifications.py "eyJhbGc..." "ExponentPushToken[...]"
"""

import asyncio
import httpx
import sys
import json
from datetime import datetime

BASE_URL = "https://monitor-backend.jetcamstudio.com:8000"  # Change to your backend URL
API_V1_PREFIX = "/api/v1"

class PushNotificationTester:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.api_url = f"{base_url}{API_V1_PREFIX}"
        self.admin_token = None
        self.user_id = None
        
    async def setup_admin_auth(self, admin_token: str):
        """Set up admin authentication"""
        self.admin_token = admin_token
        print(f"✓ Admin token set: {admin_token[:30]}...")
        
    async def test_push_token_registration(self, expo_token: str) -> bool:
        """Test 1: Register push token with backend"""
        print("\n" + "="*60)
        print("TEST 1: Register Expo Push Token with Backend")
        print("="*60)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            payload = {
                "expo_push_token": expo_token
            }
            
            try:
                response = await client.post(
                    f"{self.api_url}/users/me/push-token",
                    json=payload,
                    headers=headers
                )
                
                print(f"Request: POST /users/me/push-token")
                print(f"Payload: {json.dumps(payload, indent=2)}")
                print(f"Status Code: {response.status_code}")
                print(f"Response: {json.dumps(response.json(), indent=2)}")
                
                if response.status_code == 200:
                    print("✓ PASS: Push token registered successfully")
                    return True
                else:
                    print(f"✗ FAIL: Unexpected status code {response.status_code}")
                    return False
                    
            except Exception as e:
                print(f"✗ FAIL: {str(e)}")
                return False
    
    async def test_send_test_notification(self) -> bool:
        """Test 2: Send test notification to admin's own device"""
        print("\n" + "="*60)
        print("TEST 2: Send Test Notification to Admin Device")
        print("="*60)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            try:
                response = await client.post(
                    f"{self.api_url}/admin/push-notifications/test",
                    headers=headers
                )
                
                print(f"Request: POST /admin/push-notifications/test")
                print(f"Status Code: {response.status_code}")
                print(f"Response: {json.dumps(response.json(), indent=2)}")
                
                if response.status_code == 200 and response.json().get('success'):
                    print("✓ PASS: Test notification sent successfully")
                    return True
                else:
                    print(f"✗ FAIL: {response.json()}")
                    return False
                    
            except Exception as e:
                print(f"✗ FAIL: {str(e)}")
                return False
    
    async def test_preview_recipients(self, filters: dict) -> bool:
        """Test 3: Preview notification recipients"""
        print("\n" + "="*60)
        print("TEST 3: Preview Notification Recipients")
        print("="*60)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            try:
                response = await client.post(
                    f"{self.api_url}/admin/push-notifications/preview",
                    json=filters,
                    headers=headers
                )
                
                print(f"Request: POST /admin/push-notifications/preview")
                print(f"Filters: {json.dumps(filters, indent=2)}")
                print(f"Status Code: {response.status_code}")
                print(f"Response: {json.dumps(response.json(), indent=2)}")
                
                if response.status_code == 200:
                    data = response.json()
                    total_users = data.get('total_users', 0)
                    print(f"✓ PASS: {total_users} users match the filters")
                    return True
                else:
                    print(f"✗ FAIL: {response.json()}")
                    return False
                    
            except Exception as e:
                print(f"✗ FAIL: {str(e)}")
                return False
    
    async def test_send_broadcast(self, title: str, message: str, filters: dict) -> bool:
        """Test 4: Send broadcast push notification"""
        print("\n" + "="*60)
        print("TEST 4: Send Broadcast Push Notification")
        print("="*60)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            payload = {
                "title": title,
                "message": message,
                "filters": filters
            }
            
            try:
                response = await client.post(
                    f"{self.api_url}/admin/push-notifications/send",
                    json=payload,
                    headers=headers
                )
                
                print(f"Request: POST /admin/push-notifications/send")
                print(f"Payload: {json.dumps(payload, indent=2)}")
                print(f"Status Code: {response.status_code}")
                print(f"Response: {json.dumps(response.json(), indent=2)}")
                
                if response.status_code == 200 and response.json().get('success'):
                    recipients = response.json().get('total_recipients', 0)
                    print(f"✓ PASS: Broadcast sent to {recipients} recipients")
                    return True
                else:
                    print(f"✗ FAIL: {response.json()}")
                    return False
                    
            except Exception as e:
                print(f"✗ FAIL: {str(e)}")
                return False
    
    async def test_get_delivery_logs(self) -> bool:
        """Test 5: Get delivery logs"""
        print("\n" + "="*60)
        print("TEST 5: Get Push Notification Delivery Logs")
        print("="*60)
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {self.admin_token}"}
            
            try:
                response = await client.get(
                    f"{self.api_url}/admin/push-notifications/logs?skip=0&limit=10",
                    headers=headers
                )
                
                print(f"Request: GET /admin/push-notifications/logs?skip=0&limit=10")
                print(f"Status Code: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"Response: Total={data.get('total')}, Count={len(data.get('notifications', []))}")
                    
                    # Pretty print first few logs
                    logs = data.get('notifications', [])
                    for log in logs[:3]:
                        print(f"  - {log.get('title')}: {log.get('delivery_status')}")
                    
                    print("✓ PASS: Logs retrieved successfully")
                    return True
                else:
                    print(f"✗ FAIL: {response.json()}")
                    return False
                    
            except Exception as e:
                print(f"✗ FAIL: {str(e)}")
                return False


async def main():
    """Run all tests"""
    if len(sys.argv) < 2:
        print("Usage: python test_push_notifications.py <admin_token> [expo_token]")
        print("\nExample with token registration:")
        print("  python test_push_notifications.py 'eyJhbGc...' 'ExponentPushToken[...]'")
        print("\nExample admin-only tests:")
        print("  python test_push_notifications.py 'eyJhbGc...'")
        sys.exit(1)
    
    admin_token = sys.argv[1]
    expo_token = sys.argv[2] if len(sys.argv) > 2 else None
    
    tester = PushNotificationTester()
    await tester.setup_admin_auth(admin_token)
    
    results = {}
    
    # Test token registration if provided
    if expo_token:
        results['Token Registration'] = await tester.test_push_token_registration(expo_token)
        results['Test Notification'] = await tester.test_send_test_notification()
    
    # Test admin endpoints
    filters = {
        "user_types": ["worker"],
        "subscription_status": None,
        "require_kyc_verified": False,
        "exclude_push_disabled": True
    }
    
    results['Preview Recipients'] = await tester.test_preview_recipients(filters)
    
    if results.get('Preview Recipients'):
        results['Send Broadcast'] = await tester.test_send_broadcast(
            title="Test Notification",
            message="This is a test notification from the admin panel",
            filters=filters
        )
    
    results['Delivery Logs'] = await tester.test_get_delivery_logs()
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    asyncio.run(main())
