"""
Expo Push Notification Client
Handles sending push notifications via Expo's REST API
"""
import logging
from typing import List, Dict, Optional, Tuple
import httpx
from app.config import settings
import asyncio

logger = logging.getLogger(__name__)


class ExpoClient:
    """Client for sending push notifications through Expo servers"""
    
    BASE_URL = "https://exp.host/--/api/v2"
    MAX_TOKENS_PER_REQUEST = 100  # Expo's limit for tokens per request
    MAX_RECEIPT_IDS_PER_REQUEST = 300
    MAX_RETRIES = 3
    
    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize Expo client with access token
        
        Args:
            access_token: Expo access token from environment or explicitly provided
        """
        self.access_token = access_token or getattr(settings, 'EXPO_ACCESS_TOKEN', None)
        if not self.access_token:
            logger.warning("EXPO_ACCESS_TOKEN not configured - push notifications will fail")
    
    async def send_push_notifications(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict] = None,
        image: Optional[str] = None,
    ) -> Tuple[Dict, List[str]]:
        """
        Send push notifications to a list of tokens
        
        Args:
            tokens: List of Expo push tokens
            title: Notification title
            body: Notification message body
            data: Optional extra data to include in notification
        
        Returns:
            Tuple of (results_dict, failed_tokens)
                - results_dict: {token: {'status': 'ok'|'error', 'id': ticket_id or error}}
                - failed_tokens: List of tokens that failed to send
        """
        if not tokens or not self.access_token:
            logger.error("Cannot send: missing tokens or access token")
            return {}, tokens
        
        results = {}
        failed_tokens = []
        
        # Chunk tokens to comply with Expo's limit
        for chunk in self._chunk_tokens(tokens):
            chunk_results, chunk_failed = await self._send_chunk(
                chunk, title, body, data, image
            )
            results.update(chunk_results)
            failed_tokens.extend(chunk_failed)
        
        return results, failed_tokens

    async def get_push_receipts(self, ticket_ids: List[str]) -> Dict[str, Dict]:
        """
        Fetch Expo push receipts for ticket IDs.

        Returns:
            Dict keyed by ticket_id with Expo receipt objects.
        """
        if not ticket_ids or not self.access_token:
            return {}

        receipt_results: Dict[str, Dict] = {}
        headers = {
            "Host": "exp.host",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }

        for chunk in self._chunk_ticket_ids(ticket_ids):
            response = None
            for attempt in range(self.MAX_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            f"{self.BASE_URL}/push/getReceipts",
                            json={"ids": chunk},
                            headers=headers,
                        )
                except httpx.RequestError as e:
                    if attempt == self.MAX_RETRIES - 1:
                        logger.error("Expo receipts request error: %s", e)
                        break
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue

                if response.status_code == 200:
                    break

                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(0.5 * (2 ** attempt))
                    continue

                logger.error(
                    "Expo receipts API error: %s - %s",
                    response.status_code,
                    response.text,
                )
                response = None
                break

            if response is None:
                continue

            payload = response.json()
            data = payload.get("data") or {}
            if isinstance(data, dict):
                receipt_results.update(data)

        return receipt_results
    
    async def _send_chunk(
        self,
        tokens: List[str],
        title: str,
        body: str,
        data: Optional[Dict] = None,
        image: Optional[str] = None,
    ) -> Tuple[Dict, List[str]]:
        """
        Send a single chunk of notifications (max 100 tokens)
        
        Returns:
            Tuple of (results_dict, failed_tokens)
        """
        messages = []
        for token in tokens:
            message = {
                "to": token,
                "sound": "default",
                "title": title,
                "body": body,
                "data": data or {},
                "badge": 1,
            }
            if image:
                message["image"] = image
            messages.append(message)
        
        headers = {
            "Host": "exp.host",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
            "Content-Type": "application/json",
        }
        
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        
        results = {}
        failed_tokens = []
        
        try:
            response = None
            for attempt in range(self.MAX_RETRIES):
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            f"{self.BASE_URL}/push/send",
                            json=messages,
                            headers=headers,
                        )
                except httpx.RequestError as e:
                    if attempt == self.MAX_RETRIES - 1:
                        raise
                    delay = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Expo request error on attempt %s/%s: %s. Retrying in %.1fs",
                        attempt + 1,
                        self.MAX_RETRIES,
                        e,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                if response.status_code == 200:
                    break

                # Retry transient upstream errors and rate limits
                if response.status_code in (429, 500, 502, 503, 504) and attempt < self.MAX_RETRIES - 1:
                    delay = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Expo API transient error on attempt %s/%s: %s. Retrying in %.1fs",
                        attempt + 1,
                        self.MAX_RETRIES,
                        response.status_code,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue

                logger.error(f"Expo API error: {response.status_code} - {response.text}")
                return {}, tokens

            if response is None:
                logger.error("Expo API request did not return a response")
                return {}, tokens
            
            response_data = response.json()
            
            # Process response
            if "data" in response_data:
                for token, result in zip(tokens, response_data["data"]):
                    if result.get("status") == "ok":
                        results[token] = {
                            "status": "ok",
                            "id": result.get("id"),
                        }
                        logger.debug(f"Notification sent successfully to {token[:20]}...")
                    else:
                        details = result.get("details") or {}
                        results[token] = {
                            "status": "error",
                            "error": result.get("message", "Unknown error"),
                            "error_code": details.get("error"),
                        }
                        failed_tokens.append(token)
                        logger.warning(f"Failed to send to {token[:20]}...: {result.get('message')}")
            
        except httpx.RequestError as e:
            logger.error(f"HTTP request error sending to Expo: {e}")
            failed_tokens = tokens
        except Exception as e:
            logger.error(f"Unexpected error in _send_chunk: {e}")
            failed_tokens = tokens
        
        return results, failed_tokens
    
    @staticmethod
    def _chunk_tokens(tokens: List[str], chunk_size: int = MAX_TOKENS_PER_REQUEST) -> List[List[str]]:
        """
        Split tokens into chunks of specified size
        
        Args:
            tokens: List of tokens to chunk
            chunk_size: Size of each chunk (default: 100 per Expo limit)
        
        Returns:
            List of token chunks
        """
        return [
            tokens[i : i + chunk_size]
            for i in range(0, len(tokens), chunk_size)
        ]
    
    def validate_token(self, token: str) -> bool:
        """
        Validate if a token is in valid Expo format
        
        Args:
            token: Expo push token to validate
        
        Returns:
            True if token is valid format, False otherwise
        """
        if not token:
            return False

        # Accept both legacy and current Expo token prefixes.
        valid_prefixes = ("ExponentPushToken[", "ExpoPushToken[")
        return token.endswith("]") and any(token.startswith(prefix) for prefix in valid_prefixes)

    @staticmethod
    def _chunk_ticket_ids(ticket_ids: List[str], chunk_size: int = MAX_RECEIPT_IDS_PER_REQUEST) -> List[List[str]]:
        return [
            ticket_ids[i : i + chunk_size]
            for i in range(0, len(ticket_ids), chunk_size)
        ]


# Singleton instance
_expo_client = None


def get_expo_client() -> ExpoClient:
    """Get or create Expo client singleton"""
    global _expo_client
    if _expo_client is None:
        _expo_client = ExpoClient()
    return _expo_client
