"""Function-style repos for the operational state DB.

Each repo module exposes plain functions (no service or factory
classes) that take a SQLAlchemy ``Session`` and the kwargs they need.
The route layer maps repo exceptions to HTTP status codes.
"""
