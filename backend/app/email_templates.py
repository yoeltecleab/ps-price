"""HTML email layout shared by price alerts and system messages."""

from __future__ import annotations

from backend.app.email_themes import palette_for


def _layout(
    *,
    theme_id: str | None,
    eyebrow: str,
    title: str,
    subtitle: str,
    body_html: str,
    cta_label: str | None = None,
    cta_href: str | None = None,
    footer_note: str | None = None,
) -> str:
    p = palette_for(theme_id)
    cta_block = ""
    if cta_label and cta_href:
        cta_block = f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:40px;">
                <tr>
                  <td align="center" style="padding:8px 0 32px;">
                    <a href="{cta_href}" style="display:inline-block;min-width:220px;padding:18px 36px;background:{p['primary']};color:#ffffff;text-decoration:none;border-radius:999px;font-size:16px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">
                      {cta_label}
                    </a>
                  </td>
                </tr>
              </table>"""

    note = footer_note or "You received this because you have a PS Prices account."

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="dark light" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{p['bg']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{p['ink']};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{p['bg']};padding:56px 20px 72px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:{p['surface']};border:1px solid {p['border']};border-radius:28px;overflow:hidden;box-shadow:0 32px 80px rgba(0,0,0,0.42);">
          <tr>
            <td style="height:6px;background:linear-gradient(90deg,{p['accent']} 0%,{p['primary']} 55%,{p['accent']} 100%);font-size:0;line-height:0;">&nbsp;</td>
          </tr>
          <tr>
            <td style="padding:52px 44px 40px;text-align:center;background:linear-gradient(180deg,{p['surface']} 0%,{p['bg']} 100%);">
              <p style="margin:0;font-size:12px;letter-spacing:0.42em;text-transform:uppercase;color:{p['accent']};font-weight:700;">{eyebrow}</p>
              <h1 style="margin:28px 0 0;font-size:34px;line-height:1.2;font-weight:800;color:{p['ink']};">{title}</h1>
              <p style="margin:24px 0 0;font-size:18px;line-height:1.75;color:{p['muted']};max-width:380px;margin-left:auto;margin-right:auto;">{subtitle}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:12px 44px 0;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  <td style="height:1px;background:{p['border']};font-size:0;line-height:0;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td style="padding:36px 44px 48px;">
              {body_html}
              {cta_block}
            </td>
          </tr>
          <tr>
            <td style="padding:0 44px 40px;text-align:center;">
              <p style="margin:0;font-size:13px;line-height:1.8;color:{p['muted']};">
                PS Prices · PlayStation Store price intelligence
              </p>
            </td>
          </tr>
        </table>
        <p style="margin:28px 0 0;font-size:12px;line-height:1.7;color:{p['muted']};max-width:520px;">
          {note}
        </p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def price_alert_html(
    *,
    theme_id: str | None,
    game_name: str,
    current_price: str,
    original_price: str,
    discount: str,
    reason_label: str,
    previous_price: str,
    target_label: str,
    image_url: str | None,
    store_url: str,
    preview: bool = False,
) -> str:
    p = palette_for(theme_id)
    image_block = ""
    if image_url:
        image_block = f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:32px;">
                <tr>
                  <td align="center" style="padding:8px 0 24px;">
                    <img src="{image_url}" alt="" width="168" height="168" style="display:block;border-radius:22px;border:1px solid {p['border']};box-shadow:0 18px 48px rgba(0,0,0,0.35);" />
                  </td>
                </tr>
              </table>"""

    body = f"""
              {image_block}
              <p style="margin:0;font-size:24px;font-weight:800;color:{p['ink']};line-height:1.35;text-align:center;">{game_name}</p>
              <p style="margin:28px 0 0;font-size:52px;font-weight:900;line-height:1;color:{p['accent']};letter-spacing:-0.03em;text-align:center;">{current_price}</p>
              <p style="margin:10px 0 0;font-size:20px;color:{p['muted']};text-decoration:line-through;text-align:center;">{original_price}</p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:36px;border-top:1px solid {p['border']};">
                <tr>
                  <td style="padding:18px 0 10px;font-size:13px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.16em;">Discount</td>
                  <td align="right" style="padding:18px 0 10px;font-size:18px;font-weight:700;color:{p['ink']};">{discount}</td>
                </tr>
                <tr>
                  <td style="padding:14px 0;font-size:13px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.16em;">Trigger</td>
                  <td align="right" style="padding:14px 0;font-size:18px;font-weight:700;color:{p['ink']};">{reason_label}</td>
                </tr>
                <tr>
                  <td style="padding:14px 0;font-size:13px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.16em;">Previous</td>
                  <td align="right" style="padding:14px 0;font-size:18px;color:{p['ink']};">{previous_price}</td>
                </tr>
                <tr>
                  <td style="padding:14px 0 0;font-size:13px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.16em;">Your target</td>
                  <td align="right" style="padding:14px 0 0;font-size:18px;color:{p['ink']};">{target_label}</td>
                </tr>
              </table>"""

    return _layout(
        theme_id=theme_id,
        eyebrow="PS PRICES",
        title="Price alert" if not preview else "Alert preview",
        subtitle="A game you're watching matched your alert rules." if not preview else "This is how your alerts will look in your inbox.",
        body_html=body,
        cta_label="View on PlayStation Store",
        cta_href=store_url,
        footer_note="You received this because you enabled price alerts on PS Prices.",
    )


def system_email_html(
    *,
    theme_id: str | None,
    title: str,
    message: str,
    cta_label: str,
    cta_href: str,
    kind: str = "account",
) -> str:
    p = palette_for(theme_id)
    detail = {
        "account": "This link expires soon. If you did not request it, ignore this email.",
        "reset": "For your security, this reset link expires in 2 hours.",
        "verify": "Verify once and you are set — this link expires soon.",
    }.get(kind, "This secure link expires soon.")

    body = f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:28px;">
                <tr>
                  <td align="center" style="padding:12px 0 28px;">
                    <div style="width:72px;height:72px;border-radius:20px;border:1px solid {p['border']};background:linear-gradient(180deg,{p['surface']} 0%,{p['bg']} 100%);line-height:72px;font-size:30px;text-align:center;color:{p['accent']};">◎</div>
                  </td>
                </tr>
              </table>
              <p style="margin:0;font-size:19px;line-height:1.85;color:{p['ink']};text-align:center;">{message}</p>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:32px;">
                <tr>
                  <td style="padding:22px 24px;border:1px solid {p['border']};border-radius:18px;background:{p['bg']};">
                    <p style="margin:0;font-size:14px;line-height:1.75;color:{p['muted']};text-align:center;">{detail}</p>
                  </td>
                </tr>
              </table>"""
    return _layout(
        theme_id=theme_id,
        eyebrow="PS PRICES",
        title=title,
        subtitle="Secure account message from PS Prices.",
        body_html=body,
        cta_label=cta_label,
        cta_href=cta_href,
    )
