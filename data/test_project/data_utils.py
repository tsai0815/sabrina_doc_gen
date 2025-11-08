import csv
from logger import log_message

def load_data(filepath):
    """Load numeric data from a CSV file."""
    log_message(f"Loading data from {filepath}")
    with open(filepath, newline='') as csvfile:
        reader = csv.reader(csvfile)
        data = []
        for row in reader:
            try:
                val = float(row[0])
                data.append(val)
            except (ValueError, IndexError):
                log_message(f"Skipping invalid row: {row}")
    return data

def preprocess_data(data):
    """Clean data by removing negative values."""
    log_message("Preprocessing data (remove negatives)...")
    cleaned = [x for x in data if x >= 0]
    log_message(f"Cleaned {len(data) - len(cleaned)} invalid entries.")
    return cleaned
