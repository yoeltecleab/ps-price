"""Email notification helper that records notifications in the database.

**What this module does**

When a tracked game's price drops, users want an email alert.  This module:

1. Builds **subject**, **plain-text**, and **HTML** email bodies.
2. Sends mail through **SMTP** (the standard internet protocol for email).
3. **Logs every attempt** in the ``notifications`` table — sent, failed, or
   skipped — so the UI can show history even when SMTP is not configured.

**Why ``asyncio.to_thread`` for email?**

Python's ``smtplib`` is **blocking** — while it talks to the mail server,
nothing else on that thread can run.  FastAPI is **async**, so we offload
the blocking SMTP work to a background thread via ``asyncio.to_thread`` and
``await`` its completion without freezing the web server.

**Email structure**

An email can have multiple "parts":

- ``text/plain`` — readable in any mail client.
- ``text/html`` — styled version (tables, colors) for modern clients.

``EmailMessage.set_content`` sets the plain part; ``add_alternative`` adds
the HTML part as a sibling MIME alternative.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage

from backend.app.config import Settings
from backend.app.email_themes import palette_for
from backend.app.repository import Repository


class EmailNotifier:
    """Send email notifications for watch events and log outcomes.

    Dependencies:

    - ``settings`` — SMTP host/port/credentials (from environment variables).
    - ``repo`` — database access to persist notification audit rows.

    If SMTP is not configured (``smtp_configured`` is False), we still log a
    ``skipped`` notification so developers can test price logic locally without
    sending real mail.
    """

    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    @property
    def configured(self) -> bool:
        """True when SMTP host and from-address are set in config."""
        return self.settings.smtp_configured

    async def send_price_notification(
        self,
        watch: dict,
        game: dict,
        reason: str,
        previous_price_cents: int | None = None,
        test: bool = False,
        theme_id: str | None = None,
    ) -> dict:
        """Send (or skip) a price-drop email and return the log row.

        ``watch`` and ``game`` are plain dicts from the repository layer
        (SQLite rows converted via ``row_to_dict``).

        Flow:
            build messages → if SMTP missing: log skipped
                          → else: await thread SMTP send
                          → log sent/failed
                          → mark watch as notified (unless test)
        """
        subject = self._subject(game, reason, test)
        text_body = self._body(watch, game, reason, previous_price_cents, test)
        html_body = self._html_body(
            watch, game, reason, previous_price_cents, test, theme_id or watch.get("theme_id")
        )
        if not self.configured:
            return self.repo.log_notification(
                watch.get("id"),
                game.get("id"),
                watch["email"],
                subject,
                text_body,
                "skipped",
                reason,
                "SMTP is not configured",
                user_id=watch.get("user_id"),
            )

        try:
            # Run blocking SMTP in a worker thread; await returns to async world.
            await asyncio.to_thread(
                self._send_sync, watch["email"], subject, text_body, html_body
            )
        except Exception as exc:  # pragma: no cover
            return self.repo.log_notification(
                watch.get("id"),
                game.get("id"),
                watch["email"],
                subject,
                text_body,
                "failed",
                reason,
                str(exc)[:1000],
                user_id=watch.get("user_id"),
            )

        notification = self.repo.log_notification(
            watch.get("id"),
            game.get("id"),
            watch["email"],
            subject,
            text_body,
            "sent",
            reason,
            user_id=watch.get("user_id"),
        )
        if not test:
            # Remember last notified price so we do not spam the same drop.
            self.repo.mark_watch_notified(watch["id"], game.get("current_price_cents"))
        return notification

    async def send_system_email(
        self,
        to_email: str,
        subject: str,
        text_body: str,
        *,
        html_body: str | None = None,
        user_id: int | None = None,
    ) -> dict:
        """Send operational mail (verification links, password reset, etc.).

        Same SMTP + logging pattern as ``send_price_notification``, but not
        tied to a specific game/watch row.
        """
        if not self.configured:
            return self.repo.log_notification(
                None,
                None,
                to_email,
                subject,
                text_body,
                "skipped",
                "system",
                "SMTP is not configured",
                user_id=user_id,
            )
        try:
            await asyncio.to_thread(
                self._send_sync,
                to_email,
                subject,
                text_body,
                html_body or f"<pre>{text_body}</pre>",
            )
        except Exception as exc:  # pragma: no cover
            return self.repo.log_notification(
                None,
                None,
                to_email,
                subject,
                text_body,
                "failed",
                "system",
                str(exc)[:1000],
                user_id=user_id,
            )
        return self.repo.log_notification(
            None, None, to_email, subject, text_body, "sent", "system", user_id=user_id
        )

    def _send_sync(
        self, to_email: str, subject: str, text_body: str, html_body: str
    ) -> None:
        """Blocking SMTP send — must run in a thread, not on the event loop.

        Steps mirror what any mail client does under the hood:

        1. Build a MIME message with headers (From, To, Subject).
        2. Connect to the SMTP server (plain or SSL).
        3. Optionally upgrade with STARTTLS.
        4. Authenticate if username/password provided.
        5. ``send_message`` transmits the email.
        """
        msg = EmailMessage()
        msg["From"] = self.settings.notification_from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

        # SMTP_SSL = encrypted from the first byte; SMTP + starttls = upgrade later.
        smtp_cls = smtplib.SMTP_SSL if self.settings.smtp_use_ssl else smtplib.SMTP
        with smtp_cls(
            self.settings.smtp_host,
            self.settings.smtp_port,
            timeout=self.settings.smtp_timeout_seconds,
        ) as smtp:
            if self.settings.smtp_use_tls and not self.settings.smtp_use_ssl:
                smtp.starttls()
            if self.settings.smtp_username:
                smtp.login(self.settings.smtp_username, self.settings.smtp_password or "")
            smtp.send_message(msg)

    def _subject(self, game: dict, reason: str, test: bool) -> str:
        """One-line inbox subject summarizing the alert."""
        prefix = "[PS Price test]" if test else "[PS Price]"
        price = game.get("current_price_formatted") or "price unavailable"
        return f"{prefix} {game.get('name', 'Tracked game')} is {price}"

    def _body(
        self,
        watch: dict,
        game: dict,
        reason: str,
        previous_price_cents: int | None,
        test: bool,
    ) -> str:
        """Plain-text body — works in terminal mail readers and as fallback."""
        lines = [
            "This is a test notification." if test else "A tracked PlayStation Store price matched your watch.",
            "",
            f"Game: {game.get('name')}",
            f"Current price: {game.get('current_price_formatted') or 'Unavailable'}",
            f"Original price: {game.get('original_price_formatted') or 'Unavailable'}",
            f"Discount: {game.get('discount_text') or 'None'}",
            f"Reason: {reason}",
        ]
        if previous_price_cents is not None:
            lines.append(f"Previous stored price: {previous_price_cents / 100:.2f}")
        if watch.get("target_price_cents") is not None:
            lines.append(f"Target price: {watch['target_price_cents'] / 100:.2f}")
        lines.extend(["", f"Store URL: {game.get('store_url')}"])
        return "\n".join(lines)

    def _html_body(
        self,
        watch: dict,
        game: dict,
        reason: str,
        previous_price_cents: int | None,
        test: bool,
        theme_id: str | None,
    ) -> str:
        """HTML body with inline CSS (email clients ignore external stylesheets).

        We build the HTML as an f-string template.  ``palette_for`` picks
        colors based on the user's chosen email theme.
        """
        palette = palette_for(theme_id)
        headline = "Test alert" if test else "Price watch triggered"
        subline = (
            "This is a test notification from PS Price."
            if test
            else "A PlayStation Store price matched your deployed watch."
        )
        discount = game.get("discount_text") or "None"
        target = (
            f"${watch['target_price_cents'] / 100:.2f}"
            if watch.get("target_price_cents") is not None
            else "Any drop"
        )
        previous = (
            f"${previous_price_cents / 100:.2f}"
            if previous_price_cents is not None
            else "—"
        )
        store_url = game.get("store_url") or "#"
        image = game.get("image_url") or ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>PS Price Alert</title>
</head>
<body style="margin:0;padding:0;background:{palette['bg']};font-family:ui-monospace,Menlo,Consolas,monospace;color:{palette['ink']};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{palette['bg']};padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:{palette['surface']};border:1px solid {palette['border']};border-radius:14px;overflow:hidden;">
          <tr>
            <td style="padding:24px 28px;border-bottom:1px solid {palette['border']};">
              <p style="margin:0;font-size:11px;letter-spacing:0.28em;text-transform:uppercase;color:{palette['accent']};">PS PRICE · 2050</p>
              <h1 style="margin:12px 0 0;font-size:24px;line-height:1.2;color:{palette['ink']};">{headline}</h1>
              <p style="margin:10px 0 0;font-size:14px;line-height:1.6;color:{palette['muted']};">{subline}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:24px 28px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  {"<td width='88' style='padding-right:16px;vertical-align:top;'><img src='" + image + "' alt='' width='88' height='88' style='display:block;border-radius:10px;border:1px solid " + palette['border'] + ";' /></td>" if image else ""}
                  <td style="vertical-align:top;">
                    <p style="margin:0;font-size:18px;font-weight:700;color:{palette['ink']};">{game.get('name', 'Tracked game')}</p>
                    <p style="margin:14px 0 0;font-size:32px;font-weight:700;color:{palette['accent']};">{game.get('current_price_formatted') or '—'}</p>
                    <p style="margin:6px 0 0;font-size:14px;color:{palette['muted']};text-decoration:line-through;">{game.get('original_price_formatted') or ''}</p>
                  </td>
                </tr>
              </table>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:24px;">
                <tr><td style="padding:8px 0;font-size:12px;color:{palette['muted']};text-transform:uppercase;letter-spacing:0.16em;">Discount</td><td align="right" style="padding:8px 0;font-size:14px;color:{palette['ink']};">{discount}</td></tr>
                <tr><td style="padding:8px 0;font-size:12px;color:{palette['muted']};text-transform:uppercase;letter-spacing:0.16em;">Reason</td><td align="right" style="padding:8px 0;font-size:14px;color:{palette['ink']};">{reason}</td></tr>
                <tr><td style="padding:8px 0;font-size:12px;color:{palette['muted']};text-transform:uppercase;letter-spacing:0.16em;">Previous</td><td align="right" style="padding:8px 0;font-size:14px;color:{palette['ink']};">{previous}</td></tr>
                <tr><td style="padding:8px 0;font-size:12px;color:{palette['muted']};text-transform:uppercase;letter-spacing:0.16em;">Target</td><td align="right" style="padding:8px 0;font-size:14px;color:{palette['ink']};">{target}</td></tr>
              </table>
              <p style="margin:28px 0 0;text-align:center;">
                <a href="{store_url}" style="display:inline-block;padding:12px 22px;background:{palette['primary']};color:#ffffff;text-decoration:none;border-radius:10px;font-size:13px;letter-spacing:0.08em;text-transform:uppercase;">Open in PS Store</a>
              </p>
            </td>
          </tr>
        </table>
        <p style="margin:18px 0 0;font-size:11px;color:{palette['muted']};">PS Price · PlayStation deal intelligence</p>
      </td>
    </tr>
  </table>
</body>
</html>"""
