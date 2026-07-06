# No-Server Assessment Mode

NICO can run local defensive assessments without exposing backend credentials to a browser session.

## GitHub repository assessment

```bash
python -m nico assess github owner/repo --authorized
```

or:

```bash
python -m nico assess github https://github.com/owner/repo --authorized
```

For private repositories, configure a local read-only GitHub credential in the `NICO_GITHUB_TOKEN` environment variable before running the command. Do not paste real credentials into documentation, screenshots, browser forms, or client reports.

The credential stays local. It is not exposed to the frontend.

## Project archive

```bash
python -m nico assess archive ./project.zip --authorized
```

Supported archive formats: `.zip`, `.tar`, `.tar.gz` and other tar-compatible formats.

NICO extracts the archive into a safe temporary directory and blocks path traversal attempts.
