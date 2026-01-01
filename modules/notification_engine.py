"""
Real-time Notification Engine for Stock Dashboard

This module provides a comprehensive notification system supporting multiple channels:
- Email (SMTP)
- Push Notifications (Pushover, Pushbullet)
- Webhooks
- In-app Notifications

Features:
- Configurable alert thresholds
- Frequency limiting to prevent notification spam
- Notification deduplication
- Rate limiting per channel
- Async support for non-blocking operations
"""

import smtplib
import logging
import time
import hashlib
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from abc import ABC, abstractmethod
from collections import defaultdict
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from threading import Thread, Lock
import queue

logger = logging.getLogger(__name__)


class NotificationChannel(Enum):
    """Supported notification channels."""
    EMAIL = "email"
    PUSHOVER = "pushover"
    PUSHBULLET = "pushbullet"
    WEBHOOK = "webhook"
    IN_APP = "in_app"


class NotificationPriority(Enum):
    """Notification priority levels."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class AlertType(Enum):
    """Types of alerts supported by the system."""
    PRICE_ALERT = "price_alert"
    VOLUME_SPIKE = "volume_spike"
    TECHNICAL_SIGNAL = "technical_signal"
    PORTFOLIO_THRESHOLD = "portfolio_threshold"
    NEWS_ALERT = "news_alert"
    CUSTOM = "custom"


@dataclass
class NotificationConfig:
    """Configuration for notification thresholds and limits."""
    enabled: bool = True
    channel: NotificationChannel = NotificationChannel.IN_APP
    min_frequency_seconds: int = 300  # Minimum seconds between notifications
    max_per_hour: int = 10  # Maximum notifications per hour
    priority: NotificationPriority = NotificationPriority.MEDIUM
    include_historical_data: bool = True


@dataclass
class AlertThreshold:
    """Alert threshold configuration."""
    alert_type: AlertType
    symbol: str
    condition: str  # e.g., "price > 150", "volume > 1000000"
    value: float
    enabled: bool = True
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class Notification:
    """Notification object."""
    id: str
    title: str
    message: str
    alert_type: AlertType
    symbol: Optional[str]
    channels: List[NotificationChannel]
    priority: NotificationPriority
    timestamp: datetime
    data: Dict[str, Any]
    read: bool = False
    archived: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert notification to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['alert_type'] = self.alert_type.value
        data['priority'] = self.priority.name
        data['channels'] = [ch.value for ch in self.channels]
        return data


class NotificationChannelHandler(ABC):
    """Abstract base class for notification channel handlers."""
    
    @abstractmethod
    def send(self, notification: Notification, config: NotificationConfig) -> bool:
        """Send notification through the channel."""
        pass
    
    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate channel configuration."""
        pass


