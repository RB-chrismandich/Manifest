---
max_turns: 6
timeout_seconds: 180
allowed_tools: [Skill, Read]
model: sonnet
runs: 3
---
(Pasted from my cluster; you don't have the files.)

Kubernetes: Grafana loads datasources from a provisioning ConfigMap mounted at `/etc/grafana/provisioning/datasources/`:

```yaml
apiVersion: 1
datasources:
  - name: Postgres
    type: postgres
    url: pg.data.svc:5432
    user: grafana
    secureJsonData:
      password: ${PG_PASSWORD}
  - name: Prometheus
    type: prometheus
    url: http://prometheus.monitoring.svc:9090
```

`kubectl apply` succeeds, the Grafana pod is Ready, Prometheus works, but the Postgres datasource fails with `pq: password authentication failed for user "grafana"`. The Deployment's container `env:` has only `GF_SERVER_ROOT_URL`. We have a Secret `grafana-pg` with key `password`. The password in the Secret is correct. What's wrong?
