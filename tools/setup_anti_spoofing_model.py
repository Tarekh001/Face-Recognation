import os
import sys
import shutil
import urllib.request
import zipfile
import subprocess

# ==========================================
# Script Otomatis: Download & Convert MiniFASNet
# (Menggunakan ZIP Download untuk menghindari error Git di Windows)
# ==========================================
print("🚀 Memulai proses setup Anti-Spoofing Model...")

model_target_dir = os.path.join("models", "anti_spoof")
os.makedirs(model_target_dir, exist_ok=True)
onnx_output_path = os.path.join(model_target_dir, "anti_spoof_model.onnx")

if os.path.exists(onnx_output_path):
    print(f"✅ Model ONNX sudah ada di {onnx_output_path}. Selesai!")
    sys.exit(0)

zip_path = "fas_repo.zip"
temp_dir = "temp_fas_repo"

# 1. Bersihkan sisa-sisa percobaan sebelumnya
if os.path.exists(temp_dir):
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except:
        pass
if os.path.exists(zip_path):
    os.remove(zip_path)

# 2. Download File Zip langsung dari Github (Tanpa GIT)
print("📥 Mengunduh Repositori MiniFASNet dalam format ZIP (30MB+)...")
zip_url = "https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/archive/refs/heads/master.zip"

def download_progress(block_num, block_size, total_size):
    downloaded = block_num * block_size
    percent = downloaded * 100 / total_size if total_size > 0 else 0
    sys.stdout.write(f"\r⏳ Progress Download: {min(percent, 100):.1f}%")
    sys.stdout.flush()

try:
    urllib.request.urlretrieve(zip_url, zip_path, download_progress)
    print("\n✅ Download Selesai!")
except Exception as e:
    print(f"\n❌ Gagal mendownload ZIP: {e}")
    sys.exit(1)

# 3. Ekstrak secara hati-hati (ABAIKAN folder log yang rusak di Windows)
print("📦 Mengekstrak file ZIP...")
extract_dir = os.path.join(temp_dir, "Silent-Face-Anti-Spoofing-master")
try:
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            # INI KUNCINYA: Abaikan folder 'saved_logs' penyebab error Windows!
            if "saved_logs" in member.filename:
                continue
            zf.extract(member, temp_dir)
except Exception as e:
    print(f"⚠️ Terjadi peringatan saat ekstrak (namun biasanya aman): {e}")

# 4. Buat Script Konversi di dalam folder ekstraksi
convert_script_code = f"""
import torch
import sys
import os

sys.path.append('.')

print("📦 Memuat arsitektur jaringan MiniFASNet...")
try:
    from src.model_lib.MiniFASNet import MiniFASNetV2
except Exception as e:
    print(f"Gagal Import: {{e}}")
    sys.exit(1)

print("🧠 Memuat bobot pre-trained (2.7_80x80_MiniFASNetV2.pth)...")
model = MiniFASNetV2(conv6_kernel=(5, 5))
model_path = os.path.join('resources', 'anti_spoof_models', '2.7_80x80_MiniFASNetV2.pth')
state_dict = torch.load(model_path, map_location='cpu')

new_state_dict = {{}}
for k, v in state_dict.items():
    name = k[7:] if k.startswith('module.') else k
    new_state_dict[name] = v

model.load_state_dict(new_state_dict)
model.eval()

print("🔄 Mengkonversi model ke format ONNX...")
dummy_input = torch.randn(1, 3, 80, 80)

# Gunakan absolute path dari script luar
output_path = r"{os.path.abspath(onnx_output_path)}"

# Export dengan pengaturan default agar cocok dengan versi PyTorch >= 2.0
torch.onnx.export(
    model, 
    dummy_input, 
    output_path, 
    export_params=True,
    opset_version=14,
    do_constant_folding=True,
    input_names=['input'], 
    output_names=['output']
)

print(f"🎉 Sukses! File ONNX disimpan di: {{output_path}}")
"""

convert_script_path = os.path.join(extract_dir, "convert_to_onnx.py")
with open(convert_script_path, "w", encoding="utf-8") as f:
    f.write(convert_script_code)

# 5. Jalankan Konversi
print("⚙️  Menjalankan Konversi Model...")
try:
    subprocess.run([sys.executable, "convert_to_onnx.py"], cwd=extract_dir, check=True)
except subprocess.CalledProcessError:
    print("\n❌ Konversi gagal. Pastikan 'pip install torch torchvision onnx' sukses.")
    sys.exit(1)

# 6. Pembersihan
print("🧹 Membersihkan file sampah temporary...")
try:
    if os.path.exists(zip_path):
        os.remove(zip_path)
    shutil.rmtree(temp_dir, ignore_errors=True)
except Exception:
    pass

print("\n✅ SEMUA PROSES SELESAI! Anda sudah bisa mencoba fitur liveness (Anti-Spoofing).")
