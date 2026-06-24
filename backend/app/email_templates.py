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
) -> str:
    p = palette_for(theme_id)
    cta_block = ""
    if cta_label and cta_href:
        cta_block = f"""
              <p style="margin:36px 0 0;text-align:center;">
                <a href="{cta_href}" style="display:inline-block;padding:16px 32px;background:{p['primary']};color:#ffffff;text-decoration:none;border-radius:12px;font-size:16px;font-weight:600;letter-spacing:0.04em;">
                  {cta_label}
                </a>
              </p>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="dark light" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:{p['bg']};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:{p['ink']};">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{p['bg']};padding:48px 20px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:{p['surface']};border:1px solid {p['border']};border-radius:20px;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,0.35);">
          <tr>
            <td style="padding:40px 40px 32px;border-bottom:1px solid {p['border']};background:linear-gradient(180deg,{p['surface']} 0%,{p['bg']} 100%);">
              <p style="margin:0;font-size:13px;letter-spacing:0.32em;text-transform:uppercase;color:{p['accent']};font-weight:600;">{eyebrow}</p>
              <h1 style="margin:16px 0 0;font-size:32px;line-height:1.25;font-weight:700;color:{p['ink']};">{title}</h1>
              <p style="margin:16px 0 0;font-size:18px;line-height:1.65;color:{p['muted']};">{subtitle}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:36px 40px 44px;">
              {body_html}
              {cta_block}
            </td>
          </tr>
        </table>
        <p style="margin:24px 0 0;font-size:14px;line-height:1.6;color:{p['muted']};max-width:600px;">
          PS Prices · PlayStation Store price intelligence<br />
          <span style="font-size:12px;">You received this because you enabled alerts on psprices.</span>
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
    image_cell = ""
    if image_url:
        image_cell = f"""
                <td width="104" style="padding-right:20px;vertical-align:top;">
                  <img src="{image_url}" alt="" width="104" height="104" style="display:block;border-radius:14px;border:1px solid {p['border']};" />
                </td>"""

    body = f"""
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
                <tr>
                  {image_cell}
                  <td style="vertical-align:top;">
                    <p style="margin:0;font-size:22px;font-weight:700;color:{p['ink']};line-height:1.3;">{game_name}</p>
                    <p style="margin:20px 0 0;font-size:44px;font-weight:800;line-height:1;color:{p['accent']};letter-spacing:-0.02em;">{current_price}</p>
                    <p style="margin:8px 0 0;font-size:18px;color:{p['muted']};text-decoration:line-through;">{original_price}</p>
                  </td>
                </tr>
              </table>
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:32px;border-top:1px solid {p['border']};">
                <tr>
                  <td style="padding:16px 0;font-size:15px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.12em;">Discount</td>
                  <td align="right" style="padding:16px 0;font-size:17px;font-weight:600;color:{p['ink']};">{discount}</td>
                </tr>
                <tr>
                  <td style="padding:16px 0;font-size:15px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.12em;">Trigger</td>
                  <td align="right" style="padding:16px 0;font-size:17px;font-weight:600;color:{p['ink']};">{reason_label}</td>
                </tr>
                <tr>
                  <td style="padding:16px 0;font-size:15px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.12em;">Previous</td>
                  <td align="right" style="padding:16px 0;font-size:17px;color:{p['ink']};">{previous_price}</td>
                </tr>
                <tr>
                  <td style="padding:16px 0;font-size:15px;color:{p['muted']};text-transform:uppercase;letter-spacing:0.12em;">Your target</td>
                  <td align="right" style="padding:16px 0;font-size:17px;color:{p['ink']};">{target_label}</td>
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
    )


def system_email_html(
    *,
    theme_id: str | None,
    title: str,
    message: str,
    cta_label: str,
    cta_href: str,
) -> str:
    p = palette_for(theme_id)
    body = f"""
              <p style="margin:0;font-size:18px;line-height:1.75;color:{p['ink']};">{message}</p>"""
    return _layout(
        theme_id=theme_id,
        eyebrow="PS PRICES",
        title=title,
        subtitle="Secure account message — link expires soon.",
        body_html=body,
        cta_label=cta_label,
        cta_href=cta_href,
    )
