# Sourced by bash through BASH_ENV; the original repository scripts are unchanged.
# Pin each original validate.sh child to one of its eight allocated physical cores.
if [[ ${BASH_EXECUTION_STRING:-} == 'run "$@"' && ${OUT:-} == "${MINLP_OUTPUT:-}/validation" ]]; then
    read -r -a guard_cpus <<< "$CPUS"
    while :; do
        for guard_cpu in "${guard_cpus[@]:0:8}"; do
            exec 9>>"$MINLP_GUARD_DIR/core_$guard_cpu.lock"
            if flock -n 9; then
                taskset -pc "$guard_cpu" "$$" >/dev/null || exit 89
                printf '%s %s %s\n' "$$" "$guard_cpu" "$*" >> "$MINLP_GUARD_DIR/validation_affinity.txt"
                break 2
            fi
        done
        sleep 0.1
    done
    # The existing validate.sh retries a network-session failure; the user's instruction forbids retries.
    trap 'if (( ${attempt:-1} > 1 )); then echo "GUARD: automatic retry prevented; original failure preserved" >&2; exit 87; fi' DEBUG
    set -T
else
    __minlp_guard() {
        local guard_command=$1
        [[ ${0##*/} == run_dantzig.sh ]] || return 0
        (( BASH_SUBSHELL == 0 )) || return 0
        case "$guard_command" in
            'line=$(cat "$OUTPUT/preflight/'*)
                "$MINLP_GUARD_PYTHON" "$MINLP_GUARD_SCRIPT" preflight "$solver" || exit 86
                ;;
            'log "validation"')
                "$MINLP_GUARD_PYTHON" "$MINLP_GUARD_SCRIPT" scales || exit 86
                ;;
        esac
        return 0
    }
    set -T
    trap '__minlp_guard "$BASH_COMMAND"' DEBUG
fi
