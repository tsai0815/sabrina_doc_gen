from logger import log_message

def compute_average(values):
    """Compute the average of a list of numbers."""
    log_message("Computing average...")
    if not values:
        return 0.0
    return sum(values) / len(values)

def compute_variance(values):
    """Compute the variance of a list of numbers."""
    log_message("Computing variance...")
    if not values:
        return 0.0
    mean = compute_average(values)
    return sum((x - mean) ** 2 for x in values) / len(values)
