#!/bin/sh
set -eu

MODE="${1:-audit}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_DIR"

run_psql_file() {
    file="$1"
    docker compose exec -T db sh -lc \
        'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$file"
}

case "$MODE" in
    audit)
        run_psql_file "$SCRIPT_DIR/tallos_storage_audit.sql"
        ;;
    vacuum)
        run_psql_file "$SCRIPT_DIR/tallos_storage_vacuum.sql"
        echo
        echo "Post-maintenance storage report:"
        run_psql_file "$SCRIPT_DIR/tallos_storage_audit.sql"
        ;;
    vacuum-full)
        if [ "${CONFIRM_TALLOS_VACUUM_FULL:-}" != "YES" ]; then
            echo "Refusing VACUUM FULL without explicit confirmation." >&2
            echo "This operation takes an ACCESS EXCLUSIVE lock on dadm_tallos_attendances." >&2
            echo "Run only in a maintenance window:" >&2
            echo "  CONFIRM_TALLOS_VACUUM_FULL=YES scripts/tallos_storage_maintenance.sh vacuum-full" >&2
            exit 2
        fi
        echo "Running VACUUM FULL. TALLOS analytics that touch the table may block until it finishes."
        docker compose exec -T db sh -lc \
            'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "VACUUM (FULL, ANALYZE, VERBOSE) public.dadm_tallos_attendances;"'
        echo
        echo "Post-VACUUM FULL storage report:"
        run_psql_file "$SCRIPT_DIR/tallos_storage_audit.sql"
        ;;
    *)
        echo "Usage: $0 {audit|vacuum|vacuum-full}" >&2
        exit 2
        ;;
esac
