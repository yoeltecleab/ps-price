"""Application modules for the PS Price backend.

How the pieces connect (big picture)
====================================

When someone opens the website, the **frontend** sends HTTP requests to
``main.py``. Each route in ``main.py`` is a thin handler: it checks who
the user is (``deps.py``), then calls either:

  - ``PriceService`` (``service.py``) for game/price/watch logic, or
  - ``AuthService`` (``auth_service.py``) for accounts and login.

Both services use **repositories** to read/write PostgreSQL via SQLAlchemy:

  - ``Repository`` — games, catalog, watches, notifications
  - ``AuthRepository`` — users, sessions, passkeys

External data comes from ``ps_store.py`` and ``ps_graphql.py``, which
download information from Sony's PlayStation Store.

Background jobs run in ``scheduler.py`` (periodic price checks and catalog sync).

Supporting modules (read these when you see them imported):

  - ``config.py``      — all ``PS_PRICE_*`` environment settings
  - ``schemas.py``     — shapes of JSON request/response bodies
  - ``domain.py``      — small immutable data classes (ProductSnapshot)
  - ``money.py``       — convert "$19.99" ↔ 1999 cents
  - ``notifier.py``    — send email alerts via SMTP
  - ``passwords.py``   — hash passwords safely (never store plain text)
  - ``security.py``    — redirect safety, admin checks
  - ``rate_limit.py``  — slow down abusive requests
"""
