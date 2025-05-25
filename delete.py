import os

def delete_files_from_list(file_list_path):
    with open(file_list_path, 'r', encoding='utf-8') as f:
        file_paths = [line.strip() for line in f if line.strip()]

    for path in file_paths:
        try:
            if os.path.isfile(path):
                os.remove(path)
                print(f"Deleted: {path}")
            else:
                print(f"Not found or not a file: {path}")
        except Exception as e:
            print(f"Error deleting {path}: {e}")

# === Run ===
if __name__ == "__main__":
    file_list_path = "delete.txt"  # Replace with your file path
    delete_files_from_list(file_list_path)
