# service_formatter.awk - Final, extremely robust, and simplified version for all indentation types
# This script formats Docker Compose service and volume blocks based on section_type.
# It expects the full content of a docker-compose.yml.template as input.

# section_type is passed via -v from deploy.sh (either "service" or "volume").

# --- Control blocks for top-level sections (setting state for AWK's internal parsing) ---
# These blocks will consume the section header lines (e.g., "services:", "volumes:").

# When 'services:' is found, activate service block parsing state
/^services:$/ {
    current_section = "services";
    next; # Consume 'services:' line
}

# When 'volumes:' is found, activate volume block parsing state
/^volumes:$/ {
    current_section = "volumes";
    next; # Consume 'volumes:' line
}

# When 'networks:' or 'version:' is found, deactivate any active section states
/^(networks|version):$/ {
    current_section = "none"; # No active section
    next; # Consume 'networks:' or 'version:' line
}

# --- Processing blocks based on 'section_type' parameter and current line content ---

# This block processes lines for SERVICES when 'section_type' is set to "service" in deploy.sh
section_type == "service" && current_section == "services" {
    # Match leading whitespace (spaces or tabs) for the current line.
    match($0, /^[ \t]*/);
    actual_indent_len = RLENGTH; # Length of matched whitespace
    line_content = substr($0, actual_indent_len + 1); # Content after its own indentation

    # Skip the service name line itself (e.g., "  myservice:") as deploy.sh prints it
    if (actual_indent_len == 2 && (line_content ~ /^[a-zA-Z0-9_-]+:[[:space:]]*$/ || line_content ~ /^[a-zA-Z0-9_-]+:[ \t]*\{.*\}$/)) {
        next; # Skip this line from the template input
    }

    # Print properties (e.g., "    image:") with 4 spaces.
    # Print list items (e.g., "      - "8080:80"") with 6 spaces.
    # Print deeper nested items (e.g., "        key: value") with 8 spaces.
    # This assumes consistent 2-space increments in your templates.
    # It dynamically calculates the output indent based on the actual input indent.
    if (actual_indent_len >= 4) { # Check if it's content for a service
        # Output indentation = 4 + (actual_indent - 4) = actual_indent.
        # But we want fixed 4, 6, 8. So we need to normalize:
        if (actual_indent_len == 4) printf "%*s%s\n", 4, "", line_content;
        else if (actual_indent_len == 6) printf "%*s%s\n", 6, "", line_content;
        else if (actual_indent_len == 8) printf "%*s%s\n", 8, "", line_content;
        else { # Fallback for unexpected deeper levels, keep relative offset from 2-space base
            printf "%*s%s\n", 2 + (actual_indent_len - 2), "", line_content;
        }
    }
    next; # Process next line
}


# This block processes lines for VOLUMES when 'section_type' is set to "volume" in deploy.sh
section_type == "volume" && current_section == "volumes" {
    # Match leading whitespace (spaces or tabs) for the current line.
    match($0, /^[ \t]*/);
    actual_indent_len = RLENGTH; # Length of leading whitespace
    line_content = substr($0, actual_indent_len + 1); # Content after its own indentation

    # Match volume name definition (e.g., "  mariadb_data:")
    # These should be indented 2 spaces/tabs in the template. Print with fixed 2 spaces.
    if (actual_indent_len == 2 && (line_content ~ /^[a-zA-Z0-9_-]+:[[:space:]]*$/ || line_content ~ /^[a-zA-Z0-9_-]+:[ \t]*\{.*\}$/)) {
        printf "%*s%s\n", 2, "", line_content;
        next;
    }

    # Match volume property lines (e.g., "    name: unique-name", "    driver_opts:")
    # These should be indented 4 spaces/tabs in the template. Print with fixed 4 spaces.
    if (actual_indent_len == 4 && (line_content ~ /^[a-zA-Z0-9_-]+:[[:space:]]*.*$/)) {
        printf "%*s%s\n", 4, "", line_content;
        next;
    }

    # Skip any other lines within the volume template section (e.g., comments, blank lines, or unexpected indentation).
    next; # Skip all other lines that are not explicitly matched to avoid unwanted output.
}

# --- Default action for all lines not processed by any specific section_type block or global section control ---
# This ensures that only explicitly matched lines are processed and printed.
# Any line not matched by active rules is skipped.
{ next }