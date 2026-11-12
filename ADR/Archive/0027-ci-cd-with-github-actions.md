# ADR 0027: CI/CD with GitHub Actions

- **Date:** 30.10.2026
- **Status:** Accepted
- **Source:** project summary and diagrams from 30.10 (`diagrams/30.10_B_*`)
- **Use cases:** –

## Context
The course wants automated build and deploy.

## Decision
GitHub Actions run the tests, build the images and push them to Artifact Registry.

## Alternatives
Cloud Build.

## Consequences
Free for our repo, the pipeline is next to the code.
