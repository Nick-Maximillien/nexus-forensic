from huggingface_hub import HfApi, create_repo, login
from kaggle_secrets import UserSecretsClient

# 1. AUTHENTICATION & SETUP
print("Authenticating with stored HF_TOKEN...")
user_secrets = UserSecretsClient()
hf_token = user_secrets.get_secret("HF_TOKEN")

# Log in to ensure the environment is authenticated
login(token=hf_token)

# Initialize API with the token
api = HfApi(token=hf_token)

# Automatically get the username associated with the token
user_info = api.whoami()
username = user_info['name']
print(f"Authenticated as: {username}")

# 2. CONFIGURATION
model_name = "medgemma-4b-forensic-gguf"
file_path = "medgate_brain_4b_Q8.gguf"
repo_id = f"{username}/{model_name}"

# 3. CREATE REPOSITORY
print(f"Creating repository: {repo_id}")
try:
    create_repo(repo_id, repo_type="model", exist_ok=True, token=hf_token)
except Exception as e:
    print(f"Repo check warning (might already exist): {e}")

# 4. UPLOAD FILE
print(f"Uploading {file_path} to Hugging Face...")

try:
    api.upload_file(
        path_or_fileobj=file_path,
        path_in_repo=file_path,
        repo_id=repo_id,
        repo_type="model",
    )
    print("Upload complete.")
    print(f"Your model is available at: https://huggingface.co/{repo_id}")
except Exception as e:
    print(f"Upload failed: {e}")