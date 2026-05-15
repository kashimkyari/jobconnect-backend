"""
Paystack Webhook Security Utilities

Provides helpers for verifying Paystack webhook signatures
to prevent forged webhook attacks.
"""

import hmac
import hashlib
from typing import Tuple
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)


class PaystackWebhookVerifier:
    """
    Verifies Paystack webhook signatures using HMAC-SHA512.
    
    Paystack computes the signature as:
    signature = HMAC-SHA512(webhook_secret, raw_request_body).hexdigest()
    
    This is sent in the X-Paystack-Signature header.
    """
    
    @staticmethod
    def verify_signature(
        raw_body: bytes,
        provided_signature: str,
        webhook_secret: str
    ) -> bool:
        """
        Verify a Paystack webhook signature.
        
        Args:
            raw_body: Raw request body as bytes
            provided_signature: Signature from X-Paystack-Signature header
            webhook_secret: Paystack webhook secret key
        
        Returns:
            True if signature is valid, False otherwise
        
        Raises:
            ValueError: If webhook_secret is empty
        """
        if not webhook_secret:
            raise ValueError("Webhook secret is required for signature verification")
        
        if not provided_signature:
            logger.warning("Webhook received without signature")
            return False
        
        # Calculate expected signature using HMAC-SHA512
        computed_signature = hmac.new(
            webhook_secret.encode(),
            raw_body,
            hashlib.sha512
        ).hexdigest()
        
        # Use constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(provided_signature, computed_signature)
        
        if not is_valid:
            logger.warning(
                f"Webhook signature mismatch. "
                f"Expected: {computed_signature[:20]}..., "
                f"Got: {provided_signature[:20]}..."
            )
        
        return is_valid
    
    @staticmethod
    def verify_and_raise(
        raw_body: bytes,
        provided_signature: str,
        webhook_secret: str,
        webhook_name: str = "Webhook"
    ) -> None:
        """
        Verify a Paystack webhook signature and raise HTTPException if invalid.
        
        Args:
            raw_body: Raw request body as bytes
            provided_signature: Signature from X-Paystack-Signature header
            webhook_secret: Paystack webhook secret key
            webhook_name: Name of webhook for logging (e.g., "Payment webhook")
        
        Raises:
            HTTPException: If signature is missing or invalid
            ValueError: If webhook_secret is not configured
        """
        if not webhook_secret:
            logger.error(f"{webhook_name}: PAYSTACK_WEBHOOK_SECRET not configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook secret not configured"
            )
        
        if not provided_signature:
            logger.warning(f"{webhook_name} received without signature header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Paystack-Signature header"
            )
        
        is_valid = PaystackWebhookVerifier.verify_signature(
            raw_body,
            provided_signature,
            webhook_secret
        )
        
        if not is_valid:
            logger.warning(f"{webhook_name} signature verification failed")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )


def verify_paystack_webhook(
    raw_body: bytes,
    signature_header: str,
    webhook_secret: str,
    webhook_name: str = "Webhook"
) -> bool:
    """
    Convenience function to verify Paystack webhook signature.
    
    Args:
        raw_body: Raw request body as bytes
        signature_header: X-Paystack-Signature header value
        webhook_secret: Paystack webhook secret
        webhook_name: Name for logging
    
    Returns:
        True if valid, False otherwise
    """
    try:
        PaystackWebhookVerifier.verify_and_raise(
            raw_body,
            signature_header,
            webhook_secret,
            webhook_name
        )
        return True
    except HTTPException:
        return False
