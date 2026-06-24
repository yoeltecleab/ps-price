"""Email notification helper that records notifications in the database."""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

from backend.app.config import Settings
from backend.app.email_templates import price_alert_html, system_email_html
from backend.app.repository import Repository


REASON_LABELS = {
    "target_met": "Target price reached",
    "price_drop": "Price dropped",
    "min_drop": "Minimum drop threshold met",
    "preview": "Preview",
}


class EmailNotifier:
    def __init__(self, settings: Settings, repo: Repository):
        self.settings = settings
        self.repo = repo

    @property
    def configured(self) -> bool:
        return self.settings.smtp_configured

    def resolve_theme_id(
        self, watch: dict | None, user_preferred_theme: str | None = None
    ) -> str | None:
        """Prefer the user's last-saved UI theme over the watch default."""
        if user_preferred_theme:
            return user_preferred_theme
        if watch:
            return watch.get("theme_id")
        return None

    async def send_price_notification(
        self,
        watch: dict,
        game: dict,
        reason: str,
        previous_price_cents: int | None = None,
        test: bool = False,
        theme_id: str | None = None,
        user_preferred_theme: str | None = None,
    ) -> dict:
        resolved_theme = self.resolve_theme_id(watch, user_preferred_theme or theme_id)
        subject = self._subject(game, reason, test)
        text_body = self._body(watch, game, reason, previous_price_cents, test)
        html_body = price_alert_html(
            theme_id=resolved_theme,
            game_name=game.get("name", "Tracked game"),
            current_price=game.get("current_price_formatted") or "—",
            original_price=game.get("original_price_formatted") or "—",
            discount=game.get("discount_text") or "None",
            reason_label=REASON_LABELS.get(reason, reason.replace("_", " ").title()),
            previous_price=(
                f"${previous_price_cents / 100:.2f}" if previous_price_cents is not None else "—"
            ),
            target_label=(
                f"${watch['target_price_cents'] / 100:.2f}"
                if watch.get("target_price_cents") is not None
                else "Any qualifying drop"
            ),
            image_url=game.get("image_url"),
            store_url=game.get("store_url") or "#",
            preview=test,
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
        theme_id: str | None = "abyss",
        cta_label: str | None = None,
        cta_href: str | None = None,
        title: str | None = None,
    ) -> dict:
        if html_body is None and cta_label and cta_href:
            html_body = system_email_html(
                theme_id=theme_id,
                title=title or subject,
                message=text_body.split("\n\n")[0],
                cta_label=cta_label,
                cta_href=cta_href,
            )
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
        msg = EmailMessage()
        msg["From"] = formataddr(
            (self.settings.notification_from_name, self.settings.notification_from_email)
        )
        msg["To"] = to_email
        msg["Subject"] = subject
        msg["Reply-To"] = self.settings.notification_from_email
        msg["X-Entity-Ref-ID"] = "ps-prices-notification"
        msg.set_content(text_body)
        msg.add_alternative(html_body, subtype="html")

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
        name = game.get("name", "Tracked game")
        price = game.get("current_price_formatted") or "updated price"
        if test:
            return f"Preview: {name} — {price}"
        return f"{name} — now {price}"

    def _body(
        self,
        watch: dict,
        game: dict,
        reason: str,
        previous_price_cents: int | None,
        test: bool,
    ) -> str:
        lines = [
            "Preview of your PS Prices alert." if test else "A PlayStation Store price matched your alert.",
            "",
            f"Game: {game.get('name')}",
            f"Current price: {game.get('current_price_formatted') or 'Unavailable'}",
            f"Original price: {game.get('original_price_formatted') or 'Unavailable'}",
            f"Discount: {game.get('discount_text') or 'None'}",
            f"Trigger: {REASON_LABELS.get(reason, reason)}",
        ]
        if previous_price_cents is not None:
            lines.append(f"Previous price: ${previous_price_cents / 100:.2f}")
        if watch.get("target_price_cents") is not None:
            lines.append(f"Target price: ${watch['target_price_cents'] / 100:.2f}")
        if watch.get("min_drop_cents"):
            lines.append(f"Min drop amount: ${watch['min_drop_cents'] / 100:.2f}")
        if watch.get("min_drop_percent"):
            lines.append(f"Min drop percent: {watch['min_drop_percent']}%")
        lines.extend(["", f"Store: {game.get('store_url')}"])
        return "\n".join(lines)
