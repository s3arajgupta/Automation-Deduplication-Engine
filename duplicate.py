import os
import hashlib
from collections import defaultdict

from collections import defaultdict
import os
import hashlib

def hash_file(path, block_size=65536):
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        while chunk := f.read(block_size):
            hasher.update(chunk)
    return hasher.hexdigest()

def find_duplicate_files(directory, error_file):
    size_map = defaultdict(list)
    hashes = defaultdict(list)

    # First pass: group files by size
    for root, _, files in os.walk(directory):
        for filename in files:
            file_path = os.path.join(root, filename)
            try:
                file_size = os.path.getsize(file_path)
                size_map[file_size].append(file_path)
            except Exception as e:
                with open(error_file, 'a', encoding='utf-8') as error_f:
                    error_f.write(f"[SIZE] Error reading {file_path}: {e}\n")

    # Second pass: hash only files that share the same size
    for size, files in size_map.items():
        if len(files) < 2:
            continue  # Skip unique sizes
        for file_path in files:
            try:
                file_hash = hash_file(file_path)
                hashes[file_hash].append(file_path)
            except Exception as e:
                with open(error_file, 'a', encoding='utf-8') as error_f:
                    error_f.write(f"[HASH] Error reading {file_path}: {e}\n")

    # Keep only actual duplicates (same hash)
    duplicates = {h: paths for h, paths in hashes.items() if len(paths) > 1}
    return duplicates

def log_duplicates(duplicates, log_file="duplicate_files.log"):
    try:
        print(f"Opening log file: {log_file}")
        with open(log_file, 'w', encoding='utf-8') as f:
            print("Log file opened successfully.")
            for group_index, paths in enumerate(duplicates.values(), start=1):
                f.write(f"Duplicate group {group_index}:\n")
                for path in paths:
                    f.write(f"  {path}\n")
                f.write("\n")
        print(f"Logged {len(duplicates)} duplicate groups to '{log_file}'")
    except Exception as e:
        print(f"Error while writing to log file: {e}")

# === Run ===
if __name__ == "__main__":

    # dir_path = input("Enter directory path to scan: ").strip()
    dir_path = r"C:\Users\swara\My Drive"
    # dir_path = r"C:\Users\swara\My Drive\@Interview Prep"
    if os.path.isdir(dir_path):
        log_file = os.path.expanduser("~/log.log")  # Writes to user home dir
        error_file = os.path.expanduser("~/error.log")  # Writes to user home dir
        duplicates = find_duplicate_files(dir_path, error_file)
        if duplicates:
            log_duplicates(duplicates, log_file)
            print("log_file", log_file)
            # log_duplicates(duplicates)
        else:
            print("No duplicate files found.")
    else:
        print("Invalid directory path.")
