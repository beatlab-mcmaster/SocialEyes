# Queries the device for various statistics and outputs them in JSON format.
# This script is intended to be run on the Android phone itself, not on a host machine.
# Author: Alexander Nguyen <nguya88@mcmaster.ca>
# License: See LICENSE file in the root of the repository for license information.

on_off_to_bool() {
  local value="$1"
    case "$value" in
        ON) echo "true" ;;
        OFF) echo "false" ;;
        *) echo "null" ;;
    esac
}

get_connected_usb_devices() {
    local usb_output=$(dumpsys usb)
    local devices=$(echo "$usb_output" | awk '
        BEGIN { in_section=0; bracket_depth=0; first=1 }
        /host_manager={/ { in_section=1; bracket_depth=0; next }
        in_section {
            for (i = 1; i <= length($0); i++) {
                c = substr($0, i, 1)
                if (c == "{") bracket_depth++
                else if (c == "}") bracket_depth--
                else if (c == "[") bracket_depth++
                else if (c == "]") bracket_depth--
            }
            if (/manufacturer_name/) {
                gsub(/^[ \t]+/, "", $0)
                gsub(/=/, ":", $0)
                split($0, arr, ":")
                mfg_value = arr[2]
                gsub(/^[ \t]+|[ \t]+$/, "", mfg_value)
            }
            if (/product_name/) {
                gsub(/^[ \t]+/, "", $0)
                gsub(/=/, ":", $0)
                split($0, arr, ":")
                prod_value = arr[2]
                gsub(/^[ \t]+|[ \t]+$/, "", prod_value)
                
                if (first == 0) {
                    printf ",\n"
                }
                first=0
                printf "      {\n"
                printf "        \"manufacturer_name\": \"%s\",\n", mfg_value
                printf "        \"product_name\": \"%s\"\n", prod_value
                printf "      }"
            }
            if (bracket_depth <= 0) {
                in_section=0
            }
        }
    ')
    
    echo "$devices"
}

get_phone_data() {
    local now=$(date -In -u)
    local timezone=$(getprop persist.sys.timezone)
    local battery=0
    
    # Cache dumpsys outputs to avoid multiple calls
    local display_out=$(dumpsys display)
    local window_out=$(dumpsys window)
    local battery_out=$(dumpsys battery)
    local wifi_out=$(dumpsys wifi 2>/dev/null | grep -m 1 "mWifiInfo")
    
    # Parse display state from cached output
    local display_on=$(on_off_to_bool $(echo "$display_out" | awk -F= '/mScreenState/ {print $2; exit}'))
    local display_locked=$(echo "$window_out" | awk -F= '/mDreamingLockscreen/ {print $3; exit}')
    
    # Parse battery from /sys or cached dumpsys
    if [ -f /sys/class/power_supply/battery/capacity ]; then
        battery=$(cat /sys/class/power_supply/battery/capacity || echo "0")
    else
        battery=$(echo "$battery_out" | awk '/level:/ {print $2; exit}' || echo "0")
    fi
    
    # Storage from df
    local storage_line=$(df -H /storage/self/primary/Documents | tail -1)
    local total=$(echo "$storage_line" | awk '{gsub(/[^0-9]/, "", $2); print $2}')
    local used=$(echo "$storage_line" | awk '{gsub(/[^0-9]/, "", $3); print $3}')
    local free=$(echo "$storage_line" | awk '{gsub(/[^0-9]/, "", $4); print $4}')

    # Parse wifi info from cached output
    local ssid=$(echo "$wifi_out" | awk 'match($0, /SSID: "[^"]+"/) {print substr($0, RSTART + 7, RLENGTH - 8); exit}')
    local bssid=$(echo "$wifi_out" | awk 'match($0, /BSSID: [^ ,]+/) {print substr($0, RSTART + 7, RLENGTH - 7); exit}')
    local rssi=$(echo "$wifi_out" | awk 'match($0, /RSSI: -?[0-9]+/) {print substr($0, RSTART + 6, RLENGTH - 6); exit}')

    # Android
    local android_version=$(getprop ro.build.version.release)
    local android_build=$(getprop ro.build.display.id)
    
    cat <<EOF
{
    "now": "$now",
    "timezone": "$timezone",
    "battery_level": ${battery:-0},
    "storage": {
      "total_gb": ${total:-0},
      "used_gb": ${used:-0},
      "free_gb": ${free:-0}
    },
    "display": {
      "is_locked": $display_locked,
      "is_on": $display_on
    },
    "usb_devices": [
$(get_connected_usb_devices)
    ],
    "wifi": {
      "ssid": "$ssid",
      "bssid": "$bssid",
      "rssi": $rssi
    },
    "android_version": "$android_version",
    "android_build": "$android_build"
  }
EOF
}

get_mp4_files() {
    local dir="$1"
    local mp4_output=""
    local temp_list=$(mktemp)
    
    local first=true
    find "$dir" -name "*.mp4" -type f -print0 > "$temp_list"
    while IFS= read -r -d '' mp4; do
        if [ "$first" = "false" ]; then
            mp4_output="${mp4_output},\n"
        fi
        first=false
        
        if [ -f "$mp4" ]; then
            filename=$(basename "$mp4")
            size=$(ls -Ln "$mp4" | awk '{print $5}')
            atime=$(date -d "$(stat -c "%x" "$mp4")" -In -u)
            mtime=$(date -d "$(stat -c "%y" "$mp4")" -In -u)
            
            mp4_output="${mp4_output}          {\n"
            mp4_output="${mp4_output}            \"file_name\": \"$filename\",\n"
            mp4_output="${mp4_output}            \"file_size_bytes\": $size,\n"
            mp4_output="${mp4_output}            \"creation_time\": \"$atime\",\n"
            mp4_output="${mp4_output}            \"modification_time\": \"$mtime\"\n"
            mp4_output="${mp4_output}          }"
        fi
    done < "$temp_list"
    rm -f "$temp_list"
    
    printf "%b" "$mp4_output"
}

get_recordings() {
  BASE_DIR="/storage/self/primary/Documents/Neon"

  local temp_list=$(mktemp)
  find "$BASE_DIR" -name "temp_*.json" -type f -print0 > "$temp_list"
  
  local first=true
  while IFS= read -r -d '' temp_json; do
      # Extract workspace_id and recording_id from path
      local workspace_id=$(printf "%s" "$temp_json" | awk -F/ '{print $(NF-2)}')
      local recording_id=$(printf "%s" "$temp_json" | awk -F/ '{print $(NF-1)}')

      local mp4_files=$(get_mp4_files "$BASE_DIR/$workspace_id/$recording_id")
      
      if [ "$first" = "false" ]; then
          printf ",\n"
      fi
      first=false

      cat <<EOF
      {
        "workspace_id": "$workspace_id",
        "recording_id": "$recording_id",
        "mp4_files": [
$mp4_files
        ]
      }
EOF
  done < "$temp_list"
  rm -f "$temp_list"
}

get_neon_app_version() {
    local package=$(dumpsys package com.pupillabs.neoncomp)
    local version_code=$(echo "$package" | awk -F= '/versionCode/ {sub(/[[:space:]].*/, "", $2); print $2; exit}')
    local version_name=$(echo "$package" | awk -F= '/versionName/ {print $2; exit}')
    local last_update_time_str=$(echo "$package" | awk -F= '/lastUpdateTime/ {print $2; exit}')
    cat <<EOF
{
        "version_name": "$version_name",
        "version_code": "$version_code",
        "last_update_time_str": "$last_update_time_str"
    }
EOF
}

get_neon_data() {
  local active=$(am stack list | grep neon >/dev/null && echo "true" || echo "false")
  read app_version_code app_version_name <<< "$(get_neon_app_version)"

    cat <<EOF
{
    "app_version": $(get_neon_app_version),
    "is_active": "$active",
    "recordings": [
$(get_recordings)
    ]
  }
EOF
}

# Main
cat <<EOF
{
  "version": "1.0",
  "phone": $(get_phone_data),
  "neon": $(get_neon_data)
}
EOF