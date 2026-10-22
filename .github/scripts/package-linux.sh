#!/usr/bin/env bash
set -euo pipefail

source_executable=${1:?Usage: package-linux.sh executable package-directory readme archive}
package_dir=${2:?Usage: package-linux.sh executable package-directory readme archive}
readme=${3:?Usage: package-linux.sh executable package-directory readme archive}
archive=${4:?Usage: package-linux.sh executable package-directory readme archive}

if ! command -v patchelf >/dev/null; then
    echo "patchelf is required to make this Linux package relocatable" >&2
    exit 1
fi

rm -rf "$package_dir"
mkdir -p "$package_dir/lib"
cp "$source_executable" "$package_dir/astrond"
cp "$readme" "$package_dir/README.txt"

is_system_library() {
    case "$1" in
        linux-vdso*|ld-linux*|libc.so*|libc-*.so*|libm.so*|libmvec.so*|libpthread.so*|libdl.so*|librt.so*|libresolv.so*|libutil.so*|libanl.so*|libnss_*.so*)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

read_dependencies() {
    local line name resolved_path
    while IFS= read -r line; do
        if [[ "$line" =~ ^[[:space:]]*([^[:space:]]+)[[:space:]]+\=\>[[:space:]]+([^[:space:]]+) ]]; then
            name=${BASH_REMATCH[1]}
            resolved_path=${BASH_REMATCH[2]}
        elif [[ "$line" =~ ^[[:space:]]*(/[^[:space:]]+)[[:space:]] ]]; then
            resolved_path=${BASH_REMATCH[1]}
            name=$(basename "$resolved_path")
        else
            continue
        fi

        if [[ "$resolved_path" == "not" ]]; then
            echo "Unresolved runtime dependency: $line" >&2
            return 1
        fi
        printf '%s\t%s\n' "$name" "$resolved_path"
    done <<< "$1"
}

dependencies=$(ldd "$source_executable")
if grep -q '=> not found' <<< "$dependencies"; then
    echo "The Astron executable has unresolved runtime libraries:" >&2
    echo "$dependencies" >&2
    exit 1
fi

while IFS=$'\t' read -r name resolved_path; do
    [[ -n "$name" ]] || continue
    is_system_library "$name" && continue
    [[ -f "$resolved_path" ]] || {
        echo "Runtime dependency is not a file: $resolved_path" >&2
        exit 1
    }
    cp -L "$resolved_path" "$package_dir/lib/$name"
done < <(read_dependencies "$dependencies")

patchelf --set-rpath '$ORIGIN/lib' "$package_dir/astrond"
while IFS= read -r -d '' library; do
    patchelf --set-rpath '$ORIGIN' "$library"
done < <(find "$package_dir/lib" -type f -print0)

relocated_dependencies=$(env -u LD_LIBRARY_PATH ldd "$package_dir/astrond")
if grep -q '=> not found' <<< "$relocated_dependencies"; then
    echo "The packaged executable still has unresolved runtime libraries:" >&2
    echo "$relocated_dependencies" >&2
    exit 1
fi

while IFS=$'\t' read -r name resolved_path; do
    [[ -n "$name" ]] || continue
    is_system_library "$name" && continue
    if [[ "$resolved_path" != "$package_dir/lib/"* ]]; then
        echo "Runtime dependency was not bundled: $name => $resolved_path" >&2
        exit 1
    fi
done < <(read_dependencies "$relocated_dependencies")

tar -C "$(dirname "$package_dir")" -czf "$archive" "$(basename "$package_dir")"
