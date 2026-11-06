# Ubuntu/Linux Edition

The Linux edition is maintained on the `linux` branch and is released independently from the Windows edition.

## Supported build targets

The Linux CI packaging matrix targets:

- Ubuntu 22.04 LTS and 24.04 LTS
- x86_64 and ARM64
- Python 3.11 at build/test time

Each package is a standalone PyInstaller one-folder distribution. Build artifacts are generated on a matching Linux runner; a Windows EXE is not usable on Linux.

## Run the desktop dashboard

1. Download the artifact matching the Ubuntu version and CPU architecture.
2. Extract the `.tar.gz` archive to a directory owned by your user.
3. Run:

   ```bash
   ./NetworkSimulator/NetworkSimulator
   ```

4. The dashboard listens on `127.0.0.1:5050` and opens in the default browser.

If the browser does not open automatically, visit `http://127.0.0.1:5050`.

## Run in headless server mode

Start the dashboard without opening a browser:

```bash
./NetworkSimulator/NetworkSimulator --mode server
```

The server mode uses Waitress and remains bound to `127.0.0.1`. It is intentionally not exposed directly to the LAN.

To access it remotely, create an SSH tunnel from the client machine:

```bash
ssh -L 8666:127.0.0.1:5050 <user>@<ubuntu-server>
```

Then open `http://127.0.0.1:8666` on the client machine. Keep SSH access protected by your organization's access policy.

Use `--port 5051` to select another local dashboard port in either mode.

## Profile and configuration storage

On Linux, user data is stored in:

```
$XDG_DATA_HOME/network-simulator/
```

If `XDG_DATA_HOME` is not set, the default is:

```
~/.local/share/network-simulator/
```

This keeps writable profiles outside the application installation directory, allowing the package to be extracted under a read-only or administrator-managed location. The Linux edition retains the Windows profile JSON schema and import/export behaviour.

## Current operational behaviour

- Saved profiles and enabled/disabled states are restored when the dashboard starts.
- Profiles do not start automatically. Start individual profiles or use **Start All** from the dashboard, matching the existing Windows behaviour.
- TCP and TLS passthrough remain byte-forwarding modes; TLS is not terminated.
- The management API is localhost-only. Use an SSH tunnel for remote server administration.

## Development and tests

Install Linux dependencies in a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-linux.txt
python -m unittest discover -s tests -v
```

Build the standalone folder locally:

```bash
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onedir --console \
  --name NetworkSimulator \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --add-data "config:config" \
  app.py
```

Linux packages must be built on Linux for the target CPU architecture. Do not copy the Windows EXE into a Linux package.
