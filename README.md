# NMON Analyzer

A self-contained offline tool for inspecting [nmon](https://www.ibm.com/support/pages/nmon) performance captures and highlighting potential device health issues. The project bundles both a Flask-powered local web dashboard and a batch command line utility. Everything runs locally—no internet connection required.

## Features

- Upload multiple `.nmon` files and view an interactive dashboard summarising OK/WARN/CRIT outcomes.
- Per-file detail pages with charts for CPU, memory, eMMC, and network utilisation.
- Extensible rule engine with configurable thresholds via `config/thresholds.json`.
- CSV export and printable report views for sharing results.
- Batch CLI (`analyze_cli.py`) that produces the same artefacts as the web interface.
- Windows-friendly `start.bat` to bootstrap a virtual environment and launch the app.
- Optional single-file executable creation using PyInstaller via `build_exe.bat`.

## Getting started

### Requirements

- Python 3.11+
- (Optional) PyInstaller when building the Windows executable

### Quick start (Windows)

Double click `start.bat`. The script will create a virtual environment, install dependencies and launch the Flask server at <http://127.0.0.1:5000/>. Your default browser should open automatically; if it does not, open the address manually.

### Manual start (any OS)

```bash
python -m venv .venv
. .venv/bin/activate  # On Windows use .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Navigate to <http://127.0.0.1:5000/> and upload `.nmon` files.

### Building the CLI artefacts

```
python analyze_cli.py --in ./tests --out ./data
```

This will parse all `.nmon` files in the folder, run the rules, and persist JSON artefacts under `data/` so they appear in the web UI.

### Building the single-file executable

On Windows, run `build_exe.bat`. The script installs PyInstaller (if needed) and produces `dist\app.exe`. Launching `app.exe` starts the same local server and opens it in your default browser.

## Configuration

Tune thresholds and behaviour in `config/thresholds.json`. Settings are applied uniformly to both the web interface and CLI. Example knobs include CPU busy percentage thresholds, sustained window lengths, network/eMMC bandwidth caps, and memory leak regression parameters.

Optional friendly device/interface names can be provided via `config/device_aliases.json`.

## Project layout

```
app.py               # Flask web app entry point
analyze_cli.py       # Batch analysis CLI
config/              # Thresholds and aliases
core/                # Parser, rules, storage, utilities
static/              # Offline assets (CSS/JS)
templates/           # Jinja2 templates
tests/               # Sample data and unit tests
```

## Testing

Run the included unit tests with:

```
python -m unittest discover -s tests
```

## FAQ

**Why is a file marked OK even if it has high spikes?**

The supplied rules look for sustained usage above thresholds. Short bursts that do not persist for the configured number of minutes remain OK.

**What is the memory leak rule looking for?**

A simple linear regression is run over the configured memory series (default `mem_active_kb`). If the slope (KB per minute) exceeds the warn/crit values and the coefficient of determination (R²) is strong enough, the rule reports a WARN or CRIT.

**Where are uploaded files stored?**

Under `data/uploads/<file_id>.nmon`. Analyses are JSON files in `data/analyses/<file_id>.json`. Delete the `data/` directory to clear history.

**How do I add more rules?**

Implement a new function in `core/rules.py`, append it to the `ALL_RULES` list, and optionally add new configuration keys in `config/thresholds.json`. The web UI automatically surfaces the results.

## License

This project is released under the MIT License. See [LICENSE](LICENSE).
