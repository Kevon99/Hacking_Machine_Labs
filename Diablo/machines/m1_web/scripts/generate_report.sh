#!/bin/sh

name="monthly"
format="csv"

while [ $# -gt 0 ]; do
    case "$1" in
        --name)
            name="$2"
            shift 2
            ;;
        --format)
            format="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

mkdir -p /tmp/reports
output="/tmp/reports/${name}.${format}"

echo "report_id,created_at,status" > "$output"
echo "1,$(date -Iseconds),generated" >> "$output"

echo "Reporte generado en ${output}"
