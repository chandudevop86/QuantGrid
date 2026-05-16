#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP_SERVER="${BOOTSTRAP_SERVER:-localhost:9092}"
TOPICS=("orders" "execution-reports" "updates")

for topic in "${TOPICS[@]}"; do
  kafka-topics \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 1 \
    --replication-factor 1
done

echo "Kafka topics ready on $BOOTSTRAP_SERVER"
