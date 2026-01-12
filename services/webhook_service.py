"""
Webhook Service
Handles webhook registration and event triggering
"""

import requests
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import threading

logger = logging.getLogger(__name__)

# In-memory webhook storage (in production, use database)
_webhooks: Dict[str, List[Dict[str, Any]]] = {}
_webhook_lock = threading.Lock()


def register_webhook(webhook_id: str, url: str, events: List[str], secret: Optional[str] = None) -> bool:
    """
    Register a webhook
    
    Args:
        webhook_id: Unique identifier for webhook
        url: Webhook URL to call
        events: List of events to subscribe to (e.g., ['reconciliation.complete', 'match.created'])
        secret: Optional secret for webhook authentication
    
    Returns:
        True if registered successfully
    """
    try:
        with _webhook_lock:
            if webhook_id not in _webhooks:
                _webhooks[webhook_id] = []
            
            _webhooks[webhook_id].append({
                "url": url,
                "events": events,
                "secret": secret,
                "created_at": datetime.now().isoformat(),
                "active": True
            })
        
        logger.info(f"Webhook registered: {webhook_id} -> {url}")
        return True
    except Exception as e:
        logger.error(f"Error registering webhook: {e}", exc_info=True)
        return False


def unregister_webhook(webhook_id: str) -> bool:
    """Unregister a webhook"""
    try:
        with _webhook_lock:
            if webhook_id in _webhooks:
                del _webhooks[webhook_id]
                logger.info(f"Webhook unregistered: {webhook_id}")
                return True
        return False
    except Exception as e:
        logger.error(f"Error unregistering webhook: {e}", exc_info=True)
        return False


def trigger_webhook(event: str, data: Dict[str, Any]) -> int:
    """
    Trigger webhooks for a specific event
    
    Args:
        event: Event name (e.g., 'reconciliation.complete')
        data: Event data to send
    
    Returns:
        Number of webhooks triggered
    """
    triggered = 0
    
    with _webhook_lock:
        for webhook_id, hooks in _webhooks.items():
            for hook in hooks:
                if not hook.get("active", True):
                    continue
                
                if event in hook.get("events", []):
                    # Trigger in background thread
                    thread = threading.Thread(
                        target=_send_webhook,
                        args=(hook["url"], event, data, hook.get("secret")),
                        daemon=True
                    )
                    thread.start()
                    triggered += 1
    
    if triggered > 0:
        logger.info(f"Triggered {triggered} webhook(s) for event: {event}")
    
    return triggered


def _send_webhook(url: str, event: str, data: Dict[str, Any], secret: Optional[str] = None):
    """Send webhook request in background"""
    try:
        payload = {
            "event": event,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "OCR-Reconciliation-Webhook/1.0"
        }
        
        if secret:
            headers["X-Webhook-Secret"] = secret
        
        response = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=10
        )
        
        response.raise_for_status()
        logger.info(f"Webhook sent successfully: {url} (event: {event})")
    except requests.exceptions.RequestException as e:
        logger.error(f"Webhook failed: {url} (event: {event}) - {e}")
    except Exception as e:
        logger.error(f"Error sending webhook: {e}", exc_info=True)


def list_webhooks() -> Dict[str, List[Dict[str, Any]]]:
    """List all registered webhooks"""
    with _webhook_lock:
        return _webhooks.copy()

