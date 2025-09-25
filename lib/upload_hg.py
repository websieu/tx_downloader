from huggingface_hub import HfApi, create_repo

from lib.telegram import send_telegram_message

def upload_to_hg(file_path, name_in_hg, repo_id='raymondt/raymond_image_v1', retry=0):
    try:

        api = HfApi()
        
        
        try:
            repo_info = api.dataset_info(repo_id)
            print(f"Repository '{repo_id}' already exists.")
        except Exception as e:
            print(f"Repository '{repo_id}' not found. Creating it...")
            # Create a new dataset repository.
            create_repo(repo_id, repo_type="dataset")

        print("Repository created.")
        api.upload_file(
            path_or_fileobj=file_path,
            path_in_repo=name_in_hg,
            repo_id=repo_id,
            repo_type="dataset",
        )
        print(f"https://huggingface.co/datasets/{repo_id}/blob/main/{name_in_hg}")
        return f"https://huggingface.co/datasets/{repo_id}/blob/main/{name_in_hg}"
    except Exception as e:
        send_telegram_message(f"upload to HG error: {e}")
        print(e)
        if retry < 3:
            print(f"Retrying upload... (Attempt {retry + 1})")
            return upload_to_hg(file_path, name_in_hg, repo_id=repo_id, retry=retry + 1)
        return False

def download_file_hg(file_name, repo_id='raymondt/cn_name', local_dir='output'):
    try:
        api = HfApi()
        file_path = api.hf_hub_download(repo_id=repo_id, filename=file_name, repo_type="dataset", local_dir=local_dir)
        print(f"File downloaded to: {file_path}")
        
        return file_path
    except Exception as e:
        #send_telegram_message(f"download from HG error: {e}")
        print(e)
        return False

if __name__ == "__main__":
    upload_to_hg("/root/wan/output/hethong.wav",'hethong_123.wav', repo_id='raymondt/bao_u_review')
    #download_file_hg('BV1yLADe1EpRa.json', repo_id='raymondt/cn_name', local_dir='/root/wan/projects/BV1TT421r7YU')