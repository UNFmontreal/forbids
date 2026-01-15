# forBIDS API Reference

This document provides detailed API documentation for the forBIDS Python package.

## Modules

- [schema](#schema-module) - Schema generation and validation
- [init](#init-module) - Schema initialization from BIDS datasets
- [validation](#validation-module) - Protocol compliance validation
- [cli.run](#cli-module) - Command-line interface

---

## Schema Module

**Module**: `forbids.schema`

Provides functionality to generate JSON schemas from exemplar BIDS data and validate datasets against protocol compliance schemas.

### Functions

#### `tagpreset2type(tag, tag_preset, value)`

Convert tag presets from config files into typed constraints.

**Parameters:**
- `tag` (str): The name of the metadata tag
- `tag_preset` (str): The constraint expression
  - `"="` : Exact equality (Literal type)
  - `"*"` : Any value of the same type (wildcard)
  - `"~=X"` : Tolerance constraint (value ± X)
  - `"rPATTERN"` : Regex pattern matching
- `value` (Any): The exemplar value used to determine type

**Returns:** Python type with apischema validation constraints

**Raises:** `RuntimeError` if tag_preset is not supported

**Example:**
```python
from forbids.schema import tagpreset2type

# Exact match
typ = tagpreset2type("EchoTime", "=", 0.03)

# Tolerance
typ = tagpreset2type("FlipAngle", "~=1.0", 90.0)

# Regex
typ = tagpreset2type("SequenceName", "r^ep2d.*", "ep2d_bold")
```

#### `struct2schemaprops(sidecar, config_props, schema_path)`

Generate dataclass field definitions from exemplar data and config.

**Parameters:**
- `sidecar` (dict): Dictionary with exemplar values
- `config_props` (dict): Dictionary with validation presets
- `schema_path` (str): Schema name prefix for uniqueness

**Yields:** Tuples of (field_name, field_type)

#### `sidecar2schema(sidecar, config_props, subschema_name)`

Generate a dataclass schema from an exemplar sidecar and configuration.

**Parameters:**
- `sidecar` (dict): Exemplar sidecar dictionary
- `config_props` (dict): Schema properties configuration
- `subschema_name` (str): Name for the generated dataclass

**Returns:** Dynamically created dataclass type

#### `get_validator(sidecar_schema)`

Create an OpenAPI 3.1 validator for the given schema.

**Parameters:**
- `sidecar_schema` (dict): JSON schema dictionary

**Returns:** OAS31Validator instance

**Raises:** `jsonschema.exceptions.SchemaError` if schema is invalid

#### `sidecars2unionschema(sidecars_groups, bids_layout, config_props, series_entities, factor_entities=("subject", "run"))`

Generate a union schema from grouped sidecars across different scanners.

**Parameters:**
- `sidecars_groups` (dict): Mapping of instrument tag tuples to sidecar lists
- `bids_layout` (bids.BIDSLayout): BIDS layout object
- `config_props` (dict): Schema properties configuration
- `series_entities` (dict): BIDS entities identifying the series
- `factor_entities` (tuple): Entities to factor out

**Returns:** Annotated union type with discriminator

**Raises:** `ValidationError` if sidecars don't match schema

#### `get_instrument_key(sidecar_data, instrument_tags)`

Compose an instrument key from metadata and tag list.

**Parameters:**
- `sidecar_data` (dict): Metadata dictionary
- `instrument_tags` (list): Tag names to include in key

**Returns:** Hyphen-separated string key (e.g., "Siemens-Prisma")

**Example:**
```python
from forbids.schema import get_instrument_key

data = {
    "Manufacturer": "Siemens",
    "ManufacturersModelName": "Prisma"
}
key = get_instrument_key(data, ["Manufacturer", "ManufacturersModelName"])
# Returns: "Siemens-Prisma"
```

#### `prepare_metadata(sidecar, instrument_tags)`

Prepare sidecar metadata for JSON schema validation.

**Parameters:**
- `sidecar` (bids.layout.BIDSJSONFile): BIDS JSON sidecar file
- `instrument_tags` (list): Tag names for instrument identification

**Returns:** Dictionary with processed metadata

---

## Init Module

**Module**: `forbids.init`

Handles initialization of forBIDS schemas from exemplar BIDS datasets.

### Functions

#### `get_config(datatype)`

Load configuration for a specific BIDS datatype.

**Parameters:**
- `datatype` (str): BIDS datatype (e.g., "anat", "func", "dwi", "fmap")

**Returns:** Dictionary with instrument and properties configuration

**Raises:** `ValueError` if datatype is not recognized

**Example:**
```python
from forbids.init import get_config

config = get_config("anat")
print(config["properties"]["EchoTime"])  # "="
```

#### `initialize(bids_layout, uniform_instruments=True, uniform_sessions=False, version_specific=False, instrument_grouping_tags=())`

Initialize forBIDS schemas from a BIDS dataset.

**Parameters:**
- `bids_layout` (bids.BIDSLayout): PyBIDS BIDSLayout object
- `uniform_instruments` (bool): Create schemas across all instruments
- `uniform_sessions` (bool): Create schemas across all sessions
- `version_specific` (bool): Allow version-specific schemas
- `instrument_grouping_tags` (tuple): Additional custom grouping tags

**Returns:** True if all schemas generated successfully, False otherwise

**Example:**
```python
import bids
from forbids.init import initialize

layout = bids.BIDSLayout("/data/my_bids_dataset")
success = initialize(layout, uniform_instruments=True)
```

#### `generate_series_model(bids_layout, uniform_instruments=True, uniform_sessions=True, version_specific=False, **series_entities)`

Generate a schema model for a specific BIDS series.

**Parameters:**
- `bids_layout` (bids.BIDSLayout): PyBIDS BIDSLayout object
- `uniform_instruments` (bool): Group across all instruments
- `uniform_sessions` (bool): Group across all sessions
- `version_specific` (bool): Include software version in grouping
- `**series_entities`: BIDS entities identifying the series

**Returns:** True if schema generated successfully, False otherwise

---

## Validation Module

**Module**: `forbids.validation`

Provides functionality to validate BIDS datasets against protocol compliance schemas.

### Classes

#### `BIDSJSONError(ValidationError)`

Exception raised for BIDS metadata validation errors.

Raised when metadata in a BIDS JSON sidecar file does not match expected schema constraints.

**Inherits:** `jsonschema.exceptions.ValidationError`

#### `BIDSFileError(ValidationError)`

Exception raised for BIDS file structure errors.

Raised for issues with file presence/absence (missing required files, unexpected files, wrong number of runs).

**Inherits:** `jsonschema.exceptions.ValidationError`

### Functions

#### `validate(bids_layout, **entities)`

Validate BIDS data against protocol compliance schemas.

**Parameters:**
- `bids_layout` (bids.BIDSLayout): BIDS layout object for dataset
- `**entities`: BIDS entities to validate (e.g., subject="01", session="baseline")

**Yields:** BIDSJSONError or BIDSFileError instances for each validation failure

**Example:**
```python
import bids
from forbids.validation import validate

layout = bids.BIDSLayout("/data/my_bids_dataset")
errors = list(validate(layout, subject="01", session="baseline"))

if errors:
    print(f"Found {len(errors)} validation errors")
    for error in errors:
        print(f"  - {error}")
```

#### `add_path_note_to_error(validator, sidecar_data, filepath)`

Add file path information to validation errors.

**Parameters:**
- `validator`: JSON schema validator instance
- `sidecar_data` (dict): Metadata dictionary being validated
- `filepath` (str): Path to file being validated

**Yields:** ValidationError instances with file path in __notes__

#### `process_validation(layout, subject, session)`

Run validation and format errors for user-friendly output.

**Parameters:**
- `layout` (bids.BIDSLayout): BIDS layout object
- `subject`: Subject ID(s) to validate (string or list)
- `session`: Session ID(s) to validate (string, list, or None)

**Returns:** True if validation passed, False otherwise

**Example:**
```python
import bids
from forbids.validation import process_validation

layout = bids.BIDSLayout("/data/my_bids_dataset")
success = process_validation(layout, subject="01", session=None)

if success:
    print("Dataset is compliant!")
else:
    print("Validation failed - check logs for details")
```

---

## CLI Module

**Module**: `forbids.cli.run`

Command-line interface for forBIDS.

### Functions

#### `parse_args()`

Parse command-line arguments for forBIDS.

**Returns:** argparse.Namespace with parsed arguments

#### `main()`

Main entry point for the forBIDS CLI.

Parses arguments and executes either init or validate command. Exits with code 0 on success, 1 on failure.

---

## Constants

### `forbids.schema.FORBIDS_SCHEMA_FOLDER`
Default folder name for storing schemas: `".forbids"`

### `forbids.schema.ALT_ENTITIES`
Entities that differentiate files from the same series: `["reconstruction", "acquisition"]`

---

## Usage Examples

### Complete Workflow Example

```python
import bids
from forbids.init import initialize
from forbids.validation import process_validation

# Step 1: Initialize schemas from reference dataset
reference_layout = bids.BIDSLayout("/data/reference_dataset")
success = initialize(
    reference_layout,
    uniform_instruments=True,
    uniform_sessions=True
)

if not success:
    print("Schema initialization failed!")
    exit(1)

# Step 2: Validate new data
new_layout = bids.BIDSLayout("/data/new_dataset")
for subject in new_layout.get_subjects():
    print(f"Validating subject {subject}...")
    success = process_validation(
        new_layout,
        subject=subject,
        session=None
    )
    if not success:
        print(f"  Subject {subject} failed validation")
```

### Custom Validation Script

```python
import bids
from forbids.validation import validate, BIDSFileError, BIDSJSONError

layout = bids.BIDSLayout("/data/my_dataset")

# Validate and categorize errors
file_errors = []
metadata_errors = []

for error in validate(layout, subject="01"):
    if isinstance(error, BIDSFileError):
        file_errors.append(error)
    elif isinstance(error, BIDSJSONError):
        metadata_errors.append(error)

print(f"File structure errors: {len(file_errors)}")
print(f"Metadata errors: {len(metadata_errors)}")

# Report details
for error in file_errors:
    print(f"  FILE: {error}")

for error in metadata_errors:
    print(f"  META: {error}")
```
