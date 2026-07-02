"""Click-to-run launcher for the Agent Assurance Harness.

Run this file directly (PyCharm green arrow, or `python main.py`) — it uses absolute imports
so it works as a plain script. The package entry point is `aah/cli.py`; the equivalent
command-line form is `python -m aah.cli`.

Pass CLI flags as program arguments, e.g. `--loop 5`, `--adversarial`, `--runs 2`.
In PyCharm: Run > Edit Configurations > Parameters.
"""

from aah.cli import main

if __name__ == "__main__":
    main()