class EmailNotificationHandler(NotificationChannelHandler):
    """Handler for email notifications via SMTP."""
    
    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str, 
                 from_email: str, use_tls: bool = True):
        """
        Initialize email handler.
        
        Args:
            smtp_host: SMTP server host
            smtp_port: SMTP server port
            username: SMTP username
            password: SMTP password
            from_email: From email address
            use_tls: Use TLS encryption
        """
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email
        self.use_tls = use_tls
        self.logger = logging.getLogger(f"{__name__}.EmailHandler")
    
    def send(self, notification: Notification, config: NotificationConfig, 
             to_email: str) -> bool:
        """Send email notification."""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"[{notification.priority.name}] {notification.title}"
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Create plain text and HTML versions
            text_content = self._format_text(notification)
            html_content = self._format_html(notification)
            
            msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                if self.use_tls:
                    server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            self.logger.info(f"Email sent to {to_email} for notification {notification.id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to send email notification: {e}")
            return False
    
    def _format_text(self, notification: Notification) -> str:
        """Format notification as plain text."""
        text = f"{notification.title}\n"
        text += f"{'=' * len(notification.title)}\n\n"
        text += f"Priority: {notification.priority.name}\n"
        text += f"Type: {notification.alert_type.value}\n"
        text += f"Time: {notification.timestamp.isoformat()}\n\n"
        text += f"Message:\n{notification.message}\n"
        
        if notification.data:
            text += "\nAdditional Data:\n"
            for key, value in notification.data.items():
                text += f"  {key}: {value}\n"
        
        return text
    
    def _format_html(self, notification: Notification) -> str:
        """Format notification as HTML."""
        priority_color = {
            NotificationPriority.LOW: "#17a2b8",
            NotificationPriority.MEDIUM: "#ffc107",
            NotificationPriority.HIGH: "#fd7e14",
            NotificationPriority.CRITICAL: "#dc3545"
        }
        
        color = priority_color.get(notification.priority, "#6c757d")
        
        html = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background-color: {color}; color: white; padding: 10px; border-radius: 5px;">
                <h2 style="margin: 0;">{notification.title}</h2>
            </div>
            <div style="padding: 20px; background-color: #f8f9fa; margin-top: 10px; border-radius: 5px;">
                <p><strong>Priority:</strong> {notification.priority.name}</p>
                <p><strong>Type:</strong> {notification.alert_type.value}</p>
                <p><strong>Time:</strong> {notification.timestamp.isoformat()}</p>
                <hr>
                <p>{notification.message}</p>
        """
        
        if notification.data:
            html += "<h3>Additional Data:</h3><ul>"
            for key, value in notification.data.items():
                html += f"<li><strong>{key}:</strong> {value}</li>"
            html += "</ul>"
        
        html += """
            </div>
        </body>
        </html>
        """
        return html
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate email configuration."""
        required = ['smtp_host', 'smtp_port', 'username', 'password', 'from_email']
        return all(key in config for key in required)


class PushoverNotificationHandler(NotificationChannelHandler):
    """Handler for Pushover push notifications."""
    
    API_URL = "https://api.pushover.net/1/messages.json"
    
    def __init__(self, api_token: str):
        """
        Initialize Pushover handler.
        
        Args:
            api_token: Pushover API token
        """
        self.api_token = api_token
        self.logger = logging.getLogger(f"{__name__}.PushoverHandler")
    
    def send(self, notification: Notification, config: NotificationConfig, 
             user_key: str) -> bool:
        """Send push notification via Pushover."""
        try:
            priority_map = {
                NotificationPriority.LOW: -1,
                NotificationPriority.MEDIUM: 0,
                NotificationPriority.HIGH: 1,
                NotificationPriority.CRITICAL: 2
            }
            
            payload = {
                'token': self.api_token,
                'user': user_key,
                'title': notification.title,
                'message': notification.message,
                'priority': priority_map.get(notification.priority, 0),
                'timestamp': int(notification.timestamp.timestamp()),
                'sound': 'pushover' if notification.priority.value >= NotificationPriority.HIGH.value else None
            }
            
            response = requests.post(self.API_URL, data=payload, timeout=10)
            
            if response.status_code == 200:
                self.logger.info(f"Pushover notification sent for {notification.id}")
                return True
            else:
                self.logger.error(f"Pushover API error: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to send Pushover notification: {e}")
            return False
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Pushover configuration."""
        return 'api_token' in config and 'user_key' in config


class PushbulletNotificationHandler(NotificationChannelHandler):
    """Handler for Pushbullet push notifications."""
    
    API_URL = "https://api.pushbullet.com/v2/pushes"
    
    def __init__(self, api_key: str):
        """
        Initialize Pushbullet handler.
        
        Args:
            api_key: Pushbullet API key
        """
        self.api_key = api_key
        self.logger = logging.getLogger(f"{__name__}.PushbulletHandler")
    
    def send(self, notification: Notification, config: NotificationConfig) -> bool:
        """Send push notification via Pushbullet."""
        try:
            headers = {
                'Access-Token': self.api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {
                'type': 'note',
                'title': notification.title,
                'body': notification.message
            }
            
            response = requests.post(self.API_URL, json=payload, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.logger.info(f"Pushbullet notification sent for {notification.id}")
                return True
            else:
                self.logger.error(f"Pushbullet API error: {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to send Pushbullet notification: {e}")
            return False
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate Pushbullet configuration."""
        return 'api_key' in config


