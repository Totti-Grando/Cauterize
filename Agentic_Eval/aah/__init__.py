"""Agent Quality & Security Assurance Harness (spec v3).

Two layers, one-way dependency B -> A:
- ``aah.layer_a`` -- Evaluator Core (standalone).
- ``aah.layer_b`` -- Optimization Loop (optional; imports A only).
"""

__version__ = "0.1.0"
