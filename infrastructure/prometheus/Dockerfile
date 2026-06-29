FROM prom/prometheus:v2.52.0
COPY --chown=nobody:nogroup prometheus.yml /etc/prometheus/prometheus.yml
COPY --chown=nobody:nogroup alerts.yml /etc/prometheus/alerts.yml
