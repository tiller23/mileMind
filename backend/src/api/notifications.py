"""Notification helpers for invite request flow.

Discord webhook for admin alerts, Resend for user emails.
Both are fire-and-forget — failures are logged but never block the response.
"""

from __future__ import annotations

import html
import logging
import re

import httpx

from src.config import get_settings

logger = logging.getLogger(__name__)


def _strip_discord_markdown(text: str) -> str:
    """Strip Discord markdown special characters and mentions from text.

    Args:
        text: Raw text that may contain markdown or mentions.

    Returns:
        Sanitized plain text safe for Discord messages.
    """
    # Remove @everyone, @here, role/user mentions
    text = re.sub(r"@(everyone|here|&?\d+)", "", text)
    # Strip markdown formatting characters
    text = re.sub(r"[*_~`|>\\]", "", text)
    return text.strip()


async def send_discord_notification(message: str) -> None:
    """Send a message to the configured Discord webhook.

    Args:
        message: Plain text message content (will be sanitized).

    Raises:
        RuntimeError: If no webhook URL is configured.
    """
    settings = get_settings()
    if not settings.discord_webhook_url:
        logger.debug("Discord webhook not configured, skipping notification")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            settings.discord_webhook_url,
            json={
                "content": message,
                "allowed_mentions": {"parse": []},
            },
        )
        resp.raise_for_status()
    logger.info("Discord notification sent")


async def send_approval_email(to_email: str, name: str) -> None:
    """Send an invite approval email via Resend.

    Args:
        to_email: Recipient email address.
        name: Recipient's display name.

    Raises:
        RuntimeError: If Resend is not configured.
    """
    settings = get_settings()
    if not settings.resend_api_key:
        logger.debug("Resend not configured, skipping approval email")
        return

    safe_name = html.escape(name)
    email_html = f"""
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px;">
        <h2 style="color: #1e293b; margin-bottom: 8px;">You're in, {safe_name}!</h2>
        <p style="color: #64748b; font-size: 16px; line-height: 1.6;">
            Your MileMind invite has been approved. Log in to create your first
            AI-powered training plan.
        </p>
        <a href="{settings.frontend_url}/login"
           style="display: inline-block; margin-top: 16px; padding: 12px 24px; background: #2563eb; color: white; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 14px;">
            Create My Plan
        </a>
        <p style="color: #94a3b8; font-size: 13px; margin-top: 32px;">
            &mdash; The MileMind Team
        </p>
    </div>
    """

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.resend_from_email,
                "to": [to_email],
                "subject": "Your MileMind access is ready!",
                "html": email_html,
            },
        )
        resp.raise_for_status()
    logger.info("Approval email sent to %s", to_email)
