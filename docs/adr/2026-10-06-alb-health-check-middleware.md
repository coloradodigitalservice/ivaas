---
status: "proposed"
deciders:
---

# Use middleware for ALB health checks

## Context and Problem Statement

IVaaS is designed to be deployed as a containerized application. In AWS
environments where IVaaS is deployed to Amazon Elastic Container Service (ECS)
behind an Application Load Balancer (ALB), ALB health checks send the target's
IP address as the Host header. If the application's `ALLOWED_HOSTS` configuration
does not include the task's IP address, the application rejects the ALB
health check, leaving the application in a nonfunctional state.

How will IVaaS handle ALB health checks for ECS deployments?

## Decision Outcome

Use middleware to handle ALB health checks

### Consequences

* Requires a decision around which path to use for the ALB health check and
  whether to retain the existing health check

## Options Considered

### Use middleware to handle ALB health checks

Create a custom middleware, placed first (or very early) in the middleware
chain, to respond to ALB health checks before other middleware validate the host
header against `ALLOWED_HOSTS`.

* `+` Nothing is added to `ALLOWED_HOSTS`
* `+` No dependence on network setup
* `+` No startup step that can fail
* `-` It is a shallow check. It confirms that Django is serving requests, but
  not that URL routing or views work.
* `-` It is custom code to maintain
* `-` The health check path is reachable with any host header

### Get task IP from ECS metadata endpoint

At task startup, retrieve the task IP from the ECS metadata endpoint and add it
to `ALLOWED_HOSTS`.

* `+` Health checks go through normal request path
* `+` No custom middleware
* `-` Only works with `awsvpc` networking
* `-` The IP becomes a valid Host for every path, not just the health check
* `-` Adds a network call at startup

### Get task IP with python socket library

At task startup, retrieve the task IP using functions within python's socket
library and add it to `ALLOWED_HOSTS`.

* `+` Health checks go through normal request path
* `+` No AWS dependency
* `-` The IP becomes a valid Host for every path, not just the health check
* `-` Function results may vary more depending on image and DNS setup
