#!/bin/bash

# Configuration
OO_URL=${OO_URL:-"http://localhost:5080"}
OO_ORG=${OO_ORG:-"default"}
OO_USER=${OO_USER:-"root@example.com"}
OO_PASS=${OO_PASS:-"Complexpass#123"}

echo "Deleting all existing dashboards from OpenObserve..."

# Get all dashboard IDs
DASHBOARDS_JSON=$(curl -s -u "$OO_USER:$OO_PASS" "$OO_URL/api/$OO_ORG/dashboards")
IDS=$(echo "$DASHBOARDS_JSON" | jq -r '.dashboards[].dashboard_id')

for id in $IDS; do
    echo "Deleting dashboard $id..."
    curl -s -u "$OO_USER:$OO_PASS" -X DELETE "$OO_URL/api/$OO_ORG/dashboards/$id" > /dev/null
done

echo "Cleanup complete."
