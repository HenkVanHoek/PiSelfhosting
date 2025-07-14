cat <<'EOF_AWK_SCRIPT' > /tmp/extract_service_content.awk
BEGIN {
    in_services_block = 0;
    service_line_indent = -1; # To store indent of the service name line (e.g., 2 for '  dashy:')
}

/^services:/ {
    in_services_block = 1;
    next;
}

# End of services block if a top-level key like 'volumes:' or 'networks:' is found
/^(volumes|networks|version):$/ {
    if (in_services_block) { # Only end if we were in the services block
        in_services_block = 0;
    }
    next;
}

in_services_block {
    # Match leading spaces and get length
    match($0, /^[ \t]*/);
    current_line_indent = RLENGTH;

    # If this is the actual service name line (e.g., "  dashy:")
    # We identify it by having 2 spaces and containing a ':' followed by space/nothing
    if (current_line_indent == 2 && ($0 ~ /^[ ]{2}[a-zA-Z0-9_-]+:[[:space:]]*$/ || $0 ~ /^[ ]{2}[a-zA-Z0-9_-]+:[ \t]*\{.*\}$/)) {
        # This is the service name line itself. We skip it as it's added by deploy.sh.
        # But we capture its indent as the base for relative calculation.
        service_line_indent = current_line_indent;
        next;
    }

    # Process lines that are actual content of the service
    if (service_line_indent != -1 && current_line_indent >= service_line_indent) {
        # Calculate how many spaces to remove from the beginning of the line
        # This is the difference between current indent and the service_line_indent (2 spaces)
        spaces_to_remove = service_line_indent;

        # Strip those leading spaces
        line_content = substr($0, spaces_to_remove + 1);

        # Prepend the correct absolute indentation (4 spaces)
        # This maintains the relative spacing if it's already correct in the template
        print "    " line_content;
    }
}
EOF_AWK_SCRIPT
