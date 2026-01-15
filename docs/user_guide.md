# forBIDS User Guide

## Table of Contents
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
  - [Initializing Schemas](#initializing-schemas)
  - [Validating Data](#validating-data)
- [Advanced Usage](#advanced-usage)
- [Troubleshooting](#troubleshooting)

## Installation

### Requirements
- Python 3.11 or higher
- A BIDS-formatted dataset

### Install from PyPI
```bash
pip install forbids
```

### Install from Source
```bash
git clone https://github.com/UNFMontreal/forbids.git
cd forbids
pip install -e .
```

## Quick Start

### 1. Initialize Schemas from Your Dataset

First, generate protocol compliance schemas from an existing BIDS dataset that represents your expected protocol:

```bash
forbids init /path/to/reference/bids/dataset
```

This creates a `.forbids` folder in your dataset containing JSON schemas for each acquisition type.

### 2. Validate New Data

Validate newly acquired data against the generated schemas:

```bash
forbids validate /path/to/bids/dataset --participant-label 01
```

## Configuration

forBIDS uses configuration files located in `src/forbids/config/` to define validation rules for different modalities:

### MRI Tags Configuration

The `mri_tags.json` file defines:

- **Instrument tags**: Used to group data by scanner characteristics
  - `uid_tags`: Unique identifier tags (e.g., DeviceSerialNumber)
  - `grouping_tags`: Tags for grouping across scanners (e.g., Manufacturer, ManufacturersModelName)
  - `version_tags`: Software version tags

- **Properties**: Validation rules for metadata fields
  - `=` : Exact match required
  - `*` : Any value allowed (wildcard)
  - `~=X` : Tolerance of ±X allowed
  - `rPATTERN` : Must match regex pattern

Example:
```json
{
  "properties": {
    "EchoTime": "=",           // Must match exactly
    "Manufacturer": "*",        // Any value allowed
    "ImagingFrequency": "~=.5", // Within ±0.5
    "SequenceName": "r^ep2d.*"  // Must match regex
  }
}
```

## Usage

### Initializing Schemas

The `init` command analyzes your reference dataset and generates validation schemas.

#### Basic Initialization
```bash
forbids init /path/to/bids/dataset
```

#### Session-Specific Schemas
For longitudinal studies where protocols differ between sessions:
```bash
forbids init /path/to/bids/dataset --session-specific
```

#### Scanner-Specific Schemas
To allow different protocols for different scanner instances:
```bash
forbids init /path/to/bids/dataset --scanner-specific
```

#### Version-Specific Schemas
To account for software version differences:
```bash
forbids init /path/to/bids/dataset --version-specific
```

#### Combined Options
```bash
forbids init /path/to/bids/dataset --session-specific --version-specific
```

### Validating Data

The `validate` command checks if your data complies with the generated schemas.

#### Validate a Single Subject
```bash
forbids validate /path/to/bids/dataset --participant-label 01
```

#### Validate Multiple Subjects
```bash
forbids validate /path/to/bids/dataset --participant-label 01 02 03
```

#### Validate Specific Session
```bash
forbids validate /path/to/bids/dataset --participant-label 01 --session-label baseline
```

#### Validate All Subjects
```bash
forbids validate /path/to/bids/dataset
```

## Advanced Usage

### Multi-Site Studies

forBIDS is designed for multi-site and multi-vendor studies. By default, it groups data by manufacturer and model, allowing the same protocol to be validated across different scanner instances.

**Example workflow:**
1. Collect reference data from all sites
2. Initialize with default settings (uniform across instruments):
   ```bash
   forbids init /path/to/reference/dataset
   ```
3. Validate new data from any site:
   ```bash
   forbids validate /path/to/new/dataset --participant-label 01
   ```

### Custom Validation Workflows

#### Continuous Integration
Integrate forBIDS into your data pipeline:

```bash
#!/bin/bash
# validate_new_session.sh

SUBJECT=$1
SESSION=$2
BIDS_DIR=/data/bids

forbids validate $BIDS_DIR --participant-label $SUBJECT --session-label $SESSION

if [ $? -eq 0 ]; then
    echo "Validation passed! Merging into main dataset..."
    # Your merge logic here
else
    echo "Validation failed! Please review errors."
    exit 1
fi
```

#### Pre-Commit Hook
Validate data before committing to version control:

```bash
#!/bin/bash
# .git/hooks/pre-commit

forbids validate /path/to/bids/dataset
exit $?
```

### Understanding Schema Files

Schema files are stored in `.forbids/` with the same structure as your BIDS dataset:

```
.forbids/
├── sub-ref/
│   ├── anat/
│   │   ├── sub-ref_T1w.json
│   │   └── sub-ref_T2w.json
│   └── func/
│       └── sub-ref_task-rest_bold.json
```

Each schema file contains:
- JSON schema for metadata validation
- BIDS-specific constraints:
  - `instrument_tags`: Tags used for grouping
  - `optional`: Whether the file is optional
  - `required_for_instruments`: Which scanner configs require this file
  - `min_runs` / `max_runs`: Expected number of runs

## Troubleshooting

### Common Issues

#### Issue: "unknown data type" error
**Cause**: Unsupported BIDS datatype
**Solution**: Currently supported datatypes are: anat, func, dwi, swi, fmap, eeg, meg

#### Issue: Validation fails with "non-existing schema for instrument"
**Cause**: Data from a scanner configuration not present in reference dataset
**Solution**: Either:
- Add reference data from this scanner to your reference dataset and re-run `init`
- Use `--scanner-specific` flag during initialization if this is expected

#### Issue: Too many false positives for numerical parameters
**Cause**: Exact matching (`=`) is too strict for floating-point values
**Solution**: Edit the config file to use tolerance matching:
```json
"EchoTime": "~=0.001"  // Instead of "="
```

#### Issue: Schema generation fails
**Cause**: Inconsistent metadata across exemplar files
**Solution**:
1. Check logs for specific metadata mismatches
2. Ensure reference dataset has consistent protocol
3. Use `--version-specific` or `--scanner-specific` if variations are expected

### Debug Mode

Enable debug logging for detailed information:

```bash
export DEBUG=1
forbids validate /path/to/bids/dataset --participant-label 01
```

### Getting Help

- **GitHub Issues**: https://github.com/UNFMontreal/forbids/issues
- **Documentation**: https://github.com/UNFMontreal/forbids
- **BIDS Specification**: https://bids-specification.readthedocs.io/

## Best Practices

1. **Use a clean reference dataset**: Ensure your reference dataset is fully compliant with BIDS and represents your ideal protocol

2. **Start simple**: Begin with default settings before using advanced options like `--scanner-specific`

3. **Validate incrementally**: Validate each session as it's acquired rather than waiting for the entire study

4. **Version control your schemas**: Keep `.forbids/` in version control to track protocol changes over time

5. **Document deviations**: If validation fails for a known reason (e.g., emergency protocol change), document it in your dataset README

6. **Regular updates**: If your protocol changes, regenerate schemas from updated reference data
