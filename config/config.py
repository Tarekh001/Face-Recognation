import os

BASE_DIR = os.getcwd()
EMBEDDINGS_DIR = os.path.join(BASE_DIR, "samples_embedding")
TEMP_DIR = os.path.join(BASE_DIR, "temp")  # Add this
THRESHOLD = 0.75

# Create TEMP_DIR if it doesn’t exist
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)