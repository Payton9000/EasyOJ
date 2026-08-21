# Automated Contest Flow Design

## Goal

Demonstrate an end-to-end contest where an administrator creates the contest and five
independent users submit concurrently, without stressing or contaminating the live site.

## Flow

A bounded Windows script creates an isolated temporary `BASE_DIR` and SQLite database,
starts EasyOJ on loopback with at most two judge workers, bootstraps one temporary admin,
and drives real HTTP forms with separate cookie jars. The admin creates a contest, attaches
a known problem, and admits five users. The users log in, open the contest workspace, and
submit deterministic Python solutions concurrently.

The script polls every submission to a terminal result, opens the ranklist, checks contest
isolation and participant visibility, and writes JSON plus Markdown reports. Hard limits
are five users, ten submissions, two workers, 120 seconds, and loopback-only networking.

## Visible Demonstration

Normal mode stops and cleans up process resources after reporting. `--keep-open` keeps the
isolated server alive and prints the final ranklist URL so it can be inspected in the
in-app browser. The run directory and generated credentials are marked temporary; no live
administrator password is read or changed.

## Failure Handling

Every step records timing and evidence. A timeout terminates the bounded flow, stops judge
workers and the HTTP server, and preserves the report and isolated database for diagnosis.
