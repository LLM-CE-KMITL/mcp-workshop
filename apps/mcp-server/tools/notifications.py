from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path

def register(mcp) -> None:
    @mcp.tool(
        annotations={
            "title": "Send a notification",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False
        }
    )
    def send_notification(to: str, subject: str, body: str, attachment_path: str | None = None) -> dict:
        """Send a notification email or message to the NOC team.
        
        Args:
            to: Recipient address (e.g., noc@nt.co.th)
            subject: The subject of the notification
            body: The main content/summary to send
            attachment_path: Optional path to a report file to attach
        """
        backend = os.getenv("NOTIFIER_BACKEND", "email")

        # "mailhog" and "email" are the same backend: SMTP to localhost:1025,
        # which is Mailhog's own SMTP port in this project's docker-compose.
        # There is no real mail server here - accept both names instead of
        # forcing .env to say "email" when the thing it is pointing at is
        # named "mailhog" everywhere else in the stack.
        if backend in ("email", "mailhog"):
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = "mcp-agent@nt.co.th"
            msg["To"] = to

            if attachment_path:
                path = Path(attachment_path)
                if path.exists():
                    msg.add_attachment(
                        path.read_bytes(),
                        maintype="text",
                        subtype=path.suffix.lstrip('.') or "plain",
                        filename=path.name
                    )

            try:
                with smtplib.SMTP("localhost", 1025) as server:
                    server.send_message(msg)
                return {"ok": True, "method": backend, "status": f"Sent successfully to {to}"}
            except Exception as e:
                return {"ok": False, "error": f"Failed to send email: {e}"}

        elif backend == "telegram":
            return {"ok": True, "method": "telegram", "status": "Telegram backend selected (Mock)"}

        return {"ok": False, "error": f"Unknown backend: {backend}"}