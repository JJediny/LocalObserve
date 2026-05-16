#!/bin/bash

# Configuration
OO_URL=${OO_URL:-"http://localhost:5080"}
OO_ORG=${OO_ORG:-"default"}
OO_USER=${OO_USER:-"root@example.com"}
OO_PASS=${OO_PASS:-"Complexpass#123"}
DASHBOARD_DIR=${DASHBOARD_DIR:-"./dashboards/openobserve"}

mkdir -p "$DASHBOARD_DIR"

function export_dashboards() {
    echo "Exporting dashboards from $OO_URL..."
    # Get all dashboards
    DASHBOARDS_JSON=$(curl -s -u "$OO_USER:$OO_PASS" "$OO_URL/api/$OO_ORG/dashboards")
    
    # Extract IDs and save each one
    # Note: This uses jq to iterate over the dashboards list
    echo "$DASHBOARDS_JSON" | jq -c '.dashboards[]' | while read -r dashboard; do
        TITLE=$(echo "$dashboard" | jq -r '.title' | tr ' ' '_' | tr '/' '-')
        ID=$(echo "$dashboard" | jq -r '.dashboard_id')
        echo "Saving dashboard: $TITLE ($ID)"
        echo "$dashboard" > "$DASHBOARD_DIR/$TITLE.json"
    done
    echo "Done. Dashboards saved to $DASHBOARD_DIR"
}

function import_dashboards() {
    echo "Importing dashboards to $OO_URL..."
    
    # Get existing dashboards to check for updates
    EXISTING=$(curl -s -u "$OO_USER:$OO_PASS" "$OO_URL/api/$OO_ORG/dashboards")

    for file in "$DASHBOARD_DIR"/*.json; do
        [ -e "$file" ] || continue
        echo "Processing $file..."
        
        DATA=$(cat "$file")
        TITLE=$(echo "$DATA" | jq -r '.title // .v5.title // .v2.title // "Untitled"')
        
        # Extract the actual dashboard content (v2 or v5 or whatever is present)
        CONTENT=$(echo "$DATA" | jq -c '.v5 // .v2 // .v1 // .')
        
        # Check if it exists
        EXISTING_ID=$(echo "$EXISTING" | jq -r ".dashboards[] | select(.title == \"$TITLE\") | .dashboard_id" | head -n 1)

        if [ -n "$EXISTING_ID" ] && [ "$EXISTING_ID" != "null" ]; then
            echo "Updating existing dashboard: $TITLE ($EXISTING_ID)"
            curl -s -u "$OO_USER:$OO_PASS" \
                 -X PUT \
                 -H "Content-Type: application/json" \
                 -d "$CONTENT" \
                 "$OO_URL/api/$OO_ORG/dashboards/$EXISTING_ID" > /dev/null
        else
            echo "Creating new dashboard: $TITLE"
            curl -s -u "$OO_USER:$OO_PASS" \
                 -X POST \
                 -H "Content-Type: application/json" \
                 -d "$CONTENT" \
                 "$OO_URL/api/$OO_ORG/dashboards" > /dev/null
        fi
    done
    echo "Done."
}

case "$1" in
    export)
        export_dashboards
        ;;
    import)
        import_dashboards
        ;;
    *)
        echo "Usage: $0 {export|import}"
        exit 1
        ;;
esac
