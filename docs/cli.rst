Command Line Interface
======================

Overview
--------

forBIDS provides a command-line interface for protocol compliance validation with two main commands: ``init`` and ``validate``.

Usage
-----

.. code-block:: bash

   forbids <command> <bids_path> [options]

Commands
--------

init
~~~~

Initialize a validation schema for a BIDS dataset.

.. code-block:: bash

   forbids init <bids_path> [options]

Creates a ``.forbids`` folder containing a BIDS-like structure with JSON schemas for each series in the dataset.

Options:

- ``--session-specific``: Create different schemas for each session (use when study design is not repeated measures)
- ``--scanner-specific``: Allow schemas to be scanner instance specific
- ``--version-specific``: Allow schemas to be specific to scanner software version

Example:

.. code-block:: bash

   forbids init /path/to/bids/dataset --scanner-specific

validate
~~~~~~~~

Validate a subject/session against the schema.

.. code-block:: bash

   forbids validate <bids_path> [options]

Validates all files in a subject/session against the schema found in ``.forbids``, checking for:

- Missing sequences (configured as required)
- Extra/unwanted BIDS files
- Sequence parameters matching expected values

Options:

- ``--participant-label <label> [<label> ...]``: Subject(s) to validate (default: all)
- ``--session-label <label> [<label> ...]``: Session(s) to validate (default: all)

Example:

.. code-block:: bash

   forbids validate /path/to/bids/dataset --participant-label sub-01 sub-02

Environment Variables
---------------------

- ``DEBUG``: Set to any value to enable debug-level logging

.. code-block:: bash

   DEBUG=1 forbids validate /path/to/bids/dataset

Exit Codes
----------

- ``0``: Success
- ``1``: Validation failed or error occurred
