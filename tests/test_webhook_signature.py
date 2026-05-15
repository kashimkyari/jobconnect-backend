"""
Test script for Paystack webhook signature verification.

This script demonstrates how to test webhook signature verification
by simulating Paystack webhook calls with valid signatures.

Usage:
    python test_webhook_signature.py
"""

import hmac
import hashlib
import json
import asyncio
import httpx
from typing import Dict, Any

# Configuration
WEBHOOK_SECRET = "your_webhook_secret_here"
WEBHOOK_URL = "http://localhost:8000/api/v1/payments/callback"
WITHDRAWAL_WEBHOOK_URL = "http://localhost:8000/api/v1/withdrawals/paystack-webhook"


def create_signature(payload: Dict[str, Any], webhook_secret: str) -> str:
    """
    Create a Paystack-compatible webhook signature.
    
    Args:
        payload: Webhook payload dictionary
        webhook_secret: Paystack webhook secret
    
    Returns:
        HMAC-SHA512 signature as hex string
    """
    # Convert payload to JSON (must be valid JSON)
    raw_body = json.dumps(payload).encode('utf-8')
    
    # Calculate HMAC-SHA512
    signature = hmac.new(
        webhook_secret.encode('utf-8'),
        raw_body,
        hashlib.sha512
    ).hexdigest()
    
    return signature


def create_payment_webhook_payload() -> Dict[str, Any]:
    """Create a sample payment webhook payload (charge.success)."""
    return {
        "event": "charge.success",
        "data": {
            "id": 123456789,
            "reference": "test_payment_ref_12345",
            "amount": 10000,  # 100.00 NGN in kobo
            "currency": "NGN",
            "status": "success",
            "authorization": {
                "authorization_code": "AUTH_abc123xyz",
                "bin": "412345",
                "last4": "4321",
                "exp_month": 12,
                "exp_year": 25,
                "channel": "card",
                "card_type": "VISA"
            },
            "customer": {
                "id": 1,
                "email": "user@example.com",
                "customer_code": "CUS_abc123xyz",
                "first_name": "John",
                "last_name": "Doe"
            },
            "created_at": "2026-02-06T10:00:00.000Z"
        }
    }


def create_transfer_webhook_payload(event: str = "transfer.success") -> Dict[str, Any]:
    """
    Create a sample transfer webhook payload.
    
    Args:
        event: Either 'transfer.success' or 'transfer.failed'
    """
    return {
        "event": event,
        "data": {
            "reference": "test_transfer_ref_12345",
            "transfer_code": "TRF_abc123xyz",
            "amount": 50000,  # 500.00 NGN in kobo
            "currency": "NGN",
            "status": "success" if event == "transfer.success" else "failed",
            "recipient": {
                "domain": "ng",
                "type": "nuban",
                "currency": "NGN",
                "name": "Test User",
                "details": {
                    "authorization_url": None
                },
                "description": None,
                "recipient_code": "RCP_testrecipient123"
            },
            "reason": "Test withdrawal",
            "source": "balance",
            "source_details": None,
            "failures": None if event == "transfer.success" else {
                "reason": "Bank rejected transfer"
            },
            "titan_code": None,
            "transfersessionid": None,
            "created_at": "2026-02-06T10:00:00.000Z"
        }
    }


async def test_webhook(url: str, payload: Dict[str, Any], webhook_secret: str, webhook_name: str):
    """
    Test a webhook by sending it with a valid signature.
    
    Args:
        url: Webhook endpoint URL
        payload: Webhook payload
        webhook_secret: Webhook secret key
        webhook_name: Display name for logging
    """
    print(f"\n{'='*60}")
    print(f"Testing {webhook_name}")
    print(f"{'='*60}")
    
    # Create JSON payload
    raw_body = json.dumps(payload).encode('utf-8')
    
    # Create signature
    signature = create_signature(payload, webhook_secret)
    
    print(f"\nPayload: {json.dumps(payload, indent=2)}")
    print(f"\nSignature: {signature}")
    
    # Test with valid signature
    print(f"\n[1] Testing with VALID signature...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                content=raw_body,
                headers={
                    "X-Paystack-Signature": signature,
                    "Content-Type": "application/json"
                }
            )
            print(f"✓ Status: {response.status_code}")
            print(f"✓ Response: {response.json()}")
        except Exception as e:
            print(f"✗ Error: {str(e)}")
    
    # Test with invalid signature
    print(f"\n[2] Testing with INVALID signature (should be rejected)...")
    invalid_signature = "invalid_signature_12345abcde"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                content=raw_body,
                headers={
                    "X-Paystack-Signature": invalid_signature,
                    "Content-Type": "application/json"
                }
            )
            print(f"✓ Status: {response.status_code}")
            if response.status_code == 401:
                print(f"✓ Correctly rejected (401 Unauthorized)")
            else:
                print(f"✗ Should have been rejected with 401, got {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Error: {str(e)}")
    
    # Test without signature
    print(f"\n[3] Testing WITHOUT signature header (should be rejected)...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                url,
                content=raw_body,
                headers={"Content-Type": "application/json"}
            )
            print(f"✓ Status: {response.status_code}")
            if response.status_code == 401:
                print(f"✓ Correctly rejected (401 Unauthorized)")
            else:
                print(f"✗ Should have been rejected with 401, got {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Error: {str(e)}")


async def run_tests():
    """Run all webhook tests."""
    print("\n" + "="*60)
    print("PAYSTACK WEBHOOK SIGNATURE VERIFICATION TEST SUITE")
    print("="*60)
    print(f"\nWebhook Secret: {WEBHOOK_SECRET[:10]}...{WEBHOOK_SECRET[-10:]}")
    print(f"Payment Webhook: {WEBHOOK_URL}")
    print(f"Transfer Webhook: {WITHDRAWAL_WEBHOOK_URL}\n")
    
    # Test payment webhook
    payment_payload = create_payment_webhook_payload()
    await test_webhook(
        WEBHOOK_URL,
        payment_payload,
        WEBHOOK_SECRET,
        "Payment Webhook (charge.success)"
    )
    
    # Test transfer success webhook
    transfer_payload = create_transfer_webhook_payload("transfer.success")
    await test_webhook(
        WITHDRAWAL_WEBHOOK_URL,
        transfer_payload,
        WEBHOOK_SECRET,
        "Transfer Success Webhook (transfer.success)"
    )
    
    # Test transfer failed webhook
    transfer_failed_payload = create_transfer_webhook_payload("transfer.failed")
    await test_webhook(
        WITHDRAWAL_WEBHOOK_URL,
        transfer_failed_payload,
        WEBHOOK_SECRET,
        "Transfer Failed Webhook (transfer.failed)"
    )
    
    print("\n" + "="*60)
    print("TEST SUITE COMPLETED")
    print("="*60)


if __name__ == "__main__":
    print("\nPaystack Webhook Signature Verification Test")
    print("=" * 60)
    print("\nNOTE: Make sure to:")
    print("1. Start your backend server on localhost:8000")
    print("2. Set PAYSTACK_WEBHOOK_SECRET in .env")
    print("3. Update WEBHOOK_SECRET in this script to match your .env")
    print("\nStarting tests in 2 seconds...\n")
    
    import time
    time.sleep(2)
    
    asyncio.run(run_tests())
