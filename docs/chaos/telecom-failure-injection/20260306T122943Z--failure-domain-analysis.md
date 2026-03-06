# Failure Domain Analysis

## Observable Fault Domains
- registration/contact visibility
- trunk/gateway dependency degradation
- channel/bridge state anomalies
- module availability and audit posture shifts
- observability surface degradation
- baseline drift indicators

## Safe Mutation Surfaces
- fixture-only simulated fault injection
- lab-gated bounded runtime scenarios
- post-fault cleanup verification via existing cleanup checks

## Unsupported/Restricted Surfaces
- unrestricted shell/CLI failure injection
- production-target destructive mutation
- irreversible service restarts/shutdowns

## Environment Assumptions
- fixture mode is available for CI
- lab mode requires explicit enablement + safe target tagging
- rollback verification is mandatory in scenario flow
