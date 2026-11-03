FROM ubuntu:24.04
ARG SQUID_VERSION=6.14-0ubuntu0.24.04.5
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      squid=${SQUID_VERSION} python3 iptables ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY deploy/firewall_policy.py /opt/brz/firewall_policy.py
USER 13:13
WORKDIR /tmp
CMD ["/usr/sbin/squid", "-N", "-f", "/tmp/squid.conf"]
