from data_utils import load_data, preprocess_data
from math_utils import compute_average, compute_variance
from logger import log_message

def main():
    """Main entry point of the project."""
    log_message("Starting data processing pipeline...")

    # Step 1: load CSV data
    data = load_data("data/input.csv")

    # Step 2: clean negative or invalid entries
    cleaned = preprocess_data(data)

    # Step 3: compute statistics
    avg = compute_average(cleaned)
    var = compute_variance(cleaned)

    log_message(f"Average value: {avg:.2f}")
    log_message(f"Variance value: {var:.2f}")
    log_message("Pipeline finished successfully.")

if __name__ == "__main__":
    main()