class WebhookNotificationHandler(NotificationChannelHandler):
    """Handler for webhook notifications."""
    
    def __init__(self):
        """Initialize webhook handler."""
        self.logger = logging.getLogger(f"{__name__}.WebhookHandler")
    
    def send(self, notification: Notification, config: NotificationConfig, 
             webhook_url: str) -> bool:
        """Send notification via webhook."""
        try:
            payload = notification.to_dict()
            
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'StockDashboard-NotificationEngine/1.0'
            }
            
            response = requests.post(webhook_url, json=payload, headers=headers, timeout=10)
            
            if response.status_code in [200, 201, 204]:
                self.logger.info(f"Webhook notification sent to {webhook_url}")
                return True
            else:
                self.logger.error(f"Webhook error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            self.logger.error(f"Failed to send webhook notification: {e}")
            return False
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate webhook configuration."""
        return 'webhook_url' in config


class InAppNotificationHandler(NotificationChannelHandler):
    """Handler for in-app notifications."""
    
    def __init__(self, max_stored: int = 500):
        """
        Initialize in-app handler.
        
        Args:
            max_stored: Maximum notifications to store
        """
        self.max_stored = max_stored
        self.notifications: List[Notification] = []
        self.lock = Lock()
        self.logger = logging.getLogger(f"{__name__}.InAppHandler")
    
    def send(self, notification: Notification, config: NotificationConfig) -> bool:
        """Store in-app notification."""
        try:
            with self.lock:
                self.notifications.append(notification)
                
                # Maintain max size
                if len(self.notifications) > self.max_stored:
                    self.notifications = self.notifications[-self.max_stored:]
            
            self.logger.info(f"In-app notification stored: {notification.id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store in-app notification: {e}")
            return False
    
    def get_notifications(self, unread_only: bool = False, 
                         limit: int = 50) -> List[Notification]:
        """Retrieve stored notifications."""
        with self.lock:
            notifications = self.notifications[::-1]  # Newest first
            
            if unread_only:
                notifications = [n for n in notifications if not n.read]
            
            return notifications[:limit]
    
    def mark_as_read(self, notification_id: str) -> bool:
        """Mark notification as read."""
        with self.lock:
            for notif in self.notifications:
                if notif.id == notification_id:
                    notif.read = True
                    return True
        return False
    
    def clear_notifications(self, archived_only: bool = True) -> int:
        """Clear notifications."""
        with self.lock:
            if archived_only:
                initial_count = len(self.notifications)
                self.notifications = [n for n in self.notifications if not n.archived]
                return initial_count - len(self.notifications)
            else:
                count = len(self.notifications)
                self.notifications.clear()
                return count
    
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate in-app configuration."""
        return True  # In-app notifications don't require special config


class NotificationEngine:
    """Main notification engine orchestrating all channels."""
    
    def __init__(self, async_mode: bool = True):
        """
        Initialize notification engine.
        
        Args:
            async_mode: Use async mode for sending notifications
        """
        self.async_mode = async_mode
        self.handlers: Dict[NotificationChannel, NotificationChannelHandler] = {}
        self.alert_thresholds: Dict[str, AlertThreshold] = {}
        self.notification_history: Dict[str, Notification] = {}
        self.frequency_limiter: Dict[str, datetime] = defaultdict(lambda: datetime.min)
        self.hourly_counter: Dict[str, List[datetime]] = defaultdict(list)
        self.logger = logging.getLogger(__name__)
        self.lock = Lock()
        self.config: Dict[NotificationChannel, NotificationConfig] = {}
        
        # Async queue
        self.notification_queue: queue.Queue = queue.Queue()
        self.async_thread: Optional[Thread] = None
        self.running = False
        
        # Register built-in handlers
        self._register_builtin_handlers()
    
    def _register_builtin_handlers(self):
        """Register built-in notification handlers."""
        self.handlers[NotificationChannel.IN_APP] = InAppNotificationHandler()
    
    def configure_email(self, smtp_host: str, smtp_port: int, username: str, 
                       password: str, from_email: str, to_email: str, 
                       use_tls: bool = True, config: Optional[NotificationConfig] = None):
        """Configure email notifications."""
        handler = EmailNotificationHandler(smtp_host, smtp_port, username, 
                                          password, from_email, use_tls)
        handler.to_email = to_email  # Store recipient
        self.handlers[NotificationChannel.EMAIL] = handler
        
        if config is None:
            config = NotificationConfig(channel=NotificationChannel.EMAIL)
        self.config[NotificationChannel.EMAIL] = config
    
    def configure_pushover(self, api_token: str, user_key: str, 
                          config: Optional[NotificationConfig] = None):
        """Configure Pushover notifications."""
        handler = PushoverNotificationHandler(api_token)
        handler.user_key = user_key  # Store user key
        self.handlers[NotificationChannel.PUSHOVER] = handler
        
        if config is None:
            config = NotificationConfig(channel=NotificationChannel.PUSHOVER)
        self.config[NotificationChannel.PUSHOVER] = config
    
    def configure_pushbullet(self, api_key: str, 
                            config: Optional[NotificationConfig] = None):
        """Configure Pushbullet notifications."""
        handler = PushbulletNotificationHandler(api_key)
        self.handlers[NotificationChannel.PUSHBULLET] = handler
        
        if config is None:
            config = NotificationConfig(channel=NotificationChannel.PUSHBULLET)
        self.config[NotificationChannel.PUSHBULLET] = config
    
    def configure_webhook(self, webhook_url: str, 
                         config: Optional[NotificationConfig] = None):
        """Configure webhook notifications."""
        handler = WebhookNotificationHandler()
        handler.webhook_url = webhook_url  # Store URL
        self.handlers[NotificationChannel.WEBHOOK] = handler
        
        if config is None:
            config = NotificationConfig(channel=NotificationChannel.WEBHOOK)
        self.config[NotificationChannel.WEBHOOK] = config
    
    def add_alert_threshold(self, alert: AlertThreshold) -> str:
        """
        Add an alert threshold.
        
        Args:
            alert: AlertThreshold configuration
            
        Returns:
            Alert ID
        """
        alert_id = self._generate_id(f"{alert.symbol}_{alert.alert_type.value}")
        
        with self.lock:
            self.alert_thresholds[alert_id] = alert
        
        self.logger.info(f"Alert threshold added: {alert_id}")
        return alert_id
    
    def remove_alert_threshold(self, alert_id: str) -> bool:
        """Remove an alert threshold."""
        with self.lock:
            if alert_id in self.alert_thresholds:
                del self.alert_thresholds[alert_id]
                self.logger.info(f"Alert threshold removed: {alert_id}")
                return True
        return False
    
    def get_alert_thresholds(self, symbol: Optional[str] = None) -> List[AlertThreshold]:
        """Get alert thresholds, optionally filtered by symbol."""
        with self.lock:
            thresholds = list(self.alert_thresholds.values())
        
        if symbol:
            thresholds = [t for t in thresholds if t.symbol == symbol and t.enabled]
        else:
            thresholds = [t for t in thresholds if t.enabled]
        
        return thresholds
    
    def notify(self, title: str, message: str, alert_type: AlertType, 
              channels: Optional[List[NotificationChannel]] = None,
              symbol: Optional[str] = None, priority: NotificationPriority = NotificationPriority.MEDIUM,
              data: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        Send a notification across specified channels.
        
        Args:
            title: Notification title
            message: Notification message
            alert_type: Type of alert
            channels: Channels to send through (defaults to all configured)
            symbol: Stock symbol (if applicable)
            priority: Notification priority
            data: Additional data to include
            
        Returns:
            Notification ID or None if failed
        """
        if data is None:
            data = {}
        
        # Default to all configured channels
        if channels is None:
            channels = list(self.handlers.keys())
        
        # Check frequency limits
        dedup_key = self._generate_dedup_key(symbol, alert_type)
        if not self._check_frequency_limit(dedup_key, channels):
            self.logger.warning(f"Notification rate limited: {dedup_key}")
            return None
        
        # Create notification
        notification = Notification(
            id=self._generate_id(dedup_key),
            title=title,
            message=message,
            alert_type=alert_type,
            symbol=symbol,
            channels=channels,
            priority=priority,
            timestamp=datetime.utcnow(),
            data=data
        )
        
        # Store in history
        with self.lock:
            self.notification_history[notification.id] = notification
        
        # Send through channels
        if self.async_mode and self.running:
            self.notification_queue.put((notification, channels))
        else:
            self._send_notification(notification, channels)
        
        return notification.id
    
    def _send_notification(self, notification: Notification, 
                          channels: List[NotificationChannel]):
        """Send notification through specified channels."""
        for channel in channels:
            if channel not in self.handlers:
                self.logger.warning(f"Handler not configured for channel: {channel}")
                continue
            
            handler = self.handlers[channel]
            config = self.config.get(channel, NotificationConfig(channel=channel))
            
            if not config.enabled:
                continue
            
            try:
                if channel == NotificationChannel.EMAIL:
                    handler.send(notification, config, handler.to_email)
                elif channel == NotificationChannel.PUSHOVER:
                    handler.send(notification, config, handler.user_key)
                elif channel == NotificationChannel.WEBHOOK:
                    handler.send(notification, config, handler.webhook_url)
                else:
                    handler.send(notification, config)
            except Exception as e:
                self.logger.error(f"Error sending to {channel}: {e}")
    
    def _check_frequency_limit(self, dedup_key: str, channels: List[NotificationChannel]) -> bool:
        """Check if notification should be rate limited."""
        with self.lock:
            for channel in channels:
                config = self.config.get(channel, NotificationConfig())
                
                # Check minimum frequency
                last_time = self.frequency_limiter.get(f"{dedup_key}_{channel.value}")
                if last_time and (datetime.utcnow() - last_time).total_seconds() < config.min_frequency_seconds:
                    return False
                
                # Check hourly limit
                hour_key = f"{dedup_key}_{channel.value}_hour"
                now = datetime.utcnow()
                hour_ago = now - timedelta(hours=1)
                
                # Clean old entries
                self.hourly_counter[hour_key] = [t for t in self.hourly_counter[hour_key] if t > hour_ago]
                
                if len(self.hourly_counter[hour_key]) >= config.max_per_hour:
                    return False
                
                self.frequency_limiter[f"{dedup_key}_{channel.value}"] = now
                self.hourly_counter[hour_key].append(now)
        
        return True
    
    def evaluate_thresholds(self, symbol: str, price: float, 
                           volume: Optional[float] = None,
                           additional_data: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Evaluate alert thresholds for a stock and send notifications if triggered.
        
        Args:
            symbol: Stock symbol
            price: Current price
            volume: Current volume
            additional_data: Additional data for evaluation
            
        Returns:
            List of triggered alert IDs
        """
        triggered_alerts = []
        thresholds = self.get_alert_thresholds(symbol)
        
        context = {
            'price': price,
            'volume': volume,
            'symbol': symbol,
            **(additional_data or {})
        }
        
        for alert_id, threshold in self.alert_thresholds.items():
            if threshold.symbol != symbol or not threshold.enabled:
                continue
            
            try:
                if self._evaluate_condition(threshold.condition, context):
                    data = {
                        'symbol': symbol,
                        'price': price,
                        'volume': volume,
                        'threshold_value': threshold.value,
                        'alert_type': threshold.alert_type.value
                    }
                    
                    self.notify(
                        title=f"{symbol} Alert: {threshold.alert_type.value}",
                        message=f"Alert condition met: {threshold.condition}",
                        alert_type=threshold.alert_type,
                        symbol=symbol,
                        data=data,
                        priority=NotificationPriority.HIGH
                    )
                    
                    triggered_alerts.append(alert_id)
            except Exception as e:
                self.logger.error(f"Error evaluating threshold {alert_id}: {e}")
        
        return triggered_alerts
    
    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Safely evaluate a condition string."""
        try:
            # Only allow safe operations
            allowed_names = {'price', 'volume', 'symbol', 'True', 'False', 'None'}
            allowed_names.update(context.keys())
            
            # Create a safe namespace
            safe_dict = {k: v for k, v in context.items() if isinstance(v, (int, float, str, bool, type(None)))}
            
            return bool(eval(condition, {"__builtins__": {}}, safe_dict))
        except Exception as e:
            self.logger.error(f"Error evaluating condition '{condition}': {e}")
            return False
    
    def start_async(self):
        """Start async notification processing."""
        if not self.async_mode or self.running:
            return
        
        self.running = True
        self.async_thread = Thread(target=self._async_worker, daemon=True)
        self.async_thread.start()
        self.logger.info("Async notification processor started")
    
    def stop_async(self):
        """Stop async notification processing."""
        if not self.running:
            return
        
        self.running = False
        if self.async_thread:
            self.async_thread.join(timeout=5)
        self.logger.info("Async notification processor stopped")
    
    def _async_worker(self):
        """Worker thread for async notification processing."""
        while self.running:
            try:
                notification, channels = self.notification_queue.get(timeout=1)
                self._send_notification(notification, channels)
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Error in async worker: {e}")
    
    def get_notification_history(self, symbol: Optional[str] = None, 
                                limit: int = 100) -> List[Dict[str, Any]]:
        """Get notification history."""
        with self.lock:
            history = list(self.notification_history.values())
        
        if symbol:
            history = [n for n in history if n.symbol == symbol]
        
        # Sort by timestamp (newest first)
        history.sort(key=lambda x: x.timestamp, reverse=True)
        
        return [n.to_dict() for n in history[:limit]]
    
    def get_in_app_notifications(self, unread_only: bool = False, 
                                limit: int = 50) -> List[Dict[str, Any]]:
        """Get in-app notifications."""
        handler = self.handlers.get(NotificationChannel.IN_APP)
        if isinstance(handler, InAppNotificationHandler):
            notifications = handler.get_notifications(unread_only, limit)
            return [n.to_dict() for n in notifications]
        return []
    
    def mark_notification_read(self, notification_id: str) -> bool:
        """Mark in-app notification as read."""
        handler = self.handlers.get(NotificationChannel.IN_APP)
        if isinstance(handler, InAppNotificationHandler):
            return handler.mark_as_read(notification_id)
        return False
    
    def archive_notification(self, notification_id: str) -> bool:
        """Archive a notification."""
        with self.lock:
            if notification_id in self.notification_history:
                self.notification_history[notification_id].archived = True
                return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification engine statistics."""
        with self.lock:
            return {
                'total_notifications': len(self.notification_history),
                'active_thresholds': len([t for t in self.alert_thresholds.values() if t.enabled]),
                'configured_channels': list(self.config.keys()),
                'async_mode': self.async_mode,
                'async_running': self.running,
                'queue_size': self.notification_queue.qsize() if self.async_mode else 0
            }
    
    @staticmethod
    def _generate_id(key: str) -> str:
        """Generate a unique ID from a key."""
        timestamp = int(time.time() * 1000)
        hash_val = hashlib.md5(f"{key}_{timestamp}".encode()).hexdigest()[:8]
        return f"{hash_val}_{timestamp}"
    
    @staticmethod
    def _generate_dedup_key(symbol: Optional[str], alert_type: AlertType) -> str:
        """Generate a deduplication key."""
        return f"{symbol or 'global'}_{alert_type.value}"


# Convenience singleton instance
_engine_instance: Optional[NotificationEngine] = None


def get_notification_engine(async_mode: bool = True) -> NotificationEngine:
    """Get or create the global notification engine instance."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = NotificationEngine(async_mode=async_mode)
    return _engine_instance


def reset_notification_engine():
    """Reset the global notification engine instance."""
    global _engine_instance
    if _engine_instance and _engine_instance.running:
        _engine_instance.stop_async()
    _engine_instance = None
