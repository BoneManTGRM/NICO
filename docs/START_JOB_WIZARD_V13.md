# Start Job Wizard v13

This update adds `/start-job`, a real guided start page that turns NICO from disconnected sections into a job-first workflow.

## What it does

- Lets the user choose a job type.
- Captures repository, client, project, authorized-by, and authorization scope.
- Saves the job locally in browser storage.
- Shows the correct next steps for the selected job type.
- Links to the command center, Scanner to Express workflow, and guided workflow page.

## Job types

- Quick repo health check.
- Client Express assessment.
- Repair failed check.
- Retainer project.

## Why this matters

The command center is powerful but dense. The wizard gives non-technical users a safer starting point before they run Express, Scanner Worker, Repair Intelligence, Reports, or Retainer workflows.

## Safety rule

Saving a job does not run a scanner, change code, create a PR, merge code, or deploy. It only records the local scope and helps the user choose the correct next workflow.
