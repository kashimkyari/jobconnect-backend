#!/usr/bin/env python3
"""
Quick OAuth debugging script
Tests if the backend can verify Google tokens and authenticate users
"""

import asyncio
import httpx
import json
from app.config import settings

BACKEND_URL = "http://172.20.10.9:8000/api/v1"

async def test_oauth_endpoint():
    """Test if OAuth endpoint is reachable and working"""
    print("=" * 60)
    print("OAuth Debug Test")
    print("=" * 60)
    
    print(f"\nBackend URL: {BACKEND_URL}")
    print(f"Google Client ID: {settings.GOOGLE_CLIENT_ID}")
    print(f"Backend serving at: http://172.20.10.9:8000")
    
    # Test 1: Check if backend is alive
    print("\n[Test 1] Checking if backend is running...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{BACKEND_URL}/auth/get-role", timeout=5)
            if response.status_code < 500:
                print("✅ Backend is running and responding")
            else:
                print(f"⚠️ Backend returned status {response.status_code}")
    except Exception as e:
        print(f"❌ Cannot reach backend: {e}")
        print("Make sure backend is running with: python app/main.py")
        return
    
    # Test 2: Check OAuth endpoint exists
    print("\n[Test 2] Checking if /oauth/login endpoint exists...")
    try:
        async with httpx.AsyncClient() as client:
            # Send invalid token to see if endpoint is reachable
            response = await client.post(
                f"{BACKEND_URL}/auth/oauth/login",
                json={
                    "provider": "google",
                    "token": "test-token"
                },
                timeout=5
            )
            print(f"✅ OAuth endpoint responded with status: {response.status_code}")
            if response.status_code == 401:
                print("✓ Expected 401 for invalid token (endpoint is working)")
            print(f"Response: {response.json()}")
    except Exception as e:
        print(f"❌ OAuth endpoint error: {e}")
    
    # Test 3: Show token verification method
    print("\n[Test 3] Token verification flow:")
    print(f"1. Mobile app gets ID token from Google")
    print(f"2. Mobile app sends POST /auth/oauth/login with:")
    print(f"   - provider: 'google'")
    print(f"   - token: <Google ID token>")
    print(f"3. Backend verifies token against Google's public keys")
    print(f"4. Backend checks audience: {settings.GOOGLE_CLIENT_ID}")
    
    # Test 4: Check configuration
    print("\n[Test 4] Configuration check:")
    print(f"✓ GOOGLE_CLIENT_ID is set: {bool(settings.GOOGLE_CLIENT_ID)}")
    print(f"✓ Database URL is set: {bool(settings.DATABASE_URL)}")
    print(f"✓ JWT_SECRET_KEY is set: {bool(settings.JWT_SECRET_KEY)}")
    
    print("\n" + "=" * 60)
    print("Debug checklist:")
    print("=" * 60)
    print("□ Backend is running at http://172.20.10.9:8000")
    print("□ Mobile app can reach backend (no firewall issues)")
    print("□ Google Client ID matches between backend and iOS app")
    print("□ Token is being sent correctly from mobile app")
    print("□ Check backend logs for token verification details")

if __name__ == "__main__":
    asyncio.run(test_oauth_endpoint())
